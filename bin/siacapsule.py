"""Storage-independent freeze/verify/thaw boundary for SIA continuity.

This module deliberately knows nothing about restic, repository credentials,
systemd, or schedules.  A transport may persist a capsule only after
``freeze`` returns, and may expose it to ``thaw`` only after ``verify`` has
published an off-path prepared tree.
"""

import contextlib
import ctypes
import datetime
import errno
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import time
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)

import sialib


CAPSULE_SCHEMA = "sia-portable-capsule-v1"
ROOTS_SCHEMA = "sia-portable-roots-v1"
IDENTITY_SCHEMA = "sia-offline-identity-v1"
VERIFIED_SCHEMA = "sia-verified-capsule-v1"
PREPARED_SCHEMA = "sia-prepared-capsule-v1"
ADOPTION_SCHEMA = "sia-restore-adoption-v1"
JOURNAL_SCHEMA = "sia-thaw-journal-v1"
MANIFEST_NAME = "manifest.json"
PAYLOAD_NAME = "payload"
MAX_DOCUMENT_BYTES = sialib.MAX_STATE_JSON_BYTES

CONFIG_ROOT = os.path.join(sialib.HOME, ".config", "sia")
CONTINUITY_ROOT = os.path.join(
    sialib.HOME, ".local", "state", "sia-continuity")
RESTORE_BARRIER = os.path.join(CONTINUITY_ROOT, "restore-in-progress.json")
MANAGED_ROOT = os.path.join(sialib.STATE, "managed-install")
CORPUS_RECEIPT = os.path.join(MANAGED_ROOT, "corpus")
SCHEMA_PACK_RECEIPT = os.path.join(MANAGED_ROOT, "schema-pack")
LEDGER_KEY = os.path.join(sialib.SHARE, "key.hex")
LEDGER_PUBLIC = os.path.join(sialib.SHARE, "pub.hex")

_GBRAIN_PROJECTION_NAME = "brain.pglite"
_GBRAIN_SCHEMA_PACK_NAME = "sia-pack"
_GBRAIN_PROJECTION_SIDECARS = (
    "brain.pglite.wal-repair-attempt.json",
    "brain.pglite.lock-reap.json",
)
# Pinned gbrain's native PGLite lock implementation uses this exact claim
# lifetime.  SIA uses it only to decide whether an orphaned *native* reap
# claim may be retired; live and unknown claim holders remain refusals.
_GBRAIN_REAP_CLAIM_TTL_MS = 30000
_GBRAIN_REAP_CLAIM_TTL_NS = 30000000000
_GBRAIN_REAP_TEMP = re.compile(r"lock[.]tmp-[0-9]+")

# These strings are part of the signed format.  Additions are compatible;
# silently removing an omission is not.
OMISSIONS = (
    ".gbrain",
    "bin",
    "toolchain",
    "GBRAIN_PIN",
    "key.hex",
    "managed-install",
    "managed-mcp",
    "mcp-consumer-guards",
    "continuity configuration and credentials",
    "continuity requests, stages, prepared trees, and rollback journals",
    "SIA state lock files and publication stages",
    "SIA state test quarantines",
    "volatile status.json",
)

_SHARE_FILES = ("ledger.tsv", "ledger.pending", "pub.hex", "head.pin")
_SHARE_TREES = ("corpus", "research")
_STATE_TOP_OMIT = frozenset({
    "managed-install", "managed-mcp", "mcp-consumer-guards",
    "model-manifest-backups", "status.json",
})
_CONFIG_TOP_OMIT = frozenset({"continuity.json"})
_HEX_KEY = re.compile(rb"[0-9a-f]{64}\n?")
_HEX_PUBLIC = re.compile(rb"[0-9a-f]{64}\n?")
_HEX_HEAD = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_OPERATION_NAME = re.compile(r"[0-9a-f]{32}-[0-9a-f]{32}")
_FAILED_LIVE_NAME = re.compile(r"failed-live-[0-9a-f]{32}")
_JOURNAL_STAGE_NAME = re.compile(r"[.]journal[.]json[.][0-9a-f]{32}")
_THAW_PHASES = frozenset({
    "barrier", "mutating", "first-light", "rolling-back",
    "settling-adoption", "cleaning-rollback", "cleaning-commit",
    "rolled-back", "committed", "retiring-rollback", "retiring-commit",
})
_INACTIVE_COMPLETE_PHASES = frozenset({
    "rolled-back", "committed", "retiring-rollback", "retiring-commit",
})
_CAPSULE_DIRECTORY_ENTRY_LIMIT = sialib.MAX_SOURCE_SCAN_ENTRIES
_CAPSULE_TREE_DEPTH_LIMIT = sialib.MAX_CONFIG_TAGS
_CAPSULE_TREE_RECORD_LIMIT = sialib.MAX_CONFIG_BYTES
_CAPSULE_PATH_BYTE_LIMIT = sialib.MAX_CONFIG_BYTES
# Reuse SIA's published finite scan/path ceilings.  Cleanup catalogs the whole
# candidate before the first unlink, so an over-bound tree is preserved and
# refused rather than partly erased.
_OPERATION_DIRECTORY_ENTRY_LIMIT = sialib.MAX_SOURCE_SCAN_ENTRIES
# JACKAL status=exact, parsed=64, exact=64; exact rational arithmetic
# outside the Lean certificate chain (NOT formal-bounded).  Operation trees
# add rollback/capsule/staging prefixes around already-bounded portable roots,
# so they need a separate finite deletion-preflight depth policy.
_OPERATION_TREE_DEPTH_LIMIT = 64
_OPERATION_TREE_RECORD_LIMIT = sialib.MAX_CONFIG_BYTES


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_nlink, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns)


def _generation_record(value):
    return {
        "device": value.st_dev,
        "inode": value.st_ino,
        "mode": value.st_mode,
        "owner": value.st_uid,
        "links": value.st_nlink,
        "size": value.st_size,
        "modified_ns": value.st_mtime_ns,
        "changed_ns": value.st_ctime_ns,
    }


def _valid_generation_record(value):
    return isinstance(value, dict) \
        and set(value) == {
            "device", "inode", "mode", "owner", "links", "size",
            "modified_ns", "changed_ns"} \
        and all(type(item) is int for item in value.values())


def _valid_root_identity(value):
    return isinstance(value, dict) \
        and set(value) == {"device", "inode", "mode", "owner"} \
        and all(type(item) is int for item in value.values())


def _valid_sidecar_record(value):
    return isinstance(value, dict) \
        and set(value) == {"generation", "content"} \
        and _valid_generation_record(value.get("generation")) \
        and isinstance(value.get("content"), dict) \
        and set(value["content"]) == {
            "mode", "owner", "links", "size", "sha256"} \
        and all(type(value["content"].get(key)) is int
                for key in ("mode", "owner", "links", "size")) \
        and isinstance(value["content"].get("sha256"), str) \
        and re.fullmatch(
            r"[0-9a-f]{64}", value["content"]["sha256"]) is not None


def _root_identity(value):
    return {
        "device": value.st_dev,
        "inode": value.st_ino,
        "mode": stat.S_IMODE(value.st_mode),
        "owner": value.st_uid,
    }


def _canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _fsync_dir(path):
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
             | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError("capsule directory is not an owned real directory")
        os.fsync(fd)
    finally:
        os.close(fd)


def _owned_real_dir(path, label):
    path = os.path.abspath(path)
    if os.path.realpath(path) != path:
        raise ValueError(f"{label} path contains a symbolic link")
    info = os.lstat(path)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise ValueError(f"{label} is not an owned real directory")
    return path


def _rename_noreplace_fd(parent_fd, source_name, destination_name):
    """Atomically rename siblings through one already-authenticated parent."""
    if any(not isinstance(name, str) or not name
           or name in {".", ".."} or os.sep in name
           for name in (source_name, destination_name)):
        raise ValueError("capsule publication name is unsafe")
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        operation = libc.renameat2
    except AttributeError as exc:
        raise RuntimeError(
            "atomic no-clobber capsule publication is unavailable") \
            from exc
    operation.argtypes = (
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
        ctypes.c_uint)
    operation.restype = ctypes.c_int
    if operation(
            parent_fd, os.fsencode(source_name),
            parent_fd, os.fsencode(destination_name), 1) != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise FileExistsError(destination_name)
        raise OSError(error, os.strerror(error), destination_name)
    os.fsync(parent_fd)


def _rename_noreplace(parent, source_name, destination_name):
    """Atomically publish one sibling directory without clobbering a path."""
    directory_flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                       | getattr(os, "O_CLOEXEC", 0)
                       | getattr(os, "O_NOFOLLOW", 0))
    parent_fd = os.open(parent, directory_flags)
    try:
        held = os.fstat(parent_fd)
        linked = os.lstat(parent)
        if not stat.S_ISDIR(held.st_mode) or held.st_uid != os.geteuid() \
                or (held.st_dev, held.st_ino) != \
                   (linked.st_dev, linked.st_ino):
            raise ValueError("capsule publication parent changed")
        _rename_noreplace_fd(parent_fd, source_name, destination_name)
    finally:
        os.close(parent_fd)


def _open_owned_dir_at(parent_fd, name, label):
    """Open one owned real child directory and bind its linked generation."""
    if not isinstance(name, str) or not name or name in {".", ".."} \
            or os.sep in name:
        raise ValueError(f"{label} name is unsafe")
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
             | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    fd = os.open(name, flags, dir_fd=parent_fd)
    try:
        held = os.fstat(fd)
        linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(held.st_mode) or held.st_uid != os.geteuid() \
                or (held.st_dev, held.st_ino) != \
                   (linked.st_dev, linked.st_ino):
            raise ValueError(f"{label} changed while opened")
        return fd
    except Exception:
        os.close(fd)
        raise


def _linked_dir_matches(parent_fd, name, held_fd):
    try:
        linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    held = os.fstat(held_fd)
    return stat.S_ISDIR(linked.st_mode) \
        and linked.st_uid == os.geteuid() \
        and (linked.st_dev, linked.st_ino) == (held.st_dev, held.st_ino)


def _read_regular_at(parent_fd, name, label, *, maximum=MAX_DOCUMENT_BYTES):
    """Read one stable owned single-link file through an authenticated dir."""
    if not isinstance(name, str) or not name or name in {".", ".."} \
            or os.sep in name:
        raise ValueError(f"{label} name is unsafe")
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0))
    fd = os.open(name, flags, dir_fd=parent_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() or before.st_nlink != 1:
            raise ValueError(
                f"{label} is not an owned single-link regular file")
        if before.st_size > maximum:
            raise ValueError(f"{label} exceeds its size bound")
        chunks = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(fd)
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if len(raw) > maximum or len(raw) != before.st_size \
                or _generation(before) != _generation(after) \
                or _generation(after) != _generation(current):
            raise ValueError(f"{label} changed while read")
        return raw, before
    finally:
        os.close(fd)


def _write_exclusive_at(parent_fd, name, data, mode=0o600):
    """Durably create one sibling file through an authenticated directory."""
    if not isinstance(data, bytes):
        raise TypeError("exclusive publication requires bytes")
    if not isinstance(name, str) or not name or name in {".", ".."} \
            or os.sep in name:
        raise ValueError("exclusive publication name is unsafe")
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
             | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    fd = os.open(name, flags, mode, dir_fd=parent_fd)
    try:
        os.fchmod(fd, mode)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short capsule publication")
            view = view[written:]
        os.fsync(fd)
    except Exception:
        try:
            os.unlink(name, dir_fd=parent_fd)
        except OSError:
            pass
        raise
    finally:
        os.close(fd)
    os.fsync(parent_fd)


def _read_regular(path, label, *, maximum=MAX_DOCUMENT_BYTES,
                  private=False):
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0))
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() or before.st_nlink != 1:
            raise ValueError(f"{label} is not an owned single-link regular file")
        if private and stat.S_IMODE(before.st_mode) & 0o077:
            raise ValueError(f"{label} is not owner-private")
        if before.st_size > maximum:
            raise ValueError(f"{label} exceeds its size bound")
        chunks = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(fd)
        current = os.stat(path, follow_symlinks=False)
        if len(raw) > maximum or len(raw) != before.st_size \
                or _generation(before) != _generation(after) \
                or _generation(after) != _generation(current):
            raise ValueError(f"{label} changed while read")
        return raw, before
    finally:
        os.close(fd)


def _strict_json(raw, label):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label} contains a duplicate JSON key")
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8", "strict"),
                          object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"{label} is not strict JSON") from exc


def _read_json(path, label, *, private=False):
    raw, _info = _read_regular(path, label, private=private)
    return _strict_json(raw, label)


def _write_exclusive(path, data, mode=0o600):
    if not isinstance(data, bytes):
        raise TypeError("exclusive publication requires bytes")
    parent = _owned_real_dir(
        os.path.dirname(os.path.abspath(path)), "publication parent")
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
             | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    fd = os.open(path, flags, mode)
    try:
        os.fchmod(fd, mode)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short capsule publication")
            view = view[written:]
        os.fsync(fd)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    finally:
        os.close(fd)
    _fsync_dir(parent)
    return path


def _private_key(path=None):
    path = LEDGER_KEY if path is None else path
    raw, _info = _read_regular(path, "SIA private identity", private=True)
    if _HEX_KEY.fullmatch(raw) is None:
        raise ValueError("SIA private identity is malformed")
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(
        raw.strip().decode("ascii")))


def _public_hex(path=None):
    path = LEDGER_PUBLIC if path is None else path
    raw, _info = _read_regular(path, "SIA public identity")
    if _HEX_PUBLIC.fullmatch(raw) is None:
        raise ValueError("SIA public identity is malformed")
    return raw.strip().decode("ascii")


def _derived_public_hex(private):
    raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    return raw.hex()


def export_identity_key(output_path):
    """Publish the live signing identity once to owner-controlled media."""
    if not os.path.isabs(output_path):
        raise ValueError("identity recovery output must be an absolute path")
    candidate = os.path.abspath(output_path)
    parent = _owned_real_dir(
        os.path.dirname(candidate), "identity recovery parent")
    parent_info = os.lstat(parent)
    if stat.S_IMODE(parent_info.st_mode) & 0o077:
        raise ValueError("identity recovery parent is not owner-private")
    for authority in (sialib.SHARE, sialib.STATE, CONFIG_ROOT,
                      CONTINUITY_ROOT):
        authority = os.path.realpath(os.path.abspath(authority))
        resolved_candidate = os.path.join(
            os.path.realpath(os.path.dirname(candidate)),
            os.path.basename(candidate))
        try:
            nested = os.path.commonpath(
                (resolved_candidate, authority)) == authority
        except ValueError:
            nested = False
        if nested:
            raise ValueError(
                "offline identity output cannot be inside a SIA authority root")
    private_raw, _info = _read_regular(
        LEDGER_KEY, "SIA private identity", private=True)
    if _HEX_KEY.fullmatch(private_raw) is None:
        raise ValueError("SIA private identity is malformed")
    private = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(
        private_raw.strip().decode("ascii")))
    public = _public_hex()
    if _derived_public_hex(private) != public:
        raise ValueError("SIA private and public identities do not match")
    fingerprint = hashlib.sha256(bytes.fromhex(public)).hexdigest()
    document = {
        "schema": IDENTITY_SCHEMA,
        "private_key": private_raw.strip().decode("ascii"),
        "public_key": public,
        "fingerprint": fingerprint,
    }
    encoded = _canonical_bytes(document)
    published = _write_exclusive(output_path, encoded, 0o600)
    checked, checked_info = _read_regular(
        published, "published offline identity", private=True)
    if checked != encoded or stat.S_IMODE(checked_info.st_mode) != 0o600:
        raise RuntimeError("offline identity publication did not remain exact")
    current_parent = os.lstat(parent)
    if not stat.S_ISDIR(current_parent.st_mode) \
            or (parent_info.st_dev, parent_info.st_ino, parent_info.st_uid) \
            != (current_parent.st_dev, current_parent.st_ino,
                current_parent.st_uid) \
            or stat.S_IMODE(current_parent.st_mode) & 0o077:
        raise RuntimeError("identity recovery parent changed during publication")
    return {"path": published, "fingerprint": fingerprint}


def validate_identity_key(path, expected_public):
    if not os.path.isabs(path):
        raise ValueError("identity recovery file must be an absolute path")
    if os.path.realpath(path) != os.path.abspath(path):
        raise ValueError("identity recovery path contains a symbolic link")
    value = _read_json(path, "offline identity recovery file", private=True)
    if set(value) != {"schema", "private_key", "public_key", "fingerprint"} \
            or value.get("schema") != IDENTITY_SCHEMA \
            or not isinstance(value.get("private_key"), str) \
            or re.fullmatch(r"[0-9a-f]{64}", value["private_key"]) is None \
            or value.get("public_key") != expected_public:
        raise ValueError("offline identity recovery file has invalid schema")
    private = Ed25519PrivateKey.from_private_bytes(
        bytes.fromhex(value["private_key"]))
    if _derived_public_hex(private) != expected_public:
        raise ValueError("offline identity does not match prepared public identity")
    fingerprint = hashlib.sha256(bytes.fromhex(expected_public)).hexdigest()
    if value.get("fingerprint") != fingerprint:
        raise ValueError("offline identity fingerprint is invalid")
    return value


def roots():
    """Return the stable portable-root contract without secret contents."""
    return {
        "schema": ROOTS_SCHEMA,
        "do_not_walk_live": True,
        "source_constraints": {
            "directories": "owned-real",
            "files": "owned-single-link-regular",
            "symbolic_links": "refuse",
            "special_files": "refuse",
        },
        "authorities": [
            {
                "area": "share",
                "path": os.path.abspath(sialib.SHARE),
                "selection": {
                    "mode": "allowlist",
                    "trees": list(_SHARE_TREES),
                    "files": list(_SHARE_FILES),
                    "exclude_path_components": [".gbrain"],
                    "path_component_matching": "case-sensitive",
                },
            },
            {
                "area": "state",
                "path": os.path.abspath(sialib.STATE),
                "selection": {
                    "mode": "recursive-except",
                    "exclude_top_level_names": sorted(_STATE_TOP_OMIT),
                    "exclude_path_components": [".gbrain"],
                    "exclude_basename_exact": ["publish.lock"],
                    "exclude_basename_suffixes": [".lock"],
                    "exclude_basename_contains": [
                        ".sia-stage", "quarantine"],
                    "basename_pattern_normalization": "lower",
                    "top_level_matching": "case-sensitive",
                },
            },
            {
                "area": "config",
                "path": os.path.abspath(CONFIG_ROOT),
                "selection": {
                    "mode": "recursive-except",
                    "exclude_top_level_names": sorted(_CONFIG_TOP_OMIT),
                    "exclude_top_level_prefixes": ["continuity."],
                    "exclude_path_components": [".gbrain"],
                    "exclude_basename_contains": [
                        "credential", "password", "repository.key"],
                    "basename_pattern_normalization": "lower",
                    "top_level_matching": "case-sensitive",
                },
            },
        ],
        "omissions": list(OMISSIONS),
    }


def _excluded(area, relative):
    parts = relative.split(os.sep)
    name = parts[-1]
    lowered = name.lower()
    if any(part == ".gbrain" for part in parts):
        return True
    if area == "state":
        if parts[0] in _STATE_TOP_OMIT:
            return True
        if lowered.endswith(".lock") or lowered == "publish.lock" \
                or ".sia-stage" in lowered or "quarantine" in lowered:
            return True
    if area == "config":
        if parts[0] in _CONFIG_TOP_OMIT or parts[0].startswith("continuity."):
            return True
        if any(token in lowered for token in
               ("credential", "password", "repository.key")):
            return True
    return False


def _copy_file(source, target, manifest_path):
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0))
    source_fd = os.open(source, flags)
    target_fd = -1
    try:
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() or before.st_nlink != 1:
            raise ValueError(f"unsafe capsule source file: {source}")
        target_fd = os.open(
            target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            stat.S_IMODE(before.st_mode) & 0o777)
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(target_fd, view)
                if written <= 0:
                    raise OSError("short capsule copy")
                view = view[written:]
            size += len(chunk)
        os.fchmod(target_fd, stat.S_IMODE(before.st_mode) & 0o777)
        os.fsync(target_fd)
        after = os.fstat(source_fd)
        current = os.stat(source, follow_symlinks=False)
        if _generation(before) != _generation(after) \
                or _generation(after) != _generation(current) \
                or size != before.st_size:
            raise ValueError(f"capsule source changed while copied: {source}")
        return {
            "path": manifest_path,
            "type": "file",
            "mode": stat.S_IMODE(before.st_mode) & 0o777,
            "size": size,
            "sha256": digest.hexdigest(),
        }
    finally:
        if target_fd >= 0:
            os.close(target_fd)
        os.close(source_fd)


def _hash_regular(path, label):
    """Stream a stable payload file without imposing a JSON-sized ceiling."""
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0))
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() or before.st_nlink != 1:
            raise ValueError(f"{label} is not an owned single-link regular file")
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(fd)
        current = os.stat(path, follow_symlinks=False)
        if size != before.st_size or _generation(before) != _generation(after) \
                or _generation(after) != _generation(current):
            raise ValueError(f"{label} changed while hashed")
        return size, digest.hexdigest(), before
    finally:
        os.close(fd)


def _copy_tree(source, target, manifest_prefix, area, entries,
               area_relative="", *, budget=None, depth=0):
    if budget is None:
        budget = {"records": 0}
    if depth > _CAPSULE_TREE_DEPTH_LIMIT:
        raise ValueError("capsule source tree exceeds its depth bound")
    try:
        encoded_prefix = manifest_prefix.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise ValueError("capsule source path is not UTF-8") from exc
    if len(encoded_prefix) > _CAPSULE_PATH_BYTE_LIMIT:
        raise ValueError("capsule source path exceeds its byte bound")
    before = os.lstat(source)
    if not stat.S_ISDIR(before.st_mode) or before.st_uid != os.geteuid():
        raise ValueError(f"unsafe capsule source directory: {source}")
    os.mkdir(target, stat.S_IMODE(before.st_mode) & 0o777)
    child_records = []
    children = []
    with os.scandir(source) as scan:
        for child in scan:
            children.append(child)
            if len(children) > _CAPSULE_DIRECTORY_ENTRY_LIMIT:
                raise ValueError(
                    "capsule source directory exceeds its entry bound")
    children.sort(key=lambda entry: entry.name)
    for child in children:
        budget["records"] += 1
        if budget["records"] > _CAPSULE_TREE_RECORD_LIMIT:
            raise ValueError("capsule source tree exceeds its record bound")
        area_child = os.path.join(area_relative, child.name) \
            if area_relative else child.name
        if _excluded(area, area_child):
            continue
        info = child.stat(follow_symlinks=False)
        destination = os.path.join(target, child.name)
        manifest_path = (manifest_prefix.rstrip("/") + "/" + child.name)
        if stat.S_ISDIR(info.st_mode):
            _copy_tree(child.path, destination, manifest_path, area, entries,
                       area_child, budget=budget, depth=depth + 1)
            child_records.append((child.name, "directory"))
        elif stat.S_ISREG(info.st_mode):
            row = _copy_file(child.path, destination, manifest_path)
            entries.append(row)
            child_records.append((child.name, row["sha256"]))
        else:
            raise ValueError(f"capsule source contains a link or special file: "
                             f"{child.path}")
    os.chmod(target, stat.S_IMODE(before.st_mode) & 0o777)
    _fsync_dir(target)
    after = os.lstat(source)
    if _generation(before) != _generation(after):
        raise ValueError(f"capsule source directory changed: {source}")
    encoded = _canonical_bytes(child_records)
    entries.append({
        "path": manifest_prefix,
        "type": "directory",
        "mode": stat.S_IMODE(before.st_mode) & 0o777,
        "size": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    })


@contextlib.contextmanager
def _freeze_locks():
    """Quiesce portable writers without stopping or pre-empting brainstem."""
    lock_paths = sorted({
        os.path.join(sialib.SHARE, "ledger.lock"),
        os.path.join(sialib.STATE, "agent-inbox", ".queue.lock"),
        getattr(sialib, "THOUGHT_INBOX_LOCK",
                os.path.join(sialib.STATE, "thought-inbox.lock")),
        os.path.join(sialib.STATE, "touch-queue.jsonl.lock"),
        os.path.join(sialib.STATE, "recovery-unpin-queue.jsonl.lock"),
        os.path.join(sialib.STATE, "thought-recovery.lock"),
        os.path.join(sialib.STATE, "take-proposals.json.lock"),
    })
    descriptors = _acquire_freeze_locks(lock_paths)
    try:
        yield
    finally:
        _release_freeze_locks(descriptors)


def _acquire_freeze_locks(lock_paths=None):
    if lock_paths is None:
        lock_paths = sorted({
            os.path.join(sialib.SHARE, "ledger.lock"),
            os.path.join(sialib.STATE, "agent-inbox", ".queue.lock"),
            getattr(sialib, "THOUGHT_INBOX_LOCK",
                    os.path.join(sialib.STATE, "thought-inbox.lock")),
            os.path.join(sialib.STATE, "touch-queue.jsonl.lock"),
            os.path.join(sialib.STATE, "recovery-unpin-queue.jsonl.lock"),
            os.path.join(sialib.STATE, "thought-recovery.lock"),
            os.path.join(sialib.STATE, "take-proposals.json.lock"),
        })
    descriptors = []
    try:
        for path in lock_paths:
            parent = os.path.dirname(path)
            if not os.path.isdir(parent):
                continue
            flags = (os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
                     | getattr(os, "O_NOFOLLOW", 0))
            descriptor = os.open(path, flags, 0o600)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) \
                    or info.st_uid != os.geteuid() or info.st_nlink != 1:
                os.close(descriptor)
                raise ValueError("unsafe SIA freeze lock")
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            descriptors.append(descriptor)
        return descriptors
    except Exception:
        _release_freeze_locks(descriptors)
        raise


def _release_freeze_locks(descriptors):
    for descriptor in reversed(descriptors):
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _git_head_at(corpus):
    result = sialib._run_bounded_text_process(
        ["git", "rev-parse", "--verify", "HEAD"], env=None,
        timeout=sialib.JOURNAL_TIMEOUT_SECONDS, cwd=corpus,
        label="capsule corpus HEAD", output_limit=sialib.MAX_CONFIG_BYTES)
    head = result.stdout.strip()
    if result.returncode != 0 or _HEX_HEAD.fullmatch(head) is None:
        raise RuntimeError("capsule could not bind the corpus HEAD")
    return head


def _git_head():
    return _git_head_at(sialib.CORPUS)


def _read_head_pin(root, label):
    raw, _info = _read_regular(os.path.join(root, "head.pin"), label)
    matched = re.fullmatch(rb"([1-9][0-9]*) ([0-9a-f]{64})\n", raw)
    if matched is None:
        raise ValueError(f"{label} is malformed")
    return int(matched.group(1)), matched.group(2).decode("ascii")


def _verify_copied_ledger(share_root):
    ledger_tool = os.path.join(sialib.BIN, "sia-ledger")
    result = sialib._run_bounded_text_process(
        [ledger_tool, "verify", share_root, "--quiet"], env=None,
        timeout=sialib.JOURNAL_TIMEOUT_SECONDS, cwd=None,
        label="copied SIA ledger verifier",
        output_limit=sialib.MAX_CONFIG_BYTES)
    lock_path = os.path.join(share_root, "ledger.lock")
    if os.path.lexists(lock_path):
        info = os.lstat(lock_path)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
                or info.st_nlink != 1:
            raise ValueError("copied ledger verifier left an unsafe lock")
        os.unlink(lock_path)
        _fsync_dir(share_root)
    if result.returncode != 0:
        raise RuntimeError("copied SIA ledger failed verification")
    return "pass"


def freeze(output_path):
    """Create and sign one portable capsule at a new absolute directory."""
    if os.path.lexists(RESTORE_BARRIER):
        raise RuntimeError(
            "portable freeze is blocked by an interrupted restore")
    if not os.path.isabs(output_path):
        raise ValueError("capsule output must be an absolute path")
    output_path = os.path.abspath(output_path)
    parent = _owned_real_dir(os.path.dirname(output_path), "capsule parent")
    parent_info = os.lstat(parent)
    if stat.S_IMODE(parent_info.st_mode) & 0o077:
        raise ValueError("capsule parent is not owner-private")
    resolved_output = os.path.join(
        os.path.realpath(parent), os.path.basename(output_path))
    for authority in (sialib.SHARE, sialib.STATE, CONFIG_ROOT):
        authority = os.path.realpath(os.path.abspath(authority))
        try:
            nested = os.path.commonpath(
                (resolved_output, authority)) == authority
        except ValueError:
            nested = False
        if nested:
            raise ValueError("capsule output cannot be inside a SIA authority root")
    if os.path.lexists(output_path):
        raise FileExistsError("capsule output already exists")
    stage_path = os.path.join(
        parent, ".sia-capsule-stage-" + uuid.uuid4().hex)
    entries = []
    copy_budget = {"records": 0}
    freeze_descriptors = []
    try:
        os.mkdir(stage_path, 0o700)
        payload = os.path.join(stage_path, PAYLOAD_NAME)
        os.mkdir(payload, 0o700)
        with sialib.corpus_owner():
            ready, readiness_reason = sialib.memory_readiness()
            freeze_descriptors = _acquire_freeze_locks()
            corpus_head = _git_head()
            ledger_sequence, ledger_head = _read_head_pin(
                sialib.SHARE, "signed SIA ledger head")
            if not isinstance(ledger_sequence, int) or ledger_sequence < 1 \
                    or not isinstance(ledger_head, str) \
                    or re.fullmatch(r"[0-9a-f]{64}", ledger_head) is None:
                raise RuntimeError("capsule could not bind the signed SIA ledger head")
            public = _public_hex()
            private = _private_key()
            if _derived_public_hex(private) != public:
                raise ValueError("live SIA identity keypair does not match")
            corpus_info = os.lstat(sialib.CORPUS)
            receipt_raw, receipt_info = _read_regular(
                CORPUS_RECEIPT, "source corpus receipt", private=True)
            expected_receipt = (
                "managed-by=khephri.sia\nkind=corpus-v2\npath="
                + os.path.abspath(sialib.CORPUS) + "\nroot="
                + ":".join(str(value) for value in (
                    corpus_info.st_dev, corpus_info.st_ino,
                    corpus_info.st_mode, corpus_info.st_uid))
                + "\n").encode("utf-8")
            if receipt_raw != expected_receipt:
                raise ValueError(
                    "source corpus receipt does not bind the live corpus root")
            source_receipt = {
                "sha256": hashlib.sha256(receipt_raw).hexdigest(),
                "mode": stat.S_IMODE(receipt_info.st_mode),
            }

            share_target = os.path.join(payload, "share")
            os.mkdir(share_target, 0o700)
            present_roots = {}
            for name in _SHARE_TREES:
                source = os.path.join(sialib.SHARE, name)
                present_roots["share/" + name] = os.path.lexists(source)
                if not os.path.lexists(source):
                    if name == "corpus":
                        raise ValueError("SIA corpus is missing")
                    continue
                _copy_tree(source, os.path.join(share_target, name),
                           "share/" + name, "share", entries,
                           budget=copy_budget)
            for name in _SHARE_FILES:
                source = os.path.join(sialib.SHARE, name)
                present_roots["share/" + name] = os.path.lexists(source)
                if not os.path.lexists(source):
                    continue
                copy_budget["records"] += 1
                if copy_budget["records"] > _CAPSULE_TREE_RECORD_LIMIT:
                    raise ValueError(
                        "capsule source tree exceeds its record bound")
                entries.append(_copy_file(
                    source, os.path.join(share_target, name),
                    "share/" + name))
            _fsync_dir(share_target)

            present_roots["state"] = os.path.lexists(sialib.STATE)
            if present_roots["state"]:
                _copy_tree(sialib.STATE, os.path.join(payload, "state"),
                           "state", "state", entries, budget=copy_budget)
            present_roots["config"] = os.path.lexists(CONFIG_ROOT)
            if present_roots["config"]:
                _copy_tree(CONFIG_ROOT, os.path.join(payload, "config"),
                           "config", "config", entries, budget=copy_budget)
            _fsync_dir(payload)

            # External verifier processes must never inherit a live ledger
            # lock they need to acquire themselves.  The copied generation is
            # now immutable and can be verified safely off-path.
            _release_freeze_locks(freeze_descriptors)
            freeze_descriptors = []
            chains = {"sia": _verify_copied_ledger(share_target)}

            classification = "ready" if ready \
                and chains.get("sia") == "pass" \
                else "recovery-only"
            unsigned = {
                "schema": CAPSULE_SCHEMA,
                "root_contract_schema": ROOTS_SCHEMA,
                "capsule_id": uuid.uuid4().hex,
                "captured_at": _now(),
                "sia_version": sialib.VERSION,
                "classification": classification,
                "readiness": {"ready": bool(ready),
                              "reason": str(readiness_reason)},
                "chains": chains,
                "corpus_head": corpus_head,
                "ledger": {"sequence": ledger_sequence,
                           "head": ledger_head},
                "identity": {
                    "public_key": public,
                    "fingerprint": hashlib.sha256(
                        bytes.fromhex(public)).hexdigest(),
                },
                "source": {
                    "corpus_root": _root_identity(corpus_info),
                    "corpus_receipt": source_receipt,
                },
                "roots": present_roots,
                "omissions": list(OMISSIONS),
                "entries": sorted(entries, key=lambda row: row["path"]),
            }
            signed_bytes = _canonical_bytes(unsigned)
            if len(signed_bytes) > MAX_DOCUMENT_BYTES:
                raise ValueError("capsule manifest exceeds its size bound")
            manifest = dict(unsigned)
            manifest["signature"] = {
                "algorithm": "ed25519",
                "value": private.sign(signed_bytes).hex(),
            }
            manifest_bytes = _canonical_bytes(manifest)
            if len(manifest_bytes) > MAX_DOCUMENT_BYTES:
                raise ValueError("signed capsule manifest exceeds its size bound")
            _write_exclusive(os.path.join(stage_path, MANIFEST_NAME),
                             manifest_bytes, 0o600)
            _fsync_dir(stage_path)
        if os.path.lexists(output_path):
            raise FileExistsError("capsule output appeared during freeze")
        _rename_noreplace(
            parent, os.path.basename(stage_path), os.path.basename(output_path))
        return {
            "capsule_id": manifest["capsule_id"],
            "path": output_path,
            "classification": manifest["classification"],
            "public_key": public,
            "manifest_sha256": hashlib.sha256(
                _canonical_bytes(manifest)).hexdigest(),
            "corpus_head": corpus_head,
            "ledger_head": ledger_head,
        }
    except Exception:
        if freeze_descriptors:
            _release_freeze_locks(freeze_descriptors)
        if os.path.lexists(stage_path):
            shutil.rmtree(stage_path)
            _fsync_dir(parent)
        raise


def _walk_payload(payload):
    rows = []
    directories = set()
    record_count = 0
    for root, dirs, files in os.walk(payload, topdown=True,
                                     followlinks=False):
        if len(dirs) + len(files) > _CAPSULE_DIRECTORY_ENTRY_LIMIT:
            raise ValueError(
                "prepared payload directory exceeds its entry bound")
        dirs.sort()
        files.sort()
        root_info = os.lstat(root)
        if not stat.S_ISDIR(root_info.st_mode) \
                or root_info.st_uid != os.geteuid():
            raise ValueError("prepared payload has an unsafe directory")
        if root != payload:
            relative_root = os.path.relpath(
                root, payload).replace(os.sep, "/")
            root_parts = relative_root.split("/")
            authority_parts = 2 if root_parts[0] == "share" else 1
            if len(root_parts) - authority_parts \
                    > _CAPSULE_TREE_DEPTH_LIMIT:
                raise ValueError("prepared payload exceeds its depth bound")
            directories.add(relative_root)
        for name in dirs + files:
            record_count += 1
            if record_count > _CAPSULE_TREE_RECORD_LIMIT:
                raise ValueError("prepared payload exceeds its record bound")
            path = os.path.join(root, name)
            info = os.lstat(path)
            relative = os.path.relpath(path, payload).replace(os.sep, "/")
            try:
                encoded_relative = relative.encode("utf-8", "strict")
            except UnicodeError as exc:
                raise ValueError("prepared payload path is not UTF-8") \
                    from exc
            if len(encoded_relative) > _CAPSULE_PATH_BYTE_LIMIT:
                raise ValueError(
                    "prepared payload path exceeds its byte bound")
            logical = relative
            if stat.S_ISLNK(info.st_mode) \
                    or not (stat.S_ISDIR(info.st_mode)
                            or stat.S_ISREG(info.st_mode)):
                raise ValueError("prepared payload contains a link or special file")
            if stat.S_ISREG(info.st_mode):
                size, digest, stable = _hash_regular(
                    path, "prepared payload file")
                rows.append({
                    "path": logical, "type": "file",
                    "mode": stat.S_IMODE(stable.st_mode) & 0o777,
                    "size": size,
                    "sha256": digest,
                })
    return rows, directories


def verify(capsule_path):
    """Authenticate a capsule and validate every payload object off-path."""
    if not os.path.isabs(capsule_path):
        raise ValueError("capsule path must be absolute")
    capsule_path = os.path.abspath(capsule_path)
    if os.path.realpath(capsule_path) != capsule_path:
        raise ValueError("capsule path contains a symbolic link")
    capsule_info = os.lstat(capsule_path)
    if not stat.S_ISDIR(capsule_info.st_mode) \
            or capsule_info.st_uid != os.geteuid():
        raise ValueError("capsule root is not an owned real directory")
    manifest = _read_json(os.path.join(capsule_path, MANIFEST_NAME),
                          "capsule manifest")
    required = {
        "schema", "root_contract_schema", "capsule_id", "captured_at",
        "sia_version",
        "classification", "readiness", "chains", "corpus_head", "ledger",
        "identity", "source", "roots", "omissions", "entries", "signature",
    }
    if set(manifest) != required or manifest.get("schema") != CAPSULE_SCHEMA \
            or manifest.get("root_contract_schema") != ROOTS_SCHEMA \
            or manifest.get("omissions") != list(OMISSIONS):
        raise ValueError("capsule manifest schema is invalid")
    allowed_roots = ({"share/" + name for name in _SHARE_TREES}
                     | {"share/" + name for name in _SHARE_FILES}
                     | {"state", "config"})
    roots_value = manifest.get("roots")
    readiness = manifest.get("readiness")
    chains = manifest.get("chains")
    ledger = manifest.get("ledger")
    source = manifest.get("source")
    if not isinstance(manifest.get("capsule_id"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", manifest["capsule_id"]) is None \
            or not isinstance(manifest.get("captured_at"), str) \
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
                            r"[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
                            manifest["captured_at"]) is None \
            or not isinstance(manifest.get("sia_version"), str) \
            or not manifest["sia_version"] \
            or manifest.get("classification") not in {
                "ready", "recovery-only"} \
            or not isinstance(readiness, dict) \
            or set(readiness) != {"ready", "reason"} \
            or not isinstance(readiness.get("ready"), bool) \
            or not isinstance(readiness.get("reason"), str) \
            or not isinstance(chains, dict) or set(chains) != {"sia"} \
            or any(not isinstance(name, str)
                   or value not in {"pass", "fail", "absent"}
                   for name, value in chains.items()) \
            or not isinstance(manifest.get("corpus_head"), str) \
            or _HEX_HEAD.fullmatch(manifest["corpus_head"]) is None \
            or not isinstance(ledger, dict) \
            or set(ledger) != {"sequence", "head"} \
            or type(ledger.get("sequence")) is not int \
            or ledger["sequence"] < 1 \
            or not isinstance(ledger.get("head"), str) \
            or re.fullmatch(r"[0-9a-f]{64}", ledger["head"]) is None \
            or not isinstance(roots_value, dict) \
            or set(roots_value) != allowed_roots \
            or any(not isinstance(value, bool)
                   for value in roots_value.values()) \
            or roots_value.get("share/corpus") is not True:
        raise ValueError("capsule manifest semantic fields are invalid")
    if manifest["classification"] == "ready" \
            and (readiness["ready"] is not True
                 or chains.get("sia") != "pass"):
        raise ValueError("capsule readiness classification is inconsistent")
    if not isinstance(source, dict) \
            or set(source) != {"corpus_root", "corpus_receipt"} \
            or not isinstance(source.get("corpus_root"), dict) \
            or set(source["corpus_root"]) != {
                "device", "inode", "mode", "owner"} \
            or any(type(value) is not int
                   for value in source["corpus_root"].values()) \
            or not isinstance(source.get("corpus_receipt"), dict) \
            or set(source["corpus_receipt"]) != {"sha256", "mode"} \
            or re.fullmatch(r"[0-9a-f]{64}", str(
                source["corpus_receipt"].get("sha256"))) is None \
            or type(source["corpus_receipt"].get("mode")) is not int:
        raise ValueError("capsule source provenance is invalid")
    signature = manifest.get("signature")
    if not isinstance(signature, dict) \
            or set(signature) != {"algorithm", "value"} \
            or signature.get("algorithm") != "ed25519" \
            or not isinstance(signature.get("value"), str) \
            or re.fullmatch(r"[0-9a-f]{128}", signature["value"]) is None:
        raise ValueError("capsule signature schema is invalid")
    identity = manifest.get("identity")
    public = identity.get("public_key") if isinstance(identity, dict) else None
    if not isinstance(identity, dict) \
            or set(identity) != {"public_key", "fingerprint"} \
            or not isinstance(public, str) \
            or re.fullmatch(r"[0-9a-f]{64}", public) is None \
            or identity.get("fingerprint") != hashlib.sha256(
                bytes.fromhex(public)).hexdigest():
        raise ValueError("capsule public identity is invalid")
    unsigned = dict(manifest)
    del unsigned["signature"]
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public)).verify(
            bytes.fromhex(signature["value"]), _canonical_bytes(unsigned))
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("capsule manifest signature is invalid") from exc
    entries = manifest.get("entries")
    if not isinstance(entries, list) or any(not isinstance(row, dict)
                                             for row in entries):
        raise ValueError("capsule entry table is invalid")
    for row in entries:
        if set(row) != {"path", "type", "mode", "size", "sha256"} \
                or not isinstance(row.get("path"), str) \
                or not row["path"] \
                or row.get("type") not in {"file", "directory"} \
                or type(row.get("mode")) is not int \
                or row["mode"] < 0 or row["mode"] > 0o777 \
                or type(row.get("size")) is not int or row["size"] < 0 \
                or not isinstance(row.get("sha256"), str) \
                or re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None:
            raise ValueError("capsule entry metadata is invalid")
        path_parts = row["path"].split("/")
        if row["path"].startswith("/") or ".." in path_parts \
                or "" in path_parts:
            raise ValueError("capsule entry path is unsafe")
        if path_parts[0] not in {"share", "state", "config"}:
            raise ValueError("capsule entry is outside portable roots")
        if path_parts[0] == "share":
            if len(path_parts) < 2 \
                    or ("share/" + path_parts[1]) not in allowed_roots:
                raise ValueError("capsule share entry is not allowlisted")
            if path_parts[1] in _SHARE_FILES and len(path_parts) != 2:
                raise ValueError("capsule share control file is not a leaf")
        root_name = ("share/" + path_parts[1]
                     if path_parts[0] == "share" else path_parts[0])
        if roots_value.get(root_name) is not True:
            raise ValueError("capsule entry contradicts absent-root metadata")
    expected = {row.get("path"): row for row in entries}
    if None in expected or len(expected) != len(entries):
        raise ValueError("capsule entry paths are invalid or duplicated")
    for root_name, present in roots_value.items():
        represented = root_name in expected
        if represented is not present:
            raise ValueError("capsule root-presence table is inconsistent")
    payload = os.path.join(capsule_path, PAYLOAD_NAME)
    walked_files, actual_directories = _walk_payload(payload)
    actual_files = {row["path"]: row for row in walked_files}
    expected_files = {path: row for path, row in expected.items()
                      if row.get("type") == "file"}
    if actual_files != expected_files:
        raise ValueError("capsule payload does not match its signed manifest")
    expected_directories = {path for path, row in expected.items()
                            if row.get("type") == "directory"}
    if actual_directories != expected_directories | {"share"}:
        raise ValueError("capsule payload contains an unsigned directory")
    for path, row in expected.items():
        if row.get("type") not in {"file", "directory"} \
                or not isinstance(path, str) or path.startswith("/") \
                or ".." in path.split("/"):
            raise ValueError("capsule entry table contains an unsafe path")
        if row["type"] == "directory":
            actual = os.path.join(payload, *path.split("/"))
            info = os.lstat(actual)
            if not stat.S_ISDIR(info.st_mode) \
                    or (stat.S_IMODE(info.st_mode) & 0o777) != row.get("mode"):
                raise ValueError("capsule directory metadata does not match")
            child_records = []
            with os.scandir(actual) as scan:
                children = sorted(scan, key=lambda item: item.name)
            for child in children:
                child_path = path.rstrip("/") + "/" + child.name
                child_row = expected.get(child_path)
                if child_row is None:
                    raise ValueError("capsule directory has unsigned content")
                child_records.append((
                    child.name,
                    "directory" if child_row.get("type") == "directory"
                    else child_row.get("sha256")))
            encoded = _canonical_bytes(child_records)
            if row.get("size") != len(encoded) \
                    or row.get("sha256") != hashlib.sha256(encoded).hexdigest():
                raise ValueError("capsule directory digest does not match")
    copied_public, _public_info = _read_regular(
        os.path.join(payload, "share", "pub.hex"),
        "capsule public identity")
    if copied_public != (public + "\n").encode("ascii"):
        raise ValueError("capsule public identity does not match its manifest")
    copied_sequence, copied_head = _read_head_pin(
        os.path.join(payload, "share"), "capsule ledger head")
    if copied_sequence != ledger["sequence"] or copied_head != ledger["head"]:
        raise ValueError("capsule ledger head does not match its manifest")
    if _git_head_at(os.path.join(payload, "share", "corpus")) \
            != manifest["corpus_head"]:
        raise ValueError("capsule corpus HEAD does not match its manifest")
    return {
        "schema": VERIFIED_SCHEMA,
        "capsule_id": manifest["capsule_id"],
        "classification": manifest["classification"],
        "corpus_head": manifest["corpus_head"],
        "ledger_head": manifest["ledger"]["head"],
        "public_key": public,
        "manifest_sha256": hashlib.sha256(
            _canonical_bytes(manifest)).hexdigest(),
        "capsule_path": capsule_path,
    }


def prepare_binding(capsule_path, *, prepared_id, snapshot_id):
    """Bind verified capsule facts to an adapter's opaque snapshot identity."""
    if not isinstance(prepared_id, str) \
            or re.fullmatch(r"[0-9a-f]{32}", prepared_id) is None:
        raise ValueError("prepared restore identifier is invalid")
    if not isinstance(snapshot_id, str) or not snapshot_id \
            or len(snapshot_id.encode("utf-8", "strict")) \
               > MAX_DOCUMENT_BYTES \
            or any(marker in snapshot_id for marker in ("\0", "\n", "\r")):
        raise ValueError("prepared snapshot identity is invalid")
    verified = verify(capsule_path)
    prepared = dict(verified)
    prepared["schema"] = PREPARED_SCHEMA
    prepared["prepared_id"] = prepared_id
    prepared["snapshot_id"] = snapshot_id
    return prepared


def identity_matches(prepared):
    try:
        return _public_hex() == prepared["public_key"] \
            and _derived_public_hex(_private_key()) == prepared["public_key"]
    except (OSError, ValueError):
        return False


def target_identity():
    info = os.lstat(sialib.CORPUS)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise ValueError("target corpus root is unsafe")
    receipt_raw, receipt_info = _read_regular(
        CORPUS_RECEIPT, "target corpus receipt", private=True)
    return {
        "corpus_root": _root_identity(info),
        "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "receipt_mode": stat.S_IMODE(receipt_info.st_mode),
    }


def _validate_exclusive_lock(descriptor, path, label):
    if type(descriptor) is not int or descriptor < 0:
        raise ValueError(f"{label} capability descriptor is invalid")
    held = os.fstat(descriptor)
    current = os.lstat(path)
    if not stat.S_ISREG(held.st_mode) or held.st_uid != os.geteuid() \
            or not stat.S_ISREG(current.st_mode) \
            or current.st_uid != os.geteuid() \
            or (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino):
        raise ValueError(f"{label} capability does not bind its live lock")
    probe = os.open(path, os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0))
    try:
        try:
            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(probe, fcntl.LOCK_UN)
            raise ValueError(f"{label} capability is not held")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError(f"{label} capability is not exclusive") from exc
    finally:
        os.close(probe)


def validate_restore_capability(capability):
    """Validate the worker's already-held quiescence capability.

    The worker must call ``thaw`` in the same process and while still inside
    the corresponding SIA owner contexts so nested readiness/first-light
    operations remain reentrant.
    """
    if not isinstance(capability, dict) or set(capability) != {
            "lifecycle_fd", "brainstem_fd", "corpus_fd", "gbrain_fd"}:
        raise ValueError("restore capability has invalid shape")
    bindings = (
        ("lifecycle_fd", sialib.LIFECYCLE_LOCK, "lifecycle"),
        ("brainstem_fd", sialib.BRAINSTEM_OWNER_LOCK, "brainstem"),
        ("corpus_fd", sialib.CORPUS_OWNER_LOCK, "corpus"),
        ("gbrain_fd", sialib.GBRAIN_OWNER_LOCK, "gbrain"),
    )
    for key, path, label in bindings:
        _validate_exclusive_lock(capability[key], path, label)
    return True


def _atomic_json(path, value):
    parent = _owned_real_dir(os.path.dirname(os.path.abspath(path)),
                             "journal parent")
    raw = _canonical_bytes(value)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError("thaw journal exceeds its size bound")
    temporary = os.path.join(parent, "." + os.path.basename(path)
                             + "." + uuid.uuid4().hex)
    _write_exclusive(temporary, raw, 0o600)
    try:
        if os.path.lexists(path):
            current = os.lstat(path)
            if not stat.S_ISREG(current.st_mode) \
                    or current.st_uid != os.geteuid() \
                    or current.st_nlink != 1:
                raise ValueError("thaw journal target is unsafe")
        os.replace(temporary, path)
        _fsync_dir(parent)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _target_ledger_head():
    raw, _info = _read_regular(
        os.path.join(sialib.SHARE, "head.pin"), "target ledger head pin")
    matched = re.fullmatch(rb"[1-9][0-9]* ([0-9a-f]{64})\n", raw)
    if matched is None:
        raise ValueError("target ledger head pin is malformed")
    return matched.group(1).decode("ascii")


def _validate_confirmation(confirmation, prepared, current_head):
    expected_keys = {"schema_version", "phrase", "snapshot_id",
                     "ledger_head", "corpus_receipt_re_adopt"}
    if not isinstance(confirmation, dict) \
            or set(confirmation) != expected_keys \
            or confirmation.get("schema_version") != 1 \
            or confirmation.get("phrase") != "RESTORE" \
            or confirmation.get("snapshot_id") != prepared.get("snapshot_id") \
            or confirmation.get("ledger_head") != current_head \
            or confirmation.get("corpus_receipt_re_adopt") is not True:
        raise ValueError("restore confirmation does not bind the prepared restore")


def _safe_children(path, area):
    if not os.path.isdir(path):
        return []
    names = []
    with os.scandir(path) as scan:
        for entry in sorted(scan, key=lambda item: item.name):
            if _excluded(area, entry.name):
                continue
            info = entry.stat(follow_symlinks=False)
            if info.st_uid != os.geteuid() \
                    or not (stat.S_ISDIR(info.st_mode)
                            or (stat.S_ISREG(info.st_mode)
                                and info.st_nlink == 1)):
                raise ValueError("live portable root contains an unsafe entry")
            names.append(entry.name)
    return names


def _move_aside(source, destination):
    if not os.path.lexists(source):
        return
    if os.path.lexists(destination):
        raise ValueError("thaw rollback destination already exists")
    parent = os.path.dirname(destination)
    os.makedirs(parent, mode=0o700, exist_ok=True)
    _owned_real_dir(parent, "thaw rollback directory")
    if os.stat(os.path.dirname(source)).st_dev != os.stat(parent).st_dev:
        raise ValueError("thaw rollback must be on the same filesystem")
    os.rename(source, destination)
    _fsync_dir(os.path.dirname(source))
    _fsync_dir(parent)


def _copy_payload_entry(source, target, logical, area):
    info = os.lstat(source)
    entries = []
    if stat.S_ISDIR(info.st_mode):
        _copy_tree(source, target, logical, area, entries)
    elif stat.S_ISREG(info.st_mode):
        entries.append(_copy_file(source, target, logical))
        _fsync_dir(os.path.dirname(target))
    else:
        raise ValueError("verified capsule changed before thaw")
    _fsync_dir(os.path.dirname(target))
    return entries


def _clear_live_portable(removed_root):
    """Move current portable content aside without replacing root inodes."""
    corpus_removed = os.path.join(removed_root, "corpus")
    for name in _safe_children(sialib.CORPUS, "share"):
        _move_aside(os.path.join(sialib.CORPUS, name),
                    os.path.join(corpus_removed, name))
    for name in _SHARE_TREES[1:] + _SHARE_FILES:
        _move_aside(os.path.join(sialib.SHARE, name),
                    os.path.join(removed_root, "share", name))
    for name in _safe_children(sialib.STATE, "state"):
        _move_aside(os.path.join(sialib.STATE, name),
                    os.path.join(removed_root, "state", name))
    if os.path.isdir(CONFIG_ROOT):
        for name in _safe_children(CONFIG_ROOT, "config"):
            _move_aside(os.path.join(CONFIG_ROOT, name),
                        os.path.join(removed_root, "config", name))


def _install_capsule_content(capsule_path, binding=None):
    fresh = verify(capsule_path)
    if binding is not None:
        for key in ("capsule_id", "classification", "corpus_head",
                    "ledger_head", "public_key", "manifest_sha256"):
            if fresh.get(key) != binding.get(key):
                raise ValueError("capsule changed after restore binding")
    manifest = _read_json(
        os.path.join(capsule_path, MANIFEST_NAME), "install manifest")
    if hashlib.sha256(_canonical_bytes(manifest)).hexdigest() \
            != fresh["manifest_sha256"]:
        raise ValueError("capsule manifest changed before install")
    signed_entries = {row["path"]: row for row in manifest["entries"]}
    copied_entries = []
    payload = os.path.join(capsule_path, PAYLOAD_NAME)
    share_payload = os.path.join(payload, "share")
    corpus_payload = os.path.join(share_payload, "corpus")
    with os.scandir(corpus_payload) as scan:
        corpus_names = sorted(entry.name for entry in scan)
    for name in corpus_names:
        copied_entries.extend(_copy_payload_entry(
            os.path.join(corpus_payload, name),
            os.path.join(sialib.CORPUS, name),
            "share/corpus/" + name, "share"))
    for name in _SHARE_TREES[1:] + _SHARE_FILES:
        source = os.path.join(share_payload, name)
        if os.path.lexists(source):
            copied_entries.extend(_copy_payload_entry(
                source, os.path.join(sialib.SHARE, name),
                "share/" + name, "share"))
    state_payload = os.path.join(payload, "state")
    if os.path.isdir(state_payload):
        with os.scandir(state_payload) as scan:
            state_names = sorted(entry.name for entry in scan)
        for name in state_names:
            copied_entries.extend(_copy_payload_entry(
                os.path.join(state_payload, name),
                os.path.join(sialib.STATE, name),
                "state/" + name, "state"))
    config_payload = os.path.join(payload, "config")
    if os.path.isdir(config_payload):
        os.makedirs(CONFIG_ROOT, mode=0o700, exist_ok=True)
        with os.scandir(config_payload) as scan:
            config_names = sorted(entry.name for entry in scan)
        for name in config_names:
            copied_entries.extend(_copy_payload_entry(
                os.path.join(config_payload, name),
                os.path.join(CONFIG_ROOT, name),
                "config/" + name, "config"))
    for root in (sialib.CORPUS, sialib.SHARE, sialib.STATE, CONFIG_ROOT):
        if os.path.isdir(root):
            _fsync_dir(root)
    preserved_roots = {"share/corpus", "state", "config"}
    expected_installed = {
        path: row for path, row in signed_entries.items()
        if path not in preserved_roots}
    actual_installed = {row["path"]: row for row in copied_entries}
    if len(actual_installed) != len(copied_entries) \
            or actual_installed != expected_installed:
        raise ValueError(
            "installed capsule bytes do not match the signed manifest")
    return fresh


def _set_restored_sync_needed():
    memo_path = os.path.join(sialib.STATE, "memo.json")
    memo = _read_json(memo_path, "restored memo")
    if not isinstance(memo, dict):
        raise ValueError("restored memo is not an object")
    memo["sync_needed"] = True
    sialib.atomic_write(memo_path, json.dumps(
        memo, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n")


def write_adoption_intent(path, *, prepared, confirmation, target):
    transition_basis = {
        "order": time.time_ns(),
        "action": "RESTORE:adopt",
        "arg1": prepared["prepared_id"],
        "arg2": prepared["capsule_id"],
        "content": json.dumps({
            "snapshot_id": prepared["snapshot_id"],
            "manifest_sha256": prepared["manifest_sha256"],
            "target": target,
            "receipt_re_adopted": True,
        }, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
    }
    transition_id = hashlib.sha256(json.dumps(
        transition_basis, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    document = {
        "schema": ADOPTION_SCHEMA,
        "created": _now(),
        "prepared_id": prepared["prepared_id"],
        "snapshot_id": prepared["snapshot_id"],
        "capsule_id": prepared["capsule_id"],
        "manifest_sha256": prepared["manifest_sha256"],
        "confirmation_sha256": hashlib.sha256(
            _canonical_bytes(confirmation)).hexdigest(),
        "target": target,
        "transition": {**transition_basis, "record_id": transition_id},
        "state": "intent",
    }
    private = _private_key()
    public = _public_hex()
    if _derived_public_hex(private) != public:
        raise ValueError("target identity cannot sign restore adoption intent")
    signed = dict(document)
    signed["signer"] = public
    unsigned = dict(signed)
    signed["signature"] = private.sign(_canonical_bytes(unsigned)).hex()
    _write_exclusive(path, _canonical_bytes(signed), 0o600)
    return signed


def _settle_adoption(intent, committed_path):
    transition = intent.get("transition")
    if not isinstance(transition, dict) \
            or set(transition) != {
                "order", "action", "arg1", "arg2", "content", "record_id"}:
        raise ValueError("restore adoption transition is malformed")
    pending = sialib.queue_ledger_transition(
        transition["order"], transition["action"], transition["arg1"],
        transition["arg2"], transition["content"])
    sialib._settle_ledger_transition(pending)
    if not sialib.ledger_contains(
            transition["action"], transition["arg1"], transition["arg2"],
            transition["content"], transition["record_id"]):
        raise RuntimeError("signed restore adoption transition is absent")
    _sequence, head = sialib.ledger_head()
    if re.fullmatch(r"[0-9a-f]{64}", head) is None:
        raise RuntimeError("restore adoption ledger head is unavailable")
    committed = {
        "schema": ADOPTION_SCHEMA,
        "state": "committed",
        "intent_sha256": hashlib.sha256(
            _canonical_bytes(intent)).hexdigest(),
        "record_id": transition["record_id"],
        "ledger_head": head,
        "committed_at": _now(),
    }
    private = _private_key()
    committed["signer"] = _public_hex()
    unsigned = dict(committed)
    committed["signature"] = private.sign(_canonical_bytes(unsigned)).hex()
    _write_exclusive(committed_path, _canonical_bytes(committed), 0o600)
    return committed


def _clear_barrier(journal_path):
    barrier = _read_json(RESTORE_BARRIER, "restore barrier", private=True)
    if not isinstance(barrier, dict) \
            or set(barrier) != {
                "schema", "journal", "prepared_id", "created"} \
            or barrier.get("schema") != JOURNAL_SCHEMA \
            or barrier.get("journal") != os.path.abspath(journal_path):
        raise ValueError("restore barrier does not bind this thaw journal")
    os.unlink(RESTORE_BARRIER)
    _fsync_dir(os.path.dirname(RESTORE_BARRIER))


def _unlink_private_copy(operation_root, relative):
    """Retire a key through pinned, no-follow directory descriptors."""
    parts = relative.split("/")
    if not parts or any(not part or part in {".", ".."}
                        or "/" in part for part in parts):
        raise ValueError("private-key retirement path is unsafe")
    operation_root = _owned_real_dir(
        operation_root, "private-key retirement root")
    directory_flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                       | getattr(os, "O_CLOEXEC", 0)
                       | getattr(os, "O_NOFOLLOW", 0))
    descriptors = []
    try:
        root_fd = os.open(operation_root, directory_flags)
        descriptors.append(root_fd)
        held_root = os.fstat(root_fd)
        current_root = os.lstat(operation_root)
        if not stat.S_ISDIR(held_root.st_mode) \
                or held_root.st_uid != os.geteuid() \
                or _generation(held_root) != _generation(current_root):
            raise ValueError("private-key retirement root changed")
        parent_fd = root_fd
        for component in parts[:-1]:
            try:
                child_fd = os.open(
                    component, directory_flags, dir_fd=parent_fd)
            except FileNotFoundError:
                return False
            child = os.fstat(child_fd)
            if not stat.S_ISDIR(child.st_mode) \
                    or child.st_uid != os.geteuid():
                os.close(child_fd)
                raise ValueError(
                    "private-key retirement directory is unsafe")
            descriptors.append(child_fd)
            parent_fd = child_fd
        leaf = parts[-1]
        try:
            descriptor = os.open(
                leaf, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0), dir_fd=parent_fd)
        except FileNotFoundError:
            return False
        try:
            held = os.fstat(descriptor)
            current = os.stat(
                leaf, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISREG(held.st_mode) \
                    or held.st_uid != os.geteuid() or held.st_nlink != 1 \
                    or stat.S_IMODE(held.st_mode) != 0o600 \
                    or _generation(held) != _generation(current):
                raise ValueError("retained private-key copy is unsafe")
            os.unlink(leaf, dir_fd=parent_fd)
            os.fsync(parent_fd)
            return True
        finally:
            os.close(descriptor)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _retire_operation_keys(operation_root):
    """Unlink every continuity-created private-key copy, durably/idempotently."""
    operation_root = _validate_operation_root(operation_root)
    candidates = [
        "target-key.hex",
        "replaced-live/share/key.hex",
    ]
    directory_flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                       | getattr(os, "O_CLOEXEC", 0)
                       | getattr(os, "O_NOFOLLOW", 0))
    root_fd = os.open(operation_root, directory_flags)
    try:
        held_root = os.fstat(root_fd)
        current_root = os.lstat(operation_root)
        if not stat.S_ISDIR(held_root.st_mode) \
                or held_root.st_uid != os.geteuid() \
                or _generation(held_root) != _generation(current_root):
            raise ValueError("private-key retirement root changed")
        entries = []
        with os.scandir(root_fd) as scan:
            for entry in scan:
                entries.append((entry.name,
                                entry.stat(follow_symlinks=False)))
                if len(entries) > _OPERATION_DIRECTORY_ENTRY_LIMIT:
                    raise ValueError(
                        "rollback operation directory exceeds its entry bound")
    finally:
        os.close(root_fd)
    for name, info in entries:
        if _FAILED_LIVE_NAME.fullmatch(name) is None:
            continue
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() \
                or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("failed-live rollback entry is unsafe")
        candidates.append(name + "/share/key.hex")
    for relative in candidates:
        _unlink_private_copy(operation_root, relative)
    _fsync_dir(operation_root)


def _barrier_journal_path():
    """Return the exact active journal, refusing an unsafe barrier."""
    try:
        barrier = _read_json(
            RESTORE_BARRIER, "restore barrier", private=True)
    except FileNotFoundError:
        return None
    if not isinstance(barrier, dict) \
            or set(barrier) != {
                "schema", "journal", "prepared_id", "created"} \
            or barrier.get("schema") != JOURNAL_SCHEMA \
            or not isinstance(barrier.get("journal"), str) \
            or not os.path.isabs(barrier["journal"]) \
            or not isinstance(barrier.get("prepared_id"), str) \
            or re.fullmatch(r"[0-9a-f]{32}",
                            barrier["prepared_id"]) is None \
            or not isinstance(barrier.get("created"), str) \
            or not barrier["created"]:
        raise ValueError("restore barrier schema is invalid")
    journal_path = os.path.abspath(barrier["journal"])
    if os.path.realpath(journal_path) != journal_path:
        raise ValueError("restore barrier journal path is unsafe")
    return journal_path


def _validate_rollback_root(rollback_root):
    rollback_root = os.path.abspath(rollback_root)
    root = _owned_real_dir(rollback_root, "rollback root")
    info = os.lstat(root)
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("rollback root is not owner-private")
    return root


def _validate_operation_root(operation_root, rollback_root=None):
    operation_root = os.path.abspath(operation_root)
    if os.path.realpath(operation_root) != operation_root \
            or _OPERATION_NAME.fullmatch(
                os.path.basename(operation_root)) is None:
        raise ValueError("rollback operation path is unsafe")
    parent = _validate_rollback_root(os.path.dirname(operation_root))
    if rollback_root is not None \
            and parent != _validate_rollback_root(rollback_root):
        raise ValueError("rollback operation is outside its rollback root")
    info = os.lstat(operation_root)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() \
            or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("rollback operation root is unsafe")
    return operation_root


def _validate_target_record(target):
    if not isinstance(target, dict) \
            or set(target) != {
                "corpus_root", "receipt_sha256", "receipt_mode"} \
            or not isinstance(target.get("corpus_root"), dict) \
            or set(target["corpus_root"]) != {
                "device", "inode", "mode", "owner"} \
            or any(type(target["corpus_root"].get(key)) is not int
                   for key in ("device", "inode", "mode", "owner")) \
            or re.fullmatch(
                r"[0-9a-f]{64}", target.get("receipt_sha256", "")) is None \
            or type(target.get("receipt_mode")) is not int:
        raise ValueError("thaw journal target binding is invalid")


def _valid_gbrain_journal(journal, operation_root):
    sidecars = journal.get("projection_sidecars")
    return journal.get("projection_path") == os.path.join(
        operation_root, "target-brain.pglite") \
        and journal.get("projection_stage_home") == os.path.join(
            operation_root, "new-gbrain-home") \
        and isinstance(journal.get("native_lock_token"), str) \
        and re.fullmatch(
            r"[0-9a-f]{32}", journal["native_lock_token"]) is not None \
        and _valid_root_identity(journal.get("gbrain_root")) \
        and _valid_generation_record(journal.get("gbrain_config")) \
        and _valid_generation_record(journal.get("schema_pack")) \
        and _valid_generation_record(journal.get("schema_receipt")) \
        and _valid_root_identity(journal.get("projection")) \
        and isinstance(sidecars, dict) \
        and set(sidecars) == set(_GBRAIN_PROJECTION_SIDECARS) \
        and all(value is None or _valid_sidecar_record(value)
                for value in sidecars.values())


def _load_thaw_journal(journal_path, rollback_root=None):
    journal_path = os.path.abspath(journal_path)
    operation_root = os.path.dirname(journal_path)
    _validate_operation_root(operation_root, rollback_root)
    if journal_path != os.path.join(operation_root, "journal.json"):
        raise ValueError("thaw journal name is invalid")
    journal = _read_json(journal_path, "thaw journal", private=True)
    required = {"schema", "created", "prepared_id", "snapshot_id",
                "rollback_capsule", "target", "target_key_present",
                "target_key_path", "projection_path",
                "projection_stage_home", "native_lock_token",
                "gbrain_root", "gbrain_config", "schema_pack",
                "schema_receipt", "projection",
                "projection_sidecars", "adoption_intent",
                "adoption_committed", "phase"}
    operation_name = os.path.basename(operation_root)
    if not isinstance(journal, dict) or set(journal) != required \
            or journal.get("schema") != JOURNAL_SCHEMA \
            or journal.get("phase") not in _THAW_PHASES \
            or not isinstance(journal.get("created"), str) \
            or not journal["created"] \
            or not isinstance(journal.get("snapshot_id"), str) \
            or not journal["snapshot_id"] \
            or not isinstance(journal.get("prepared_id"), str) \
            or re.fullmatch(
                r"[0-9a-f]{32}", journal["prepared_id"]) is None \
            or not operation_name.startswith(journal["prepared_id"] + "-") \
            or journal.get("rollback_capsule") != os.path.join(
                operation_root, "target-capsule") \
            or journal.get("target_key_path") != os.path.join(
                operation_root, "target-key.hex") \
            or not _valid_gbrain_journal(journal, operation_root) \
            or journal.get("adoption_intent") != os.path.join(
                operation_root, "adoption.json") \
            or journal.get("adoption_committed") != os.path.join(
                operation_root, "adoption-committed.json") \
            or not isinstance(journal.get("target_key_present"), bool):
        raise ValueError("thaw journal is not recoverable")
    _validate_target_record(journal["target"])
    return journal, operation_root


def _catalog_operation_tree(operation_root):
    """Preflight one private tree without following a link or deleting bytes."""
    operation_root = _validate_operation_root(operation_root)
    directory_flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                       | getattr(os, "O_CLOEXEC", 0)
                       | getattr(os, "O_NOFOLLOW", 0))
    root_fd = os.open(operation_root, directory_flags)
    records = []
    seen_records = 0

    def walk(directory_fd, parts):
        nonlocal seen_records
        entries = []
        with os.scandir(directory_fd) as scan:
            for entry in scan:
                entries.append(entry)
                if len(entries) > _OPERATION_DIRECTORY_ENTRY_LIMIT:
                    raise ValueError(
                        "rollback cleanup directory exceeds its entry bound")
        entries.sort(key=lambda entry: entry.name)
        for entry in entries:
            name = entry.name
            if not name or name in {".", ".."} or "/" in name \
                    or "\0" in name:
                raise ValueError("rollback cleanup entry name is unsafe")
            child_parts = parts + (name,)
            relative = "/".join(child_parts)
            if len(child_parts) > _OPERATION_TREE_DEPTH_LIMIT:
                raise ValueError("rollback cleanup tree exceeds its depth bound")
            seen_records += 1
            if seen_records > _OPERATION_TREE_RECORD_LIMIT:
                raise ValueError(
                    "rollback cleanup tree exceeds its record bound")
            if len(relative) > sialib.MAX_CONFIG_PATH_CHARS:
                raise ValueError("rollback cleanup path exceeds its bound")
            observed = entry.stat(follow_symlinks=False)
            if observed.st_uid != os.geteuid():
                raise ValueError("rollback cleanup entry has a foreign owner")
            if stat.S_ISDIR(observed.st_mode):
                child_fd = os.open(name, directory_flags,
                                   dir_fd=directory_fd)
                try:
                    held = os.fstat(child_fd)
                    current = os.stat(
                        name, dir_fd=directory_fd, follow_symlinks=False)
                    if not stat.S_ISDIR(held.st_mode) \
                            or _generation(held) != _generation(observed) \
                            or _generation(current) != _generation(observed):
                        raise ValueError(
                            "rollback cleanup directory changed during scan")
                    walk(child_fd, child_parts)
                    records.append({
                        "parts": child_parts,
                        "kind": "directory",
                        "device": held.st_dev,
                        "inode": held.st_ino,
                        "mode": stat.S_IMODE(held.st_mode),
                    })
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
                raise ValueError(
                    "rollback cleanup tree contains a link or special file")
            flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                     | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_NONBLOCK", 0))
            file_fd = os.open(name, flags, dir_fd=directory_fd)
            try:
                held = os.fstat(file_fd)
                current = os.stat(
                    name, dir_fd=directory_fd, follow_symlinks=False)
                if _generation(held) != _generation(observed) \
                        or _generation(current) != _generation(observed):
                    raise ValueError(
                        "rollback cleanup file changed during scan")
                if name in {"key.hex", "target-key.hex"} \
                        and stat.S_IMODE(held.st_mode) != 0o600:
                    raise ValueError(
                        "rollback cleanup private-key copy is unsafe")
                records.append({
                    "parts": child_parts,
                    "kind": "file",
                    "generation": _generation(held),
                })
            finally:
                os.close(file_fd)

    try:
        held_root = os.fstat(root_fd)
        current_root = os.lstat(operation_root)
        if not stat.S_ISDIR(held_root.st_mode) \
                or held_root.st_uid != os.geteuid() \
                or _generation(held_root) != _generation(current_root):
            raise ValueError("rollback operation root changed during scan")
        walk(root_fd, ())
        return {
            "root": operation_root,
            "device": held_root.st_dev,
            "inode": held_root.st_ino,
            "mode": stat.S_IMODE(held_root.st_mode),
            "records": records,
        }
    finally:
        os.close(root_fd)


def _operation_cleanup_classification(catalog):
    operation_root = catalog["root"]
    top = {record["parts"][0] for record in catalog["records"]}
    journal_path = os.path.join(operation_root, "journal.json")
    journal = None
    if "journal.json" in top:
        journal_record = next(
            record for record in catalog["records"]
            if record["parts"] == ("journal.json",))
        if journal_record["kind"] != "file":
            raise ValueError("thaw journal is not a regular file")
        journal, _operation = _load_thaw_journal(journal_path)
        if _generation(os.lstat(journal_path)) != \
                journal_record["generation"]:
            raise ValueError("thaw journal changed after cleanup preflight")
    prebarrier_allowed = {"target-capsule", "journal.json", "adoption.json"}
    completed_allowed = {
        "target-capsule", "journal.json", "adoption.json",
        "adoption-committed.json", "target-key.hex",
        "target-brain.pglite", "new-gbrain-home", "replaced-live",
    }
    completed_allowed.update(
        "target-" + name for name in _GBRAIN_PROJECTION_SIDECARS)
    for name in top:
        if _JOURNAL_STAGE_NAME.fullmatch(name) is not None:
            continue
        if journal is None or journal["phase"] == "barrier":
            if name not in prebarrier_allowed:
                raise ValueError(
                    "pre-barrier rollback operation has ambiguous content")
            continue
        if journal["phase"] not in _INACTIVE_COMPLETE_PHASES:
            raise ValueError(
                "inactive rollback operation has an unfinished phase")
        if name not in completed_allowed \
                and _FAILED_LIVE_NAME.fullmatch(name) is None:
            raise ValueError(
                "completed rollback operation has ambiguous content")
    if journal is None:
        return "pre-barrier"
    return journal["phase"]


def _delete_operation_catalog(catalog):
    """Delete a fully preflighted operation, keeping its journal until last."""
    operation_root = catalog["root"]
    active_journal = _barrier_journal_path()
    if active_journal is not None \
            and os.path.dirname(active_journal) == operation_root:
        raise RuntimeError("active rollback operation cannot be retired")
    parent = _validate_rollback_root(os.path.dirname(operation_root))
    directory_flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                       | getattr(os, "O_CLOEXEC", 0)
                       | getattr(os, "O_NOFOLLOW", 0))
    parent_fd = os.open(parent, directory_flags)
    root_fd = -1
    directory_records = {
        record["parts"]: record for record in catalog["records"]
        if record["kind"] == "directory"
    }

    def open_parent(parts):
        descriptor = os.dup(root_fd)
        try:
            for index, component in enumerate(parts[:-1]):
                child = os.open(
                    component, directory_flags, dir_fd=descriptor)
                expected = directory_records[parts[:index + 1]]
                held = os.fstat(child)
                if not stat.S_ISDIR(held.st_mode) \
                        or held.st_uid != os.geteuid() \
                        or (held.st_dev, held.st_ino,
                            stat.S_IMODE(held.st_mode)) != (
                                expected["device"], expected["inode"],
                                expected["mode"]):
                    os.close(child)
                    raise ValueError(
                        "rollback cleanup directory identity changed")
                os.close(descriptor)
                descriptor = child
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    try:
        root_fd = os.open(
            os.path.basename(operation_root), directory_flags,
            dir_fd=parent_fd)
        held_root = os.fstat(root_fd)
        if not stat.S_ISDIR(held_root.st_mode) \
                or held_root.st_uid != os.geteuid() \
                or (held_root.st_dev, held_root.st_ino,
                    stat.S_IMODE(held_root.st_mode)) != (
                        catalog["device"], catalog["inode"], catalog["mode"]):
            raise ValueError("rollback operation identity changed")

        def cleanup_order(record):
            parts = record["parts"]
            name = parts[-1]
            if name in {"key.hex", "target-key.hex"}:
                return (0, -len(parts), "/".join(parts))
            if parts == ("journal.json",):
                return (2, 0, "journal.json")
            return (1, -len(parts), "/".join(parts))

        for record in sorted(catalog["records"], key=cleanup_order):
            parts = record["parts"]
            descriptor = open_parent(parts)
            try:
                leaf = parts[-1]
                if record["kind"] == "file":
                    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                             | getattr(os, "O_NOFOLLOW", 0)
                             | getattr(os, "O_NONBLOCK", 0))
                    file_fd = os.open(leaf, flags, dir_fd=descriptor)
                    try:
                        held = os.fstat(file_fd)
                        current = os.stat(
                            leaf, dir_fd=descriptor, follow_symlinks=False)
                        if _generation(held) != record["generation"] \
                                or _generation(current) != \
                                   record["generation"]:
                            raise ValueError(
                                "rollback cleanup file identity changed")
                        os.unlink(leaf, dir_fd=descriptor)
                    finally:
                        os.close(file_fd)
                else:
                    current = os.stat(
                        leaf, dir_fd=descriptor, follow_symlinks=False)
                    if not stat.S_ISDIR(current.st_mode) \
                            or current.st_uid != os.geteuid() \
                            or (current.st_dev, current.st_ino,
                                stat.S_IMODE(current.st_mode)) != (
                                    record["device"], record["inode"],
                                    record["mode"]):
                        raise ValueError(
                            "rollback cleanup directory identity changed")
                    os.rmdir(leaf, dir_fd=descriptor)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        current_root = os.stat(
            os.path.basename(operation_root), dir_fd=parent_fd,
            follow_symlinks=False)
        if not stat.S_ISDIR(current_root.st_mode) \
                or (current_root.st_dev, current_root.st_ino) != (
                    catalog["device"], catalog["inode"]):
            raise ValueError("rollback operation root changed before retirement")
        os.rmdir(os.path.basename(operation_root), dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        if root_fd >= 0:
            os.close(root_fd)
        os.close(parent_fd)


def _retire_inactive_operation(operation_root):
    catalog = _catalog_operation_tree(operation_root)
    _operation_cleanup_classification(catalog)
    _delete_operation_catalog(catalog)


def _reconcile_rollback_operations(rollback_root, *, active_operation=None):
    """Retire only strict pre-barrier or completed inactive operations."""
    rollback_root = _validate_rollback_root(rollback_root)
    active = None if active_operation is None else os.path.abspath(
        active_operation)
    if active is not None:
        if os.path.dirname(active) != rollback_root \
                or _OPERATION_NAME.fullmatch(os.path.basename(active)) is None:
            raise ValueError("active rollback operation path is unsafe")
    entries = []
    with os.scandir(rollback_root) as scan:
        for entry in scan:
            entries.append(entry)
            if len(entries) > _OPERATION_DIRECTORY_ENTRY_LIMIT:
                raise ValueError("rollback root exceeds its operation bound")
    entries.sort(key=lambda entry: entry.name)
    catalogs = []
    for entry in entries:
        candidate = os.path.join(rollback_root, entry.name)
        if candidate == active:
            # Do not stat, open, catalog, or otherwise inspect the exact tree
            # bound by the active durable barrier.
            continue
        info = entry.stat(follow_symlinks=False)
        if _OPERATION_NAME.fullmatch(entry.name) is None \
                or not stat.S_ISDIR(info.st_mode) \
                or info.st_uid != os.geteuid() \
                or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("rollback root contains an ambiguous operation")
        catalog = _catalog_operation_tree(candidate)
        _operation_cleanup_classification(catalog)
        catalogs.append(catalog)
    for catalog in catalogs:
        _delete_operation_catalog(catalog)
    _fsync_dir(rollback_root)


def _install_private_hex(private_hex):
    if not isinstance(private_hex, str) \
            or re.fullmatch(r"[0-9a-f]{64}", private_hex) is None:
        raise ValueError("restore private identity is malformed")
    private = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex))
    expected_public = _derived_public_hex(private)
    current_public = _public_hex()
    if expected_public != current_public:
        raise ValueError("restore private identity does not match restored public key")
    _write_exclusive(LEDGER_KEY, (private_hex + "\n").encode("ascii"), 0o600)


def _prepared_binding(prepared):
    if not isinstance(prepared, dict) \
            or prepared.get("schema") != PREPARED_SCHEMA \
            or not isinstance(prepared.get("prepared_id"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", prepared["prepared_id"]) is None \
            or not isinstance(prepared.get("snapshot_id"), str) \
            or not prepared["snapshot_id"] \
            or len(prepared["snapshot_id"].encode("utf-8", "strict")) \
               > MAX_DOCUMENT_BYTES \
            or any(marker in prepared["snapshot_id"]
                   for marker in ("\0", "\n", "\r")) \
            or not isinstance(prepared.get("capsule_path"), str) \
            or not os.path.isabs(prepared["capsule_path"]):
        raise ValueError("prepared restore receipt is malformed")
    verified = verify(prepared["capsule_path"])
    for key in ("capsule_id", "classification", "corpus_head",
                "ledger_head", "public_key", "manifest_sha256"):
        if prepared.get(key) != verified.get(key):
            raise ValueError("prepared restore receipt does not bind its capsule")
    return verified


def _restore_health():
    ready, reason = sialib.memory_readiness()
    if not ready:
        raise RuntimeError("restored SIA did not become ready: " + str(reason))
    if not _verify_live_sia_ledger():
        raise RuntimeError("restored SIA signed ledger verification failed")
    return {"ready": True, "sia_ledger_verified": True,
            "readiness_reason": str(reason)}


def _health_observation():
    try:
        ready, reason = sialib.memory_readiness()
    except Exception as exc:
        ready, reason = False, str(exc)
    try:
        sia_ledger_verified = _verify_live_sia_ledger()
    except Exception:
        sia_ledger_verified = False
    return {"ready": bool(ready),
            "sia_ledger_verified": bool(sia_ledger_verified),
            "readiness_reason": str(reason)}


def _verify_live_sia_ledger():
    result = sialib._run_bounded_text_process(
        [os.path.join(sialib.BIN, "sia-ledger"), "verify", sialib.SHARE,
         "--quiet"], env=None, timeout=sialib.JOURNAL_TIMEOUT_SECONDS,
        cwd=None, label="restored SIA ledger verifier",
        output_limit=sialib.MAX_CONFIG_BYTES)
    return result.returncode == 0


def _native_first_light(*, full_sync=True):
    """Run the ordinary brain heartbeat inside the worker's owner contexts."""
    if full_sync is not True:
        raise ValueError("restore first light requires a full sync")
    memo = sialib.load_memo()
    if not isinstance(memo, dict):
        raise ValueError("restored memo is not an object")
    sequence = memo.get("pulse_seq", 0)
    if isinstance(sequence, bool) or not isinstance(sequence, int) \
            or sequence < 0:
        raise ValueError("restored pulse sequence is invalid")
    memo["pulse_seq"] = sequence + 1
    memo["sync_needed"] = True
    sialib._write_memo(memo)
    result = sialib._pulse_transaction(memo["pulse_seq"])
    if not isinstance(result, dict):
        raise RuntimeError("restore first light did not publish status")
    return result


def _finish_operation_retirement(journal_path, journal, *, rolled_back,
                                 health):
    """Publish the settled outcome, clear its barrier, then retire the tree."""
    operation_root = os.path.dirname(os.path.abspath(journal_path))
    _retire_operation_keys(operation_root)
    retiring_phase = "retiring-rollback" if rolled_back \
        else "retiring-commit"
    if journal.get("phase") != retiring_phase:
        journal["phase"] = retiring_phase
        _atomic_json(journal_path, journal)
    # Preflight every byte while the durable barrier still prevents ordinary
    # SIA entry.  Once the barrier is durably unlinked, a crash can leave only
    # this terminal journal and a safe subset of the same catalog; the next
    # thaw will resume retirement with the journal deleted last.
    catalog = _catalog_operation_tree(operation_root)
    if _operation_cleanup_classification(catalog) != retiring_phase:
        raise ValueError("rollback retirement phase changed during cleanup")
    _clear_barrier(journal_path)
    _delete_operation_catalog(catalog)
    return {"rolled_back": bool(rolled_back), **health}


def rollback_restore(journal_path, *, capability):
    """Recover a failed/interrupted thaw from its complete target capsule."""
    validate_restore_capability(capability)
    journal_path = os.path.abspath(journal_path)
    journal, operation_root = _load_thaw_journal(journal_path)
    target_before = journal["target"]
    if target_identity() != target_before:
        raise ValueError("target corpus root or receipt changed during thaw")
    if journal["phase"] in {
            "rolled-back", "committed",
            "retiring-rollback", "retiring-commit"}:
        rollback_outcome = journal["phase"] in {
            "rolled-back", "retiring-rollback"}
        return _finish_operation_retirement(
            journal_path, journal, rolled_back=rollback_outcome,
            health=_health_observation())
    if journal["phase"] in {"cleaning-rollback", "cleaning-commit"}:
        rollback_outcome = journal["phase"] == "cleaning-rollback"
        health = (_health_observation() if rollback_outcome
                  else _restore_health())
        return _finish_operation_retirement(
            journal_path, journal, rolled_back=rollback_outcome,
            health=health)
    if journal["phase"] == "barrier":
        # The barrier is durable before the first live mutation.  A crash in
        # this phase can leave only operation-local projection material, an
        # incomplete/full private-key duplicate, or SIA's exact native-lock
        # intent. Rewriting the coherent live generation would expand risk.
        _prepare_live_projection_for_native_lock(journal)
        _refresh_barrier_gbrain_binding(journal, journal_path)
        _gbrain_substrate_binding(journal)
        rollback_binding = verify(journal["rollback_capsule"])
        if journal["target_key_present"]:
            if not identity_matches(rollback_binding):
                raise ValueError(
                    "pre-mutation target identity changed during thaw")
        elif os.path.lexists(LEDGER_KEY):
            raise ValueError(
                "pre-mutation target identity appeared during thaw")
        _unlink_private_copy(operation_root, "target-key.hex")
        if target_identity() != target_before:
            raise ValueError("pre-mutation target root or receipt changed")
        health = _health_observation()
        journal["phase"] = "cleaning-rollback"
        _atomic_json(journal_path, journal)
        return _finish_operation_retirement(
            journal_path, journal, rolled_back=True, health=health)
    journal["phase"] = "rolling-back"
    _atomic_json(journal_path, journal)
    failed_root = os.path.join(operation_root, "failed-live-" + uuid.uuid4().hex)
    os.mkdir(failed_root, 0o700)
    with _freeze_locks():
        rollback_binding = verify(journal["rollback_capsule"])
        _clear_live_portable(failed_root)
        _install_capsule_content(
            journal["rollback_capsule"], binding=rollback_binding)

        _restore_target_gbrain(journal, failed_root)

        saved_target_key = os.path.lexists(journal["target_key_path"])
        if saved_target_key:
            if os.path.lexists(LEDGER_KEY):
                _move_aside(LEDGER_KEY,
                            os.path.join(failed_root, "share", "key.hex"))
            target_key, _info = _read_regular(
                journal["target_key_path"], "rollback private identity",
                private=True)
            if _HEX_KEY.fullmatch(target_key) is None:
                raise ValueError("rollback private identity is malformed")
            _write_exclusive(LEDGER_KEY, target_key, 0o600)
        elif journal["target_key_present"]:
            if not identity_matches(rollback_binding):
                raise ValueError("rollback private identity copy is missing")
        elif os.path.lexists(LEDGER_KEY):
            _move_aside(LEDGER_KEY,
                        os.path.join(failed_root, "share", "key.hex"))
        if target_identity() != target_before:
            raise ValueError("rollback changed the target root or receipt")
    health = _health_observation()
    journal["phase"] = "cleaning-rollback"
    _atomic_json(journal_path, journal)
    return _finish_operation_retirement(
        journal_path, journal, rolled_back=True, health=health)


def recover_barrier(*, capability):
    """Resolve the one durable power-loss barrier under restore authority."""
    validate_restore_capability(capability)
    journal_path = _barrier_journal_path()
    if journal_path is None:
        raise FileNotFoundError("restore barrier is absent")
    journal, operation_root = _load_thaw_journal(journal_path)
    if journal["prepared_id"] != _read_json(
            RESTORE_BARRIER, "restore barrier", private=True)["prepared_id"]:
        raise ValueError("restore barrier prepared identity changed")
    rollback_root = os.path.dirname(operation_root)
    _reconcile_rollback_operations(
        rollback_root, active_operation=operation_root)
    return rollback_restore(journal_path, capability=capability)


def _prepare_rollback_operation(operation_root, prepared, current_head,
                                target_before):
    """Build the complete pre-mutation rollback material for one thaw."""
    rollback_capsule = os.path.join(operation_root, "target-capsule")
    rollback_result = freeze(rollback_capsule)
    if rollback_result["ledger_head"] != current_head \
            or target_identity() != target_before:
        raise RuntimeError(
            "target changed while its rollback capsule was frozen")

    target_key_path = os.path.join(operation_root, "target-key.hex")
    target_key_present = os.path.exists(LEDGER_KEY)
    target_key = None
    if target_key_present:
        target_key, _info = _read_regular(
            LEDGER_KEY, "target private identity", private=True)
        if _HEX_KEY.fullmatch(target_key) is None:
            raise ValueError("target private identity is malformed")

    _probe_live_projection_quiescent()
    gbrain = _gbrain_substrate_binding()

    journal = {
        "schema": JOURNAL_SCHEMA,
        "created": _now(),
        "prepared_id": prepared["prepared_id"],
        "snapshot_id": prepared["snapshot_id"],
        "rollback_capsule": rollback_capsule,
        "target": target_before,
        "target_key_present": target_key_present,
        "target_key_path": target_key_path,
        "projection_path": os.path.join(
            operation_root, "target-brain.pglite"),
        "projection_stage_home": os.path.join(
            operation_root, "new-gbrain-home"),
        "native_lock_token": uuid.uuid4().hex,
        **gbrain,
        "adoption_intent": os.path.join(operation_root, "adoption.json"),
        "adoption_committed": os.path.join(
            operation_root, "adoption-committed.json"),
        "phase": "barrier",
    }
    return journal, target_key


def _gbrain_live_paths():
    root = os.path.join(sialib.SHARE, ".gbrain")
    projection = os.path.join(root, _GBRAIN_PROJECTION_NAME)
    pack = os.path.join(
        root, "schema-packs", _GBRAIN_SCHEMA_PACK_NAME, "pack.yaml")
    return root, projection, os.path.join(root, "config.json"), pack


def _gbrain_sidecar_record(path):
    size, digest, info = _hash_regular(
        path, "gbrain projection sidecar")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise ValueError(
            "gbrain projection sidecar is writable by another user")
    return {
        "generation": _generation_record(info),
        "content": {
            "mode": stat.S_IMODE(info.st_mode),
            "owner": info.st_uid,
            "links": info.st_nlink,
            "size": size,
            "sha256": digest,
        },
    }


def _gbrain_substrate_binding(expected=None, *, projection_required=True,
                              stable_sidecars=False):
    """Authenticate the installed runtime substrate without walking it."""
    root, projection, config_path, pack_path = _gbrain_live_paths()
    _owned_real_dir(root, "target gbrain root")
    _owned_real_dir(os.path.dirname(pack_path), "target gbrain schema pack")
    if projection_required:
        _owned_real_dir(projection, "target gbrain projection")

    config_raw, config_info = _read_regular(
        config_path, "target gbrain config", private=True)
    config = _strict_json(config_raw, "target gbrain config")
    if not isinstance(config, dict) \
            or config.get("engine") != "pglite" \
            or config.get("database_path") != projection \
            or config.get("schema_pack") != _GBRAIN_SCHEMA_PACK_NAME:
        raise ValueError("target gbrain config is not SIA's PGLite substrate")

    disabled = config.get("embedding_disabled") is True
    model = config.get("embedding_model")
    dimensions = config.get("embedding_dimensions")
    if not disabled and (not isinstance(model, str) or not model \
            or isinstance(dimensions, bool) \
            or not isinstance(dimensions, int) or dimensions <= 0):
        raise ValueError("target gbrain embedding profile is incomplete")

    _pack_size, pack_digest, pack_info = _hash_regular(
        pack_path, "managed SIA schema pack")
    if stat.S_IMODE(pack_info.st_mode) & 0o022:
        raise ValueError("managed SIA schema pack is writable by another user")
    managed_root = os.path.abspath(MANAGED_ROOT)
    receipt_path = os.path.abspath(SCHEMA_PACK_RECEIPT)
    if os.path.dirname(receipt_path) != managed_root:
        raise ValueError("managed schema-pack receipt path is not exact")
    _owned_real_dir(managed_root, "managed install receipts")
    receipt_raw, receipt_info = _read_regular(
        receipt_path, "managed schema-pack receipt")
    if stat.S_IMODE(receipt_info.st_mode) & 0o022:
        raise ValueError("managed schema-pack receipt is writable by another user")
    receipt_expected = (
        "managed-by=khephri.sia\nkind=schema-pack\npath=" + pack_path
        + "\nsha256=" + pack_digest + "\n").encode("utf-8")
    if receipt_raw != receipt_expected:
        raise ValueError("managed schema-pack receipt does not bind its pack")

    binding = {
        "gbrain_root": _root_identity(os.lstat(root)),
        "gbrain_config": _generation_record(config_info),
        "schema_pack": _generation_record(pack_info),
        "schema_receipt": _generation_record(receipt_info),
    }
    if projection_required:
        sidecars = {}
        for name in _GBRAIN_PROJECTION_SIDECARS:
            path = os.path.join(root, name)
            if not os.path.lexists(path):
                sidecars[name] = None
                continue
            sidecars[name] = _gbrain_sidecar_record(path)
        binding.update({
            "projection": _root_identity(os.lstat(projection)),
            "projection_sidecars": sidecars,
        })
    if expected is not None:
        for key, value in binding.items():
            if key == "projection_sidecars" and stable_sidecars:
                mismatch = set(value) != set(expected.get(key, {})) \
                    or any(
                        (value[name] is None) !=
                        (expected[key][name] is None)
                        or (value[name] is not None and
                            value[name]["content"] !=
                            expected[key][name]["content"])
                        for name in value)
            else:
                mismatch = expected.get(key) != value
            if mismatch:
                raise ValueError("target gbrain substrate changed during restore")
    return binding


def _refresh_barrier_gbrain_binding(journal, journal_path):
    """Bind native-probe side effects before SIA's first live mutation."""
    if journal.get("phase") != "barrier":
        raise ValueError("gbrain barrier binding refresh is out of phase")
    current = _gbrain_substrate_binding()
    for key in (
            "gbrain_root", "gbrain_config", "schema_pack",
            "schema_receipt", "projection"):
        if current[key] != journal[key]:
            raise ValueError(
                "target gbrain substrate changed before restore mutation")
    if current["projection_sidecars"] != journal["projection_sidecars"]:
        journal["projection_sidecars"] = current["projection_sidecars"]
        _atomic_json(journal_path, journal)
    return current


def _gbrain_environment(home):
    environment = dict(sialib.GBRAIN_ENV)
    for name in (
            "GBRAIN_DATABASE_URL", "DATABASE_URL", "GBRAIN_BRAIN_ID",
            "GBRAIN_SOURCE", "GBRAIN_SCHEMA_PACK",
            "GBRAIN_EMBEDDING_MODEL", "GBRAIN_EMBEDDING_DIMENSIONS"):
        environment.pop(name, None)
    environment.update({
        "GBRAIN_HOME": home,
        "GBRAIN_SKIP_STARTUP_HOOKS": "1",
        "GBRAIN_SELF_UPGRADE_MODE": "off",
        "GBRAIN_NO_BANNER": "1",
        "GBRAIN_NO_ONBOARD_NUDGE": "1",
        "GBRAIN_NO_MODE_SWITCH_UX": "1",
        "GBRAIN_NO_SKILL_NAG": "1",
    })
    return environment


def _run_gbrain(args, *, home, label):
    result = sialib._run_bounded_text_process(
        [sialib.GBRAIN, *args], env=_gbrain_environment(home),
        timeout=sialib.JOURNAL_TIMEOUT_SECONDS, cwd=sialib.CORPUS,
        label=label, output_limit=sialib.MAX_GBRAIN_OUTPUT_BYTES)
    if result.returncode != 0:
        raise RuntimeError(label + " failed")
    return result


def _contains_native_lock_note(value):
    if isinstance(value, str):
        return "locked_by_" in value
    if isinstance(value, list):
        return any(_contains_native_lock_note(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_native_lock_note(item)
                   for item in value.values())
    return False


def _probe_projection(home, expected_path, label):
    result = _run_gbrain(
        ["engine", "status", "--probe", "--json"],
        home=home, label=label)
    report = _strict_json(result.stdout.encode("utf-8"), label)
    if not isinstance(report, dict) \
            or report.get("schema_version") != 1 \
            or report.get("effective_engine") != "pglite" \
            or report.get("config_file_engine") != "pglite" \
            or report.get("database_path") != expected_path \
            or report.get("thin_client") is not False \
            or not isinstance(report.get("probe"), dict) \
            or report["probe"].get("ok") is not True \
            or _contains_native_lock_note(report):
        raise RuntimeError(label + " did not prove a quiescent PGLite store")
    if os.path.lexists(os.path.join(expected_path, ".gbrain-lock")):
        raise RuntimeError(label + " left an ambiguous native PGLite holder")
    return report


def _probe_live_projection_quiescent():
    _root, projection, _config, _pack = _gbrain_live_paths()
    return _probe_projection(
        sialib.SHARE, projection, "target gbrain quiescence probe")


def _native_lock_record(token):
    try:
        pid_namespace = os.readlink("/proc/self/ns/pid")
    except OSError:
        pid_namespace = None
    try:
        with open("/proc/sys/kernel/random/boot_id", encoding="ascii") \
                as stream:
            boot_id = stream.read().strip() or None
    except OSError:
        boot_id = None
    observed = time.time_ns() // 1000000
    return {
        "pid": os.getpid(),
        "acquired_at": observed,
        "refreshed_at": observed,
        "command": "python3 sia restore projection",
        "subcommand": "restore",
        "pid_ns": pid_namespace,
        "boot_id": boot_id,
        "sia_restore_token": token,
    }


def _native_claim_record(token):
    return {
        "pid": os.getpid(),
        "at": time.time_ns() // 1000000,
        "sia_restore_token": token,
    }


def _valid_native_lock_record(record, token):
    return isinstance(record, dict) \
        and set(record) == {
            "pid", "acquired_at", "refreshed_at", "command",
            "subcommand", "pid_ns", "boot_id", "sia_restore_token"} \
        and record.get("sia_restore_token") == token \
        and type(record.get("pid")) is int \
        and type(record.get("acquired_at")) is int \
        and type(record.get("refreshed_at")) is int \
        and record.get("command") == "python3 sia restore projection" \
        and record.get("subcommand") == "restore" \
        and (record.get("pid_ns") is None
             or isinstance(record.get("pid_ns"), str)) \
        and (record.get("boot_id") is None
             or isinstance(record.get("boot_id"), str))


def _valid_native_claim_record(record, token):
    return isinstance(record, dict) \
        and set(record) == {"pid", "at", "sia_restore_token"} \
        and record.get("sia_restore_token") == token \
        and type(record.get("pid")) is int \
        and type(record.get("at")) is int


def _native_pid_alive(pid):
    """Match gbrain's conservative process-existence decision."""
    if type(pid) is not int or pid <= 0:
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True


def _native_lock_authority(projection, token):
    """Classify only the token namespace; native records remain gbrain's."""
    projection = _owned_real_dir(projection, "target gbrain projection")
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
             | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    projection_fd = os.open(projection, flags)
    lock_fd = -1
    try:
        if not _entry_exists_at(projection_fd, ".gbrain-lock"):
            return "absent"
        lock_fd = _open_owned_dir_at(
            projection_fd, ".gbrain-lock", "native PGLite lock")
        names = _directory_names(lock_fd)
        allowed = ["lock"]
        rebind = ".sia-rebind-" + token
        if names == sorted(["lock", rebind]):
            allowed.append(rebind)
        if names != sorted(allowed):
            return "native"
        raw, _info = _read_regular_at(
            lock_fd, "lock", "native PGLite lock record")
        try:
            record = _strict_json(raw, "native PGLite lock record")
        except ValueError:
            return "native"
        claimed = record.get("sia_restore_token") \
            if isinstance(record, dict) else None
        if claimed is None:
            return "native"
        if claimed != token:
            raise ValueError(
                "native PGLite lock belongs to another restore journal")
        if not _valid_native_lock_record(record, token):
            raise ValueError("SIA native PGLite lock record is malformed")
        if not _linked_dir_matches(
                projection_fd, ".gbrain-lock", lock_fd):
            raise ValueError("native PGLite lock changed while classified")
        return "sia"
    finally:
        if lock_fd >= 0:
            os.close(lock_fd)
        os.close(projection_fd)


def _native_claim_state(directory_fd, token):
    """Classify a held reap claim using pinned gbrain's stale rules."""
    info = os.fstat(directory_fd)
    names = _directory_names(directory_fd)
    record = None
    if names == ["lock"]:
        raw, _record_info = _read_regular_at(
            directory_fd, "lock", "native PGLite reap claim record")
        try:
            record = _strict_json(
                raw, "native PGLite reap claim record")
        except ValueError:
            record = None
        if _valid_native_claim_record(record, token):
            return "sia"
        claimed = record.get("sia_restore_token") \
            if isinstance(record, dict) else None
        if claimed is not None:
            raise ValueError(
                "native PGLite reap claim belongs to another restore journal")
        if isinstance(record, dict) and set(record) == {"pid", "at"} \
                and type(record.get("pid")) is int \
                and type(record.get("at")) is int:
            now_ms = time.time_ns() // 1000000
            fresh = now_ms - record["at"] < _GBRAIN_REAP_CLAIM_TTL_MS
            return "native-live" if _native_pid_alive(
                record["pid"]) and fresh else "native-stale"
    elif names and not (
            len(names) == 1
            and _GBRAIN_REAP_TEMP.fullmatch(names[0]) is not None):
        return "ambiguous"

    age_ns = time.time_ns() - info.st_mtime_ns
    return "native-stale" \
        if age_ns >= _GBRAIN_REAP_CLAIM_TTL_NS else "native-live"


def _entry_exists_at(parent_fd, name):
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _directory_names(fd):
    return sorted(os.listdir(fd))


def _discard_rebind_record(directory_fd, token):
    name = ".sia-rebind-" + token
    if not _entry_exists_at(directory_fd, name):
        return
    _read_regular_at(directory_fd, name, "SIA native-lock rebind stage")
    os.unlink(name, dir_fd=directory_fd)
    os.fsync(directory_fd)


def _replace_native_record(directory_fd, token, record, validator, label):
    temporary = ".sia-rebind-" + token
    _discard_rebind_record(directory_fd, token)
    _write_exclusive_at(
        directory_fd, temporary, _canonical_bytes(record), 0o644)
    os.replace(
        temporary, "lock", src_dir_fd=directory_fd,
        dst_dir_fd=directory_fd)
    os.fsync(directory_fd)
    raw, _info = _read_regular_at(directory_fd, "lock", label)
    rebound = _strict_json(raw, label)
    if not validator(rebound, token):
        raise ValueError(label + " did not remain SIA-owned")


def _open_native_record_dir(parent_fd, name, token, validator, label):
    directory_fd = _open_owned_dir_at(parent_fd, name, label)
    try:
        _discard_rebind_record(directory_fd, token)
        if _directory_names(directory_fd) != ["lock"]:
            raise ValueError(label + " has ambiguous content")
        raw, _info = _read_regular_at(directory_fd, "lock", label + " record")
        record = _strict_json(raw, label + " record")
        if not validator(record, token):
            raise ValueError(label + " is not SIA's restore lock")
        if not _linked_dir_matches(parent_fd, name, directory_fd):
            raise ValueError(label + " was replaced while inspected")
        return directory_fd
    except Exception:
        os.close(directory_fd)
        raise


def _cleanup_unpublished_native_dir(parent_fd, name, label):
    if not _entry_exists_at(parent_fd, name):
        return
    directory_fd = _open_owned_dir_at(parent_fd, name, label)
    try:
        names = _directory_names(directory_fd)
        if names not in ([], ["lock"]):
            raise ValueError(label + " has ambiguous content")
        if names:
            _read_regular_at(directory_fd, "lock", label + " record")
        if not _linked_dir_matches(parent_fd, name, directory_fd):
            raise ValueError(label + " was replaced before cleanup")
        if names:
            os.unlink("lock", dir_fd=directory_fd)
            os.fsync(directory_fd)
        if not _linked_dir_matches(parent_fd, name, directory_fd):
            raise ValueError(label + " was replaced during cleanup")
        os.rmdir(name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(directory_fd)


def _cleanup_retired_native_dir(parent_fd, name, token, validator, label):
    if not _entry_exists_at(parent_fd, name):
        return
    directory_fd = _open_owned_dir_at(parent_fd, name, label)
    try:
        _discard_rebind_record(directory_fd, token)
        names = _directory_names(directory_fd)
        if names not in ([], ["lock"]):
            raise ValueError(label + " has ambiguous content")
        if names:
            raw, _info = _read_regular_at(
                directory_fd, "lock", label + " record")
            record = _strict_json(raw, label + " record")
            if not validator(record, token):
                raise ValueError(label + " is not SIA's retired lock")
        if not _linked_dir_matches(parent_fd, name, directory_fd):
            raise ValueError(label + " was replaced before cleanup")
        if names:
            os.unlink("lock", dir_fd=directory_fd)
            os.fsync(directory_fd)
        if not _linked_dir_matches(parent_fd, name, directory_fd):
            raise ValueError(label + " was replaced during cleanup")
        os.rmdir(name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(directory_fd)


def _cleanup_retired_standard_claim(parent_fd, name):
    if not _entry_exists_at(parent_fd, name):
        return
    directory_fd = _open_owned_dir_at(
        parent_fd, name, "retired native PGLite reap claim")
    try:
        names = _directory_names(directory_fd)
        if names not in ([], ["lock"]) and not (
                len(names) == 1
                and _GBRAIN_REAP_TEMP.fullmatch(names[0]) is not None):
            raise ValueError(
                "retired native PGLite reap claim has ambiguous content")
        if names:
            _read_regular_at(
                directory_fd, names[0],
                "retired native PGLite reap claim record")
        if not _linked_dir_matches(parent_fd, name, directory_fd):
            raise ValueError(
                "retired native PGLite reap claim was replaced")
        if names:
            os.unlink(names[0], dir_fd=directory_fd)
            os.fsync(directory_fd)
        if not _linked_dir_matches(parent_fd, name, directory_fd):
            raise ValueError(
                "retired native PGLite reap claim changed during cleanup")
        os.rmdir(name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(directory_fd)


def _retire_stale_native_reap_claim(projection, token):
    """Retire a dead/stale native claim without touching a live claimant."""
    projection = _owned_real_dir(projection, "target gbrain projection")
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
             | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    projection_fd = os.open(projection, flags)
    claim_fd = -1
    claim_name = ".gbrain-lock.reap-claim"
    retired_name = ".sia-retired-native-reap-claim-" + token
    try:
        held = os.fstat(projection_fd)
        linked = os.lstat(projection)
        if (held.st_dev, held.st_ino) != (linked.st_dev, linked.st_ino):
            raise ValueError("target gbrain projection changed while opened")
        _cleanup_retired_standard_claim(projection_fd, retired_name)
        if not _entry_exists_at(projection_fd, claim_name):
            return "absent"
        claim_fd = _open_owned_dir_at(
            projection_fd, claim_name, "native PGLite reap claim")
        state = _native_claim_state(claim_fd, token)
        if state == "sia":
            return state
        if state != "native-stale":
            raise RuntimeError(
                "native PGLite reap claim is live or ambiguous")
        if not _linked_dir_matches(projection_fd, claim_name, claim_fd) \
                or _native_claim_state(claim_fd, token) != "native-stale":
            raise ValueError(
                "native PGLite reap claim changed before retirement")
        _retire_open_native_dir(
            projection_fd, claim_name, retired_name, claim_fd,
            "native PGLite reap claim")
        os.close(claim_fd)
        claim_fd = -1
        _cleanup_retired_standard_claim(projection_fd, retired_name)
        if _entry_exists_at(projection_fd, claim_name):
            raise RuntimeError(
                "a replacement native PGLite reap claim appeared")
        return "native-retired"
    finally:
        if claim_fd >= 0:
            os.close(claim_fd)
        os.close(projection_fd)


def _acquire_native_reap_claim(projection_fd, token):
    claim_name = ".gbrain-lock.reap-claim"
    temporary_name = ".sia-restore-reap-claim-" + token
    if _entry_exists_at(projection_fd, claim_name):
        claim_fd = _open_native_record_dir(
            projection_fd, claim_name, token,
            _valid_native_claim_record, "SIA native-lock reap claim")
        try:
            _replace_native_record(
                claim_fd, token, _native_claim_record(token),
                _valid_native_claim_record, "SIA native-lock reap claim")
            if not _linked_dir_matches(projection_fd, claim_name, claim_fd):
                raise ValueError(
                    "SIA native-lock reap claim was replaced during rebind")
            return claim_fd
        except Exception:
            os.close(claim_fd)
            raise

    _cleanup_unpublished_native_dir(
        projection_fd, temporary_name,
        "temporary SIA native-lock reap claim")
    os.mkdir(temporary_name, 0o700, dir_fd=projection_fd)
    os.fsync(projection_fd)
    temporary_fd = _open_owned_dir_at(
        projection_fd, temporary_name,
        "temporary SIA native-lock reap claim")
    try:
        _write_exclusive_at(
            temporary_fd, "lock",
            _canonical_bytes(_native_claim_record(token)), 0o644)
    finally:
        os.close(temporary_fd)
    try:
        _rename_noreplace_fd(
            projection_fd, temporary_name, claim_name)
    except Exception:
        _cleanup_unpublished_native_dir(
            projection_fd, temporary_name,
            "temporary SIA native-lock reap claim")
        raise
    return _open_native_record_dir(
        projection_fd, claim_name, token,
        _valid_native_claim_record, "SIA native-lock reap claim")


def _retire_open_native_dir(parent_fd, current_name, retired_name,
                            directory_fd, label):
    if not _linked_dir_matches(parent_fd, current_name, directory_fd):
        raise ValueError(label + " was replaced before retirement")
    _rename_noreplace_fd(parent_fd, current_name, retired_name)
    if not _linked_dir_matches(parent_fd, retired_name, directory_fd):
        raise ValueError(label + " changed during retirement")


def _prepare_live_projection_for_native_lock(journal):
    """Quiesce native debt, keeping SIA and gbrain lock authorities apart."""
    _root, projection, _config, _pack = _gbrain_live_paths()
    token = journal["native_lock_token"]
    authority = _native_lock_authority(projection, token)
    if authority == "sia":
        _retire_stale_native_reap_claim(projection, token)
        _remove_native_lock_intent(projection, token)

    report = _probe_live_projection_quiescent()
    claim_state = _retire_stale_native_reap_claim(projection, token)
    if claim_state == "sia":
        _remove_native_lock_intent(projection, token)

    authority = _native_lock_authority(projection, token)
    if authority != "absent" \
            or os.path.lexists(os.path.join(
                projection, ".gbrain-lock.reap-claim")):
        raise RuntimeError(
            "native PGLite quiescence left unresolved lock debt")
    return report


def _remove_native_lock_intent(projection, token):
    """Remove only SIA's lock, preserving any racing native replacement."""
    projection = _owned_real_dir(projection, "target gbrain projection")
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
             | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    projection_fd = os.open(projection, flags)
    temporary_lock = ".sia-restore-native-lock-" + token
    temporary_claim = ".sia-restore-reap-claim-" + token
    retired_lock = ".sia-retired-native-lock-" + token
    retired_claim = ".sia-retired-reap-claim-" + token
    lock_name = ".gbrain-lock"
    claim_name = ".gbrain-lock.reap-claim"
    try:
        held = os.fstat(projection_fd)
        linked = os.lstat(projection)
        if (held.st_dev, held.st_ino) != (linked.st_dev, linked.st_ino):
            raise ValueError("target gbrain projection changed while opened")
        _cleanup_unpublished_native_dir(
            projection_fd, temporary_lock, "temporary SIA native lock")
        _cleanup_unpublished_native_dir(
            projection_fd, temporary_claim,
            "temporary SIA native-lock reap claim")
        _cleanup_retired_native_dir(
            projection_fd, retired_lock, token,
            _valid_native_lock_record, "retired SIA native lock")
        _cleanup_retired_native_dir(
            projection_fd, retired_claim, token,
            _valid_native_claim_record,
            "retired SIA native-lock reap claim")

        if not _entry_exists_at(projection_fd, lock_name):
            if _entry_exists_at(projection_fd, claim_name):
                claim_fd = _open_native_record_dir(
                    projection_fd, claim_name, token,
                    _valid_native_claim_record,
                    "SIA native-lock reap claim")
                try:
                    _replace_native_record(
                        claim_fd, token, _native_claim_record(token),
                        _valid_native_claim_record,
                        "SIA native-lock reap claim")
                    _retire_open_native_dir(
                        projection_fd, claim_name, retired_claim,
                        claim_fd, "SIA native-lock reap claim")
                finally:
                    os.close(claim_fd)
                _cleanup_retired_native_dir(
                    projection_fd, retired_claim, token,
                    _valid_native_claim_record,
                    "retired SIA native-lock reap claim")
            if _entry_exists_at(projection_fd, lock_name) \
                    or _entry_exists_at(projection_fd, claim_name):
                raise RuntimeError(
                    "a replacement native PGLite holder appeared")
            return

        lock_fd = _open_native_record_dir(
            projection_fd, lock_name, token,
            _valid_native_lock_record, "SIA restore native lock")
        claim_fd = -1
        try:
            claim_fd = _acquire_native_reap_claim(projection_fd, token)
            if not _linked_dir_matches(projection_fd, lock_name, lock_fd):
                raise ValueError(
                    "SIA restore native lock was replaced before cleanup")
            _replace_native_record(
                lock_fd, token, _native_lock_record(token),
                _valid_native_lock_record, "SIA restore native lock")
            _replace_native_record(
                claim_fd, token, _native_claim_record(token),
                _valid_native_claim_record,
                "SIA native-lock reap claim")
            if not _linked_dir_matches(projection_fd, lock_name, lock_fd) \
                    or not _linked_dir_matches(
                        projection_fd, claim_name, claim_fd):
                raise ValueError(
                    "native PGLite cleanup ownership changed")
            _retire_open_native_dir(
                projection_fd, lock_name, retired_lock, lock_fd,
                "SIA restore native lock")
            _cleanup_retired_native_dir(
                projection_fd, retired_lock, token,
                _valid_native_lock_record, "retired SIA native lock")
            _replace_native_record(
                claim_fd, token, _native_claim_record(token),
                _valid_native_claim_record,
                "SIA native-lock reap claim")
            _retire_open_native_dir(
                projection_fd, claim_name, retired_claim, claim_fd,
                "SIA native-lock reap claim")
        finally:
            os.close(lock_fd)
            if claim_fd >= 0:
                os.close(claim_fd)
        _cleanup_retired_native_dir(
            projection_fd, retired_claim, token,
            _valid_native_claim_record,
            "retired SIA native-lock reap claim")
        if _entry_exists_at(projection_fd, lock_name) \
                or _entry_exists_at(projection_fd, claim_name):
            raise RuntimeError("a replacement native PGLite holder appeared")
    finally:
        os.close(projection_fd)


def _acquire_native_projection_lock(journal):
    _root, projection, _config, _pack = _gbrain_live_paths()
    token = journal["native_lock_token"]
    # A prior power cut may have left this journal's authenticated intent.
    # Retire only that exact token before publishing a fresh live generation;
    # a foreign holder or reap claim is preserved and refused.
    _remove_native_lock_intent(projection, token)
    temporary_name = ".sia-restore-native-lock-" + token
    lock_name = ".gbrain-lock"
    projection = _owned_real_dir(projection, "target gbrain projection")
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
             | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    projection_fd = os.open(projection, flags)
    try:
        held = os.fstat(projection_fd)
        linked = os.lstat(projection)
        if (held.st_dev, held.st_ino) != (linked.st_dev, linked.st_ino):
            raise ValueError("target gbrain projection changed while opened")
        if _entry_exists_at(projection_fd, temporary_name) \
                or _entry_exists_at(projection_fd, lock_name) \
                or _entry_exists_at(
                    projection_fd, ".gbrain-lock.reap-claim"):
            raise RuntimeError("a native PGLite holder or lock debt is present")
        os.mkdir(temporary_name, 0o700, dir_fd=projection_fd)
        os.fsync(projection_fd)
        temporary_fd = _open_owned_dir_at(
            projection_fd, temporary_name, "temporary SIA native lock")
        try:
            _write_exclusive_at(
                temporary_fd, "lock",
                _canonical_bytes(_native_lock_record(token)), 0o644)
        finally:
            os.close(temporary_fd)
        try:
            _rename_noreplace_fd(
                projection_fd, temporary_name, lock_name)
        except Exception:
            _cleanup_unpublished_native_dir(
                projection_fd, temporary_name,
                "temporary SIA native lock")
            raise
        lock_fd = _open_native_record_dir(
            projection_fd, lock_name, token,
            _valid_native_lock_record, "SIA restore native lock")
        os.close(lock_fd)
    finally:
        os.close(projection_fd)


def _initialize_projection_stage(journal):
    """Create and probe a fresh PGLite store without touching the live one."""
    binding = _gbrain_substrate_binding(journal)
    stage_home = journal["projection_stage_home"]
    if os.path.lexists(stage_home):
        raise ValueError("new gbrain projection stage already exists")
    os.mkdir(stage_home, 0o700)
    stage_root = os.path.join(stage_home, ".gbrain")
    os.mkdir(stage_root, 0o700)
    stage_packs = os.path.join(stage_root, "schema-packs")
    os.mkdir(stage_packs, 0o700)
    stage_pack_dir = os.path.join(stage_packs, _GBRAIN_SCHEMA_PACK_NAME)
    os.mkdir(stage_pack_dir, 0o700)
    _root, _projection, config_path, pack_path = _gbrain_live_paths()
    copied = _copy_file(
        pack_path, os.path.join(stage_pack_dir, "pack.yaml"),
        "schema-packs/sia-pack/pack.yaml")
    if copied["sha256"] != hashlib.sha256(
            _read_regular(pack_path, "managed SIA schema pack")[0]
            ).hexdigest():
        raise RuntimeError("staged schema pack digest changed")

    config = _strict_json(
        _read_regular(config_path, "target gbrain config", private=True)[0],
        "target gbrain config")
    stage_projection = os.path.join(stage_root, _GBRAIN_PROJECTION_NAME)
    arguments = [
        "init", "--pglite", "--non-interactive", "--json",
        "--skip-embed-check", "--path", stage_projection,
        "--schema-pack", _GBRAIN_SCHEMA_PACK_NAME,
    ]
    if config.get("embedding_disabled") is True:
        arguments.append("--no-embedding")
    else:
        arguments.extend([
            "--embedding-model", config["embedding_model"],
            "--embedding-dimensions", str(config["embedding_dimensions"]),
        ])
    _run_gbrain(arguments, home=stage_home,
                label="off-path gbrain projection initialization")
    _owned_real_dir(stage_projection, "staged gbrain projection")
    _probe_projection(
        stage_home, stage_projection, "staged gbrain projection probe")
    _gbrain_substrate_binding(binding)
    return stage_projection


def _stage_gbrain_projection(journal):
    """Replace only the rebuildable projection; preserve runtime substrate."""
    root, live_projection, _config, _pack = _gbrain_live_paths()
    _gbrain_substrate_binding(journal)
    staged_projection = os.path.join(
        journal["projection_stage_home"], ".gbrain",
        _GBRAIN_PROJECTION_NAME)
    _owned_real_dir(staged_projection, "staged gbrain projection")
    if os.path.lexists(journal["projection_path"]):
        raise ValueError("target gbrain projection is already staged")
    _move_aside(live_projection, journal["projection_path"])
    for name in _GBRAIN_PROJECTION_SIDECARS:
        if journal["projection_sidecars"][name] is not None:
            _move_aside(
                os.path.join(root, name),
                os.path.join(os.path.dirname(journal["projection_path"]),
                             "target-" + name))
    _move_aside(staged_projection, live_projection)
    _owned_real_dir(live_projection, "published gbrain projection")


def _activate_restored_projection():
    """Bind the restored corpus to the fresh DB through gbrain's front door."""
    _root, projection, _config, _pack = _gbrain_live_paths()
    _probe_projection(
        sialib.SHARE, projection, "published gbrain projection probe")
    _run_gbrain(
        ["sources", "add", "sia", "--path", sialib.CORPUS],
        home=sialib.SHARE, label="restored gbrain source registration")
    listed = _run_gbrain(
        ["sources", "list", "--json"], home=sialib.SHARE,
        label="restored gbrain source inspection")
    report = _strict_json(
        listed.stdout.encode("utf-8"), "restored gbrain source inspection")
    sources = report.get("sources") if isinstance(report, dict) else None
    matches = [] if not isinstance(sources, list) else [
        row for row in sources if isinstance(row, dict)
        and row.get("id") == "sia"]
    if len(matches) != 1 or matches[0].get("local_path") != sialib.CORPUS:
        raise RuntimeError("restored gbrain source registration is not exact")
    _run_gbrain(
        ["schema", "validate", _GBRAIN_SCHEMA_PACK_NAME],
        home=sialib.SHARE, label="retained SIA schema-pack validation")


def _restore_target_gbrain(journal, failed_root):
    """Restore the prior projection while keeping the substrate in place."""
    root, live_projection, _config, _pack = _gbrain_live_paths()
    current = _gbrain_substrate_binding(projection_required=False)
    for key in ("gbrain_root", "gbrain_config", "schema_pack",
                "schema_receipt"):
        if current[key] != journal[key]:
            raise ValueError("target gbrain substrate changed during rollback")

    saved_projection = os.path.lexists(journal["projection_path"])
    failed_gbrain = os.path.join(failed_root, "share", ".gbrain")
    if saved_projection:
        _owned_real_dir(journal["projection_path"],
                        "rollback gbrain projection")
        if os.path.lexists(live_projection):
            _prepare_live_projection_for_native_lock(journal)
            _acquire_native_projection_lock(journal)
            _move_aside(
                live_projection,
                os.path.join(failed_gbrain, _GBRAIN_PROJECTION_NAME))
        _move_aside(journal["projection_path"], live_projection)
    elif _root_identity(os.lstat(live_projection)) != journal["projection"]:
        raise ValueError("unmoved target gbrain projection changed")
    _remove_native_lock_intent(
        live_projection, journal["native_lock_token"])

    for name in _GBRAIN_PROJECTION_SIDECARS:
        live = os.path.join(root, name)
        saved = os.path.join(
            os.path.dirname(journal["projection_path"]), "target-" + name)
        original = journal["projection_sidecars"][name]
        if os.path.lexists(saved):
            if original is None:
                raise ValueError("absent target gained a saved gbrain sidecar")
            if os.path.lexists(live):
                _move_aside(live, os.path.join(failed_gbrain, name))
            _move_aside(saved, live)
        elif original is not None:
            if not os.path.lexists(live) \
                    or _gbrain_sidecar_record(live) != original:
                raise ValueError("unmoved target gbrain sidecar changed")
        elif os.path.lexists(live):
            _move_aside(live, os.path.join(failed_gbrain, name))
    _gbrain_substrate_binding(journal, stable_sidecars=True)


def thaw(prepared, confirmation, *, capability, identity_key_file=None,
         rollback_root, first_light=None):
    """Transactionally adopt one verified capsule into the live SIA roots.

    ``capability`` has exactly four already-held exclusive descriptors:
    ``lifecycle_fd``, ``brainstem_fd``, ``corpus_fd``, and ``gbrain_fd``.
    The caller must still be inside the corresponding owner contexts.
    ``first_light(full_sync=True)`` performs SIA's ordinary post-restore pulse;
    this module independently requires readiness and SIA-ledger verification
    before it clears the durable boot barrier.
    """
    validate_restore_capability(capability)
    if first_light is None:
        first_light = _native_first_light
    if not callable(first_light):
        raise ValueError("thaw requires a first-light callback")
    verified = _prepared_binding(prepared)
    if not os.path.isabs(rollback_root):
        raise ValueError("rollback root must be absolute")
    rollback_root = os.path.abspath(rollback_root)
    continuity = os.path.realpath(CONTINUITY_ROOT)
    resolved_rollback = os.path.realpath(rollback_root)
    if os.path.commonpath((resolved_rollback, continuity)) != continuity:
        raise ValueError("rollback root is outside continuity state")
    os.makedirs(rollback_root, mode=0o700, exist_ok=True)
    rollback_root = _validate_rollback_root(rollback_root)
    if os.path.lexists(RESTORE_BARRIER):
        raise RuntimeError(
            "an interrupted restore barrier already requires recovery")
    _reconcile_rollback_operations(rollback_root)
    if os.path.lexists(RESTORE_BARRIER):
        raise RuntimeError(
            "a restore barrier appeared during rollback reconciliation")

    target_before = target_identity()
    current_head = _target_ledger_head()
    _validate_confirmation(confirmation, prepared, current_head)

    restore_identity = None
    matches = identity_matches(verified)
    if not matches:
        if identity_key_file is None:
            raise ValueError("prepared identity requires the offline identity file")
        restore_identity = validate_identity_key(
            identity_key_file, verified["public_key"])["private_key"]

    operation_root = os.path.join(
        rollback_root, prepared["prepared_id"] + "-" + uuid.uuid4().hex)
    os.mkdir(operation_root, 0o700)
    try:
        _fsync_dir(rollback_root)
        journal, target_key = _prepare_rollback_operation(
            operation_root, prepared, current_head, target_before)
    except Exception:
        _retire_inactive_operation(operation_root)
        raise
    journal_path = os.path.join(operation_root, "journal.json")
    target_key_path = journal["target_key_path"]
    target_key_present = journal["target_key_present"]
    adoption_path = journal["adoption_intent"]
    adoption_committed_path = journal["adoption_committed"]
    try:
        _atomic_json(journal_path, journal)
        adoption_intent = write_adoption_intent(
            adoption_path, prepared=prepared, confirmation=confirmation,
            target=target_before)
        barrier = {"schema": JOURNAL_SCHEMA,
                   "journal": journal_path,
                   "prepared_id": prepared["prepared_id"],
                   "created": _now()}
        _owned_real_dir(CONTINUITY_ROOT, "continuity state")
        _atomic_json(RESTORE_BARRIER, barrier)
    except Exception:
        if not os.path.lexists(RESTORE_BARRIER):
            _retire_inactive_operation(operation_root)
        raise

    try:
        if target_key_present:
            _write_exclusive(target_key_path, target_key, 0o600)
        _initialize_projection_stage(journal)
        removed_root = os.path.join(operation_root, "replaced-live")
        os.mkdir(removed_root, 0o700)
        with _freeze_locks():
            if target_identity() != target_before \
                    or _target_ledger_head() != current_head:
                raise RuntimeError("target changed before thaw mutation")
            install_binding = verify(verified["capsule_path"])
            for key in ("capsule_id", "classification", "corpus_head",
                        "ledger_head", "public_key", "manifest_sha256"):
                if install_binding.get(key) != verified.get(key):
                    raise RuntimeError("prepared capsule changed before thaw")
            _prepare_live_projection_for_native_lock(journal)
            _refresh_barrier_gbrain_binding(journal, journal_path)
            _gbrain_substrate_binding(journal)
            _acquire_native_projection_lock(journal)
            journal["phase"] = "mutating"
            _atomic_json(journal_path, journal)
            _clear_live_portable(removed_root)
            _stage_gbrain_projection(journal)
            if not matches and os.path.lexists(LEDGER_KEY):
                _move_aside(LEDGER_KEY,
                            os.path.join(removed_root, "share", "key.hex"))
            _install_capsule_content(
                verified["capsule_path"], binding=install_binding)
            if not matches:
                _install_private_hex(restore_identity)
            _activate_restored_projection()
            _set_restored_sync_needed()
            if target_identity() != target_before:
                raise RuntimeError("thaw changed the target root or receipt")

        journal["phase"] = "first-light"
        _atomic_json(journal_path, journal)
        previous_full_sync = os.environ.get("SIA_RESTORE_FULL_SYNC")
        os.environ["SIA_RESTORE_FULL_SYNC"] = "1"
        try:
            first_light(full_sync=True)
        finally:
            if previous_full_sync is None:
                os.environ.pop("SIA_RESTORE_FULL_SYNC", None)
            else:
                os.environ["SIA_RESTORE_FULL_SYNC"] = previous_full_sync
        journal["phase"] = "settling-adoption"
        _atomic_json(journal_path, journal)
        _settle_adoption(adoption_intent, adoption_committed_path)
        health = _restore_health()
        journal["phase"] = "cleaning-commit"
        _atomic_json(journal_path, journal)
        outcome = _finish_operation_retirement(
            journal_path, journal, rolled_back=False, health=health)
        return {
            "prepared_id": prepared["prepared_id"],
            "snapshot_id": prepared["snapshot_id"],
            "capsule_id": verified["capsule_id"],
            "restored": True,
            **outcome,
        }
    except Exception as restore_error:
        # A terminal cleanup may already have durably cleared the barrier.
        # The signed adoption/rollback outcome is then settled; never turn a
        # retention failure into a second live-state mutation.
        if not os.path.lexists(RESTORE_BARRIER):
            raise RuntimeError(
                "restore outcome settled but rollback retirement was refused") \
                from restore_error
        try:
            recovered = rollback_restore(journal_path, capability=capability)
        except Exception as rollback_error:
            raise RuntimeError(
                "restore failed and rollback remains behind the durable "
                f"barrier: {rollback_error}") from restore_error
        if recovered.get("rolled_back") is False:
            return {
                "prepared_id": prepared["prepared_id"],
                "snapshot_id": prepared["snapshot_id"],
                "capsule_id": verified["capsule_id"],
                "restored": True,
                **recovered,
            }
        raise RuntimeError("restore failed and was rolled back") from restore_error
