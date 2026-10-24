"""Bounded grant-file observations, not authorization or signature verification.

The service must supply its already-authorized directory descriptor and hold
its grant-store lease. Separate-UID installation and protected ancestry are
external obligations. This module never accepts a caller-selected file name.
GrantRefusal and OSError both propagate without a usable result. Callers must
fail closed on either, including close failures, and retain cleanup uncertainty.
"""
from dataclasses import dataclass
import os
import stat

MAX_RECORD_BYTES = 1024
GRANT_NAME = "grant.record"


class GrantRefusal(Exception):
    """The retained grant cannot be supplied to policy evaluation."""


@dataclass(frozen=True)
class GrantRecord:
    subject: int
    not_before: int
    expires: int
    active: bool
    expected_frame: bytes


@dataclass(frozen=True)
class ScopedGrantRecord:
    boot: bytes
    service: bytes
    grant: GrantRecord


def _decimal(value, maximum):
    if not 1 <= len(value) <= 19 or any(c < "0" or c > "9" for c in value):
        raise GrantRefusal("invalid-decimal")
    if len(value) > 1 and value[0] == "0":
        raise GrantRefusal("noncanonical-decimal")
    number = int(value)
    if number > maximum:
        raise GrantRefusal("decimal-out-of-range")
    return number


def parse_record(raw):
    """Parse flat bounded syntax; all authorization stays in the policy."""
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_RECORD_BYTES:
        raise GrantRefusal("invalid-record-size")
    try:
        rows = raw.decode("ascii").split("\n")
    except UnicodeDecodeError as exc:
        raise GrantRefusal("non-ascii-record") from exc
    if len(rows) != 7 or rows[0] != "sia-grant-v1" or rows[-1] != "":
        raise GrantRefusal("invalid-record-layout")
    prefixes = ("subject=", "not-before=", "expires=", "active=", "request=")
    values = []
    for row, prefix in zip(rows[1:6], prefixes):
        if not row.startswith(prefix):
            raise GrantRefusal("invalid-record-field")
        values.append(row[len(prefix):])
    subject = _decimal(values[0], 4294967295)
    not_before = _decimal(values[1], 9223372036854775807)
    expires = _decimal(values[2], 9223372036854775807)
    if values[3] not in ("0", "1"):
        raise GrantRefusal("invalid-active-field")
    if len(values[4]) != 384 or any(c not in "0123456789abcdef" for c in values[4]):
        raise GrantRefusal("invalid-request-encoding")
    return GrantRecord(subject, not_before, expires, values[3] == "1",
                       bytes.fromhex(values[4]))


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory(directory_fd):
    info = os.fstat(directory_fd)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() \
            or stat.S_IMODE(info.st_mode) not in (0o500, 0o700):
        raise GrantRefusal("unsafe-grant-directory")
    return info


def _read_record(directory_fd):
    """Read one held, private service-owned record; errors never yield a grant."""
    parent = _directory(directory_fd)
    descriptor = os.open(GRANT_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                         | os.O_CLOEXEC, dir_fd=directory_fd)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() \
                or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) not in (0o400, 0o600):
            raise GrantRefusal("unsafe-grant-file")
        if not 1 <= before.st_size <= MAX_RECORD_BYTES:
            raise GrantRefusal("invalid-record-size")
        raw = os.read(descriptor, MAX_RECORD_BYTES + 1)
        if len(raw) != before.st_size or _identity(os.fstat(descriptor)) != _identity(before):
            raise GrantRefusal("grant-changed-or-short-read")
        linked = os.stat(GRANT_NAME, dir_fd=directory_fd, follow_symlinks=False)
        if _identity(linked) != _identity(before) or _identity(_directory(directory_fd)) != _identity(parent):
            raise GrantRefusal("grant-binding-changed")
        return raw
    finally:
        os.close(descriptor)


def load_record(directory_fd):
    """Observe the legacy unscoped fixture format only."""
    return parse_record(_read_record(directory_fd))


def parse_scoped_record(raw):
    """Decode explicit v2 domains; zeros remain for SPARK policy to deny."""
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_RECORD_BYTES:
        raise GrantRefusal("invalid-record-size")
    try:
        rows = raw.decode("ascii").split("\n")
    except UnicodeDecodeError as exc:
        raise GrantRefusal("non-ascii-record") from exc
    if len(rows) != 9 or rows[0] != "sia-grant-v2" or rows[-1] != "":
        raise GrantRefusal("invalid-scoped-record-layout")
    domains = []
    for row, prefix in zip(rows[1:3], ("boot=", "service=")):
        if not row.startswith(prefix):
            raise GrantRefusal("invalid-domain-field")
        value = row[len(prefix):]
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise GrantRefusal("invalid-domain-encoding")
        domains.append(bytes.fromhex(value))
    legacy = ("sia-grant-v1\n" + "\n".join(rows[3:])).encode("ascii")
    return ScopedGrantRecord(domains[0], domains[1], parse_record(legacy))


def load_scoped_record(directory_fd):
    """Observe v2 only: legacy records cannot become scoped grants implicitly."""
    return parse_scoped_record(_read_record(directory_fd))
