"""Experimental captured dual-format lookup, not runtime publication authority.

The caller holds the existing corpus lease and owns a bounded dependency capture.
It must validate the complete capture before acting. No runtime imports this
module; source migration and protected authorization remain separate obligations.
"""

import os

import siaeventpack


def _optional(capture, path, maximum):
    if type(maximum) is not int or maximum <= 0:
        raise ValueError("event index read capacity is invalid")
    try:
        raw = capture.read_file(path, maximum)
    except FileNotFoundError:
        return None
    if type(raw) is not bytes or len(raw) > maximum:
        raise ValueError("event index capture returned invalid bytes")
    return raw


def _packed_entries(owner, capture, raw, organ, prefix):
    entries = {}
    if raw is not None:
        for key, value in siaeventpack.decode(raw, organ, prefix):
            identifier = key.decode("ascii")
            entry = owner["_validate_event_index_raw"](
                value, organ, identifier, dependency_capture=capture)
            entries[identifier] = (entry, value)
    return entries


def _request_paths(owner, organ, identifiers):
    if type(identifiers) is not tuple or not 1 <= len(identifiers) <= siaeventpack.MAX_RECORDS:
        raise ValueError("event index group request count is invalid")
    paths = []
    previous = ""
    for identifier in identifiers:
        if type(identifier) is not str or identifier <= previous:
            raise ValueError("event index group request order is invalid")
        relative = owner["_event_index_relative"](organ, identifier)
        if identifier[:3] != identifiers[0][:3]:
            raise ValueError("event index group request route is invalid")
        paths.append(os.path.join(owner["CORPUS"], relative))
        previous = identifier
    return tuple(paths)


def read_group_captured(owner, organ, identifiers, capture):
    """One bounded group request; no validated records survive across calls."""
    paths = _request_paths(owner, organ, identifiers)
    prefix = identifiers[0][:3]
    pack_path = os.path.join(owner["CORPUS"], "event-packs", organ,
                             prefix[:2], prefix + ".siaep")
    limit = owner["MAX_EVENT_INDEX_BYTES"]
    legacy = tuple(_optional(capture, path, limit) for path in paths)
    pack_raw = _optional(capture, pack_path, siaeventpack.MAX_BYTES)
    packed = _packed_entries(owner, capture, pack_raw, organ, prefix)
    result = {}
    for identifier, raw in zip(identifiers, legacy, strict=True):
        entry, packed_raw = packed.get(identifier, (None, None))
        if raw is not None:
            original = owner["_validate_event_index_raw"](
                raw, organ, identifier, dependency_capture=capture)
            if packed_raw is not None and packed_raw != raw:
                raise ValueError("event index representations conflict")
            entry = original
        result[identifier] = entry
    if owner["MAX_EVENT_INDEX_BYTES"] != limit:
        raise ValueError("event index record policy changed during group lookup")
    # All absent/present observations must survive validation of the whole group.
    for path in paths:
        capture.check_file(path)
    capture.check_file(pack_path)
    return result


def read_captured(owner, organ, event_id, capture):
    """Freshly check both representations; never fall through a malformed pack."""
    return read_group_captured(owner, organ, (event_id,), capture)[event_id]
