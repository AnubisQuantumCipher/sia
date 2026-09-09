"""Real resident source-v3 cycles through the additive owning entry point.

Positive runs use actual acknowledged source parents, the real epoch adoption,
collector, fixed WAL, live/status publication and source ACK implementations.
The wrapper, not this fixture, must acquire and continuously hold the source
brainstem/corpus leases. No successful source capture, generation or ACK is
replaced by a mock result. Instrumentation only records real front-door values.

The existing effects fixture supplies controlled Git/index observations and
graph/status observation clocks. It does not prove those external programs.
The controller observation clock is an explicit supplied fixture callback.
No journal output is synthesized: the retained journal remains genuinely empty
and delivery writers are forbidden. This is local resident orchestration proof,
not writer enablement, output delivery, complete machine history, biological
cognition, JACKAL assurance or a held-out retrieval improvement.

The additive API can resume the existing initial/pending transaction and may
therefore return a legacy initial completion. These positives start from real
completed parents; none claims that a relabeled initial capture is source v3.
Root alone executes this module, sequentially under the mission memory cap.
"""

import contextlib
import copy
import importlib
import inspect
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import test_controller_delivery_epoch as epoch_tests
from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_capture_v3 as capture_tests
from tests import test_controller_source_idle as idle_tests
from tests import test_controller_source_rollover_storage as clock_tests
from tests import test_controller_source_v3_rollover as rollover_tests


ENTRY = "_run_controller_source_transaction_v3"
PARAMETERS = ("operation", "clock", "journal_limits",
              "expected_journal_limits_sha256", "expected_adoption_sha256")
REFUSALS = (ValueError, RuntimeError, OSError)
V3 = "sia-controller-source-batch-v3"


class _WalDeath(KeyboardInterrupt):
    pass


class ControllerSourceResidentV3(unittest.TestCase):
    def setUp(self):
        self.runner = importlib.import_module("siacontrollersourcerunner")
        self.assertTrue(callable(getattr(self.runner, "run_v3", None)),
                        "missing actual resident source-v3 dispatcher")
        self.core = importlib.import_module("sialib")
        self.assertTrue(callable(getattr(self.core, ENTRY, None)),
                        "missing continuously owned resident source-v3 entry point")
        # Missing APIs fail before constructing an acknowledged parent.
        self.rollover = rollover_tests.ControllerSourceV3Rollover(methodName="runTest")
        self.addCleanup(self.rollover.doCleanups)
        self.rollover.setUp()
        self.effects = self.rollover.effects
        self.capture = self.rollover.capture
        self.epoch = self.rollover.epoch
        self.source = self.rollover.source
        self.live = self.rollover.live

    @staticmethod
    def forbidden(name):
        return mock.Mock(side_effect=AssertionError("resident-v3 forbidden work: " + name))

    @contextlib.contextmanager
    def legacy(self):
        with self.epoch.completed() as (case, retained, committed, status, generation, root):
            self.assertFalse(root.exists())
            self.assertNotIn(epoch_tests.MARKER_KEY, case.live.memo)
            yield SimpleNamespace(case=case, retained=retained, committed=committed,
                status=status, generation=generation, root=root, adopted=None,
                marker=None, nonidle=False, notifications=False,
                owner=case.source.lib.__dict__, batch=None, request=None)

    @contextlib.contextmanager
    def resident_owner(self, f):
        # Join actual temporary artifact paths while preserving the actual
        # collector/configuration module. Unlike capture_owner, do NOT enter
        # a source lease here: the resident entry point owns that obligation.
        with self.epoch.idle.source_owner(f.case), contextlib.ExitStack() as stack:
            owner = f.case.source.lib
            for name in capture_tests.AUTHORITY_PATHS:
                stack.enter_context(mock.patch.object(
                    owner, name, getattr(f.case.lib, name),
                    create=name == epoch_tests.ROOT_KEY))
            self.assertIsNone(owner._CORPUS_OWNER_FD.get())
            self.assertIsNone(owner._BRAINSTEM_OWNER_FD.get())
            owner._load_live_publication()
            try:
                yield owner
            finally:
                self.assertIsNone(owner._CORPUS_OWNER_FD.get())
                self.assertIsNone(owner._BRAINSTEM_OWNER_FD.get())

    def observe_handoff(self, f, owner, memo, status):
        """Populate controlled external observers from actual durable inputs."""
        view = owner._read_pending_controller_source_batch(memo=memo)
        self.assertEqual(view["status"], "pending")
        batch = view["batch"]
        self.assertEqual(batch, f.batch)
        candidate = owner._prepare_controller_source_live_candidate(
            memo=memo, admitted_status=status)
        transition = self.live.prepare_pulse(**candidate["prepare_inputs"])
        binding = copy.deepcopy(memo["controller_source_live_pending"])
        handoff = copy.deepcopy(memo["pulse_status_effects_pending"])
        fixture = f.case.effects
        fixture.admitted_status = copy.deepcopy(status)
        fixture.batch, fixture.candidate = copy.deepcopy(batch), copy.deepcopy(candidate)
        fixture.transition, fixture.binding = copy.deepcopy(transition), copy.deepcopy(binding)
        fixture.handoff, fixture.memo_before = handoff, copy.deepcopy(memo)
        fixture.corpus_generation = fixture._corpus_generation()
        plan = getattr(owner, idle_tests.GIST_PREPARER)(
            transition=transition, expected_transition_sha256=transition["transition_sha256"])
        rows = fixture._manifest(batch["event_closure"])
        rows.extend({
            **row, "page_state": "live", "parse_error_codes": [],
            "expected_projection_sha256": "4" * 64,
            "current_projection_sha256": "4" * 64,
            "current_content_hash": "4" * 64,
            "current_content_hash_match": True, "projection_match": True,
        } for row in plan["target_versions"])
        self.assertEqual(len({row["slug"] for row in rows}), len(rows))
        fixture.target_manifest = sorted(rows, key=lambda row: row["slug"])
        fixture.sync_generation = fixture._sync_generation(fixture.target_manifest)
        f.candidate, f.transition, f.binding, f.gist_plan = candidate, transition, binding, plan

    @contextlib.contextmanager
    def instrument(self, f, *, recovery=False, crash_wal=False):
        with self.resident_owner(f) as owner, contextlib.ExitStack() as stack:
            trace = SimpleNamespace(stages=[], lease=None, captures=[], prepares=[],
                                    retained=[], effects=[], acknowledgments=[],
                                    scope_events=[], active_scopes=[])
            prepare = self.capture.epoch_module.prepare_epoch
            capture = self.source.capture_successor_v3
            retain = owner._retain_controller_source_successor_batch
            publish = owner._publish_controller_source_effects
            acknowledge = owner._acknowledge_controller_source_batch
            write_memo = owner._write_memo
            boundary = owner._controller_source_rollover_boundary
            actual_iso = owner.iso

            def owned(stage):
                self.assertEqual(trace.active_scopes, ["brainstem", "corpus"])
                f.case.source.assert_brainstem_owned()
                corpus = os.fstat(owner._CORPUS_OWNER_FD.get())
                brainstem = os.fstat(owner._BRAINSTEM_OWNER_FD.get())
                identity = (corpus.st_dev, corpus.st_ino, brainstem.st_dev, brainstem.st_ino)
                if trace.lease is None:
                    trace.lease = identity
                self.assertEqual(identity, trace.lease)
                trace.stages.append(stage)

            def tracked_scope(name, actual, field):
                @contextlib.contextmanager
                def enter():
                    outer = getattr(owner, field).get() is None
                    with actual() as descriptor:
                        if outer:
                            trace.scope_events.append(name + "-enter")
                            trace.active_scopes.append(name)
                        try:
                            yield descriptor
                        finally:
                            if outer:
                                self.assertEqual(trace.active_scopes[-1], name)
                                trace.active_scopes.pop()
                                trace.scope_events.append(name + "-exit")
                return enter

            def prepare_epoch(actual_owner, **kwargs):
                if recovery:
                    raise AssertionError("fixed-WAL retry reacquired/prepared delivery epoch")
                self.assertIs(actual_owner, owner.__dict__)
                owned("prepare")
                result = prepare(actual_owner, **kwargs)
                trace.prepares.append(copy.deepcopy(result))
                f.adopted = copy.deepcopy(result)
                return result

            def clock():
                if recovery:
                    raise AssertionError("fixed-WAL retry acquired another controller clock")
                owned("clock")
                return clock_tests.SUCCESSOR_OBSERVED_AT

            def collect(actual_owner, **kwargs):
                if recovery:
                    raise AssertionError("fixed-WAL retry recollected sources or delivery input")
                self.assertIs(actual_owner, owner.__dict__)
                owned("capture")
                f.request = kwargs
                # Real collector/capture operation, with the existing guards
                # against acquisition-side publication, clock or writer work.
                with self.capture.no_effects(f, owner):
                    batch = capture(actual_owner, **kwargs)
                self.capture.assert_batch(f, owner, batch)
                f.batch = copy.deepcopy(batch)
                trace.captures.append(copy.deepcopy(batch))
                return batch

            def retain_batch(**kwargs):
                if recovery:
                    raise AssertionError("fixed-WAL retry retained another source batch")
                owned("retain")
                self.assertEqual(kwargs["batch"], f.batch)
                result = retain(**kwargs)
                trace.retained.append(Path(owner.CONTROLLER_SOURCE_BATCH_PATH).read_bytes())
                return result

            def effects(*, memo, admitted_status):
                owned("effects")
                # Only the external-witness observer changes owners. All
                # source/core functions still execute against real globals.
                with mock.patch.object(f.case.effects, "lib", owner), \
                        mock.patch.object(f.case.live, "memo", memo):
                    self.observe_handoff(f, owner, memo, admitted_status)
                    with self.effects.no_recapture(f), self.effects.content_effects(f) as observed:
                        result = publish(memo=memo, admitted_status=admitted_status)
                    trace.effects.append(observed)
                return result

            def ack(*, memo, admitted_status):
                pending = "controller_source_effects_committed" in memo
                owned("ack-pending" if pending else "ack-completed")
                if pending:
                    actual_batch = owner._read_pending_controller_source_batch(memo=memo)["batch"]
                    actual_generation = f.case.live._read("LIVE_STATE_PATH")
                    self.assertEqual(actual_batch, f.batch)
                    with mock.patch.object(f.case.live, "memo", memo):
                        f.case._remember_committed(copy.deepcopy(actual_batch), copy.deepcopy(actual_generation))
                    trace.acknowledgments.append(copy.deepcopy(memo["controller_source_effects_committed"]))
                return acknowledge(memo=memo, admitted_status=admitted_status)

            def write(value):
                previous = owner.load_memo()
                if previous.get("pulse_seq") != value.get("pulse_seq"):
                    if recovery:
                        raise AssertionError("fixed-WAL retry allocated another pulse sequence")
                    owned("reserve")
                return write_memo(value)

            def cut(stage):
                owned(stage)
                boundary(stage)
                if crash_wal and stage == "successor-batch-durable":
                    raise _WalDeath("actual resident-v3 fixed WAL retained")

            def handoff_time(dt=None):
                # Status handoff uses a controlled retained UTC timestamp;
                # the explicitly supplied integer controller clock is separate.
                return f.status["ts"] if dt is None else actual_iso(dt)

            for module, name, replacement in (
                    (owner, "brainstem_owner", tracked_scope(
                        "brainstem", owner.brainstem_owner, "_BRAINSTEM_OWNER_FD")),
                    (owner, "corpus_owner", tracked_scope(
                        "corpus", owner.corpus_owner, "_CORPUS_OWNER_FD")),
                    (self.capture.epoch_module, "prepare_epoch", prepare_epoch),
                    (self.source, "capture_successor_v3", collect),
                    (owner, "_retain_controller_source_successor_batch", retain_batch),
                    (owner, "_publish_controller_source_effects", effects),
                    (owner, "_acknowledge_controller_source_batch", ack),
                    (owner, "_write_memo", write),
                    (owner, "_controller_source_rollover_boundary", cut),
                    (owner, "iso", handoff_time)):
                stack.enter_context(mock.patch.object(module, name, replacement))
            blocked = self.forbidden("delivery writer or legacy successor capture")
            for module, name in (
                    (self.capture.journal, "reserve_delivery"),
                    (self.capture.journal, "deliver_reserved"),
                    (self.source, "capture_successor")):
                stack.enter_context(mock.patch.object(module, name, blocked))
            initial = self.forbidden("completed rollover requested initial capture")

            def invoke(pin, *, limits=None, limits_pin=None):
                selected_limits = self.epoch.limits if limits is None else limits
                selected_limits_pin = (self.live._sha(selected_limits)
                                       if limits_pin is None else limits_pin)
                try:
                    return getattr(owner, ENTRY)(
                        operation=initial, clock=clock,
                        journal_limits=copy.deepcopy(selected_limits),
                        expected_journal_limits_sha256=selected_limits_pin,
                        expected_adoption_sha256=pin)
                finally:
                    # Read back actual durable state for TestCase assertions;
                    # never substitute fixture memo for the runner's own load.
                    durable = owner.load_memo()
                    f.case.live.memo.clear()
                    f.case.live.memo.update(durable)

            trace.invoke, trace.owner = invoke, owner
            yield trace
            initial.assert_not_called()
            blocked.assert_not_called()

    def assert_completed(self, f, status, trace):
        self.assertEqual(trace.scope_events,
                         ["brainstem-enter", "corpus-enter", "corpus-exit", "brainstem-exit"])
        self.assertEqual(trace.active_scopes, [])
        durable = f.case.assert_final()
        self.assertEqual(status, f.case.admitted_status())
        self.assertEqual(f.case.batch, f.batch)
        self.assertEqual(f.batch["schema"], V3)
        self.assertGreater(durable["pulse_seq"], f.status["pulse_seq"])
        self.assertNotEqual(f.case.generation["generation_sha256"], f.generation["generation_sha256"])
        self.assertEqual(f.case.generation, f.case.live._read("LIVE_STATE_PATH"))
        self.assertEqual(f.batch["delivery_input"]["epoch_view"]["parent_generation"], f.generation)
        self.assertEqual(f.batch["delivery_input"]["epoch_view"]["parent_committed"], f.committed)
        self.assertEqual(f.batch["delivery_input"]["epoch_view"]["epoch_adoption"], f.adopted)
        self.assertEqual(f.batch["delivery_input"]["expected_adoption_sha256"], f.adopted["expected_adoption_sha256"])
        self.assertEqual(durable[epoch_tests.MARKER_KEY]["adoption_sha256"], f.adopted["expected_adoption_sha256"])
        self.assertEqual(f.case.generation["transition"]["state"]["deliveries"]["records"], [])
        self.assertEqual(trace.acknowledgments, [f.case.memo_before_ack["controller_source_effects_committed"]])
        self.assertTrue(trace.effects)
        with self.rollover.no_content_republication(f), f.case.forbid_ack_effects():
            completed = self.rollover.ack.read_completed(
                f.case.lib.__dict__, memo=f.case.live.memo, admitted_status=status)
        self.assertEqual(completed, {"status": "available", "batch": f.batch,
                                    "committed": durable["controller_source_committed"]})
        return durable

    def test_additive_runner_and_owning_entry_have_exact_explicit_contracts(self):
        for operation, expected in ((self.runner.run_v3, ("owner", *PARAMETERS)),
                                    (getattr(self.core, ENTRY), PARAMETERS)):
            with self.subTest(operation=operation.__name__):
                parameters = inspect.signature(operation).parameters
                self.assertEqual(tuple(parameters), expected)
                for name, parameter in parameters.items():
                    self.assertEqual(parameter.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD
                                     if name == "owner" else inspect.Parameter.KEYWORD_ONLY)
                    self.assertIs(parameter.default, inspect.Parameter.empty)
        self.assertEqual(tuple(inspect.signature(self.runner.run).parameters), ("owner", "operation"))
        self.assertEqual(tuple(inspect.signature(self.runner.run_v2).parameters), ("owner", "operation", "clock"))

    def test_actual_legacy_bootstrap_runs_to_v3_completion_under_one_owned_scope(self):
        with self.legacy() as f:
            parent_archive = ack_tests._path_image(f.case.archive_path(f.retained))
            with self.instrument(f) as trace:
                status = trace.invoke(None)
            self.assert_completed(f, status, trace)
            self.assertEqual(trace.prepares, [f.adopted])
            self.assertEqual(trace.captures, [f.batch])
            self.assertEqual(trace.retained, [self.source.native_bytes(f.case.lib.__dict__, f.batch)])
            stages = trace.stages
            for earlier, later in (("prepare", "reserve"), ("reserve", "clock"),
                                   ("clock", "capture"), ("capture", "retain"),
                                   ("retain", "effects"), ("effects", "ack-pending")):
                self.assertLess(stages.index(earlier), stages.index(later))
            self.assertEqual(ack_tests._path_image(f.case.archive_path(f.retained)), parent_archive)
            self.assertEqual(f.batch["delivery_input"]["parent_source_schema"], f.retained["schema"])

    def test_configured_zero_argument_cycle_runs_actual_legacy_to_v3_transaction(self):
        with self.legacy() as f:
            parent_archive = ack_tests._path_image(f.case.archive_path(f.retained))
            with self.instrument(f) as trace, mock.patch.object(
                    trace.owner.time, "time",
                    return_value=clock_tests.SUCCESSOR_OBSERVED_AT):
                try:
                    status = trace.owner._run_controller_source_cycle()
                finally:
                    durable = trace.owner.load_memo()
                    f.case.live.memo.clear()
                    f.case.live.memo.update(durable)
            self.assert_completed(f, status, trace)
            self.assertEqual(trace.prepares, [f.adopted])
            self.assertEqual(trace.captures, [f.batch])
            self.assertEqual(trace.retained, [
                self.source.native_bytes(f.case.lib.__dict__, f.batch)])
            self.assertEqual(
                ack_tests._path_image(f.case.archive_path(f.retained)),
                parent_archive)
            self.assertEqual(
                f.batch["delivery_input"]["parent_source_schema"],
                f.retained["schema"])

    def test_actual_v3_parent_runs_to_next_v3_completion_without_rebirth(self):
        with self.rollover.completed() as f:
            previous_adoption = copy.deepcopy(f.adopted)
            adoption_files = epoch_tests._tree(f.root)
            parent_archive = ack_tests._path_image(f.case.archive_path(f.retained))
            with self.instrument(f) as trace:
                status = trace.invoke(previous_adoption["expected_adoption_sha256"])
            self.assert_completed(f, status, trace)
            self.assertEqual(f.adopted, previous_adoption)
            self.assertEqual(epoch_tests._tree(f.root), adoption_files)
            self.assertEqual(ack_tests._path_image(f.case.archive_path(f.retained)), parent_archive)
            self.assertEqual(f.batch["delivery_input"]["parent_source_schema"], V3)
            self.assertEqual(trace.captures, [f.batch])
            self.assertEqual(trace.prepares, [previous_adoption])

    def test_actual_fixed_v3_wal_crash_retries_to_completion_without_new_acquisition(self):
        with self.legacy() as f:
            with self.instrument(f, crash_wal=True) as first, self.assertRaises(_WalDeath):
                first.invoke(None)
            retained_raw = Path(f.case.producer.source_path).read_bytes()
            retained_batch = copy.deepcopy(f.batch)
            original_adoption = copy.deepcopy(f.adopted)
            reserved = copy.deepcopy(f.case.live.memo)
            self.assertEqual(reserved["controller_source_committed"], f.committed)
            self.assertNotIn("controller_source_pending", reserved)
            self.assertEqual(first.effects, [])
            self.assertEqual(first.acknowledgments, [])
            wrong_pin = "0" * 64
            self.assertNotEqual(wrong_pin, original_adoption["expected_adoption_sha256"])
            changed_limits = copy.deepcopy(self.epoch.limits)
            self.assertNotEqual(changed_limits["max_requests"], 1)
            changed_limits["max_requests"] = 1
            for request in (
                    {"pin": wrong_pin},
                    {"pin": original_adoption["expected_adoption_sha256"],
                     "limits": changed_limits, "limits_pin": self.live._sha(changed_limits)}):
                with self.subTest(recovery_request=request):
                    before = self.capture.images(f)
                    blocked = self.forbidden("bad WAL request reached recovery or a write")
                    with self.instrument(f, recovery=True) as refused, \
                            mock.patch.object(refused.owner, "_recover_orphan_controller_source_successor_batch", blocked), \
                            mock.patch.object(refused.owner, "_write_memo", blocked), \
                            mock.patch.object(refused.owner, "atomic_write", blocked), \
                            self.assertRaises(REFUSALS):
                        refused.invoke(**request)
                    blocked.assert_not_called()
                    self.assertEqual(self.capture.images(f), before)
            with self.instrument(f, recovery=True) as retry:
                status = retry.invoke(original_adoption["expected_adoption_sha256"])
            durable = self.assert_completed(f, status, retry)
            self.assertEqual(durable["pulse_seq"], reserved["pulse_seq"])
            self.assertEqual(f.batch, retained_batch)
            self.assertEqual(f.case.archive_path(f.batch).read_bytes(), retained_raw)
            self.assertEqual(f.adopted, original_adoption)
            self.assertEqual(retry.prepares, [])
            self.assertEqual(retry.captures, [])
            self.assertEqual(retry.retained, [])
            self.assertNotIn("reserve", retry.stages)
            self.assertNotIn("clock", retry.stages)

    def test_existing_legacy_adoption_requires_external_pin_before_new_cycle(self):
        with self.legacy() as f:
            f.adopted = self.epoch.prepare(f.case, f.retained, f.committed, f.status)
            before = self.capture.images(f)
            blocked = self.forbidden("missing existing adoption pin reached a write")
            with self.instrument(f) as trace, \
                    mock.patch.object(trace.owner, "_write_memo", blocked), \
                    mock.patch.object(trace.owner, "atomic_write", blocked), \
                    self.assertRaises(REFUSALS):
                trace.invoke(None)
            blocked.assert_not_called()
            self.assertEqual(self.capture.images(f), before)
            self.assertEqual(trace.captures, [])
            self.assertEqual(trace.retained, [])
            self.assertEqual(trace.effects, [])
            self.assertNotIn("reserve", trace.stages)
            self.assertNotIn("clock", trace.stages)

    def test_genuine_legacy_successor_wal_is_not_silently_adopted_by_v3_runner(self):
        with self.legacy() as f:
            self.capture.reserve(f.case)
            request = self.epoch.idle.successor_request(f.case, f.retained, f.committed)
            with self.capture.capture_owner(f) as owner:
                with self.capture.no_effects(f, owner):
                    legacy = self.source.capture_successor(
                        owner.__dict__, memo=f.case.live.memo, retained_batch=f.retained,
                        committed=f.committed, **request)
                self.assertEqual(legacy["schema"], "sia-controller-source-batch-v2")
                self.assertNotIn("delivery_input", legacy)
                self.assertIsNone(self.rollover.publication.retain_successor(
                    owner.__dict__, memo=f.case.live.memo, retained_batch=f.retained,
                    committed=f.committed, batch=legacy,
                    expected_batch_sha256=legacy["batch_sha256"], seq=f.case.live.memo["pulse_seq"]))
            self.assertEqual(Path(f.case.producer.source_path).read_bytes(),
                             self.source.native_bytes(f.case.lib.__dict__, legacy))
            f.batch = legacy
            before = self.capture.images(f)
            blocked = self.forbidden("legacy WAL reached v3 recovery or a write")
            with self.instrument(f, recovery=True) as trace, \
                    mock.patch.object(trace.owner, "_recover_orphan_controller_source_successor_batch", blocked), \
                    mock.patch.object(trace.owner, "_write_memo", blocked), \
                    mock.patch.object(trace.owner, "atomic_write", blocked), \
                    self.assertRaises(REFUSALS):
                trace.invoke(None)
            blocked.assert_not_called()
            self.assertEqual(self.capture.images(f), before)
            self.assertEqual(f.case.live.memo["controller_source_committed"], f.committed)
            self.assertNotIn("controller_source_pending", f.case.live.memo)
            self.assertNotIn(epoch_tests.MARKER_KEY, f.case.live.memo)
            self.assertFalse(f.root.exists())


if __name__ == "__main__":
    unittest.main()
