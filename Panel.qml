// SIA bar widget — brain glyph + today's event count, colored by brain
// state. Clicking summons the full-screen SIA cockpit (Cockpit.qml).
// Pixels only: reads ~/.local/state/sia/status.json.

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
  property bool stale: true
  property real nowMs: Date.now()

  readonly property string statusPath:
    (Quickshell.env("HOME") || "") + "/.local/state/sia/status.json"
  readonly property string brainState:
    stale ? "stale" : (status && status.state ? status.state : "unknown")
  readonly property int eventsToday:
    status && status.events_today ? status.events_today : 0
  readonly property real staleAfterSec:
    Model.validStaleAfterSec(
      root.setting("staleAfterSec", Model.staleAfterDefaultSec()),
      Model.staleAfterDefaultSec())

  function setting(name, fallback) {
    var value = settings ? settings[name] : undefined
    return value === undefined || value === null ? fallback : value
  }

  function stateColor() {
    if (root.stale) return Qt.alpha(root.fg, 0.4)
    if (root.brainState === "failed") return root.urgentColor
    if (root.brainState === "degraded") return Qt.alpha(root.urgentColor, 0.75)
    if (root.brainState === "thinking") return Color.accent
    return root.fg
  }

  function applyStatus(text) {
    try {
      const parsed = JSON.parse(text)
      root.status = parsed
      const ts = Date.parse(parsed.ts)
      root.stale = !(ts > 0) ||
        (Date.now() - ts) > root.staleAfterSec * 1000
    } catch (e) { /* mid-replace read; keep last-known-good */ }
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  FileView {
    id: statusFile
    path: root.statusPath
    watchChanges: true
    printErrors: false
    onLoaded: root.applyStatus(text())
    onFileChanged: statusApply.restart()
  }
  Timer { id: statusApply; interval: 150; repeat: false
          onTriggered: { statusFile.reload(); root.applyStatus(statusFile.text()) } }

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
      + (root.eventsToday > 0 && !root.stale ? " " + root.eventsToday : "")
    slotSize: Style.bar.statusSlot
    // the stock slot is one-glyph wide; grow with the painted count so the
    // neighbouring widget can't paint over our number
    fixedWidth: vertical ? -1
      : Math.max(slotSize, glyphPaintedWidth + Style.spaceReal(8))
    fontSize: Style.font.caption
    foreground: root.stateColor()
    tooltipText: root.stale
      ? "SIA — brainstem not reporting"
      : "SIA — " + root.brainState + " · " + root.eventsToday
        + " events today · click for the cockpit"
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) { statusFile.reload(); return }
      if (root.bar && root.bar.shell)
        root.bar.shell.summon("khephri.sia", "{}")
    }
  }
}
