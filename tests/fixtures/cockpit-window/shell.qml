import QtQuick
import Quickshell
import Quickshell.Io
import "plugin" as Sia

ShellRoot {
  id: harness
  property int step: 0
  property var members: []
  property var nativeWindow: null
  property var overlayWindow: null
  property var content: null
  property int summons: 0
  property int hides: 0
  property bool failed: false
  property int observedClientWidth: 0
  property int observedClientHeight: 0

  function check(condition, label) {
    console.log("SIA-WINDOW-CHECK " + JSON.stringify({label: label, pass: !!condition}))
    if (!condition) failed = true
  }

  function inventory() {
    for (var i = 0; i < cockpit.data.length; i++) {
      var object = cockpit.data[i]
      members.push(object)
      var name = String(object)
      if (name.indexOf("FloatingWindow") !== -1) nativeWindow = object
      if (name.indexOf("PanelInterface") !== -1) overlayWindow = object
    }
    var host = cockpit.windowed ? nativeWindow : overlayWindow
    if (host !== null) {
      var children = host.contentItem.children
      for (var j = 0; j < children.length; j++)
        if (children[j].focus === true) content = children[j]
    }
    console.log("SIA-WINDOW-MEMBERS " + members.map(String).join(","))
    check(nativeWindow !== null && overlayWindow !== null, "both-surfaces-created")
    check(content !== null, "single-content-found")
  }

  function stableMembers() {
    if (cockpit.data.length !== members.length) return false
    for (var i = 0; i < members.length; i++)
      if (cockpit.data[i] !== members[i]) return false
    return true
  }

  function present(mode) {
    check(cockpit.showPresentation(mode) === "sia-cockpit-v1:" + mode,
          "ack-" + mode + "-" + step)
  }

  function firstWindow() {
    inventory()
    present("window")
    cockpit.restoreRequestId = "fixture-pending-operation"
    cockpit.repositoryInput = "fixture-input"
    check(cockpit.opened && cockpit.windowed, "window-open")
    check(cockpit.releaseLifecycle === "ready" && cockpit.currentGraph !== null,
          "fixture-main-interface-admitted")
  }

  function repeatedWindow() {
    check(nativeWindow.visible && !overlayWindow.visible, "only-window-visible")
    check(content.parent === nativeWindow.contentItem, "window-parent")
    present("window")
    check(summons === 1, "one-summon-after-repeat")
    check(cockpit.restoreRequestId === "fixture-pending-operation"
          && cockpit.repositoryInput === "fixture-input", "repeat-preserves-inputs")
    check(stableMembers(), "repeat-preserves-component-members")
    console.log("SIA-WINDOW-AWAIT-COMPOSITOR-RESIZE")
  }

  function overlayThenWindow() {
    check(overlayWindow.visible && !nativeWindow.visible, "only-overlay-visible")
    check(content.parent === overlayWindow.contentItem, "overlay-parent")
    check(cockpit.restoreRequestId === "fixture-pending-operation"
          && cockpit.repositoryInput === "fixture-input", "switch-preserves-inputs")
    check(stableMembers(), "switch-preserves-component-members")
    check(cockpit.showPresentation("invalid") === "invalid-presentation",
          "invalid-mode-refused")
    check(!cockpit.windowed, "invalid-mode-preserves-state")
    present("window")
    cockpit.setupTerminalPresented = true
    present("overlay")
  }

  function afterSetupYield() {
    check(!cockpit.opened && hides > 0, "observed-setup-yields-on-overlay-switch")
    check(cockpit.restoreRequestId === "fixture-pending-operation",
          "dismiss-keeps-operation-identity")
    present("window")
    check(summons === 2, "reopen-uses-same-component")
    check(stableMembers(), "reopen-preserves-component-members")
    console.log("SIA-WINDOW-AWAIT-COMPOSITOR-CLOSE")
  }

  QtObject {
    id: facade
    property var shellConfig: ({})
    function summon(id, payload) {
      if (id !== "khephri.sia") return false
      summons += 1
      cockpit.open(payload)
      return true
    }
    function hide(id) {
      if (id !== "khephri.sia") return false
      hides += 1
      cockpit.close()
      return true
    }
    function updateEntryInline(id, settings) { return id === "khephri.sia" }
  }

  // Minimal implementation of the installed host's call interface, for
  // transport qualification. This is not the live Omarchy plugin loader.
  IpcHandler {
    target: "shell"
    function call(id: string, method: string, argument: string): string {
      if (id !== "khephri.sia" || method !== "showPresentation") return "unknown"
      return cockpit.showPresentation(argument)
    }
  }

  IpcHandler {
    target: "fixture"
    function observedSize(width: int, height: int): string {
      observedClientWidth = width
      observedClientHeight = height
      return "ok"
    }
  }

  Sia.Cockpit {
    id: cockpit
    shell: facade
    manifest: ({id: "khephri.sia"})
  }

  Timer {
    interval: 750
    running: true
    repeat: true
    onTriggered: {
      step += 1
      try {
        if (step === 1) firstWindow()
        else if (step === 2) repeatedWindow()
        else if (step === 3) {
          console.log("SIA-WINDOW-SIZE " + nativeWindow.width + "x" + nativeWindow.height)
          check(observedClientWidth >= 960 && observedClientHeight >= 640
                && nativeWindow.width === observedClientWidth
                && nativeWindow.height === observedClientHeight,
                "compositor-resize")
          console.log("SIA-WINDOW-RESIZED")
        }
        else if (step === 4) present("overlay")
        else if (step === 5) overlayThenWindow()
        else if (step === 8) afterSetupYield()
        else if (step === 9) {
          check(!cockpit.opened, "compositor-close-dismisses")
          present("window")
          check(nativeWindow.visible, "compositor-close-reopen")
          console.log("SIA-WINDOW-RESULT " + (failed ? "FAILED" : "TESTED"))
          Qt.quit()
        }
      } catch (error) {
        console.log("SIA-WINDOW-EXCEPTION " + error)
        failed = true
        Qt.quit()
      }
    }
  }
}
