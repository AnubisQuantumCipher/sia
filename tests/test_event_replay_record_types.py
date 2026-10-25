"""Malformed replay collections must refuse before hashing or reconstruction."""

import copy
import datetime
import importlib
import os
import unittest
from unittest import mock

from tests import sia_test_home
from tests import test_controller_source_idle as idle_tests


class UnadmittedElement:
    def __hash__(self):
        raise AssertionError("unadmitted element was hashed")

    def __lt__(self, other):
        raise AssertionError("unadmitted element was compared")


class UnreadList(list):
    def __iter__(self):
        raise AssertionError("over-capacity collection was traversed")


class EventReplayRecordTypes(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.path.expanduser("~"), sia_test_home.ISOLATED_HOME)
        self.lib = importlib.import_module("sialib")
        event = self.lib.Event(
            "org", datetime.datetime(2026, 1, 5, tzinfo=datetime.timezone.utc),
            "observation", "Recorded source evidence", [], [],
            occurrence="native:record-type-control")
        self.record = self.lib._event_replay_record(event)

    def assert_invalid_before_reconstruction(self, record):
        with mock.patch.object(self.lib, "_canonical_utc_timestamp") as timestamp, \
                mock.patch.object(self.lib, "Event") as event, \
                mock.patch.object(self.lib, "event_memory_identity") as identity, \
                mock.patch.object(self.lib, "event_semantic_identity") as semantic:
            with self.assertRaises(ValueError) as caught:
                self.lib._event_from_replay_record(record)
        self.assertIs(type(caught.exception), ValueError)
        self.assertEqual(str(caught.exception), "event replay record is invalid")
        timestamp.assert_not_called()
        event.assert_not_called()
        identity.assert_not_called()
        semantic.assert_not_called()

    def test_json_nonstring_elements_refuse_before_reconstruction(self):
        for field in ("links", "tags"):
            for value in ([], {}, 7, True, None):
                for values in ([value], ["first", value]):
                    with self.subTest(field=field, values=values):
                        record = copy.deepcopy(self.record)
                        record[field] = values
                        before = copy.deepcopy(record)
                        self.assert_invalid_before_reconstruction(record)
                        self.assertEqual(record, before)

    def test_unadmitted_python_element_is_not_hashed_or_compared(self):
        for field in ("links", "tags"):
            with self.subTest(field=field):
                record = dict(self.record, **{field: ["first", UnadmittedElement()]})
                self.assert_invalid_before_reconstruction(record)

    def test_count_limit_precedes_element_iteration(self):
        for field in ("links", "tags"):
            with self.subTest(field=field), \
                    mock.patch.object(self.lib, "MAX_LEDGER_PENDING_RECORDS", 1):
                record = dict(self.record, **{field: UnreadList([None, None])})
                self.assert_invalid_before_reconstruction(record)

    def test_nonlist_duplicate_and_unsorted_values_still_refuse(self):
        for field in ("links", "tags"):
            for values in (None, {}, ("a",), ["a", "a"], ["b", "a"]):
                with self.subTest(field=field, values=values):
                    record = dict(self.record, **{field: values})
                    self.assert_invalid_before_reconstruction(record)

    def test_valid_records_preserve_identity_and_round_trip(self):
        for links, tags in (([], []), (["events/a", "events/b"], ["a", "b"])):
            with self.subTest(links=links, tags=tags):
                event = self.lib.Event(
                    "org", datetime.datetime(2026, 1, 5, tzinfo=datetime.timezone.utc),
                    "observation", "Recorded source evidence", links, tags,
                    occurrence="native:record-type-control")
                record = self.lib._event_replay_record(event)
                before = copy.deepcopy(record)
                restored = self.lib._event_from_replay_record(record)
                self.assertEqual(self.lib._event_replay_record(restored), before)
                self.assertEqual(record, before)

    def test_full_source_batch_preserves_closed_outer_reason(self):
        fixture = idle_tests.ControllerSourceIdle(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        source = importlib.import_module("siasourcebatch")
        with fixture.completed() as (case, retained, _commit, _status, _generation):
            owner = vars(case.lib)
            for field in ("links", "tags"):
                with self.subTest(field=field):
                    batch = copy.deepcopy(retained)
                    record = dict(self.record, **{field: [{}]})
                    batch["source_returns"]["runs"][0]["events"] = [record]
                    batch["batch_sha256"] = source.native_sha(owner, {
                        key: value for key, value in batch.items() if key != "batch_sha256"})
                    with self.assertRaises(source.SourceBatchRefusal) as caught:
                        source.validate_batch(owner, batch, batch["batch_sha256"])
                    self.assertEqual(caught.exception.reason, "source-event-record")
                    self.assertIs(type(caught.exception.__context__), ValueError)
                    self.assertEqual(str(caught.exception.__context__),
                                     "event replay record is invalid")


if __name__ == "__main__":
    unittest.main()
