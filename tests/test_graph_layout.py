#!/usr/bin/env python3
"""Executable contracts for SIA's deterministic animated cockpit graph."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest


REPO = Path(__file__).resolve().parent.parent


def _read(relative):
    return (REPO / relative).read_text(encoding="utf-8")


class GraphLayoutTests(unittest.TestCase):
    def _run_model(self, body):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node is unavailable for executable Model.js check")
        harness = r'''
const fs = require("fs")
const vm = require("vm")
const source = fs.readFileSync(process.argv[1], "utf8")
  .replace(/^\.pragma library\s*$/m, "")
const context = {}
vm.createContext(context)
vm.runInContext(source, context)
const testBody = new vm.Script("(function () {\n" + process.argv[2]
  + "\n})()")
const result = testBody.runInContext(context)
process.stdout.write(JSON.stringify(result))
'''
        result = subprocess.run(
            [node, "-e", harness, str(REPO / "Model.js"), body],
            cwd=REPO, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_dominant_branch_still_uses_the_whole_field(self):
        metrics = self._run_model(r'''
const graph = {nodes: [], edges: []}
graph.nodes.push({id: "sia/cortex", t: "organ", ts: "", deg: 1})
const organs = ["alpha", "beta", "gamma", "delta"]
for (const organ of organs) {
  const id = "organs/" + organ
  graph.nodes.push({id, t: "organ", ts: "", deg: 1})
  graph.edges.push({s: id, d: "sia/cortex", t: "mentions"})
}
for (let index = 0; index < 64; index++) {
  const id = "events/alpha/memory-" + index
  graph.nodes.push({id, t: "event-day",
    ts: new Date(Date.UTC(2026, 8, 1) + index * 60000).toISOString(),
    deg: 2})
  graph.edges.push({s: id, d: "organs/alpha", t: "mentions"})
  graph.edges.push({s: id, d: "sia/cortex", t: "mentions"})
}
for (let oi = 1; oi < organs.length; oi++) {
  for (let index = 0; index < 4; index++) {
    const id = "events/" + organs[oi] + "/memory-" + index
    graph.nodes.push({id, t: "event-day",
      ts: new Date(Date.UTC(2026, 8, 1) + (64 + oi * 4 + index) * 60000)
        .toISOString(), deg: 2})
    graph.edges.push({s: id, d: "organs/" + organs[oi], t: "mentions"})
    graph.edges.push({s: id, d: "sia/cortex", t: "mentions"})
  }
}
const width = 900, height = 900, cx = width / 2, cy = height / 2
syncGraph(graph, width, height)
for (let tick = 0; tick < 900; tick++) step(graph, width, height, 1)
const points = graph.nodes.map(node => posOf(node.id))
const quadrants = [0, 0, 0, 0]
for (const point of points) {
  const quadrant = (point.y >= cy ? 2 : 0) + (point.x >= cx ? 1 : 0)
  quadrants[quadrant]++
}
return {
  quadrants,
  left: Math.min(...points.map(point => point.x)),
  right: Math.max(...points.map(point => point.x)),
  top: Math.min(...points.map(point => point.y)),
  bottom: Math.max(...points.map(point => point.y)),
  meanX: points.reduce((sum, point) => sum + point.x, 0) / points.length,
  meanY: points.reduce((sum, point) => sum + point.y, 0) / points.length
}
''')
        self.assertTrue(all(count >= 8 for count in metrics["quadrants"]),
                        metrics)
        self.assertLess(metrics["left"], 225, metrics)
        self.assertGreater(metrics["right"], 675, metrics)
        self.assertLess(metrics["top"], 225, metrics)
        self.assertGreater(metrics["bottom"], 675, metrics)
        self.assertLess(abs(metrics["meanX"] - 450), 135, metrics)
        self.assertLess(abs(metrics["meanY"] - 450), 135, metrics)

    def test_replay_reseeds_growth_and_hidden_nodes_do_not_settle_early(self):
        metrics = self._run_model(r'''
const graph = {nodes: [
  {id: "sia/cortex", t: "organ", ts: "", deg: 1},
  {id: "organs/alpha", t: "organ", ts: "", deg: 2},
  {id: "events/alpha/old", t: "event-day",
    ts: "2026-09-01T00:00:00Z", deg: 2},
  {id: "events/alpha/new", t: "event-day",
    ts: "2026-09-02T00:00:00Z", deg: 2}
], edges: [
  {s: "organs/alpha", d: "sia/cortex", t: "mentions"},
  {s: "events/alpha/old", d: "organs/alpha", t: "mentions"},
  {s: "events/alpha/old", d: "sia/cortex", t: "mentions"},
  {s: "events/alpha/new", d: "organs/alpha", t: "mentions"},
  {s: "events/alpha/new", d: "sia/cortex", t: "mentions"}
]}
const width = 800, height = 800, cx = width / 2, cy = height / 2
replayLayout(graph, width, height)
const first = {...posOf("events/alpha/new")}
for (let tick = 0; tick < 120; tick++) step(graph, width, height, 0)
const hidden = {...posOf("events/alpha/new")}
for (let tick = 0; tick < 240; tick++) step(graph, width, height, 1)
const grown = {...posOf("events/alpha/new")}
replayLayout(graph, width, height)
const repeated = {...posOf("events/alpha/new")}
function radius(point) {
  return Math.hypot(point.x - cx, point.y - cy)
}
return {
  hiddenMovement: Math.hypot(hidden.x - first.x, hidden.y - first.y),
  startRadius: radius(first),
  grownRadius: radius(grown),
  deterministic: first.x === repeated.x && first.y === repeated.y
}
''')
        self.assertEqual(metrics["hiddenMovement"], 0, metrics)
        self.assertGreater(metrics["grownRadius"],
                           metrics["startRadius"] + 100, metrics)
        self.assertTrue(metrics["deterministic"], metrics)

    def test_long_frames_settle_instead_of_running_forever(self):
        """The frame loop stops when the layout settles; long frames must let it.

        The physics was tuned per 40 ms tick and scaled by the elapsed frame
        time. Fed a 100 ms frame (the step scale's 2.5 cap, routine under a
        software renderer), the explicit integrator overshot its own springs
        and never crossed the settle threshold, so the cockpit's frame loop
        ran at full rate forever: a graph sitting still cost 64% of a core.
        Time is now spent in sub-ticks of at most one tuned tick, so a
        100 ms frame settles in the same wall time as a 17 ms one, and a
        frame of exactly 2.5 ticks follows the trajectory of 2.5 sub-ticks.
        """
        metrics = self._run_model(r'''
function build() {
  const nodes = [{id: "sia/cortex", t: "organ", ts: "", deg: 1}]
  const edges = []
  for (let o = 0; o < 8; o++) {
    nodes.push({id: "organs/o" + o, t: "organ", ts: "", deg: 12})
    edges.push({s: "organs/o" + o, d: "sia/cortex", t: "mentions"})
    for (let k = 0; k < 60; k++) {
      const id = "events/o" + o + "/d" + k
      nodes.push({id, t: "event-day", deg: 2,
        ts: "2026-09-" + String(1 + (k % 28)).padStart(2, "0") + "T00:00:00Z"})
      edges.push({s: id, d: "organs/o" + o, t: "mentions"})
      if (k) edges.push({s: id, d: "events/o" + o + "/d" + (k - 1), t: "mentions"})
      // One cross-organ link per memory: the density at which a 2.5-tick
      // step made the old integrator oscillate forever.
      edges.push({s: id, d: "events/o" + ((o + 1) % 8) + "/d" + ((k * 7) % 60), t: "mentions"})
    }
  }
  return {nodes, edges}
}
function scatter(graph) {
  // Seeding places nodes near their targets; a real pulse's fresh nodes and
  // a resized canvas do not. Start every memory far from where it belongs,
  // deterministically, so the layout has real distance to travel.
  let k = 0
  for (const id in L.pos) {
    if (id === "sia/cortex") continue
    L.pos[id].x = 60 + ((k * 587) % 1880)
    L.pos[id].y = 60 + ((k * 733) % 1680)
    L.pos[id].vx = 0; L.pos[id].vy = 0
    k++
  }
}
function settleTime(dtMs) {
  const graph = build()
  // Each run seeds from nothing; the layout state is module-global.
  L.pos = {}; L.seeded = false; L.maxSpeed = 0
  syncGraph(graph, 2000, 1800)
  for (let tick = 1; tick <= 5000; tick++) {
    step(graph, 2000, 1800, 1.0, dtMs)
    if (settled()) return tick * dtMs / 1000
  }
  return -1
}
const walls = {fast: settleTime(16.7), tick: settleTime(40), slow: settleTime(100)}
return {walls, nodes: build().nodes.length}
''')
        walls = metrics["walls"]
        for name in ("fast", "tick", "slow"):
            self.assertGreater(walls[name], 0, metrics)
            self.assertLess(walls[name], 30, metrics)
        # Same order of wall-clock settle time across frame rates; the 100 ms
        # case used to be -1 (never) on this exact graph.
        self.assertLess(max(walls.values()), 3 * min(walls.values()), metrics)

    def test_label_candidates_begin_outward_and_ui_uses_collision_guard(self):
        candidates = self._run_model(r'''
return {
  top: labelCandidates(450, 120, 450, 450, 6, 80, 18),
  right: labelCandidates(780, 450, 450, 450, 6, 80, 18)
}
''')
        self.assertLess(candidates["top"][0]["y"], 120)
        self.assertGreater(candidates["right"][0]["x"], 780)

        cockpit = _read("Cockpit.qml")
        self.assertIn("Model.replayLayout", cockpit)
        self.assertIn("root.revealT, ms)", cockpit)
        self.assertIn("nodeObstacles", cockpit)
        self.assertIn("placedLabels", cockpit)
        self.assertIn("Model.labelCandidates", cockpit)
        self.assertIn("import QtQuick.Controls as Controls", cockpit)
        self.assertIn("Controls.Button {", cockpit)
        self.assertIn("Controls.ScrollBar.vertical", cockpit)


if __name__ == "__main__":
    unittest.main()
