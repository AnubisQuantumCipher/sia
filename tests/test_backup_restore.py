import contextlib
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

try:
    import sia_test_home  # noqa: F401  (patch HOME before runtime imports)
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore  # noqa: F401


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin")
if BIN not in sys.path:
    sys.path.insert(0, BIN)

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)

import sialib
import siacapsule


@contextlib.contextmanager
def _owned_corpus():
    yield 7


class CapsuleBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = tempfile.TemporaryDirectory(prefix="sia-capsule-test-")
        self.home = self.fixture.name
        self.share = os.path.join(self.home, "share")
        self.state = os.path.join(self.home, "state")
        self.corpus = os.path.join(self.share, "corpus")
        self.config = os.path.join(self.home, "config")
        self.continuity = os.path.join(self.home, "continuity")
        self.output = os.path.join(self.home, "output")
        for path in (self.corpus, self.state, self.config,
                     self.continuity, self.output,
                     os.path.join(self.share, "research"),
                     os.path.join(self.state, "managed-install")):
            os.makedirs(path, mode=0o700, exist_ok=True)

        private = Ed25519PrivateKey.generate()
        private_raw = private.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
            serialization.NoEncryption())
        public_raw = private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self._write(os.path.join(self.share, "key.hex"),
                    private_raw.hex() + "\n", 0o600)
        self._write(os.path.join(self.share, "pub.hex"),
                    public_raw.hex() + "\n", 0o644)
        self._write(os.path.join(self.share, "ledger.tsv"), "signed rows\n")
        self.ledger_head = "a" * 64
        self._write(os.path.join(self.share, "head.pin"),
                    "1 " + self.ledger_head + "\n")
        self._write(os.path.join(self.corpus, "memory.md"), "remember me\n")
        os.mkdir(os.path.join(self.corpus, ".git"), 0o700)
        self._write(os.path.join(self.corpus, ".git", "HEAD"),
                    "ref: refs/heads/main\n")
        self._write(os.path.join(self.corpus, "legitimate.lock"),
                    "brain content, not an internal lock\n")
        os.mkdir(os.path.join(self.corpus, ".gbrain"), 0o700)
        self._write(os.path.join(self.corpus, ".gbrain", "machine"), "x")
        self._write(os.path.join(self.share, "research", "finding.md"),
                    "finding\n")
        self._write(os.path.join(self.state, "memo.json"), json.dumps({
            "pulse_seq": 1, "sync_needed": False}) + "\n")
        self._write(os.path.join(self.state, "status.json"), "{}\n")
        self._write(os.path.join(self.state, "worker.lock"), "")
        os.mkdir(os.path.join(self.state, "test.quarantine"), 0o700)
        self._write(os.path.join(self.config, "config.json"),
                    '{"safe":true}\n')
        self._write(os.path.join(self.config, "continuity.json"),
                    '{"repository":"secret"}\n', 0o600)
        self._write(os.path.join(self.config, "backend.credentials"),
                    "secret\n", 0o600)

        self.patches = [
            mock.patch.object(sialib, "HOME", self.home),
            mock.patch.object(sialib, "SHARE", self.share),
            mock.patch.object(sialib, "STATE", self.state),
            mock.patch.object(sialib, "CORPUS", self.corpus),
            mock.patch.object(sialib, "BIN", BIN),
            mock.patch.object(sialib, "CORPUS_OWNER_LOCK",
                              os.path.join(self.state, "corpus-owner.lock")),
            mock.patch.object(sialib, "BRAINSTEM_OWNER_LOCK",
                              os.path.join(self.state, "brainstem-owner.lock")),
            mock.patch.object(sialib, "GBRAIN_OWNER_LOCK",
                              os.path.join(self.state, "gbrain-owner.lock")),
            mock.patch.object(sialib, "LIFECYCLE_LOCK",
                              os.path.join(self.home, "lifecycle.lock")),
            mock.patch.object(sialib, "THOUGHT_INBOX_LOCK",
                              os.path.join(self.state, "thought-inbox.lock")),
            mock.patch.object(sialib, "corpus_owner", _owned_corpus),
            mock.patch.object(sialib, "memory_readiness",
                              return_value=(True, "ready")),
            mock.patch.object(siacapsule, "CONFIG_ROOT", self.config),
            mock.patch.object(siacapsule, "CONTINUITY_ROOT", self.continuity),
            mock.patch.object(siacapsule, "RESTORE_BARRIER",
                              os.path.join(self.continuity,
                                           "restore-in-progress.json")),
            mock.patch.object(siacapsule, "MANAGED_ROOT",
                              os.path.join(self.state, "managed-install")),
            mock.patch.object(siacapsule, "CORPUS_RECEIPT",
                              os.path.join(self.state, "managed-install",
                                           "corpus")),
            mock.patch.object(siacapsule, "SCHEMA_PACK_RECEIPT",
                              os.path.join(self.state, "managed-install",
                                           "schema-pack")),
            mock.patch.object(siacapsule, "LEDGER_KEY",
                              os.path.join(self.share, "key.hex")),
            mock.patch.object(siacapsule, "LEDGER_PUBLIC",
                              os.path.join(self.share, "pub.hex")),
            mock.patch.object(siacapsule, "_git_head",
                              return_value="b" * 40),
            mock.patch.object(siacapsule, "_git_head_at",
                              return_value="b" * 40),
            mock.patch.object(siacapsule, "_verify_copied_ledger",
                              return_value="pass"),
            mock.patch.object(siacapsule,
                              "_probe_live_projection_quiescent",
                              return_value={"probe": {"ok": True}}),
            mock.patch.object(siacapsule, "_initialize_projection_stage",
                              side_effect=self._fake_projection_stage),
            mock.patch.object(siacapsule, "_activate_restored_projection",
                              return_value=None),
        ]
        for patcher in self.patches:
            patcher.start()
        self._publish_gbrain_fixture()
        self._publish_receipt()

    def tearDown(self):
        for patcher in reversed(self.patches):
            patcher.stop()
        self.fixture.cleanup()

    @staticmethod
    def _write(path, text, mode=0o600):
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, mode)

    def _publish_receipt(self):
        info = os.lstat(self.corpus)
        receipt = (
            "managed-by=khephri.sia\nkind=corpus-v2\npath="
            + self.corpus + "\nroot="
            + ":".join(str(value) for value in (
                info.st_dev, info.st_ino, info.st_mode, info.st_uid))
            + "\n")
        self._write(siacapsule.CORPUS_RECEIPT, receipt, 0o600)
        self.receipt = receipt

    def _publish_gbrain_fixture(self):
        self.gbrain = os.path.join(self.share, ".gbrain")
        self.projection = os.path.join(self.gbrain, "brain.pglite")
        pack_dir = os.path.join(
            self.gbrain, "schema-packs", "sia-pack")
        os.makedirs(self.projection, mode=0o700)
        os.makedirs(pack_dir, mode=0o700)
        self._write(
            os.path.join(self.gbrain, "config.json"),
            json.dumps({
                "engine": "pglite",
                "database_path": self.projection,
                "schema_pack": "sia-pack",
                "embedding_disabled": True,
            }, sort_keys=True) + "\n", 0o600)
        pack_path = os.path.join(pack_dir, "pack.yaml")
        self._write(pack_path, "name: sia-pack\n", 0o644)
        with open(pack_path, "rb") as stream:
            digest = hashlib.sha256(stream.read()).hexdigest()
        self._write(
            siacapsule.SCHEMA_PACK_RECEIPT,
            "managed-by=khephri.sia\nkind=schema-pack\npath="
            + pack_path + "\nsha256=" + digest + "\n", 0o600)
        self._write(
            os.path.join(self.projection, "fixture"),
            "resident projection\n")

    def _fake_projection_stage(self, journal):
        projection = os.path.join(
            journal["projection_stage_home"], ".gbrain", "brain.pglite")
        os.makedirs(projection, mode=0o700)
        self._write(os.path.join(projection, "fixture"),
                    "fresh projection\n")
        return projection

    def _gbrain_substrate_observation(self):
        pack = os.path.join(
            self.gbrain, "schema-packs", "sia-pack", "pack.yaml")
        paths = (
            os.path.join(self.gbrain, "config.json"),
            pack,
            siacapsule.SCHEMA_PACK_RECEIPT,
        )
        return {
            "root": siacapsule._root_identity(os.lstat(self.gbrain)),
            "files": {
                path: siacapsule._generation(os.lstat(path))
                for path in paths
            },
        }

    def _freeze(self, name="capsule"):
        path = os.path.join(self.output, name)
        result = siacapsule.freeze(path)
        return path, result

    @staticmethod
    def _prepare(path, prepared_id, snapshot_id):
        return siacapsule.prepare_binding(
            path, prepared_id=prepared_id, snapshot_id=snapshot_id)

    def test_roots_contract_is_versioned_exact_and_never_walked_live(self):
        contract = siacapsule.roots()
        self.assertEqual(contract["schema"], siacapsule.ROOTS_SCHEMA)
        self.assertIs(contract["do_not_walk_live"], True)
        self.assertEqual(
            contract["source_constraints"]["symbolic_links"], "refuse")
        authorities = {
            row["area"]: row for row in contract["authorities"]}
        self.assertEqual(authorities["share"]["path"], self.share)
        self.assertEqual(authorities["state"]["path"], self.state)
        self.assertEqual(authorities["config"]["path"], self.config)
        self.assertEqual(
            authorities["share"]["selection"]["mode"], "allowlist")
        self.assertIn(
            "managed-install",
            authorities["state"]["selection"]["exclude_top_level_names"])
        self.assertEqual(
            authorities["state"]["selection"]
            ["basename_pattern_normalization"], "lower")
        self.assertIn(
            "continuity.",
            authorities["config"]["selection"]
            ["exclude_top_level_prefixes"])

    def test_freeze_is_signed_portable_and_secret_free(self):
        path, result = self._freeze()
        verified = siacapsule.verify(path)
        self.assertEqual(verified["schema"], siacapsule.VERIFIED_SCHEMA)
        self.assertNotIn("snapshot_id", verified)
        self.assertEqual(result["capsule_id"], verified["capsule_id"])
        self.assertEqual(result["public_key"], verified["public_key"])
        payload = os.path.join(path, "payload")
        self.assertTrue(os.path.isfile(
            os.path.join(payload, "share", "corpus", ".git", "HEAD")))
        self.assertTrue(os.path.isfile(os.path.join(
            payload, "share", "corpus", "legitimate.lock")))
        self.assertFalse(os.path.lexists(
            os.path.join(payload, "share", "key.hex")))
        self.assertFalse(os.path.lexists(os.path.join(
            payload, "share", "corpus", ".gbrain")))
        self.assertFalse(os.path.lexists(
            os.path.join(payload, "state", "managed-install")))
        self.assertFalse(os.path.lexists(
            os.path.join(payload, "state", "status.json")))
        self.assertFalse(os.path.lexists(os.path.join(
            payload, "config", "continuity.json")))
        self.assertFalse(os.path.lexists(os.path.join(
            payload, "config", "backend.credentials")))

        identity_path = os.path.join(self.output, "offline.identity")
        siacapsule.export_identity_key(identity_path)
        self.assertEqual(stat.S_IMODE(os.lstat(identity_path).st_mode), 0o600)
        siacapsule.validate_identity_key(identity_path,
                                         verified["public_key"])

        unbound = dict(verified)
        unbound.update({
            "prepared_id": "f" * 32,
            "snapshot_id": "snapshot-not-core-bound",
        })
        with self.assertRaisesRegex(ValueError, "receipt is malformed"):
            siacapsule._prepared_binding(unbound)
        prepared = self._prepare(
            path, "f" * 32, "snapshot-core-bound")
        self.assertEqual(prepared["schema"], siacapsule.PREPARED_SCHEMA)

    def test_verify_rejects_tampering_and_unsigned_empty_directory(self):
        path, _result = self._freeze()
        os.mkdir(os.path.join(path, "payload", "share", "unsigned"), 0o700)
        with self.assertRaisesRegex(ValueError, "unsigned directory"):
            siacapsule.verify(path)
        os.rmdir(os.path.join(path, "payload", "share", "unsigned"))

        manifest_path = os.path.join(path, "manifest.json")
        with open(manifest_path, encoding="utf-8") as stream:
            manifest = json.load(stream)
        manifest["sia_version"] = "tampered"
        self._write(manifest_path, json.dumps(
            manifest, sort_keys=True, separators=(",", ":")) + "\n")
        with self.assertRaisesRegex(ValueError, "signature"):
            siacapsule.verify(path)

    def test_freeze_refuses_authority_output_links_and_bad_receipt(self):
        with self.assertRaisesRegex(ValueError, "absolute"):
            siacapsule.freeze("relative-capsule")
        with self.assertRaisesRegex(ValueError, "authority root"):
            siacapsule.freeze(os.path.join(self.corpus, "capsule"))
        with self.assertRaisesRegex(ValueError, "authority root"):
            siacapsule.export_identity_key(
                os.path.join(self.state, "offline.identity"))

        os.unlink(siacapsule.CORPUS_RECEIPT)
        with self.assertRaises(FileNotFoundError):
            self._freeze("missing-receipt")
        self.assertFalse(os.path.lexists(os.path.join(
            self.output, "missing-receipt")))
        self.assertFalse(any(
            name.startswith(".sia-capsule-stage-")
            for name in os.listdir(self.output)))
        self._write(siacapsule.CORPUS_RECEIPT, "wrong\n", 0o600)
        with self.assertRaisesRegex(ValueError, "does not bind"):
            self._freeze("wrong-receipt")

        self._publish_receipt()
        os.symlink("memory.md", os.path.join(self.corpus, "linked.md"))
        with self.assertRaisesRegex(ValueError, "link or special"):
            self._freeze("linked-source")
        self.assertFalse(os.path.lexists(os.path.join(
            self.output, "linked-source")))
        self.assertFalse(any(
            name.startswith(".sia-capsule-stage-")
            for name in os.listdir(self.output)))

    def test_identity_export_requires_private_parent_and_rechecks_output(self):
        exposed = os.path.join(self.home, "exposed")
        os.mkdir(exposed, 0o700)
        os.chmod(exposed, 0o755)
        with self.assertRaisesRegex(ValueError, "owner-private"):
            siacapsule.freeze(os.path.join(exposed, "capsule"))
        with self.assertRaisesRegex(ValueError, "owner-private"):
            siacapsule.export_identity_key(
                os.path.join(exposed, "identity.key"))

        result = siacapsule.export_identity_key(os.path.join(
            self.output, "identity.key"))
        self.assertEqual(result["path"], os.path.join(
            self.output, "identity.key"))
        self.assertRegex(result["fingerprint"], r"^[0-9a-f]{64}$")
        info = os.lstat(result["path"])
        self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)

    def test_freeze_atomic_publication_never_clobbers_a_racing_target(self):
        destination = os.path.join(self.output, "raced-capsule")
        publish = siacapsule._rename_noreplace

        def race(parent, source_name, destination_name):
            os.mkdir(destination, 0o700)
            publish(parent, source_name, destination_name)

        with mock.patch.object(
                siacapsule, "_rename_noreplace", side_effect=race):
            with self.assertRaises(FileExistsError):
                siacapsule.freeze(destination)
        self.assertTrue(os.path.isdir(destination))
        self.assertEqual(os.listdir(destination), [])
        self.assertFalse(any(
            name.startswith(".sia-capsule-stage-")
            for name in os.listdir(self.output)))

    def test_freeze_refuses_bounded_scan_overflow_without_plaintext_residue(self):
        destination = os.path.join(self.output, "bounded-refusal")
        with mock.patch.object(
                siacapsule, "_CAPSULE_DIRECTORY_ENTRY_LIMIT", 1):
            with self.assertRaisesRegex(ValueError, "entry bound"):
                siacapsule.freeze(destination)
        self.assertFalse(os.path.lexists(destination))
        self.assertFalse(any(
            name.startswith(".sia-capsule-stage-")
            for name in os.listdir(self.output)))

    def test_gbrain_substrate_refuses_managed_receipt_parent_symlink(self):
        managed = siacapsule.MANAGED_ROOT
        parked = managed + ".real"
        os.rename(managed, parked)
        os.symlink(parked, managed)
        try:
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                siacapsule._gbrain_substrate_binding()
        finally:
            os.unlink(managed)
            os.rename(parked, managed)

    def test_missing_schema_receipt_refuses_before_restore_mutation(self):
        prepared_path, _result = self._freeze("missing-schema-receipt")
        prepared = self._prepare(
            prepared_path, "9" * 32, "snapshot-missing-schema-receipt")
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": prepared["snapshot_id"],
            "ledger_head": self.ledger_head,
            "corpus_receipt_re_adopt": True,
        }
        observed_paths = (
            os.path.join(self.corpus, "memory.md"),
            os.path.join(self.gbrain, "config.json"),
            os.path.join(self.projection, "fixture"),
        )
        before = {
            path: siacapsule._generation(os.lstat(path))
            for path in observed_paths
        }
        os.unlink(siacapsule.SCHEMA_PACK_RECEIPT)
        rollback_root = os.path.join(self.continuity, "rollback")

        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True):
            with self.assertRaises(FileNotFoundError):
                siacapsule.thaw(
                    prepared, confirmation, capability={},
                    rollback_root=rollback_root,
                    first_light=lambda **_kwargs: None)

        self.assertEqual(
            {
                path: siacapsule._generation(os.lstat(path))
                for path in observed_paths
            },
            before)
        self.assertFalse(os.path.lexists(siacapsule.RESTORE_BARRIER))
        self.assertEqual(os.listdir(rollback_root), [])

    def test_native_lock_cleanup_preserves_racing_replacement_holder(self):
        token = "a" * 32
        journal = {"native_lock_token": token}
        siacapsule._acquire_native_projection_lock(journal)
        replacement = {
            "pid": os.getpid(),
            "acquired_at": 1,
            "refreshed_at": 1,
            "command": "gbrain serve",
            "subcommand": "serve",
            "pid_ns": None,
            "boot_id": None,
        }
        replacement_raw = json.dumps(
            replacement, sort_keys=True, separators=(",", ":")) + "\n"
        rename = siacapsule._rename_noreplace_fd

        def replace_after_validation(parent_fd, source_name,
                                     destination_name):
            rename(parent_fd, source_name, destination_name)
            if source_name == ".gbrain-lock" \
                    and destination_name.startswith(
                        ".sia-retired-native-lock-"):
                lock_dir = os.path.join(self.projection, ".gbrain-lock")
                os.mkdir(lock_dir, 0o700)
                self._write(
                    os.path.join(lock_dir, "lock"), replacement_raw,
                    0o644)

        with mock.patch.object(
                siacapsule, "_rename_noreplace_fd",
                side_effect=replace_after_validation):
            with self.assertRaisesRegex(
                    RuntimeError, "replacement native PGLite holder"):
                siacapsule._remove_native_lock_intent(
                    self.projection, token)

        replacement_path = os.path.join(
            self.projection, ".gbrain-lock", "lock")
        with open(replacement_path, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), replacement_raw)
        self.assertFalse(os.path.lexists(os.path.join(
            self.projection, ".gbrain-lock.reap-claim")))

    def test_native_lock_cleanup_resumes_after_retirement_power_cut(self):
        token = "b" * 32
        journal = {"native_lock_token": token}
        siacapsule._acquire_native_projection_lock(journal)
        cleanup = siacapsule._cleanup_retired_native_dir
        interrupted = False

        def cut_once(parent_fd, name, *args):
            nonlocal interrupted
            if not interrupted and name.startswith(
                    ".sia-retired-native-lock-"):
                interrupted = True
                raise KeyboardInterrupt("power cut after native retirement")
            return cleanup(parent_fd, name, *args)

        with mock.patch.object(
                siacapsule, "_cleanup_retired_native_dir",
                side_effect=cut_once):
            with self.assertRaises(KeyboardInterrupt):
                siacapsule._remove_native_lock_intent(
                    self.projection, token)

        siacapsule._remove_native_lock_intent(self.projection, token)
        self.assertFalse(any(
            name == ".gbrain-lock"
            or name == ".gbrain-lock.reap-claim"
            or token in name
            for name in os.listdir(self.projection)))

    def test_dead_gbrain_lock_and_claim_are_delegated_to_native_probe(self):
        process = subprocess.Popen([
            sys.executable, "-c", "import time; time.sleep(60)"])
        dead_pid = process.pid
        process.terminate()
        process.wait(timeout=5)
        token = "c" * 32
        lock_dir = os.path.join(self.projection, ".gbrain-lock")
        claim_dir = os.path.join(
            self.projection, ".gbrain-lock.reap-claim")
        os.mkdir(lock_dir, 0o700)
        native = siacapsule._native_lock_record(token)
        native.pop("sia_restore_token")
        native["pid"] = dead_pid
        native["command"] = "gbrain engine status --probe --json"
        native["subcommand"] = "engine"
        self._write(
            os.path.join(lock_dir, "lock"),
            json.dumps(native, sort_keys=True) + "\n", 0o644)
        os.mkdir(claim_dir, 0o700)
        self._write(
            os.path.join(claim_dir, "lock"),
            json.dumps({
                "pid": dead_pid,
                "at": siacapsule._native_claim_record(token)["at"],
            }, sort_keys=True) + "\n", 0o644)
        journal = {
            "native_lock_token": token,
            "phase": "barrier",
            **siacapsule._gbrain_substrate_binding(),
        }
        journal_path = os.path.join(self.output, "native-journal.json")
        siacapsule._atomic_json(journal_path, journal)
        probe_observed_native = False

        def native_probe():
            nonlocal probe_observed_native
            probe_observed_native = os.path.isfile(os.path.join(
                lock_dir, "lock")) and os.path.isfile(os.path.join(
                    claim_dir, "lock"))
            os.unlink(os.path.join(claim_dir, "lock"))
            os.rmdir(claim_dir)
            os.unlink(os.path.join(lock_dir, "lock"))
            os.rmdir(lock_dir)
            self._write(os.path.join(
                self.gbrain, "brain.pglite.lock-reap.json"),
                '{"native":true}\n', 0o644)
            return {"probe": {"ok": True}}

        with mock.patch.object(
                siacapsule, "_probe_live_projection_quiescent",
                side_effect=native_probe):
            siacapsule._prepare_live_projection_for_native_lock(journal)
        siacapsule._refresh_barrier_gbrain_binding(journal, journal_path)

        self.assertTrue(probe_observed_native)
        self.assertFalse(os.path.lexists(lock_dir))
        self.assertFalse(os.path.lexists(claim_dir))
        with open(journal_path, encoding="utf-8") as stream:
            persisted = json.load(stream)
        self.assertEqual(
            persisted["projection_sidecars"],
            siacapsule._gbrain_substrate_binding()["projection_sidecars"])

    def test_dead_orphan_gbrain_reap_claim_is_retired_descriptor_safely(self):
        process = subprocess.Popen([
            sys.executable, "-c", "import time; time.sleep(60)"])
        dead_pid = process.pid
        process.terminate()
        process.wait(timeout=5)
        token = "d" * 32
        claim_dir = os.path.join(
            self.projection, ".gbrain-lock.reap-claim")
        os.mkdir(claim_dir, 0o700)
        self._write(
            os.path.join(claim_dir, "lock"),
            json.dumps({
                "pid": dead_pid,
                "at": siacapsule._native_claim_record(token)["at"],
            }, sort_keys=True) + "\n", 0o644)

        siacapsule._prepare_live_projection_for_native_lock({
            "native_lock_token": token})

        self.assertFalse(os.path.lexists(claim_dir))
        self.assertFalse(any(
            name.startswith(".sia-retired-native-reap-claim-")
            for name in os.listdir(self.projection)))

    def test_live_gbrain_reap_claim_is_preserved_and_refused(self):
        process = subprocess.Popen([
            sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(lambda: process.poll() is None and process.kill())
        token = "e" * 32
        claim_dir = os.path.join(
            self.projection, ".gbrain-lock.reap-claim")
        os.mkdir(claim_dir, 0o700)
        self._write(
            os.path.join(claim_dir, "lock"),
            json.dumps({
                "pid": process.pid,
                "at": siacapsule._native_claim_record(token)["at"],
            }, sort_keys=True) + "\n", 0o644)

        with self.assertRaisesRegex(
                RuntimeError, "reap claim is live or ambiguous"):
            siacapsule._prepare_live_projection_for_native_lock({
                "native_lock_token": token})

        self.assertTrue(os.path.isfile(os.path.join(claim_dir, "lock")))
        process.terminate()
        process.wait(timeout=5)

    def test_successful_thaw_retires_complete_rollback_operation(self):
        prepared_path, _result = self._freeze("commit-prepared")
        prepared = self._prepare(
            prepared_path, "8" * 32, "snapshot-commit-cleanup")
        self._write(os.path.join(self.corpus, "memory.md"),
                    "target before commit\n")
        gbrain = self.gbrain
        old_projection = os.path.join(self.projection, "target.db")
        self._write(old_projection, "old projection\n")
        substrate_before = self._gbrain_substrate_observation()
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": prepared["snapshot_id"],
            "ledger_head": self.ledger_head,
            "corpus_receipt_re_adopt": True,
        }
        rollback_root = os.path.join(self.continuity, "rollback")

        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True), \
                mock.patch.object(siacapsule, "_settle_adoption") \
                as settle, \
                mock.patch.object(siacapsule, "_restore_health",
                                  return_value={
                                      "ready": True,
                                      "readiness_reason": "ready"}):
            restored = siacapsule.thaw(
                prepared, confirmation, capability={},
                rollback_root=rollback_root,
                first_light=lambda **_kwargs: None)

        self.assertTrue(restored["restored"])
        self.assertFalse(restored["rolled_back"])
        settle.assert_called_once()
        self.assertFalse(os.path.lexists(siacapsule.RESTORE_BARRIER))
        self.assertEqual(os.listdir(rollback_root), [])
        self.assertTrue(os.path.isdir(gbrain))
        self.assertFalse(os.path.lexists(old_projection))
        self.assertTrue(os.path.isfile(os.path.join(
            self.projection, "fixture")))
        self.assertEqual(
            self._gbrain_substrate_observation(), substrate_before)
        for current, _dirs, files in os.walk(self.continuity):
            self.assertNotIn("key.hex", files, current)

    def test_next_thaw_resumes_terminal_cleanup_after_barrier_clear(self):
        prepared_path, _result = self._freeze("cleanup-cut-prepared")
        prepared = self._prepare(
            prepared_path, "7" * 32, "snapshot-cleanup-cut")
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": prepared["snapshot_id"],
            "ledger_head": self.ledger_head,
            "corpus_receipt_re_adopt": True,
        }
        rollback_root = os.path.join(self.continuity, "rollback")
        original_delete = siacapsule._delete_operation_catalog

        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True), \
                mock.patch.object(siacapsule, "_settle_adoption"), \
                mock.patch.object(siacapsule, "_restore_health",
                                  return_value={
                                      "ready": True,
                                      "readiness_reason": "ready"}), \
                mock.patch.object(
                    siacapsule, "_delete_operation_catalog",
                    side_effect=KeyboardInterrupt(
                        "power cut after barrier retirement")):
            with self.assertRaises(KeyboardInterrupt):
                siacapsule.thaw(
                    prepared, confirmation, capability={},
                    rollback_root=rollback_root,
                    first_light=lambda **_kwargs: None)

        self.assertFalse(os.path.lexists(siacapsule.RESTORE_BARRIER))
        operations = os.listdir(rollback_root)
        self.assertTrue(operations)
        journal_path = os.path.join(
            rollback_root, operations[0], "journal.json")
        with open(journal_path, encoding="utf-8") as stream:
            self.assertEqual(json.load(stream)["phase"], "retiring-commit")

        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True), \
                mock.patch.object(siacapsule, "_settle_adoption"), \
                mock.patch.object(siacapsule, "_restore_health",
                                  return_value={
                                      "ready": True,
                                      "readiness_reason": "ready"}), \
                mock.patch.object(siacapsule, "_delete_operation_catalog",
                                  side_effect=original_delete):
            result = siacapsule.thaw(
                prepared, confirmation, capability={},
                rollback_root=rollback_root,
                first_light=lambda **_kwargs: None)
        self.assertTrue(result["restored"])
        self.assertEqual(os.listdir(rollback_root), [])

    def test_failed_first_light_rolls_back_and_clears_barrier(self):
        prepared_path, _result = self._freeze("prepared")
        prepared = self._prepare(
            prepared_path, "c" * 32, "snapshot-one")

        self._write(os.path.join(self.corpus, "memory.md"), "target before\n")
        gbrain = self.gbrain
        target_projection = os.path.join(self.projection, "target.db")
        self._write(target_projection, "target projection\n")
        sidecars = {}
        for name in siacapsule._GBRAIN_PROJECTION_SIDECARS:
            path = os.path.join(self.gbrain, name)
            self._write(path, "sidecar " + name + "\n", 0o600)
            sidecars[path] = siacapsule._gbrain_sidecar_record(path)["content"]
        substrate_before = self._gbrain_substrate_observation()
        corpus_inode = os.lstat(self.corpus).st_ino
        with open(siacapsule.CORPUS_RECEIPT, "rb") as stream:
            receipt_bytes = stream.read()
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": prepared["snapshot_id"],
            "ledger_head": self.ledger_head,
            "corpus_receipt_re_adopt": True,
        }
        rollback_root = os.path.join(self.continuity, "rollback")

        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True), \
                mock.patch.object(siacapsule, "_restore_health",
                                  return_value={
                                      "ready": True,
                                      "sia_ledger_verified": True,
                                      "readiness_reason": "ready"}):
            with self.assertRaisesRegex(RuntimeError, "rolled back"):
                siacapsule.thaw(
                    prepared, confirmation, capability={},
                    rollback_root=rollback_root,
                    first_light=lambda **_kwargs: (_ for _ in ()).throw(
                        RuntimeError("first light failed")))

        with open(os.path.join(self.corpus, "memory.md"), encoding="utf-8") \
                as stream:
            self.assertEqual(stream.read(), "target before\n")
        with open(target_projection, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "target projection\n")
        self.assertEqual(
            self._gbrain_substrate_observation(), substrate_before)
        self.assertEqual(
            {
                path: siacapsule._gbrain_sidecar_record(path)["content"]
                for path in sidecars
            },
            sidecars)
        self.assertEqual(os.lstat(self.corpus).st_ino, corpus_inode)
        with open(siacapsule.CORPUS_RECEIPT, "rb") as stream:
            self.assertEqual(stream.read(), receipt_bytes)
        self.assertFalse(os.path.lexists(siacapsule.RESTORE_BARRIER))
        self.assertEqual(os.listdir(rollback_root), [])
        for current, _dirs, files in os.walk(self.continuity):
            self.assertNotIn("key.hex", files, current)

    def test_power_cut_barrier_recovers_before_first_mutation(self):
        prepared_path, _result = self._freeze("power-prepared")
        prepared = self._prepare(
            prepared_path, "d" * 32, "snapshot-power-cut")
        gbrain = self.gbrain
        kept_projection = os.path.join(self.projection, "kept.db")
        self._write(kept_projection, "unchanged\n")
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": prepared["snapshot_id"],
            "ledger_head": self.ledger_head,
            "corpus_receipt_re_adopt": True,
        }
        rollback_root = os.path.join(self.continuity, "rollback")
        original_clear = siacapsule._clear_live_portable
        interrupted = mock.Mock(side_effect=KeyboardInterrupt("power cut"))
        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True), \
                mock.patch.object(siacapsule, "_restore_health",
                                  return_value={
                                      "ready": True,
                                      "sia_ledger_verified": True,
                                      "readiness_reason": "ready"}), \
                mock.patch.object(siacapsule, "_clear_live_portable",
                                  interrupted):
            with self.assertRaises(KeyboardInterrupt):
                siacapsule.thaw(
                    prepared, confirmation, capability={},
                    rollback_root=rollback_root,
                    first_light=lambda **_kwargs: None)
        self.assertTrue(os.path.isfile(siacapsule.RESTORE_BARRIER))

        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True), \
                mock.patch.object(siacapsule, "_health_observation",
                                  return_value={
                                      "ready": False,
                                      "sia_ledger_verified": True,
                                      "readiness_reason": "prior projection debt"}), \
                mock.patch.object(siacapsule, "_clear_live_portable",
                                  original_clear):
            result = siacapsule.recover_barrier(capability={})
        self.assertTrue(result["rolled_back"])
        self.assertFalse(result["ready"])
        self.assertFalse(os.path.lexists(siacapsule.RESTORE_BARRIER))
        with open(kept_projection, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "unchanged\n")

    def test_power_cut_after_projection_swap_restores_exact_target(self):
        prepared_path, _result = self._freeze("projection-cut-prepared")
        prepared = self._prepare(
            prepared_path, "3" * 32, "snapshot-projection-cut")
        self._write(os.path.join(self.corpus, "memory.md"),
                    "target before projection cut\n")
        target_projection = os.path.join(self.projection, "target.db")
        self._write(target_projection, "target projection before cut\n")
        substrate_before = self._gbrain_substrate_observation()
        corpus_inode = os.lstat(self.corpus).st_ino
        with open(siacapsule.CORPUS_RECEIPT, "rb") as stream:
            receipt_before = stream.read()
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": prepared["snapshot_id"],
            "ledger_head": self.ledger_head,
            "corpus_receipt_re_adopt": True,
        }
        rollback_root = os.path.join(self.continuity, "rollback")

        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True), \
                mock.patch.object(
                    siacapsule, "_install_capsule_content",
                    side_effect=KeyboardInterrupt(
                        "power cut after projection swap")):
            with self.assertRaises(KeyboardInterrupt):
                siacapsule.thaw(
                    prepared, confirmation, capability={},
                    rollback_root=rollback_root,
                    first_light=lambda **_kwargs: None)

        self.assertTrue(os.path.isfile(siacapsule.RESTORE_BARRIER))
        self.assertFalse(os.path.lexists(target_projection))

        move_aside = siacapsule._move_aside

        def cut_first_recovery(source, destination):
            if source == self.projection:
                raise KeyboardInterrupt(
                    "power cut after recovery acquired native lock")
            return move_aside(source, destination)

        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True), \
                mock.patch.object(siacapsule, "_move_aside",
                                  side_effect=cut_first_recovery):
            with self.assertRaises(KeyboardInterrupt):
                siacapsule.recover_barrier(capability={})
        self.assertTrue(os.path.isdir(os.path.join(
            self.projection, ".gbrain-lock")))

        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True), \
                mock.patch.object(siacapsule, "_health_observation",
                                  return_value={
                                      "ready": True,
                                      "sia_ledger_verified": True,
                                      "readiness_reason": "ready"}):
            recovered = siacapsule.recover_barrier(capability={})

        self.assertTrue(recovered["rolled_back"])
        with open(os.path.join(self.corpus, "memory.md"),
                  encoding="utf-8") as stream:
            self.assertEqual(stream.read(),
                             "target before projection cut\n")
        with open(target_projection, encoding="utf-8") as stream:
            self.assertEqual(stream.read(),
                             "target projection before cut\n")
        self.assertEqual(os.lstat(self.corpus).st_ino, corpus_inode)
        with open(siacapsule.CORPUS_RECEIPT, "rb") as stream:
            self.assertEqual(stream.read(), receipt_before)
        self.assertEqual(
            self._gbrain_substrate_observation(), substrate_before)
        self.assertFalse(os.path.lexists(siacapsule.RESTORE_BARRIER))
        self.assertEqual(os.listdir(rollback_root), [])

    def test_power_cut_during_private_key_copy_leaves_recoverable_barrier(self):
        prepared_path, _result = self._freeze("pre-key-cut-prepared")
        prepared = self._prepare(
            prepared_path, "4" * 32, "snapshot-pre-key-cut")
        live_gbrain = self.gbrain
        resident_projection = os.path.join(
            self.projection, "resident.db")
        self._write(resident_projection,
                    "resident projection\n")
        observed_paths = (
            os.path.join(self.corpus, "memory.md"),
            os.path.join(self.state, "memo.json"),
            os.path.join(self.config, "config.json"),
            os.path.join(self.share, "key.hex"),
            resident_projection,
        )
        generations_before = {
            path: siacapsule._generation(os.lstat(path))
            for path in observed_paths
        }
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": prepared["snapshot_id"],
            "ledger_head": self.ledger_head,
            "corpus_receipt_re_adopt": True,
        }
        rollback_root = os.path.join(self.continuity, "rollback")
        original_write = siacapsule._write_exclusive

        def interrupt_during_key_copy(path, content, mode):
            if os.path.basename(path) == "target-key.hex":
                with open(path, "wb") as stream:
                    stream.write(content[:1])
                os.chmod(path, mode)
                raise KeyboardInterrupt("power cut during private-key copy")
            return original_write(path, content, mode)

        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True), \
                mock.patch.object(siacapsule, "_write_exclusive",
                                  side_effect=interrupt_during_key_copy):
            with self.assertRaises(KeyboardInterrupt):
                siacapsule.thaw(
                    prepared, confirmation, capability={},
                    rollback_root=rollback_root,
                    first_light=lambda **_kwargs: None)

        self.assertTrue(os.path.isfile(siacapsule.RESTORE_BARRIER))
        self.assertTrue(any(
            "target-key.hex" in files
            for _current, _dirs, files in os.walk(self.continuity)))

        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True), \
                mock.patch.object(siacapsule, "_health_observation",
                                  return_value={
                                      "ready": True,
                                      "sia_ledger_verified": True,
                                      "readiness_reason": "ready"}), \
                mock.patch.object(
                    siacapsule, "_clear_live_portable",
                    side_effect=AssertionError(
                        "barrier-only recovery rewrote live roots")):
            recovered = siacapsule.recover_barrier(capability={})
        self.assertTrue(recovered["rolled_back"])
        self.assertFalse(os.path.lexists(siacapsule.RESTORE_BARRIER))
        self.assertEqual(
            {
                path: siacapsule._generation(os.lstat(path))
                for path in observed_paths
            },
            generations_before)
        for current, _dirs, files in os.walk(self.continuity):
            self.assertNotIn("key.hex", files, current)

    def test_next_thaw_retires_prebarrier_power_cut_orphan(self):
        prepared_path, _result = self._freeze("prebarrier-prepared")
        prepared = self._prepare(
            prepared_path, "6" * 32, "snapshot-prebarrier-cut")
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": prepared["snapshot_id"],
            "ledger_head": self.ledger_head,
            "corpus_receipt_re_adopt": True,
        }
        rollback_root = os.path.join(self.continuity, "rollback")
        original_atomic = siacapsule._atomic_json

        def cut_before_barrier(path, value):
            if os.path.basename(path) == "journal.json" \
                    and value.get("phase") == "barrier":
                raise KeyboardInterrupt("power cut before barrier")
            return original_atomic(path, value)

        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True), \
                mock.patch.object(siacapsule, "_atomic_json",
                                  side_effect=cut_before_barrier):
            with self.assertRaises(KeyboardInterrupt):
                siacapsule.thaw(
                    prepared, confirmation, capability={},
                    rollback_root=rollback_root,
                    first_light=lambda **_kwargs: None)

        self.assertFalse(os.path.lexists(siacapsule.RESTORE_BARRIER))
        self.assertTrue(os.listdir(rollback_root))

        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True), \
                mock.patch.object(siacapsule, "_settle_adoption"), \
                mock.patch.object(siacapsule, "_restore_health",
                                  return_value={
                                      "ready": True,
                                      "readiness_reason": "ready"}):
            result = siacapsule.thaw(
                prepared, confirmation, capability={},
                rollback_root=rollback_root,
                first_light=lambda **_kwargs: None)
        self.assertTrue(result["restored"])
        self.assertEqual(os.listdir(rollback_root), [])

    def test_ordinary_rollback_freeze_failure_is_retired_immediately(self):
        prepared_path, _result = self._freeze("freeze-failure-prepared")
        prepared = self._prepare(
            prepared_path, "5" * 32, "snapshot-freeze-failure")
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": prepared["snapshot_id"],
            "ledger_head": self.ledger_head,
            "corpus_receipt_re_adopt": True,
        }
        rollback_root = os.path.join(self.continuity, "rollback")

        def fail_partial_rollback_freeze(path, **_kwargs):
            os.mkdir(path, 0o700)
            self._write(os.path.join(path, "partial"), "incomplete\n")
            raise RuntimeError("rollback freeze failed")

        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True), \
                mock.patch.object(
                    siacapsule, "freeze",
                    side_effect=fail_partial_rollback_freeze):
            with self.assertRaisesRegex(RuntimeError,
                                        "rollback freeze failed"):
                siacapsule.thaw(
                    prepared, confirmation, capability={},
                    rollback_root=rollback_root,
                    first_light=lambda **_kwargs: None)

        self.assertFalse(os.path.lexists(siacapsule.RESTORE_BARRIER))
        self.assertEqual(os.listdir(rollback_root), [])

    def test_reconciliation_never_touches_active_barrier_operation(self):
        rollback_root = os.path.join(self.continuity, "rollback")
        os.mkdir(rollback_root, 0o700)
        active = os.path.join(
            rollback_root, "a" * 32 + "-" + "b" * 32)
        inactive = os.path.join(
            rollback_root, "c" * 32 + "-" + "d" * 32)
        os.mkdir(active, 0o700)
        os.mkdir(inactive, 0o700)
        self._write(os.path.join(active, "sentinel"), "active\n")
        barrier = {
            "schema": siacapsule.JOURNAL_SCHEMA,
            "journal": os.path.join(active, "journal.json"),
            "prepared_id": "a" * 32,
            "created": "active",
        }
        self._write(siacapsule.RESTORE_BARRIER, json.dumps(
            barrier, sort_keys=True, separators=(",", ":")) + "\n", 0o600)

        siacapsule._reconcile_rollback_operations(
            rollback_root, active_operation=active)

        self.assertTrue(os.path.isfile(os.path.join(active, "sentinel")))
        self.assertFalse(os.path.lexists(inactive))
        self.assertTrue(os.path.isfile(siacapsule.RESTORE_BARRIER))

    def test_reconciliation_refuses_symlink_tree_without_partial_delete(self):
        rollback_root = os.path.join(self.continuity, "rollback")
        os.mkdir(rollback_root, 0o700)
        operation = os.path.join(
            rollback_root, "e" * 32 + "-" + "f" * 32)
        capsule = os.path.join(operation, "target-capsule")
        os.mkdir(operation, 0o700)
        os.mkdir(capsule, 0o700)
        os.symlink(self.share, os.path.join(capsule, "escape"))
        live_key = os.path.join(self.share, "key.hex")
        with open(live_key, "rb") as stream:
            expected = stream.read()

        with self.assertRaisesRegex(ValueError, "link or special"):
            siacapsule._reconcile_rollback_operations(rollback_root)

        self.assertTrue(os.path.islink(os.path.join(capsule, "escape")))
        with open(live_key, "rb") as stream:
            self.assertEqual(stream.read(), expected)

    def test_cleanup_catalog_refuses_each_finite_bound_before_delete(self):
        rollback_root = os.path.join(self.continuity, "rollback")
        os.mkdir(rollback_root, 0o700)
        operation = os.path.join(
            rollback_root, "0" * 32 + "-" + "1" * 32)
        capsule = os.path.join(operation, "target-capsule")
        nested = os.path.join(capsule, "nested")
        os.mkdir(operation, 0o700)
        os.mkdir(capsule, 0o700)
        os.mkdir(nested, 0o700)
        marker = os.path.join(nested, "marker")
        self._write(marker, "retained\n")

        limits = (
            ("_OPERATION_DIRECTORY_ENTRY_LIMIT", "entry bound"),
            ("_OPERATION_TREE_DEPTH_LIMIT", "depth bound"),
            ("_OPERATION_TREE_RECORD_LIMIT", "record bound"),
        )
        for constant, refusal in limits:
            with self.subTest(bound=constant), \
                    mock.patch.object(siacapsule, constant, False):
                with self.assertRaisesRegex(ValueError, refusal):
                    siacapsule._catalog_operation_tree(operation)
                self.assertTrue(os.path.isfile(marker))

        siacapsule._retire_inactive_operation(operation)
        self.assertFalse(os.path.lexists(operation))

    def test_cleanup_catalog_accepts_capsule_git_log_depth(self):
        rollback_root = os.path.join(self.continuity, "rollback")
        os.mkdir(rollback_root, 0o700)
        operation = os.path.join(
            rollback_root, "a" * 32 + "-" + "b" * 32)
        os.mkdir(operation, 0o700)
        deepest = os.path.join(
            operation, "target-capsule", "payload", "share", "corpus",
            ".git", "logs", "refs", "heads", "master")
        os.makedirs(os.path.dirname(deepest), mode=0o700)
        self._write(deepest, "ref history\n")

        catalog = siacapsule._catalog_operation_tree(operation)
        self.assertIn(
            tuple(os.path.relpath(deepest, operation).split(os.sep)),
            {record["parts"] for record in catalog["records"]})
        with mock.patch.object(
                siacapsule, "_OPERATION_TREE_DEPTH_LIMIT", 8):
            with self.assertRaisesRegex(ValueError, "depth bound"):
                siacapsule._catalog_operation_tree(operation)
        self.assertTrue(os.path.isfile(deepest))

    def test_repeated_successful_thaws_leave_bounded_empty_rollback_root(self):
        prepared_path, _result = self._freeze("repeat-prepared")
        rollback_root = os.path.join(self.continuity, "rollback")
        for prepared_id, snapshot_id in (
                ("1" * 32, "snapshot-repeat-a"),
                ("2" * 32, "snapshot-repeat-b")):
            prepared = self._prepare(
                prepared_path, prepared_id, snapshot_id)
            confirmation = {
                "schema_version": 1,
                "phrase": "RESTORE",
                "snapshot_id": snapshot_id,
                "ledger_head": self.ledger_head,
                "corpus_receipt_re_adopt": True,
            }
            with mock.patch.object(siacapsule,
                                   "validate_restore_capability",
                                   return_value=True), \
                    mock.patch.object(siacapsule, "_settle_adoption"), \
                    mock.patch.object(siacapsule, "_restore_health",
                                      return_value={
                                          "ready": True,
                                          "readiness_reason": "ready"}):
                result = siacapsule.thaw(
                    prepared, confirmation, capability={},
                    rollback_root=rollback_root,
                    first_light=lambda **_kwargs: None)
            self.assertTrue(result["restored"])
            self.assertEqual(os.listdir(rollback_root), [])
            for current, _dirs, files in os.walk(self.continuity):
                self.assertNotIn("key.hex", files, current)

    def test_key_retirement_cannot_follow_intermediate_share_symlink(self):
        rollback_root = os.path.join(self.continuity, "rollback")
        os.mkdir(rollback_root, 0o700)
        operation_root = os.path.join(
            rollback_root, "3" * 32 + "-" + "4" * 32)
        replaced = os.path.join(operation_root, "replaced-live")
        os.makedirs(replaced, mode=0o700)
        os.symlink(self.share, os.path.join(replaced, "share"))
        live_key = os.path.join(self.share, "key.hex")
        with open(live_key, "rb") as stream:
            expected = stream.read()

        with self.assertRaises((OSError, ValueError)):
            siacapsule._retire_operation_keys(operation_root)

        with open(live_key, "rb") as stream:
            self.assertEqual(stream.read(), expected)

    def test_adoption_intent_and_committed_transition_are_signed(self):
        prepared = {
            "prepared_id": "e" * 32,
            "snapshot_id": "snapshot-adoption",
            "capsule_id": "f" * 32,
            "manifest_sha256": "1" * 64,
        }
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": prepared["snapshot_id"],
            "ledger_head": self.ledger_head,
            "corpus_receipt_re_adopt": True,
        }
        target = siacapsule.target_identity()
        intent_path = os.path.join(self.output, "adoption.json")
        intent = siacapsule.write_adoption_intent(
            intent_path, prepared=prepared, confirmation=confirmation,
            target=target)
        unsigned_intent = dict(intent)
        signature = bytes.fromhex(unsigned_intent.pop("signature"))
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(intent["signer"])).verify(
                signature, siacapsule._canonical_bytes(unsigned_intent))

        committed_path = os.path.join(self.output, "adoption-committed.json")
        with mock.patch.object(sialib, "queue_ledger_transition",
                               return_value="pending"), \
                mock.patch.object(sialib, "_settle_ledger_transition"), \
                mock.patch.object(sialib, "ledger_contains",
                                  return_value=True), \
                mock.patch.object(sialib, "ledger_head",
                                  return_value=(2, "2" * 64)):
            committed = siacapsule._settle_adoption(intent, committed_path)
        self.assertEqual(committed["state"], "committed")
        unsigned_committed = dict(committed)
        committed_signature = bytes.fromhex(
            unsigned_committed.pop("signature"))
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(committed["signer"])).verify(
                committed_signature,
                siacapsule._canonical_bytes(unsigned_committed))

    def test_payload_mutation_after_binding_rolls_back(self):
        prepared_path, _result = self._freeze("race-prepared")
        prepared = self._prepare(
            prepared_path, "3" * 32, "snapshot-race")
        target_page = os.path.join(self.corpus, "memory.md")
        self._write(target_page, "target survives\n")
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": prepared["snapshot_id"],
            "ledger_head": self.ledger_head,
            "corpus_receipt_re_adopt": True,
        }
        source_page = os.path.join(
            prepared_path, "payload", "share", "corpus", "memory.md")
        original_clear = siacapsule._clear_live_portable
        calls = []

        def clear_then_mutate(removed_root):
            original_clear(removed_root)
            if not calls:
                calls.append(True)
                self._write(source_page, "changed after binding\n")

        with mock.patch.object(siacapsule,
                               "validate_restore_capability",
                               return_value=True), \
                mock.patch.object(siacapsule, "_restore_health",
                                  return_value={
                                      "ready": True,
                                      "sia_ledger_verified": True,
                                      "readiness_reason": "ready"}), \
                mock.patch.object(siacapsule, "_clear_live_portable",
                                  side_effect=clear_then_mutate):
            with self.assertRaisesRegex(RuntimeError, "rolled back"):
                siacapsule.thaw(
                    prepared, confirmation, capability={},
                    rollback_root=os.path.join(self.continuity, "rollback"),
                    first_light=lambda **_kwargs: None)
        with open(target_page, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "target survives\n")
        self.assertFalse(os.path.lexists(siacapsule.RESTORE_BARRIER))

    def test_brain_admission_refuses_barrier_except_restore_ex(self):
        barrier = os.path.join(self.continuity, "admission-barrier.json")
        self._write(barrier, "{}\n", 0o600)
        with mock.patch.object(sialib, "RESTORE_BARRIER_PATH", barrier), \
                mock.patch.dict(os.environ, {
                    "SIA_RESTORE_LAUNCH_ABI": ""}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "restore is interrupted"):
                sialib._require_restore_admission()
        with mock.patch.object(sialib, "RESTORE_BARRIER_PATH", barrier), \
                mock.patch.dict(os.environ, {
                    "SIA_RESTORE_LAUNCH_ABI": "sia-restore-launch-v1"},
                    clear=False), \
                mock.patch.object(sialib,
                                  "_validated_inherited_lifecycle_fd",
                                  return_value=9):
            self.assertIsNone(sialib._require_restore_admission())

    def test_installed_brainstem_exits_cleanly_behind_restore_barrier(self):
        runtime = os.path.join(
            self.home, ".local", "share", "sia", "bin")
        os.makedirs(runtime, mode=0o700, exist_ok=True)
        for name in ("sia-brainstem", "sialib.py", "siamind.py",
                     "siatakes.py", "siaqueue.py", "siasenses.py",
                     "siagraph.py", "siarestoreadmit.py"):
            source = os.path.join(BIN, name)
            target = os.path.join(
                runtime, "sia-brainstem.py" if name == "sia-brainstem"
                else name)
            shutil.copyfile(source, target)
            os.chmod(target, 0o700 if name == "sia-brainstem" else 0o600)
        lifecycle = os.path.join(
            self.home, ".local", "state", "sia.lifecycle.lock")
        os.makedirs(os.path.dirname(lifecycle), mode=0o700, exist_ok=True)
        with open(lifecycle, "wb"):
            pass
        os.chmod(lifecycle, 0o600)
        barrier = os.path.join(
            self.home, ".local", "state", "sia-continuity",
            "restore-in-progress.json")
        os.makedirs(os.path.dirname(barrier), mode=0o700, exist_ok=True)
        self._write(barrier, "{}\n", 0o600)
        target = os.path.join(runtime, "sia-brainstem.py")
        launcher = textwrap.dedent("""
            import fcntl
            import os
            import sys

            lifecycle, target = sys.argv[1:]
            lifecycle_fd = os.open(lifecycle, os.O_RDWR)
            target_fd = os.open(target, os.O_RDONLY)
            fcntl.flock(lifecycle_fd, fcntl.LOCK_SH)
            os.set_inheritable(lifecycle_fd, True)
            os.set_inheritable(target_fd, True)
            environment = dict(os.environ)
            environment.update({
                "SIA_LAUNCHER_ABI": "sia-launch-v1",
                "SIA_LAUNCHER_LIFECYCLE_FD": str(lifecycle_fd),
                "SIA_LAUNCHER_TARGET_FD": str(target_fd),
                "SIA_LAUNCHER_TARGET_PATH": target,
            })
            os.execve(sys.executable, [sys.executable, target], environment)
        """)
        environment = dict(os.environ)
        environment["HOME"] = self.home
        result = subprocess.run(
            [sys.executable, "-c", launcher, lifecycle, target],
            env=environment, text=True, capture_output=True, timeout=10,
            check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
