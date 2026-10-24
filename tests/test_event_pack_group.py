"""Bounded group operation; not trace-equivalence to repeated singleton calls."""

import json
import unittest
from unittest import mock

from tests import test_event_pack_reader as fixtures


class PackedEventGroup(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CapturedEventPackTests(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.fixture._alternate_roster(64)
        self.records = fixtures.siaeventpack.decode(
            self.fixture.pack.read_bytes(), "org", self.fixture.event_id[:3])
        self.identifiers = tuple(key.decode("ascii") for key, _raw in self.records)

    def _read(self, identifiers=None, capture=None):
        capture = self.fixture._capture() if capture is None else capture
        result = fixtures.reader.read_group_captured(
            self.lib.__dict__, "org",
            self.identifiers if identifiers is None else identifiers, capture)
        capture.current()
        return result

    def test_complete_group_matches_exact_records_and_freshly_revalidates(self):
        expected = {key.decode("ascii"): json.loads(raw) for key, raw in self.records}
        capture = self.fixture._capture()
        with mock.patch.object(self.lib, "_read_epoch_state",
                               wraps=self.lib._read_epoch_state) as epoch:
            for _ in range(2):
                epoch.reset_mock()
                self.assertEqual(self._read(capture=capture), expected)
                self.assertEqual(epoch.call_count, len(self.records))

    def test_invalid_request_refuses_before_capture(self):
        first, second = self.identifiers[:2]
        invalid = ((), list(self.identifiers), (first, first), (second, first),
                   (None,), ("../bad",), self.identifiers + (self.fixture.event_id,),
                   tuple(sorted((first, "f" * 64))))
        capture = mock.Mock()
        for identifiers in invalid:
            with self.subTest(identifiers=identifiers), self.assertRaises(ValueError):
                fixtures.reader.read_group_captured(
                    self.lib.__dict__, "org", identifiers, capture)
        capture.read_file.assert_not_called()

    def test_singleton_duplicate_keeps_pack_then_legacy_validation(self):
        self.fixture._write_pack()
        original = self.lib._validate_event_index_raw
        calls = []

        def validate(raw, organ, identifier, **kwargs):
            calls.append(raw)
            if len(calls) > 1:
                raise ValueError("fresh duplicate legacy refusal")
            return original(raw, organ, identifier, **kwargs)

        with mock.patch.object(self.lib, "_validate_event_index_raw", validate):
            with self.assertRaisesRegex(ValueError, "fresh duplicate legacy refusal"):
                self.fixture._read()
        self.assertEqual(calls, [self.fixture.raw, self.fixture.raw])

    def test_partial_result_is_not_returned_after_later_refusal(self):
        original = self.lib._validate_event_index_raw

        def validate(raw, organ, identifier, **kwargs):
            if identifier == self.identifiers[-1]:
                raise ValueError("last entry refusal")
            return original(raw, organ, identifier, **kwargs)

        with mock.patch.object(self.lib, "_validate_event_index_raw", validate):
            with self.assertRaisesRegex(ValueError, "last entry refusal"):
                self._read()

    def test_policy_change_during_group_refuses(self):
        original = self.lib._read_epoch_state
        limit = self.lib.MAX_EVENT_INDEX_BYTES

        def epoch(slug, **kwargs):
            self.lib.MAX_EVENT_INDEX_BYTES = limit + 1
            return original(slug, **kwargs)

        with mock.patch.object(self.lib, "MAX_EVENT_INDEX_BYTES", limit), \
                mock.patch.object(self.lib, "_read_epoch_state", epoch):
            with self.assertRaisesRegex(ValueError, "policy changed during group"):
                self._read()


if __name__ == "__main__":
    unittest.main()
