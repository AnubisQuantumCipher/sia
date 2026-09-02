"""Filesystem spool for multi-writer agent requests.

Agent-origin note writes keep one corpus owner: ``sia-brainstem``.  MCP
servers and ``sia note`` processes only create immutable request files here;
operator-controlled take, intent, and synthesis transitions remain separate
CLI workflows. A unique file per request avoids shared read/modify/write
state, while atomic rename and directory fsync make a successfully returned
enqueue durable. The daemon acknowledges a request only after materializing
it in the corpus. No queue client opens PGLite.
"""

import datetime
import contextlib
import ctypes
import errno
import fcntl
import hashlib
import json
import os
import re
import stat
import uuid


SCHEMA = "sia-agent-request-v1"
QUEUE_DIRNAME = "agent-inbox"
MAX_REQUEST_BYTES = 16_384
MAX_PENDING_REQUESTS = 1024
# parsed=1024*2, exact=2048; parsed=2048+1, exact=2049. Exact rational
MAX_PENDING_BYTES = 16_777_216
MAX_QUEUE_SCAN_ENTRIES = 2_049
_ACK_NAME_RE = re.compile(r"^\.ack-(.+\.json)-[0-9a-f]{32}$")
_LEGACY_ENQUEUE_RE = re.compile(r"^\.enqueue-[A-Za-z0-9_-]{1,200}$")
STAGING_DIR_SUFFIX = ".sia-stage"
STAGING_LOCK_NAME = "publish.lock"
STAGING_PAYLOAD_NAME = "payload"


def _utc_stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _queue_dir(state_dir):
    return os.path.join(state_dir, QUEUE_DIRNAME)


def _ensure_queue_dir(state_dir):
    queue_dir = _queue_dir(state_dir)
    try:
        os.mkdir(queue_dir, 0o700)
    except FileExistsError:
        pass
    linked = os.lstat(queue_dir)
    if not stat.S_ISDIR(linked.st_mode):
        raise ValueError("agent queue is not a real directory")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) \
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(queue_dir, flags)
    try:
        meta = os.fstat(fd)
        if not stat.S_ISDIR(meta.st_mode) \
                or meta.st_uid != os.geteuid():
            raise ValueError("agent queue is not an owned real directory")
        os.fchmod(fd, 0o700)
        os.fsync(fd)
    finally:
        os.close(fd)
    # Repeat the parent sync on every preparation. A retry after an earlier
    # failure must close the first-creation durability window rather than
    # trusting the directory's presence.
    _fsync_dir(state_dir)
    return queue_dir


@contextlib.contextmanager
def _queue_lock(queue_dir):
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) \
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_descriptor = os.open(queue_dir, directory_flags)
    directory_info = os.fstat(directory_descriptor)
    if not stat.S_ISDIR(directory_info.st_mode) \
            or directory_info.st_uid != os.geteuid() \
            or stat.S_IMODE(directory_info.st_mode) & 0o022:
        os.close(directory_descriptor)
        raise ValueError(
            "agent queue is not an owner-private real directory")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(".queue.lock", flags, 0o600,
                     dir_fd=directory_descriptor)
    except Exception:
        os.close(directory_descriptor)
        raise
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) \
                or info.st_uid != os.geteuid() or info.st_nlink != 1:
            raise ValueError("agent queue lock is not an owned regular file")
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            held = os.fstat(fd)
            current = os.stat(
                ".queue.lock", dir_fd=directory_descriptor,
                follow_symlinks=False)
            if not stat.S_ISREG(current.st_mode) \
                    or current.st_uid != os.geteuid() \
                    or current.st_nlink != 1 \
                    or (held.st_dev, held.st_ino) != (
                        current.st_dev, current.st_ino):
                raise ValueError(
                    "agent queue lock changed while acquiring its lease")
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
        os.close(directory_descriptor)


def _scan_queue(queue_dir, *, cleanup_legacy=False):
    """Return one bounded queue snapshot without materializing overflow."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) \
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(queue_dir, flags)
    names = []
    total = 0
    inspected = 0
    cleaned = False
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() \
                or stat.S_IMODE(info.st_mode) & 0o022:
            raise ValueError(
                "agent queue is not an owner-private real directory")
        with os.scandir(descriptor) as entries:
            for entry in entries:
                inspected += 1
                if inspected >= MAX_QUEUE_SCAN_ENTRIES:
                    raise ValueError(
                        "agent queue directory exceeds its scan bound")
                name = entry.name
                if cleanup_legacy and _LEGACY_ENQUEUE_RE.fullmatch(name):
                    entry_info = entry.stat(follow_symlinks=False)
                    if not stat.S_ISREG(entry_info.st_mode) \
                            or entry_info.st_uid != os.geteuid() \
                            or entry_info.st_nlink != 1:
                        raise ValueError(
                            "agent queue legacy staging entry is unsafe")
                    os.unlink(name, dir_fd=descriptor)
                    cleaned = True
                    continue
                if _canonical_spool_name(name) is None:
                    continue
                if len(names) >= MAX_PENDING_REQUESTS:
                    raise ValueError("agent queue exceeds its request bound")
                entry_info = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(entry_info.st_mode) \
                        or entry_info.st_uid != os.geteuid() \
                        or entry_info.st_nlink != 1 \
                        or entry_info.st_mode & 0o077 \
                        or entry_info.st_size > MAX_REQUEST_BYTES:
                    raise ValueError(
                        "agent queue has an unsafe authoritative request")
                if entry_info.st_size > MAX_PENDING_BYTES - total:
                    raise ValueError("agent queue exceeds its byte bound")
                total += entry_info.st_size
                names.append(name)
    finally:
        if cleaned:
            os.fsync(descriptor)
        os.close(descriptor)
    names.sort()
    return names, total


def _queue_usage(queue_dir):
    names, total = _scan_queue(queue_dir, cleanup_legacy=True)
    return len(names), total


def _validate_record(record, filename=None):
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise ValueError("unsupported schema")
    request_id = record.get("request_id")
    if (not isinstance(request_id, str)
            or not re.fullmatch(r"[0-9a-f]{32}", request_id)):
        raise ValueError("invalid request_id")
    queued_at = record.get("queued_at")
    if (not isinstance(queued_at, str)
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                                queued_at)):
        raise ValueError("invalid queued_at")
    try:
        datetime.datetime.strptime(queued_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError("invalid queued_at") from exc
    if record.get("operation") != "note":
        raise ValueError("unsupported operation")
    payload = record.get("payload")
    if not isinstance(payload, dict) or set(payload) != {"author", "text"}:
        raise ValueError("invalid note payload keys")
    author, text = payload.get("author"), payload.get("text")
    if (not isinstance(author, str) or not author.strip()
            or len(author) > 40 or not isinstance(text, str)
            or not text.strip() or len(text) > 2000):
        raise ValueError("invalid note payload")
    if filename is not None:
        canonical = (queued_at.replace(":", "").replace("-", "") + "-"
                     + request_id + ".json")
        if filename != canonical:
            raise ValueError("filename does not match request identity")
    return record


def _fsync_dir(path):
    """Make a directory edit durable or propagate the indeterminate result."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def staging_dir_for(path, authority_roots=()):
    """Return one fixed staging directory outside a known authority root.

    Production callers pass the roots whose children are enumerated as
    authority.  The staging directory is their sibling, so a killed writer
    cannot add even hidden entries to an authoritative scan.  Standalone
    callers fall back to one fixed child of the destination directory; this
    still bounds abandoned staging state to a single directory entry.
    """
    target = os.path.abspath(path)
    directory = os.path.dirname(target) or os.curdir
    matches = []
    for value in authority_roots:
        if not isinstance(value, str) or not value:
            continue
        root = os.path.abspath(value)
        try:
            if os.path.commonpath((target, root)) == root:
                matches.append(root)
        except ValueError:
            continue
    if not matches:
        return os.path.join(directory, STAGING_DIR_SUFFIX)
    # A nested root can itself sit inside a broader enumerated authority.  The
    # staging directory must be outside *all* matching roots, so anchor it at
    # the outermost matching ancestor rather than the nearest one.
    root = min(matches, key=len)
    leaf = os.path.basename(root.rstrip(os.sep)) or "authority"
    return os.path.join(
        os.path.dirname(root.rstrip(os.sep)), f".{leaf}{STAGING_DIR_SUFFIX}")


def _open_owned_directory(path, label):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) \
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    info = os.fstat(descriptor)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() \
            or stat.S_IMODE(info.st_mode) & 0o022:
        os.close(descriptor)
        raise ValueError(f"{label} is not an owner-private real directory")
    return descriptor


def _ensure_staging_directory(path):
    """Create and durably bind one owner-private fixed staging directory."""
    parent = os.path.dirname(path) or os.curdir
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        pass
    descriptor = _open_owned_directory(path, "publication staging directory")
    try:
        os.fchmod(descriptor, 0o700)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    # Repeat the parent sync on retry to close a crash after mkdir but before
    # the directory link itself became durable.
    _fsync_dir(parent)


@contextlib.contextmanager
def _staging_lock(staging_descriptor):
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(
        STAGING_LOCK_NAME, flags, 0o600, dir_fd=staging_descriptor)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
                or info.st_nlink != 1:
            raise ValueError("publication staging lock is not an owned file")
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            held = os.fstat(descriptor)
            current = os.stat(
                STAGING_LOCK_NAME, dir_fd=staging_descriptor,
                follow_symlinks=False)
            if not stat.S_ISREG(current.st_mode) \
                    or current.st_uid != os.geteuid() \
                    or current.st_nlink != 1 \
                    or (held.st_dev, held.st_ino) != (
                        current.st_dev, current.st_ino):
                raise ValueError(
                    "publication staging lock changed while acquiring its lease")
            # The lock is itself a fixed directory entry.  Persisting it here
            # makes later payload serialization independent of its creation
            # window.
            os.fsync(staging_descriptor)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _publish_boundary(_name):
    """Fault-injection seam for publication crash-boundary tests."""


def _rename_noreplace(source_descriptor, source_name,
                      destination_descriptor, destination_name):
    """Linux atomic no-clobber rename using already-bound directories."""
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        operation = libc.renameat2
    except AttributeError as exc:
        raise RuntimeError(
            "atomic no-clobber publication is unavailable") from exc
    operation.argtypes = (
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
        ctypes.c_uint)
    operation.restype = ctypes.c_int
    if operation(
            source_descriptor, os.fsencode(source_name),
            destination_descriptor, os.fsencode(destination_name), 1) == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise FileExistsError(destination_name)
    raise OSError(error, os.strerror(error), destination_name)


def _owned_regular_at(directory_descriptor, name, label):
    info = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
            or info.st_nlink != 1:
        raise ValueError(f"{label} is not an owned regular file")
    return info


def _read_exact_at(directory_descriptor, name, expected_size, label):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(name, flags, dir_fd=directory_descriptor)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_nlink != 1 \
                or before.st_size != expected_size:
            raise ValueError(f"{label} is not the expected regular file")
        chunks = []
        remaining = expected_size
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                raise ValueError(f"{label} changed while read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError(f"{label} changed while read")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        current = os.stat(
            name, dir_fd=directory_descriptor, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise ValueError(f"{label} changed while read") from exc
    identity = lambda value: (
        value.st_dev, value.st_ino, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns)
    if identity(before) != identity(after) \
            or identity(after) != identity(current) \
            or not stat.S_ISREG(current.st_mode) \
            or current.st_uid != os.geteuid() or current.st_nlink != 1:
        raise ValueError(f"{label} changed while read")
    return b"".join(chunks)


def fixed_atomic_publish(path, data, *, mode=0o600, exclusive=False,
                         staging_dir=None, authority_roots=()):
    """Publish bytes through one crash-reusable fixed payload slot.

    ``exclusive`` never replaces a destination.  An already-present exact
    byte sequence is accepted as an idempotent replay; any other destination
    is refused.  A failed or killed attempt can leave only ``payload`` in the
    owner-private staging directory, and the next holder cleans that exact
    owned regular slot before proceeding.
    """
    if not isinstance(data, bytes):
        raise TypeError("fixed publication payload must be bytes")
    target = os.path.abspath(path)
    directory = os.path.dirname(target) or os.curdir
    name = os.path.basename(target)
    if name in ("", ".", ".."):
        raise ValueError("fixed publication target name is invalid")
    staging_dir = staging_dir or staging_dir_for(
        target, authority_roots=authority_roots)
    _ensure_staging_directory(staging_dir)
    destination_descriptor = _open_owned_directory(
        directory, "publication destination directory")
    staging_descriptor = _open_owned_directory(
        staging_dir, "publication staging directory")
    try:
        if os.fstat(destination_descriptor).st_dev \
                != os.fstat(staging_descriptor).st_dev:
            raise ValueError(
                "publication staging and destination are on different filesystems")
        with _staging_lock(staging_descriptor):
            try:
                _owned_regular_at(
                    staging_descriptor, STAGING_PAYLOAD_NAME,
                    "publication staging payload")
            except FileNotFoundError:
                pass
            else:
                os.unlink(STAGING_PAYLOAD_NAME, dir_fd=staging_descriptor)
                os.fsync(staging_descriptor)

            try:
                current = _owned_regular_at(
                    destination_descriptor, name, "publication target")
            except FileNotFoundError:
                current = None
            if current is not None and exclusive:
                if stat.S_IMODE(current.st_mode) == mode \
                        and current.st_size == len(data) and _read_exact_at(
                        destination_descriptor, name, len(data),
                        "publication target") == data:
                    # The first publisher may have died after link(2) but
                    # before persisting the destination directory.  A replay
                    # must close that durability window before reporting the
                    # exact destination as already published.
                    os.fsync(destination_descriptor)
                    _publish_boundary("target-directory-fsynced")
                    return "existing"
                raise FileExistsError(path)

            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL \
                | getattr(os, "O_CLOEXEC", 0) \
                | getattr(os, "O_NOFOLLOW", 0)
            payload_descriptor = os.open(
                STAGING_PAYLOAD_NAME, flags, mode,
                dir_fd=staging_descriptor)
            try:
                os.fchmod(payload_descriptor, mode)
                view = memoryview(data)
                while view:
                    written = os.write(payload_descriptor, view)
                    if written <= 0:
                        raise OSError("publication payload write made no progress")
                    view = view[written:]
                os.fsync(payload_descriptor)
            finally:
                os.close(payload_descriptor)
            _publish_boundary("payload-fsynced")
            os.fsync(staging_descriptor)
            _publish_boundary("payload-linked")

            if exclusive:
                _rename_noreplace(
                    staging_descriptor, STAGING_PAYLOAD_NAME,
                    destination_descriptor, name)
            else:
                os.replace(
                    STAGING_PAYLOAD_NAME, name,
                    src_dir_fd=staging_descriptor,
                    dst_dir_fd=destination_descriptor)
            _publish_boundary("target-published")
            os.fsync(destination_descriptor)
            _publish_boundary("target-directory-fsynced")

            os.fsync(staging_descriptor)
            _publish_boundary("staging-clean-fsynced")
            return "published"
    finally:
        os.close(staging_descriptor)
        os.close(destination_descriptor)


def _identity(info, request_id, digest):
    return {"dev": info.st_dev, "ino": info.st_ino,
            "size": info.st_size, "mtime_ns": info.st_mtime_ns,
            "ctime_ns": info.st_ctime_ns, "request_id": request_id,
            "sha256": digest}


def _same_identity(info, expected, digest):
    return (info.st_dev == expected.get("dev")
            and info.st_ino == expected.get("ino")
            and info.st_size == expected.get("size")
            and info.st_mtime_ns == expected.get("mtime_ns")
            and digest == expected.get("sha256"))


def _read_open_request(path, name):
    linked = os.lstat(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as f:
        opened = os.fstat(f.fileno())
        if (not stat.S_ISREG(opened.st_mode)
                or opened.st_size > MAX_REQUEST_BYTES
                or opened.st_mode & 0o077
                or opened.st_uid != os.geteuid()
                or opened.st_nlink != 1
                or (linked.st_dev, linked.st_ino) != (
                    opened.st_dev, opened.st_ino)):
            raise ValueError("request is not a bounded regular file")
        raw_bytes = f.read(MAX_REQUEST_BYTES + 1)
        finished = os.fstat(f.fileno())
    try:
        current = os.lstat(path)
    except FileNotFoundError as exc:
        raise ValueError("request changed while it was read") from exc
    if (opened.st_dev, opened.st_ino, opened.st_size,
            opened.st_mtime_ns, opened.st_ctime_ns) != \
            (finished.st_dev, finished.st_ino, finished.st_size,
             finished.st_mtime_ns, finished.st_ctime_ns) \
            or (finished.st_dev, finished.st_ino, finished.st_size,
                finished.st_mtime_ns, finished.st_ctime_ns) != \
            (current.st_dev, current.st_ino, current.st_size,
             current.st_mtime_ns, current.st_ctime_ns):
        raise ValueError("request changed while it was read")
    if len(raw_bytes) > MAX_REQUEST_BYTES:
        raise ValueError("request exceeds byte limit")
    try:
        raw = raw_bytes.decode("utf-8")
        record = json.loads(raw)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("request is malformed JSON") from exc
    _validate_record(record, name)
    digest = hashlib.sha256(raw_bytes).hexdigest()
    return record, _identity(finished, record["request_id"], digest)


def _canonical_spool_name(name):
    if name.endswith(".json") and not name.startswith("."):
        return name
    match = _ACK_NAME_RE.fullmatch(name)
    return match.group(1) if match else None


def enqueue(state_dir, operation, payload):
    """Durably enqueue one immutable request and return its public receipt."""
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    if operation not in {"note"}:
        raise ValueError(f"unsupported agent request: {operation}")

    queue_dir = _ensure_queue_dir(state_dir)
    request_id = uuid.uuid4().hex
    queued_at = _utc_stamp()
    record = {
        "schema": SCHEMA,
        "request_id": request_id,
        "queued_at": queued_at,
        "operation": operation,
        "payload": payload,
    }
    _validate_record(record)
    encoded = (json.dumps(record, ensure_ascii=False, sort_keys=True)
               + "\n").encode("utf-8")
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("agent request exceeds byte limit")
    # The timestamp makes the spool human-auditable; the UUID supplies the
    # collision-resistant identity and becomes the idempotence key.
    name = queued_at.replace(":", "").replace("-", "") + "-" + request_id
    final_path = os.path.join(queue_dir, name + ".json")
    with _queue_lock(queue_dir):
        pending_count, pending_bytes = _queue_usage(queue_dir)
        if pending_count >= MAX_PENDING_REQUESTS \
                or pending_bytes + len(encoded) > MAX_PENDING_BYTES:
            raise ValueError(
                "agent queue is at capacity; wait for the brainstem to drain")
        fixed_atomic_publish(
            final_path, encoded, mode=0o600, exclusive=True,
            staging_dir=os.path.join(state_dir, STAGING_DIR_SUFFIX))
    return {"request_id": request_id, "queued_at": queued_at,
            "operation": operation}


def enqueue_note(state_dir, author, text):
    return enqueue(state_dir, "note", {"author": str(author),
                                        "text": str(text)})


def pending(state_dir):
    """Return ``(path, record, identity)`` requests plus visible errors."""
    queue_dir = _queue_dir(state_dir)
    try:
        meta = os.lstat(queue_dir)
        if not stat.S_ISDIR(meta.st_mode):
            raise ValueError("agent queue is not a real directory")
        with _queue_lock(queue_dir):
            names, pending_bytes = _scan_queue(
                queue_dir, cleanup_legacy=True)
    except FileNotFoundError:
        return [], []
    except (OSError, ValueError) as exc:
        return [], [{"file": QUEUE_DIRNAME, "error": str(exc)}]

    requests, errors = [], []
    try:
        pending_count = len(names)
        if pending_count >= MAX_PENDING_REQUESTS \
                or pending_bytes >= MAX_PENDING_BYTES:
            errors.append({
                "file": QUEUE_DIRNAME,
                "error": "agent queue reached its bounded capacity"})
    except OSError as exc:
        errors.append({"file": QUEUE_DIRNAME, "error": str(exc)})
    for name in names:
        path = os.path.join(queue_dir, name)
        canonical_name = _canonical_spool_name(name)
        try:
            meta = os.lstat(path)
            if not stat.S_ISREG(meta.st_mode) or meta.st_size > MAX_REQUEST_BYTES:
                raise ValueError("request is not a bounded regular file")
            record, identity = _read_open_request(path, canonical_name)
            requests.append((path, record, identity))
        except Exception as exc:
            errors.append({"file": name, "error": str(exc)})
    return requests, errors


def acknowledge(path, expected):
    """Identity-check, remove, and durably acknowledge one request.

    Rename first, then validate the exact inode and request identity that was
    materialized. A pathname replacement is restored/preserved and refused;
    it is never mistaken for the processed request and unlinked.
    """
    if not isinstance(expected, dict) or not expected.get("request_id"):
        raise ValueError("acknowledgment requires the observed request identity")
    queue_dir = os.path.dirname(path)
    name = os.path.basename(path)
    canonical_name = _canonical_spool_name(name)
    if canonical_name is None:
        raise ValueError("acknowledgment path is not a queue request")
    already_claimed = name.startswith(".ack-")
    claim = path if already_claimed else os.path.join(
        queue_dir, ".ack-" + canonical_name + "-" + uuid.uuid4().hex)
    if not already_claimed:
        os.replace(path, claim)
        _fsync_dir(queue_dir)
    try:
        try:
            record, observed = _read_open_request(claim, canonical_name)
        except Exception as exc:
            raise ValueError(
                "request identity changed before acknowledgment") from exc
        info = os.lstat(claim)
        if not _same_identity(info, expected, observed.get("sha256")) \
                or observed["request_id"] != expected["request_id"] \
                or record["request_id"] != expected["request_id"]:
            raise ValueError("request identity changed before acknowledgment")
        os.unlink(claim)
        _fsync_dir(queue_dir)
    except Exception:
        if not already_claimed and os.path.lexists(claim) \
                and not os.path.lexists(path):
            os.replace(claim, path)
            _fsync_dir(queue_dir)
        raise
