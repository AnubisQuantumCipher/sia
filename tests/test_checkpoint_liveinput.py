"""Actual compact capture reaches the real live pulse without publishing it."""

import contextlib
import copy
import tempfile
import unittest
from unittest import mock

import siacontrollerliveinput as api
import sialiveloop as live
import siahistoryroot as roots
import siasourcecheckpoint as checkpoint
from tests import test_checkpoint_delivery_capture as capture_tests


class CheckpointLiveInput(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(getattr(api, "prepare_inputs_checkpoint", None)),
                        "missing compact capture live-input adapter")
        self.capture_case = capture_tests.CheckpointDeliveryCapture(methodName="runTest")
        self.capture_case.setUp()
        self.addCleanup(self.capture_case.doCleanups)

    @contextlib.contextmanager
    def captured(self, *, nonidle=False, fenced=False):
        fixture = self.capture_case.case
        # Keep the genuinely acknowledged custom episode for gist testing.
        # Notification-only bootstrap has no episode and cannot warrant gist.
        with fixture.prepared(nonidle=nonidle) as f, tempfile.TemporaryDirectory(prefix="sia-checkpoint-live-") as directory:
            root = roots.prepare(vars(f.case.lib), memo=f.case.live.memo, admitted_status=f.status, directory=directory)
            if fenced:
                f.case.lib._mark_notify_baseline_attempt(f.case.live.memo)
            with fixture.capture_owner(f) as owner:
                owner._load_live_publication()
                with fixture.no_effects(f, owner):
                    batch = self.capture_case.capture(f, owner, directory, root)
                yield f, vars(owner), batch

    def prepare(self, owner, batch, generation):
        return api.prepare_inputs_checkpoint(
            owner, batch=batch, previous_generation=generation,
            expected_previous_generation_sha256=generation["generation_sha256"])

    def test_actual_nonempty_capture_runs_real_pulse_and_preserves_all_intake(self):
        with self.captured(nonidle=True) as (f, owner, batch):
            before = copy.deepcopy((batch, f.generation, f.case.live.memo))
            with mock.patch("builtins.open", side_effect=AssertionError("unexpected IO")), \
                    mock.patch("os.open", side_effect=AssertionError("unexpected IO")), \
                    mock.patch.object(live, "prepare_pulse", side_effect=AssertionError("adapter ran pulse")):
                request = self.prepare(owner, batch, f.generation)
            transition = live.prepare_pulse(**request)
            self.assertEqual(transition["state"]["intake"], batch["intake_projection"]["checkpoint"]["intake"])
            self.assertEqual(transition["state"]["deliveries"], batch["delivery_input"]["binding"]["deliveries"])
            self.assertFalse(request["idle"])
            self.assertEqual((batch, f.generation, f.case.live.memo), before)
            changed = copy.deepcopy(f.generation)
            changed["candidate_sha256"] = "f" * 64
            changed["generation_sha256"] = live._own(changed, "generation_sha256")
            with self.assertRaises(ValueError):
                self.prepare(owner, batch, changed)
            with self.assertRaises(ValueError):
                api.prepare_inputs_v4(owner, batch=batch, previous_generation=f.generation,
                                      expected_previous_generation_sha256=f.generation["generation_sha256"])
            changed_batch = copy.deepcopy(batch)
            self.assertTrue(changed_batch["intake_projection"]["associations"])
            changed_batch["intake_projection"]["associations"] = []
            changed_batch["batch_sha256"] = checkpoint.source.native_sha(owner, {
                key: value for key, value in changed_batch.items() if key != "batch_sha256"})
            with self.assertRaises(ValueError):
                self.prepare(owner, changed_batch, f.generation)

    def test_actual_fenced_idle_capture_preserves_episode_bound_gist(self):
        with self.captured(fenced=True) as (f, owner, batch):
            marker = copy.deepcopy(batch["notification_baseline_attempt"])
            request = self.prepare(owner, batch, f.generation)
            transition = live.prepare_pulse(**request)
            self.assertTrue(request["idle"])
            self.assertEqual(request["gist_inputs"], batch["idle_input"])
            self.assertEqual(transition["state"]["idle"]["binding"]["episode_bindings"], batch["idle_input"]["episode_bindings"])
            self.assertTrue(transition["gist_pages"])
            self.assertTrue(all(page["origin"] == "derived" for page in transition["gist_pages"]))
            self.assertEqual(f.case.live.memo[owner["NOTIFY_BASELINE_ATTEMPT_KEY"]], marker)
