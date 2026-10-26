"""Claim effects retain acknowledgment ownership and existing recovery gates."""
import ast
import copy
from pathlib import Path
import unittest
from unittest import mock

from tests import test_epoch_exemplar_coverage as epoch_fixture


EXECUTOR_ROUTINES = frozenset({
    "_consolidation_day_paths", "_consolidation_day_lineage",
    "_consolidation_day_is_durable", "_read_consolidation_source",
    "_consolidation_day_items", "_group_consolidation_claims",
    "_unlink_consolidation_source", "_consolidation_pending_summary",
    "_extend_consolidation_summary", "_render_consolidation_epoch",
    "_plan_consolidation_group", "_apply_consolidation_groups",
    "_execute_consolidation_claims", "consolidate_corpus",
})


class ConsolidationExecutor(unittest.TestCase):
    def setUp(self):
        self.fixture = epoch_fixture.EpochExemplarCoverage(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.lib.CORPUS_OWNER_LOCK = str(Path(self.lib.STATE) / "corpus.lock")
        self.paths = [self.fixture._day(date, ("OBS",))
                      for date in ("2026-01-05", "2026-01-06")]
        self.originals = {path: path.read_bytes() for path in self.paths}
        self.fixture._commit()
        self.cutoff = "2026-02-01"
        with self.lib.corpus_owner():
            state = self.lib._load_consolidation_scan(self.cutoff)
            state = self.lib._advance_consolidation_scan(state)
            self.claims = self.lib._prepare_consolidation_claims(state)
        self.retained = copy.deepcopy(self.claims)
        self.scan_path = Path(self.lib._consolidation_scan_path())
        self.scan_bytes = self.scan_path.read_bytes()

    def execute(self, pins=frozenset()):
        with self.lib.corpus_owner(), mock.patch.object(
                self.lib, "_acknowledge_consolidation_claims",
                side_effect=AssertionError("executor must not acknowledge")):
            return self.lib._execute_consolidation_claims(
                self.claims, self.cutoff, pins, [])

    def assert_claims_retained(self):
        self.assertEqual(self.claims, self.retained)
        self.assertEqual(self.scan_path.read_bytes(), self.scan_bytes)

    def test_effects_and_protected_days_leave_claim_ack_to_caller(self):
        protected = self.paths[0]
        pin = protected.relative_to(self.lib.CORPUS).as_posix()[:-3]
        self.assertEqual(self.execute({pin}), (1, 1, 1))
        self.assertEqual(protected.read_bytes(), self.originals[protected])
        self.assertFalse(self.paths[1].exists())
        state = self.lib._read_epoch_state("epochs/org/2026-w02")
        self.assertEqual(state["dates"], ["2026-01-06"])
        self.assertEqual([record["rel"] for record in state["source_manifest"]],
                         ["events/org/2026-01-06.md"])
        self.assert_claims_retained()

    def test_index_failure_retains_sources_then_replays_without_double_counts(self):
        failure = RuntimeError("injected index publication failure")
        with mock.patch.object(self.lib, "_publish_event_index_entries",
                               side_effect=failure):
            with self.assertRaises(RuntimeError) as raised:
                self.execute()
        self.assertIs(raised.exception, failure)
        self.assertEqual({path: path.read_bytes() for path in self.paths},
                         self.originals)
        before = self.fixture.epoch.read_bytes()
        self.assert_claims_retained()
        self.assertEqual(self.execute(), (0, 0, 0))
        self.assertEqual(self.fixture.epoch.read_bytes(), before)
        self.assertTrue(all(not path.exists() for path in self.paths))
        self.assert_claims_retained()

    def test_changed_source_refuses_without_mutation_or_ack(self):
        changed = self.paths[-1]
        changed.write_bytes(self.originals[changed] + b"\nchanged\n")
        expected = {path: path.read_bytes() for path in self.paths}
        with self.assertRaisesRegex(
                RuntimeError, "live event shard conflicts.*consolidation claim"):
            self.execute()
        self.assertEqual({path: path.read_bytes() for path in self.paths}, expected)
        self.assertFalse(self.fixture.epoch.exists())
        self.assert_claims_retained()


class ConsolidationRoutineBudget(unittest.TestCase):
    def test_reviewed_executor_routines_have_at_most_sixty_physical_lines(self):
        source = epoch_fixture.REPO / "bin" / "siathought.py"
        definitions = {node.name: node for node in ast.parse(source.read_text()).body
                       if isinstance(node, ast.FunctionDef)}
        self.assertTrue(EXECUTOR_ROUTINES <= definitions.keys())
        for name in sorted(EXECUTOR_ROUTINES):
            with self.subTest(routine=name):
                node = definitions[name]
                self.assertLessEqual(node.end_lineno - node.lineno + 1, 60)


if __name__ == "__main__":
    unittest.main()
