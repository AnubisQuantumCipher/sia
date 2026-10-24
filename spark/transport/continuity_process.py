"""Experimental Linux process supervision; results are proposals, not authority."""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time

REQUEST_BYTES = 32768
RESPONSE_BYTES = 64
STDERR_BYTES = 4096
MAX_EXECUTABLE_BYTES = 8 * 1024 * 1024
MAX_POLLS = 8192
MAX_SECONDS = 5.0
PRLIMIT = '/usr/bin/prlimit'
LIMIT_ARGS = ('--as=268435456', '--stack=16777216', '--cpu=10',
              '--nofile=16', '--nproc=0', '--fsize=0', '--core=0')


class ProbeRefusal(RuntimeError):
    """No usable policy classification; never permission to retry an action."""


@dataclass(frozen=True)
class Observation:
    request_sha256: str
    executable_sha256: str
    operation: int
    code: int
    transport_refused: bool


def pin_executable(path, expected):
    """Pin the opened inode, with bounded hashing and observed change checks.

    Same-UID writes/custody attacks remain outside this experimental boundary.
    The expected digest must come from qualified build evidence, not the file.
    """
    if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
        raise ProbeRefusal('invalid expected executable identity')
    descriptor = os.open(Path(path), os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
                         | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or not before.st_mode & 0o111
                or not 0 < before.st_size <= MAX_EXECUTABLE_BYTES):
            raise ProbeRefusal('executable type, mode or byte budget')
        digest = hashlib.sha256()
        for _ in range(128):
            block = os.read(descriptor, 65536)
            if not block:
                break
            digest.update(block)
        if os.read(descriptor, 1):
            raise ProbeRefusal('executable exceeded read budget')
        after = os.fstat(descriptor)
        before_key = (before.st_dev, before.st_ino, before.st_size,
                      before.st_mtime_ns, before.st_ctime_ns)
        after_key = (after.st_dev, after.st_ino, after.st_size,
                     after.st_mtime_ns, after.st_ctime_ns)
        if before_key != after_key:
            raise ProbeRefusal('executable changed during hashing')
        if digest.hexdigest() != expected:
            raise ProbeRefusal('executable identity mismatch')
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def command(descriptor):
    return [PRLIMIT, *LIMIT_ARGS, '--', f'/proc/self/fd/{descriptor}']


def classify_response(output, error, status, requested, request_hash, binary_hash):
    """Independent envelope checks; no semantic recomputation or action grant."""
    if error or len(output) != RESPONSE_BYTES:
        raise ProbeRefusal('stderr or response length')
    if output[:5] != b'SIAR\x01' or any(output[8:]):
        raise ProbeRefusal('response header or reserved bytes')
    operation, family, code = output[5:8]
    if operation != family:
        raise ProbeRefusal('response family mismatch')
    if operation == 0:
        if code != 1 or status != 65:
            raise ProbeRefusal('malformed response/status mismatch')
    elif (operation not in (1, 2) or operation != requested or status != 0
          or code not in range(1, 8 if operation == 1 else 10)):
        raise ProbeRefusal('policy response/status/request mismatch')
    return Observation(request_hash, binary_hash, operation, code, operation == 0)


def stop_and_reap(child):
    # The caller must retain the unreaped leader to reserve this numeric PGID.
    if child.returncode is not None:
        raise ProbeRefusal('leader already reaped before cleanup')
    termination_error = None
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as error:
        termination_error = error
    try:
        child.wait(timeout=1)
    except subprocess.TimeoutExpired as error:
        refusal = ProbeRefusal('cleanup outcome uncertain')
        if termination_error is not None:
            refusal.add_note('group termination failed: ' + str(termination_error))
        raise refusal from error
    if termination_error is not None:
        raise ProbeRefusal('group termination failed; direct child reaped') from termination_error


def observe_exit(child):
    result = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    if result is None:
        return None
    if result.si_pid != child.pid:
        raise ProbeRefusal('unexpected terminal identity')
    if result.si_code == os.CLD_EXITED:
        return result.si_status
    if result.si_code in (os.CLD_KILLED, os.CLD_DUMPED):
        return -result.si_status
    raise ProbeRefusal('unexpected terminal state')


def close_pipes(child):
    failure = None
    for stream in (child.stdin, child.stdout, child.stderr):
        try:
            stream.close()
        except OSError as error:
            failure = error
    if failure is not None:
        raise ProbeRefusal('pipe cleanup failed') from failure


def exchange(child, payload, seconds):
    """Bound each stream and the poll count, then require a terminal process."""
    output, error = bytearray(), bytearray()
    deadline, position = time.monotonic() + seconds, 0
    with selectors.DefaultSelector() as selector:
        if payload:
            os.set_blocking(child.stdin.fileno(), False)
            selector.register(child.stdin, selectors.EVENT_WRITE)
        else:
            child.stdin.close()
        for stream, events in ((child.stdout, selectors.EVENT_READ),
                               (child.stderr, selectors.EVENT_READ)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, events)
        for _ in range(MAX_POLLS):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProbeRefusal('process deadline')
            if not selector.get_map():
                status = observe_exit(child)
                if status is not None:
                    return bytes(output), bytes(error), status
            for key, _ in selector.select(min(remaining, 0.05)):
                stream = key.fileobj
                if stream is child.stdin:
                    position = write_input(selector, stream, payload, position)
                else:
                    target = output if stream is child.stdout else error
                    limit = RESPONSE_BYTES if stream is child.stdout else STDERR_BYTES
                    read_output(selector, stream, target, limit)
    raise ProbeRefusal('poll iteration budget')


def write_input(selector, stream, payload, position):
    try:
        count = os.write(stream.fileno(), payload[position:position + 4096])
    except BlockingIOError:
        return position
    if count <= 0:
        raise ProbeRefusal('input write failed')
    position += count
    if position == len(payload):
        selector.unregister(stream)
        stream.close()
    return position


def read_output(selector, stream, target, limit):
    try:
        block = os.read(stream.fileno(), limit + 1 - len(target))
    except BlockingIOError:
        return
    if not block:
        selector.unregister(stream)
        return
    if len(block) > limit - len(target):
        raise ProbeRefusal('output byte budget')
    target.extend(block)


def run(path, expected, payload, requested, *, seconds=MAX_SECONDS):
    """Run only a source-qualified test binary; no installed or live effects.

    Parent Python allocation/scheduling and prlimit/exec remain assumptions.
    The startup syscall itself is not made real-time by the exchange deadline.
    """
    if (not isinstance(payload, bytes) or len(payload) != REQUEST_BYTES
            or type(requested) is not int or requested not in (1, 2)
            or type(seconds) not in (int, float) or not 0 < seconds <= MAX_SECONDS):
        raise ProbeRefusal('request or deadline outside budget')
    if signal.getsignal(signal.SIGPIPE) != signal.SIG_IGN:
        raise ProbeRefusal('parent must ignore SIGPIPE')
    if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
        raise ProbeRefusal('parent must own child reaping with default SIGCHLD')
    descriptor = pin_executable(path, expected)
    try:
        child = subprocess.Popen(command(descriptor), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 pass_fds=(descriptor,), start_new_session=True,
                                 restore_signals=False, cwd='/',
                                 env={'PATH': '/usr/bin:/bin', 'LANG': 'C',
                                      'LC_ALL': 'C'})
        try:
            output, error, status = exchange(child, payload, seconds)
        finally:
            try:
                stop_and_reap(child)
            finally:
                close_pipes(child)
        if child.returncode != status:
            raise ProbeRefusal('observed/reaped status mismatch')
        return classify_response(output, error, status, requested,
                                 hashlib.sha256(payload).hexdigest(), expected)
    finally:
        os.close(descriptor)
