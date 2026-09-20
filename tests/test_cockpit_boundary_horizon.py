#!/usr/bin/env python3
"""Boundary discipline for the cockpit and bar surfaces.

Every check here pins a defect that shipped: a snapshot that passed
validation while the UI read fields it never required, a thought stream
rendered with no shape check and a silent catch, three FileViews that
resolved a failed load into last-good pixels with an EMPTY boundary
string, an `installing` record that nothing ever expired, and a bar that
kept painting a reassuring continuity state for a worker that had
stopped publishing.

The QML surfaces are not loadable from a unit test, so the pure logic is
lifted out of them by name and executed under Node, and the wiring that
cannot be lifted is pinned as source contract.
"""

import copy
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import unittest

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = Path(__file__).resolve().parent.parent


def _read(relative):
    return (REPO / relative).read_text(encoding="utf-8")


def _scan_block(source, opening):
    """Return the index of the brace closing the one at *opening*.

    Unlike the older brace walker in the marketplace suite this one skips
    line and block comments, so an apostrophe inside a comment cannot
    swallow a closing brace and fail an unrelated assertion.
    """
    depth = 0
    index = opening
    length = len(source)
    while index < length:
        char = source[index]
        pair = source[index:index + 2]
        if pair == "//":
            index = source.find("\n", index)
            if index == -1:
                break
            continue
        if pair == "/*":
            index = source.index("*/", index) + 2
            continue
        if char in {'"', "'", "`"}:
            quote = char
            index += 1
            while index < length:
                if source[index] == "\\":
                    index += 2
                    continue
                if source[index] == quote:
                    break
                index += 1
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise AssertionError("unterminated block")


def _qml_function(source, name):
    """Return the full text of a root-scoped QML function declaration."""
    marker = "\n  function " + name + "("
    start = source.index(marker) + 1
    opening = source.index("{", start)
    return source[start:_scan_block(source, opening) + 1]


def _qml_element(source, id_line):
    """Return the element block whose body declares *id_line*."""
    anchor = source.index(id_line)
    opening = source.rindex("{", 0, anchor)
    return source[opening:_scan_block(source, opening) + 1]


class _JsRunner:
    """Evaluate lifted QML/Model.js logic in a bare Node context."""

    SCRIPT = r'''
const fs = require("fs")
const vm = require("vm")
const context = {}
vm.createContext(context)
for (const path of JSON.parse(process.argv[1]))
  vm.runInContext(
    fs.readFileSync(path, "utf8").replace(/^\.pragma library\s*$/m, ""),
    context)
vm.runInContext(process.argv[2], context)
const args = JSON.parse(process.argv[4])
process.stdout.write(
  JSON.stringify(context[process.argv[3]].apply(null, args)))
'''


class CockpitBoundaryHorizonTests(unittest.TestCase):
    def setUp(self):
        self.node = shutil.which("node")
        if self.node is None:
            self.skipTest("Node is unavailable for executable QML logic")

    def _contains(self, haystack, needle, label):
        """assertIn against a whole QML file dumps the file into CI logs."""
        self.assertTrue(needle in haystack, label + ": missing " + needle)

    def _lacks(self, haystack, needle, label):
        self.assertFalse(
            needle in haystack, label + ": unexpected " + needle)

    def _run(self, prelude, function_name, arguments, sources=()):
        result = subprocess.run(
            [self.node, "-e", _JsRunner.SCRIPT,
             json.dumps([str(REPO / name) for name in sources]),
             prelude, function_name,
             json.dumps(list(arguments), separators=(",", ":"))],
            cwd=REPO, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def _cockpit_logic(self, *names):
        cockpit = _read("Cockpit.qml")
        for name in names:
            self._contains(
                cockpit, "\n  function " + name + "(",
                "Cockpit.qml")
        # `root.` is the QML scope prefix; the lifted declarations become
        # plain top-level functions in the Node context.
        return "\n".join(
            _qml_function(cockpit, name) for name in names
        ).replace("root.", "")

    def _model_call(self, function_name, *arguments):
        return self._run(
            "", function_name, arguments, sources=("Model.js",))

    # ------------------------------------------------------- finding 7

    def _snapshot(self, **overrides):
        snapshot = {
            "v": 1,
            "version": "1.7.8",
            "ts": "2026-09-04T08:05:57Z",
            "state": "thinking",
            "day": "2026-09-04",
            "events_pulse": 0,
            "events_today": 0,
            "organs": {},
            "errors": {},
            "pulse_seq": 7780,
            "pages": 1894,
            "graph_nodes": 260,
            "graph_edges": 465,
            "ledger": {"seq": 7612, "head": "291610e08125"},
            "ledger_transition": {
                "state": "signed", "recovered": 0,
                "pending_errors": 0,
            },
            "publication_id": "a780a1590f1e41d19e68c31c0ee93c88",
            "graph_publication_id": "b780a1590f1e41d19e68c31c0ee93c88",
            "projection_debt": {"graph": "", "consolidation": ""},
            "integrity": {
                "chains": {"sia": "pass"}, "verdict": "pass",
                "checked_at": "2026-09-04T08:05:57Z",
            },
            "sync_note": "",
            "thought": {
                "ts": "", "kind": "", "text": "",
                "origin": "legacy-unlabeled",
            },
            "dream": {},
            "history": [],
            "workspace": [],
            "mind": {
                "nodes": 0, "edges": 0, "decay_active": 0,
                "decay_demoted": 0, "rehearsal_eligible": 0,
                "rehearsal_due": 0, "pinned": 0},
            "agent_queue": {
                "materialized": 0, "refused": 0, "acknowledged": 0},
            "takes": {},
            "intents": [],
            "bench_trend": [],
            "bench_trend_boundary": {"legacy_truncated": False},
            "redactions": {},
        }
        snapshot.update(overrides)
        return snapshot

    def _valid_snapshot(self, snapshot):
        prelude = ("var Model = { residentStatusShape: residentStatusShape, "
                   "residentLedgerSummaryShape: residentLedgerSummaryShape }\n")
        prelude += self._cockpit_logic(
            "isNonNegativeCount", "isPlainRecord", "validLedgerSummary",
            "projectionDebtKnownFor", "validStatusSnapshot")
        return self._run(
            prelude, "validStatusSnapshot", [snapshot], sources=("Model.js",))

    def test_status_validator_requires_every_field_the_counts_render(self):
        # The status-count row prints status.pages and status.graph_edges, the
        # header prints status.pulse_seq, and the chain row prints
        # status.ledger.seq and .head -- all unguarded.  A snapshot that
        # passed validation without them rendered "memories: undefined"
        # under a boundary that claimed the status was good.
        self.assertTrue(self._valid_snapshot(self._snapshot()))

        # graph_publication_id is covered separately: frozen v1.7.8 status
        # intentionally lacks it, while a present current field is UUID-bound.
        for field in (
                "day", "events_pulse", "organs", "pages", "graph_nodes",
                "graph_edges", "pulse_seq", "ledger", "ledger_transition",
                "events_today", "errors",
                "integrity", "thought", "dream", "history", "workspace",
                "takes", "intents", "bench_trend", "bench_trend_boundary",
                "redactions", "sync_note"):
            missing = self._snapshot()
            del missing[field]
            self.assertFalse(
                self._valid_snapshot(missing),
                "a snapshot without " + field + " must not validate")

        self.assertFalse(self._valid_snapshot(
            self._snapshot(ledger={"seq": 7612})))
        self.assertFalse(self._valid_snapshot(
            self._snapshot(ledger={"seq": "7612", "head": "abc"})))
        self.assertFalse(self._valid_snapshot(self._snapshot(pages=-1)))
        self.assertFalse(self._valid_snapshot(self._snapshot(pages=1.5)))
        self.assertFalse(self._valid_snapshot(
            self._snapshot(events_today=-1)))
        self.assertFalse(self._valid_snapshot(
            self._snapshot(events_today=1.5)))
        self.assertFalse(self._valid_snapshot(
            self._snapshot(errors=[])))

    def test_current_status_nested_claims_use_the_exact_producer_shapes(self):
        valid = self._snapshot()
        valid["thought"] = {
            "ts": "2026-09-04T08:05:56Z", "kind": "integrity",
            "text": "the retained sweep passed", "origin": "derived",
        }
        valid["dream"] = {
            "last": "2026-09-03T03:33:00Z", "status": "ok",
            "summary": "cycle complete",
        }
        valid["takes"] = {
            "open": 2, "due": 1, "resolved": 1, "brier": 0.25,
            "calibration_status": "single-case",
            "monitoring_display_eligible": False,
            "unresolvable": 0, "invalid_resolved": 0,
            "invalid_records": 0,
        }
        self.assertTrue(self._valid_snapshot(valid))
        mutations = []
        extra = copy.deepcopy(valid); extra["claim"] = "not produced"
        mutations.append(extra)
        for field in ("thought", "dream", "takes"):
            row = copy.deepcopy(valid); row[field]["claim"] = "not produced"
            mutations.append(row)
        row = copy.deepcopy(valid); row["takes"]["due"] = 3
        mutations.append(row)
        row = copy.deepcopy(valid); row["takes"]["brier"] = 2
        mutations.append(row)
        row = copy.deepcopy(valid)
        row["takes"]["monitoring_display_eligible"] = True
        mutations.append(row)
        row = copy.deepcopy(valid); row["dream"]["last"] = "yesterday"
        mutations.append(row)
        row = copy.deepcopy(valid); row["thought"]["ts"] = "tomorrow"
        mutations.append(row)
        for kind, text in (
                ("Not Canonical", "ordinary thought"),
                ("integrity", "active [link]"),
                ("integrity", "hidden\U000e0001format"),
                ("integrity", "token=abcdefghijklmnop")):
            row = copy.deepcopy(valid)
            row["thought"].update({"kind": kind, "text": text})
            mutations.append(row)
        row = copy.deepcopy(valid); row["redactions"] = {"not canonical": 1}
        mutations.append(row)
        row = copy.deepcopy(valid); row["projection_debt"]["graph"] = "\ud800"
        mutations.append(row)
        row = copy.deepcopy(valid)
        row["errors"] = {"token=abcdefghijklmnop": "refused"}
        mutations.append(row)
        row = copy.deepcopy(valid)
        row["errors"] = {"source": {"error": "not a producer row"}}
        mutations.append(row)
        row = copy.deepcopy(valid)
        row["errors"] = {"source": "x" * 161}
        mutations.append(row)
        row = copy.deepcopy(valid)
        row["errors"] = {
            "source": [{"file": "fixture", "error": "x" * 161}]}
        mutations.append(row)
        row = copy.deepcopy(valid)
        row["organs"] = {"x" * 201: {"today": 0, "last_ts": ""}}
        mutations.append(row)
        row = copy.deepcopy(valid)
        row["organs"] = {
            "x" + str(index): {"today": 0, "last_ts": ""}
            for index in range(1041)}
        mutations.append(row)
        row = copy.deepcopy(valid)
        row["integrity"]["chains"] = {"x" * 201: "pass"}
        mutations.append(row)
        row = copy.deepcopy(valid); row["redactions"] = {"x" * 201: 1}
        mutations.append(row)
        row = copy.deepcopy(valid); row["sync_note"] = "line one\nline two"
        mutations.append(row)
        for workspace in (
                ["not a slug"], ["../escape"], ["sia/cortex\u200b"],
                ["sia/cortex", "sia/cortex"]):
            row = copy.deepcopy(valid)
            row["workspace"] = workspace
            mutations.append(row)
        row = copy.deepcopy(valid)
        row["dream"] = {
            "last": "", "attempt": "2026-09-04T08:05:56Z",
            "status": "failed", "summary": "token=abcdefghijklmnop",
        }
        mutations.append(row)
        for control in (
                "\u0890", "\u0891", "\U000110bd", "\U000110cd",
                "\U00013430", "\U0001343f", "\U0001bca0",
                "\U0001bca3", "\U0001d173", "\U0001d17a",
                "\U000e0001", "\U000e0020", "\U000e007f"):
            row = copy.deepcopy(valid)
            row["errors"] = {"source": "hidden" + control + "format"}
            mutations.append(row)
        row = copy.deepcopy(valid)
        row["integrity"]["chains"] = {"other": "pass"}
        row["ledger"] = {"seq": 0, "head": ""}
        mutations.append(row)
        row = copy.deepcopy(valid); row["pages"] = 0
        row["graph_nodes"] = 1
        mutations.append(row)
        row = copy.deepcopy(valid); row["graph_nodes"] = 261
        mutations.append(row)
        row = copy.deepcopy(valid); row["graph_edges"] = 4097
        mutations.append(row)
        for impossible_mind in ({
                "nodes": 1, "edges": 1,
                "decay_active": 1, "decay_demoted": 1,
                "rehearsal_eligible": 0, "rehearsal_due": 0,
                "pinned": 0,
        }, {
                "nodes": 1, "edges": 0,
                "decay_active": 0, "decay_demoted": 0,
                "rehearsal_eligible": 2, "rehearsal_due": 0,
                "pinned": 0,
        }, {
                "nodes": 1, "edges": 0,
                "decay_active": 0, "decay_demoted": 0,
                "rehearsal_eligible": 1, "rehearsal_due": 2,
                "pinned": 0,
        }, {
                "nodes": 1, "edges": 0,
                "decay_active": 0, "decay_demoted": 0,
                "rehearsal_eligible": 1, "rehearsal_due": 1,
                "pinned": 2,
        }):
            row = copy.deepcopy(valid); row["mind"] = impossible_mind
            mutations.append(row)
        row = copy.deepcopy(valid)
        row["agent_queue"] = {
            "materialized": 0, "refused": 0, "acknowledged": 1}
        mutations.append(row)
        row = copy.deepcopy(valid)
        row["agent_queue"] = {
            "materialized": 1025, "refused": 0, "acknowledged": 0}
        mutations.append(row)
        row = copy.deepcopy(valid)
        row["takes"].update({
            "resolved": 2, "calibration_status": "monitoring-population",
            "monitoring_display_eligible": True})
        mutations.append(row)
        row = copy.deepcopy(valid)
        row["takes"].update({
            "resolved": 30, "calibration_status": "descriptive-series"})
        mutations.append(row)
        row = copy.deepcopy(valid); row["ledger_transition"]["recovered"] = 1025
        mutations.append(row)
        row = copy.deepcopy(valid); row["ledger_transition"]["pending_errors"] = 1
        mutations.append(row)
        row = copy.deepcopy(valid); row["ledger_transition"]["state"] = "pending"
        mutations.append(row)
        for status in mutations:
            with self.subTest(status=status):
                self.assertFalse(self._valid_snapshot(status))

        descriptive = copy.deepcopy(valid)
        descriptive["takes"].update({
            "resolved": 2, "calibration_status": "descriptive-series"})
        self.assertTrue(self._valid_snapshot(descriptive))
        imbalanced = copy.deepcopy(valid)
        imbalanced["takes"].update({
            "resolved": 30, "calibration_status": "outcome-imbalanced"})
        self.assertTrue(self._valid_snapshot(imbalanced))

    def test_snapshot_json_rejects_duplicate_decoded_keys(self):
        wrapper = """
function strictAccepted(text) {
  try { strictJsonParse(text); return true }
  catch (error) { return false }
}
"""
        self.assertTrue(self._run(
            wrapper, "strictAccepted", ['{"v":1,"nested":{"x":2}}'],
            sources=("Model.js",)))
        for raw in (
                '{"v":0,"v":1}',
                '{"v":0,"\\u0076":1}',
                '{"nested":{"x":0,"x":1}}',
                '{"errors":{"fixture":1e400}}'):
            with self.subTest(raw=raw):
                self.assertFalse(self._run(
                    wrapper, "strictAccepted", [raw],
                    sources=("Model.js",)))
        for surface in ("Cockpit.qml", "Panel.qml"):
            self.assertIn(
                "Model.strictStatusJsonParse(text)",
                _qml_function(_read(surface), "applyStatus"))

    def test_status_json_preserves_integer_lexical_types(self):
        wrapper = """
function strictStatusAccepted(text) {
  try { return residentStatusShape(strictStatusJsonParse(text)) }
  catch (error) { return false }
}
"""
        valid = json.dumps(self._snapshot(), separators=(",", ":"))
        take_valid = json.dumps(self._snapshot(takes={
            "open": 2, "due": 1, "resolved": 1, "brier": 0.25,
            "calibration_status": "single-case",
            "monitoring_display_eligible": False,
            "unresolvable": 0, "invalid_resolved": 0,
            "invalid_records": 0,
        }), separators=(",", ":"))
        malformed = (
            valid.replace('"pulse_seq":7780', '"pulse_seq":1.0'),
            valid.replace('"nodes":0', '"nodes":1e0', 1),
            take_valid.replace('"open":2', '"open":2.0'),
        )
        for raw in malformed:
            with self.subTest(raw=raw):
                self.assertFalse(self._run(
                    wrapper, "strictStatusAccepted", [raw],
                    sources=("Model.js",)))

        legal_metric = self._snapshot(bench_trend=[{
            "date": "2026-09-04", "slug_match_at_5": 1.0,
            "kind": "heuristic-slug-retrieval-drift-tripwire",
        }])
        self.assertTrue(self._run(
            wrapper, "strictStatusAccepted",
            [json.dumps(legal_metric, separators=(",", ":"))],
            sources=("Model.js",)))

    def test_status_common_shape_uses_only_producer_states(self):
        for state in ("failed", "degraded", "thinking", "ok"):
            snapshot = self._snapshot(state=state)
            if state == "failed":
                snapshot["integrity"] = {
                    "chains": {"sia": "fail"}, "verdict": "fail",
                    "checked_at": "2026-09-04T08:05:57Z",
                }
            with self.subTest(state=state):
                self.assertTrue(
                    self._model_call("residentStatusShape", snapshot))
                self.assertTrue(self._valid_snapshot(snapshot))

        for state in ("", "ready", "healthy", "unknown", 7, None):
            snapshot = self._snapshot(state=state)
            with self.subTest(state=state):
                self.assertFalse(
                    self._model_call("residentStatusShape", snapshot))
                self.assertFalse(self._valid_snapshot(snapshot))

        impossible = self._snapshot(ts="2026-02-30T08:05:57Z")
        self.assertFalse(self._model_call(
            "residentStatusShape", impossible))
        self.assertFalse(self._valid_snapshot(impossible))
        impossible = self._snapshot(day="2026-02-30")
        self.assertFalse(self._model_call(
            "residentStatusShape", impossible))
        self.assertFalse(self._valid_snapshot(impossible))

        for state in ("thinking", "ok"):
            impossible = self._snapshot(
                state=state, errors={"config": "broken"})
            with self.subTest(state=state, contradiction="errors"):
                self.assertFalse(self._model_call(
                    "residentStatusShape", impossible))
                self.assertFalse(self._valid_snapshot(impossible))
            impossible = self._snapshot(
                state=state, sync_note="brain sync failed")
            with self.subTest(state=state, contradiction="sync"):
                self.assertFalse(self._model_call(
                    "residentStatusShape", impossible))
                self.assertFalse(self._valid_snapshot(impossible))

        contradictions = []
        impossible = self._snapshot(state="ok")
        impossible["integrity"]["chains"]["sia"] = "fail"
        impossible["integrity"]["verdict"] = "fail"
        contradictions.append(impossible)
        impossible = self._snapshot()
        impossible["integrity"]["chains"]["sia"] = "nonsense"
        contradictions.append(impossible)
        impossible = self._snapshot()
        impossible["integrity"]["chains"]["sia"] = "absent"
        contradictions.append(impossible)
        impossible = self._snapshot()
        impossible["integrity"]["checked_at"] = "not-a-time"
        contradictions.append(impossible)
        for impossible in contradictions:
            with self.subTest(contradiction=impossible["integrity"]):
                self.assertFalse(self._model_call(
                    "residentStatusShape", impossible))
                self.assertFalse(self._valid_snapshot(impossible))

        retained_integrity = self._snapshot(
            state="failed", errors={"brainstem": "pulse failed"})
        self.assertTrue(self._model_call(
            "residentStatusShape", retained_integrity))
        degraded = self._snapshot(state="degraded")
        degraded["integrity"]["chains"]["sia"] = "absent"
        degraded["integrity"]["verdict"] = "degraded"
        self.assertTrue(self._model_call("residentStatusShape", degraded))

    def test_rendered_status_collections_require_producer_row_shapes(self):
        valid = self._snapshot(
            organs={"notify": {"today": 0, "last_ts": ""}},
            history=[["2026-09-04T08:05:57Z", 0]],
            workspace=["sia/cortex"],
            intents=[{
                "id": "0123456789", "text": "finish the audit",
                "due": "2026-09-04", "days_left": 0,
            }],
            bench_trend=[{
                "date": "2026-09-04", "slug_match_at_5": 0.5,
                "kind": "heuristic-slug-retrieval-drift-tripwire",
            }])
        self.assertTrue(self._model_call("residentStatusShape", valid))
        self.assertTrue(self._valid_snapshot(valid))

        malformed = []
        for field in ("history", "workspace", "intents", "bench_trend"):
            candidate = copy.deepcopy(valid)
            candidate[field] = [None]
            malformed.append(candidate)
        candidate = copy.deepcopy(valid)
        candidate["organs"] = {"notify": None}
        malformed.append(candidate)
        candidate = copy.deepcopy(valid)
        candidate["events_today"] = 1
        malformed.append(candidate)
        for candidate in malformed:
            with self.subTest(candidate=candidate):
                self.assertFalse(
                    self._model_call("residentStatusShape", candidate))
                self.assertFalse(self._valid_snapshot(candidate))

    def test_current_status_shape_matches_backend_bounds(self):
        malformed = []
        malformed.append(self._snapshot(
            organs={"Bad Name": {"today": 0, "last_ts": ""}}))
        candidate = self._snapshot()
        candidate["integrity"]["extra"] = True
        malformed.append(candidate)
        malformed.append(self._snapshot(workspace=["x" * 4097]))
        malformed.append(self._snapshot(intents=[{
            "id": "0123456789", "text": "x" * 70 + "y",
            "due": "2026-09-04", "days_left": 0,
        }]))
        malformed.append(self._snapshot(intents=[{
            "id": "not-an-id", "text": "finish the audit",
            "due": "2026-09-04", "days_left": 0,
        }]))
        malformed.append(self._snapshot(intents=[{
            "id": "0123456789", "text": "line one\nline two",
            "due": "2026-09-04", "days_left": 0,
        }]))
        malformed.append(self._snapshot(intents=[{
            "id": "0123456789", "text": "token=abcdefghijklmnop",
            "due": "2026-09-04", "days_left": 0,
        }]))
        for candidate in malformed:
            with self.subTest(candidate=candidate):
                self.assertFalse(
                    self._model_call("residentStatusShape", candidate))
                self.assertFalse(self._valid_snapshot(candidate))

        epoch = self._snapshot(ts="1970-01-01T00:00:00Z")
        epoch["integrity"]["checked_at"] = "1970-01-01T00:00:00Z"
        epoch["history"] = [["1970-01-01T00:00:00Z", 0]]
        epoch["organs"] = {
            "notify": {"today": 0, "last_ts": "1970-01-01T00:00:00Z"}}
        self.assertTrue(self._model_call("residentStatusShape", epoch))
        self.assertTrue(self._valid_snapshot(epoch))

        zero_year = "0000-01-01T00:00:00Z"
        invalid_timestamps = []
        candidate = self._snapshot(ts=zero_year)
        invalid_timestamps.append(candidate)
        candidate = self._snapshot()
        candidate["integrity"]["checked_at"] = zero_year
        invalid_timestamps.append(candidate)
        candidate = self._snapshot(history=[[zero_year, 0]])
        invalid_timestamps.append(candidate)
        candidate = self._snapshot(organs={
            "notify": {"today": 0, "last_ts": zero_year}})
        invalid_timestamps.append(candidate)
        for candidate in invalid_timestamps:
            with self.subTest(zero_year_candidate=candidate):
                self.assertFalse(
                    self._model_call("residentStatusShape", candidate))
                self.assertFalse(self._valid_snapshot(candidate))

        unsafe_integer = self._snapshot(pulse_seq=9007199254740992)
        self.assertFalse(
            self._model_call("residentStatusShape", unsafe_integer))
        self.assertFalse(self._valid_snapshot(unsafe_integer))

    def test_stamped_status_publication_ids_match_the_backend_envelope(self):
        empty_graph = self._snapshot(
            graph_publication_id="", pages=0,
            graph_nodes=0, graph_edges=0)
        self.assertTrue(self._model_call(
            "residentStatusShape", empty_graph),
            "the producer uses an empty graph id before its first export")
        for field in ("pages", "graph_nodes", "graph_edges"):
            unbound = copy.deepcopy(empty_graph)
            unbound[field] = 1
            with self.subTest(unbound_graph_count=field):
                self.assertFalse(self._model_call(
                    "residentStatusShape", unbound))

        for field, value in (
                ("publication_id", ""),
                ("publication_id", "A" * 32),
                ("publication_id", "a" * 31),
                ("graph_publication_id", "G" * 32),
                ("graph_publication_id", "b" * 33)):
            malformed = self._snapshot()
            malformed[field] = value
            with self.subTest(field=field, value=value):
                self.assertFalse(self._model_call(
                    "residentStatusShape", malformed))

    def test_vitals_withdraw_graph_counts_without_a_graph_generation(self):
        cockpit = " ".join(_read("Cockpit.qml").split())
        self.assertIn(
            'root.currentStatus && root.currentGraph ? String(root.currentStatus.pages) : "—"',
            cockpit)
        self.assertIn(
            'root.currentStatus && root.currentGraph ? String(root.currentStatus.graph_edges) : "—"',
            cockpit)

        frozen = self._snapshot()
        del frozen["graph_publication_id"]
        self.assertTrue(self._model_call(
            "residentStatusShape", frozen),
            "frozen v1.7.8 status intentionally predates graph binding")

    def test_ahead_runtime_evidence_survives_status_render_rejection(self):
        status = self._snapshot(version="1.7.9", state="sleeping")
        completion = {"v": 1, "state": "ready", "version": "1.7.8"}
        self.assertFalse(self._valid_snapshot(status))

        evidence = self._model_call(
            "runtimeLifecycleEvidence", status, False, None, "1.7.8")

        self.assertEqual(evidence, {"version": "1.7.9"})
        self.assertEqual(self._model_call(
            "guidedLifecycle", evidence, completion, "1.7.8"), "ahead")
        self.assertEqual(self._model_call(
            "aheadVersion", evidence, "1.7.8"), "1.7.9")
        self.assertEqual(self._model_call(
            "aheadVersion", {"version": "1.7.8"}, "1.7.8"), "")
        self.assertEqual(self._model_call(
            "aheadVersion", {"version": "invalid"}, "1.7.8"), "")
        for surface in ("Cockpit.qml", "Panel.qml"):
            source = _read(surface)
            apply_status = " ".join(
                _qml_function(source, "applyStatus").split())
            status_file = " ".join(
                _qml_element(source, "id: statusFile").split())
            compact = " ".join(source.split())
            with self.subTest(surface=surface):
                self.assertIn("property var runtimeEvidence: null", source)
                self.assertIn(
                    "Model.runtimeLifecycleEvidence( parsed, valid, "
                    "root.runtimeEvidence, root.pluginVersion)",
                    apply_status)
                self.assertIn(
                    "Model.runtimeLifecycleEvidence( null, false, "
                    "root.runtimeEvidence, root.pluginVersion)",
                    apply_status)
                self.assertIn(
                    "Model.runtimeLifecycleEvidence( null, false, "
                    "root.runtimeEvidence, root.pluginVersion)",
                    status_file)
                self.assertIn(
                    "Model.guidedLifecycle(root.runtimeEvidence, "
                    "root.installCompletion, root.pluginVersion)", compact)

        cockpit_ahead = _qml_function(
            _read("Cockpit.qml"), "setupDescription").split(
                'if (root.releaseLifecycle === "ahead")', 1)[1]
        panel_ahead = _qml_function(_read("Panel.qml"), "tooltip").split(
            'if (root.releaseLifecycle === "ahead")', 1)[1].split(
                'if (root.releaseLifecycle === "update")', 1)[0]
        for label, source in (
                ("Cockpit.qml", cockpit_ahead),
                ("Panel.qml", panel_ahead)):
            with self.subTest(ahead_surface=label):
                compact_ahead = " ".join(source.split())
                self.assertIn("Model.aheadVersion(", compact_ahead)
                self.assertIn(
                    "root.runtimeEvidence, root.pluginVersion)",
                    compact_ahead)
                self.assertNotIn("root.status.version", source)

        cockpit = " ".join(_read("Cockpit.qml").split())
        self.assertIn(
            "Model.runtimeLifecycle(root.runtimeEvidence, "
            "root.pluginVersion)", cockpit)

        body = _qml_function(_read("Cockpit.qml"), "validStatusSnapshot")
        self.assertIn("Model.residentStatusShape(snapshot)", body)
        self.assertNotIn("snapshot.state", body)

    def test_install_completion_is_an_exact_producer_record(self):
        ready = {"v": 1, "state": "ready", "version": "1.7.8"}
        installing = {
            "v": 1, "state": "installing", "version": "1.7.8"}
        ahead = {"v": 1, "state": "ready", "version": "1.7.9"}
        for record in (ready, installing, ahead):
            self.assertTrue(self._model_call(
                "validInstallCompletion", record))
            malformed = dict(record, extra="unpublished")
            self.assertFalse(self._model_call(
                "validInstallCompletion", malformed))
            self.assertFalse(self._model_call(
                "installCompletionReady", malformed, "1.7.8"))
            self.assertFalse(self._model_call(
                "installCompletionInstalling", malformed, "1.7.8"))

        current = self._snapshot()
        self.assertEqual(self._model_call(
            "guidedLifecycle", current, ready, "1.7.8"), "ready")
        self.assertEqual(self._model_call(
            "guidedLifecycle", current, dict(ready, extra=True), "1.7.8"),
            "repair")
        self.assertEqual(self._model_call(
            "guidedLifecycle", None, installing, "1.7.8"), "installing")
        self.assertEqual(self._model_call(
            "guidedLifecycle", None, dict(installing, extra=True), "1.7.8"),
            "repair")
        self.assertEqual(self._model_call(
            "guidedLifecycle", None, ahead, "1.7.8"), "ahead")
        self.assertEqual(self._model_call(
            "guidedLifecycle", None, dict(ahead, extra=True), "1.7.8"),
            "repair")

    def test_lifecycle_markers_preserve_integer_lexical_types(self):
        wrapper = """
function strictInstallAccepted(text) {
  try { return validInstallCompletion(strictInstallCompletionJsonParse(text)) }
  catch (error) { return false }
}
function strictSetupAccepted(text) {
  try {
    return setupTerminalPresented(
      strictSetupMarkerJsonParse(text), 1000,
      "a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4", 1001)
  } catch (error) { return false }
}
"""
        install = '{"v":1,"version":"1.7.8","state":"ready"}'
        setup = ('{"attempt":"a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4",'
                 '"pid":1234,"ts":1000,"tty":true,"v":1}')
        self.assertTrue(self._run(
            wrapper, "strictInstallAccepted", [install],
            sources=("Model.js",)))
        self.assertTrue(self._run(
            wrapper, "strictSetupAccepted", [setup],
            sources=("Model.js",)))
        self.assertFalse(self._run(
            wrapper, "strictInstallAccepted",
            [install.replace('"v":1', '"v":1.0')],
            sources=("Model.js",)))
        for field in ('"pid":1234', '"ts":1000', '"v":1'):
            self.assertFalse(self._run(
                wrapper, "strictSetupAccepted",
                [setup.replace(field, field + ".0")],
                sources=("Model.js",)))

        for surface in ("Cockpit.qml", "Panel.qml"):
            self.assertIn(
                "Model.strictInstallCompletionJsonParse(text)",
                _qml_function(_read(surface), "applyInstallCompletion"))
        self.assertIn(
            "Model.strictSetupMarkerJsonParse(text)",
            _qml_function(_read("Cockpit.qml"), "applySetupPresence"))

    def test_tightening_the_shape_did_not_strand_legacy_upgrades(self):
        # statusLoadValid gates what guidedLifecycle is even shown, so
        # tightening validStatusSnapshot tightens lifecycle routing too: a
        # rejected snapshot is routed as if there were no resident memory service at
        # all.  The pre-release publisher already wrote pulse_seq, pages,
        # graph_edges and ledger, so a real legacy status still validates
        # and still routes to `update`.  If a future field is added to this
        # validator without checking that, an upgradable brain silently
        # becomes a repair condition.
        legacy = {
            "v": 1, "ts": "2026-09-04T08:05:57Z",
            "state": "thinking", "events_today": 0, "errors": {},
            "pulse_seq": 7780, "pages": 1894, "graph_edges": 465,
            "ledger": {"seq": 7612, "head": "291610e08125"},
            "publication_id": "a780a1590f1e41d19e68c31c0ee93c88",
            "projection_debt": {"graph": "", "consolidation": ""},
            "mind": {
                "nodes": 0, "edges": 0, "decay_active": 0,
                "decay_demoted": 0, "rehearsal_eligible": 0,
                "rehearsal_due": 0, "pinned": 0},
            "agent_queue": {
                "materialized": 0, "refused": 0, "acknowledged": 0},
        }
        self.assertTrue(
            self._valid_snapshot(legacy),
            "a legacy resident status must still validate")
        self.assertEqual(
            self._model_call("runtimeLifecycle", legacy, "1.7.8"), "update")
        self.assertEqual(
            self._model_call(
                "guidedLifecycle", legacy,
                {"v": 1, "state": "ready", "version": "1.7.8"}, "1.7.8"),
            "update")

        prior = self._snapshot(version="1.7.7")
        del prior["graph_publication_id"]
        self.assertTrue(
            self._valid_snapshot(prior),
            "the prior stamped runtime must remain upgradable")
        for field in (
                "day", "events_pulse", "graph_nodes", "thought", "dream",
                "takes", "intents", "history"):
            malformed_prior = copy.deepcopy(prior)
            del malformed_prior[field]
            with self.subTest(prior_missing=field):
                self.assertFalse(
                    self._model_call(
                        "residentStatusShape", malformed_prior))
                self.assertFalse(self._valid_snapshot(malformed_prior))
        evidence = self._model_call(
            "runtimeLifecycleEvidence", prior, True, None, "1.7.8")
        self.assertEqual(self._model_call(
            "guidedLifecycle", evidence,
            {"v": 1, "state": "ready", "version": "1.7.7"}, "1.7.8"),
            "update")

    def test_empty_ledger_sentinel_cannot_accompany_a_passing_sia_chain(self):
        sentinel = self._snapshot(ledger={"seq": 0, "head": ""})
        self.assertFalse(self._valid_snapshot(sentinel))
        sentinel["state"] = "degraded"
        sentinel["integrity"] = {
            "chains": {"sia": "absent"}, "verdict": "degraded",
            "checked_at": "2026-09-04T08:05:57Z",
        }
        self.assertTrue(self._valid_snapshot(sentinel))

    # ------------------------------------------------------- finding 6

    def _valid_stream(self, stream, now="2026-09-04T08:05:57Z"):
        prelude = """var Model = {
  validUtcSecondTimestamp: validUtcSecondTimestamp,
  recordHasExactly: recordHasExactly,
  strictStringLength: strictStringLength,
  codePointIsControlOrFormat: codePointIsControlOrFormat,
  canonicalCorpusSlug: canonicalCorpusSlug,
  legacyModelThoughtKind: legacyModelThoughtKind
}
"""
        prelude += self._cockpit_logic(
            "isPlainRecord", "validGraphString", "validGraphSlug",
            "validThoughtKind", "validThoughtRecoveryReceipt",
            "thoughtCodePointIsControl", "thoughtTextIsCanonical",
            "validThoughtSlugFor", "validThought", "validThoughtStream")
        prelude += """
function validThoughtStreamAt(stream, nowIso) {
  return validThoughtStream(stream, Date.parse(nowIso))
}
"""
        return self._run(
            prelude, "validThoughtStreamAt", [stream, now],
            sources=("Model.js",))

    def _thought(self, **overrides):
        thought = {
            "ts": "2026-09-04T07:34:01Z",
            "kind": "anomaly",
            "text": "Unusual activity in tag association.",
            "links": ["sia/cortex"],
            "urgent": False,
            "origin": "derived",
            "slug": "thoughts/2026-09-04-0734-anomaly",
        }
        thought.update(overrides)
        return thought

    def test_thought_stream_shape_is_checked_before_it_is_rendered(self):
        # This is the plane carrying model-origin prose.  kind and origin
        # are painted into the row as the honesty labels themselves, so a
        # record missing either rendered the word "undefined" where a label
        # belongs -- which reads as a label, not as an absence.
        self.assertTrue(
            self._valid_stream({"v": 1, "thoughts": [self._thought()]}))

        for field in ("ts", "kind", "text", "links", "urgent", "slug"):
            broken = self._thought()
            del broken[field]
            self.assertFalse(
                self._valid_stream({"v": 1, "thoughts": [broken]}),
                "a thought without " + field + " must not validate")

        self.assertFalse(self._valid_stream(
            {"v": 1, "thoughts": [self._thought(kind="")]}))
        self.assertFalse(self._valid_stream(
            {"v": 1, "thoughts": [self._thought(origin=7)]}))
        self.assertFalse(self._valid_stream(
            {"v": 1, "thoughts": [self._thought(origin="invented")]}))
        self.assertFalse(self._valid_stream(
            {"v": 1, "thoughts": [self._thought(urgent="false")]}))
        self.assertFalse(self._valid_stream(
            {"v": 1, "thoughts": [self._thought(ts="not-a-date")]}))
        self.assertFalse(self._valid_stream(
            {"v": 1, "thoughts": [self._thought(
                ts="2026-02-30T08:05:57Z")]}))
        self.assertFalse(self._valid_stream(
            {"v": 1, "thoughts": [self._thought(
                ts="09/04/2026 07:34:01")]}))
        self.assertTrue(self._valid_stream({
            "v": 1, "thoughts": [self._thought(
                ts="2999-09-04T08:05:57Z",
                slug="thoughts/2999-09-04-0805-anomaly")],
        }))
        self.assertFalse(self._valid_stream({"v": 1, "thoughts": "no"}))
        self.assertFalse(self._valid_stream({"thoughts": []}))
        self.assertFalse(self._valid_stream(None))

    def test_thought_stream_is_bounded_to_the_exact_producer_envelope(self):
        queue_id = "a" * 32
        complete = self._thought(
            slug="thoughts/queue-" + queue_id,
            queue_id=queue_id)
        recovery = {
            "claim_id": "b" * 32,
            "payload_sha256": "c" * 64,
        }
        self.assertTrue(self._valid_stream({
            "v": 1, "thoughts": [complete],
            "thought_recovery": recovery,
        }))
        queued_legacy = dict(complete)
        del queued_legacy["origin"]
        self.assertTrue(self._valid_stream({
            "v": 1, "thoughts": [queued_legacy],
        }))

        for extra in ("payload", "html", "model_label"):
            row = self._thought()
            row[extra] = "untrusted"
            with self.subTest(extra_row_field=extra):
                self.assertFalse(self._valid_stream(
                    {"v": 1, "thoughts": [row]}))
        self.assertFalse(self._valid_stream(
            {"v": 1, "thoughts": [], "extra": []}))
        for optional in ("links", "urgent", "slug"):
            partial = self._thought()
            del partial[optional]
            with self.subTest(unsupported_partial_shape=optional):
                self.assertFalse(self._valid_stream(
                    {"v": 1, "thoughts": [partial]}))

        # Arithmetic evidence: status=exact, parsed=200+1, exact=201. The producer retains
        # at most MAX_THOUGHT_INBOX_ITEMS (200) projection rows.
        self.assertFalse(self._valid_stream({
            "v": 1, "thoughts": [self._thought() for _ in range(201)],
        }))

        self.assertTrue(self._valid_stream({
            "v": 1,
            "thoughts": [{"kind": "k" * 2000, "text": "t" * 2000}],
        }))
        self.assertTrue(self._valid_stream({
            "v": 1, "thoughts": [self._thought(text="t" * 2000)],
        }))
        # Arithmetic evidence: status=exact, parsed=2000+1, exact=2001.
        for field in ("kind", "text"):
            with self.subTest(overlong=field):
                self.assertFalse(self._valid_stream({
                    "v": 1,
                    "thoughts": [self._thought(**{field: "x" * 2001})],
                }))
        for kind in ("Upper", "two--parts", ".leading", "trailing-"):
            with self.subTest(noncanonical_kind=kind):
                self.assertFalse(self._valid_stream({
                    "v": 1, "thoughts": [self._thought(kind=kind)],
                }))

        for links in (
                [], ["sia/cortex", "sia/cortex"],
                ["z/page", "a/page"], ["../escape"]):
            with self.subTest(invalid_links=links):
                self.assertFalse(self._valid_stream({
                    "v": 1, "thoughts": [self._thought(links=links)],
                }))
        self.assertFalse(self._valid_stream({
            "v": 1,
            "thoughts": [self._thought(links=[
                "links/item-" + str(index) for index in range(201)])],
        }))
        self.assertFalse(self._valid_stream({
            "v": 1,
            "thoughts": [self._thought(queue_id="A" * 32)],
        }))
        # Baseline recovery retains arbitrary canonical historical page names.
        self.assertTrue(self._valid_stream({
            "v": 1,
            "thoughts": [self._thought(
                slug="thoughts/mind-save-boundary")],
        }))
        self.assertFalse(self._valid_stream({
            "v": 1,
            "thoughts": [self._thought(slug="../escape")],
        }))
        for text in (" leading", "two  spaces", "active [link]",
                     "hidden\u200bformat", "hidden\U000e0001tag",
                     "line\nbreak"):
            with self.subTest(noncanonical_text=text):
                self.assertFalse(self._valid_stream({
                    "v": 1, "thoughts": [self._thought(text=text)],
                }))
        duplicate = self._thought()
        self.assertFalse(self._valid_stream({
            "v": 1, "thoughts": [duplicate, dict(duplicate)],
        }))
        duplicate_queue = dict(complete)
        duplicate_queue["slug"] = "thoughts/queue-" + queue_id
        self.assertFalse(self._valid_stream({
            "v": 1, "thoughts": [complete, duplicate_queue],
        }))
        self.assertFalse(self._valid_stream({
            "v": 1, "thoughts": [complete],
            "thought_recovery": {**recovery, "extra": "untrusted"},
        }))

        validator = _qml_function(_read("Cockpit.qml"), "validThoughtStream")
        self.assertIn("stream.thoughts.length > 200", validator)
        self.assertIn("Model.recordHasExactly(stream, topFields)", validator)

        producer = _read("bin/sialib.py")
        page_producer = _read("bin/siathought.py")
        self.assertIn("MAX_THOUGHT_INBOX_ITEMS = 200", producer)
        self.assertIn("MAX_THOUGHT_INBOX_TEXT = 2000", producer)
        self.assertIn(
            'store["thoughts"] = store["thoughts"][-MAX_THOUGHT_INBOX_ITEMS:]',
            producer)
        self.assertIn(
            'allowed = {"ts", "kind", "text", "links", "urgent", "origin",',
            page_producer)

    def test_unlabeled_legacy_thoughts_stay_renderable(self):
        # sialib.load_thoughts deliberately leaves genuinely unlabeled
        # legacy rows unlabeled rather than laundering them into a
        # classification.  Requiring origin here would reject exactly the
        # rows the legacy-unlabeled boundary exists to expose.
        legacy = self._thought()
        del legacy["origin"]
        self.assertTrue(self._valid_stream({"v": 1, "thoughts": [legacy]}))
        self.assertTrue(self._valid_stream({
            "v": 1,
            "thoughts": [{"kind": "note", "text": "legacy text"}],
        }))
        self.assertFalse(self._valid_stream({
            "v": 1,
            "thoughts": [self._thought(origin="legacy-unlabeled")],
        }))

    def test_normalized_legacy_model_rows_and_missing_metadata_are_explicit(self):
        for kind in ("grade", "ponder", "note", "take"):
            row = {"kind": kind, "text": "legacy model prose",
                   "origin": "model"}
            with self.subTest(kind=kind):
                self.assertTrue(self._model_call(
                    "legacyModelThoughtKind", kind))
                self.assertTrue(self._valid_stream(
                    {"v": 1, "thoughts": [row]}))
        self.assertFalse(self._valid_stream({
            "v": 1,
            "thoughts": [{"kind": "attention", "text": "unknown source",
                          "origin": "model"}],
        }))

        logic = self._cockpit_logic(
            "thoughtUrgencyState", "thoughtRowMetadata")
        wrapper = """
var Model = {
  timeAgo: function(stamp) {
    return stamp === "2026-09-04T07:34:01Z" ? "observed age" : ""
  }
}
var root = {
  thoughtUrgencyState: thoughtUrgencyState,
  thoughtRowMetadata: thoughtRowMetadata
}
""" + logic
        minimal = {"kind": "attention", "text": "legacy text"}
        self.assertEqual(self._run(
            wrapper, "thoughtUrgencyState", [minimal]), "unrecorded")
        self.assertEqual(self._run(
            wrapper, "thoughtRowMetadata", [minimal, 0]),
            "attention · origin:legacy-unlabeled · urgency unrecorded"
            " · time unrecorded")
        future = self._thought(ts="2999-09-04T08:05:57Z")
        self.assertEqual(self._run(
            wrapper, "thoughtRowMetadata", [future, 0]),
            "anomaly · origin:derived · time unrecorded")

        thought_delegate = _qml_element(
            _read("Cockpit.qml"), "id: thoughtRow")
        self.assertIn("root.thoughtUrgencyState(", thought_delegate)
        self.assertIn('urgencyState === "unrecorded"', thought_delegate)
        self.assertIn("root.thoughtRowMetadata(", thought_delegate)

    def test_thought_stream_authority_does_not_depend_on_row_count(self):
        cockpit = _read("Cockpit.qml")
        for declaration in (
                "property bool thoughtsResolved: false",
                "property bool thoughtsLoadValid: false",
                "property bool thoughtsEverAdmitted: false"):
            self.assertIn(declaration, cockpit)

        count_logic = _qml_function(cockpit, "thoughtStreamCountText")
        wrapper = """
var thoughts = [], thoughtsLoadValid = false
function countFor(valid, rows) {
  thoughtsLoadValid = valid
  thoughts = rows
  return thoughtStreamCountText()
}
""" + count_logic.replace("root.", "")
        self.assertEqual(self._run(
            wrapper, "countFor", [False, []]), "—")
        self.assertEqual(self._run(
            wrapper, "countFor", [True, []]), "0")

        apply_body = _qml_function(cockpit, "applyThoughts")
        for assignment in (
                "root.thoughtsResolved = true",
                "root.thoughtsLoadValid = true",
                "root.thoughtsEverAdmitted = true"):
            self.assertIn(assignment, apply_body)
        rejected = _qml_function(cockpit, "thoughtsRejected")
        self.assertIn("root.thoughtsEverAdmitted", rejected)
        self.assertNotIn("root.thoughts.length", rejected)
        self.assertIn("root.thoughtsLoadValid = false", rejected)
        thought_file = _qml_element(cockpit, "id: thoughtsFile")
        self.assertIn("root.thoughtsEverAdmitted", thought_file)
        self.assertIn("root.thoughtsLoadValid = false", thought_file)
        self.assertIn("root.thoughtsResolved = false", thought_file)
        compact = " ".join(cockpit.split())
        self.assertGreaterEqual(
            compact.count("root.thoughtStreamCountText()"), 2)

    def test_thought_stream_failure_sets_a_boundary_and_keeps_last_good(self):
        cockpit = _read("Cockpit.qml")
        apply_body = _qml_function(cockpit, "applyThoughts")
        self.assertIn("validThoughtStream(t, Date.now())", apply_body)
        self.assertIn("thoughtsRejected()", apply_body)
        # The silent catch(e){} was the whole defect: a truncated read froze
        # the stream with no mark on screen at all.
        self.assertNotRegex(apply_body, r"catch\s*\(e\)\s*\{\s*\}")

        rejected = _qml_function(cockpit, "thoughtsRejected")
        self.assertIn("root.thoughtsEverAdmitted", rejected)
        self.assertIn("last good generated-entry stream", rejected)
        self.assertIn("no valid generated-entry stream", rejected)

        for needle in ('property string thoughtsBoundary: ""',
                       'visible: root.thoughtsBoundary !== ""',
                       "text: root.thoughtsBoundary"):
            self._contains(cockpit, needle, "Cockpit.qml")

    def test_structured_status_errors_render_each_admitted_detail(self):
        logic = self._cockpit_logic("isPlainRecord", "statusErrorRows")
        wrapper = "var root = {isPlainRecord: isPlainRecord}\n" + logic
        errors = {
            "catalog": [
                {"file": "broken.json", "error": "malformed row"},
                {"file": "missing.json", "error": "unavailable"},
            ],
            "config": [
                {"config": "senses.roots", "error": "invalid root"},
            ],
            "pulse": "worker refused",
        }
        self.assertEqual(self._run(
            wrapper, "statusErrorRows", [errors]), [
                "✗ catalog · file broken.json: malformed row",
                "✗ catalog · file missing.json: unavailable",
                "✗ config · config senses.roots: invalid root",
                "✗ pulse: worker refused",
            ])
        health = _qml_element(_read("Cockpit.qml"), "id: healthCol")
        self.assertIn("root.statusErrorRows(", health)
        self.assertNotIn(
            "root.currentStatus.errors[errRow.modelData]", health)

    def test_dream_failure_display_uses_attempt_and_names_prior_success(self):
        logic = _qml_function(_read("Cockpit.qml"), "dreamSummaryText")
        wrapper = """
var Model = {
  dreamGlyph: function() { return "D" },
  timeAgo: function(stamp) {
    if (stamp === "attempt") return "attempt age"
    if (stamp === "success") return "success age"
    return ""
  }
}
""" + logic.replace("root.", "")
        first_failure = {
            "last": "", "attempt": "attempt", "status": "failed",
            "summary": "worker unavailable",
        }
        self.assertEqual(self._run(
            wrapper, "dreamSummaryText", [first_failure, 0]),
            "D maintenance attempt attempt age · failed · worker unavailable")
        later_failure = dict(first_failure, last="success")
        self.assertEqual(self._run(
            wrapper, "dreamSummaryText", [later_failure, 0]),
            "D maintenance attempt attempt age · failed · worker unavailable"
            " · prior success success age")
        self.assertEqual(self._run(
            wrapper, "dreamSummaryText", [{}, 0]), "")
        cockpit = _read("Cockpit.qml")
        self.assertIn(
            "visible: root.dreamSummaryText(root.currentStatus",
            " ".join(cockpit.split()))

    def test_take_summary_unavailable_and_exclusions_are_not_zeroed(self):
        logic = self._cockpit_logic(
            "isPlainRecord", "takeSummaryAvailable",
            "takeSummaryText", "beliefCardVisibleFor")
        wrapper = "var root = {isPlainRecord: isPlainRecord, " \
                  "takeSummaryAvailable: takeSummaryAvailable}\n" + logic
        self.assertFalse(self._run(
            wrapper, "takeSummaryAvailable", [{}]))
        self.assertEqual(self._run(
            wrapper, "takeSummaryText", [{}]),
            "prediction summary unavailable")
        baseline = {
            "open": 0, "due": 0, "resolved": 0, "brier": None,
            "calibration_status": "no-resolved-outcomes",
            "monitoring_display_eligible": False,
            "unresolvable": 0, "invalid_resolved": 0,
            "invalid_records": 0,
        }
        for field, expected in (
                ("unresolvable", "1 unresolvable (excluded)"),
                ("invalid_resolved", "1 invalid resolved row excluded"),
                ("invalid_records",
                 "1 malformed/unknown-status row excluded")):
            takes = dict(baseline, **{field: 1})
            status = {"takes": takes, "bench_trend": []}
            with self.subTest(field=field):
                self.assertIn(expected, self._run(
                    wrapper, "takeSummaryText", [takes]))
                self.assertTrue(self._run(
                    wrapper, "beliefCardVisibleFor", [status]))
        self.assertTrue(self._run(
            wrapper, "beliefCardVisibleFor",
            [{"takes": {}, "bench_trend": [{"kind": "fixture"}]}]))

    def test_ledger_failure_sentinel_renders_unavailable(self):
        logic = _qml_function(_read("Cockpit.qml"), "ledgerSummaryText")
        wrapper = """
var Model = { chainGlyph: function() { return "L" } }
""" + logic.replace("root.", "")
        self.assertEqual(self._run(
            wrapper, "ledgerSummaryText", [{"seq": 0, "head": ""}]),
            "signed ledger head unavailable")
        self.assertEqual(self._run(
            wrapper, "ledgerSummaryText",
            [{"seq": 7, "head": "abcdef123456"}]),
            "L ledger seq 7 · abcdef123456…")

    def test_thought_stream_preserves_version_integer_lexeme(self):
        wrapper = """
function strictThoughtAccepted(text) {
  try { return strictThoughtStreamJsonParse(text).v === 1 }
  catch (error) { return false }
}
"""
        canonical = '{"v":1,"thoughts":[]}'
        self.assertTrue(self._run(
            wrapper, "strictThoughtAccepted", [canonical],
            sources=("Model.js",)))
        self.assertFalse(self._run(
            wrapper, "strictThoughtAccepted",
            [canonical.replace('"v":1', '"v":1.0')],
            sources=("Model.js",)))
        self.assertIn(
            "Model.strictThoughtStreamJsonParse(text)",
            _qml_function(_read("Cockpit.qml"), "applyThoughts"))

    def test_invalid_or_future_times_never_look_recent_or_fresh(self):
        wrapper = """
function timeAgoAt(stamp, nowIso) {
  return timeAgo(stamp, Date.parse(nowIso))
}
function freshnessAt(stamp, nowIso) {
  return freshness({ts: stamp}, Date.parse(nowIso))
}
"""
        now = "2026-09-04T08:05:57Z"
        for stamp in (
                "", "not-a-date", "2026-02-30T08:05:57Z",
                "09/04/2026 08:05:57", "2999-09-04T08:05:57Z"):
            with self.subTest(stamp=stamp):
                self.assertEqual(self._run(
                    wrapper, "timeAgoAt", [stamp, now],
                    sources=("Model.js",)), "")
                self.assertEqual(self._run(
                    wrapper, "freshnessAt", [stamp, now],
                    sources=("Model.js",)), 0)

        self.assertEqual(self._run(
            wrapper, "timeAgoAt", [now, "not-a-date"],
            sources=("Model.js",)), "")
        self.assertEqual(self._run(
            wrapper, "freshnessAt", [now, "not-a-date"],
            sources=("Model.js",)), 0)
        self.assertNotEqual(self._run(
            wrapper, "timeAgoAt", [now, now], sources=("Model.js",)), "")
        self.assertGreater(self._run(
            wrapper, "freshnessAt", [now, now], sources=("Model.js",)), 0)

    def test_rejected_status_withdraws_all_current_cockpit_claims(self):
        cockpit = _read("Cockpit.qml")
        start = cockpit.index("readonly property string eventsToday:")
        events = cockpit[start:cockpit.index("\n  readonly", start + 1)]
        self.assertIn("root.statusLoadValid", events)
        self.assertIn(': "—"', events)
        self.assertNotIn(": 0", events)

        marker = 'text: "published snapshot sensors reporting ✓'
        marker_at = cockpit.index(marker)
        visible_at = cockpit.rfind("visible:", 0, marker_at)
        clear_rule = cockpit[visible_at:marker_at]
        self.assertIn("root.currentStatus", clear_rule)
        self.assertIn(
            "root.isPlainRecord(root.currentStatus.errors)", clear_rule)
        self.assertIn("root.currentGraph", clear_rule)
        self.assertNotIn("!root.currentStatus.errors", clear_rule)

        errors_at = cockpit.index("root.statusErrorRows(")
        model_at = cockpit.rfind("model:", 0, errors_at)
        error_rule = cockpit[model_at:errors_at + 180]
        self.assertIn("root.currentStatus", error_rule)
        self.assertIn("root.statusErrorRows(", error_rule)

        state_start = cockpit.index("readonly property string brainState:")
        state_rule = cockpit[
            state_start:cockpit.index("\n  readonly", state_start + 1)]
        self.assertIn("statusLoadValid", state_rule)

        current_rule = _qml_function(cockpit, "currentStatusSnapshot")
        self.assertIn("root.statusLoadValid ? root.status : null", current_rule)
        rendered_surface = cockpit[cockpit.index("  PanelWindow {"):]
        self.assertNotRegex(
            rendered_surface, r"\broot\.status\b",
            "rendered cards must consume only the validity-gated snapshot")

        graph_summary = _qml_function(cockpit, "graphSnapshotText")
        self.assertIn("!root.currentStatus", graph_summary)
        self.assertIn("resident status unavailable", graph_summary)

    def test_cockpit_good_then_rejected_keeps_diagnostics_not_claims(self):
        cockpit = _read("Cockpit.qml")
        logic = "\n".join(_qml_function(cockpit, name) for name in (
            "isNonNegativeCount", "currentStatusSnapshot", "isPlainRecord",
            "validLedgerSummary", "projectionDebtKnownFor",
            "validStatusSnapshot", "applyStatus"))
        wrapper = """
var Model = {
  strictStatusJsonParse: strictStatusJsonParse,
  residentStatusShape: residentStatusShape,
  residentLedgerSummaryShape: residentLedgerSummaryShape,
  runtimeLifecycleEvidence: runtimeLifecycleEvidence,
  timestampStale: timestampStale
}
var readyProc = { cancel: function() {} }
var root = {
  status: null, statusLoadValid: false, statusBoundary: "", stale: false,
  runtimeEvidence: null, pluginVersion: "1.7.8",
  staleAfterSec: staleAfterDefaultSec(),
  clearVerification: function() {}, clearReadyCheck: function() {},
  isNonNegativeCount: isNonNegativeCount,
  currentStatusSnapshot: currentStatusSnapshot,
  isPlainRecord: isPlainRecord,
  validLedgerSummary: validLedgerSummary,
  projectionDebtKnownFor: projectionDebtKnownFor,
  validStatusSnapshot: validStatusSnapshot,
  applyStatus: applyStatus
}
function cockpitGoodThenRejected(goodText, rejectedText, nowIso) {
  Date.now = function() { return Date.parse(nowIso) }
  root.applyStatus(goodText)
  var admitted = root.currentStatusSnapshot()
  root.applyStatus(rejectedText)
  return {
    admittedState: admitted ? admitted.state : null,
    valid: root.statusLoadValid,
    current: root.currentStatusSnapshot(),
    retainedState: root.status ? root.status.state : null,
    boundary: root.statusBoundary
  }
}
""" + logic
        snapshot = self._snapshot(thought={
            "ts": "", "kind": "", "text": "",
            "origin": "legacy-unlabeled",
        })
        self.assertEqual(self._run(
            wrapper, "cockpitGoodThenRejected",
            [json.dumps(snapshot), "{malformed", snapshot["ts"]],
            sources=("Model.js",)), {
                "admittedState": "thinking",
                "valid": False,
                "current": None,
                "retainedState": "thinking",
                "boundary": "last good status; latest status rejected",
            })

    def test_panel_preserves_a_high_valid_events_today_counter(self):
        high = 9_007_199_254_740_991
        snapshot = self._snapshot(
            events_today=high,
            organs={"notify": {"today": high, "last_ts": ""}})
        self.assertTrue(self._model_call("residentStatusShape", snapshot))

        panel = _read("Panel.qml")
        self.assertNotIn("readonly property int eventsToday:", panel)
        value_start = panel.index(
            "readonly property real eventsTodayValue:")
        value_rule = panel[
            value_start:panel.index("\n  readonly", value_start + 1)]
        self.assertIn("compactEventsTodayValue()", value_rule)
        display_start = panel.index("readonly property string eventsToday:")
        display_rule = panel[
            display_start:panel.index("\n  readonly", display_start + 1)]
        self.assertIn("compactEventsTodayText()", display_rule)
        self.assertIn(
            "root.statusLoadValid",
            _qml_function(panel, "compactEventsTodayValue"))
        self.assertIn(
            "String(root.status.events_today)",
            _qml_function(panel, "compactEventsTodayText"))
        button = _qml_element(panel, "id: button")
        self.assertIn("root.eventsTodayValue > 0", button)
        self.assertIn('" " + root.eventsToday', button)

    def test_panel_rejected_status_withdraws_last_good_compact_claims(self):
        panel = _read("Panel.qml")
        logic = "\n".join(_qml_function(panel, name) for name in (
            "applyStatus", "compactBrainState", "compactEventsTodayValue",
            "compactEventsTodayText"))
        wrapper = """
var Model = {
  strictStatusJsonParse: strictStatusJsonParse,
  residentStatusShape: residentStatusShape,
  runtimeLifecycleEvidence: runtimeLifecycleEvidence,
  timestampStale: timestampStale
}
var root = {
  status: null, statusLoadValid: false, stale: false,
  runtimeEvidence: null, pluginVersion: "1.7.8",
  staleAfterSec: staleAfterDefaultSec(), releaseLifecycle: "ready",
  applyStatus: applyStatus,
  compactBrainState: compactBrainState,
  compactEventsTodayValue: compactEventsTodayValue,
  compactEventsTodayText: compactEventsTodayText
}
function panelGoodThenRejected(goodText, rejectedText, nowIso) {
  Date.now = function() { return Date.parse(nowIso) }
  root.applyStatus(goodText)
  var admitted = {
    valid: root.statusLoadValid,
    state: root.compactBrainState(),
    countValue: root.compactEventsTodayValue(),
    countText: root.compactEventsTodayText()
  }
  root.applyStatus(rejectedText)
  return {
    admitted: admitted,
    rejected: {
      valid: root.statusLoadValid,
      state: root.compactBrainState(),
      countValue: root.compactEventsTodayValue(),
      countText: root.compactEventsTodayText(),
      retainedState: root.status ? root.status.state : null,
      retainedCount: root.status ? root.status.events_today : null
    }
  }
}
""" + logic
        snapshot = self._snapshot(
            events_today=1,
            organs={"notify": {"today": 1, "last_ts": ""}})
        self.assertEqual(self._run(
            wrapper, "panelGoodThenRejected",
            [json.dumps(snapshot), "{malformed", snapshot["ts"]],
            sources=("Model.js",)), {
                "admitted": {
                    "valid": True, "state": "thinking",
                    "countValue": 1, "countText": "1",
                },
                "rejected": {
                    "valid": False, "state": "unknown",
                    "countValue": 0, "countText": "—",
                    "retainedState": "thinking", "retainedCount": 1,
                },
            })

        tooltip = _qml_function(panel, "tooltip")
        self.assertIn("!root.statusLoadValid", tooltip)
        self.assertIn("brainstem status unavailable", tooltip)
        self.assertIn('!root.statusLoadValid ? " STATUS?"',
                      _qml_element(panel, "id: button"))
        self.assertIn("!root.statusLoadValid || root.stale",
                      _qml_function(panel, "stateColor"))

    def test_history_total_remains_exact_beyond_javascript_integer_range(self):
        high = 9_007_199_254_740_991
        stamp = "2026-09-04T08:05:57Z"
        history = [[stamp, high], [stamp, 2]]
        self.assertTrue(self._model_call("residentHistoryShape", history))
        self.assertEqual(
            self._model_call("historyEventTotal", history, 90),
            "9007199254740993")
        self.assertEqual(self._model_call(
            "historyEventTotal", [[stamp, high], [stamp, high]], 90),
            "18014398509481982")
        self.assertEqual(
            self._model_call("historyEventTotal", history, 1), "2")
        self.assertEqual(self._model_call("historyEventTotal", [], 90), "0")

        for malformed in (
                None,
                [[stamp, -1]],
                [[stamp, 1.5]],
                [[stamp, "2"]],
                [["not-a-time", 2]],
                [[stamp, 2, 3]]):
            with self.subTest(malformed=malformed):
                self.assertIsNone(
                    self._model_call("historyEventTotal", malformed, 90))
        for bad_limit in (-1, 1.5, "90"):
            with self.subTest(bad_limit=bad_limit):
                self.assertIsNone(
                    self._model_call("historyEventTotal", history, bad_limit))

        cockpit = _read("Cockpit.qml")
        summary_at = cockpit.index('return "last " + Math.min(hist.length, 90)')
        summary_start = cockpit.rfind("text: {", 0, summary_at)
        summary = cockpit[summary_start:summary_at + 160]
        self.assertIn("Model.historyEventTotal(hist, 90)", summary)
        self.assertIn("total === null", summary)
        self.assertNotIn("tot +=", summary)

    # ------------------------------------------------------- finding 5

    def test_every_cockpit_snapshot_view_resolves_a_failed_load(self):
        # statusFile has always done this.  The other three did not, so a
        # file deleted or made unreadable after a good load left last-good
        # data on screen with an empty boundary string -- the display
        # reading as freshly confirmed at the moment its source vanished.
        cockpit = _read("Cockpit.qml")
        expected = {
            "id: statusFile": "resident status unavailable",
            "id: graphFile": "resident graph snapshot unavailable",
            "id: thoughtsFile": "resident generated-entry stream unavailable",
            "id: continuityFile": "resident continuity status unavailable",
        }
        for id_line, sentence in expected.items():
            block = _qml_element(cockpit, id_line)
            self.assertIn(
                "onLoadFailed:", block,
                id_line + " must resolve a failed load")
            self.assertIn(
                sentence, block,
                id_line + " must name an honest boundary")
            self.assertIn("last good", block, id_line)

    def test_snapshot_reload_timers_wait_for_fileview_callbacks(self):
        cockpit = _read("Cockpit.qml")
        for timer_id, file_name, apply_name in (
                ("id: graphApply", "graphFile.reload()", "applyGraph"),
                ("id: thoughtsApply", "thoughtsFile.reload()", "applyThoughts"),
                ("id: continuityApply", "continuityFile.reload()",
                 "applyContinuity")):
            timer = _qml_element(cockpit, timer_id)
            with self.subTest(surface="cockpit", timer=timer_id):
                self.assertIn(file_name, timer)
                self.assertNotIn(apply_name, timer)
                self.assertNotIn(".text()", timer)

        panel = _qml_element(_read("Panel.qml"), "id: continuityApply")
        self.assertIn("continuityFile.reload()", panel)
        self.assertNotIn("applyContinuity", panel)
        self.assertNotIn(".text()", panel)

    def test_watched_file_changes_survive_an_inflight_fileview_reader(self):
        # Quickshell 0.3 ignores reload() while a reader for the same path is
        # live.  The change bit therefore has to survive both outcomes and be
        # consumed only by a deferred reload after that callback returns.
        surfaces = {
            "Cockpit.qml": (
                "statusFile", "graphFile", "thoughtsFile",
                "continuityFile", "continuityReceiptFile",
                "installCompletionFile",
                "setupPresenceFile"),
            "Panel.qml": (
                "statusFile", "continuityFile", "continuityReceiptFile",
                "installCompletionFile"),
        }
        for surface, file_ids in surfaces.items():
            source = _read(surface)
            helper = _qml_function(source, "settleWatchedFileRefresh")
            self.assertIn("view.refreshPending !== true", helper, surface)
            self.assertIn("view.refreshPending = false", helper, surface)
            self.assertIn("Qt.callLater(", helper, surface)
            self.assertIn("view.reload()", helper, surface)
            self.assertIn("return true", helper, surface)
            for file_id in file_ids:
                with self.subTest(surface=surface, file=file_id):
                    block = _qml_element(source, "id: " + file_id)
                    self.assertIn(
                        "property bool refreshPending: false", block)
                    self.assertIn(
                        file_id + ".refreshPending = true", block)
                    self.assertGreaterEqual(
                        block.count(
                            "root.settleWatchedFileRefresh(" + file_id + ")"),
                        2,
                        "both load success and failure must drain the change")
                    self.assertEqual(
                        block.count(
                            "if (root.settleWatchedFileRefresh(" + file_id
                            + ")) return"),
                        2,
                        "a superseded read must not be applied before reread")

    def test_current_status_claims_withdraw_while_changed_files_settle(self):
        cockpit = _read("Cockpit.qml")
        panel = _read("Panel.qml")

        cockpit_status = _qml_element(cockpit, "id: statusFile")
        status_change = cockpit_status.split("onFileChanged:", 1)[1]
        self.assertIn("root.statusLoadValid = false", status_change)
        self.assertIn("root.statusResolved = false", status_change)
        self.assertIn("root.statusBoundary =", status_change)
        self.assertLess(status_change.index("root.statusLoadValid = false"),
                        status_change.index("statusFile.refreshPending = true"))

        cockpit_continuity = _qml_element(cockpit, "id: continuityFile")
        continuity_change = cockpit_continuity.split("onFileChanged:", 1)[1]
        self.assertIn("root.continuityBoundary =", continuity_change)
        self.assertIn("root.continuityActionOk = false", continuity_change)
        self.assertIn("waiting to validate", continuity_change)
        self.assertLess(continuity_change.index("root.continuityBoundary ="),
                        continuity_change.index(
                            "continuityFile.refreshPending = true"))

        panel_status = _qml_element(panel, "id: statusFile")
        panel_status_change = panel_status.split("onFileChanged:", 1)[1]
        self.assertIn("root.statusLoadValid = false", panel_status_change)
        self.assertIn("root.statusResolved = false", panel_status_change)
        self.assertLess(panel_status_change.index("root.statusLoadValid = false"),
                        panel_status_change.index(
                            "statusFile.refreshPending = true"))

        panel_continuity = _qml_element(panel, "id: continuityFile")
        panel_continuity_change = panel_continuity.split(
            "onFileChanged:", 1)[1]
        self.assertIn("root.continuityLoadValid = false",
                      panel_continuity_change)
        self.assertIn("root.continuityStale = true",
                      panel_continuity_change)
        self.assertLess(
            panel_continuity_change.index("root.continuityLoadValid = false"),
            panel_continuity_change.index(
                "continuityFile.refreshPending = true"))

        graph = _qml_element(cockpit, "id: graphFile")
        graph_change = graph.split("onFileChanged:", 1)[1]
        self.assertIn("root.graphBoundary =", graph_change)
        self.assertIn("root.graph = null", graph_change)
        self.assertLess(graph_change.index("root.graph = null"),
                        graph_change.index("graphFile.refreshPending = true"))

        thoughts = _qml_element(cockpit, "id: thoughtsFile")
        thoughts_change = thoughts.split("onFileChanged:", 1)[1]
        self.assertIn("root.thoughtsBoundary =", thoughts_change)
        self.assertIn("root.thoughts = []", thoughts_change)
        self.assertLess(thoughts_change.index("root.thoughts = []"),
                        thoughts_change.index(
                            "thoughtsFile.refreshPending = true"))

    def test_receipt_only_change_withdraws_authenticated_continuity(self):
        now = datetime.datetime.now(datetime.timezone.utc).replace(
            microsecond=0).isoformat().replace("+00:00", "Z")
        status = {
            "schema_version": 2,
            "state": "verified",
            "detail": "Verified recovery copy is available.",
            "repository_display": "External recovery repository",
            "latest": {
                "snapshot_id": "abc123",
                "created_at": now,
                "verified": True,
                "readiness": "ready",
                "profile": "signed portable capsule",
                "identity_matches": True,
            },
            "prepared": None,
            "operation": None,
            "updated_at": now,
        }

        cockpit_logic = self._cockpit_logic(
            "rejectContinuityStatus", "applyContinuity")
        cockpit_wrapper = """
var Model = {
  strictContinuityJsonParse: strictContinuityJsonParse,
  validContinuityStatus: validContinuityStatus,
  continuityStale: continuityStale,
  continuityStaleAfterSec: continuityStaleAfterSec
}
var continuity = null
var continuityReceiptAuthenticated = false
var continuityBoundary = ""
var continuityActionOk = false
var continuityActionMsg = ""
var restoreVerificationPending = false
var restoreCorrelationLost = false
var restoreRequestId = ""
var restoreExpectedPreparedId = ""
var restoreConfirmOpen = false
var continuitySheetOpen = false
var continuityPage = "overview"
var opened = false
var continuityScheduleRefresh = {restart: function() {}}
function preparedRestore() {
  return continuity && continuity.prepared ? continuity.prepared : null
}
function clearRestoreCeremony() {}
function focusContinuityPage() {}
function matchingRestoreOperation() { return null }
function cockpitReceiptLoss(raw) {
  applyContinuity(raw, true)
  var before = {
    authenticated: continuityReceiptAuthenticated,
    current: continuityBoundary === ""
      && continuityReceiptAuthenticated
  }
  continuityActionOk = true
  continuityActionMsg = "Restore verified."
  rejectContinuityStatus(
    "last good continuity status; verification receipt changed",
    "continuity verification receipt changed")
  return {
    before: before,
    after: {
      authenticated: continuityReceiptAuthenticated,
      current: continuityBoundary === ""
        && continuityReceiptAuthenticated,
      actionOk: continuityActionOk,
      boundary: continuityBoundary
    }
  }
}
""" + cockpit_logic
        cockpit_result = self._run(
            cockpit_wrapper, "cockpitReceiptLoss",
            [json.dumps(status)], sources=("Model.js",))
        self.assertEqual(cockpit_result["before"], {
            "authenticated": True, "current": True})
        self.assertEqual(cockpit_result["after"], {
            "authenticated": False,
            "current": False,
            "actionOk": False,
            "boundary": (
                "last good continuity status; verification receipt "
                "changed"),
        })

        panel = _read("Panel.qml")
        panel_wrapper = """
var Model = {
  strictContinuityJsonParse: strictContinuityJsonParse,
  validContinuityStatus: validContinuityStatus,
  continuityStale: continuityStale,
  continuityStaleAfterSec: continuityStaleAfterSec,
  continuityBarMark: continuityBarMark,
  continuityStateLabel: continuityStateLabel
}
var root = {
  continuity: null,
  continuityLoadValid: false,
  continuityReceiptAuthenticated: false,
  continuityStale: true,
  nowMs: 0,
  refreshContinuityStale: refreshContinuityStale
}
function panelReceiptLoss(raw, nowIso) {
  root.nowMs = Date.parse(nowIso)
  applyContinuity(raw, true)
  var before = {
    authenticated: root.continuityReceiptAuthenticated,
    loadValid: root.continuityLoadValid,
    mark: panelContinuityBarMark(),
    text: continuityText()
  }
  invalidateContinuityAuthority()
  return {
    before: before,
    after: {
      authenticated: root.continuityReceiptAuthenticated,
      loadValid: root.continuityLoadValid,
      mark: panelContinuityBarMark(),
      text: continuityText()
    }
  }
}
""" + "\n".join((
            _qml_function(panel, "refreshContinuityStale"),
            _qml_function(panel, "applyContinuity"),
            _qml_function(panel, "invalidateContinuityAuthority"),
            _qml_function(panel, "continuityBarMark").replace(
                "function continuityBarMark(",
                "function panelContinuityBarMark("),
            _qml_function(panel, "continuityText"),
        ))
        panel_result = self._run(
            panel_wrapper, "panelReceiptLoss",
            [json.dumps(status), now], sources=("Model.js",))
        self.assertEqual(panel_result["before"], {
            "authenticated": True,
            "loadValid": True,
            "mark": "",
            "text": "recovery ready — Verified recovery copy is available.",
        })
        self.assertEqual(panel_result["after"], {
            "authenticated": False,
            "loadValid": False,
            "mark": "?",
            "text": "continuity status unavailable",
        })

        for surface in ("Cockpit.qml", "Panel.qml"):
            source = _read(surface)
            receipt = _qml_element(source, "id: continuityReceiptFile")
            self.assertIn("path: root.continuityReceiptPath", receipt)
            self.assertIn("onFileChanged:", receipt)
            self.assertIn("continuityStatusProc.invalidate()", receipt)
            self.assertNotIn("text()", receipt)
            self.assertIn(
                "readonly property int continuityAuthorityPollInterval: "
                "60000", source)
            poll_at = source.index(
                "interval: root.continuityAuthorityPollInterval")
            poll = source[poll_at:_scan_block(
                source, source.rindex("{", 0, poll_at)) + 1]
            self.assertLess(
                poll.index("continuityReceiptAuthenticated = false")
                if surface == "Cockpit.qml"
                else poll.index("invalidateContinuityAuthority()"),
                poll.index("continuityStatusProc.refresh()"))

    # ------------------------------------------------------- finding 3

    def test_installing_horizon_is_bounded_and_reports_only_silence(self):
        bound = self._model_call("installingUnobservedAfterSec")
        self.assertIsInstance(bound, int)
        self.assertGreater(bound, 0)
        # Far away from the resident pulse clock: that one times a
        # pulse cycle, this one times an install.
        self.assertGreater(bound, self._model_call("staleAfterMaxSec"))

        started = 1_000_000_000_000
        self.assertFalse(self._model_call(
            "installingProgressUnobserved", started, started))
        self.assertFalse(self._model_call(
            "installingProgressUnobserved", started,
            started + (bound - 1) * 1000))
        self.assertTrue(self._model_call(
            "installingProgressUnobserved", started,
            started + bound * 1000))

        # An unreadable clock may only stay quiet.  This predicate exists to
        # add a caveat, never to accuse a running installer.
        for observed in (0, -1, None, "soon"):
            self.assertFalse(
                self._model_call(
                    "installingProgressUnobserved", observed,
                    started + bound * 1000),
                "an unreadable start must not report silence")
        self.assertFalse(self._model_call(
            "installingProgressUnobserved", started, started - 1))

    def test_installing_horizon_can_never_reach_the_lifecycle(self):
        # Fail-closed: a timeout changes wording and nothing else.  It must
        # not be able to move the gate to ready or invent readiness.
        cockpit = _read("Cockpit.qml")
        self._contains(
            cockpit, "readonly property bool installerProgressUnobserved:",
            "Cockpit.qml")
        self._contains(
            cockpit, "Model.installingProgressUnobserved(", "Cockpit.qml")

        readers = {
            "setupEyebrow", "setupTitle", "setupDescription",
            "setupActionLabel",
        }
        for name in readers:
            self._contains(
                _qml_function(cockpit, name),
                "root.installerProgressUnobserved",
                name + " must carry the honest installing wording")

        declaration = cockpit.index(
            "readonly property bool installerProgressUnobserved:")
        end_of_declaration = cockpit.index("\n  readonly", declaration + 1)
        rest = cockpit[:declaration] + cockpit[end_of_declaration:]
        for name in readers:
            rest = rest.replace(_qml_function(cockpit, name), "")
        self._lacks(
            rest, "installerProgressUnobserved",
            "the installing horizon may only reach the gate wording")

        for declaration in (
                "readonly property string releaseLifecycle:",
                "readonly property bool setupRequired:",
                "readonly property bool setupActionAllowed:"):
            start = cockpit.index(declaration)
            self._lacks(
                cockpit[start:cockpit.index("\n  readonly", start + 1)],
                "installerProgressUnobserved",
                declaration + " must not depend on a timeout")

    def test_panel_carries_the_dead_installer_horizon(self):
        panel = _read("Panel.qml")
        for token in (
                "property string installingRecordKey:",
                "property real installingObservedAtMs:",
                "readonly property bool installerProgressUnobserved:",
                "Model.installingProgressUnobserved(",
                "first light has not reported progress",
                '" INSTALL?"'):
            self.assertIn(token, panel)
        self.assertIn(
            "root.noteInstallingObservation(publicationChanged)",
            _qml_function(panel, "applyInstallCompletion"))
        self.assertIn(
            "Date.now()",
            _qml_function(panel, "noteInstallingObservation"))
        lifecycle_start = panel.index(
            "readonly property string releaseLifecycle:")
        lifecycle_end = panel.index("\n  readonly", lifecycle_start + 1)
        self.assertNotIn(
            "installerProgressUnobserved",
            panel[lifecycle_start:lifecycle_end])

    def test_installing_horizon_survives_a_cockpit_summon(self):
        # The installer usually dies while the cockpit is closed, so the
        # observation clock must not be reset by open() or close().
        cockpit = _read("Cockpit.qml")
        note = _qml_function(cockpit, "noteInstallingObservation")
        self.assertIn("installingRecordKey", note)
        self.assertIn("Date.now()", note)
        # A new record is a new installer and is owed the full bound again.
        self.assertIn("key !== root.installingRecordKey", note)

        for name in ("open", "close"):
            body = _qml_function(cockpit, name)
            self.assertNotIn("installingObservedAtMs", body, name)
            self.assertNotIn("installingRecordKey", body, name)

        self._contains(
            _qml_function(cockpit, "applyInstallCompletion"),
            "root.noteInstallingObservation(", "applyInstallCompletion")
        lifecycle = cockpit.index("onReleaseLifecycleChanged:")
        handler = cockpit[lifecycle:_scan_block(
            cockpit, cockpit.index("{", lifecycle)) + 1]
        self.assertLess(
            handler.index("root.noteInstallingObservation()"),
            handler.index("if (!root.cockpitVisible) return"),
            "the horizon must keep running while the cockpit is closed")

    def test_same_release_republication_restarts_only_from_file_change(self):
        cockpit = _read("Cockpit.qml")
        self.assertIn(
            "property bool installCompletionPublicationChanged: false",
            cockpit)
        note = _qml_function(cockpit, "noteInstallingObservation")
        self.assertIn("publicationChanged", note)
        self.assertIn("|| publicationChanged", note)
        apply_body = _qml_function(cockpit, "applyInstallCompletion")
        self.assertIn("publicationChanged", apply_body)
        completion_view = _qml_element(cockpit, "id: installCompletionFile")
        self.assertIn(
            "root.installCompletionPublicationChanged = true",
            completion_view)
        self.assertIn(
            "root.installCompletionPublicationChanged = false",
            completion_view)
        for name in ("open", "close"):
            self.assertNotIn(
                "installCompletionPublicationChanged",
                _qml_function(cockpit, name), name)

    # ------------------------------------------------------- finding 8

    def test_continuity_has_a_clock_that_only_withdraws_claims(self):
        horizon = self._model_call("continuityStaleAfterSec")
        self.assertIsInstance(horizon, int)
        self.assertGreater(horizon, 0)

        published = datetime.datetime(
            2026, 9, 4, 8, 0, 8, tzinfo=datetime.timezone.utc)
        fresh = {"updated_at": "2026-09-04T08:00:08Z"}
        # Derive the epoch projection here rather than writing a literal:
        # a hand-computed constant would silently move the assertion.
        stamped = int(published.timestamp() * 1000)
        now = stamped + horizon * 1000 * 10

        self.assertFalse(self._model_call(
            "continuityStale", fresh, stamped + 60_000, horizon))
        self.assertFalse(self._model_call(
            "continuityStale", fresh, stamped + horizon * 1000, horizon))
        self.assertTrue(self._model_call(
            "continuityStale", fresh, stamped + horizon * 1000 + 1, horizon))

        # Unknown falls towards "not reporting": the opposite default from
        # the installing horizon, because this predicate exists to stop a
        # reassuring mark from outliving its subsystem.
        for status in (None, {}, {"updated_at": ""},
                       {"updated_at": "not a date"}, []):
            self.assertTrue(
                self._model_call("continuityStale", status, now, horizon),
                "an unreadable continuity clock must read as stale")
        self.assertTrue(
            self._model_call("continuityStale", fresh, "later", horizon))

    def test_null_continuity_is_unavailable_never_a_stale_publication(self):
        logic = self._cockpit_logic(
            "continuityStateText", "continuityRepositoryText",
            "continuityLatestText", "continuityDetailText")
        wrapper = """
var Model = {
  continuityStateLabel: function(state) { return state },
  continuityLatestReady: function() { return false },
  timeAgo: function() { return "age" }
}
var continuity = null, currentContinuity = null
var continuityBoundary = "", continuityStale = true
var restoreCorrelationLost = false, restoreVerificationPending = false
var continuityReceiptAuthenticated = false
function continuityWords(raw, current, stale) {
  continuity = raw
  currentContinuity = current
  continuityStale = stale
  return [continuityStateText(), continuityRepositoryText(),
          continuityLatestText(), continuityDetailText()]
}
""" + logic
        initial = self._run(
            wrapper, "continuityWords", [None, None, True])
        self.assertEqual(initial, [
            "STATUS UNAVAILABLE",
            "No continuity status has been published.",
            "No recovery copy has been recorded.",
            "The continuity worker is not reporting.",
        ])
        self.assertFalse(any("stale" in value.lower() for value in initial))

        stale = {"state": "verified", "latest": None}
        self.assertEqual(self._run(
            wrapper, "continuityWords", [stale, None, True]), [
                "STATUS STALE",
                "The last continuity publication is stale.",
                "The last recovery-copy publication is stale.",
                "Last good continuity status is stale; no recovery state is current.",
            ])

    def test_bar_withdraws_the_continuity_mark_when_it_goes_quiet(self):
        panel = _read("Panel.qml")
        self.assertIn("property bool continuityStale: true", panel)
        self.assertIn("property bool continuityLoadValid: false", panel)

        block = _qml_element(panel, "id: continuityFile")
        self.assertIn(
            "onLoadFailed:", block,
            "a deleted continuity status must not stay reassuring")
        self.assertIn("root.continuity = null", block)
        self.assertIn("root.continuityStale = true", block)

        refresh = _qml_function(panel, "refreshContinuityStale")
        self.assertIn("Model.continuityStale(", refresh)
        self.assertIn("Model.continuityStaleAfterSec()", refresh)

        # Told, and asked: the horizon is crossed with no file changing.
        self.assertIn(
            "root.refreshContinuityStale()",
            _qml_function(panel, "applyContinuity"))
        tick = panel.index("interval: 5000; running: true; repeat: true")
        handler = panel[tick:_scan_block(
            panel, panel.index("{", tick)) + 1]
        self.assertIn("root.refreshContinuityStale()", handler)

        mark = _qml_function(panel, "continuityBarMark")
        self.assertIn('if (root.continuityStale) return "?"', mark)
        self.assertIn("root.continuityBarMark()", panel)
        self.assertIn(
            "continuity not reporting",
            _qml_function(panel, "continuityText"))
        self.assertIn(
            "!root.continuityStale",
            _qml_function(panel, "indicatorColor"))

    def test_bar_withdraws_fresh_continuity_after_rejected_publication(self):
        panel = _read("Panel.qml")
        refresh = _qml_function(panel, "refreshContinuityStale")
        apply = _qml_function(panel, "applyContinuity")
        wrapper = """
var Model = {
  strictContinuityJsonParse: strictContinuityJsonParse,
  validContinuityStatus: validContinuityStatus,
  continuityStale: continuityStale,
  continuityStaleAfterSec: continuityStaleAfterSec
}
var root = {
  continuity: null,
  continuityStale: true,
  continuityLoadValid: false,
  nowMs: 0,
  refreshContinuityStale: refreshContinuityStale
}
function continuityTransition(goodText, rejectedText, nowIso) {
  root.nowMs = Date.parse(nowIso)
  applyContinuity(goodText, true)
  var admitted = !root.continuityStale && root.continuityLoadValid
  applyContinuity(rejectedText, true)
  refreshContinuityStale()
  return {
    admitted: admitted,
    stale: root.continuityStale,
    loadValid: root.continuityLoadValid,
    retainedState: root.continuity ? root.continuity.state : null
  }
}
""" + refresh + "\n" + apply
        latest = {
            "snapshot_id": "abc123",
            "created_at": "2026-09-04T08:00:00Z",
            "verified": True, "readiness": "ready",
            "profile": "signed portable capsule",
            "identity_matches": True,
        }
        status = {
            "schema_version": 2, "state": "verified",
            "detail": "Verified recovery copy is available.",
            "repository_display": "External recovery repository",
            "latest": latest,
            "prepared": None, "operation": None,
            "updated_at": "2026-09-04T08:05:57Z",
        }
        for rejected in ('{"schema_version":2}', "{malformed"):
            result = self._run(
                wrapper, "continuityTransition",
                [json.dumps(status), rejected, status["updated_at"]],
                sources=("Model.js",))
            with self.subTest(rejected=rejected):
                self.assertEqual(result, {
                    "admitted": True, "stale": True,
                    "loadValid": False, "retainedState": "verified",
                })

    def test_cockpit_withdraws_every_recovery_fact_after_rejection(self):
        cockpit = _read("Cockpit.qml")
        logic = self._cockpit_logic(
            "rejectContinuityStatus", "applyContinuity",
            "continuityStateText",
            "continuityRepositoryText", "continuityLatestText",
            "continuityDetailText")
        prelude = """
var Model = {
  strictContinuityJsonParse: strictContinuityJsonParse,
  validContinuityStatus: validContinuityStatus,
  continuityLatestReady: continuityLatestReady,
  continuityStateLabel: continuityStateLabel,
  continuityBarMark: continuityBarMark,
  timeAgo: function() { return "just now" }
}
var continuity = null
var continuityBoundary = ""
var continuityStale = false
var currentContinuity = null
var continuityState = "unknown"
var continuityActionOk = false
var continuityActionMsg = ""
var restoreCorrelationLost = false
var restoreVerificationPending = false
var restoreRequestId = ""
var restoreExpectedPreparedId = ""
function rejectedContinuityFacts(good, rejected) {
  continuity = good
  currentContinuity = good
  continuityState = good.state
  applyContinuity(rejected, true)
  currentContinuity = !continuityStale && continuityBoundary === ""
    ? continuity : null
  continuityState = currentContinuity ? currentContinuity.state : "unknown"
  return {
    state: continuityStateText(),
    repository: continuityRepositoryText(),
    copy: continuityLatestText(),
    detail: continuityDetailText(),
    mark: Model.continuityBarMark(currentContinuity)
  }
}
""" + logic
        status = {
            "schema_version": 2,
            "state": "verified",
            "detail": "Verified recovery copy is available.",
            "repository_display": "External recovery repository",
            "latest": {
                "snapshot_id": "abc123",
                "created_at": "2026-09-04T08:00:00Z",
                "verified": True,
                "readiness": "ready",
                "profile": "signed portable capsule",
                "identity_matches": True,
            },
            "prepared": None,
            "operation": None,
            "updated_at": "2026-09-04T08:05:57Z",
        }
        result = self._run(
            prelude, "rejectedContinuityFacts",
            [status, {"schema_version": 2}], sources=("Model.js",))
        self.assertEqual(result, {
            "state": "STATUS UNAVAILABLE",
            "repository": (
                "Repository status unavailable; last good value withheld."),
            "copy": (
                "Recovery-copy status unavailable; last good value "
                "withheld."),
            "detail": (
                "last good continuity status; latest update rejected"),
            "mark": "?",
        })
        self.assertNotIn("Recovery-ready", " ".join(result.values()))
        self.assertNotIn(
            "External recovery repository", " ".join(result.values()))
        self.assertIn("Model.continuityBarMark(", cockpit)
        self.assertIn("root.continuityReceiptAuthenticated", cockpit)
        for button_id in (
                "overviewBackupButton", "overviewCheckButton",
                "overviewRestoreButton", "cardBackupButton",
                "cardRestoreButton"):
            button = _qml_element(cockpit, "id: " + button_id)
            self.assertIn("visible: !!root.currentContinuity", button)

    def test_cockpit_rejection_withdraws_terminal_action_success(self):
        logic = self._cockpit_logic(
            "rejectContinuityStatus", "applyContinuity")
        prelude = """
var Model = {
  strictContinuityJsonParse: strictContinuityJsonParse,
  validContinuityStatus: validContinuityStatus
}
var continuity = {state: "verified"}
var continuityBoundary = ""
var continuityActionOk = true
var continuityActionMsg = "Restore verified: SIA is ready and its signed ledger passes."
var restoreVerificationPending = false
var restoreCorrelationLost = false
var restoreRequestId = "a".repeat(32)
var restoreExpectedPreparedId = "b".repeat(32)
function rejectedTerminalAction(raw) {
  applyContinuity(raw, true)
  return {
    ok: continuityActionOk,
    message: continuityActionMsg,
    pending: restoreVerificationPending,
    correlationLost: restoreCorrelationLost,
    accent: continuityActionOk ? "accent" : "urgent",
    boundary: continuityBoundary
  }
}
""" + logic
        for rejected in ('{"schema_version":2}', "{malformed"):
            result = self._run(
                prelude, "rejectedTerminalAction", [rejected],
                sources=("Model.js",))
            with self.subTest(rejected=rejected):
                self.assertFalse(result["ok"])
                self.assertFalse(result["pending"])
                self.assertTrue(result["correlationLost"])
                self.assertEqual(result["accent"], "urgent")
                self.assertNotIn("Restore verified", result["message"])
                self.assertNotEqual(result["boundary"], "")

        cockpit = _read("Cockpit.qml")
        continuity_file = _qml_element(cockpit, "id: continuityFile")
        self.assertIn("root.rejectContinuityStatus(", continuity_file)

    def test_continuity_horizon_withdraws_terminal_action_success(self):
        logic = self._cockpit_logic("refreshContinuityActionFreshness")
        prelude = """
var Model = {
  continuityStale: continuityStale,
  continuityStaleAfterSec: continuityStaleAfterSec
}
var continuity = {updated_at: "2026-09-04T08:05:57Z"}
var nowMs = Date.parse("2030-09-04T08:05:57Z")
var continuityActionOk = true
var continuityActionMsg = "Restore verified: SIA is ready and its signed ledger passes."
var restoreVerificationPending = false
var restoreCorrelationLost = false
var restoreRequestId = "a".repeat(32)
var restoreExpectedPreparedId = "b".repeat(32)
function staleTerminalAction() {
  refreshContinuityActionFreshness()
  return {
    ok: continuityActionOk,
    message: continuityActionMsg,
    pending: restoreVerificationPending,
    correlationLost: restoreCorrelationLost,
    accent: continuityActionOk ? "accent" : "urgent"
  }
}
""" + logic
        result = self._run(
            prelude, "staleTerminalAction", [], sources=("Model.js",))
        self.assertEqual(result, {
            "ok": False,
            "message": (
                "Continuity status is stale; prior action results are not "
                "current."),
            "pending": False,
            "correlationLost": True,
            "accent": "urgent",
        })

        cockpit = _read("Cockpit.qml")
        clock = cockpit[cockpit.index(
            "interval: 1000; running: root.opened; repeat: true"):]
        self.assertIn("root.refreshContinuityActionFreshness()", clock)

    def test_restore_correlation_retires_terminally_and_resets_on_fresh_prepare(self):
        logic = self._cockpit_logic(
            "rejectContinuityStatus", "applyContinuity")
        prelude = """
var Model = {
  strictContinuityJsonParse: strictContinuityJsonParse,
  validContinuityStatus: validContinuityStatus,
  continuityStale: continuityStale,
  continuityStaleAfterSec: continuityStaleAfterSec
}
var continuity = null
var continuityBoundary = ""
var continuityActionOk = false
var continuityActionMsg = ""
var restoreVerificationPending = true
var restoreCorrelationLost = false
var restoreRequestId = "a".repeat(32)
var restoreExpectedPreparedId = "b".repeat(32)
var restoreConfirmOpen = false
var continuitySheetOpen = false
var continuityPage = "overview"
var opened = false
var continuityScheduleRefresh = {restart: function() {}}
function preparedRestore() {
  return continuity && continuity.prepared ? continuity.prepared : null
}
function clearRestoreCeremony() {}
function focusContinuityPage() {}
function matchingRestoreOperation(value) {
  var operation = value && value.operation
  return operation
    && operation.request_id === restoreRequestId
    && operation.prepared_id === restoreExpectedPreparedId
    ? operation : null
}
function correlationLifecycle(runningText, terminalText, rejectedText,
                              freshPreparedText) {
  applyContinuity(runningText, true)
  applyContinuity(terminalText, true)
  var terminal = {
    pending: restoreVerificationPending,
    lost: restoreCorrelationLost,
    requestId: restoreRequestId,
    preparedId: restoreExpectedPreparedId,
    ok: continuityActionOk
  }
  applyContinuity(rejectedText, true)
  var rejected = {
    pending: restoreVerificationPending,
    lost: restoreCorrelationLost,
    requestId: restoreRequestId,
    preparedId: restoreExpectedPreparedId,
    ok: continuityActionOk
  }

  restoreVerificationPending = true
  restoreCorrelationLost = false
  restoreRequestId = "a".repeat(32)
  restoreExpectedPreparedId = "b".repeat(32)
  applyContinuity(runningText, true)
  applyContinuity(rejectedText, true)
  applyContinuity(freshPreparedText, true)
  var fresh = {
    pending: restoreVerificationPending,
    lost: restoreCorrelationLost,
    requestId: restoreRequestId,
    preparedId: restoreExpectedPreparedId
  }
  return {terminal: terminal, rejected: rejected, fresh: fresh}
}
""" + logic
        now = datetime.datetime.now(datetime.timezone.utc).replace(
            microsecond=0).isoformat().replace("+00:00", "Z")
        latest = {
            "snapshot_id": "abc123", "created_at": now,
            "verified": True, "readiness": "ready",
            "profile": "signed portable capsule",
            "identity_matches": True,
        }
        operation = {
            "request_id": "a" * 32,
            "kind": "restore-apply",
            "prepared_id": "b" * 32,
            "phase": "running",
            "ready": True,
            "sia_ledger_verified": True,
        }
        running = {
            "schema_version": 2, "state": "restoring",
            "detail": "Restore is running.",
            "repository_display": "External recovery repository",
            "latest": latest, "prepared": None,
            "operation": operation, "updated_at": now,
        }
        terminal = {
            **running, "state": "verified",
            "detail": "Restore verified.",
            "operation": {**operation, "phase": "verified"},
        }
        prepared_id = "d" * 32
        fresh = {
            **running, "state": "prepared",
            "detail": "Restore capsule verified off-path.",
            "prepared": {
                "prepared_id": prepared_id,
                "snapshot_id": "abc123", "created_at": now,
                "readiness": "ready",
                "profile": "signed portable capsule",
                "ledger_head": "f" * 64,
                "identity_matches": True,
            },
            "operation": {
                "request_id": "c" * 32,
                "kind": "restore-prepare",
                "prepared_id": prepared_id,
                "phase": "verified", "ready": False,
                "sia_ledger_verified": False,
            },
        }
        result = self._run(
            prelude, "correlationLifecycle",
            [json.dumps(running), json.dumps(terminal), "{malformed",
             json.dumps(fresh)], sources=("Model.js",))
        self.assertEqual(result["terminal"], {
            "pending": False, "lost": False,
            "requestId": "", "preparedId": "", "ok": True,
        })
        self.assertEqual(result["rejected"], {
            "pending": False, "lost": False,
            "requestId": "", "preparedId": "", "ok": False,
        })
        self.assertEqual(result["fresh"], {
            "pending": False, "lost": False,
            "requestId": "", "preparedId": "",
        })

    def test_restore_acceptance_is_exact_canonical_and_lexically_integer(self):
        logic = self._cockpit_logic("validRestoreAcceptance")
        prelude = """
var root = {
  isPlainRecord: function(value) {
    return !!value && typeof value === "object" && !Array.isArray(value)
  }
}
var Model = {
  strictContinuityAcceptanceJsonParse: strictContinuityAcceptanceJsonParse,
  validContinuityCorrelationId: validContinuityCorrelationId,
  recordHasExactly: recordHasExactly
}
function acceptanceAdmitted(raw, expectedPreparedId) {
  var parsed
  try {
    parsed = Model.strictContinuityAcceptanceJsonParse(raw)
  } catch (_) {
    return false
  }
  return validRestoreAcceptance(parsed, expectedPreparedId)
}
""" + logic
        prepared_id = "b" * 32
        valid = {
            "schema_version": 1,
            "accepted": True,
            "request_id": "a" * 32,
            "operation": "restore-apply",
            "prepared_id": prepared_id,
        }
        self.assertTrue(self._run(
            prelude, "acceptanceAdmitted",
            [json.dumps(valid), prepared_id], sources=("Model.js",)))
        invalid_documents = (
            {**valid, "unexpected": "field"},
            {**valid, "request_id": "NOT-HEX"},
            {**valid, "prepared_id": "c" * 32},
        )
        for document in invalid_documents:
            with self.subTest(document=document):
                self.assertFalse(self._run(
                    prelude, "acceptanceAdmitted",
                    [json.dumps(document), prepared_id],
                    sources=("Model.js",)))
        lexical_float = json.dumps(valid).replace(
            '"schema_version": 1', '"schema_version": 1.0')
        self.assertFalse(self._run(
            prelude, "acceptanceAdmitted", [lexical_float, prepared_id],
            sources=("Model.js",)))

        self.assertIn(
            "Model.strictContinuityAcceptanceJsonParse(",
            _read("Cockpit.qml"))

    def test_bar_declares_no_unread_second_lifecycle(self):
        # runtimeLifecycle was computed here and never read.  A laxer
        # lifecycle sitting unread beside the one the widget acts on is an
        # invitation to bind the wrong one.
        panel = _read("Panel.qml")
        self.assertNotIn(
            "readonly property string runtimeLifecycle:", panel)
        self.assertNotIn("Model.runtimeLifecycle(", panel)
        self.assertIn("readonly property string releaseLifecycle:", panel)


if __name__ == "__main__":
    unittest.main()
