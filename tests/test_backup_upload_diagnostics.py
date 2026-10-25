"""Upload failure phase and non-disclosure controls; no network or live data."""
import contextlib
import json
import os
import subprocess
import unittest
from unittest import mock

from tests import test_continuity as continuity_tests

siabackup = continuity_tests.siabackup


class UploadDiagnostics(unittest.TestCase):
    def setUp(self):
        self.fixture = continuity_tests.ContinuityTransport(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.request = {"id": "a" * 32, "action": "upload",
                        "args": {"scheduled": False}}
        self.path = os.path.join(siabackup.CAPSULES_DIR, ".capsule-" + "a" * 32)
        self.verified = {"capsule_id": "capsule", "manifest_sha256": "digest",
                         "classification": "ready", "public_key": "b" * 64}
        self.failure = ValueError("SYNTHETIC_PRIVATE_CREDENTIAL")

    @contextlib.contextmanager
    def scenario(self, phase=None, error=None):
        failure = self.failure if error is None else error
        real_publish, real_now = siabackup._publish_status, siabackup._now

        def fail_at(point):
            if phase == point:
                raise failure

        def freeze(path):
            os.mkdir(path)
            fail_at("capsule-capture")
            return {**self.verified, "path": path}

        def validate(path, _frozen):
            fail_at("capsule-validation")
            return path, self.verified

        def publish(**changes):
            if changes["state"] == "uploading":
                fail_at("upload-status-publication")
            return real_publish(**changes)

        def restic(arguments, **_kwargs):
            point = "repository-upload" if arguments[0] == "backup" else "repository-check"
            fail_at(point)
            if phase == "upload-response":
                return "invalid SYNTHETIC_PRIVATE_CREDENTIAL"
            return json.dumps({"message_type": "summary", "snapshot_id": "abc123"})

        def verify(*_args, **_kwargs):
            fail_at("offpath-verification")
            return {} if phase == "result-construction" else self.verified

        with mock.patch.object(siabackup.siacapsule, "freeze", side_effect=freeze), \
                mock.patch.object(siabackup, "_validate_completed_capsule", side_effect=validate), \
                mock.patch.object(siabackup, "_publish_status", side_effect=publish), \
                mock.patch.object(siabackup, "_run_restic", side_effect=restic), \
                mock.patch.object(siabackup, "_verify_snapshot_offpath", side_effect=verify), \
                mock.patch.object(siabackup, "_now", side_effect=real_now):
            yield

    def test_each_failure_phase_is_retained_without_success_or_secret(self):
        cases = (
            ("capsule-capture", "not-attempted"),
            ("capsule-validation", "not-attempted"),
            ("upload-status-publication", "not-attempted"),
            ("repository-upload", "outcome-unknown"),
            ("upload-response", "outcome-unknown"),
            ("repository-check", "snapshot-reported"),
            ("offpath-verification", "snapshot-reported"),
            ("result-construction", "snapshot-reported"),
        )
        for phase, remote in cases:
            with self.subTest(phase=phase), self.scenario(phase):
                self.assertEqual(siabackup._run_request_locked(self.request), 1)
                status = siabackup.read_status()
                self.assertEqual(status["state"], "failed")
                self.assertIn("Upload phase: " + phase, status["detail"])
                self.assertIn("remote: " + remote, status["detail"])
                self.assertNotIn("SYNTHETIC_PRIVATE_CREDENTIAL", json.dumps(status))
                self.assertIsNone(status["latest"])
                self.assertEqual(status["operation"]["request_id"], self.request["id"])
                self.assertFalse(status["operation"]["ready"])
                self.assertFalse(status["operation"]["sia_ledger_verified"])
                self.assertFalse(os.path.lexists(self.path))

    def test_primary_and_cleanup_errors_are_both_retained(self):
        cleanup = OSError("SECOND_PRIVATE_CREDENTIAL")
        with self.scenario("repository-upload"), mock.patch.object(
                siabackup, "_retire_private_tree", side_effect=cleanup) as retire:
            with self.assertRaises(siabackup._UploadFailure) as caught:
                siabackup._perform_upload(self.request["args"], self.request["id"])
        self.assertIs(caught.exception.primary, self.failure)
        self.assertIs(caught.exception.__cause__, self.failure)
        self.assertIs(caught.exception.cleanup, cleanup)
        self.assertEqual(retire.call_count, 1)
        clause = siabackup._named_failure_clause(caught.exception)
        self.assertIn("cleanup: failed", clause)
        self.assertNotIn("PRIVATE_CREDENTIAL", clause)

    def test_cleanup_failure_after_success_retains_reported_outcome(self):
        with self.scenario(), mock.patch.object(
                siabackup, "_retire_private_tree", side_effect=self.failure):
            with self.assertRaises(siabackup._UploadFailure) as caught:
                siabackup._perform_upload(self.request["args"], self.request["id"])
        self.assertEqual(caught.exception.phase, "capsule-cleanup")
        self.assertEqual(caught.exception.remote, "snapshot-reported")
        self.assertIs(caught.exception.primary, self.failure)

    def test_blocked_upload_preserves_blocked_status_and_uncertainty(self):
        with self.scenario("repository-upload", siabackup.BlockedError("private")):
            self.assertEqual(siabackup._run_request_locked(self.request), 3)
        status = siabackup.read_status()
        self.assertEqual(status["state"], "blocked")
        self.assertIn("remote: outcome-unknown", status["detail"])
        self.assertIsNone(status["latest"])

    def test_fatal_failure_propagates_original_after_cleanup(self):
        fatal = KeyboardInterrupt("private")
        with self.scenario("repository-upload", fatal):
            with self.assertRaises(KeyboardInterrupt) as caught:
                siabackup._perform_upload(self.request["args"], self.request["id"])
        self.assertIs(caught.exception, fatal)
        self.assertFalse(os.path.lexists(self.path))

    def test_diagnostics_never_stringify_primary_or_cleanup(self):
        class HostileError(Exception):
            def __str__(self):
                raise AssertionError("error text must not be evaluated")

        attempt = siabackup._UploadAttempt()
        attempt.phase, attempt.remote = "private", "private"
        attempt.cleanup = HostileError()
        failure = siabackup._UploadFailure(attempt, HostileError())
        clause = siabackup._named_failure_clause(failure)
        self.assertEqual(clause, " Upload phase: unknown; remote: outcome-unknown; "
                         "error: exception; cleanup: failed.")
        self.assertLess(len(clause), siabackup.STATUS_TEXT_MAX_CHARS)

    def test_exit_classification_is_bounded_and_keeps_generic_message(self):
        attempt = siabackup._UploadAttempt()
        for code, expected in ((3, "restic-exit-3"), (-9, "restic-exit--9"),
                               (True, "restic-status-unavailable"),
                               ("private", "restic-status-unavailable"),
                               (256, "restic-status-unavailable")):
            with self.subTest(code=code):
                primary = siabackup._ResticExitFailure(code)
                self.assertEqual(str(primary), "restic operation was refused")
                clause = siabackup._named_failure_clause(siabackup._UploadFailure(attempt, primary))
                self.assertIn("error: " + expected + ";", clause)
                self.assertNotIn("private", clause)
        timeout = subprocess.TimeoutExpired(["private"], 1, stderr="private")
        clause = siabackup._named_failure_clause(siabackup._UploadFailure(attempt, timeout))
        self.assertIn("error: process-timeout;", clause)
        self.assertNotIn("private", clause)

    def test_scheduled_success_still_does_not_claim_verification(self):
        with self.scenario(), mock.patch.object(siabackup, "_verify_snapshot_offpath") as verify:
            latest = siabackup._perform_upload({"scheduled": True}, self.request["id"])
        verify.assert_not_called()
        self.assertFalse(latest["verified"])
        self.assertEqual(latest["snapshot_id"], "abc123")
        self.assertFalse(os.path.lexists(self.path))

    def test_named_refusals_survive_actual_upload_wrapper_without_suffixes(self):
        cases = list(siabackup._NAMED_FAILURE_PREFIXES) + [
            ("capsule source tree exceeds its record bound", "capsule-record-bound")]
        for message, code in cases:
            with self.subTest(code=code), self.scenario("capsule-capture", ValueError(message)):
                self.assertEqual(siabackup._run_request_locked(self.request), 1)
                self.assertIn(" Reason: " + code + ".", siabackup.read_status()["detail"])
        error = ValueError("capsule output already exists SYNTHETIC_PRIVATE_CREDENTIAL")
        with self.scenario("capsule-capture", error):
            self.assertEqual(siabackup._run_request_locked(self.request), 1)
        detail = siabackup.read_status()["detail"]
        self.assertIn("Reason: capsule-output-exists.", detail)
        self.assertNotIn("SYNTHETIC_PRIVATE_CREDENTIAL", detail)

    def test_exception_metaclass_equality_is_never_called(self):
        calls = []

        class HostileMeta(type):
            __hash__ = type.__hash__

            def __eq__(cls, other):
                calls.append(other)
                raise AssertionError("type equality must not run")

        class HostileError(Exception, metaclass=HostileMeta):
            pass

        with self.scenario("repository-upload", HostileError("private")):
            self.assertEqual(siabackup._run_request_locked(self.request), 1)
        self.assertEqual(calls, [])
        self.assertIn("error: exception;", siabackup.read_status()["detail"])

    def test_exception_class_property_is_not_a_classification_authority(self):
        class HostileError(Exception):
            @property
            def __class__(self):
                raise AssertionError("class property must not run")

            def __str__(self):
                raise AssertionError("text hook must not run")

        with self.scenario("repository-upload", HostileError("private")):
            self.assertEqual(siabackup._run_request_locked(self.request), 1)
        self.assertIn("error: exception;", siabackup.read_status()["detail"])

    def test_actual_restic_exit_path_retains_status_without_provider_output(self):
        executable = os.path.join(self.fixture.temp.name, "restic-fixture")
        with open(executable, "xb") as stream:
            stream.write(b"fixture only, never executed\n")
        os.chmod(executable, 0o700)
        result = subprocess.CompletedProcess([], 17, stdout="PRIVATE", stderr="PRIVATE")
        with mock.patch.object(siabackup.sialib, "_run_bounded_text_process",
                               return_value=result) as process:
            with self.assertRaises(siabackup._ResticExitFailure) as caught:
                siabackup._execute_restic(["backup"], config={}, key_path="private",
                                         cwd=None, restic_path=executable, environment={})
        self.assertEqual(process.call_count, 1)
        self.assertEqual(caught.exception.returncode, 17)
        self.assertEqual(str(caught.exception), "restic operation was refused")
        failure = siabackup._UploadFailure(siabackup._UploadAttempt(), caught.exception)
        self.assertIn("error: restic-exit-17;", siabackup._named_failure_clause(failure))
        self.assertNotIn("PRIVATE", siabackup._named_failure_clause(failure))


if __name__ == "__main__":
    unittest.main()
