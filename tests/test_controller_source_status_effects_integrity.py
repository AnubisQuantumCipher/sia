"""Adversarial authority controls for bound controller status effects.

These tests compose the frozen status-effects fixture without inheriting its
test roster.  They exercise write-ahead recovery and the authorities which
must remain current around the one memo write.  They never publish event
pages, graph, status, live state or cursors themselves.
"""

import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_source_status_effects as status_tests


class ControllerSourceStatusEffectsIntegrity(unittest.TestCase):
    def setUp(self):
        self.case = status_tests.ControllerSourceStatusEffects(
            methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.live = self.case.live
        self.lib = self.case.lib
        self.ready = copy.deepcopy(self.live.memo["ready"])
        self.status = self.case._install_status()
        self.batch = self.case.producer._capture()
        self.bound = self.case._bind(self.batch, status=self.status)
        self.arguments = self.case._arguments(self.bound)

    def _persist_memo(self, value):
        detached = copy.deepcopy(value)
        self.live._write(self.live.paths["MEMO_PATH"], detached)
        self.live.memo.clear()
        self.live.memo.update(detached)

    def _stage(self, *, memo=None, arguments=None):
        selected = self.arguments if arguments is None else arguments
        return self.case._stager()(
            memo=self.live.memo if memo is None else memo, **selected)

    def _assert_refusal_without_memo_change(self):
        path = Path(self.live.paths["MEMO_PATH"])
        before = path.read_bytes()
        with self.assertRaises((RuntimeError, ValueError)):
            self._stage()
        self.assertEqual(path.read_bytes(), before)

    def test_ready_beside_pending_status_authority_refuses_instead_of_being_erased(self):
        malformed = copy.deepcopy(self.live.memo)
        malformed["ready"] = copy.deepcopy(self.ready)
        self._persist_memo(malformed)

        self._assert_refusal_without_memo_change()
        self.assertIn("ready", self.live.memo)

    def test_boolean_durable_allocator_cannot_equal_the_integer_binding_sequence(self):
        malformed = copy.deepcopy(self.live.memo)
        malformed["pulse_seq"] = True
        self._persist_memo(malformed)

        self._assert_refusal_without_memo_change()
        self.assertIs(self.live.memo["pulse_seq"], True)

    def test_post_write_caller_mutation_refuses_with_durable_redo_and_exact_retry(self):
        memo_path = Path(self.live.paths["MEMO_PATH"])
        original_write = self.lib.atomic_write
        original_candidate = copy.deepcopy(self.arguments["candidate"])

        def write_then_mutate(path, text, **kwargs):
            result = original_write(path, text, **kwargs)
            self.arguments["candidate"]["prepare_inputs"]["observed_at"] = (
                "changed-after-write")
            return result

        with mock.patch.object(
                self.lib, "atomic_write", side_effect=write_then_mutate), \
                self.assertRaises((RuntimeError, ValueError)):
            self._stage()

        durable = json.loads(memo_path.read_bytes())
        self.assertIn("pulse_status_effects_pending", durable)
        self.assertNotIn("pulse_status_effects_pending", self.live.memo)

        self.arguments["candidate"] = original_candidate
        reloaded = copy.deepcopy(durable)
        self.live.memo.clear()
        self.live.memo.update(reloaded)
        with mock.patch.object(
                self.lib, "atomic_write",
                side_effect=AssertionError("exact recovery retry rewrote memo")):
            self.assertIsNone(self._stage())
        self.assertEqual(json.loads(memo_path.read_bytes()), durable)

    def test_delegated_validation_mutation_on_refusal_cannot_reach_caller_values(self):
        import siasourcebatch

        arguments = copy.deepcopy(self.arguments)

        def mutate_then_refuse(_owner, batch, _expected):
            batch.clear()
            siasourcebatch.refuse("fixture-mutating-validation")

        with mock.patch.object(
                siasourcebatch, "validate_batch",
                side_effect=mutate_then_refuse):
            self.case._assert_refuses(arguments)

    def test_committed_parent_is_reopened_before_status_handoff(self):
        other = status_tests.ControllerSourceStatusEffects(
            methodName="runTest")
        other.setUp()
        self.addCleanup(other.doCleanups)
        admitted = other._install_status()
        batch = other.producer._capture()
        other.producer._commit_matching_parent(batch)
        bound = other._bind(batch, status=admitted, parent=True)
        arguments = other._arguments(bound)

        other.live._write(other.live.paths["LIVE_STATE_PATH"], {})
        memo_path = Path(other.live.paths["MEMO_PATH"])
        before = memo_path.read_bytes()
        with self.assertRaises((RuntimeError, ValueError)):
            other._stager()(memo=other.live.memo, **arguments)
        self.assertEqual(memo_path.read_bytes(), before)
        self.assertNotIn("pulse_status_effects_pending", other.live.memo)

    def test_nonprefix_parent_intake_is_not_guessed_to_be_a_delta(self):
        other = status_tests.ControllerSourceStatusEffects(
            methodName="runTest")
        other.setUp()
        self.addCleanup(other.doCleanups)
        admitted = other._install_status()
        parent = other.producer._capture()
        other.producer._commit_matching_parent(parent)
        with other.source.observe_returns(
                lambda _source_id, _events: []):
            empty = other.source.capture()
            other.source.assert_batch(empty)
        other.producer._stage(empty)

        with self.assertRaises((RuntimeError, ValueError)):
            other.producer._prepare_candidate(
                parent=True, admitted_status=admitted)


if __name__ == "__main__":
    unittest.main()
