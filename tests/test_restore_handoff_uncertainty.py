"""Execute actual cockpit decisions with bounded Node fixtures, no restore."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest

from tests.test_cockpit_boundary_horizon import _qml_function, _scan_block


REPO = Path(__file__).resolve().parents[1]
RUNNER = r'''
const fs = require('fs'), vm = require('vm');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const context = vm.createContext({});
vm.runInContext(payload.model + '\n' + payload.methods + '\n' + payload.settle
                + '\n' + payload.fixture, context, {timeout: 1000});
context.options = payload.options;
process.stdout.write(JSON.stringify(vm.runInContext(
  'scenario(options)', context, {timeout: 1000})));
'''
FIXTURE = r'''
var Model = globalThis;
var preparedId = 'a'.repeat(32), snapshotId = 'b'.repeat(64);
var ledgerHead = 'c'.repeat(64), requestId = 'd'.repeat(32);
var now = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
function preparedStatus(id, stamp) {
  return {schema_version: 2, state: 'prepared', detail: 'Prepared',
    repository_display: 'External recovery repository', latest: null,
    updated_at: stamp,
    prepared: {prepared_id: id, snapshot_id: snapshotId, created_at: stamp,
      readiness: 'ready', profile: 'signed portable capsule',
      ledger_head: ledgerHead, identity_matches: true},
    operation: {request_id: requestId, kind: 'restore-prepare',
      prepared_id: id, phase: 'verified', ready: false,
      sia_ledger_verified: false}};
}
var root = {
  preparedRestore: preparedRestore, clearRestoreCeremony: clearRestoreCeremony,
  isPlainRecord: isPlainRecord, validRestoreAcceptance: validRestoreAcceptance,
  matchingRestoreOperation: matchingRestoreOperation,
  rejectContinuityStatus: rejectContinuityStatus,
  continuityReceiptAuthenticated: true, continuity: preparedStatus(preparedId, now),
  get currentContinuity() { return this.continuity; },
  restoreVerificationPending: false, restoreCorrelationLost: false,
  restoreRequestId: '', restoreExpectedPreparedId: preparedId,
  restoreConfirmOpen: false, continuitySheetOpen: false, opened: false,
  continuityActionOk: false, continuityActionMsg: ''
};
var reloads = 0, continuityFile = {reload: function() { reloads++; }};
var launchFailed = false, exited = true, outDone = true, errDone = true;
var working = true, outOverflow = false, errOverflow = false;
var outText = '', errText = '', exitCode = 1;
var awaitRestoreVerification = true, restorePreparedId = preparedId;
var operationLabel = 'Restore SIA', stdinPayload = 'private ceremony';
function fillCeremony() {
  root.restorePhraseInput = 'RESTORE';
  root.restorePreparedSnapshotInput = snapshotId;
  root.restoreLedgerHeadInput = ledgerHead;
  root.restoreReceiptReadoptAck = true;
  root.restoreIdentityKeyPathInput = '';
}
function observe() {
  return {ok: root.continuityActionOk, pending: root.restoreVerificationPending,
    lost: root.restoreCorrelationLost, request: root.restoreRequestId,
    prepared: root.restoreExpectedPreparedId, ready: restoreCeremonyReady(),
    message: root.continuityActionMsg, reloads: reloads, working: working,
    payload: stdinPayload};
}
function scenario(options) {
  fillCeremony();
  if (!Model.validContinuityStatus(root.currentContinuity, true))
    throw new Error('invalid prepared fixture');
  exitCode = options.code;
  awaitRestoreVerification = options.restore !== false;
  outOverflow = options.overflow === true;
  if (options.receipt === 'valid')
    outText = JSON.stringify({schema_version: 1, accepted: true,
      request_id: requestId, operation: 'restore-apply', prepared_id: preparedId});
  else if (options.receipt === 'malformed') outText = '{broken';
  errText = options.error || '';
  settle();
  const afterExit = observe();
  if (options.status) {
    var next = preparedStatus(options.status === 'same' ? preparedId : 'e'.repeat(32), now);
    if (options.stale) next.updated_at = '2000-01-01T00:00:00Z';
    if (options.mismatch) next.operation.prepared_id = 'f'.repeat(32);
    applyContinuity(JSON.stringify(next), options.authenticated !== false);
    fillCeremony();
  }
  return {afterExit: afterExit, afterStatus: observe()};
}
'''


class RestoreHandoffUncertainty(unittest.TestCase):
    def setUp(self):
        self.node = shutil.which("node")
        self.assertIsNotNone(self.node, "Node is required for this executable UI check")
        source = (REPO / "Cockpit.qml").read_text()
        controller = source[source.index("    id: continuityProc\n"):]
        start = controller.index("    function settle() {")
        opening = controller.index("{", start)
        self.settle = controller[start:_scan_block(controller, opening) + 1]
        self.methods = "\n".join(_qml_function(source, name) for name in (
            "preparedRestore", "clearRestoreCeremony", "restoreCeremonyReady",
            "validRestoreAcceptance", "matchingRestoreOperation", "isPlainRecord",
            "rejectContinuityStatus", "applyContinuity"))
        self.model = (REPO / "Model.js").read_text().replace(".pragma library", "")

    def run_scenario(self, **options):
        payload = dict(model=self.model, methods=self.methods, settle=self.settle,
                       fixture=FIXTURE, options=options)
        result = subprocess.run(
            [self.node, "-e", RUNNER], input=json.dumps(payload), text=True,
            capture_output=True, timeout=5, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def assert_uncertain(self, state):
        self.assertFalse(state["ok"])
        self.assertFalse(state["pending"])
        self.assertTrue(state["lost"])
        self.assertEqual(state["request"], "")
        self.assertEqual(state["prepared"], "a" * 32)
        self.assertFalse(state["ready"])

    def test_nonzero_restore_exit_never_authorizes_a_retry(self):
        for code in (1, 124, -15):
            for receipt in ("absent", "valid", "malformed"):
                with self.subTest(code=code, receipt=receipt):
                    result = self.run_scenario(code=code, receipt=receipt)
                    self.assert_uncertain(result["afterExit"])
                    self.assertEqual(result["afterExit"]["reloads"], 1)
                    self.assertEqual(result["afterExit"]["payload"], "")
                    self.assertFalse(result["afterExit"]["working"])

    def test_nonzero_overflow_still_preserves_uncertainty(self):
        self.assert_uncertain(self.run_scenario(
            code=1, receipt="valid", overflow=True)["afterExit"])

    def test_old_prepared_reload_cannot_erase_unknown_handoff(self):
        for code in (0, 1):
            with self.subTest(code=code):
                result = self.run_scenario(code=code, status="same")
                self.assert_uncertain(result["afterExit"])
                self.assert_uncertain(result["afterStatus"])

    def test_new_authenticated_preparation_allows_fresh_ceremony(self):
        result = self.run_scenario(code=1, status="new")
        self.assert_uncertain(result["afterExit"])
        fresh = result["afterStatus"]
        self.assertFalse(fresh["lost"])
        self.assertFalse(fresh["pending"])
        self.assertFalse(fresh["ok"])
        self.assertEqual(fresh["prepared"], "")
        self.assertEqual(fresh["request"], "")
        self.assertTrue(fresh["ready"])

    def test_invalid_or_stale_new_status_cannot_clear_unknown_handoff(self):
        for options in ({"stale": True}, {"authenticated": False}, {"mismatch": True}):
            with self.subTest(options=options):
                self.assert_uncertain(self.run_scenario(
                    code=1, status="new", **options)["afterStatus"])

    def test_success_with_valid_receipt_waits_for_exact_verification(self):
        state = self.run_scenario(code=0, receipt="valid")["afterExit"]
        self.assertFalse(state["ok"])
        self.assertTrue(state["pending"])
        self.assertFalse(state["lost"])
        self.assertEqual(state["request"], "d" * 32)
        self.assertEqual(state["prepared"], "a" * 32)
        self.assertFalse(state["ready"])

    def test_success_without_receipt_remains_uncertain(self):
        self.assert_uncertain(self.run_scenario(code=0)["afterExit"])

    def test_non_restore_result_keeps_existing_success_contract(self):
        for code in (0, 1):
            with self.subTest(code=code):
                state = self.run_scenario(code=code, restore=False)["afterExit"]
                self.assertEqual(state["ok"], code == 0)
                self.assertFalse(state["pending"])
                self.assertFalse(state["lost"])


if __name__ == "__main__":
    unittest.main()
