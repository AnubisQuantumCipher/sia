#!/usr/bin/env python3
"""Fail-closed release and runtime-receipt authority for SIA."""

import hashlib
import json
import os
import re
import stat
import sys


MAX_RUNTIME_SOURCE_BYTES = 16_777_216
MAX_COMPLETION_BYTES = 4_096
VERSION_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


LEGACY_RUNTIME_NAMES = (
    "sia-brainstem", "sia-ledger", "sia-mcp", "siabench.py", "sialib.py",
    "siamind.py", "siaqueue.py", "siatakes.py")
MODERN_V2_RUNTIME_NAMES = (
    "sia-brainstem", "sia-brainstem.py", "sia-cli", "sia-ledger", "sia-mcp",
    "siabench.py", "sialib.py", "siamind.py", "siaqueue.py", "siatakes.py")
MODERN_V3_RUNTIME_NAMES = MODERN_V2_RUNTIME_NAMES + ("siasenses.py",)
MODERN_V4_RUNTIME_NAMES = MODERN_V3_RUNTIME_NAMES + (
    "siacapsule.py", "siabackup.py", "siarestoreadmit.py",
    "sia-continuity-worker")
MODERN_V5_RUNTIME_NAMES = MODERN_V4_RUNTIME_NAMES + ("siagraph.py",)
MODERN_V6_RUNTIME_NAMES = MODERN_V5_RUNTIME_NAMES + ("siathought.py",)

# Ordered newest first.  Marker presence selects a rung even when the tree is
# incomplete; hashing then refuses on the missing member instead of silently
# falling back to an older, weaker receipt contract.  The empty marker tuple
# is the legacy fallback and therefore must remain last.
RUNTIME_LADDER = (
    (b"sia-runtime-v6\0", MODERN_V6_RUNTIME_NAMES, ("siathought.py",)),
    (b"sia-runtime-v5\0", MODERN_V5_RUNTIME_NAMES, ("siagraph.py",)),
    (b"sia-runtime-v4\0", MODERN_V4_RUNTIME_NAMES,
     ("siacapsule.py", "siabackup.py", "sia-continuity-worker")),
    (b"sia-runtime-v3\0", MODERN_V3_RUNTIME_NAMES, ("siasenses.py",)),
    (b"sia-runtime-v2\0", MODERN_V2_RUNTIME_NAMES,
     ("sia-brainstem.py", "sia-cli")),
    (b"sia-runtime-v1\0", LEGACY_RUNTIME_NAMES, ()),
)
LATEST_RUNTIME_NAMES = MODERN_V6_RUNTIME_NAMES


def validate_runtime_ladder(ladder=None):
    """Refuse a ladder whose schema could weaken receipt classification."""
    candidate = RUNTIME_LADDER if ladder is None else ladder
    if not isinstance(candidate, tuple) or not candidate:
        raise ValueError("runtime ladder must be a non-empty tuple")

    salts = set()
    checked = []
    for entry in candidate:
        if not isinstance(entry, tuple) or len(entry) != 3:
            raise ValueError("runtime ladder entry has an invalid shape")
        salt, names, selectors = entry
        if not isinstance(salt, bytes) \
                or re.fullmatch(
                    rb"sia-runtime-v(?:[1-9][0-9]*)\0", salt) is None:
            raise ValueError("runtime ladder salt is malformed")
        if salt in salts:
            raise ValueError("runtime ladder has a duplicate salt")
        salts.add(salt)
        if not isinstance(names, tuple) or not names:
            raise ValueError("runtime ladder members must be a non-empty tuple")
        if not isinstance(selectors, tuple):
            raise ValueError("runtime ladder selectors are malformed")
        for value in names + selectors:
            if not isinstance(value, str) \
                    or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) \
                    is None:
                raise ValueError("runtime ladder basename is malformed")
        if len(names) != len(set(names)):
            raise ValueError("runtime ladder has a duplicate member")
        if len(selectors) != len(set(selectors)):
            raise ValueError("runtime ladder has a duplicate selector")
        checked.append((names, selectors))

    prior_names = ()
    prior_set = set()
    for names, selectors in reversed(checked):
        current = set(names)
        if not prior_names:
            if selectors:
                raise ValueError("runtime ladder fallback has selectors")
        else:
            if not prior_set < current:
                raise ValueError("runtime ladder is not cumulative")
            if tuple(name for name in names if name in prior_set) \
                    != prior_names:
                raise ValueError("runtime ladder reorders prior members")
            introduced = current - prior_set
            if not selectors:
                raise ValueError("runtime ladder rung has no selector")
            if not set(selectors).issubset(introduced):
                raise ValueError(
                    "runtime ladder selector is outside introduced members")
        prior_names = names
        prior_set = current


def runtime_rung(root):
    """Return ``(salt, required_names)`` for the markers present at *root*."""
    ladder = RUNTIME_LADDER
    validate_runtime_ladder(ladder)
    root = os.fspath(root)
    for salt, names, markers in ladder:
        if not markers or any(
                os.path.lexists(os.path.join(root, marker))
                for marker in markers):
            return salt, names
    raise AssertionError("runtime ladder has no fallback rung")


def _runtime_generation(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def runtime_tree_digest(root):
    """Hash the selected shipped runtime rung through stable owned fds."""
    root = os.fspath(root)
    salt, names = runtime_rung(root)
    digest = hashlib.sha256(salt)
    uid = os.geteuid()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    for name in names:
        path = os.path.join(root, name)
        descriptor = os.open(path, flags)
        member = hashlib.sha256()
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_uid != uid:
                raise ValueError(f"unsafe runtime member: {name}")
            while True:
                chunk = os.read(descriptor, 1_048_576)
                if not chunk:
                    break
                member.update(chunk)
            after = os.fstat(descriptor)
            current = os.stat(path, follow_symlinks=False)
            if not stat.S_ISREG(current.st_mode) or current.st_uid != uid \
                    or _runtime_generation(before) != _runtime_generation(after) \
                    or _runtime_generation(after) != _runtime_generation(current):
                raise ValueError(
                    f"runtime member changed while hashing: {name}")
        finally:
            os.close(descriptor)
        digest.update(
            name.encode("utf-8") + b"\0" + member.digest())
    return digest.hexdigest()


def _read_fence_owned(path, limit, uid, flags):
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
                or current.st_uid != uid or b"\0" in content \
                or _runtime_generation(before) != _runtime_generation(after) \
                or _runtime_generation(after) != _runtime_generation(current):
            raise ValueError("managed metadata changed while reading")
        return content
    finally:
        os.close(descriptor)


def authorize_fenced_runtime(journal, tombstone, receipt, runtime):
    """Validate an uninstall fence, including mode-zero runtime members."""
    uid = os.geteuid()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    try:
        payload = json.loads(
            _read_fence_owned(journal, 1_048_576, uid, flags))
        marker = os.lstat(tombstone)
        contents = _read_fence_owned(
            receipt, 65_536, uid, flags).decode("utf-8")
        runtime_info = os.lstat(runtime)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid runtime launch-fence metadata") from error
    if not stat.S_ISREG(marker.st_mode) or marker.st_uid != uid \
            or not stat.S_ISDIR(runtime_info.st_mode) \
            or runtime_info.st_uid != uid \
            or not isinstance(payload, dict) \
            or payload.get("schema") != "sia-launch-fence-v1" \
            or set(payload) != {"schema", "runtime_before_digest",
                                "runtime_digest", "cli_digest", "entries"} \
            or not isinstance(payload["entries"], list):
        raise ValueError("invalid runtime launch-fence metadata")
    before_digest = payload["runtime_before_digest"]
    if not isinstance(before_digest, str) \
            or re.fullmatch(r"[0-9a-f]{64}", before_digest) is None:
        raise ValueError("invalid runtime launch-fence digest")
    expected = (
        f"managed-by=khephri.sia\nkind=runtime\npath={runtime}\n"
        f"sha256={before_digest}\n")
    if contents != expected:
        raise ValueError("runtime receipt does not match launch fence")

    entries = {}
    for entry in payload["entries"]:
        if not isinstance(entry, dict) \
                or set(entry) != {
                    "path", "device", "inode", "mode", "sha256"} \
                or not isinstance(entry["path"], str) \
                or entry["path"] in entries \
                or any(isinstance(entry[key], bool)
                       or not isinstance(entry[key], int) or entry[key] < 0
                       for key in ("device", "inode", "mode")) \
                or entry["mode"] > 0o7777 \
                or not isinstance(entry["sha256"], str) \
                or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None:
            raise ValueError("invalid runtime launch-fence entry")
        entries[entry["path"]] = entry

    salt, names = runtime_rung(runtime)
    digest = hashlib.sha256(salt)
    for name in names:
        path = os.path.join(runtime, name)
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != uid:
            raise ValueError(f"unsafe runtime member: {name}")
        if stat.S_IMODE(info.st_mode) == 0:
            entry = entries.get(path)
            if entry is None or (info.st_dev, info.st_ino) != (
                    entry["device"], entry["inode"]):
                raise ValueError(
                    f"unattested fenced runtime member: {name}")
            member_digest = bytes.fromhex(entry["sha256"])
        else:
            descriptor = os.open(path, flags)
            member = hashlib.sha256()
            try:
                before = os.fstat(descriptor)
                if not stat.S_ISREG(before.st_mode) or before.st_uid != uid \
                        or (before.st_dev, before.st_ino) != (
                            info.st_dev, info.st_ino):
                    raise ValueError(f"unsafe runtime member: {name}")
                while True:
                    chunk = os.read(descriptor, 1_048_576)
                    if not chunk:
                        break
                    member.update(chunk)
                after = os.fstat(descriptor)
                current = os.stat(path, follow_symlinks=False)
                if not stat.S_ISREG(current.st_mode) \
                        or current.st_uid != uid \
                        or _runtime_generation(before) != \
                        _runtime_generation(after) \
                        or _runtime_generation(after) != \
                        _runtime_generation(current):
                    raise ValueError(
                        f"runtime member changed while hashing: {name}")
            finally:
                os.close(descriptor)
            member_digest = member.digest()
        digest.update(
            name.encode("utf-8") + b"\0" + member_digest)
    if digest.hexdigest() != before_digest:
        raise ValueError("runtime launch-fence digest does not match")
    return before_digest


def _stable_owned_read(path, label, limit, *, required):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        if required:
            raise ValueError(f"{label} is missing") from None
        return None
    except OSError as error:
        raise ValueError(f"{label} cannot be opened safely: {error}") \
            from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() or before.st_nlink != 1 \
                or stat.S_IMODE(before.st_mode) & 0o022:
            raise ValueError(f"{label} is not an owner-controlled regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read(limit + 1)
        after = os.fstat(descriptor)
        if len(payload) > limit:
            raise ValueError(f"{label} exceeds its byte bound")
        observed = (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns)
        finished = (after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns)
        if observed != finished:
            raise ValueError(f"{label} changed while read")
        try:
            named = os.stat(path, follow_symlinks=False)
        except OSError as error:
            raise ValueError(f"{label} changed after read: {error}") from error
        if (named.st_dev, named.st_ino) != (after.st_dev, after.st_ino):
            raise ValueError(f"{label} path changed after read")
        return payload
    finally:
        os.close(descriptor)


def _version_parts(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} has no valid release version")
    matched = VERSION_RE.fullmatch(value)
    if matched is None:
        raise ValueError(f"{label} has no valid release version")
    return tuple(matched.groups())


def _compare_versions(left, right):
    for left_part, right_part in zip(left, right):
        if len(left_part) != len(right_part):
            return -1 if len(left_part) < len(right_part) else 1
        if left_part != right_part:
            return -1 if left_part < right_part else 1
    return 0


def _python_release(payload, label):
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ValueError(f"{label} is not valid UTF-8") from error
    matches = re.findall(
        r'^VERSION = "((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))"$',
        text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(f"{label} does not declare exactly one release version")
    _version_parts(matches[0], label)
    return matches[0]


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("first-light completion has duplicate fields")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def _completion_release(payload):
    try:
        record = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValueError("first-light completion is malformed") from error
    if not isinstance(record, dict) or set(record) != {
            "v", "version", "state"} \
            or isinstance(record.get("v"), bool) or record.get("v") != 1 \
            or record.get("state") not in {"installing", "ready"}:
        raise ValueError("first-light completion has an invalid schema")
    _version_parts(record.get("version"), "first-light completion")
    return record["version"]


def refuse_release_downgrade(source_path, resident_path, completion_path):
    source = _stable_owned_read(
        source_path, "installer runtime", MAX_RUNTIME_SOURCE_BYTES,
        required=True)
    source_version = _python_release(source, "installer runtime")
    source_parts = _version_parts(source_version, "installer runtime")

    candidates = []
    resident = _stable_owned_read(
        resident_path, "resident runtime", MAX_RUNTIME_SOURCE_BYTES,
        required=False)
    if resident is not None:
        resident_version = _python_release(resident, "resident runtime")
        candidates.append(("resident runtime", resident_version))
    completion = _stable_owned_read(
        completion_path, "first-light completion", MAX_COMPLETION_BYTES,
        required=False)
    if completion is not None:
        candidates.append(
            ("first-light completion", _completion_release(completion)))

    for label, candidate in candidates:
        if _compare_versions(
                _version_parts(candidate, label), source_parts) > 0:
            raise ValueError(
                f"release downgrade refused: {label} {candidate} is newer "
                f"than installer {source_version}")
    return source_version


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["runtime-tree-digest"]:
        if len(arguments) != 2:
            print(
                "usage: siarelease.py runtime-tree-digest RUNTIME",
                file=sys.stderr)
            return 2
        try:
            print(runtime_tree_digest(arguments[1]))
        except (OSError, ValueError) as error:
            print(f"SIA runtime digest refused: {error}", file=sys.stderr)
            return 2
        return 0
    if arguments[:1] == ["runtime-authorize-fence"]:
        if len(arguments) != 5:
            print(
                "usage: siarelease.py runtime-authorize-fence "
                "JOURNAL TOMBSTONE RECEIPT RUNTIME",
                file=sys.stderr)
            return 2
        try:
            authorize_fenced_runtime(*arguments[1:])
        except (OSError, ValueError) as error:
            print(f"SIA runtime fence refused: {error}", file=sys.stderr)
            return 2
        return 0
    if len(arguments) != 3:
        print(
            "usage: siarelease.py SOURCE_RUNTIME RESIDENT_RUNTIME COMPLETION\n"
            "       siarelease.py runtime-tree-digest RUNTIME\n"
            "       siarelease.py runtime-authorize-fence "
            "JOURNAL TOMBSTONE RECEIPT RUNTIME",
            file=sys.stderr)
        return 2
    try:
        refuse_release_downgrade(*arguments)
    except (OSError, ValueError) as error:
        print(f"SIA installer refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
