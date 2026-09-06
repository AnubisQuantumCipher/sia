#!/usr/bin/env python3
"""Repair-only public command contracts; every mutable root is a fixture.

The owner runs this file sequentially.  It uses temporary Git repositories,
never the resident CLI, keeper, daemon, model service, or PGlite database.
"""

import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import unittest
from unittest import mock

try:
    import sia_test_home
    import test_cortex_boundary_repair as fixtures
except ModuleNotFoundError:
    from tests import sia_test_home
    from tests import test_cortex_boundary_repair as fixtures


MODULE_PATH = os.path.join(fixtures.BIN, "siacortexrepair.py")
PUBLICATION_SCHEMA = "sia-cortex-boundary-publication-v1"
COMMAND_SCHEMA = "sia-cortex-boundary-command-v1"
TARGET_PATH = "sia/cortex.md"


class CortexRepairCommand(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE_PATH),
                        "dedicated repair-only command module is missing")
        self.fixture = fixtures.CortexBoundaryRepair(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.core = self.fixture.sialib
        self.home = Path(self.fixture.home)
        self.root = Path(self.core.CORPUS)
        self.state = Path(self.core.STATE)
        self.cortex = Path(self.fixture.cortex)
        self.fixture._write_cortex()
        self.original = self.cortex.read_bytes()
        self.target = self.original + self.core.CORTEX_BOUNDARY_REPAIR_SUFFIX.encode()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)

        def expanduser(path):
            if path == "~":
                return str(self.home)
            if isinstance(path, str) and path.startswith("~/"):
                return str(self.home / path[2:])
            return sia_test_home._REAL_EXPANDUSER(path)

        with mock.patch("os.path.expanduser", side_effect=expanduser):
            for name in ("siamind", "siatakes"):
                module = fixtures._load(
                    name + "_repair_command_" + self._testMethodName,
                    os.path.join(fixtures.BIN, name + ".py"))
                self.stack.enter_context(mock.patch.object(self.core, name, module))
        self.repair = fixtures._load(
            "siacortexrepair_" + self._testMethodName, MODULE_PATH)
        with mock.patch.dict(sys.modules, {"sialib": self.core,
                                           "siacortexrepair": self.repair}):
            self.cli = fixtures._load(
                "sia_repair_command_" + self._testMethodName, fixtures.SIA_PATH)

        self.memo = self.core._with_ready_receipt(
            {"pulse_seq": 7, "retained_operator_field": {"keep": True}},
            "recovery", "a" * 32)
        self.core._write_memo(self.memo)
        self._write_json(self.core.siamind.MIND_PATH, {
            "v": 2, "nodes": {}, "edges": {}, "event_applied": {},
            "event_batch_applied": None})
        self.mind_before = Path(self.core.siamind.MIND_PATH).read_bytes()
        self._ready_graph()
        self._write_json(self.core._thought_legacy_scan_path(), {
            "schema": self.core.THOUGHT_LEGACY_SCAN_SCHEMA,
            "phase": "complete", "after": "", "unindexed": 0,
            "indexed": 0, "cookie": 0, "directory": None,
            "discarded": [], "reset_id": None})
        self.stack.enter_context(mock.patch.object(
            self.core, "_require_recoverable_graph_snapshot", return_value={}))
        self._git("init", "-q")
        self._git("add", "--", TARGET_PATH)
        self._git("commit", "-q", "-m", "fixture original root")
        self.original_head = self._git("rev-parse", "HEAD").strip()

        self.events = []
        self.active = []
        self.signed = {}
        for name in ("brainstem_owner", "corpus_owner"):
            self.stack.enter_context(mock.patch.object(
                self.core, name, side_effect=lambda name=name: self._lease(name)))
        self.keeper = self.stack.enter_context(mock.patch.object(
            self.core, "ledger_settle", side_effect=self._ledger_settle))
        self.stack.enter_context(mock.patch.object(
            self.core, "ledger_contains", side_effect=self._ledger_contains))
        self.sync = self.stack.enter_context(mock.patch.object(
            self.core, "brain_sync", side_effect=self._sync))
        self.graph = self.stack.enter_context(mock.patch.object(
            self.core, "_export_graph_publication", side_effect=self._graph))

        # These are not recovery shortcuts available to the new front door.
        self.forbidden = []
        for module, names in (
                (self.core, ("pulse", "_pulse_transaction", "_recover_before_pulse",
                             "consolidate_corpus", "ensure_organs",
                             "recover_ledger_transitions", "corpus_commit",
                             "_settle_pending_publication", "memory_readiness")),
                (self.core.siamind, ("load_mind", "save_mind"))):
            for name in names:
                self.forbidden.append(self.stack.enter_context(mock.patch.object(
                    module, name, side_effect=AssertionError(
                        "repair-only command invoked forbidden " + name))))

    def _write_json(self, path, value):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
        target.chmod(0o600)

    def _git(self, *args):
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_CONFIG_GLOBAL": os.devnull, "GIT_OPTIONAL_LOCKS": "0",
               "XDG_CONFIG_HOME": str(self.home / "config")}
        completed = subprocess.run(
            ["git", "-c", "user.email=fixture@example.invalid", "-c",
             "user.name=Cortex fixture", *args], cwd=self.root, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        return completed.stdout.decode()

    @contextlib.contextmanager
    def _lease(self, name):
        self.events.append("enter:" + name)
        self.active.append(name)
        try:
            yield
        finally:
            self.assertEqual(self.active.pop(), name)
            self.events.append("exit:" + name)

    def _assert_owned(self):
        self.assertEqual(self.active, ["brainstem_owner", "corpus_owner"])

    def _ledger_settle(self, action, arg1, arg2, content, occurrence_id=None):
        self._assert_owned()
        self.assertTrue(self.core.load_memo().get("sync_needed"))
        self.assertEqual(self.cortex.read_bytes(), self.target)
        self.assertTrue(self._publications(), "ledger write lacks command witness")
        self.events.append("ledger")
        value = (action, arg1, arg2, content)
        if occurrence_id in self.signed:
            self.assertEqual(self.signed[occurrence_id], value)
        self.signed[occurrence_id] = value
        return True

    def _ledger_contains(self, action, arg1, arg2, content, occurrence_id=None):
        return self.signed.get(occurrence_id) == (action, arg1, arg2, content)

    def _sync(self):
        self._assert_owned()
        self.assertTrue(self.core.load_memo().get("sync_needed"))
        self.assertEqual(self._git("status", "--porcelain", "--untracked-files=all"), "")
        self.assertEqual(self._git("show", "HEAD:" + TARGET_PATH).encode(), self.target)
        self.events.append("sync")
        return True, ""

    def _ready_graph(self):
        path = Path(self.core._graph_projection_state_path())
        value = json.loads(path.read_text()) if path.exists() \
            else self.core._fresh_graph_projection_state()
        value.update(phase="ready", queue=[])
        self._write_json(self.core._graph_projection_state_path(), value)

    def _graph(self):
        self._assert_owned()
        self.assertTrue(self.core.load_memo().get("sync_needed"))
        self.events.append("graph")
        self._ready_graph()
        return 0, 0, 0

    def _publications(self):
        return self.fixture._state_records(PUBLICATION_SCHEMA)

    def _run(self):
        return self.repair.repair_cortex_boundary(self.core)

    def _snapshot(self):
        result = {}
        for directory, children, files in os.walk(self.home, followlinks=False):
            for name in children + files:
                path = Path(directory) / name
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode):
                    value = ("link", os.readlink(path))
                elif stat.S_ISREG(info.st_mode):
                    value = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
                else:
                    value = ("directory",)
                result[str(path.relative_to(self.home))] = (stat.S_IMODE(info.st_mode), value)
        return result

    def _refuses_without_mutation(self):
        before = self._snapshot()
        calls = (self.keeper.call_count, self.sync.call_count, self.graph.call_count)
        with self.assertRaises((RuntimeError, ValueError)):
            self._run()
        self.assertEqual(self._snapshot(), before,
                         "repair preflight changed bytes, modes, or entries")
        self.assertEqual((self.keeper.call_count, self.sync.call_count, self.graph.call_count), calls)

    def _interrupt_at_sync(self):
        with mock.patch.object(self.core, "brain_sync", return_value=(False, "fixture sync interruption")):
            with self.assertRaisesRegex((RuntimeError, ValueError), "sync"):
                self._run()
        self.assertTrue(self.core.load_memo().get("sync_needed"))
        self.assertTrue(self._publications())

    def test_public_frontdoor_dispatch_uses_leases_without_readiness_bypass(self):
        with mock.patch.object(self.core, "_lifecycle_reader", return_value=contextlib.nullcontext()), \
                mock.patch.dict(sys.modules, {"sialib": self.core, "siacortexrepair": self.repair}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            result = self.cli.main(["sia", "repair-cortex-boundary", "--json"])
        self.assertEqual(result, 0, output.getvalue())
        value = json.loads(output.getvalue())
        self.assertEqual(value["schema"], COMMAND_SCHEMA)
        self.assertEqual(value["status"], "repaired")
        self.assertLessEqual(len(output.getvalue().encode()), self.core.MAX_CONFIG_BYTES)
        self.assertEqual(self.events[:2], ["enter:brainstem_owner", "enter:corpus_owner"])
        self.assertEqual(self.events[-2:], ["exit:corpus_owner", "exit:brainstem_owner"])
        self.assertNotIn("repair-cortex-boundary", self.cli.READINESS_GATED_COMMANDS)
        self.assertIn("bench", self.cli.READINESS_GATED_COMMANDS)

    def test_busy_owner_and_unknown_options_refuse_without_writes_or_service_control(self):
        for argv in (["sia", "repair-cortex-boundary", "--unsafe"],
                     ["sia", "repair-cortex-boundary", "--json", "extra"]):
            with self.subTest(argv=argv), \
                    mock.patch.object(self.core, "_lifecycle_reader", return_value=contextlib.nullcontext()), \
                    mock.patch.dict(sys.modules, {"sialib": self.core, "siacortexrepair": self.repair}), \
                    contextlib.redirect_stdout(io.StringIO()):
                before = self._snapshot()
                self.assertNotEqual(self.cli.main(argv), 0)
                self.assertEqual(self._snapshot(), before)
        with mock.patch.object(self.core, "brainstem_owner", side_effect=self.core.OwnerBusy("fixture owner")):
            self._refuses_without_mutation()

    def test_success_is_append_only_scoped_committed_compatible_and_idempotent(self):
        value = self._run()
        self.assertEqual(value["status"], "repaired")
        self.assertEqual(self.cortex.read_bytes(), self.target)
        self.assertEqual(self._git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").strip(), TARGET_PATH)
        self.assertEqual(self._git("rev-parse", "HEAD^").strip(), self.original_head)
        self.assertEqual(self.events[2:-2], ["ledger", "sync", "graph"])
        self.assertEqual(len(self.signed), 1)
        memo = self.core.load_memo()
        self.assertFalse(memo.get("sync_needed", False))
        self.assertEqual(memo["pulse_seq"], self.memo["pulse_seq"])
        self.assertEqual(memo["retained_operator_field"], self.memo["retained_operator_field"])
        self.assertEqual(set(memo["ready"]), {"v", "completed_at", "kind", "identity"})
        self.assertEqual(memo["ready"]["kind"], "recovery")
        self.assertEqual(Path(self.core.siamind.MIND_PATH).read_bytes(), self.mind_before)
        nonclaims = " ".join(value["non_claims"]).casefold()
        self.assertIn("cognition", nonclaims)
        self.assertIn("biological", nonclaims)
        self.assertIn("mind", nonclaims)
        before = self._snapshot()
        again = self._run()
        self.assertEqual(again["status"], "already-ready")
        self.assertEqual(self._snapshot(), before)
        self.sync.assert_called_once()
        self.graph.assert_called_once()

    def test_unrelated_memo_debt_and_full_restore_sync_are_readonly_refusals(self):
        debts = {
            "sync_needed": True, "pulse_publication": {}, "dream_publication": {},
            "consolidation_pending": {}, "source_replay_pending": {},
            "pulse_status_effects_pending": {}, "notify_baseline_attempt": {},
            "brainstem_failure_pending": {},
        }
        for key, value in debts.items():
            with self.subTest(key=key):
                self.core._write_memo(dict(self.memo, **{key: value}))
                self._refuses_without_mutation()
        self.core._write_memo(self.memo)
        with mock.patch.dict(os.environ, {"SIA_RESTORE_FULL_SYNC": "1"}):
            self._refuses_without_mutation()

    def test_unrelated_untracked_corpus_refuses(self):
        unrelated = self.root / "notes" / "operator.md"
        unrelated.parent.mkdir()
        unrelated.write_text("retain operator text\n")
        self._refuses_without_mutation()

    def test_unrelated_staged_corpus_refuses(self):
        unrelated = self.root / "notes" / "operator.md"
        unrelated.parent.mkdir()
        unrelated.write_text("retain operator text\n")
        self._git("add", "--", "notes/operator.md")
        self._refuses_without_mutation()

    def test_exact_dirty_cortex_target_without_publication_witness_refuses(self):
        self.cortex.write_bytes(self.target)
        receipt, journal = self.fixture._repair_records_for(self.original, self.target)
        self._write_json(self.core.CORTEX_BOUNDARY_REPAIR_RECEIPT, receipt)
        self._write_json(self.core.CORTEX_BOUNDARY_REPAIR_JOURNAL, journal)
        self._refuses_without_mutation()

    def test_raw_mind_and_legacy_cleanup_candidates_are_never_normalized(self):
        mind = Path(self.core.siamind.MIND_PATH)
        mind.chmod(0o644)
        paths = (Path(self.core._ledger_pending_dir()),
                 Path(self.core.siatakes._grade_transaction_dir()),
                 Path(self.core.siatakes._take_migration_transaction_dir()),
                 Path(self.core._thought_recovery_dir()))
        for index, directory in enumerate(paths):
            with self.subTest(directory=directory):
                directory.mkdir(parents=True, exist_ok=True)
                sentinel = directory / (".retained." + str(index) + ".new")
                sentinel.write_bytes(b"retain crash evidence")
                self._refuses_without_mutation()
                # Fixture cleanup only: otherwise the first queue would mask
                # later cleanup-capable directory probes.
                sentinel.unlink()
        self.assertEqual(stat.S_IMODE(mind.stat().st_mode), 0o644)

    def test_readonly_preflight_does_not_rewrite_legacy_graph_failure(self):
        value = json.loads(Path(self.core._graph_projection_state_path()).read_text())
        value["failed_ops"] = [self.core.LEGACY_GRAPH_README_FAILURE]
        self._write_json(self.core._graph_projection_state_path(), value)
        self._refuses_without_mutation()

    def test_raw_mind_cursor_or_dream_guard_blocks_without_migration(self):
        for patch in ({"event_applied": {"fixture": True}},
                      {"event_batch_applied": {}}, {"dream_unit": {}}):
            with self.subTest(patch=patch):
                value = json.loads(self.mind_before)
                value.update(patch)
                self._write_json(self.core.siamind.MIND_PATH, value)
                self._refuses_without_mutation()

    def test_missing_root_or_wrong_git_root_generation_is_not_bootstrapped(self):
        self.cortex.unlink()
        self._refuses_without_mutation()

    def test_publication_witness_precedes_barrier_and_unmutated_source_can_resume(self):
        with mock.patch.object(self.repair, "_publication_barrier",
                               side_effect=RuntimeError("fixture barrier interruption")):
            with self.assertRaisesRegex(RuntimeError, "barrier interruption"):
                self._run()
        self.assertEqual(self.cortex.read_bytes(), self.original)
        self.assertFalse(self.core.load_memo().get("sync_needed", False))
        records = self._publications()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][1]["path"], TARGET_PATH)
        self.assertEqual(records[0][1]["source_head"], self.original_head)
        self.assertEqual(records[0][1]["repair"]["source_sha256"], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(records[0][1]["repair"]["target_sha256"], hashlib.sha256(self.target).hexdigest())
        self.assertEqual(self._run()["status"], "repaired")

    def test_receipt_before_root_interruption_resumes_same_exact_receipt(self):
        original_write = self.core.atomic_write

        def interrupt(path, value, **kwargs):
            if path == str(self.cortex):
                raise RuntimeError("fixture root interruption")
            return original_write(path, value, **kwargs)

        with mock.patch.object(self.core, "atomic_write", side_effect=interrupt):
            with self.assertRaisesRegex(RuntimeError, "root interruption"):
                self._run()
        receipt = Path(self.core.CORTEX_BOUNDARY_REPAIR_RECEIPT).read_bytes()
        self.assertEqual(self.cortex.read_bytes(), self.original)
        self.assertTrue(self.core.load_memo().get("sync_needed"))
        self.assertEqual(self._run()["status"], "repaired")
        self.assertEqual(Path(self.core.CORTEX_BOUNDARY_REPAIR_RECEIPT).read_bytes(), receipt)

    def test_first_dirty_target_resume_admits_only_its_exact_ledger_pending_occurrence(self):
        with mock.patch.object(self.core, "ledger_settle", side_effect=RuntimeError("fixture keeper interruption")):
            with self.assertRaisesRegex(RuntimeError, "keeper interruption"):
                self._run()
        self.assertEqual(self.cortex.read_bytes(), self.target)
        self.assertEqual(self._git("rev-parse", "HEAD").strip(), self.original_head)
        pending = list(Path(self.core._ledger_pending_dir()).glob("*.json"))
        self.assertEqual(len(pending), 1)
        before = pending[0].read_bytes()
        self.assertEqual(self._run()["status"], "repaired")
        record = json.loads(before)
        self.assertIn(record["record_id"], self.signed)
        self.assertFalse(pending[0].exists())

    def test_target_after_ledger_retirement_before_git_commit_remains_resumable(self):
        with mock.patch.object(self.repair, "_commit_cortex", side_effect=RuntimeError("fixture commit interruption")):
            with self.assertRaisesRegex(RuntimeError, "commit interruption"):
                self._run()
        self.assertFalse(os.path.lexists(self.core.CORTEX_BOUNDARY_REPAIR_JOURNAL))
        self.assertEqual(self.cortex.read_bytes(), self.target)
        self.assertEqual(self._git("rev-parse", "HEAD").strip(), self.original_head)
        self.assertEqual(self._run()["status"], "repaired")
        self.assertEqual(len(self.signed), 1)

    def test_scoped_commit_refuses_new_unrelated_staged_data_and_does_not_add_all(self):
        real_settle = self._ledger_settle

        def inject(*args, **kwargs):
            result = real_settle(*args, **kwargs)
            sentinel = self.root / "new-operator-page.md"
            sentinel.write_text("must not be captured by repair commit\n")
            self._git("add", "--", sentinel.name)
            return result

        with mock.patch.object(self.core, "ledger_settle", side_effect=inject):
            with self.assertRaises((RuntimeError, ValueError)):
                self._run()
        self.assertEqual(self._git("rev-parse", "HEAD").strip(), self.original_head)
        self.assertEqual(self._git("diff", "--cached", "--name-only").strip(), "new-operator-page.md")
        self.assertTrue(self.core.load_memo().get("sync_needed"))
        self.sync.assert_not_called()

    def test_synced_commit_resume_rebinds_barrier_and_preserves_ready_receipt_until_success(self):
        self._interrupt_at_sync()
        head = self._git("rev-parse", "HEAD").strip()
        old_ready = copy.deepcopy(self.core.load_memo()["ready"])
        self.assertEqual(old_ready, self.memo["ready"])
        with mock.patch.object(self.repair, "_publication_barrier",
                               wraps=self.repair._publication_barrier) as barrier:
            self.assertEqual(self._run()["status"], "repaired")
        barrier.assert_called()
        self.assertEqual(self._git("rev-parse", "HEAD").strip(), head)
        self.assertNotEqual(self.core.load_memo()["ready"], old_ready)

    def test_unrelated_head_or_witness_substitution_on_resume_refuses_before_writes(self):
        self._interrupt_at_sync()
        self._git("commit", "--allow-empty", "-q", "-m", "unrelated commit")
        self._refuses_without_mutation()

    def test_changed_publication_receipt_identity_on_resume_is_not_reauthorized(self):
        self._interrupt_at_sync()
        path, publication = self._publications()[0]
        publication["repair"]["source_sha256"] = "0" * 64
        self._write_json(path, publication)
        self._refuses_without_mutation()

    def test_unrelated_ledger_pending_record_is_not_recovered_during_resume(self):
        with mock.patch.object(self.core, "ledger_settle", side_effect=RuntimeError("fixture keeper interruption")):
            with self.assertRaisesRegex(RuntimeError, "keeper interruption"):
                self._run()
        self.core.queue_ledger_transition(42, "NOTE:other", "other", "other", "retain")
        self._refuses_without_mutation()

    def test_graph_failure_retains_sync_debt_and_never_publishes_false_readiness(self):
        with mock.patch.object(self.core, "_export_graph_publication", side_effect=RuntimeError("fixture graph interruption")):
            with self.assertRaisesRegex(RuntimeError, "graph"):
                self._run()
        self.assertTrue(self.core.load_memo().get("sync_needed"))
        self.assertEqual(self.core.load_memo()["ready"], self.memo["ready"])
        self.assertTrue(self._publications())
        self.assertEqual(self._run()["status"], "repaired")

    def test_non_cortex_recovery_stores_refuse_without_consuming_their_records(self):
        paths = (
            Path(self.core._thought_recovery_claim_path()),
            Path(self.core._thought_mind_replay_path()),
            Path(self.core._thought_recovery_dir()) / "unrelated.json",
            Path(self.core.siatakes._history_paths("take")["pending"]),
            Path(self.core.siatakes._history_paths("intent")["pending"]),
            Path(self.core.siatakes._grade_transaction_dir()) / "unrelated.json",
            Path(self.core.siatakes._take_migration_transaction_dir()) / "unrelated.json",
        )
        for path in paths:
            with self.subTest(path=path):
                self._write_json(path, {"retain": "unrelated interrupted publication"})
                self._refuses_without_mutation()
                path.unlink()  # only this known private fixture record

    def test_unsafe_malformed_or_oversized_publication_witness_refuses_readonly(self):
        with mock.patch.object(self.repair, "_publication_barrier",
                               side_effect=RuntimeError("fixture barrier interruption")):
            with self.assertRaisesRegex(RuntimeError, "barrier interruption"):
                self._run()
        path = Path(self._publications()[0][0])
        original = path.read_bytes()
        for raw in (b"{malformed", b" " * self.core.MAX_CONFIG_BYTES + b" "):
            with self.subTest(kind=raw[:16]):
                path.write_bytes(raw)
                self._refuses_without_mutation()
        path.write_bytes(original)
        other = self.state / "retained-witness-target.json"
        path.rename(other)
        path.symlink_to(other)
        self._refuses_without_mutation()

    def test_git_mutations_are_explicitly_scoped_and_reads_disable_optional_writes(self):
        actual = self.core._run_bounded_text_process
        with mock.patch.object(self.core, "_run_bounded_text_process", wraps=actual) as process:
            self._run()
        git_calls = [call for call in process.call_args_list
                     if call.args and call.args[0][0] == "git"]
        self.assertTrue(git_calls, "repair did not use bounded Git transport")
        for call in git_calls:
            argv = call.args[0]
            self.assertNotIn("-A", argv)
            self.assertNotIn("--all", argv)
            self.assertEqual(call.kwargs.get("cwd"), self.core.CORPUS)
            self.assertEqual(call.kwargs["env"]["GIT_OPTIONAL_LOCKS"], "0")
            if "add" in argv:
                self.assertEqual(argv[argv.index("add"):], ["add", "--", TARGET_PATH])

    def test_bound_graph_generation_precedes_root_and_ledger_effects(self):
        actual = self.core.atomic_write

        def observe(path, value, **kwargs):
            if path in (str(self.cortex), self.core.CORTEX_BOUNDARY_REPAIR_JOURNAL,
                        self.core.CORTEX_BOUNDARY_REPAIR_RECEIPT):
                self.assertTrue(self.core.load_memo().get("sync_needed"))
                publication = self._publications()[0][1]
                graph = json.loads(Path(self.core._graph_projection_state_path()).read_text())
                self.assertEqual(graph["generation"], publication["graph_dirty"]["generation"])
            return actual(path, value, **kwargs)

        with mock.patch.object(self.core, "atomic_write", side_effect=observe):
            self._run()

    def test_unrelated_graph_generation_on_resume_refuses_before_restarting_it(self):
        self._interrupt_at_sync()
        self._write_json(self.core._graph_projection_state_path(),
                         self.core._fresh_graph_projection_state())
        self._refuses_without_mutation()

    def test_matching_owned_partial_graph_can_resume_without_becoming_read_authority(self):
        self._interrupt_at_sync()
        self._write_json(self.core.GRAPH_PATH, {"fixture": "explicit partial graph"})
        actual_graph = self._graph

        def graph():
            result = actual_graph()
            self._write_json(self.core.GRAPH_PATH, {})
            return result

        def require(value):
            if value.get("fixture"):
                raise RuntimeError("resident graph snapshot is incomplete")
            return value

        with mock.patch.object(self.core, "_require_recoverable_graph_snapshot", side_effect=require), \
                mock.patch.object(self.core, "_recoverable_graph_snapshot", return_value={"fixture": "structurally valid partial"}), \
                mock.patch.object(self.core, "_export_graph_publication", side_effect=graph):
            self.assertEqual(self._run()["status"], "repaired")

    def test_unknown_memo_change_on_resume_is_not_silently_preserved_as_own_debt(self):
        self._interrupt_at_sync()
        memo = self.core.load_memo()
        memo["retained_operator_field"] = {"changed outside this repair": True}
        self.core._write_memo(memo)
        self._refuses_without_mutation()

    def test_source_readers_refuse_ancestor_aliases_and_replaced_parent_generation(self):
        parent = self.home / "source-parent"
        parent.mkdir()
        (parent / "leaf").write_bytes(b"bounded source")
        (parent / "empty").mkdir()
        alias = self.home / "source-alias"
        alias.symlink_to(parent, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            self.repair._read(self.core, str(alias / "leaf"), self.core.MAX_CONFIG_BYTES, "fixture source")
        with self.assertRaises(RuntimeError):
            self.repair._scan(self.core, str(alias / "empty"))
        actual = self.core._source_path_identity

        def replace(path, flags):
            if path == str(parent / "leaf"):
                parent.rename(self.home / "retained-source-parent")
                parent.mkdir()
                (parent / "leaf").write_bytes(b"bounded source")
            return actual(path, flags)

        with mock.patch.object(self.core, "_source_path_identity", side_effect=replace):
            with self.assertRaisesRegex(RuntimeError, "changed"):
                self.repair._read(self.core, str(parent / "leaf"), self.core.MAX_CONFIG_BYTES, "fixture source")
        self.assertEqual((self.home / "retained-source-parent" / "leaf").read_bytes(), b"bounded source")

    def test_public_json_refusal_has_named_debt_code_and_unknown_errors_never_echo(self):
        self.core._write_memo(dict(self.memo, sync_needed=True))
        before = self._snapshot()
        with mock.patch.object(self.core, "_lifecycle_reader", return_value=contextlib.nullcontext()), \
                mock.patch.dict(sys.modules, {"sialib": self.core, "siacortexrepair": self.repair}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertNotEqual(self.cli.main(["sia", "repair-cortex-boundary", "--json"]), 0)
        value = json.loads(output.getvalue())
        self.assertEqual(value["status"], "refused")
        self.assertEqual(value["reason_code"], "unrelated-publication-debt")
        self.assertEqual(value["phase"], "preflight")
        self.assertTrue(value["non_claims"])
        self.assertEqual(self._snapshot(), before)
        secret = "DO-NOT-ECHO fixture keeper secret/path"
        with mock.patch.object(self.core, "_lifecycle_reader", return_value=contextlib.nullcontext()), \
                mock.patch.dict(sys.modules, {"sialib": self.core, "siacortexrepair": self.repair}), \
                mock.patch.object(self.repair, "repair_cortex_boundary", side_effect=RuntimeError(secret)), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertNotEqual(self.cli.main(["sia", "repair-cortex-boundary", "--json"]), 0)
        value = json.loads(output.getvalue())
        self.assertEqual(value["reason_code"], "unclassified-repair-refusal")
        self.assertNotIn(secret, output.getvalue())
        self.assertTrue(value["non_claims"])

    def test_pending_directory_refusals_name_only_the_owning_subsystem(self):
        cases = (
            (self.core._thought_recovery_dir(), "unrelated-thought-recovery-entry"),
            (self.core.siatakes._grade_transaction_dir(), "unrelated-take-grade-entry"),
            (self.core.siatakes._take_migration_transaction_dir(), "unrelated-take-migration-entry"),
            (self.core._ledger_pending_dir(), "unrelated-ledger-pending-entry"),
        )
        for directory, expected_code in cases:
            for name in ("private-operator-entry.without-json-suffix", ".private.crash.new"):
                with self.subTest(subsystem=expected_code, name_kind=name):
                    target = Path(directory)
                    target.mkdir(parents=True, exist_ok=True)
                    entry = target / name
                    entry.write_bytes(b"PRIVATE RECOVERY CONTENT MUST NOT CROSS THE PUBLIC FRONT DOOR")
                    before = self._snapshot()
                    with mock.patch.object(self.core, "_lifecycle_reader", return_value=contextlib.nullcontext()), \
                            mock.patch.dict(sys.modules, {"sialib": self.core, "siacortexrepair": self.repair}), \
                            contextlib.redirect_stdout(io.StringIO()) as output:
                        result = self.cli.main(["sia", "repair-cortex-boundary", "--json"])
                    self.assertNotEqual(result, 0)
                    value = json.loads(output.getvalue())
                    self.assertEqual(value["schema"], COMMAND_SCHEMA)
                    self.assertEqual(value["status"], "refused")
                    self.assertEqual(value["reason_code"], expected_code)
                    self.assertEqual(value["phase"], "preflight")
                    self.assertEqual(value["non_claims"], list(self.repair.NON_CLAIMS))
                    self.assertNotIn(str(entry), output.getvalue())
                    self.assertNotIn(name, output.getvalue())
                    self.assertNotIn("PRIVATE RECOVERY CONTENT", output.getvalue())
                    self.assertEqual(self._snapshot(), before)
                    self.keeper.assert_not_called()
                    self.sync.assert_not_called()
                    self.graph.assert_not_called()
                # Only the known private fixture entry is removed, so an
                # earlier subsystem cannot mask the next refusal control.
                entry.unlink()


if __name__ == "__main__":
    unittest.main()
