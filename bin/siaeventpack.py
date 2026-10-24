"""Experimental bounded event-index transport; grants no source authority.

Records retain exact legacy bytes. Callers must independently validate every
legacy record and its epoch lineage. This module performs no filesystem I/O,
migration, publication, signature verification or deletion.
"""

import hashlib
import re

MAX_BYTES = 65_536
MAX_RECORDS = 64
MAGIC = b"SIA-EVENT-PACK-1\n"
_ORGAN = re.compile(r"[a-z0-9][a-z0-9._-]{0,199}\Z")
_PREFIX = re.compile(r"[0-9a-f]{3}\Z")
_ID = re.compile(rb"[0-9a-f]{64}\Z")


def _route(organ, prefix):
    if type(organ) is not str or _ORGAN.fullmatch(organ) is None:
        raise ValueError("event pack organ is invalid")
    if type(prefix) is not str or _PREFIX.fullmatch(prefix) is None:
        raise ValueError("event pack prefix is invalid")
    return organ.encode("ascii"), prefix.encode("ascii")


def _record(identifier, raw, prefix, previous):
    if type(identifier) is not bytes or _ID.fullmatch(identifier) is None:
        raise ValueError("event pack identifier is invalid")
    if not identifier.startswith(prefix) or identifier <= previous:
        raise ValueError("event pack ordering or route is invalid")
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError("event pack record bytes are invalid")


def header_size(organ, prefix):
    """Validated wire-header size, independent of payload interpretation."""
    organ_raw, _prefix_raw = _route(organ, prefix)
    return len(MAGIC) + 1 + len(organ_raw) + 3 + 1 + 4 + 32


def encode(organ, prefix, records):
    """Encode a strictly ordered tuple without interpreting legacy bytes."""
    organ_raw, prefix_raw = _route(organ, prefix)
    if type(records) is not tuple or not 1 <= len(records) <= MAX_RECORDS:
        raise ValueError("event pack record count is invalid")
    framing = header_size(organ, prefix)
    body = bytearray()
    previous = b""
    for item in records:
        if type(item) is not tuple or len(item) != 2:
            raise ValueError("event pack record shape is invalid")
        identifier, raw = item
        _record(identifier, raw, prefix_raw, previous)
        if framing + len(body) + 68 + len(raw) > MAX_BYTES:
            raise ValueError("event pack exceeds its byte bound")
        body.extend(identifier)
        body.extend(len(raw).to_bytes(4, "big"))
        body.extend(raw)
        previous = identifier
    header = (MAGIC + bytes([len(organ_raw)]) + organ_raw + prefix_raw
              + bytes([len(records)]) + len(body).to_bytes(4, "big")
              + hashlib.sha256(body).digest())
    return header + bytes(body)


def _header(raw, organ_raw, prefix_raw):
    fixed = MAGIC + bytes([len(organ_raw)]) + organ_raw + prefix_raw
    start = len(fixed)
    body_start = start + 1 + 4 + 32
    if len(raw) < body_start or raw[:start] != fixed:
        raise ValueError("event pack header or route is invalid")
    count = raw[start]
    size = int.from_bytes(raw[start + 1:start + 5], "big")
    if not 1 <= count <= MAX_RECORDS or size != len(raw) - body_start:
        raise ValueError("event pack count or size is invalid")
    digest = raw[start + 5:body_start]
    if hashlib.sha256(raw[body_start:]).digest() != digest:
        raise ValueError("event pack digest is invalid")
    return count, body_start


def decode(raw, organ, prefix):
    """Return exact record bytes only after the whole frame is validated."""
    organ_raw, prefix_raw = _route(organ, prefix)
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError("event pack bytes are invalid")
    count, position = _header(raw, organ_raw, prefix_raw)
    result = []
    previous = b""
    for _ in range(count):
        if len(raw) - position < 68:
            raise ValueError("event pack record header is truncated")
        identifier = raw[position:position + 64]
        size = int.from_bytes(raw[position + 64:position + 68], "big")
        position += 68
        if size > len(raw) - position:
            raise ValueError("event pack record is truncated")
        value = raw[position:position + size]
        _record(identifier, value, prefix_raw, previous)
        result.append((identifier, value))
        position += size
        previous = identifier
    if position != len(raw):
        raise ValueError("event pack has trailing bytes")
    return tuple(result)
