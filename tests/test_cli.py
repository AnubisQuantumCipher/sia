#!/usr/bin/env python3
"""Focused regression tests for the user-facing SIA CLI."""

import ast
import copy
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

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


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


def _current_status_fixture(verdict="pass"):
    chain = "fail" if verdict == "fail" else (
        "absent" if verdict == "degraded" else "pass")
    state = "failed" if verdict == "fail" else (
        "degraded" if verdict == "degraded" else "ok")
    return {
        "v": 1, "version": brainstem.sialib.VERSION,
        "ts": "2026-08-30T12:00:00Z", "state": state,
        "pulse_seq": 8, "day": "2026-08-30",
        "publication_id": "a" * 32,
        "graph_publication_id": "b" * 32,
        "events_pulse": 0, "events_today": 0,
        "organs": {}, "errors": {}, "pages": 0,
        "graph_nodes": 0, "graph_edges": 0,
        "integrity": {
            "chains": {"sia": chain}, "verdict": verdict,
            "checked_at": "2026-08-30T12:00:00Z",
        },
        "ledger": {"seq": 1, "head": "a" * 12},
        "ledger_transition": {
            "state": "not-required", "recovered": 0,
            "pending_errors": 0,
        },
        "thought": {
            "ts": "", "kind": "", "text": "",
            "origin": "legacy-unlabeled",
        },
        "dream": {}, "history": [], "workspace": [],
        "mind": {
            "nodes": 0, "edges": 0, "decay_active": 0,
            "decay_demoted": 0, "rehearsal_eligible": 0,
            "rehearsal_due": 0, "pinned": 0,
        },
        "takes": {}, "intents": [], "bench_trend": [],
        "bench_trend_boundary": {"legacy_truncated": False},
        "projection_debt": {"graph": "", "consolidation": ""},
        "agent_queue": {
            "materialized": 0, "refused": 0, "acknowledged": 0,
        },
        "redactions": {}, "sync_note": "",
    }


def _current_graph_fixture(publication_id="b" * 32):
    return {
        "v": 2, "ts": "2026-08-30T12:00:00Z",
        "publication_id": publication_id,
        "nodes": [], "edges": [], "pages_total": 0,
        "pages_total_complete": True,
        "snapshot": {
            "complete": True, "truncated": 0,
            "omitted_nodes": 0, "omitted_edges": 0,
            "omissions_imply_absence": False,
            "aged_out": 0, "counts_by_kind": {},
            "failed_ops": [], "window_days": 14,
        },
    }


class TakeOptionShapedTokens(unittest.TestCase):
    def test_option_shaped_token_refuses_instead_of_registering(self):
        # `sia take --help` once registered a take whose claim was "--help".
        # An unrecognized option must refuse with usage and register nothing.
        import io, contextlib
        for argv in (["--help"], ["-h"], ["real claim", "--confidnce", "0.6"]):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = sia.cmd_take(argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("usage:", out.getvalue())
            self.assertIn("nothing was registered", out.getvalue())


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

    def test_agent_proposal_refuses_ambiguous_and_nonstandard_json(self):
        ambiguous = (
            '{"claim":"safe","claim":"private","confidence":0.7,'
            '"deadline":"2026-12-31","domain":"general",'
            '"proposed":"agent","source":"sia/cortex"}')
        nonstandard = (
            '{"claim":"safe","confidence":NaN,'
            '"deadline":"2026-12-31","domain":"general",'
            '"proposed":"agent","source":"sia/cortex"}')
        for raw in (ambiguous, nonstandard):
            output = io.StringIO()
            with self.subTest(raw=raw), \
                    mock.patch.object(
                        siatakes, "validate_proposal",
                        return_value={"proposal_id": "a" * 20}) as validate, \
                    mock.patch.object(siatakes, "locked_proposals") as locked, \
                    contextlib.redirect_stdout(output):
                result = sia.cmd_agent_propose(raw)
            self.assertEqual(result, 2)
            self.assertEqual(
                output.getvalue(),
                "proposal rejected: payload is malformed JSON\n")
            validate.assert_not_called()
            locked.assert_not_called()
            self.assertNotIn("private", output.getvalue())

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
                mock.patch.object(sia.sialib, "_cortex_boundary_status",
                                  return_value=(True, "")), \
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
                mock.patch.object(
                    sia.sialib, "read_json",
                    return_value=_current_graph_fixture()), \
                mock.patch.object(sia, "cmd_ponder", side_effect=ponder):
            self.assertEqual(sia.main(["sia", "ponder", "question"]), 0)
        self.assertEqual(trace, [
            "lease-enter", "readiness-memo", "readiness-history",
            "readiness-grades", "readiness-migrations",
            "readiness-intents", "dispatch", "nested-command-owner",
            "lease-exit"])

    @staticmethod
    def _verify_basis(suffix="a"):
        return {
            "graph_publication_id": suffix * 32,
            "ledger_head": suffix * 12,
            "ledger_seq": 7612,
            "status_publication_id": suffix * 32,
        }

    def test_cockpit_verify_holds_lease_and_returns_exact_basis_receipt(self):
        basis = self._verify_basis()
        held = {"value": False}

        @contextlib.contextmanager
        def owner():
            self.assertFalse(held["value"])
            held["value"] = True
            try:
                yield
            finally:
                held["value"] = False

        def current():
            self.assertTrue(held["value"])
            return dict(basis)

        def verify():
            self.assertTrue(held["value"])
            return {"sia": "pass"}

        output = io.StringIO()
        encoded = json.dumps(basis, sort_keys=True, separators=(",", ":"))
        with mock.patch.object(sia.sialib, "corpus_owner",
                               side_effect=owner), \
                mock.patch.object(sia, "_current_verify_basis",
                                  side_effect=current), \
                mock.patch.object(sia.sialib, "verify_chains",
                                  side_effect=verify), \
                mock.patch.object(sia, "_gbrain_pin_check"), \
                contextlib.redirect_stdout(output):
            result = sia.cmd_verify(["--expect-basis", encoded])
        self.assertEqual(result, 0)
        self.assertFalse(held["value"])
        self.assertEqual(output.getvalue().splitlines()[-1],
                         sia._VERIFY_BASIS_RECEIPT + encoded)

    def test_cockpit_verify_refuses_displayed_a_when_live_basis_is_b(self):
        displayed = self._verify_basis("a")
        live = self._verify_basis("b")
        verify = mock.Mock(return_value={"sia": "pass"})
        output = io.StringIO()
        with mock.patch.object(sia, "_current_verify_basis",
                               return_value=live), \
                mock.patch.object(sia.sialib, "verify_chains", verify), \
                contextlib.redirect_stdout(output):
            result = sia.cmd_verify([
                "--expect-basis",
                json.dumps(displayed, sort_keys=True,
                           separators=(",", ":")),
            ])
        self.assertEqual(result, 1)
        verify.assert_not_called()
        self.assertIn("no longer live", output.getvalue())
        self.assertNotIn(sia._VERIFY_BASIS_RECEIPT, output.getvalue())

    def test_cockpit_verify_refuses_change_during_verifier_readback(self):
        before = self._verify_basis("a")
        after = self._verify_basis("b")
        output = io.StringIO()
        with mock.patch.object(sia, "_current_verify_basis",
                               side_effect=[before, after]), \
                mock.patch.object(sia.sialib, "verify_chains",
                                  return_value={"sia": "pass"}), \
                contextlib.redirect_stdout(output):
            result = sia.cmd_verify([
                "--expect-basis",
                json.dumps(before, sort_keys=True, separators=(",", ":")),
            ])
        self.assertEqual(result, 1)
        self.assertIn("changed during verification", output.getvalue())
        self.assertNotIn(sia._VERIFY_BASIS_RECEIPT, output.getvalue())

    def test_cockpit_verify_refuses_chain_changed_after_keeper_success(self):
        basis = self._verify_basis("a")
        with tempfile.TemporaryDirectory() as directory:
            ledger = os.path.join(directory, "ledger.tsv")
            verifier = os.path.join(directory, "verify.py")
            with open(ledger, "w", encoding="utf-8") as stream:
                stream.write("verified generation\n")
            with open(verifier, "w", encoding="utf-8") as stream:
                stream.write("raise SystemExit(0)\n")
            binding = (ledger, verifier,
                       [sys.executable, verifier, ledger])

            def mutate_after_success(*_args, **_kwargs):
                with open(ledger, "a", encoding="utf-8") as stream:
                    stream.write("unverified generation\n")
                return subprocess.CompletedProcess([], 0, "", "")

            output = io.StringIO()
            encoded = json.dumps(
                basis, sort_keys=True, separators=(",", ":"))
            with mock.patch.object(
                    sia.sialib, "corpus_owner",
                    return_value=contextlib.nullcontext()), \
                    mock.patch.object(
                        sia, "_current_verify_basis",
                        side_effect=[dict(basis), dict(basis)]), \
                    mock.patch.object(
                        sia.sialib, "_chain_cmds",
                        return_value={"fixture": binding}), \
                    mock.patch.object(
                        sia.sialib, "_run_bounded_text_process",
                        side_effect=mutate_after_success), \
                    mock.patch.object(sia, "_gbrain_pin_check"), \
                    contextlib.redirect_stdout(output):
                result = sia.cmd_verify(["--expect-basis", encoded])

        self.assertEqual(result, 1)
        self.assertIn("fixture  fail", output.getvalue())
        self.assertNotIn(sia._VERIFY_BASIS_RECEIPT, output.getvalue())

    def test_cockpit_verify_rechecks_earlier_chain_after_later_keeper(self):
        basis = self._verify_basis("a")
        with tempfile.TemporaryDirectory() as directory:
            first_ledger = os.path.join(directory, "first.tsv")
            second_ledger = os.path.join(directory, "second.tsv")
            verifier = os.path.join(directory, "verify.py")
            for path in (first_ledger, second_ledger):
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write("verified generation\n")
            with open(verifier, "w", encoding="utf-8") as stream:
                stream.write("raise SystemExit(0)\n")
            registry = {
                "first": (first_ledger, verifier,
                          [sys.executable, verifier, first_ledger]),
                "second": (second_ledger, verifier,
                           [sys.executable, verifier, second_ledger]),
            }
            calls = []

            def mutate_first_from_second(command, **_kwargs):
                calls.append(command)
                if len(calls) == 2:
                    with open(first_ledger, "a", encoding="utf-8") as stream:
                        stream.write("later generation\n")
                return subprocess.CompletedProcess([], 0, "", "")

            output = io.StringIO()
            encoded = json.dumps(
                basis, sort_keys=True, separators=(",", ":"))
            with mock.patch.object(
                    sia.sialib, "corpus_owner",
                    return_value=contextlib.nullcontext()), \
                    mock.patch.object(
                        sia, "_current_verify_basis",
                        side_effect=[dict(basis), dict(basis)]), \
                    mock.patch.object(
                        sia.sialib, "_chain_cmds", return_value=registry), \
                    mock.patch.object(
                        sia.sialib, "_run_bounded_text_process",
                        side_effect=mutate_first_from_second), \
                    mock.patch.object(sia, "_gbrain_pin_check"), \
                    contextlib.redirect_stdout(output):
                result = sia.cmd_verify(["--expect-basis", encoded])

        self.assertEqual(len(calls), 2)
        self.assertTrue(all(
            part.startswith("/proc/self/fd/")
            for command in calls for part in command))
        self.assertEqual(result, 1)
        self.assertIn("first    fail", output.getvalue())
        self.assertIn("second   pass", output.getvalue())
        self.assertNotIn(sia._VERIFY_BASIS_RECEIPT, output.getvalue())

    def test_cockpit_verify_basis_checks_live_ledger_head(self):
        basis = self._verify_basis("a")
        status = {
            "publication_id": basis["status_publication_id"],
            "graph_publication_id": basis["graph_publication_id"],
            "pages": 0, "graph_nodes": 0, "graph_edges": 0,
            "ledger": {"seq": basis["ledger_seq"],
                       "head": basis["ledger_head"]},
        }
        graph = {
            "v": 2, "ts": "2026-08-30T12:00:00Z",
            "publication_id": basis["graph_publication_id"],
            "nodes": [], "edges": [], "pages_total": 0,
            "pages_total_complete": True,
            "snapshot": {
                "complete": True, "truncated": 0, "omitted_nodes": 0,
                "omitted_edges": 0, "omissions_imply_absence": False,
                "aged_out": 0, "counts_by_kind": {}, "failed_ops": [],
                "window_days": 14,
            },
        }
        with mock.patch.object(
                sia.sialib, "read_json", side_effect=[status, graph]), \
                mock.patch.object(sia.sialib,
                                  "_recoverable_status_integrity",
                                  return_value="pass"), \
                mock.patch.object(sia.sialib, "ledger_head",
                                  return_value=(basis["ledger_seq"],
                                                "b" * 64)):
            with self.assertRaisesRegex(
                    RuntimeError, "ledger generation is no longer live"):
                sia._current_verify_basis()

    def test_cockpit_verify_refuses_an_unobserved_live_ledger_head(self):
        basis = self._verify_basis("a")
        status = {
            "publication_id": basis["status_publication_id"],
            "graph_publication_id": basis["graph_publication_id"],
            "pages": 0, "graph_nodes": 0, "graph_edges": 0,
            "ledger": {"seq": 0, "head": ""},
        }
        graph = {
            "v": 2, "ts": "2026-08-30T12:00:00Z",
            "publication_id": basis["graph_publication_id"],
            "nodes": [], "edges": [], "pages_total": 0,
            "pages_total_complete": True,
            "snapshot": {
                "complete": True, "truncated": 0, "omitted_nodes": 0,
                "omitted_edges": 0, "omissions_imply_absence": False,
                "aged_out": 0, "counts_by_kind": {}, "failed_ops": [],
                "window_days": 14,
            },
        }
        with mock.patch.object(
                sia.sialib, "read_json", side_effect=[status, graph]), \
                mock.patch.object(
                    sia.sialib, "_recoverable_status_integrity",
                    return_value="degraded"), \
                mock.patch.object(
                    sia.sialib, "ledger_head", return_value=(0, "")):
            with self.assertRaisesRegex(
                    RuntimeError, "ledger head is unavailable"):
                sia._current_verify_basis()

    def test_cockpit_verify_refuses_malformed_or_unbound_graph_generation(self):
        basis = self._verify_basis("a")
        status = {
            "publication_id": basis["status_publication_id"],
            "graph_publication_id": basis["graph_publication_id"],
            "pages": 1, "graph_nodes": 1, "graph_edges": 0,
            "ledger": {"seq": basis["ledger_seq"],
                       "head": basis["ledger_head"]},
        }
        graph = {
            "v": 2, "ts": "2026-08-30T12:00:00Z",
            "publication_id": basis["graph_publication_id"],
            "nodes": [{
                "id": "notes/one", "t": "note", "title": "One",
                "ts": "2026-08-30T11:59:59Z", "origin": "model",
                "deg": 0, "din": 0, "dout": 0,
            }],
            "edges": [], "pages_total": 1,
            "pages_total_complete": True,
            "snapshot": {
                "complete": True, "truncated": 0, "omitted_nodes": 0,
                "omitted_edges": 0, "omissions_imply_absence": False,
                "aged_out": 0, "counts_by_kind": {"note": 1},
                "failed_ops": [], "window_days": 14,
            },
        }
        self.assertTrue(sia._valid_verify_graph_snapshot(graph, status))
        mutations = []
        malformed = copy.deepcopy(graph)
        malformed["unexpected"] = False
        mutations.append((malformed, status))
        malformed = copy.deepcopy(graph)
        malformed["nodes"][0]["unexpected"] = False
        mutations.append((malformed, status))
        malformed = copy.deepcopy(graph)
        malformed["nodes"][0]["deg"] = 1
        mutations.append((malformed, status))
        malformed = copy.deepcopy(graph)
        malformed["snapshot"]["counts_by_kind"] = {"note": 2}
        mutations.append((malformed, status))
        malformed = copy.deepcopy(graph)
        malformed["snapshot"]["counts_by_kind"]["ghost"] = 0
        mutations.append((malformed, status))
        malformed = copy.deepcopy(graph)
        malformed["snapshot"]["omitted_nodes"] = 1
        mutations.append((malformed, status))
        malformed = copy.deepcopy(graph)
        malformed["snapshot"]["omitted_edges"] = 1
        mutations.append((malformed, status))
        malformed = copy.deepcopy(graph)
        malformed["pages_total_complete"] = False
        mutations.append((malformed, status))
        malformed = copy.deepcopy(graph)
        malformed["snapshot"]["failed_ops"] = ["scan refused"]
        mutations.append((malformed, status))
        malformed = copy.deepcopy(graph)
        malformed["snapshot"]["window_days"] = 15
        mutations.append((malformed, status))
        malformed = copy.deepcopy(graph)
        malformed["nodes"][0]["title"] = "active [label]"
        mutations.append((malformed, status))
        malformed = copy.deepcopy(graph)
        malformed["nodes"][0]["title"] = ""
        mutations.append((malformed, status))
        malformed = copy.deepcopy(graph)
        malformed["nodes"][0].update({"deg": 2, "din": 1, "dout": 1})
        malformed["edges"] = [{
            "s": "notes/one", "d": "notes/one", "t": "Not Canonical",
            "why": "context",
        }]
        malformed["snapshot"]["omitted_edges"] = 0
        mutations.append((malformed, dict(status, graph_edges=1)))
        malformed = copy.deepcopy(graph)
        malformed["nodes"][0].update({"deg": 2, "din": 1, "dout": 1})
        malformed["edges"] = [{
            "s": "notes/one", "d": "notes/one", "t": "mentions",
            "why": "line\nbreak",
        }]
        mutations.append((malformed, dict(status, graph_edges=1)))
        malformed = copy.deepcopy(graph)
        malformed["snapshot"]["complete"] = False
        malformed["snapshot"]["failed_ops"] = ["scan\u202erefused"]
        mutations.append((malformed, status))
        malformed = copy.deepcopy(graph)
        malformed["ts"] = "2999-08-30T12:00:00Z"
        mutations.append((malformed, status))
        unbound = dict(status, graph_nodes=0)
        mutations.append((graph, unbound))
        for candidate, resident in mutations:
            with self.subTest(candidate=candidate, resident=resident):
                self.assertFalse(
                    sia._valid_verify_graph_snapshot(candidate, resident))

        with mock.patch.object(
                sia.sialib, "read_json",
                side_effect=[status, mutations[0][0]]), \
                mock.patch.object(
                    sia.sialib, "_recoverable_status_integrity",
                    return_value="pass"), \
                mock.patch.object(sia.sialib, "ledger_head") as head:
            with self.assertRaisesRegex(
                    RuntimeError, "resident snapshots are not valid"):
                sia._current_verify_basis()
        head.assert_not_called()

    def test_cockpit_verify_rejects_noncanonical_or_partial_basis(self):
        basis = self._verify_basis()
        malformed = []
        bad = dict(basis); bad["ledger_seq"] = True; malformed.append(bad)
        bad = dict(basis); bad["status_publication_id"] = "generation"
        malformed.append(bad)
        bad = dict(basis); bad["graph_publication_id"] = "A" * 32
        malformed.append(bad)
        bad = dict(basis); bad["ledger_head"] = "abc"
        malformed.append(bad)
        bad = dict(basis); bad["ledger_seq"] = 0
        malformed.append(bad)
        bad = dict(basis); bad["ledger_seq"] = 0; bad["ledger_head"] = ""
        malformed.append(bad)
        for argv in ((["--expect-basis"],
                      ["--unknown", json.dumps(basis)])
                     + tuple(["--expect-basis", json.dumps(row)]
                             for row in malformed)):
            with self.subTest(argv=argv), \
                    mock.patch.object(sia.sialib, "verify_chains") as verify, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sia.cmd_verify(argv), 2)
                verify.assert_not_called()

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

    def test_unverified_jackal_rehearsal_is_not_reported_as_queued(self):
        output = io.StringIO()
        mind = __import__("siamind")
        with mock.patch.object(sia.sialib, "page_exists", return_value=True), \
                mock.patch.object(
                    sia.sialib, "unverified_jackal_recall_page",
                    return_value=True), \
                mock.patch.object(sia.sialib, "corpus_origin",
                                  return_value="derived"), \
                mock.patch.object(
                    sia, "_gbrain_read",
                    side_effect=AssertionError("suppressed page must not query")), \
                mock.patch.object(
                    mind, "queue_touches",
                    side_effect=AssertionError("suppressed page must not touch")), \
                contextlib.redirect_stdout(output):
            status = sia.cmd_rehearse(["events/jackal/legacy"])
        self.assertEqual(status, 0)
        self.assertNotIn("rehearsal touch queued", output.getvalue())
        self.assertIn("intentionally excluded", output.getvalue())

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
    def test_status_and_graph_versions_require_exact_json_integers(self):
        for replacement in (True, 1.0):
            with self.subTest(surface="status", replacement=replacement):
                status = _current_status_fixture()
                status["v"] = replacement
                self.assertIsNone(
                    sia.sialib._recoverable_status_integrity(status))
        for replacement in (True, 2.0):
            with self.subTest(surface="graph", replacement=replacement):
                graph = _current_graph_fixture()
                graph["v"] = replacement
                self.assertIsNone(
                    sia.sialib._recoverable_graph_snapshot(graph))
        for replacement in (True, 14.0):
            with self.subTest(
                    surface="graph-window", replacement=replacement):
                graph = _current_graph_fixture()
                graph["snapshot"]["window_days"] = replacement
                self.assertIsNone(
                    sia.sialib._recoverable_graph_snapshot(graph))

    def test_health_footer_binds_graph_claim_to_status_generation(self):
        status = _current_status_fixture()
        graph = _current_graph_fixture("c" * 32)
        with mock.patch.object(
                sia.sialib, "read_state_json", side_effect=(status, graph)):
            mismatched = sia._health_footer()
        self.assertIn("GRAPH GENERATION MISMATCH", mismatched)
        self.assertNotIn("graph complete", mismatched)

        graph = _current_graph_fixture(status["graph_publication_id"])
        with mock.patch.object(
                sia.sialib, "read_state_json", side_effect=(status, graph)):
            matched = sia._health_footer()
        self.assertIn("graph complete", matched)
        self.assertNotIn("GRAPH GENERATION MISMATCH", matched)

    def test_health_footer_refuses_malformed_snapshot_shapes_without_crashing(self):
        cases = (
            ([], {}),
            ({}, []),
            ({"ts": "2026-01-01T00:00:00Z", "integrity": []}, {}),
            ({"ts": "2026-01-01T00:00:00Z", "errors": []},
             {"snapshot": []}),
            ({"ts": "2026-01-01T00:00:00Z",
              "redactions": {"fixture": "many"}}, {}),
        )
        for status, graph in cases:
            with self.subTest(status=status, graph=graph), \
                    mock.patch.object(
                        sia.sialib, "read_state_json",
                        side_effect=(status, graph)):
                footer = sia._health_footer()
            self.assertTrue(footer.startswith("boundary: "))
            self.assertIn("absence of recall", footer)
            self.assertNotIn("graph complete", footer)

    def test_health_footer_distinguishes_corruption_from_snapshot_absence(self):
        status = _current_status_fixture()
        for invalid_name in ("status", "graph"):
            with self.subTest(invalid_name=invalid_name), \
                    tempfile.TemporaryDirectory() as root:
                status_path = os.path.join(root, "status.json")
                graph_path = os.path.join(root, "graph.json")
                with open(status_path, "w", encoding="utf-8") as stream:
                    if invalid_name == "status":
                        stream.write("{broken")
                    else:
                        json.dump(status, stream)
                if invalid_name == "graph":
                    with open(graph_path, "w", encoding="utf-8") as stream:
                        stream.write("{broken")
                with mock.patch.object(
                        sia.sialib, "STATUS_PATH", status_path), \
                        mock.patch.object(
                            sia.sialib, "GRAPH_PATH", graph_path):
                    footer = sia._health_footer()
                self.assertIn(
                    invalid_name.upper() + " SNAPSHOT INVALID", footer)
                self.assertIn("absence of recall", footer)

    def test_health_footer_never_calls_a_future_snapshot_live(self):
        status = _current_status_fixture()
        status["ts"] = "9999-12-31T23:59:59Z"
        with mock.patch.object(
                sia.sialib, "read_state_json", side_effect=(status, {})):
            footer = sia._health_footer()
        self.assertNotIn("senses live", footer)
        self.assertIn("SENSES STALE", footer)
        self.assertIn("future timestamp", footer)
        self.assertNotRegex(footer, r"STALE \(-[0-9]+m\)")

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

    def test_ask_refuses_ambiguous_and_nonstandard_engine_json(self):
        cases = (
            '[{"slug":"events/safe","slug":"events/private",'
            '"score":1,"type":"event-day","title":"private",'
            '"chunk_text":"private"}]',
            '[{"slug":"events/safe","score":NaN,"type":"event-day",'
            '"title":"safe","chunk_text":"safe"}]',
        )
        for raw in cases:
            result = types.SimpleNamespace(
                returncode=0, stdout=raw, stderr="")
            output, errors = io.StringIO(), io.StringIO()
            with self.subTest(raw=raw), \
                    mock.patch.object(sia, "_gbrain_query",
                                      return_value=result), \
                    mock.patch.object(sia, "_health_footer",
                                      return_value="boundary: refused"), \
                    contextlib.redirect_stdout(output), \
                    contextlib.redirect_stderr(errors):
                self.assertEqual(sia.cmd_ask("memory", touch=False), 1)
            self.assertIn("memory engine JSON is malformed", errors.getvalue())
            self.assertNotIn("private", output.getvalue())
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
                mock.patch.object(sia.sialib, "associative_rerank_enabled",
                                  return_value=True), \
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

    def test_enabled_rerank_labels_empty_and_unseedable_graph_fallbacks(self):
        result = types.SimpleNamespace(
            returncode=0,
            stdout=json.dumps([{
                "slug": "events/selected", "score": 1,
                "type": "event-day", "title": "selected",
                "chunk_text": "memory",
            }]), stderr="")
        graphs = (
            None,
            {},
            {
                "nodes": [
                    {"id": "events/other-a", "t": "event-day"},
                    {"id": "events/other-b", "t": "event-day"},
                ],
                "edges": [{
                    "s": "events/other-a", "d": "events/other-b",
                    "t": "related",
                }],
            },
        )
        mind = sys.modules["siamind"]
        for graph in graphs:
            output = io.StringIO()
            with self.subTest(graph=graph), \
                    mock.patch.object(sia, "_gbrain_query",
                                      return_value=result), \
                    mock.patch.object(sia.sialib, "corpus_origin",
                                      return_value="evidence"), \
                    mock.patch.object(sia.sialib, "read_json",
                                      return_value=graph), \
                    mock.patch.object(
                        sia.sialib, "associative_rerank_enabled",
                        return_value=True), \
                    mock.patch.object(mind, "load_mind", return_value={}), \
                    mock.patch.object(
                        sia, "_health_footer",
                        side_effect=lambda **kwargs:
                        "boundary: " + kwargs.get("recall_degraded", "")), \
                    contextlib.redirect_stdout(output):
                self.assertEqual(sia.cmd_ask("memory", touch=False), 0)
            self.assertIn(
                "associative rerank unavailable; origin-safe fallback",
                output.getvalue())

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
        status = _current_status_fixture()
        status["thought"] = {
            "ts": "2026-08-30T11:59:59Z", "kind": "grade",
            "text": "judged", "origin": "model",
        }
        output = io.StringIO()
        with mock.patch.object(
                sia.sialib, "read_state_json",
                side_effect=(status, _current_graph_fixture())), \
                mock.patch.object(sia.sialib, "memory_readiness",
                                  return_value=(True, "")), \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_status(), 0)
        self.assertIn("[origin:model] [grade] judged", output.getvalue())

    def test_status_withdraws_unobserved_ledger_head(self):
        status = _current_status_fixture("degraded")
        status["ledger"] = {"seq": 0, "head": ""}
        output = io.StringIO()
        with mock.patch.object(
                sia.sialib, "read_state_json",
                side_effect=(status, _current_graph_fixture())), \
                mock.patch.object(
                    sia.sialib, "memory_readiness",
                    return_value=(False, "signed ledger unavailable")), \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_status(), 0)
        rendered = output.getvalue()
        self.assertIn("ledger   signed ledger head unavailable", rendered)
        self.assertNotIn("ledger   seq 0", rendered)

    def test_ledger_command_refuses_unobserved_head_before_verification(self):
        output = io.StringIO()
        verifier = mock.Mock()
        with mock.patch.object(
                sia.sialib, "ledger_head", return_value=(0, "")), \
                mock.patch.object(
                    sia.sialib, "_run_bounded_text_process", verifier), \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_ledger(), 1)
        verifier.assert_not_called()
        self.assertIn("signed ledger head unavailable", output.getvalue())
        self.assertNotIn("seq 0", output.getvalue())

    def test_status_dates_failed_weekly_attempt_not_prior_success(self):
        cases = (
            ("", ""),
            ("2026-08-29T12:00:00Z", "prior success 2026-08-29T12:00"),
        )
        for last, prior_text in cases:
            status = _current_status_fixture("degraded")
            status["dream"] = {
                "last": last,
                "attempt": "2026-08-30T13:00:00Z",
                "status": "failed",
                "summary": "keeper unavailable",
            }
            output = io.StringIO()
            with self.subTest(last=last), \
                    mock.patch.object(
                        sia.sialib, "read_state_json",
                        side_effect=(status, _current_graph_fixture())), \
                    mock.patch.object(
                        sia.sialib, "memory_readiness",
                        return_value=(False, "signed ledger unavailable")), \
                    contextlib.redirect_stdout(output):
                self.assertEqual(sia.cmd_status(), 0)
                rendered = output.getvalue()
                self.assertIn(
                    "weekly   attempt 2026-08-30T13:00 failed keeper unavailable",
                    rendered)
                if prior_text:
                    self.assertIn(prior_text, rendered)
                else:
                    self.assertNotIn("prior success", rendered)

    def test_status_refuses_a_stale_graph_generation_before_claiming_ready(self):
        status = _current_status_fixture()
        graph = _current_graph_fixture("c" * 32)
        output = io.StringIO()
        with mock.patch.object(
                sia.sialib, "corpus_owner",
                return_value=contextlib.nullcontext()), \
                mock.patch.object(
                    sia.sialib, "read_state_json",
                    side_effect=(status, graph)), \
                mock.patch.object(
                    sia.sialib, "memory_readiness") as readiness, \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_status(), 1)
        readiness.assert_not_called()
        self.assertIn("status/graph generation mismatch", output.getvalue())
        self.assertNotIn("readiness READY", output.getvalue())

    def test_status_empty_graph_sentinel_cannot_mask_a_live_graph(self):
        status = _current_status_fixture()
        status.update({
            "graph_publication_id": "", "pages": 0,
            "graph_nodes": 0, "graph_edges": 0,
        })
        graph = _current_graph_fixture()
        output = io.StringIO()
        with mock.patch.object(
                sia.sialib, "corpus_owner",
                return_value=contextlib.nullcontext()), \
                mock.patch.object(
                    sia.sialib, "read_state_json",
                    side_effect=(status, graph)), \
                mock.patch.object(
                    sia.sialib, "memory_readiness") as readiness, \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_status(), 1)
        readiness.assert_not_called()
        self.assertIn("status/graph generation mismatch", output.getvalue())
        self.assertNotIn("readiness READY", output.getvalue())

    def test_status_refuses_an_open_or_malformed_current_snapshot(self):
        for mutation in (
                {**_current_status_fixture(), "unexpected": "claim"},
                {**_current_status_fixture(), "workspace": ["../escape"]}):
            output = io.StringIO()
            with self.subTest(mutation=mutation), \
                    mock.patch.object(
                        sia.sialib, "read_state_json",
                        return_value=mutation), \
                    mock.patch.object(
                        sia.sialib, "memory_readiness") as readiness, \
                    contextlib.redirect_stdout(output):
                self.assertEqual(sia.cmd_status(), 1)
            readiness.assert_not_called()
            self.assertIn("status snapshot is invalid", output.getvalue())

    def test_existing_malformed_status_is_not_reported_as_bootstrap_absence(self):
        with tempfile.TemporaryDirectory() as root:
            status_path = os.path.join(root, "status.json")
            with open(status_path, "w", encoding="utf-8") as stream:
                stream.write("{broken")
            output = io.StringIO()
            with mock.patch.object(
                    sia.sialib, "STATUS_PATH", status_path), \
                    mock.patch.object(
                        sia.sialib, "corpus_owner",
                        return_value=contextlib.nullcontext()), \
                    mock.patch.object(
                        sia.sialib, "memory_readiness") as readiness, \
                    contextlib.redirect_stdout(output):
                self.assertEqual(sia.cmd_status(), 1)
        readiness.assert_not_called()
        self.assertIn("status snapshot is invalid", output.getvalue())
        self.assertNotIn("no status yet", output.getvalue())

    def test_graph_command_refuses_an_invalid_open_envelope(self):
        graph = _current_graph_fixture()
        graph["unexpected"] = "claim"
        output = io.StringIO()
        with mock.patch.object(
                sia.sialib, "read_state_json", return_value=graph), \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_graph(), 1)
        self.assertIn("Graph snapshot is invalid", output.getvalue())

    def test_existing_malformed_graph_is_not_reported_as_bootstrap_absence(self):
        with tempfile.TemporaryDirectory() as root:
            graph_path = os.path.join(root, "graph.json")
            with open(graph_path, "w", encoding="utf-8") as stream:
                stream.write("{broken")
            output = io.StringIO()
            with mock.patch.object(sia.sialib, "GRAPH_PATH", graph_path), \
                    contextlib.redirect_stdout(output):
                self.assertEqual(sia.cmd_graph(), 1)
        self.assertIn("Graph snapshot is invalid", output.getvalue())
        self.assertNotIn("No graph snapshot yet", output.getvalue())

    def test_graph_withdrawal_sentinel_is_rendered_as_unavailable(self):
        status = _current_status_fixture()
        status.update({
            "state": "degraded",
            "graph_publication_id": "", "pages": 0,
            "graph_nodes": 0, "graph_edges": 0,
            "errors": {"graph_snapshot":
                       "resident graph snapshot is invalid"},
        })
        with tempfile.TemporaryDirectory() as root:
            status_path = os.path.join(root, "status.json")
            graph_path = os.path.join(root, "graph.json")
            with open(status_path, "w", encoding="utf-8") as stream:
                json.dump(status, stream)
            output = io.StringIO()
            with mock.patch.object(sia.sialib, "STATUS_PATH", status_path), \
                    mock.patch.object(sia.sialib, "GRAPH_PATH", graph_path), \
                    mock.patch.object(
                        sia.sialib, "corpus_owner",
                        return_value=contextlib.nullcontext()), \
                    mock.patch.object(
                        sia.sialib, "memory_readiness",
                        return_value=(False, "graph unavailable")), \
                    contextlib.redirect_stdout(output):
                self.assertEqual(sia.cmd_status(), 0)
        self.assertIn("memory   unavailable", output.getvalue())
        self.assertNotIn("memory   0 pages", output.getvalue())

    def test_ready_is_an_exit_status_health_gate(self):
        output = io.StringIO()
        with mock.patch.object(
                sia.sialib, "corpus_owner",
                return_value=contextlib.nullcontext()), \
                mock.patch.object(
                    sia.sialib, "memory_readiness",
                    side_effect=[(True, ""),
                                 (False, "projection pending")]), \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_ready(), 0)
            self.assertEqual(sia.cmd_ready(), 1)
        rendered = output.getvalue()
        self.assertIn("SIA memory ready", rendered)
        self.assertIn("SIA memory not ready: projection pending", rendered)

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

    def test_calibration_accepts_only_an_explicit_decimal_cursor(self):
        previous = sys.modules.get("siatakes")
        seen = []

        def calibration_text(*, domain_cursor=None):
            seen.append(domain_cursor)
            return ["domain continuation complete"]

        sys.modules["siatakes"] = types.SimpleNamespace(
            calibration_text=calibration_text,
            MAX_HISTORY_CURSOR_DIGITS=256)
        printed = io.StringIO()
        try:
            with contextlib.redirect_stdout(printed):
                self.assertEqual(
                    sia.cmd_calibration(["--cursor", "17"]), 0)
                self.assertEqual(
                    sia.cmd_calibration(["--cursor", "not-a-cursor"]), 2)
                self.assertEqual(sia.cmd_calibration([
                    "--cursor",
                    "1" * (__import__("siatakes")
                           .MAX_HISTORY_CURSOR_DIGITS + 1),
                ]), 2)
        finally:
            if previous is None:
                sys.modules.pop("siatakes", None)
            else:
                sys.modules["siatakes"] = previous
        self.assertEqual(seen, ["17"])
        self.assertIn("usage: sia calibration", printed.getvalue())

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

    def test_ponder_refuses_malformed_existing_status_before_model_work(self):
        with tempfile.TemporaryDirectory() as root:
            status_path = os.path.join(root, "status.json")
            with open(status_path, "w", encoding="utf-8") as stream:
                stream.write("{broken")
            gbrain = mock.Mock(return_value=types.SimpleNamespace(
                returncode=0, stdout="", stderr=""))
            judge_run = mock.Mock(return_value=("", "unexpected model work"))
            judge = types.SimpleNamespace(
                judge_model_label=lambda: "fixture:model",
                _judge_run=judge_run)
            judge_factory = mock.Mock(return_value=judge)
            output = io.StringIO()
            with mock.patch.object(sia.sialib, "STATUS_PATH", status_path), \
                    mock.patch.object(
                        sia.sialib, "load_thoughts",
                        return_value={"thoughts": []}), \
                    mock.patch.object(sia, "_gbrain_read", gbrain), \
                    mock.patch.object(sia, "_judge", judge_factory), \
                    contextlib.redirect_stdout(output):
                self.assertEqual(sia.cmd_ponder("question"), 1)
        gbrain.assert_not_called()
        judge_factory.assert_not_called()
        judge_run.assert_not_called()
        self.assertIn("ponder refused", output.getvalue())
        self.assertIn("status snapshot is invalid", output.getvalue())

    def test_ponder_labels_absent_status_activity_as_unknown(self):
        captured = []
        judge = types.SimpleNamespace(
            judge_model_label=lambda: "fixture:model",
            _judge_run=lambda prompt: (captured.append(prompt) or "", None))
        result = types.SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(
                sia.sialib, "load_thoughts",
                return_value={"thoughts": []}), \
                mock.patch.object(
                    sia.sialib, "read_state_json", return_value=None), \
                mock.patch.object(sia, "_gbrain_read", return_value=result), \
                mock.patch.object(sia, "_judge", return_value=judge), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sia.cmd_ponder("question"), 1)
        self.assertEqual(len(captured), 1)
        self.assertIn(
            "TODAY'S SOURCE ACTIVITY: (unknown — no status snapshot)",
            captured[0])
        self.assertNotIn("TODAY'S SOURCE ACTIVITY: (none)", captured[0])

    def test_context_refuses_unknown_status_before_recall(self):
        for raw in (None, "{broken"):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as root:
                status_path = os.path.join(root, "status.json")
                if raw is not None:
                    with open(status_path, "w", encoding="utf-8") as stream:
                        stream.write(raw)
                recall = mock.Mock(return_value=types.SimpleNamespace(
                    returncode=0, stdout="forged context", stderr=""))
                output = io.StringIO()
                with mock.patch.object(
                        sia.sialib, "STATUS_PATH", status_path), \
                        mock.patch.object(sia, "_gbrain_read", recall), \
                        contextlib.redirect_stdout(output):
                    self.assertEqual(
                        sia._dispatch(["sia", "context"], "context"), 1)
                recall.assert_not_called()
                self.assertIn("context refused", output.getvalue())

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
    def _complete_brainstem_status(self, verdict="pass"):
        return _current_status_fixture(verdict)

    @staticmethod
    def _complete_brainstem_graph(publication_id="b" * 32):
        return _current_graph_fixture(publication_id)

    def test_failure_status_requires_a_complete_current_snapshot(self):
        complete = self._complete_brainstem_status()
        invalid = (
            {},
            {"v": 1, "version": brainstem.sialib.VERSION,
             "ts": complete["ts"], "state": "failed",
             "pulse_seq": 8, "errors": {}},
            {key: value for key, value in complete.items()
             if key != "version"},
            {**complete, "ledger": []},
            {**complete, "events_today": 99},
            {**complete, "history": [None]},
            {**complete, "workspace": [None]},
            {**complete, "intents": [None]},
            {**complete, "bench_trend": [None]},
        )
        for status in invalid:
            with self.subTest(status=status), \
                    mock.patch.object(
                        brainstem.sialib, "read_json",
                        return_value=copy.deepcopy(status)), \
                    mock.patch.object(
                        brainstem.sialib, "export_status") as export, \
                    mock.patch.object(brainstem.sialib, "log") as log:
                brainstem._publish_failure(8, RuntimeError("fixture failure"))
            export.assert_not_called()
            self.assertIn("export REFUSED", log.call_args.args[0])

        for verdict in ("pass", "degraded", "fail"):
            status = self._complete_brainstem_status(verdict)
            exported = []
            with self.subTest(verdict=verdict), \
                    mock.patch.object(
                        brainstem.sialib, "read_json",
                        return_value=copy.deepcopy(status)), \
                    mock.patch.object(
                        brainstem.sialib, "export_status",
                        side_effect=lambda value: exported.append(value)), \
                    mock.patch.object(brainstem.sialib, "iso",
                                      return_value=status["ts"]):
                brainstem._publish_failure(8, RuntimeError("fixture failure"))
            self.assertEqual(len(exported), 1)
            self.assertEqual(exported[0]["state"], "failed")
            self.assertRegex(exported[0]["publication_id"], r"^[0-9a-f]{32}$")
            self.assertNotEqual(
                exported[0]["publication_id"], status["publication_id"])
            self.assertEqual(exported[0]["integrity"], status["integrity"])
            self.assertEqual(exported[0]["errors"]["brainstem"],
                             "fixture failure")

    def test_failure_status_binds_only_the_current_exact_graph_generation(self):
        status = self._complete_brainstem_status()

        def publish(graph):
            memo = {"pulse_seq": status["pulse_seq"], "redactions": {}}
            persisted = copy.deepcopy(memo)
            exported = []

            def read(path, default):
                if path == brainstem.sialib.STATUS_PATH:
                    return copy.deepcopy(status)
                if path == brainstem.sialib.GRAPH_PATH:
                    return copy.deepcopy(graph)
                return copy.deepcopy(default)

            def write(value):
                persisted.clear()
                persisted.update(copy.deepcopy(value))

            with mock.patch.object(
                    brainstem.sialib, "load_memo",
                    side_effect=lambda: copy.deepcopy(persisted)), \
                    mock.patch.object(
                        brainstem.sialib, "read_json", side_effect=read), \
                    mock.patch.object(
                        brainstem.sialib, "_write_memo", side_effect=write), \
                    mock.patch.object(
                        brainstem.sialib, "export_status",
                        side_effect=lambda value: exported.append(
                            copy.deepcopy(value))), \
                    mock.patch.object(brainstem.sialib, "iso",
                                      return_value=status["ts"]):
                brainstem._publish_failure(
                    status["pulse_seq"], RuntimeError("fixture failure"))
            return exported[-1]

        current = self._complete_brainstem_graph(
            status["graph_publication_id"])
        retained = publish(current)
        self.assertEqual(
            retained["graph_publication_id"],
            status["graph_publication_id"])
        self.assertEqual(
            (retained["pages"], retained["graph_nodes"],
             retained["graph_edges"]),
            (0, 0, 0))
        self.assertNotIn("graph_snapshot", retained["errors"])

        mismatched = self._complete_brainstem_graph("c" * 32)
        withdrawn = publish(mismatched)
        self.assertEqual(withdrawn["graph_publication_id"], "")
        self.assertEqual(
            (withdrawn["pages"], withdrawn["graph_nodes"],
             withdrawn["graph_edges"]),
            (0, 0, 0))
        self.assertEqual(
            withdrawn["errors"]["graph_snapshot"],
            "resident status/graph generation mismatch")

        malformed = copy.deepcopy(current)
        malformed["nodes"] = [{
            "id": "forged", "t": "note", "title": "Forged",
            "ts": current["ts"], "origin": "derived",
            "deg": 0, "din": 0, "dout": 0,
        }]
        withdrawn = publish(malformed)
        self.assertEqual(withdrawn["graph_publication_id"], "")
        self.assertEqual(
            (withdrawn["pages"], withdrawn["graph_nodes"],
             withdrawn["graph_edges"]),
            (0, 0, 0))
        self.assertEqual(
            withdrawn["errors"]["graph_snapshot"],
            "resident graph snapshot is invalid")

    def test_failure_status_redaction_replays_one_durable_generation(self):
        status = self._complete_brainstem_status()
        memo = {"pulse_seq": status["pulse_seq"], "redactions": {}}
        persisted = copy.deepcopy(memo)
        prior_redactions = copy.deepcopy(brainstem.sialib.REDACTIONS)
        brainstem.sialib.REDACTIONS.clear()

        def write(value):
            persisted.clear()
            persisted.update(copy.deepcopy(value))

        try:
            with mock.patch.object(
                    brainstem.sialib, "load_memo",
                    side_effect=lambda: copy.deepcopy(persisted)), \
                    mock.patch.object(
                        brainstem.sialib, "read_json",
                        return_value=copy.deepcopy(status)), \
                    mock.patch.object(
                        brainstem.sialib, "_write_memo", side_effect=write), \
                    mock.patch.object(
                        brainstem.sialib, "export_status",
                        side_effect=OSError("status disk refused")), \
                    mock.patch.object(brainstem.sialib, "log"):
                brainstem._publish_failure(
                    status["pulse_seq"],
                    RuntimeError("token=abcdefghijklmnop"))
            marker = copy.deepcopy(persisted["brainstem_failure_pending"])
            self.assertEqual(marker["v"], 2)
            self.assertEqual(
                marker["producer_version"], brainstem.sialib.VERSION)
            self.assertNotIn(
                "abcdefghijklmnop",
                marker["status"]["errors"]["brainstem"])
            self.assertEqual(
                marker["status"]["redactions"], {"status-error": 1})

            exported = []
            with mock.patch.object(
                    brainstem.sialib, "load_memo",
                    side_effect=lambda: copy.deepcopy(persisted)), \
                    mock.patch.object(
                        brainstem.sialib, "export_status",
                        side_effect=lambda value: exported.append(
                            copy.deepcopy(value))), \
                    mock.patch.object(
                        brainstem.sialib, "_write_memo", side_effect=write):
                brainstem._publish_failure(
                    status["pulse_seq"] + 1,
                    RuntimeError("token=abcdefghijklmnop"))
            self.assertEqual(exported, [marker["status"]])
            self.assertNotIn("brainstem_failure_pending", persisted)
            self.assertEqual(persisted["redactions"], {"status-error": 1})
        finally:
            brainstem.sialib.REDACTIONS.clear()
            brainstem.sialib.REDACTIONS.update(prior_redactions)

    def test_failure_publication_holds_the_corpus_lease(self):
        status = self._complete_brainstem_status()
        persisted = {
            "pulse_seq": status["pulse_seq"], "redactions": {}}
        held = {"value": False}
        exported = []

        @contextlib.contextmanager
        def corpus_owner():
            self.assertFalse(held["value"])
            held["value"] = True
            try:
                yield
            finally:
                held["value"] = False

        def require_lease(value=None):
            self.assertTrue(held["value"])
            return copy.deepcopy(persisted if value is None else value)

        def write(value):
            require_lease(value)
            persisted.clear()
            persisted.update(copy.deepcopy(value))

        def export(value):
            require_lease(value)
            exported.append(copy.deepcopy(value))

        with mock.patch.object(
                brainstem.sialib, "corpus_owner",
                side_effect=corpus_owner), \
                mock.patch.object(
                    brainstem.sialib, "load_memo",
                    side_effect=lambda: require_lease()), \
                mock.patch.object(
                    brainstem.sialib, "read_json",
                    side_effect=lambda *_args: require_lease(status)), \
                mock.patch.object(
                    brainstem.sialib, "_write_memo", side_effect=write), \
                mock.patch.object(
                    brainstem.sialib, "export_status", side_effect=export), \
                mock.patch.object(brainstem.sialib, "log"):
            brainstem._publish_failure(
                status["pulse_seq"], RuntimeError("fixture failure"))

        self.assertFalse(held["value"])
        self.assertEqual(exported[-1]["state"], "failed")
        self.assertNotIn("brainstem_failure_pending", persisted)

    def test_upgrade_retires_prior_failure_journal_before_manual_pulse(self):
        prior_status = self._complete_brainstem_status()
        prior_status.update({
            "version": "1.7.7", "state": "failed",
            "publication_id": "c" * 32,
        })
        persisted = {
            "pulse_seq": prior_status["pulse_seq"], "redactions": {},
            "ready": {"stale": True},
            "brainstem_failure_pending": {
                "v": 2, "producer_version": "1.7.7",
                "status": prior_status,
            },
        }
        writes = []

        def write(value):
            writes.append(copy.deepcopy(value))
            persisted.clear()
            persisted.update(copy.deepcopy(value))

        pulse_status = {
            "state": "ok", "events_pulse": 0, "pages": 0,
            "graph_nodes": 0, "graph_edges": 0, "integrity": {},
        }
        with mock.patch.object(
                sia.sialib, "corpus_owner",
                return_value=contextlib.nullcontext()), \
                mock.patch.object(
                    sia.sialib, "load_memo",
                    side_effect=lambda: copy.deepcopy(persisted)), \
                mock.patch.object(sia.sialib, "load_cursors",
                                  return_value={}), \
                mock.patch.object(sia.sialib, "read_json",
                                  return_value={}), \
                mock.patch.object(sia.sialib, "_write_memo",
                                  side_effect=write), \
                mock.patch.object(sia.sialib, "export_status") as export, \
                mock.patch.object(sia.sialib, "log") as log, \
                mock.patch.object(
                    sia.sialib, "_pulse_transaction",
                    return_value=pulse_status) as pulse, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sia._cmd_pulse_owned(), 0)

        export.assert_not_called()
        pulse.assert_called_once()
        self.assertNotIn("brainstem_failure_pending", writes[0])
        self.assertNotIn("ready", writes[0])
        self.assertIn("superseded", log.call_args.args[0])
        self.assertNotIn("brainstem_failure_pending", persisted)

    def test_failure_journal_retirement_refuses_newer_or_malformed_core(self):
        status = self._complete_brainstem_status()
        status.update({"version": "1.7.9", "state": "failed"})
        newer = {
            "pulse_seq": status["pulse_seq"], "redactions": {},
            "brainstem_failure_pending": {
                "v": 2, "producer_version": "1.7.9", "status": status,
            },
        }
        with self.assertRaisesRegex(RuntimeError, "newer runtime"):
            brainstem.sialib._pending_brainstem_failure_publication(newer)

        malformed = copy.deepcopy(newer)
        malformed["brainstem_failure_pending"]["producer_version"] = \
            "1.7.7"
        malformed["brainstem_failure_pending"]["status"]["version"] = \
            "1.7.7"
        malformed["brainstem_failure_pending"]["status"].pop(
            "publication_id")
        with self.assertRaisesRegex(RuntimeError, "marker is invalid"):
            brainstem.sialib._pending_brainstem_failure_publication(
                malformed)

    def test_failure_journal_versions_require_exact_json_integers(self):
        current_status = self._complete_brainstem_status("fail")
        legacy = {
            "pulse_seq": current_status["pulse_seq"],
            "redactions": copy.deepcopy(current_status["redactions"]),
            "brainstem_failure_pending": {
                "v": 1, "status": copy.deepcopy(current_status)},
        }
        self.assertIsNotNone(
            brainstem.sialib._pending_brainstem_failure_publication(legacy))
        for replacement in (True, 1.0):
            with self.subTest(schema="legacy", replacement=replacement):
                malformed = copy.deepcopy(legacy)
                malformed["brainstem_failure_pending"]["v"] = replacement
                with self.assertRaisesRegex(RuntimeError, "marker is invalid"):
                    brainstem.sialib._pending_brainstem_failure_publication(
                        malformed)

        prior_status = copy.deepcopy(current_status)
        prior_status["version"] = "1.7.7"
        current = {
            "pulse_seq": prior_status["pulse_seq"],
            "redactions": copy.deepcopy(prior_status["redactions"]),
            "brainstem_failure_pending": {
                "v": 2, "producer_version": "1.7.7",
                "status": prior_status,
            },
        }
        self.assertIsNotNone(
            brainstem.sialib._pending_brainstem_failure_publication(current))
        malformed = copy.deepcopy(current)
        malformed["brainstem_failure_pending"]["v"] = 2.0
        with self.assertRaisesRegex(RuntimeError, "marker is invalid"):
            brainstem.sialib._pending_brainstem_failure_publication(malformed)
        for replacement in (True, 1.0):
            with self.subTest(
                    schema="nested-status", replacement=replacement):
                malformed = copy.deepcopy(current)
                malformed["brainstem_failure_pending"]["status"][
                    "v"] = replacement
                with self.assertRaisesRegex(RuntimeError, "marker is invalid"):
                    brainstem.sialib._pending_brainstem_failure_publication(
                        malformed)

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
        self.assertIn("owns the local memory runtime", output.getvalue())

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

        def capture_pulse(sequence, *, admitted_status):
            self.assertTrue(lease["held"])
            self.assertIsNone(admitted_status)
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

    def test_manual_pulse_renders_a_withdrawn_graph_as_unavailable(self):
        memo = {"pulse_seq": 0}
        status = self._complete_brainstem_status()
        status.update({
            "graph_publication_id": "",
            "pages": 0,
            "graph_nodes": 0,
            "graph_edges": 0,
            "errors": {
                "graph_snapshot":
                    "graph publication failed; current graph claims withdrawn",
            },
        })
        output = io.StringIO()
        with mock.patch.object(
                sia.sialib, "corpus_owner",
                return_value=contextlib.nullcontext()), \
                mock.patch.object(
                    sia.sialib, "load_memo", return_value=dict(memo)), \
                mock.patch.object(sia.sialib, "_write_memo"), \
                mock.patch.object(
                    sia.sialib, "_pulse_transaction",
                    return_value=copy.deepcopy(status)), \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia._cmd_pulse_owned(), 0)

        rendered = json.loads(output.getvalue())
        self.assertEqual(rendered["graph"], "unavailable")
        self.assertEqual(rendered["errors"], status["errors"])
        for claim in ("pages", "graph_nodes", "graph_edges"):
            self.assertNotIn(claim, rendered)

    def test_status_sequence_cannot_outrun_the_durable_allocator(self):
        memo = {"pulse_seq": 7}
        status = self._complete_brainstem_status()
        self.assertEqual(status["pulse_seq"], 8)
        for runtime, entry in (
                (sia.sialib, sia._cmd_pulse_owned),
                (brainstem.sialib,
                 lambda: brainstem._reserved_pulse(8))):
            with self.subTest(entry=entry), \
                    mock.patch.object(runtime, "load_memo",
                                      return_value=copy.deepcopy(memo)), \
                    mock.patch.object(runtime, "read_state_json",
                                      return_value=copy.deepcopy(status)), \
                    mock.patch.object(runtime, "load_cursors",
                                      return_value={}), \
                    mock.patch.object(runtime, "_write_memo") as write, \
                    mock.patch.object(runtime, "_pulse_transaction") as pulse:
                with self.assertRaisesRegex(
                        ValueError, "exceeds the durable memo"):
                    entry()
            write.assert_not_called()
            pulse.assert_not_called()

    def test_status_sequence_treats_only_an_absent_status_as_bootstrap(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(
                sia.sialib, "STATUS_PATH",
                os.path.join(root, "status.json")):
            sia.sialib._require_status_sequence_not_ahead(0)
            path = sia.sialib.STATUS_PATH
            malformed_values = (
                b"{broken",
                json.dumps({
                    **self._complete_brainstem_status(),
                    "unknown": "unadmitted",
                }).encode("utf-8"),
            )
            for raw in malformed_values:
                with self.subTest(raw=raw):
                    with open(path, "wb") as stream:
                        stream.write(raw)
                    try:
                        with self.assertRaisesRegex(
                                ValueError, "resident status.*admitted"):
                            sia.sialib._require_status_sequence_not_ahead(0)
                    finally:
                        if os.path.lexists(path):
                            os.unlink(path)
            target = os.path.join(root, "target.json")
            with open(target, "w", encoding="utf-8") as stream:
                json.dump(self._complete_brainstem_status(), stream)
            os.symlink(target, path)
            with self.assertRaisesRegex(
                    ValueError, "resident status.*admitted"):
                sia.sialib._require_status_sequence_not_ahead(0)

    def test_pre_reservation_failure_cannot_publish_the_proposed_sequence(self):
        memo = {
            "pulse_seq": 7, "sync_needed": True,
            "pulse_publication": {"bad": True},
        }
        status = self._complete_brainstem_status()
        status["pulse_seq"] = 7
        with mock.patch.object(
                brainstem.sialib, "load_memo",
                return_value=copy.deepcopy(memo)), \
                mock.patch.object(brainstem.sialib, "load_cursors",
                                  return_value={}), \
                mock.patch.object(brainstem.sialib, "read_json",
                                  return_value=copy.deepcopy(status)), \
                mock.patch.object(brainstem.sialib, "_write_memo") as write, \
                mock.patch.object(brainstem.sialib, "export_status") as export:
            with self.assertRaisesRegex(
                    RuntimeError, "pulse publication recovery marker") as err:
                brainstem._reserved_pulse(8)
            brainstem._publish_failure(8, err.exception)
        self.assertEqual(write.call_count, 2)
        self.assertIn("brainstem_failure_pending", write.call_args_list[0].args[0])
        self.assertNotIn("brainstem_failure_pending", write.call_args.args[0])
        export.assert_called_once()
        self.assertEqual(export.call_args.args[0]["pulse_seq"], 7)
        self.assertNotEqual(
            export.call_args.args[0]["publication_id"],
            status["publication_id"])

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

    def test_source_replay_quarantine_precedes_sequence_reservation(self):
        memo = {"pulse_seq": 7, "source_replay_pending": {"marker": True}}
        for runtime, entry in (
                (sia.sialib, sia._cmd_pulse_owned),
                (brainstem.sialib,
                 lambda: brainstem._reserved_pulse(8))):
            with self.subTest(entry=entry), \
                    mock.patch.object(
                        runtime, "load_memo", return_value=dict(memo)), \
                    mock.patch.object(
                        runtime, "_pending_source_replay_marker",
                        return_value=memo["source_replay_pending"]), \
                    mock.patch.object(runtime, "load_cursors",
                                      return_value={}), \
                    mock.patch.object(
                        runtime, "_authorize_pending_source_replay",
                        side_effect=runtime.SourceReplayQuarantine(
                            "source replay quarantine")), \
                    mock.patch.object(runtime, "_write_memo") as write, \
                    mock.patch.object(
                        runtime, "_pulse_transaction") as pulse:
                with self.assertRaises(runtime.SourceReplayQuarantine):
                    entry()
            write.assert_not_called()
            pulse.assert_not_called()

    def test_malformed_pulse_marker_precedes_sequence_reservation(self):
        memo = {
            "pulse_seq": 7, "sync_needed": True,
            "pulse_publication": {"bad": True},
        }
        for runtime, entry in (
                (sia.sialib, sia._cmd_pulse_owned),
                (brainstem.sialib,
                 lambda: brainstem._reserved_pulse(8))):
            with self.subTest(entry=entry), \
                    mock.patch.object(
                        runtime, "load_memo", return_value=dict(memo)), \
                    mock.patch.object(runtime, "load_cursors",
                                      return_value={}), \
                    mock.patch.object(runtime, "_write_memo") as write, \
                    mock.patch.object(
                        runtime, "_pulse_transaction") as pulse:
                with self.assertRaisesRegex(
                        RuntimeError, "pulse publication recovery marker"):
                    entry()
            write.assert_not_called()
            pulse.assert_not_called()

    def test_invalid_status_memo_withdraws_ready_before_reservation(self):
        memo = {
            "pulse_seq": 7, "dream": "oops",
            "ready": {
                "v": 1, "completed_at": "2026-08-30T12:00:00Z",
                "kind": "recovery", "identity": "0" * 32,
            },
        }
        for runtime, entry in (
                (sia.sialib, sia._cmd_pulse_owned),
                (brainstem.sialib,
                 lambda: brainstem._reserved_pulse(8))):
            with self.subTest(entry=entry), \
                    mock.patch.object(
                        runtime, "load_memo", return_value=dict(memo)), \
                    mock.patch.object(runtime, "load_cursors") as cursors, \
                    mock.patch.object(runtime, "_write_memo") as write, \
                    mock.patch.object(
                        runtime, "_pulse_transaction") as pulse:
                with self.assertRaisesRegex(
                        RuntimeError, "status memo fields are invalid"):
                    entry()
            cursors.assert_not_called()
            write.assert_called_once()
            self.assertNotIn("ready", write.call_args.args[0])
            pulse.assert_not_called()

    def test_daemon_malformed_pulse_marker_refuses_before_ready(self):
        memo = {
            "pulse_seq": 7, "sync_needed": True,
            "pulse_publication": {"bad": True},
        }
        with mock.patch.object(brainstem.signal, "signal"), \
                mock.patch.object(
                    brainstem.sialib, "load_memo", return_value=memo), \
                mock.patch.object(brainstem.sialib, "load_cursors",
                                  return_value={}), \
                mock.patch.object(brainstem.sialib, "log"), \
                mock.patch.object(
                    brainstem.sialib, "ensure_dirs") as ensure_dirs, \
                mock.patch.object(
                    brainstem, "_publish_failure") as publish, \
                mock.patch.object(
                    brainstem, "_systemd_ready") as ready, \
                mock.patch.object(
                    brainstem.sialib,
                    "recover_ledger_transitions") as recover, \
                mock.patch.object(
                    brainstem.sialib,
                    "durable_ledger_append") as ledger:
            self.assertEqual(brainstem._run_owned(), 1)
        ensure_dirs.assert_not_called()
        ready.assert_not_called()
        recover.assert_not_called()
        ledger.assert_not_called()
        publish.assert_called_once()

    def test_daemon_invalid_status_memo_refuses_before_boot_or_ready(self):
        invalid = (
            {"pulse_history": [["not-a-time", 0]]},
            {"redactions": []},
        )
        for corrupt in invalid:
            with self.subTest(corrupt=corrupt):
                retained_status = self._complete_brainstem_status()
                memo = {
                    "pulse_seq": 7,
                    "ready": {
                        "v": 1,
                        "completed_at": "2026-08-30T12:00:00Z",
                        "kind": "recovery", "identity": "0" * 32,
                    },
                    **copy.deepcopy(corrupt),
                }
                exported = []
                with mock.patch.object(brainstem.signal, "signal"), \
                        mock.patch.object(
                            brainstem.sialib, "load_memo",
                            return_value=memo), \
                        mock.patch.object(
                            brainstem.sialib, "_write_memo") as write, \
                        mock.patch.object(
                            brainstem.sialib, "load_cursors") as cursors, \
                        mock.patch.object(brainstem.sialib, "log"), \
                        mock.patch.object(
                            brainstem.sialib, "ensure_dirs") as ensure_dirs, \
                        mock.patch.object(
                            brainstem.sialib, "corpus_owner",
                            return_value=contextlib.nullcontext()), \
                        mock.patch.object(
                            brainstem.sialib, "read_json",
                            return_value=copy.deepcopy(retained_status)), \
                        mock.patch.object(
                            brainstem.sialib, "export_status",
                            side_effect=lambda value: exported.append(
                                copy.deepcopy(value))), \
                        mock.patch.object(
                            brainstem, "_systemd_ready") as ready, \
                        mock.patch.object(
                            brainstem.sialib,
                            "recover_ledger_transitions") as recover, \
                        mock.patch.object(
                            brainstem.sialib,
                            "durable_ledger_append") as ledger:
                    self.assertEqual(brainstem._run_owned(), 1)
                expected_failure_export = "redactions" not in corrupt
                self.assertGreaterEqual(
                    write.call_count, 3 if expected_failure_export else 1)
                self.assertNotIn("ready", write.call_args.args[0])
                cursors.assert_not_called()
                ensure_dirs.assert_not_called()
                recover.assert_not_called()
                ledger.assert_not_called()
                ready.assert_not_called()
                if expected_failure_export:
                    self.assertEqual(len(exported), 1)
                    self.assertEqual(
                        exported[0]["pulse_seq"],
                        retained_status["pulse_seq"])
                else:
                    # An invalid cumulative redaction checkpoint cannot be
                    # safely copied into a new publication.  Refusal leaves
                    # the prior valid status generation (and sequence) intact.
                    self.assertEqual(exported, [])

    def test_daemon_refuses_status_ahead_of_memo_before_boot_or_ready(self):
        memo = {"pulse_seq": 7}
        retained_status = self._complete_brainstem_status()
        exported = []
        with mock.patch.object(brainstem.signal, "signal"), \
                mock.patch.object(
                    brainstem.sialib, "load_memo",
                    return_value=copy.deepcopy(memo)), \
                mock.patch.object(brainstem.sialib, "_write_memo"), \
                mock.patch.object(brainstem.sialib, "load_cursors",
                                  return_value={}), \
                mock.patch.object(brainstem.sialib, "read_state_json",
                                  return_value=copy.deepcopy(retained_status)), \
                mock.patch.object(brainstem.sialib, "read_json",
                                  return_value=copy.deepcopy(retained_status)), \
                mock.patch.object(
                    brainstem.sialib, "export_status",
                    side_effect=lambda value: exported.append(
                        copy.deepcopy(value))), \
                mock.patch.object(brainstem.sialib, "ensure_dirs") as ensure, \
                mock.patch.object(
                    brainstem.sialib, "corpus_owner",
                    return_value=contextlib.nullcontext()), \
                mock.patch.object(
                    brainstem.sialib, "recover_ledger_transitions") as recover, \
                mock.patch.object(
                    brainstem.sialib, "durable_ledger_append") as ledger, \
                mock.patch.object(brainstem, "_systemd_ready") as ready, \
                mock.patch.object(brainstem.sialib, "log"):
            self.assertEqual(brainstem._run_owned(), 1)
        ensure.assert_not_called()
        recover.assert_not_called()
        ledger.assert_not_called()
        ready.assert_not_called()
        self.assertEqual(len(exported), 1)
        self.assertEqual(
            exported[0]["pulse_seq"], retained_status["pulse_seq"])
        self.assertNotEqual(
            exported[0]["publication_id"],
            retained_status["publication_id"])

    def test_daemon_quarantine_exits_cleanly_without_startup_publication(self):
        marker = {"marker": True}
        with mock.patch.object(brainstem.signal, "signal"), \
                mock.patch.object(brainstem.sialib, "load_memo",
                                  return_value={
                                      "pulse_seq": 0,
                                      "source_replay_pending": marker}), \
                mock.patch.object(
                    brainstem.sialib, "_pending_source_replay_marker",
                    return_value=marker), \
                mock.patch.object(brainstem.sialib, "load_cursors",
                                  return_value={}), \
                mock.patch.object(
                    brainstem.sialib, "_authorize_pending_source_replay",
                    side_effect=brainstem.sialib.SourceReplayQuarantine(
                        "source replay quarantine")), \
                mock.patch.object(brainstem.sialib, "log") as log, \
                mock.patch.object(
                    brainstem.sialib, "ensure_dirs") as ensure_dirs, \
                mock.patch.object(
                    brainstem, "_publish_failure") as publish, \
                mock.patch.object(
                    brainstem, "_systemd_ready") as ready, \
                mock.patch.object(
                    brainstem.sialib,
                    "recover_ledger_transitions") as recover, \
                mock.patch.object(
                    brainstem.sialib,
                    "durable_ledger_append") as ledger:
            self.assertEqual(
                brainstem._run_owned(), brainstem.INTENTIONAL_STOP_EXIT)
        ensure_dirs.assert_not_called()
        publish.assert_not_called()
        ready.assert_not_called()
        recover.assert_not_called()
        ledger.assert_not_called()
        self.assertIn("source_replay_quarantine", log.call_args.args[0])

    def test_restore_barrier_returns_intentional_stop_before_ownership(self):
        with mock.patch.object(
                brainstem, "_restore_barrier_present",
                return_value=True), \
                mock.patch.object(
                    brainstem.sialib, "brainstem_owner",
                    return_value=contextlib.nullcontext()) as owner, \
                mock.patch.object(brainstem, "_run_owned") as run_owned, \
                mock.patch.object(brainstem.sialib, "log") as log:
            result = brainstem.main()

        self.assertEqual(result, brainstem.INTENTIONAL_STOP_EXIT)
        owner.assert_not_called()
        run_owned.assert_not_called()
        log.assert_called_once_with(
            "sia-brainstem REFUSED: interrupted restore barrier requires "
            "recovery")

    def test_daemon_in_loop_quarantine_returns_intentional_stop(self):
        quarantine = brainstem.sialib.SourceReplayQuarantine(
            "source replay quarantine")
        with mock.patch.object(brainstem, "_stop", False), \
                mock.patch.object(brainstem.signal, "signal"), \
                mock.patch.object(
                    brainstem.sialib, "load_memo",
                    return_value={"pulse_seq": 0}), \
                mock.patch.object(
                    brainstem.sialib, "load_cursors",
                    return_value={}), \
                mock.patch.object(
                    brainstem.sialib,
                    "_require_status_sequence_not_ahead"), \
                mock.patch.object(brainstem.sialib, "ensure_dirs"), \
                mock.patch.object(
                    brainstem.sialib, "recover_ledger_transitions",
                    return_value=(False, [])), \
                mock.patch.object(
                    brainstem.sialib, "durable_ledger_append"), \
                mock.patch.object(
                    brainstem, "_systemd_ready") as ready, \
                mock.patch.object(
                    brainstem, "_reserved_pulse",
                    side_effect=quarantine) as pulse, \
                mock.patch.object(
                    brainstem, "_durable_failure_detail",
                    return_value="source replay quarantine"), \
                mock.patch.object(
                    brainstem, "_publish_failure") as publish, \
                mock.patch.object(brainstem.sialib, "log") as log:
            result = brainstem._run_owned()

        self.assertEqual(result, brainstem.INTENTIONAL_STOP_EXIT)
        ready.assert_called_once_with()
        pulse.assert_called_once_with(1)
        publish.assert_not_called()
        self.assertIn(
            "pulse 1 source_replay_quarantine",
            log.call_args.args[0])

    def test_failed_dream_attempt_is_rate_limited(self):
        now = datetime.datetime.now().replace(
            hour=brainstem.DREAM_HOUR, minute=brainstem.DREAM_MIN)
        persisted = {}
        logs = []
        prior_redactions = copy.deepcopy(brainstem.sialib.REDACTIONS)
        brainstem.sialib.REDACTIONS.clear()

        def write(value):
            persisted.clear()
            persisted.update(copy.deepcopy(value))

        secret = "token=abcdefghijklmnop"
        with mock.patch.object(brainstem.sialib, "dream",
                               side_effect=RuntimeError(secret)), \
                mock.patch.object(
                    brainstem.sialib, "corpus_owner",
                    return_value=contextlib.nullcontext()), \
                mock.patch.object(brainstem.sialib, "load_memo",
                                  side_effect=lambda: copy.deepcopy(
                                      persisted)), \
                mock.patch.object(brainstem.sialib, "_write_memo",
                                  side_effect=write), \
                mock.patch.object(brainstem.sialib, "log",
                                  side_effect=logs.append), \
                mock.patch.object(brainstem.time, "monotonic",
                                  return_value=0.0):
            try:
                last_day, next_attempt = brainstem._attempt_dream(
                    now, "prior")
            finally:
                brainstem.sialib.REDACTIONS.clear()
                brainstem.sialib.REDACTIONS.update(prior_redactions)
        self.assertEqual(last_day, "")
        self.assertEqual(next_attempt, brainstem.DREAM_RETRY_SEC)
        self.assertEqual(persisted["redactions"], {"status-error": 1})
        self.assertTrue(any("⟦redacted⟧" in row for row in logs))
        self.assertTrue(all("abcdefghijklmnop" not in row for row in logs))
        self.assertFalse(brainstem._dream_due(
            now, last_day, next_attempt, monotonic_now=0.0))
        self.assertTrue(brainstem._dream_due(
            now, last_day, next_attempt, monotonic_now=next_attempt))

    def test_failure_export_exception_rebinds_redaction_journal(self):
        status = self._complete_brainstem_status()
        persisted = {"pulse_seq": status["pulse_seq"], "redactions": {}}
        writes = []
        logs = []
        prior_redactions = copy.deepcopy(brainstem.sialib.REDACTIONS)
        brainstem.sialib.REDACTIONS.clear()

        def write(value):
            writes.append(copy.deepcopy(value))
            persisted.clear()
            persisted.update(copy.deepcopy(value))

        try:
            with mock.patch.object(
                    brainstem.sialib, "corpus_owner",
                    return_value=contextlib.nullcontext()), \
                    mock.patch.object(
                        brainstem.sialib, "load_memo",
                        side_effect=lambda: copy.deepcopy(persisted)), \
                    mock.patch.object(
                        brainstem.sialib, "read_json",
                        return_value=copy.deepcopy(status)), \
                    mock.patch.object(brainstem.sialib, "_write_memo",
                                      side_effect=write), \
                    mock.patch.object(
                        brainstem.sialib, "export_status",
                        side_effect=OSError("token=abcdefghijklmnop")), \
                    mock.patch.object(brainstem.sialib, "log",
                                      side_effect=logs.append):
                brainstem._publish_failure(
                    status["pulse_seq"], RuntimeError("pulse refused"))
        finally:
            brainstem.sialib.REDACTIONS.clear()
            brainstem.sialib.REDACTIONS.update(prior_redactions)

        marker = persisted["brainstem_failure_pending"]
        self.assertEqual(persisted["redactions"], {"status-error": 1})
        self.assertEqual(marker["status"]["redactions"],
                         persisted["redactions"])
        self.assertNotEqual(
            marker["status"]["publication_id"],
            writes[0]["brainstem_failure_pending"]["status"][
                "publication_id"])
        self.assertTrue(all("abcdefghijklmnop" not in row for row in logs))

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

        def pulse(sequence, *, admitted_status):
            self.assertTrue(lease["held"])
            self.assertIsNone(admitted_status)
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
                mock.patch.object(brainstem, "_systemd_ready") as ready, \
                mock.patch.object(brainstem.sialib,
                                  "recover_ledger_transitions") as recover:
            self.assertEqual(brainstem._run_owned(), 1)
        recover.assert_not_called()
        ready.assert_not_called()
        publish.assert_called_once()

    def test_daemon_notifies_systemd_only_after_boot_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            endpoint = os.path.join(directory, "notify.sock")
            trace = []
            notifier = mock.MagicMock()
            notifier.__enter__.return_value = notifier
            payload = b"READY=1\nSTATUS=SIA brainstem ready"
            owner = {"held": False}

            @contextlib.contextmanager
            def brainstem_owner():
                owner["held"] = True
                try:
                    yield
                finally:
                    owner["held"] = False

            def append(action, *_args):
                trace.append(action)

            def sendto(message, address):
                self.assertTrue(owner["held"])
                trace.append("READY")
                self.assertEqual((message, address), (payload, endpoint))
                return len(message)

            notifier.sendto.side_effect = sendto
            prior_stop = brainstem._stop
            brainstem._stop = True
            try:
                with mock.patch.dict(
                        os.environ, {"NOTIFY_SOCKET": endpoint}), \
                        mock.patch.object(
                            brainstem, "_restore_barrier_present",
                            return_value=False), \
                        mock.patch.object(
                            brainstem.sialib, "brainstem_owner",
                            side_effect=brainstem_owner), \
                        mock.patch.object(brainstem.signal, "signal"), \
                        mock.patch.object(brainstem.sialib, "ensure_dirs"), \
                        mock.patch.object(brainstem.sialib, "log"), \
                        mock.patch.object(
                            brainstem.sialib, "load_memo",
                            return_value={"pulse_seq": 0}), \
                        mock.patch.object(
                            brainstem.sialib, "recover_ledger_transitions",
                            return_value=(False, [])), \
                        mock.patch.object(
                            brainstem.sialib, "durable_ledger_append",
                            side_effect=append), \
                        mock.patch.object(brainstem.socket, "socket",
                                          return_value=notifier):
                    self.assertEqual(brainstem.main(), 0)
            finally:
                brainstem._stop = prior_stop
            self.assertEqual(
                trace, ["BOOT:brainstem", "READY", "HALT:brainstem"])

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

    def test_note_binds_redaction_count_to_the_sanitized_queue_request(self):
        queue_module = sys.modules["siaqueue"]
        receipt = {
            "request_id": "a" * 32,
            "queued_at": "2026-08-30T12:00:00Z",
        }
        prior = copy.deepcopy(sia.sialib.REDACTIONS)
        sia.sialib.REDACTIONS.clear()
        try:
            with mock.patch.object(
                    queue_module, "enqueue_note", return_value=receipt) as enqueue, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sia.cmd_note([
                    "remember", "token=abcdefghijklmnop",
                    "--from", "codex",
                ]), 0)
            args, kwargs = enqueue.call_args
            self.assertEqual(args[0], sia.sialib.STATE)
            self.assertNotIn("abcdefghijklmnop", args[2])
            self.assertEqual(kwargs["redactions"], {"agent-note": 1})
            self.assertNotIn("agent-note", sia.sialib.REDACTIONS)
        finally:
            sia.sialib.REDACTIONS.clear()
            sia.sialib.REDACTIONS.update(prior)


if __name__ == "__main__":
    unittest.main(verbosity=2)
