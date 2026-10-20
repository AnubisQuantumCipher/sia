"""Fresh interpreters retain exact staged work across actual SIGKILL."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest


class ConsolidationDeliveryExec(unittest.TestCase):
    def test_process_death_replays_exact_batch_then_exact_claims(self):
        worker = Path(__file__).with_name("consolidation_delivery_exec_worker.py")
        with tempfile.TemporaryDirectory(prefix="sia-delivery-exec-") as directory:
            home = Path(directory)
            (home / ".sia-exec-fixture").write_text("disposable-test-home\n")
            env = {"HOME": directory, "SIA_EXEC_FIXTURE_HOME": directory,
                   "PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"}
            state = home / ".local/state/sia"
            corpus = home / ".local/share/sia/corpus"
            journal = state / "consolidation-snapshot-delivery.json"

            def invoke(phase, expected=0):
                result = subprocess.run(
                    [sys.executable, "-B", str(worker), phase], env=env,
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, expected, result.stderr)
                return json.loads(result.stdout) if expected == 0 else None

            admission = invoke("prepare")
            source = corpus / "events/org/2026-01-05.md"
            original = source.read_bytes()
            memo = (state / "memo.json").read_bytes()
            invoke("kill-batch", -signal.SIGKILL)
            pending = json.loads(journal.read_text())
            self.assertEqual(pending["admission"], admission)
            self.assertEqual(pending["phase"], "pending")
            self.assertIsNone(pending["cursor"])
            self.assertEqual([item["relative"] for item in
                              pending["batch"]["result"]["candidates"]],
                             ["events/org/2026-01-05.md"])
            persisted = journal.read_bytes()
            self.assertEqual(invoke("offer"), pending)
            self.assertEqual(journal.read_bytes(), persisted)
            invoke("kill-claims", -signal.SIGKILL)
            claimed = json.loads(journal.read_text())
            self.assertEqual(claimed["phase"], "claimed")
            self.assertEqual(claimed["admission"], admission)
            self.assertEqual(claimed["cursor"], pending["cursor"])
            self.assertEqual(claimed["batch"], pending["batch"])
            self.assertEqual([claim["date"] for claim in claimed["claims"]["claims"]],
                             ["2026-01-05"])
            persisted = journal.read_bytes()
            self.assertEqual(invoke("claim"), claimed)
            self.assertEqual(invoke("offer"), claimed)
            self.assertEqual(journal.read_bytes(), persisted)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual((state / "memo.json").read_bytes(), memo)
            self.assertFalse((corpus / "epochs").exists())

    def test_worker_requires_fixture_opt_in(self):
        worker = Path(__file__).with_name("consolidation_delivery_exec_worker.py")
        with tempfile.TemporaryDirectory(prefix="sia-delivery-refusal-") as home:
            result = subprocess.run(
                [sys.executable, "-B", str(worker), "prepare"],
                env={"HOME": home, "PATH": "/usr/bin:/bin"},
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1)
            self.assertIn("explicit isolated fixture home required", result.stderr)
            self.assertFalse((Path(home) / ".local").exists())


if __name__ == "__main__":
    unittest.main()
