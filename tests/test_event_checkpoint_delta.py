"""Incremental replay against the same complete controlled source history."""

import copy
import unittest
from unittest import mock

import siaeventcheckpoint as api
from tests import test_event_live_intake as fixtures
from tests import test_live_loop as live_tests
from tests.test_history_block import digest


class CheckpointDelta(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.EventLiveIntakeProjection(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.owner = vars(self.case.lib)

    def inputs(self, *, append=True, repeat_initial=False):
        initial_events = [self.case.event()]
        if repeat_initial:
            initial_events.append(self.case.event())
        first = self.case.entry({"sense_custom:alpha": initial_events})
        self.case.publish_entry_fixture(first)
        events = [self.case.event("2026-01-07")]
        if append:
            events.append(self.case.event("2026-01-07", occurrence="delta-new"))
        later = self.case.entry({"sense_custom:alpha": events},
                                stamp=live_tests.DELIVERED_AT, batch_id="delta-later")
        request = self.case.request([first])
        checkpoint = api.bootstrap_incremental(self.owner, request=request,
                                               expected_request_sha256=digest(request))
        delta = {"schema": "sia-event-replay-delta-v1", "parent_checkpoint_sha256": digest(checkpoint),
                 "entry": later, "observed_at": later["source_returns"]["observed_at"],
                 "non_claims": list(api.DELTA_NON_CLAIMS)}
        return checkpoint, delta, self.case.request([first, later])

    def advance(self, checkpoint, delta, *, owner=None):
        return api.advance(self.owner if owner is None else owner, checkpoint=checkpoint,
                           expected_checkpoint_sha256=digest(checkpoint), delta=delta,
                           expected_delta_sha256=digest(delta))

    def test_advance_matches_whole_replay_without_old_history(self):
        checkpoint, delta, request = self.inputs()
        before = copy.deepcopy((checkpoint, delta))
        expected = self.case.project(request)
        with mock.patch.object(api.replay, "prepare", side_effect=AssertionError("whole-history replay")):
            advanced = self.advance(checkpoint, delta)
        self.assertEqual(advanced["intake"], expected["intake"])
        self.assertEqual(advanced["source_non_claims"], expected["source_non_claims"])
        self.assertEqual(advanced["parent_checkpoint_sha256"], digest(checkpoint))
        self.assertEqual(advanced["last_delta_sha256"], digest(delta))
        self.assertEqual((checkpoint, delta), before)
        self.assertEqual(api.admit(self.owner, checkpoint=advanced,
                                   expected_checkpoint_sha256=digest(advanced)), advanced)

    def test_delta_projection_retains_only_current_exact_associations(self):
        checkpoint, delta, request = self.inputs()
        expected = self.case.project(request)
        with mock.patch.object(api.replay, "prepare", side_effect=AssertionError("whole-history replay")):
            result = api.project_delta(
                self.owner, checkpoint=checkpoint, expected_checkpoint_sha256=digest(checkpoint),
                delta=delta, expected_delta_sha256=digest(delta))
        self.assertEqual(result["schema"], "sia-event-delta-projection-v1")
        self.assertEqual(result["status"], "prepared-not-authorized")
        self.assertEqual(result["checkpoint"], self.advance(checkpoint, delta))
        self.assertEqual(result["checkpoint_sha256"], digest(result["checkpoint"]))
        self.assertEqual(result["parent_checkpoint_sha256"], digest(checkpoint))
        self.assertEqual(result["delta_sha256"], digest(delta))
        self.assertEqual(result["checkpoint"]["intake"], expected["intake"])
        self.assertEqual(result["associations"], [
            row for row in expected["associations"]
            if row["source_returns_sha256"] == delta["entry"]["expected_source_returns_sha256"]])
        self.assertEqual([row["status"] for row in result["associations"]],
                         ["already-observed", "first-observation"])
        self.assertNotIn("history", result)
        self.assertEqual(result["non_claims"], list(api.PROJECTION_NON_CLAIMS))

    def test_projection_empty_delta_keeps_checkpoint_without_associations(self):
        checkpoint, delta, request = self.inputs()
        delta["entry"] = self.case.entry({}, stamp=delta["observed_at"], batch_id="empty-projection")
        result = api.project_delta(
            self.owner, checkpoint=checkpoint, expected_checkpoint_sha256=digest(checkpoint),
            delta=delta, expected_delta_sha256=digest(delta))
        self.assertEqual(result["associations"], [])
        self.assertEqual(result["checkpoint"]["intake"], checkpoint["intake"])

    def test_projection_reserves_its_envelope_before_fold(self):
        checkpoint, delta, request = self.inputs()
        original = api.replay._reservation

        def enlarged(*args):
            skeleton, content = original(*args)
            skeleton["associations"] = "x" * api.blocks.MAX_DOCUMENT_BYTES
            return skeleton, content

        with mock.patch.object(api.replay, "_reservation", side_effect=enlarged), \
                mock.patch.object(api.replay, "_fold_entry", side_effect=AssertionError("oversized fold")):
            with self.assertRaises(ValueError):
                api.project_delta(
                    self.owner, checkpoint=checkpoint, expected_checkpoint_sha256=digest(checkpoint),
                    delta=delta, expected_delta_sha256=digest(delta))

    def test_projection_changed_detached_associations_refuse(self):
        checkpoint, delta, request = self.inputs()
        original = api.json.loads

        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            if isinstance(result, dict) and result.get("schema") == "sia-event-delta-projection-v1":
                result["associations"].clear()
            return result

        with mock.patch.object(api.json, "loads", side_effect=changed):
            with self.assertRaises(ValueError) as caught:
                api.project_delta(
                    self.owner, checkpoint=checkpoint, expected_checkpoint_sha256=digest(checkpoint),
                    delta=delta, expected_delta_sha256=digest(delta))
        self.assertIn("checkpoint-delta-input-or-output-changed", str(caught.exception))

    def test_projection_wrong_pin_refuses_before_fold(self):
        checkpoint, delta, request = self.inputs()
        with mock.patch.object(api.replay, "_fold_entry", side_effect=AssertionError("unbound fold")):
            with self.assertRaises(ValueError):
                api.project_delta(
                    self.owner, checkpoint=checkpoint, expected_checkpoint_sha256=digest(checkpoint),
                    delta=delta, expected_delta_sha256="a" * 64)

    def test_repeat_keeps_first_clock_and_version(self):
        checkpoint, delta, request = self.inputs(append=False)
        advanced = self.advance(checkpoint, delta)
        self.assertEqual(advanced["intake"]["observations"], checkpoint["intake"]["observations"])
        self.assertEqual(advanced["first_associations"], checkpoint["first_associations"])

    def test_wrong_parent_and_duplicate_source_batch_refuse(self):
        checkpoint, delta, request = self.inputs()
        wrong = copy.deepcopy(delta)
        wrong["parent_checkpoint_sha256"] = "a" * 64
        with self.assertRaises(ValueError):
            self.advance(checkpoint, wrong)
        repeated = copy.deepcopy(delta)
        repeated["entry"] = request["history"]["entries"][0]
        repeated["observed_at"] = repeated["entry"]["source_returns"]["observed_at"]
        with self.assertRaises(ValueError):
            self.advance(checkpoint, repeated)

    def test_cumulative_event_limit_does_not_reset_per_delta(self):
        checkpoint, delta, request = self.inputs(repeat_initial=True)
        owner = {**self.owner, "MAX_SOURCE_REPLAY_EVENTS": 3}
        with self.assertRaises(ValueError) as caught:
            self.advance(checkpoint, delta, owner=owner)
        self.assertIn("checkpoint-total-event-capacity", str(caught.exception))

    def test_mutated_original_delta_after_fold_refuses(self):
        checkpoint, delta, request = self.inputs()
        original = api.replay._fold_entry

        def changing(*args):
            result = original(*args)
            delta["non_claims"].clear()
            return result

        with mock.patch.object(api.replay, "_fold_entry", side_effect=changing):
            with self.assertRaises(ValueError):
                self.advance(checkpoint, delta)

    def test_mutated_detached_delta_after_fold_refuses(self):
        checkpoint, delta, request = self.inputs()
        original = api.replay._fold_entry

        def changing(*args):
            result = original(*args)
            args[2]["source_returns"]["complete"] = False
            return result

        with mock.patch.object(api.replay, "_fold_entry", side_effect=changing):
            with self.assertRaises(ValueError):
                self.advance(checkpoint, delta)

    def test_v1_checkpoint_is_not_silently_upgraded(self):
        checkpoint, delta, request = self.inputs()
        initial = self.case.request([request["history"]["entries"][0]])
        legacy = api.bootstrap(self.owner, request=initial, expected_request_sha256=digest(initial))
        delta["parent_checkpoint_sha256"] = digest(legacy)
        with self.assertRaises(ValueError) as caught:
            self.advance(legacy, delta)
        self.assertIn("incremental-accounting-required", str(caught.exception))

    def test_wrong_delta_pin_and_clock_rollback_refuse(self):
        checkpoint, delta, request = self.inputs()
        with self.assertRaises(ValueError):
            api.advance(self.owner, checkpoint=checkpoint, expected_checkpoint_sha256=digest(checkpoint),
                        delta=delta, expected_delta_sha256="a" * 64)
        delta["observed_at"] = checkpoint["intake"]["started_at"]
        with self.assertRaises(ValueError):
            self.advance(checkpoint, delta)

    def test_oversized_reservation_refuses_before_fold(self):
        checkpoint, delta, request = self.inputs()
        with mock.patch.object(api.replay, "_reservation", return_value=("x" * api.blocks.MAX_DOCUMENT_BYTES, 0)), \
                mock.patch.object(api.replay, "_fold_entry", side_effect=AssertionError("oversized fold")):
            with self.assertRaises(ValueError):
                self.advance(checkpoint, delta)

    def test_rebased_duplicate_refuses_and_empty_next_step_preserves_intake(self):
        checkpoint, delta, request = self.inputs()
        advanced = self.advance(checkpoint, delta)
        repeated = copy.deepcopy(delta)
        repeated["parent_checkpoint_sha256"] = digest(advanced)
        with self.assertRaises(ValueError) as caught:
            self.advance(advanced, repeated)
        self.assertIn("checkpoint-duplicate-batch", str(caught.exception))
        empty = self.case.entry({}, stamp=advanced["observed_at"], batch_id="empty-after-delta")
        next_delta = {"schema": "sia-event-replay-delta-v1",
                      "parent_checkpoint_sha256": digest(advanced), "entry": empty,
                      "observed_at": advanced["observed_at"], "non_claims": list(api.DELTA_NON_CLAIMS)}
        following = self.advance(advanced, next_delta)
        self.assertEqual(following["intake"], advanced["intake"])
        self.assertEqual(following["total_returned_events"], advanced["total_returned_events"])
        self.assertEqual(following["parent_checkpoint_sha256"], digest(advanced))
