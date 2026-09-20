// SIA COCKPIT — full-screen mission control for the Omarchy Brain.
// “Brain” is a product metaphor for auditable local machine memory; it is not a
// biological brain and does not establish cognition or neuroscience.
// Overlay kind: summoned from the bar widget or SUPER+SHIFT+B, dismissed
// with Esc / ✕ / click on the header brand. Pixels only — renders the
// brainstem service snapshots; authoritative state is gbrain + the signed corpus.

import QtQuick
import QtQuick.Controls as Controls
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import qs.Ui as Ui
import "Model.js" as Model

Item {
  id: root

  property var shell: ({})
  property var manifest: ({})
  property bool opened: false
  property bool workspaceLockLoaded: false
  property string workspaceLockName: ""
  property string workspaceLockFeedback: ""

  property var status: null
  property var runtimeEvidence: null
  property var installCompletion: null
  property bool statusResolved: false
  property bool statusLoadValid: false
  property bool installCompletionResolved: false
  property var graph: null
  // The graph generation the current status names.  `graph` holds the watched
  // file's latest validated bytes and is withdrawn the instant that file
  // changes; `admittedGraph` is the last graph a validated status named, and
  // it is displayed only while that same status is still the current status.
  // The brainstem republishes graph.json several times a pulse and names the
  // final one in status.json seconds later; withholding the still-named
  // generation in between blanked the graph for ten seconds a minute.
  property var admittedGraph: null
  property var thoughts: []
  property bool thoughtsResolved: false
  property bool thoughtsLoadValid: false
  property bool thoughtsEverAdmitted: false
  property bool stale: true
  property real nowMs: Date.now()
  property string hoverId: ""
  property string selectedId: ""
  property var hiddenKinds: ({})
  property real revealT: 1.0
  property bool playing: false
  // True while the graph has something to move; every input that can move
  // it sets it, and the frame loop clears it once the layout has settled.
  property bool layoutLive: true
  onPlayingChanged: layoutLive = true
  // Inspection changes ink, not node positions. A stationary pointer must
  // not keep the expensive graph/label canvas painting every display frame.
  onEffIdChanged: graphCanvas.requestPaint()
  onHiddenKindsChanged: graphCanvas.requestPaint()
  property string verifyMsg: ""
  property bool verifyOk: false
  property string graphBoundary: ""
  property string statusBoundary: ""
  property string thoughtsBoundary: ""
  property bool readyChecked: false
  property bool readyOk: false
  property string readyDetail: ""
  property var continuity: null
  property bool continuityReceiptAuthenticated: false
  property string continuityBoundary: ""
  property var continuitySchedule: null
  property string continuityScheduleBoundary: ""
  property bool continuitySheetOpen: false
  property bool continuityExpanded: false
  property string continuityPage: "overview"
  property bool restoreConfirmOpen: false
  property string continuityActionMsg: ""
  property bool continuityActionOk: false
  property string repositoryInput: ""
  property string recoveryKeyPathInput: ""
  property string identityKeyOutputPathInput: ""
  property string environmentFileInput: ""
  property string restoreSnapshotInput: ""
  property string restorePhraseInput: ""
  property string restorePreparedSnapshotInput: ""
  property string restoreLedgerHeadInput: ""
  property bool restoreReceiptReadoptAck: false
  property string restoreIdentityKeyPathInput: ""
  property bool restoreVerificationPending: false
  property bool restoreCorrelationLost: false
  property string restoreRequestId: ""
  property string restoreExpectedPreparedId: ""
  property bool setupLaunchRequested: false
  property bool setupTerminalPresented: false
  property bool setupTerminalMissing: false
  property real setupRequestedAtSec: 0
  property string setupAttemptId: ""
  // How long this cockpit has continuously observed one unchanged
  // `installing` record.  Deliberately NOT cleared by open()/close(): the
  // whole point is that it outlives a cockpit summon, because the failure it
  // catches — an installer that died — is invisible within any one summon.
  property string installingRecordKey: ""
  property real installingObservedAtMs: 0
  property bool installCompletionPublicationChanged: false
  readonly property int continuityInputMaxLength: 4096
  readonly property int continuityResponseMaxLength: 65536
  readonly property int continuityAuthorityPollInterval: 60000
  readonly property int verificationResponseMaxLength: 65536

  readonly property string effId: hoverId !== "" ? hoverId : selectedId
  readonly property string statePath:
    (Quickshell.env("HOME") || "") + "/.local/state/sia"
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
  readonly property string setupPresencePath:
    (Quickshell.env("XDG_RUNTIME_DIR") || "")
      + "/khephri.sia-first-light/terminal.json"
  readonly property string pluginVersion:
    root.manifest && typeof root.manifest.version === "string"
      && root.manifest.version !== "" ? root.manifest.version
      : Model.releaseVersion()
  readonly property string pluginRoot:
    String(Qt.resolvedUrl(".")).replace(/^file:\/\//, "").replace(/\/$/, "")
  readonly property string setupHelperPath:
    root.pluginRoot + "/bin/sia-setup"
  readonly property string runtimeLifecycle:
    Model.runtimeLifecycle(root.runtimeEvidence, root.pluginVersion)
  readonly property string releaseLifecycle:
    !root.statusResolved || !root.installCompletionResolved ? "checking"
      : Model.guidedLifecycle(root.runtimeEvidence,
                              root.installCompletion, root.pluginVersion)
  readonly property bool setupRequired: root.releaseLifecycle !== "ready"
  // Remember presentation history only; this never admits data or actions.
  // A watched-file refresh should show CHECKING in the existing cockpit,
  // not replace an established session with the first-install screen.
  property bool lifecycleWasReady: false
  readonly property bool showSetupGate: root.setupRequired
    && !(root.lifecycleWasReady && root.releaseLifecycle === "checking")
  // A caveat on the wording, never a lifecycle.  It cannot reach
  // releaseLifecycle, so no timeout can move this gate to ready, and it
  // asserts nothing about the installer beyond what SIA has observed.
  readonly property bool installerProgressUnobserved:
    root.releaseLifecycle === "installing"
      && Model.installingProgressUnobserved(root.installingObservedAtMs,
                                            root.nowMs)
  readonly property bool setupActionAllowed:
    ["setup", "installing", "update", "repair"]
      .indexOf(root.releaseLifecycle) !== -1
  readonly property string fontFamily: Style.font.family
  readonly property color bg: Color.background
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
    releaseLifecycle !== "ready" ? releaseLifecycle
      : stale ? "stale"
      : (statusLoadValid && status ? status.state : "unknown")
  readonly property string eventsToday:
    root.statusLoadValid && root.status
      ? String(root.status.events_today) : "—"
  // Keep rejected last-good bytes available to the boundary text, but never
  // let a card or action consume them as the current resident publication.
  readonly property var currentStatus: root.currentStatusSnapshot()
  readonly property var currentGraph: root.currentGraphSnapshot()
  readonly property var snap:
    currentGraph && currentGraph.snapshot ? currentGraph.snapshot : null
  readonly property real staleAfterSec: configuredStaleAfterSec()

  LiveView {
    id: liveLoopView
    statusSnapshot: root.statusLoadValid ? root.status : null
    enabled: root.opened && !root.playing && root.releaseLifecycle === "ready"
      && root.statusLoadValid && !root.stale
    staleAfterSec: root.staleAfterSec
  }
  readonly property string pluginId:
    root.manifest && typeof root.manifest.id === "string"
      && root.manifest.id !== "" ? root.manifest.id : "khephri.sia"
  readonly property string focusedWorkspaceName:
    root.workspaceName(Hyprland.focusedWorkspace)
  readonly property bool workspaceLockActive: root.workspaceLockName !== ""
  readonly property bool workspaceLockMismatch:
    root.workspaceLockActive && root.focusedWorkspaceName !== ""
      && root.focusedWorkspaceName !== root.workspaceLockName
  readonly property bool cockpitVisible:
    root.opened && !root.workspaceLockMismatch
  // Let the compositor move the finished surface. Repainting a full-screen
  // opacity/translation every frame stalls the software Qt renderer.
  Timer {
    id: presentationHold
    interval: 450
    onTriggered: {
      // The keepLoaded file watchers already withdraw changed publications.
      // Refresh again after arrival instead of parsing every snapshot while
      // the first surface is being painted.
      statusFile.reload(); installCompletionFile.reload()
      graphFile.reload(); thoughtsFile.reload()
      continuityFile.reload()
      continuityScheduleRefresh.restart()
      graphCanvas.requestPaint()
    }
  }
  readonly property bool continuityStale:
    Model.continuityStale(root.continuity, root.nowMs,
                          Model.continuityStaleAfterSec())
  readonly property var currentContinuity:
    !root.continuityStale && root.continuityBoundary === ""
      && root.continuityReceiptAuthenticated
      ? root.continuity : null
  readonly property string continuityState:
    root.currentContinuity ? root.currentContinuity.state : "unknown"
  readonly property color continuityColor: {
    if (root.continuityStale || root.continuityBoundary !== "")
      return root.urgent
    if (root.restoreCorrelationLost) return root.urgent
    if (root.restoreVerificationPending) return root.accent
    var tone = Model.continuityTone(root.continuityState)
    if (tone === "good" || tone === "busy") return root.accent
    if (tone === "danger") return root.urgent
    return Qt.alpha(root.fg, 0.62)
  }

  function isNonNegativeCount(value) {
    return typeof value === "number" && isFinite(value)
      && Math.floor(value) === value && value >= 0
      && value <= 9007199254740991
  }

  function currentStatusSnapshot() {
    return root.statusLoadValid ? root.status : null
  }

  function currentGraphSnapshot() {
    if (root.graphBoundary === ""
        && Model.snapshotGenerationsMatch(root.currentStatus, root.graph))
      return root.graph
    // A newer graph publication is on disk — pending validation, or validated
    // but not yet named by any status.  The current status still names the
    // admitted generation, so that pair remains the combined snapshot claim.
    var newerPublication = root.graphBoundary === ""
      ? !!root.graph
      : /pending validation$/.test(root.graphBoundary)
    if (newerPublication
        && Model.snapshotGenerationsMatch(root.currentStatus,
                                          root.admittedGraph))
      return root.admittedGraph
    return null
  }

  function isPlainRecord(value) {
    return !!value && typeof value === "object" && !Array.isArray(value)
  }

  function validLedgerSummary(ledger) {
    return Model.residentLedgerSummaryShape(ledger)
  }

  function validStatusSnapshot(snapshot) {
    // Model owns the producer's shared status contract.  Cockpit adds only
    // the fields this surface alone renders unguarded.
    return Model.residentStatusShape(snapshot)
      && root.isNonNegativeCount(snapshot.pages)
      && root.isNonNegativeCount(snapshot.graph_edges)
      && root.isNonNegativeCount(snapshot.pulse_seq)
      && root.validLedgerSummary(snapshot.ledger)
  }

  function validOriginLabel(value) {
    return ["evidence", "derived", "model", "legacy-unlabeled"]
      .indexOf(value) !== -1
  }

  function validGraphString(value, limit, nonempty) {
    var length = Model.strictStringLength(value)
    if (length < 0 || length > limit) return false
    return nonempty !== true || (length > 0 && value.trim() !== "")
  }

  function validGraphSlug(value) {
    return Model.canonicalCorpusSlug(value)
  }

  function validGraphSnapshot(candidate, nowMs) {
    if (!Model.recordHasExactly(candidate, [
          "v", "ts", "publication_id", "nodes", "edges", "pages_total",
          "pages_total_complete", "snapshot"
        ]) || candidate.v !== 2
        || !Model.timestampObservedBy(candidate.ts, nowMs)
        || !/^[0-9a-f]{32}$/.test(candidate.publication_id)
        || !root.isNonNegativeCount(candidate.pages_total)
        || typeof candidate.pages_total_complete !== "boolean"
        || !Array.isArray(candidate.nodes) || candidate.nodes.length > 260
        || !Array.isArray(candidate.edges) || candidate.edges.length > 4096
        || !Model.recordHasExactly(candidate.snapshot, [
          "complete", "truncated", "omitted_nodes", "omitted_edges",
          "omissions_imply_absence", "aged_out", "counts_by_kind",
          "failed_ops", "window_days"
        ])) return false
    var snapshot = candidate.snapshot
    if (typeof snapshot.complete !== "boolean"
        || !root.isNonNegativeCount(snapshot.truncated)
        || !root.isNonNegativeCount(snapshot.omitted_nodes)
        || !root.isNonNegativeCount(snapshot.omitted_edges)
        || typeof snapshot.omissions_imply_absence !== "boolean"
        || !root.isNonNegativeCount(snapshot.aged_out)
        || snapshot.window_days !== 14
        || !root.isPlainRecord(snapshot.counts_by_kind)
        || !Array.isArray(snapshot.failed_ops)
        || snapshot.failed_ops.length > 1024) return false
    if (snapshot.complete !== (snapshot.failed_ops.length === 0)
        || (snapshot.complete && !candidate.pages_total_complete)
        || snapshot.omissions_imply_absence !== false
        || snapshot.omitted_nodes !== snapshot.truncated
        || (snapshot.omitted_edges > 0
            && candidate.edges.length !== 4096)) return false
    for (var failureIndex = 0;
         failureIndex < snapshot.failed_ops.length; failureIndex++)
      if (!Model.inertStatusString(
            snapshot.failed_ops[failureIndex], 2000, true)
          || snapshot.failed_ops.indexOf(snapshot.failed_ops[failureIndex])
             !== failureIndex) return false
    var ids = ({})
    var observedKinds = ({})
    var expectedIn = ({})
    var expectedOut = ({})
    var edgeKeys = ({})
    for (var nodeIndex = 0; nodeIndex < candidate.nodes.length; nodeIndex++) {
      var node = candidate.nodes[nodeIndex]
      if (!Model.recordHasExactly(
            node, ["id", "t", "title", "ts", "origin",
                   "deg", "din", "dout"])
          || !root.validGraphSlug(node.id)
          || !root.validGraphString(node.t, 200, true)
          || !/^[a-z0-9][a-z0-9._-]*$/.test(node.t)
          || !Model.inertStatusString(node.title, 200, true)
          || !Model.timestampObservedBy(node.ts, nowMs)
          || !root.validOriginLabel(node.origin)
          || !root.isNonNegativeCount(node.deg)
          || !root.isNonNegativeCount(node.din)
          || !root.isNonNegativeCount(node.dout)) return false
      var nodeKey = "$" + node.id
      if (ids[nodeKey] === true) return false
      ids[nodeKey] = true
      expectedIn[nodeKey] = 0
      expectedOut[nodeKey] = 0
      var kindKey = "$" + node.t
      observedKinds[kindKey] = (observedKinds[kindKey] || 0) + 1
    }
    for (var edgeIndex = 0; edgeIndex < candidate.edges.length; edgeIndex++) {
      var edge = candidate.edges[edgeIndex]
      if (!Model.recordHasExactly(edge, ["s", "d", "t", "why"])
          || typeof edge.s !== "string"
          || typeof edge.d !== "string"
          || !root.validGraphString(edge.t, 200, true)
          || !/^[a-z0-9][a-z0-9._-]*$/.test(edge.t)
          || !Model.inertStatusString(edge.why, 90, false)) return false
      var sourceKey = "$" + edge.s
      var destinationKey = "$" + edge.d
      var edgeKey = "$" + JSON.stringify([edge.s, edge.d, edge.t])
      if (ids[sourceKey] !== true || ids[destinationKey] !== true
          || edgeKeys[edgeKey] === true) return false
      edgeKeys[edgeKey] = true
      expectedOut[sourceKey] += 1
      expectedIn[destinationKey] += 1
    }
    for (nodeIndex = 0; nodeIndex < candidate.nodes.length; nodeIndex++) {
      node = candidate.nodes[nodeIndex]
      nodeKey = "$" + node.id
      if (node.din !== expectedIn[nodeKey]
          || node.dout !== expectedOut[nodeKey]
          || node.deg !== expectedIn[nodeKey] + expectedOut[nodeKey])
        return false
    }
    var countKinds = Object.keys(snapshot.counts_by_kind)
    var observedKindNames = Object.keys(observedKinds)
    if (countKinds.length !== observedKindNames.length) return false
    for (var countKindIndex = 0;
         countKindIndex < countKinds.length; countKindIndex++) {
      var countKind = countKinds[countKindIndex]
      if (!root.validGraphString(countKind, 200, true)
          || !/^[a-z0-9][a-z0-9._-]*$/.test(countKind)
          || !root.isNonNegativeCount(snapshot.counts_by_kind[countKind])
          || snapshot.counts_by_kind[countKind]
             !== (observedKinds["$" + countKind] || 0))
        return false
    }
    for (var observedKindIndex = 0;
         observedKindIndex < observedKindNames.length; observedKindIndex++) {
      var observedKind = observedKindNames[observedKindIndex]
      if (snapshot.counts_by_kind[observedKind.substring(1)]
          !== observedKinds[observedKind])
        return false
    }
    return snapshot.aged_out <= candidate.pages_total
      && snapshot.truncated <= candidate.pages_total - snapshot.aged_out
      && candidate.nodes.length === candidate.pages_total
         - snapshot.aged_out - snapshot.truncated
  }

  function graphHasNode(id) {
    return root.nodeById(id) !== null
  }

  function projectionDebtKeys() {
    var debt = root.currentStatus && root.currentStatus.projection_debt
      ? root.currentStatus.projection_debt : null
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
    return root.projectionDebtKnownFor(root.currentStatus)
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

  function processAttemptIsCurrent(activeAttempt, attempt) {
    // The object identity is the generation.  A basis, pid or mutable flag is
    // not enough: a canceled process may deliver collectors and exit signals
    // after another attempt for the same published snapshot has started.
    return !!attempt && activeAttempt === attempt
      && attempt.acceptResults === true
  }

  function snapshotBasis() {
    var status = root.currentStatus
    var graph = root.currentGraph
    if (!graph
        || !status || !status.ledger
        || !Model.publicationId(status.publication_id, false)
        || !Model.publicationId(graph.publication_id, false)
        || !root.validLedgerSummary(status.ledger)
        || status.ledger.seq <= 0
        || !/^[0-9a-f]{12}$/.test(status.ledger.head)) return ""
    // Property insertion order matches the CLI's sorted canonical receipt.
    return JSON.stringify({
      graph_publication_id: graph.publication_id,
      ledger_head: status.ledger.head,
      ledger_seq: status.ledger.seq,
      status_publication_id: status.publication_id
    })
  }

  function clearVerification() {
    root.verifyMsg = ""
    root.verifyOk = false
    verifyProc.cancel()
  }

  // Quickshell 0.3 FileView.reload() does not queue another read when one for
  // the same path is already in flight.  A watched change must therefore
  // survive until the current callback has returned (FileView still owns the
  // live reader while emitting loaded/loadFailed), then request one more read.
  function settleWatchedFileRefresh(view) {
    if (!view || view.refreshPending !== true) return false
    view.refreshPending = false
    Qt.callLater(function() {
      if (view) view.reload()
    })
    return true
  }

  function startVerification() {
    root.clearVerification()
    var current = root.snapshotBasis()
    if (current === "") {
      root.verifyMsg = "CHAIN VERIFICATION INCOMPLETE — snapshots are not one generation"
      return
    }
    verifyProc.start(current)
  }

  function projectionDebtDetail() {
    var keys = root.projectionDebtKeys()
    if (!keys.length) return ""
    var debt = root.currentStatus.projection_debt
    var parts = []
    for (var i = 0; i < keys.length; i++)
      parts.push(keys[i] + ": " + String(debt[keys[i]]))
    return parts.join(" · ")
  }

  // A boundary that names a routine revalidation beat is context, not an
  // alarm; an unavailable or rejected source keeps the urgent colour.
  function boundaryColor(text) {
    return /pending validation$/.test(text)
      ? Qt.alpha(root.fg, 0.55) : root.urgent
  }

  function graphSnapshotText() {
    var shown = root.currentGraph
    if (shown && shown !== root.graph) {
      // The admitted generation the current status names, while a newer
      // graph publication waits for the status that will name it.
      return "graph published "
        + Model.timeAgo(shown.ts, root.nowMs) + " · "
        + (shown.snapshot && shown.snapshot.complete === true
           ? "complete" : "partial")
        + " · newer graph publication awaiting its status"
    }
    if (root.graphBoundary !== "") return root.graphBoundary
    if (!root.graph || !root.graph.ts) return "no graph snapshot"
    if (!root.currentStatus)
      return "last good graph; resident status unavailable"
    if (!Model.snapshotGenerationsMatch(root.currentStatus, root.graph))
      return "mixed status/graph generations; no combined snapshot claim"
    var complete = root.snap && root.snap.complete === true
    return "graph published "
      + Model.timeAgo(root.currentGraph.ts, root.nowMs)
      + " · " + (complete ? "complete" : "partial")
  }

  function ledgerTransitionText() {
    var transition = root.currentStatus
      && root.currentStatus.ledger_transition
      ? root.currentStatus.ledger_transition : null
    if (!transition || !transition.state) return "ledger transition unknown"
    return "ledger " + transition.state
  }

  function ledgerSummaryText(ledger) {
    if (!ledger || ledger.seq === 0 || ledger.head === "")
      return "signed ledger head unavailable"
    return Model.chainGlyph() + " ledger seq " + ledger.seq
      + " · " + ledger.head + "…"
  }

  function dreamSummaryText(dream, nowMs) {
    if (!dream || typeof dream !== "object" || Array.isArray(dream)
        || Object.keys(dream).length === 0) return ""
    if (typeof dream.attempt === "string") {
      var attemptAge = Model.timeAgo(dream.attempt, nowMs)
      var attemptWhen = attemptAge !== "" ? attemptAge
        : (dream.attempt !== "" ? dream.attempt : "time unavailable")
      var failure = Model.dreamGlyph() + " maintenance attempt " + attemptWhen
        + " · " + dream.status
      if (dream.summary !== "") failure += " · " + dream.summary
      if (dream.last !== "") {
        var priorAge = Model.timeAgo(dream.last, nowMs)
        var priorWhen = priorAge !== "" ? priorAge : dream.last
        failure += " · prior success " + priorWhen
      }
      return failure
    }
    if (typeof dream.last !== "string" || dream.last === "") return ""
    var age = Model.timeAgo(dream.last, nowMs)
    var when = age !== "" ? age : dream.last
    var result = Model.dreamGlyph() + " maintenance finished " + when
      + " · " + dream.status
    if (dream.summary !== "") result += " · " + dream.summary
    return result
  }

  function takeSummaryAvailable(takes) {
    return root.isPlainRecord(takes) && Object.keys(takes).length > 0
  }

  function takeSummaryText(takes) {
    if (!root.takeSummaryAvailable(takes))
      return "prediction summary unavailable"
    var result = takes.open + " open prediction"
      + (takes.open === 1 ? "" : "s")
    if (takes.due > 0) result += " · " + takes.due + " DUE"
    result += " · " + takes.resolved + " resolved"
    if (takes.unresolvable > 0)
      result += " · " + takes.unresolvable + " unresolvable (excluded)"
    if (takes.invalid_resolved > 0)
      result += " · " + takes.invalid_resolved + " invalid resolved row"
        + (takes.invalid_resolved === 1 ? "" : "s") + " excluded"
    if (takes.invalid_records > 0)
      result += " · " + takes.invalid_records
        + " malformed/unknown-status row"
        + (takes.invalid_records === 1 ? "" : "s") + " excluded"
    return result
  }

  function beliefCardVisibleFor(status) {
    if (!root.isPlainRecord(status)) return false
    var takes = status.takes
    var hasTakeRows = root.takeSummaryAvailable(takes)
      && (takes.open > 0 || takes.resolved > 0
          || takes.unresolvable > 0 || takes.invalid_resolved > 0
          || takes.invalid_records > 0)
    return hasTakeRows
      || (Array.isArray(status.bench_trend)
          && status.bench_trend.length > 0)
  }

  function statusErrorRows(errors) {
    if (!root.isPlainRecord(errors)) return []
    var result = []
    var names = Object.keys(errors).sort()
    for (var nameIndex = 0; nameIndex < names.length; nameIndex++) {
      var name = names[nameIndex]
      var detail = errors[name]
      if (typeof detail === "string") {
        result.push("✗ " + name + ": " + detail)
        continue
      }
      if (!Array.isArray(detail) || detail.length === 0) {
        result.push("✗ " + name + ": no detail recorded")
        continue
      }
      for (var detailIndex = 0;
           detailIndex < detail.length; detailIndex++) {
        var row = detail[detailIndex]
        var field = row.file !== undefined ? "file" : "config"
        result.push("✗ " + name + " · " + field + " " + row[field]
          + ": " + row.error)
      }
    }
    return result
  }

  function continuityStateText() {
    if (root.continuityBoundary !== "") return "STATUS UNAVAILABLE"
    if (!root.continuity) return "STATUS UNAVAILABLE"
    if (root.continuityStale) return "STATUS STALE"
    if (root.restoreCorrelationLost) return "NEEDS ATTENTION"
    if (root.restoreVerificationPending) return "RESTORE VERIFYING"
    if (!root.currentContinuity) return "STATUS UNAVAILABLE"
    return Model.continuityStateLabel(root.currentContinuity.state)
  }

  function continuityRepositoryText() {
    if (root.continuityBoundary !== "")
      return "Repository status unavailable; last good value withheld."
    if (!root.continuity)
      return "No continuity status has been published."
    if (root.continuityStale)
      return "The last continuity publication is stale."
    if (!root.currentContinuity)
      return "No continuity status has been published."
    var display = String(
      root.currentContinuity.repository_display || "").trim()
    if (display !== "") return display
    return root.currentContinuity.state === "unconfigured"
      ? "Choose a recovery repository to begin."
      : "Repository identity is not available."
  }

  function continuityLatestText() {
    if (root.continuityBoundary !== "")
      return "Recovery-copy status unavailable; last good value withheld."
    if (!root.continuity)
      return "No recovery copy has been recorded."
    if (root.continuityStale)
      return "The last recovery-copy publication is stale."
    var latest = root.currentContinuity
      ? root.currentContinuity.latest : null
    if (!latest) return "No recovery copy has been recorded."
    var age = Model.timeAgo(latest.created_at, root.nowMs)
    var when = age !== "" ? age : latest.created_at
    var classification = Model.continuityLatestReady(
      latest, root.continuityReceiptAuthenticated)
      ? "Recovery-ready copy · "
      : latest.verified
        ? "Verified recovery material · "
        : "Unverified copy · "
    return classification
      + when + " · " + latest.profile
  }

  function continuityDetailText() {
    if (root.continuityBoundary !== "") return root.continuityBoundary
    if (!root.continuity)
      return "The continuity worker is not reporting."
    if (root.continuityStale)
      return "Last good continuity status is stale; no recovery state is current."
    if (!root.currentContinuity)
      return "The continuity worker is not reporting."
    var detail = String(root.currentContinuity.detail || "").trim()
    return detail !== "" ? detail : root.continuityLatestText()
  }

  function continuityScheduleStateText() {
    if (root.continuityState === "unconfigured")
      return "AUTOMATIC BACKUP · AFTER SETUP"
    if (!root.continuitySchedule) {
      if (continuityScheduleProc.checking)
        return "AUTOMATIC BACKUP · CHECKING"
      return root.continuityScheduleBoundary !== ""
        ? "AUTOMATIC BACKUP · STATUS UNAVAILABLE"
        : "AUTOMATIC BACKUP · CHECKING"
    }
    return root.continuitySchedule.automatic
      ? "AUTOMATIC BACKUP · ON"
      : "AUTOMATIC BACKUP · NEEDS ATTENTION"
  }

  function continuityScheduleColor() {
    if (root.continuitySchedule && root.continuitySchedule.automatic)
      return root.accent
    if (continuityScheduleProc.checking)
      return Qt.alpha(root.fg, 0.52)
    if (root.continuityState !== "unconfigured"
        && (root.continuitySchedule
            || root.continuityScheduleBoundary !== ""))
      return root.urgent
    return Qt.alpha(root.fg, 0.52)
  }

  function continuityTimerState(timer) {
    if (!timer) return "status unavailable"
    if (!timer.enabled) return "disabled"
    return timer.active ? "active" : "not running"
  }

  function continuityTriggerText(value, emptyText, relative) {
    var timestamp = Date.parse(value || "")
    if (!(timestamp > 0)) return emptyText
    if (relative) {
      var age = Model.timeAgo(value, root.nowMs)
      if (age !== "") return age
    }
    return Qt.formatDateTime(new Date(timestamp), "ddd HH:mm")
  }

  function continuityHourlyText() {
    var schedule = root.continuitySchedule
    if (!schedule) {
      if (root.continuityState === "unconfigured")
        return "Every hour after setup · no button needed"
      if (continuityScheduleProc.checking)
        return "Checking the hourly timer…"
      return root.continuityScheduleBoundary !== ""
        ? root.continuityScheduleBoundary
        : "Checking the hourly timer…"
    }
    var timer = schedule.upload
    return "Every hour · no button needed · "
      + root.continuityTimerState(timer)
      + "\nLast start "
      + root.continuityTriggerText(
          timer.last_trigger_at, "not yet", true)
      + " · next "
      + root.continuityTriggerText(
          timer.next_trigger_at, "not scheduled", false)
  }

  function continuityWeeklyText() {
    if (root.continuityState === "unconfigured")
      return "Weekly deep restore-check verification begins after setup."
    var schedule = root.continuitySchedule
    if (!schedule)
      return "Weekly deep restore-check verification"
    var timer = schedule.verification
    return "Weekly deep restore check · "
      + root.continuityTimerState(timer)
      + "\nLast check start "
      + root.continuityTriggerText(
          timer.last_trigger_at, "not yet", true)
      + " · next "
      + root.continuityTriggerText(
          timer.next_trigger_at, "not scheduled", false)
  }

  function continuitySleepText() {
    if (root.continuityState === "unconfigured")
      return "Persistent catch-up and no-wake protection begin after setup."
    var schedule = root.continuitySchedule
    if (!schedule)
      return "Sleep/off policy is shown after schedule verification."
    if (schedule.upload.persistent && schedule.verification.persistent
        && !schedule.upload.wake_system
        && !schedule.verification.wake_system) {
      var checked = root.continuityTriggerText(
        schedule.observed_at, "time unavailable", true)
      return "Schedule checked " + checked
        + " · Sleep/off: never wakes this computer · a missed run catches up after you return."
    }
    return "Sleep/catch-up policy differs from SIA's protected default."
  }

  function clearContinuityInputs() {
    root.repositoryInput = ""
    root.recoveryKeyPathInput = ""
    root.identityKeyOutputPathInput = ""
    root.environmentFileInput = ""
    root.restoreSnapshotInput = ""
    root.clearRestoreCeremony()
  }

  function preparedRestore() {
    return root.currentContinuity && root.currentContinuity.prepared
      ? root.currentContinuity.prepared : null
  }

  function clearRestoreCeremony() {
    root.restorePhraseInput = ""
    root.restorePreparedSnapshotInput = ""
    root.restoreLedgerHeadInput = ""
    root.restoreReceiptReadoptAck = false
    root.restoreIdentityKeyPathInput = ""
  }

  function restoreCeremonyReady() {
    var prepared = root.preparedRestore()
    if (root.restoreVerificationPending || root.restoreCorrelationLost
        || !prepared
        || !Model.continuityCanApply(
          root.currentContinuity,
          root.continuityReceiptAuthenticated)) return false
    return root.restorePhraseInput === "RESTORE"
      && root.restorePreparedSnapshotInput === prepared.snapshot_id
      && root.restoreLedgerHeadInput === prepared.ledger_head
      && root.restoreReceiptReadoptAck
      && (prepared.identity_matches
          || root.restoreIdentityKeyPathInput.trim() !== "")
  }

  function focusContinuityPage() {
    Qt.callLater(function() {
      if (!root.continuitySheetOpen || root.restoreConfirmOpen) return
      if (root.continuityPage === "setup") setupRepositoryField.forceActiveFocus()
      else if (root.continuityPage === "connect")
        connectRepositoryField.forceActiveFocus()
      else if (root.continuityPage === "restore") {
        if (Model.continuityCanApply(
              root.currentContinuity,
              root.continuityReceiptAuthenticated))
          restorePhraseField.forceActiveFocus()
        else if (root.continuityState === "restoring")
          continuityCloseButton.forceActiveFocus()
        else restoreSnapshotField.forceActiveFocus()
      }
      else if (Model.continuityCanBackUp(
                 root.currentContinuity,
                 root.continuityReceiptAuthenticated))
        continuityCloseButton.forceActiveFocus()
      else if (Model.continuityCanPrepare(
                 root.currentContinuity,
                 root.continuityReceiptAuthenticated)
               || Model.continuityCanApply(
                 root.currentContinuity,
                 root.continuityReceiptAuthenticated))
        overviewRestoreButton.forceActiveFocus()
      else if (!root.continuity
               || root.continuityState === "unconfigured")
        overviewSetupButton.forceActiveFocus()
      else continuityCloseButton.forceActiveFocus()
    })
  }

  function openContinuity(page) {
    root.continuityPage = page || "overview"
    root.continuitySheetOpen = true
    root.restoreConfirmOpen = false
    continuityScheduleRefresh.restart()
    if (root.continuityPage === "restore"
        && root.restoreSnapshotInput.trim() === ""
        && root.currentContinuity && root.currentContinuity.latest)
      root.restoreSnapshotInput = root.currentContinuity.latest.snapshot_id
    root.focusContinuityPage()
  }

  function closeContinuity() {
    root.restoreConfirmOpen = false
    root.continuitySheetOpen = false
    root.continuityPage = "overview"
    root.clearRestoreCeremony()
    Qt.callLater(function() {
      if (root.cockpitVisible) keyCatcher.forceActiveFocus()
    })
  }

  function continuityRefusal(message) {
    root.continuityActionOk = false
    root.continuityActionMsg = message
  }

  function requestBackupNow() {
    continuityProc.launch(["backup", "now"], "Extra copy")
  }

  function requestBackupCheck() {
    continuityProc.launch(["backup", "check"], "Check backup")
  }

  function requestSetup() {
    var repository = root.repositoryInput.trim()
    var recoveryKey = root.recoveryKeyPathInput.trim()
    var identityKey = root.identityKeyOutputPathInput.trim()
    var environmentFile = root.environmentFileInput.trim()
    if (repository === "" || recoveryKey === "" || identityKey === "") {
      root.continuityRefusal(
        "Repository, recovery-key, and offline identity-key output paths are required.")
      return
    }
    var args = ["backup", "setup", "--repository", repository,
                "--recovery-key-out", recoveryKey,
                "--identity-key-out", identityKey]
    if (environmentFile !== "")
      args = args.concat(["--environment-file", environmentFile])
    continuityProc.launch(args, "Set up backup")
  }

  function requestConnect() {
    var repository = root.repositoryInput.trim()
    var recoveryKey = root.recoveryKeyPathInput.trim()
    var environmentFile = root.environmentFileInput.trim()
    if (repository === "" || recoveryKey === "") {
      root.continuityRefusal(
        "Repository and recovery-key file paths are required.")
      return
    }
    var args = ["backup", "connect", "--repository", repository,
                "--recovery-key-file", recoveryKey]
    if (environmentFile !== "")
      args = args.concat(["--environment-file", environmentFile])
    continuityProc.launch(args, "Connect backup")
  }

  function requestRestorePrepare() {
    var snapshot = root.restoreSnapshotInput.trim()
    if (snapshot === "") {
      root.continuityRefusal("Choose a verified snapshot before preparing restore.")
      return
    }
    root.clearRestoreCeremony()
    continuityProc.launch(["restore", "prepare", snapshot], "Prepare restore")
  }

  function requestRestoreConfirmation() {
    var prepared = root.preparedRestore()
    if (root.restoreCorrelationLost) {
      root.continuityRefusal(
        "Restore correlation was lost. Inspect continuity status before any retry.")
      return
    }
    if (root.restoreVerificationPending) {
      root.continuityRefusal(
        "A restore is already waiting for readiness and SIA signed-ledger verification.")
      return
    }
    if (!prepared || !Model.continuityCanApply(
          root.currentContinuity,
          root.continuityReceiptAuthenticated)) {
      root.continuityRefusal(
        "Restore is not prepared. Prepare and verify the snapshot first.")
      return
    }
    if (root.restorePhraseInput !== "RESTORE") {
      root.continuityRefusal("Type RESTORE exactly to continue.")
      return
    }
    if (root.restorePreparedSnapshotInput !== prepared.snapshot_id) {
      root.continuityRefusal(
        "The typed snapshot ID does not match the prepared restore.")
      return
    }
    if (root.restoreLedgerHeadInput !== prepared.ledger_head) {
      root.continuityRefusal(
        "The typed ledger head does not match the prepared restore.")
      return
    }
    if (!root.restoreReceiptReadoptAck) {
      root.continuityRefusal(
        "Acknowledge corpus-receipt re-adoption before continuing.")
      return
    }
    if (!prepared.identity_matches
        && root.restoreIdentityKeyPathInput.trim() === "") {
      root.continuityRefusal(
        "This machine needs the offline identity-key file path.")
      return
    }
    continuityRestoreConfirm.selectedIndex = 0
    root.restoreConfirmOpen = true
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function cancelRestoreConfirmation() {
    root.restoreConfirmOpen = false
    root.clearRestoreCeremony()
    Qt.callLater(function() {
      if (root.continuitySheetOpen) restorePhraseField.forceActiveFocus()
    })
  }

  function confirmRestore() {
    var prepared = root.preparedRestore()
    root.restoreConfirmOpen = false
    if (!prepared || !root.restoreCeremonyReady()) {
      root.clearRestoreCeremony()
      root.continuityRefusal(
        "Restore ceremony changed or expired. Enter it again.")
      return
    }
    var identityKeyPath = root.restoreIdentityKeyPathInput.trim()
    var request = JSON.stringify({
      schema_version: 1,
      phrase: root.restorePhraseInput,
      snapshot_id: root.restorePreparedSnapshotInput,
      ledger_head: root.restoreLedgerHeadInput,
      corpus_receipt_re_adopt: true
    })
    var args = ["restore", "apply", prepared.prepared_id, "--confirm-stdin"]
    if (!prepared.identity_matches)
      args = args.concat(["--identity-key-file", identityKeyPath])
    if (continuityProc.launch(
        args, "Restore SIA", request, true, prepared.prepared_id))
      root.clearRestoreCeremony()
  }

  function validRestoreAcceptance(value, preparedId) {
    return root.isPlainRecord(value)
      && Model.recordHasExactly(value, [
        "schema_version", "accepted", "request_id", "operation",
        "prepared_id"
      ])
      && value.schema_version === 1
      && value.accepted === true
      && Model.validContinuityCorrelationId(value.request_id)
      && value.operation === "restore-apply"
      && Model.validContinuityCorrelationId(preparedId)
      && Model.validContinuityCorrelationId(value.prepared_id)
      && value.prepared_id === preparedId
  }

  function matchingRestoreOperation(status) {
    var operation = status && status.operation ? status.operation : null
    if (!operation || !Model.validContinuityOperation(operation)) return null
    return operation.request_id === root.restoreRequestId
        && operation.kind === "restore-apply"
        && operation.prepared_id === root.restoreExpectedPreparedId
      ? operation : null
  }

  function configuredPluginSettings() {
    const config = root.shell ? root.shell.shellConfig : null
    const layout = config && config.bar ? config.bar.layout : null
    const sections = ["left", "center", "right"]
    const pluginId = Util.canonicalWidgetId(root.pluginId)
    if (layout) {
      for (var s = 0; s < sections.length; s++) {
        const entries = layout[sections[s]]
        if (!Array.isArray(entries)) continue
        for (var i = 0; i < entries.length; i++) {
          const entry = entries[i]
          const id = Util.canonicalWidgetId(String(
            entry && entry.id !== undefined ? entry.id : entry || ""))
          if (id === pluginId)
            return root.copyPluginSettings(entry)
        }
      }
    }
    return root.configuredPluginArraySettings(config)
  }

  // ------------------------------------------------ continuity sheet
  Item {
        id: continuityLayer
        parent: keyCatcher
        anchors.fill: parent
        visible: root.continuitySheetOpen
        z: 20

        Rectangle {
          anchors.fill: parent
          color: Qt.alpha(Color.background, 0.7)
          MouseArea {
            anchors.fill: parent
            onClicked: {
              if (!root.restoreConfirmOpen) root.closeContinuity()
            }
          }
        }

        Ui.BorderSurface {
          id: continuitySheetCard
          anchors.centerIn: parent
          width: Math.min(parent.width - Style.spacing.panelPadding,
                          body.leftW + body.rightW)
          height: Math.min(parent.height - header.height,
                           continuitySheetCol.implicitHeight
                             + contentTopInset + contentBottomInset)
          color: Color.background
          borderSpec: Border.flat(root.continuityColor,
                                  Style.normalBorderWidth)
          padding: Style.spacing.panelPadding
          radius: Style.cornerRadius

          MouseArea { anchors.fill: parent; onClicked: {} }

          Flickable {
            id: continuitySheetScroll
            anchors.fill: parent
            anchors.leftMargin: continuitySheetCard.contentLeftInset
            anchors.rightMargin: continuitySheetCard.contentRightInset
            anchors.topMargin: continuitySheetCard.contentTopInset
            anchors.bottomMargin: continuitySheetCard.contentBottomInset
            contentWidth: width
            contentHeight: continuitySheetCol.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            Controls.ScrollBar.vertical: Controls.ScrollBar {
              policy: Controls.ScrollBar.AsNeeded
            }

            Column {
              id: continuitySheetCol
              width: continuitySheetScroll.width
              spacing: Style.spacing.lg

            Item {
              width: continuitySheetCol.width
              height: Math.max(sheetTitleCol.implicitHeight,
                               continuityCloseButton.implicitHeight)
              Column {
                id: sheetTitleCol
                anchors.left: parent.left
                anchors.right: continuityCloseButton.left
                anchors.rightMargin: Style.spacing.md
                spacing: Style.spacing.xs
                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: "SIA CONTINUITY"
                  color: root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                  font.bold: true
                }
                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: root.continuityPage === "setup"
                    ? "Create a verified recovery repository"
                    : root.continuityPage === "connect"
                      ? "Reconnect this local memory to an existing repository"
                      : root.continuityPage === "restore"
                        ? "Inspect, prepare, then deliberately restore"
                        : "Keep local memory recoverable beyond this computer"
                  color: Qt.alpha(root.fg, 0.52)
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
              }
              Ui.Button {
                id: continuityCloseButton
                anchors.right: parent.right
                anchors.top: parent.top
                text: "Close"
                fontSize: Style.font.caption
                bordered: true
                focusable: true
                Accessible.role: Accessible.Button
                Accessible.name: "Close continuity"
                Accessible.description:
                  "Return to the SIA cockpit without stopping accepted work"
                onClicked: root.closeContinuity()
              }
            }

            Rectangle {
              width: continuitySheetCol.width
              height: Style.normalBorderWidth
              color: Qt.alpha(root.continuityColor, 0.35)
            }

            // ---------------------------------------------------- overview
            Column {
              visible: root.continuityPage === "overview"
              width: continuitySheetCol.width
              spacing: Style.spacing.lg

              Item {
                width: parent.width
                height: Math.max(overviewState.implicitHeight,
                                 overviewStateMark.implicitHeight)
                Text {
                  id: overviewState
                  anchors.left: parent.left
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: root.continuityStateText()
                  color: root.continuityColor
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.subtitle
                  font.bold: true
                }
                Text {
                  id: overviewStateMark
                  anchors.right: parent.right
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: Model.continuityBarMark(
                    root.currentContinuity,
                    root.continuityReceiptAuthenticated)
                  color: root.continuityColor
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                }
              }

              Ui.BorderSurface {
                width: parent.width
                height: overviewAutomation.implicitHeight
                  + contentTopInset + contentBottomInset
                color: Qt.alpha(root.continuityScheduleColor(), 0.05)
                borderSpec: Border.flat(
                  Qt.alpha(root.continuityScheduleColor(), 0.28),
                  Style.normalBorderWidth)
                padding: Style.spacing.xl
                radius: Style.cornerRadius
                Column {
                  id: overviewAutomation
                  anchors.left: parent.left
                  anchors.right: parent.right
                  anchors.top: parent.top
                  anchors.leftMargin: parent.contentLeftInset
                  anchors.rightMargin: parent.contentRightInset
                  anchors.topMargin: parent.contentTopInset
                  spacing: Style.spacing.sm
                  Text {
                    width: parent.width
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    text: root.continuityScheduleStateText()
                    color: root.continuityScheduleColor()
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                    font.bold: true
                  }
                  Text {
                    width: parent.width
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    text: root.continuityHourlyText()
                    wrapMode: Text.WordWrap
                    color: Qt.alpha(root.fg, 0.72)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                  Text {
                    width: parent.width
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    text: root.continuityWeeklyText()
                    wrapMode: Text.WordWrap
                    color: Qt.alpha(root.fg, 0.62)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                  Text {
                    width: parent.width
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    text: root.continuitySleepText()
                    wrapMode: Text.WordWrap
                    color: Qt.alpha(root.fg, 0.54)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                  Text {
                    visible: root.continuityState !== "unconfigured"
                    width: parent.width
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    text: "Make extra copy now is optional. It uploads and immediately performs the deep repository restore check."
                    wrapMode: Text.WordWrap
                    color: Qt.alpha(root.fg, 0.54)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                }
              }

              Ui.BorderSurface {
                width: parent.width
                height: overviewFacts.implicitHeight
                  + contentTopInset + contentBottomInset
                color: Qt.alpha(root.continuityColor, 0.05)
                borderSpec: Border.flat(Qt.alpha(root.continuityColor, 0.24),
                                        Style.normalBorderWidth)
                padding: Style.spacing.xl
                radius: Style.cornerRadius
                Column {
                  id: overviewFacts
                  anchors.left: parent.left
                  anchors.right: parent.right
                  anchors.top: parent.top
                  anchors.leftMargin: parent.contentLeftInset
                  anchors.rightMargin: parent.contentRightInset
                  anchors.topMargin: parent.contentTopInset
                  spacing: Style.spacing.sm
                  Text {
                    width: parent.width
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    text: root.continuityRepositoryText()
                    elide: Text.ElideMiddle
                    color: root.fg
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                  }
                  Text {
                    width: parent.width
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    text: root.continuityLatestText()
                    wrapMode: Text.WordWrap
                    color: Qt.alpha(root.fg, 0.7)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                  Text {
                    width: parent.width
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    text: root.continuityDetailText()
                    wrapMode: Text.WordWrap
                    color: root.continuityBoundary !== ""
                      || root.continuityState === "failed"
                      || root.continuityState === "blocked"
                        ? root.urgent : Qt.alpha(root.fg, 0.58)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                  Text {
                    width: parent.width
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    text: "Verification checks the repository copy. Off-machine placement, immutability, and retention remain operator-owned."
                    wrapMode: Text.WordWrap
                    color: Qt.alpha(root.fg, 0.5)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                }
              }

              Flow {
                width: parent.width
                spacing: Style.spacing.md
                Ui.Button {
                  id: overviewSetupButton
                  visible: !root.continuity
                    || root.continuityState === "unconfigured"
                  text: "Set up new"
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Set up a new SIA backup"
                  Accessible.description:
                    "Create a repository with separate recovery and offline identity key files"
                  onClicked: root.openContinuity("setup")
                }
                Ui.Button {
                  id: overviewConnectButton
                  visible: !root.continuity
                    || root.continuityState === "unconfigured"
                  text: "Connect existing"
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Connect an existing SIA backup"
                  Accessible.description:
                    "Reconnect with an existing recovery key file"
                  onClicked: root.openContinuity("connect")
                }
                Ui.Button {
                  id: overviewBackupButton
                  visible: !!root.currentContinuity
                    && root.continuityState !== "unconfigured"
                  enabled: Model.continuityCanBackUp(
                    root.currentContinuity,
                    root.continuityReceiptAuthenticated)
                    && !continuityProc.working
                  text: continuityProc.working
                    ? "Requesting…" : "Make extra copy now"
                  foreground: enabled ? root.fg : Qt.alpha(root.fg, 0.35)
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Make an extra SIA backup now"
                  Accessible.description:
                    "Optional extra copy with immediate deep repository verification; hourly backups continue automatically"
                  onClicked: root.requestBackupNow()
                }
                Ui.Button {
                  id: overviewCheckButton
                  visible: !!root.currentContinuity
                    && root.continuityState !== "unconfigured"
                  enabled: Model.continuityCanCheck(
                    root.currentContinuity,
                    root.continuityReceiptAuthenticated)
                    && !continuityProc.working
                  text: "Check backup"
                  foreground: enabled ? root.fg : Qt.alpha(root.fg, 0.35)
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Check SIA backup"
                  Accessible.description:
                    "Verify the encrypted recovery repository"
                  onClicked: root.requestBackupCheck()
                }
                Ui.Button {
                  id: overviewRestoreButton
                  visible: !!root.currentContinuity
                    && root.continuityState !== "unconfigured"
                  enabled: (Model.continuityCanPrepare(
                              root.currentContinuity,
                              root.continuityReceiptAuthenticated)
                            || Model.continuityCanApply(
                              root.currentContinuity,
                              root.continuityReceiptAuthenticated))
                    && !continuityProc.working
                  text: "Restore…"
                  foreground: enabled ? root.fg : Qt.alpha(root.fg, 0.35)
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Restore SIA"
                  Accessible.description:
                    "Review a verified snapshot before restoring"
                  onClicked: root.openContinuity("restore")
                }
              }
            }

            // ------------------------------------------------------- setup
            Column {
              visible: root.continuityPage === "setup"
              width: continuitySheetCol.width
              spacing: Style.spacing.md

              Text {
                width: parent.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "Repository"
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Ui.TextField {
                id: setupRepositoryField
                width: parent.width
                maximumLength: root.continuityInputMaxLength
                text: root.repositoryInput
                placeholderText: "Repository path or endpoint"
                Accessible.name: "Backup repository"
                Accessible.description:
                  "Path or endpoint for the new encrypted backup repository"
                onTextChanged: root.repositoryInput = text
              }
              Text {
                width: parent.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "Recovery key output"
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Ui.TextField {
                width: parent.width
                maximumLength: root.continuityInputMaxLength
                text: root.recoveryKeyPathInput
                placeholderText: "Path on separate recovery media"
                Accessible.name: "Recovery key output path"
                Accessible.description:
                  "Where SIA should create the recovery key file"
                onTextChanged: root.recoveryKeyPathInput = text
              }
              Text {
                width: parent.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "Offline identity key output"
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Ui.TextField {
                width: parent.width
                maximumLength: root.continuityInputMaxLength
                text: root.identityKeyOutputPathInput
                placeholderText: "Path on separate offline media"
                Accessible.name: "Offline identity key output path"
                Accessible.description:
                  "Where SIA should create the machine identity recovery key"
                onTextChanged: root.identityKeyOutputPathInput = text
              }
              Text {
                width: parent.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "Keep the offline identity key separate from this computer, the repository, and the recovery key. It is never uploaded."
                wrapMode: Text.WordWrap
                color: root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                width: parent.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "Environment file · optional"
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Ui.TextField {
                width: parent.width
                maximumLength: root.continuityInputMaxLength
                text: root.environmentFileInput
                placeholderText: "Path to repository environment file"
                Accessible.name: "Backup environment file"
                Accessible.description:
                  "Optional path containing repository environment settings"
                onTextChanged: root.environmentFileInput = text
              }
              Text {
                width: parent.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "Keep both key files outside this computer and outside the repository. Only file paths—not key contents—enter this cockpit. Destination resilience and retention remain operator-owned."
                wrapMode: Text.WordWrap
                color: Qt.alpha(root.fg, 0.58)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Row {
                spacing: Style.spacing.md
                Ui.Button {
                  text: "Back"
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Back to continuity overview"
                  onClicked: root.openContinuity("overview")
                }
                Ui.Button {
                  text: continuityProc.working ? "Requesting…" : "Set up backup"
                  enabled: !continuityProc.working
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Set up SIA backup"
                  Accessible.description:
                    "Create the repository and write separate recovery and identity key files"
                  onClicked: root.requestSetup()
                }
              }
            }

            // ----------------------------------------------------- connect
            Column {
              visible: root.continuityPage === "connect"
              width: continuitySheetCol.width
              spacing: Style.spacing.md

              Text {
                width: parent.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "Repository"
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Ui.TextField {
                id: connectRepositoryField
                width: parent.width
                maximumLength: root.continuityInputMaxLength
                text: root.repositoryInput
                placeholderText: "Existing repository path or endpoint"
                Accessible.name: "Existing backup repository"
                Accessible.description:
                  "Path or endpoint for the encrypted backup repository"
                onTextChanged: root.repositoryInput = text
              }
              Text {
                width: parent.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "Recovery key file"
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Ui.TextField {
                width: parent.width
                maximumLength: root.continuityInputMaxLength
                text: root.recoveryKeyPathInput
                placeholderText: "Path to the existing recovery key file"
                Accessible.name: "Recovery key file"
                Accessible.description:
                  "Recovery key file used to reconnect this computer"
                onTextChanged: root.recoveryKeyPathInput = text
              }
              Text {
                width: parent.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "Environment file · optional"
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Ui.TextField {
                width: parent.width
                maximumLength: root.continuityInputMaxLength
                text: root.environmentFileInput
                placeholderText: "Path to repository environment file"
                Accessible.name: "Backup environment file"
                Accessible.description:
                  "Optional path containing repository environment settings"
                onTextChanged: root.environmentFileInput = text
              }
              Text {
                width: parent.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "SIA reads the recovery key through its guarded CLI. The cockpit never asks for or displays the key itself."
                wrapMode: Text.WordWrap
                color: Qt.alpha(root.fg, 0.58)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Row {
                spacing: Style.spacing.md
                Ui.Button {
                  text: "Back"
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Back to continuity overview"
                  onClicked: root.openContinuity("overview")
                }
                Ui.Button {
                  text: continuityProc.working ? "Requesting…" : "Connect backup"
                  enabled: !continuityProc.working
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Connect SIA backup"
                  Accessible.description:
                    "Reconnect this computer to the encrypted repository"
                  onClicked: root.requestConnect()
                }
              }
            }

            // ----------------------------------------------------- restore
            Column {
              visible: root.continuityPage === "restore"
              width: continuitySheetCol.width
              spacing: Style.spacing.md

              Column {
                visible: root.continuityState !== "prepared"
                  && root.continuityState !== "restoring"
                width: parent.width
                spacing: Style.spacing.md
                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: "Verified snapshot"
                  color: root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                }
                Ui.TextField {
                  id: restoreSnapshotField
                  width: parent.width
                  maximumLength: root.continuityInputMaxLength
                  text: root.restoreSnapshotInput
                  placeholderText: "Snapshot ID"
                  Accessible.name: "Snapshot to prepare"
                  Accessible.description:
                    "Identifier of the verified SIA recovery snapshot"
                  onTextChanged: root.restoreSnapshotInput = text
                }
                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: root.continuityLatestText()
                  wrapMode: Text.WordWrap
                  color: Qt.alpha(root.fg, 0.62)
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
                Ui.Button {
                  text: continuityProc.working
                    ? "Requesting…" : "Prepare restore"
                  enabled: Model.continuityCanPrepare(
                    root.currentContinuity,
                    root.continuityReceiptAuthenticated)
                    && !continuityProc.working
                    && root.restoreSnapshotInput.trim() !== ""
                  foreground: enabled ? root.fg : Qt.alpha(root.fg, 0.35)
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Prepare SIA restore"
                  Accessible.description:
                    "Download, verify, and stage a snapshot without applying it"
                  onClicked: root.requestRestorePrepare()
                }
              }

              Column {
                visible: root.continuityState === "prepared"
                  && Model.continuityCanApply(
                    root.currentContinuity,
                    root.continuityReceiptAuthenticated)
                width: parent.width
                spacing: Style.spacing.md

                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: "RESTORE CEREMONY"
                  color: root.urgent
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.subtitle
                  font.bold: true
                }
                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: "Preparation is non-destructive. Applying it replaces live SIA memory state. Every value below is checked again by the backend under the exclusive lifecycle lease."
                  wrapMode: Text.WordWrap
                  color: Qt.alpha(root.fg, 0.68)
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }

                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: "Type RESTORE"
                  color: root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                }
                Ui.TextField {
                  id: restorePhraseField
                  width: parent.width
                  maximumLength: "RESTORE".length
                  text: root.restorePhraseInput
                  placeholderText: "RESTORE"
                  Accessible.name: "Restore confirmation phrase"
                  Accessible.description: "Type RESTORE exactly"
                  onTextChanged: root.restorePhraseInput = text
                }

                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: "Prepared snapshot · type exactly"
                  color: root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                }
                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: {
                    var prepared = root.preparedRestore()
                    return prepared ? prepared.snapshot_id : ""
                  }
                  wrapMode: Text.WrapAnywhere
                  color: root.accent
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.bodySmall
                }
                Ui.TextField {
                  width: parent.width
                  maximumLength: root.continuityInputMaxLength
                  text: root.restorePreparedSnapshotInput
                  placeholderText: "Exact prepared snapshot ID"
                  Accessible.name: "Prepared snapshot confirmation"
                  Accessible.description:
                    "Type the exact prepared snapshot identifier shown above"
                  onTextChanged: root.restorePreparedSnapshotInput = text
                }

                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: "Current ledger head · type exactly"
                  color: root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                }
                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: {
                    var prepared = root.preparedRestore()
                    return prepared ? prepared.ledger_head : ""
                  }
                  wrapMode: Text.WrapAnywhere
                  color: root.accent
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.bodySmall
                }
                Ui.TextField {
                  width: parent.width
                  maximumLength: root.continuityInputMaxLength
                  text: root.restoreLedgerHeadInput
                  placeholderText: "Exact current ledger head"
                  Accessible.name: "Current ledger head confirmation"
                  Accessible.description:
                    "Type the exact current ledger head shown above"
                  onTextChanged: root.restoreLedgerHeadInput = text
                }

                Ui.Toggle {
                  width: parent.width
                  checked: root.restoreReceiptReadoptAck
                  label: "Re-adopt corpus receipt"
                  description: "I understand this machine will deliberately re-adopt the prepared snapshot's corpus receipt as its recovery lineage."
                  foreground: root.fg
                  accent: root.accent
                  Accessible.role: Accessible.CheckBox
                  Accessible.name: label
                  Accessible.description: description
                  Accessible.checked: checked
                  onClicked: root.restoreReceiptReadoptAck
                    = !root.restoreReceiptReadoptAck
                }

                Column {
                  visible: {
                    var prepared = root.preparedRestore()
                    return !!prepared && !prepared.identity_matches
                  }
                  width: parent.width
                  spacing: Style.spacing.sm
                  Text {
                    width: parent.width
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    text: "Offline identity key file"
                    color: root.urgent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    font.bold: true
                  }
                  Ui.TextField {
                    width: parent.width
                    maximumLength: root.continuityInputMaxLength
                    text: root.restoreIdentityKeyPathInput
                    placeholderText: "Path to offline identity-key file"
                    Accessible.name: "Offline identity key file"
                    Accessible.description:
                      "Path used locally to authorize identity recovery"
                    onTextChanged: root.restoreIdentityKeyPathInput = text
                  }
                  Text {
                    width: parent.width
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    text: "This prepared identity does not match this machine. Only the file path is handed to the guarded CLI; key bytes are never displayed, uploaded, or placed in argv."
                    wrapMode: Text.WordWrap
                    color: Qt.alpha(root.urgent, 0.82)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                }

                Ui.Button {
                  id: restoreApplyButton
                  enabled: root.restoreCeremonyReady()
                    && !continuityProc.working
                  text: "Review live restore…"
                  foreground: enabled ? root.urgent
                    : Qt.alpha(root.fg, 0.35)
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Review prepared SIA restore"
                  Accessible.description:
                    "Open the final destructive confirmation after every ceremony field matches"
                  onClicked: root.requestRestoreConfirmation()
                }
              }

              Text {
                visible: root.continuityState === "restoring"
                width: parent.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: "Restore is running outside the cockpit. Success is withheld until SIA reports ready and its signed ledger passes verification."
                wrapMode: Text.WordWrap
                color: root.accent
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }

              Ui.Button {
                text: "Back"
                bordered: true
                focusable: true
                Accessible.role: Accessible.Button
                Accessible.name: "Back to continuity overview"
                onClicked: root.openContinuity("overview")
              }
            }

            Text {
              visible: root.continuityActionMsg !== ""
              width: continuitySheetCol.width
              textFormat: Text.PlainText
              renderType: Text.NativeRendering
              text: root.continuityActionMsg
              wrapMode: Text.WordWrap
              color: continuityProc.working || root.restoreVerificationPending
                ? Qt.alpha(root.fg, 0.65)
                : root.continuityStale || root.continuityBoundary !== ""
                  ? root.urgent
                  : root.continuityActionOk ? root.accent : root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
          }
        }
      }

        Ui.ConfirmDialog {
          id: continuityRestoreConfirm
          anchors.fill: parent
          opened: root.restoreConfirmOpen
          z: 30
          selectedIndex: 0
          message: "Begin the live restore and re-adopt its corpus receipt on this machine? This replaces live memory state. Cancel applies nothing and resets the ceremony. Success remains withheld until SIA is ready and its signed ledger verifies."
          cancelText: "Cancel"
          confirmText: "Restore SIA"
          background: Color.background
          foreground: root.fg
          scrim: Qt.alpha(Color.background, 0.7)
          selectedBackground: Qt.alpha(root.fg, 0.08)
          selectedText: root.accent
          fontFamily: root.fontFamily
          cornerRadius: Style.cornerRadius
          onCanceled: root.cancelRestoreConfirmation()
          onConfirmed: root.confirmRestore()
        }
      }

  function configuredPluginArraySettings(config) {
    const pluginId = Util.canonicalWidgetId(root.pluginId)
    const plugins = config ? config.plugins : null
    if (Array.isArray(plugins)) {
      for (var p = 0; p < plugins.length; p++) {
        const entry = plugins[p]
        if (entry && Util.canonicalWidgetId(String(entry.id || ""))
            === pluginId)
          return root.copyPluginSettings(entry)
      }
    }
    return ({})
  }

  function copyPluginSettings(entry) {
    var settings = ({})
    if (!root.isPlainRecord(entry)) return settings
    for (var key in entry)
      if (key !== "id") settings[key] = entry[key]
    return settings
  }

  function configuredStaleAfterSec() {
    var fallback = Model.staleAfterDefaultSec()
    if (root.manifest && root.manifest.barWidget
        && root.manifest.barWidget.defaults)
      fallback = Model.validStaleAfterSec(
        root.manifest.barWidget.defaults.staleAfterSec, fallback)
    return Model.validStaleAfterSec(
      root.configuredPluginSettings().staleAfterSec, fallback)
  }

  function normalizeWorkspaceName(value) {
    if (typeof value !== "string" && typeof value !== "number") return ""
    return String(value).trim()
  }

  function workspaceName(workspace) {
    if (!workspace) return ""
    var name = root.normalizeWorkspaceName(workspace.name)
    return name !== "" ? name : root.normalizeWorkspaceName(workspace.id)
  }

  function configuredWorkspaceLockName() {
    return root.normalizeWorkspaceName(
      root.configuredPluginSettings().cockpitWorkspace)
  }

  function loadWorkspaceLock() {
    if (root.workspaceLockLoaded) return
    root.workspaceLockName = root.configuredWorkspaceLockName()
    root.workspaceLockLoaded = true
  }

  function persistWorkspaceLock() {
    if (!root.shell || typeof root.shell.updateEntryInline !== "function") {
      root.workspaceLockFeedback = "This shell cannot save the workspace lock; it will last only until the cockpit closes."
      return
    }
    var settings = root.configuredPluginSettings()
    settings.id = root.pluginId
    settings.cockpitWorkspace = root.workspaceLockName
    root.shell.updateEntryInline(root.pluginId, settings)
    root.workspaceLockFeedback = ""
  }

  function setWorkspaceLock(name) {
    var next = root.normalizeWorkspaceName(name)
    if (root.workspaceLockLoaded && root.workspaceLockName === next) return
    root.workspaceLockName = next
    root.workspaceLockLoaded = true
    root.persistWorkspaceLock()
  }

  function clearWorkspaceLock() {
    if (root.workspaceLockActive) root.setWorkspaceLock("")
  }

  function toggleWorkspaceLock() {
    root.loadWorkspaceLock()
    if (root.workspaceLockActive) {
      root.clearWorkspaceLock()
      return
    }
    if (root.focusedWorkspaceName === "") {
      root.workspaceLockFeedback = "Workspace lock unavailable: Hyprland did not report a focused workspace."
      return
    }
    root.setWorkspaceLock(root.focusedWorkspaceName)
  }

  function launchSetup() {
    // This is the sole UI launch edge.  It is reached only from an explicit
    // click/key action; loading or enabling the plugin never executes setup.
    if (!root.setupActionAllowed || root.setupLaunchRequested) return
    root.setupLaunchRequested = true
    root.setupTerminalPresented = false
    root.setupTerminalMissing = false
    // A click is a request, not an outcome.  Draw the id this click will be
    // answered by, stamp it, then read presentation back from the runtime
    // marker the helper publishes under that id, under a deadline.
    root.setupAttemptId = Model.drawAttemptId()
    root.setupRequestedAtSec = Math.floor(Date.now() / 1000)
    setupPresenceApply.restart()
    setupPresenceDeadline.restart()
    Quickshell.execDetached([
      "/usr/bin/env", "-u", "BASH_ENV", "-u", "ENV",
      root.setupHelperPath, "launch", root.setupAttemptId])
  }

  function setupPresenceMessage() {
    // A late start supersedes the deadline's honest "never observed": the
    // deadline reports what had been seen by then, not a final verdict.
    if (root.setupTerminalPresented)
      return "Setup terminal started. This cockpit steps aside in a moment so that window is in front; SIA holds it open at the end, on success and on a named refusal. Reopen SIA any time for progress. This gate clears only after the matching resident release reaches first light."
    if (root.setupTerminalMissing)
      return "Setup terminal requested, but SIA never observed the installer shell start. If it starts later it is the real installer and holds itself open. Otherwise open a terminal yourself and run install.sh from the plugin checkout, or repair the terminal handler on this desktop, then try again."
    return "Setup terminal requested. Waiting for the installer shell to start…"
  }

  function setupEyebrow() {
    if (root.releaseLifecycle === "checking")
      return "INSTALLATION CHECK · READING LOCAL STATE"
    if (root.releaseLifecycle === "setup")
      return "FIRST LIGHT · LOCAL MEMORY NOT YET INSTALLED"
    if (root.releaseLifecycle === "installing")
      return root.installerProgressUnobserved
        ? "FIRST LIGHT · NO INSTALLER PROGRESS OBSERVED"
        : "FIRST LIGHT · INSTALLATION IN PROGRESS"
    if (root.releaseLifecycle === "update")
      return "RELEASE ALIGNMENT · RUNTIME UPDATE REQUIRED"
    if (root.releaseLifecycle === "ahead")
      return "RELEASE ALIGNMENT · COCKPIT CHECKOUT IS OLDER"
    return "INSTALLATION BOUNDARY · REPAIR REQUIRED"
  }

  function setupTitle() {
    if (root.releaseLifecycle === "checking") return "  Checking SIA"
    if (root.releaseLifecycle === "setup")
      return "  Give this machine a memory"
    if (root.releaseLifecycle === "installing")
      return root.installerProgressUnobserved
        ? "  First light has gone quiet"
        : "  First light is underway"
    if (root.releaseLifecycle === "update") return "  Finish the SIA update"
    if (root.releaseLifecycle === "ahead") return "  Update this cockpit"
    return "  Repair the release boundary"
  }

  function setupDescription() {
    if (root.releaseLifecycle === "checking")
      return "SIA is reading the resident status and the separate first-light completion record. No installer has been started."
    if (root.releaseLifecycle === "setup")
      return "The Marketplace installed SIA's cockpit. The resident memory service is not complete; first light remains a deliberate local action."
    if (root.releaseLifecycle === "installing")
      return root.installerProgressUnobserved
        ? "A matching installer recorded work in progress, and SIA has watched that record sit unchanged for longer than a first light takes. That is not evidence the installer failed, and SIA is not claiming it did: this cockpit cannot see whether that terminal is still running, and the install lock it holds is per-boot and unreadable from here. Check for the installer terminal. If it is gone, retry here; the installer verifies ownership and refuses unsafe replacement. Nothing is installed and nothing is ready until the matching runtime publishes status."
        : "A matching installer recorded work in progress. Keep its terminal open, or retry here only if that terminal has ended."
    if (root.releaseLifecycle === "update") {
      var installed = root.currentStatus
        && typeof root.currentStatus.version === "string"
        ? root.currentStatus.version : "a legacy runtime"
      return "The cockpit is " + root.pluginVersion
        + ", while the resident status is " + installed
        + ". The installer verifies ownership and retains the corpus and signing identity while advancing the runtime."
    }
    if (root.releaseLifecycle === "ahead") {
      var resident = Model.aheadVersion(
        root.runtimeEvidence, root.pluginVersion)
      return (resident !== ""
        ? "Resident SIA " + resident + " is newer than cockpit "
          + root.pluginVersion + "."
        : "A newer resident SIA runtime was observed.")
        + " Installation is disabled to prevent a downgrade. Run `omarchy plugin update khephri.sia`, then reopen the cockpit."
    }
    return "SIA could not establish a matching resident status and first-light completion record. The repair action re-enters the fail-closed installer, which verifies ownership and refuses unsafe replacement."
  }

  function setupActionLabel() {
    if (root.releaseLifecycle === "setup") return "BEGIN FIRST LIGHT"
    if (root.releaseLifecycle === "installing")
      return root.installerProgressUnobserved
        ? "RETRY FIRST LIGHT IN TERMINAL"
        : "REOPEN OR RETRY IN TERMINAL"
    if (root.releaseLifecycle === "update") return "FINISH UPDATE"
    return "RUN SAFE REPAIR"
  }

  function stateColor() {
    if (root.setupRequired) return root.accent
    if (root.stale) return Qt.alpha(root.fg, 0.4)
    if (root.brainState === "failed") return root.urgent
    if (root.brainState === "degraded") return Qt.alpha(root.urgent, 0.75)
    if (root.brainState === "thinking") return root.accent
    return root.fg
  }

  function nodeById(id) {
    if (!root.currentGraph || id === "") return null
    for (var i = 0; i < root.currentGraph.nodes.length; i++)
      if (root.currentGraph.nodes[i].id === id)
        return root.currentGraph.nodes[i]
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

  function toggleGraphReplay() {
    if (!root.currentGraph) return
    if (root.playing) {
      root.playing = false
      root.revealT = 1.0
    } else {
      Model.replayLayout(
        root.currentGraph, graphCanvas.width, graphCanvas.height)
      root.revealT = 0.0
      root.playing = true
    }
    graphCanvas.requestPaint()
  }

  function open(payloadJson) {
    var payload = ({})
    try {
      payload = typeof payloadJson === "string"
        ? JSON.parse(payloadJson || "{}") : (payloadJson || ({}))
    } catch (e) { payload = ({}) }
    root.loadWorkspaceLock()
    // A layer-shell surface is not a Hyprland toplevel, so the lock gates
    // visibility against the live focused workspace rather than claiming a
    // compositor workspace assignment. A direct summon elsewhere releases it.
    if (root.workspaceLockMismatch) root.clearWorkspaceLock()
    opened = true
    workspaceLockFeedback = ""
    root.clearVerification()
    continuityActionMsg = ""
    continuityActionOk = false
    continuitySheetOpen = false
    continuityPage = "overview"
    restoreConfirmOpen = false
    setupLaunchRequested = false
    setupTerminalPresented = false
    setupTerminalMissing = false
    // Model.setupTerminalPresented refuses an empty id and a zero stamp, so
    // clearing both keeps a marker from an earlier cockpit session from
    // being read as the presentation belonging to this one.
    // (Deliberately apostrophe-free: the release contract test extracts this
    // body by scanning braces with a quote state machine that does not skip
    // comments, so a lone apostrophe here silently swallows the closing brace
    // and the test fails somewhere else entirely.)
    setupAttemptId = ""
    setupRequestedAtSec = 0
    setupPresenceApply.stop()
    setupPresenceDeadline.stop()
    setupYield.stop()
    readyProc.cancel()
    clearReadyCheck()
    // The 1s clock only runs while the cockpit is open, so on summon nowMs
    // still holds whatever it read when the cockpit was last closed. Every
    // age on this screen, the installing horizon included, is measured
    // against it; re-read it before any of them are painted.
    nowMs = Date.now()
    // Watched publications and canvas resize handlers maintain the layout
    // while closed. The presentation timer requests a fresh read on arrival.
    presentationHold.restart()
    Qt.callLater(function() {
      if (payload.mode === "continuity") root.openContinuity("overview")
      else if (root.cockpitVisible && root.setupActionAllowed)
        firstLightButton.forceActiveFocus()
      else if (root.cockpitVisible) keyCatcher.forceActiveFocus()
      graphCanvas.requestPaint()
    })
  }

  // The installer calls this through Omarchy shell IPC after activation.  A
  // copied plugin tree is not the live generation until the resident shell
  // answers with the exact release it has actually loaded.
  function loadedReleaseVersion(ignored) {
    return Model.releaseVersion()
  }

  function close() {
    opened = false
    root.clearVerification()
    playing = false
    revealT = 1.0
    hoverId = ""
    readyProc.cancel()
    clearReadyCheck()
    root.continuitySheetOpen = false
    root.continuityPage = "overview"
    root.restoreConfirmOpen = false
    root.clearContinuityInputs()
    root.clearWorkspaceLock()
    workspaceLockFeedback = ""
  }

  function dismiss() {
    root.close()
    if (shell && typeof shell.hide === "function") shell.hide(root.pluginId)
  }

  onCockpitVisibleChanged: {
    if (!root.cockpitVisible) {
      presentationHold.stop()
      return
    }
    presentationHold.restart()
    Qt.callLater(function() {
      if (!root.cockpitVisible) return
      if (root.setupActionAllowed) firstLightButton.forceActiveFocus()
      else if (root.continuitySheetOpen) root.focusContinuityPage()
      else keyCatcher.forceActiveFocus()
      graphCanvas.requestPaint()
    })
  }

  onCurrentGraphChanged: {
    root.layoutLive = true
    if (root.currentGraph && graphCanvas.width > 0 && graphCanvas.height > 0)
      Model.syncGraph(
        root.currentGraph, graphCanvas.width, graphCanvas.height)
    if (!root.currentGraph) {
      // Withdrawn: hover is re-derived from the pointer, but a locked
      // selection and a running replay survive the beat between one named
      // generation and the next.
      root.hoverId = ""
      graphGapTimer.restart()
    } else {
      graphGapTimer.stop()
      root.graphGapSettled = false
      if (root.selectedId !== "" && !root.graphHasNode(root.selectedId))
        root.selectedId = ""
    }
    graphCanvas.requestPaint()
  }

  onReleaseLifecycleChanged: {
    if (root.releaseLifecycle === "ready") root.lifecycleWasReady = true
    // Ahead of the visibility guard on purpose.  The horizon has to keep
    // running while the cockpit is closed, which is where an installer
    // usually dies.
    root.noteInstallingObservation()
    if (!root.cockpitVisible) return
    Qt.callLater(function() {
      if (!root.cockpitVisible) return
      if (root.setupActionAllowed) firstLightButton.forceActiveFocus()
      else keyCatcher.forceActiveFocus()
    })
  }

  function applyStatus(text) {
    root.clearVerification()
    readyProc.cancel()
    root.clearReadyCheck()
    try {
      const parsed = Model.strictStatusJsonParse(text)
      const valid = root.validStatusSnapshot(parsed)
      root.runtimeEvidence = Model.runtimeLifecycleEvidence(
        parsed, valid, root.runtimeEvidence, root.pluginVersion)
      if (!valid) {
        root.statusLoadValid = false
        root.statusBoundary = root.status
          ? "last good status; latest status rejected" : "no valid status"
        return
      }
      root.status = parsed
      root.statusLoadValid = true
      root.statusBoundary = ""
      // A status that names the resident graph admits that generation.
      if (root.graphBoundary === "" && root.graph
          && Model.snapshotGenerationsMatch(root.status, root.graph))
        root.admittedGraph = root.graph
      root.stale = Model.timestampStale(
        parsed.ts, Date.now(), root.staleAfterSec)
    } catch (e) {
      root.runtimeEvidence = Model.runtimeLifecycleEvidence(
        null, false, root.runtimeEvidence, root.pluginVersion)
      root.statusLoadValid = false
      root.statusBoundary = root.status
        ? "last good status; latest status rejected" : "no valid status"
    }
  }

  function applyGraph(text) {
    root.clearVerification()
    readyProc.cancel()
    root.clearReadyCheck()
    try {
      const g = Model.strictGraphJsonParse(text)
      if (!root.validGraphSnapshot(g, Date.now())) {
        root.graphBoundary = root.graph
          || root.graphBoundary.indexOf("last good graph;") === 0
          ? "last good graph; latest graph rejected" : "no valid graph snapshot"
        root.admittedGraph = null
        return
      }
      // Only a generation the current status names may touch the layout:
      // syncing an unnamed newer publication would rebuild the rings and
      // adjacency under the admitted graph still on screen.
      var named = Model.snapshotGenerationsMatch(root.currentStatus, g)
      if (named && graphCanvas.width > 0 && graphCanvas.height > 0)
        Model.syncGraph(g, graphCanvas.width, graphCanvas.height)
      root.graph = g
      root.graphBoundary = ""
      if (named) root.admittedGraph = g
      if (root.selectedId !== "" && !root.graphHasNode(root.selectedId))
        root.selectedId = ""
      if (root.hoverId !== "" && !root.graphHasNode(root.hoverId))
        root.hoverId = ""
      graphCanvas.requestPaint()
    } catch (e) {
      root.graphBoundary = root.graph
        || root.graphBoundary.indexOf("last good graph;") === 0
        ? "last good graph; latest graph rejected" : "no valid graph snapshot"
      root.admittedGraph = null
    }
  }

  // The generated-entry stream is the plane that carries model-origin prose, so it
  // is the one plane whose shape must never be assumed.  `kind` and `origin`
  // are painted into the row as the honesty labels themselves; a record
  // missing either rendered the literal word "undefined" beside prose, which
  // is worse than showing nothing — it looks like a label.
  //
  // `origin` stays optional on purpose.  sialib.load_thoughts deliberately
  // leaves genuinely unlabeled legacy rows unlabeled rather than laundering
  // them into a classification, and the delegate renders those as
  // legacy-unlabeled.  Requiring it here would reject the very rows that
  // boundary exists to expose.
  function validThoughtKind(value) {
    if (!root.validGraphString(value, 2000, true)) return false
    var canonical = value.toLowerCase().trim()
      .replace(/[^a-z0-9._-]+/g, "-")
      .replace(/-+/g, "-")
      .replace(/^[.-]+|[.-]+$/g, "")
    return value === (canonical === "" ? "unknown" : canonical)
  }

  function validThoughtRecoveryReceipt(receipt) {
    return Model.recordHasExactly(
        receipt, ["claim_id", "payload_sha256"])
      && /^[0-9a-f]{32}$/.test(receipt.claim_id)
      && /^[0-9a-f]{64}$/.test(receipt.payload_sha256)
  }

  function thoughtCodePointIsControl(code) {
    return Model.codePointIsControlOrFormat(code)
  }

  function thoughtTextIsCanonical(value) {
    if (!root.validGraphString(value, 2000, true)) return false
    // inert_summary removes control/format/surrogate code points, collapses
    // all whitespace to single ASCII spaces, and substitutes active Markdown
    // punctuation before the producer publishes the row.
    for (var index = 0; index < value.length; index++) {
      var code = value.codePointAt(index)
      if (root.thoughtCodePointIsControl(code)) return false
      if (code > 0xffff) index += 1
    }
    if (/[^\S ]/.test(value)
        || value.indexOf("  ") !== -1
        || value.trim() !== value
        || /[<>\[\]|*]/.test(value)
        || value.indexOf(String.fromCharCode(96)) !== -1) return false
    return true
  }

  function validThoughtSlugFor(thought) {
    if (!root.validGraphSlug(thought.slug)) return false
    return thought.queue_id === undefined
      || thought.slug === "thoughts/queue-" + thought.queue_id
  }

  function thoughtUrgencyState(thought) {
    if (!thought || typeof thought.urgent !== "boolean")
      return "unrecorded"
    return thought.urgent ? "urgent" : "ordinary"
  }

  function thoughtRowMetadata(thought, nowMs) {
    var origin = thought && typeof thought.origin === "string"
      ? thought.origin : "legacy-unlabeled"
    var parts = [thought.kind, "origin:" + origin]
    if (root.thoughtUrgencyState(thought) === "unrecorded")
      parts.push("urgency unrecorded")
    var age = thought && typeof thought.ts === "string"
      ? Model.timeAgo(thought.ts, nowMs) : ""
    parts.push(age !== "" ? age : "time unrecorded")
    return parts.join(" · ")
  }

  function thoughtStreamCountText() {
    return root.thoughtsLoadValid ? String(root.thoughts.length) : "—"
  }

  function validThought(thought, nowMs) {
    if (!root.isPlainRecord(thought)) return false
    // The loader preserves an unlabeled {kind,text} legacy row and adds only
    // origin:model to the closed set of known model-backed legacy kinds.
    // Projected legacy rows carry the base fields; later rows may add origin,
    // a durable queue binding, or both. These are the only admitted envelopes.
    var minimal = Model.recordHasExactly(thought, ["kind", "text"])
    var normalizedLegacyModel = Model.recordHasExactly(
      thought, ["kind", "text", "origin"])
      && thought.origin === "model"
      && Model.legacyModelThoughtKind(thought.kind)
    var baseFields = ["ts", "kind", "text", "links", "urgent", "slug"]
    var legacy = Model.recordHasExactly(thought, baseFields)
    var modernFields = baseFields.concat(["origin"])
    var modern = Model.recordHasExactly(thought, modernFields)
    var legacyQueued = Model.recordHasExactly(
      thought, baseFields.concat(["queue_id"]))
    var modernQueued = Model.recordHasExactly(
      thought, modernFields.concat(["queue_id"]))
    if (!minimal && !normalizedLegacyModel && !legacy && !modern
        && !legacyQueued && !modernQueued)
      return false
    if (!root.validThoughtKind(thought.kind)
        || !root.thoughtTextIsCanonical(thought.text)) return false
    if (minimal || normalizedLegacyModel) return true
    if (!Model.validUtcSecondTimestamp(thought.ts)) return false
    if (modern || modernQueued) {
      if (["evidence", "derived", "model"].indexOf(thought.origin) === -1)
        return false
    }
    if ((legacyQueued || modernQueued)
        && (typeof thought.queue_id !== "string"
            || !/^[0-9a-f]{32}$/.test(thought.queue_id))) return false
    if (!root.validThoughtSlugFor(thought)
        || typeof thought.urgent !== "boolean") return false
    if (!Array.isArray(thought.links) || thought.links.length === 0
        || thought.links.length > 200) return false
    for (var linkIndex = 0; linkIndex < thought.links.length; linkIndex++) {
      if (!root.validGraphSlug(thought.links[linkIndex])) return false
      if (linkIndex > 0
          && thought.links[linkIndex - 1] >= thought.links[linkIndex])
        return false
    }
    return true
  }

  function validThoughtStream(stream, nowMs) {
    if (!root.isPlainRecord(stream)) return false
    var topFields = ["v", "thoughts"]
    if (stream.thought_recovery !== undefined)
      topFields.push("thought_recovery")
    if (!Model.recordHasExactly(stream, topFields)
        || stream.v !== 1 || !Array.isArray(stream.thoughts)
        || stream.thoughts.length > 200
        || (stream.thought_recovery !== undefined
            && !root.validThoughtRecoveryReceipt(
              stream.thought_recovery))) return false
    var slugs = ({}), queueIds = ({})
    for (var i = 0; i < stream.thoughts.length; i++) {
      var thought = stream.thoughts[i]
      if (!root.validThought(thought, nowMs)) return false
      if (thought.slug !== undefined) {
        var slugKey = "$" + thought.slug
        if (slugs[slugKey] === true) return false
        slugs[slugKey] = true
      }
      if (thought.queue_id !== undefined) {
        var queueKey = "$" + thought.queue_id
        if (queueIds[queueKey] === true) return false
        queueIds[queueKey] = true
      }
    }
    return true
  }

  function thoughtsRejected() {
    root.thoughtsResolved = true
    root.thoughtsLoadValid = false
    root.thoughtsBoundary = root.thoughtsEverAdmitted
      || root.thoughtsBoundary.indexOf("last good generated-entry stream;") === 0
      ? "last good generated-entry stream; latest generated-entry stream rejected"
      : "no valid generated-entry stream"
  }

  function applyThoughts(text) {
    try {
      const t = Model.strictThoughtStreamJsonParse(text)
      if (!root.validThoughtStream(t, Date.now())) {
        root.thoughtsRejected()
        return
      }
      root.thoughts = t.thoughts.slice(-40).reverse()
      root.thoughtsResolved = true
      root.thoughtsLoadValid = true
      root.thoughtsEverAdmitted = true
      root.thoughtsBoundary = ""
    } catch (e) {
      // A silent catch here meant a truncated or mid-replace read quietly
      // froze the stream with no mark on screen at all.
      root.thoughtsRejected()
    }
  }

  function rejectContinuityStatus(lastGoodMessage, unavailableMessage) {
    root.continuityReceiptAuthenticated = false
    root.continuityBoundary = root.continuity
      ? lastGoodMessage : unavailableMessage
    var hadActionClaim = root.continuityActionOk
      || root.continuityActionMsg !== ""
      || root.restoreVerificationPending
    var hadRestoreCorrelation = root.restoreRequestId !== ""
      || root.restoreExpectedPreparedId !== ""
    root.continuityActionOk = false
    root.restoreVerificationPending = false
    if (hadRestoreCorrelation) root.restoreCorrelationLost = true
    if (hadActionClaim || hadRestoreCorrelation)
      root.continuityActionMsg = "Continuity status is unavailable; prior action results are not current."
  }

  function refreshContinuityActionFreshness() {
    var stale = Model.continuityStale(
      root.continuity, root.nowMs, Model.continuityStaleAfterSec())
    if (!stale || (!root.continuityActionOk
                   && !root.restoreVerificationPending)) return
    root.continuityActionOk = false
    root.restoreVerificationPending = false
    if (root.restoreRequestId !== ""
        || root.restoreExpectedPreparedId !== "")
      root.restoreCorrelationLost = true
    root.continuityActionMsg = "Continuity status is stale; prior action results are not current."
  }

  function applyContinuity(text, receiptAuthenticated) {
    try {
      const parsed = Model.strictContinuityJsonParse(text)
      if (!Model.validContinuityStatus(parsed, receiptAuthenticated)) {
        root.rejectContinuityStatus(
          "last good continuity status; latest update rejected",
          "no valid continuity status")
        return
      }
      var previousPrepared = root.preparedRestore()
      var previousPreparedId = previousPrepared
        ? previousPrepared.prepared_id : ""
      var nextPreparedId = parsed.prepared
        ? parsed.prepared.prepared_id : ""
      root.continuity = parsed
      root.continuityReceiptAuthenticated =
        receiptAuthenticated === true
      root.continuityBoundary = ""
      if (previousPreparedId !== nextPreparedId) {
        root.restoreConfirmOpen = false
        root.clearRestoreCeremony()
      }
      var currentPublicationStale = Model.continuityStale(
        parsed, Date.now(), Model.continuityStaleAfterSec())
      if (!root.restoreVerificationPending
          && root.restoreCorrelationLost
          && parsed.state === "prepared"
          && nextPreparedId !== ""
          && !currentPublicationStale) {
        root.restoreRequestId = ""
        root.restoreExpectedPreparedId = ""
        root.restoreCorrelationLost = false
      }
      if (root.restoreVerificationPending) {
        var operation = root.matchingRestoreOperation(parsed)
        if (currentPublicationStale) {
          root.restoreVerificationPending = false
          root.restoreCorrelationLost = true
          root.continuityActionOk = false
          root.continuityActionMsg = "Restore correlation is stale; no terminal verification is current."
        } else if (operation && (operation.phase === "accepted"
                          || operation.phase === "running")) {
          root.continuityActionOk = false
          root.continuityActionMsg = "Restore is running. Readiness and SIA signed-ledger verification are still pending."
        } else if (operation && operation.phase === "verified"
                   && operation.ready
                   && operation.sia_ledger_verified) {
          root.restoreVerificationPending = false
          root.restoreCorrelationLost = false
          root.restoreRequestId = ""
          root.restoreExpectedPreparedId = ""
          root.continuityActionOk = true
          root.continuityActionMsg = "Restore verified: SIA is ready and its signed ledger passes."
        } else if (operation && operation.phase === "verified") {
          root.restoreVerificationPending = false
          root.restoreCorrelationLost = false
          root.restoreRequestId = ""
          root.restoreExpectedPreparedId = ""
          root.continuityActionOk = false
          root.continuityActionMsg = "Restore terminal record did not prove both readiness and SIA signed-ledger verification."
        } else if (operation && (operation.phase === "failed"
                                 || operation.phase === "blocked")) {
          root.restoreVerificationPending = false
          root.restoreCorrelationLost = false
          root.restoreRequestId = ""
          root.restoreExpectedPreparedId = ""
          root.continuityActionOk = false
          root.continuityActionMsg = "The exact restore request did not reach verified readiness. Review continuity details before retrying."
        } else if (!operation) {
          root.restoreVerificationPending = false
          root.restoreCorrelationLost = true
          root.continuityActionOk = false
          root.continuityActionMsg = "Restore request correlation disappeared before terminal verification."
        }
      }
      if (root.continuitySheetOpen
          && (root.continuityPage === "setup"
              || root.continuityPage === "connect")
          && parsed.state !== "unconfigured") {
        root.continuityPage = "overview"
        root.focusContinuityPage()
      }
      if (root.opened) continuityScheduleRefresh.restart()
    } catch (e) {
      root.rejectContinuityStatus(
        "last good continuity status; latest update rejected",
        "no valid continuity status")
    }
  }

  function applyContinuitySchedule(text) {
    try {
      const parsed = Model.strictContinuityJsonParse(text)
      if (!Model.validContinuitySchedule(parsed))
        throw new Error("invalid continuity schedule")
      root.continuitySchedule = parsed
      root.continuityScheduleBoundary = ""
    } catch (e) {
      root.continuitySchedule = null
      root.continuityScheduleBoundary =
        "Automatic schedule status unavailable; no automatic run is being claimed."
    }
  }

  function applySetupPresence(text) {
    try {
      const parsed = Model.strictSetupMarkerJsonParse(text)
      if (!Model.setupTerminalPresented(parsed, root.setupRequestedAtSec,
                                        root.setupAttemptId,
                                        Math.floor(Date.now() / 1000)))
        return
      root.setupTerminalPresented = true
      root.setupTerminalMissing = false
      // The deadline may already have re-armed the button on the honest
      // report that nothing was seen in time.  A shell that starts later is
      // still this click's installer, so close the launch gate again rather
      // than let a second press open a window that can only refuse on the
      // install lock.
      root.setupLaunchRequested = true
      setupPresenceApply.stop()
      setupPresenceDeadline.stop()
      // This cockpit is a layer-shell overlay above every normal window and
      // holds the keyboard while visible, so the terminal it just asked for
      // opens behind it.  Step aside once that shell is known to be running;
      // the installing lifecycle reports progress when the cockpit reopens.
      setupYield.restart()
    } catch (e) { }
  }

  function installCompletionKey(completion) {
    if (!root.isPlainRecord(completion)) return ""
    return String(completion.v) + "/" + String(completion.state)
      + "/" + String(completion.version)
  }

  // Start the horizon when this exact installing record is first seen, and
  // restart it whenever the record changes.  A second install writing a new
  // record is a fresh installer and is owed the full bound again, even
  // though the lifecycle string never left "installing".
  function noteInstallingObservation(publicationChanged) {
    var key = root.releaseLifecycle === "installing"
      ? root.installCompletionKey(root.installCompletion) : ""
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

  function applyInstallCompletion(text, publicationChanged) {
    try {
      const parsed = Model.strictInstallCompletionJsonParse(text)
      root.installCompletion = parsed
    } catch (e) { root.installCompletion = null }
    root.noteInstallingObservation(publicationChanged)
  }

  FileView {
    id: statusFile
    property bool refreshPending: false
    path: root.statePath + "/status.json"
    watchChanges: true
    printErrors: false
    onLoaded: {
      if (root.settleWatchedFileRefresh(statusFile)) return
      root.applyStatus(text())
      root.statusResolved = true
    }
    onLoadFailed: {
      if (root.settleWatchedFileRefresh(statusFile)) return
      root.clearVerification()
      readyProc.cancel()
      root.clearReadyCheck()
      root.runtimeEvidence = Model.runtimeLifecycleEvidence(
        null, false, root.runtimeEvidence, root.pluginVersion)
      root.statusLoadValid = false
      root.statusResolved = true
      root.statusBoundary = root.status
        ? "last good status; resident status unavailable"
        : "resident status unavailable"
    }
    onFileChanged: {
      // The watched name now denotes an unvalidated generation.  Keep the
      // prior bytes only as diagnostic context until the settled reread.
      root.clearVerification()
      readyProc.cancel()
      root.clearReadyCheck()
      root.statusLoadValid = false
      root.statusResolved = false
      root.statusBoundary = root.status
        ? "last good status; newer resident status pending validation"
        : "resident status pending validation"
      statusFile.refreshPending = true
      statusApply.restart()
    }
  }
  // Every snapshot is published by one atomic rename, so the settle wait only
  // has to outlast the watcher's own burst of events for that rename.  At
  // 150-200 ms the beat between one named generation and the next was a
  // visible blink; the reread itself validates whatever it finds.
  Timer { id: statusApply; interval: 60; repeat: false
          onTriggered: statusFile.reload() }
  // "current graph unavailable" is said only once the graph has been absent
  // long enough to be a state, not the beat between two named generations.
  property bool graphGapSettled: false
  Timer { id: graphGapTimer; interval: 400; repeat: false
          onTriggered: root.graphGapSettled = true }

  FileView {
    id: graphFile
    property bool refreshPending: false
    path: root.statePath + "/graph.json"
    watchChanges: true
    printErrors: false
    onLoaded: {
      if (root.settleWatchedFileRefresh(graphFile)) return
      root.applyGraph(text())
    }
    onLoadFailed: {
      if (root.settleWatchedFileRefresh(graphFile)) return
      // statusFile has always resolved a failed load into a boundary; these
      // three planes did not, so a snapshot deleted or made unreadable after
      // a good load left its last-good pixels on screen with an EMPTY
      // boundary string — the display reading as freshly confirmed at the
      // exact moment its source stopped existing.
      root.clearVerification()
      readyProc.cancel()
      root.clearReadyCheck()
      var hadLastGood = !!root.graph
        || root.graphBoundary.indexOf("last good graph;") === 0
      root.graph = null
      root.admittedGraph = null
      root.selectedId = ""
      root.hoverId = ""
      graphCanvas.requestPaint()
      root.graphBoundary = hadLastGood
        ? "last good graph; resident graph snapshot unavailable"
        : "resident graph snapshot unavailable"
    }
    onFileChanged: {
      root.clearVerification()
      readyProc.cancel()
      root.clearReadyCheck()
      // One rename can arrive as a burst of change events; the first already
      // withdrew `graph`, but the admitted generation is still the last good
      // graph on screen.
      root.graphBoundary = root.graph || root.admittedGraph
        ? "last good graph; newer graph snapshot pending validation"
        : "resident graph snapshot pending validation"
      root.graph = null
      graphCanvas.requestPaint()
      graphFile.refreshPending = true
      graphApply.restart()
    }
  }
  Timer { id: graphApply; interval: 60; repeat: false
          onTriggered: graphFile.reload() }

  FileView {
    id: thoughtsFile
    property bool refreshPending: false
    path: root.statePath + "/thoughts.json"
    watchChanges: true
    printErrors: false
    onLoaded: {
      if (root.settleWatchedFileRefresh(thoughtsFile)) return
      root.applyThoughts(text())
    }
    onLoadFailed: {
      if (root.settleWatchedFileRefresh(thoughtsFile)) return
      var hadLastGood = root.thoughtsEverAdmitted
        || root.thoughtsBoundary.indexOf(
          "last good generated-entry stream;") === 0
      root.thoughtsResolved = true
      root.thoughtsLoadValid = false
      root.thoughts = []
      root.thoughtsBoundary = hadLastGood
        ? "last good generated-entry stream; resident generated-entry stream unavailable"
        : "resident generated-entry stream unavailable"
    }
    onFileChanged: {
      root.thoughtsResolved = false
      root.thoughtsLoadValid = false
      root.thoughtsBoundary = root.thoughtsEverAdmitted
        ? "last good generated-entry stream; newer stream pending validation"
        : "resident generated-entry stream pending validation"
      root.thoughts = []
      thoughtsFile.refreshPending = true
      thoughtsApply.restart()
    }
  }
  Timer { id: thoughtsApply; interval: 60; repeat: false
          onTriggered: thoughtsFile.reload() }

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
      root.rejectContinuityStatus(
        "last good continuity status; resident continuity status unavailable",
        "resident continuity status unavailable")
      continuityStatusProc.refresh()
    }
    onFileChanged: {
      root.continuityReceiptAuthenticated = false
      continuityStatusProc.invalidate()
      root.continuityBoundary = root.continuity
        ? "last good continuity status; newer update pending validation"
        : "continuity status pending validation"
      var hadActionContext = root.continuityActionOk
        || root.continuityActionMsg !== ""
        || root.restoreVerificationPending
        || root.restoreRequestId !== ""
        || root.restoreExpectedPreparedId !== ""
      root.continuityActionOk = false
      if (hadActionContext)
        root.continuityActionMsg = "Continuity status changed; waiting to validate the new publication."
      continuityFile.refreshPending = true
      continuityApply.restart()
    }
  }
  Timer { id: continuityApply; interval: 150; repeat: false
          onTriggered: continuityFile.reload() }

  // Receipt replacement or deletion is an authority change even when the
  // display envelope does not move.  Never parse this file in QML; its only
  // role here is to invalidate provenance and trigger backend revalidation.
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
      root.rejectContinuityStatus(
        "last good continuity status; verification receipt unavailable",
        "continuity verification receipt unavailable")
      continuityStatusProc.refresh()
    }
    onFileChanged: {
      root.rejectContinuityStatus(
        "last good continuity status; verification receipt changed",
        "continuity verification receipt changed")
      continuityStatusProc.invalidate()
      continuityReceiptFile.refreshPending = true
      continuityReceiptApply.restart()
    }
  }
  Timer { id: continuityReceiptApply; interval: 150; repeat: false
          onTriggered: continuityReceiptFile.reload() }

  Timer { id: continuityScheduleRefresh; interval: 150; repeat: false
          onTriggered: continuityScheduleProc.refresh() }
  Timer {
    // The exact receipt watcher above withdraws that claim immediately.
    // Rebind the remaining config, key, identity, and optional environment
    // authorities on this explicit bounded polling horizon.
    interval: root.continuityAuthorityPollInterval
    running: root.opened
    repeat: true
    onTriggered: {
      root.continuityReceiptAuthenticated = false
      root.continuityBoundary = root.continuity
        ? "last good continuity status; authority revalidation pending"
        : "continuity authority revalidation pending"
      if (root.continuityActionOk) {
        root.continuityActionOk = false
        root.continuityActionMsg =
          "Continuity authority is being revalidated; prior action results are not current."
      }
      continuityStatusProc.invalidate()
      continuityStatusProc.refresh()
      continuityScheduleProc.refresh()
    }
  }

  FileView {
    id: installCompletionFile
    property bool refreshPending: false
    path: root.installCompletionPath
    watchChanges: true
    printErrors: false
    onLoaded: {
      if (root.settleWatchedFileRefresh(installCompletionFile)) return
      var publicationChanged = root.installCompletionPublicationChanged
      root.installCompletionPublicationChanged = false
      root.applyInstallCompletion(text(), publicationChanged)
      root.installCompletionResolved = true
    }
    onLoadFailed: {
      if (root.settleWatchedFileRefresh(installCompletionFile)) return
      root.installCompletionPublicationChanged = false
      root.installCompletion = null
      root.installCompletionResolved = true
      root.noteInstallingObservation()
    }
    onFileChanged: {
      // First-light is an install lifecycle barrier, not a routine status
      // refresh.  Withdraw validated pixels until the changed record settles.
      root.installCompletionPublicationChanged = true
      root.installCompletionResolved = false
      installCompletionFile.refreshPending = true
      installCompletionApply.restart()
    }
  }
  Timer { id: installCompletionApply; interval: 150; repeat: false
          onTriggered: installCompletionFile.reload() }

  FileView {
    id: setupPresenceFile
    property bool refreshPending: false
    path: root.setupPresencePath
    watchChanges: true
    printErrors: false
    // Reading this owner-only marker is the whole new capability: it observes
    // that the installer shell started in a terminal.  It is not readiness,
    // it starts nothing, and an absent or unreadable marker is fail-closed.
    onLoaded: {
      if (root.settleWatchedFileRefresh(setupPresenceFile)) return
      root.applySetupPresence(text())
    }
    onLoadFailed: {
      if (root.settleWatchedFileRefresh(setupPresenceFile)) return
    }
    onFileChanged: {
      // A change is worth exactly one reload.  Only launchSetup() starts the
      // repeating poll, and only under the deadline that is guaranteed to
      // stop it, so an unrequested marker change can never leave a timer
      // running for the life of the shell.
      setupPresenceFile.refreshPending = true
      if (setupPresenceDeadline.running) setupPresenceApply.restart()
      else setupPresenceFile.reload()
    }
  }
  Timer { id: setupPresenceApply; interval: 500; repeat: true
          onTriggered: setupPresenceFile.reload() }
  Timer { id: setupYield; interval: 1500; repeat: false
          onTriggered: {
            if (root.setupTerminalPresented && root.cockpitVisible)
              root.dismiss()
          } }
  Timer { id: setupPresenceDeadline; interval: 25000; repeat: false
          onTriggered: {
            // The helper waits 20s for its own marker.  Past that the honest
            // report is that no installer shell was observed, not silence.
            setupPresenceApply.stop()
            if (root.setupTerminalPresented) return
            root.setupTerminalMissing = true
            root.setupLaunchRequested = false
          } }

  Timer {
    interval: 1000; running: root.opened; repeat: true
    onTriggered: {
      root.nowMs = Date.now()
      root.refreshContinuityActionFreshness()
      if (root.status) {
        root.stale = Model.timestampStale(
          root.status.ts, root.nowMs, root.staleAfterSec)
      }
    }
  }

  QtObject {
    id: verifyProc
    property var activeAttempt: null
    readonly property bool running:
      !!activeAttempt && activeAttempt.running
    readonly property string basis:
      activeAttempt ? activeAttempt.basis : ""
    readonly property bool launchPending:
      !!activeAttempt && activeAttempt.launchPending

    function retire(attempt) {
      if (!attempt) return
      if (activeAttempt === attempt) activeAttempt = null
      attempt.acceptResults = false
      attempt.launchPending = false
      if (attempt.running) attempt.running = false
      if (!attempt.destructionQueued) {
        attempt.destructionQueued = true
        Qt.callLater(function() { attempt.destroy() })
      }
    }

    function cancel() {
      var attempt = activeAttempt
      if (!attempt) return
      // Retire the identity before stopping the child.  `running = false`
      // may synchronously deliver callbacks on some Quickshell versions.
      activeAttempt = null
      attempt.acceptResults = false
      attempt.launchPending = false
      if (attempt.running) attempt.running = false
      if (!attempt.destructionQueued) {
        attempt.destructionQueued = true
        Qt.callLater(function() { attempt.destroy() })
      }
    }

    function start(basis) {
      if (activeAttempt) return false
      var attempt = verifyAttemptComponent.createObject(root, {
        "basis": basis
      })
      if (!attempt) {
        if (root.opened) {
          root.verifyOk = false
          root.verifyMsg = "CHAIN VERIFICATION INCOMPLETE — command did not start"
        }
        return false
      }
      activeAttempt = attempt
      attempt.running = true
      return true
    }

    function markLaunchFailure(attempt) {
      if (!root.processAttemptIsCurrent(activeAttempt, attempt)) return
      retire(attempt)
      if (root.opened) {
        root.verifyOk = false
        root.verifyMsg = "CHAIN VERIFICATION INCOMPLETE — command did not start"
      }
    }

    function receiptMatches(attempt) {
      if (attempt.outOverflow) return false
      var lines = attempt.outText.replace(/\r\n/g, "\n").split("\n")
      while (lines.length && lines[lines.length - 1] === "") lines.pop()
      return lines.length > 0
        && lines[lines.length - 1] === "SIA-VERIFIED-BASIS " + attempt.basis
    }

    function settle(attempt) {
      if (!attempt.exited || !attempt.outDone) return
      var accepted = root.opened
        && root.processAttemptIsCurrent(activeAttempt, attempt)
        && attempt.basis !== ""
        && verifyProc.basis === attempt.basis
        && attempt.basis === root.snapshotBasis()
      var verified = accepted && attempt.exitCode === 0
        && receiptMatches(attempt)
      retire(attempt)
      if (!accepted) return
      root.verifyOk = verified
      root.verifyMsg = verified
        ? "SIA signed ledger re-verified ✓"
        : "CHAIN VERIFICATION INCOMPLETE"
    }

    function finish(attempt, code) {
      attempt.exitCode = code
      attempt.exited = true
      settle(attempt)
    }
  }

  Component {
    id: verifyAttemptComponent
    Process {
      id: verifyAttempt
      property bool acceptResults: true
      property bool destructionQueued: false
      property string basis: ""
      property bool launchPending: true
      property bool startedForAttempt: false
      property string outText: ""
      property bool outDone: false
      property bool outOverflow: false
      property bool exited: false
      property int exitCode: 0
      command: [(Quickshell.env("HOME") || "") + "/.local/bin/sia",
                "verify", "--expect-basis", verifyAttempt.basis]
      stdout: StdioCollector {
        waitForEnd: true
        onStreamFinished: {
          var output = String(text || "")
          verifyAttempt.outOverflow = output.length
            > root.verificationResponseMaxLength
          verifyAttempt.outText = output.slice(
            0, root.verificationResponseMaxLength)
          output = ""
          verifyAttempt.outDone = true
          verifyProc.settle(verifyAttempt)
        }
      }
      onStarted: {
        verifyAttempt.startedForAttempt = true
        verifyAttempt.launchPending = false
      }
      onRunningChanged: {
        if (!running && verifyAttempt.launchPending
            && !verifyAttempt.startedForAttempt)
          verifyProc.markLaunchFailure(verifyAttempt)
      }
      onExited: function(code) {
        verifyProc.finish(verifyAttempt, code)
      }
    }
  }

  // The status JSON is a display envelope, not proof that a verification
  // receipt still exists.  Read it through the backend boundary that rebinds
  // every verified latest row to its current receipt before exposing it.
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
      root.rejectContinuityStatus(
        "last good continuity status; receipt authority unavailable",
        "continuity receipt authority unavailable")
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

  // Schedule health is observed live instead of inferred from RECOVERY READY.
  // The CLI authenticates the managed systemd units and returns only bounded,
  // closed JSON; no repository credential enters the cockpit.
  Process {
    id: continuityScheduleProc
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
    command: [(Quickshell.env("HOME") || "") + "/.local/bin/sia",
              "backup", "schedule"]

    function refresh() {
      if (checking || running) return
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
      root.continuitySchedule = null
      root.continuityScheduleBoundary = ""
      running = true
    }

    function fail(message) {
      checking = false
      launchPending = false
      root.continuitySchedule = null
      root.continuityScheduleBoundary = message
    }

    function settle() {
      if (!exited || !outDone || !errDone) return
      checking = false
      if (exitCode === 0 && !outOverflow && !errOverflow) {
        root.applyContinuitySchedule(
          outText.replace(/^\s+|\s+$/g, ""))
      } else {
        fail(outOverflow || errOverflow
          ? "Automatic schedule response exceeded its display boundary."
          : "Automatic schedule could not be verified; no automatic run is being claimed.")
      }
    }

    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var output = String(text || "")
        continuityScheduleProc.outOverflow = output.length
          > root.continuityResponseMaxLength
        continuityScheduleProc.outText = output.slice(
          0, root.continuityResponseMaxLength)
        output = ""
        continuityScheduleProc.outDone = true
        continuityScheduleProc.settle()
      }
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var output = String(text || "")
        continuityScheduleProc.errOverflow = output.length
          > root.continuityResponseMaxLength
        continuityScheduleProc.errText = output.slice(
          0, root.continuityResponseMaxLength)
        output = ""
        continuityScheduleProc.errDone = true
        continuityScheduleProc.settle()
      }
    }
    onStarted: {
      continuityScheduleProc.startedForAttempt = true
      continuityScheduleProc.launchPending = false
    }
    onRunningChanged: {
      if (!running && continuityScheduleProc.launchPending
          && !continuityScheduleProc.startedForAttempt)
        continuityScheduleProc.fail(
          "Automatic schedule command could not start; no automatic run is being claimed.")
    }
    onExited: function(code) {
      continuityScheduleProc.exitCode = code
      continuityScheduleProc.exited = true
      continuityScheduleProc.settle()
    }
  }

  // `sia ready` is the only live memory-readiness predicate. Status and graph
  // are intentionally last-published snapshots, so this process runs solely
  // on an explicit cockpit action and never infers readiness from a snapshot.
  QtObject {
    id: readyProc
    property var activeAttempt: null
    readonly property bool checking: !!activeAttempt
    readonly property bool running:
      !!activeAttempt && activeAttempt.running
    readonly property bool launchPending:
      !!activeAttempt && activeAttempt.launchPending

    function startCheck() {
      if (readyProc.launchPending || activeAttempt) return false
      root.clearReadyCheck()
      var attempt = readyAttemptComponent.createObject(root)
      if (!attempt) {
        readyProc.markLaunchFailure()
        return false
      }
      activeAttempt = attempt
      attempt.running = true
      return true
    }

    function cancel() {
      // Snapshot and overlay boundaries must not later acquire a result from
      // an earlier process/collector callback.
      var attempt = activeAttempt
      if (!attempt) return
      activeAttempt = null
      attempt.acceptResults = false
      attempt.launchPending = false
      if (attempt.running) attempt.running = false
      if (!attempt.destructionQueued) {
        attempt.destructionQueued = true
        Qt.callLater(function() { attempt.destroy() })
      }
    }

    function retire(attempt) {
      if (!attempt) return
      if (activeAttempt === attempt) activeAttempt = null
      attempt.acceptResults = false
      attempt.launchPending = false
      if (attempt.running) attempt.running = false
      if (!attempt.destructionQueued) {
        attempt.destructionQueued = true
        Qt.callLater(function() { attempt.destroy() })
      }
    }

    function markLaunchFailure(attempt) {
      if (!attempt) {
        root.readyChecked = true
        root.readyOk = false
        root.readyDetail = "could not start the local sia readiness command"
        return
      }
      if (!root.processAttemptIsCurrent(activeAttempt, attempt)) return
      retire(attempt)
      root.readyChecked = true
      root.readyOk = false
      root.readyDetail = "could not start the local sia readiness command"
    }

    function settle(attempt) {
      if (!root.processAttemptIsCurrent(activeAttempt, attempt)
          || !attempt.exited
          || !attempt.outDone || !attempt.errDone)
        return
      var detail = (attempt.outText + "\n" + attempt.errText)
        .replace(/^\s+|\s+$/g, "")
      var succeeded = attempt.exitCode === 0
      retire(attempt)
      root.readyChecked = true
      root.readyOk = succeeded
      root.readyDetail = detail || (root.readyOk
        ? "sia ready returned success" : "sia ready returned a refusal")
    }
  }

  Component {
    id: readyAttemptComponent
    Process {
      id: readyAttempt
      property bool acceptResults: true
      property bool destructionQueued: false
      property string outText: ""
      property string errText: ""
      property int exitCode: 0
      property bool exited: false
      property bool outDone: false
      property bool errDone: false
      // A failed exec does not produce an `exited` signal in Quickshell 0.3,
      // so retain the start boundary independently of normal completion.
      property bool launchPending: true
      property bool startedForAttempt: false
      command: [(Quickshell.env("HOME") || "") + "/.local/bin/sia", "ready"]
      stdout: StdioCollector {
        waitForEnd: true
        onStreamFinished: {
          readyAttempt.outText = String(text || "")
          readyAttempt.outDone = true
          readyProc.settle(readyAttempt)
        }
      }
      stderr: StdioCollector {
        waitForEnd: true
        onStreamFinished: {
          readyAttempt.errText = String(text || "")
          readyAttempt.errDone = true
          readyProc.settle(readyAttempt)
        }
      }
      // Quickshell's Process reports a failed exec as a transition back to
      // !running without an exited signal. Its public `started` signal lets us
      // distinguish that from a process which started and later completed.
      onStarted: {
        readyAttempt.startedForAttempt = true
        readyAttempt.launchPending = false
      }
      onRunningChanged: {
        if (!running && readyAttempt.launchPending
            && !readyAttempt.startedForAttempt)
          readyProc.markLaunchFailure(readyAttempt)
      }
      onExited: function(code) {
        readyAttempt.exitCode = code
        readyAttempt.exited = true
        readyProc.settle(readyAttempt)
      }
    }
  }

  // Every continuity command is a short hand-off to the independently
  // published worker.  The accepted backup or restore continues if this
  // cockpit closes; this Process reports only whether the request crossed the
  // local CLI boundary.
  Process {
    id: continuityProc
    property string operationLabel: ""
    property string outText: ""
    property string errText: ""
    property int exitCode: 0
    property bool exited: false
    property bool outDone: false
    property bool errDone: false
    property bool launchPending: false
    property bool startedForAttempt: false
    property bool launchFailed: false
    property bool working: false
    property string stdinPayload: ""
    property bool awaitRestoreVerification: false
    property string restorePreparedId: ""
    property bool outOverflow: false
    property bool errOverflow: false
    command: []
    stdinEnabled: true

    function launch(args, label, inputLine, waitForRestoreVerification,
                    preparedId) {
      if (working || running) {
        root.continuityRefusal(
          "Another continuity request is still being handed off.")
        return false
      }
      operationLabel = label
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
      launchFailed = false
      stdinPayload = typeof inputLine === "string" ? inputLine : ""
      awaitRestoreVerification = waitForRestoreVerification === true
      restorePreparedId = typeof preparedId === "string" ? preparedId : ""
      if (awaitRestoreVerification) {
        root.restoreVerificationPending = false
        root.restoreCorrelationLost = false
        root.restoreRequestId = ""
        root.restoreExpectedPreparedId = restorePreparedId
      }
      working = true
      root.continuityActionMsg = label + " requested…"
      root.continuityActionOk = false
      command = [(Quickshell.env("HOME") || "") + "/.local/bin/sia"]
        .concat(args)
      running = true
      return true
    }

    function markLaunchFailure() {
      if (launchFailed) return
      var wasRestore = awaitRestoreVerification
      launchPending = false
      launchFailed = true
      working = false
      stdinPayload = ""
      awaitRestoreVerification = false
      restorePreparedId = ""
      if (wasRestore) {
        root.restoreVerificationPending = false
        root.restoreRequestId = ""
        root.restoreExpectedPreparedId = ""
      }
      root.continuityActionOk = false
      root.continuityActionMsg = "Could not start the local SIA command."
    }

    function settle() {
      if (launchFailed || !exited || !outDone || !errDone) return
      working = false
      var detail = outOverflow || errOverflow
        ? "SIA command output exceeded the cockpit display boundary."
        : (outText + "\n" + errText).replace(/^\s+|\s+$/g, "")
      var accepted = exitCode === 0
      if (awaitRestoreVerification && accepted) {
        root.continuityActionOk = false
        var acceptance = null
        try {
          acceptance = outOverflow ? null
            : Model.strictContinuityAcceptanceJsonParse(
                outText.replace(/^\s+|\s+$/g, ""))
        }
        catch (e) { acceptance = null }
        if (root.validRestoreAcceptance(acceptance, restorePreparedId)) {
          root.restoreRequestId = acceptance.request_id
          root.restoreExpectedPreparedId = restorePreparedId
          root.restoreVerificationPending = true
          root.restoreCorrelationLost = false
          root.continuityActionMsg = "Restore accepted. Waiting for the exact request's readiness and SIA signed-ledger verification."
        } else {
          root.restoreRequestId = ""
          root.restoreExpectedPreparedId = restorePreparedId
          root.restoreVerificationPending = false
          root.restoreCorrelationLost = true
          root.continuityActionMsg = "Restore handoff lacked a valid correlation receipt. No success will be shown; inspect continuity status before any retry."
        }
      } else {
        if (awaitRestoreVerification) {
          root.restoreVerificationPending = false
          root.restoreCorrelationLost = false
          root.restoreRequestId = ""
          root.restoreExpectedPreparedId = ""
        }
        root.continuityActionOk = accepted
        root.continuityActionMsg = detail !== "" ? detail
          : operationLabel + (accepted ? " accepted." : " was refused.")
      }
      stdinPayload = ""
      awaitRestoreVerification = false
      restorePreparedId = ""
      outText = ""
      errText = ""
      continuityFile.reload()
    }

    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var output = String(text || "")
        continuityProc.outOverflow = output.length
          > root.continuityResponseMaxLength
        continuityProc.outText = output.slice(
          0, root.continuityResponseMaxLength)
        output = ""
        continuityProc.outDone = true
        continuityProc.settle()
      }
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var output = String(text || "")
        continuityProc.errOverflow = output.length
          > root.continuityResponseMaxLength
        continuityProc.errText = output.slice(
          0, root.continuityResponseMaxLength)
        output = ""
        continuityProc.errDone = true
        continuityProc.settle()
      }
    }
    onStarted: {
      continuityProc.startedForAttempt = true
      continuityProc.launchPending = false
      if (continuityProc.stdinPayload !== "") {
        // Quickshell Process exposes write but no close-stdin method.  The
        // restore CLI reads exactly one bounded newline-terminated record.
        var inputLine = continuityProc.stdinPayload
        continuityProc.stdinPayload = ""
        continuityProc.write(inputLine + "\n")
        inputLine = ""
      }
    }
    onRunningChanged: {
      if (!running && continuityProc.launchPending
          && !continuityProc.startedForAttempt)
        continuityProc.markLaunchFailure()
    }
    onExited: function(code) {
      continuityProc.exitCode = code
      continuityProc.exited = true
      continuityProc.settle()
    }
  }

  PanelWindow {
    id: win
    visible: root.cockpitVisible
    anchors { top: true; bottom: true; left: true; right: true }
    color: root.bg
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.namespace: "sia-cockpit"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: root.cockpitVisible
      ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    Item {
      id: keyCatcher
      anchors.fill: parent
      focus: true
      enabled: root.cockpitVisible
      Rectangle {
        anchors.fill: parent
        color: root.bg
        z: -1
      }

      // Sheets contain focusable controls, so Esc must remain available even
      // when a field rather than this catcher owns active focus.
      Shortcut {
        sequences: ["Esc"]
        enabled: root.cockpitVisible
        context: Qt.WindowShortcut
        onActivated: {
          if (root.restoreConfirmOpen) root.cancelRestoreConfirmation()
          else if (root.continuitySheetOpen) root.closeContinuity()
          else root.dismiss()
        }
      }

      Keys.priority: Keys.BeforeItem
      Keys.onPressed: function(event) {
        if (root.setupRequired) {
          if (root.setupActionAllowed && !root.setupLaunchRequested
              && !event.isAutoRepeat
              && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter
                  || event.key === Qt.Key_Space)) {
            root.launchSetup()
            event.accepted = true
          }
          return
        }
        if (root.restoreConfirmOpen) {
          if (continuityRestoreConfirm.handleKey(event)) event.accepted = true
          return
        }
        if (root.continuitySheetOpen) return
        if (event.key === Qt.Key_L) {
          root.toggleWorkspaceLock()
          event.accepted = true
        }
        else if (event.key === Qt.Key_R) {
          root.toggleGraphReplay()
          event.accepted = true
        }
      }

      // ---------------------------------------------------------- header
      Item {
        id: header
        enabled: !root.setupRequired
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: Style.space(16)
        height: Style.space(52) + brainBoundaryText.implicitHeight

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
            Text {
              id: brainBoundaryText
              anchors.left: parent.left
              anchors.top: parent.bottom
              width: header.width
              text: "“Brain” is a product metaphor for auditable local machine memory; it is not a biological brain and does not establish cognition or neuroscience."
              wrapMode: Text.WordWrap
              color: Qt.alpha(root.fg, 0.55)
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
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
              text: root.brainState === "thinking"
                ? "PROCESSING" : root.brainState.toUpperCase()
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
            text: root.currentStatus
              ? "pulse " + root.currentStatus.pulse_seq + " · "
                + Model.timeAgo(root.currentStatus.ts, root.nowMs)
              : "no current status"
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
            id: workspaceLockControl
            readonly property real maximumTextWidth: Style.space(180)
            activeFocusOnTab: true
            Accessible.role: Accessible.Button
            Accessible.name: workspaceLockText.text
            Accessible.description: root.workspaceLockActive
              ? "Release the cockpit workspace lock"
              : "Keep the cockpit visible only on the focused workspace"
            Accessible.onPressAction: root.toggleWorkspaceLock()
            Keys.onPressed: function(event) {
              if (!event.isAutoRepeat
                  && (event.key === Qt.Key_Return
                      || event.key === Qt.Key_Enter
                      || event.key === Qt.Key_Space)) {
                root.toggleWorkspaceLock()
                event.accepted = true
              }
            }
            anchors.verticalCenter: parent.verticalCenter
            width: workspaceLockText.width + Style.space(16)
            height: workspaceLockText.implicitHeight + Style.space(8)
            radius: Style.cornerRadius
            color: workspaceLockArea.containsMouse
              ? Qt.alpha(root.workspaceLockActive ? root.accent : root.fg, 0.18)
              : Qt.alpha(root.workspaceLockActive ? root.accent : root.fg, 0.08)
            border.color: workspaceLockControl.activeFocus ? root.accent
              : Qt.alpha(root.workspaceLockActive ? root.accent : root.fg, 0.25)
            border.width: workspaceLockControl.activeFocus ? 2 : 1
            Text {
              id: workspaceLockText
              anchors.centerIn: parent
              width: Math.min(implicitWidth, workspaceLockControl.maximumTextWidth)
              elide: Text.ElideRight
              textFormat: Text.PlainText
              renderType: Text.NativeRendering
              text: root.workspaceLockActive
                ? "UNLOCK " + root.workspaceLockName
                : root.focusedWorkspaceName !== ""
                  ? "LOCK TO " + root.focusedWorkspaceName
                  : "WS LOCK UNAVAILABLE"
              color: root.workspaceLockActive ? root.accent : root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: root.workspaceLockActive
            }
            MouseArea {
              id: workspaceLockArea
              anchors.fill: parent
              hoverEnabled: true
              onClicked: {
                workspaceLockControl.forceActiveFocus()
                root.toggleWorkspaceLock()
              }
            }
            // Use Omarchy's themed surface rather than Qt Quick Controls'
            // bright default tooltip. The lock lives in a deliberately dark,
            // instrument-like header and its hover help should belong to it.
            PanelToolTip {
              id: workspaceLockTooltip
              parent: workspaceLockArea
              visible: workspaceLockArea.containsMouse
              text: root.workspaceLockFeedback !== ""
                ? root.workspaceLockFeedback
                : root.workspaceLockActive
                  ? "The cockpit stays visible only on workspace "
                    + root.workspaceLockName
                    + ". Switch back here to see it, or click to unlock."
                  : root.focusedWorkspaceName !== ""
                    ? "Keep this full-screen cockpit on workspace "
                      + root.focusedWorkspaceName
                      + "; it hides elsewhere."
                    : "Workspace lock needs a focused Hyprland workspace."
              y: workspaceLockArea.height + Style.space(4)
              panelForeground: root.fg
              fontFamily: root.fontFamily
              fontSize: Style.font.caption
            }
          }
          Rectangle {
            id: closeControl
            activeFocusOnTab: true
            Accessible.role: Accessible.Button
            Accessible.name: "Close SIA cockpit"
            Accessible.onPressAction: root.dismiss()
            Keys.onPressed: function(event) {
              if (!event.isAutoRepeat
                  && (event.key === Qt.Key_Return
                      || event.key === Qt.Key_Enter
                      || event.key === Qt.Key_Space)) {
                root.dismiss()
                event.accepted = true
              }
            }
            anchors.verticalCenter: parent.verticalCenter
            width: closeText.implicitWidth + Style.space(16)
            height: closeText.implicitHeight + Style.space(8)
            radius: Style.cornerRadius
            color: closeArea.containsMouse
              ? Qt.alpha(root.fg, 0.18) : Qt.alpha(root.fg, 0.08)
            border.color: closeControl.activeFocus
              ? root.accent : Qt.alpha(root.fg, 0.25)
            border.width: closeControl.activeFocus ? 2 : 1
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
              onClicked: {
                closeControl.forceActiveFocus()
                root.dismiss()
              }
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
            color: root.graphBoundary !== "" && !root.currentGraph
              ? root.boundaryColor(root.graphBoundary)
              : (root.snap && root.snap.complete !== true)
                ? root.urgent : Qt.alpha(root.fg, 0.5)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            textFormat: Text.PlainText
            renderType: Text.NativeRendering
            text: root.ledgerTransitionText().toUpperCase()
            color: root.currentStatus && root.currentStatus.ledger_transition
              && root.currentStatus.ledger_transition.state === "pending"
              ? root.urgent
              : root.currentStatus && root.currentStatus.ledger_transition
                && root.currentStatus.ledger_transition.state === "signed"
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
            id: liveReadyControl
            activeFocusOnTab: true
            enabled: !readyProc.checking && !readyProc.running
            Accessible.role: Accessible.Button
            Accessible.name: readyText.text
            Accessible.description: root.readyDetail !== ""
              ? root.readyDetail
              : "Run the explicit live SIA memory-readiness check"
            Accessible.onPressAction: {
              if (liveReadyControl.enabled) readyProc.startCheck()
            }
            Keys.onPressed: function(event) {
              if (liveReadyControl.enabled && !event.isAutoRepeat
                  && (event.key === Qt.Key_Return
                      || event.key === Qt.Key_Enter
                      || event.key === Qt.Key_Space)) {
                readyProc.startCheck()
                event.accepted = true
              }
            }
            width: readyText.implicitWidth + Style.space(14)
            height: readyText.implicitHeight + Style.space(6)
            radius: height / 2
            color: liveReadyArea.containsMouse
              ? Qt.alpha(root.fg, 0.16) : Qt.alpha(root.fg, 0.07)
            border.color: liveReadyControl.activeFocus ? root.accent
              : root.readyChecked
                ? Qt.alpha(root.readyOk ? root.accent : root.urgent, 0.65)
                : Qt.alpha(root.fg, 0.22)
            border.width: liveReadyControl.activeFocus ? 2 : 1
            Text {
              id: readyText
              anchors.centerIn: parent
              textFormat: Text.PlainText
              renderType: Text.NativeRendering
              text: readyProc.checking ? "checking live readiness…"
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
              enabled: liveReadyControl.enabled
              onClicked: {
                liveReadyControl.forceActiveFocus()
                readyProc.startCheck()
              }
            }
            // `sia ready` diagnostics cross a process boundary, so keep the
            // tooltip on the same plain-text rendering contract as snapshots.
            // Keep every cockpit hover surface on the same dark Omarchy
            // palette; the detailed readiness diagnostic remains plain text.
            PanelToolTip {
              id: readyTooltip
              parent: liveReadyArea
              visible: liveReadyArea.containsMouse
                && root.readyDetail !== ""
              text: root.readyDetail
              x: Math.min(0, liveReadyArea.width - width)
              y: liveReadyArea.height + Style.space(4)
              panelForeground: root.fg
              fontFamily: root.fontFamily
              fontSize: Style.font.caption
              contentItem: Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: readyTooltip.text
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                leftPadding: Style.spacing.controlPaddingX
                rightPadding: Style.spacing.controlPaddingX
                topPadding: Style.spacing.controlPaddingY
                bottomPadding: Style.spacing.controlPaddingY
              }
            }
          }
        }
      }

      // ---------------------------------------------------------- footer
      Item {
        id: footer
        enabled: !root.setupRequired
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
          text: "hover = inspect · click = lock · L = workspace lock · R = replay · Esc = close · sia ask \"…\""
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
            var th = root.currentStatus && root.currentStatus.thought
              ? root.currentStatus.thought : null
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
        enabled: !root.setupRequired
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

        // ================================================= LEFT: status counts
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
          Controls.ScrollBar.vertical: Controls.ScrollBar {
            policy: Controls.ScrollBar.AsNeeded
          }

        Column {
          id: leftPane
          width: leftScroll.width
          spacing: body.gap

          // Continuity is a separate operational truth plane: it stays above
          // ordinary memory-service status and remains legible while restore quiesces
          // the brainstem.  The colored lifeline is the one deliberate visual
          // signature; every state is also named in text.
          Rectangle {
            id: continuityCard
            width: parent.width
            height: continuityCardCol.implicitHeight + Style.space(20)
            radius: Style.cornerRadius
            color: Qt.alpha(root.continuityColor, 0.05)
            border.color: Qt.alpha(root.continuityColor, 0.28)
            border.width: 1

            Rectangle {
              anchors.left: parent.left
              anchors.top: parent.top
              anchors.bottom: parent.bottom
              width: Style.normalBorderWidth
              color: root.continuityColor
            }

            Column {
              id: continuityCardCol
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.margins: Style.space(10)
              spacing: Style.space(5)

              Item {
                width: continuityCardCol.width
                height: Math.max(continuityTitle.implicitHeight,
                                 continuityStateButton.implicitHeight)
                Text {
                  id: continuityTitle
                  anchors.left: parent.left
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: "CONTINUITY"
                  color: Qt.alpha(root.fg, 0.48)
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                }
                Ui.Button {
                  id: continuityStateButton
                  anchors.right: parent.right
                  anchors.verticalCenter: parent.verticalCenter
                  text: root.continuityStateText()
                  foreground: root.continuityColor
                  fontSize: Style.font.caption
                  horizontalPadding: Style.spacing.sm
                  verticalPadding: Style.spacing.xxs
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Open continuity details, "
                    + root.continuityStateText().toLowerCase()
                  Accessible.description:
                    "Show backup setup, verification, and recovery controls"
                  onClicked: root.openContinuity("overview")
                }
              }

              Text {
                width: continuityCardCol.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: root.continuityScheduleStateText()
                wrapMode: Text.WordWrap
                color: root.continuityScheduleColor()
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Text {
                width: continuityCardCol.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: root.continuityHourlyText()
                wrapMode: Text.WordWrap
                color: Qt.alpha(root.fg, 0.68)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                width: continuityCardCol.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: root.continuityWeeklyText()
                visible: root.continuityExpanded
                wrapMode: Text.WordWrap
                color: Qt.alpha(root.fg, 0.56)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                width: continuityCardCol.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: root.continuitySleepText()
                visible: root.continuityExpanded
                wrapMode: Text.WordWrap
                color: Qt.alpha(root.fg, 0.48)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Text {
                width: continuityCardCol.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: root.continuityRepositoryText()
                visible: root.continuityExpanded
                elide: Text.ElideMiddle
                color: Qt.alpha(root.fg, 0.7)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                width: continuityCardCol.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: root.continuityLatestText()
                visible: root.continuityExpanded
                wrapMode: Text.WordWrap
                color: Qt.alpha(root.fg, 0.52)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                visible: root.continuityDetailText() !== ""
                  && root.continuityDetailText() !== root.continuityLatestText()
                width: continuityCardCol.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: root.continuityDetailText()
                wrapMode: Text.WordWrap
                color: root.continuityBoundary !== ""
                  || root.continuityState === "failed"
                  || root.continuityState === "blocked"
                    ? root.urgent : Qt.alpha(root.fg, 0.52)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Ui.Button {
                text: root.continuityExpanded ? "Less detail ▴" : "Schedule & recovery details ▾"
                fontSize: Style.font.caption
                focusable: true
                Accessible.name: text
                onClicked: root.continuityExpanded = !root.continuityExpanded
              }

              Row {
                spacing: Style.spacing.sm
                Ui.Button {
                  id: cardSetupButton
                  visible: !root.continuity
                    || root.continuityState === "unconfigured"
                  text: "Set up"
                  fontSize: Style.font.caption
                  horizontalPadding: Style.spacing.sm
                  verticalPadding: Style.spacing.xs
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Set up SIA backup"
                  Accessible.description:
                    "Create a new encrypted recovery repository"
                  onClicked: root.openContinuity("setup")
                }
                Ui.Button {
                  id: cardConnectButton
                  visible: !root.continuity
                    || root.continuityState === "unconfigured"
                  text: "Connect"
                  fontSize: Style.font.caption
                  horizontalPadding: Style.spacing.sm
                  verticalPadding: Style.spacing.xs
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Connect an existing SIA backup"
                  Accessible.description:
                    "Use a recovery key file to connect this computer"
                  onClicked: root.openContinuity("connect")
                }
                Ui.Button {
                  id: cardBackupButton
                  visible: !!root.currentContinuity
                    && root.continuityState !== "unconfigured"
                  enabled: Model.continuityCanBackUp(
                    root.currentContinuity,
                    root.continuityReceiptAuthenticated)
                    && !continuityProc.working
                  text: continuityProc.working ? "Requesting…" : "Extra copy"
                  foreground: enabled ? root.fg : Qt.alpha(root.fg, 0.35)
                  fontSize: Style.font.caption
                  horizontalPadding: Style.spacing.sm
                  verticalPadding: Style.spacing.xs
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Make an extra SIA backup now"
                  Accessible.description:
                    "Optional extra copy with immediate deep repository verification; hourly backups continue automatically"
                  onClicked: root.requestBackupNow()
                }
                Ui.Button {
                  id: cardRestoreButton
                  visible: !!root.currentContinuity
                    && root.continuityState !== "unconfigured"
                  enabled: (Model.continuityCanPrepare(
                              root.currentContinuity,
                              root.continuityReceiptAuthenticated)
                            || Model.continuityCanApply(
                              root.currentContinuity,
                              root.continuityReceiptAuthenticated))
                    && !continuityProc.working
                  text: "Restore…"
                  foreground: enabled ? root.fg : Qt.alpha(root.fg, 0.35)
                  fontSize: Style.font.caption
                  horizontalPadding: Style.spacing.sm
                  verticalPadding: Style.spacing.xs
                  bordered: true
                  focusable: true
                  Accessible.role: Accessible.Button
                  Accessible.name: "Restore SIA"
                  Accessible.description:
                    "Review a verified recovery copy before restoring"
                  onClicked: root.openContinuity("restore")
                }
              }

              Text {
                visible: root.continuityActionMsg !== ""
                width: continuityCardCol.width
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: root.continuityActionMsg
                wrapMode: Text.WordWrap
                color: continuityProc.working
                    || root.restoreVerificationPending
                  ? Qt.alpha(root.fg, 0.65)
                  : root.continuityStale || root.continuityBoundary !== ""
                    ? root.urgent
                    : root.continuityActionOk ? root.accent : root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
          }

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
                text: "STATUS COUNTS"
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
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: root.currentStatus && root.currentGraph ? String(root.currentStatus.pages) : "—"
                       color: root.fg; font.bold: true
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "links"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: root.currentStatus && root.currentGraph ? String(root.currentStatus.graph_edges) : "—"
                       color: root.fg; font.bold: true
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "events today"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: String(root.eventsToday)
                       color: root.accent; font.bold: true
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "entries kept"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: root.thoughtStreamCountText()
                       color: root.fg; font.bold: true
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "usage-tracked pages"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
                Text { textFormat: Text.PlainText; renderType: Text.NativeRendering; text: root.currentStatus && root.currentStatus.mind
                         ? root.currentStatus.mind.nodes + " · " + root.currentStatus.mind.edges + " co-return edges"
                         : "—"
                       color: root.fg; font.bold: true
                       font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall }
              }

              Text {
                visible: !!(root.currentStatus && root.currentStatus.mind)
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
                visible: !!(root.currentStatus && root.currentStatus.mind)
                width: vitalsCol.width
                columns: 2
                columnSpacing: Style.space(14)
                rowSpacing: Style.space(2)
                readonly property var mind:
                  root.currentStatus && root.currentStatus.mind
                    ? root.currentStatus.mind : ({})
                readonly property real labelWidth: Math.max(
                  stabilityLabel.implicitWidth, reviewLabel.implicitWidth,
                  pinsLabel.implicitWidth, familiarityLabel.implicitWidth)
                readonly property real valueWidth: Math.max(0,
                  memoryLens.width - memoryLens.labelWidth
                    - memoryLens.columnSpacing)
                Text { id: stabilityLabel; width: memoryLens.labelWidth
                       textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "stability"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.caption }
                Text { width: memoryLens.valueWidth; wrapMode: Text.WordWrap
                       textFormat: Text.PlainText; renderType: Text.NativeRendering; text: (memoryLens.mind.decay_active || 0) + " active · " + (memoryLens.mind.decay_demoted || 0) + " demoted"
                       color: root.fg; font.family: root.fontFamily; font.pixelSize: Style.font.caption }
                Text { id: reviewLabel; width: memoryLens.labelWidth
                       textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "SM-2 review"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.caption }
                Text { width: memoryLens.valueWidth; wrapMode: Text.WordWrap
                       textFormat: Text.PlainText; renderType: Text.NativeRendering; text: (memoryLens.mind.rehearsal_due || 0) + " due / " + (memoryLens.mind.rehearsal_eligible || 0) + " eligible"
                       color: (memoryLens.mind.rehearsal_due || 0) > 0 ? root.accent : root.fg
                       font.family: root.fontFamily; font.pixelSize: Style.font.caption }
                Text { id: pinsLabel; width: memoryLens.labelWidth
                       textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "operator pins"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.caption }
                Text { width: memoryLens.valueWidth; wrapMode: Text.WordWrap
                       textFormat: Text.PlainText; renderType: Text.NativeRendering; text: String(memoryLens.mind.pinned || 0)
                       color: root.fg; font.family: root.fontFamily; font.pixelSize: Style.font.caption }
                Text { id: familiarityLabel; width: memoryLens.labelWidth
                       textFormat: Text.PlainText; renderType: Text.NativeRendering; text: "familiarity"; color: Qt.alpha(root.fg, 0.55)
                       font.family: root.fontFamily; font.pixelSize: Style.font.caption }
                Text { id: familiarityValue; width: memoryLens.valueWidth; wrapMode: Text.WordWrap
                       textFormat: Text.PlainText; renderType: Text.NativeRendering; text: Model.familiarityStatusText(memoryLens.mind)
                       color: root.fg; font.family: root.fontFamily; font.pixelSize: Style.font.caption }
              }
              Text {
                visible: !!(root.currentStatus && root.currentStatus.mind)
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
                visible: !!(root.currentStatus && root.currentStatus.agent_queue)
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
                visible: !!(root.currentStatus && root.currentStatus.agent_queue)
                readonly property var relay:
                  root.currentStatus && root.currentStatus.agent_queue
                    ? root.currentStatus.agent_queue : ({})
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
                visible: !!(root.currentStatus && root.currentStatus.agent_queue)
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
                  var hist = root.currentStatus && root.currentStatus.history
                    ? root.currentStatus.history : []
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
                  var hist = root.currentStatus && root.currentStatus.history
                    ? root.currentStatus.history : []
                  if (!hist.length) return "no pulses yet"
                  var total = Model.historyEventTotal(hist, 90)
                  if (total === null) return "pulse history unavailable"
                  return "last " + Math.min(hist.length, 90) + " pulses · "
                    + total + " events"
                }
                color: Qt.alpha(root.fg, 0.4)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
          }

          // The source-authorized retained selection, never compatibility
          // policy slugs or an animation standing in for an observed pulse.
          Rectangle {
            visible: !root.playing
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
                width: wsCol.width
                text: liveLoopView.summary
                wrapMode: Text.WordWrap
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Repeater {
                model: liveLoopView.display ? liveLoopView.display.workspace.slots : []
                delegate: Item {
                  id: wsRow
                  required property var modelData
                  readonly property bool onMap:
                    root.graphHasNode(wsRow.modelData)
                  readonly property string selectionReason: {
                    var display = liveLoopView.display
                    if (!display) return "retained selection unavailable"
                    var selection = display.workspace.selection
                    var sources = display.workspace.selected_sources
                    var origin = sources.find(function(item) {
                      return item.subject === wsRow.modelData
                    })
                    var chosen = selection ? selection.activation.activations.find(function(item) {
                      return item.subject === wsRow.modelData
                    }) : null
                    var current = display.activation.activations.find(function(item) {
                      return item.subject === wsRow.modelData
                    })
                    function score(item) {
                      if (!item) return "unavailable"
                      return item.score === null ? item.reason + " (" + item.status + ")"
                        : String(item.score) + " (" + item.status + ")"
                    }
                    return "[origin:" + (origin ? origin.origin : "legacy-unlabeled")
                      + "] · selection " + score(chosen) + " · current " + score(current)
                  }
                  width: wsCol.width
                  height: wsText.implicitHeight + wsReason.implicitHeight + Style.space(5)
                  Text {
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    id: wsText
                    text: "◉ " + Model.slugLabel(wsRow.modelData)
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.rightMargin: wsMapState.visible
                      ? wsMapState.width + Style.space(6) : 0
                    elide: Text.ElideRight
                    color: !wsRow.onMap ? Qt.alpha(root.fg, 0.45)
                      : root.selectedId === wsRow.modelData
                      ? root.accent : Qt.alpha(root.fg, 0.75)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                  Text {
                    id: wsReason
                    anchors.top: wsText.bottom
                    width: parent.width
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                    text: wsRow.selectionReason
                    wrapMode: Text.WordWrap
                    color: Qt.alpha(root.fg, 0.45)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                  Text {
                    id: wsMapState
                    visible: !wsRow.onMap
                    anchors.right: parent.right
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
                text: liveLoopView.display
                  ? "Retained selection; expiry " + liveLoopView.display.workspace.expires_at
                    + ". Off-map is only a graph-display limit. Inspect full boundaries with sia live --json."
                  : "No matching source-authorized view. Inspect sia live --json for the refusal; compatibility slugs are not used here."
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
                text: "SOURCES"
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
                bottomPadding: Style.space(3)
              }
              Repeater {
                model: {
                  if (!root.currentStatus || !root.currentStatus.organs) return []
                  var ks = Object.keys(root.currentStatus.organs)
                  ks.sort(function(a, b) {
                    return (root.currentStatus.organs[b].today || 0)
                         - (root.currentStatus.organs[a].today || 0)
                  })
                  return ks
                }
                delegate: Item {
                  id: organRow
                  required property var modelData
                  readonly property var o:
                    (root.currentStatus && root.currentStatus.organs
                     && root.currentStatus.organs[organRow.modelData]) || {}
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
                model: root.currentStatus && root.currentStatus.integrity
                       && root.currentStatus.integrity.chains
                  ? Object.keys(root.currentStatus.integrity.chains).sort() : []
                delegate: Item {
                  id: chainRow
                  required property var modelData
                  readonly property string v:
                    ((root.currentStatus && root.currentStatus.integrity
                      && root.currentStatus.integrity.chains) || {})[
                        chainRow.modelData]
                    || "absent"
                  readonly property string observedAge: {
                    var age = Model.timeAgo(
                      root.currentStatus.integrity.checked_at, root.nowMs)
                    return age === "" ? "time unobserved" : age
                  }
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
                    text: chainRow.v === "pass"
                        ? "passed · observed " + chainRow.observedAge + " ✓"
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
                text: root.ledgerSummaryText(
                  root.currentStatus ? root.currentStatus.ledger : null)
                elide: Text.ElideRight
                color: Qt.alpha(root.fg, 0.55)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: root.dreamSummaryText(root.currentStatus
                  ? root.currentStatus.dream : null, root.nowMs) !== ""
                text: root.dreamSummaryText(root.currentStatus
                  ? root.currentStatus.dream : null, root.nowMs)
                color: Qt.alpha(root.fg, 0.55)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Rectangle {
                id: verifyControl
                activeFocusOnTab: true
                enabled: !verifyProc.running
                Accessible.role: Accessible.Button
                Accessible.name: verifyBtnText.text
                Accessible.description:
                  "Verify the signed SIA ledger against the displayed snapshot generation"
                Accessible.onPressAction: {
                  if (verifyControl.enabled) root.startVerification()
                }
                Keys.onPressed: function(event) {
                  if (verifyControl.enabled && !event.isAutoRepeat
                      && (event.key === Qt.Key_Return
                          || event.key === Qt.Key_Enter
                          || event.key === Qt.Key_Space)) {
                    root.startVerification()
                    event.accepted = true
                  }
                }
                width: verifyBtnText.implicitWidth + Style.space(16)
                height: verifyBtnText.implicitHeight + Style.space(6)
                radius: Style.cornerRadius
                color: verifyBtnArea.containsMouse
                  ? Qt.alpha(root.fg, 0.18) : Qt.alpha(root.fg, 0.08)
                border.color: verifyControl.activeFocus
                  ? root.accent : Qt.alpha(root.fg, 0.25)
                border.width: verifyControl.activeFocus ? 2 : 1
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
                  enabled: verifyControl.enabled
                  onClicked: {
                    verifyControl.forceActiveFocus()
                    root.startVerification()
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

          // Prediction calibration plus the separate heuristic retrieval-drift
          // instrument. The latter stays visible even before any takes exist.
          Rectangle {
            visible: root.beliefCardVisibleFor(root.currentStatus)
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
                text: "PREDICTIONS"
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                readonly property var tk:
                  root.currentStatus && root.currentStatus.takes
                    ? root.currentStatus.takes : ({})
                width: beliefCol.width
                text: root.takeSummaryText(tk)
                wrapMode: Text.WordWrap
                color: root.takeSummaryAvailable(tk) && tk.due > 0
                  ? root.accent
                                         : Qt.alpha(root.fg, 0.7)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: !!(root.currentStatus
                            && root.takeSummaryAvailable(
                              root.currentStatus.takes)
                            && root.currentStatus.takes.brier !== null
                            && root.currentStatus.takes.brier !== undefined)
                width: beliefCol.width
                wrapMode: Text.WordWrap
                text: "mean Brier "
                  + (root.currentStatus && root.currentStatus.takes
                     ? root.currentStatus.takes.brier : "")
                  + " · " + (root.currentStatus && root.currentStatus.takes
                     ? (root.currentStatus.takes.calibration_status || "descriptive")
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
                visible: !!(root.currentStatus && root.currentStatus.bench_trend
                            && root.currentStatus.bench_trend.length)
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
                visible: !!(root.currentStatus && root.currentStatus.bench_trend
                            && root.currentStatus.bench_trend.length)
                width: beliefCol.width
                height: Style.space(22)
                onPaint: {
                  var ctx = getContext("2d")
                  ctx.reset(); ctx.clearRect(0, 0, width, height)
                  var tr = root.currentStatus && root.currentStatus.bench_trend
                    ? root.currentStatus.bench_trend : []
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
                  function onCurrentStatusChanged() {
                    benchSpark.requestPaint()
                  }
                }
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: benchSpark.visible
                readonly property var bt:
                  root.currentStatus && root.currentStatus.bench_trend
                    ? root.currentStatus.bench_trend : []
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
                visible: !!(root.currentStatus
                            && root.currentStatus.bench_trend_boundary
                            && root.currentStatus.bench_trend_boundary.legacy_truncated)
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
            visible: !!(root.currentStatus && root.currentStatus.intents
                        && root.currentStatus.intents.length)
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
                text: "INTENTS — DATED COMMITMENTS"
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Repeater {
                model: root.currentStatus && root.currentStatus.intents
                  ? root.currentStatus.intents : []
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
                  if (!root.currentStatus)
                    return "last good graph snapshot · resident status unavailable"
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
                color: !root.currentStatus
                  ? root.urgent
                  : root.snap && (root.snap.complete !== true
                        || (root.snap.failed_ops
                            && root.snap.failed_ops.length))
                  ? root.urgent : Qt.alpha(root.fg, 0.6)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: !!(root.currentStatus
                            && root.currentStatus.ledger_transition)
                width: healthCol.width
                text: "publication ledger · " + root.ledgerTransitionText()
                wrapMode: Text.WordWrap
                color: root.currentStatus
                  && root.currentStatus.ledger_transition
                  && root.currentStatus.ledger_transition.state === "signed"
                  ? Qt.alpha(root.accent, 0.75)
                  : root.currentStatus
                    && root.currentStatus.ledger_transition
                    && root.currentStatus.ledger_transition.state === "pending"
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
                visible: !!root.currentStatus && !root.projectionDebtKnown()
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
                color: [root.graphBoundary, root.statusBoundary].every(
                  function(value) {
                    return value === "" || /pending validation$/.test(value)
                  }) ? Qt.alpha(root.fg, 0.55) : root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: !!(root.snap && root.snap.aged_out)
                width: healthCol.width
                text: (root.snap ? root.snap.aged_out : 0)
                  + " older pages beyond the display window (still in local memory)"
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
                model: root.statusErrorRows(
                  root.currentStatus ? root.currentStatus.errors : null)
                delegate: Text {
                  id: errRow
                  required property var modelData
                  width: healthCol.width
                  textFormat: Text.PlainText
                  renderType: Text.NativeRendering
                  text: errRow.modelData
                  wrapMode: Text.WordWrap
                  color: root.urgent
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: !!(root.currentStatus && root.currentStatus.sync_note)
                width: healthCol.width
                text: "✗ sync: " + (root.currentStatus
                  ? root.currentStatus.sync_note : "")
                wrapMode: Text.WordWrap
                color: root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: !!(root.currentStatus && root.currentStatus.redactions
                            && Object.keys(root.currentStatus.redactions).length)
                width: healthCol.width
                text: {
                  var redactions = root.currentStatus
                    && root.currentStatus.redactions
                    ? root.currentStatus.redactions : ({})
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
                visible: !root.stale && !!root.currentStatus
                  && root.isPlainRecord(root.currentStatus.errors)
                  && Object.keys(root.currentStatus.errors).length === 0
                  && !root.currentStatus.sync_note
                  && root.snap && root.snap.complete === true
                  && (!root.snap.failed_ops
                      || root.snap.failed_ops.length === 0)
                  && root.projectionDebtKnown()
                  && root.projectionDebtKeys().length === 0
                  && root.statusBoundary === "" && root.currentGraph
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
          color: Qt.tint(root.bg, Qt.alpha(root.fg, 0.03))
          border.color: Qt.alpha(root.fg, 0.10)
          border.width: 1
          clip: true

          Canvas {
            id: graphCanvas
            anchors.fill: parent
            anchors.margins: 2
            renderStrategy: Canvas.Immediate
            // Finish the image before presenting the surface. Cooperative
            // painting exposed an unpainted texture during remapping here.
            opacity: root.currentGraph ? 1 : 0
            // The glow layer follows every graph frame, so it never shows
            // a halo where a node no longer is.
            onPainted: glowCanvas.requestPaint()

            // Both dimensions, not just width: the first size a canvas
            // reports has its width and a zero height, and Model refuses to
            // seed a layout on a zero-size canvas.
            onWidthChanged: if (root.currentGraph && width > 0 && height > 0) {
              Model.syncGraph(root.currentGraph, width, height)
              root.layoutLive = true
            }
            onHeightChanged: if (root.currentGraph && width > 0 && height > 0) {
              Model.syncGraph(root.currentGraph, width, height)
              root.layoutLive = true
            }

            // The graph moves on the display's own frame clock and stops
            // when nothing moves. A 40 ms Timer used to drive both the
            // physics and the growth reveal: under the software-rendered
            // canvas it fired late, so the 12-second replay stretched
            // and every frame landed off the display's beat.
            FrameAnimation {
              id: graphFrames
              running: root.cockpitVisible && !presentationHold.running
                       && root.currentGraph !== null
                       && root.layoutLive
              onTriggered: {
                // A slow frame advances the layout by the time it took, up
                // to 250 ms (Model integrates it in sub-ticks). Treating a
                // slow frame as one 40 ms tick made wall-clock convergence
                // six times slower on the 220 ms frames of a software
                // renderer, so the loop ran through every pulse.
                var ms = frameTime * 1000
                if (!(ms > 0)) ms = 40
                else if (ms > 250) ms = 250
                if (root.playing) {
                  // Wall-clock reveal: twelve seconds regardless of frame rate.
                  root.revealT = Math.min(1, root.revealT + ms / 12000)
                  if (root.revealT >= 1) root.playing = false
                }
                Model.step(root.currentGraph,
                           graphCanvas.width, graphCanvas.height,
                           root.revealT, ms)
                graphCanvas.requestPaint()
                if (!root.playing && Model.settled())
                  root.layoutLive = false
              }
            }

            // Settled: nothing moves, but fresh memories breathe and the root
            // keeps its halo. Five slow frames a second carry that, and only
            // on glowCanvas: a full graph frame costs about 90 ms under a
            // software renderer at 2x scale, and ten of those a second held
            // a settled cockpit at 40% of a core. The physics does not run
            // again until something changes.
            Timer {
              id: graphBreath
              interval: 200
              repeat: true
              running: root.cockpitVisible && !presentationHold.running
                       && root.currentGraph !== null
                       && !root.layoutLive
              onTriggered: {
                Model.breathe(interval)
                glowCanvas.requestPaint()
              }
            }

            onPaint: {
              var ctx = getContext("2d")
              ctx.reset()
              ctx.clearRect(0, 0, width, height)
              ctx.fillStyle = graphCard.color
              ctx.fillRect(0, 0, width, height)
              var graph = root.currentGraph
              if (!graph || !graph.nodes) return
              var now = root.nowMs > 0 ? root.nowMs : Date.now()
              var nodes = graph.nodes, edges = graph.edges
              var i, p, q, n
              var eff = root.effId
              var nbrs = eff !== "" ? Model.neighbors(eff) : null

              var vis = {}
              for (i = 0; i < nodes.length; i++)
                vis[Model.graphMapKey(nodes[i].id)] =
                  root.nodeVisible(nodes[i])

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
                if (!vis[Model.graphMapKey(edges[i].s)]
                    || !vis[Model.graphMapKey(edges[i].d)]) continue
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

              var nodeObstacles = []
              for (i = 0; i < nodes.length; i++) {
                n = nodes[i]
                if (!vis[Model.graphMapKey(n.id)]) continue
                p = Model.posOf(n.id)
                if (!p) continue
                var dimmed = eff !== "" && n.id !== eff &&
                  !Model.hasNeighbor(nbrs, n.id)
                var r = Model.nodeRadius(n)
                nodeObstacles.push({
                  id: n.id, left: p.x - r - 3, right: p.x + r + 3,
                  top: p.y - r - 3, bottom: p.y + r + 3
                })
                var col = Model.nodeColor(n, root.pal)
                // The fresh glow and the root halo breathe on glowCanvas.
                ctx.fillStyle = dimmed ? Qt.alpha(col, 0.22) : col
                ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 2 * Math.PI)
                ctx.fill()
                if (n.id === eff) {
                  ctx.strokeStyle = root.fg
                  ctx.beginPath()
                  ctx.arc(p.x, p.y, r + 3, 0, 2 * Math.PI)
                  ctx.stroke()
                }
              }

              var labelNodes = []
              for (i = 0; i < nodes.length; i++) {
                n = nodes[i]
                if (!vis[Model.graphMapKey(n.id)]) continue
                var isEff = n.id === eff
                var isNbr = Model.hasNeighbor(nbrs, n.id)
                var anchorLbl = n.t === "organ" || n.id === "sia/cortex"
                if (!anchorLbl && !isEff && !isNbr) continue
                p = Model.posOf(n.id)
                if (!p) continue
                labelNodes.push({
                  node: n, point: p, effective: isEff, neighbor: isNbr,
                  priority: n.id === "sia/cortex" ? 400
                    : isEff ? 350 : n.t === "organ" ? 200 + (n.deg || 0)
                    : 100 + (n.deg || 0)
                })
              }
              labelNodes.sort(function(a, b) {
                if (a.priority !== b.priority) return b.priority - a.priority
                return a.node.id < b.node.id ? -1
                  : (a.node.id > b.node.id ? 1 : 0)
              })

              var placedLabels = []
              var topSafe = Style.space(34)
              var bottomSafe = height - Style.space(54)
              var sideSafe = Style.space(8)
              var labelHeight = Style.font.caption + 6
              ctx.font = Style.font.caption + "px " + root.fontFamily
              ctx.textAlign = "center"
              ctx.textBaseline = "middle"

              function overlaps(left, right, top, bottom, rect, padding) {
                return !(right + padding < rect.left
                         || left - padding > rect.right
                         || bottom + padding < rect.top
                         || top - padding > rect.bottom)
              }

              for (i = 0; i < labelNodes.length; i++) {
                var labelNode = labelNodes[i]
                n = labelNode.node
                p = labelNode.point
                var label = Model.shortLabel(n)
                var labelWidth = ctx.measureText(label).width + 8
                var candidates = Model.labelCandidates(
                  p.x, p.y, cx, cy, Model.nodeRadius(n),
                  labelWidth, labelHeight)
                var chosen = null
                for (var ci = 0; ci < candidates.length; ci++) {
                  var candidate = candidates[ci]
                  var left = candidate.x - labelWidth / 2
                  var right = candidate.x + labelWidth / 2
                  var top = candidate.y - labelHeight / 2
                  var bottom = candidate.y + labelHeight / 2
                  if (left < sideSafe || right > width - sideSafe
                      || top < topSafe || bottom > bottomSafe) continue
                  var blocked = false
                  for (var pi = 0; pi < placedLabels.length && !blocked; pi++)
                    blocked = overlaps(left, right, top, bottom,
                                       placedLabels[pi], 3)
                  for (var oi = 0; oi < nodeObstacles.length && !blocked; oi++) {
                    if (nodeObstacles[oi].id === n.id) continue
                    blocked = overlaps(left, right, top, bottom,
                                       nodeObstacles[oi], 2)
                  }
                  if (!blocked) {
                    chosen = { x: candidate.x, y: candidate.y,
                      left: left, right: right, top: top, bottom: bottom }
                    break
                  }
                }
                if (!chosen) continue
                placedLabels.push(chosen)

                var alpha = labelNode.effective ? 1.0
                  : labelNode.neighbor ? 0.82
                  : (eff !== "" ? 0.28
                     : (n.id === "sia/cortex" ? 0.94 : 0.62))
                ctx.strokeStyle = Qt.alpha(root.fg, alpha * 0.24)
                ctx.beginPath(); ctx.moveTo(p.x, p.y)
                ctx.lineTo(chosen.x, chosen.y); ctx.stroke()
                ctx.fillStyle = Qt.alpha(root.bg,
                  labelNode.effective ? 0.90 : 0.76)
                ctx.fillRect(chosen.left - 2, chosen.top - 1,
                             labelWidth + 4, labelHeight + 2)
                ctx.fillStyle = Qt.alpha(root.fg, alpha)
                ctx.fillText(label, chosen.x, chosen.y)
              }
            }

            MouseArea {
              anchors.fill: parent
              hoverEnabled: true
              function nearest(mx, my) {
                if (!root.currentGraph) return ""
                var best = "", bd = 500
                for (var i = 0; i < root.currentGraph.nodes.length; i++) {
                  var n = root.currentGraph.nodes[i]
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

          // Native rings avoid uploading a full transparent canvas for a
          // small halo. They do not intercept graph inspection underneath.
          Item {
            id: glowCanvas
            anchors.fill: graphCanvas
            opacity: graphCanvas.opacity
            property var rings: []
            function requestPaint() {
              var next = []
              var graph = root.currentGraph
              if (graph && graph.nodes) {
                var eff = root.effId
                var nbrs = eff !== "" ? Model.neighbors(eff) : null
                for (var i = 0; i < graph.nodes.length; i++) {
                  var n = graph.nodes[i]
                  var p = Model.posOf(n.id)
                  if (!p || !root.nodeVisible(n)) continue
                  if (eff !== "" && n.id !== eff
                      && !Model.hasNeighbor(nbrs, n.id)) continue
                  var r = Model.nodeRadius(n)
                  var fresh = Model.freshness(n, root.nowMs)
                  if (fresh > 0.02) {
                    var breathe = 0.75 + 0.25 * Math.sin(Model.phase() * 2
                                                         + p.x * 0.05)
                    next.push({ x: p.x, y: p.y, radius: r + 5 + 4 * fresh,
                      thickness: 5 + 4 * fresh,
                      ink: Qt.alpha(root.accent, 0.28 * fresh * breathe) })
                  }
                  if (n.id === "sia/cortex")
                    next.push({ x: p.x, y: p.y, radius: r + 3.5,
                      thickness: 1.2,
                      ink: Qt.alpha(root.fg, 0.35 + 0.20 * Math.sin(Model.phase())) })
                }
              }
              rings = next
            }
            Repeater {
              model: glowCanvas.rings
              delegate: Rectangle {
                required property var modelData
                x: modelData.x - modelData.radius
                y: modelData.y - modelData.radius
                width: modelData.radius * 2
                height: width
                radius: modelData.radius
                color: "transparent"
                border.width: modelData.thickness
                border.color: modelData.ink
                antialiasing: true
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
            id: replayControl
            activeFocusOnTab: true
            Accessible.role: Accessible.Button
            Accessible.name: replayText.text
            Accessible.description:
              "Replay or stop the bounded graph-growth visualization"
            Accessible.onPressAction: root.toggleGraphReplay()
            Keys.onPressed: function(event) {
              if (!event.isAutoRepeat
                  && (event.key === Qt.Key_Return
                      || event.key === Qt.Key_Enter
                      || event.key === Qt.Key_Space)) {
                root.toggleGraphReplay()
                event.accepted = true
              }
            }
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Style.space(10)
            width: replayText.implicitWidth + Style.space(16)
            height: replayText.implicitHeight + Style.space(8)
            radius: Style.cornerRadius
            color: replayArea.containsMouse
              ? Qt.alpha(root.fg, 0.18) : Qt.alpha(root.fg, 0.08)
            border.color: replayControl.activeFocus
              ? root.accent : Qt.alpha(root.fg, 0.25)
            border.width: replayControl.activeFocus ? 2 : 1
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
                replayControl.forceActiveFocus()
                root.toggleGraphReplay()
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
                { label: "root",    role: "cortex" },
                { label: "source",  role: "organ" },
                { label: "memory",  role: "day" },
                { label: "generated", role: "thought" },
                { label: "record",  role: "record" },
                { label: "skill",   role: "skill" }
              ]
              delegate: Item {
                id: chip
                required property var modelData
                activeFocusOnTab: true
                Accessible.role: Accessible.CheckBox
                Accessible.name: "Show " + chip.modelData.label
                  + " graph nodes"
                Accessible.description:
                  "Toggle this memory kind in the bounded graph display"
                Accessible.checked:
                  !root.hiddenKinds[chip.modelData.role]
                Accessible.onPressAction:
                  root.toggleKind(chip.modelData.role)
                Keys.onPressed: function(event) {
                  if (!event.isAutoRepeat
                      && (event.key === Qt.Key_Return
                          || event.key === Qt.Key_Enter
                          || event.key === Qt.Key_Space)) {
                    root.toggleKind(chip.modelData.role)
                    event.accepted = true
                  }
                }
                width: chipRow.implicitWidth
                height: chipRow.implicitHeight
                Rectangle {
                  anchors.fill: parent
                  anchors.margins: -Style.space(3)
                  radius: Style.cornerRadius
                  color: "transparent"
                  border.color: root.accent
                  border.width: 1
                  visible: chip.activeFocus
                }
                Row {
                  id: chipRow
                  opacity: root.hiddenKinds[chip.modelData.role] ? 0.3 : 1.0
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
                  onClicked: {
                    chip.forceActiveFocus()
                    root.toggleKind(chip.modelData.role)
                  }
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
            text: root.currentGraph
              ? root.currentGraph.nodes.length
                + " of " + root.currentGraph.pages_total
                + " memories · " + root.currentGraph.edges.length + " links · "
                + (root.snap && root.snap.complete ? "complete" : "partial")
              : root.graphGapSettled ? "current graph unavailable" : ""
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
                readonly property var n: root.currentGraph
                  ? root.nodeById(root.effId) : null

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
                  model: root.currentGraph && inspectorCol.n
                    ? Model.nodeEdges(root.effId) : []
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
                text: "GENERATED ENTRIES — " + root.thoughtStreamCountText()
                color: Qt.alpha(root.fg, 0.45)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
              Text {
                // Rows on screen must never outlive the statement that they
                // are current.  If the stream was rejected or vanished, the
                // header says so directly above the prose it qualifies.
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                visible: root.thoughtsBoundary !== ""
                width: thoughtHeader.width
                text: root.thoughtsBoundary
                wrapMode: Text.WordWrap
                color: root.boundaryColor(root.thoughtsBoundary)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
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
              // A revalidated stream fades back in; a withdrawn one empties
              // at once.
              opacity: root.thoughtsLoadValid ? 1 : 0
              Behavior on opacity {
                NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
              }
              pixelAligned: true
              clip: true
              boundsBehavior: Flickable.StopAtBounds
              Controls.ScrollBar.vertical: Controls.ScrollBar {
                policy: Controls.ScrollBar.AsNeeded
              }

              Column {
                id: thoughtCol
                width: parent.width
                spacing: Style.space(8)
                Repeater {
                  model: root.thoughts
                  delegate: Row {
                    id: thoughtRow
                    required property var modelData
                    readonly property string urgencyState:
                      root.thoughtUrgencyState(thoughtRow.modelData)
                    width: thoughtCol.width
                    spacing: Style.space(8)
                    Text {
                      textFormat: Text.PlainText
                      renderType: Text.NativeRendering
                      text: Model.thoughtMark(thoughtRow.modelData.kind)
                      color: thoughtRow.urgencyState === "unrecorded"
                        ? Qt.alpha(root.fg, 0.45)
                        : thoughtRow.urgencyState === "urgent"
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
                        lineHeight: 1.2
                        color: thoughtRow.urgencyState === "unrecorded"
                          ? Qt.alpha(root.fg, 0.6)
                          : thoughtRow.urgencyState === "urgent"
                            ? root.urgent : Qt.alpha(root.fg, 0.85)
                        font.family: "sans-serif"
                        font.pixelSize: Style.font.bodySmall
                      }
                      Text {
                        textFormat: Text.PlainText
                        renderType: Text.NativeRendering
                        text: root.thoughtRowMetadata(
                          thoughtRow.modelData, root.nowMs)
                        width: parent.width
                        wrapMode: Text.WordWrap
                        color: Qt.alpha(root.fg, 0.58)
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

      // ------------------------------------------------ guided first light
      // The checkout is already a functioning, reviewable plugin at this
      // point.  Resident installation remains an informed operator action.
      Rectangle {
        id: firstLightGate
        anchors.fill: parent
        visible: root.showSetupGate
        z: 30
        color: Color.background

        MouseArea { anchors.fill: parent; onClicked: {} }

        Rectangle {
          id: firstLightCard
          anchors.centerIn: parent
          width: parent.width * 0.44
          height: firstLightColumn.implicitHeight + Style.space(24)
          radius: Style.cornerRadius
          color: Qt.alpha(root.fg, 0.04)
          border.color: Qt.alpha(root.accent, 0.45)
          border.width: 1

          Column {
            id: firstLightColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Style.space(12)
            spacing: Style.space(12)

            Text {
              width: parent.width
              textFormat: Text.PlainText
              renderType: Text.NativeRendering
              text: root.setupEyebrow()
              color: root.accent
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
              horizontalAlignment: Text.AlignHCenter
            }

            Text {
              width: parent.width
              textFormat: Text.PlainText
              renderType: Text.NativeRendering
              text: Model.brainGlyph() + root.setupTitle()
              color: root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
              horizontalAlignment: Text.AlignHCenter
            }

            Text {
              width: parent.width
              textFormat: Text.PlainText
              renderType: Text.NativeRendering
              text: root.setupDescription()
              wrapMode: Text.WordWrap
              color: Qt.alpha(root.fg, 0.78)
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              horizontalAlignment: Text.AlignHCenter
            }

            Rectangle {
              width: parent.width
              height: firstLightBoundary.implicitHeight + Style.space(16)
              radius: Style.cornerRadius
              color: Qt.alpha(root.accent, 0.07)
              border.color: Qt.alpha(root.fg, 0.12)
              border.width: 1
              Text {
                id: firstLightBoundary
                anchors.fill: parent
                anchors.margins: Style.space(8)
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
              text: "“Brain” is a product metaphor for auditable local machine memory; it is not a biological brain and does not establish cognition or neuroscience. LOCAL BOUNDARY · SIA is unrelated to Sia.tech. Your click asks this desktop to open a terminal; this cockpit is an overlay above every window, so it steps aside once the installer shell is observed to start, and reports if it never is. SIA holds that terminal open at the end, on success and on a named refusal. This cockpit stays locked until the matching runtime publishes status after `sia ready`."
                wrapMode: Text.WordWrap
                color: Qt.alpha(root.fg, 0.65)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                horizontalAlignment: Text.AlignHCenter
              }
            }

            Text {
              // The gate paints over the close chrome, so it carries its own
              // way out: nothing on this screen may trap the operator behind
              // an overlay while a terminal waits underneath it.
              width: parent.width
              textFormat: Text.PlainText
              renderType: Text.NativeRendering
              text: "Esc closes this cockpit at any time. The installer terminal opens behind it until the cockpit steps aside."
              wrapMode: Text.WordWrap
              color: Qt.alpha(root.fg, 0.55)
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              horizontalAlignment: Text.AlignHCenter
            }

            Text {
              visible: root.setupActionAllowed
              width: parent.width
              textFormat: Text.PlainText
              renderType: Text.NativeRendering
              text: "YOUR CLICK MAY · download pinned restic, Bun, gbrain, and Ollama artifacts; build gbrain; pull the pinned local embedding model; create a signing identity and empty corpus only when no owned memory store exists; and install or restart user services. YOUR CLICK WILL NOT · change how any other tool behaves. The agent skill that gives Claude Code instructions about SIA, the SUPER+SHIFT+B keybinding, and MCP registration are each declined unless you opt into them by name on the command line; the installer prints how."
              wrapMode: Text.WordWrap
              color: Qt.alpha(root.fg, 0.72)
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              horizontalAlignment: Text.AlignHCenter
            }

            Controls.Button {
              id: firstLightButton
              visible: root.setupActionAllowed
              enabled: root.setupActionAllowed && !root.setupLaunchRequested
              width: parent.width
              height: firstLightButtonText.implicitHeight + Style.space(16)
              focusPolicy: Qt.StrongFocus
              hoverEnabled: true
              Accessible.name: root.setupActionLabel()
              Accessible.description: "Ask this desktop to open the SIA installer terminal after reviewing the local installation boundary; the cockpit then reports whether the installer shell actually started."
              onClicked: root.launchSetup()
              background: Rectangle {
                radius: Style.cornerRadius
                color: firstLightButton.hovered
                  ? Qt.alpha(root.accent, 0.28)
                  : Qt.alpha(root.accent, 0.18)
                border.color: firstLightButton.activeFocus
                  ? root.fg : Qt.alpha(root.accent, 0.75)
                border.width: firstLightButton.activeFocus ? 2 : 1
              }
              contentItem: Text {
                id: firstLightButtonText
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
                text: root.setupActionLabel()
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
              }
            }

            Text {
              visible: root.setupLaunchRequested || root.setupTerminalMissing
                || root.setupTerminalPresented
              width: parent.width
              textFormat: Text.PlainText
              renderType: Text.NativeRendering
              text: root.setupPresenceMessage()
              wrapMode: Text.WordWrap
              color: root.setupTerminalMissing ? root.urgent : root.accent
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              horizontalAlignment: Text.AlignHCenter
            }

            Text {
              width: parent.width
              textFormat: Text.PlainText
              renderType: Text.NativeRendering
              text: root.setupActionAllowed
                ? "Enter = continue · Esc = leave setup"
                : "Esc = leave setup"
              color: Qt.alpha(root.fg, 0.4)
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              horizontalAlignment: Text.AlignHCenter
            }
          }
        }
      }
    }
  }
}
