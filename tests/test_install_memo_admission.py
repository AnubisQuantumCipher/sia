"""Exercise the real installer memo front door in disposable child processes."""

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


def _program():
    installer = Path(__file__).resolve().parents[1] / "install.sh"
    with installer.open("rb") as stream:
        raw = stream.read(1_048_577)
    if len(raw) > 1_048_576:
        raise AssertionError("installer fixture exceeds source budget")
    source = raw.decode("utf-8")
    marker = 'mark_install_sync_debt() {\n  python3 - "$STATE/memo.json" <<\'PY\'\n'
    if source.count(marker) != 1:
        raise AssertionError("installer must contain one memo front door")
    program, separator, _ = source.partition(marker)[2].partition("\nPY\n}\n")
    if not separator:
        raise AssertionError("memo front door has no closed heredoc")
    return program


def _identity(path):
    value = path.lstat()
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


class InstallMemoAdmission(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.memo = self.root / "memo.json"
        self.program = _program()

    def _run(self):
        return subprocess.run(
            [sys.executable, "-I", "-W", "error", "-c", self.program, str(self.memo)],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=3, check=False)

    def _assert_completed(self, result, expected):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")
        self.assertEqual(json.loads(self.memo.read_bytes()), expected)
        info = self.memo.lstat()
        self.assertTrue(stat.S_ISREG(info.st_mode))
        self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
        self.assertEqual(info.st_uid, os.geteuid())
        self.assertEqual(set(os.listdir(self.root)), {"memo.json"})

    def test_missing_memo_creates_only_sync_debt(self):
        self._assert_completed(self._run(), {"sync_needed": True})

    def test_existing_memo_preserves_other_fields_and_updates_debt(self):
        original = {"sync_needed": False, "cursor": 42,
                    "retained": {"text": "π", "values": [None, True, "history"]}}
        self.memo.write_bytes(json.dumps(original).encode("utf-8"))
        expected = {**original, "sync_needed": True}
        self._assert_completed(self._run(), expected)

    def test_fifo_without_writer_refuses_without_replacing_it(self):
        os.mkfifo(self.memo, 0o600)
        before = _identity(self.memo)
        try:
            result = self._run()
        finally:
            self.assertEqual(_identity(self.memo), before)
            self.assertEqual(set(os.listdir(self.root)), {"memo.json"})
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"unsafe or oversized brainstem memo\n")

    def test_symlink_refuses_without_changing_target(self):
        target = self.root / "foreign.json"
        content = b'{"keep":"foreign"}'
        target.write_bytes(content)
        self.memo.symlink_to(target.name)
        before = (_identity(self.memo), _identity(target))
        result = self._run()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")
        self.assertEqual((_identity(self.memo), _identity(target)), before)
        self.assertEqual(os.readlink(self.memo), target.name)
        self.assertEqual(target.read_bytes(), content)
        self.assertEqual(set(os.listdir(self.root)), {"memo.json", "foreign.json"})

    def test_malformed_and_nonobject_memos_refuse_without_replacement(self):
        for content in (b"{", b"\xff", b"[]", b"null", b"42"):
            with self.subTest(content=content):
                self.memo.write_bytes(content)
                before = _identity(self.memo)
                result = self._run()
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(_identity(self.memo), before)
                self.assertEqual(self.memo.read_bytes(), content)
                self.assertEqual(set(os.listdir(self.root)), {"memo.json"})
                expected = (b"malformed brainstem memo:" if content in (b"{", b"\xff")
                            else b"brainstem memo must be an object\n")
                self.assertTrue(result.stderr.startswith(expected), result.stderr)


if __name__ == "__main__":
    unittest.main()
