"""Release contract for continuity's fail-closed UI boundary."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "bin"))

import siabackup


def _read(relative):
    return (REPO / relative).read_text(encoding="utf-8")


class ContinuityUiContractTests(unittest.TestCase):
    def _model_validator_accepts(self, validator_name, payload, *arguments):
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
const arguments = JSON.parse(process.argv[4])
process.stdout.write(JSON.stringify(
  validator.apply(null, [payload].concat(arguments))))
'''
        result = subprocess.run(
            [node, "-e", script, str(REPO / "Model.js"), validator_name,
             json.dumps(payload, separators=(",", ":")),
             json.dumps(arguments, separators=(",", ":"))],
            cwd=REPO, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def _model_parser_accepts(self, raw):
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
try {
  context.strictContinuityJsonParse(process.argv[2])
  process.stdout.write("true")
} catch (_) {
  process.stdout.write("false")
}
'''
        result = subprocess.run(
            [node, "-e", script, str(REPO / "Model.js"), raw],
            cwd=REPO, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def _model_accepts(self, payload, receipt_authenticated=True):
        return self._model_validator_accepts(
            "validContinuityStatus", payload, receipt_authenticated)

    @staticmethod
    def _backend_accepts(payload):
        try:
            siabackup._validate_status(payload)
        except (TypeError, ValueError):
            return False
        return True

    def _schedule_model_accepts(self, payload):
        return self._model_validator_accepts(
            "validContinuitySchedule", payload)

    @staticmethod
    def _schedule_backend_accepts(payload):
        try:
            siabackup._validate_schedule_status(payload)
        except (TypeError, ValueError):
            return False
        return True

    def test_verified_state_requires_a_ready_identity_matching_copy(self):
        model = _read("Model.js")
        _prefix, marker, remainder = model.partition(
            "function validContinuityStatus(value, receiptAuthenticated) {")
        self.assertTrue(marker)
        validator, marker, _suffix = remainder.partition(
            "function continuityStateLabel(state) {")
        self.assertTrue(marker)

        self.assertIn('value.state !== "verified"', validator)
        self.assertIn(
            "continuityLatestReady(value.latest, receiptAuthenticated)",
            validator)

        _prefix, marker, readiness_remainder = model.partition(
            "function continuityLatestReady(value, receiptAuthenticated) {")
        self.assertTrue(marker)
        readiness_validator, marker, _suffix = readiness_remainder.partition(
            "function validContinuityPrepared(value) {")
        self.assertTrue(marker)
        self.assertIn("validContinuityLatest(value)", readiness_validator)
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
                "Model.validContinuityStatus(parsed, receiptAuthenticated)",
                _read(surface))
            self.assertIn(
                "Model.strictContinuityJsonParse(text)", _read(surface))
        self.assertIn(
            "Model.continuityLatestReady(", _read("Cockpit.qml"))
        self.assertIn(
            "root.continuityReceiptAuthenticated", _read("Cockpit.qml"))

        latest = {
            "snapshot_id": "abc123",
            "created_at": "2026-09-02T20:44:00Z",
            "verified": True,
            "readiness": "ready",
            "profile": "signed portable capsule",
            "identity_matches": True,
        }
        status = {
            "schema_version": 2,
            "state": "verified",
            "detail": "Verified recovery copy is available.",
            "repository_display": "External recovery repository",
            "latest": latest,
            "prepared": None,
            "operation": None,
            "updated_at": "2026-09-02T20:44:00Z",
        }
        self.assertTrue(self._model_accepts(status))
        self.assertTrue(self._backend_accepts(status))
        offset_status = {
            **status,
            "latest": {
                **latest,
                "created_at": "2026-09-02T12:42:33.191486601-04:00"},
        }
        self.assertTrue(self._model_accepts(offset_status))
        self.assertTrue(self._backend_accepts(offset_status))
        self.assertFalse(self._model_accepts({
            **status, "schema_version": 1}))
        self.assertFalse(self._backend_accepts({
            **status, "schema_version": 1}))
        self.assertFalse(self._model_accepts({
            **status, "latest": {**latest, "snapshot_id": ""}}))
        self.assertFalse(self._backend_accepts({
            **status, "latest": {**latest, "snapshot_id": ""}}))

        successful_restore = {
            **status,
            "state": "recovery-only",
            "latest": None,
            "operation": {
                "request_id": "a" * 32,
                "kind": "restore-apply",
                "prepared_id": "d" * 32,
                "phase": "verified",
                "ready": True,
                "sia_ledger_verified": True,
            },
        }
        self.assertTrue(self._model_accepts(successful_restore))
        self.assertTrue(self._backend_accepts(successful_restore))

        prepared = {
            "prepared_id": "d" * 32,
            "snapshot_id": "abc123",
            "created_at": "2026-09-02T20:44:00Z",
            "readiness": "ready",
            "profile": "signed portable capsule",
            "ledger_head": "f" * 64,
            "identity_matches": True,
        }
        prepared_status = {
            **status,
            "state": "prepared",
            "prepared": prepared,
            "operation": {
                "request_id": "a" * 32,
                "kind": "restore-prepare",
                "prepared_id": "d" * 32,
                "phase": "verified",
                "ready": False,
                "sia_ledger_verified": False,
            },
        }
        self.assertTrue(self._model_accepts(prepared_status))
        self.assertTrue(self._backend_accepts(prepared_status))
        invalid = {
            "top-level extra": {**status, "unexpected": True},
            "missing updated timestamp": {
                key: value for key, value in status.items()
                if key != "updated_at"},
            "invalid updated timestamp": {
                **status, "updated_at": "2026-09-02 20:44:00"},
            "detail control": {**status, "detail": "unsafe\n"},
            "latest extra": {
                **status, "latest": {**latest, "unexpected": True}},
            "latest identifier": {
                **status, "latest": {**latest, "snapshot_id": "ABC123"}},
            "latest identifier control": {
                **status,
                "latest": {**latest, "snapshot_id": "abc123\n"}},
            "latest identifier bound": {
                **status,
                "latest": {
                    **latest,
                    "snapshot_id": (
                        "a" * siabackup.STATUS_IDENTIFIER_MAX_CHARS + "a")}},
            "latest timestamp": {
                **status, "latest": {**latest, "created_at": "later"}},
            "latest noncanonical fraction": {
                **status,
                "latest": {
                    **latest,
                    "created_at": "2026-09-02T20:44:00.120Z"}},
            "latest noncanonical zero offset": {
                **status,
                "latest": {
                    **latest,
                    "created_at": "2026-09-02T20:44:00+00:00"}},
            "latest readiness": {
                **status, "latest": {**latest, "readiness": "maybe"}},
            "latest profile": {
                **status, "latest": {**latest, "profile": "daily"}},
            "prepared extra": {
                **prepared_status,
                "prepared": {**prepared, "unexpected": True}},
            "prepared identifier width": {
                **prepared_status,
                "prepared": {**prepared, "prepared_id": "def456"}},
            "prepared ledger head": {
                **prepared_status,
                "prepared": {**prepared, "ledger_head": "head"}},
            "prepared ledger head control": {
                **prepared_status,
                "prepared": {**prepared, "ledger_head": "f" * 64 + "\n"}},
            "operation extra": {
                **successful_restore,
                "operation": {
                    **successful_restore["operation"], "unexpected": True}},
            "operation kind": {
                **successful_restore,
                "operation": {
                    **successful_restore["operation"], "kind": "other"}},
            "operation request identifier bound": {
                **successful_restore,
                "operation": {
                    **successful_restore["operation"],
                    "request_id": (
                        "a" * siabackup.STATUS_IDENTIFIER_MAX_CHARS + "a")}},
            "operation request identifier width": {
                **successful_restore,
                "operation": {
                    **successful_restore["operation"],
                    "request_id": "abc123"}},
            "prepared operation mismatch": {
                **prepared_status,
                "operation": {
                    **prepared_status["operation"],
                    "prepared_id": "abc999"}},
        }
        for label, document in invalid.items():
            with self.subTest(label=label):
                self.assertFalse(self._model_accepts(document))
                self.assertFalse(self._backend_accepts(document))

    def test_verified_latest_requires_authenticated_backend_provenance(self):
        latest = {
            "snapshot_id": "abc123",
            "created_at": "2026-09-02T20:44:00Z",
            "verified": True,
            "readiness": "ready",
            "profile": "signed portable capsule",
            "identity_matches": True,
        }
        status = {
            "schema_version": 2,
            "state": "verified",
            "detail": "Verified recovery copy is available.",
            "repository_display": "External recovery repository",
            "latest": latest,
            "prepared": None,
            "operation": None,
            "updated_at": "2026-09-02T20:44:00Z",
        }
        checking = {
            **status,
            "state": "checking",
            "detail": "Repository verification is running.",
            "operation": {
                "request_id": "c" * 32,
                "kind": "backup-check",
                "prepared_id": "",
                "phase": "running",
                "ready": False,
                "sia_ledger_verified": False,
            },
        }
        for document in (status, checking):
            with self.subTest(state=document["state"]):
                self.assertFalse(self._model_validator_accepts(
                    "validContinuityStatus", document))
                self.assertFalse(self._model_accepts(
                    document, receipt_authenticated=False))
                self.assertTrue(self._model_accepts(
                    document, receipt_authenticated=True))
        self.assertFalse(self._model_validator_accepts(
            "continuityLatestReady", latest, False))
        self.assertTrue(self._model_validator_accepts(
            "continuityLatestReady", latest, True))
        self.assertEqual(self._model_validator_accepts(
            "continuityBarMark", status, False), "?")
        self.assertEqual(self._model_validator_accepts(
            "continuityBarMark", status, True), "")

        for surface in ("Cockpit.qml", "Panel.qml"):
            source = _read(surface)
            self.assertIn("id: continuityStatusProc", source)
            self.assertIn('"backup", "status"', source)
            self.assertIn("receiptAuthenticated === true", source)
            file_view = source.split("id: continuityFile", 1)[1].split(
                "\n  }", 1)[0]
            self.assertIn("continuityStatusProc.refresh()", file_view)
            self.assertNotIn("root.applyContinuity(text())", file_view)

    def test_continuity_parser_preserves_the_integer_schema_boundary(self):
        self.assertTrue(self._model_parser_accepts(
            '{"schema_version":2}'))
        self.assertFalse(self._model_parser_accepts(
            '{"schema_version":2.0}'))
        self.assertFalse(self._model_parser_accepts(
            '{"schema_version":2,"schema_version":2}'))

    def test_status_state_operation_pairs_match_producer_semantics(self):
        latest = {
            "snapshot_id": "abc123",
            "created_at": "2026-09-02T20:44:00Z",
            "verified": True,
            "readiness": "ready",
            "profile": "signed portable capsule",
            "identity_matches": True,
        }
        prepared = {
            "prepared_id": "d" * 32,
            "snapshot_id": "abc123",
            "created_at": "2026-09-02T20:44:00Z",
            "readiness": "ready",
            "profile": "signed portable capsule",
            "ledger_head": "f" * 64,
            "identity_matches": True,
        }
        base = {
            "schema_version": 2,
            "state": "recovery-only",
            "detail": "Continuity status is available.",
            "repository_display": "External recovery repository",
            "latest": latest,
            "prepared": None,
            "operation": None,
            "updated_at": "2026-09-02T20:44:00Z",
        }

        def operation(kind, phase, *, ready=False,
                      ledger_verified=False):
            prepared_id = "d" * 32 if kind == "restore-apply" \
                or (kind == "restore-prepare" and phase == "verified") \
                else ""
            return {
                "request_id": "a" * 32,
                "kind": kind,
                "prepared_id": prepared_id,
                "phase": phase,
                "ready": ready,
                "sia_ledger_verified": ledger_verified,
            }

        producer_pairs = [
            {**base, "state": "unconfigured", "latest": None,
             "repository_display": ""},
            {**base, "state": "verified"},
        ]
        for kind in ("backup-setup", "backup-connect", "backup-upload",
                     "backup-check", "restore-prepare"):
            producer_pairs.append({
                **base, "state": "queued",
                "operation": operation(kind, "accepted")})
        for kind in ("backup-setup", "backup-connect"):
            producer_pairs.append({
                **base, "state": "queued",
                "operation": operation(kind, "running")})
        producer_pairs.extend((
            {**base, "state": "capturing",
             "operation": operation("backup-upload", "running")},
            {**base, "state": "uploading",
             "operation": operation("backup-upload", "running")},
            {**base, "state": "checking",
             "operation": operation("backup-check", "running")},
            {**base, "state": "preparing",
             "operation": operation("restore-prepare", "running")},
            {**base, "state": "prepared", "prepared": prepared,
             "operation": operation("restore-prepare", "verified")},
            {**base, "state": "restoring",
             "operation": operation("restore-apply", "accepted")},
            {**base, "state": "restoring",
             "operation": operation("restore-apply", "running")},
            {**base, "state": "restoring",
             "operation": operation(
                 "restore-apply", "running", ready=True,
                 ledger_verified=True)},
            {**base, "state": "restoring",
             "operation": operation("restore-recover", "running")},
        ))
        terminal_kinds = (
            "backup-setup", "backup-connect", "backup-upload",
            "backup-check", "restore-apply", "restore-recover")
        for kind in terminal_kinds:
            restore = kind in {"restore-apply", "restore-recover"}
            producer_pairs.append({
                **base, "state": "verified",
                "operation": operation(
                    kind, "verified", ready=restore,
                    ledger_verified=restore)})
        for kind in (
                "backup-setup", "backup-connect", "backup-upload",
                "backup-check", "restore-prepare", "restore-apply",
                "restore-recover"):
            producer_pairs.extend((
                {**base, "state": "failed",
                 "operation": operation(kind, "failed")},
                {**base, "state": "blocked",
                 "operation": operation(kind, "blocked")},
            ))
        for index, document in enumerate(producer_pairs):
            with self.subTest(producer_pair=index):
                self.assertTrue(self._backend_accepts(document))
                self.assertTrue(self._model_accepts(document))

        invalid_pairs = {
            "green active": {
                **base, "state": "verified",
                "operation": operation("backup-upload", "running")},
            "green failed": {
                **base, "operation": operation("backup-check", "failed")},
            "unconfigured accepted": {
                **base, "state": "unconfigured", "latest": None,
                "repository_display": "",
                "operation": operation("backup-setup", "accepted")},
            "queued terminal": {
                **base, "state": "queued",
                "operation": operation("backup-upload", "verified")},
            "capturing wrong kind": {
                **base, "state": "capturing",
                "operation": operation("backup-check", "running")},
            "uploading accepted": {
                **base, "state": "uploading",
                "operation": operation("backup-upload", "accepted")},
            "checking failed": {
                **base, "state": "checking",
                "operation": operation("backup-check", "failed")},
            "preparing wrong kind": {
                **base, "state": "preparing",
                "operation": operation("restore-apply", "running")},
            "restoring terminal": {
                **base, "state": "restoring",
                "operation": operation(
                    "restore-apply", "verified", ready=True,
                    ledger_verified=True)},
            "failed active": {
                **base, "state": "failed",
                "operation": operation("backup-upload", "running")},
            "blocked successful": {
                **base, "state": "blocked",
                "operation": operation("backup-check", "verified")},
            "accepted restore proof": {
                **base, "state": "restoring",
                "operation": operation(
                    "restore-apply", "accepted", ready=True,
                    ledger_verified=True)},
            "unconfigured ready latest": {
                **base, "state": "unconfigured",
                "repository_display": ""},
            "verified empty repository": {
                **base, "state": "verified",
                "repository_display": ""},
            "unconfigured external repository": {
                **base, "state": "unconfigured", "latest": None},
        }
        for label, document in invalid_pairs.items():
            with self.subTest(invalid_pair=label):
                self.assertFalse(self._backend_accepts(document))
                self.assertFalse(self._model_accepts(document))

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
        self.assertTrue(self._schedule_backend_accepts(schedule))

        invalid = {
            "schema version": {**schedule, "schema_version": 2},
            "top-level extra": {**schedule, "unexpected": True},
            "upload cadence": {
                **schedule, "upload": {**upload, "cadence": "weekly"}},
            "upload extra": {
                **schedule, "upload": {**upload, "unexpected": True}},
            "verification cadence": {
                **schedule,
                "verification": {**verification, "cadence": "hourly"}},
            "verification missing field": {
                **schedule,
                "verification": {
                    key: value for key, value in verification.items()
                    if key != "wake_system"}},
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
                self.assertFalse(self._schedule_backend_accepts(candidate))

        self.assertTrue(self._model_parser_accepts(
            '{"schema_version":1}'))
        self.assertFalse(self._model_parser_accepts(
            '{"schema_version":1.0}'))
        schedule_loader = _read("Cockpit.qml").split(
            "function applyContinuitySchedule(text) {", 1)[1].split(
                "function applySetupPresence(text) {", 1)[0]
        self.assertIn("Model.strictContinuityJsonParse(text)", schedule_loader)

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
        self.assertIn(
            "`latest` is the current repository-protection row",
            continuity_folded)
        cockpit = _read("Cockpit.qml")
        _prefix, marker, latest_text = cockpit.partition(
            "function continuityLatestText() {")
        self.assertTrue(marker)
        latest_text, marker, _suffix = latest_text.partition(
            "function continuityDetailText() {")
        self.assertTrue(marker)
        self.assertNotIn("newest", latest_text.casefold())
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
