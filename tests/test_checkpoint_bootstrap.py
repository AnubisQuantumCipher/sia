"""Start a compact chain from an adopted, acknowledged legacy controller.

The state here is genuinely pre-compact: the underlying capture fixture
yields a real legacy acknowledgment and a real adopted delivery epoch,
and this module asserts that no chain pointer, package marker or root
document exists before the first cycle call. Nothing is seeded to make
bootstrap look reachable.

The resident entry takes its own owner leases, so the resident fixture is
used rather than the capture one. The configured chain root is an owned
temporary directory for the duration; the controlled clock is a fixture,
not a claim about real timing. No operator configuration is created,
read or altered: the authority is the opt-in the caller already
established plus the adopted, acknowledged state itself.
"""

import contextlib
import copy
import hashlib
import os
import importlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tests import test_controller_source_resident_v3 as resident_tests
from tests import test_controller_source_rollover_storage as clock_tests
from tests import test_controller_source_effects as effects_fixture


class CheckpointBootstrap(unittest.TestCase):
    def setUp(self):
        self.cycle = importlib.import_module("siacheckpointcycle")
        self.assertTrue(callable(getattr(self.cycle, "bootstrap", None)),
            "missing compact bootstrap entry")
        self.dispatch = importlib.import_module("siacheckpointdispatch")
        self.resident = resident_tests.ControllerSourceResidentV3(methodName="runTest")
        self.resident.setUp()
        self.addCleanup(self.resident.doCleanups)

    @contextlib.contextmanager
    def precompact(self, *, notifications=False):
        """A real adopted, acknowledged controller with no compact state."""
        with self.resident.capture.prepared(notifications=notifications) as f, \
                tempfile.TemporaryDirectory(prefix="sia-chain-bootstrap-") as directory, \
                self.resident.resident_owner(f) as owner:
            memo = owner.load_memo()
            self.assertIsNone(self.dispatch.select(vars(owner), memo=memo),
                "a package marker existed before bootstrap")
            self.assertIsNone(self.dispatch.select_chain(vars(owner), memo=memo),
                "a chain pointer existed before bootstrap")
            self.assertEqual(sorted(Path(directory).iterdir()), [],
                "the owned chain root was not empty before bootstrap")
            with contextlib.ExitStack() as stack:
                for context in self.engine(f, owner, directory):
                    stack.enter_context(context)
                if notifications:
                    # The real notification collector, so the fence below is
                    # written by production code at the production point.
                    stack.enter_context(mock.patch.object(owner, "SENSES",
                        [owner.sense_notify, owner.sense_custom]))
                yield f, owner, directory

    def engine(self, f, owner, directory):
        """Controlled Git and index observations, not proof of those programs.

        The compact completion commits real pages to a real repository and
        reads a controlled index generation, exactly as the existing
        compact fixtures do. Nothing about the engine itself is claimed.
        """
        def git(*args):
            return subprocess.run(["/usr/bin/git", *args], cwd=owner.CORPUS,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=True, text=True).stdout.strip()

        git("init", "-q", "-b", "fixture")
        git("add", "-A")
        git("-c", "user.email=sia@omarchy.local", "-c", "user.name=SIA",
            "commit", "-q", "--allow-empty", "-m", "fixture parent")

        graph = f.case.effects._new_graph()
        graph["publication_id"] = "4" * 32

        def export():
            owner.atomic_write(owner.GRAPH_PATH, owner.json.dumps(graph), mode=0o600)

        def observed(*, corpus_generation, target_versions):
            manifest = [{**row, "page_state": "live", "parse_error_codes": [],
                "expected_projection_sha256": "4" * 64,
                "current_projection_sha256": "4" * 64,
                "current_content_hash": "4" * 64,
                "current_content_hash_match": True, "projection_match": True}
                for row in target_versions]
            generation = f.case.effects._sync_generation(manifest,
                sync_requested_commit=corpus_generation["corpus_commit_oid"],
                status_last_commit=corpus_generation["corpus_commit_oid"],
                local_path=str(owner.CORPUS))
            return {"sync_generation": generation, "target_manifest": manifest,
                "target_manifest_sha256": owner.sialiveloop._sha(manifest)}

        return (
            mock.patch.object(owner, "CONTROLLER_CHECKPOINT_CHAIN_DIR",
                directory, create=True),
            mock.patch.object(owner.time, "time",
                return_value=clock_tests.SUCCESSOR_OBSERVED_AT),
            mock.patch.object(owner, "GIT", "/usr/bin/git"),
            mock.patch.object(owner, "_export_graph_publication", side_effect=export),
            mock.patch.object(owner, "_controller_source_effects_observed_at",
                return_value=effects_fixture.STATUS_AT),
            mock.patch.object(owner, "_controller_source_sync_generation",
                side_effect=observed),
        )

    def test_bootstrap_starts_a_chain_and_leaves_a_usable_pointer(self):
        with self.precompact() as (f, owner, directory):
            before = owner.load_memo()
            view = owner._run_controller_source_cycle()
            self.assertEqual(view["status"], "available")
            durable = owner.load_memo()
            # A compact transaction was acknowledged, not a legacy one.
            self.assertEqual(view["batch"]["schema"],
                "sia-controller-source-checkpoint-capture-v3")
            self.assertNotEqual(
                durable["controller_source_committed"]["source_batch_sha256"],
                before["controller_source_committed"]["source_batch_sha256"])
            # The chain exists now, and its head is its own root.
            pointer = self.dispatch.select_chain(vars(owner), memo=durable)
            self.assertEqual(pointer["status"], "continued")
            self.assertEqual(pointer["directory"], directory)
            self.assertEqual(pointer["head_sha256"], pointer["root_sha256"])
            self.assertEqual(pointer["next_generation"], 1)
            self.assertIsNone(self.dispatch.select(vars(owner), memo=durable))
            self.assertTrue(
                (Path(directory) / ("root-" + pointer["root_sha256"] + ".json")).exists())

    def converged(self, owner, trace):
        """Trace the legacy-authority prelude and both compact capture preparers."""
        stack = contextlib.ExitStack()
        takes = owner.siatakes
        for name in ("recover_natural_history_transactions", "recover_grade_transactions"):
            stack.enter_context(mock.patch.object(takes, name,
                side_effect=lambda before_publish=None, _n=name: (trace.append(_n), ([], []))[1]))
        stack.enter_context(mock.patch.object(owner, "_reconcile_legacy_memory_authority",
            side_effect=lambda memo: trace.append("reconcile")))
        transaction = self.cycle.transaction
        for name in ("prepare_root", "prepare_successor"):
            original = getattr(transaction, name)
            stack.enter_context(mock.patch.object(transaction, name,
                side_effect=lambda *a, _o=original, _n=name, **k: (trace.append(_n), _o(*a, **k))[1]))
        return stack

    def test_fresh_link_converges_legacy_authority_before_it_captures(self):
        """The compact lane runs the legacy prelude's provenance convergence.

        Interrupted natural-history and grade transactions are finished and
        legacy take/intent provenance advanced before a fresh capture, in
        the legacy prelude's order. Without this the readiness gates
        `take_migration_required` / `intent_history_required` stayed closed
        forever once the compact lane owned the pulse (a moved takes
        directory, an external corpus edit, or a runtime upgrade).
        """
        self.assertTrue(callable(getattr(self.cycle, "converge_legacy_authority", None)),
            "missing compact legacy-authority convergence")
        with self.precompact() as (f, owner, directory):
            trace = []
            with self.converged(owner, trace):
                view = owner._run_controller_source_cycle()
            self.assertEqual(view["status"], "available")
            self.assertEqual(trace[:3], ["recover_natural_history_transactions",
                                         "recover_grade_transactions", "reconcile"])
            self.assertIn(trace[3], ("prepare_root", "prepare_successor"))
            self.assertEqual(trace.count("reconcile"), 1)

    def test_recovery_of_a_captured_package_does_not_converge(self):
        """Nothing publishes between a capture and its completion."""
        with self.precompact() as (f, owner, directory):
            trace = []
            sentinel = {"status": "available", "batch": {}, "committed": {}}
            with self.converged(owner, trace), \
                    mock.patch.object(self.cycle, "recover", return_value=sentinel):
                self.assertIs(owner._run_controller_source_cycle(), sentinel)
            self.assertEqual(trace, [])

    def test_convergence_refusal_names_the_prelude_gate(self):
        with self.precompact() as (f, owner, directory):
            with mock.patch.object(owner.siatakes, "recover_natural_history_transactions",
                    return_value=([], [{"kind": "take", "error": "fixture"}])), \
                    self.assertRaisesRegex(RuntimeError, "natural-history recovery refused"):
                owner._run_controller_source_cycle()

    def test_retirement_releases_lane_authority_under_a_receipt(self):
        """The retained lane has no rollover; retirement is its named end.

        Every capture carries every page version since adoption and the
        ceilings are final (the maintainer machine refused
        complete-byte-capacity after ten days). Retirement writes a receipt
        naming what it releases, releases exactly the memo's lane authority,
        touches no archive, and refuses while anything is in flight.
        """
        source = importlib.import_module("siasourcebatch")
        self.assertTrue(callable(getattr(self.cycle, "retire", None)),
            "missing controller-source retirement")
        with self.precompact() as (f, owner, directory):
            view = owner._run_controller_source_cycle()
            self.assertEqual(view["status"], "available")
            memo = owner.load_memo()
            for key in self.cycle.RETIRED_KEYS:
                self.assertIn(key, memo)
            chain_files = sorted(Path(directory).iterdir())
            archive = Path(owner.CONTROLLER_SOURCE_ARCHIVE_DIR)
            archive_files = sorted(archive.iterdir()) if archive.exists() else []

            report = self.cycle.retire(vars(owner), memo=dict(memo), apply=False,
                                       reason="operator", retired_at=1_790_000_000)
            self.assertFalse(report["applied"])
            self.assertEqual(report["released"], sorted(self.cycle.RETIRED_KEYS))
            self.assertEqual(owner.load_memo(), memo, "a report changed the memo")
            self.assertFalse((Path(owner.STATE) / self.cycle.RETIREMENT_DIRECTORY).exists())

            held = dict(memo, controller_source_pending={"batch_sha256": "a" * 64})
            with self.assertRaises(source.SourceBatchRefusal) as refused:
                self.cycle.retire(vars(owner), memo=held, apply=True,
                                  reason="operator", retired_at=1_790_000_000)
            self.assertEqual(refused.exception.reason, "controller-retirement-in-flight")
            # A pending batch with no committed predecessor is a fresh
            # segment's initial batch, not the retired lane in flight.
            fresh = {k: v for k, v in held.items() if k != "controller_source_committed"}
            self.assertIsNone(self.cycle.retirement_pending(vars(owner), fresh))
            live_files = [owner.LIVE_STATE_PATH, owner.LIVE_CANDIDATE_PATH]
            present = [path for path in live_files if os.path.exists(path)]
            self.assertTrue(present, "the fixture published no live generation")

            live = dict(memo)
            applied = self.cycle.retire(vars(owner), memo=live, apply=True,
                                        reason="capacity: complete-byte-capacity",
                                        retired_at=1_790_000_000)
            self.assertTrue(applied["applied"])
            receipt_path = Path(applied["receipt"])
            self.assertTrue(receipt_path.is_file())
            self.assertEqual(receipt_path.stat().st_mode & 0o777, 0o600)
            receipt = json.loads(receipt_path.read_text())
            self.assertEqual(receipt["schema"], self.cycle.RETIREMENT_SCHEMA)
            self.assertEqual(receipt["reason"], "capacity: complete-byte-capacity")
            self.assertEqual(set(receipt["retired"]), set(self.cycle.RETIRED_KEYS))
            for key in self.cycle.RETIRED_KEYS:
                self.assertEqual(receipt["retired"][key], memo[key])
            durable = owner.load_memo()
            for key in self.cycle.RETIRED_KEYS:
                self.assertNotIn(key, durable)
            self.assertEqual(live, durable)
            self.assertEqual({k: v for k, v in memo.items() if k not in self.cycle.RETIRED_KEYS},
                             durable)
            self.assertFalse(owner._controller_source_present(durable))
            self.assertFalse(owner._live_started(durable),
                "a retired live lineage still counts as started")
            for label, row in receipt["retired_files"].items():
                self.assertFalse(os.path.exists(row["path"]))
                self.assertTrue(os.path.isfile(row["retained_as"]))
                with open(row["retained_as"], "rb") as stream:
                    self.assertEqual(hashlib.sha256(stream.read()).hexdigest(), row["sha256"])
            self.assertEqual(sorted(Path(directory).iterdir()), chain_files,
                "retirement touched the chain directory")
            if archive.exists():
                self.assertEqual(sorted(archive.iterdir()), archive_files)
            with self.assertRaises(source.SourceBatchRefusal) as again:
                self.cycle.retire(vars(owner), memo=dict(durable), apply=True,
                                  reason="operator", retired_at=1_790_000_000)
            self.assertEqual(again.exception.reason, "controller-retirement-nothing-retained")

    def test_capture_at_capacity_retires_the_lane_and_hands_the_pulse_back(self):
        """A capacity refusal is final on this lane; the cycle retires it.

        Any other refusal still propagates unchanged.
        """
        source = importlib.import_module("siasourcebatch")
        with self.precompact() as (f, owner, directory):
            self.assertEqual(owner._run_controller_source_cycle()["status"], "available")
            refusal = source.SourceBatchRefusal("complete-byte-capacity")
            trace = []
            with mock.patch.object(self.cycle.transaction, "prepare_successor",
                                   side_effect=refusal), \
                    mock.patch.object(owner, "log", side_effect=trace.append), \
                    mock.patch.object(owner, "_run_controller_source_transaction_v3",
                                      return_value={"state": "ok"}) as legacy:
                result = owner._run_controller_source_cycle()
            self.assertEqual(result, {"state": "ok"})
            legacy.assert_called_once()
            durable = owner.load_memo()
            for key in self.cycle.RETIRED_KEYS:
                self.assertNotIn(key, durable)
            retired = Path(owner.STATE) / self.cycle.RETIREMENT_DIRECTORY
            receipts = [path for path in retired.iterdir()
                        if path.name.startswith("retired-") and path.name.count(".") == 1]
            self.assertEqual(len(receipts), 1, sorted(retired.iterdir()))
            receipt = json.loads(receipts[0].read_text())
            self.assertEqual(receipt["reason"], "capacity: complete-byte-capacity")
            for row in receipt["retired_files"].values():
                self.assertTrue(Path(row["retained_as"]).is_file())
            self.assertTrue(any("retired at capacity" in line for line in trace))

        with self.precompact() as (f, owner, directory):
            self.assertEqual(owner._run_controller_source_cycle()["status"], "available")
            other = source.SourceBatchRefusal("checkpoint-transaction-head-pin")
            with mock.patch.object(self.cycle.transaction, "prepare_successor",
                                   side_effect=other), \
                    self.assertRaises(source.SourceBatchRefusal):
                owner._run_controller_source_cycle()
            for key in self.cycle.RETIRED_KEYS:
                self.assertIn(key, owner.load_memo())

    def test_compact_completion_renders_the_durable_status_not_the_view(self):
        """A pulse consumer renders a status; the compact lane returns a view.

        The brainstem and `sia pulse` both read `state` and `events_pulse`
        from the cycle result. The legacy lane returns the fresh admitted
        status; the compact lane returns the completed reader's evidence
        view, which has no such fields. The adapter reads the status that
        completion published from durable state and passes any status
        through untouched.
        """
        self.assertTrue(callable(getattr(self.cycle, "pulse_status", None)),
            "missing compact pulse status adapter")
        with self.precompact() as (f, owner, directory):
            view = owner._run_controller_source_cycle()
            self.assertEqual(set(view), {"status", "batch", "committed"})
            self.assertNotIn("state", view)
            status = self.cycle.pulse_status(vars(owner), view)
            durable = owner.read_state_json(
                owner.STATUS_PATH, None, "resident status", expected_type=dict)
            self.assertEqual(status, durable)
            self.assertEqual(status["pulse_seq"], owner.load_memo()["pulse_seq"])
            for field in ("state", "events_pulse", "integrity", "errors"):
                self.assertIn(field, status)
            # A status already in hand is the caller's, not re-read.
            legacy = {"state": "ok", "events_pulse": 0, "errors": {}}
            with mock.patch.object(owner, "load_memo",
                    side_effect=AssertionError("a status was re-read")):
                self.assertIs(self.cycle.pulse_status(vars(owner), legacy), legacy)

    def test_capture_interruption_leaves_the_root_head_selection_recoverable(self):
        """Interruption BEFORE capture, resumed as a root package.

        Boundary, stated rather than implied: this interrupts before the
        capture runs, so it establishes that the root=head selection is
        durable ahead of capture and that resuming it uses the ROOT
        preparer. It does NOT establish recovery from a fence the capture
        itself raises; that needs a real notify collector in this lane and
        has no coverage here.
        """
        with self.precompact() as (f, owner, directory):
            transaction = importlib.import_module("siacheckpointtransaction")
            real = transaction.prepare_root

            def interrupted(*args, **options):
                raise OSError("controlled bootstrap capture interruption")

            # The selection is written before the capture precisely so a
            # fence or crash during capture has something to come back to.
            with mock.patch.object(transaction, "prepare_root", side_effect=interrupted):
                with self.assertRaisesRegex(OSError, "bootstrap capture interruption"):
                    owner._run_controller_source_cycle()
            stranded = owner.load_memo()
            pointer = self.dispatch.select_chain(vars(owner), memo=stranded)
            self.assertIsNotNone(pointer, "the root=head selection was not durable")
            self.assertEqual(pointer["status"], "selected-not-captured")
            self.assertEqual(pointer["head_sha256"], pointer["root_sha256"])
            self.assertIsNone(self.dispatch.select(vars(owner), memo=stranded))
            reserved = stranded["pulse_seq"]

            # Re-entering resumes that exact selection rather than choosing
            # a new one, and spends the reservation already made.
            view = owner._run_controller_source_cycle()
            self.assertEqual(view["status"], "available")
            durable = owner.load_memo()
            self.assertEqual(durable["pulse_seq"], reserved,
                "the retry reserved a second sequence for one link")
            advanced = self.dispatch.select_chain(vars(owner), memo=durable)
            self.assertEqual(advanced["status"], "continued")
            self.assertEqual(advanced["head_sha256"], pointer["head_sha256"])

    def test_notifications_bootstrap_raises_no_new_fence_once_a_baseline_exists(self):
        """Why capture-created fence recovery has NO coverage in this lane.

        This is a recorded boundary, not a proof of recovery. With the real
        notification collector running, an epoch that has already taken a
        notification baseline does not raise a new fence during capture:
        sense_notify only calls the baseline writer when it must establish
        an initial baseline. So the capture-created fence this lane would
        need cannot be reached from this fixture at all, and the honest
        record is that fact rather than a fence the fixture raised itself.

        What therefore remains UNVERIFIED for bootstrap: recovery from a
        fence the capture itself creates, and the interrupted-first-
        baseline opaque recovery underneath it. Reaching either needs a
        chain whose notification baseline has never been established.
        """
        import siasourcebatch
        with self.precompact(notifications=True) as (f, owner, directory):
            self.assertIsNone(siasourcebatch._notification_marker(
                vars(owner), owner.load_memo()))
            view = owner._run_controller_source_cycle()
            self.assertEqual(view["status"], "available")
            durable = owner.load_memo()
            # The real collector ran and still raised no fence, because the
            # baseline was already established before this pulse.
            self.assertIsNone(view["batch"]["notification_baseline_attempt"])
            self.assertIsNone(siasourcebatch._notification_marker(
                vars(owner), durable))
            after = view["batch"]["cursor_proposal"]["after"]
            self.assertTrue(owner._notify_cursor_checkpoint_safe(after))
            self.assertEqual(after["notify.baseline"]["kind"], "exact")
            # Bootstrap still completed and left the chain usable.
            pointer = self.dispatch.select_chain(vars(owner), memo=durable)
            self.assertEqual(pointer["status"], "continued")
            self.assertEqual(pointer["head_sha256"], pointer["root_sha256"])

    def test_root_head_selection_recovers_beneath_a_retained_fence(self):
        """Resume a root=head selection while a fence is outstanding.

        Honest about provenance: the capture does not raise a fence here
        (see the boundary test above), so the fence is injected by the
        fixture — but through the production writer,
        _mark_notify_baseline_attempt, at a point where a real pulse could
        hold one. This is a controlled injection of a retained fence, and
        it is NOT a capture-created fence or a first-baseline recovery.

        What it does establish: the root=head selection persisted before
        capture is resumable while a fence stands, the retry reuses its
        reservation, and acknowledgment clears the fence itself.
        """
        import siasourcebatch
        import siacheckpointtransaction as transaction
        with self.precompact(notifications=True) as (f, owner, directory):
            def interrupted(*args, **options):
                raise OSError("controlled pre-capture interruption")

            with mock.patch.object(transaction, "prepare_root", side_effect=interrupted):
                with self.assertRaisesRegex(OSError, "pre-capture interruption"):
                    owner._run_controller_source_cycle()
            stranded = owner.load_memo()
            pointer = self.dispatch.select_chain(vars(owner), memo=stranded)
            self.assertEqual(pointer["status"], "selected-not-captured")
            self.assertEqual(pointer["head_sha256"], pointer["root_sha256"])
            reserved = stranded["pulse_seq"]

            # Controlled injection, production writer, durable immediately.
            marker = owner._mark_notify_baseline_attempt(stranded)
            self.assertIsNotNone(marker)
            self.assertEqual(
                siasourcebatch._notification_marker(vars(owner), owner.load_memo()),
                marker)

            view = owner._run_controller_source_cycle()
            self.assertEqual(view["status"], "available")
            durable = owner.load_memo()
            self.assertEqual(durable["pulse_seq"], reserved,
                "the fenced retry reserved a second sequence")
            self.assertEqual(view["batch"]["notification_baseline_attempt"], marker)
            # Acknowledgment retired the fence; the fixture never cleared it.
            self.assertIsNone(
                siasourcebatch._notification_marker(vars(owner), durable))
            advanced = self.dispatch.select_chain(vars(owner), memo=durable)
            self.assertEqual(advanced["status"], "continued")
            self.assertEqual(advanced["head_sha256"], pointer["head_sha256"])


if __name__ == "__main__":
    unittest.main()
