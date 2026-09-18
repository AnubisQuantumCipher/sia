"""Synthetic v2 baseline compatibility through complete public replay paths.

Root alone schedules execution. Existing signed-source and stopped-controller
fixtures provide both explicit embedding modes; no real model, index, private
artifact, metric evaluation, or outcome-based policy choice is involved.
Each heldout fixture freezes its own complete successor policies BEFORE its
synthetic baseline runs. No retained paired-run freeze is rewritten here.

Numeric inputs and endpoint expressions are reused from the existing fixtures;
this suite introduces no calculated score, duration, or arithmetic oracle.
"""

import copy
import importlib
import unittest
from unittest import mock

from tests import test_cognitive_baseline_prefix as prefix_tests
from tests import test_cognitive_event_exposure as exposure_tests
from tests import test_cognitive_exposure_timing as timing_tests
from tests import test_cognitive_fidelity as fidelity_tests
from tests import test_cognitive_inference as inference_tests


canonical = exposure_tests.canonical
sha = exposure_tests.sha
body_digest = exposure_tests.body_digest
MODES = ("bare-v1", "nomic-prefix-v1")


def use_v2_baseline(fixture, mode):
    """Compose existing fixture methods, not an alternative production replay."""
    source = prefix_tests.PrefixBaselineFixture
    for name in ("_contract", "_policy_fields", "_request", "_rebind", "_prepare",
                 "_observe", "_controls", "_run", "_pure"):
        setattr(fixture, name, getattr(source, name).__get__(fixture))

    def baseline_inputs(module, split):
        source._inputs(fixture, module, split=split, mode=mode)

    fixture._baseline_inputs = baseline_inputs


class CognitivePrefixDownstream(unittest.TestCase):
    def _fixture(self, cls):
        result = cls(methodName="runTest")
        result.setUp()
        self.addCleanup(result.doCleanups)
        return result

    def _assert_retained_baseline(self, exposure, fixture, mode):
        baseline = exposure["measurement_plan"]["baseline"]
        self.assertEqual(baseline["schema"], "sia-cognitive-baseline-v2")
        self.assertEqual(baseline["contract"], fixture._contract())
        self.assertEqual(baseline["embedding_input_policy"], prefix_tests.embedding_policy(mode))
        self.assertEqual(baseline["embedding_input_policy_sha256"],
                         fixture.kw["expected_embedding_input_policy_sha256"])
        self.assertEqual(baseline["pages"], fixture.kw["selection"]["pages"])
        self.assertEqual(baseline["queries"], fixture._queries())
        self.assertEqual(baseline["non_claims"], prefix_tests.NON_CLAIMS_V2)
        self.assertEqual(exposure["non_claims"], exposure_tests.NON_CLAIMS)
        originals = {row["id"]: row for row in baseline["observation"]["query"]["payload"]["results"]}
        pages = {page["slug"]: page for page in baseline["pages"]}
        for query in exposure["queries"]:
            self.assertEqual(query["text"], next(row["text"] for row in baseline["queries"]
                                                 if row["id"] == query["id"]))
            self.assertEqual([candidate["raw_row"] for candidate in query["candidates"]],
                             originals[query["id"]]["rows"])
            for candidate in query["candidates"]:
                self.assertEqual(candidate["origin"], pages[candidate["raw_row"]["slug"]]["origin"])
        return baseline

    def test_both_v2_modes_replay_exposure_ordered_and_fidelity(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                fx = self._fixture(fidelity_tests.CognitiveFidelity)
                fixture = fx.fx.fx.fixture
                use_v2_baseline(fixture, mode)
                fx._inputs(split="heldout", compound=True)
                before = copy.deepcopy(fx.kw)
                measurement = importlib.import_module("siacognitivemeasure")
                with mock.patch.object(measurement, "prepare_measurement",
                                       wraps=measurement.prepare_measurement) as replay:
                    result = fx._call()
                self.assertTrue(replay.called)
                self.assertEqual(fx.kw, before)
                ordered = fx.kw["ordered_plan"]
                exposure = ordered["exposure"]
                baseline = self._assert_retained_baseline(exposure, fixture, mode)
                raw = exposure["measurement_plan"]
                raw_arm = next(arm for arm in ordered["arms"] if arm["name"] == "raw-original")
                for field in ("queries", "classes", "jackal_requests"):
                    self.assertEqual(canonical(raw_arm[field]), canonical(raw[field]))
                self.assertEqual(ordered["schema"], "sia-cognitive-ordered-measurement-plan-v1")
                self.assertEqual(ordered["ordered_policy"]["schema"],
                                 "sia-cognitive-ordered-measurement-policy-v2")
                self.assertEqual(ordered["arithmetic_status"], "not-evaluated")
                self.assertEqual(result["status"], "computed-unverified")
                self.assertEqual(result["material_bindings"], fx._bindings())
                self.assertEqual(result["source_non_claims"], fx._source_nonclaims())
                self.assertEqual(result["non_claims"], fidelity_tests.NON_CLAIMS)
                self.assertEqual(result["source_pins"]["parameter_freeze_sha256"],
                                 baseline["parameter_freeze_sha256"])

    def test_both_v2_modes_time_new_replay_and_prepare_endpoint_requests(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                fx = self._fixture(timing_tests.CognitiveExposureTiming)
                use_v2_baseline(fx.fx.fixture, mode)
                fx._inputs(split="heldout")
                module = fx._module()
                original = canonical(fx.exposure)
                with mock.patch("siavectorrun.prepare_bound_v2", side_effect=AssertionError("timing prepared index")), \
                        mock.patch("siavectorrun.observe_bound_v2", side_effect=AssertionError("timing queried engine")), \
                        mock.patch("siacognitivebaseline.run_baseline_v2", side_effect=AssertionError("timing reran baseline")):
                    observation = fx._observe(module)
                plan = fx._prepare(module, observation)
                self._assert_retained_baseline(observation["exposure"], fx.fx.fixture, mode)
                self.assertEqual(canonical(observation["exposure"]), original)
                self.assertEqual(canonical(plan["observation"]), canonical(observation))
                self.assertEqual([(span["query_id"], span["arm"]) for span in observation["query_spans"]],
                                 fx._schedule())
                self.assertEqual([(row["query_id"], row["arm"]) for row in plan["query_samples"]],
                                 fx._schedule())
                for sample, span in zip(plan["query_samples"], observation["query_spans"], strict=True):
                    self.assertEqual(sample["given"]["start_ns"], span["start_ns"])
                    self.assertEqual(sample["given"]["end_ns"], span["end_ns"])
                    self.assertEqual(sample["expression"], "(100-100)")
                self.assertEqual(plan["arithmetic_status"], "not-evaluated")
                self.assertEqual(plan["pipeline_timing"], timing_tests.PIPELINE_UNAVAILABLE)
                self.assertEqual(observation["non_claims"], timing_tests.NON_CLAIMS)
                self.assertEqual(plan["non_claims"], timing_tests.PLAN_NON_CLAIMS)

    def test_v2_inference_protocol_and_comparison_replay_full_sources(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                fx = self._fixture(inference_tests.CognitiveInference)
                use_v2_baseline(fx.fixture, mode)
                fx._inputs()
                before = copy.deepcopy(fx.kw)
                with mock.patch.object(fx.module, "build_inference_protocol",
                                       wraps=fx.module.build_inference_protocol) as source, \
                        mock.patch.object(fx.ordered, "prepare_ordered_measurement",
                                          wraps=fx.ordered.prepare_ordered_measurement) as ordered:
                    result = fx._comparison()
                self.assertEqual(source.call_args_list, [mock.call(**fx.kw["inference_inputs"])])
                self.assertEqual(ordered.call_args_list, [mock.call(**fx.kw["ordered_inputs"])])
                self.assertEqual(fx.kw, before)
                self._assert_retained_baseline(fx.kw["ordered_plan"]["exposure"], fx.fixture, mode)
                self.assertEqual(result["inference_protocol"], fx.kw["inference_protocol"])
                self.assertEqual(result["retrieval_protocol_sha256"], fx.pk["expected_retrieval_protocol_sha256"])
                self.assertEqual(result["split"], "heldout")
                self.assertEqual(result["arithmetic_status"], "not-evaluated")
                self.assertEqual(result["non_claims"], inference_tests.NON_CLAIMS)
                self.assertNotIn("win", result)

    def test_original_policy_protocol_and_freeze_pins_refuse_as_v2_authority(self):
        module = importlib.import_module("siacognitiveexposure")
        old = self._fixture(exposure_tests.CognitiveEventExposure)
        old._inputs(split="heldout")
        self.assertEqual(old._call(module)["measurement_plan"]["baseline"]["schema"],
                         "sia-cognitive-baseline-v1")
        for mode in MODES:
            with self.subTest(mode=mode):
                fx = self._fixture(exposure_tests.CognitiveEventExposure)
                use_v2_baseline(fx.fixture, mode)
                fx._inputs(split="heldout")
                self._assert_retained_baseline(fx._call(module), fx.fixture, mode)
                with self.assertRaises(module.ExposureRefusal):
                    fx._call(module, rerank_policy=old.kw["rerank_policy"],
                             expected_rerank_policy_sha256=old.kw["expected_rerank_policy_sha256"])
                for field in ("expected_protocol_sha256", "expected_parameter_freeze_sha256"):
                    replay = copy.deepcopy(fx.kw["replay_inputs"])
                    replay[field] = old.kw["replay_inputs"][field]
                    with self.subTest(pin=field), self.assertRaises(module.ExposureRefusal):
                        fx._call(module, replay_inputs=replay)

    def test_wrong_or_mixed_embedding_witness_refuses_before_timed_workers(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                fx = self._fixture(timing_tests.CognitiveExposureTiming)
                use_v2_baseline(fx.fx.fixture, mode)
                fx._inputs(split="heldout")
                module = fx._module()
                measurement = importlib.import_module("siacognitivemeasure")
                for defect in ("embedding-policy", "query-input-witness"):
                    inputs = copy.deepcopy(fx.kw["exposure_inputs"])
                    replay = inputs["replay_inputs"]
                    baseline = replay["baseline"]
                    if defect == "embedding-policy":
                        other = next(value for value in MODES if value != mode)
                        baseline["embedding_input_policy"] = prefix_tests.embedding_policy(other)
                    else:
                        baseline["observation"]["query"]["payload"]["results"][0]["embedding_input_sha256"] = "0" * 64
                    baseline["artifact_sha256"] = body_digest(baseline, "artifact_sha256")
                    replay["expected_baseline_sha256"] = baseline["artifact_sha256"]
                    with self.subTest(defect=defect), fx.fx.fixture._pure(), \
                            self.assertRaises(measurement.MeasurementRefusal):
                        measurement.prepare_measurement(**replay)
                    with self.subTest(defect=defect), \
                            mock.patch("time.perf_counter_ns", side_effect=AssertionError("timed invalid source")), \
                            mock.patch("siacognitiveexposure._rank_arm", side_effect=AssertionError("ranked invalid source")), \
                            self.assertRaises(module.ExposureTimingRefusal):
                        fx._invoke(module, exposure_inputs=inputs)

    def test_v2_compatibility_preserves_complete_trace_and_resource_refusals(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                fx = self._fixture(fidelity_tests.CognitiveFidelity)
                use_v2_baseline(fx.fx.fx.fixture, mode)
                fx._inputs(compound=True)
                self.assertEqual(fx._call()["status"], "computed-unverified")
                for field in ("max_trace_bytes", "max_document_bytes", "max_output_bytes"):
                    policy = copy.deepcopy(fx.kw["fidelity_policy"])
                    policy["resources"][field] = 1
                    overrides = fx._policy_override(policy)
                    with self.subTest(cap=field), \
                            mock.patch("copy.deepcopy", side_effect=AssertionError("copied over-cap input")), \
                            mock.patch("hashlib.sha256", side_effect=AssertionError("hashed over-cap input")), \
                            mock.patch.object(fx.ordered, "prepare_ordered_measurement",
                                              side_effect=AssertionError("replayed over-cap input")), \
                            self.assertRaises(fx.module.FidelityRefusal):
                        fx._call(**overrides)
                exposure = fx.fx.fx
                policy = copy.deepcopy(exposure.kw["rerank_policy"])
                policy["resources"]["max_trace_bytes"] = 1
                overrides = exposure._policy_override(policy)
                module = importlib.import_module("siacognitiveexposure")
                with mock.patch.object(module, "_rank_arm", side_effect=AssertionError("ranked clipped trace")), \
                        self.assertRaises(module.ExposureRefusal):
                    exposure._call(module, **overrides)
