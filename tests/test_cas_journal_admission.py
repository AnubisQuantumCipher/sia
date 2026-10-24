"""Exact installer CAS journal admission in private files; no installation."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "install.sh"


def cas_program():
    source = SOURCE.read_text()
    marker = "owned_file_cas() {\n  python3 - \"$@\" <<'PY'\n"
    if source.count(marker) != 1:
        raise ValueError("ambiguous CAS helper extraction")
    return source.split(marker, 1)[1].split("\nPY\n}", 1)[0]


def identity(path):
    info = path.lstat()
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class CasJournalAdmission(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / "target"
        self.stage = self.root / "stage"
        self.target.write_bytes(b"preserve original\n")
        self.stage.write_bytes(b"staged successor\n")
        key = hashlib.sha256(os.fsencode(self.target)).hexdigest()
        self.journal = self.root / (".sia-cas-journal-" + key)
        self.lock = self.root / (".sia-cas-lock-" + key)
        self.program = cas_program()

    def invoke(self, *arguments):
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-c", self.program, *arguments],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=3, check=False)
        except subprocess.TimeoutExpired:
            self.fail("CAS helper exceeded its fixture deadline")
        self.assert_lock_released()
        return result

    def assert_lock_released(self):
        descriptor = os.open(self.lock, os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def refuse_unchanged(self):
        before = {p: identity(p) for p in (self.target, self.stage, self.journal)}
        result = self.invoke("recover", str(self.target))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, b"")
        for path, expected in before.items():
            self.assertEqual(identity(path), expected)
        self.assertEqual(self.target.read_bytes(), b"preserve original\n")
        self.assertEqual(self.stage.read_bytes(), b"staged successor\n")
        return result

    def test_fifo_without_peer_is_refused_before_waiting(self):
        os.mkfifo(self.journal, 0o600)
        result = self.refuse_unchanged()
        self.assertIn(b"unsafe CAS journal", result.stderr)

    def test_fifo_with_peer_is_not_consumed(self):
        os.mkfifo(self.journal, 0o600)
        descriptor = os.open(self.journal, os.O_RDWR | os.O_NONBLOCK)
        try:
            payload = b"must not consume this stream\n"
            self.assertEqual(os.write(descriptor, payload), len(payload))
            result = self.refuse_unchanged()
            self.assertIn(b"unsafe CAS journal", result.stderr)
            self.assertEqual(os.read(descriptor, 128), payload)
        finally:
            os.close(descriptor)

    def test_symlink_is_refused_without_touching_referent(self):
        referent = self.root / "referent"
        referent.write_bytes(b"operator file\n")
        before = identity(referent)
        self.journal.symlink_to(referent)
        self.refuse_unchanged()
        self.assertEqual(identity(referent), before)
        self.assertEqual(referent.read_bytes(), b"operator file\n")

    def test_directory_is_refused(self):
        self.journal.mkdir()
        result = self.refuse_unchanged()
        self.assertIn(b"unsafe CAS journal", result.stderr)

    def test_invalid_regular_journals_are_preserved(self):
        for payload in (b"{}\n", b"\xff", b"null", b"x" * 65537):
            with self.subTest(payload_length=len(payload)):
                self.journal.write_bytes(payload)
                self.refuse_unchanged()
                self.assertEqual(self.journal.read_bytes(), payload)

    def test_missing_journal_is_a_successful_noop(self):
        before = {p: identity(p) for p in (self.target, self.stage)}
        result = self.invoke("recover", str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.journal.exists())
        self.assertEqual({p: identity(p) for p in before}, before)

    def publish(self):
        self.target.unlink()
        result = self.invoke("publish", str(self.stage), str(self.target), "absent")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), b"staged successor\n")
        self.assertFalse(self.journal.exists())
        return result.stdout.decode().strip()

    def test_valid_journal_reconciles_completed_publication(self):
        token = self.publish()
        self.journal.write_text(json.dumps({
            "version": 1, "operation": "publish", "target": self.target.name,
            "staged": self.stage.name, "archive": "archive",
            "expected": "absent", "desired": token,
        }))
        before = identity(self.target)
        result = self.invoke("recover", str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.journal.exists())
        self.assertEqual(identity(self.target), before)
        self.assertEqual(self.target.read_bytes(), b"staged successor\n")

    def test_normal_publication_and_archive_preserve_bytes(self):
        token = self.publish()
        archive = self.root / "archive"
        result = self.invoke("archive", str(archive), str(self.target), token)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.target.exists())
        self.assertEqual(archive.read_bytes(), b"staged successor\n")
        self.assertFalse(self.journal.exists())


if __name__ == "__main__":
    unittest.main()
