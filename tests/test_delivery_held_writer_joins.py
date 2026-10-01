"""Follow-up controls for held journal roster and returned receipts.

The source-independent journal fixture supplies real ranked plans, actual
temporary intent/attempt/completion files and a sink that receives bytes.
The foreign intent is first created by the real legacy reservation API in a
separate temporary journal. A publication hook then inserts those valid bytes
into the held journal alongside its intended publication. This is deliberate
fixture interference, not an authorized source delivery or adoption.

The completed-retry hook targets by object identity the actual retained
completion selected by the held writer, not an independently loaded fixture
lookalike. It delegates the real copy and alters only that detached return.
The durable receipt and retained snapshot object remain byte-exact. Rehashing
this negative copy must not substitute it for the actual historical receipt.

These are local construction controls, not source-writer authorization,
machine history, human receipt, JACKAL assurance or cognitive benchmarks.
Root alone executes these tests sequentially.
"""

import copy
import os
from pathlib import Path
import sys
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "bin"))

from tests import sia_test_home
from tests import test_delivery_held_writer as writer_tests
from tests import test_delivery_journal as journal_tests
from tests import test_event_page_plan as page_tests
from tests import test_live_loop as live_tests


class DeliveryHeldWriterJoins(unittest.TestCase):
    def setUp(self):
        self.fixture = writer_tests.DeliveryHeldWriter(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.journal = self.fixture.journal
        self.module = self.fixture.module

    def test_entry_identity_failure_closes_each_just_opened_directory(self):
        actual_open, actual_stat = os.open, os.fstat
        parts = Path(self.journal.directory).parts
        self.assertGreaterEqual(len(parts), 2)
        for target in (parts[0], parts[1]):
            with self.subTest(component=target):
                before = self.fixture.fds()
                selected = []

                def opened(path, *args, **kwargs):
                    descriptor = actual_open(path, *args, **kwargs)
                    if path == target and not selected:
                        selected.append(descriptor)
                    return descriptor

                def failed_identity(descriptor):
                    if descriptor in selected:
                        raise OSError("controlled directory identity failure")
                    return actual_stat(descriptor)

                try:
                    with mock.patch.object(
                            self.module, "os", page_tests._ModuleShim(
                                self.module.os, open=opened, fstat=failed_identity)):
                        with self.assertRaises(self.module.DeliveryJournalRefusal):
                            with self.fixture.hold():
                                self.fail("entry ignored its failed directory identity")
                finally:
                    after = self.fixture.fds()
                    # The RED must not leak its deliberately exposed descriptor
                    # into later tests. These are only this operation's opens.
                    for descriptor in selected:
                        try:
                            actual_stat(descriptor)
                        except OSError:
                            pass
                        else:
                            os.close(descriptor)
                self.assertTrue(selected, "control missed the requested directory open")
                self.assertEqual(after, before,
                                 "directory descriptor must be owned before fallible identity")

    def test_foreign_valid_intent_during_own_publication_is_not_own_progress(self):
        foreign_directory = self.journal._directory("foreign-intent-seed")
        foreign = self.journal._reserve(
            directory=str(foreign_directory), request_id=journal_tests.REQUEST_B)
        foreign_name = journal_tests.REQUEST_B + ".intent.json"
        foreign_source = foreign_directory / foreign_name
        foreign_raw = foreign_source.read_bytes()
        self.assertEqual(foreign_raw,
                         self.module._wire(foreign["intent"], self.journal.limits))
        actual_publish = self.module._publish
        own_name = journal_tests.REQUEST_A + ".intent.json"
        injected, own_wire = [], []

        def publish(directory, name, value, limits):
            result = actual_publish(directory, name, value, limits)
            if directory.path == str(self.journal.directory) and name == own_name:
                self.assertFalse(injected, "own intent publication unexpectedly repeated")
                own_wire.append(self.module._wire(value, limits))
                # Real publisher, same held descriptor and valid foreign
                # intent; no nested public writer attempts another flock.
                actual_publish(directory, foreign_name, foreign["intent"], limits)
                injected.append(foreign_name)
            return result

        descriptors = self.fixture.fds()
        with mock.patch.object(self.module, "_publish", side_effect=publish):
            with self.assertRaises(self.module.DeliveryJournalRefusal) as caught:
                with self.fixture.hold() as held:
                    self.fixture.reserve(held)
        self.assertEqual(caught.exception.output_state, "not-started")
        self.assertEqual(caught.exception.reason, "held-writer-unexpected-record-progress")
        self.assertEqual(injected, [foreign_name])
        self.fixture.closed(held)
        self.assertEqual(self.fixture.fds(), descriptors)
        self.assertEqual((self.journal.directory / own_name).read_bytes(), own_wire[0])
        self.assertEqual((self.journal.directory / foreign_name).read_bytes(), foreign_raw)
        self.assertEqual(foreign_source.read_bytes(), foreign_raw)
        # Reopening the actual journal admits both intent documents. The
        # refusal above must concern unexpected progress, not malformed data.
        inspected = self.journal._inspect()
        self.assertEqual(inspected["records"], [])
        self.assertEqual(inspected["pending"],
                         sorted([journal_tests.REQUEST_A, journal_tests.REQUEST_B]))
        self.assertIs(inspected["complete"], False)
        for request_id in (journal_tests.REQUEST_A, journal_tests.REQUEST_B):
            self.assertFalse(self.journal._path(request_id, "attempt").exists())
            self.assertFalse(self.journal._path(request_id, "complete").exists())

    def test_completed_retry_cannot_accept_a_substituted_first_copy(self):
        reservation = self.journal._reserve()
        sink = journal_tests.ByteSink()
        completed = self.journal._deliver(reservation, sink=sink)
        self.assertEqual(bytes(sink.body), self.journal.body)
        self.assertEqual(completed["boundary"], "write-all-and-flush-returned")
        durable_path = self.journal._path(journal_tests.REQUEST_A, "complete")
        durable_raw = durable_path.read_bytes()
        self.assertEqual(durable_raw, self.module._wire(completed, self.journal.limits))
        disk, descriptors = self.journal._snapshot(records_only=True), self.fixture.fds()
        actual_copy = copy.deepcopy
        substitutions, returned = [], []
        retry_sink = mock.Mock()
        retry_clock = mock.Mock(side_effect=AssertionError("completed retry sampled clock"))
        retained = None

        try:
            with self.assertRaises(self.module.DeliveryJournalRefusal) as caught:
                with self.fixture.hold() as held:
                    # This is the exact object the implementation will use
                    # as prior['complete']; equal fixture objects do not fire
                    # the hook, nor does any reservation or nested child copy.
                    retained = held._snapshot.records[journal_tests.REQUEST_A]["complete"]
                    self.assertEqual(self.module._wire(retained, self.journal.limits), durable_raw)

                    def substitute(value, memo=None):
                        detached = actual_copy(value, memo)
                        if value is retained:
                            self.assertFalse(substitutions, "retained completion first copy repeated")
                            self.assertIsNot(detached, retained)
                            self.assertIsNot(detached["record"], retained["record"])
                            # Negative return substitution only. No output
                            # with this altered record identity is claimed.
                            detached["record"]["id"] = journal_tests.REQUEST_B
                            detached["record"]["record_sha256"] = live_tests.own_digest(
                                detached["record"], "record_sha256")
                            detached["completion_sha256"] = live_tests.own_digest(
                                detached, "completion_sha256")
                            substitutions.append(self.module._wire(detached, self.journal.limits))
                        return detached

                    with mock.patch.object(self.module.copy, "deepcopy", side_effect=substitute):
                        returned.append(self.fixture.deliver(
                            held, reservation, sink=retry_sink, clock=retry_clock))
            self.assertEqual(caught.exception.output_state, "not-started")
            self.fixture.closed(held, reservation)
        finally:
            self.assertTrue(substitutions,
                            "control did not reach the actual retained completion first copy")
            self.assertNotEqual(substitutions[0], durable_raw)
            if returned:
                self.assertEqual(self.module._wire(returned[0], self.journal.limits), substitutions[0])
                self.assertNotEqual(self.module._wire(returned[0], self.journal.limits), durable_raw)
            if retained is not None:
                self.assertEqual(self.module._wire(retained, self.journal.limits), durable_raw)
            self.assertEqual(durable_path.read_bytes(), durable_raw)
            self.assertEqual(self.journal._snapshot(records_only=True), disk)
            retry_sink.write.assert_not_called()
            retry_sink.flush.assert_not_called()
            retry_clock.assert_not_called()
            self.assertEqual(self.fixture.fds(), descriptors)


if __name__ == "__main__":
    unittest.main()
