#!/usr/bin/env python3
"""Truth boundaries that must survive after a snapshot has validated."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

from tests.test_cockpit_boundary_horizon import (
    _JsRunner,
    _scan_block,
    _qml_element,
    _qml_function,
    _read,
)


REPO = Path(__file__).resolve().parent.parent


class CockpitIntegrityBoundaries(unittest.TestCase):
    def setUp(self):
        self.node = shutil.which("node")
        if self.node is None:
            self.skipTest("Node is unavailable for executable QML logic")

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
        return "\n".join(
            _qml_function(cockpit, name) for name in names
        ).replace("root.", "")

    def _valid_graph(self, graph, now="2026-09-04T08:05:57Z"):
        logic = """var Model = {
  timestampObservedBy: timestampObservedBy,
  recordHasExactly: recordHasExactly,
  strictStringLength: strictStringLength,
  inertStatusString: inertStatusString,
  canonicalCorpusSlug: canonicalCorpusSlug
}
"""
        logic += self._cockpit_logic(
            "isNonNegativeCount", "isPlainRecord", "validOriginLabel",
            "validGraphString", "validGraphSlug", "validGraphSnapshot")
        logic += """
function validGraphAt(graph, nowIso) {
  return validGraphSnapshot(graph, Date.parse(nowIso))
}
"""
        return self._run(
            logic, "validGraphAt", [graph, now], sources=("Model.js",))

    @staticmethod
    def _graph():
        return {
            "v": 2,
            "ts": "2026-09-04T08:05:57Z",
            "publication_id": "a780a1590f1e41d19e68c31c0ee93c88",
            "pages_total": 1,
            "pages_total_complete": True,
            "nodes": [{
                "id": "sia/cortex", "t": "cortex", "title": "SIA",
                "ts": "2026-09-04T08:05:57Z", "origin": "derived",
                "deg": 0, "din": 0, "dout": 0,
            }],
            "edges": [],
            "snapshot": {
                "complete": True, "truncated": 0, "omitted_nodes": 0,
                "omitted_edges": 0, "omissions_imply_absence": False,
                "aged_out": 0, "counts_by_kind": {"cortex": 1},
                "failed_ops": [], "window_days": 14,
            },
        }

    def test_graph_shape_is_deep_and_identity_bearing(self):
        graph = self._graph()
        self.assertTrue(self._valid_graph(graph))

        mutations = []
        bad = self._graph(); bad["nodes"] = [None]; mutations.append(bad)
        bad = self._graph(); bad["nodes"][0]["id"] = ""; mutations.append(bad)
        bad = self._graph(); bad["nodes"][0]["deg"] = -1; mutations.append(bad)
        bad = self._graph(); bad["nodes"][0]["deg"] = 99; mutations.append(bad)
        bad = self._graph(); bad["edges"] = [{
            "s": "missing", "d": "sia/cortex", "t": "mentions",
            "why": "fixture"}]; mutations.append(bad)
        bad = self._graph(); bad["snapshot"]["failed_ops"] = [7]; mutations.append(bad)
        bad = self._graph(); bad["snapshot"]["failed_ops"] = ["list_pages"];
        mutations.append(bad)
        bad = self._graph(); bad["pages_total_complete"] = False;
        mutations.append(bad)
        bad = self._graph(); bad["snapshot"]["omissions_imply_absence"] = True;
        mutations.append(bad)
        bad = self._graph(); bad["snapshot"]["omitted_nodes"] = 1;
        mutations.append(bad)
        bad = self._graph(); bad["snapshot"]["omitted_edges"] = 1;
        mutations.append(bad)
        bad = self._graph(); bad["snapshot"]["counts_by_kind"] = [];
        mutations.append(bad)
        bad = self._graph()
        bad["snapshot"]["counts_by_kind"]["unobserved-kind"] = 0
        mutations.append(bad)
        bad = self._graph(); bad["pages_total"] = None; mutations.append(bad)
        bad = self._graph(); bad["pages_total"] = 2; mutations.append(bad)
        bad = self._graph(); bad["publication_id"] = ""; mutations.append(bad)
        bad = self._graph(); bad["ts"] = "not-a-date"; mutations.append(bad)
        bad = self._graph(); bad["ts"] = "2026-02-30T08:05:57Z";
        mutations.append(bad)
        bad = self._graph(); bad["ts"] = "2999-09-04T08:05:57Z";
        mutations.append(bad)
        bad = self._graph()
        bad["nodes"][0]["ts"] = "2999-09-04T08:05:57Z"
        mutations.append(bad)

        bad = self._graph()
        bad["nodes"][0]["title"] = "hidden\U000e0001title"
        mutations.append(bad)

        for container in ("top", "snapshot", "node"):
            bad = self._graph()
            target = (bad if container == "top" else bad["snapshot"]
                      if container == "snapshot" else bad["nodes"][0])
            target["extra"] = True
            mutations.append(bad)

        for field, value in (
                ("id", "a" * 2001),
                ("id", "not//canonical"),
                ("t", "a" * 201),
                ("t", "Not-Canonical"),
                ("title", "x" * 201)):
            bad = self._graph()
            bad["nodes"][0][field] = value
            mutations.append(bad)

        duplicate = self._graph()
        duplicate["nodes"][0].update({"deg": 4, "din": 2, "dout": 2})
        edge = {
            "s": "sia/cortex", "d": "sia/cortex", "t": "mentions",
            "why": "fixture",
        }
        duplicate["edges"] = [edge, dict(edge)]
        mutations.append(duplicate)

        for field, value in (
                ("t", "Not Canonical"),
                ("why", "hidden\U000e0001context")):
            bad = self._graph()
            bad["nodes"][0].update({"deg": 2, "din": 1, "dout": 1})
            bad["edges"] = [dict(edge, **{field: value})]
            mutations.append(bad)

        for bad in mutations:
            with self.subTest(graph=bad):
                self.assertFalse(self._valid_graph(bad))

        self_edge = self._graph()
        self_edge["nodes"][0].update({"deg": 2, "din": 1, "dout": 1})
        self_edge["edges"] = [edge]
        self.assertTrue(self._valid_graph(self_edge))

        for field, value in (("t", "x" * 4097), ("why", "x" * 91)):
            bad = self._graph()
            bad["nodes"][0].update({"deg": 2, "din": 1, "dout": 1})
            bad["edges"] = [dict(edge, **{field: value})]
            self.assertFalse(self._valid_graph(bad), field)

        bad = self_edge.copy()
        bad["edges"] = [dict(edge, extra=True)]
        self.assertFalse(self._valid_graph(bad))

        partial = self._graph()
        partial["snapshot"]["complete"] = False
        partial["snapshot"]["failed_ops"] = ["list_pages"]
        self.assertTrue(self._valid_graph(partial))
        partial["snapshot"]["failed_ops"] = ["x" * 2001]
        self.assertFalse(self._valid_graph(partial))
        partial["snapshot"]["failed_ops"] = [
            "hidden\U000e0001failure"]
        self.assertFalse(self._valid_graph(partial))

        for publication_id in (
                "A780a1590f1e41d19e68c31c0ee93c88",
                "a780a1590f1e41d19e68c31c0ee93c8",
                "a780a1590f1e41d19e68c31c0ee93c880"):
            bad = self._graph()
            bad["publication_id"] = publication_id
            self.assertFalse(self._valid_graph(bad), publication_id)

    def test_graph_validator_carries_the_exporter_envelope(self):
        cockpit = _qml_function(_read("Cockpit.qml"), "validGraphSnapshot")
        exporter = _read("bin/sialib.py")
        self.assertIn("MAX_GRAPH_NODES = 260", exporter)
        self.assertIn("MAX_GRAPH_EDGES = MAX_EVENT_LOOKUP_PAGES", exporter)
        self.assertIn("MAX_EVENT_LOOKUP_PAGES = 4096", exporter)
        self.assertIn("candidate.nodes.length > 260", cockpit)
        self.assertIn("candidate.edges.length > 4096", cockpit)
        for fields in (
                ('"v", "ts", "publication_id", "nodes", "edges"',),
                ('"complete", "truncated", "omitted_nodes", "omitted_edges"',),
                ('"id", "t", "title", "ts", "origin"',),
                ('"s", "d", "t", "why"',)):
            for field_group in fields:
                self.assertIn(field_group, cockpit)

        # Build the over-cap arrays inside Node. Passing the edge envelope as
        # argv would itself exceed the host's command-line byte boundary.
        logic = """var Model = {
  timestampObservedBy: timestampObservedBy,
  recordHasExactly: recordHasExactly,
  strictStringLength: strictStringLength,
  canonicalCorpusSlug: canonicalCorpusSlug
}
"""
        logic += self._cockpit_logic(
            "isNonNegativeCount", "isPlainRecord", "validOriginLabel",
            "validGraphString", "validGraphSlug", "validGraphSnapshot")
        logic += """
function graphBeyondEnvelope(graph, collection, count, nowIso) {
  var row = collection === "nodes" ? graph.nodes[0] : {
    s: "sia/cortex", d: "sia/cortex", t: "mentions", why: "fixture"
  }
  graph[collection] = []
  for (var i = 0; i < count; i++) graph[collection].push(row)
  return validGraphSnapshot(graph, Date.parse(nowIso))
}
"""
        for collection, count in (("nodes", 261), ("edges", 4097)):
            with self.subTest(collection=collection):
                self.assertFalse(self._run(
                    logic, "graphBeyondEnvelope",
                    [self._graph(), collection, count,
                     "2026-09-04T08:05:57Z"],
                    sources=("Model.js",)))

    def test_graph_maps_admit_object_prototype_names_without_collision(self):
        for field in ("id", "t"):
            graph = self._graph()
            graph["nodes"][0][field] = "constructor"
            if field == "t":
                graph["snapshot"]["counts_by_kind"] = {"constructor": 1}
            self.assertTrue(self._valid_graph(graph), field)

        graph = self._graph()
        graph["nodes"][0]["id"] = "constructor"
        wrapper = """
function layoutHasConstructor(graph) {
  replayLayout(graph, 800, 600)
  var point = posOf("constructor")
  return !!point && isFinite(point.x) && isFinite(point.y)
}
"""
        self.assertTrue(self._run(
            wrapper, "layoutHasConstructor", [graph], sources=("Model.js",)))

    def test_graph_is_committed_only_after_candidate_sync(self):
        body = _qml_function(_read("Cockpit.qml"), "applyGraph")
        self.assertIn("root.validGraphSnapshot(g, Date.now())", body)
        self.assertIn("Model.syncGraph(g", body)
        self.assertLess(body.index("Model.syncGraph(g"),
                        body.index("root.graph = g"))

    def test_graph_json_preserves_integer_lexical_types(self):
        logic = """var Model = {
  timestampObservedBy: timestampObservedBy,
  recordHasExactly: recordHasExactly,
  strictStringLength: strictStringLength,
  inertStatusString: inertStatusString,
  canonicalCorpusSlug: canonicalCorpusSlug
}
"""
        logic += self._cockpit_logic(
            "isNonNegativeCount", "isPlainRecord", "validOriginLabel",
            "validGraphString", "validGraphSlug", "validGraphSnapshot")
        logic += """
function strictGraphAccepted(text, nowIso) {
  try {
    return validGraphSnapshot(
      strictJsonParse(text, "graph"), Date.parse(nowIso))
  } catch (error) { return false }
}
"""
        raw = json.dumps(self._graph(), separators=(",", ":"))
        now = "2026-09-04T08:05:57Z"
        self.assertTrue(self._run(
            logic, "strictGraphAccepted", [raw, now],
            sources=("Model.js",)))
        malformed = (
            raw.replace('"v":2', '"v":2.0'),
            raw.replace('"pages_total":1', '"pages_total":1e0'),
            raw.replace('"deg":0', '"deg":0.0'),
            raw.replace('"aged_out":0', '"aged_out":0e0'),
            raw.replace('"cortex":1', '"cortex":1.0'),
        )
        for candidate in malformed:
            with self.subTest(candidate=candidate):
                self.assertFalse(self._run(
                    logic, "strictGraphAccepted", [candidate, now],
                    sources=("Model.js",)))
        self.assertIn(
            "Model.strictGraphJsonParse(text)",
            _qml_function(_read("Cockpit.qml"), "applyGraph"))

    def test_status_and_graph_must_share_a_publication_generation(self):
        status = {"graph_publication_id": "generation-a"}
        graph = {"publication_id": "generation-a"}
        self.assertTrue(self._run(
            "", "snapshotGenerationsMatch", [status, graph],
            sources=("Model.js",)))
        graph["publication_id"] = "generation-b"
        self.assertFalse(self._run(
            "", "snapshotGenerationsMatch", [status, graph],
            sources=("Model.js",)))
        graph["publication_id"] = ""
        self.assertFalse(self._run(
            "", "snapshotGenerationsMatch", [status, graph],
            sources=("Model.js",)))
        cockpit = _read("Cockpit.qml")
        self.assertIn("mixed status/graph generations",
                      _qml_function(cockpit, "graphSnapshotText"))

    def test_one_current_graph_gate_owns_every_unqualified_graph_view(self):
        cockpit = _read("Cockpit.qml")
        gate = _qml_function(cockpit, "currentGraphSnapshot")
        wrapper = """
var Model = { snapshotGenerationsMatch: snapshotGenerationsMatch }
var root = {
  currentStatus: null, graph: null, graphBoundary: "",
  currentGraphSnapshot: currentGraphSnapshot
}
function admittedGraph(status, graph, boundary) {
  root.currentStatus = status
  root.graph = graph
  root.graphBoundary = boundary
  return root.currentGraphSnapshot()
}
""" + gate
        graph = {"publication_id": "b" * 32, "nodes": [], "edges": [],
                 "snapshot": {"complete": True}}
        status = {"graph_publication_id": "b" * 32}
        self.assertEqual(
            self._run(
                wrapper, "admittedGraph", [status, graph, ""],
                sources=("Model.js",)),
            graph)
        for rejected_status, rejected_graph, boundary in (
                (None, graph, ""),
                ({"graph_publication_id": ""}, graph, ""),
                ({"graph_publication_id": "a" * 32}, graph, ""),
                (status, graph, "last good graph; latest graph rejected"),
                (status, None, "resident graph snapshot pending validation")):
            with self.subTest(status=rejected_status, boundary=boundary):
                self.assertIsNone(self._run(
                    wrapper, "admittedGraph",
                    [rejected_status, rejected_graph, boundary],
                    sources=("Model.js",)))

        declaration = cockpit[
            cockpit.index("readonly property var currentGraph:"):
            cockpit.index("readonly property real staleAfterSec:")]
        self.assertIn("root.currentGraphSnapshot()", declaration)
        self.assertIn("currentGraph && currentGraph.snapshot", declaration)
        for element_id in ("graphCanvas", "inspectorCard"):
            block = _qml_element(cockpit, "id: " + element_id)
            self.assertNotIn("root.graph", block, element_id)
            self.assertIn("root.currentGraph", block, element_id)
        self.assertNotIn(
            "root.graph", _qml_function(cockpit, "nodeById"))
        self.assertIn(
            "root.currentGraph", _qml_function(cockpit, "nodeById"))
        compact = " ".join(cockpit.split())
        self.assertIn(
            "text: root.currentGraph ? root.currentGraph.nodes.length",
            compact)
        self.assertNotIn(
            "text: root.graph ? root.graph.nodes.length", compact)

    def test_publishers_carry_the_graph_generation_into_status(self):
        graph_source = _read("bin/siagraph.py")
        status_source = _read("bin/sialib.py")
        self.assertIn('"publication_id": uuid.uuid4().hex', graph_source)
        self.assertIn(
            "graph_generation = _recoverable_graph_snapshot(prev_graph)",
            status_source)
        self.assertIn(
            '"graph_publication_id": graph_generation["publication_id"]',
            status_source)
        self.assertIn(
            'current.get("graph_publication_id")', status_source)

    def test_future_timestamps_withdraw_status_and_continuity_claims(self):
        wrapper = """
function continuityAt(status, nowIso) {
  return continuityStale(
    status, Date.parse(nowIso), continuityStaleAfterSec())
}
function statusAt(stamp, nowIso) {
  return timestampStale(
    stamp, Date.parse(nowIso), staleAfterDefaultSec())
}
"""
        now = "2026-09-04T08:05:57Z"
        future = "2999-09-04T08:05:57Z"
        self.assertTrue(self._run(
            wrapper, "continuityAt", [{"updated_at": future}, now],
            sources=("Model.js",)))
        self.assertTrue(self._run(
            wrapper, "statusAt", [future, now], sources=("Model.js",)))
        self.assertTrue(self._run(
            wrapper, "statusAt", ["2026-02-30T08:05:57Z", now],
            sources=("Model.js",)))
        cockpit = _read("Cockpit.qml")
        self.assertIn("Model.timestampStale(",
                      _qml_function(cockpit, "applyStatus"))
        timer = _qml_element(cockpit, "interval: 1000; running: root.opened")
        self.assertIn("Model.timestampStale(", timer)

    def test_panel_future_status_is_stale_on_load_and_on_the_clock_tick(self):
        panel = _read("Panel.qml")
        apply_status = _qml_function(panel, "applyStatus")
        timer = _qml_element(panel, "interval: 5000; running: true")
        status = {
            "v": 1,
            "version": "1.7.8",
            "ts": "2999-09-04T08:05:57Z",
            "state": "thinking",
            "pulse_seq": 1,
            "day": "2999-09-04",
            "events_pulse": 0,
            "events_today": 0,
            "organs": {},
            "errors": {},
            "pages": 0,
            "graph_nodes": 0,
            "graph_edges": 0,
            "publication_id": "a780a1590f1e41d19e68c31c0ee93c88",
            "graph_publication_id": "b780a1590f1e41d19e68c31c0ee93c88",
            "projection_debt": {"graph": "", "consolidation": ""},
            "integrity": {
                "chains": {"sia": "pass"}, "verdict": "pass",
                "checked_at": "2999-09-04T08:05:57Z",
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
            "sync_note": "",
            "mind": {
                "nodes": 0, "edges": 0, "decay_active": 0,
                "decay_demoted": 0, "rehearsal_eligible": 0,
                "rehearsal_due": 0, "pinned": 0,
            },
            "agent_queue": {
                "materialized": 0, "refused": 0, "acknowledged": 0,
            },
            "takes": {}, "intents": [], "bench_trend": [],
            "bench_trend_boundary": {"legacy_truncated": False},
            "redactions": {},
        }
        wrapper = apply_status + """
var Model = {
  strictJsonParse: strictJsonParse,
  strictStatusJsonParse: strictStatusJsonParse,
  residentStatusShape: residentStatusShape,
  runtimeLifecycleEvidence: runtimeLifecycleEvidence,
  timestampStale: timestampStale
}
var root = {
  status: null, statusLoadValid: false, stale: false,
  runtimeEvidence: null, pluginVersion: "1.7.8",
  staleAfterSec: staleAfterDefaultSec()
}
function panelStatusAt(snapshot, nowIso) {
  Date.now = function() { return Date.parse(nowIso) }
  applyStatus(JSON.stringify(snapshot))
  return {
    valid: root.statusLoadValid,
    stale: root.stale,
    evidenceVersion: root.runtimeEvidence
      ? root.runtimeEvidence.version : null
  }
}
"""
        self.assertEqual(self._run(
            wrapper, "panelStatusAt",
            [status, "2026-09-04T08:05:57Z"], sources=("Model.js",)),
            {"valid": True, "stale": True, "evidenceVersion": "1.7.8"})
        self.assertIn("Model.runtimeLifecycleEvidence(", apply_status)
        self.assertIn("root.runtimeEvidence", apply_status)
        self.assertIn("root.pluginVersion", apply_status)
        self.assertIn("Model.timestampStale(", apply_status)
        self.assertIn("Model.timestampStale(", timer)
        self.assertNotIn("root.staleAfterSec * 1000", panel)

    def test_cockpit_withdraws_stale_continuity_everywhere(self):
        cockpit = _read("Cockpit.qml")
        self.assertIn("readonly property bool continuityStale:", cockpit)
        current = cockpit[
            cockpit.index("readonly property var currentContinuity:"):
            cockpit.index("readonly property string continuityState:")]
        self.assertIn("root.continuityStale", current)
        self.assertIn("STATUS STALE", _qml_function(
            cockpit, "continuityStateText"))
        self.assertIn("root.continuityStale", _qml_function(
            cockpit, "continuityDetailText"))
        declaration = cockpit[
            cockpit.index("readonly property bool continuityStale:"):
            cockpit.index("readonly property var currentContinuity:")]
        self.assertIn("Model.continuityStale(root.continuity, root.nowMs",
                      declaration)
        timer = _qml_element(
            cockpit, "interval: 1000; running: root.opened")
        self.assertIn("root.nowMs = Date.now()", timer)

    def test_restore_wait_cannot_outlive_request_correlation(self):
        body = _qml_function(_read("Cockpit.qml"), "applyContinuity")
        self.assertIn("else if (!operation)", body)
        branch = body[body.index("else if (!operation)"):]
        self.assertIn("root.restoreVerificationPending = false", branch)
        self.assertIn("root.restoreCorrelationLost = true", branch)
        self.assertIn("correlation", branch.lower())

    def test_verify_result_is_bound_to_the_snapshot_generation(self):
        cockpit = _read("Cockpit.qml")
        verify = _qml_element(cockpit, "id: verifyProc")
        basis = _qml_function(cockpit, "snapshotBasis")
        self.assertIn("property string basis:", verify)
        self.assertIn("root.snapshotBasis()", verify)
        self.assertIn("root.opened", verify)
        self.assertIn("verifyProc.basis", verify)
        self.assertIn("JSON.stringify", basis)
        for field in ("status_publication_id", "graph_publication_id",
                      "ledger_seq", "ledger_head"):
            self.assertIn(field, basis)
        self.assertIn("SIA-VERIFIED-BASIS", verify)
        self.assertIn("receiptMatches(attempt)", verify)
        self.assertIn("function clearVerification(", cockpit)
        for name in ("applyStatus", "applyGraph", "close"):
            self.assertIn("clearVerification()", _qml_function(cockpit, name),
                          name)

    def test_verify_basis_withdraws_an_unobserved_ledger_head(self):
        logic = _qml_function(_read("Cockpit.qml"), "snapshotBasis")
        wrapper = """
var Model = {
  snapshotGenerationsMatch: function() { return true },
  publicationId: function() { return true }
}
var root = {
  currentStatus: null,
  graph: { publication_id: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" },
  validLedgerSummary: function() { return true },
  snapshotBasis: snapshotBasis
}
function basisFor(status) {
  root.currentStatus = status
  return root.snapshotBasis()
}
""" + logic
        status = {
            "publication_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "ledger": {"seq": 0, "head": ""},
        }
        self.assertEqual(self._run(wrapper, "basisFor", [status]), "")

    def test_verify_accepts_only_the_exact_generation_receipt(self):
        basis = json.dumps({
            "graph_publication_id": "a" * 32,
            "ledger_head": "b" * 12,
            "ledger_seq": 7612,
            "status_publication_id": "c" * 32,
        }, separators=(",", ":"))
        controller = _qml_element(_read("Cockpit.qml"), "id: verifyProc")
        start = controller.index("function receiptMatches(")
        opening = controller.index("{", start)
        logic = controller[start:_scan_block(controller, opening) + 1]

        def accepted(output, overflow=False):
            attempt = {"basis": basis, "outText": output,
                       "outOverflow": overflow}
            return self._run(logic, "receiptMatches", [attempt])

        receipt = "SIA-VERIFIED-BASIS " + basis
        self.assertTrue(accepted("VERDICT: all registered chains verified\n"
                                 + receipt + "\n"))
        self.assertFalse(accepted(
            "VERDICT: all registered chains verified\n"))
        self.assertFalse(accepted(receipt + "\ntrailing output\n"))
        self.assertFalse(accepted(receipt + "\n", overflow=True))

    def test_snapshot_rejection_withdraws_prior_live_results(self):
        cockpit = _read("Cockpit.qml")
        for name in ("applyStatus", "applyGraph"):
            body = _qml_function(cockpit, name)
            before_validation = body[:body.index("try {")]
            with self.subTest(callback=name):
                self.assertIn("root.clearVerification()", before_validation)
                self.assertIn("readyProc.cancel()", before_validation)
                self.assertIn("root.clearReadyCheck()", before_validation)

        # A FileView failure bypasses the apply function, so it must perform
        # the same withdrawal before retaining last-good diagnostic pixels.
        for file_id in ("statusFile", "graphFile"):
            block = _qml_element(cockpit, "id: " + file_id)
            with self.subTest(load_failure=file_id):
                self.assertIn("onLoadFailed:", block)
                self.assertIn("root.clearVerification()", block)
                self.assertIn("readyProc.cancel()", block)
                self.assertIn("root.clearReadyCheck()", block)


if __name__ == "__main__":
    unittest.main()
