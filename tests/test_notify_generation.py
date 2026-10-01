#!/usr/bin/env python3
"""Notification directory-generation ingestion regressions."""

import importlib.util
import copy
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

    def _zero_filter(self):
        return self.sialib._notify_scan_candidate(None)["baseline_bits"]

    def test_baseline_is_silent_and_unchanged_generation_does_no_scan(self):
        self._write("alpha.json")
        self._write("bravo.json")
        cursors = {}

        self.assertEqual(self._finish_scan(cursors), [])
        self.assertIn("notify.generation", cursors)
        self.assertEqual(cursors["notify.baseline"], {
            "schema": "sia-notification-baseline-v1",
            "kind": "exact",
            "names": ["alpha.json", "bravo.json"],
        })
        self.assertNotIn("source.notify.page", cursors)

        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=AssertionError("unchanged generation rescanned")):
            self.assertEqual(self.sialib.sense_notify(cursors), [])

    def test_first_baseline_fence_precedes_directory_enumeration(self):
        self._write("alpha.json")
        trace = []
        bounded = self.sialib._bounded_source_entries

        def enumerate_after_fence(*args, **kwargs):
            trace.append("enumerate")
            return bounded(*args, **kwargs)

        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=enumerate_after_fence):
            self.sialib.sense_notify(
                {}, before_initial_baseline=lambda: trace.append("fence"))

        self.assertEqual(trace[0], "fence")
        self.assertIn("enumerate", trace)

    def test_absent_initial_directory_is_an_exact_empty_baseline(self):
        os.rmdir(self.history)
        cursors = {}
        trace = []

        self.assertEqual(self.sialib.sense_notify(
            cursors, before_initial_baseline=lambda: trace.append("fence")), [])
        self.assertEqual(trace, ["fence"])
        self.assertEqual(cursors, {
            "notify.baseline": {
                "schema": "sia-notification-baseline-v1",
                "kind": "exact", "names": [],
            },
            "notify.scan_mode": "empty-replay",
        })
        self.assertTrue(
            self.sialib._notify_cursor_checkpoint_safe(cursors))

        os.makedirs(self.history)
        self._write("first.json")
        replay = self._finish_scan(cursors)
        self.assertEqual(
            {event.summary for event in replay
             if event.kind == "notification"},
            {"fixture: first.json"})

    def test_crash_after_absence_before_cursor_save_stays_opaque(self):
        os.rmdir(self.history)
        memo = {}
        persisted_cursors = {}
        with tempfile.TemporaryDirectory() as state, \
                mock.patch.object(
                    self.sialib, "MEMO_PATH",
                    os.path.join(state, "memo.json")):
            trial = copy.deepcopy(persisted_cursors)
            self.sialib.sense_notify(
                trial, before_initial_baseline=lambda:
                self.sialib._mark_notify_baseline_attempt(memo))
            self.assertEqual(trial["notify.scan_mode"], "empty-replay")
            self.assertIsNotNone(
                self.sialib._pending_notify_baseline_attempt(memo))

            recovered = copy.deepcopy(persisted_cursors)
            self.sialib._recover_notify_baseline_attempt(memo, recovered)
            self.assertEqual(recovered["notify.baseline"], {
                "schema": "sia-notification-baseline-v1",
                "kind": "opaque", "cause": "baseline-unstable",
            })
            os.makedirs(self.history)
            self._write("first.json")
            replay = self._finish_scan(recovered)

        self.assertFalse(any(event.kind == "notification"
                             for event in replay))

    def test_crash_before_first_cursor_save_stays_permanently_opaque(self):
        self._write("alpha.json")
        memo = {}
        persisted_cursors = {}
        with tempfile.TemporaryDirectory() as state, \
                mock.patch.object(
                    self.sialib, "MEMO_PATH",
                    os.path.join(state, "memo.json")):
            trial = copy.deepcopy(persisted_cursors)
            self.sialib.sense_notify(
                trial, before_initial_baseline=lambda:
                self.sialib._mark_notify_baseline_attempt(memo))
            self.assertIsNotNone(
                self.sialib._pending_notify_baseline_attempt(memo))

            # Simulate death before the trial cursor image is published.
            os.unlink(os.path.join(self.history, "alpha.json"))
            recovered = copy.deepcopy(persisted_cursors)
            self.sialib._recover_notify_baseline_attempt(memo, recovered)
            self.assertEqual(recovered["notify.baseline"], {
                "schema": "sia-notification-baseline-v1",
                "kind": "opaque", "cause": "baseline-unstable",
            })
            self.assertEqual(recovered["notify.scan_mode"], "replay")
            self._finish_scan(recovered)
            self.assertTrue(
                self.sialib._notify_cursor_checkpoint_safe(recovered))
            self.sialib._clear_notify_baseline_attempt(memo)

            self._write("alpha.json")
            replay = self._finish_scan(recovered)

        self.assertFalse(any(event.kind == "notification"
                             for event in replay))
        self.assertIsNone(
            self.sialib._pending_notify_baseline_attempt(memo))

    def test_interrupted_baseline_recovery_refuses_mixed_cursor_state(self):
        memo = {
            self.sialib.NOTIFY_BASELINE_ATTEMPT_KEY: {
                "v": 1, "id": "a" * 32,
                "started_at": "2026-08-30T12:00:00Z",
            },
        }
        with self.assertRaisesRegex(
                self.sialib.SourceReplayQuarantine, "cursor is ambiguous"):
            self.sialib._recover_notify_baseline_attempt(
                memo, {"notify.generation": {}})

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
        self.assertNotIn("fixture: zulu.json",
                         {event.summary for event in events})
        self.assertNotIn("notification:zulu.json",
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

    def test_in_progress_old_candidate_becomes_permanently_opaque(self):
        self._write("alpha.json")
        self._write("bravo.json")
        cursors = {}
        self.sialib.sense_notify(cursors)
        cursors["notify.scan"]["schema"] = \
            "sia-notification-directory-scan-v1"
        cursors["notify.scan"].pop("truncated")
        cursors["notify.scan"].pop("baseline_bits")

        events = self._finish_scan(cursors)

        self.assertFalse(any(event.kind == "notification"
                             for event in events))
        self.assertTrue(any(event.kind == "source-entry-refused"
                            for event in events))
        self.assertIn("notify.generation", cursors)
        self.assertNotIn("notify.scan", cursors)
        self.assertEqual(cursors["notify.baseline"], {
            "schema": "sia-notification-baseline-v1",
            "kind": "opaque",
            "cause": "baseline-unstable",
        })

    def test_legacy_high_water_migrates_to_permanent_opaque_boundary(self):
        self._write("zulu.json")
        self._write("alpha.json")
        cursors = {
            "notify.last": "zulu.json",
            "notify.seen": ["zulu.json"],
            "notify.cycle_max": "zulu.json",
        }

        events = self._finish_scan(cursors)

        self.assertFalse(any(event.kind == "notification"
                             for event in events))
        self.assertTrue(any(event.kind == "source-entry-refused"
                            for event in events))
        self.assertEqual(cursors["notify.baseline"], {
            "schema": "sia-notification-baseline-v1",
            "kind": "opaque",
            "cause": "legacy-ambiguous",
        })
        self.assertTrue(self.LEGACY_KEYS.isdisjoint(cursors))

    def test_existing_v2_generation_without_membership_stays_opaque(self):
        self._write("zulu.json")
        cursors = {}
        self.assertEqual(self._finish_scan(cursors), [])
        cursors.pop("notify.baseline")

        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=AssertionError("unchanged generation rescanned")):
            migrated = self.sialib.sense_notify(cursors)

        self.assertFalse(any(event.kind == "notification"
                             for event in migrated))
        self.assertTrue(any(event.kind == "source-entry-refused"
                            for event in migrated))
        self.assertEqual(cursors["notify.baseline"], {
            "schema": "sia-notification-baseline-v1",
            "kind": "opaque",
            "cause": "v2-migration",
        })

        os.unlink(os.path.join(self.history, "zulu.json"))
        self.assertFalse(any(
            event.kind == "notification"
            for event in self._finish_scan(cursors)))
        self._write("zulu.json")
        self._write("new.json")
        replay = self._finish_scan(cursors)
        self.assertFalse(any(event.kind == "notification"
                             for event in replay))

    def test_exact_baseline_suppresses_reappearance_but_admits_rename(self):
        self._write("baseline.json")
        cursors = {}
        self.assertEqual(self._finish_scan(cursors), [])

        os.unlink(os.path.join(self.history, "baseline.json"))
        self.assertFalse(any(
            event.kind == "notification"
            for event in self._finish_scan(cursors)))
        self._write("baseline.json")
        reappeared = self._finish_scan(cursors)
        self.assertFalse(any(event.kind == "notification"
                             for event in reappeared))

        os.rename(
            os.path.join(self.history, "baseline.json"),
            os.path.join(self.history, "renamed.json"))
        renamed = self._finish_scan(cursors)
        self.assertEqual(
            {event.summary for event in renamed
             if event.kind == "notification"},
            {"fixture: baseline.json"})
        self.assertEqual(
            {event.occurrence for event in renamed
             if event.kind == "notification"},
            {"notification:renamed.json"})

    def test_truncated_first_baseline_uses_one_sided_membership(self):
        for name, stamp in (
                ("old.json", 10),
                ("middle.json", 20),
                ("newest.json", 30)):
            self._write(name)
            os.utime(os.path.join(self.history, name), ns=(stamp, stamp))
        cursors = {}
        with mock.patch.object(
                self.sialib, "MAX_LEDGER_PENDING_RECORDS", 2):
            baseline_events = self._finish_scan(cursors)

        self.assertFalse(any(event.kind == "notification"
                             for event in baseline_events))
        self.assertTrue(any(event.kind == "source-truncated"
                            for event in baseline_events))
        baseline = copy.deepcopy(cursors["notify.baseline"])
        self.assertEqual(baseline["schema"],
                         "sia-notification-baseline-v1")
        self.assertEqual(baseline["kind"], "filter")
        self.assertEqual(len(baseline["bits"]),
                         len(self._zero_filter()))
        for name in ("old.json", "middle.json", "newest.json"):
            self.assertTrue(self.sialib._notify_filter_contains(
                baseline["bits"], name), name)

        os.unlink(os.path.join(self.history, "old.json"))
        os.unlink(os.path.join(self.history, "middle.json"))
        os.unlink(os.path.join(self.history, "newest.json"))
        with mock.patch.object(
                self.sialib, "MAX_LEDGER_PENDING_RECORDS", 2):
            revealed = self._finish_scan(cursors)
        self.assertFalse(any(event.kind == "notification"
                             for event in revealed))
        self.assertEqual(cursors["notify.baseline"], baseline)

        self._write("old.json")
        candidates = (
            "genuinely-new.json", "fresh-notification.json",
            "another-new-notification.json", "filter-negative.json",
        )
        negatives = [
            name for name in candidates
            if not self.sialib._notify_filter_contains(
                baseline["bits"], name)]
        self.assertTrue(negatives)
        new_name = negatives[0]
        self._write(new_name)
        with mock.patch.object(
                self.sialib, "MAX_LEDGER_PENDING_RECORDS", 2):
            added = self._finish_scan(cursors)
        self.assertEqual(
            {event.summary for event in added
             if event.kind == "notification"},
            {f"fixture: {new_name}"})
        self.assertEqual(cursors["notify.baseline"], baseline)

    def test_saturated_filter_safely_suppresses_every_name(self):
        for name in ("old.json", "middle.json", "newest.json"):
            self._write(name)
        cursors = {}
        with mock.patch.object(
                self.sialib, "MAX_LEDGER_PENDING_RECORDS", 2):
            self._finish_scan(cursors)
        cursors["notify.baseline"]["bits"] = (
            "f" * len(self._zero_filter()))

        self._write("blocked-by-saturated-filter.json")
        with mock.patch.object(
                self.sialib, "MAX_LEDGER_PENDING_RECORDS", 2):
            events = self._finish_scan(cursors)

        self.assertFalse(any(event.kind == "notification"
                             for event in events))

    def test_initial_page_reset_makes_membership_permanently_opaque(self):
        self._write("alpha.json")
        self._write("bravo.json")
        cursors = {}
        self.sialib.sense_notify(cursors)
        self._write("charlie.json")

        events = self.sialib.sense_notify(cursors)
        events.extend(self._finish_scan(cursors))

        self.assertFalse(any(event.kind == "notification"
                             for event in events))
        self.assertEqual(cursors["notify.baseline"], {
            "schema": "sia-notification-baseline-v1",
            "kind": "opaque",
            "cause": "baseline-unstable",
        })

    def test_initial_source_loss_makes_membership_permanently_opaque(self):
        self._write("alpha.json")
        self._write("bravo.json")
        cursors = {}
        self.sialib.sense_notify(cursors)
        saved = next(iter(cursors["notify.scan"]["sources"]))["name"]
        moved = self.history + ".moved"
        os.rename(self.history, moved)

        events = self.sialib.sense_notify(cursors)

        self.assertTrue(any(event.kind == "source-entry-refused"
                            for event in events))
        self.assertEqual(cursors["notify.baseline"]["kind"], "opaque")
        os.mkdir(self.history)
        self._write(saved)
        replay = self._finish_scan(cursors)
        self.assertFalse(any(event.kind == "notification"
                             for event in replay))

    def test_initial_record_refusal_makes_membership_permanently_opaque(self):
        self._write("alpha.json")
        with open(os.path.join(self.history, "broken.json"), "w") as stream:
            stream.write("not-json")
        cursors = {}

        events = self._finish_scan(cursors)

        self.assertFalse(any(event.kind == "notification"
                             for event in events))
        self.assertEqual(cursors["notify.baseline"], {
            "schema": "sia-notification-baseline-v1",
            "kind": "opaque",
            "cause": "baseline-unstable",
        })
        self.assertEqual(cursors["notify.scan_mode"], "replay")

    def test_initial_nonregular_name_makes_membership_permanently_opaque(self):
        for kind in ("fifo", "symlink", "directory"):
            with self.subTest(kind=kind):
                name = f"broken-{kind}.json"
                broken = os.path.join(self.history, name)
                target = os.path.join(
                    self.home.name, f"symlink-target-{kind}.json")
                if kind == "fifo":
                    os.mkfifo(broken)
                elif kind == "symlink":
                    with open(target, "w", encoding="utf-8") as stream:
                        json.dump({"app": "outside", "summary": "target"},
                                  stream)
                    os.symlink(target, broken)
                else:
                    os.mkdir(broken)
                cursors = {}
                initial = self._finish_scan(cursors)
                if kind == "directory":
                    os.rmdir(broken)
                else:
                    os.unlink(broken)
                self._write(name)
                replay = self._finish_scan(cursors)
                observed = (
                    any(event.kind == "source-entry-refused"
                        for event in initial),
                    cursors["notify.baseline"]["kind"],
                    any(event.kind == "notification" for event in replay),
                )
                self.assertEqual(observed, (True, "opaque", False))
                os.unlink(broken)
                if os.path.exists(target):
                    os.unlink(target)

    def test_single_page_initial_refusal_keeps_replay_debt_after_repair(self):
        broken = os.path.join(self.history, "broken.json")
        with open(broken, "w") as stream:
            stream.write("not-json")
        cursors = {}
        with mock.patch.object(
                self.sialib, "MAX_SOURCE_SCAN_ENTRIES", 2):
            refused = self.sialib.sense_notify(cursors)

        self.assertTrue(any(event.kind == "source-entry-refused"
                            for event in refused))
        self.assertEqual(cursors["notify.baseline"]["kind"], "opaque")
        self.assertEqual(cursors["notify.scan_mode"], "replay")
        self.assertNotIn("notify.generation", cursors)

        self._write("broken.json")
        original = self.sialib._read_bounded_source_json
        with mock.patch.object(
                self.sialib, "MAX_SOURCE_SCAN_ENTRIES", 2), \
                mock.patch.object(
                    self.sialib, "_read_bounded_source_json",
                    wraps=original) as reader:
            replay = self.sialib.sense_notify(cursors)

        self.assertTrue(reader.called)
        self.assertFalse(any(event.kind == "notification"
                             for event in replay))
        self.assertIn("notify.generation", cursors)

    def test_malformed_baseline_refuses_without_cursor_mutation(self):
        self._write("baseline.json")
        base = {}
        self.assertEqual(self._finish_scan(base), [])
        malformed = (
            {"schema": "sia-notification-baseline-v1",
             "kind": "exact", "names": ["zulu", "alpha"]},
            {"schema": "sia-notification-baseline-v1",
             "kind": "exact", "names": ["same", "same"]},
            {"schema": "sia-notification-baseline-v1",
             "kind": "exact", "names": ["\ud800"]},
            {"schema": "sia-notification-baseline-v1",
             "kind": "exact", "names": [], "extra": False},
            {"schema": "sia-notification-baseline-v1",
             "kind": "filter",
             "bits": self._zero_filter()},
            {"schema": "sia-notification-baseline-v1",
             "kind": "filter",
             "bits": "F" * len(self._zero_filter())},
            {"schema": "sia-notification-baseline-v1",
             "kind": "filter",
             "bits": ("f" * len(self._zero_filter()))[:-1]},
            {"schema": "sia-notification-baseline-v1",
             "kind": "filter",
             "bits": "f" * len(self._zero_filter()),
             "extra": False},
            {"schema": "sia-notification-baseline-v1",
             "kind": "opaque", "cause": "invented"},
            {"schema": "sia-notification-baseline-v1",
             "kind": "opaque", "cause": "v2-migration",
             "names": []},
        )
        for candidate in malformed:
            cursors = copy.deepcopy(base)
            cursors["notify.baseline"] = candidate
            before = copy.deepcopy(cursors)
            with self.subTest(candidate=candidate), self.assertRaisesRegex(
                    ValueError, "notification baseline cursor is invalid"):
                self.sialib.sense_notify(cursors)
            self.assertEqual(cursors, before)

    def test_explicit_null_and_unbound_membership_refuse_atomically(self):
        cases = (
            {"notify.generation": None},
            {"notify.baseline": None},
            {"notify.baseline": {
                "schema": "sia-notification-baseline-v1",
                "kind": "exact", "names": ["old.json"]}},
            {"notify.baseline": {
                "schema": "sia-notification-baseline-v1",
                "kind": "filter",
                "bits": "f" * len(self._zero_filter())}},
        )
        for cursors in cases:
            before = copy.deepcopy(cursors)
            with self.subTest(cursors=cursors), self.assertRaises(ValueError):
                self.sialib.sense_notify(cursors)
            self.assertEqual(cursors, before)

    def test_malformed_filter_accumulator_refuses_atomically(self):
        self._write("alpha.json")
        self._write("bravo.json")
        cursors = {}
        self.sialib.sense_notify(cursors)
        cursors["notify.scan"]["baseline_bits"] = "not-hex"
        before = copy.deepcopy(cursors)

        with self.assertRaisesRegex(
                ValueError, "notification directory scan cursor is invalid"):
            self.sialib.sense_notify(cursors)

        self.assertEqual(cursors, before)

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

    def test_over_capacity_history_commits_a_bounded_newest_generation(self):
        self._write("baseline.json")
        cursors = {}
        self.assertEqual(self._finish_scan(cursors), [])
        os.unlink(os.path.join(self.history, "baseline.json"))
        for name, stamp in (
                ("old.json", 10),
                ("middle.json", 20),
                ("newest.json", 30)):
            self._write(name)
            os.utime(os.path.join(self.history, name), ns=(stamp, stamp))

        with mock.patch.object(
                self.sialib, "MAX_LEDGER_PENDING_RECORDS", 2):
            events = self._finish_scan(cursors)

        summaries = {event.summary for event in events}
        self.assertIn("fixture: newest.json", summaries)
        self.assertIn("fixture: middle.json", summaries)
        self.assertNotIn("fixture: old.json", summaries)
        self.assertTrue(any(event.kind == "source-truncated"
                            for event in events))
        self.assertIn("notify.generation", cursors)
        self.assertNotIn("notify.scan_tainted", cursors)
        self.assertNotIn("notify.scan_mode", cursors)
        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=AssertionError("completed generation rescanned")):
            self.assertEqual(self.sialib.sense_notify(cursors), [])

    def test_ambiguous_notification_json_refuses_the_generation(self):
        self._write("baseline.json")
        cursors = {}
        self.assertEqual(self._finish_scan(cursors), [])
        completed = dict(cursors["notify.generation"])
        ambiguous = os.path.join(self.history, "ambiguous.json")
        with open(ambiguous, "w") as stream:
            stream.write(
                '{"app":"fixture","summary":"safe",'
                '"summary":"private"}')

        events = self._finish_scan(cursors)

        self.assertTrue(any(event.kind == "source-entry-refused"
                            for event in events))
        self.assertFalse(any(event.kind == "notification"
                             for event in events))
        self.assertNotIn("private", " ".join(
            event.summary for event in events))
        self.assertEqual(cursors["notify.generation"], completed)
        self.assertTrue(cursors["notify.scan_tainted"])

    def test_notification_schema_refuses_nontext_nonfinite_and_invalid_unicode(self):
        self._write("baseline.json")
        cursors = {}
        self.assertEqual(self._finish_scan(cursors), [])
        completed = dict(cursors["notify.generation"])
        candidate = os.path.join(self.history, "candidate.json")
        overbound = ("x" * self.sialib.MAX_CONFIG_TEXT_CHARS) + "x"
        cases = (
            '{"app":"fixture","summary":1e999}',
            '{"app":"fixture","summary":-1e999}',
            '{"app":"fixture","summary":{"private":"nested"}}',
            '{"app":{"private":"nested"},"summary":"safe"}',
            '{"app":"fixture","summary":"\\ud800"}',
            json.dumps({"app": "fixture", "summary": overbound}),
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with open(candidate, "w", encoding="utf-8") as stream:
                    stream.write(raw)

                events = self._finish_scan(cursors)

                self.assertTrue(any(event.kind == "source-entry-refused"
                                    for event in events))
                self.assertFalse(any(event.kind == "notification"
                                     for event in events))
                self.assertNotIn("private", " ".join(
                    event.summary for event in events))
                self.assertEqual(cursors["notify.generation"], completed)
                self.assertTrue(cursors["notify.scan_tainted"])

    def test_late_refusal_discards_earlier_page_notifications(self):
        self._write("baseline.json")
        cursors = {}
        self.assertEqual(self._finish_scan(cursors), [])
        completed = dict(cursors["notify.generation"])
        self._write("alpha.json")
        refused = os.path.join(self.history, "zulu.json")
        with open(refused, "w") as stream:
            stream.write('{"app":"fixture","summary":NaN}')

        first = self.sialib.sense_notify(cursors)
        events = first + self._finish_scan(cursors)

        self.assertFalse(any(event.kind == "notification"
                             for event in events))
        self.assertTrue(any(event.kind == "source-entry-refused"
                            for event in events))
        self.assertEqual(cursors["notify.generation"], completed)
        self.assertTrue(cursors["notify.scan_tainted"])

    def test_orphan_scan_candidate_is_discarded_before_generation_gate(self):
        self._write("baseline.json")
        cursors = {}
        self.assertEqual(self._finish_scan(cursors), [])
        cursors["notify.scan"] = {"laundered": "second authority"}

        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=AssertionError("unchanged generation rescanned")):
            self.assertEqual(self.sialib.sense_notify(cursors), [])

        self.assertNotIn("notify.scan", cursors)

    def test_source_record_json_rejects_nonfinite_numbers(self):
        path = os.path.join(self.history, "constant.json")
        for raw in (
                '{"app":"fixture","summary":NaN}',
                '{"app":"fixture","summary":Infinity}',
                '{"app":"fixture","summary":-Infinity}',
                '{"app":"fixture","summary":1e999}',
                '{"app":"fixture","summary":-1e999}'):
            with self.subTest(raw=raw):
                with open(path, "w") as stream:
                    stream.write(raw)
                with self.assertRaisesRegex(ValueError, "is malformed"):
                    self.sialib._read_bounded_source_json(
                        path, "notification fixture")

    def test_removed_high_water_model_has_no_second_cursor_authority(self):
        with open(os.path.join(BIN, "sialib.py"), encoding="utf-8") as stream:
            source = stream.read()
        for token in ("_SEEN_SET_CURSORS", "_compact_seen_set_cursors"):
            self.assertFalse(token in source, token)


if __name__ == "__main__":
    unittest.main()
