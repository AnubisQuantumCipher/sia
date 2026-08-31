// SIA COCKPIT — full-screen mission control for the Omarchy Brain.
// Overlay kind: summoned from the bar widget or SUPER+SHIFT+B, dismissed
// with Esc / ✕ / click on the header brand. Pixels only — renders the
// brainstem's snapshots; the brain is gbrain + the signed corpus.

import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import "Model.js" as Model

Item {
  id: root

  property var shell: ({})
  property var manifest: ({})
  property bool opened: false

  property var status: null
  property var graph: null
  property var thoughts: []
  property bool stale: true
  property real nowMs: Date.now()
  property string hoverId: ""
  property string selectedId: ""
  property var hiddenKinds: ({})
  property real revealT: 1.0
  property bool playing: false
  property string verifyMsg: ""
  property bool verifyOk: false
  property string graphBoundary: ""
  property string statusBoundary: ""
  property bool readyChecked: false
  property bool readyOk: false
  property string readyDetail: ""

  readonly property string effId: hoverId !== "" ? hoverId : selectedId
  readonly property string statePath:
    (Quickshell.env("HOME") || "") + "/.local/state/sia"
  readonly property string fontFamily: Style.font.family
  readonly property color fg: Color.foreground
  readonly property color accent: Color.accent
  readonly property color urgent: Color.urgent

  readonly property var pal: ({
    cortex:  root.fg,
    organ:   root.accent,
    day:     Qt.alpha(root.fg, 0.78),
    thought: Qt.lighter(root.accent, 1.35),
    record:  Qt.alpha(root.fg, 0.5),
    skill:   Qt.darker(root.accent, 1.45),
    urgent:  root.urgent
  })

  readonly property string brainState:
    stale ? "stale" : (status && status.state ? status.state : "unknown")
  readonly property int eventsToday:
    status && status.events_today ? status.events_today : 0
  readonly property var snap:
    graph && graph.snapshot ? graph.snapshot : null
  readonly property real staleAfterSec: configuredStaleAfterSec()

  function isNonNegativeCount(value) {
    return typeof value === "number" && isFinite(value)
      && Math.floor(value) === value && value >= 0
  }

  function isPlainRecord(value) {
    return !!value && typeof value === "object" && !Array.isArray(value)
  }

  function validMindSummary(mind) {
    if (!root.isPlainRecord(mind)) return false
    var fields = ["nodes", "edges", "decay_active", "decay_demoted",
                  "rehearsal_eligible", "rehearsal_due", "pinned"]
    for (var i = 0; i < fields.length; i++)
      if (!root.isNonNegativeCount(mind[fields[i]])) return false
    return true
  }

  function validAgentRelay(relay) {
    if (!root.isPlainRecord(relay)) return false
    var fields = ["materialized", "refused", "acknowledged"]
    for (var i = 0; i < fields.length; i++)
      if (!root.isNonNegativeCount(relay[fields[i]])) return false
    return true
  }

  function validStatusSnapshot(snapshot) {
    return root.isPlainRecord(snapshot)
      && typeof snapshot.ts === "string" && typeof snapshot.state === "string"
      && root.projectionDebtKnownFor(snapshot)
      && root.validMindSummary(snapshot.mind)
      && root.validAgentRelay(snapshot.agent_queue)
  }

  function graphHasNode(id) {
    return root.nodeById(id) !== null
  }

  function projectionDebtKeys() {
    var debt = root.status && root.status.projection_debt
      ? root.status.projection_debt : null
    if (!debt || typeof debt !== "object") return []
    var keys = []
    for (var key in debt) {
      var value = debt[key]
      if ((typeof value === "string" && value.trim() !== "")
          || (typeof value !== "string" && !!value))
        keys.push(key)
    }
    return keys.sort()
  }

  function projectionDebtKnown() {
    return root.projectionDebtKnownFor(root.status)
  }

  function projectionDebtKnownFor(snapshot) {
    if (!snapshot || !root.isPlainRecord(snapshot.projection_debt))
      return false
    var debt = snapshot.projection_debt
    return typeof debt.graph === "string"
      && typeof debt.consolidation === "string"
  }

  function clearReadyCheck() {
    root.readyChecked = false
    root.readyOk = false
    root.readyDetail = ""
  }

  function projectionDebtDetail() {
    var keys = root.projectionDebtKeys()
    if (!keys.length) return ""
    var debt = root.status.projection_debt
    var parts = []
    for (var i = 0; i < keys.length; i++)
      parts.push(keys[i] + ": " + String(debt[keys[i]]))
    return parts.join(" · ")
  }

  function graphSnapshotText() {
    if (root.graphBoundary !== "") return root.graphBoundary
    if (!root.graph || !root.graph.ts) return "no graph snapshot"
    var complete = root.snap && root.snap.complete === true
    return "graph published " + Model.timeAgo(root.graph.ts, root.nowMs)
      + " · " + (complete ? "complete" : "partial")
  }

  function ledgerTransitionText() {
    var transition = root.status && root.status.ledger_transition
      ? root.status.ledger_transition : null
    if (!transition || !transition.state) return "ledger transition unknown"
    return "ledger " + transition.state
  }

  function configuredStaleAfterSec() {
    var fallback = Model.staleAfterDefaultSec()
    if (root.manifest && root.manifest.barWidget
        && root.manifest.barWidget.defaults)
      fallback = Model.validStaleAfterSec(
        root.manifest.barWidget.defaults.staleAfterSec, fallback)

    const config = root.shell ? root.shell.shellConfig : null
    const layout = config && config.bar ? config.bar.layout : null
    const sections = ["left", "center", "right"]
    if (layout) {
      for (var s = 0; s < sections.length; s++) {
        const entries = layout[sections[s]]
        if (!Array.isArray(entries)) continue
        for (var i = 0; i < entries.length; i++) {
          const entry = entries[i]
          const id = Util.canonicalWidgetId(String(
            entry && entry.id !== undefined ? entry.id : entry || ""))
          if (id === "khephri.sia")
            return Model.validStaleAfterSec(
              entry && entry.staleAfterSec, fallback)
        }
      }
    }

    const plugins = config ? config.plugins : null
    if (Array.isArray(plugins)) {
      for (var p = 0; p < plugins.length; p++) {
        const entry = plugins[p]
        if (entry && Util.canonicalWidgetId(String(entry.id || ""))
            === "khephri.sia")
          return Model.validStaleAfterSec(entry.staleAfterSec, fallback)
      }
    }
    return fallback
  }

  function stateColor() {
    if (root.stale) return Qt.alpha(root.fg, 0.4)
    if (root.brainState === "failed") return root.urgent
    if (root.brainState === "degraded") return Qt.alpha(root.urgent, 0.75)
    if (root.brainState === "thinking") return root.accent
    return root.fg
  }

  function nodeById(id) {
    if (!root.graph || id === "") return null
    for (var i = 0; i < root.graph.nodes.length; i++)
      if (root.graph.nodes[i].id === id) return root.graph.nodes[i]
    return null
  }

  function nodeVisible(n) {
    if (root.hiddenKinds[Model.kindKey(n)]) return false
    return (n.tsNorm || 0) <= root.revealT
  }

  function toggleKind(role) {
    if (role === "cortex") return
    var h = {}
    for (var k in root.hiddenKinds) h[k] = root.hiddenKinds[k]
    h[role] = !h[role]
    root.hiddenKinds = h
    graphCanvas.requestPaint()
  }

  function open(payloadJson) {
    opened = true
    verifyMsg = ""
    verifyOk = false
    clearReadyCheck()
    statusFile.reload(); graphFile.reload(); thoughtsFile.reload()
    if (root.graph && graphCanvas.width > 0)
      Model.syncGraph(root.graph, graphCanvas.width, graphCanvas.height)
    Qt.callLater(function() {
      keyCatcher.forceActiveFocus()
      graphCanvas.requestPaint()
    })
  }

  function dismiss() {
    opened = false
    playing = false
    revealT = 1.0
    hoverId = ""
    if (readyProc.running) readyProc.running = false
    clearReadyCheck()
    if (shell && typeof shell.hide === "function") shell.hide("khephri.sia")
  }

  function applyStatus(text) {
    try {
      const parsed = JSON.parse(text)
      if (!root.validStatusSnapshot(parsed)) {
        root.statusBoundary = root.status
          ? "last good status; latest status rejected" : "no valid status"
        return
      }
      root.status = parsed
      root.statusBoundary = ""
      root.clearReadyCheck()
      const ts = Date.parse(parsed.ts)
      root.stale = !(ts > 0) ||
        (Date.now() - ts) > root.staleAfterSec * 1000
    } catch (e) {
      root.statusBoundary = root.status
        ? "last good status; latest status rejected" : "no valid status"
    }
  }

  function applyGraph(text) {
    try {
      const g = JSON.parse(text)
      if (!g || !Array.isArray(g.nodes) || !Array.isArray(g.edges)
          || g.pages_total === undefined || typeof g.ts !== "string"
          || !root.isPlainRecord(g.snapshot)
          || typeof g.snapshot.complete !== "boolean"
          || !Array.isArray(g.snapshot.failed_ops)) {
        root.graphBoundary = root.graph
          ? "last good graph; latest graph rejected" : "no valid graph snapshot"
        return
      }
      root.graph = g
      root.graphBoundary = ""
      root.clearReadyCheck()
      if (root.selectedId !== "" && !root.graphHasNode(root.selectedId))
        root.selectedId = ""
      if (root.hoverId !== "" && !root.graphHasNode(root.hoverId))
        root.hoverId = ""
      if (graphCanvas.width > 0)
        Model.syncGraph(g, graphCanvas.width, graphCanvas.height)
      graphCanvas.requestPaint()
    } catch (e) {
      root.graphBoundary = root.graph
        ? "last good graph; latest graph rejected" : "no valid graph snapshot"
    }
  }

  function applyThoughts(text) {
    try {
      const t = JSON.parse(text)
      root.thoughts = (t.thoughts || []).slice(-40).reverse()
    } catch (e) { }
  }

  FileView {
    id: statusFile
    path: root.statePath + "/status.json"
    watchChanges: true
    printErrors: false
    onLoaded: root.applyStatus(text())
    onFileChanged: statusApply.restart()
  }
  Timer { id: statusApply; interval: 150; repeat: false
          onTriggered: { statusFile.reload(); root.applyStatus(statusFile.text()) } }

  FileView {
    id: graphFile
    path: root.statePath + "/graph.json"
    watchChanges: true
    printErrors: false
    onLoaded: root.applyGraph(text())
    onFileChanged: graphApply.restart()
  }
  Timer { id: graphApply; interval: 200; repeat: false
          onTriggered: { graphFile.reload(); root.applyGraph(graphFile.text()) } }

  FileView {
    id: thoughtsFile
    path: root.statePath + "/thoughts.json"
    watchChanges: true
    printErrors: false
    onLoaded: root.applyThoughts(text())
    onFileChanged: thoughtsApply.restart()
  }
  Timer { id: thoughtsApply; interval: 200; repeat: false
          onTriggered: { thoughtsFile.reload(); root.applyThoughts(thoughtsFile.text()) } }

  Timer {
    interval: 1000; running: root.opened; repeat: true
    onTriggered: {
      root.nowMs = Date.now()
      if (root.status) {
        const ts = Date.parse(root.status.ts)
        root.stale = !(ts > 0) ||
          (root.nowMs - ts) > root.staleAfterSec * 1000
      }
    }
  }

  Process {
    id: verifyProc
    command: [(Quickshell.env("HOME") || "") + "/.local/bin/sia", "verify"]
    stdout: StdioCollector { waitForEnd: true }
    onExited: function(code) {
      root.verifyOk = code === 0
      root.verifyMsg = code === 0
        ? "all registered chains re-verified ✓"
        : "CHAIN VERIFICATION INCOMPLETE"
    }
  }

  // `sia ready` is the only live memory-readiness predicate. Status and graph
  // are intentionally last-published snapshots, so this process runs solely
  // on an explicit cockpit action and never infers readiness from a snapshot.
  Process {
    id: readyProc
    property string outText: ""
    property string errText: ""
    property int exitCode: 0
    property bool exited: false
    property bool outDone: false
    property bool errDone: false
    property bool launchFailed: false
    command: [(Quickshell.env("HOME") || "") + "/.local/bin/sia", "ready"]
    function settle() {
      if (launchFailed || !exited || !outDone || !errDone) return
      var detail = (outText + "\n" + errText)
        .replace(/^\s+|\s+$/g, "")
      root.readyChecked = true
      root.readyOk = exitCode === 0
      root.readyDetail = detail || (root.readyOk
        ? "sia ready returned success" : "sia ready returned a refusal")
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        readyProc.outText = String(text || "")
        readyProc.outDone = true
        readyProc.settle()
      }
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        readyProc.errText = String(text || "")
        readyProc.errDone = true
        readyProc.settle()
      }
    }
    onRunningChanged: if (running) {
      readyProc.outText = ""
      readyProc.errText = ""
      readyProc.exitCode = 0
      readyProc.exited = false
      readyProc.outDone = false
      readyProc.errDone = false
      readyProc.launchFailed = false
      root.clearReadyCheck()
    }
    onErrorOccurred: function(error) {
      if (readyProc.launchFailed) return
      readyProc.launchFailed = true
      root.readyChecked = true
      root.readyOk = false
      root.readyDetail = "could not start the local sia readiness command"
    }
    onExited: function(code) {
      readyProc.exitCode = code
      readyProc.exited = true
      readyProc.settle()
    }
  }

  PanelWindow {
    id: win
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: Color.background
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.namespace: "sia-cockpit"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive

    Item {
      id: keyCatcher
      anchors.fill: parent
      focus: true
      Keys.priority: Keys.BeforeItem
      Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Escape) { root.dismiss(); event.accepted = true }
        else if (event.key === Qt.Key_R) {
          if (root.playing) { root.playing = false; root.revealT = 1.0 }
          else { root.revealT = 0.0; root.playing = true }
          event.accepted = true
        }
      }

      // ---------------------------------------------------------- header
      Item {
        id: header
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: Style.space(16)
        height: Style.space(52)

        Row {
          anchors.left: parent.left
          anchors.top: parent.top
          spacing: Style.space(14)
          Text {
            textFormat: Text.PlainText
            renderType: Text.NativeRendering
            text: Model.brainGlyph() + "  SIA — THE OMARCHY BRAIN"
            color: root.fg
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
          }
          Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: stateText.implicitWidth + Style.space(16)
            height: stateText.implicitHeight + Style.space(6)
            radius: height / 2
            color: Qt.alpha(root.stateColor(), 0.12)
            border.color: Qt.alpha(root.stateColor(), 0.5)
            border.width: 1
            Text {
              textFormat: Text.PlainText
              renderType: Text.NativeRendering
              id: stateText
              anchors.centerIn: parent
              text: root.brainState.toUpperCase()
              color: root.stateColor()
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
            }
          }
          Text {
            textFormat: Text.PlainText
            renderType: Text.NativeRendering
            anchors.verticalCenter: parent.verticalCenter
            text: root.status
              ? "pulse " + root.status.pulse_seq + " · "
                + Model.timeAgo(root.status.ts, root.nowMs)
              : "no status"
            color: Qt.alpha(root.fg, 0.55)
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
          }
        }

        Row {
          anchors.right: parent.right
          anchors.top: parent.top
          spacing: Style.space(16)
          Text {
            textFormat: Text.PlainText
            renderType: Text.NativeRendering
            anchors.verticalCenter: parent.verticalCenter
            text: Qt.formatTime(new Date(root.nowMs), "HH:mm:ss")
            color: Qt.alpha(root.fg, 0.55)
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
          }
          Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: closeText.implicitWidth + Style.space(16)
            height: closeText.implicitHeight + Style.space(8)
            radius: Style.cornerRadius
            color: closeArea.containsMouse
              ? Qt.alpha(root.fg, 0.18) : Qt.alpha(root.fg, 0.08)
            border.color: Qt.alpha(root.fg, 0.25)
            border.width: 1
            Text {
              textFormat: Text.PlainText
              renderType: Text.NativeRendering
              id: closeText
              anchors.centerIn: parent
              text: "✕ close"
              color: root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
            MouseArea {
              id: closeArea
              anchors.fill: parent
              hoverEnabled: true
              onClicked: root.dismiss()
            }
          }
        }

        // Snapshot truth is intentionally separated from the explicit live
        // readiness probe below. This keeps a healthy-looking graph from
        // silently standing in for a memory-read authorization.
        Row {
          id: truthRibbon
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.bottom: parent.bottom
          spacing: Style.space(12)
          Text {
            textFormat: Text.PlainText
            renderType: Text.NativeRendering
            text: "PUBLISHED SNAPSHOT · " + root.graphSnapshotText()
            color: root.graphBoundary !== "" || (root.snap
              && root.snap.complete !== true)
              ? root.urgent : Qt.alpha(root.fg, 0.5)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            textFormat: Text.PlainText
            renderType: Text.NativeRendering
            text: root.ledgerTransitionText().toUpperCase()
            color: root.status && root.status.ledger_transition
              && root.status.ledger_transition.state === "pending"
              ? root.urgent
              : root.status && root.status.ledger_transition
                && root.status.ledger_transition.state === "signed"
                ? Qt.alpha(root.accent, 0.8) : Qt.alpha(root.fg, 0.5)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            textFormat: Text.PlainText
            renderType: Text.NativeRendering
            text: !root.projectionDebtKnown() ? "DEBT UNKNOWN"
              : root.projectionDebtKeys().length
                ? "DEBT · " + root.projectionDebtKeys().join(", ")
                : "DEBT CLEAR IN SNAPSHOT"
            color: !root.projectionDebtKnown()
              || root.projectionDebtKeys().length
                ? root.urgent : Qt.alpha(root.fg, 0.5)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
          Rectangle {
            width: readyText.implicitWidth + Style.space(14)
            height: readyText.implicitHeight + Style.space(6)
            radius: height / 2
            color: liveReadyArea.containsMouse
              ? Qt.alpha(root.fg, 0.16) : Qt.alpha(root.fg, 0.07)
            border.color: root.readyChecked
              ? Qt.alpha(root.readyOk ? root.accent : root.urgent, 0.65)
              : Qt.alpha(root.fg, 0.22)
            border.width: 1
            Text {
              id: readyText
              anchors.centerIn: parent
              textFormat: Text.PlainText
              renderType: Text.NativeRendering
              text: readyProc.running ? "checking live readiness…"
                : root.readyChecked
                  ? (root.readyOk ? "LIVE READY ✓" : "LIVE BLOCKED")
                  : "check live readiness"
              color: root.readyChecked
                ? (root.readyOk ? root.accent : root.urgent) : root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: root.readyChecked
            }
            MouseArea {
              id: liveReadyArea
              anchors.fill: parent
              hoverEnabled: true
              enabled: !readyProc.running
              onClicked: readyProc.running = true
            }
            // `sia ready` diagnostics cross a process boundary, so keep the
            // tooltip on the same plain-text rendering contract as snapshots.
            ToolTip {
              id: readyTooltip
              parent: liveReadyArea
              visible: liveReadyArea.containsMouse
                && root.readyDetail !== ""
              text: root.readyDetail
              x: Math.min(0, liveReadyArea.width - width)
              y: liveReadyArea.height + Style.space(4)
              contentItem: Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: readyTooltip.text
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
          }
        }
      }

      // ---------------------------------------------------------- footer
      Item {
        id: footer
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: Style.space(16)
        height: Style.space(20)
        Text {
          textFormat: Text.PlainText
          renderType: Text.NativeRendering
          id: keysHint
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          text: "hover = inspect · click = lock · R = replay · Esc = close · sia ask \"…\""
          color: Qt.alpha(root.fg, 0.4)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }
        Text {
          textFormat: Text.PlainText
          renderType: Text.NativeRendering
          anchors.left: parent.left
          anchors.right: keysHint.left
          anchors.rightMargin: Style.space(24)
          anchors.verticalCenter: parent.verticalCenter
          elide: Text.ElideRight
          text: {
            var th = root.status && root.status.thought ? root.status.thought : null
            return th && th.text
              ? Model.thoughtMark(th.kind) + "  [origin:"
                + (th.origin || "legacy-unlabeled") + "] " + th.text : ""
          }
          color: Qt.alpha(root.fg, 0.6)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }
      }

      // ---------------------------------------------------------- body
      Item {
        id: body
        anchors.top: header.bottom
        anchors.bottom: footer.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: Style.space(16)
        anchors.topMargin: Style.space(10)
        anchors.bottomMargin: Style.space(10)

        readonly property real gap: Style.space(12)
        readonly property real leftW: Style.space(230)
        readonly property real rightW: Style.space(300)

        // ================================================= LEFT: vitals
        Flickable {
          id: leftScroll
          width: body.leftW
          anchors.top: parent.top
          anchors.bottom: parent.bottom
          contentWidth: width
          contentHeight: leftPane.implicitHeight
          clip: true
          pixelAligned: true    // snap scroll to whole pixels — no text shimmer
          boundsBehavior: Flickable.StopAtBounds
          ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: leftPane
          width: leftScroll.width
          spacing: body.gap

          Rectangle {
            width: parent.width
            height: vitalsCol.implicitHeight + Style.space(20)
            radius: Style.cornerRadius
            color: Qt.alpha(root.fg, 0.04)
            border.color: Qt.alpha(root.fg, 0.10)
            border.width: 1
            Column {
              id: vitalsCol
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.margins: Style.space(10)
              spacing: Style.space(6)
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "VITALS"
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Grid {
                columns: 2
                columnSpacing: Style.space(14)
                rowSpacing: Style.space(2)
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "memories"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: root.status ? String(root.status.pages) : "—"
                       color: root.fg; font.bold: true
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "links"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: root.status ? String(root.status.graph_edges) : "—"
                       color: root.fg; font.bold: true
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "events today"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: String(root.eventsToday)
                       color: root.accent; font.bold: true
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "thoughts kept"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: String(root.thoughts.length)
                       color: root.fg; font.bold: true
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "mind traces"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: root.status && root.status.mind
                         ? root.status.mind.nodes + " · " + root.status.mind.edges + " bonds"
                         : "—"
                       color: root.fg; font.bold: true
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
              }

              Text {
                visible: !!(root.status && root.status.mind)
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "MEMORY LENS"
                topPadding: Style.space(6)
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Grid {
                id: memoryLens
                visible: !!(root.status && root.status.mind)
                columns: 2
                columnSpacing: Style.space(14)
                rowSpacing: Style.space(2)
                readonly property var mind:
                  root.status && root.status.mind ? root.status.mind : ({})
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "stability"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.caption }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: (memoryLens.mind.decay_active || 0) + " active · " + (memoryLens.mind.decay_demoted || 0) + " demoted"
                       color: root.fg; font.family: root.fontFamily; font.pixelSize: Style.font.caption }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "SM-2 review"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.caption }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: (memoryLens.mind.rehearsal_due || 0) + " due / " + (memoryLens.mind.rehearsal_eligible || 0) + " eligible"
                       color: (memoryLens.mind.rehearsal_due || 0) > 0 ? root.accent : root.fg
                       font.family: root.fontFamily; font.pixelSize: Style.font.caption }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "operator pins"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.caption }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: String(memoryLens.mind.pinned || 0)
                       color: root.fg; font.family: root.fontFamily; font.pixelSize: Style.font.caption }
              }
              Text {
                visible: !!(root.status && root.status.mind)
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                width: vitalsCol.width
                wrapMode: Text.WordWrap
                text: "stability changes retrieval weight; evidence stays retained"
                color: Qt.alpha(root.fg, 0.35)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Text {
                visible: !!(root.status && root.status.agent_queue)
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "AGENT RELAY — last published pulse"
                topPadding: Style.space(6)
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Text {
                visible: !!(root.status && root.status.agent_queue)
                readonly property var relay:
                  root.status && root.status.agent_queue
                    ? root.status.agent_queue : ({})
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                width: vitalsCol.width
                wrapMode: Text.WordWrap
                text: (relay.materialized || 0) + " materialized · "
                  + (relay.acknowledged || 0) + " acknowledged · "
                  + (relay.refused || 0) + " refused"
                color: (relay.refused || 0) > 0
                  ? root.urgent : Qt.alpha(root.fg, 0.65)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                visible: !!(root.status && root.status.agent_queue)
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                width: vitalsCol.width
                wrapMode: Text.WordWrap
                text: "acknowledgement follows corpus commit and index sync"
                color: Qt.alpha(root.fg, 0.35)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Text {

                textFormat: Text.PlainText

                renderType: Text.NativeRendering
                text: "PULSE ACTIVITY"
                topPadding: Style.space(6)
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Canvas {
                id: sparkline
                width: vitalsCol.width
                height: Style.space(34)
                onPaint: {
                  var ctx = getContext("2d")
                  ctx.reset(); ctx.clearRect(0, 0, width, height)
                  var hist = root.status && root.status.history
                    ? root.status.history : []
                  if (!hist.length) return
                  var n = Math.min(hist.length, 90)
                  var bw = width / 90
                  var maxV = 1
                  for (var i = hist.length - n; i < hist.length; i++)
                    maxV = Math.max(maxV, hist[i][1])
                  for (i = 0; i < n; i++) {
                    var v = hist[hist.length - n + i][1]
                    var h = v > 0
                      ? Math.max(2, (Math.log(1 + v) / Math.log(1 + maxV))
                                 * (height - 4))
                      : 1
                    ctx.fillStyle = v > 0 ? Qt.alpha(root.accent, 0.85)
                                          : Qt.alpha(root.fg, 0.15)
                    ctx.fillRect(i * bw, height - h, Math.max(1, bw - 1.5), h)
                  }
                }
                Connections {
                  target: root
                  function onStatusChanged() { sparkline.requestPaint() }
                }
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: {
                  var hist = root.status && root.status.history
                    ? root.status.history : []
                  if (!hist.length) return "no pulses yet"
                  var tot = 0
                  for (var i = Math.max(0, hist.length - 90); i < hist.length; i++)
                    tot += hist[i][1]
                  return "last " + Math.min(hist.length, 90) + " pulses · "
                    + tot + " events"
                }
                color: Qt.alpha(root.fg, 0.4)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
          }

          // Global Workspace (Baars/Dehaene): the brain's 7±2 conscious
          // slots — ignition-thresholded, laterally inhibited, hysteretic
          Rectangle {
            visible: !!(root.status && root.status.workspace
                        && root.status.workspace.length)
            width: parent.width
            height: wsCol.implicitHeight + Style.space(20)
            radius: Style.cornerRadius
            color: Qt.alpha(root.accent, 0.05)
            border.color: Qt.alpha(root.accent, 0.22)
            border.width: 1
            Column {
              id: wsCol
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.margins: Style.space(10)
              spacing: Style.space(3)
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "WORKSPACE — "
                  + (root.status && root.status.workspace
                     ? root.status.workspace.length : 0) + " OF 7 SLOTS"
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Repeater {
                model: root.status && root.status.workspace
                  ? root.status.workspace : []
                delegate: Item {
                  id: wsRow
                  required property var modelData
                  readonly property bool onMap:
                    root.graphHasNode(wsRow.modelData)
                  width: wsCol.width
                  height: wsText.implicitHeight + Style.space(2)
                  Text {
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    id: wsText
                    text: "◉ " + Model.slugLabel(wsRow.modelData)
                    anchors.left: parent.left
                    anchors.right: wsMapState.left
                    anchors.rightMargin: Style.space(6)
                    elide: Text.ElideRight
                    color: !wsRow.onMap ? Qt.alpha(root.fg, 0.45)
                      : root.selectedId === wsRow.modelData
                      ? root.accent : Qt.alpha(root.fg, 0.75)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                  Text {
                    id: wsMapState
                    visible: !wsRow.onMap
                    anchors.right: parent.right
                    width: visible ? implicitWidth : 0
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    text: "off-map"
                    color: Qt.alpha(root.fg, 0.35)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                  MouseArea {
                    anchors.fill: parent
                    enabled: wsRow.onMap
                    onClicked: {
                      root.selectedId =
                        (root.selectedId === wsRow.modelData)
                          ? "" : wsRow.modelData
                      graphCanvas.requestPaint()
                    }
                  }
                }
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                width: wsCol.width
                text: "off-map entries remain retained in mind; the graph is a bounded display window"
                wrapMode: Text.WordWrap
                color: Qt.alpha(root.fg, 0.35)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
          }

          Rectangle {
            width: parent.width
            height: organCol.implicitHeight + Style.space(20)
            radius: Style.cornerRadius
            color: Qt.alpha(root.fg, 0.04)
            border.color: Qt.alpha(root.fg, 0.10)
            border.width: 1
            Column {
              id: organCol
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.margins: Style.space(10)
              spacing: Style.space(3)
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "ORGANS"
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
                bottomPadding: Style.space(3)
              }
              Repeater {
                model: {
                  if (!root.status || !root.status.organs) return []
                  var ks = Object.keys(root.status.organs)
                  ks.sort(function(a, b) {
                    return (root.status.organs[b].today || 0)
                         - (root.status.organs[a].today || 0)
                  })
                  return ks
                }
                delegate: Item {
                  id: organRow
                  required property var modelData
                  readonly property var o:
                    (root.status && root.status.organs
                     && root.status.organs[organRow.modelData]) || {}
                  width: organCol.width
                  height: organName.implicitHeight + Style.space(2)
                  Text {
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    id: organName
                    anchors.left: parent.left
                    text: organRow.modelData
                    color: Qt.alpha(root.fg, 0.7)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                  Text {
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    anchors.right: countText.left
                    anchors.rightMargin: Style.space(8)
                    text: organRow.o.last_ts
                      ? Model.timeAgo(organRow.o.last_ts, root.nowMs) : ""
                    color: Qt.alpha(root.fg, 0.35)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                  Text {
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    id: countText
                    anchors.right: parent.right
                    text: String(organRow.o.today || 0)
                    color: (organRow.o.today || 0) > 0
                      ? root.accent : Qt.alpha(root.fg, 0.3)
                    font.bold: (organRow.o.today || 0) > 0
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                }
              }
            }
          }

          Rectangle {
            width: parent.width
            height: chainCol.implicitHeight + Style.space(20)
            radius: Style.cornerRadius
            color: Qt.alpha(root.fg, 0.04)
            border.color: Qt.alpha(root.fg, 0.10)
            border.width: 1
            Column {
              id: chainCol
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.margins: Style.space(10)
              spacing: Style.space(4)
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "EVIDENCE CHAINS"
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Repeater {
                model: root.status && root.status.integrity
                       && root.status.integrity.chains
                  ? Object.keys(root.status.integrity.chains).sort() : []
                delegate: Item {
                  id: chainRow
                  required property var modelData
                  readonly property string v:
                    ((root.status && root.status.integrity
                      && root.status.integrity.chains) || {})[chainRow.modelData]
                    || "absent"
                  width: chainCol.width
                  height: chainName.implicitHeight + Style.space(2)
                  Text {
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    id: chainName
                    anchors.left: parent.left
                    text: chainRow.modelData
                    color: Qt.alpha(root.fg, 0.7)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                  Text {
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    anchors.right: parent.right
                    text: chainRow.v === "pass" ? "verified ✓"
                        : chainRow.v === "absent" ? "absent –" : "FAILED ✗"
                    color: chainRow.v === "pass" ? root.accent
                         : chainRow.v === "absent" ? Qt.alpha(root.fg, 0.35)
                                                   : root.urgent
                    font.bold: chainRow.v === "fail"
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                }
              }
              Item { width: 1; height: Style.space(2) }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                width: chainCol.width
                text: Model.chainGlyph() + " ledger seq "
                  + (root.status && root.status.ledger
                     ? root.status.ledger.seq : "?")
                  + " · " + (root.status && root.status.ledger
                             ? root.status.ledger.head : "") + "…"
                elide: Text.ElideRight
                color: Qt.alpha(root.fg, 0.55)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: !!(root.status && root.status.dream
                            && root.status.dream.last)
                text: Model.dreamGlyph() + " dreamed "
                  + (root.status && root.status.dream
                     ? Model.timeAgo(root.status.dream.last, root.nowMs) : "")
                  + (root.status && root.status.dream
                     && root.status.dream.status
                     ? " · " + root.status.dream.status : "")
                color: Qt.alpha(root.fg, 0.55)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Rectangle {
                width: verifyBtnText.implicitWidth + Style.space(16)
                height: verifyBtnText.implicitHeight + Style.space(6)
                radius: Style.cornerRadius
                color: verifyBtnArea.containsMouse
                  ? Qt.alpha(root.fg, 0.18) : Qt.alpha(root.fg, 0.08)
                border.color: Qt.alpha(root.fg, 0.25)
                border.width: 1
                Text {
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  id: verifyBtnText
                  anchors.centerIn: parent
                  text: verifyProc.running ? "verifying…" : "verify now"
                  color: root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
                MouseArea {
                  id: verifyBtnArea
                  anchors.fill: parent
                  hoverEnabled: true
                  enabled: !verifyProc.running
                  onClicked: {
                    root.verifyMsg = ""
                    root.verifyOk = false
                    verifyProc.running = true
                  }
                }
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: root.verifyMsg !== ""
                text: root.verifyMsg
                color: root.verifyOk ? root.accent : root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
          }

          // Outcome learning plus the separate heuristic retrieval-drift
          // instrument. The latter stays visible even before any takes exist.
          Rectangle {
            visible: !!(root.status
                        && ((root.status.takes
                             && (root.status.takes.open
                                 || root.status.takes.resolved))
                            || (root.status.bench_trend
                                && root.status.bench_trend.length)))
            width: parent.width
            height: beliefCol.implicitHeight + Style.space(20)
            radius: Style.cornerRadius
            color: Qt.alpha(root.fg, 0.04)
            border.color: Qt.alpha(root.fg, 0.10)
            border.width: 1
            Column {
              id: beliefCol
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.margins: Style.space(10)
              spacing: Style.space(4)
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "BELIEFS"
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                readonly property var tk:
                  root.status && root.status.takes ? root.status.takes : ({})
                width: beliefCol.width
                text: (tk.open || 0) + " open prediction"
                  + ((tk.open || 0) === 1 ? "" : "s")
                  + ((tk.due || 0) > 0 ? " · " + tk.due + " DUE" : "")
                  + " · " + (tk.resolved || 0) + " resolved"
                  + ((tk.unresolvable || 0) > 0
                     ? " · " + tk.unresolvable + " unresolvable" : "")
                wrapMode: Text.WordWrap
                color: (tk.due || 0) > 0 ? root.accent
                                         : Qt.alpha(root.fg, 0.7)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: !!(root.status && root.status.takes
                            && root.status.takes.brier !== null
                            && root.status.takes.brier !== undefined)
                width: beliefCol.width
                wrapMode: Text.WordWrap
                text: "mean Brier "
                  + (root.status && root.status.takes
                     ? root.status.takes.brier : "")
                  + " · " + (root.status && root.status.takes
                     ? (root.status.takes.calibration_status || "descriptive")
                     : "descriptive")
                color: Qt.alpha(root.fg, 0.55)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                width: beliefCol.width
                wrapMode: Text.WordWrap
                text: "operator-selected population · model-assisted grades"
                color: Qt.alpha(root.fg, 0.35)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: !!(root.status && root.status.bench_trend
                            && root.status.bench_trend.length)
                topPadding: Style.space(4)
                width: beliefCol.width
                wrapMode: Text.WordWrap
                text: "SLUG DRIFT — heuristic blend match@5"
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Canvas {
                id: benchSpark
                visible: !!(root.status && root.status.bench_trend
                            && root.status.bench_trend.length)
                width: beliefCol.width
                height: Style.space(22)
                onPaint: {
                  var ctx = getContext("2d")
                  ctx.reset(); ctx.clearRect(0, 0, width, height)
                  var tr = root.status && root.status.bench_trend
                    ? root.status.bench_trend : []
                  if (!tr.length) return
                  var n = Math.min(tr.length, 30)
                  var step = width / 30
                  ctx.strokeStyle = Qt.alpha(root.fg, 0.15)
                  ctx.beginPath()
                  ctx.moveTo(0, height - 2); ctx.lineTo(width, height - 2)
                  ctx.stroke()
                  ctx.fillStyle = root.accent
                  ctx.strokeStyle = Qt.alpha(root.accent, 0.5)
                  ctx.beginPath()
                  var started = false
                  for (var i = 0; i < n; i++) {
                    var v = tr[tr.length - n + i].slug_match_at_5
                    if (typeof v !== "number") continue   // skip bad rows
                    var x = i * step + step / 2
                    var y = height - 2 - v * (height - 6)
                    if (!started) { ctx.moveTo(x, y); started = true }
                    else ctx.lineTo(x, y)
                  }
                  ctx.stroke()
                  for (i = 0; i < n; i++) {
                    v = tr[tr.length - n + i].slug_match_at_5
                    if (typeof v !== "number") continue
                    x = i * step + step / 2
                    y = height - 2 - v * (height - 6)
                    ctx.fillRect(x - 1.5, y - 1.5, 3, 3)
                  }
                }
                Connections {
                  target: root
                  function onStatusChanged() { benchSpark.requestPaint() }
                }
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: benchSpark.visible
                readonly property var bt:
                  root.status && root.status.bench_trend
                    ? root.status.bench_trend : []
                width: beliefCol.width
                wrapMode: Text.WordWrap
                text: bt.length
                  ? "latest blend "
                    + (typeof bt[bt.length - 1].slug_match_at_5 === "number"
                      ? bt[bt.length - 1].slug_match_at_5.toFixed(2) : "—")
                    + " · " + bt.length
                    + (bt.length === 1 ? " observation" : " observations")
                    + " · heuristic only; no answer scoring"
                    + " · drift says: run the signed-ledger bench"
                  : ""
                color: Qt.alpha(root.fg, 0.35)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                width: beliefCol.width
                wrapMode: Text.WordWrap
                text: "SIGNED-LEDGER QA · not projected in this snapshot; run `sia bench` for scored retrieval and abstention checks"
                color: Qt.alpha(root.fg, 0.35)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: !!(root.status && root.status.bench_trend_boundary
                            && root.status.bench_trend_boundary.legacy_truncated)
                width: beliefCol.width
                wrapMode: Text.WordWrap
                text: "legacy SLUG DRIFT display history was tail-compacted; "
                  + "this is not scored memory evidence"
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
          }

          Rectangle {
            visible: !!(root.status && root.status.intents
                        && root.status.intents.length)
            width: parent.width
            height: intentCol.implicitHeight + Style.space(20)
            radius: Style.cornerRadius
            color: Qt.alpha(root.fg, 0.04)
            border.color: Qt.alpha(root.fg, 0.10)
            border.width: 1
            Column {
              id: intentCol
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.margins: Style.space(10)
              spacing: Style.space(4)
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "INTENTS — prospective memory"
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Repeater {
                model: root.status && root.status.intents
                  ? root.status.intents : []
                delegate: Text {
                  required property var modelData
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  width: intentCol.width
                  wrapMode: Text.WordWrap
                  text: (modelData.days_left < 0
                          ? "➤ OVERDUE " + (-modelData.days_left) + "d — "
                          : modelData.days_left === 0
                            ? "➤ due today — "
                            : "➤ in " + modelData.days_left + "d — ")
                        + modelData.text
                  color: modelData.days_left < 0 ? root.urgent
                    : modelData.days_left <= 2 ? root.accent
                    : Qt.alpha(root.fg, 0.7)
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
              }
            }
          }

          Rectangle {
            width: parent.width
            height: healthCol.implicitHeight + Style.space(20)
            radius: Style.cornerRadius
            color: Qt.alpha(root.fg, 0.04)
            border.color: Qt.alpha(root.fg, 0.10)
            border.width: 1
            Column {
              id: healthCol
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.margins: Style.space(10)
              spacing: Style.space(4)
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "SOURCE HEALTH"
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                width: healthCol.width
                text: {
                  if (!root.snap) return "no snapshot contract"
                  if (root.snap.complete !== true)
                    return "snapshot PARTIAL — publication boundary incomplete"
                  if (root.snap.failed_ops && root.snap.failed_ops.length)
                    return "snapshot PARTIAL — failed: "
                      + root.snap.failed_ops.join(", ")
                  var s = "snapshot complete · " + root.snap.window_days
                    + "d window"
                  var omittedNodes = root.snap.omitted_nodes
                    || root.snap.truncated || 0
                  var omittedEdges = root.snap.omitted_edges || 0
                  if (omittedNodes || omittedEdges)
                    s += " · display cap omitted " + omittedNodes
                      + " nodes / " + omittedEdges
                      + " edges (not an absence claim)"
                  return s
                }
                wrapMode: Text.WordWrap
                color: root.snap && (root.snap.complete !== true
                        || (root.snap.failed_ops
                            && root.snap.failed_ops.length))
                  ? root.urgent : Qt.alpha(root.fg, 0.6)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: !!(root.status && root.status.ledger_transition)
                width: healthCol.width
                text: "publication ledger · " + root.ledgerTransitionText()
                wrapMode: Text.WordWrap
                color: root.status && root.status.ledger_transition
                  && root.status.ledger_transition.state === "signed"
                  ? Qt.alpha(root.accent, 0.75)
                  : root.status && root.status.ledger_transition
                    && root.status.ledger_transition.state === "pending"
                    ? root.urgent : Qt.alpha(root.fg, 0.55)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: root.projectionDebtKeys().length > 0
                width: healthCol.width
                text: "PUBLISHED SNAPSHOT DEBT — "
                  + root.projectionDebtDetail()
                  + " · memory reads remain closed until reconciliation"
                wrapMode: Text.WordWrap
                color: root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: !!root.status && !root.projectionDebtKnown()
                width: healthCol.width
                text: "PUBLISHED SNAPSHOT DEBT — unknown; use the live check before memory reads"
                wrapMode: Text.WordWrap
                color: root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: root.graphBoundary !== "" || root.statusBoundary !== ""
                width: healthCol.width
                text: [root.graphBoundary, root.statusBoundary]
                  .filter(function(value) { return value !== "" }).join(" · ")
                wrapMode: Text.WordWrap
                color: root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: !!(root.snap && root.snap.aged_out)
                width: healthCol.width
                text: (root.snap ? root.snap.aged_out : 0)
                  + " older memories beyond the display window (still in the brain)"
                wrapMode: Text.WordWrap
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Repeater {
                model: root.snap && root.snap.counts_by_kind
                  ? Object.keys(root.snap.counts_by_kind).sort() : []
                delegate: Item {
                  id: kindRow
                  required property var modelData
                  width: healthCol.width
                  height: kindName.implicitHeight
                  Text {
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    id: kindName
                    anchors.left: parent.left
                    text: kindRow.modelData
                    color: Qt.alpha(root.fg, 0.55)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                  Text {
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    anchors.right: parent.right
                    text: String(root.snap.counts_by_kind[kindRow.modelData])
                    color: Qt.alpha(root.fg, 0.75)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                }
              }
              Repeater {
                model: root.status && root.status.errors
                  ? Object.keys(root.status.errors).sort() : []
                delegate: Text {
                  id: errRow
                  required property var modelData
                  width: healthCol.width
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: "✗ " + errRow.modelData + ": "
                    + root.status.errors[errRow.modelData]
                  wrapMode: Text.WordWrap
                  color: root.urgent
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: !!(root.status && root.status.sync_note)
                width: healthCol.width
                text: "✗ sync: " + (root.status ? root.status.sync_note : "")
                wrapMode: Text.WordWrap
                color: root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: !!(root.status && root.status.redactions
                            && Object.keys(root.status.redactions).length)
                width: healthCol.width
                text: {
                  var redactions = root.status && root.status.redactions
                    ? root.status.redactions : ({})
                  var parts = []
                  var names = Object.keys(redactions).sort()
                  for (var i = 0; i < names.length; i++)
                    parts.push(names[i] + ": " + redactions[names[i]])
                  return "redactions retained · " + parts.join(" · ")
                }
                wrapMode: Text.WordWrap
                color: Qt.alpha(root.fg, 0.5)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: !root.stale && root.status
                  && (!root.status.errors
                      || Object.keys(root.status.errors).length === 0)
                  && !(root.status && root.status.sync_note)
                  && root.snap && root.snap.complete === true
                  && (!root.snap.failed_ops
                      || root.snap.failed_ops.length === 0)
                  && root.projectionDebtKnown()
                  && root.projectionDebtKeys().length === 0
                  && root.graphBoundary === "" && root.statusBoundary === ""
                text: "published snapshot sensors reporting ✓ · use live check for memory reads"
                color: Qt.alpha(root.accent, 0.7)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
          }
        }
        }

        // ================================================= CENTER: graph
        Rectangle {
          id: graphCard
          anchors.left: leftScroll.right
          anchors.right: rightPane.left
          anchors.top: parent.top
          anchors.bottom: parent.bottom
          anchors.leftMargin: body.gap
          anchors.rightMargin: body.gap
          radius: Style.cornerRadius
          color: Qt.alpha(root.fg, 0.03)
          border.color: Qt.alpha(root.fg, 0.10)
          border.width: 1
          clip: true

          Canvas {
            id: graphCanvas
            anchors.fill: parent
            anchors.margins: 2
            renderStrategy: Canvas.Cooperative

            onWidthChanged: if (root.graph && width > 0)
              Model.syncGraph(root.graph, width, height)
            onHeightChanged: if (root.graph && width > 0)
              Model.syncGraph(root.graph, width, height)

            Timer {
              interval: 40
              running: root.opened && root.graph !== null
              repeat: true
              onTriggered: {
                if (root.playing) {
                  root.revealT = Math.min(1, root.revealT + 40 / 12000)
                  if (root.revealT >= 1) root.playing = false
                }
                Model.step(root.graph, graphCanvas.width, graphCanvas.height)
                graphCanvas.requestPaint()
              }
            }

            onPaint: {
              var ctx = getContext("2d")
              ctx.reset()
              ctx.clearRect(0, 0, width, height)
              if (!root.graph || !root.graph.nodes) return
              var now = root.nowMs > 0 ? root.nowMs : Date.now()
              var nodes = root.graph.nodes, edges = root.graph.edges
              var i, p, q, n
              var eff = root.effId
              var nbrs = eff !== "" ? Model.neighbors(eff) : null

              var vis = {}
              for (i = 0; i < nodes.length; i++)
                vis[nodes[i].id] = root.nodeVisible(nodes[i])

              var rings = Model.rings()
              var cx = width / 2, cy = height / 2
              ctx.lineWidth = 1
              for (i = 0; i < rings.length; i++) {
                ctx.strokeStyle = Qt.alpha(root.fg, 0.055)
                ctx.beginPath()
                ctx.arc(cx, cy, rings[i].r, 0, 2 * Math.PI)
                ctx.stroke()
              }
              ctx.font = Style.font.caption + "px " + root.fontFamily
              ctx.textAlign = "center"
              for (i = 0; i < rings.length; i++) {
                ctx.fillStyle = Qt.alpha(root.fg, 0.25)
                ctx.fillText(rings[i].label, cx, cy - rings[i].r - 3)
              }

              for (i = 0; i < edges.length; i++) {
                if (!vis[edges[i].s] || !vis[edges[i].d]) continue
                p = Model.posOf(edges[i].s); q = Model.posOf(edges[i].d)
                if (!p || !q) continue
                var touching = eff !== "" &&
                  (edges[i].s === eff || edges[i].d === eff)
                if (eff !== "" && !touching)
                  ctx.strokeStyle = Qt.alpha(root.fg, 0.035)
                else if (touching)
                  ctx.strokeStyle = Qt.alpha(
                    Model.edgeColor(edges[i].t, root.pal), 0.72)
                else
                  ctx.strokeStyle = Qt.alpha(root.fg, 0.10)
                ctx.lineWidth = touching ? 1.5 : 1
                ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y)
                ctx.stroke()
              }
              ctx.lineWidth = 1

              for (i = 0; i < nodes.length; i++) {
                n = nodes[i]
                if (!vis[n.id]) continue
                p = Model.posOf(n.id)
                if (!p) continue
                var dimmed = eff !== "" && n.id !== eff &&
                  !(nbrs && nbrs[n.id])
                var r = Model.nodeRadius(n)
                var col = Model.nodeColor(n, root.pal)
                var fresh = Model.freshness(n, now)
                if (fresh > 0.02 && !dimmed) {
                  var breathe = 0.75 + 0.25 * Math.sin(Model.phase() * 2
                                                       + p.x * 0.05)
                  ctx.fillStyle = Qt.alpha(root.accent, 0.28 * fresh * breathe)
                  ctx.beginPath()
                  ctx.arc(p.x, p.y, r + 5 + 4 * fresh, 0, 2 * Math.PI)
                  ctx.fill()
                }
                ctx.fillStyle = dimmed ? Qt.alpha(col, 0.22) : col
                ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 2 * Math.PI)
                ctx.fill()
                if (n.id === "sia/cortex" && !dimmed) {
                  var halo = 0.35 + 0.20 * Math.sin(Model.phase())
                  ctx.strokeStyle = Qt.alpha(root.fg, halo)
                  ctx.lineWidth = 1.2
                  ctx.beginPath()
                  ctx.arc(p.x, p.y, r + 3.5, 0, 2 * Math.PI)
                  ctx.stroke()
                  ctx.lineWidth = 1
                }
                if (n.id === eff) {
                  ctx.strokeStyle = root.fg
                  ctx.beginPath()
                  ctx.arc(p.x, p.y, r + 3, 0, 2 * Math.PI)
                  ctx.stroke()
                }
              }

              for (i = 0; i < nodes.length; i++) {
                n = nodes[i]
                if (!vis[n.id]) continue
                var isEff = n.id === eff
                var isNbr = nbrs && nbrs[n.id]
                var anchorLbl = n.t === "organ" || n.id === "sia/cortex"
                if (!anchorLbl && !isEff && !isNbr) continue
                p = Model.posOf(n.id)
                if (!p) continue
                var alpha = isEff ? 1.0
                  : isNbr ? 0.8
                  : (eff !== "" ? 0.25
                     : (n.id === "sia/cortex" ? 0.9 : 0.55))
                ctx.fillStyle = Qt.alpha(root.fg, alpha)
                ctx.fillText(Model.shortLabel(n), p.x,
                             p.y - Model.nodeRadius(n) - 5)
              }
            }

            MouseArea {
              anchors.fill: parent
              hoverEnabled: true
              function nearest(mx, my) {
                if (!root.graph) return ""
                var best = "", bd = 500
                for (var i = 0; i < root.graph.nodes.length; i++) {
                  var n = root.graph.nodes[i]
                  if (!root.nodeVisible(n)) continue
                  var p = Model.posOf(n.id)
                  if (!p) continue
                  var dx = p.x - mx, dy = p.y - my
                  var d2 = dx * dx + dy * dy
                  if (d2 < bd) { bd = d2; best = n.id }
                }
                return best
              }
              onPositionChanged: function(mouse) {
                root.hoverId = nearest(mouse.x, mouse.y)
              }
              onExited: root.hoverId = ""
              onClicked: function(mouse) {
                var hit = nearest(mouse.x, mouse.y)
                root.selectedId = (hit === root.selectedId) ? "" : hit
                graphCanvas.requestPaint()
              }
            }
          }

          Text {
            textFormat: Text.PlainText
            renderType: Text.NativeRendering
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.margins: Style.space(10)
            text: "CORPUS-LINKED RELATIONS · hover or lock to reveal type"
            color: Qt.alpha(root.fg, 0.38)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }

          Rectangle {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Style.space(10)
            width: replayText.implicitWidth + Style.space(16)
            height: replayText.implicitHeight + Style.space(8)
            radius: Style.cornerRadius
            color: replayArea.containsMouse
              ? Qt.alpha(root.fg, 0.18) : Qt.alpha(root.fg, 0.08)
            border.color: Qt.alpha(root.fg, 0.25)
            border.width: 1
            Text {
              textFormat: Text.PlainText
              renderType: Text.NativeRendering
              id: replayText
              anchors.centerIn: parent
              text: root.playing ? "◼ stop" : "⟲ replay growth"
              color: root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
            MouseArea {
              id: replayArea
              anchors.fill: parent
              hoverEnabled: true
              onClicked: {
                if (root.playing) { root.playing = false; root.revealT = 1.0 }
                else { root.revealT = 0.0; root.playing = true }
                graphCanvas.requestPaint()
              }
            }
          }

          Row {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            anchors.margins: Style.space(10)
            spacing: Style.space(12)
            Repeater {
              model: [
                { label: "cortex",  role: "cortex" },
                { label: "organ",   role: "organ" },
                { label: "memory",  role: "day" },
                { label: "thought", role: "thought" },
                { label: "record",  role: "record" },
                { label: "skill",   role: "skill" }
              ]
              delegate: Item {
                id: chip
                required property var modelData
                width: chipRow.implicitWidth
                height: chipRow.implicitHeight
                opacity: root.hiddenKinds[chip.modelData.role] ? 0.3 : 1.0
                Row {
                  id: chipRow
                  spacing: Style.space(4)
                  Rectangle {
                    width: 8; height: 8; radius: 4
                    anchors.verticalCenter: parent.verticalCenter
                    color: root.pal[chip.modelData.role]
                  }
                  Text {
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    text: chip.modelData.label
                    color: Qt.alpha(root.fg, 0.5)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                }
                MouseArea {
                  anchors.fill: parent
                  anchors.margins: -Style.space(3)
                  onClicked: root.toggleKind(chip.modelData.role)
                }
              }
            }
          }

          Text {

            textFormat: Text.PlainText

            renderType: Text.NativeRendering
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.rightMargin: Style.space(10)
            // one line above the legend chips — six kinds now reach this far
            anchors.bottomMargin: Style.space(28)
            text: root.graph
              ? root.graph.nodes.length + " of " + root.graph.pages_total
                + " memories · " + root.graph.edges.length + " links · "
                + (root.snap && root.snap.complete ? "complete" : "partial")
              : "no graph snapshot yet"
            color: Qt.alpha(root.fg, 0.45)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        // ================================================= RIGHT: inspect
        Column {
          id: rightPane
          width: body.rightW
          anchors.top: parent.top
          anchors.bottom: parent.bottom
          anchors.right: parent.right
          spacing: body.gap

          Rectangle {
            id: inspectorCard
            width: parent.width
            height: Math.min(inspectorCol.implicitHeight + Style.space(20),
                             rightPane.height * 0.44)
            radius: Style.cornerRadius
            color: root.effId !== ""
              ? Qt.alpha(root.accent, 0.06) : Qt.alpha(root.fg, 0.04)
            border.color: root.effId !== ""
              ? Qt.alpha(root.accent, 0.3) : Qt.alpha(root.fg, 0.10)
            border.width: 1
            clip: true

            Flickable {
              anchors.fill: parent
              anchors.margins: Style.space(10)
              contentWidth: width
              contentHeight: inspectorCol.implicitHeight
              clip: true
              pixelAligned: true
              boundsBehavior: Flickable.StopAtBounds

              Column {
                id: inspectorCol
                width: parent.width
                spacing: Style.space(4)
                readonly property var n: root.nodeById(root.effId)

                Text {

                  textFormat: Text.PlainText

                  renderType: Text.NativeRendering
                  text: "INSPECTOR"
                  color: Qt.alpha(root.fg, 0.45)
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                }
                Text {
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  visible: !inspectorCol.n
                  width: inspectorCol.width
                  text: "hover a memory to inspect it — click to lock the "
                    + "selection. every edge shows its type and the context "
                    + "it was extracted from."
                  wrapMode: Text.WordWrap
                  color: Qt.alpha(root.fg, 0.45)
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
                Text {
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  visible: !!inspectorCol.n
                  width: inspectorCol.width
                  text: inspectorCol.n ? inspectorCol.n.title : ""
                  wrapMode: Text.WordWrap
                  color: root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.bodySmall
                  font.bold: true
                }
                Text {
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  visible: !!inspectorCol.n
                  width: inspectorCol.width
                  text: inspectorCol.n
                    ? inspectorCol.n.t + " · " + inspectorCol.n.id
                    : ""
                  wrapMode: Text.WrapAnywhere
                  color: Qt.alpha(root.fg, 0.55)
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
                Text {
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  visible: !!inspectorCol.n
                  text: inspectorCol.n
                    ? "ORIGIN · " + Model.originLabel(inspectorCol.n.origin)
                    : ""
                  color: inspectorCol.n
                    ? Qt.alpha(Model.originColor(inspectorCol.n.origin,
                                                 root.pal), 0.85)
                    : Qt.alpha(root.fg, 0.55)
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                }
                Text {
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  visible: !!inspectorCol.n
                  text: inspectorCol.n
                    ? "updated " + Model.timeAgo(inspectorCol.n.ts, root.nowMs)
                      + " · " + (inspectorCol.n.din || 0) + " in / "
                      + (inspectorCol.n.dout || 0) + " out"
                      + (root.selectedId === root.effId ? " · LOCKED" : "")
                    : ""
                  color: Qt.alpha(root.fg, 0.55)
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
                Text {
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  visible: !!inspectorCol.n
                  text: "CONNECTIONS"
                  topPadding: Style.space(4)
                  color: Qt.alpha(root.fg, 0.45)
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                }
                Repeater {
                  model: root.effId !== "" ? Model.nodeEdges(root.effId) : []
                  delegate: Column {
                    id: edgeRow
                    required property var modelData
                    width: inspectorCol.width
                    spacing: 0
                    Text {
                      textFormat: Text.PlainText
                      renderType: Text.NativeRendering
                      width: parent.width
                      text: (edgeRow.modelData.out ? "→ " : "← ")
                        + edgeRow.modelData.type + "  "
                        + Model.slugLabel(edgeRow.modelData.other)
                      elide: Text.ElideRight
                      color: Qt.alpha(Model.edgeColor(
                        edgeRow.modelData.type, root.pal), 0.9)
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                    }
                    Text {
                      textFormat: Text.PlainText
                      renderType: Text.NativeRendering
                      visible: edgeRow.modelData.why !== ""
                      width: parent.width
                      leftPadding: Style.space(12)
                      text: "“" + edgeRow.modelData.why + "”"
                      elide: Text.ElideRight
                      color: Qt.alpha(root.fg, 0.4)
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                    }
                  }
                }
              }
            }
          }

          Rectangle {
            width: parent.width
            height: rightPane.height - inspectorCard.height - body.gap
            radius: Style.cornerRadius
            color: Qt.alpha(root.fg, 0.04)
            border.color: Qt.alpha(root.fg, 0.10)
            border.width: 1
            clip: true

            Column {
              id: thoughtHeader
              anchors.top: parent.top
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.margins: Style.space(10)
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "THOUGHT STREAM — " + root.thoughts.length
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
            }

            Flickable {
              anchors.top: thoughtHeader.bottom
              anchors.bottom: parent.bottom
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.margins: Style.space(10)
              anchors.topMargin: Style.space(6)
              contentWidth: width
              contentHeight: thoughtCol.implicitHeight
              pixelAligned: true
              clip: true
              boundsBehavior: Flickable.StopAtBounds
              ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

              Column {
                id: thoughtCol
                width: parent.width
                spacing: Style.space(8)
                Repeater {
                  model: root.thoughts
                  delegate: Row {
                    id: thoughtRow
                    required property var modelData
                    width: thoughtCol.width
                    spacing: Style.space(8)
                    Text {
                      textFormat: Text.PlainText
                      renderType: Text.NativeRendering
                      text: Model.thoughtMark(thoughtRow.modelData.kind)
                      color: thoughtRow.modelData.urgent
                        ? root.urgent : root.accent
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.bodySmall
                      width: Style.space(12)
                      horizontalAlignment: Text.AlignHCenter
                    }
                    Column {
                      width: parent.width - Style.space(20)
                      Text {
                        textFormat: Text.PlainText
                        renderType: Text.NativeRendering
                        width: parent.width
                        text: thoughtRow.modelData.text
                        wrapMode: Text.WordWrap
                        color: thoughtRow.modelData.urgent
                          ? root.urgent : Qt.alpha(root.fg, 0.85)
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                      }
                      Text {
                        textFormat: Text.PlainText
                        renderType: Text.NativeRendering
                        text: thoughtRow.modelData.kind + " · origin:"
                          + (thoughtRow.modelData.origin
                             || "legacy-unlabeled") + " · "
                          + Model.timeAgo(thoughtRow.modelData.ts, root.nowMs)
                        color: Qt.alpha(root.fg, 0.35)
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
