"""Status effects from actual compact capture and durable live binding."""

import copy
import unittest

import siacontrollerstatus as status
from tests import test_checkpoint_adoption as fixtures


class CheckpointStatus(unittest.TestCase):
    def test_real_compact_status_projection_and_legacy_separation(self):
        self.assertTrue(callable(getattr(status, "prepare_checkpoint", None)), "missing compact status projection")
        case = fixtures.CheckpointAdoption(methodName="runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        with case.prepared() as (f, owner, package, request):
            api = case.api
            api.adopt_root(vars(owner), **request)
            args = {k: v for k, v in request.items() if k not in {
                "journal_limits", "expected_journal_limits_sha256", "expected_adoption_sha256"}}
            api.stage_live_binding(vars(owner), **args)
            view = api.read_pending(vars(owner), **{k: v for k, v in args.items() if k != "seq"})
            artifacts = view["package"]["artifacts"]
            batch, transition = artifacts["capture"], artifacts["transition"]
            inputs = dict(admitted_status=f.status, batch=batch, expected_batch_sha256=batch["batch_sha256"],
                source_live_pending=args["memo"]["controller_source_live_pending"], candidate=artifacts["candidate"],
                transition=transition, expected_transition_sha256=transition["transition_sha256"], started_at=f.status["ts"])
            before = copy.deepcopy(args["memo"])
            result = status.prepare_checkpoint(vars(owner), **inputs)
            self.assertEqual(result["workspace"], transition["state"]["workspace"]["slots"])
            self.assertEqual(result["history"][:-1], f.status["history"])
            self.assertEqual(result["history"][-1][0], f.status["ts"])
            self.assertEqual(args["memo"], before)
            self.assertEqual(owner.load_memo(), before)
            with self.assertRaises(ValueError):
                status.prepare(vars(owner), **inputs)
            altered = copy.deepcopy(batch)
            altered["intake_projection"]["associations"] = []
            altered["batch_sha256"] = api.source.native_sha(vars(owner), {k: v for k, v in altered.items() if k != "batch_sha256"})
            with self.assertRaises(ValueError):
                status.prepare_checkpoint(vars(owner), **{**inputs, "batch": altered, "expected_batch_sha256": altered["batch_sha256"]})
