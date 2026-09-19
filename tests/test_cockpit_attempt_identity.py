#!/usr/bin/env python3
"""Process-attempt identity and keyboard contracts for the cockpit."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest

from tests.test_cockpit_boundary_horizon import (
    _JsRunner,
    _qml_element,
    _qml_function,
)


REPO = Path(__file__).resolve().parent.parent


def _read_cockpit():
    return (REPO / "Cockpit.qml").read_text(encoding="utf-8")


class CockpitAttemptIdentityTests(unittest.TestCase):
    def setUp(self):
        self.node = shutil.which("node")
        if self.node is None:
            self.skipTest("Node is unavailable for executable QML logic")

    def _run_gate(self, prelude, function_name):
        source = _qml_function(
            _read_cockpit(), "processAttemptIsCurrent").replace("root.", "")
        result = subprocess.run(
            [self.node, "-e", _JsRunner.SCRIPT, json.dumps([]),
             source + "\n" + prelude, function_name, "[]"],
            cwd=REPO, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_only_the_current_live_attempt_is_accepted(self):
        # The same basis is intentional: a basis-only gate is the defect.
        prelude = """
function scenarios() {
  var oldAttempt = { acceptResults: true, basis: "same-basis" }
  var newAttempt = { acceptResults: true, basis: "same-basis" }
  return {
    current: processAttemptIsCurrent(newAttempt, newAttempt),
    staleSameBasis: processAttemptIsCurrent(newAttempt, oldAttempt),
    retiredCurrent: processAttemptIsCurrent(
      newAttempt, { acceptResults: false, basis: "same-basis" }),
    absent: processAttemptIsCurrent(null, oldAttempt)
  }
}
"""
        self.assertEqual(self._run_gate(prelude, "scenarios"), {
            "current": True,
            "staleSameBasis": False,
            "retiredCurrent": False,
            "absent": False,
        })

    def test_ready_callbacks_carry_their_attempt_identity(self):
        cockpit = _read_cockpit()
        controller = _qml_element(cockpit, "id: readyProc")
        attempt = _qml_element(cockpit, "id: readyAttempt")

        self.assertIn("property var activeAttempt: null", controller)
        self.assertIn("readyAttemptComponent.createObject", controller)
        self.assertIn("root.processAttemptIsCurrent(activeAttempt, attempt)",
                      controller)
        self.assertIn("activeAttempt = null", controller)
        self.assertIn("attempt.acceptResults = false", controller)
        self.assertLess(controller.index("activeAttempt = null"),
                        controller.index("attempt.running = false"))

        for callback in ("onStreamFinished:", "onRunningChanged:",
                         "onExited:"):
            self.assertIn(callback, attempt)
        self.assertIn("readyProc.settle(readyAttempt)", attempt)
        self.assertIn("readyProc.markLaunchFailure(readyAttempt)", attempt)
        self.assertNotIn("readyProc.outText =", attempt)
        self.assertNotIn("readyProc.exitCode =", attempt)

    def test_verification_rejects_an_old_attempt_even_on_the_same_basis(self):
        cockpit = _read_cockpit()
        controller = _qml_element(cockpit, "id: verifyProc")
        attempt = _qml_element(cockpit, "id: verifyAttempt")

        self.assertIn("property var activeAttempt: null", controller)
        self.assertIn("verifyAttemptComponent.createObject", controller)
        self.assertIn("root.processAttemptIsCurrent(activeAttempt, attempt)",
                      controller)
        self.assertIn("attempt.basis === root.snapshotBasis()", controller)
        self.assertIn("root.opened", controller)
        self.assertIn("attempt.acceptResults = false", controller)
        self.assertLess(controller.index("activeAttempt = null"),
                        controller.index("attempt.running = false"))
        self.assertIn("receiptMatches(attempt)", controller)
        self.assertIn('"SIA-VERIFIED-BASIS " + attempt.basis', controller)
        self.assertIn("attempt.exited", controller)
        self.assertIn("attempt.outDone", controller)
        self.assertIn("attempt.exitCode === 0", controller)
        self.assertIn('"--expect-basis", verifyAttempt.basis', attempt)
        self.assertIn("onStreamFinished:", attempt)
        self.assertIn("verifyProc.settle(verifyAttempt)", attempt)
        self.assertIn("verifyProc.finish(verifyAttempt, code)", attempt)
        self.assertNotRegex(cockpit, r"verifyProc\.basis\s*=(?!=)")
        self.assertNotRegex(cockpit, r"verifyProc\.launchPending\s*=(?!=)")

    def test_named_controls_are_keyboard_and_accessibility_complete(self):
        cockpit = _read_cockpit()
        controls = {
            "id: workspaceLockControl": "Accessible.Button",
            "id: closeControl": "Accessible.Button",
            "id: liveReadyControl": "Accessible.Button",
            "id: verifyControl": "Accessible.Button",
            "id: replayControl": "Accessible.Button",
            "id: chip": "Accessible.CheckBox",
        }
        for marker, role in controls.items():
            with self.subTest(control=marker):
                block = _qml_element(cockpit, marker)
                self.assertIn("activeFocusOnTab: true", block)
                self.assertIn("Accessible.role: " + role, block)
                self.assertIn("Accessible.name:", block)
                self.assertIn("Accessible.onPressAction:", block)
                self.assertIn("Keys.onPressed:", block)
                self.assertIn("Qt.Key_Return", block)
                self.assertIn("Qt.Key_Enter", block)
                self.assertIn("Qt.Key_Space", block)
        chip = _qml_element(cockpit, "id: chip")
        self.assertIn("Accessible.checked:", chip)


if __name__ == "__main__":
    unittest.main()
