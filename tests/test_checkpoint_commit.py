"""Real Git commit of compact pages, with unchanged source authority."""

import copy
import subprocess
import unittest
from unittest import mock

import siacheckpointcontent as content
from tests import test_checkpoint_adoption as fixtures


class CheckpointCommit(unittest.TestCase):
    def test_actual_git_cut_retry_and_false_generation_refusal(self):
        self.assertTrue(callable(getattr(content, "commit_pages", None)), "missing compact corpus commit")
        case = fixtures.CheckpointAdoption(methodName="runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        with case.prepared() as (f, owner, package, request):
            def git(*args):
                return subprocess.run(["/usr/bin/git", *args], cwd=owner.CORPUS,
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    check=True, text=True).stdout.strip()

            git("init", "-q", "-b", "fixture")
            git("add", "-A")
            git("-c", "user.email=sia@omarchy.local", "-c", "user.name=SIA", "commit", "-q", "-m", "fixture parent")
            parent = git("rev-parse", "HEAD")
            adoption = case.api
            adoption.adopt_root(vars(owner), **request)
            args = {k: v for k, v in request.items() if k not in {
                "journal_limits", "expected_journal_limits_sha256", "expected_adoption_sha256"}}
            adoption.stage_live_binding(vars(owner), **args)
            adoption.stage_status_effects(vars(owner), **args, started_at=f.status["ts"])
            args.pop("seq")
            before = copy.deepcopy(args["memo"])
            with mock.patch.object(owner, "GIT", "/usr/bin/git"):
                result = content.commit_pages(vars(owner), **args)
                self.assertEqual(result["status"], "pages-committed-not-indexed")
                generation = result["corpus_generation"]
                self.assertEqual(generation["before_commit_oid"], parent)
                self.assertNotEqual(generation["corpus_commit_oid"], parent)
                self.assertEqual(generation["corpus_commit_oid"], git("rev-parse", "HEAD"))
                self.assertEqual(generation["corpus_tree_oid"], git("rev-parse", "HEAD^{tree}"))
                self.assertEqual(git("status", "--porcelain"), "")
                retried = content.commit_pages(vars(owner), **args)
                self.assertEqual(retried["corpus_generation"]["corpus_commit_oid"], generation["corpus_commit_oid"])
                with mock.patch.object(owner, "_controller_source_corpus_commit_generation_v2", return_value={}):
                    with self.assertRaises(ValueError):
                        content.commit_pages(vars(owner), **args)
            self.assertEqual(args["memo"], before)
            self.assertEqual(owner.load_memo(), before)
