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


def _packed_entry(owner, capture, raw, organ, event_id):
    selected = None
    selected_raw = None
    if raw is not None:
        for key, value in siaeventpack.decode(raw, organ, event_id[:3]):
            identifier = key.decode("ascii")
            entry = owner["_validate_event_index_raw"](
                value, organ, identifier, dependency_capture=capture)
            if identifier == event_id:
                selected, selected_raw = entry, value
    return selected, selected_raw


def read_captured(owner, organ, event_id, capture):
    """Freshly check both representations; never fall through a malformed pack."""
    relative = owner["_event_index_relative"](organ, event_id)
    legacy_path = os.path.join(owner["CORPUS"], relative)
    pack_path = os.path.join(owner["CORPUS"], "event-packs", organ,
                             event_id[:2], event_id[:3] + ".siaep")
    legacy_raw = _optional(capture, legacy_path, owner["MAX_EVENT_INDEX_BYTES"])
    pack_raw = _optional(capture, pack_path, siaeventpack.MAX_BYTES)
    entry, selected_raw = _packed_entry(owner, capture, pack_raw, organ, event_id)
    if legacy_raw is not None:
        legacy = owner["_validate_event_index_raw"](
            legacy_raw, organ, event_id, dependency_capture=capture)
        if selected_raw is not None and selected_raw != legacy_raw:
            raise ValueError("event index representations conflict")
        entry = legacy
    # Absence is an observation too: publication during validation must refuse.
    capture.check_file(legacy_path)
    capture.check_file(pack_path)
    return entry
