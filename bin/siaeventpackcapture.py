"""Unactivated source-bound pack planning; no writes or effect authority.

The caller owns the existing live capture and corpus lease. A result covers the
declared selection and preserves the prior pack; it is not a corpus inventory,
durable intent, source-authenticity proof or permission to retire legacy files.
"""

import os

import siaeventpack as codec
import siaeventpackplan as planner
import siaeventpackreader as reader
import siaeventplan as capture_module


POLICIES = ("MAX_EVENT_INDEX_RECORDS", "MAX_EVENT_INDEX_BYTES", "MAX_STATE_JSON_BYTES",
            "MAX_EPOCH_SOURCE_RECORDS", "MAX_EPOCH_EVENT_IDS",
            "MAX_EPOCH_SOURCE_MANIFEST_BYTES", "MAX_EPOCH_PAGE_BYTES", "MAX_EVENT_PAGE_BYTES")


def _policies(owner):
    values = tuple(owner[name] for name in POLICIES)
    if any(type(value) is not int or value <= 0 for value in values):
        raise ValueError("event pack capture policy is invalid")
    planner._limits(values[:3])
    return values


def _current(owner, capture, policy):
    if _policies(owner) != policy:
        raise ValueError("event pack capture policy changed")
    if owner["_CORPUS_OWNER_DEPTH"].get() <= 0:
        raise ValueError("event pack capture requires the corpus lease")
    if type(capture) is not capture_module._Capture or capture.owner is not owner \
            or capture.root != os.path.abspath(owner["CORPUS"]) \
            or capture.budget.limit != policy[2] or capture.root_fd is None:
        raise ValueError("event pack capture owner mismatch")
    capture.budget.check()


def _selection(owner, organ, prefix, identifiers, policy):
    codec.header_size(organ, prefix)
    if type(identifiers) is not tuple or len(identifiers) > policy[0]:
        raise ValueError("event pack capture selection capacity")
    previous = ""
    for identifier in identifiers:
        if type(identifier) is not str or len(identifier) != 64 \
                or identifier <= previous or identifier[:3] != prefix:
            raise ValueError("event pack capture selection identity")
        owner["_event_index_relative"](organ, identifier)
        previous = identifier


def _legacy(owner, organ, identifier, capture, policy):
    path = capture.path(owner["_event_index_relative"](organ, identifier))
    raw = reader._optional(capture, path, policy[1])
    if raw is not None:
        owner["_validate_event_index_raw"](
            raw, organ, identifier, dependency_capture=capture)
    return raw


def _prior(owner, organ, prefix, capture, policy):
    path = capture.path("/".join(("event-packs", organ, prefix[:2], prefix + ".siaep")))
    raw = reader._optional(capture, path, codec.MAX_BYTES)
    rows = reader._packed_entries(owner, capture, raw, organ, prefix)
    # Even unselected prior entries must agree with an existing legacy copy.
    for identifier, (_entry, packed) in rows.items():
        legacy = _legacy(owner, organ, identifier, capture, policy)
        if legacy is not None and legacy != packed:
            raise ValueError("event index representations conflict")
    return raw, rows


def _records(owner, organ, identifiers, capture, policy, prior):
    records = []
    for identifier in identifiers:
        raw = _legacy(owner, organ, identifier, capture, policy)
        packed = prior.get(identifier)
        if packed is not None:
            if raw is not None and raw != packed[1]:
                raise ValueError("event index representations conflict")
            raw = packed[1]
        if raw is None:
            raise ValueError("event pack capture selected record missing")
        records.append((identifier.encode("ascii"), raw))
    return tuple(records)


def prepare_captured(owner, *, organ, prefix, identifiers, capture):
    """Return the planner's exact partition under one retained source capture.

    Each organ/prefix may be attempted once in this capture. Its reservation
    remains after failure; callers must not reset the whole-operation budget.
    Capture ownership stays with the caller on success and failure. Validate
    again at any later use: this observation is neither atomic nor perpetual.
    """
    policy = _policies(owner)
    _current(owner, capture, policy)
    _selection(owner, organ, prefix, identifiers, policy)
    key = ("event-pack-plan", organ, prefix)
    if key in capture.budget.items:
        raise ValueError("event pack prefix already attempted in capture")
    # Logical result/envelope reservation. CPython allocator overhead is unproved.
    capture.budget.reserve(key, 4096 + codec.MAX_BYTES + 2048 * len(identifiers))
    prior_raw, prior = _prior(owner, organ, prefix, capture, policy)
    records = _records(owner, organ, identifiers, capture, policy, prior)
    _current(owner, capture, policy)
    result = planner.plan(organ, prefix, records, prior_raw, limits=policy[:3])
    _current(owner, capture, policy)
    capture.current()
    _current(owner, capture, policy)
    return result
