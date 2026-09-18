"""Real Git commit of compact pages, with unchanged source authority."""

import copy
import hashlib
import importlib
from pathlib import Path
import subprocess
import unittest
from unittest import mock

import siacheckpointcontent as content
from tests import test_checkpoint_adoption as fixtures


class CheckpointCommit(unittest.TestCase):
    def test_compact_driver_completes_adopted_transaction_and_retries(self):
        self.driver_api = importlib.import_module("siacheckpointrunner")
        self.exercise(synchronize=True)

    def test_compact_driver_recovers_after_source_archive_move(self):
        self.driver_api = importlib.import_module("siacheckpointrunner")
        self.interrupt_driver = True
        self.exercise(synchronize=True)

    def test_acknowledged_compact_parent_retention_and_historical_read(self):
        import siacheckpointparent
        self.assertTrue(callable(getattr(siacheckpointparent, "retain_checkpoint_live", None)),
            "missing acknowledged compact parent retention")
        self.check_compact_parent = True
        self.driver_api = importlib.import_module("siacheckpointrunner")
        self.exercise(synchronize=True)

    def test_durable_package_selection_drives_recurring_dispatch(self):
        self.dispatch_api = importlib.import_module("siacheckpointdispatch")
        self.driver_api = importlib.import_module("siacheckpointrunner")
        self.exercise(synchronize=True)

    def test_successor_extends_the_chain_from_the_acknowledged_compact_parent(self):
        import siahistoryroot
        self.assertTrue(callable(getattr(siahistoryroot, "prepare_successor", None)),
            "missing compact successor chain link")
        self.check_successor = True
        self.dispatch_api = importlib.import_module("siacheckpointdispatch")
        self.driver_api = importlib.import_module("siacheckpointrunner")
        self.exercise(synchronize=True)

    def test_dispatch_recovers_after_marker_written_before_adoption(self):
        self.dispatch_api = importlib.import_module("siacheckpointdispatch")
        self.recover_before_adoption = True
        self.driver_api = importlib.import_module("siacheckpointrunner")
        self.exercise(synchronize=True)

    def test_dispatch_recovers_after_interrupted_marker_retirement(self):
        self.dispatch_api = importlib.import_module("siacheckpointdispatch")
        self.interrupt_retire = True
        self.driver_api = importlib.import_module("siacheckpointrunner")
        self.exercise(synchronize=True)

    def test_actual_git_cut_retry_and_false_generation_refusal(self):
        self.exercise(synchronize=False)

    def test_sync_binds_actual_commit_to_controlled_engine_observations(self):
        self.assertTrue(callable(getattr(content, "synchronize", None)), "missing compact index synchronization")
        self.exercise(synchronize=True)

    def test_compact_effects_pending_binds_content_status_and_live_pulse(self):
        self.assertTrue(callable(getattr(content.effects, "prepare_checkpoint_pending", None)), "missing compact effects pending preparation")
        self.effects_pending = True
        self.exercise(synchronize=True)

    def test_durable_compact_effects_stage_and_retry(self):
        self.stage_api = importlib.import_module("siacheckpointeffects")
        self.exercise(synchronize=True)

    def test_parent_live_artifacts_retained_before_graph_advance(self):
        import siacheckpointparent
        self.assertTrue(callable(getattr(siacheckpointparent, "retain_live", None)), "missing parent live retention")
        self.check_parent_live = True
        self.stage_api = importlib.import_module("siacheckpointeffects")
        self.exercise(synchronize=True)

    def test_parent_live_retention_recovers_after_partial_copy(self):
        self.check_parent_live = True
        self.interrupt_parent_live = True
        self.stage_api = importlib.import_module("siacheckpointeffects")
        self.exercise(synchronize=True)

    def test_historical_parent_reader_survives_current_live_file_replacement(self):
        import siacheckpointparent
        self.assertTrue(callable(getattr(siacheckpointparent, "hold_live", None)), "missing retained parent reader")
        self.read_parent_live = True
        self.stage_api = importlib.import_module("siacheckpointeffects")
        self.exercise(synchronize=True)

    def test_compact_successor_live_publication_and_retry(self):
        self.live_api = importlib.import_module("siacheckpointlive")
        self.stage_api = importlib.import_module("siacheckpointeffects")
        self.exercise(synchronize=True)

    def test_compact_successor_recovers_each_durable_live_boundary(self):
        self.interrupt_live = True
        self.live_api = importlib.import_module("siacheckpointlive")
        self.stage_api = importlib.import_module("siacheckpointeffects")
        self.exercise(synchronize=True)

    def test_compact_effects_finalize_and_durable_retry(self):
        self.live_api = importlib.import_module("siacheckpointlive")
        self.assertTrue(callable(getattr(self.live_api, "finalize", None)), "missing compact effects finalization")
        self.finalize_effects = True
        self.stage_api = importlib.import_module("siacheckpointeffects")
        self.exercise(synchronize=True)

    def test_compact_source_acknowledgment_and_completed_retry(self):
        import siasourceack
        self.assertTrue(callable(getattr(siasourceack, "acknowledge_checkpoint", None)), "missing compact source acknowledgment")
        self.ack_api = siasourceack
        self.finalize_effects = True
        self.live_api = importlib.import_module("siacheckpointlive")
        self.stage_api = importlib.import_module("siacheckpointeffects")
        self.exercise(synchronize=True)

    def test_compact_source_ack_recovers_each_durable_boundary(self):
        import siasourceack
        self.ack_api = siasourceack
        self.interrupt_ack = True
        self.finalize_effects = True
        self.live_api = importlib.import_module("siacheckpointlive")
        self.stage_api = importlib.import_module("siacheckpointeffects")
        self.exercise(synchronize=True)

    def test_compact_effects_reload_after_durable_interruption(self):
        self.stage_api = importlib.import_module("siacheckpointeffects")
        self.interrupt_effects = True
        self.exercise(synchronize=True)

    def test_compact_effects_retry_after_graph_advance_before_memo(self):
        self.stage_api = importlib.import_module("siacheckpointeffects")
        self.interrupt_graph = True
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
            if hasattr(self, "dispatch_api"):
                self.record_package(owner, f, request)
            if not getattr(self, "recover_before_adoption", False):
                adoption.adopt_root(vars(owner), **request)
            args = {k: v for k, v in request.items() if k not in {
                "journal_limits", "expected_journal_limits_sha256", "expected_adoption_sha256"}}
            if not hasattr(self, "driver_api"):
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
            if hasattr(self, "driver_api"):
                self.driver_case(f, owner, args)
                return
            if hasattr(self, "stage_api"):
                self.stage_case(f, owner, args, before)
                return
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

    def driver_case(self, f, owner, args):
        from tests import test_controller_source_effects as effects_fixture
        graph = f.case.effects._new_graph()
        graph["publication_id"] = "4" * 32
        def export():
            owner.atomic_write(owner.GRAPH_PATH, owner.json.dumps(graph), mode=0o600)
        request = {key: value for key, value in args.items() if key not in {"memo", "admitted_status"}}
        request["started_at"] = f.status["ts"]
        with mock.patch.object(owner, "_export_graph_publication", side_effect=export), \
                mock.patch.object(owner, "_controller_source_effects_observed_at", return_value=effects_fixture.STATUS_AT):
            if hasattr(self, "dispatch_api"):
                self.dispatch_case(owner, args, request)
                return
            if getattr(self, "interrupt_driver", False):
                def interrupted(name):
                    if name == "archive-durable":
                        raise OSError("controlled driver archived-source interruption")
                with mock.patch.object(owner, "_controller_source_ack_boundary", side_effect=interrupted):
                    with self.assertRaisesRegex(OSError, "controlled driver archived-source interruption"):
                        self.driver_api.complete_adopted(vars(owner), **request)
                self.assertFalse(Path(owner.CONTROLLER_SOURCE_BATCH_PATH).exists())
                self.assertNotIn("ready", owner.load_memo())
            view = self.driver_api.complete_adopted(vars(owner), **request)
        memo = owner.load_memo()
        self.assertEqual(view["status"], "available")
        self.assertIn("ready", memo)
        self.assertFalse(Path(owner.CONTROLLER_SOURCE_BATCH_PATH).exists())
        self.assertFalse(self.driver_api.ack._PENDING_ONLY.intersection(memo))
        with mock.patch.object(owner, "atomic_write", side_effect=AssertionError("driver retry wrote")), \
                mock.patch.object(owner, "_controller_source_sync_generation", side_effect=AssertionError("driver retry synchronized")), \
                mock.patch.object(owner, "_export_graph_publication", side_effect=AssertionError("driver retry exported")):
            retried = self.driver_api.complete_adopted(vars(owner), **request)
        self.assertEqual(retried, view)
        with mock.patch.object(owner, "atomic_write", side_effect=AssertionError("invalid retry wrote")):
            with self.assertRaises(ValueError) as refused:
                self.driver_api.complete_adopted(vars(owner), **{**request, "started_at": "different"})
        self.assertEqual(refused.exception.reason, "checkpoint-runner-completed-start-differs")
        if getattr(self, "check_compact_parent", False):
            import siacheckpointparent as parents
            committed = memo["controller_source_committed"]
            status = owner.json.loads(Path(owner.STATUS_PATH).read_bytes())
            retained = dict(directory=args["directory"], committed=committed)
            parents.retain_graph(vars(owner), **retained)
            self.assertTrue(parents.retain_checkpoint_live(vars(owner), **retained,
                memo=memo, admitted_status=status))
            with mock.patch.object(owner.siaqueue, "fixed_atomic_publish", side_effect=AssertionError("parent retry wrote")):
                self.assertFalse(parents.retain_checkpoint_live(vars(owner), **retained,
                    memo=memo, admitted_status=status))
            for path in (owner.STATUS_PATH, owner.GRAPH_PATH, owner.LIVE_CANDIDATE_PATH, owner.LIVE_STATE_PATH):
                owner.atomic_write(path, "{}", mode=0o600)
            with parents.hold_checkpoint_live(vars(owner), **retained) as historical:
                self.assertEqual(historical["authority"], "historical-parent-not-current-readiness")
                self.assertEqual(historical["batch"], view["batch"])
                self.assertEqual(historical["status"], status)
            with self.assertRaises(ValueError):
                with parents.hold_live(vars(owner), **retained):
                    self.fail("legacy parent reader admitted compact source")
            wrong = {**committed, "live_generation_sha256": "0" * 64}
            with self.assertRaises(ValueError):
                with parents.hold_checkpoint_live(vars(owner), **{**retained, "committed": wrong}):
                    self.fail("compact parent reader admitted wrong predecessor")

    def record_package(self, owner, f, request):
        """Bind the package pins durably before the transaction is adopted."""
        api = self.dispatch_api
        pins = dict(directory=request["directory"],
            expected_manifest_sha256=request["expected_manifest_sha256"],
            expected_root_sha256=request["expected_root_sha256"],
            started_at=f.status["ts"], seq=request["seq"])
        self.assertTrue(api.record(vars(owner), memo=request["memo"], **pins))
        self.assertFalse(api.record(vars(owner), memo=request["memo"], **pins))
        with mock.patch.object(owner, "atomic_write", side_effect=AssertionError("record retry wrote")):
            self.assertFalse(api.record(vars(owner), memo=request["memo"], **pins))
        with self.assertRaises(ValueError) as refused:
            api.record(vars(owner), memo=request["memo"], **{**pins, "started_at": "different"})
        self.assertEqual(refused.exception.reason, "checkpoint-dispatch-marker-differs")
        self.assertIn(api._MARKER, owner.load_memo())
        # A present but malformed marker is a refusal, never a free slot.
        durable = owner.load_memo()
        owner.atomic_write(owner.MEMO_PATH,
            owner.json.dumps({**durable, api._MARKER: None}), mode=0o600)
        with self.assertRaises(ValueError) as refused:
            api.record(vars(owner), memo=owner.load_memo(), **pins)
        self.assertEqual(refused.exception.reason, "checkpoint-dispatch-marker-shape")
        owner.atomic_write(owner.MEMO_PATH, owner.json.dumps(durable), mode=0o600)
        self.premises = {key: request[key] for key in (
            "journal_limits", "expected_journal_limits_sha256", "expected_adoption_sha256")}

    def dispatch_case(self, owner, args, request):
        """Finish the recorded package from durable state, holding no pins."""
        api = self.dispatch_api
        sha = content.adoption.transaction.live._sha
        selected = api.select(vars(owner), memo=owner.load_memo())
        self.assertEqual(selected["directory"], request["directory"])
        self.assertEqual(selected["manifest_sha256"], request["expected_manifest_sha256"])
        self.assertEqual(selected["root_sha256"], request["expected_root_sha256"])
        self.assertEqual(selected["started_at"], request["started_at"])
        if getattr(self, "recover_before_adoption", False):
            self.recover_case(owner, args, selected)
            return
        self.assertEqual(selected["source_batch_sha256"],
            owner.load_memo()["controller_source_pending"]["batch_sha256"])

        durable = owner.load_memo()

        def replace(marker):
            owner.atomic_write(owner.MEMO_PATH,
                owner.json.dumps({**durable, api._MARKER: marker}), mode=0o600)

        def refuses(reason):
            with mock.patch.object(owner, "atomic_write", side_effect=AssertionError("refused dispatch wrote")):
                with self.assertRaises(ValueError) as refused:
                    api.dispatch(vars(owner))
            self.assertEqual(refused.exception.reason, reason)

        # A mutated pin without a recomputed digest is caught by the digest.
        replace({**selected, "source_batch_sha256": "0" * 64})
        refuses("checkpoint-dispatch-marker-digest")
        # A consistently re-digested marker still cannot name a package that
        # durable state does not actually show adopted or acknowledged.
        forged = {key: value for key, value in selected.items() if key != "marker_sha256"}
        forged["source_batch_sha256"] = "0" * 64
        replace({**forged, "marker_sha256": sha(forged)})
        refuses("checkpoint-dispatch-package-not-adopted")
        owner.atomic_write(owner.MEMO_PATH, owner.json.dumps(durable), mode=0o600)

        if getattr(self, "interrupt_retire", False):
            actual_write = owner.atomic_write

            def interrupted(path, text, *args, **kwargs):
                if path == owner.MEMO_PATH and api._MARKER not in owner.json.loads(text):
                    raise OSError("controlled dispatch retirement interruption")
                return actual_write(path, text, *args, **kwargs)

            with mock.patch.object(owner, "atomic_write", side_effect=interrupted):
                with self.assertRaisesRegex(OSError, "controlled dispatch retirement interruption"):
                    api.dispatch(vars(owner))
            interrupted_memo = owner.load_memo()
            self.assertIn(api._MARKER, interrupted_memo)
            self.assertIn("ready", interrupted_memo)
            self.assertNotIn("controller_source_pending", interrupted_memo)

        self.check_completed(owner, api.dispatch(vars(owner)), selected)

    def recover_case(self, owner, args, selected):
        """Resume a package whose marker became durable before adoption."""
        api = self.dispatch_api
        memo = owner.load_memo()
        self.assertNotIn("controller_source_pending", memo)
        self.assertFalse(api._adopted(memo, selected["source_batch_sha256"]))
        # The pins-free completion must not invent an adoption it cannot see.
        with mock.patch.object(owner, "atomic_write", side_effect=AssertionError("unadopted dispatch wrote")):
            with self.assertRaises(ValueError) as refused:
                api.dispatch(vars(owner))
        self.assertEqual(refused.exception.reason, "checkpoint-dispatch-package-not-adopted")
        # A marker names bytes, never authorization: the independent epoch
        # adoption premise is still checked against the retained package.
        forged = {**self.premises, "expected_adoption_sha256": "0" * 64}
        with self.assertRaises(ValueError):
            api.advance(vars(owner), admitted_status=args["admitted_status"], **forged)
        self.assertNotIn("controller_source_pending", owner.load_memo())
        self.assertIn(api._MARKER, owner.load_memo())
        view = api.advance(vars(owner), admitted_status=args["admitted_status"], **self.premises)
        self.check_completed(owner, view, selected)
        self.assertIsNone(api.advance(vars(owner),
            admitted_status=args["admitted_status"], **self.premises))

    def check_completed(self, owner, view, selected):
        api = self.dispatch_api
        self.assertEqual(view["status"], "available")
        self.assertEqual(view["batch"]["batch_sha256"], selected["source_batch_sha256"])
        memo = owner.load_memo()
        self.assertIn("ready", memo)
        self.assertNotIn(api._MARKER, memo)
        self.assertFalse(Path(owner.CONTROLLER_SOURCE_BATCH_PATH).exists())
        # A retired package is never retried, and nothing else is selected.
        with mock.patch.object(owner, "atomic_write", side_effect=AssertionError("retired dispatch wrote")):
            self.assertIsNone(api.dispatch(vars(owner)))
        self.assertIsNone(api.select(vars(owner), memo=memo))
        if getattr(self, "check_successor", False):
            self.successor_case(owner, selected)

    def successor_case(self, owner, selected):
        """Extend the retained chain by one link from the acknowledged parent."""
        import siahistoryroot as roots
        directory = Path(selected["directory"])
        root_pin = selected["root_sha256"]
        root = owner.json.loads((directory / ("root-" + root_pin + ".json")).read_bytes())
        memo = owner.load_memo()
        committed = memo["controller_source_committed"]
        status = owner.json.loads(Path(owner.STATUS_PATH).read_bytes())
        args = dict(memo=memo, admitted_status=status, directory=str(directory),
            expected_root_sha256=root_pin, expected_head_sha256=root_pin)
        # Retaining the acknowledged parent is the successor's precondition,
        # not something the successor may reconstruct for itself.
        with self.assertRaises(ValueError) as refused:
            roots.prepare_successor(vars(owner), **args)
        self.assertEqual(refused.exception.reason, "checkpoint-parent-graph-required")
        import siacheckpointparent as parents
        retained = dict(directory=str(directory), committed=committed)
        parents.retain_graph(vars(owner), **retained)
        self.assertTrue(parents.retain_checkpoint_live(vars(owner), **retained,
            memo=memo, admitted_status=status))
        view = roots.prepare_successor(vars(owner), **args)
        successor = view["successor"]
        self.assertEqual(successor["schema"], "sia-source-history-successor-v1")
        self.assertEqual(successor["status"], "successor-retained-not-activated")
        # The bootstrap root is carried by reference, never rebuilt.
        self.assertEqual(successor["root_sha256"], root_pin)
        self.assertEqual(successor["parent_sha256"], root_pin)
        self.assertEqual(successor["generation"], 1)
        self.assertEqual(successor["epoch_id"], root["epoch_id"])
        for key in ("legacy_epoch_sha256", "legacy_history_sha256"):
            self.assertEqual(successor[key], root[key])
        self.assertEqual(successor["committed"], committed)
        self.assertNotEqual(successor["committed"], root["committed"])
        # The chain advances by exactly one entry block.
        self.assertNotEqual(successor["final_entry_block_sha256"],
            root["final_entry_block_sha256"])
        self.assertTrue((directory / roots.store._name(
            successor["final_entry_block_sha256"])).exists())
        self.assertEqual(view["parent_sha256"], root_pin)
        self.assertEqual(successor["checkpoint_sha256"],
            view["batch"]["intake_projection"]["checkpoint_sha256"])
        # The head names this capture's own predecessor as a whole triple.
        self.assertEqual(root["committed"], view["batch"]["epoch"]["predecessor"])
        self.assertEqual(view["batch"]["batch_sha256"], committed["source_batch_sha256"])
        # A retry rereads the retained successor instead of republishing it;
        # content-addressed block retention may still replay for durability.
        published = roots.store.queue.fixed_atomic_publish

        def no_successor(path, *rest, **options):
            if Path(path).name.startswith("successor-"):
                raise AssertionError("successor retry published")
            return published(path, *rest, **options)

        with mock.patch.object(roots.store.queue, "fixed_atomic_publish",
                side_effect=no_successor):
            retried = roots.prepare_successor(vars(owner), **args)
        self.assertEqual(retried, view)
        # A head pin the directory does not hold is refused, not bootstrapped.
        with self.assertRaises(ValueError):
            roots.prepare_successor(vars(owner), **{**args, "expected_head_sha256": "0" * 64})
        # A rehashed unrelated bootstrap root carrying the same final entry
        # block must not be carried forward as this chain's origin.
        def publish(prefix, document):
            raw = roots.blocks._wire(document)
            pin = hashlib.sha256(raw).hexdigest()
            owner.atomic_write(str(directory / (prefix + pin + ".json")),
                raw.decode("utf-8"), mode=0o600)
            return pin

        # A rehashed bootstrap root keeping the same final entry block is not
        # this chain's origin: the acknowledged capture pins the original.
        wrong_pin = publish("root-", {**root, "epoch_id": root["epoch_id"] + "-other"})
        with self.assertRaises(ValueError) as refused:
            roots.prepare_successor(vars(owner), **{**args,
                "expected_root_sha256": wrong_pin, "expected_head_sha256": wrong_pin})
        self.assertEqual(refused.exception.reason, "successor-parent-root-binding")
        # The original root pin survives; only the head advances. A head whose
        # recorded predecessor is not the acknowledged capture's own
        # predecessor is refused, because block linkage binds just the source
        # batch of that triple, not its effects or live identity.
        with self.assertRaises(ValueError) as refused:
            roots.prepare_successor(vars(owner), **{**args,
                "expected_head_sha256": view["successor_sha256"]})
        self.assertEqual(refused.exception.reason, "successor-head-predecessor-binding")
        # Predecessor corrected, checkpoint metadata altered: still refused.
        forged_head = publish("successor-", {**successor,
            "committed": copy.deepcopy(root["committed"]), "checkpoint_sha256": "0" * 64})
        with self.assertRaises(ValueError) as refused:
            roots.prepare_successor(vars(owner), **{**args,
                "expected_head_sha256": forged_head})
        self.assertEqual(refused.exception.reason, "successor-head-checkpoint-binding")
        # Current acknowledged authority, not a caller's memo copy, decides.
        forged = copy.deepcopy(memo)
        forged["controller_source_committed"] = {**committed, "live_generation_sha256": "0" * 64}
        with self.assertRaises(ValueError):
            roots.prepare_successor(vars(owner), **{**args, "memo": forged})
        stale = copy.deepcopy(memo)
        stale.pop("ready", None)
        with self.assertRaises(ValueError) as refused:
            roots.prepare_successor(vars(owner), **{**args, "memo": stale})
        self.assertEqual(refused.exception.reason, "successor-durable-memo-differs")

    def stage_case(self, f, owner, args, before):
        from tests import test_controller_source_effects as effects_fixture
        graph = f.case.effects._new_graph()
        graph["publication_id"] = "4" * 32
        old_graph_raw = Path(owner.GRAPH_PATH).read_bytes()
        old_live = {name: Path(path).read_bytes() for name, path in {
            "status": owner.STATUS_PATH, "candidate": owner.LIVE_CANDIDATE_PATH,
            "generation": owner.LIVE_STATE_PATH}.items()}
        def export():
            if getattr(self, "check_parent_live", False):
                for name, raw in old_live.items():
                    saved_live = list(Path(args["directory"]).glob("parent-" + name + "-*.json"))
                    self.assertEqual(len(saved_live), 1)
                    self.assertEqual(saved_live[0].read_bytes(), raw)
            owner.atomic_write(owner.GRAPH_PATH, owner.json.dumps(graph), mode=0o600)
            if getattr(self, "interrupt_graph", False):
                self.interrupt_graph = False
                raise OSError("controlled graph-before-memo interruption")
        with mock.patch.object(owner, "_export_graph_publication", side_effect=export), \
                mock.patch.object(owner, "_controller_source_effects_observed_at", return_value=effects_fixture.STATUS_AT):
            if getattr(self, "interrupt_parent_live", False):
                publish = owner.siaqueue.fixed_atomic_publish
                def partial(path, *pos, **kw):
                    result = publish(path, *pos, **kw)
                    if Path(path).name.startswith("parent-status-"):
                        raise OSError("controlled parent-live partial copy")
                    return result
                with mock.patch.object(owner.siaqueue, "fixed_atomic_publish", side_effect=partial):
                    with self.assertRaisesRegex(OSError, "controlled parent-live partial copy"):
                        self.stage_api.stage(vars(owner), **args)
                self.assertEqual(args["memo"], before)
                self.assertEqual(owner.load_memo(), before)
                self.assertEqual(Path(owner.GRAPH_PATH).read_bytes(), old_graph_raw)
            if getattr(self, "interrupt_graph", False):
                with self.assertRaisesRegex(OSError, "controlled graph-before-memo interruption"):
                    self.stage_api.stage(vars(owner), **args)
                self.assertEqual(args["memo"], before)
                self.assertEqual(owner.load_memo(), before)
            if getattr(self, "interrupt_effects", False):
                write = owner.atomic_write
                def interrupted(path, *pos, **kw):
                    result = write(path, *pos, **kw)
                    if path == owner.MEMO_PATH:
                        raise OSError("controlled durable effects interruption")
                    return result
                with mock.patch.object(owner, "atomic_write", side_effect=interrupted):
                    with self.assertRaisesRegex(OSError, "controlled durable effects interruption"):
                        self.stage_api.stage(vars(owner), **args)
                self.assertEqual(args["memo"], before)
                args["memo"] = owner.load_memo()
            else:
                self.assertTrue(self.stage_api.stage(vars(owner), **args))
            self.assertEqual(owner.load_memo(), args["memo"])
            self.assertEqual(args["memo"]["live_loop_committed"], before["live_loop_committed"])
            self.assertNotIn("ready", args["memo"])
            pending = args["memo"]["controller_source_effects_pending"]
            saved = list(Path(args["directory"]).glob("parent-graph-*.json"))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].read_bytes(), old_graph_raw)
            with self.assertRaisesRegex(RuntimeError, "current graph generation"):
                owner._read_committed_live_generation(memo=args["memo"], admitted_status=args["admitted_status"])
            self.assertEqual(pending["source_batch_sha256"], before["controller_source_pending"]["batch_sha256"])
            if getattr(self, "live_api", None) is not None:
                self.publish_case(owner, args, pending)
                return
            if getattr(self, "read_parent_live", False):
                self.historical_case(owner, args, old_live)
                return
            if getattr(self, "check_parent_live", False):
                import siacheckpointparent
                view = content.adoption.read_pending(vars(owner), **args)
                committed = view["package"]["artifacts"]["capture"]["epoch"]["predecessor"]
                retained_args = dict(directory=args["directory"], committed=committed,
                    memo=args["memo"], admitted_status=args["admitted_status"])
                with mock.patch.object(owner.siaqueue, "fixed_atomic_publish", side_effect=AssertionError("retention retry wrote")):
                    self.assertFalse(siacheckpointparent.retain_live(vars(owner), **retained_args))
                saved_candidate = next(Path(args["directory"]).glob("parent-candidate-*.json"))
                owner.atomic_write(str(saved_candidate), "{}", mode=0o600)
                with self.assertRaises(ValueError) as refused:
                    siacheckpointparent.retain_live(vars(owner), **retained_args)
                self.assertEqual(refused.exception.reason, "checkpoint-parent-live-retained-differs")
            with mock.patch.object(owner, "_controller_source_sync_generation", side_effect=AssertionError("retry synchronized")), \
                    mock.patch.object(owner, "_export_graph_publication", side_effect=AssertionError("retry exported")), \
                    mock.patch.object(owner, "atomic_write", side_effect=AssertionError("retry wrote")):
                self.assertFalse(self.stage_api.stage(vars(owner), **args))
            altered = copy.deepcopy(graph)
            altered["publication_id"] = "0" * 32
            owner.atomic_write(owner.GRAPH_PATH, owner.json.dumps(altered), mode=0o600)
            with self.assertRaises(ValueError) as refused:
                self.stage_api.stage(vars(owner), **args)
            self.assertEqual(refused.exception.reason, "checkpoint-effects-pending-graph-differs")
            owner.atomic_write(owner.GRAPH_PATH, owner.json.dumps(graph), mode=0o600)
            corrupt_parent = owner.json.loads(old_graph_raw)
            corrupt_parent["publication_id"] = "5" * 32
            owner.atomic_write(str(saved[0]), owner.json.dumps(corrupt_parent), mode=0o600)
            with self.assertRaises(ValueError) as refused:
                self.stage_api.stage(vars(owner), **args)
            self.assertEqual(refused.exception.reason, "checkpoint-parent-graph-generation")

    def historical_case(self, owner, args, old_live):
        import siacheckpointparent
        view = content.adoption.read_pending(vars(owner), **args)
        committed = view["package"]["artifacts"]["capture"]["epoch"]["predecessor"]
        inputs = dict(directory=args["directory"], committed=committed)
        paths = {"status": owner.STATUS_PATH, "candidate": owner.LIVE_CANDIDATE_PATH,
                 "generation": owner.LIVE_STATE_PATH, "graph": owner.GRAPH_PATH}
        for path in paths.values():
            owner.atomic_write(path, "{}", mode=0o600)
        before_memo = owner.load_memo()
        with mock.patch.object(owner, "atomic_write", side_effect=AssertionError("historical reader wrote")):
            with siacheckpointparent.hold_live(vars(owner), **inputs) as historical:
                self.assertEqual(historical["status"], owner.json.loads(old_live["status"]))
                self.assertEqual(historical["generation"], owner.json.loads(old_live["generation"]))
                self.assertEqual(historical["candidate"], owner.json.loads(old_live["candidate"]))
                self.assertEqual(historical["authority"], "historical-parent-not-current-readiness")
        self.assertEqual(owner.load_memo(), before_memo)
        with self.assertRaises(RuntimeError):
            owner._read_committed_live_generation(memo=args["memo"], admitted_status=args["admitted_status"])
        altered = copy.deepcopy(committed)
        altered["live_generation_sha256"] = "0" * 64
        with self.assertRaises(ValueError) as refused:
            with siacheckpointparent.hold_live(vars(owner), **{**inputs, "committed": altered}):
                pass
        self.assertEqual(refused.exception.reason, "checkpoint-parent-live-archive-identity")
        with self.assertRaises(ValueError) as refused:
            with siacheckpointparent.hold_live(vars(owner), **inputs) as historical:
                historical["generation"]["publication_id"] = "0" * 32
        self.assertEqual(refused.exception.reason, "checkpoint-parent-live-archive-output-changed")
        saved = next(Path(args["directory"]).glob("parent-candidate-*.json"))
        with self.assertRaises(ValueError) as refused:
            with siacheckpointparent.hold_live(vars(owner), **inputs):
                owner.atomic_write(str(saved), old_live["candidate"].decode("utf-8") + " ", mode=0o600)
        self.assertEqual(refused.exception.reason, "ack-file-generation-changed")
        owner.atomic_write(str(saved), old_live["candidate"].decode("utf-8") + " ", mode=0o600)
        with self.assertRaises(ValueError) as refused:
            with siacheckpointparent.hold_live(vars(owner), **inputs):
                pass
        self.assertEqual(refused.exception.reason, "checkpoint-parent-live-archive-bytes")

    def publish_case(self, owner, args, pending):
        before = copy.deepcopy(args["memo"])
        if getattr(self, "interrupt_live", False):
            paths = {"candidate": owner.LIVE_CANDIDATE_PATH, "generation": owner.LIVE_STATE_PATH,
                "status": owner.STATUS_PATH, "memo": owner.MEMO_PATH}
            originals = {key: Path(path).read_bytes() for key, path in paths.items()}
            for boundary in ("candidate", "stage_memo", "generation", "status", "final_memo"):
                with self.subTest(boundary=boundary):
                    for key, path in paths.items():
                        owner.atomic_write(path, originals[key].decode("utf-8"), mode=0o600)
                    args["memo"] = owner.load_memo()
                    args["admitted_status"] = owner.json.loads(Path(owner.STATUS_PATH).read_bytes())
                    write = owner.atomic_write
                    def interrupted(path, text, **kw):
                        result = write(path, text, **kw)
                        name = next((key for key, value in paths.items() if value == path), None)
                        if name == "memo":
                            name = "stage_memo" if "live_loop_pending" in owner.json.loads(text) else "final_memo"
                        if name == boundary:
                            raise OSError("controlled durable live interruption")
                        return result
                    with mock.patch.object(owner, "atomic_write", side_effect=interrupted):
                        with self.assertRaisesRegex(OSError, "controlled durable live interruption"):
                            self.live_api.publish(vars(owner), **args)
                    args["memo"] = owner.load_memo()
                    args["admitted_status"] = owner.json.loads(Path(owner.STATUS_PATH).read_bytes())
                    self.assertNotIn("ready", args["memo"])
                    self.assertEqual(self.live_api.publish(vars(owner), **args), boundary != "final_memo")
        else:
            self.assertTrue(self.live_api.publish(vars(owner), **args))
        self.assertEqual(owner.load_memo(), args["memo"])
        status = owner.json.loads(Path(owner.STATUS_PATH).read_bytes())
        self.assertEqual(status, pending["status"])
        view = owner._read_committed_live_generation(memo=args["memo"], admitted_status=status)
        self.assertEqual(view["status"], "available")
        self.assertEqual(view["generation"]["state_sha256"], pending["state_sha256"])
        for key in ("controller_source_pending", "controller_source_live_pending", "controller_source_effects_pending"):
            self.assertEqual(args["memo"][key], before[key])
        self.assertNotIn("ready", args["memo"])
        self.assertNotIn("live_loop_pending", args["memo"])
        self.assertNotIn("pulse_status_effects_pending", args["memo"])
        args["admitted_status"] = status
        with mock.patch.object(owner, "atomic_write", side_effect=AssertionError("live retry wrote")), \
                mock.patch.object(owner, "export_status", side_effect=AssertionError("live retry exported")):
            self.assertFalse(self.live_api.publish(vars(owner), **args))
        if getattr(self, "finalize_effects", False):
            original = copy.deepcopy(args["memo"])
            write = owner.atomic_write
            def interrupted(path, text, **kw):
                result = write(path, text, **kw)
                if path == owner.MEMO_PATH:
                    raise OSError("controlled durable effects finalization")
                return result
            with mock.patch.object(owner, "atomic_write", side_effect=interrupted):
                with self.assertRaisesRegex(OSError, "controlled durable effects finalization"):
                    self.live_api.finalize(vars(owner), **args)
            self.assertEqual(args["memo"], original)
            args["memo"] = owner.load_memo()
            receipt = args["memo"]["controller_source_effects_committed"]
            self.assertNotIn("controller_source_effects_pending", args["memo"])
            self.assertNotIn("ready", args["memo"])
            self.assertEqual(receipt["state_sha256"], pending["state_sha256"])
            self.assertEqual(receipt["source_batch_sha256"], pending["source_batch_sha256"])
            with mock.patch.object(owner, "atomic_write", side_effect=AssertionError("effects retry wrote")):
                self.assertFalse(self.live_api.finalize(vars(owner), **args))
                self.assertFalse(self.live_api.publish(vars(owner), **args))
            if getattr(self, "ack_api", None) is not None:
                self.ack_case(owner, args, receipt)
                return
            corrupted = copy.deepcopy(args["memo"])
            altered_receipt = corrupted["controller_source_effects_committed"]
            altered_receipt["state_sha256"] = "0" * 64
            altered_receipt["receipt_sha256"] = owner._live_own(altered_receipt, "receipt_sha256")
            owner.atomic_write(owner.MEMO_PATH, owner.json.dumps(corrupted), mode=0o600)
            args["memo"] = owner.load_memo()
            with self.assertRaises(ValueError) as refused:
                self.live_api.finalize(vars(owner), **args)
            self.assertEqual(refused.exception.reason, "checkpoint-live-effects-receipt-differs")
            return
        altered = copy.deepcopy(view["generation"])
        def booleanize(value):
            if not isinstance(value, (dict, list)):
                return False
            for key, item in (value.items() if isinstance(value, dict) else enumerate(value)):
                if type(item) is int and item in (0, 1):
                    value[key] = bool(item)
                    return True
                if booleanize(item):
                    return True
            return False
        self.assertTrue(booleanize(altered))
        owner.atomic_write(owner.LIVE_STATE_PATH, owner.json.dumps(altered), mode=0o600)
        with self.assertRaises(ValueError) as refused:
            self.live_api.publish(vars(owner), **args)
        self.assertEqual(refused.exception.reason, "checkpoint-live-publication-phase-differs")

        owner.atomic_write(owner.LIVE_STATE_PATH, "{}", mode=0o600)
        with self.assertRaises(ValueError) as refused:
            self.live_api.publish(vars(owner), **args)
        self.assertEqual(refused.exception.reason, "checkpoint-live-publication-phase-differs")

    def ack_case(self, owner, args, receipt):
        before = copy.deepcopy(args["memo"])
        if getattr(self, "interrupt_ack", False):
            batch = owner.json.loads(Path(owner.CONTROLLER_SOURCE_BATCH_PATH).read_bytes())
            boundaries = ["effects-receipt-archive-durable", "archive-durable", "refusals-durable"]
            boundaries.extend("journal-" + row["scope"] + "-durable"
                for proposal in batch["journal_proposals"] for row in proposal["cursors"])
            boundaries.extend(("cursor-state-durable", "memo-durable"))
            for boundary in boundaries:
                with self.subTest(boundary=boundary):
                    def interrupted(name):
                        if name == boundary:
                            raise OSError("controlled durable ACK interruption")
                    with mock.patch.object(owner, "_controller_source_ack_boundary", side_effect=interrupted):
                        with self.assertRaisesRegex(OSError, "controlled durable ACK interruption"):
                            self.ack_api.acknowledge_checkpoint(vars(owner), memo=args["memo"], admitted_status=args["admitted_status"])
                    args["memo"] = owner.load_memo()
                    if boundary != "memo-durable":
                        self.assertNotIn("ready", args["memo"])
        else:
            self.ack_api.acknowledge_checkpoint(vars(owner), memo=args["memo"], admitted_status=args["admitted_status"])
        self.assertEqual(owner.load_memo(), args["memo"])
        self.assertFalse(Path(owner.CONTROLLER_SOURCE_BATCH_PATH).exists())
        self.assertEqual(args["memo"]["controller_source_committed"]["source_batch_sha256"], receipt["source_batch_sha256"])
        self.assertEqual(args["memo"]["controller_source_committed"]["source_effects_receipt_sha256"], receipt["receipt_sha256"])
        self.assertEqual(args["memo"]["live_loop_committed"], before["live_loop_committed"])
        self.assertIn("ready", args["memo"])
        self.assertFalse(self.ack_api._PENDING_ONLY.intersection(args["memo"]))
        with mock.patch.object(owner, "_write_memo", side_effect=AssertionError("ACK retry wrote")), \
                mock.patch.object(owner, "atomic_write", side_effect=AssertionError("ACK retry wrote")):
            self.ack_api.acknowledge_checkpoint(vars(owner), memo=args["memo"], admitted_status=args["admitted_status"])
            view = self.ack_api.read_checkpoint_completed(vars(owner), memo=args["memo"], admitted_status=args["admitted_status"])
        self.assertEqual(view["status"], "available")
        self.assertEqual(view["batch"]["batch_sha256"], receipt["source_batch_sha256"])

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
