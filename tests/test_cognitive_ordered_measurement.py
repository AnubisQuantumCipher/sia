"""Ordered summaries reuse raw native-target coverage, never raw admission bypasses.

Only synthetic signed-history fixtures and existing stopped-process doubles
are used. Root alone schedules tests. No private real artifact, model, DB,
retrieval run, tuning decision, or JACKAL execution occurs in this suite.

Fixture fractions routed before writing: status=exact, formal=false;
parsed=0/1 exact=0; parsed=1/1 exact=1; parsed=1/2 exact=1/2;
parsed=1/3 exact=1/3; parsed=2/2 exact=1; parsed=0/2 exact=0.
Nonclaims: NOT formal-bounded: this lane carries no Lean-checked certificate;
The epistemic class above is the STRONGEST claim this result supports;
exact rational arithmetic (not yet checker-covered).
These results support fixture literals, not code correctness or retrieval wins.
Resource values and row references are existing declared fixture inputs.
"""

import copy
import importlib
import inspect
import unittest
from unittest import mock

from tests import test_cognitive_event_exposure as exposure_tests
from tests import test_cognitive_measurement as measurement_tests


sha = measurement_tests.sha
canonical = measurement_tests.canonical
body_digest = measurement_tests.body_digest
ARMS = exposure_tests.ARMS
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


def policy_fixture(protocol_sha256):
    limits = exposure_tests.policy_fixture(protocol_sha256)["resources"]
    return {
        "schema": "sia-cognitive-ordered-measurement-policy-v1",
        "exposure_schema": "sia-cognitive-event-exposure-v1",
        "metric_protocol_sha256": protocol_sha256,
        "arms": list(ARMS),
        "ordering": "replayed-row-reference-bijection-v1",
        "targets": "replayed-raw-native-occurrence-coverage-v1",
        "queries": "complete-observed-split-roster-v1",
        "summaries": "frozen-retrieval-policy-cutoffs-and-class-means-v1",
        "latencies": "retain-raw-no-rerank-timing-v1",
        "resources": {key: limits[key] for key in (
            "max_input_bytes", "max_output_bytes", "max_queries")},
    }


class CognitiveOrderedMeasurement(unittest.TestCase):
    def setUp(self):
        self.fx = exposure_tests.CognitiveEventExposure(methodName="runTest")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)

    def _module(self):
        try:
            module = importlib.import_module("siacognitiveorderedmeasure")
        except ModuleNotFoundError as exc:
            self.fail("independently replayed ordered measurement API must exist: " + str(exc))
        self.assertTrue(callable(getattr(module, "prepare_ordered_measurement", None)))
        self.assertTrue(hasattr(module, "OrderedMeasurementRefusal"))
        measurement = importlib.import_module("siacognitivemeasure")
        self.assertTrue(callable(getattr(measurement, "_summarize_coverage", None)))
        return module

    def _inputs(self, *, split="calibration", choices=None, freeze_ordered="correct"):
        fixture = self.fx.fixture
        original_freeze = fixture._freeze

        def frozen_before_observation():
            # These declarations precede even the synthetic baseline run.
            value = original_freeze()
            measurement = importlib.import_module("siacognitivemeasure")
            protocol = fixture._protocol(measurement)
            policy = policy_fixture(protocol["protocol_sha256"])
            if freeze_ordered != "missing":
                value["parameters"]["ordered_measurement_policy_sha256"] = (
                    sha(canonical(policy)) if freeze_ordered == "correct" else "0" * 64)
            value["parameters_sha256"] = sha(canonical(value["parameters"]))
            value["freeze_sha256"] = body_digest(value, "freeze_sha256")
            fixture.kw["expected_parameter_freeze_sha256"] = value["freeze_sha256"]
            return value

        with mock.patch.object(fixture, "_freeze", side_effect=frozen_before_observation):
            self.fx._inputs(split=split, choices=choices)
        exposure = self.fx._call(importlib.import_module("siacognitiveexposure"))
        policy = policy_fixture(self.fx.kw["replay_inputs"]["expected_protocol_sha256"])
        self.kw = {
            "exposure": exposure, "expected_exposure_sha256": exposure["artifact_sha256"],
            "exposure_inputs": copy.deepcopy(self.fx.kw), "ordered_policy": policy,
            "expected_ordered_policy_sha256": sha(canonical(policy)),
        }

    def _call(self, module, **overrides):
        with self.fx.fixture._pure():
            return module.prepare_ordered_measurement(**{**self.kw, **overrides})

    def _arm(self, result, name):
        self.assertEqual([arm["name"] for arm in result["arms"]], ARMS)
        return next(arm for arm in result["arms"] if arm["name"] == name)

    def _answer(self, klass):
        return self.fx.fixture._answers(klass)[0]

    def _cutoff(self, result, arm, klass, k):
        return self.fx.fixture._cutoff(self._arm(result, arm), self._answer(klass)["id"], k)

    def _expression(self, result, arm, klass, metric, k):
        request = self.fx.fixture._request(self._arm(result, arm), "query", self._answer(klass)["id"], metric, k)
        return request["arguments"]["expression"]

    def _policy_override(self, policy):
        return {"ordered_policy": policy, "expected_ordered_policy_sha256": sha(canonical(policy))}

    def test_public_api_requires_closed_keyword_only_external_inputs(self):
        module = self._module()
        parameters = inspect.signature(module.prepare_ordered_measurement).parameters
        self.assertEqual(set(parameters), {"exposure", "expected_exposure_sha256", "exposure_inputs",
                                          "ordered_policy", "expected_ordered_policy_sha256"})
        for parameter in parameters.values():
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)

    def test_detached_complete_artifact_replays_exposure_and_binds_every_source_pin(self):
        module = self._module()
        self._inputs()
        before = copy.deepcopy(self.kw)
        exposure_module = importlib.import_module("siacognitiveexposure")
        with mock.patch.object(exposure_module, "rerank_event_exposure",
                               wraps=exposure_module.rerank_event_exposure) as replay:
            result = self._call(module)
        self.assertEqual(replay.call_args_list, [mock.call(**self.kw["exposure_inputs"])])
        self.assertEqual(result, self._call(module))
        self.assertEqual(self.kw, before)
        self.assertEqual(result["schema"], "sia-cognitive-ordered-measurement-plan-v1")
        self.assertEqual(result["status"], "prepared-for-jackal")
        self.assertEqual(result["arithmetic_status"], "not-evaluated")
        self.assertEqual(result["plan_sha256"], body_digest(result, "plan_sha256"))
        self.assertEqual(result["exposure"], self.kw["exposure"])
        self.assertIsNot(result["exposure"], self.kw["exposure"])
        raw = self.kw["exposure_inputs"]["measurement_plan"]
        for field in ("capture_sha256", "policy_sha256", "selection_sha256", "pages_sha256",
                      "metric_policy_sha256", "baseline_contract_sha256", "protocol_sha256",
                      "baseline_sha256", "query_roster_sha256", "split", "parameter_freeze_sha256"):
            self.assertEqual(result[field], raw[field])
        for field in ("measurement_plan_sha256", "rerank_policy_sha256", "activation_grid_sha256",
                      "activation_policy_sha256"):
            self.assertEqual(result[field], self.kw["exposure"][field])
        self.assertEqual(result["exposure_sha256"], self.kw["expected_exposure_sha256"])
        self.assertEqual(result["ordered_policy_sha256"], self.kw["expected_ordered_policy_sha256"])
        self.assertEqual(result["ordered_policy"], self.kw["ordered_policy"])
        result["exposure"]["measurement_plan"]["baseline"]["queries"].clear()
        result["arms"].clear()
        self.assertEqual(self.kw, before)

    def test_raw_original_summaries_are_exactly_the_original_measurement(self):
        module = self._module()
        self._inputs()
        result = self._call(module)
        raw = self.kw["exposure_inputs"]["measurement_plan"]
        original = self._arm(result, "raw-original")
        for field in ("queries", "classes", "jackal_requests"):
            self.assertEqual(canonical(original[field]), canonical(raw[field]))
        for arm in result["arms"]:
            self.assertEqual(set(arm), {"name", "query_orders", "queries", "classes", "jackal_requests"})
            expected = [{"id": query["id"], "order": next(row["order"] for row in query["arms"]
                                                         if row["name"] == arm["name"])}
                        for query in self.kw["exposure"]["queries"]]
            self.assertEqual(arm["query_orders"], expected)

    def test_recency_contrast_is_not_target_credit_after_cue_or_exposure_permutation(self):
        module = self._module()
        self._inputs()
        result = self._call(module)
        expected = {"raw-original": ("0/1", "1/3"), "cue-only": ("0/1", "1/2"),
                    "cue-event-exposure": ("1/1", "1/1")}
        for name, (recall, reciprocal) in expected.items():
            self.assertEqual(self._expression(result, name, "recency-heavy", "recall_at_k", 1), recall)
            self.assertEqual(self._expression(result, name, "recency-heavy", "reciprocal_rank_at_k", 5), reciprocal)
            cutoff = self._cutoff(result, name, "recency-heavy", 5)
            self.assertEqual(cutoff["target_count"], 1)
            self.assertEqual([row["seq"] for row in cutoff["covered_occurrences"]], ["2"])
        self.assertEqual(self._cutoff(result, "cue-only", "recency-heavy", 1)["covered_occurrences"], [])

    def test_repetition_union_and_first_occurrence_targets_do_not_follow_the_reranker(self):
        module = self._module()
        self._inputs()
        result = self._call(module)
        for name in ARMS:
            self.assertEqual(self._expression(result, name, "repetition-heavy", "recall_at_k", 5), "2/2")
            repetitions = self._cutoff(result, name, "repetition-heavy", 5)
            self.assertEqual({row["seq"] for row in repetitions["covered_occurrences"]}, {"1", "2"})
            self.assertEqual(repetitions["target_count"], 2)
            novelty = self._cutoff(result, name, "novelty", 5)
            self.assertEqual([row["seq"] for row in novelty["covered_occurrences"]], ["1"])
        self.assertEqual(self._expression(result, "cue-only", "novelty", "recall_at_k", 1), "1/1")
        self.assertEqual(self._expression(result, "cue-event-exposure", "novelty", "recall_at_k", 1), "0/1")

    def test_empty_candidate_queries_keep_all_arms_and_complete_denominators(self):
        module = self._module()
        self._inputs(choices={})
        result = self._call(module)
        raw = self.kw["exposure_inputs"]["measurement_plan"]
        for arm in result["arms"]:
            self.assertEqual([row["id"] for row in arm["queries"]], [row["id"] for row in raw["queries"]])
            self.assertTrue(all(row["order"] == [] for row in arm["query_orders"]))
            self.assertTrue(all(row["row_coverage"] == [] for row in arm["queries"]))
            self.assertEqual(arm["classes"], raw["classes"])
            self.assertEqual(self._expression(result, arm["name"], "recency-heavy", "recall_at_k", 1), "0/1")
            self.assertEqual(self._expression(result, arm["name"], "repetition-heavy", "recall_at_k", 1), "0/2")

    def test_rehashed_exposure_changes_cannot_replace_complete_independent_replay(self):
        module = self._module()
        self._inputs()
        self._call(module)
        for change in ("order", "missing-reference", "duplicate-reference", "missing-arm", "extra-arm",
                       "late-query", "raw-chunk", "origin", "trace", "raw-plan-target", "raw-plan-request"):
            altered = copy.deepcopy(self.kw["exposure"])
            query = altered["queries"][-1]
            arm = query["arms"][-1]
            if change == "order":
                arm["order"].reverse()
            elif change == "missing-reference":
                arm["order"].pop()
            elif change == "duplicate-reference":
                arm["order"][-1] = arm["order"][0]
            elif change == "missing-arm":
                query["arms"].pop()
            elif change == "extra-arm":
                query["arms"].append({"name": "target-first", "order": list(arm["order"])})
            elif change == "late-query":
                altered["queries"].pop()
            elif change == "raw-chunk":
                query["candidates"][0]["raw_row"]["chunk_text"] = "unwitnessed content"
            elif change == "origin":
                candidate = query["candidates"][0]
                candidate["origin"] = "model" if candidate["origin"] != "model" else "evidence"
            elif change == "trace":
                query["candidates"][-1]["trace"]["complete"] = False
            elif change == "raw-plan-target":
                altered["measurement_plan"]["queries"][-1]["targets"] = []
            else:
                altered["measurement_plan"]["jackal_requests"][-1]["arguments"]["expression"] = "unreviewed-expression"
            altered["artifact_sha256"] = body_digest(altered, "artifact_sha256")
            with self.subTest(change=change), self.assertRaises(module.OrderedMeasurementRefusal):
                self._call(module, exposure=altered, expected_exposure_sha256=altered["artifact_sha256"])

    def test_raw_observation_reorder_still_refuses_even_with_rebound_rows_and_outer_hashes(self):
        module = self._module()
        self._inputs()
        self._call(module)
        measurement = importlib.import_module("siacognitivemeasure")
        replay = copy.deepcopy(self.kw["exposure_inputs"]["replay_inputs"])
        baseline = replay["baseline"]
        query = baseline["observation"]["query"]
        raw = query["payload"]["results"][0]
        measurement_tests.raw_tests._bind_rows(raw, list(reversed(raw["rows"])))
        label = next(row for row in baseline["retrieval_rows"] if row["id"] == raw["id"])
        label["rows"].reverse()
        query["stdout_sha256"] = sha(canonical(query["payload"]))
        baseline["artifact_sha256"] = body_digest(baseline, "artifact_sha256")
        replay["expected_baseline_sha256"] = baseline["artifact_sha256"]
        with self.fx.fixture._pure(), self.assertRaises(measurement.MeasurementRefusal):
            measurement.prepare_measurement(**replay)

    def test_external_expectations_never_come_from_the_exposure_under_review(self):
        module = self._module()
        self._inputs()
        for field in ("expected_exposure_sha256", "expected_ordered_policy_sha256"):
            for wrong in (None, True, "0" * 64):
                with self.subTest(field=field, wrong=wrong), self.assertRaises(module.OrderedMeasurementRefusal):
                    self._call(module, **{field: wrong})
        for field in ("expected_measurement_plan_sha256", "expected_rerank_policy_sha256", "expected_activation_policy_sha256"):
            inputs = copy.deepcopy(self.kw["exposure_inputs"])
            inputs[field] = "0" * 64
            with self.subTest(field=field), self.assertRaises(module.OrderedMeasurementRefusal):
                self._call(module, exposure_inputs=inputs)
        for field in ("expected_capture_sha256", "expected_policy_sha256", "expected_selection_sha256",
                      "expected_baseline_contract_sha256", "expected_metric_policy_sha256",
                      "expected_protocol_sha256", "expected_baseline_sha256"):
            inputs = copy.deepcopy(self.kw["exposure_inputs"])
            inputs["replay_inputs"][field] = "0" * 64
            with self.subTest(field=field), self.assertRaises(module.OrderedMeasurementRefusal):
                self._call(module, exposure_inputs=inputs)
        for field in self.kw["exposure_inputs"]:
            inputs = copy.deepcopy(self.kw["exposure_inputs"])
            del inputs[field]
            with self.subTest(missing=field), self.assertRaises(module.OrderedMeasurementRefusal):
                self._call(module, exposure_inputs=inputs)
        with self.assertRaises(module.OrderedMeasurementRefusal):
            self._call(module, exposure_inputs={**self.kw["exposure_inputs"], "trusted_order": []})

    def test_ordered_policy_is_closed_and_cannot_change_targets_arms_or_protocol(self):
        module = self._module()
        self._inputs()
        self._call(module)
        for field, wrong in (("schema", "sia-cognitive-retrieval-policy-v1"),
                             ("exposure_schema", "unreplayed-overlay"), ("metric_protocol_sha256", "0" * 64),
                             ("arms", ["cue-event-exposure"]), ("ordering", "target-first"),
                             ("targets", "eligibility-is-relevance"), ("queries", "drop-empty-queries"),
                             ("summaries", "local-float-metrics"), ("latencies", "attribute-raw-time-to-arm"),
                             ("choose_best", True)):
            policy = copy.deepcopy(self.kw["ordered_policy"])
            policy[field] = wrong
            with self.subTest(field=field), self.assertRaises(module.OrderedMeasurementRefusal):
                self._call(module, **self._policy_override(policy))
        policy = copy.deepcopy(self.kw["ordered_policy"])
        policy["arms"].reverse()
        with self.assertRaises(module.OrderedMeasurementRefusal):
            self._call(module, **self._policy_override(policy))

    def test_invalid_structure_refuses_before_copy_serialization_or_exposure_replay(self):
        module = self._module()
        self._inputs()
        cycle = {}
        cycle["cycle"] = cycle
        for field, invalid in (("exposure", cycle), ("exposure_inputs", {"bad": float("inf")}),
                               ("ordered_policy", {"bad": float("nan")})):
            with self.subTest(field=field), \
                    mock.patch("copy.deepcopy", side_effect=AssertionError("copied unadmitted input")), \
                    mock.patch("json.dumps", side_effect=AssertionError("serialized unadmitted input")), \
                    mock.patch("siacognitiveexposure.rerank_event_exposure", side_effect=AssertionError("replayed unadmitted input")), \
                    self.assertRaises(module.OrderedMeasurementRefusal):
                self._call(module, **{field: invalid})

    def test_late_query_mutation_refuses_before_any_ordered_summary(self):
        module = self._module()
        self._inputs()
        changed = copy.deepcopy(self.kw["exposure"])
        changed["queries"][-1]["arms"][-1]["order"].pop()
        changed["artifact_sha256"] = body_digest(changed, "artifact_sha256")
        # The real independently replayed control was built in _inputs. This
        # double isolates ordered admission from the raw scorer used by replay.
        with mock.patch("siacognitiveexposure.rerank_event_exposure", return_value=self.kw["exposure"]), \
                mock.patch("siacognitivemeasure._summarize_coverage", create=True,
                           side_effect=AssertionError("summarized before late query admission")), \
                self.assertRaises(module.OrderedMeasurementRefusal):
            self._call(module, exposure=changed, expected_exposure_sha256=changed["artifact_sha256"])

    def test_explicit_resource_overflow_refuses_whole_run_before_ordered_summary(self):
        module = self._module()
        self._inputs()
        for field in ("max_input_bytes", "max_output_bytes", "max_queries"):
            for wrong in (None, True, 0, 1.0, 1):
                policy = copy.deepcopy(self.kw["ordered_policy"])
                policy["resources"][field] = wrong
                with self.subTest(field=field, wrong=wrong), \
                        mock.patch("siacognitiveexposure.rerank_event_exposure", return_value=self.kw["exposure"]), \
                        mock.patch("siacognitivemeasure._summarize_coverage", create=True,
                                   side_effect=AssertionError("summarized incomplete resource-bounded run")), \
                        self.assertRaises(module.OrderedMeasurementRefusal):
                    self._call(module, **self._policy_override(policy))
        policy = copy.deepcopy(self.kw["ordered_policy"])
        policy["resources"]["prefix_only"] = True
        with self.assertRaises(module.OrderedMeasurementRefusal):
            self._call(module, **self._policy_override(policy))

    def test_heldout_admits_only_the_preexisting_ordered_policy_and_all_upstream_freeze_pins(self):
        module = self._module()
        self._inputs(split="heldout")
        result = self._call(module)
        raw = self.kw["exposure_inputs"]["measurement_plan"]
        freeze = raw["baseline"]["parameter_freeze"]
        self.assertEqual(result["split"], "heldout")
        self.assertEqual(result["parameter_freeze_sha256"], raw["parameter_freeze_sha256"])
        self.assertEqual(freeze["parameters"]["ordered_measurement_policy_sha256"],
                         self.kw["expected_ordered_policy_sha256"])
        for field in ("measurement_protocol_sha256", "event_exposure_policy_sha256",
                      "activation_grid_sha256", "selected_activation_policy_sha256"):
            self.assertIn(field, freeze["parameters"])
        altered = copy.deepcopy(self.kw["exposure_inputs"])
        altered["replay_inputs"]["expected_parameter_freeze_sha256"] = "0" * 64
        with self.assertRaises(module.OrderedMeasurementRefusal):
            self._call(module, exposure_inputs=altered)

    def test_heldout_missing_ordered_policy_pin_refuses_after_valid_exposure_replay(self):
        module = self._module()
        self._inputs(split="heldout", freeze_ordered="missing")
        self.assertEqual(self.kw["exposure"]["split"], "heldout")
        with self.assertRaises(module.OrderedMeasurementRefusal):
            self._call(module)

    def test_heldout_foreign_ordered_policy_pin_refuses_after_valid_exposure_replay(self):
        module = self._module()
        self._inputs(split="heldout", freeze_ordered="foreign")
        self.assertEqual(self.kw["exposure"]["split"], "heldout")
        with self.assertRaises(module.OrderedMeasurementRefusal):
            self._call(module)

    def test_latency_origins_nonclaims_and_unevaluated_request_scope_remain_controlling(self):
        module = self._module()
        source = self.fx.fixture._source()
        original = source.read_bytes().replace(b"---\n", b"---\norigin: model\n", 1)
        original += "\r\nOriginal Ω尾 bytes.\r\n".encode("utf-8")
        source.write_bytes(original)
        self._inputs()
        result = self._call(module)
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertEqual(result["source_non_claims"], {
            "exposure": self.kw["exposure"]["non_claims"],
            "exposure_sources": self.kw["exposure"]["source_non_claims"],
            "measurement": self.kw["exposure_inputs"]["measurement_plan"]["non_claims"],
            "history": self.kw["exposure_inputs"]["measurement_plan"]["source_non_claims"],
        })
        before = self.kw["exposure_inputs"]["measurement_plan"]["baseline"]
        retained = result["exposure"]["measurement_plan"]["baseline"]
        for field in ("observation", "preparation", "retrieval_rows", "pages", "source_non_claims", "non_claims"):
            self.assertEqual(canonical(retained[field]), canonical(before[field]))
        page = next(row for row in retained["pages"] if row["slug"] == "events/aegis/2026-01-01")
        self.assertEqual(page["origin"], "model")
        self.assertEqual(page["text"].encode("utf-8"), original)
        for arm in result["arms"]:
            novelty = next(row for row in arm["queries"] if row["id"] == self._answer("novelty")["id"])
            self.assertEqual(novelty["targets"][0]["witness"]["origin"], "model")
            witness = next(row for row in novelty["row_coverage"] if row["slug"] == page["slug"])
            self.assertEqual(witness["origin"], "model")
        for forbidden in ("best_policy", "win", "p_value", "statistical_power", "speedup", "latency_ms", "rerank_latency_ms"):
            self.assertNotIn(forbidden, result)
            for arm in result["arms"]:
                self.assertNotIn(forbidden, arm)
        self.assertNotIn("jackal_requests", result)  # Requests remain arm-namespaced.
        for arm in result["arms"]:
            for request in arm["jackal_requests"]:
                self.assertEqual(request["tool"], "jackal_exact")
                self.assertEqual(set(request["arguments"]), {"expression"})
                self.assertRegex(request["arguments"]["expression"], r"^[0-9+()/]+$")
                self.assertIn(request["scope"]["kind"], ("query", "class"))
                self.assertNotIn("result", request)
                self.assertNotIn("status", request)


if __name__ == "__main__":
    unittest.main()
