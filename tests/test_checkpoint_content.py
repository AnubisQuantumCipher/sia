"""Actual additive pages from an adopted compact pulse, not fake receipts."""

import copy
import importlib
from pathlib import Path
import unittest
from unittest import mock
from tests import test_checkpoint_adoption as fixtures


class CheckpointContent(unittest.TestCase):
    def test_actual_pages_and_idempotent_retry_without_ack(self):
        self.exercise(fenced=False)

    def test_actual_derived_gist_addition_preserves_notification_fence(self):
        self.exercise(fenced=True)

    def exercise(self, *, fenced):
        api = importlib.import_module("siacheckpointcontent")
        case = fixtures.CheckpointAdoption(methodName="runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        with case.prepared(fenced=fenced) as (f, owner, package, request):
            adoption = case.api
            adoption.adopt_root(vars(owner), **request)
            args = {k: v for k, v in request.items() if k not in {
                "journal_limits", "expected_journal_limits_sha256", "expected_adoption_sha256"}}
            adoption.stage_live_binding(vars(owner), **args)
            adoption.stage_status_effects(vars(owner), **args, started_at=f.status["ts"])
            args.pop("seq")
            before = copy.deepcopy(args["memo"])
            with mock.patch.object(owner, "_acknowledge_controller_source_batch", side_effect=AssertionError("pages acknowledged")), \
                    mock.patch.object(owner, "_stage_live_generation", side_effect=AssertionError("pages staged live")):
                result = api.publish_pages(vars(owner), **args)
                self.assertEqual(api.publish_pages(vars(owner), **args), result)
            self.assertEqual(result["status"], "pages-published-not-indexed")
            self.assertTrue(result["target_versions"])
            if fenced:
                self.assertTrue(result["gist_publication"]["target_versions"])
            for target in result["target_versions"]:
                self.assertTrue((Path(owner.CORPUS) / (target["slug"] + ".md")).is_file())
            self.assertEqual(args["memo"], before)
            self.assertEqual(owner.load_memo(), before)
            # A fabricated return cannot stand in for the original publisher.
            publisher = "_publish_controller_source_gist_page_plan" if fenced else "_publish_event_page_batch_closure"
            with mock.patch.object(owner, publisher, return_value={}):
                with self.assertRaises(ValueError):
                    api.publish_pages(vars(owner), **args)
