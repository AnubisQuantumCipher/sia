"""Bounded protected-day recovery; ledger settlement is a controlled witness.

Real corpus Git, scan checkpoints and memo persistence run in isolated storage.
This is not a resident-service or signed-ledger acceptance campaign.
"""
import copy
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from tests import sia_test_home  # noqa: F401
from tests import test_epoch_exemplar_coverage as epoch_fixture


class ConsolidationBacklogRecovery(unittest.TestCase):
    def setUp(self):
        self.fixture = epoch_fixture.EpochExemplarCoverage(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.lib.MEMO_PATH = str(Path(self.lib.STATE) / "memo.json")
        self.paths = [
            self.fixture._day(date, ("OBS",))
            for date in ("2026-01-05", "2026-01-06", "2026-01-07")]
        self.originals = {path: path.read_bytes() for path in self.paths}
        self.fixture._commit()
        self.pins = {path.relative_to(self.lib.CORPUS).as_posix()[:-3]
                     for path in self.paths}

    def scan(self):
        return self.lib.read_state_json(
            self.lib._consolidation_scan_path(), {}, "consolidation scan")

    def test_protected_backlog_drains_without_early_settlement(self):
        memo = {}
        self.lib._mark_consolidation_pending(memo)
        identity = copy.deepcopy(memo["consolidation_pending"])
        with mock.patch.object(self.lib, "MAX_CONSOLIDATION_DAYS_PER_RUN", 1), \
                mock.patch.object(self.lib.siamind, "pending_user_pin_slugs",
                                  return_value=self.pins), \
                mock.patch.object(self.lib, "_settle_consolidation_ledger") as settle:
            generation = None
            for remaining in (2, 1):
                self.lib._recover_pending_consolidation(memo)
                state = self.scan()
                self.assertEqual(len(state["pending_days"]), remaining)
                self.assertEqual(state["claims"], [])
                self.assertEqual(state["phase"], "complete")
                if generation is None:
                    generation = state["generation"]
                self.assertEqual(state["generation"], generation)
                self.assertEqual(memo["consolidation_pending"]["id"], identity["id"])
                self.assertNotIn("applied_at", memo["consolidation_pending"])
                self.assertTrue(self.lib._consolidation_scan_debt())
                settle.assert_not_called()
                # Discard in-memory state between bounded recovery calls.
                memo = self.lib.load_memo()
            self.lib._recover_pending_consolidation(memo)
            settle.assert_called_once()
            self.assertNotIn("consolidation_pending", self.lib.load_memo())
            self.assertEqual(self.lib._consolidation_scan_debt(), "")
        self.assertEqual({path: path.read_bytes() for path in self.paths},
                         self.originals)
        self.assertFalse(self.fixture.epoch.exists())

    def test_unlink_rescan_finishes_without_losing_protected_days(self):
        original_commit = subprocess.check_output(
            ["git", "-C", self.lib.CORPUS, "rev-parse", "HEAD"],
            text=True, timeout=10).strip()
        retired = self.paths[-1]
        retired_rel = retired.relative_to(self.lib.CORPUS).as_posix()
        pins = self.pins - {retired_rel[:-3]}
        memo = {}
        self.lib._mark_consolidation_pending(memo)
        identity = memo["consolidation_pending"]["id"]
        generations = []
        with mock.patch.object(self.lib, "MAX_CONSOLIDATION_DAYS_PER_RUN", 1), \
                mock.patch.object(self.lib.siamind, "pending_user_pin_slugs",
                                  return_value=pins), \
                mock.patch.object(self.lib, "_settle_consolidation_ledger") as settle:
            for phase, remaining in (
                    ("complete", 2), ("complete", 1), ("scan", 0),
                    ("complete", 1), ("complete", 0)):
                self.lib._recover_pending_consolidation(memo)
                state = self.scan()
                generations.append(state["generation"])
                self.assertEqual((state["phase"], len(state["pending_days"])),
                                 (phase, remaining))
                self.assertEqual(state["claims"], [])
                if self.lib._consolidation_scan_debt():
                    settle.assert_not_called()
                    self.assertEqual(memo["consolidation_pending"]["id"], identity)
                    self.assertNotIn("applied_at", memo["consolidation_pending"])
                memo = self.lib.load_memo()
            settle.assert_called_once()
        self.assertEqual(generations[0], generations[1])
        self.assertNotEqual(generations[1], generations[2])
        self.assertEqual(generations[2:], [generations[2]] * 3)
        self.assertNotIn("consolidation_pending", memo)
        self.assertFalse(retired.exists())
        for path in self.paths[:-1]:
            self.assertEqual(path.read_bytes(), self.originals[path])
        retained = subprocess.check_output(
            ["git", "-C", self.lib.CORPUS, "show",
             original_commit + ":" + retired_rel], timeout=10)
        self.assertEqual(retained, self.originals[retired])
        self.assertTrue(self.fixture.epoch.exists())

    def test_settlement_failure_retains_applied_identity_for_retry(self):
        memo = {}
        self.lib._mark_consolidation_pending(memo)
        identity = memo["consolidation_pending"]["id"]
        with mock.patch.object(self.lib.siamind, "pending_user_pin_slugs",
                               return_value=self.pins), \
                mock.patch.object(self.lib, "_settle_consolidation_ledger",
                                  side_effect=RuntimeError("injected settlement failure")):
            with self.assertRaisesRegex(RuntimeError, "injected settlement failure"):
                self.lib._recover_pending_consolidation(memo)
        persisted = self.lib.load_memo()
        marker = copy.deepcopy(persisted["consolidation_pending"])
        self.assertEqual(marker["id"], identity)
        self.assertIn("applied_at", marker)
        self.assertIn("ledger", marker)
        self.assertEqual(self.lib._consolidation_scan_debt(), "")
        # A completed scan must not erase an unsettled named transaction.
        self.assertEqual(self.lib._pending_consolidation_marker(persisted), marker)
        settled = []
        with mock.patch.object(self.lib, "consolidate_corpus",
                               side_effect=AssertionError("applied work repeated")), \
                mock.patch.object(self.lib, "_settle_consolidation_ledger",
                                  side_effect=lambda state: settled.append(
                                      copy.deepcopy(state["consolidation_pending"]))) as settle:
            self.lib._recover_pending_consolidation(persisted)
            settle.assert_called_once()
        self.assertEqual(settled, [marker])
        self.assertNotIn("consolidation_pending", self.lib.load_memo())
        self.assertEqual({path: path.read_bytes() for path in self.paths},
                         self.originals)
        self.assertFalse(self.fixture.epoch.exists())


if __name__ == "__main__":
    unittest.main()
