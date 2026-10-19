"""SIGKILL cuts through real ACK file publication in disposable fixtures.

Unlike exception injection, child death does not run Python finally blocks.
Recovery reloads memo bytes after the child has been reaped. Source capture,
Git/index observations and unrelated services remain the existing controlled
fixture: this is not a resident restart, power-loss or hostile-user proof.
Only the root orchestrator runs this composed test module, sequentially.
"""

import copy
import multiprocessing
import os
import signal
import unittest
from unittest import mock

from tests import sia_test_home  # noqa: F401 -- isolate before runtime imports
from tests import test_controller_source_ack as ack_tests


def _die_at_boundary(case, selected):
    def boundary(phase):
        if phase == selected:
            os.kill(os.getpid(), signal.SIGKILL)

    with mock.patch.object(case.lib, ack_tests.BOUNDARY, side_effect=boundary):
        case.acknowledge()
    raise AssertionError("requested process-death boundary was not reached")


@unittest.skipUnless("fork" in multiprocessing.get_all_start_methods(),
                     "Linux fork process-death fixture required")
class AssuranceAckProcessDeath(unittest.TestCase):
    def fixture(self):
        case = ack_tests.ControllerSourceAcknowledgment(methodName="runTest")
        self.addCleanup(case.doCleanups)
        case.setUp()
        return case

    def kill_at(self, case, phase):
        child = multiprocessing.get_context("fork").Process(
            target=_die_at_boundary, args=(case, phase))
        child.start()
        try:
            child.join(timeout=30)
            if child.is_alive():
                child.kill()
                child.join(timeout=5)
                self.fail("ACK child exceeded deadline before " + phase)
            self.assertEqual(child.exitcode, -signal.SIGKILL)
        finally:
            if child.is_alive():
                child.kill()
                child.join(timeout=5)
            child.close()

    def reload_memo(self, case, phase):
        durable = case.lib.load_memo()
        case.live.memo.clear()
        case.live.memo.update(copy.deepcopy(durable))
        if phase == "memo-durable":
            self.assertEqual(durable, case.expected_final_memo())
        else:
            self.assertIn("controller_source_pending", durable)
            self.assertNotIn("ready", durable)
        return durable

    def complete_images(self, case):
        images = case.images()
        images["effects-archive"] = ack_tests._path_image(
            case.effects_archive_path())
        images["effects-archive-dir"] = ack_tests._path_image(
            case.effects_archive_dir)
        return images

    def assert_effectless_retry(self, case):
        completed = self.complete_images(case)
        self.assertIsNone(case.acknowledge())
        self.assertEqual(self.complete_images(case), completed)

    def test_core_prefixes_survive_process_death_and_retry_is_effectless(self):
        for phase in ack_tests.CORE_PHASES:
            with self.subTest(phase=phase):
                case = self.fixture()
                case.start_empty()
                self.kill_at(case, phase)
                self.reload_memo(case, phase)
                self.assertIsNone(case.acknowledge())
                case.assert_final()
                self.assert_effectless_retry(case)
                case.doCleanups()

    def test_journal_prefixes_survive_process_death(self):
        for phase in ack_tests.JOURNAL_PHASES:
            with self.subTest(phase=phase):
                case = self.fixture()
                case.start_journal()
                self.kill_at(case, phase)
                self.reload_memo(case, phase)
                self.assertIsNone(case.acknowledge())
                case.assert_final()
                self.assert_effectless_retry(case)
                case.doCleanups()

    def test_foreign_cursor_after_process_death_cannot_become_ready(self):
        case = self.fixture()
        case.start_empty()
        self.kill_at(case, "cursor-state-durable")
        self.reload_memo(case, "cursor-state-durable")
        case.source.cursors_path.write_bytes(b'{"foreign":true}\n')
        before = self.complete_images(case)
        with self.assertRaises(ack_tests.REFUSALS):
            case.acknowledge()
        self.assertEqual(self.complete_images(case), before)
        self.assertNotIn("ready", case.lib.load_memo())


if __name__ == "__main__":
    unittest.main()
