"""Read back a complete index before retiring its original source pages.

Faults are injected in the real writer callback, not physical I/O failures.
The fixture uses real temporary corpus files and retained execution intent.
It does not establish protected authorization or crash durability.
"""

import json
from pathlib import Path
import unittest
from unittest import mock

from tests import test_consolidation_delivery_execution as execution


class ConsolidationIndexBarrier(unittest.TestCase):
    def setUp(self):
        self.fixture = execution.ConsolidationDeliveryExecution(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.claimed = self.fixture.stage()
        self.originals = {path: path.read_bytes() for path in self.fixture.sources}
        self.index_paths = []

    def assert_refused_with_sources(self, write):
        with mock.patch.object(self.lib, "atomic_write", write):
            with self.assertRaises(ValueError):
                self.fixture.execute()
        self.assertEqual({path: path.read_bytes() for path in self.originals}, self.originals)
        self.fixture.assert_retained_batch(self.claimed, "executing")
        self.assertTrue(self.fixture.epoch.exists(), "epoch effect remains explicit")
        self.assertTrue(self.index_paths, "fault reached a real index write")

    def faulty_writer(self, mode):
        original = self.lib.atomic_write
        root = Path(self.lib.CORPUS) / "event-index"

        def write(path, text, **kwargs):
            target = Path(path)
            if not target.is_relative_to(root):
                return original(path, text, **kwargs)
            self.index_paths.append(target)
            if mode == "missing":
                return None
            if mode == "malformed":
                return original(path, "not-json", **kwargs)
            if mode == "conflicting":
                entry = json.loads(text)
                entry["payload_sha256"] = "f" * 64
                text = self.lib._event_index_encoded(entry).decode("utf-8")
            result = original(path, text, **kwargs)
            if mode == "earlier-loss" and len(self.index_paths) == 2:
                self.index_paths[0].unlink()
            return result

        return write

    def test_missing_write_refuses_then_fresh_retry_finishes(self):
        self.assert_refused_with_sources(self.faulty_writer("missing"))
        epoch = self.fixture.epoch.read_bytes()
        self.assertEqual(self.fixture.execute()["phase"], "effects-returned")
        self.assertEqual(self.fixture.epoch.read_bytes(), epoch)
        self.assertTrue(all(not path.exists() for path in self.originals))

    def test_malformed_write_refuses_before_source_retirement(self):
        self.assert_refused_with_sources(self.faulty_writer("malformed"))

    def test_canonical_conflicting_write_refuses_before_source_retirement(self):
        self.assert_refused_with_sources(self.faulty_writer("conflicting"))

    def test_later_write_removing_earlier_entry_refuses_before_retirement(self):
        self.assert_refused_with_sources(self.faulty_writer("earlier-loss"))
        self.assertGreaterEqual(len(self.index_paths), 2)


if __name__ == "__main__":
    unittest.main()
