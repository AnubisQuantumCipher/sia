"""Real Git commit of compact pages, with unchanged source authority."""

import copy
import subprocess
import unittest
from unittest import mock

import siacheckpointcontent as content
from tests import test_checkpoint_adoption as fixtures


class CheckpointCommit(unittest.TestCase):
    def test_actual_git_cut_retry_and_false_generation_refusal(self):
        self.exercise(synchronize=False)

    def test_sync_binds_actual_commit_to_controlled_engine_observations(self):
        self.assertTrue(callable(getattr(content, "synchronize", None)), "missing compact index synchronization")
        self.exercise(synchronize=True)

    def test_compact_effects_pending_binds_content_status_and_live_pulse(self):
        self.assertTrue(callable(getattr(content.effects, "prepare_checkpoint_pending", None)), "missing compact effects pending preparation")
        self.effects_pending = True
        self.exercise(synchronize=True)

    def exercise(self, *, synchronize):
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
                if synchronize:
                    self.sync_case(f, owner, args, before, git)
                    return
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

    def sync_case(self, f, owner, args, before, git):
        # These are explicitly controlled engine observations, not a real
        # gbrain run. Actual source adoption, pages and Git remain in use.
        malformed = []

        def observed(*, corpus_generation, target_versions):
            self.assertEqual(corpus_generation["corpus_commit_oid"], git("rev-parse", "HEAD"))
            manifest = [{**row, "page_state": "live", "parse_error_codes": [],
                "expected_projection_sha256": "4" * 64, "current_projection_sha256": "4" * 64,
                "current_content_hash": "4" * 64, "current_content_hash_match": True,
                "projection_match": True} for row in target_versions]
            generation = f.case.effects._sync_generation(manifest,
                sync_requested_commit=corpus_generation["corpus_commit_oid"],
                status_last_commit=corpus_generation["corpus_commit_oid"], local_path=str(owner.CORPUS))
            result = {"sync_generation": generation, "target_manifest": manifest,
                      "target_manifest_sha256": content.adoption.transaction.live._sha(manifest)}
            if malformed:
                result["target_manifest_sha256"] = "0" * 64
            return result

        with mock.patch.object(owner, "_controller_source_sync_generation", side_effect=observed):
            result = content.synchronize(vars(owner), **args)
            self.assertEqual(result["status"], "content-index-synchronized-not-live")
            self.assertEqual(result["sync_generation"]["status_last_commit"], git("rev-parse", "HEAD"))
            self.assertTrue(result["target_manifest"])
            if getattr(self, "effects_pending", False):
                self.check_pending(owner, args, result)
            malformed.append(True)
            with self.assertRaises(ValueError):
                content.synchronize(vars(owner), **args)
        self.assertEqual(args["memo"], before)
        self.assertEqual(owner.load_memo(), before)

    def check_pending(self, owner, args, indexed):
        adoption, effects = content.adoption, content.effects
        live, source = adoption.transaction.live, adoption.source
        view = adoption.read_pending(vars(owner), **args)
        artifacts = view["package"]["artifacts"]
        batch, transition = artifacts["capture"], artifacts["transition"]
        binding = args["memo"]["controller_source_live_pending"]
        handoff = args["memo"]["pulse_status_effects_pending"]
        graph_generation, graph = effects._graph_generation(vars(owner), source, live)
        status = effects._project_status(vars(owner), source, live, args["admitted_status"],
            binding, handoff, transition, graph, args["memo"]["pulse_history"], args["admitted_status"]["ts"])
        pages = indexed["committed"]["pages"]
        gist = pages["gist_publication"]
        supplied = dict(admitted_status=args["admitted_status"], batch=batch, binding=binding, handoff=handoff, candidate=artifacts["candidate"],
            transition=transition, closure_result=pages["closure_result"], target_manifest=indexed["target_manifest"],
            corpus_generation=indexed["committed"]["corpus_generation"], sync_generation=indexed["sync_generation"],
            graph_generation=graph_generation, status_generation=effects._status_generation_value(vars(owner), source, live, status),
            status=status, content_fields={"gist_page_plan_sha256": gist["plan_sha256"],
                "gist_pages_sha256": gist["gist_pages_sha256"], "gist_publication": gist,
                "content_publication_sha256": pages["content_publication_sha256"]})
        pending = effects.prepare_checkpoint_pending(vars(owner), **supplied)
        self.assertEqual(pending["schema"], "sia-controller-source-effects-pending-v2")
        self.assertEqual(pending["source_batch_sha256"], batch["batch_sha256"])
        self.assertEqual(pending["transition_sha256"], transition["transition_sha256"])
        self.assertEqual(pending["gist_publication"], gist)
        altered = copy.deepcopy(status)
        altered["workspace"] = []
        altered["publication_id"] = "0" * 32
        with self.assertRaises(ValueError):
            effects.prepare_checkpoint_pending(vars(owner), **{**supplied, "status": altered})
        truncated = copy.deepcopy(status)
        truncated["history"] = [truncated["history"][-1]]
        with self.assertRaises(ValueError):
            effects.prepare_checkpoint_pending(vars(owner), **{**supplied, "status": truncated,
                "status_generation": effects._status_generation_value(vars(owner), source, live, truncated)})
