"""Replaceable recovery-repository adapter for SIA portable capsules.

The brain-native boundary lives in :mod:`siacapsule`.  This module never
walks SIA's live roots and never teaches restic where those roots live.  It
persists only capsules returned by ``siacapsule.freeze`` and restores only to
an off-path tree which ``siacapsule.verify`` authenticates.
"""

import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import posixpath
import re
import secrets
import stat
import subprocess
import sys
import uuid

import siacapsule
import sialib


CONFIG_SCHEMA = "sia-continuity-config-v2"
REQUEST_SCHEMA = "sia-continuity-request-v1"
# JACKAL status=exact, parsed=1+1, exact=2. Exact rational arithmetic
# outside the Lean certificate chain (NOT formal-bounded).
STATUS_SCHEMA_VERSION = 2
CONFIRMATION_SCHEMA_VERSION = 1
ACCEPTANCE_SCHEMA_VERSION = 1
PROFILE = "signed portable capsule"

ROOT = os.path.join(sialib.HOME, ".local", "state", "sia-continuity")
CONFIG_PATH = os.path.join(sialib.HOME, ".config", "sia", "continuity.json")
KEY_PATH = os.path.join(ROOT, "repository.key")
STATUS_PATH = os.path.join(ROOT, "status.json")
SUPERVISOR_PATH = os.path.join(ROOT, "restore-supervisor.json")
REQUESTS_DIR = os.path.join(ROOT, "requests")
CAPSULES_DIR = os.path.join(ROOT, "capsules")
PREPARED_DIR = os.path.join(ROOT, "prepared")
ROLLBACK_DIR = os.path.join(ROOT, "rollback")
CHECKS_DIR = os.path.join(ROOT, "checks")
VERIFICATIONS_DIR = os.path.join(ROOT, "verifications")
REQUEST_LOCK = os.path.join(ROOT, "request.lock")
WORKER_LOCK = os.path.join(ROOT, "worker.lock")
RESTIC_PATH = os.path.join(sialib.TOOLCHAIN, "restic", "bin", "restic")
STABLE_CLI_PATH = os.path.join(sialib.HOME, ".local", "bin", "sia")

# JACKAL status=exact, parsed=24*60*60, exact=86400. Exact rational
# arithmetic outside the Lean certificate chain (NOT formal-bounded).
RESTIC_TIMEOUT_SECONDS = 86400
# JACKAL status=exact, parsed=1, exact=1; exact rational arithmetic
# outside the Lean certificate chain (NOT formal-bounded).
LATEST_SNAPSHOT_COUNT = "1"
# JACKAL status=exact, parsed=64, exact=64; exact rational arithmetic
# outside the Lean certificate chain (NOT formal-bounded). This is a policy
# bound for the operator-facing list, not a claim about repository size.
LIST_SNAPSHOT_COUNT = "64"
# JACKAL status=exact, parsed=1024*1024, exact=1048576. Exact rational
# arithmetic outside the Lean certificate chain (NOT formal-bounded).
MAX_SPOOL_ENTRIES = 1_048_576
# JACKAL status=exact, parsed=64, exact=64; same assurance boundary.
MAX_SPOOL_DEPTH = 64
# JACKAL status=exact, parsed=64*1024*1024*1024, exact=68719476736;
# same assurance boundary. This is an explicit local staging policy, not a
# claim about available disk capacity or a repository-retention policy.
MAX_SPOOL_BYTES = 68_719_476_736
# JACKAL status=exact, parsed=64*1024*1024, exact=67108864;
# exact rational arithmetic outside the Lean certificate chain (NOT
# formal-bounded). This bounds the signed-ledger scan used only after its
# verifier succeeds.
MAX_LEDGER_BYTES = 67_108_864

_SAFE_ID = re.compile(r"[0-9a-f]+")
_REMOTE_REPOSITORY_PREFIXES = (
    "rest:", "sftp:", "s3:", "b2:", "azure:", "gs:", "rclone:",
    "swift:",
)
_ALLOWED_ENVIRONMENT = frozenset({
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "AWS_DEFAULT_REGION", "AWS_REGION",
    "B2_ACCOUNT_ID", "B2_ACCOUNT_KEY", "B2_APPLICATION_KEY_ID",
    "B2_APPLICATION_KEY", "AZURE_ACCOUNT_NAME", "AZURE_ACCOUNT_KEY",
    "AZURE_ACCOUNT_SAS", "GOOGLE_PROJECT_ID",
    "GOOGLE_APPLICATION_CREDENTIALS", "RESTIC_REST_USERNAME",
    "RESTIC_REST_PASSWORD", "RCLONE_CONFIG", "SSH_AUTH_SOCK",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
})
_PATH_ENVIRONMENT = frozenset({
    "GOOGLE_APPLICATION_CREDENTIALS", "RCLONE_CONFIG",
})
VERIFICATION_SCHEMA = "sia-continuity-verification-v2"
SUPERVISOR_SCHEMA = "sia-restore-supervisor-v1"

SYSTEMD_USER_DIR = os.path.join(sialib.HOME, ".config", "systemd", "user")
MANAGED_INSTALL_DIR = os.path.join(sialib.STATE, "managed-install")
_CONTINUITY_UNITS = (
    ("sia-backup.service", "backup-unit", "service", None),
    ("sia-backup.timer", "backup-timer", "timer", "sia-backup.service"),
    ("sia-backup-check.service", "backup-check-unit", "service", None),
    ("sia-backup-check.timer", "backup-check-timer", "timer",
     "sia-backup-check.service"),
)
_ACTIONS = frozenset({
    "setup", "connect", "upload", "check", "prepare", "apply",
})
_ACTION_KIND = {
    "setup": "backup-setup",
    "connect": "backup-connect",
    "upload": "backup-upload",
    "check": "backup-check",
    "prepare": "restore-prepare",
    "apply": "restore-apply",
}
_STATUS_STATES = frozenset({
    "unconfigured", "queued", "capturing", "uploading", "checking",
    "preparing", "prepared", "restoring", "verified", "recovery-only",
    "failed", "blocked",
})
_OPERATION_PHASES = frozenset({
    "accepted", "running", "verified", "failed", "blocked",
})


class BlockedError(RuntimeError):
    """A safe, operator-visible terminal refusal rather than a failed write."""


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_nlink, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns)


def _fsync_dir(path):
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
             | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError("continuity directory is not an owned directory")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree(path):
    _catalog_private_tree(path, "prepared tree")
    directories = []
    for current, children, files in os.walk(path, topdown=True,
                                            followlinks=False):
        children.sort()
        files.sort()
        info = os.lstat(current)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError("prepared tree contains an unsafe directory")
        directories.append(current)
        for name in children + files:
            child = os.path.join(current, name)
            child_info = os.lstat(child)
            if stat.S_ISLNK(child_info.st_mode) \
                    or not (stat.S_ISDIR(child_info.st_mode)
                            or stat.S_ISREG(child_info.st_mode)):
                raise ValueError("prepared tree contains a special file")
            if stat.S_ISREG(child_info.st_mode):
                flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                         | getattr(os, "O_NOFOLLOW", 0)
                         | getattr(os, "O_NONBLOCK", 0))
                descriptor = os.open(child, flags)
                try:
                    current_info = os.fstat(descriptor)
                    if current_info.st_uid != os.geteuid() \
                            or current_info.st_nlink != 1:
                        raise ValueError(
                            "prepared tree contains an unsafe file")
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
    for directory in reversed(directories):
        _fsync_dir(directory)


def _bounded_fd_names(directory_fd, label):
    """List one private spool directory without unbounded allocation."""
    names = []
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            if len(names) >= MAX_SPOOL_ENTRIES:
                raise ValueError(f"{label} exceeds its entry boundary")
            name = entry.name
            if not isinstance(name, str) or not name \
                    or name in {".", ".."} or "/" in name or "\0" in name \
                    or len(os.fsencode(name)) > sialib.MAX_CONFIG_BYTES:
                raise ValueError(f"{label} contains an invalid name")
            names.append(name)
    return tuple(sorted(names))


def _bounded_private_names(path, label):
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
             | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError(f"{label} is not an owned directory")
        return _bounded_fd_names(descriptor, label)
    finally:
        os.close(descriptor)


def _catalog_private_tree(path, label):
    """Preflight one untrusted spool tree before any consumer or deletion."""
    path = os.path.abspath(path)
    directory_flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                       | getattr(os, "O_CLOEXEC", 0)
                       | getattr(os, "O_NOFOLLOW", 0))
    file_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                  | getattr(os, "O_NOFOLLOW", 0)
                  | getattr(os, "O_NONBLOCK", 0))
    records = {}
    children = {}
    total_bytes = 0

    def visit(directory_fd, relative, depth):
        nonlocal total_bytes
        if depth > MAX_SPOOL_DEPTH:
            raise ValueError(f"{label} exceeds its depth boundary")
        names = _bounded_fd_names(directory_fd, label)
        children[relative] = names
        for name in names:
            if not isinstance(name, str) or not name \
                    or name in {".", ".."} \
                    or "/" in name or "\0" in name:
                raise ValueError(f"{label} contains an invalid name")
            child_relative = relative + (name,)
            encoded_path = os.fsencode(os.path.join(*child_relative))
            if len(encoded_path) > sialib.MAX_CONFIG_BYTES:
                raise ValueError(f"{label} exceeds its path boundary")
            if len(records) >= MAX_SPOOL_ENTRIES:
                raise ValueError(f"{label} exceeds its entry boundary")
            observed = os.stat(
                name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISDIR(observed.st_mode):
                child_fd = os.open(name, directory_flags,
                                   dir_fd=directory_fd)
                try:
                    opened = os.fstat(child_fd)
                    if not stat.S_ISDIR(opened.st_mode) \
                            or opened.st_uid != os.geteuid() \
                            or (opened.st_dev, opened.st_ino) != \
                               (observed.st_dev, observed.st_ino):
                        raise ValueError(
                            f"{label} contains an unsafe directory")
                    records[child_relative] = ("directory", _generation(opened))
                    visit(child_fd, child_relative, depth + 1)
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(observed.st_mode) \
                    or observed.st_uid != os.geteuid() \
                    or observed.st_nlink != 1:
                raise ValueError(f"{label} contains an unsafe file")
            descriptor = os.open(name, file_flags, dir_fd=directory_fd)
            try:
                opened = os.fstat(descriptor)
                if _generation(opened) != _generation(observed):
                    raise ValueError(f"{label} changed during preflight")
            finally:
                os.close(descriptor)
            if opened.st_size > MAX_SPOOL_BYTES - total_bytes:
                raise ValueError(f"{label} exceeds its byte boundary")
            total_bytes += opened.st_size
            records[child_relative] = ("file", _generation(opened))

    root_fd = os.open(path, directory_flags)
    try:
        root_info = os.fstat(root_fd)
        if not stat.S_ISDIR(root_info.st_mode) \
                or root_info.st_uid != os.geteuid():
            raise ValueError(f"{label} root is unsafe")
        records[()] = ("directory", _generation(root_info))
        visit(root_fd, (), 0)
    finally:
        os.close(root_fd)
    return {"records": records, "children": children,
            "total_bytes": total_bytes}


def _retire_private_tree(path, authority):
    """Catalog, then descriptor-retire one direct private-spool child."""
    path = os.path.abspath(path)
    authority = os.path.abspath(authority)
    if os.path.dirname(path) != authority:
        raise ValueError("continuity retirement target is outside its spool")
    directory_flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                       | getattr(os, "O_CLOEXEC", 0)
                       | getattr(os, "O_NOFOLLOW", 0))
    file_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                  | getattr(os, "O_NOFOLLOW", 0)
                  | getattr(os, "O_NONBLOCK", 0))
    catalog = _catalog_private_tree(path, "continuity retirement tree")

    def retire(parent_fd, name, relative):
        child_fd = os.open(name, directory_flags, dir_fd=parent_fd)
        try:
            opened = os.fstat(child_fd)
            if not stat.S_ISDIR(opened.st_mode) \
                    or opened.st_uid != os.geteuid() \
                    or (opened.st_dev, opened.st_ino) != \
                       catalog["records"][relative][1][:2]:
                raise ValueError(
                    "continuity retirement encountered an unsafe directory")
            names = _bounded_fd_names(
                child_fd, "continuity retirement tree")
            if names != catalog["children"][relative]:
                raise ValueError("continuity retirement tree changed")
            for child_name in names:
                child_relative = relative + (child_name,)
                expected_kind, expected_generation = \
                    catalog["records"][child_relative]
                observed = os.stat(
                    child_name, dir_fd=child_fd, follow_symlinks=False)
                if expected_kind == "directory":
                    if not stat.S_ISDIR(observed.st_mode) \
                            or (observed.st_dev, observed.st_ino) != \
                               expected_generation[:2]:
                        raise ValueError(
                            "continuity retirement directory changed")
                    retire(child_fd, child_name, child_relative)
                    continue
                if not stat.S_ISREG(observed.st_mode) \
                        or observed.st_uid != os.geteuid() \
                        or observed.st_nlink != 1 \
                        or _generation(observed) != expected_generation:
                    raise ValueError(
                        "continuity retirement encountered an unsafe file")
                descriptor = os.open(
                    child_name, file_flags, dir_fd=child_fd)
                try:
                    current = os.fstat(descriptor)
                    if _generation(current) != _generation(observed):
                        raise ValueError(
                            "continuity retirement file changed")
                    os.unlink(child_name, dir_fd=child_fd)
                finally:
                    os.close(descriptor)
            linked = os.stat(
                name, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISDIR(linked.st_mode) \
                    or (linked.st_dev, linked.st_ino) != \
                       (opened.st_dev, opened.st_ino):
                raise ValueError(
                    "continuity retirement directory changed")
            os.fsync(child_fd)
        finally:
            os.close(child_fd)
        os.rmdir(name, dir_fd=parent_fd)

    authority_fd = os.open(authority, directory_flags)
    try:
        authority_info = os.fstat(authority_fd)
        if not stat.S_ISDIR(authority_info.st_mode) \
                or authority_info.st_uid != os.geteuid():
            raise ValueError("continuity retirement spool is unsafe")
        retire(authority_fd, os.path.basename(path), ())
        os.fsync(authority_fd)
    finally:
        os.close(authority_fd)


def _retire_private_file(path, authority):
    path = os.path.abspath(path)
    authority = os.path.abspath(authority)
    if os.path.dirname(path) != authority:
        raise ValueError("continuity file retirement is outside its spool")
    directory_flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                       | getattr(os, "O_CLOEXEC", 0)
                       | getattr(os, "O_NOFOLLOW", 0))
    file_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                  | getattr(os, "O_NOFOLLOW", 0)
                  | getattr(os, "O_NONBLOCK", 0))
    parent_fd = os.open(authority, directory_flags)
    try:
        parent = os.fstat(parent_fd)
        if not stat.S_ISDIR(parent.st_mode) \
                or parent.st_uid != os.geteuid():
            raise ValueError("continuity file spool is unsafe")
        name = os.path.basename(path)
        descriptor = os.open(name, file_flags, dir_fd=parent_fd)
        try:
            opened = os.fstat(descriptor)
            linked = os.stat(name, dir_fd=parent_fd,
                             follow_symlinks=False)
            if not stat.S_ISREG(opened.st_mode) \
                    or opened.st_uid != os.geteuid() \
                    or opened.st_nlink != 1 \
                    or _generation(opened) != _generation(linked):
                raise ValueError("continuity retirement file is unsafe")
            os.unlink(name, dir_fd=parent_fd)
        finally:
            os.close(descriptor)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _ensure_private_dir(path):
    path = os.path.abspath(path)
    os.makedirs(path, mode=0o700, exist_ok=True)
    info = os.lstat(path)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise ValueError("continuity path is not an owned real directory")
    if stat.S_IMODE(info.st_mode) & 0o077:
        os.chmod(path, 0o700)
    return path


def _ensure_layout():
    for path in (ROOT, REQUESTS_DIR, CAPSULES_DIR, PREPARED_DIR, ROLLBACK_DIR,
                 CHECKS_DIR, VERIFICATIONS_DIR):
        _ensure_private_dir(path)
    _fsync_dir(ROOT)


def _read_regular(path, label, *, private=False,
                  maximum=sialib.MAX_STATE_JSON_BYTES):
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0))
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() or before.st_nlink != 1:
            raise ValueError(f"{label} is not an owned single-link file")
        if private and stat.S_IMODE(before.st_mode) & 0o077:
            raise ValueError(f"{label} is not owner-private")
        if before.st_size > maximum:
            raise ValueError(f"{label} exceeds its byte boundary")
        chunks = []
        remaining = maximum + 1
        while remaining:
            block = os.read(descriptor, min(remaining, sialib.MAX_CONFIG_BYTES))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        if len(raw) > maximum or len(raw) != before.st_size \
                or _generation(before) != _generation(after) \
                or _generation(after) != _generation(current):
            raise ValueError(f"{label} changed while read")
        return raw
    finally:
        os.close(descriptor)


def _decode_json(raw, label):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label} contains duplicate JSON keys")
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8", "strict"),
                          object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"{label} is not strict JSON") from exc


def _read_json(path, label, *, private=True):
    return _decode_json(_read_regular(path, label, private=private), label)


def _write_exclusive(path, raw, mode=0o600):
    if not isinstance(raw, bytes):
        raise TypeError("continuity publication requires bytes")
    parent = _ensure_private_dir(os.path.dirname(os.path.abspath(path)))
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
             | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    descriptor = os.open(path, flags, mode)
    try:
        os.fchmod(descriptor, mode)
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short continuity publication")
            view = view[written:]
        os.fsync(descriptor)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)
    _fsync_dir(parent)
    return path


def _external_parent(path, label):
    parent = os.path.dirname(os.path.abspath(path))
    if os.path.realpath(parent) != parent:
        raise ValueError(f"{label} parent must not traverse symlinks")
    info = os.lstat(parent)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() \
            or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError(
            f"{label} parent must be an existing owner-private directory")
    return parent


def _write_external_exclusive(path, raw, mode=0o600):
    parent = _external_parent(path, "offline recovery output")
    parent_before = os.lstat(parent)
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
             | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    descriptor = os.open(path, flags, mode)
    try:
        os.fchmod(descriptor, mode)
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short offline recovery publication")
            view = view[written:]
        os.fsync(descriptor)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)
    checked = _read_regular(
        path, "published offline recovery output", private=True,
        maximum=sialib.MAX_CONFIG_BYTES)
    output_info = os.lstat(path)
    parent_after = os.lstat(parent)
    parent_identity = lambda value: (
        value.st_dev, value.st_ino, value.st_mode, value.st_uid,
        value.st_nlink)
    if checked != raw or stat.S_IMODE(output_info.st_mode) != 0o600 \
            or parent_identity(parent_before) != parent_identity(parent_after) \
            or stat.S_IMODE(parent_after.st_mode) & 0o077:
        raise RuntimeError(
            "offline recovery publication did not remain exact")
    _fsync_dir(parent)
    return path


def _atomic_json(path, value):
    raw = _canonical_bytes(value)
    if len(raw) > sialib.MAX_STATE_JSON_BYTES:
        raise ValueError("continuity state exceeds its byte boundary")
    parent = _ensure_private_dir(os.path.dirname(os.path.abspath(path)))
    if os.path.lexists(path):
        current = os.lstat(path)
        if not stat.S_ISREG(current.st_mode) \
                or current.st_uid != os.geteuid() or current.st_nlink != 1:
            raise ValueError("continuity publication target is unsafe")
    stage = os.path.join(parent, ".status-stage-" + uuid.uuid4().hex)
    _write_exclusive(stage, raw, 0o600)
    os.replace(stage, path)
    _fsync_dir(parent)
    return value


@contextlib.contextmanager
def _exclusive_lock(path):
    _ensure_private_dir(os.path.dirname(path))
    flags = (os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    descriptor = os.open(path, flags, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) \
                or info.st_uid != os.geteuid() or info.st_nlink != 1:
            raise ValueError("continuity lock is unsafe")
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


@contextlib.contextmanager
def _exclusive_lock_nonblocking(path):
    _ensure_private_dir(os.path.dirname(path))
    flags = (os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    descriptor = os.open(path, flags, 0o600)
    acquired = False
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) \
                or info.st_uid != os.geteuid() or info.st_nlink != 1:
            raise ValueError("continuity lock is unsafe")
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BlockedError("Another continuity worker is active.") \
                from exc
        acquired = True
        yield
    finally:
        try:
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _default_status():
    configured = os.path.isfile(CONFIG_PATH) and os.path.isfile(KEY_PATH)
    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "state": "recovery-only" if configured else "unconfigured",
        "detail": ("Repository configured; no verified copy recorded."
                   if configured else "Continuity is not configured."),
        "repository_display": ("External recovery repository"
                               if configured else ""),
        "latest": None,
        "prepared": None,
        "operation": None,
        "updated_at": _now(),
    }


def _latest_is_protecting(latest):
    return isinstance(latest, dict) \
        and isinstance(latest.get("snapshot_id"), str) \
        and bool(latest["snapshot_id"]) \
        and isinstance(latest.get("created_at"), str) \
        and bool(latest["created_at"]) \
        and isinstance(latest.get("profile"), str) \
        and bool(latest["profile"]) \
        and latest.get("verified") is True \
        and latest.get("readiness") == "ready" \
        and latest.get("identity_matches") is True


def read_status():
    try:
        value = _read_json(STATUS_PATH, "continuity status")
    except FileNotFoundError:
        return _default_status()
    required = {"schema_version", "state", "detail", "repository_display",
                "latest", "prepared", "operation", "updated_at"}
    if set(value) != required \
            or value.get("schema_version") != STATUS_SCHEMA_VERSION \
            or value.get("state") not in _STATUS_STATES \
            or not isinstance(value.get("detail"), str) \
            or not isinstance(value.get("repository_display"), str) \
            or not isinstance(value.get("updated_at"), str):
        raise ValueError("continuity status schema is invalid")
    latest = value.get("latest")
    if latest is not None and (
            not isinstance(latest, dict)
            or set(latest) != {"snapshot_id", "created_at", "verified",
                              "readiness", "profile", "identity_matches"}
            or not isinstance(latest.get("snapshot_id"), str)
            or not isinstance(latest.get("created_at"), str)
            or not isinstance(latest.get("verified"), bool)
            or not isinstance(latest.get("readiness"), str)
            or not isinstance(latest.get("profile"), str)
            or not isinstance(latest.get("identity_matches"), bool)):
        raise ValueError("continuity latest-copy status is invalid")
    if value.get("state") == "verified" \
            and not _latest_is_protecting(latest):
        raise ValueError(
            "verified continuity status lacks a ready identity-bound copy")
    prepared = value.get("prepared")
    if prepared is not None and (
            not isinstance(prepared, dict)
            or not isinstance(prepared.get("prepared_id"), str)
            or not isinstance(prepared.get("snapshot_id"), str)
            or not isinstance(prepared.get("created_at"), str)
            or not isinstance(prepared.get("readiness"), str)
            or not isinstance(prepared.get("profile"), str)
            or not isinstance(prepared.get("ledger_head"), str)
            or not isinstance(prepared.get("identity_matches"), bool)):
        raise ValueError("continuity prepared status is invalid")
    operation = value.get("operation")
    if operation is not None and (
            not isinstance(operation, dict)
            or set(operation) != {"request_id", "kind", "prepared_id",
                                  "phase", "ready", "sia_ledger_verified"}
            or not isinstance(operation.get("request_id"), str)
            or not operation["request_id"]
            or not isinstance(operation.get("kind"), str)
            or not operation["kind"]
            or not isinstance(operation.get("prepared_id"), str)
            or operation.get("phase") not in _OPERATION_PHASES
            or not isinstance(operation.get("ready"), bool)
            or not isinstance(operation.get("sia_ledger_verified"), bool)):
        raise ValueError("continuity operation status is invalid")
    return value


def _publish_status(**changes):
    try:
        value = read_status()
    except (OSError, ValueError):
        value = _default_status()
    value.update(changes)
    value["schema_version"] = STATUS_SCHEMA_VERSION
    value["updated_at"] = _now()
    if value.get("state") == "verified" \
            and not _latest_is_protecting(value.get("latest")):
        raise ValueError(
            "verified continuity publication lacks a concrete ready copy")
    return _atomic_json(STATUS_PATH, value)


def _operation(request_id, kind, phase, *, prepared_id="", ready=False,
               sia_ledger_verified=False):
    return {
        "request_id": request_id,
        "kind": kind,
        "prepared_id": prepared_id,
        "phase": phase,
        "ready": bool(ready),
        "sia_ledger_verified": bool(sia_ledger_verified),
    }


def _validate_text(value, label, *, absolute=False):
    if not isinstance(value, str) or not value \
            or len(value.encode("utf-8", "strict")) > sialib.MAX_CONFIG_BYTES \
            or any(marker in value for marker in ("\0", "\n", "\r")):
        raise ValueError(f"{label} is invalid")
    if absolute and not os.path.isabs(value):
        raise ValueError(f"{label} must be an absolute path")
    return value


def _live_brain_public_key():
    return _validate_text(
        siacapsule._public_hex(), "live SIA public identity")


def _validate_config(value, *, require_binding=True):
    if not isinstance(value, dict) \
            or set(value) != {"schema", "repository", "environment_file",
                              "repository_id", "brain_public_key",
                              "created_at"} \
            or value.get("schema") != CONFIG_SCHEMA:
        raise ValueError("continuity configuration schema is invalid")
    _validate_repository(value.get("repository"))
    environment_file = value.get("environment_file")
    if environment_file is not None:
        _validate_environment_file(environment_file)
    repository_id = value.get("repository_id")
    if not isinstance(repository_id, str) \
            or (repository_id and _SAFE_ID.fullmatch(repository_id) is None) \
            or (require_binding and not repository_id):
        raise ValueError("continuity repository identity is invalid")
    brain_public_key = _validate_text(
        value.get("brain_public_key"), "configured SIA public identity")
    if _SAFE_ID.fullmatch(brain_public_key) is None:
        raise ValueError("configured SIA public identity is malformed")
    if require_binding and not secrets.compare_digest(
            brain_public_key, _live_brain_public_key()):
        raise BlockedError(
            "Continuity configuration belongs to another SIA identity.")
    _validate_text(value.get("created_at"), "configuration timestamp")
    return value


def load_config():
    value = _validate_config(_read_json(
        CONFIG_PATH, "continuity configuration"), require_binding=True)
    key = _read_regular(KEY_PATH, "repository key", private=True,
                        maximum=sialib.MAX_CONFIG_BYTES)
    if not key.strip() or b"\0" in key or b"\n" in key.rstrip(b"\n"):
        raise ValueError("repository key is malformed")
    return value


def _parse_environment(path):
    if path is None:
        return {}
    _validate_text(path, "environment file", absolute=True)
    raw = _read_regular(path, "repository environment file", private=True,
                        maximum=sialib.MAX_CONFIG_BYTES)
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise ValueError("repository environment file is not UTF-8") from exc
    result = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("repository environment line is malformed")
        key, value = line.split("=", 1)
        if key not in _ALLOWED_ENVIRONMENT or key in result \
                or "\0" in value:
            raise ValueError("repository environment key is not allowed")
        if key in _PATH_ENVIRONMENT:
            _validate_backend_secret_path(value, key)
        result[key] = value
    return result


def _portable_authority_roots():
    return (sialib.SHARE, sialib.STATE, siacapsule.CONFIG_ROOT, ROOT)


def _validate_backend_secret_path(path, key):
    _validate_text(path, key, absolute=True)
    absolute = os.path.abspath(path)
    if os.path.realpath(absolute) != absolute:
        raise ValueError(f"{key} must not traverse symbolic links")
    for portable_root in _portable_authority_roots():
        authority = os.path.realpath(portable_root)
        try:
            nested = os.path.commonpath((absolute, authority)) == authority
        except ValueError:
            nested = False
        if nested:
            raise ValueError(
                f"{key} must be outside every portable authority root")
    _external_parent(absolute, key)
    _read_regular(absolute, key, private=True,
                  maximum=sialib.MAX_CONFIG_BYTES)
    return absolute


def _validate_environment_file(path):
    _validate_text(path, "environment file", absolute=True)
    candidate = os.path.realpath(path)
    if candidate != os.path.abspath(path):
        raise ValueError("repository environment file traverses a symlink")
    for portable_root in _portable_authority_roots():
        authority = os.path.realpath(portable_root)
        try:
            nested = os.path.commonpath((candidate, authority)) == authority
        except ValueError:
            nested = False
        if nested:
            raise ValueError(
                "repository environment file cannot be inside portable roots")
    _external_parent(path, "repository environment file")
    _parse_environment(path)
    return path


def _restic_environment(config, key_path=KEY_PATH):
    environment_file = config.get("environment_file")
    backend = _parse_environment(environment_file)
    environment = {}
    for name in ("HOME", "PATH", "LANG", "LC_ALL", "TMPDIR",
                 "XDG_RUNTIME_DIR"):
        if name in os.environ:
            environment[name] = os.environ[name]
    environment.update(backend)
    environment["RESTIC_REPOSITORY"] = config["repository"]
    environment["RESTIC_PASSWORD_FILE"] = key_path
    return environment


def _execute_restic(arguments, *, config, key_path, cwd, restic_path):
    restic_path = restic_path or RESTIC_PATH
    info = os.lstat(restic_path)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
            or not os.access(restic_path, os.X_OK):
        raise ValueError("private restic executable is unavailable")
    result = sialib._run_bounded_text_process(
        [restic_path, *arguments], env=_restic_environment(config, key_path),
        timeout=RESTIC_TIMEOUT_SECONDS, cwd=cwd, label="restic adapter",
        output_limit=sialib.MAX_STATE_JSON_BYTES)
    if result.returncode != 0:
        raise RuntimeError("restic operation was refused")
    return result.stdout


def _repository_identity(raw):
    value = _decode_json(raw.encode("utf-8", "strict"),
                         "restic repository configuration")
    repository_id = value.get("id") if isinstance(value, dict) else None
    if not isinstance(repository_id, str) or not repository_id \
            or _SAFE_ID.fullmatch(repository_id) is None:
        raise ValueError("restic repository identity is malformed")
    return repository_id


def _run_restic(arguments, *, config=None, key_path=KEY_PATH, cwd=None,
                restic_path=None):
    config = (load_config() if config is None else
              _validate_config(config, require_binding=False))
    repository_id = config.get("repository_id")
    if repository_id:
        raw_config = _execute_restic(
            ["cat", "config"], config=config, key_path=key_path, cwd=None,
            restic_path=restic_path)
        if not secrets.compare_digest(
                _repository_identity(raw_config), repository_id):
            raise BlockedError(
                "Recovery repository identity changed after configuration.")
        if arguments == ["cat", "config"]:
            return raw_config
    return _execute_restic(
        arguments, config=config, key_path=key_path, cwd=cwd,
        restic_path=restic_path)


def _validate_repository(repository):
    repository = _validate_text(repository, "repository")
    if os.path.isabs(repository):
        _protected_output(repository, "repository")
    elif not repository.startswith(_REMOTE_REPOSITORY_PREFIXES):
        raise ValueError(
            "repository backend prefix is not supported")
    return repository


def _repository_config(repository, environment_file):
    repository = _validate_repository(repository)
    return {
        "schema": CONFIG_SCHEMA,
        "repository": repository,
        "environment_file": (None if environment_file is None else
                             _validate_environment_file(environment_file)),
        "repository_id": "",
        "brain_public_key": _live_brain_public_key(),
        "created_at": _now(),
    }


def _reject_local_repository_secrets(repository, paths, environment_file):
    if not os.path.isabs(repository):
        return
    repository_root = os.path.realpath(repository)
    sensitive = [path for path in paths if path is not None]
    if environment_file is not None:
        sensitive.append(environment_file)
        for key, value in _parse_environment(environment_file).items():
            if key in _PATH_ENVIRONMENT:
                sensitive.append(value)
    for path in sensitive:
        candidate = os.path.realpath(path)
        try:
            nested = os.path.commonpath(
                (candidate, repository_root)) == repository_root
        except ValueError:
            nested = False
        if nested:
            raise ValueError(
                "recovery credentials must be outside the local repository")


def _protected_output(path, label):
    _validate_text(path, label, absolute=True)
    candidate = os.path.realpath(path)
    protected = (sialib.SHARE, sialib.STATE, siacapsule.CONFIG_ROOT, ROOT)
    for root in protected:
        try:
            common = os.path.commonpath((candidate, os.path.realpath(root)))
        except ValueError:
            continue
        if common == os.path.realpath(root):
            raise ValueError(f"{label} must be outside SIA's live roots")
    _external_parent(path, label)
    return path


def _commit_staged_key(stage):
    if os.path.lexists(KEY_PATH):
        existing = _read_regular(KEY_PATH, "repository key", private=True,
                                 maximum=sialib.MAX_CONFIG_BYTES)
        staged = _read_regular(stage, "staged repository key", private=True,
                               maximum=sialib.MAX_CONFIG_BYTES)
        if not secrets.compare_digest(existing, staged):
            raise ValueError("a different local repository key already exists")
        os.unlink(stage)
        _fsync_dir(ROOT)
        return
    os.rename(stage, KEY_PATH)
    _fsync_dir(ROOT)


def _managed_unit_binding(name, kind):
    target = os.path.join(SYSTEMD_USER_DIR, name)
    receipt = os.path.join(MANAGED_INSTALL_DIR, name)
    raw = _read_regular(
        target, "managed continuity unit", maximum=sialib.MAX_CONFIG_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    expected = (
        "managed-by=khephri.sia\n"
        f"kind={kind}\n"
        f"path={target}\n"
        f"sha256={digest}\n"
    ).encode("utf-8")
    if not secrets.compare_digest(
            _read_regular(receipt, "managed continuity unit receipt",
                          private=True, maximum=sialib.MAX_CONFIG_BYTES),
            expected):
        raise BlockedError(
            "A continuity systemd unit lacks its exact managed receipt.")
    return target, _generation(os.lstat(target)), \
        receipt, _generation(os.lstat(receipt))


def _systemd_unit_fields(name, *, timer):
    properties = [
        "LoadState", "FragmentPath", "DropInPaths", "ActiveState",
        "UnitFileState", "Job",
    ]
    if timer:
        properties.append("Unit")
    command = ["systemctl", "--user", "show", name]
    for prop in properties:
        command.append("--property=" + prop)
    result = sialib._run_bounded_text_process(
        command, env=None, timeout=sialib.JOURNAL_TIMEOUT_SECONDS, cwd=None,
        label="continuity systemd attestation",
        output_limit=sialib.MAX_CONFIG_BYTES)
    if result.returncode != 0:
        raise BlockedError("Continuity systemd unit attestation failed.")
    fields = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            raise ValueError("continuity systemd response is malformed")
        key, value = line.split("=", 1)
        if key in fields:
            raise ValueError("continuity systemd response repeats a field")
        fields[key] = value
    if set(fields) != set(properties):
        raise ValueError("continuity systemd response is incomplete")
    return fields


def _attest_continuity_units(*, timers_enabled=False,
                             timers_active=False):
    for name, kind, unit_type, timer_target in _CONTINUITY_UNITS:
        target, target_generation, receipt, receipt_generation = \
            _managed_unit_binding(name, kind)
        timer = unit_type == "timer"
        fields = _systemd_unit_fields(name, timer=timer)
        if fields["LoadState"] != "loaded" \
                or os.path.abspath(fields["FragmentPath"]) != target \
                or fields["DropInPaths"] \
                or fields["Job"]:
            raise BlockedError(
                "Effective continuity systemd authority is not exact.")
        if timer and fields["Unit"] != timer_target:
            raise BlockedError(
                "Continuity timer targets an unexpected service.")
        if timer and timers_enabled \
                and fields["UnitFileState"] != "enabled":
            raise BlockedError("Continuity timer is not enabled exactly.")
        if timer and timers_active and fields["ActiveState"] != "active":
            raise BlockedError("Continuity timer is not active exactly.")
        if _generation(os.lstat(target)) != target_generation \
                or _generation(os.lstat(receipt)) != receipt_generation:
            raise BlockedError(
                "Continuity systemd authority changed during attestation.")
    return True


def _enable_schedules():
    _attest_continuity_units()
    result = sialib._run_bounded_text_process(
        ["systemctl", "--user", "enable", "sia-backup.timer",
         "sia-backup-check.timer"], env=None,
        timeout=sialib.JOURNAL_TIMEOUT_SECONDS, cwd=None,
        label="continuity schedule", output_limit=sialib.MAX_CONFIG_BYTES)
    if result.returncode != 0:
        raise RuntimeError("continuity schedules could not be enabled")
    _attest_continuity_units(timers_enabled=True)


def _start_schedules():
    _attest_continuity_units(timers_enabled=True)
    result = sialib._run_bounded_text_process(
        ["systemctl", "--user", "start", "sia-backup.timer",
         "sia-backup-check.timer"], env=None,
        timeout=sialib.JOURNAL_TIMEOUT_SECONDS, cwd=None,
        label="continuity schedule start",
        output_limit=sialib.MAX_CONFIG_BYTES)
    if result.returncode != 0:
        raise RuntimeError("continuity schedules could not be started")
    _attest_continuity_units(
        timers_enabled=True, timers_active=True)


def _activate_schedules(callback=None):
    if callback is not None:
        callback()
        return
    _enable_schedules()
    _start_schedules()


def resume_schedule(*, restic_path=None, enable_schedules=None):
    _refuse_restore_barrier()
    config = load_config()
    _run_restic(["cat", "config"], config=config, restic_path=restic_path)
    if enable_schedules is not None:
        enable_schedules()
    else:
        _activate_schedules()
    return True


def _request_path(request_id):
    if not isinstance(request_id, str) or _SAFE_ID.fullmatch(request_id) is None:
        raise ValueError("continuity request identifier is invalid")
    return os.path.join(REQUESTS_DIR, request_id + ".json")


def _create_request(action, args, *, request_id=None):
    if action not in _ACTIONS or not isinstance(args, dict):
        raise ValueError("continuity request is invalid")
    request_id = request_id or uuid.uuid4().hex
    request = {
        "schema": REQUEST_SCHEMA,
        "id": request_id,
        "created_at": _now(),
        "action": action,
        "args": args,
    }
    _write_exclusive(_request_path(request_id), _canonical_bytes(request),
                     0o600)
    return request


def _load_request(path):
    path = os.path.abspath(path)
    if os.path.dirname(path) != os.path.abspath(REQUESTS_DIR):
        raise ValueError("continuity request is outside the request spool")
    value = _read_json(path, "continuity request")
    if not isinstance(value, dict) \
            or set(value) != {"schema", "id", "created_at", "action", "args"} \
            or value.get("schema") != REQUEST_SCHEMA \
            or value.get("action") not in _ACTIONS \
            or not isinstance(value.get("args"), dict) \
            or path != os.path.abspath(_request_path(value.get("id"))):
        raise ValueError("continuity request schema is invalid")
    if value["action"] == "apply":
        _restore_request_binding(value["args"])
    return value


def _validate_confirmation(value):
    required = {"schema_version", "phrase", "snapshot_id", "ledger_head",
                "corpus_receipt_re_adopt"}
    if not isinstance(value, dict) or set(value) != required \
            or value.get("schema_version") != CONFIRMATION_SCHEMA_VERSION \
            or value.get("phrase") != "RESTORE" \
            or value.get("corpus_receipt_re_adopt") is not True:
        raise ValueError("restore confirmation schema is invalid")
    _validate_text(value.get("snapshot_id"), "confirmed snapshot")
    _validate_text(value.get("ledger_head"), "confirmed ledger head")
    return value


def _restore_request_binding(args):
    """Validate the durable apply request without touching external media."""
    required = {
        "prepared_id", "snapshot_id", "capsule_id", "manifest_sha256",
        "confirmation", "identity_key_file", "repository",
        "environment_file", "repository_id", "configured_at",
        "target_public_key", "restored_public_key",
    }
    if not isinstance(args, dict) or set(args) != required:
        raise ValueError("restore request argument schema is invalid")
    for key in ("prepared_id", "snapshot_id", "capsule_id",
                "manifest_sha256", "repository_id", "target_public_key",
                "restored_public_key"):
        value = _validate_text(args.get(key), "restore request " + key)
        if _SAFE_ID.fullmatch(value) is None:
            raise ValueError("restore request binding is malformed")
    _validate_text(args.get("repository"), "restore request repository")
    _validate_text(args.get("configured_at"),
                   "restore request configuration timestamp")
    environment_file = args.get("environment_file")
    if not isinstance(environment_file, str) \
            or (environment_file and not os.path.isabs(environment_file)):
        raise ValueError("restore request environment binding is malformed")
    identity_key_file = args.get("identity_key_file")
    if identity_key_file is not None \
            and (not isinstance(identity_key_file, str)
                 or not identity_key_file
                 or not os.path.isabs(identity_key_file)):
        raise ValueError("restore request identity path is malformed")
    _validate_confirmation(args.get("confirmation"))
    return {
        key: args[key] for key in (
            "prepared_id", "snapshot_id", "capsule_id",
            "manifest_sha256", "repository", "environment_file",
            "repository_id", "configured_at", "target_public_key",
            "restored_public_key")
    }


def _refuse_restore_barrier():
    if sialib.restore_barrier_active():
        raise BlockedError(
            "An interrupted restore barrier requires `sia restore recover`.")


def _request_unit_active(operation, expected_kind):
    if not isinstance(operation, dict) \
            or operation.get("kind") != expected_kind \
            or operation.get("phase") not in {"accepted", "running"}:
        return False
    request_id = operation.get("request_id")
    if not isinstance(request_id, str) \
            or _SAFE_ID.fullmatch(request_id) is None:
        return False
    try:
        request = _load_request(_request_path(request_id))
    except (OSError, TypeError, ValueError):
        return False
    if _ACTION_KIND.get(request["action"]) != expected_kind:
        return False
    return _request_id_active(request_id)


def _request_id_active(request_id):
    if not isinstance(request_id, str) \
            or _SAFE_ID.fullmatch(request_id) is None:
        return False
    result = sialib._run_bounded_text_process(
        ["systemctl", "--user", "show",
         "sia-continuity-" + request_id + ".service",
         "--property=LoadState", "--property=ActiveState",
         "--property=Job"], env=None,
        timeout=sialib.JOURNAL_TIMEOUT_SECONDS, cwd=None,
        label="continuity request liveness",
        output_limit=sialib.MAX_CONFIG_BYTES)
    if result.returncode != 0:
        raise BlockedError(
            "Continuity worker liveness could not be established.")
    fields = {}
    for line in result.stdout.splitlines():
        key, marker, value = line.partition("=")
        if not marker or key not in {"LoadState", "ActiveState", "Job"} \
                or key in fields:
            raise BlockedError(
                "Continuity worker liveness response is malformed.")
        fields[key] = value
    if set(fields) != {"LoadState", "ActiveState", "Job"}:
        raise BlockedError(
            "Continuity worker liveness response is incomplete.")
    if fields["Job"]:
        return True
    if fields["LoadState"] == "not-found" \
            and fields["ActiveState"] == "inactive":
        return False
    if fields["LoadState"] != "loaded":
        raise BlockedError(
            "Continuity worker unit load state is unsafe.")
    if fields["ActiveState"] in {
            "active", "activating", "reloading", "deactivating"}:
        return True
    if fields["ActiveState"] in {"inactive", "failed"}:
        return False
    raise BlockedError(
        "Continuity worker liveness state is not terminal.")


def _retire_request(request):
    path = _request_path(request["id"])
    current = _load_request(path)
    if current != request:
        raise ValueError("continuity request changed before retirement")
    _retire_private_file(path, REQUESTS_DIR)


def _retire_request_artifacts(request, *, include_apply=False):
    if request.get("action") == "apply" and not include_apply:
        return
    if request.get("action") == "upload":
        capsule = os.path.join(
            CAPSULES_DIR, ".capsule-" + request["id"])
        if os.path.lexists(capsule):
            _retire_private_tree(capsule, CAPSULES_DIR)
    if request.get("action") == "prepare":
        stage = os.path.join(PREPARED_DIR, ".stage-" + request["id"])
        if os.path.lexists(stage):
            _retire_private_tree(stage, PREPARED_DIR)
    if os.path.lexists(_request_path(request["id"])):
        _retire_request(request)


def load_supervisor_debt():
    try:
        value = _read_json(SUPERVISOR_PATH, "restore supervisor debt")
    except FileNotFoundError:
        return None
    required = {
        "schema", "kind", "request_path", "request_id", "prepared_id",
        "snapshot_id", "capsule_id", "manifest_sha256", "phase",
        "child_code", "restart_pid", "runtime_path", "runtime_device",
        "runtime_inode", "repository", "environment_file",
        "repository_id", "configured_at", "target_public_key",
        "restored_public_key",
    }
    if not isinstance(value, dict) or set(value) != required \
            or value.get("schema") != SUPERVISOR_SCHEMA \
            or value.get("kind") not in {"restore-apply", "restore-recover"} \
            or value.get("phase") not in {
                "accepted", "child-running", "child-finished",
                "restart-starting", "restart-attested", "restart-failed"}:
        raise ValueError("restore supervisor debt is malformed")
    for key in required:
        if key in {"request_path", "prepared_id", "snapshot_id",
                   "capsule_id", "manifest_sha256", "repository",
                   "environment_file", "repository_id", "configured_at",
                   "target_public_key", "restored_public_key"} \
                and value.get("kind") == "restore-recover":
            if value.get(key) != "":
                raise ValueError("restore recovery debt has unsafe binding")
        elif key == "environment_file" and value.get(key) == "":
            continue
        else:
            _validate_text(value.get(key), "restore supervisor " + key)
    if _SAFE_ID.fullmatch(value["request_id"]) is None \
            or not os.path.isabs(value["runtime_path"]) \
            or not value["runtime_device"].isascii() \
            or not value["runtime_device"].isdigit() \
            or not value["runtime_inode"].isascii() \
            or not value["runtime_inode"].isdigit():
        raise ValueError("restore supervisor debt binding is invalid")
    if value["phase"] == "restart-attested":
        if not value["restart_pid"].isascii() \
                or not value["restart_pid"].isdigit() \
                or value["restart_pid"] == "0":
            raise ValueError("restore supervisor PID attestation is invalid")
    elif value["restart_pid"] != "pending" \
            and (not value["restart_pid"].isascii()
                 or not value["restart_pid"].isdigit()
                 or value["restart_pid"] == "0"):
        raise ValueError("restore supervisor PID state is invalid")
    if value["kind"] == "restore-apply" \
            and (_SAFE_ID.fullmatch(value["prepared_id"]) is None
                 or _SAFE_ID.fullmatch(value["capsule_id"]) is None
                 or _SAFE_ID.fullmatch(value["manifest_sha256"]) is None
                 or _SAFE_ID.fullmatch(value["repository_id"]) is None
                 or _SAFE_ID.fullmatch(value["target_public_key"]) is None
                 or _SAFE_ID.fullmatch(value["restored_public_key"]) is None
                 or os.path.abspath(value["request_path"]) !=
                    os.path.abspath(_request_path(value["request_id"]))):
        raise ValueError("restore supervisor apply binding is invalid")
    if value["kind"] == "restore-apply":
        _validate_repository(value["repository"])
        if value["environment_file"]:
            _validate_environment_file(value["environment_file"])
    return value


def _create_supervisor_intent(request, prepared_id):
    binding = _restore_request_binding(request.get("args"))
    if binding["prepared_id"] != prepared_id:
        raise ValueError("restore supervisor prepared binding changed")
    prepared = load_prepared(prepared_id)
    config = load_config()
    expected_binding = {
        "prepared_id": prepared_id,
        "snapshot_id": prepared["snapshot_id"],
        "capsule_id": prepared["capsule_id"],
        "manifest_sha256": prepared["manifest_sha256"],
        "repository": config["repository"],
        "environment_file": config["environment_file"] or "",
        "repository_id": config["repository_id"],
        "configured_at": config["created_at"],
        "target_public_key": config["brain_public_key"],
        "restored_public_key": prepared["public_key"],
    }
    if binding != expected_binding:
        raise BlockedError("restore supervisor repository binding changed")
    main = sys.modules.get("__main__")
    runtime_path = os.path.abspath(str(getattr(main, "__file__", "")))
    info = os.lstat(runtime_path)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
        raise ValueError("restore runtime generation is unsafe")
    debt = {
        "schema": SUPERVISOR_SCHEMA,
        "kind": "restore-apply",
        "request_path": _request_path(request["id"]),
        "request_id": request["id"],
        "prepared_id": prepared_id,
        "snapshot_id": prepared["snapshot_id"],
        "capsule_id": prepared["capsule_id"],
        "manifest_sha256": prepared["manifest_sha256"],
        "phase": "accepted",
        "child_code": "pending",
        "restart_pid": "pending",
        "runtime_path": runtime_path,
        "runtime_device": str(info.st_dev),
        "runtime_inode": str(info.st_ino),
        "repository": binding["repository"],
        "environment_file": binding["environment_file"],
        "repository_id": binding["repository_id"],
        "configured_at": binding["configured_at"],
        "target_public_key": binding["target_public_key"],
        "restored_public_key": binding["restored_public_key"],
    }
    _write_exclusive(SUPERVISOR_PATH, _canonical_bytes(debt), 0o600)
    return debt


def _retire_supervisor_debt(debt):
    current = load_supervisor_debt()
    if current != debt:
        raise ValueError("restore supervisor debt changed")
    _retire_private_file(SUPERVISOR_PATH, ROOT)


def _reconcile_configured_request(request):
    """Finish setup/connect only after probe, enable, and start are durable."""
    if request.get("action") not in {"setup", "connect"}:
        raise ValueError("configuration reconciliation action is invalid")
    args = request["args"]
    expected_repository = _validate_repository(args.get("repository"))
    expected_environment = args.get("environment_file")
    if expected_environment is not None:
        expected_environment = _validate_environment_file(
            expected_environment)
    config_exists = os.path.lexists(CONFIG_PATH)
    key_exists = os.path.lexists(KEY_PATH)
    if not config_exists:
        recovery_name = ("recovery_key_out"
                         if request["action"] == "setup"
                         else "recovery_key_file")
        recovery_path = _protected_output(
            args.get(recovery_name), "recovery-key file")
        try:
            recovery_key = _read_regular(
                recovery_path, "recovery-key file", private=True,
                maximum=sialib.MAX_CONFIG_BYTES)
        except FileNotFoundError:
            recovery_key = None
        if request["action"] == "connect" and recovery_key is None:
            raise BlockedError(
                "Interrupted repository connection lost its offline "
                "recovery-key input; the durable request was retained.")
        if recovery_key is not None and not recovery_key.strip():
            raise BlockedError(
                "Interrupted repository setup has an empty recovery key.")
        staged_paths = []
        for name in _bounded_private_names(
                ROOT, "continuity state root"):
            if not name.startswith(".repository-key-stage-"):
                continue
            stage = os.path.join(ROOT, name)
            staged = _read_regular(
                stage, "staged repository key", private=True,
                maximum=sialib.MAX_CONFIG_BYTES)
            if recovery_key is not None \
                    and not secrets.compare_digest(staged, recovery_key):
                raise BlockedError(
                    "Interrupted setup key no longer matches its offline "
                    "recovery copy.")
            staged_paths.append(stage)
        if key_exists:
            local_key = _read_regular(
                KEY_PATH, "repository key", private=True,
                maximum=sialib.MAX_CONFIG_BYTES)
            if recovery_key is None \
                    or not secrets.compare_digest(local_key, recovery_key):
                raise BlockedError(
                    "Interrupted setup local key cannot be retired without "
                    "its matching offline recovery copy.")
            _retire_private_file(KEY_PATH, ROOT)
        for stage in staged_paths:
            if os.path.lexists(stage):
                _retire_private_file(stage, ROOT)
        try:
            previous = read_status()
            latest = previous.get("latest")
            prepared = previous.get("prepared")
        except (OSError, ValueError):
            latest = None
            prepared = None
        _publish_status(
            state="blocked",
            detail=(
                "Interrupted repository setup was safely retired before "
                "configuration publication. Reconnect with the preserved "
                "offline recovery key, or rerun setup with fresh offline "
                "destinations if no key was exported."),
            repository_display="External recovery repository",
            latest=latest, prepared=prepared,
            operation=_operation(
                request["id"], _ACTION_KIND[request["action"]], "blocked"))
        _retire_request(request)
        return
    if not key_exists:
        raise BlockedError(
            "Configured continuity repository is missing its local key; "
            "reconnect requires explicit operator recovery.")
    config = load_config()
    if config["repository"] != expected_repository \
            or config["environment_file"] != expected_environment:
        raise BlockedError(
            "Configured repository changed after its durable request.")
    # resume_schedule performs a fresh repository probe, then enables and
    # starts both persistent timers. Any failure leaves this one request in
    # place so the next admission retries the idempotent sequence.
    resume_schedule()
    try:
        previous = read_status()
        latest = previous.get("latest")
        prepared = previous.get("prepared")
    except (OSError, ValueError):
        latest = None
        prepared = None
    copy_verified = _latest_is_protecting(latest)
    _publish_status(
        state="verified" if copy_verified else "recovery-only",
        detail="Configured repository reconciled; persistent schedules "
               "are active after a fresh probe.",
        repository_display="External recovery repository",
        latest=latest, prepared=prepared,
        operation=_operation(
            request["id"], _ACTION_KIND[request["action"]], "verified"))
    _retire_request(request)


def _reconcile_inactive_spools():
    """Bound crash debris while refusing to race any live worker unit."""
    _ensure_layout()
    with _exclusive_lock_nonblocking(WORKER_LOCK):
        for name in _bounded_private_names(
                REQUESTS_DIR, "continuity request spool"):
            if not name.endswith(".json"):
                raise BlockedError("Continuity request spool needs review.")
            request_id = name.removesuffix(".json")
            request = _load_request(_request_path(request_id))
            if _request_id_active(request_id):
                raise BlockedError("Another continuity request is active.")
            if request["action"] in {"setup", "connect"}:
                _reconcile_configured_request(request)
                continue
            if request["action"] == "apply":
                status = read_status()
                operation = status.get("operation")
                debt = load_supervisor_debt()
                if debt is not None \
                        and debt.get("request_id") == request_id:
                    raise BlockedError(
                        "Restore supervisor finalization is still pending.")
                if isinstance(operation, dict) \
                        and operation.get("request_id") == request_id \
                        and operation.get("kind") == "restore-apply" \
                        and operation.get("phase") == "running":
                    if debt is None \
                            or debt.get("request_id") != request_id:
                        raise BlockedError(
                            "Restore supervisor correlation requires review.")
                    raise BlockedError(
                        "Restore supervisor finalization is still pending.")
                if debt is None and isinstance(operation, dict) \
                        and operation.get("request_id") == request_id \
                        and operation.get("kind") == "restore-apply" \
                        and operation.get("phase") in {
                            "accepted", "running", "blocked"}:
                    _publish_status(
                        state="blocked",
                        detail="Restore request ended before supervisor "
                               "authority was published; no live mutation "
                               "was launched.",
                        operation=_operation(
                            request_id, "restore-apply", "blocked",
                            prepared_id=operation.get("prepared_id", "")))
            _retire_request_artifacts(request, include_apply=True)

        for name in _bounded_private_names(
                CAPSULES_DIR, "continuity capsule spool"):
            path = os.path.join(CAPSULES_DIR, name)
            if not (name.startswith(".capsule-")
                    or name.startswith(".sia-capsule-stage-")):
                raise BlockedError("Continuity capsule spool needs review.")
            _retire_private_tree(path, CAPSULES_DIR)

        for name in _bounded_private_names(
                CHECKS_DIR, "continuity check spool"):
            path = os.path.join(CHECKS_DIR, name)
            if not name.startswith(".check-"):
                raise BlockedError("Continuity check spool needs review.")
            _retire_private_tree(path, CHECKS_DIR)

        status = read_status()
        current = status.get("prepared")
        keep = (current.get("prepared_id")
                if isinstance(current, dict) else None)
        for name in _bounded_private_names(
                PREPARED_DIR, "prepared restore spool"):
            path = os.path.join(PREPARED_DIR, name)
            if name.startswith(".stage-"):
                _retire_private_tree(path, PREPARED_DIR)
            elif _SAFE_ID.fullmatch(name) is not None and name != keep:
                _retire_private_tree(path, PREPARED_DIR)
            elif name != keep:
                raise BlockedError("Prepared restore spool needs review.")

        for name in _bounded_private_names(ROOT, "continuity state root"):
            if name.startswith(".repository-key-stage-"):
                _retire_private_file(os.path.join(ROOT, name), ROOT)


def launch_request(request, *, runner=None):
    request_path = _request_path(request["id"])
    hidden_command = ("_continuity-restore-worker"
                      if request["action"] == "apply"
                      else "_continuity-worker")
    command = [
        "systemd-run", "--user", "--collect", "--quiet",
        "--property=Type=exec", "--property=UMask=0077",
        "--property=NoNewPrivileges=yes",
        "--unit=sia-continuity-" + request["id"],
        STABLE_CLI_PATH, hidden_command, request_path,
    ]
    if runner is not None:
        result = runner(command)
    else:
        result = sialib._run_bounded_text_process(
            command, env=None, timeout=sialib.JOURNAL_TIMEOUT_SECONDS,
            cwd=None, label="continuity worker launch",
            output_limit=sialib.MAX_CONFIG_BYTES)
    if result.returncode != 0:
        raise RuntimeError("continuity worker could not be launched")
    return request


def _queue(action, args, *, request_id=None, runner=None,
           prepared_id=""):
    _ensure_layout()
    request = _create_request(action, args, request_id=request_id)
    kind = _ACTION_KIND[action]
    state = "restoring" if action == "apply" else "queued"
    try:
        # The non-green accepted record precedes any restore supervisor debt.
        # A crash can therefore never leave authoritative mutation debt while
        # the last durable UI state still claims recovery readiness.
        _publish_status(
            state=state, detail="Continuity request accepted.",
            repository_display="External recovery repository",
            operation=_operation(request["id"], kind, "accepted",
                                 prepared_id=prepared_id))
    except Exception:
        _retire_request_artifacts(request, include_apply=True)
        raise
    if action == "apply":
        try:
            _create_supervisor_intent(request, prepared_id)
        except Exception:
            try:
                _publish_status(
                    state="blocked",
                    detail="Restore supervisor intent could not be "
                           "published; no live mutation was launched.",
                    repository_display="External recovery repository",
                    operation=_operation(
                        request["id"], kind, "blocked",
                        prepared_id=prepared_id))
            finally:
                # A publication primitive may fail after its atomic rename.
                # Retire the request only when no supervisor authority is
                # observable; otherwise preserve their exact correlation.
                try:
                    debt = load_supervisor_debt()
                except (OSError, ValueError):
                    debt = "unsafe"
                if debt is None:
                    _retire_request_artifacts(request, include_apply=True)
            raise
    try:
        launch_request(request, runner=runner)
    except Exception:
        _publish_status(
            state="blocked",
            detail="Worker launch outcome is ambiguous; the durable request "
                   "is retained for exact liveness reconciliation.",
            operation=_operation(request["id"], kind, "blocked",
                                 prepared_id=prepared_id))
        # A bounded systemd-run client can time out after the user manager
        # accepted the transient unit. Never erase authority underneath that
        # potentially live worker. The next admission holds REQUEST_LOCK,
        # checks the exact unit, and retires this single intent only when it is
        # deterministically inactive.
        raise
    return request


def queue_setup(repository, recovery_key_out, identity_key_out,
                environment_file=None, *, runner=None):
    _refuse_restore_barrier()
    args = {
        "repository": _validate_repository(repository),
        "recovery_key_out": _protected_output(
            recovery_key_out, "recovery-key output"),
        "identity_key_out": _protected_output(
            identity_key_out, "identity-key output"),
        "environment_file": (None if environment_file is None else
                             _validate_environment_file(environment_file)),
    }
    if os.path.abspath(recovery_key_out) == os.path.abspath(identity_key_out):
        raise ValueError("recovery and identity outputs must be different")
    _reject_local_repository_secrets(
        args["repository"], [args["recovery_key_out"],
                             args["identity_key_out"]],
        args["environment_file"])
    if os.path.lexists(CONFIG_PATH):
        raise ValueError("continuity is already configured")
    with _exclusive_lock(REQUEST_LOCK):
        _reconcile_inactive_spools()
        if os.path.lexists(CONFIG_PATH):
            raise ValueError("continuity is already configured")
        return _queue("setup", args, runner=runner)


def queue_connect(repository, recovery_key_file, environment_file=None,
                  *, runner=None):
    _refuse_restore_barrier()
    _protected_output(recovery_key_file, "recovery-key file")
    _read_regular(recovery_key_file, "recovery-key file", private=True,
                  maximum=sialib.MAX_CONFIG_BYTES)
    args = {
        "repository": _validate_repository(repository),
        "recovery_key_file": recovery_key_file,
        "environment_file": (None if environment_file is None else
                             _validate_environment_file(environment_file)),
    }
    _reject_local_repository_secrets(
        args["repository"], [args["recovery_key_file"]],
        args["environment_file"])
    if os.path.lexists(CONFIG_PATH):
        raise ValueError("continuity is already configured")
    with _exclusive_lock(REQUEST_LOCK):
        _reconcile_inactive_spools()
        if os.path.lexists(CONFIG_PATH):
            raise ValueError("continuity is already configured")
        return _queue("connect", args, runner=runner)


def queue_backup(*, scheduled=False, runner=None):
    _refuse_restore_barrier()
    load_config()
    _ensure_layout()
    with _exclusive_lock(REQUEST_LOCK):
        current = read_status()
        operation = current.get("operation")
        if scheduled and _request_unit_active(operation, "backup-upload"):
            return None
        _reconcile_inactive_spools()
        # The durable worker owns freeze as well as upload. Once the exact
        # Type=exec handoff returns, closing the caller cannot interrupt the
        # capsule capture.
        return _queue("upload", {"scheduled": bool(scheduled)},
                      runner=runner)


def queue_check(*, scheduled=False, runner=None):
    _refuse_restore_barrier()
    load_config()
    with _exclusive_lock(REQUEST_LOCK):
        current = read_status()
        operation = current.get("operation")
        if scheduled and _request_unit_active(operation, "backup-check"):
            return None
        _reconcile_inactive_spools()
        return _queue("check", {"scheduled": bool(scheduled)}, runner=runner)


def queue_prepare(snapshot_id, *, runner=None):
    _refuse_restore_barrier()
    load_config()
    _validate_text(snapshot_id, "snapshot identifier")
    with _exclusive_lock(REQUEST_LOCK):
        _reconcile_inactive_spools()
        _retire_current_prepared()
        return _queue("prepare", {"snapshot_id": snapshot_id}, runner=runner)


def _prepared_path(prepared_id):
    if not isinstance(prepared_id, str) \
            or _SAFE_ID.fullmatch(prepared_id) is None:
        raise ValueError("prepared identifier is invalid")
    return os.path.join(PREPARED_DIR, prepared_id, "prepared.json")


def _retire_current_prepared():
    status = read_status()
    prepared = status.get("prepared")
    if prepared is None:
        return
    prepared_id = prepared.get("prepared_id")
    path = os.path.dirname(_prepared_path(prepared_id))
    if os.path.lexists(path):
        _retire_private_tree(path, PREPARED_DIR)
    _publish_status(prepared=None)


def load_prepared(prepared_id):
    value = _read_json(_prepared_path(prepared_id), "prepared restore")
    required = {
        "schema", "prepared_id", "snapshot_id", "capsule_id",
        "created_at", "classification", "profile", "corpus_head",
        "ledger_head", "target_ledger_head", "identity_matches",
        "public_key", "manifest_sha256", "capsule_path",
    }
    if not isinstance(value, dict) or set(value) != required \
            or value.get("schema") != siacapsule.PREPARED_SCHEMA \
            or value.get("prepared_id") != prepared_id \
            or not isinstance(value.get("identity_matches"), bool):
        raise ValueError("prepared restore schema is invalid")
    for key in required - {"identity_matches"}:
        if not isinstance(value.get(key), str) or not value[key]:
            raise ValueError("prepared restore field is invalid")
    expected_root = os.path.abspath(os.path.join(PREPARED_DIR, prepared_id))
    capsule_path = os.path.abspath(value["capsule_path"])
    if os.path.commonpath((expected_root, capsule_path)) != expected_root:
        raise ValueError("prepared capsule is outside its prepared tree")
    return value


def _prepared_status(value):
    """Publish the target-head ceremony view, not the capsule source head."""
    return {
        "prepared_id": value["prepared_id"],
        "snapshot_id": value["snapshot_id"],
        "created_at": value["created_at"],
        "readiness": value["classification"],
        "profile": value["profile"],
        "ledger_head": value["target_ledger_head"],
        "identity_matches": value["identity_matches"],
    }


def _read_confirmation(stream):
    line = stream.readline(sialib.MAX_CONFIG_BYTES + 1)
    if len(line) > sialib.MAX_CONFIG_BYTES or not line.endswith(b"\n"):
        raise ValueError("restore confirmation exceeds its line boundary")
    if line.count(b"\n") != 1:
        raise ValueError("restore confirmation must be exactly one line")
    body = line[:-1]
    if not body or body.strip() != body:
        raise ValueError("restore confirmation has trailing whitespace")
    # Quickshell deliberately keeps its stdin pipe open after writing the
    # record.  Reject already-buffered extra records without waiting for EOF.
    try:
        descriptor = stream.fileno()
    except (AttributeError, OSError):
        if stream.read(1):
            raise ValueError("restore confirmation contains trailing bytes")
    else:
        blocking = os.get_blocking(descriptor)
        try:
            os.set_blocking(descriptor, False)
            try:
                extra = (stream.peek(1)[:1] if hasattr(stream, "peek")
                         else os.read(descriptor, 1))
            except BlockingIOError:
                extra = b""
        finally:
            os.set_blocking(descriptor, blocking)
        if extra:
            raise ValueError("restore confirmation contains trailing bytes")
    value = _decode_json(body, "restore confirmation")
    return _validate_confirmation(value)


def queue_apply(prepared_id, confirmation, identity_key_file=None,
                *, runner=None):
    if os.path.lexists(siacapsule.RESTORE_BARRIER):
        raise BlockedError(
            "An interrupted restore barrier requires recovery before apply.")
    prepared = load_prepared(prepared_id)
    if confirmation.get("snapshot_id") != prepared["snapshot_id"]:
        raise ValueError("confirmed snapshot does not match prepared restore")
    _sequence, current_head = sialib.ledger_head()
    if confirmation.get("ledger_head") != current_head \
            or prepared["target_ledger_head"] != current_head:
        raise ValueError("current ledger head changed after preparation")
    verified = siacapsule.verify(prepared["capsule_path"])
    if verified["capsule_id"] != prepared["capsule_id"] \
            or verified["manifest_sha256"] != prepared["manifest_sha256"]:
        raise ValueError("prepared capsule changed after verification")
    if not prepared["identity_matches"]:
        if identity_key_file is None:
            raise ValueError("offline identity recovery file is required")
        _protected_output(identity_key_file, "identity recovery file")
        siacapsule.validate_identity_key(identity_key_file,
                                         prepared["public_key"])
    elif identity_key_file is not None:
        _protected_output(identity_key_file, "identity recovery file")
    config = load_config()
    args = {
        "prepared_id": prepared_id,
        "snapshot_id": prepared["snapshot_id"],
        "capsule_id": prepared["capsule_id"],
        "manifest_sha256": prepared["manifest_sha256"],
        "confirmation": confirmation,
        "identity_key_file": identity_key_file,
        "repository": config["repository"],
        "environment_file": config["environment_file"] or "",
        "repository_id": config["repository_id"],
        "configured_at": config["created_at"],
        "target_public_key": config["brain_public_key"],
        "restored_public_key": prepared["public_key"],
    }
    _restore_request_binding(args)
    with _exclusive_lock(REQUEST_LOCK):
        _reconcile_inactive_spools()
        return _queue("apply", args, runner=runner,
                      prepared_id=prepared_id)


def _json_documents(text, label):
    documents = []
    for line in text.splitlines():
        if not line.strip():
            continue
        documents.append(_decode_json(line.encode("utf-8"), label))
    return documents


def _verification_path(snapshot_id):
    if not isinstance(snapshot_id, str) \
            or _SAFE_ID.fullmatch(snapshot_id) is None:
        raise ValueError("snapshot identifier is invalid")
    return os.path.join(VERIFICATIONS_DIR, snapshot_id + ".json")


def _load_verification(snapshot_id, *, config=None):
    config = load_config() if config is None else _validate_config(config)
    try:
        value = _read_json(
            _verification_path(snapshot_id), "snapshot verification")
    except FileNotFoundError:
        return None
    required = {
        "schema", "snapshot_id", "capsule_id", "manifest_sha256",
        "classification", "profile", "public_key", "repository_id",
        "verified_at",
    }
    if not isinstance(value, dict) or set(value) != required \
            or value.get("schema") != VERIFICATION_SCHEMA \
            or value.get("snapshot_id") != snapshot_id \
            or value.get("classification") not in {"ready", "recovery-only"} \
            or value.get("profile") != PROFILE \
            or value.get("repository_id") != config["repository_id"]:
        raise ValueError("snapshot verification receipt is malformed")
    for key in {"snapshot_id", "capsule_id", "manifest_sha256",
                "public_key", "repository_id", "verified_at"}:
        _validate_text(value.get(key), "snapshot verification " + key)
    return value


def _record_verification(snapshot_id, verified, *, config=None):
    config = load_config() if config is None else _validate_config(config)
    classification = verified.get("classification")
    if classification not in {"ready", "recovery-only"}:
        raise ValueError("verified capsule classification is invalid")
    document = {
        "schema": VERIFICATION_SCHEMA,
        "snapshot_id": snapshot_id,
        "capsule_id": _validate_text(
            verified.get("capsule_id"), "verified capsule identity"),
        "manifest_sha256": _validate_text(
            verified.get("manifest_sha256"), "verified manifest digest"),
        "classification": classification,
        "profile": PROFILE,
        "public_key": _validate_text(
            verified.get("public_key"), "verified capsule public identity"),
        "repository_id": config["repository_id"],
        "verified_at": _now(),
    }
    path = _verification_path(snapshot_id)
    existing = _load_verification(snapshot_id, config=config)
    if existing is not None:
        comparable = set(document) - {"verified_at"}
        if any(existing[key] != document[key] for key in comparable):
            raise ValueError(
                "snapshot verification conflicts with its durable receipt")
        return existing
    _write_exclusive(path, _canonical_bytes(document), 0o600)
    return document


def _snapshot_rows(*, restic_path=None, latest=False, snapshot_id=None,
                   matching_identity=False):
    config = load_config()
    tag_query = "sia-capsule"
    if matching_identity:
        tag_query += ",sia-brain=" + config["brain_public_key"]
    arguments = ["snapshots", "--json", "--tag", tag_query]
    if snapshot_id is not None:
        if not isinstance(snapshot_id, str) \
                or _SAFE_ID.fullmatch(snapshot_id) is None:
            raise ValueError("snapshot identifier is invalid")
        arguments.append(snapshot_id)
    else:
        arguments.extend([
            "--latest",
            LATEST_SNAPSHOT_COUNT if latest else LIST_SNAPSHOT_COUNT,
        ])
    raw = _run_restic(
        arguments, config=config, restic_path=restic_path)
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise ValueError("restic snapshot response is malformed") from exc
    rows = value.get("snapshots") if isinstance(value, dict) else value
    if not isinstance(rows, list):
        raise ValueError("restic snapshot response is malformed")
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tags = row.get("tags", [])
        snapshot_id = row.get("id")
        created = row.get("time")
        if not isinstance(tags, list) or "sia-capsule" not in tags \
                or not isinstance(snapshot_id, str) \
                or _SAFE_ID.fullmatch(snapshot_id) is None \
                or not isinstance(created, str):
            continue
        brain_tags = [tag.split("=", 1)[1] for tag in tags
                      if isinstance(tag, str)
                      and tag.startswith("sia-brain=")]
        if len(brain_tags) > 1:
            raise ValueError("snapshot repeats its SIA identity tag")
        brain_public_key = brain_tags[0] if brain_tags else ""
        if brain_public_key and _SAFE_ID.fullmatch(brain_public_key) is None:
            raise ValueError("snapshot SIA identity tag is malformed")
        identity_matches = bool(brain_public_key) and secrets.compare_digest(
            brain_public_key, config["brain_public_key"])
        if matching_identity and not identity_matches:
            raise ValueError("restic identity filter returned a foreign snapshot")
        verification = _load_verification(snapshot_id, config=config)
        readiness = next((tag.split("=", 1)[1] for tag in tags
                          if isinstance(tag, str)
                          and tag.startswith("sia-readiness=")),
                         "unknown")
        if verification is not None \
                and (verification["classification"] != readiness
                     or (brain_public_key
                         and verification["public_key"] != brain_public_key)):
            raise ValueError(
                "snapshot tag conflicts with its verification receipt")
        result.append({
            "snapshot_id": snapshot_id,
            "created_at": created,
            "verified": verification is not None,
            "readiness": readiness,
            "profile": PROFILE,
            "identity_matches": identity_matches,
        })
    return sorted(result, key=lambda row: (row["created_at"],
                                           row["snapshot_id"]))


def list_snapshots(*, restic_path=None):
    _refuse_restore_barrier()
    return _snapshot_rows(restic_path=restic_path)


def _perform_setup(args, *, restic_path=None, enable_schedules=None):
    if os.path.lexists(CONFIG_PATH):
        raise ValueError("continuity is already configured")
    config = _repository_config(args.get("repository"),
                                args.get("environment_file"))
    recovery_out = _protected_output(args.get("recovery_key_out"),
                                     "recovery-key output")
    identity_out = _protected_output(args.get("identity_key_out"),
                                     "identity-key output")
    _reject_local_repository_secrets(
        config["repository"], [recovery_out, identity_out],
        config.get("environment_file"))
    _parse_environment(config.get("environment_file"))
    if os.path.lexists(KEY_PATH):
        raise BlockedError(
            "Partial continuity setup exists; reconnect with its recovery key.")
    key = (secrets.token_urlsafe() + "\n").encode("ascii")
    stage = os.path.join(ROOT, ".repository-key-stage-" + uuid.uuid4().hex)
    _write_exclusive(stage, key, 0o600)
    try:
        _write_external_exclusive(recovery_out, key, 0o600)
        siacapsule.export_identity_key(identity_out)
        _run_restic(["init"], config=config, key_path=stage,
                    restic_path=restic_path)
        raw_config = _run_restic(
            ["cat", "config"], config=config, key_path=stage,
            restic_path=restic_path)
        config = {**config, "repository_id":
                  _repository_identity(raw_config)}
        # Arm both persistent timers only after the initialized repository
        # answers through the staged key, but before CONFIG becomes a public
        # protection claim. A power cut can leave harmless timers whose
        # ConditionPathExists is false; it cannot leave configured protection
        # silently disabled.
        _activate_schedules(enable_schedules)
        _commit_staged_key(stage)
        _write_exclusive(CONFIG_PATH, _canonical_bytes(config), 0o600)
    finally:
        if os.path.lexists(stage):
            _retire_private_file(stage, ROOT)
    return None


def _perform_connect(args, *, restic_path=None, enable_schedules=None):
    if os.path.lexists(CONFIG_PATH):
        raise ValueError("continuity is already configured")
    config = _repository_config(args.get("repository"),
                                args.get("environment_file"))
    recovery = _protected_output(args.get("recovery_key_file"),
                                 "recovery-key file")
    _reject_local_repository_secrets(
        config["repository"], [recovery],
        config.get("environment_file"))
    key = _read_regular(recovery, "recovery-key file", private=True,
                        maximum=sialib.MAX_CONFIG_BYTES)
    if not key.strip():
        raise ValueError("recovery-key file is empty")
    stage = os.path.join(ROOT, ".repository-key-stage-" + uuid.uuid4().hex)
    _write_exclusive(stage, key, 0o600)
    try:
        raw_config = _run_restic(
            ["cat", "config"], config=config, key_path=stage,
            restic_path=restic_path)
        config = {**config, "repository_id":
                  _repository_identity(raw_config)}
        _run_restic(["check"], config=config, key_path=stage,
                    restic_path=restic_path)
        _activate_schedules(enable_schedules)
        _commit_staged_key(stage)
        _write_exclusive(CONFIG_PATH, _canonical_bytes(config), 0o600)
    finally:
        if os.path.lexists(stage):
            _retire_private_file(stage, ROOT)
    rows = _snapshot_rows(
        restic_path=restic_path, latest=True, matching_identity=True)
    return rows[-1] if rows else None


def _validate_completed_capsule(path, expected):
    path = os.path.abspath(path)
    if os.path.dirname(path) != os.path.abspath(CAPSULES_DIR) \
            or not os.path.basename(path).startswith(".capsule-"):
        raise ValueError("worker capsule is outside its managed spool")
    if not isinstance(expected, dict) \
            or expected.get("path") != path:
        raise ValueError("completed capsule result is malformed")
    verified = siacapsule.verify(path)
    for key in ("capsule_id", "manifest_sha256", "classification",
                "public_key"):
        if verified.get(key) != expected.get(key):
            raise ValueError("completed capsule identity changed")
    return path, verified


def _perform_upload(args, request_id, *, restic_path=None):
    if set(args) != {"scheduled"} or type(args.get("scheduled")) is not bool:
        raise ValueError("backup capture request is malformed")
    path = os.path.join(CAPSULES_DIR, ".capsule-" + request_id)
    if os.path.lexists(path):
        raise BlockedError("A prior managed capsule requires review.")
    try:
        frozen = siacapsule.freeze(path)
        path, verified = _validate_completed_capsule(path, frozen)
        classification = verified["classification"]
        _publish_status(
            state="uploading",
            detail="Signed portable capsule completed; uploading offsite.",
            repository_display="External recovery repository",
            operation=_operation(
                request_id, "backup-upload", "running"))
        output = _run_restic(
            ["backup", "--json", "--quiet", "--tag", "sia-capsule",
             "--tag", "sia-readiness=" + classification, "--host",
             "sia-continuity", "--tag",
             "sia-brain=" + verified["public_key"],
             os.path.basename(path)],
            cwd=CAPSULES_DIR, restic_path=restic_path)
        snapshot_id = None
        for row in _json_documents(output, "restic backup response"):
            if isinstance(row, dict) \
                    and row.get("message_type") == "summary" \
                    and isinstance(row.get("snapshot_id"), str):
                snapshot_id = row["snapshot_id"]
        if snapshot_id is None or _SAFE_ID.fullmatch(snapshot_id) is None:
            raise ValueError("restic did not return a snapshot identity")
        scheduled = args["scheduled"]
        if not scheduled:
            _run_restic(["check"], restic_path=restic_path)
            restored = _verify_snapshot_offpath(
                snapshot_id, expected=verified, restic_path=restic_path)
        else:
            restored = verified
        result = {
            "snapshot_id": snapshot_id,
            "created_at": _now(),
            "verified": not scheduled,
            "readiness": restored["classification"],
            "profile": PROFILE,
            "identity_matches": True,
        }
    except BaseException:
        if os.path.lexists(path):
            try:
                _retire_private_tree(path, CAPSULES_DIR)
            except Exception:
                pass
        raise
    if os.path.lexists(path):
        _retire_private_tree(path, CAPSULES_DIR)
    return result


def _perform_check(*, restic_path=None):
    _run_restic(["check"], restic_path=restic_path)
    rows = _snapshot_rows(
        restic_path=restic_path, latest=True, matching_identity=True)
    if not rows:
        return None
    latest = rows[-1]
    _verify_snapshot_offpath(
        latest["snapshot_id"], restic_path=restic_path)
    rows = _snapshot_rows(
        restic_path=restic_path, snapshot_id=latest["snapshot_id"])
    return next(row for row in rows
                if row["snapshot_id"] == latest["snapshot_id"])


def _resolve_snapshot(requested, *, restic_path=None):
    if requested == "latest":
        rows = _snapshot_rows(
            restic_path=restic_path, latest=True, matching_identity=True)
        if not rows:
            raise ValueError("repository contains no SIA capsule snapshots")
        return rows[-1]["snapshot_id"]
    if _SAFE_ID.fullmatch(requested) is None:
        raise ValueError("snapshot identifier is invalid")
    rows = _snapshot_rows(
        restic_path=restic_path, snapshot_id=requested)
    matches = [row["snapshot_id"] for row in rows
               if row["snapshot_id"] == requested
               or row["snapshot_id"].startswith(requested)]
    if len(matches) != 1:
        raise ValueError("snapshot identifier is absent or ambiguous")
    return matches[0]


def _preflight_snapshot(snapshot_id, *, restic_path=None):
    """Bound authenticated repository metadata before restic writes bytes."""
    raw = _run_restic(
        ["ls", "--json", snapshot_id], restic_path=restic_path)
    snapshot_seen = False
    paths = {}
    total_bytes = 0
    for document in _json_documents(raw, "restic snapshot listing"):
        if not isinstance(document, dict):
            raise ValueError("restic snapshot listing contains a non-object")
        message_type = document.get("message_type")
        struct_type = document.get("struct_type")
        if message_type is not None and struct_type is not None \
                and message_type != struct_type:
            raise ValueError("restic snapshot listing type fields conflict")
        kind = message_type if message_type is not None else struct_type
        if kind == "snapshot":
            if snapshot_seen or document.get("id") != snapshot_id:
                raise ValueError("restic snapshot listing identity changed")
            tags = document.get("tags")
            if not isinstance(tags, list) or "sia-capsule" not in tags:
                raise ValueError("restic snapshot listing lost its SIA tag")
            snapshot_seen = True
            continue
        if kind != "node":
            raise ValueError("restic snapshot listing has an unknown record")
        node_type = document.get("type")
        path = document.get("path")
        if node_type not in {"file", "dir"} \
                or not isinstance(path, str) or not path.startswith("/") \
                or path.startswith("//") or "\0" in path \
                or posixpath.normpath(path) != path:
            raise ValueError("restic snapshot listing contains an unsafe node")
        relative = path[1:]
        if not relative:
            if node_type != "dir":
                raise ValueError("restic snapshot root is not a directory")
            continue
        components = tuple(relative.split("/"))
        if any(not component or component in {".", ".."}
               for component in components) \
                or len(components) > MAX_SPOOL_DEPTH \
                or len(os.fsencode(relative)) > sialib.MAX_CONFIG_BYTES \
                or relative in paths \
                or len(paths) >= MAX_SPOOL_ENTRIES:
            raise ValueError("restic snapshot listing exceeds path policy")
        size = document.get("size")
        if node_type == "file":
            if isinstance(size, bool) or not isinstance(size, int) or size < 0 \
                    or size > MAX_SPOOL_BYTES - total_bytes:
                raise ValueError("restic snapshot listing exceeds byte policy")
            total_bytes += size
        paths[relative] = node_type
    if not snapshot_seen:
        raise ValueError("restic snapshot listing lacks its snapshot record")
    candidates = set()
    for relative in paths:
        parts = relative.split("/")
        if parts and parts[0].startswith(".capsule-"):
            candidates.add(parts[0])
    if len(candidates) != 1:
        raise ValueError("restic snapshot listing does not contain one capsule")
    capsule = next(iter(candidates))
    if paths.get(capsule + "/" + siacapsule.MANIFEST_NAME) != "file" \
            or paths.get(capsule + "/" + siacapsule.PAYLOAD_NAME) != "dir":
        raise ValueError("restic snapshot listing lacks capsule structure")
    return {"entries": len(paths), "total_bytes": total_bytes,
            "capsule_root": capsule}


def _purge_untrusted_stage(path, authority):
    """Retire one direct spool child without trusting admission metadata."""
    path = os.path.abspath(path)
    authority = os.path.abspath(authority)
    if os.path.dirname(path) != authority:
        raise ValueError("untrusted stage is outside its spool")
    directory_flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                       | getattr(os, "O_CLOEXEC", 0)
                       | getattr(os, "O_NOFOLLOW", 0))

    def purge_directory(parent_fd, name, depth):
        if depth > MAX_SPOOL_DEPTH:
            raise ValueError("untrusted stage exceeds cleanup depth")
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(before.st_mode) or before.st_uid != os.geteuid():
            raise ValueError("untrusted stage directory is unsafe")
        child_fd = os.open(name, directory_flags, dir_fd=parent_fd)
        try:
            opened = os.fstat(child_fd)
            if (opened.st_dev, opened.st_ino) != \
                    (before.st_dev, before.st_ino):
                raise ValueError("untrusted stage directory changed")
            with os.scandir(child_fd) as entries:
                for entry in entries:
                    child_name = entry.name
                    if not child_name or child_name in {".", ".."} \
                            or "/" in child_name or "\0" in child_name:
                        raise ValueError("untrusted stage name is unsafe")
                    observed = os.stat(
                        child_name, dir_fd=child_fd,
                        follow_symlinks=False)
                    if observed.st_uid != os.geteuid():
                        raise ValueError("untrusted stage entry is not owned")
                    if stat.S_ISDIR(observed.st_mode):
                        purge_directory(child_fd, child_name, depth + 1)
                    else:
                        os.unlink(child_name, dir_fd=child_fd)
            os.fsync(child_fd)
        finally:
            os.close(child_fd)
        linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(linked.st_mode) \
                or (linked.st_dev, linked.st_ino) != \
                   (before.st_dev, before.st_ino):
            raise ValueError("untrusted stage directory changed")
        os.rmdir(name, dir_fd=parent_fd)

    authority_fd = os.open(authority, directory_flags)
    try:
        authority_info = os.fstat(authority_fd)
        if not stat.S_ISDIR(authority_info.st_mode) \
                or authority_info.st_uid != os.geteuid():
            raise ValueError("untrusted stage spool is unsafe")
        purge_directory(authority_fd, os.path.basename(path), 0)
        os.fsync(authority_fd)
    finally:
        os.close(authority_fd)


def _find_restored_capsule(root):
    catalog = _catalog_private_tree(root, "restored repository tree")
    candidates = []
    for relative, names in catalog["children"].items():
        manifest = relative + (siacapsule.MANIFEST_NAME,)
        payload = relative + (siacapsule.PAYLOAD_NAME,)
        if siacapsule.MANIFEST_NAME in names \
                and siacapsule.PAYLOAD_NAME in names \
                and catalog["records"].get(manifest, (None,))[0] == "file" \
                and catalog["records"].get(payload, (None,))[0] == \
                    "directory":
            candidates.append(os.path.join(root, *relative))
    if len(candidates) != 1:
        raise ValueError("restored snapshot does not contain one capsule")
    return candidates[0]


def _verify_snapshot_offpath(snapshot_id, *, expected=None,
                             restic_path=None):
    stage = os.path.join(CHECKS_DIR, ".check-" + uuid.uuid4().hex)
    if os.path.lexists(stage):
        raise BlockedError("A repository verification stage already exists.")
    os.mkdir(stage, 0o700)
    try:
        _preflight_snapshot(snapshot_id, restic_path=restic_path)
        restored_root = os.path.join(stage, "restored")
        os.mkdir(restored_root, 0o700)
        _run_restic(["restore", snapshot_id, "--target", restored_root],
                    restic_path=restic_path)
        capsule = _find_restored_capsule(restored_root)
        verified = siacapsule.verify(capsule)
        if expected is not None:
            for key in ("capsule_id", "manifest_sha256", "classification",
                        "public_key"):
                if verified.get(key) != expected.get(key):
                    raise ValueError(
                        "repository snapshot differs from uploaded capsule")
        _record_verification(snapshot_id, verified)
    except BaseException:
        if os.path.lexists(stage):
            try:
                _purge_untrusted_stage(stage, CHECKS_DIR)
            except Exception:
                # Preserve the primary verification refusal. The bounded
                # stage remains the single reconciliation debt and prevents
                # another scheduled restore from accumulating beside it.
                pass
        raise
    if os.path.lexists(stage):
        _retire_private_tree(stage, CHECKS_DIR)
    return verified


def _perform_prepare(args, request_id, *, restic_path=None):
    requested = _validate_text(args.get("snapshot_id"),
                               "snapshot identifier")
    snapshot_id = _resolve_snapshot(requested, restic_path=restic_path)
    stage = os.path.join(PREPARED_DIR, ".stage-" + request_id)
    if os.path.lexists(stage):
        raise BlockedError("A prior prepare stage requires operator review.")
    os.mkdir(stage, 0o700)
    try:
        _preflight_snapshot(snapshot_id, restic_path=restic_path)
        restored = os.path.join(stage, "restored")
        os.mkdir(restored, 0o700)
        _run_restic(["restore", snapshot_id, "--target", restored],
                    restic_path=restic_path)
        capsule = _find_restored_capsule(restored)
        verified = siacapsule.verify(capsule)
        _record_verification(snapshot_id, verified)
        prepared_id = uuid.uuid4().hex
        binding = siacapsule.prepare_binding(
            capsule, prepared_id=prepared_id, snapshot_id=snapshot_id)
        final = os.path.join(PREPARED_DIR, prepared_id)
        final_capsule = os.path.join(final, os.path.relpath(capsule, stage))
        _sequence, target_head = sialib.ledger_head()
        document = {
            **binding,
            "created_at": _now(),
            "profile": PROFILE,
            "target_ledger_head": target_head,
            "identity_matches": siacapsule.identity_matches(binding),
            "capsule_path": final_capsule,
        }
        _write_exclusive(os.path.join(stage, "prepared.json"),
                         _canonical_bytes(document), 0o600)
        rows = _snapshot_rows(
            restic_path=restic_path, snapshot_id=snapshot_id)
        candidate = next(
            row for row in rows if row["snapshot_id"] == snapshot_id)
        _fsync_tree(stage)
        os.rename(stage, final)
        _fsync_dir(PREPARED_DIR)
        return {**document, "_latest_status": candidate}
    except BaseException:
        if os.path.lexists(stage):
            try:
                _purge_untrusted_stage(stage, PREPARED_DIR)
            except Exception:
                pass
        raise


def _restore_config_binding(config, restored_public_key):
    return {
        "schema": CONFIG_SCHEMA,
        "repository": config["repository"],
        "environment_file": config["environment_file"],
        "repository_id": config["repository_id"],
        "brain_public_key": restored_public_key,
        "created_at": config["created_at"],
    }


def _debt_config_binding(debt):
    return {
        "schema": CONFIG_SCHEMA,
        "repository": debt["repository"],
        "environment_file": debt["environment_file"] or None,
        "repository_id": debt["repository_id"],
        "brain_public_key": debt["target_public_key"],
        "created_at": debt["configured_at"],
    }


def _rebind_after_identity_adoption(config, restored_public_key):
    config = _validate_config(config, require_binding=False)
    restored_public_key = _validate_text(
        restored_public_key, "restored SIA public identity")
    if not secrets.compare_digest(
            _live_brain_public_key(), restored_public_key):
        raise BlockedError(
            "Live SIA identity does not match the adopted capsule.")
    rebound = _restore_config_binding(config, restored_public_key)
    try:
        current = _validate_config(
            _read_json(CONFIG_PATH, "continuity configuration"),
            require_binding=False)
    except FileNotFoundError:
        current = None
    if current is not None:
        stable_fields = {
            "schema", "repository", "environment_file", "repository_id",
            "created_at",
        }
        if any(current[key] != rebound[key] for key in stable_fields) \
                or current["brain_public_key"] not in {
                    config["brain_public_key"], restored_public_key}:
            raise BlockedError(
                "Continuity configuration changed during identity adoption.")
    _atomic_json(CONFIG_PATH, rebound)
    load_config()
    return rebound


def _perform_apply(args, *, capability):
    binding = _restore_request_binding(args)
    prepared_id = args.get("prepared_id")
    prepared = load_prepared(prepared_id)
    if any(args.get(key) != prepared[key] for key in (
            "snapshot_id", "capsule_id", "manifest_sha256")):
        raise ValueError("restore request no longer binds its preparation")
    confirmation = args.get("confirmation")
    if not isinstance(confirmation, dict) \
            or confirmation.get("snapshot_id") != prepared["snapshot_id"]:
        raise ValueError("restore acceptance no longer matches preparation")
    _sequence, current_head = sialib.ledger_head()
    if confirmation.get("ledger_head") != current_head \
            or prepared["target_ledger_head"] != current_head:
        raise BlockedError("Target ledger head changed after restore acceptance.")
    verified = siacapsule.verify(prepared["capsule_path"])
    if verified["manifest_sha256"] != prepared["manifest_sha256"]:
        raise ValueError("prepared capsule changed after restore acceptance")
    identity_path = args.get("identity_key_file")
    if not prepared["identity_matches"]:
        _protected_output(identity_path, "identity recovery file")
        siacapsule.validate_identity_key(identity_path,
                                         prepared["public_key"])
    config = load_config()
    expected_binding = {
        "prepared_id": prepared_id,
        "snapshot_id": prepared["snapshot_id"],
        "capsule_id": prepared["capsule_id"],
        "manifest_sha256": prepared["manifest_sha256"],
        "repository": config["repository"],
        "environment_file": config["environment_file"] or "",
        "repository_id": config["repository_id"],
        "configured_at": config["created_at"],
        "target_public_key": config["brain_public_key"],
        "restored_public_key": prepared["public_key"],
    }
    if binding != expected_binding:
        raise BlockedError("restore repository binding changed before thaw")
    result = siacapsule.thaw(
        prepared, confirmation, capability=capability,
        identity_key_file=identity_path, rollback_root=ROLLBACK_DIR)
    _rebind_after_identity_adoption(config, prepared["public_key"])
    return result


def _run_request_locked(request, *, restic_path=None, enable_schedules=None,
                        capability=None):
    action = request["action"]
    kind = _ACTION_KIND[action]
    prepared_id = (request["args"].get("prepared_id", "")
                   if action == "apply" else "")
    state = {
        "upload": "capturing", "check": "checking",
        "prepare": "preparing", "apply": "restoring",
    }.get(action, "queued")
    with _exclusive_lock(WORKER_LOCK):
        _publish_status(
            state=state, detail="Continuity worker is running.",
            repository_display="External recovery repository",
            operation=_operation(request["id"], kind, "running",
                                 prepared_id=prepared_id))
        try:
            latest = None
            prepared = None
            if action == "setup":
                _perform_setup(request["args"], restic_path=restic_path,
                               enable_schedules=enable_schedules)
            elif action == "connect":
                latest = _perform_connect(
                    request["args"], restic_path=restic_path,
                    enable_schedules=enable_schedules)
            elif action == "upload":
                latest = _perform_upload(request["args"], request["id"],
                                         restic_path=restic_path)
            elif action == "check":
                latest = _perform_check(restic_path=restic_path)
            elif action == "prepare":
                prepared = _perform_prepare(
                    request["args"], request["id"],
                    restic_path=restic_path)
            else:
                if capability is None:
                    raise BlockedError(
                        "Restore requires the exclusive stable-launcher path.")
                restore_result = _perform_apply(
                    request["args"], capability=capability)
        except BlockedError:
            _publish_status(
                state="blocked",
                detail="Continuity operation was safely blocked; no live "
                       "brain mutation was committed.",
                operation=_operation(request["id"], kind, "blocked",
                                     prepared_id=prepared_id))
            try:
                _retire_request_artifacts(request)
            except Exception:
                pass
            return 3
        except Exception:
            _publish_status(
                state="failed",
                detail="Continuity operation failed without reporting "
                       "repository credentials.",
                operation=_operation(request["id"], kind, "failed",
                                     prepared_id=prepared_id))
            try:
                _retire_request_artifacts(request)
            except Exception:
                pass
            return 1

        if action == "prepare":
            try:
                previous = read_status()
                prior_latest = previous.get("latest")
            except (OSError, ValueError):
                prior_latest = None
            candidate = prepared.pop("_latest_status")
            promoted = (prior_latest if _latest_is_protecting(prior_latest)
                        else candidate if _latest_is_protecting(candidate)
                        else None)
            _publish_status(
                state="prepared", detail="Restore capsule verified off-path.",
                repository_display="External recovery repository",
                latest=promoted,
                prepared=_prepared_status(prepared),
                operation=_operation(request["id"], kind, "verified",
                                     prepared_id=prepared["prepared_id"]))
        elif action == "apply":
            try:
                previous = read_status()
                prior_latest = previous.get("latest")
                prior_prepared = previous.get("prepared")
            except (OSError, ValueError):
                prior_latest = None
                prior_prepared = None
            ready = restore_result.get("ready") is True
            sia_ledger_verified = (
                restore_result.get("sia_ledger_verified") is True)
            if not (ready and sia_ledger_verified):
                _publish_status(
                    state="blocked",
                    detail="Restore completed without the full readiness "
                           "and signed-history acceptance proof.",
                    repository_display="External recovery repository",
                    latest=prior_latest, prepared=prior_prepared,
                    operation=_operation(
                        request["id"], kind, "blocked",
                        prepared_id=prepared_id, ready=ready,
                        sia_ledger_verified=sia_ledger_verified))
                return 3
            prepared_root = os.path.dirname(_prepared_path(prepared_id))
            if os.path.lexists(prepared_root):
                try:
                    _retire_private_tree(prepared_root, PREPARED_DIR)
                except Exception:
                    _publish_status(
                        state="blocked",
                        detail="Restore verified, but prepared-stage "
                               "retirement was safely blocked.",
                        repository_display="External recovery repository",
                        latest=prior_latest, prepared=prior_prepared,
                        operation=_operation(
                            request["id"], kind, "blocked",
                            prepared_id=prepared_id, ready=True,
                            sia_ledger_verified=True))
                    return 3
            _publish_status(
                state="restoring",
                detail="Restore data and SIA ledger verified; awaiting "
                       "brainstem restart attestation.",
                repository_display="External recovery repository",
                latest=prior_latest, prepared=None,
                operation=_operation(
                    request["id"], kind, "running",
                    prepared_id=prepared_id, ready=ready,
                    sia_ledger_verified=sia_ledger_verified))
        else:
            terminal_code = 0
            try:
                previous = read_status()
                prior_latest = previous.get("latest")
                prior_prepared = previous.get("prepared")
            except (OSError, ValueError):
                prior_latest = None
                prior_prepared = None
            pending_upload = (action == "upload"
                              and isinstance(latest, dict)
                              and latest.get("verified") is False)
            if pending_upload:
                latest = (prior_latest
                          if _latest_is_protecting(prior_latest)
                          else None)
            elif action == "setup":
                latest = None
            copy_verified = _latest_is_protecting(latest)
            empty_check = action == "check" and latest is None
            if empty_check:
                final_state = "blocked"
                terminal_phase = "blocked"
                terminal_code = 3
            else:
                final_state = "verified" if copy_verified else "recovery-only"
                terminal_phase = "verified"
            _publish_status(
                state=final_state,
                detail=(
                    "Repository check found no identity-bound SIA capsule; "
                    "no recovery copy is claimed."
                    if empty_check else
                    "Newest upload is stored and awaits weekly verification; "
                    "the prior verified recovery copy remains current."
                    if pending_upload and copy_verified else
                    "Newest upload is stored and awaits weekly verification."
                    if pending_upload else
                    "Verified recovery copy is available."
                    if copy_verified else
                    "Repository connected; no ready verified copy recorded."),
                repository_display="External recovery repository",
                latest=latest, prepared=prior_prepared,
                operation=_operation(
                    request["id"], kind, terminal_phase))
        try:
            # Apply remains until the stable supervisor observes the daemon
            # restart outcome and retires the exact correlated request.
            if action != "apply":
                _retire_request(request)
        except Exception:
            _publish_status(
                state="blocked",
                detail="Continuity completed, but local finalization was "
                       "safely blocked.",
                operation=_operation(request["id"], kind, "blocked",
                                     prepared_id=prepared_id))
            return 1
        return terminal_code if action not in {"prepare", "apply"} else 0


def run_request(request_path, *, restic_path=None, enable_schedules=None):
    """Run a normal generation-pinned request under lifecycle SH."""
    _ensure_layout()
    request = _load_request(request_path)
    return _run_request_locked(
        request, restic_path=restic_path,
        enable_schedules=enable_schedules)


def run_restore_request(request_path, *, lifecycle_fd):
    """Run only restore apply under a validated lifecycle-EX capability."""
    _ensure_layout()
    request = _load_request(request_path)
    if request["action"] != "apply":
        raise ValueError(
            "exclusive restore dispatch accepts only restore apply requests")
    if os.path.lexists(siacapsule.RESTORE_BARRIER):
        raise BlockedError(
            "An interrupted restore barrier requires recovery before apply.")
    prepared_id = request["args"].get("prepared_id", "")
    try:
        with sialib.brainstem_owner() as brainstem_fd, \
                sialib.corpus_owner() as corpus_fd, \
                sialib.gbrain_owner() as gbrain_fd:
            capability = {
                "lifecycle_fd": lifecycle_fd,
                "brainstem_fd": brainstem_fd,
                "corpus_fd": corpus_fd,
                "gbrain_fd": gbrain_fd,
            }
            siacapsule.validate_restore_capability(capability)
            return _run_request_locked(request, capability=capability)
    except BlockedError:
        _publish_status(
            state="blocked",
            detail="Restore was safely blocked before live mutation.",
            operation=_operation(
                request["id"], "restore-apply", "blocked",
                prepared_id=prepared_id))
        return 3
    except Exception:
        _publish_status(
            state="failed",
            detail="Restore worker failed without exposing recovery secrets.",
            operation=_operation(
                request["id"], "restore-apply", "failed",
                prepared_id=prepared_id))
        return 1


def _live_restore_observation(debt=None):
    """Observe health and, for apply debt, its signed adoption transition.

    The SIA ledger verifier authenticates the bounded ledger before the exact
    action/argument tuple is inspected.  No content hash is guessed: the
    occurrence-bound content is intentionally unavailable after the capsule
    journal is retired.
    """
    before_sequence, before_head = sialib.ledger_head()
    if before_sequence <= 0 or not before_head:
        raise ValueError("SIA ledger has no nonempty generation head")
    observed = siacapsule._health_observation()
    ready = observed.get("ready") is True
    ledger_verified = observed.get("sia_ledger_verified") is True
    committed = None
    if ledger_verified and debt is not None \
            and debt.get("kind") == "restore-apply":
        # Observed from bin/sia-ledger's published storage boundary.
        raw = _read_regular(
            os.path.join(sialib.SHARE, "ledger.tsv"), "SIA ledger",
            maximum=MAX_LEDGER_BYTES)
        try:
            text = raw.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise ValueError("SIA ledger is not valid UTF-8") from exc
        if text and not text.endswith("\n"):
            raise ValueError("SIA ledger has a torn final row")
        matches = 0
        for line in (text[:-1].split("\n") if text else []):
            fields = line.split("\t")
            if len(fields) != 9:
                raise ValueError("SIA ledger row shape is malformed")
            if fields[2] == "RESTORE:adopt" \
                    and fields[3] == debt["prepared_id"] \
                    and fields[4] == debt["capsule_id"]:
                matches += 1
        if matches > 1:
            raise ValueError("SIA restore adoption transition is ambiguous")
        committed = matches == 1
    after_sequence, after_head = sialib.ledger_head()
    if (after_sequence, after_head) != (before_sequence, before_head):
        raise BlockedError(
            "SIA ledger generation changed during restore attestation.")
    return {
        "ready": ready,
        "sia_ledger_verified": ledger_verified,
        "committed": committed,
        "ledger_sequence": before_sequence,
        "ledger_head": before_head,
    }


def run_restore_recovery(request_id, *, lifecycle_fd):
    """Resolve a barrier or exact supervisor debt under lifecycle EX."""
    _ensure_layout()
    if not isinstance(request_id, str) \
            or _SAFE_ID.fullmatch(request_id) is None:
        raise ValueError("restore recovery identifier is invalid")
    debt = load_supervisor_debt()
    if debt is not None and debt["request_id"] != request_id:
        raise BlockedError("Restore recovery correlation changed.")
    barrier_present = os.path.lexists(siacapsule.RESTORE_BARRIER)
    if not barrier_present and debt is None \
            and not os.path.lexists(sialib.RESTORE_MASK_PATH):
        raise BlockedError("No interrupted restore requires recovery.")
    apply_debt = debt is not None and debt["kind"] == "restore-apply"
    operation_kind = "restore-apply" if apply_debt else "restore-recover"
    operation_prepared = debt["prepared_id"] if apply_debt else ""
    _publish_status(
        state="restoring", detail="Interrupted restore recovery is running.",
        repository_display="External recovery repository",
        operation=_operation(
            request_id, operation_kind, "running",
            prepared_id=operation_prepared))
    try:
        with sialib.brainstem_owner() as brainstem_fd, \
                sialib.corpus_owner() as corpus_fd, \
                sialib.gbrain_owner() as gbrain_fd:
            capability = {
                "lifecycle_fd": lifecycle_fd,
                "brainstem_fd": brainstem_fd,
                "corpus_fd": corpus_fd,
                "gbrain_fd": gbrain_fd,
            }
            siacapsule.validate_restore_capability(capability)
            with _exclusive_lock(WORKER_LOCK):
                if barrier_present:
                    siacapsule.recover_barrier(capability=capability)
                    # Recovery can either settle the adoption or roll the
                    # live roots back.  Re-observe the signed transition; a
                    # successful health check alone cannot distinguish them.
                    observed = _live_restore_observation(debt)
                else:
                    observed = _live_restore_observation(debt)
                if apply_debt and observed.get("committed") is True:
                    _rebind_after_identity_adoption(
                        _debt_config_binding(debt),
                        debt["restored_public_key"])
    except BlockedError:
        _publish_status(
            state="blocked",
            detail="Interrupted restore recovery was safely blocked.",
            operation=_operation(
                request_id, operation_kind, "blocked",
                prepared_id=operation_prepared))
        return 3
    except Exception:
        _publish_status(
            state="failed",
            detail="Interrupted restore recovery failed; the durable "
                   "barrier remains authoritative.",
            operation=_operation(
                request_id, operation_kind, "failed",
                prepared_id=operation_prepared))
        return 1
    ready = observed.get("ready") is True
    sia_ledger_verified = observed.get("sia_ledger_verified") is True
    try:
        previous = read_status()
        latest = previous.get("latest")
        prepared = previous.get("prepared")
    except (OSError, ValueError):
        latest = None
        prepared = None
    if ready and sia_ledger_verified \
            and (not apply_debt or observed.get("committed") is True):
        _publish_status(
            state="restoring",
            detail="Interrupted restore recovered; awaiting brainstem "
                   "restart attestation.",
            repository_display="External recovery repository",
            latest=latest, prepared=prepared,
            operation=_operation(
                request_id,
                "restore-apply" if apply_debt else "restore-recover",
                "running", prepared_id=(debt["prepared_id"]
                                         if apply_debt else ""),
                ready=True, sia_ledger_verified=True))
        return 0
    if sia_ledger_verified and apply_debt \
            and observed.get("committed") is False:
        _publish_status(
            state="blocked",
            detail="The interrupted restore has no signed adoption "
                   "transition; the coherent prior generation was retained.",
            repository_display="External recovery repository",
            latest=latest, prepared=prepared,
            operation=_operation(
                request_id, "restore-apply", "blocked",
                prepared_id=debt["prepared_id"], ready=ready,
                sia_ledger_verified=True))
        # This is a proven non-commit, not a recovery failure.  The stable
        # supervisor may restart the coherent brain and retire the request.
        return 0
    if sia_ledger_verified and apply_debt \
            and observed.get("committed") is True:
        _publish_status(
            state="blocked",
            detail="The signed restore adoption is committed, but SIA is "
                   "not ready yet; restart will allow normal healing.",
            repository_display="External recovery repository",
            latest=latest, prepared=prepared,
            operation=_operation(
                request_id, "restore-apply", "blocked",
                prepared_id=debt["prepared_id"], ready=ready,
                sia_ledger_verified=True))
        return 0
    if sia_ledger_verified and not apply_debt:
        _publish_status(
            state="blocked",
            detail="Interrupted recovery settled with a valid SIA ledger, "
                   "but readiness still requires normal brainstem healing.",
            repository_display="External recovery repository",
            latest=latest, prepared=prepared,
            operation=_operation(
                request_id, "restore-recover", "blocked", ready=ready,
                sia_ledger_verified=True))
        return 0
    _publish_status(
        state="blocked",
        detail="Interrupted restore recovery completed without the full "
               "readiness and signed-history proof.",
        repository_display="External recovery repository",
        latest=latest, prepared=prepared,
        operation=_operation(
            request_id,
            "restore-apply" if apply_debt else "restore-recover",
            "blocked", prepared_id=(debt["prepared_id"]
                                     if apply_debt else ""), ready=ready,
            sia_ledger_verified=sia_ledger_verified))
    return 3


def mark_brainstem_restart_failed(request_path):
    """Withhold restore success if the resident daemon could not restart."""
    try:
        request = _load_request(request_path)
        debt = load_supervisor_debt()
        if debt is None or debt.get("phase") != "restart-failed" \
                or debt.get("request_id") != request["id"] \
                or debt.get("prepared_id") != \
                   request["args"].get("prepared_id") \
                or debt.get("snapshot_id") != \
                   request["args"].get("snapshot_id") \
                or debt.get("capsule_id") != \
                   request["args"].get("capsule_id") \
                or debt.get("manifest_sha256") != \
                   request["args"].get("manifest_sha256"):
            return False
        operation = read_status().get("operation")
        if not isinstance(operation, dict) \
                or operation.get("request_id") != request["id"] \
                or operation.get("kind") != "restore-apply" \
                or operation.get("prepared_id") != debt["prepared_id"]:
            return False
        prepared_id = request["args"].get("prepared_id", "")
        request_id = request["id"]
    except (OSError, TypeError, ValueError):
        return False
    _publish_status(
        state="blocked",
        detail="Restore completed, but the brainstem restart was refused.",
        operation=_operation(
            request_id, "restore-apply", "blocked",
            prepared_id=prepared_id,
            ready=(operation.get("ready") is True),
            sia_ledger_verified=(
                operation.get("sia_ledger_verified") is True)))
    return True


def _post_restart_observation(debt):
    """Bind a fresh live proof to one stable resident brainstem PID."""
    def resident_pid():
        result = sialib._run_bounded_text_process(
            ["systemctl", "--user", "show", "sia-brainstem.service",
             "--property=ActiveState", "--property=MainPID"], env=None,
            timeout=sialib.JOURNAL_TIMEOUT_SECONDS, cwd=None,
            label="post-restore brainstem attestation",
            output_limit=sialib.MAX_CONFIG_BYTES)
        if result.returncode != 0:
            return None
        fields = {}
        for line in result.stdout.splitlines():
            if "=" not in line:
                return None
            key, value = line.split("=", 1)
            if key in fields:
                return None
            fields[key] = value
        if set(fields) != {"ActiveState", "MainPID"} \
                or fields["ActiveState"] != "active" \
                or not fields["MainPID"].isascii() \
                or not fields["MainPID"].isdigit() \
                or fields["MainPID"] == "0":
            return None
        command_path = os.path.join("/proc", fields["MainPID"], "cmdline")
        descriptor = os.open(
            command_path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(descriptor)
            command = os.read(descriptor, sialib.MAX_CONFIG_BYTES + 1)
        finally:
            os.close(descriptor)
        expected = os.path.abspath(os.path.join(sialib.BIN,
                                                "sia-brainstem.py"))
        arguments = [part.decode("utf-8", "strict")
                     for part in command.rstrip(b"\0").split(b"\0")]
        try:
            executable = os.path.realpath(os.path.join(
                "/proc", fields["MainPID"], "exe"))
        except OSError:
            return None
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
                or len(command) > sialib.MAX_CONFIG_BYTES \
                or len(arguments) != 2 \
                or os.path.realpath(arguments[0]) != \
                   os.path.realpath(sys.executable) \
                or executable != os.path.realpath(sys.executable) \
                or os.path.abspath(arguments[1]) != expected:
            return None
        return fields["MainPID"]

    before_pid = resident_pid()
    if before_pid is None or before_pid != debt.get("restart_pid"):
        return None
    observed = _live_restore_observation(debt)
    after_pid = resident_pid()
    if after_pid != before_pid:
        return None
    return observed


def _finalize_restore_request_under_corpus(request_path):
    debt = load_supervisor_debt()
    if debt is None or debt.get("kind") != "restore-apply" \
            or debt.get("phase") != "restart-attested" \
            or os.path.abspath(request_path) != \
               os.path.abspath(debt["request_path"]):
        raise ValueError("restore finalizer lacks supervisor attestation")
    request = None
    try:
        request = _load_request(request_path)
    except FileNotFoundError:
        pass
    if request is not None \
            and (request["action"] != "apply"
                 or debt.get("request_id") != request["id"]
                 or debt.get("prepared_id") !=
                    request["args"].get("prepared_id")
                 or debt.get("snapshot_id") !=
                    request["args"].get("snapshot_id")
                 or debt.get("capsule_id") !=
                    request["args"].get("capsule_id")
                 or debt.get("manifest_sha256") !=
                    request["args"].get("manifest_sha256")):
        raise ValueError("restore request binding changed")
    status = read_status()
    operation = status.get("operation")
    if not isinstance(operation, dict) \
            or operation.get("request_id") != debt["request_id"] \
            or operation.get("kind") != "restore-apply" \
            or operation.get("prepared_id") != debt["prepared_id"] \
            or operation.get("phase") not in {
                "running", "verified", "failed", "blocked"}:
        raise ValueError("restore finalizer lacks matching terminal status")
    if operation["phase"] == "failed":
        raise ValueError("failed restore cannot be restart-attested")
    observed = _post_restart_observation(debt)
    if observed is None \
            or observed.get("sia_ledger_verified") is not True \
            or observed.get("committed") not in {True, False}:
        raise ValueError("restore finalizer lacks fresh signed proof")
    if observed.get("committed") is True \
            and observed.get("ready") is True:
        latest = status.get("latest")
        protecting = _latest_is_protecting(latest)
        terminal = {
            "state": "verified" if protecting else "recovery-only",
            "detail": (
                "Restore verified and an identity-bound repository copy is "
                "ready."
                if protecting else
                "Restore verified; repository protection remains unclaimed "
                "until an identity-bound copy passes verification."),
            "operation": _operation(
                debt["request_id"], "restore-apply", "verified",
                prepared_id=debt["prepared_id"], ready=True,
                sia_ledger_verified=True),
        }
    else:
        terminal = {
            "state": "blocked",
            "detail": (
                "Restore adoption is signed, but readiness still requires "
                "normal brainstem healing."
                if observed.get("committed") is True else
                "Restore was not committed; the coherent prior generation "
                "was restarted."),
            "operation": _operation(
                debt["request_id"], "restore-apply", "blocked",
                prepared_id=debt["prepared_id"],
                ready=(observed.get("ready") is True),
                sia_ledger_verified=True),
        }
    if request is not None:
        _retire_request(request)
    _retire_supervisor_debt(debt)
    _publish_status(**terminal)
    return True


def finalize_restore_request(request_path):
    """Retire exact restore authority, then publish under one corpus lease."""
    with sialib.corpus_owner():
        return _finalize_restore_request_under_corpus(request_path)


def _finalize_restore_recovery_under_corpus():
    debt = load_supervisor_debt()
    if debt is None or debt.get("kind") != "restore-recover" \
            or debt.get("phase") != "restart-attested":
        return False
    status = read_status()
    operation = status.get("operation")
    if not isinstance(operation, dict) \
            or operation.get("kind") != "restore-recover" \
            or operation.get("request_id") != debt["request_id"] \
            or operation.get("prepared_id") != "":
        return False
    if operation.get("phase") not in {"running", "verified", "blocked"}:
        return False
    observed = _post_restart_observation(debt)
    if observed is None or observed.get("sia_ledger_verified") is not True:
        return False
    if observed.get("ready") is True:
        latest = status.get("latest")
        protecting = _latest_is_protecting(latest)
        terminal = {
            "state": "verified" if protecting else "recovery-only",
            "detail": (
                "Interrupted restore recovered and an identity-bound "
                "repository copy is ready."
                if protecting else
                "Interrupted restore recovered; repository protection "
                "remains unclaimed until a copy passes verification."),
            "operation": _operation(
                operation["request_id"], "restore-recover", "verified",
                ready=True, sia_ledger_verified=True),
        }
    else:
        terminal = {
            "state": "blocked",
            "detail": "Recovery is signed but readiness still requires "
                      "normal brainstem healing.",
            "operation": _operation(
                operation["request_id"], "restore-recover", "blocked",
                ready=False, sia_ledger_verified=True),
        }
    _retire_supervisor_debt(debt)
    _publish_status(**terminal)
    return True


def finalize_restore_recovery():
    with sialib.corpus_owner():
        return _finalize_restore_recovery_under_corpus()


def mark_recovery_restart_failed():
    """Downgrade the exact current recovery after supervisor restart failure."""
    status = read_status()
    operation = status.get("operation")
    debt = load_supervisor_debt()
    if debt is None or debt.get("kind") != "restore-recover" \
            or debt.get("phase") != "restart-failed" \
            or not isinstance(operation, dict) \
            or operation.get("kind") != "restore-recover" \
            or operation.get("request_id") != debt["request_id"] \
            or operation.get("prepared_id") != "" \
            or operation.get("phase") not in {"running", "verified"}:
        return False
    _publish_status(
        state="blocked",
        detail="Recovery completed, but the brainstem restart was refused.",
        operation=_operation(
            operation["request_id"], "restore-recover", "blocked",
            ready=(operation.get("ready") is True),
            sia_ledger_verified=(
                operation.get("sia_ledger_verified") is True)))
    return True


def reconcile_supervisor_spools():
    """Replay exact terminal finalization after gate retirement."""
    if os.path.lexists(siacapsule.RESTORE_BARRIER) \
            or os.path.lexists(sialib.RESTORE_MASK_PATH):
        raise BlockedError("Restore mutation or runtime-mask debt remains.")
    with _exclusive_lock(REQUEST_LOCK):
        debt = load_supervisor_debt()
        if debt is None:
            return True
        if debt.get("phase") != "restart-attested":
            raise BlockedError("Restore supervisor restart is not attested.")
        if debt["kind"] == "restore-apply":
            finalize_restore_request(debt["request_path"])
        elif not finalize_restore_recovery():
            raise BlockedError("Restore recovery promotion was refused.")
        _reconcile_inactive_spools()
    return True


def _parse_named_options(argv, required, optional=frozenset()):
    values = {}
    index = 0
    allowed = set(required) | set(optional)
    while index < len(argv):
        option = argv[index]
        if option not in allowed or option in values or index + 1 >= len(argv):
            raise ValueError("continuity command options are invalid")
        values[option] = argv[index + 1]
        index += 2
    if any(option not in values for option in required):
        raise ValueError("continuity command is missing a required option")
    return values


def _print_request(request, label):
    print(f"{label} accepted · request {request['id']}")


def cli_backup(argv):
    try:
        if argv and argv[0] == "setup":
            values = _parse_named_options(
                argv[1:], {"--repository", "--recovery-key-out",
                           "--identity-key-out"}, {"--environment-file"})
            request = queue_setup(
                values["--repository"], values["--recovery-key-out"],
                values["--identity-key-out"], values.get("--environment-file"))
            _print_request(request, "setup")
            return 0
        if argv and argv[0] == "connect":
            values = _parse_named_options(
                argv[1:], {"--repository", "--recovery-key-file"},
                {"--environment-file"})
            request = queue_connect(
                values["--repository"], values["--recovery-key-file"],
                values.get("--environment-file"))
            _print_request(request, "connection")
            return 0
        if argv in (["now"], ["now", "--scheduled"]):
            request = queue_backup(scheduled="--scheduled" in argv)
            if request is None:
                print("scheduled backup coalesced with active upload")
            else:
                _print_request(request, "backup")
            return 0
        if argv in (["check"], ["check", "--scheduled"]):
            request = queue_check(scheduled="--scheduled" in argv)
            if request is None:
                print("scheduled check coalesced with active check")
            else:
                _print_request(request, "check")
            return 0
        if argv == ["status"]:
            print(json.dumps(read_status(), ensure_ascii=True, sort_keys=True,
                             separators=(",", ":")))
            return 0
        if argv == ["list"]:
            print(json.dumps(list_snapshots(), ensure_ascii=True,
                             sort_keys=True, separators=(",", ":")))
            return 0
        if argv == ["resume-schedule"]:
            resume_schedule()
            print("continuity schedules enabled after repository probe")
            return 0
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"backup refused: {exc}", file=sys.stderr)
        return 1
    print("usage: sia backup setup --repository REPOSITORY "
          "--recovery-key-out ABSOLUTE_PATH --identity-key-out ABSOLUTE_PATH "
          "[--environment-file ABSOLUTE_PATH]\n"
          "       sia backup connect --repository REPOSITORY "
          "--recovery-key-file ABSOLUTE_PATH "
          "[--environment-file ABSOLUTE_PATH]\n"
          "       sia backup now [--scheduled] | status | list | "
          "check [--scheduled] | resume-schedule")
    return 2


def cli_restore(argv, stream):
    try:
        if len(argv) == 2 and argv[0] == "prepare":
            request = queue_prepare(argv[1])
            _print_request(request, "restore preparation")
            return 0
        if argv == ["status"]:
            print(json.dumps(read_status(), ensure_ascii=True, sort_keys=True,
                             separators=(",", ":")))
            return 0
        if len(argv) in {3, 5} and argv[0] == "apply" \
                and argv[2] == "--confirm-stdin":
            identity_file = None
            if len(argv) == 5:
                if argv[3] != "--identity-key-file":
                    raise ValueError("restore apply option is invalid")
                identity_file = _validate_text(
                    argv[4], "identity recovery file", absolute=True)
            confirmation = _read_confirmation(stream)
            request = queue_apply(argv[1], confirmation, identity_file)
            acceptance = {
                "schema_version": ACCEPTANCE_SCHEMA_VERSION,
                "accepted": True,
                "request_id": request["id"],
                "operation": "restore-apply",
                "prepared_id": argv[1],
            }
            print(json.dumps(acceptance, ensure_ascii=True, sort_keys=True,
                             separators=(",", ":")))
            return 0
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"restore refused: {exc}", file=sys.stderr)
        return 1
    print("usage: sia restore prepare SNAPSHOT_ID | status | recover\n"
          "       sia restore apply PREPARED_ID --confirm-stdin "
          "[--identity-key-file ABSOLUTE_PATH]")
    return 2
