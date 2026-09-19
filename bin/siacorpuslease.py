"""Recognize a parent's inherited exclusive corpus lease.

Extracted from the resident library without behavioural change. The
marketplace per-file scan guard refuses a library above its headroom and
says extraction is the repair, not a raised threshold, so this moved out
whole rather than being trimmed.

The library keeps the original private name and delegates to it, so every
caller and every test that patches that name still binds the call. The
paths and environment key stay caller-supplied: this module owns the
checks, not the policy about where the lease lives.
"""

import fcntl
import os
import stat


def validated_inherited_fd(*, environ_key, lock_path):
    """Return the inherited descriptor, or None, refusing anything else.

    Every original check is preserved in its original order: the value is
    ASCII digits, the descriptor and the lock are both regular files owned
    by this euid and the same (dev, ino), the lock has not changed during
    handoff, no other holder can take it exclusively or shared, and the
    inherited descriptor itself owns the exclusive lease.
    """
    raw = os.environ.get(environ_key)
    if raw is None:
        return None
    if not raw or not raw.isascii() or not raw.isdigit():
        raise RuntimeError("invalid inherited SIA corpus descriptor")
    try:
        inherited_fd = int(raw, 10)
        inherited = os.fstat(inherited_fd)
        target = os.lstat(lock_path)
    except (OSError, ValueError) as exc:
        raise RuntimeError("invalid inherited SIA corpus descriptor") from exc
    if not stat.S_ISREG(inherited.st_mode) \
            or inherited.st_uid != os.geteuid() \
            or not stat.S_ISREG(target.st_mode) \
            or target.st_uid != os.geteuid() \
            or (inherited.st_dev, inherited.st_ino) != \
               (target.st_dev, target.st_ino):
        raise RuntimeError(
            "inherited SIA corpus descriptor is not the owned lease")

    flags = (os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    try:
        probe_fd = os.open(lock_path, flags)
    except OSError as exc:
        raise RuntimeError("could not probe inherited SIA corpus lease") \
            from exc
    try:
        probe = os.fstat(probe_fd)
        if not stat.S_ISREG(probe.st_mode) \
                or probe.st_uid != os.geteuid() \
                or (probe.st_dev, probe.st_ino) != \
                   (inherited.st_dev, inherited.st_ino):
            raise RuntimeError("SIA corpus lease changed during handoff")
        try:
            fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(probe_fd, fcntl.LOCK_UN)
            raise RuntimeError(
                "inherited SIA corpus descriptor has no conflicting lease")
        try:
            fcntl.flock(probe_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(probe_fd, fcntl.LOCK_UN)
            raise RuntimeError(
                "inherited SIA corpus descriptor is not exclusively held")
        try:
            fcntl.flock(inherited_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "inherited SIA corpus descriptor does not own the lease") \
                from exc
    finally:
        os.close(probe_fd)
    return inherited_fd
