"""Root preparation from genuinely acknowledged private source fixtures."""

import copy
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests import test_controller_source_idle as idle_tests
from tests.test_history_block import digest


class HistoryRoot(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("siahistoryroot")
        self.fixture = idle_tests.ControllerSourceIdle(methodName="runTest")

    def test_completed_source_retains_replayable_root_without_changing_memo(self):
        with self.fixture.completed() as (case, batch, committed, status, generation), \
                tempfile.TemporaryDirectory(prefix="sia-history-root-") as directory:
            before = copy.deepcopy(case.live.memo)
            result = self.api.prepare(vars(case.lib), memo=case.live.memo,
                                      admitted_status=status, directory=directory)
            root = result["root"]
            self.assertEqual(root["committed"], committed)
            self.assertEqual(root["legacy_history_sha256"], batch["epoch"]["expected_history_sha256"])
            self.assertEqual(root["legacy_epoch_sha256"], batch["epoch_sha256"])
            self.assertEqual(root["status"], "root-retained-not-activated")
            self.assertEqual(case.live.memo, before)
            self.assertEqual(result["root_sha256"], digest(root))
            path = Path(directory, "root-" + result["root_sha256"] + ".json")
            self.assertEqual(path.read_bytes(), self.api.blocks._wire(root))
            self.assertEqual(self.api.prepare(vars(case.lib), memo=case.live.memo,
                                             admitted_status=status, directory=directory), result)

    def test_wrong_memo_authority_refuses_before_retention(self):
        with self.fixture.completed() as (case, batch, committed, status, generation), \
                tempfile.TemporaryDirectory(prefix="sia-history-root-") as directory:
            forged = copy.deepcopy(case.live.memo)
            forged["controller_source_committed"]["source_batch_sha256"] = "a" * 64
            with self.assertRaises(ValueError):
                self.api.prepare(vars(case.lib), memo=forged,
                                 admitted_status=status, directory=directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_post_retention_authority_change_prevents_result(self):
        with self.fixture.completed() as (case, batch, committed, status, generation), \
                tempfile.TemporaryDirectory(prefix="sia-history-root-") as directory:
            original = self.api.store.retain

            def changing(**kwargs):
                result = original(**kwargs)
                case.live.memo["controller_source_committed"]["source_batch_sha256"] = "a" * 64
                return result

            with mock.patch.object(self.api.store, "retain", side_effect=changing):
                with self.assertRaises(ValueError):
                    self.api.prepare(vars(case.lib), memo=case.live.memo,
                                     admitted_status=status, directory=directory)
            self.assertEqual(list(Path(directory).glob("root-*.json")), [])

    def test_archive_tamper_refuses_before_root_write(self):
        with self.fixture.completed() as (case, batch, committed, status, generation), \
                tempfile.TemporaryDirectory(prefix="sia-history-root-") as directory:
            case.archive_path().write_bytes(b"{}")
            with self.assertRaises(ValueError):
                self.api.prepare(vars(case.lib), memo=case.live.memo,
                                 admitted_status=status, directory=directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_archive_change_after_root_publication_prevents_activation_result(self):
        with self.fixture.completed() as (case, batch, committed, status, generation), \
                tempfile.TemporaryDirectory(prefix="sia-history-root-") as directory:
            reached = []

            def change(name):
                if name == "target-published" and list(Path(directory).glob("root-*.json")):
                    reached.append(name)
                    case.archive_path().write_bytes(b"{}")

            with mock.patch.object(self.api.store.queue, "_publish_boundary", side_effect=change):
                with self.assertRaises(ValueError):
                    self.api.prepare(vars(case.lib), memo=case.live.memo,
                                     admitted_status=status, directory=directory)
            self.assertTrue(reached)
            self.assertTrue(list(Path(directory).glob("root-*.json")))
