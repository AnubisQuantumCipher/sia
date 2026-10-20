"""Fresh-process recovery after execution intent, publication and cleanup cuts."""
from tests import sia_test_home  # noqa: F401 -- isolate before runtime references

import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest


WORKER = Path(__file__).with_name("consolidation_execution_exec_worker.py")


class ConsolidationExecutionExec(unittest.TestCase):
    def invoke(self, home, phase, expected=0):
        result = subprocess.run(
            [sys.executable, "-B", str(WORKER), phase],
            env={"HOME": str(home), "SIA_EXEC_FIXTURE_HOME": str(home),
                 "PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"},
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stderr)
        return json.loads(result.stdout) if expected == 0 else None

    def check_cut(self, home, cut, later=False):
        (home / ".sia-exec-fixture").write_text("disposable-test-home\n")
        claimed = self.invoke(home, "prepare-later" if later else "prepare")
        state = home / ".local/state/sia"
        corpus = home / ".local/share/sia/corpus"
        sources = sorted((corpus / "events/org").glob("*.md"))
        self.assertEqual(len(sources), 2)
        original = {path.relative_to(corpus).as_posix(): path.read_bytes()
                    for path in sources}
        memo = (state / "memo.json").read_bytes()
        journal = state / "consolidation-snapshot-delivery.json"
        epoch = corpus / "epochs/org/2026-w02.md"
        self.invoke(home, cut, -signal.SIGKILL)
        originals = self.check_originals_prefix(home, cut, claimed, original)
        if later:
            self.assertNotEqual(originals["commit"], claimed["admission"]["commit"])
        phase = "effects-returned" if cut == "kill-persisted" else "executing"
        if cut.startswith("kill-originals-"):
            phase = "claimed"
        self.assertEqual(json.loads(journal.read_text()), dict(claimed, phase=phase))
        if cut == "kill-intent" or cut.startswith("kill-originals-"):
            self.assertFalse(epoch.exists())
            self.assertTrue(all(path.exists() for path in sources))
        elif cut == "kill-epoch":
            self.assertTrue(epoch.exists())
            self.assertTrue(all(path.exists() for path in sources))
        elif cut == "kill-unlink":
            self.assertFalse(sources[0].exists())
            self.assertTrue(sources[1].exists())
        else:
            self.assertTrue(all(not path.exists() for path in sources))
        before = epoch.read_bytes() if epoch.exists() else None
        returned = self.invoke(home, "recover")
        self.assertEqual(returned, dict(claimed, phase="effects-returned"))
        self.assertTrue(all(not path.exists() for path in sources))
        if before is not None:
            self.assertEqual(epoch.read_bytes(), before)
        self.assertEqual((state / "memo.json").read_bytes(), memo)
        self.assertEqual(json.loads((state / "consolidation-originals.json").read_text()),
                         dict(originals, phase="retained"))
        if later:
            self.sever_head_history(corpus)
        self.check_replay_and_retention(home, returned, original, later)

    def sever_head_history(self, corpus):
        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(corpus), *args], text=True, timeout=10).strip()
        git("add", "-u")
        tree = git("write-tree")
        root = git("-c", "user.name=Fixture", "-c", "user.email=t@t",
                   "commit-tree", tree, "-m", "independent process fixture root")
        git("update-ref", "HEAD", root)
        git("reflog", "expire", "--expire=now", "--all")
        git("pack-refs", "--all", "--prune")
        git("gc", "--prune=now", "--quiet")
        self.assertEqual(git("cat-file", "-t", root), "commit")

    def check_originals_prefix(self, home, cut, claimed, original):
        corpus = home / ".local/share/sia/corpus"
        path = home / ".local/state/sia/consolidation-originals.json"
        value = json.loads(path.read_text())
        binding = hashlib.sha256(json.dumps({
            "admission": claimed["admission"], "claims": claimed["claims"]},
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        phase = "planned" if cut in {
            "kill-originals-plan", "kill-originals-pin"} else "retained"
        self.assertEqual(value, {"schema": "sia-consolidation-originals-v1",
                                 "binding": binding, "commit": value["commit"],
                                 "phase": phase})
        found = subprocess.run(
            ["git", "-C", str(corpus), "rev-parse", "--verify", "--quiet",
             "refs/sia/consolidation-originals/" + binding],
            capture_output=True, text=True, timeout=10)
        expected = (1, "", "") if cut == "kill-originals-plan" else (
            0, value["commit"] + "\n", "")
        self.assertEqual((found.returncode, found.stdout, found.stderr), expected)
        for relative, raw in original.items():
            self.assertEqual(subprocess.check_output(
                ["git", "-C", str(corpus), "cat-file", "blob",
                 value["commit"] + ":" + relative], timeout=10), raw)
        return value

    def check_replay_and_retention(self, home, returned, original, later=False):
        corpus = home / ".local/share/sia/corpus"
        journal = home / ".local/state/sia/consolidation-snapshot-delivery.json"
        retained = journal.read_bytes()
        before = {path.relative_to(corpus): path.read_bytes()
                  for path in corpus.rglob("*.md") if ".git" not in path.parts}
        self.assertEqual(self.invoke(home, "recover"), returned)
        self.assertEqual(journal.read_bytes(), retained)
        observed = self.invoke(home, "inspect")
        self.assertEqual(observed["admission"], returned["admission"])
        self.assertEqual(observed["coverage"], "selected-claims-only")
        self.assertEqual(observed["unclaimed_days"], [])
        self.assertEqual([item["disposition"] for item in observed["outcomes"]],
                         ["compacted", "compacted"])
        self.assertEqual([item["sources"] for item in observed["outcomes"]],
                         [claim["sources"] for claim in returned["claims"]["claims"]])
        self.assertEqual(journal.read_bytes(), retained)
        self.assertEqual({path.relative_to(corpus): path.read_bytes()
                          for path in corpus.rglob("*.md")
                          if ".git" not in path.parts}, before)
        pin = home / ".local/state/sia/consolidation-originals.json"
        commits = {json.loads(pin.read_text())["commit"]}
        if not later:
            commits.add(returned["admission"]["commit"])
        for commit in commits:
            for relative, raw in original.items():
                self.assertEqual(subprocess.check_output(
                    ["git", "-C", str(corpus), "show", commit + ":" + relative],
                    timeout=10), raw)

    def test_actual_process_cuts_retain_intent_and_resume_exact_effects(self):
        for cut in ("kill-originals-plan", "kill-originals-pin",
                    "kill-originals-retained", "kill-intent", "kill-epoch", "kill-unlink",
                    "kill-return", "kill-persisted"):
            with self.subTest(cut=cut), tempfile.TemporaryDirectory(
                    prefix="sia-execution-cut-") as directory:
                self.check_cut(Path(directory), cut)

    def test_later_originals_survive_fresh_process_retention_and_cleanup_cuts(self):
        for cut in ("kill-originals-plan", "kill-originals-pin",
                    "kill-originals-retained", "kill-unlink"):
            with self.subTest(cut=cut), tempfile.TemporaryDirectory(
                    prefix="sia-later-originals-cut-") as directory:
                self.check_cut(Path(directory), cut, later=True)

    def test_worker_requires_fixture_opt_in(self):
        with tempfile.TemporaryDirectory(prefix="sia-execution-refusal-") as home:
            result = subprocess.run(
                [sys.executable, "-B", str(WORKER), "prepare"],
                env={"HOME": home, "PATH": "/usr/bin:/bin"},
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1)
            self.assertIn("explicit isolated fixture home required", result.stderr)
            self.assertFalse((Path(home) / ".local").exists())


if __name__ == "__main__":
    unittest.main()
