"""Display contracts for the retained, source-authorized live workspace.

The fixture comes through the live-view front door once. Clock rebasing below
is only a display fixture: Model.js is not an authority reader, its inputs are
not authentication evidence, and no digest is recomputed to pretend otherwise.
Node executes the pure display functions. QML-only lifecycle and integration
wiring are pinned separately, as in test_cockpit_boundary_horizon.
"""

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import copy
import datetime
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import unittest

from tests.test_cockpit_boundary_horizon import (
    _JsRunner, _qml_element, _qml_function, _read,
)
from tests import test_live_view as view_tests


REPO = Path(__file__).resolve().parent.parent


class LiveWorkspaceDisplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if cls.node is None:
            raise unittest.SkipTest("Node is unavailable for executable display logic")
        case = view_tests.SourceAuthorizedLiveView(methodName="runTest")
        module = case.module()
        with case.completed() as completed, case.read_only(completed):
            cls.view = copy.deepcopy(module.read_view(completed.lib.__dict__))
            cls.status = copy.deepcopy(completed.admitted_status())
        # The composed source fixture intentionally has an independent status
        # clock. Rebase the display-only pair without reissuing any authority.
        stamp = datetime.datetime.fromtimestamp(
            cls.view["as_of"], datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cls.status["ts"] = stamp
        cls.view["publication"]["status_timestamp"] = stamp

    def _run(self, prelude, function_name, arguments):
        # Preserve the exact JSON cases while avoiding the host argv limit.
        # The controlling RED reached OSError before Node for the mutation
        # bundle; stdin changes transport, not the evaluated display contract.
        script = _JsRunner.SCRIPT.replace(
            "JSON.parse(process.argv[4])",
            "JSON.parse(fs.readFileSync(0, 'utf8'))")
        result = subprocess.run(
            [self.node, "-e", script,
             json.dumps([str(REPO / "Model.js")]), prelude, function_name],
            input=json.dumps(arguments, separators=(",", ":")),
            cwd=REPO, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def display(self, view=None, status=None, *, clock="as-of"):
        return self._run("""
function displayAt(view, status, clock) {
  var now = view.as_of * 1000
  if (clock === "expiry") now = view.workspace.expires_at * 1000
  if (clock === "stale") now += (staleAfterDefaultSec() + 1) * 1000
  if (clock === "future") now -= 1
  return liveWorkspaceView(view, status, now, staleAfterDefaultSec())
}
""", "displayAt", [self.view if view is None else view,
                       self.status if status is None else status, clock])

    def test_real_frontdoor_projection_remains_retained_and_detached(self):
        result = self.display()
        self.assertIsInstance(result, dict)
        self.assertEqual(result["as_of"], self.view["as_of"])
        self.assertFalse(result["expired"])
        for field in ("publication", "workspace", "activation", "admission",
                      "idle", "non_claims"):
            self.assertEqual(result[field], self.view[field], field)
        self.assertEqual(result["workspace"]["status"], "computed-unverified")
        self.assertTrue(result["workspace"]["selected_sources"])
        self.assertEqual(self._run("""
function displayDetached(view, status) {
  var result = liveWorkspaceView(view, status, view.as_of * 1000,
                                 staleAfterDefaultSec())
  var before = JSON.stringify(result)
  view.workspace.slots.length = 0
  view.workspace.selected_sources[0].origin = "model"
  view.publication.publication_id = "changed"
  view.non_claims.length = 0
  return JSON.stringify(result) === before
}
""", "displayDetached", [self.view, self.status]), True)

    def test_selection_reason_and_current_pulse_are_distinct_observations(self):
        view = copy.deepcopy(self.view)
        self.assertIsNotNone(view["workspace"]["selection"])
        # Synthetic display-only pulse: the held selection remains original.
        current = view["activation"]["activations"][0]
        current.update(status="unavailable", score=None, reason="no-use-history")
        result = self.display(view)
        self.assertIsNotNone(result)
        self.assertEqual(result["workspace"]["selection"],
                         self.view["workspace"]["selection"])
        self.assertEqual(result["activation"], view["activation"])
        self.assertEqual(result["workspace"]["candidates"],
                         self.view["workspace"]["candidates"])

    def test_expiry_keeps_retained_identity_but_never_current_activity(self):
        result = self.display(clock="expiry")
        self.assertIsNotNone(result)
        self.assertTrue(result["expired"])
        self.assertEqual(result["workspace"], self.view["workspace"])
        summary = self._run("", "liveWorkspaceSummary", [result])
        self.assertIn("expired", summary.casefold())
        self.assertIn("computed-unverified", summary)
        self.assertNotRegex(summary.casefold(), r"\bactive\b")

    def test_stale_and_future_observation_withdraw_instead_of_using_last_good(self):
        self.assertIsNone(self.display(clock="stale"))
        self.assertIsNone(self.display(clock="future"))
        self.assertIsNone(self._run("", "liveWorkspaceView", [
            self.view, None, self.view["as_of"] * 1000, 240]))

    def test_mismatched_publication_status_sequence_or_stamp_refuses(self):
        pairs = []
        for field, replacement in (
                ("publication_id", "d" * 32), ("pulse_seq", -1),
                ("ts", "2026-09-08T00:00:00Z")):
            status = copy.deepcopy(self.status)
            status[field] = replacement
            pairs.append([field, self.view, status])
        self.assertEqual(self._run("""
function rejectPairs(pairs) {
  return pairs.filter(function(pair) {
    return liveWorkspaceView(pair[1], pair[2], pair[1].as_of * 1000,
                             staleAfterDefaultSec()) !== null
  }).map(function(pair) { return pair[0] })
}
""", "rejectPairs", [pairs]), [])

    def test_malformed_display_data_and_truth_label_substitution_fail_closed(self):
        variants = []

        def changed(label, path, value):
            candidate = copy.deepcopy(self.view)
            target = candidate
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = value
            variants.append([label, candidate])

        for field, value in (
                ("schema", "sia-live-publication-v1"), ("status", "refused"),
                ("origin", "evidence"), ("as_of", "now"),
                ("workspace", None), ("publication", None),
                ("non_claims", [])):
            changed(field, [field], value)
        for field, value in (
                ("component", "Global Workspace"), ("status", "formal-bounded"),
                ("phase", "active"), ("capacity", 0), ("capacity", "7"),
                ("slots", ["../private"]), ("slots", ["bad\nslug"]),
                ("transition", "ignited\ntrusted"),
                ("release_reason", "hidden\u202ereason"),
                ("expires_at", "later"), ("selected_sources", [None]),
                ("selection", None), ("candidates", [None])):
            changed("workspace." + field, ["workspace", field], value)
        changed("bad-source-origin", ["workspace", "selected_sources", 0, "origin"],
                "certified")
        changed("bad-source-identity",
                ["workspace", "selected_sources", 0, "source_sha256"], "not-a-digest")
        changed("bad-selected-clock", ["workspace", "selection", "observed_at"],
                "now")
        changed("missing-selected-admission",
                ["workspace", "selection", "admission"], None)
        changed("false-current-status", ["activation", "status"], "exact")
        changed("body-in-slot", ["workspace", "slots"], [{"content": "hidden"}])
        self.assertEqual(self._run("""
function rejectVariants(variants, status, now) {
  return variants.filter(function(pair) {
    return liveWorkspaceView(pair[1], status, now,
                             staleAfterDefaultSec()) !== null
  }).map(function(pair) { return pair[0] })
}
""", "rejectVariants", [variants, self.status, self.view["as_of"] * 1000]), [])

    def test_slots_capacity_and_selected_origins_are_consistent(self):
        self.assertEqual(self._run("""
function rejectRosterDrift(view, status) {
  function rejected(mutator) {
    var item = JSON.parse(JSON.stringify(view))
    mutator(item.workspace)
    return liveWorkspaceView(item, status, item.as_of * 1000,
                             staleAfterDefaultSec()) === null
  }
  return [
    rejected(function(ws) { ws.capacity = ws.slots.length - 1 }),
    rejected(function(ws) { ws.slots.push(ws.slots[0]) }),
    rejected(function(ws) { ws.selected_sources = [] }),
    rejected(function(ws) { ws.selected_sources[0].subject = "other/page" }),
    rejected(function(ws) { ws.expires_at = ws.ignited_at })
  ]
}
""", "rejectRosterDrift", [self.view, self.status]), [True] * 5)

    def test_summary_keeps_as_of_dynamic_capacity_raw_status_and_gist_boundary(self):
        view = copy.deepcopy(self.view)
        view["workspace"]["capacity"] = 13  # declared display fixture, not a metric
        result = self.display(view)
        self.assertIsNotNone(result)
        summary = self._run("", "liveWorkspaceSummary", [result])
        for text in ("Live workspace", "retained", "as of", "computed-unverified",
                     "13", view["workspace"]["transition"],
                     view["idle"]["gist_publication_status"]):
            self.assertIn(text.casefold(), summary.casefold(), text)
        self.assertNotIn("OF 7", summary)
        self.assertNotRegex(summary.casefold(), r"\b(active|certified|proven)\b")
        self.assertIn("unavailable", self._run(
            "", "liveWorkspaceSummary", [None]).casefold())

    def test_summary_distinguishes_no_native_support_from_gist_publication(self):
        result = self.display()
        self.assertIsNotNone(result)
        # Summary-only display fixture, not a manufactured native capture or
        # source receipt. Producer validation lives in the source-view tests.
        result["idle"].update(
            requested=True,
            availability="no-selected-supported-native-source",
            binding_status="bound-no-gist",
            gist_publication_status="proposals-only",
            gist_publication=None,
            proposed_pages=[])
        summary = self._run("", "liveWorkspaceSummary", [result])
        for text in ("no-selected-supported-native-source", "proposals-only",
                     "computed-unverified"):
            self.assertIn(text, summary)
        self.assertNotIn("gist-pages-published", summary)
        self.assertNotRegex(summary.casefold(), r"\b(sleeping|consolidated)\b")


class LiveWorkspaceQmlWiring(unittest.TestCase):
    def test_shared_consumer_is_in_release_snapshot_and_desktop_stage(self):
        installer = _read("install.sh")
        snapshot = shlex.split(installer.split(
            "SIA_RELEASE_FILES=(", 1)[1].split("\n)", 1)[0])
        match = re.search(r"PLUGIN_ROOT_FILES=\(([^)]*)\)", installer)
        self.assertIsNotNone(match)
        desktop = shlex.split(match.group(1))
        self.assertEqual(snapshot.count("LiveView.qml"), 1)
        self.assertEqual(desktop.count("LiveView.qml"), 1)

    def shared(self):
        path = REPO / "LiveView.qml"
        self.assertTrue(path.is_file(), "missing shared retained-live consumer")
        return path.read_text(encoding="utf-8")

    def test_shared_consumer_uses_only_absolute_readonly_frontdoor(self):
        source = self.shared()
        self.assertIn('import "Model.js" as Model', source)
        self.assertIn("statusSnapshot", source)
        self.assertIn("Model.liveWorkspaceView", source)
        self.assertIn("Model.liveWorkspaceSummary", source)
        self.assertIn('"/.local/bin/sia"', source)
        self.assertRegex(source, r'"live"\s*,\s*"--json"')
        self.assertNotIn("FileView", source)
        self.assertNotIn("/.gbrain", source)
        self.assertNotIn("live-generations/", source)
        self.assertNotRegex(source, r'\[\s*[\'"](?:sh|bash|sia)[\'"]')

    def test_process_lifecycle_clears_previous_view_and_serializes_requests(self):
        source = self.shared()
        refresh = _qml_function(source, "refresh")
        invalidate = _qml_function(source, "invalidate")
        settle = _qml_function(source, "settle")
        apply_result = _qml_function(source, "applyResult")
        self.assertRegex(invalidate, r"=\s*null")
        self.assertIn("invalidate", refresh)
        self.assertIn("running", refresh)
        self.assertIn("return", refresh)
        self.assertIn("invalidate", apply_result)
        self.assertIn("statusSnapshot", apply_result)
        self.assertIn("outDone", settle)
        self.assertIn("errDone", settle)
        self.assertIn("exited", settle)
        self.assertIn("outOverflow", settle)
        self.assertIn("errOverflow", settle)
        self.assertIn("exitCode", settle)
        self.assertIn("onStatusSnapshotChanged", source)
        self.assertIn("onEnabledChanged", source)
        self.assertIn("onRunningChanged", source)
        self.assertIn("onExited", source)
        self.assertIn("onStarted", source)
        self.assertIn("onStreamFinished", source)
        self.assertIn("responseMaxLength", source)
        self.assertIn("Timer", source)

    def test_cockpit_and_bar_consume_shared_live_view_not_compatibility_attention(self):
        panel = _read("Panel.qml")
        cockpit = _read("Cockpit.qml")
        for source in (panel, cockpit):
            self.assertIn("LiveView {", source)
            component = _qml_element(source, "id: liveLoopView")
            self.assertIn("statusSnapshot:", component)
            self.assertIn("statusLoadValid", component)
            self.assertIn("releaseLifecycle", component)
            self.assertIn('"ready"', component)
            self.assertIn("liveLoopView.summary", source)
        component = _qml_element(cockpit, "id: liveLoopView")
        self.assertIn("opened", component)
        self.assertIn("!root.playing", component)
        self.assertIn("liveLoopView.display", cockpit)
        self.assertIn("selected_sources", cockpit)
        self.assertIn("selection", cockpit)
        self.assertIn("expires_at", cockpit)
        self.assertNotIn("root.currentStatus.workspace", cockpit)
        self.assertNotIn('" OF 7"', cockpit)
        tooltip = _qml_function(panel, "tooltip")
        self.assertIn("liveLoopView.summary", tooltip)
        # Existing honest product boundary remains close to the new view.
        self.assertIn("not a biological brain", tooltip)


if __name__ == "__main__":
    unittest.main()
