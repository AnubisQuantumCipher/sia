"""Pure, preregistered raw embedding-prefix comparison, without adoption.

Both source protocols and raw measurements are independently replayed through
their public APIs. This component emits the complete existing metric requests
and a fixed class-balanced selector request roster; it never evaluates them.
Original artifacts remain externally retained and no baseline is relabeled.
"""

import copy
import json

import siacognitiveenvelope as envelope
import siacognitivemeasure as measurement


baseline = measurement.baseline_module
MAX_INPUT_BYTES = envelope.MAX_INPUT_BYTES
MAX_DOCUMENT_BYTES = envelope.MAX_DOCUMENT_BYTES
MAX_OUTPUT_BYTES = baseline.MAX_ARTIFACT_BYTES
MAX_QUERIES = 64
ARMS = ("bare", "nomic-search-prefixes")
CLASSES = ("recency-heavy", "repetition-heavy", "novelty", "associative-multi-hop", "consolidation-gist")
CUTOFFS = (1, 3, 5, 10)
METRICS = ("recall_at_k", "mrr_at_k")
NON_CLAIMS = [
    "This component prepares a source-frozen baseline-configuration comparison and unevaluated JACKAL requests, not numeric results, baseline adoption, statistical significance or a cognitive win.",
    "The selected baseline will be selected using this frozen dataset; its performance here is not an independent heldout estimate, and the selection adjustment is not claimed automatically conservative.",
    "Class balance and lexicographic metric precedence are declared engineering choices, not uniform dominance across classes, cutoffs, latency or future data.",
    "All original query and class metrics, unavailable coverage, ties, losses and latency observations remain represented; no query-level or class-level winner splicing is authorized.",
    "Exact equality of the complete selector vector permits the declared prefixed convention only after fresh numeric admission; it is a tie, not evidence that prefixes are stronger.",
    "Original source/query text, chunk boundaries, target occurrences, qualifiers and origins remain unchanged; task prefixes belong only to separately identified embedding inputs.",
    "Independent public replay checks represented source, contract and observation consistency, not current private archive bytes, historical model execution, loaded heap or hostile same-user immutability.",
    "Original bare artifacts remain separate and immutable; a new selected baseline needs additive identity and downstream mechanism/fidelity/timing replay, never relabeling an old candidate pool.",
    "Supplied pins and recorded freezes do not independently prove historical chronology or that no private outcome was inspected; no mechanism parameter retuning on these outcomes is authorized.",
    "Compact identities and occurrence witnesses are not source archives; complete independently replayed source and raw documents, all upstream nonclaims and original refusals must remain retained.",
    "No cognitive authorization follows from baseline selection; independent fidelity, new timed replay, and fresh JACKAL numeric/model admission remain separate prerequisites.",
    "No model, index, resident corpus, filesystem, clock, JACKAL execution, durable publication or deletion is invoked by these pure APIs.",
]


def _embedding_policy(arm):
    return {"schema": "sia-embedding-input-policy-v1",
            "mode": "bare-v1" if arm == "bare" else "nomic-prefix-v1",
            "document_prefix": "" if arm == "bare" else "search_document: ",
            "query_prefix": "" if arm == "bare" else "search_query: ",
            "encoding": "utf-8", "document_stage": "after-lossless-chunking",
            "query_stage": "original-query", "overflow": "refuse"}


_POLICY = {
    "schema": "sia-cognitive-raw-prefix-comparison-policy-v1", "split": "heldout",
    "arms": list(ARMS), "classes": list(CLASSES), "cutoffs": list(CUTOFFS), "metrics": list(METRICS),
    "embedding_input_policies": {arm: _embedding_policy(arm) for arm in ARMS},
    "pairing": "same-fresh-runner-model-source-query-roster-v1",
    "source_fidelity": "unchanged-text-chunks-targets-and-origins-v1",
    "selector": "equal-weight-nonempty-heldout-class-means-v1",
    "selector_order": "recall-at-frozen-cutoffs-then-mrr-at-frozen-cutoffs-v1",
    "direction": "nomic-search-prefixes-minus-bare-v1",
    "selection": "first-unequal-coordinate-greater-arm-v1",
    "full_tie": "adopt-nomic-search-prefixes-by-convention-not-superiority-v1",
    "unavailable": "source-declared-before-results-retained-not-zero-v1",
    "missing_or_refused": "adoption-unadmitted-no-fallback-v1",
    "latency": "retain-separate-arm-observations-not-a-selector-v1",
    "numeric_admission": "fresh-jackal-complete-expression-scope-request-bindings-v1",
    "adoption": "separate-external-receipt-no-local-verdict-v1",
    "chronology": "freeze-before-prefix-execution-or-either-arm-metric-evaluation-v1",
    "downstream": "new-selected-baseline-identity-and-full-replay-no-retuning-v1",
    "interpretation": "same-dataset-configuration-selection-not-independent-heldout-estimate-v1",
    "non_claims": list(NON_CLAIMS),
}
_SOURCE_LAYOUT = {key: None for key in measurement._SOURCE_KEYS}
_PROTOCOL_LAYOUT = {
    "arm_sources": {arm: _SOURCE_LAYOUT for arm in ARMS}, "comparison_policy": None,
    "expected_comparison_policy_sha256": None, "original_parameter_freeze": None,
    "expected_original_parameter_freeze_sha256": None,
}
_COMPARISON_LAYOUT = {
    "prefix_protocol": None, "expected_prefix_protocol_sha256": None,
    "protocol_inputs": _PROTOCOL_LAYOUT,
    "observations": {arm: {"baseline": None, "expected_baseline_sha256": None,
                           "expected_parameter_freeze_sha256": None} for arm in ARMS},
}
_SOURCE_PINS = (*measurement._SOURCE_PINS, "metric_policy_sha256")
_PROFILE_FIELDS = {"embedding_input_policy", "embedding_input_policy_sha256"}
_FREEZE_FIELDS = {"schema", "capture_sha256", "policy_sha256", "selection_sha256",
                  "baseline_contract_sha256", "calibration_run_sha256", "tuning_split",
                  "parameters", "parameters_sha256", "non_claims", "freeze_sha256"}
_DIGEST = "0" * 64
_INTEGER = str(baseline.raw_admission.MAX_SAFE_INTEGER)


class PrefixRefusal(ValueError):
    """The complete source/pair/selector construction was refused."""


def _fail(reason):
    error = PrefixRefusal("cognitive prefix comparison refused: " + reason)
    error.non_claims = list(NON_CLAIMS)
    raise error


def _keys(value, expected, label):
    if type(value) is not dict or set(value) != set(expected):
        _fail(label + " has invalid fields")


def _same(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(_same(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return left == right


def _list(value, maximum, label):
    if type(value) is not list or len(value) > maximum:
        _fail(label + " exceeds its complete roster ceiling")
    return value


def _digest(value):
    if not measurement._digest(value):
        _fail("an independent canonical digest is missing")
    return value


def _resources():
    return {"max_input_bytes": MAX_INPUT_BYTES, "max_document_bytes": MAX_DOCUMENT_BYTES,
            "max_output_bytes": MAX_OUTPUT_BYTES, "max_queries": MAX_QUERIES}


def _envelope(kw, layout):
    envelope.admit_compound(envelope=kw, layout=layout, max_input_bytes=MAX_INPUT_BYTES,
                            max_document_bytes=MAX_DOCUMENT_BYTES)


class _Expression:
    """Lazy request text for byte reservation, never arithmetic evaluation."""

    def __init__(self, *parts):
        self.parts = parts

    def fragments(self):
        for part in self.parts:
            if type(part) is _Expression:
                yield from part.fragments()
            else:
                yield part


def _size(value):
    size = 0

    def add(amount):
        nonlocal size
        size += amount
        if size > MAX_OUTPUT_BYTES:
            _fail("complete output exceeds its pre-work reservation")

    def scalar(item):
        # Incoming strings are already admitted whole documents. Iterencode
        # never creates the complete prospective output or repeated expression.
        for fragment in json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":")).iterencode(item):
            add(len(fragment.encode("utf-8")))

    def visit(item):
        if type(item) is _Expression:
            add(len('""'))
            for fragment in item.fragments():
                # Each fragment is text; JSON escaping is additive after the
                # surrounding string quotes are removed.
                encoded = json.dumps(fragment, ensure_ascii=False, allow_nan=False)
                add(len(encoded.encode("utf-8")) - len('""'))
        elif type(item) is dict:
            add(len("{}"))
            for index, (key, child) in enumerate(item.items()):
                if index:
                    add(len(","))
                scalar(key)
                add(len(":"))
                visit(child)
        elif type(item) is list:
            add(len("[]"))
            for index, child in enumerate(item):
                if index:
                    add(len(","))
                visit(child)
        else:
            scalar(item)

    visit(value)
    return size


def _text(expression, reserve):
    return expression if reserve else "".join(expression.fragments())


def _mean(expressions):
    if not expressions:
        _fail("no source-declared nonempty class is available for the selector")
    parts = ["("]
    for index, expression in enumerate(expressions):
        if index:
            parts.append("+")
        parts.extend(("(", expression, ")"))
    parts.extend((")/", str(len(expressions))))
    return _Expression(*parts)


def _original(kw):
    value = kw["original_parameter_freeze"]
    _keys(value, _FREEZE_FIELDS, "original parameter freeze")
    source = kw["arm_sources"]["bare"]
    if value["schema"] != "sia-cognitive-parameter-freeze-v1" or value["tuning_split"] != "calibration" \
            or type(value["parameters"]) is not dict:
        _fail("original parameter freeze is not the declared calibration-only source")
    for key, expected_key in (("capture_sha256", "expected_capture_sha256"),
                              ("policy_sha256", "expected_policy_sha256"),
                              ("selection_sha256", "expected_selection_sha256")):
        if value[key] != source[expected_key]:
            _fail("original parameter freeze belongs to a different captured source")
    for field in ("baseline_contract_sha256", "calibration_run_sha256", "parameters_sha256", "freeze_sha256"):
        _digest(value[field])
    _digest(kw["expected_original_parameter_freeze_sha256"])
    baseline._nonclaims(value["non_claims"])
    # The original contract can be legacy v1. Its external freeze identity is
    # authority for the retained parameters, not an assertion that it is v2.
    return value


def _source_shapes(kw):
    if not _same(kw["comparison_policy"], _POLICY):
        _fail("comparison policy changes the complete preregistered selector")
    _digest(kw["expected_comparison_policy_sha256"])
    sources = kw["arm_sources"]
    first = sources["bare"]
    for arm in ARMS:
        source = sources[arm]
        for field in measurement._SOURCE_KEYS:
            if field.startswith("expected_"):
                _digest(source[field])
        if not _same(source["metric_policy"]["cutoffs"], list(CUTOFFS)):
            _fail("raw metric cutoffs differ from the frozen complete selector")
        for field in measurement._SOURCE_KEYS:
            if field not in ("baseline_contract", "expected_baseline_contract_sha256") \
                    and not _same(source[field], first[field]):
                _fail("arms do not share the same complete captured source and query policy")
        contract = source["baseline_contract"]
        if type(contract) is not dict or contract.get("schema") != "sia-cognitive-baseline-contract-v2" \
                or not _same(contract.get("embedding_input_policy"), _embedding_policy(arm)):
            _fail("both arms require their explicit fixed v2 embedding-input policies")
        _digest(contract.get("embedding_input_policy_sha256"))
        if contract["embedding"]["model"] != "ollama:nomic-embed-text:v1.5":
            _fail("the prefixed pair requires the declared nomic embedding model")
        shared = {key: value for key, value in contract.items() if key not in _PROFILE_FIELDS}
        reference = {key: value for key, value in first["baseline_contract"].items() if key not in _PROFILE_FIELDS}
        if not _same(shared, reference):
            _fail("nonprefix contract fields differ across the same-runner pair")
    _original(kw)


def _preview_source(source):
    """Untrusted shape projection for reservation; public replay is authority.

    This mirrors the public protocol's target fields without hashing excerpts,
    authenticating occurrences, computing hit credit or copying source bytes.
    The later independently rebuilt protocol must match this projection.
    """
    selected = source["selection"]
    queries = _list(selected["queries"], MAX_QUERIES, "complete source queries")
    answers = _list(selected["answer_key"], MAX_QUERIES, "complete source answer keys")
    pages = {row["slug"]: row for row in selected["pages"]}
    answers_by_id = {row["id"]: row for row in answers}
    if len(answers_by_id) != len(answers) or len({row["id"] for row in queries}) != len(queries):
        _fail("source query or answer identity is repeated")
    projected = []
    for public in queries:
        answer = answers_by_id[public["id"]]
        support = {row["seq"]: row for row in answer["support"]}
        targets = []
        for sequence in answer["answer"]["sequences"]:
            witness = support[sequence]
            page = pages[witness["slug"]]
            targets.append({
                "occurrence": {"chain": answer["scope"]["chain"], "seq": sequence,
                               "entry_hash": witness["entry_hash"]},
                "witness": {"slug": witness["slug"], "origin": page["origin"],
                            "page_text_sha256": page["text_sha256"], "excerpt": witness["excerpt"],
                            "excerpt_sha256": _DIGEST, "chunk_index": witness["chunk_index"],
                            "chunk_sha256": witness["chunk_sha256"]},
            })
        projected.append({**public, "class": answer["class"], "group_id": answer["group_id"],
                          "action": answer["action"], "answer_kind": answer["answer"]["kind"],
                          "scope": answer["scope"], "targets": targets,
                          "eligibility_support": answer["support"]})
    return {"schema": "sia-cognitive-retrieval-protocol-v1",
            **{key: selected[key] for key in measurement._SOURCE_PINS},
            "baseline_contract_sha256": source["expected_baseline_contract_sha256"],
            "metric_policy_sha256": source["expected_metric_policy_sha256"], "metric_policy": source["metric_policy"],
            "groups": selected["groups"], "queries": projected, "coverage": selected["coverage"],
            "exclusions": selected["exclusions"], "protocol_sha256": _DIGEST,
            "source_non_claims": {"selection": selected["non_claims"], "history": selected["source_non_claims"]},
            "non_claims": measurement.NON_CLAIMS}


def _class_roster(protocol, *, prepared):
    coverage = {row["class"]: row for row in protocol["coverage"]}
    if set(coverage) != set(CLASSES) or len(coverage) != len(protocol["coverage"]):
        _fail("complete source coverage does not have the fixed class roster")
    heldout = [row for row in protocol["queries"] if row["split"] == "heldout"]
    rows = []
    for klass in CLASSES:
        ids = [row["id"] for row in heldout if row["class"] == klass]
        rows.append({"class": klass, "query_ids": ids,
                     "status": prepared if ids else "unavailable",
                     "reason": None if ids else coverage[klass]["reason"] or "no-queries-in-requested-split"})
    if any(row["class"] not in CLASSES for row in protocol["queries"]):
        _fail("a query has an undeclared class")
    return rows


def _protocol_body(kw, protocols):
    first = protocols["bare"]
    # Contract/protocol identities differ by design; every original query,
    # target, source, group, exclusion and source boundary must agree.
    for arm in ARMS:
        other = protocols[arm]
        for field in (*_SOURCE_PINS, "metric_policy", "queries", "groups", "coverage", "exclusions", "source_non_claims"):
            if not _same(first[field], other[field]):
                _fail("public arm source protocols do not preserve the complete same-source task")
    classes = _class_roster(first, prepared="prepared-before-arm-results")
    selected_classes = [row["class"] for row in classes if row["query_ids"]]
    if not selected_classes:
        _fail("there is no complete nonempty heldout class for baseline selection")
    return {
        "schema": "sia-cognitive-raw-prefix-protocol-v1", "status": "prepared-before-arm-results",
        "comparison_policy": kw["comparison_policy"],
        "comparison_policy_sha256": kw["expected_comparison_policy_sha256"],
        "original_parameter_freeze_sha256": kw["expected_original_parameter_freeze_sha256"],
        "original_baseline_contract_sha256": kw["original_parameter_freeze"]["baseline_contract_sha256"],
        "original_parameters": kw["original_parameter_freeze"]["parameters"],
        "source_pins": {key: first[key] for key in _SOURCE_PINS},
        "arms": [{"name": arm, "retrieval_protocol_sha256": protocols[arm]["protocol_sha256"],
                  "baseline_contract_sha256": kw["arm_sources"][arm]["expected_baseline_contract_sha256"],
                  **{key: kw["arm_sources"][arm]["baseline_contract"][key] for key in _PROFILE_FIELDS}} for arm in ARMS],
        **{key: first[key] for key in ("queries", "groups", "coverage", "exclusions")},
        "heldout_query_ids": [row["id"] for row in first["queries"] if row["split"] == "heldout"],
        "class_roster": classes, "selector_class_ids": selected_classes, "resources": _resources(),
        "source_non_claims": {"arms": {arm: {"retrieval": protocols[arm]["non_claims"],
                                                "retrieval_sources": protocols[arm]["source_non_claims"]} for arm in ARMS},
                              "original_freeze": kw["original_parameter_freeze"]["non_claims"]},
        "non_claims": list(NON_CLAIMS),
    }


def _source_preflight(kw):
    _source_shapes(kw)
    previews = {arm: _preview_source(kw["arm_sources"][arm]) for arm in ARMS}
    body = _protocol_body(kw, previews)
    body["protocol_sha256"] = _DIGEST
    return previews, _size(body)


def _source_pins(kw):
    measurement._pin(kw["comparison_policy"], kw["expected_comparison_policy_sha256"])
    measurement._pin(kw["original_parameter_freeze"], kw["expected_original_parameter_freeze_sha256"], "freeze_sha256")
    original = kw["original_parameter_freeze"]
    measurement._pin(original["parameters"], original["parameters_sha256"])
    for arm in ARMS:
        contract = kw["arm_sources"][arm]["baseline_contract"]
        measurement._pin(contract, kw["arm_sources"][arm]["expected_baseline_contract_sha256"])
        measurement._pin(contract["embedding_input_policy"], contract["embedding_input_policy_sha256"])


def _finish(body, field, reserved):
    # Admission here checks that the complete pre-work reservation covered the
    # actual output. It does not replace that earlier reservation.
    actual = {**body, field: _DIGEST}
    if _size(actual) > reserved:
        _fail("actual output exceeds its complete pre-work reservation")
    body[field] = measurement._sha(measurement._canonical(body))
    baseline._canonical(body, MAX_OUTPUT_BYTES)
    return copy.deepcopy(body)


def _build(kw):
    _envelope(kw, _PROTOCOL_LAYOUT)
    _previews, reserved = _source_preflight(kw)
    _source_pins(kw)
    detached = copy.deepcopy(kw)
    _source_preflight(detached)
    _source_pins(detached)
    protocols = {arm: measurement.build_protocol(**detached["arm_sources"][arm]) for arm in ARMS}
    return _finish(_protocol_body(detached, protocols), "protocol_sha256", reserved)


def _arm_freezes(kw, protocols):
    pk = kw["protocol_inputs"]
    for arm in ARMS:
        observation = kw["observations"][arm]
        _digest(observation["expected_baseline_sha256"])
        _digest(observation["expected_parameter_freeze_sha256"])
        raw = observation["baseline"]
        source = pk["arm_sources"][arm]
        if raw["schema"] != "sia-cognitive-baseline-v2" or raw["split"] != "heldout" \
                or raw["status"] != "observed" or raw["lane"] != "raw_vector" \
                or raw["baseline_contract_sha256"] != source["expected_baseline_contract_sha256"] \
                or not _same(raw["contract"], source["baseline_contract"]):
            _fail("an arm is not the newly declared v2 heldout raw observation")
        freeze = raw["parameter_freeze"]
        _keys(freeze, _FREEZE_FIELDS, "new arm parameter freeze")
        if freeze["calibration_run_sha256"] != pk["original_parameter_freeze"]["calibration_run_sha256"]:
            _fail("new arm calibration provenance differs from the independently pinned original freeze")
        expected = {**pk["original_parameter_freeze"]["parameters"],
                    "measurement_protocol_sha256": protocols[arm]["protocol_sha256"],
                    "raw_prefix_comparison_policy_sha256": pk["expected_comparison_policy_sha256"],
                    "raw_prefix_comparison_protocol_sha256": kw["expected_prefix_protocol_sha256"]}
        if not _same(freeze["parameters"], expected):
            _fail("new arm parameters drift from the independently pinned original freeze")


def _latency(raw):
    observation = raw["observation"]
    return {"queries": [{"id": row["id"], "latency_ms": row["latency_ms"]}
                         for row in observation["query"]["payload"]["results"]],
            "operations": {operation: observation[operation]["payload"]["latency_ms"]
                           for operation in ("capture", "query")},
            "parent_elapsed_ms": {operation: observation[operation]["elapsed_ms"]
                                  for operation in ("capture", "query") if "elapsed_ms" in observation[operation]}}


def _preview_measurement(protocol, observation):
    """Reserve maximal admitted request numerals, without evaluating any hit."""
    raw = observation["baseline"]
    queries = [row for row in protocol["queries"] if row["split"] == "heldout"]
    classes, requests, expressions = [], [], {}
    for query in queries:
        for cutoff in CUTOFFS:
            for metric in ("recall_at_k", "reciprocal_rank_at_k"):
                expression = _Expression(_INTEGER, "/", _INTEGER) if metric == "recall_at_k" else _Expression("1/", _INTEGER)
                expressions[query["id"], metric, cutoff] = expression
                requests.append(measurement._request("query", query["id"], metric, cutoff, [query["id"]], expression))
    for coverage in protocol["coverage"]:
        klass = coverage["class"]
        members = [row for row in queries if row["class"] == klass]
        ids = [row["id"] for row in members]
        classes.append({"class": klass, "query_ids": ids, "group_ids": sorted({row["group_id"] for row in members}),
                        "status": "prepared-for-jackal" if ids else "unavailable",
                        "reason": None if ids else coverage["reason"] or "no-queries-in-requested-split"})
        for cutoff in CUTOFFS:
            if not ids:
                continue
            for metric, constituent in (("recall_at_k", "recall_at_k"), ("mrr_at_k", "reciprocal_rank_at_k")):
                expression = _mean([expressions[identifier, constituent, cutoff] for identifier in ids])
                requests.append(measurement._request("class", klass, metric, cutoff, ids, expression))
    return {"baseline_sha256": observation["expected_baseline_sha256"],
            "baseline_contract_sha256": protocol["baseline_contract_sha256"], "protocol_sha256": protocol["protocol_sha256"],
            "parameter_freeze_sha256": observation["expected_parameter_freeze_sha256"],
            "plan_sha256": _DIGEST, "query_roster_sha256": raw["query_roster_sha256"],
            "queries": queries, "classes": classes, "jackal_requests": requests,
            "non_claims": measurement.NON_CLAIMS,
            "source_non_claims": {"protocol": protocol["non_claims"], "baseline": raw["non_claims"],
                                  "history": raw["source_non_claims"]}}


def _request(expression, scope, reserve):
    value = {"tool": "jackal_exact", "arguments": {"expression": _text(expression, reserve)}, "scope": scope}
    value["request_sha256"] = _DIGEST if reserve else measurement._sha(measurement._canonical(value))
    return value


def _comparison_body(kw, plans, reserve):
    protocol = kw["prefix_protocol"]
    class_ids = protocol["selector_class_ids"]
    coordinates, requests, arms = [], [], []
    lookups = {}
    for arm in ARMS:
        plan = plans[arm]
        lookups[arm] = {(row["scope"]["id"], row["metric"], row["k"]): row["arguments"]["expression"]
                       for row in plan["jackal_requests"] if row["scope"]["kind"] == "class"}
        arms.append({"name": arm, "baseline_sha256": plan["baseline_sha256"],
                     "baseline_contract_sha256": plan["baseline_contract_sha256"],
                     "retrieval_protocol_sha256": plan["protocol_sha256"],
                     "parameter_freeze_sha256": plan["parameter_freeze_sha256"],
                     "measurement_plan_sha256": plan["plan_sha256"],
                     "query_roster_sha256": plan["query_roster_sha256"],
                     "query_ids": [row["id"] for row in plan["queries"]], "classes": plan["classes"],
                     "jackal_requests": plan["jackal_requests"], "latency_observations": _latency(kw["observations"][arm]["baseline"])})
    for metric in METRICS:
        for cutoff in CUTOFFS:
            expressions, identifiers = {}, {}
            for arm in ARMS:
                expressions[arm] = _mean([lookups[arm][klass, metric, cutoff] for klass in class_ids])
                request = _request(expressions[arm], {"kind": "class-balanced-selector", "arm": arm,
                                   "metric": metric, "k": cutoff, "class_ids": class_ids}, reserve)
                requests.append(request)
                identifiers[arm] = request["request_sha256"]
            difference = _Expression("(", expressions[ARMS[-1]], ")-(", expressions[ARMS[0]], ")")
            request = _request(difference, {"kind": "class-balanced-difference", "metric": metric,
                               "k": cutoff, "class_ids": class_ids}, reserve)
            requests.append(request)
            identifiers["difference"] = request["request_sha256"]
            coordinates.append({"metric": metric, "k": cutoff, "class_ids": class_ids, "requests": identifiers})
    return {
        "schema": "sia-cognitive-raw-prefix-comparison-v1", "status": "prepared-for-jackal",
        "arithmetic_status": "not-evaluated", "split": "heldout", "prefix_protocol": protocol,
        "prefix_protocol_sha256": kw["expected_prefix_protocol_sha256"],
        "comparison_policy_sha256": kw["protocol_inputs"]["expected_comparison_policy_sha256"],
        "arms": arms, "selector": {"status": "awaiting-fresh-jackal", "class_ids": class_ids,
                                    "coordinates": coordinates, "selection": _POLICY["selection"],
                                    "full_tie": _POLICY["full_tie"]},
        "jackal_requests": requests, "adoption": {"status": "unadmitted", "reason": "fresh-jackal-results-required"},
        "claim_gate": {"status": "not-authorized", "reason": "baseline-selection-is-not-cognitive-authorization"},
        "resources": _resources(),
        "source_non_claims": {"protocol": protocol["non_claims"], "protocol_sources": protocol["source_non_claims"],
                              "arms": {arm: {"measurement": plans[arm]["non_claims"],
                                              "measurement_sources": plans[arm]["source_non_claims"]} for arm in ARMS}},
        "non_claims": list(NON_CLAIMS),
    }


def _comparison_preflight(kw):
    previews, _reserved_protocol = _source_preflight(kw["protocol_inputs"])
    _digest(kw["expected_prefix_protocol_sha256"])
    # Use independently carried per-arm protocol identities to shape the new
    # freezes before the public replay recomputes and compares those protocols.
    listed = kw["prefix_protocol"]["arms"]
    if type(listed) is not list or [row["name"] for row in listed] != list(ARMS):
        _fail("prefix protocol lacks its complete fixed arm roster")
    for row in listed:
        previews[row["name"]]["protocol_sha256"] = _digest(row["retrieval_protocol_sha256"])
    _arm_freezes(kw, previews)
    plans = {arm: _preview_measurement(previews[arm], kw["observations"][arm]) for arm in ARMS}
    body = _comparison_body(kw, plans, True)
    body["plan_sha256"] = _DIGEST
    return _size(body)


def _comparison_pins(kw):
    _source_pins(kw["protocol_inputs"])
    measurement._pin(kw["prefix_protocol"], kw["expected_prefix_protocol_sha256"], "protocol_sha256")
    for arm in ARMS:
        observation = kw["observations"][arm]
        measurement._pin(observation["baseline"], observation["expected_baseline_sha256"], "artifact_sha256")
        measurement._pin(observation["baseline"]["parameter_freeze"],
                         observation["expected_parameter_freeze_sha256"], "freeze_sha256")


def _prepare(kw):
    _envelope(kw, _COMPARISON_LAYOUT)
    reserved = _comparison_preflight(kw)
    _comparison_pins(kw)
    detached = copy.deepcopy(kw)
    _comparison_preflight(detached)
    _comparison_pins(detached)
    protocol = prepare_raw_prefix_protocol(**detached["protocol_inputs"])
    if not _same(protocol, detached["prefix_protocol"]):
        _fail("prefix protocol differs from complete independently pinned source replay")
    plans = {}
    for arm in ARMS:
        source = detached["protocol_inputs"]["arm_sources"][arm]
        # The protocol is reconstructed from the same complete source again by
        # prepare_measurement; its compact pin alone never authorizes rows.
        retrieval_protocol = measurement.build_protocol(**source)
        observation = detached["observations"][arm]
        plans[arm] = measurement.prepare_measurement(
            **source, protocol=retrieval_protocol, expected_protocol_sha256=retrieval_protocol["protocol_sha256"],
            **observation)
    _arm_freezes(detached, {arm: plans[arm]["protocol"] for arm in ARMS})
    return _finish(_comparison_body(detached, plans, False), "plan_sha256", reserved)


def _public(function, kw):
    try:
        return function(kw)
    except PrefixRefusal:
        raise
    except (baseline.BaselineRefusal, measurement.MeasurementRefusal, ValueError, TypeError, KeyError,
            IndexError, OverflowError, RecursionError) as exc:
        error = PrefixRefusal("cognitive prefix comparison could not be admitted")
        error.non_claims = list(NON_CLAIMS)
        raise error from exc


def prepare_raw_prefix_protocol(*, arm_sources, comparison_policy, expected_comparison_policy_sha256,
                                original_parameter_freeze, expected_original_parameter_freeze_sha256):
    return _public(_build, locals())


def prepare_raw_prefix_comparison(*, prefix_protocol, expected_prefix_protocol_sha256, protocol_inputs, observations):
    return _public(_prepare, locals())
