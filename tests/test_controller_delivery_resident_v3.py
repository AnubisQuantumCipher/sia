"""Actual output becomes retained input in the next completed resident cycle.

One genuinely acknowledged source-v3 parent admits the real source writer.
The actual sink returns from write-all-and-flush, then the actual owning
resident run_v3 captures that complete journal, publishes live/content/status
effects and acknowledges the successor. No successful source, generation,
writer, publication or ACK result is replaced by a fixture result.

The existing external-effects fixture still controls Git/index observations
and status/graph observation clocks. The source controller clock below is the
previously supplied JACKAL result, not an observation of this machine's time.
Rows and body remain the sourcewriter fixture's explicit caller premises, not
engine query results or proof of rendered semantic fidelity. This test does
not enable a resident service or CLI writer, observe human reading, prove
external Git/index programs, or establish a biological/held-out cognitive win.

The resident fixture's old assertion helpers intentionally freeze an empty
journal. The local nonempty helpers retain their shape, hash, ownership,
current-parent and adoption checks and require the actual completed record.
Only the test controller-clock constant and a test assertion method are
adapted; no production admission/currentness check is weakened or replaced.
Root alone executes this module sequentially under the mission memory cap.
"""

import copy
import importlib
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_delivery_epoch as epoch_tests
from tests import test_controller_delivery_wrapper as wrapper_tests
from tests import test_controller_delivery_writer as writer_tests
from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_capture as source_capture_tests
from tests import test_controller_source_capture_v3 as capture_tests
from tests import test_controller_source_resident_v3 as resident_tests
from tests import test_delivery_journal as journal_tests


# Reuse the observed result, not new arithmetic or a newly observed clock:
# JACKAL status=exact parsed=2000000010+1 exact=2000000011 formal=false.
# Assurance: exact rational arithmetic (not yet checker-covered).
# All original nonclaims remain in writer_tests.EXACT_NON_CLAIMS.
COMPLETED_AT = writer_tests.COMPLETED_AT


class ControllerDeliveryResidentV3(unittest.TestCase):
    def setUp(self):
        self.writer = writer_tests.ControllerDeliveryWriter(methodName="runTest")
        self.addCleanup(self.writer.doCleanups)
        self.writer.setUp()
        self.core = importlib.import_module("sialib")
        self.assertTrue(callable(getattr(self.writer.capture.runner, "run_v3", None)))
        self.assertTrue(callable(getattr(self.core, resident_tests.ENTRY, None)))

        # Share the already composed genuine fixture rather than creating
        # another corpus or discovering the fixture classes as test suites.
        self.resident = resident_tests.ControllerSourceResidentV3(methodName="runTest")
        self.resident.runner, self.resident.core = self.writer.capture.runner, self.core
        for name in ("rollover", "capture", "epoch", "source", "live"):
            setattr(self.resident, name, getattr(self.writer, name))
        self.resident.effects = self.writer.rollover.effects
        self.source, self.live = self.writer.source, self.writer.live

    def assert_captured_record(self, f, owner, result, *, inspected, record):
        """The existing exact capture contract, with actual nonempty history."""
        self.assertIs(type(result), dict)
        self.assertEqual(set(result), capture_tests.BATCH_KEYS)
        self.assertEqual(result["schema"], capture_tests.SCHEMA)
        self.assertEqual(result["status"], "captured-not-published")
        self.assertEqual(result["batch_sha256"], source_capture_tests.own(result, "batch_sha256"))
        self.assertEqual(result["epoch"], f.request["epoch"])
        self.assertEqual(result["epoch_sha256"], f.request["expected_epoch_sha256"])
        self.assertEqual(result["observed_at"], f.request["observed_at"])
        self.assertEqual(result["observed_at"], COMPLETED_AT)
        self.assertEqual(result["notification_baseline_attempt"], f.marker)
        self.assertIsNone(f.marker)
        self.assertEqual(result["non_claims"], list(self.source.NON_CLAIMS))
        wrapped = result["delivery_input"]
        self.assertEqual(set(wrapped), wrapper_tests.WRAPPER_KEYS)
        self.assertEqual(wrapped["schema"], wrapper_tests.SCHEMA)
        self.assertEqual(wrapped["status"], "bound-not-consumed")
        self.assertEqual(wrapped["parent_source_schema"], f.retained["schema"])
        self.assertEqual(wrapped["non_claims"], list(self.writer.capture.wrapper.NON_CLAIMS))
        self.assertEqual(wrapped["expected_adoption_sha256"], f.adopted["expected_adoption_sha256"])
        view = wrapped["epoch_view"]
        self.assertEqual(view["schema"], "sia-controller-delivery-epoch-view-v1")
        self.assertEqual(view["status"], "held-not-consumed")
        self.assertEqual(view["epoch_adoption"], f.adopted)
        self.assertEqual(view["parent_generation"], f.generation)
        self.assertEqual(view["parent_committed"], f.committed)
        self.assertEqual(view["records_identity"], f.adopted["adoption"]["records_identity"])
        self.assertEqual(view["expected_parent_generation_sha256"],
                         f.committed["live_generation_sha256"])
        self.assertEqual(wrapped["expected_epoch_view_sha256"],
                         self.source.native_sha(owner.__dict__, view))
        self.assertEqual(wrapped["journal"], inspected)
        self.assertEqual(wrapped["journal"]["records"], [record])
        self.assertEqual(wrapped["journal"]["pending"], [])
        self.assertIs(wrapped["journal"]["complete"], True)
        self.assertEqual(wrapped["expected_journal_sha256"], self.live._sha(inspected))
        self.assertEqual(wrapped["input_sha256"], source_capture_tests.own(wrapped, "input_sha256"))
        projection = result["intake_projection"]
        self.assertEqual(wrapped["binding"]["intake_sha256"], projection["intake_sha256"])
        self.assertEqual(wrapped["binding"]["deliveries"]["records"], [record])
        self.assertIs(wrapped["binding"]["deliveries"]["complete"], True)
        self.assertIsNone(self.writer.capture.wrapper.validate(owner.__dict__,
            delivery_input=wrapped, expected_input_sha256=wrapped["input_sha256"],
            epoch=result["epoch"], expected_epoch_sha256=result["epoch_sha256"],
            projection=projection, expected_projection_sha256=projection["projection_sha256"],
            observed_at=result["observed_at"], notification_baseline_attempt=f.marker))
        self.assertIsNone(self.source.validate_batch(owner.__dict__, result, result["batch_sha256"]))

    def assert_completed_record(self, f, status, trace, record):
        """Actual ACK/archive checks, plus exact nonempty retained live use."""
        self.assertEqual(trace.scope_events,
                         ["brainstem-enter", "corpus-enter", "corpus-exit", "brainstem-exit"])
        self.assertEqual(trace.active_scopes, [])
        durable = f.case.assert_final()
        self.assertEqual(status, f.case.admitted_status())
        self.assertEqual(f.case.batch, f.batch)
        self.assertEqual(f.batch["schema"], resident_tests.V3)
        self.assertGreater(durable["pulse_seq"], f.status["pulse_seq"])
        self.assertNotEqual(f.case.generation["generation_sha256"], f.generation["generation_sha256"])
        self.assertEqual(f.case.generation, f.case.live._read("LIVE_STATE_PATH"))
        wrapped = f.batch["delivery_input"]
        self.assertEqual(wrapped["epoch_view"]["parent_generation"], f.generation)
        self.assertEqual(wrapped["epoch_view"]["parent_committed"], f.committed)
        self.assertEqual(wrapped["epoch_view"]["epoch_adoption"], f.adopted)
        self.assertEqual(wrapped["expected_adoption_sha256"], f.adopted["expected_adoption_sha256"])
        self.assertEqual(durable[epoch_tests.MARKER_KEY]["adoption_sha256"],
                         f.adopted["expected_adoption_sha256"])
        self.assertEqual(trace.acknowledgments,
                         [f.case.memo_before_ack["controller_source_effects_committed"]])
        self.assertTrue(trace.effects)
        self.assertEqual(f.candidate["prepare_inputs"]["deliveries"], wrapped["binding"]["deliveries"])
        self.assertEqual(f.candidate["prepare_inputs"]["previous_state"], f.generation["transition"]["state"])
        self.assertEqual(f.candidate["prepare_inputs"]["expected_previous_state_sha256"],
                         f.generation["state_sha256"])
        self.assertEqual(f.transition, f.case.generation["transition"])
        self.assertEqual(f.transition["status"], "planned")
        state = f.case.generation["transition"]["state"]
        history = f.case.generation["transition"]["history_capture"]
        self.assertEqual(state["observed_at"], COMPLETED_AT)
        self.assertEqual(state["deliveries"]["records"], [record])
        self.assertEqual(history["deliveries"], state["deliveries"])
        self.assertEqual(history["uses"], state["uses"])
        self.assertEqual(history["state_sha256"], f.case.generation["state_sha256"])
        self.assertEqual(state["non_claims"], list(self.live.NON_CLAIMS))
        self.assertEqual(history["non_claims"], list(self.live.NON_CLAIMS))
        self.assertIn(f.page, state["intake"]["pages"])
        self.assertIn(f.page["version_sha256"], state["intake"]["current_versions"])
        self.assertEqual(record["rows"], f.rows)
        self.assertEqual(record["rows"][0]["row"]["origin"], f.page["origin"])
        identity = {"kind": "service-output-completed", "record_id": record["id"],
                    "version_sha256": f.page["version_sha256"]}
        expected_use = {"id": self.live._sha(identity), **identity,
            "timestamp": COMPLETED_AT, "origin": "derived", "subject": f.page["subject"],
            "subject_origin": f.page["origin"], "source_sha256": f.page["source_sha256"],
            "content_sha256": f.page["content_sha256"]}
        self.assertEqual([use for use in state["uses"] if use["kind"] == "service-output-completed"],
                         [expected_use])
        self.assertEqual([entry for entry in state["admission"] if entry["kind"] == "delivery"], [{
            "kind": "delivery", "record_id": record["id"],
            "version_sha256": f.page["version_sha256"], "eligible": True,
            "reason": "explicit-delivery-admitted"}])
        with self.writer.rollover.no_content_republication(f), f.case.forbid_ack_effects():
            completed = self.writer.rollover.ack.read_completed(
                f.case.lib.__dict__, memo=f.case.live.memo, admitted_status=status)
        self.assertEqual(completed, {"status": "available", "batch": f.batch,
                                    "committed": durable["controller_source_committed"]})
        self.assertFalse(Path(f.case.producer.source_path).exists())
        self.assertEqual(f.case.archive_path(f.batch).read_bytes(),
                         self.source.native_bytes(f.case.lib.__dict__, f.batch))
        return durable

    def test_actual_output_is_consumed_by_the_next_resident_publication_and_ack(self):
        with self.writer.completed() as f:
            source_before_output = f.case.images()
            original_generation = copy.deepcopy(f.generation)
            original_adoption = copy.deepcopy(f.adopted)
            original_rows = copy.deepcopy(f.rows)
            self.assertEqual(original_generation["transition"]["state"]["deliveries"]["records"], [])
            parent_archive = ack_tests._path_image(f.case.archive_path(f.retained))
            sink = journal_tests.ByteSink(short=True)

            def completion_clock():
                self.assertEqual(sink.events[-1], "flush")
                self.assertEqual(bytes(sink.body), f.body)
                return COMPLETED_AT

            with self.writer.writer_owner(f) as owner, self.writer.boundary(f, owner) as output:
                completion = self.writer.call(f, owner, sink=sink, clock=completion_clock)
            self.assertEqual(set(completion), journal_tests.COMPLETION_KEYS)
            self.assertEqual(completion["status"], "service-output-completed")
            self.assertEqual(completion["boundary"], "write-all-and-flush-returned")
            self.assertEqual(completion["non_claims"], list(self.writer.journal.NON_CLAIMS))
            self.assertEqual(completion["completion_sha256"], self.live._own(completion, "completion_sha256"))
            self.assertTrue(output.ranked)
            self.assertEqual(output.ranked[-1]["status"], "computed-unverified")
            record = copy.deepcopy(completion["record"])
            self.assertEqual(record["rank_sha256"], output.ranked[-1]["rank_sha256"])
            self.assertEqual(record["state_sha256"], original_generation["state_sha256"])
            self.assertEqual(record["completed_at"], COMPLETED_AT)
            self.assertEqual(record["ranked_at"], f.writer_request["observed_at"])
            self.assertEqual(record["rows"], original_rows)
            self.assertEqual(record["origin"], "derived")
            self.assertEqual(record["boundary"], self.live.DELIVERY_BOUNDARY)
            self.assertEqual(record["emitted_row_refs"], f.writer_request["emitted_row_refs"])
            self.assertEqual(record["non_claims"], list(self.live.NON_CLAIMS))
            self.assertEqual(bytes(sink.body), f.body)
            self.assertEqual(f.case.images(), source_before_output)
            inspected = self.writer.inspect(f)
            self.assertEqual(inspected["records"], [record])
            self.assertIs(inspected["complete"], True)
            self.assertEqual(inspected["pending"], [])
            record_images = self.writer.record_images(f)
            epoch_images = epoch_tests._tree(f.root)

            def captured(actual_fixture, actual_owner, result):
                self.assertIs(actual_fixture, f)
                self.assert_captured_record(f, actual_owner, result, inspected=inspected, record=record)

            # Only fixture seams change: the existing supplied clock callback
            # retains its real lease assertion and returns the post-output
            # declared time. The capture operation remains the actual source
            # front door; only its empty-history assertion helper is replaced
            # with the stronger nonempty observed-journal assertion above.
            forbidden = self.writer.forbidden("resident cycle attempted another output")
            with mock.patch.object(resident_tests.clock_tests, "SUCCESSOR_OBSERVED_AT", COMPLETED_AT), \
                    mock.patch.object(self.resident.capture, "assert_batch", side_effect=captured), \
                    mock.patch.object(self.writer.module, "deliver", forbidden), \
                    mock.patch.object(self.writer.journal, "hold_delivery_writer", forbidden), \
                    self.resident.instrument(f) as trace:
                status = trace.invoke(original_adoption["expected_adoption_sha256"])
            forbidden.assert_not_called()
            self.assert_completed_record(f, status, trace, record)
            self.assertEqual(trace.prepares, [original_adoption])
            self.assertEqual(trace.captures, [f.batch])
            self.assertEqual(trace.retained, [self.source.native_bytes(f.case.lib.__dict__, f.batch)])
            stages = trace.stages
            for earlier, later in (("prepare", "reserve"), ("reserve", "clock"),
                                   ("clock", "capture"), ("capture", "retain"),
                                   ("retain", "effects"), ("effects", "ack-pending")):
                self.assertLess(stages.index(earlier), stages.index(later))
            self.assertEqual(f.generation, original_generation)
            self.assertEqual(f.adopted, original_adoption)
            self.assertEqual(f.rows, original_rows)
            self.assertEqual(f.batch["delivery_input"]["parent_source_schema"], resident_tests.V3)
            self.assertEqual(f.batch["delivery_input"]["epoch_view"]["parent_generation"], original_generation)
            self.assertEqual(self.writer.inspect(f), inspected)
            self.assertEqual(self.writer.record_images(f), record_images)
            self.assertEqual(epoch_tests._tree(f.root), epoch_images)
            self.assertEqual(ack_tests._path_image(f.case.archive_path(f.retained)), parent_archive)


if __name__ == "__main__":
    unittest.main()
