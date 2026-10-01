"""Bootstrap authority controls for the first controller-source capture.

A stable legacy live-loop receipt is opaque context for the later
source-to-live publisher.  It is not controller-source ancestry and does not
prevent the first empty-history source capture.  Unresolved publication debt
and any prior controller-source authority remain fail-closed here.

Root owns execution of this composed fixture and keeps it sequential.  No
host source, runtime service, model, database, publication, or cursor
acknowledgment is used by this module.
"""

import contextlib
import copy
import functools
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_source_capture as capture_tests


UNRESOLVED_AUTHORITY_KEYS = (
    "live_loop_pending",
    "pulse_publication",
    "source_replay_pending",
    "dream_publication",
    "consolidation_pending",
    "controller_source_pending",
    "controller_source_committed",
)


class ControllerSourceBootstrap(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        case = capture_tests.ControllerSourceCapture(methodName="runTest")
        try:
            case.setUp()
            yield case
        finally:
            case.doCleanups()

    @staticmethod
    def persist_memo(case, value):
        case.memo.clear()
        case.memo.update(copy.deepcopy(value))
        path = Path(case.lib.MEMO_PATH)
        path.write_bytes(capture_tests.canonical(case.memo))
        path.chmod(0o600)

    @contextlib.contextmanager
    def no_collector_or_plan(self, case):
        original_native = case.lib.sense_aegis
        original_custom = case.lib.sense_custom

        @functools.wraps(original_native)
        def native(*_args, **_kwargs):
            raise AssertionError(
                "unresolved bootstrap authority reached native acquisition")

        @functools.wraps(original_custom)
        def custom(*_args, **_kwargs):
            raise AssertionError(
                "unresolved bootstrap authority reached custom acquisition")

        with mock.patch.object(case.lib, "sense_aegis", native), \
                mock.patch.object(case.lib, "sense_custom", custom), \
                mock.patch.object(case.lib, "SENSES", [native, custom]), \
                mock.patch.object(
                    case.lib, "_prepare_event_page_plan",
                    side_effect=AssertionError(
                        "unresolved bootstrap authority reached planning")):
            yield

    def test_stable_legacy_live_receipt_permits_opaque_initial_source_capture(self):
        with self.fixture() as case:
            opaque_identity = "opaque-legacy-live-receipt-not-source-ancestry"
            memo = copy.deepcopy(case.memo)
            memo["live_loop_committed"] = {
                "opaque_identity": opaque_identity,
            }
            self.persist_memo(case, memo)
            before = case.inert_before()

            batch = case.capture()

            case.assert_batch(batch)
            self.assertEqual(batch["epoch"]["history"]["entries"], [])
            self.assertIsNone(batch["epoch"]["predecessor"])
            self.assertNotIn(
                opaque_identity.encode("ascii"), capture_tests.canonical(batch))
            self.assertEqual(case.memo, memo)
            case.assert_inert(before)

    def test_stable_legacy_live_receipt_survives_inert_stage_and_pending_read(self):
        with self.fixture() as case:
            live_receipt = {
                "opaque_identity": "stable-live-context-for-later-validation",
            }
            memo = copy.deepcopy(case.memo)
            memo["live_loop_committed"] = copy.deepcopy(live_receipt)
            self.persist_memo(case, memo)
            batch = case.capture()
            cursor_before = case.cursors_path.read_bytes()
            corpus_before = case.pages.snapshot()

            self.assertIsNone(case.lib._stage_controller_source_batch(
                memo=case.memo, batch=batch,
                expected_batch_sha256=batch["batch_sha256"]))
            view = case.lib._read_pending_controller_source_batch(
                memo=case.memo)

            self.assertEqual(case.memo["live_loop_committed"], live_receipt)
            self.assertIn("controller_source_pending", case.memo)
            self.assertEqual(view["status"], "pending")
            self.assertEqual(
                capture_tests.canonical(view["batch"]),
                capture_tests.canonical(batch))
            self.assertEqual(case.cursors_path.read_bytes(), cursor_before)
            self.assertEqual(case.pages.snapshot(), corpus_before)

    def test_every_unresolved_authority_key_refuses_even_when_present_null(self):
        for key in UNRESOLVED_AUTHORITY_KEYS:
            for value in (None, {"opaque_unresolved": key}):
                with self.subTest(key=key, value=value), self.fixture() as case:
                    memo = copy.deepcopy(case.memo)
                    memo[key] = copy.deepcopy(value)
                    self.persist_memo(case, memo)
                    before = case.inert_before()

                    with self.no_collector_or_plan(case):
                        error = case.assert_named_refusal(
                            case.capture, phase="admit")

                    self.assertEqual(
                        error.reason, "unbound-prior-source-history")
                    self.assertEqual(case.memo, memo)
                    case.assert_inert(before)


if __name__ == "__main__":
    unittest.main()
