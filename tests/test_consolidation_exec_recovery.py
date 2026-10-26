"""Fresh-exec recovery with controlled and actual signed-ledger settlement."""
from tests import sia_test_home  # noqa: F401 -- isolate before runtime references

import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest


class ConsolidationExecRecovery(unittest.TestCase):
    def test_signed_settlement_survives_death_without_duplicate_entry(self):
        worker = Path(__file__).with_name("consolidation_exec_worker.py")
        with tempfile.TemporaryDirectory(prefix="sia-exec-signed-") as home:
            (Path(home) / ".sia-exec-fixture").write_text("disposable-test-home\n")
            env = {"HOME": home, "SIA_EXEC_FIXTURE_HOME": home,
                   "PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"}
            state = Path(home) / ".local/state/sia"
            share = Path(home) / ".local/share/sia"

            def run(phase, expected):
                result = subprocess.run(
                    [sys.executable, "-B", str(worker), phase], env=env,
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, expected, result.stderr)

            run("prepare-signed", 0)
            source = share / "corpus/events/org/2026-01-05.md"
            original = source.read_bytes()
            genesis = (share / "ledger.tsv").read_bytes()
            run("kill", -signal.SIGKILL)
            applied = json.loads((state / "memo.json").read_text())
            marker = applied["consolidation_pending"]
            self.assertIn("applied_at", marker)
            self.assertEqual((share / "ledger.tsv").read_bytes(), genesis)
            run("kill-settled", -signal.SIGKILL)
            self.assertEqual(json.loads((state / "memo.json").read_text()), applied)
            signed = (share / "ledger.tsv").read_bytes()
            self.assertTrue(signed.startswith(genesis))
            self.assertEqual(len(signed.splitlines()), 2)
            pin = (share / "head.pin").read_bytes()
            run("recover-signed", 0)
            self.assertEqual((share / "ledger.tsv").read_bytes(), signed)
            self.assertEqual((share / "head.pin").read_bytes(), pin)
            self.assertNotIn("consolidation_pending",
                             json.loads((state / "memo.json").read_text()))
            self.assertEqual(source.read_bytes(), original)

    def test_worker_requires_explicit_fixture_home_before_import(self):
        worker = Path(__file__).with_name("consolidation_exec_worker.py")
        with tempfile.TemporaryDirectory(prefix="sia-exec-refusal-") as home:
            env = {"HOME": home, "PATH": "/usr/bin:/bin"}
            result = subprocess.run(
                [sys.executable, "-B", str(worker), "prepare"], env=env,
                capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("explicit isolated fixture home required", result.stderr)
            self.assertFalse((Path(home) / ".local").exists())

    def test_sigkill_after_apply_reloads_exact_transaction(self):
        worker = Path(__file__).with_name("consolidation_exec_worker.py")
        with tempfile.TemporaryDirectory(prefix="sia-exec-recovery-") as home:
            (Path(home) / ".sia-exec-fixture").write_text("disposable-test-home\n")
            env = {"HOME": home, "SIA_EXEC_FIXTURE_HOME": home,
                   "PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"}
            state = Path(home) / ".local/state/sia"
            corpus = Path(home) / ".local/share/sia/corpus"

            def run(phase, expected):
                result = subprocess.run(
                    [sys.executable, "-B", str(worker), phase], env=env,
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, expected, result.stderr)

            run("prepare", 0)
            source = corpus / "events/org/2026-01-05.md"
            original = source.read_bytes()
            initial = json.loads((state / "memo.json").read_text())
            run("kill", -signal.SIGKILL)
            applied = json.loads((state / "memo.json").read_text())
            marker = applied["consolidation_pending"]
            self.assertEqual(marker["id"], initial["consolidation_pending"]["id"])
            self.assertIn("applied_at", marker)
            self.assertIn("ledger", marker)
            self.assertFalse((state / "settlement-witness.json").exists())
            run("recover", 0)
            witness = json.loads((state / "settlement-witness.json").read_text())
            self.assertEqual(witness, marker)
            completed = json.loads((state / "memo.json").read_text())
            self.assertNotIn("consolidation_pending", completed)
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse((corpus / "epochs").exists())


if __name__ == "__main__":
    unittest.main()
