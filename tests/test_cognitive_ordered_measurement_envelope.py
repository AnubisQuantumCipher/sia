"""Ordered v2 expands only a closed argument envelope, never its documents.

Root schedules execution. All observations here are existing synthetic signed
fixtures and stopped-process doubles, not real queries, private artifacts,
models, measurements, or tuning results. Runtime fixture wire lengths are
observed by the fixture rather than replaced by guessed large corpus sizes.

JACKAL boundary routes before writing: status=exact, formal=false;
parsed=64*1024*1024 exact=67108864;
parsed=67108864+1 exact=67108865;
parsed=16777216+1 exact=16777217.
Nonclaims: NOT formal-bounded: this lane carries no Lean-checked certificate;
The epistemic class above is the STRONGEST claim this result supports;
exact rational arithmetic (not yet checker-covered).
These arithmetic fixtures do not assure implementation or future observations.
"""

import contextlib
import copy
import importlib
import unittest
from unittest import mock

from tests import test_cognitive_ordered_measurement as original
from tests import test_cognitive_event_exposure_envelope as exposure_envelope


_LEGACY_POLICY = original.policy_fixture


def policy_fixture(protocol_sha256):
    policy = _LEGACY_POLICY(protocol_sha256)
    policy["schema"] = "sia-cognitive-ordered-measurement-policy-v2"
    policy["resources"]["max_input_bytes"] = 67108864
    policy["resources"]["max_document_bytes"] = 16777216
    return policy


def expected_layout():
    # Literal API contracts, not keys learned from an artifact under review.
    replay = {
        "capture": None, "expected_capture_sha256": None,
        "selection_policy": None, "expected_policy_sha256": None,
        "selection": None, "expected_selection_sha256": None,
        "baseline_contract": None, "expected_baseline_contract_sha256": None,
        "metric_policy": None, "expected_metric_policy_sha256": None,
        "protocol": None, "expected_protocol_sha256": None,
        "baseline": None, "expected_baseline_sha256": None,
        "expected_parameter_freeze_sha256": None,
    }
    return {
        "exposure": None, "expected_exposure_sha256": None,
        "ordered_policy": None, "expected_ordered_policy_sha256": None,
        "exposure_inputs": {
            "measurement_plan": None, "expected_measurement_plan_sha256": None,
            "replay_inputs": replay, "rerank_policy": None,
            "expected_rerank_policy_sha256": None, "activation_policy": None,
            "expected_activation_policy_sha256": None,
        },
    }


class CognitiveOrderedMeasurementEnvelope(unittest.TestCase):
    def setUp(self):
        self.fx = original.CognitiveOrderedMeasurement(methodName="runTest")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.module = importlib.import_module("siacognitiveorderedmeasure")

    def _inputs(self, *, exposure_v2=False, **kwargs):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(original, "policy_fixture", side_effect=policy_fixture))
            if exposure_v2:
                stack.enter_context(mock.patch.object(original.exposure_tests, "policy_fixture",
                                                      side_effect=exposure_envelope.policy_fixture))
            self.fx._inputs(**kwargs)

    def _override(self, policy):
        return self.fx._policy_override(policy)

    def test_v2_admits_literal_nested_envelopes_and_whole_exposure_measurement_source_documents(self):
        self._inputs()
        before = copy.deepcopy(self.fx.kw)
        envelope = importlib.import_module("siacognitiveenvelope")
        with mock.patch.object(envelope, "admit_compound", wraps=envelope.admit_compound) as admit:
            result = self.fx._call(self.module)
        calls = [call for call in admit.call_args_list if "exposure_inputs" in call.kwargs["envelope"]]
        self.assertTrue(calls, "ordered v2 must use complete compound-envelope admission")
        for call in calls:
            arguments = call.kwargs
            self.assertEqual(arguments["envelope"], before)
            self.assertEqual(arguments["layout"], expected_layout())
            self.assertEqual(arguments["max_input_bytes"], before["ordered_policy"]["resources"]["max_input_bytes"])
            self.assertEqual(arguments["max_document_bytes"], before["ordered_policy"]["resources"]["max_document_bytes"])
            self.assertIsNone(arguments["layout"]["exposure"])
            self.assertIsNone(arguments["layout"]["exposure_inputs"]["measurement_plan"])
            self.assertTrue(all(node is None for node in arguments["layout"]["exposure_inputs"]["replay_inputs"].values()))
        self.assertEqual(result["schema"], "sia-cognitive-ordered-measurement-plan-v1")
        self.assertEqual(result["status"], "prepared-for-jackal")
        self.assertEqual(result["arithmetic_status"], "not-evaluated")
        self.assertEqual(result["ordered_policy"]["schema"], "sia-cognitive-ordered-measurement-policy-v2")
        self.assertEqual(result["ordered_policy_sha256"], before["expected_ordered_policy_sha256"])
        self.assertEqual(result["exposure"], before["exposure"])
        self.assertEqual(result["non_claims"], original.NON_CLAIMS)
        self.assertEqual(result["plan_sha256"], original.body_digest(result, "plan_sha256"))
        self.assertEqual(self.fx.kw, before)

    def test_policy_version_does_not_change_any_arm_target_request_or_raw_observation(self):
        self._inputs()
        current = self.fx._call(self.module)
        policy = _LEGACY_POLICY(self.fx.kw["exposure_inputs"]["replay_inputs"]["expected_protocol_sha256"])
        before = self.fx._call(self.module, **self._override(policy))
        after = self.fx._call(self.module, **self._override(policy))
        self.assertEqual(original.canonical(before), original.canonical(after))
        for field in ("arms", "exposure", "source_non_claims", "non_claims", "protocol_sha256",
                      "measurement_plan_sha256", "baseline_sha256", "query_roster_sha256",
                      "activation_grid_sha256", "activation_policy_sha256"):
            self.assertEqual(current[field], before[field], field)
        self.assertNotEqual(current["ordered_policy_sha256"], before["ordered_policy_sha256"])
        for key, value in policy.items():
            if key not in ("schema", "resources"):
                self.assertEqual(current["ordered_policy"][key], value)
        for key in ("max_output_bytes", "max_queries"):
            self.assertEqual(current["ordered_policy"]["resources"][key], policy["resources"][key])

    def test_nested_exposure_v2_still_has_whole_v1_artifact_and_identical_raw_original_summary(self):
        self._inputs(exposure_v2=True)
        result = self.fx._call(self.module)
        exposure = result["exposure"]
        self.assertEqual(exposure["schema"], "sia-cognitive-event-exposure-v1")
        self.assertEqual(exposure["rerank_policy"]["schema"], "sia-cognitive-event-exposure-policy-v2")
        self.assertEqual(exposure, self.fx.kw["exposure"])
        raw = exposure["measurement_plan"]
        arm = self.fx._arm(result, "raw-original")
        for field in ("queries", "classes", "jackal_requests"):
            self.assertEqual(arm[field], raw[field])
        self.assertEqual([row["name"] for row in result["arms"]], original.ARMS)

    def test_compound_packet_can_exceed_legacy_cap_without_splitting_any_document(self):
        self._inputs()
        kwargs = self.fx.kw
        documents = [value for key, value in kwargs.items() if key != "exposure_inputs"]
        documents.extend(value for key, value in kwargs["exposure_inputs"].items() if key != "replay_inputs")
        documents.extend(kwargs["exposure_inputs"]["replay_inputs"].values())
        document_limit = max(len(original.canonical(value)) for value in documents)
        self.assertGreater(len(original.canonical(kwargs)), document_limit)
        policy = copy.deepcopy(kwargs["ordered_policy"])
        policy["resources"]["max_document_bytes"] = document_limit
        # A small synthetic seam detects an accidental legacy aggregate gate;
        # no original hard document bound or shared helper limit is weakened.
        with mock.patch.object(self.module, "MAX_INPUT_BYTES", document_limit):
            result = self.fx._call(self.module, **self._override(policy))
        self.assertEqual(result["exposure"], kwargs["exposure"])
        self.assertEqual(result["ordered_policy"]["resources"]["max_document_bytes"], document_limit)

    def test_v1_cannot_acquire_v2_fields_caps_or_compound_admission(self):
        self.fx._inputs()
        envelope = importlib.import_module("siacognitiveenvelope")
        before = copy.deepcopy(self.fx.kw)
        with mock.patch.object(envelope, "admit_compound", side_effect=AssertionError("legacy input acquired compound admission")):
            result = self.fx._call(self.module)
        self.assertEqual(result["ordered_policy"]["schema"], "sia-cognitive-ordered-measurement-policy-v1")
        self.assertEqual(self.fx.kw, before)
        for field, value in (("max_document_bytes", 16777216), ("max_input_bytes", 67108864)):
            policy = copy.deepcopy(self.fx.kw["ordered_policy"])
            policy["resources"][field] = value
            with self.subTest(field=field), self.assertRaises(self.module.OrderedMeasurementRefusal):
                self.fx._call(self.module, **self._override(policy))

    def test_v2_resource_bounds_refuse_before_copy_exposure_replay_or_ordered_summary(self):
        self._inputs()
        for field in ("max_input_bytes", "max_document_bytes", "max_output_bytes"):
            for invalid in (None, True, 0, 1.0, 1, 67108865):
                policy = copy.deepcopy(self.fx.kw["ordered_policy"])
                policy["resources"][field] = invalid
                overrides = self._override(policy)
                with self.subTest(field=field, invalid=invalid), \
                        mock.patch("copy.deepcopy", side_effect=AssertionError("copied before bounded admission")), \
                        mock.patch("siacognitiveexposure.rerank_event_exposure", side_effect=AssertionError("replayed before bounds")), \
                        mock.patch("siacognitivemeasure._summarize_coverage", side_effect=AssertionError("summarized before bounds")), \
                        self.assertRaises(self.module.OrderedMeasurementRefusal):
                    self.fx._call(self.module, **overrides)
        for field, invalid in (("max_document_bytes", 16777217), ("max_output_bytes", 16777217),
                               ("ignore_documents", True)):
            policy = copy.deepcopy(self.fx.kw["ordered_policy"])
            policy["resources"][field] = invalid
            with self.subTest(field=field), self.assertRaises(self.module.OrderedMeasurementRefusal):
                self.fx._call(self.module, **self._override(policy))
        policy = copy.deepcopy(self.fx.kw["ordered_policy"])
        del policy["resources"]["max_document_bytes"]
        with self.assertRaises(self.module.OrderedMeasurementRefusal):
            self.fx._call(self.module, **self._override(policy))

    def test_late_invalid_whole_source_refuses_before_copy_hash_or_serialization(self):
        self._inputs()
        cycle = {}
        cycle["self"] = cycle
        for field, value in (("capture", cycle), ("protocol", {"bad": float("inf")}),
                             ("baseline", {"bad": float("nan")})):
            inputs = copy.deepcopy(self.fx.kw["exposure_inputs"])
            inputs["replay_inputs"][field] = value
            with self.subTest(field=field), \
                    mock.patch("copy.deepcopy", side_effect=AssertionError("copied malformed compound input")), \
                    mock.patch("json.dumps", side_effect=AssertionError("serialized malformed compound input")), \
                    mock.patch("siacognitiveexposure.rerank_event_exposure", side_effect=AssertionError("replayed malformed input")), \
                    self.assertRaises(self.module.OrderedMeasurementRefusal):
                self.fx._call(self.module, exposure_inputs=inputs)

    def test_closed_topology_cannot_ignore_extra_missing_or_retyped_argument_branches(self):
        self._inputs()
        for change in ("extra-exposure-input", "missing-exposure-input", "extra-replay-input",
                       "missing-replay-input", "retyped-replay-input", "foreign-capture"):
            inputs = copy.deepcopy(self.fx.kw["exposure_inputs"])
            if change == "extra-exposure-input":
                inputs["ignored_artifact"] = {}
            elif change == "missing-exposure-input":
                del inputs["measurement_plan"]
            elif change == "extra-replay-input":
                inputs["replay_inputs"]["ignored_artifact"] = {}
            elif change == "missing-replay-input":
                del inputs["replay_inputs"]["capture"]
            elif change == "retyped-replay-input":
                inputs["replay_inputs"] = []
            else:
                inputs["replay_inputs"]["capture"] = []
            with self.subTest(change=change), self.assertRaises(self.module.OrderedMeasurementRefusal):
                self.fx._call(self.module, exposure_inputs=inputs)

    def test_larger_envelope_still_requires_complete_exposure_and_source_replay(self):
        self._inputs()
        self.fx._call(self.module)
        changed = copy.deepcopy(self.fx.kw["exposure"])
        changed["queries"][-1]["arms"][-1]["order"].reverse()
        changed["artifact_sha256"] = original.body_digest(changed, "artifact_sha256")
        with self.assertRaises(self.module.OrderedMeasurementRefusal):
            self.fx._call(self.module, exposure=changed, expected_exposure_sha256=changed["artifact_sha256"])
        inputs = copy.deepcopy(self.fx.kw["exposure_inputs"])
        inputs["replay_inputs"]["expected_capture_sha256"] = "0" * 64
        with self.assertRaises(self.module.OrderedMeasurementRefusal):
            self.fx._call(self.module, exposure_inputs=inputs)

    def test_heldout_requires_preexisting_v2_ordered_pin_not_legacy_or_refitted_resources(self):
        self._inputs(split="heldout")
        result = self.fx._call(self.module)
        freeze = result["exposure"]["measurement_plan"]["baseline"]["parameter_freeze"]
        self.assertEqual(result["split"], "heldout")
        self.assertEqual(freeze["parameters"]["ordered_measurement_policy_sha256"],
                         self.fx.kw["expected_ordered_policy_sha256"])
        self.assertEqual(result["parameter_freeze_sha256"], freeze["freeze_sha256"])
        old = _LEGACY_POLICY(result["protocol_sha256"])
        with self.assertRaises(self.module.OrderedMeasurementRefusal):
            self.fx._call(self.module, **self._override(old))
        changed = copy.deepcopy(self.fx.kw["ordered_policy"])
        changed["resources"]["max_input_bytes"] = 16777216
        with self.assertRaises(self.module.OrderedMeasurementRefusal):
            self.fx._call(self.module, **self._override(changed))


if __name__ == "__main__":
    unittest.main()
