"""Admitted immutable traversal under continuing worktree and HEAD changes."""
import copy
import importlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from tests import test_epoch_exemplar_coverage as fixture_module


class ConsolidationDiscovery(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.EpochExemplarCoverage(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.lib.CORPUS_OWNER_LOCK = str(Path(self.lib.STATE) / "corpus-owner.lock")
        self.admission = importlib.import_module("siaconsolidationadmission")
        self.discovery = importlib.import_module("siaconsolidationdiscovery")
        self.old = [self.fixture._day(day, ("OBS",))
                    for day in ("2026-01-05", "2026-01-06", "2026-01-07")]
        self.current = self.fixture._day("2026-10-20", ("OBS",))
        self.original = {path: path.read_bytes() for path in self.old}
        self.fixture._commit()
        self.journal = Path(self.lib.STATE) / "consolidation-snapshot-admission.json"

    def start(self, commit=None):
        if commit is None:
            commit = self.git("rev-parse", "HEAD")
        self.record = self.admission.admit(
            self.lib, generation="a" * 32, transaction="b" * 64,
            cutoff="2026-10-06", commit=commit)
        self.before = self.journal.read_bytes()

    def git(self, *arguments):
        # Every test-created commit has its own identity. Never depend on a
        # developer's global Git config or signing agent being present in CI.
        return subprocess.check_output(
            ["git", "-c", "user.name=SIA Fixture",
             "-c", "user.email=sia-fixture@example.invalid",
             "-c", "commit.gpgsign=false", "-C", self.lib.CORPUS, *arguments],
            text=True, timeout=10).strip()

    def test_discovery_finishes_with_continuing_writes_and_preserves_arrival(self):
        self.start()
        cursor, found = None, []
        late = None
        for attempt in range(32):
            step = self.discovery.discover(self.lib, self.record, cursor, budget=1)
            # The input cursor remains unchanged; replay emits the same batch.
            self.assertEqual(self.discovery.discover(
                self.lib, self.record, cursor, budget=1), step)
            following = json.loads(json.dumps(step["cursor"]))
            self.assertNotEqual(cursor, following)
            found.extend(step["candidates"])
            if late is None:
                late = self.fixture._day("2026-01-08", ("OBS",))
            self.lib.atomic_write(str(self.current),
                                  self.current.read_text() + f"\nwrite {attempt}\n")
            self.fixture._commit()
            cursor = following
            if cursor["complete"]:
                break
        self.assertTrue(cursor["complete"])
        expected = [path.relative_to(self.lib.CORPUS).as_posix() for path in self.old]
        self.assertEqual([entry["relative"] for entry in found], expected)
        for entry in found:
            self.assertEqual(entry["blob"], self.git(
                "rev-parse", self.record["commit"] + ":" + entry["relative"]))
        self.assertNotEqual(self.git("rev-parse", "HEAD"), self.record["commit"])
        self.assertEqual({path: path.read_bytes() for path in self.old}, self.original)
        self.assertTrue(late.exists())
        self.assertEqual(self.journal.read_bytes(), self.before)
        self.assertEqual(self.discovery.discover(
            self.lib, self.record, cursor, budget=1),
            {"cursor": cursor, "candidates": []})
        self.assertFalse(self.fixture.epoch.exists())

    def test_invalid_cursor_and_admission_bindings_refuse(self):
        self.start()
        state = self.discovery.discover(self.lib, self.record, budget=1)["cursor"]
        root = copy.deepcopy(state)
        root["frames"][0]["tree"] = self.git("rev-parse", "HEAD:events")
        wrong_child = copy.deepcopy(state)
        wrong_child["frames"][-1]["tree"] = self.git("rev-parse", "HEAD:events/org")
        bad_offset = copy.deepcopy(state)
        bad_offset["frames"][0]["offset"] = True
        bad_identity = copy.deepcopy(state)
        bad_identity["admission"]["transaction"] = "c" * 64
        false_complete = copy.deepcopy(state)
        false_complete["complete"] = True
        for value in (root, wrong_child, bad_offset, bad_identity, false_complete):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.discovery.discover(self.lib, self.record, value, budget=1)
        for budget in (0, True, 1025):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                self.discovery.discover(self.lib, self.record, budget=budget)
        with self.assertRaisesRegex(ValueError, "admission differs"):
            self.discovery.discover(
                self.lib, dict(self.record, transaction="c" * 64))
        with self.assertRaisesRegex(ValueError, "requires admitted"):
            self.discovery.discover(self.lib, dict(self.record, phase="planned"))
        self.assertEqual(self.journal.read_bytes(), self.before)

    def test_missing_admitted_pin_refuses_without_recreation(self):
        self.start()
        ref = "refs/sia/consolidation/" + self.record["generation"]
        self.git("update-ref", "-d", ref, self.record["commit"])
        with self.assertRaisesRegex(ValueError, "missing or differs"):
            self.discovery.discover(self.lib, self.record)
        result = subprocess.run(
            ["git", "-C", self.lib.CORPUS, "rev-parse", "--verify", "--quiet", ref],
            capture_output=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (1, b"", b""))
        self.assertEqual(self.journal.read_bytes(), self.before)

    def collect(self, budget):
        cursor, found = None, []
        for _attempt in range(64):
            original = copy.deepcopy(cursor)
            result = self.discovery.discover(self.lib, self.record, cursor,
                                            budget=budget)
            self.assertEqual(cursor, original)
            self.assertLessEqual(len(result["candidates"]), budget)
            found.extend(result["candidates"])
            cursor = json.loads(json.dumps(result["cursor"]))
            if cursor["complete"]:
                return found
        self.fail("fixture discovery did not complete within attempt bound")

    def test_batched_multiple_organs_shards_and_cutoff_endpoints(self):
        directory = Path(self.lib.CORPUS) / "events/zeta"
        directory.mkdir()
        # Contents are opaque to discovery; live-source validation is separate.
        names = ["2026-10-05.md", "2026-10-05-part-2.md", "2026-10-06.md",
                 "2026-10-07.md", "2026-02-30.md", "notes.txt"]
        for name in names:
            (directory / name).write_bytes(self.original[self.old[0]])
        self.fixture._commit()
        self.start()
        single = self.collect(1)
        batched = self.collect(32)
        self.assertEqual(single, batched)
        self.assertEqual([entry["relative"] for entry in batched], [
            "events/org/2026-01-05.md", "events/org/2026-01-06.md",
            "events/org/2026-01-07.md", "events/zeta/2026-10-05-part-2.md",
            "events/zeta/2026-10-05.md"])
        self.assertEqual([entry["part"] for entry in batched[-2:]], [2, 1])
        self.assertEqual(self.journal.read_bytes(), self.before)
        for name in names:
            self.assertEqual((directory / name).read_bytes(),
                             self.original[self.old[0]])

    def empty_tree_commit(self, *, events):
        def tree(text):
            return subprocess.check_output(
                ["git", "-C", self.lib.CORPUS, "mktree"],
                input=text, text=True, timeout=10).strip()
        root = tree("")
        if events:
            root = tree(f"040000 tree {root}\tevents\n")
        return self.git("-c", "user.name=Fixture", "-c", "user.email=t@t",
                        "commit-tree", root, "-m", "empty tree fixture")

    def test_empty_corpus_tree_completes(self):
        self.start(self.empty_tree_commit(events=False))
        self.assertEqual(self.collect(1), [])
        self.assertEqual(self.journal.read_bytes(), self.before)

    def test_empty_events_tree_completes(self):
        self.start(self.empty_tree_commit(events=True))
        self.assertEqual(self.collect(1), [])
        self.assertEqual(self.journal.read_bytes(), self.before)

    def test_failed_descendant_read_preserves_input_for_exact_retry(self):
        self.start()
        cursor = self.discovery.discover(self.lib, self.record, budget=2)["cursor"]
        original = copy.deepcopy(cursor)
        target = self.git("rev-parse", "HEAD:events/org")
        actual = self.discovery.snapshot.tree_page

        def fail(run, corpus, identity, offset, limit):
            if identity == target and offset > 0:
                raise RuntimeError("injected descendant read failure")
            return actual(run, corpus, identity, offset, limit)

        with mock.patch.object(self.discovery.snapshot, "tree_page", fail):
            with self.assertRaisesRegex(RuntimeError, "descendant read failure"):
                self.discovery.discover(self.lib, self.record, cursor, budget=32)
        self.assertEqual(cursor, original)
        retry = self.discovery.discover(self.lib, self.record, cursor, budget=2)
        self.assertEqual([entry["relative"] for entry in retry["candidates"]],
                         ["events/org/2026-01-05.md", "events/org/2026-01-06.md"])
        self.assertEqual(self.journal.read_bytes(), self.before)

    def test_forged_completed_cursor_demonstrates_untrusted_history_boundary(self):
        self.start()
        forged = {"schema": self.discovery.SCHEMA, "admission": self.record,
                  "frames": [], "complete": True}
        # A deliberately retained negative result: shape checks do not prove
        # traversal history. Production must own and authenticate that history.
        result = self.discovery.discover(self.lib, self.record, forged, budget=1)
        self.assertEqual(result, {"cursor": forged, "candidates": []})
        self.assertTrue(self.old[0].exists())


if __name__ == "__main__":
    unittest.main()
