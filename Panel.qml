// SIA bar widget — brain glyph + today's event count, colored by brain
// state. Clicking summons the full-screen SIA cockpit (Cockpit.qml).
// Pixels only: reads the brainstem and continuity workers' published state.

import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

BarWidget {
  id: root
  moduleName: "khephri.sia"

  readonly property color fg: bar ? bar.foreground : Color.foreground
  readonly property color urgentColor: bar ? bar.urgent : Color.urgent

  property var status: null
  property var runtimeEvidence: null
  property var installCompletion: null
  property var continuity: null
  property bool statusResolved: false
  property bool statusLoadValid: false
  property bool installCompletionResolved: false
  property bool stale: true
  // Continuity gets its own clock, separate from the brainstem pulse: the
  // two subsystems publish on completely different cadences and a single
  // `stale` flag would have to pick one of them to lie about.
  property bool continuityStale: true
  property real nowMs: Date.now()

  readonly property string statusPath:
    (Quickshell.env("HOME") || "") + "/.local/state/sia/status.json"
  readonly property string continuityPath:
    (Quickshell.env("HOME") || "")
      + "/.local/state/sia-continuity/status.json"
  readonly property string installCompletionPath:
    (Quickshell.env("HOME") || "")
      + "/.local/state/sia/managed-install/first-light.json"
  readonly property string pluginVersion: Model.releaseVersion()
  // There is deliberately no `runtimeLifecycle` property here.  The bar used
  // to compute one and never read it; the only lifecycle this widget may act
  // on is releaseLifecycle, which also weighs the first-light completion
  // record.  A second, laxer lifecycle sitting unread beside it was an
  // invitation to bind the wrong one.
  readonly property string releaseLifecycle:
    !root.statusResolved || !root.installCompletionResolved ? "checking"
      : Model.guidedLifecycle(root.runtimeEvidence,
                              root.installCompletion, root.pluginVersion)
  readonly property string brainState:
    releaseLifecycle !== "ready" ? releaseLifecycle
      : stale ? "stale" : (status && status.state ? status.state : "unknown")
  readonly property int eventsToday:
    status && status.events_today ? status.events_today : 0
  readonly property real staleAfterSec:
    Model.validStaleAfterSec(
      root.setting("staleAfterSec", Model.staleAfterDefaultSec()),
      Model.staleAfterDefaultSec())
  readonly property string cockpitWorkspace:
    root.normalizedSetting("cockpitWorkspace")

  function setting(name, fallback) {
    var value = settings ? settings[name] : undefined
    return value === undefined || value === null ? fallback : value
  }

  function normalizedSetting(name) {
    var value = root.setting(name, "")
    return typeof value === "string" ? value.trim() : ""
  }

  function stateColor() {
    if (root.releaseLifecycle !== "ready") return Color.accent
    if (root.stale) return Qt.alpha(root.fg, 0.4)
    if (root.brainState === "failed") return root.urgentColor
    if (root.brainState === "degraded") return Qt.alpha(root.urgentColor, 0.75)
    if (root.brainState === "thinking") return Color.accent
    return root.fg
  }

  function indicatorColor() {
    // A stale record may not tint the glyph.  Both non-default tones are
    // claims about right now — "danger" that something is wrong, "busy" that
    // work is under way — and neither survives the worker going silent.
    if (root.continuity && !root.continuityStale) {
      var tone = Model.continuityTone(root.continuity.state)
      if (tone === "danger") return root.urgentColor
      if (tone === "busy") return Color.accent
    }
    return root.stateColor()
  }

  function continuityBarMark() {
    // Withdraw the mark to "unknown" rather than repaint the last state: the
    // mark is the operator's at-a-glance recovery signal and an empty one
    // reads as "verified, nothing to do".
    if (root.continuityStale) return "?"
    return Model.continuityBarMark(root.continuity)
  }

  function continuityText() {
    if (!root.continuity) return "continuity status unavailable"
    var label = Model.continuityStateLabel(root.continuity.state)
      .toLowerCase()
    var detail = String(root.continuity.detail || "").trim()
    var text = detail !== "" ? label + " — " + detail : label
    if (root.continuityStale)
      return "continuity not reporting · last published " + text
    return text
  }

  function refreshContinuityStale() {
    root.continuityStale = Model.continuityStale(
      root.continuity, root.nowMs, Model.continuityStaleAfterSec())
  }

  function tooltip() {
    if (root.releaseLifecycle === "checking")
      return "SIA — checking the resident installation"
    if (root.releaseLifecycle === "setup")
      return "SIA — first light required · click to install"
    if (root.releaseLifecycle === "installing")
      return "SIA — first light is in progress · click for status or retry"
    if (root.releaseLifecycle === "repair")
      return "SIA — installation state needs repair · click to continue safely"
    if (root.releaseLifecycle === "ahead") {
      var resident = root.status && typeof root.status.version === "string"
        ? root.status.version : "newer runtime"
      return "SIA — resident " + resident + " is newer than cockpit "
        + root.pluginVersion + " · update the plugin checkout"
    }
    if (root.releaseLifecycle === "update") {
      var installed = root.status && typeof root.status.version === "string"
        ? root.status.version : "legacy runtime"
      return "SIA — finish update " + installed + " → "
        + root.pluginVersion + " · click to continue"
    }
    var brain = root.cockpitWorkspace !== ""
      ? "SIA — cockpit locked to workspace " + root.cockpitWorkspace
        + " · return there to unlock"
      : root.stale
        ? "SIA — brainstem not reporting"
        : "SIA — " + root.brainState + " · " + root.eventsToday
          + " events today"
    return brain + " · " + root.continuityText()
      + " · click for cockpit · right-click for continuity"
  }

  function applyStatus(text) {
    try {
      const parsed = JSON.parse(text)
      const valid = Model.residentStatusShape(parsed)
      root.runtimeEvidence = Model.runtimeLifecycleEvidence(
        parsed, valid, root.runtimeEvidence, root.pluginVersion)
      if (!valid) {
        root.statusLoadValid = false
        return
      }
      root.status = parsed
      root.statusLoadValid = true
      root.stale = Model.timestampStale(
        parsed.ts, Date.now(), root.staleAfterSec)
    } catch (e) {
      root.runtimeEvidence = Model.runtimeLifecycleEvidence(
        null, false, root.runtimeEvidence, root.pluginVersion)
      root.statusLoadValid = false
      /* mid-replace read; keep last-known-good pixels, but fail the gate */
    }
  }

  function applyContinuity(text) {
    try {
      const parsed = JSON.parse(text)
      if (Model.validContinuityStatus(parsed)) root.continuity = parsed
    } catch (e) { /* mid-replace read; keep last-known-good */ }
    // Re-clock on every read, accepted or rejected.  A file that keeps being
    // rewritten with bytes this widget refuses is exactly as unreported as
    // one that stopped being written at all.
    root.refreshContinuityStale()
  }

  function applyInstallCompletion(text) {
    try {
      const parsed = JSON.parse(text)
      root.installCompletion = parsed
    } catch (e) { root.installCompletion = null }
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  FileView {
    id: statusFile
    path: root.statusPath
    watchChanges: true
    printErrors: false
    onLoaded: {
      root.applyStatus(text())
      root.statusResolved = true
    }
    onLoadFailed: {
      root.runtimeEvidence = Model.runtimeLifecycleEvidence(
        null, false, root.runtimeEvidence, root.pluginVersion)
      root.status = null
      root.statusLoadValid = false
      root.stale = true
      root.statusResolved = true
    }
    onFileChanged: {
      // Keep the last validated generation while the atomic refresh settles;
      // the load callbacks still fail closed on missing or invalid status.
      statusApply.restart()
    }
  }
  Timer { id: statusApply; interval: 150; repeat: false
          onTriggered: statusFile.reload() }

  FileView {
    id: continuityFile
    path: root.continuityPath
    watchChanges: true
    printErrors: false
    onLoaded: root.applyContinuity(text())
    onLoadFailed: {
      // The brain status has had this discipline since the beginning;
      // continuity did not, so a deleted or unreadable status file left the
      // last good record painted forever and the bar went on reassuring an
      // operator about a subsystem that was no longer there.  Drop to
      // unknown: a missing file is not evidence of a healthy copy.
      root.continuity = null
      root.continuityStale = true
    }
    onFileChanged: continuityApply.restart()
  }

  FileView {
    id: installCompletionFile
    path: root.installCompletionPath
    watchChanges: true
    printErrors: false
    onLoaded: {
      root.applyInstallCompletion(text())
      root.installCompletionResolved = true
    }
    onLoadFailed: {
      root.installCompletion = null
      root.installCompletionResolved = true
    }
    onFileChanged: {
      // A real first-light change immediately restores the install barrier;
      // the settled callback decides which lifecycle may be shown next.
      root.installCompletionResolved = false
      installCompletionApply.restart()
    }
  }
  Timer { id: installCompletionApply; interval: 150; repeat: false
          onTriggered: installCompletionFile.reload() }
  Timer { id: continuityApply; interval: 150; repeat: false
          onTriggered: {
            continuityFile.reload()
            root.applyContinuity(continuityFile.text())
          } }

  Timer {
    interval: 5000; running: true; repeat: true
    onTriggered: {
      root.nowMs = Date.now()
      if (root.status) {
        root.stale = Model.timestampStale(
          root.status.ts, root.nowMs, root.staleAfterSec)
      }
      // Continuity crosses its horizon without any file changing, so the
      // tick has to ask, not wait to be told.
      root.refreshContinuityStale()
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: String.fromCodePoint(0xF09D1)
      + (root.releaseLifecycle === "checking" ? " CHECK"
         : root.releaseLifecycle === "setup" ? " SETUP"
         : root.releaseLifecycle === "installing" ? " INSTALL"
         : root.releaseLifecycle === "update" ? " UPDATE"
         : root.releaseLifecycle === "repair" ? " REPAIR"
         : root.releaseLifecycle === "ahead" ? " AHEAD"
         : root.eventsToday > 0 && !root.stale ? " " + root.eventsToday : "")
      + (root.releaseLifecycle === "ready"
         && root.continuityBarMark() !== ""
         ? " " + root.continuityBarMark() : "")
    slotSize: Style.bar.statusSlot
    // the stock slot is one-glyph wide; grow with the painted count so the
    // neighbouring widget can't paint over our number
    fixedWidth: vertical ? -1
      : Math.max(slotSize, glyphPaintedWidth + Style.spaceReal(8))
    fontSize: Style.font.caption
    foreground: root.indicatorColor()
    tooltipText: root.tooltip()
    onPressed: function(buttonCode) {
      if (!root.bar || !root.bar.shell) return
      if (buttonCode === Qt.RightButton) {
        root.bar.shell.summon("khephri.sia", "{\"mode\":\"continuity\"}")
        return
      }
      root.bar.shell.summon("khephri.sia", "{}")
    }
  }
}
