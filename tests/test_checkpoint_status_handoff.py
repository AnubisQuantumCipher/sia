"""Actual durable compact pulse-status handoff and interrupted retry."""

import copy
import unittest
from unittest import mock
from tests import test_checkpoint_adoption as fixtures


class CheckpointStatusHandoff(unittest.TestCase):
    def test_actual_handoff_reload_retry_and_history_binding(self):
        self.exercise(interrupt=True)

    def test_normal_fenced_handoff_and_retry(self):
        self.exercise(interrupt=False)

    def exercise(self, *, interrupt):
        case = fixtures.CheckpointAdoption(methodName="runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        api = case.api
        self.assertTrue(callable(getattr(api, "stage_status_effects", None)), "missing compact status handoff")
        with case.prepared(fenced=not interrupt) as (f, owner, package, request):
            api.adopt_root(vars(owner), **request)
            args = {k: v for k, v in request.items() if k not in {
                "journal_limits", "expected_journal_limits_sha256", "expected_adoption_sha256"}}
            api.stage_live_binding(vars(owner), **args)
            args["started_at"] = f.status["ts"]
            before = copy.deepcopy(args["memo"])
            write = owner.atomic_write

            def interrupted(path, *pos, **kw):
                result = write(path, *pos, **kw)
                if path == owner.MEMO_PATH:
                    raise OSError("controlled durable status interruption")
                return result

            if interrupt:
                with mock.patch.object(owner, "atomic_write", side_effect=interrupted):
                    with self.assertRaisesRegex(OSError, "controlled durable status interruption"):
                        api.stage_status_effects(vars(owner), **args)
                self.assertEqual(args["memo"], before)
            else:
                self.assertTrue(api.stage_status_effects(vars(owner), **args))
                self.assertEqual(args["memo"], owner.load_memo())
                self.assertEqual(api.source._notification_marker(vars(owner), args["memo"]),
                                 api.source._notification_marker(vars(owner), before))
            args["memo"] = owner.load_memo()
            with mock.patch.object(owner, "atomic_write", side_effect=AssertionError("retry wrote")):
                self.assertFalse(api.stage_status_effects(vars(owner), **args))
            handoff = owner._pending_pulse_status_effects(args["memo"])
            self.assertEqual(handoff["publication_id"], before["controller_source_live_pending"]["publication_id"])
            self.assertEqual(args["memo"]["pulse_history"][:-1], f.status["history"])
            self.assertEqual(args["memo"]["live_loop_committed"], before["live_loop_committed"])
            altered = copy.deepcopy(args["memo"])
            altered["pulse_history"] = [altered["pulse_history"][-1]]
            owner.atomic_write(owner.MEMO_PATH, owner._memo_text(altered), mode=0o600)
            with self.assertRaises(ValueError):
                api.stage_status_effects(vars(owner), **{**args, "memo": altered})
