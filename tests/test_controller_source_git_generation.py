"""Descriptor-bound Git generation for one published source closure.

The fixture uses an isolated ordinary Git repository and the system Git
binary.  It proves the adapter's process boundary and returned generation;
it does not authenticate corpus truth, source events, or later engine state.
"""

import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

import sialib


API = "_controller_source_corpus_commit_generation"
KEYS = {
    "schema", "object_format", "git_executable_sha256",
    "before_commit_oid", "corpus_commit_oid", "corpus_tree_oid",
    "clean", "generation_sha256",
}
REFUSALS = (RuntimeError, ValueError, OSError)
BATCH_SHA256 = "a" * 64
CLOSURE_SHA256 = "b" * 64


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


class ControllerSourceGitGeneration(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.path.expanduser("~"), sia_test_home.ISOLATED_HOME)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.corpus = self.root / "corpus"
        self.state = self.root / "state"
        self.corpus.mkdir()
        self.state.mkdir()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in (
                ("CORPUS", str(self.corpus)),
                ("CORPUS_OWNER_LOCK", str(self.state / "corpus-owner.lock")),
                ("LIFECYCLE_LOCK", str(self.state / "lifecycle.lock")),
                ("LIFECYCLE_TOMBSTONE", str(self.state / "lifecycle-removed")),
                ("RESTORE_BARRIER_PATH", str(self.state / "restore.json")),
                ("RESTORE_MASK_PATH", str(self.state / "restore-mask")),
                ("RESTORE_SUPERVISOR_PATH", str(self.state / "restore-supervisor.json")),
                ("GIT", "/usr/bin/git")):
            self.stack.enter_context(mock.patch.object(
                sialib, name, value, create=True))
        self._git("init", "-q", "-b", "fixture")
        (self.corpus / "seed.md").write_text("seed\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("-c", "user.email=sia@omarchy.local",
                  "-c", "user.name=SIA", "commit", "-q", "-m", "seed")

    def _git(self, *args):
        result = subprocess.run(
            ["/usr/bin/git", *args], cwd=self.corpus,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=True, text=True,
            env={**os.environ, "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0"})
        return result.stdout.strip()

    def helper(self):
        value = getattr(sialib, API, None)
        self.assertTrue(callable(value), "missing corpus generation API: " + API)
        return value

    def _call(self):
        return self.helper()(
            source_batch_sha256=BATCH_SHA256,
            event_closure_sha256=CLOSURE_SHA256)

    def _alternate_corpus(self):
        alternate = self.root / "alternate"
        alternate.mkdir()
        self._git("-C", str(alternate), "init", "-q", "-b", "foreign")
        (alternate / "foreign.md").write_text("foreign seed\n", encoding="utf-8")
        self._git("-C", str(alternate), "add", "foreign.md")
        self._git("-C", str(alternate), "-c", "user.email=fixture@example.invalid",
                  "-c", "user.name=Fixture", "commit", "-q", "-m", "foreign")
        return alternate

    def test_ambient_repository_selection_cannot_redirect_corpus_commit(self):
        alternate = self._alternate_corpus()
        before = self._git("rev-parse", "HEAD")
        foreign_head = self._git("-C", str(alternate), "rev-parse", "HEAD")
        foreign_index = (alternate / ".git" / "index").read_bytes()
        (alternate / "pending.md").write_text("foreign pending\n", encoding="utf-8")
        (self.corpus / "intended.md").write_text("intended\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {
                "GIT_DIR": str(alternate / ".git"),
                "GIT_WORK_TREE": str(alternate)}):
            result = self._call()
        self.assertEqual(result["before_commit_oid"], before)
        self.assertNotEqual(result["corpus_commit_oid"], before)
        self.assertEqual(result["corpus_commit_oid"], self._git("rev-parse", "HEAD"))
        self.assertEqual(self._git("status", "--porcelain"), "")
        self.assertEqual(self._git("-C", str(alternate), "rev-parse", "HEAD"),
                         foreign_head)
        self.assertEqual((alternate / ".git" / "index").read_bytes(), foreign_index)
        self.assertEqual(self._git("-C", str(alternate), "status", "--porcelain"),
                         "?? pending.md")

    def test_ambient_index_cannot_replace_the_corpus_index(self):
        external_index = self.root / "external-index"
        (self.corpus / "intended.md").write_text("intended\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"GIT_INDEX_FILE": str(external_index)}):
            result = self._call()
        self.assertFalse(external_index.exists())
        self.assertTrue(result["clean"])
        self.assertEqual(self._git("status", "--porcelain"), "")
        self.assertEqual(self._git("show", "HEAD:intended.md"), "intended")

    def test_git_environment_is_owned_at_every_launch(self):
        inherited = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.worktree",
            "GIT_CONFIG_VALUE_0": str(self.root / "wrong-tree"),
            "GIT_CONFIG_PARAMETERS": "'core.bare=true'",
            "GIT_OBJECT_DIRECTORY": str(self.root / "wrong-objects"),
            "GIT_COMMON_DIR": str(self.root / "wrong-common"),
            "GIT_NAMESPACE": "foreign",
            "SIA_SOURCE_GIT_ENV_TEST": "preserved",
        }
        expected = {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
        }
        real_run = sialib._run_bounded_text_process

        def observed(command, **kwargs):
            environment = kwargs["env"]
            self.assertEqual({key: value for key, value in environment.items()
                              if key.startswith("GIT_")}, expected)
            self.assertEqual(environment["SIA_SOURCE_GIT_ENV_TEST"], "preserved")
            return real_run(command, **kwargs)

        with mock.patch.dict(os.environ, inherited), mock.patch.object(
                sialib, "_run_bounded_text_process", side_effect=observed):
            result = self._call()
        self.assertTrue(result["clean"])

    def test_exact_generation_uses_pinned_executable_and_repository_descriptors(self):
        before = self._git("rev-parse", "HEAD")
        (self.corpus / "events.md").write_text(
            "one exact published generation\n", encoding="utf-8")
        calls = []
        real_run = sialib._run_bounded_text_process

        def observed(command, **kwargs):
            self.assertTrue(command[0].startswith("/proc/self/fd/"))
            self.assertTrue(str(kwargs["cwd"]).startswith("/proc/self/fd/"))
            descriptors = tuple(kwargs.get("pass_fds", ()))
            self.assertGreaterEqual(len(descriptors), 2)
            identities = []
            for descriptor in descriptors:
                info = os.fstat(descriptor)
                identities.append((info.st_dev, info.st_ino, info.st_mode))
            calls.append((tuple(command[1:]), identities))
            return real_run(command, **kwargs)

        with mock.patch.object(
                sialib, "_run_bounded_text_process", side_effect=observed):
            result = self._call()

        self.assertTrue(calls)
        self.assertEqual(set(result), KEYS)
        self.assertEqual(result["schema"],
                         "sia-controller-source-corpus-generation-v1")
        self.assertIn(result["object_format"], ("sha1", "sha256"))
        self.assertEqual(result["before_commit_oid"], before)
        self.assertEqual(result["corpus_commit_oid"],
                         self._git("rev-parse", "HEAD"))
        self.assertEqual(result["corpus_tree_oid"],
                         self._git("rev-parse", "HEAD^{tree}"))
        self.assertEqual(self._git("status", "--porcelain",
                                   "--untracked-files=all"), "")
        self.assertIs(result["clean"], True)
        self.assertEqual(
            result["git_executable_sha256"],
            hashlib.sha256(Path("/usr/bin/git").read_bytes()).hexdigest())
        self.assertEqual(result["generation_sha256"], _digest({
            key: item for key, item in result.items()
            if key != "generation_sha256"
        }))
        self.assertEqual(
            self._git("log", "-1", "--format=%s"),
            "SIA source batch " + BATCH_SHA256)

    def test_clean_retry_returns_the_exact_current_generation_without_a_commit(self):
        (self.corpus / "events.md").write_text("stable\n", encoding="utf-8")
        first = self._call()
        current = self._git("rev-parse", "HEAD")
        retried = self._call()
        self.assertEqual(first["corpus_commit_oid"], current)
        self.assertEqual(retried["before_commit_oid"], current)
        self.assertEqual(retried["corpus_commit_oid"], current)
        self.assertEqual(retried["corpus_tree_oid"],
                         self._git("rev-parse", "HEAD^{tree}"))
        self.assertIs(retried["clean"], True)
        self.assertEqual(self._git("status", "--porcelain",
                                   "--untracked-files=all"), "")

    def test_named_repository_replacement_refuses_without_switching_authority(self):
        (self.corpus / "events.md").write_text("pending\n", encoding="utf-8")
        retired = self.root / "retired-corpus"
        real_run = sialib._run_bounded_text_process
        swapped = False

        def replace_after_first(command, **kwargs):
            nonlocal swapped
            result = real_run(command, **kwargs)
            if not swapped:
                swapped = True
                self.corpus.rename(retired)
                self.corpus.mkdir()
            return result

        with mock.patch.object(
                sialib, "_run_bounded_text_process",
                side_effect=replace_after_first), self.assertRaises(REFUSALS):
            self._call()
        self.assertTrue(swapped)
        self.assertFalse((self.corpus / ".git").exists())

    def test_symlinked_repository_or_executable_refuses_before_subprocess(self):
        corpus_link = self.root / "corpus-link"
        corpus_link.symlink_to(self.corpus, target_is_directory=True)
        executable_link = self.root / "git-link"
        executable_link.symlink_to("/usr/bin/git")
        for name, path in (("CORPUS", corpus_link), ("GIT", executable_link)):
            with self.subTest(name=name), mock.patch.object(
                    sialib, name, str(path)), mock.patch.object(
                    sialib, "_run_bounded_text_process",
                    side_effect=AssertionError("unsafe boundary executed")), \
                    self.assertRaises(REFUSALS):
                self._call()


if __name__ == "__main__":
    unittest.main()
