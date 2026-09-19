"""First normalized episode records survive checkpoint continuation exactly."""

import copy
import unittest
from unittest import mock

import siaeventcheckpoint as api
import siacontrolleridle as idle
import siacontrollerepoch as epochs
import siasourcecheckpoint as source_checkpoint
from tests import test_event_checkpoint_delta as fixtures
from tests import test_live_loop as clocks
from tests.test_history_block import digest


class CheckpointEpisodes(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.CheckpointDelta(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.owner = self.case.owner

    def inputs(self):
        checkpoint, delta, request = self.case.inputs()
        initial = self.case.case.request([request["history"]["entries"][0]])
        checkpoint = api.bootstrap_episodes(self.owner, request=initial, expected_request_sha256=digest(initial))
        delta["parent_checkpoint_sha256"] = digest(checkpoint)
        return checkpoint, delta, request

    def test_bootstrap_and_advance_match_full_idle_episode_roster(self):
        checkpoint, delta, request = self.inputs()
        expected_projection = self.case.case.project(request)
        expected = idle._episode_records(
            {"epoch_id": request["history"]["epoch_id"], "history": request["history"]}, expected_projection)
        with mock.patch.object(api.replay, "prepare", side_effect=AssertionError("prefix replay")):
            advanced = self.case.advance(checkpoint, delta)
        self.assertEqual(advanced["schema"], "sia-event-replay-checkpoint-v3")
        self.assertEqual(advanced["episode_records"], expected)
        self.assertEqual(advanced["episode_records"][0], checkpoint["episode_records"][0])
        self.assertEqual(advanced["intake"], expected_projection["intake"])
        self.assertEqual(api.admit(self.owner, checkpoint=advanced, expected_checkpoint_sha256=digest(advanced)), advanced)

    def test_resealed_record_changes_refuse(self):
        checkpoint, delta, request = self.inputs()
        for field, value in (("source_id", "sense_custom:wrong"), ("native_occurrence", {}),
                             ("event_record", {}), ("observation_id", "a" * 64)):
            changed = copy.deepcopy(checkpoint)
            changed["episode_records"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                api.admit(self.owner, checkpoint=changed, expected_checkpoint_sha256=digest(changed))

    def test_episode_bytes_are_reserved_before_fold(self):
        checkpoint, delta, request = self.inputs()
        with mock.patch.object(api, "_episode_records", return_value=["x" * api.blocks.MAX_DOCUMENT_BYTES]), \
                mock.patch.object(api.replay, "_fold_entry", side_effect=AssertionError("oversized fold")):
            with self.assertRaises(ValueError):
                self.case.advance(checkpoint, delta)

    def test_old_checkpoint_does_not_invent_missing_records(self):
        checkpoint, delta, request = self.case.inputs()
        advanced = self.case.advance(checkpoint, delta)
        self.assertEqual(advanced["schema"], "sia-event-replay-checkpoint-v2")
        self.assertNotIn("episode_records", advanced)

    def test_custom_only_idle_preserves_episodes_without_native_acquisition(self):
        self.case.case.policy = copy.deepcopy(epochs.LIVE_POLICY)
        self.case.case.profile["live_policy_sha256"] = digest(self.case.case.policy)
        first = self.case.case.entry({"sense_custom:alpha": [self.case.case.event()]})
        self.case.case.publish_entry_fixture(first)
        request = self.case.case.request([first])
        observed_at = clocks.DELIVERED_AT
        checkpoint = api.bootstrap_episodes(self.owner, request=request, expected_request_sha256=digest(request))
        epoch = source_checkpoint.prepare_epoch(
            self.owner, checkpoint=checkpoint, expected_checkpoint_sha256=digest(checkpoint),
            committed={"source_batch_sha256": "a" * 64, "live_generation_sha256": "b" * 64,
                       "source_effects_receipt_sha256": "c" * 64}, root_sha256="d" * 64,
            observed_at=observed_at)
        entry = self.case.case.entry({}, stamp=observed_at, batch_id="custom-only-idle")
        projection = source_checkpoint.project(
            self.owner, epoch=epoch, expected_epoch_sha256=digest(epoch), checkpoint=checkpoint,
            entry=entry, expected_entry_sha256=digest(entry), observed_at=observed_at)
        with mock.patch("siabench.capture_native_history_v2", side_effect=AssertionError("custom is not native")):
            result = idle.capture_checkpoint(self.owner, epoch=epoch, projection=projection, observed_at=observed_at)
            idle.validate_checkpoint(self.owner, epoch=epoch, projection=projection,
                                     observed_at=observed_at, idle_input=result)
        self.assertEqual(result["idle_without_native"]["availability"], "no-selected-supported-native-source")
        self.assertEqual(result["idle_without_native"]["episodes"], checkpoint["episode_records"])
