#!/usr/bin/env python3
"""Notification directory-generation ingestion regressions."""

import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NotificationGenerationScan(unittest.TestCase):
    """A changed directory restarts a bounded scan without lexical loss."""

    PAGE_BOUND = 1
    LEGACY_KEYS = {
        "notify.last", "notify.pending", "notify.pending_complete",
        "notify.paginated", "notify.baselining", "notify.seen",
        "notify.cycle_max",
    }

    def setUp(self):
        self.sialib = _load(
            "sialib_notify_generation", os.path.join(BIN, "sialib.py"))
        self.guard = self.sialib.MAX_SOURCE_SCAN_ENTRIES
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.history = os.path.join(
            self.home.name,
            ".local/state/omarchy/notifications/history")
        os.makedirs(self.history)
        old_home = self.sialib.HOME
        self.sialib.HOME = self.home.name
        self.addCleanup(setattr, self.sialib, "HOME", old_home)
        bound = mock.patch.object(
            self.sialib, "MAX_SOURCE_SCAN_ENTRIES", self.PAGE_BOUND)
        bound.start()
        self.addCleanup(bound.stop)

    def _write(self, name):
        with open(os.path.join(self.history, name), "w") as stream:
            json.dump({"app": "fixture", "summary": name}, stream)

    def _finish_scan(self, cursors):
        events = []
        for _attempt in range(self.guard):
            events.extend(self.sialib.sense_notify(cursors))
            if "source.notify.page" not in cursors:
                return events
        self.fail("notification generation scan did not reach EOF")

    def test_baseline_is_silent_and_unchanged_generation_does_no_scan(self):
        self._write("alpha.json")
        self._write("bravo.json")
        cursors = {}

        self.assertEqual(self._finish_scan(cursors), [])
        self.assertIn("notify.generation", cursors)
        self.assertNotIn("source.notify.page", cursors)

        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=AssertionError("unchanged generation rescanned")):
            self.assertEqual(self.sialib.sense_notify(cursors), [])

    def test_later_lexically_earlier_name_is_not_starved(self):
        self._write("zulu.json")
        cursors = {}
        self.assertEqual(self._finish_scan(cursors), [])

        self._write("alpha.json")
        events = self._finish_scan(cursors)

        self.assertIn("fixture: alpha.json",
                      {event.summary for event in events})
        self.assertIn("notification:alpha.json",
                      {event.occurrence for event in events})
        self.assertTrue(self.LEGACY_KEYS.isdisjoint(cursors))

    def test_generation_change_during_page_scan_restarts_at_the_root(self):
        self._write("zulu.json")
        cursors = {}
        self.assertEqual(self._finish_scan(cursors), [])

        self._write("middle.json")
        first_page = self.sialib.sense_notify(cursors)
        self.assertIn("source.notify.page", cursors)

        self._write("alpha.json")
        restarted_page = self.sialib.sense_notify(cursors)
        self.assertTrue(cursors["source.notify.page"]["reset"])
        remainder = self._finish_scan(cursors)

        summaries = {
            event.summary
            for event in first_page + restarted_page + remainder}
        self.assertIn("fixture: alpha.json", summaries)
        self.assertEqual(
            cursors["notify.generation"],
            self.sialib._source_tree_path_generation(self.history))

    def test_legacy_high_water_migrates_by_replay_not_silent_baseline(self):
        self._write("zulu.json")
        self._write("alpha.json")
        cursors = {
            "notify.last": "zulu.json",
            "notify.seen": ["zulu.json"],
            "notify.cycle_max": "zulu.json",
        }

        events = self._finish_scan(cursors)

        self.assertIn("fixture: alpha.json",
                      {event.summary for event in events})
        self.assertTrue(self.LEGACY_KEYS.isdisjoint(cursors))

    def test_durable_occurrence_identity_suppresses_rescan_replay(self):
        self._write("zulu.json")
        cursors = {}
        self.assertEqual(self._finish_scan(cursors), [])

        self._write("middle.json")
        first_generation = self._finish_scan(cursors)
        self.assertTrue(first_generation)

        with tempfile.TemporaryDirectory() as corpus, \
                mock.patch.object(self.sialib, "CORPUS", corpus):
            day = self.sialib.today()
            _pages, first_appended, _admitted = \
                self.sialib.update_day_page(
                    "notify", day, first_generation)
            self.assertEqual(first_appended, first_generation)

            self._write("alpha.json")
            replayed_generation = self._finish_scan(cursors)
            _pages, second_appended, _admitted = \
                self.sialib.update_day_page(
                    "notify", day, replayed_generation)

        self.assertEqual(
            {event.summary for event in second_appended},
            {"fixture: alpha.json"})

    def test_refused_generation_is_rescanned_after_in_place_repair(self):
        self._write("baseline.json")
        cursors = {}
        self.assertEqual(self._finish_scan(cursors), [])
        completed = dict(cursors["notify.generation"])

        broken = os.path.join(self.history, "repair.json")
        with open(broken, "w") as stream:
            stream.write("not-json")
        refused = self._finish_scan(cursors)

        self.assertTrue(any(event.kind == "source-entry-refused"
                            for event in refused))
        self.assertEqual(cursors["notify.generation"], completed)
        self.assertTrue(cursors["notify.scan_tainted"])

        self._write("repair.json")
        repaired = self._finish_scan(cursors)

        self.assertIn("fixture: repair.json",
                      {event.summary for event in repaired})
        self.assertNotIn("notify.scan_tainted", cursors)
        self.assertEqual(
            cursors["notify.generation"],
            self.sialib._source_tree_path_generation(self.history))

    def test_removed_high_water_model_has_no_second_cursor_authority(self):
        with open(os.path.join(BIN, "sialib.py"), encoding="utf-8") as stream:
            source = stream.read()
        for token in ("_SEEN_SET_CURSORS", "_compact_seen_set_cursors"):
            self.assertFalse(token in source, token)


if __name__ == "__main__":
    unittest.main()
