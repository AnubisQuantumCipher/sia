"""Late writer/epoch/corpus exit mutation after an actual journal completion.

One genuinely acknowledged source-v3 fixture produces a real output completion
through the writer front door. Subsequent exact completed retries execute the
actual held writer and source/epoch readers, but must never emit again. Exit
hooks change only in-memory test values after the corresponding REAL context
has exited. No completion, source authority or current() success is mocked.

The callback-free tail must refuse the changed response/request/owner basis
with conservative completed-unrecorded output state even though the actual
complete journal record remains available. That state is a refusal boundary,
not permission to resend output or a claim that the retained record is absent.
No deployed CLI, human receipt, cognition or held-out improvement is claimed.
Root alone executes this module sequentially; no fixture class is rediscovered.
"""

import contextlib
import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import test_controller_delivery_writer as writer_tests
from tests import test_delivery_journal as journal_tests


CASES = (
    ("journal", "detached"),
    ("epoch", "detached"),
    ("corpus", "detached"),
    ("epoch", "original-request"),
    ("corpus", "admitted-request"),
    ("corpus", "owner-operation"),
)


class ControllerDeliveryWriterExitTail(unittest.TestCase):
    def setUp(self):
        self.fixture = writer_tests.ControllerDeliveryWriter(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.module = self.fixture.module

    @contextlib.contextmanager
    def exit_mutation(self, f, owner, *, stage, target):
        module = self.module
        journal = self.fixture.journal
        epoch = self.fixture.capture.epoch_module
        trace = SimpleNamespace(requests=[], completed=None, detached=None,
                                delivered=[], exited=[], mutations=[], replacement=None)
        initialize = module._Request.__init__
        delivery = journal._HeldDeliveryWriter.deliver
        copy_value = module.copy.deepcopy
        hold_writer = journal.hold_delivery_writer
        hold_epoch = epoch.hold_epoch
        corpus_owner = owner.corpus_owner
        original_refs = list(f.writer_request["emitted_row_refs"])
        original_operation = owner._canonical_utc_timestamp

        def admitted(request, *args, **kwargs):
            initialize(request, *args, **kwargs)
            trace.requests.append(request)

        def actual_delivery(held, **kwargs):
            result = delivery(held, **kwargs)
            self.assertEqual(result["status"], "service-output-completed")
            self.assertEqual(result["boundary"], "write-all-and-flush-returned")
            self.assertEqual(result["non_claims"], list(journal.NON_CLAIMS))
            trace.completed = result
            trace.delivered.append(copy.deepcopy(result))
            return result

        def detach(value, *args, **kwargs):
            result = copy_value(value, *args, **kwargs)
            if value is trace.completed:
                self.assertIsNone(trace.detached, "writer detached completed result more than once")
                trace.detached = result
            return result

        def mutate(selected):
            if selected != stage:
                return
            self.assertEqual(trace.mutations, [])
            self.assertIsNotNone(trace.completed, "exit mutation preceded actual completion")
            self.assertIsNotNone(trace.detached, "exit mutation preceded final response copy")
            self.assertEqual(trace.delivered, [trace.completed])
            self.assertIsNot(trace.detached, trace.completed)
            self.assertTrue(trace.requests)
            request = trace.requests[-1]
            if target == "detached":
                trace.detached["boundary"] = "unadmitted-exit-replacement"
            elif target == "original-request":
                self.assertIs(request.arguments["emitted_row_refs"],
                              f.writer_request["emitted_row_refs"])
                f.writer_request["emitted_row_refs"].append("unadmitted-exit-row")
            elif target == "admitted-request":
                self.assertIsNot(request.admitted["emitted_row_refs"],
                                 f.writer_request["emitted_row_refs"])
                request.admitted["emitted_row_refs"].append("unadmitted-exit-row")
            elif target == "owner-operation":
                self.assertIs(request._tail_references["_canonical_utc_timestamp"],
                              original_operation)
                trace.replacement = self.fixture.forbidden("exit tail invoked replacement owner operation")
                owner._canonical_utc_timestamp = trace.replacement
            else:
                self.fail("unknown exit mutation target")
            trace.mutations.append((selected, target))

        @contextlib.contextmanager
        def writer_context(**kwargs):
            try:
                with hold_writer(**kwargs) as held:
                    yield held
            finally:
                trace.exited.append("journal")
            # This callback follows the actual descriptor/lock retirement,
            # not the body before the held writer's normal exit checks.
            mutate("journal")

        @contextlib.contextmanager
        def epoch_context(actual_owner, **kwargs):
            try:
                with hold_epoch(actual_owner, **kwargs) as held:
                    yield held
            finally:
                trace.exited.append("epoch")
            mutate("epoch")

        @contextlib.contextmanager
        def corpus_context():
            outer = owner._CORPUS_OWNER_FD.get() is None
            try:
                with corpus_owner() as descriptor:
                    yield descriptor
            finally:
                if outer:
                    trace.exited.append("corpus")
            if outer:
                self.assertIsNone(owner._CORPUS_OWNER_FD.get())
                mutate("corpus")

        # Replace this module's copy reference only. Other modules and the
        # actual held journal retain the ordinary stdlib copy implementation.
        isolated_copy = SimpleNamespace(deepcopy=detach)
        try:
            with mock.patch.object(module._Request, "__init__", admitted), \
                    mock.patch.object(journal._HeldDeliveryWriter, "deliver", actual_delivery), \
                    mock.patch.object(module, "copy", isolated_copy), \
                    mock.patch.object(journal, "hold_delivery_writer", writer_context), \
                    mock.patch.object(epoch, "hold_epoch", epoch_context), \
                    mock.patch.object(owner, "corpus_owner", corpus_context):
                yield trace
        finally:
            # Restore only the deliberately changed caller premises and
            # owner identity. No source or journal artifact is repaired.
            f.writer_request["emitted_row_refs"][:] = original_refs
            owner._canonical_utc_timestamp = original_operation
        if trace.replacement is not None:
            trace.replacement.assert_not_called()

    def test_actual_completed_retry_exit_mutations_refuse_without_reemission_or_record_loss(self):
        fixture = self.fixture
        with fixture.completed() as f:
            sink = journal_tests.ByteSink()

            def completion_clock():
                self.assertEqual(sink.events, ["write", "flush"])
                self.assertEqual(bytes(sink.body), f.body)
                return writer_tests.COMPLETED_AT

            clock = mock.Mock(side_effect=completion_clock)
            with fixture.writer_owner(f) as owner, fixture.boundary(f, owner):
                completed = fixture.call(f, owner, sink=sink, clock=clock)
            clock.assert_called_once()
            self.assertEqual(sink.events, ["write", "flush"])
            self.assertEqual(bytes(sink.body), f.body)
            self.assertEqual(completed["record"]["rows"], f.rows)
            self.assertEqual(completed["record"]["state_sha256"], f.generation["state_sha256"])
            path = f.records / (journal_tests.REQUEST_A + ".complete.json")
            completed_raw = path.read_bytes()
            records = fixture.record_images(f)
            authority = f.case.images()
            inspection = fixture.inspect(f)
            self.assertIs(inspection["complete"], True)
            self.assertEqual(inspection["pending"], [])
            self.assertEqual(inspection["records"], [completed["record"]])

            for stage, target in CASES:
                with self.subTest(stage=stage, target=target):
                    retry_sink = mock.Mock()
                    retry_clock = fixture.forbidden("completed retry sampled another output clock")
                    with fixture.writer_owner(f) as owner, fixture.boundary(f, owner), \
                            self.exit_mutation(f, owner, stage=stage, target=target) as trace, \
                            self.assertRaises(self.module.ControllerDeliveryWriterRefusal) as caught:
                        fixture.call(f, owner, sink=retry_sink, clock=retry_clock)
                    self.assertEqual(caught.exception.output_state, "completed-unrecorded")
                    self.assertEqual(caught.exception.non_claims, list(self.module.NON_CLAIMS))
                    self.assertRegex(caught.exception.reason, r"\A[a-z][a-z0-9-]*\Z")
                    self.assertEqual(trace.delivered, [completed])
                    self.assertEqual(trace.exited, ["journal", "epoch", "corpus"])
                    self.assertEqual(trace.mutations, [(stage, target)])
                    retry_sink.write.assert_not_called()
                    retry_sink.flush.assert_not_called()
                    retry_clock.assert_not_called()
                    self.assertEqual(path.read_bytes(), completed_raw)
                    self.assertEqual(fixture.record_images(f), records)
                    self.assertEqual(fixture.inspect(f), inspection)
                    self.assertEqual(f.case.images(), authority)

            # A clean exact retry still returns the original completion;
            # the previous wrapper refusal cannot authorize a second output.
            final_sink = mock.Mock()
            final_clock = fixture.forbidden("clean completed retry sampled another clock")
            with fixture.writer_owner(f) as owner, fixture.boundary(f, owner):
                returned = fixture.call(f, owner, sink=final_sink, clock=final_clock)
            self.assertEqual(returned, completed)
            final_sink.write.assert_not_called()
            final_sink.flush.assert_not_called()
            final_clock.assert_not_called()
            self.assertEqual(path.read_bytes(), completed_raw)
            self.assertEqual(fixture.record_images(f), records)
            self.assertEqual(fixture.inspect(f), inspection)
            self.assertEqual(f.case.images(), authority)


if __name__ == "__main__":
    unittest.main()
