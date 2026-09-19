"""Versioned multi-document latency admission; v1 budgets remain unchanged."""

import copy
import importlib
import unittest
from unittest import mock

from tests import test_cognitive_latency as original


def policy_fixture():
    return {**original.policy_fixture(), "schema": "sia-cognitive-latency-policy-v2",
            "resources": {"max_input_bytes": 67108864, "max_document_bytes": 16777216,
                          "max_output_bytes": 16777216}}


class CognitiveLatencyEnvelope(unittest.TestCase):
    def setUp(self):
        self.fx = original.CognitiveLatency(methodName="runTest")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.module = importlib.import_module("siacognitivelatency")

    def _inputs(self, **kwargs):
        policy = policy_fixture()
        with mock.patch.object(original, "policy_fixture", return_value=policy):
            self.fx._inputs(**kwargs)

    def _override(self, policy):
        return {"latency_policy": policy,
                "expected_latency_policy_sha256": original.sha(original.canonical(policy))}

    def test_versioned_compound_admission_preserves_full_source_replay_and_given_requests(self):
        self._inputs()
        before = copy.deepcopy(self.fx.kw)
        envelope = importlib.import_module("siacognitiveenvelope")
        with mock.patch.object(envelope, "admit_compound", wraps=envelope.admit_compound) as admit:
            result = self.fx._call(self.module)
        admit.assert_called_once()
        arguments = admit.call_args.kwargs
        self.assertEqual(arguments["envelope"], before)
        self.assertEqual(arguments["max_input_bytes"], before["latency_policy"]["resources"]["max_input_bytes"])
        self.assertEqual(arguments["max_document_bytes"], before["latency_policy"]["resources"]["max_document_bytes"])
        self.assertEqual(set(arguments["layout"]["replay_inputs"]), set(before["replay_inputs"]))
        self.assertTrue(all(item is None for item in arguments["layout"]["replay_inputs"].values()))
        self.assertEqual(result["schema"], "sia-cognitive-latency-plan-v2")
        self.assertEqual(result["status"], "prepared-for-jackal")
        self.assertEqual(result["arithmetic_status"], "not-evaluated")
        self.assertEqual(result["measurement_plan"], before["measurement_plan"])
        self.assertEqual(result["non_claims"], original.NON_CLAIMS)
        legacy = self.fx._call(self.module, **self._override(original.policy_fixture()))
        for field in ("jackal_requests", "query_samples", "operation_samples", "classes", "unavailable"):
            self.assertEqual(result[field], legacy[field])
        self.assertEqual(self.fx.kw, before)

    def test_v1_does_not_acquire_a_larger_or_implicit_resource_envelope(self):
        self.fx._inputs()
        policy = self.fx.kw["latency_policy"]
        self.assertEqual(self.fx._call(self.module)["schema"], "sia-cognitive-latency-plan-v1")
        with self.assertRaises(self.module.LatencyRefusal):
            self.fx._call(self.module, **self._override({**policy, "resources": policy_fixture()["resources"]}))
        changed = {**policy, "schema": "sia-cognitive-latency-policy-v2"}
        with self.assertRaises(self.module.LatencyRefusal):
            self.fx._call(self.module, **self._override(changed))

    def test_resource_limits_are_complete_strict_and_fail_before_source_replay(self):
        self._inputs()
        for field in self.fx.kw["latency_policy"]["resources"]:
            for invalid in (None, True, 0, 1.0, 1, 67108865):
                policy = copy.deepcopy(self.fx.kw["latency_policy"])
                policy["resources"][field] = invalid
                with self.subTest(field=field, invalid=invalid), \
                        mock.patch.object(self.module.measurement, "prepare_measurement",
                                          side_effect=AssertionError("replayed before complete resource admission")), \
                        self.assertRaises(self.module.LatencyRefusal):
                    self.fx._call(self.module, **self._override(policy))
        policy = copy.deepcopy(self.fx.kw["latency_policy"])
        policy["resources"]["skip_documents"] = True
        with self.assertRaises(self.module.LatencyRefusal):
            self.fx._call(self.module, **self._override(policy))

    def test_late_invalid_source_refuses_before_copy_hash_or_serialization(self):
        self._inputs()
        cycle = {}
        cycle["self"] = cycle
        replay = {**self.fx.kw["replay_inputs"], "baseline": cycle}
        with mock.patch("json.dumps", side_effect=AssertionError("serialized malformed envelope")), \
                mock.patch("copy.deepcopy", side_effect=AssertionError("copied malformed envelope")), \
                self.assertRaises(self.module.LatencyRefusal):
            self.fx._call(self.module, replay_inputs=replay)

    def test_compound_layout_never_omits_foreign_or_missing_replay_fields(self):
        self._inputs()
        for replay in ({**self.fx.kw["replay_inputs"], "extra": {}},
                       {key: item for key, item in self.fx.kw["replay_inputs"].items() if key != "expected_capture_sha256"}):
            with self.assertRaises(self.module.LatencyRefusal):
                self.fx._call(self.module, replay_inputs=replay)

    def test_heldout_requires_preexisting_v2_policy_pin_not_the_legacy_identity(self):
        self._inputs(split="heldout")
        self.assertEqual(self.fx._call(self.module)["split"], "heldout")
        with self.assertRaises(self.module.LatencyRefusal):
            self.fx._call(self.module, **self._override(original.policy_fixture()))
        policy = copy.deepcopy(self.fx.kw["latency_policy"])
        policy["resources"]["max_input_bytes"] = 16777216
        with self.assertRaises(self.module.LatencyRefusal):
            self.fx._call(self.module, **self._override(policy))

    def test_rehashed_measurement_cannot_bypass_the_unchanged_source_gate(self):
        self._inputs()
        plan = copy.deepcopy(self.fx.kw["measurement_plan"])
        plan["jackal_requests"][0]["arguments"]["expression"] = "999"
        plan["plan_sha256"] = original.body_digest(plan, "plan_sha256")
        with self.assertRaises(self.module.LatencyRefusal):
            self.fx._call(self.module, measurement_plan=plan, expected_measurement_plan_sha256=plan["plan_sha256"])


if __name__ == "__main__":
    unittest.main()
