"""Controller-source debt at the live publication memo boundary.

This module composes the existing synthetic live-publication fixture without
inheriting its test roster.  The source receipt is opaque at this boundary:
these tests establish memo authority and preservation, not source-batch
capture, retained-batch validity, acknowledgment, or archive completion.

Root alone executes this module, sequentially.  No collector, resident model,
database, host runtime, source acknowledgment, or external publication is
used here.
"""

import contextlib
import copy
from pathlib import Path
import unittest
from unittest import mock

from tests import test_live_publication as publication_tests


def source_pending():
    """Return one closed, well-formed controller-source pending receipt."""
    return {
        "schema": "sia-controller-source-pending-v1",
        "epoch_id": "fixture-controller-epoch",
        "batch_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "epoch_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "batch_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        "batch_wire_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        "batch_bytes": 1,
        "parent_batch_sha256": None,
    }


class ControllerSourceLiveMemo(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        case = publication_tests.LivePublication(methodName="runTest")
        try:
            case.setUp()
            # Keep any later source-receipt admission confined to this
            # fixture.  The memo-only contract must never inspect the host's
            # fixed controller-source slot.
            source_path = case.root / "controller-source-batch.json"
            case.stack.enter_context(mock.patch.object(
                case.lib, "CONTROLLER_SOURCE_BATCH_PATH", str(source_path)))
            yield case
        finally:
            case.doCleanups()

    @staticmethod
    def persist(case, memo):
        case.memo.clear()
        case.memo.update(copy.deepcopy(memo))
        case._write(case.paths["MEMO_PATH"], case.memo)

    def assert_refused_before_write(self, case, callback, durable_before):
        with mock.patch.object(
                case.lib, "atomic_write",
                side_effect=AssertionError(
                    "controller-source memo refusal reached publication")):
            with self.assertRaises(RuntimeError) as caught:
                callback()
        self.assertTrue(getattr(caught.exception, "non_claims", None))
        self.assertEqual(
            Path(case.paths["MEMO_PATH"]).read_bytes(), durable_before)
        self.assertFalse(Path(case.paths["LIVE_CANDIDATE_PATH"]).exists())
        self.assertFalse(Path(case.paths["LIVE_STATE_PATH"]).exists())

    def test_controller_pending_presence_and_value_are_durable_live_authority(self):
        marker = source_pending()
        changed = copy.deepcopy(marker)
        changed["batch_sha256"] = (
            "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee")
        cases = (
            ({"controller_source_pending": marker}, {}),
            ({}, {"controller_source_pending": marker}),
            ({"controller_source_pending": marker},
             {"controller_source_pending": changed}),
            ({"controller_source_pending": None}, {}),
            ({}, {"controller_source_pending": None}),
        )
        for memory_patch, durable_patch in cases:
            with self.subTest(memory=memory_patch, durable=durable_patch), \
                    self.fixture() as case:
                durable = copy.deepcopy(case.memo)
                durable.update(copy.deepcopy(durable_patch))
                case._write(case.paths["MEMO_PATH"], durable)
                proposed = copy.deepcopy(case.memo)
                proposed.update(copy.deepcopy(memory_patch))
                case.memo.clear()
                case.memo.update(proposed)
                before = Path(case.paths["MEMO_PATH"]).read_bytes()

                self.assert_refused_before_write(
                    case, case._stage, before)

    def test_matched_present_null_controller_pending_refuses_before_write(self):
        with self.fixture() as case:
            memo = copy.deepcopy(case.memo)
            memo["controller_source_pending"] = None
            self.persist(case, memo)
            before = Path(case.paths["MEMO_PATH"]).read_bytes()

            self.assert_refused_before_write(case, case._stage, before)

    def test_valid_controller_pending_survives_final_memo_and_withholds_ready(self):
        with self.fixture() as case:
            marker = source_pending()
            memo = copy.deepcopy(case.memo)
            memo["controller_source_pending"] = copy.deepcopy(marker)
            self.persist(case, memo)

            case._stage()
            staged = case._read("MEMO_PATH")
            self.assertEqual(staged["controller_source_pending"], marker)
            self.assertNotIn("ready", staged)
            generation = case._publish()
            final = case._read("MEMO_PATH")

            self.assertEqual(final["controller_source_pending"], marker)
            self.assertEqual(case.memo["controller_source_pending"], marker)
            self.assertNotIn("ready", final)
            self.assertNotIn("ready", case.memo)
            self.assertNotIn("live_loop_pending", final)
            self.assertEqual(
                final["live_loop_committed"]["generation_sha256"],
                generation["generation_sha256"])
            case._assert_view(case._view(), "available")

    def test_absent_controller_pending_keeps_existing_live_ready_behavior(self):
        with self.fixture() as case:
            self.assertNotIn("controller_source_pending", case.memo)
            case._stage()
            generation = case._publish()
            final = case._read("MEMO_PATH")
            candidate = case._read("LIVE_CANDIDATE_PATH")

            self.assertNotIn("controller_source_pending", final)
            self.assertEqual(final["ready"], {
                "v": 1,
                "completed_at": candidate["status"]["ts"],
                "kind": "pulse",
                "identity": generation["publication_id"],
            })
            view = case._view()
            case._assert_view(view, "available")
            self.assertEqual(view["generation"], generation)


if __name__ == "__main__":
    unittest.main()
