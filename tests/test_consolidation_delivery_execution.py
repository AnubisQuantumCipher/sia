"""Execution intent permits exact-lineage recovery without retiring a batch."""
import json
from pathlib import Path
import unittest
from unittest import mock

from tests import test_consolidation_delivery as delivery_fixture


class ConsolidationDeliveryExecution(unittest.TestCase):
    def setUp(self):
        self.fixture = delivery_fixture.ConsolidationDelivery(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.delivery = self.fixture.delivery
        self.record = self.fixture.record
        self.path = self.fixture.path
        self.sources = self.fixture.fixture.old
        self.epoch = self.fixture.fixture.fixture.epoch
        self.memo_path = self.path.parent / "memo.json"
        self.lib.atomic_write(str(self.memo_path), '{"retained-debt":true}')
        self.memo_bytes = self.memo_path.read_bytes()

    def stage(self):
        self.fixture.offer()
        return self.delivery.prepare_claims(self.lib, self.record)

    def execute(self):
        with mock.patch.object(
                self.lib, "_acknowledge_consolidation_claims",
                side_effect=AssertionError("snapshot must not ACK legacy scan")):
            return self.delivery.execute_claims(self.lib, self.record)

    def retained(self):
        return json.loads(self.path.read_text())

    def assert_retained_batch(self, original, phase):
        value = self.retained()
        self.assertEqual(value, dict(original, phase=phase))
        self.assertEqual(self.memo_path.read_bytes(), self.memo_bytes)
        return value

    def test_effects_replay_never_acknowledges_or_advances_cursor(self):
        claimed = self.stage()
        result = self.execute()
        self.assertEqual(result, dict(claimed, phase="effects-returned"))
        self.assertTrue(all(not path.exists() for path in self.sources))
        before = self.epoch.read_bytes()
        retained = self.path.read_bytes()
        with mock.patch.object(
                self.lib, "_execute_consolidation_claims",
                side_effect=AssertionError("returned effects repeated")):
            self.assertEqual(self.execute(), result)
            self.assertEqual(self.fixture.offer(budget=1), result)
        self.assertEqual(self.epoch.read_bytes(), before)
        self.assertEqual(self.path.read_bytes(), retained)
        self.assert_retained_batch(claimed, "effects-returned")
        with self.assertRaisesRegex(ValueError, "no pending batch"):
            self.delivery.prepare_claims(self.lib, self.record)

    def test_intent_cuts_precede_every_epoch_effect(self):
        claimed = self.stage()
        for stage, phase in (("before-execution-persist", "claimed"),
                             ("execution-persisted", "executing")):
            def cut(observed):
                if observed == stage:
                    raise RuntimeError("intent cut")
            with mock.patch.object(self.delivery, "_boundary", cut):
                with self.assertRaisesRegex(RuntimeError, "intent cut"):
                    self.execute()
            self.assert_retained_batch(claimed, phase)
            self.fixture.assert_sources_unchanged()
        self.assertEqual(self.execute()["phase"], "effects-returned")

    def test_partial_cleanup_replays_only_with_retained_execution_intent(self):
        claimed = self.stage()
        original = self.lib._unlink_consolidation_source

        def cut(item):
            original(item)
            raise RuntimeError("cut after first unlink")

        with mock.patch.object(self.lib, "_unlink_consolidation_source", cut):
            with self.assertRaisesRegex(RuntimeError, "cut after first unlink"):
                self.execute()
        executing = self.assert_retained_batch(claimed, "executing")
        self.assertFalse(self.sources[0].exists())
        self.assertTrue(all(path.exists() for path in self.sources[1:]))
        before = self.epoch.read_bytes()
        self.assertEqual(self.fixture.offer(), executing)
        self.execute()
        self.assertEqual(self.epoch.read_bytes(), before)
        self.assertTrue(all(not path.exists() for path in self.sources))
        self.assert_retained_batch(claimed, "effects-returned")

    def test_publication_failure_keeps_execution_intent_and_source_bytes(self):
        claimed = self.stage()
        failure = RuntimeError("index refused")
        with mock.patch.object(self.lib, "_publish_event_index_entries",
                               side_effect=failure):
            with self.assertRaises(RuntimeError) as raised:
                self.execute()
        self.assertIs(raised.exception, failure)
        self.assertEqual({path: path.read_bytes() for path in self.sources},
                         self.fixture.fixture.original)
        before = self.epoch.read_bytes()
        self.assert_retained_batch(claimed, "executing")
        self.execute()
        self.assertEqual(self.epoch.read_bytes(), before)
        self.assertTrue(all(not path.exists() for path in self.sources))

    def test_current_pin_observation_retains_sources_without_completion_claim(self):
        claimed = self.stage()
        pins = {path.relative_to(self.lib.CORPUS).as_posix()[:-3]
                for path in self.sources}
        with mock.patch.object(self.lib.siamind, "pending_user_pin_slugs",
                               return_value=pins):
            self.assertEqual(self.execute()["phase"], "effects-returned")
        self.fixture.assert_sources_unchanged()
        self.assert_retained_batch(claimed, "effects-returned")

    def test_commit_failure_and_unstaged_execution_refuse_without_effects(self):
        with self.assertRaisesRegex(ValueError, "no executable claims"):
            self.execute()
        self.assertFalse(self.path.exists())
        self.fixture.offer()
        pending = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "no executable claims"):
            self.execute()
        self.assertEqual(self.path.read_bytes(), pending)
        claimed = self.stage()
        with mock.patch.object(self.lib, "corpus_commit", return_value="error"):
            with self.assertRaisesRegex(RuntimeError, "git commit failed"):
                self.execute()
        self.assert_retained_batch(claimed, "claimed")
        self.fixture.assert_sources_unchanged()

    def test_missing_source_requires_exact_epoch_lineage_after_intent(self):
        claimed = self.stage()
        def cut(stage):
            if stage == "execution-persisted":
                raise RuntimeError("stop after intent")
        with mock.patch.object(self.delivery, "_boundary", cut):
            with self.assertRaisesRegex(RuntimeError, "stop after intent"):
                self.execute()
        self.sources[0].unlink()
        for operation in (self.execute, self.fixture.offer):
            with self.assertRaisesRegex(RuntimeError, "lacks exact epoch"):
                operation()
        self.assertFalse(self.epoch.exists())
        self.assert_retained_batch(claimed, "executing")

    def test_returned_effect_cuts_replay_exact_epoch_and_claim_identity(self):
        claimed = self.stage()
        for stage, phase in (("effects-returned", "executing"),
                             ("effects-persisted", "effects-returned")):
            def cut(observed):
                if observed == stage:
                    raise RuntimeError("completion cut")
            with mock.patch.object(self.delivery, "_boundary", cut):
                with self.assertRaisesRegex(RuntimeError, "completion cut"):
                    self.execute()
            self.assert_retained_batch(claimed, phase)
            if stage == "effects-returned":
                before = self.epoch.read_bytes()
            self.assertEqual(self.epoch.read_bytes(), before)
        self.execute()
        self.assertEqual(self.epoch.read_bytes(), before)

    def test_invalid_attempt_result_does_not_persist_returned_state(self):
        claimed = self.stage()
        for result in (None, [0, 0, 0], (True, 0, 0), (4, 0, 0), (-1, 0, 0)):
            with self.subTest(result=result), mock.patch.object(
                    self.lib, "_execute_consolidation_claims",
                    return_value=result):
                with self.assertRaisesRegex(ValueError, "invalid attempt counts"):
                    self.execute()
            self.assert_retained_batch(claimed, "executing")
            self.fixture.assert_sources_unchanged()

    def test_execution_cannot_relabel_prior_missing_sources_as_its_own_effects(self):
        claimed = self.stage()
        self.lib.consolidate_corpus()
        self.assertTrue(all(not path.exists() for path in self.sources))
        with self.assertRaisesRegex(ValueError, "every source to remain live"):
            self.execute()
        self.assert_retained_batch(claimed, "claimed")

    def test_returned_attempt_is_not_an_index_completeness_witness(self):
        """Negative boundary: retirement must not infer readiness from this state."""
        claimed = self.stage()
        returned = self.execute()
        epoch = self.lib._read_epoch_state("epochs/org/2026-w02")
        event_id = epoch["event_ids"][0]
        leaf = Path(self.lib.CORPUS) / self.lib._event_index_relative("org", event_id)
        self.assertIsNotNone(self.lib._read_event_index_entry("org", event_id))
        leaf.unlink()
        self.assertIsNone(self.lib._read_event_index_entry("org", event_id))
        self.assertEqual(self.execute(), returned)
        self.assertFalse(leaf.exists())
        self.assert_retained_batch(claimed, "effects-returned")


if __name__ == "__main__":
    unittest.main()
