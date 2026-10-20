"""Actual SIGKILL and fresh-interpreter admission recovery, in disposable HOME."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest


class ConsolidationAdmissionExec(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sia-admission-exec-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        (self.home / ".sia-exec-fixture").write_text("disposable-test-home\n")
        self.env = {"HOME": str(self.home),
                    "SIA_EXEC_FIXTURE_HOME": str(self.home),
                    "PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"}
        self.worker = Path(__file__).with_name(
            "consolidation_admission_exec_worker.py")
        self.state = self.home / ".local/state/sia"
        self.corpus = self.home / ".local/share/sia/corpus"
        self.journal = self.state / "consolidation-snapshot-admission.json"
        self.invoke("prepare")
        self.request = json.loads(
            (self.state / "admission-fixture-request.json").read_text())
        self.ref = "refs/sia/consolidation/" + self.request["generation"]
        self.source = self.corpus / "events/org/2026-01-05.md"
        self.original = self.source.read_bytes()
        self.memo = (self.state / "memo.json").read_bytes()

    def invoke(self, phase, expected=0):
        result = subprocess.run(
            [sys.executable, "-B", str(self.worker), phase], env=self.env,
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def git(self, *arguments, expected=0):
        result = subprocess.run(
            ["git", "-C", str(self.corpus), *arguments], env=self.env,
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def assert_source_unchanged(self):
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual((self.state / "memo.json").read_bytes(), self.memo)
        self.assertFalse((self.corpus / "epochs").exists())

    def cut_and_recover(self, phase, retained_phase, pinned):
        self.invoke(phase, -signal.SIGKILL)
        retained = json.loads(self.journal.read_text())
        self.assertEqual(retained, dict(
            self.request, schema="sia-consolidation-snapshot-admission-v1",
            phase=retained_phase))
        result = self.git("rev-parse", "--verify", "--quiet", self.ref,
                          expected=0 if pinned else 1)
        self.assertEqual(result.stdout,
                         self.request["commit"] + "\n" if pinned else "")
        self.assertEqual(result.stderr, "")
        self.assert_source_unchanged()
        # Each call starts a new interpreter; no module state crosses the cut.
        recovered = self.invoke("recover")
        expected = dict(retained, phase="admitted")
        self.assertEqual(json.loads(recovered.stdout), expected)
        self.assertEqual(json.loads(self.journal.read_text()), expected)
        journal_bytes = self.journal.read_bytes()
        replay = self.invoke("recover")
        self.assertEqual(json.loads(replay.stdout), expected)
        self.assertEqual(self.journal.read_bytes(), journal_bytes)
        self.assertEqual(self.git("rev-parse", "--verify", self.ref).stdout,
                         self.request["commit"] + "\n")
        self.assert_source_unchanged()

    def test_death_after_planned_journal(self):
        self.cut_and_recover("kill-planned", "planned", False)

    def test_death_after_pin_before_admission(self):
        self.cut_and_recover("kill-pin", "planned", True)

    def test_death_after_admission(self):
        self.cut_and_recover("kill-admitted", "admitted", True)

    def test_missing_admitted_pin_refuses_after_restart(self):
        self.invoke("kill-admitted", -signal.SIGKILL)
        before = self.journal.read_bytes()
        self.git("update-ref", "-d", self.ref, self.request["commit"])
        result = self.invoke("recover", 1)
        self.assertIn("admitted snapshot pin is missing or differs", result.stderr)
        self.assertEqual(self.journal.read_bytes(), before)
        absent = self.git("rev-parse", "--verify", "--quiet", self.ref, expected=1)
        self.assertEqual((absent.stdout, absent.stderr), ("", ""))
        self.assert_source_unchanged()

    def test_conflicting_pin_refuses_planned_recovery(self):
        self.invoke("kill-planned", -signal.SIGKILL)
        before = self.journal.read_bytes()
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@invalid",
                 "commit", "--allow-empty", "-qm", "different fixture commit")
        other = self.git("rev-parse", "HEAD").stdout.strip()
        self.assertNotEqual(other, self.request["commit"])
        self.git("update-ref", self.ref, other)
        result = self.invoke("recover", 1)
        self.assertIn("snapshot generation is already bound differently",
                      result.stderr)
        self.assertEqual(self.journal.read_bytes(), before)
        self.assertEqual(self.git("rev-parse", "--verify", self.ref).stdout,
                         other + "\n")
        self.assert_source_unchanged()

    def test_truncated_journal_refuses_without_pin_creation(self):
        self.invoke("kill-planned", -signal.SIGKILL)
        # Explicit corruption, distinct from a real storage tear.
        damaged = self.journal.read_bytes()[:-1]
        self.journal.write_bytes(damaged)
        result = self.invoke("recover", 1)
        self.assertIn("snapshot admission", result.stderr)
        self.assertEqual(self.journal.read_bytes(), damaged)
        absent = self.git("rev-parse", "--verify", "--quiet", self.ref, expected=1)
        self.assertEqual((absent.stdout, absent.stderr), ("", ""))
        self.assert_source_unchanged()

    def test_worker_refuses_without_fixture_opt_in(self):
        with tempfile.TemporaryDirectory(prefix="sia-admission-refusal-") as home:
            result = subprocess.run(
                [sys.executable, "-B", str(self.worker), "prepare"],
                env={"HOME": home, "PATH": "/usr/bin:/bin"},
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1)
            self.assertIn("explicit isolated fixture home required", result.stderr)
            self.assertFalse((Path(home) / ".local").exists())


if __name__ == "__main__":
    unittest.main()
