#!/usr/bin/env python3
"""Nightly publication must fail closed and remain retryable."""

import copy
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack, nullcontext
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DreamPublication(unittest.TestCase):
    def setUp(self):
        self.sialib = _load("sialib_dream_test", os.path.join(BIN, "sialib.py"))
        self.state_root = tempfile.TemporaryDirectory()
        self.old_state_paths = (
            self.sialib.STATE, self.sialib.CORPUS_OWNER_LOCK,
            self.sialib.THOUGHTS_PATH, self.sialib.siamind.MIND_PATH,
            self.sialib.LIFECYCLE_LOCK,
            self.sialib.LIFECYCLE_TOMBSTONE)
        self.sialib.STATE = self.state_root.name
        self.sialib.CORPUS_OWNER_LOCK = os.path.join(
            self.state_root.name, "corpus-owner.lock")
        self.sialib.THOUGHTS_PATH = os.path.join(
            self.state_root.name, "thoughts.json")
        self.sialib.siamind.MIND_PATH = os.path.join(
            self.state_root.name, "mind.json")
        self.sialib.LIFECYCLE_LOCK = os.path.join(
            self.state_root.name, "lifecycle.lock")
        self.sialib.LIFECYCLE_TOMBSTONE = os.path.join(
            self.state_root.name, "lifecycle-removed")
        self.memo = {
            "dream": {"last": "previous-success"},
            "ready": {
                "v": 1, "completed_at": "2026-08-30T12:00:00Z",
                "kind": "recovery", "identity": "0" * 32,
            },
        }
        self.mind = {}
        self.written_memo = None
        self.ledger_rows = []
        self.thought_rows = []
        self.trace = []
        self.consolidation_trace = []
        self.fake_bench = types.SimpleNamespace(run_quick=lambda: None)

    def tearDown(self):
        (self.sialib.STATE, self.sialib.CORPUS_OWNER_LOCK,
         self.sialib.THOUGHTS_PATH,
         self.sialib.siamind.MIND_PATH, self.sialib.LIFECYCLE_LOCK,
         self.sialib.LIFECYCLE_TOMBSTONE) = self.old_state_paths
        self.state_root.cleanup()

    def _run(self, *, result, commit="clean", sync=(True, ""),
             graph=(False, False, False), rehearse=None, ledger=None,
             due_takes=None, grade_take=None, grade_summary=None,
             muse=None, save_mind=None, consolidate=None,
             add_thought=None, commit_grade=None):
        def capture_write(path, content, mode=None):
            if path != self.sialib.MEMO_PATH:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write(content)
                return
            self.written_memo = json.loads(content)
            self.trace.append(
                ("memo", self.written_memo.get("sync_needed", False)))
            self.consolidation_trace.append(
                ("memo", self.written_memo.get(
                    "consolidation_pending", False)))

        def capture_ledger(*args):
            self.ledger_rows.append(args)
            self.consolidation_trace.append(("ledger", args[0]))

        def capture_thought(*args, **kwargs):
            self.sialib._before_corpus_mutation()
            self.trace.append(
                ("page", self.memo.get("sync_needed", False)))
            self.thought_rows.append(args + ((kwargs,) if kwargs else ()))

        def default_rehearsal(*, now=None, stage=None):
            report = {
                "reviewed": [], "embedded": 0, "failed": 0,
                "missing": 0, "planned": [], "decay": {}}
            mind = copy.deepcopy(self.mind)
            if stage is not None:
                stage(mind, report)
            self.sialib.siamind.save_mind(mind)
            return report

        def load_mind(*_args, **_kwargs):
            return copy.deepcopy(self.mind)

        def persist_mind(mind):
            if save_mind is not None:
                save_mind(mind)
            self.mind = copy.deepcopy(mind)

        def queue_transition(_order, action, arg1, arg2, content):
            row = (action, arg1, arg2, content)
            if ledger is not None:
                ledger(*row)
            else:
                capture_ledger(*row)
            return "pending-transition"

        patches = {
            "recover_ledger_transitions": (False, []),
            "load_thoughts": {"v": 1, "thoughts": []},
            "consolidate_corpus": (consolidate if consolidate is not None
                                   else (False, False, False)),
            "durable_ledger_append": ledger or capture_ledger,
            "queue_ledger_transition": queue_transition,
            "_settle_ledger_transition": None,
            "rehearse_memories": rehearse or default_rehearsal,
            "read_json": {},
            "ledger_head": (False, ""),
            "export_thoughts": None,
            "log": None,
            "gbrain": result,
            "load_memo": self.memo,
            "add_thought": add_thought or capture_thought,
            "atomic_write": capture_write,
            "corpus_commit": commit,
            "brain_sync": sync,
            "export_graph": graph,
            "_settle_thought_page_signals": (0, 0),
        }
        with ExitStack() as stack:
            stack.enter_context(mock.patch.dict(sys.modules,
                                                {"siabench": self.fake_bench}))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "recover_grade_transactions",
                return_value=(False, [])))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "migrate_legacy_take_pages",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "due_takes",
                return_value=[] if due_takes is None else due_takes))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "grade_take",
                grade_take or (lambda *_args, **_kwargs: None)))
            if commit_grade is not None:
                stack.enter_context(mock.patch.object(
                    self.sialib.siatakes, "commit_grade_transition",
                    side_effect=commit_grade))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "summary",
                return_value=({"resolved": 0} if grade_summary is None
                              else grade_summary)))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "load_mind", side_effect=load_mind))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "hebb_hygiene", return_value=False))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "muse",
                muse or (lambda *_args, **_kwargs: None)))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "save_mind",
                side_effect=persist_mind))
            for name, value in patches.items():
                replacement = value if callable(value) else mock.Mock(
                    return_value=value)
                stack.enter_context(mock.patch.object(
                    self.sialib, name, replacement))
            return self.sialib._dream_transaction()

    @staticmethod
    def _result(returncode, stdout="", stderr=""):
        return subprocess.CompletedProcess([], returncode, stdout, stderr)

    def test_failed_cycle_preserves_last_success_and_refuses(self):
        with self.assertRaisesRegex(RuntimeError, "gbrain dream cycle failed"):
            self._run(result=self._result(os.EX_SOFTWARE, stderr="failed"))
        self.assertEqual(self.written_memo["dream"]["last"],
                         "previous-success")
        self.assertEqual(self.written_memo["dream"]["status"], "failed")
        self.assertTrue(any(
            row[:3] == ("DREAM:cycle", "failed", "failed")
            for row in self.ledger_rows))

    def test_skipped_cycle_preserves_last_success_and_refuses(self):
        report = {"status": "skipped", "reason": "owner busy"}
        with self.assertRaisesRegex(RuntimeError, "gbrain dream cycle skipped"):
            self._run(result=self._result(os.EX_OK, json.dumps(report)))
        self.assertEqual(self.written_memo["dream"]["last"],
                         "previous-success")
        self.assertEqual(self.written_memo["dream"]["status"], "skipped")

    def test_commit_failure_refuses_before_sync(self):
        with self.assertRaisesRegex(RuntimeError, "corpus git commit failed"):
            self._run(result=self._result(
                os.EX_OK, json.dumps({"status": "ok", "totals": {}})),
                commit="error")
        self.assertEqual(self.ledger_rows[-1][:2],
                         ("DREAM:publish", "error"))
        self.assertIs(self.written_memo.get("sync_needed"), True)

    def test_sync_failure_refuses_and_records_transition(self):
        with self.assertRaisesRegex(RuntimeError, "brain sync failed"):
            self._run(result=self._result(
                os.EX_OK, json.dumps({"status": "ok", "totals": {}})),
                sync=(False, "sync refused"))
        self.assertEqual(self.ledger_rows[-1][:2],
                         ("DREAM:publish", "sync-fail"))
        self.assertIs(self.written_memo.get("sync_needed"), True)

    def test_graph_publication_exception_is_signed_and_refused(self):
        def graph_failure():
            raise OSError("graph refused")

        with self.assertRaisesRegex(RuntimeError, "publication failed"):
            self._run(result=self._result(
                os.EX_OK, json.dumps({"status": "ok", "totals": {}})),
                graph=graph_failure)
        self.assertEqual(self.ledger_rows[-1][:2],
                         ("DREAM:publish", "error"))
        self.assertIs(self.written_memo.get("sync_needed"), True)

    def test_success_returns_report_and_records_publication(self):
        report = {"status": "ok", "totals": {}}

        def graph():
            self.trace.append(
                ("graph", self.memo.get("sync_needed", False)))
            return False, False, False

        self.assertEqual(
            self._run(result=self._result(os.EX_OK, json.dumps(report)),
                      graph=graph),
            report)
        self.assertEqual(self.written_memo["dream"]["status"], "ok")
        self.assertEqual(self.ledger_rows[-1][:2],
                         ("DREAM:publish", "ok"))
        self.assertIn(("graph", True), self.trace)
        self.assertNotIn("sync_needed", self.written_memo)
        self.assertGreater(
            max(i for i, row in enumerate(self.trace)
                if row == ("memo", False)),
            self.trace.index(("graph", True)))

    def test_rehearsal_total_failure_emits_urgent_thought(self):
        def rehearsal(*, now=None, stage=None):
            report = {
                "reviewed": [], "embedded": 0, "failed": 2, "missing": 0,
                "planned": [
                    {"slug": "events/a", "embed": "failed",
                     "error": "Page not found: events/a (source=default)"},
                    {"slug": "events/b", "embed": "failed",
                     "error": "Page not found: events/b (source=default)"},
                ], "decay": {}}
            mind = copy.deepcopy(self.mind)
            if stage is not None:
                stage(mind, report)
            self.sialib.siamind.save_mind(mind)
            return report

        self._run(result=self._result(
            os.EX_OK, json.dumps({"status": "ok", "totals": {}})),
            rehearse=rehearsal)
        failing = [row for row in self.thought_rows
                   if row[1] == "dream" and "could not rehearse" in row[2]]
        self.assertEqual(len(failing), 1)
        self.assertIn("2 embed failure(s)", failing[0][2])
        self.assertIn("Page not found", failing[0][2])
        self.assertEqual(failing[0][3], ["events/a", "events/b"])
        self.assertIs(failing[0][4], True)

    def test_write_ahead_marker_precedes_consolidation_mutation(self):
        def consolidate():
            self.sialib._before_corpus_mutation()
            self.trace.append(
                ("consolidate", self.memo.get("sync_needed", False)))
            return 1, 1, 0

        self._run(
            result=self._result(
                os.EX_OK, json.dumps({"status": "ok", "totals": {}})),
            consolidate=consolidate)
        self.assertLess(self.trace.index(("memo", True)),
                        self.trace.index(("consolidate", True)))

    def test_consolidation_exception_leaves_write_ahead_marker_durable(self):
        def consolidate():
            self.sialib._before_corpus_mutation()
            self.trace.append(
                ("consolidate", self.memo.get("sync_needed", False)))
            raise self.sialib.LedgerTransitionError("keeper refused")

        with self.assertRaisesRegex(
                RuntimeError, "consolidation requires recovery"):
            self._run(
                result=self._result(
                    os.EX_OK, json.dumps({"status": "ok", "totals": {}})),
                consolidate=consolidate)
        self.assertIs(self.written_memo.get("sync_needed"), True)
        consolidate_index = self.trace.index(("consolidate", True))
        self.assertTrue(any(
            row == ("memo", True)
            for row in self.trace[:consolidate_index]))

    def test_consolidation_success_is_signed_before_marker_clear(self):
        def consolidate():
            self.sialib._before_corpus_mutation()
            return 1, 1, 0

        self._run(
            result=self._result(
                os.EX_OK, json.dumps({"status": "ok", "totals": {}})),
            consolidate=consolidate)
        signed = self.consolidation_trace.index(
            ("ledger", "DREAM:consolidate"))
        cleared = next(
            index for index, row in enumerate(self.consolidation_trace)
            if index > signed and row == ("memo", False))
        self.assertLess(signed, cleared)

    def test_recovery_is_signed_before_consolidation_marker_clear(self):
        memo = {"consolidation_pending": {
            "v": 1, "id": "a" * 32,
            "started_at": "2026-08-30T12:00:00Z",
        }, "sync_needed": True}
        trace = []

        def queue(_order, action, _arg1, _arg2, _content):
            trace.append(("ledger", action))
            return "pending"

        def write(_path, payload, mode=None):
            trace.append(("memo", json.loads(payload).get(
                "consolidation_pending", False)))

        with mock.patch.object(self.sialib, "consolidate_corpus",
                               return_value=(1, 1, 0)), \
                mock.patch.object(self.sialib, "queue_ledger_transition",
                                  side_effect=queue), \
                mock.patch.object(self.sialib, "_settle_ledger_transition"), \
                mock.patch.object(self.sialib, "atomic_write",
                                  side_effect=write):
            self.assertEqual(
                self.sialib._recover_pending_consolidation(memo),
                (1, 1, 0))
        signed = trace.index(("ledger", "RECOVER:consolidate"))
        cleared = next(
            index for index, row in enumerate(trace)
            if index > signed and row == ("memo", False))
        self.assertLess(signed, cleared)

    def test_recovery_keeper_failure_retains_consolidation_marker(self):
        memo = {"consolidation_pending": {
            "v": 1, "id": "b" * 32,
            "started_at": "2026-08-30T12:00:00Z",
        }, "sync_needed": True}
        with mock.patch.object(self.sialib, "consolidate_corpus",
                               return_value=(1, 1, 0)), \
                mock.patch.object(
                    self.sialib, "queue_ledger_transition",
                    return_value="pending"), \
                mock.patch.object(
                    self.sialib, "_settle_ledger_transition",
                    side_effect=self.sialib.LedgerTransitionError(
                        "keeper refused")), \
                mock.patch.object(self.sialib, "atomic_write") as write:
            with self.assertRaisesRegex(
                    self.sialib.LedgerTransitionError, "keeper refused"):
                self.sialib._recover_pending_consolidation(memo)
        self.assertIsInstance(memo.get("consolidation_pending"), dict)
        self.assertIn("ledger", memo["consolidation_pending"])
        self.assertIn("applied_at", memo["consolidation_pending"])
        self.assertTrue(write.called)

    def test_rehearsal_keeper_failure_cannot_save_and_retry_can_commit(self):
        report = {
            "reviewed": [{"slug": "events/test/day", "quality": 5}],
            "embedded": 1, "failed": 0, "missing": 0,
            "planned": [], "decay": {}}
        state_saves = []
        refuse_once = [True]

        def rehearsal(*, now=None, stage=None):
            mind = copy.deepcopy(self.mind)
            stage(mind, report)
            self.sialib.siamind.save_mind(mind)
            state_saves.append("saved")
            return report

        def keeper(*row):
            self.ledger_rows.append(row)
            if row[0] == "DREAM:rehearse" and refuse_once[0]:
                refuse_once[0] = False
                raise self.sialib.LedgerTransitionError("keeper refused")

        cycle = self._result(
            os.EX_OK, json.dumps({"status": "ok", "totals": {}}))
        with self.assertRaisesRegex(
                self.sialib.LedgerTransitionError, "keeper refused"):
            self._run(result=cycle, rehearse=rehearsal, ledger=keeper)
        self.assertEqual(state_saves, ["saved"])
        self.assertEqual(self.mind["dream_unit"]["unit"], "rehearse")

        self._run(result=cycle, rehearse=rehearsal, ledger=keeper)
        self.assertNotIn("dream_unit", self.mind)
        attempts = [row for row in self.ledger_rows
                    if row[0] == "DREAM:rehearse"]
        self.assertGreaterEqual(len(attempts), 2)

    def test_rehearsal_function_publishes_before_mind_save(self):
        minds = [{}, {}]
        saved = []
        refuse_once = [True]

        def apply_rehearsal(mind, plan, now=None):
            mind["reviewed"] = plan["slug"]
            return {"slug": plan["slug"], "quality": 5}

        def publish(_mind, _report):
            if refuse_once[0]:
                refuse_once[0] = False
                raise self.sialib.LedgerTransitionError("keeper refused")

        patches = (
            mock.patch.object(self.sialib, "read_json", return_value={}),
            mock.patch.object(self.sialib, "page_exists", return_value=True),
            mock.patch.object(
                self.sialib, "gbrain", return_value=self._result(os.EX_OK)),
            mock.patch.object(
                self.sialib.siamind, "load_mind", side_effect=minds),
            mock.patch.object(
                self.sialib.siamind, "sync_graph_state", return_value=None),
            mock.patch.object(
                self.sialib.siamind, "plan_rehearsal",
                return_value=[{"slug": "events/test/day"}]),
            mock.patch.object(
                self.sialib.siamind, "apply_rehearsal",
                side_effect=apply_rehearsal),
            mock.patch.object(
                self.sialib.siamind, "decay_sweep", return_value={}),
            mock.patch.object(
                self.sialib.siamind, "save_mind",
                side_effect=lambda mind: saved.append(dict(mind))),
        )
        with ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            with self.assertRaisesRegex(
                    self.sialib.LedgerTransitionError, "keeper refused"):
                self.sialib.rehearse_memories(now=1, stage=publish)
            self.assertEqual(saved, [])
            self.sialib.rehearse_memories(now=1, stage=publish)

        self.assertEqual(saved, [{"reviewed": "events/test/day"}])

    def test_musing_keeper_failure_cannot_save_and_retry_can_commit(self):
        state_saves = []
        refuse_once = [True]

        def muse(mind, *_args, **_kwargs):
            mind["musing_day"] = "prepared"
            return ("association", ["sia/cortex"])

        def save_mind(mind):
            state_saves.append(dict(mind))

        def keeper(*row):
            self.ledger_rows.append(row)
            if row[0] == "DREAM:muse" and refuse_once[0]:
                refuse_once[0] = False
                raise self.sialib.LedgerTransitionError("keeper refused")

        cycle = self._result(
            os.EX_OK, json.dumps({"status": "ok", "totals": {}}))
        with self.assertRaisesRegex(
                self.sialib.LedgerTransitionError, "keeper refused"):
            self._run(result=cycle, ledger=keeper, muse=muse,
                      save_mind=save_mind)
        self.assertEqual(self.mind["dream_unit"]["unit"], "muse")
        self.assertEqual(state_saves[-1]["dream_unit"]["unit"], "muse")

        self._run(result=cycle, ledger=keeper, muse=muse,
                  save_mind=save_mind)
        self.assertNotIn("dream_unit", self.mind)
        attempts = [row for row in self.ledger_rows
                    if row[0] == "DREAM:muse"]
        self.assertGreaterEqual(len(attempts), 2)

    def test_due_grade_refusals_are_not_signed_as_none_due(self):
        report = {"status": "ok", "totals": {}}
        self._run(
            result=self._result(os.EX_OK, json.dumps(report)),
            due_takes=[{"id": "due-take"}],
            grade_take=lambda *_args, **_kwargs: None)
        grade_rows = [row for row in self.ledger_rows
                      if row[0] == "DREAM:grade"]
        self.assertEqual(grade_rows, [
            ("DREAM:grade", "refused",
             "attempted=1 completed=0 refused=1")])

    def test_multigrade_publishes_before_next_gbrain_grade(self):
        takes = [
            {"id": "first", "claim": "first held"},
            {"id": "second", "claim": "second held"},
        ]

        def commit_grade(row, _verdict, _justification, _evidence,
                         before_publish=None):
            before_publish()
            self.trace.append((
                "grade-page", row["id"],
                self.memo.get("sync_needed", False)))

        def grade_take(row, persist=None):
            self.trace.append((
                "gbrain-grade", row["id"],
                self.memo.get("sync_needed", False)))
            self.assertNotIn("sync_needed", self.memo)
            persist(row, "resolved-true", "held", [])
            self.assertNotIn("sync_needed", self.memo)
            return {"status": "resolved-true", "brier": None,
                    "claim": row["claim"], "slug": "takes/" + row["id"]}

        def corpus_commit(_message):
            self.trace.append(
                ("commit", self.memo.get("sync_needed", False)))
            return "committed"

        def brain_sync():
            self.trace.append(
                ("sync", self.memo.get("sync_needed", False)))
            return True, ""

        def export_graph():
            self.trace.append(
                ("graph", self.memo.get("sync_needed", False)))
            return False, False, False

        self._run(
            result=self._result(
                os.EX_OK, json.dumps({"status": "ok", "totals": {}})),
            due_takes=takes, grade_take=grade_take,
            commit_grade=commit_grade, commit=corpus_commit,
            sync=brain_sync, graph=export_graph,
            grade_summary={"resolved": 0})

        first = self.trace.index(("gbrain-grade", "first", False))
        second = self.trace.index(("gbrain-grade", "second", False))
        between = self.trace[first:second]
        self.assertIn(("grade-page", "first", True), between)
        self.assertIn(("graph", True), between)
        self.assertIn(("memo", False), between)
        self.assertNotIn("sync_needed", self.memo)

    def test_multigrade_publication_failure_aborts_later_grade_and_cycle(self):
        takes = [
            {"id": "first", "claim": "first held"},
            {"id": "second", "claim": "second held"},
        ]
        judged = []

        def commit_grade(_row, _verdict, _justification, _evidence,
                         before_publish=None):
            before_publish()

        def grade_take(row, persist=None):
            judged.append(row["id"])
            persist(row, "resolved-true", "held", [])
            return {"status": "resolved-true", "brier": None,
                    "claim": row["claim"], "slug": "takes/" + row["id"]}

        gbrain_cycle = mock.Mock(return_value=self._result(
            os.EX_OK, json.dumps({"status": "ok", "totals": {}})))
        with self.assertRaisesRegex(RuntimeError, "pending brain sync failed"):
            self._run(
                result=gbrain_cycle, due_takes=takes,
                grade_take=grade_take, commit_grade=commit_grade,
                commit="committed", sync=(False, "index refused"),
                grade_summary={"resolved": 0})

        self.assertEqual(judged, ["first"])
        self.assertIs(self.memo.get("sync_needed"), True)
        gbrain_cycle.assert_not_called()

    def test_none_due_is_reserved_for_an_empty_due_set(self):
        self._run(result=self._result(
            os.EX_OK, json.dumps({"status": "ok", "totals": {}})))
        grade_rows = [row for row in self.ledger_rows
                      if row[0] == "DREAM:grade"]
        self.assertEqual(grade_rows, [("DREAM:grade", "none-due", "")])

    def test_nightly_grade_thought_is_model_origin(self):
        grade = {
            "status": "resolved-true", "brier": None,
            "claim": "the held outcome", "slug": "takes/held"}
        self._run(
            result=self._result(
                os.EX_OK, json.dumps({"status": "ok", "totals": {}})),
            due_takes=[{"id": "due-take"}],
            grade_take=lambda *_args, **_kwargs: grade)
        grade_thoughts = [row for row in self.thought_rows
                          if len(row) > 1 and row[1] == "grade"]
        self.assertEqual(len(grade_thoughts), 1)
        self.assertEqual(grade_thoughts[0][-1], {"origin": "model"})

    def test_quick_tripwire_uses_explicit_heuristic_metrics(self):
        self.fake_bench = types.SimpleNamespace(run_quick=lambda: {
            "schema": "sia-heuristic-slug-retrieval-tripwire-v1",
            "kind": "heuristic-slug-retrieval-drift-tripwire",
            "date": "2026-08-30",
            "probe_count": 4,
            "slug_match_at_5_blend": 0.75,
            "slug_match_at_5_keyword": 0.5,
            "reciprocal_slug_rank_blend": 0.5,
            "reciprocal_slug_rank_keyword": 0.25,
            "non_claims": ["no answer correctness"],
        })
        report = {"status": "ok", "totals": {}}
        with tempfile.TemporaryDirectory() as state, mock.patch.object(
                self.sialib, "STATE", state):
            self._run(result=self._result(os.EX_OK, json.dumps(report)))
            trend = self.sialib._bench_trend_snapshot(
                os.path.join(state, "bench-trend.jsonl"))

        self.assertEqual(trend[0]["slug_match_at_5"], 0.75)
        bench_rows = [row for row in self.ledger_rows
                      if row and row[0] == "DREAM:bench"]
        self.assertEqual(bench_rows[0][1], "blend-slug-match@5=0.75")
        self.assertIn("no answer correctness was evaluated",
                      " ".join(str(value) for row in self.thought_rows
                               for value in row))

    def test_bench_trend_migrates_legacy_name_and_skips_bad_rows(self):
        with tempfile.TemporaryDirectory() as state:
            path = os.path.join(state, "bench-trend.jsonl")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write('{"date":"2026-08-28","hit5_blend":0.25}\n')
                stream.write('not json\n')
                stream.write('{"date":"2026-08-29","hit5_blend":true}\n')
                stream.write('{"date":"2026-08-30",'
                             '"slug_match_at_5_blend":0.75}\n')
            rows = self.sialib._bench_trend_snapshot(path)

        self.assertEqual(
            rows,
            [{"date": "2026-08-28", "slug_match_at_5": 0.25,
              "kind": "heuristic-slug-retrieval-drift-tripwire"},
             {"date": "2026-08-30", "slug_match_at_5": 0.75,
              "kind": "heuristic-slug-retrieval-drift-tripwire"}])

    def test_bench_trend_upgrade_reads_only_bounded_legacy_tail(self):
        with tempfile.TemporaryDirectory() as state:
            path = os.path.join(state, "bench-trend.jsonl")
            with open(path, "w", encoding="utf-8") as stream:
                for _index in range(32):
                    stream.write(
                        '{"date":"2026-08-28","hit5_blend":0.25}\n')
            rows = self.sialib._bench_trend_snapshot(path)
        self.assertEqual(len(rows), self.sialib.MAX_BENCH_TREND_ROWS)
        self.assertTrue(all(
            row["slug_match_at_5"] == 0.25 for row in rows))

    def test_bench_trend_symlink_is_refused_without_following(self):
        with tempfile.TemporaryDirectory() as state:
            target = os.path.join(state, "target.jsonl")
            with open(target, "w", encoding="utf-8") as stream:
                stream.write(
                    '{"date":"2026-08-28","hit5_blend":0.25}\n')
            link = os.path.join(state, "bench-trend.jsonl")
            os.symlink(target, link)
            with self.assertRaises(OSError):
                self.sialib._bench_trend_snapshot(link)

    def test_bench_trend_newline_free_legacy_overflow_is_exposed_and_empty(self):
        with tempfile.TemporaryDirectory() as state:
            path = os.path.join(state, "bench-trend.jsonl")
            with open(path, "wb") as stream:
                stream.write(
                    b"x" * (self.sialib.MAX_BENCH_TREND_BYTES + 1))
            rows, boundary = self.sialib._bench_trend_snapshot(
                path, include_metadata=True)
        self.assertEqual(rows, [])
        self.assertTrue(boundary["legacy_truncated"])

    def test_bench_trend_legacy_line_ceiling_retains_recent_complete_rows(self):
        with tempfile.TemporaryDirectory() as state:
            path = os.path.join(state, "bench-trend.jsonl")
            with open(path, "w", encoding="utf-8") as stream:
                for index in range(
                        self.sialib.MAX_BENCH_TREND_INPUT_LINES + 1):
                    stream.write(json.dumps({
                        "date": "2026-08-30",
                        "hit5_blend": 0.25,
                        "legacy_index": index,
                    }) + "\n")
            rows, boundary = self.sialib._bench_trend_snapshot(
                path, include_metadata=True)
        self.assertEqual(len(rows), self.sialib.MAX_BENCH_TREND_ROWS)
        self.assertTrue(boundary["legacy_truncated"])

    def test_bench_trend_replacement_during_read_is_refused(self):
        with tempfile.TemporaryDirectory() as state:
            path = os.path.join(state, "bench-trend.jsonl")
            replacement = os.path.join(state, "replacement.jsonl")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(
                    '{"date":"2026-08-28","hit5_blend":0.25}\n')
            with open(replacement, "w", encoding="utf-8") as stream:
                stream.write(
                    '{"date":"2026-08-29","hit5_blend":0.75}\n')
            real_lstat = os.lstat

            def replace_then_stat(candidate):
                os.replace(replacement, path)
                return real_lstat(candidate)

            with mock.patch.object(
                    self.sialib.os, "lstat",
                    side_effect=replace_then_stat), \
                    self.assertRaisesRegex(ValueError, "changed"):
                self.sialib._bench_trend_snapshot(path)

    def test_bench_trend_rotates_before_receipt_can_deadlock_recovery(self):
        with tempfile.TemporaryDirectory() as state, \
                mock.patch.object(self.sialib, "STATE", state), \
                mock.patch.object(self.sialib, "MAX_MEMO_BYTES", 180):
            path = os.path.join(state, "bench-trend.jsonl")
            with open(path, "wb") as stream:
                stream.write(b'{"legacy":"' + b"x" * 130 + b'"}\n')
            record = {"date": "2026-08-30", "slug_match_at_5": 0.75}
            receipt_id = "a" * 32
            self.assertTrue(self.sialib._append_bench_trend_once(
                record, receipt_id))
            self.assertFalse(self.sialib._append_bench_trend_once(
                record, receipt_id))
            with open(path, "rb") as stream:
                persisted = stream.read()
        self.assertLessEqual(len(persisted), 180)
        self.assertIn(receipt_id.encode(), persisted)

    def test_oversized_legacy_trend_cannot_strand_dream_receipt_or_readiness(self):
        path = os.path.join(self.state_root.name, "bench-trend.jsonl")
        legacy = b'{"date":"2026-08-29","hit5_blend":0.25}\n'
        with open(path, "wb") as stream:
            stream.write(b"x" * (self.sialib.MAX_BENCH_TREND_BYTES + 1))
            stream.write(b"\n" + legacy)
        record = {
            "date": "2026-08-30",
            "slug_match_at_5_blend": 0.75,
        }
        mind = {}
        receipt = self.sialib._stage_dream_unit(
            mind, "bench", "DREAM:bench", "blend-slug-match@5=0.75",
            "probes=1", "heuristic only", trend=record)
        real_save = self.sialib.siamind.save_mind
        real_save(mind)
        fail_once = [True]

        def crash_after_trend(value):
            if fail_once[0]:
                fail_once[0] = False
                raise OSError("simulated crash after trend replacement")
            return real_save(value)

        store = {"v": 1, "thoughts": []}
        with mock.patch.object(
                self.sialib, "queue_ledger_transition",
                return_value="pending"), \
                mock.patch.object(
                    self.sialib, "_settle_ledger_transition"), \
                mock.patch.object(
                    self.sialib.siamind, "save_mind",
                    side_effect=crash_after_trend):
            with self.assertRaisesRegex(
                    self.sialib.LedgerTransitionError,
                    "recovery remains pending"):
                self.sialib._settle_pending_dream_unit(store, "bench")
            self.assertIsNotNone(self.sialib._pending_dream_unit(
                self.sialib.siamind.load_mind()))
            self.sialib._settle_pending_dream_unit(store, "bench")

        persisted = self.sialib.siamind.load_mind()
        self.assertIsNone(self.sialib._pending_dream_unit(persisted))
        lines, compacted = self.sialib._read_bench_trend_tail(path)
        matching = [json.loads(line) for line in lines
                    if json.loads(line).get("dream_unit_id") == receipt["id"]]
        self.assertEqual(len(matching), 1)
        self.assertTrue(matching[0]["legacy_history_truncated"])
        self.assertFalse(compacted)
        rows, boundary = self.sialib._bench_trend_snapshot(
            path, include_metadata=True)
        self.assertTrue(rows)
        self.assertTrue(boundary["legacy_truncated"])

        with mock.patch.object(
                self.sialib, "corpus_owner",
                return_value=nullcontext()), \
                mock.patch.object(
                    self.sialib, "load_memo", return_value=self.memo), \
                mock.patch.object(
                    self.sialib, "_consolidation_scan_debt",
                    return_value=""), \
                mock.patch.object(
                    self.sialib, "_thought_recovery_debt",
                    return_value=""), \
                mock.patch.object(
                    self.sialib, "_graph_projection_debt",
                    return_value=""), \
                mock.patch.object(
                    self.sialib.siatakes,
                    "natural_history_recovery_required",
                    return_value=False), \
                mock.patch.object(
                    self.sialib.siatakes, "grade_recovery_required",
                    return_value=False), \
                mock.patch.object(
                    self.sialib.siatakes, "take_migration_required",
                    return_value=False), \
                mock.patch.object(
                    self.sialib.siatakes, "intent_history_required",
                    return_value=False):
            self.assertEqual(self.sialib.memory_readiness(), (True, ""))


class ThoughtOrigins(unittest.TestCase):
    def setUp(self):
        self.sialib = _load(
            "sialib_thought_origin_test", os.path.join(BIN, "sialib.py"))
        self.state_root = tempfile.TemporaryDirectory()
        self.old_state_paths = (
            self.sialib.STATE, self.sialib.CORPUS_OWNER_LOCK,
            self.sialib.THOUGHTS_PATH, self.sialib.siamind.MIND_PATH,
            self.sialib.LIFECYCLE_LOCK,
            self.sialib.LIFECYCLE_TOMBSTONE)
        self.sialib.STATE = self.state_root.name
        self.sialib.CORPUS_OWNER_LOCK = os.path.join(
            self.state_root.name, "corpus-owner.lock")
        self.sialib.THOUGHTS_PATH = os.path.join(
            self.state_root.name, "thoughts.json")
        self.sialib.siamind.MIND_PATH = os.path.join(
            self.state_root.name, "mind.json")
        self.sialib.LIFECYCLE_LOCK = os.path.join(
            self.state_root.name, "lifecycle.lock")
        self.sialib.LIFECYCLE_TOMBSTONE = os.path.join(
            self.state_root.name, "lifecycle-removed")

    def tearDown(self):
        (self.sialib.STATE, self.sialib.CORPUS_OWNER_LOCK,
         self.sialib.THOUGHTS_PATH,
         self.sialib.siamind.MIND_PATH, self.sialib.LIFECYCLE_LOCK,
         self.sialib.LIFECYCLE_TOMBSTONE) = self.old_state_paths
        self.state_root.cleanup()

    def test_inbox_preserves_explicit_origin_and_defaults_new_rows(self):
        explicit = self.sialib._canonical_thought_inbox_item(
            {"kind": "note", "text": "model prose", "origin": "model"},
            queued=False)
        defaulted = self.sialib._canonical_thought_inbox_item(
            {"kind": "attention", "text": "deterministic"}, queued=False)
        legacy_queued = self.sialib._canonical_thought_inbox_item({
            "kind": "ponder", "text": "pre-upgrade model prose",
            "_queue_id": "b" * 32,
            "_queued_at": "2026-01-02T03:04:05Z"}, queued=True)
        self.assertEqual(explicit["origin"], "model")
        self.assertEqual(defaulted["origin"], "derived")
        self.assertEqual(legacy_queued["origin"], "model")
        with self.assertRaisesRegex(ValueError, "thought origin"):
            self.sialib._canonical_thought_inbox_item(
                {"kind": "note", "text": "bad", "origin": "trusted"},
                queued=False)

    def test_legacy_store_does_not_launder_unknown_rows_as_derived(self):
        legacy = {"v": 1, "thoughts": [
            {"kind": "grade", "text": "judge output"},
            {"kind": "ponder", "text": "model synthesis"},
            {"kind": "note", "text": "agent prose"},
            {"kind": "attention", "text": "unknown old generator"},
        ]}
        with mock.patch.object(
                self.sialib, "read_state_json", return_value=legacy):
            loaded = self.sialib.load_thoughts()
        self.assertEqual(
            [row.get("origin") for row in loaded["thoughts"]],
            ["model", "model", "model", None])

    def test_write_thought_persists_origin_and_upgrades_exact_legacy_retry(self):
        thought = {
            "ts": "2026-01-02T03:04:05Z", "kind": "note",
            "text": "remembered model prose", "links": ["sia/cortex"],
            "urgent": False, "origin": "model", "queue_id": "a" * 32}
        slug = self.sialib._queued_thought_slug(thought["queue_id"])
        legacy_fm = [
            "type: thought", self.sialib.fm_title(thought["text"]),
            "tags: [thought, note]", "date: 2026-01-02",
            f"queue_id: {thought['queue_id']}"]
        legacy_body = (
            "# thought · note\n\nremembered model prose\n\n"
            "[[sia/cortex]]\n")

        with tempfile.TemporaryDirectory() as corpus:
            old_corpus = self.sialib.CORPUS
            self.sialib.CORPUS = corpus
            try:
                self.sialib.write_page(slug, legacy_fm, legacy_body)
                self.assertEqual(self.sialib.write_thought(thought), slug)
                with open(self.sialib.corpus_path(slug)) as stream:
                    upgraded = stream.read()
                self.assertIn("\norigin: model\n", upgraded)

                tampered = upgraded.replace(
                    "remembered model prose", "different prose")
                self.sialib.atomic_write(
                    self.sialib.corpus_path(slug), tampered)
                with self.assertRaisesRegex(ValueError, "conflicts"):
                    self.sialib.write_thought(thought)
                with open(self.sialib.corpus_path(slug)) as stream:
                    self.assertEqual(stream.read(), tampered)
            finally:
                self.sialib.CORPUS = old_corpus

    def test_queue_page_identity_survives_projection_aging(self):
        queue_id = "e" * 32
        store = {"v": 1, "thoughts": []}
        with tempfile.TemporaryDirectory() as corpus, \
                mock.patch.object(self.sialib.siamind, "queue_touches",
                                  return_value=True):
            old_corpus = self.sialib.CORPUS
            self.sialib.CORPUS = corpus
            try:
                first = self.sialib.add_thought(
                    store, "note", "durable identity", ["sia/cortex"],
                    queue_id=queue_id,
                    thought_ts="2026-01-02T03:04:05Z", origin="model")
                expected_slug = self.sialib._queued_thought_slug(queue_id)
                self.assertEqual(first["slug"], expected_slug)
                with open(self.sialib.corpus_path(expected_slug)) as stream:
                    original_page = stream.read()

                # thoughts.json is a bounded projection.  The exact page is
                # the durable identity once an older row ages out.
                store["thoughts"].clear()
                retried = self.sialib.add_thought(
                    store, "note", "durable identity", ["sia/cortex"],
                    queue_id=queue_id,
                    thought_ts="2026-02-03T04:05:06Z", origin="model")

                self.assertEqual(retried, first)
                self.assertEqual(store["thoughts"], [first])
                self.assertEqual(
                    os.listdir(os.path.join(corpus, "thoughts")),
                    [expected_slug.split("/", 1)[1] + ".md"])
                with open(self.sialib.corpus_path(expected_slug)) as stream:
                    self.assertEqual(stream.read(), original_page)
            finally:
                self.sialib.CORPUS = old_corpus

    def test_existing_queued_thought_reuses_one_page_bound_intent(self):
        queue_id = "7" * 32
        store = {"v": 1, "thoughts": []}
        with tempfile.TemporaryDirectory() as corpus, \
                mock.patch.object(
                    self.sialib.siamind, "queue_touches",
                    side_effect=[False, True]) as touches:
            old_corpus = self.sialib.CORPUS
            self.sialib.CORPUS = corpus
            try:
                first = self.sialib.add_thought(
                    store, "note", "repair rehearsal", ["sia/cortex"],
                    queue_id=queue_id,
                    thought_ts="2026-01-02T03:04:05Z", origin="model")
                retried = self.sialib.add_thought(
                    store, "note", "repair rehearsal", ["sia/cortex"],
                    queue_id=queue_id,
                    thought_ts="2026-01-02T03:04:05Z", origin="model")
                self.assertEqual(retried, first)
                touches.assert_not_called()
                recovery = self.sialib._thought_recovery_record(first)
                self.assertEqual(os.listdir(
                    self.sialib._thought_recovery_dir()),
                    [recovery["record_id"] + ".json"])
            finally:
                self.sialib.CORPUS = old_corpus

    def test_recovery_reconstructs_nonqueued_thought_reinforcement(self):
        store = {"v": 1, "thoughts": []}
        mind = self.sialib.siamind._empty_mind()
        with tempfile.TemporaryDirectory() as corpus:
            old_corpus = self.sialib.CORPUS
            self.sialib.CORPUS = corpus
            try:
                with mock.patch.object(
                        self.sialib.siamind, "queue_touches",
                        return_value=False):
                    thought = self.sialib.add_thought(
                        store, "grade", "durable unqueued page",
                        ["units/a", "units/b"],
                        thought_ts="2026-01-02T03:04:05Z", origin="model")
                before = json.loads(json.dumps(mind))
                recovered, reinforced = self.sialib.reconcile_thought_pages(
                    store, mind=mind)
                self.assertEqual(recovered, 0)
                self.assertNotEqual(mind, before)
                self.assertGreater(reinforced, 0)
                after_first = json.loads(json.dumps(mind))
                recovered, reinforced = self.sialib.reconcile_thought_pages(
                    store, mind=mind)
                self.assertEqual((recovered, reinforced), (0, 0))
                self.assertEqual(mind, after_first)
                self.assertEqual(thought["slug"], store["thoughts"][0]["slug"])
            finally:
                self.sialib.CORPUS = old_corpus

    def test_recovery_applies_thought_pages_in_timestamp_order(self):
        store = {"v": 1, "thoughts": []}
        mind = self.sialib.siamind._empty_mind()
        with tempfile.TemporaryDirectory() as corpus, \
                mock.patch.object(self.sialib.siamind, "queue_touches",
                                  return_value=False):
            old_corpus = self.sialib.CORPUS
            self.sialib.CORPUS = corpus
            try:
                # The later page sorts first by queue slug. Timestamp order
                # must still preserve both distinct edges through the shared
                # receipt node.
                self.sialib.add_thought(
                    store, "note", "older", ["units/common", "units/old"],
                    queue_id="f" * 32,
                    thought_ts="2026-01-02T03:04:05Z", origin="model")
                self.sialib.add_thought(
                    store, "note", "later", ["units/common", "units/new"],
                    queue_id="0" * 32,
                    thought_ts="2026-01-02T03:04:06Z", origin="model")
                self.sialib.reconcile_thought_pages(store, mind=mind)
                self.assertIn("units/common|units/old", mind["edges"])
                self.assertIn("units/common|units/new", mind["edges"])
            finally:
                self.sialib.CORPUS = old_corpus

    def test_recovery_reconciles_page_signal_without_sync_debt(self):
        store = {"v": 1, "thoughts": []}
        with tempfile.TemporaryDirectory() as root, \
                mock.patch.object(self.sialib.siamind, "queue_touches",
                                  return_value=False):
            corpus = os.path.join(root, "corpus")
            mind_path = os.path.join(root, "mind.json")
            old_corpus = self.sialib.CORPUS
            old_mind_path = self.sialib.siamind.MIND_PATH
            self.sialib.CORPUS = corpus
            self.sialib.siamind.MIND_PATH = mind_path
            try:
                self.sialib.siamind.save_mind(
                    self.sialib.siamind._empty_mind())
                self.sialib.add_thought(
                    store, "grade", "repair without named debt", ["units/a"],
                    thought_ts="2026-01-02T03:04:05Z", origin="model")
                self.sialib._recover_pending_thought_projection(
                    {"sync_needed": False}, store)
                persisted = self.sialib.siamind.load_mind()
                self.assertIn("thought", persisted["nodes"]["units/a"]["signals"])
            finally:
                self.sialib.CORPUS = old_corpus
                self.sialib.siamind.MIND_PATH = old_mind_path

    def test_aged_out_queue_identity_conflict_is_fail_closed(self):
        queue_id = "f" * 32
        store = {"v": 1, "thoughts": []}
        with tempfile.TemporaryDirectory() as corpus, \
                mock.patch.object(self.sialib.siamind, "queue_touches",
                                  return_value=True):
            old_corpus = self.sialib.CORPUS
            self.sialib.CORPUS = corpus
            try:
                first = self.sialib.add_thought(
                    store, "note", "bound payload", ["sia/cortex"],
                    queue_id=queue_id,
                    thought_ts="2026-01-02T03:04:05Z", origin="model")
                path = self.sialib.corpus_path(first["slug"])
                with open(path) as stream:
                    original_page = stream.read()
                store["thoughts"].clear()

                with self.assertRaisesRegex(ValueError, "conflicts"):
                    self.sialib.add_thought(
                        store, "note", "different payload", ["sia/cortex"],
                        queue_id=queue_id,
                        thought_ts="2026-02-03T04:05:06Z", origin="model")

                self.assertEqual(store["thoughts"], [])
                with open(path) as stream:
                    self.assertEqual(stream.read(), original_page)
            finally:
                self.sialib.CORPUS = old_corpus

    def test_failed_page_write_leaves_thought_projection_unchanged(self):
        store = {"v": 1, "thoughts": [{
            "ts": "2026-01-01T00:00:00Z", "kind": "attention",
            "text": "existing", "links": ["sia/cortex"],
            "urgent": False, "origin": "derived",
            "slug": "thoughts/existing"}]}
        before = json.loads(json.dumps(store))
        with mock.patch.object(self.sialib, "page_exists",
                               return_value=False), \
                mock.patch.object(self.sialib, "write_page",
                                  side_effect=OSError("page fsync refused")), \
                mock.patch.object(self.sialib.siamind,
                                  "queue_touches") as touches:
            with self.assertRaisesRegex(OSError, "page fsync refused"):
                self.sialib.add_thought(
                    store, "attention", "new thought", ["sia/cortex"],
                    thought_ts="2026-01-02T03:04:05Z")
        self.assertEqual(store, before)
        touches.assert_not_called()

    def test_self_described_orphan_page_rejoins_projection(self):
        thought = {
            "ts": "2026-01-02T03:04:05Z", "kind": "note",
            "text": "recover me", "links": ["sia/cortex"],
            "urgent": False, "origin": "model", "queue_id": "c" * 32}
        with tempfile.TemporaryDirectory() as corpus:
            old_corpus = self.sialib.CORPUS
            self.sialib.CORPUS = corpus
            try:
                slug = self.sialib.write_thought(thought)
                store = {"v": 1, "thoughts": []}
                self.assertEqual(
                    self.sialib.reconcile_thought_pages(store), 1)
                self.assertEqual(store["thoughts"][0]["slug"], slug)
                self.assertEqual(store["thoughts"][0]["text"],
                                 "recover me")
            finally:
                self.sialib.CORPUS = old_corpus

    def test_misbound_orphan_refuses_without_clearing_debt(self):
        thought = {
            "ts": "2026-01-02T03:04:05Z", "kind": "note",
            "text": "recover me", "links": ["sia/cortex"],
            "urgent": False, "origin": "model", "queue_id": "d" * 32}
        with tempfile.TemporaryDirectory() as corpus:
            old_corpus = self.sialib.CORPUS
            self.sialib.CORPUS = corpus
            try:
                slug = self.sialib.write_thought(thought)
                path = self.sialib.corpus_path(slug)
                with open(path) as stream:
                    content = stream.read()
                content = content.replace(
                    f'"slug": "{slug}"',
                    '"slug": "thoughts/different"')
                self.sialib.atomic_write(path, content)
                memo = {"sync_needed": True}
                with mock.patch.object(
                        self.sialib, "export_thoughts") as export:
                    with self.assertRaisesRegex(
                            RuntimeError, "binds another page"):
                        self.sialib._recover_pending_thought_projection(
                            memo, {"v": 1, "thoughts": []})
                self.assertIs(memo.get("sync_needed"), True)
                export.assert_not_called()
            finally:
                self.sialib.CORPUS = old_corpus


class RehearsalEmbedContract(unittest.TestCase):
    """rehearse_memories must address pages in the registered gbrain source.

    The per-page embed ran without --source for the project's whole history,
    so gbrain looked the slug up in its "default" source, answered "Page not
    found", and every nightly rehearsal failed with reviewed=0 (issue #3).
    """

    def setUp(self):
        self.sialib = _load(
            "sialib_rehearse_test", os.path.join(BIN, "sialib.py"))

    def _rehearse(self, gbrain_result, apply_result=None):
        calls = []

        def fake_gbrain(args, timeout=120, json_out=False):
            calls.append(list(args))
            return gbrain_result

        plan = {"slug": "events/skills/2026-08-31", "quality": 5}
        with ExitStack() as stack:
            for name, replacement in (
                    ("gbrain", fake_gbrain),
                    ("page_exists", lambda _slug: True),
                    ("read_json", lambda *_args, **_kwargs: {})):
                stack.enter_context(
                    mock.patch.object(self.sialib, name, replacement))
            for name, replacement in (
                    ("load_mind", lambda now=None: {}),
                    ("sync_graph_state", lambda *_args, **_kwargs: None),
                    ("plan_rehearsal",
                     lambda _mind, now=None: [dict(plan)]),
                    ("apply_rehearsal",
                     lambda _mind, _plan, now=None: apply_result),
                    ("decay_sweep", lambda _mind, now=None: {}),
                    ("save_mind", lambda _mind: None)):
                stack.enter_context(
                    mock.patch.object(self.sialib.siamind, name, replacement))
            report = self.sialib.rehearse_memories(now=0.0)
        return calls, report

    def test_embed_names_the_registered_source(self):
        committed = {"slug": "events/skills/2026-08-31", "quality": 5}
        calls, report = self._rehearse(
            subprocess.CompletedProcess([], 0, "", ""),
            apply_result=committed)
        self.assertEqual(calls, [[
            "embed", "events/skills/2026-08-31",
            "--source", self.sialib.GBRAIN_SOURCE]])
        self.assertEqual(report["embedded"], 1)
        self.assertEqual(report["failed"], 0)
        self.assertEqual(report["reviewed"][0]["embed"], "ok")

    def test_failed_embed_records_bounded_reason(self):
        calls, report = self._rehearse(subprocess.CompletedProcess(
            [], 1,
            "Page not found: events/skills/2026-08-31 (source=default)\n",
            ""))
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["reviewed"], [])
        item = report["planned"][0]
        self.assertEqual(item["embed"], "failed")
        self.assertIn("Page not found", item["error"])
        self.assertLessEqual(len(item["error"]), 160)
        self.assertNotIn("\n", item["error"])


if __name__ == "__main__":
    unittest.main(verbosity=True)
