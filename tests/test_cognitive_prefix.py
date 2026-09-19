"""Preregistered raw prefix comparison; no locally evaluated selector or win.

Root alone schedules these tests. Full synthetic signed capture and owned v2
baseline doubles feed the actual public source/measurement replay APIs. No
private query/outcome files, model, database, clock worker or JACKAL call is
test input. Existing measurement fixture arithmetic/status/nonclaims remain
controlling; expected expressions here are syntax over public request strings,
not evaluated arithmetic or fabricated benchmark numbers.

The policy's numerical literals are the existing frozen retrieval cutoffs and
resource ceilings. Full source, both raw observations and public measurement
documents remain externally retained; compact identities are not an archive.
"""

import contextlib
import copy
import importlib
import inspect
import json
from pathlib import Path
import unittest
from unittest import mock

from tests import test_cognitive_measurement as measurement_tests
from tests import test_raw_vector_admission as raw_tests


sha = measurement_tests.sha
canonical = measurement_tests.canonical
body_digest = measurement_tests.body_digest
ARMS = ["bare", "nomic-search-prefixes"]
CLASSES = ["recency-heavy", "repetition-heavy", "novelty",
           "associative-multi-hop", "consolidation-gist"]
CUTOFFS = [1, 3, 5, 10]
METRICS = ["recall_at_k", "mrr_at_k"]
RESOURCES = {"max_input_bytes": 67108864, "max_document_bytes": 16777216,
             "max_output_bytes": 16777216, "max_queries": 64}
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


def embedding_policy(arm):
    return {"schema": "sia-embedding-input-policy-v1",
            "mode": "bare-v1" if arm == "bare" else "nomic-prefix-v1",
            "document_prefix": "" if arm == "bare" else "search_document: ",
            "query_prefix": "" if arm == "bare" else "search_query: ",
            "encoding": "utf-8", "document_stage": "after-lossless-chunking",
            "query_stage": "original-query", "overflow": "refuse"}


def policy_fixture():
    return {
        "schema": "sia-cognitive-raw-prefix-comparison-policy-v1", "split": "heldout",
        "arms": ARMS.copy(), "classes": CLASSES.copy(), "cutoffs": CUTOFFS.copy(),
        "metrics": METRICS.copy(),
        "embedding_input_policies": {arm: embedding_policy(arm) for arm in ARMS},
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
        "non_claims": NON_CLAIMS.copy(),
    }


def source_layout():
    return {"capture": None, "expected_capture_sha256": None,
            "selection_policy": None, "expected_policy_sha256": None,
            "selection": None, "expected_selection_sha256": None,
            "baseline_contract": None, "expected_baseline_contract_sha256": None,
            "metric_policy": None, "expected_metric_policy_sha256": None}


def protocol_layout():
    return {"arm_sources": {arm: source_layout() for arm in ARMS},
            "comparison_policy": None, "expected_comparison_policy_sha256": None,
            "original_parameter_freeze": None, "expected_original_parameter_freeze_sha256": None}


def comparison_layout():
    return {"prefix_protocol": None, "expected_prefix_protocol_sha256": None,
            "protocol_inputs": protocol_layout(),
            "observations": {arm: {"baseline": None, "expected_baseline_sha256": None,
                                   "expected_parameter_freeze_sha256": None} for arm in ARMS}}


def mean_expression(expressions):
    # Pure string construction; the public constituent requests are not scored.
    return "(" + "+".join("(" + item + ")" for item in expressions) + ")/" + str(len(expressions))


class RawPrefixPolicyFreeze(unittest.TestCase):
    def test_policy_file_is_the_complete_closed_preregistered_selector(self):
        path = Path(__file__).resolve().parents[1] / "benchmarks/cognitive/raw-prefix-baseline-comparison-v1.json"
        self.assertTrue(path.is_file(), "raw prefix comparison policy must be frozen before arm scoring")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), policy_fixture())


class CognitivePrefix(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("siacognitiveprefix")
        except ModuleNotFoundError as exc:
            self.fail("source-replayed raw prefix comparison APIs must exist: " + str(exc))
        for name in ("prepare_raw_prefix_protocol", "prepare_raw_prefix_comparison"):
            self.assertTrue(callable(getattr(self.module, name, None)), name)
        self.assertTrue(hasattr(self.module, "PrefixRefusal"))
        self.measurement = importlib.import_module("siacognitivemeasure")

    def _pure(self):
        return self.fx._pure()

    def _source_inputs(self):
        prefix_tests = importlib.import_module("tests.test_cognitive_baseline_prefix")
        self.fx = prefix_tests.PrefixBaselineFixture(methodName="runTest")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.fx._inputs(importlib.import_module("siacognitivebaseline"), "heldout", mode="bare-v1")
        self.fx.kw["limit"] = CUTOFFS[-1]
        original = self.fx._freeze()
        # The independently pinned original belongs to the legacy raw lane,
        # not either newly built v2 arm. It is retained, never relabeled.
        legacy_contract = self.fx._contract()
        legacy_contract["schema"] = "sia-cognitive-baseline-contract-v1"
        del legacy_contract["embedding_input_policy"]
        del legacy_contract["embedding_input_policy_sha256"]
        original["baseline_contract_sha256"] = sha(canonical(legacy_contract))
        original["parameters"]["measurement_protocol_sha256"] = sha(b"original legacy measurement protocol")
        original["parameters_sha256"] = sha(canonical(original["parameters"]))
        original["freeze_sha256"] = body_digest(original, "freeze_sha256")
        sources = {}
        for arm in ARMS:
            policy = embedding_policy(arm)
            self.fx.kw["embedding_input_policy"] = policy
            self.fx.kw["expected_embedding_input_policy_sha256"] = sha(canonical(policy))
            sources[arm] = self.fx._source_inputs()
            sources[arm]["metric_policy"]["cutoffs"] = CUTOFFS.copy()
            sources[arm]["expected_metric_policy_sha256"] = sha(canonical(sources[arm]["metric_policy"]))
        policy = policy_fixture()
        self.pk = {"arm_sources": sources, "comparison_policy": policy,
                   "expected_comparison_policy_sha256": sha(canonical(policy)),
                   "original_parameter_freeze": original,
                   "expected_original_parameter_freeze_sha256": original["freeze_sha256"]}
        with self._pure():
            self.protocols = {arm: self.measurement.build_protocol(**sources[arm]) for arm in ARMS}

    def _inputs(self, *, hits=None):
        self._source_inputs()
        protocol = self._protocol()
        hits = {"bare": False, "nomic-search-prefixes": True} if hits is None else hits
        observations, self.plans, self.measurement_inputs = {}, {}, {}
        self.arm_control_traces = {}
        for arm in ARMS:
            self.fx.calls = []
            policy = embedding_policy(arm)
            self.fx.kw["embedding_input_policy"] = policy
            self.fx.kw["expected_embedding_input_policy_sha256"] = sha(canonical(policy))
            self.fx.kw["output_directory"] = str(self.fx.root / ("prefix-comparison-" + arm))
            freeze = self.fx._freeze()
            freeze["parameters"] = {
                **copy.deepcopy(self.pk["original_parameter_freeze"]["parameters"]),
                "measurement_protocol_sha256": self.protocols[arm]["protocol_sha256"],
                "raw_prefix_comparison_policy_sha256": self.pk["expected_comparison_policy_sha256"],
                "raw_prefix_comparison_protocol_sha256": protocol["protocol_sha256"],
            }
            freeze["parameters_sha256"] = sha(canonical(freeze["parameters"]))
            freeze["freeze_sha256"] = body_digest(freeze, "freeze_sha256")
            self.fx.kw["parameter_freeze"] = freeze
            self.fx.kw["expected_parameter_freeze_sha256"] = freeze["freeze_sha256"]
            targets = {row["id"]: row["targets"] for row in self.protocols[arm]["queries"]}

            def observe(**kwargs):
                value = self.fx._observe(**kwargs)
                for row in value["query"]["payload"]["results"]:
                    witness = targets[row["id"]][0]["witness"]
                    choices = [(witness["slug"], witness["chunk_index"])] if hits[arm] else []
                    raw_tests._bind_rows(row, measurement_tests.CognitiveMeasurement._rows(self.fx, choices))
                    # Existing supplied timing literals; neither combined nor
                    # converted into a selector value or timing improvement.
                    row["latency_ms"] = {"embedding": 1.25, "search": 2.5}
                value["query"]["payload"]["latency_ms"] = {"total": 7.75}
                value["capture"]["payload"]["latency_ms"] = {"total": 3.25}
                for operation in ("capture", "query"):
                    value[operation]["stdout_sha256"] = sha(canonical(value[operation]["payload"]))
                return value

            with self.fx._controls(observe=observe):
                observed = self.fx._run()
            self.arm_control_traces[arm] = list(self.fx.calls)
            observations[arm] = {"baseline": observed, "expected_baseline_sha256": observed["artifact_sha256"],
                                 "expected_parameter_freeze_sha256": freeze["freeze_sha256"]}
            replay = {**copy.deepcopy(self.pk["arm_sources"][arm]), "protocol": self.protocols[arm],
                      "expected_protocol_sha256": self.protocols[arm]["protocol_sha256"], **observations[arm]}
            self.measurement_inputs[arm] = replay
            with self._pure():
                self.plans[arm] = self.measurement.prepare_measurement(**replay)
        self.kw = {"prefix_protocol": protocol, "expected_prefix_protocol_sha256": protocol["protocol_sha256"],
                   "protocol_inputs": copy.deepcopy(self.pk), "observations": observations}

    def _protocol(self, **overrides):
        with self._pure(), mock.patch("time.time", side_effect=AssertionError("prefix protocol read a clock")):
            return self.module.prepare_raw_prefix_protocol(**{**self.pk, **overrides})

    def _comparison(self, **overrides):
        with self._pure(), mock.patch("time.time", side_effect=AssertionError("prefix comparison read a clock")):
            return self.module.prepare_raw_prefix_comparison(**{**self.kw, **overrides})

    def _no_work(self):
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch("copy.deepcopy", side_effect=AssertionError("copy before complete reservation")))
        stack.enter_context(mock.patch("hashlib.sha256", side_effect=AssertionError("hash before complete reservation")))
        stack.enter_context(mock.patch.object(self.measurement, "build_protocol",
                                             side_effect=AssertionError("source replay before complete reservation")))
        stack.enter_context(mock.patch.object(self.measurement, "prepare_measurement",
                                             side_effect=AssertionError("measurement replay before complete reservation")))
        return stack

    def _policy(self, changed):
        return {"comparison_policy": changed, "expected_comparison_policy_sha256": sha(canonical(changed))}

    def test_public_apis_are_closed_keyword_only_with_no_numeric_results_or_adoption_override(self):
        for name, layout in (("prepare_raw_prefix_protocol", protocol_layout()),
                             ("prepare_raw_prefix_comparison", comparison_layout())):
            parameters = inspect.signature(getattr(self.module, name)).parameters
            self.assertEqual(set(parameters), set(layout))
            for parameter in parameters.values():
                self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(parameter.default, inspect.Parameter.empty)
        for name in ("prepare_raw_prefix_protocol", "prepare_raw_prefix_comparison"):
            for field in ("numeric_results", "scores", "selected_arm", "trusted", "skip_replay", "win"):
                with self.subTest(api=name, field=field), self.assertRaises(TypeError):
                    getattr(self.module, name)(**{field: {}})

    def test_protocol_replays_both_complete_sources_before_detached_deterministic_output(self):
        self._source_inputs()
        before = copy.deepcopy(self.pk)
        with mock.patch.object(self.measurement, "build_protocol", wraps=self.measurement.build_protocol) as replay:
            result = self._protocol()
        self.assertEqual(replay.call_args_list, [mock.call(**self.pk["arm_sources"][arm]) for arm in ARMS])
        self.assertEqual(result, self._protocol())
        self.assertEqual(result["schema"], "sia-cognitive-raw-prefix-protocol-v1")
        self.assertEqual(result["status"], "prepared-before-arm-results")
        self.assertEqual(result["protocol_sha256"], body_digest(result, "protocol_sha256"))
        self.assertEqual(result["comparison_policy"], policy_fixture())
        self.assertEqual(result["comparison_policy_sha256"], self.pk["expected_comparison_policy_sha256"])
        self.assertEqual(result["original_parameter_freeze_sha256"], self.pk["expected_original_parameter_freeze_sha256"])
        for source in self.pk["arm_sources"].values():
            self.assertNotEqual(self.pk["original_parameter_freeze"]["baseline_contract_sha256"],
                                source["expected_baseline_contract_sha256"])
        self.assertEqual(result["resources"], RESOURCES)
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertEqual(result["source_non_claims"], {
            "arms": {arm: {"retrieval": self.protocols[arm]["non_claims"],
                            "retrieval_sources": self.protocols[arm]["source_non_claims"]} for arm in ARMS},
            "original_freeze": self.pk["original_parameter_freeze"]["non_claims"],
        })
        for forbidden in ("capture", "arm_sources", "baseline", "observations", "jackal_requests", "selected_arm", "win"):
            self.assertNotIn(forbidden, result)
        result["queries"].clear()
        result["comparison_policy"]["arms"].clear()
        result["source_non_claims"].clear()
        self.assertEqual(self.pk, before)

    def test_preregistration_binds_full_original_query_group_target_origin_and_coverage_rosters(self):
        self._source_inputs()
        result = self._protocol()
        original = self.protocols["bare"]
        for field in ("queries", "groups", "coverage", "exclusions"):
            self.assertEqual(result[field], original[field], field)
        self.assertEqual(result["source_pins"], {
            key: original[key] for key in ("capture_sha256", "policy_sha256", "selection_sha256", "pages_sha256",
                                          "metric_policy_sha256")})
        self.assertEqual([row["name"] for row in result["arms"]], ARMS)
        for row in result["arms"]:
            arm = row["name"]
            contract = self.pk["arm_sources"][arm]["baseline_contract"]
            self.assertEqual(row["retrieval_protocol_sha256"], self.protocols[arm]["protocol_sha256"])
            self.assertEqual(row["baseline_contract_sha256"], self.pk["arm_sources"][arm]["expected_baseline_contract_sha256"])
            self.assertEqual(row["embedding_input_policy"], embedding_policy(arm))
            self.assertEqual(row["embedding_input_policy_sha256"], contract["embedding_input_policy_sha256"])
        heldout = [row for row in original["queries"] if row["split"] == "heldout"]
        self.assertEqual(result["heldout_query_ids"], [row["id"] for row in heldout])
        self.assertEqual([row["class"] for row in result["class_roster"]], CLASSES)
        for klass in result["class_roster"]:
            ids = [row["id"] for row in heldout if row["class"] == klass["class"]]
            self.assertEqual(klass["query_ids"], ids)
            self.assertEqual(klass["status"], "prepared-before-arm-results" if ids else "unavailable")
            if not ids:
                self.assertIsInstance(klass["reason"], str)
        self.assertEqual(result["selector_class_ids"], [klass for klass in CLASSES
                                                       if any(row["class"] == klass for row in heldout)])

    def test_closed_policy_rejects_tuning_weights_metric_order_classes_or_prefix_convention(self):
        self._source_inputs()
        original = policy_fixture()
        for field in original:
            changed = copy.deepcopy(original)
            if isinstance(changed[field], list):
                changed[field] = list(reversed(changed[field])) + ["undeclared"]
            elif isinstance(changed[field], dict):
                changed[field]["undeclared"] = "cannot add an arm"
            else:
                changed[field] = "later choice"
            with self.subTest(field=field), self.assertRaises(self.module.PrefixRefusal):
                self._protocol(**self._policy(changed))
        changed = {**original, "weight_by_query_count": True}
        with self.assertRaises(self.module.PrefixRefusal):
            self._protocol(**self._policy(changed))

    def test_same_sealed_runner_model_runtime_limit_and_all_nonprefix_contract_fields_are_required(self):
        self._source_inputs()
        for field in ("adapter", "preparer", "embedding", "model", "runtime", "code_expectations", "limit", "timeout"):
            inputs = copy.deepcopy(self.pk["arm_sources"])
            contract = inputs[ARMS[-1]]["baseline_contract"]
            if field in ("adapter", "preparer"):
                contract[field]["expected"]["executable_sha256"] = sha(b"different sealed executable")
            elif field == "embedding":
                contract[field]["model"] = "ollama:other-model"
            elif field == "model":
                contract[field]["manifest_sha256"] = sha(b"different model manifest")
            elif field == "runtime":
                contract[field][0]["sha256"] = sha(b"different runtime")
            elif field == "code_expectations":
                contract[field]["files"]["sia"] = sha(b"different Python producer")
            elif field == "limit":
                contract[field] = CUTOFFS[0]
            else:
                contract[field] = True
            inputs[ARMS[-1]]["expected_baseline_contract_sha256"] = sha(canonical(contract))
            with self.subTest(field=field), self.assertRaises(self.module.PrefixRefusal):
                self._protocol(arm_sources=inputs)

    def test_v1_or_prefix_only_relabeling_cannot_stand_in_for_explicit_v2_contract_pair(self):
        self._source_inputs()
        for mutation in ("v1", "same-mode", "prefix-byte", "prefix-hash", "pre-chunk", "truncate"):
            inputs = copy.deepcopy(self.pk["arm_sources"])
            contract = inputs[ARMS[-1]]["baseline_contract"]
            policy = contract["embedding_input_policy"]
            if mutation == "v1":
                contract["schema"] = "sia-cognitive-baseline-contract-v1"
                del contract["embedding_input_policy"]
                del contract["embedding_input_policy_sha256"]
            else:
                if mutation == "same-mode":
                    contract["embedding_input_policy"] = embedding_policy("bare")
                elif mutation == "prefix-byte":
                    policy["query_prefix"] = "search_query:"
                elif mutation == "pre-chunk":
                    policy["document_stage"] = "before-chunking"
                elif mutation == "truncate":
                    policy["overflow"] = "truncate"
                contract["embedding_input_policy_sha256"] = (sha(b"different policy") if mutation == "prefix-hash"
                    else sha(canonical(contract["embedding_input_policy"])))
            inputs[ARMS[-1]]["expected_baseline_contract_sha256"] = sha(canonical(contract))
            with self.subTest(mutation=mutation), self.assertRaises(self.module.PrefixRefusal):
                self._protocol(arm_sources=inputs)

    def test_source_text_origin_target_and_protocol_identity_drift_refuse_despite_new_self_hashes(self):
        self._source_inputs()
        for field in ("text", "origin", "targets", "metric_policy"):
            inputs = copy.deepcopy(self.pk["arm_sources"])
            source = inputs[ARMS[-1]]
            if field in ("text", "origin"):
                source["selection"]["pages"][0][field] = "mutated original source"
                source["selection"]["selection_sha256"] = body_digest(source["selection"], "selection_sha256")
                source["expected_selection_sha256"] = source["selection"]["selection_sha256"]
            elif field == "targets":
                source["selection"]["answer_key"][0]["answer"]["sequences"] = []
                source["selection"]["selection_sha256"] = body_digest(source["selection"], "selection_sha256")
                source["expected_selection_sha256"] = source["selection"]["selection_sha256"]
            else:
                source["metric_policy"]["cutoffs"] = [CUTOFFS[0]]
                source["expected_metric_policy_sha256"] = sha(canonical(source["metric_policy"]))
            with self.subTest(field=field), self.assertRaises(self.module.PrefixRefusal):
                self._protocol(arm_sources=inputs)

    def test_original_freeze_is_independently_pinned_and_matches_captured_source(self):
        self._source_inputs()
        with self.assertRaises(self.module.PrefixRefusal):
            self._protocol(expected_original_parameter_freeze_sha256=sha(b"foreign original freeze"))
        for field in ("capture_sha256", "policy_sha256", "selection_sha256", "tuning_split"):
            value = copy.deepcopy(self.pk["original_parameter_freeze"])
            value[field] = "heldout" if field == "tuning_split" else sha(b"foreign source generation")
            value["freeze_sha256"] = body_digest(value, "freeze_sha256")
            with self.subTest(field=field), self.assertRaises(self.module.PrefixRefusal):
                self._protocol(original_parameter_freeze=value,
                               expected_original_parameter_freeze_sha256=value["freeze_sha256"])

    def test_refusal_carries_full_component_nonclaims_without_a_partial_plan(self):
        self._source_inputs()
        with self.assertRaises(self.module.PrefixRefusal) as refused:
            self._protocol(expected_comparison_policy_sha256=sha(b"independent foreign policy"))
        self.assertEqual(refused.exception.non_claims, NON_CLAIMS)
        self.assertFalse(hasattr(refused.exception, "selected_arm"))

    def test_comparison_replays_preregistration_then_both_complete_public_measurements(self):
        self._inputs()
        before = copy.deepcopy(self.kw)
        with (mock.patch.object(self.module, "prepare_raw_prefix_protocol",
                                wraps=self.module.prepare_raw_prefix_protocol) as source,
              mock.patch.object(self.measurement, "prepare_measurement",
                                wraps=self.measurement.prepare_measurement) as replay):
            result = self._comparison()
        source.assert_called_once_with(**self.kw["protocol_inputs"])
        self.assertEqual(replay.call_args_list, [mock.call(**self.measurement_inputs[arm]) for arm in ARMS])
        self.assertEqual(result, self._comparison())
        self.assertEqual(result["schema"], "sia-cognitive-raw-prefix-comparison-v1")
        self.assertEqual(result["status"], "prepared-for-jackal")
        self.assertEqual(result["arithmetic_status"], "not-evaluated")
        self.assertEqual(result["split"], "heldout")
        self.assertEqual(result["plan_sha256"], body_digest(result, "plan_sha256"))
        self.assertEqual(result["prefix_protocol"], self.kw["prefix_protocol"])
        self.assertEqual(result["prefix_protocol_sha256"], self.kw["expected_prefix_protocol_sha256"])
        self.assertEqual(result["comparison_policy_sha256"], self.pk["expected_comparison_policy_sha256"])
        self.assertEqual(result["resources"], RESOURCES)
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertEqual(result["adoption"], {"status": "unadmitted", "reason": "fresh-jackal-results-required"})
        self.assertEqual(result["claim_gate"], {"status": "not-authorized",
                                               "reason": "baseline-selection-is-not-cognitive-authorization"})
        self.assertEqual(result["source_non_claims"], {
            "protocol": self.kw["prefix_protocol"]["non_claims"],
            "protocol_sources": self.kw["prefix_protocol"]["source_non_claims"],
            "arms": {arm: {"measurement": self.plans[arm]["non_claims"],
                            "measurement_sources": self.plans[arm]["source_non_claims"]} for arm in ARMS},
        })
        for forbidden in ("selected_arm", "win", "p_value", "numeric_results", "capture", "observations"):
            self.assertNotIn(forbidden, result)
        result["arms"].clear()
        result["source_non_claims"].clear()
        result["prefix_protocol"]["queries"].clear()
        self.assertEqual(self.kw, before)

    def test_each_independent_arm_retains_its_exact_prepare_observe_control_trace(self):
        self._inputs()
        self.assertEqual(self.arm_control_traces, {
            "bare": ["prepare", "observe"],
            "nomic-search-prefixes": ["prepare", "observe"],
        })
        self.assertIsNot(self.arm_control_traces["bare"], self.arm_control_traces["nomic-search-prefixes"])
        self.assertIsNot(self.arm_control_traces["bare"], self.fx.calls)
        self.assertIsNot(self.arm_control_traces["nomic-search-prefixes"], self.fx.calls)

    def test_all_original_query_class_requests_and_raw_latency_scopes_are_retained(self):
        self._inputs()
        result = self._comparison()
        self.assertEqual([row["name"] for row in result["arms"]], ARMS)
        for row in result["arms"]:
            arm = row["name"]
            source, plan = self.kw["observations"][arm], self.plans[arm]
            self.assertEqual(row["baseline_sha256"], source["expected_baseline_sha256"])
            self.assertEqual(row["baseline_contract_sha256"], plan["baseline_contract_sha256"])
            self.assertEqual(row["retrieval_protocol_sha256"], plan["protocol_sha256"])
            self.assertEqual(row["parameter_freeze_sha256"], source["expected_parameter_freeze_sha256"])
            self.assertEqual(row["measurement_plan_sha256"], plan["plan_sha256"])
            self.assertEqual(row["query_roster_sha256"], plan["query_roster_sha256"])
            self.assertEqual(row["query_ids"], [query["id"] for query in plan["queries"]])
            self.assertEqual(row["classes"], plan["classes"])
            self.assertEqual(row["jackal_requests"], plan["jackal_requests"])
            observed = source["baseline"]["observation"]
            self.assertEqual(row["latency_observations"], {
                "queries": [{"id": query["id"], "latency_ms": query["latency_ms"]}
                            for query in observed["query"]["payload"]["results"]],
                "operations": {operation: observed[operation]["payload"]["latency_ms"]
                               for operation in ("capture", "query")},
                "parent_elapsed_ms": {operation: observed[operation]["elapsed_ms"]
                                      for operation in ("capture", "query") if "elapsed_ms" in observed[operation]},
            })
            for klass in row["classes"]:
                if klass["status"] == "unavailable":
                    self.assertEqual(klass["query_ids"], [])
                    self.assertIsInstance(klass["reason"], str)

    def test_selector_is_class_balanced_complete_and_fixed_recall_then_mrr_order(self):
        self._inputs()
        result = self._comparison()
        selector = result["selector"]
        self.assertEqual(selector["status"], "awaiting-fresh-jackal")
        self.assertEqual(selector["class_ids"], self.kw["prefix_protocol"]["selector_class_ids"])
        self.assertEqual(selector["selection"], policy_fixture()["selection"])
        self.assertEqual(selector["full_tie"], policy_fixture()["full_tie"])
        self.assertEqual([(row["metric"], row["k"]) for row in selector["coordinates"]],
                         [(metric, cutoff) for metric in METRICS for cutoff in CUTOFFS])
        requests = {row["request_sha256"]: row for row in result["jackal_requests"]}
        self.assertEqual(len(requests), len(result["jackal_requests"]))
        referenced = set()
        for coordinate in selector["coordinates"]:
            metric, cutoff = coordinate["metric"], coordinate["k"]
            self.assertEqual(coordinate["class_ids"], selector["class_ids"])
            self.assertEqual(set(coordinate["requests"]), {*ARMS, "difference"})
            expressions = {}
            for arm in ARMS:
                constituent = []
                for klass in selector["class_ids"]:
                    original = next(row for row in self.plans[arm]["jackal_requests"]
                                    if row["scope"] == {"kind": "class", "id": klass}
                                    and row["metric"] == metric and row["k"] == cutoff)
                    constituent.append(original["arguments"]["expression"])
                expressions[arm] = mean_expression(constituent)
                identifier = coordinate["requests"][arm]
                request = requests[identifier]
                self.assertEqual(request["tool"], "jackal_exact")
                self.assertEqual(request["arguments"], {"expression": expressions[arm]})
                self.assertEqual(request["scope"], {"kind": "class-balanced-selector", "arm": arm,
                                                    "metric": metric, "k": cutoff,
                                                    "class_ids": selector["class_ids"]})
                self.assertEqual(identifier, body_digest(request, "request_sha256"))
                referenced.add(identifier)
            identifier = coordinate["requests"]["difference"]
            request = requests[identifier]
            self.assertEqual(request["tool"], "jackal_exact")
            self.assertEqual(request["arguments"], {
                "expression": "(" + expressions[ARMS[-1]] + ")-(" + expressions[ARMS[0]] + ")"})
            self.assertEqual(request["scope"], {"kind": "class-balanced-difference", "metric": metric,
                                                "k": cutoff, "class_ids": selector["class_ids"]})
            self.assertEqual(identifier, body_digest(request, "request_sha256"))
            referenced.add(identifier)
        self.assertEqual(referenced, set(requests))

    def test_full_tie_and_bare_advantage_are_not_locally_adopted_or_hidden(self):
        for hits in ({"bare": False, "nomic-search-prefixes": False},
                     {"bare": True, "nomic-search-prefixes": False}):
            with self.subTest(hits=hits):
                self._inputs(hits=hits)
                result = self._comparison()
                self.assertEqual([row["name"] for row in result["arms"]], ARMS)
                for row in result["arms"]:
                    self.assertEqual(row["jackal_requests"], self.plans[row["name"]]["jackal_requests"])
                self.assertEqual(result["adoption"]["status"], "unadmitted")
                self.assertEqual(result["selector"]["full_tie"], policy_fixture()["full_tie"])
                self.assertNotIn("selected_arm", result)
                self.assertNotIn("sign", result["selector"])

    def test_external_arm_pins_and_complete_replay_reject_self_authenticating_result_changes(self):
        self._inputs()
        for arm in ARMS:
            changed = copy.deepcopy(self.kw["observations"])
            changed[arm]["expected_baseline_sha256"] = sha(b"foreign independently supplied raw pin")
            with self.subTest(arm=arm, mutation="external-pin"), self.assertRaises(self.module.PrefixRefusal):
                self._comparison(observations=changed)
            changed = copy.deepcopy(self.kw["observations"])
            raw = changed[arm]["baseline"]
            raw["retrieval_rows"][0]["rows"] = [{"slug": "forged-target-credit"}]
            raw["artifact_sha256"] = body_digest(raw, "artifact_sha256")
            changed[arm]["expected_baseline_sha256"] = raw["artifact_sha256"]
            with self.subTest(arm=arm, mutation="rehashed-result"), self.assertRaises(self.module.PrefixRefusal):
                self._comparison(observations=changed)
        with mock.patch.object(self.measurement, "prepare_measurement",
                               side_effect=self.measurement.MeasurementRefusal("synthetic upstream refusal")):
            with self.assertRaises(self.module.PrefixRefusal):
                self._comparison()

    def test_new_arm_freezes_bind_protocol_policy_and_original_parameters_even_when_both_drift_identically(self):
        self._inputs()
        for field in ("raw_prefix_comparison_policy_sha256", "raw_prefix_comparison_protocol_sha256",
                      "measurement_protocol_sha256", "usage_decay", "undeclared_parameter", "removed_original"):
            changed = copy.deepcopy(self.kw["observations"])
            for arm in ARMS:
                raw = changed[arm]["baseline"]
                freeze = raw["parameter_freeze"]
                if field.startswith("raw_prefix"):
                    del freeze["parameters"][field]
                elif field == "removed_original":
                    del freeze["parameters"]["policy"]
                else:
                    freeze["parameters"][field] = "identical late drift in both arms"
                freeze["parameters_sha256"] = sha(canonical(freeze["parameters"]))
                freeze["freeze_sha256"] = body_digest(freeze, "freeze_sha256")
                raw["parameter_freeze_sha256"] = freeze["freeze_sha256"]
                raw["artifact_sha256"] = body_digest(raw, "artifact_sha256")
                changed[arm]["expected_baseline_sha256"] = raw["artifact_sha256"]
                changed[arm]["expected_parameter_freeze_sha256"] = freeze["freeze_sha256"]
            with self.subTest(field=field), self.assertRaises(self.module.PrefixRefusal):
                self._comparison(observations=changed)

    def test_calibration_reference_cannot_drift_in_one_or_both_rehashed_arm_freezes(self):
        self._inputs()
        original_reference = self.pk["original_parameter_freeze"]["calibration_run_sha256"]
        for affected in ((ARMS[0],), (ARMS[-1],), tuple(ARMS)):
            changed = copy.deepcopy(self.kw["observations"])
            parameters = {arm: copy.deepcopy(changed[arm]["baseline"]["parameter_freeze"]["parameters"])
                          for arm in ARMS}
            for arm in affected:
                raw = changed[arm]["baseline"]
                freeze = raw["parameter_freeze"]
                freeze["calibration_run_sha256"] = sha(b"different calibration provenance, unchanged coefficients")
                self.assertNotEqual(freeze["calibration_run_sha256"], original_reference)
                freeze["freeze_sha256"] = body_digest(freeze, "freeze_sha256")
                raw["parameter_freeze_sha256"] = freeze["freeze_sha256"]
                raw["artifact_sha256"] = body_digest(raw, "artifact_sha256")
                changed[arm]["expected_baseline_sha256"] = raw["artifact_sha256"]
                changed[arm]["expected_parameter_freeze_sha256"] = freeze["freeze_sha256"]
            for arm in ARMS:
                self.assertEqual(changed[arm]["baseline"]["parameter_freeze"]["parameters"], parameters[arm])
            with self.subTest(affected=affected), self.assertRaises(self.module.PrefixRefusal):
                self._comparison(observations=changed)

    def test_rehashed_preregistration_cannot_change_selector_members_or_original_targets(self):
        self._inputs()
        for field in ("heldout_query_ids", "selector_class_ids", "queries"):
            changed = copy.deepcopy(self.kw["prefix_protocol"])
            changed[field] = []
            changed["protocol_sha256"] = body_digest(changed, "protocol_sha256")
            with self.subTest(field=field), self.assertRaises(self.module.PrefixRefusal):
                self._comparison(prefix_protocol=changed, expected_prefix_protocol_sha256=changed["protocol_sha256"])

    def test_missing_extra_duplicate_or_wrong_named_arms_cannot_shrink_comparison_population(self):
        self._inputs()
        for name in ("arm_sources", "observations"):
            original = self.pk["arm_sources"] if name == "arm_sources" else self.kw["observations"]
            missing = copy.deepcopy(original)
            del missing[ARMS[-1]]
            extra = {**original, "prefixed": original[ARMS[-1]]}
            renamed = {"bare": original["bare"], "prefixed": original[ARMS[-1]]}
            for changed in (missing, extra, renamed, [original["bare"], original["bare"]]):
                with self.subTest(field=name, kind=type(changed).__name__), self.assertRaises(self.module.PrefixRefusal):
                    if name == "arm_sources":
                        self._protocol(arm_sources=changed)
                    else:
                        self._comparison(observations=changed)

    def test_complete_compound_whole_document_roster_precedes_copy_hash_and_replay(self):
        self._inputs()
        for method, inputs, layout in ((self._protocol, self.pk, protocol_layout()),
                                       (self._comparison, self.kw, comparison_layout())):
            with (self.subTest(api=method.__name__), self._no_work(),
                  mock.patch.object(self.module.envelope, "admit_compound",
                                    side_effect=ValueError("complete compound refused")) as admitted):
                with self.assertRaises(self.module.PrefixRefusal):
                    method()
            admitted.assert_called_once_with(envelope=inputs, layout=layout,
                                             max_input_bytes=RESOURCES["max_input_bytes"],
                                             max_document_bytes=RESOURCES["max_document_bytes"])

    def test_late_cycle_nonfinite_extra_pin_or_oversized_document_refuses_before_any_work(self):
        self._inputs()
        mutations = []
        cycle = copy.deepcopy(self.kw)
        cycle["observations"][ARMS[-1]]["baseline"]["source_non_claims"]["cycle"] = cycle
        mutations.append(cycle)
        nonfinite = copy.deepcopy(self.kw)
        nonfinite["observations"][ARMS[-1]]["baseline"]["extra"] = float("nan")
        mutations.append(nonfinite)
        extra = copy.deepcopy(self.kw)
        extra["observations"][ARMS[-1]]["undeclared_pin"] = sha(b"must not be ignored")
        mutations.append(extra)
        long_text = copy.deepcopy(self.kw)
        long_text["observations"][ARMS[-1]]["baseline"]["source_non_claims"]["long"] = "x" * RESOURCES["max_document_bytes"]
        mutations.append(long_text)
        for changed in mutations:
            with self.subTest(kind=next(iter(changed))), self._no_work(), self.assertRaises(self.module.PrefixRefusal):
                self._comparison(**changed)

    def test_output_and_full_variable_nonclaim_reservations_precede_hash_or_replay(self):
        self._inputs()
        for method in (self._protocol, self._comparison):
            with (self.subTest(api=method.__name__), mock.patch.object(self.module, "MAX_OUTPUT_BYTES", 1),
                  self._no_work(), self.assertRaises(self.module.PrefixRefusal)):
                method()
        # Repeated source nonclaims are real document content, not discounted
        # by shared-reference identity or a fixed metadata allowance.
        changed = copy.deepcopy(self.kw)
        shared = "variable source boundary " * RESOURCES["max_queries"]
        changed["protocol_inputs"]["original_parameter_freeze"]["non_claims"].append(shared)
        for arm in ARMS:
            changed["observations"][arm]["baseline"]["source_non_claims"]["extra"] = shared
        with (mock.patch.object(self.module, "MAX_OUTPUT_BYTES", len(shared)), self._no_work(),
              self.assertRaises(self.module.PrefixRefusal)):
            self._comparison(**changed)


if __name__ == "__main__":
    unittest.main()
