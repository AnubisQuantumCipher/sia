"""Retained pin-stage refusal and signed-tail recovery through the real CLI."""

import contextlib
import io
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tests.test_ledger_init_recovery import KEEPER, LEDGER


class LedgerStageRecovery(unittest.TestCase):
    def _pending_tail(self, state):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(KEEPER.cmd_init(str(state)), 0)
        with mock.patch.object(
                KEEPER, "_write_pin", side_effect=OSError("pin interrupted")) \
                as interrupted:
            with self.assertRaisesRegex(OSError, "pin interrupted"):
                KEEPER.cmd_append(str(state), "TEST:stage", "a", "b", "0" * 64, 0)
        interrupted.assert_called_once()
        _path, count, head = interrupted.call_args.args
        self.assertTrue((state / "ledger.pending").is_file())
        return f"{count} {head}\n".encode("ascii")

    def _snapshot(self, state):
        names = sorted(os.listdir(state))
        self.assertLessEqual(len(names), 8)
        result = {}
        for name in names:
            if name == "ledger.lock":
                continue  # Acquiring the existing lease refreshes its mode/ctime.
            path = state / name
            info = path.lstat()
            identity = (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
                        info.st_nlink, info.st_size, info.st_mtime_ns,
                        info.st_ctime_ns)
            data = None
            if stat.S_ISREG(info.st_mode):
                with path.open("rb") as stream:
                    data = stream.read(4097)
                self.assertLessEqual(len(data), 4096)
            elif stat.S_ISLNK(info.st_mode):
                data = os.readlink(path)
            result[name] = (identity, data)
        return names, result

    def _command(self, state, command="head"):
        return subprocess.run(
            [sys.executable, "-B", "-W", "error", LEDGER, command, str(state)],
            capture_output=True, text=True, timeout=3, check=False)

    def _refuses_unchanged(self, state, reason, command="head"):
        before = self._snapshot(state)
        try:
            result = self._command(state, command)
        finally:
            self.assertEqual(self._snapshot(state), before)
        self.assertEqual(result.returncode, 1, result)
        diagnostic = result.stdout + result.stderr
        self.assertIn(reason, diagnostic)
        self.assertNotIn("Bad file descriptor", diagnostic)
        self.assertNotIn("LEDGER VERIFIED.", diagnostic)

    def test_fifo_stage_refuses_without_writer_or_history_mutation(self):
        for command in ("head", "verify"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmp:
                state = Path(tmp)
                self._pending_tail(state)
                os.mkfifo(state / ".head.pin.stage", 0o644)
                self._refuses_unchanged(
                    state, "retained replacement stage is unsafe", command)

    def test_symlink_stage_is_not_followed_or_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            payload = self._pending_tail(state)
            victim = state / "operator-file"
            victim.write_bytes(payload)
            victim.chmod(0o644)
            (state / ".head.pin.stage").symlink_to(victim.name)
            self._refuses_unchanged(state, "Too many levels of symbolic links")

    def test_unsafe_regular_stage_keeps_original_refusal_and_bytes(self):
        cases = ("wrong-mode", "wrong-size", "wrong-content", "hardlink")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                state = Path(tmp)
                payload = self._pending_tail(state)
                stage = state / ".head.pin.stage"
                content = payload
                if case == "wrong-size":
                    content = payload + b"extra"
                elif case == "wrong-content":
                    content = b"X" + payload[1:]
                stage.write_bytes(content)
                stage.chmod(0o600 if case == "wrong-mode" else 0o644)
                if case == "hardlink":
                    os.link(stage, state / "operator-file")
                reason = "not exact" if case == "wrong-content" else "unsafe"
                self._refuses_unchanged(
                    state, f"retained replacement stage is {reason}")

    def test_exact_stage_finishes_same_tail_and_repeated_head_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            payload = self._pending_tail(state)
            stage = state / ".head.pin.stage"
            stage.write_bytes(payload)
            stage.chmod(0o644)
            before = self._snapshot(state)[1]
            retained_inode = stage.stat().st_ino
            first = self._command(state)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stderr, "")
            self.assertEqual(first.stdout.encode("ascii"), payload)
            self.assertFalse(stage.exists())
            self.assertFalse((state / "ledger.pending").exists())
            self.assertEqual((state / "head.pin").read_bytes(), payload)
            self.assertEqual((state / "head.pin").stat().st_ino, retained_inode)
            after = self._snapshot(state)[1]
            for name in ("key.hex", "pub.hex", "ledger.tsv"):
                self.assertEqual(after[name], before[name])
            second = self._command(state)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(second.stderr, "")
            self.assertEqual(second.stdout, first.stdout)
            self.assertEqual(self._snapshot(state)[1], after)


if __name__ == "__main__":
    unittest.main()
