"""Actual held delivery capture through a retained source checkpoint root."""

import copy
import tempfile
import unittest
from unittest import mock

import siahistoryroot as roots
import siasourcecheckpoint as api
from tests import test_controller_source_capture_v3 as fixtures


class CheckpointDeliveryCapture(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.ControllerSourceCaptureV3(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def capture(self, f, owner, directory, root, **changes):
        return api.capture_root_delivery(vars(owner), **{
            "memo": f.case.live.memo, "admitted_status": f.status,
            "directory": directory, "expected_root_sha256": root["root_sha256"],
            "observed_at": f.request["observed_at"],
            "journal_limits": f.request["journal_limits"],
            "expected_journal_limits_sha256": f.request["expected_journal_limits_sha256"],
            "expected_adoption_sha256": f.request["expected_adoption_sha256"], **changes})

    def test_actual_epoch_and_journal_are_retained_without_publication(self):
        with self.case.prepared(nonidle=True) as f, tempfile.TemporaryDirectory(prefix="sia-checkpoint-delivery-") as directory:
            root = roots.prepare(vars(f.case.lib), memo=f.case.live.memo, admitted_status=f.status, directory=directory)
            before = copy.deepcopy(f.case.live.memo)
            with self.case.capture_owner(f) as owner:
                owner._load_live_publication()
                with self.case.no_effects(f, owner):
                    result = self.capture(f, owner, directory, root)
                api.validate_capture(vars(owner), result, result["batch_sha256"])
            self.assertEqual(result["schema"], "sia-controller-source-checkpoint-capture-v3")
            self.assertEqual(result["delivery_input"]["epoch_view"]["parent_generation"], f.generation)
            self.assertEqual(result["delivery_input"]["expected_adoption_sha256"], f.adopted["expected_adoption_sha256"])
            self.assertEqual(result["delivery_input"]["journal"]["records"], [])
            self.assertIsNone(result["idle_input"])
            self.assertEqual(f.case.live.memo, before)
            changed = copy.deepcopy(result)
            wrapped = changed["delivery_input"]
            wrapped["expected_adoption_sha256"] = "f" * 64
            wrapped["input_sha256"] = api.source.native_sha(vars(owner), {
                key: value for key, value in wrapped.items() if key != "input_sha256"})
            changed["batch_sha256"] = api.source.native_sha(vars(owner), {
                key: value for key, value in changed.items() if key != "batch_sha256"})
            with self.assertRaises((ValueError, RuntimeError, OSError)):
                api.validate_capture(vars(owner), changed, changed["batch_sha256"])

    def test_real_notification_fence_is_retained_not_cleared(self):
        with self.case.prepared(notifications=True) as f, tempfile.TemporaryDirectory(prefix="sia-checkpoint-delivery-") as directory:
            root = roots.prepare(vars(f.case.lib), memo=f.case.live.memo, admitted_status=f.status, directory=directory)
            marker = copy.deepcopy(f.case.lib._mark_notify_baseline_attempt(f.case.live.memo))
            with self.case.capture_owner(f) as owner:
                owner._load_live_publication()
                with self.case.no_effects(f, owner):
                    result = self.capture(f, owner, directory, root)
                api.validate_capture(vars(owner), result, result["batch_sha256"])
            self.assertEqual(result["notification_baseline_attempt"], marker)
            self.assertEqual(result["delivery_input"]["epoch_view"]["status"], "held-capturable-not-ready")
            self.assertEqual(f.case.live.memo[f.case.lib.NOTIFY_BASELINE_ATTEMPT_KEY], marker)

    def test_wrong_adoption_refuses_before_collection(self):
        with self.case.prepared() as f, tempfile.TemporaryDirectory(prefix="sia-checkpoint-delivery-") as directory:
            root = roots.prepare(vars(f.case.lib), memo=f.case.live.memo, admitted_status=f.status, directory=directory)
            with self.case.capture_owner(f) as owner:
                owner._load_live_publication()
                with mock.patch.object(api.source, "_collect", side_effect=AssertionError("unadmitted collector")):
                    with self.assertRaises((ValueError, OSError)):
                        self.capture(f, owner, directory, root, expected_adoption_sha256="f" * 64)
