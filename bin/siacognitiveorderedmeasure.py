"""Measure pinned row permutations without rewriting any raw observation.

The exposure component independently replays the complete raw measurement.
This adapter then permutes that replay's native-target hit records and shares
the existing cutoff/class expression builder. It never changes target rules,
admission of raw score order, source text/origin, latency, or parameter choice.
It emits unevaluated requests, not a retrieval result or mathematical assurance.
"""

import copy

import siacognitiveexposure as exposure_module
import siacognitivemeasure as measurement


MAX_INPUT_BYTES = measurement.MAX_ARTIFACT_BYTES
MAX_OUTPUT_BYTES = measurement.MAX_ARTIFACT_BYTES
MAX_QUERIES = measurement.baseline_module.raw_admission.MAX_QUERIES
ARMS = ("raw-original", "cue-only", "cue-event-exposure")
NON_CLAIMS = [
    "This plan contains unevaluated JACKAL expressions, not arithmetic assurance, significance, or a cognitive win.",
    "Ordered arms reuse independently replayed exact native-target coverage; they do not change relevance, candidate membership, source origins, or raw adapter observations.",
    "Raw-original summaries must match the complete original measurement; all fixed ablations and empty-candidate queries remain represented.",
    "Event-exposure computation remains computed-unverified and is not a JACKAL assurance class or an earned cognitive mechanism.",
    "This adapter does not select a grid member, tune an objective, evaluate a metric, or authorize heldout parameter changes.",
    "Heldout freeze pins declare calibration-only selection chronology but do not independently prove when tuning or result inspection occurred.",
    "Raw latency observations remain unchanged and belong to the original retrieval run; no rerank duration or comparative latency was measured.",
    "All complete exposure, raw measurement, source, baseline, model, build, activation, and protocol nonclaims remain controlling.",
]
_POLICY = {
    "schema": "sia-cognitive-ordered-measurement-policy-v1",
    "exposure_schema": "sia-cognitive-event-exposure-v1",
    "ordering": "replayed-row-reference-bijection-v1",
    "targets": "replayed-raw-native-occurrence-coverage-v1",
    "queries": "complete-observed-split-roster-v1",
    "summaries": "frozen-retrieval-policy-cutoffs-and-class-means-v1",
    "latencies": "retain-raw-no-rerank-timing-v1",
}
_RESOURCES = {"max_input_bytes": MAX_INPUT_BYTES, "max_output_bytes": MAX_OUTPUT_BYTES,
              "max_queries": MAX_QUERIES}
_EXPOSURE_INPUTS = {
    "measurement_plan", "expected_measurement_plan_sha256", "replay_inputs", "rerank_policy",
    "expected_rerank_policy_sha256", "activation_policy", "expected_activation_policy_sha256",
}
_SOURCE_FIELDS = (
    "capture_sha256", "policy_sha256", "selection_sha256", "pages_sha256",
    "metric_policy_sha256", "baseline_contract_sha256", "protocol_sha256", "baseline_sha256",
    "query_roster_sha256", "split", "parameter_freeze_sha256",
)
_EXPOSURE_FIELDS = (
    "measurement_plan_sha256", "rerank_policy_sha256", "activation_grid_sha256", "activation_policy_sha256",
)


class OrderedMeasurementRefusal(ValueError):
    """The complete pinned ordered measurement could not be admitted."""


def _fail(reason):
    error = OrderedMeasurementRefusal("cognitive ordered measurement refused: " + reason)
    error.non_claims = list(NON_CLAIMS)
    raise error


def _keys(value, fields, label):
    if type(value) is not dict or len(value) != len(fields) or set(value) != set(fields):
        _fail(label + " fields are invalid")


def _policy(kw):
    # This v1 contract intentionally retains its complete aggregate ceiling.
    # A future compound-envelope version must not silently widen this lane.
    measurement.baseline_module._bounded(kw, MAX_INPUT_BYTES)
    policy = kw["ordered_policy"]
    _keys(policy, {*_POLICY, "metric_protocol_sha256", "arms", "resources"}, "ordered policy")
    if any(type(policy[key]) is not str or policy[key] != expected for key, expected in _POLICY.items()):
        _fail("ordered policy changes a frozen admission or scoring rule")
    if type(policy["arms"]) is not list or policy["arms"] != list(ARMS):
        _fail("complete fixed ordered arm roster is required")
    _keys(policy["resources"], _RESOURCES, "ordered resources")
    for key, ceiling in _RESOURCES.items():
        value = policy["resources"][key]
        if type(value) is not int or not 0 < value <= ceiling:
            _fail("ordered resource declaration exceeds its strict hard ceiling")
    _keys(kw["exposure_inputs"], _EXPOSURE_INPUTS, "independent exposure replay")
    # Domain checks above precede byte accounting or serialization of any
    # earlier valid object when a later input contains a cycle or bad number.
    exposure_module._json_size(kw, policy["resources"]["max_input_bytes"])
    measurement._pin(policy, kw["expected_ordered_policy_sha256"])
    measurement._pin(kw["exposure"], kw["expected_exposure_sha256"], "artifact_sha256")
    replay = kw["exposure_inputs"]["replay_inputs"]
    if not measurement._digest(policy["metric_protocol_sha256"]) \
            or policy["metric_protocol_sha256"] != replay["expected_protocol_sha256"]:
        _fail("ordered policy does not identify the independent measurement protocol")
    return policy


def _body(kw, source, arms):
    raw = source["measurement_plan"]
    return {
        "schema": "sia-cognitive-ordered-measurement-plan-v1", "status": "prepared-for-jackal",
        "arithmetic_status": "not-evaluated", **{key: raw[key] for key in _SOURCE_FIELDS},
        **{key: source[key] for key in _EXPOSURE_FIELDS},
        "exposure_sha256": kw["expected_exposure_sha256"],
        "ordered_policy_sha256": kw["expected_ordered_policy_sha256"],
        "ordered_policy": kw["ordered_policy"], "exposure": source, "arms": arms,
        "source_non_claims": {
            "exposure": source["non_claims"], "exposure_sources": source["source_non_claims"],
            "measurement": raw["non_claims"], "history": raw["source_non_claims"],
        },
        "non_claims": list(NON_CLAIMS),
    }


def _orders(source, policy):
    """Admit the complete query/arm/reference roster before any summary."""
    raw = source["measurement_plan"]
    if source["schema"] != policy["exposure_schema"] or source["status"] != "computed-unverified" \
            or raw["status"] != "prepared-for-jackal" or raw["arithmetic_status"] != "not-evaluated":
        _fail("exposure or raw measurement has an unsupported status or schema")
    roster = raw["baseline"]["queries"]
    identifiers = [row["id"] for row in roster]
    if not identifiers or len(identifiers) > policy["resources"]["max_queries"] \
            or len(set(identifiers)) != len(identifiers) \
            or identifiers != [row["id"] for row in raw["queries"]] \
            or identifiers != [row["id"] for row in source["queries"]]:
        _fail("complete measured query roster differs or exceeds its capacity")
    original_rows = raw["baseline"]["observation"]["query"]["payload"]["results"]
    labels = raw["baseline"]["retrieval_rows"]
    if identifiers != [row["id"] for row in original_rows] or identifiers != [row["id"] for row in labels]:
        _fail("source candidate or label query roster differs")
    prepared = []
    for query, measured, observed, joined in zip(source["queries"], raw["queries"], original_rows, labels, strict=True):
        candidates, coverage = query["candidates"], measured["row_coverage"]
        if type(candidates) is not list or len(candidates) != len(observed["rows"]) \
                or len(coverage) != len(candidates) or len(joined["rows"]) != len(candidates):
            _fail("complete raw candidate and native coverage populations differ")
        references, by_reference = [], {}
        for rank, (candidate, row, hits, label) in enumerate(
                zip(candidates, observed["rows"], coverage, joined["rows"], strict=True), 1):
            reference = "row-" + str(rank)
            if candidate["row_ref"] != reference or candidate["raw_rank"] != rank \
                    or not measurement._same(candidate["raw_row"], row) \
                    or candidate["origin"] != label["origin"] \
                    or candidate["page_text_sha256"] != label["page_text_sha256"] \
                    or candidate["chunk_text_sha256"] != label["chunk_text_sha256"] \
                    or hits["rank"] != rank or hits["slug"] != row["slug"] \
                    or hits["chunk_index"] != row["chunk_index"] or hits["origin"] != label["origin"]:
                _fail("row reference no longer binds its original raw row, source, and native hits")
            references.append(reference)
            by_reference[reference] = hits
        arms = query["arms"]
        if type(arms) is not list or [arm["name"] for arm in arms] != list(ARMS):
            _fail("a measured query omits or changes a fixed arm")
        for arm in arms:
            _keys(arm, {"name", "order"}, "arm")
            order = arm["order"]
            if type(order) is not list or any(type(reference) is not str for reference in order) \
                    or len(order) != len(references) or set(order) != set(references) \
                    or len(set(order)) != len(order):
                _fail("an arm is not a complete raw-reference bijection")
            if arm["name"] == "raw-original" and order != references:
                _fail("raw-original arm changes the original observation order")
        prepared.append({"id": query["id"], "coverage": by_reference,
                         "orders": {arm["name"]: arm["order"] for arm in arms}})
    return prepared


def _freeze(kw, source):
    # Measurement and exposure replay retain all existing protocol/grid/member
    # checks. This boundary adds only its independently frozen policy identity.
    raw = source["measurement_plan"]
    if raw["split"] == "heldout":
        parameters = raw["baseline"]["parameter_freeze"]["parameters"]
        if parameters.get("ordered_measurement_policy_sha256") != kw["expected_ordered_policy_sha256"]:
            _fail("heldout freeze omits or changes the ordered measurement policy pin")
    elif raw["split"] != "calibration":
        _fail("ordered measurement has no admitted query split")


def _reserve_output(kw, source, prepared):
    """Reserve every arm's complete summary before computing any new summary.

    All targets at every cutoff conservatively cover any retrieved subset.
    Expression/rank strings are size placeholders, never emitted observations
    or evaluated arithmetic. The hit roster and all text stay shared, not
    duplicated in memory merely to count their repeated serialized bytes.
    """
    raw = source["measurement_plan"]
    ceiling = kw["ordered_policy"]["resources"]["max_output_bytes"]
    maximum = str(measurement.baseline_module.raw_admission.MAX_SAFE_INTEGER)
    scalar_expression = maximum + "/" + maximum
    digest = "0" * len(kw["expected_exposure_sha256"])
    reserved_queries = []
    for query in raw["queries"]:
        targets = query["targets"]
        reserved_queries.append({**query, "cutoffs": [{
            "k": k, "target_count": len(targets), "retrieved_target_count": len(targets),
            "covered_occurrences": [target["occurrence"] for target in targets],
            "first_target_rank": maximum + "null",
        } for k in raw["protocol"]["metric_policy"]["cutoffs"]]})
    reserved_requests = []
    for request in raw["jackal_requests"]:
        expression = scalar_expression if request["scope"]["kind"] == "query" else (
            "(" + "+".join("(" + scalar_expression + ")" for _ in request["query_ids"])
            + ")/" + maximum)
        reserved_requests.append({**request, "arguments": {"expression": expression}})
    arms = [{"name": name,
             "query_orders": [{"id": query["id"], "order": query["orders"][name]} for query in prepared],
             "queries": reserved_queries, "classes": raw["classes"], "jackal_requests": reserved_requests}
            for name in ARMS]
    body = _body(kw, source, arms)
    body["plan_sha256"] = digest
    exposure_module._json_size(body, ceiling)


def _prepare(kw):
    policy = _policy(kw)
    # A minimum complete wrapper already contains the entire supplied exposure;
    # reject an impossible output declaration before copying or invoking replay.
    minimum = _body(kw, kw["exposure"], [])
    minimum["plan_sha256"] = "0" * len(kw["expected_exposure_sha256"])
    exposure_module._json_size(minimum, policy["resources"]["max_output_bytes"])
    detached = copy.deepcopy(kw)
    policy = _policy(detached)
    source = exposure_module.rerank_event_exposure(**detached["exposure_inputs"])
    if not measurement._same(source, detached["exposure"]):
        _fail("retained exposure differs from complete independent source and policy replay")
    _freeze(detached, source)
    prepared = _orders(source, policy)
    _reserve_output(detached, source, prepared)
    raw = source["measurement_plan"]
    arms = []
    for name in ARMS:
        coverage_by_id = {
            query["id"]: [{**query["coverage"][reference], "rank": rank}
                          for rank, reference in enumerate(query["orders"][name], 1)]
            for query in prepared
        }
        queries, classes, requests = measurement._summarize_coverage(
            raw["protocol"], raw["baseline"]["queries"], coverage_by_id)
        if not measurement._same(classes, raw["classes"]):
            _fail("ordered summary changed class membership or missing-query boundaries")
        if name == "raw-original" and any(not measurement._same(value, raw[field]) for field, value in (
                ("queries", queries), ("classes", classes), ("jackal_requests", requests))):
            _fail("raw-original summary differs from the original raw measurement")
        arms.append({"name": name,
                     "query_orders": [{"id": query["id"], "order": query["orders"][name]} for query in prepared],
                     "queries": queries, "classes": classes, "jackal_requests": requests})
    body = _body(detached, source, arms)
    ceiling = policy["resources"]["max_output_bytes"]
    body["plan_sha256"] = measurement._sha(exposure_module._canonical(body, ceiling))
    exposure_module._json_size(body, ceiling)
    return body


def prepare_ordered_measurement(*, exposure, expected_exposure_sha256, exposure_inputs,
                                ordered_policy, expected_ordered_policy_sha256):
    """Prepare all fixed arms from fully pinned exposure and raw source replay."""
    try:
        return _prepare(locals())
    except OrderedMeasurementRefusal:
        raise
    except (measurement.baseline_module.BaselineRefusal, ValueError, TypeError,
            KeyError, IndexError, OverflowError, RecursionError) as exc:
        error = OrderedMeasurementRefusal("cognitive ordered measurement could not be admitted")
        error.non_claims = list(NON_CLAIMS)
        upstream = getattr(exc, "non_claims", [])
        try:
            measurement.baseline_module._bounded(upstream, MAX_OUTPUT_BYTES)
        except (measurement.baseline_module.BaselineRefusal, ValueError, TypeError,
                OverflowError, RecursionError):
            _fail("upstream refusal nonclaims are not bounded JSON")
        if type(upstream) is not list or any(type(statement) is not str for statement in upstream):
            _fail("upstream refusal nonclaims are not a string list")
        # Strings are immutable; preserve their exact values without copying
        # unadmitted input structures on this refusal path.
        error.upstream_non_claims = list(upstream)
        raise error from exc
