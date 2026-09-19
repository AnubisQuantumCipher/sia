"""Source-root checkpoint seeding against acknowledged private fixtures."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import siahistoryroot as roots
import siaeventcheckpoint as checkpoints
from tests import test_controller_source_idle as fixtures
from tests.test_history_block import digest


class HistoryCheckpointSeed(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ControllerSourceIdle(methodName="runTest")

    def test_seed_replays_root_and_preserves_acknowledged_intake(self):
        with self.fixture.completed() as (case, batch, committed, status, generation), \
                tempfile.TemporaryDirectory(prefix="sia-checkpoint-seed-") as directory:
            root = roots.prepare(vars(case.lib), memo=case.live.memo, admitted_status=status, directory=directory)
            before = copy.deepcopy(case.live.memo)
            seed = roots.prepare_checkpoint(vars(case.lib), memo=case.live.memo, admitted_status=status,
                                             directory=directory, expected_root_sha256=root["root_sha256"])
            self.assertEqual(seed["status"], "seed-retained-not-activated")
            self.assertEqual(seed["root_sha256"], root["root_sha256"])
            self.assertEqual(seed["committed"], committed)
            checkpoint = json.loads(Path(directory, "checkpoint-" + seed["checkpoint_sha256"] + ".json").read_bytes())
            self.assertEqual(checkpoint["intake"], batch["intake_projection"]["intake"])
            self.assertEqual(digest(checkpoint), seed["checkpoint_sha256"])
            self.assertEqual(json.loads(Path(directory, "seed-" + digest(seed) + ".json").read_bytes()), seed)
            self.assertEqual(case.live.memo, before)
            self.assertEqual(roots.prepare_checkpoint(vars(case.lib), memo=case.live.memo, admitted_status=status,
                                                       directory=directory, expected_root_sha256=root["root_sha256"]), seed)

    def test_wrong_root_pin_does_not_write_checkpoint(self):
        with self.fixture.completed() as (case, batch, committed, status, generation), \
                tempfile.TemporaryDirectory(prefix="sia-checkpoint-seed-") as directory:
            roots.prepare(vars(case.lib), memo=case.live.memo, admitted_status=status, directory=directory)
            with self.assertRaises(ValueError):
                roots.prepare_checkpoint(vars(case.lib), memo=case.live.memo, admitted_status=status,
                                         directory=directory, expected_root_sha256="a" * 64)
            self.assertEqual(list(Path(directory).glob("checkpoint-*.json")), [])

    def test_changed_source_after_checkpoint_write_refuses_seed_result(self):
        with self.fixture.completed() as (case, batch, committed, status, generation), \
                tempfile.TemporaryDirectory(prefix="sia-checkpoint-seed-") as directory:
            root = roots.prepare(vars(case.lib), memo=case.live.memo, admitted_status=status, directory=directory)
            reached = []

            def changing(name):
                if name == "target-published" and list(Path(directory).glob("checkpoint-*.json")):
                    reached.append(name)
                    case.archive_path().write_bytes(b"{}")

            with mock.patch.object(roots.store.queue, "_publish_boundary", side_effect=changing):
                with self.assertRaises(ValueError):
                    roots.prepare_checkpoint(vars(case.lib), memo=case.live.memo, admitted_status=status,
                                             directory=directory, expected_root_sha256=root["root_sha256"])
            self.assertTrue(reached)

    def test_changed_bootstrap_intake_refuses_before_checkpoint_retention(self):
        with self.fixture.completed() as (case, batch, committed, status, generation), \
                tempfile.TemporaryDirectory(prefix="sia-checkpoint-seed-") as directory:
            root = roots.prepare(vars(case.lib), memo=case.live.memo, admitted_status=status, directory=directory)
            original = checkpoints.bootstrap_incremental

            def altered(*args, **kwargs):
                result = original(*args, **kwargs)
                result["intake"]["observations"].clear()
                return result

            with mock.patch.object(checkpoints, "bootstrap_incremental", side_effect=altered):
                with self.assertRaises(ValueError) as caught:
                    roots.prepare_checkpoint(vars(case.lib), memo=case.live.memo, admitted_status=status,
                                             directory=directory, expected_root_sha256=root["root_sha256"])
            self.assertIn("seed-intake-fidelity", str(caught.exception))
            self.assertEqual(list(Path(directory).glob("checkpoint-*.json")), [])
