// Shared read-only consumer for the retained controller-source live view.
// The CLI rejoins source authority. Model.js validates a display contract;
// neither QML nor a represented digest authenticates a live generation.
// Inspection never selects a workspace or acknowledges a consumer.

import QtQuick
import Quickshell
import Quickshell.Io
import "Model.js" as Model

Scope {
  id: root

  property var statusSnapshot: null
  property bool enabled: false
  property real staleAfterSec: Model.staleAfterDefaultSec()
  property real nowMs: Date.now()
  readonly property var display: root.enabled
    ? Model.liveWorkspaceView(root.rawView, root.statusSnapshot,
                              root.nowMs, root.staleAfterSec)
    : null
  readonly property string summary: Model.liveWorkspaceSummary(root.display)

  // The CLI independently bounds UTF-8 output at its source. These ceilings
  // bound retained QML response strings; overflows are discarded wholesale,
  // never parsed as a prefix or displayed as a partial view.
  readonly property int responseMaxLength: 16777216
  readonly property int errorResponseMaxLength: 65536
  readonly property int pollInterval: 60000

  property var rawView: null
  property string unavailableReason: "not-requested"
  property bool componentReady: false
  property bool checking: false
  property bool rereadPending: false
  property string attemptStatusKey: ""
  property string outText: ""
  property string errText: ""
  property int exitCode: 0
  property bool exited: false
  property bool outDone: false
  property bool errDone: false
  property bool outOverflow: false
  property bool errOverflow: false
  property bool launchPending: false
  property bool startedForAttempt: false

  function statusKey(snapshot) {
    if (!Model.residentStatusShape(snapshot)) return ""
    return JSON.stringify([
      snapshot.publication_id, snapshot.pulse_seq, snapshot.ts])
  }

  function invalidate(reason) {
    root.rawView = null
    root.unavailableReason = typeof reason === "string"
      ? reason : "view-unavailable"
  }

  function refresh() {
    root.invalidate("refreshing")
    if (!root.componentReady) return
    var key = root.statusKey(root.statusSnapshot)
    // Unchanged-key polling cannot supersede its own slow response. A real
    // invalidation is sticky until this child finishes, even if the original
    // key or enabled state is later restored before its callbacks arrive.
    if (root.checking || liveProc.running) {
      if (!root.enabled || key === "" || key !== root.attemptStatusKey)
        root.rereadPending = true
      return
    }
    if (!root.enabled || key === "") {
      root.rereadPending = false
      root.unavailableReason = !root.enabled
        ? "inspection-disabled" : "status-unavailable"
      return
    }
    // One child per component. Superseding changes coalesce into a later
    // read only after all exit/stream callbacks have retired this attempt.
    root.rereadPending = false
    root.attemptStatusKey = key
    root.outText = ""
    root.errText = ""
    root.exitCode = 0
    root.exited = false
    root.outDone = false
    root.errDone = false
    root.outOverflow = false
    root.errOverflow = false
    root.launchPending = true
    root.startedForAttempt = false
    root.checking = true
    liveProc.running = true
  }

  function applyResult(text, requestedStatusKey) {
    root.invalidate("view-unavailable")
    if (!root.enabled || typeof text !== "string" || text.length === 0
        || text.length > root.responseMaxLength
        || requestedStatusKey === ""
        || requestedStatusKey !== root.statusKey(root.statusSnapshot)) return
    try {
      var parsed = JSON.parse(text)
      root.nowMs = Date.now()
      var admittedDisplay = Model.liveWorkspaceView(
        parsed, root.statusSnapshot, root.nowMs, root.staleAfterSec)
      if (admittedDisplay === null) return
      root.rawView = parsed
      root.unavailableReason = ""
    } catch (error) {
      root.invalidate("invalid-live-response")
    }
  }

  function fail(reason) {
    root.checking = false
    root.launchPending = false
    root.rereadPending = false
    root.outText = ""
    root.errText = ""
    root.invalidate(reason)
  }

  function settle() {
    if (!root.checking || !root.exited || !root.outDone || !root.errDone
        || liveProc.running) return
    root.checking = false
    root.launchPending = false
    if (!root.enabled || root.rereadPending
        || root.attemptStatusKey !== root.statusKey(root.statusSnapshot)) {
      root.rereadPending = false
      root.outText = ""
      root.errText = ""
      root.invalidate("superseded-live-response")
      if (root.enabled) Qt.callLater(function() { root.refresh() })
      return
    }
    if (root.exitCode === 0 && !root.outOverflow && !root.errOverflow) {
      root.applyResult(root.outText, root.attemptStatusKey)
      root.outText = ""
      root.errText = ""
    } else {
      root.fail(root.outOverflow || root.errOverflow
        ? "live-response-overflow" : "live-command-failed")
    }
  }

  onStatusSnapshotChanged: root.refresh()
  onEnabledChanged: root.refresh()
  onDisplayChanged: {
    // A clock crossing the freshness horizon or a generation mismatch also
    // withdraws the stored object; it cannot reappear as last-good pixels.
    if (root.display === null && root.rawView !== null)
      root.invalidate("display-no-longer-current")
  }
  Component.onCompleted: {
    root.componentReady = true
    root.refresh()
  }

  Process {
    id: liveProc
    command: [(Quickshell.env("HOME") || "") + "/.local/bin/sia",
              "live", "--json"]

    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var output = String(text || "")
        root.outOverflow = output.length > root.responseMaxLength
        root.outText = root.outOverflow ? "" : output
        output = ""
        root.outDone = true
        root.settle()
      }
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var output = String(text || "")
        root.errOverflow = output.length > root.errorResponseMaxLength
        root.errText = root.errOverflow ? "" : output
        output = ""
        root.errDone = true
        root.settle()
      }
    }
    onStarted: {
      root.invalidate("reading-live-view")
      root.startedForAttempt = true
      root.launchPending = false
    }
    onRunningChanged: {
      if (!running && root.launchPending && !root.startedForAttempt)
        root.fail("live-command-start-failed")
      else if (!running) root.settle()
    }
    onExited: function(code) {
      root.exitCode = code
      root.exited = true
      root.settle()
    }
  }

  Timer {
    interval: root.pollInterval
    running: root.componentReady && root.enabled
    repeat: true
    onTriggered: root.refresh()
  }
  Timer {
    interval: 1000
    running: root.componentReady && root.enabled
    repeat: true
    onTriggered: root.nowMs = Date.now()
  }
}
