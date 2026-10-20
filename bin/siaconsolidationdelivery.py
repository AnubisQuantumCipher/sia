"""Experimental owned discovery, live claims and durable execution intent.

No caller acknowledgment can retire a batch. A returned effects attempt is
not completion, publication or settlement. Retirement, legacy migration and
protected authority remain separate integration gates.
"""
import json
import os

import siaconsolidationadmission as admission
import siaconsolidationdiscovery as discovery
import siaconsolidationoutcomes as outcomes
import siaconsolidationsnapshot as snapshot

SCHEMA = "sia-consolidation-delivery-v1"
MAX_BYTES = 1_048_576


def _path(owner):
    return os.path.join(owner.STATE, "consolidation-snapshot-delivery.json")


def _boundary(_stage):
    """Test-only failure injection at returned durable-operation boundaries."""


def _encoded(value):
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("snapshot delivery exceeds its byte bound")
    return text


def _save(owner, value):
    text = _encoded(value)
    owner.ensure_durable_directory(owner.STATE)
    owner.atomic_write(_path(owner), text)


def _record(expected):
    record = admission.canonical(expected)
    if record["phase"] != "admitted":
        raise ValueError("snapshot delivery requires admitted state")
    return record


def _budget(value):
    if isinstance(value, bool) or not isinstance(value, int) \
            or not 1 <= value <= snapshot.MAX_PAGE_ENTRIES:
        raise ValueError("snapshot delivery budget is invalid")
    return value


def _fresh(record):
    return {"schema": SCHEMA, "admission": dict(record), "phase": "scan",
            "cursor": None, "batch": None, "claims": None}


def _days(batch):
    unique = {(item["organ"], item["date"]) for item in batch["result"]["candidates"]}
    return [{"organ": organ, "date": date} for organ, date in sorted(unique)]


def _claim_state(owner, record, batch):
    days = _days(batch)
    if len(days) > owner.MAX_SOURCE_SCAN_ENTRIES:
        raise ValueError("snapshot candidate days exceed the claim-state bound")
    return {"schema": owner.CONSOLIDATION_SCAN_SCHEMA,
            "generation": record["generation"], "phase": "complete",
            "cutoff": record["cutoff"], "queue": [],
            "pending_days": days, "claims": []}


def _validate_claims(owner, record, batch, value):
    claims = owner._canonical_consolidation_scan(value)
    expected = _claim_state(owner, record, batch)
    if dict(claims, claims=[]) != expected or not claims["claims"]:
        raise ValueError("snapshot delivery claims differ from retained batch")
    selected = expected["pending_days"][:owner.MAX_CONSOLIDATION_DAYS_PER_RUN]
    expected_keys = {(day["organ"], day["date"]) for day in selected}
    actual_keys = {(claim["organ"], claim["date"]) for claim in claims["claims"]}
    if actual_keys != expected_keys or len(actual_keys) != len(claims["claims"]):
        raise ValueError("snapshot delivery lacks exact selected claims")
    for claim in claims["claims"]:
        paths = {source["rel"] for source in claim["sources"]}
        required = {item["relative"] for item in batch["result"]["candidates"]
                    if (item["organ"], item["date"]) ==
                    (claim["organ"], claim["date"])}
        if not required <= paths:
            raise ValueError("snapshot delivery candidate is absent from live claim")
    return claims


def _validate(owner, record, value):
    if not isinstance(value, dict) or set(value) != {
            "schema", "admission", "phase", "cursor", "batch", "claims"} \
            or value["schema"] != SCHEMA or value["admission"] != record \
            or not isinstance(value["phase"], str) \
            or value["phase"] not in {
                "scan", "pending", "claimed", "executing",
                "effects-returned", "complete"}:
        raise ValueError("snapshot delivery shape is invalid")
    _encoded(value)
    cursor = value["cursor"]
    if cursor is not None:
        cursor = discovery.canonical(cursor, record)
    if value["phase"] in {"scan", "complete"}:
        if value["batch"] is not None or value["claims"] is not None \
                or (value["phase"] == "complete") != (
                    cursor is not None and cursor["complete"]):
            raise ValueError("snapshot delivery phase is invalid")
    else:
        batch = value["batch"]
        if not isinstance(batch, dict) or set(batch) != {"budget", "result"}:
            raise ValueError("snapshot delivery batch shape is invalid")
        actual = discovery.discover(owner, record, cursor,
                                    budget=_budget(batch["budget"]))
        if not actual["candidates"] or _encoded(batch["result"]) != _encoded(actual):
            raise ValueError("snapshot delivery batch differs from pinned traversal")
        if value["phase"] in {"claimed", "executing", "effects-returned"}:
            _validate_claims(owner, record, batch, value["claims"])
        elif value["claims"] is not None:
            raise ValueError("snapshot pending batch has unexpected claims")
    return dict(value, cursor=cursor)


def _load(owner, record):
    value = owner.read_state_json(
        _path(owner), None, "snapshot delivery", expected_type=dict)
    return _fresh(record) if value is None else _validate(owner, record, value)


def offer(owner, expected, *, budget=32):
    """Persist one page before returning; existing pending work always replays."""
    record, budget = _record(expected), _budget(budget)
    with owner.corpus_owner():
        state = _load(owner, record)
        if state["phase"] in {
                "pending", "claimed", "executing", "effects-returned"}:
            if state["phase"] == "claimed":
                _require_live_sources(owner, state["claims"])
            elif state["phase"] in {"executing", "effects-returned"}:
                owner._claimed_consolidation_paths(state["claims"])
            return state
        result = discovery.discover(owner, record, state["cursor"], budget=budget)
        if result["candidates"]:
            updated = dict(state, phase="pending",
                           batch={"budget": budget, "result": result})
        else:
            updated = dict(state, cursor=result["cursor"],
                           phase="complete" if result["cursor"]["complete"] else "scan")
        _boundary("before-batch-persist")
        _save(owner, updated)
        _boundary("batch-persisted")
        return updated


def _require_live_sources(owner, claims):
    expected = {os.path.join(owner.CORPUS, source["rel"])
                for claim in claims["claims"] for source in claim["sources"]}
    observed = set(owner._claimed_consolidation_paths(claims))
    if observed != expected:
        raise ValueError("snapshot staging requires every source to remain live")


def prepare_claims(owner, expected):
    """Derive live claims from retained candidates, never from a caller ACK."""
    record = _record(expected)
    with owner.corpus_owner():
        state = _load(owner, record)
        if state["phase"] not in {"pending", "claimed"}:
            raise ValueError("snapshot delivery has no pending batch")
        if state["phase"] == "claimed":
            _require_live_sources(owner, state["claims"])
            return state
        claims = _claim_state(owner, record, state["batch"])
        selected = claims["pending_days"][:owner.MAX_CONSOLIDATION_DAYS_PER_RUN]
        claims["claims"] = owner._observe_consolidation_claims(selected,
                                                              record["cutoff"])
        claims = _validate_claims(owner, record, state["batch"], claims)
        _require_live_sources(owner, claims)
        updated = dict(state, phase="claimed", claims=claims)
        _boundary("before-claims-persist")
        _save(owner, updated)
        _boundary("claims-persisted")
        return updated


def _protection(owner):
    """Observe current protection inside the caller's corpus lease."""
    mind = owner.siamind.load_mind()
    windows = owner.siatakes.open_take_evidence_windows()
    pages = owner.siamind.pending_user_pin_slugs() | {
        slug for slug, record in mind.get("nodes", {}).items()
        if isinstance(record, dict) and owner.siamind.is_important(record)}
    return pages, windows


def _check_effect_result(result, claims):
    # These counts describe the attempt; they cannot acknowledge sources.
    limit = len(claims["claims"])
    if not isinstance(result, tuple) or len(result) != 3 \
            or any(isinstance(value, bool) or not isinstance(value, int)
                   or not 0 <= value <= limit for value in result):
        raise ValueError("snapshot executor returned invalid attempt counts")


def execute_claims(owner, expected):
    """Persist intent before effects; retain all work until qualified retirement.

    `effects-returned` records only successful return of this attempt. Protected,
    capacity-limited or otherwise retained sources can remain. Caller-provided
    counts or acknowledgments cannot create that transition.
    """
    record = _record(expected)
    with owner.corpus_owner():
        state = _load(owner, record)
        if state["phase"] == "effects-returned":
            owner._claimed_consolidation_paths(state["claims"])
            return state
        if state["phase"] not in {"claimed", "executing"}:
            raise ValueError("snapshot delivery has no executable claims")
        # Check the longer final phase's encoded size before effects.
        _encoded(dict(state, phase="effects-returned"))
        if state["phase"] == "claimed":
            _require_live_sources(owner, state["claims"])
        else:
            owner._claimed_consolidation_paths(state["claims"])
        if owner.corpus_commit("pre-consolidation") not in {"committed", "clean"}:
            raise RuntimeError("pre-consolidation corpus git commit failed")
        pages, windows = _protection(owner)
        if state["phase"] == "claimed":
            state = dict(state, phase="executing")
            _boundary("before-execution-persist")
            _save(owner, state)
            _boundary("execution-persisted")
        result = owner._execute_consolidation_claims(
            state["claims"], record["cutoff"], pages, windows)
        _check_effect_result(result, state["claims"])
        _boundary("effects-returned")
        updated = dict(state, phase="effects-returned")
        _save(owner, updated)
        _boundary("effects-persisted")
        return updated


def inspect_outcomes(owner, expected):
    """Recheck selected source outcomes without accepting a caller's receipt."""
    record = _record(expected)
    with owner.corpus_owner():
        state = _load(owner, record)
        if state["phase"] != "effects-returned":
            raise ValueError("snapshot effects have not returned")
        observed = outcomes.inspect_claims(owner, record, state["claims"])
        selected = {(item["organ"], item["date"]) for item in observed}
        unclaimed = [day for day in _days(state["batch"])
                     if (day["organ"], day["date"]) not in selected]
        result = {"schema": "sia-consolidation-outcomes-v1",
                  "admission": record, "coverage": "selected-claims-only",
                  "outcomes": observed, "unclaimed_days": unclaimed}
        _encoded(result)
        return result
