"""Retain exact selected originals before effects; no retirement authority.

Caller owns the corpus lease and validated delivery. The journal and Git
references provide cooperative recovery, not hostile same-user isolation.
"""
import hashlib
import json
import os
import re

import siaconsolidationadmission as admission
import siaconsolidationoutcomes as outcomes
import siaconsolidationsnapshot as snapshot

SCHEMA = "sia-consolidation-originals-v1"
MAX_BINDING_BYTES = 1_048_576
MAX_RECORD_BYTES = 4096


def _encoded(value, limit):
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(text.encode("utf-8")) > limit:
        raise ValueError("consolidation originals exceed their byte bound")
    return text


def _binding(owner, record, claims):
    record = admission.canonical(record)
    claims = owner._canonical_consolidation_scan(claims)
    if record["phase"] != "admitted" or claims["phase"] != "complete" \
            or claims["generation"] != record["generation"] \
            or claims["cutoff"] != record["cutoff"] or not claims["claims"]:
        raise ValueError("consolidation originals lack exact admitted claims")
    text = _encoded({"admission": record, "claims": claims}, MAX_BINDING_BYTES)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value, binding):
    if not isinstance(value, dict) or set(value) != {
            "schema", "binding", "commit", "phase"} \
            or value["schema"] != SCHEMA or value["binding"] != binding \
            or not isinstance(value["phase"], str) \
            or value["phase"] not in {"planned", "retained"}:
        raise ValueError("consolidation originals conflict with retained claims")
    snapshot.object_id(value["commit"])
    _encoded(value, MAX_RECORD_BYTES)
    return dict(value)


def _path(owner):
    return os.path.join(owner.STATE, "consolidation-originals.json")


def _load(owner, binding):
    value = owner.read_state_json(
        _path(owner), None, "consolidation originals", expected_type=dict)
    return None if value is None else _canonical(value, binding)


def _save(owner, value):
    text = _encoded(_canonical(value, value["binding"]), MAX_RECORD_BYTES)
    owner.ensure_durable_directory(owner.STATE)
    owner.atomic_write(_path(owner), text)


def _name(binding):
    if not isinstance(binding, str) or re.fullmatch("[0-9a-f]{64}", binding) is None:
        raise ValueError("consolidation originals binding is invalid")
    return "refs/sia/consolidation-originals/" + binding


def _verify_sources(owner, value, claims):
    snapshot.commit_tree(owner._run_bounded_text_process,
                         owner.CORPUS, value["commit"])
    for claim in claims["claims"]:
        for source in claim["sources"]:
            if outcomes._committed_text(owner, value["commit"], source) is None:
                raise ValueError("retained commit lacks exact claimed original")


def _check(owner, value, claims):
    name = _name(value["binding"])
    if snapshot._pin_value(owner._run_bounded_text_process,
                           owner.CORPUS, name) != value["commit"]:
        raise ValueError("retained originals pin is missing or differs")
    _verify_sources(owner, value, claims)
    return dict(value)


def _pin(owner, value, claims):
    _verify_sources(owner, value, claims)
    run, name = owner._run_bounded_text_process, _name(value["binding"])
    current = snapshot._pin_value(run, owner.CORPUS, name)
    if current is not None and current != value["commit"]:
        raise ValueError("originals binding is already pinned differently")
    if current is None:
        result = snapshot._git(run, owner.CORPUS, [
            "update-ref", "--no-deref", name, value["commit"],
            "0" * len(value["commit"])], 1024)
        if result.returncode != 0:
            raise ValueError("originals pin creation failed")
    _check(owner, value, claims)


def _boundary(_stage):
    """Test-only crash seam at returned durable-operation boundaries."""


def retain(owner, record, claims):
    """Plan, pin, then retain; caller must precommit while all claims are live."""
    binding = _binding(owner, record, claims)
    value = _load(owner, binding)
    if value is None:
        result = snapshot._git(owner._run_bounded_text_process, owner.CORPUS,
                               ["rev-parse", "--verify", "HEAD^{commit}"], 1024)
        if result.returncode != 0:
            raise ValueError("originals precommit identity is unavailable")
        value = _canonical({
            "schema": SCHEMA, "binding": binding,
            "commit": result.stdout.rstrip("\n"), "phase": "planned"}, binding)
        _verify_sources(owner, value, claims)
        _save(owner, value)
        _boundary("originals-planned")
    if value["phase"] == "planned":
        _pin(owner, value, claims)
        _boundary("originals-pinned")
        value = dict(value, phase="retained")
        _save(owner, value)
        _boundary("originals-retained")
    return _check(owner, value, claims)


def check(owner, record, claims):
    """Require already retained originals; never create or replace a lost pin."""
    value = _load(owner, _binding(owner, record, claims))
    if value is None or value["phase"] != "retained":
        raise ValueError("consolidation originals are not retained")
    return _check(owner, value, claims)
