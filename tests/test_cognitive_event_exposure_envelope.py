"""Versioned exposure envelopes preserve whole source artifacts and v1 limits.

Root schedules execution. Fixtures remain synthetic and target blind; no real
query, model, corpus, metric execution, or parameter choice is introduced.

JACKAL boundaries copied from the already retained envelope fixture:
status=exact, formal=false; parsed=64*1024*1024 exact=67108864;
parsed=67108864+1 exact=67108865;
parsed=16777216+1 exact=16777217.
Nonclaims: NOT formal-bounded: this lane carries no Lean-checked certificate;
The epistemic class above is the STRONGEST claim this result supports;
exact rational arithmetic (not yet checker-covered).
These arithmetic fixtures do not assure software or future observations.
"""

import copy
import importlib
import unittest
from unittest import mock

from tests import test_cognitive_event_exposure as original


_LEGACY_POLICY = original.policy_fixture


def policy_fixture(protocol_sha256, *, selected=None):
    value = _LEGACY_POLICY(protocol_sha256, selected=selected)
    value["schema"] = "sia-cognitive-event-exposure-policy-v2"
    value["resources"]["max_input_bytes"] = 67108864
    value["resources"]["max_document_bytes"] = 16777216
    return value


class CognitiveEventExposureEnvelope(unittest.TestCase):
    def setUp(self):
        self.fx = original.CognitiveEventExposure(methodName="runTest")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.module = importlib.import_module("siacognitiveexposure")

    def _inputs(self, **kwargs):
        with mock.patch.object(original, "policy_fixture", side_effect=policy_fixture):
            self.fx._inputs(**kwargs)

    def _override(self, policy):
        return self.fx._policy_override(policy)

    def test_v2_uses_closed_compound_helper_with_every_original_replay_document_whole(self):
        self._inputs()
        before = copy.deepcopy(self.fx.kw)
        envelope = importlib.import_module("siacognitiveenvelope")
        with mock.patch.object(envelope, "admit_compound", wraps=envelope.admit_compound) as admit:
            result = self.fx._call(self.module)
        self.assertTrue(admit.called)
        for call in admit.call_args_list:
            arguments = call.kwargs
            self.assertEqual(arguments["envelope"], before)
            self.assertEqual(arguments["max_input_bytes"], before["rerank_policy"]["resources"]["max_input_bytes"])
            self.assertEqual(arguments["max_document_bytes"], before["rerank_policy"]["resources"]["max_document_bytes"])
            expected_layout = {key: None for key in before}
            expected_layout["replay_inputs"] = {key: None for key in before["replay_inputs"]}
            self.assertEqual(arguments["layout"], expected_layout)
            # None is a complete leaf. Capture/selection/protocol/baseline may
            # not become subtrees that split a large artifact to obtain yield.
            self.assertTrue(all(node is None for node in arguments["layout"]["replay_inputs"].values()))
        self.assertEqual(result["schema"], "sia-cognitive-event-exposure-v1")
        self.assertEqual(result["status"], "computed-unverified")
        self.assertEqual(result["rerank_policy"]["schema"], "sia-cognitive-event-exposure-policy-v2")
        self.assertEqual(result["artifact_sha256"], original.body_digest(result, "artifact_sha256"))
        self.assertEqual(result["measurement_plan"], before["measurement_plan"])
        self.assertEqual(result["non_claims"], original.NON_CLAIMS)
        self.assertEqual(self.fx.kw, before)

    def test_only_policy_identity_changes_not_clock_grid_selected_member_trace_or_arm_semantics(self):
        self._inputs()
        current = self.fx._call(self.module)
        old_policy = _LEGACY_POLICY(self.fx.kw["replay_inputs"]["expected_protocol_sha256"])
        legacy = self.fx._call(self.module, **self._override(old_policy))
        for field in ("queries", "event_population", "measurement_plan", "observed_at", "activation_grid_sha256",
                      "activation_policy", "activation_policy_sha256", "source_non_claims", "non_claims"):
            self.assertEqual(current[field], legacy[field], field)
        self.assertNotEqual(current["rerank_policy_sha256"], legacy["rerank_policy_sha256"])
        self.assertEqual(current["rerank_policy"]["activation_grid"], old_policy["activation_grid"])
        self.assertEqual(current["rerank_policy"]["calibration_objective"], old_policy["calibration_objective"])
        self.assertEqual(current["rerank_policy"]["ablation_roster"], old_policy["ablation_roster"])
        for field in ("max_queries", "max_source_events", "max_grid_policies", "max_trace_bytes", "max_output_bytes"):
            self.assertEqual(current["rerank_policy"]["resources"][field], old_policy["resources"][field])

    def test_compound_packet_can_exceed_legacy_single_bound_without_widening_any_document(self):
        self._inputs()
        # Use actual fixture document lengths, not a large artificial corpus or
        # assumed byte literal. Shrink only the existing v1 aggregate ceiling;
        # the shared helper retains its real hard caps and whole-document gate.
        documents = [value for key, value in self.fx.kw.items() if key != "replay_inputs"]
        documents.extend(self.fx.kw["replay_inputs"].values())
        document_limit = max(len(original.canonical(value)) for value in documents)
        self.assertGreater(len(original.canonical(self.fx.kw["replay_inputs"])), document_limit)
        policy = copy.deepcopy(self.fx.kw["rerank_policy"])
        policy["resources"]["max_document_bytes"] = document_limit
        with mock.patch.object(self.module, "MAX_INPUT_BYTES", document_limit):
            result = self.fx._call(self.module, **self._override(policy))
        self.assertEqual(result["measurement_plan"], self.fx.kw["measurement_plan"])
        self.assertEqual(result["rerank_policy"]["resources"]["max_document_bytes"], document_limit)

    def test_v1_neither_acquires_v2_fields_nor_silently_changes_its_admission_path(self):
        self.fx._inputs()
        before = copy.deepcopy(self.fx.kw)
        envelope = importlib.import_module("siacognitiveenvelope")
        with mock.patch.object(envelope, "admit_compound", side_effect=AssertionError("v1 acquired compound admission")):
            result = self.fx._call(self.module)
        self.assertEqual(result["rerank_policy"]["schema"], "sia-cognitive-event-exposure-policy-v1")
        self.assertEqual(self.fx.kw, before)
        policy = copy.deepcopy(self.fx.kw["rerank_policy"])
        policy["resources"]["max_document_bytes"] = 16777216
        with self.assertRaises(self.module.ExposureRefusal):
            self.fx._call(self.module, **self._override(policy))
        policy = copy.deepcopy(self.fx.kw["rerank_policy"])
        policy["resources"]["max_input_bytes"] = 67108864
        with self.assertRaises(self.module.ExposureRefusal):
            self.fx._call(self.module, **self._override(policy))

    def test_v2_resource_shape_and_whole_document_limits_refuse_before_copy_replay_or_scoring(self):
        self._inputs()
        for field in ("max_input_bytes", "max_document_bytes", "max_output_bytes"):
            for invalid in (None, True, 0, 1.0, 1, 67108865):
                policy = copy.deepcopy(self.fx.kw["rerank_policy"])
                policy["resources"][field] = invalid
                overrides = self._override(policy)
                with self.subTest(field=field, invalid=invalid), \
                        mock.patch.object(self.module.measurement, "prepare_measurement",
                                          side_effect=AssertionError("replayed before resource admission")), \
                        mock.patch("copy.deepcopy", side_effect=AssertionError("copied before resource admission")), \
                        mock.patch.object(self.module, "_rank_query", side_effect=AssertionError("scored before resource admission")), \
                        self.assertRaises(self.module.ExposureRefusal):
                    self.fx._call(self.module, **overrides)
        for field, invalid in (("max_document_bytes", 16777217), ("max_output_bytes", 16777217),
                               ("max_trace_bytes", 67108864), ("ignore_documents", True)):
            policy = copy.deepcopy(self.fx.kw["rerank_policy"])
            policy["resources"][field] = invalid
            with self.subTest(field=field), self.assertRaises(self.module.ExposureRefusal):
                self.fx._call(self.module, **self._override(policy))
        policy = copy.deepcopy(self.fx.kw["rerank_policy"])
        del policy["resources"]["max_document_bytes"]
        with self.assertRaises(self.module.ExposureRefusal):
            self.fx._call(self.module, **self._override(policy))

    def test_late_invalid_artifact_refuses_before_copy_hash_or_serialization(self):
        self._inputs()
        cycle = {}
        cycle["self"] = cycle
        for field, invalid in (("capture", cycle), ("baseline", {"bad": float("inf")})):
            replay = {**self.fx.kw["replay_inputs"], field: invalid}
            with self.subTest(field=field), \
                    mock.patch("json.dumps", side_effect=AssertionError("serialized malformed compound input")), \
                    mock.patch("copy.deepcopy", side_effect=AssertionError("copied malformed compound input")), \
                    mock.patch.object(self.module, "_rank_query", side_effect=AssertionError("scored malformed compound input")), \
                    self.assertRaises(self.module.ExposureRefusal):
                self.fx._call(self.module, replay_inputs=replay)

    def test_literal_layout_cannot_omit_missing_extra_or_foreign_replay_branches(self):
        self._inputs()
        for replay in ({**self.fx.kw["replay_inputs"], "ignored_source": {}},
                       {key: value for key, value in self.fx.kw["replay_inputs"].items() if key != "capture"},
                       {**self.fx.kw["replay_inputs"], "capture": []}):
            with self.assertRaises(self.module.ExposureRefusal):
                self.fx._call(self.module, replay_inputs=replay)

    def test_full_trace_capacity_still_refuses_entire_v2_roster_without_clipping(self):
        selected = {**original.activation_tests.POLICY, "max_total_uses": 1}
        self._inputs(selected=selected)
        with mock.patch.object(self.module, "_rank_query", side_effect=AssertionError("ranked clipped complete history")), \
                mock.patch("siaactivation.rank_traces", side_effect=AssertionError("scored before full trace admission")), \
                self.assertRaises(self.module.ExposureRefusal):
            self.fx._call(self.module)

    def test_rehashed_measurement_and_source_cannot_use_envelope_admission_as_provenance(self):
        self._inputs()
        plan = copy.deepcopy(self.fx.kw["measurement_plan"])
        plan["baseline"]["answer_key"][0]["answer"]["sequences"] = ["0"]
        plan["plan_sha256"] = original.body_digest(plan, "plan_sha256")
        with self.assertRaises(self.module.ExposureRefusal):
            self.fx._call(self.module, measurement_plan=plan, expected_measurement_plan_sha256=plan["plan_sha256"])
        replay = copy.deepcopy(self.fx.kw["replay_inputs"])
        replay["expected_capture_sha256"] = "0" * 64
        with self.assertRaises(self.module.ExposureRefusal):
            self.fx._call(self.module, replay_inputs=replay)

    def test_heldout_requires_preexisting_v2_policy_identity_with_same_grid_and_selected_member(self):
        self._inputs(split="heldout")
        result = self.fx._call(self.module)
        freeze = result["measurement_plan"]["baseline"]["parameter_freeze"]["parameters"]
        self.assertEqual(freeze["event_exposure_policy_sha256"], self.fx.kw["expected_rerank_policy_sha256"])
        self.assertEqual(freeze["activation_grid_sha256"], self.fx.kw["rerank_policy"]["activation_grid_sha256"])
        self.assertEqual(freeze["selected_activation_policy_sha256"], self.fx.kw["expected_activation_policy_sha256"])
        old_policy = _LEGACY_POLICY(self.fx.kw["replay_inputs"]["expected_protocol_sha256"])
        self.assertEqual(old_policy["activation_grid_sha256"], result["activation_grid_sha256"])
        with self.assertRaises(self.module.ExposureRefusal):
            self.fx._call(self.module, **self._override(old_policy))
        changed = copy.deepcopy(self.fx.kw["rerank_policy"])
        changed["resources"]["max_input_bytes"] = 16777216
        with self.assertRaises(self.module.ExposureRefusal):
            self.fx._call(self.module, **self._override(changed))


if __name__ == "__main__":
    unittest.main()
