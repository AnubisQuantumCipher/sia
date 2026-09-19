"""Source-frozen dependency components and unevaluated paired requests.

Complete public source replay, not submitted protocol rows or their self hash,
establishes the represented query roster. All classes and splits participate
in its dependency closure. Only then are heldout primary members selected.
The comparison boundary independently replays that protocol and the complete
ordered measurement. It does not evaluate expressions, admit numeric receipts,
run a sign test, measure latency, or authorize any mechanism claim.

The declared sign-test policy follows the paired-difference convention in
https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/signtest.htm .
Source coalescence is an engineering dependency declaration, not evidence for
independent sampling or the sign model. Complete documents remain externally
retained; compact identities and page witnesses are not a source archive.
"""

import copy

import siacognitiveenvelope as envelope_module
import siacognitivemeasure as measurement
import siacognitiveorderedmeasure as ordered_module


baseline = measurement.baseline_module
exposure = ordered_module.exposure_module
MAX_INPUT_BYTES = envelope_module.MAX_INPUT_BYTES
MAX_DOCUMENT_BYTES = envelope_module.MAX_DOCUMENT_BYTES
MAX_OUTPUT_BYTES = baseline.MAX_ARTIFACT_BYTES
MAX_QUERIES = ordered_module.MAX_QUERIES
COMPARATORS = ("raw-original", "cue-only")
PENDING = ("independently-replayed-fidelity", "new-timed-replay",
           "fresh-jackal-numeric-admission", "fresh-jackal-model-admission")
NON_CLAIMS = [
    "These compact plans contain unevaluated JACKAL difference requests, not arithmetic assurance, component signs, tail probabilities or a cognitive win.",
    "Dependency components use the complete admitted retrieval-query closure across all classes and splits before selecting heldout primary members; coalescence does not establish independent sampling, statistical power or the sign-test model.",
    "Native chain/raw-subject groups and exact target/support source-page generations define edges; eligibility support is not answer credit and query-level heldout selection is not a source-page holdout.",
    "All fixed comparators, complete component members, class/cutoff metrics, ties, losses and unavailable scopes remain represented; secondary outcomes cannot replace the frozen primary test.",
    "External pins and represented parameter freezes declare chronology but do not independently prove when tuning, source capture or private result inspection occurred.",
    "Complete independent replay checks represented consistency, not historical source authentication, current resident state, model truth or semantic-answer correctness.",
    "Identity references are not source archives; callers must retain the complete independently replayed source and ordered documents with all upstream nonclaims.",
    "No claim is authorized before independent fidelity, new timed replay, and fresh JACKAL numeric and model admission; original raw latency observations do not measure rerank duration or authorize speedup.",
    "No source publication, corpus deletion, filesystem, clock, model, index, JACKAL execution or durable storage is invoked.",
]
_POLICY = {
    "schema": "sia-cognitive-event-exposure-inference-policy-v1",
    "split": "heldout", "primary_class": "recency-heavy", "primary_metric": "recall_at_k",
    "primary_cutoff": 1, "mechanism_arm": "cue-event-exposure",
    "comparators": list(COMPARATORS),
    "effect_requirement": "positive-complete-class-mean-delta-against-every-comparator-v1",
    "test": "one-sided-positive-sign-exact-binomial-tail-v1",
    "alternative": "greater", "null_success_probability": "1/2",
    "familywise_alpha": "1/20", "per_comparison_alpha": "1/40",
    "multiplicity": "bonferroni-fixed-comparator-roster-v1",
    "paired_unit": "connected-native-group-and-target-support-page-component-v1",
    "component_metric": "macro-query-recall-within-complete-component-v1",
    "components": "complete-primary-class-before-arm-outcome-inspection-v1",
    "ties": "retain-in-descriptive-means-exclude-only-sign-test-denominator-v1",
    "no_nonties": "no-sign-evidence-no-win-v1",
    "model_assumptions": ["fixed admitted component roster",
                          "independent component signs conditional on the null",
                          "constant null positive-sign probability among non-ties",
                          "one-sided exact tail convention"],
    "assumption_boundary": "source-dependency-coalescence-does-not-verify-sampling-or-independence-v1",
    "secondary_metrics": "complete-frozen-cutoffs-and-classes-descriptive-only-v1",
    "fidelity_requirement": "complete-independently-replayed-policy-predicates-v1",
    "latency_requirement": "complete-new-timed-replay-and-separate-original-raw-observations-v1",
    "latency_claim": "descriptive-scope-separated-no-speedup-authorization-v1",
    "numeric_admission": "fresh-jackal-frontdoor-results-full-bindings-status-assumptions-nonclaims-v1",
    "missing_or_refused": "no-win-authorization-v1",
    "public_claim": "none-without-completed-mechanism-fidelity-latency-and-inference-admission-v1",
    "chronology": "freeze-before-heldout-results-no-heldout-tuning-v1",
    "source": "https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/signtest.htm",
    "non_claims": [
        "This policy is a frozen test design, not implemented verdict admission or a heldout result.",
        "A sign test addresses the declared component-sign model, not general cognition or a distribution-free mean-effect guarantee.",
        "Native groups and shared target/support pages define declared dependency blocks; their coalescence does not establish independent sampling or statistical power.",
        "Query-level heldout selection is not a source-page holdout; shared pages and authentication anchors remain disclosed.",
        "Calibration cue-only gains do not earn a power-law decay or frequency claim; the mechanism must improve against both fixed comparators.",
        "All fixed retrieval metrics, ties, losses, missing scopes and unavailable classes remain in the descriptive report; secondary outcomes do not substitute for the primary test.",
        "Exact arithmetic and model-based tail probabilities do not authenticate history, validate the test model, or authorize a cognitive name by themselves.",
        "No mechanism claim is authorized by this policy alone, and no latency superiority or end-to-end duration may be inferred from component spans.",
    ],
}
_SOURCE_LAYOUT = {key: None for key in measurement._SOURCE_KEYS}
_PROTOCOL_LAYOUT = {
    "retrieval_protocol": None, "expected_retrieval_protocol_sha256": None,
    "retrieval_inputs": _SOURCE_LAYOUT, "inference_policy": None,
    "expected_inference_policy_sha256": None,
}
_COMPARISON_LAYOUT = {
    "inference_protocol": None, "expected_inference_protocol_sha256": None,
    "inference_inputs": _PROTOCOL_LAYOUT, "ordered_plan": None,
    "expected_ordered_plan_sha256": None, "ordered_inputs": ordered_module._COMPOUND_LAYOUT,
}
_SOURCE_PINS = (*measurement._SOURCE_PINS, "baseline_contract_sha256", "metric_policy_sha256")
_PLACEHOLDER = "0" * 64


class InferenceRefusal(ValueError):
    """The complete source protocol or unevaluated comparison was refused."""


def _fail(reason):
    error = InferenceRefusal("cognitive inference refused: " + reason)
    error.non_claims = list(NON_CLAIMS)
    raise error


def _keys(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        _fail(label + " fields are invalid")


def _population(value, limit, label):
    if type(value) is not list or len(value) > limit:
        _fail(label + " exceeds its complete roster ceiling")
    return value


def _text(value):
    if type(value) is not str or not value:
        _fail("a required source label is not nonempty text")
    return value


def _strict_same(value, expected):
    if type(value) is not type(expected):
        return False
    if type(expected) is list:
        return len(value) == len(expected) and all(_strict_same(a, b) for a, b in zip(value, expected))
    return value == expected


def _policy(kw):
    policy = kw["inference_policy"]
    _keys(policy, {*_POLICY, "protocol_sha256"}, "inference policy")
    if any(not _strict_same(policy[key], expected) for key, expected in _POLICY.items()):
        _fail("inference policy changes its frozen test or claim boundary")
    if not measurement._digest(policy["protocol_sha256"]) \
            or policy["protocol_sha256"] != kw["expected_retrieval_protocol_sha256"]:
        _fail("inference policy does not identify the independently supplied retrieval protocol")


def _envelope(kw, layout):
    # The shared helper checks the entire domain before serializing even an
    # earlier document. Repeated references count at each wire occurrence.
    envelope_module.admit_compound(envelope=kw, layout=layout,
                                   max_input_bytes=MAX_INPUT_BYTES,
                                   max_document_bytes=MAX_DOCUMENT_BYTES)


def _resources():
    return {"max_input_bytes": MAX_INPUT_BYTES, "max_document_bytes": MAX_DOCUMENT_BYTES,
            "max_output_bytes": MAX_OUTPUT_BYTES, "max_queries": MAX_QUERIES}


class _Parts:
    """A bounded expression reservation, not a materialized output string."""

    def __init__(self, *parts):
        self.parts = parts

    def fragments(self):
        for part in self.parts:
            if type(part) is _Parts:
                yield from part.fragments()
            else:
                yield part


def _output_size(value):
    # Count complete generated metadata and lazy expression fragments without
    # constructing their repeated text. No untrusted object class reaches
    # this walk: the complete incoming domain was already JSON-admitted.
    size = 0

    def add(amount):
        nonlocal size
        size += amount
        if size > MAX_OUTPUT_BYTES:
            _fail("complete output exceeds its pre-work reservation")

    def visit(item):
        if type(item) is _Parts:
            add(len('""'))
            for fragment in item.fragments():
                add(exposure._json_size(fragment, MAX_OUTPUT_BYTES) - len('""'))
        elif type(item) is dict:
            add(len("{}"))
            for index, (key, child) in enumerate(item.items()):
                if index:
                    add(len(","))
                visit(key)
                add(len(":"))
                visit(child)
        elif type(item) is list:
            add(len("[]"))
            for index, child in enumerate(item):
                if index:
                    add(len(","))
                visit(child)
        else:
            add(exposure._json_size(item, MAX_OUTPUT_BYTES))

    visit(value)
    return size


def _expression(parts, reserve):
    return parts if reserve else "".join(parts.fragments())


def _page(slug, digest, origin):
    if not measurement._digest(digest):
        _fail("source page generation is not a digest")
    return {"slug": _text(slug), "page_text_sha256": digest, "origin": _text(origin)}


def _page_key(page):
    return page["slug"], page["page_text_sha256"], page["origin"]


def _unique_pages(pages):
    return [dict(zip(("slug", "page_text_sha256", "origin"), key))
            for key in sorted({_page_key(page) for page in pages})]


def _nodes(kw):
    protocol, inputs = kw["retrieval_protocol"], kw["retrieval_inputs"]
    queries = _population(protocol["queries"], MAX_QUERIES, "complete retrieval queries")
    _population(inputs["selection"]["queries"], MAX_QUERIES, "complete selected queries")
    groups = {}
    for group in _population(protocol["groups"], baseline.sialib.MAX_SOURCE_REPLAY_EVENTS, "native groups"):
        identifier = _text(group["id"])
        if identifier in groups:
            _fail("native group identity is duplicated")
        groups[identifier] = group
    pages = {}
    for page in _population(inputs["selection"]["pages"], baseline.sialib.MAX_EVENT_LOOKUP_PAGES, "selected source pages"):
        slug = _text(page["slug"])
        if slug in pages:
            _fail("source page identity is duplicated")
        pages[slug] = page
    result, seen = [], set()
    for query in queries:
        identifier = _text(query["id"])
        if identifier in seen:
            _fail("retrieval query identity is duplicated")
        seen.add(identifier)
        group = groups[query["group_id"]]
        targets = _population(query["targets"], baseline.sialib.MAX_SOURCE_REPLAY_EVENTS, "native target occurrences")
        support = _population(query["eligibility_support"], baseline.sialib.MAX_SOURCE_REPLAY_EVENTS, "eligibility witnesses")
        target_pages = [_page(row["witness"]["slug"], row["witness"]["page_text_sha256"],
                              row["witness"]["origin"]) for row in targets]
        support_pages = [_page(row["slug"], pages[row["slug"]]["text_sha256"],
                               pages[row["slug"]]["origin"]) for row in support]
        if query["split"] not in ("calibration", "heldout"):
            _fail("retrieval query split is invalid")
        result.append({"id": identifier, "class": _text(query["class"]), "split": query["split"],
                       "group_id": query["group_id"], "chain": _text(group["chain"]),
                       "raw_subject": _text(group["subject"]),
                       "target_pages": _unique_pages(target_pages),
                       "support_pages": _unique_pages(support_pages)})
    return sorted(result, key=lambda row: row["id"])


def _components(nodes, retrieval_sha, reserve):
    # Union by explicit incidence avoids pairwise all-query/page comparison.
    # No split/class filtering occurs until the entire graph is connected.
    parent = {node["id"]: node["id"] for node in nodes}

    def find(identifier):
        root = identifier
        while parent[root] != root:
            root = parent[root]
        while parent[identifier] != identifier:
            previous = parent[identifier]
            parent[identifier] = root
            identifier = previous
        return root

    incidence = {}
    for node in nodes:
        edges = [("native-group", node["chain"], node["raw_subject"])]
        edges.extend(("page", page["slug"], page["page_text_sha256"])
                     for role in ("target_pages", "support_pages") for page in node[role])
        for edge in edges:
            previous = incidence.setdefault(edge, node["id"])
            left, right = find(previous), find(node["id"])
            if left != right:
                parent[right] = left
    populations = {}
    for node in nodes:
        populations.setdefault(find(node["id"]), []).append(node)
    result = []
    for population in populations.values():
        ids = sorted(node["id"] for node in population)
        primary = sorted(node["id"] for node in population
                         if node["split"] == _POLICY["split"] and node["class"] == _POLICY["primary_class"])
        identifier = (_PLACEHOLDER if reserve else measurement._sha(measurement._canonical(
            ["sia-cognitive-inference-component-v1", retrieval_sha, ids])))
        result.append({"id": identifier, "query_ids": ids, "primary_query_ids": primary,
                       "group_ids": sorted({node["group_id"] for node in population}),
                       "pages": _unique_pages(page for node in population
                                              for role in ("target_pages", "support_pages") for page in node[role]),
                       "status": "testable" if primary else "not-testable",
                       "reason": None if primary else "no-heldout-primary-members"})
    return sorted(result, key=lambda row: row["id"])


def _protocol_body(kw, reserve):
    protocol = kw["retrieval_protocol"]
    nodes = _nodes(kw)
    components = _components(nodes, kw["expected_retrieval_protocol_sha256"], reserve)
    return {
        "schema": "sia-cognitive-inference-protocol-v1", "status": "prepared-before-arm-results",
        "retrieval_protocol_sha256": kw["expected_retrieval_protocol_sha256"],
        "inference_policy_sha256": kw["expected_inference_policy_sha256"],
        "inference_policy": kw["inference_policy"], "resources": _resources(),
        "source_pins": {key: protocol[key] for key in _SOURCE_PINS},
        "query_nodes": nodes, "components": components,
        "primary_query_ids": sorted(identifier for row in components for identifier in row["primary_query_ids"]),
        "primary_component_ids": sorted(row["id"] for row in components if row["primary_query_ids"]),
        "source_non_claims": {"retrieval": protocol["non_claims"],
                              "retrieval_sources": protocol["source_non_claims"]},
        "non_claims": list(NON_CLAIMS),
    }


def _protocol_preflight(kw):
    _envelope(kw, _PROTOCOL_LAYOUT)
    _policy(kw)
    body = _protocol_body(kw, True)
    body["protocol_sha256"] = _PLACEHOLDER
    return _output_size(body)


def _protocol_pins(kw):
    measurement._pin(kw["inference_policy"], kw["expected_inference_policy_sha256"])
    measurement._pin(kw["retrieval_protocol"], kw["expected_retrieval_protocol_sha256"], "protocol_sha256")


def _finish(body, field, reserved_size):
    body[field] = measurement._sha(exposure._canonical(body, MAX_OUTPUT_BYTES))
    if _output_size(body) != reserved_size:
        _fail("complete output differs from its pre-work byte reservation")
    return body


def _build(kw):
    _protocol_preflight(kw)
    _protocol_pins(kw)
    detached = copy.deepcopy(kw)
    size = _protocol_preflight(detached)
    _protocol_pins(detached)
    replayed = measurement.build_protocol(**detached["retrieval_inputs"])
    if not measurement._same(replayed, detached["retrieval_protocol"]):
        _fail("retrieval protocol differs from its complete independent source replay")
    return _finish(_protocol_body(detached, False), "protocol_sha256", size)


def _requests(arm):
    result = {}
    for row in arm["jackal_requests"]:
        if row["tool"] != "jackal_exact":
            _fail("ordered metric is not an unevaluated exact request")
        _keys(row["arguments"], {"expression"}, "ordered request arguments")
        expression = _text(row["arguments"]["expression"])
        key = (row["scope"]["kind"], row["scope"]["id"], row["metric"], row["k"])
        if key in result:
            _fail("ordered metric request is duplicated")
        result[key] = expression
    return result


def _mean(values, reserve):
    if not values:
        _fail("a component mean has no complete primary members")
    parts = []
    for index, value in enumerate(values):
        if index:
            parts.append("+")
        parts.extend(("(", value, ")"))
    return _expression(_Parts("(", _Parts(*parts), ")/", str(len(values))), reserve)


def _difference(scope, mechanism, comparator, requests, reserve):
    expression = _expression(_Parts("(", mechanism, ")-(", comparator, ")"), reserve)
    core = {"tool": "jackal_exact", "arguments": {"expression": expression}}
    digest = _PLACEHOLDER if reserve else measurement._sha(measurement._canonical(core))
    identifier = (_PLACEHOLDER if reserve else measurement._sha(measurement._canonical(
        ["sia-cognitive-inference-request-v1", scope, digest])))
    requests.append({"id": identifier, **core, "scope": scope, "request_sha256": digest})
    return identifier


def _comparison_rosters(kw):
    protocol = kw["inference_protocol"]
    for key in ("query_nodes", "components", "primary_query_ids", "primary_component_ids"):
        _population(protocol[key], MAX_QUERIES, "complete inference " + key)
    for component in protocol["components"]:
        _population(component["query_ids"], MAX_QUERIES, "component members")
        _population(component["primary_query_ids"], MAX_QUERIES, "component primary members")
    plan = kw["ordered_plan"]
    arms = _population(plan["arms"], len(ordered_module.ARMS), "fixed ordered arms")
    if [arm["name"] for arm in arms] != list(ordered_module.ARMS):
        _fail("complete fixed ordered arms are required")
    for arm in arms:
        _population(arm["queries"], MAX_QUERIES, "complete ordered queries")
        _population(arm["query_orders"], MAX_QUERIES, "complete ordered query references")
        _population(arm["classes"], len(baseline.selection_module.CLASSES), "complete ordered classes")
    replay = kw["ordered_inputs"]["exposure_inputs"]["replay_inputs"]
    for owner in (replay["protocol"], replay["selection"], replay["baseline"],
                  kw["ordered_inputs"]["exposure"],
                  kw["ordered_inputs"]["exposure_inputs"]["measurement_plan"],
                  plan["exposure"], plan["exposure"]["measurement_plan"]):
        _population(owner["queries"], MAX_QUERIES, "complete repeated query document")


def _comparison_body(kw, reserve):
    protocol, plan = kw["inference_protocol"], kw["ordered_plan"]
    policy = kw["inference_inputs"]["inference_policy"]
    arms = {arm["name"]: arm for arm in plan["arms"]}
    expressions = {name: _requests(arm) for name, arm in arms.items()}
    classes = arms["raw-original"]["classes"]
    cutoffs = kw["inference_inputs"]["retrieval_protocol"]["metric_policy"]["cutoffs"]
    _population(cutoffs, baseline.raw_admission.MAX_RESULTS, "complete frozen cutoffs")
    requests, comparisons = [], []
    for comparator in COMPARATORS:
        component_rows, class_rows = [], []
        for component in protocol["components"]:
            ids = component["primary_query_ids"]
            if not ids:
                continue
            values = {}
            means = {}
            for role, name in (("mechanism", policy["mechanism_arm"]), ("comparator", comparator)):
                values[role] = [expressions[name][("query", identifier, policy["primary_metric"], policy["primary_cutoff"])]
                                for identifier in ids]
                means[role] = _mean(values[role], reserve)
            scope = {"kind": "component", "id": component["id"], "comparator": comparator,
                     "metric": policy["primary_metric"], "k": policy["primary_cutoff"]}
            request_id = _difference(scope, means["mechanism"], means["comparator"], requests, reserve)
            component_rows.append({"component_id": component["id"], "query_ids": ids,
                                   "mechanism_expressions": values["mechanism"], "comparator_expressions": values["comparator"],
                                   "mechanism_mean_expression": means["mechanism"], "comparator_mean_expression": means["comparator"],
                                   "request_id": request_id, "status": "prepared-for-jackal"})
        for klass in classes:
            for cutoff in cutoffs:
                for metric in ("recall_at_k", "mrr_at_k"):
                    primary = (klass["class"], metric, cutoff) == (policy["primary_class"], policy["primary_metric"], policy["primary_cutoff"])
                    mechanism_expression = comparator_expression = request_id = None
                    if klass["status"] == "prepared-for-jackal":
                        key = ("class", klass["class"], metric, cutoff)
                        mechanism_expression = expressions[policy["mechanism_arm"]][key]
                        comparator_expression = expressions[comparator][key]
                        scope = {"kind": "class", "id": klass["class"], "comparator": comparator, "metric": metric, "k": cutoff}
                        request_id = _difference(scope, mechanism_expression, comparator_expression, requests, reserve)
                    elif klass["status"] != "unavailable":
                        _fail("a class has no admitted availability status")
                    class_rows.append({"class": klass["class"], "metric": metric, "cutoff": cutoff,
                                       "role": "primary" if primary else "secondary-descriptive",
                                       "query_ids": klass["query_ids"], "status": klass["status"], "reason": klass["reason"],
                                       "mechanism_expression": mechanism_expression, "comparator_expression": comparator_expression,
                                       "request_id": request_id})
        comparisons.append({"comparator": comparator, "component_differences": component_rows,
                            "class_differences": class_rows, "sign_test": {
                                "status": "awaiting-fresh-numeric-admission" if component_rows else "not-testable",
                                "reason": None if component_rows else "no-heldout-primary-members",
                                "component_ids": protocol["primary_component_ids"], "ties": policy["ties"],
                                "no_nonties": policy["no_nonties"], "model_assumptions": policy["model_assumptions"]}})
    return {
        "schema": "sia-cognitive-inference-comparison-plan-v1", "status": "prepared-for-jackal",
        "arithmetic_status": "not-evaluated", "split": plan["split"],
        "inference_protocol": protocol, "inference_protocol_sha256": kw["expected_inference_protocol_sha256"],
        "ordered_plan_sha256": kw["expected_ordered_plan_sha256"],
        "retrieval_protocol_sha256": kw["inference_inputs"]["expected_retrieval_protocol_sha256"],
        "inference_policy_sha256": kw["inference_inputs"]["expected_inference_policy_sha256"],
        "comparisons": comparisons, "jackal_requests": requests,
        "claim_gate": {"status": "not-authorized", "pending": list(PENDING)},
        "source_non_claims": {"inference_protocol": protocol["non_claims"],
                              "inference_sources": protocol["source_non_claims"],
                              "ordered": plan["non_claims"], "ordered_sources": plan["source_non_claims"]},
        "non_claims": list(NON_CLAIMS),
    }


def _comparison_preflight(kw):
    _envelope(kw, _COMPARISON_LAYOUT)
    _protocol_preflight(kw["inference_inputs"])
    _comparison_rosters(kw)
    body = _comparison_body(kw, True)
    body["plan_sha256"] = _PLACEHOLDER
    return _output_size(body)


def _comparison_pins(kw):
    measurement._pin(kw["inference_protocol"], kw["expected_inference_protocol_sha256"], "protocol_sha256")
    measurement._pin(kw["ordered_plan"], kw["expected_ordered_plan_sha256"], "plan_sha256")


def _prepare(kw):
    _comparison_preflight(kw)
    _comparison_pins(kw)
    detached = copy.deepcopy(kw)
    size = _comparison_preflight(detached)
    _comparison_pins(detached)
    protocol = build_inference_protocol(**detached["inference_inputs"])
    if not measurement._same(protocol, detached["inference_protocol"]):
        _fail("inference protocol differs from complete independent source replay")
    plan = ordered_module.prepare_ordered_measurement(**detached["ordered_inputs"])
    if not measurement._same(plan, detached["ordered_plan"]):
        _fail("ordered plan differs from complete independent replay")
    if plan["split"] != "heldout" or plan["protocol_sha256"] != protocol["retrieval_protocol_sha256"]:
        _fail("comparison is not the same frozen heldout retrieval protocol")
    parameters = plan["exposure"]["measurement_plan"]["baseline"]["parameter_freeze"]["parameters"]
    if parameters.get("event_exposure_inference_policy_sha256") != protocol["inference_policy_sha256"] \
            or parameters.get("event_exposure_inference_protocol_sha256") != protocol["protocol_sha256"]:
        _fail("heldout freeze omits or changes an inference policy or component-protocol identity")
    return _finish(_comparison_body(detached, False), "plan_sha256", size)


def _public(call, kw):
    try:
        return call(kw)
    except InferenceRefusal:
        raise
    except (baseline.BaselineRefusal, ValueError, TypeError, KeyError, IndexError,
            OverflowError, RecursionError, AttributeError) as exc:
        error = InferenceRefusal("cognitive inference inputs or replay could not be admitted")
        error.non_claims = list(NON_CLAIMS)
        upstream = {"non_claims": getattr(exc, "non_claims", []),
                    "upstream_non_claims": getattr(exc, "upstream_non_claims", [])}
        try:
            baseline._bounded(upstream, MAX_OUTPUT_BYTES)
        except (baseline.BaselineRefusal, ValueError, TypeError, OverflowError, RecursionError):
            _fail("upstream refusal nonclaims exceed their complete representation bound")
        error.upstream_non_claims = upstream
        raise error from exc


def build_inference_protocol(*, retrieval_protocol, expected_retrieval_protocol_sha256,
                             retrieval_inputs, inference_policy, expected_inference_policy_sha256):
    """Prepare source-only dependency closure before observing any arm results."""
    return _public(_build, locals())


def prepare_inference_comparison(*, inference_protocol, expected_inference_protocol_sha256,
                                 inference_inputs, ordered_plan, expected_ordered_plan_sha256, ordered_inputs):
    """Replay complete pinned inputs and prepare requests, never a verdict."""
    return _public(_prepare, locals())
