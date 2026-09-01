#!/usr/bin/env bash
# SIA uninstaller — removes daemon, plugin, CLI, MCP registrations, and
# installed runtime code. Without --purge, corpus, ledgers, keys, queues,
# state snapshots, and operator configuration are retained.

set -uo pipefail

case "${HOME:-}" in
  ""|/) echo "refusing uninstall with an unsafe HOME" >&2; exit 2 ;;
  /*) ;;
  *) echo "refusing uninstall with a non-absolute HOME" >&2; exit 2 ;;
esac
case "$HOME" in
  *$'\n'*|*$'\r'*) echo "refusing uninstall with line breaks in HOME" >&2; exit 2 ;;
esac
SIA_CANONICAL_HOME="$(cd -P -- "$HOME" 2>/dev/null && pwd)" || {
  echo "refusing uninstall because HOME is not an accessible directory" >&2
  exit 2
}
[ "$SIA_CANONICAL_HOME" != "/" ] || {
  echo "refusing uninstall because HOME resolves to /" >&2
  exit 2
}
HOME="$SIA_CANONICAL_HOME"
export HOME
unset SIA_INHERITED_LIFECYCLE_FD SIA_INHERITED_CORPUS_FD \
  SIA_LAUNCHER_ABI SIA_LAUNCHER_LIFECYCLE_FD \
  SIA_LAUNCHER_TARGET_FD SIA_LAUNCHER_TARGET_PATH \
  SIA_RESTORE_LAUNCH_ABI SIA_RESTORE_LIFECYCLE_FD \
  SIA_RESTORE_ADMIN_FD SIA_RESTORE_TARGET_FD \
  SIA_RESTORE_TARGET_PATH SIA_RESTORE_MASK_OWNED \
  SIA_RESTORE_FINALIZE_ABI SIA_RESTORE_FINALIZE_ADMIN_FD
case "${XDG_RUNTIME_DIR:-}" in
  /*) ;;
  *) echo "refusing uninstall with an unsafe XDG_RUNTIME_DIR" >&2; exit 2 ;;
esac
case "$XDG_RUNTIME_DIR" in
  *$'\n'*|*$'\r'*|*[[:space:]\\]*)
    echo "refusing uninstall with an unsafe XDG_RUNTIME_DIR" >&2
    exit 2
    ;;
esac
case "${1:-}" in
  "") PURGE=0 ;;
  --purge) PURGE=1 ;;
  *) echo "usage: ./uninstall.sh [--purge]" >&2; exit 2 ;;
esac

SHARE_DIR="$HOME/.local/share/sia"
RUNTIME_BIN_DIR="$SHARE_DIR/bin"
STATE_DIR="$HOME/.local/state/sia"
CONTINUITY_STATE_DIR="$HOME/.local/state/sia-continuity"
RESTORE_BARRIER="$CONTINUITY_STATE_DIR/restore-in-progress.json"
RESTORE_MASK_DEBT="$CONTINUITY_STATE_DIR/restore-runtime-mask"
RESTORE_SUPERVISOR_DEBT="$CONTINUITY_STATE_DIR/restore-supervisor.json"
SHARE_PUBLICATION_STAGE="$HOME/.local/share/.sia.sia-stage"
STATE_PUBLICATION_STAGE="$HOME/.local/state/.sia.sia-stage"
LIFECYCLE_LOCK="$HOME/.local/state/sia.lifecycle.lock"
LIFECYCLE_ADMIN_LOCK="$HOME/.local/state/sia.lifecycle-admin.lock"
LIFECYCLE_TOMBSTONE="$HOME/.local/state/sia.lifecycle-removed"
MCP_MARKER_DIR="$STATE_DIR/managed-mcp"
MCP_GUARD_DIR="$STATE_DIR/mcp-consumer-guards"
MANAGED_DIR="$STATE_DIR/managed-install"
CONFIG_DIR="$HOME/.config/sia"
CLI_PATH="$HOME/.local/bin/sia"
UNIT_PATH="$HOME/.config/systemd/user/sia-brainstem.service"
UNIT_RECEIPT="$MANAGED_DIR/sia-brainstem.service"
CONTINUITY_UNIT_NAMES=(
  sia-backup.timer
  sia-backup-check.timer
  sia-backup.service
  sia-backup-check.service
)
CONTINUITY_UNIT_PATHS=(
  "$HOME/.config/systemd/user/sia-backup.timer"
  "$HOME/.config/systemd/user/sia-backup-check.timer"
  "$HOME/.config/systemd/user/sia-backup.service"
  "$HOME/.config/systemd/user/sia-backup-check.service"
)
CONTINUITY_UNIT_RECEIPTS=(
  "$MANAGED_DIR/sia-backup.timer"
  "$MANAGED_DIR/sia-backup-check.timer"
  "$MANAGED_DIR/sia-backup.service"
  "$MANAGED_DIR/sia-backup-check.service"
)
CONTINUITY_UNIT_KINDS=(
  backup-timer
  backup-check-timer
  backup-unit
  backup-check-unit
)
BRAINSTEM_RUNTIME_BARRIER="$XDG_RUNTIME_DIR/systemd/user/sia-brainstem.service.d/sia-lifecycle-barrier.conf"
CLI_RECEIPT="$MANAGED_DIR/sia-cli"
RUNTIME_RECEIPT="$MANAGED_DIR/runtime"
GBRAIN_PIN_PATH="$SHARE_DIR/GBRAIN_PIN"
GBRAIN_PIN_RECEIPT="$MANAGED_DIR/gbrain-pin"
LAUNCH_FENCE_JOURNAL="$MANAGED_DIR/launch-fence.json"
SKILL_DIR="$HOME/.claude/skills/sia"
SKILL_FILE="$SKILL_DIR/SKILL.md"
SKILL_MARKER="$SKILL_DIR/.sia-managed"
PLUGIN_DIR="$HOME/.config/omarchy/plugins/khephri.sia"
BINDINGS_PATH="$HOME/.config/hypr/bindings.lua"
FAILURES=()
BRAINSTEM_SAFE_TO_REMOVE=1
RUNTIME_NEEDED_BY_MCP=0
RUNTIME_NEEDED_BY_PLUGIN=0
RUNTIME_NEEDED_BY_SERVICE=0
RUNTIME_NEEDED_BY_CONTINUITY=0
RUNTIME_NEEDED_BY_CLI=0
RUNTIME_UNOWNED=0
PLUGIN_SAFE_TO_ARCHIVE=1
PLUGIN_EXPECTED=""
UNIT_OWNED=0
UNIT_TARGET_EXPECTED=""
UNIT_RECEIPT_EXPECTED=""
CONTINUITY_SAFE_TO_REMOVE=1
CONTINUITY_ARCHIVE_NEEDED=0
declare -a CONTINUITY_UNIT_STATES
declare -a CONTINUITY_TARGET_EXPECTED
declare -a CONTINUITY_RECEIPT_EXPECTED
SIA_UNINSTALL_LOCK_FD=""
SIA_UNINSTALL_ADMIN_LOCK_FD=""
SIA_LIFECYCLE_ACQUIRE_ATTEMPTS=8
SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED=0
SIA_BRAINSTEM_RETIRED_BARRIER_PRESENT=0
SIA_LAUNCH_FENCE_ARMED=0
# Assigned by name with printf -v and read later through indirect expansion.
# shellcheck disable=SC2034
SIA_BRAINSTEM_LOCK_FD=""
# shellcheck disable=SC2034
SIA_CORPUS_LOCK_FD=""
# shellcheck disable=SC2034
SIA_GBRAIN_LOCK_FD=""

sia_uninstall_cleanup() {
  local status=$? lock_variable lock_descriptor barrier_state
  trap - EXIT
  set +e
  for lock_variable in SIA_GBRAIN_LOCK_FD SIA_CORPUS_LOCK_FD \
      SIA_BRAINSTEM_LOCK_FD; do
    lock_descriptor="${!lock_variable}"
    if [ -n "$lock_descriptor" ]; then
      flock -u "$lock_descriptor" >/dev/null 2>&1 || true
      eval "exec ${lock_descriptor}>&-"
      printf -v "$lock_variable" '%s' ""
    fi
  done
  if [ -n "$SIA_UNINSTALL_LOCK_FD" ]; then
    flock -u "$SIA_UNINSTALL_LOCK_FD" >/dev/null 2>&1 || true
    eval "exec ${SIA_UNINSTALL_LOCK_FD}>&-"
    SIA_UNINSTALL_LOCK_FD=""
  fi
  if [ "$SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED" -eq 1 ] \
      || [ "$SIA_BRAINSTEM_RETIRED_BARRIER_PRESENT" -eq 1 ]; then
    barrier_state="$(brainstem_runtime_barrier_file state 2>/dev/null || true)"
    case "$barrier_state" in
      active)
        echo "sia-brainstem.service retains its exact runtime start barrier; resolve the uninstall failure and rerun uninstall.sh" >&2
        ;;
      retired)
        echo "sia-brainstem.service retains an exact retired barrier recovery copy; rerun uninstall.sh" >&2
        ;;
      *)
        echo "WARNING: uninstall could not attest a retained sia-brainstem start barrier" >&2
        ;;
    esac
  fi
  exit "$status"
}
trap sia_uninstall_cleanup EXIT

have() { command -v "$1" >/dev/null 2>&1; }

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
if hasattr(os, "pidfd_open"):
    try:
        pidfd = os.pidfd_open(process.pid, 0)
    except OSError:
        pidfd = None
if pidfd is not None:
    selector.register(pidfd, selectors.EVENT_READ, "leader")


def leader_exited():
    # A registered pidfd is itself the non-reaping exit notification. Avoid a
    # second waitid(P_PIDFD) syscall; the selector branch below observes it.
    if pidfd is not None:
        return False
    result = os.waitid(
        os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
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
if hasattr(os, "pidfd_open"):
    try:
        pidfd = os.pidfd_open(process.pid, 0)
    except OSError:
        pidfd = None
selector = selectors.DefaultSelector()
if pidfd is not None:
    selector.register(pidfd, selectors.EVENT_READ)


def leader_exited():
    if pidfd is not None:
        return bool(selector.select(0))
    result = os.waitid(
        os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
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
    # Polling a pidfd never reaps; the fallback WNOWAIT check also preserves
    # the leader's PID/PGID until every descendant has received SIGKILL.
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

# Byte-exact lifecycle authority verifier.  It keeps receipt/marker bytes out
# of Bash, rejects links/non-owned/nonregular/oversized/unstable files, and
# streams target digests through one generation-bound no-follow descriptor.
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


def inspect_managed_receipt(receipt, kind, target):
    content, value = inspect_metadata(receipt)
    prefix = (f"managed-by=khephri.sia\nkind={kind}\npath={target}\n"
              "sha256=").encode("utf-8")
    if not content.startswith(prefix) or not content.endswith(b"\n"):
        raise ValueError("managed receipt has an invalid shape")
    digest = content[len(prefix):-1]
    if re.fullmatch(rb"[0-9a-f]{64}", digest) is None:
        raise ValueError("managed receipt has an invalid digest")
    receipt_digest = hashlib.sha256(content).hexdigest()
    return (digest.decode("ascii"),
            token_from_inspection(value, receipt_digest))


def managed_receipt_generation(receipt, kind, target):
    _digest, receipt_token = inspect_managed_receipt(receipt, kind, target)
    print(receipt_token)
    return True


def managed_receipt_fields(receipt, kind, target):
    digest, receipt_token = inspect_managed_receipt(receipt, kind, target)
    print(digest + "\t" + receipt_token)
    return True


def fenced_generation_token(path, digest):
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("invalid launch-fence digest")
    flags = (getattr(os, "O_PATH", os.O_RDONLY)
             | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        current = current_generation(path)
        after = os.fstat(descriptor)
        if stat.S_IMODE(before.st_mode) != 0 \
                or generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise ValueError("launch-fenced file changed while inspected")
    finally:
        os.close(descriptor)
    print(token_from_inspection(before, digest))
    return True


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
    elif mode == "managed-file":
        accepted = exact_managed_file(*arguments)
    elif mode == "managed-receipt-generation":
        accepted = managed_receipt_generation(*arguments)
    elif mode == "managed-receipt-fields":
        accepted = managed_receipt_fields(*arguments)
    elif mode == "fenced-generation":
        accepted = fenced_generation_token(*arguments)
    elif mode == "runtime":
        accepted = exact_runtime_receipt(*arguments)
    elif mode == "runtime-digest":
        accepted = runtime_digest_field(*arguments)
    elif mode == "skill":
        accepted = exact_skill_marker(*arguments)
    elif mode == "skill-generations":
        accepted = exact_skill_generations(*arguments)
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


def token(name, allow_absent=False, trusted_digest=None):
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
        readable = True
    except PermissionError:
        if trusted_digest is None:
            raise
        descriptor = os.open(
            name, getattr(os, "O_PATH", os.O_RDONLY)
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd)
        readable = False
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
        if readable:
            while True:
                chunk = os.read(descriptor, CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    raise ValueError("oversized CAS file")
                digest.update(chunk)
        else:
            if stat.S_IMODE(before.st_mode) != 0:
                raise ValueError("unreadable CAS file is not launch-fenced")
            total = before.st_size
        after = os.fstat(descriptor)
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if total != before.st_size \
                or generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise ValueError("CAS file changed while inspected")
    finally:
        os.close(descriptor)
    observed_digest = digest.hexdigest() if readable else trusted_digest
    fields = (*generation(before), observed_digest)
    return "present:" + ":".join(str(value) for value in fields)


def prior_digest(prior):
    match = token_pattern.fullmatch(prior)
    return None if match is None else match.group(8)


def prior_token(name, prior, allow_absent=False):
    return token(name, allow_absent=allow_absent,
                 trusted_digest=prior_digest(prior))


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
    current = prior_token(target_name, prior, allow_absent=True)
    archived = prior_token(archive, prior, allow_absent=True)
    staged_current = prior_token(prior_stage, prior, allow_absent=True)
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
    current = prior_token(target_name, expected, allow_absent=True)
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
            archived = prior_token(archive_name, expected)
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
            if not moved_token_matches(prior_token(staged_name, expected), expected) \
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
        if not moved_token_matches(prior_token(archive_name, expected), expected):
            try:
                rename_noreplace(archive_name, target_name)
                sync_parent()
            except OSError:
                retained(record, "CAS archival preserved a newer target")
            clear_journal()
            raise SystemExit("CAS archived generation did not match preflight")
        if prior_token(target_name, expected, allow_absent=True) != "absent":
            retained(record, "CAS archival preserved a concurrent target")
            clear_journal()
            raise SystemExit("CAS target changed during archival")
        rename_noreplace(archive_name, staged_name)
        sync_parent()
        archived_token = prior_token(staged_name, expected)
        if not moved_token_matches(archived_token, expected) \
                or prior_token(target_name, expected,
                               allow_absent=True) != "absent":
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
        print(archived_token)
    else:
        raise SystemExit("unknown CAS operation")
finally:
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    os.close(lock_fd)
    os.close(parent_fd)
PY
}

# Descriptor-rooted, generation-bound archival for managed directory trees.
# MAX_ENTRIES is status=exact parsed=2^17 exact=131072 (JACKAL rat lane;
# non-formal, outside the Lean certificate chain). The ceiling bounds every
# traversal, and the durable journal makes a temporary canonical-path absence
# recoverable without ever overwriting an independently published tree.
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
    backup = expected = None
elif operation == "archive" and len(arguments) == 4:
    _, target, backup, expected = arguments
    target, backup = map(os.path.abspath, (target, backup))
else:
    raise SystemExit("invalid tree CAS arguments")
parent = os.path.dirname(target)
if os.path.realpath(parent) != parent:
    raise SystemExit("tree CAS parent must not traverse symbolic links")
target_name = os.path.basename(target)
if backup is not None:
    if os.path.dirname(backup) != parent or backup == target:
        raise SystemExit("tree CAS paths must be distinct siblings")
    backup_name = os.path.basename(backup)
else:
    backup_name = None
token_pattern = re.compile(
    r"tree:(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):([0-9a-f]{64})")
if expected is not None and token_pattern.fullmatch(expected) is None:
    raise SystemExit("invalid expected tree generation")
directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                   | getattr(os, "O_DIRECTORY", 0)
                   | getattr(os, "O_NOFOLLOW", 0))
path_flags = (getattr(os, "O_PATH", os.O_RDONLY)
              | getattr(os, "O_CLOEXEC", 0)
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


def tree_token(name, allow_absent=False):
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
                child_fd = os.open(child, directory_flags, dir_fd=descriptor)
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
                child_fd = os.open(child, path_flags, dir_fd=descriptor)
                try:
                    opened = os.fstat(child_fd)
                    current_child = os.stat(
                        child, dir_fd=descriptor, follow_symlinks=False)
                    if not stat.S_ISREG(opened.st_mode) \
                            or opened.st_uid != os.geteuid() \
                            or generation(opened) != generation(observed) \
                            or generation(opened) != generation(current_child):
                        raise ValueError("tree file changed while inspected")
                    update_record(digest, b"F", child_relative, opened)
                finally:
                    os.close(child_fd)
            else:
                raise ValueError("tree contains a symbolic or special entry")
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
                       parent_fd, os.fsencode(destination), RENAME_NOREPLACE)
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
    descriptor = os.open(journal_name, os.O_RDONLY
                         | getattr(os, "O_CLOEXEC", 0)
                         | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
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
    required = {"version", "target", "backup", "archive", "expected"}
    if not isinstance(record, dict) or set(record) != required \
            or record["version"] != 1 or record["target"] != target_name:
        raise ValueError("invalid tree CAS journal")
    for key in ("target", "backup", "archive"):
        value = record[key]
        if not isinstance(value, str) or not value \
                or os.path.basename(value) != value:
            raise ValueError("invalid tree CAS journal path")
    if token_pattern.fullmatch(record["expected"]) is None:
        raise ValueError("invalid tree CAS journal token")
    return record


def write_journal(record):
    payload = (json.dumps(record, sort_keys=True,
                          separators=(",", ":")) + "\n").encode()
    if len(payload) > MAX_JOURNAL_BYTES:
        raise ValueError("oversized tree CAS journal payload")
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
    for key in ("archive", "backup"):
        if child_exists(record[key]):
            print(f"{reason}; managed tree retained at "
                  f"{os.path.join(parent, record[key])}", file=sys.stderr)
            return


def recover_journal():
    if not child_exists(journal_name):
        return
    record = read_journal()
    current = tree_token(target_name, allow_absent=True)
    archived = tree_token(record["archive"], allow_absent=True)
    saved = tree_token(record["backup"], allow_absent=True)
    prior = record["expected"]
    if moved_matches(saved, prior):
        if current != "absent":
            print("tree CAS recovery preserved an independent canonical tree",
                  file=sys.stderr)
        clear_journal()
        return
    if current == prior and archived == "absent" and saved == "absent":
        clear_journal()
        return
    if moved_matches(archived, prior) and saved == "absent":
        try:
            rename_noreplace(record["archive"], record["backup"])
            sync_parent()
        except OSError:
            retained(record, "tree CAS recovery could not finish archival")
            raise SystemExit("tree CAS recovery retained an incomplete journal")
        if not moved_matches(tree_token(record["backup"]), prior):
            retained(record, "tree CAS recovery found a changed archive")
            raise SystemExit("tree CAS recovery retained an incomplete journal")
        if tree_token(target_name, allow_absent=True) != "absent":
            print("tree CAS recovery preserved an independent canonical tree",
                  file=sys.stderr)
        clear_journal()
        return
    retained(record, "tree CAS recovery found an ambiguous transaction")
    raise SystemExit("tree CAS recovery retained an ambiguous journal")


try:
    recover_journal()
    if operation == "recover":
        raise SystemExit(0)
    if child_exists(backup_name):
        raise SystemExit("tree CAS backup path is occupied")
    current = tree_token(target_name, allow_absent=True)
    if current != expected:
        raise SystemExit("tree CAS target changed before archival")
    archive = unique_name(".sia-tree-cas-prior.")
    record = {"version": 1, "target": target_name,
              "backup": backup_name, "archive": archive,
              "expected": expected}
    write_journal(record)
    rename_noreplace(target_name, archive)
    sync_parent()
    if not moved_matches(tree_token(archive), expected):
        try:
            rename_noreplace(archive, target_name)
            sync_parent()
        except OSError:
            retained(record, "tree CAS refused to overwrite a newer target")
        raise SystemExit("archived tree did not match preflight")
    rename_noreplace(archive, backup_name)
    sync_parent()
    archived_token = tree_token(backup_name)
    if not moved_matches(archived_token, expected):
        retained(record, "tree CAS archive changed at publication boundary")
        raise SystemExit("tree CAS archive changed at publication boundary")
    if tree_token(target_name, allow_absent=True) != "absent":
        retained(record, "tree CAS preserved an independent canonical tree")
        clear_journal()
        raise SystemExit("tree CAS target changed during archival")
    clear_journal()
    print(archived_token)
finally:
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    os.close(lock_fd)
    os.close(parent_fd)
PY
}

owned_tree_generation() {
  owned_tree_cas generation "$1"
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
write_managed_receipt() {
  local receipt="$1" kind="$2" target="$3" digest="$4"
  local output_variable="${5:-}" expected stage installed
  [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || return 1
  mkdir -p "$MANAGED_DIR" || return 1
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
failed() {
  FAILURES+=("$1")
  printf 'failed: %s\n' "$1" >&2
}
attempt() {
  local label="$1"
  shift
  "$@" || failed "$label"
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
    current = home
    for component in os.path.relpath(target, home).split(os.sep):
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
managed_receipt_matches() {
  local receipt="$1" kind="$2" target="$3"
  [ -f "$target" ] && [ ! -L "$target" ] \
    && [ -f "$receipt" ] && [ ! -L "$receipt" ] || return 1
  owned_metadata managed-file "$receipt" "$kind" "$target"
}

# Runtime masks are lower-precedence than ~/.config/systemd/user units. Use
# one exact runtime-control drop-in as the lifecycle start barrier instead.
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

capture_managed_file_authority() {
  local receipt="$1" kind="$2" target="$3"
  local target_before receipt_before target_after receipt_after
  owned_file_cas recover "$target" || return 1
  owned_file_cas recover "$receipt" || return 1
  target_before="$(owned_metadata generation "$target")" || return 1
  receipt_before="$(owned_metadata generation "$receipt")" || return 1
  managed_receipt_matches "$receipt" "$kind" "$target" || return 1
  target_after="$(owned_metadata generation "$target")" || return 1
  receipt_after="$(owned_metadata generation "$receipt")" || return 1
  [ "$target_before" = "$target_after" ] \
    && [ "$receipt_before" = "$receipt_after" ] || return 1
  printf '%s\t%s\n' "$target_after" "$receipt_after"
}

capture_cli_removal_authority() {
  local fields_after fields_before digest_after digest_before
  local receipt_after receipt_before target_after target_before
  owned_file_cas recover "$CLI_PATH" || return 1
  owned_file_cas recover "$CLI_RECEIPT" || return 1
  if capture_managed_file_authority \
      "$CLI_RECEIPT" sia-cli "$CLI_PATH"; then
    return 0
  fi
  fields_before="$(owned_metadata managed-receipt-fields \
    "$CLI_RECEIPT" sia-cli "$CLI_PATH")" || return 1
  IFS=$'\t' read -r digest_before receipt_before <<< "$fields_before"
  target_before="$(owned_metadata fenced-generation \
    "$CLI_PATH" "$digest_before")" || return 1
  fenced_managed_file_authorized \
    "$CLI_RECEIPT" sia-cli "$CLI_PATH" || return 1
  fields_after="$(owned_metadata managed-receipt-fields \
    "$CLI_RECEIPT" sia-cli "$CLI_PATH")" || return 1
  IFS=$'\t' read -r digest_after receipt_after <<< "$fields_after"
  target_after="$(owned_metadata fenced-generation \
    "$CLI_PATH" "$digest_after")" || return 1
  [ "$digest_before" = "$digest_after" ] \
    && [ "$receipt_before" = "$receipt_after" ] \
    && [ "$target_before" = "$target_after" ] || return 1
  printf '%s\t%s\n' "$target_after" "$receipt_after"
}
inspect_user_unit() {
  local unit="$1" prefix="$2" expected_drop_in_paths="${3:-}"
  local state_mode="${4:-steady}" output key count
  local load_state active_state fragment_path unit_file_state
  local drop_in_paths main_pid refuse_manual_start job
  if ! output="$(bounded_command_capture systemctl --user show "$unit" \
      --property=LoadState --property=ActiveState \
      --property=FragmentPath --property=UnitFileState \
      --property=DropInPaths --property=MainPID \
      --property=RefuseManualStart --property=Job)"; then
    printf '%s\n' "$output" >&2
    return 1
  fi
  for key in LoadState ActiveState FragmentPath UnitFileState \
      DropInPaths MainPID RefuseManualStart Job; do
    count="$(printf '%s\n' "$output" | grep -c "^${key}=" || true)"
    [ "$count" = 1 ] || return 1
  done
  load_state="$(printf '%s\n' "$output" | sed -n 's/^LoadState=//p')"
  active_state="$(printf '%s\n' "$output" | sed -n 's/^ActiveState=//p')"
  fragment_path="$(printf '%s\n' "$output" | sed -n 's/^FragmentPath=//p')"
  unit_file_state="$(printf '%s\n' "$output" | sed -n 's/^UnitFileState=//p')"
  drop_in_paths="$(printf '%s\n' "$output" | sed -n 's/^DropInPaths=//p')"
  main_pid="$(printf '%s\n' "$output" | sed -n 's/^MainPID=//p')"
  refuse_manual_start="$(printf '%s\n' "$output" | sed -n 's/^RefuseManualStart=//p')"
  job="$(printf '%s\n' "$output" | sed -n 's/^Job=//p')"
  case "$load_state" in loaded|not-found|masked) ;; *) return 1;; esac
  case "$state_mode:$active_state" in
    steady:active|steady:inactive|steady:failed \
      |continuity:active|continuity:inactive|continuity:failed \
      |continuity:activating|continuity:deactivating) ;;
    *) return 1;;
  esac
  case "$unit_file_state" in
    ""|disabled|enabled|enabled-runtime|masked-runtime|static) ;;
    *)
    return 1;;
  esac
  [ "$drop_in_paths" = "$expected_drop_in_paths" ] || return 1
  [[ "$main_pid" =~ ^[0-9]+$ ]] || return 1
  [ -z "$job" ] || [ "$state_mode" = continuity ] || return 1
  if [ -n "$expected_drop_in_paths" ]; then
    [ "$refuse_manual_start" = yes ] || return 1
  else
    [ "$refuse_manual_start" = no ] || return 1
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

continuity_manager_binding_valid() {
  local index="$1" prefix="$2"
  local active_var fragment_var load_var main_pid_var unit_state_var
  load_var="${prefix}_LOAD_STATE"
  active_var="${prefix}_ACTIVE_STATE"
  fragment_var="${prefix}_FRAGMENT_PATH"
  unit_state_var="${prefix}_UNIT_FILE_STATE"
  main_pid_var="${prefix}_MAIN_PID"
  case "${!load_var}" in
    not-found)
      [ "${!active_var}" = inactive ] \
        && [ -z "${!fragment_var}" ] \
        && [ -z "${!unit_state_var}" ] \
        && [ "${!main_pid_var}" = 0 ]
      ;;
    loaded)
      [ "${!fragment_var}" = "${CONTINUITY_UNIT_PATHS[$index]}" ]
      ;;
    *) return 1 ;;
  esac
}

continuity_authority_unchanged() {
  local index="$1" target_now receipt_now
  [ "${CONTINUITY_UNIT_STATES[$index]:-}" = owned ] || return 1
  target_now="$(owned_metadata generation \
    "${CONTINUITY_UNIT_PATHS[$index]}")" || return 1
  receipt_now="$(owned_metadata generation \
    "${CONTINUITY_UNIT_RECEIPTS[$index]}")" || return 1
  [ "$target_now" = "${CONTINUITY_TARGET_EXPECTED[$index]}" ] \
    && [ "$receipt_now" = "${CONTINUITY_RECEIPT_EXPECTED[$index]}" ] \
    && managed_receipt_matches \
      "${CONTINUITY_UNIT_RECEIPTS[$index]}" \
      "${CONTINUITY_UNIT_KINDS[$index]}" \
      "${CONTINUITY_UNIT_PATHS[$index]}"
}

continuity_unit_absent() {
  local index="$1"
  [ ! -e "${CONTINUITY_UNIT_PATHS[$index]}" ] \
    && [ ! -L "${CONTINUITY_UNIT_PATHS[$index]}" ] \
    && [ ! -e "${CONTINUITY_UNIT_RECEIPTS[$index]}" ] \
    && [ ! -L "${CONTINUITY_UNIT_RECEIPTS[$index]}" ] \
    && inspect_user_unit "${CONTINUITY_UNIT_NAMES[$index]}" \
      CONTINUITY_ABSENT \
    && continuity_manager_binding_valid "$index" CONTINUITY_ABSENT \
    && [ "$CONTINUITY_ABSENT_LOAD_STATE" = not-found ] \
    && [ ! -e "${CONTINUITY_UNIT_PATHS[$index]}" ] \
    && [ ! -L "${CONTINUITY_UNIT_PATHS[$index]}" ] \
    && [ ! -e "${CONTINUITY_UNIT_RECEIPTS[$index]}" ] \
    && [ ! -L "${CONTINUITY_UNIT_RECEIPTS[$index]}" ]
}

# One durable record binds the unit and its ownership receipt to fixed archive
# paths.  The record is synced before either single-file CAS is allowed to run
# and is retained until daemon-reload has made the paired absence observable.
continuity_archive_intent_path() {
  local index="$1"
  printf '%s/.%s.archive-intent.json\n' \
    "$MANAGED_DIR" "${CONTINUITY_UNIT_NAMES[$index]}"
}

continuity_archive_intent() {
  python3 - "$@" <<'PY'
import ctypes
import hashlib
import json
import os
import re
import secrets
import stat
import sys

MAX_BYTES = 1_048_576
MAX_INTENT_BYTES = 65_536
SCHEMA = "sia-continuity-archive-pair-v1"
TOKEN = re.compile(
    r"present:(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):([0-9a-f]{64})")
REQUIRED = {"schema", "name", "kind", "unit", "receipt",
            "unit_archive", "receipt_archive", "unit_expected",
            "receipt_expected"}
arguments = sys.argv[1:]
if not arguments:
    raise SystemExit("missing continuity archive-intent operation")
operation, *values = arguments
if operation == "create" and len(values) == 9:
    (intent, name, kind, unit, receipt, unit_archive, receipt_archive,
     unit_expected, receipt_expected) = values
elif operation in {"read", "state"} and len(values) == 5:
    intent, name, kind, unit, receipt = values
    unit_archive = receipt_archive = None
    unit_expected = receipt_expected = None
elif operation == "finish" and len(values) == 9:
    (intent, name, kind, unit, receipt, unit_archive, receipt_archive,
     unit_expected, receipt_expected) = values
else:
    raise SystemExit("invalid continuity archive-intent arguments")

paths = [intent, unit, receipt]
if operation in {"create", "finish"}:
    paths.extend([unit_archive, receipt_archive])
if any(not os.path.isabs(path) or os.path.abspath(path) != path
       for path in paths):
    raise SystemExit("continuity archive-intent paths must be absolute")
if any(any(character in path for character in "\0\t\r\n")
       for path in paths):
    raise SystemExit("continuity archive-intent paths contain controls")
for path in paths:
    parent = os.path.dirname(path)
    if os.path.realpath(parent) != parent:
        raise SystemExit("continuity archive-intent paths must not traverse links")
if os.path.basename(intent) != f".{name}.archive-intent.json":
    raise SystemExit("continuity archive-intent name mismatch")
if re.fullmatch(r"sia-backup(?:-check)?\.(?:timer|service)", name) is None \
        or re.fullmatch(r"[a-z][a-z-]*", kind) is None:
    raise SystemExit("invalid continuity archive-intent identity")

directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                   | getattr(os, "O_DIRECTORY", 0)
                   | getattr(os, "O_NOFOLLOW", 0))
read_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
              | getattr(os, "O_NOFOLLOW", 0)
              | getattr(os, "O_NONBLOCK", 0))
parent_path = os.path.dirname(intent)
parent_fd = os.open(parent_path, directory_flags)
parent_info = os.fstat(parent_fd)
if not stat.S_ISDIR(parent_info.st_mode) \
        or parent_info.st_uid != os.geteuid():
    os.close(parent_fd)
    raise SystemExit("continuity archive-intent parent is not owned")
intent_name = os.path.basename(intent)


def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def child_exists(descriptor, child):
    try:
        os.stat(child, dir_fd=descriptor, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def unique_name(prefix):
    while True:
        candidate = prefix + secrets.token_hex(12)
        if not child_exists(parent_fd, candidate):
            return candidate


libc = ctypes.CDLL(None, use_errno=True)
renameat2 = libc.renameat2
renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p,
                      ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
renameat2.restype = ctypes.c_int
RENAME_NOREPLACE = 1


def rename_noreplace(source, destination):
    result = renameat2(parent_fd, os.fsencode(source),
                       parent_fd, os.fsencode(destination), RENAME_NOREPLACE)
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), (source, destination))


def reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate continuity archive-intent field")
        value[key] = item
    return value


def validate_record(record):
    if not isinstance(record, dict) or set(record) != REQUIRED \
            or record["schema"] != SCHEMA \
            or record["name"] != name or record["kind"] != kind \
            or record["unit"] != unit or record["receipt"] != receipt:
        raise ValueError("invalid continuity archive-intent record")
    for key in REQUIRED:
        if not isinstance(record[key], str):
            raise ValueError("non-string continuity archive-intent field")
    if TOKEN.fullmatch(record["unit_expected"]) is None \
            or TOKEN.fullmatch(record["receipt_expected"]) is None:
        raise ValueError("invalid continuity archive-intent generation")
    expected_unit_prefix = f".{name}.removed."
    expected_receipt_prefix = f".{name}.receipt.removed."
    unit_archive_name = os.path.basename(record["unit_archive"])
    receipt_archive_name = os.path.basename(record["receipt_archive"])
    if os.path.dirname(record["unit_archive"]) != os.path.dirname(unit) \
            or re.fullmatch(re.escape(expected_unit_prefix) + r"[A-Za-z0-9]+",
                            unit_archive_name) is None:
        raise ValueError("invalid continuity unit archive path")
    if os.path.dirname(record["receipt_archive"]) != os.path.dirname(receipt) \
            or re.fullmatch(re.escape(expected_receipt_prefix)
                            + r"[A-Za-z0-9]+",
                            receipt_archive_name) is None:
        raise ValueError("invalid continuity receipt archive path")
    for key in ("unit", "receipt", "unit_archive", "receipt_archive"):
        path = record[key]
        if not os.path.isabs(path) or os.path.abspath(path) != path \
                or os.path.realpath(os.path.dirname(path)) \
                != os.path.dirname(path):
            raise ValueError("unsafe continuity archive-intent path")
    if len({record["unit"], record["receipt"], record["unit_archive"],
            record["receipt_archive"]}) != 4:
        raise ValueError("continuity archive-intent paths are not distinct")
    return record


def read_record():
    descriptor = os.open(intent_name, read_flags, dir_fd=parent_fd)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() or before.st_nlink != 1 \
                or stat.S_IMODE(before.st_mode) != 0o600 \
                or before.st_size > MAX_INTENT_BYTES:
            raise ValueError("unsafe continuity archive-intent")
        chunks = []
        total = 0
        while True:
            chunk = os.read(descriptor, MAX_INTENT_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_INTENT_BYTES:
                raise ValueError("oversized continuity archive-intent")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        current = os.stat(intent_name, dir_fd=parent_fd,
                          follow_symlinks=False)
        if total != before.st_size or generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise ValueError("continuity archive-intent changed while read")
        record = json.loads(b"".join(chunks).decode("utf-8"),
                            object_pairs_hook=reject_duplicate_keys)
    finally:
        os.close(descriptor)
    return validate_record(record), generation(before)


def path_token(path, allow_absent=False):
    try:
        descriptor = os.open(path, read_flags)
    except FileNotFoundError:
        if allow_absent:
            try:
                os.stat(path, follow_symlinks=False)
            except FileNotFoundError:
                return "absent"
        raise
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() or before.st_size > MAX_BYTES:
            raise ValueError("unsafe continuity archive member")
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(descriptor, MAX_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BYTES:
                raise ValueError("oversized continuity archive member")
            digest.update(chunk)
        after = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        if total != before.st_size or generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise ValueError("continuity archive member changed while read")
    finally:
        os.close(descriptor)
    return "present:" + ":".join(
        str(item) for item in (*generation(before), digest.hexdigest()))


def moved_matches(actual, expected):
    actual_match = TOKEN.fullmatch(actual)
    expected_match = TOKEN.fullmatch(expected)
    if actual_match is None or expected_match is None:
        return False
    actual_fields = actual_match.groups()
    expected_fields = expected_match.groups()
    return actual_fields[:6] == expected_fields[:6] \
        and actual_fields[7] == expected_fields[7]


def member_state(current_path, archive_path, expected):
    current = path_token(current_path, allow_absent=True)
    archived = path_token(archive_path, allow_absent=True)
    if current == expected and archived == "absent":
        return "pending"
    if current == "absent" and moved_matches(archived, expected):
        return "archived"
    raise ValueError("ambiguous continuity archive member state")


try:
    if operation == "create":
        record = validate_record({
            "schema": SCHEMA, "name": name, "kind": kind,
            "unit": unit, "receipt": receipt,
            "unit_archive": unit_archive,
            "receipt_archive": receipt_archive,
            "unit_expected": unit_expected,
            "receipt_expected": receipt_expected,
        })
        if child_exists(parent_fd, intent_name) \
                or path_token(unit) != unit_expected \
                or path_token(receipt) != receipt_expected \
                or path_token(unit_archive, allow_absent=True) != "absent" \
                or path_token(receipt_archive, allow_absent=True) != "absent":
            raise ValueError("continuity archive-intent precondition changed")
        payload = (json.dumps(record, sort_keys=True,
                              separators=(",", ":")) + "\n").encode("utf-8")
        if len(payload) > MAX_INTENT_BYTES:
            raise ValueError("oversized continuity archive-intent payload")
        temporary = unique_name(".sia-continuity-archive-intent-stage.")
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
                        raise OSError("short continuity archive-intent write")
                    remaining = remaining[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            rename_noreplace(temporary, intent_name)
            os.fsync(parent_fd)
        except BaseException:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except FileNotFoundError:
                pass
            raise
        persisted, _persisted_generation = read_record()
        if persisted != record:
            raise ValueError("continuity archive-intent did not persist exactly")
    else:
        record, intent_generation = read_record()
        if operation == "read":
            print("\t".join((record["unit_archive"],
                             record["receipt_archive"],
                             record["unit_expected"],
                             record["receipt_expected"])))
        else:
            unit_state = member_state(record["unit"], record["unit_archive"],
                                      record["unit_expected"])
            receipt_state = member_state(
                record["receipt"], record["receipt_archive"],
                record["receipt_expected"])
            if operation == "state":
                print(unit_state + "\t" + receipt_state)
            else:
                if unit_state != "archived" or receipt_state != "archived":
                    raise ValueError("continuity archive pair is incomplete")
                if (record["unit_archive"] != unit_archive
                        or record["receipt_archive"] != receipt_archive
                        or record["unit_expected"] != unit_expected
                        or record["receipt_expected"] != receipt_expected):
                    raise ValueError("continuity archive-intent finish mismatch")
                current = os.stat(intent_name, dir_fd=parent_fd,
                                  follow_symlinks=False)
                if generation(current) != intent_generation:
                    raise ValueError("continuity archive-intent changed before finish")
                os.unlink(intent_name, dir_fd=parent_fd)
                os.fsync(parent_fd)
except (IndexError, OSError, UnicodeError, ValueError) as error:
    print(str(error), file=sys.stderr)
    raise SystemExit(1)
finally:
    os.close(parent_fd)
PY
}

continuity_archive_intent_fields() {
  local index="$1" intent="$2"
  continuity_archive_intent read "$intent" \
    "${CONTINUITY_UNIT_NAMES[$index]}" \
    "${CONTINUITY_UNIT_KINDS[$index]}" \
    "${CONTINUITY_UNIT_PATHS[$index]}" \
    "${CONTINUITY_UNIT_RECEIPTS[$index]}"
}

continuity_recovery_manager_quiesced() {
  local index="$1" active_var job_var load_var main_pid_var unit_state_var
  inspect_user_unit "${CONTINUITY_UNIT_NAMES[$index]}" \
    CONTINUITY_RECOVERY "" continuity || return 1
  load_var=CONTINUITY_RECOVERY_LOAD_STATE
  active_var=CONTINUITY_RECOVERY_ACTIVE_STATE
  unit_state_var=CONTINUITY_RECOVERY_UNIT_FILE_STATE
  main_pid_var=CONTINUITY_RECOVERY_MAIN_PID
  job_var=CONTINUITY_RECOVERY_JOB
  [ -z "${!job_var}" ] && [ "${!active_var}" = inactive ] \
    && [ "${!main_pid_var}" = 0 ] || return 1
  continuity_manager_binding_valid "$index" CONTINUITY_RECOVERY || return 1
  if [ "${!load_var}" = loaded ]; then
    case "${CONTINUITY_UNIT_NAMES[$index]}:${!unit_state_var}" in
      *.timer:disabled|*.service:static|*.service:disabled) ;;
      *) return 1 ;;
    esac
  fi
}

preflight_continuity_archive_intents() {
  local fields index intent status=0
  for index in "${!CONTINUITY_UNIT_NAMES[@]}"; do
    intent="$(continuity_archive_intent_path "$index")"
    if [ -e "$intent" ] || [ -L "$intent" ]; then
      CONTINUITY_UNIT_STATES[$index]=unsafe
      if ! fields="$(continuity_archive_intent_fields "$index" "$intent")" \
          || [ -z "$fields" ]; then
        failed "preserve ambiguous ${CONTINUITY_UNIT_NAMES[$index]} archive intent"
        CONTINUITY_SAFE_TO_REMOVE=0
        RUNTIME_NEEDED_BY_CONTINUITY=1
        status=1
        continue
      fi
      CONTINUITY_UNIT_STATES[$index]=recovery-pending
    fi
  done
  for index in "${!CONTINUITY_UNIT_NAMES[@]}"; do
    [ "${CONTINUITY_UNIT_STATES[$index]:-}" = recovery-pending ] \
      || continue
    if ! continuity_recovery_manager_quiesced "$index"; then
      failed "preserve active or ambiguous ${CONTINUITY_UNIT_NAMES[$index]} archive recovery"
      CONTINUITY_UNIT_STATES[$index]=unsafe
      CONTINUITY_SAFE_TO_REMOVE=0
      RUNTIME_NEEDED_BY_CONTINUITY=1
      status=1
    fi
  done
  return "$status"
}

preflight_continuity_units_for_uninstall() {
  local authority index intent receipt_expected target_expected
  for index in "${!CONTINUITY_UNIT_NAMES[@]}"; do
    intent="$(continuity_archive_intent_path "$index")"
    if [ -e "$intent" ] || [ -L "$intent" ]; then
      [ "${CONTINUITY_UNIT_STATES[$index]:-}" = recovery-pending ] \
        || CONTINUITY_UNIT_STATES[$index]=unsafe
      continue
    fi
    CONTINUITY_UNIT_STATES[$index]=unsafe
    if [ ! -e "${CONTINUITY_UNIT_PATHS[$index]}" ] \
        && [ ! -L "${CONTINUITY_UNIT_PATHS[$index]}" ] \
        && [ ! -e "${CONTINUITY_UNIT_RECEIPTS[$index]}" ] \
        && [ ! -L "${CONTINUITY_UNIT_RECEIPTS[$index]}" ]; then
      if continuity_unit_absent "$index"; then
        CONTINUITY_UNIT_STATES[$index]=absent
      else
        failed "preserve indeterminate ${CONTINUITY_UNIT_NAMES[$index]}"
        CONTINUITY_SAFE_TO_REMOVE=0
        RUNTIME_NEEDED_BY_CONTINUITY=1
      fi
      continue
    fi
    if authority="$(capture_managed_file_authority \
          "${CONTINUITY_UNIT_RECEIPTS[$index]}" \
          "${CONTINUITY_UNIT_KINDS[$index]}" \
          "${CONTINUITY_UNIT_PATHS[$index]}")"; then
      IFS=$'\t' read -r target_expected receipt_expected <<< "$authority"
      CONTINUITY_TARGET_EXPECTED[$index]="$target_expected"
      CONTINUITY_RECEIPT_EXPECTED[$index]="$receipt_expected"
      CONTINUITY_UNIT_STATES[$index]=owned
      if ! inspect_user_unit "${CONTINUITY_UNIT_NAMES[$index]}" \
          CONTINUITY_PREFLIGHT "" continuity \
          || ! continuity_manager_binding_valid \
            "$index" CONTINUITY_PREFLIGHT \
          || ! continuity_authority_unchanged "$index"; then
        failed "preserve indeterminate ${CONTINUITY_UNIT_NAMES[$index]}"
        CONTINUITY_UNIT_STATES[$index]=unsafe
        CONTINUITY_SAFE_TO_REMOVE=0
        RUNTIME_NEEDED_BY_CONTINUITY=1
      fi
    else
      failed "preserve unowned or modified ${CONTINUITY_UNIT_NAMES[$index]}"
      CONTINUITY_SAFE_TO_REMOVE=0
      RUNTIME_NEEDED_BY_CONTINUITY=1
    fi
  done
}

inspect_owned_continuity_unit() {
  local index="$1" prefix="$2"
  continuity_authority_unchanged "$index" \
    && inspect_user_unit "${CONTINUITY_UNIT_NAMES[$index]}" "$prefix" \
      "" continuity \
    && continuity_manager_binding_valid "$index" "$prefix" \
    && continuity_authority_unchanged "$index"
}

quiesce_continuity_units_for_uninstall() {
  local active_var index job_var load_var main_pid_var name state unit_state_var
  for index in "${!CONTINUITY_UNIT_NAMES[@]}"; do
    state="${CONTINUITY_UNIT_STATES[$index]:-unsafe}"
    if [ "$state" = absent ]; then
      continuity_unit_absent "$index" || return 1
      continue
    fi
    if [ "$state" = recovery-pending ]; then
      continuity_recovery_manager_quiesced "$index" || return 1
      continue
    fi
    [ "$state" = owned ] || return 1
    inspect_owned_continuity_unit "$index" CONTINUITY_HANDOFF \
      || return 1
    load_var=CONTINUITY_HANDOFF_LOAD_STATE
    active_var=CONTINUITY_HANDOFF_ACTIVE_STATE
    job_var=CONTINUITY_HANDOFF_JOB
    unit_state_var=CONTINUITY_HANDOFF_UNIT_FILE_STATE
    main_pid_var=CONTINUITY_HANDOFF_MAIN_PID
    if [ "${!load_var}" = loaded ]; then
      name="${CONTINUITY_UNIT_NAMES[$index]}"
      case "$name" in
        *.timer)
          if [ "${!active_var}" != inactive ] \
              || [ "${!main_pid_var}" != 0 ] \
              || [ -n "${!job_var}" ] \
              || [ "${!unit_state_var}" != disabled ]; then
            run_with_deadline 120 systemctl --user disable --now "$name" \
              || return 1
          fi
          ;;
        *.service)
          case "${!unit_state_var}" in static|disabled) ;; *) return 1 ;; esac
          if [ "${!active_var}" != inactive ] \
              || [ "${!main_pid_var}" != 0 ] \
              || [ -n "${!job_var}" ]; then
            run_with_deadline 120 systemctl --user stop "$name" || return 1
          fi
          ;;
        *) return 1 ;;
      esac
    fi
    inspect_owned_continuity_unit "$index" CONTINUITY_QUIESCED \
      || return 1
    [ -z "$CONTINUITY_QUIESCED_JOB" ] || return 1
    if [ "$CONTINUITY_QUIESCED_LOAD_STATE" = loaded ]; then
      [ "$CONTINUITY_QUIESCED_ACTIVE_STATE" = inactive ] \
        && [ "$CONTINUITY_QUIESCED_MAIN_PID" = 0 ] || return 1
      case "${CONTINUITY_UNIT_NAMES[$index]}" in
        *.timer)
          [ "$CONTINUITY_QUIESCED_UNIT_FILE_STATE" = disabled ] \
            || return 1
          ;;
        *.service)
          case "$CONTINUITY_QUIESCED_UNIT_FILE_STATE" in
            static|disabled) ;;
            *) return 1 ;;
          esac
          ;;
      esac
    fi
  done
}

complete_continuity_archive_pair() {
  local fields index="$1" intent="$2" receipt_backup receipt_expected
  local states unit_backup unit_expected unit_state receipt_state
  fields="$(continuity_archive_intent_fields "$index" "$intent")" || return 1
  IFS=$'\t' read -r unit_backup receipt_backup unit_expected receipt_expected \
    <<< "$fields"
  [ -n "$unit_backup" ] && [ -n "$receipt_backup" ] \
    && [ -n "$unit_expected" ] && [ -n "$receipt_expected" ] || return 1
  owned_file_cas recover "${CONTINUITY_UNIT_PATHS[$index]}" || return 1
  owned_file_cas recover "${CONTINUITY_UNIT_RECEIPTS[$index]}" || return 1
  states="$(continuity_archive_intent state "$intent" \
    "${CONTINUITY_UNIT_NAMES[$index]}" \
    "${CONTINUITY_UNIT_KINDS[$index]}" \
    "${CONTINUITY_UNIT_PATHS[$index]}" \
    "${CONTINUITY_UNIT_RECEIPTS[$index]}")" || return 1
  IFS=$'\t' read -r unit_state receipt_state <<< "$states"
  case "$unit_state:$receipt_state" in
    pending:pending)
      owned_file_cas archive "$unit_backup" \
        "${CONTINUITY_UNIT_PATHS[$index]}" "$unit_expected" >/dev/null \
        || return 1
      ;;
    archived:pending) ;;
    archived:archived)
      CONTINUITY_UNIT_STATES[$index]=pair-archived
      return 0
      ;;
    *)
      echo "ambiguous paired archive state for ${CONTINUITY_UNIT_NAMES[$index]}" >&2
      return 1
      ;;
  esac
  states="$(continuity_archive_intent state "$intent" \
    "${CONTINUITY_UNIT_NAMES[$index]}" \
    "${CONTINUITY_UNIT_KINDS[$index]}" \
    "${CONTINUITY_UNIT_PATHS[$index]}" \
    "${CONTINUITY_UNIT_RECEIPTS[$index]}")" || return 1
  IFS=$'\t' read -r unit_state receipt_state <<< "$states"
  [ "$unit_state:$receipt_state" = archived:pending ] || {
    echo "ambiguous paired archive state for ${CONTINUITY_UNIT_NAMES[$index]}" >&2
    return 1
  }
  owned_file_cas archive "$receipt_backup" \
    "${CONTINUITY_UNIT_RECEIPTS[$index]}" "$receipt_expected" >/dev/null \
    || return 1
  states="$(continuity_archive_intent state "$intent" \
    "${CONTINUITY_UNIT_NAMES[$index]}" \
    "${CONTINUITY_UNIT_KINDS[$index]}" \
    "${CONTINUITY_UNIT_PATHS[$index]}" \
    "${CONTINUITY_UNIT_RECEIPTS[$index]}")" || return 1
  [ "$states" = $'archived\tarchived' ] || {
    echo "ambiguous paired archive state for ${CONTINUITY_UNIT_NAMES[$index]}" >&2
    return 1
  }
  CONTINUITY_UNIT_STATES[$index]=pair-archived
}

finalize_continuity_archive_pair() {
  local fields index="$1" intent="$2" receipt_backup receipt_expected
  local unit_backup unit_expected
  [ "${CONTINUITY_UNIT_STATES[$index]:-}" = pair-archived ] || return 1
  continuity_unit_absent "$index" || return 1
  fields="$(continuity_archive_intent_fields "$index" "$intent")" || return 1
  IFS=$'\t' read -r unit_backup receipt_backup unit_expected receipt_expected \
    <<< "$fields"
  continuity_archive_intent finish "$intent" \
    "${CONTINUITY_UNIT_NAMES[$index]}" \
    "${CONTINUITY_UNIT_KINDS[$index]}" \
    "${CONTINUITY_UNIT_PATHS[$index]}" \
    "${CONTINUITY_UNIT_RECEIPTS[$index]}" \
    "$unit_backup" "$receipt_backup" "$unit_expected" "$receipt_expected" \
    || return 1
  CONTINUITY_UNIT_STATES[$index]=removed
  echo "exact prior ${CONTINUITY_UNIT_NAMES[$index]} retained at $unit_backup"
  echo "exact prior ${CONTINUITY_UNIT_NAMES[$index]} receipt retained at $receipt_backup"
}

recover_continuity_archive_intents() {
  local index intent status=0
  for index in "${!CONTINUITY_UNIT_NAMES[@]}"; do
    [ "${CONTINUITY_UNIT_STATES[$index]:-}" = recovery-pending ] \
      || continue
    intent="$(continuity_archive_intent_path "$index")"
    if ! continuity_recovery_manager_quiesced "$index" \
        || ! complete_continuity_archive_pair "$index" "$intent"; then
      echo "ambiguous archive recovery retained for ${CONTINUITY_UNIT_NAMES[$index]}" >&2
      status=1
      break
    fi
    CONTINUITY_ARCHIVE_NEEDED=1
  done
  if [ "$CONTINUITY_ARCHIVE_NEEDED" -eq 1 ]; then
    run_with_deadline 120 systemctl --user daemon-reload || status=1
  fi
  if [ "$status" -eq 0 ]; then
    for index in "${!CONTINUITY_UNIT_NAMES[@]}"; do
      [ "${CONTINUITY_UNIT_STATES[$index]:-}" = pair-archived ] \
        || continue
      intent="$(continuity_archive_intent_path "$index")"
      if ! finalize_continuity_archive_pair "$index" "$intent"; then
        echo "paired archive intent retained for ${CONTINUITY_UNIT_NAMES[$index]}" >&2
        status=1
        break
      fi
      CONTINUITY_UNIT_STATES[$index]=absent
    done
  fi
  return "$status"
}

archive_owned_continuity_units() {
  local index intent receipt_backup status=0 unit_backup
  for index in "${!CONTINUITY_UNIT_NAMES[@]}"; do
    [ "${CONTINUITY_UNIT_STATES[$index]:-}" = owned ] || continue
    if ! continuity_authority_unchanged "$index"; then
      echo "${CONTINUITY_UNIT_NAMES[$index]} authority changed before archival" >&2
      status=1
      break
    fi
    unit_backup="$(mktemp \
      "$(dirname "${CONTINUITY_UNIT_PATHS[$index]}")/.${CONTINUITY_UNIT_NAMES[$index]}.removed.XXXXXX")" \
      || { status=1; break; }
    rm -f -- "$unit_backup"
    receipt_backup="$(mktemp \
      "$(dirname "${CONTINUITY_UNIT_RECEIPTS[$index]}")/.${CONTINUITY_UNIT_NAMES[$index]}.receipt.removed.XXXXXX")" \
      || {
        status=1
        break
      }
    rm -f -- "$receipt_backup"
    intent="$(continuity_archive_intent_path "$index")"
    if ! continuity_archive_intent create "$intent" \
        "${CONTINUITY_UNIT_NAMES[$index]}" \
        "${CONTINUITY_UNIT_KINDS[$index]}" \
        "${CONTINUITY_UNIT_PATHS[$index]}" \
        "${CONTINUITY_UNIT_RECEIPTS[$index]}" \
        "$unit_backup" "$receipt_backup" \
        "${CONTINUITY_TARGET_EXPECTED[$index]}" \
        "${CONTINUITY_RECEIPT_EXPECTED[$index]}"; then
      status=1
      break
    fi
    CONTINUITY_UNIT_STATES[$index]=recovery-pending
    CONTINUITY_ARCHIVE_NEEDED=1
    if ! complete_continuity_archive_pair "$index" "$intent"; then
      echo "paired archive intent retained for ${CONTINUITY_UNIT_NAMES[$index]}" >&2
      status=1
      break
    fi
  done
  if [ "$CONTINUITY_ARCHIVE_NEEDED" -eq 1 ] \
      && ! run_with_deadline 120 systemctl --user daemon-reload; then
    status=1
  fi
  if [ "$status" -eq 0 ]; then
    for index in "${!CONTINUITY_UNIT_NAMES[@]}"; do
      [ "${CONTINUITY_UNIT_STATES[$index]:-}" = pair-archived ] \
        || continue
      intent="$(continuity_archive_intent_path "$index")"
      if ! finalize_continuity_archive_pair "$index" "$intent"; then
        echo "paired archive intent retained for ${CONTINUITY_UNIT_NAMES[$index]}" >&2
        status=1
        break
      fi
    done
  fi
  return "$status"
}

acquire_owner_lock() {
  local path="$1" variable="$2" label="$3" descriptor
  if [ -L "$path" ] || { [ -e "$path" ] && [ ! -f "$path" ]; }; then
    failed "unsafe $label lock"
    return 1
  fi
  if ! exec {descriptor}>>"$path"; then
    failed "open $label lock"
    return 1
  fi
  if ! chmod 0600 "$path"; then
    eval "exec ${descriptor}>&-"
    failed "secure $label lock"
    return 1
  fi
  if ! flock -n "$descriptor"; then
    eval "exec ${descriptor}>&-"
    failed "$label is busy"
    return 1
  fi
  printf -v "$variable" '%s' "$descriptor"
}

for dependency in flock python3 sha256sum; do
  command -v "$dependency" >/dev/null 2>&1 || {
    echo "$dependency is required for a safe uninstall" >&2
    exit 1
  }
done
if ! assert_safe_managed_roots \
  "$HOME/.local" "$HOME/.local/state" "$STATE_DIR" \
  "$MANAGED_DIR" "$MCP_MARKER_DIR" "$MCP_GUARD_DIR" \
  "$HOME/.local/share" "$SHARE_DIR" "$RUNTIME_BIN_DIR" \
  "$HOME/.local/bin" "$CONFIG_DIR" "$HOME/.config/systemd" \
  "$HOME/.config/systemd/user" "$HOME/.config/hypr" \
  "$HOME/.config/omarchy" "$HOME/.config/omarchy/plugins" \
  "$PLUGIN_DIR" "$HOME/.claude" "$HOME/.claude/skills" \
  "$SKILL_DIR"; then
  echo "unsafe managed roots preserved; uninstall not attempted" >&2
  exit 1
fi
mkdir -p "$HOME/.local/state" || {
  echo "could not prepare the lifecycle lease parent" >&2
  exit 1
}
if [ -L "$LIFECYCLE_ADMIN_LOCK" ] \
    || { [ -e "$LIFECYCLE_ADMIN_LOCK" ] \
         && [ ! -f "$LIFECYCLE_ADMIN_LOCK" ]; }; then
  echo "refusing unsafe lifecycle administration lease path" >&2
  exit 1
fi
exec {SIA_UNINSTALL_ADMIN_LOCK_FD}>>"$LIFECYCLE_ADMIN_LOCK"
chmod 0600 "$LIFECYCLE_ADMIN_LOCK"
flock -n "$SIA_UNINSTALL_ADMIN_LOCK_FD" || {
  echo "another SIA install or uninstall is active" >&2
  exit 1
}
if [ -e "$RESTORE_BARRIER" ] || [ -L "$RESTORE_BARRIER" ] \
    || [ -e "$RESTORE_MASK_DEBT" ] || [ -L "$RESTORE_MASK_DEBT" ] \
    || [ -e "$RESTORE_SUPERVISOR_DEBT" ] \
    || [ -L "$RESTORE_SUPERVISOR_DEBT" ]; then
  echo "SIA restore is interrupted; run 'sia restore recover' before uninstall" >&2
  exit 1
fi

inspect_owned_brainstem_for_uninstall() {
  local prefix="$1" expected_drop_in_paths=""
  local load_var active_var fragment_var unit_state_var main_pid_var
  if [ "$SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED" -eq 1 ]; then
    expected_drop_in_paths="$BRAINSTEM_RUNTIME_BARRIER"
  fi
  inspect_user_unit sia-brainstem.service "$prefix" \
    "$expected_drop_in_paths" || return 1
  load_var="${prefix}_LOAD_STATE"
  active_var="${prefix}_ACTIVE_STATE"
  fragment_var="${prefix}_FRAGMENT_PATH"
  unit_state_var="${prefix}_UNIT_FILE_STATE"
  main_pid_var="${prefix}_MAIN_PID"
  managed_receipt_matches "$UNIT_RECEIPT" brainstem-unit "$UNIT_PATH" \
    || return 1
  if [ "${!load_var}" = not-found ]; then
    [ "${!active_var}" = inactive ] && [ -z "${!fragment_var}" ] \
      && [ -z "${!unit_state_var}" ] && [ "${!main_pid_var}" = 0 ]
    return
  fi
  [ "${!load_var}" = loaded ] \
    && [ "${!fragment_var}" = "$UNIT_PATH" ]
}

verify_uninstall_brainstem_runtime_barrier() {
  local barrier_state
  managed_receipt_matches "$UNIT_RECEIPT" brainstem-unit "$UNIT_PATH" \
    || return 1
  barrier_state="$(brainstem_runtime_barrier_file state)" || return 1
  [ "$barrier_state" = active ] || return 1
  inspect_user_unit sia-brainstem.service BRAINSTEM_BARRIER \
    "$BRAINSTEM_RUNTIME_BARRIER" || return 1
  [ "$BRAINSTEM_BARRIER_LOAD_STATE" = loaded ] \
    && [ "$BRAINSTEM_BARRIER_ACTIVE_STATE" = inactive ] \
    && [ "$BRAINSTEM_BARRIER_FRAGMENT_PATH" = "$UNIT_PATH" ] \
    && [ "$BRAINSTEM_BARRIER_UNIT_FILE_STATE" = disabled ] \
    && [ "$BRAINSTEM_BARRIER_MAIN_PID" = 0 ]
}

install_uninstall_brainstem_runtime_barrier() {
  local barrier_state
  SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED=1
  barrier_state="$(brainstem_runtime_barrier_file state)" || return 1
  case "$barrier_state" in
    active) ;;
    retired)
      brainstem_runtime_barrier_file restore >/dev/null || return 1
      SIA_BRAINSTEM_RETIRED_BARRIER_PRESENT=0
      ;;
    absent)
      brainstem_runtime_barrier_file install >/dev/null || return 1
      ;;
    *) return 1 ;;
  esac
  run_with_deadline 120 systemctl --user daemon-reload || return 1
  run_with_deadline 120 systemctl --user disable --now \
    sia-brainstem.service || return 1
  run_with_deadline 120 systemctl --user reset-failed \
    sia-brainstem.service >/dev/null 2>&1 || true
  verify_uninstall_brainstem_runtime_barrier
}

remove_uninstall_brainstem_runtime_barrier() {
  local barrier_state restore_failed=0
  [ "$SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED" -eq 1 ] || return 0
  barrier_state="$(brainstem_runtime_barrier_file state)" || return 1
  [ "$barrier_state" = active ] || return 1
  # Keep an exact non-.conf sibling until the manager has proven the unit is
  # unbarriered. Any failure restores the active filename before returning.
  SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED=0
  if ! brainstem_runtime_barrier_file retire >/dev/null \
      || ! run_with_deadline 120 systemctl --user daemon-reload \
      || ! inspect_user_unit sia-brainstem.service BRAINSTEM_UNBARRIERED \
      || [ "$BRAINSTEM_UNBARRIERED_LOAD_STATE" != not-found ] \
      || [ "$BRAINSTEM_UNBARRIERED_ACTIVE_STATE" != inactive ] \
      || [ -n "$BRAINSTEM_UNBARRIERED_FRAGMENT_PATH" ] \
      || [ -n "$BRAINSTEM_UNBARRIERED_UNIT_FILE_STATE" ] \
      || [ "$BRAINSTEM_UNBARRIERED_MAIN_PID" != 0 ] \
      || ! brainstem_runtime_barrier_file discard >/dev/null; then
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
    [ "$restore_failed" -eq 0 ] || return 1
    return 1
  fi
  SIA_BRAINSTEM_RETIRED_BARRIER_PRESENT=0
}

verify_absent_brainstem_for_uninstall() {
  inspect_user_unit sia-brainstem.service BRAINSTEM_ABSENT || return 1
  [ "$BRAINSTEM_ABSENT_LOAD_STATE" = not-found ] \
    && [ "$BRAINSTEM_ABSENT_ACTIVE_STATE" = inactive ] \
    && [ -z "$BRAINSTEM_ABSENT_FRAGMENT_PATH" ] \
    && [ -z "$BRAINSTEM_ABSENT_UNIT_FILE_STATE" ] \
    && [ "$BRAINSTEM_ABSENT_MAIN_PID" = 0 ]
}

quiesce_owned_brainstem_for_uninstall() {
  if [ "$SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED" -eq 1 ]; then
    verify_uninstall_brainstem_runtime_barrier
    return
  fi
  inspect_owned_brainstem_for_uninstall BRAINSTEM_HANDOFF || {
    echo "sia-brainstem.service ownership changed during uninstall" >&2
    return 1
  }
  if [ "$BRAINSTEM_HANDOFF_LOAD_STATE" = not-found ]; then
    return 0
  fi
  if [ "$BRAINSTEM_HANDOFF_ACTIVE_STATE" = inactive ] \
      && [ "$BRAINSTEM_HANDOFF_MAIN_PID" = 0 ] \
      && [ "$BRAINSTEM_HANDOFF_UNIT_FILE_STATE" = disabled ]; then
    return 0
  fi
  run_with_deadline 120 systemctl --user disable --now \
    sia-brainstem.service || return 1
  inspect_owned_brainstem_for_uninstall BRAINSTEM_QUIESCED || return 1
  if [ "$BRAINSTEM_QUIESCED_LOAD_STATE" = loaded ] \
      && { [ "$BRAINSTEM_QUIESCED_ACTIVE_STATE" != inactive ] \
           || [ "$BRAINSTEM_QUIESCED_MAIN_PID" != 0 ] \
           || [ "$BRAINSTEM_QUIESCED_UNIT_FILE_STATE" != disabled ]; }; then
    echo "sia-brainstem.service did not remain disabled and inactive" >&2
    return 1
  fi
}

acquire_uninstall_lifecycle() {
  local attempt
  if [ -L "$LIFECYCLE_LOCK" ] \
      || { [ -e "$LIFECYCLE_LOCK" ] && [ ! -f "$LIFECYCLE_LOCK" ]; }; then
    echo "refusing unsafe lifecycle lease path" >&2
    return 1
  fi
  exec {SIA_UNINSTALL_LOCK_FD}>>"$LIFECYCLE_LOCK"
  chmod 0600 "$LIFECYCLE_LOCK"
  if [ "$BRAINSTEM_SAFE_TO_REMOVE" -eq 1 ]; then
    echo "waiting within a bounded window for active SIA clients"
    for ((attempt = 1; attempt <= SIA_LIFECYCLE_ACQUIRE_ATTEMPTS; attempt++)); do
      if flock -n "$SIA_UNINSTALL_LOCK_FD"; then
        # Legacy runtimes may not have held this lease; quiesce the exact
        # receipt-bound unit after acquisition as well as between retries.
        if [ "$UNIT_OWNED" -eq 1 ]; then
          if ! quiesce_owned_brainstem_for_uninstall; then
            failed "quiesce owned sia-brainstem.service"
            BRAINSTEM_SAFE_TO_REMOVE=0
            RUNTIME_NEEDED_BY_SERVICE=1
          fi
        elif ! verify_absent_brainstem_for_uninstall; then
          failed "preserve newly appeared sia-brainstem.service"
          BRAINSTEM_SAFE_TO_REMOVE=0
          RUNTIME_NEEDED_BY_SERVICE=1
        fi
        return 0
      fi
      if [ "$UNIT_OWNED" -eq 1 ]; then
        quiesce_owned_brainstem_for_uninstall || return 1
      else
        verify_absent_brainstem_for_uninstall || {
          echo "an unowned sia-brainstem.service appeared during uninstall" >&2
          return 1
        }
      fi
      if [ "$attempt" -lt "$SIA_LIFECYCLE_ACQUIRE_ATTEMPTS" ]; then
        sleep 1
      fi
    done
    echo "active SIA clients did not leave the runtime generation" >&2
    return 1
  else
    flock -n "$SIA_UNINSTALL_LOCK_FD" || {
      echo "unsafe or unowned active SIA process prevents uninstall" >&2
      return 1
    }
  fi
}

legacy_launchers_quiescent() {
  python3 - "$CLI_PATH" "$RUNTIME_BIN_DIR/sia-brainstem" \
      "$RUNTIME_BIN_DIR/sia-mcp" "$RUNTIME_BIN_DIR/sia-cli" \
      "$RUNTIME_BIN_DIR/sia-brainstem.py" <<'PY'
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
  echo "waiting within a bounded window for legacy launchers"
  for ((attempt = 1; attempt <= SIA_LIFECYCLE_ACQUIRE_ATTEMPTS; attempt++)); do
    if legacy_launchers_quiescent; then
      return 0
    fi
    if [ "$UNIT_OWNED" -eq 1 ]; then
      quiesce_owned_brainstem_for_uninstall || return 1
    else
      verify_absent_brainstem_for_uninstall || return 1
    fi
    if [ "$attempt" -lt "$SIA_LIFECYCLE_ACQUIRE_ATTEMPTS" ]; then
      sleep 1
    fi
  done
  echo "legacy SIA launchers did not become quiescent" >&2
  return 1
}
purge_fixed_publication_stages() {
  if [ "$#" -ne 2 ] \
      || [ "$1" != "$STATE_PUBLICATION_STAGE" ] \
      || [ "$2" != "$SHARE_PUBLICATION_STAGE" ]; then
    echo "refusing unexpected fixed publication stage purge" >&2
    return 1
  fi
  python3 - "$@" <<'PY'
import fcntl
import os
import stat
import sys

LOCK = "publish.lock"
PAYLOAD = "payload"
PURGING_SUFFIX = ".purging"
UID = os.geteuid()
DIRECTORY_FLAGS = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                   | getattr(os, "O_NOFOLLOW", 0)
                   | getattr(os, "O_DIRECTORY", 0))
FILE_FLAGS = (os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
              | getattr(os, "O_NOFOLLOW", 0))


def refuse(message):
    raise ValueError(message)


def linked(path):
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None


def open_parent(stage):
    parent = os.path.dirname(stage)
    descriptor = os.open(parent, DIRECTORY_FLAGS)
    info = os.fstat(descriptor)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != UID \
            or stat.S_IMODE(info.st_mode) & 0o022:
        os.close(descriptor)
        refuse("fixed publication stage parent is unsafe")
    return parent, descriptor


def inspect_stage(parent_descriptor, name, *, recovering):
    linked_info = os.stat(
        name, dir_fd=parent_descriptor, follow_symlinks=False)
    if not stat.S_ISDIR(linked_info.st_mode) \
            or linked_info.st_uid != UID \
            or stat.S_IMODE(linked_info.st_mode) != 0o700:
        refuse("fixed publication stage is not an owned mode-0700 directory")
    descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=parent_descriptor)
    lock_descriptor = None
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (
                linked_info.st_dev, linked_info.st_ino):
            refuse("fixed publication stage changed while opening")
        names = []
        with os.scandir(descriptor) as entries:
            for entry in entries:
                names.append(entry.name)
                if len(names) > 2:
                    refuse("fixed publication stage has unexpected entries")
        name_set = set(names)
        allowed = {LOCK, PAYLOAD}
        if not name_set <= allowed \
                or (not recovering and LOCK not in name_set) \
                or (recovering and name_set == {PAYLOAD}):
            refuse("fixed publication stage has an invalid entry set")
        for entry_name in names:
            info = os.stat(
                entry_name, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != UID \
                    or info.st_nlink != 1 \
                    or stat.S_IMODE(info.st_mode) != 0o600:
                refuse("fixed publication stage entry is unsafe")
        if LOCK in name_set:
            lock_descriptor = os.open(
                LOCK, FILE_FLAGS, dir_fd=descriptor)
            held = os.fstat(lock_descriptor)
            try:
                fcntl.flock(
                    lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                refuse("fixed publication stage is still in use")
            current = os.stat(
                LOCK, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISREG(current.st_mode) \
                    or current.st_uid != UID or current.st_nlink != 1 \
                    or stat.S_IMODE(current.st_mode) != 0o600 \
                    or (held.st_dev, held.st_ino) != (
                        current.st_dev, current.st_ino):
                refuse("fixed publication stage lock changed")
        current_stage = os.stat(
            name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (
                current_stage.st_dev, current_stage.st_ino):
            refuse("fixed publication stage path changed")
        return descriptor, lock_descriptor, name_set
    except Exception:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        os.close(descriptor)
        raise


resources = []
try:
    # Bind and validate every surviving stage before mutating either one. An
    # unsafe stage therefore cannot cause the other valid stage to be erased.
    for stage in sys.argv[1:]:
        normal = linked(stage)
        purging = linked(stage + PURGING_SUFFIX)
        if normal is not None and purging is not None:
            refuse("fixed publication stage and recovery path both exist")
        if normal is None and purging is None:
            resources.append(None)
            continue
        parent, parent_descriptor = open_parent(stage)
        selected = (os.path.basename(stage) if normal is not None
                    else os.path.basename(stage) + PURGING_SUFFIX)
        try:
            descriptor, lock_descriptor, names = inspect_stage(
                parent_descriptor, selected, recovering=normal is None)
        except Exception:
            os.close(parent_descriptor)
            raise
        resources.append({
            "stage": stage,
            "parent": parent,
            "parent_descriptor": parent_descriptor,
            "name": selected,
            "descriptor": descriptor,
            "lock_descriptor": lock_descriptor,
            "names": names,
            "needs_rename": normal is not None,
        })

    for resource in resources:
        if resource is None:
            continue
        parent_descriptor = resource["parent_descriptor"]
        descriptor = resource["descriptor"]
        purging_name = os.path.basename(resource["stage"]) + PURGING_SUFFIX
        if resource["needs_rename"]:
            os.rename(
                resource["name"], purging_name,
                src_dir_fd=parent_descriptor, dst_dir_fd=parent_descriptor)
            os.fsync(parent_descriptor)
            moved = os.stat(
                purging_name, dir_fd=parent_descriptor,
                follow_symlinks=False)
            held = os.fstat(descriptor)
            if (moved.st_dev, moved.st_ino) != (held.st_dev, held.st_ino):
                refuse("fixed publication stage rename changed identity")
        if PAYLOAD in resource["names"]:
            os.unlink(PAYLOAD, dir_fd=descriptor)
            os.fsync(descriptor)
        if LOCK in resource["names"]:
            os.unlink(LOCK, dir_fd=descriptor)
            os.fsync(descriptor)
        if resource["lock_descriptor"] is not None:
            os.close(resource["lock_descriptor"])
            resource["lock_descriptor"] = None
        os.close(descriptor)
        resource["descriptor"] = None
        os.rmdir(purging_name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
finally:
    for resource in resources:
        if resource is None:
            continue
        lock_descriptor = resource.get("lock_descriptor")
        descriptor = resource.get("descriptor")
        parent_descriptor = resource.get("parent_descriptor")
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        if descriptor is not None:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)
PY
}
safe_remove_tree() {
  if [ -L "$1" ] || { [ -e "$1" ] && [ ! -d "$1" ]; }; then
    echo "refusing unsafe managed tree removal: $1" >&2
    return 1
  fi
  case "$1" in
    "$RUNTIME_BIN_DIR"|"$STATE_DIR"|"$CONTINUITY_STATE_DIR"\
      |"$CONFIG_DIR"|"$SHARE_DIR")
      rm -rf -- "$1"
      ;;
    *) echo "refusing unexpected tree removal: $1" >&2; return 1 ;;
  esac
}
remove_managed_metadata() {
  local path="$1" expected="$2" archive archived
  archive="$(mktemp "$(dirname "$path")/.${path##*/}.removed.XXXXXX")" \
    || return 1
  rm -f -- "$archive"
  if ! archived="$(owned_file_cas archive "$archive" "$path" \
      "$expected")"; then
    [ ! -e "$archive" ] \
      || echo "managed metadata retained at $archive" >&2
    return 1
  fi
  if [ "$(owned_metadata generation "$archive" 2>/dev/null || true)" \
      != "$archived" ]; then
    echo "managed metadata archive changed; retained at $archive" >&2
    return 1
  fi
  echo "managed metadata archived at $archive"
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
modern_v2_names = ("sia-brainstem", "sia-brainstem.py", "sia-cli",
                   "sia-ledger", "sia-mcp", "siabench.py", "sialib.py",
                   "siamind.py", "siaqueue.py", "siatakes.py")
modern_v3_names = modern_v2_names + ("siasenses.py",)
modern_v4_names = modern_v3_names + (
    "siacapsule.py", "siabackup.py", "siarestoreadmit.py",
    "sia-continuity-worker")
modern = any(os.path.lexists(os.path.join(root, name))
             for name in ("sia-brainstem.py", "sia-cli"))
v3 = os.path.lexists(os.path.join(root, "siasenses.py"))
v4 = any(os.path.lexists(os.path.join(root, name))
         for name in ("siacapsule.py", "siabackup.py",
                      "sia-continuity-worker"))
if v4:
    names, salt = modern_v4_names, b"sia-runtime-v4\0"
elif v3:
    names, salt = modern_v3_names, b"sia-runtime-v3\0"
elif modern:
    names, salt = modern_v2_names, b"sia-runtime-v2\0"
else:
    names, salt = legacy_names, b"sia-runtime-v1\0"
digest = hashlib.sha256(salt)
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
            raise SystemExit(1)
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
            raise SystemExit(1)
    finally:
        os.close(descriptor)
    digest.update(name.encode() + b"\0" + member.digest())
print(digest.hexdigest())
PY
}
runtime_receipt_valid() {
  local digest
  [ -d "$RUNTIME_BIN_DIR" ] && [ ! -L "$RUNTIME_BIN_DIR" ] \
    && [ -f "$RUNTIME_RECEIPT" ] && [ ! -L "$RUNTIME_RECEIPT" ] || return 1
  digest="$(runtime_tree_digest "$RUNTIME_BIN_DIR")" || return 1
  [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || return 1
  owned_metadata runtime "$RUNTIME_RECEIPT" "$RUNTIME_BIN_DIR" "$digest"
}

fenced_managed_file_authorized() {
  python3 - "$LAUNCH_FENCE_JOURNAL" "$LIFECYCLE_TOMBSTONE" \
      "$1" "$2" "$3" <<'PY'
import json
import os
import re
import stat
import sys

journal, tombstone, receipt, kind, target = sys.argv[1:]
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
            raise RuntimeError("unsafe managed metadata")
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
                or current.st_uid != uid or b"\0" in content \
                or generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise RuntimeError("managed metadata changed while reading")
        return content
    finally:
        os.close(descriptor)

try:
    payload = json.loads(read_owned(journal, 1_048_576))
    marker = os.lstat(tombstone)
    contents = read_owned(receipt, 65_536).decode("utf-8")
    current = os.lstat(target)
except (FileNotFoundError, OSError, RuntimeError, UnicodeError,
        ValueError, json.JSONDecodeError):
    raise SystemExit(1)
if not stat.S_ISREG(marker.st_mode) or marker.st_uid != uid \
        or not isinstance(payload, dict) \
        or payload.get("schema") != "sia-launch-fence-v1" \
        or set(payload) != {"schema", "runtime_before_digest",
                            "runtime_digest", "cli_digest", "entries"} \
        or not isinstance(payload["entries"], list):
    raise SystemExit(1)
matches = []
seen = set()
for entry in payload["entries"]:
    if not isinstance(entry, dict) \
            or set(entry) != {"path", "device", "inode", "mode", "sha256"} \
            or not isinstance(entry["path"], str) \
            or entry["path"] in seen \
            or any(isinstance(entry[key], bool)
                   or not isinstance(entry[key], int) or entry[key] < 0
                   for key in ("device", "inode", "mode")) \
            or entry["mode"] > 0o7777 \
            or re.fullmatch(r"[0-9a-f]{64}",
                            str(entry.get("sha256", ""))) is None:
        raise SystemExit(1)
    seen.add(entry["path"])
    if os.path.abspath(entry["path"]) == os.path.abspath(target):
        matches.append(entry)
if len(matches) != 1:
    raise SystemExit(1)
entry = matches[0]
expected = (f"managed-by=khephri.sia\nkind={kind}\npath={target}\n"
            f"sha256={entry['sha256']}\n")
if not stat.S_ISREG(current.st_mode) or current.st_uid != uid \
        or stat.S_IMODE(current.st_mode) != 0 \
        or (current.st_dev, current.st_ino) != (
            entry["device"], entry["inode"]) \
        or contents != expected:
    raise SystemExit(1)
PY
}

fenced_runtime_authorized() {
  python3 - "$LAUNCH_FENCE_JOURNAL" "$LIFECYCLE_TOMBSTONE" \
      "$RUNTIME_RECEIPT" "$RUNTIME_BIN_DIR" <<'PY'
import hashlib
import json
import os
import re
import stat
import sys

journal, tombstone, receipt, runtime = sys.argv[1:]
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
            raise RuntimeError("unsafe managed metadata")
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
                or current.st_uid != uid or b"\0" in content \
                or generation(before) != generation(after) \
                or generation(after) != generation(current):
            raise RuntimeError("managed metadata changed while reading")
        return content
    finally:
        os.close(descriptor)

try:
    payload = json.loads(read_owned(journal, 1_048_576))
    marker = os.lstat(tombstone)
    contents = read_owned(receipt, 65_536).decode("utf-8")
    runtime_info = os.lstat(runtime)
except (FileNotFoundError, OSError, RuntimeError, UnicodeError,
        ValueError, json.JSONDecodeError):
    raise SystemExit(1)
if not stat.S_ISREG(marker.st_mode) or marker.st_uid != uid \
        or not stat.S_ISDIR(runtime_info.st_mode) \
        or runtime_info.st_uid != uid \
        or not isinstance(payload, dict) \
        or payload.get("schema") != "sia-launch-fence-v1" \
        or set(payload) != {"schema", "runtime_before_digest",
                            "runtime_digest", "cli_digest", "entries"} \
        or not isinstance(payload["entries"], list):
    raise SystemExit(1)
before_digest = payload["runtime_before_digest"]
if not isinstance(before_digest, str) \
        or re.fullmatch(r"[0-9a-f]{64}", before_digest) is None:
    raise SystemExit(1)
expected = (f"managed-by=khephri.sia\nkind=runtime\npath={runtime}\n"
            f"sha256={before_digest}\n")
if contents != expected:
    raise SystemExit(1)
entries = {}
for entry in payload["entries"]:
    if not isinstance(entry, dict) \
            or set(entry) != {"path", "device", "inode", "mode", "sha256"} \
            or not isinstance(entry["path"], str) \
            or entry["path"] in entries \
            or any(isinstance(entry[key], bool)
                   or not isinstance(entry[key], int) or entry[key] < 0
                   for key in ("device", "inode", "mode")) \
            or entry["mode"] > 0o7777 \
            or re.fullmatch(r"[0-9a-f]{64}",
                            str(entry.get("sha256", ""))) is None:
        raise SystemExit(1)
    entries[entry["path"]] = entry
legacy_names = ("sia-brainstem", "sia-ledger", "sia-mcp", "siabench.py",
                "sialib.py", "siamind.py", "siaqueue.py", "siatakes.py")
modern_v2_names = ("sia-brainstem", "sia-brainstem.py", "sia-cli",
                   "sia-ledger", "sia-mcp", "siabench.py", "sialib.py",
                   "siamind.py", "siaqueue.py", "siatakes.py")
modern_v3_names = modern_v2_names + ("siasenses.py",)
modern_v4_names = modern_v3_names + (
    "siacapsule.py", "siabackup.py", "siarestoreadmit.py",
    "sia-continuity-worker")
modern = any(os.path.lexists(os.path.join(runtime, name))
             for name in ("sia-brainstem.py", "sia-cli"))
v3 = os.path.lexists(os.path.join(runtime, "siasenses.py"))
v4 = any(os.path.lexists(os.path.join(runtime, name))
         for name in ("siacapsule.py", "siabackup.py",
                      "sia-continuity-worker"))
if v4:
    names, salt = modern_v4_names, b"sia-runtime-v4\0"
elif v3:
    names, salt = modern_v3_names, b"sia-runtime-v3\0"
elif modern:
    names, salt = modern_v2_names, b"sia-runtime-v2\0"
else:
    names, salt = legacy_names, b"sia-runtime-v1\0"
digest = hashlib.sha256(salt)
for name in names:
    path = os.path.join(runtime, name)
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != uid:
        raise SystemExit(1)
    if stat.S_IMODE(info.st_mode) == 0:
        entry = entries.get(path)
        if entry is None or (info.st_dev, info.st_ino) != (
                entry["device"], entry["inode"]):
            raise SystemExit(1)
        member_digest = bytes.fromhex(entry["sha256"])
    else:
        descriptor = os.open(path, flags)
        try:
            held = os.fstat(descriptor)
            if not stat.S_ISREG(held.st_mode) or held.st_uid != uid \
                    or (held.st_dev, held.st_ino) != (
                        info.st_dev, info.st_ino):
                raise SystemExit(1)
            member = hashlib.sha256()
            while chunk := os.read(descriptor, 1_048_576):
                member.update(chunk)
            member_digest = member.digest()
        finally:
            os.close(descriptor)
    digest.update(name.encode() + b"\0" + member_digest)
if digest.hexdigest() != before_digest:
    raise SystemExit(1)
PY
}

capture_runtime_removal_authority() {
  local tree_before tree_after receipt_before receipt_after
  owned_tree_cas recover "$RUNTIME_BIN_DIR" || return 1
  owned_file_cas recover "$RUNTIME_RECEIPT" || return 1
  tree_before="$(owned_tree_generation "$RUNTIME_BIN_DIR")" || return 1
  receipt_before="$(owned_metadata generation "$RUNTIME_RECEIPT")" \
    || return 1
  if ! runtime_receipt_valid && ! fenced_runtime_authorized; then
    return 1
  fi
  tree_after="$(owned_tree_generation "$RUNTIME_BIN_DIR")" || return 1
  receipt_after="$(owned_metadata generation "$RUNTIME_RECEIPT")" \
    || return 1
  [ "$tree_before" = "$tree_after" ] \
    && [ "$receipt_before" = "$receipt_after" ] || return 1
  printf '%s\t%s\n' "$tree_after" "$receipt_after"
}

recover_publication_receipts_from_fence() {
  local recovered desired_runtime desired_cli fenced_cli current
  if [ ! -e "$LAUNCH_FENCE_JOURNAL" ] \
      && [ ! -L "$LAUNCH_FENCE_JOURNAL" ]; then
    return 0
  fi
  recovered="$(python3 - "$LAUNCH_FENCE_JOURNAL" \
      "$LIFECYCLE_TOMBSTONE" "$CLI_PATH" <<'PY'
import json
import os
import re
import stat
import sys

journal, tombstone, cli = sys.argv[1:]
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
            raise SystemExit("unsafe uninstall launch-fence journal")
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
            raise SystemExit("uninstall launch-fence journal changed")
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
    raise SystemExit("invalid uninstall launch-fence journal")
for key in ("runtime_before_digest", "runtime_digest", "cli_digest"):
    value = payload[key]
    if not isinstance(value, str) \
            or value and re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise SystemExit("invalid uninstall launch-fence digest")
fenced_cli = ""
seen = set()
for entry in payload["entries"]:
    if not isinstance(entry, dict) \
            or set(entry) != {"path", "device", "inode", "mode", "sha256"} \
            or not isinstance(entry["path"], str) \
            or entry["path"] in seen \
            or any(isinstance(entry[key], bool)
                   or not isinstance(entry[key], int) or entry[key] < 0
                   for key in ("device", "inode", "mode")) \
            or entry["mode"] > 0o7777 \
            or re.fullmatch(r"[0-9a-f]{64}",
                            str(entry.get("sha256", ""))) is None:
        raise SystemExit("invalid uninstall launch-fence entry")
    seen.add(entry["path"])
    if os.path.abspath(entry["path"]) == os.path.abspath(cli):
        try:
            current = os.lstat(cli)
        except FileNotFoundError:
            continue
        if stat.S_ISREG(current.st_mode) \
                and stat.S_IMODE(current.st_mode) == 0 \
                and (current.st_dev, current.st_ino) == (
                    entry["device"], entry["inode"]):
            fenced_cli = entry["sha256"]
print(payload["runtime_digest"] + "\t" + payload["cli_digest"]
      + "\t" + fenced_cli)
PY
  )" || return 1
  IFS=$'\t' read -r desired_runtime desired_cli fenced_cli <<< "$recovered"
  if [ -n "$desired_runtime" ] \
      && [ -d "$RUNTIME_BIN_DIR" ] && [ ! -L "$RUNTIME_BIN_DIR" ]; then
    current="$(runtime_tree_digest "$RUNTIME_BIN_DIR" 2>/dev/null || true)"
    if [ -n "$current" ] && [ "$current" = "$desired_runtime" ]; then
      write_managed_receipt \
        "$RUNTIME_RECEIPT" runtime "$RUNTIME_BIN_DIR" "$current" || return 1
      echo "recovered exact runtime receipt from interrupted publication"
    fi
  fi
  if [ -n "$desired_cli" ] \
      && [ -f "$CLI_PATH" ] && [ ! -L "$CLI_PATH" ]; then
    if [ "$desired_cli" = "$fenced_cli" ]; then
      current="$fenced_cli"
    else
      current="$(owned_metadata digest "$CLI_PATH" 2>/dev/null)" \
        || return 1
    fi
    if [ "$current" = "$desired_cli" ]; then
      write_managed_receipt \
        "$CLI_RECEIPT" sia-cli "$CLI_PATH" "$current" || return 1
      echo "recovered exact CLI receipt from interrupted publication"
    fi
  fi
}

arm_uninstall_launch_fence() {
  local runtime_owned=0 runtime_before=""
  local -a fence_paths=()
  mkdir -p "$MANAGED_DIR" || return 1
  if managed_receipt_matches "$CLI_RECEIPT" sia-cli "$CLI_PATH" \
      || fenced_managed_file_authorized \
        "$CLI_RECEIPT" sia-cli "$CLI_PATH"; then
    fence_paths+=("$CLI_PATH")
  fi
  if runtime_receipt_valid; then
    runtime_owned=1
    runtime_before="$(runtime_tree_digest "$RUNTIME_BIN_DIR")" || return 1
  elif fenced_runtime_authorized; then
    runtime_owned=1
    runtime_before="$(owned_metadata runtime-digest \
      "$RUNTIME_RECEIPT" "$RUNTIME_BIN_DIR")" || return 1
  fi
  if [ "$runtime_owned" -eq 1 ]; then
    fence_paths+=("$RUNTIME_BIN_DIR/sia-brainstem"
                  "$RUNTIME_BIN_DIR/sia-mcp")
  fi
  SIA_LAUNCH_FENCE_ARMED=1
  python3 - "$LAUNCH_FENCE_JOURNAL" "$runtime_before" \
      "${fence_paths[@]}" <<'PY'
import hashlib
import json
import os
import re
import stat
import tempfile
import sys

journal, runtime_before, *paths = sys.argv[1:]
uid = os.geteuid()
prior = {}
runtime_digest = ""
cli_digest = ""
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
            raise SystemExit("unsafe uninstall launch-fence journal")
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
            raise SystemExit("uninstall launch-fence journal changed")
        return json.loads(content)
    finally:
        os.close(descriptor)

try:
    payload = read_journal(journal)
except FileNotFoundError:
    pass
else:
    if not isinstance(payload, dict) \
            or payload.get("schema") != "sia-launch-fence-v1" \
            or set(payload) != {"schema", "runtime_before_digest",
                                "runtime_digest", "cli_digest", "entries"} \
            or not isinstance(payload["entries"], list):
        raise SystemExit("invalid uninstall launch-fence journal")
    runtime_digest = payload["runtime_digest"]
    cli_digest = payload["cli_digest"]
    for value in (runtime_digest, cli_digest):
        if not isinstance(value, str) \
                or value and re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise SystemExit("invalid uninstall launch-fence digest")
    prior = {entry.get("path"): entry for entry in payload["entries"]
             if isinstance(entry, dict)}
if runtime_before \
        and re.fullmatch(r"[0-9a-f]{64}", runtime_before) is None:
    raise SystemExit("invalid uninstall runtime digest")

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
        entries.append({"path": path, "device": info.st_dev,
                        "inode": info.st_ino, "mode": current_mode,
                        "sha256": digest.hexdigest()})

    payload = {"schema": "sia-launch-fence-v1",
               "runtime_before_digest": runtime_before,
               "runtime_digest": runtime_digest,
               "cli_digest": cli_digest, "entries": entries}
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

restore_runtime_archive_fence_modes() {
  local archive="$1"
  python3 - "$LAUNCH_FENCE_JOURNAL" "$RUNTIME_BIN_DIR" "$archive" <<'PY'
import json
import os
import stat
import sys

journal, runtime, archive = map(os.path.abspath, sys.argv[1:])
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
        raise SystemExit("unsafe uninstall launch-fence journal")
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
        raise SystemExit("uninstall launch-fence journal changed")
    payload = json.loads(content)
finally:
    os.close(descriptor)
archive_info = os.lstat(archive)
if not stat.S_ISDIR(archive_info.st_mode) or archive_info.st_uid != uid \
        or payload.get("schema") != "sia-launch-fence-v1" \
        or not isinstance(payload.get("entries"), list):
    raise SystemExit("unsafe archived runtime fence")
for entry in payload["entries"]:
    if not isinstance(entry, dict) or os.path.dirname(
            os.path.abspath(str(entry.get("path", "")))) != runtime:
        continue
    candidate = os.path.join(archive, os.path.basename(entry["path"]))
    try:
        current = os.lstat(candidate)
    except FileNotFoundError:
        continue
    mode = entry.get("mode")
    if isinstance(mode, bool) or not isinstance(mode, int) \
            or not 0 <= mode <= 0o7777 \
            or not stat.S_ISREG(current.st_mode) or current.st_uid != uid \
            or (current.st_dev, current.st_ino) != (
                entry.get("device"), entry.get("inode")):
        raise SystemExit("archived runtime launch inode changed")
    os.chmod(candidate, mode, follow_symlinks=False)
directory = os.open(archive,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(directory)
finally:
    os.close(directory)
PY
}

complete_uninstall_launch_fence() {
  local public_remains=0
  if [ -e "$CLI_PATH" ] || [ -L "$CLI_PATH" ] \
      || [ -e "$RUNTIME_BIN_DIR" ] || [ -L "$RUNTIME_BIN_DIR" ]; then
    public_remains=1
  fi
  python3 - "$LAUNCH_FENCE_JOURNAL" "$public_remains" <<'PY'
import json
import os
import stat
import sys

journal, public_remains = sys.argv[1], sys.argv[2] == "1"
uid = os.geteuid()
flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
         | getattr(os, "O_NOFOLLOW", 0))
try:
    descriptor = os.open(journal, flags)
except FileNotFoundError:
    if public_remains:
        raise SystemExit("surviving runtime lacks its launch-fence journal")
    raise SystemExit(0)
def generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)

try:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_uid != uid \
            or before.st_size > 1_048_576:
        raise SystemExit("unsafe uninstall launch-fence journal")
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
        raise SystemExit("uninstall launch-fence journal changed")
    payload = json.loads(content)
finally:
    os.close(descriptor)
if payload.get("schema") != "sia-launch-fence-v1" \
        or not isinstance(payload.get("entries"), list):
    raise SystemExit("invalid uninstall launch-fence journal")
for entry in payload["entries"]:
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
        raise SystemExit("invalid uninstall launch-fence entry")
    path = entry["path"]
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        continue
    mode = entry.get("mode")
    if isinstance(mode, bool) or not isinstance(mode, int) \
            or not 0 <= mode <= 0o7777 \
            or not stat.S_ISREG(current.st_mode) or current.st_uid != uid \
            or (current.st_dev, current.st_ino) != (
                entry.get("device"), entry.get("inode")):
        raise SystemExit("surviving launch path changed during uninstall")
    os.chmod(path, mode, follow_symlinks=False)
    after = os.lstat(path)
    if (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino) \
            or stat.S_IMODE(after.st_mode) != mode:
        raise SystemExit("could not restore surviving launch mode")
    file_descriptor = os.open(path, flags)
    try:
        os.fsync(file_descriptor)
    finally:
        os.close(file_descriptor)
os.unlink(journal)
directory = os.open(os.path.dirname(journal),
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(directory)
finally:
    os.close(directory)
PY
  if [ "$public_remains" -eq 1 ]; then
    clear_lifecycle_tombstone || return 1
  fi
  SIA_LAUNCH_FENCE_ARMED=0
}
remove_owned_cli() {
  local authority backup cli_expected receipt_expected receipt_before
  local archived
  if [ ! -e "$CLI_PATH" ] && [ ! -L "$CLI_PATH" ]; then
    if [ ! -e "$CLI_RECEIPT" ] && [ ! -L "$CLI_RECEIPT" ]; then
      return 0
    fi
    receipt_expected="$(owned_metadata managed-receipt-generation \
      "$CLI_RECEIPT" sia-cli "$CLI_PATH")" || {
      echo "stale or malformed SIA CLI receipt preserved" >&2
      RUNTIME_NEEDED_BY_CLI=1
      return 1
    }
    receipt_before="$(owned_metadata managed-receipt-generation \
      "$CLI_RECEIPT" sia-cli "$CLI_PATH")" || return 1
    if [ "$receipt_before" != "$receipt_expected" ] \
        || ! remove_managed_metadata "$CLI_RECEIPT" "$receipt_expected"; then
        RUNTIME_NEEDED_BY_CLI=1
        return 1
    fi
    return 0
  fi
  if authority="$(capture_cli_removal_authority)"; then
    IFS=$'\t' read -r cli_expected receipt_expected <<< "$authority"
    backup="$(mktemp "$(dirname "$CLI_PATH")/.sia.removed.XXXXXX")" \
      || return 1
    rm -f -- "$backup"
    if ! archived="$(owned_file_cas archive "$backup" "$CLI_PATH" \
        "$cli_expected")"; then
      [ ! -e "$backup" ] \
        || echo "prior SIA CLI retained at $backup" >&2
      failed "remove owned SIA CLI"
      RUNTIME_NEEDED_BY_CLI=1
      return 1
    fi
    if ! remove_managed_metadata "$CLI_RECEIPT" "$receipt_expected"; then
      echo "exact prior SIA CLI retained at $backup" >&2
      failed "remove SIA CLI ownership receipt"
      RUNTIME_NEEDED_BY_CLI=1
      return 1
    fi
    if [ -e "$CLI_PATH" ] || [ -L "$CLI_PATH" ]; then
      echo "a newer SIA CLI publication was preserved" >&2
      echo "exact prior SIA CLI retained at $backup" >&2
      failed "verify SIA CLI remained absent after receipt archival"
      RUNTIME_NEEDED_BY_CLI=1
      return 1
    fi
    echo "exact prior SIA CLI retained at $backup"
  else
    echo "existing SIA CLI preserved (unowned or locally modified)"
    RUNTIME_NEEDED_BY_CLI=1
  fi
}
archive_owned_runtime() {
  local archived authority backup receipt_expected receipt_before
  local runtime_expected runtime_state
  if [ ! -e "$RUNTIME_BIN_DIR" ] && [ ! -L "$RUNTIME_BIN_DIR" ]; then
    if [ ! -e "$RUNTIME_RECEIPT" ] && [ ! -L "$RUNTIME_RECEIPT" ]; then
      return 0
    fi
    receipt_expected="$(owned_metadata managed-receipt-generation \
      "$RUNTIME_RECEIPT" runtime "$RUNTIME_BIN_DIR")" || {
      echo "stale or malformed runtime receipt preserved" >&2
      RUNTIME_UNOWNED=1
      return 1
    }
    receipt_before="$(owned_metadata managed-receipt-generation \
      "$RUNTIME_RECEIPT" runtime "$RUNTIME_BIN_DIR")" || return 1
    if [ "$receipt_before" != "$receipt_expected" ] \
        || ! remove_managed_metadata "$RUNTIME_RECEIPT" "$receipt_expected"; then
        RUNTIME_UNOWNED=1
        return 1
    fi
    return 0
  fi
  if ! authority="$(capture_runtime_removal_authority)"; then
    echo "SIA runtime preserved (unowned, locally modified, or invalid receipt)" >&2
    RUNTIME_UNOWNED=1
    return 0
  fi
  IFS=$'\t' read -r runtime_expected receipt_expected <<< "$authority"
  backup="$(mktemp -d "$SHARE_DIR/.bin.removed.XXXXXX")"
  rmdir -- "$backup"
  if ! archived="$(owned_tree_cas archive "$RUNTIME_BIN_DIR" "$backup" \
      "$runtime_expected")"; then
    [ ! -e "$backup" ] \
      || echo "exact prior runtime retained at $backup" >&2
    failed "archive SIA runtime"
    RUNTIME_UNOWNED=1
    return 1
  fi
  if ! restore_runtime_archive_fence_modes "$backup"; then
    echo "exact prior runtime retained at $backup" >&2
    failed "restore archived runtime launch modes"
    RUNTIME_UNOWNED=1
    return 1
  fi
  if ! remove_managed_metadata "$RUNTIME_RECEIPT" "$receipt_expected"; then
    echo "exact prior runtime retained at $backup" >&2
    failed "remove SIA runtime ownership receipt"
    RUNTIME_UNOWNED=1
    return 1
  fi
  runtime_state="$(owned_tree_generation "$RUNTIME_BIN_DIR" 2>/dev/null \
    || true)"
  if [ "$runtime_state" != absent ]; then
    echo "a newer runtime publication was preserved" >&2
    echo "exact prior runtime retained at $backup" >&2
    failed "verify runtime remained absent after receipt archival"
    RUNTIME_UNOWNED=1
    return 1
  fi
  echo "managed runtime archived at $backup"
}

remove_owned_gbrain_pin() {
  local archived authority backup pin_expected receipt_before
  local receipt_expected
  if [ ! -e "$GBRAIN_PIN_PATH" ] && [ ! -L "$GBRAIN_PIN_PATH" ]; then
    if [ ! -e "$GBRAIN_PIN_RECEIPT" ] \
        && [ ! -L "$GBRAIN_PIN_RECEIPT" ]; then
      return 0
    fi
    owned_file_cas recover "$GBRAIN_PIN_RECEIPT" || return 1
    receipt_expected="$(owned_metadata managed-receipt-generation \
      "$GBRAIN_PIN_RECEIPT" gbrain-pin "$GBRAIN_PIN_PATH")" || {
      echo "stale or malformed gbrain pin receipt preserved" >&2
      return 1
    }
    receipt_before="$(owned_metadata managed-receipt-generation \
      "$GBRAIN_PIN_RECEIPT" gbrain-pin "$GBRAIN_PIN_PATH")" || return 1
    [ "$receipt_before" = "$receipt_expected" ] \
      && remove_managed_metadata \
        "$GBRAIN_PIN_RECEIPT" "$receipt_expected"
    return
  fi
  owned_file_cas recover "$GBRAIN_PIN_PATH" || return 1
  owned_file_cas recover "$GBRAIN_PIN_RECEIPT" || return 1
  authority="$(capture_managed_file_authority \
    "$GBRAIN_PIN_RECEIPT" gbrain-pin "$GBRAIN_PIN_PATH")" || {
      echo "installed gbrain pin preserved (unowned or locally modified)" >&2
      return 1
    }
  IFS=$'\t' read -r pin_expected receipt_expected <<< "$authority"
  backup="$(mktemp "$SHARE_DIR/.GBRAIN_PIN.removed.XXXXXX")" || return 1
  rm -f -- "$backup"
  if ! archived="$(owned_file_cas archive "$backup" "$GBRAIN_PIN_PATH" \
      "$pin_expected")"; then
    [ ! -e "$backup" ] \
      || echo "exact prior gbrain pin retained at $backup" >&2
    return 1
  fi
  if ! remove_managed_metadata \
      "$GBRAIN_PIN_RECEIPT" "$receipt_expected"; then
    echo "exact prior gbrain pin retained at $backup" >&2
    return 1
  fi
  if [ -e "$GBRAIN_PIN_PATH" ] || [ -L "$GBRAIN_PIN_PATH" ]; then
    echo "a newer gbrain pin publication was preserved" >&2
    echo "exact prior gbrain pin retained at $backup" >&2
    return 1
  fi
  echo "exact prior gbrain pin retained at $backup"
}

mcp_marker_state() {
  local client="$1" marker state legacy pending committed
  marker="$MCP_MARKER_DIR/$client"
  if [ ! -e "$marker" ] && [ ! -L "$marker" ]; then
    echo none
    return 0
  fi
  if [ ! -f "$marker" ] || [ -L "$marker" ]; then
    echo invalid
    return 0
  fi
  legacy="$(printf 'managed-by=khephri.sia\ncommand=python3\narg=%s/sia-mcp' \
    "$RUNTIME_BIN_DIR")"
  pending="$(printf 'managed-by=khephri.sia\nstate=pending-add\ncommand=python3\narg=%s/sia-mcp' \
    "$RUNTIME_BIN_DIR")"
  committed="$(printf 'managed-by=khephri.sia\nstate=committed\ncommand=python3\narg=%s/sia-mcp' \
    "$RUNTIME_BIN_DIR")"
  if state="$(owned_metadata classify "$marker" \
      legacy "$legacy" pending "$pending" committed "$committed")"; then
    printf '%s\n' "$state"
  else
    echo invalid
  fi
}

mcp_consumer_guard_state() {
  local client="$1" guard state prefix
  guard="$MCP_GUARD_DIR/$client"
  if [ ! -e "$guard" ] && [ ! -L "$guard" ]; then
    echo none
    return 0
  fi
  if [ ! -f "$guard" ] || [ -L "$guard" ]; then
    echo invalid
    return 0
  fi
  prefix="$(printf 'guarded-by=khephri.sia\nkind=external-mcp-consumer\nconsumer=%s\nownership=external\ncommand=python3\narg=%s/sia-mcp\nreason=' \
    "$client" "$RUNTIME_BIN_DIR")"
  if state="$(owned_metadata classify "$guard" \
      guarded "${prefix}exact-unmarked" \
      guarded "${prefix}modified-reference")"; then
    printf '%s\n' "$state"
  else
    echo invalid
  fi
}

# Non-ownership guards use the shared journaled NOREPLACE front door and an
# exact absent/current generation validated by the caller.
durable_replace_file() {
  owned_file_cas publish "$1" "$2" "$3" >/dev/null
}

write_mcp_consumer_guard() {
  local client="$1" reason="$2" state guard temporary expected after
  case "$client" in claude|codex|grok) ;; *) return 1 ;; esac
  case "$reason" in exact-unmarked|modified-reference) ;; *) return 1 ;; esac
  state="$(mcp_consumer_guard_state "$client")"
  [ "$state" != invalid ] || return 1
  mkdir -p "$MCP_GUARD_DIR" || return 1
  guard="$MCP_GUARD_DIR/$client"
  case "$state" in
    none) expected=absent ;;
    guarded) expected="$(owned_metadata generation "$guard")" || return 1 ;;
    *) return 1 ;;
  esac
  after="$(mcp_consumer_guard_state "$client")"
  [ "$after" = "$state" ] || return 1
  if [ "$expected" != absent ]; then
    [ "$(owned_metadata generation "$guard" 2>/dev/null || true)" \
      = "$expected" ] || return 1
  fi
  temporary="$(mktemp "$MCP_GUARD_DIR/.${client}.tmp.XXXXXX")" || return 1
  if ! printf 'guarded-by=khephri.sia\nkind=external-mcp-consumer\nconsumer=%s\nownership=external\ncommand=python3\narg=%s/sia-mcp\nreason=%s\n' \
      "$client" "$RUNTIME_BIN_DIR" "$reason" > "$temporary" \
      || ! chmod 0600 "$temporary" \
      || ! durable_replace_file "$temporary" "$guard" "$expected"; then
    [ ! -e "$temporary" ] \
      || echo "staged/prior MCP guard retained at $temporary" >&2
    return 1
  fi
}

# Any entry in this directory is also a generic operator-facing keep-runtime
# guard for an MCP client SIA does not know how to inspect. It is deliberately
# presence-based and never auto-removed: an unknown or malformed entry fails
# safe by preserving the CLI/runtime until the operator retires the consumer.
apply_generic_mcp_consumer_guards() {
  local first
  if [ ! -e "$MCP_GUARD_DIR" ] && [ ! -L "$MCP_GUARD_DIR" ]; then
    return 0
  fi
  if [ ! -d "$MCP_GUARD_DIR" ] || [ -L "$MCP_GUARD_DIR" ]; then
    failed "inspect durable MCP consumer guards"
    RUNTIME_NEEDED_BY_MCP=1
    return 0
  fi
  if ! first="$(find "$MCP_GUARD_DIR" -mindepth 1 -maxdepth 1 -print -quit)"; then
    failed "inspect durable MCP consumer guards"
    RUNTIME_NEEDED_BY_MCP=1
  elif [ -n "$first" ]; then
    echo "durable external MCP consumer guard(s) preserve the SIA CLI and runtime"
    echo "  guards: $MCP_GUARD_DIR"
    RUNTIME_NEEDED_BY_MCP=1
  fi
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
  local client="$1" inspection
  case "$client" in
    claude|codex)
      if inspection="$(bounded_command_capture \
          "$client" mcp get sia)"; then
        parse_text_mcp_inspection "$client" "$RUNTIME_BIN_DIR/sia-mcp" \
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
      else
        printf '%s' "$inspection" | python3 -c \
          'import json,sys; p=sys.argv[1]
try: xs=json.load(sys.stdin); assert isinstance(xs,list)
except Exception: print("indeterminate"); raise SystemExit
rows=[x for x in xs if isinstance(x,dict) and x.get("name")=="sia"]
if not rows: print("absent")
elif len(rows)==1:
 x=rows[0]; allowed={"name","command","args","enabled","scope","transport","env","cwd"}; exact=(set(x)<=allowed and x.get("command")=="python3" and x.get("args")==[p] and not x.get("env") and not x.get("cwd") and x.get("transport","stdio")=="stdio" and x.get("enabled") is True and x.get("scope")=="user"); print("match" if exact else "reference" if p in json.dumps(x) else "mismatch")
else: print("reference" if p in json.dumps(rows) else "mismatch")' \
          "$RUNTIME_BIN_DIR/sia-mcp"
      fi
      ;;
  esac
}

print_mcp_remove_command() {
  case "$1" in
    claude) echo "  claude mcp remove --scope user sia" ;;
    codex) echo "  codex mcp remove sia" ;;
    grok) echo "  grok mcp remove --scope user sia" ;;
  esac
}

remove_mcp_marker_checked() {
  local client="$1" marker="$MCP_MARKER_DIR/$1" state_before state_after
  local expected after
  state_before="$(mcp_marker_state "$client")" || return 1
  case "$state_before" in legacy|pending|committed) ;; *) return 1 ;; esac
  expected="$(owned_metadata generation "$marker")" || return 1
  state_after="$(mcp_marker_state "$client")" || return 1
  after="$(owned_metadata generation "$marker")" || return 1
  if [ "$state_after" = "$state_before" ] && [ "$after" = "$expected" ] \
      && remove_managed_metadata "$marker" "$expected"; then
    return 0
  fi
  failed "remove $client MCP ownership marker"
  RUNTIME_NEEDED_BY_MCP=1
  return 1
}

remove_managed_mcp() {
  local client="$1" marker marker_state guard_state state
  marker="$MCP_MARKER_DIR/$client"
  marker_state="$(mcp_marker_state "$client")"
  guard_state="$(mcp_consumer_guard_state "$client")"
  case "$guard_state" in
    guarded)
      echo "$client MCP registration preserved by its durable non-ownership guard"
      RUNTIME_NEEDED_BY_MCP=1
      return 0
      ;;
    invalid)
      echo "invalid $client MCP non-ownership guard preserved" >&2
      failed "validate $client MCP non-ownership guard"
      RUNTIME_NEEDED_BY_MCP=1
      return 0
      ;;
    none) ;;
    *)
      failed "parse $client MCP non-ownership guard"
      RUNTIME_NEEDED_BY_MCP=1
      return 0
      ;;
  esac
  if ! have "$client"; then
    if [ "$marker_state" != none ]; then
      echo "$client harness unavailable; MCP registration and runtime preserved"
      RUNTIME_NEEDED_BY_MCP=1
      failed "inspect $client MCP registration"
    fi
    return 0
  fi
  state="$(inspect_mcp_server "$client")"
  case "$state" in
    absent)
      if [ "$marker_state" = invalid ]; then
        echo "invalid $client MCP marker preserved" >&2
        failed "validate $client MCP ownership marker"
        RUNTIME_NEEDED_BY_MCP=1
      elif [ "$marker_state" != none ]; then
        remove_mcp_marker_checked "$client" || true
      fi
      ;;
    match)
      case "$marker_state" in
        committed|pending|legacy)
          echo "$client MCP registration is exact, but the client has no compare-and-remove API; preserved"
          echo "remove it manually, then rerun uninstall:"
          print_mcp_remove_command "$client"
          RUNTIME_NEEDED_BY_MCP=1
          ;;
        *)
          if ! write_mcp_consumer_guard "$client" exact-unmarked; then
            failed "record $client MCP non-ownership guard"
          fi
          echo "exact unowned $client MCP registration preserved"
          RUNTIME_NEEDED_BY_MCP=1
          ;;
      esac
      ;;
    reference)
      case "$marker_state" in
        none)
          if ! write_mcp_consumer_guard "$client" modified-reference; then
            failed "record $client MCP non-ownership guard"
          fi
          echo "$client MCP registration still references SIA but is not an exact owned shape; preserved"
          ;;
        pending|committed|legacy)
          # The client may only have changed its display format. A reference
          # alone cannot prove that an installer-owned registration became an
          # external consumer, so retain ownership metadata and fail closed.
          echo "$client MCP registration references SIA but no longer verifies exactly; owned marker retained" >&2
          failed "resolve $client MCP registration ownership"
          ;;
        invalid)
          echo "invalid $client MCP ownership marker preserved beside a non-exact SIA reference" >&2
          failed "validate $client MCP ownership marker"
          ;;
        *) failed "parse $client MCP ownership marker" ;;
      esac
      RUNTIME_NEEDED_BY_MCP=1
      ;;
    mismatch)
      echo "$client MCP registration is unrelated; preserved"
      ;;
    indeterminate)
      failed "inspect $client MCP registration"
      RUNTIME_NEEDED_BY_MCP=1
      ;;
    *)
      failed "parse $client MCP registration"
      RUNTIME_NEEDED_BY_MCP=1
      ;;
  esac
}
remove_managed_skill() {
  local skill_expected marker_expected skill_archive marker_archive generations
  if [ ! -e "$SKILL_DIR" ] && [ ! -L "$SKILL_DIR" ]; then
    return 0
  fi
  if [ -d "$SKILL_DIR" ] && [ ! -L "$SKILL_DIR" ]; then
    owned_file_cas recover "$SKILL_FILE" || {
      failed "recover interrupted agent skill update"
      return 1
    }
    owned_file_cas recover "$SKILL_MARKER" || {
      failed "recover interrupted agent skill marker update"
      return 1
    }
  fi
  if [ -d "$SKILL_DIR" ] && [ ! -L "$SKILL_DIR" ] \
      && [ -f "$SKILL_FILE" ] && [ ! -L "$SKILL_FILE" ] \
      && [ -f "$SKILL_MARKER" ] && [ ! -L "$SKILL_MARKER" ] \
      && generations="$(owned_metadata skill-generations \
        "$SKILL_MARKER" "$SKILL_FILE")"; then
    IFS=$'\t' read -r skill_expected marker_expected <<< "$generations"
    skill_archive="$(mktemp "$SKILL_DIR/.SKILL.md.removed.XXXXXX")"
    marker_archive="$(mktemp "$SKILL_DIR/.sia-managed.removed.XXXXXX")"
    rm -f -- "$skill_archive" "$marker_archive"
    if ! owned_file_cas archive "$marker_archive" "$SKILL_MARKER" \
        "$marker_expected"; then
      rm -f -- "$skill_archive" "$marker_archive"
      echo "existing agent skill marker changed concurrently; preserved"
      return 1
    fi
    if ! owned_file_cas archive "$skill_archive" "$SKILL_FILE" \
        "$skill_expected"; then
      echo "agent skill changed concurrently; preserved" >&2
      echo "its prior ownership marker is retained at $marker_archive" >&2
      rm -f -- "$skill_archive"
      return 1
    fi
    rm -f -- "$skill_archive" "$marker_archive" || return 1
    rmdir -- "$SKILL_DIR" 2>/dev/null || true
    return 0
  fi
  echo "existing agent skill preserved (unmanaged or locally modified)"
  return 0
}

binding_block_state() {
  owned_metadata binding-state "$1"
}

remove_managed_binding() {
  local bindings="$1" state parent stage expected installed config_errors
  if [ -d "$(dirname "$bindings")" ]; then
    owned_file_cas recover "$bindings" || {
      failed "recover interrupted Hyprland binding update"
      return 0
    }
  fi
  if [ ! -e "$bindings" ] && [ ! -L "$bindings" ]; then
    return 0
  fi
  if [ ! -f "$bindings" ] || [ -L "$bindings" ]; then
    failed "preserve unsafe Hyprland bindings path"
    return 0
  fi
  if ! state="$(binding_block_state "$bindings")"; then
    failed "inspect managed Hyprland keybinding"
    return 0
  fi
  case "$state" in
    absent) return 0 ;;
    unsafe)
      echo "incomplete, duplicated, or malformed SIA keybinding markers preserved" >&2
      failed "preserve malformed managed Hyprland keybinding"
      return 0
      ;;
    managed) ;;
    *) failed "inspect managed Hyprland keybinding"; return 0 ;;
  esac

  parent="$(dirname "$bindings")"
  stage="$(mktemp "$parent/.bindings.lua.sia-uninstall-stage.XXXXXX")"
  expected="$(owned_metadata generation "$bindings")" || {
    rm -f -- "$stage"
    failed "capture managed Hyprland keybinding generation"
    return 0
  }
  if ! cp -a -- "$bindings" "$stage"; then
    rm -f -- "$stage"
    failed "stage managed Hyprland keybinding removal"
    return 0
  fi
  if ! python3 - "$stage" <<'PY'
import sys

target = sys.argv[1]
with open(target, encoding="utf-8") as stream:
    lines = stream.readlines()
stripped = [line.strip() for line in lines]
begins = [index for index, line in enumerate(stripped)
          if line in {"-- BEGIN SIA",
                      "-- BEGIN SIA (managed by khephri.sia/install.sh)"}]
ends = [index for index, line in enumerate(stripped)
        if line == "-- END SIA"]
if len(begins) != 1 or len(ends) != 1 or begins[0] >= ends[0]:
    raise SystemExit("managed SIA marker pair changed during removal")
start = begins[0]
if start and not stripped[start - 1]:
    start -= 1
with open(target, "w", encoding="utf-8") as stream:
    stream.writelines(lines[:start] + lines[ends[0] + 1:])
    stream.flush()
PY
  then
    rm -f -- "$stage"
    failed "remove managed Hyprland keybinding"
    return 0
  fi
  if ! installed="$(owned_file_cas publish "$stage" "$bindings" \
      "$expected")"; then
    [ ! -e "$stage" ] || echo "staged/prior bindings retained at $stage" >&2
    failed "install Hyprland bindings without the managed SIA block"
    return 0
  fi

  if have hyprctl && [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]; then
    if ! run_with_deadline 120 hyprctl reload; then
      if owned_file_cas publish "$stage" "$bindings" "$installed" \
          >/dev/null; then
        rm -f -- "$stage"
        if ! run_with_deadline 120 hyprctl reload >/dev/null 2>&1; then
          failed "reload restored Hyprland bindings"
        fi
      else
        echo "original bindings retained at $stage" >&2
        failed "CAS-restore Hyprland bindings after reload failure"
      fi
      failed "reload Hyprland configuration"
      return 0
    fi
    if ! config_errors="$(bounded_command_capture hyprctl configerrors)" \
        || [ -n "$config_errors" ]; then
      printf '%s\n' "$config_errors" >&2
      if owned_file_cas publish "$stage" "$bindings" "$installed" \
          >/dev/null; then
        rm -f -- "$stage"
        if ! run_with_deadline 120 hyprctl reload >/dev/null 2>&1; then
          failed "reload restored Hyprland bindings"
        fi
      else
        echo "original bindings retained at $stage" >&2
        failed "CAS-restore Hyprland bindings after validation failure"
      fi
      failed "validate Hyprland configuration"
      return 0
    fi
  else
    echo "managed keybinding removed; Hyprland reload skipped (no active session)"
  fi
  rm -f -- "$stage"
}

if have systemctl; then
  preflight_continuity_archive_intents || true
  preflight_continuity_units_for_uninstall
  BRAINSTEM_BARRIER_STATE="$(brainstem_runtime_barrier_file state)" || exit 1
  BRAINSTEM_EXPECTED_DROP_IN=""
  case "$BRAINSTEM_BARRIER_STATE" in
    active)
      SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED=1
      run_with_deadline 120 systemctl --user daemon-reload || exit 1
      if [ -e "$UNIT_PATH" ] || [ -L "$UNIT_PATH" ]; then
        BRAINSTEM_EXPECTED_DROP_IN="$BRAINSTEM_RUNTIME_BARRIER"
      fi
      ;;
    retired)
      SIA_BRAINSTEM_RETIRED_BARRIER_PRESENT=1
      run_with_deadline 120 systemctl --user daemon-reload || exit 1
      ;;
    absent) ;;
    *) echo "unexpected sia-brainstem barrier state" >&2; exit 1 ;;
  esac
  if ! inspect_user_unit sia-brainstem.service BRAINSTEM_INSPECT \
      "$BRAINSTEM_EXPECTED_DROP_IN"; then
    failed "inspect sia-brainstem.service state"
    BRAINSTEM_SAFE_TO_REMOVE=0
    RUNTIME_NEEDED_BY_SERVICE=1
  elif UNIT_AUTHORITY="$(capture_managed_file_authority \
        "$UNIT_RECEIPT" brainstem-unit "$UNIT_PATH")" \
      && { { [ "$BRAINSTEM_INSPECT_LOAD_STATE" = loaded ] \
             && [ "$BRAINSTEM_INSPECT_FRAGMENT_PATH" = "$UNIT_PATH" ]; } \
           || { [ "$BRAINSTEM_INSPECT_LOAD_STATE" = not-found ] \
                && [ "$BRAINSTEM_INSPECT_ACTIVE_STATE" = inactive ] \
                && [ -z "$BRAINSTEM_INSPECT_FRAGMENT_PATH" ] \
                && [ -z "$BRAINSTEM_INSPECT_UNIT_FILE_STATE" ]; }; }; then
    IFS=$'\t' read -r UNIT_TARGET_EXPECTED UNIT_RECEIPT_EXPECTED \
      <<< "$UNIT_AUTHORITY"
    UNIT_OWNED=1
  elif [ -e "$UNIT_PATH" ] || [ -L "$UNIT_PATH" ] \
      || [ -e "$UNIT_RECEIPT" ] || [ -L "$UNIT_RECEIPT" ] \
      || [ "$BRAINSTEM_INSPECT_LOAD_STATE" != not-found ] \
      || [ "$BRAINSTEM_INSPECT_ACTIVE_STATE" != inactive ] \
      || [ -n "$BRAINSTEM_INSPECT_FRAGMENT_PATH" ] \
      || [ -n "$BRAINSTEM_INSPECT_UNIT_FILE_STATE" ]; then
    failed "preserve unowned or modified sia-brainstem.service"
    BRAINSTEM_SAFE_TO_REMOVE=0
    RUNTIME_NEEDED_BY_SERVICE=1
  fi
else
  failed "systemctl unavailable; sia-brainstem.service may still be running"
  BRAINSTEM_SAFE_TO_REMOVE=0
  RUNTIME_NEEDED_BY_SERVICE=1
  CONTINUITY_SAFE_TO_REMOVE=0
  RUNTIME_NEEDED_BY_CONTINUITY=1
fi

if [ "$CONTINUITY_SAFE_TO_REMOVE" -eq 1 ]; then
  if ! quiesce_continuity_units_for_uninstall; then
    failed "quiesce exact SIA continuity timers and services"
    CONTINUITY_SAFE_TO_REMOVE=0
    RUNTIME_NEEDED_BY_CONTINUITY=1
  fi
else
  echo "SIA continuity units preserved because ownership or manager state is indeterminate" >&2
fi

if [ "$UNIT_OWNED" -eq 1 ] && [ "$BRAINSTEM_SAFE_TO_REMOVE" -eq 1 ]; then
  if ! install_uninstall_brainstem_runtime_barrier; then
    failed "install exact sia-brainstem.service runtime start barrier"
    BRAINSTEM_SAFE_TO_REMOVE=0
    RUNTIME_NEEDED_BY_SERVICE=1
  fi
fi

acquire_uninstall_lifecycle || exit 1

# The first stop/disable pass lets an in-flight scheduled command release its
# shared lifecycle lease.  Repeat under EX so no admitted client can race the
# receipt-bound unit archives that follow.
if [ "$CONTINUITY_SAFE_TO_REMOVE" -eq 1 ]; then
  if ! recover_continuity_archive_intents; then
    failed "recover interrupted SIA continuity unit and receipt archives"
    CONTINUITY_SAFE_TO_REMOVE=0
    RUNTIME_NEEDED_BY_CONTINUITY=1
  elif ! quiesce_continuity_units_for_uninstall; then
    failed "revalidate quiesced SIA continuity units under lifecycle EX"
    CONTINUITY_SAFE_TO_REMOVE=0
    RUNTIME_NEEDED_BY_CONTINUITY=1
  elif ! archive_owned_continuity_units; then
    failed "archive exact SIA continuity units and receipts"
    CONTINUITY_SAFE_TO_REMOVE=0
    RUNTIME_NEEDED_BY_CONTINUITY=1
  fi
fi

if [ "$BRAINSTEM_SAFE_TO_REMOVE" -eq 1 ] \
    && { [ -e "$SHARE_DIR" ] || [ -e "$STATE_DIR" ] \
         || [ -e "$CLI_PATH" ]; }; then
  if ! mkdir -p "$STATE_DIR" || ! assert_safe_managed_roots "$STATE_DIR"; then
    failed "prepare SIA owner leases"
    BRAINSTEM_SAFE_TO_REMOVE=0
    RUNTIME_NEEDED_BY_SERVICE=1
  fi
  if [ "$BRAINSTEM_SAFE_TO_REMOVE" -eq 1 ]; then
    acquire_owner_lock "$STATE_DIR/brainstem-owner.lock" \
      SIA_BRAINSTEM_LOCK_FD brainstem || BRAINSTEM_SAFE_TO_REMOVE=0
  fi
  if [ "$BRAINSTEM_SAFE_TO_REMOVE" -eq 1 ]; then
    acquire_owner_lock "$STATE_DIR/corpus-owner.lock" \
      SIA_CORPUS_LOCK_FD "corpus transaction" || BRAINSTEM_SAFE_TO_REMOVE=0
  fi
  if [ "$BRAINSTEM_SAFE_TO_REMOVE" -eq 1 ]; then
    acquire_owner_lock "$STATE_DIR/gbrain-owner.lock" \
      SIA_GBRAIN_LOCK_FD PGLite || BRAINSTEM_SAFE_TO_REMOVE=0
  fi
  if [ "$BRAINSTEM_SAFE_TO_REMOVE" -eq 0 ]; then
    RUNTIME_NEEDED_BY_SERVICE=1
  fi
fi

if [ "$BRAINSTEM_SAFE_TO_REMOVE" -eq 1 ]; then
  # An interrupted installer may have published the exact new runtime/CLI
  # before its receipts. Recover only journal-attested bytes while EX and all
  # available data-owner leases exclude modern clients.
  recover_publication_receipts_from_fence || {
    failed "recover interrupted SIA publication"
    exit 1
  }
  # First drain catches legacy processes that predate lifecycle leases. Then a
  # durable tombstone plus mode-000 journal fence closes admission through the
  # old CLI, direct brainstem, and resident MCP paths. The second drain proves
  # every process admitted before that fence has left before mutation begins.
  drain_legacy_launchers || {
    failed "quiesce legacy SIA launchers before uninstall fence"
    exit 1
  }
  write_lifecycle_tombstone || {
    failed "write uninstall lifecycle marker"
    exit 1
  }
  arm_uninstall_launch_fence || {
    failed "arm uninstall legacy-launch fence"
    exit 1
  }
  drain_legacy_launchers || {
    failed "quiesce legacy SIA launchers after uninstall fence"
    exit 1
  }
fi

if [ -e "$PLUGIN_DIR" ] || [ -L "$PLUGIN_DIR" ]; then
  if ! owned_tree_cas recover "$PLUGIN_DIR" \
      || ! PLUGIN_EXPECTED="$(owned_tree_generation "$PLUGIN_DIR")"; then
    failed "capture installed plugin tree generation"
    PLUGIN_SAFE_TO_ARCHIVE=0
    RUNTIME_NEEDED_BY_PLUGIN=1
  elif have omarchy; then
    if ! run_with_deadline 120 omarchy plugin disable khephri.sia; then
      failed "disable Omarchy plugin khephri.sia"
      PLUGIN_SAFE_TO_ARCHIVE=0
      RUNTIME_NEEDED_BY_PLUGIN=1
    fi
  else
    failed "disable Omarchy plugin khephri.sia (omarchy unavailable)"
    PLUGIN_SAFE_TO_ARCHIVE=0
    RUNTIME_NEEDED_BY_PLUGIN=1
  fi
fi
remove_managed_mcp claude
remove_managed_mcp codex
remove_managed_mcp grok
apply_generic_mcp_consumer_guards
rmdir -- "$MCP_MARKER_DIR" 2>/dev/null || true

if [ "$UNIT_OWNED" -eq 1 ] && [ "$BRAINSTEM_SAFE_TO_REMOVE" -eq 1 ]; then
  UNIT_BACKUP="$(mktemp "$(dirname "$UNIT_PATH")/.sia-brainstem.removed.XXXXXX")"
  rm -f -- "$UNIT_BACKUP"
  if ! _UNIT_ARCHIVED="$(owned_file_cas archive "$UNIT_BACKUP" \
      "$UNIT_PATH" "$UNIT_TARGET_EXPECTED")"; then
    [ ! -e "$UNIT_BACKUP" ] \
      || echo "exact prior brainstem unit retained at $UNIT_BACKUP" >&2
    failed "remove owned sia-brainstem.service unit"
    RUNTIME_NEEDED_BY_SERVICE=1
  elif ! run_with_deadline 120 systemctl --user daemon-reload; then
    echo "exact prior brainstem unit retained at $UNIT_BACKUP" >&2
    run_with_deadline 120 systemctl --user daemon-reload \
      >/dev/null 2>&1 || true
    failed "reload systemd after archiving owned sia-brainstem.service unit"
    RUNTIME_NEEDED_BY_SERVICE=1
  elif ! remove_managed_metadata \
      "$UNIT_RECEIPT" "$UNIT_RECEIPT_EXPECTED"; then
    echo "exact prior brainstem unit retained at $UNIT_BACKUP" >&2
    run_with_deadline 120 systemctl --user daemon-reload \
      >/dev/null 2>&1 || true
    failed "remove sia-brainstem.service ownership receipt"
    RUNTIME_NEEDED_BY_SERVICE=1
  elif [ -e "$UNIT_PATH" ] || [ -L "$UNIT_PATH" ]; then
    echo "a newer brainstem unit publication was preserved" >&2
    echo "exact prior brainstem unit retained at $UNIT_BACKUP" >&2
    failed "verify brainstem unit remained absent after receipt archival"
    RUNTIME_NEEDED_BY_SERVICE=1
  else
    echo "exact prior brainstem unit retained at $UNIT_BACKUP"
  fi
elif [ -e "$UNIT_PATH" ] || [ -L "$UNIT_PATH" ]; then
  echo "sia-brainstem.service unit preserved for recovery" >&2
fi

PLUGIN_BACKUP=""
if [ "$PLUGIN_SAFE_TO_ARCHIVE" -eq 1 ] \
    && { [ -e "$PLUGIN_DIR" ] || [ -L "$PLUGIN_DIR" ]; }; then
  PLUGIN_PARENT="$(dirname "$PLUGIN_DIR")"
  PLUGIN_BACKUP="$(mktemp -d "$PLUGIN_PARENT/.khephri.sia.removed.XXXXXX")"
  rmdir -- "$PLUGIN_BACKUP"
  if ! _PLUGIN_ARCHIVED="$(owned_tree_cas archive "$PLUGIN_DIR" \
      "$PLUGIN_BACKUP" "$PLUGIN_EXPECTED")"; then
    [ ! -e "$PLUGIN_BACKUP" ] \
      || echo "exact prior plugin tree retained at $PLUGIN_BACKUP" >&2
    failed "archive installed plugin tree"
    RUNTIME_NEEDED_BY_PLUGIN=1
  elif [ -e "$PLUGIN_DIR" ] || [ -L "$PLUGIN_DIR" ]; then
    echo "a newer plugin publication was preserved" >&2
    echo "exact prior plugin tree retained at $PLUGIN_BACKUP" >&2
    failed "verify plugin tree remained absent after archival"
    RUNTIME_NEEDED_BY_PLUGIN=1
  fi
fi

if [ "$PLUGIN_SAFE_TO_ARCHIVE" -eq 1 ] \
    && [ "$RUNTIME_NEEDED_BY_PLUGIN" -eq 0 ]; then
  remove_managed_binding "$BINDINGS_PATH"
else
  echo "managed keybinding preserved because the plugin remains enabled/installed" >&2
fi

if [ "$RUNTIME_NEEDED_BY_SERVICE" -eq 0 ] \
    && [ "$RUNTIME_NEEDED_BY_CONTINUITY" -eq 0 ] \
    && [ "$RUNTIME_NEEDED_BY_MCP" -eq 0 ] \
    && [ "$RUNTIME_NEEDED_BY_PLUGIN" -eq 0 ]; then
  attempt "remove SIA CLI" remove_owned_cli
  if [ "$RUNTIME_NEEDED_BY_CLI" -eq 0 ]; then
    attempt "archive SIA runtime modules" archive_owned_runtime
    if [ "$RUNTIME_UNOWNED" -eq 0 ]; then
      attempt "remove installed gbrain pin and receipt" \
        remove_owned_gbrain_pin
    fi
  else
    echo "SIA runtime preserved for the surviving CLI" >&2
  fi
else
  echo "SIA CLI and runtime preserved for surviving or indeterminate consumers" >&2
fi
attempt "remove managed SIA skill" remove_managed_skill

if [ "$PURGE" -eq 1 ]; then
  if [ "${#FAILURES[@]}" -ne 0 ]; then
    failed "purge blocked because uninstall integrations did not all complete"
    echo "purge was not attempted; resolve the listed failures and retry" >&2
  elif [ "$RUNTIME_NEEDED_BY_SERVICE" -eq 1 ] \
      || [ "$RUNTIME_NEEDED_BY_CONTINUITY" -eq 1 ] \
      || [ "$RUNTIME_NEEDED_BY_MCP" -eq 1 ] \
      || [ "$RUNTIME_NEEDED_BY_PLUGIN" -eq 1 ] \
      || [ "$RUNTIME_NEEDED_BY_CLI" -eq 1 ] \
      || [ "$RUNTIME_UNOWNED" -eq 1 ]; then
    failed "purge blocked because a surviving integration still needs SIA"
    echo "purge was not attempted; remove the surviving consumer and retry" >&2
  else
    if [ -L "$LIFECYCLE_TOMBSTONE" ] \
        || { [ -e "$LIFECYCLE_TOMBSTONE" ] \
             && [ ! -f "$LIFECYCLE_TOMBSTONE" ]; }; then
      failed "write lifecycle removal marker at an unsafe path"
    elif ! write_lifecycle_tombstone; then
      failed "write lifecycle removal marker"
    elif ! purge_fixed_publication_stages \
        "$STATE_PUBLICATION_STAGE" "$SHARE_PUBLICATION_STAGE"; then
      failed "purge fixed SIA publication stages"
      echo "purge was not attempted because a fixed publication stage is unsafe" >&2
    else
      attempt "purge retained SIA state" safe_remove_tree "$STATE_DIR"
      attempt "purge retained SIA continuity state" \
        safe_remove_tree "$CONTINUITY_STATE_DIR"
      attempt "purge retained SIA memory" safe_remove_tree "$SHARE_DIR"
      attempt "purge SIA operator configuration" safe_remove_tree "$CONFIG_DIR"
    fi
    if { [ ! -e "$STATE_DIR" ] && [ ! -L "$STATE_DIR" ]; } \
        && { [ ! -e "$CONTINUITY_STATE_DIR" ] \
             && [ ! -L "$CONTINUITY_STATE_DIR" ]; } \
        && { [ ! -e "$SHARE_DIR" ] && [ ! -L "$SHARE_DIR" ]; } \
        && { [ ! -e "$CONFIG_DIR" ] && [ ! -L "$CONFIG_DIR" ]; } \
        && { [ ! -e "$STATE_PUBLICATION_STAGE" ] \
             && [ ! -L "$STATE_PUBLICATION_STAGE" ]; } \
        && { [ ! -e "$STATE_PUBLICATION_STAGE.purging" ] \
             && [ ! -L "$STATE_PUBLICATION_STAGE.purging" ]; } \
        && { [ ! -e "$SHARE_PUBLICATION_STAGE" ] \
             && [ ! -L "$SHARE_PUBLICATION_STAGE" ]; } \
        && { [ ! -e "$SHARE_PUBLICATION_STAGE.purging" ] \
             && [ ! -L "$SHARE_PUBLICATION_STAGE.purging" ]; }; then
      echo "purge verified: corpus, ledger, keys, queues, state, and config removed."
    else
      failed "verify purge targets are absent"
    fi
  fi
else
  echo "removed program/UI integration. Memory and state survive at:"
  echo "  $SHARE_DIR"
  echo "  $STATE_DIR"
  echo "  $CONTINUITY_STATE_DIR"
  echo "  $CONFIG_DIR"
  echo "To erase them too: ./uninstall.sh --purge"
fi

# Restore exact surviving launch modes and clear the temporary tombstone only
# after every integration decision has succeeded. If anything failed, retain
# both durable gates so no legacy entry point can resume into partial state.
if [ "$SIA_LAUNCH_FENCE_ARMED" -eq 1 ]; then
  if [ "${#FAILURES[@]}" -eq 0 ]; then
    complete_uninstall_launch_fence || \
      failed "complete uninstall legacy-launch fence"
  else
    echo "uninstall launch fence retained; resolve failures and rerun uninstall.sh" >&2
  fi
fi

# A waiting shipped client must not acquire any owner lease until destructive
# purge and its absence check have both finished.  Releasing these descriptors
# earlier lets that client race the retained-tree removals.
for lock_variable in SIA_GBRAIN_LOCK_FD SIA_CORPUS_LOCK_FD \
    SIA_BRAINSTEM_LOCK_FD; do
  lock_descriptor="${!lock_variable}"
  if [ -n "$lock_descriptor" ]; then
    flock -u "$lock_descriptor" || true
    eval "exec ${lock_descriptor}>&-"
  fi
done

if [ -n "$SIA_UNINSTALL_LOCK_FD" ]; then
  flock -u "$SIA_UNINSTALL_LOCK_FD" || true
  eval "exec ${SIA_UNINSTALL_LOCK_FD}>&-"
  SIA_UNINSTALL_LOCK_FD=""
fi
if [ "$SIA_BRAINSTEM_RUNTIME_BARRIER_ARMED" -eq 1 ]; then
  if [ "${#FAILURES[@]}" -eq 0 ]; then
    remove_uninstall_brainstem_runtime_barrier || \
      failed "remove exact sia-brainstem.service runtime start barrier"
  else
    echo "sia-brainstem.service runtime start barrier retained because uninstall has failures" >&2
  fi
elif [ "$SIA_BRAINSTEM_RETIRED_BARRIER_PRESENT" -eq 1 ]; then
  if [ "${#FAILURES[@]}" -eq 0 ]; then
    if [ "$(brainstem_runtime_barrier_file state)" = retired ] \
        && run_with_deadline 120 systemctl --user daemon-reload \
        && inspect_user_unit sia-brainstem.service \
          BRAINSTEM_RETIRED_ABSENT \
        && [ "$BRAINSTEM_RETIRED_ABSENT_LOAD_STATE" = not-found ] \
        && [ "$BRAINSTEM_RETIRED_ABSENT_ACTIVE_STATE" = inactive ] \
        && [ -z "$BRAINSTEM_RETIRED_ABSENT_FRAGMENT_PATH" ] \
        && [ -z "$BRAINSTEM_RETIRED_ABSENT_UNIT_FILE_STATE" ] \
        && [ "$BRAINSTEM_RETIRED_ABSENT_MAIN_PID" = 0 ] \
        && brainstem_runtime_barrier_file discard >/dev/null; then
      SIA_BRAINSTEM_RETIRED_BARRIER_PRESENT=0
    else
      failed "discard interrupted-uninstall brainstem barrier recovery copy"
    fi
  else
    echo "retired sia-brainstem barrier recovery copy retained because uninstall has failures" >&2
  fi
fi

if [ -n "$PLUGIN_BACKUP" ]; then
  echo "previous plugin tree retained at $PLUGIN_BACKUP"
  echo "review and remove it manually when no longer needed."
fi
echo "Ollama (including its service/model) is left installed."
if [ -d "$SHARE_DIR/toolchain" ] && [ ! -L "$SHARE_DIR/toolchain" ]; then
  echo "SIA's private Bun/gbrain toolchain remains in the retained share tree."
else
  echo "SIA's private Bun/gbrain toolchain is not present."
fi

if [ "${#FAILURES[@]}" -ne 0 ]; then
  printf 'uninstall completed with %s failure(s):\n' "${#FAILURES[@]}" >&2
  printf '  - %s\n' "${FAILURES[@]}" >&2
  exit 1
fi
echo "uninstall completed successfully."
