#!/usr/bin/env python3
"""Real-process release lifetime regressions; never run a live installation.

The fixture lifts the actual entry bootstrap, command runners, owner-lock
acquisition and EXIT cleanup from each release script.  Only the installation
body is replaced with a temporary actor.  Before the lifetime bootstrap exists,
the same fixture runs the current direct Bash entry: the process regressions
therefore expose surviving mutators, not just a missing future module.

The shared release-only owner's proposed CLI is ``supervise ENTRY [ARG ...]``.
The shell bootstrap is delimited by the exact comments below so lifting it
cannot accidentally execute the real install/uninstall body.  No lifetime
behavior is copied into these fixtures.
"""

import contextlib
import fcntl
import json
import os
from pathlib import Path
import selectors
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest


REPO = Path(__file__).resolve().parents[1]
OWNER = REPO / "bin" / "sialifetime.py"
BOOTSTRAP_START = "# BEGIN SIA RELEASE LIFETIME\n"
BOOTSTRAP_END = "# END SIA RELEASE LIFETIME\n"


def _function(source, name):
    marker = name + "() {"
    if source.count(marker) != 1:
        raise AssertionError(f"expected one production {name} function")
    return marker + source.split(marker, 1)[1].split("\n}\n", 1)[0] + "\n}\n"


def _bootstrap(source):
    if BOOTSTRAP_START not in source and BOOTSTRAP_END not in source:
        # Baseline semantic RED: execute today's unsupervised real functions.
        return ""
    if source.count(BOOTSTRAP_START) != 1 or source.count(BOOTSTRAP_END) != 1:
        raise AssertionError("release lifetime bootstrap is ambiguous")
    return source.split(BOOTSTRAP_START, 1)[1].split(BOOTSTRAP_END, 1)[0]


ACTOR_SOURCE = r'''
import json
import os
from pathlib import Path
import socket
import sys


def connect(role, **fields):
    channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    channel.connect(os.environ["SIA_TEST_CONTROL"])
    channel.sendall((json.dumps({"role": role, "pid": os.getpid(),
                                "parent": os.getppid(), **fields}) + "\n").encode())
    return channel


def instruction(channel):
    value = bytearray()
    while not value.endswith(b"\n"):
        chunk = channel.recv(1)
        if not chunk:
            os._exit(0)
        value.extend(chunk)
    return value.decode().strip()


if sys.argv[1] == "fdcheck":
    try:
        info = os.fstat(int(os.environ["SIA_TEST_EXTRA_FD"]))
        leaked = [info.st_dev, info.st_ino] == json.loads(
            os.environ["SIA_TEST_EXTRA_IDENTITY"])
    except OSError:
        leaked = False
    channel = connect("fdcheck", extra_fd_open=leaked)
    instruction(channel)
    channel.close()
    raise SystemExit(0)

if sys.argv[1] in {"cleanup", "returned"}:
    channel = connect(sys.argv[1])
    if instruction(channel) == "continue":
        if sys.argv[1] == "cleanup":
            Path(os.environ["SIA_TEST_CLEANUP_FINISHED"]).write_text("finished")
    channel.close()
    raise SystemExit(0)

if sys.argv[1] == "tree":
    child = os.fork()
    if child == 0:
        os.setsid()
        for descriptor in (0, 1, 2):
            try:
                os.close(descriptor)
            except OSError:
                pass
        channel = connect("detached")
        while True:
            command = instruction(channel)
            if command == "mutate":
                Path(os.environ["SIA_TEST_MUTATION"]).write_text("late mutation")
                os._exit(0)
            if command == "fork":
                grandchild = os.fork()
                if grandchild == 0:
                    channel.close()
                    os.setsid()
                    channel = connect("grandchild")
                continue
            if command == "exit":
                os._exit(0)
    channel = connect("leader")
    command = instruction(channel)
    channel.close()
    os._exit(7 if command == "error" else 0)
raise SystemExit("unknown test actor mode")
'''


class _Actor:
    def __init__(self, connection, record):
        self.connection = connection
        self.record = record
        self.pidfd = os.pidfd_open(record["pid"], 0)

    def send(self, command):
        self.connection.sendall((command + "\n").encode("ascii"))

    def exited(self):
        with selectors.DefaultSelector() as selector:
            selector.register(self.pidfd, selectors.EVENT_READ)
            return bool(selector.select(0))

    def wait_exit(self):
        with selectors.DefaultSelector() as selector:
            selector.register(self.pidfd, selectors.EVENT_READ)
            if not selector.select(10):
                raise AssertionError(f"actor stayed live: {self.record}")

    def close(self):
        try:
            if not self.exited():
                signal.pidfd_send_signal(self.pidfd, signal.SIGKILL)
                self.wait_exit()
        finally:
            self.connection.close()
            os.close(self.pidfd)


class _ReleaseRig:
    def __init__(self, testcase, entry, runner="deadline", ambient=None):
        self.testcase = testcase
        self.temporary = tempfile.TemporaryDirectory(prefix="sia-lifetime-test-")
        testcase.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.actors = {}
        self.closed = False
        self.process = None
        self.root_pidfd = None
        self.worker_pidfd = None
        self.runner_pidfd = None
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        testcase.addCleanup(self.listener.close)
        self.listener.bind(str(self.root / "control.sock"))
        self.listener.listen()
        self.listener.settimeout(10)
        self.stdout = open(self.root / "stdout", "w+b")
        self.stderr = open(self.root / "stderr", "w+b")
        (self.root / "home").mkdir()
        (self.root / "runtime").mkdir()
        (self.root / "stage").mkdir()
        (self.root / "stage" / "owned-file").write_text("stage data")
        (self.root / "bin").mkdir()
        for name in ("sialifetime.py", "siarelease.py"):
            source = REPO / "bin" / name
            if source.exists():
                shutil.copy2(source, self.root / "bin" / name)
        if runner == "timeout":
            helper = self.root / "bin" / "sialifetime.py"
            source = helper.read_text()
            shortened = source.replace("ALLOWED_DEADLINES = {120, 300, 1800}",
                                       "ALLOWED_DEADLINES = {1}")
            testcase.assertNotEqual(source, shortened)
            helper.write_text(shortened)
        self.actor_path = self.root / "actor.py"
        self.actor_path.write_text(ACTOR_SOURCE, encoding="utf-8")
        self.lock_path = self.root / "owner.lock"
        self.entry = self.root / entry
        self._write_entry(entry, runner)
        self.environment = os.environ.copy()
        self.environment.update({
            "HOME": str(self.root / "home"),
            "XDG_RUNTIME_DIR": str(self.root / "runtime"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "SIA_TEST_CONTROL": str(self.root / "control.sock"),
            "SIA_TEST_ROOT": str(self.root),
            "SIA_TEST_ACTOR": str(self.actor_path),
            "SIA_TEST_PYTHON": sys.executable,
            "SIA_TEST_CLEANUP_FINISHED": str(self.root / "cleanup-finished"),
            "SIA_TEST_MUTATION": str(self.root / "mutation"),
        })
        if ambient:
            self.environment.update(ambient)

    def _write_entry(self, entry, runner):
        source = (REPO / entry).read_text(encoding="utf-8")
        cleanup_name = ("sia_install_cleanup" if entry == "install.sh"
                        else "sia_uninstall_cleanup")
        functions = "".join(_function(source, name) for name in (
            "bounded_command_capture", "run_with_deadline",
            "acquire_owner_lock", cleanup_name))
        # Every optional rollback flag is false: cleanup may only touch this
        # fixture's stage and lease. The real acquire/cleanup bodies remain
        # unchanged, including their future lifetime registration/barriers.
        settings = r'''
SIA_INSTALL_TMP="$SIA_TEST_ROOT/stage"
SIA_INSTALL_LOCK_FD=""
SIA_INSTALL_ADMIN_LOCK_FD=""
SIA_UNINSTALL_LOCK_FD=""
SIA_UNINSTALL_ADMIN_LOCK_FD=""
SIA_GBRAIN_LOCK_FD=""
SIA_CORPUS_LOCK_FD=""
SIA_BRAINSTEM_LOCK_FD=""
SIA_OLLAMA_STAGE=""
SIA_PLUGIN_STAGE=""
SIA_RUNTIME_STAGE=""
SIA_BUN_STAGE=""
SIA_RESTIC_STAGE=""
SIA_GBRAIN_STAGE=""
SIA_RESTORE_LIFECYCLE_TOMBSTONE=0
SIA_LIFECYCLE_TOMBSTONE_CLEARED=0
SIA_LAUNCH_FENCE_ARMED=0
SIA_OLLAMA_SERVICE_MUTATED=0
SIA_INSTALL_MUTATED=0
SIA_BRAINSTEM_FINAL_UNBARRIERED=0
SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED=0
SIA_BRAINSTEM_RETIRED_BARRIER_PRESENT=0
SIA_KEEP_BRAINSTEM_RUNTIME_BARRIER=0
SIA_BRAINSTEM_ENABLE_STATE=disabled
SIA_BRAINSTEM_WAS_ACTIVE=0
SIA_LIFECYCLE_ACQUIRE_ATTEMPTS=1
failed() { printf '%s\n' "$*" >&2; return 1; }
quiesce_install_brainstem_for_lifecycle() { return 1; }
observe_cleanup() {
  if [ ! -e "$SIA_TEST_ROOT/cleanup-observed" ]; then
    printf observed > "$SIA_TEST_ROOT/cleanup-observed"
    "$SIA_TEST_PYTHON" "$SIA_TEST_ACTOR" cleanup
  fi
}
chmod() {
  if [ "${1:-}" = -R ]; then observe_cleanup; fi
  command chmod "$@"
}
flock() {
  if [ "${1:-}" = -u ]; then observe_cleanup; fi
  command flock "$@"
}
'''
        if runner == "capture":
            invocation = ('captured="$(bounded_command_capture '
                          '"$SIA_TEST_PYTHON" "$SIA_TEST_ACTOR" tree)"\n')
        elif runner == "direct":
            invocation = '"$SIA_TEST_PYTHON" "$SIA_TEST_ACTOR" tree\n'
        else:
            deadline = "1" if runner == "timeout" else "120"
            invocation = ('run_with_deadline ' + deadline + ' "$SIA_TEST_PYTHON" '
                          '"$SIA_TEST_ACTOR" tree\n')
        body = ("#!/usr/bin/env bash\nset -euo pipefail\n"
                + _bootstrap(source) + "\n" + functions + settings
                + f"trap {cleanup_name} EXIT\n"
                + 'acquire_owner_lock "$SIA_TEST_ROOT/owner.lock" '
                  'SIA_BRAINSTEM_LOCK_FD fixture\n'
                + 'printf "%s\\n" "$BASHPID" > "$SIA_TEST_ROOT/worker-pid"\n'
                + 'if [ "${SIA_TEST_PARTIAL_CONTROL:-0}" = 1 ]; then\n'
                  '  printf "QUIESCE " >&"$SIA_LIFETIME_CONTROL_FD"\nfi\n'
                + 'if [ -n "${SIA_TEST_EXTRA_FD:-}" ]; then\n'
                  '  "$SIA_TEST_PYTHON" "$SIA_TEST_ACTOR" fdcheck\nfi\n'
                + invocation
                + 'printf returned > "$SIA_TEST_ROOT/command-returned"\n'
                + 'if [ "${SIA_TEST_OBSERVE_RETURN:-0}" = 1 ]; then\n'
                  '  "$SIA_TEST_PYTHON" "$SIA_TEST_ACTOR" returned\nfi\n')
        self.entry.write_text(body, encoding="utf-8")
        self.entry.chmod(0o700)

    def start(self, *, pass_fds=(), setup_caller=False):
        command = [str(self.entry)]
        if setup_caller:
            launcher = textwrap.dedent(r'''
                import fcntl
                import json
                import os
                import socket
                import subprocess
                import sys
                descriptor = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                child = subprocess.Popen(
                    [sys.executable, sys.argv[2], "setup", "--caller", str(os.getpid()),
                     str(descriptor), sys.argv[3]], pass_fds=(descriptor,))
                channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                channel.connect(os.environ["SIA_TEST_CONTROL"])
                channel.sendall((json.dumps({"role": "owner", "pid": child.pid}) + "\n").encode())
                result = child.wait()
                channel.close()
                os.close(descriptor)
                raise SystemExit(result)
            ''')
            command = [sys.executable, "-c", launcher, str(self.root / "setup.lock"),
                       str(self.root / "bin" / "sialifetime.py"), str(self.entry)]
        self.process = subprocess.Popen(
            command, cwd=self.root, env=self.environment,
            stdin=subprocess.DEVNULL, stdout=self.stdout, stderr=self.stderr,
            pass_fds=pass_fds)
        if setup_caller:
            self.accept("owner")
            self.root_pidfd = os.dup(self.actors["owner"].pidfd)
        else:
            self.root_pidfd = os.pidfd_open(self.process.pid, 0)
        if "SIA_TEST_EXTRA_FD" in self.environment:
            self.accept("fdcheck")
            self.actors["fdcheck"].send("continue")
        self.accept("leader", "detached")
        self.runner_pidfd = os.pidfd_open(self.actors["leader"].record["parent"], 0)
        worker_pid = int((self.root / "worker-pid").read_text().strip())
        self.worker_pidfd = os.pidfd_open(worker_pid, 0)
        self.testcase.assertFalse(self.lock_available(), "fixture lease not held")
        return self

    def accept(self, *roles):
        while not set(roles).issubset(self.actors):
            connection, _ = self.listener.accept()
            connection.settimeout(10)
            raw = bytearray()
            while not raw.endswith(b"\n"):
                block = connection.recv(1)
                if not block or len(raw) > 4096:
                    connection.close()
                    raise AssertionError("invalid fixture actor admission")
                raw.extend(block)
            record = json.loads(raw)
            self.testcase.assertNotIn(record["role"], self.actors)
            self.actors[record["role"]] = _Actor(connection, record)

    def lock_available(self, path=None):
        descriptor = os.open(self.lock_path if path is None else path,
                             os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            return True
        finally:
            os.close(descriptor)

    def finish_cleanup(self):
        self.accept("cleanup")
        self.actors["cleanup"].send("continue")
        return self.process.wait(timeout=30)

    def close(self):
        if self.closed:
            return
        self.closed = True
        # These are exclusively fixture-created identities pinned with
        # pidfds. Never discover/kill a process by a stale textual PID.
        if self.root_pidfd is not None:
            with contextlib.suppress(ProcessLookupError):
                signal.pidfd_send_signal(self.root_pidfd, signal.SIGCONT)
        for actor in reversed(tuple(self.actors.values())):
            actor.close()
        self.listener.close()
        for descriptor in (self.runner_pidfd, self.worker_pidfd):
            if descriptor is not None:
                with contextlib.suppress(ProcessLookupError):
                    signal.pidfd_send_signal(descriptor, signal.SIGKILL)
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=30)
        for descriptor in (self.runner_pidfd, self.worker_pidfd, self.root_pidfd):
            if descriptor is not None:
                os.close(descriptor)
        self.stdout.close()
        self.stderr.close()
        self.temporary.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *_exception):
        self.close()


class LifecycleProcessOwnershipTests(unittest.TestCase):
    def test_release_source_admission_rejects_group_and_world_writes(self):
        cases = (
            ("source-root-group", "root", stat.S_IWGRP,
             "release source root is not an owner-controlled directory"),
            ("source-root-world", "root", stat.S_IWOTH,
             "release source root is not an owner-controlled directory"),
            ("source-file-group", "helper", stat.S_IWGRP,
             "sia-lifetime-source source is not bounded and owner-controlled"),
            ("source-file-world", "helper", stat.S_IWOTH,
             "sia-lifetime-source source is not bounded and owner-controlled"),
        )
        for case, target_name, writable, expected in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                    prefix="sia-lifetime-source-mode-") as temporary:
                parent = Path(temporary)
                release = parent / "release"
                binary = release / "bin"
                release.mkdir()
                binary.mkdir()
                release.chmod(0o700)
                binary.chmod(0o700)

                helper = binary / "sialifetime.py"
                shutil.copy2(OWNER, helper)
                helper.chmod(0o600)

                marker = parent / "launched"
                entry = release / "install.sh"
                entry.write_text(
                    "#!/usr/bin/env bash\nprintf launched > "
                    + shlex.quote(str(marker)) + "\n",
                    encoding="utf-8")
                entry.chmod(0o700)

                target = release if target_name == "root" else helper
                target.chmod(
                    stat.S_IMODE(target.stat().st_mode) | writable)

                result = subprocess.run(
                    [sys.executable, str(OWNER), "supervise", str(entry)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30,
                    check=False,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})

                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(expected, result.stderr)
                self.assertFalse(
                    marker.exists(),
                    "unsafe release source reached the worker body")

    def _admission_or_drain_probe(self, operation, boundary, *, lose_caller=False):
        probe = textwrap.dedent(r'''
            import json
            import os
            from pathlib import Path
            import runpy
            import socket
            import sys

            helper, entry, operation, boundary, address, result_path = sys.argv[1:]
            namespace = runpy.run_path(helper)
            target = namespace[operation]
            globals_ = target.__globals__
            original = globals_[boundary]
            channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            parked = False
            def gate(*args, **kwargs):
                global parked
                if not parked:
                    parked = True
                    channel.connect(address)
                    channel.sendall((json.dumps({"role": "probe", "pid": os.getpid()}) + "\n").encode())
                    message = bytearray()
                    while not message.endswith(b"\n"):
                        message.extend(channel.recv(1))
                return original(*args, **kwargs)
            globals_[boundary] = gate
            try:
                if operation == "supervise":
                    result = target(entry, [])
                else:
                    result = target([sys.executable, "-c", "pass"], deadline=120)
            except Exception as error:
                result = {"refused": str(error)}
            Path(result_path).write_text(json.dumps(result))
            channel.close()
        ''')
        launcher = "import subprocess,sys; raise SystemExit(subprocess.call(sys.argv[1:]))"
        with tempfile.TemporaryDirectory(prefix="sia-lifetime-boundary-") as root:
            root = Path(root)
            (root / "bin").mkdir()
            shutil.copy2(OWNER, root / "bin" / "sialifetime.py")
            entry = root / "install.sh"
            entry.write_text("#!/usr/bin/env bash\nprintf launched > "
                             + shlex.quote(str(root / "launched")) + "\n")
            entry.chmod(0o700)
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(root / "control"))
            listener.listen()
            listener.settimeout(10)
            actor = None
            process = subprocess.Popen(
                [sys.executable, "-c", launcher, sys.executable, "-c", probe,
                 str(OWNER), str(entry), operation, boundary,
                 str(root / "control"), str(root / "result")],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            try:
                channel, _ = listener.accept()
                channel.settimeout(10)
                record = bytearray()
                while not record.endswith(b"\n"):
                    record.extend(channel.recv(1))
                actor = _Actor(channel, json.loads(record))
                if lose_caller:
                    process.kill()
                    process.wait(timeout=10)
                else:
                    signal.pidfd_send_signal(actor.pidfd, signal.SIGTERM)
                actor.send("continue")
                actor.wait_exit()
                if process.poll() is None:
                    process.wait(timeout=10)
                return json.loads((root / "result").read_text()), (root / "launched").exists()
            finally:
                if actor is not None:
                    actor.close()
                listener.close()
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)

    def test_caller_death_during_features_cannot_launch_a_release_worker(self):
        result, launched = self._admission_or_drain_probe(
            "supervise", "_features", lose_caller=True)
        self.assertFalse(launched, "release work launched after original caller death")
        self.assertIsInstance(result, dict)
        self.assertIn("caller", result["refused"])

    def test_final_drain_signal_is_part_of_the_returned_outcome(self):
        for operation in ("supervise", "run_command"):
            with self.subTest(operation=operation):
                result, _ = self._admission_or_drain_probe(operation, "_drain")
                self.assertEqual(result, 143,
                                 "first signal during final drainage was reported as success")

    def rig(self, entry, runner="deadline", ambient=None):
        rig = _ReleaseRig(self, entry, runner, ambient)
        self.addCleanup(rig.close)
        return rig

    def assert_old_mutators_gone_at_cleanup(self, rig):
        rig.accept("cleanup")
        self.assertTrue(rig.actors["detached"].exited(),
                        "detached mutator reached the real cleanup boundary")
        self.assertFalse(rig.lock_available(),
                         "lease released before cleanup drainage was observed")

    def test_direct_entries_stop_mutators_before_cleanup_on_signal(self):
        for entry in ("install.sh", "uninstall.sh"):
            for runner in ("deadline", "capture"):
                with self.subTest(entry=entry, runner=runner), \
                        self.rig(entry, runner) as rig:
                    rig.start()
                    rig.process.send_signal(signal.SIGTERM)
                    self.assert_old_mutators_gone_at_cleanup(rig)
                    self.assertEqual(rig.finish_cleanup(), 143)
                    self.assertTrue(rig.lock_available())

    def test_direct_worker_children_are_drained_before_exit_cleanup(self):
        for entry in ("install.sh", "uninstall.sh"):
            with self.subTest(entry=entry), self.rig(entry, runner="direct") as rig:
                rig.start()
                rig.process.send_signal(signal.SIGTERM)
                with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                    rig.actors["leader"].send("exit")
                self.assert_old_mutators_gone_at_cleanup(rig)
                self.assertEqual(rig.finish_cleanup(), 143)

    def test_partial_control_frame_cannot_block_cancellation_or_authorize_cleanup(self):
        with self.rig("install.sh") as rig:
            rig.environment["SIA_TEST_PARTIAL_CONTROL"] = "1"
            rig.start()
            rig.process.send_signal(signal.SIGTERM)
            self.assertEqual(rig.process.wait(timeout=10), 2)
            self.assertTrue(rig.actors["detached"].exited())
            self.assertTrue((rig.root / "stage" / "owned-file").exists(),
                            "invalid control protocol authorized stage cleanup")
            self.assertFalse((rig.root / "cleanup-observed").exists())
            self.assertTrue(rig.lock_available())

    def test_normal_leader_exit_drains_detached_descendants(self):
        for entry in ("install.sh", "uninstall.sh"):
            for runner in ("deadline", "capture"):
                with self.subTest(entry=entry, runner=runner), \
                        self.rig(entry, runner) as rig:
                    rig.start()
                    rig.actors["detached"].send("fork")
                    rig.accept("grandchild")
                    rig.actors["leader"].send("exit")
                    self.assert_old_mutators_gone_at_cleanup(rig)
                    self.assertTrue(rig.actors["grandchild"].exited(),
                                    "nested detached descendant survived")
                    self.assertEqual(rig.finish_cleanup(), 0)
                    self.assertTrue((rig.root / "command-returned").exists())

    def test_command_return_itself_waits_for_detached_descendants(self):
        for runner in ("deadline", "capture"):
            with self.subTest(runner=runner), self.rig("install.sh", runner) as rig:
                rig.environment["SIA_TEST_OBSERVE_RETURN"] = "1"
                rig.start()
                rig.actors["leader"].send("exit")
                rig.accept("returned")
                self.assertTrue(rig.actors["detached"].exited(),
                                "command returned before its detached mutator exited")
                rig.actors["returned"].send("continue")
                self.assertEqual(rig.finish_cleanup(), 0)

    def test_nonzero_leader_exit_uses_the_same_drainage_boundary(self):
        for entry in ("install.sh", "uninstall.sh"):
            with self.subTest(entry=entry), self.rig(entry) as rig:
                rig.start()
                rig.actors["leader"].send("error")
                self.assert_old_mutators_gone_at_cleanup(rig)
                self.assertEqual(rig.finish_cleanup(), 7)
                self.assertFalse((rig.root / "command-returned").exists())

    def test_timeout_drains_detached_descendants_before_cleanup(self):
        for entry in ("install.sh", "uninstall.sh"):
            with self.subTest(entry=entry), self.rig(entry, runner="timeout") as rig:
                rig.start()
                self.assert_old_mutators_gone_at_cleanup(rig)
                self.assertEqual(rig.finish_cleanup(), 124)
                self.assertFalse((rig.root / "command-returned").exists())

    def test_setup_caller_death_retains_transferred_lease_through_drainage(self):
        with self.rig("install.sh") as rig:
            rig.start(setup_caller=True)
            signal.pidfd_send_signal(rig.root_pidfd, signal.SIGSTOP)
            # The owner is a grandchild; its caller cannot consume WSTOPPED
            # for us. pidfd-directed stop plus the kernel status is the
            # stopped-state observation, not a delay-based assumption.
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                status = Path(f"/proc/{rig.actors['owner'].record['pid']}/status").read_text()
                if "State:\tT" in status:
                    break
                time.sleep(0.01)
            else:
                self.fail("lifetime owner did not enter stopped state")
            rig.process.kill()
            rig.process.wait(timeout=10)
            self.assertFalse(rig.lock_available(rig.root / "setup.lock"),
                             "caller death released the transferred setup lease")
            signal.pidfd_send_signal(rig.root_pidfd, signal.SIGCONT)
            self.assert_old_mutators_gone_at_cleanup(rig)
            rig.actors["cleanup"].send("continue")
            rig.actors["owner"].wait_exit()
            self.assertTrue(rig.lock_available(rig.root / "setup.lock"))

    def test_repeated_signals_do_not_skip_cleanup_or_release_the_lease(self):
        for entry in ("install.sh", "uninstall.sh"):
            with self.subTest(entry=entry), self.rig(entry) as rig:
                rig.start()
                rig.process.send_signal(signal.SIGTERM)
                rig.accept("cleanup")
                rig.process.send_signal(signal.SIGTERM)
                rig.process.send_signal(signal.SIGHUP)
                # Cleanup is deliberately parked at an actual deletion or
                # unlock, not delayed by a timing guess in the test process.
                self.assertFalse(rig.lock_available())
                self.assertEqual(rig.finish_cleanup(), 143)
                self.assertTrue((rig.root / "cleanup-finished").exists())
                self.assertTrue(rig.actors["detached"].exited())

    def test_signal_during_normal_cleanup_cannot_report_success(self):
        for entry in ("install.sh", "uninstall.sh"):
            with self.subTest(entry=entry), self.rig(entry) as rig:
                rig.start()
                rig.actors["leader"].send("exit")
                self.assert_old_mutators_gone_at_cleanup(rig)
                rig.process.send_signal(signal.SIGTERM)
                self.assertEqual(rig.finish_cleanup(), 143)
                self.assertTrue((rig.root / "cleanup-finished").exists())

    def test_release_source_retirement_does_not_replace_owned_cleanup_code(self):
        for entry in ("install.sh", "uninstall.sh"):
            with self.subTest(entry=entry), self.rig(entry) as rig:
                rig.start()
                rig.entry.write_text("#!/usr/bin/env bash\nexit 99\n")
                (rig.root / "bin" / "sialifetime.py").write_text("raise SystemExit(99)\n")
                rig.actors["leader"].send("exit")
                self.assert_old_mutators_gone_at_cleanup(rig)
                self.assertEqual(rig.finish_cleanup(), 0)
                self.assertTrue((rig.root / "command-returned").exists())

    def test_admitted_worker_keeps_original_release_root_after_path_rebind(self):
        synchronizer = textwrap.dedent(r'''
            import socket
            import sys

            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
                channel.connect(sys.argv[1])
                channel.sendall(b"ADMITTED\n")
                if channel.recv(1) != b"G":
                    raise SystemExit("release-root test gate closed unexpectedly")
        ''')
        cases = (("install.sh", False), ("uninstall.sh", False),
                 ("install.sh", True))
        for entry_name, setup_caller in cases:
            with self.subTest(entry=entry_name, setup=setup_caller), \
                    tempfile.TemporaryDirectory(
                        prefix="sia-lifetime-root-generation-") as parent:
                parent = Path(parent)
                source = parent / "release"
                retired = parent / "retired-release"
                outside = parent / "outside"
                source.mkdir()
                outside.mkdir()
                (source / "bin").mkdir()
                shutil.copy2(OWNER, source / "bin" / "sialifetime.py")
                (source / "sentinel").write_text("original\n", encoding="utf-8")
                control_path = outside / "control.sock"
                result_path = outside / "observed"
                listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.addCleanup(listener.close)
                listener.bind(str(control_path))
                listener.listen()
                listener.settimeout(10)
                source_text = (REPO / entry_name).read_text(encoding="utf-8")
                entry = source / entry_name
                entry.write_text(
                    "#!/usr/bin/env bash\nset -euo pipefail\n"
                    + _bootstrap(source_text)
                    + "\n"
                    + shlex.quote(sys.executable) + " -c "
                    + shlex.quote(synchronizer) + " "
                    + shlex.quote(str(control_path)) + "\n"
                    + 'IFS= read -r observed < '
                      '"$SIA_LIFETIME_SOURCE_ROOT/sentinel"\n'
                    + 'printf "%s\\n" "$observed" > '
                    + shlex.quote(str(result_path)) + "\n",
                    encoding="utf-8")
                entry.chmod(0o700)
                setup_fd = None
                process = None
                channel = None
                try:
                    if setup_caller:
                        setup_fd = os.open(
                            outside / "setup.lock", os.O_RDWR | os.O_CREAT,
                            0o600)
                        fcntl.flock(setup_fd, fcntl.LOCK_EX)
                        command = [
                            sys.executable,
                            str(source / "bin" / "sialifetime.py"),
                            "setup", "--caller", str(os.getpid()),
                            str(setup_fd), str(entry),
                        ]
                        process = subprocess.Popen(
                            command, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, pass_fds=(setup_fd,),
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                    else:
                        process = subprocess.Popen(
                            [str(entry)], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                    channel, _ = listener.accept()
                    self.assertEqual(channel.recv(64), b"ADMITTED\n")
                    source.rename(retired)
                    source.mkdir()
                    (source / "sentinel").write_text(
                        "replacement\n", encoding="utf-8")
                    channel.sendall(b"G")
                    stdout, stderr = process.communicate(timeout=30)
                    self.assertEqual(process.returncode, 0, stdout + stderr)
                    self.assertEqual(result_path.read_text(encoding="utf-8"),
                                     "original\n")
                finally:
                    if channel is not None:
                        channel.close()
                    listener.close()
                    if process is not None and process.poll() is None:
                        process.kill()
                        process.wait(timeout=10)
                    if process is not None:
                        if process.stdout is not None:
                            process.stdout.close()
                        if process.stderr is not None:
                            process.stderr.close()
                    if setup_fd is not None:
                        os.close(setup_fd)

    def test_worker_death_cannot_release_lease_before_supervisor_drains(self):
        for entry in ("install.sh", "uninstall.sh"):
            with self.subTest(entry=entry), self.rig(entry) as rig:
                rig.start()
                signal.pidfd_send_signal(rig.root_pidfd, signal.SIGSTOP)
                stopped = os.waitid(os.P_PID, rig.process.pid,
                                    os.WSTOPPED | os.WNOWAIT)
                self.assertEqual(stopped.si_code, os.CLD_STOPPED)
                signal.pidfd_send_signal(rig.worker_pidfd, signal.SIGKILL)
                with selectors.DefaultSelector() as watcher:
                    watcher.register(rig.worker_pidfd, selectors.EVENT_READ)
                    self.assertTrue(watcher.select(10), "worker did not exit")
                with selectors.DefaultSelector() as watcher:
                    watcher.register(rig.runner_pidfd, selectors.EVENT_READ)
                    self.assertTrue(watcher.select(10), "orphaned command owner did not exit")
                # The supervisor is stopped. A passing lock check therefore
                # proves retained ownership, not fast reaction to SIGCHLD.
                self.assertFalse(rig.lock_available(),
                                 "worker death released the active lease")
                signal.pidfd_send_signal(rig.root_pidfd, signal.SIGCONT)
                self.assertNotEqual(rig.process.wait(timeout=30), 0)
                rig.actors["detached"].wait_exit()
                self.assertTrue(rig.lock_available())

    def test_ambient_owned_flags_do_not_bypass_direct_entry_supervision(self):
        ambient = {
            "SIA_LIFETIME_OWNED": "1",
            "SIA_LIFETIME_CHILD": "1",
            "SIA_LIFETIME_CONTROL_FD": "999",
            "SIA_LIFETIME_SOURCE_FD": "998",
        }
        for entry in ("install.sh", "uninstall.sh"):
            with self.subTest(entry=entry), self.rig(entry, ambient=ambient) as rig:
                rig.start()
                rig.process.send_signal(signal.SIGTERM)
                self.assert_old_mutators_gone_at_cleanup(rig)
                self.assertEqual(rig.finish_cleanup(), 143)

    def test_unrelated_inherited_descriptor_is_closed_before_worker_body(self):
        for entry in ("install.sh", "uninstall.sh"):
            with self.subTest(entry=entry), self.rig(entry) as rig:
                sentinel = os.open(rig.root / "unrelated-fd", os.O_CREAT | os.O_RDWR, 0o600)
                try:
                    info = os.fstat(sentinel)
                    rig.environment.update({
                        "SIA_TEST_EXTRA_FD": str(sentinel),
                        "SIA_TEST_EXTRA_IDENTITY": json.dumps([info.st_dev, info.st_ino]),
                    })
                    rig.start(pass_fds=(sentinel,))
                    self.assertFalse(rig.actors["fdcheck"].record["extra_fd_open"],
                                     "unrelated inherited fd reached worker body")
                    rig.actors["leader"].send("exit")
                    self.assertEqual(rig.finish_cleanup(), 0)
                finally:
                    os.close(sentinel)

    def test_release_owner_is_shared_and_installed_only_in_current_rung(self):
        self.assertTrue(OWNER.is_file(), "shared release lifetime owner missing")
        for entry in ("install.sh", "uninstall.sh"):
            source = (REPO / entry).read_text(encoding="utf-8")
            self.assertTrue(_bootstrap(source), entry)
            for name in ("bounded_command_capture", "run_with_deadline"):
                self.assertNotIn("subprocess.Popen", _function(source, name))
        installer = (REPO / "install.sh").read_text(encoding="utf-8")
        roster = installer.split("SIA_RELEASE_FILES=(", 1)[1].split("\n)", 1)[0]
        self.assertIn("bin/sialifetime.py", shlex.split(roster))
        authority = (REPO / "bin" / "siarelease.py").read_text(encoding="utf-8")
        ladder_section = authority.split("def validate_runtime_ladder", 1)[0]
        historical = ladder_section.split(
            "MODERN_V13_RUNTIME_ADDITIONS", 1)[0]
        self.assertNotIn('"sialifetime.py"', historical)
        self.assertIn(
            'MODERN_V13_RUNTIME_ADDITIONS = (\n'
            '    "sialifetime.py", "uninstall.sh",\n)', ladder_section)

    def test_feature_refusal_precedes_worker_launch_and_closes_opened_fds(self):
        self.assertTrue(OWNER.is_file(), "shared release lifetime owner missing")
        # Only capability syscalls are fault-injected. No spawn, signal,
        # wait, lock, or claimed child-death observation is mocked.
        probe = textwrap.dedent(r'''
            import ctypes
            import errno
            import json
            import os
            import runpy
            import sys

            helper, entry, failure = sys.argv[1:]
            baseline = set(os.listdir("/proc/self/fd"))
            if failure == "pidfd":
                def unavailable(*args, **kwargs):
                    raise OSError(errno.ENOSYS, "pidfd unavailable")
                os.pidfd_open = unavailable
            else:
                original = ctypes.CDLL
                class RefusingPrctl:
                    def __call__(self, *args):
                        ctypes.set_errno(errno.ENOSYS)
                        return -1
                class Library:
                    def __init__(self, *args, **kwargs):
                        self.library = original(*args, **kwargs)
                        self.prctl = RefusingPrctl()
                    def __getattr__(self, name):
                        return getattr(self.library, name)
                ctypes.CDLL = Library
            sys.argv = [helper, "supervise", entry]
            try:
                runpy.run_path(helper, run_name="__main__")
            except SystemExit as result:
                status = result.code
            else:
                status = 0
            remaining = set(os.listdir("/proc/self/fd"))
            print(json.dumps({"status": status, "fds_closed": baseline == remaining}))
        ''')
        for feature in ("pidfd", "subreaper"):
            with self.subTest(feature=feature), tempfile.TemporaryDirectory() as root:
                entry = Path(root) / "install.sh"
                helper = Path(root) / "bin" / "sialifetime.py"
                helper.parent.mkdir()
                shutil.copy2(OWNER, helper)
                marker = Path(root) / "launched"
                entry.write_text("#!/usr/bin/env bash\nprintf launched > "
                                 + shlex.quote(str(marker)) + "\n")
                entry.chmod(0o700)
                result = subprocess.run(
                    [sys.executable, "-c", probe, str(helper), str(entry), feature],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, timeout=30, check=False,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                self.assertEqual(result.returncode, 0, result.stderr)
                record = json.loads(result.stdout)
                self.assertNotEqual(record["status"], 0)
                self.assertTrue(record["fds_closed"], result.stdout)
                self.assertFalse(marker.exists(), "worker ran before feature refusal")
                self.assertIn(feature, result.stderr.lower())
                self.assertNotIn("Traceback", result.stderr)

    def test_incomplete_caller_admission_is_a_named_refusal(self):
        result = subprocess.run(
            [sys.executable, str(OWNER), "supervise", "--caller"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("caller", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
