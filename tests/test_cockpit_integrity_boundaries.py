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

    def _valid_graph(self, graph):
        logic = self._cockpit_logic(
            "isNonNegativeCount", "isPlainRecord", "validOriginLabel",
            "validGraphSnapshot")
        return self._run(logic, "validGraphSnapshot", [graph])

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
        bad = self._graph(); bad["edges"] = [{
            "s": "missing", "d": "sia/cortex", "t": "mentions",
            "why": "fixture"}]; mutations.append(bad)
        bad = self._graph(); bad["snapshot"]["failed_ops"] = [7]; mutations.append(bad)
        bad = self._graph(); bad["snapshot"]["counts_by_kind"] = [];
        mutations.append(bad)
        bad = self._graph(); bad["pages_total"] = None; mutations.append(bad)
        bad = self._graph(); bad["publication_id"] = ""; mutations.append(bad)
        bad = self._graph(); bad["ts"] = "not-a-date"; mutations.append(bad)

        for bad in mutations:
            with self.subTest(graph=bad):
                self.assertFalse(self._valid_graph(bad))

    def test_graph_is_committed_only_after_candidate_sync(self):
        body = _qml_function(_read("Cockpit.qml"), "applyGraph")
        self.assertIn("root.validGraphSnapshot(g)", body)
        self.assertIn("Model.syncGraph(g", body)
        self.assertLess(body.index("Model.syncGraph(g"),
                        body.index("root.graph = g"))

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

    def test_publishers_carry_the_graph_generation_into_status(self):
        graph_source = _read("bin/siagraph.py")
        status_source = _read("bin/sialib.py")
        self.assertIn('"publication_id": uuid.uuid4().hex', graph_source)
        self.assertIn(
            '"graph_publication_id": prev_graph.get("publication_id", "")',
            status_source)
        self.assertIn("graph_publication_id=", status_source)

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
            "ts": "2999-09-04T08:05:57Z",
            "state": "thinking",
            "publication_id": "a780a1590f1e41d19e68c31c0ee93c88",
            "projection_debt": {"graph": "", "consolidation": ""},
            "mind": {
                "nodes": 0, "edges": 0, "decay_active": 0,
                "decay_demoted": 0, "rehearsal_eligible": 0,
                "rehearsal_due": 0, "pinned": 0,
            },
            "agent_queue": {
                "materialized": 0, "refused": 0, "acknowledged": 0,
            },
        }
        wrapper = apply_status + """
var Model = {
  residentStatusShape: residentStatusShape,
  timestampStale: timestampStale
}
var root = {
  status: null, statusLoadValid: false, stale: false,
  staleAfterSec: staleAfterDefaultSec()
}
function panelStatusAt(snapshot, nowIso) {
  Date.now = function() { return Date.parse(nowIso) }
  applyStatus(JSON.stringify(snapshot))
  return { valid: root.statusLoadValid, stale: root.stale }
}
"""
        self.assertEqual(self._run(
            wrapper, "panelStatusAt",
            [status, "2026-09-04T08:05:57Z"], sources=("Model.js",)),
            {"valid": True, "stale": True})
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
        self.assertIn("property string basis:", verify)
        self.assertIn("root.snapshotBasis()", verify)
        self.assertIn("root.opened", verify)
        self.assertIn("verifyProc.basis", verify)
        self.assertIn("function clearVerification(", cockpit)
        for name in ("applyStatus", "applyGraph", "close"):
            self.assertIn("clearVerification()", _qml_function(cockpit, name),
                          name)


if __name__ == "__main__":
    unittest.main()
