// SIA COCKPIT — full-screen mission control for the Omarchy Brain.
// Overlay kind: summoned from the bar widget or SUPER+SHIFT+B, dismissed
// with Esc / ✕ / click on the header brand. Pixels only — renders the
// brainstem's snapshots; the brain is gbrain + the signed corpus.

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
  property var installCompletion: null
  property bool statusResolved: false
  property bool statusLoadValid: false
  property bool installCompletionResolved: false
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
  property var continuity: null
  property string continuityBoundary: ""
  property var continuitySchedule: null
  property string continuityScheduleBoundary: ""
  property bool continuitySheetOpen: false
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
  readonly property int continuityInputMaxLength: 4096
  readonly property int continuityResponseMaxLength: 65536

  readonly property string effId: hoverId !== "" ? hoverId : selectedId
  readonly property string statePath:
    (Quickshell.env("HOME") || "") + "/.local/state/sia"
  readonly property string continuityPath:
    (Quickshell.env("HOME") || "")
      + "/.local/state/sia-continuity/status.json"
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
    Model.runtimeLifecycle(root.statusLoadValid ? root.status : null,
                           root.pluginVersion)
  readonly property string releaseLifecycle:
    !root.statusResolved || !root.installCompletionResolved ? "checking"
      : Model.guidedLifecycle(root.statusLoadValid ? root.status : null,
                              root.installCompletion, root.pluginVersion)
  readonly property bool setupRequired: root.releaseLifecycle !== "ready"
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
      : stale ? "stale" : (status && status.state ? status.state : "unknown")
  readonly property int eventsToday:
    status && status.events_today ? status.events_today : 0
  readonly property var snap:
    graph && graph.snapshot ? graph.snapshot : null
  readonly property real staleAfterSec: configuredStaleAfterSec()
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
  readonly property string continuityState:
    root.continuity ? root.continuity.state : "unknown"
  readonly property color continuityColor: {
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

  function continuityStateText() {
    if (root.restoreCorrelationLost) return "NEEDS ATTENTION"
    if (root.restoreVerificationPending) return "RESTORE VERIFYING"
    if (!root.continuity) return "STATUS UNAVAILABLE"
    return Model.continuityStateLabel(root.continuity.state)
  }

  function continuityRepositoryText() {
    if (!root.continuity) return "No continuity status has been published."
    var display = String(root.continuity.repository_display || "").trim()
    if (display !== "") return display
    return root.continuity.state === "unconfigured"
      ? "Choose a recovery repository to begin."
      : "Repository identity is not available."
  }

  function continuityLatestText() {
    var latest = root.continuity ? root.continuity.latest : null
    if (!latest) return "No recovery copy has been recorded."
    var age = Model.timeAgo(latest.created_at, root.nowMs)
    var when = age !== "" ? age : latest.created_at
    var classification = Model.continuityLatestReady(latest)
      ? "Recovery-ready copy · "
      : latest.verified
        ? "Verified recovery material · "
        : "Unverified copy · "
    return classification
      + when + " · " + latest.profile
  }

  function continuityDetailText() {
    if (root.continuityBoundary !== "") return root.continuityBoundary
    if (!root.continuity) return "The continuity worker is not reporting."
    var detail = String(root.continuity.detail || "").trim()
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
    return root.continuity && root.continuity.prepared
      ? root.continuity.prepared : null
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
        || !Model.continuityCanApply(root.continuity)) return false
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
        if (Model.continuityCanApply(root.continuity))
          restorePhraseField.forceActiveFocus()
        else if (root.continuityState === "restoring")
          continuityCloseButton.forceActiveFocus()
        else restoreSnapshotField.forceActiveFocus()
      }
      else if (Model.continuityCanBackUp(root.continuity))
        continuityCloseButton.forceActiveFocus()
      else if (Model.continuityCanPrepare(root.continuity)
               || Model.continuityCanApply(root.continuity))
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
        && root.continuity && root.continuity.latest)
      root.restoreSnapshotInput = root.continuity.latest.snapshot_id
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
    if (!prepared || !Model.continuityCanApply(root.continuity)) {
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
      && value.schema_version === 1
      && value.accepted === true
      && typeof value.request_id === "string" && value.request_id !== ""
      && value.operation === "restore-apply"
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
                      ? "Reconnect this brain to an existing repository"
                      : root.continuityPage === "restore"
                        ? "Inspect, prepare, then deliberately restore"
                        : "Keep the brain recoverable beyond this computer"
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
                  text: Model.continuityBarMark(root.continuity)
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
                  visible: !!root.continuity
                    && root.continuityState !== "unconfigured"
                  enabled: Model.continuityCanBackUp(root.continuity)
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
                  visible: !!root.continuity
                    && root.continuityState !== "unconfigured"
                  enabled: Model.continuityCanCheck(root.continuity)
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
                  visible: !!root.continuity
                    && root.continuityState !== "unconfigured"
                  enabled: (Model.continuityCanPrepare(root.continuity)
                            || Model.continuityCanApply(root.continuity))
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
                  enabled: Model.continuityCanPrepare(root.continuity)
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
                  && Model.continuityCanApply(root.continuity)
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
                  text: "Preparation is non-destructive. Applying it replaces live SIA brain state. Every value below is checked again by the backend under the exclusive lifecycle lease."
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
          message: "Begin the live restore and re-adopt its corpus receipt on this machine? This replaces live brain state. Cancel applies nothing and resets the ceremony. Success remains withheld until SIA is ready and its signed ledger verifies."
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
      return "FIRST LIGHT · LOCAL BRAIN NOT YET INSTALLED"
    if (root.releaseLifecycle === "installing")
      return "FIRST LIGHT · INSTALLATION IN PROGRESS"
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
      return "  First light is underway"
    if (root.releaseLifecycle === "update") return "  Finish the SIA update"
    if (root.releaseLifecycle === "ahead") return "  Update this cockpit"
    return "  Repair the release boundary"
  }

  function setupDescription() {
    if (root.releaseLifecycle === "checking")
      return "SIA is reading the resident status and the separate first-light completion record. No installer has been started."
    if (root.releaseLifecycle === "setup")
      return "The Marketplace installed SIA's cockpit. The resident brain is not complete; first light remains a deliberate local action."
    if (root.releaseLifecycle === "installing")
      return "A matching installer recorded work in progress. Keep its terminal open, or retry here only if that terminal has ended."
    if (root.releaseLifecycle === "update") {
      var installed = root.status && typeof root.status.version === "string"
        ? root.status.version : "a legacy runtime"
      return "The cockpit is " + root.pluginVersion
        + ", while the resident status is " + installed
        + ". The installer verifies ownership and retains the corpus and signing identity while advancing the runtime."
    }
    if (root.releaseLifecycle === "ahead") {
      var resident = root.status && typeof root.status.version === "string"
        ? root.status.version : "newer"
      return "Resident SIA " + resident + " is newer than cockpit "
        + root.pluginVersion
        + ". Installation is disabled to prevent a downgrade. Run `omarchy plugin update khephri.sia`, then reopen the cockpit."
    }
    return "SIA could not establish a matching resident status and first-light completion record. The repair action re-enters the fail-closed installer, which verifies ownership and refuses unsafe replacement."
  }

  function setupActionLabel() {
    if (root.releaseLifecycle === "setup") return "BEGIN FIRST LIGHT"
    if (root.releaseLifecycle === "installing")
      return "REOPEN OR RETRY IN TERMINAL"
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

  function toggleGraphReplay() {
    if (!root.graph) return
    if (root.playing) {
      root.playing = false
      root.revealT = 1.0
    } else {
      Model.replayLayout(root.graph, graphCanvas.width, graphCanvas.height)
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
    verifyMsg = ""
    verifyOk = false
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
    // being read as this session's presentation.
    setupAttemptId = ""
    setupRequestedAtSec = 0
    setupPresenceApply.stop()
    setupPresenceDeadline.stop()
    setupYield.stop()
    readyProc.cancel()
    clearReadyCheck()
    // Opening requests fresh bytes without discarding the last validated
    // generation. Cold startup and every failed load still resolve fail-closed.
    statusFile.reload(); installCompletionFile.reload()
    graphFile.reload(); thoughtsFile.reload()
    continuityFile.reload()
    continuityScheduleRefresh.restart()
    if (root.graph && graphCanvas.width > 0)
      Model.syncGraph(root.graph, graphCanvas.width, graphCanvas.height)
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
    if (!root.cockpitVisible) return
    Qt.callLater(function() {
      if (!root.cockpitVisible) return
      if (root.setupActionAllowed) firstLightButton.forceActiveFocus()
      else if (root.continuitySheetOpen) root.focusContinuityPage()
      else keyCatcher.forceActiveFocus()
      graphCanvas.requestPaint()
    })
  }

  onReleaseLifecycleChanged: {
    if (!root.cockpitVisible) return
    Qt.callLater(function() {
      if (!root.cockpitVisible) return
      if (root.setupActionAllowed) firstLightButton.forceActiveFocus()
      else keyCatcher.forceActiveFocus()
    })
  }

  function applyStatus(text) {
    try {
      const parsed = JSON.parse(text)
      if (!root.validStatusSnapshot(parsed)) {
        root.statusLoadValid = false
        root.statusBoundary = root.status
          ? "last good status; latest status rejected" : "no valid status"
        return
      }
      root.status = parsed
      root.statusLoadValid = true
      root.statusBoundary = ""
      readyProc.cancel()
      root.clearReadyCheck()
      const ts = Date.parse(parsed.ts)
      root.stale = !(ts > 0) ||
        (Date.now() - ts) > root.staleAfterSec * 1000
    } catch (e) {
      root.statusLoadValid = false
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
      readyProc.cancel()
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

  function applyContinuity(text) {
    try {
      const parsed = JSON.parse(text)
      if (!Model.validContinuityStatus(parsed)) {
        root.continuityBoundary = root.continuity
          ? "last good continuity status; latest update rejected"
          : "no valid continuity status"
        return
      }
      var previousPrepared = root.preparedRestore()
      var previousPreparedId = previousPrepared
        ? previousPrepared.prepared_id : ""
      var nextPreparedId = parsed.prepared
        ? parsed.prepared.prepared_id : ""
      root.continuity = parsed
      root.continuityBoundary = ""
      if (previousPreparedId !== nextPreparedId) {
        root.restoreConfirmOpen = false
        root.clearRestoreCeremony()
      }
      if (root.restoreVerificationPending) {
        var operation = root.matchingRestoreOperation(parsed)
        if (operation && (operation.phase === "accepted"
                          || operation.phase === "running")) {
          root.continuityActionOk = false
          root.continuityActionMsg = "Restore is running. Readiness and SIA signed-ledger verification are still pending."
        } else if (operation && operation.phase === "verified"
                   && operation.ready
                   && operation.sia_ledger_verified) {
          root.restoreVerificationPending = false
          root.continuityActionOk = true
          root.continuityActionMsg = "Restore verified: SIA is ready and its signed ledger passes."
        } else if (operation && operation.phase === "verified") {
          root.restoreVerificationPending = false
          root.continuityActionOk = false
          root.continuityActionMsg = "Restore terminal record did not prove both readiness and SIA signed-ledger verification."
        } else if (operation && (operation.phase === "failed"
                                 || operation.phase === "blocked")) {
          root.restoreVerificationPending = false
          root.continuityActionOk = false
          root.continuityActionMsg = "The exact restore request did not reach verified readiness. Review continuity details before retrying."
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
      root.continuityBoundary = root.continuity
        ? "last good continuity status; latest update rejected"
        : "no valid continuity status"
    }
  }

  function applyContinuitySchedule(text) {
    try {
      const parsed = JSON.parse(text)
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
      const parsed = JSON.parse(text)
      if (!Model.setupTerminalPresented(parsed, root.setupRequestedAtSec,
                                        root.setupAttemptId))
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

  function applyInstallCompletion(text) {
    try {
      const parsed = JSON.parse(text)
      root.installCompletion = parsed
    } catch (e) { root.installCompletion = null }
  }

  FileView {
    id: statusFile
    path: root.statePath + "/status.json"
    watchChanges: true
    printErrors: false
    onLoaded: {
      root.applyStatus(text())
      root.statusResolved = true
    }
    onLoadFailed: {
      root.statusLoadValid = false
      root.statusResolved = true
      root.statusBoundary = root.status
        ? "last good status; resident status unavailable"
        : "resident status unavailable"
    }
    onFileChanged: {
      // Atomic publication is a refresh, not evidence that the resident
      // generation became unsafe. Commit the new result in the load callbacks.
      statusApply.restart()
    }
  }
  Timer { id: statusApply; interval: 150; repeat: false
          onTriggered: statusFile.reload() }

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

  FileView {
    id: continuityFile
    path: root.continuityPath
    watchChanges: true
    printErrors: false
    onLoaded: root.applyContinuity(text())
    onFileChanged: continuityApply.restart()
  }
  Timer { id: continuityApply; interval: 150; repeat: false
          onTriggered: {
            continuityFile.reload()
            root.applyContinuity(continuityFile.text())
          } }
  Timer { id: continuityScheduleRefresh; interval: 150; repeat: false
          onTriggered: continuityScheduleProc.refresh() }
  Timer {
    interval: 60000
    running: root.opened
    repeat: true
    onTriggered: continuityScheduleProc.refresh()
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
      // First-light is an install lifecycle barrier, not a routine status
      // refresh.  Withdraw validated pixels until the changed record settles.
      root.installCompletionResolved = false
      installCompletionApply.restart()
    }
  }
  Timer { id: installCompletionApply; interval: 150; repeat: false
          onTriggered: installCompletionFile.reload() }

  FileView {
    id: setupPresenceFile
    path: root.setupPresencePath
    watchChanges: true
    printErrors: false
    // Reading this owner-only marker is the whole new capability: it observes
    // that the installer shell started in a terminal.  It is not readiness,
    // it starts nothing, and an absent or unreadable marker is fail-closed.
    onLoaded: root.applySetupPresence(text())
    onLoadFailed: { }
    onFileChanged: {
      // A change is worth exactly one reload.  Only launchSetup() starts the
      // repeating poll, and only under the deadline that is guaranteed to
      // stop it, so an unrequested marker change can never leave a timer
      // running for the life of the shell.
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
        ? "SIA signed ledger re-verified ✓"
        : "CHAIN VERIFICATION INCOMPLETE"
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
  Process {
    id: readyProc
    property string outText: ""
    property string errText: ""
    property int exitCode: 0
    property bool exited: false
    property bool outDone: false
    property bool errDone: false
    property bool launchFailed: false
    // A failed exec does not produce an `exited` signal in Quickshell 0.3,
    // so retain the start boundary independently of normal completion.
    property bool launchPending: false
    property bool startedForAttempt: false
    property bool discardResult: false
    property bool checking: false
    command: [(Quickshell.env("HOME") || "") + "/.local/bin/sia", "ready"]

    function startCheck() {
      if (checking || running) return
      outText = ""
      errText = ""
      exitCode = 0
      exited = false
      outDone = false
      errDone = false
      launchFailed = false
      launchPending = true
      startedForAttempt = false
      discardResult = false
      checking = true
      root.clearReadyCheck()
      running = true
    }

    function cancel() {
      // Snapshot and overlay boundaries must not later acquire a result from
      // an earlier process/collector callback.
      discardResult = true
      launchPending = false
      checking = false
      if (running) running = false
    }

    function markLaunchFailure() {
      if (discardResult || launchFailed) return
      launchPending = false
      launchFailed = true
      checking = false
      root.readyChecked = true
      root.readyOk = false
      root.readyDetail = "could not start the local sia readiness command"
    }

    function settle() {
      if (discardResult || launchFailed || !exited || !outDone || !errDone)
        return
      checking = false
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
    // Quickshell's Process reports a failed exec as a transition back to
    // !running without an exited signal. Its public `started` signal lets us
    // distinguish that from a process which started and later completed.
    onStarted: {
      readyProc.startedForAttempt = true
      readyProc.launchPending = false
    }
    onRunningChanged: {
      if (!running && readyProc.launchPending
          && !readyProc.startedForAttempt)
        readyProc.markLaunchFailure()
    }
    onExited: function(code) {
      readyProc.exitCode = code
      readyProc.exited = true
      readyProc.settle()
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
            : JSON.parse(outText.replace(/^\s+|\s+$/g, ""))
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
    color: Color.background
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.namespace: "sia-cockpit"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: root.cockpitVisible
      ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    Item {
      id: keyCatcher
      anchors.fill: parent
      focus: true

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
            id: workspaceLockControl
            readonly property real maximumTextWidth: Style.space(180)
            anchors.verticalCenter: parent.verticalCenter
            width: workspaceLockText.width + Style.space(16)
            height: workspaceLockText.implicitHeight + Style.space(8)
            radius: Style.cornerRadius
            color: workspaceLockArea.containsMouse
              ? Qt.alpha(root.workspaceLockActive ? root.accent : root.fg, 0.18)
              : Qt.alpha(root.workspaceLockActive ? root.accent : root.fg, 0.08)
            border.color: Qt.alpha(
              root.workspaceLockActive ? root.accent : root.fg, 0.25)
            border.width: 1
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
              onClicked: root.toggleWorkspaceLock()
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
              enabled: !readyProc.checking && !readyProc.running
              onClicked: readyProc.startCheck()
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
          Controls.ScrollBar.vertical: Controls.ScrollBar {
            policy: Controls.ScrollBar.AsNeeded
          }

        Column {
          id: leftPane
          width: leftScroll.width
          spacing: body.gap

          // Continuity is a separate operational truth plane: it stays above
          // ordinary brain vitals and remains legible while restore quiesces
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
                  visible: !!root.continuity
                    && root.continuityState !== "unconfigured"
                  enabled: Model.continuityCanBackUp(root.continuity)
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
                  visible: !!root.continuity
                    && root.continuityState !== "unconfigured"
                  enabled: (Model.continuityCanPrepare(root.continuity)
                            || Model.continuityCanApply(root.continuity))
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
                width: vitalsCol.width
                columns: 2
                columnSpacing: Style.space(14)
                rowSpacing: Style.space(2)
                readonly property var mind:
                  root.status && root.status.mind ? root.status.mind : ({})
                readonly property real labelWidth: Math.max(
                  stabilityLabel.implicitWidth, reviewLabel.implicitWidth,
                  pinsLabel.implicitWidth)
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
                Model.step(root.graph, graphCanvas.width, graphCanvas.height,
                           root.revealT)
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

              var nodeObstacles = []
              for (i = 0; i < nodes.length; i++) {
                n = nodes[i]
                if (!vis[n.id]) continue
                p = Model.posOf(n.id)
                if (!p) continue
                var dimmed = eff !== "" && n.id !== eff &&
                  !(nbrs && nbrs[n.id])
                var r = Model.nodeRadius(n)
                nodeObstacles.push({
                  id: n.id, left: p.x - r - 3, right: p.x + r + 3,
                  top: p.y - r - 3, bottom: p.y + r + 3
                })
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

              var labelNodes = []
              for (i = 0; i < nodes.length; i++) {
                n = nodes[i]
                if (!vis[n.id]) continue
                var isEff = n.id === eff
                var isNbr = nbrs && nbrs[n.id]
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

      // ------------------------------------------------ guided first light
      // The checkout is already a functioning, reviewable plugin at this
      // point.  Resident installation remains an informed operator action.
      Rectangle {
        id: firstLightGate
        anchors.fill: parent
        visible: root.setupRequired
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
                text: "LOCAL BOUNDARY · SIA the Omarchy Brain is unrelated to Sia.tech. Your click asks this desktop to open a terminal; this cockpit is an overlay above every window, so it steps aside once the installer shell is observed to start, and reports if it never is. SIA holds that terminal open at the end, on success and on a named refusal. This cockpit stays locked until the matching runtime publishes status after `sia ready`."
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
              text: "YOUR CLICK MAY · download pinned restic, Bun, gbrain, and Ollama artifacts; build gbrain; pull the pinned local embedding model; create a signing identity and empty corpus only when no owned brain exists; and install or restart user services."
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
