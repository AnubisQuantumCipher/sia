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


def _roster(owner, organ, identifiers):
    limit = owner["MAX_EVENT_INDEX_RECORDS"]
    if type(limit) is not int or limit <= 0 or type(identifiers) is not tuple \
            or len(identifiers) > limit:
        raise ValueError("event index roster exceeds its identity bound")
    previous = ""
    for identifier in identifiers:
        if type(identifier) is not str or identifier <= previous:
            raise ValueError("event index roster order is invalid")
        owner["_event_index_relative"](organ, identifier)
        previous = identifier
    return limit


def iter_roster_captured(owner, organ, identifiers, capture):
    """Yield the complete bounded roster; caller must exhaust or refuse it.

    One capture is shared across every group. Partial iteration is not a
    complete result and grants no authority. No observations are retired here.
    """
    limit = _roster(owner, organ, identifiers)
    start = 0
    for end in range(1, len(identifiers) + 1):
        boundary = (end == len(identifiers)
                    or end - start == siaeventpack.MAX_RECORDS
                    or identifiers[end][:3] != identifiers[start][:3])
        if boundary:
            group = identifiers[start:end]
            rows = read_group_captured(owner, organ, group, capture)
            for identifier in group:
                if owner["MAX_EVENT_INDEX_RECORDS"] != limit:
                    raise ValueError("event index identity policy changed during lookup")
                yield identifier, rows[identifier]
            start = end
    if owner["MAX_EVENT_INDEX_RECORDS"] != limit:
        raise ValueError("event index identity policy changed during lookup")


def _found_snapshot(found, maximum):
    if type(found) is not dict or len(found) > maximum:
        raise ValueError("event occurrence result shape is invalid")
    for key, value in found.items():
        if type(key) is not str or type(value) is not tuple or len(value) != 3 \
                or any(type(part) is not str and part is not None for part in value):
            raise ValueError("event occurrence result entry is invalid")
    return found.copy()


def join_occurrences_captured(owner, organ, wanted, found, capture):
    """Experimental join for an already bounded occurrence-request owner."""
    if type(wanted) is not set and type(wanted) is not frozenset:
        raise ValueError("event occurrence roster shape is invalid")
    limit = owner["MAX_EVENT_INDEX_RECORDS"]
    if type(limit) is not int or limit <= 0 or len(wanted) > limit:
        raise ValueError("event occurrence lookup exceeds its identity bound")
    # Reject subclasses before sorted() can dispatch attacker-supplied comparisons.
    if any(type(identifier) is not str for identifier in wanted):
        raise ValueError("event occurrence identity type is invalid")
    identifiers = tuple(sorted(wanted))
    original_found = _found_snapshot(found, limit)
    if not found.keys() <= wanted:
        raise ValueError("event occurrence result exceeds request scope")
    additions, missing = {}, set()
    for identifier, entry in iter_roster_captured(owner, organ, identifiers, capture):
        if entry is None:
            missing.add(identifier)
        elif identifier in found:
            raise ValueError("event identity occurs in live and consolidated evidence")
        else:
            additions[identifier] = (entry["epoch_slug"], entry["payload_sha256"],
                                      entry["semantic_id"])
    if len(wanted) != len(identifiers) \
            or any(type(identifier) is not str for identifier in wanted) \
            or wanted != frozenset(identifiers) \
            or _found_snapshot(found, limit) != original_found:
        raise ValueError("event occurrence input changed during lookup")
    # Commit the local result only after every group has succeeded.
    found.update(additions)
    return missing
