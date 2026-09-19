"""Durable compact source/live handoff, using the actual adopted package."""

import copy
import unittest
from unittest import mock

from tests import test_checkpoint_adoption as fixtures


class CheckpointLiveBinding(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.CheckpointAdoption(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_normal_binding_preserves_actual_notification_fence(self):
        with self.case.prepared(fenced=True) as (f, owner, package, request):
            api = self.case.api
            api.adopt_root(vars(owner), **request)
            before = copy.deepcopy(request["memo"])
            args = {key: value for key, value in request.items() if key not in {
                "journal_limits", "expected_journal_limits_sha256", "expected_adoption_sha256"}}
            self.assertTrue(api.stage_live_binding(vars(owner), **args))
            self.assertEqual(owner.load_memo(), args["memo"])
            self.assertEqual(api.source._notification_marker(vars(owner), args["memo"]),
                             api.source._notification_marker(vars(owner), before))
            self.assertFalse(api.stage_live_binding(vars(owner), **args))
            self.assertEqual(args["memo"]["controller_source_live_pending"]["source_batch_sha256"],
                             package["manifest"]["source_batch_sha256"])

    def test_actual_binding_and_durable_retry_without_recollection(self):
        self.assertTrue(callable(getattr(self.case.api, "stage_live_binding", None)),
                        "missing compact live handoff")
        with self.case.prepared() as (f, owner, package, request):
            api = self.case.api
            api.adopt_root(vars(owner), **request)
            args = {key: value for key, value in request.items() if key not in {
                "journal_limits", "expected_journal_limits_sha256", "expected_adoption_sha256"}}
            before = copy.deepcopy(request["memo"])
            write = owner.atomic_write

            def interrupted(path, *pos, **kw):
                result = write(path, *pos, **kw)
                if path == owner.MEMO_PATH:
                    raise OSError("controlled durable binding interruption")
                return result

            with mock.patch.object(owner, "atomic_write", side_effect=interrupted):
                with self.assertRaisesRegex(OSError, "controlled durable binding interruption"):
                    api.stage_live_binding(vars(owner), **args)
            self.assertEqual(args["memo"], before)
            args["memo"] = owner.load_memo()
            with mock.patch.object(owner, "atomic_write", side_effect=AssertionError("retry wrote")), \
                    mock.patch.object(api.transaction.checkpoint, "capture_root_delivery", side_effect=AssertionError("recollected")):
                self.assertFalse(api.stage_live_binding(vars(owner), **args))
            marker = owner._controller_source_live_binding_marker(args["memo"])
            self.assertEqual(marker["source_batch_sha256"], package["manifest"]["source_batch_sha256"])
            self.assertEqual(marker["status"], "prepared-not-published")
            self.assertEqual(args["memo"]["live_loop_committed"], before["live_loop_committed"])
            self.assertNotIn("ready", args["memo"])
            # A self-hashed replacement is not the actual prepared transition.
            altered = copy.deepcopy(args["memo"])
            changed = altered["controller_source_live_pending"]
            changed["transition_sha256"] = "0" * 64
            changed["marker_sha256"] = api.transaction.live._sha({k: v for k, v in changed.items() if k != "marker_sha256"})
            owner.atomic_write(owner.MEMO_PATH, owner._memo_text(altered), mode=0o600)
            with self.assertRaises(ValueError):
                api.stage_live_binding(vars(owner), **{**args, "memo": altered})
