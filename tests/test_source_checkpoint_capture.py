"""Actual private collectors under acknowledged root-bound checkpoint capture."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import siahistoryroot as roots
import siasourcecheckpoint as api
from tests import test_controller_source_idle as fixtures
from tests import test_controller_source_rollover_storage as clocks
from tests.test_history_block import digest


class SourceCheckpointCapture(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ControllerSourceIdle(methodName="runTest")
        self.fixture.setUp()

    def capture(self, case, status, directory, root):
        # The composed legacy fixture uses separate isolated modules for
        # collectors and publication. Supply the real publication reader and
        # its paths alongside the real collector owner; no authority is mocked.
        owner = {**vars(case.lib), **vars(case.source.lib)}
        for name in ("CONTROLLER_SOURCE_ARCHIVE_DIR", "CONTROLLER_SOURCE_EFFECTS_ARCHIVE_DIR",
                     "STATUS_PATH", "GRAPH_PATH", "LIVE_CANDIDATE_PATH", "LIVE_STATE_PATH",
                     "_require_status_admission_unchanged", "_read_committed_live_generation",
                     "_ready_receipt"):
            owner[name] = getattr(case.lib, name)
        return api.capture_root(
            owner, memo=case.live.memo, admitted_status=status,
            directory=directory, expected_root_sha256=root["root_sha256"],
            observed_at=clocks.SUCCESSOR_OBSERVED_AT)

    def test_actual_collectors_capture_compact_epoch_without_publication(self):
        with self.fixture.completed() as (case, prior, committed, status, generation), \
                tempfile.TemporaryDirectory(prefix="sia-checkpoint-capture-") as directory:
            root = roots.prepare(vars(case.lib), memo=case.live.memo, admitted_status=status, directory=directory)
            before = copy.deepcopy(case.live.memo)
            cursor_before = case.source.cursors_path.read_bytes()
            with self.fixture.source_owner(case), case.source.capture_boundary(), case.source.observe_returns():
                captured = self.capture(case, status, directory, root)
            self.assertEqual(captured["schema"], "sia-controller-source-checkpoint-capture-v1")
            self.assertEqual(captured["status"], "captured-not-published")
            self.assertEqual([row[0] for row in case.source.calls],
                             [row["source_id"] for row in captured["epoch"]["source_catalog"]["sources"]])
            self.assertNotIn("history", captured["epoch"])
            self.assertEqual(captured["parent_checkpoint"]["intake"], prior["intake_projection"]["intake"])
            self.assertEqual(captured["epoch"]["predecessor"], committed)
            self.assertEqual(case.live.memo, before)
            self.assertEqual(case.source.cursors_path.read_bytes(), cursor_before)
            api.validate_capture(vars(case.source.lib), captured, captured["batch_sha256"])
            with self.assertRaises(ValueError):
                api.source.validate_batch(vars(case.source.lib), captured, captured["batch_sha256"])

    def test_wrong_root_refuses_before_collectors(self):
        with self.fixture.completed() as (case, prior, committed, status, generation), \
                tempfile.TemporaryDirectory(prefix="sia-checkpoint-capture-") as directory:
            with self.fixture.source_owner(case), \
                    mock.patch.object(api.source, "_collect", side_effect=AssertionError("unbound collection")):
                with self.assertRaises((ValueError, OSError)):
                    self.capture(case, status, directory, {"root_sha256": "a" * 64})

    def test_new_actual_custom_event_matches_full_history_replay(self):
        with self.fixture.completed() as (case, prior, committed, status, generation), \
                tempfile.TemporaryDirectory(prefix="sia-checkpoint-capture-") as directory:
            root = roots.prepare(vars(case.lib), memo=case.live.memo, admitted_status=status, directory=directory)
            path = Path(case.source.custom_entries[0]["path"])
            path.write_bytes(path.read_bytes() + b"new checkpoint capture event\n")
            with self.fixture.source_owner(case), case.source.capture_boundary(), case.source.observe_returns():
                captured = self.capture(case, status, directory, root)
            self.assertTrue(any(run["events"] for run in captured["source_returns"]["runs"]))
            self.assertIsNotNone(captured["event_closure"])
            epoch = copy.deepcopy(prior["epoch"])
            epoch["history"]["entries"].append({
                "source_returns": prior["source_returns"],
                "expected_source_returns_sha256": prior["source_returns"]["returns_sha256"],
                "event_batches": api.source._validate_closure(
                    vars(case.source.lib), prior["event_closure"], prior["source_returns"])})
            expected = api.source._intake_projection(
                vars(case.source.lib), epoch, captured["source_returns"],
                captured["event_closure"], captured["observed_at"])
            projection = captured["intake_projection"]
            self.assertEqual(projection["checkpoint"]["intake"], expected["intake"])
            self.assertEqual(projection["checkpoint"]["source_non_claims"], expected["source_non_claims"])
            self.assertEqual(projection["associations"], [row for row in expected["associations"]
                if row["source_returns_sha256"] == captured["source_returns"]["returns_sha256"]])
            for field in ("refusal_intents", "intake_projection"):
                changed = copy.deepcopy(captured)
                if field == "refusal_intents":
                    changed[field].clear()
                else:
                    changed[field]["associations"].clear()
                changed["batch_sha256"] = digest({key: value for key, value in changed.items()
                                                  if key != "batch_sha256"})
                with self.subTest(field=field), self.assertRaises(ValueError):
                    api.validate_capture(vars(case.source.lib), changed, changed["batch_sha256"])

    def test_changed_bootstrap_intake_refuses_before_collectors(self):
        with self.fixture.completed() as (case, prior, committed, status, generation), \
                tempfile.TemporaryDirectory(prefix="sia-checkpoint-capture-") as directory:
            root = roots.prepare(vars(case.lib), memo=case.live.memo, admitted_status=status, directory=directory)
            original = api.checkpoints.bootstrap_incremental

            def changed(*args, **kwargs):
                result = original(*args, **kwargs)
                result["intake"]["observations"].clear()
                return result

            with self.fixture.source_owner(case), \
                    mock.patch.object(api.checkpoints, "bootstrap_incremental", side_effect=changed), \
                    mock.patch.object(api.source, "_collect", side_effect=AssertionError("unbound collection")):
                with self.assertRaises(ValueError) as caught:
                    self.capture(case, status, directory, root)
            self.assertIn("checkpoint-source-intake-fidelity", str(caught.exception))

    def test_root_changed_during_collection_refuses(self):
        with self.fixture.completed() as (case, prior, committed, status, generation), \
                tempfile.TemporaryDirectory(prefix="sia-checkpoint-capture-") as directory:
            root = roots.prepare(vars(case.lib), memo=case.live.memo, admitted_status=status, directory=directory)
            original = api.source._collect
            reached = []

            def changed(*args, **kwargs):
                result = original(*args, **kwargs)
                Path(directory, "root-" + root["root_sha256"] + ".json").write_bytes(b"{}")
                reached.append(True)
                return result

            with self.fixture.source_owner(case), case.source.capture_boundary(), \
                    mock.patch.object(api.source, "_collect", side_effect=changed):
                with self.assertRaises((ValueError, OSError)):
                    self.capture(case, status, directory, root)
            self.assertTrue(reached)
