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
  property var installCompletion: null
  property var continuity: null
  property bool statusResolved: false
  property bool statusLoadValid: false
  property bool installCompletionResolved: false
  property bool stale: true
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
  readonly property string runtimeLifecycle:
    Model.runtimeLifecycle(root.statusLoadValid ? root.status : null,
                           root.pluginVersion)
  readonly property string releaseLifecycle:
    !root.statusResolved || !root.installCompletionResolved ? "checking"
      : Model.guidedLifecycle(root.statusLoadValid ? root.status : null,
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
    if (root.continuity) {
      var tone = Model.continuityTone(root.continuity.state)
      if (tone === "danger") return root.urgentColor
      if (tone === "busy") return Color.accent
    }
    return root.stateColor()
  }

  function continuityText() {
    if (!root.continuity) return "continuity status unavailable"
    var label = Model.continuityStateLabel(root.continuity.state)
      .toLowerCase()
    var detail = String(root.continuity.detail || "").trim()
    return detail !== "" ? label + " — " + detail : label
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
      if (!Model.residentStatusShape(parsed)) {
        root.statusLoadValid = false
        return
      }
      root.status = parsed
      root.statusLoadValid = true
      const ts = Date.parse(parsed.ts)
      root.stale = !(ts > 0) ||
        (Date.now() - ts) > root.staleAfterSec * 1000
    } catch (e) {
      root.statusLoadValid = false
      /* mid-replace read; keep last-known-good pixels, but fail the gate */
    }
  }

  function applyContinuity(text) {
    try {
      const parsed = JSON.parse(text)
      if (Model.validContinuityStatus(parsed)) root.continuity = parsed
    } catch (e) { /* mid-replace read; keep last-known-good */ }
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
        const ts = Date.parse(root.status.ts)
        root.stale = !(ts > 0) ||
          (root.nowMs - ts) > root.staleAfterSec * 1000
      }
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
         && Model.continuityBarMark(root.continuity) !== ""
         ? " " + Model.continuityBarMark(root.continuity) : "")
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
