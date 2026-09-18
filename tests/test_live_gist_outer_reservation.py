"""Focused v2 enclosing-document reservation controls.

The established fixture caps remain unchanged. Every boundary comparison
measures actual serialized documents inside the test; no arithmetic size
estimate, lowered production ceiling, or trace-budget completeness claim is
introduced. The historical pages are synthetic, unobserved fixture inputs.

This is a separate test module using the existing native/live fixture. It
does not subclass its TestCase, so importing it does not inherit that suite.
"""

import copy
import unittest
from unittest import mock

from tests import test_live_gist_binding as binding_tests


class LiveGistOuterReservation(unittest.TestCase):
    def setUp(self):
        self.case = binding_tests.LiveGistBinding(methodName="runTest")
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()

    def _append_unobserved_history(self, request):
        intake = request["intake"]
        limits = request["episode_bindings"]["live_policy"]["limits"]
        self.assertLess(len(intake["pages"]), limits["max_versions"])
        source = intake["pages"][0]
        raw = source["content"].encode("utf-8")
        self.assertLessEqual(len(raw), limits["max_content_bytes"])
        # Pad genuine fixture page bytes to the existing admitted page limit.
        # Each unique historical subject remains outside current_versions
        # and observations, so it introduces no extra controller activity.
        raw = raw.ljust(limits["max_content_bytes"], b"x")
        page = self.case.lib._corpus_page_version_from_bytes(
            slug="fixture-unobserved-history-" + str(len(intake["pages"])),
            raw=raw,
        )
        self.assertEqual(len(page["content"].encode("utf-8")), limits["max_content_bytes"])
        self.assertNotIn(page["version_sha256"], intake["current_versions"])
        self.assertNotIn(page["version_sha256"],
                         [row["version_sha256"] for row in intake["observations"]])
        intake["pages"].append(page)
        return page

    @staticmethod
    def _required_intake_copies(request, *, idle):
        # These are literal required locations in the actual transition,
        # with all other fields omitted. Container aliasing must not erase
        # any serialized occurrence. The idle copy belongs to the new v2
        # binding; the other locations are shared enclosing documents.
        intake = request["intake"]
        state = {"intake": intake}
        if idle:
            state["idle"] = {"binding": {"intake": intake}}
        return {"state": state, "history_capture": {"intake": intake}}

    def _pulse_args(self, request, *, idle):
        bindings = request["episode_bindings"]
        policy = bindings["live_policy"]
        deliveries = {
            "schema": "sia-live-deliveries-v1", "epoch_id": bindings["epoch_id"],
            "complete": True, "records": [],
        }
        return {
            "intake": request["intake"],
            "expected_intake_sha256": request["expected_intake_sha256"],
            "deliveries": deliveries,
            "expected_deliveries_sha256": binding_tests.digest(deliveries),
            "previous_state": None, "expected_previous_state_sha256": None,
            "policy": policy, "expected_policy_sha256": binding_tests.digest(policy),
            "observed_at": bindings["observed_at"], "idle": idle,
            "gist_inputs": self.case.wrapper(request) if idle else None,
        }

    def _overflowing_request(self, *, idle):
        request = self.case.request(("1",))
        baseline = copy.deepcopy(request)
        limits = request["episode_bindings"]["live_policy"]["limits"]
        while len(binding_tests.canonical(self._required_intake_copies(request, idle=idle))) \
                <= limits["max_output_bytes"]:
            self._append_unobserved_history(request)
        # Reseal the complete intake, binding, nested gist documents and live
        # policy pins. _pulse_args separately pins that same outer policy.
        self.case.reseal(request)
        args = self._pulse_args(request, idle=idle)
        self.assertEqual(request["episode_bindings"]["live_policy"],
                         baseline["episode_bindings"]["live_policy"])
        self.assertEqual(args["expected_policy_sha256"],
                         request["episode_bindings"]["live_policy_sha256"])
        self.assertEqual(request["intake"]["observations"], baseline["intake"]["observations"])
        self.assertEqual(request["intake"]["current_versions"], baseline["intake"]["current_versions"])
        self.assertEqual(request["episode_bindings"]["episodes"],
                         baseline["episode_bindings"]["episodes"])
        self.assertEqual(request["gist_inputs"], baseline["gist_inputs"])
        self.assertLessEqual(len(binding_tests.canonical(args)), limits["max_input_bytes"])
        self.assertGreater(
            len(binding_tests.canonical(self._required_intake_copies(request, idle=idle))),
            limits["max_output_bytes"],
        )
        return request, args

    def _assert_capacity_refusal_before_numeric_work(self, request, args, *, standalone):
        original = copy.deepcopy(request)
        reconstruct = mock.Mock(
            side_effect=AssertionError("_reconstruct reached before v2 enclosing-copy reservation"))
        coretrieval = mock.Mock(
            side_effect=AssertionError("coretrieval learner reached before v2 enclosing-copy reservation"))
        replay = mock.Mock(
            side_effect=AssertionError("gist replay reached before v2 enclosing-copy reservation"))
        with self.case.pure_boundary(), \
                mock.patch.object(self.case.live, "_reconstruct", reconstruct), \
                mock.patch.object(self.case.live.coretrieval, "learn_coretrieval", coretrieval), \
                mock.patch.object(self.case.gist, "replay_gist", replay):
            if standalone:
                # The whole standalone binding still admits under the real
                # cap, including its existing output reservation. The new
                # enclosing copies are the reason this pulse must refuse.
                original_bytes, dispositions, ceiling = self.case.component._prepare_request(request)
                self.assertEqual(original_bytes, binding_tests.canonical(request))
                self.assertTrue(dispositions)
                self.assertEqual(ceiling, args["policy"]["limits"]["max_output_bytes"])
            with self.assertRaises(self.case.live.LiveLoopRefusal) as raised:
                self.case.live.prepare_pulse(**args)
        self.assertEqual(raised.exception.reason, "bound-pulse-output-reservation-capacity")
        reconstruct.assert_not_called()
        coretrieval.assert_not_called()
        replay.assert_not_called()
        self.assertEqual(request, original)

    def test_v2_idle_new_binding_intake_copy_reserves_before_numeric_work(self):
        request, args = self._overflowing_request(idle=True)
        # Without the newly embedded v2 binding intake, these required outer
        # intake copies still fit. This control isolates that new duplication
        # and does not assert anything about legacy trace-size admission.
        self.assertLessEqual(
            len(binding_tests.canonical(self._required_intake_copies(request, idle=False))),
            args["policy"]["limits"]["max_output_bytes"],
        )
        self._assert_capacity_refusal_before_numeric_work(request, args, standalone=True)

    def test_v2_nonidle_known_outer_copies_reserve_before_numeric_work(self):
        request, args = self._overflowing_request(idle=False)
        self.assertIsNone(args["gist_inputs"])
        self._assert_capacity_refusal_before_numeric_work(request, args, standalone=False)

    def test_v2_continuation_reserves_before_prior_state_numeric_reconstruction(self):
        for idle in (True, False):
            with self.subTest(idle=idle):
                baseline_request = self.case.request(("1",))
                with self.case.pure_boundary():
                    baseline = self.case.live.prepare_pulse(
                        **self._pulse_args(baseline_request, idle=idle))
                request, args = self._overflowing_request(idle=idle)
                args["previous_state"] = baseline["state"]
                args["expected_previous_state_sha256"] = baseline["state_sha256"]
                self.assertLessEqual(len(binding_tests.canonical(args)),
                                     args["policy"]["limits"]["max_input_bytes"])
                self.assertEqual(request["intake"]["observations"],
                                 baseline["state"]["intake"]["observations"])
                self.assertEqual(request["intake"]["pages"][:len(baseline_request["intake"]["pages"])],
                                 baseline["state"]["intake"]["pages"])
                self._assert_capacity_refusal_before_numeric_work(
                    request, args, standalone=idle)

    def test_v2_fitting_unobserved_history_retains_complete_transition(self):
        for idle in (True, False):
            with self.subTest(idle=idle):
                request = self.case.request(("1",))
                baseline_args = self._pulse_args(request, idle=idle)
                with self.case.pure_boundary():
                    baseline = self.case.live.prepare_pulse(**baseline_args)
                historical = self._append_unobserved_history(request)
                self.case.reseal(request)
                args = self._pulse_args(request, idle=idle)
                original = copy.deepcopy(request)
                self.assertEqual(args["policy"], baseline["state"]["policy"])
                self.assertEqual(args["expected_policy_sha256"],
                                 request["episode_bindings"]["live_policy_sha256"])
                self.assertLessEqual(
                    len(binding_tests.canonical(self._required_intake_copies(request, idle=idle))),
                    args["policy"]["limits"]["max_output_bytes"],
                )
                with self.case.pure_boundary():
                    if idle:
                        self.case.component._prepare_request(request)
                    result = self.case.live.prepare_pulse(**args)
                self.assertEqual(request, original)
                self.assertEqual(result["status"], "planned")
                self.assertLessEqual(len(binding_tests.canonical(result)),
                                     args["policy"]["limits"]["max_output_bytes"])
                self.assertEqual(result["state"]["intake"], request["intake"])
                self.assertEqual(result["history_capture"]["intake"], request["intake"])
                self.assertIn(historical, result["state"]["intake"]["pages"])
                self.assertEqual(result["state"]["intake"]["observations"],
                                 baseline["state"]["intake"]["observations"])
                self.assertEqual(result["state"]["uses"], baseline["state"]["uses"])
                if idle:
                    binding = result["state"]["idle"]["binding"]
                    self.assertEqual(binding["intake"], request["intake"])
                    self.assertEqual(binding["gist"], baseline["state"]["idle"]["binding"]["gist"])
                else:
                    self.assertEqual(result["state"]["idle"], {"requested": False, "gist": None})
                    self.assertEqual(result["gist_pages"], [])
