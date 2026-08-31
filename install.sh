#!/usr/bin/env bash
# SIA — the Omarchy Brain · installer
# Idempotent. Run from the cloned repo / plugin directory:
#   omarchy plugin add https://github.com/AnubisQuantumCipher/sia
#   cd ~/.config/omarchy/plugins/khephri.sia && ./install.sh
# or: git clone … && cd sia && ./install.sh
#
# What you get: a resident daemon that turns YOUR machine's evidence
# streams into a private, associative, self-consolidating memory. A fresh
# installation creates private keys and an empty corpus before replaying the
# available historical tails; an upgrade verifies and retains the existing
# identity and corpus. Ingestion, storage, indexing, and embeddings stay local;
# an optional operator-configured CLI judge may send recalled context.

set -euo pipefail
case "${HOME:-}" in
  ""|/) echo "refusing install with an unsafe HOME" >&2; exit 2 ;;
  /*) ;;
  *) echo "refusing install with a non-absolute HOME" >&2; exit 2 ;;
esac
case "$HOME" in
  *$'\n'*|*$'\r'*) echo "refusing install with line breaks in HOME" >&2; exit 2 ;;
esac
SIA_CANONICAL_HOME="$(cd -P -- "$HOME" 2>/dev/null && pwd)" || {
  echo "refusing install because HOME is not an accessible directory" >&2
  exit 2
}
[ "$SIA_CANONICAL_HOME" != "/" ] || {
  echo "refusing install because HOME resolves to /" >&2
  exit 2
}
HOME="$SIA_CANONICAL_HOME"
export HOME
case "${XDG_RUNTIME_DIR:-}" in
  /*) ;;
  *) echo "refusing install with an unsafe XDG_RUNTIME_DIR" >&2; exit 2 ;;
esac
case "$XDG_RUNTIME_DIR" in
  *$'\n'*|*$'\r'*|*[[:space:]\\]*)
    echo "refusing install with an unsafe XDG_RUNTIME_DIR" >&2
    exit 2
    ;;
esac
export GBRAIN_SKIP_STARTUP_HOOKS=1
unset SIA_INHERITED_LIFECYCLE_FD \
  SIA_LAUNCHER_ABI SIA_LAUNCHER_LIFECYCLE_FD \
  SIA_LAUNCHER_TARGET_FD SIA_LAUNCHER_TARGET_PATH
REPO="$(cd "$(dirname "$0")" && pwd)"
SIA_ORIGINAL_REPO="$REPO"
SIA_RELEASE_SOURCE=""
SHARE="$HOME/.local/share/sia"
STATE="$HOME/.local/state/sia"
BINDIR="$SHARE/bin"
LIFECYCLE_LOCK="$HOME/.local/state/sia.lifecycle.lock"
LIFECYCLE_ADMIN_LOCK="$HOME/.local/state/sia.lifecycle-admin.lock"
LIFECYCLE_TOMBSTONE="$HOME/.local/state/sia.lifecycle-removed"
CONFIG_DIR="$HOME/.config/sia"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
TOOLCHAIN="$SHARE/toolchain"
MANAGED_DIR="$STATE/managed-install"
BRAINSTEM_UNIT="$SYSTEMD_USER_DIR/sia-brainstem.service"
BRAINSTEM_RECEIPT="$MANAGED_DIR/sia-brainstem.service"
BRAINSTEM_RUNTIME_BARRIER="$XDG_RUNTIME_DIR/systemd/user/sia-brainstem.service.d/sia-lifecycle-barrier.conf"
CORPUS_RECEIPT="$MANAGED_DIR/corpus"
CORPUS_BOOTSTRAP_INTENT="$MANAGED_DIR/corpus-bootstrap"
CORPUS_ADOPTION_INTENT="$MANAGED_DIR/corpus-adoption"
CORPUS_BOOTSTRAP_STAGE="$SHARE/.corpus-bootstrap-tree"
GBRAIN_BOOTSTRAP_INTENT="$MANAGED_DIR/gbrain-bootstrap"
GBRAIN_BOOTSTRAP_HOME="$SHARE/.gbrain-bootstrap-home"
GBRAIN_BOOTSTRAP_STAGE="$SHARE/.gbrain-bootstrap-tree"
GBRAIN_BOOTSTRAP_BACKUP="$SHARE/.gbrain-bootstrap-prior"
OLLAMA_UNIT_RECEIPT="$MANAGED_DIR/ollama.service"
OLLAMA_LINK_RECEIPT="$MANAGED_DIR/ollama-link"
CLI_PATH="$HOME/.local/bin/sia"
CLI_RECEIPT="$MANAGED_DIR/sia-cli"
GBRAIN_PIN_RECEIPT="$MANAGED_DIR/gbrain-pin"
SCHEMA_PACK_RECEIPT="$MANAGED_DIR/schema-pack"
RUNTIME_RECEIPT="$MANAGED_DIR/runtime"
LAUNCH_FENCE_JOURNAL="$MANAGED_DIR/launch-fence.json"
SIA_OLLAMA_STAGE=""
SIA_PLUGIN_STAGE=""
SIA_RUNTIME_STAGE=""
SIA_BUN_STAGE=""
SIA_GBRAIN_STAGE=""
SIA_INSTALL_LOCK_FD=""
SIA_INSTALL_ADMIN_LOCK_FD=""
SIA_BRAINSTEM_LOCK_FD=""
SIA_CORPUS_LOCK_FD=""
SIA_GBRAIN_LOCK_FD=""
SIA_RESTORE_LIFECYCLE_TOMBSTONE=0
SIA_LIFECYCLE_TOMBSTONE_CLEARED=0
SIA_LIFECYCLE_ACQUIRE_ATTEMPTS=8
SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED=0
SIA_BRAINSTEM_BARRIER_DEFERRED=0
SIA_BRAINSTEM_FINAL_UNBARRIERED=0
SIA_KEEP_BRAINSTEM_RUNTIME_BARRIER=0
SIA_STABLE_LAUNCHER=""
SIA_CLI_EXPECTED=""
SIA_RUNTIME_TREE_EXPECTED=""
SIA_RUNTIME_INSTALLED_TREE=""
SIA_LAUNCH_FENCE_ARMED=0
SIA_CORPUS_BOOTSTRAP_NEEDED=0
SIA_CORPUS_ADOPTION_NEEDED=0
SIA_CORPUS_EARLY_RECEIPT_STATE=absent
SIA_CORPUS_EARLY_RECEIPT_ROOT=""
SIA_CORPUS_EARLY_RECEIPT_GENERATION=""
SIA_CORPUS_EARLY_RECEIPT_JOURNAL_STATE=absent
SIA_CORPUS_RECEIPT_LOCKS_HELD=0
SIA_GBRAIN_BOOTSTRAP_NEEDED=0
step() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

preflight_python_capabilities() {
  python3 - <<'PY'
import os
import selectors
import subprocess
import sys
try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey)
except Exception as error:
    raise SystemExit(
        "python-cryptography with Ed25519 support is required: "
        f"{error}") from error

if not hasattr(os, "pidfd_open"):
    raise SystemExit(
        "Python os.pidfd_open is required for bounded SIA process cleanup")
process = subprocess.Popen(
    [sys.executable, "-c", "pass"],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True)
pidfd = None
watcher = selectors.DefaultSelector()
try:
    pidfd = os.pidfd_open(process.pid, 0)
    watcher.register(pidfd, selectors.EVENT_READ)
    if not watcher.select(2):
        raise OSError("pidfd did not become poll-readable after child exit")
except OSError as error:
    raise SystemExit(
        "the running kernel must support pollable pidfds for bounded SIA "
        f"process cleanup: {error}") from error
finally:
    watcher.close()
    if pidfd is not None:
        os.close(pidfd)
    process.wait()

try:
    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption())
    public_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    restored_private = Ed25519PrivateKey.from_private_bytes(private_raw)
    restored_public = Ed25519PublicKey.from_public_bytes(public_raw)
    message = b"sia-installer-ed25519-preflight-v1"
    restored_public.verify(restored_private.sign(message), message)
except Exception as error:
    raise SystemExit(
        "python-cryptography cannot generate, raw-serialize, sign, and "
        f"verify Ed25519 keys: {error}") from error
PY
}

# Exercise the Linux/filesystem primitives used by every durable publication
# before any managed payload is replaced. Fixed private names make a killed
# probe bounded and replayable; an unexpected occupant is preserved/refused.
preflight_managed_filesystem_capabilities() {
  python3 - "$@" <<'PY'
import ctypes
import errno
import os
import stat
import sys

if len(sys.argv) < 3:
    raise SystemExit("managed-filesystem capability probe needs a ledger root")

ledger_root = os.path.abspath(sys.argv[1])
roots = [os.path.abspath(value) for value in sys.argv[2:]]
DIRECTORY_FLAGS = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                   | getattr(os, "O_DIRECTORY", 0)
                   | getattr(os, "O_NOFOLLOW", 0))
FILE_FLAGS = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
              | getattr(os, "O_NOFOLLOW", 0)
              | getattr(os, "O_NONBLOCK", 0))
SOURCE = b"sia-renameat2-source-v1\n"
DESTINATION = b"sia-renameat2-destination-v1\n"
ANONYMOUS = b"sia-ledger-anonymous-stage-v1\n"
SOURCE_NAME = ".sia-capability-rename-source"
DESTINATION_NAME = ".sia-capability-rename-destination"
LINK_NAME = ".sia-capability-ledger-link"


def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_nlink, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns)


def read_exact(directory, name, allowed):
    descriptor = os.open(name, FILE_FLAGS, dir_fd=directory)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() or before.st_nlink != 1 \
                or stat.S_IMODE(before.st_mode) != 0o600:
            raise ValueError(f"unsafe retained capability probe: {name}")
        ceiling = max(map(len, allowed))
        chunks = []
        remaining = ceiling + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        current = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if generation(before) != generation(after) \
                or generation(after) != generation(current) \
                or len(content) != after.st_size or content not in allowed:
            raise ValueError(f"changed or foreign capability probe: {name}")
        return generation(after), content
    finally:
        os.close(descriptor)


def exists(directory, name):
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def remove_exact(directory, name, allowed):
    if not exists(directory, name):
        return
    expected, _content = read_exact(directory, name, allowed)
    current = os.stat(name, dir_fd=directory, follow_symlinks=False)
    if generation(current) != expected:
        raise ValueError(f"capability probe changed before cleanup: {name}")
    os.unlink(name, dir_fd=directory)
    os.fsync(directory)


def create_exact(directory, name, content):
    descriptor = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        0o600, dir_fd=directory)
    try:
        remaining = memoryview(content)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("short capability-probe write")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.fsync(directory)


try:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = libc.renameat2
    linkat = libc.linkat
except AttributeError as error:
    raise SystemExit(
        "Linux renameat2 and linkat are required for no-clobber SIA "
        "publication") from error
renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p,
                      ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
renameat2.restype = ctypes.c_int
linkat.argtypes = [ctypes.c_int, ctypes.c_char_p,
                   ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
linkat.restype = ctypes.c_int
RENAME_NOREPLACE = 1
AT_EMPTY_PATH = 0x1000


def rename_noreplace(directory, source, destination):
    result = renameat2(directory, os.fsencode(source), directory,
                       os.fsencode(destination), RENAME_NOREPLACE)
    if result:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), (source, destination))


def probe_rename(root):
    directory = os.open(root, DIRECTORY_FLAGS)
    try:
        info = os.fstat(directory)
        current = os.stat(root, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() \
                or generation(info) != generation(current):
            raise ValueError(f"unsafe managed-filesystem probe root: {root}")
        remove_exact(directory, SOURCE_NAME, {SOURCE})
        remove_exact(directory, DESTINATION_NAME, {SOURCE, DESTINATION})
        create_exact(directory, SOURCE_NAME, SOURCE)
        create_exact(directory, DESTINATION_NAME, DESTINATION)
        try:
            rename_noreplace(directory, SOURCE_NAME, DESTINATION_NAME)
        except OSError as error:
            if error.errno != errno.EEXIST:
                raise RuntimeError(
                    f"filesystem at {root} lacks working "
                    f"renameat2(RENAME_NOREPLACE): {error}") from error
        else:
            raise RuntimeError(
                "renameat2(RENAME_NOREPLACE) overwrote an existing target")
        read_exact(directory, SOURCE_NAME, {SOURCE})
        read_exact(directory, DESTINATION_NAME, {DESTINATION})
        remove_exact(directory, DESTINATION_NAME, {DESTINATION})
        rename_noreplace(directory, SOURCE_NAME, DESTINATION_NAME)
        os.fsync(directory)
        read_exact(directory, DESTINATION_NAME, {SOURCE})
        remove_exact(directory, DESTINATION_NAME, {SOURCE})
    finally:
        try:
            remove_exact(directory, SOURCE_NAME, {SOURCE})
            remove_exact(directory, DESTINATION_NAME, {SOURCE, DESTINATION})
        finally:
            os.close(directory)


seen_devices = set()
for root in roots:
    info = os.stat(root, follow_symlinks=False)
    if info.st_dev in seen_devices:
        continue
    probe_rename(root)
    seen_devices.add(info.st_dev)

directory = os.open(ledger_root, DIRECTORY_FLAGS)
anonymous = None
try:
    remove_exact(directory, LINK_NAME, {ANONYMOUS})
    tmpfile = getattr(os, "O_TMPFILE", 0)
    if not tmpfile:
        raise RuntimeError(
            "Python/Linux O_TMPFILE support is required for ledger state")
    try:
        anonymous = os.open(
            ".", os.O_RDWR | tmpfile | getattr(os, "O_CLOEXEC", 0),
            0o600, dir_fd=directory)
    except OSError as error:
        raise RuntimeError(
            "the SIA ledger filesystem does not support O_TMPFILE: "
            f"{error}") from error
    remaining = memoryview(ANONYMOUS)
    while remaining:
        written = os.write(anonymous, remaining)
        if written <= 0:
            raise OSError("short anonymous ledger capability write")
        remaining = remaining[written:]
    os.fchmod(anonymous, 0o600)
    os.fsync(anonymous)
    result = linkat(anonymous, b"", directory, os.fsencode(LINK_NAME),
                    AT_EMPTY_PATH)
    if result:
        code = ctypes.get_errno()
        raise RuntimeError(
            "the SIA ledger filesystem does not support "
            f"linkat(AT_EMPTY_PATH): {os.strerror(code)}")
    os.fsync(directory)
    linked, content = read_exact(directory, LINK_NAME, {ANONYMOUS})
    if linked[0:2] != generation(os.fstat(anonymous))[0:2] \
            or content != ANONYMOUS:
        raise RuntimeError("anonymous ledger capability link changed")
    remove_exact(directory, LINK_NAME, {ANONYMOUS})
finally:
    try:
        remove_exact(directory, LINK_NAME, {ANONYMOUS})
    finally:
        if anonymous is not None:
            os.close(anonymous)
        os.close(directory)
PY
}

# External inspectors are format-drifting and may emit arbitrary output. This
# front door streams a status=exact 1048576-byte ceiling, rejects NUL/non-UTF-8,
# and kills an overflowing producer before Bash materializes its response.
bounded_command_capture() {
  python3 - "$@" 3<&0 <<'PY'
import os
import selectors
import signal
import subprocess
import sys
import time

MAX_CAPTURE_BYTES = 1_048_576
MAX_RUNTIME_SECONDS = 120
LEADER_POLL_SECONDS = 15
arguments = sys.argv[1:]
if arguments[:1] == ["--stdin"]:
    child_stdin = 3
    arguments = arguments[1:]
else:
    child_stdin = subprocess.DEVNULL
if not arguments:
    raise SystemExit("missing bounded inspector command")
try:
    process = subprocess.Popen(arguments, stdin=child_stdin,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT,
                               start_new_session=True)
except OSError as error:
    print(f"could not execute bounded inspector: {error}", file=sys.stderr)
    raise SystemExit(127)
chunks = []
total = 0
deadline = time.monotonic() + MAX_RUNTIME_SECONDS
selector = selectors.DefaultSelector()
os.set_blocking(process.stdout.fileno(), False)
selector.register(process.stdout, selectors.EVENT_READ, "stdout")
pidfd = None
if hasattr(os, "pidfd_open") and hasattr(os, "P_PIDFD"):
    try:
        pidfd = os.pidfd_open(process.pid, 0)
    except OSError:
        pidfd = None
if pidfd is not None:
    selector.register(pidfd, selectors.EVENT_READ, "leader")


def leader_exited():
    id_type = os.P_PIDFD if pidfd is not None else os.P_PID
    identifier = pidfd if pidfd is not None else process.pid
    result = os.waitid(
        id_type, identifier, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    return result is not None


def kill_group():
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


failure_code = None
failure_message = None
leader_done = False
stdout_open = True
try:
    while True:
        if leader_exited():
            leader_done = True
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            failure_code = 124
            failure_message = "external inspector exceeded its runtime deadline"
            break
        wait_time = remaining if pidfd is not None else min(
            remaining, LEADER_POLL_SECONDS)
        for key, _ in selector.select(wait_time):
            if key.data == "leader":
                leader_done = True
                continue
            try:
                chunk = os.read(
                    process.stdout.fileno(), MAX_CAPTURE_BYTES + 1 - total)
            except BlockingIOError:
                continue
            if not chunk:
                selector.unregister(process.stdout)
                stdout_open = False
                continue
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_CAPTURE_BYTES:
                failure_code = 125
                failure_message = (
                    "external inspector exceeded its output byte ceiling")
                break
        if failure_code is not None or leader_done:
            break
finally:
    # Keep the leader unreaped until this signal. Its PID therefore still pins
    # the process-group identity and cannot be recycled under killpg().
    kill_group()
    status = process.wait()
    if stdout_open and total <= MAX_CAPTURE_BYTES:
        while True:
            try:
                chunk = os.read(
                    process.stdout.fileno(), MAX_CAPTURE_BYTES + 1 - total)
            except BlockingIOError:
                break
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_CAPTURE_BYTES:
                failure_code = 125
                failure_message = (
                    "external inspector exceeded its output byte ceiling")
                break
    selector.close()
    process.stdout.close()
    if pidfd is not None:
        os.close(pidfd)
if failure_code is not None:
    print(failure_message, file=sys.stderr)
    raise SystemExit(failure_code)
content = b"".join(chunks)
if b"\0" in content:
    print("external inspector emitted NUL", file=sys.stderr)
    raise SystemExit(125)
try:
    text = content.decode("utf-8", "strict")
except UnicodeError:
    print("external inspector emitted non-UTF-8 output", file=sys.stderr)
    raise SystemExit(125)
sys.stdout.write(text)
raise SystemExit(status)
PY
}

# Status=exact deadline constants: parsed=2*60 exact=120,
# parsed=5*60 exact=300, parsed=30*60 exact=1800, and parsed=15 exact=15.
# These are operational ceilings, not claims that a command will finish.
run_with_deadline() {
  python3 - "$@" <<'PY'
import os
import selectors
import signal
import subprocess
import sys
import time

ALLOWED_DEADLINES = {120, 300, 1800}
LEADER_POLL_SECONDS = 15
try:
    deadline = int(sys.argv[1], 10)
except (IndexError, ValueError):
    raise SystemExit("invalid command deadline")
if deadline not in ALLOWED_DEADLINES or len(sys.argv) < 3:
    raise SystemExit("unsupported command deadline")
try:
    process = subprocess.Popen(sys.argv[2:], start_new_session=True)
except OSError as error:
    print(f"could not execute bounded command: {error}", file=sys.stderr)
    raise SystemExit(127)
pidfd = None
if hasattr(os, "pidfd_open") and hasattr(os, "P_PIDFD"):
    try:
        pidfd = os.pidfd_open(process.pid, 0)
    except OSError:
        pidfd = None
selector = selectors.DefaultSelector()
if pidfd is not None:
    selector.register(pidfd, selectors.EVENT_READ)


def leader_exited():
    id_type = os.P_PIDFD if pidfd is not None else os.P_PID
    identifier = pidfd if pidfd is not None else process.pid
    result = os.waitid(
        id_type, identifier, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    return result is not None


def kill_group():
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


timed_out = False
end = time.monotonic() + deadline
try:
    while not leader_exited():
        remaining = end - time.monotonic()
        if remaining <= 0:
            timed_out = True
            break
        if pidfd is not None:
            selector.select(remaining)
        else:
            time.sleep(min(remaining, LEADER_POLL_SECONDS))
finally:
    # WNOWAIT keeps the leader's PID/PGID pinned until all descendants have
    # received SIGKILL. Only then may subprocess reap the leader.
    kill_group()
    status = process.wait()
    selector.close()
    if pidfd is not None:
        os.close(pidfd)
if timed_out:
    print(f"command exceeded its {deadline}-second runtime deadline",
          file=sys.stderr)
    raise SystemExit(124)
raise SystemExit(status)
PY
}

# One byte-exact front door for lifecycle authority metadata.  File bytes never
# enter a shell variable: the helper opens without following links, checks the
# owner/type/ceiling, binds the read to one before/after/current-path
# generation, and compares the final newline as data.  Managed target digests
# are streamed from the same kind of generation-bound descriptor.
owned_metadata() {
  python3 - "$@" <<'PY'
import hashlib
import os
import re
import stat
import sys
import tempfile

MAX_METADATA_BYTES = 65_536
READ_CHUNK_BYTES = 1_048_576


def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def current_generation(path):
    value = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(value.st_mode) or value.st_uid != os.geteuid():
        raise ValueError("current path is not an owned regular file")
    return value


def open_owned_regular(path):
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    descriptor = os.open(path, flags)
    value = os.fstat(descriptor)
    if not stat.S_ISREG(value.st_mode) or value.st_uid != os.geteuid():
        os.close(descriptor)
        raise ValueError("not an owned regular file")
    return descriptor, value


def finish_stable(path, descriptor, before):
    after = os.fstat(descriptor)
    current = current_generation(path)
    if generation(before) != generation(after) \
            or generation(after) != generation(current):
        raise ValueError("file changed while it was inspected")


def inspect_metadata(path):
    descriptor, before = open_owned_regular(path)
    try:
        if before.st_size > MAX_METADATA_BYTES:
            raise ValueError("metadata exceeds its byte ceiling")
        chunks = []
        remaining = MAX_METADATA_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, READ_CHUNK_BYTES))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) != before.st_size \
                or len(content) > MAX_METADATA_BYTES:
            raise ValueError("metadata changed or exceeds its byte ceiling")
        finish_stable(path, descriptor, before)
    finally:
        os.close(descriptor)
    if b"\0" in content:
        raise ValueError("metadata contains NUL")
    return content, before


def read_metadata(path):
    return inspect_metadata(path)[0]


def inspect_owned_regular(path):
    descriptor, before = open_owned_regular(path)
    digest = hashlib.sha256()
    try:
        while True:
            chunk = os.read(descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
        finish_stable(path, descriptor, before)
    finally:
        os.close(descriptor)
    return digest.hexdigest(), before


def digest_owned_regular(path):
    return inspect_owned_regular(path)[0]


def generation_token(path):
    digest, value = inspect_owned_regular(path)
    fields = (*generation(value), digest)
    return "present:" + ":".join(str(field) for field in fields)


def same_content(first, second):
    return digest_owned_regular(first) == digest_owned_regular(second)


def line_file(value):
    return value.encode("utf-8", "strict") + b"\n"


def exact_managed_file(receipt, kind, target):
    digest = digest_owned_regular(target)
    expected = (f"managed-by=khephri.sia\nkind={kind}\npath={target}\n"
                f"sha256={digest}\n").encode("utf-8")
    return read_metadata(receipt) == expected


def exact_runtime_receipt(receipt, runtime, digest):
    expected = (f"managed-by=khephri.sia\nkind=runtime\npath={runtime}\n"
                f"sha256={digest}\n").encode("utf-8")
    return read_metadata(receipt) == expected


def exact_skill_marker(marker, skill):
    digest = digest_owned_regular(skill)
    expected = ("managed-by=khephri.sia\n"
                f"skill_sha256={digest}\n").encode("utf-8")
    return read_metadata(marker) == expected


def token_from_inspection(value, digest):
    fields = (*generation(value), digest)
    return "present:" + ":".join(str(field) for field in fields)


def exact_skill_generations(marker, skill):
    skill_digest, skill_info = inspect_owned_regular(skill)
    marker_content, marker_info = inspect_metadata(marker)
    expected = ("managed-by=khephri.sia\n"
                f"skill_sha256={skill_digest}\n").encode("utf-8")
    if marker_content != expected \
            or generation(current_generation(skill)) != generation(skill_info) \
            or generation(current_generation(marker)) != generation(marker_info):
        return False
    marker_digest = hashlib.sha256(marker_content).hexdigest()
    print(token_from_inspection(skill_info, skill_digest) + "\t"
          + token_from_inspection(marker_info, marker_digest))
    return True


def exact_release_receipt(receipt, binary, prefix):
    digest = digest_owned_regular(binary)
    expected = (prefix + f"\nbinary_sha256={digest}\n").encode("utf-8")
    return read_metadata(receipt) == expected


def classify(path, pairs):
    if not pairs or len(pairs) % 2:
        raise ValueError("classification requires token/value pairs")
    content = read_metadata(path)
    for token, expected in zip(pairs[0::2], pairs[1::2]):
        if re.fullmatch(r"[a-z][a-z-]*", token) is None:
            raise ValueError("unsafe classification token")
        if content == line_file(expected):
            print(token)
            return True
    return False


def binding_state(path):
    content = read_metadata(path)
    try:
        text = content.decode("utf-8", "strict")
    except UnicodeError as error:
        raise ValueError("bindings are not strict UTF-8") from error
    stripped = [line.strip() for line in text.split("\n")]
    allowed_begins = {
        "-- BEGIN SIA",
        "-- BEGIN SIA (managed by khephri.sia/install.sh)",
    }
    begins = [index for index, line in enumerate(stripped)
              if "-- BEGIN SIA" in line]
    ends = [index for index, line in enumerate(stripped)
            if "-- END SIA" in line]
    if not begins and not ends:
        print("absent")
    elif (len(begins) == 1 and len(ends) == 1
          and stripped[begins[0]] in allowed_begins
          and stripped[ends[0]] == "-- END SIA"
          and begins[0] < ends[0]):
        print("managed")
    else:
        print("unsafe")
    return True


def runtime_digest_field(receipt, runtime):
    content = read_metadata(receipt)
    prefix = (f"managed-by=khephri.sia\nkind=runtime\npath={runtime}\n"
              "sha256=").encode("utf-8")
    if not content.startswith(prefix) or not content.endswith(b"\n"):
        return False
    digest = content[len(prefix):-1]
    if re.fullmatch(rb"[0-9a-f]{64}", digest) is None:
        return False
    print(digest.decode("ascii"))
    return True


try:
    mode, *arguments = sys.argv[1:]
    if mode == "exact":
        accepted = read_metadata(arguments[0]) == line_file(arguments[1])
    elif mode == "line":
        needle = arguments[1].encode("utf-8", "strict")
        accepted = needle in read_metadata(arguments[0]).split(b"\n")
    elif mode == "managed-file":
        accepted = exact_managed_file(*arguments)
    elif mode == "runtime":
        accepted = exact_runtime_receipt(*arguments)
    elif mode == "runtime-digest":
        accepted = runtime_digest_field(*arguments)
    elif mode == "skill":
        accepted = exact_skill_marker(*arguments)
    elif mode == "skill-generations":
        accepted = exact_skill_generations(*arguments)
    elif mode == "release":
        accepted = exact_release_receipt(*arguments)
    elif mode == "digest":
        print(digest_owned_regular(arguments[0]))
        accepted = True
    elif mode == "generation":
        print(generation_token(arguments[0]))
        accepted = True
    elif mode == "same-content":
        accepted = same_content(*arguments)
    elif mode == "classify":
        accepted = classify(arguments[0], arguments[1:])
    elif mode == "binding-state":
        accepted = binding_state(arguments[0])
    else:
        accepted = False
except (IndexError, OSError, UnicodeError, ValueError):
    accepted = False
raise SystemExit(0 if accepted else 1)
PY
}

# Generation-bound publication/removal for user-editable integration files.
# Both operations serialize through an owner-only sibling lock and leave a
# durable intent journal before creating a temporary canonical-path absence.
# Every rename is RENAME_NOREPLACE: an independent writer always wins the
# canonical name, while the generation displaced by this helper is retained at
# a unique, reported sibling path.  A later invocation recovers a crash journal
# before beginning new work.
owned_file_cas() {
  python3 - "$@" <<'PY'
import ctypes
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import sys

MAX_BYTES = 1_048_576
CHUNK_BYTES = 1_048_576
MAX_JOURNAL_BYTES = 65_536
arguments = sys.argv[1:]
if not arguments:
    raise SystemExit("missing CAS operation")
mode = arguments[0]
if mode == "recover":
    if len(arguments) != 2:
        raise SystemExit("recover requires a target")
    target = os.path.abspath(arguments[1])
    staged = None
    expected = None
elif len(arguments) == 4:
    _, staged, target, expected = arguments
    staged = os.path.abspath(staged)
    target = os.path.abspath(target)
else:
    raise SystemExit("invalid CAS arguments")
parent = os.path.dirname(target)
if os.path.realpath(parent) != parent:
    raise SystemExit("CAS parent must not traverse symbolic links")
if staged is not None \
        and (os.path.dirname(staged) != parent or staged == target):
    raise SystemExit("CAS paths must be distinct siblings")
target_name = os.path.basename(target)
staged_name = None if staged is None else os.path.basename(staged)
token_pattern = re.compile(
    r"present:(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):([0-9a-f]{64})")
if expected is not None and expected != "absent" \
        and token_pattern.fullmatch(expected) is None:
    raise SystemExit("invalid CAS generation")
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_NOFOLLOW", 0))
parent_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0))
parent_fd = os.open(parent, parent_flags)
parent_info = os.fstat(parent_fd)
if not stat.S_ISDIR(parent_info.st_mode) \
        or parent_info.st_uid != os.geteuid():
    os.close(parent_fd)
    raise SystemExit("CAS parent must be an owned directory")


def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def token(name, allow_absent=False):
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        if allow_absent:
            try:
                os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return "absent"
        raise
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_size > MAX_BYTES:
            raise ValueError("unsafe or oversized CAS file")
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(descriptor, CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BYTES:
                raise ValueError("oversized CAS file")
            digest.update(chunk)
        after = os.fstat(descriptor)
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if total != before.st_size \
                or generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise ValueError("CAS file changed while inspected")
    finally:
        os.close(descriptor)
    fields = (*generation(before), digest.hexdigest())
    return "present:" + ":".join(str(value) for value in fields)


libc = ctypes.CDLL(None, use_errno=True)
renameat2 = libc.renameat2
renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p,
                      ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
renameat2.restype = ctypes.c_int
RENAME_NOREPLACE = 1


def rename_noreplace(source, destination):
    result = renameat2(parent_fd, os.fsencode(source),
                       parent_fd, os.fsencode(destination),
                       RENAME_NOREPLACE)
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), (source, destination))


def sync_parent():
    os.fsync(parent_fd)


def moved_token_matches(actual, prior):
    actual_match = token_pattern.fullmatch(actual)
    prior_match = token_pattern.fullmatch(prior)
    if actual_match is None or prior_match is None:
        return False
    actual_fields = actual_match.groups()
    prior_fields = prior_match.groups()
    return actual_fields[:6] == prior_fields[:6] \
        and actual_fields[7] == prior_fields[7]


def child_exists(name):
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def unlink_child(name):
    os.unlink(name, dir_fd=parent_fd)
    sync_parent()


def unique_name(prefix):
    while True:
        candidate = prefix + secrets.token_hex(12)
        if not child_exists(candidate):
            return candidate


identity = hashlib.sha256(os.fsencode(target)).hexdigest()
lock_name = ".sia-cas-lock-" + identity
journal_name = ".sia-cas-journal-" + identity
lock_flags = (os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
              | getattr(os, "O_NOFOLLOW", 0))
lock_fd = os.open(lock_name, lock_flags, 0o600, dir_fd=parent_fd)
lock_info = os.fstat(lock_fd)
if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.geteuid():
    raise SystemExit("unsafe CAS lock")
os.fchmod(lock_fd, 0o600)
fcntl.flock(lock_fd, fcntl.LOCK_EX)


def read_journal():
    descriptor = os.open(journal_name, flags, dir_fd=parent_fd)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_size > MAX_JOURNAL_BYTES:
            raise ValueError("unsafe CAS journal")
        chunks = []
        total = 0
        while True:
            chunk = os.read(descriptor, CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_JOURNAL_BYTES:
                raise ValueError("oversized CAS journal")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        current = os.stat(journal_name, dir_fd=parent_fd,
                          follow_symlinks=False)
        if total != before.st_size \
                or generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise ValueError("CAS journal changed while inspected")
        value = json.loads(b"".join(chunks).decode("utf-8"))
    finally:
        os.close(descriptor)
    required = {"version", "operation", "target", "staged",
                "archive", "expected", "desired"}
    if not isinstance(value, dict) or set(value) != required \
            or value["version"] != 1 or value["target"] != target_name \
            or value["operation"] not in {"publish", "archive"}:
        raise ValueError("invalid CAS journal")
    for key in ("target", "staged", "archive"):
        item = value[key]
        if not isinstance(item, str) or not item \
                or os.path.basename(item) != item:
            raise ValueError("invalid CAS journal path")
    for key in ("expected", "desired"):
        item = value[key]
        if item != "absent" and token_pattern.fullmatch(item) is None:
            raise ValueError("invalid CAS journal generation")
    return value


def write_journal(record):
    payload = (json.dumps(record, sort_keys=True,
                          separators=(",", ":")) + "\n").encode("utf-8")
    if len(payload) > MAX_JOURNAL_BYTES:
        raise ValueError("oversized CAS journal payload")
    temporary_name = unique_name(".sia-cas-journal-stage.")
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            0o600, dir_fd=parent_fd)
        try:
            remaining = memoryview(payload)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("short CAS journal write")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        rename_noreplace(temporary_name, journal_name)
        sync_parent()
    except BaseException:
        try:
            unlink_child(temporary_name)
        except FileNotFoundError:
            pass
        raise


def clear_journal():
    if child_exists(journal_name):
        unlink_child(journal_name)


def retained(record, reason):
    archive = record["archive"]
    if child_exists(archive):
        print(f"{reason}; prior generation retained at "
              f"{os.path.join(parent, archive)}", file=sys.stderr)


def recover_journal():
    if not child_exists(journal_name):
        return
    record = read_journal()
    operation = record["operation"]
    archive = record["archive"]
    prior_stage = record["staged"]
    prior = record["expected"]
    desired = record["desired"]
    current = token(target_name, allow_absent=True)
    archived = token(archive, allow_absent=True)
    staged_current = token(prior_stage, allow_absent=True)
    if operation == "publish" and prior == "absent":
        if current == "absent" and moved_token_matches(staged_current, desired):
            clear_journal()
            return
        if moved_token_matches(current, desired):
            clear_journal()
            return
        print("CAS recovery preserved an independently published target",
              file=sys.stderr)
        clear_journal()
        return
    if operation == "publish":
        if moved_token_matches(current, desired):
            if moved_token_matches(archived, prior):
                if staged_current == "absent":
                    try:
                        rename_noreplace(archive, prior_stage)
                        sync_parent()
                    except OSError:
                        retained(record, "CAS recovery could not return backup")
                else:
                    retained(record, "CAS recovery found an occupied backup path")
            clear_journal()
            return
        if current == "absent" and moved_token_matches(archived, prior):
            try:
                rename_noreplace(archive, target_name)
                sync_parent()
            except OSError:
                retained(record, "CAS recovery would not overwrite a newer target")
            clear_journal()
            return
        if current == prior and archived == "absent":
            clear_journal()
            return
        retained(record, "CAS recovery preserved a concurrent target")
        clear_journal()
        return
    if moved_token_matches(staged_current, prior):
        clear_journal()
        return
    if current == prior and archived == "absent":
        clear_journal()
        return
    if current == "absent" and moved_token_matches(archived, prior) \
            and staged_current == "absent":
        try:
            rename_noreplace(archive, prior_stage)
            sync_parent()
        except OSError:
            retained(record, "CAS recovery could not finish archival")
        clear_journal()
        return
    retained(record, "CAS recovery preserved a concurrent target")
    clear_journal()


try:
    recover_journal()
    if mode == "recover":
        raise SystemExit(0)
    if mode == "publish":
        desired_token = token(staged_name)
        staged_fd = os.open(staged_name, flags, dir_fd=parent_fd)
        try:
            os.fsync(staged_fd)
        finally:
            os.close(staged_fd)
    elif mode == "archive":
        if child_exists(staged_name):
            raise SystemExit("CAS archive already exists")
        desired_token = "absent"
    else:
        raise SystemExit("unknown CAS operation")
    current = token(target_name, allow_absent=True)
    if current != expected:
        raise SystemExit("CAS target changed before operation")
    archive_name = unique_name(".sia-cas-prior.")
    record = {"version": 1, "operation": mode, "target": target_name,
              "staged": staged_name, "archive": archive_name,
              "expected": expected, "desired": desired_token}
    if mode == "publish":
        write_journal(record)
        if expected != "absent":
            rename_noreplace(target_name, archive_name)
            sync_parent()
            archived = token(archive_name)
            if not moved_token_matches(archived, expected):
                try:
                    rename_noreplace(archive_name, target_name)
                    sync_parent()
                except OSError:
                    retained(record, "CAS validation refused to overwrite a newer target")
                clear_journal()
                raise SystemExit("CAS archived generation did not match preflight")
        try:
            rename_noreplace(staged_name, target_name)
            sync_parent()
        except OSError:
            retained(record, "CAS publication preserved a concurrent target")
            clear_journal()
            raise SystemExit("CAS target changed during publication")
        installed = token(target_name)
        if not moved_token_matches(installed, desired_token):
            retained(record, "CAS canonical target changed after publication")
            clear_journal()
            raise SystemExit("CAS published generation is no longer current")
        if expected != "absent":
            try:
                rename_noreplace(archive_name, staged_name)
                sync_parent()
            except OSError:
                retained(record, "CAS could not return the prior generation")
                clear_journal()
                raise SystemExit("CAS backup path changed during publication")
            if not moved_token_matches(token(staged_name), expected) \
                    or not moved_token_matches(token(target_name), installed):
                conflict_name = unique_name(".sia-cas-conflict.")
                try:
                    rename_noreplace(staged_name, conflict_name)
                    sync_parent()
                    print("CAS prior generation retained at "
                          f"{os.path.join(parent, conflict_name)}",
                          file=sys.stderr)
                except OSError:
                    print("CAS prior generation retained at "
                          f"{os.path.join(parent, staged_name)}",
                          file=sys.stderr)
                clear_journal()
                raise SystemExit("CAS target changed at publication boundary")
        clear_journal()
        print(installed)
    elif mode == "archive":
        if expected == "absent":
            raise SystemExit("invalid CAS archival state")
        write_journal(record)
        rename_noreplace(target_name, archive_name)
        sync_parent()
        if not moved_token_matches(token(archive_name), expected):
            try:
                rename_noreplace(archive_name, target_name)
                sync_parent()
            except OSError:
                retained(record, "CAS archival preserved a newer target")
            clear_journal()
            raise SystemExit("CAS archived generation did not match preflight")
        if token(target_name, allow_absent=True) != "absent":
            retained(record, "CAS archival preserved a concurrent target")
            clear_journal()
            raise SystemExit("CAS target changed during archival")
        rename_noreplace(archive_name, staged_name)
        sync_parent()
        if not moved_token_matches(token(staged_name), expected) \
                or token(target_name, allow_absent=True) != "absent":
            conflict_name = unique_name(".sia-cas-conflict.")
            try:
                rename_noreplace(staged_name, conflict_name)
                sync_parent()
                print("CAS archived generation retained at "
                      f"{os.path.join(parent, conflict_name)}",
                      file=sys.stderr)
            except OSError:
                print("CAS archived generation retained at "
                      f"{os.path.join(parent, staged_name)}",
                      file=sys.stderr)
            clear_journal()
            raise SystemExit("CAS target changed at archival boundary")
        clear_journal()
    else:
        raise SystemExit("unknown CAS operation")
finally:
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    os.close(lock_fd)
    os.close(parent_fd)
PY
}

write_lifecycle_tombstone() {
  python3 - "$LIFECYCLE_TOMBSTONE" <<'PY'
import os
import stat
import sys

path = sys.argv[1]
parent = os.path.dirname(path)
flags = (os.O_WRONLY | os.O_CREAT | os.O_TRUNC
         | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
fd = os.open(path, flags, 0o600)
try:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
        raise SystemExit("unsafe lifecycle removal marker")
    os.fchmod(fd, 0o600)
    os.write(fd, b"removed-by=khephri.sia\n")
    os.fsync(fd)
finally:
    os.close(fd)
directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(directory)
finally:
    os.close(directory)
PY
}

clear_lifecycle_tombstone() {
  python3 - "$LIFECYCLE_TOMBSTONE" <<'PY'
import os
import stat
import sys

path = sys.argv[1]
try:
    info = os.lstat(path)
except FileNotFoundError:
    raise SystemExit(0)
if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
    raise SystemExit("unsafe lifecycle removal marker")
os.unlink(path)
directory = os.open(os.path.dirname(path),
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(directory)
finally:
    os.close(directory)
PY
}

mark_install_sync_debt() {
  python3 - "$STATE/memo.json" <<'PY'
import json
import os
import stat
import sys
import tempfile

path = sys.argv[1]
parent = os.path.dirname(path)
limit = 16_777_216
flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
    | getattr(os, "O_NOFOLLOW", 0)
try:
    fd = os.open(path, flags)
except FileNotFoundError:
    memo = {}
else:
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_size > limit:
            raise SystemExit("unsafe or oversized brainstem memo")
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    identity = lambda value: (
        value.st_dev, value.st_ino, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns)
    if identity(before) != identity(after) or len(raw) > limit:
        raise SystemExit("brainstem memo changed during install preflight")
    try:
        memo = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"malformed brainstem memo: {error}") from error
    if not isinstance(memo, dict):
        raise SystemExit("brainstem memo must be an object")
memo["sync_needed"] = True
encoded = json.dumps(memo).encode("utf-8")
if len(encoded) > limit:
    raise SystemExit("brainstem memo exceeds its byte bound")
descriptor, staged = tempfile.mkstemp(prefix=".memo.json.install.",
                                       dir=parent)
try:
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        descriptor = -1
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staged, path)
    directory = os.open(parent,
                        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
except BaseException:
    if descriptor >= 0:
        os.close(descriptor)
    try:
        os.unlink(staged)
    except FileNotFoundError:
        pass
    raise
PY
}

step "SIA — the Omarchy Brain"
for dep in python3 git curl tar unzip sha256sum zstd systemctl flock ss; do
  have "$dep" || { echo "missing dependency: $dep"; exit 1; }
done
ARCH="$(uname -m)"; case "$ARCH" in
  aarch64|arm64)
    OLLAMA_ARCH=arm64
    OLLAMA_SHA256=6c648fd62bc8ea18d19aeb0900a03ff2d6a1fc830d901348d070fb93aca4630e
    BUN_ASSET=bun-linux-aarch64.zip
    BUN_SHA256=4b1a332ee861983eb93bcfe6f770fff94e3e31b2c388bdaea3c8ed35e58eed0e
    ;;
  x86_64)
    OLLAMA_ARCH=amd64
    OLLAMA_SHA256=9785247dea264d9072f09f6c9c0eb4b8e666892826a3d8388eba3e8fb9ed1db9
    if grep -qw avx2 /proc/cpuinfo 2>/dev/null; then
      BUN_ASSET=bun-linux-x64.zip
      BUN_SHA256=2d03fb5fb83ac8b567aca0a281b2ce1a1a19d488f56c2968d88c3f25e92fe452
    else
      BUN_ASSET=bun-linux-x64-baseline.zip
      BUN_SHA256=184fb4595f0d401a217cf7c78c1bc430ba83314dab7a8b94805babbf7fa7097f
    fi
    ;;
  *) echo "unsupported arch: $ARCH"; exit 1 ;;
esac
preflight_python_capabilities

SIA_INSTALL_TMP="$(mktemp -d)"
SIA_BRAINSTEM_WAS_ACTIVE=0
SIA_BRAINSTEM_ENABLE_STATE=disabled
SIA_INSTALL_MUTATED=0
SIA_OLLAMA_SERVICE_MUTATED=0
SIA_OLLAMA_WAS_ACTIVE=0
SIA_OLLAMA_WAS_ENABLED=0
SIA_OLLAMA_ENABLE_STATE=disabled
sia_install_cleanup() {
  local status=$? brainstem_contained=0
  trap - EXIT
  set +e
  chmod -R u+w -- "$SIA_INSTALL_TMP" >/dev/null 2>&1 || true
  rm -rf -- "$SIA_INSTALL_TMP"
  [ -z "$SIA_OLLAMA_STAGE" ] || rm -rf -- "$SIA_OLLAMA_STAGE"
  [ -z "$SIA_PLUGIN_STAGE" ] || rm -rf -- "$SIA_PLUGIN_STAGE"
  [ -z "$SIA_RUNTIME_STAGE" ] || rm -rf -- "$SIA_RUNTIME_STAGE"
  [ -z "$SIA_BUN_STAGE" ] || rm -rf -- "$SIA_BUN_STAGE"
  [ -z "$SIA_GBRAIN_STAGE" ] || rm -rf -- "$SIA_GBRAIN_STAGE"
  if [ "$status" -ne 0 ]; then
    # Restore every public failure gate and stop a mutated generation while
    # the exclusive lifecycle lease and runtime barrier still exclude entrants.
    if [ "$SIA_RESTORE_LIFECYCLE_TOMBSTONE" -eq 1 ] \
        && [ "$SIA_LIFECYCLE_TOMBSTONE_CLEARED" -eq 1 ]; then
      write_lifecycle_tombstone || \
        echo "WARNING: lifecycle removal marker could not be restored" >&2
    fi
    if [ "${SIA_LAUNCH_FENCE_ARMED:-0}" -eq 1 ]; then
      echo "install launch-fence transaction remains incomplete; rerun install.sh to recover it" >&2
    fi
    if [ "$SIA_OLLAMA_SERVICE_MUTATED" -eq 1 ]; then
      # A post-start hash/listener/model refusal means the current unit or
      # runtime is not trusted. Starting it merely to recreate the prior
      # active bit would re-activate rejected artifacts.
      run_with_deadline 120 systemctl --user disable --now ollama.service \
        >/dev/null 2>&1 || \
        echo "WARNING: rejected Ollama service could not be disabled/stopped" >&2
      echo "rejected Ollama service left disabled; inspect retained backups before restoring it" >&2
    fi
    if [ "$SIA_INSTALL_MUTATED" -eq 1 ]; then
      # The successful tail deliberately drops the transaction barrier before
      # starting the completed generation. If reload/start/attestation then
      # fails, re-establish and verify that start barrier before a one-shot
      # disable/stop can be described as containment.
      if [ "$SIA_BRAINSTEM_FINAL_UNBARRIERED" -eq 1 ] \
          && [ "$SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED" -eq 0 ]; then
        if install_brainstem_runtime_barrier; then
          echo "re-established sia-brainstem runtime barrier after final activation failure" >&2
        else
          echo "WARNING: sia-brainstem runtime barrier could not be re-established" >&2
        fi
      fi
      if [ "$SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED" -eq 1 ] \
          && verify_install_brainstem_runtime_barrier; then
        brainstem_contained=1
        # Any mutated generation requires an explicit recovery rerun. A
        # disabled unit remains manually startable, so retain the verified
        # barrier rather than reopening a partially completed installation.
        SIA_KEEP_BRAINSTEM_RUNTIME_BARRIER=1
      fi
      if run_with_deadline 120 systemctl --user disable --now \
          sia-brainstem.service; then
        if [ "$SIA_BRAINSTEM_FINAL_UNBARRIERED" -eq 0 ] \
            || [ "$brainstem_contained" -eq 1 ]; then
          echo "install failed after mutation; sia-brainstem was disabled and stopped" >&2
        else
          echo "WARNING: sia-brainstem disable/stop returned without a verified start barrier" >&2
        fi
      else
        echo "WARNING: install failed and sia-brainstem could not be disabled/stopped" >&2
      fi
      echo "repair the reported cause, then rerun install.sh" >&2
    fi
  fi
  # A synchronous service restart must never occur while this process still
  # owns a lease that the launcher needs. This also makes pre-mutation failure
  # restoration safe after any partial quiescence acquisition.
  if [ -n "$SIA_GBRAIN_LOCK_FD" ]; then
    flock -u "$SIA_GBRAIN_LOCK_FD" >/dev/null 2>&1 || true
    eval "exec ${SIA_GBRAIN_LOCK_FD}>&-"
    SIA_GBRAIN_LOCK_FD=""
  fi
  if [ -n "$SIA_CORPUS_LOCK_FD" ]; then
    flock -u "$SIA_CORPUS_LOCK_FD" >/dev/null 2>&1 || true
    eval "exec ${SIA_CORPUS_LOCK_FD}>&-"
    SIA_CORPUS_LOCK_FD=""
    SIA_CORPUS_RECEIPT_LOCKS_HELD=0
  fi
  if [ -n "$SIA_BRAINSTEM_LOCK_FD" ]; then
    flock -u "$SIA_BRAINSTEM_LOCK_FD" >/dev/null 2>&1 || true
    eval "exec ${SIA_BRAINSTEM_LOCK_FD}>&-"
    SIA_BRAINSTEM_LOCK_FD=""
  fi
  if [ -n "$SIA_INSTALL_LOCK_FD" ]; then
    flock -u "$SIA_INSTALL_LOCK_FD" >/dev/null 2>&1 || true
    eval "exec ${SIA_INSTALL_LOCK_FD}>&-"
    SIA_INSTALL_LOCK_FD=""
  fi
  if [ "$SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED" -eq 1 ] \
      && [ "$SIA_KEEP_BRAINSTEM_RUNTIME_BARRIER" -eq 0 ]; then
    remove_install_brainstem_runtime_barrier || \
      echo "WARNING: installer runtime barrier could not be removed" >&2
  elif [ "$SIA_KEEP_BRAINSTEM_RUNTIME_BARRIER" -eq 1 ]; then
    echo "sia-brainstem.service retains its runtime start barrier after failed activation; inspect it, then rerun install.sh" >&2
  fi
  if [ "$status" -ne 0 ]; then
    if [ "$SIA_INSTALL_MUTATED" -eq 0 ] \
        && [ "$SIA_KEEP_BRAINSTEM_RUNTIME_BARRIER" -eq 0 ] \
        && [ "$SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED" -eq 0 ]; then
      case "$SIA_BRAINSTEM_ENABLE_STATE" in
        enabled)
          run_with_deadline 120 systemctl --user enable sia-brainstem.service \
            >/dev/null 2>&1 || true
          ;;
        enabled-runtime)
          run_with_deadline 120 systemctl --user enable --runtime \
            sia-brainstem.service \
            >/dev/null 2>&1 || true
          ;;
      esac
      if [ "$SIA_BRAINSTEM_WAS_ACTIVE" -eq 1 ]; then
        run_with_deadline 120 systemctl --user start sia-brainstem.service \
          >/dev/null 2>&1 || \
          echo "WARNING: unchanged sia-brainstem could not be restarted" >&2
      fi
    fi
  fi
  exit "$status"
}
trap sia_install_cleanup EXIT
download_verified() {
  local url="$1" out="$2" expected="$3"
  # status=exact parsed=2^31 exact=2147483648; not formal-bounded. This is a
  # transfer/materialization ceiling, not a claim about expected asset size.
  run_with_deadline 1800 curl -fL --proto '=https' --tlsv1.2 \
    --connect-timeout 120 --max-time 1800 --max-filesize 2147483648 \
    -o "$out" "$url"
  printf '%s  %s\n' "$expected" "$out" | sha256sum -c -
}

assert_safe_managed_roots() {
  python3 - "$HOME" "$@" <<'PY'
import os
import stat
import sys

home = os.path.abspath(sys.argv[1])
uid = os.geteuid()
for raw in sys.argv[2:]:
    target = os.path.abspath(raw)
    if os.path.commonpath((home, target)) != home or target == home:
        raise SystemExit(f"unsafe managed root outside HOME: {raw}")
    relative = os.path.relpath(target, home)
    current = home
    for component in relative.split(os.sep):
        current = os.path.join(current, component)
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            break
        if stat.S_ISLNK(info.st_mode):
            raise SystemExit(f"refusing symlinked managed root: {current}")
        if not stat.S_ISDIR(info.st_mode):
            raise SystemExit(f"managed root component is not a directory: {current}")
        if info.st_uid != uid:
            raise SystemExit(f"managed root is not owned by this user: {current}")
PY
}

write_managed_receipt() {
  local receipt="$1" kind="$2" target="$3" digest="$4"
  local output_variable="${5:-}" expected stage installed
  [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || {
    echo "refusing invalid managed receipt digest for $kind" >&2
    return 1
  }
  mkdir -p "$MANAGED_DIR"
  owned_file_cas recover "$receipt" || return 1
  if [ -e "$receipt" ] || [ -L "$receipt" ]; then
    expected="$(owned_metadata generation "$receipt")" || return 1
  else
    expected=absent
  fi
  stage="$(mktemp "$MANAGED_DIR/.${kind}.receipt.XXXXXX")" || return 1
  if ! printf 'managed-by=khephri.sia\nkind=%s\npath=%s\nsha256=%s\n' \
      "$kind" "$target" "$digest" > "$stage" \
      || ! chmod 0600 "$stage"; then
    rm -f -- "$stage"
    return 1
  fi
  if ! installed="$(owned_file_cas publish "$stage" "$receipt" \
      "$expected")"; then
    [ ! -e "$stage" ] \
      || echo "staged/prior $kind receipt retained at $stage" >&2
    return 1
  fi
  rm -f -- "$stage"
  [ -z "$output_variable" ] \
    || printf -v "$output_variable" '%s' "$installed"
}

retire_exact_receipt() {
  local receipt="$1" expected="$2" archive
  archive="$(mktemp "$(dirname "$receipt")/.${receipt##*/}.retired.XXXXXX")" \
    || return 1
  rm -f -- "$archive"
  owned_file_cas archive "$archive" "$receipt" "$expected" || return 1
  rm -f -- "$archive"
}

managed_receipt_matches() {
  local receipt="$1" kind="$2" target="$3"
  [ -f "$target" ] && [ ! -L "$target" ] \
    && [ -f "$receipt" ] && [ ! -L "$receipt" ] || return 1
  owned_metadata managed-file "$receipt" "$kind" "$target"
}

# A runtime `systemctl mask --user` is lower-precedence than a unit installed
# in ~/.config/systemd/user and therefore cannot stop that local unit from
# loading. Publish one exact runtime drop-in instead. Its structurally false
# condition blocks indirect activation and RefuseManualStart blocks explicit
# activation before service hooks can run.
brainstem_runtime_barrier_file() {
  python3 - "$1" "$XDG_RUNTIME_DIR" \
      "$BRAINSTEM_RUNTIME_BARRIER" <<'PY'
import ctypes
import errno
import os
import stat
import sys

action, runtime, barrier = sys.argv[1:]
if action not in {"state", "install", "retire", "restore", "discard",
                  "remove"}:
    raise SystemExit("invalid brainstem runtime barrier action")
if not runtime.startswith("/") or runtime == "/" \
        or os.path.realpath(runtime) != runtime:
    raise SystemExit("XDG_RUNTIME_DIR is not a canonical private directory")
runtime_info = os.lstat(runtime)
if not stat.S_ISDIR(runtime_info.st_mode) \
        or runtime_info.st_uid != os.geteuid() \
        or stat.S_IMODE(runtime_info.st_mode) != 0o700:
    raise SystemExit("XDG_RUNTIME_DIR is not a canonical private directory")
expected_barrier = os.path.join(
    runtime, "systemd", "user", "sia-brainstem.service.d",
    "sia-lifecycle-barrier.conf")
if barrier != expected_barrier:
    raise SystemExit("brainstem runtime barrier path is invalid")
active_name = "sia-lifecycle-barrier.conf"
retired_name = "sia-lifecycle-barrier.retired"

content = (
    "[Unit]\n"
    "RefuseManualStart=yes\n"
    "ConditionPathExists=\n"
    "ConditionPathExists=!/\n"
).encode("utf-8")
directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                   | getattr(os, "O_DIRECTORY", 0)
                   | getattr(os, "O_NOFOLLOW", 0))
read_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
              | getattr(os, "O_NOFOLLOW", 0)
              | getattr(os, "O_NONBLOCK", 0))


def generation(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
            info.st_gid, info.st_nlink, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns)


def child_directory(parent, name, create):
    try:
        descriptor = os.open(name, directory_flags, dir_fd=parent)
    except FileNotFoundError:
        if not create:
            return None
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
        except FileExistsError:
            pass
        descriptor = os.open(name, directory_flags, dir_fd=parent)
        os.fsync(parent)
    info = os.fstat(descriptor)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() \
            or stat.S_IMODE(info.st_mode) & 0o022:
        os.close(descriptor)
        raise ValueError(f"unsafe runtime systemd directory: {name}")
    return descriptor


def open_parent(create):
    descriptors = [os.open(runtime, directory_flags)]
    try:
        runtime_open = os.fstat(descriptors[0])
        if not stat.S_ISDIR(runtime_open.st_mode) \
                or runtime_open.st_uid != os.geteuid() \
                or stat.S_IMODE(runtime_open.st_mode) != 0o700:
            raise ValueError("XDG_RUNTIME_DIR changed during inspection")
        for name in ("systemd", "user", "sia-brainstem.service.d"):
            descriptor = child_directory(descriptors[-1], name, create)
            if descriptor is None:
                return None, descriptors
            descriptors.append(descriptor)
            if name == "user":
                try:
                    os.stat("sia-brainstem.service", dir_fd=descriptor,
                            follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError(
                        "foreign runtime sia-brainstem unit fragment exists")
        return descriptors[-1], descriptors
    except Exception:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def read_barrier(parent, name):
    try:
        descriptor = os.open(name, read_flags, dir_fd=parent)
    except FileNotFoundError:
        return None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() or before.st_nlink != 1 \
                or stat.S_IMODE(before.st_mode) != 0o644 \
                or before.st_size != len(content):
            raise ValueError("brainstem runtime barrier is foreign or unstable")
        chunks = []
        remaining = len(content) + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        observed = b"".join(chunks)
        after = os.fstat(descriptor)
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(after.st_mode) \
                or after.st_uid != os.geteuid() or after.st_nlink != 1 \
                or stat.S_IMODE(after.st_mode) != 0o644 \
                or generation(before) != generation(after) \
                or generation(after) != generation(current) \
                or observed != content or after.st_size != len(content):
            raise ValueError("brainstem runtime barrier is foreign or unstable")
        return generation(after)
    finally:
        os.close(descriptor)


def require_unchanged(parent, name, expected):
    current = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if generation(current) != expected:
        raise ValueError("brainstem runtime barrier changed before mutation")


def rename_noreplace(parent, source, target):
    libc = ctypes.CDLL(None, use_errno=True)
    operation = getattr(libc, "renameat2", None)
    if operation is None:
        raise OSError(errno.ENOSYS, "renameat2 is unavailable")
    operation.argtypes = [ctypes.c_int, ctypes.c_char_p,
                          ctypes.c_int, ctypes.c_char_p,
                          ctypes.c_uint]
    operation.restype = ctypes.c_int
    result = operation(parent, os.fsencode(source), parent,
                       os.fsencode(target), 1)
    if result != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), target)
    os.fsync(parent)


parent = None
descriptors = []
try:
    parent, descriptors = open_parent(action == "install")
    if parent is None:
        if action not in {"state", "discard", "remove"}:
            raise ValueError("brainstem runtime barrier directory is absent")
        print("absent")
        raise SystemExit(0)
    active = read_barrier(parent, active_name)
    retired = read_barrier(parent, retired_name)
    if active is not None and retired is not None:
        raise ValueError("active and retired brainstem barriers both exist")
    if action == "state":
        if active is not None:
            print("active")
        elif retired is not None:
            print("retired")
        else:
            print("absent")
    elif action == "install":
        if retired is not None:
            raise ValueError("retired brainstem barrier requires recovery")
        if active is None:
            flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_CLOEXEC", 0)
                     | getattr(os, "O_NOFOLLOW", 0))
            descriptor = os.open(active_name, flags, 0o644, dir_fd=parent)
            try:
                os.fchmod(descriptor, 0o644)
                view = memoryview(content)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise OSError("short brainstem runtime barrier write")
                    view = view[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.fsync(parent)
            read_barrier(parent, active_name)
        print("active")
    elif action == "retire":
        if active is None or retired is not None:
            raise ValueError("brainstem runtime barrier cannot be retired")
        require_unchanged(parent, active_name, active)
        rename_noreplace(parent, active_name, retired_name)
        read_barrier(parent, retired_name)
        print("retired")
    elif action == "restore":
        if retired is None or active is not None:
            raise ValueError("brainstem runtime barrier cannot be restored")
        require_unchanged(parent, retired_name, retired)
        rename_noreplace(parent, retired_name, active_name)
        read_barrier(parent, active_name)
        print("active")
    elif action == "discard":
        if active is not None:
            raise ValueError("active brainstem runtime barrier cannot be discarded")
        if retired is not None:
            require_unchanged(parent, retired_name, retired)
            os.unlink(retired_name, dir_fd=parent)
            os.fsync(parent)
        print("absent")
    else:
        if retired is not None:
            raise ValueError("retired brainstem runtime barrier requires recovery")
        if active is not None:
            require_unchanged(parent, active_name, active)
            os.unlink(active_name, dir_fd=parent)
            os.fsync(parent)
        print("absent")
finally:
    for descriptor in reversed(descriptors):
        os.close(descriptor)
PY
}

# Inspect one user unit through a single `show` query.  Unlike `is-active` and
# `is-enabled`, this distinguishes a genuinely absent/inactive unit from an
# unreachable user manager.  Callers must treat a refusal as fail-closed.
inspect_user_unit() {
  local unit="$1" prefix="$2" expected_drop_in_paths="${3:-}" output key count
  local load_state active_state fragment_path unit_file_state
  local drop_in_paths main_pid refuse_manual_start job
  if ! output="$(bounded_command_capture systemctl --user show "$unit" \
      --property=LoadState --property=ActiveState \
      --property=FragmentPath --property=UnitFileState \
      --property=DropInPaths --property=MainPID \
      --property=RefuseManualStart --property=Job)"; then
    printf '%s\n' "$output" >&2
    echo "could not inspect user service $unit" >&2
    return 1
  fi
  for key in LoadState ActiveState FragmentPath UnitFileState \
      DropInPaths MainPID RefuseManualStart Job; do
    count="$(printf '%s\n' "$output" | grep -c "^${key}=" || true)"
    [ "$count" = 1 ] || {
      echo "incomplete systemd inspection for $unit ($key)" >&2
      return 1
    }
  done
  load_state="$(printf '%s\n' "$output" | sed -n 's/^LoadState=//p')"
  active_state="$(printf '%s\n' "$output" | sed -n 's/^ActiveState=//p')"
  fragment_path="$(printf '%s\n' "$output" | sed -n 's/^FragmentPath=//p')"
  unit_file_state="$(printf '%s\n' "$output" | sed -n 's/^UnitFileState=//p')"
  drop_in_paths="$(printf '%s\n' "$output" | sed -n 's/^DropInPaths=//p')"
  main_pid="$(printf '%s\n' "$output" | sed -n 's/^MainPID=//p')"
  refuse_manual_start="$(printf '%s\n' "$output" | sed -n 's/^RefuseManualStart=//p')"
  job="$(printf '%s\n' "$output" | sed -n 's/^Job=//p')"
  case "$load_state" in loaded|not-found|masked) ;; *)
    echo "unsafe systemd load state for $unit: $load_state" >&2; return 1;;
  esac
  case "$active_state" in active|inactive|failed) ;; *)
    echo "transitional systemd active state for $unit: $active_state" >&2
    return 1;;
  esac
  case "$unit_file_state" in
    ""|disabled|enabled|enabled-runtime|masked-runtime) ;;
    *)
    echo "unsupported systemd enablement state for $unit: $unit_file_state" >&2
    return 1;;
  esac
  [ "$drop_in_paths" = "$expected_drop_in_paths" ] || {
    echo "unexpected systemd drop-ins for $unit: $drop_in_paths" >&2
    return 1
  }
  [[ "$main_pid" =~ ^[0-9]+$ ]] || {
    echo "invalid systemd MainPID for $unit" >&2
    return 1
  }
  [ -z "$job" ] || {
    echo "systemd job is still pending for $unit: $job" >&2
    return 1
  }
  if [ -n "$expected_drop_in_paths" ]; then
    [ "$refuse_manual_start" = yes ] || {
      echo "systemd start refusal is not armed for $unit" >&2
      return 1
    }
  else
    [ "$refuse_manual_start" = no ] || {
      echo "unexpected systemd start refusal for $unit" >&2
      return 1
    }
  fi
  printf -v "${prefix}_LOAD_STATE" '%s' "$load_state"
  printf -v "${prefix}_ACTIVE_STATE" '%s' "$active_state"
  printf -v "${prefix}_FRAGMENT_PATH" '%s' "$fragment_path"
  printf -v "${prefix}_UNIT_FILE_STATE" '%s' "$unit_file_state"
  printf -v "${prefix}_DROP_IN_PATHS" '%s' "$drop_in_paths"
  printf -v "${prefix}_MAIN_PID" '%s' "$main_pid"
  printf -v "${prefix}_REFUSE_MANUAL_START" '%s' "$refuse_manual_start"
  printf -v "${prefix}_JOB" '%s' "$job"
}

write_stable_generation_launcher() {
  local target="$1"
  python3 - "$target" <<'PY'
import os
import sys

path = sys.argv[1]
source = r'''#!/usr/bin/env python3
"""Stable SIA launcher: pin one runtime generation before opening Python."""

import fcntl
import os
import stat
import sys

_ABI = "sia-launch-v1"


def _refuse(message):
    print(f"{os.path.basename(sys.argv[0])}: refused: {message}",
          file=sys.stderr)
    raise SystemExit(1)


def _main():
    home = os.path.abspath(os.path.expanduser("~"))
    launcher = os.path.basename(os.path.abspath(sys.argv[0]))
    runtime = os.path.join(home, ".local", "share", "sia", "bin")
    if launcher == "sia":
        target = os.path.join(runtime, "sia-cli")
    elif launcher == "sia-brainstem":
        target = os.path.join(runtime, "sia-brainstem.py")
    else:
        _refuse("unexpected launcher name")

    state_parent = os.path.join(home, ".local", "state")
    lock = os.path.join(state_parent, "sia.lifecycle.lock")
    tombstone = os.path.join(state_parent, "sia.lifecycle-removed")
    os.makedirs(state_parent, exist_ok=True)
    lock_flags = (os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
                  | getattr(os, "O_NOFOLLOW", 0))
    try:
        lifecycle_fd = os.open(lock, lock_flags, 0o600)
    except OSError as exc:
        _refuse(f"could not open lifecycle lease: {exc}")
    try:
        lifecycle = os.fstat(lifecycle_fd)
        if not stat.S_ISREG(lifecycle.st_mode) \
                or lifecycle.st_uid != os.geteuid():
            _refuse("lifecycle lease is not an owned regular file")
        os.fchmod(lifecycle_fd, 0o600)
        fcntl.flock(lifecycle_fd, fcntl.LOCK_SH)
        if os.path.lexists(tombstone):
            marker = os.lstat(tombstone)
            if not stat.S_ISREG(marker.st_mode) \
                    or marker.st_uid != os.geteuid():
                _refuse("lifecycle removal marker is unsafe")
            _refuse("SIA runtime was removed; reinstall before using it")

        target_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                        | getattr(os, "O_NOFOLLOW", 0))
        try:
            target_fd = os.open(target, target_flags)
        except OSError as exc:
            _refuse(f"could not open the pinned runtime target: {exc}")
        target_info = os.fstat(target_fd)
        current = os.lstat(target)
        if not stat.S_ISREG(target_info.st_mode) \
                or target_info.st_uid != os.geteuid() \
                or not stat.S_ISREG(current.st_mode) \
                or current.st_uid != os.geteuid() \
                or (target_info.st_dev, target_info.st_ino) != \
                   (current.st_dev, current.st_ino):
            _refuse("runtime target is not the exact owned regular file")

        os.set_inheritable(lifecycle_fd, True)
        os.set_inheritable(target_fd, True)
        environment = dict(os.environ)
        environment.pop("SIA_INHERITED_LIFECYCLE_FD", None)
        environment["SIA_LAUNCHER_ABI"] = _ABI
        environment["SIA_LAUNCHER_LIFECYCLE_FD"] = str(lifecycle_fd)
        environment["SIA_LAUNCHER_TARGET_FD"] = str(target_fd)
        environment["SIA_LAUNCHER_TARGET_PATH"] = target
        os.execve(sys.executable,
                  [sys.executable, target, *sys.argv[1:]], environment)
    except (OSError, RuntimeError, ValueError) as exc:
        _refuse(str(exc))


if __name__ == "__main__":
    _main()
'''
flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
         | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
descriptor = os.open(path, flags, 0o700)
try:
    os.write(descriptor, source.encode("utf-8"))
    os.fchmod(descriptor, 0o755)
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
}

preflight_owned_file() {
  local source="$1" target="$2" receipt="$3" kind="$4" consent_var="$5"
  local output_variable="${6:-}" expected
  if [ -e "$target" ] || [ -L "$target" ]; then
    if [ ! -f "$target" ] || [ -L "$target" ]; then
      echo "refusing unsafe managed $kind path: $target" >&2
      return 1
    fi
    if fenced_managed_file_authorized "$receipt" "$kind" "$target" \
        || managed_receipt_matches "$receipt" "$kind" "$target" \
        || { owned_metadata same-content "$source" "$target" \
             && [ ! -e "$receipt" ] && [ ! -L "$receipt" ]; } \
        || [ "${!consent_var:-0}" = "1" ]; then
      expected="$(owned_metadata generation "$target")" || return 1
      [ -z "$output_variable" ] \
        || printf -v "$output_variable" '%s' "$expected"
      return 0
    fi
    echo "existing $kind is unowned or locally modified; preserved" >&2
    echo "explicit replacement requires $consent_var=1 ./install.sh" >&2
    return 1
  fi
  if [ -e "$receipt" ] || [ -L "$receipt" ]; then
    echo "stale or unsafe $kind ownership receipt; refusing install" >&2
    return 1
  fi
  [ -z "$output_variable" ] \
    || printf -v "$output_variable" '%s' absent
}

retain_unowned_cli_before_fence() {
  local backup
  if [ ! -e "$CLI_PATH" ] && [ ! -L "$CLI_PATH" ]; then
    return 0
  fi
  if fenced_managed_file_authorized \
      "$CLI_RECEIPT" sia-cli "$CLI_PATH" \
      || managed_receipt_matches "$CLI_RECEIPT" sia-cli "$CLI_PATH"; then
    return 0
  fi
  if owned_metadata same-content "$SIA_STABLE_LAUNCHER" "$CLI_PATH" \
      && [ ! -e "$CLI_RECEIPT" ] && [ ! -L "$CLI_RECEIPT" ]; then
    return 0
  fi
  [ "${SIA_REPLACE_SIA_CLI:-0}" = 1 ] || return 1
  backup="$(mktemp "$(dirname "$CLI_PATH")/.sia-cli.previous.XXXXXX")" \
    || return 1
  cp -a -- "$CLI_PATH" "$backup"
  echo "  previous sia-cli retained at $backup"
}

install_preflighted_cli() {
  local current installed receipt_installed
  current="$(owned_metadata digest "$SIA_STABLE_LAUNCHER")" || return 1
  installed="$(atomic_install_file "$SIA_STABLE_LAUNCHER" "$CLI_PATH" \
    0755 "$SIA_CLI_EXPECTED")" || return 1
  if [ "$(owned_metadata generation "$CLI_PATH" 2>/dev/null || true)" \
      != "$installed" ]; then
    echo "sia-cli changed after generation-bound installation" >&2
    return 1
  fi
  write_managed_receipt "$CLI_RECEIPT" sia-cli "$CLI_PATH" "$current" \
    receipt_installed || return 1
  if [ "$(owned_metadata generation "$CLI_PATH" 2>/dev/null || true)" \
      != "$installed" ]; then
    retire_exact_receipt "$CLI_RECEIPT" "$receipt_installed" || true
    echo "sia-cli changed across receipt publication; receipt retired" >&2
    return 1
  fi
}

install_owned_file() {
  local source="$1" target="$2" mode="$3" receipt="$4" kind="$5"
  local consent_var="$6" legacy_digest="${7:-}" current backup expected installed
  local receipt_installed
  if [ -e "$target" ] || [ -L "$target" ]; then
    if [ ! -f "$target" ] || [ -L "$target" ]; then
      echo "refusing unsafe managed $kind path: $target" >&2
      return 1
    fi
    current="$(owned_metadata digest "$target")" || return 1
    if managed_receipt_matches "$receipt" "$kind" "$target"; then
      :
    elif owned_metadata same-content "$source" "$target" \
        && { [ ! -e "$receipt" ] && [ ! -L "$receipt" ]; }; then
      echo "  adopted exact unmarked $kind"
    elif [ -n "$legacy_digest" ] && [ "$current" = "$legacy_digest" ]; then
      echo "  adopted byte-exact legacy $kind"
    elif [ "${!consent_var:-0}" = "1" ]; then
      backup="$(mktemp "$(dirname "$target")/.${kind}.previous.XXXXXX")"
      cp -a -- "$target" "$backup"
      echo "  previous $kind retained at $backup"
    else
      echo "existing $kind is unowned or locally modified; preserved" >&2
      echo "explicit replacement requires $consent_var=1 ./install.sh" >&2
      return 1
    fi
    expected="$(owned_metadata generation "$target")" || return 1
  elif [ -e "$receipt" ] || [ -L "$receipt" ]; then
    echo "stale or unsafe $kind ownership receipt; refusing install" >&2
    return 1
  else
    expected=absent
  fi
  current="$(owned_metadata digest "$source")" || return 1
  installed="$(atomic_install_file "$source" "$target" "$mode" \
    "$expected")" || return 1
  if [ "$(owned_metadata generation "$target" 2>/dev/null || true)" \
      != "$installed" ]; then
    echo "$kind changed after generation-bound installation" >&2
    return 1
  fi
  write_managed_receipt "$receipt" "$kind" "$target" "$current" \
    receipt_installed || return 1
  if [ "$(owned_metadata generation "$target" 2>/dev/null || true)" \
      != "$installed" ]; then
    retire_exact_receipt "$receipt" "$receipt_installed" || true
    echo "$kind changed across receipt publication; receipt retired" >&2
    return 1
  fi
}

acquire_owner_lock() {
  local path="$1" variable="$2" label="$3" descriptor attempt
  if [ -L "$path" ] || { [ -e "$path" ] && [ ! -f "$path" ]; }; then
    echo "refusing unsafe $label lock: $path" >&2
    return 1
  fi
  exec {descriptor}>>"$path"
  chmod 0600 "$path"
  echo "  waiting within a bounded window for $label quiescence"
  for ((attempt = 1; attempt <= SIA_LIFECYCLE_ACQUIRE_ATTEMPTS; attempt++)); do
    if flock -n "$descriptor"; then
      printf -v "$variable" '%s' "$descriptor"
      return 0
    fi
    quiesce_install_brainstem_for_lifecycle || {
      eval "exec ${descriptor}>&-"
      return 1
    }
    if [ "$attempt" -lt "$SIA_LIFECYCLE_ACQUIRE_ATTEMPTS" ]; then
      sleep 1
    fi
  done
  eval "exec ${descriptor}>&-"
  echo "$label did not become quiescent" >&2
  return 1
}

prepare_and_lock_install() {
  assert_safe_managed_roots \
    "$HOME/.local" "$HOME/.local/share" "$SHARE" "$SHARE/corpus" \
    "$SHARE/.gbrain" "$SHARE/.gbrain/schema-packs" \
    "$SHARE/.gbrain/schema-packs/sia-pack" \
    "$BINDIR" "$MANAGED_DIR" "$STATE/managed-mcp" \
    "$STATE/mcp-consumer-guards" \
    "$HOME/.local/state" "$STATE" "$HOME/.local/bin" \
    "$STATE/model-manifest-backups" \
    "$HOME/.config" "$CONFIG_DIR" "$HOME/.config/systemd" \
    "$SYSTEMD_USER_DIR" "$HOME/.config/hypr" \
    "$HOME/.config/omarchy" "$HOME/.config/omarchy/plugins" \
    "$HOME/.config/omarchy/plugins/khephri.sia" \
    "$HOME/.claude" "$HOME/.claude/skills" \
    "$HOME/.claude/skills/sia" "$HOME/opt" "$TOOLCHAIN"
  # The external administration lease serializes all managed-root creation
  # against purge. Only its retained parent may be prepared before the lock.
  mkdir -p "$HOME/.local/state"
  if [ -L "$LIFECYCLE_ADMIN_LOCK" ] \
      || { [ -e "$LIFECYCLE_ADMIN_LOCK" ] \
           && [ ! -f "$LIFECYCLE_ADMIN_LOCK" ]; }; then
    echo "refusing unsafe installer administration lease path" >&2
    return 1
  fi
  exec {SIA_INSTALL_ADMIN_LOCK_FD}>>"$LIFECYCLE_ADMIN_LOCK"
  chmod 0600 "$LIFECYCLE_ADMIN_LOCK"
  flock -n "$SIA_INSTALL_ADMIN_LOCK_FD" || {
    echo "another SIA install or uninstall is active" >&2
    return 1
  }
  mkdir -p "$SHARE" "$STATE" "$MANAGED_DIR" "$HOME/.local/bin" \
    "$CONFIG_DIR" "$SYSTEMD_USER_DIR" "$HOME/opt" "$TOOLCHAIN"
  assert_safe_managed_roots \
    "$SHARE" "$SHARE/.gbrain" "$SHARE/.gbrain/schema-packs" \
    "$SHARE/.gbrain/schema-packs/sia-pack" \
    "$STATE" "$STATE/model-manifest-backups" "$MANAGED_DIR" \
    "$STATE/managed-mcp" "$STATE/mcp-consumer-guards" \
    "$HOME/.local/bin" \
    "$CONFIG_DIR" "$SYSTEMD_USER_DIR" "$HOME/.config/hypr" \
    "$HOME/.config/omarchy" "$HOME/.config/omarchy/plugins" \
    "$HOME/.config/omarchy/plugins/khephri.sia" \
    "$HOME/.claude" "$HOME/.claude/skills" \
    "$HOME/.claude/skills/sia" "$HOME/opt" "$TOOLCHAIN"
  if [ -L "$LIFECYCLE_TOMBSTONE" ] \
      || { [ -e "$LIFECYCLE_TOMBSTONE" ] \
           && [ ! -f "$LIFECYCLE_TOMBSTONE" ]; }; then
    echo "refusing unsafe lifecycle removal marker" >&2
    return 1
  fi
  if [ -e "$LIFECYCLE_TOMBSTONE" ]; then
    SIA_RESTORE_LIFECYCLE_TOMBSTONE=1
  fi
}

verify_install_brainstem_runtime_barrier() {
  local barrier_state
  barrier_state="$(brainstem_runtime_barrier_file state)" || return 1
  [ "$barrier_state" = active ] || {
    echo "sia-brainstem runtime barrier is not active" >&2
    return 1
  }
  inspect_user_unit sia-brainstem.service BRAINSTEM_BARRIER \
    "$BRAINSTEM_RUNTIME_BARRIER" || return 1
  if [ "$BRAINSTEM_BARRIER_LOAD_STATE" != loaded ] \
      || [ "$BRAINSTEM_BARRIER_ACTIVE_STATE" != inactive ] \
      || [ "$BRAINSTEM_BARRIER_FRAGMENT_PATH" != "$BRAINSTEM_UNIT" ] \
      || [ "$BRAINSTEM_BARRIER_MAIN_PID" != 0 ]; then
    echo "sia-brainstem.service runtime barrier did not verify" >&2
    return 1
  fi
  case "$BRAINSTEM_BARRIER_UNIT_FILE_STATE" in
    disabled|enabled|enabled-runtime) ;;
    *)
      echo "sia-brainstem.service has an unsafe barrier enablement state" >&2
      return 1
      ;;
  esac
}

install_brainstem_runtime_barrier() {
  local barrier_state
  SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED=1
  barrier_state="$(brainstem_runtime_barrier_file state)" || return 1
  case "$barrier_state" in
    active) ;;
    retired)
      brainstem_runtime_barrier_file restore >/dev/null || return 1
      ;;
    absent)
      brainstem_runtime_barrier_file install >/dev/null || return 1
      ;;
    *) return 1 ;;
  esac
  run_with_deadline 120 systemctl --user daemon-reload || return 1
  if [ -e "$BRAINSTEM_UNIT" ] || [ -L "$BRAINSTEM_UNIT" ]; then
    run_with_deadline 120 systemctl --user stop \
      sia-brainstem.service || return 1
    run_with_deadline 120 systemctl --user reset-failed \
      sia-brainstem.service >/dev/null 2>&1 || true
    verify_install_brainstem_runtime_barrier
  else
    inspect_user_unit sia-brainstem.service BRAINSTEM_ORPHAN || return 1
    [ "$BRAINSTEM_ORPHAN_LOAD_STATE" = not-found ] \
      && [ "$BRAINSTEM_ORPHAN_ACTIVE_STATE" = inactive ] \
      && [ -z "$BRAINSTEM_ORPHAN_FRAGMENT_PATH" ] \
      && [ "$BRAINSTEM_ORPHAN_MAIN_PID" = 0 ]
  fi
}

remove_install_brainstem_runtime_barrier() {
  local barrier_state restore_failed=0
  if [ "$SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED" -ne 1 ]; then
    return 0
  fi
  barrier_state="$(brainstem_runtime_barrier_file state)" || return 1
  [ "$barrier_state" = active ] || return 1
  SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED=0
  if brainstem_runtime_barrier_file retire >/dev/null \
      && run_with_deadline 120 systemctl --user daemon-reload \
      && inspect_user_unit sia-brainstem.service BRAINSTEM_UNBARRIERED \
      && [ "$BRAINSTEM_UNBARRIERED_LOAD_STATE" = loaded ] \
      && [ "$BRAINSTEM_UNBARRIERED_ACTIVE_STATE" = inactive ] \
      && [ "$BRAINSTEM_UNBARRIERED_FRAGMENT_PATH" = "$BRAINSTEM_UNIT" ] \
      && [ "$BRAINSTEM_UNBARRIERED_MAIN_PID" = 0 ] \
      && brainstem_runtime_barrier_file discard >/dev/null; then
    return 0
  fi
  barrier_state="$(brainstem_runtime_barrier_file state)" || return 1
  case "$barrier_state" in
    retired)
      brainstem_runtime_barrier_file restore >/dev/null || restore_failed=1
      ;;
    active) ;;
    *) restore_failed=1 ;;
  esac
  SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED=1
  run_with_deadline 120 systemctl --user daemon-reload \
    >/dev/null 2>&1 || restore_failed=1
  if [ "$restore_failed" -eq 0 ]; then
    verify_install_brainstem_runtime_barrier >/dev/null 2>&1 \
      || restore_failed=1
  fi
  [ "$restore_failed" -eq 0 ] || \
    echo "WARNING: installer start barrier recovery did not verify" >&2
  return 1
}

retire_install_brainstem_runtime_barrier() {
  # Set the recovery markers before the atomic rename. EXIT can then restore
  # either side of a failure at every point in final activation.
  SIA_BRAINSTEM_FINAL_UNBARRIERED=1
  SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED=0
  brainstem_runtime_barrier_file retire >/dev/null || return 1
  run_with_deadline 120 systemctl --user daemon-reload || return 1
  inspect_user_unit sia-brainstem.service BRAINSTEM_UNBARRIERED || return 1
  [ "$BRAINSTEM_UNBARRIERED_LOAD_STATE" = loaded ] \
    && [ "$BRAINSTEM_UNBARRIERED_ACTIVE_STATE" = inactive ] \
    && [ "$BRAINSTEM_UNBARRIERED_FRAGMENT_PATH" = "$BRAINSTEM_UNIT" ] \
    && [ "$BRAINSTEM_UNBARRIERED_MAIN_PID" = 0 ]
}

discard_install_brainstem_retired_barrier() {
  brainstem_runtime_barrier_file discard >/dev/null
}

inspect_install_brainstem_for_lifecycle() {
  local prefix="$1" expected_drop_in_paths=""
  local load_var active_var fragment_var unit_state_var main_pid_var
  if [ "$SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED" -eq 1 ] \
      && [ "$SIA_BRAINSTEM_BARRIER_DEFERRED" -eq 0 ]; then
    expected_drop_in_paths="$BRAINSTEM_RUNTIME_BARRIER"
  fi
  inspect_user_unit sia-brainstem.service "$prefix" \
    "$expected_drop_in_paths" || return 1
  load_var="${prefix}_LOAD_STATE"
  active_var="${prefix}_ACTIVE_STATE"
  fragment_var="${prefix}_FRAGMENT_PATH"
  unit_state_var="${prefix}_UNIT_FILE_STATE"
  main_pid_var="${prefix}_MAIN_PID"
  SIA_LIFECYCLE_SERVICE_EXACT=0
  if [ "${!load_var}" = not-found ]; then
    if [ "${!active_var}" != inactive ] || [ -n "${!fragment_var}" ] \
        || [ -n "${!unit_state_var}" ] || [ "${!main_pid_var}" != 0 ]; then
      echo "sia-brainstem.service changed to an unsafe absent state" >&2
      return 1
    fi
    return 0
  fi
  if [ "${!load_var}" != loaded ] \
      || [ "${!fragment_var}" != "$BRAINSTEM_UNIT" ] \
      || [ ! -f "$BRAINSTEM_UNIT" ] || [ -L "$BRAINSTEM_UNIT" ]; then
    echo "sia-brainstem.service changed outside SIA's managed unit" >&2
    return 1
  fi
  if owned_metadata same-content \
      "$REPO/systemd/sia-brainstem.service" "$BRAINSTEM_UNIT" \
      || managed_receipt_matches "$BRAINSTEM_RECEIPT" \
        brainstem-unit "$BRAINSTEM_UNIT"; then
    SIA_LIFECYCLE_SERVICE_EXACT=1
  elif [ "${SIA_REPLACE_BRAINSTEM_UNIT:-0}" != 1 ]; then
    echo "sia-brainstem.service changed to an unowned unit" >&2
    return 1
  fi
}

quiesce_install_brainstem_for_lifecycle() {
  if [ "$SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED" -eq 1 ] \
      && [ "$SIA_BRAINSTEM_BARRIER_DEFERRED" -eq 0 ]; then
    verify_install_brainstem_runtime_barrier
    return
  fi
  inspect_install_brainstem_for_lifecycle BRAINSTEM_HANDOFF || return 1
  if [ "$BRAINSTEM_HANDOFF_LOAD_STATE" != loaded ] \
      || { [ "$BRAINSTEM_HANDOFF_ACTIVE_STATE" != active ] \
           && [ "$BRAINSTEM_HANDOFF_MAIN_PID" = 0 ]; }; then
    return 0
  fi
  if [ "$SIA_LIFECYCLE_SERVICE_EXACT" -ne 1 ]; then
    echo "refusing to stop an active unowned sia-brainstem.service" >&2
    return 1
  fi
  SIA_BRAINSTEM_WAS_ACTIVE=1
  run_with_deadline 120 systemctl --user stop \
    sia-brainstem.service || return 1
  inspect_install_brainstem_for_lifecycle BRAINSTEM_QUIESCED || return 1
  if [ "$BRAINSTEM_QUIESCED_LOAD_STATE" = loaded ] \
      && { [ "$BRAINSTEM_QUIESCED_ACTIVE_STATE" != inactive ] \
           || [ "$BRAINSTEM_QUIESCED_MAIN_PID" != 0 ]; }; then
    echo "sia-brainstem.service did not become inactive" >&2
    return 1
  fi
}

acquire_install_lifecycle() {
  local attempt
  if [ -L "$LIFECYCLE_LOCK" ] \
      || { [ -e "$LIFECYCLE_LOCK" ] && [ ! -f "$LIFECYCLE_LOCK" ]; }; then
    echo "refusing unsafe installer lifecycle lease path" >&2
    return 1
  fi
  exec {SIA_INSTALL_LOCK_FD}>>"$LIFECYCLE_LOCK"
  chmod 0600 "$LIFECYCLE_LOCK"
  echo "  waiting within a bounded window for active SIA clients"
  for ((attempt = 1; attempt <= SIA_LIFECYCLE_ACQUIRE_ATTEMPTS; attempt++)); do
    if flock -n "$SIA_INSTALL_LOCK_FD"; then
      # A pre-lifecycle runtime may not have held the lease. Reinspect and
      # quiesce it even after acquisition before any managed byte changes.
      quiesce_install_brainstem_for_lifecycle || return 1
      return 0
    fi
    quiesce_install_brainstem_for_lifecycle || return 1
    if [ "$attempt" -lt "$SIA_LIFECYCLE_ACQUIRE_ATTEMPTS" ]; then
      sleep 1
    fi
  done
  echo "active SIA clients did not leave the runtime generation" >&2
  return 1
}

legacy_launchers_quiescent() {
  python3 - "$CLI_PATH" "$BINDIR/sia-brainstem" \
      "$BINDIR/sia-mcp" "$BINDIR/sia-cli" \
      "$BINDIR/sia-brainstem.py" <<'PY'
import os
import sys

uid = os.geteuid()
probe_pid = os.getpid()
managed = frozenset(os.path.abspath(path) for path in sys.argv[1:])
found = []
for entry in os.scandir("/proc"):
    if not entry.name.isdigit() or int(entry.name) == probe_pid:
        continue
    try:
        if entry.stat(follow_symlinks=False).st_uid != uid:
            continue
        cwd = os.readlink(os.path.join(entry.path, "cwd"))
        with open(os.path.join(entry.path, "cmdline"), "rb") as stream:
            arguments = [os.fsdecode(value) for value in
                         stream.read().rstrip(b"\0").split(b"\0") if value]
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        continue
    resolved = [(value, os.path.abspath(
        value if os.path.isabs(value) else os.path.join(cwd, value)))
        for value in arguments]
    matches = [value for value, path in resolved if path in managed]
    if matches:
        found.append((int(entry.name), matches[0]))
if found:
    for pid, path in sorted(found):
        print(f"legacy SIA launcher still loaded: pid={pid} path={path}",
              file=sys.stderr)
    raise SystemExit(1)
PY
}

drain_legacy_launchers() {
  local attempt
  echo "  waiting within a bounded window for legacy launchers"
  for ((attempt = 1; attempt <= SIA_LIFECYCLE_ACQUIRE_ATTEMPTS; attempt++)); do
    if legacy_launchers_quiescent; then
      return 0
    fi
    quiesce_install_brainstem_for_lifecycle || return 1
    if [ "$attempt" -lt "$SIA_LIFECYCLE_ACQUIRE_ATTEMPTS" ]; then
      sleep 1
    fi
  done
  echo "legacy SIA launchers did not become quiescent" >&2
  return 1
}

durable_fixed_metadata_stage() {
  python3 - "$1" "$2" <<'PY'
import os
import stat
import sys

path = os.path.abspath(sys.argv[1])
content = sys.argv[2].encode("utf-8", "strict") + b"\n"
if b"\0" in content:
    raise ValueError("metadata stage contains NUL")
parent = os.path.dirname(path)
name = os.path.basename(path)
directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                   | getattr(os, "O_DIRECTORY", 0)
                   | getattr(os, "O_NOFOLLOW", 0))
file_flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
              | getattr(os, "O_CLOEXEC", 0)
              | getattr(os, "O_NOFOLLOW", 0))
parent_fd = os.open(parent, directory_flags)
try:
    parent_info = os.fstat(parent_fd)
    if not stat.S_ISDIR(parent_info.st_mode) \
            or parent_info.st_uid != os.geteuid():
        raise ValueError("unsafe metadata stage parent")
    descriptor = os.open(name, file_flags, 0o600, dir_fd=parent_fd)
    try:
        remaining = memoryview(content)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("short fixed metadata stage write")
            remaining = remaining[written:]
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.fsync(parent_fd)
finally:
    os.close(parent_fd)
PY
}

remove_owned_fixed_metadata() {
  python3 - "$1" <<'PY'
import os
import stat
import sys

path = os.path.abspath(sys.argv[1])
parent = os.path.dirname(path)
name = os.path.basename(path)
directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                   | getattr(os, "O_DIRECTORY", 0)
                   | getattr(os, "O_NOFOLLOW", 0))
file_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
              | getattr(os, "O_NOFOLLOW", 0)
              | getattr(os, "O_NONBLOCK", 0))
parent_fd = os.open(parent, directory_flags)
try:
    descriptor = os.open(name, file_flags, dir_fd=parent_fd)
    try:
        before = os.fstat(descriptor)
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() or before.st_nlink != 1 \
                or stat.S_IMODE(before.st_mode) != 0o600 \
                or (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns) != (
                    current.st_dev, current.st_ino, current.st_size,
                    current.st_mtime_ns, current.st_ctime_ns):
            raise ValueError("fixed metadata retirement target changed")
        os.unlink(name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(descriptor)
finally:
    os.close(parent_fd)
PY
}

safe_corpus_git() {
  run_with_deadline 300 env \
    -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
    -u GIT_OBJECT_DIRECTORY -u GIT_ALTERNATE_OBJECT_DIRECTORIES \
    -u GIT_CONFIG_PARAMETERS -u GIT_CONFIG_COUNT -u GIT_TEMPLATE_DIR \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_ATTR_NOSYSTEM=1 \
    git -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c commit.gpgsign=false "$@"
}

bounded_corpus_git() {
  bounded_command_capture env \
    -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
    -u GIT_OBJECT_DIRECTORY -u GIT_ALTERNATE_OBJECT_DIRECTORIES \
    -u GIT_CONFIG_PARAMETERS -u GIT_CONFIG_COUNT -u GIT_TEMPLATE_DIR \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_ATTR_NOSYSTEM=1 \
    git -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c commit.gpgsign=false "$@"
}

corpus_bootstrap_initial_state() {
  python3 - "$SHARE/corpus" <<'PY'
import os
import stat
import sys

target = os.path.abspath(sys.argv[1])
parent = os.path.dirname(target)
name = os.path.basename(target)
directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                   | getattr(os, "O_DIRECTORY", 0)
                   | getattr(os, "O_NOFOLLOW", 0))


def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_nlink, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns)


parent_fd = os.open(parent, directory_flags)
try:
    before_parent = os.fstat(parent_fd)
    if not stat.S_ISDIR(before_parent.st_mode) \
            or before_parent.st_uid != os.geteuid():
        raise ValueError("unsafe corpus parent")
    try:
        root_fd = os.open(name, directory_flags, dir_fd=parent_fd)
    except FileNotFoundError:
        if os.path.lexists(target):
            raise ValueError("unsafe corpus root")
        after_parent = os.fstat(parent_fd)
        current_parent = os.stat(parent, follow_symlinks=False)
        if generation(before_parent) != generation(after_parent) \
                or generation(after_parent) != generation(current_parent):
            raise ValueError("corpus parent changed during absent capture")
        print("absent")
        raise SystemExit(0)
    try:
        before = os.fstat(root_fd)
        if not stat.S_ISDIR(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or stat.S_IMODE(before.st_mode) & 0o022:
            raise ValueError("unsafe empty corpus root")
        with os.scandir(root_fd) as entries:
            if next(entries, None) is not None:
                raise ValueError("corpus is no longer empty")
        after = os.fstat(root_fd)
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise ValueError("empty corpus changed during capture")
        print("empty:" + ":".join(str(value) for value in generation(before)))
    finally:
        os.close(root_fd)
finally:
    os.close(parent_fd)
PY
}

corpus_bootstrap_intent_fields() {
  local record="${1:-$CORPUS_BOOTSTRAP_INTENT}"
  python3 - "$record" "$SHARE/corpus" <<'PY'
import os
import re
import stat
import sys

intent = os.path.abspath(sys.argv[1])
target = os.path.abspath(sys.argv[2])
# This reuses the established exact metadata ceiling. It is a resource bound,
# not a formal or code-correctness claim.
MAX_INTENT_BYTES = 65_536
file_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
              | getattr(os, "O_NOFOLLOW", 0)
              | getattr(os, "O_NONBLOCK", 0))


def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_nlink, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns)


def stable_file(path, label, ceiling):
    descriptor = os.open(path, file_flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_nlink != 1 or before.st_size > ceiling \
                or stat.S_IMODE(before.st_mode) & 0o022:
            raise ValueError(f"unsafe {label}")
        chunks = []
        remaining = ceiling + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        if len(content) != before.st_size or len(content) > ceiling \
                or generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise ValueError(f"{label} changed while inspected")
        return content
    finally:
        os.close(descriptor)


raw = stable_file(intent, "corpus bootstrap intent", MAX_INTENT_BYTES)
try:
    text = raw.decode("utf-8", "strict")
except UnicodeError as error:
    raise ValueError("corpus bootstrap intent is not strict UTF-8") from error
pattern = re.compile(
    r"managed-by=khephri[.]sia\nkind=corpus-bootstrap-v2\npath="
    + re.escape(target)
    + r"\ninitial=(absent|empty:(?:[0-9]+:){7}[0-9]+)"
      r"\nphase=(prepared|publishing|published|existing)"
      r"\ntree=(absent|tree:(?:[0-9]+:){8}[0-9a-f]{64})\n")
matched = pattern.fullmatch(text)
if matched is None:
    raise ValueError("corpus bootstrap intent bytes are not exact")
initial, phase, tree = matched.groups()
if initial == "absent":
    if phase == "prepared":
        if tree != "absent":
            raise ValueError("prepared corpus bootstrap has a tree token")
    elif phase in {"publishing", "published"}:
        if tree == "absent":
            raise ValueError("published corpus bootstrap lacks a tree token")
    else:
        raise ValueError("absent corpus bootstrap has an invalid phase")
elif phase != "existing" or tree != "absent":
    raise ValueError("existing corpus bootstrap has an invalid phase")
print("\t".join((initial, phase, tree)))
PY
}

corpus_bootstrap_stage_empty() {
  local stage="${CORPUS_BOOTSTRAP_STAGE:-$SHARE/.corpus-bootstrap-tree}"
  python3 - "$stage" <<'PY'
import os
import stat
import sys

stage = os.path.abspath(sys.argv[1])
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
descriptor = os.open(stage, flags)
try:
    before = os.fstat(descriptor)
    if not stat.S_ISDIR(before.st_mode) \
            or before.st_uid != os.geteuid() \
            or stat.S_IMODE(before.st_mode) != 0o700:
        raise ValueError("corpus bootstrap stage is unsafe")
    with os.scandir(descriptor) as entries:
        if next(entries, None) is not None:
            raise ValueError("corpus bootstrap stage is not empty")
    after = os.fstat(descriptor)
    current = os.stat(stage, follow_symlinks=False)
    identity = lambda value: (
        value.st_dev, value.st_ino, value.st_mode, value.st_uid,
        value.st_nlink, value.st_size, value.st_mtime_ns,
        value.st_ctime_ns)
    if identity(before) != identity(after) \
            or identity(after) != identity(current):
        raise ValueError("corpus bootstrap stage changed while inspected")
finally:
    os.close(descriptor)
PY
}

corpus_bootstrap_prefix_state() {
  local initial="$1" phase="$2" tree="$3"
  python3 - "$SHARE/corpus" \
      "# SIA corpus — this machine's memory" \
      "$initial" "$phase" "$tree" <<'PY'
import os
import re
import stat
import sys

target = os.path.abspath(sys.argv[1])
expected_readme, initial, phase, tree = sys.argv[2:]
MAX_INTENT_BYTES = 65_536
directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                   | getattr(os, "O_DIRECTORY", 0)
                   | getattr(os, "O_NOFOLLOW", 0))
file_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
              | getattr(os, "O_NOFOLLOW", 0)
              | getattr(os, "O_NONBLOCK", 0))


def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_nlink, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns)


def stable_file(path, label, ceiling):
    descriptor = os.open(path, file_flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_nlink != 1 or before.st_size > ceiling \
                or stat.S_IMODE(before.st_mode) & 0o022:
            raise ValueError(f"unsafe {label}")
        chunks = []
        remaining = ceiling + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        if len(content) != before.st_size or len(content) > ceiling \
                or generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise ValueError(f"{label} changed while inspected")
        return content
    finally:
        os.close(descriptor)


def expected_root_identity():
    if initial.startswith("empty:"):
        fields = initial.removeprefix("empty:").split(":")
    elif phase in {"publishing", "published"}:
        fields = tree.removeprefix("tree:").split(":")
    else:
        return None
    if len(fields) < 4 or any(re.fullmatch(r"[0-9]+", item) is None
                              for item in fields[:4]):
        raise ValueError("corpus bootstrap root identity is malformed")
    return tuple(int(item) for item in fields[:4])

try:
    root_fd = os.open(target, directory_flags)
except FileNotFoundError:
    if os.path.lexists(target) \
            or initial != "absent" \
            or phase not in {"prepared", "publishing"}:
        raise ValueError("corpus bootstrap root does not match its intent")
    print("absent")
    raise SystemExit(0)
try:
    before_root = os.fstat(root_fd)
    if not stat.S_ISDIR(before_root.st_mode) \
            or before_root.st_uid != os.geteuid() \
            or stat.S_IMODE(before_root.st_mode) & 0o022:
        raise ValueError("unsafe corpus bootstrap root")
    expected_identity = expected_root_identity()
    if expected_identity is not None \
            and (before_root.st_dev, before_root.st_ino,
                 before_root.st_mode, before_root.st_uid) != expected_identity:
        raise ValueError("corpus bootstrap root identity changed")
    seen = set()
    with os.scandir(root_fd) as entries:
        for entry in entries:
            if entry.name not in {".git", "README.md"}:
                raise ValueError(
                    f"unattributed corpus bootstrap entry: {entry.name}")
            if entry.name in seen:
                raise ValueError("duplicate corpus bootstrap entry")
            info = entry.stat(follow_symlinks=False)
            if info.st_uid != os.geteuid() \
                    or stat.S_IMODE(info.st_mode) & 0o022:
                raise ValueError("unsafe corpus bootstrap entry")
            if entry.name == ".git" and not stat.S_ISDIR(info.st_mode):
                raise ValueError("unsafe corpus bootstrap git metadata")
            if entry.name == "README.md" and not stat.S_ISREG(info.st_mode):
                raise ValueError("unsafe corpus bootstrap README")
            seen.add(entry.name)
    if "README.md" in seen and ".git" not in seen:
        raise ValueError("README exists before corpus git initialization")
    if ".git" in seen:
        git_root = os.path.join(target, ".git")
        for relative in (
                "hooks", "config.worktree", "info/attributes",
                "info/grafts", "objects/info/alternates", "refs/replace"):
            if os.path.lexists(os.path.join(git_root, relative)):
                raise ValueError(
                    f"active or external git control is forbidden: {relative}")
        config_path = os.path.join(git_root, "config")
        head_path = os.path.join(git_root, "HEAD")
        config_exists = os.path.lexists(config_path)
        head_exists = os.path.lexists(head_path)
        if config_exists != head_exists:
            raise ValueError("incomplete corpus git control files")
        if config_exists:
            expected_config = (
                b"[core]\n\trepositoryformatversion = 0\n"
                b"\tfilemode = true\n\tbare = false\n"
                b"\tlogallrefupdates = true\n")
            if stable_file(config_path, "corpus git config",
                           MAX_INTENT_BYTES) != expected_config:
                raise ValueError("corpus git config is not producer-exact")
            if stable_file(head_path, "corpus git HEAD",
                           MAX_INTENT_BYTES) \
                    != b"ref: refs/heads/sia-genesis\n":
                raise ValueError("corpus git HEAD is not producer-exact")
    if "README.md" in seen:
        expected = (expected_readme + "\n").encode("utf-8")
        if stable_file(os.path.join(target, "README.md"),
                       "corpus bootstrap README", len(expected) + 1) != expected:
            raise ValueError("corpus bootstrap README bytes are not exact")
    after_root = os.fstat(root_fd)
    current_root = os.stat(target, follow_symlinks=False)
    if generation(before_root) != generation(after_root) \
            or generation(after_root) != generation(current_root):
        raise ValueError("corpus bootstrap root changed while inspected")
    if not seen:
        if phase == "existing" \
                and "empty:" + ":".join(
                    str(value) for value in generation(before_root)) != initial:
            raise ValueError("empty corpus no longer matches captured generation")
        print("empty")
    elif seen == {".git"}:
        print("git")
    elif seen == {".git", "README.md"}:
        print("readme")
    else:
        raise ValueError("corpus bootstrap is not an allowed prefix")
finally:
    os.close(root_fd)
PY
}

corpus_bootstrap_intent_valid() {
  local record="${1:-$CORPUS_BOOTSTRAP_INTENT}"
  local before after initial phase tree stage state current
  stage="${CORPUS_BOOTSTRAP_STAGE:-$SHARE/.corpus-bootstrap-tree}"
  before="$(corpus_bootstrap_intent_fields "$record")" || return 1
  IFS=$'\t' read -r initial phase tree <<< "$before"
  case "$phase" in
    prepared)
      [ ! -e "$SHARE/corpus" ] && [ ! -L "$SHARE/corpus" ] || return 1
      if [ -e "$stage" ] || [ -L "$stage" ]; then
        corpus_bootstrap_stage_empty || return 1
      fi
      ;;
    publishing)
      if [ ! -e "$SHARE/corpus" ] && [ ! -L "$SHARE/corpus" ]; then
        [ -d "$stage" ] && [ ! -L "$stage" ] || return 1
        [ "$(owned_tree_generation "$stage")" = "$tree" ] || return 1
      else
        [ ! -e "$stage" ] && [ ! -L "$stage" ] || return 1
        current="$(owned_tree_generation "$SHARE/corpus")" || return 1
        gbrain_tree_generation_matches "$current" "$tree" || return 1
      fi
      ;;
    published|existing)
      [ ! -e "$stage" ] && [ ! -L "$stage" ] || return 1
      ;;
    *) return 1 ;;
  esac
  state="$(corpus_bootstrap_prefix_state "$initial" "$phase" "$tree")" \
    || return 1
  after="$(corpus_bootstrap_intent_fields "$record")" || return 1
  [ "$before" = "$after" ] || {
    echo "corpus bootstrap intent changed during validation" >&2
    return 1
  }
  printf '%s\n' "$state"
}

write_corpus_bootstrap_intent() {
  local initial phase stage installed payload
  stage="$MANAGED_DIR/.corpus-bootstrap.intent.stage"
  owned_file_cas recover "$CORPUS_BOOTSTRAP_INTENT" || return 1
  if [ -e "$CORPUS_BOOTSTRAP_INTENT" ] \
      || [ -L "$CORPUS_BOOTSTRAP_INTENT" ]; then
    echo "corpus bootstrap intent already exists" >&2
    return 1
  fi
  if [ -e "$stage" ] || [ -L "$stage" ]; then
    corpus_bootstrap_intent_valid "$stage" >/dev/null || {
      echo "fixed corpus bootstrap intent stage is invalid; preserved" >&2
      return 1
    }
  else
    initial="$(corpus_bootstrap_initial_state)" || return 1
    if [ "$initial" = absent ]; then
      phase=prepared
    else
      phase=existing
    fi
    payload="$(printf 'managed-by=khephri.sia\nkind=corpus-bootstrap-v2\npath=%s\ninitial=%s\nphase=%s\ntree=absent' \
      "$SHARE/corpus" "$initial" "$phase")"
    durable_fixed_metadata_stage "$stage" "$payload" || return 1
    corpus_bootstrap_intent_valid "$stage" >/dev/null || return 1
  fi
  if ! installed="$(owned_file_cas publish "$stage" \
      "$CORPUS_BOOTSTRAP_INTENT" absent)"; then
    [ ! -e "$stage" ] \
      || echo "corpus bootstrap intent stage retained at $stage" >&2
    return 1
  fi
  corpus_bootstrap_intent_valid >/dev/null
}

set_corpus_bootstrap_intent() {
  local phase="$1" tree="$2" stage expected payload installed fields
  local initial _current_phase _current_tree
  case "$phase" in
    prepared) [ "$tree" = absent ] || return 1 ;;
    publishing|published)
      [[ "$tree" =~ ^tree:([0-9]+:){8}[0-9a-f]{64}$ ]] || return 1 ;;
    *) return 1 ;;
  esac
  fields="$(corpus_bootstrap_intent_fields)" || return 1
  IFS=$'\t' read -r initial _current_phase _current_tree <<< "$fields"
  [ "$initial" = absent ] || return 1
  stage="$MANAGED_DIR/.corpus-bootstrap.intent.stage"
  owned_file_cas recover "$CORPUS_BOOTSTRAP_INTENT" || return 1
  expected="$(owned_metadata generation "$CORPUS_BOOTSTRAP_INTENT")" \
    || return 1
  payload="$(printf 'managed-by=khephri.sia\nkind=corpus-bootstrap-v2\npath=%s\ninitial=absent\nphase=%s\ntree=%s' \
    "$SHARE/corpus" "$phase" "$tree")"
  if [ -e "$stage" ] || [ -L "$stage" ]; then
    if ! owned_metadata exact "$stage" "$payload"; then
      corpus_bootstrap_intent_fields "$stage" >/dev/null || {
        echo "fixed corpus bootstrap intent stage is invalid; preserved" >&2
        return 1
      }
      remove_owned_fixed_metadata "$stage" || return 1
      durable_fixed_metadata_stage "$stage" "$payload" || return 1
    fi
  else
    durable_fixed_metadata_stage "$stage" "$payload" || return 1
  fi
  if ! installed="$(owned_file_cas publish "$stage" \
      "$CORPUS_BOOTSTRAP_INTENT" "$expected")"; then
    [ ! -e "$stage" ] \
      || echo "corpus bootstrap intent stage retained at $stage" >&2
    return 1
  fi
  fields="$(corpus_bootstrap_intent_fields)" || return 1
  [ "$fields" = "absent"$'\t'"$phase"$'\t'"$tree" ] || return 1
  if [ -e "$stage" ] || [ -L "$stage" ]; then
    corpus_bootstrap_intent_fields "$stage" >/dev/null || return 1
    remove_owned_fixed_metadata "$stage" || return 1
  fi
}

ensure_corpus_bootstrap_root() {
  local fields initial phase tree stage current
  stage="${CORPUS_BOOTSTRAP_STAGE:-$SHARE/.corpus-bootstrap-tree}"
  fields="$(corpus_bootstrap_intent_fields)" || return 1
  IFS=$'\t' read -r initial phase tree <<< "$fields"
  if [ "$initial" != absent ]; then
    [ "$phase" = existing ] || return 1
    corpus_bootstrap_intent_valid >/dev/null
    return
  fi
  if [ "$phase" = prepared ]; then
    if [ -e "$SHARE/corpus" ] || [ -L "$SHARE/corpus" ]; then
      echo "a corpus root appeared before its prepared intent published it; preserved" >&2
      return 1
    fi
    if [ -e "$stage" ] || [ -L "$stage" ]; then
      corpus_bootstrap_stage_empty || return 1
    else
      python3 - "$SHARE" "$stage" <<'PY'
import os
import stat
import sys

root, stage = map(os.path.abspath, sys.argv[1:])
if os.path.dirname(stage) != root:
    raise ValueError("corpus bootstrap stage is not a share-root child")
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
root_fd = os.open(root, flags)
try:
    info = os.fstat(root_fd)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise ValueError("unsafe corpus bootstrap parent")
    os.mkdir(os.path.basename(stage), 0o700, dir_fd=root_fd)
    os.fsync(root_fd)
finally:
    os.close(root_fd)
PY
      corpus_bootstrap_stage_empty || return 1
    fi
    # Durable corpus-root boundary: the intent-bound off-path tree exists.
    tree="$(owned_tree_generation "$stage")" || return 1
    set_corpus_bootstrap_intent publishing "$tree" || return 1
    # Durable corpus-root boundary: the exact staged generation is authorized.
    phase=publishing
  fi
  if [ "$phase" = publishing ]; then
    if [ ! -e "$SHARE/corpus" ] && [ ! -L "$SHARE/corpus" ]; then
      [ -d "$stage" ] && [ ! -L "$stage" ] || return 1
      [ "$(owned_tree_generation "$stage")" = "$tree" ] || {
        echo "corpus bootstrap stage changed before publication; preserved" >&2
        return 1
      }
      move_bootstrap_tree_noreplace "$stage" "$SHARE/corpus" || return 1
      # Durable corpus-root boundary: the no-clobber canonical rename is synced.
    else
      if [ -e "$stage" ] || [ -L "$stage" ]; then
        echo "corpus bootstrap has two publication roots; preserved" >&2
        return 1
      fi
    fi
    current="$(owned_tree_generation "$SHARE/corpus")" || return 1
    gbrain_tree_generation_matches "$current" "$tree" || {
      echo "corpus root does not match its publishing intent; preserved" >&2
      return 1
    }
    set_corpus_bootstrap_intent published "$current" || return 1
    # Durable corpus-root boundary: the canonical root identity is bound.
    phase=published
  fi
  [ "$phase" = published ] || return 1
  corpus_bootstrap_intent_valid >/dev/null
}

retire_corpus_bootstrap_intent() {
  local expected archive
  archive="$MANAGED_DIR/.corpus-bootstrap.retired"
  if [ -e "$archive" ] || [ -L "$archive" ]; then
    corpus_bootstrap_intent_valid "$archive" >/dev/null || {
      echo "fixed retired corpus bootstrap intent is invalid; preserved" >&2
      return 1
    }
    remove_owned_fixed_metadata "$archive" || return 1
  fi
  [ -e "$CORPUS_BOOTSTRAP_INTENT" ] \
    || [ -L "$CORPUS_BOOTSTRAP_INTENT" ] || return 0
  expected="$(owned_metadata generation "$CORPUS_BOOTSTRAP_INTENT")" \
    || return 1
  owned_file_cas archive "$archive" "$CORPUS_BOOTSTRAP_INTENT" \
    "$expected" || return 1
  corpus_bootstrap_intent_valid "$archive" >/dev/null || return 1
  remove_owned_fixed_metadata "$archive"
}

corpus_adoption_intent_fields() {
  local record="${1:-$CORPUS_ADOPTION_INTENT}"
  python3 - "$record" "$SHARE/corpus" <<'PY'
import os
import re
import stat
import sys

record = os.path.abspath(sys.argv[1])
target = os.path.abspath(sys.argv[2])
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_NOFOLLOW", 0)
         | getattr(os, "O_NONBLOCK", 0))
descriptor = os.open(record, flags)
try:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() \
            or before.st_nlink != 1 \
            or stat.S_IMODE(before.st_mode) != 0o600 \
            or before.st_size > 65_536:
        raise ValueError("unsafe corpus adoption intent")
    chunks = []
    remaining = 65_537
    while remaining:
        chunk = os.read(descriptor, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    content = b"".join(chunks)
    after = os.fstat(descriptor)
    current = os.stat(record, follow_symlinks=False)
    generation = lambda value: (
        value.st_dev, value.st_ino, value.st_mode, value.st_uid,
        value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    if len(content) != before.st_size or len(content) > 65_536 \
            or generation(before) != generation(after) \
            or generation(after) != generation(current):
        raise ValueError("corpus adoption intent changed while inspected")
finally:
    os.close(descriptor)
try:
    text = content.decode("utf-8", "strict")
except UnicodeError as error:
    raise ValueError("corpus adoption intent is not strict UTF-8") from error
tree = r"tree:(?:[0-9]+:){8}[0-9a-f]{64}"
pattern = re.compile(
    r"managed-by=khephri[.]sia\nkind=corpus-adoption-v1\npath="
    + re.escape(target)
    + r"\nmode=(legacy|explicit)\ntree=(" + tree + ")"
      r"\nhead=([0-9a-f]{40}|[0-9a-f]{64})\n")
matched = pattern.fullmatch(text)
if matched is None:
    raise ValueError("corpus adoption intent bytes are not exact")
print("\t".join(matched.groups()))
PY
}

corpus_adoption_intent_valid() {
  local record="${1:-$CORPUS_ADOPTION_INTENT}"
  local fields mode expected_tree expected_head before after current_head
  fields="$(corpus_adoption_intent_fields "$record")" || return 1
  IFS=$'\t' read -r mode expected_tree expected_head <<< "$fields"
  before="$(owned_tree_generation "$SHARE/corpus")" || return 1
  [ "$(bounded_corpus_git -C "$SHARE/corpus" \
      rev-parse --is-inside-work-tree 2>/dev/null)" = true ] || return 1
  current_head="$(bounded_corpus_git -C "$SHARE/corpus" \
    rev-parse --verify HEAD)" || return 1
  after="$(owned_tree_generation "$SHARE/corpus")" || return 1
  [ "$before" = "$expected_tree" ] && [ "$after" = "$expected_tree" ] \
    && [ "$current_head" = "$expected_head" ]
}

write_corpus_adoption_intent() {
  local mode="$1" stage before after head payload installed
  case "$mode" in legacy|explicit) ;; *) return 1 ;; esac
  stage="$MANAGED_DIR/.corpus-adoption.intent.stage"
  owned_file_cas recover "$CORPUS_ADOPTION_INTENT" || return 1
  if [ -e "$CORPUS_ADOPTION_INTENT" ] \
      || [ -L "$CORPUS_ADOPTION_INTENT" ]; then
    echo "corpus adoption intent already exists" >&2
    return 1
  fi
  if [ -e "$stage" ] || [ -L "$stage" ]; then
    corpus_adoption_intent_valid "$stage" || {
      echo "fixed corpus adoption intent stage is invalid; preserved" >&2
      return 1
    }
  else
    before="$(owned_tree_generation "$SHARE/corpus")" || return 1
    [ "$(bounded_corpus_git -C "$SHARE/corpus" \
        rev-parse --is-inside-work-tree 2>/dev/null)" = true ] || return 1
    head="$(bounded_corpus_git -C "$SHARE/corpus" \
      rev-parse --verify HEAD)" || return 1
    [[ "$head" =~ ^([0-9a-f]{40}|[0-9a-f]{64})$ ]] || return 1
    after="$(owned_tree_generation "$SHARE/corpus")" || return 1
    [ "$before" = "$after" ] || {
      echo "corpus changed while adoption authority was captured" >&2
      return 1
    }
    payload="$(printf 'managed-by=khephri.sia\nkind=corpus-adoption-v1\npath=%s\nmode=%s\ntree=%s\nhead=%s' \
      "$SHARE/corpus" "$mode" "$before" "$head")"
    durable_fixed_metadata_stage "$stage" "$payload" || return 1
    corpus_adoption_intent_valid "$stage" || return 1
  fi
  if ! installed="$(owned_file_cas publish "$stage" \
      "$CORPUS_ADOPTION_INTENT" absent)"; then
    [ ! -e "$stage" ] \
      || echo "corpus adoption intent stage retained at $stage" >&2
    return 1
  fi
  corpus_adoption_intent_valid
}

retire_corpus_adoption_intent() {
  local expected archive
  archive="$MANAGED_DIR/.corpus-adoption.retired"
  if [ -e "$archive" ] || [ -L "$archive" ]; then
    corpus_adoption_intent_valid "$archive" || {
      echo "fixed retired corpus adoption intent is invalid; preserved" >&2
      return 1
    }
    remove_owned_fixed_metadata "$archive" || return 1
  fi
  [ -e "$CORPUS_ADOPTION_INTENT" ] \
    || [ -L "$CORPUS_ADOPTION_INTENT" ] || return 0
  corpus_adoption_intent_valid || {
    echo "corpus changed before adoption intent retirement; preserved" >&2
    return 1
  }
  expected="$(owned_metadata generation "$CORPUS_ADOPTION_INTENT")" \
    || return 1
  owned_file_cas archive "$archive" "$CORPUS_ADOPTION_INTENT" \
    "$expected" || return 1
  corpus_adoption_intent_valid "$archive" || return 1
  remove_owned_fixed_metadata "$archive"
}

corpus_root_identity() {
  python3 - "$SHARE/corpus" <<'PY'
import os
import stat
import sys

target = os.path.abspath(sys.argv[1])
if os.path.realpath(target) != target:
    raise SystemExit("corpus root path is not canonical")
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
descriptor = os.open(target, flags)
try:
    before = os.fstat(descriptor)
    if not stat.S_ISDIR(before.st_mode) \
            or before.st_uid != os.geteuid() \
            or stat.S_IMODE(before.st_mode) & 0o022:
        raise ValueError("unsafe corpus root")
    after = os.fstat(descriptor)
    current = os.stat(target, follow_symlinks=False)
    identity = lambda value: (
        value.st_dev, value.st_ino, value.st_mode, value.st_uid)
    if identity(before) != identity(after) \
            or identity(after) != identity(current):
        raise ValueError("corpus root identity changed while inspected")
    print(":".join(str(value) for value in identity(before)))
finally:
    os.close(descriptor)
PY
}

corpus_receipt_file_private() {
  python3 - "$1" <<'PY'
import os
import stat
import sys

path = os.path.abspath(sys.argv[1])
info = os.stat(path, follow_symlinks=False)
if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
        or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
    raise SystemExit("unsafe corpus receipt metadata")
PY
}

corpus_receipt_journal_state() {
  python3 - "$CORPUS_RECEIPT" <<'PY'
import hashlib
import json
import os
import re
import stat
import sys

target = os.path.abspath(sys.argv[1])
parent = os.path.dirname(target)
target_name = os.path.basename(target)
identity = hashlib.sha256(os.fsencode(target)).hexdigest()
journal_name = ".sia-cas-journal-" + identity
directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                   | getattr(os, "O_DIRECTORY", 0)
                   | getattr(os, "O_NOFOLLOW", 0))
file_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
              | getattr(os, "O_NOFOLLOW", 0)
              | getattr(os, "O_NONBLOCK", 0))
parent_fd = os.open(parent, directory_flags)
try:
    parent_info = os.fstat(parent_fd)
    if not stat.S_ISDIR(parent_info.st_mode) \
            or parent_info.st_uid != os.geteuid():
        raise ValueError("unsafe corpus receipt journal parent")
    try:
        descriptor = os.open(journal_name, file_flags, dir_fd=parent_fd)
    except FileNotFoundError:
        try:
            os.stat(journal_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            print("absent")
            raise SystemExit(0)
        raise
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() or before.st_nlink != 1 \
                or stat.S_IMODE(before.st_mode) != 0o600 \
                or before.st_size > 65_536:
            raise ValueError("unsafe corpus receipt CAS journal")
        chunks = []
        remaining = 65_537
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        current = os.stat(
            journal_name, dir_fd=parent_fd, follow_symlinks=False)
        generation = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_nlink, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns)
        if len(content) != before.st_size or len(content) > 65_536 \
                or generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise ValueError("corpus receipt CAS journal changed")
    finally:
        os.close(descriptor)
finally:
    os.close(parent_fd)
try:
    value = json.loads(content.decode("utf-8", "strict"))
except (json.JSONDecodeError, UnicodeError) as error:
    raise ValueError("invalid corpus receipt CAS journal") from error
required = {"version", "operation", "target", "staged", "archive",
            "expected", "desired"}
token = re.compile(
    r"present:(?:[0-9]+:){7}[0-9a-f]{64}")
if not isinstance(value, dict) or set(value) != required \
        or value["version"] != 1 or value["operation"] != "publish" \
        or value["target"] != target_name \
        or value["staged"] != ".corpus.receipt.stage" \
        or not isinstance(value["archive"], str) \
        or os.path.basename(value["archive"]) != value["archive"] \
        or not isinstance(value["expected"], str) \
        or not isinstance(value["desired"], str) \
        or token.fullmatch(value["desired"]) is None:
    raise ValueError("journal is not a corpus receipt publication")
if value["expected"] == "absent":
    print("fresh")
elif token.fullmatch(value["expected"]) is not None:
    print("migration")
else:
    raise ValueError("invalid corpus receipt publication expectation")
PY
}

corpus_legacy_receipt_valid() {
  local record="${1:-$CORPUS_RECEIPT}" expected before after
  expected="$(printf 'managed-by=khephri.sia\nkind=corpus\npath=%s' \
    "$SHARE/corpus")"
  before="$(owned_metadata generation "$record")" || return 1
  corpus_receipt_file_private "$record" \
    && owned_metadata exact "$record" "$expected" \
    && corpus_receipt_file_private "$record" || return 1
  after="$(owned_metadata generation "$record")" || return 1
  [ "$before" = "$after" ]
}

corpus_v2_receipt_payload() {
  local identity="$1"
  printf 'managed-by=khephri.sia\nkind=corpus-v2\npath=%s\nroot=%s' \
    "$SHARE/corpus" "$identity"
}

corpus_receipt_state() {
  local before after expected receipt_before receipt_after
  [ -f "$CORPUS_RECEIPT" ] && [ ! -L "$CORPUS_RECEIPT" ] || return 1
  before="$(corpus_root_identity)" || return 1
  if corpus_legacy_receipt_valid; then
    after="$(corpus_root_identity)" || return 1
    [ "$before" = "$after" ] || return 1
    printf '%s\n' legacy
    return 0
  fi
  expected="$(corpus_v2_receipt_payload "$before")"
  receipt_before="$(owned_metadata generation "$CORPUS_RECEIPT")" || return 1
  if corpus_receipt_file_private "$CORPUS_RECEIPT" \
      && owned_metadata exact "$CORPUS_RECEIPT" "$expected" \
      && corpus_receipt_file_private "$CORPUS_RECEIPT"; then
    receipt_after="$(owned_metadata generation "$CORPUS_RECEIPT")" || return 1
    [ "$receipt_before" = "$receipt_after" ] || return 1
    after="$(corpus_root_identity)" || return 1
    [ "$before" = "$after" ] || return 1
    printf '%s\n' v2
    return 0
  fi
  return 1
}

corpus_receipt_valid() {
  [ "$(corpus_receipt_state 2>/dev/null || true)" = v2 ]
}

require_corpus_receipt_transition_locks() {
  if [ "${SIA_CORPUS_RECEIPT_LOCKS_HELD:-0}" != 1 ] \
      || [ -z "${SIA_INSTALL_LOCK_FD:-}" ] \
      || [ -z "${SIA_CORPUS_LOCK_FD:-}" ]; then
    echo "corpus receipt transition requires lifecycle and corpus owner locks" >&2
    return 1
  fi
}

retire_migrated_legacy_corpus_receipt_stage() {
  local stage="$MANAGED_DIR/.corpus.receipt.stage"
  local archive="$MANAGED_DIR/.corpus.receipt.retired" expected
  owned_file_cas recover "$stage" || return 1
  if [ -e "$archive" ] || [ -L "$archive" ]; then
    corpus_legacy_receipt_valid "$archive" || {
      echo "fixed retired corpus receipt is invalid; preserved" >&2
      return 1
    }
    remove_owned_fixed_metadata "$archive" || return 1
  fi
  [ -e "$stage" ] || [ -L "$stage" ] || return 0
  corpus_legacy_receipt_valid "$stage" || {
    echo "fixed prior corpus receipt stage is invalid; preserved" >&2
    return 1
  }
  expected="$(owned_metadata generation "$stage")" || return 1
  corpus_legacy_receipt_valid "$stage" || {
    echo "fixed prior corpus receipt changed before retirement" >&2
    return 1
  }
  owned_file_cas archive "$archive" "$stage" "$expected" || return 1
  corpus_legacy_receipt_valid "$archive" || return 1
  remove_owned_fixed_metadata "$archive"
}

migrate_legacy_corpus_receipt() {
  local early_state="${1:-${SIA_CORPUS_EARLY_RECEIPT_STATE:-absent}}"
  local early_root="${2:-${SIA_CORPUS_EARLY_RECEIPT_ROOT:-}}"
  local early_generation="${3:-${SIA_CORPUS_EARLY_RECEIPT_GENERATION:-}}"
  local early_journal="${4:-${SIA_CORPUS_EARLY_RECEIPT_JOURNAL_STATE:-absent}}"
  local stage current_state current_root current_generation after_generation
  local before after expected payload installed resume_authority=0
  case "$early_state" in absent|legacy|v2) ;; *) return 1 ;; esac
  case "$early_journal" in absent|fresh|migration) ;; *) return 1 ;; esac
  require_corpus_receipt_transition_locks || return 1
  owned_file_cas recover "$CORPUS_RECEIPT" || return 1
  owned_file_cas recover "$CORPUS_BOOTSTRAP_INTENT" || return 1
  owned_file_cas recover "$CORPUS_ADOPTION_INTENT" || return 1
  if [ ! -e "$CORPUS_RECEIPT" ] && [ ! -L "$CORPUS_RECEIPT" ]; then
    if [ "$early_state" != absent ] || [ "$early_journal" = migration ]; then
      echo "corpus receipt authority disappeared before locked recovery" >&2
      return 1
    fi
    return 0
  fi
  current_generation="$(owned_metadata generation "$CORPUS_RECEIPT")" \
    || return 1
  current_state="$(corpus_receipt_state)" || {
    echo "existing corpus receipt is invalid; preserved" >&2
    return 1
  }
  after_generation="$(owned_metadata generation "$CORPUS_RECEIPT")" \
    || return 1
  [ "$current_generation" = "$after_generation" ] || {
    echo "corpus receipt changed across locked recovery" >&2
    return 1
  }
  current_root="$(corpus_root_identity)" || return 1
  if [ "$current_state" = v2 ]; then
    case "$early_state" in
      v2)
        if [ "$current_root" != "$early_root" ] \
            || [ "$current_generation" != "$early_generation" ]; then
          echo "v2 corpus receipt changed before locked recovery" >&2
          return 1
        fi
        ;;
      legacy)
        if [ "$early_journal" != migration ] \
            || [ "$current_root" != "$early_root" ]; then
          echo "unexpected v2 receipt replaced early legacy authority" >&2
          return 1
        fi
        ;;
      absent)
        case "$early_journal" in fresh|migration) ;; *)
          echo "a corpus receipt appeared without an observed CAS journal" >&2
          return 1
          ;;
        esac
        if [ -z "$early_root" ] || [ "$current_root" != "$early_root" ]; then
          echo "published corpus receipt does not match the observed root" >&2
          return 1
        fi
        ;;
    esac
    retire_migrated_legacy_corpus_receipt_stage || return 1
    return 0
  fi
  [ "$current_state" = legacy ] || return 1
  if [ "$early_state" = legacy ]; then
    case "$early_journal" in absent|migration) ;; *)
      echo "legacy receipt conflicts with a fresh receipt CAS journal" >&2
      return 1
      ;;
    esac
    if [ "$current_root" != "$early_root" ] \
        || [ "$current_generation" != "$early_generation" ]; then
      echo "legacy corpus root or receipt changed before locked migration" >&2
      return 1
    fi
  elif [ "$early_state" = absent ] \
      && [ "$early_journal" = migration ] \
      && [ -n "$early_root" ] && [ "$current_root" = "$early_root" ]; then
    resume_authority=1
  else
    echo "refusing an unexpected legacy receipt at the locked boundary" >&2
    return 1
  fi
  if [ -e "$CORPUS_BOOTSTRAP_INTENT" ] \
      || [ -L "$CORPUS_BOOTSTRAP_INTENT" ] \
      || [ -e "$CORPUS_ADOPTION_INTENT" ] \
      || [ -L "$CORPUS_ADOPTION_INTENT" ]; then
    echo "legacy corpus receipt conflicts with a pending ownership intent" >&2
    return 1
  fi
  # Locked corpus-receipt boundary: continuity remains the publication baseline.
  before="$(corpus_root_identity)" || return 1
  expected="$(owned_metadata generation "$CORPUS_RECEIPT")" || return 1
  if [ "$before" != "$current_root" ] \
      || [ "$expected" != "$current_generation" ]; then
    echo "corpus root or legacy receipt changed before publication staging" >&2
    return 1
  fi
  [ "$(corpus_receipt_state)" = legacy ] || {
    echo "legacy corpus receipt changed before migration" >&2
    return 1
  }
  payload="$(corpus_v2_receipt_payload "$before")"
  stage="$MANAGED_DIR/.corpus.receipt.stage"
  if [ -e "$stage" ] || [ -L "$stage" ]; then
    if ! corpus_receipt_file_private "$stage" \
        || ! owned_metadata exact "$stage" "$payload" \
        || ! corpus_receipt_file_private "$stage"; then
      echo "fixed corpus receipt migration stage is invalid; preserved" >&2
      return 1
    fi
  elif [ "$resume_authority" = 1 ]; then
    echo "pending corpus receipt migration lost its desired v2 stage" >&2
    return 1
  else
    durable_fixed_metadata_stage "$stage" "$payload" || return 1
  fi
  after="$(corpus_root_identity)" || return 1
  [ "$before" = "$after" ] || {
    echo "corpus root changed before receipt migration" >&2
    return 1
  }
  if ! installed="$(owned_file_cas publish "$stage" "$CORPUS_RECEIPT" \
      "$expected")"; then
    [ ! -e "$stage" ] \
      || echo "corpus receipt migration stage retained at $stage" >&2
    return 1
  fi
  # Durable corpus-receipt migration boundary: v2 is canonical.
  after="$(corpus_root_identity)" || return 1
  if [ "$before" != "$after" ] || ! corpus_receipt_valid; then
    echo "corpus root changed across receipt migration; refusing rebind" >&2
    return 1
  fi
  retire_migrated_legacy_corpus_receipt_stage || return 1
}

write_corpus_receipt() {
  local stage installed expected before after
  require_corpus_receipt_transition_locks || return 1
  corpus_receipt_valid && return 0
  owned_file_cas recover "$CORPUS_RECEIPT" || return 1
  if [ -e "$CORPUS_RECEIPT" ] || [ -L "$CORPUS_RECEIPT" ]; then
    echo "existing corpus receipt is invalid; preserved" >&2
    return 1
  fi
  before="$(corpus_root_identity)" || return 1
  stage="$MANAGED_DIR/.corpus.receipt.stage"
  expected="$(corpus_v2_receipt_payload "$before")"
  if [ -e "$stage" ] || [ -L "$stage" ]; then
    if ! corpus_receipt_file_private "$stage" \
        || ! owned_metadata exact "$stage" "$expected" \
        || ! corpus_receipt_file_private "$stage"; then
      echo "fixed corpus receipt stage is invalid; preserved" >&2
      return 1
    fi
  else
    durable_fixed_metadata_stage "$stage" "$expected" || return 1
  fi
  after="$(corpus_root_identity)" || return 1
  [ "$before" = "$after" ] || {
    echo "corpus root changed before receipt publication" >&2
    return 1
  }
  if ! installed="$(owned_file_cas publish "$stage" "$CORPUS_RECEIPT" \
      absent)"; then
    [ ! -e "$stage" ] \
      || echo "corpus receipt stage retained at $stage" >&2
    return 1
  fi
  after="$(corpus_root_identity)" || return 1
  if [ "$before" != "$after" ] || ! corpus_receipt_valid; then
    echo "corpus root changed across receipt publication; refusing rebind" >&2
    return 1
  fi
}

preflight_corpus_read_only() {
  local receipt_state journal_state early_root="" after_root
  local early_generation after_generation
  SIA_CORPUS_NEEDS_RECEIPT=0
  SIA_CORPUS_BOOTSTRAP_NEEDED=0
  SIA_CORPUS_ADOPTION_NEEDED=0
  SIA_CORPUS_EARLY_RECEIPT_STATE=absent
  SIA_CORPUS_EARLY_RECEIPT_ROOT=""
  SIA_CORPUS_EARLY_RECEIPT_GENERATION=""
  SIA_CORPUS_EARLY_RECEIPT_JOURNAL_STATE=absent
  journal_state="$(corpus_receipt_journal_state)" || {
    echo "unsafe or invalid corpus receipt CAS journal; preserved" >&2
    return 1
  }
  case "$journal_state" in absent|fresh|migration) ;; *) return 1 ;; esac
  SIA_CORPUS_EARLY_RECEIPT_JOURNAL_STATE="$journal_state"
  if [ -e "$SHARE/corpus" ] || [ -L "$SHARE/corpus" ]; then
    early_root="$(corpus_root_identity)" || {
      echo "refusing unsafe SIA corpus root" >&2
      return 1
    }
    SIA_CORPUS_EARLY_RECEIPT_ROOT="$early_root"
  fi
  if { [ -e "$CORPUS_BOOTSTRAP_INTENT" ] \
        || [ -L "$CORPUS_BOOTSTRAP_INTENT" ]; } \
      && { [ -e "$CORPUS_ADOPTION_INTENT" ] \
        || [ -L "$CORPUS_ADOPTION_INTENT" ]; }; then
    echo "conflicting corpus bootstrap and adoption intents" >&2
    return 1
  fi
  if [ -e "$CORPUS_RECEIPT" ] || [ -L "$CORPUS_RECEIPT" ]; then
    early_generation="$(owned_metadata generation "$CORPUS_RECEIPT")" \
      || return 1
    receipt_state="$(corpus_receipt_state)" || {
      echo "existing corpus receipt is invalid; preserved" >&2
      return 1
    }
    after_generation="$(owned_metadata generation "$CORPUS_RECEIPT")" \
      || return 1
    after_root="$(corpus_root_identity)" || return 1
    if [ -z "$early_root" ] || [ "$early_root" != "$after_root" ] \
        || [ "$early_generation" != "$after_generation" ] \
        || [ "$(corpus_receipt_state)" != "$receipt_state" ]; then
      echo "corpus receipt boundary changed during read-only preflight" >&2
      return 1
    fi
    if [ "$receipt_state" = legacy ] && [ "$journal_state" = fresh ]; then
      echo "legacy corpus receipt conflicts with a fresh publication journal" >&2
      return 1
    fi
    SIA_CORPUS_EARLY_RECEIPT_STATE="$receipt_state"
    SIA_CORPUS_EARLY_RECEIPT_ROOT="$early_root"
    SIA_CORPUS_EARLY_RECEIPT_GENERATION="$early_generation"
    if [ "$receipt_state" = legacy ]; then
      echo "  exact legacy corpus receipt awaits locked v2 migration"
    fi
    # This pass precedes the lifecycle and corpus-owner leases. It only
    # recognizes receipt state; it never recovers CAS or retires an intent.
    return 0
  fi
  if [ -e "$CORPUS_RECEIPT" ] || [ -L "$CORPUS_RECEIPT" ]; then
    echo "corpus receipt appeared during read-only preflight" >&2
    return 1
  fi
  if [ -n "$early_root" ]; then
    after_root="$(corpus_root_identity)" || return 1
    [ "$early_root" = "$after_root" ] || {
      echo "corpus root changed during read-only preflight" >&2
      return 1
    }
  elif [ -e "$SHARE/corpus" ] || [ -L "$SHARE/corpus" ]; then
    echo "corpus root appeared during read-only preflight" >&2
    return 1
  fi
  if [ -e "$CORPUS_BOOTSTRAP_INTENT" ] \
      || [ -L "$CORPUS_BOOTSTRAP_INTENT" ]; then
    corpus_bootstrap_intent_valid >/dev/null || {
      echo "refusing corpus state that does not match its bootstrap intent" >&2
      return 1
    }
    return 0
  fi
  if [ -e "$CORPUS_ADOPTION_INTENT" ] \
      || [ -L "$CORPUS_ADOPTION_INTENT" ]; then
    corpus_adoption_intent_valid || {
      echo "refusing corpus changed after durable adoption consent" >&2
      return 1
    }
    return 0
  fi
  # A missing receipt can be a fresh install, an unowned corpus that the
  # locked pass must classify, or the temporary canonical absence of a
  # journaled receipt CAS. Do not create adoption authority in this pass.
  return 0
}

preflight_corpus() {
  local mode="${1:-locked}" bootstrap_stage receipt_state
  if [ "$mode" = read-only ]; then
    preflight_corpus_read_only
    return
  fi
  [ "$mode" = locked ] || {
    echo "invalid corpus preflight mode" >&2
    return 1
  }
  require_corpus_receipt_transition_locks || return 1
  bootstrap_stage="${CORPUS_BOOTSTRAP_STAGE:-$SHARE/.corpus-bootstrap-tree}"
  SIA_CORPUS_NEEDS_RECEIPT=0
  SIA_CORPUS_BOOTSTRAP_NEEDED=0
  SIA_CORPUS_ADOPTION_NEEDED=0
  owned_file_cas recover "$CORPUS_RECEIPT" || return 1
  owned_file_cas recover "$CORPUS_BOOTSTRAP_INTENT" || return 1
  owned_file_cas recover "$CORPUS_ADOPTION_INTENT" || return 1
  if [ -e "$CORPUS_RECEIPT" ] || [ -L "$CORPUS_RECEIPT" ]; then
    receipt_state="$(corpus_receipt_state 2>/dev/null || true)"
    if [ "$receipt_state" = legacy ]; then
      echo "legacy corpus receipt requires locked v2 migration" >&2
      return 1
    fi
  fi
  if { [ -e "$bootstrap_stage" ] || [ -L "$bootstrap_stage" ]; } \
      && { [ ! -e "$CORPUS_BOOTSTRAP_INTENT" ] \
           && [ ! -L "$CORPUS_BOOTSTRAP_INTENT" ]; }; then
    echo "unattributed corpus bootstrap workspace is present; preserved" >&2
    return 1
  fi
  if { [ -e "$CORPUS_BOOTSTRAP_INTENT" ] \
        || [ -L "$CORPUS_BOOTSTRAP_INTENT" ]; } \
      && { [ -e "$CORPUS_ADOPTION_INTENT" ] \
        || [ -L "$CORPUS_ADOPTION_INTENT" ]; }; then
    echo "conflicting corpus bootstrap and adoption intents" >&2
    return 1
  fi
  if corpus_receipt_valid; then
    retire_corpus_bootstrap_intent || return 1
    retire_corpus_adoption_intent || return 1
    return 0
  fi
  if [ -e "$CORPUS_BOOTSTRAP_INTENT" ] \
      || [ -L "$CORPUS_BOOTSTRAP_INTENT" ]; then
    if [ -e "$CORPUS_RECEIPT" ] || [ -L "$CORPUS_RECEIPT" ]; then
      echo "invalid corpus receipt conflicts with bootstrap intent" >&2
      return 1
    fi
    corpus_bootstrap_intent_valid >/dev/null || {
      echo "refusing corpus state that does not match its bootstrap intent" >&2
      return 1
    }
    SIA_CORPUS_NEEDS_RECEIPT=1
    SIA_CORPUS_BOOTSTRAP_NEEDED=1
    return 0
  fi
  if [ -e "$CORPUS_ADOPTION_INTENT" ] \
      || [ -L "$CORPUS_ADOPTION_INTENT" ]; then
    if [ -e "$CORPUS_RECEIPT" ] || [ -L "$CORPUS_RECEIPT" ]; then
      echo "invalid corpus receipt conflicts with adoption intent" >&2
      return 1
    fi
    corpus_adoption_intent_valid || {
      echo "refusing corpus changed after durable adoption consent" >&2
      return 1
    }
    SIA_CORPUS_NEEDS_RECEIPT=1
    SIA_CORPUS_ADOPTION_NEEDED=1
    return 0
  fi
  if [ ! -e "$SHARE/corpus" ] && [ ! -L "$SHARE/corpus" ]; then
    SIA_CORPUS_NEEDS_RECEIPT=1
    SIA_CORPUS_BOOTSTRAP_NEEDED=1
    return 0
  fi
  if [ ! -d "$SHARE/corpus" ] || [ -L "$SHARE/corpus" ]; then
    echo "refusing unsafe SIA corpus root" >&2
    return 1
  fi
  if ! find "$SHARE/corpus" -mindepth 1 -print -quit | grep -q .; then
    SIA_CORPUS_NEEDS_RECEIPT=1
    SIA_CORPUS_BOOTSTRAP_NEEDED=1
    return 0
  fi
  if corpus_receipt_valid; then
    return 0
  fi
  if [ -L "$CORPUS_RECEIPT" ] \
      || { [ -e "$CORPUS_RECEIPT" ] && [ ! -f "$CORPUS_RECEIPT" ]; }; then
    echo "refusing unsafe corpus ownership receipt" >&2
    return 1
  fi
  # One exact legacy-upgrade lane: the old installer created this README,
  # git repository, and valid signed SIA ledger together. This is stronger
  # than guessing from directory names and avoids breaking existing brains.
  if [ -d "$SHARE/corpus/.git" ] && [ ! -L "$SHARE/corpus/.git" ] \
      && [ -f "$SHARE/corpus/README.md" ] \
      && [ ! -L "$SHARE/corpus/README.md" ] \
      && owned_metadata line "$SHARE/corpus/README.md" \
        "# SIA corpus — this machine's memory" \
      && python3 "$REPO/bin/sia-ledger" verify "$SHARE" --quiet \
        >/dev/null 2>&1; then
    write_corpus_adoption_intent legacy || return 1
    SIA_CORPUS_NEEDS_RECEIPT=1
    SIA_CORPUS_ADOPTION_NEEDED=1
    echo "  exact legacy SIA corpus recognized for ownership adoption"
    return 0
  fi
  if [ "${SIA_ADOPT_EXISTING_CORPUS:-0}" = "1" ] \
      && [ -d "$SHARE/corpus/.git" ] && [ ! -L "$SHARE/corpus/.git" ]; then
    write_corpus_adoption_intent explicit || return 1
    SIA_CORPUS_NEEDS_RECEIPT=1
    SIA_CORPUS_ADOPTION_NEEDED=1
    echo "  adopting existing git corpus by explicit operator consent"
    return 0
  fi
  echo "refusing nonempty corpus without a valid SIA ownership receipt" >&2
  echo "move it aside, or inspect it and explicitly adopt its git history with:" >&2
  echo "  SIA_ADOPT_EXISTING_CORPUS=1 ./install.sh" >&2
  return 1
}

gbrain_bootstrap_intent_fields() {
  local record="${1:-$GBRAIN_BOOTSTRAP_INTENT}"
  python3 - "$record" "$SHARE/.gbrain" "$GBRAIN_BOOTSTRAP_STAGE" <<'PY'
import os
import re
import stat
import sys

record, target, stage = map(os.path.abspath, sys.argv[1:])
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_NOFOLLOW", 0)
         | getattr(os, "O_NONBLOCK", 0))
descriptor = os.open(record, flags)
try:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() \
            or before.st_nlink != 1 \
            or stat.S_IMODE(before.st_mode) != 0o600 \
            or before.st_size > 65_536:
        raise ValueError("unsafe gbrain bootstrap intent")
    chunks = []
    remaining = 65_537
    while remaining:
        chunk = os.read(descriptor, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    content = b"".join(chunks)
    after = os.fstat(descriptor)
    current = os.stat(record, follow_symlinks=False)
    generation = lambda value: (
        value.st_dev, value.st_ino, value.st_mode, value.st_uid,
        value.st_nlink, value.st_size, value.st_mtime_ns,
        value.st_ctime_ns)
    if len(content) != before.st_size or len(content) > 65_536 \
            or generation(before) != generation(after) \
            or generation(after) != generation(current):
        raise ValueError("gbrain bootstrap intent changed while inspected")
finally:
    os.close(descriptor)
try:
    text = content.decode("utf-8", "strict")
except UnicodeError as error:
    raise ValueError("gbrain bootstrap intent is not strict UTF-8") from error
tree = r"(?:absent|tree:(?:[0-9]+:){8}[0-9a-f]{64})"
pattern = re.compile(
    r"managed-by=khephri[.]sia\nkind=gbrain-bootstrap-v1\ntarget="
    + re.escape(target) + r"\nstage=" + re.escape(stage)
    + r"\nphase=(prepared|initializing|publishing|probing|published)\ntree=(" + tree
    + r")\n")
matched = pattern.fullmatch(text)
if matched is None:
    raise ValueError("gbrain bootstrap intent bytes are not exact")
phase, generation_token = matched.groups()
if (phase in {"prepared", "initializing"}) \
        != (generation_token == "absent"):
    raise ValueError("gbrain bootstrap intent phase/token mismatch")
print(phase + "\t" + generation_token)
PY
}

gbrain_bootstrap_intent_valid() {
  gbrain_bootstrap_intent_fields "${1:-$GBRAIN_BOOTSTRAP_INTENT}" \
    >/dev/null
}

set_gbrain_bootstrap_intent() {
  local phase="$1" tree="$2" stage expected payload installed fields
  case "$phase" in
    prepared|initializing) [ "$tree" = absent ] || return 1 ;;
    publishing|probing|published)
      [[ "$tree" =~ ^tree:([0-9]+:){8}[0-9a-f]{64}$ ]] || return 1 ;;
    *) return 1 ;;
  esac
  stage="$MANAGED_DIR/.gbrain-bootstrap.intent.stage"
  owned_file_cas recover "$GBRAIN_BOOTSTRAP_INTENT" || return 1
  if [ -e "$GBRAIN_BOOTSTRAP_INTENT" ] \
      || [ -L "$GBRAIN_BOOTSTRAP_INTENT" ]; then
    gbrain_bootstrap_intent_valid || return 1
    expected="$(owned_metadata generation "$GBRAIN_BOOTSTRAP_INTENT")" \
      || return 1
  else
    expected=absent
  fi
  payload="$(printf 'managed-by=khephri.sia\nkind=gbrain-bootstrap-v1\ntarget=%s\nstage=%s\nphase=%s\ntree=%s' \
    "$SHARE/.gbrain" "$GBRAIN_BOOTSTRAP_STAGE" "$phase" "$tree")"
  if [ -e "$stage" ] || [ -L "$stage" ]; then
    if ! owned_metadata exact "$stage" "$payload"; then
      gbrain_bootstrap_intent_valid "$stage" || {
        echo "fixed gbrain bootstrap intent stage is invalid; preserved" >&2
        return 1
      }
      remove_owned_fixed_metadata "$stage" || return 1
      durable_fixed_metadata_stage "$stage" "$payload" || return 1
    fi
  else
    durable_fixed_metadata_stage "$stage" "$payload" || return 1
  fi
  if ! installed="$(owned_file_cas publish "$stage" \
      "$GBRAIN_BOOTSTRAP_INTENT" "$expected")"; then
    [ ! -e "$stage" ] \
      || echo "gbrain bootstrap intent stage retained at $stage" >&2
    return 1
  fi
  fields="$(gbrain_bootstrap_intent_fields)" || return 1
  [ "$fields" = "$phase"$'\t'"$tree" ] || return 1
  if [ -e "$stage" ] || [ -L "$stage" ]; then
    gbrain_bootstrap_intent_valid "$stage" || return 1
    remove_owned_fixed_metadata "$stage" || return 1
  fi
}

retire_gbrain_bootstrap_intent() {
  local expected archive
  archive="$MANAGED_DIR/.gbrain-bootstrap.retired"
  if [ -e "$archive" ] || [ -L "$archive" ]; then
    gbrain_bootstrap_intent_valid "$archive" || {
      echo "fixed retired gbrain bootstrap intent is invalid; preserved" >&2
      return 1
    }
    remove_owned_fixed_metadata "$archive" || return 1
  fi
  [ -e "$GBRAIN_BOOTSTRAP_INTENT" ] \
    || [ -L "$GBRAIN_BOOTSTRAP_INTENT" ] || return 0
  expected="$(owned_metadata generation "$GBRAIN_BOOTSTRAP_INTENT")" \
    || return 1
  owned_file_cas archive "$archive" "$GBRAIN_BOOTSTRAP_INTENT" \
    "$expected" || return 1
  gbrain_bootstrap_intent_valid "$archive" || return 1
  remove_owned_fixed_metadata "$archive"
}

gbrain_tree_generation_matches() {
  python3 - "$1" "$2" <<'PY'
import re
import sys

pattern = re.compile(
    r"tree:(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):"
    r"(\d+):([0-9a-f]{64})")
actual = pattern.fullmatch(sys.argv[1])
expected = pattern.fullmatch(sys.argv[2])
if actual is None or expected is None:
    raise SystemExit(1)
left = actual.groups()
right = expected.groups()
raise SystemExit(0 if left[:6] == right[:6] and left[7:] == right[7:] else 1)
PY
}

gbrain_tree_root_matches() {
  python3 - "$1" "$2" <<'PY'
import re
import sys

pattern = re.compile(
    r"tree:(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):"
    r"(\d+):([0-9a-f]{64})")
actual = pattern.fullmatch(sys.argv[1])
expected = pattern.fullmatch(sys.argv[2])
if actual is None or expected is None:
    raise SystemExit(1)
raise SystemExit(0 if actual.groups()[:4] == expected.groups()[:4] else 1)
PY
}

gbrain_frontdoor_valid() {
  local home="$1" expected_path before output after
  expected_path="$home/.gbrain/brain.pglite"
  before="$(owned_tree_generation "$home/.gbrain")" || return 1
  output="$(bounded_command_capture env \
    -u GBRAIN_DATABASE_URL -u DATABASE_URL -u GBRAIN_BRAIN_ID \
    GBRAIN_HOME="$home" GBRAIN_SKIP_STARTUP_HOOKS=1 \
    "$GBRAIN_BIN" engine status --probe --json)" || return 1
  after="$(owned_tree_generation "$home/.gbrain")" || return 1
  gbrain_tree_root_matches "$after" "$before" || {
    echo "gbrain root changed during its supported health probe" >&2
    return 1
  }
  python3 - "$expected_path" 3<<<"$output" <<'PY'
import json
import os
import sys

expected = os.path.abspath(sys.argv[1])


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate gbrain status key: {key}")
        value[key] = item
    return value


def reject_constant(value):
    raise ValueError(f"non-finite gbrain status number: {value}")


try:
    with os.fdopen(3, "r", encoding="utf-8", errors="strict") as stream:
        report = json.load(
            stream, object_pairs_hook=unique_object,
            parse_constant=reject_constant)
except (UnicodeError, json.JSONDecodeError, ValueError) as error:
    raise SystemExit(f"invalid gbrain engine status: {error}") from error
if not isinstance(report, dict) \
        or report.get("schema_version") != 1 \
        or report.get("effective_engine") != "pglite" \
        or report.get("config_file_engine") != "pglite" \
        or report.get("database_path") != expected \
        or report.get("thin_client") is not False \
        or not isinstance(report.get("probe"), dict) \
        or report["probe"].get("ok") is not True:
    raise SystemExit("gbrain engine status did not verify the expected PGLite store")
PY
}

prepare_gbrain_bootstrap_home() {
  python3 - "$SHARE" "$GBRAIN_BOOTSTRAP_HOME" <<'PY'
import os
import stat
import sys

root, home = map(os.path.abspath, sys.argv[1:])
if os.path.dirname(home) != root:
    raise SystemExit("gbrain bootstrap home is not a share-root child")
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_DIRECTORY", 0)
         | getattr(os, "O_NOFOLLOW", 0))
root_fd = os.open(root, flags)
try:
    name = os.path.basename(home)
    try:
        os.mkdir(name, 0o700, dir_fd=root_fd)
        os.fsync(root_fd)
    except FileExistsError:
        pass
    descriptor = os.open(name, flags, dir_fd=root_fd)
    try:
        info = os.fstat(descriptor)
        current = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        generation = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() \
                or stat.S_IMODE(info.st_mode) != 0o700 \
                or generation(info) != generation(current):
            raise ValueError("unsafe gbrain bootstrap home")
    finally:
        os.close(descriptor)
finally:
    os.close(root_fd)
PY
}

move_bootstrap_tree_noreplace() {
  local source="$1" destination="$2"
  python3 - "$source" "$destination" <<'PY'
import ctypes
import os
import stat
import sys

source, destination = map(os.path.abspath, sys.argv[1:])
source_parent, source_name = os.path.dirname(source), os.path.basename(source)
destination_parent = os.path.dirname(destination)
destination_name = os.path.basename(destination)
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_DIRECTORY", 0)
         | getattr(os, "O_NOFOLLOW", 0))
source_fd = os.open(source_parent, flags)
destination_fd = os.open(destination_parent, flags)
try:
    info = os.stat(source_name, dir_fd=source_fd, follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise ValueError("unsafe bootstrap publication tree")
    try:
        os.stat(destination_name, dir_fd=destination_fd,
                follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError("bootstrap move target is occupied")
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = libc.renameat2
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p,
                          ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(source_fd, os.fsencode(source_name), destination_fd,
                 os.fsencode(destination_name), 1):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), (source, destination))
    os.fsync(source_fd)
    if destination_fd != source_fd:
        os.fsync(destination_fd)
finally:
    os.close(destination_fd)
    os.close(source_fd)
PY
}

move_gbrain_bootstrap_tree() {
  move_bootstrap_tree_noreplace "$@"
}

remove_empty_gbrain_bootstrap_home() {
  python3 - "$SHARE" "$GBRAIN_BOOTSTRAP_HOME" <<'PY'
import os
import stat
import sys

root, home = map(os.path.abspath, sys.argv[1:])
name = os.path.basename(home)
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_DIRECTORY", 0)
         | getattr(os, "O_NOFOLLOW", 0))
root_fd = os.open(root, flags)
try:
    try:
        descriptor = os.open(name, flags, dir_fd=root_fd)
    except FileNotFoundError:
        raise SystemExit(0)
    try:
        info = os.fstat(descriptor)
        current = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() \
                or (info.st_dev, info.st_ino) != \
                   (current.st_dev, current.st_ino):
            raise ValueError("unsafe gbrain bootstrap home during cleanup")
    finally:
        os.close(descriptor)
    os.rmdir(name, dir_fd=root_fd)
    os.fsync(root_fd)
finally:
    os.close(root_fd)
PY
}

preflight_gbrain_bootstrap() {
  local phase tree fields current
  SIA_GBRAIN_BOOTSTRAP_NEEDED=0
  owned_file_cas recover "$GBRAIN_BOOTSTRAP_INTENT" || return 1
  owned_tree_cas recover "$SHARE/.gbrain" || return 1
  if [ -e "$SHARE/.gbrain" ] || [ -L "$SHARE/.gbrain" ]; then
    if [ -e "$GBRAIN_BOOTSTRAP_INTENT" ] \
        || [ -L "$GBRAIN_BOOTSTRAP_INTENT" ]; then
      fields="$(gbrain_bootstrap_intent_fields)" || return 1
      IFS=$'\t' read -r phase tree <<< "$fields"
      case "$phase" in
        publishing)
          current="$(owned_tree_generation "$SHARE/.gbrain")" || return 1
          gbrain_tree_generation_matches "$current" "$tree" || {
            echo "gbrain store does not match the publishing intent; preserved" >&2
            return 1
          }
          set_gbrain_bootstrap_intent probing "$current" || return 1
          phase=probing
          tree="$current"
          ;;
        probing)
          current="$(owned_tree_generation "$SHARE/.gbrain")" || return 1
          gbrain_tree_root_matches "$current" "$tree" || {
            echo "gbrain root does not match its probing intent; preserved" >&2
            return 1
          }
          ;;
        published)
          current="$(owned_tree_generation "$SHARE/.gbrain")" || return 1
          [ "$current" = "$tree" ] || {
            echo "gbrain store does not match its published intent; preserved" >&2
            return 1
          }
          remove_empty_gbrain_bootstrap_home || return 1
          retire_gbrain_bootstrap_intent || return 1
          return 0
          ;;
        prepared|initializing)
          echo "a gbrain store appeared before its prepared intent published it; preserved" >&2
          return 1
          ;;
      esac
      gbrain_frontdoor_valid "$SHARE" || {
        echo "interrupted gbrain bootstrap did not produce a valid PGLite store; preserved" >&2
        return 1
      }
      current="$(owned_tree_generation "$SHARE/.gbrain")" || return 1
      gbrain_tree_root_matches "$current" "$tree" || {
        echo "gbrain root changed while recovering its probe; preserved" >&2
        return 1
      }
      set_gbrain_bootstrap_intent published "$current" || return 1
      remove_empty_gbrain_bootstrap_home || return 1
      retire_gbrain_bootstrap_intent || return 1
      return 0
    fi
    if [ -e "$GBRAIN_BOOTSTRAP_HOME" ] \
        || [ -L "$GBRAIN_BOOTSTRAP_HOME" ] \
        || [ -e "$GBRAIN_BOOTSTRAP_STAGE" ] \
        || [ -L "$GBRAIN_BOOTSTRAP_STAGE" ] \
        || [ -e "$GBRAIN_BOOTSTRAP_BACKUP" ] \
        || [ -L "$GBRAIN_BOOTSTRAP_BACKUP" ]; then
      echo "unattributed gbrain bootstrap workspace is present; preserved" >&2
      return 1
    fi
    gbrain_frontdoor_valid "$SHARE" || {
      echo "preexisting gbrain store failed its supported health probe; preserved" >&2
      return 1
    }
    return 0
  fi
  if [ -e "$GBRAIN_BOOTSTRAP_BACKUP" ] \
      || [ -L "$GBRAIN_BOOTSTRAP_BACKUP" ]; then
    echo "unexpected gbrain bootstrap prior tree is present; preserved" >&2
    return 1
  fi
  if [ ! -e "$GBRAIN_BOOTSTRAP_INTENT" ] \
      && [ ! -L "$GBRAIN_BOOTSTRAP_INTENT" ]; then
    if [ -e "$GBRAIN_BOOTSTRAP_HOME" ] \
        || [ -L "$GBRAIN_BOOTSTRAP_HOME" ] \
        || [ -e "$GBRAIN_BOOTSTRAP_STAGE" ] \
        || [ -L "$GBRAIN_BOOTSTRAP_STAGE" ]; then
      echo "unattributed gbrain bootstrap workspace is present; preserved" >&2
      return 1
    fi
    set_gbrain_bootstrap_intent prepared absent || return 1
  fi
  fields="$(gbrain_bootstrap_intent_fields)" || return 1
  IFS=$'\t' read -r phase tree <<< "$fields"
  case "$phase" in
    prepared)
      if [ -e "$GBRAIN_BOOTSTRAP_HOME" ] \
          || [ -L "$GBRAIN_BOOTSTRAP_HOME" ] \
          || [ -e "$GBRAIN_BOOTSTRAP_STAGE" ] \
          || [ -L "$GBRAIN_BOOTSTRAP_STAGE" ]; then
        echo "workspace appeared before gbrain initialization was authorized; preserved" >&2
        return 1
      fi
      ;;
    initializing)
      if [ -e "$GBRAIN_BOOTSTRAP_STAGE" ] \
          || [ -L "$GBRAIN_BOOTSTRAP_STAGE" ]; then
        echo "gbrain publication stage appeared during initialization; preserved" >&2
        return 1
      fi
      ;;
    publishing) ;;
    probing|published)
      echo "$phase gbrain bootstrap intent has no target; refusing" >&2
      return 1
      ;;
    *) return 1 ;;
  esac
  SIA_GBRAIN_BOOTSTRAP_NEEDED=1
}

complete_gbrain_bootstrap() {
  local phase tree fields inner current result installed
  inner="$GBRAIN_BOOTSTRAP_HOME/.gbrain"
  fields="$(gbrain_bootstrap_intent_fields)" || return 1
  IFS=$'\t' read -r phase tree <<< "$fields"
  if [ -e "$SHARE/.gbrain" ] || [ -L "$SHARE/.gbrain" ]; then
    echo "gbrain target appeared before bootstrap completion; preserved" >&2
    return 1
  fi
  if [ "$phase" = prepared ]; then
    if [ -e "$GBRAIN_BOOTSTRAP_HOME" ] \
        || [ -L "$GBRAIN_BOOTSTRAP_HOME" ] \
        || [ -e "$GBRAIN_BOOTSTRAP_STAGE" ] \
        || [ -L "$GBRAIN_BOOTSTRAP_STAGE" ]; then
      echo "workspace appeared before gbrain initialization was authorized; preserved" >&2
      return 1
    fi
    set_gbrain_bootstrap_intent initializing absent || return 1
    phase=initializing
  fi
  if [ "$phase" = initializing ]; then
    if [ -e "$GBRAIN_BOOTSTRAP_STAGE" ] \
        || [ -L "$GBRAIN_BOOTSTRAP_STAGE" ]; then
      echo "gbrain publication stage appeared before validation; preserved" >&2
      return 1
    fi
    prepare_gbrain_bootstrap_home || return 1
    run_with_deadline 1800 env \
      -u GBRAIN_DATABASE_URL -u DATABASE_URL -u GBRAIN_BRAIN_ID \
      GBRAIN_HOME="$GBRAIN_BOOTSTRAP_HOME" GBRAIN_SKIP_STARTUP_HOOKS=1 \
      "$GBRAIN_BIN" init --pglite --force \
      --embedding-model ollama:nomic-embed-text:v1.5 || return 1
    gbrain_frontdoor_valid "$GBRAIN_BOOTSTRAP_HOME" || {
      echo "gbrain bootstrap stage failed its supported health probe; retained" >&2
      return 1
    }
    tree="$(owned_tree_generation "$inner")" || return 1
    set_gbrain_bootstrap_intent publishing "$tree" || return 1
    phase=publishing
  fi
  [ "$phase" = publishing ] || return 1
  if [ -e "$inner" ] || [ -L "$inner" ]; then
    current="$(owned_tree_generation "$inner")" || return 1
    gbrain_tree_generation_matches "$current" "$tree" || {
      echo "gbrain bootstrap stage changed after validation; preserved" >&2
      return 1
    }
    if [ -e "$GBRAIN_BOOTSTRAP_STAGE" ] \
        || [ -L "$GBRAIN_BOOTSTRAP_STAGE" ]; then
      echo "gbrain bootstrap has two publication stages; preserved" >&2
      return 1
    fi
    move_gbrain_bootstrap_tree "$inner" "$GBRAIN_BOOTSTRAP_STAGE" \
      || return 1
  fi
  current="$(owned_tree_generation "$GBRAIN_BOOTSTRAP_STAGE")" || return 1
  gbrain_tree_generation_matches "$current" "$tree" || {
    echo "moved gbrain bootstrap stage changed; preserved" >&2
    return 1
  }
  result="$(owned_tree_cas publish "$GBRAIN_BOOTSTRAP_STAGE" \
    "$SHARE/.gbrain" "$GBRAIN_BOOTSTRAP_BACKUP" absent)" || return 1
  IFS=$'\t' read -r installed _ <<< "$result"
  [ "$(owned_tree_generation "$SHARE/.gbrain")" = "$installed" ] || {
    echo "gbrain store changed immediately after publication; preserved" >&2
    return 1
  }
  set_gbrain_bootstrap_intent probing "$installed" || return 1
  gbrain_frontdoor_valid "$SHARE" || {
    echo "published gbrain store failed its supported health probe; preserved" >&2
    return 1
  }
  current="$(owned_tree_generation "$SHARE/.gbrain")" || return 1
  gbrain_tree_root_matches "$current" "$installed" || {
    echo "gbrain root changed while completing its health probe; preserved" >&2
    return 1
  }
  set_gbrain_bootstrap_intent published "$current" || return 1
  remove_empty_gbrain_bootstrap_home || return 1
  retire_gbrain_bootstrap_intent
}

runtime_tree_digest() {
  python3 - "$1" <<'PY'
import hashlib
import os
import stat
import sys

root = sys.argv[1]
legacy_names = ("sia-brainstem", "sia-ledger", "sia-mcp", "siabench.py",
                "sialib.py", "siamind.py", "siaqueue.py", "siatakes.py")
modern_names = ("sia-brainstem", "sia-brainstem.py", "sia-cli",
                "sia-ledger", "sia-mcp", "siabench.py", "sialib.py",
                "siamind.py", "siaqueue.py", "siatakes.py")
modern = any(os.path.lexists(os.path.join(root, name))
             for name in ("sia-brainstem.py", "sia-cli"))
names = modern_names if modern else legacy_names
digest = hashlib.sha256(
    b"sia-runtime-v2\0" if modern else b"sia-runtime-v1\0")
uid = os.geteuid()
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_NOFOLLOW", 0))

def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)

for name in names:
    path = os.path.join(root, name)
    descriptor = os.open(path, flags)
    member = hashlib.sha256()
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != uid:
            raise SystemExit(f"unsafe runtime member: {name}")
        while True:
            chunk = os.read(descriptor, 1_048_576)
            if not chunk:
                break
            member.update(chunk)
        after = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(current.st_mode) or current.st_uid != uid \
                or generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise SystemExit(f"runtime member changed while hashing: {name}")
    finally:
        os.close(descriptor)
    digest.update(name.encode() + b"\0" + member.digest())
print(digest.hexdigest())
PY
}

runtime_receipt_valid() {
  local digest
  [ -d "$BINDIR" ] && [ ! -L "$BINDIR" ] \
    && [ -f "$RUNTIME_RECEIPT" ] && [ ! -L "$RUNTIME_RECEIPT" ] || return 1
  digest="$(runtime_tree_digest "$BINDIR")" || return 1
  [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || return 1
  owned_metadata runtime "$RUNTIME_RECEIPT" "$BINDIR" "$digest"
}

fenced_managed_file_authorized() {
  python3 - "$LAUNCH_FENCE_JOURNAL" "$1" "$2" "$3" <<'PY'
import json
import os
import stat
import sys

journal, receipt, kind, target = sys.argv[1:]
uid = os.geteuid()
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_NOFOLLOW", 0))

def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)

def read_owned(path, limit):
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != uid \
                or before.st_size > limit:
            raise ValueError("unsafe managed metadata")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1_048_576))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        if len(content) != before.st_size or len(content) > limit \
                or not stat.S_ISREG(current.st_mode) \
                or current.st_uid != uid \
                or generation(before) != generation(after) \
                or generation(after) != generation(current) \
                or b"\0" in content:
            raise ValueError("managed metadata changed while reading")
        return content
    finally:
        os.close(descriptor)

try:
    payload = json.loads(read_owned(journal, 1_048_576))
    entry = next(value for value in payload.get("entries", [])
                 if value.get("path") == target)
    current = os.lstat(target)
    contents = read_owned(receipt, 65_536).decode("utf-8", "strict")
except (FileNotFoundError, StopIteration, OSError, ValueError,
        json.JSONDecodeError):
    raise SystemExit(1)
expected = (f"managed-by=khephri.sia\nkind={kind}\npath={target}\n"
            f"sha256={entry.get('sha256', '')}\n")
if payload.get("schema") != "sia-launch-fence-v1" \
        or not stat.S_ISREG(current.st_mode) \
        or current.st_uid != os.geteuid() \
        or stat.S_IMODE(current.st_mode) != 0 \
        or (current.st_dev, current.st_ino) != (
            entry.get("device"), entry.get("inode")) \
        or contents != expected:
    raise SystemExit(1)
PY
}

fenced_runtime_authorized() {
  python3 - "$LAUNCH_FENCE_JOURNAL" "$RUNTIME_RECEIPT" "$BINDIR" <<'PY'
import json
import os
import stat
import sys

journal, receipt, runtime = sys.argv[1:]
uid = os.geteuid()
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_NOFOLLOW", 0))

def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)

def read_owned(path, limit):
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != uid \
                or before.st_size > limit:
            raise ValueError("unsafe managed metadata")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1_048_576))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        if len(content) != before.st_size or len(content) > limit \
                or not stat.S_ISREG(current.st_mode) \
                or current.st_uid != uid \
                or generation(before) != generation(after) \
                or generation(after) != generation(current) \
                or b"\0" in content:
            raise ValueError("managed metadata changed while reading")
        return content
    finally:
        os.close(descriptor)

try:
    payload = json.loads(read_owned(journal, 1_048_576))
    before_digest = payload["runtime_before_digest"]
    contents = read_owned(receipt, 65_536).decode("utf-8", "strict")
except (FileNotFoundError, OSError, ValueError, KeyError,
        json.JSONDecodeError):
    raise SystemExit(1)
expected = (f"managed-by=khephri.sia\nkind=runtime\npath={runtime}\n"
            f"sha256={before_digest}\n")
if payload.get("schema") != "sia-launch-fence-v1" \
        or not isinstance(before_digest, str) or not before_digest \
        or contents != expected:
    raise SystemExit(1)
entries = {entry.get("path"): entry for entry in payload.get("entries", [])
           if isinstance(entry, dict)}
for name in ("sia-brainstem", "sia-mcp"):
    path = os.path.join(runtime, name)
    if not os.path.lexists(path):
        continue
    entry = entries.get(path)
    current = os.lstat(path)
    if entry is None or not stat.S_ISREG(current.st_mode) \
            or current.st_uid != os.geteuid() \
            or stat.S_IMODE(current.st_mode) != 0 \
            or (current.st_dev, current.st_ino) != (
                entry.get("device"), entry.get("inode")):
        raise SystemExit(1)
PY
}

write_runtime_receipt() {
  local installed_tree="$1" desired_digest="$2" current_tree current_digest
  local receipt_installed
  [[ "$desired_digest" =~ ^[0-9a-f]{64}$ ]] || return 1
  current_tree="$(owned_tree_generation "$BINDIR")" || return 1
  [ "$current_tree" = "$installed_tree" ] || {
    echo "runtime changed after generation-bound publication; refusing receipt" >&2
    return 1
  }
  current_digest="$(runtime_tree_digest "$BINDIR")" || return 1
  [ "$current_digest" = "$desired_digest" ] || {
    echo "runtime differs from the staged digest; refusing receipt" >&2
    return 1
  }
  write_managed_receipt "$RUNTIME_RECEIPT" runtime "$BINDIR" \
    "$desired_digest" receipt_installed || return 1
  current_tree="$(owned_tree_generation "$BINDIR")" || return 1
  if [ "$current_tree" != "$installed_tree" ]; then
    retire_exact_receipt "$RUNTIME_RECEIPT" "$receipt_installed" || true
    echo "runtime changed across receipt publication; receipt retired" >&2
    return 1
  fi
}

preflight_runtime() {
  local before after authorized=0
  mkdir -p "$SHARE"
  owned_tree_cas recover "$BINDIR" || return 1
  if [ -e "$BINDIR" ] || [ -L "$BINDIR" ]; then
    if [ ! -d "$BINDIR" ] || [ -L "$BINDIR" ]; then
      echo "refusing unsafe SIA runtime root" >&2
      return 1
    fi
    before="$(owned_tree_generation "$BINDIR")" || return 1
    if runtime_receipt_valid || fenced_runtime_authorized; then
      authorized=1
    elif [ "${SIA_REPLACE_RUNTIME:-0}" = "1" ]; then
      authorized=1
    fi
    if [ "$authorized" -ne 1 ]; then
      echo "existing runtime tree is unowned, locally modified, or has an invalid receipt; preserved" >&2
      echo "inspect it, then explicitly replace with SIA_REPLACE_RUNTIME=1 ./install.sh" >&2
      return 1
    fi
    after="$(owned_tree_generation "$BINDIR")" || return 1
    if [ "$before" != "$after" ]; then
      echo "runtime tree changed during ownership preflight; preserved" >&2
      return 1
    fi
    SIA_RUNTIME_TREE_EXPECTED="$after"
  elif [ -e "$RUNTIME_RECEIPT" ] || [ -L "$RUNTIME_RECEIPT" ]; then
    echo "stale or unsafe runtime ownership receipt; refusing install" >&2
    return 1
  else
    SIA_RUNTIME_TREE_EXPECTED=absent
  fi
}

recover_publication_receipts_from_fence() {
  local recovered desired_runtime desired_cli fenced_cli current
  if [ ! -e "$LAUNCH_FENCE_JOURNAL" ] \
      && [ ! -L "$LAUNCH_FENCE_JOURNAL" ]; then
    return 0
  fi
  recovered="$(python3 - "$LAUNCH_FENCE_JOURNAL" \
      "$LIFECYCLE_TOMBSTONE" <<'PY'
import json
import os
import re
import stat
import sys

journal, tombstone = sys.argv[1:]
uid = os.geteuid()
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_NOFOLLOW", 0))

def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)

def read_journal(path):
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != uid \
                or before.st_size > 1_048_576:
            raise SystemExit("unsafe install launch-fence journal")
        chunks = []
        remaining = 1_048_577
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1_048_576))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        if len(content) != before.st_size or len(content) > 1_048_576 \
                or not stat.S_ISREG(current.st_mode) \
                or current.st_uid != uid or b"\0" in content \
                or generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise SystemExit("install launch-fence journal changed")
        return json.loads(content)
    finally:
        os.close(descriptor)

payload = read_journal(journal)
marker = os.lstat(tombstone)
if not stat.S_ISREG(marker.st_mode) or marker.st_uid != uid:
    raise SystemExit("launch-fence journal lacks its lifecycle tombstone")
if not isinstance(payload, dict) \
        or payload.get("schema") != "sia-launch-fence-v1" \
        or set(payload) != {"schema", "runtime_before_digest",
                            "runtime_digest", "cli_digest", "entries"} \
        or not isinstance(payload["entries"], list):
    raise SystemExit("invalid install launch-fence journal")
for key in ("runtime_before_digest", "runtime_digest", "cli_digest"):
    value = payload[key]
    if not isinstance(value, str) \
            or value and re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise SystemExit("invalid install launch-fence digest")
for entry in payload["entries"]:
    if not isinstance(entry, dict) \
            or set(entry) != {"path", "device", "inode", "mode", "sha256"} \
            or not isinstance(entry["path"], str) \
            or any(isinstance(entry[key], bool)
                   or not isinstance(entry[key], int) or entry[key] < 0
                   for key in ("device", "inode", "mode")) \
            or entry["mode"] > 0o7777 \
            or not isinstance(entry["sha256"], str) \
            or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None:
        raise SystemExit("invalid install launch-fence entry")
fenced_cli = ""
for entry in payload["entries"]:
    if os.path.abspath(entry["path"]) == os.path.abspath(
            os.path.join(os.path.expanduser("~"), ".local", "bin", "sia")):
        try:
            current = os.lstat(entry["path"])
        except FileNotFoundError:
            break
        if stat.S_ISREG(current.st_mode) \
                and stat.S_IMODE(current.st_mode) == 0 \
                and (current.st_dev, current.st_ino) == (
                    entry["device"], entry["inode"]):
            fenced_cli = entry["sha256"]
        break
print(payload["runtime_digest"] + "\t" + payload["cli_digest"]
      + "\t" + fenced_cli)
PY
  )" || return 1
  IFS=$'\t' read -r desired_runtime desired_cli fenced_cli <<< "$recovered"
  if [ -n "$desired_runtime" ] \
      && [ -d "$BINDIR" ] && [ ! -L "$BINDIR" ]; then
    current="$(runtime_tree_digest "$BINDIR" 2>/dev/null || true)"
    if [ -n "$current" ] && [ "$current" = "$desired_runtime" ]; then
      write_managed_receipt \
        "$RUNTIME_RECEIPT" runtime "$BINDIR" "$current"
      echo "  recovered exact runtime receipt from interrupted publication"
    fi
  fi
  if [ -n "$desired_cli" ] \
      && [ -f "$CLI_PATH" ] && [ ! -L "$CLI_PATH" ]; then
    if [ "$desired_cli" = "$fenced_cli" ]; then
      current="$fenced_cli"
    else
      current="$(owned_metadata digest "$CLI_PATH")" || return 1
    fi
    if [ "$current" = "$desired_cli" ]; then
      write_managed_receipt "$CLI_RECEIPT" sia-cli "$CLI_PATH" "$current"
      echo "  recovered exact CLI receipt from interrupted publication"
    fi
  fi
}

arm_install_launch_fence() {
  local desired_cli runtime_before=""
  desired_cli="$(owned_metadata digest "$SIA_STABLE_LAUNCHER")" \
    || return 1
  if [ -d "$BINDIR" ] && [ ! -L "$BINDIR" ]; then
    runtime_before="$(runtime_tree_digest "$BINDIR" 2>/dev/null || true)"
    if [ -n "$runtime_before" ]; then
      [[ "$runtime_before" =~ ^[0-9a-f]{64}$ ]] || return 1
    fi
  fi
  SIA_LAUNCH_FENCE_ARMED=1
  python3 - "$LAUNCH_FENCE_JOURNAL" "$desired_cli" "$runtime_before" \
      "$CLI_PATH" "$BINDIR/sia-brainstem" "$BINDIR/sia-mcp" <<'PY'
import hashlib
import json
import os
import re
import stat
import tempfile
import sys

journal, desired_cli, runtime_before, *paths = sys.argv[1:]
uid = os.geteuid()
prior = {}
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_NOFOLLOW", 0))

def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)

def read_journal(path):
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != uid \
                or before.st_size > 1_048_576:
            raise SystemExit("unsafe install launch-fence journal")
        chunks = []
        remaining = 1_048_577
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1_048_576))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        if len(content) != before.st_size or len(content) > 1_048_576 \
                or not stat.S_ISREG(current.st_mode) \
                or current.st_uid != uid or b"\0" in content \
                or generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise SystemExit("install launch-fence journal changed")
        return json.loads(content)
    finally:
        os.close(descriptor)

try:
    payload = read_journal(journal)
except FileNotFoundError:
    pass
else:
    if isinstance(payload, dict) \
            and payload.get("schema") == "sia-launch-fence-v1" \
            and isinstance(payload.get("entries"), list):
        prior = {entry.get("path"): entry for entry in payload["entries"]
                 if isinstance(entry, dict)}
        if not runtime_before:
            runtime_before = str(payload.get("runtime_before_digest", ""))
if runtime_before \
        and re.fullmatch(r"[0-9a-f]{64}", runtime_before) is None:
    raise SystemExit("invalid pre-existing runtime fence digest")

opened = []
entries = []
try:
    for path in paths:
        try:
            path_info = os.lstat(path)
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(path_info.st_mode) or path_info.st_uid != uid:
            raise RuntimeError(f"unsafe legacy launch path: {path}")
        previous = prior.get(path, {})
        current_mode = stat.S_IMODE(path_info.st_mode)
        if current_mode == 0:
            if not isinstance(previous, dict) \
                    or previous.get("device") != path_info.st_dev \
                    or previous.get("inode") != path_info.st_ino \
                    or isinstance(previous.get("mode"), bool) \
                    or not isinstance(previous.get("mode"), int) \
                    or not 0 <= previous["mode"] <= 0o7777 \
                    or re.fullmatch(r"[0-9a-f]{64}",
                                    str(previous.get("sha256", ""))) is None:
                raise RuntimeError(
                    f"unrecognized pre-existing launch fence: {path}")
            descriptor = os.open(
                path, getattr(os, "O_PATH", os.O_RDONLY)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0))
            opened.append((path, descriptor, False))
            info = os.fstat(descriptor)
            if (info.st_dev, info.st_ino) != (
                    path_info.st_dev, path_info.st_ino):
                raise RuntimeError(f"legacy launch path changed: {path}")
            entries.append({"path": path, "device": info.st_dev,
                            "inode": info.st_ino,
                            "mode": previous["mode"],
                            "sha256": previous["sha256"]})
            continue
        descriptor = os.open(path, flags)
        opened.append((path, descriptor, True))
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != uid \
                or (info.st_dev, info.st_ino) != (
                    path_info.st_dev, path_info.st_ino):
            raise RuntimeError(f"unsafe legacy launch path: {path}")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1_048_576):
            digest.update(chunk)
        digest = digest.hexdigest()
        entries.append({"path": path, "device": info.st_dev,
                        "inode": info.st_ino, "mode": current_mode,
                        "sha256": digest})

    payload = {"schema": "sia-launch-fence-v1",
               "runtime_before_digest": runtime_before,
               "runtime_digest": "", "cli_digest": desired_cli,
               "entries": entries}
    parent = os.path.dirname(journal)
    temporary_fd, temporary = tempfile.mkstemp(
        prefix=".launch-fence.tmp.", dir=parent)
    try:
        os.fchmod(temporary_fd, 0o600)
        with os.fdopen(temporary_fd, "w", encoding="utf-8") as stream:
            temporary_fd = -1
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, journal)
        directory = os.open(parent,
                            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        if temporary_fd >= 0:
            os.close(temporary_fd)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise

    for path, descriptor, needs_fence in opened:
        if needs_fence:
            os.fchmod(descriptor, 0)
            os.fsync(descriptor)
        current = os.lstat(path)
        held = os.fstat(descriptor)
        if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino) \
                or stat.S_IMODE(current.st_mode) != 0:
            raise RuntimeError(f"legacy launch path changed while fencing: {path}")
finally:
    for _path, descriptor, _needs_fence in opened:
        os.close(descriptor)
PY
}

update_install_launch_fence_desired() {
  local runtime_digest="$1" cli_digest
  [[ "$runtime_digest" =~ ^[0-9a-f]{64}$ ]] || return 1
  cli_digest="$(owned_metadata digest "$SIA_STABLE_LAUNCHER")" \
    || return 1
  python3 - "$LAUNCH_FENCE_JOURNAL" "$runtime_digest" "$cli_digest" <<'PY'
import json
import os
import stat
import tempfile
import sys

journal, runtime_digest, cli_digest = sys.argv[1:]
uid = os.geteuid()
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_NOFOLLOW", 0))

def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)

descriptor = os.open(journal, flags)
try:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_uid != uid \
            or before.st_size > 1_048_576:
        raise SystemExit("unsafe install launch-fence journal")
    chunks = []
    remaining = 1_048_577
    while remaining:
        chunk = os.read(descriptor, min(remaining, 1_048_576))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    content = b"".join(chunks)
    after = os.fstat(descriptor)
    current = os.stat(journal, follow_symlinks=False)
    if len(content) != before.st_size or len(content) > 1_048_576 \
            or not stat.S_ISREG(current.st_mode) or current.st_uid != uid \
            or b"\0" in content \
            or generation(before) != generation(after) \
            or generation(after) != generation(current):
        raise SystemExit("install launch-fence journal changed")
    payload = json.loads(content)
finally:
    os.close(descriptor)
if payload.get("schema") != "sia-launch-fence-v1" \
        or not isinstance(payload.get("entries"), list):
    raise SystemExit("invalid install launch-fence journal")
payload["runtime_digest"] = runtime_digest
payload["cli_digest"] = cli_digest
parent = os.path.dirname(journal)
temporary_fd, temporary = tempfile.mkstemp(
    prefix=".launch-fence.tmp.", dir=parent)
try:
    os.fchmod(temporary_fd, 0o600)
    with os.fdopen(temporary_fd, "w", encoding="utf-8") as stream:
        temporary_fd = -1
        json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, journal)
    directory = os.open(parent,
                        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
except BaseException:
    if temporary_fd >= 0:
        os.close(temporary_fd)
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
    raise
PY
}

complete_install_launch_fence() {
  local installed_tree="$1" desired_digest="$2"
  [ "$(owned_tree_generation "$BINDIR")" = "$installed_tree" ] || {
    echo "runtime changed before launch-fence completion" >&2
    return 1
  }
  [ "$(runtime_tree_digest "$BINDIR")" = "$desired_digest" ] || {
    echo "runtime digest changed before launch-fence completion" >&2
    return 1
  }
  python3 - "$LAUNCH_FENCE_JOURNAL" "$desired_digest" <<'PY'
import json
import os
import stat
import sys

path, desired_digest = sys.argv[1:]
try:
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0))
except FileNotFoundError:
    raise SystemExit("install launch-fence journal is missing")


def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


try:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() \
            or before.st_size > 1_048_576:
        raise SystemExit("unsafe install launch-fence journal")
    chunks = []
    remaining = 1_048_577
    while remaining:
        chunk = os.read(descriptor, min(remaining, 1_048_576))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    content = b"".join(chunks)
    after = os.fstat(descriptor)
    current = os.stat(path, follow_symlinks=False)
    if len(content) != before.st_size or len(content) > 1_048_576 \
            or generation(before) != generation(after) \
            or generation(after) != generation(current):
        raise SystemExit("install launch-fence journal changed")
    payload = json.loads(content)
finally:
    os.close(descriptor)
if not isinstance(payload, dict) \
        or payload.get("schema") != "sia-launch-fence-v1" \
        or payload.get("runtime_digest") != desired_digest:
    raise SystemExit("launch fence does not bind the published runtime")
parent = os.path.dirname(path)
parent_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    final = os.stat(os.path.basename(path), dir_fd=parent_fd,
                    follow_symlinks=False)
    if generation(final) != generation(current):
        raise SystemExit("install launch-fence journal changed before removal")
    os.unlink(os.path.basename(path), dir_fd=parent_fd)
    os.fsync(parent_fd)
finally:
    os.close(parent_fd)
PY
  SIA_LAUNCH_FENCE_ARMED=0
}

restore_retained_runtime_fence_modes() {
  local retained="$1"
  [ -n "$retained" ] || return 0
  python3 - "$LAUNCH_FENCE_JOURNAL" "$BINDIR" "$retained" <<'PY'
import json
import os
import re
import stat
import sys

journal, installed, retained = map(os.path.abspath, sys.argv[1:])
uid = os.geteuid()
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_NOFOLLOW", 0))
descriptor = os.open(journal, flags)

def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)

try:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_uid != uid \
            or before.st_size > 1_048_576:
        raise SystemExit("unsafe install launch-fence journal")
    chunks = []
    remaining = 1_048_577
    while remaining:
        chunk = os.read(descriptor, min(remaining, 1_048_576))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    content = b"".join(chunks)
    after = os.fstat(descriptor)
    current_journal = os.stat(journal, follow_symlinks=False)
    if len(content) != before.st_size or len(content) > 1_048_576 \
            or not stat.S_ISREG(current_journal.st_mode) \
            or current_journal.st_uid != uid or b"\0" in content \
            or generation(before) != generation(after) \
            or generation(after) != generation(current_journal):
        raise SystemExit("install launch-fence journal changed")
    payload = json.loads(content)
finally:
    os.close(descriptor)
retained_info = os.lstat(retained)
if not stat.S_ISDIR(retained_info.st_mode) \
        or retained_info.st_uid != uid:
    raise SystemExit("unsafe retained runtime tree")
if not isinstance(payload, dict) \
        or payload.get("schema") != "sia-launch-fence-v1" \
        or not isinstance(payload.get("entries"), list):
    raise SystemExit("invalid install launch-fence journal")
for entry in payload["entries"]:
    if not isinstance(entry, dict) \
            or set(entry) != {"path", "device", "inode", "mode", "sha256"}:
        raise SystemExit("invalid install launch-fence entry")
    path = os.path.abspath(str(entry["path"]))
    if os.path.dirname(path) != installed:
        continue
    if any(isinstance(entry[key], bool)
           or not isinstance(entry[key], int) or entry[key] < 0
           for key in ("device", "inode", "mode")) \
            or entry["mode"] > 0o7777 \
            or re.fullmatch(r"[0-9a-f]{64}",
                            str(entry.get("sha256", ""))) is None:
        raise SystemExit("invalid install launch-fence entry")
    candidate = os.path.join(retained, os.path.basename(path))
    try:
        current = os.lstat(candidate)
    except FileNotFoundError:
        continue
    if not stat.S_ISREG(current.st_mode) or current.st_uid != uid \
            or (current.st_dev, current.st_ino) != (
                entry["device"], entry["inode"]):
        raise SystemExit("retained runtime launch inode changed")
    os.chmod(candidate, entry["mode"], follow_symlinks=False)
    after = os.lstat(candidate)
    if (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino) \
            or stat.S_IMODE(after.st_mode) != entry["mode"]:
        raise SystemExit("could not restore retained runtime launch mode")
    file_descriptor = os.open(candidate, flags)
    try:
        os.fsync(file_descriptor)
    finally:
        os.close(file_descriptor)
directory = os.open(retained,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(directory)
finally:
    os.close(directory)
PY
}

# Descriptor-rooted tree generations and journaled NOREPLACE publication.
# MAX_ENTRIES is status=exact parsed=2^17 exact=131072 (JACKAL rat lane;
# non-formal, outside the Lean certificate chain).  The cap bounds directory
# materialization while metadata generations bind in-place concurrent edits.
owned_tree_cas() {
  python3 - "$@" <<'PY'
import ctypes
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import sys

MAX_ENTRIES = 131_072
MAX_JOURNAL_BYTES = 65_536
arguments = sys.argv[1:]
if not arguments:
    raise SystemExit("missing tree CAS operation")
operation = arguments[0]
if operation in {"generation", "recover"} and len(arguments) == 2:
    target = os.path.abspath(arguments[1])
    staged = backup = expected = None
elif operation == "publish" and len(arguments) == 5:
    _, staged, target, backup, expected = arguments
    staged, target, backup = map(os.path.abspath,
                                 (staged, target, backup))
else:
    raise SystemExit("invalid tree CAS arguments")
parent = os.path.dirname(target)
if os.path.realpath(parent) != parent:
    raise SystemExit("tree CAS parent must not traverse symbolic links")
target_name = os.path.basename(target)
if staged is not None:
    if os.path.dirname(staged) != parent \
            or os.path.dirname(backup) != parent \
            or len({staged, target, backup}) != 3:
        raise SystemExit("tree CAS paths must be distinct siblings")
    staged_name = os.path.basename(staged)
    backup_name = os.path.basename(backup)
else:
    staged_name = backup_name = None
token_pattern = re.compile(
    r"tree:(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):([0-9a-f]{64})")
if expected is not None and expected != "absent" \
        and token_pattern.fullmatch(expected) is None:
    raise SystemExit("invalid expected tree generation")
directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                   | getattr(os, "O_DIRECTORY", 0)
                   | getattr(os, "O_NOFOLLOW", 0))
file_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
              | getattr(os, "O_NOFOLLOW", 0))
parent_fd = os.open(parent, directory_flags)
parent_info = os.fstat(parent_fd)
if not stat.S_ISDIR(parent_info.st_mode) \
        or parent_info.st_uid != os.geteuid():
    os.close(parent_fd)
    raise SystemExit("tree CAS parent is not an owned directory")


def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def update_record(digest, kind, relative, value):
    encoded = os.fsencode(relative)
    digest.update(kind)
    digest.update(len(encoded).to_bytes(4, "big"))
    digest.update(encoded)
    digest.update(b"\0")
    digest.update(":".join(str(item) for item in generation(value)).encode())
    digest.update(b"\n")


def tree_token(name, allow_absent=False, synchronize=False):
    try:
        root_fd = os.open(name, directory_flags, dir_fd=parent_fd)
    except FileNotFoundError:
        if allow_absent:
            try:
                os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return "absent"
        raise
    digest = hashlib.sha256()
    count = [0]

    def walk(descriptor, relative):
        before = os.fstat(descriptor)
        if not stat.S_ISDIR(before.st_mode) \
                or before.st_uid != os.geteuid():
            raise ValueError("tree contains an unsafe directory")
        names = []
        with os.scandir(descriptor) as entries:
            for entry in entries:
                names.append(entry.name)
                if len(names) > MAX_ENTRIES:
                    raise ValueError("tree directory exceeds entry ceiling")
        for child in sorted(names, key=os.fsencode):
            child_relative = child if not relative \
                else os.path.join(relative, child)
            observed = os.stat(child, dir_fd=descriptor,
                               follow_symlinks=False)
            count[0] += 1
            if count[0] > MAX_ENTRIES:
                raise ValueError("tree exceeds aggregate entry ceiling")
            if stat.S_ISDIR(observed.st_mode):
                child_fd = os.open(child, directory_flags,
                                   dir_fd=descriptor)
                try:
                    opened = os.fstat(child_fd)
                    if generation(opened) != generation(observed):
                        raise ValueError("tree directory changed before open")
                    update_record(digest, b"D", child_relative, opened)
                    walk(child_fd, child_relative)
                    after_child = os.fstat(child_fd)
                    current_child = os.stat(
                        child, dir_fd=descriptor, follow_symlinks=False)
                    if generation(after_child) != generation(current_child):
                        raise ValueError("tree directory path changed")
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(observed.st_mode):
                child_fd = os.open(child, file_flags, dir_fd=descriptor)
                try:
                    opened = os.fstat(child_fd)
                    if not stat.S_ISREG(opened.st_mode) \
                            or opened.st_uid != os.geteuid() \
                            or generation(opened) != generation(observed):
                        raise ValueError("tree file changed before open")
                    if synchronize:
                        os.fsync(child_fd)
                    after_child = os.fstat(child_fd)
                    current_child = os.stat(
                        child, dir_fd=descriptor, follow_symlinks=False)
                    if generation(opened) != generation(after_child) \
                            or generation(after_child) != generation(current_child):
                        raise ValueError("tree file changed while inspected")
                    update_record(digest, b"F", child_relative, opened)
                finally:
                    os.close(child_fd)
            else:
                raise ValueError("tree contains a symbolic or special entry")
        if synchronize:
            os.fsync(descriptor)
        after = os.fstat(descriptor)
        if generation(before) != generation(after):
            raise ValueError("tree directory changed while traversed")

    try:
        root_before = os.fstat(root_fd)
        if not stat.S_ISDIR(root_before.st_mode) \
                or root_before.st_uid != os.geteuid():
            raise ValueError("tree root is unsafe")
        walk(root_fd, "")
        root_after = os.fstat(root_fd)
        root_current = os.stat(name, dir_fd=parent_fd,
                               follow_symlinks=False)
        if generation(root_before) != generation(root_after) \
                or generation(root_after) != generation(root_current):
            raise ValueError("tree root changed while inspected")
    finally:
        os.close(root_fd)
    fields = (*generation(root_before), count[0], digest.hexdigest())
    return "tree:" + ":".join(str(item) for item in fields)


def moved_matches(actual, prior):
    actual_match = token_pattern.fullmatch(actual)
    prior_match = token_pattern.fullmatch(prior)
    if actual_match is None or prior_match is None:
        return False
    actual_fields = actual_match.groups()
    prior_fields = prior_match.groups()
    return actual_fields[:6] == prior_fields[:6] \
        and actual_fields[7:] == prior_fields[7:]


if operation == "generation":
    try:
        print(tree_token(target_name, allow_absent=True))
    finally:
        os.close(parent_fd)
    raise SystemExit(0)

libc = ctypes.CDLL(None, use_errno=True)
renameat2 = libc.renameat2
renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p,
                      ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
renameat2.restype = ctypes.c_int
RENAME_NOREPLACE = 1


def rename_noreplace(source, destination):
    result = renameat2(parent_fd, os.fsencode(source),
                       parent_fd, os.fsencode(destination),
                       RENAME_NOREPLACE)
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), (source, destination))


def child_exists(name):
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def unique_name(prefix):
    while True:
        candidate = prefix + secrets.token_hex(12)
        if not child_exists(candidate):
            return candidate


def sync_parent():
    os.fsync(parent_fd)


identity = hashlib.sha256(os.fsencode(target)).hexdigest()
lock_name = ".sia-tree-cas-lock-" + identity
journal_name = ".sia-tree-cas-journal-" + identity
lock_fd = os.open(
    lock_name, os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent_fd)
lock_info = os.fstat(lock_fd)
if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.geteuid():
    raise SystemExit("unsafe tree CAS lock")
os.fchmod(lock_fd, 0o600)
fcntl.flock(lock_fd, fcntl.LOCK_EX)


def read_journal():
    descriptor = os.open(journal_name, file_flags, dir_fd=parent_fd)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_size > MAX_JOURNAL_BYTES:
            raise ValueError("unsafe tree CAS journal")
        chunks = []
        total = 0
        while True:
            chunk = os.read(descriptor, MAX_JOURNAL_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_JOURNAL_BYTES:
                raise ValueError("oversized tree CAS journal")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        current = os.stat(journal_name, dir_fd=parent_fd,
                          follow_symlinks=False)
        if total != before.st_size \
                or generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise ValueError("tree CAS journal changed")
        record = json.loads(b"".join(chunks).decode("utf-8"))
    finally:
        os.close(descriptor)
    required = {"version", "target", "staged", "backup", "archive",
                "expected", "desired"}
    if not isinstance(record, dict) or set(record) != required \
            or record["version"] != 1 or record["target"] != target_name:
        raise ValueError("invalid tree CAS journal")
    for key in ("target", "staged", "backup", "archive"):
        value = record[key]
        if not isinstance(value, str) or not value \
                or os.path.basename(value) != value:
            raise ValueError("invalid tree CAS journal path")
    for key in ("expected", "desired"):
        value = record[key]
        if value != "absent" and token_pattern.fullmatch(value) is None:
            raise ValueError("invalid tree CAS journal token")
    return record


def write_journal(record):
    payload = (json.dumps(record, sort_keys=True,
                          separators=(",", ":")) + "\n").encode()
    temporary = unique_name(".sia-tree-cas-journal-stage.")
    try:
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            0o600, dir_fd=parent_fd)
        try:
            remaining = memoryview(payload)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("short tree CAS journal write")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        rename_noreplace(temporary, journal_name)
        sync_parent()
    except BaseException:
        try:
            os.unlink(temporary, dir_fd=parent_fd)
            sync_parent()
        except FileNotFoundError:
            pass
        raise


def clear_journal():
    try:
        os.unlink(journal_name, dir_fd=parent_fd)
        sync_parent()
    except FileNotFoundError:
        pass


def retained(record, reason):
    if child_exists(record["archive"]):
        print(f"{reason}; prior tree retained at "
              f"{os.path.join(parent, record['archive'])}", file=sys.stderr)


def recover_journal():
    if not child_exists(journal_name):
        return
    record = read_journal()
    current = tree_token(target_name, allow_absent=True)
    archived = tree_token(record["archive"], allow_absent=True)
    staged_current = tree_token(record["staged"], allow_absent=True)
    prior = record["expected"]
    desired = record["desired"]
    if prior == "absent":
        if moved_matches(current, desired) \
                or (current == "absent"
                    and moved_matches(staged_current, desired)):
            clear_journal()
            return
        print("tree CAS recovery preserved an independent target",
              file=sys.stderr)
        clear_journal()
        return
    if moved_matches(current, desired):
        if moved_matches(archived, prior):
            if not child_exists(record["backup"]):
                try:
                    rename_noreplace(record["archive"], record["backup"])
                    sync_parent()
                except OSError:
                    retained(record, "tree CAS recovery could not return backup")
            else:
                retained(record, "tree CAS recovery found occupied backup")
        clear_journal()
        return
    if current == "absent" and moved_matches(archived, prior):
        try:
            rename_noreplace(record["archive"], target_name)
            sync_parent()
        except OSError:
            retained(record, "tree CAS recovery preserved a newer target")
        clear_journal()
        return
    if current == prior and archived == "absent":
        clear_journal()
        return
    retained(record, "tree CAS recovery preserved a concurrent target")
    clear_journal()


try:
    recover_journal()
    if operation == "recover":
        raise SystemExit(0)
    if child_exists(backup_name):
        raise SystemExit("tree CAS backup path is occupied")
    desired = tree_token(staged_name, synchronize=True)
    current = tree_token(target_name, allow_absent=True)
    if current != expected:
        raise SystemExit("tree CAS target changed before publication")
    archive = unique_name(".sia-tree-cas-prior.")
    record = {"version": 1, "target": target_name,
              "staged": staged_name, "backup": backup_name,
              "archive": archive, "expected": expected,
              "desired": desired}
    write_journal(record)
    if expected != "absent":
        rename_noreplace(target_name, archive)
        sync_parent()
        if not moved_matches(tree_token(archive), expected):
            try:
                rename_noreplace(archive, target_name)
                sync_parent()
            except OSError:
                retained(record, "tree CAS refused to overwrite a newer target")
            clear_journal()
            raise SystemExit("archived tree did not match preflight")
    try:
        rename_noreplace(staged_name, target_name)
        sync_parent()
    except OSError:
        retained(record, "tree CAS publication preserved a concurrent target")
        clear_journal()
        raise SystemExit("tree CAS target changed during publication")
    installed = tree_token(target_name)
    if not moved_matches(installed, desired):
        retained(record, "tree CAS target changed after publication")
        clear_journal()
        raise SystemExit("published tree is no longer current")
    if expected != "absent":
        try:
            rename_noreplace(archive, backup_name)
            sync_parent()
        except OSError:
            retained(record, "tree CAS could not return the prior tree")
            clear_journal()
            raise SystemExit("tree CAS backup changed during publication")
        if not moved_matches(tree_token(backup_name), expected) \
                or not moved_matches(tree_token(target_name), installed):
            print(f"prior tree retained at {backup}", file=sys.stderr)
            clear_journal()
            raise SystemExit("tree CAS changed at publication boundary")
    clear_journal()
    print(installed + "\t" + (backup if expected != "absent" else ""))
finally:
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    os.close(lock_fd)
    os.close(parent_fd)
PY
}

owned_tree_generation() {
  owned_tree_cas generation "$1"
}

atomic_install_tree() {
  local staged="$1" target="$2" backup_template="$3" expected="$4"
  local backup result installed
  backup="$(mktemp -d "$backup_template")" || return 1
  rmdir -- "$backup" || return 1
  result="$(owned_tree_cas publish "$staged" "$target" "$backup" \
    "$expected")" || return 1
  IFS=$'\t' read -r installed backup <<< "$result"
  printf '%s\t%s\n' "$installed" "$backup"
}

# Assemble a bounded, stable replacement beside its destination, then publish
# it through the same journaled, generation-bound NOREPLACE protocol used for
# user-editable integrations.  Callers that preflight public targets pass the
# exact expected generation; the fallback is only for fresh private stages.
atomic_install_file() {
  local source="$1" target="$2" mode="$3" expected="${4:-}"
  local parent temporary installed
  parent="$(dirname "$target")"
  mkdir -p "$parent"
  if [ -z "$expected" ]; then
    if [ -e "$target" ] || [ -L "$target" ]; then
      expected="$(owned_metadata generation "$target")" || return 1
    else
      expected=absent
    fi
  fi
  temporary="$(mktemp "$parent/.${target##*/}.stage.XXXXXX")" || return 1
  if ! python3 - "$source" "$temporary" "$mode" <<'PY'
import hashlib
import os
import stat
import sys

MAX_BYTES = 1_048_576
source, temporary, mode = sys.argv[1:]
mode = int(mode, 8)
source_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0))
source_fd = os.open(source, source_flags)
temporary_fd = os.open(
    temporary, os.O_WRONLY | os.O_TRUNC | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0))


def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


try:
    before = os.fstat(source_fd)
    if not stat.S_ISREG(before.st_mode) \
            or before.st_uid != os.geteuid() or before.st_size > MAX_BYTES:
        raise RuntimeError("atomic install source is unsafe or oversized")
    total = 0
    digest = hashlib.sha256()
    while chunk := os.read(source_fd, MAX_BYTES):
        total += len(chunk)
        if total > MAX_BYTES:
            raise RuntimeError("atomic install source is oversized")
        digest.update(chunk)
        remaining = memoryview(chunk)
        while remaining:
            remaining = remaining[os.write(temporary_fd, remaining):]
    after = os.fstat(source_fd)
    current = os.stat(source, follow_symlinks=False)
    if total != before.st_size or generation(before) != generation(after) \
            or generation(after) != generation(current):
        raise RuntimeError("atomic install source changed during staging")
    os.fchmod(temporary_fd, mode)
    os.fsync(temporary_fd)
finally:
    os.close(temporary_fd)
    os.close(source_fd)
PY
  then
    rm -f -- "$temporary"
    return 1
  fi
  if ! installed="$(owned_file_cas publish "$temporary" "$target" \
      "$expected")"; then
    [ ! -e "$temporary" ] \
      || echo "staged/prior file retained at $temporary" >&2
    return 1
  fi
  # A successful present-target CAS returns exactly the preflight-authorized
  # prior generation at our private random stage; no concurrent generation is
  # ever placed there on a failure path.
  rm -f -- "$temporary"
  printf '%s\n' "$installed"
}

ollama_client_version() {
  OLLAMA_HOST=http://127.0.0.1:9 \
    bounded_command_capture "$1" --version 2>/dev/null \
    | sed -n 's/^Warning: client version is //p' | head -n 1
}

effective_ollama_models_dir() {
  local daemon_pid
  daemon_pid="$(bounded_command_capture systemctl --user show ollama.service \
    --property=MainPID --value 2>/dev/null)"
  [[ "$daemon_pid" =~ ^[1-9][0-9]*$ ]] || {
    echo "cannot discover the running ollama.service process" >&2
    return 1
  }
  python3 - "$daemon_pid" <<'PY'
import os
import pwd
import sys

pid = sys.argv[1]
with open(f"/proc/{pid}/environ", "rb") as stream:
    environment = dict(
        item.split(b"=", 1) for item in stream.read().split(b"\0")
        if b"=" in item
    )
raw = os.fsdecode(environment.get(b"OLLAMA_MODELS", b""))
if raw:
    if not os.path.isabs(raw):
        raw = os.path.join(os.readlink(f"/proc/{pid}/cwd"), raw)
    models = os.path.abspath(raw)
else:
    service_home = os.fsdecode(environment.get(b"HOME", b""))
    if not service_home:
        service_home = pwd.getpwuid(os.stat(f"/proc/{pid}").st_uid).pw_dir
    if not service_home or not os.path.isabs(service_home):
        raise SystemExit("cannot derive ollama.service HOME")
    models = os.path.join(service_home, ".ollama", "models")
print(models)
PY
}

verify_ollama_model_store() {
  local models_dir="$1" manifest_path="$2" expected_manifest="$3"
  python3 - "$models_dir" "$manifest_path" "$expected_manifest" <<'PY'
import hashlib
import json
import os
import re
import stat
import sys

models_dir, manifest_path, expected_manifest = sys.argv[1:]
digest_pattern = re.compile(r"^sha256:([0-9a-f]{64})$")
# JACKAL status=exact: parsed=1024*1024, exact=1048576. Exact rational
# arithmetic outside the Lean certificate chain (NOT formal-bounded).
MAX_MODEL_MANIFEST_BYTES = 1_048_576

def open_regular(path):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        os.close(descriptor)
        raise ValueError(f"not a regular file: {path}")
    return os.fdopen(descriptor, "rb"), metadata.st_size

def read_stable_bounded_regular(path, maximum, label):
    stream, size = open_regular(path)
    with stream:
        before = os.fstat(stream.fileno())
        if size > maximum:
            raise SystemExit(f"{label} exceeds its byte ceiling")
        content = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as error:
        raise SystemExit(f"{label} changed while reading") from error
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if len(content) != size or observed != finished \
            or (current.st_dev, current.st_ino) != (after.st_dev,
                                                    after.st_ino):
        raise SystemExit(f"{label} changed while reading")
    return content

manifest_bytes = read_stable_bounded_regular(
    manifest_path, MAX_MODEL_MANIFEST_BYTES, "nomic-embed-text manifest")
manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
if manifest_digest != expected_manifest:
    raise SystemExit(
        f"nomic-embed-text manifest mismatch: expected {expected_manifest}, "
        f"got {manifest_digest}"
    )
try:
    manifest = json.loads(manifest_bytes)
except (UnicodeDecodeError, json.JSONDecodeError) as error:
    raise SystemExit(f"invalid nomic-embed-text manifest: {error}") from error

entries = [manifest.get("config")] + list(manifest.get("layers", []))
if not entries or any(not isinstance(entry, dict) for entry in entries):
    raise SystemExit("nomic-embed-text manifest has invalid blob entries")
for entry in entries:
    match = digest_pattern.fullmatch(str(entry.get("digest", "")))
    if not match:
        raise SystemExit("nomic-embed-text manifest contains an invalid digest")
    blob_path = os.path.join(models_dir, "blobs", "sha256-" + match.group(1))
    stream, blob_size = open_regular(blob_path)
    with stream:
        blob_digest = hashlib.sha256()
        while chunk := stream.read(1024 * 1024):
            blob_digest.update(chunk)
    if blob_size != entry.get("size"):
        raise SystemExit(f"blob size mismatch: {entry['digest']}")
    if blob_digest.hexdigest() != match.group(1):
        raise SystemExit(f"blob digest mismatch: {entry['digest']}")
PY
}

model_manifest_generation() {
  python3 - "$1" <<'PY'
import hashlib
import os
import stat
import sys

MAX_BYTES = 1_048_576
CHUNK_BYTES = 1_048_576
path = sys.argv[1]
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_NOFOLLOW", 0))


def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


try:
    descriptor = os.open(path, flags)
except FileNotFoundError:
    if os.path.lexists(path):
        raise SystemExit("unsafe model manifest path")
    print("absent")
    raise SystemExit(0)
try:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() \
            or before.st_size > MAX_BYTES:
        raise SystemExit("unsafe or oversized model manifest")
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = os.read(descriptor, CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_BYTES:
            raise SystemExit("oversized model manifest")
        digest.update(chunk)
    after = os.fstat(descriptor)
    current = os.stat(path, follow_symlinks=False)
    if total != before.st_size or generation(before) != generation(after) \
            or generation(after) != generation(current):
        raise SystemExit("model manifest changed during generation capture")
finally:
    os.close(descriptor)
fields = (*generation(before), digest.hexdigest())
print("present:" + ":".join(str(value) for value in fields))
PY
}

snapshot_model_manifest() {
  python3 - "$1" "$2" <<'PY'
import os
import stat
import sys

MAX_BYTES = 1_048_576
CHUNK_BYTES = 1_048_576
source, target = sys.argv[1:]
read_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
              | getattr(os, "O_NOFOLLOW", 0))
write_flags = (os.O_WRONLY | os.O_TRUNC | getattr(os, "O_CLOEXEC", 0)
               | getattr(os, "O_NOFOLLOW", 0))


def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


source_fd = os.open(source, read_flags)
target_fd = os.open(target, write_flags)
try:
    before = os.fstat(source_fd)
    target_info = os.fstat(target_fd)
    if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() \
            or before.st_size > MAX_BYTES \
            or not stat.S_ISREG(target_info.st_mode) \
            or target_info.st_uid != os.geteuid():
        raise SystemExit("unsafe model manifest backup path")
    total = 0
    while True:
        chunk = os.read(source_fd, CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_BYTES:
            raise SystemExit("oversized model manifest backup")
        remaining = memoryview(chunk)
        while remaining:
            written = os.write(target_fd, remaining)
            if written <= 0:
                raise SystemExit("short model manifest backup write")
            remaining = remaining[written:]
    after = os.fstat(source_fd)
    current = os.stat(source, follow_symlinks=False)
    if total != before.st_size or generation(before) != generation(after) \
            or generation(after) != generation(current):
        raise SystemExit("model manifest changed during backup")
    os.fchmod(target_fd, 0o600)
    os.fsync(target_fd)
finally:
    os.close(target_fd)
    os.close(source_fd)
PY
}

# Capture every installer input into one bounded, generation-stable release
# snapshot before any managed path is changed.  Later source reads are rebound
# to this private snapshot, so a concurrently updated checkout can neither
# produce a mixed runtime nor alter the bytes selected earlier in the run.
release_source_frontdoor() {
  python3 - "$@" <<'PY'
import os
import stat
import sys

# JACKAL status=exact, parsed=16*1024^2, exact=16777216.
# Non-claim: this arithmetic is exact but outside the Lean certificate chain.
MAX_SOURCE_FILE_BYTES = 16_777_216
# JACKAL status=exact, parsed=64*1024^2, exact=67108864.
# Non-claim: this arithmetic is exact but outside the Lean certificate chain.
MAX_SOURCE_TOTAL_BYTES = 67_108_864
READ_CHUNK_BYTES = 1_048_576
DIRECTORY_FLAGS = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                   | getattr(os, "O_DIRECTORY", 0)
                   | getattr(os, "O_NOFOLLOW", 0))
FILE_FLAGS = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
              | getattr(os, "O_NOFOLLOW", 0))


def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def normalize_relative(value):
    if not value or os.path.isabs(value) or "\\" in value:
        raise ValueError("unsafe release-source allowlist entry")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts) \
            or os.path.normpath(value) != value:
        raise ValueError("unsafe release-source allowlist entry")
    return value


def required_directories(relatives):
    directories = {""}
    for relative in relatives:
        parent = os.path.dirname(relative)
        while parent:
            directories.add(parent)
            parent = os.path.dirname(parent)
    return sorted(directories, key=lambda item: (item.count("/"), item))


def open_absolute_directory(path):
    absolute = os.path.abspath(path)
    descriptor = os.open(os.sep, DIRECTORY_FLAGS)
    try:
        for component in [part for part in absolute.split(os.sep) if part]:
            child = os.open(component, DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


class BoundTree:
    def __init__(self, root, relatives, directories):
        self.root = os.path.abspath(root)
        self.relatives = relatives
        self.directories = directories
        self.directory_fds = {}
        self.states = {}
        root_fd = open_absolute_directory(self.root)
        self.directory_fds[""] = root_fd
        root_info = os.fstat(root_fd)
        if not stat.S_ISDIR(root_info.st_mode) \
                or root_info.st_uid != os.geteuid():
            raise ValueError("unsafe release-source root")
        self.states[("directory", "")] = generation(root_info)
        for relative in directories:
            if not relative:
                continue
            parent = os.path.dirname(relative)
            name = os.path.basename(relative)
            parent_fd = self.directory_fds[parent]
            descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=parent_fd)
            value = os.fstat(descriptor)
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISDIR(value.st_mode) \
                    or value.st_uid != os.geteuid() \
                    or generation(value) != generation(current):
                os.close(descriptor)
                raise ValueError(
                    f"unsafe release-source directory: {relative}")
            self.directory_fds[relative] = descriptor
            self.states[("directory", relative)] = generation(value)
        total = 0
        for relative in relatives:
            parent = os.path.dirname(relative)
            name = os.path.basename(relative)
            value = os.stat(name, dir_fd=self.directory_fds[parent],
                            follow_symlinks=False)
            if not stat.S_ISREG(value.st_mode) \
                    or value.st_uid != os.geteuid():
                raise ValueError(f"unsafe release-source file: {relative}")
            if value.st_size > MAX_SOURCE_FILE_BYTES:
                raise ValueError(
                    f"release-source file exceeds ceiling: {relative}")
            total += value.st_size
            if total > MAX_SOURCE_TOTAL_BYTES:
                raise ValueError("release-source snapshot exceeds total ceiling")
            self.states[("file", relative)] = generation(value)

    def read_stable(self, relative):
        parent = os.path.dirname(relative)
        name = os.path.basename(relative)
        parent_fd = self.directory_fds[parent]
        descriptor = os.open(name, FILE_FLAGS, dir_fd=parent_fd)
        try:
            before = os.fstat(descriptor)
            expected = self.states[("file", relative)]
            if generation(before) != expected \
                    or not stat.S_ISREG(before.st_mode) \
                    or before.st_uid != os.geteuid() \
                    or before.st_size > MAX_SOURCE_FILE_BYTES:
                raise ValueError("release source changed before it was read")
            chunks = []
            remaining = MAX_SOURCE_FILE_BYTES + 1
            while remaining:
                chunk = os.read(
                    descriptor, min(remaining, READ_CHUNK_BYTES))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            content = b"".join(chunks)
            after = os.fstat(descriptor)
            current = os.stat(name, dir_fd=parent_fd,
                              follow_symlinks=False)
            if len(content) != before.st_size \
                    or len(content) > MAX_SOURCE_FILE_BYTES \
                    or generation(before) != generation(after) \
                    or generation(after) != generation(current):
                raise ValueError("release source changed while it was read")
            return content, stat.S_IMODE(before.st_mode)
        finally:
            os.close(descriptor)

    def require_unchanged(self):
        current_root = open_absolute_directory(self.root)
        try:
            if generation(os.fstat(current_root)) \
                    != self.states[("directory", "")]:
                raise ValueError("release-source root changed")
        finally:
            os.close(current_root)
        for relative in self.directories:
            descriptor = self.directory_fds[relative]
            if generation(os.fstat(descriptor)) \
                    != self.states[("directory", relative)]:
                raise ValueError("release-source directory changed")
            if relative:
                parent = os.path.dirname(relative)
                current = os.stat(
                    os.path.basename(relative),
                    dir_fd=self.directory_fds[parent], follow_symlinks=False)
                if generation(current) \
                        != self.states[("directory", relative)]:
                    raise ValueError("release-source directory was replaced")
        for relative in self.relatives:
            parent = os.path.dirname(relative)
            current = os.stat(
                os.path.basename(relative),
                dir_fd=self.directory_fds[parent], follow_symlinks=False)
            if generation(current) != self.states[("file", relative)]:
                raise ValueError("release-source file was replaced")

    def close(self):
        for descriptor in reversed(list(self.directory_fds.values())):
            os.close(descriptor)
        self.directory_fds.clear()


def write_all(descriptor, content):
    remaining = memoryview(content)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("short release-snapshot write")
        remaining = remaining[written:]


mode, source_root, snapshot_root, *raw_relatives = sys.argv[1:]
relatives = [normalize_relative(value) for value in raw_relatives]
if not relatives or len(relatives) != len(set(relatives)):
    raise SystemExit("release-source allowlist is empty or duplicated")
directories = required_directories(relatives)
source_tree = None
snapshot_tree = None
try:
    source_tree = BoundTree(source_root, relatives, directories)
    if mode == "snapshot":
        snapshot_parent = os.path.dirname(os.path.abspath(snapshot_root))
        snapshot_name = os.path.basename(os.path.abspath(snapshot_root))
        parent_fd = open_absolute_directory(snapshot_parent)
        os.mkdir(snapshot_name, 0o700, dir_fd=parent_fd)
        snapshot_root_fd = os.open(
            snapshot_name, DIRECTORY_FLAGS, dir_fd=parent_fd)
        os.close(parent_fd)
        destination_fds = {"": snapshot_root_fd}
        for relative in directories:
            if relative:
                parent = os.path.dirname(relative)
                name = os.path.basename(relative)
                os.mkdir(name, 0o700, dir_fd=destination_fds[parent])
                destination_fds[relative] = os.open(
                    name, DIRECTORY_FLAGS, dir_fd=destination_fds[parent])
        for relative in relatives:
            content, source_mode = source_tree.read_stable(relative)
            target_mode = source_mode & ~0o222
            flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_CLOEXEC", 0)
                     | getattr(os, "O_NOFOLLOW", 0))
            parent = os.path.dirname(relative)
            descriptor = os.open(
                os.path.basename(relative), flags, target_mode,
                dir_fd=destination_fds[parent])
            try:
                write_all(descriptor, content)
                os.fchmod(descriptor, target_mode)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        source_tree.require_unchanged()
        for relative in reversed(directories):
            descriptor = destination_fds[relative]
            os.fsync(descriptor)
            os.fchmod(descriptor, 0o500)
            os.close(descriptor)
        destination_fds.clear()
    elif mode == "verify":
        snapshot_tree = BoundTree(snapshot_root, relatives, directories)
        for relative in relatives:
            source_content, source_mode = source_tree.read_stable(relative)
            snapshot_content, snapshot_mode = snapshot_tree.read_stable(
                relative)
            if source_content != snapshot_content \
                    or (source_mode & ~0o222) != snapshot_mode:
                raise ValueError(f"release source diverged: {relative}")
        source_tree.require_unchanged()
        snapshot_tree.require_unchanged()
    else:
        raise ValueError("unknown release-source operation")
except (OSError, UnicodeError, ValueError) as error:
    raise SystemExit(str(error)) from error
finally:
    if snapshot_tree is not None:
        snapshot_tree.close()
    if source_tree is not None:
        source_tree.close()
PY
}

SIA_RELEASE_FILES=(
  manifest.json preview.png Panel.qml Cockpit.qml Model.js README.md LICENSE
  SECURITY.md CHANGELOG.md GBRAIN_PIN config.example.json install.sh
  uninstall.sh assets/cockpit.png bin/sia bin/sia-brainstem bin/sia-ledger
  bin/sia-mcp bin/siabench.py bin/sialib.py bin/siamind.py bin/siaqueue.py
  bin/siatakes.py docs/MANUAL.md docs/WHITEPAPER.md schema-pack/pack.yaml
  skill/SKILL.md systemd/sia-brainstem.service systemd/sia-ollama.service
)
SIA_RELEASE_SOURCE="$SIA_INSTALL_TMP/release-source"
release_source_frontdoor snapshot "$SIA_ORIGINAL_REPO" \
  "$SIA_RELEASE_SOURCE" "${SIA_RELEASE_FILES[@]}"
REPO="$SIA_RELEASE_SOURCE"

SIA_STABLE_LAUNCHER="$SIA_INSTALL_TMP/sia-launcher"
write_stable_generation_launcher "$SIA_STABLE_LAUNCHER"
prepare_and_lock_install
preflight_managed_filesystem_capabilities "$SHARE" \
  "$SHARE" "$STATE" "$HOME/.local/bin" "$CONFIG_DIR" \
  "$SYSTEMD_USER_DIR" "$TOOLCHAIN"
recover_publication_receipts_from_fence
preflight_runtime
preflight_corpus read-only
preflight_owned_file "$SIA_STABLE_LAUNCHER" "$CLI_PATH" "$CLI_RECEIPT" \
  sia-cli SIA_REPLACE_SIA_CLI SIA_CLI_EXPECTED

# Never stop a foreign or locally modified unit merely because it happens to
# use SIA's service name. An exact current unit is safely adoptable; an older
# receipt-bound unit is an owned upgrade. Everything else needs explicit
# replacement consent before install-wide quiescence begins.
BRAINSTEM_BARRIER_STATE="$(brainstem_runtime_barrier_file state)" || exit 1
BRAINSTEM_EXPECTED_DROP_IN=""
case "$BRAINSTEM_BARRIER_STATE" in
  active)
    SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED=1
    SIA_KEEP_BRAINSTEM_RUNTIME_BARRIER=1
    if [ -e "$BRAINSTEM_UNIT" ] || [ -L "$BRAINSTEM_UNIT" ]; then
      BRAINSTEM_EXPECTED_DROP_IN="$BRAINSTEM_RUNTIME_BARRIER"
    fi
    run_with_deadline 120 systemctl --user daemon-reload
    ;;
  retired)
    SIA_KEEP_BRAINSTEM_RUNTIME_BARRIER=1
    # Normalize a crash between atomic retirement and daemon-reload. The
    # exact retired copy remains available for restoration after ownership is
    # proven below.
    run_with_deadline 120 systemctl --user daemon-reload
    ;;
  absent) ;;
  *) echo "unexpected sia-brainstem barrier state" >&2; exit 1 ;;
esac
inspect_user_unit sia-brainstem.service BRAINSTEM_INSPECT \
  "$BRAINSTEM_EXPECTED_DROP_IN" || exit 1
if [ "$BRAINSTEM_INSPECT_LOAD_STATE" = masked ] \
    || [ "$BRAINSTEM_INSPECT_UNIT_FILE_STATE" = masked-runtime ]; then
  echo "pre-existing sia-brainstem.service runtime mask preserved" >&2
  exit 1
fi
if [ "$BRAINSTEM_INSPECT_LOAD_STATE" = loaded ] \
    && [ "$BRAINSTEM_INSPECT_FRAGMENT_PATH" != "$BRAINSTEM_UNIT" ]; then
  echo "sia-brainstem.service is loaded from an unowned path: $BRAINSTEM_INSPECT_FRAGMENT_PATH" >&2
  exit 1
fi
if [ -e "$BRAINSTEM_UNIT" ] || [ -L "$BRAINSTEM_UNIT" ]; then
  if [ ! -f "$BRAINSTEM_UNIT" ] || [ -L "$BRAINSTEM_UNIT" ]; then
    echo "refusing unsafe sia-brainstem unit path" >&2
    exit 1
  fi
  if ! owned_metadata same-content \
        "$REPO/systemd/sia-brainstem.service" "$BRAINSTEM_UNIT" \
      && ! managed_receipt_matches "$BRAINSTEM_RECEIPT" \
        brainstem-unit "$BRAINSTEM_UNIT" \
      && [ "${SIA_REPLACE_BRAINSTEM_UNIT:-0}" != "1" ]; then
    echo "existing sia-brainstem unit is unowned or locally modified; preserved" >&2
    echo "inspect it, then use SIA_REPLACE_BRAINSTEM_UNIT=1 to replace it" >&2
    exit 1
  fi
elif [ "$BRAINSTEM_INSPECT_LOAD_STATE" != not-found ] \
    || [ "$BRAINSTEM_INSPECT_ACTIVE_STATE" != inactive ] \
    || [ -n "$BRAINSTEM_INSPECT_UNIT_FILE_STATE" ]; then
  echo "sia-brainstem.service resolves outside SIA's managed unit path; preserved" >&2
  exit 1
fi

SIA_BRAINSTEM_ENABLE_STATE="$BRAINSTEM_INSPECT_UNIT_FILE_STATE"
if [ "$BRAINSTEM_INSPECT_ACTIVE_STATE" = active ]; then
  SIA_BRAINSTEM_WAS_ACTIVE=1
fi
if [ -e "$BRAINSTEM_UNIT" ] || [ -L "$BRAINSTEM_UNIT" ] \
    || [ "$BRAINSTEM_INSPECT_LOAD_STATE" = loaded ]; then
  install_brainstem_runtime_barrier
else
  if [ "$BRAINSTEM_BARRIER_STATE" = retired ]; then
    # Recover a power loss after an uninstall retired the barrier but before
    # its exact recovery copy was discarded. It remains an ignored orphan
    # until the new main unit is published below.
    install_brainstem_runtime_barrier
  fi
  # A genuinely fresh install has no launcher to queue yet. Provision the
  # barrier immediately before the unit first becomes visible, then attest it
  # after the main unit and drop-in enter the manager in one reload.
  SIA_BRAINSTEM_BARRIER_DEFERRED=1
fi
acquire_install_lifecycle
acquire_owner_lock "$STATE/brainstem-owner.lock" SIA_BRAINSTEM_LOCK_FD \
  "brainstem"
acquire_owner_lock "$STATE/corpus-owner.lock" SIA_CORPUS_LOCK_FD \
  "corpus transaction"
acquire_owner_lock "$STATE/gbrain-owner.lock" SIA_GBRAIN_LOCK_FD \
  "PGLite"
SIA_CORPUS_RECEIPT_LOCKS_HELD=1
migrate_legacy_corpus_receipt \
  "$SIA_CORPUS_EARLY_RECEIPT_STATE" \
  "$SIA_CORPUS_EARLY_RECEIPT_ROOT" \
  "$SIA_CORPUS_EARLY_RECEIPT_GENERATION" \
  "$SIA_CORPUS_EARLY_RECEIPT_JOURNAL_STATE"
preflight_corpus locked
drain_legacy_launchers
preflight_owned_file "$SIA_STABLE_LAUNCHER" "$CLI_PATH" "$CLI_RECEIPT" \
  sia-cli SIA_REPLACE_SIA_CLI SIA_CLI_EXPECTED
retain_unowned_cli_before_fence
SIA_INSTALL_MUTATED=1
# A durable marker makes every failure or power loss fail closed, including an
# ordinary upgrade from a launcher that predates lifecycle leases. The marker
# remains through first light and is cleared only after every public artifact
# and integration is complete.
write_lifecycle_tombstone
SIA_RESTORE_LIFECYCLE_TOMBSTONE=1
# Journal the exact old launch inodes before making them unreadable. New
# CLI/direct-brainstem/MCP admissions now fail at open(2); the second drain
# proves that every process admitted before the fence is gone.
arm_install_launch_fence
drain_legacy_launchers
# Block every newly launched reader before the first managed engine, model,
# runtime, schema, or ledger byte can change. This standalone writer works on
# both fresh installs and upgrades from runtimes that predate readiness.
mark_install_sync_debt

step "1/9 private bun + pinned gbrain (the memory engine, by Garry Tan)"
BUN_VERSION=1.4.0
BUN_TAG="bun-v$BUN_VERSION"
BUN_ROOT="$TOOLCHAIN/bun"
BUN_BIN="$BUN_ROOT/bin/bun"
BUN_RECEIPT="$BUN_ROOT/.sia-release"
owned_tree_cas recover "$BUN_ROOT" || exit 1
bun_runtime_receipt_valid() {
  local receipt_prefix reported_version
  [ -x "$BUN_BIN" ] && [ ! -L "$BUN_BIN" ] \
    && [ -f "$BUN_RECEIPT" ] && [ ! -L "$BUN_RECEIPT" ] || return 1
  receipt_prefix="$(printf 'managed-by=khephri.sia\nversion=%s\nasset=%s\nsha256=%s' \
    "$BUN_VERSION" "$BUN_ASSET" "$BUN_SHA256")"
  # Do not execute an installed binary until exact, bounded metadata has bound
  # this stable current inode and digest to the requested release.
  owned_metadata release "$BUN_RECEIPT" "$BUN_BIN" "$receipt_prefix" \
    || return 1
  reported_version="$(bounded_command_capture \
    "$BUN_BIN" --version 2>/dev/null)" || return 1
  [ "$reported_version" = "$BUN_VERSION" ]
}
if ! bun_runtime_receipt_valid; then
  if [ -e "$BUN_ROOT" ] || [ -L "$BUN_ROOT" ]; then
    if [ ! -d "$BUN_ROOT" ] || [ -L "$BUN_ROOT" ]; then
      echo "refusing unsafe private Bun root" >&2
      exit 1
    fi
    if [ -L "$BUN_RECEIPT" ] \
        || { [ -e "$BUN_RECEIPT" ] && [ ! -f "$BUN_RECEIPT" ]; }; then
      echo "refusing unsafe private Bun receipt" >&2
      exit 1
    fi
    if [ "${SIA_REPLACE_TOOLCHAIN:-0}" != "1" ]; then
      echo "existing private Bun tree lacks an exact current release receipt; preserved" >&2
      echo "explicit replacement requires SIA_REPLACE_TOOLCHAIN=1 ./install.sh" >&2
      exit 1
    fi
    BUN_TREE_EXPECTED="$(owned_tree_generation "$BUN_ROOT")" || exit 1
  else
    BUN_TREE_EXPECTED=absent
  fi
  download_verified \
    "https://github.com/oven-sh/bun/releases/download/$BUN_TAG/$BUN_ASSET" \
    "$SIA_INSTALL_TMP/$BUN_ASSET" "$BUN_SHA256"
  run_with_deadline 300 unzip -q "$SIA_INSTALL_TMP/$BUN_ASSET" \
    -d "$SIA_INSTALL_TMP/bun-archive"
  SIA_BUN_STAGE="$(mktemp -d "$TOOLCHAIN/.bun.stage.XXXXXX")"
  mkdir -p "$SIA_BUN_STAGE/bin"
  install -m 0755 \
    "$SIA_INSTALL_TMP/bun-archive/${BUN_ASSET%.zip}/bun" \
    "$SIA_BUN_STAGE/bin/bun"
  BUN_BINARY_SHA256="$(owned_metadata digest "$SIA_BUN_STAGE/bin/bun")" \
    || exit 1
  printf 'managed-by=khephri.sia\nversion=%s\nasset=%s\nsha256=%s\nbinary_sha256=%s\n' \
    "$BUN_VERSION" "$BUN_ASSET" "$BUN_SHA256" "$BUN_BINARY_SHA256" \
    > "$SIA_BUN_STAGE/.sia-release"
  SIA_INSTALL_MUTATED=1
  BUN_RESULT="$(atomic_install_tree "$SIA_BUN_STAGE" "$BUN_ROOT" \
    "$TOOLCHAIN/.bun.previous.XXXXXX" "$BUN_TREE_EXPECTED")"
  IFS=$'\t' read -r _BUN_INSTALLED_TREE BUN_BACKUP <<< "$BUN_RESULT"
  SIA_BUN_STAGE=""
  [ -z "$BUN_BACKUP" ] || echo "  previous private Bun retained at $BUN_BACKUP"
fi
bun_runtime_receipt_valid || {
  echo "private Bun receipt or executable verification failed" >&2; exit 1; }

PIN="$(grep '^commit=' "$REPO/GBRAIN_PIN" 2>/dev/null | cut -d= -f2)"
PIN_VERSION="$(grep '^version=' "$REPO/GBRAIN_PIN" 2>/dev/null | cut -d= -f2)"
PIN_LOCK_SHA256="$(grep '^bun_lock_sha256=' "$REPO/GBRAIN_PIN" 2>/dev/null \
  | cut -d= -f2)"
[[ "$PIN" =~ ^[0-9a-f]{40}$ ]] || {
  echo "GBRAIN_PIN must contain one full lowercase commit digest"; exit 1; }
[[ "$PIN_VERSION" =~ ^[0-9]+([.][0-9]+)+$ ]] || {
  echo "GBRAIN_PIN must contain a numeric dotted version"; exit 1; }
[[ "$PIN_LOCK_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
  echo "GBRAIN_PIN must bind the upstream bun.lock SHA-256"; exit 1; }

GBRAIN_ROOT="$TOOLCHAIN/gbrain"
GBRAIN_BIN="$GBRAIN_ROOT/bin/gbrain"
GBRAIN_RECEIPT="$GBRAIN_ROOT/.sia-release"
owned_tree_cas recover "$GBRAIN_ROOT" || exit 1
gbrain_runtime_receipt_valid() {
  local receipt_prefix reported_version
  [ -x "$GBRAIN_BIN" ] && [ ! -L "$GBRAIN_BIN" ] \
    && [ -f "$GBRAIN_RECEIPT" ] && [ ! -L "$GBRAIN_RECEIPT" ] || return 1
  receipt_prefix="$(printf 'managed-by=khephri.sia\ncommit=%s\nversion=%s\nbun_lock_sha256=%s' \
    "$PIN" "$PIN_VERSION" "$PIN_LOCK_SHA256")"
  owned_metadata release "$GBRAIN_RECEIPT" "$GBRAIN_BIN" \
    "$receipt_prefix" || return 1
  reported_version="$(bounded_command_capture \
    "$GBRAIN_BIN" --version 2>/dev/null)" || return 1
  [ "$reported_version" = "gbrain $PIN_VERSION" ]
}
if ! gbrain_runtime_receipt_valid; then
  if [ -e "$GBRAIN_ROOT" ] || [ -L "$GBRAIN_ROOT" ]; then
    if [ ! -d "$GBRAIN_ROOT" ] || [ -L "$GBRAIN_ROOT" ]; then
      echo "refusing unsafe private gbrain root" >&2
      exit 1
    fi
    if [ -L "$GBRAIN_RECEIPT" ] \
        || { [ -e "$GBRAIN_RECEIPT" ] && [ ! -f "$GBRAIN_RECEIPT" ]; }; then
      echo "refusing unsafe private gbrain receipt" >&2
      exit 1
    fi
    if [ "${SIA_REPLACE_TOOLCHAIN:-0}" != "1" ]; then
      echo "existing private gbrain tree lacks an exact current release receipt; preserved" >&2
      echo "explicit replacement requires SIA_REPLACE_TOOLCHAIN=1 ./install.sh" >&2
      exit 1
    fi
    GBRAIN_TREE_EXPECTED="$(owned_tree_generation "$GBRAIN_ROOT")" \
      || exit 1
  else
    GBRAIN_TREE_EXPECTED=absent
  fi
  GBRAIN_SOURCE="$SIA_INSTALL_TMP/gbrain-source"
  run_with_deadline 300 git init -q "$GBRAIN_SOURCE"
  run_with_deadline 300 git -C "$GBRAIN_SOURCE" remote add origin \
    https://github.com/garrytan/gbrain.git
  run_with_deadline 1800 git -C "$GBRAIN_SOURCE" \
    -c protocol.version=2 fetch --depth 1 --no-tags \
    origin "$PIN"
  run_with_deadline 300 git -C "$GBRAIN_SOURCE" \
    checkout -q --detach FETCH_HEAD
  [ "$(bounded_command_capture git -C "$GBRAIN_SOURCE" rev-parse HEAD)" \
    = "$PIN" ] || {
    echo "gbrain checkout did not resolve to the requested commit" >&2; exit 1; }
  printf '%s  %s\n' "$PIN_LOCK_SHA256" "$GBRAIN_SOURCE/bun.lock" \
    | sha256sum -c -
  BUN_INSTALL_CACHE_DIR="$SIA_INSTALL_TMP/bun-cache" \
    run_with_deadline 1800 "$BUN_BIN" install --cwd "$GBRAIN_SOURCE" \
      --frozen-lockfile \
      --production --ignore-scripts --no-progress
  printf '%s  %s\n' "$PIN_LOCK_SHA256" "$GBRAIN_SOURCE/bun.lock" \
    | sha256sum -c -
  SIA_GBRAIN_STAGE="$(mktemp -d "$TOOLCHAIN/.gbrain.stage.XXXXXX")"
  mkdir -p "$SIA_GBRAIN_STAGE/bin"
  run_with_deadline 1800 "$BUN_BIN" build --compile \
    --outfile "$SIA_GBRAIN_STAGE/bin/gbrain" \
    "$GBRAIN_SOURCE/src/cli.ts"
  chmod 0755 "$SIA_GBRAIN_STAGE/bin/gbrain"
  GBRAIN_VERSION_OUTPUT="$(bounded_command_capture \
    "$SIA_GBRAIN_STAGE/bin/gbrain" --version)"
  [ "$GBRAIN_VERSION_OUTPUT" = "gbrain $PIN_VERSION" ] || {
    echo "compiled gbrain version mismatch" >&2; exit 1; }
  GBRAIN_BINARY_SHA256="$(owned_metadata digest \
    "$SIA_GBRAIN_STAGE/bin/gbrain")" || exit 1
  printf 'managed-by=khephri.sia\ncommit=%s\nversion=%s\nbun_lock_sha256=%s\nbinary_sha256=%s\n' \
    "$PIN" "$PIN_VERSION" "$PIN_LOCK_SHA256" "$GBRAIN_BINARY_SHA256" \
    > "$SIA_GBRAIN_STAGE/.sia-release"
  SIA_INSTALL_MUTATED=1
  GBRAIN_RESULT="$(atomic_install_tree "$SIA_GBRAIN_STAGE" "$GBRAIN_ROOT" \
    "$TOOLCHAIN/.gbrain.previous.XXXXXX" "$GBRAIN_TREE_EXPECTED")"
  IFS=$'\t' read -r _GBRAIN_INSTALLED_TREE GBRAIN_BACKUP \
    <<< "$GBRAIN_RESULT"
  SIA_GBRAIN_STAGE=""
  [ -z "$GBRAIN_BACKUP" ] \
    || echo "  previous private gbrain retained at $GBRAIN_BACKUP"
fi
gbrain_runtime_receipt_valid || {
  echo "private gbrain receipt or executable verification failed" >&2; exit 1; }
PATH="$GBRAIN_ROOT/bin:$BUN_ROOT/bin:$PATH"
export PATH
bounded_command_capture "$GBRAIN_BIN" --version
echo "  (compiled from requested gbrain commit $PIN and frozen lockfile)"

step "2/9 ollama (local embeddings — nothing leaves the machine)"
# Pin provenance (verified 2026-08-30):
# https://github.com/ollama/ollama/releases/tag/v0.33.2
# https://ollama.com/library/nomic-embed-text:v1.5
# https://registry.ollama.ai/v2/library/nomic-embed-text/manifests/v1.5
OLLAMA_VERSION=0.33.2
OLLAMA_TAG="v$OLLAMA_VERSION"
OLLAMA_ASSET="ollama-linux-${OLLAMA_ARCH}.tar.zst"
NOMIC_MANIFEST_SHA256=0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f
NOMIC_MODEL=nomic-embed-text:v1.5
NOMIC_COMPAT_ALIAS=nomic-embed-text:latest
OLLAMA_BIN="$HOME/opt/ollama/bin/ollama"
OLLAMA_RECEIPT="$HOME/opt/ollama/.sia-release"
OLLAMA_RUNTIME_CHANGED=0
OLLAMA_UNIT="$SYSTEMD_USER_DIR/ollama.service"
OLLAMA_UNIT_CHANGED=0
OLLAMA_RECEIPT_EXPECTED="managed-by=khephri.sia
version=$OLLAMA_VERSION
asset=$OLLAMA_ASSET
sha256=$OLLAMA_SHA256"
mkdir -p "$HOME/opt"
owned_tree_cas recover "$HOME/opt/ollama" || exit 1
ollama_runtime_receipt_valid() {
  local reported_version
  [ -x "$OLLAMA_BIN" ] && [ -f "$OLLAMA_RECEIPT" ] \
    && [ ! -L "$OLLAMA_BIN" ] && [ ! -L "$OLLAMA_RECEIPT" ] || return 1
  owned_metadata release "$OLLAMA_RECEIPT" "$OLLAMA_BIN" \
    "$OLLAMA_RECEIPT_EXPECTED" || return 1
  reported_version="$(ollama_client_version "$OLLAMA_BIN")" || return 1
  [ "$reported_version" = "$OLLAMA_VERSION" ] || return 1
}

inspect_user_unit ollama.service OLLAMA_INSPECT || exit 1
if [ "$OLLAMA_INSPECT_LOAD_STATE" = loaded ] \
    && [ "$OLLAMA_INSPECT_FRAGMENT_PATH" != "$OLLAMA_UNIT" ]; then
  echo "ollama.service is loaded from an unowned path: $OLLAMA_INSPECT_FRAGMENT_PATH" >&2
  exit 1
fi
if [ -e "$OLLAMA_UNIT" ] || [ -L "$OLLAMA_UNIT" ]; then
  if [ ! -f "$OLLAMA_UNIT" ] || [ -L "$OLLAMA_UNIT" ]; then
    echo "refusing unsafe ollama.service unit path" >&2
    exit 1
  fi
  if owned_metadata same-content \
      "$REPO/systemd/sia-ollama.service" "$OLLAMA_UNIT"; then
    :
  else
    OLLAMA_UNIT_CHANGED=1
    if ! managed_receipt_matches "$OLLAMA_UNIT_RECEIPT" ollama-unit \
          "$OLLAMA_UNIT" \
        && [ "${SIA_REPLACE_OLLAMA_UNIT:-0}" != "1" ]; then
      echo "existing ollama.service is unowned or locally modified; preserved" >&2
      echo "SIA will not start or enable it; replacement requires" >&2
      echo "  SIA_REPLACE_OLLAMA_UNIT=1 ./install.sh" >&2
      exit 1
    fi
  fi
elif [ "$OLLAMA_INSPECT_LOAD_STATE" != not-found ] \
    || [ "$OLLAMA_INSPECT_ACTIVE_STATE" != inactive ] \
    || [ -n "$OLLAMA_INSPECT_UNIT_FILE_STATE" ]; then
  echo "ollama.service resolves outside SIA's managed unit path; preserved" >&2
  exit 1
else
  OLLAMA_UNIT_CHANGED=1
fi
SIA_OLLAMA_ENABLE_STATE="$OLLAMA_INSPECT_UNIT_FILE_STATE"
if [ "$SIA_OLLAMA_ENABLE_STATE" = enabled ] \
    || [ "$SIA_OLLAMA_ENABLE_STATE" = enabled-runtime ]; then
  SIA_OLLAMA_WAS_ENABLED=1
fi
if [ "$OLLAMA_INSPECT_ACTIVE_STATE" = active ]; then
  SIA_OLLAMA_WAS_ACTIVE=1
fi

if ! ollama_runtime_receipt_valid; then
  if [ -e "$HOME/opt/ollama" ] || [ -L "$HOME/opt/ollama" ]; then
    if [ ! -d "$HOME/opt/ollama" ] || [ -L "$HOME/opt/ollama" ]; then
      echo "refusing unsafe Ollama runtime root" >&2
      exit 1
    fi
    if [ -L "$OLLAMA_RECEIPT" ] \
        || { [ -e "$OLLAMA_RECEIPT" ] && [ ! -f "$OLLAMA_RECEIPT" ]; }; then
      echo "refusing unsafe Ollama runtime receipt" >&2
      exit 1
    fi
    if [ "${SIA_REPLACE_OLLAMA_RUNTIME:-0}" != "1" ]; then
      echo "existing $HOME/opt/ollama is not demonstrably SIA-managed; preserved" >&2
      echo "explicit replacement requires SIA_REPLACE_OLLAMA_RUNTIME=1 ./install.sh" >&2
      exit 1
    fi
    OLLAMA_TREE_EXPECTED="$(owned_tree_generation "$HOME/opt/ollama")" \
      || exit 1
  else
    OLLAMA_TREE_EXPECTED=absent
  fi
  download_verified \
    "https://github.com/ollama/ollama/releases/download/$OLLAMA_TAG/$OLLAMA_ASSET" \
    "$SIA_INSTALL_TMP/$OLLAMA_ASSET" "$OLLAMA_SHA256"
  SIA_OLLAMA_STAGE="$(mktemp -d "$HOME/opt/.ollama.stage.XXXXXX")"
  run_with_deadline 300 tar --zstd \
    -xf "$SIA_INSTALL_TMP/$OLLAMA_ASSET" -C "$SIA_OLLAMA_STAGE"
  [ -x "$SIA_OLLAMA_STAGE/bin/ollama" ] || {
    echo "verified Ollama archive has no executable bin/ollama"; exit 1; }
  [ "$(ollama_client_version "$SIA_OLLAMA_STAGE/bin/ollama")" = "$OLLAMA_VERSION" ] || {
    echo "verified Ollama archive does not report $OLLAMA_VERSION"; exit 1; }
  OLLAMA_BINARY_SHA256="$(owned_metadata digest \
    "$SIA_OLLAMA_STAGE/bin/ollama")" || exit 1
  printf '%s\nbinary_sha256=%s\n' "$OLLAMA_RECEIPT_EXPECTED" \
    "$OLLAMA_BINARY_SHA256" > "$SIA_OLLAMA_STAGE/.sia-release"
  SIA_INSTALL_MUTATED=1
  OLLAMA_RESULT="$(atomic_install_tree "$SIA_OLLAMA_STAGE" \
    "$HOME/opt/ollama" "$HOME/opt/.ollama.previous.XXXXXX" \
    "$OLLAMA_TREE_EXPECTED")"
  IFS=$'\t' read -r _OLLAMA_INSTALLED_TREE OLLAMA_BACKUP \
    <<< "$OLLAMA_RESULT"
  SIA_OLLAMA_STAGE=""
  [ -z "$OLLAMA_BACKUP" ] || echo "  previous Ollama tree retained at $OLLAMA_BACKUP"
  OLLAMA_RUNTIME_CHANGED=1
fi
OLLAMA_LINK="$HOME/.local/bin/ollama"
if [ ! -e "$OLLAMA_LINK" ] && [ ! -L "$OLLAMA_LINK" ]; then
  SIA_INSTALL_MUTATED=1
  ln -s -- "$OLLAMA_BIN" "$OLLAMA_LINK"
  OLLAMA_LINK_DIGEST="$(printf '%s' "$OLLAMA_BIN" | sha256sum | cut -d' ' -f1)"
  write_managed_receipt "$OLLAMA_LINK_RECEIPT" ollama-link \
    "$OLLAMA_LINK" "$OLLAMA_LINK_DIGEST"
  echo "  installed optional Ollama command link"
elif [ -L "$OLLAMA_LINK" ] && [ "$(readlink "$OLLAMA_LINK")" = "$OLLAMA_BIN" ]; then
  OLLAMA_LINK_DIGEST="$(printf '%s' "$OLLAMA_BIN" | sha256sum | cut -d' ' -f1)"
  write_managed_receipt "$OLLAMA_LINK_RECEIPT" ollama-link \
    "$OLLAMA_LINK" "$OLLAMA_LINK_DIGEST"
  echo "  adopted exact Ollama command link"
else
  echo "  existing ~/.local/bin/ollama is unrelated; preserved"
fi

SIA_INSTALL_MUTATED=1
install_owned_file "$REPO/systemd/sia-ollama.service" "$OLLAMA_UNIT" 0644 \
  "$OLLAMA_UNIT_RECEIPT" ollama-unit SIA_REPLACE_OLLAMA_UNIT
run_with_deadline 120 systemctl --user daemon-reload
if [ "$SIA_OLLAMA_WAS_ACTIVE" -eq 0 ]; then
  SIA_OLLAMA_SERVICE_MUTATED=1
  run_with_deadline 120 systemctl --user start ollama.service
elif [ "$OLLAMA_RUNTIME_CHANGED" -eq 1 ] \
    || [ "$OLLAMA_UNIT_CHANGED" -eq 1 ]; then
  SIA_OLLAMA_SERVICE_MUTATED=1
  run_with_deadline 120 systemctl --user restart ollama.service
fi
sleep 2
export OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_SERVER_VERSION="$(bounded_command_capture "$OLLAMA_BIN" --version \
  | sed -n 's/^ollama version is //p' | head -n 1)"
if [ -z "$OLLAMA_SERVER_VERSION" ]; then
  echo "ollama.service did not answer on $OLLAMA_HOST"
  exit 1
elif [ "$OLLAMA_SERVER_VERSION" != "$OLLAMA_VERSION" ]; then
  if [ "${SIA_ALLOW_UNPINNED_OLLAMA:-0}" != "1" ]; then
    echo "ollama.service reports '${OLLAMA_SERVER_VERSION:-unavailable}', expected $OLLAMA_VERSION"
    echo "fix the service, or explicitly accept the weaker runtime boundary with:"
    echo "  SIA_ALLOW_UNPINNED_OLLAMA=1 ./install.sh"
    exit 1
  fi
  echo "  WARNING: accepting unpinned Ollama server '${OLLAMA_SERVER_VERSION:-unavailable}'"
fi
inspect_user_unit ollama.service OLLAMA_LIVE || exit 1
if [ "$OLLAMA_LIVE_LOAD_STATE" != loaded ] \
    || [ "$OLLAMA_LIVE_ACTIVE_STATE" != active ] \
    || [ "$OLLAMA_LIVE_FRAGMENT_PATH" != "$OLLAMA_UNIT" ]; then
  echo "ollama.service did not retain the exact managed unit shape" >&2
  exit 1
fi
OLLAMA_DAEMON_PID="$OLLAMA_LIVE_MAIN_PID"
[[ "$OLLAMA_DAEMON_PID" =~ ^[1-9][0-9]*$ ]] || {
  echo "cannot identify the ollama.service executable"; exit 1; }
OLLAMA_LOCAL_BINARY_SHA256="$(owned_metadata digest "$OLLAMA_BIN")" \
  || exit 1
OLLAMA_LIVE_BINARY_SHA256="$(sha256sum "/proc/$OLLAMA_DAEMON_PID/exe" \
  | cut -d' ' -f1)"
if [ "$OLLAMA_LIVE_BINARY_SHA256" != "$OLLAMA_LOCAL_BINARY_SHA256" ]; then
  if [ "${SIA_ALLOW_UNPINNED_OLLAMA:-0}" != "1" ]; then
    echo "ollama.service is not running SIA's verified Ollama binary"
    echo "fix the service, or explicitly accept the weaker runtime boundary with:"
    echo "  SIA_ALLOW_UNPINNED_OLLAMA=1 ./install.sh"
    exit 1
  fi
  echo "  WARNING: ollama.service executable differs from SIA's verified binary"
fi
if ! OLLAMA_LISTENERS="$(bounded_command_capture \
    ss -H -ltnp 'sport = :11434')"; then
  echo "could not inspect the Ollama TCP listener" >&2
  exit 1
fi
if ! python3 - "$OLLAMA_DAEMON_PID" "$OLLAMA_LISTENERS" <<'PY'
import ipaddress
import re
import sys

pid = sys.argv[1]
rows = [line.split() for line in sys.argv[2].splitlines() if line.strip()]
if not rows:
    raise SystemExit("ollama.service has no observable TCP listener on 11434")
for fields in rows:
    if len(fields) < 6 or not re.search(rf"pid={re.escape(pid)}(?:,|\))",
                                         " ".join(fields[5:])):
        raise SystemExit("port 11434 listener is not owned by ollama.service")
    endpoint = fields[3]
    host, separator, port = endpoint.rpartition(":")
    host = host.strip("[]")
    if not separator or port != "11434" or host in {"", "*"}:
        raise SystemExit(f"unsafe Ollama listener: {endpoint}")
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError as error:
        raise SystemExit(f"unsafe Ollama listener: {endpoint}") from error
    if not address.is_loopback:
        raise SystemExit(f"Ollama listener is not loopback-only: {endpoint}")
PY
then
  echo "ollama.service listener ownership/loopback verification failed" >&2
  exit 1
fi
echo "  Ollama listener is owned by the service and loopback-only"

OLLAMA_MODELS_DIR="$(effective_ollama_models_dir)"
NOMIC_MANIFEST="$OLLAMA_MODELS_DIR/manifests/registry.ollama.ai/library/nomic-embed-text/v1.5"
# Ollama v0.33.2's official parser does not retain an @digest selector for
# pulls. Pull the semantic v1.5 tag, then require its immutable manifest digest
# and independently hash every config/layer blob before SIA can use the model.
# Snapshot the prior manifest before the command. If the post-command state is
# rejected, preserve both generations for manual attribution; never roll a
# shared Ollama name back based on a post-hoc observation.
# Downloaded blobs are content-addressed and may remain unreferenced.
NOMIC_PULL_BACKUP=""
if [ -f "$NOMIC_MANIFEST" ] && [ ! -L "$NOMIC_MANIFEST" ]; then
  mkdir -p "$STATE/model-manifest-backups"
  NOMIC_PULL_BACKUP="$(mktemp \
    "$STATE/model-manifest-backups/nomic-v1.5.pre-pull.XXXXXX.json")"
  snapshot_model_manifest "$NOMIC_MANIFEST" "$NOMIC_PULL_BACKUP"
elif [ -e "$NOMIC_MANIFEST" ] || [ -L "$NOMIC_MANIFEST" ]; then
  echo "refusing unsafe nomic-embed-text:v1.5 manifest path"
  exit 1
else
  :
fi
if ! run_with_deadline 1800 "$OLLAMA_BIN" pull "$NOMIC_MODEL"; then
  echo "nomic-embed-text:v1.5 pull failed; post-command manifest preserved" >&2
  [ -z "$NOMIC_PULL_BACKUP" ] \
    || echo "pre-pull manifest retained at $NOMIC_PULL_BACKUP" >&2
  exit 1
fi
if [ ! -f "$NOMIC_MANIFEST" ] || [ -L "$NOMIC_MANIFEST" ]; then
  echo "nomic-embed-text manifest missing after pull; shared store preserved" >&2
  [ -z "$NOMIC_PULL_BACKUP" ] \
    || echo "pre-pull manifest retained at $NOMIC_PULL_BACKUP" >&2
  exit 1
fi
if ! verify_ollama_model_store "$OLLAMA_MODELS_DIR" "$NOMIC_MANIFEST" \
    "$NOMIC_MANIFEST_SHA256"; then
  echo "rejected v1.5 manifest preserved: command attribution is unavailable" >&2
  [ -z "$NOMIC_PULL_BACKUP" ] \
    || echo "pre-pull manifest retained at $NOMIC_PULL_BACKUP" >&2
  exit 1
fi
if [ -n "$NOMIC_PULL_BACKUP" ]; then
  NOMIC_PRE_PULL_SHA256="$(sha256sum "$NOMIC_PULL_BACKUP" | cut -d' ' -f1)"
  if [ "$NOMIC_PRE_PULL_SHA256" = "$NOMIC_MANIFEST_SHA256" ]; then
    rm -f -- "$NOMIC_PULL_BACKUP"
    NOMIC_PULL_BACKUP=""
  else
    echo "  pre-pull v1.5 manifest retained at $NOMIC_PULL_BACKUP"
  fi
fi
echo "  v1.5 model manifest and every referenced blob verified"

# Older gbrain databases may have persisted the untagged model name. Preserve
# compatibility with an alias only when it is absent or already resolves to
# the same pinned manifest. Replacing a different local alias requires explicit
# operator consent because model names are user-owned Ollama state.
NOMIC_ALIAS_MANIFEST="$OLLAMA_MODELS_DIR/manifests/registry.ollama.ai/library/nomic-embed-text/latest"
NOMIC_ALIAS_READY=0
NOMIC_ALIAS_BACKUP=""
if [ -f "$NOMIC_ALIAS_MANIFEST" ] && [ ! -L "$NOMIC_ALIAS_MANIFEST" ]; then
  if verify_ollama_model_store "$OLLAMA_MODELS_DIR" "$NOMIC_ALIAS_MANIFEST" \
      "$NOMIC_MANIFEST_SHA256"; then
    NOMIC_ALIAS_READY=1
    echo "  existing untagged compatibility alias is already pinned"
  elif [ "${SIA_REPLACE_NOMIC_LATEST:-0}" != "1" ]; then
    echo "existing nomic-embed-text:latest differs from SIA's v1.5 pin"
    echo "preserved it; inspect it, then explicitly replace with:"
    echo "  SIA_REPLACE_NOMIC_LATEST=1 ./install.sh"
    exit 1
  else
    mkdir -p "$STATE/model-manifest-backups"
    NOMIC_ALIAS_BACKUP="$(mktemp \
      "$STATE/model-manifest-backups/nomic-latest.XXXXXX.json")"
    snapshot_model_manifest "$NOMIC_ALIAS_MANIFEST" "$NOMIC_ALIAS_BACKUP"
    echo "  previous nomic-embed-text:latest manifest retained at $NOMIC_ALIAS_BACKUP"
  fi
elif [ -e "$NOMIC_ALIAS_MANIFEST" ] || [ -L "$NOMIC_ALIAS_MANIFEST" ]; then
  echo "refusing unsafe nomic-embed-text:latest manifest path"
  exit 1
else
  :
fi
if [ "$NOMIC_ALIAS_READY" -eq 0 ]; then
  if ! run_with_deadline 1800 "$OLLAMA_BIN" cp \
      "$NOMIC_MODEL" "$NOMIC_COMPAT_ALIAS"; then
    echo "alias copy failed; post-command shared manifest preserved" >&2
    [ -z "$NOMIC_ALIAS_BACKUP" ] \
      || echo "prior alias retained at $NOMIC_ALIAS_BACKUP" >&2
    exit 1
  fi
fi
if [ ! -f "$NOMIC_ALIAS_MANIFEST" ] || [ -L "$NOMIC_ALIAS_MANIFEST" ]; then
  echo "compatibility alias missing after copy; shared store preserved" >&2
  [ -z "$NOMIC_ALIAS_BACKUP" ] \
    || echo "prior alias retained at $NOMIC_ALIAS_BACKUP" >&2
  exit 1
fi
if ! verify_ollama_model_store "$OLLAMA_MODELS_DIR" \
    "$NOMIC_ALIAS_MANIFEST" "$NOMIC_MANIFEST_SHA256"; then
  echo "rejected compatibility alias preserved: command attribution is unavailable" >&2
  [ -z "$NOMIC_ALIAS_BACKUP" ] \
    || echo "prior alias retained at $NOMIC_ALIAS_BACKUP" >&2
  exit 1
fi
echo "  untagged compatibility alias verified"

# Commit enablement only after every live-runtime, listener, model, and alias
# check has succeeded.  Failure cleanup leaves any rejected service stopped.
if [ "$SIA_OLLAMA_WAS_ENABLED" -eq 0 ]; then
  SIA_OLLAMA_SERVICE_MUTATED=1
  run_with_deadline 120 systemctl --user enable ollama.service
fi

step "3/9 runtime"
SIA_RUNTIME_STAGE="$(mktemp -d "$SHARE/.bin.stage.XXXXXX")"
for runtime_module in sialib.py siamind.py siatakes.py siabench.py siaqueue.py; do
  install -m 0644 "$REPO/bin/$runtime_module" \
    "$SIA_RUNTIME_STAGE/$runtime_module"
done
for runtime_command in sia-ledger sia-mcp; do
  install -m 0755 "$REPO/bin/$runtime_command" \
    "$SIA_RUNTIME_STAGE/$runtime_command"
done
install -m 0755 "$SIA_STABLE_LAUNCHER" \
  "$SIA_RUNTIME_STAGE/sia-brainstem"
install -m 0644 "$REPO/bin/sia-brainstem" \
  "$SIA_RUNTIME_STAGE/sia-brainstem.py"
install -m 0644 "$REPO/bin/sia" "$SIA_RUNTIME_STAGE/sia-cli"
STAGED_RUNTIME_DIGEST="$(runtime_tree_digest "$SIA_RUNTIME_STAGE")"
update_install_launch_fence_desired "$STAGED_RUNTIME_DIGEST"
# The durable mode fence has excluded new opens since before engine/model
# mutation. This final drain is an assertion that no pre-fence process survived
# to the publication point; it is not itself used as an admission gate.
drain_legacy_launchers
RUNTIME_RESULT="$(atomic_install_tree "$SIA_RUNTIME_STAGE" "$BINDIR" \
  "$SHARE/.bin.previous.XXXXXX" "$SIA_RUNTIME_TREE_EXPECTED")"
IFS=$'\t' read -r SIA_RUNTIME_INSTALLED_TREE RUNTIME_BACKUP \
  <<< "$RUNTIME_RESULT"
SIA_RUNTIME_STAGE=""
restore_retained_runtime_fence_modes "$RUNTIME_BACKUP"
[ -z "$RUNTIME_BACKUP" ] || {
  echo "  previous runtime tree retained at $RUNTIME_BACKUP"
  echo "  (review and remove it manually after confirming the upgrade)"
}
install_preflighted_cli
write_runtime_receipt "$SIA_RUNTIME_INSTALLED_TREE" "$STAGED_RUNTIME_DIGEST"
complete_install_launch_fence "$SIA_RUNTIME_INSTALLED_TREE" \
  "$STAGED_RUNTIME_DIGEST"

# Byte-exact digest of the immediately preceding public release's GBRAIN_PIN.
# This is deliberate one-time legacy authority, not a managed-by inference.
install_owned_file "$REPO/GBRAIN_PIN" "$SHARE/GBRAIN_PIN" 0644 \
  "$GBRAIN_PIN_RECEIPT" gbrain-pin SIA_REPLACE_GBRAIN_PIN \
  973e873979d0fccd67383087a33b78444d008a5cf7d952a978a49d884e414f74
CONFIG_PATH="$CONFIG_DIR/config.json"
if [ -L "$CONFIG_PATH" ] \
    || { [ -e "$CONFIG_PATH" ] && [ ! -f "$CONFIG_PATH" ]; }; then
  echo "refusing unsafe SIA configuration path" >&2
  exit 1
elif [ ! -e "$CONFIG_PATH" ]; then
  atomic_install_file "$REPO/config.example.json" \
    "$CONFIG_PATH" 0644 absent >/dev/null
fi

step "4/9 the corpus (your memory, as files, in git)"
SIA_GENESIS_README="# SIA corpus — this machine's memory"
if [ "$SIA_CORPUS_BOOTSTRAP_NEEDED" -eq 1 ]; then
  if [ ! -e "$CORPUS_BOOTSTRAP_INTENT" ] \
      && [ ! -L "$CORPUS_BOOTSTRAP_INTENT" ]; then
    write_corpus_bootstrap_intent
  fi
  # The durable intent precedes off-path construction. Only its exact staged
  # generation may claim an absent canonical corpus name.
  ensure_corpus_bootstrap_root || {
    echo "corpus root could not be published from its durable intent" >&2
    exit 1
  }
  SIA_CORPUS_BOOTSTRAP_PHASE="$(corpus_bootstrap_intent_valid)" || {
    echo "corpus does not match its durable bootstrap intent" >&2
    exit 1
  }
  # Durable bootstrap boundary: target directory creation is replayable.
  case "$SIA_CORPUS_BOOTSTRAP_PHASE" in
    empty|git|readme) ;;
    *) echo "corpus bootstrap is not a resumable prefix" >&2; exit 1 ;;
  esac
  validate_fresh_corpus() {
    [ "$(corpus_bootstrap_intent_valid)" = readme ]
  }
  SIA_GENESIS_BLOB="$(printf '%s\n' "$SIA_GENESIS_README" \
    | bounded_command_capture --stdin env \
      -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
      -u GIT_OBJECT_DIRECTORY -u GIT_ALTERNATE_OBJECT_DIRECTORIES \
      -u GIT_CONFIG_PARAMETERS -u GIT_CONFIG_COUNT -u GIT_TEMPLATE_DIR \
      GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_ATTR_NOSYSTEM=1 \
      git -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c commit.gpgsign=false -C "$SHARE/corpus" hash-object --stdin)"
  exact_corpus_genesis() {
    validate_fresh_corpus \
      && [ "$(bounded_corpus_git -C "$SHARE/corpus" \
        rev-list --count HEAD)" = 1 ] \
      && [ "$(bounded_corpus_git -C "$SHARE/corpus" \
        rev-parse HEAD:README.md)" = "$SIA_GENESIS_BLOB" ] \
      && [ "$(bounded_corpus_git -C "$SHARE/corpus" \
        rev-parse :README.md)" = "$SIA_GENESIS_BLOB" ] \
      && [ "$(bounded_corpus_git -C "$SHARE/corpus" \
        ls-tree -r --name-only HEAD)" = README.md ] \
      && [ "$(bounded_corpus_git -C "$SHARE/corpus" \
        log -1 --format=%s HEAD)" = genesis ] \
      && safe_corpus_git -C "$SHARE/corpus" diff --no-ext-diff \
        --no-textconv --quiet -- README.md \
      && safe_corpus_git -C "$SHARE/corpus" diff --no-ext-diff \
        --no-textconv --cached --quiet --
  }
  SIA_CORPUS_ALREADY_COMMITTED=0
  if [ "$SIA_CORPUS_BOOTSTRAP_PHASE" != empty ] \
      && bounded_corpus_git -C "$SHARE/corpus" rev-parse --verify HEAD \
        >/dev/null 2>&1; then
    exact_corpus_genesis || {
      echo "preexisting corpus HEAD is not the exact genesis commit" >&2
      exit 1
    }
    SIA_CORPUS_ALREADY_COMMITTED=1
  elif [ -e "$SHARE/corpus/.git/refs/heads/sia-genesis" ] \
      || [ -L "$SHARE/corpus/.git/refs/heads/sia-genesis" ]; then
    echo "corpus bootstrap branch is present but does not resolve exactly" >&2
    exit 1
  fi

  if [ "$SIA_CORPUS_ALREADY_COMMITTED" -eq 0 ]; then
    # The hardened command environment disables templates, hooks, inherited
    # repositories/config, signing, and fsmonitor before any Git mutation.
    safe_corpus_git -C "$SHARE/corpus" init -q -b sia-genesis --template=
  # Durable bootstrap boundary: hardened git initialization is replayable.
  SIA_CORPUS_BOOTSTRAP_PHASE="$(corpus_bootstrap_intent_valid)"
  case "$SIA_CORPUS_BOOTSTRAP_PHASE" in
    git) ;;
    readme) ;;
    *) echo "git initialization produced an unsafe corpus prefix" >&2; exit 1 ;;
  esac
  if [ "$SIA_CORPUS_BOOTSTRAP_PHASE" = git ]; then
    python3 - "$SHARE/corpus" "$SIA_GENESIS_README" <<'PY'
import os
import stat
import sys

root = os.path.abspath(sys.argv[1])
text = sys.argv[2]
directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                   | getattr(os, "O_DIRECTORY", 0)
                   | getattr(os, "O_NOFOLLOW", 0))
file_flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
              | getattr(os, "O_CLOEXEC", 0)
              | getattr(os, "O_NOFOLLOW", 0))
directory = os.open(root, directory_flags)
try:
    root_info = os.fstat(directory)
    if not stat.S_ISDIR(root_info.st_mode) \
            or root_info.st_uid != os.geteuid():
        raise ValueError("unsafe fresh corpus root")
    descriptor = os.open("README.md", file_flags, 0o644, dir_fd=directory)
    try:
        content = (text + "\n").encode("utf-8")
        remaining = memoryview(content)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("short corpus genesis write")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.fsync(directory)
finally:
    os.close(directory)
PY
    fi
  validate_fresh_corpus
  safe_corpus_git -C "$SHARE/corpus" add -- README.md
  # Durable bootstrap boundary: the exact narrow index update is replayable.
  validate_fresh_corpus
  [ "$(bounded_corpus_git -C "$SHARE/corpus" \
      rev-parse :README.md)" = "$SIA_GENESIS_BLOB" ] || {
    echo "fresh corpus README changed before genesis commit" >&2
    exit 1
  }
  if ! safe_corpus_git -C "$SHARE/corpus" diff --no-ext-diff \
      --no-textconv --cached --quiet -- . ':(exclude)README.md'; then
    echo "fresh corpus index gained concurrent entries; refusing genesis" >&2
    exit 1
  fi
  if bounded_corpus_git -C "$SHARE/corpus" rev-parse --verify HEAD \
      >/dev/null 2>&1; then
    [ "$(bounded_corpus_git -C "$SHARE/corpus" \
        rev-list --count HEAD)" = 1 ] || {
      echo "corpus bootstrap HEAD is not the single genesis commit" >&2
      exit 1
    }
  else
    safe_corpus_git -C "$SHARE/corpus" \
      -c user.email=sia@localhost -c user.name=SIA commit -qm genesis
  fi
  # Durable bootstrap boundary: the exact genesis commit is replayable.
  fi
  exact_corpus_genesis || {
    echo "corpus genesis commit is not the exact producer shape" >&2
    exit 1
  }
elif [ ! -d "$SHARE/corpus" ] || [ -L "$SHARE/corpus" ] \
    || [ ! -d "$SHARE/corpus/.git" ] || [ -L "$SHARE/corpus/.git" ]; then
  echo "refusing unsafe corpus or git metadata" >&2
  exit 1
fi
if [ "$SIA_CORPUS_ADOPTION_NEEDED" -eq 1 ]; then
  corpus_adoption_intent_valid || {
    echo "corpus changed after durable adoption consent; preserved" >&2
    exit 1
  }
fi
[ "$(bounded_corpus_git -C "$SHARE/corpus" \
    rev-parse --is-inside-work-tree 2>/dev/null)" = true ] || {
  echo "corpus git repository validation failed" >&2
  exit 1
}
if [ "$SIA_CORPUS_NEEDS_RECEIPT" -eq 1 ]; then
  write_corpus_receipt
  # Durable bootstrap/adoption boundary: receipt publication is replayable.
fi
if [ "$SIA_CORPUS_BOOTSTRAP_NEEDED" -eq 1 ]; then
  retire_corpus_bootstrap_intent
fi
if [ "$SIA_CORPUS_ADOPTION_NEEDED" -eq 1 ]; then
  retire_corpus_adoption_intent
fi
step "5/9 the brain (gbrain · PGLite · local embeddings)"
export GBRAIN_HOME="$SHARE"
preflight_gbrain_bootstrap
if [ "$SIA_GBRAIN_BOOTSTRAP_NEEDED" -eq 1 ]; then
  complete_gbrain_bootstrap
fi
GBRAIN_CONFIG_PATH="$SHARE/.gbrain/config.json"
if [ ! -f "$GBRAIN_CONFIG_PATH" ] || [ -L "$GBRAIN_CONFIG_PATH" ]; then
  echo "refusing to mutate an unsafe or missing gbrain config" >&2
  exit 1
fi
# self_upgrade.mode is a canonical file-plane setting in this gbrain release.
# `gbrain config set` writes the DB plane and can be shadowed by config.json,
# so update the plane the runtime actually reads and then verify through the
# pinned CLI. Capture one bounded, no-follow generation and publish its staged
# successor only if the live name still denotes that exact generation.
GBRAIN_CONFIG_EXPECTED="$(
  owned_metadata generation "$GBRAIN_CONFIG_PATH")" || {
    echo "gbrain config is not an owned bounded stable file" >&2
    exit 1
  }
GBRAIN_CONFIG_STAGE="$(mktemp \
  "$(dirname "$GBRAIN_CONFIG_PATH")/.config.json.sia-stage.XXXXXX")"
if ! GBRAIN_CONFIG_ACTION="$(
    python3 - "$GBRAIN_CONFIG_PATH" "$GBRAIN_CONFIG_STAGE" <<'PY'
import json
import os
import stat
import sys

path, staged = map(os.path.abspath, sys.argv[1:])
# JACKAL status=exact, parsed=1024*1024, exact=1048576. Exact rational
# arithmetic outside the Lean certificate chain (NOT formal-bounded).
MAX_BYTES = 1_048_576
READ_BYTES = 65_536
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_NOFOLLOW", 0))


def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def reject_constant(value):
    raise ValueError(f"non-finite JSON number: {value}")


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate gbrain config key: {key}")
        value[key] = item
    return value


descriptor = os.open(path, flags)
try:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) \
            or before.st_uid != os.geteuid() \
            or before.st_mode & 0o022 or before.st_size > MAX_BYTES:
        raise ValueError(
            "gbrain config is not owned, bounded, and protected from other writers")
    chunks = []
    remaining = MAX_BYTES + 1
    while remaining:
        chunk = os.read(descriptor, min(remaining, READ_BYTES))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    after = os.fstat(descriptor)
    current = os.stat(path, follow_symlinks=False)
    if len(raw) != before.st_size or len(raw) > MAX_BYTES \
            or generation(before) != generation(after) \
            or generation(after) != generation(current):
        raise ValueError("gbrain config changed while read")
finally:
    os.close(descriptor)
try:
    config = json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=unique_object, parse_constant=reject_constant)
except (UnicodeError, json.JSONDecodeError, ValueError) as error:
    raise SystemExit(f"gbrain config is not strict unambiguous JSON: {error}") \
        from error
if not isinstance(config, dict):
    raise SystemExit("gbrain config root is not an object")
self_upgrade = config.get("self_upgrade")
if self_upgrade is None:
    self_upgrade = {}
elif not isinstance(self_upgrade, dict):
    raise SystemExit("gbrain self_upgrade config is not an object")
if self_upgrade.get("mode") == "off":
    print("unchanged")
    raise SystemExit(0)
self_upgrade["mode"] = "off"
config["self_upgrade"] = self_upgrade
encoded = (json.dumps(
    config, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode(
        "utf-8")
if len(encoded) > MAX_BYTES:
    raise SystemExit("updated gbrain config exceeds its byte ceiling")
if os.path.dirname(staged) != os.path.dirname(path):
    raise SystemExit("gbrain config stage is not a sibling")
stage_info = os.lstat(staged)
if not stat.S_ISREG(stage_info.st_mode) \
        or stage_info.st_uid != os.geteuid() or stage_info.st_size != 0:
    raise SystemExit("gbrain config stage is unsafe")
write_flags = (os.O_WRONLY | os.O_TRUNC | getattr(os, "O_CLOEXEC", 0)
               | getattr(os, "O_NOFOLLOW", 0))
descriptor = os.open(staged, write_flags)
try:
    remaining = memoryview(encoded)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("short gbrain config stage write")
        remaining = remaining[written:]
    os.fchmod(descriptor, stat.S_IMODE(before.st_mode))
    os.fsync(descriptor)
finally:
    os.close(descriptor)
print("publish")
PY
  )"; then
  rm -f -- "$GBRAIN_CONFIG_STAGE"
  echo "could not prepare a bounded gbrain configuration update" >&2
  exit 1
fi
case "$GBRAIN_CONFIG_ACTION" in
  unchanged)
    rm -f -- "$GBRAIN_CONFIG_STAGE"
    ;;
  publish)
    if ! owned_file_cas publish "$GBRAIN_CONFIG_STAGE" \
        "$GBRAIN_CONFIG_PATH" "$GBRAIN_CONFIG_EXPECTED" >/dev/null; then
      [ ! -e "$GBRAIN_CONFIG_STAGE" ] || {
        echo "  staged/conflicting gbrain config retained at $GBRAIN_CONFIG_STAGE" >&2
      }
      echo "gbrain config changed concurrently; preserved" >&2
      exit 1
    fi
    [ ! -e "$GBRAIN_CONFIG_STAGE" ] || {
      echo "  previous gbrain config retained at $GBRAIN_CONFIG_STAGE"
    }
    ;;
  *)
    rm -f -- "$GBRAIN_CONFIG_STAGE"
    echo "unexpected gbrain config preparation result" >&2
    exit 1
    ;;
esac
if ! GBRAIN_SELF_UPGRADE_MODE="$(bounded_command_capture \
    "$GBRAIN_BIN" config get self_upgrade.mode)"; then
  echo "could not verify that gbrain self-upgrade is disabled" >&2
  exit 1
fi
[ "$GBRAIN_SELF_UPGRADE_MODE" = "off" ] || {
  echo "gbrain self-upgrade is not disabled after configuration" >&2
  printf '  observed mode: %s\n' "$GBRAIN_SELF_UPGRADE_MODE" >&2
  exit 1
}
if ! SIA_SOURCES_JSON="$(bounded_command_capture \
    "$GBRAIN_BIN" sources list --json)"; then
  echo "could not inspect gbrain source registration" >&2
  exit 1
fi
if ! SIA_SOURCE_STATE="$(python3 -c '
import json
import sys

expected = sys.argv[1]
payload = json.load(sys.stdin)
sources = [source for source in payload.get("sources", [])
           if source.get("id") == "sia"]
if not sources:
    print("absent")
elif len(sources) == 1 and sources[0].get("local_path") == expected:
    print("match")
else:
    print("mismatch")
' "$SHARE/corpus" <<< "$SIA_SOURCES_JSON")"; then
  echo "could not parse gbrain source registration" >&2
  exit 1
fi
case "$SIA_SOURCE_STATE" in
  absent) run_with_deadline 300 "$GBRAIN_BIN" sources add sia \
      --path "$SHARE/corpus" ;;
  match) echo "  existing gbrain source registration matches SIA corpus" ;;
  mismatch)
    echo "existing gbrain source 'sia' points somewhere else; preserved it" >&2
    echo "remove or rename that source deliberately, then rerun install.sh" >&2
    exit 1
    ;;
  *) echo "unexpected gbrain source inspection result" >&2; exit 1 ;;
esac
mkdir -p "$SHARE/.gbrain/schema-packs/sia-pack"
# Byte-exact digest of the immediately preceding public schema pack; future
# upgrades are authorized by the receipt written below.
install_owned_file "$REPO/schema-pack/pack.yaml" \
  "$SHARE/.gbrain/schema-packs/sia-pack/pack.yaml" 0644 \
  "$SCHEMA_PACK_RECEIPT" schema-pack SIA_REPLACE_SCHEMA_PACK \
  37ced12281bff4b16a99295fa65cd673ffd87986c19da3d539e7bc2ca38c228d
run_with_deadline 300 "$GBRAIN_BIN" schema validate sia-pack >/dev/null
run_with_deadline 300 "$GBRAIN_BIN" schema use sia-pack >/dev/null

step "6/9 your signed run ledger (new identity only on fresh install)"
python3 "$BINDIR/sia-ledger" init "$SHARE"
# Record two distinct, already-established installer facts. The SIA-ledger
# sense projects these keeper-signed rows on first light, giving even a fresh
# standalone install a balanced, answer-bearing benchmark seed without
# inventing synthetic memory or feeding PULSE/benchmark output back into it.
python3 - "$BINDIR" <<'PY'
import sys

sys.path.insert(0, sys.argv[1])
import sialib

sialib.durable_ledger_append(
    "INSTALL:runtime", f"sia-{sialib.VERSION}", "prepared")
sialib.durable_ledger_append(
    "INSTALL:index", "sia", "registered")
PY

step "7/9 first light — backfilling YOUR machine's history"
if [ "$SIA_BRAINSTEM_BARRIER_DEFERRED" -eq 1 ]; then
  install_brainstem_runtime_barrier
fi
install_owned_file "$REPO/systemd/sia-brainstem.service" "$BRAINSTEM_UNIT" \
  0644 "$BRAINSTEM_RECEIPT" brainstem-unit SIA_REPLACE_BRAINSTEM_UNIT
run_with_deadline 120 systemctl --user daemon-reload
SIA_BRAINSTEM_BARRIER_DEFERRED=0
run_with_deadline 120 systemctl --user stop sia-brainstem.service
run_with_deadline 120 systemctl --user reset-failed \
  sia-brainstem.service >/dev/null 2>&1 || true
verify_install_brainstem_runtime_barrier
# The new CLI acquires these exact leases itself. Release the inherited
# quiescence leases before launching it. The parent keeps the lifecycle lease
# exclusive and a purged install keeps its tombstone. The child can cross both
# gates only through the inherited open-file description that the CLI and
# nested sialib readers validate independently. Reacquire the brainstem lease
# after first light so no resident daemon can start before integration ends.
flock -u "$SIA_GBRAIN_LOCK_FD"
exec {SIA_GBRAIN_LOCK_FD}>&-
SIA_GBRAIN_LOCK_FD=""
flock -u "$SIA_CORPUS_LOCK_FD"
exec {SIA_CORPUS_LOCK_FD}>&-
SIA_CORPUS_LOCK_FD=""
SIA_CORPUS_RECEIPT_LOCKS_HELD=0
flock -u "$SIA_BRAINSTEM_LOCK_FD"
exec {SIA_BRAINSTEM_LOCK_FD}>&-
SIA_BRAINSTEM_LOCK_FD=""
SIA_INHERITED_LIFECYCLE_FD="$SIA_INSTALL_LOCK_FD" \
  SIA_BACKFILL=1 python3 "$BINDIR/sia-cli" pulse
acquire_owner_lock "$STATE/brainstem-owner.lock" SIA_BRAINSTEM_LOCK_FD \
  "brainstem after first light"

step "8/9 desktop (Omarchy plugin + keybinding)"
PLUGDIR="$HOME/.config/omarchy/plugins/khephri.sia"
if have omarchy; then
  assert_safe_managed_roots "$HOME/.config/omarchy" \
    "$HOME/.config/omarchy/plugins" "$PLUGDIR"
fi
if [ "$SIA_ORIGINAL_REPO" != "$PLUGDIR" ] && have omarchy; then
  PLUGIN_PARENT="$(dirname "$PLUGDIR")"
  mkdir -p "$PLUGIN_PARENT"
  owned_tree_cas recover "$PLUGDIR" || exit 1
  if [ -e "$PLUGDIR" ] || [ -L "$PLUGDIR" ]; then
    if [ ! -d "$PLUGDIR" ] || [ -L "$PLUGDIR" ]; then
      echo "existing Omarchy plugin path is unsafe; preserved" >&2
      exit 1
    fi
    if [ "${SIA_REPLACE_PLUGIN:-0}" != "1" ]; then
      echo "existing Omarchy plugin tree is user-editable; preserved" >&2
      echo "explicit replacement requires SIA_REPLACE_PLUGIN=1 ./install.sh" >&2
      exit 1
    fi
    PLUGIN_TREE_EXPECTED="$(owned_tree_generation "$PLUGDIR")" || exit 1
  else
    PLUGIN_TREE_EXPECTED=absent
  fi
  SIA_PLUGIN_STAGE="$(mktemp -d "$PLUGIN_PARENT/.khephri.sia.stage.XXXXXX")"
  PLUGIN_ROOT_FILES=(manifest.json preview.png Panel.qml Cockpit.qml Model.js README.md
    LICENSE SECURITY.md CHANGELOG.md GBRAIN_PIN config.example.json install.sh
    uninstall.sh)
  PLUGIN_DIRS=(assets bin docs schema-pack skill systemd)
  for relative in "${PLUGIN_ROOT_FILES[@]}"; do
    if [ ! -f "$REPO/$relative" ] || [ -L "$REPO/$relative" ]; then
      echo "plugin snapshot source is not a regular file: $relative"
      exit 1
    fi
    cp -a -- "$REPO/$relative" "$SIA_PLUGIN_STAGE/"
  done
  for relative in "${PLUGIN_DIRS[@]}"; do
    if [ ! -d "$REPO/$relative" ] || [ -L "$REPO/$relative" ]; then
      echo "plugin snapshot source is not a real directory: $relative"
      exit 1
    fi
    cp -a -- "$REPO/$relative" "$SIA_PLUGIN_STAGE/"
  done
  find "$SIA_PLUGIN_STAGE" -type d -exec chmod 0755 {} +
  find "$SIA_PLUGIN_STAGE" -type f -exec chmod 0644 {} +
  chmod 0755 "$SIA_PLUGIN_STAGE/install.sh" \
    "$SIA_PLUGIN_STAGE/uninstall.sh" "$SIA_PLUGIN_STAGE/bin/sia" \
    "$SIA_PLUGIN_STAGE/bin/sia-brainstem" \
    "$SIA_PLUGIN_STAGE/bin/sia-ledger" "$SIA_PLUGIN_STAGE/bin/sia-mcp"
  find "$SIA_PLUGIN_STAGE" -type d -name __pycache__ -prune \
    -exec rm -rf -- {} +
  find "$SIA_PLUGIN_STAGE" -type f \
    \( -name '*.pyc' -o -name '*.pyo' -o -name '.DS_Store' \) -delete
  if find "$SIA_PLUGIN_STAGE" ! -type f ! -type d -print -quit | grep -q .; then
    echo "plugin snapshot refused: allowlisted source contains a special file"
    exit 1
  fi
  PLUGIN_RESULT="$(atomic_install_tree "$SIA_PLUGIN_STAGE" "$PLUGDIR" \
    "$PLUGIN_PARENT/.khephri.sia.previous.XXXXXX" \
    "$PLUGIN_TREE_EXPECTED")"
  IFS=$'\t' read -r _PLUGIN_INSTALLED_TREE PLUGIN_BACKUP \
    <<< "$PLUGIN_RESULT"
  SIA_PLUGIN_STAGE=""
  [ -z "$PLUGIN_BACKUP" ] || {
    echo "  previous plugin tree retained at $PLUGIN_BACKUP"
    echo "  (review and remove it manually after confirming the upgrade)"
  }
fi
plugin_id_is_discovered() {
  python3 -c '
import json
import sys
plugin_id = sys.argv[1]
try:
    plugins = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)
if not isinstance(plugins, list):
    raise SystemExit(1)
raise SystemExit(not any(
    isinstance(plugin, dict) and plugin.get("id") == plugin_id
    for plugin in plugins
))
' "$1"
}

rescan_and_verify_omarchy_plugin() {
  local plugin_id="$1" plugins discovered=0 attempt
  # This is the documented manual-install sequence and intentionally mirrors
  # omarchy-plugin-add's bounded discovery poll before enablement.
  run_with_deadline 120 omarchy-shell shell rescanPlugins >/dev/null
  for (( attempt = 0; attempt < 40; attempt++ )); do
    if plugins="$(bounded_command_capture omarchy plugin list --json)" \
        && plugin_id_is_discovered "$plugin_id" <<<"$plugins"; then
      discovered=1
      break
    fi
    sleep 0.05
  done
  (( discovered )) || {
    echo "plugin '$plugin_id' is not known after rescan; refusing enablement" >&2
    return 1
  }
}

binding_block_state() {
  owned_metadata binding-state "$1"
}

install_sia_keybinding() {
  local bindings="$1" state parent stage expected installed config_errors
  if [ -d "$(dirname "$bindings")" ]; then
    owned_file_cas recover "$bindings" || {
      echo "could not recover an interrupted Hyprland binding update" >&2
      return 1
    }
  fi
  if [ ! -e "$bindings" ] && [ ! -L "$bindings" ]; then
    echo "  optional SUPER+SHIFT+B not installed (bindings.lua is absent)"
    return 0
  fi
  if [ ! -f "$bindings" ] || [ -L "$bindings" ]; then
    if [ "${SIA_INSTALL_KEYBINDING:-0}" = "1" ]; then
      echo "refusing to alter unsafe Hyprland bindings path: $bindings" >&2
      return 1
    fi
    echo "  unsafe/symbolic Hyprland bindings path preserved; optional binding skipped"
    return 0
  fi
  if ! state="$(binding_block_state "$bindings")"; then
    echo "could not inspect existing Hyprland bindings" >&2
    return 1
  fi
  case "$state" in
    managed)
      echo "  existing complete SIA keybinding left unchanged"
      return 0
      ;;
    unsafe)
      echo "refusing to alter incomplete, duplicated, or malformed SIA keybinding markers" >&2
      echo "  preserved $bindings; repair the marker block manually" >&2
      return 1
      ;;
    absent) ;;
    *) echo "unexpected SIA keybinding inspection result" >&2; return 1 ;;
  esac
  if [ "${SIA_INSTALL_KEYBINDING:-0}" != "1" ]; then
    echo "  optional SUPER+SHIFT+B not installed (set"
    echo "  SIA_INSTALL_KEYBINDING=1 when running install.sh to consent;"
    echo "  it replaces the Browser binding, which remains on SUPER+SHIFT+RETURN)"
    return 0
  fi

  parent="$(dirname "$bindings")"
  stage="$(mktemp "$parent/.bindings.lua.sia-stage.XXXXXX")"
  expected="$(owned_metadata generation "$bindings")" || {
    rm -f -- "$stage"
    echo "Hyprland bindings changed before staging" >&2
    return 1
  }
  if ! cp -a -- "$bindings" "$stage" \
      || [ "$(binding_block_state "$stage")" != absent ] \
      || ! printf '%s\n' '' \
        '-- BEGIN SIA (managed by khephri.sia/install.sh)' \
        'hl.unbind("SUPER + SHIFT + B")   -- displaces Browser (still on SUPER+SHIFT+RETURN)' \
        'o.bind("SUPER + SHIFT + B", "SIA: brain cockpit", "omarchy-shell shell summon khephri.sia '\''{}'\''")' \
        '-- END SIA' >> "$stage"; then
    rm -f -- "$stage"
    echo "failed to assemble the managed SIA keybinding" >&2
    return 1
  fi
  if ! installed="$(owned_file_cas publish "$stage" "$bindings" \
      "$expected")"; then
    [ ! -e "$stage" ] \
      || echo "staged/prior binding retained at $stage" >&2
    echo "failed to publish the managed SIA keybinding atomically" >&2
    return 1
  fi

  if have hyprctl && [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]; then
    if ! run_with_deadline 120 hyprctl reload; then
      owned_file_cas publish "$stage" "$bindings" "$installed" \
          >/dev/null || {
        echo "failed to CAS-restore bindings after Hyprland reload failure; original retained at $stage" >&2
        return 1
      }
      rm -f -- "$stage"
      if ! run_with_deadline 120 hyprctl reload >/dev/null 2>&1; then
        echo "WARNING: original bindings restored but live reload still failed" >&2
      fi
      echo "Hyprland reload failed; restored the original bindings" >&2
      return 1
    fi
    if ! config_errors="$(bounded_command_capture hyprctl configerrors)" \
        || [ -n "$config_errors" ]; then
      printf '%s\n' "$config_errors" >&2
      owned_file_cas publish "$stage" "$bindings" "$installed" \
          >/dev/null || {
        echo "failed to CAS-restore bindings after Hyprland validation failure; original retained at $stage" >&2
        return 1
      }
      rm -f -- "$stage"
      if ! run_with_deadline 120 hyprctl reload >/dev/null 2>&1; then
        echo "WARNING: original bindings restored but live reload failed" >&2
      fi
      echo "Hyprland rejected the SIA binding; restored the original bindings" >&2
      return 1
    fi
  else
    echo "  no active Hyprland session; binding will load on the next session"
  fi
  rm -f -- "$stage"
  echo "  installed SUPER+SHIFT+B by explicit SIA_INSTALL_KEYBINDING=1 consent"
}

if have omarchy; then
  rescan_and_verify_omarchy_plugin khephri.sia
  run_with_deadline 120 omarchy plugin enable khephri.sia
  BINDINGS="$HOME/.config/hypr/bindings.lua"
  install_sia_keybinding "$BINDINGS"
else
  echo "  (omarchy shell not found — CLI + MCP still fully functional)"
fi

step "9/9 agents (skill + MCP, wherever you have harnesses)"
SKILL_DIR="$HOME/.claude/skills/sia"
SKILL_FILE="$SKILL_DIR/SKILL.md"
SKILL_MARKER="$SKILL_DIR/.sia-managed"
install_agent_skill() {
  local source_hash skill_expected marker_expected installed_skill current_skill
  local installed_marker skill_stage marker_stage rollback_archive
  local marker_rollback_archive owned_generations
  local retain_previous=0
  for candidate in "$HOME/.claude" "$HOME/.claude/skills" "$SKILL_DIR"; do
    if [ -L "$candidate" ]; then
      echo "  agent skill preserved: symbolic config path $candidate"
      echo "  configure manually from $SIA_ORIGINAL_REPO/skill/SKILL.md"
      return 0
    fi
  done
  mkdir -p "$SKILL_DIR"
  owned_file_cas recover "$SKILL_FILE" || {
    echo "  interrupted agent skill update could not be recovered" >&2
    return 1
  }
  owned_file_cas recover "$SKILL_MARKER" || {
    echo "  interrupted agent skill marker update could not be recovered" >&2
    return 1
  }
  if [ -e "$SKILL_FILE" ] || [ -L "$SKILL_FILE" ]; then
    if [ ! -f "$SKILL_FILE" ] || [ -L "$SKILL_FILE" ]; then
      echo "  existing agent skill preserved (not marked as SIA-managed)"
      echo "  configure manually from $SIA_ORIGINAL_REPO/skill/SKILL.md or explicitly replace:"
      echo "    SIA_REPLACE_AGENT_SKILL=1 ./install.sh"
      return 0
    fi
    if [ -f "$SKILL_MARKER" ] && [ ! -L "$SKILL_MARKER" ] \
        && owned_generations="$(owned_metadata skill-generations \
          "$SKILL_MARKER" "$SKILL_FILE")"; then
      IFS=$'\t' read -r skill_expected marker_expected \
        <<< "$owned_generations"
    elif [ "${SIA_REPLACE_AGENT_SKILL:-0}" = "1" ]; then
      retain_previous=1
      skill_expected="$(owned_metadata generation "$SKILL_FILE")" \
        || return 1
      if [ -e "$SKILL_MARKER" ] || [ -L "$SKILL_MARKER" ]; then
        if [ ! -f "$SKILL_MARKER" ] || [ -L "$SKILL_MARKER" ]; then
          echo "  unsafe agent skill marker preserved; replacement refused"
          return 1
        fi
        marker_expected="$(owned_metadata generation "$SKILL_MARKER")" \
          || return 1
      else
        marker_expected=absent
      fi
    else
      echo "  existing agent skill preserved (not marked as SIA-managed)"
      echo "  configure manually from $SIA_ORIGINAL_REPO/skill/SKILL.md or explicitly replace:"
      echo "    SIA_REPLACE_AGENT_SKILL=1 ./install.sh"
      return 0
    fi
  elif [ -e "$SKILL_MARKER" ] || [ -L "$SKILL_MARKER" ]; then
    echo "  stale or unsafe SIA skill marker preserved; skill not installed"
    echo "  inspect $SKILL_DIR and configure manually from $SIA_ORIGINAL_REPO/skill/SKILL.md"
    return 0
  else
    skill_expected=absent
    marker_expected=absent
  fi

  skill_stage="$(mktemp "$SKILL_DIR/.SKILL.md.previous.XXXXXX")"
  atomic_install_file "$REPO/skill/SKILL.md" "$skill_stage" 0644 \
    >/dev/null
  source_hash="$(owned_metadata digest "$skill_stage")" || return 1
  if ! installed_skill="$(owned_file_cas publish "$skill_stage" \
      "$SKILL_FILE" "$skill_expected")"; then
    [ ! -e "$skill_stage" ] \
      || echo "  staged/prior agent skill retained at $skill_stage" >&2
    echo "  agent skill changed concurrently; preserved"
    return 1
  fi
  marker_stage="$(mktemp "$SKILL_DIR/.sia-managed.previous.XXXXXX")"
  printf 'managed-by=khephri.sia\nskill_sha256=%s\n' "$source_hash" \
    > "$marker_stage"
  chmod 0600 "$marker_stage"
  current_skill="$(owned_metadata generation "$SKILL_FILE")" || true
  if [ "$current_skill" != "$installed_skill" ] \
      || ! installed_marker="$(owned_file_cas publish "$marker_stage" \
        "$SKILL_MARKER" "$marker_expected")"; then
    if [ "$skill_expected" = absent ]; then
      rollback_archive="$(mktemp "$SKILL_DIR/.SKILL.md.rollback.XXXXXX")"
      rm -f -- "$rollback_archive"
      if owned_file_cas archive "$rollback_archive" "$SKILL_FILE" \
          "$installed_skill"; then
        rm -f -- "$rollback_archive"
      fi
    else
      if owned_file_cas publish "$skill_stage" "$SKILL_FILE" \
          "$installed_skill" >/dev/null; then
        rm -f -- "$skill_stage"
      fi
    fi
    [ ! -e "$marker_stage" ] \
      || echo "  staged/prior agent marker retained at $marker_stage" >&2
    echo "  agent skill marker changed concurrently; replacement rolled back where safe" >&2
    return 1
  fi
  current_skill="$(owned_metadata generation "$SKILL_FILE")" || true
  if [ "$current_skill" != "$installed_skill" ]; then
    marker_rollback_archive="$(mktemp \
      "$SKILL_DIR/.sia-managed.rollback.XXXXXX")"
    rm -f -- "$marker_rollback_archive"
    if owned_file_cas archive "$marker_rollback_archive" "$SKILL_MARKER" \
        "$installed_marker"; then
      rm -f -- "$marker_rollback_archive"
    else
      echo "  exact newly published marker could not be retired; retained for inspection" >&2
    fi
    if [ "$skill_expected" = absent ]; then
      rollback_archive="$(mktemp "$SKILL_DIR/.SKILL.md.rollback.XXXXXX")"
      rm -f -- "$rollback_archive"
      if owned_file_cas archive "$rollback_archive" "$SKILL_FILE" \
          "$installed_skill"; then
        rm -f -- "$rollback_archive"
      fi
    elif owned_file_cas publish "$skill_stage" "$SKILL_FILE" \
        "$installed_skill" >/dev/null; then
      rm -f -- "$skill_stage"
    fi
    echo "  agent skill changed across marker publication; no concurrent skill was claimed" >&2
    return 1
  fi
  if [ "$retain_previous" -eq 1 ]; then
    [ ! -e "$skill_stage" ] \
      || echo "  existing agent skill retained at $skill_stage"
    [ ! -e "$marker_stage" ] \
      || echo "  existing agent marker retained at $marker_stage"
  else
    rm -f -- "$skill_stage" "$marker_stage"
  fi
  echo "  installed managed agent skill at $SKILL_FILE"
}
install_agent_skill

MCP_MARKER_DIR="$STATE/managed-mcp"
MCP_GUARD_DIR="$STATE/mcp-consumer-guards"
assert_safe_managed_roots "$MCP_MARKER_DIR" "$MCP_GUARD_DIR"
mkdir -p "$MCP_MARKER_DIR" "$MCP_GUARD_DIR"

# Commit transaction metadata through the shared journaled NOREPLACE front
# door.  Callers pass the exact absent/current generation they validated.
durable_replace_file() {
  owned_file_cas publish "$1" "$2" "$3" >/dev/null
}

write_mcp_marker() {
  local harness="$1" state="$2" marker marker_tmp before after expected
  mkdir -p "$MCP_MARKER_DIR" || return 1
  marker="$MCP_MARKER_DIR/$harness"
  before="$(mcp_marker_state "$harness")"
  case "$before" in
    none) expected=absent ;;
    legacy|pending|committed)
      expected="$(owned_metadata generation "$marker")" || return 1 ;;
    *) echo "invalid $harness MCP marker preserved" >&2; return 1 ;;
  esac
  after="$(mcp_marker_state "$harness")"
  [ "$before" = "$after" ] || return 1
  if [ "$expected" != absent ]; then
    [ "$(owned_metadata generation "$marker" 2>/dev/null || true)" \
      = "$expected" ] || return 1
  fi
  marker_tmp="$(mktemp "$MCP_MARKER_DIR/.${harness}.tmp.XXXXXX")" \
    || return 1
  if ! printf 'managed-by=khephri.sia\nstate=%s\ncommand=python3\narg=%s/sia-mcp\n' \
      "$state" "$BINDIR" > "$marker_tmp" \
      || ! chmod 0600 "$marker_tmp" \
      || ! durable_replace_file "$marker_tmp" \
        "$marker" "$expected"; then
    [ ! -e "$marker_tmp" ] \
      || echo "staged/prior MCP marker retained at $marker_tmp" >&2
    return 1
  fi
}

mcp_marker_state() {
  local harness="$1" marker state legacy pending committed
  marker="$MCP_MARKER_DIR/$harness"
  if [ ! -e "$marker" ] && [ ! -L "$marker" ]; then
    echo none
    return 0
  fi
  if [ ! -f "$marker" ] || [ -L "$marker" ]; then
    echo invalid
    return 0
  fi
  legacy="$(printf 'managed-by=khephri.sia\ncommand=python3\narg=%s/sia-mcp' \
    "$BINDIR")"
  pending="$(printf 'managed-by=khephri.sia\nstate=pending-add\ncommand=python3\narg=%s/sia-mcp' \
    "$BINDIR")"
  committed="$(printf 'managed-by=khephri.sia\nstate=committed\ncommand=python3\narg=%s/sia-mcp' \
    "$BINDIR")"
  if state="$(owned_metadata classify "$marker" \
      legacy "$legacy" pending "$pending" committed "$committed")"; then
    printf '%s\n' "$state"
  else
    echo invalid
  fi
}

mcp_consumer_guard_state() {
  local harness="$1" guard state prefix
  guard="$MCP_GUARD_DIR/$harness"
  if [ ! -e "$guard" ] && [ ! -L "$guard" ]; then
    echo none
    return 0
  fi
  if [ ! -f "$guard" ] || [ -L "$guard" ]; then
    echo invalid
    return 0
  fi
  prefix="$(printf 'guarded-by=khephri.sia\nkind=external-mcp-consumer\nconsumer=%s\nownership=external\ncommand=python3\narg=%s/sia-mcp\nreason=' \
    "$harness" "$BINDIR")"
  if state="$(owned_metadata classify "$guard" \
      guarded "${prefix}exact-unmarked" \
      guarded "${prefix}modified-reference")"; then
    printf '%s\n' "$state"
  else
    echo invalid
  fi
}

write_mcp_consumer_guard() {
  local harness="$1" reason="$2" state guard temporary expected after
  case "$harness" in claude|codex|grok) ;; *) return 1 ;; esac
  case "$reason" in exact-unmarked|modified-reference) ;; *) return 1 ;; esac
  state="$(mcp_consumer_guard_state "$harness")"
  [ "$state" != invalid ] || {
    echo "invalid $harness MCP non-ownership guard preserved" >&2
    return 1
  }
  guard="$MCP_GUARD_DIR/$harness"
  case "$state" in
    none) expected=absent ;;
    guarded) expected="$(owned_metadata generation "$guard")" || return 1 ;;
    *) return 1 ;;
  esac
  after="$(mcp_consumer_guard_state "$harness")"
  [ "$after" = "$state" ] || return 1
  if [ "$expected" != absent ]; then
    [ "$(owned_metadata generation "$guard" 2>/dev/null || true)" \
      = "$expected" ] || return 1
  fi
  temporary="$(mktemp "$MCP_GUARD_DIR/.${harness}.tmp.XXXXXX")"
  if ! printf 'guarded-by=khephri.sia\nkind=external-mcp-consumer\nconsumer=%s\nownership=external\ncommand=python3\narg=%s/sia-mcp\nreason=%s\n' \
      "$harness" "$BINDIR" "$reason" > "$temporary" \
      || ! chmod 0600 "$temporary" \
      || ! durable_replace_file "$temporary" "$guard" "$expected"; then
    [ ! -e "$temporary" ] \
      || echo "staged/prior MCP guard retained at $temporary" >&2
    return 1
  fi
}

guard_unowned_mcp_registration() {
  local harness="$1" reason="$2" marker_state="$3"
  write_mcp_consumer_guard "$harness" "$reason" || return 1
  case "$marker_state" in
    none) ;;
    committed|pending|legacy)
      # The guard is durable before stale ownership metadata is retired, so a
      # crash cannot expose an externally-owned registration to later removal.
      remove_mcp_marker_file "$harness" || {
        echo "could not retire stale $harness MCP ownership marker" >&2
        return 1
      }
      ;;
    invalid)
      echo "invalid $harness MCP ownership marker preserved behind its non-ownership guard" >&2
      return 1
      ;;
    *) return 1 ;;
  esac
}

parse_text_mcp_inspection() {
  python3 - "$1" "$2" "$3" <<'PY'
import re
import sys

client, path, text = sys.argv[1:]

def values(label):
    return re.findall(
        rf"(?mi)^[ \t]*{re.escape(label)}:[ \t]*(.*?)[ \t]*$", text)

def one(label):
    found = values(label)
    return found[0] if len(found) == 1 else None

exact = False
if client == "claude":
    known = {"scope", "status", "type", "command", "args", "environment"}
    indented = [match.group(1).casefold() for match in re.finditer(
        r"(?m)^[ \t]{2}([A-Za-z][A-Za-z ]*):", text)]
    fields_known = all(label in known for label in indented)
    environment_empty = False
    lines = text.splitlines()
    environment_rows = [index for index, line in enumerate(lines)
                        if re.fullmatch(r"[ \t]*Environment:[ \t]*", line,
                                        re.IGNORECASE)]
    if len(environment_rows) == 1:
        tail = lines[environment_rows[0] + 1:]
        before_blank = []
        for line in tail:
            if not line.strip():
                break
            before_blank.append(line)
        environment_empty = not before_blank
    scope = one("scope")
    status = one("status")
    exact = (
        fields_known and environment_empty
        and scope is not None
        and re.fullmatch(r"User config(?: \(available in all your projects\))?",
                         scope) is not None
        and status is not None
        and one("type") == "stdio"
        and one("command") == "python3"
        and one("args") == path
        and one("environment") == ""
    )
elif client == "codex":
    known = {"enabled", "transport", "command", "args", "cwd", "env",
             "remove"}
    indented = [match.group(1).casefold() for match in re.finditer(
        r"(?m)^[ \t]{2}([A-Za-z][A-Za-z ]*):", text)]
    remove = values("remove")
    exact = (
        all(label in known for label in indented)
        and one("enabled") == "true"
        and one("transport") == "stdio"
        and one("command") == "python3"
        and one("args") == path
        and one("cwd") == "-"
        and one("env") == "-"
        and (not remove or remove == ["codex mcp remove sia"])
    )

print("match" if exact else "reference" if path in text else "mismatch")
PY
}

inspect_mcp_server() {
  local harness="$1" inspection
  case "$harness" in
    claude|codex)
      if inspection="$(bounded_command_capture \
          "$harness" mcp get sia)"; then
        parse_text_mcp_inspection "$harness" "$BINDIR/sia-mcp" \
          "$inspection"
      elif [[ "$inspection" == *"No MCP server named"* ]]; then
        echo absent
      else
        printf '%s\n' "$inspection" >&2
        echo indeterminate
      fi
      ;;
    grok)
      if ! inspection="$(bounded_command_capture \
          grok mcp list --json)"; then
        printf '%s\n' "$inspection" >&2
        echo indeterminate
      elif ! printf '%s' "$inspection" | python3 -c \
        'import json,sys; xs=json.load(sys.stdin); assert isinstance(xs,list)' \
        >/dev/null 2>&1; then
        echo indeterminate
      else
        printf '%s' "$inspection" | python3 -c \
          'import json,sys; p=sys.argv[1]; xs=[x for x in json.load(sys.stdin) if isinstance(x,dict) and x.get("name")=="sia"]; allowed={"name","command","args","enabled","scope","transport","env","cwd"}; exact=len(xs)==1 and set(xs[0])<=allowed and xs[0].get("command")=="python3" and xs[0].get("args")==[p] and not xs[0].get("env") and not xs[0].get("cwd") and xs[0].get("transport","stdio")=="stdio" and xs[0].get("enabled") is True and xs[0].get("scope")=="user"; print("absent" if not xs else "match" if exact else "reference" if p in json.dumps(xs,sort_keys=True) else "mismatch")' \
          "$BINDIR/sia-mcp"
      fi
      ;;
  esac
}

print_mcp_add_command() {
  case "$1" in
    claude) echo "  claude mcp add --scope user sia -- python3 $BINDIR/sia-mcp" ;;
    codex) echo "  codex mcp add sia -- python3 $BINDIR/sia-mcp" ;;
    grok) echo "  grok mcp add --scope user sia -- python3 $BINDIR/sia-mcp" ;;
  esac
}

remove_mcp_marker_file() {
  local harness="$1" marker="$MCP_MARKER_DIR/$1" state expected archive
  state="$(mcp_marker_state "$harness")"
  case "$state" in legacy|pending|committed) ;; *) return 1 ;; esac
  expected="$(owned_metadata generation "$marker")" || return 1
  [ "$(mcp_marker_state "$harness")" = "$state" ] || return 1
  [ "$(owned_metadata generation "$marker" 2>/dev/null || true)" \
    = "$expected" ] || return 1
  archive="$(mktemp "$MCP_MARKER_DIR/.${harness}.removed.XXXXXX")" \
    || return 1
  rm -f -- "$archive"
  owned_file_cas archive "$archive" "$marker" "$expected" || return 1
  rm -f -- "$archive"
}

register_mcp_server() {
  local harness="$1" state marker_state guard_state
  marker_state="$(mcp_marker_state "$harness")"
  guard_state="$(mcp_consumer_guard_state "$harness")"
  case "$guard_state" in
    guarded)
      echo "  durable non-ownership guard preserves the external $harness MCP consumer"
      return 0
      ;;
    invalid)
      echo "invalid $harness MCP non-ownership guard; refusing registration changes" >&2
      return 1
      ;;
    none) ;;
    *) echo "unexpected $harness MCP guard state" >&2; return 1 ;;
  esac
  if ! have "$harness"; then
    case "$marker_state" in
      none)
        echo "  $harness not installed; MCP registration skipped"
        return 0
        ;;
      committed|legacy)
        echo "  $harness unavailable; owned MCP marker preserved"
        return 0
        ;;
      *)
        echo "$harness unavailable with unresolved/invalid MCP transaction marker" >&2
        return 1
        ;;
    esac
  fi
  state="$(inspect_mcp_server "$harness")"
  case "$state" in
    match)
      case "$marker_state" in
        committed|pending|legacy)
          write_mcp_marker "$harness" committed
          echo "  exact owned $harness MCP registration recovered"
          return 0
          ;;
        none)
          guard_unowned_mcp_registration "$harness" exact-unmarked \
            "$marker_state" || return 1
          echo "  exact unmarked $harness MCP registration is user-owned; preserved"
          return 0
          ;;
        *)
          echo "exact $harness MCP registration has an invalid ownership marker; preserved" >&2
          return 1
          ;;
      esac
      ;;
    reference)
      case "$marker_state" in
        none)
          guard_unowned_mcp_registration "$harness" modified-reference \
            "$marker_state" || return 1
          echo "  modified $harness MCP registration references SIA and is externally owned; guarded and preserved"
          return 0
          ;;
        pending|committed|legacy)
          # A reference is not proof that ownership changed: it can also mean
          # the harness added a display field or otherwise changed its output
          # format.  Keep installer-owned transaction metadata authoritative.
          # In particular, never turn our own pending add into a durable
          # external-consumer guard on the next installer run.
          echo "$harness MCP registration references SIA but no longer verifies exactly; owned marker retained" >&2
          echo "inspect the harness configuration and resolve the ownership ambiguity before retrying" >&2
          return 1
          ;;
        invalid)
          echo "invalid $harness MCP ownership marker preserved beside a non-exact SIA reference" >&2
          return 1
          ;;
        *) echo "unexpected $harness MCP marker state" >&2; return 1 ;;
      esac
      ;;
    mismatch)
      echo "  existing $harness MCP registration differs from SIA; preserved"
      [ "$marker_state" = none ] || {
        echo "  ownership marker also exists; inspect this divergence manually" >&2
        return 1
      }
      return 0
      ;;
    indeterminate)
      echo "could not inspect $harness MCP configuration" >&2
      return 1
      ;;
    absent)
      case "$marker_state" in
        none)
          echo "  $harness MCP registration is absent; no compare-and-add API is available"
          echo "  add it manually after install if desired:"
          print_mcp_add_command "$harness"
          return 0
          ;;
        pending|committed|legacy)
          echo "$harness MCP registration is absent but owned metadata remains; preserved for manual resolution" >&2
          return 1
          ;;
        invalid)
          echo "invalid $harness MCP ownership marker; preserved" >&2
          return 1
          ;;
        *) return 1 ;;
      esac
      ;;
    *) echo "unexpected $harness MCP inspection state" >&2; return 1 ;;
  esac
}
register_mcp_server claude
register_mcp_server codex
register_mcp_server grok
echo "  external MCP clients can preserve the CLI/runtime by placing a guard file in:"
echo "    $MCP_GUARD_DIR"

# When the live Omarchy plugin checkout was itself the source, it remains the
# UI generation rather than being replaced by the temporary snapshot.  Refuse
# final activation if a concurrent plugin update made that UI diverge from the
# release bytes used for the runtime.
# Re-observe both model names and every referenced blob at the activation
# boundary, with the manifest generation held equal across each verification.
# This is not coordination with independent Ollama writers: a write after this
# final observation remains outside the installer's transaction.
for final_manifest in "$NOMIC_MANIFEST" "$NOMIC_ALIAS_MANIFEST"; do
  final_before="$(model_manifest_generation "$final_manifest")" \
    || { echo "unsafe final model manifest generation" >&2; exit 1; }
  [ "$final_before" != absent ] \
    || { echo "final model manifest disappeared" >&2; exit 1; }
  verify_ollama_model_store "$OLLAMA_MODELS_DIR" "$final_manifest" \
    "$NOMIC_MANIFEST_SHA256"
  final_after="$(model_manifest_generation "$final_manifest")" \
    || { echo "unsafe final model manifest generation" >&2; exit 1; }
  [ "$final_before" = "$final_after" ] \
    || { echo "model manifest changed during final verification" >&2; exit 1; }
done

if [ "$SIA_ORIGINAL_REPO" = "$PLUGDIR" ]; then
  release_source_frontdoor verify "$SIA_ORIGINAL_REPO" \
    "$SIA_RELEASE_SOURCE" "${SIA_RELEASE_FILES[@]}"
fi

if [ "$SIA_RESTORE_LIFECYCLE_TOMBSTONE" -eq 1 ]; then
  # All replacement artifacts now exist. Arm EXIT restoration before the
  # unlink so even a post-unlink fsync failure stays fail-closed.
  SIA_LIFECYCLE_TOMBSTONE_CLEARED=1
  clear_lifecycle_tombstone
  # The complete replacement generation is now public. A later service-start
  # failure must not retombstone valid installed bytes after this lease ends.
  SIA_LIFECYCLE_TOMBSTONE_CLEARED=0
  SIA_RESTORE_LIFECYCLE_TOMBSTONE=0
fi
flock -u "$SIA_BRAINSTEM_LOCK_FD"
exec {SIA_BRAINSTEM_LOCK_FD}>&-
SIA_BRAINSTEM_LOCK_FD=""
# The replacement generation, durable debt, public integrations, and (for a
# purged reinstall) tombstone clear are complete. Release the generation gate
# before synchronous systemd operations so a start job already waiting on the
# lease can finish instead of deadlocking the installer.
flock -u "$SIA_INSTALL_LOCK_FD"
exec {SIA_INSTALL_LOCK_FD}>&-
SIA_INSTALL_LOCK_FD=""
retire_install_brainstem_runtime_barrier
run_with_deadline 120 systemctl --user enable sia-brainstem.service
run_with_deadline 120 systemctl --user start sia-brainstem.service
inspect_user_unit sia-brainstem.service BRAINSTEM_LIVE || {
  echo "sia-brainstem.service state could not be verified" >&2
  exit 1
}
if [ "$BRAINSTEM_LIVE_LOAD_STATE" != loaded ] \
    || [ "$BRAINSTEM_LIVE_ACTIVE_STATE" != active ] \
    || [ "$BRAINSTEM_LIVE_FRAGMENT_PATH" != "$BRAINSTEM_UNIT" ] \
    || [ "$BRAINSTEM_LIVE_MAIN_PID" = 0 ]; then
  echo "sia-brainstem.service did not reach active state" >&2
  exit 1
fi
python3 - "$BRAINSTEM_LIVE_MAIN_PID" "$BINDIR/sia-brainstem.py" <<'PY'
import os
import sys

pid, runtime = sys.argv[1:]
actual_executable = os.path.realpath(f"/proc/{pid}/exe")
expected_executable = os.path.realpath("/usr/bin/python3")
with open(f"/proc/{pid}/cmdline", "rb") as stream:
    argv = [part.decode("utf-8", "strict")
            for part in stream.read().rstrip(b"\0").split(b"\0")]
if (actual_executable != expected_executable
        or len(argv) != 2
        or os.path.realpath(argv[0]) != expected_executable
        or os.path.realpath(argv[1]) != os.path.realpath(runtime)):
    raise SystemExit("sia-brainstem.service is not running the exact managed runtime")
PY
discard_install_brainstem_retired_barrier
echo "  brainstem: active (verified executable and argv)"

step "done — your machine has a brain"
cat <<'EOF'
  cockpit    click the bar widget (optional consented key: SUPER+SHIFT+B)
  ask it     sia ask "what happened today"
  thoughts   sia think          status   sia status
  predict    sia take "..." --confidence 0.8 --by YYYY-MM-DD
  configure  ~/.config/sia/config.json   (judge model, custom senses, chains)
  docs       docs/MANUAL.md · docs/WHITEPAPER.md

  It dreams at 03:33: consolidation, musing, grading. Storage, indexing, and
  embeddings stay local; the optional configured CLI judge may send recalled
  context. The corpus (~/.local/share/sia/corpus) IS the brain — back it up.
EOF
