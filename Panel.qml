// SIA bar widget — product glyph + today's event count, colored by service
// state. “Brain” is a product metaphor for auditable local machine memory; it
// is not a biological brain and does not establish cognition or neuroscience.
// Clicking summons the full-screen SIA cockpit (Cockpit.qml). Pixels only:
// reads the brainstem and continuity workers' published state.

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
  property string installingRecordKey: ""
  property real installingObservedAtMs: 0
  property bool installCompletionPublicationChanged: false
  property bool stale: true
  // Continuity gets its own clock, separate from the brainstem pulse: the
  // two subsystems publish on completely different cadences and a single
  // `stale` flag would have to pick one of them to lie about.
  property bool continuityStale: true
  property bool continuityLoadValid: false
  property bool continuityReceiptAuthenticated: false
  property real nowMs: Date.now()
  readonly property int continuityResponseMaxLength: 65536
  readonly property int continuityAuthorityPollInterval: 60000

  readonly property string statusPath:
    (Quickshell.env("HOME") || "") + "/.local/state/sia/status.json"
  readonly property string continuityPath:
    (Quickshell.env("HOME") || "")
      + "/.local/state/sia-continuity/status.json"
  readonly property string continuityReceiptPath:
    root.continuity && root.continuity.latest
      && root.continuity.latest.verified === true
      ? (Quickshell.env("HOME") || "")
        + "/.local/state/sia-continuity/verifications/"
        + root.continuity.latest.snapshot_id + ".json"
      : ""
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
  readonly property bool installerProgressUnobserved:
    root.releaseLifecycle === "installing"
      && Model.installingProgressUnobserved(root.installingObservedAtMs,
                                            root.nowMs)
  readonly property string brainState: root.compactBrainState()
  // Status counters span the full JSON-safe integer domain.  QML `int` is a
  // signed 32-bit lane, so keep the comparison in `real` and render directly
  // from the validated JavaScript number rather than narrowing it first.
  readonly property real eventsTodayValue: root.compactEventsTodayValue()
  readonly property string eventsToday: root.compactEventsTodayText()
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

  function compactBrainState() {
    if (root.releaseLifecycle !== "ready") return root.releaseLifecycle
    if (!root.statusLoadValid) return "unknown"
    if (root.stale) return "stale"
    return root.status && root.status.state ? root.status.state : "unknown"
  }

  function compactEventsTodayValue() {
    return root.statusLoadValid && root.status
      ? root.status.events_today : 0
  }

  function compactEventsTodayText() {
    return root.statusLoadValid && root.status
      ? String(root.status.events_today) : "—"
  }

  function stateColor() {
    if (root.releaseLifecycle !== "ready") return Color.accent
    if (!root.statusLoadValid || root.stale) return Qt.alpha(root.fg, 0.4)
    if (root.brainState === "failed") return root.urgentColor
    if (root.brainState === "degraded") return Qt.alpha(root.urgentColor, 0.75)
    if (root.brainState === "thinking") return Color.accent
    return root.fg
  }

  function indicatorColor() {
    // A stale record may not tint the glyph.  Both non-default tones are
    // claims about right now — "danger" that something is wrong, "busy" that
    // work is under way — and neither survives the worker going silent.
    if (root.continuity && !root.continuityStale
        && root.continuityReceiptAuthenticated) {
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
    return Model.continuityBarMark(
      root.continuity, root.continuityReceiptAuthenticated)
  }

  function continuityText() {
    if (!root.continuity || !root.continuityReceiptAuthenticated)
      return "continuity status unavailable"
    var label = Model.continuityStateLabel(root.continuity.state)
      .toLowerCase()
    var detail = String(root.continuity.detail || "").trim()
    var text = detail !== "" ? label + " — " + detail : label
    if (root.continuityStale)
      return "continuity not reporting · last published " + text
    return text
  }

  function refreshContinuityStale() {
    if (!root.continuityLoadValid) {
      root.continuityStale = true
      return
    }
    root.continuityStale = Model.continuityStale(
      root.continuity, root.nowMs, Model.continuityStaleAfterSec())
  }

  // FileView.reload() is intentionally asynchronous and Quickshell 0.3 drops
  // a same-path reload while its prior reader is still live.  Keep a watched
  // change pending through that callback and reread after the reader retires.
  function settleWatchedFileRefresh(view) {
    if (!view || view.refreshPending !== true) return false
    view.refreshPending = false
    Qt.callLater(function() {
      if (view) view.reload()
    })
    return true
  }

  function tooltip() {
    var brainBoundary = "“Brain” is a product metaphor for auditable local machine memory; it is not a biological brain and does not establish cognition or neuroscience."
    if (root.releaseLifecycle === "checking")
      return "SIA — checking the resident installation\n" + brainBoundary
    if (root.releaseLifecycle === "setup")
      return "SIA — first light required · click to install\n" + brainBoundary
    if (root.releaseLifecycle === "installing") {
      var installing = root.installerProgressUnobserved
        ? "SIA — first light has not reported progress · click for status or retry"
        : "SIA — first light is in progress · click for status or retry"
      return installing + "\n" + brainBoundary
    }
    if (root.releaseLifecycle === "repair")
      return "SIA — installation state needs repair · click to continue safely\n"
        + brainBoundary
    if (root.releaseLifecycle === "ahead") {
      var resident = Model.aheadVersion(
        root.runtimeEvidence, root.pluginVersion)
      var ahead = resident !== ""
        ? "SIA — resident " + resident + " is newer than cockpit "
          + root.pluginVersion + " · update the plugin checkout"
        : "SIA — a newer resident runtime is present · update the plugin checkout"
      return ahead + "\n" + brainBoundary
    }
    if (root.releaseLifecycle === "update") {
      var installed = root.status && typeof root.status.version === "string"
        ? root.status.version : "legacy runtime"
      return "SIA — finish update " + installed + " → "
        + root.pluginVersion + " · click to continue\n" + brainBoundary
    }
    var brain = root.cockpitWorkspace !== ""
      ? "SIA — cockpit locked to workspace " + root.cockpitWorkspace
        + " · return there to unlock"
      : !root.statusLoadValid
        ? "SIA — brainstem status unavailable"
      : root.stale
        ? "SIA — brainstem not reporting"
        : "SIA — " + (root.brainState === "thinking"
          ? "processing" : root.brainState) + " · " + root.eventsToday
          + " events today"
    return brain + " · " + root.continuityText()
      + " · click for cockpit · right-click for continuity\n" + brainBoundary
  }

  function applyStatus(text) {
    try {
      const parsed = Model.strictStatusJsonParse(text)
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

  function applyContinuity(text, receiptAuthenticated) {
    try {
      const parsed = Model.strictContinuityJsonParse(text)
      if (!Model.validContinuityStatus(parsed, receiptAuthenticated)) {
        root.continuityLoadValid = false
        root.continuityReceiptAuthenticated = false
        root.continuityStale = true
        return
      }
      root.continuity = parsed
      root.continuityLoadValid = true
      root.continuityReceiptAuthenticated =
        receiptAuthenticated === true
    } catch (e) {
      // Keep last-known-good detail for diagnosis, but withdraw every current
      // claim until a later publication validates.
      root.continuityLoadValid = false
      root.continuityReceiptAuthenticated = false
      root.continuityStale = true
      return
    }
    root.refreshContinuityStale()
  }

  function invalidateContinuityAuthority() {
    root.continuityLoadValid = false
    root.continuityReceiptAuthenticated = false
    root.continuityStale = true
  }

  function applyInstallCompletion(text) {
    var publicationChanged = root.installCompletionPublicationChanged
    root.installCompletionPublicationChanged = false
    try {
      const parsed = Model.strictInstallCompletionJsonParse(text)
      root.installCompletion = parsed
    } catch (e) { root.installCompletion = null }
    root.noteInstallingObservation(publicationChanged)
  }

  function noteInstallingObservation(publicationChanged) {
    var key = root.releaseLifecycle === "installing"
      && root.installCompletion
      ? String(root.installCompletion.v) + "/"
        + String(root.installCompletion.state) + "/"
        + String(root.installCompletion.version)
      : ""
    if (key === "") {
      root.installingRecordKey = ""
      root.installingObservedAtMs = 0
      return
    }
    if (key !== root.installingRecordKey || publicationChanged === true) {
      root.installingRecordKey = key
      root.installingObservedAtMs = Date.now()
    }
  }

  onReleaseLifecycleChanged: root.noteInstallingObservation(false)

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  FileView {
    id: statusFile
    property bool refreshPending: false
    path: root.statusPath
    watchChanges: true
    printErrors: false
    onLoaded: {
      if (root.settleWatchedFileRefresh(statusFile)) return
      root.applyStatus(text())
      root.statusResolved = true
    }
    onLoadFailed: {
      if (root.settleWatchedFileRefresh(statusFile)) return
      root.runtimeEvidence = Model.runtimeLifecycleEvidence(
        null, false, root.runtimeEvidence, root.pluginVersion)
      root.status = null
      root.statusLoadValid = false
      root.stale = true
      root.statusResolved = true
    }
    onFileChanged: {
      // The watched name now denotes an unvalidated generation.  Withdraw
      // current claims until the settled reread accepts it.
      root.statusLoadValid = false
      root.statusResolved = false
      root.stale = true
      statusFile.refreshPending = true
      statusApply.restart()
    }
  }
  Timer { id: statusApply; interval: 150; repeat: false
          onTriggered: statusFile.reload() }

  FileView {
    id: continuityFile
    property bool refreshPending: false
    path: root.continuityPath
    watchChanges: true
    printErrors: false
    onLoaded: {
      if (root.settleWatchedFileRefresh(continuityFile)) return
      continuityStatusProc.refresh()
    }
    onLoadFailed: {
      if (root.settleWatchedFileRefresh(continuityFile)) return
      // The resident-memory status has had this discipline since the beginning;
      // continuity did not, so a deleted or unreadable status file left the
      // last good record painted forever and the bar went on reassuring an
      // operator about a subsystem that was no longer there.  Drop to
      // unknown: a missing file is not evidence of a healthy copy.
      root.continuity = null
      root.continuityLoadValid = false
      root.continuityReceiptAuthenticated = false
      root.continuityStale = true
      continuityStatusProc.refresh()
    }
    onFileChanged: {
      root.continuityLoadValid = false
      root.continuityReceiptAuthenticated = false
      root.continuityStale = true
      continuityStatusProc.invalidate()
      continuityFile.refreshPending = true
      continuityApply.restart()
    }
  }

  // The receipt is watched only as an authority generation.  Its contents
  // are never interpreted here; the backend must rebind the status claim.
  FileView {
    id: continuityReceiptFile
    property bool refreshPending: false
    path: root.continuityReceiptPath
    preload: path !== ""
    watchChanges: path !== ""
    printErrors: false
    onLoaded: {
      if (root.settleWatchedFileRefresh(continuityReceiptFile)) return
      if (path !== "") continuityStatusProc.refresh()
    }
    onLoadFailed: {
      if (root.settleWatchedFileRefresh(continuityReceiptFile)) return
      if (path === "") return
      root.invalidateContinuityAuthority()
      continuityStatusProc.refresh()
    }
    onFileChanged: {
      root.invalidateContinuityAuthority()
      continuityStatusProc.invalidate()
      continuityReceiptFile.refreshPending = true
      continuityReceiptApply.restart()
    }
  }
  Timer { id: continuityReceiptApply; interval: 150; repeat: false
          onTriggered: continuityReceiptFile.reload() }

  FileView {
    id: installCompletionFile
    property bool refreshPending: false
    path: root.installCompletionPath
    watchChanges: true
    printErrors: false
    onLoaded: {
      if (root.settleWatchedFileRefresh(installCompletionFile)) return
      root.applyInstallCompletion(text())
      root.installCompletionResolved = true
    }
    onLoadFailed: {
      if (root.settleWatchedFileRefresh(installCompletionFile)) return
      root.installCompletion = null
      root.installCompletionResolved = true
    }
    onFileChanged: {
      // A real first-light change immediately restores the install barrier;
      // the settled callback decides which lifecycle may be shown next.
      root.installCompletionResolved = false
      root.installCompletionPublicationChanged = true
      installCompletionFile.refreshPending = true
      installCompletionApply.restart()
    }
  }
  Timer { id: installCompletionApply; interval: 150; repeat: false
          onTriggered: installCompletionFile.reload() }
  Timer { id: continuityApply; interval: 150; repeat: false
          onTriggered: continuityFile.reload() }

  // A status envelope cannot prove that its verification receipt still
  // exists.  The backend status command performs that receipt rebind; only
  // its bounded successful response may restore a reassuring bar claim.
  Process {
    id: continuityStatusProc
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
    property bool checking: false
    property bool rereadPending: false
    command: [(Quickshell.env("HOME") || "") + "/.local/bin/sia",
              "backup", "status"]

    function invalidate() {
      root.continuityReceiptAuthenticated = false
      if (checking || running) rereadPending = true
    }

    function refresh() {
      if (checking || running) {
        rereadPending = true
        return
      }
      outText = ""
      errText = ""
      exitCode = 0
      exited = false
      outDone = false
      errDone = false
      outOverflow = false
      errOverflow = false
      launchPending = true
      startedForAttempt = false
      checking = true
      running = true
    }

    function fail() {
      checking = false
      launchPending = false
      rereadPending = false
      root.invalidateContinuityAuthority()
    }

    function settle() {
      if (!checking || !exited || !outDone || !errDone) return
      checking = false
      launchPending = false
      if (rereadPending) {
        rereadPending = false
        Qt.callLater(function() { continuityStatusProc.refresh() })
        return
      }
      if (exitCode === 0 && !outOverflow && !errOverflow) {
        root.applyContinuity(
          outText.replace(/^\s+|\s+$/g, ""), true)
      } else {
        fail()
      }
    }

    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var output = String(text || "")
        continuityStatusProc.outOverflow = output.length
          > root.continuityResponseMaxLength
        continuityStatusProc.outText = output.slice(
          0, root.continuityResponseMaxLength)
        output = ""
        continuityStatusProc.outDone = true
        continuityStatusProc.settle()
      }
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var output = String(text || "")
        continuityStatusProc.errOverflow = output.length
          > root.continuityResponseMaxLength
        continuityStatusProc.errText = output.slice(
          0, root.continuityResponseMaxLength)
        output = ""
        continuityStatusProc.errDone = true
        continuityStatusProc.settle()
      }
    }
    onStarted: {
      continuityStatusProc.startedForAttempt = true
      continuityStatusProc.launchPending = false
    }
    onRunningChanged: {
      if (!running && continuityStatusProc.launchPending
          && !continuityStatusProc.startedForAttempt)
        continuityStatusProc.fail()
    }
    onExited: function(code) {
      continuityStatusProc.exitCode = code
      continuityStatusProc.exited = true
      continuityStatusProc.settle()
    }
  }

  Timer {
    // Receipt-only loss is watched immediately; this bounded poll also
    // rebinds configuration, repository-key, identity, and environment
    // authority that is intentionally never loaded into the panel.
    interval: root.continuityAuthorityPollInterval
    running: true
    repeat: true
    onTriggered: {
      root.invalidateContinuityAuthority()
      continuityStatusProc.invalidate()
      continuityStatusProc.refresh()
    }
  }

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
         : root.releaseLifecycle === "installing"
           ? (root.installerProgressUnobserved ? " INSTALL?" : " INSTALL")
         : root.releaseLifecycle === "update" ? " UPDATE"
         : root.releaseLifecycle === "repair" ? " REPAIR"
         : root.releaseLifecycle === "ahead" ? " AHEAD"
         : !root.statusLoadValid ? " STATUS?"
         : root.eventsTodayValue > 0 && !root.stale
           ? " " + root.eventsToday : "")
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
