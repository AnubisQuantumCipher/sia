"""Bounded protected-day recovery; ledger settlement is a controlled witness.

Real corpus Git, scan checkpoints and memo persistence run in isolated storage.
This is not a resident-service or signed-ledger acceptance campaign.
"""
import copy
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
