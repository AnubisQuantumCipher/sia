"""An existing epoch root still needs its parent-entry durability on retry.

The initial call is killed after the real descriptor-relative root mkdir,
before that call can fsync the root's parent. Retrying must preserve the root
inode and fsync that exact held parent before creating an epoch or publishing
birth. Fsyncing only the root itself does not satisfy this entry boundary.

The fixture is module-qualified so unittest does not discover its TestCase
again from this module.
No real delivery, consumer receipt, source truth or cognitive win is claimed.
"""

import contextlib
import copy
import os
from pathlib import Path
import stat
import unittest
from unittest import mock

from tests import test_controller_delivery_epoch as epoch_tests


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


class ControllerDeliveryEpochRootRetry(unittest.TestCase):
    def setUp(self):
        self.fixture = epoch_tests.ControllerDeliveryEpoch(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_retry_fsyncs_exact_root_parent_before_epoch_or_birth_without_replacing_root(self):
        with self.fixture.completed() as fixture, contextlib.ExitStack() as stack:
            case, retained, committed, status, generation, _root = fixture
            # Keep this parent distinct from the memo directory, so repairing
            # a memo-publication fsync cannot incidentally satisfy this test.
            root_parent = case.live.root / "delivery-root-parent"
            root_parent.mkdir(mode=0o700)
            root = root_parent / "epochs"
            stack.enter_context(mock.patch.object(case.lib, epoch_tests.ROOT_KEY, str(root)))
            _key, epoch, birth, _adoption, _records = self.fixture.paths(retained, root)
            root_parent_identity = _identity(os.lstat(root.parent))
            original_memo = copy.deepcopy(case.live.memo)
            original_images = case.images()
            self.assertFalse(root.exists())
            real_mkdir = os.mkdir
            real_fsync = os.fsync
            initial_events = []
            created_identity = []
            initial_boundary = mock.Mock()

            def die_after_real_root_mkdir(path, mode=0o777, *, dir_fd=None):
                is_root_creation = (
                    os.fspath(path) == root.name and type(dir_fd) is int
                    and _identity(os.fstat(dir_fd)) == root_parent_identity)
                result = real_mkdir(path, mode, dir_fd=dir_fd)
                if is_root_creation:
                    info = os.lstat(root)
                    self.assertTrue(stat.S_ISDIR(info.st_mode))
                    self.assertEqual(stat.S_IMODE(info.st_mode), 0o700)
                    created_identity.append(_identity(info))
                    initial_events.append("root-created")
                    raise epoch_tests._EpochDeath("after-real-root-mkdir-before-parent-fsync")
                return result

            def observe_initial_fsync(descriptor):
                if _identity(os.fstat(descriptor)) == root_parent_identity:
                    initial_events.append("root-parent-fsync")
                return real_fsync(descriptor)

            with self.fixture._local_os(
                    case, mkdir=die_after_real_root_mkdir, fsync=observe_initial_fsync), \
                    mock.patch.object(case.lib, epoch_tests.BOUNDARY_KEY, initial_boundary), \
                    self.fixture.no_new_work(case), self.assertRaises(epoch_tests._EpochDeath):
                self.fixture.prepare(case, retained, committed, status)

            self.assertEqual(initial_events[-1], "root-created")
            self.assertNotIn("root-parent-fsync", initial_events[initial_events.index("root-created"):])
            self.assertEqual(created_identity, [_identity(os.lstat(root))])
            self.assertEqual(list(root.iterdir()), [])
            self.assertFalse(epoch.exists())
            self.assertFalse(birth.exists())
            initial_boundary.assert_not_called()
            self.assertEqual(case.images(), original_images)
            self.assertEqual(case.live._read("MEMO_PATH"), original_memo)

            # A new process takes its memo from disk, not the interrupted call.
            durable = case.live._read("MEMO_PATH")
            case.live.memo.clear()
            case.live.memo.update(durable)
            retry_events = []
            real_publish = case.lib.siaqueue.fixed_atomic_publish

            def observe_retry_fsync(descriptor):
                if _identity(os.fstat(descriptor)) == root_parent_identity:
                    retry_events.append("root-parent-fsync")
                return real_fsync(descriptor)

            def observe_retry_mkdir(path, mode=0o777, *, dir_fd=None):
                if os.fspath(path) == root.name and type(dir_fd) is int \
                        and _identity(os.fstat(dir_fd)) == root_parent_identity:
                    retry_events.append("root-recreated")
                if os.fspath(path) == epoch.name and type(dir_fd) is int \
                        and _identity(os.fstat(dir_fd)) == created_identity[0]:
                    retry_events.append("epoch-mkdir")
                return real_mkdir(path, mode, dir_fd=dir_fd)

            def observe_retry_publish(path, data, **kwargs):
                if Path(path) == birth:
                    retry_events.append("birth-publication")
                return real_publish(path, data, **kwargs)

            def observe_retry_boundary(phase):
                self.assertIn(phase, epoch_tests.PHASES)
                retry_events.append("boundary:" + phase)

            with self.fixture._local_os(
                    case, mkdir=observe_retry_mkdir, fsync=observe_retry_fsync), \
                    mock.patch.object(case.lib.siaqueue, "fixed_atomic_publish",
                                      side_effect=observe_retry_publish), \
                    mock.patch.object(case.lib, epoch_tests.BOUNDARY_KEY, observe_retry_boundary), \
                    self.fixture.no_new_work(case):
                result = self.fixture.prepare(case, retained, committed, status)

            self.fixture.assert_adopted(case, retained, committed, generation, root, result)
            self.assertEqual(_identity(os.lstat(root)), created_identity[0])
            self.assertNotIn("root-recreated", retry_events)
            self.assertIn("root-parent-fsync", retry_events)
            self.assertIn("epoch-mkdir", retry_events)
            self.assertIn("birth-publication", retry_events)
            parent_fsync = retry_events.index("root-parent-fsync")
            self.assertLess(parent_fsync, retry_events.index("epoch-mkdir"), retry_events)
            self.assertLess(parent_fsync, retry_events.index("birth-publication"), retry_events)
            for phase in epoch_tests.PHASES:
                event = "boundary:" + phase
                self.assertIn(event, retry_events)
                self.assertLess(parent_fsync, retry_events.index(event), retry_events)


if __name__ == "__main__":
    unittest.main()
