"""Experimental captured legacy fallback writer, not publication authority.

No runtime imports this module. Callers must hold the corpus lease and obtain
protected authorization before any future integration. This adapter neither
publishes packs nor retires sources, acknowledges work, or proves durability.
An exception can follow a write; retained operation intent is still required.
"""

import os

import siaeventpackreader as reader
import siaeventplan as plan


POLICIES = ("MAX_EVENT_INDEX_RECORDS", "MAX_EVENT_INDEX_BYTES", "MAX_STATE_JSON_BYTES")


def _policies(owner):
    values = tuple(owner[name] for name in POLICIES)
    if any(type(value) is not int or value <= 0 for value in values):
        raise ValueError("event index delta policy is invalid")
    return values


def _current(owner, policy):
    if _policies(owner) != policy:
        raise ValueError("event index delta policy changed")
    if owner["_CORPUS_OWNER_DEPTH"].get() <= 0:
        raise ValueError("event index delta requires the corpus lease")


def _inputs(owner, organ, records, policy):
    if type(organ) is not str or not 1 <= len(organ) <= 200 \
            or type(records) is not tuple or len(records) > policy[0]:
        raise ValueError("event index delta request is invalid")
    owner["_event_index_relative"](organ, "0" * 64)
    previous, amount = "", 4096
    for record in records:
        if type(record) is not tuple or len(record) != 2:
            raise ValueError("event index delta record shape is invalid")
        identifier, raw = record
        if type(identifier) is not str or identifier <= previous \
                or type(raw) is not bytes or not 1 <= len(raw) <= policy[1]:
            raise ValueError("event index delta record is invalid")
        owner["_event_index_relative"](organ, identifier)
        amount += 2048 + 4 * len(raw)
        if amount > policy[2]:
            raise ValueError("event index delta request exceeds byte capacity")
        previous = identifier
    return amount


def _expected(owner, organ, identifier, raw, capture):
    return owner["_validate_event_index_raw"](
        raw, organ, identifier, dependency_capture=capture)


def _preflight(owner, organ, records, capture):
    expected = {identifier: _expected(owner, organ, identifier, raw, capture)
                for identifier, raw in records}
    raw_by_id = dict(records)
    images, scanned = {}, set()
    for identifier, existing in reader.iter_roster_captured(
            owner, organ, tuple(expected), capture):
        if existing is not None and existing != expected[identifier]:
            raise ValueError("event identity conflicts with durable consolidation index")
        if existing is None:
            relative = owner["_event_index_relative"](organ, identifier)
            images[relative] = {"raw": raw_by_id[identifier], "page": {"write": True}}
            for parent in plan._ancestors(relative):
                if parent not in scanned:
                    capture.directory_snapshot(capture.path(parent))
                    scanned.add(parent)
    return images


def _fresh(owner, organ, identifier, raw, capture, policy):
    _current(owner, policy)
    expected = _expected(owner, organ, identifier, raw, capture)
    existing = reader.read_captured(owner, organ, identifier, capture)
    if existing is not None and existing != expected:
        raise ValueError("event identity conflicts with durable consolidation index")
    _current(owner, policy)
    capture.current()
    _current(owner, policy)


def _refresh(owner, deps, images, state, required, budget, *, files, directories):
    old = state["live"]
    old.current(exempt_files=files, exempt_directories=directories)
    new, targets = plan._observe_closure(
        owner, deps, images, required, budget=budget, allow_directory_entry_deltas=True)
    plan._replace_capture(state, new, targets, files=files, directories=directories)


def _write(owner, organ, record, deps, images, state, budget, policy):
    identifier, raw = record
    relative = owner["_event_index_relative"](organ, identifier)
    if relative not in images:
        return
    _fresh(owner, organ, identifier, raw, state["live"], policy)
    owner["_before_corpus_mutation"]()
    _fresh(owner, organ, identifier, raw, state["live"], policy)
    path = state["live"].path(relative)
    owner["ensure_durable_directory"](os.path.dirname(path))
    directories = frozenset(plan._ancestors(relative))
    _refresh(owner, deps, images, state, state["targets"], budget,
             files=frozenset(), directories=directories)
    _fresh(owner, organ, identifier, raw, state["live"], policy)
    owner["atomic_write"](path, raw.decode("utf-8", errors="strict"))
    _refresh(owner, deps, images, state, state["targets"] | {relative}, budget,
             files=frozenset({relative}), directories=directories)
    _fresh(owner, organ, identifier, raw, state["live"], policy)


def publish_legacy_fallbacks(owner, *, organ, records):
    """Observe exact fallback bytes; return written paths, never readiness.

    Input records are an immutable sorted tuple of (native str ID, native bytes).
    Current canonical/epoch validation is necessary, not proof of original
    payload truth or permission. The original caller must establish both.
    """
    policy = _policies(owner)
    _current(owner, policy)
    amount = _inputs(owner, organ, records, policy)
    budget = plan._Budget(owner, amount)
    capture = plan._Capture(owner, budget)
    state = {"live": capture, "targets": set(), "retired": None}
    try:
        images = _preflight(owner, organ, records, capture)
        deps = capture.dependencies()
        _current(owner, policy)
        capture.current()
        for record in records:
            _write(owner, organ, record, deps, images, state, budget, policy)
        _current(owner, policy)
        state["live"].current()
        _current(owner, policy)
        return tuple(images)
    finally:
        plan._close_state(state)
