"""Actual fixed-slot and memo adoption of a prepared compact root pulse."""

import contextlib
import copy
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import siahistoryroot as roots
import siacontrollersourcerunner as runner
from tests import test_checkpoint_transaction as fixtures


class CheckpointAdoption(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("siacheckpointadoption")
        self.case = fixtures.CheckpointTransaction(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    @contextlib.contextmanager
    def prepared(self, *, fenced=False):
        fixture = self.case.case.case
        with fixture.prepared(nonidle=not fenced) as f, tempfile.TemporaryDirectory(prefix="sia-checkpoint-adoption-") as directory:
            root = roots.prepare(vars(f.case.lib), memo=f.case.live.memo, admitted_status=f.status, directory=directory)
            if fenced:
                f.case.lib._mark_notify_baseline_attempt(f.case.live.memo)
            with fixture.capture_owner(f) as owner:
                owner._load_live_publication()
                package = self.case.invoke(f, owner, directory, root)
                request = dict(memo=f.case.live.memo, admitted_status=f.status, directory=directory,
                    expected_manifest_sha256=package["manifest_sha256"], expected_root_sha256=root["root_sha256"],
                    journal_limits=f.request["journal_limits"],
                    expected_journal_limits_sha256=f.request["expected_journal_limits_sha256"],
                    expected_adoption_sha256=f.request["expected_adoption_sha256"], seq=f.case.live.memo["pulse_seq"])
                yield f, owner, package, request

    def test_real_adoption_is_pending_and_idempotent_not_legacy_publication(self):
        with self.prepared() as (f, owner, package, request):
            self.assertTrue(self.api.adopt_root(vars(owner), **request))
            self.assertFalse(self.api.adopt_root(vars(owner), **request))
            self.assertEqual(owner.load_memo(), request["memo"])
            self.assertNotIn("ready", request["memo"])
            self.assertNotIn("controller_source_committed", request["memo"])
            self.assertEqual(runner._source_state(request["memo"]), "batch")
            self.assertTrue(owner._controller_source_ack_pending(request["memo"]))
            with self.assertRaises(ValueError):
                owner._read_pending_controller_source_batch(memo=request["memo"])
            view = self.api.read_pending(vars(owner), **{key: value for key, value in request.items()
                if key not in {"journal_limits", "expected_journal_limits_sha256", "expected_adoption_sha256", "seq"}})
            self.assertEqual(view["status"], "pending-not-published")
            self.assertEqual(view["package"]["manifest"], package["manifest"])
            self.assertEqual(request["memo"]["live_loop_committed"]["generation_sha256"], f.generation["generation_sha256"])

    def test_retry_after_fixed_slot_before_memo_never_recollects(self):
        with self.prepared() as (f, owner, package, request):
            before = copy.deepcopy(request["memo"])
            actual_write = owner.atomic_write

            def interrupted(path, *args, **kwargs):
                if path == owner.MEMO_PATH:
                    raise OSError("controlled adoption interruption")
                return actual_write(path, *args, **kwargs)

            with mock.patch.object(owner, "atomic_write", side_effect=interrupted):
                with self.assertRaisesRegex(OSError, "controlled adoption interruption"):
                    self.api.adopt_root(vars(owner), **request)
            self.assertEqual(request["memo"], before)
            self.assertEqual(owner.load_memo(), before)
            self.assertTrue(Path(owner.CONTROLLER_SOURCE_BATCH_PATH).exists())
            with mock.patch.object(self.api.transaction.checkpoint, "capture_root_delivery", side_effect=AssertionError("retry recollected")):
                self.assertTrue(self.api.adopt_root(vars(owner), **request))
            self.assertEqual(request["memo"]["controller_source_pending"]["batch_sha256"], package["manifest"]["source_batch_sha256"])

    def test_retry_after_durable_memo_reload_preserves_notification_fence(self):
        with self.prepared(fenced=True) as (f, owner, package, request):
            before = copy.deepcopy(request["memo"])
            actual_write = owner.atomic_write

            def interrupted(path, *args, **kwargs):
                result = actual_write(path, *args, **kwargs)
                if path == owner.MEMO_PATH:
                    raise OSError("controlled post-memo interruption")
                return result

            with mock.patch.object(owner, "atomic_write", side_effect=interrupted):
                with self.assertRaisesRegex(OSError, "controlled post-memo interruption"):
                    self.api.adopt_root(vars(owner), **request)
            self.assertEqual(request["memo"], before)
            request["memo"] = owner.load_memo()
            marker = self.api.source._notification_marker(vars(owner), before)
            self.assertIsNotNone(marker)
            self.assertEqual(self.api.source._notification_marker(vars(owner), request["memo"]), marker)
            with mock.patch.object(self.api.transaction.checkpoint, "capture_root_delivery", side_effect=AssertionError("retry recollected")), \
                    mock.patch.object(owner, "atomic_write", side_effect=AssertionError("adopted retry wrote")):
                self.assertFalse(self.api.adopt_root(vars(owner), **request))
            self.assertNotIn("ready", request["memo"])
            self.assertEqual(request["memo"]["controller_source_pending"]["batch_sha256"], package["manifest"]["source_batch_sha256"])
