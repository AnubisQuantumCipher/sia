#!/usr/bin/env python3
"""Owned process lifetimes for release scripts, not a SIA runtime member.

This module is self-contained deliberately: uninstall can retire its source
tree while a pinned, sealed copy still owns the release transaction.  It does
not import the installed runtime or discover replacement code through sys.path.

The outer owner admits one Bash worker over an inherited private socket.  The
worker requests drainage before cleanup and lease handoffs; lease descriptors
are transferred, not reopened by pathname.  Command workers use the same
subreaper/drainage primitive before reporting any result.
"""

import array
import contextlib
import ctypes
import errno
import fcntl
import json
import os
import re
import selectors
import shlex
import signal
import socket
import stat
import struct
import subprocess
import sys
import time


MAX_SOURCE_BYTES = 16_777_216
MAX_CAPTURE_BYTES = 1_048_576
MAX_CONTROL_BYTES = 4_096
MAX_COMMAND_LABEL_CHARS = 160
ALLOWED_DEADLINES = {120, 300, 1800}
CAPTURE_DEADLINE = 120
LEADER_POLL_SECONDS = 15
# Values from Linux's UAPI linux/prctl.h, not an architecture syscall number.
PR_SET_CHILD_SUBREAPER = 36
PR_GET_CHILD_SUBREAPER = 37
LEASE_NAME = re.compile(r"SIA_[A-Z_]+_FD\Z")
COMMAND_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _./:-]*\Z")
DIRECTORY_FLAGS = (os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW)
SETUP_HANDOFF_ABI = "1"
SETUP_HANDOFF_FDS = {
    "helper_fd": "SIA_SETUP_HANDOFF_HELPER_FD",
    "installer_fd": "SIA_SETUP_HANDOFF_INSTALLER_FD",
    "owner_fd": "SIA_SETUP_HANDOFF_OWNER_FD",
    "root_fd": "SIA_SETUP_HANDOFF_ROOT_FD",
}
SETUP_HANDOFF_PREFIX = "SIA_SETUP_HANDOFF_"

# Emitted only after authenticated admission to the sealed worker. Policy
# stays here; release scripts contain only the entry and command delegation.
SHELL_CONTROL = r'''
SIA_LIFETIME_SOURCE="/proc/self/fd/$SIA_LIFETIME_SOURCE_FD"
SIA_LIFETIME_SOURCE_ROOT="/proc/self/fd/$SIA_LIFETIME_SOURCE_ROOT_FD"
readonly SIA_LIFETIME_SOURCE_ROOT_PATH SIA_LIFETIME_SOURCE_ROOT
readonly SIA_LIFETIME_SOURCE_ROOT_FD SIA_LIFETIME_CONTROL_FD
readonly SIA_LIFETIME_SOURCE_FD SIA_LIFETIME_SOURCE
lifetime_quiesce() {
  local response
  printf 'QUIESCE %s\n' "$1" >&"$SIA_LIFETIME_CONTROL_FD" || return 1
  IFS= read -r response <&"$SIA_LIFETIME_CONTROL_FD" || return 1
  [ "$response" = OK ]
}
lifetime_register() {
  python3 -I "$SIA_LIFETIME_SOURCE" register \
    "$SIA_LIFETIME_CONTROL_FD" "$1" "$2"
}
lifetime_release() {
  lifetime_quiesce handoff || return 1
  python3 -I "$SIA_LIFETIME_SOURCE" release \
    "$SIA_LIFETIME_CONTROL_FD" "$1"
}
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
'''


class LifetimeRefusal(Exception):
    """An owned lifetime could not be established or safely handed off."""


def _close(descriptor):
    if descriptor is not None:
        with contextlib.suppress(OSError):
            os.close(descriptor)


def _features():
    """Require native containment before opening a worker's mutation path."""
    for name in ("pidfd_open", "waitid", "WNOWAIT", "WSTOPPED", "memfd_create"):
        if not hasattr(os, name):
            raise LifetimeRefusal(f"required lifetime feature unavailable: {name}")
    if not hasattr(signal, "pidfd_send_signal"):
        raise LifetimeRefusal("required lifetime feature unavailable: pidfd signaling")
    descriptor = None
    try:
        descriptor = os.pidfd_open(os.getpid(), 0)
        signal.pidfd_send_signal(descriptor, 0)
    except OSError as error:
        raise LifetimeRefusal(f"pidfd lifetime feature unavailable: {error}") from error
    finally:
        _close(descriptor)
    try:
        library = ctypes.CDLL(None, use_errno=True)
        operation = library.prctl
        operation.restype = ctypes.c_int
        if operation(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "cannot establish subreaper")
        enabled = ctypes.c_int()
        if operation(PR_GET_CHILD_SUBREAPER, ctypes.byref(enabled), 0, 0, 0) != 0 \
                or enabled.value != 1:
            raise OSError(ctypes.get_errno(), "subreaper was not established")
    except (AttributeError, OSError) as error:
        raise LifetimeRefusal(f"subreaper lifetime feature unavailable: {error}") from error
    # SIGCHLD=SIG_IGN would discard zombies and invalidate the no-reaping
    # collection invariant. Both this owner and its admitted Bash start with
    # the ordinary disposition; the owned worker must not override it.
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    _children(os.getpid())


def _children(parent):
    # This is not an arbitrary live process-tree snapshot. Collection is
    # restricted to this single-thread owner and an observed-stopped Bash
    # worker. Neither reaps during collection. Exited children therefore stay
    # on these lists until this owner deliberately consumes their wait status.
    path = f"/proc/{parent}/task/{parent}/children"
    try:
        with open(path, "rb") as stream:
            payload = stream.read(MAX_SOURCE_BYTES + 1)
    except OSError as error:
        raise LifetimeRefusal(f"owned child identities unavailable: {error}") from error
    if len(payload) > MAX_SOURCE_BYTES:
        raise LifetimeRefusal("owned child identity list exceeded its byte ceiling")
    try:
        return {int(value, 10) for value in payload.split()}
    except ValueError as error:
        raise LifetimeRefusal("owned child identity list is malformed") from error


def _terminal(descriptor):
    with selectors.DefaultSelector() as selector:
        selector.register(descriptor, selectors.EVENT_READ)
        return bool(selector.select(0))


def _send_signal(descriptor, value):
    with contextlib.suppress(ProcessLookupError):
        signal.pidfd_send_signal(descriptor, value)


def _exit_info(process):
    return os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT)


def _result(info):
    if info.si_code == os.CLD_EXITED:
        return info.si_status
    return 128 + info.si_status


def _freeze(process, descriptor):
    if _terminal(descriptor):
        return False
    _send_signal(descriptor, signal.SIGSTOP)
    observed = os.waitid(os.P_PID, process.pid,
                         os.WSTOPPED | os.WEXITED | os.WNOWAIT)
    return observed.si_code == os.CLD_STOPPED


def _drain_once(stopped_worker, reaped):
    """Kill, observe terminal state, then reap only owned descendants.

    Killing a child makes its descendants adopt upward, including descendants
    that created sessions or were themselves subreapers. New adoptees are
    pinned before signaling. No reaping occurs until the pinned set is closed
    under adoption and every member is terminal. A kernel task that cannot
    terminate keeps this owner/its leases alive: there is no timeout path that
    reports drainage or releases ownership while a mutator remains live.
    """
    pinned = {}
    worker_pid = None if stopped_worker is None else stopped_worker.pid
    try:
        while True:
            identities = _children(os.getpid())
            if worker_pid is not None:
                identities.discard(worker_pid)
                identities.update(_children(worker_pid))
            for pid in identities - pinned.keys():
                pinned[pid] = os.pidfd_open(pid, 0)
                _send_signal(pinned[pid], signal.SIGKILL)
            pending = [descriptor for descriptor in pinned.values()
                       if not _terminal(descriptor)]
            if not pending:
                # A separate collection after exit observation admits children
                # orphaned by those exits. Empty output by itself is not proof.
                adopted = _children(os.getpid())
                if worker_pid is not None:
                    adopted.discard(worker_pid)
                    adopted.update(_children(worker_pid))
                if adopted.issubset(pinned):
                    break
                continue
            with selectors.DefaultSelector() as selector:
                for descriptor in pending:
                    selector.register(descriptor, selectors.EVENT_READ)
                selector.select(LEADER_POLL_SECONDS)
        for pid in pinned:
            try:
                observed, status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                # A stopped Bash still owns its immediate zombie children.
                # It will reap them after the acknowledged handoff resumes it.
                continue
            if observed != pid:
                raise LifetimeRefusal("owned descendant was not terminal at reap")
            reaped[pid] = status
        return reaped
    finally:
        for descriptor in pinned.values():
            _close(descriptor)


def _drain(stopped_worker=None):
    # Losing observation is not successful drainage. Retain the owner's
    # duplicate leases while retrying a transient /proc or pidfd failure.
    # A permanent kernel refusal deliberately leaves this owner present for
    # operator diagnosis instead of exposing a generation with live mutators.
    last_error = None
    reaped = {}
    while True:
        try:
            return _drain_once(stopped_worker, reaped)
        except (OSError, LifetimeRefusal) as error:
            message = str(error)
            if message != last_error:
                print(f"SIA release lifetime retains ownership: {message}",
                      file=sys.stderr, flush=True)
                last_error = message
            with selectors.DefaultSelector() as selector:
                selector.select(LEADER_POLL_SECONDS)


class _Signals:
    def __init__(self):
        self.first = None
        self.previous = {}
        self.read_fd, self.write_fd = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
        self.previous_wakeup = signal.set_wakeup_fd(self.write_fd)
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            self.previous[signum] = signal.getsignal(signum)
            signal.signal(signum, self._record)

    def _record(self, signum, _frame):
        if self.first is None:
            self.first = signum

    def consume(self):
        with contextlib.suppress(BlockingIOError):
            os.read(self.read_fd, MAX_CONTROL_BYTES)

    def close(self):
        signal.set_wakeup_fd(self.previous_wakeup)
        for signum, disposition in self.previous.items():
            signal.signal(signum, disposition)
        _close(self.read_fd)
        _close(self.write_fd)


def _generation(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
            info.st_gid, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _owner_controlled(info):
    return info.st_uid == os.geteuid() \
        and stat.S_IMODE(info.st_mode) & (stat.S_IWGRP | stat.S_IWOTH) == 0


def _open_absolute_directory(path):
    absolute = os.path.abspath(path)
    descriptor = os.open(os.sep, DIRECTORY_FLAGS)
    try:
        for component in [part for part in absolute.split(os.sep) if part]:
            child = os.open(component, DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        _close(descriptor)
        raise


def _admit_source_directory(descriptor, label):
    info = os.fstat(descriptor)
    if not stat.S_ISDIR(info.st_mode) or not _owner_controlled(info):
        raise LifetimeRefusal(f"{label} is not an owner-controlled directory")
    return _generation(info)


def _snapshot_source_descriptor(descriptor, path, label, *, dir_fd=None):
    """Seal one stable regular file already bound to its source directory."""
    sealed = None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not _owner_controlled(before) \
                or before.st_nlink != 1 \
                or before.st_size > MAX_SOURCE_BYTES:
            raise LifetimeRefusal(f"{label} source is not bounded and owner-controlled")
        current = os.stat(path, dir_fd=dir_fd, follow_symlinks=False)
        if _generation(before) != _generation(current):
            raise LifetimeRefusal(f"{label} source changed during admission")
        chunks = []
        total = 0
        while True:
            block = os.pread(
                descriptor, MAX_SOURCE_BYTES + 1 - total, total)
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > MAX_SOURCE_BYTES:
                raise LifetimeRefusal(f"{label} source exceeded its byte ceiling")
        after = os.fstat(descriptor)
        current = os.stat(path, dir_fd=dir_fd, follow_symlinks=False)
        if _generation(before) != _generation(after) \
                or _generation(after) != _generation(current):
            raise LifetimeRefusal(f"{label} source changed during admission")
        sealed = os.memfd_create(label, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        pending = memoryview(b"".join(chunks))
        while pending:
            written = os.write(sealed, pending)
            if written <= 0:
                raise LifetimeRefusal(f"{label} source snapshot was short-written")
            pending = pending[written:]
        os.lseek(sealed, 0, os.SEEK_SET)
        fcntl.fcntl(sealed, fcntl.F_ADD_SEALS,
                    fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK |
                    fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE)
        result, sealed = sealed, None
        return result
    finally:
        _close(sealed)


def _source_snapshot(path, label, *, dir_fd=None):
    descriptor = os.open(
        path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=dir_fd)
    try:
        return _snapshot_source_descriptor(
            descriptor, path, label, dir_fd=dir_fd)
    finally:
        _close(descriptor)


def _setup_handoff(entry):
    """Decode the first-light descriptor handoff, if this is that entry."""
    abi = os.environ.get("SIA_SETUP_HANDOFF_ABI")
    if abi is None:
        return None
    if abi != SETUP_HANDOFF_ABI:
        raise LifetimeRefusal("unsupported first-light descriptor handoff")
    source_root = os.environ.get("SIA_SETUP_HANDOFF_ROOT_PATH")
    if not isinstance(source_root, str) \
            or not os.path.isabs(source_root) \
            or os.path.normpath(source_root) != source_root \
            or len(source_root.encode("utf-8")) > MAX_CONTROL_BYTES:
        raise LifetimeRefusal("first-light source root display is invalid")
    handoff = {"source_root": source_root}
    for key, name in SETUP_HANDOFF_FDS.items():
        raw = os.environ.get(name, "")
        if re.fullmatch(r"(?:0|[1-9][0-9]*)", raw) is None:
            raise LifetimeRefusal("first-light descriptor handoff is malformed")
        handoff[key] = int(raw, 10)
    if entry != f"/proc/self/fd/{handoff['installer_fd']}" \
            or sys.argv[0] != f"/proc/self/fd/{handoff['owner_fd']}":
        raise LifetimeRefusal(
            "first-light descriptor handoff is not bound to its sources")
    return handoff


def _parent_pid(pid):
    with open(f"/proc/{pid}/status", encoding="ascii") as stream:
        for line in stream:
            if line.startswith("PPid:"):
                return int(line.split()[1], 10)
    raise LifetimeRefusal("control sender parent could not be established")


def _read_line(channel):
    payload = bytearray()
    while not payload.endswith(b"\n"):
        block = channel.recv(1)
        if not block:
            raise LifetimeRefusal("lifetime owner closed its control channel")
        payload.extend(block)
        if len(payload) > MAX_CONTROL_BYTES:
            raise LifetimeRefusal("lifetime control response exceeded its byte ceiling")
    return payload.decode("utf-8", "strict").rstrip("\n")


class _Requests:
    """Bounded incremental frames; an incomplete sender cannot park the owner."""
    def __init__(self):
        self.payload = bytearray()
        self.received = []
        self.credentials = None

    def receive(self, channel):
        try:
            data, ancillary, flags, _address = channel.recvmsg(
                MAX_CONTROL_BYTES + 1 - len(self.payload),
                socket.CMSG_SPACE(struct.calcsize("3i"))
                + socket.CMSG_SPACE(array.array("i").itemsize),
                socket.MSG_DONTWAIT | socket.MSG_CMSG_CLOEXEC)
        except BlockingIOError:
            return None
        try:
            for level, kind, content in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS:
                    current = struct.unpack("3i", content)
                    if self.credentials is not None and current != self.credentials:
                        raise LifetimeRefusal("lifetime frame changed authenticated sender")
                    self.credentials = current
                elif level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    values = array.array("i")
                    values.frombytes(content)
                    self.received.extend(values)
            if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
                raise LifetimeRefusal("lifetime request ancillary data was truncated")
            if not data:
                if self.payload:
                    raise LifetimeRefusal("lifetime owner received an incomplete request")
            self.payload.extend(data)
            if len(self.payload) > MAX_CONTROL_BYTES or self.payload.count(b"\n") > 1 \
                    or (b"\n" in self.payload and not self.payload.endswith(b"\n")):
                raise LifetimeRefusal("lifetime request exceeded one bounded frame")
            if data and not self.payload.endswith(b"\n"):
                return None
            result = bytes(self.payload), self.credentials, self.received
            self.payload, self.credentials, self.received = bytearray(), None, []
            return result
        except BaseException:
            self.close()
            raise

    def close(self):
        for descriptor in self.received:
            _close(descriptor)
        self.received = []


def _control_socket(descriptor):
    channel = socket.socket(fileno=os.dup(descriptor))
    try:
        peer_pid, peer_uid, _peer_gid = struct.unpack(
            "3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                     struct.calcsize("3i")))
        if peer_uid != os.geteuid() or _parent_pid(os.getppid()) != peer_pid:
            raise LifetimeRefusal("lifetime control peer is not this worker's owner")
        return channel
    except BaseException:
        channel.close()
        raise


def _sealed(descriptor):
    seals = fcntl.fcntl(descriptor, fcntl.F_GET_SEALS)
    required = (fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK |
                fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE)
    if seals & required != required:
        raise LifetimeRefusal("inherited release source is not sealed")


def admit(control_fd, source_fd, script_fd, root_fd, worker_pid):
    if worker_pid != os.getppid():
        raise LifetimeRefusal("lifetime admission is not from its worker")
    _sealed(source_fd)
    _sealed(script_fd)
    _admit_source_directory(root_fd, "inherited release root")
    with _control_socket(control_fd) as channel:
        channel.sendall(
            f"ADMIT {worker_pid} {source_fd} {script_fd} {root_fd}\n".encode())
        response = json.loads(_read_line(channel))
    if set(response) != {"root_fd", "source_root", "worker"} \
            or type(response["root_fd"]) is not int \
            or type(response["worker"]) is not int \
            or response["root_fd"] != root_fd \
            or response["worker"] != worker_pid \
            or not isinstance(response["source_root"], str):
        raise LifetimeRefusal("lifetime admission response is not bound to its worker")
    print("SIA_LIFETIME_SOURCE_ROOT_PATH="
          + shlex.quote(response["source_root"]))
    print("SIA_LIFETIME_SOURCE_ROOT_FD=" + shlex.quote(str(root_fd)))
    print("SIA_LIFETIME_CONTROL_FD=" + shlex.quote(str(control_fd)))
    print("SIA_LIFETIME_SOURCE_FD=" + shlex.quote(str(source_fd)))
    print(SHELL_CONTROL)


def lease(control_fd, action, name, descriptor=None):
    if not LEASE_NAME.fullmatch(name):
        raise LifetimeRefusal("invalid owned lease name")
    with _control_socket(control_fd) as channel:
        payload = f"{action.upper()} {os.getppid()} {name}\n".encode()
        if action == "register":
            rights = array.array("i", [descriptor])
            channel.sendmsg([payload], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, rights)])
        else:
            channel.sendall(payload)
        if _read_line(channel) != "OK":
            raise LifetimeRefusal("owned lease handoff was not acknowledged")


def _admit_lease(descriptor):
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o022:
        raise LifetimeRefusal("lease descriptor is not owner-controlled")
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _pin_caller(expected):
    # Bash may exec its final command in a command-substitution child. In
    # that case its supplied identity is this process, and its still-live
    # parent remains the caller whose death must cancel the owned command.
    caller = os.getppid() if expected is None or expected == os.getpid() else expected
    if not hasattr(os, "pidfd_open"):
        raise LifetimeRefusal("caller pidfd admission is unavailable")
    try:
        descriptor = os.pidfd_open(caller, 0)
    except OSError as error:
        raise LifetimeRefusal(f"caller pidfd admission failed: {error}") from error
    if os.getppid() != caller or _terminal(descriptor):
        _close(descriptor)
        raise LifetimeRefusal("original caller died before lifetime admission")
    return descriptor


def _require_caller(descriptor):
    if _terminal(descriptor):
        raise LifetimeRefusal("original caller died before owned work could launch")


def supervise(entry, arguments, *, setup_lease=None, caller=None,
              setup_handoff=None, flat_source=False):
    if setup_handoff is None:
        entry = os.path.abspath(entry)
        if os.path.basename(entry) not in {"install.sh", "uninstall.sh"}:
            raise LifetimeRefusal(
                "lifetime owner admits only release-script entries")
        if flat_source and os.path.basename(entry) != "uninstall.sh":
            raise LifetimeRefusal("installed lifetime permits only uninstall")
        source_root = os.path.dirname(entry)
    else:
        source_root = setup_handoff["source_root"]
    root_fd = bin_fd = script_fd = source_fd = parent_fd = worker_fd = None
    helper_snapshot_fd = None
    parent_channel = child_channel = signals = process = None
    leases = {}
    cleanup_started = False
    cancellation = None
    admitted = False
    result = None
    requests = _Requests()
    try:
        parent_fd = _pin_caller(caller)
        root_fd = (_open_absolute_directory(source_root)
                   if setup_handoff is None
                   else os.dup(setup_handoff["root_fd"]))
        root_generation = _admit_source_directory(root_fd, "release source root")
        bin_fd = (os.dup(root_fd) if flat_source else
                  os.open("bin", DIRECTORY_FLAGS, dir_fd=root_fd))
        bin_generation = _admit_source_directory(
            bin_fd, ("installed release source root" if flat_source else
                     "release source bin directory"))
        _features()
        if setup_lease is not None:
            descriptor = os.dup(setup_lease)
            leases["SIA_SETUP_LOCK_FD"] = descriptor
            _admit_lease(descriptor)
            _close(setup_lease)
        if setup_handoff is None:
            source_fd = _source_snapshot(
                "sialifetime.py", "sia-lifetime-source", dir_fd=bin_fd)
            script_fd = _source_snapshot(
                os.path.basename(entry), "sia-release-script",
                dir_fd=root_fd)
        else:
            helper_snapshot_fd = _snapshot_source_descriptor(
                setup_handoff["helper_fd"], "sia-setup",
                "sia-first-light-helper", dir_fd=bin_fd)
            source_fd = _snapshot_source_descriptor(
                setup_handoff["owner_fd"], "sialifetime.py",
                "sia-lifetime-source", dir_fd=bin_fd)
            script_fd = _snapshot_source_descriptor(
                setup_handoff["installer_fd"], "install.sh",
                "sia-release-script", dir_fd=root_fd)
        hierarchy_changed = (
            root_generation != _generation(os.fstat(root_fd))
            or bin_generation != _generation(os.fstat(bin_fd)))
        if not flat_source:
            hierarchy_changed = hierarchy_changed or (
                bin_generation != _generation(os.stat(
                    "bin", dir_fd=root_fd, follow_symlinks=False)))
        if hierarchy_changed:
            raise LifetimeRefusal("release source hierarchy changed during admission")
        _close(bin_fd)
        bin_fd = None
        _close(helper_snapshot_fd)
        helper_snapshot_fd = None
        parent_channel, child_channel = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        parent_channel.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        signals = _Signals()
        environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith("SIA_LIFETIME_")
            and not key.startswith(SETUP_HANDOFF_PREFIX)}
        # Internal Bash re-entry cannot acquire startup code from ambient
        # hooks. Consent variables and the caller's tool/environment choices
        # remain intact; first-light applies its separate fresh-consent scrub.
        environment.pop("BASH_ENV", None)
        environment.pop("ENV", None)
        control_fd = child_channel.fileno()
        _require_caller(parent_fd)
        process = subprocess.Popen(
            ["/bin/bash", f"/proc/self/fd/{script_fd}", "--sia-release-worker",
             str(control_fd), str(source_fd), str(script_fd), str(root_fd),
             *arguments],
            env=environment, start_new_session=True,
            pass_fds=(control_fd, source_fd, script_fd, root_fd),
            close_fds=True)
        worker_fd = os.pidfd_open(process.pid, 0)
        child_channel.close()
        child_channel = None
        with selectors.DefaultSelector() as selector:
            selector.register(worker_fd, selectors.EVENT_READ, "worker")
            selector.register(parent_fd, selectors.EVENT_READ, "parent")
            selector.register(signals.read_fd, selectors.EVENT_READ, "signal")
            selector.register(parent_channel, selectors.EVENT_READ, "control")
            while not _terminal(worker_fd):
                for key, _events in selector.select(LEADER_POLL_SECONDS):
                    if key.data == "signal":
                        signals.consume()
                    elif key.data == "parent":
                        selector.unregister(parent_fd)
                        if signals.first is None:
                            signals.first = signal.SIGTERM
                    elif key.data == "control":
                        request = requests.receive(parent_channel)
                        if request is None:
                            continue
                        data, credentials, received = request
                        try:
                            if not data:
                                selector.unregister(parent_channel)
                                # File-descriptor teardown precedes the
                                # worker's pidfd exit notification. EOF alone
                                # is not an observed cancellation or status.
                                continue
                            if credentials is None or credentials[1] != os.geteuid():
                                raise LifetimeRefusal("lifetime request has no owned credentials")
                            sender = credentials[0]
                            parts = data.decode("ascii", "strict").strip().split()
                            if parts == ["QUIESCE", "cleanup"] or parts == ["QUIESCE", "handoff"]:
                                if not admitted or sender != process.pid or received:
                                    raise LifetimeRefusal("drainage request is not from admitted Bash")
                                if _freeze(process, worker_fd):
                                    _drain(process)
                                    cleanup_started = cleanup_started or parts[1] == "cleanup"
                                    parent_channel.sendall(b"OK\n")
                                    _send_signal(worker_fd, signal.SIGCONT)
                            elif parts == ["ADMIT", str(process.pid), str(source_fd),
                                          str(script_fd), str(root_fd)]:
                                if admitted or received or _parent_pid(sender) != process.pid:
                                    raise LifetimeRefusal("release worker admission is not owned")
                                _require_caller(parent_fd)
                                admitted = True
                                parent_channel.sendall((json.dumps({
                                    "root_fd": root_fd,
                                    "source_root": source_root,
                                    "worker": process.pid}) + "\n").encode())
                            elif len(parts) == 3 and parts[0] in {"REGISTER", "RELEASE"}:
                                if not admitted or parts[1] != str(process.pid) \
                                        or _parent_pid(sender) != process.pid \
                                        or not LEASE_NAME.fullmatch(parts[2]):
                                    raise LifetimeRefusal("lease request is not from admitted worker")
                                name = parts[2]
                                if parts[0] == "REGISTER":
                                    if len(received) != 1 or name in leases:
                                        raise LifetimeRefusal("lease registration is ambiguous")
                                    descriptor = received.pop()
                                    try:
                                        _admit_lease(descriptor)
                                    except BaseException:
                                        _close(descriptor)
                                        raise
                                    leases[name] = descriptor
                                elif received:
                                    raise LifetimeRefusal("lease release carried an unexpected descriptor")
                                else:
                                    _close(leases.pop(name, None))
                                parent_channel.sendall(b"OK\n")
                            else:
                                raise LifetimeRefusal("unrecognized lifetime control request")
                        finally:
                            for descriptor in received:
                                _close(descriptor)
                if signals.first is not None and cancellation is None:
                    cancellation = signals.first
                    if not cleanup_started and _freeze(process, worker_fd):
                        _drain(process)
                        _send_signal(worker_fd, signal.SIGTERM)
                        _send_signal(worker_fd, signal.SIGCONT)
            info = _exit_info(process)
            process.returncode = (info.si_status if info.si_code == os.CLD_EXITED
                                  else -info.si_status)
            _drain()
            result = 128 + cancellation if cancellation is not None else _result(info)
    finally:
        # Even an ordinary Python/control error must not close duplicate
        # leases over still-running mutators. A failed control protocol cannot
        # authorize further cleanup: drain, then retain its stages/recovery
        # debt rather than claiming Bash rollback completed.
        if process is not None:
            if worker_fd is not None and not _terminal(worker_fd) \
                    and _freeze(process, worker_fd):
                _drain(process)
                _send_signal(worker_fd, signal.SIGKILL)
                _send_signal(worker_fd, signal.SIGCONT)
            _drain()
            if process.returncode is None:
                process.returncode = 1
        requests.close()
        for descriptor in leases.values():
            _close(descriptor)
        if signals is not None:
            if signals.first is not None:
                result = 128 + signals.first
            signals.close()
        if child_channel is not None:
            child_channel.close()
        if parent_channel is not None:
            parent_channel.close()
        for descriptor in (worker_fd, parent_fd, script_fd, source_fd,
                           helper_snapshot_fd, bin_fd, root_fd):
            _close(descriptor)
    return result


def run_command(arguments, *, deadline, capture=False, pass_stdin=False,
                caller=None, label=None):
    if deadline not in ALLOWED_DEADLINES or not arguments:
        raise LifetimeRefusal("unsupported command deadline or empty command")
    if label is not None and (
            not isinstance(label, str) or not label
            or len(label) > MAX_COMMAND_LABEL_CHARS
            or COMMAND_LABEL.fullmatch(label) is None):
        raise LifetimeRefusal("bounded command label is invalid")
    signals = process = None
    leader_fd = parent_fd = None
    output = bytearray()
    refusal = None
    returncode = None
    try:
        parent_fd = _pin_caller(caller)
        _features()
        signals = _Signals()
        _require_caller(parent_fd)
        try:
            process = subprocess.Popen(
                arguments, start_new_session=True, close_fds=True,
                stdin=(None if pass_stdin or not capture else subprocess.DEVNULL),
                stdout=(subprocess.PIPE if capture else None),
                stderr=(subprocess.STDOUT if capture else None))
        except OSError as error:
            print(f"could not execute bounded command: {error}", file=sys.stderr)
            return 127
        leader_fd = os.pidfd_open(process.pid, 0)
        end = time.monotonic() + deadline
        with selectors.DefaultSelector() as selector:
            selector.register(leader_fd, selectors.EVENT_READ, "leader")
            selector.register(parent_fd, selectors.EVENT_READ, "parent")
            selector.register(signals.read_fd, selectors.EVENT_READ, "signal")
            if capture:
                os.set_blocking(process.stdout.fileno(), False)
                selector.register(process.stdout, selectors.EVENT_READ, "output")
            while returncode is None:
                remaining = end - time.monotonic()
                if remaining <= 0:
                    returncode = 124
                    subject = label if label is not None else "external command"
                    refusal = (
                        f"{subject} exceeded its {deadline}-second "
                        "runtime deadline")
                    break
                for key, _events in selector.select(remaining):
                    if key.data == "leader":
                        info = _exit_info(process)
                        if returncode is None:
                            returncode = _result(info)
                    elif key.data == "parent":
                        returncode = 143
                    elif key.data == "signal":
                        signals.consume()
                        returncode = 128 + signals.first
                    elif key.data == "output":
                        try:
                            block = os.read(process.stdout.fileno(), MAX_CAPTURE_BYTES + 1 - len(output))
                        except BlockingIOError:
                            continue
                        if not block:
                            selector.unregister(process.stdout)
                        else:
                            output.extend(block)
                        if len(output) > MAX_CAPTURE_BYTES:
                            returncode = 125
                            refusal = "external inspector exceeded its output byte ceiling"
                if signals.first is not None:
                    returncode = 128 + signals.first
        statuses = _drain()
        process.returncode = os.waitstatus_to_exitcode(statuses[process.pid])
        if capture and len(output) <= MAX_CAPTURE_BYTES:
            while True:
                try:
                    block = os.read(process.stdout.fileno(), MAX_CAPTURE_BYTES + 1 - len(output))
                except BlockingIOError:
                    break
                if not block:
                    break
                output.extend(block)
                if len(output) > MAX_CAPTURE_BYTES:
                    returncode = 125
                    refusal = "external inspector exceeded its output byte ceiling"
                    break
        if refusal is not None:
            print(refusal, file=sys.stderr)
        elif capture:
            if b"\0" in output:
                print("external inspector emitted NUL", file=sys.stderr)
                return 125
            try:
                text = output.decode("utf-8", "strict")
            except UnicodeError as error:
                print("external inspector emitted non-UTF-8 output", file=sys.stderr)
                return 125
            sys.stdout.write(text)
    finally:
        if process is not None and process.returncode is None:
            statuses = _drain()
            if process.pid in statuses:
                process.returncode = os.waitstatus_to_exitcode(statuses[process.pid])
        if process is not None and process.stdout is not None:
            process.stdout.close()
        if signals is not None:
            if signals.first is not None:
                returncode = 128 + signals.first
            signals.close()
        _close(leader_fd)
        _close(parent_fd)
    return returncode


def main(arguments=None):
    values = list(sys.argv[1:] if arguments is None else arguments)
    try:
        caller = None
        if values[1:2] == ["--caller"]:
            if len(values) < 3:
                raise LifetimeRefusal("incomplete caller admission")
            caller = int(values[2], 10)
            values[1:3] = []
        if values[:1] == ["supervise"] and len(values) >= 2:
            return supervise(values[1], values[2:], caller=caller)
        if values[:1] == ["supervise-installed"] and len(values) >= 2:
            return supervise(
                values[1], values[2:], caller=caller, flat_source=True)
        if values[:1] == ["setup"] and len(values) >= 3:
            handoff = _setup_handoff(values[2])
            return supervise(
                values[2], values[3:], setup_lease=int(values[1], 10),
                caller=caller, setup_handoff=handoff)
        if values[:1] == ["admit"] and len(values) == 6:
            admit(*(int(value, 10) for value in values[1:]))
            return 0
        if values[:1] == ["register"] and len(values) == 4:
            lease(int(values[1], 10), "register", values[2], int(values[3], 10))
            return 0
        if values[:1] == ["release"] and len(values) == 3:
            lease(int(values[1], 10), "release", values[2])
            return 0
        if values[:1] == ["run"] and len(values) >= 3:
            commands = values[2:]
            label = None
            if commands[:1] == ["--label"]:
                if len(commands) < 3:
                    raise LifetimeRefusal("incomplete bounded command label")
                label = commands[1]
                commands = commands[2:]
            return run_command(
                commands, deadline=int(values[1], 10), caller=caller,
                label=label)
        if values[:1] == ["capture"]:
            commands = values[1:]
            pass_stdin = commands[:1] == ["--stdin"]
            if pass_stdin:
                commands = commands[1:]
            return run_command(commands, deadline=CAPTURE_DEADLINE,
                               capture=True, pass_stdin=pass_stdin, caller=caller)
        raise LifetimeRefusal("invalid release lifetime operation")
    except (OSError, ValueError, LifetimeRefusal) as error:
        print(f"SIA release lifetime refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
