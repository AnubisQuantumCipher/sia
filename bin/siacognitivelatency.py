"""Prepare conditional latency arithmetic over replayed bound observations.

The frozen retrieval policy and measurement artifact are unchanged. This module
does not open source files, rerun an engine, invoke JACKAL, calculate means, or
convert units. It emits exact-expression requests over explicitly supplied JSON
number representations; later arithmetic assurance cannot authenticate those
measurements or establish physical-clock accuracy.

Only the raw adapter's per-query embedding/search spans are class-mean inputs.
Its capture/query operation totals stay separate. Model startup, warmup,
preparation and controller wall timing are not reported by the bound producer;
similarly named optional diagnostics are retained without being adopted.
"""

import json
import math
import re

import siacognitivemeasure as measurement


MAX_ARTIFACT_BYTES = measurement.MAX_ARTIFACT_BYTES
NON_CLAIMS = [
    "This plan contains unevaluated JACKAL requests, not arithmetic assurance, physical-clock accuracy, significance, or a cognitive win.",
    "Eventual exact arithmetic is conditional on supplied shortest-roundtrip JSON number text; it does not authenticate original wire tokens or physical durations.",
    "Embedding spans include vector validation and byte preparation; search spans include row normalization and canonical-row byte binding.",
    "Adapter operation totals include connection, snapshots, query loop and receipt work; they exclude prior request admission and later engine close.",
    "Operation totals are not per-query totals and are never allocated across queries or classes.",
    "The bound producer does not report per-query total, owned-model startup or warmup, preparation duration, or controller wall duration.",
    "Uncontracted diagnostic durations and unbound-controller wall measurements are retained but are not admitted latency samples.",
    "Class means use the same selected query roster, including zero samples; group dependence and shared pages do not establish independent sampling or statistical power.",
    "Source origins and model/build lineage are preserved; raw timing lineage does not establish CPU, model, machine, or cognitive comparisons.",
    "A pinned latency policy in the heldout parameter freeze declares chronology but does not independently prove when policy selection or result inspection occurred.",
    "Unavailable timing scopes and query classes are not assigned zero durations or fabricated component breakdowns.",
    "All retained measurement, retrieval, source, baseline, model, build, and raw-adapter nonclaims remain controlling.",
]
TIMING_CONTRACT = {
    "schema": "sia-raw-vector-timing-scope-v1",
    "producer": "raw-vector/adapter.ts:runRawVector", "clock": "performance.now", "unit": "ms",
    "query_embedding": "embed-start-through-validation-and-vector-bytes-before-search",
    "query_search": "search-start-through-normalization-and-row-byte-binding",
    "operation_total": "post-admission-through-connect-snapshots-query-loop-receipt-before-close",
}
UNAVAILABLE = [
    {"scope": "query", "component": "total", "reason": "not-reported-by-adapter-query-v1"},
    {"scope": "owned-model", "component": "startup", "reason": "not-reported-by-bound-model-v1"},
    {"scope": "owned-model", "component": "warmup", "reason": "not-reported-by-bound-model-v1"},
    {"scope": "preparation", "component": "total", "reason": "not-reported-by-bound-preparer-v1"},
    {"scope": "controller", "component": "wall", "reason": "not-reported-by-bound-controller-v1"},
]
_POLICY = {
    "schema": "sia-cognitive-latency-policy-v1",
    "samples": "adapter-query-embedding-search-v1",
    "aggregation": "macro-query-within-class-v1",
    "numbers": "retained-json-roundtrip-decimal-as-given-v1",
    "units": "producer-ms-no-conversion-v1",
    "roster": "same-admitted-query-roster-v1",
    "missing": "refuse-sample-drop-v1",
    "operation_timings": "retain-separate-no-query-allocation-v1",
    "chronology": "externally-pinned-before-heldout-v1",
}
_REPLAY_KEYS = {
    *measurement._SOURCE_KEYS, "protocol", "expected_protocol_sha256", "baseline", "expected_baseline_sha256",
    "expected_parameter_freeze_sha256",
}
_NUMBER = re.compile(r"(-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?)(?:[eE]([+-]?[0-9]+))?")


class LatencyRefusal(ValueError):
    """The independently pinned policy, replay, or given samples were refused."""


def _fail(reason):
    error = LatencyRefusal("cognitive latency refused: " + reason)
    error.non_claims = list(NON_CLAIMS)
    raise error


def _keys(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        _fail(label + " fields are invalid")


def _admit(kw):
    # Bound every complete input before any copying or JSON serialization. A
    # late malformed policy must not trigger eager work on an earlier baseline.
    measurement._bounded_inputs(kw.values())
    _keys(kw["latency_policy"], _POLICY, "latency policy")
    if any(type(kw["latency_policy"][key]) is not str or kw["latency_policy"][key] != expected
           for key, expected in _POLICY.items()):
        _fail("latency policy changes a frozen sampling, unit or aggregation rule")
    measurement._pin(kw["latency_policy"], kw["expected_latency_policy_sha256"])
    _keys(kw["replay_inputs"], _REPLAY_KEYS, "complete measurement replay inputs")
    measurement._pin(kw["measurement_plan"], kw["expected_measurement_plan_sha256"], "plan_sha256")
    # Selfhashes cannot admit modified answer keys, raw timings, source labels,
    # query rosters or arithmetic requests. Recompute the entire source-bound
    # retrieval plan using the existing independent caller pin contract.
    replayed = measurement.prepare_measurement(**kw["replay_inputs"])
    if not measurement._same(replayed, kw["measurement_plan"]):
        _fail("retained measurement plan differs from complete source and baseline replay")
    if replayed["split"] == "heldout":
        freeze = replayed["baseline"]["parameter_freeze"]
        if freeze["parameters"].get("latency_policy_sha256") != kw["expected_latency_policy_sha256"]:
            _fail("heldout parameter freeze does not name the independently pinned latency policy")
    return replayed


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        _fail("reported timing is not a finite nonnegative strict JSON number")
    # JSON spelling preserves integer/float identity and negative zero. It is
    # the retained Python JSON representation, not the original TS stdout token
    # or a claim that decimal digits are exact physical measurements.
    token = json.dumps(value, allow_nan=False)
    match = _NUMBER.fullmatch(token)
    if match is None:
        _fail("reported timing has no admitted numeric transcription")
    mantissa, exponent = match.groups()
    if exponent is None:
        return token, token
    # Syntactic scientific-notation transcription only: never evaluate a power,
    # multiply a binary float, or locally convert the producer's milliseconds.
    digits = exponent.lstrip("+-").lstrip("0") or "0"
    sign = "-" if exponent.startswith("-") and digits != "0" else ""
    return token, "(" + mantissa + "*10^(" + sign + digits + "))"


def _sample(value, baseline_sha256, pointer):
    token, literal = _number(value)
    return {
        "unit": "ms", "value": value, "json_number": token, "expression_literal": literal,
        "given": {"baseline_sha256": baseline_sha256, "source_pointer": pointer,
                  "representation": "retained-json-number-shortest-roundtrip-v1", "unit": "ms"},
    }


def _samples(plan):
    baseline = plan["baseline"]
    baseline_sha = plan["baseline_sha256"]
    observations = baseline["observation"]
    metadata = {row["id"]: row for row in plan["queries"]}
    query_samples = []
    for index, row in enumerate(observations["query"]["payload"]["results"]):
        query = metadata[row["id"]]
        for component in ("embedding", "search"):
            query_samples.append({
                "query_id": row["id"], "class": query["class"], "group_id": query["group_id"],
                "component": component,
                **_sample(row["latency_ms"][component], baseline_sha,
                          f"/observation/query/payload/results/{index}/latency_ms/{component}"),
            })
    operation_samples = []
    for operation in ("capture", "query"):
        operation_samples.append({
            "operation": operation, "component": "total",
            **_sample(observations[operation]["payload"]["latency_ms"]["total"], baseline_sha,
                      f"/observation/{operation}/payload/latency_ms/total"),
        })
    return query_samples, operation_samples


def _requests(classes, samples):
    requests = []
    for klass in classes:
        identifiers = klass["query_ids"]
        if not identifiers:
            # Missing/unsupported query classes retain their declared reason;
            # no zero-valued observation or undefined mean is constructed.
            continue
        for component in ("embedding", "search"):
            given = [row for row in samples if row["class"] == klass["class"] and row["component"] == component]
            if [row["query_id"] for row in given] != identifiers \
                    or sorted({row["group_id"] for row in given}) != klass["group_ids"]:
                _fail("latency samples do not cover the exact measured query and group roster")
            expression = "(" + "+".join("(" + row["expression_literal"] + ")" for row in given) \
                         + ")/" + str(len(given))
            requests.append({
                "tool": "jackal_exact", "arguments": {"expression": expression},
                "scope": {"kind": "class", "id": klass["class"]},
                "metric": "mean_" + component + "_ms", "unit": "ms",
                "query_ids": identifiers, "group_ids": klass["group_ids"], "given": given,
            })
    return requests


def _prepare(kw):
    plan = _admit(kw)
    query_samples, operation_samples = _samples(plan)
    requests = _requests(plan["classes"], query_samples)
    return measurement._finish({
        "schema": "sia-cognitive-latency-plan-v1", "status": "prepared-for-jackal",
        "arithmetic_status": "not-evaluated",
        **{key: plan[key] for key in (
            "capture_sha256", "policy_sha256", "selection_sha256", "pages_sha256", "metric_policy_sha256",
            "baseline_contract_sha256", "protocol_sha256", "baseline_sha256", "query_roster_sha256",
            "split", "parameter_freeze_sha256")},
        "measurement_plan_sha256": kw["expected_measurement_plan_sha256"],
        "latency_policy_sha256": kw["expected_latency_policy_sha256"], "latency_policy": kw["latency_policy"],
        "measurement_plan": plan, "timing_contract": TIMING_CONTRACT,
        "query_samples": query_samples, "operation_samples": operation_samples,
        "classes": plan["classes"], "unavailable": UNAVAILABLE, "jackal_requests": requests,
        "source_non_claims": {"measurement": plan["non_claims"], "history": plan["source_non_claims"]},
        "non_claims": list(NON_CLAIMS),
    }, "plan_sha256")


def prepare_latency(*, measurement_plan, expected_measurement_plan_sha256, replay_inputs,
                    latency_policy, expected_latency_policy_sha256):
    """Return a detached plan of unevaluated requests over caller-pinned given samples."""
    try:
        return _prepare(locals())
    except LatencyRefusal:
        raise
    except (measurement.baseline_module.BaselineRefusal, ValueError, TypeError, KeyError,
            IndexError, OverflowError, RecursionError) as exc:
        error = LatencyRefusal("cognitive latency could not be admitted: " + str(exc))
        error.non_claims = list(NON_CLAIMS)
        raise error from exc
