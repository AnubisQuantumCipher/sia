"""Compact source epoch preparation from independently pinned checkpoints."""

import copy
import unittest
from unittest import mock

import siasourcecheckpoint as api
import siasourcebatch as source
from tests import test_event_checkpoint_delta as fixtures
from tests.test_history_block import digest


class SourceCheckpointEpoch(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.CheckpointDelta(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.owner = self.case.owner
        self.checkpoint, self.delta, self.request = self.case.inputs()
        self.committed = {"source_batch_sha256": "a" * 64,
                          "live_generation_sha256": "b" * 64,
                          "source_effects_receipt_sha256": "c" * 64}

    def prepare(self):
        return api.prepare_epoch(
            self.owner, checkpoint=self.checkpoint, expected_checkpoint_sha256=digest(self.checkpoint),
            committed=self.committed, root_sha256="d" * 64,
            observed_at=self.delta["observed_at"])

    def test_compact_epoch_and_current_projection_match_complete_replay(self):
        epoch = self.prepare()
        self.assertEqual(epoch["schema"], "sia-controller-source-checkpoint-epoch-v1")
        self.assertNotIn("history", epoch)
        self.assertNotIn("expected_history_sha256", epoch)
        self.assertNotIn("checkpoint", epoch)
        self.assertEqual(epoch["checkpoint_sha256"], digest(self.checkpoint))
        self.assertEqual(epoch["predecessor"], self.committed)
        self.assertEqual(epoch["epoch_id"], self.checkpoint["intake"]["epoch_id"])
        self.assertEqual(epoch["non_claims"], list(api.NON_CLAIMS))
        expected = self.case.case.project(self.request)
        with mock.patch.object(api.checkpoints.replay, "prepare", side_effect=AssertionError("prefix replay")):
            result = api.project(
                self.owner, epoch=epoch, expected_epoch_sha256=digest(epoch),
                checkpoint=self.checkpoint, entry=self.delta["entry"],
                expected_entry_sha256=digest(self.delta["entry"]), observed_at=self.delta["observed_at"])
        self.assertEqual(result["checkpoint"]["intake"], expected["intake"])
        with self.assertRaises(ValueError):
            source._validate_epoch(self.owner, epoch, digest(epoch), self.delta["observed_at"], initial=False)

    def test_context_drift_resealed_epoch_refuses_before_fold(self):
        epoch = self.prepare()
        epoch["configuration"]["custom_collectors"].clear()
        epoch["expected_configuration_sha256"] = source._component_sha(self.owner, epoch["configuration"])
        with mock.patch.object(api.checkpoints.replay, "_fold_entry", side_effect=AssertionError("drifted fold")):
            with self.assertRaises(ValueError):
                api.project(self.owner, epoch=epoch, expected_epoch_sha256=digest(epoch),
                            checkpoint=self.checkpoint, entry=self.delta["entry"],
                            expected_entry_sha256=digest(self.delta["entry"]), observed_at=self.delta["observed_at"])

    def test_bad_root_commit_or_clock_refuses(self):
        for overrides in ({"root_sha256": "bad"}, {"committed": {}},
                          {"observed_at": self.checkpoint["intake"]["started_at"] - 1}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                api.prepare_epoch(self.owner, **{
                    "checkpoint": self.checkpoint, "expected_checkpoint_sha256": digest(self.checkpoint),
                    "committed": self.committed, "root_sha256": "d" * 64,
                    "observed_at": self.delta["observed_at"], **overrides})

    def test_valid_resealed_policy_drift_is_not_a_checkpoint_migration(self):
        epoch = self.prepare()
        epoch["live_policy"]["workspace"]["slots"] = 2
        epoch["expected_live_policy_sha256"] = source._component_sha(self.owner, epoch["live_policy"])
        epoch["profile"]["live_policy_sha256"] = epoch["expected_live_policy_sha256"]
        epoch["expected_profile_sha256"] = source._component_sha(self.owner, epoch["profile"])
        source._validate_epoch_context(self.owner, epoch)
        with self.assertRaises(ValueError) as caught:
            api.project(self.owner, epoch=epoch, expected_epoch_sha256=digest(epoch),
                        checkpoint=self.checkpoint, entry=self.delta["entry"],
                        expected_entry_sha256=digest(self.delta["entry"]), observed_at=self.delta["observed_at"])
        self.assertIn("checkpoint-epoch-context-drift", str(caught.exception))

    def test_malformed_epoch_has_named_refusal(self):
        with self.assertRaises(source.SourceBatchRefusal) as caught:
            api.project(self.owner, epoch={}, expected_epoch_sha256=digest({}),
                        checkpoint=self.checkpoint, entry=self.delta["entry"],
                        expected_entry_sha256=digest(self.delta["entry"]), observed_at=self.delta["observed_at"])
        self.assertIn("checkpoint-epoch-shape", str(caught.exception))

    def test_wrong_entry_pin_and_epoch_clock_refuse(self):
        epoch = self.prepare()
        for overrides in ({"expected_entry_sha256": "e" * 64},
                          {"observed_at": self.checkpoint["intake"]["started_at"]}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                api.project(self.owner, **{
                    "epoch": epoch, "expected_epoch_sha256": digest(epoch), "checkpoint": self.checkpoint,
                    "entry": self.delta["entry"], "expected_entry_sha256": digest(self.delta["entry"]),
                    "observed_at": self.delta["observed_at"], **overrides})

    def test_changed_caller_entry_after_projection_refuses(self):
        epoch = self.prepare()
        original = api.checkpoints.project_delta
        entry = copy.deepcopy(self.delta["entry"])

        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            entry["event_batches"].clear()
            return result

        with mock.patch.object(api.checkpoints, "project_delta", side_effect=changed):
            with self.assertRaises(ValueError):
                api.project(self.owner, epoch=epoch, expected_epoch_sha256=digest(epoch),
                            checkpoint=self.checkpoint, entry=entry,
                            expected_entry_sha256=digest(entry), observed_at=self.delta["observed_at"])
