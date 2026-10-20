"""Durable batch/live-claim handoff; no consumption or publication authority."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import unittest
from unittest import mock

from tests import test_consolidation_discovery as discovery_fixture


class ConsolidationDelivery(unittest.TestCase):
    def setUp(self):
        self.fixture = discovery_fixture.ConsolidationDiscovery(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.fixture.start()
        self.lib = self.fixture.lib
        self.record = self.fixture.record
        self.delivery = importlib.import_module("siaconsolidationdelivery")
        self.path = Path(self.lib.STATE) / "consolidation-snapshot-delivery.json"

    def offer(self, budget=32):
        return self.delivery.offer(self.lib, self.record, budget=budget)

    def assert_sources_unchanged(self):
        self.assertEqual({path: path.read_bytes() for path in self.fixture.old},
                         self.fixture.original)
        self.assertFalse(self.fixture.fixture.epoch.exists())
        self.assertEqual(self.fixture.journal.read_bytes(), self.fixture.before)

    def test_batch_and_cursor_replay_together_without_caller_ack(self):
        pending = self.offer()
        self.assertEqual(pending["phase"], "pending")
        self.assertIsNone(pending["cursor"])
        self.assertTrue(pending["batch"]["result"]["cursor"]["complete"])
        self.assertEqual([item["relative"] for item in
                          pending["batch"]["result"]["candidates"]],
                         ["events/org/2026-01-05.md", "events/org/2026-01-06.md",
                          "events/org/2026-01-07.md"])
        before = self.path.read_bytes()
        self.assertEqual(self.offer(budget=1), pending)
        self.assertEqual(self.path.read_bytes(), before)
        # Mutating the return value is not a durable acknowledgment.
        pending["batch"]["result"]["candidates"].clear()
        pending["phase"] = "complete"
        replay = self.offer()
        self.assertEqual(len(replay["batch"]["result"]["candidates"]), 3)
        self.assertEqual(replay["phase"], "pending")
        self.assertEqual(self.path.read_bytes(), before)
        self.assert_sources_unchanged()

    def test_live_claim_handoff_retains_pending_batch_and_exact_source_ids(self):
        pending = self.offer()
        claimed = self.delivery.prepare_claims(self.lib, self.record)
        self.assertEqual(claimed["phase"], "claimed")
        self.assertEqual(claimed["batch"], pending["batch"])
        self.assertEqual(claimed["cursor"], pending["cursor"])
        expected = []
        for path in self.fixture.old:
            relative = path.relative_to(self.lib.CORPUS).as_posix()
            digest = hashlib.sha256(
                relative.encode() + b"\0" + self.fixture.original[path]).hexdigest()
            expected.append({"rel": relative, "sha256": digest})
        self.assertEqual([source for claim in claimed["claims"]["claims"]
                          for source in claim["sources"]], expected)
        before = self.path.read_bytes()
        self.assertEqual(self.delivery.prepare_claims(self.lib, self.record), claimed)
        self.assertEqual(self.offer(), claimed)
        self.assertEqual(self.path.read_bytes(), before)
        self.assert_sources_unchanged()

    def test_empty_discovery_pages_advance_but_pending_batch_cannot_be_skipped(self):
        for _attempt in range(16):
            state = self.offer(budget=1)
            if state["phase"] == "pending":
                break
            self.assertEqual(state["phase"], "scan")
            self.assertIsNone(state["batch"])
        self.assertEqual(state["phase"], "pending")
        retained = self.path.read_bytes()
        for _attempt in range(3):
            self.assertEqual(self.offer(), state)
            self.assertEqual(self.path.read_bytes(), retained)
        self.assert_sources_unchanged()

    def test_retained_candidate_omission_and_cursor_jump_refuse(self):
        pending = self.offer()
        omitted = copy.deepcopy(pending)
        omitted["batch"]["result"]["candidates"].pop()
        jumped = copy.deepcopy(pending)
        jumped["cursor"] = jumped["batch"]["result"]["cursor"]
        unexpected = copy.deepcopy(pending)
        unexpected["acknowledged"] = True
        boolean_part = copy.deepcopy(pending)
        boolean_part["batch"]["result"]["candidates"][0]["part"] = True
        integer_complete = copy.deepcopy(pending)
        integer_complete["batch"]["result"]["cursor"]["complete"] = 1
        for value in (omitted, jumped, unexpected, boolean_part, integer_complete):
            with self.subTest(value=value):
                self.lib.atomic_write(str(self.path), json.dumps(value))
                before = self.path.read_bytes()
                with self.assertRaises(ValueError):
                    self.offer()
                self.assertEqual(self.path.read_bytes(), before)
        self.assert_sources_unchanged()

    def test_missing_live_source_refuses_without_losing_pending_batch(self):
        self.offer()
        before = self.path.read_bytes()
        self.fixture.old[0].unlink()  # Disposable fixture-only loss injection.
        with self.assertRaisesRegex(ValueError, "exact selected claims"):
            self.delivery.prepare_claims(self.lib, self.record)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.offer()["phase"], "pending")
        self.assertFalse(self.fixture.fixture.epoch.exists())

    def test_changed_source_refuses_claimed_replay_without_rewriting_claim(self):
        self.offer()
        self.delivery.prepare_claims(self.lib, self.record)
        before = self.path.read_bytes()
        path = self.fixture.old[0]
        self.lib.atomic_write(str(path), path.read_text() + "\nchanged source\n")
        with self.assertRaisesRegex(RuntimeError, "conflicts"):
            self.delivery.prepare_claims(self.lib, self.record)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.fixture.fixture.epoch.exists())

    def test_preexisting_epoch_lineage_does_not_authorize_staging_source_loss(self):
        self.offer()
        claimed = self.delivery.prepare_claims(self.lib, self.record)
        before = self.path.read_bytes()
        # Real legacy consolidation produces exact epoch lineage and removes
        # these fixture sources. The new staging consumer has executed nothing.
        self.lib.consolidate_corpus()
        self.assertTrue(self.fixture.fixture.epoch.exists())
        self.assertTrue(all(not path.exists() for path in self.fixture.old))
        self.assertEqual(self.lib._claimed_consolidation_paths(claimed["claims"]), [])
        with self.assertRaisesRegex(ValueError, "every source"):
            self.delivery.prepare_claims(self.lib, self.record)
        with self.assertRaisesRegex(ValueError, "every source"):
            self.offer()
        self.assertEqual(self.path.read_bytes(), before)

    def test_exception_cuts_preserve_exact_batch_or_claim_for_retry(self):
        stages = ("before-batch-persist", "batch-persisted",
                  "before-claims-persist", "claims-persisted")
        for stage in stages:
            with self.subTest(stage=stage):
                def fail(current):
                    if current == stage:
                        raise RuntimeError("injected delivery cut")
                operation = self.offer if "batch" in stage else (
                    lambda: self.delivery.prepare_claims(self.lib, self.record))
                with mock.patch.object(self.delivery, "_boundary", fail):
                    with self.assertRaisesRegex(RuntimeError, "injected delivery cut"):
                        operation()
                if stage == "before-batch-persist":
                    self.assertFalse(self.path.exists())
                elif stage in {"batch-persisted", "before-claims-persist"}:
                    self.assertEqual(json.loads(self.path.read_text())["phase"],
                                     "pending")
                else:
                    self.assertEqual(json.loads(self.path.read_text())["phase"],
                                     "claimed")
        claimed = self.delivery.prepare_claims(self.lib, self.record)
        self.assertEqual(claimed["phase"], "claimed")
        self.assertEqual(self.offer(), claimed)
        self.assert_sources_unchanged()

    def test_invalid_budget_and_claim_before_offer_refuse(self):
        for budget in (0, True, 1025):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                self.offer(budget)
        with self.assertRaisesRegex(ValueError, "no pending batch"):
            self.delivery.prepare_claims(self.lib, self.record)
        self.assertFalse(self.path.exists())
        self.assert_sources_unchanged()


if __name__ == "__main__":
    unittest.main()
