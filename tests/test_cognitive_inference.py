"""Source-frozen dependency blocks and unevaluated paired comparison plans.

Only the existing public signed fixtures and owned stopped-process doubles are
used. Root schedules execution. No private results, models, DB, real retrieval,
JACKAL execution, significance admission or win authorization occurs here.

Fixture expressions were routed before writing: status=exact, formal=false;
parsed=1/1-0/1 exact=1; parsed=0/1-1/1 exact=-1;
parsed=0/1-0/1 exact=0;
parsed=(1/1+0/1)/2-(0/1+0/1)/2 exact=1/2.
Nonclaims: NOT formal-bounded: this lane carries no Lean-checked certificate;
The epistemic class above is the STRONGEST claim this result supports;
exact rational arithmetic (not yet checker-covered).
These support fixture literals, not code correctness or observed retrieval.
Resource constants are the existing compound/document/query hard ceilings.

The compact output retains all component/page bindings, policy, requests and
upstream nonclaims. Complete capture, selection and ordered documents remain
externally retained; their identity references are not a source archive.
"""

import contextlib
import copy
import importlib
import inspect
import unittest
from unittest import mock

from tests import test_cognitive_ordered_measurement as ordered_tests
from tests import test_cognitive_ordered_measurement_envelope as ordered_envelope
from tests import test_cognitive_event_exposure_envelope as exposure_envelope
from tests import test_cognitive_inference_policy_freeze as frozen_policy


sha = ordered_tests.sha
canonical = ordered_tests.canonical
body_digest = ordered_tests.body_digest
RESOURCES = {"max_input_bytes": 67108864, "max_document_bytes": 16777216,
             "max_output_bytes": 16777216, "max_queries": 64}
COMPARATORS = ["raw-original", "cue-only"]
PENDING = ["independently-replayed-fidelity", "new-timed-replay",
           "fresh-jackal-numeric-admission", "fresh-jackal-model-admission"]
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


def policy_fixture(protocol_sha256):
    policy = copy.deepcopy(frozen_policy.EXPECTED)
    # Only the independently generated synthetic source identity differs.
    policy["protocol_sha256"] = protocol_sha256
    return policy


def source_layout():
    return {"capture": None, "expected_capture_sha256": None,
            "selection_policy": None, "expected_policy_sha256": None,
            "selection": None, "expected_selection_sha256": None,
            "baseline_contract": None, "expected_baseline_contract_sha256": None,
            "metric_policy": None, "expected_metric_policy_sha256": None}


def protocol_layout():
    return {"retrieval_protocol": None, "expected_retrieval_protocol_sha256": None,
            "retrieval_inputs": source_layout(), "inference_policy": None,
            "expected_inference_policy_sha256": None}


def comparison_layout():
    return {"inference_protocol": None, "expected_inference_protocol_sha256": None,
            "inference_inputs": protocol_layout(), "ordered_plan": None,
            "expected_ordered_plan_sha256": None,
            "ordered_inputs": ordered_envelope.expected_layout()}


def mean_expression(expressions):
    # Render observed constituents without evaluating or simplifying them.
    return "(" + "+".join("(" + item + ")" for item in expressions) + ")/" + str(len(expressions))


class CognitiveInference(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("siacognitiveinference")
        except ModuleNotFoundError as exc:
            self.fail("source-replayed inference protocol and comparison APIs must exist: " + str(exc))
        for name in ("build_inference_protocol", "prepare_inference_comparison"):
            self.assertTrue(callable(getattr(self.module, name, None)), name)
        self.assertTrue(hasattr(self.module, "InferenceRefusal"))
        self.fx = ordered_tests.CognitiveOrderedMeasurement(methodName="runTest")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.fixture = self.fx.fx.fixture
        self.measurement = importlib.import_module("siacognitivemeasure")
        self.ordered = importlib.import_module("siacognitiveorderedmeasure")

    def _history(self, *, bridge=False, primary=True):
        rows = self.fixture._signed_rows()
        if primary:
            rows[3][2] = "OUTCOME:restart"
        additions = [("2026-01-08T01:00:00Z", "CHECK:unit", "isolated.service", "healthy")]
        if primary:
            # Distinct primary queries in one native group make complete
            # component means a non-singleton contract, without new subjects.
            additions += [("2026-01-03T01:00:00Z", "OUTCOME:check", "pipewire.service", "requested"),
                          ("2026-01-04T01:00:00Z", "OUTCOME:check", "pipewire.service", "ok")]
        if bridge:
            additions += [("2026-01-03T01:00:00Z", "INTENT:inspect", "wireplumber.service", "bridge-only"),
                          ("2026-01-05T01:00:00Z", "INTENT:inspect", "pipewire.service", "bridge-only")]
        for timestamp, action, subject, value in additions:
            row = list(rows[-1])
            row[1], row[2], row[3], row[4] = timestamp, action, subject, value
            rows.append(row)
        for sequence, row in enumerate(rows):
            row[0] = str(sequence)
        self.fixture._resign_fixture(rows)

    def _source_kwargs(self, inputs):
        protocol = self.measurement.build_protocol(**inputs)
        policy = policy_fixture(protocol["protocol_sha256"])
        return {"retrieval_protocol": protocol,
                "expected_retrieval_protocol_sha256": protocol["protocol_sha256"],
                "retrieval_inputs": copy.deepcopy(inputs), "inference_policy": policy,
                "expected_inference_policy_sha256": sha(canonical(policy))}

    def _source_inputs(self, *, bridge=False, primary=True):
        self._history(bridge=bridge, primary=primary)
        self.fixture._inputs("heldout")
        with self.fixture._pure():
            self.pk = self._source_kwargs(self.fixture.pk)

    def _inputs(self, *, choices=None, split="heldout", freeze="correct", padding=None):
        self._history()
        original_freeze = self.fixture._freeze
        original_capture = self.fixture._capture

        def capture_with_provenance():
            capture = original_capture()
            if padding is not None:
                capture["source_non_claims"].append(padding)
                capture["capture_sha256"] = body_digest(capture, "capture_sha256")
            return capture

        def frozen_before_observation():
            value = original_freeze()
            self.pk = self._source_kwargs(self.fixture.pk)
            with self.fixture._pure():
                protocol = self.module.build_inference_protocol(**self.pk)
            pins = {"event_exposure_inference_policy_sha256": self.pk["expected_inference_policy_sha256"],
                    "event_exposure_inference_protocol_sha256": protocol["protocol_sha256"]}
            for key, pin in pins.items():
                if freeze != "missing-" + key:
                    value["parameters"][key] = "0" * 64 if freeze == "foreign-" + key else pin
            value["parameters_sha256"] = sha(canonical(value["parameters"]))
            value["freeze_sha256"] = body_digest(value, "freeze_sha256")
            self.fixture.kw["expected_parameter_freeze_sha256"] = value["freeze_sha256"]
            return value

        if choices is None:
            def choices(fixture):
                rows = [("events/aegis/2026-01-01", 0), ("events/aegis/2026-01-03", 0),
                        ("events/aegis/2026-01-04", 0)]
                return {query["id"]: rows for query in fixture._queries()}
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(self.fixture, "_freeze", side_effect=frozen_before_observation))
            stack.enter_context(mock.patch.object(self.fixture, "_capture", side_effect=capture_with_provenance))
            stack.enter_context(mock.patch.object(ordered_tests, "policy_fixture", side_effect=ordered_envelope.policy_fixture))
            stack.enter_context(mock.patch.object(ordered_tests.exposure_tests, "policy_fixture", side_effect=exposure_envelope.policy_fixture))
            self.fx._inputs(split=split, choices=choices)
        with self.fixture._pure():
            self.pk = self._source_kwargs(self.fixture.pk)
            protocol = self.module.build_inference_protocol(**self.pk)
        ordered = self.fx._call(self.ordered)
        self.kw = {"inference_protocol": protocol,
                   "expected_inference_protocol_sha256": protocol["protocol_sha256"],
                   "inference_inputs": copy.deepcopy(self.pk), "ordered_plan": ordered,
                   "expected_ordered_plan_sha256": ordered["plan_sha256"],
                   "ordered_inputs": copy.deepcopy(self.fx.kw)}

    def _protocol(self, **overrides):
        with self.fixture._pure(), mock.patch("time.time", side_effect=AssertionError("pure inference read clock")):
            return self.module.build_inference_protocol(**{**self.pk, **overrides})

    def _comparison(self, **overrides):
        with self.fixture._pure(), mock.patch("time.time", side_effect=AssertionError("pure inference read clock")):
            return self.module.prepare_inference_comparison(**{**self.kw, **overrides})

    def _policy_override(self, policy):
        return {"inference_policy": policy, "expected_inference_policy_sha256": sha(canonical(policy))}

    def _arm(self, name):
        return next(arm for arm in self.kw["ordered_plan"]["arms"] if arm["name"] == name)

    def _request(self, arm, kind, identifier, metric, cutoff):
        return next(row for row in self._arm(arm)["jackal_requests"]
                    if row["scope"] == {"kind": kind, "id": identifier}
                    and row["metric"] == metric and row["k"] == cutoff)

    def _no_work(self):
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch("copy.deepcopy", side_effect=AssertionError("copy before complete reservation")))
        stack.enter_context(mock.patch("hashlib.sha256", side_effect=AssertionError("hash before complete reservation")))
        stack.enter_context(mock.patch.object(self.measurement, "build_protocol", side_effect=AssertionError("source replay before complete reservation")))
        stack.enter_context(mock.patch.object(self.ordered, "prepare_ordered_measurement", side_effect=AssertionError("ordered replay before complete reservation")))
        return stack

    def test_public_apis_are_closed_keyword_only_and_accept_no_results_or_win_override(self):
        for name, layout in (("build_inference_protocol", protocol_layout()),
                             ("prepare_inference_comparison", comparison_layout())):
            parameters = inspect.signature(getattr(self.module, name)).parameters
            self.assertEqual(set(parameters), set(layout))
            for parameter in parameters.values():
                self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(parameter.default, inspect.Parameter.empty)
        self._source_inputs()
        for forbidden in ("baseline", "arm_results", "numeric_results", "trusted_protocol", "choose_arm", "win"):
            with self.subTest(field=forbidden), self.assertRaises(TypeError):
                self._protocol(**{forbidden: {}})

    def test_protocol_replays_full_source_before_detached_deterministic_component_output(self):
        self._source_inputs()
        before = copy.deepcopy(self.pk)
        with mock.patch.object(self.measurement, "build_protocol", wraps=self.measurement.build_protocol) as replay:
            result = self._protocol()
        self.assertEqual(replay.call_args_list, [mock.call(**self.pk["retrieval_inputs"])])
        self.assertEqual(result, self._protocol())
        self.assertEqual(result["schema"], "sia-cognitive-inference-protocol-v1")
        self.assertEqual(result["status"], "prepared-before-arm-results")
        self.assertEqual(result["protocol_sha256"], body_digest(result, "protocol_sha256"))
        self.assertEqual(result["retrieval_protocol_sha256"], self.pk["expected_retrieval_protocol_sha256"])
        self.assertEqual(result["inference_policy"], self.pk["inference_policy"])
        self.assertEqual(result["inference_policy_sha256"], self.pk["expected_inference_policy_sha256"])
        self.assertEqual(result["resources"], RESOURCES)
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertEqual(result["source_non_claims"], {
            "retrieval": self.pk["retrieval_protocol"]["non_claims"],
            "retrieval_sources": self.pk["retrieval_protocol"]["source_non_claims"]})
        for forbidden in ("capture", "retrieval_inputs", "baseline", "ordered_plan", "jackal_requests", "win"):
            self.assertNotIn(forbidden, result)
        result["components"].clear()
        result["source_non_claims"].clear()
        result["inference_policy"]["comparators"].clear()
        self.assertEqual(self.pk, before)

    def test_query_nodes_bind_complete_native_groups_targets_support_generations_and_origins(self):
        self._source_inputs()
        result = self._protocol()
        protocol = self.pk["retrieval_protocol"]
        pages = {page["slug"]: page for page in self.pk["retrieval_inputs"]["selection"]["pages"]}
        groups = {group["id"]: group for group in protocol["groups"]}
        nodes = {node["id"]: node for node in result["query_nodes"]}
        self.assertEqual(set(nodes), {query["id"] for query in protocol["queries"]})
        for query in protocol["queries"]:
            node = nodes[query["id"]]
            expected_targets = {canonical({key: target["witness"][key]
                                          for key in ("slug", "page_text_sha256", "origin")})
                                for target in query["targets"]}
            expected_support = {canonical({"slug": witness["slug"],
                                           "page_text_sha256": pages[witness["slug"]]["text_sha256"],
                                           "origin": pages[witness["slug"]]["origin"]})
                                for witness in query["eligibility_support"]}
            self.assertEqual({canonical(page) for page in node["target_pages"]}, expected_targets)
            self.assertEqual({canonical(page) for page in node["support_pages"]}, expected_support)
            self.assertEqual(node["group_id"], query["group_id"])
            self.assertEqual(node["chain"], groups[query["group_id"]]["chain"])
            self.assertEqual(node["raw_subject"], groups[query["group_id"]]["subject"])
            self.assertEqual((node["class"], node["split"]), (query["class"], query["split"]))
        contrast = next(node for node in nodes.values() if node["class"] == "recency-heavy" and node["split"] == "heldout")
        self.assertNotEqual(contrast["target_pages"], contrast["support_pages"])

    def test_complete_graph_preserves_transitive_secondary_calibration_bridges_and_non_testable_components(self):
        self._source_inputs(bridge=True)
        result = self._protocol()
        nodes = {node["id"]: node for node in result["query_nodes"]}
        self.assertEqual(sorted(query for component in result["components"] for query in component["query_ids"]), sorted(nodes))
        connected = next(component for component in result["components"]
                         if any(nodes[identifier]["raw_subject"] == "pipewire.service" for identifier in component["query_ids"]))
        self.assertEqual({nodes[identifier]["raw_subject"] for identifier in connected["query_ids"]},
                         {"wireplumber.service", "pipewire.service", "bluetooth.service"})
        self.assertTrue(any(nodes[identifier]["split"] == "calibration" for identifier in connected["query_ids"]))
        self.assertTrue(any(nodes[identifier]["class"] != "recency-heavy" for identifier in connected["query_ids"]))
        for component in result["components"]:
            members = component["query_ids"]
            primary = sorted(identifier for identifier in members
                             if nodes[identifier]["split"] == "heldout" and nodes[identifier]["class"] == "recency-heavy")
            self.assertEqual(members, sorted(members))
            self.assertEqual(component["primary_query_ids"], primary)
            self.assertEqual(component["group_ids"], sorted({nodes[identifier]["group_id"] for identifier in members}))
            expected_pages = {canonical(page) for identifier in members
                              for role in ("target_pages", "support_pages") for page in nodes[identifier][role]}
            self.assertEqual({canonical(page) for page in component["pages"]}, expected_pages)
            self.assertEqual(component["id"], sha(canonical(["sia-cognitive-inference-component-v1",
                                                           self.pk["expected_retrieval_protocol_sha256"], members])))
            self.assertEqual(component["status"], "testable" if primary else "not-testable")
            self.assertEqual(component["reason"], None if primary else "no-heldout-primary-members")
        isolated = next(component for component in result["components"] if component is not connected)
        self.assertEqual({nodes[identifier]["raw_subject"] for identifier in isolated["query_ids"]}, {"isolated.service"})
        self.assertEqual(result["primary_component_ids"], sorted(component["id"] for component in result["components"]
                                                                 if component["primary_query_ids"]))
        self.assertEqual(result["primary_query_ids"], sorted(identifier for identifier, node in nodes.items()
                                                             if node["split"] == "heldout" and node["class"] == "recency-heavy"))

    def test_no_primary_members_remain_explicit_without_fabricated_testability(self):
        self._source_inputs(primary=False)
        result = self._protocol()
        self.assertTrue(result["query_nodes"])
        self.assertEqual(result["primary_query_ids"], [])
        self.assertEqual(result["primary_component_ids"], [])
        self.assertTrue(all(component["status"] == "not-testable" for component in result["components"]))

    def test_rehashed_protocol_rows_are_not_an_independent_source_of_groups_pages_or_targets(self):
        self._source_inputs()
        for change in ("group", "target-generation", "origin", "support", "class", "missing-query", "nonclaims"):
            protocol = copy.deepcopy(self.pk["retrieval_protocol"])
            query = protocol["queries"][-1]
            if change == "group":
                protocol["groups"][-1]["subject"] = "foreign.service"
            elif change == "target-generation":
                query["targets"][0]["witness"]["page_text_sha256"] = "0" * 64
            elif change == "origin":
                query["targets"][0]["witness"]["origin"] = "model"
            elif change == "support":
                query["eligibility_support"] = []
            elif change == "class":
                query["class"] = "recency-heavy" if query["class"] != "recency-heavy" else "novelty"
            elif change == "missing-query":
                protocol["queries"].pop()
            else:
                protocol["source_non_claims"] = {}
            self.assertNotEqual(protocol, self.pk["retrieval_protocol"], change)
            protocol["protocol_sha256"] = body_digest(protocol, "protocol_sha256")
            policy = policy_fixture(protocol["protocol_sha256"])
            with self.subTest(change=change), self.assertRaises(self.module.InferenceRefusal):
                self._protocol(retrieval_protocol=protocol,
                               expected_retrieval_protocol_sha256=protocol["protocol_sha256"], **self._policy_override(policy))

    def test_frozen_policy_is_closed_and_cannot_drop_comparator_assumptions_or_nonclaims(self):
        self._source_inputs()
        for key in self.pk["inference_policy"]:
            policy = copy.deepcopy(self.pk["inference_policy"])
            del policy[key]
            with self.subTest(missing=key), self.assertRaises(self.module.InferenceRefusal):
                self._protocol(**self._policy_override(policy))
        for key, value in (("comparators", ["raw-original"]), ("primary_cutoff", True),
                           ("primary_class", "novelty"), ("split", "calibration"),
                           ("model_assumptions", []), ("non_claims", []),
                           ("components", "primary-only-before-graph"), ("ties", "drop-before-means"),
                           ("per_comparison_alpha", "1/20"), ("win", True)):
            policy = copy.deepcopy(self.pk["inference_policy"])
            policy[key] = value
            with self.subTest(changed=key), self.assertRaises(self.module.InferenceRefusal):
                self._protocol(**self._policy_override(policy))

    def test_comparison_replays_both_complete_documents_and_retains_compact_bindings(self):
        self._inputs()
        before = copy.deepcopy(self.kw)
        with mock.patch.object(self.module, "build_inference_protocol", wraps=self.module.build_inference_protocol) as source, \
                mock.patch.object(self.ordered, "prepare_ordered_measurement", wraps=self.ordered.prepare_ordered_measurement) as ordered:
            result = self._comparison()
        self.assertEqual(source.call_args_list, [mock.call(**self.kw["inference_inputs"])])
        self.assertEqual(ordered.call_args_list, [mock.call(**self.kw["ordered_inputs"])])
        self.assertEqual(result, self._comparison())
        self.assertEqual(result["schema"], "sia-cognitive-inference-comparison-plan-v1")
        self.assertEqual(result["status"], "prepared-for-jackal")
        self.assertEqual(result["arithmetic_status"], "not-evaluated")
        self.assertEqual(result["plan_sha256"], body_digest(result, "plan_sha256"))
        self.assertEqual(result["inference_protocol"], self.kw["inference_protocol"])
        self.assertEqual(result["inference_protocol_sha256"], self.kw["expected_inference_protocol_sha256"])
        self.assertEqual(result["ordered_plan_sha256"], self.kw["expected_ordered_plan_sha256"])
        self.assertEqual(result["retrieval_protocol_sha256"], self.pk["expected_retrieval_protocol_sha256"])
        self.assertEqual(result["inference_policy_sha256"], self.pk["expected_inference_policy_sha256"])
        self.assertEqual(result["split"], "heldout")
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertEqual(result["source_non_claims"], {
            "inference_protocol": self.kw["inference_protocol"]["non_claims"],
            "inference_sources": self.kw["inference_protocol"]["source_non_claims"],
            "ordered": self.kw["ordered_plan"]["non_claims"],
            "ordered_sources": self.kw["ordered_plan"]["source_non_claims"]})
        for forbidden in ("ordered_plan", "ordered_inputs", "capture", "baseline"):
            self.assertNotIn(forbidden, result)
        result["inference_protocol"]["components"].clear()
        result["source_non_claims"].clear()
        self.assertEqual(self.kw, before)

    def test_component_difference_requests_use_every_primary_member_and_both_fixed_comparators(self):
        self._inputs()
        result = self._comparison()
        self.assertEqual([row["comparator"] for row in result["comparisons"]], COMPARATORS)
        components = [component for component in self.kw["inference_protocol"]["components"] if component["primary_query_ids"]]
        self.assertTrue(components, "synthetic heldout contrast must be nonvacuous")
        source_queries = {query["id"]: query for query in self.pk["retrieval_protocol"]["queries"]}
        self.assertEqual({source_queries[identifier]["action"] for component in components
                          for identifier in component["primary_query_ids"]}, {"OUTCOME:restart", "OUTCOME:check"})
        requests = {request["id"]: request for request in result["jackal_requests"]}
        for comparison in result["comparisons"]:
            rows = comparison["component_differences"]
            self.assertEqual({row["component_id"] for row in rows}, {component["id"] for component in components})
            for row in rows:
                component = next(item for item in components if item["id"] == row["component_id"])
                ids = component["primary_query_ids"]
                self.assertEqual(row["query_ids"], ids)
                expressions = {}
                for role, arm in (("mechanism", "cue-event-exposure"), ("comparator", comparison["comparator"])):
                    observed = [self._request(arm, "query", identifier, "recall_at_k", 1)["arguments"]["expression"] for identifier in ids]
                    self.assertEqual(row[role + "_expressions"], observed)
                    self.assertEqual(row[role + "_mean_expression"], mean_expression(observed))
                    expressions[role] = mean_expression(observed)
                request = requests[row["request_id"]]
                self.assertEqual(request["tool"], "jackal_exact")
                self.assertEqual(request["arguments"], {"expression": "(" + expressions["mechanism"] + ")-(" + expressions["comparator"] + ")"})
                self.assertEqual(request["scope"], {"kind": "component", "id": component["id"],
                                                    "comparator": comparison["comparator"], "metric": "recall_at_k", "k": 1})
                self.assertEqual(request["request_sha256"], sha(canonical({"tool": request["tool"], "arguments": request["arguments"]})))
                self.assertEqual(row["status"], "prepared-for-jackal")

    def test_all_classes_cutoffs_secondary_metrics_and_unavailable_scopes_are_retained(self):
        self._inputs()
        result = self._comparison()
        raw_classes = self._arm("raw-original")["classes"]
        cutoffs = self.pk["retrieval_protocol"]["metric_policy"]["cutoffs"]
        expected = {(row["class"], metric, cutoff) for row in raw_classes
                    for cutoff in cutoffs for metric in ("recall_at_k", "mrr_at_k")}
        requests = {request["id"]: request for request in result["jackal_requests"]}
        self.assertTrue(any(row["status"] == "unavailable" for row in raw_classes))
        for comparison in result["comparisons"]:
            rows = comparison["class_differences"]
            self.assertEqual({(row["class"], row["metric"], row["cutoff"]) for row in rows}, expected)
            for row in rows:
                klass = next(item for item in raw_classes if item["class"] == row["class"])
                self.assertEqual(row["query_ids"], klass["query_ids"])
                is_primary = (row["class"], row["metric"], row["cutoff"]) == ("recency-heavy", "recall_at_k", 1)
                self.assertEqual(row["role"], "primary" if is_primary else "secondary-descriptive")
                self.assertEqual(row["status"], klass["status"])
                self.assertEqual(row["reason"], klass["reason"])
                if klass["status"] == "unavailable":
                    self.assertIsNone(row["request_id"])
                    self.assertIsNone(row["mechanism_expression"])
                    self.assertIsNone(row["comparator_expression"])
                    continue
                mechanism = self._request("cue-event-exposure", "class", row["class"], row["metric"], row["cutoff"])["arguments"]["expression"]
                comparator = self._request(comparison["comparator"], "class", row["class"], row["metric"], row["cutoff"])["arguments"]["expression"]
                self.assertEqual((row["mechanism_expression"], row["comparator_expression"]), (mechanism, comparator))
                self.assertEqual(requests[row["request_id"]]["arguments"], {"expression": "(" + mechanism + ")-(" + comparator + ")"})

    def test_positive_primary_and_secondary_loss_requests_never_authorize_a_win(self):
        self._inputs()
        result = self._comparison()
        primary = next(query for query in self.pk["retrieval_protocol"]["queries"]
                       if query["split"] == "heldout" and query["class"] == "recency-heavy")
        novelty = next(query for query in self.pk["retrieval_protocol"]["queries"]
                       if query["split"] == "heldout" and query["class"] == "novelty" and query["action"] == "OUTCOME:restart")
        for comparator in COMPARATORS:
            self.assertEqual(self._request("cue-event-exposure", "query", primary["id"], "recall_at_k", 1)["arguments"]["expression"], "1/1")
            self.assertEqual(self._request(comparator, "query", primary["id"], "recall_at_k", 1)["arguments"]["expression"], "0/1")
        self.assertEqual(self._request("cue-event-exposure", "query", novelty["id"], "recall_at_k", 1)["arguments"]["expression"], "0/1")
        self.assertEqual(self._request("cue-only", "query", novelty["id"], "recall_at_k", 1)["arguments"]["expression"], "1/1")
        self.assertEqual(result["claim_gate"], {"status": "not-authorized", "pending": PENDING})
        for comparison in result["comparisons"]:
            sign = comparison["sign_test"]
            self.assertEqual(sign["status"], "awaiting-fresh-numeric-admission")
            self.assertEqual(sign["component_ids"], self.kw["inference_protocol"]["primary_component_ids"])
            self.assertEqual(sign["ties"], self.pk["inference_policy"]["ties"])
            self.assertEqual(sign["no_nonties"], self.pk["inference_policy"]["no_nonties"])
            self.assertEqual(sign["model_assumptions"], self.pk["inference_policy"]["model_assumptions"])
        for node in (result, *result["comparisons"], *(row["sign_test"] for row in result["comparisons"])):
            for forbidden in ("win", "p_value", "positive_count", "negative_count", "tie_count", "n", "k", "exact", "significant"):
                self.assertNotIn(forbidden, node)
        self.assertTrue(all(row["tool"] == "jackal_exact" for row in result["jackal_requests"]))

    def test_empty_candidate_ties_do_not_shrink_components_or_descriptive_denominators(self):
        self._inputs(choices={})
        result = self._comparison()
        for comparison in result["comparisons"]:
            self.assertEqual([row["component_id"] for row in comparison["component_differences"]],
                             self.kw["inference_protocol"]["primary_component_ids"])
            for row in comparison["component_differences"]:
                self.assertEqual(row["mechanism_expressions"], row["comparator_expressions"])
                self.assertTrue(row["query_ids"])
            self.assertEqual(comparison["sign_test"]["status"], "awaiting-fresh-numeric-admission")
        self.assertEqual(result["claim_gate"], {"status": "not-authorized", "pending": PENDING})

    def test_rehashed_inference_components_cannot_split_drop_or_promote_source_members(self):
        self._inputs()
        for change in ("membership", "primary-members", "component", "source-generation", "nonclaims"):
            protocol = copy.deepcopy(self.kw["inference_protocol"])
            if change == "membership":
                protocol["components"][0]["query_ids"].pop()
            elif change == "primary-members":
                protocol["primary_query_ids"] = []
            elif change == "component":
                protocol["components"].pop()
            elif change == "source-generation":
                protocol["query_nodes"][-1]["target_pages"][0]["page_text_sha256"] = "0" * 64
            else:
                protocol["source_non_claims"] = {}
            protocol["protocol_sha256"] = body_digest(protocol, "protocol_sha256")
            with self.subTest(change=change), self.assertRaises(self.module.InferenceRefusal):
                self._comparison(inference_protocol=protocol, expected_inference_protocol_sha256=protocol["protocol_sha256"])

    def test_rehashed_ordered_outcomes_or_missing_losses_cannot_replace_full_replay(self):
        self._inputs()
        for change in ("expression", "missing-secondary", "targets", "nonclaims"):
            plan = copy.deepcopy(self.kw["ordered_plan"])
            if change == "expression":
                plan["arms"][-1]["jackal_requests"][0]["arguments"]["expression"] = "1/1"
                if plan == self.kw["ordered_plan"]:
                    plan["arms"][-1]["jackal_requests"][0]["arguments"]["expression"] = "0/1"
            elif change == "missing-secondary":
                plan["arms"][-1]["classes"].pop()
            elif change == "targets":
                plan["arms"][-1]["queries"][-1]["targets"] = []
            else:
                plan["source_non_claims"] = {}
            self.assertNotEqual(plan, self.kw["ordered_plan"], change)
            plan["plan_sha256"] = body_digest(plan, "plan_sha256")
            with self.subTest(change=change), self.assertRaises(self.module.InferenceRefusal):
                self._comparison(ordered_plan=plan, expected_ordered_plan_sha256=plan["plan_sha256"])

    def test_independent_pins_are_required_for_source_protocol_policy_and_ordered_inputs(self):
        self._inputs()
        for field in ("expected_retrieval_protocol_sha256", "expected_inference_policy_sha256"):
            with self.subTest(field=field), self.assertRaises(self.module.InferenceRefusal):
                self._protocol(**{field: "0" * 64})
        for field in ("expected_inference_protocol_sha256", "expected_ordered_plan_sha256"):
            with self.subTest(field=field), self.assertRaises(self.module.InferenceRefusal):
                self._comparison(**{field: "0" * 64})
        for field in ("expected_capture_sha256", "expected_policy_sha256", "expected_selection_sha256",
                      "expected_baseline_contract_sha256", "expected_metric_policy_sha256"):
            inputs = copy.deepcopy(self.pk["retrieval_inputs"])
            inputs[field] = "0" * 64
            with self.subTest(field=field), self.assertRaises(self.module.InferenceRefusal):
                self._protocol(retrieval_inputs=inputs)

    def test_heldout_freeze_requires_inference_policy_pin_before_observation(self):
        self._inputs(freeze="missing-event_exposure_inference_policy_sha256")
        with self.assertRaises(self.module.InferenceRefusal):
            self._comparison()

    def test_heldout_freeze_requires_source_component_protocol_pin_before_observation(self):
        self._inputs(freeze="foreign-event_exposure_inference_protocol_sha256")
        with self.assertRaises(self.module.InferenceRefusal):
            self._comparison()

    def test_calibration_cannot_be_relabelled_as_frozen_heldout_inference(self):
        self._inputs(split="calibration")
        with self.assertRaises(self.module.InferenceRefusal):
            self._comparison()

    def test_literal_envelope_layout_keeps_repeated_sources_and_ordered_documents_whole(self):
        self._inputs()
        envelope = importlib.import_module("siacognitiveenvelope")
        for call_api, kwargs, layout in ((self._protocol, self.pk, protocol_layout()),
                                          (self._comparison, self.kw, comparison_layout())):
            with mock.patch.object(envelope, "admit_compound", wraps=envelope.admit_compound) as admission:
                call_api()
            calls = [call for call in admission.call_args_list if set(call.kwargs["envelope"]) == set(kwargs)]
            self.assertTrue(calls)
            for call in calls:
                self.assertEqual(call.kwargs["envelope"], kwargs)
                self.assertEqual(call.kwargs["layout"], layout)
                self.assertEqual(call.kwargs["max_input_bytes"], RESOURCES["max_input_bytes"])
                self.assertEqual(call.kwargs["max_document_bytes"], RESOURCES["max_document_bytes"])

    def test_late_cycle_or_nonfinite_input_refuses_before_copy_hash_serialization_or_replay(self):
        self._inputs()
        cycle = {}
        cycle["cycle"] = cycle
        for invalid in (cycle, {"late": float("nan")}, {"late": float("inf")}):
            inputs = copy.deepcopy(self.kw["ordered_inputs"])
            inputs["exposure_inputs"]["replay_inputs"]["capture"] = invalid
            with self.subTest(invalid=type(invalid).__name__), self._no_work(), \
                    mock.patch("json.dumps", side_effect=AssertionError("serialization before complete domain admission")), \
                    self.assertRaises(self.module.InferenceRefusal):
                self._comparison(ordered_inputs=inputs)

    def test_document_and_compound_and_query_limits_precede_copy_hash_or_replay(self):
        self._inputs()
        for name in ("MAX_INPUT_BYTES", "MAX_DOCUMENT_BYTES", "MAX_OUTPUT_BYTES", "MAX_QUERIES"):
            self.assertEqual(getattr(self.module, name), RESOURCES[name.lower()])
        for name in ("MAX_DOCUMENT_BYTES", "MAX_INPUT_BYTES", "MAX_QUERIES"):
            with self.subTest(limit=name), mock.patch.object(self.module, name, 1), self._no_work(), \
                    self.assertRaises(self.module.InferenceRefusal):
                self._comparison()
        # Repeat the identical whole protocol object in both admitted locations.
        # A below-compound cap still above every whole document must refuse:
        # aliases do not discount their repeated serialized occurrences.
        kwargs = copy.deepcopy(self.kw)
        kwargs["inference_inputs"]["retrieval_protocol"] = self.pk["retrieval_protocol"]
        kwargs["ordered_inputs"]["exposure_inputs"]["replay_inputs"]["protocol"] = self.pk["retrieval_protocol"]
        def documents(value, layout):
            if layout is None:
                yield value
            else:
                for key, child in layout.items():
                    yield from documents(value[key], child)
        largest_document = max(len(canonical(document)) for document in documents(kwargs, comparison_layout()))
        self.assertLess(largest_document, len(canonical(kwargs)))
        with mock.patch.object(self.module, "MAX_INPUT_BYTES", largest_document), \
                mock.patch.object(self.module, "MAX_DOCUMENT_BYTES", largest_document), self._no_work(), \
                self.assertRaises(self.module.InferenceRefusal):
            self._comparison(**kwargs)

    def test_valid_variable_upstream_nonclaims_are_retained_and_fully_reserved_before_work(self):
        # This is admitted source provenance, not an invalid result-row mutation.
        padding = "Retained synthetic provenance, not historical authentication. " * 4096
        self._inputs(padding=padding)
        protocol = self._protocol()
        comparison = self._comparison()
        self.assertIn(padding, protocol["source_non_claims"]["retrieval_sources"]["history"]["generator"])
        self.assertIn(padding, canonical(comparison["source_non_claims"]).decode("utf-8"))
        for api, result in ((self._protocol, protocol), (self._comparison, comparison)):
            # This observed budget covers the full provenance subtree alone,
            # but not its enclosing bindings, requests and repeated retention.
            # Complete reservation must precede hashing or upstream replay.
            cap = len(canonical(result["source_non_claims"]))
            self.assertLess(cap, len(canonical(result)))
            with self.subTest(api=api.__name__), mock.patch.object(self.module, "MAX_OUTPUT_BYTES", cap), \
                    self._no_work(), self.assertRaises(self.module.InferenceRefusal):
                api()


if __name__ == "__main__":
    unittest.main()
