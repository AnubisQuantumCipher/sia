"""Experimental snapshot admission journal; not a publication authority.

Caller bindings remain observations, not authenticated source evidence.
The installed recovery path does not use this module.
"""
import datetime
import json
import os
import re

import siaconsolidationsnapshot as snapshot

SCHEMA = "sia-consolidation-snapshot-admission-v1"


def canonical(value):
    fields = {"schema", "generation", "transaction", "cutoff", "commit", "phase"}
    if not isinstance(value, dict) or set(value) != fields \
            or value.get("schema") != SCHEMA \
            or not isinstance(value.get("phase"), str) \
            or value.get("phase") not in {"planned", "admitted"}:
        raise ValueError("snapshot admission shape is invalid")
    for field, width in (("generation", 32), ("transaction", 64)):
        if not isinstance(value[field], str) \
                or re.fullmatch("[0-9a-f]{" + str(width) + "}", value[field]) is None:
            raise ValueError("snapshot admission identity is invalid")
    snapshot.object_id(value["commit"])
    cutoff = value["cutoff"]
    if not isinstance(cutoff, str) or len(cutoff) != 10:
        raise ValueError("snapshot admission cutoff is invalid")
    try:
        if datetime.date.fromisoformat(cutoff).isoformat() != cutoff:
            raise ValueError
    except ValueError:
        raise ValueError("snapshot admission cutoff is invalid") from None
    return dict(value)


def _path(owner):
    return os.path.join(owner.STATE, "consolidation-snapshot-admission.json")


def _save(owner, record):
    text = json.dumps(canonical(record), sort_keys=True, separators=(",", ":"))
    if len(text.encode("utf-8")) > 4096:
        raise ValueError("snapshot admission exceeds its byte bound")
    owner.ensure_durable_directory(owner.STATE)
    owner.atomic_write(_path(owner), text)


def _boundary(_stage):
    """Test-only crash injection seam; production execution has no hook."""


def admit(owner, *, generation, transaction, cutoff, commit):
    """Resume only exact planned work; admitted missing pins refuse."""
    requested = canonical({
        "schema": SCHEMA, "generation": generation, "transaction": transaction,
        "cutoff": cutoff, "commit": commit, "phase": "planned"})
    with owner.corpus_owner():
        current = owner.read_state_json(
            _path(owner), None, "snapshot admission", expected_type=dict)
        if current is None:
            _save(owner, requested)
            current = requested
            _boundary("planned-persisted")
        else:
            current = canonical(current)
            if dict(current, phase="planned") != requested:
                raise ValueError("snapshot admission conflicts with retained request")
        run = owner._run_bounded_text_process
        if current["phase"] == "planned":
            snapshot.pin_commit(run, owner.CORPUS, generation, commit)
            _boundary("pin-retained")
            current = dict(current, phase="admitted")
            _save(owner, current)
            _boundary("admission-persisted")
        snapshot.check_pin(run, owner.CORPUS, generation, commit)
        return current
