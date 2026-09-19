#!/usr/bin/env python3
"""Focused contracts for the capsule-only recovery-repository adapter."""

import contextlib
import hashlib
import io
import json
import os
import shutil
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

    def test_continuity_json_decoder_refuses_ambiguity_and_constants(self):
        for raw in (
                b'{"state":"safe","state":"private"}',
                b'{"state":NaN}',
                b'{"state":Infinity}',
                b'{"state":-Infinity}'):
            with self.subTest(raw=raw), self.assertRaisesRegex(
                    ValueError, "^continuity fixture is not strict JSON$"):
                siabackup._decode_json(raw, "continuity fixture")

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
            "created_at": "2026-09-04T12:00:00Z",
        }
        siabackup._write_exclusive(
            siabackup.CONFIG_PATH, siabackup._canonical_bytes(config))
        siabackup._write_exclusive(siabackup.KEY_PATH, b"recovery-key\n")
        return config

    def _apply_args(self, *, prepared_id="d" * 32, snapshot_id="abc123",
                    restored_public_key=None):
        confirmation = {
            "schema_version": siabackup.CONFIRMATION_SCHEMA_VERSION,
            "phrase": "RESTORE",
            "snapshot_id": snapshot_id,
            "ledger_head": "f" * 64,
            "corpus_receipt_re_adopt": True,
        }
        target = {
            "corpus_root": {
                "device": 1, "inode": 2, "mode": 448,
                "owner": os.geteuid(),
            },
            "receipt_sha256": "e" * 64,
            "receipt_mode": 384,
        }
        prepared = {
            "prepared_id": prepared_id,
            "snapshot_id": snapshot_id,
            "capsule_id": "a" * 32,
            "manifest_sha256": "b" * 64,
        }
        return {
            **prepared,
            "confirmation": confirmation,
            "identity_key_file": None,
            "repository": os.path.join(self.temp.name, "repository"),
            "environment_file": "",
            "repository_id": "b" * 64,
            "configured_at": "2026-09-04T12:00:00Z",
            "target_public_key": self.public_key,
            "restored_public_key": (
                restored_public_key or self.public_key),
            "adoption": siabackup.siacapsule.adoption_binding(
                prepared, confirmation, target, order=7),
        }

    def _apply_request_and_debt(self, *, phase="restart-attested",
                                write_request=True,
                                restored_public_key=None):
        self._ensure_healthy_latest_authority()
        runtime = os.path.join(REPO, "bin", "sia")
        runtime_info = os.lstat(runtime)
        apply_args = self._apply_args(
            restored_public_key=restored_public_key)
        request = {
            "schema": siabackup.REQUEST_SCHEMA,
            "id": "a" * 32, "created_at": "2026-09-04T12:00:00Z",
            "action": "apply",
            "args": apply_args,
        }
        if write_request:
            siabackup._write_exclusive(
                siabackup._request_path(request["id"]),
                siabackup._canonical_bytes(request))
        request_info = (os.lstat(siabackup._request_path(request["id"]))
                        if write_request else None)
        binding = siabackup._restore_request_binding(apply_args)
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
            "request_device": (str(request_info.st_dev)
                               if request_info is not None else "1"),
            "request_inode": (str(request_info.st_ino)
                              if request_info is not None else "1"),
            **binding,
        }
        siabackup._write_exclusive(
            siabackup.SUPERVISOR_PATH,
            siabackup._canonical_bytes(debt))
        return request, debt

    def _recovery_debt(self, *, phase="restart-attested"):
        self._ensure_healthy_latest_authority()
        runtime = os.path.join(REPO, "bin", "sia")
        runtime_info = os.lstat(runtime)
        debt = {
            "schema": siabackup.SUPERVISOR_SCHEMA,
            "kind": "restore-recover",
            "request_path": "",
            "request_id": "e" * 32,
            "prepared_id": "",
            "snapshot_id": "",
            "capsule_id": "",
            "manifest_sha256": "",
            "phase": phase,
            "child_code": "0",
            "restart_pid": ("123" if phase == "restart-attested"
                            else "pending"),
            "runtime_path": runtime,
            "runtime_device": str(runtime_info.st_dev),
            "runtime_inode": str(runtime_info.st_ino),
            "request_device": "",
            "request_inode": "",
            "repository": "",
            "environment_file": "",
            "identity_key_file": "",
            "repository_id": "",
            "configured_at": "",
            "target_public_key": "",
            "restored_public_key": "",
            "accepted_ledger_head": "",
            "confirmation_sha256": "",
            "adoption_order": "",
            "adoption_record_id": "",
            "target": "",
        }
        siabackup._write_exclusive(
            siabackup.SUPERVISOR_PATH,
            siabackup._canonical_bytes(debt))
        return debt

    def _healthy_latest(self, snapshot_id="abc123"):
        return {
            "snapshot_id": snapshot_id,
            "created_at": "2026-09-04T12:00:00Z",
            "verified": True,
            "readiness": "ready",
            "profile": siabackup.PROFILE,
            "identity_matches": True,
        }

    def _ensure_healthy_latest_authority(self):
        try:
            config = siabackup.load_config()
        except FileNotFoundError:
            config = self._configure()
        latest = self._healthy_latest()
        if siabackup._load_verification(
                latest["snapshot_id"], config=config) is None:
            siabackup._record_verification(latest["snapshot_id"], {
                "capsule_id": "a" * 32,
                "manifest_sha256": "b" * 64,
                "classification": "ready",
                "public_key": self.public_key,
            }, config=config)
        return latest

    def _healthy_prepared(self, prepared_id="d" * 32):
        return {
            "prepared_id": prepared_id,
            "snapshot_id": "abc123",
            "created_at": "2026-09-04T12:00:00Z",
            "readiness": "ready",
            "profile": siabackup.PROFILE,
            "ledger_head": "f" * 64,
            "identity_matches": True,
        }

    def _prepared_status(self, prepared_id="d" * 32):
        prepared = self._healthy_prepared(prepared_id)
        return {
            "schema_version": siabackup.STATUS_SCHEMA_VERSION,
            "state": "prepared",
            "detail": "Restore capsule verified off-path.",
            "repository_display": "External recovery repository",
            "latest": self._healthy_latest(),
            "prepared": prepared,
            "operation": siabackup._operation(
                "a" * 32, "restore-prepare", "verified",
                prepared_id=prepared_id),
            "updated_at": "2026-09-04T12:00:00Z",
        }

    @staticmethod
    def _repository_config_output():
        return json.dumps({"id": "b" * 64}) + "\n"

    def _managed_schedule_authority(self):
        systemd_dir = os.path.join(self.temp.name, "schedule-systemd")
        managed_dir = os.path.join(self.temp.name, "schedule-managed")
        os.mkdir(systemd_dir, 0o700)
        os.mkdir(managed_dir, 0o700)
        for name, kind, unit_type, timer_target in siabackup._CONTINUITY_UNITS:
            unit = os.path.join(systemd_dir, name)
            if unit_type == "timer":
                raw = (
                    "[Timer]\n"
                    "OnCalendar="
                    + ("weekly" if name == "sia-backup-check.timer"
                       else "hourly")
                    + "\nPersistent=true\nUnit=" + timer_target + "\n"
                ).encode()
            else:
                raw = b"[Service]\nType=oneshot\nExecStart=/bin/true\n"
            siabackup._write_exclusive(unit, raw)
            receipt = (
                "managed-by=khephri.sia\n"
                f"kind={kind}\n"
                f"path={unit}\n"
                f"sha256={siabackup.hashlib.sha256(raw).hexdigest()}\n"
            ).encode()
            siabackup._write_exclusive(
                os.path.join(managed_dir, name), receipt)
        return systemd_dir, managed_dir

    @staticmethod
    def _schedule_fields(systemd_dir, name, *, active=True, enabled=True,
                         drop_in="", job="", last="", next_trigger=""):
        return {
            "LoadState": "loaded",
            "FragmentPath": os.path.join(systemd_dir, name),
            "DropInPaths": drop_in,
            "NeedDaemonReload": "no",
            "ActiveState": "active" if active else "inactive",
            "UnitFileState": "enabled" if enabled else "disabled",
            "Job": job,
            "Unit": ("sia-backup-check.service"
                     if name == "sia-backup-check.timer"
                     else "sia-backup.service"),
            "Persistent": "yes",
            "WakeSystem": "no",
            "LastTriggerUSec": last,
            "NextElapseUSecRealtime": next_trigger,
        }

    def test_default_status_is_not_a_protection_claim(self):
        status = siabackup.read_status()
        self.assertEqual(status["state"], "unconfigured")
        self.assertIsNone(status["latest"])
        self.assertNotIn("protected", status["detail"].casefold())

    def test_missing_status_refuses_partial_configuration(self):
        self._configure()
        os.unlink(siabackup.KEY_PATH)
        with self.assertRaisesRegex(
                siabackup.BlockedError, "configuration.*incomplete"):
            siabackup.read_status()
        os.unlink(siabackup.CONFIG_PATH)
        siabackup._write_exclusive(
            siabackup.KEY_PATH, b"recovery-key\n")
        with self.assertRaisesRegex(
                siabackup.BlockedError, "configuration.*incomplete"):
            siabackup.read_status()

    def test_missing_status_validates_configuration_before_claiming_it(self):
        self._configure()
        os.chmod(siabackup.CONFIG_PATH, 0o644)
        with self.assertRaisesRegex(ValueError, "owner-private"):
            siabackup.read_status()

    def test_missing_status_admits_complete_valid_configuration(self):
        self._configure()
        status = siabackup.read_status()
        self.assertEqual(status["state"], "recovery-only")
        self.assertIsNone(status["latest"])

    def test_status_reader_enforces_the_exact_bounded_nested_contract(self):
        valid = self._prepared_status()
        invalid = {
            "top-level extra": {**valid, "unexpected": True},
            "invalid publication timestamp": {
                **valid, "updated_at": "2026-09-04 12:00:00"},
            "unbounded detail": {
                **valid,
                "detail": "x" * (siabackup.STATUS_TEXT_MAX_CHARS + 1)},
            "detail control": {**valid, "detail": "unsafe\n"},
            "latest extra": {
                **valid, "latest": {**valid["latest"], "extra": "x"}},
            "latest identifier": {
                **valid,
                "latest": {**valid["latest"], "snapshot_id": "ABC123"}},
            "latest identifier control": {
                **valid,
                "latest": {
                    **valid["latest"], "snapshot_id": "abc123\n"}},
            "latest identifier bound": {
                **valid,
                "latest": {
                    **valid["latest"],
                    "snapshot_id": (
                        "a" * siabackup.STATUS_IDENTIFIER_MAX_CHARS + "a")}},
            "latest timestamp": {
                **valid,
                "latest": {**valid["latest"], "created_at": "later"}},
            "latest noncanonical fraction": {
                **valid,
                "latest": {
                    **valid["latest"],
                    "created_at": "2026-09-04T12:00:00.120Z"}},
            "latest noncanonical zero offset": {
                **valid,
                "latest": {
                    **valid["latest"],
                    "created_at": "2026-09-04T12:00:00+00:00"}},
            "latest readiness": {
                **valid,
                "latest": {**valid["latest"], "readiness": "maybe"}},
            "latest profile": {
                **valid,
                "latest": {**valid["latest"], "profile": "other"}},
            "prepared extra": {
                **valid,
                "prepared": {**valid["prepared"], "extra": "x"}},
            "prepared identifier": {
                **valid,
                "prepared": {**valid["prepared"], "prepared_id": "ABC"}},
            "prepared identifier width": {
                **valid,
                "prepared": {**valid["prepared"], "prepared_id": "abc123"}},
            "prepared timestamp": {
                **valid,
                "prepared": {**valid["prepared"], "created_at": "later"}},
            "prepared readiness": {
                **valid,
                "prepared": {**valid["prepared"], "readiness": "unknown"}},
            "prepared ledger head": {
                **valid,
                "prepared": {**valid["prepared"], "ledger_head": "head"}},
            "prepared ledger head control": {
                **valid,
                "prepared": {
                    **valid["prepared"], "ledger_head": "f" * 64 + "\n"}},
            "operation extra": {
                **valid,
                "operation": {**valid["operation"], "extra": "x"}},
            "operation request identifier": {
                **valid,
                "operation": {**valid["operation"], "request_id": "REQ"}},
            "operation request identifier width": {
                **valid,
                "operation": {
                    **valid["operation"], "request_id": "abc123"}},
            "operation request identifier bound": {
                **valid,
                "operation": {
                    **valid["operation"],
                    "request_id": (
                        "a" * siabackup.STATUS_IDENTIFIER_MAX_CHARS + "a")}},
            "operation kind": {
                **valid,
                "operation": {**valid["operation"], "kind": "other"}},
            "prepared operation mismatch": {
                **valid,
                "operation": {**valid["operation"], "prepared_id": "abc999"}},
        }
        for label, document in invalid.items():
            with self.subTest(label=label):
                siabackup._atomic_json(siabackup.STATUS_PATH, document)
                with self.assertRaisesRegex(
                        ValueError,
                        "continuity (?:.* status|status schema) is invalid"):
                    siabackup.read_status()

    def test_malformed_status_cannot_erase_a_prepared_reference(self):
        prepared_id = "d" * 32
        prepared_root = os.path.join(siabackup.PREPARED_DIR, prepared_id)
        os.mkdir(prepared_root, 0o700)
        siabackup._write_exclusive(
            os.path.join(prepared_root, "preserve"), b"prepared\n")
        corrupt = self._prepared_status(prepared_id)
        corrupt["prepared"]["unexpected"] = "discarded by old fallback"
        raw = siabackup._canonical_bytes(corrupt)
        siabackup._write_exclusive(siabackup.STATUS_PATH, raw)

        with self.assertRaisesRegex(ValueError, "prepared status is invalid"):
            siabackup._publish_status(detail="A newer publication.")
        self.assertEqual(
            siabackup._read_regular(
                siabackup.STATUS_PATH, "continuity status", private=True),
            raw)

        with self.assertRaisesRegex(ValueError, "prepared status is invalid"):
            siabackup._reconcile_inactive_spools()
        self.assertTrue(os.path.isdir(prepared_root))
        self.assertTrue(os.path.isfile(os.path.join(prepared_root, "preserve")))

    def test_status_publication_bootstraps_only_an_absent_safe_target(self):
        self.assertFalse(os.path.lexists(siabackup.STATUS_PATH))
        published = siabackup._publish_status()
        self.assertEqual(siabackup.read_status(), published)

        os.chmod(siabackup.STATUS_PATH, 0o640)
        before = siabackup._read_regular(
            siabackup.STATUS_PATH, "unsafe status", private=False)
        with self.assertRaisesRegex(ValueError, "owner-private"):
            siabackup._publish_status(detail="Must not replace unsafe state.")
        self.assertEqual(
            siabackup._read_regular(
                siabackup.STATUS_PATH, "unsafe status", private=False),
            before)
        self.assertEqual(stat.S_IMODE(os.stat(siabackup.STATUS_PATH).st_mode),
                         0o640)

    def test_status_disappearing_after_open_is_not_treated_as_absent(self):
        document = self._prepared_status()
        siabackup._write_exclusive(
            siabackup.STATUS_PATH, siabackup._canonical_bytes(document))
        real_os = siabackup.os

        class OsShim:
            def __getattr__(self, name):
                return getattr(real_os, name)

            @staticmethod
            def stat(*_args, **_kwargs):
                raise FileNotFoundError

        with mock.patch.object(
                siabackup, "os", OsShim()), \
                self.assertRaisesRegex(ValueError, "changed while read"):
            siabackup._publish_status(detail="Must not bootstrap a race.")
        self.assertEqual(
            siabackup._read_regular(
                siabackup.STATUS_PATH, "continuity status", private=True),
            siabackup._canonical_bytes(document))

    def test_status_bootstrap_refuses_a_concurrent_new_target(self):
        original = siabackup._atomic_json
        competing = b'{"competing":"status"}\n'

        def appear(path, value, *, require_absent=False):
            siabackup._write_exclusive(path, competing)
            return original(path, value, require_absent=require_absent)

        with mock.patch.object(
                siabackup, "_atomic_json", side_effect=appear), \
                self.assertRaisesRegex(ValueError, "appeared during bootstrap"):
            siabackup._publish_status()
        self.assertEqual(
            siabackup._read_regular(
                siabackup.STATUS_PATH, "competing status", private=True),
            competing)

    def test_bootstrap_link_cleanup_debt_is_recovered_before_status_read(self):
        real_os = siabackup.os
        refused = False

        class OsShim:
            def __getattr__(self, name):
                return getattr(real_os, name)

            @staticmethod
            def unlink(path, *args, **kwargs):
                nonlocal refused
                name = os.path.basename(path)
                if not refused and name.startswith(".status-stage-") \
                        and os.path.isfile(siabackup.STATUS_PATH):
                    refused = True
                    raise OSError("stage unlink refused")
                return real_os.unlink(path, *args, **kwargs)

        with mock.patch.object(siabackup, "os", OsShim()), \
                self.assertRaisesRegex(OSError, "stage unlink refused"):
            siabackup._publish_status()
        stages = [
            os.path.join(siabackup.ROOT, name)
            for name in os.listdir(siabackup.ROOT)
            if name.startswith(".status-stage-")
        ]
        self.assertEqual(len(stages), 1)
        self.assertEqual(os.stat(stages[0]).st_ino,
                         os.stat(siabackup.STATUS_PATH).st_ino)
        self.assertEqual(os.stat(stages[0]).st_nlink, 2)

        siabackup._reconcile_inactive_spools()
        self.assertEqual(siabackup.read_status()["state"], "unconfigured")
        self.assertFalse(os.path.lexists(stages[0]))
        self.assertEqual(os.stat(siabackup.STATUS_PATH).st_nlink, 1)

    def test_atomic_json_replace_failure_retires_its_stage(self):
        class OsShim:
            def __getattr__(self, name):
                return getattr(os, name)

        os_shim = OsShim()
        os_shim.replace = mock.Mock(side_effect=OSError("replace refused"))
        with mock.patch.object(
                siabackup, "os", os_shim), \
                self.assertRaisesRegex(OSError, "replace refused"):
            siabackup._atomic_json(
                siabackup.STATUS_PATH, siabackup._default_status())
        self.assertFalse(any(
            name.startswith(".status-stage-")
            for name in os.listdir(siabackup.ROOT)))

    def test_queue_retains_post_rename_status_authority_until_reconciled(self):
        real_fsync_dir = siabackup._fsync_dir

        def fail_after_status_rename(path):
            status_visible = os.path.isfile(siabackup.STATUS_PATH)
            stage_visible = any(
                name.startswith(".status-stage-")
                for name in os.listdir(siabackup.ROOT))
            if os.path.abspath(path) == os.path.abspath(siabackup.ROOT) \
                    and status_visible and not stage_visible:
                raise OSError("status directory durability is unknown")
            return real_fsync_dir(path)

        with mock.patch.object(
                siabackup, "_fsync_dir",
                side_effect=fail_after_status_rename), \
                self.assertRaisesRegex(OSError, "durability is unknown"):
            siabackup._queue(
                "upload", {"scheduled": False},
                request_id="a" * 32, runner=self._runner)

        request_path = siabackup._request_path("a" * 32)
        self.assertTrue(os.path.isfile(request_path))
        status = siabackup.read_status()
        self.assertEqual(status["state"], "queued")
        self.assertEqual(status["operation"]["phase"], "accepted")

        with mock.patch.object(
                siabackup, "_request_id_active", return_value=False):
            siabackup._reconcile_inactive_spools()
        self.assertFalse(os.path.lexists(request_path))
        status = siabackup.read_status()
        self.assertEqual(status["state"], "blocked")
        self.assertEqual(status["operation"]["phase"], "blocked")

    def test_ambiguous_supervisor_creation_reconciles_unlaunched_apply(self):
        config = self._configure()
        prepared_id = "d" * 32
        args = self._apply_args(prepared_id=prepared_id)
        prepared = {
            "prepared_id": prepared_id,
            "snapshot_id": args["snapshot_id"],
            "capsule_id": args["capsule_id"],
            "manifest_sha256": args["manifest_sha256"],
            "public_key": config["brain_public_key"],
        }
        real_fsync_dir = siabackup._fsync_dir
        failed = False

        def fail_once_after_supervisor_create(path):
            nonlocal failed
            if not failed and os.path.isfile(siabackup.SUPERVISOR_PATH):
                failed = True
                raise OSError("supervisor durability is unknown")
            return real_fsync_dir(path)

        launch = mock.Mock(return_value=self._runner([]))
        main = sys.modules["__main__"]
        with mock.patch.object(
                siabackup, "load_prepared", return_value=prepared), \
                mock.patch.object(
                    siabackup.siacapsule, "target_identity",
                    return_value=args["adoption"]["target"]), \
                mock.patch.object(
                    main, "__file__", os.path.join(REPO, "bin", "sia")), \
                mock.patch.object(
                    siabackup, "_fsync_dir",
                    side_effect=fail_once_after_supervisor_create), \
                self.assertRaisesRegex(OSError, "durability is unknown"):
            siabackup._queue(
                "apply", args, request_id="a" * 32,
                runner=launch, prepared_id=prepared_id)
        launch.assert_not_called()
        self.assertTrue(os.path.isfile(
            siabackup._request_path("a" * 32)))
        debt = siabackup.load_supervisor_debt()
        self.assertEqual(debt["phase"], "accepted")

        with mock.patch.object(
                siabackup, "_request_id_active", return_value=False):
            siabackup._reconcile_inactive_spools()
        self.assertFalse(os.path.lexists(siabackup.SUPERVISOR_PATH))
        self.assertFalse(os.path.lexists(
            siabackup._request_path("a" * 32)))
        status = siabackup.read_status()
        self.assertEqual(status["state"], "blocked")
        self.assertEqual(status["operation"]["phase"], "blocked")

    def test_reconciliation_retires_exact_legacy_atomic_stages(self):
        config_parent = os.path.dirname(siabackup.CONFIG_PATH)
        os.makedirs(config_parent, mode=0o700, exist_ok=True)
        stages = (
            os.path.join(siabackup.ROOT, ".status-stage-" + "a" * 32),
            os.path.join(config_parent, ".status-stage-" + "b" * 32),
        )
        for stage in stages:
            siabackup._write_exclusive(stage, b"legacy stage\n")
        siabackup._reconcile_inactive_spools()
        for stage in stages:
            self.assertFalse(os.path.lexists(stage))

        suspicious = os.path.join(
            siabackup.ROOT, ".status-stage-not-a-managed-identifier")
        siabackup._write_exclusive(suspicious, b"do not guess\n")
        with self.assertRaisesRegex(
                siabackup.BlockedError, "publication spool needs review"):
            siabackup._reconcile_inactive_spools()
        self.assertTrue(os.path.isfile(suspicious))

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

    def _restic_authority_case(self, name, mutation, phase):
        authority = os.path.join(self.temp.name, "restic-authority-" + name)
        os.mkdir(authority, 0o700)
        secret = os.path.join(authority, "rclone.conf")
        secret_replacement = os.path.join(authority, "rclone.next")
        environment = os.path.join(authority, "repository.env")
        environment_replacement = os.path.join(
            authority, "repository.next")
        key = os.path.join(authority, "repository.key")
        key_replacement = os.path.join(authority, "repository.next-key")
        audit = os.path.join(authority, "action.json")
        fake_restic = os.path.join(authority, "restic")
        siabackup._write_exclusive(secret, b"secret=A\n")
        siabackup._write_exclusive(secret_replacement, b"secret=B\n")
        siabackup._write_exclusive(
            environment, ("RCLONE_CONFIG=" + secret + "\n").encode())
        siabackup._write_exclusive(
            environment_replacement,
            ("RCLONE_CONFIG=" + secret_replacement + "\n").encode())
        siabackup._write_exclusive(key, b"key=A\n")
        siabackup._write_exclusive(key_replacement, b"key=B\n")
        source = f'''#!{sys.executable}
import json
import os
import sys

mutation = {mutation!r}
phase = {phase!r}
environment = {environment!r}
environment_replacement = {environment_replacement!r}
secret = {secret!r}
secret_replacement = {secret_replacement!r}
key = {key!r}
key_replacement = {key_replacement!r}
audit = {audit!r}

def rewrite(path, raw):
    with open(path, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())

def mutate():
    if mutation == "environment-rebind":
        os.replace(environment_replacement, environment)
    elif mutation == "path-secret-in-place":
        rewrite(secret, b"secret=B\\n")
    elif mutation == "path-secret-rebind":
        os.replace(secret_replacement, secret)
    elif mutation == "key-in-place":
        rewrite(key, b"key=B\\n")
    else:
        raise RuntimeError("unknown mutation")

if sys.argv[1:] == ["cat", "config"]:
    if phase == "identity":
        mutate()
    print(json.dumps({{"id": {("b" * 64)!r}}}))
    raise SystemExit(0)

if phase == "action":
    mutate()
with open(os.environ["RCLONE_CONFIG"], "rb") as stream:
    backend = stream.read().decode("utf-8")
with open(os.environ["RESTIC_PASSWORD_FILE"], "rb") as stream:
    password = stream.read().decode("utf-8")
with open(audit, "w", encoding="utf-8") as stream:
    json.dump({{"backend": backend, "password": password}}, stream)
print("untrusted-action-result")
'''
        siabackup._write_exclusive(fake_restic, source.encode(), 0o700)
        config = {
            "schema": siabackup.CONFIG_SCHEMA,
            "repository": "rest:https://example.invalid/repository",
            "environment_file": environment,
            "repository_id": "b" * 64,
            "brain_public_key": self.public_key,
            "created_at": "2026-09-04T12:00:00Z",
        }
        return config, key, fake_restic, audit

    def test_restic_refuses_to_act_after_authority_generation_changes(self):
        for mutation in ("environment-rebind", "path-secret-in-place"):
            with self.subTest(mutation=mutation):
                config, key, fake_restic, audit = \
                    self._restic_authority_case(
                        "before-" + mutation, mutation, "identity")
                with self.assertRaisesRegex(
                        siabackup.BlockedError,
                        "repository authority changed"):
                    siabackup._run_restic(
                        ["snapshots", "--json"], config=config,
                        key_path=key, restic_path=fake_restic)
                self.assertFalse(os.path.lexists(audit))
                self.assertEqual(os.listdir(siabackup.CHECKS_DIR), [])

    def test_restic_withholds_result_if_authority_changes_during_action(self):
        for mutation in ("path-secret-rebind", "key-in-place"):
            with self.subTest(mutation=mutation):
                config, key, fake_restic, audit = \
                    self._restic_authority_case(
                        "during-" + mutation, mutation, "action")
                with self.assertRaisesRegex(
                        siabackup.BlockedError,
                        "repository authority changed"):
                    siabackup._run_restic(
                        ["snapshots", "--json"], config=config,
                        key_path=key, restic_path=fake_restic)
                with open(audit, encoding="utf-8") as stream:
                    observed = json.load(stream)
                self.assertEqual(observed, {
                    "backend": "secret=A\n", "password": "key=A\n",
                })
                self.assertEqual(os.listdir(siabackup.CHECKS_DIR), [])

    def test_restic_allows_unchanged_admitted_authority(self):
        config, key, fake_restic, audit = self._restic_authority_case(
            "unchanged", "path-secret-in-place", "never")
        self.assertEqual(
            siabackup._run_restic(
                ["snapshots", "--json"], config=config,
                key_path=key, restic_path=fake_restic),
            "untrusted-action-result\n")
        with open(audit, encoding="utf-8") as stream:
            observed = json.load(stream)
        self.assertEqual(observed, {
            "backend": "secret=A\n", "password": "key=A\n",
        })
        self.assertEqual(os.listdir(siabackup.CHECKS_DIR), [])

    def test_restic_allows_unchanged_initialization_authority(self):
        config, key, fake_restic, audit = self._restic_authority_case(
            "initialization", "path-secret-in-place", "never")
        config = {**config, "repository_id": ""}
        self.assertEqual(
            siabackup._run_restic(
                ["init"], config=config, key_path=key,
                restic_path=fake_restic),
            "untrusted-action-result\n")
        with open(audit, encoding="utf-8") as stream:
            observed = json.load(stream)
        self.assertEqual(observed, {
            "backend": "secret=A\n", "password": "key=A\n",
        })
        self.assertEqual(os.listdir(siabackup.CHECKS_DIR), [])

    def test_restic_authority_crash_stage_is_reconciled(self):
        stage = os.path.join(
            siabackup.CHECKS_DIR,
            ".check-restic-authority-" + "a" * 32)
        os.mkdir(stage, 0o700)
        siabackup._write_exclusive(
            os.path.join(stage, "repository.key"), b"key=A\n", 0o400)
        siabackup._reconcile_inactive_spools()
        self.assertFalse(os.path.lexists(stage))

    def _restic_executable_swap_case(self, name, phase):
        authority = os.path.join(self.temp.name, "restic-executable-" + name)
        os.mkdir(authority, 0o700)
        key = os.path.join(authority, "repository.key")
        executable = os.path.join(authority, "restic")
        replacement = os.path.join(authority, "restic.next")
        audit = os.path.join(authority, "action")
        siabackup._write_exclusive(key, b"key=A\n")

        def program(label):
            return f'''#!{sys.executable}
import json
import os
import sys

phase = {phase!r}
label = {label!r}
executable = {executable!r}
replacement = {replacement!r}
audit = {audit!r}

def swap():
    os.replace(replacement, executable)

if sys.argv[1:] == ["cat", "config"]:
    if label == "A" and phase == "identity":
        swap()
    print(json.dumps({{"id": {("b" * 64)!r}}}))
    raise SystemExit(0)

if label == "A" and phase == "action":
    swap()
with open(audit, "w", encoding="utf-8") as stream:
    stream.write(label + "\\n")
print("action-" + label)
'''

        siabackup._write_exclusive(
            replacement, program("B").encode(), 0o700)
        siabackup._write_exclusive(
            executable, program("A").encode(), 0o700)
        config = {
            "schema": siabackup.CONFIG_SCHEMA,
            "repository": "rest:https://example.invalid/repository",
            "environment_file": None,
            "repository_id": "b" * 64,
            "brain_public_key": self.public_key,
            "created_at": "2026-09-04T12:00:00Z",
        }
        return config, key, executable, audit

    def test_restic_refuses_executable_swap_after_identity(self):
        config, key, executable, audit = self._restic_executable_swap_case(
            "before-action", "identity")
        with self.assertRaisesRegex(
                siabackup.BlockedError, "repository authority changed"):
            siabackup._run_restic(
                ["snapshots", "--json"], config=config, key_path=key,
                restic_path=executable)
        self.assertFalse(os.path.lexists(audit))
        self.assertEqual(os.listdir(siabackup.CHECKS_DIR), [])

    def test_restic_withholds_result_after_in_action_executable_swap(self):
        config, key, executable, audit = self._restic_executable_swap_case(
            "during-action", "action")
        with self.assertRaisesRegex(
                siabackup.BlockedError, "repository authority changed"):
            siabackup._run_restic(
                ["snapshots", "--json"], config=config, key_path=key,
                restic_path=executable)
        with open(audit, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "A\n")
        self.assertEqual(os.listdir(siabackup.CHECKS_DIR), [])

    def _local_repository_swap_case(self, name, phase):
        authority = os.path.join(self.temp.name, "local-repository-" + name)
        os.mkdir(authority, 0o700)
        repository = os.path.join(authority, "repository")
        replacement = os.path.join(authority, "repository.next")
        displaced = os.path.join(authority, "repository.old")
        os.mkdir(repository, 0o700)
        os.mkdir(replacement, 0o700)
        siabackup._write_exclusive(
            os.path.join(repository, "backend"), b"A\n")
        siabackup._write_exclusive(
            os.path.join(replacement, "backend"), b"B\n")
        key = os.path.join(authority, "repository.key")
        audit = os.path.join(authority, "action")
        fake_restic = os.path.join(authority, "restic")
        siabackup._write_exclusive(key, b"key=A\n")
        source = f'''#!{sys.executable}
import json
import os
import sys

phase = {phase!r}
repository = {repository!r}
replacement = {replacement!r}
displaced = {displaced!r}
audit = {audit!r}

def swap():
    os.rename(repository, displaced)
    os.rename(replacement, repository)

if sys.argv[1:] == ["cat", "config"]:
    if phase == "identity":
        swap()
    print(json.dumps({{"id": {("b" * 64)!r}}}))
    raise SystemExit(0)

if phase == "action":
    swap()
with open(os.path.join(
        os.environ["RESTIC_REPOSITORY"], "backend"),
        encoding="utf-8") as stream:
    backend = stream.read()
with open(audit, "w", encoding="utf-8") as stream:
    stream.write(backend)
print("untrusted-action-result")
'''
        siabackup._write_exclusive(fake_restic, source.encode(), 0o700)
        config = {
            "schema": siabackup.CONFIG_SCHEMA,
            "repository": repository,
            "environment_file": None,
            "repository_id": "b" * 64,
            "brain_public_key": self.public_key,
            "created_at": "2026-09-04T12:00:00Z",
        }
        return config, key, fake_restic, audit

    def test_restic_refuses_local_repository_swap_after_identity(self):
        config, key, fake_restic, audit = self._local_repository_swap_case(
            "before-action", "identity")
        with self.assertRaisesRegex(
                siabackup.BlockedError, "repository authority changed"):
            siabackup._run_restic(
                ["snapshots", "--json"], config=config, key_path=key,
                restic_path=fake_restic)
        self.assertFalse(os.path.lexists(audit))
        self.assertEqual(os.listdir(siabackup.CHECKS_DIR), [])

    def test_restic_withholds_result_after_in_action_repository_swap(self):
        config, key, fake_restic, audit = self._local_repository_swap_case(
            "during-action", "action")
        with self.assertRaisesRegex(
                siabackup.BlockedError, "repository authority changed"):
            siabackup._run_restic(
                ["snapshots", "--json"], config=config, key_path=key,
                restic_path=fake_restic)
        with open(audit, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "A\n")
        self.assertEqual(os.listdir(siabackup.CHECKS_DIR), [])

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
            "id": "a" * 32, "created_at": "2026-09-04T12:00:00Z",
            "action": "apply", "args": {"prepared_id": "d" * 32},
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
            repository_display="External recovery repository",
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
            state="restoring",
            repository_display="External recovery repository",
            latest=self._healthy_latest(),
            operation=siabackup._operation(
                request["id"], "restore-apply", "running",
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
            repository_display="External recovery repository",
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
            "created_at": "2026-09-04T12:00:00Z",
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
expected = {{"capsule_id": "a" * 32, "manifest_sha256": "b" * 64,
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
def verify_snapshot(snapshot_id, *_args, **_kwargs):
    siabackup._record_verification(snapshot_id, expected)
    return expected
siabackup._verify_snapshot_offpath = verify_snapshot
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
                "apply", self._apply_args(), request_id="a" * 32,
                runner=ambiguous,
                prepared_id="d" * 32)
        self.assertTrue(os.path.isfile(
            siabackup._request_path("a" * 32)))
        with open(siabackup.SUPERVISOR_PATH, "rb") as stream:
            self.assertEqual(stream.read(), debt)
        status = siabackup.read_status()
        self.assertEqual(status["state"], "blocked")
        self.assertEqual(status["operation"]["request_id"], "a" * 32)

    def test_failed_liveness_probe_never_retires_worker_authority(self):
        request = siabackup._create_request(
            "upload", {"scheduled": True}, request_id="a" * 32)
        capsule = os.path.join(
            siabackup.CAPSULES_DIR, ".capsule-" + "a" * 32)
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

    def test_inactive_running_requests_are_terminalized_before_retirement(self):
        cases = (
            ("upload", {"scheduled": True}, "capturing", "backup-upload"),
            ("check", {"scheduled": True}, "checking", "backup-check"),
            ("prepare", {"snapshot_id": "abc123"}, "preparing",
             "restore-prepare"),
        )
        for index, (action, args, state, kind) in enumerate(cases):
            with self.subTest(action=action):
                request_id = format(index + 1, "x") * 32
                request = siabackup._create_request(
                    action, args, request_id=request_id)
                siabackup._publish_status(
                    state=state,
                    detail="Continuity worker is running.",
                    repository_display="External recovery repository",
                    operation=siabackup._operation(
                        request_id, kind, "running"))
                with mock.patch.object(
                        siabackup, "_request_id_active",
                        return_value=False):
                    siabackup._reconcile_inactive_spools()
                status = siabackup.read_status()
                self.assertEqual(status["state"], "blocked")
                self.assertEqual(status["operation"]["phase"], "blocked")
                self.assertFalse(os.path.lexists(
                    siabackup._request_path(request["id"])))

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
            }, request_id="a" * 32)
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
            }, request_id="a" * 32)
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

    def test_visible_configuration_after_fsync_error_keeps_replay_authority(self):
        offline = os.path.join(self.temp.name, "offline-config-ambiguity")
        os.mkdir(offline, 0o700)
        recovery = os.path.join(offline, "repository.key")
        identity = os.path.join(offline, "identity.key")
        request = siabackup._create_request(
            "setup", {
                "repository": os.path.join(
                    self.temp.name, "repository-config-ambiguity"),
                "environment_file": None,
                "recovery_key_out": recovery,
                "identity_key_out": identity,
            }, request_id="e" * 32)
        real_fsync_dir = siabackup._fsync_dir
        refused = False

        def fail_after_config_visibility(path):
            nonlocal refused
            if not refused \
                    and os.path.abspath(path) == os.path.abspath(
                        os.path.dirname(siabackup.CONFIG_PATH)) \
                    and os.path.lexists(siabackup.CONFIG_PATH):
                refused = True
                raise OSError("configuration durability is unknown")
            return real_fsync_dir(path)

        def run(arguments, **_kwargs):
            if arguments == ["cat", "config"]:
                return self._repository_config_output()
            return ""

        def export(path):
            siabackup._write_exclusive(path, b"offline-identity\n")

        with mock.patch.object(siabackup, "_run_restic", side_effect=run), \
                mock.patch.object(
                    siabackup.siacapsule, "export_identity_key",
                    side_effect=export), \
                mock.patch.object(
                    siabackup, "_fsync_dir",
                    side_effect=fail_after_config_visibility):
            self.assertEqual(siabackup.run_request(
                siabackup._request_path(request["id"]),
                enable_schedules=lambda: None), 1)
        self.assertTrue(refused)
        self.assertTrue(os.path.isfile(siabackup.CONFIG_PATH))
        self.assertTrue(os.path.isfile(siabackup.KEY_PATH))
        self.assertTrue(os.path.isfile(
            siabackup._request_path(request["id"])))
        self.assertEqual(siabackup.read_status()["state"], "blocked")

        with mock.patch.object(
                siabackup, "_request_id_active", return_value=False), \
                mock.patch.object(
                    siabackup, "_run_restic", side_effect=run), \
                mock.patch.object(siabackup, "_enable_schedules"), \
                mock.patch.object(siabackup, "_start_schedules"), \
                mock.patch.object(
                    siabackup, "_fsync_dir",
                    wraps=real_fsync_dir) as replay_fsync:
            siabackup._reconcile_inactive_spools()
        self.assertTrue(any(
            os.path.abspath(call.args[0]) == os.path.abspath(
                os.path.dirname(siabackup.CONFIG_PATH))
            for call in replay_fsync.call_args_list))
        self.assertFalse(os.path.lexists(
            siabackup._request_path(request["id"])))
        self.assertEqual(siabackup.read_status()["state"], "recovery-only")

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
            ("request-created", "a" * 32),
            ("key-staged", "b" * 32),
            ("recovery-exported", "c" * 32),
            ("identity-exported", "d" * 32),
            ("repository-initialized", "e" * 32),
            ("key-committed", "f" * 32),
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
            }, request_id="d" * 32)
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
                request_id="a" * 32, prepared_id="d" * 32,
                runner=self._runner)
        self.assertEqual(observed, [("restoring", "accepted")])
        self.assertEqual(siabackup.read_status()["state"], "blocked")
        self.assertFalse(os.path.lexists(
            siabackup._request_path("a" * 32)))
        self.assertFalse(os.path.lexists(siabackup.SUPERVISOR_PATH))

    def test_prepared_retirement_withdraws_status_before_tree_deletion(self):
        prepared_id = "d" * 32
        prepared_root = os.path.join(siabackup.PREPARED_DIR, prepared_id)
        os.mkdir(prepared_root, 0o700)
        siabackup._write_exclusive(
            os.path.join(prepared_root, "prepared.json"), b"preserve\n")
        status = self._prepared_status(prepared_id)
        status["latest"] = None
        siabackup._atomic_json(siabackup.STATUS_PATH, status)
        observed = []

        def refuse_retirement(_path, _authority):
            observed.append(siabackup.read_status())
            raise RuntimeError("tree retirement refused")

        with mock.patch.object(
                siabackup, "_retire_private_tree",
                side_effect=refuse_retirement), \
                self.assertRaisesRegex(RuntimeError, "retirement refused"):
            siabackup._retire_current_prepared()
        self.assertIsNone(observed[0]["prepared"])
        self.assertNotEqual(observed[0]["state"], "prepared")
        self.assertTrue(os.path.isdir(prepared_root))

        siabackup._reconcile_inactive_spools()
        self.assertFalse(os.path.lexists(prepared_root))
        self.assertIsNone(siabackup.read_status()["prepared"])

    def test_prepared_withdrawal_failure_preserves_actionable_tree(self):
        prepared_id = "d" * 32
        prepared_root = os.path.join(siabackup.PREPARED_DIR, prepared_id)
        os.mkdir(prepared_root, 0o700)
        siabackup._write_exclusive(
            os.path.join(prepared_root, "prepared.json"), b"preserve\n")
        original = self._prepared_status(prepared_id)
        original["latest"] = None
        siabackup._atomic_json(siabackup.STATUS_PATH, original)

        with mock.patch.object(
                siabackup, "_publish_status",
                side_effect=RuntimeError("status withdrawal refused")), \
                self.assertRaisesRegex(RuntimeError, "withdrawal refused"):
            siabackup._retire_current_prepared()
        self.assertTrue(os.path.isdir(prepared_root))
        self.assertEqual(siabackup.read_status(), original)

    def test_apply_retirement_waits_for_durable_prepared_withdrawal(self):
        prepared_id = "d" * 32
        prepared_root = os.path.join(siabackup.PREPARED_DIR, prepared_id)
        os.mkdir(prepared_root, 0o700)
        siabackup._write_exclusive(
            os.path.join(prepared_root, "prepared.json"), b"preserve\n")
        status = self._prepared_status(prepared_id)
        status["latest"] = None
        siabackup._atomic_json(siabackup.STATUS_PATH, status)
        request = {
            "schema": siabackup.REQUEST_SCHEMA,
            "id": "a" * 32, "created_at": "2026-09-04T12:00:00Z",
            "action": "apply", "args": self._apply_args(),
        }
        publish = siabackup._publish_status

        def refuse_withdrawal(**changes):
            operation = changes.get("operation")
            if changes.get("prepared", object()) is None \
                    and isinstance(operation, dict) \
                    and operation.get("ready") is True:
                raise RuntimeError("status withdrawal refused")
            return publish(**changes)

        with mock.patch.object(
                siabackup, "_perform_apply",
                return_value={"ready": True,
                              "sia_ledger_verified": True}), \
                mock.patch.object(
                    siabackup, "_publish_status",
                    side_effect=refuse_withdrawal), \
                self.assertRaisesRegex(RuntimeError, "withdrawal refused"):
            siabackup._run_request_locked(request, capability={})
        self.assertTrue(os.path.isdir(prepared_root))

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
                request_id="b" * 32, prepared_id="d" * 32,
                runner=self._runner)
        intent.assert_not_called()
        self.assertFalse(os.path.lexists(
            siabackup._request_path("b" * 32)))
        self.assertFalse(os.path.lexists(siabackup.SUPERVISOR_PATH))

    def test_accepted_restore_without_debt_reconciles_non_green(self):
        request = siabackup._create_request(
            "apply", self._apply_args(),
            request_id="c" * 32)
        siabackup._publish_status(
            state="restoring", detail="Continuity request accepted.",
            repository_display="External recovery repository",
            operation=siabackup._operation(
                request["id"], "restore-apply", "accepted",
                prepared_id="d" * 32))
        with mock.patch.object(
                siabackup, "_request_id_active", return_value=False):
            siabackup._reconcile_inactive_spools()
        status = siabackup.read_status()
        self.assertEqual(status["state"], "blocked")
        self.assertEqual(status["operation"]["phase"], "blocked")
        self.assertFalse(os.path.lexists(
            siabackup._request_path(request["id"])))

    def test_upload_adapter_passes_only_completed_capsule_to_restic(self):
        capsule = os.path.join(
            siabackup.CAPSULES_DIR, ".capsule-" + "a" * 32)
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
                siabackup._request_path("a" * 32)))
            self.assertEqual(path, capsule)
            os.mkdir(path)
            return frozen

        request = {
            "schema": siabackup.REQUEST_SCHEMA,
            "id": "a" * 32, "created_at": "2026-09-04T12:00:00Z",
            "action": "upload", "args": {"scheduled": False},
        }
        siabackup._write_exclusive(
            siabackup._request_path("a" * 32),
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
                {"scheduled": False}, "a" * 32)
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
                    "id": "abc123", "time": "2026-09-04T12:00:00Z",
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
            "capsule_id": "a" * 32, "classification": "ready",
            "corpus_head": "c" * 40, "ledger_head": "e" * 64,
            "public_key": self.public_key,
            "manifest_sha256": "b" * 64,
        }
        with mock.patch.object(siabackup, "_resolve_snapshot",
                               return_value="abc123"), \
                mock.patch.object(siabackup, "_run_restic", side_effect=run), \
                mock.patch.object(siabackup.siacapsule, "verify",
                                  return_value=verified), \
                mock.patch.object(siabackup.siacapsule, "identity_matches",
                                  return_value=True), \
                mock.patch.object(siabackup.sialib, "ledger_head",
                                  return_value=(1, "f" * 64)):
            prepared = siabackup._perform_prepare(
                {"snapshot_id": "abc123"}, "request")
        self.assertTrue(observed_target)
        self.assertEqual(
            os.path.commonpath((siabackup.PREPARED_DIR, observed_target[0])),
            siabackup.PREPARED_DIR)
        self.assertTrue(os.path.isfile(
            siabackup._prepared_path(prepared["prepared_id"])))
        self.assertEqual(prepared["target_ledger_head"], "f" * 64)
        self.assertEqual(prepared["ledger_head"], "e" * 64)

    def test_restore_confirmation_is_exact_bounded_one_line(self):
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": "abc123",
            "ledger_head": "f" * 64,
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
        for ambiguous_version in (True, 1.0):
            with self.subTest(schema_version=ambiguous_version), \
                    self.assertRaisesRegex(ValueError, "schema"):
                changed = dict(
                    confirmation, schema_version=ambiguous_version)
                siabackup._read_confirmation(io.BytesIO(
                    json.dumps(changed, separators=(",", ":")).encode()
                    + b"\n"))

    def test_queue_apply_carries_the_stable_launcher_repository_binding(self):
        config = self._configure()
        prepared = {
            "prepared_id": "d" * 32,
            "snapshot_id": "f" * 64,
            "capsule_id": "a" * 32,
            "manifest_sha256": "b" * 64,
            "target_ledger_head": "e" * 64,
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
        target = self._apply_args()["adoption"]["target"]

        def enqueue(action, args, **kwargs):
            captured.update({"action": action, "args": args, **kwargs})
            return {"id": "request"}

        with mock.patch.object(siabackup, "load_prepared",
                               return_value=prepared), \
                mock.patch.object(siabackup.sialib, "ledger_head",
                                  return_value=("sequence", "e" * 64)), \
                mock.patch.object(siabackup.siacapsule, "verify",
                                  return_value={
                                      "capsule_id": prepared["capsule_id"],
                                      "manifest_sha256":
                                          prepared["manifest_sha256"],
                                  }), \
                mock.patch.object(
                    siabackup.siacapsule, "target_identity",
                    return_value=target), \
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
            "identity_key_file": "",
            "accepted_ledger_head": confirmation["ledger_head"],
            "confirmation_sha256": hashlib.sha256(
                siabackup._canonical_bytes(confirmation)).hexdigest(),
            "adoption_order": str(captured["args"]["adoption"]["order"]),
            "adoption_record_id":
                captured["args"]["adoption"]["record_id"],
            "target": target,
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
        request_id = "a" * 32
        request_path = os.path.join(
            launcher_requests, request_id + ".json")
        request = {
            "schema": siabackup.REQUEST_SCHEMA,
            "id": request_id,
            "created_at": "2026-09-04T12:00:00Z",
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
            "snapshot_id": "abc123",
            "ledger_head": "f" * 64,
            "corpus_receipt_re_adopt": True,
        }
        stream = io.BytesIO(
            json.dumps(confirmation, separators=(",", ":")).encode() + b"\n")
        request = {"id": "a" * 32}
        output = io.StringIO()
        with mock.patch.object(siabackup, "queue_apply",
                               return_value=request), \
                mock.patch("sys.stdout", output):
            result = siabackup.cli_restore(
                ["apply", "d" * 32, "--confirm-stdin"], stream)
        self.assertEqual(result, 0)
        acceptance = json.loads(output.getvalue())
        self.assertEqual(acceptance, {
            "schema_version": siabackup.ACCEPTANCE_SCHEMA_VERSION,
            "accepted": True,
            "request_id": "a" * 32,
            "operation": "restore-apply",
            "prepared_id": "d" * 32,
        })

    def test_backend_refuses_green_without_a_concrete_ready_copy(self):
        with self.assertRaisesRegex(ValueError, "concrete ready copy"):
            siabackup._publish_status(state="verified", latest=None)
        empty = self._healthy_latest(snapshot_id="")
        with self.assertRaisesRegex(ValueError, "concrete ready copy"):
            siabackup._publish_status(state="verified", latest=empty)

    def test_empty_checked_repository_clears_prior_green(self):
        self._configure()
        self._ensure_healthy_latest_authority()
        siabackup._publish_status(
            state="verified", latest=self._healthy_latest())
        request = siabackup._create_request(
            "check", {"scheduled": True}, request_id="a" * 32)
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
            "capsule_id": "f" * 32,
            "manifest_sha256": "d" * 64,
            "classification": "ready",
            "public_key": foreign_public,
        })
        response = json.dumps([{
            "id": "fedcba", "time": "2026-09-04T13:00:00Z",
            "tags": [
                "sia-capsule", "sia-readiness=ready",
                "sia-brain=" + foreign_public,
            ],
        }, {
            "id": "abc123", "time": "2026-09-04T12:00:00Z",
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

    def test_malformed_filtered_snapshot_cannot_be_reported_as_absent(self):
        self._configure()
        malformed_rows = (
            "not-a-snapshot-row",
            {"id": "abc123", "time": "2026-09-04T12:00:00Z",
             "tags": []},
            {"id": "abc123", "time": "2026-09-04T12:00:00Z",
             "tags": ["sia-capsule", None]},
        )
        for row in malformed_rows:
            with self.subTest(row=row), mock.patch.object(
                    siabackup, "_run_restic",
                    return_value=json.dumps([row])), \
                    self.assertRaisesRegex(
                        ValueError, "snapshot row is malformed"):
                siabackup._resolve_snapshot("latest")

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

    def test_schedule_status_reports_configured_active_policy(self):
        self._configure()
        systemd_dir, managed_dir = self._managed_schedule_authority()
        fields = {
            "sia-backup.timer": self._schedule_fields(
                systemd_dir, "sia-backup.timer", last="@1700000000",
                next_trigger="@1700003600"),
            "sia-backup-check.timer": self._schedule_fields(
                systemd_dir, "sia-backup-check.timer",
                next_trigger="@1700600000"),
        }
        commands = []

        def systemctl(command, **kwargs):
            self.assertEqual(
                command[:5],
                ["systemctl", "--user", "show", "--timestamp=unix",
                 command[4]])
            self.assertEqual(kwargs["label"],
                             "continuity schedule observation")
            self.assertIn("--property=NeedDaemonReload", command)
            name = command[4]
            commands.append(name)
            stdout = "".join(
                f"{key}={value}\n" for key, value in fields[name].items())
            return subprocess.CompletedProcess(
                command, 0, stdout=stdout, stderr="")

        with mock.patch.object(siabackup, "SYSTEMD_USER_DIR", systemd_dir), \
                mock.patch.object(
                    siabackup, "MANAGED_INSTALL_DIR", managed_dir), \
                mock.patch.object(
                    siabackup, "_attest_continuity_units") as attestor, \
                mock.patch.object(
                    siabackup.sialib, "_run_bounded_text_process",
                    side_effect=systemctl), \
                mock.patch.object(
                    siabackup, "_now", return_value="2026-09-02T20:00:00Z"):
            status = siabackup.schedule_status()

        attestor.assert_called_once_with()
        self.assertEqual(commands, [
            "sia-backup.timer", "sia-backup-check.timer"])
        self.assertEqual(status, {
            "schema_version": siabackup.SCHEDULE_SCHEMA_VERSION,
            "configured": True,
            "automatic": True,
            "observed_at": "2026-09-02T20:00:00Z",
            "upload": {
                "cadence": "hourly",
                "enabled": True,
                "active": True,
                "persistent": True,
                "wake_system": False,
                "last_trigger_at": "2023-11-14T22:13:20Z",
                "next_trigger_at": "2023-11-14T23:13:20Z",
            },
            "verification": {
                "cadence": "weekly",
                "enabled": True,
                "active": True,
                "persistent": True,
                "wake_system": False,
                "last_trigger_at": None,
                "next_trigger_at": "2023-11-21T20:53:20Z",
            },
        })

    def test_schedule_status_is_not_automatic_when_timer_is_inactive(self):
        self._configure()
        upload = {
            "cadence": "hourly", "enabled": True, "active": True,
            "persistent": True, "wake_system": False,
            "last_trigger_at": None, "next_trigger_at": None,
        }
        verification = {
            "cadence": "weekly", "enabled": True, "active": False,
            "persistent": True, "wake_system": False,
            "last_trigger_at": None, "next_trigger_at": None,
        }
        with mock.patch.object(siabackup, "_attest_continuity_units"), \
                mock.patch.object(
                    siabackup, "_timer_schedule_observation",
                    side_effect=[upload, verification]):
            status = siabackup.schedule_status()
        self.assertTrue(status["configured"])
        self.assertFalse(status["automatic"])
        self.assertFalse(status["verification"]["active"])

    def test_schedule_timestamp_is_strict_and_nullable(self):
        self.assertIsNone(siabackup._schedule_timestamp(
            "", "continuity trigger"))
        self.assertEqual(
            siabackup._schedule_timestamp(
                "@1700000000", "continuity trigger"),
            "2023-11-14T22:13:20Z")
        for value in ("1700000000", "@-1", "@1.5", "@1 trailing",
                      "@00", "@01", "@+1", "@\u0661"):
            with self.subTest(value=value), self.assertRaisesRegex(
                    ValueError, "not a systemd Unix timestamp"):
                siabackup._schedule_timestamp(value, "continuity trigger")
        with self.assertRaisesRegex(ValueError, "supported time range"):
            siabackup._schedule_timestamp(
                "@99999999999999999999", "continuity trigger")

    def test_managed_binding_is_tied_to_bytes_actually_read(self):
        systemd_dir, managed_dir = self._managed_schedule_authority()
        name = "sia-backup.timer"
        target = os.path.join(systemd_dir, name)
        real_read = siabackup._read_regular
        replaced = False

        def read_then_replace(path, *args, **kwargs):
            nonlocal replaced
            result = real_read(path, *args, **kwargs)
            if path == target and not replaced:
                raw = result[0] if isinstance(result, tuple) else result
                stage = target + ".replacement"
                siabackup._write_exclusive(stage, raw)
                os.replace(stage, target)
                replaced = True
            return result

        with mock.patch.object(siabackup, "SYSTEMD_USER_DIR", systemd_dir), \
                mock.patch.object(
                    siabackup, "MANAGED_INSTALL_DIR", managed_dir), \
                mock.patch.object(
                    siabackup, "_read_regular", side_effect=read_then_replace), \
                self.assertRaisesRegex(
                    siabackup.BlockedError, "authority changed"):
            siabackup._managed_unit_binding(name, "backup-timer")

    def test_unit_attestation_rechecks_the_complete_authority_set(self):
        systemd_dir, managed_dir = self._managed_schedule_authority()
        first_receipt = os.path.join(
            managed_dir, siabackup._CONTINUITY_UNITS[0][0])

        def fields(name, *, timer):
            if name == siabackup._CONTINUITY_UNITS[-1][0]:
                raw = siabackup._read_regular(
                    first_receipt, "managed receipt", private=True)
                stage = first_receipt + ".replacement"
                siabackup._write_exclusive(stage, raw)
                os.replace(stage, first_receipt)
            value = {
                "LoadState": "loaded",
                "FragmentPath": os.path.join(systemd_dir, name),
                "DropInPaths": "",
                "NeedDaemonReload": "no",
                "ActiveState": "inactive",
                "UnitFileState": "disabled",
                "Job": "",
            }
            if timer:
                value["Unit"] = (
                    "sia-backup-check.service"
                    if name == "sia-backup-check.timer"
                    else "sia-backup.service")
            return value

        with mock.patch.object(siabackup, "SYSTEMD_USER_DIR", systemd_dir), \
                mock.patch.object(
                    siabackup, "MANAGED_INSTALL_DIR", managed_dir), \
                mock.patch.object(
                    siabackup, "_systemd_unit_fields", side_effect=fields), \
                self.assertRaisesRegex(
                    siabackup.BlockedError, "authority changed"):
            siabackup._attest_continuity_units()

    def test_schedule_rechecks_all_units_after_timer_observation(self):
        systemd_dir, managed_dir = self._managed_schedule_authority()
        with mock.patch.object(siabackup, "SYSTEMD_USER_DIR", systemd_dir), \
                mock.patch.object(
                    siabackup, "MANAGED_INSTALL_DIR", managed_dir):
            bindings = tuple(
                siabackup._managed_unit_binding(name, kind)
                for name, kind, _unit_type, _timer_target
                in siabackup._CONTINUITY_UNITS)
        first_unit = os.path.join(
            systemd_dir, siabackup._CONTINUITY_UNITS[0][0])
        timer = {
            "cadence": "hourly", "enabled": False, "active": False,
            "persistent": True, "wake_system": False,
            "last_trigger_at": None, "next_trigger_at": None,
        }

        def observe(_name, cadence, _target, _receipt_kind):
            if cadence == "weekly":
                raw = siabackup._read_regular(first_unit, "managed unit")
                stage = first_unit + ".replacement"
                siabackup._write_exclusive(stage, raw)
                os.replace(stage, first_unit)
            return {**timer, "cadence": cadence}

        with mock.patch.object(siabackup, "SYSTEMD_USER_DIR", systemd_dir), \
                mock.patch.object(
                    siabackup, "MANAGED_INSTALL_DIR", managed_dir), \
                mock.patch.object(
                    siabackup, "_attest_continuity_units",
                    return_value=bindings), \
                mock.patch.object(
                    siabackup, "_timer_schedule_observation",
                    side_effect=observe), \
                self.assertRaisesRegex(
                    siabackup.BlockedError, "authority changed"):
            siabackup.schedule_status()

    def test_request_arguments_are_exact_at_creation_and_load(self):
        valid = {
            "setup": {
                "repository": os.path.join(self.temp.name, "repository"),
                "recovery_key_out": os.path.join(
                    self.temp.name, "recovery.key"),
                "identity_key_out": os.path.join(
                    self.temp.name, "identity.key"),
                "environment_file": None,
            },
            "connect": {
                "repository": os.path.join(self.temp.name, "repository"),
                "recovery_key_file": os.path.join(
                    self.temp.name, "recovery.key"),
                "environment_file": None,
            },
            "upload": {"scheduled": False},
            "check": {"scheduled": True},
            "prepare": {"snapshot_id": "abc123"},
            "apply": self._apply_args(),
        }
        for action, args in valid.items():
            corrupt = {**args, "unexpected": True}
            with self.subTest(action=action, boundary="creation"), \
                    self.assertRaisesRegex(
                        ValueError, "request argument schema"):
                siabackup._create_request(
                    action, corrupt, request_id="a" * 32)
            path = siabackup._request_path("a" * 32)
            self.assertFalse(os.path.lexists(path))

            document = {
                "schema": siabackup.REQUEST_SCHEMA,
                "id": "a" * 32,
                "created_at": "2026-09-04T12:00:00Z",
                "action": action,
                "args": corrupt,
            }
            siabackup._write_exclusive(
                path, siabackup._canonical_bytes(document))
            with self.subTest(action=action, boundary="load"), \
                    self.assertRaisesRegex(
                        ValueError, "request argument schema"):
                siabackup._load_request(path)
            os.unlink(path)

        with self.assertRaisesRegex(ValueError, "request identifier"):
            siabackup._create_request(
                "check", {"scheduled": False}, request_id="a")

        apply_args = self._apply_args()
        identifier_mutations = {
            "prepared_id": "d",
            "snapshot_id": "",
            "capsule_id": "a",
            "manifest_sha256": "b" * 63,
            "repository_id": "b" * 63,
            "target_public_key": "a" * 63,
            "restored_public_key": "a" * 65,
        }
        for key, value in identifier_mutations.items():
            with self.subTest(apply_identifier=key), \
                    self.assertRaisesRegex(
                        ValueError, "restore request binding"):
                siabackup._restore_request_binding({
                    **apply_args, key: value,
                })

    def test_verification_receipt_replay_closes_parent_durability(self):
        config = self._configure()
        verified = {
            "capsule_id": "a" * 32,
            "manifest_sha256": "b" * 64,
            "classification": "ready",
            "public_key": self.public_key,
        }
        real_fsync_dir = siabackup._fsync_dir
        refused = False

        def fail_after_receipt_visibility(path):
            nonlocal refused
            receipt = siabackup._verification_path("abc123")
            if not refused \
                    and os.path.abspath(path) == os.path.abspath(
                        siabackup.VERIFICATIONS_DIR) \
                    and os.path.lexists(receipt):
                refused = True
                raise OSError("receipt durability is unknown")
            return real_fsync_dir(path)

        with mock.patch.object(
                siabackup, "_fsync_dir",
                side_effect=fail_after_receipt_visibility), \
                self.assertRaisesRegex(OSError, "durability is unknown"):
            siabackup._record_verification(
                "abc123", verified, config=config)
        self.assertTrue(refused)

        with mock.patch.object(
                siabackup, "_fsync_dir", wraps=real_fsync_dir) as fsync_dir:
            receipt = siabackup._record_verification(
                "abc123", verified, config=config)
        self.assertEqual(receipt["snapshot_id"], "abc123")
        self.assertTrue(any(
            os.path.abspath(call.args[0]) == os.path.abspath(
                siabackup.VERIFICATIONS_DIR)
            for call in fsync_dir.call_args_list))

    def test_every_verified_latest_row_requires_durable_receipt_authority(self):
        config = self._configure()
        latest = self._healthy_latest()
        siabackup._record_verification(latest["snapshot_id"], {
            "capsule_id": "a" * 32,
            "manifest_sha256": "b" * 64,
            "classification": "ready",
            "public_key": self.public_key,
        }, config=config)
        siabackup._publish_status(state="verified", latest=latest)
        verified_status = siabackup.read_status()
        verification_path = siabackup._verification_path(
            latest["snapshot_id"])
        siabackup._retire_private_file(
            verification_path, siabackup.VERIFICATIONS_DIR)

        with self.assertRaisesRegex(ValueError, "receipt authority"):
            siabackup.read_status()
        with self.assertRaisesRegex(ValueError, "receipt authority"):
            siabackup._publish_status(
                detail="A missing receipt cannot preserve a green claim.")

        checking_status = {
            **verified_status,
            "state": "checking",
            "detail": "Repository verification is running.",
            "operation": siabackup._operation(
                "c" * 32, "backup-check", "running"),
        }
        siabackup._atomic_json(siabackup.STATUS_PATH, checking_status)
        with self.assertRaisesRegex(ValueError, "receipt authority"):
            siabackup.read_status()
        with self.assertRaisesRegex(ValueError, "receipt authority"):
            siabackup._publish_status(
                detail="A busy state cannot launder a missing receipt.")
        with self.assertRaisesRegex(ValueError, "receipt authority"):
            siabackup._publish_status(
                state="recovery-only", latest=None, operation=None,
                detail="A mutation cannot erase unauthenticated history.")

    def test_restore_worker_refuses_same_content_request_replacement(self):
        request, debt = self._apply_request_and_debt(
            phase="child-running")
        request_path = debt["request_path"]
        raw = siabackup._read_regular(
            request_path, "restore request", private=True)
        stage = os.path.join(siabackup.REQUESTS_DIR, ".replacement")
        siabackup._write_exclusive(stage, raw)
        os.replace(stage, request_path)
        siabackup._fsync_dir(siabackup.REQUESTS_DIR)

        with self.assertRaisesRegex(
                siabackup.BlockedError, "generation changed"):
            siabackup.run_restore_request(request_path, lifecycle_fd=None)

    def test_request_created_at_is_a_canonical_producer_timestamp(self):
        path = siabackup._request_path("a" * 32)
        base = {
            "schema": siabackup.REQUEST_SCHEMA,
            "id": "a" * 32,
            "created_at": "2026-09-04T12:00:00Z",
            "action": "check",
            "args": {"scheduled": False},
        }
        siabackup._write_exclusive(
            path, siabackup._canonical_bytes(base))
        self.assertEqual(siabackup._load_request(path), base)

        for created_at in (
                {"looks": "timestamp-like"}, "test-time",
                "2026-09-04T12:00:00.0Z",
                "2026-09-04T08:00:00-04:00", ""):
            with self.subTest(created_at=created_at):
                siabackup._atomic_json(
                    path, {**base, "created_at": created_at})
                with self.assertRaisesRegex(
                        ValueError, "request schema is invalid"):
                    siabackup._load_request(path)

    def test_durable_continuity_timestamps_are_canonical(self):
        config = self._configure()
        canonical = "2026-09-04T12:00:00Z"

        siabackup._atomic_json(
            siabackup.CONFIG_PATH,
            {**config, "created_at": "2026-09-04T12:00:00.0Z"})
        with self.assertRaisesRegex(ValueError, "configuration timestamp"):
            siabackup.load_config()
        siabackup._atomic_json(
            siabackup.CONFIG_PATH, {**config, "created_at": canonical})
        config = siabackup.load_config()

        with self.assertRaisesRegex(ValueError, "configuration timestamp"):
            siabackup._restore_request_binding({
                **self._apply_args(),
                "configured_at": "2026-09-04T08:00:00-04:00",
            })

        prepared_id = "d" * 32
        prepared_root = os.path.join(
            siabackup.PREPARED_DIR, prepared_id)
        os.mkdir(prepared_root, 0o700)
        prepared = {
            "schema": siabackup.siacapsule.PREPARED_SCHEMA,
            "prepared_id": prepared_id,
            "snapshot_id": "abc123",
            "capsule_id": "a" * 32,
            "created_at": "not-a-time",
            "classification": "ready",
            "profile": siabackup.PROFILE,
            "corpus_head": "c" * 64,
            "ledger_head": "e" * 64,
            "target_ledger_head": "f" * 64,
            "identity_matches": True,
            "public_key": self.public_key,
            "manifest_sha256": "b" * 64,
            "capsule_path": os.path.join(prepared_root, "capsule"),
        }
        siabackup._write_exclusive(
            os.path.join(prepared_root, "prepared.json"),
            siabackup._canonical_bytes(prepared))
        with self.assertRaisesRegex(ValueError, "created timestamp"):
            siabackup.load_prepared(prepared_id)

        siabackup._record_verification("fedcba", {
            "capsule_id": "a" * 32,
            "manifest_sha256": "b" * 64,
            "classification": "ready",
            "public_key": self.public_key,
        }, config=config)
        verification_path = siabackup._verification_path("fedcba")
        verification = siabackup._read_json(
            verification_path, "snapshot verification")
        siabackup._atomic_json(
            verification_path,
            {**verification, "verified_at": {"not": "a timestamp"}})
        with self.assertRaisesRegex(ValueError, "verification timestamp"):
            siabackup._load_verification("fedcba", config=config)

        request, debt = self._apply_request_and_debt()
        siabackup._atomic_json(
            siabackup.SUPERVISOR_PATH,
            {**debt, "configured_at": "not-a-time"})
        with self.assertRaisesRegex(ValueError, "configured timestamp"):
            siabackup.load_supervisor_debt()

        siabackup._retire_private_file(
            siabackup.SUPERVISOR_PATH, siabackup.ROOT)
        recovery = self._recovery_debt()
        siabackup._atomic_json(
            siabackup.SUPERVISOR_PATH,
            {**recovery, "request_id": "a"})
        with self.assertRaisesRegex(ValueError, "binding is invalid"):
            siabackup.load_supervisor_debt()

    def test_identity_adoption_rebinds_prior_latest_before_finalization(self):
        config = self._configure()
        prior_latest = self._healthy_latest()
        siabackup._record_verification(prior_latest["snapshot_id"], {
            "capsule_id": "a" * 32,
            "manifest_sha256": "b" * 64,
            "classification": "ready",
            "public_key": self.public_key,
        })
        restored_public = "c" * 64
        request, debt = self._apply_request_and_debt(
            restored_public_key=restored_public)
        siabackup._publish_status(
            state="restoring",
            repository_display="External recovery repository",
            latest=prior_latest,
            operation=siabackup._operation(
                request["id"], "restore-apply", "running",
                prepared_id=debt["prepared_id"], ready=True,
                sia_ledger_verified=True))

        with mock.patch.object(
                siabackup, "_live_brain_public_key",
                return_value=restored_public):
            siabackup._rebind_after_identity_adoption(
                config, restored_public)
            rebound = siabackup.read_status()
            self.assertIsNone(rebound["latest"])
            with mock.patch.object(
                    siabackup, "_post_restart_observation",
                    return_value={
                        "ready": True,
                        "sia_ledger_verified": True,
                        "committed": True,
                    }):
                self.assertTrue(siabackup.finalize_restore_request(
                    debt["request_path"]))
        terminal = siabackup.read_status()
        self.assertEqual(terminal["state"], "recovery-only")
        self.assertIsNone(terminal["latest"])

    def test_schedule_field_reader_refuses_malformed_manager_output(self):
        responses = (
            ("LoadState=loaded\n", "incomplete"),
            ("LoadState=loaded\nLoadState=loaded\n", "repeats a field"),
            ("not-a-field\n", "malformed"),
        )
        for stdout, message in responses:
            with self.subTest(message=message), mock.patch.object(
                    siabackup.sialib, "_run_bounded_text_process",
                    return_value=subprocess.CompletedProcess(
                        [], 0, stdout=stdout, stderr="")), \
                    self.assertRaisesRegex(ValueError, message):
                siabackup._systemd_schedule_fields("sia-backup.timer")
        with mock.patch.object(
                siabackup.sialib, "_run_bounded_text_process",
                return_value=subprocess.CompletedProcess(
                    [], 1, stdout="", stderr="refused")), \
                self.assertRaisesRegex(
                    siabackup.BlockedError, "observation failed"):
            siabackup._systemd_schedule_fields("sia-backup.timer")

    def test_schedule_observation_refuses_dropin_and_generation_change(self):
        systemd_dir, managed_dir = self._managed_schedule_authority()
        name = "sia-backup.timer"
        foreign = self._schedule_fields(
            systemd_dir, name, drop_in="/foreign.conf")
        current = self._schedule_fields(systemd_dir, name)
        with mock.patch.object(siabackup, "SYSTEMD_USER_DIR", systemd_dir), \
                mock.patch.object(
                    siabackup, "MANAGED_INSTALL_DIR", managed_dir):
            with mock.patch.object(
                    siabackup, "_systemd_schedule_fields",
                    return_value=foreign), \
                    self.assertRaisesRegex(
                        siabackup.BlockedError, "authority is not exact"):
                siabackup._timer_schedule_observation(
                    name, "hourly", "sia-backup.service", "backup-timer")
            binding = siabackup._managed_unit_binding(name, "backup-timer")
            with mock.patch.object(
                    siabackup, "_systemd_schedule_fields",
                    return_value=current), \
                    mock.patch.object(
                        siabackup, "_managed_unit_binding",
                        return_value=binding), \
                    mock.patch.object(
                        siabackup, "_generation",
                        return_value="changed-generation"), \
                    self.assertRaisesRegex(
                        siabackup.BlockedError,
                        "authority changed during observation"):
                siabackup._timer_schedule_observation(
                    name, "hourly", "sia-backup.service", "backup-timer")

    def test_schedule_status_refuses_partial_configuration(self):
        self._configure()
        observe = mock.Mock()
        with mock.patch.object(
                siabackup, "_timer_schedule_observation", observe):
            os.unlink(siabackup.KEY_PATH)
            with self.assertRaisesRegex(
                    siabackup.BlockedError, "configuration.*incomplete"):
                siabackup.schedule_status()
            os.unlink(siabackup.CONFIG_PATH)
            siabackup._write_exclusive(
                siabackup.KEY_PATH, b"recovery-key\n")
            with self.assertRaisesRegex(
                    siabackup.BlockedError, "configuration.*incomplete"):
                siabackup.schedule_status()
        observe.assert_not_called()

    def test_schedule_status_refuses_configuration_generation_change(self):
        self._configure()
        timer = {
            "cadence": "hourly", "enabled": True, "active": True,
            "persistent": True, "wake_system": False,
            "last_trigger_at": None, "next_trigger_at": None,
        }
        replaced = False

        def observe(_name, cadence, _target, _receipt_kind):
            nonlocal replaced
            if not replaced:
                with open(siabackup.CONFIG_PATH, "rb") as stream:
                    raw = stream.read()
                stage = siabackup.CONFIG_PATH + ".replacement"
                siabackup._write_exclusive(stage, raw)
                os.replace(stage, siabackup.CONFIG_PATH)
                replaced = True
            return {**timer, "cadence": cadence}

        with mock.patch.object(siabackup, "_attest_continuity_units"), \
                mock.patch.object(
                    siabackup, "_timer_schedule_observation",
                    side_effect=observe), \
                self.assertRaisesRegex(
                    siabackup.BlockedError,
                    "configuration changed during schedule observation"):
            siabackup.schedule_status()

    def test_schedule_status_refuses_foreign_target_service(self):
        self._configure()
        systemd_dir, managed_dir = self._managed_schedule_authority()

        def fields(name, *, timer):
            value = {
                "LoadState": "loaded",
                "FragmentPath": os.path.join(systemd_dir, name),
                "DropInPaths": (
                    "/foreign.conf" if name == "sia-backup.service" else ""),
                "NeedDaemonReload": "no",
                "ActiveState": "inactive",
                "UnitFileState": "disabled",
                "Job": "",
            }
            if timer:
                value["Unit"] = (
                    "sia-backup-check.service"
                    if name == "sia-backup-check.timer"
                    else "sia-backup.service")
            return value

        observe = mock.Mock()
        with mock.patch.object(siabackup, "SYSTEMD_USER_DIR", systemd_dir), \
                mock.patch.object(
                    siabackup, "MANAGED_INSTALL_DIR", managed_dir), \
                mock.patch.object(
                    siabackup, "_systemd_unit_fields", side_effect=fields), \
                mock.patch.object(
                    siabackup, "_timer_schedule_observation", observe), \
                self.assertRaisesRegex(
                    siabackup.BlockedError, "authority is not exact"):
            siabackup.schedule_status()
        observe.assert_not_called()

    def test_effective_units_refuse_pending_daemon_reload(self):
        systemd_dir, managed_dir = self._managed_schedule_authority()

        def fields(name, *, timer):
            value = {
                "LoadState": "loaded",
                "FragmentPath": os.path.join(systemd_dir, name),
                "DropInPaths": "",
                "NeedDaemonReload": (
                    "yes" if name == "sia-backup.service" else "no"),
                "ActiveState": "inactive",
                "UnitFileState": "disabled",
                "Job": "",
            }
            if timer:
                value["Unit"] = (
                    "sia-backup-check.service"
                    if name == "sia-backup-check.timer"
                    else "sia-backup.service")
            return value

        with mock.patch.object(
                siabackup, "SYSTEMD_USER_DIR", systemd_dir), \
                mock.patch.object(
                    siabackup, "MANAGED_INSTALL_DIR", managed_dir), \
                mock.patch.object(
                    siabackup, "_systemd_unit_fields",
                    side_effect=fields), \
                self.assertRaisesRegex(
                    siabackup.BlockedError, "authority is not exact"):
            siabackup._attest_continuity_units()

    def test_schedule_cli_emits_machine_readable_status(self):
        payload = {
            "schema_version": siabackup.SCHEDULE_SCHEMA_VERSION,
            "configured": True,
            "automatic": True,
            "observed_at": "2026-09-02T20:00:00Z",
            "upload": {"cadence": "hourly"},
            "verification": {"cadence": "weekly"},
        }
        output = io.StringIO()
        with mock.patch.object(
                siabackup, "schedule_status", return_value=payload) as status, \
                mock.patch("sys.stdout", output):
            result = siabackup.cli_backup(["schedule"])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue()), payload)
        status.assert_called_once_with()

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
                    "NeedDaemonReload": "no",
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
            state="restoring",
            repository_display="External recovery repository",
            latest=self._healthy_latest(),
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
        self.assertEqual(status["state"], "blocked")
        self.assertTrue(os.path.isfile(siabackup.SUPERVISOR_PATH))

    def test_apply_finalizer_withholds_green_until_debt_unlink_is_durable(self):
        request, debt = self._apply_request_and_debt()
        siabackup._publish_status(
            state="restoring",
            repository_display="External recovery repository",
            latest=self._healthy_latest(),
            operation=siabackup._operation(
                request["id"], "restore-apply", "running",
                prepared_id=debt["prepared_id"], ready=True,
                sia_ledger_verified=True))
        real_os = siabackup.os

        class OsShim:
            def __getattr__(self, name):
                return getattr(real_os, name)

            @staticmethod
            def fsync(descriptor):
                if not os.path.lexists(siabackup.SUPERVISOR_PATH):
                    raise OSError("supervisor unlink durability unknown")
                return real_os.fsync(descriptor)

        with mock.patch.object(
                siabackup, "_post_restart_observation",
                return_value={
                    "ready": True, "sia_ledger_verified": True,
                    "committed": True,
                }), mock.patch.object(siabackup, "os", OsShim()), \
                self.assertRaisesRegex(OSError, "unlink durability unknown"):
            siabackup.finalize_restore_request(debt["request_path"])
        self.assertEqual(siabackup.read_status()["state"], "blocked")
        self.assertFalse(os.path.lexists(siabackup.SUPERVISOR_PATH))
        self.assertTrue(siabackup.reconcile_supervisor_spools())

    def test_recovery_finalizer_withholds_green_until_debt_unlink_is_durable(self):
        debt = self._recovery_debt()
        siabackup._publish_status(
            state="restoring",
            repository_display="External recovery repository",
            latest=self._healthy_latest(),
            operation=siabackup._operation(
                debt["request_id"], "restore-recover", "running",
                ready=True, sia_ledger_verified=True))
        real_os = siabackup.os

        class OsShim:
            def __getattr__(self, name):
                return getattr(real_os, name)

            @staticmethod
            def fsync(descriptor):
                if not os.path.lexists(siabackup.SUPERVISOR_PATH):
                    raise OSError("supervisor unlink durability unknown")
                return real_os.fsync(descriptor)

        with mock.patch.object(
                siabackup, "_post_restart_observation",
                return_value={
                    "ready": True, "sia_ledger_verified": True,
                    "committed": None,
                }), mock.patch.object(siabackup, "os", OsShim()), \
                self.assertRaisesRegex(OSError, "unlink durability unknown"):
            siabackup.finalize_restore_recovery()
        self.assertEqual(siabackup.read_status()["state"], "blocked")
        self.assertFalse(os.path.lexists(siabackup.SUPERVISOR_PATH))
        self.assertTrue(siabackup.reconcile_supervisor_spools())

    def test_terminal_publication_ambiguity_restores_non_green_fallback(self):
        request, debt = self._apply_request_and_debt()
        siabackup._publish_status(
            state="restoring",
            repository_display="External recovery repository",
            latest=self._healthy_latest(),
            operation=siabackup._operation(
                request["id"], "restore-apply", "running",
                prepared_id=debt["prepared_id"], ready=True,
                sia_ledger_verified=True))
        real_fsync_dir = siabackup._fsync_dir
        failed = False

        def fail_once_after_terminal_rename(path):
            nonlocal failed
            if not failed:
                try:
                    phase = siabackup.read_status()["operation"]["phase"]
                except (OSError, TypeError, ValueError):
                    phase = ""
                if phase == "verified":
                    failed = True
                    raise OSError("terminal durability is unknown")
            return real_fsync_dir(path)

        observation = {
            "ready": True, "sia_ledger_verified": True,
            "committed": True,
        }
        with mock.patch.object(
                siabackup, "_post_restart_observation",
                return_value=observation), mock.patch.object(
                    siabackup, "_fsync_dir",
                    side_effect=fail_once_after_terminal_rename), \
                self.assertRaisesRegex(OSError, "durability is unknown"):
            siabackup.finalize_restore_request(debt["request_path"])
        self.assertFalse(os.path.lexists(siabackup.SUPERVISOR_PATH))
        self.assertEqual(siabackup.read_status()["state"], "blocked")
        self.assertTrue(siabackup.reconcile_supervisor_spools())

    def test_restart_failure_downgrades_after_request_retirement(self):
        request, debt = self._apply_request_and_debt()
        siabackup._publish_status(
            state="restoring",
            repository_display="External recovery repository",
            latest=self._healthy_latest(),
            operation=siabackup._operation(
                request["id"], "restore-apply", "running",
                prepared_id=debt["prepared_id"], ready=True,
                sia_ledger_verified=True))
        debt["phase"] = "restart-failed"
        siabackup._atomic_json(siabackup.SUPERVISOR_PATH, debt)
        siabackup._retire_request(request)

        self.assertTrue(
            siabackup.mark_brainstem_restart_failed(debt["request_path"]))
        status = siabackup.read_status()
        self.assertEqual(status["state"], "blocked")
        self.assertEqual(status["operation"]["phase"], "blocked")

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
        request_id = "a" * 32
        request_path = os.path.join(requests, request_id + ".json")
        request = {
            "schema": siabackup.REQUEST_SCHEMA,
            "id": request_id,
            "created_at": "2026-09-04T12:00:00Z",
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
        self.assertEqual(status["operation"]["request_id"], request_id)
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


class PostRestartResidentProof(unittest.TestCase):
    """Real /proc coverage for the post-restart resident-brainstem proof.

    ``_post_restart_observation`` is the only thing standing between a
    half-finished restore and a green light: it binds the systemd-reported
    MainPID to that PID's own ``/proc`` cmdline and ``exe``, and re-reads the
    PID after the observation so a daemon that restarted mid-attestation
    cannot be laundered into success.  Every supervisor test in this file
    replaces the whole function with a dict, so the proof itself had no
    behavioural coverage at all.  These tests drive it against real child
    processes whose /proc entries are genuinely readable.
    """

    SCRIPT = ("import sys\n"
              "sys.stdout.write('ready\\n')\n"
              "sys.stdout.flush()\n"
              "sys.stdin.read()\n")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sia-restart-test-")
        self.addCleanup(self.temp.cleanup)
        self.bin = os.path.join(self.temp.name, "bin")
        os.makedirs(self.bin, mode=0o700)
        # The proof resolves the expected program against sialib.BIN, so the
        # fixture's installed-runtime directory has to stand in for it.
        patcher = mock.patch.object(siabackup.sialib, "BIN", self.bin)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.report = {"ActiveState": "active", "MainPID": "0"}
        self.returncode = 0
        systemctl = mock.patch.object(
            siabackup.sialib, "_run_bounded_text_process",
            side_effect=self._systemctl)
        systemctl.start()
        self.addCleanup(systemctl.stop)

    def _systemctl(self, command, **_kwargs):
        """Stand in for the systemd query only; /proc stays real."""
        self.assertEqual(command[:2], ["systemctl", "--user"])
        stdout = "".join(
            f"{key}={value}\n" for key, value in self.report.items())
        return subprocess.CompletedProcess(
            command, self.returncode, stdout=stdout, stderr="")

    @staticmethod
    def _reap(process):
        try:
            if not process.stdin.closed:
                process.stdin.close()
            process.wait(timeout=10)
        except Exception:
            process.kill()
            process.wait(timeout=10)
        finally:
            process.stdout.close()

    def _spawn(self, *, program="sia-brainstem.py", argv0=None,
               executable=None):
        script = os.path.join(self.bin, program)
        if not os.path.lexists(script):
            with open(script, "w", encoding="ascii") as stream:
                stream.write(self.SCRIPT)
            os.chmod(script, 0o600)
        environment = dict(os.environ)
        if executable is not None:
            # A copied interpreter still needs the real stdlib prefix; only
            # the /proc/<pid>/exe path is under test here.
            environment["PYTHONHOME"] = sys.prefix
        process = subprocess.Popen(
            [argv0 or sys.executable, script], executable=executable,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, env=environment)
        self.addCleanup(self._reap, process)
        # Read the child's own handshake so the exec has certainly happened
        # before anything reads its /proc entries.
        self.assertEqual(process.stdout.readline(), "ready\n")
        return process

    def _attest(self, process):
        self.report["MainPID"] = str(process.pid)
        return {"kind": "restore-apply", "prepared_id": "d" * 32,
                "capsule_id": "a" * 32, "restart_pid": str(process.pid)}

    def test_post_restart_proof_accepts_one_stable_matching_resident(self):
        process = self._spawn()
        debt = self._attest(process)
        observation = {"ready": True, "sia_ledger_verified": True,
                       "committed": True}
        with mock.patch.object(
                siabackup, "_live_restore_observation",
                return_value=observation) as observed:
            self.assertEqual(
                siabackup._post_restart_observation(debt), observation)
        observed.assert_called_once_with(debt)

    def test_post_restart_proof_refuses_a_resident_that_restarted(self):
        first = self._spawn()
        debt = self._attest(first)
        replacements = []

        def restart_midway(_debt):
            # The daemon dies and systemd replaces it while the signed
            # observation is being taken: the proof must not carry the
            # earlier PID's evidence over to the new process.
            self._reap(first)
            second = self._spawn()
            replacements.append(second)
            self.report["MainPID"] = str(second.pid)
            return {"ready": True, "sia_ledger_verified": True,
                    "committed": True}

        with mock.patch.object(
                siabackup, "_live_restore_observation",
                side_effect=restart_midway):
            self.assertIsNone(siabackup._post_restart_observation(debt))
        self.assertEqual(len(replacements), 1)

    def test_post_restart_proof_refuses_a_pid_the_debt_never_attested(self):
        attested = self._spawn()
        debt = self._attest(attested)
        other = self._spawn(program="sia-brainstem.py")
        self.report["MainPID"] = str(other.pid)
        with mock.patch.object(
                siabackup, "_live_restore_observation") as observed:
            self.assertIsNone(siabackup._post_restart_observation(debt))
        observed.assert_not_called()

    def test_post_restart_proof_refuses_a_resident_running_another_program(
            self):
        process = self._spawn(program="sia-thoughts.py")
        debt = self._attest(process)
        with mock.patch.object(
                siabackup, "_live_restore_observation") as observed:
            self.assertIsNone(siabackup._post_restart_observation(debt))
        observed.assert_not_called()

    def test_post_restart_proof_refuses_a_forged_interpreter_argv(self):
        forged = os.path.join(self.temp.name, "not-the-interpreter")
        process = self._spawn(argv0=forged, executable=sys.executable)
        debt = self._attest(process)
        with mock.patch.object(
                siabackup, "_live_restore_observation") as observed:
            self.assertIsNone(siabackup._post_restart_observation(debt))
        observed.assert_not_called()

    def test_post_restart_proof_refuses_an_exe_that_is_not_the_interpreter(
            self):
        # argv can be written by anyone who can exec; /proc/<pid>/exe cannot.
        # A copied interpreter presents a truthful-looking cmdline and the
        # wrong executable, which is exactly what the exe check exists for.
        copy = os.path.join(self.temp.name, "impostor-python")
        shutil.copy2(os.path.realpath(sys.executable), copy)
        process = self._spawn(executable=copy)
        debt = self._attest(process)
        with mock.patch.object(
                siabackup, "_live_restore_observation") as observed:
            self.assertIsNone(siabackup._post_restart_observation(debt))
        observed.assert_not_called()

    def test_post_restart_proof_refuses_unusable_unit_reports(self):
        process = self._spawn()
        debt = self._attest(process)
        live = str(process.pid)
        reports = (
            {"ActiveState": "inactive", "MainPID": live},
            {"ActiveState": "activating", "MainPID": live},
            {"ActiveState": "active", "MainPID": "0"},
            {"ActiveState": "active", "MainPID": ""},
            {"ActiveState": "active", "MainPID": " " + live},
            {"ActiveState": "active"},
            {"ActiveState": "active", "MainPID": live, "Extra": "1"},
        )
        with mock.patch.object(
                siabackup, "_live_restore_observation") as observed:
            for report in reports:
                with self.subTest(report=report):
                    self.report = report
                    self.assertIsNone(
                        siabackup._post_restart_observation(debt))
            self.returncode = 1
            self.report = {"ActiveState": "active", "MainPID": live}
            self.assertIsNone(siabackup._post_restart_observation(debt))
        observed.assert_not_called()


class RestoreAdoptionCommitment(unittest.TestCase):
    """Real signed-ledger coverage for the "committed" determination.

    ``_live_restore_observation`` decides whether a restore actually adopted
    the recovered identity by scanning the verified SIA ledger for exactly
    one ``RESTORE:adopt`` row bound to this prepared/capsule pair.  A green
    restore hangs off that one boolean, yet every test that reached it did so
    through a mocked observation, so neither the exact match nor the
    ambiguity refusal was ever executed.  These tests build genuine signed
    ledgers with bin/sia-ledger and let the real scan read them.
    """

    PREPARED_ID = "d" * 32
    CAPSULE_ID = "a" * 32
    CONTENT = "0" * 64

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sia-adopt-test-")
        self.addCleanup(self.temp.cleanup)
        self.share = os.path.join(self.temp.name, "share")
        os.makedirs(self.share, mode=0o700)
        self._ledger("init")
        _sequence, self.accepted_head = self._head()
        for name, value in (("SHARE", self.share),
                            ("BIN", os.path.join(REPO, "bin"))):
            patcher = mock.patch.object(siabackup.sialib, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        # Readiness is a separate live property; pin it so these tests speak
        # only about the signed adoption transition.
        readiness = mock.patch.object(
            siabackup.sialib, "memory_readiness",
            return_value=(True, "ready"))
        readiness.start()
        self.addCleanup(readiness.stop)

    def _ledger(self, command, *arguments):
        result = subprocess.run(
            [sys.executable, os.path.join(REPO, "bin", "sia-ledger"),
             command, self.share, *arguments],
            capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def _head(self):
        sequence, head = self._ledger("head").strip().split()
        return int(sequence), head

    def _adopt(self, *, prepared_id=None, capsule_id=None, debt=None,
               unbound=False):
        debt = self._debt() if debt is None else debt
        digest, size = siabackup._expected_adoption_ledger_binding(debt)
        if unbound:
            digest, size = self.CONTENT, "0"
        self._ledger("append", "RESTORE:adopt",
                     prepared_id or self.PREPARED_ID,
                     capsule_id or self.CAPSULE_ID, digest, size)

    def _debt(self, *, accepted_head=None):
        accepted_head = accepted_head or self.accepted_head
        prepared = {
            "prepared_id": self.PREPARED_ID,
            "snapshot_id": "b" * 64,
            "capsule_id": self.CAPSULE_ID,
            "manifest_sha256": "c" * 64,
        }
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": prepared["snapshot_id"],
            "ledger_head": accepted_head,
            "corpus_receipt_re_adopt": True,
        }
        target = {
            "corpus_root": {
                "device": 1, "inode": 2, "mode": 448, "owner": 0,
            },
            "receipt_sha256": "e" * 64,
            "receipt_mode": 384,
        }
        adoption = siabackup.siacapsule.adoption_binding(
            prepared, confirmation, target, order=7)
        return {
            "kind": "restore-apply",
            **prepared,
            "accepted_ledger_head": accepted_head,
            "confirmation_sha256": hashlib.sha256(
                siabackup._canonical_bytes(confirmation)).hexdigest(),
            "adoption_order": str(adoption["order"]),
            "adoption_record_id": adoption["record_id"],
            "target": target,
        }

    def test_adoption_is_uncommitted_without_a_signed_adopt_row(self):
        observed = siabackup._live_restore_observation(self._debt())
        self.assertTrue(observed["sia_ledger_verified"])
        self.assertIs(observed["committed"], False)
        self.assertEqual(observed["ledger_sequence"], 1)

    def test_adoption_is_committed_by_its_exact_signed_row(self):
        self._adopt()
        observed = siabackup._live_restore_observation(self._debt())
        self.assertTrue(observed["sia_ledger_verified"])
        self.assertIs(observed["committed"], True)
        self.assertEqual(observed["ledger_sequence"], 2)

    def test_adoption_refuses_a_signed_row_with_unbound_content(self):
        self._adopt(unbound=True)
        observed = siabackup._live_restore_observation(self._debt())
        self.assertIs(observed["committed"], False)

    def test_adoption_refuses_a_mismatched_accepted_predecessor(self):
        debt = self._debt(accepted_head="f" * 64)
        self._adopt(debt=debt)
        with self.assertRaisesRegex(ValueError, "accepted predecessor"):
            siabackup._live_restore_observation(debt)

    def test_adoption_ignores_rows_bound_to_another_restore(self):
        self._adopt(prepared_id="e" * 32)
        self._adopt(capsule_id="b" * 32)
        self._ledger("append", "RESTORE:intent", self.PREPARED_ID,
                     self.CAPSULE_ID, self.CONTENT, "0")
        observed = siabackup._live_restore_observation(self._debt())
        self.assertIs(observed["committed"], False)
        self.assertEqual(observed["ledger_sequence"], 4)

    def test_adoption_ambiguity_refuses_instead_of_guessing(self):
        self._adopt()
        self._adopt()
        with self.assertRaisesRegex(
                ValueError, "restore adoption transition is ambiguous"):
            siabackup._live_restore_observation(self._debt())

    def test_adoption_is_undetermined_without_apply_debt(self):
        self._adopt()
        for debt in (None, {"kind": "restore-recover"}):
            with self.subTest(debt=debt):
                observed = siabackup._live_restore_observation(debt)
                self.assertIsNone(observed["committed"])

    def test_observation_blocks_when_the_generation_moves_underneath_it(self):
        self._adopt()
        real_health = siabackup.siacapsule._health_observation

        def append_during_health():
            # A concurrent signed append is exactly the race the before/after
            # head comparison exists to catch: the scanned bytes would no
            # longer describe the generation the attestation reports.
            observation = real_health()
            self._ledger("append", "PULSE:tick", "sia", "-",
                         self.CONTENT, "0")
            return observation

        with mock.patch.object(
                siabackup.siacapsule, "_health_observation",
                side_effect=append_during_health):
            with self.assertRaisesRegex(
                    siabackup.BlockedError, "generation changed"):
                siabackup._live_restore_observation(self._debt())

    def test_observation_refuses_a_target_with_no_generation_head(self):
        empty = os.path.join(self.temp.name, "no-ledger")
        os.makedirs(empty, mode=0o700)
        with mock.patch.object(siabackup.sialib, "SHARE", empty):
            with self.assertRaisesRegex(
                    ValueError, "no nonempty generation head"):
                siabackup._live_restore_observation(self._debt())


if __name__ == "__main__":
    unittest.main()
