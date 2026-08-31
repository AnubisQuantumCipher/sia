#!/usr/bin/env python3
"""Crash-safe handoff tests between corpus commits and the signed keeper."""

import importlib.util
import hashlib
import os
import subprocess
import sys
import tempfile
import threading
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


sialib = _load("sialib_ledger_recovery", os.path.join(BIN, "sialib.py"))


class LedgerRecovery(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.share = os.path.join(self.root.name, "share")
        self.state = os.path.join(self.root.name, "state")
        os.makedirs(self.share)
        os.makedirs(self.state)
        self.old = sialib.SHARE, sialib.STATE, sialib.BIN
        sialib.SHARE, sialib.STATE, sialib.BIN = self.share, self.state, BIN
        initialized = subprocess.run(
            [sys.executable, os.path.join(BIN, "sia-ledger"),
             "init", self.share], capture_output=True, text=True)
        self.assertEqual(initialized.returncode, 0, initialized.stderr)

    def tearDown(self):
        sialib.SHARE, sialib.STATE, sialib.BIN = self.old
        self.root.cleanup()

    def _queue(self, order=1):
        return sialib.queue_ledger_transition(
            order, "PULSE:ingest", f"pulse={order} fixture", "ok",
            '["events/fixture"]')

    def test_recovery_appends_exact_transition_and_acknowledges_request(self):
        path = self._queue()
        recovered, errors = sialib.recover_ledger_transitions()
        self.assertEqual(errors, [])
        self.assertEqual(len(recovered), 1)
        self.assertFalse(os.path.exists(path))
        self.assertTrue(sialib.ledger_contains(
            "PULSE:ingest", "pulse=1 fixture", "ok",
            '["events/fixture"]', recovered[0]["record_id"]))

    def test_crash_after_keeper_append_is_idempotent_on_recovery(self):
        path = self._queue()
        record, _identity = sialib._read_pending_record(path)
        sialib.ledger_append(
            "PULSE:ingest", "pulse=1 fixture", "ok",
            '["events/fixture"]', required=True,
            occurrence_id=record["record_id"])
        ledger = os.path.join(self.share, "ledger.tsv")
        with open(ledger, "rb") as stream:
            signed = stream.read()
        recovered, errors = sialib.recover_ledger_transitions()
        self.assertEqual(errors, [])
        self.assertEqual(len(recovered), 1)
        self.assertFalse(os.path.exists(path))
        with open(ledger, "rb") as stream:
            self.assertEqual(stream.read(), signed)

    def test_crash_after_atomic_settlement_before_ack_is_idempotent(self):
        path = self._queue()
        settle = sialib.ledger_settle

        def settle_then_crash(*args, **kwargs):
            settle(*args, **kwargs)
            raise OSError("injected crash after keeper settlement")

        with mock.patch.object(
                sialib, "ledger_settle", side_effect=settle_then_crash):
            recovered, errors = sialib.recover_ledger_transitions()
        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertTrue(os.path.exists(path))
        ledger = os.path.join(self.share, "ledger.tsv")
        with open(ledger, "rb") as stream:
            signed = stream.read()

        recovered, errors = sialib.recover_ledger_transitions()
        self.assertEqual(errors, [])
        self.assertEqual(len(recovered), 1)
        self.assertFalse(os.path.exists(path))
        with open(ledger, "rb") as stream:
            self.assertEqual(stream.read(), signed)

    def test_concurrent_keeper_settlers_append_occurrence_once(self):
        path = self._queue()
        record, _identity = sialib._read_pending_record(path)
        content = sialib._ledger_bound_content(
            record["content"], record["record_id"]).encode()
        digest = hashlib.sha256(content).hexdigest()
        command = [
            sys.executable, os.path.join(BIN, "sia-ledger"), "settle",
            self.share, record["action"], record["arg1"], record["arg2"],
            digest, str(len(content)),
        ]
        # JACKAL status=exact: parsed=2+1, exact=3; parsed=2-1, exact=1.
        # Exact rational arithmetic outside the Lean certificate chain
        # (NOT formal-bounded).
        barrier = threading.Barrier(3)
        results = []

        def worker():
            barrier.wait()
            results.append(subprocess.run(
                command, capture_output=True, text=True, timeout=30))

        threads = [threading.Thread(target=worker) for _index in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertTrue(all(result.returncode == 0 for result in results),
                        [result.stderr for result in results])

        with open(os.path.join(self.share, "ledger.tsv"), encoding="utf-8") \
                as stream:
            rows = [line.rstrip("\n").split("\t") for line in stream]
        matches = [row for row in rows
                   if row[2:7] == [record["action"], record["arg1"],
                                   record["arg2"], digest,
                                   str(len(content))]]
        self.assertEqual(len(matches), 1)

        recovered, errors = sialib.recover_ledger_transitions()
        self.assertEqual(errors, [])
        self.assertEqual(len(recovered), 1)
        self.assertFalse(os.path.exists(path))

    def test_distinct_identical_occurrences_each_reach_the_ledger(self):
        sialib.durable_ledger_append(
            "DREAM:grade", "none-due", "", order=101)
        first_count, _first_head = sialib.ledger_head()
        sialib.durable_ledger_append(
            "DREAM:grade", "none-due", "", order=102)
        second_count, _second_head = sialib.ledger_head()
        self.assertGreater(second_count, first_count)

    def test_keeper_refusal_retains_request_and_surfaces_error(self):
        path = self._queue()
        with mock.patch.object(
                    sialib, "ledger_settle",
                    side_effect=RuntimeError("keeper refused")):
            recovered, errors = sialib.recover_ledger_transitions()
        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn("keeper refused", errors[0]["error"])
        self.assertTrue(os.path.exists(path))

    def test_symlink_record_is_reported_without_reading_target(self):
        directory = sialib._ensure_ledger_pending_dir()
        target = os.path.join(self.root.name, "private")
        with open(target, "w") as stream:
            stream.write("do not read")
        os.symlink(target, os.path.join(directory, "0" * 64 + ".json"))
        recovered, errors = sialib.recover_ledger_transitions()
        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn("Too many levels", errors[0]["error"])

    def test_record_overflow_fails_before_unbounded_name_materialization(self):
        directory = sialib._ensure_ledger_pending_dir()
        # JACKAL status=exact: parsed=1+1, exact=2; parsed=2+1, exact=3.
        # Exact rational arithmetic outside the Lean certificate chain
        # (NOT formal-bounded).
        for index in range(3):
            path = os.path.join(directory, f"{index:064x}.json")
            with open(path, "w") as stream:
                stream.write("{}")
            os.chmod(path, 0o600)
        with mock.patch.object(sialib, "MAX_LEDGER_PENDING_RECORDS", 2), \
                mock.patch.object(
                    sialib.os, "listdir",
                    side_effect=AssertionError("os.listdir is unbounded")):
            recovered, errors = sialib.recover_ledger_transitions()
        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn("record limit", errors[0]["error"])

    def test_unexpected_directory_entries_have_a_hard_scan_ceiling(self):
        directory = sialib._ensure_ledger_pending_dir()
        # JACKAL status=exact: parsed=2+1, exact=3. Exact rational arithmetic
        # outside the Lean certificate chain (NOT formal-bounded).
        for index in range(3):
            with open(os.path.join(directory, f"noise-{index}"), "w") \
                    as stream:
                stream.write("ignored")
        with mock.patch.object(
                sialib, "MAX_LEDGER_PENDING_SCAN_ENTRIES", 3):
            recovered, errors = sialib.recover_ledger_transitions()
        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn("scan limit", errors[0]["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
