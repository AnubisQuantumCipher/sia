"""Rollback sidecar replay against the existing isolated capsule fixture.

The interruption is injected after the real, durable sidecar rename. Recovery
then acquires fresh capability descriptors and reloads the journal through the
normal barrier front door; no process-local journal is passed to the retry.
"""

import contextlib
import fcntl
import os
import unittest
from unittest import mock

try:
    import sia_test_home  # noqa: F401  (isolate paths before runtime imports)
    import test_backup_restore as capsule_fixtures
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore  # noqa: F401
    from tests import test_backup_restore as capsule_fixtures  # type: ignore


class CapsuleSidecarRetry(unittest.TestCase):
    def setUp(self):
        # Composition reuses the fixture without re-exporting or inheriting
        # its TestCase, which would duplicate its tests during discovery.
        self.fixture = capsule_fixtures.CapsuleBoundaryTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.runtime = capsule_fixtures.siacapsule
        self.core = capsule_fixtures.sialib
        # The shared fixture supplies synthetic ledger bytes. Verification
        # itself is outside this file-identity/recovery-journal regression.
        verifier = mock.patch.object(
            self.runtime, "_verify_live_sia_ledger", return_value=True)
        verifier.start()
        self.addCleanup(verifier.stop)

    @contextlib.contextmanager
    def _held_capability(self):
        """Use real owned temporary lock files, renewed on recovery."""
        descriptors = []
        capability = {}
        try:
            for key, path in (
                    ("lifecycle_fd", self.core.LIFECYCLE_LOCK),
                    ("brainstem_fd", self.core.BRAINSTEM_OWNER_LOCK),
                    ("corpus_fd", self.core.CORPUS_OWNER_LOCK),
                    ("gbrain_fd", self.core.GBRAIN_OWNER_LOCK)):
                descriptor = os.open(
                    path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
                    | os.O_CLOEXEC, 0o600)
                descriptors.append(descriptor)
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                capability[key] = descriptor
            yield capability
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    @staticmethod
    def _bytes(path):
        with open(path, "rb") as stream:
            return stream.read()

    def _cut_after_restored_sidecar(self):
        fixture = self.fixture
        runtime = self.runtime
        prepared_path, _result = fixture._freeze("sidecar-retry-prepared")
        prepared = fixture._prepare(
            prepared_path, "b" * 32, "snapshot-sidecar-retry")
        fixture._write(
            os.path.join(fixture.corpus, "memory.md"),
            "target corpus before interrupted restore\n")
        self.target_page = self._bytes(
            os.path.join(fixture.corpus, "memory.md"))
        self.target_projection = self._bytes(
            os.path.join(fixture.projection, "fixture"))
        self.target_corpus_identity = runtime.target_identity()
        self.original_records = {}
        self.original_bytes = {}
        for name in runtime._GBRAIN_PROJECTION_SIDECARS:
            path = os.path.join(fixture.gbrain, name)
            fixture._write(path, "original sidecar " + name + "\n", 0o600)
            self.original_records[name] = runtime._gbrain_sidecar_record(path)
            self.original_bytes[name] = self._bytes(path)
        self.cut_name = runtime._GBRAIN_PROJECTION_SIDECARS[0]
        self.cut_path = os.path.join(fixture.gbrain, self.cut_name)
        self.rollback_root = os.path.join(fixture.continuity, "rollback")
        confirmation = {
            "schema_version": 1,
            "phrase": "RESTORE",
            "snapshot_id": prepared["snapshot_id"],
            "ledger_head": fixture.ledger_head,
            "corpus_receipt_re_adopt": True,
        }
        move_aside = runtime._move_aside
        interrupted_sources = []

        def cut_after_real_rename(source, destination):
            result = move_aside(source, destination)
            if destination == self.cut_path \
                    and os.path.basename(source) == "target-" + self.cut_name:
                interrupted_sources.append(source)
                raise KeyboardInterrupt("power cut after restored sidecar rename")
            return result

        def fail_first_light(**_kwargs):
            raise RuntimeError("fixture first light requires rollback")

        with self._held_capability() as capability, mock.patch.object(
                runtime, "_move_aside", side_effect=cut_after_real_rename):
            with self.assertRaisesRegex(
                    KeyboardInterrupt, "restored sidecar rename"):
                runtime.thaw(
                    prepared, confirmation, capability=capability,
                    rollback_root=self.rollback_root,
                    first_light=fail_first_light)

        self.assertEqual(len(interrupted_sources), 1)
        self.saved_sidecar = interrupted_sources[0]
        self.assertFalse(os.path.lexists(self.saved_sidecar))
        self.assertEqual(self._bytes(self.cut_path),
                         self.original_bytes[self.cut_name])
        restored = runtime._gbrain_sidecar_record(self.cut_path)
        self.assertEqual(restored["content"],
                         self.original_records[self.cut_name]["content"])
        self.assertEqual(restored["generation"]["inode"],
                         self.original_records[self.cut_name]["generation"]
                         ["inode"])
        self.assertNotEqual(restored["generation"],
                            self.original_records[self.cut_name]["generation"])
        self.journal_path = runtime._barrier_journal_path()
        journal, self.operation_root = runtime._load_thaw_journal(
            self.journal_path)
        self.assertEqual(journal["phase"], "rolling-back")
        self.assertEqual(journal["projection_sidecars"], self.original_records)

    def test_restart_after_sidecar_rename_preserves_exact_prior_contents(self):
        self._cut_after_restored_sidecar()

        with self._held_capability() as capability:
            outcome = self.runtime.recover_barrier(capability=capability)

        self.assertIs(outcome["rolled_back"], True)
        self.assertFalse(os.path.lexists(self.runtime.RESTORE_BARRIER))
        self.assertEqual(os.listdir(self.rollback_root), [])
        self.assertEqual(self.runtime.target_identity(),
                         self.target_corpus_identity)
        self.assertEqual(self._bytes(os.path.join(
            self.fixture.corpus, "memory.md")), self.target_page)
        self.assertEqual(self._bytes(os.path.join(
            self.fixture.projection, "fixture")), self.target_projection)
        for name, expected in self.original_bytes.items():
            with self.subTest(sidecar=name):
                path = os.path.join(self.fixture.gbrain, name)
                self.assertEqual(self._bytes(path), expected)
                self.assertEqual(
                    self.runtime._gbrain_sidecar_record(path)["content"],
                    self.original_records[name]["content"])

    def test_restart_refuses_changed_restored_sidecar_bytes(self):
        self._cut_after_restored_sidecar()
        original = self.original_bytes[self.cut_name]
        altered = bytes([original[0] ^ 1]) + original[1:]
        self.fixture._write(self.cut_path, altered.decode("ascii"), 0o600)
        info = os.stat(self.cut_path)
        os.utime(self.cut_path, ns=(
            info.st_atime_ns,
            self.original_records[self.cut_name]["generation"]["modified_ns"]))
        changed = self._bytes(self.cut_path)

        with self._held_capability() as capability:
            with self.assertRaisesRegex(ValueError, "gbrain sidecar|substrate"):
                self.runtime.recover_barrier(capability=capability)

        self.assertTrue(os.path.isfile(self.runtime.RESTORE_BARRIER))
        self.assertEqual(self.runtime._barrier_journal_path(), self.journal_path)
        self.assertEqual(self._bytes(self.cut_path), changed)
        self.assertFalse(os.path.lexists(self.saved_sidecar))
        journal, _operation_root = self.runtime._load_thaw_journal(
            self.journal_path)
        self.assertEqual(journal["phase"], "rolling-back")
        self.assertEqual(journal["projection_sidecars"], self.original_records)


if __name__ == "__main__":
    unittest.main()
