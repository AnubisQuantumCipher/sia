"""Experimental namespace reader; no integration/authorization acceptance."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from tests import test_epoch_exemplar_coverage as fixture_module

PATH = Path(__file__).resolve().parents[1] / "bin/siaconsolidationsnapshot.py"
SPEC = importlib.util.spec_from_file_location("snapshot_fixture", PATH)
snapshot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshot)


class ConsolidationSnapshot(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.EpochExemplarCoverage(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib

    def git(self, *args):
        return subprocess.check_output(
            ["/usr/bin/git", "-C", self.lib.CORPUS, *args],
            text=True, timeout=10).strip()

    def test_pinned_tree_survives_updates_and_new_head(self):
        first = self.fixture._day("2026-01-05", ("OBS",))
        self.fixture._day("2026-01-06", ("OBS",))
        self.fixture._commit()
        original = first.read_bytes()
        tree = self.git("rev-parse", "HEAD:events/org")
        run = self.lib._run_bounded_text_process
        page = snapshot.tree_page(run, self.lib.CORPUS, tree, 0, 1)
        first.write_bytes(original + b"\n")
        self.fixture._day("2026-01-07", ("OBS",))
        self.fixture._commit()
        following = snapshot.tree_page(run, self.lib.CORPUS, tree, page["next"], 1)
        self.assertEqual([page["entries"][0]["name"], following["entries"][0]["name"]],
                         ["2026-01-05.md", "2026-01-06.md"])
        self.assertTrue(following["complete"])
        self.assertEqual(snapshot.tree_page(run, self.lib.CORPUS, tree, 0, 1), page)
        newer = self.git("rev-parse", "HEAD:events/org")
        self.assertNotEqual(newer, tree)
        self.assertEqual(len(snapshot.tree_page(
            run, self.lib.CORPUS, newer, 0, 3)["entries"]), 3)
        self.git("replace", tree, newer)
        self.assertEqual(snapshot.tree_page(run, self.lib.CORPUS, tree, 0, 1), page)
        blob = page["entries"][0]["object"]
        with self.assertRaisesRegex(ValueError, "not an available tree"):
            snapshot.tree_page(run, self.lib.CORPUS, blob, 0, 1)
        with self.assertRaisesRegex(ValueError, "exceeds tree entries"):
            snapshot.tree_page(run, self.lib.CORPUS, tree, 3, 1)
        with self.assertRaises(ValueError):
            snapshot.tree_page(run, self.lib.CORPUS, "0" * 40, 0, 1)

    def test_malformed_names_types_and_bounds_refuse(self):
        oid = "a" * 40
        valid = f"100644 blob {oid}\tday.md\0"
        for text in (valid[:-1], valid + valid,
                     valid.replace("100644 blob", "120000 blob"),
                     valid.replace("day.md", "../day.md"),
                     valid.replace("day.md", "bad\nname"),
                     valid.replace(oid, "HEAD"),
                     valid * (snapshot.MAX_TREE_ENTRIES + 1)):
            with self.subTest(text_length=len(text)), self.assertRaises(ValueError):
                snapshot.parse_tree(text)
        for identity, offset, limit in (
                ("HEAD", 0, 1), (oid, True, 1), (oid, -1, 1),
                (oid, 0, 0), (oid, 0, snapshot.MAX_PAGE_ENTRIES + 1)):
            with self.assertRaises(ValueError):
                snapshot.tree_page(None, self.lib.CORPUS, identity, offset, limit)
        with mock.patch.object(snapshot, "MAX_TREE_BYTES", 10):
            with self.assertRaisesRegex(ValueError, "byte bound"):
                snapshot.parse_tree(valid)

    def test_retention_pin_survives_collection_and_refuses_conflict(self):
        day = self.fixture._day("2026-01-05", ("OBS",))
        self.fixture._commit()
        commit = self.git("rev-parse", "HEAD")
        tree = self.git("rev-parse", "HEAD:events/org")
        run = self.lib._run_bounded_text_process
        generation = "a" * 32
        pin = snapshot.pin_commit(run, self.lib.CORPUS, generation, commit)
        self.assertEqual(snapshot.pin_commit(
            run, self.lib.CORPUS, generation, commit), pin)
        day.write_bytes(day.read_bytes() + b"\n")
        self.fixture._commit()
        # Make HEAD a new root so it cannot keep the original commit reachable.
        new_tree = self.git("rev-parse", "HEAD^{tree}")
        root = self.git("-c", "user.name=Fixture", "-c", "user.email=t@t",
                        "commit-tree", new_tree, "-m", "independent root")
        self.git("update-ref", "HEAD", root)
        with self.assertRaisesRegex(ValueError, "bound differently"):
            snapshot.pin_commit(run, self.lib.CORPUS, generation, root)
        self.git("pack-refs", "--all", "--prune")
        self.assertEqual(snapshot.pin_commit(
            run, self.lib.CORPUS, generation, commit), pin)
        self.git("reflog", "expire", "--expire=now", "--all")
        self.git("gc", "--prune=now")
        self.assertEqual(self.git("rev-parse", pin["ref"]), commit)
        self.assertEqual(snapshot.check_pin(
            run, self.lib.CORPUS, generation, commit), pin)
        self.assertEqual(snapshot.tree_page(
            run, self.lib.CORPUS, tree, 0, 1)["entries"][0]["name"],
                         "2026-01-05.md")
        # Negative control: exact fixture-only pin removal permits collection.
        self.git("update-ref", "-d", pin["ref"], commit)
        with self.assertRaisesRegex(ValueError, "missing or differs"):
            snapshot.check_pin(run, self.lib.CORPUS, generation, commit)
        self.git("reflog", "expire", "--expire=now", "--all")
        self.git("gc", "--prune=now")
        absent = subprocess.run(
            ["/usr/bin/git", "-C", self.lib.CORPUS, "cat-file", "-e", commit],
            capture_output=True, timeout=10)
        self.assertEqual((absent.returncode, absent.stdout, absent.stderr),
                         (1, b"", b""))
        self.assertEqual(self.git("cat-file", "-t", root), "commit")

    def test_symbolic_pin_refuses_without_mutating_its_target(self):
        self.fixture._day("2026-01-05", ("OBS",))
        self.fixture._commit()
        commit = self.git("rev-parse", "HEAD")
        generation = "b" * 32
        name = "refs/sia/consolidation/" + generation
        target = self.git("symbolic-ref", "HEAD")
        self.git("symbolic-ref", name, target)
        with self.assertRaisesRegex(ValueError, "direct reference"):
            snapshot.pin_commit(
                self.lib._run_bounded_text_process,
                self.lib.CORPUS, generation, commit)
        self.assertEqual(self.git("symbolic-ref", name), target)
        self.assertEqual(self.git("rev-parse", target), commit)


if __name__ == "__main__":
    unittest.main()
