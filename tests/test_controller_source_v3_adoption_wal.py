"""Adoption-continuity negative over genuine consecutive v3 captures.

The module-qualified rollover fixture actually publishes and ACKs its first
source-v3 batch. Its next_request and real capture_successor_v3 produce the
second batch under the original adopted storage. No positive source, ACK,
adoption or completion is synthesized by this test.

Only a detached negative copy is changed: its represented records identity
borrows the existing fixture epoch-root directory identity, and the dependent
adoption, held-view, wrapper and source hashes are resealed with their proper
component/native hash families. The original birth, journal, full live parent,
completion receipt, source history, records path and binding remain unchanged.
This self-consistent representation is not an actual alternate adoption.

The source validator must accept the negative representation before the real
WAL relationship and ordinary retention refuse it against the acknowledged
v3 predecessor's independently retained adoption pin. No writer, output,
complete machine history, biological cognition, JACKAL assurance or held-out
retrieval improvement is asserted. Root alone executes this module.
"""

import contextlib
import copy
import os
from pathlib import Path
import sys
import unittest


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "bin"))

from tests import sia_test_home
from tests import test_controller_source_v3_rollover as rollover_tests


V3 = "sia-controller-source-batch-v3"


class ControllerSourceV3AdoptionWal(unittest.TestCase):
    def setUp(self):
        self.rollover = rollover_tests.ControllerSourceV3Rollover(
            methodName="runTest")
        self.addCleanup(self.rollover.doCleanups)
        self.rollover.setUp()
        self.capture = self.rollover.capture
        self.source = self.capture.source
        self.epoch_api = self.capture.epoch_module
        self.runner = self.rollover.runner
        self.publication = self.rollover.publication

    @contextlib.contextmanager
    def genuine_second_capture(self):
        with self.rollover.completed() as f:
            self.assertEqual(f.retained["schema"], V3)
            self.assertEqual(f.case.live.memo["controller_source_committed"],
                             f.committed)
            self.rollover.next_request(f)
            before = self.capture.images(f)
            with self.capture.capture_owner(f) as owner:
                with self.capture.no_effects(f, owner):
                    batch = self.capture.operation(owner.__dict__, **f.request)
                    self.capture.assert_batch(f, owner, batch)
                    self.assertIsNone(self.runner.validate_successor_wal(
                        owner.__dict__, retained_batch=f.retained,
                        committed=f.committed, successor_batch=batch,
                        expected_batch_sha256=batch["batch_sha256"]))
                self.assertEqual(self.capture.images(f), before)
                self.assertEqual(batch["schema"], V3)
                self.assertEqual(batch["delivery_input"]["parent_source_schema"], V3)
                self.assertEqual(
                    batch["delivery_input"]["expected_adoption_sha256"],
                    f.retained["delivery_input"]["expected_adoption_sha256"])
                self.assertFalse(Path(owner.CONTROLLER_SOURCE_BATCH_PATH).exists())
                yield f, owner, batch

    def changed_adoption(self, f, owner, batch):
        result = copy.deepcopy(batch)
        wrapped = result["delivery_input"]
        view = wrapped["epoch_view"]
        original_view = batch["delivery_input"]["epoch_view"]
        birth = copy.deepcopy(view["epoch_adoption"]["birth"])

        # Borrow an observed native directory identity; do not guess or
        # arithmetically alter an inode. No storage is created or rebound.
        foreign_identity = self.epoch_api._identity(
            os.stat(f.root, follow_symlinks=False))
        self.assertEqual(foreign_identity["dev"], view["records_identity"]["dev"])
        self.assertNotEqual(foreign_identity["ino"], view["records_identity"]["ino"])
        adoption = self.epoch_api._adoption(
            owner.__dict__, birth, copy.deepcopy(foreign_identity))
        view["epoch_adoption"] = self.epoch_api._result(birth, adoption)
        view["records_identity"] = copy.deepcopy(foreign_identity)
        wrapped["expected_adoption_sha256"] = adoption["adoption_sha256"]

        # Birth/adoption above use epoch component hashes. Envelopes below
        # contain filesystem identities and retain source-native hashes.
        wrapped["expected_epoch_view_sha256"] = self.source.native_sha(
            owner.__dict__, view)
        wrapped["input_sha256"] = self.source.native_sha(owner.__dict__, {
            key: value for key, value in wrapped.items()
            if key != "input_sha256"})
        result["batch_sha256"] = self.source.native_sha(owner.__dict__, {
            key: value for key, value in result.items()
            if key != "batch_sha256"})

        self.assertNotEqual(wrapped["expected_adoption_sha256"],
                            f.retained["delivery_input"]["expected_adoption_sha256"])
        self.assertNotEqual(result["batch_sha256"], batch["batch_sha256"])
        self.assertEqual(view["epoch_adoption"]["birth"],
                         original_view["epoch_adoption"]["birth"])
        self.assertEqual(
            {key: value for key, value in view.items()
             if key not in {"epoch_adoption", "records_identity"}},
            {key: value for key, value in original_view.items()
             if key not in {"epoch_adoption", "records_identity"}})
        changed_wrapper_fields = {
            "epoch_view", "expected_epoch_view_sha256",
            "expected_adoption_sha256", "input_sha256"}
        self.assertEqual(
            {key: value for key, value in wrapped.items()
             if key not in changed_wrapper_fields},
            {key: value for key, value in batch["delivery_input"].items()
             if key not in changed_wrapper_fields})
        self.assertEqual(
            {key: value for key, value in result.items()
             if key not in {"delivery_input", "batch_sha256"}},
            {key: value for key, value in batch.items()
             if key not in {"delivery_input", "batch_sha256"}})
        return result

    def test_acknowledged_v3_adoption_cannot_be_replaced_by_resealed_successor(self):
        with self.genuine_second_capture() as (f, owner, batch):
            changed = self.changed_adoption(f, owner, batch)
            original_inputs = copy.deepcopy((f.retained, f.committed, batch, changed))
            # Failure here is a negative-fixture setup failure, not evidence
            # that actual predecessor adoption continuity is enforced.
            with self.capture.no_effects(f, owner):
                self.assertIsNone(self.source.validate_batch(
                    owner.__dict__, changed, changed["batch_sha256"]),
                    "the resealed negative must reach the actual predecessor join")

            def validate():
                return self.runner.validate_successor_wal(
                    owner.__dict__, retained_batch=f.retained,
                    committed=f.committed, successor_batch=changed,
                    expected_batch_sha256=changed["batch_sha256"])

            def retain():
                return self.publication.retain_successor(
                    owner.__dict__, memo=f.case.live.memo,
                    retained_batch=f.retained, committed=f.committed,
                    batch=changed, expected_batch_sha256=changed["batch_sha256"],
                    seq=f.seq)

            for front_door, operation in (("validate_successor_wal", validate),
                                           ("retain_successor", retain)):
                with self.subTest(front_door=front_door):
                    before = self.capture.images(f)
                    descriptors = self.capture.fd_fixture.fds()
                    try:
                        with self.capture.no_effects(f, owner):
                            # These are the real effect barriers already
                            # installed by the fixture, never fake success.
                            blocked = owner.siaqueue.fixed_atomic_publish
                            try:
                                with self.assertRaises(RuntimeError):
                                    operation()
                            finally:
                                # Keep the same no-call assertion without
                                # dumping an entire source batch on failure.
                                self.assertEqual(blocked.call_count, 0,
                                                 "unexpected WAL publication")
                    finally:
                        self.assertEqual(self.capture.images(f), before)
                        self.assertFalse(Path(owner.CONTROLLER_SOURCE_BATCH_PATH).exists())
                        self.assertEqual((f.retained, f.committed, batch, changed),
                                         original_inputs)
                        self.assertEqual(self.capture.fd_fixture.fds(), descriptors)


if __name__ == "__main__":
    unittest.main()
