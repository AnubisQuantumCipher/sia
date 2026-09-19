"""Whether this host's running interpreter can be pinned by the cognitive timing lane.

The lane pins the running interpreter as an admitted ordinary executable:
a regular ELF file owned by root or by the current user, with one hard
link and no group/other write bit, opened through a no-follow directory
chain. GitHub's hosted tool cache does not satisfy that for its Python, so
the observation cannot run there. Tests that need the pin skip with the
observed reason, which is a statement about the host, not about the lane.
"""
import functools
import os
import stat
import sys

_BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

try:
    import sia_test_home  # noqa: F401  test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore  # noqa: F401


def interpreter_refusal():
    """Return None when the running interpreter is admissible, else why not."""
    import siavectormodel as model_files
    import siavector

    path = os.path.realpath(sys.executable)
    try:
        fd = model_files._open(path, os.O_RDONLY)
    except (OSError, ValueError, RuntimeError, model_files.ModelRefusal) as exc:
        return (f"running interpreter {path} is not openable through the "
                f"lane's no-follow chain ({exc})")
    try:
        info = os.fstat(fd)
        problems = []
        if not stat.S_ISREG(info.st_mode):
            problems.append("not a regular file")
        if info.st_uid not in (0, os.geteuid()):
            problems.append(f"owned by uid {info.st_uid}")
        if info.st_nlink != 1:
            problems.append(f"{info.st_nlink} hard links")
        if info.st_mode & 0o022:
            problems.append(f"mode {oct(stat.S_IMODE(info.st_mode))} is group/other writable")
        if not info.st_mode & 0o111:
            problems.append("not executable")
        if info.st_size > siavector.MAX_EXECUTABLE_BYTES:
            problems.append("larger than the executable ceiling")
        if os.pread(fd, 4, 0) != b"\x7fELF":
            problems.append("not an ELF executable")
    finally:
        os.close(fd)
    if not problems:
        return None
    return ("running interpreter " + path + " is not an admitted ordinary "
            "executable on this host (" + ", ".join(problems) + "); the cognitive "
            "timing lane pins only such an interpreter, so this observation "
            "cannot run here")


def requires_admitted_interpreter(test):
    """Skip the test, naming the host's reason, when the interpreter cannot be pinned.

    Evaluated when the test runs, after the suite has put the runtime on the
    import path, never at import time.
    """
    @functools.wraps(test)
    def wrapper(self, *args, **kwargs):
        reason = interpreter_refusal()
        if reason is not None:
            self.skipTest(reason)
        return test(self, *args, **kwargs)
    return wrapper
