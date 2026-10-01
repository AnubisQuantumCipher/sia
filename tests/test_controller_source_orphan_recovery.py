"""Restart adoption for a durably retained source batch with no memo receipt."""

import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_source_capture as capture_tests
from tests import test_controller_source_publication as publication_tests


class ControllerSourceOrphanRecovery(unittest.TestCase):
    def setUp(self):
        self.fixture = publication_tests.ControllerSourcePublication(
            methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.lib = self.fixture.lib

    def recover(self):
        value = getattr(
            self.lib, "_recover_orphan_controller_source_batch", None)
        self.assertTrue(callable(value),
                        "missing restart-safe source orphan recovery API")
        return value(memo=self.fixture.memo)

    def make_orphan(self):
        original_write = self.lib.atomic_write

        def fail_memo(path, data, **kwargs):
            if str(path) == str(self.fixture.memo_path):
                self.assertEqual(
                    self.fixture.path.read_bytes(),
                    capture_tests.canonical(self.fixture.batch))
                raise OSError("injected crash before source memo receipt")
            return original_write(path, data, **kwargs)

        with mock.patch.object(
                self.lib, "atomic_write", side_effect=fail_memo):
            with self.assertRaises((OSError, ValueError, RuntimeError)):
                self.fixture.stage()
        self.assertNotIn("controller_source_pending", self.fixture.memo)
        self.assertTrue(self.fixture.path.is_file())

    def test_absence_is_write_free_and_returns_false(self):
        before = self.fixture.before()
        with mock.patch.object(
                self.lib, "atomic_write",
                side_effect=AssertionError("absent recovery wrote state")):
            self.assertIs(self.recover(), False)
        self.assertEqual(self.fixture.before(), before)

    def test_restart_recovers_exact_batch_without_collecting_or_republishing(self):
        self.make_orphan()
        batch_before = self.fixture.path.read_bytes()
        generation_before = self.fixture.path.stat()
        cursor_before = Path(self.lib.CURSORS_PATH).read_bytes()
        corpus_before = self.fixture.fixture.pages.snapshot()
        original_write = self.lib.atomic_write
        memo_writes = []

        def write(path, data, **kwargs):
            self.assertEqual(str(path), str(self.fixture.memo_path))
            memo_writes.append(json.loads(data))
            return original_write(path, data, **kwargs)

        with mock.patch.object(
                self.lib, "_capture_controller_source_batch",
                side_effect=AssertionError("orphan recovery recollected")), \
                mock.patch.object(
                    self.lib, "_stage_controller_source_batch",
                    side_effect=AssertionError("orphan recovery republished")), \
                mock.patch.object(
                    self.lib, "atomic_write", side_effect=write):
            self.assertIs(self.recover(), True)

        self.assertEqual(len(memo_writes), 1)
        self.assertEqual(memo_writes[0], self.fixture.memo)
        self.assertIn("controller_source_pending", self.fixture.memo)
        after = self.fixture.path.stat()
        self.assertEqual(
            (after.st_dev, after.st_ino),
            (generation_before.st_dev, generation_before.st_ino))
        self.assertEqual(self.fixture.path.read_bytes(), batch_before)
        self.assertEqual(Path(self.lib.CURSORS_PATH).read_bytes(), cursor_before)
        self.assertEqual(self.fixture.fixture.pages.snapshot(), corpus_before)
        self.fixture.assert_view(self.fixture.view(), "pending")

        durable_before = self.fixture.memo_path.read_bytes()
        with mock.patch.object(
                self.lib, "atomic_write",
                side_effect=AssertionError("settled recovery rewrote memo")):
            self.assertIs(self.recover(), False)
        self.assertEqual(self.fixture.memo_path.read_bytes(), durable_before)

    def test_malformed_or_downstream_orphan_authority_refuses_without_writes(self):
        for mode in ("malformed", "downstream"):
            with self.subTest(mode=mode):
                other = publication_tests.ControllerSourcePublication(
                    methodName="runTest")
                other.setUp()
                self.addCleanup(other.doCleanups)
                self.fixture = other
                self.lib = other.lib
                self.make_orphan()
                if mode == "malformed":
                    raw = self.fixture.path.read_bytes()
                    self.fixture.path.write_bytes(raw[:-1])
                else:
                    self.fixture.memo[
                        "controller_source_live_pending"] = {
                            "unbound": True,
                        }
                    self.fixture.memo_path.write_bytes(
                        capture_tests.canonical(self.fixture.memo))
                before = self.fixture.before()
                with mock.patch.object(
                        self.lib, "atomic_write",
                        side_effect=AssertionError(
                            "invalid orphan recovery wrote memo")):
                    with self.assertRaises((OSError, ValueError, RuntimeError)):
                        self.recover()
                self.assertEqual(self.fixture.before(), before)


if __name__ == "__main__":
    unittest.main()
