"""Recovery cut: pending memo replaced, its parent not yet flushed.

The real controlled source capture and stage publish the WAL, flush its
directory, then enter the real atomic memo writer. A named target-published
interruption stops that memo writer before its destination-directory fsync.
Recovery receives only the real pending memo reloaded from that file.

For this cut, WAL directory durability is established by stage, not invented
by a recovery spy. Recovery must finish the memo-parent barrier without
rewriting either file and keep the established False return contract. A cut
before WAL directory fsync is a different orphan-without-pending scenario.

This initial-source fixture does not manufacture completed predecessor state,
relax notification-fence continuation, acknowledge sources, or authorize any
downstream operation. Exception injection is not an actual kernel crash or a
proof of filesystem power-loss behavior.
"""

import contextlib
import copy
import errno
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "bin"))

from tests import sia_test_home
from tests import test_controller_source_capture as capture_tests
from tests import test_controller_source_publication as publication_tests
from tests import test_controller_source_publication_boundary as boundary_tests
from tests import test_event_page_plan as page_tests

import siasourcebatch as source
import siasourcepublication as publication


class _MemoTargetPublished(KeyboardInterrupt):
    pass


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def _file_image(path):
    info = path.stat()
    return (_identity(info), info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, path.read_bytes())


def _descriptors():
    result = {}
    for leaf in os.listdir("/proc/self/fd"):
        descriptor = int(leaf)
        try:
            info = os.fstat(descriptor)
            target = os.readlink("/proc/self/fd/" + leaf)
        except OSError as exc:
            if exc.errno not in (errno.EBADF, errno.ENOENT):
                raise
            continue
        result[descriptor] = (_identity(info), target)
    return result


class SourcePendingMemoDurability(unittest.TestCase):
    @contextlib.contextmanager
    def local_os(self, lib, **overrides):
        # Cover the publication transaction, source descriptor helpers,
        # owning core and actual atomic publisher. The stdlib module and
        # the test's original native observers remain untouched.
        with contextlib.ExitStack() as stack:
            for module in (publication, source, lib, lib.siaqueue):
                stack.enter_context(mock.patch.object(
                    module, "os", page_tests._ModuleShim(module.os, **overrides)))
            yield

    @contextlib.contextmanager
    def crashed_pending(self):
        fixture = boundary_tests.ControllerSourcePublicationBoundary(methodName="runTest")
        with fixture.fixture(separate_batch_parent=True) as (case, batch):
            lib = case.lib
            memo_path = Path(lib.MEMO_PATH)
            wal_path = case.batch_path
            memo_parent = _identity(memo_path.parent.stat())
            wal_parent = _identity(wal_path.parent.stat())
            self.assertNotEqual(memo_parent, wal_parent)
            self.assertNotIn("controller_source_pending", case.memo)
            self.assertNotIn("controller_source_committed", case.memo)
            original_memo = copy.deepcopy(case.memo)
            events = []
            phase = {"name": "stage-wal", "wal_published": False}
            failure = _MemoTargetPublished("controlled memo target-publication cut")
            real_fsync = os.fsync
            real_atomic = lib.atomic_write
            real_boundary = lib.siaqueue._publish_boundary

            def observe_stage_fsync(descriptor):
                identity = _identity(os.fstat(descriptor))
                result = real_fsync(descriptor)
                # An earlier flush used to create a staging directory cannot
                # stand in for persisting the later WAL target entry.
                if identity == wal_parent and phase["wal_published"]:
                    events.append("stage-wal-parent-fsynced")
                if identity == memo_parent and "memo-target-published" in events:
                    events.append("stage-memo-parent-fsynced-after-target")
                return result

            def publication_boundary(name):
                if phase["name"] == "stage-wal":
                    if name == "target-published":
                        phase["wal_published"] = True
                        events.append("wal-target-published")
                    elif name == "target-directory-fsynced":
                        self.assertIn("stage-wal-parent-fsynced", events)
                        events.append("wal-directory-durable")
                elif name == "target-published":
                    self.assertIn("wal-directory-durable", events)
                    self.assertEqual(wal_path.read_bytes(), capture_tests.canonical(batch))
                    actual = lib.load_memo()
                    self.assertIn("controller_source_pending", actual)
                    self.assertEqual(actual["controller_source_pending"]["batch_sha256"],
                                     batch["batch_sha256"])
                    events.append("memo-target-published")
                    raise failure
                return real_boundary(name)

            def write_real_memo(path, data, **kwargs):
                self.assertEqual(str(path), str(memo_path))
                self.assertIn("wal-directory-durable", events)
                phase["name"] = "stage-memo"
                return real_atomic(path, data, **kwargs)

            # Open ordinary infrastructure before installing durability spies
            # and keep it entered through the retry. No owner reacquisition
            # may accidentally flush the memo parent and mask the recovery cut.
            with lib.brainstem_owner(), lib.corpus_owner():
                scope_fd = lib._CORPUS_OWNER_FD.get()
                scope_identity = _identity(os.fstat(scope_fd))
                with publication_tests.ControllerSourcePublication.inert(
                        SimpleNamespace(lib=lib)), \
                        self.local_os(lib, fsync=observe_stage_fsync), \
                        mock.patch.object(lib.siaqueue, "_publish_boundary", publication_boundary), \
                        mock.patch.object(lib, "atomic_write", write_real_memo):
                    with self.assertRaises(_MemoTargetPublished) as caught:
                        publication.stage(lib.__dict__, memo=case.memo, batch=batch,
                                          expected_batch_sha256=batch["batch_sha256"])
                self.assertIs(caught.exception, failure)
                self.assertEqual(case.memo, original_memo,
                                 "stage must not report memo completion after the injected cut")
                self.assertIn("memo-target-published", events)
                self.assertNotIn("stage-memo-parent-fsynced-after-target", events)
                # Do not synthesize a receipt or remove any authority keys.
                pending = lib.load_memo()
                self.assertIn("controller_source_pending", pending)
                self.assertNotIn("controller_source_committed", pending)
                self.assertEqual(capture_tests.canonical(pending), memo_path.read_bytes())
                with memo_path.open("rb") as caller_file:
                    caller_identity = _identity(os.fstat(caller_file.fileno()))
                    f = SimpleNamespace(
                        case=case, lib=lib, batch=batch, memo=pending,
                        memo_path=memo_path, wal_path=wal_path,
                        memo_parent=memo_parent, wal_parent=wal_parent,
                        events=events, real_fsync=real_fsync)
                    try:
                        yield f
                    finally:
                        self.assertEqual(_identity(os.fstat(scope_fd)), scope_identity)
                        self.assertEqual(lib._CORPUS_OWNER_FD.get(), scope_fd)
                        self.assertFalse(caller_file.closed)
                        self.assertEqual(_identity(os.fstat(caller_file.fileno())), caller_identity)

    def snapshot(self, f):
        return {
            "memo": _file_image(f.memo_path), "wal": _file_image(f.wal_path),
            "caller_memo": copy.deepcopy(f.memo),
            "cursors": f.case.cursors_path.read_bytes(),
            "corpus": f.case.pages.snapshot(),
            "cursor_renames": copy.deepcopy(f.lib.PENDING_CURSOR_RENAMES),
        }

    @contextlib.contextmanager
    def recovery_only(self, f, *, fail_memo_fsync=None):
        def forbidden(*_args, **_kwargs):
            raise AssertionError("pending durability retry crossed a publication/downstream effect")

        def persist(descriptor):
            identity = _identity(os.fstat(descriptor))
            if identity == f.memo_parent:
                self.assertIn("wal-directory-durable", f.events)
                self.assertIn("memo-target-published", f.events)
                f.events.append("recovery-memo-parent-fsync-attempt")
                if fail_memo_fsync is not None:
                    raise fail_memo_fsync
                result = f.real_fsync(descriptor)
                f.events.append("recovery-memo-parent-fsynced")
                return result
            return f.real_fsync(descriptor)

        with publication_tests.ControllerSourcePublication.inert(
                SimpleNamespace(lib=f.lib)), contextlib.ExitStack() as stack:
            for name in (
                    "atomic_write", "_write_memo", "_stage_controller_source_batch",
                    "_acknowledge_controller_source_batch", "_publish_controller_source_effects",
                    "_recover_controller_source_effects", "_recover_pending_live_generation",
                    "_mark_notify_baseline_attempt", "_clear_notify_baseline_attempt",
                    "_recover_notify_baseline_attempt"):
                if hasattr(f.lib, name):
                    stack.enter_context(mock.patch.object(f.lib, name, side_effect=forbidden))
            stack.enter_context(mock.patch.object(f.lib.siaqueue, "fixed_atomic_publish",
                                                  side_effect=forbidden))
            stack.enter_context(self.local_os(
                f.lib, mkdir=forbidden, replace=forbidden, rename=forbidden,
                unlink=forbidden, fsync=persist))
            yield

    def test_already_pending_retry_flushes_memo_parent_without_rewriting(self):
        with self.crashed_pending() as f:
            before = self.snapshot(f)
            descriptors = _descriptors()
            with self.recovery_only(f):
                self.assertIs(publication.recover_orphan(f.lib.__dict__, memo=f.memo), False)
            self.assertIn("recovery-memo-parent-fsynced", f.events,
                          "existing pending receipt returned before repairing memo directory durability")
            self.assertLess(f.events.index("wal-directory-durable"),
                            f.events.index("memo-target-published"))
            self.assertLess(f.events.index("memo-target-published"),
                            f.events.index("recovery-memo-parent-fsynced"))
            self.assertEqual(self.snapshot(f), before)
            self.assertEqual(_descriptors(), descriptors)

    def test_memo_parent_fsync_failure_propagates_without_false_completion(self):
        with self.crashed_pending() as f:
            before = self.snapshot(f)
            descriptors = _descriptors()
            failure = OSError(errno.EIO, "injected pending memo-parent fsync failure")
            with self.recovery_only(f, fail_memo_fsync=failure):
                with self.assertRaises(OSError) as caught:
                    publication.recover_orphan(f.lib.__dict__, memo=f.memo)
            self.assertIs(caught.exception, failure)
            self.assertIn("recovery-memo-parent-fsync-attempt", f.events)
            self.assertNotIn("recovery-memo-parent-fsynced", f.events)
            self.assertEqual(self.snapshot(f), before)
            self.assertEqual(_descriptors(), descriptors)


if __name__ == "__main__":
    unittest.main()
