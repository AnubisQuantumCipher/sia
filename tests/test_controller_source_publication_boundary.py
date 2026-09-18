"""Source-publication boundary controls.

These tests compose the actual capture fixture without inheriting its test
roster. Parent replacement is an explicit injected filesystem mutation, not
a claim that an ordinary collector performed it.
"""

import contextlib
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_source_capture as capture_tests
from tests import test_event_page_plan as page_tests


class ControllerSourcePublicationBoundary(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self, *, separate_batch_parent=False):
        case = capture_tests.ControllerSourceCapture(methodName="runTest")
        try:
            case.setUp()
            if separate_batch_parent:
                case.batch_path = case.root / "separate-batch-parent/controller-source-batch.json"
                case.batch_path.parent.mkdir(mode=0o700)
                case.stack.enter_context(mock.patch.object(
                    case.lib, "CONTROLLER_SOURCE_BATCH_PATH", str(case.batch_path)))
            batch = case.capture()
            case.assert_batch(batch)
            yield case, batch
        finally:
            case.doCleanups()

    @staticmethod
    def stage(case, batch):
        return case.lib._stage_controller_source_batch(
            memo=case.memo, batch=batch, expected_batch_sha256=batch["batch_sha256"])

    def test_absent_pending_key_permits_absence_then_exact_stage(self):
        with self.fixture() as (case, batch):
            self.assertNotIn("controller_source_pending", case.memo)
            self.assertFalse(case.batch_path.exists())
            before = case.inert_before()
            view = case.lib._read_pending_controller_source_batch(memo=case.memo)
            self.assertEqual(view["status"], "absent")
            self.assertIsNone(view["batch"])
            self.assertIsNone(view["receipt"])
            case.assert_inert(before)
            self.assertIsNone(self.stage(case, batch))
            view = case.lib._read_pending_controller_source_batch(memo=case.memo)
            self.assertEqual(view["status"], "pending")
            self.assertEqual(capture_tests.canonical(view["batch"]), capture_tests.canonical(batch))

    def test_present_null_pending_marker_is_not_absence_or_permission_to_stage(self):
        for operation in ("read", "stage"):
            with self.subTest(operation=operation), self.fixture() as (case, batch):
                case.memo["controller_source_pending"] = None
                memo_path = Path(case.lib.MEMO_PATH)
                memo_path.write_bytes(capture_tests.canonical(case.memo))
                self.assertEqual(memo_path.read_bytes(), capture_tests.canonical(case.memo))
                self.assertFalse(case.batch_path.exists())
                before = case.inert_before()

                def forbidden(*_args, **_kwargs):
                    raise AssertionError("null pending pointer reached source publication")

                with mock.patch.object(case.lib, "siaqueue", page_tests._ModuleShim(
                        case.lib.siaqueue, fixed_atomic_publish=forbidden)), \
                        mock.patch.object(case.lib, "atomic_write", side_effect=forbidden):
                    callback = (lambda: case.lib._read_pending_controller_source_batch(memo=case.memo)) \
                        if operation == "read" else (lambda: self.stage(case, batch))
                    case.assert_named_refusal(callback, phase="stage")
                case.assert_inert(before)

    def test_own_batch_write_cannot_adopt_a_replaced_separate_parent(self):
        for replace_parent in (False, True):
            with self.subTest(replace_parent=replace_parent), \
                    self.fixture(separate_batch_parent=True) as (case, batch):
                batch_path = case.batch_path
                memo_path = Path(case.lib.MEMO_PATH)
                self.assertNotEqual(batch_path.parent, memo_path.parent)
                parent_before = page_tests.generation(batch_path.parent.stat())
                memo_before = memo_path.read_bytes()
                cursor_before = case.cursors_path.read_bytes()
                corpus_before = case.pages.snapshot()
                original_publish = case.lib.siaqueue.fixed_atomic_publish
                retained_parent = case.root / "retained-original-batch-parent"
                reached = []

                def publish(path, raw, **kwargs):
                    result = original_publish(path, raw, **kwargs)
                    if str(path) == str(batch_path) and not reached:
                        reached.append(True)
                        self.assertEqual(batch_path.read_bytes(), capture_tests.canonical(batch))
                        if replace_parent:
                            batch_path.parent.rename(retained_parent)
                            batch_path.parent.mkdir(mode=0o700)
                            batch_path.write_bytes((retained_parent / batch_path.name).read_bytes())
                            batch_path.chmod(0o600)
                            self.assertNotEqual(page_tests.generation(batch_path.parent.stat()), parent_before)
                    return result

                with mock.patch.object(case.lib, "siaqueue", page_tests._ModuleShim(
                        case.lib.siaqueue, fixed_atomic_publish=publish)):
                    if replace_parent:
                        case.assert_named_refusal(lambda: self.stage(case, batch), phase="stage")
                    else:
                        self.assertIsNone(self.stage(case, batch))
                self.assertTrue(reached, "actual fixed-slot publication was not exercised")
                self.assertEqual(case.cursors_path.read_bytes(), cursor_before)
                self.assertEqual(case.pages.snapshot(), corpus_before)
                if replace_parent:
                    self.assertEqual(memo_path.read_bytes(), memo_before)
                    self.assertNotIn("controller_source_pending", case.memo)
                    self.assertEqual((retained_parent / batch_path.name).read_bytes(),
                                     capture_tests.canonical(batch))
                else:
                    self.assertEqual(case.lib._read_pending_controller_source_batch(
                        memo=case.memo)["status"], "pending")

