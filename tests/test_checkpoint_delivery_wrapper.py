"""Compact delivery binding over real held parent/journal snapshots.

The root digest is a represented fixture pin, not an authenticated retained
root. These pure tests do not authorize source capture or publication.
"""

import copy
from types import SimpleNamespace
import unittest

import siaeventcheckpoint as checkpoints
import siasourcecheckpoint as compact
import siacontrollerdeliverywrapper as api
from tests import test_controller_delivery_wrapper as fixtures
from tests import test_controller_delivery_writer as writer_fixtures
from tests.test_history_block import digest


class CheckpointDeliveryWrapper(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.ControllerDeliveryWrapper(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def request(self, f):
        epoch = f.batch["epoch"]
        replay = {key: epoch[key] for key in checkpoints._CONTEXT_KEYS}
        replay.update(history=epoch["history"], observed_at=f.retained["observed_at"])
        parent = checkpoints.bootstrap_episodes(f.owner, request=replay, expected_request_sha256=digest(replay))
        selected = compact.prepare_epoch(
            f.owner, checkpoint=parent, expected_checkpoint_sha256=digest(parent),
            committed=f.committed, root_sha256="d" * 64, observed_at=f.kw["observed_at"])
        projected = compact.project_capture_entry(
            f.owner, epoch=selected, expected_epoch_sha256=digest(selected), checkpoint=parent,
            returns=f.batch["source_returns"], closure=f.batch["event_closure"], observed_at=f.kw["observed_at"])
        return {**f.kw, "epoch": selected, "expected_epoch_sha256": digest(selected),
                "parent_checkpoint": parent, "projection": projected, "expected_projection_sha256": digest(projected)}

    def validate(self, f, value, kw):
        return api.validate_checkpoint(f.owner, delivery_input=value, expected_input_sha256=value["input_sha256"],
                                       **{key: kw[key] for key in fixtures.CONTEXT_PARAMETERS},
                                       parent_checkpoint=kw["parent_checkpoint"])

    def test_binding_matches_legacy_without_storage_or_fabricated_history(self):
        with self.case.snapshot() as f:
            kw = self.request(f)
            before = copy.deepcopy(kw)
            with self.case.no_io(f):
                expected = api.build(f.owner, **f.kw)
                result = api.build_checkpoint(f.owner, **kw)
                self.validate(f, result, kw)
            self.assertEqual(result["schema"], "sia-controller-checkpoint-delivery-input-v1")
            self.assertEqual(result["binding"], expected["binding"])
            self.assertEqual(result["checkpoint_epoch_sha256"], kw["expected_epoch_sha256"])
            self.assertEqual(result["checkpoint_projection_sha256"], kw["expected_projection_sha256"])
            self.assertEqual(result["parent_checkpoint_sha256"], digest(kw["parent_checkpoint"]))
            self.assertEqual(kw, before)
            self.assertNotIn("history", kw["epoch"])

    def test_full_predecessor_receipt_binding_is_not_dropped(self):
        with self.case.snapshot() as f:
            kw = self.request(f)
            kw["epoch"]["predecessor"]["source_effects_receipt_sha256"] = "e" * 64
            kw["expected_epoch_sha256"] = digest(kw["epoch"])
            with self.case.no_io(f), self.assertRaises(ValueError):
                api.build_checkpoint(f.owner, **kw)

    def test_resealed_wrapper_cannot_switch_projection(self):
        with self.case.snapshot() as f:
            kw = self.request(f)
            with self.case.no_io(f):
                result = api.build_checkpoint(f.owner, **kw)
                result["checkpoint_projection_sha256"] = "e" * 64
                result["input_sha256"] = digest({key: value for key, value in result.items() if key != "input_sha256"})
                with self.assertRaises(ValueError):
                    self.validate(f, result, kw)

    def test_actual_completed_output_record_survives_compact_binding(self):
        writer = writer_fixtures.ControllerDeliveryWriter(methodName="runTest")
        writer.setUp()
        self.addCleanup(writer.doCleanups)
        with writer.completed() as f:
            sink = writer_fixtures.journal_tests.ByteSink(short=True)

            def clock():
                self.assertEqual(sink.events[-1], "flush")
                self.assertEqual(bytes(sink.body), f.body)
                return writer_fixtures.COMPLETED_AT

            with writer.writer_owner(f) as owner, writer.boundary(f, owner):
                completion = writer.call(f, owner, sink=sink, clock=clock)
            self.assertEqual(completion["status"], "service-output-completed")
            writer.epoch.prepare(f.case, f.retained, f.committed, f.status,
                                 expected_adoption_sha256=f.adopted["expected_adoption_sha256"])
            writer.capture.reserve(f.case)
            request = writer.epoch.idle.epoch.build_successor(
                vars(f.case.source.lib), retained_batch=f.retained, committed=f.committed,
                observed_at=writer_fixtures.COMPLETED_AT)
            request.update(memo=f.case.live.memo, admitted_status=f.status, retained_batch=f.retained,
                           committed=f.committed, journal_limits=copy.deepcopy(writer.epoch.limits),
                           expected_journal_limits_sha256=writer.live._sha(writer.epoch.limits),
                           expected_adoption_sha256=f.adopted["expected_adoption_sha256"])
            f.request = request
            batch = writer.capture.capture(f)
            wrapped = batch["delivery_input"]
            legacy_kw = {key: wrapped[key] for key in (
                "parent_source_schema", "epoch_view", "expected_epoch_view_sha256",
                "expected_adoption_sha256", "journal", "expected_journal_sha256")}
            legacy_kw.update(epoch=batch["epoch"], expected_epoch_sha256=batch["epoch_sha256"],
                             projection=batch["intake_projection"],
                             expected_projection_sha256=batch["intake_projection"]["projection_sha256"],
                             observed_at=batch["observed_at"], notification_baseline_attempt=batch["notification_baseline_attempt"])
            selected = SimpleNamespace(**{**vars(f), "batch": batch, "kw": legacy_kw, "owner": vars(f.case.lib)})
            kw = self.request(selected)
            with self.case.no_io(selected):
                result = api.build_checkpoint(selected.owner, **kw)
                self.validate(selected, result, kw)
            self.assertEqual(result["binding"], wrapped["binding"])
            self.assertEqual(result["binding"]["deliveries"]["records"], [completion["record"]])
            self.assertEqual(result["binding"]["deliveries"]["records"][0]["rows"], f.rows)
            self.assertEqual(result["journal"], wrapped["journal"])
