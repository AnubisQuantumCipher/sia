#!/usr/bin/env python3
"""Fail-closed release-generation comparison for the SIA installer."""

import json
import os
import re
import stat
import sys


MAX_RUNTIME_SOURCE_BYTES = 16_777_216
MAX_COMPLETION_BYTES = 4_096
VERSION_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


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
    if len(arguments) != 3:
        print(
            "usage: siarelease.py SOURCE_RUNTIME RESIDENT_RUNTIME COMPLETION",
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
