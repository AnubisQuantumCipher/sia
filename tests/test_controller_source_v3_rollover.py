"""Actual source-v3 ACK followed by an adopted second-v3 source capture.

The composed effects fixture genuinely captures, retains, binds and publishes
the first v3 source transaction. Its ordinary ACK front door then archives the
real source/effects bytes, settles the proposed cursors and publishes compact
completion. No positive case relabels a source schema or invents v3 completion.

The existing run_v2 reservation-to-clock seam allocates the next sequence; it
is deliberately stopped before its legacy capture path. This is not a claim
that an end-to-end resident v3 runner exists. The next source epoch and v3
capture use their actual front doors, retaining the original adoption and
binding the newly published full live parent. The second WAL is not ACKed.

Git/index observations remain the existing controlled effects-fixture seams.
These tests concern local ordering and retained joins, not external engine
correctness, writer authorization, output delivery, complete machine history,
biological cognition, JACKAL assurance or a held-out retrieval improvement.
Root alone runs this module, sequentially under the mission memory cap.
"""

import contextlib
import copy
import importlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import test_controller_delivery_epoch as epoch_tests
from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_idle as idle_tests
from tests import test_controller_source_v3_live_effects as effects_tests


REFUSALS = (ValueError, RuntimeError, OSError)
V3 = "sia-controller-source-batch-v3"


class ControllerSourceV3Rollover(unittest.TestCase):
    def setUp(self):
        self.effects = effects_tests.ControllerSourceV3LiveEffects(methodName="runTest")
        self.addCleanup(self.effects.doCleanups)
        self.effects.setUp()
        self.capture = self.effects.capture_fixture
        self.source = self.capture.source
        self.epoch = self.capture.epoch
        self.live = self.capture.live
        self.ack = importlib.import_module("siasourceack")
        self.publication = self.effects.publication
        self.runner = self.capture.runner

    @staticmethod
    def forbidden(name):
        return mock.Mock(side_effect=AssertionError("v3 rollover repeated forbidden work: " + name))

    @contextlib.contextmanager
    def no_content_republication(self, f):
        with self.effects.no_recapture(f), contextlib.ExitStack() as stack:
            blocked = self.forbidden("live/content publication")
            for name in (
                    "_publish_controller_source_effects", "_stage_live_generation",
                    "_publish_staged_live_generation", "_publish_event_page_batch_closure",
                    idle_tests.GIST_PREPARER, idle_tests.GIST_PUBLISHER,
                    idle_tests.GIST_COMMITTER, "brain_sync", "export_status", "export_graph"):
                stack.enter_context(mock.patch.object(f.case.lib, name, blocked))
            yield
        blocked.assert_not_called()

    @contextlib.contextmanager
    def completed(self):
        with self.effects.pending(nonidle=True) as f:
            bootstrap_archive = ack_tests._path_image(f.case.archive_path(f.retained))
            original_adoption = copy.deepcopy(f.adopted)
            adoption_files = epoch_tests._tree(f.root)
            self.effects.bind_status(f)
            with self.effects.no_recapture(f), self.effects.content_effects(f):
                self.assertIsNone(f.case.effects.publisher()(
                    memo=f.case.live.memo, admitted_status=f.status))
            receipt = self.effects.assert_receipt(f)
            actual_generation = f.case.live._read("LIVE_STATE_PATH")
            self.assertEqual(receipt["live_generation"]["generation_sha256"],
                             actual_generation["generation_sha256"])
            self.assertNotEqual(actual_generation["generation_sha256"],
                                f.generation["generation_sha256"])

            # Bookkeeping reads actual completed-effects artifacts only.
            # The ACK operation never consults these TestCase fields.
            f.case._remember_committed(copy.deepcopy(f.batch), copy.deepcopy(actual_generation))
            source_image = ack_tests._path_image(f.case.producer.source_path)
            content = self.effects.content_images(f)
            with self.no_content_republication(f):
                self.assertIsNone(f.case.acknowledge())
            durable = f.case.assert_final()
            self.assertEqual(ack_tests._path_image(f.case.archive_path())[0][:2],
                             source_image[0][:2])
            self.assertEqual(self.effects.content_images(f), content)
            self.assertEqual(ack_tests._path_image(f.case.archive_path(f.retained)), bootstrap_archive)
            self.assertEqual(epoch_tests._tree(f.root), adoption_files)
            self.assertEqual(f.adopted, original_adoption)
            self.assertEqual(durable[epoch_tests.MARKER_KEY]["adoption_sha256"],
                             original_adoption["expected_adoption_sha256"])
            committed = copy.deepcopy(durable["controller_source_committed"])
            self.assertEqual(committed, {
                "source_batch_sha256": f.batch["batch_sha256"],
                "live_generation_sha256": actual_generation["generation_sha256"],
                "source_effects_receipt_sha256": receipt["receipt_sha256"],
            })
            fields = dict(vars(f))
            fields.update(bootstrap_retained=copy.deepcopy(f.retained),
                          bootstrap_generation=copy.deepcopy(f.generation),
                          retained=copy.deepcopy(f.batch), committed=committed,
                          generation=copy.deepcopy(actual_generation),
                          status=copy.deepcopy(f.case.admitted_status()), nonidle=False,
                          completed_receipt=copy.deepcopy(receipt))
            yield SimpleNamespace(**fields)

    def next_request(self, f):
        original_adoption = copy.deepcopy(f.adopted)
        before = self.capture.images(f)
        # Existing v3 storage is observed, never re-born or refreshed.
        with self.epoch.no_new_work(f.case), f.case.forbid_ack_effects():
            adopted = self.epoch.prepare(
                f.case, f.retained, f.committed, f.status,
                expected_adoption_sha256=original_adoption["expected_adoption_sha256"])
        self.assertEqual(adopted, original_adoption)
        self.assertEqual(self.capture.images(f), before)

        # Real durable allocation only. The supplied clock raises before
        # legacy capture, so this is not a successful run_v2 rollover.
        self.capture.reserve(f.case)
        request = self.epoch.idle.successor_request(f.case, f.retained, f.committed)
        request.update({
            "memo": f.case.live.memo, "admitted_status": f.status,
            "retained_batch": f.retained, "committed": f.committed,
            "journal_limits": copy.deepcopy(self.epoch.limits),
            "expected_journal_limits_sha256": self.live._sha(self.epoch.limits),
            "expected_adoption_sha256": original_adoption["expected_adoption_sha256"],
        })
        self.assertEqual(request["epoch"]["predecessor"], {
            "source_batch_sha256": f.retained["batch_sha256"],
            "live_generation_sha256": f.generation["generation_sha256"],
        })
        history = copy.deepcopy(f.retained["epoch"]["history"])
        closure = f.retained["event_closure"]
        history["entries"].append({
            "source_returns": copy.deepcopy(f.retained["source_returns"]),
            "expected_source_returns_sha256": f.retained["source_returns"]["returns_sha256"],
            "event_batches": [] if closure is None else [
                {"batch": copy.deepcopy(member), "expected_batch_sha256": member["batch_sha256"]}
                for member in closure["batches"]],
        })
        self.assertEqual(request["epoch"]["history"], history)
        f.request, f.seq = request, f.case.live.memo["pulse_seq"]
        return request

    def test_actual_v3_ack_archives_exact_content_and_completed_retry_is_effectless(self):
        with self.completed() as f:
            before = self.capture.images(f)
            with self.no_content_republication(f), f.case.forbid_ack_effects():
                self.assertIsNone(f.case.acknowledge())
                view = self.ack.read_completed(
                    f.case.lib.__dict__, memo=f.case.live.memo, admitted_status=f.status)
            self.assertEqual(set(view), {"status", "batch", "committed"})
            self.assertEqual(view, {"status": "available", "batch": f.retained, "committed": f.committed})
            self.assertEqual(view["batch"]["schema"], V3)
            self.assertEqual(view["batch"]["delivery_input"]["epoch_view"]["epoch_adoption"], f.adopted)
            self.assertEqual(f.case.archive_path().read_bytes(),
                             self.source.native_bytes(f.case.lib.__dict__, f.retained))
            self.assertEqual(f.case.effects_archive_path().read_bytes(),
                             self.source.native_bytes(f.case.lib.__dict__, f.completed_receipt))
            view["batch"]["delivery_input"]["epoch_view"]["epoch_adoption"].clear()
            view["committed"].clear()
            with self.no_content_republication(f), f.case.forbid_ack_effects():
                again = self.ack.read_completed(
                    f.case.lib.__dict__, memo=f.case.live.memo, admitted_status=f.status)
            self.assertEqual(again, {"status": "available", "batch": f.retained, "committed": f.committed})
            self.assertEqual(self.capture.images(f), before)

    def test_second_real_v3_capture_retains_original_adoption_and_new_full_parent(self):
        with self.completed() as f:
            self.next_request(f)
            before = self.capture.images(f)
            with self.capture.capture_owner(f) as owner:
                with self.capture.no_effects(f, owner):
                    batch = self.capture.operation(owner.__dict__, **f.request)
                self.capture.assert_batch(f, owner, batch)
                self.assertEqual(self.capture.images(f), before)
                self.assertNotEqual(batch["batch_sha256"], f.retained["batch_sha256"])
                self.assertIsNotNone(batch["idle_input"])
                self.assertTrue(all(not row["events"] for row in batch["source_returns"]["runs"]))
                wrapper = batch["delivery_input"]
                original = f.retained["delivery_input"]
                self.assertEqual(wrapper["parent_source_schema"], V3)
                self.assertEqual(wrapper["expected_adoption_sha256"], original["expected_adoption_sha256"])
                self.assertEqual(wrapper["epoch_view"]["epoch_adoption"], original["epoch_view"]["epoch_adoption"])
                self.assertEqual(wrapper["epoch_view"]["parent_generation"], f.case.live._read("LIVE_STATE_PATH"))
                self.assertNotEqual(wrapper["epoch_view"]["parent_generation"],
                                    original["epoch_view"]["parent_generation"])
                self.assertEqual(wrapper["epoch_view"]["expected_parent_generation_sha256"],
                                 self.live._own(f.generation, "generation_sha256"))
                self.assertEqual(wrapper["epoch_view"]["parent_committed"], f.committed)
                self.assertEqual(wrapper["epoch_view"]["epoch_adoption"]["birth"]["bootstrap_parent"], {
                    "source_batch_sha256": f.bootstrap_retained["batch_sha256"],
                    "live_generation_sha256": f.bootstrap_generation["generation_sha256"],
                    "state_sha256": f.bootstrap_generation["state_sha256"],
                })
                self.assertEqual(wrapper["journal"], original["journal"])
                self.assertEqual(wrapper["binding"]["deliveries"]["records"], [])
                self.assertIsNone(self.runner.validate_successor_wal(
                    owner.__dict__, retained_batch=f.retained, committed=f.committed,
                    successor_batch=batch, expected_batch_sha256=batch["batch_sha256"]))
                # The continuous outer corpus lease spans actual capture,
                # closed held snapshots, and immutable second-WAL retention.
                with self.no_content_republication(f):
                    self.assertIsNone(self.publication.retain_successor(
                        owner.__dict__, memo=f.case.live.memo, retained_batch=f.retained,
                        committed=f.committed, batch=batch,
                        expected_batch_sha256=batch["batch_sha256"], seq=f.seq))
            self.assertEqual(Path(f.case.producer.source_path).read_bytes(),
                             self.source.native_bytes(f.case.lib.__dict__, batch))
            self.assertEqual(f.case.live.memo, before[3])
            self.assertEqual(f.case.live._read("MEMO_PATH"), before[3])
            self.assertEqual(f.case.live.memo["controller_source_committed"], f.committed)
            self.assertNotIn("controller_source_pending", f.case.live.memo)
            self.assertFalse(f.case.archive_path(batch).exists())
            self.assertEqual(epoch_tests._tree(f.root), before[1])
            # Different orphan WAL bytes do not silently become ACK authority.
            with self.no_content_republication(f), f.case.forbid_ack_effects():
                view = self.ack.read_completed(
                    f.case.lib.__dict__, memo=f.case.live.memo, admitted_status=f.status)
            self.assertEqual(view, {"status": "available", "batch": f.retained, "committed": f.committed})

    def test_actual_v3_parent_cannot_downgrade_capture_or_retain_legacy_child(self):
        with self.completed() as f:
            self.next_request(f)
            before = self.capture.images(f)
            collected = self.forbidden("legacy collection after v3 ACK")
            with self.capture.capture_owner(f) as owner:
                with mock.patch.object(self.source, "_collect", collected), \
                        self.capture.no_effects(f, owner), self.assertRaises(self.source.SourceBatchRefusal) as caught:
                    self.source.capture_successor(
                        owner.__dict__, memo=f.case.live.memo, retained_batch=f.retained,
                        committed=f.committed, epoch=f.request["epoch"],
                        expected_epoch_sha256=f.request["expected_epoch_sha256"],
                        observed_at=f.request["observed_at"])
                self.assertEqual(caught.exception.reason, "delivery-predecessor-requires-source-v3-capture")
                collected.assert_not_called()
                with self.capture.no_effects(f, owner):
                    batch = self.capture.operation(owner.__dict__, **f.request)

                # Adversarial omission, never represented as a captured
                # success: ordinary v2 shape/hash checks alone are insufficient
                # to authorize downgrading this actual v3 predecessor.
                legacy = copy.deepcopy(batch)
                legacy["schema"] = "sia-controller-source-batch-v2"
                legacy.pop("delivery_input")
                legacy.pop("batch_sha256")
                legacy["batch_sha256"] = self.source.native_sha(owner.__dict__, legacy)
                self.assertIsNone(self.source.validate_batch(owner.__dict__, legacy, legacy["batch_sha256"]))
                with self.assertRaises(REFUSALS):
                    self.runner.validate_successor_wal(
                        owner.__dict__, retained_batch=f.retained, committed=f.committed,
                        successor_batch=legacy, expected_batch_sha256=legacy["batch_sha256"])
                with f.case.forbid_ack_effects(), self.capture.no_effects(f, owner), self.assertRaises(REFUSALS):
                    self.publication.retain_successor(
                        owner.__dict__, memo=f.case.live.memo, retained_batch=f.retained,
                        committed=f.committed, batch=legacy,
                        expected_batch_sha256=legacy["batch_sha256"], seq=f.seq)
            self.assertEqual(self.capture.images(f), before)

    def test_actual_v3_adoption_pin_remains_mandatory_before_preparation_and_collection(self):
        with self.completed() as f:
            self.next_request(f)
            before = self.capture.images(f)
            wrong_pin = "0" * 64
            self.assertNotEqual(wrong_pin, f.adopted["expected_adoption_sha256"])
            for pin in (None, wrong_pin):
                with self.subTest(pin=pin):
                    with self.epoch.no_new_work(f.case), f.case.forbid_ack_effects(), self.assertRaises(REFUSALS):
                        self.epoch.prepare(f.case, f.retained, f.committed, f.status,
                                           expected_adoption_sha256=pin)
                    collected = self.forbidden("collection before parent adoption admission")
                    with self.capture.capture_owner(f) as owner, \
                            self.capture.no_effects(f, owner), \
                            mock.patch.object(self.source, "_collect", collected), \
                            self.assertRaises(REFUSALS):
                        self.capture.operation(owner.__dict__, **{
                            **f.request, "expected_adoption_sha256": pin})
                    collected.assert_not_called()
                    self.assertEqual(self.capture.images(f), before)


if __name__ == "__main__":
    unittest.main()
