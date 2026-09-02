"""Release contract for continuity's fail-closed UI boundary."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest


REPO = Path(__file__).resolve().parent.parent


def _read(relative):
    return (REPO / relative).read_text(encoding="utf-8")


class ContinuityUiContractTests(unittest.TestCase):
    def _model_validator_accepts(self, validator_name, payload):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node is unavailable for executable Model.js check")
        script = r'''
const fs = require("fs")
const vm = require("vm")
const source = fs.readFileSync(process.argv[1], "utf8")
  .replace(/^\.pragma library\s*$/m, "")
const context = {}
vm.createContext(context)
vm.runInContext(source, context)
const validator = context[process.argv[2]]
if (typeof validator !== "function")
  throw new Error("missing Model.js validator: " + process.argv[2])
const payload = JSON.parse(process.argv[3])
process.stdout.write(JSON.stringify(validator(payload)))
'''
        result = subprocess.run(
            [node, "-e", script, str(REPO / "Model.js"), validator_name,
             json.dumps(payload, separators=(",", ":"))],
            cwd=REPO, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def _model_accepts(self, payload):
        return self._model_validator_accepts(
            "validContinuityStatus", payload)

    def _schedule_model_accepts(self, payload):
        return self._model_validator_accepts(
            "validContinuitySchedule", payload)

    def test_verified_state_requires_a_ready_identity_matching_copy(self):
        model = _read("Model.js")
        _prefix, marker, remainder = model.partition(
            "function validContinuityStatus(value) {")
        self.assertTrue(marker)
        validator, marker, _suffix = remainder.partition(
            "function continuityStateLabel(state) {")
        self.assertTrue(marker)

        self.assertIn('value.state !== "verified"', validator)
        self.assertIn("continuityLatestReady(value.latest)", validator)

        _prefix, marker, readiness_remainder = model.partition(
            "function continuityLatestReady(value) {")
        self.assertTrue(marker)
        readiness_validator, marker, _suffix = readiness_remainder.partition(
            "function validContinuityPrepared(value) {")
        self.assertTrue(marker)
        self.assertIn("isPlainRecord(value)", readiness_validator)
        self.assertIn('value.snapshot_id !== ""', readiness_validator)
        self.assertIn('value.created_at !== ""', readiness_validator)
        self.assertIn('value.profile !== ""', readiness_validator)
        self.assertIn("value.verified === true", readiness_validator)
        self.assertIn('value.readiness === "ready"', readiness_validator)
        self.assertIn("value.identity_matches === true", readiness_validator)

        _prefix, marker, latest_remainder = model.partition(
            "function validContinuityLatest(value) {")
        self.assertTrue(marker)
        latest_validator, marker, _suffix = latest_remainder.partition(
            "function validContinuityPrepared(value) {")
        self.assertTrue(marker)
        self.assertIn(
            'typeof value.identity_matches === "boolean"',
            latest_validator)

        for surface in ("Cockpit.qml", "Panel.qml"):
            self.assertIn(
                "Model.validContinuityStatus(parsed)", _read(surface))
        self.assertIn(
            "Model.continuityLatestReady(latest)", _read("Cockpit.qml"))

        latest = {
            "snapshot_id": "snapshot",
            "created_at": "published",
            "verified": True,
            "readiness": "ready",
            "profile": "daily",
            "identity_matches": True,
        }
        status = {
            "schema_version": 2,
            "state": "verified",
            "detail": "",
            "repository_display": "repository",
            "latest": latest,
            "prepared": None,
            "operation": None,
        }
        self.assertTrue(self._model_accepts(status))
        self.assertFalse(self._model_accepts({
            **status, "schema_version": 1}))
        self.assertFalse(self._model_accepts({
            **status, "latest": {**latest, "snapshot_id": ""}}))

        successful_restore = {
            **status,
            "state": "recovery-only",
            "latest": None,
            "operation": {
                "request_id": "request",
                "kind": "restore-apply",
                "prepared_id": "prepared",
                "phase": "verified",
                "ready": True,
                "sia_ledger_verified": True,
            },
        }
        self.assertTrue(self._model_accepts(successful_restore))

    def test_schedule_validator_accepts_only_the_live_contract(self):
        upload = {
            "cadence": "hourly",
            "enabled": True,
            "active": True,
            "persistent": True,
            "wake_system": False,
            "last_trigger_at": "2026-09-02T20:00:05Z",
            "next_trigger_at": "2026-09-02T21:00:00Z",
        }
        verification = {
            "cadence": "weekly",
            "enabled": True,
            "active": True,
            "persistent": True,
            "wake_system": False,
            "last_trigger_at": None,
            "next_trigger_at": "2026-09-07T04:00:00Z",
        }
        schedule = {
            "schema_version": 1,
            "configured": True,
            "automatic": True,
            "observed_at": "2026-09-02T20:44:00Z",
            "upload": upload,
            "verification": verification,
        }
        self.assertTrue(self._schedule_model_accepts(schedule))

        invalid = {
            "schema version": {**schedule, "schema_version": 2},
            "upload cadence": {
                **schedule, "upload": {**upload, "cadence": "weekly"}},
            "verification cadence": {
                **schedule,
                "verification": {**verification, "cadence": "hourly"}},
            "observed timestamp": {
                **schedule, "observed_at": "2026-09-02 20:44:00"},
            "normalized impossible timestamp": {
                **schedule, "observed_at": "2026-02-31T20:44:00Z"},
            "last-trigger timestamp": {
                **schedule,
                "upload": {**upload, "last_trigger_at": "not-a-time"}},
            "next-trigger timestamp": {
                **schedule,
                "verification": {
                    **verification,
                    "next_trigger_at": "2026-09-07T00:00:00-04:00"}},
            "automatic false while live": {
                **schedule, "automatic": False},
            "automatic true while inactive": {
                **schedule,
                "upload": {**upload, "active": False}},
        }
        for boundary, candidate in invalid.items():
            with self.subTest(boundary=boundary):
                self.assertFalse(self._schedule_model_accepts(candidate))

    def test_cockpit_explains_automatic_and_optional_backup_actions(self):
        cockpit = _read("Cockpit.qml")

        self.assertIn("Model.validContinuitySchedule(parsed)", cockpit)
        _prefix, marker, schedule_process = cockpit.partition(
            "id: continuityScheduleProc")
        self.assertTrue(marker)
        schedule_process, marker, _suffix = schedule_process.partition(
            "// `sia ready` is the only live memory-readiness predicate.")
        self.assertTrue(marker)
        self.assertIn('"/.local/bin/sia"', schedule_process)
        self.assertIn('"backup", "schedule"', schedule_process)

        for visible_copy in (
                "AUTOMATIC BACKUP · ON",
                "Every hour · no button needed",
                "Last start ",
                "Weekly deep restore check",
                "Last check start ",
                "never wakes this computer",
                "a missed run catches up after you return",
                "no automatic run is being claimed",
                "Make extra copy now is optional"):
            self.assertIn(visible_copy, cockpit)

        self.assertIn('"Make extra copy now"', cockpit)
        self.assertIn('"Extra copy"', cockpit)
        self.assertIn(
            "Optional extra copy with immediate deep repository verification; "
            "hourly backups continue automatically", cockpit)

        _prefix, marker, focus_body = cockpit.partition(
            "function focusContinuityPage() {")
        self.assertTrue(marker)
        focus_body, marker, _suffix = focus_body.partition(
            "function openContinuity(page) {")
        self.assertTrue(marker)
        self.assertIn("continuityCloseButton.forceActiveFocus()", focus_body)
        self.assertNotIn(
            "overviewBackupButton.forceActiveFocus()", focus_body)

    def test_security_contract_is_operator_visible(self):
        continuity = _read("docs/CONTINUITY.md")
        security = _read("SECURITY.md")
        changelog = _read("CHANGELOG.md")
        continuity_folded = " ".join(continuity.split())
        security_folded = " ".join(security.split())

        self.assertIn("authenticated restic repository", continuity)
        self.assertIn(
            "intended SIA capsule-signing public identity", continuity)
        self.assertIn("systemd's effective fragment paths", continuity)
        self.assertIn(
            "Before restic may materialize snapshot payload bytes", continuity)
        self.assertIn("one corpus generation", continuity)
        self.assertIn("green is the final durable write", continuity_folded)
        self.assertIn(
            "does not invent a healthy repository copy", continuity_folded)
        self.assertIn(
            "`latest` deliberately means the newest snapshot",
            continuity_folded)
        self.assertIn("That rebind does not promote", continuity)

        self.assertIn("Systemd is also an input boundary", security)
        self.assertIn(
            "strictly preflights the bounded metadata listing", security)
        self.assertIn("preventing a proof", security)
        self.assertIn("Green is written last", security_folded)
        self.assertIn("does not by itself", security)
        self.assertIn("This rebind cannot promote a snapshot", security)

        self.assertIn("Fail-closed continuity attestation", changelog)
        self.assertIn("cannot manufacture **RECOVERY READY**", changelog)
        self.assertIn("only a later repository check may promote", changelog)


if __name__ == "__main__":
    unittest.main()
