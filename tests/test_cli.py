#!/usr/bin/env python3
"""Focused regression tests for the user-facing SIA CLI."""

import ast
import contextlib
import datetime
import gc
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import warnings
from unittest import mock


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIA_PATH = os.path.join(REPO, "bin", "sia")
BRAINSTEM_PATH = os.path.join(REPO, "bin", "sia-brainstem")


def _load_script(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _read(path):
    with open(path, encoding="utf-8") as stream:
        return stream.read()


sia = _load_script("sia_cli_test", SIA_PATH)
brainstem = _load_script("sia_brainstem_test", BRAINSTEM_PATH)
import siatakes


class RuntimeResolution(unittest.TestCase):
    def test_source_and_installed_launchers_both_find_runtime_modules(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home, PYTHONDONTWRITEBYTECODE="1")
            source_run = subprocess.run(
                [sys.executable, SIA_PATH], env=env, capture_output=True,
                text=True)
            self.assertEqual(source_run.returncode, 2, source_run.stderr)

            launcher_dir = os.path.join(home, ".local", "bin")
            runtime_dir = os.path.join(
                home, ".local", "share", "sia", "bin")
            os.makedirs(launcher_dir)
            os.makedirs(runtime_dir)
            launcher = os.path.join(launcher_dir, "sia")
            shutil.copyfile(SIA_PATH, launcher)
            with open(os.path.join(runtime_dir, "sialib.py"), "w",
                      encoding="utf-8") as stream:
                stream.write(
                    "import contextlib\n"
                    "@contextlib.contextmanager\n"
                    "def _lifecycle_reader():\n"
                    "    yield\n")

            installed_run = subprocess.run(
                [sys.executable, launcher], env=env, capture_output=True,
                text=True)
            self.assertEqual(installed_run.returncode, 2,
                             installed_run.stderr)


class DispatchAndOwnership(unittest.TestCase):
    def test_agent_proposal_cli_rechecks_future_deadline_before_queue(self):
        observed = {}
        payload = {"claim": "future claim", "confidence": 0.7,
                   "deadline": "2026-12-31", "domain": "general",
                   "proposed": "agent", "source": "sia/cortex"}

        def validate(proposal, **kwargs):
            observed["proposal"] = proposal
            observed["kwargs"] = kwargs
            return {**proposal, "proposal_id": "a" * 20}

        def locked(_state, mutate):
            observed["queued"] = mutate([])

        with mock.patch.object(siatakes, "validate_proposal",
                               side_effect=validate), \
                mock.patch.object(siatakes, "locked_proposals",
                                  side_effect=locked), \
                contextlib.redirect_stdout(io.StringIO()):
            result = sia.cmd_agent_propose(json.dumps(payload))
        self.assertEqual(result, 0)
        self.assertEqual(observed["proposal"], payload)
        self.assertEqual(observed["kwargs"], {"require_future": True})
        self.assertEqual(observed["queued"][0]["proposal_id"], "a" * 20)

    def test_agent_proposal_parser_limits_are_clean_source_free_refusals(self):
        for parser_error in (ValueError, RecursionError):
            output = io.StringIO()
            with self.subTest(parser_error=parser_error.__name__), \
                    mock.patch.object(
                        sia.json, "loads",
                        side_effect=parser_error("private source content")), \
                    contextlib.redirect_stdout(output):
                result = sia.cmd_agent_propose("{}")
            self.assertEqual(result, 2)
            self.assertEqual(
                output.getvalue(),
                "proposal rejected: payload is malformed JSON\n")

    def test_gated_dispatch_holds_one_reentrant_corpus_lease(self):
        trace = []
        held = {"value": False}

        @contextlib.contextmanager
        def physical_lease(_path, _label, **_kwargs):
            self.assertFalse(held["value"])
            held["value"] = True
            trace.append("lease-enter")
            try:
                yield
            finally:
                trace.append("lease-exit")
                held["value"] = False

        def load_memo():
            self.assertTrue(held["value"])
            trace.append("readiness-memo")
            return {"sync_needed": False, "ready": {
                "v": 1, "completed_at": "2026-08-30T12:00:00Z",
                "kind": "recovery", "identity": "0" * 32}}

        def grade_required():
            self.assertTrue(held["value"])
            trace.append("readiness-grades")
            return False

        def history_required():
            self.assertTrue(held["value"])
            trace.append("readiness-history")
            return False

        def migration_required():
            self.assertTrue(held["value"])
            trace.append("readiness-migrations")
            return False

        def intent_history_required():
            self.assertTrue(held["value"])
            trace.append("readiness-intents")
            return False

        def ponder(_question):
            self.assertTrue(held["value"])
            trace.append("dispatch")
            with sia.sialib.corpus_owner():
                self.assertTrue(held["value"])
                trace.append("nested-command-owner")
            return 0

        with mock.patch.object(sia.sialib, "_owner_lease",
                               side_effect=physical_lease), \
                mock.patch.object(sia.sialib, "load_memo",
                                  side_effect=load_memo), \
                mock.patch.object(sia.sialib, "_consolidation_scan_debt",
                                  return_value=""), \
                mock.patch.object(sia.sialib, "_thought_recovery_debt",
                                  return_value=""), \
                mock.patch.object(sia.sialib, "_graph_projection_debt",
                                  return_value=""), \
                mock.patch.object(
                    sia.sialib.siatakes,
                    "natural_history_recovery_required",
                    side_effect=history_required), \
                mock.patch.object(
                    sia.sialib.siatakes, "grade_recovery_required",
                    side_effect=grade_required), \
                mock.patch.object(
                    sia.sialib.siatakes, "take_migration_required",
                    side_effect=migration_required), \
                mock.patch.object(
                    sia.sialib.siatakes, "intent_history_required",
                    side_effect=intent_history_required), \
                mock.patch.object(
                    sia.sialib, "_graph_projection_debt", return_value=""), \
                mock.patch.object(
                    sia.sialib, "_consolidation_scan_debt",
                    return_value=""), \
                mock.patch.object(sia, "cmd_ponder", side_effect=ponder):
            self.assertEqual(sia.main(["sia", "ponder", "question"]), 0)
        self.assertEqual(trace, [
            "lease-enter", "readiness-memo", "readiness-history",
            "readiness-grades", "readiness-migrations",
            "readiness-intents", "dispatch", "nested-command-owner",
            "lease-exit"])

    def test_recall_missing_page_has_stable_not_found_status(self):
        output = io.StringIO()
        with mock.patch.object(sia.sialib, "page_exists", return_value=False), \
                mock.patch.object(
                    sia, "_gbrain_read",
                    side_effect=AssertionError("database must not be queried")), \
                contextlib.redirect_stdout(output):
            result = sia.cmd_recall("organs/missing", touch=False)
        self.assertEqual(result, 3)
        self.assertIn("memory not found", output.getvalue())

    def test_rehearsal_touch_queue_refusal_is_not_reported_as_success(self):
        output, errors = io.StringIO(), io.StringIO()
        result = types.SimpleNamespace(returncode=0, stdout="memory\n",
                                       stderr="")
        mind = __import__("siamind")
        with mock.patch.object(sia.sialib, "page_exists", return_value=True), \
                mock.patch.object(sia, "_gbrain_read", return_value=result), \
                mock.patch.object(mind, "queue_touches", return_value=False), \
                contextlib.redirect_stdout(output), \
                contextlib.redirect_stderr(errors):
            status = sia.cmd_rehearse(["events/test/day"])
        self.assertNotEqual(status, 0)
        self.assertNotIn("rehearsal touch queued", output.getvalue())
        self.assertIn("reinforcement refused", errors.getvalue())

    def test_bench_forwards_subcommand_arguments_to_siabench_main(self):
        calls = []
        result = object()

        def fake_main(argv):
            calls.append(argv)
            return result

        previous = sys.modules.get("siabench")
        sys.modules["siabench"] = types.SimpleNamespace(main=fake_main)
        try:
            with mock.patch.object(
                    sia.sialib, "memory_readiness", return_value=(True, "")):
                got = sia.main(
                    ["sia", "bench", "generate", "--out", "dataset"])
        finally:
            if previous is None:
                sys.modules.pop("siabench", None)
            else:
                sys.modules["siabench"] = previous
        self.assertIs(got, result)
        self.assertEqual(calls, [["generate", "--out", "dataset"]])

    def test_only_non_database_version_probe_bypasses_owner_wrapper(self):
        tree = ast.parse(_read(SIA_PATH))
        direct_commands = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            if not (isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and ((node.func.value.id == "subprocess"
                          and node.func.attr == "run")
                         or (node.func.value.id == "sialib"
                             and node.func.attr
                             == "_run_bounded_text_process"))):
                continue
            command, *_rest = node.args
            if not isinstance(command, ast.List) or not command.elts:
                continue
            executable, *arguments = command.elts
            if not (isinstance(executable, ast.Attribute)
                    and isinstance(executable.value, ast.Name)
                    and executable.value.id == "sialib"
                    and executable.attr == "GBRAIN"):
                continue
            direct_commands.append([
                item.value for item in arguments
                if isinstance(item, ast.Constant)])
        self.assertEqual(direct_commands, [["--version"]])

    def test_grading_recall_uses_the_owner_locked_gbrain_wrapper(self):
        calls = []
        result = types.SimpleNamespace(
            returncode=0,
            stdout='[{"slug":"events/test/day","chunk_text":"held"}]',
            stderr="")
        old_corpus = siatakes.CORPUS
        with tempfile.TemporaryDirectory() as corpus:
            path = os.path.join(corpus, "events", "test", "day.md")
            os.makedirs(os.path.dirname(path))
            with open(path, "w") as stream:
                stream.write("evidence")
            siatakes.CORPUS = corpus
            try:
                with mock.patch.object(
                        sia.sialib, "gbrain",
                        side_effect=lambda argv, timeout=0: calls.append(
                            (argv, timeout)) or result):
                    with mock.patch.object(
                            siatakes.subprocess, "run",
                            side_effect=AssertionError(
                                "raw gbrain subprocess bypass")):
                        recalled = siatakes._recall("what held")
            finally:
                siatakes.CORPUS = old_corpus
        self.assertEqual(calls, [(["query", "what held", "--source", "sia",
                                  "--json"], 180)])
        self.assertTrue(recalled.completed)
        self.assertIn("events/test/day", recalled.text)
        self.assertEqual(recalled.citations, frozenset({"events/test/day"}))

    def test_grading_recall_nonzero_is_typed_infrastructure_refusal(self):
        result = types.SimpleNamespace(
            returncode=1, stdout="", stderr="index unavailable")
        with mock.patch.object(sia.sialib, "gbrain", return_value=result):
            recalled = siatakes._recall("what held")
        self.assertIsInstance(recalled, siatakes.RecallEvidence)
        self.assertFalse(recalled.completed)
        self.assertEqual(recalled.text, "")
        self.assertEqual(recalled.citations, frozenset())
        self.assertIn("did not complete", recalled.reason)


class HonestStatusLanguage(unittest.TestCase):
    def test_ask_refuses_malformed_json_without_unlabeled_fallback(self):
        result = types.SimpleNamespace(returncode=0, stdout="not-json",
                                       stderr="")
        output, errors = io.StringIO(), io.StringIO()
        query = mock.Mock(return_value=result)
        with mock.patch.object(sia, "_gbrain_query", query), \
                mock.patch.object(sia, "_health_footer",
                                  return_value="boundary: refused"), \
                contextlib.redirect_stdout(output), \
                contextlib.redirect_stderr(errors):
            self.assertEqual(sia.cmd_ask("memory", touch=False), 1)
        query.assert_called_once()
        self.assertIn("result admission failed", errors.getvalue())
        self.assertIn("boundary: refused", output.getvalue())

    def test_ask_parser_limits_use_a_clean_admission_refusal(self):
        result = types.SimpleNamespace(returncode=0, stdout="[]", stderr="")
        for parser_error in (ValueError, RecursionError):
            output, errors = io.StringIO(), io.StringIO()
            with self.subTest(parser_error=parser_error.__name__), \
                    mock.patch.object(sia, "_gbrain_query",
                                      return_value=result), \
                    mock.patch.object(sia.json, "loads",
                                      side_effect=parser_error(
                                          "private source content")), \
                    mock.patch.object(sia, "_health_footer",
                                      return_value="boundary: refused"), \
                    contextlib.redirect_stdout(output), \
                    contextlib.redirect_stderr(errors):
                self.assertEqual(sia.cmd_ask("memory", touch=False), 1)
            self.assertIn("memory engine JSON is malformed", errors.getvalue())
            self.assertNotIn("private source content", errors.getvalue())
            self.assertIn("boundary: refused", output.getvalue())

    def test_ask_mind_failure_keeps_origin_labels_in_safe_fallback(self):
        result = types.SimpleNamespace(
            returncode=0,
            stdout=json.dumps([{
                "slug": "thoughts/model", "score": 1,
                "type": "thought", "title": "model", "chunk_text": "x",
            }]), stderr="")
        mind = sys.modules["siamind"]
        output = io.StringIO()
        with mock.patch.object(sia, "_gbrain_query", return_value=result), \
                mock.patch.object(sia.sialib, "corpus_origin",
                                  return_value="model"), \
                mock.patch.object(sia.sialib, "read_json", return_value={}), \
                mock.patch.object(mind, "load_mind",
                                  side_effect=RuntimeError("damaged mind")), \
                mock.patch.object(sia, "_health_footer",
                                  side_effect=lambda **kwargs:
                                  "boundary: " + kwargs.get(
                                      "recall_degraded", "")), \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_ask("memory", touch=False), 0)
        rendered = output.getvalue()
        self.assertIn("[model] thoughts/model", rendered)
        self.assertIn("origin-safe fallback", rendered)

    def test_recall_success_is_explicitly_origin_labeled(self):
        result = types.SimpleNamespace(returncode=0, stdout="# page\n",
                                       stderr="")
        output = io.StringIO()
        with mock.patch.object(sia.sialib, "page_exists", return_value=True), \
                mock.patch.object(sia.sialib, "corpus_origin",
                                  return_value="model"), \
                mock.patch.object(
                    sia.sialib, "unverified_jackal_recall_page",
                    return_value=False), \
                mock.patch.object(sia, "_gbrain_read", return_value=result), \
                contextlib.redirect_stdout(output):
            self.assertEqual(
                sia.cmd_recall("thoughts/model", touch=False), 0)
        self.assertTrue(output.getvalue().startswith(
            "[origin:model] thoughts/model\n"))

    def test_legacy_jackal_assurance_is_suppressed_but_clean_recall_remains(self):
        with tempfile.TemporaryDirectory() as corpus:
            pages = {
                "events/jackal/legacy": (
                    "type: event-day\ntags: [formal-receipt]",
                    "formal receipt retained fixture"),
                "thoughts/legacy-formal": (
                    "type: thought\norigin: derived",
                    "Lean-checked mathematics entered my memory"),
                "events/jackal/clean": (
                    "type: event-day\norigin: derived\n"
                    "tags: [unverified-observation]",
                    "unverified result record observed"),
            }
            for slug, (frontmatter, body) in pages.items():
                path = os.path.join(corpus, slug + ".md")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write(
                        f"---\n{frontmatter}\n---\n{body}\n")
            result = types.SimpleNamespace(
                returncode=0, stdout="unverified result record observed\n",
                stderr="")
            with mock.patch.object(sia.sialib, "CORPUS", corpus), \
                    mock.patch.object(
                        sia, "_gbrain_read", return_value=result) as recall:
                for slug in ("events/jackal/legacy",
                             "thoughts/legacy-formal"):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        self.assertEqual(
                            sia.cmd_recall(slug, touch=False), 0)
                    rendered = output.getvalue()
                    self.assertIn("unverified JACKAL", rendered)
                    self.assertNotIn("Lean-checked mathematics", rendered)
                    self.assertNotIn("formal receipt retained", rendered)
                recall.assert_not_called()
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(sia.cmd_recall(
                        "events/jackal/clean", touch=False), 0)
                self.assertIn("unverified result record observed",
                              output.getvalue())
                recall.assert_called_once()

    def test_status_surfaces_config_health_without_a_prior_pulse(self):
        errors = [{"config": "config.json",
                   "error": "config-invalid-json"}]
        output = io.StringIO()
        with mock.patch.object(
                sia.sialib, "corpus_owner",
                return_value=contextlib.nullcontext()), \
                mock.patch.object(sia.sialib, "read_json", return_value=None), \
                mock.patch.object(sia.sialib, "CONFIG_ERRORS", errors), \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_status(), 1)
        self.assertIn("config-invalid-json", output.getvalue())

    def test_status_latest_thought_carries_origin(self):
        status = {
            "state": "ok", "pulse_seq": 1,
            "ts": "2026-01-01T00:00:00Z", "pages": 1,
            "graph_nodes": 1, "graph_edges": 0, "organs": {},
            "events_today": 0, "integrity": {"verdict": "pass",
                                                "chains": {"sia": "pass"}},
            "ledger": {"seq": 1, "head": "abc"},
            "thought": {"kind": "grade", "text": "judged",
                        "origin": "model"},
        }
        output = io.StringIO()
        with mock.patch.object(sia.sialib, "read_json",
                               return_value=status), \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_status(), 0)
        self.assertIn("[origin:model] [grade] judged", output.getvalue())

    def test_thought_output_carries_origin_or_explicit_legacy_boundary(self):
        thoughts = {"thoughts": [
            {"ts": "2026-01-01T00:00:00Z", "kind": "grade",
             "origin": "model", "text": "judged", "urgent": False},
            {"ts": "2026-01-01T00:01:00Z", "kind": "attention",
             "text": "older record", "urgent": False},
        ]}
        output = io.StringIO()
        with mock.patch.object(sia.sialib, "load_thoughts",
                               return_value=thoughts), \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_think(), 0)
        rendered = output.getvalue()
        self.assertIn("[origin:model] [grade]", rendered)
        self.assertIn("[origin:legacy-unlabeled] [attention]", rendered)

    def test_pin_check_closes_file_and_limits_claim_to_version(self):
        pin = {}
        pin_path = os.path.join(REPO, "GBRAIN_PIN")
        for line in _read(pin_path).splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                pin[key] = value
        run = types.SimpleNamespace(
            returncode=0, stdout=f"gbrain {pin['version']}\n", stderr="")
        output = io.StringIO()
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            with mock.patch.object(
                    sia.sialib, "_run_bounded_text_process",
                    return_value=run):
                with contextlib.redirect_stdout(output):
                    sia._gbrain_pin_check([pin_path])
            gc.collect()
        rendered = output.getvalue()
        self.assertIn("version matches expected pin", rendered)
        self.assertIn(pin["commit"], rendered)
        self.assertIn("not self-verifiable", rendered)

    def test_pin_check_refuses_an_oversized_metadata_file(self):
        with tempfile.TemporaryDirectory() as directory:
            pin_path = os.path.join(directory, "GBRAIN_PIN")
            with open(pin_path, "wb") as stream:
                stream.write(
                    b"x" * (sia.sialib.MAX_CONFIG_BYTES + 1))
            output = io.StringIO()
            with mock.patch.object(
                    sia.sialib, "_run_bounded_text_process") as run, \
                    contextlib.redirect_stdout(output):
                sia._gbrain_pin_check([pin_path])
            run.assert_not_called()
            self.assertEqual(output.getvalue(), "")

    def test_calibration_output_is_descriptive_and_population_aware(self):
        previous = sys.modules.get("siatakes")
        sys.modules["siatakes"] = types.SimpleNamespace(
            calibration_text=lambda: ["domain=ops resolved population"])
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                self.assertEqual(sia.cmd_calibration(), 0)
        finally:
            if previous is None:
                sys.modules.pop("siatakes", None)
            else:
                sys.modules["siatakes"] = previous
        rendered = output.getvalue().casefold()
        self.assertIn("descriptive calibration", rendered)
        self.assertIn("population", rendered)
        self.assertNotIn("judgment", rendered)
        self.assertNotIn("prophet", rendered)

    def test_malformed_take_is_reported_without_crashing_list(self):
        previous = sys.modules.get("siatakes")
        sys.modules["siatakes"] = types.SimpleNamespace(
            read_proposals=lambda _state: [],
            load_takes=lambda: [{"status": "invalid-record",
                                 "slug": "takes/broken",
                                 "invalid_reason": "missing metadata"}],
            summary=lambda _takes: {"open": 0, "due": 0, "resolved": 0,
                                    "brier": None})
        output = io.StringIO()
        try:
            with mock.patch.object(sia.sialib, "read_json", return_value=[]):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(sia.cmd_takes(), 0)
        finally:
            if previous is None:
                sys.modules.pop("siatakes", None)
            else:
                sys.modules["siatakes"] = previous
        self.assertIn("invalid take record", output.getvalue())

    def test_ponder_admits_at_most_two_valid_take_proposals(self):
        take_lines = "\n".join(
            f"TAKE: confidence=0.70 deadline=2099-01-0{day} "
            f"domain=ops claim=claim {day} [[units/forged]] will resolve"
            for day in range(1, 5))
        judge = types.SimpleNamespace(
            judge_model_label=lambda: "fixture:model",
            _judge_run=lambda _prompt: (
                "Reflection [[units/forged]] <img src=x>\n" + take_lines,
                None))
        captured = []

        def validate(row, require_future=False):
            self.assertTrue(require_future)
            return {**row, "proposal_id": f"p{len(captured)}"}

        def lock(_state, mutate):
            captured.extend(mutate([]))

        result = types.SimpleNamespace(returncode=0, stdout="[]", stderr="")
        written = mock.Mock()
        with mock.patch.object(sia.sialib, "load_thoughts",
                               return_value={"thoughts": []}), \
                mock.patch.object(sia.sialib, "read_json", return_value={}), \
                mock.patch.object(sia, "_gbrain_read", return_value=result), \
                mock.patch.object(sia, "_judge", return_value=judge), \
                mock.patch.object(sia.sialib, "corpus_owner",
                                  return_value=contextlib.nullcontext()), \
                mock.patch.object(sia.sialib, "page_exists",
                                  return_value=False), \
                mock.patch.object(sia.sialib, "write_page", written), \
                mock.patch.object(sia.sialib, "append_thought_inbox"), \
                mock.patch.object(siatakes, "validate_proposal",
                                  side_effect=validate), \
                mock.patch.object(siatakes, "locked_proposals",
                                  side_effect=lock), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sia.cmd_ponder("question"), 0)
        self.assertEqual(len(captured), 2)
        self.assertIn("origin: model", written.call_args.args[1])
        body = written.call_args.args[2]
        self.assertIn('<pre class="sia-model-output">', body)
        self.assertNotIn("[[units/forged]]", body)
        self.assertIn("⟦⟦units/forged⟧⟧", body)
        self.assertTrue(all("[[" not in row["claim"] for row in captured))

    def test_ponder_refuses_a_bounded_synthesis_collision_search(self):
        judge = types.SimpleNamespace(
            judge_model_label=lambda: "fixture:model",
            _judge_run=lambda _prompt: ("Grounded reflection.", None))
        result = types.SimpleNamespace(returncode=0, stdout="[]", stderr="")
        written = mock.Mock()
        output = io.StringIO()
        with mock.patch.object(sia.sialib, "load_thoughts",
                               return_value={"thoughts": []}), \
                mock.patch.object(sia.sialib, "read_json", return_value={}), \
                mock.patch.object(sia, "_gbrain_read", return_value=result), \
                mock.patch.object(sia, "_judge", return_value=judge), \
                mock.patch.object(sia.sialib, "corpus_owner",
                                  return_value=contextlib.nullcontext()), \
                mock.patch.object(sia.sialib, "page_exists",
                                  return_value=True), \
                mock.patch.object(sia.sialib,
                                  "MAX_THOUGHT_RECOVERY_RECORDS", 2), \
                mock.patch.object(sia.sialib, "write_page", written), \
                mock.patch.object(sia.sialib,
                                  "append_thought_inbox") as enqueue, \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_ponder("question"), 1)
        written.assert_not_called()
        enqueue.assert_not_called()
        self.assertIn("collision search reached its bound",
                      output.getvalue())


class MutationBoundaries(unittest.TestCase):
    def test_manual_pulse_and_dream_refuse_an_active_brainstem_owner(self):
        owner = mock.MagicMock()
        owner.__enter__.side_effect = sia.sialib.OwnerBusy("busy")
        output = io.StringIO()
        with mock.patch.object(sia.sialib, "brainstem_owner",
                               return_value=owner), \
                mock.patch.object(
                    sia.sialib, "_pulse_transaction") as pulse, \
                mock.patch.object(sia.sialib, "dream") as dream, \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_pulse(), 1)
            self.assertEqual(sia.cmd_dream(), 1)
        pulse.assert_not_called()
        dream.assert_not_called()
        self.assertIn("owns the brain", output.getvalue())

    def test_manual_pulse_reserves_sequence_before_effects(self):
        events = []
        memo = {"pulse_seq": 0}
        lease = {"held": False}
        status = {"state": "ok", "events_pulse": 0, "pages": 0,
                  "graph_nodes": 0, "graph_edges": 0, "integrity": {}}

        @contextlib.contextmanager
        def corpus_owner():
            self.assertFalse(lease["held"])
            lease["held"] = True
            events.append(("lease", "enter"))
            try:
                yield
            finally:
                events.append(("lease", "exit"))
                lease["held"] = False

        def capture_write(value):
            self.assertTrue(lease["held"])
            events.append(("write", value["pulse_seq"]))

        def capture_pulse(sequence):
            self.assertTrue(lease["held"])
            events.append(("pulse", sequence))
            return status

        with mock.patch.object(sia.sialib, "brainstem_owner",
                               return_value=contextlib.nullcontext()), \
                mock.patch.object(sia.sialib, "corpus_owner",
                                  side_effect=corpus_owner), \
                mock.patch.object(sia.sialib, "load_memo",
                                  return_value=dict(memo)), \
                mock.patch.object(sia.sialib, "_write_memo",
                                  side_effect=capture_write), \
                mock.patch.object(sia.sialib, "_pulse_transaction",
                                  side_effect=capture_pulse), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sia.cmd_pulse(), 0)
        self.assertEqual([name for name, _value in events],
                         ["lease", "write", "pulse", "lease"])
        self.assertEqual(events[1][1], events[2][1])

    def test_sequence_reservation_refuses_an_oversized_memo(self):
        memo = {"pulse_seq": 9}
        boundary = len(json.dumps(memo).encode("utf-8"))
        with mock.patch.object(sia.sialib, "load_memo",
                               return_value=dict(memo)), \
                mock.patch.object(sia.sialib, "MAX_MEMO_BYTES", boundary), \
                mock.patch.object(
                    sia.sialib, "_pulse_transaction") as manual_pulse:
            with self.assertRaisesRegex(ValueError, "memo exceeds"):
                sia._cmd_pulse_owned()
        manual_pulse.assert_not_called()

        with mock.patch.object(brainstem.sialib, "load_memo",
                               return_value=dict(memo)), \
                mock.patch.object(brainstem.sialib,
                                  "MAX_MEMO_BYTES", boundary), \
                mock.patch.object(
                    brainstem.sialib, "_pulse_transaction") as daemon_pulse:
            with self.assertRaisesRegex(ValueError, "memo exceeds"):
                brainstem._reserved_pulse(memo["pulse_seq"] + 1)
        daemon_pulse.assert_not_called()

    def test_failed_dream_attempt_is_rate_limited(self):
        now = datetime.datetime.now().replace(
            hour=brainstem.DREAM_HOUR, minute=brainstem.DREAM_MIN)
        with mock.patch.object(brainstem.sialib, "dream",
                               side_effect=RuntimeError("failed")), \
                mock.patch.object(brainstem.sialib, "load_memo",
                                  return_value={}), \
                mock.patch.object(brainstem.sialib, "log"), \
                mock.patch.object(brainstem.time, "monotonic",
                                  return_value=0.0):
            last_day, next_attempt = brainstem._attempt_dream(now, "prior")
        self.assertEqual(last_day, "")
        self.assertEqual(next_attempt, brainstem.DREAM_RETRY_SEC)
        self.assertFalse(brainstem._dream_due(
            now, last_day, next_attempt, monotonic_now=0.0))
        self.assertTrue(brainstem._dream_due(
            now, last_day, next_attempt, monotonic_now=next_attempt))

    def test_daemon_reservation_failure_prevents_pulse_effects(self):
        with mock.patch.object(brainstem.sialib, "load_memo",
                               return_value={"pulse_seq": 0}), \
                mock.patch.object(brainstem.sialib, "_write_memo",
                                  side_effect=OSError("disk refused")), \
                mock.patch.object(
                    brainstem.sialib, "_pulse_transaction") as pulse:
            with self.assertRaisesRegex(OSError, "disk refused"):
                brainstem._reserved_pulse(1)
        pulse.assert_not_called()

    def test_daemon_reservation_and_pulse_share_corpus_lease(self):
        trace = []
        lease = {"held": False}

        @contextlib.contextmanager
        def corpus_owner():
            lease["held"] = True
            trace.append("lease-enter")
            try:
                yield
            finally:
                trace.append("lease-exit")
                lease["held"] = False

        def reserve(value):
            self.assertTrue(lease["held"])
            trace.append(("reserve", value["pulse_seq"]))

        def pulse(sequence):
            self.assertTrue(lease["held"])
            trace.append(("pulse", sequence))
            return {"pulse_seq": sequence}

        with mock.patch.object(brainstem.sialib, "corpus_owner",
                               side_effect=corpus_owner), \
                mock.patch.object(brainstem.sialib, "load_memo",
                                  return_value={"pulse_seq": 0}), \
                mock.patch.object(brainstem.sialib, "_write_memo",
                                  side_effect=reserve), \
                mock.patch.object(
                    brainstem.sialib, "_pulse_transaction",
                    side_effect=pulse):
            status = brainstem._reserved_pulse(1)
        self.assertEqual(status, {"pulse_seq": 1})
        self.assertEqual(trace, ["lease-enter", ("reserve", 1),
                                 ("pulse", 1), "lease-exit"])

    def test_corrupt_startup_memo_is_refused_before_daemon_effects(self):
        invalid = (
            {"pulse_seq": "not-an-int"},
            {"pulse_seq": True},
            {"pulse_seq": -1},
            {"sync_needed": "yes"},
            {"dream": []},
            {"dream": {"last": "2026-1-01T00:00:00Z"}},
        )
        for memo in invalid:
            with self.subTest(memo=memo):
                with self.assertRaises(ValueError):
                    brainstem._startup_state(memo)

        with mock.patch.object(brainstem.signal, "signal"), \
                mock.patch.object(brainstem.sialib, "ensure_dirs"), \
                mock.patch.object(brainstem.sialib, "log"), \
                mock.patch.object(brainstem.sialib, "load_memo",
                                  return_value={"pulse_seq": "broken"}), \
                mock.patch.object(brainstem, "_publish_failure") as publish, \
                mock.patch.object(brainstem.sialib,
                                  "recover_ledger_transitions") as recover:
            self.assertEqual(brainstem._run_owned(), 1)
        recover.assert_not_called()
        publish.assert_called_once()

    def test_manual_pulse_refuses_corrupt_sequence_without_mutation(self):
        output = io.StringIO()
        with mock.patch.object(sia.sialib, "brainstem_owner",
                               return_value=contextlib.nullcontext()), \
                mock.patch.object(sia.sialib, "corpus_owner",
                                  return_value=contextlib.nullcontext()), \
                mock.patch.object(sia.sialib, "load_memo",
                                  return_value={"pulse_seq": "broken"}), \
                mock.patch.object(sia.sialib, "atomic_write") as write, \
                mock.patch.object(
                    sia.sialib, "_pulse_transaction") as pulse, \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_pulse(), 1)
        write.assert_not_called()
        pulse.assert_not_called()
        self.assertIn("manual pulse refused", output.getvalue())

    def test_manual_take_marks_publication_debt_before_page_publish(self):
        memo, trace = {}, []

        def capture_write(path, payload, mode=None):
            if path == sia.sialib.MEMO_PATH:
                trace.append((
                    "memo", json.loads(payload).get("sync_needed", False)))

        def create_take(claim, **kwargs):
            kwargs["before_publish"]()
            trace.append(("take-page", memo.get("sync_needed", False)))
            return {"id": "take-id", "confidence": 0.7,
                    "deadline": "2099-01-01", "domain": "ops",
                    "claim": claim}

        with mock.patch.object(sia.sialib, "corpus_owner",
                               return_value=contextlib.nullcontext()), \
                mock.patch.object(sia.sialib, "load_memo",
                                  return_value=memo), \
                mock.patch.object(sia.sialib, "atomic_write",
                                  side_effect=capture_write), \
                mock.patch.object(siatakes, "create_take",
                                  side_effect=create_take), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sia.cmd_take([
                "held", "--confidence", "0.7", "--by", "2099-01-01",
                "--domain", "ops"]), 0)
        self.assertEqual(trace,
                         [("memo", True), ("take-page", True)])
        self.assertIs(memo.get("sync_needed"), True)

    def test_manual_intent_marks_publication_debt_before_page_publish(self):
        memo, trace = {}, []

        def capture_write(path, payload, mode=None):
            if path == sia.sialib.MEMO_PATH:
                trace.append(("memo", json.loads(payload)["sync_needed"]))

        def create_intent(text, due, before_publish=None):
            before_publish()
            trace.append(("intent-page", memo.get("sync_needed", False)))
            return {"id": "intent-id", "text": text, "due": due}

        with mock.patch.object(sia.sialib, "corpus_owner",
                               return_value=contextlib.nullcontext()), \
                mock.patch.object(sia.sialib, "load_memo",
                                  return_value=memo), \
                mock.patch.object(sia.sialib, "atomic_write",
                                  side_effect=capture_write), \
                mock.patch.object(siatakes, "create_intent",
                                  side_effect=create_intent), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sia.cmd_intend(
                ["do work", "--by", "2099-01-01"]), 0)
        self.assertEqual(trace,
                         [("memo", True), ("intent-page", True)])
        self.assertIs(memo.get("sync_needed"), True)

    def test_manual_grade_marks_publication_debt_before_page_publish(self):
        memo, trace = {}, []
        take = {"id": "take-id", "status": "open", "claim": "held"}

        def capture_write(path, payload, mode=None):
            if path == sia.sialib.MEMO_PATH:
                trace.append((
                    "memo", json.loads(payload).get("sync_needed", False)))

        def commit_grade(_row, _verdict, _justification, _evidence,
                         before_publish=None):
            before_publish()
            trace.append(("grade-page", memo.get("sync_needed", False)))

        def corpus_commit(_message):
            trace.append(("commit", memo.get("sync_needed", False)))
            return "committed"

        def brain_sync():
            trace.append(("sync", memo.get("sync_needed", False)))
            return True, ""

        def export_graph():
            trace.append(("graph", memo.get("sync_needed", False)))
            return 1, 2, 3

        def grade_take(row, persist=None):
            persist(row, "resolved-true", "held", [])
            return {"status": "resolved-true", "brier": None,
                    "claim": row["claim"], "slug": "takes/take-id"}

        with mock.patch.object(sia.sialib, "corpus_owner",
                               return_value=contextlib.nullcontext()), \
                mock.patch.object(sia.sialib, "load_memo",
                                  return_value=memo), \
                mock.patch.object(sia.sialib, "atomic_write",
                                  side_effect=capture_write), \
                mock.patch.object(
                    siatakes, "recover_grade_transactions",
                    return_value=([], [])), \
                mock.patch.object(siatakes, "load_takes",
                                  return_value=[take]), \
                mock.patch.object(siatakes, "grade_take",
                                  side_effect=grade_take), \
                mock.patch.object(siatakes, "commit_grade_transition",
                                  side_effect=commit_grade), \
                mock.patch.object(sia.sialib, "corpus_commit",
                                  side_effect=corpus_commit), \
                mock.patch.object(sia.sialib, "brain_sync",
                                  side_effect=brain_sync), \
                mock.patch.object(sia.sialib, "export_graph",
                                  side_effect=export_graph), \
                mock.patch.object(siatakes, "calibration_text",
                                  return_value=[]), \
                mock.patch.object(sia.sialib, "append_thought_inbox"), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sia.cmd_grade("take-id"), 0)
        self.assertEqual(trace, [
            ("memo", True), ("grade-page", True), ("commit", True),
            ("sync", True), ("graph", True), ("memo", False)])
        self.assertNotIn("sync_needed", memo)

    def test_manual_multigrade_publishes_before_next_gbrain_grade(self):
        memo, trace = {}, []
        takes = [
            {"id": "first", "status": "open", "claim": "first held"},
            {"id": "second", "status": "open", "claim": "second held"},
        ]

        def capture_write(path, payload, mode=None):
            if path == sia.sialib.MEMO_PATH:
                trace.append((
                    "memo", json.loads(payload).get("sync_needed", False)))

        def commit_grade(row, _verdict, _justification, _evidence,
                         before_publish=None):
            before_publish()
            trace.append(
                ("grade-page", row["id"], memo.get("sync_needed", False)))

        def grade_take(row, persist=None):
            trace.append(
                ("gbrain-grade", row["id"],
                 memo.get("sync_needed", False)))
            self.assertNotIn("sync_needed", memo)
            persist(row, "resolved-true", "held", [])
            self.assertNotIn("sync_needed", memo)
            return {"status": "resolved-true", "brier": None,
                    "claim": row["claim"], "slug": "takes/" + row["id"]}

        def corpus_commit(_message):
            trace.append(("commit", memo.get("sync_needed", False)))
            return "committed"

        def brain_sync():
            trace.append(("sync", memo.get("sync_needed", False)))
            return True, ""

        def export_graph():
            trace.append(("graph", memo.get("sync_needed", False)))
            return 1, 2, 3

        with mock.patch.object(sia.sialib, "corpus_owner",
                               return_value=contextlib.nullcontext()), \
                mock.patch.object(sia.sialib, "load_memo",
                                  return_value=memo), \
                mock.patch.object(sia.sialib, "atomic_write",
                                  side_effect=capture_write), \
                mock.patch.object(
                    siatakes, "recover_grade_transactions",
                    return_value=([], [])), \
                mock.patch.object(siatakes, "load_takes",
                                  return_value=takes), \
                mock.patch.object(siatakes, "due_takes",
                                  return_value=takes), \
                mock.patch.object(siatakes, "grade_take",
                                  side_effect=grade_take), \
                mock.patch.object(siatakes, "commit_grade_transition",
                                  side_effect=commit_grade), \
                mock.patch.object(sia.sialib, "corpus_commit",
                                  side_effect=corpus_commit), \
                mock.patch.object(sia.sialib, "brain_sync",
                                  side_effect=brain_sync), \
                mock.patch.object(sia.sialib, "export_graph",
                                  side_effect=export_graph), \
                mock.patch.object(siatakes, "calibration_text",
                                  return_value=[]), \
                mock.patch.object(sia.sialib, "append_thought_inbox"), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sia.cmd_grade(), 0)

        first = trace.index(("gbrain-grade", "first", False))
        second = trace.index(("gbrain-grade", "second", False))
        between = trace[first:second]
        self.assertIn(("grade-page", "first", True), between)
        self.assertIn(("graph", True), between)
        self.assertIn(("memo", False), between)
        self.assertNotIn("sync_needed", memo)

    def test_manual_multigrade_publication_failure_aborts_later_judge(self):
        memo, judged = {}, []
        takes = [
            {"id": "first", "status": "open", "claim": "first held"},
            {"id": "second", "status": "open", "claim": "second held"},
        ]

        def capture_write(_path, _payload, mode=None):
            return None

        def commit_grade(row, _verdict, _justification, _evidence,
                         before_publish=None):
            before_publish()

        def grade_take(row, persist=None):
            judged.append(row["id"])
            persist(row, "resolved-true", "held", [])
            return {"status": "resolved-true", "brier": None,
                    "claim": row["claim"], "slug": "takes/" + row["id"]}

        with mock.patch.object(sia.sialib, "corpus_owner",
                               return_value=contextlib.nullcontext()), \
                mock.patch.object(sia.sialib, "load_memo",
                                  return_value=memo), \
                mock.patch.object(sia.sialib, "atomic_write",
                                  side_effect=capture_write), \
                mock.patch.object(
                    siatakes, "recover_grade_transactions",
                    return_value=([], [])), \
                mock.patch.object(siatakes, "load_takes",
                                  return_value=takes), \
                mock.patch.object(siatakes, "due_takes",
                                  return_value=takes), \
                mock.patch.object(siatakes, "grade_take",
                                  side_effect=grade_take), \
                mock.patch.object(siatakes, "commit_grade_transition",
                                  side_effect=commit_grade), \
                mock.patch.object(sia.sialib, "corpus_commit",
                                  return_value="committed"), \
                mock.patch.object(sia.sialib, "brain_sync",
                                  return_value=(False, "index refused")), \
                mock.patch.object(sia.sialib, "export_graph") as graph, \
                mock.patch.object(siatakes, "calibration_text",
                                  return_value=[]), \
                mock.patch.object(sia.sialib, "append_thought_inbox"), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sia.cmd_grade(), 1)

        self.assertEqual(judged, ["first"])
        self.assertIs(memo.get("sync_needed"), True)
        graph.assert_not_called()

    def test_manual_ponder_marks_publication_debt_before_page_publish(self):
        memo, trace = {}, []
        judge = types.SimpleNamespace(
            judge_model_label=lambda: "fixture:model",
            _judge_run=lambda _prompt: ("Grounded reflection.", None))
        result = types.SimpleNamespace(returncode=0, stdout="[]", stderr="")

        def capture_write(path, payload, mode=None):
            if path == sia.sialib.MEMO_PATH:
                trace.append(("memo", json.loads(payload)["sync_needed"]))

        def write_page(*_args, **_kwargs):
            sia.sialib._before_corpus_mutation()
            trace.append(("ponder-page", memo.get("sync_needed", False)))

        with mock.patch.object(sia.sialib, "load_thoughts",
                               return_value={"thoughts": []}), \
                mock.patch.object(sia.sialib, "read_json", return_value={}), \
                mock.patch.object(sia, "_gbrain_read", return_value=result), \
                mock.patch.object(sia, "_judge", return_value=judge), \
                mock.patch.object(sia.sialib, "corpus_owner",
                                  return_value=contextlib.nullcontext()), \
                mock.patch.object(sia.sialib, "load_memo",
                                  return_value=memo), \
                mock.patch.object(sia.sialib, "atomic_write",
                                  side_effect=capture_write), \
                mock.patch.object(sia.sialib, "page_exists",
                                  return_value=False), \
                mock.patch.object(sia.sialib, "write_page",
                                  side_effect=write_page), \
                mock.patch.object(sia.sialib, "append_thought_inbox"), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sia.cmd_ponder("question"), 0)
        self.assertEqual(trace,
                         [("memo", True), ("ponder-page", True)])
        self.assertIs(memo.get("sync_needed"), True)

    def test_take_bad_confidence_is_refused_without_traceback(self):
        output = io.StringIO()
        with mock.patch.object(sia.sialib, "corpus_owner",
                               return_value=contextlib.nullcontext()), \
                mock.patch.object(
                    siatakes, "create_take",
                    side_effect=ValueError("proposal confidence is invalid")):
            with contextlib.redirect_stdout(output):
                for value in ("not-a-number", "nan", "inf"):
                    self.assertEqual(sia.cmd_take(
                        ["claim", "--confidence", value]), 2)
        self.assertIn("confidence is invalid", output.getvalue())

    def test_pin_requires_a_page_but_unpin_can_recover_absent_state(self):
        mind_module = sys.modules["siamind"]
        old_corpus = sia.sialib.CORPUS
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as root:
            corpus = os.path.join(root, "corpus")
            os.makedirs(os.path.join(corpus, "organs"))
            sia.sialib.CORPUS = corpus
            queued = []
            try:
                with mock.patch.object(
                        mind_module, "queue_pin",
                        side_effect=lambda slug, pinned=True:
                        queued.append((slug, pinned)) or True):
                    with contextlib.redirect_stdout(output):
                        self.assertEqual(
                            sia.cmd_memory(["--pin", "organs/missing"]), 1)
                        self.assertEqual(
                            sia.cmd_memory(["--unpin", "organs/missing"]), 0)

                        outside = os.path.join(root, "outside.md")
                        with open(outside, "w", encoding="utf-8") as stream:
                            stream.write("# outside\n")
                        os.symlink(outside,
                                   os.path.join(corpus, "organs/link.md"))
                        self.assertEqual(
                            sia.cmd_memory(["--pin", "organs/link"]), 1)

                        with open(os.path.join(corpus, "organs/real.md"), "w",
                                  encoding="utf-8") as stream:
                            stream.write("# real\n")
                        self.assertEqual(
                            sia.cmd_memory(["--pin", "organs/real"]), 0)
                        self.assertEqual(
                            sia.cmd_memory(["--unpin", "organs/real"]), 0)
            finally:
                sia.sialib.CORPUS = old_corpus
        self.assertEqual(queued, [("organs/missing", False),
                                  ("organs/real", True),
                                  ("organs/real", False)])
        self.assertIn("pins apply only to existing memories",
                      output.getvalue())

    def test_note_rejects_invalid_or_oversized_input_without_traceback(self):
        queue_module = sys.modules["siaqueue"]
        output = io.StringIO()
        with mock.patch.object(queue_module, "enqueue_note") as enqueue:
            with contextlib.redirect_stdout(output):
                self.assertEqual(sia.cmd_note(["x" * 2001]), 2)
                self.assertEqual(sia.cmd_note(["context", "--from", " "]), 2)
                self.assertEqual(sia.cmd_note(["context", "--from"]), 2)
            enqueue.assert_not_called()
        rendered = output.getvalue()
        self.assertIn("note text must be", rendered)
        self.assertIn("note author must be", rendered)

        output = io.StringIO()
        with mock.patch.object(queue_module, "enqueue_note",
                               side_effect=ValueError("invalid note payload")):
            with contextlib.redirect_stdout(output):
                self.assertEqual(sia.cmd_note(["context"]), 2)
        self.assertIn("note rejected: invalid note payload", output.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
