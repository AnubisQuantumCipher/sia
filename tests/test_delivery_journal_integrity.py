"""Narrow delivery-journal integrity REDs after the initial green gate.

Compose the frozen synthetic fixture without inheriting its tests. The
retained engine score is the existing fixture's float, not a new arithmetic
oracle. Changing it to a Boolean must not preserve canonical source identity,
even though ordinary Python dictionary equality considers those values equal.

The final-copy controls replace an authoritative named file only while the
public result is being detached, after earlier publication/readback. They do
not execute a real CLI, use a live stream, or establish historical delivery.
Root alone executes these tests. The original journal suite remains unchanged.
"""

import copy
import os
import unittest
from unittest import mock

from tests import test_delivery_journal as journal_tests
from tests import test_live_loop as live_tests


class DeliveryJournalIntegrity(unittest.TestCase):
    def setUp(self):
        self.fixture = journal_tests.DeliveryJournal(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.module = self.fixture.module

    def _completed(self):
        reservation = self.fixture._reserve()
        completion = self.fixture._deliver(reservation)
        return reservation, completion

    def _changed_score(self, completion):
        changed = copy.deepcopy(completion)
        row = changed["record"]["rows"][0]["row"]
        self.assertIs(type(row["score"]), float)
        self.assertEqual(row["score"], 1.0)
        row["score"] = True
        self.assertNotEqual(live_tests.canonical(changed), live_tests.canonical(completion))
        return changed

    def _late_copy(self, schema, kind):
        """Patch only the final envelope copy, after its named leaf exists."""
        original = copy.deepcopy
        changes = []

        def detach_then_replace(value, *args, **kwargs):
            detached = original(value, *args, **kwargs)
            target = self.fixture._path(journal_tests.REQUEST_A, kind)
            if not changes and type(value) is dict and value.get("schema") == schema and target.exists():
                before = target.read_bytes()
                retained = self.fixture._disk(journal_tests.REQUEST_A, kind)
                if kind == "intent":
                    self.assertEqual(retained["consumer"], "cli.ask")
                    retained["consumer"] = "cli.recall"
                else:
                    self.assertEqual(retained["boundary"], "write-all-and-flush-returned")
                    retained["boundary"] = "synthetic-replacement-after-final-readback"
                replacement = self.fixture.root / "late-replacement.json"
                self.fixture._write_fixture(replacement, retained)
                self.assertNotEqual(replacement.read_bytes(), before)
                os.replace(replacement, target)
                changes.append(target)
            return detached

        return mock.patch.object(copy, "deepcopy", side_effect=detach_then_replace), changes

    def test_control_returns_original_canonical_record_and_keeps_pure_nonclaims(self):
        _reservation, completion = self._completed()
        result = self.fixture._inspect()
        self.assertEqual(live_tests.canonical(result["records"]), live_tests.canonical([completion["record"]]))
        self.assertEqual(result["records"][0]["non_claims"], live_tests.NON_CLAIMS)
        self.assertIs(type(result["records"][0]["rows"][0]["row"]["score"]), float)

    def test_stale_hashes_cannot_hide_boolean_for_float_source_substitution(self):
        _reservation, completion = self._completed()
        changed = self._changed_score(completion)
        # This is the exact ordinary-equality trap under review. Both retained
        # hashes stay unchanged while the canonical source bytes differ.
        self.assertEqual(changed, completion)
        self.assertEqual(changed["record"]["record_sha256"], completion["record"]["record_sha256"])
        self.assertEqual(changed["completion_sha256"], completion["completion_sha256"])
        self.assertNotEqual(changed["record"]["record_sha256"],
                            live_tests.own_digest(changed["record"], "record_sha256"))
        self.fixture._write_fixture(self.fixture._path(journal_tests.REQUEST_A, "complete"), changed)
        self.fixture._refusal(self.fixture._inspect, "not-started")

    def test_rehashing_both_changed_envelopes_does_not_authorize_source_substitution(self):
        _reservation, completion = self._completed()
        changed = self._changed_score(completion)
        changed["record"]["record_sha256"] = live_tests.own_digest(changed["record"], "record_sha256")
        changed["completion_sha256"] = live_tests.own_digest(changed, "completion_sha256")
        self.fixture._write_fixture(self.fixture._path(journal_tests.REQUEST_A, "complete"), changed)
        self.fixture._refusal(self.fixture._inspect, "not-started")

    def test_reservation_final_copy_rechecks_named_intent_before_return(self):
        patch, changed = self._late_copy("sia-live-delivery-reservation-v1", "intent")
        with patch:
            self.fixture._refusal(self.fixture._reserve, "not-started")
        self.assertTrue(changed, "control must reach the final reservation copy")
        self.assertFalse(self.fixture._path(journal_tests.REQUEST_A, "attempt").exists())
        self.assertFalse(self.fixture._path(journal_tests.REQUEST_A, "complete").exists())

    def test_completion_final_copy_rechecks_named_record_after_output(self):
        reservation = self.fixture._reserve()
        sink = journal_tests.ByteSink()
        patch, changed = self._late_copy("sia-live-delivery-completion-v1", "complete")
        with patch:
            self.fixture._refusal(lambda: self.fixture._deliver(reservation, sink=sink), "completed-unrecorded")
        self.assertTrue(changed, "control must reach the final completion copy")
        self.assertEqual(bytes(sink.body), self.fixture.body)
        self.assertEqual(sink.events[-1], "flush")
        self.assertTrue(self.fixture._path(journal_tests.REQUEST_A, "attempt").exists())
        self.assertTrue(self.fixture._path(journal_tests.REQUEST_A, "complete").exists())

    def test_inspection_final_copy_rechecks_named_records_without_mutating_them_itself(self):
        self._completed()
        patch, changed = self._late_copy("sia-live-delivery-journal-v1", "complete")
        with patch:
            self.fixture._refusal(self.fixture._inspect, "not-started")
        self.assertTrue(changed, "control must reach the final inspection copy")
        self.assertTrue(self.fixture._path(journal_tests.REQUEST_A, "complete").exists())

    def test_completed_retry_final_copy_rechecks_record_without_reemitting(self):
        reservation, _completion = self._completed()
        sink = journal_tests.ByteSink()
        clock = mock.Mock(side_effect=AssertionError("completed retry must not read a new clock"))
        patch, changed = self._late_copy("sia-live-delivery-completion-v1", "complete")
        with patch:
            # This invocation has not emitted anything. It must refuse the
            # changed retained authority, not return a cached success packet.
            self.fixture._refusal(lambda: self.fixture._deliver(reservation, sink=sink, clock=clock), "not-started")
        self.assertTrue(changed, "control must reach the retained completion copy")
        self.assertFalse(sink.events)
        clock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
