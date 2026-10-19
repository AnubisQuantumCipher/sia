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
from pathlib import Path
import signal
import unittest
from unittest import mock

from tests import sia_test_home  # noqa: F401 -- isolate before runtime imports
from tests import test_controller_source_ack as ack_tests


def _die_at_boundary(case, selected, queue_boundary=False):
    def boundary(phase):
        if phase == selected:
            os.kill(os.getpid(), signal.SIGKILL)

    target = case.lib.siaqueue if queue_boundary else case.lib
    name = "_publish_boundary" if queue_boundary else ack_tests.BOUNDARY
    with mock.patch.object(target, name, side_effect=boundary):
        case.acknowledge()
    raise AssertionError("requested process-death boundary was not reached")


def _die_inside_publication(case, path):
    queue = case.lib.siaqueue
    publish = queue.fixed_atomic_publish
    rename = queue._rename_noreplace

    def cut(phase):
        if phase == "target-published":
            os.kill(os.getpid(), signal.SIGKILL)

    def publishing(target, *args, **kwargs):
        if os.fspath(target) == os.fspath(path):
            with mock.patch.object(queue, "_publish_boundary", side_effect=cut):
                return publish(target, *args, **kwargs)
        return publish(target, *args, **kwargs)

    def moving(src_fd, src_name, dst_fd, dst_name):
        result = rename(src_fd, src_name, dst_fd, dst_name)
        if path == case.archive_path() and dst_name == path.name:
            os.kill(os.getpid(), signal.SIGKILL)
        return result

    with mock.patch.object(queue, "fixed_atomic_publish", side_effect=publishing), \
            mock.patch.object(queue, "_rename_noreplace", side_effect=moving):
        case.acknowledge()
    raise AssertionError("selected publication was not reached")


@unittest.skipUnless("fork" in multiprocessing.get_all_start_methods(),
                     "Linux fork process-death fixture required")
class AssuranceAckProcessDeath(unittest.TestCase):
    def fixture(self):
        case = ack_tests.ControllerSourceAcknowledgment(methodName="runTest")
        self.addCleanup(case.doCleanups)
        case.setUp()
        return case

    def kill_at(self, case, phase, *, queue_boundary=False, path=None):
        target = _die_at_boundary if path is None else _die_inside_publication
        args = (case, phase, queue_boundary) if path is None else (case, path)
        child = multiprocessing.get_context("fork").Process(
            target=target, args=args)
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

    def test_archive_recovery_syncs_directory_before_declaring_durable(self):
        case = self.fixture()
        case.start_empty()
        # The first fixed publication in ACK is the effects receipt archive.
        self.kill_at(case, "target-published", queue_boundary=True)
        self.reload_memo(case, "target-published")
        self.assertTrue(case.effects_archive_path().is_file())
        directory = os.stat(case.effects_archive_dir)
        expected = (directory.st_dev, directory.st_ino)
        synced = []
        real_fsync = os.fsync

        def fsync(fd):
            info = os.fstat(fd)
            real_fsync(fd)
            synced.append((info.st_dev, info.st_ino))

        def boundary(phase):
            if phase == "effects-receipt-archive-durable":
                self.assertIn(expected, synced,
                              "recovered archive declared durable without directory fsync")

        with mock.patch.object(os, "fsync", side_effect=fsync), \
                mock.patch.object(case.lib, ack_tests.BOUNDARY, side_effect=boundary):
            self.assertIsNone(case.acknowledge())
        case.assert_final()

    def recovery_case(self, kind):
        case = self.fixture()
        case.start_journal() if kind.startswith("journal") else case.start_empty()
        choices = {
            "source": (case.archive_path(), "archive-durable"),
            "effects": (case.effects_archive_path(), "effects-receipt-archive-durable"),
            "main": (case.source.cursors_path, "cursor-state-durable"),
            "journal-sys": (case.source_state / "journal-sys.cursor", "journal-sys-durable"),
            "journal-user": (case.source_state / "journal-user.cursor", "journal-user-durable"),
        }
        path, phase = choices[kind]
        self.kill_at(case, phase, path=path)
        self.reload_memo(case, "interrupted-publication")
        parents = [path.parent]
        if kind == "source":
            parents.append(Path(case.producer.source_path).parent)
        identities = [(os.stat(p).st_dev, os.stat(p).st_ino) for p in parents]
        return case, phase, identities

    def test_recovery_completes_each_interrupted_directory_sync(self):
        for kind in ("source", "main", "journal-sys", "journal-user"):
            with self.subTest(kind=kind):
                case, phase, expected = self.recovery_case(kind)
                synced = set()
                real = os.fsync

                def fsync(fd):
                    info = os.fstat(fd)
                    real(fd)
                    synced.add((info.st_dev, info.st_ino))

                def boundary(current):
                    if current == phase:
                        self.assertTrue(set(expected) <= synced,
                                        "missing recovered directory synchronization")
                    synced.clear()

                with mock.patch.object(os, "fsync", side_effect=fsync), \
                        mock.patch.object(case.lib, ack_tests.BOUNDARY, side_effect=boundary):
                    case.acknowledge()
                case.assert_final()
                self.assert_effectless_retry(case)
                case.doCleanups()

    def check_sync_failure(self, kind, parent_index):
        case, phase, expected = self.recovery_case(kind)
        predecessor = {
            "effects": None,
            "source": "effects-receipt-archive-durable",
            "main": "refusals-durable",
            "journal-sys": "refusals-durable",
            "journal-user": "journal-sys-durable",
        }[kind]
        real = os.fsync
        reached = []
        injected = []
        failure = OSError("injected directory synchronization failure")

        def fsync(fd):
            info = os.fstat(fd)
            armed = predecessor is None or reached and reached[-1] == predecessor
            if armed and (info.st_dev, info.st_ino) == expected[parent_index]:
                injected.append(expected[parent_index])
                raise failure
            return real(fd)

        with mock.patch.object(os, "fsync", side_effect=fsync), \
                mock.patch.object(case.lib, ack_tests.BOUNDARY, side_effect=reached.append):
            with self.assertRaises(OSError) as caught:
                case.acknowledge()
        self.assertIs(caught.exception, failure)
        self.assertEqual(injected, [expected[parent_index]])
        if predecessor is not None:
            self.assertEqual(reached[-1], predecessor)
        self.assertNotIn(phase, reached)
        durable = case.lib.load_memo()
        self.assertIn("controller_source_pending", durable)
        self.assertNotIn("ready", durable)
        case.doCleanups()

    def test_recovery_sync_failure_keeps_ack_pending(self):
        cases = (("effects", 0), ("source", 0), ("source", 1),
                 ("main", 0), ("journal-sys", 0), ("journal-user", 0))
        for kind, parent_index in cases:
            with self.subTest(kind=kind, parent_index=parent_index):
                self.check_sync_failure(kind, parent_index)

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
