"""Do not downgrade output phase after a real completed journal retry returns.

A genuine source-v3 writer first emits and records its output. On an exact
completed retry, the real held journal returns that actual retained completion
before this test changes a selected owner operation. No current() exception
or successful source/journal result is supplied by a mock. The later source
wrapper refusal must remain completed-unrecorded, not claim not-started from
a fresh retry handle. The actual complete record remains unchanged and the
retry may never emit or sample another output clock.

This is local refusal bookkeeping, not human receipt or live CLI deployment.
Root alone executes tests sequentially. Fixture classes are module-qualified
composition only and are not rediscovered by unittest.
"""

import copy
import unittest
from unittest import mock

from tests import test_controller_delivery_writer as writer_tests
from tests import test_delivery_journal as journal_tests


class ControllerDeliveryWriterCompletedPhase(unittest.TestCase):
    def setUp(self):
        self.fixture = writer_tests.ControllerDeliveryWriter(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()

    def test_owner_drift_after_actual_completed_retry_return_cannot_downgrade_phase(self):
        fixture = self.fixture
        with fixture.completed() as f:
            sink = journal_tests.ByteSink()
            clock = mock.Mock(return_value=writer_tests.COMPLETED_AT)
            with fixture.writer_owner(f) as owner, fixture.boundary(f, owner):
                completed = fixture.call(f, owner, sink=sink, clock=clock)
            self.assertEqual(completed["status"], "service-output-completed")
            self.assertEqual(completed["boundary"], "write-all-and-flush-returned")
            self.assertEqual(sink.events, ["write", "flush"])
            self.assertEqual(bytes(sink.body), f.body)
            clock.assert_called_once()
            completion_path = f.records / (journal_tests.REQUEST_A + ".complete.json")
            completion_raw = completion_path.read_bytes()
            records = fixture.record_images(f)
            inspection = fixture.inspect(f)
            authority = f.case.images()
            self.assertIs(inspection["complete"], True)
            self.assertEqual(inspection["pending"], [])
            self.assertEqual(inspection["records"], [completed["record"]])

            retry_sink = mock.Mock()
            retry_clock = fixture.forbidden("completed retry sampled another completion clock")
            replacement = fixture.forbidden("changed owner operation was invoked after completion")
            returned = []
            actual_delivery = fixture.journal._HeldDeliveryWriter.deliver
            with fixture.writer_owner(f) as owner:
                original_operation = owner._canonical_utc_timestamp

                def completed_then_change_owner(held, **kwargs):
                    result = actual_delivery(held, **kwargs)
                    self.assertEqual(result, completed)
                    self.assertEqual(completion_path.read_bytes(), completion_raw)
                    returned.append(copy.deepcopy(result))
                    # The actual held writer has already returned a genuine
                    # completed record. The source wrapper must retain that
                    # phase even if subsequent held validation refuses.
                    owner._canonical_utc_timestamp = replacement
                    return result

                try:
                    with fixture.boundary(f, owner), \
                            mock.patch.object(fixture.journal._HeldDeliveryWriter,
                                              "deliver", completed_then_change_owner), \
                            self.assertRaises(fixture.module.ControllerDeliveryWriterRefusal) as caught:
                        fixture.call(f, owner, sink=retry_sink, clock=retry_clock)
                finally:
                    # Restore only the deliberate in-memory owner identity.
                    # No source/journal state is rewritten or repaired.
                    owner._canonical_utc_timestamp = original_operation

            self.assertEqual(returned, [completed])
            self.assertEqual(caught.exception.output_state, "completed-unrecorded")
            self.assertEqual(caught.exception.non_claims, list(fixture.module.NON_CLAIMS))
            self.assertRegex(caught.exception.reason, r"\A[a-z][a-z0-9-]*\Z")
            retry_sink.write.assert_not_called()
            retry_sink.flush.assert_not_called()
            retry_clock.assert_not_called()
            replacement.assert_not_called()
            self.assertEqual(completion_path.read_bytes(), completion_raw)
            self.assertEqual(fixture.record_images(f), records)
            self.assertEqual(fixture.inspect(f), inspection)
            self.assertEqual(f.case.images(), authority)


if __name__ == "__main__":
    unittest.main()
