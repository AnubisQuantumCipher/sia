"""WAL crossjoins over a genuinely captured first source-v3 batch.

The module-qualified fixture actually ACKs a legacy predecessor, prepares its
delivery epoch, reserves through the recurring runner, and invokes the real
source-v3 capture operation. A positive source-v3 is never obtained by
relabeling v2 bytes. The first v3 WAL is retained/adopted only as pending; no
v3 ACK, v3-to-v3 continuity, downgrade test or writer permit is claimed here.

Negative copies deliberately reseal represented wrapper/outer hashes. The
source validator must accept their represented consistency before the WAL
relationship rejects their disagreement with the actual legacy completion.
The recovery case alters only temporary fixture WAL bytes after a genuine
retention; that mutation is not attributed to any production collector.
"""

import contextlib
import copy
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
from tests import test_controller_source_capture_v3 as capture_tests
from tests import test_controller_source_publication as publication_tests
from tests import test_controller_source_ack as ack_tests
from tests import test_controller_delivery_epoch as epoch_tests

import siasourcepublication as publication


class ControllerSourceFirstV3Wal(unittest.TestCase):
    @contextlib.contextmanager
    def genuine(self):
        fixture = capture_tests.ControllerSourceCaptureV3(methodName="runTest")
        try:
            fixture.setUp()
            with fixture.prepared() as f, fixture.capture_owner(f) as owner:
                with fixture.no_effects(f, owner):
                    batch = fixture.operation(owner.__dict__, **f.request)
                fixture.assert_batch(f, owner, batch)
                self.assertIn(f.retained["schema"], {
                    "sia-controller-source-batch-v1", "sia-controller-source-batch-v2"})
                self.assertEqual(batch["schema"], "sia-controller-source-batch-v3")
                self.assertIsNone(batch["notification_baseline_attempt"])
                self.assertFalse(Path(owner.CONTROLLER_SOURCE_BATCH_PATH).exists())
                yield fixture, f, owner, batch
        finally:
            fixture.doCleanups()

    @contextlib.contextmanager
    def no_downstream(self, fixture, f, owner, *, writes=False, pure=False):
        def forbidden(*_args, **_kwargs):
            raise AssertionError("v3 WAL relationship crossed a forbidden effect")

        with publication_tests.ControllerSourcePublication.inert(
                SimpleNamespace(lib=owner)), contextlib.ExitStack() as stack:
            for module in (owner, f.case.lib):
                for name in (
                        "_acknowledge_controller_source_batch",
                        "_prepare_controller_source_live_candidate",
                        "_stage_controller_source_live_binding",
                        "_publish_controller_source_effects", "utcnow",
                        "_capture_controller_source_successor_batch",
                        "_stage_controller_source_batch"):
                    if hasattr(module, name):
                        stack.enter_context(mock.patch.object(module, name, side_effect=forbidden))
                if not writes:
                    for name in ("atomic_write", "_write_memo"):
                        stack.enter_context(mock.patch.object(module, name, side_effect=forbidden))
            for module, name in (
                    (fixture.source, "capture_successor_v3"),
                    (fixture.source, "capture_successor"),
                    (fixture.source, "_collect"),
                    (fixture.epoch_module, "prepare_epoch"),
                    (fixture.epoch_module, "hold_epoch"),
                    (fixture.epoch_module, "hold_capturable_epoch"),
                    (fixture.journal, "reserve_delivery"),
                    (fixture.journal, "deliver_reserved"),
                    (fixture.journal, "hold_deliveries")):
                stack.enter_context(mock.patch.object(module, name, side_effect=forbidden))
            if not writes:
                stack.enter_context(mock.patch.object(owner.siaqueue, "fixed_atomic_publish",
                                                      side_effect=forbidden))
            if pure:
                for target in ("builtins.open", "os.open", "os.stat", "os.lstat",
                               "os.scandir", "os.listdir", "os.mkdir", "os.fsync", "time.time"):
                    stack.enter_context(mock.patch(target, side_effect=forbidden))
            yield

    def validate(self, fixture, f, owner, batch):
        return fixture.runner.validate_successor_wal(
            owner.__dict__, retained_batch=f.retained, committed=f.committed,
            successor_batch=batch, expected_batch_sha256=batch["batch_sha256"])

    def retain(self, f, owner, batch):
        return publication.retain_successor(
            owner.__dict__, memo=f.case.live.memo, retained_batch=f.retained,
            committed=f.committed, batch=batch,
            expected_batch_sha256=batch["batch_sha256"],
            seq=f.case.live.memo["pulse_seq"])

    def recover(self, f, owner, memo):
        return publication.recover_successor(
            owner.__dict__, memo=memo, retained_batch=f.retained,
            committed=f.committed, seq=memo["pulse_seq"])

    def changed(self, fixture, f, owner, batch, mutation):
        result = copy.deepcopy(batch)
        wrapped = result["delivery_input"]
        if mutation == "parent-schema":
            self.assertNotEqual(f.retained["schema"], "sia-controller-source-batch-v3")
            wrapped["parent_source_schema"] = "sia-controller-source-batch-v3"
        elif mutation == "effects-receipt":
            # A different observed digest, not a claimed second effects receipt.
            foreign = f.retained["batch_sha256"]
            self.assertNotEqual(foreign, f.committed["source_effects_receipt_sha256"])
            wrapped["epoch_view"]["parent_committed"]["source_effects_receipt_sha256"] = foreign
        else:
            self.fail("unknown bounded wrapper mutation")
        # Whole represented wrappers contain native identities; retain their
        # source-native hash family rather than using the live serializer.
        wrapped["expected_epoch_view_sha256"] = fixture.source.native_sha(
            owner.__dict__, wrapped["epoch_view"])
        wrapped["input_sha256"] = fixture.source.native_sha(owner.__dict__, {
            key: value for key, value in wrapped.items() if key != "input_sha256"})
        result["batch_sha256"] = fixture.source.native_sha(owner.__dict__, {
            key: value for key, value in result.items() if key != "batch_sha256"})
        self.assertNotEqual(result["batch_sha256"], batch["batch_sha256"])
        return result

    def unchanged_downstream(self, f):
        return {
            "source-archive": ack_tests._path_image(f.case.archive_path()),
            "effects-archive": ack_tests._path_image(f.case.effects_archive_path()),
            "epoch": epoch_tests._tree(f.root),
            "cursors": Path(f.case.source.lib.CURSORS_PATH).read_bytes(),
            "corpus": f.case.source.pages.snapshot(),
            "live": {name: ack_tests._path_image(f.case.live.paths[name]) for name in (
                "STATUS_PATH", "GRAPH_PATH", "LIVE_CANDIDATE_PATH", "LIVE_STATE_PATH")},
        }

    def test_genuine_first_v3_validates_retains_and_recovers_only_to_pending(self):
        with self.genuine() as (fixture, f, owner, batch):
            original_batch = copy.deepcopy(batch)
            before = self.unchanged_downstream(f)
            memo_before = copy.deepcopy(f.case.live.memo)
            memo_raw = Path(owner.MEMO_PATH).read_bytes()
            wal = Path(owner.CONTROLLER_SOURCE_BATCH_PATH)
            raw = fixture.source.native_bytes(owner.__dict__, batch)
            descriptors = fixture.fd_fixture.fds()
            with self.no_downstream(fixture, f, owner, pure=True):
                self.assertIsNone(self.validate(fixture, f, owner, batch))
            with self.no_downstream(fixture, f, owner, writes=True):
                self.assertIsNone(self.retain(f, owner, batch))
                self.assertEqual(wal.read_bytes(), raw)
                wal_before = ack_tests._path_image(wal)
                self.assertIsNone(self.retain(f, owner, batch))
                self.assertEqual(ack_tests._path_image(wal), wal_before)
                self.assertEqual(Path(owner.MEMO_PATH).read_bytes(), memo_raw)
                self.assertEqual(f.case.live.memo, memo_before)
                # Retry from actual durable completion, not a manufactured
                # old memo or a marker-filtered approximation.
                durable = owner.load_memo()
                self.assertEqual(durable, memo_before)
                self.assertIs(self.recover(f, owner, durable), True)
                self.assertEqual(ack_tests._path_image(wal), wal_before)
                self.assertEqual(owner.load_memo(), durable)
                self.assertNotIn("controller_source_committed", durable)
                self.assertNotIn("ready", durable)
                self.assertEqual(durable["controller_source_pending"]["batch_sha256"],
                                 batch["batch_sha256"])
                self.assertEqual(durable["controller_source_pending"]["parent_batch_sha256"],
                                 f.retained["batch_sha256"])
                self.assertEqual(durable["controller_delivery_epoch"],
                                 memo_before["controller_delivery_epoch"])
                self.assertEqual(durable["pulse_seq"], memo_before["pulse_seq"])
                pending = publication.read_pending(owner.__dict__, memo=durable)
                self.assertEqual(pending["status"], "pending")
                self.assertEqual(pending["batch"], batch)
            self.assertEqual(fixture.fd_fixture.fds(), descriptors)
            self.assertEqual(batch, original_batch)
            self.assertEqual(self.unchanged_downstream(f), before)

    def test_pure_wal_join_rejects_resealed_schema_and_effects_receipt_lies(self):
        with self.genuine() as (fixture, f, owner, batch):
            for mutation in ("parent-schema", "effects-receipt"):
                with self.subTest(mutation=mutation):
                    changed = self.changed(fixture, f, owner, batch, mutation)
                    before = (fixture.images(f), copy.deepcopy(changed))
                    descriptors = fixture.fd_fixture.fds()
                    with self.no_downstream(fixture, f, owner, pure=True):
                        self.assertIsNone(fixture.source.validate_batch(
                            owner.__dict__, changed, changed["batch_sha256"]),
                            "negative fixture must reach the actual-predecessor join")
                        with self.assertRaises(RuntimeError):
                            self.validate(fixture, f, owner, changed)
                    self.assertEqual((fixture.images(f), changed), before)
                    self.assertEqual(fixture.fd_fixture.fds(), descriptors)

    def test_ordinary_retention_rejects_same_lies_before_any_wal_publication(self):
        with self.genuine() as (fixture, f, owner, batch):
            for mutation in ("parent-schema", "effects-receipt"):
                with self.subTest(mutation=mutation):
                    changed = self.changed(fixture, f, owner, batch, mutation)
                    self.assertIsNone(fixture.source.validate_batch(
                        owner.__dict__, changed, changed["batch_sha256"]))
                    before = (fixture.images(f), copy.deepcopy(changed))
                    descriptors = fixture.fd_fixture.fds()
                    with self.no_downstream(fixture, f, owner):
                        with self.assertRaises(RuntimeError):
                            self.retain(f, owner, changed)
                    self.assertFalse(Path(owner.CONTROLLER_SOURCE_BATCH_PATH).exists())
                    self.assertEqual((fixture.images(f), changed), before)
                    self.assertEqual(fixture.fd_fixture.fds(), descriptors)

    def test_ordinary_recovery_rechecks_resealed_fixture_wal_before_adoption(self):
        with self.genuine() as (fixture, f, owner, batch):
            with self.no_downstream(fixture, f, owner, writes=True):
                self.assertIsNone(self.retain(f, owner, batch))
            wal = Path(owner.CONTROLLER_SOURCE_BATCH_PATH)
            original_memo = owner.load_memo()
            for mutation in ("parent-schema", "effects-receipt"):
                with self.subTest(mutation=mutation):
                    changed = self.changed(fixture, f, owner, batch, mutation)
                    self.assertIsNone(fixture.source.validate_batch(
                        owner.__dict__, changed, changed["batch_sha256"]))
                    # Controlled mutation of this test's already retained WAL.
                    # No production capture or retention is said to emit it.
                    wal.write_bytes(fixture.source.native_bytes(owner.__dict__, changed))
                    self.assertEqual(owner.load_memo(), original_memo)
                    durable = owner.load_memo()
                    before = (fixture.images(f), copy.deepcopy(durable), ack_tests._path_image(wal))
                    descriptors = fixture.fd_fixture.fds()
                    with self.no_downstream(fixture, f, owner):
                        with self.assertRaises(RuntimeError):
                            self.recover(f, owner, durable)
                    self.assertEqual((fixture.images(f), durable, ack_tests._path_image(wal)), before)
                    self.assertEqual(fixture.fd_fixture.fds(), descriptors)


if __name__ == "__main__":
    unittest.main()
