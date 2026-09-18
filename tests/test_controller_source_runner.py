"""Resident initial controller-source transaction dispatcher — RED contract.

``operation`` is a zero-argument callable that lazily constructs the existing
initial capture request: ``epoch``, ``expected_epoch_sha256`` and
``observed_at``.  It is invoked only when no source-owned durable state exists.
Every orphan or pending prefix is recovered before a new epoch, collector call
or pulse-sequence allocation can occur.

This v1 runner is deliberately terminal after one completed initial source
transaction.  It revalidates that commit and returns the freshly admitted
resident status; construction of a successor epoch/history is a distinct next
cut because the current capture contract correctly refuses prior source
authority.  These tests do not imply recurring rollover, source truth,
delivery, cognitive authorization, or a held-out win.

Only existing synthetic live-publication fixtures and stopped seam doubles are
used.  No real source, corpus, model, network, package manager, JACKAL call, or
resident SIA state is touched.  Root alone runs this module sequentially.
"""

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import contextlib
import copy
import inspect
import unittest
from unittest import mock

from tests import test_controller_source_status_effects as status_tests
from tests import test_live_loop as live_tests
from tests import test_live_publication as publication_tests
from tests import test_pulse_sync as pulse_tests


RUNNER = "_run_controller_source_transaction"
REQUEST_FIELDS = {"epoch", "expected_epoch_sha256", "observed_at"}
RESERVED_SEQUENCE = pulse_tests.FROZEN_EFFECTLESS_STATUS["pulse_seq"]
STARTED_AT = status_tests.STARTED_AT
MAJOR_STAGES = (
    "capture", "batch", "binding", "candidate", "transition", "handoff",
    "effects", "fresh-status", "ack",
)
SOURCE_KEYS = {
    "controller_source_pending", "controller_source_live_pending",
    "controller_source_effects_pending", "controller_source_effects_committed",
    "controller_source_committed",
}


class _Pipeline:
    """Deterministic durable-state double around the already tested seams."""

    def __init__(self, case, *, state="absent", crash_after=None):
        self.case = case
        self.lib = case.lib
        self.loop = case.loop
        self.memo = copy.deepcopy(case.base_memo)
        self.prior_status = copy.deepcopy(case.base_status)
        self.fresh_status = copy.deepcopy(case.base_status)
        self.fresh_status.update({
            "pulse_seq": RESERVED_SEQUENCE,
            "ts": STARTED_AT,
            "publication_id": "d" * 32,
        })
        self.current_status = self.prior_status
        self.request = {
            "epoch": {"schema": "fixture-controller-source-initial-epoch"},
            "expected_epoch_sha256": "e" * 64,
            "observed_at": live_tests.NOW,
        }
        self.batch = {
            "schema": "fixture-controller-source-batch",
            "batch_sha256": "b" * 64,
            "observed_at": live_tests.NOW,
        }
        self.receipt = {"batch_sha256": self.batch["batch_sha256"]}
        self.binding = {
            "publication_id": "d" * 32,
            "seq": RESERVED_SEQUENCE,
            "source_batch_sha256": self.batch["batch_sha256"],
        }
        self.candidate = {
            "prepare_inputs": {"schema": "fixture-live-input"},
            "expected_prepare_inputs_sha256": "c" * 64,
        }
        self.transition = {
            "schema": "fixture-live-transition",
            "transition_sha256": "f" * 64,
        }
        self.handoff = {
            "v": 1, "publication_id": self.binding["publication_id"],
            "effects": {"events_pulse": 1},
            "history": [STARTED_AT, 1],
        }
        self.effects_receipt = {"receipt_sha256": "a" * 64}
        self.committed = {
            "source_batch_sha256": self.batch["batch_sha256"],
            "live_generation_sha256": "9" * 64,
            "source_effects_receipt_sha256": "a" * 64,
        }
        self.trace = []
        self.crash_after = crash_after
        self.crashed = False
        self.orphan = state == "orphan"
        self.operation = mock.Mock(side_effect=self._operation)
        self._install(state)

    def _install(self, state):
        if state == "absent" or state == "orphan":
            return
        self.memo["pulse_seq"] = RESERVED_SEQUENCE
        self.memo.pop("ready", None)
        self.memo["controller_source_pending"] = copy.deepcopy(self.receipt)
        if state == "batch":
            return
        self.memo["controller_source_live_pending"] = copy.deepcopy(self.binding)
        if state == "binding":
            return
        self.memo["pulse_status_effects_pending"] = copy.deepcopy(self.handoff)
        if state == "handoff":
            return
        if state == "effects-pending":
            self.memo["controller_source_effects_pending"] = {
                "pending_sha256": "8" * 64,
            }
            return
        self.memo["controller_source_effects_committed"] = copy.deepcopy(
            self.effects_receipt)
        self.current_status = self.fresh_status
        if state == "effects-committed":
            return
        if state != "completed":
            raise AssertionError("unknown fixture source state: " + state)
        for key in SOURCE_KEYS:
            self.memo.pop(key, None)
        self.memo.pop("pulse_status_effects_pending", None)
        self.memo["controller_source_committed"] = copy.deepcopy(self.committed)
        self.memo["ready"] = {
            "v": 1, "completed_at": self.fresh_status["ts"], "kind": "pulse",
            "identity": self.binding["publication_id"],
        }

    def _cut(self, stage):
        if self.crash_after == stage and not self.crashed:
            self.crashed = True
            raise KeyboardInterrupt("fixture cut after " + stage)

    def _operation(self):
        self.trace.append("operation")
        return copy.deepcopy(self.request)

    def _present(self, memo):
        self.case.assertIs(memo, self.memo)
        return self.orphan or bool(SOURCE_KEYS.intersection(memo))

    def _recover_orphan(self, *, memo):
        self.case.assertIs(memo, self.memo)
        self.trace.append("source-recovery")
        if not self.orphan:
            return False
        self.orphan = False
        memo["controller_source_pending"] = copy.deepcopy(self.receipt)
        memo["pulse_seq"] = RESERVED_SEQUENCE
        memo.pop("ready", None)
        return True

    def _admit_status(self, sequence):
        self.case.assertEqual(sequence, self.memo["pulse_seq"])
        label = ("fresh-status" if self.current_status == self.fresh_status
                 else "initial-status")
        self.trace.append(label)
        return copy.deepcopy(self.current_status)

    def _write_memo(self, memo):
        self.case.assertIs(memo, self.memo)
        self.case.assertEqual(memo["pulse_seq"], RESERVED_SEQUENCE)
        self.trace.append("reserve")

    def _capture(self, **kwargs):
        self.case.assertEqual(set(kwargs), {
            "memo", "epoch", "expected_epoch_sha256", "observed_at"})
        self.case.assertIs(kwargs["memo"], self.memo)
        self.case.assertEqual(
            {key: kwargs[key] for key in REQUEST_FIELDS}, self.request)
        self.trace.append("capture")
        return copy.deepcopy(self.batch)

    def _stage_batch(self, *, memo, batch, expected_batch_sha256):
        self.case.assertIs(memo, self.memo)
        self.case.assertEqual(batch, self.batch)
        self.case.assertEqual(expected_batch_sha256, self.batch["batch_sha256"])
        self.trace.append("batch")
        memo["controller_source_pending"] = copy.deepcopy(self.receipt)
        memo.pop("ready", None)
        self._cut("batch")

    def _read_batch(self, *, memo):
        self.case.assertIs(memo, self.memo)
        return {"status": "pending", "batch": copy.deepcopy(self.batch),
                "receipt": copy.deepcopy(self.receipt)}

    def _stage_binding(self, *, memo, admitted_status, seq):
        self.case.assertIs(memo, self.memo)
        self.case.assertEqual(admitted_status, self.prior_status)
        self.case.assertEqual(seq, RESERVED_SEQUENCE)
        self.trace.append("binding")
        memo["controller_source_live_pending"] = copy.deepcopy(self.binding)
        self._cut("binding")

    def _binding(self, memo):
        self.case.assertIs(memo, self.memo)
        value = memo.get("controller_source_live_pending")
        return None if value is None else copy.deepcopy(value)

    def _prepare_candidate(self, *, memo, admitted_status):
        self.case.assertIs(memo, self.memo)
        self.case.assertEqual(admitted_status, self.prior_status)
        self.trace.append("candidate")
        return copy.deepcopy(self.candidate)

    def _transition(self, **prepare_inputs):
        self.case.assertEqual(prepare_inputs, self.candidate["prepare_inputs"])
        self.trace.append("transition")
        return copy.deepcopy(self.transition)

    def _pending_handoff(self, memo):
        self.case.assertIs(memo, self.memo)
        value = memo.get("pulse_status_effects_pending")
        return None if value is None else copy.deepcopy(value)

    def _stage_handoff(self, **kwargs):
        self.case.assertEqual(set(kwargs), {
            "memo", "admitted_status", "batch", "expected_batch_sha256",
            "source_live_pending", "candidate", "transition",
            "expected_transition_sha256", "started_at",
        })
        self.case.assertIs(kwargs["memo"], self.memo)
        self.case.assertEqual(kwargs["admitted_status"], self.prior_status)
        self.case.assertEqual(kwargs["batch"], self.batch)
        self.case.assertEqual(kwargs["expected_batch_sha256"],
                              self.batch["batch_sha256"])
        self.case.assertEqual(kwargs["source_live_pending"], self.binding)
        self.case.assertEqual(kwargs["candidate"], self.candidate)
        self.case.assertEqual(kwargs["transition"], self.transition)
        self.case.assertEqual(kwargs["expected_transition_sha256"],
                              self.transition["transition_sha256"])
        self.case.assertEqual(kwargs["started_at"], STARTED_AT)
        self.trace.append("handoff")
        self.memo["pulse_status_effects_pending"] = copy.deepcopy(self.handoff)
        self._cut("handoff")

    def _effects(self, *, memo, admitted_status):
        self.case.assertIs(memo, self.memo)
        self.case.assertEqual(admitted_status, self.prior_status)
        self.trace.append("effects")
        memo.pop("controller_source_effects_pending", None)
        memo["controller_source_effects_committed"] = copy.deepcopy(
            self.effects_receipt)
        self.current_status = self.fresh_status
        self._cut("effects")

    def _ack(self, *, memo, admitted_status):
        self.case.assertIs(memo, self.memo)
        self.case.assertEqual(admitted_status, self.fresh_status)
        self.trace.append("ack")
        for key in SOURCE_KEYS:
            memo.pop(key, None)
        memo.pop("pulse_status_effects_pending", None)
        memo["controller_source_committed"] = copy.deepcopy(self.committed)
        self._cut("ack")

    @contextlib.contextmanager
    def patched(self, *, forbid_allocation=False):
        def forbidden(name):
            return mock.Mock(side_effect=AssertionError(
                "source runner entered forbidden operation: " + name))

        with contextlib.ExitStack() as stack:
            patches = {
                "load_memo": mock.Mock(return_value=self.memo),
                "_controller_source_present": mock.Mock(side_effect=self._present),
                "_recover_orphan_controller_source_batch": mock.Mock(
                    side_effect=self._recover_orphan),
                "_require_status_sequence_not_ahead": mock.Mock(
                    side_effect=self._admit_status),
                "_write_memo": (forbidden("_write_memo") if forbid_allocation
                                else mock.Mock(side_effect=self._write_memo)),
                "_capture_controller_source_batch": mock.Mock(
                    side_effect=self._capture),
                "_stage_controller_source_batch": mock.Mock(
                    side_effect=self._stage_batch),
                "_read_pending_controller_source_batch": mock.Mock(
                    side_effect=self._read_batch),
                "_stage_controller_source_live_binding": mock.Mock(
                    side_effect=self._stage_binding),
                "_controller_source_live_binding_marker": mock.Mock(
                    side_effect=self._binding),
                "_prepare_controller_source_live_candidate": mock.Mock(
                    side_effect=self._prepare_candidate),
                "_pending_pulse_status_effects": mock.Mock(
                    side_effect=self._pending_handoff),
                "_stage_controller_source_status_effects": mock.Mock(
                    side_effect=self._stage_handoff),
                "_publish_controller_source_effects": mock.Mock(
                    side_effect=self._effects),
                "_acknowledge_controller_source_batch": mock.Mock(
                    side_effect=self._ack),
                "iso": mock.Mock(return_value=STARTED_AT),
            }
            for name, replacement in patches.items():
                stack.enter_context(mock.patch.object(
                    self.lib, name, replacement))
            stack.enter_context(mock.patch.object(
                self.loop, "prepare_pulse", side_effect=self._transition))
            for name in (
                    "_recover_pending_live_generation", "_pulse_transaction",
                    "_pulse_transaction_guarded", "_mark_pulse_publication"):
                stack.enter_context(mock.patch.object(
                    self.lib, name, forbidden(name)))
            stack.enter_context(mock.patch.object(
                self.lib.uuid, "uuid4", forbidden("uuid.uuid4")))
            yield patches


class ControllerSourceRunner(unittest.TestCase):
    def setUp(self):
        self.fixture = publication_tests.LivePublication(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.lib = self.fixture.lib
        self.loop = self.fixture.loop
        self.base_memo = copy.deepcopy(self.fixture.memo)
        self.base_status = copy.deepcopy(self.fixture.status)

    def runner(self):
        value = getattr(self.lib, RUNNER, None)
        self.assertTrue(callable(value),
                        "missing resident source transaction runner: " + RUNNER)
        return value

    def test_exact_single_keyword_only_operation_api(self):
        runner = self.runner()
        parameters = inspect.signature(runner).parameters
        self.assertEqual(tuple(parameters), ("operation",))
        self.assertEqual(parameters["operation"].kind,
                         inspect.Parameter.KEYWORD_ONLY)
        self.assertIs(parameters["operation"].default,
                      inspect.Parameter.empty)
        with self.assertRaises(TypeError):
            runner(lambda: None)

    def test_initial_source_transaction_uses_the_exact_specific_stage_order(self):
        pipeline = _Pipeline(self)
        legacy = {
            "load_thoughts": self.lib.load_thoughts,
            "add_thought": self.lib.add_thought,
            "materialize_agent_notes": self.lib.materialize_agent_notes,
            "verify_chains": self.lib.verify_chains,
            "create_take": self.lib.siatakes.create_take,
            "create_intent": self.lib.siatakes.create_intent,
        }

        def forbidden_legacy(name):
            return mock.Mock(side_effect=AssertionError(
                "source branch entered legacy functionality: " + name))

        with pipeline.patched() as patches, contextlib.ExitStack() as stack:
            for name in ("load_thoughts", "add_thought",
                         "materialize_agent_notes", "verify_chains"):
                stack.enter_context(mock.patch.object(
                    self.lib, name, forbidden_legacy(name)))
            for name in ("create_take", "create_intent"):
                stack.enter_context(mock.patch.object(
                    self.lib.siatakes, name, forbidden_legacy(name)))
            result = self.runner()(operation=pipeline.operation)

        observed = [stage for stage in pipeline.trace if stage in MAJOR_STAGES]
        self.assertEqual(tuple(observed), MAJOR_STAGES)
        self.assertEqual(pipeline.trace[:4], [
            "initial-status", "reserve", "operation", "capture"])
        pipeline.operation.assert_called_once_with()
        patches["_write_memo"].assert_called_once_with(pipeline.memo)
        self.assertEqual(result, pipeline.fresh_status)
        self.assertIsNot(result, pipeline.fresh_status)
        self.assertEqual(
            pipeline.memo["controller_source_committed"], pipeline.committed)
        for name, original in legacy.items():
            owner = self.lib.siatakes if name in ("create_take", "create_intent") \
                else self.lib
            self.assertIs(getattr(owner, name), original)

    def test_all_source_owned_prefixes_recover_before_new_work_or_allocation(self):
        for state in (
                "orphan", "batch", "binding", "handoff",
                "effects-pending", "effects-committed"):
            with self.subTest(state=state):
                pipeline = _Pipeline(self, state=state)
                pipeline.operation.side_effect = AssertionError(
                    "pending source state invoked a new epoch operation")
                with pipeline.patched(forbid_allocation=True) as patches:
                    result = self.runner()(operation=pipeline.operation)
                pipeline.operation.assert_not_called()
                patches["_capture_controller_source_batch"].assert_not_called()
                self.assertEqual(result, pipeline.fresh_status)
                self.assertEqual(
                    pipeline.memo["controller_source_committed"],
                    pipeline.committed)
                self.assertNotIn("_recover_pending_live_generation",
                                 pipeline.trace)

    def test_each_durable_crash_prefix_resumes_without_recollection_or_reallocation(self):
        for crash_after in ("batch", "binding", "handoff", "effects", "ack"):
            with self.subTest(crash_after=crash_after):
                pipeline = _Pipeline(self, crash_after=crash_after)
                with pipeline.patched() as patches:
                    with self.assertRaisesRegex(
                            KeyboardInterrupt,
                            "fixture cut after " + crash_after):
                        self.runner()(operation=pipeline.operation)
                    result = self.runner()(operation=pipeline.operation)
                pipeline.operation.assert_called_once_with()
                patches["_capture_controller_source_batch"].assert_called_once()
                patches["_stage_controller_source_batch"].assert_called_once()
                patches["_write_memo"].assert_called_once()
                self.assertEqual(result, pipeline.fresh_status)
                self.assertEqual(
                    pipeline.memo["controller_source_committed"],
                    pipeline.committed)

    def test_completed_transaction_revalidates_then_returns_fresh_status(self):
        pipeline = _Pipeline(self, state="completed")
        pipeline.operation.side_effect = AssertionError(
            "completed source transaction recollected")
        with pipeline.patched(forbid_allocation=True) as patches:
            result = self.runner()(operation=pipeline.operation)
        pipeline.operation.assert_not_called()
        patches["_capture_controller_source_batch"].assert_not_called()
        patches["_publish_controller_source_effects"].assert_not_called()
        patches["_acknowledge_controller_source_batch"].assert_called_once()
        self.assertEqual(pipeline.trace, ["fresh-status", "ack", "fresh-status"])
        self.assertEqual(result, pipeline.fresh_status)
        self.assertIsNot(result, pipeline.fresh_status)
        # A completed v1 run is terminal here: a successor epoch/history is
        # intentionally neither constructed nor claimed by this dispatcher.


if __name__ == "__main__":
    unittest.main(verbosity=2)
