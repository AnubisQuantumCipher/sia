"""Compact, replay-bound consistency predicates for a constructed mechanism.

This boundary distinguishes representation preservation from successful
retrieval, source truth and biological memory. It neither computes a fidelity
percentage nor observes resident storage. Its complete document references
require the caller to retain those documents; a digest is not a source archive.

The complete ordered adapter is replayed with independently supplied inputs.
Only after exact agreement can the fixed predicates and source references be
returned. No corpus consolidation, publication, model or metric execution is
introduced here; upstream pure replay keeps its original assurance boundary.
"""

import copy

import siacognitiveenvelope as envelope_module
import siacognitiveorderedmeasure as ordered_module


measurement = ordered_module.measurement
baseline = measurement.baseline_module
exposure_module = ordered_module.exposure_module
MAX_INPUT_BYTES = envelope_module.MAX_INPUT_BYTES
MAX_DOCUMENT_BYTES = envelope_module.MAX_DOCUMENT_BYTES
MAX_OUTPUT_BYTES = baseline.MAX_ARTIFACT_BYTES
MAX_QUERIES = ordered_module.MAX_QUERIES
MAX_SOURCE_EVENTS = exposure_module.MAX_SOURCE_EVENTS
MAX_SOURCE_PAGES = baseline.sialib.MAX_EVENT_LOOKUP_PAGES
MAX_CANDIDATES_PER_QUERY = exposure_module.activation.MAX_CANDIDATES
MAX_TRACE_BYTES = exposure_module.MAX_TRACE_BYTES
ARMS = ordered_module.ARMS
PREDICATES = (
    "complete-captured-source-bindings",
    "complete-returned-candidate-membership",
    "unchanged-raw-chunk-and-score-values",
    "unchanged-source-origins",
    "complete-exposure-and-activation-traces",
    "unchanged-native-targets-and-coverage",
    "complete-fixed-arm-permutations",
    "complete-upstream-nonclaims",
)
SCOPE = {
    "sources": "admitted-captured-history-only",
    "candidates": "returned-raw-candidate-roster-only",
    "storage": "identity-references-not-a-source-archive",
    "resident_state": "not-observed",
}
NON_CLAIMS = [
    "These Boolean predicates describe independently replayed represented consistency within the admitted capture and returned candidate roster, not a memory-fidelity percentage.",
    "Identity references are not source archives; the caller must retain the complete externally referenced documents.",
    "Independent replay does not authenticate historical sources, establish current resident-state bytes, or prove that no live corpus page was deleted.",
    "Preserving raw chunk/score values and source origins does not establish truth, semantic-answer correctness, biological memory fidelity, recall improvement or a cognitive win.",
    "Full traces, targets, fixed arms, raw latency observations, and upstream nonclaims remain controlling; this boundary does not tune, select an arm, or evaluate JACKAL expressions.",
    "Heldout policy pins declare calibration-only chronology but do not independently prove when tuning or private result inspection occurred.",
    "No model, index, filesystem, clock, corpus mutation, source publication or durable storage is invoked.",
]
_POLICY = {
    "schema": "sia-cognitive-memory-fidelity-policy-v1",
    "ordered_schema": "sia-cognitive-ordered-measurement-plan-v1",
    "replay": "complete-independent-ordered-replay-v1",
    "references": "complete-documents-and-subtrees-no-archive-claim-v1",
    "chronology": "externally-pinned-before-heldout-v1",
    "overflow": "refuse-complete-artifact-v1",
}
_RESOURCES = {
    "max_input_bytes": MAX_INPUT_BYTES, "max_document_bytes": MAX_DOCUMENT_BYTES,
    "max_output_bytes": MAX_OUTPUT_BYTES, "max_queries": MAX_QUERIES,
    "max_source_events": MAX_SOURCE_EVENTS, "max_source_pages": MAX_SOURCE_PAGES,
    "max_candidates_per_query": MAX_CANDIDATES_PER_QUERY, "max_trace_bytes": MAX_TRACE_BYTES,
}
_SOURCE_PINS = (
    "capture_sha256", "policy_sha256", "selection_sha256", "pages_sha256",
    "metric_policy_sha256", "baseline_contract_sha256", "protocol_sha256",
    "baseline_sha256", "query_roster_sha256", "parameter_freeze_sha256",
    "measurement_plan_sha256", "rerank_policy_sha256", "activation_grid_sha256",
    "activation_policy_sha256", "exposure_sha256", "ordered_policy_sha256",
)
# Reuse the upstream code-defined API topology, not fields inferred from any
# supplied document. Its None leaves keep capture, source, baseline, exposure
# and ordered artifacts whole under their unchanged document ceilings.
_COMPOUND_LAYOUT = {
    "ordered_plan": None, "expected_ordered_plan_sha256": None,
    "ordered_inputs": ordered_module._COMPOUND_LAYOUT,
    "fidelity_policy": None, "expected_fidelity_policy_sha256": None,
}
_ORDERED_FIELDS = {
    "schema", "status", "arithmetic_status", *_SOURCE_PINS, "split",
    "ordered_policy", "exposure", "arms", "source_non_claims", "non_claims", "plan_sha256",
}
_QUERY_FIELDS = {"id", "text", "cue", "candidates", "activation", "arms"}
_CANDIDATE_FIELDS = {
    "row_ref", "raw_rank", "raw_row", "origin", "page_text_sha256",
    "chunk_text_sha256", "exposures", "trace",
}
_ARM_FIELDS = {"name", "query_orders", "queries", "classes", "jackal_requests"}
_DIGEST_PLACEHOLDER = "0" * 64


class FidelityRefusal(ValueError):
    """The complete represented consistency claim could not be admitted."""


def _fail(reason):
    error = FidelityRefusal("cognitive fidelity refused: " + reason)
    error.non_claims = list(NON_CLAIMS)
    raise error


def _keys(value, expected, label):
    if type(value) is not dict or len(value) != len(expected) \
            or any(type(key) is not str for key in value) or set(value) != set(expected):
        _fail(label + " fields are invalid")


def _population(value, maximum, label):
    if type(value) is not list or len(value) > maximum:
        _fail(label + " exceeds its complete roster ceiling")
    return value


def _roster(value, expected, label):
    if type(value) is not list or any(type(item) is not str for item in value) \
            or value != list(expected):
        _fail(label + " changes its complete fixed roster")


def _capture(kw):
    return kw["ordered_inputs"]["exposure_inputs"]["replay_inputs"]["capture"]


def _policy(kw):
    # A late nonfinite/cyclic source must refuse before an earlier policy is
    # serialized, copied or hashed. Keep finite raw wire floats unmodified.
    baseline._bounded(kw, MAX_INPUT_BYTES)
    policy = kw["fidelity_policy"]
    _keys(policy, {*_POLICY, "metric_protocol_sha256", "arms", "predicates", "scope", "resources"},
          "fidelity policy")
    for key, expected in _POLICY.items():
        if type(policy[key]) is not str or policy[key] != expected:
            _fail("fidelity policy changes a fixed consistency contract")
    _roster(policy["arms"], ARMS, "arm policy")
    _roster(policy["predicates"], PREDICATES, "predicate policy")
    _keys(policy["scope"], SCOPE, "scope policy")
    if any(type(policy["scope"][key]) is not str or policy["scope"][key] != value
           for key, value in SCOPE.items()):
        _fail("fidelity scope exceeds represented capture and candidate consistency")
    _keys(policy["resources"], _RESOURCES, "fidelity resources")
    for name, hard in _RESOURCES.items():
        value = policy["resources"][name]
        if type(value) is not int or not 0 < value <= hard:
            _fail("fidelity resource declaration exceeds its strict hard ceiling")
    envelope_module.admit_compound(
        envelope=kw, layout=_COMPOUND_LAYOUT,
        max_input_bytes=policy["resources"]["max_input_bytes"],
        max_document_bytes=policy["resources"]["max_document_bytes"])
    return policy


def _expected_shapes(kw, policy):
    plan = kw["ordered_plan"]
    _keys(plan, _ORDERED_FIELDS, "ordered plan")
    if plan["schema"] != policy["ordered_schema"] or plan["status"] != "prepared-for-jackal" \
            or plan["arithmetic_status"] != "not-evaluated" \
            or type(plan["split"]) is not str or plan["split"] not in ("calibration", "heldout"):
        _fail("ordered plan has no supported schema, status or split")
    inputs = kw["ordered_inputs"]
    exposed = inputs["exposure_inputs"]
    replay = exposed["replay_inputs"]
    for owner in (kw, inputs, exposed, replay):
        for key, value in owner.items():
            if key.startswith("expected_"):
                if key == "expected_parameter_freeze_sha256" and plan["split"] == "calibration" and value is None:
                    continue
                if not measurement._digest(value):
                    _fail("an independent external identity is absent or malformed")
    for key in _SOURCE_PINS:
        if key == "parameter_freeze_sha256" and plan["split"] == "calibration" and plan[key] is None:
            continue
        if not measurement._digest(plan[key]):
            _fail("an ordered source identity is absent or malformed")
    if not measurement._digest(plan["plan_sha256"]) \
            or not measurement._digest(_capture(kw)["capture_sha256"]):
        _fail("a referenced complete document has no identity")
    if not measurement._digest(policy["metric_protocol_sha256"]) \
            or policy["metric_protocol_sha256"] != replay["expected_protocol_sha256"] \
            or policy["metric_protocol_sha256"] != plan["protocol_sha256"]:
        _fail("fidelity policy does not identify the independently supplied protocol")


def _measured_roster(queries, resources):
    for query in _population(queries, resources["max_queries"], "measured queries"):
        _population(query["targets"], resources["max_source_events"], "complete native targets")
        _population(query["row_coverage"], resources["max_candidates_per_query"], "complete row coverage")


def _baseline_rosters(value, resources):
    _population(value["pages"], resources["max_source_pages"], "baseline source pages")
    _population(value["queries"], resources["max_queries"], "baseline queries")
    for query in _population(value["retrieval_rows"], resources["max_queries"], "source-label queries"):
        _population(query["rows"], resources["max_candidates_per_query"], "complete source-label rows")
    raw = value["observation"]["query"]["payload"]["results"]
    for query in _population(raw, resources["max_queries"], "raw observation queries"):
        _population(query["rows"], resources["max_candidates_per_query"], "complete raw observation rows")


def _exposure_rosters(value, resources):
    _population(value["event_population"], resources["max_source_events"], "complete exposure source population")
    trace_view = []
    for query in _population(value["queries"], resources["max_queries"], "complete exposure queries"):
        _keys(query, _QUERY_FIELDS, "exposure query")
        candidates = _population(query["candidates"], resources["max_candidates_per_query"], "complete candidates")
        traces = []
        for candidate in candidates:
            _keys(candidate, _CANDIDATE_FIELDS, "exposure candidate")
            _population(candidate["exposures"], resources["max_source_events"], "complete candidate exposures")
            traces.append({"row_ref": candidate["row_ref"], "exposures": candidate["exposures"],
                           "trace": candidate["trace"]})
        arms = _population(query["arms"], len(ARMS), "query arms")
        if [arm["name"] for arm in arms] != list(ARMS):
            _fail("an exposure query omits or changes a fixed arm")
        for arm in arms:
            _keys(arm, {"name", "order"}, "query arm")
            _population(arm["order"], resources["max_candidates_per_query"], "complete arm references")
        # Include unfiltered exposure witnesses, every cue-filtered trace and
        # the complete activation receipt. This is one logical exposure view;
        # repeated copies elsewhere in the packet get their own same gate.
        trace_view.append({"id": query["id"], "candidates": traces, "activation": query["activation"]})
    exposure_module._json_size(trace_view, resources["max_trace_bytes"])
    raw = value["measurement_plan"]
    _measured_roster(raw["queries"], resources)
    _baseline_rosters(raw["baseline"], resources)


def _resources(kw, policy):
    resources = policy["resources"]
    plan, capture = kw["ordered_plan"], _capture(kw)
    inputs = kw["ordered_inputs"]["exposure_inputs"]
    replay = inputs["replay_inputs"]
    _population(capture["events"], resources["max_source_events"], "complete captured events")
    _population(capture["pages"], resources["max_source_pages"], "complete captured pages")
    _population(replay["selection"]["pages"], resources["max_source_pages"], "complete selected pages")
    # Do not let a smaller copy of an artifact stand in for a larger later
    # duplicate. All submitted roster occurrences are inspected before work.
    _exposure_rosters(plan["exposure"], resources)
    _exposure_rosters(kw["ordered_inputs"]["exposure"], resources)
    _measured_roster(inputs["measurement_plan"]["queries"], resources)
    _baseline_rosters(inputs["measurement_plan"]["baseline"], resources)
    _baseline_rosters(replay["baseline"], resources)
    arms = _population(plan["arms"], len(ARMS), "complete ordered arms")
    if [arm["name"] for arm in arms] != list(ARMS):
        _fail("ordered plan omits or changes a fixed arm")
    for arm in arms:
        _keys(arm, _ARM_FIELDS, "ordered arm")
        _measured_roster(arm["queries"], resources)
        for query in _population(arm["query_orders"], resources["max_queries"], "ordered query roster"):
            _keys(query, {"id", "order"}, "ordered query references")
            _population(query["order"], resources["max_candidates_per_query"], "complete ordered references")


def _material(kw):
    plan, capture = kw["ordered_plan"], _capture(kw)
    observed = plan["exposure"]["measurement_plan"]["baseline"]
    return (
        ("capture.events", capture["events"]), ("capture.pages", capture["pages"]),
        ("capture.witness_files", capture["witness_files"]),
        ("baseline.pages", observed["pages"]), ("baseline.observation", observed["observation"]),
        ("baseline.retrieval_rows", observed["retrieval_rows"]),
        ("exposure.queries", plan["exposure"]["queries"]), ("ordered_plan.arms", plan["arms"]),
    )


def _bindings(kw, *, reserve=False):
    rows = [
        {"name": "capture", "sha256": _capture(kw)["capture_sha256"],
         "digest_rule": "embedded-body-sha256", "retention": "externally-retained-complete-document"},
        {"name": "ordered_plan", "sha256": kw["expected_ordered_plan_sha256"],
         "digest_rule": "embedded-body-sha256", "retention": "externally-retained-complete-document"},
    ]
    for name, value in _material(kw):
        digest = (_DIGEST_PLACEHOLDER if reserve else measurement._sha(
            exposure_module._canonical(value, kw["fidelity_policy"]["resources"]["max_document_bytes"])))
        rows.append({"name": name, "sha256": digest, "digest_rule": "canonical-json-sha256",
                     "retention": "externally-retained-complete-subtree"})
    return rows


def _body(kw, bindings):
    plan, capture = kw["ordered_plan"], _capture(kw)
    return {
        "schema": "sia-cognitive-memory-fidelity-v1", "status": "computed-unverified",
        "ordered_plan_sha256": kw["expected_ordered_plan_sha256"],
        "fidelity_policy": kw["fidelity_policy"],
        "fidelity_policy_sha256": kw["expected_fidelity_policy_sha256"],
        "source_pins": {key: plan[key] for key in _SOURCE_PINS}, "split": plan["split"],
        "scope": dict(SCOPE), "predicates": [{"name": name, "holds": True} for name in PREDICATES],
        "material_bindings": bindings,
        "source_non_claims": {
            "ordered": plan["non_claims"], "ordered_sources": plan["source_non_claims"],
            "capture": capture["non_claims"], "capture_sources": capture["source_non_claims"],
        },
        "non_claims": list(NON_CLAIMS),
    }


def _preflight(kw):
    policy = _policy(kw)
    _expected_shapes(kw, policy)
    _resources(kw, policy)
    # Only metadata containers are constructed here; complete source/nonclaim
    # values are references to the already bounded input. Placeholders have
    # the exact eventual digest length and are never emitted as evidence.
    # Thus all variable upstream nonclaims and every output field are counted
    # before any source hash, detached copy or independent replay is invoked.
    reservation = _body(kw, _bindings(kw, reserve=True))
    reservation["artifact_sha256"] = _DIGEST_PLACEHOLDER
    return exposure_module._json_size(reservation, policy["resources"]["max_output_bytes"])


def _pins(kw):
    measurement._pin(kw["fidelity_policy"], kw["expected_fidelity_policy_sha256"])
    measurement._pin(kw["ordered_plan"], kw["expected_ordered_plan_sha256"], "plan_sha256")


def _freeze(kw, replayed):
    if replayed["split"] == "heldout":
        parameters = replayed["exposure"]["measurement_plan"]["baseline"]["parameter_freeze"]["parameters"]
        if parameters.get("memory_fidelity_policy_sha256") != kw["expected_fidelity_policy_sha256"]:
            _fail("heldout freeze omits or changes the fidelity policy identity")
    elif replayed["split"] != "calibration":
        _fail("fidelity has no admitted query split")


def _prepare(kw):
    _preflight(kw)
    _pins(kw)
    detached = copy.deepcopy(kw)
    reserved_size = _preflight(detached)
    _pins(detached)
    # The exact public ordered replay includes all source, raw observation,
    # score/chunk, origin, trace, target, arm and upstream chronology gates.
    # A self-consistent submitted hash is not a substitute for this replay.
    replayed = ordered_module.prepare_ordered_measurement(**detached["ordered_inputs"])
    if not measurement._same(replayed, detached["ordered_plan"]):
        _fail("ordered plan differs from its complete independent replay")
    _freeze(detached, replayed)
    body = _body(detached, _bindings(detached))
    ceiling = detached["fidelity_policy"]["resources"]["max_output_bytes"]
    body["artifact_sha256"] = measurement._sha(exposure_module._canonical(body, ceiling))
    if exposure_module._json_size(body, ceiling) != reserved_size:
        _fail("complete output differs from its preflight byte reservation")
    return body


def prepare_mechanism_fidelity(*, ordered_plan, expected_ordered_plan_sha256, ordered_inputs,
                               fidelity_policy, expected_fidelity_policy_sha256):
    """Return scoped consistency predicates only after complete pinned replay."""
    try:
        return _prepare(locals())
    except FidelityRefusal:
        raise
    except (baseline.BaselineRefusal, ValueError, TypeError, KeyError, IndexError,
            OverflowError, RecursionError, AttributeError) as exc:
        error = FidelityRefusal("cognitive fidelity inputs or replay could not be admitted")
        error.non_claims = list(NON_CLAIMS)
        upstream = {"non_claims": getattr(exc, "non_claims", []),
                    "upstream_non_claims": getattr(exc, "upstream_non_claims", [])}
        try:
            baseline._bounded(upstream, MAX_OUTPUT_BYTES)
        except (baseline.BaselineRefusal, ValueError, TypeError, OverflowError, RecursionError):
            _fail("upstream refusal nonclaims exceed their complete representation bound")
        # Preserve both existing upstream layers without echoing exception
        # text, changing their status class, or copying unadmitted documents.
        error.upstream_non_claims = upstream
        raise error from exc
