#!/usr/bin/env python3
"""Focused contracts for the capsule-only recovery-repository adapter."""

import contextlib
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "bin"))

import siabackup


class ContinuityTransport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sia-continuity-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = os.path.join(self.temp.name, "state")
        self.config = os.path.join(self.temp.name, "config", "continuity.json")
        paths = {
            "ROOT": self.root,
            "CONFIG_PATH": self.config,
            "KEY_PATH": os.path.join(self.root, "repository.key"),
            "STATUS_PATH": os.path.join(self.root, "status.json"),
            "SUPERVISOR_PATH": os.path.join(
                self.root, "restore-supervisor.json"),
            "REQUESTS_DIR": os.path.join(self.root, "requests"),
            "CAPSULES_DIR": os.path.join(self.root, "capsules"),
            "PREPARED_DIR": os.path.join(self.root, "prepared"),
            "ROLLBACK_DIR": os.path.join(self.root, "rollback"),
            "CHECKS_DIR": os.path.join(self.root, "checks"),
            "VERIFICATIONS_DIR": os.path.join(
                self.root, "verifications"),
            "REQUEST_LOCK": os.path.join(self.root, "request.lock"),
            "WORKER_LOCK": os.path.join(self.root, "worker.lock"),
        }
        for name, value in paths.items():
            patcher = mock.patch.object(siabackup, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.public_key = "a" * 64
        public_patcher = mock.patch.object(
            siabackup, "_live_brain_public_key",
            return_value=self.public_key)
        public_patcher.start()
        self.addCleanup(public_patcher.stop)
        siabackup._ensure_layout()

    @staticmethod
    def _runner(_command):
        return subprocess.CompletedProcess([], 0, stdout="", stderr="")

    def _configure(self):
        config = {
            "schema": siabackup.CONFIG_SCHEMA,
            "repository": os.path.join(self.temp.name, "repository"),
            "environment_file": None,
            "repository_id": "b" * 64,
            "brain_public_key": self.public_key,
            "created_at": "test-time",
        }
        siabackup._write_exclusive(
            siabackup.CONFIG_PATH, siabackup._canonical_bytes(config))
        siabackup._write_exclusive(siabackup.KEY_PATH, b"recovery-key\n")
        return config

    def _apply_args(self, *, prepared_id="def456", snapshot_id="abc123",
                    restored_public_key=None):
        return {
            "prepared_id": prepared_id,
            "snapshot_id": snapshot_id,
            "capsule_id": "a" * 32,
            "manifest_sha256": "b" * 64,
            "confirmation": {
                "schema_version": siabackup.CONFIRMATION_SCHEMA_VERSION,
                "phrase": "RESTORE",
                "snapshot_id": snapshot_id,
                "ledger_head": "target-head",
                "corpus_receipt_re_adopt": True,
            },
            "identity_key_file": None,
            "repository": os.path.join(self.temp.name, "repository"),
            "environment_file": "",
            "repository_id": "b" * 64,
            "configured_at": "test-time",
            "target_public_key": self.public_key,
            "restored_public_key": (
                restored_public_key or self.public_key),
        }

    def _apply_request_and_debt(self, *, phase="restart-attested",
                                write_request=True):
        runtime = os.path.join(REPO, "bin", "sia")
        runtime_info = os.lstat(runtime)
        request = {
            "schema": siabackup.REQUEST_SCHEMA,
            "id": "abc123", "created_at": "test-time",
            "action": "apply",
            "args": self._apply_args(),
        }
        if write_request:
            siabackup._write_exclusive(
                siabackup._request_path(request["id"]),
                siabackup._canonical_bytes(request))
        debt = {
            "schema": siabackup.SUPERVISOR_SCHEMA,
            "kind": "restore-apply",
            "request_path": siabackup._request_path(request["id"]),
            "request_id": request["id"],
            "prepared_id": request["args"]["prepared_id"],
            "snapshot_id": request["args"]["snapshot_id"],
            "capsule_id": request["args"]["capsule_id"],
            "manifest_sha256": request["args"]["manifest_sha256"],
            "phase": phase,
            "child_code": "0",
            "restart_pid": ("123" if phase == "restart-attested"
                            else "pending"),
            "runtime_path": runtime,
            "runtime_device": str(runtime_info.st_dev),
            "runtime_inode": str(runtime_info.st_ino),
            "repository": os.path.join(self.temp.name, "repository"),
            "environment_file": "",
            "repository_id": "b" * 64,
            "configured_at": "test-time",
            "target_public_key": self.public_key,
            "restored_public_key": self.public_key,
        }
        siabackup._write_exclusive(
            siabackup.SUPERVISOR_PATH,
            siabackup._canonical_bytes(debt))
        return request, debt

    def _healthy_latest(self, snapshot_id="abc123"):
        return {
            "snapshot_id": snapshot_id,
            "created_at": "test-time",
            "verified": True,
            "readiness": "ready",
            "profile": siabackup.PROFILE,
            "identity_matches": True,
        }

    @staticmethod
    def _repository_config_output():
        return json.dumps({"id": "b" * 64}) + "\n"

    def test_default_status_is_not_a_protection_claim(self):
        status = siabackup.read_status()
        self.assertEqual(status["state"], "unconfigured")
        self.assertIsNone(status["latest"])
        self.assertNotIn("protected", status["detail"].casefold())

    def test_offline_outputs_are_refused_inside_live_sia_roots(self):
        with self.assertRaisesRegex(ValueError, "outside SIA"):
            siabackup._protected_output(
                os.path.join(siabackup.sialib.SHARE, "identity.key"),
                "identity-key output")

    def test_backend_credentials_cannot_enter_a_portable_root(self):
        with self.assertRaisesRegex(ValueError, "portable roots"):
            siabackup._validate_environment_file(os.path.join(
                siabackup.sialib.STATE, "backend.env"))

    def test_path_bearing_backend_secret_cannot_enter_config_capsule(self):
        authority = os.path.join(self.temp.name, "portable-config")
        os.mkdir(authority, 0o700)
        secret = os.path.join(authority, "rclone.conf")
        siabackup._write_exclusive(secret, b"backend-secret\n")
        environment = os.path.join(self.temp.name, "repository.env")
        siabackup._write_exclusive(
            environment, ("RCLONE_CONFIG=" + secret + "\n").encode())
        with mock.patch.object(
                siabackup.siacapsule, "CONFIG_ROOT", authority), \
                self.assertRaisesRegex(ValueError, "portable authority"):
            siabackup._validate_environment_file(environment)

    def test_local_repository_cannot_contain_recovery_credentials(self):
        repository = os.path.join(self.temp.name, "repository")
        os.mkdir(repository, 0o700)
        recovery = os.path.join(repository, "repository.key")
        siabackup._write_exclusive(recovery, b"recovery-key\n")
        with self.assertRaisesRegex(ValueError, "outside the local"):
            siabackup._reject_local_repository_secrets(
                repository, [recovery], None)

    def test_top_level_spool_listing_is_bounded_before_reconciliation(self):
        for name in ("first", "second"):
            siabackup._write_exclusive(
                os.path.join(siabackup.REQUESTS_DIR, name), b"{}\n")
        with mock.patch.object(siabackup, "MAX_SPOOL_ENTRIES", 1), \
                self.assertRaisesRegex(ValueError, "entry boundary"):
            siabackup._bounded_private_names(
                siabackup.REQUESTS_DIR, "continuity request spool")
        self.assertEqual(
            set(os.listdir(siabackup.REQUESTS_DIR)), {"first", "second"})

    def test_retirement_preflights_entire_untrusted_tree(self):
        tree = os.path.join(siabackup.CAPSULES_DIR, ".capsule-hostile")
        os.mkdir(tree, 0o700)
        safe = os.path.join(tree, "a-safe")
        siabackup._write_exclusive(safe, b"keep\n")
        link = os.path.join(tree, "z-link")
        os.symlink(safe, link)
        with self.assertRaisesRegex(ValueError, "unsafe file"):
            siabackup._retire_private_tree(tree, siabackup.CAPSULES_DIR)
        self.assertTrue(os.path.isfile(safe))
        self.assertTrue(os.path.islink(link))

    def test_restore_child_never_publishes_green_before_restart(self):
        request = {
            "schema": siabackup.REQUEST_SCHEMA,
            "id": "abc123", "created_at": "test-time",
            "action": "apply", "args": {"prepared_id": "def456"},
        }
        with mock.patch.object(
                siabackup, "_perform_apply",
                return_value={"ready": True,
                              "sia_ledger_verified": True}):
            self.assertEqual(
                siabackup._run_request_locked(request, capability={}), 0)
        status = siabackup.read_status()
        self.assertEqual(status["state"], "restoring")
        self.assertEqual(status["operation"]["phase"], "running")
        self.assertTrue(status["operation"]["ready"])
        self.assertTrue(status["operation"]["sia_ledger_verified"])

    def test_supervisor_promotes_only_fresh_exact_post_restart_proof(self):
        request, debt = self._apply_request_and_debt()
        siabackup._publish_status(
            state="restoring",
            latest=self._healthy_latest(),
            operation=siabackup._operation(
                request["id"], "restore-apply", "running",
                prepared_id=debt["prepared_id"], ready=True,
                sia_ledger_verified=True))
        observation = {
            "ready": True, "sia_ledger_verified": True,
            "committed": True,
        }
        with mock.patch.object(
                siabackup, "_post_restart_observation",
                return_value=observation):
            self.assertTrue(siabackup.finalize_restore_request(
                debt["request_path"]))
        status = siabackup.read_status()
        self.assertEqual(status["state"], "verified")
        self.assertEqual(status["operation"]["phase"], "verified")
        self.assertFalse(os.path.lexists(debt["request_path"]))
        self.assertFalse(os.path.lexists(siabackup.SUPERVISOR_PATH))

    def test_supervisor_finalizer_replays_after_request_retirement(self):
        request, debt = self._apply_request_and_debt(write_request=False)
        siabackup._publish_status(
            state="restoring", latest=self._healthy_latest(),
            operation=siabackup._operation(
                request["id"], "restore-apply", "verified",
                prepared_id=debt["prepared_id"], ready=True,
                sia_ledger_verified=True))
        with mock.patch.object(
                siabackup, "_post_restart_observation",
                return_value={"ready": True,
                              "sia_ledger_verified": True,
                              "committed": True}):
            self.assertTrue(siabackup.finalize_restore_request(
                debt["request_path"]))
        self.assertFalse(os.path.lexists(siabackup.SUPERVISOR_PATH))

    def test_supervisor_withholds_green_when_fresh_adoption_is_absent(self):
        request, debt = self._apply_request_and_debt()
        siabackup._publish_status(
            state="restoring",
            operation=siabackup._operation(
                request["id"], "restore-apply", "running",
                prepared_id=debt["prepared_id"], ready=True,
                sia_ledger_verified=True))
        with mock.patch.object(
                siabackup, "_post_restart_observation",
                return_value={"ready": True,
                              "sia_ledger_verified": True,
                              "committed": False}):
            self.assertTrue(siabackup.finalize_restore_request(
                debt["request_path"]))
        status = siabackup.read_status()
        self.assertEqual(status["state"], "blocked")
        self.assertEqual(status["operation"]["phase"], "blocked")

    def test_prebarrier_crash_without_adoption_restarts_non_green(self):
        request, _debt = self._apply_request_and_debt(
            phase="child-running")
        owners = contextlib.nullcontext(None)
        observed = {
            "ready": False, "sia_ledger_verified": True,
            "committed": False,
        }
        with mock.patch.object(
                siabackup.sialib, "brainstem_owner",
                return_value=owners), \
                mock.patch.object(
                    siabackup.sialib, "corpus_owner",
                    return_value=contextlib.nullcontext(None)), \
                mock.patch.object(
                    siabackup.sialib, "gbrain_owner",
                    return_value=contextlib.nullcontext(None)), \
                mock.patch.object(
                    siabackup.siacapsule,
                    "validate_restore_capability"), \
                mock.patch.object(
                    siabackup, "_live_restore_observation",
                    return_value=observed):
            self.assertEqual(siabackup.run_restore_recovery(
                request["id"], lifecycle_fd=None), 0)
        status = siabackup.read_status()
        self.assertEqual(status["state"], "blocked")
        self.assertFalse(status["operation"]["ready"])
        self.assertTrue(status["operation"]["sia_ledger_verified"])

    def test_postbarrier_crash_requires_exact_adoption_before_promotion(self):
        self._configure()
        request, _debt = self._apply_request_and_debt(
            phase="child-running")
        observed = {
            "ready": True, "sia_ledger_verified": True,
            "committed": True,
        }
        with mock.patch.object(
                siabackup.sialib, "brainstem_owner",
                return_value=contextlib.nullcontext(None)), \
                mock.patch.object(
                    siabackup.sialib, "corpus_owner",
                    return_value=contextlib.nullcontext(None)), \
                mock.patch.object(
                    siabackup.sialib, "gbrain_owner",
                    return_value=contextlib.nullcontext(None)), \
                mock.patch.object(
                    siabackup.siacapsule,
                    "validate_restore_capability"), \
                mock.patch.object(
                    siabackup, "_live_restore_observation",
                    return_value=observed):
            self.assertEqual(siabackup.run_restore_recovery(
                request["id"], lifecycle_fd=None), 0)
        status = siabackup.read_status()
        self.assertEqual(status["state"], "restoring")
        self.assertEqual(status["operation"]["phase"], "running")
        self.assertTrue(status["operation"]["ready"])
        self.assertTrue(status["operation"]["sia_ledger_verified"])

    def test_backup_hands_off_before_worker_freezes_live_roots(self):
        self._configure()
        with mock.patch.object(siabackup.siacapsule, "freeze") as freeze:
            request = siabackup.queue_backup(runner=self._runner)
        self.assertEqual(request["action"], "upload")
        self.assertEqual(request["args"], {"scheduled": False})
        freeze.assert_not_called()
        request_info = os.stat(siabackup._request_path(request["id"]))
        self.assertEqual(stat.S_IMODE(request_info.st_mode), 0o600)

    def test_caller_exit_after_acceptance_cannot_cancel_worker_capture(self):
        home = os.path.join(self.temp.name, "async-home")
        fake_bin = os.path.join(self.temp.name, "async-bin")
        os.makedirs(fake_bin, mode=0o700)
        systemd_run = os.path.join(fake_bin, "systemd-run")
        with open(systemd_run, "w", encoding="utf-8") as stream:
            stream.write("#!/bin/sh\nexit 0\n")
        os.chmod(systemd_run, 0o700)
        config_path = os.path.join(
            home, ".config", "sia", "continuity.json")
        key_path = os.path.join(
            home, ".local", "state", "sia-continuity",
            "repository.key")
        os.makedirs(os.path.dirname(config_path), mode=0o700)
        os.makedirs(os.path.dirname(key_path), mode=0o700)
        os.chmod(home, 0o700)
        repository = os.path.join(home, "repository")
        public_root = os.path.join(home, ".local", "share", "sia")
        os.makedirs(public_root, mode=0o700)
        with open(os.path.join(public_root, "pub.hex"),
                  "w", encoding="ascii") as stream:
            stream.write(self.public_key + "\n")
        config = {
            "schema": siabackup.CONFIG_SCHEMA,
            "repository": repository,
            "environment_file": None,
            "repository_id": "b" * 64,
            "brain_public_key": self.public_key,
            "created_at": "test-time",
        }
        with open(config_path, "w", encoding="utf-8") as stream:
            json.dump(config, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
        os.chmod(config_path, 0o600)
        with open(key_path, "wb") as stream:
            stream.write(b"recovery-key\n")
        os.chmod(key_path, 0o600)
        environment = os.environ.copy()
        environment.update({
            "HOME": home,
            "PATH": fake_bin + os.pathsep + environment["PATH"],
        })
        caller = subprocess.run(
            [os.path.join(REPO, "bin", "sia"), "backup", "now"],
            env=environment, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False)
        self.assertEqual(caller.returncode, 0, caller.stderr)
        requests = os.path.join(
            home, ".local", "state", "sia-continuity", "requests")
        request_names = os.listdir(requests)
        self.assertEqual(len(request_names), 1)
        request_path = os.path.join(requests, request_names[0])
        captured = os.path.join(home, "worker-captured")
        worker_code = f'''
import json, os, sys
sys.path.insert(0, {os.path.join(REPO, "bin")!r})
import siabackup
captured = {captured!r}
expected = {{"capsule_id": "capsule", "manifest_sha256": "digest",
             "classification": "ready", "public_key": {self.public_key!r}}}
def freeze(path):
    if not os.path.isfile({request_path!r}):
        raise RuntimeError("durable request disappeared")
    os.mkdir(path, 0o700)
    with open(captured, "w", encoding="utf-8") as stream:
        stream.write("captured\\n")
    return {{**expected, "path": path}}
def restic(arguments, **_kwargs):
    if arguments[0] == "backup":
        return json.dumps({{"message_type": "summary",
                           "snapshot_id": "abc123"}}) + "\\n"
    return ""
siabackup.siacapsule.freeze = freeze
siabackup.siacapsule.verify = lambda _path: expected
siabackup._run_restic = restic
siabackup._verify_snapshot_offpath = lambda *_args, **_kwargs: expected
raise SystemExit(siabackup.run_request({request_path!r}))
'''
        worker = subprocess.run(
            [sys.executable, "-c", worker_code], env=environment,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False)
        self.assertEqual(worker.returncode, 0, worker.stderr)
        self.assertTrue(os.path.isfile(captured))
        self.assertFalse(os.path.lexists(request_path))

    def test_ambiguous_launch_retains_request_and_restore_debt(self):
        def ambiguous(_command):
            raise TimeoutError("client timed out after unit submission")

        debt = b"durable supervisor authority\n"

        def supervisor(_request, _prepared_id):
            siabackup._write_exclusive(siabackup.SUPERVISOR_PATH, debt)
            return {"retained": True}

        with mock.patch.object(
                siabackup, "_create_supervisor_intent",
                side_effect=supervisor), \
                self.assertRaisesRegex(TimeoutError, "unit submission"):
            siabackup._queue(
                "apply", {}, request_id="abc123", runner=ambiguous,
                prepared_id="def456")
        self.assertTrue(os.path.isfile(
            siabackup._request_path("abc123")))
        with open(siabackup.SUPERVISOR_PATH, "rb") as stream:
            self.assertEqual(stream.read(), debt)
        status = siabackup.read_status()
        self.assertEqual(status["state"], "blocked")
        self.assertEqual(status["operation"]["request_id"], "abc123")

    def test_failed_liveness_probe_never_retires_worker_authority(self):
        request = siabackup._create_request(
            "upload", {"scheduled": True}, request_id="abc123")
        capsule = os.path.join(
            siabackup.CAPSULES_DIR, ".capsule-abc123")
        os.mkdir(capsule, 0o700)
        refused = subprocess.CompletedProcess([], 1, stdout="", stderr="")
        with mock.patch.object(
                siabackup.sialib, "_run_bounded_text_process",
                return_value=refused), \
                self.assertRaisesRegex(
                    siabackup.BlockedError, "could not be established"):
            siabackup._reconcile_inactive_spools()
        self.assertTrue(os.path.isfile(
            siabackup._request_path(request["id"])))
        self.assertTrue(os.path.isdir(capsule))

    def test_configured_power_cut_probes_enables_and_starts_before_retire(self):
        config = self._configure()
        request = siabackup._create_request(
            "setup", {
                "repository": config["repository"],
                "environment_file": None,
                "recovery_key_out": os.path.join(
                    self.temp.name, "repository.key"),
                "identity_key_out": os.path.join(
                    self.temp.name, "identity.key"),
            }, request_id="abc123")
        events = []

        def restic(arguments, **_kwargs):
            events.append(arguments[0])
            return ""

        with mock.patch.object(
                siabackup, "_request_id_active", return_value=False), \
                mock.patch.object(
                    siabackup, "_run_restic", side_effect=restic), \
                mock.patch.object(
                    siabackup, "_enable_schedules",
                    side_effect=lambda: events.append("enable")), \
                mock.patch.object(
                    siabackup, "_start_schedules",
                    side_effect=lambda: events.append("start")):
            siabackup._reconcile_inactive_spools()
        self.assertEqual(events, ["cat", "enable", "start"])
        self.assertFalse(os.path.lexists(
            siabackup._request_path(request["id"])))
        status = siabackup.read_status()
        self.assertEqual(status["operation"]["phase"], "verified")

    def test_schedule_start_power_cut_retains_idempotent_request(self):
        config = self._configure()
        request = siabackup._create_request(
            "connect", {
                "repository": config["repository"],
                "environment_file": None,
                "recovery_key_file": os.path.join(
                    self.temp.name, "repository.key"),
            }, request_id="abc123")
        start = mock.Mock(side_effect=[
            RuntimeError("power cut before timer start"), None])
        with mock.patch.object(
                siabackup, "_request_id_active", return_value=False), \
                mock.patch.object(
                    siabackup, "_run_restic", return_value=""), \
                mock.patch.object(siabackup, "_enable_schedules"), \
                mock.patch.object(siabackup, "_start_schedules", start):
            with self.assertRaisesRegex(RuntimeError, "power cut"):
                siabackup._reconcile_inactive_spools()
            self.assertTrue(os.path.isfile(
                siabackup._request_path(request["id"])))
            siabackup._reconcile_inactive_spools()
        self.assertEqual(start.call_count, 2)
        self.assertFalse(os.path.lexists(
            siabackup._request_path(request["id"])))

    def test_setup_start_failure_never_publishes_configuration(self):
        offline = os.path.join(self.temp.name, "offline-start-failure")
        os.mkdir(offline, 0o700)
        recovery = os.path.join(offline, "repository.key")
        identity = os.path.join(offline, "identity.key")
        events = []

        def run(arguments, **_kwargs):
            events.append(arguments[0])
            if arguments == ["cat", "config"]:
                return self._repository_config_output()
            return ""

        def export(path):
            events.append("identity")
            siabackup._write_exclusive(path, b"offline-identity\n")

        def start():
            events.append("start")
            raise RuntimeError("power cut before timer activation")

        with mock.patch.object(siabackup, "_run_restic", side_effect=run), \
                mock.patch.object(
                    siabackup.siacapsule, "export_identity_key",
                    side_effect=export), \
                mock.patch.object(
                    siabackup, "_enable_schedules",
                    side_effect=lambda: events.append("enable")), \
                mock.patch.object(
                    siabackup, "_start_schedules", side_effect=start), \
                self.assertRaisesRegex(RuntimeError, "power cut"):
            siabackup._perform_setup({
                "repository": os.path.join(
                    self.temp.name, "repository-start-failure"),
                "environment_file": None,
                "recovery_key_out": recovery,
                "identity_key_out": identity,
            })
        self.assertEqual(
            events, ["identity", "init", "cat", "enable", "start"])
        self.assertFalse(os.path.lexists(siabackup.CONFIG_PATH))
        self.assertFalse(os.path.lexists(siabackup.KEY_PATH))
        self.assertFalse(any(
            name.startswith(".repository-key-stage-")
            for name in os.listdir(siabackup.ROOT)))
        self.assertTrue(os.path.isfile(recovery))
        self.assertTrue(os.path.isfile(identity))

    def test_setup_partial_crash_points_retire_only_hot_local_state(self):
        phases = (
            ("request-created", "a1"),
            ("key-staged", "b2"),
            ("recovery-exported", "c3"),
            ("identity-exported", "d4"),
            ("repository-initialized", "e5"),
            ("key-committed", "f6"),
        )
        for phase, request_id in phases:
            with self.subTest(phase=phase):
                offline = os.path.join(self.temp.name, "offline-" + phase)
                os.mkdir(offline, 0o700)
                recovery = os.path.join(offline, "repository.key")
                identity = os.path.join(offline, "identity.key")
                request = siabackup._create_request(
                    "setup", {
                        "repository": os.path.join(
                            self.temp.name, "repository-" + phase),
                        "environment_file": None,
                        "recovery_key_out": recovery,
                        "identity_key_out": identity,
                    }, request_id=request_id)
                key = b"recovery-key-" + phase.encode("ascii") + b"\n"
                stage = os.path.join(
                    siabackup.ROOT,
                    ".repository-key-stage-" + request_id)
                if phase != "request-created":
                    siabackup._write_exclusive(stage, key)
                if phase in {
                        "recovery-exported", "identity-exported",
                        "repository-initialized", "key-committed"}:
                    siabackup._write_exclusive(recovery, key)
                if phase in {
                        "identity-exported", "repository-initialized",
                        "key-committed"}:
                    siabackup._write_exclusive(
                        identity, b"offline-identity\n")
                if phase == "key-committed":
                    siabackup._retire_private_file(stage, siabackup.ROOT)
                    siabackup._write_exclusive(siabackup.KEY_PATH, key)
                with mock.patch.object(
                        siabackup, "_request_id_active",
                        return_value=False):
                    siabackup._reconcile_inactive_spools()
                self.assertFalse(os.path.lexists(
                    siabackup._request_path(request["id"])))
                self.assertFalse(os.path.lexists(stage))
                self.assertFalse(os.path.lexists(siabackup.KEY_PATH))
                self.assertFalse(os.path.lexists(siabackup.CONFIG_PATH))
                if os.path.lexists(recovery):
                    with open(recovery, "rb") as stream:
                        self.assertEqual(stream.read(), key)
                if os.path.lexists(identity):
                    self.assertTrue(os.path.isfile(identity))
        status = siabackup.read_status()
        self.assertEqual(status["state"], "blocked")
        self.assertIn("Reconnect", status["detail"])

    def test_setup_timer_start_precedes_terminal_operation_status(self):
        offline = os.path.join(self.temp.name, "offline-terminal-order")
        os.mkdir(offline, 0o700)
        request = siabackup._create_request(
            "setup", {
                "repository": os.path.join(
                    self.temp.name, "repository-terminal-order"),
                "environment_file": None,
                "recovery_key_out": os.path.join(
                    offline, "repository.key"),
                "identity_key_out": os.path.join(
                    offline, "identity.key"),
            }, request_id="deadbeef")
        observed = []

        def export(path):
            siabackup._write_exclusive(path, b"offline-identity\n")

        def start():
            observed.append(
                siabackup.read_status()["operation"]["phase"])

        def run(arguments, **_kwargs):
            if arguments == ["cat", "config"]:
                return self._repository_config_output()
            return ""

        with mock.patch.object(siabackup, "_run_restic", side_effect=run), \
                mock.patch.object(
                    siabackup.siacapsule, "export_identity_key",
                    side_effect=export), \
                mock.patch.object(siabackup, "_enable_schedules"), \
                mock.patch.object(
                    siabackup, "_start_schedules", side_effect=start):
            result = siabackup.run_request(
                siabackup._request_path(request["id"]))
        self.assertEqual(result, 0)
        self.assertEqual(observed, ["running"])
        self.assertEqual(
            siabackup.read_status()["operation"]["phase"], "verified")

    def test_restore_intent_is_created_only_after_non_green_status(self):
        observed = []

        def intent(_request, _prepared_id):
            status = siabackup.read_status()
            observed.append((status["state"], status["operation"]["phase"]))
            raise RuntimeError("intent publication refused")

        with mock.patch.object(
                siabackup, "_create_supervisor_intent",
                side_effect=intent), \
                self.assertRaisesRegex(RuntimeError, "intent publication"):
            siabackup._queue(
                "apply", self._apply_args(),
                request_id="aabbcc", prepared_id="def456",
                runner=self._runner)
        self.assertEqual(observed, [("restoring", "accepted")])
        self.assertEqual(siabackup.read_status()["state"], "blocked")
        self.assertFalse(os.path.lexists(
            siabackup._request_path("aabbcc")))
        self.assertFalse(os.path.lexists(siabackup.SUPERVISOR_PATH))

    def test_restore_status_failure_cannot_create_supervisor_debt(self):
        intent = mock.Mock()
        with mock.patch.object(
                siabackup, "_publish_status",
                side_effect=RuntimeError("status publication refused")), \
                mock.patch.object(
                    siabackup, "_create_supervisor_intent", intent), \
                self.assertRaisesRegex(RuntimeError, "status publication"):
            siabackup._queue(
                "apply", self._apply_args(),
                request_id="bbccdd", prepared_id="def456",
                runner=self._runner)
        intent.assert_not_called()
        self.assertFalse(os.path.lexists(
            siabackup._request_path("bbccdd")))
        self.assertFalse(os.path.lexists(siabackup.SUPERVISOR_PATH))

    def test_accepted_restore_without_debt_reconciles_non_green(self):
        request = siabackup._create_request(
            "apply", self._apply_args(),
            request_id="ccddee")
        siabackup._publish_status(
            state="restoring", detail="Continuity request accepted.",
            operation=siabackup._operation(
                request["id"], "restore-apply", "accepted",
                prepared_id="def456"))
        with mock.patch.object(
                siabackup, "_request_id_active", return_value=False):
            siabackup._reconcile_inactive_spools()
        status = siabackup.read_status()
        self.assertEqual(status["state"], "blocked")
        self.assertEqual(status["operation"]["phase"], "blocked")
        self.assertFalse(os.path.lexists(
            siabackup._request_path(request["id"])))

    def test_upload_adapter_passes_only_completed_capsule_to_restic(self):
        capsule = os.path.join(siabackup.CAPSULES_DIR, ".capsule-abc123")
        calls = []

        def run(arguments, **kwargs):
            calls.append((arguments, kwargs.get("cwd")))
            if arguments[0] == "backup":
                return json.dumps({
                    "message_type": "summary", "snapshot_id": "abc123"
                }) + "\n"
            return ""

        verified = {
            "capsule_id": "capsule", "manifest_sha256": "digest",
            "classification": "ready", "public_key": self.public_key,
        }
        frozen = {**verified, "path": capsule}

        def freeze(path):
            self.assertTrue(os.path.isfile(
                siabackup._request_path("abc123")))
            self.assertEqual(path, capsule)
            os.mkdir(path)
            return frozen

        request = {
            "schema": siabackup.REQUEST_SCHEMA,
            "id": "abc123", "created_at": "test-time",
            "action": "upload", "args": {"scheduled": False},
        }
        siabackup._write_exclusive(
            siabackup._request_path("abc123"),
            siabackup._canonical_bytes(request))
        with mock.patch.object(siabackup.siacapsule, "freeze",
                               side_effect=freeze), \
                mock.patch.object(siabackup.siacapsule, "verify",
                               return_value=verified), \
                mock.patch.object(siabackup, "_run_restic", side_effect=run), \
                mock.patch.object(
                    siabackup, "_verify_snapshot_offpath",
                    return_value=verified):
            latest = siabackup._perform_upload(
                {"scheduled": False}, "abc123")
        backup_args, backup_cwd = calls[0]
        self.assertEqual(backup_args[-1], os.path.basename(capsule))
        self.assertEqual(backup_cwd, siabackup.CAPSULES_DIR)
        self.assertNotIn(siabackup.sialib.SHARE, backup_args)
        self.assertTrue(latest["verified"])
        self.assertEqual(calls[-1][0], ["check"])
        self.assertFalse(os.path.lexists(capsule))

    def test_setup_exports_two_secrets_then_probes_before_schedules(self):
        offline = os.path.join(self.temp.name, "offline")
        os.mkdir(offline, 0o700)
        recovery = os.path.join(offline, "repository.key")
        identity = os.path.join(offline, "identity.key")
        events = []

        def run(arguments, **_kwargs):
            events.append(arguments[0])
            if arguments == ["cat", "config"]:
                return self._repository_config_output()
            return ""

        def export(path):
            events.append("identity")
            return siabackup._write_exclusive(path, b"offline-identity\n")

        def enable():
            events.append("enable")

        with mock.patch.object(siabackup, "_run_restic", side_effect=run), \
                mock.patch.object(siabackup.siacapsule,
                                  "export_identity_key", side_effect=export):
            siabackup._perform_setup({
                "repository": os.path.join(self.temp.name, "repository"),
                "environment_file": None,
                "recovery_key_out": recovery,
                "identity_key_out": identity,
            }, enable_schedules=enable)
        self.assertTrue(os.path.isfile(recovery))
        self.assertTrue(os.path.isfile(identity))
        with open(recovery, "rb") as recovery_stream, \
                open(identity, "rb") as identity_stream:
            self.assertNotEqual(recovery_stream.read(), identity_stream.read())
        self.assertEqual(events[-1], "enable")
        self.assertLess(events.index("init"), events.index("cat"))
        self.assertLess(events.index("cat"), events.index("enable"))

    def test_prepare_restores_and_verifies_only_off_path(self):
        self._configure()
        observed_target = []

        def run(arguments, **_kwargs):
            if arguments[0] == "snapshots":
                return json.dumps([{
                    "id": "abc123", "time": "test-time",
                    "tags": [
                        "sia-capsule", "sia-readiness=ready",
                        "sia-brain=" + self.public_key,
                    ],
                }])
            if arguments[:2] == ["ls", "--json"]:
                capsule_name = ".capsule-restored"
                return "\n".join((
                    json.dumps({
                        "message_type": "snapshot", "id": "abc123",
                        "tags": ["sia-capsule"]}),
                    json.dumps({
                        "message_type": "node", "type": "dir",
                        "path": "/" + capsule_name, "size": 0}),
                    json.dumps({
                        "message_type": "node", "type": "file",
                        "path": "/" + capsule_name + "/manifest.json",
                        "size": 3}),
                    json.dumps({
                        "message_type": "node", "type": "dir",
                        "path": "/" + capsule_name + "/payload",
                        "size": 0}),
                )) + "\n"
            if arguments[0] == "restore":
                target = arguments[arguments.index("--target") + 1]
                observed_target.append(target)
                capsule = os.path.join(target, ".capsule-restored")
                os.mkdir(capsule)
                os.mkdir(os.path.join(capsule, "payload"))
                siabackup._write_exclusive(
                    os.path.join(capsule, "manifest.json"), b"{}\n")
            return ""

        verified = {
            "capsule_id": "capsule", "classification": "ready",
            "corpus_head": "corpus-head", "ledger_head": "source-head",
            "public_key": self.public_key,
            "manifest_sha256": "digest",
        }
        with mock.patch.object(siabackup, "_resolve_snapshot",
                               return_value="abc123"), \
                mock.patch.object(siabackup, "_run_restic", side_effect=run), \
                mock.patch.object(siabackup.siacapsule, "verify",
                                  return_value=verified), \
                mock.patch.object(siabackup.siacapsule, "identity_matches",
                                  return_value=True), \
                mock.patch.object(siabackup.sialib, "ledger_head",
                                  return_value=("sequence", "target-head")):
            prepared = siabackup._perform_prepare(
                {"snapshot_id": "abc123"}, "request")
        self.assertTrue(observed_target)
        self.assertEqual(
            os.path.commonpath((siabackup.PREPARED_DIR, observed_target[0])),
            siabackup.PREPARED_DIR)
        self.assertTrue(os.path.isfile(
            siabackup._prepared_path(prepared["prepared_id"])))
        self.assertEqual(prepared["target_ledger_head"], "target-head")
        self.assertEqual(prepared["ledger_head"], "source-head")

    def test_restore_confirmation_is_exact_bounded_one_line(self):
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": "snapshot",
            "ledger_head": "head",
            "corpus_receipt_re_adopt": True,
        }
        raw = json.dumps(confirmation, separators=(",", ":")).encode() + b"\n"
        self.assertEqual(
            siabackup._read_confirmation(io.BytesIO(raw)), confirmation)
        with self.assertRaisesRegex(ValueError, "trailing"):
            siabackup._read_confirmation(io.BytesIO(raw + b"{}\n"))
        with self.assertRaisesRegex(ValueError, "schema"):
            changed = dict(confirmation, phrase="restore")
            siabackup._read_confirmation(io.BytesIO(
                json.dumps(changed, separators=(",", ":")).encode() + b"\n"))

    def test_queue_apply_carries_the_stable_launcher_repository_binding(self):
        config = self._configure()
        prepared = {
            "prepared_id": "def456",
            "snapshot_id": "abc123",
            "capsule_id": "a" * 32,
            "manifest_sha256": "b" * 64,
            "target_ledger_head": "target-head",
            "identity_matches": True,
            "public_key": self.public_key,
            "capsule_path": os.path.join(self.temp.name, "capsule"),
        }
        confirmation = {
            "schema_version": siabackup.CONFIRMATION_SCHEMA_VERSION,
            "phrase": "RESTORE",
            "snapshot_id": prepared["snapshot_id"],
            "ledger_head": prepared["target_ledger_head"],
            "corpus_receipt_re_adopt": True,
        }
        captured = {}

        def enqueue(action, args, **kwargs):
            captured.update({"action": action, "args": args, **kwargs})
            return {"id": "request"}

        with mock.patch.object(siabackup, "load_prepared",
                               return_value=prepared), \
                mock.patch.object(siabackup.sialib, "ledger_head",
                                  return_value=("sequence", "target-head")), \
                mock.patch.object(siabackup.siacapsule, "verify",
                                  return_value={
                                      "capsule_id": prepared["capsule_id"],
                                      "manifest_sha256":
                                          prepared["manifest_sha256"],
                                  }), \
                mock.patch.object(siabackup, "_reconcile_inactive_spools"), \
                mock.patch.object(siabackup, "_queue",
                                  side_effect=enqueue):
            siabackup.queue_apply(prepared["prepared_id"], confirmation)

        binding = siabackup._restore_request_binding(captured["args"])
        self.assertEqual(captured["action"], "apply")
        self.assertEqual(binding, {
            "prepared_id": prepared["prepared_id"],
            "snapshot_id": prepared["snapshot_id"],
            "capsule_id": prepared["capsule_id"],
            "manifest_sha256": prepared["manifest_sha256"],
            "repository": config["repository"],
            "environment_file": "",
            "repository_id": config["repository_id"],
            "configured_at": config["created_at"],
            "target_public_key": config["brain_public_key"],
            "restored_public_key": prepared["public_key"],
        })

        from tests.test_release import _generate_stable_launcher, _load
        launcher_path = os.path.join(
            self.temp.name, "launcher-home", ".local", "bin", "sia")
        _generate_stable_launcher(launcher_path)
        launcher = _load("sia_restore_queue_contract", launcher_path)
        launcher_root = os.path.join(
            self.temp.name, "launcher-state", "sia-continuity")
        launcher_requests = os.path.join(launcher_root, "requests")
        os.makedirs(launcher_requests, mode=0o700)
        request_path = os.path.join(launcher_requests, "abc123.json")
        request = {
            "schema": siabackup.REQUEST_SCHEMA,
            "id": "abc123",
            "created_at": "test-time",
            "action": "apply",
            "args": captured["args"],
        }
        siabackup._write_exclusive(
            request_path, siabackup._canonical_bytes(request))
        launcher_binding = launcher._request_binding(
            request_path, launcher_root)
        self.assertEqual(
            {key: launcher_binding[key] for key in binding}, binding)
        self.assertEqual(launcher_binding["request_id"], request["id"])
        self.assertEqual(launcher_binding["request_path"], request_path)

    def test_restore_acceptance_matches_cockpit_correlation_contract(self):
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": "snapshot",
            "ledger_head": "head",
            "corpus_receipt_re_adopt": True,
        }
        stream = io.BytesIO(
            json.dumps(confirmation, separators=(",", ":")).encode() + b"\n")
        request = {"id": "request"}
        output = io.StringIO()
        with mock.patch.object(siabackup, "queue_apply",
                               return_value=request), \
                mock.patch("sys.stdout", output):
            result = siabackup.cli_restore(
                ["apply", "prepared", "--confirm-stdin"], stream)
        self.assertEqual(result, 0)
        acceptance = json.loads(output.getvalue())
        self.assertEqual(acceptance, {
            "schema_version": siabackup.ACCEPTANCE_SCHEMA_VERSION,
            "accepted": True,
            "request_id": "request",
            "operation": "restore-apply",
            "prepared_id": "prepared",
        })

    def test_backend_refuses_green_without_a_concrete_ready_copy(self):
        with self.assertRaisesRegex(ValueError, "concrete ready copy"):
            siabackup._publish_status(state="verified", latest=None)
        empty = self._healthy_latest(snapshot_id="")
        with self.assertRaisesRegex(ValueError, "concrete ready copy"):
            siabackup._publish_status(state="verified", latest=empty)

    def test_empty_checked_repository_clears_prior_green(self):
        self._configure()
        siabackup._publish_status(
            state="verified", latest=self._healthy_latest())
        request = siabackup._create_request(
            "check", {"scheduled": True}, request_id="abc123")
        with mock.patch.object(
                siabackup, "_perform_check", return_value=None):
            result = siabackup.run_request(
                siabackup._request_path(request["id"]))
        self.assertEqual(result, 3)
        status = siabackup.read_status()
        self.assertEqual(status["state"], "blocked")
        self.assertIsNone(status["latest"])
        self.assertEqual(status["operation"]["phase"], "blocked")

    def test_foreign_verified_snapshot_is_never_a_protecting_copy(self):
        self._configure()
        foreign_public = "c" * 64
        siabackup._record_verification("fedcba", {
            "capsule_id": "foreign-capsule",
            "manifest_sha256": "d" * 64,
            "classification": "ready",
            "public_key": foreign_public,
        })
        response = json.dumps([{
            "id": "fedcba", "time": "later",
            "tags": [
                "sia-capsule", "sia-readiness=ready",
                "sia-brain=" + foreign_public,
            ],
        }, {
            "id": "abc123", "time": "earlier",
            "tags": [
                "sia-capsule", "sia-readiness=ready",
                "sia-brain=" + self.public_key,
            ],
        }])
        with mock.patch.object(
                siabackup, "_run_restic", return_value=response):
            rows = siabackup._snapshot_rows()
        foreign = next(row for row in rows
                       if row["snapshot_id"] == "fedcba")
        self.assertTrue(foreign["verified"])
        self.assertFalse(foreign["identity_matches"])
        self.assertFalse(siabackup._latest_is_protecting(foreign))

    def test_snapshot_preflight_refuses_bytes_before_restore(self):
        listing = "\n".join((
            json.dumps({
                "message_type": "snapshot", "id": "abc123",
                "tags": ["sia-capsule"]}),
            json.dumps({
                "message_type": "node", "type": "dir",
                "path": "/.capsule-test", "size": 0}),
            json.dumps({
                "message_type": "node", "type": "file",
                "path": "/.capsule-test/manifest.json", "size": 2}),
            json.dumps({
                "message_type": "node", "type": "dir",
                "path": "/.capsule-test/payload", "size": 0}),
        )) + "\n"
        calls = []

        def run(arguments, **_kwargs):
            calls.append(arguments[0])
            return listing

        with mock.patch.object(siabackup, "_run_restic", side_effect=run), \
                mock.patch.object(siabackup, "MAX_SPOOL_BYTES", 1), \
                self.assertRaisesRegex(ValueError, "byte policy"):
            siabackup._verify_snapshot_offpath("abc123")
        self.assertEqual(calls, ["ls"])
        self.assertEqual(os.listdir(siabackup.CHECKS_DIR), [])

    def test_failed_partial_restore_is_cleaned_without_following_links(self):
        listing = "\n".join((
            json.dumps({
                "message_type": "snapshot", "id": "abc123",
                "tags": ["sia-capsule"]}),
            json.dumps({
                "message_type": "node", "type": "dir",
                "path": "/.capsule-test", "size": 0}),
            json.dumps({
                "message_type": "node", "type": "file",
                "path": "/.capsule-test/manifest.json", "size": 1}),
            json.dumps({
                "message_type": "node", "type": "dir",
                "path": "/.capsule-test/payload", "size": 0}),
        )) + "\n"
        outside = os.path.join(self.temp.name, "outside")
        siabackup._write_exclusive(outside, b"preserve\n")

        def run(arguments, **_kwargs):
            if arguments[0] == "ls":
                return listing
            target = arguments[arguments.index("--target") + 1]
            partial = os.path.join(target, ".capsule-test")
            os.mkdir(partial)
            siabackup._write_exclusive(
                os.path.join(partial, "partial"), b"partial\n")
            os.symlink(outside, os.path.join(partial, "link"))
            raise RuntimeError("interrupted restore")

        with mock.patch.object(siabackup, "_run_restic", side_effect=run), \
                self.assertRaisesRegex(RuntimeError, "interrupted restore"):
            siabackup._verify_snapshot_offpath("abc123")
        self.assertEqual(os.listdir(siabackup.CHECKS_DIR), [])
        with open(outside, "rb") as stream:
            self.assertEqual(stream.read(), b"preserve\n")

    def test_schedule_enable_refuses_foreign_effective_dropin(self):
        systemd_dir = os.path.join(self.temp.name, "systemd")
        managed_dir = os.path.join(self.temp.name, "managed")
        os.mkdir(systemd_dir, 0o700)
        os.mkdir(managed_dir, 0o700)
        with mock.patch.object(siabackup, "SYSTEMD_USER_DIR", systemd_dir), \
                mock.patch.object(
                    siabackup, "MANAGED_INSTALL_DIR", managed_dir):
            for name, kind, _unit_type, _target in \
                    siabackup._CONTINUITY_UNITS:
                unit = os.path.join(systemd_dir, name)
                raw = ("[Unit]\nDescription=" + name + "\n").encode()
                siabackup._write_exclusive(unit, raw)
                receipt = (
                    "managed-by=khephri.sia\n"
                    f"kind={kind}\n"
                    f"path={unit}\n"
                    f"sha256={siabackup.hashlib.sha256(raw).hexdigest()}\n"
                ).encode()
                siabackup._write_exclusive(
                    os.path.join(managed_dir, name), receipt)

            def fields(name, *, timer):
                value = {
                    "LoadState": "loaded",
                    "FragmentPath": os.path.join(systemd_dir, name),
                    "DropInPaths": ("/foreign.conf"
                                    if name == "sia-backup.timer" else ""),
                    "ActiveState": "inactive",
                    "UnitFileState": "disabled",
                    "Job": "",
                }
                if timer:
                    value["Unit"] = (
                        "sia-backup-check.service"
                        if name == "sia-backup-check.timer" else
                        "sia-backup.service")
                return value

            runner = mock.Mock()
            with mock.patch.object(
                    siabackup, "_systemd_unit_fields",
                    side_effect=fields), \
                    mock.patch.object(
                        siabackup.sialib, "_run_bounded_text_process",
                        runner), \
                    self.assertRaisesRegex(
                        siabackup.BlockedError, "authority is not exact"):
                siabackup._enable_schedules()
            runner.assert_not_called()

    def test_restore_observation_refuses_cross_generation_ledger(self):
        with mock.patch.object(
                siabackup.sialib, "ledger_head",
                side_effect=[(1, "before"), (2, "after")]), \
                mock.patch.object(
                    siabackup.siacapsule, "_health_observation",
                    return_value={
                        "ready": True, "sia_ledger_verified": True}), \
                self.assertRaisesRegex(
                    siabackup.BlockedError, "generation changed"):
            siabackup._live_restore_observation()

    def test_supervisor_debt_retirement_failure_cannot_publish_green(self):
        request, debt = self._apply_request_and_debt()
        siabackup._publish_status(
            state="restoring", latest=self._healthy_latest(),
            operation=siabackup._operation(
                request["id"], "restore-apply", "running",
                prepared_id=debt["prepared_id"], ready=True,
                sia_ledger_verified=True))
        with mock.patch.object(
                siabackup, "_post_restart_observation",
                return_value={
                    "ready": True, "sia_ledger_verified": True,
                    "committed": True}), \
                mock.patch.object(
                    siabackup, "_retire_supervisor_debt",
                    side_effect=RuntimeError("debt retirement refused")), \
                self.assertRaisesRegex(RuntimeError, "debt retirement"):
            siabackup.finalize_restore_request(debt["request_path"])
        status = siabackup.read_status()
        self.assertEqual(status["state"], "restoring")
        self.assertTrue(os.path.isfile(siabackup.SUPERVISOR_PATH))

    def test_signed_identity_adoption_recreates_bound_configuration(self):
        config = self._configure()
        os.unlink(siabackup.CONFIG_PATH)
        restored_public = "c" * 64
        with mock.patch.object(
                siabackup, "_live_brain_public_key",
                return_value=restored_public):
            rebound = siabackup._rebind_after_identity_adoption(
                config, restored_public)
            loaded = siabackup.load_config()
        self.assertEqual(rebound["repository_id"], config["repository_id"])
        self.assertEqual(loaded["repository"], config["repository"])
        self.assertEqual(loaded["brain_public_key"], restored_public)

    def test_real_cli_worker_boundary_holds_runtime_and_publishes_terminal(self):
        home = os.path.join(self.temp.name, "worker-home")
        requests = os.path.join(
            home, ".local", "state", "sia-continuity", "requests")
        os.makedirs(requests, mode=0o700)
        request_path = os.path.join(requests, "abc.json")
        request = {
            "schema": siabackup.REQUEST_SCHEMA,
            "id": "abc",
            "created_at": "test-time",
            "action": "check",
            "args": {"scheduled": False},
        }
        with open(request_path, "w", encoding="utf-8") as stream:
            json.dump(request, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
        os.chmod(request_path, 0o600)
        environment = os.environ.copy()
        environment["HOME"] = home
        result = subprocess.run(
            [os.path.join(REPO, "bin", "sia"), "_continuity-worker",
             request_path], env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 1, result.stderr)
        status_path = os.path.join(
            home, ".local", "state", "sia-continuity", "status.json")
        with open(status_path, encoding="utf-8") as stream:
            status = json.load(stream)
        self.assertEqual(status["operation"]["request_id"], "abc")
        self.assertEqual(status["operation"]["kind"], "backup-check")
        self.assertEqual(status["operation"]["phase"], "failed")
        self.assertEqual(
            stat.S_IMODE(os.stat(status_path).st_mode), 0o600)

    def test_direct_runtime_worker_trampolines_to_stable_front_door(self):
        home = os.path.join(self.temp.name, "trampoline-home")
        stable = os.path.join(home, ".local", "bin", "sia")
        os.makedirs(os.path.dirname(stable))
        with open(stable, "w", encoding="utf-8") as stream:
            stream.write("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
        os.chmod(stable, 0o700)
        request_path = os.path.join(self.temp.name, "request.json")
        environment = os.environ.copy()
        environment["HOME"] = home
        result = subprocess.run(
            [os.path.join(REPO, "bin", "sia-continuity-worker"),
             request_path], env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(),
                         ["_continuity-worker", request_path])


if __name__ == "__main__":
    unittest.main()
