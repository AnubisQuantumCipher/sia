#!/usr/bin/env python3
"""Pulse publication keeps PGLite retry state across crash boundaries."""

import copy
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from unittest import mock


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")
READY = {
    "v": 1, "completed_at": "2026-08-30T12:00:00Z",
    "kind": "recovery", "identity": "0" * 32,
}


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PulseSyncRetry(unittest.TestCase):
    def setUp(self):
        self.sialib = _load(
            "sialib_pulse_sync_test", os.path.join(BIN, "sialib.py"))

    def _run_barrier_pulse(self, *, raise_after_page=False,
                           graph_error=None, page_activity=True,
                           inbox_claim=None):
        """Run an otherwise-idle pulse with one simulated page mutation."""
        persisted = {"chains": {"sia": "pass"},
                     "ready": copy.deepcopy(READY)}
        trace = []
        self.barrier_persisted = persisted
        self.barrier_trace = trace

        def load_memo():
            return copy.deepcopy(persisted)

        def capture_write(path, payload, mode=None):
            if path != self.sialib.MEMO_PATH:
                return
            value = json.loads(payload)
            persisted.clear()
            persisted.update(value)
            trace.append(("memo", value.get("sync_needed", False)))

        def mutate_page():
            self.sialib._before_corpus_mutation()
            trace.append(("page", persisted.get("sync_needed", False)))
            if raise_after_page:
                raise OSError("page fsync refused")
            return True

        def commit(_message):
            trace.append(("commit", persisted.get("sync_needed", False)))
            return "committed"

        def sync():
            trace.append(("sync", persisted.get("sync_needed", False)))
            return True, ""

        def graph():
            trace.append(("graph", persisted.get("sync_needed", False)))
            if graph_error is not None:
                raise graph_error
            return 1, 2, 3

        patches = {
            "ensure_dirs": None,
            "load_cursors": {},
            "save_cursors": None,
            "load_thoughts": {"v": 1, "thoughts": []},
            "load_memo": load_memo,
            "read_json": {},
            "recover_ledger_transitions": ([], []),
            "_settle_thought_page_signals": (0, 0),
            "think": [],
            "materialize_agent_notes": ([], [], [], []),
            "drain_thought_inbox": ([], inbox_claim),
            "ensure_organs": mutate_page if page_activity else False,
            "corpus_dirty": False,
            "atomic_write": capture_write,
            "corpus_commit": commit,
            "brain_sync": sync,
            "export_graph": graph,
            "queue_ledger_transition": "pending-record",
            "_settle_ledger_transition": None,
            "export_thoughts": None,
            "acknowledge_thought_inbox": lambda claim:
                trace.append(("inbox-ack", claim)),
            "ledger_head": (0, ""),
            "export_status": None,
        }
        with tempfile.TemporaryDirectory() as state_dir, ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                self.sialib, "STATE", state_dir))
            stack.enter_context(mock.patch.object(self.sialib, "SENSES", []))
            for name, value in patches.items():
                replacement = value if callable(value) else mock.Mock(
                    return_value=value)
                stack.enter_context(mock.patch.object(
                    self.sialib, name, replacement))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "recover_grade_transactions",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "migrate_legacy_take_pages",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "auto_propose_heals",
                return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "open_intents", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "summary", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "load_mind", return_value={
                    "workspace": [], "seen": {}, "nodes": {}, "edges": {}}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "touch_queue_usage", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "sync_graph_state"))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "drain_touch_queue",
                side_effect=lambda *args, **kwargs:
                (0, None, 0) if kwargs.get("report_capacity")
                else (0, None)))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "surprisal_update", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "rebuild_workspace", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "memory_summary", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "save_mind"))
            return self.sialib._pulse_transaction(1)

    def test_idle_pulse_acknowledges_empty_inbox_claim_without_graph(self):
        status = self._run_barrier_pulse(
            page_activity=False, inbox_claim="empty.draining.json")
        self.assertNotIn("graph_export", status["errors"])
        self.assertIn(("inbox-ack", "empty.draining.json"),
                      self.barrier_trace)
        self.assertFalse(any(item[0] == "graph"
                             for item in self.barrier_trace))

    def test_write_ahead_marker_precedes_first_pulse_page_mutation(self):
        self._run_barrier_pulse()
        self.assertLess(self.barrier_trace.index(("memo", True)),
                        self.barrier_trace.index(("page", True)))
        page_index = self.barrier_trace.index(("page", True))
        self.assertTrue(any(
            kind == "memo" and pending
            for kind, pending in self.barrier_trace[:page_index]))

    def test_page_exception_leaves_write_ahead_marker_durable(self):
        with self.assertRaisesRegex(OSError, "page fsync refused"):
            self._run_barrier_pulse(raise_after_page=True)
        self.assertIs(self.barrier_persisted.get("sync_needed"), True)
        page_index = self.barrier_trace.index(("page", True))
        self.assertTrue(any(
            kind == "memo" and pending
            for kind, pending in self.barrier_trace[:page_index]))

    def test_graph_failure_keeps_pulse_publication_debt(self):
        status = self._run_barrier_pulse(
            graph_error=OSError("graph snapshot refused"))
        self.assertIn("graph_export", status["errors"])
        self.assertIs(self.barrier_persisted.get("sync_needed"), True)
        self.assertIn(("graph", True), self.barrier_trace)

    def test_pulse_debt_clears_only_after_graph_success(self):
        self._run_barrier_pulse()
        self.assertIn(("graph", True), self.barrier_trace)
        self.assertNotIn("sync_needed", self.barrier_persisted)
        final_clear = max(
            index for index, item in enumerate(self.barrier_trace)
            if item == ("memo", False))
        self.assertGreater(
            final_clear, self.barrier_trace.index(("graph", True)))

    def test_failed_sync_is_retried_by_next_idle_pulse(self):
        persisted = {"chains": {"sia": "pass"},
                     "ready": copy.deepcopy(READY)}
        trace = []
        statuses = []
        dirty_results = iter((True, False))
        commit_results = iter(("committed", "clean"))
        sync_results = iter(((False, "index refused"), (True, "")))

        def load_memo():
            return copy.deepcopy(persisted)

        def capture_write(path, payload, mode=None):
            if path != self.sialib.MEMO_PATH:
                return
            value = json.loads(payload)
            persisted.clear()
            persisted.update(value)
            trace.append(("memo", value.get("sync_needed", False)))

        def corpus_commit(_message):
            result = next(commit_results)
            trace.append(("commit", result))
            return result

        def brain_sync():
            result = next(sync_results)
            trace.append(("sync", result[0]))
            return result

        def new_mind():
            return {"workspace": [], "seen": {}, "nodes": {}, "edges": {}}

        patches = {
            "ensure_dirs": None,
            "load_cursors": {},
            "save_cursors": None,
            "load_thoughts": {"v": 1, "thoughts": [{
                "ts": "2026-01-01T00:00:00Z", "kind": "grade",
                "text": "judged", "origin": "model",
            }]},
            "load_memo": load_memo,
            "read_json": {},
            "recover_ledger_transitions": ([], []),
            "_settle_thought_page_signals": (0, 0),
            "think": [],
            "materialize_agent_notes": ([], [], [], []),
            "drain_thought_inbox": ([], None),
            "ensure_organs": False,
            "corpus_dirty": lambda: next(dirty_results),
            "atomic_write": capture_write,
            "corpus_commit": corpus_commit,
            "brain_sync": brain_sync,
            "export_graph": (0, 0, 0),
            "queue_ledger_transition": "pending-record",
            "_settle_ledger_transition": None,
            "export_thoughts": None,
            "ledger_head": (0, ""),
            "export_status": lambda status: statuses.append(status),
        }
        with tempfile.TemporaryDirectory() as state_dir, ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                self.sialib, "STATE", state_dir))
            stack.enter_context(mock.patch.object(self.sialib, "SENSES", []))
            for name, value in patches.items():
                replacement = value if callable(value) else mock.Mock(
                    return_value=value)
                stack.enter_context(mock.patch.object(
                    self.sialib, name, replacement))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "recover_grade_transactions",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "migrate_legacy_take_pages",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "auto_propose_heals",
                return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "open_intents", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "summary", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "load_mind", side_effect=new_mind))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "touch_queue_usage", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "sync_graph_state"))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "drain_touch_queue",
                side_effect=lambda *args, **kwargs:
                (0, None, 0) if kwargs.get("report_capacity")
                else (0, None)))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "surprisal_update", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "rebuild_workspace", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "memory_summary", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "save_mind"))

            first = self.sialib._pulse_transaction(1)
            self.assertEqual(first["state"], "degraded")
            self.assertEqual(first["sync_note"], "index refused")
            self.assertIs(persisted.get("sync_needed"), True)
            self.assertLess(trace.index(("memo", True)),
                            trace.index(("commit", "committed")))

            second_start = len(trace)
            second = self.sialib._pulse_transaction(2)
            self.assertEqual(second["state"], "ok")
            self.assertEqual(second["events_pulse"], 0)
            self.assertNotIn("sync_needed", persisted)
            self.assertEqual(trace[second_start:second_start + 2],
                             [("commit", "clean"), ("sync", True)])

        self.assertEqual([item for item in trace if item[0] == "sync"],
                         [("sync", False), ("sync", True)])
        self.assertEqual(statuses, [first, second])
        self.assertTrue(all(status["thought"]["origin"] == "model"
                            for status in statuses))

    def test_malformed_sync_intent_refuses_before_sensing(self):
        with mock.patch.object(self.sialib, "ensure_dirs"), \
                mock.patch.object(self.sialib, "load_cursors",
                                  return_value={}), \
                mock.patch.object(self.sialib, "load_thoughts",
                                  return_value={"v": 1, "thoughts": []}), \
                mock.patch.object(self.sialib, "load_memo",
                                  return_value={"sync_needed": "yes"}), \
                mock.patch.object(self.sialib, "recover_ledger_transitions") \
                as recover:
            with self.assertRaisesRegex(
                    RuntimeError, "memo sync-needed state is invalid"):
                self.sialib._pulse_transaction(1)
        recover.assert_not_called()

    def test_graph_publication_failure_is_visible_and_signed_as_failure(self):
        queued, settled = [], []

        def queue(*args):
            queued.append(args)
            return "pending"

        patches = {
            "ensure_dirs": None,
            "load_cursors": {},
            "save_cursors": None,
            "load_thoughts": {"v": 1, "thoughts": []},
            "load_memo": {"sync_needed": False,
                          "chains": {"sia": "pass"},
                          "ready": copy.deepcopy(READY)},
            "read_json": {},
            "recover_ledger_transitions": ([], []),
            "_settle_thought_page_signals": (0, 0),
            "think": [],
            "materialize_agent_notes": ([], [], [], []),
            "drain_thought_inbox": ([], None),
            "ensure_organs": False,
            "corpus_dirty": True,
            "atomic_write": None,
            "corpus_commit": "clean",
            "brain_sync": (True, ""),
            "export_graph": OSError("graph snapshot refused"),
            "queue_ledger_transition": queue,
            "_settle_ledger_transition": lambda path: settled.append(path),
            "export_thoughts": None,
            "ledger_head": (0, ""),
            "export_status": None,
        }
        with tempfile.TemporaryDirectory() as state_dir, ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                self.sialib, "STATE", state_dir))
            stack.enter_context(mock.patch.object(self.sialib, "SENSES", []))
            for name, value in patches.items():
                if isinstance(value, BaseException):
                    replacement = mock.Mock(side_effect=value)
                else:
                    replacement = value if callable(value) else mock.Mock(
                        return_value=value)
                stack.enter_context(mock.patch.object(
                    self.sialib, name, replacement))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "recover_grade_transactions",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "migrate_legacy_take_pages",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "auto_propose_heals",
                return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "open_intents", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "summary", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "load_mind", return_value={
                    "workspace": [], "seen": {}, "nodes": {}, "edges": {}}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "touch_queue_usage", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "sync_graph_state"))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "drain_touch_queue",
                side_effect=lambda *args, **kwargs:
                (0, None, 0) if kwargs.get("report_capacity")
                else (0, None)))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "surprisal_update", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "rebuild_workspace", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "memory_summary", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "save_mind"))
            status = self.sialib._pulse_transaction(1)

        self.assertIn("graph_export", status["errors"])
        self.assertEqual(queued[0][1], "PULSE:ingest")
        self.assertEqual(queued[0][3], "graph-fail")
        self.assertEqual(settled, ["pending"])


if __name__ == "__main__":
    unittest.main()
