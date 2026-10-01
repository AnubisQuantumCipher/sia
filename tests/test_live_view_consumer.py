"""Executable callback-order contracts for the shared live-view reader.

This is a deterministic QML-logic harness, not an actual Process integration
or an authority test. It lifts the component's functions, signal handlers and
display binding, then supplies property notifications, a deferred-callback
queue and one fake child. Model.js remains the real display validator. The
small status/view fixtures contain no machine history or corpus content.
"""

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from tests.test_cockpit_boundary_horizon import (
    CockpitBoundaryHorizonTests, _JsRunner, _qml_element, _qml_function,
    _scan_block,
)


REPO = Path(__file__).resolve().parent.parent


def _block(source, marker):
    opening = source.index("{", source.index(marker))
    return source[opening:_scan_block(source, opening) + 1]


def _signal(source, name, wrapper, parameters="", prelude=""):
    match = re.search(
        r"\b" + re.escape(name) + r"\s*:\s*(?:function\s*\([^)]*\)\s*)?",
        source)
    if match is None:
        raise AssertionError("missing signal handler: " + name)
    start = match.end()
    if source[start] == "{":
        body = source[start + 1:_scan_block(source, start)]
    else:
        body = source[start:source.index("\n", start)]
    return "function " + wrapper + "(" + parameters + ") {\n" + prelude + body + "\n}\n"


class LiveViewConsumerLifecycle(unittest.TestCase):
    def setUp(self):
        self.node = shutil.which("node")
        if self.node is None:
            self.skipTest("Node is unavailable for executable consumer logic")
        path = REPO / "LiveView.qml"
        self.assertTrue(path.is_file(), "missing shared live consumer")
        self.source = path.read_text(encoding="utf-8")
        self.status = CockpitBoundaryHorizonTests(
            methodName="runTest")._snapshot()

    def harness(self):
        source = self.source
        process = _qml_element(source, "id: liveProc")
        functions = ("statusKey", "invalidate", "refresh", "applyResult", "fail", "settle")
        lifted = "\n".join(_qml_function(source, name) for name in functions)
        assignment = "\n".join("root." + name + " = " + name for name in functions)
        defaults = []
        for match in re.finditer(
                r"^  (?:readonly )?property (?:var|bool|string|int|real) (\w+): ([^\n]+)$",
                source, re.MULTILINE):
            if match[1] not in ("display", "summary"):
                defaults.append("root." + match[1] + " = " + match[2])
        display_start = source.index("readonly property var display:") \
            + len("readonly property var display:")
        display_end = source.index("readonly property string summary:", display_start)
        display_expression = source[display_start:display_end].strip()
        summary = re.search(r"readonly property string summary: ([^\n]+)", source)[1]
        handlers = "\n".join((
            _signal(source, "onStatusSnapshotChanged", "statusChanged"),
            _signal(source, "onEnabledChanged", "enabledChanged"),
            _signal(source, "onDisplayChanged", "displayChanged"),
            _signal(process, "onStarted", "started"),
            _signal(process, "onRunningChanged", "runningChanged",
                    prelude="var running = liveProc.running\n"),
            _signal(process, "onExited", "exited", "code"),
            _signal(_block(process, "stdout: StdioCollector"),
                    "onStreamFinished", "stdoutFinished", "text"),
            _signal(_block(process, "stderr: StdioCollector"),
                    "onStreamFinished", "stderrFinished", "text"),
        ))
        return """
var Model = {
  residentStatusShape: residentStatusShape,
  liveWorkspaceView: liveWorkspaceView,
  liveWorkspaceSummary: liveWorkspaceSummary,
  staleAfterDefaultSec: staleAfterDefaultSec
}
var root, liveProc, queued, launches, fixtureView, clockMs
var Qt = {callLater: function(callback) { queued.push(callback) }}
Date.now = function() { return clockMs }
function clone(value) { return JSON.parse(JSON.stringify(value)) }
""" + lifted + "\n" + handlers + """
function fixture(status) {
  var observed = Date.parse(status.ts) / 1000
  var digest = "a".repeat(64)
  var activation = {
    component: "usage-salience", status: "computed-unverified", observed_at: observed,
    order: ["fixture/page"], activations: [{
      component: "usage-salience", subject: "fixture/page", observed_at: observed,
      status: "computed-unverified", score: 0, reason: null
    }]
  }
  return {
    schema: "sia-controller-live-view-v1", status: "available", origin: "derived",
    as_of: observed, view_sha256: digest,
    publication: {
      publication_id: status.publication_id, pulse_seq: status.pulse_seq,
      status_timestamp: status.ts, epoch_id: "synthetic-consumer-display",
      state_sha256: digest, transition_sha256: digest, generation_sha256: digest,
      source_batch_sha256: digest, source_effects_receipt_sha256: digest,
      policy_sha256: digest
    },
    workspace: {
      component: "maintained-workspace", status: "computed-unverified",
      observed_at: observed, phase: "holding", transition: "ignited", release_reason: null,
      capacity: 3, ignition_threshold: 0, slots: ["fixture/page"],
      candidates: [{subject: "fixture/page", eligible: true, selected: true}],
      payload_sha256: digest, ignited_at: observed, expires_at: observed + 10,
      selected_sources: [{subject: "fixture/page", origin: "derived", source_sha256: digest}],
      selection: {observed_at: observed, payload_sha256: digest, frame_sha256: digest,
                  activation: clone(activation), admission: []},
      broadcast_identities: {}
    },
    activation: activation, admission: [], encoding: [], coretrieval: {},
    idle: {requested: false, availability: null, binding_status: null, binding_sha256: null,
           gist_artifact_sha256: null, proposed_pages: [],
           gist_publication_status: "not-requested", gist_publication: null},
    non_claims: ["Synthetic display fixture; no source authority or cognitive claim."],
    upstream_non_claims: {}
  }
}
function boot(status) {
  queued = []; launches = []; root = {}; liveProc = {}
  clockMs = Date.parse(status.ts)
""" + "\n".join(defaults) + "\n" + assignment + """
  root.statusSnapshot = clone(status)
  root.enabled = true
  root.componentReady = true
  fixtureView = fixture(root.statusSnapshot)
  Object.defineProperty(root, "display", {get: function() {
    return (
""" + display_expression + """
    )
  }})
  Object.defineProperty(root, "summary", {get: function() { return (
""" + summary + """
  ) }})
  function notify(name, callback) {
    var value = root[name]
    Object.defineProperty(root, name, {
      get: function() { return value },
      set: function(next) { value = next; callback() }
    })
  }
  notify("statusSnapshot", statusChanged)
  notify("enabled", enabledChanged)
  notify("rawView", displayChanged)
  notify("nowMs", displayChanged)
  var running = false
  Object.defineProperty(liveProc, "running", {
    get: function() { return running },
    set: function(next) {
      if (next === running) return
      running = next
      if (next) launches.push(root.attemptStatusKey)
      runningChanged()
    }
  })
  if (!Model.residentStatusShape(root.statusSnapshot)
      || Model.liveWorkspaceView(fixtureView, root.statusSnapshot,
                                clockMs, root.staleAfterSec) === null)
    throw new Error("synthetic display fixture is outside the real Model contract")
}
function seedVisible() {
  root.applyResult(JSON.stringify(fixtureView), root.statusKey(root.statusSnapshot))
  if (root.rawView === null) throw new Error("fixture failed to become visible")
}
function launch() { root.refresh(); started() }
function stop(code) { liveProc.running = false; exited(code) }
function finish(view, code) {
  stdoutFinished(JSON.stringify(view)); stderrFinished(""); stop(code)
}
function flushLater() {
  var ready = queued.splice(0)
  ready.forEach(function(callback) { callback() })
}
function state() {
  return {visible: root.rawView !== null,
          publication: root.rawView === null ? null : root.rawView.publication.publication_id,
          checking: root.checking, running: liveProc.running,
          pending: root.rereadPending, queued: queued.length, launches: launches.length,
          reason: root.unavailableReason, outText: root.outText, errText: root.errText}
}
"""

    def run_case(self, script):
        runner = _JsRunner.SCRIPT.replace(
            "JSON.parse(process.argv[4])", "JSON.parse(fs.readFileSync(0, 'utf8'))")
        result = subprocess.run(
            [self.node, "-e", runner, json.dumps([str(REPO / "Model.js")]),
             self.harness() + "\nfunction scenario(status) {\n" + script + "\n}\n",
             "scenario"], input=json.dumps([self.status]), cwd=REPO,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_unchanged_key_polls_preserve_slow_matching_read_without_extra_child(self):
        # A repeated poll is not a new authority generation. The predecessor
        # test required discarding this matching response, which starved any
        # read slower than the poll cadence. Preserve withdrawal and the
        # single-child bound, but require this successful read to complete.
        result = self.run_case("""
boot(status); seedVisible(); launch()
var begun = state()
for (var poll = 0; poll < 3; poll++) {
  clockMs += root.pollInterval
  root.nowMs = Date.now()
  root.refresh()
}
var coalesced = state()
finish(fixtureView, 0)
var completed = state()
flushLater()
return {begun: begun, coalesced: coalesced, completed: completed,
        afterDeferredCallbacks: state()}
""")
        for field in ("begun", "coalesced"):
            self.assertFalse(result[field]["visible"], field)
        self.assertEqual(result["begun"]["launches"], 1)
        self.assertEqual(result["coalesced"]["launches"], 1)
        self.assertTrue(result["coalesced"]["checking"])
        self.assertFalse(result["coalesced"]["pending"])
        self.assertTrue(result["completed"]["visible"])
        self.assertFalse(result["completed"]["checking"])
        self.assertEqual(result["completed"]["queued"], 0)
        self.assertEqual(result["completed"]["launches"], 1)
        self.assertEqual(result["completed"]["outText"], "")
        self.assertEqual(result["completed"]["errText"], "")
        self.assertEqual(result["afterDeferredCallbacks"], result["completed"])

    def test_exit_and_stream_callbacks_require_complete_join_in_every_order(self):
        result = self.run_case("""
var orders = [
  ["exit", "stdout", "stderr"], ["exit", "stderr", "stdout"],
  ["stdout", "exit", "stderr"], ["stderr", "exit", "stdout"],
  ["stdout", "stderr", "exit"], ["stderr", "stdout", "exit"]
]
return orders.map(function(order) {
  boot(status); seedVisible(); launch()
  var steps = []
  order.forEach(function(event) {
    if (event === "exit") stop(0)
    else if (event === "stdout") stdoutFinished(JSON.stringify(fixtureView))
    else stderrFinished("")
    steps.push(state())
  })
  root.settle(); root.settle()
  return {order: order, steps: steps, after: state()}
})
""")
        for item in result:
            with self.subTest(order=item["order"]):
                for step in item["steps"][:-1]:
                    self.assertFalse(step["visible"])
                    self.assertTrue(step["checking"])
                self.assertTrue(item["steps"][-1]["visible"])
                self.assertEqual(item["after"]["launches"], 1)
                self.assertFalse(item["after"]["checking"])
                self.assertEqual(item["after"]["outText"], "")
                self.assertEqual(item["after"]["errText"], "")

    def test_status_replacement_discards_old_result_and_rechecks_new_generation(self):
        result = self.run_case("""
boot(status); seedVisible(); launch()
var oldView = clone(fixtureView)
var oldKey = root.attemptStatusKey
var replacement = clone(status)
replacement.publication_id = "d".repeat(32)
root.statusSnapshot = replacement
var changed = state()
finish(oldView, 0)
var discarded = state()
flushLater(); started()
fixtureView = fixture(replacement)
finish(fixtureView, 0)
var newView = state()
root.applyResult(JSON.stringify(oldView), oldKey)
return {changed: changed, discarded: discarded, newView: newView, oldKeyAttempt: state()}
""")
        self.assertFalse(result["changed"]["visible"])
        self.assertTrue(result["changed"]["pending"])
        self.assertFalse(result["discarded"]["visible"])
        self.assertEqual(result["discarded"]["queued"], 1)
        self.assertTrue(result["newView"]["visible"])
        self.assertEqual(result["newView"]["publication"], "d" * 32)
        self.assertFalse(result["oldKeyAttempt"]["visible"])

    def test_unavailable_status_and_disabled_component_cannot_restore_old_view(self):
        result = self.run_case("""
return ["disabled", "status-unavailable"].map(function(mode) {
  boot(status); seedVisible(); launch()
  if (mode === "disabled") root.enabled = false
  else root.statusSnapshot = null
  var invalidated = state()
  finish(fixtureView, 0); flushLater()
  var completed = state()
  root.applyResult(JSON.stringify(fixtureView), root.attemptStatusKey)
  return {mode: mode, invalidated: invalidated, completed: completed, direct: state()}
})
""")
        for item in result:
            with self.subTest(mode=item["mode"]):
                for field in ("invalidated", "completed", "direct"):
                    self.assertFalse(item[field]["visible"])
                self.assertEqual(item["completed"]["launches"], 1)
                self.assertFalse(item["completed"]["checking"])

    def test_real_supersession_stays_sticky_when_original_key_is_restored(self):
        result = self.run_case("""
return ["changed-key", "disabled", "status-unavailable"].map(function(mode) {
  boot(status); seedVisible(); launch()
  if (mode === "changed-key") {
    var replacement = clone(status)
    replacement.publication_id = "d".repeat(32)
    root.statusSnapshot = replacement
    root.statusSnapshot = clone(status)
  } else if (mode === "disabled") {
    root.enabled = false
    root.enabled = true
  } else {
    root.statusSnapshot = null
    root.statusSnapshot = clone(status)
  }
  // Further unchanged-key polls must not erase a genuine supersession.
  root.refresh(); root.refresh()
  var invalidated = state()
  finish(fixtureView, 0)
  var discarded = state()
  flushLater(); started(); finish(fixtureView, 0)
  return {mode: mode, invalidated: invalidated, discarded: discarded,
          completed: state()}
})
""")
        for item in result:
            with self.subTest(mode=item["mode"]):
                self.assertFalse(item["invalidated"]["visible"])
                self.assertTrue(item["invalidated"]["pending"])
                self.assertEqual(item["invalidated"]["launches"], 1)
                self.assertFalse(item["discarded"]["visible"])
                self.assertEqual(item["discarded"]["queued"], 1)
                self.assertFalse(item["discarded"]["checking"])
                self.assertTrue(item["completed"]["visible"])
                self.assertEqual(item["completed"]["launches"], 2)
                self.assertEqual(item["completed"]["queued"], 0)

    def test_overflow_nonzero_and_parse_failure_never_publish_partial_response(self):
        result = self.run_case("""
return ["stdout-overflow", "stderr-overflow", "nonzero", "malformed"].map(function(mode) {
  boot(status); seedVisible(); launch()
  // Lower only the copied harness ceilings to keep overflow fixtures tiny;
  // production declares these properties readonly.
  if (mode === "stdout-overflow") root.responseMaxLength = 1
  if (mode === "stderr-overflow") root.errorResponseMaxLength = 1
  stdoutFinished(mode === "malformed" ? "{" : JSON.stringify(fixtureView))
  stderrFinished(mode === "stderr-overflow" ? "oversize" : "")
  stop(mode === "nonzero" ? 1 : 0)
  return {mode: mode, state: state()}
})
""")
        reasons = {
            "stdout-overflow": "live-response-overflow",
            "stderr-overflow": "live-response-overflow",
            "nonzero": "live-command-failed",
            "malformed": "invalid-live-response",
        }
        for item in result:
            with self.subTest(mode=item["mode"]):
                state = item["state"]
                self.assertFalse(state["visible"])
                self.assertFalse(state["checking"])
                self.assertEqual(state["reason"], reasons[item["mode"]])
                self.assertEqual(state["outText"], "")
                self.assertEqual(state["errText"], "")

    def test_start_failure_resolves_without_waiting_for_nonexistent_streams(self):
        result = self.run_case("""
boot(status); seedVisible(); root.refresh()
liveProc.running = false
return state()
""")
        self.assertFalse(result["visible"])
        self.assertFalse(result["checking"])
        self.assertFalse(result["running"])
        self.assertEqual(result["reason"], "live-command-start-failed")
        self.assertEqual(result["queued"], 0)

    def test_expired_retained_view_is_not_active_and_stale_view_cannot_reappear(self):
        result = self.run_case("""
boot(status); seedVisible()
clockMs = fixtureView.workspace.expires_at * 1000
root.nowMs = Date.now()
var expired = {state: state(), display: root.display, summary: root.summary}
clockMs = (fixtureView.as_of + root.staleAfterSec + 1) * 1000
root.nowMs = Date.now()
var stale = state()
clockMs = fixtureView.as_of * 1000
root.nowMs = Date.now()
return {expired: expired, stale: stale, rewound: state(), summary: root.summary}
""")
        self.assertTrue(result["expired"]["state"]["visible"])
        self.assertTrue(result["expired"]["display"]["expired"])
        self.assertIn("expired", result["expired"]["summary"])
        self.assertIn("computed-unverified", result["expired"]["summary"])
        self.assertNotRegex(result["expired"]["summary"], r"\bactive\b")
        self.assertFalse(result["stale"]["visible"])
        self.assertFalse(result["rewound"]["visible"])
        self.assertIn("unavailable", result["summary"])


if __name__ == "__main__":
    unittest.main()
