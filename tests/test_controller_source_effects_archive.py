"""RED contract for durable controller source-effects receipt retention.

The composed source ACK fixture has already committed a full, validated effects
receipt before each operation under test.  Acknowledgment must retain those
exact canonical bytes under the receipt's exact digest before it retires the
batch or advances a cursor.  The retained receipt remains required authority
for completed-state replay; the compact memo digest is not a substitute.

These tests establish local durability, ordering, replay and fail-closed file
handling.  They do not establish source truth, hostile same-user immutability,
retrieval quality, biological cognition or a held-out benchmark win.
"""

import contextlib
import copy
import json
import os
from pathlib import Path
import stat
import unittest
from unittest import mock

from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_capture as capture_tests
from tests import test_event_page_plan as page_tests
from tests import test_live_loop as live_tests


EFFECTS_ARCHIVE_DIR = "CONTROLLER_SOURCE_EFFECTS_ARCHIVE_DIR"
EFFECTS_ARCHIVE_BOUNDARY = "effects-receipt-archive-durable"
REFUSALS = (ValueError, RuntimeError, OSError)


class ControllerSourceEffectsArchive(unittest.TestCase):
    def setUp(self):
        self.ack = ack_tests.ControllerSourceAcknowledgment(
            methodName="runTest")
        self.ack.setUp()
        self.addCleanup(self.ack.doCleanups)
        self.lib = self.ack.lib
        self.archive_dir = (
            self.ack.live.root / "controller-source-effects-archive")
        self.archive_constant_existed = hasattr(
            self.lib, EFFECTS_ARCHIVE_DIR)
        # Keep behavioral failures focused if the public constant is absent;
        # the API-shape test independently requires production to define it.
        self.constant_patch = mock.patch.object(
            self.lib, EFFECTS_ARCHIVE_DIR, str(self.archive_dir), create=True)
        self.constant_patch.start()
        self.addCleanup(self.constant_patch.stop)

    @contextlib.contextmanager
    def fresh(self):
        case = type(self)(methodName="runTest")
        case.setUp()
        try:
            yield case
        finally:
            case.doCleanups()

    def receipt(self):
        return copy.deepcopy(
            self.ack.live.memo["controller_source_effects_committed"])

    def receipt_raw(self, receipt=None):
        selected = self.receipt() if receipt is None else receipt
        return capture_tests.canonical(selected)

    def receipt_path(self, receipt=None):
        selected = self.receipt() if receipt is None else receipt
        return self.archive_dir / (selected["receipt_sha256"] + ".json")

    @contextlib.contextmanager
    def forbid_downstream_effects(self, *, forbid_publication=True):
        def forbidden(*_args, **_kwargs):
            raise AssertionError(
                "receipt refusal/replay crossed a write boundary")

        overrides = {"_rename_noreplace": forbidden}
        if forbid_publication:
            overrides["fixed_atomic_publish"] = forbidden
        shim = page_tests._ModuleShim(self.lib.siaqueue, **overrides)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(self.lib, "siaqueue", shim))
            for name in (
                    "atomic_write", "_write_memo", "save_cursors",
                    "_commit_sense_cursors", "_discard_pending_cursor_renames",
                    "_settle_source_refusals",
                    "_settle_source_record_refusals",
                    "_settle_source_entry_refusals",
                    "_publish_event_page_plan",
                    "_publish_event_page_plan_batch",
                    "_publish_event_page_batch_closure",
                    "brain_sync", "export_status", "export_graph"):
                if hasattr(self.lib, name):
                    stack.enter_context(mock.patch.object(
                        self.lib, name, side_effect=forbidden))
            yield

    def assert_private_canonical_receipt(self, receipt):
        path = self.receipt_path(receipt)
        info = path.stat(follow_symlinks=False)
        self.assertTrue(stat.S_ISREG(info.st_mode))
        self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
        self.assertEqual(info.st_uid, os.geteuid())
        self.assertEqual(info.st_nlink, 1)
        self.assertEqual(path.read_bytes(), self.receipt_raw(receipt))
        self.assertEqual(
            capture_tests.canonical(
                self.lib._strict_json_loads(
                    path.read_text(encoding="utf-8"))),
            self.receipt_raw(receipt))
        directory = self.archive_dir.stat(follow_symlinks=False)
        self.assertTrue(stat.S_ISDIR(directory.st_mode))
        self.assertEqual(stat.S_IMODE(directory.st_mode), 0o700)
        self.assertEqual(directory.st_uid, os.geteuid())
        return path

    def test_public_constant_and_named_durable_boundary_are_required(self):
        self.assertTrue(
            self.archive_constant_existed,
            "missing source-effects archive constant: "
            + EFFECTS_ARCHIVE_DIR)
        boundary = getattr(self.lib, ack_tests.BOUNDARY, None)
        self.assertTrue(callable(boundary))
        self.assertIsNone(boundary(EFFECTS_ARCHIVE_BOUNDARY))

    def test_receipt_is_durable_before_batch_archive_or_cursor_ack(self):
        self.ack.start_empty()
        receipt = self.receipt()
        source_before = ack_tests._path_image(self.ack.producer.source_path)
        cursor_before = self.ack.source.cursors_path.read_bytes()
        memo_before = Path(self.ack.live.paths["MEMO_PATH"]).read_bytes()
        phases = []

        def cut(phase):
            phases.append(phase)
            if phase != EFFECTS_ARCHIVE_BOUNDARY:
                self.fail("batch ACK crossed the receipt durability seam")
            self.assert_private_canonical_receipt(receipt)
            self.assertEqual(
                ack_tests._path_image(self.ack.producer.source_path),
                source_before)
            self.assertIsNone(ack_tests._path_image(self.ack.archive_path()))
            self.assertEqual(
                self.ack.source.cursors_path.read_bytes(), cursor_before)
            self.assertEqual(
                Path(self.ack.live.paths["MEMO_PATH"]).read_bytes(),
                memo_before)
            raise KeyboardInterrupt("cut after effects receipt archive")

        with mock.patch.object(
                self.lib, ack_tests.BOUNDARY, side_effect=cut, create=True), \
                self.assertRaisesRegex(
                    KeyboardInterrupt, "effects receipt archive"):
            self.ack.acknowledge()

        self.assertEqual(phases, [EFFECTS_ARCHIVE_BOUNDARY])
        self.assert_private_canonical_receipt(receipt)
        self.assertEqual(
            ack_tests._path_image(self.ack.producer.source_path), source_before)
        self.assertIsNone(ack_tests._path_image(self.ack.archive_path()))
        self.assertEqual(self.ack.source.cursors_path.read_bytes(), cursor_before)

    def test_exact_existing_archive_is_accepted_without_rewriting(self):
        self.ack.start_empty()
        receipt = self.receipt()
        self.archive_dir.mkdir(mode=0o700)
        target = self.receipt_path(receipt)
        target.write_bytes(self.receipt_raw(receipt))
        target.chmod(0o600)
        before = ack_tests._path_image(target)
        phases = []

        with mock.patch.object(
                self.lib, ack_tests.BOUNDARY,
                side_effect=lambda phase: phases.append(phase), create=True):
            self.assertIsNone(self.ack.acknowledge())
        self.assertEqual(phases[0], EFFECTS_ARCHIVE_BOUNDARY)
        self.assertLess(
            phases.index(EFFECTS_ARCHIVE_BOUNDARY),
            phases.index("archive-durable"))
        self.assertEqual(ack_tests._path_image(target), before)
        self.ack.assert_final()

        transaction = self.ack.images()
        with self.forbid_downstream_effects():
            self.assertIsNone(self.ack.acknowledge())
        self.assertEqual(self.ack.images(), transaction)
        self.assertEqual(ack_tests._path_image(target), before)

    def test_unsafe_existing_archives_refuse_before_downstream_mutation(self):
        for selected in (
                "corrupt", "symlink", "noncanonical", "mismatched-digest"):
            with self.subTest(case=selected), self.fresh() as case:
                case.ack.start_empty()
                receipt = case.receipt()
                case.archive_dir.mkdir(mode=0o700)
                target = case.receipt_path(receipt)
                if selected == "corrupt":
                    target.write_bytes(b'{"truncated"')
                    target.chmod(0o600)
                elif selected == "symlink":
                    decoy = case.ack.live.root / "effects-receipt-decoy.json"
                    decoy.write_bytes(case.receipt_raw(receipt))
                    decoy.chmod(0o600)
                    target.symlink_to(decoy)
                elif selected == "noncanonical":
                    target.write_text(
                        json.dumps(
                            receipt, indent=1, sort_keys=True,
                            allow_nan=False),
                        encoding="utf-8")
                    target.chmod(0o600)
                    self.assertNotEqual(
                        target.read_bytes(), case.receipt_raw(receipt))
                else:
                    forged = copy.deepcopy(receipt)
                    forged["non_claims"][0] += " forged"
                    body = copy.deepcopy(forged)
                    body.pop("receipt_sha256")
                    forged["receipt_sha256"] = live_tests.digest(body)
                    self.assertNotEqual(
                        forged["receipt_sha256"], receipt["receipt_sha256"])
                    target.write_bytes(case.receipt_raw(forged))
                    target.chmod(0o600)

                before = case.ack.images()
                archive_before = ack_tests._path_image(target)
                with case.forbid_downstream_effects(
                        forbid_publication=False), \
                        self.assertRaises(REFUSALS):
                    case.ack.acknowledge()
                self.assertEqual(case.ack.images(), before)
                self.assertEqual(
                    ack_tests._path_image(target), archive_before)

    def test_publish_collision_preserves_foreign_target_and_pending_state(self):
        self.ack.start_empty()
        receipt = self.receipt()
        target = self.receipt_path(receipt)
        before = self.ack.images()
        rename = self.lib.siaqueue._rename_noreplace
        foreign = b"foreign source-effects receipt collision"

        def collide(source_descriptor, source_name,
                    destination_descriptor, destination_name):
            if destination_name != target.name:
                raise AssertionError(
                    "batch archive reached before effects receipt archive")
            descriptor = os.open(
                destination_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600, dir_fd=destination_descriptor)
            try:
                os.write(descriptor, foreign)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.fsync(destination_descriptor)
            return rename(
                source_descriptor, source_name,
                destination_descriptor, destination_name)

        with mock.patch.object(
                self.lib.siaqueue, "_rename_noreplace",
                side_effect=collide), self.assertRaises(REFUSALS):
            self.ack.acknowledge()

        self.assertEqual(target.read_bytes(), foreign)
        self.assertEqual(self.ack.images(), before)

    def test_completed_state_requires_and_revalidates_retained_receipt(self):
        for selected in ("absent", "corrupt", "symlink"):
            with self.subTest(case=selected), self.fresh() as case:
                case.ack.start_empty()
                receipt = case.receipt()
                self.assertIsNone(case.ack.acknowledge())
                target = case.assert_private_canonical_receipt(receipt)
                if selected == "absent":
                    target.unlink()
                elif selected == "corrupt":
                    target.write_bytes(b'{"corrupt":true}')
                else:
                    decoy = case.ack.live.root / "completed-receipt-decoy"
                    decoy.write_bytes(case.receipt_raw(receipt))
                    decoy.chmod(0o600)
                    target.unlink()
                    target.symlink_to(decoy)

                before = case.ack.images()
                archive_before = ack_tests._path_image(target)
                with case.forbid_downstream_effects(), \
                        self.assertRaises(REFUSALS):
                    case.ack.acknowledge()
                self.assertEqual(case.ack.images(), before)
                self.assertEqual(
                    ack_tests._path_image(target), archive_before)


if __name__ == "__main__":
    unittest.main()
