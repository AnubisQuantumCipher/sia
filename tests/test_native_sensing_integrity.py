"""Native ledger intake keeps keeper authority bound through cursor admission."""

import copy
import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")


def _load_core(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(BIN, "sialib.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeKeeperAdmission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            prefix="sia-native-keeper-test-")
        self.addCleanup(self.temp.cleanup)
        self.core = _load_core("sialib_native_keeper_integrity")
        self.core.SHARE = self.temp.name
        self.core.BIN = BIN
        self.keeper = os.path.join(BIN, "sia-ledger")
        self.public = os.path.join(self.temp.name, "pub.hex")
        self._keeper("init", self.temp.name)
        self._keeper(
            "append", self.temp.name, "INSTALL:runtime", "fixture", "ready",
            hashlib.sha256(b"").hexdigest(), "0")

    def _keeper(self, *arguments):
        return subprocess.run(
            [sys.executable, self.keeper, *arguments], check=True,
            capture_output=True, text=True)

    def _change_public_key(self):
        with open(self.public, "w", encoding="ascii") as stream:
            stream.write("0" * 64 + "\n")

    def test_stable_signed_source_projects_and_replay_does_not_duplicate(self):
        cursor = {"sia.lines": 0}
        events = self.core.sense_sia(cursor)

        self.assertEqual([event.kind for event in events], ["install"])
        self.assertIn("INSTALL:runtime fixture ready", events[0].summary)
        self.assertEqual(self.core.sense_sia(cursor), [])

    def test_periodic_rows_yield_no_event_but_lifecycle_rows_still_project(self):
        # setUp already appended one INSTALL:runtime row. A pulse-period row
        # is the same kind of row bin/sialib.py appends every resident
        # cycle ("PULSE:ingest"); a following lifecycle row is the same
        # kind sia-brainstem appends at startup ("BOOT:brainstem").
        self._keeper(
            "append", self.temp.name, "PULSE:ingest", "43", "events",
            hashlib.sha256(b"").hexdigest(), "0")
        self._keeper(
            "append", self.temp.name, "BOOT:brainstem", "1.0.0",
            "pulse=60s", hashlib.sha256(b"").hexdigest(), "0")

        cursor = {"sia.lines": 0}
        events = self.core.sense_sia(cursor)

        # The periodic row is read and verified but never becomes a corpus
        # event; the lifecycle row after it still does, on the same cursor.
        self.assertEqual(
            [event.kind for event in events], ["install", "boot"])
        # The cursor advanced past the filtered row too — not stuck behind
        # it and not left to be silently re-read next time.
        self.assertEqual(self.core.sense_sia(cursor), [])

    def test_changed_keeper_sidecar_refuses_success_before_projection(self):
        cursor = {"sia.lines": 0}
        prior = copy.deepcopy(cursor)
        real_run = self.core._run_bounded_text_process
        child_statuses = []

        def change_sidecar_after_success(*arguments, **options):
            result = real_run(*arguments, **options)
            child_statuses.append(result.returncode)
            self._change_public_key()
            return result

        with mock.patch.object(
                self.core, "_run_bounded_text_process",
                side_effect=change_sidecar_after_success):
            with self.assertRaisesRegex(RuntimeError, "projection"):
                self.core.sense_sia(cursor)

        self.assertEqual(child_statuses, [0])
        self.assertEqual(cursor, prior)

    def test_changed_keeper_sidecar_during_tail_cannot_commit_cursor(self):
        cursor = {"sia.lines": 0}
        prior = copy.deepcopy(cursor)
        real_rows = self.core._attest_rows
        observed_rows = []

        def change_sidecar_after_tail(*arguments, **options):
            rows = real_rows(*arguments, **options)
            observed_rows.extend(rows)
            self._change_public_key()
            return rows

        with mock.patch.object(
                self.core, "_attest_rows",
                side_effect=change_sidecar_after_tail):
            with self.assertRaisesRegex(RuntimeError, "projection"):
                self.core.sense_sia(cursor)

        self.assertTrue(any(row[2] == "INSTALL:runtime"
                            for row in observed_rows))
        self.assertEqual(cursor, prior)


class ExplicitNullTailCursor(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            prefix="sia-null-cursor-test-")
        self.addCleanup(self.temp.cleanup)
        self.core = _load_core("sialib_null_cursor_integrity")
        self.source = os.path.join(self.temp.name, "source.log")
        with open(self.source, "w", encoding="utf-8") as stream:
            stream.write("unseen observation\n")

    def test_explicit_null_cannot_establish_a_new_baseline(self):
        cursor = {"k": None}
        prior = copy.deepcopy(cursor)

        with mock.patch.dict(os.environ, {"SIA_BACKFILL": "0"}):
            with self.assertRaisesRegex(ValueError, "cursor"):
                self.core.tail_lines(self.source, cursor, "k")

        self.assertEqual(cursor, prior)

    def test_explicit_null_is_still_damage_when_backfill_is_enabled(self):
        cursor = {"k": None}
        prior = copy.deepcopy(cursor)

        with mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
            with self.assertRaisesRegex(ValueError, "cursor"):
                self.core.tail_line_records(self.source, cursor, "k")

        self.assertEqual(cursor, prior)

    def test_absent_cursor_baselines_and_legacy_integer_replays(self):
        fresh = {}
        legacy = {"k": 0}

        with mock.patch.dict(os.environ, {"SIA_BACKFILL": "0"}):
            self.assertEqual(
                self.core.tail_lines(self.source, fresh, "k"), [])
            self.assertEqual(
                self.core.tail_lines(self.source, legacy, "k"),
                ["unseen observation"])

        self.assertIn("k.cursor_v", fresh)
        self.assertIn("k.cursor_v", legacy)


if __name__ == "__main__":
    unittest.main()
