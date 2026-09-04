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

import datetime
import json
from pathlib import Path
import shutil
import subprocess
import unittest


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
            "pulse_seq": 7780,
            "pages": 1894,
            "graph_edges": 465,
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
        snapshot.update(overrides)
        return snapshot

    def _valid_snapshot(self, snapshot):
        prelude = self._cockpit_logic(
            "isNonNegativeCount", "isPlainRecord", "validMindSummary",
            "validAgentRelay", "validLedgerSummary",
            "projectionDebtKnownFor", "validStatusSnapshot")
        return self._run(prelude, "validStatusSnapshot", [snapshot])

    def test_status_validator_requires_every_field_the_vitals_render(self):
        # The vitals row prints status.pages and status.graph_edges, the
        # header prints status.pulse_seq, and the chain row prints
        # status.ledger.seq and .head -- all unguarded.  A snapshot that
        # passed validation without them rendered "memories: undefined"
        # under a boundary that claimed the status was good.
        self.assertTrue(self._valid_snapshot(self._snapshot()))

        for field in ("pages", "graph_edges", "pulse_seq", "ledger"):
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

    def test_tightening_the_shape_did_not_strand_legacy_upgrades(self):
        # statusLoadValid gates what guidedLifecycle is even shown, so
        # tightening validStatusSnapshot tightens lifecycle routing too: a
        # rejected snapshot is routed as if there were no resident brain at
        # all.  The pre-release publisher already wrote pulse_seq, pages,
        # graph_edges and ledger, so a real legacy status still validates
        # and still routes to `update`.  If a future field is added to this
        # validator without checking that, an upgradable brain silently
        # becomes a repair condition.
        legacy = self._snapshot()
        del legacy["version"]
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

    def test_status_validator_keeps_an_empty_ledger_head_publishable(self):
        # sialib publishes seq 0 with an empty head when it cannot read the
        # chain.  That is a real answer the cockpit must show, so tightening
        # the shape must not reject it.
        self.assertTrue(self._valid_snapshot(
            self._snapshot(ledger={"seq": 0, "head": ""})))

    # ------------------------------------------------------- finding 6

    def _valid_stream(self, stream):
        prelude = self._cockpit_logic(
            "isPlainRecord", "validThought", "validThoughtStream")
        return self._run(prelude, "validThoughtStream", [stream])

    def _thought(self, **overrides):
        thought = {
            "ts": "2026-09-04T07:34:01Z",
            "kind": "anomaly",
            "text": "Unusual activity in tag association.",
            "links": ["sia/cortex"],
            "urgent": False,
            "origin": "derived",
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

        for field in ("ts", "kind", "text"):
            broken = self._thought()
            del broken[field]
            self.assertFalse(
                self._valid_stream({"v": 1, "thoughts": [broken]}),
                "a thought without " + field + " must not validate")

        self.assertFalse(self._valid_stream(
            {"v": 1, "thoughts": [self._thought(kind="")]}))
        self.assertFalse(self._valid_stream(
            {"v": 1, "thoughts": [self._thought(origin=7)]}))
        self.assertFalse(self._valid_stream({"v": 1, "thoughts": "no"}))
        self.assertFalse(self._valid_stream({"thoughts": []}))
        self.assertFalse(self._valid_stream(None))

    def test_unlabeled_legacy_thoughts_stay_renderable(self):
        # sialib.load_thoughts deliberately leaves genuinely unlabeled
        # legacy rows unlabeled rather than laundering them into a
        # classification.  Requiring origin here would reject exactly the
        # rows the legacy-unlabeled boundary exists to expose.
        legacy = self._thought()
        del legacy["origin"]
        self.assertTrue(self._valid_stream({"v": 1, "thoughts": [legacy]}))

    def test_thought_stream_failure_sets_a_boundary_and_keeps_last_good(self):
        cockpit = _read("Cockpit.qml")
        apply_body = _qml_function(cockpit, "applyThoughts")
        self.assertIn("validThoughtStream", apply_body)
        self.assertIn("thoughtsRejected()", apply_body)
        # The silent catch(e){} was the whole defect: a truncated read froze
        # the stream with no mark on screen at all.
        self.assertNotRegex(apply_body, r"catch\s*\(e\)\s*\{\s*\}")

        rejected = _qml_function(cockpit, "thoughtsRejected")
        self.assertIn("root.thoughts.length", rejected)
        self.assertIn("last good thought stream", rejected)
        self.assertIn("no valid thought stream", rejected)

        for needle in ('property string thoughtsBoundary: ""',
                       'visible: root.thoughtsBoundary !== ""',
                       "text: root.thoughtsBoundary"):
            self._contains(cockpit, needle, "Cockpit.qml")

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
            "id: thoughtsFile": "resident thought stream unavailable",
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

    # ------------------------------------------------------- finding 3

    def test_installing_horizon_is_bounded_and_reports_only_silence(self):
        bound = self._model_call("installingUnobservedAfterSec")
        self.assertIsInstance(bound, int)
        self.assertGreater(bound, 0)
        # Far away from the brainstem pulse clock: that one times a
        # heartbeat, this one times an install.
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
            "root.noteInstallingObservation()", "applyInstallCompletion")
        lifecycle = cockpit.index("onReleaseLifecycleChanged:")
        handler = cockpit[lifecycle:_scan_block(
            cockpit, cockpit.index("{", lifecycle)) + 1]
        self.assertLess(
            handler.index("root.noteInstallingObservation()"),
            handler.index("if (!root.cockpitVisible) return"),
            "the horizon must keep running while the cockpit is closed")

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

    def test_bar_withdraws_the_continuity_mark_when_it_goes_quiet(self):
        panel = _read("Panel.qml")
        self.assertIn("property bool continuityStale: true", panel)

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
