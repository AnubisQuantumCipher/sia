"""Crash-safe recurring controller-source rollover -- RED contract.

The already-shipped v1 dispatcher is intentionally terminal after its first
completed source transaction.  This module specifies an additive v2
coordinator.  It must revalidate that completed transaction, derive and
capture one successor through explicit continuation front doors, retain the
successor in the same fixed batch slot as its write-ahead log, and only then
replace the completed memo authority with ordinary pending authority.

An exact fixed-slot orphan is recovery authority: its previously reserved
sequence and captured bytes are adopted without another clock, epoch build,
collector call, capture, or sequence allocation.  Once adopted, the existing
binding/handoff/effects/ACK pipeline resumes unchanged.  No generic live
recovery or legacy pulse marker is allowed on this branch.

These stopped seam doubles establish orchestration and crash ordering only.
They do not establish source truth, complete machine history, external
delivery, hostile same-user immutability, biological cognition, or a held-out
retrieval win.  Root alone executes this module sequentially.
"""

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import contextlib
import copy
import importlib
import inspect
import unittest
from unittest import mock

from tests import test_controller_source_runner as runner_tests
from tests import test_live_loop as live_tests


RUNNER_V1 = "_run_controller_source_transaction"
RUNNER_V2 = "_run_controller_source_transaction_v2"
OLD_SEQUENCE = runner_tests.RESERVED_SEQUENCE
# This is the frozen successor reservation already represented by the pulse
# synchronization fixtures, not a wall-clock or locally inferred measurement.
SUCCESSOR_SEQUENCE = 10
# JACKAL: status=exact parsed=10+1 exact=11.  This later reservation leaves
# the prior durable allocation as a gap when no fixed successor WAL exists.
POST_GAP_SEQUENCE = 11
SUCCESSOR_OBSERVED_AT = live_tests.EXPIRED_AT
ROLLOVER_STAGES = (
    "revalidate-completed",
    "read-committed",
    "successor-probe",
    "reserve-successor",
    "clock",
    "build-successor",
    "capture-successor",
    "validate-successor",
    "retain-successor",
    "successor-batch-durable",
    "successor-probe",
    "adopt-successor",
)


def _history_entry(batch):
    closure = batch["event_closure"]
    batches = [] if closure is None else closure["batches"]
    return {
        "source_returns": copy.deepcopy(batch["source_returns"]),
        "expected_source_returns_sha256":
            batch["source_returns"]["returns_sha256"],
        "event_batches": [
            {
                "batch": copy.deepcopy(member),
                "expected_batch_sha256": member["batch_sha256"],
            }
            for member in batches
        ],
    }


class _RolloverPipeline(runner_tests._Pipeline):
    """Completed predecessor plus one exact successor fixed-slot WAL."""

    def __init__(self, case, *, orphan=False, abandoned_sequence=False,
                 crash_at_boundary=False):
        super().__init__(case, state="completed")
        self.runner_module = importlib.import_module(
            "siacontrollersourcerunner")
        self.epoch_module = importlib.import_module("siacontrollerepoch")

        self.predecessor_batch = copy.deepcopy(self.batch)
        self.predecessor_batch.update({
            "epoch": {
                "epoch_id": "fixture-controller-source-epoch",
                "started_at": live_tests.START,
                "history": {"entries": []},
            },
            "source_returns": {
                "schema": "fixture-source-returns",
                "returns_sha256": "6" * 64,
            },
            "event_closure": {
                "batches": [{
                    "schema": "fixture-event-batch",
                    "batch_sha256": "5" * 64,
                }],
            },
        })
        self.predecessor_committed = copy.deepcopy(self.committed)
        self.predecessor_committed["source_batch_sha256"] = \
            self.predecessor_batch["batch_sha256"]
        self.memo["controller_source_committed"] = copy.deepcopy(
            self.predecessor_committed)

        self.prior_status = copy.deepcopy(self.fresh_status)
        self.prior_status["pulse_seq"] = OLD_SEQUENCE
        self.current_status = self.prior_status
        self.successor_sequence = (
            POST_GAP_SEQUENCE if abandoned_sequence
            else SUCCESSOR_SEQUENCE)
        self.fresh_status = copy.deepcopy(self.prior_status)
        self.fresh_status.update({
            "pulse_seq": self.successor_sequence,
            "publication_id": "7" * 32,
            "ts": runner_tests.STARTED_AT,
        })

        prior_entries = copy.deepcopy(
            self.predecessor_batch["epoch"]["history"]["entries"])
        successor_epoch = {
            "schema": "fixture-controller-source-successor-epoch",
            "epoch_id": self.predecessor_batch["epoch"]["epoch_id"],
            "started_at": self.predecessor_batch["epoch"]["started_at"],
            "predecessor": {
                "source_batch_sha256":
                    self.predecessor_batch["batch_sha256"],
                "live_generation_sha256": self.predecessor_committed[
                    "live_generation_sha256"],
            },
            "history": {
                "entries": prior_entries + [
                    _history_entry(self.predecessor_batch)],
            },
        }
        self.successor_request = {
            "epoch": successor_epoch,
            "expected_epoch_sha256": "4" * 64,
            "observed_at": SUCCESSOR_OBSERVED_AT,
        }
        self.batch = {
            "schema": "fixture-controller-source-successor-batch",
            "batch_sha256": "3" * 64,
            "observed_at": SUCCESSOR_OBSERVED_AT,
            "epoch": copy.deepcopy(successor_epoch),
        }
        self.receipt = {
            "schema": "fixture-controller-source-pending",
            "batch_sha256": self.batch["batch_sha256"],
        }
        self.binding.update({
            "publication_id": self.fresh_status["publication_id"],
            "seq": self.successor_sequence,
            "source_batch_sha256": self.batch["batch_sha256"],
        })
        self.effects_receipt = {"receipt_sha256": "2" * 64}
        self.committed = {
            "source_batch_sha256": self.batch["batch_sha256"],
            "live_generation_sha256": "1" * 64,
            "source_effects_receipt_sha256": "2" * 64,
        }

        self.successor_orphan = orphan
        self.crash_at_boundary = crash_at_boundary
        self.boundary_crashed = False
        if abandoned_sequence or orphan:
            self.memo["pulse_seq"] = SUCCESSOR_SEQUENCE
        self.operation = mock.Mock(side_effect=AssertionError(
            "completed source rollover invoked the initial operation"))
        self.clock = mock.Mock(side_effect=self._clock)

    def _admit_status(self, sequence):
        self.case.assertEqual(sequence, self.memo["pulse_seq"])
        label = ("fresh-status" if self.current_status == self.fresh_status
                 else "predecessor-status")
        self.trace.append(label)
        return copy.deepcopy(self.current_status)

    def _write_memo(self, memo):
        self.case.assertIs(memo, self.memo)
        self.case.assertEqual(memo["pulse_seq"], self.successor_sequence)
        self.case.assertEqual(
            memo.get("controller_source_committed"),
            self.predecessor_committed)
        self.case.assertNotIn("controller_source_pending", memo)
        self.case.assertIn("ready", memo)
        self.trace.append("reserve-successor")

    def _stage_binding(self, *, memo, admitted_status, seq):
        self.case.assertIs(memo, self.memo)
        self.case.assertEqual(admitted_status, self.prior_status)
        self.case.assertEqual(seq, self.successor_sequence)
        self.trace.append("binding")
        memo["controller_source_live_pending"] = copy.deepcopy(
            self.binding)
        self._cut("binding")

    def _ack(self, *, memo, admitted_status):
        self.case.assertIs(memo, self.memo)
        if "controller_source_committed" in memo:
            self.case.assertEqual(
                memo["controller_source_committed"],
                self.predecessor_committed)
            self.case.assertEqual(admitted_status, self.prior_status)
            self.trace.append("revalidate-completed")
            return None
        self.case.assertEqual(admitted_status, self.fresh_status)
        self.trace.append("ack")
        for key in runner_tests.SOURCE_KEYS:
            memo.pop(key, None)
        memo.pop("pulse_status_effects_pending", None)
        memo["controller_source_committed"] = copy.deepcopy(self.committed)
        memo["ready"] = {
            "v": 1, "completed_at": self.fresh_status["ts"],
            "kind": "pulse", "identity": self.binding["publication_id"],
        }

    def _read_committed(self, *, memo, admitted_status):
        self.case.assertIs(memo, self.memo)
        self.case.assertEqual(admitted_status, self.prior_status)
        self.case.assertEqual(
            memo.get("controller_source_committed"),
            self.predecessor_committed)
        self.trace.append("read-committed")
        return {
            "status": "available",
            "batch": copy.deepcopy(self.predecessor_batch),
            "committed": copy.deepcopy(self.predecessor_committed),
        }

    def _assert_wal_relationship(self):
        predecessor = self.batch.get("epoch", {}).get("predecessor")
        expected_predecessor = {
            "source_batch_sha256": self.predecessor_batch["batch_sha256"],
            "live_generation_sha256": self.predecessor_committed[
                "live_generation_sha256"],
        }
        if predecessor != expected_predecessor:
            raise RuntimeError(
                "controller source runner refused: successor-wal-predecessor")
        expected_entries = copy.deepcopy(
            self.predecessor_batch["epoch"]["history"]["entries"])
        expected_entries.append(_history_entry(self.predecessor_batch))
        if self.batch.get("epoch", {}).get("history", {}).get("entries") \
                != expected_entries:
            raise RuntimeError(
                "controller source runner refused: successor-wal-history")

    def _recover_successor(self, *, memo, retained_batch, committed, seq):
        self.case.assertIs(memo, self.memo)
        self.case.assertEqual(retained_batch, self.predecessor_batch)
        self.case.assertEqual(committed, self.predecessor_committed)
        self.case.assertEqual(seq, self.memo["pulse_seq"])
        self.trace.append("successor-probe")
        if not self.successor_orphan:
            return False
        self._assert_wal_relationship()
        self.case.assertEqual(seq, self.successor_sequence)
        self.case.assertIn("controller_source_committed", memo)
        memo.pop("controller_source_committed")
        memo.pop("ready", None)
        memo["controller_source_pending"] = copy.deepcopy(self.receipt)
        self.successor_orphan = False
        self.trace.append("adopt-successor")
        return True

    def _clock(self):
        self.trace.append("clock")
        return SUCCESSOR_OBSERVED_AT

    def _build_successor(self, owner, *, retained_batch, committed,
                         observed_at):
        self.case.assertIs(owner, self.lib.__dict__)
        self.case.assertEqual(retained_batch, self.predecessor_batch)
        self.case.assertEqual(committed, self.predecessor_committed)
        self.case.assertEqual(observed_at, SUCCESSOR_OBSERVED_AT)
        self.trace.append("build-successor")
        return copy.deepcopy(self.successor_request)

    def _capture_successor(self, **kwargs):
        self.case.assertEqual(set(kwargs), {
            "memo", "retained_batch", "committed", "epoch",
            "expected_epoch_sha256", "observed_at",
        })
        self.case.assertIs(kwargs["memo"], self.memo)
        self.case.assertEqual(
            kwargs["retained_batch"], self.predecessor_batch)
        self.case.assertEqual(kwargs["committed"],
                              self.predecessor_committed)
        self.case.assertEqual(
            {key: kwargs[key] for key in runner_tests.REQUEST_FIELDS},
            self.successor_request)
        self.case.assertIn("controller_source_committed", self.memo)
        self.case.assertNotIn("controller_source_pending", self.memo)
        self.trace.append("capture-successor")
        return copy.deepcopy(self.batch)

    def _validate_successor(self, owner, *, retained_batch, committed,
                            successor_batch, expected_batch_sha256):
        self.case.assertIs(owner, self.lib.__dict__)
        self.case.assertEqual(retained_batch, self.predecessor_batch)
        self.case.assertEqual(committed, self.predecessor_committed)
        self.case.assertEqual(successor_batch, self.batch)
        self.case.assertEqual(expected_batch_sha256,
                              self.batch["batch_sha256"])
        self._assert_wal_relationship()
        self.trace.append("validate-successor")
        return None

    def _retain_successor(self, **kwargs):
        self.case.assertEqual(set(kwargs), {
            "memo", "retained_batch", "committed", "batch",
            "expected_batch_sha256", "seq",
        })
        self.case.assertIs(kwargs["memo"], self.memo)
        self.case.assertEqual(
            kwargs["retained_batch"], self.predecessor_batch)
        self.case.assertEqual(kwargs["committed"],
                              self.predecessor_committed)
        self.case.assertEqual(kwargs["batch"], self.batch)
        self.case.assertEqual(kwargs["expected_batch_sha256"],
                              self.batch["batch_sha256"])
        self.case.assertEqual(kwargs["seq"], self.successor_sequence)
        self.case.assertIn("controller_source_committed", self.memo)
        self.case.assertNotIn("controller_source_pending", self.memo)
        self.case.assertIn("ready", self.memo)
        self.trace.append("retain-successor")
        self.successor_orphan = True
        return None

    def _boundary(self, phase):
        self.case.assertEqual(phase, "successor-batch-durable")
        self.case.assertTrue(self.successor_orphan)
        self.case.assertEqual(
            self.memo.get("controller_source_committed"),
            self.predecessor_committed)
        self.case.assertNotIn("controller_source_pending", self.memo)
        self.case.assertIn("ready", self.memo)
        self.trace.append("successor-batch-durable")
        if self.crash_at_boundary and not self.boundary_crashed:
            self.boundary_crashed = True
            raise KeyboardInterrupt(
                "fixture cut after successor fixed batch durability")

    def _capture(self, **_kwargs):
        raise AssertionError(
            "successor rollover entered initial-only capture front door")

    @contextlib.contextmanager
    def patched(self, *, forbid_creation=False, forbid_allocation=False):
        def forbidden(name):
            return mock.Mock(side_effect=AssertionError(
                "source rollover entered forbidden operation: " + name))

        with super().patched(
                forbid_allocation=forbid_allocation) as patches, \
                contextlib.ExitStack() as stack:
            extras = {
                "_read_committed_controller_source_batch": mock.Mock(
                    side_effect=self._read_committed),
                "_recover_orphan_controller_source_successor_batch":
                    mock.Mock(side_effect=self._recover_successor),
                "_capture_controller_source_successor_batch":
                    (forbidden("successor-capture") if forbid_creation else
                     mock.Mock(side_effect=self._capture_successor)),
                "_retain_controller_source_successor_batch":
                    (forbidden("successor-retention") if forbid_creation else
                     mock.Mock(side_effect=self._retain_successor)),
                "_controller_source_rollover_boundary": mock.Mock(
                    side_effect=self._boundary),
            }
            for name, replacement in extras.items():
                stack.enter_context(mock.patch.object(
                    self.lib, name, replacement, create=True))
            builder = (forbidden("successor-build") if forbid_creation else
                       mock.Mock(side_effect=self._build_successor))
            validator = (forbidden("successor-validation")
                         if forbid_creation else
                         mock.Mock(side_effect=self._validate_successor))
            stack.enter_context(mock.patch.object(
                self.epoch_module, "build_successor", builder))
            stack.enter_context(mock.patch.object(
                self.runner_module, "validate_successor_wal", validator,
                create=True))
            for name in ("_pending_pulse_marker",):
                stack.enter_context(mock.patch.object(
                    self.lib, name, forbidden(name)))
            merged = dict(patches)
            merged.update(extras)
            merged["build_successor"] = builder
            merged["validate_successor_wal"] = validator
            yield merged


class ControllerSourceRollover(unittest.TestCase):
    def setUp(self):
        self.fixture = runner_tests.ControllerSourceRunner(
            methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.lib = self.fixture.lib
        self.loop = self.fixture.loop
        self.base_memo = self.fixture.base_memo
        self.base_status = self.fixture.base_status
        self.runner_module = importlib.import_module(
            "siacontrollersourcerunner")

    def runner_v2(self):
        value = getattr(self.lib, RUNNER_V2, None)
        self.assertTrue(callable(value),
                        "missing recurring source transaction runner: "
                        + RUNNER_V2)
        return value

    def test_additive_v2_api_preserves_the_exact_v1_contract(self):
        v1 = getattr(self.lib, RUNNER_V1, None)
        self.assertTrue(callable(v1))
        self.assertEqual(tuple(inspect.signature(v1).parameters),
                         ("operation",))

        direct = getattr(self.runner_module, "run_v2", None)
        self.assertTrue(callable(direct),
                        "missing additive siacontrollersourcerunner.run_v2")
        direct_parameters = inspect.signature(direct).parameters
        self.assertEqual(tuple(direct_parameters),
                         ("owner", "operation", "clock"))
        self.assertEqual(direct_parameters["owner"].kind,
                         inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for name in ("operation", "clock"):
            self.assertEqual(direct_parameters[name].kind,
                             inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(direct_parameters[name].default,
                          inspect.Parameter.empty)

        wrapped = self.runner_v2()
        wrapped_parameters = inspect.signature(wrapped).parameters
        self.assertEqual(tuple(wrapped_parameters), ("operation", "clock"))
        for parameter in wrapped_parameters.values():
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)
        with self.assertRaises(TypeError):
            wrapped(lambda: None, lambda: SUCCESSOR_OBSERVED_AT)

    def test_completed_transaction_rolls_over_then_uses_existing_pipeline(self):
        pipeline = _RolloverPipeline(self)
        with pipeline.patched() as patches:
            result = self.runner_v2()(
                operation=pipeline.operation, clock=pipeline.clock)

        pipeline.operation.assert_not_called()
        pipeline.clock.assert_called_once_with()
        self.assertEqual(
            tuple(stage for stage in pipeline.trace
                  if stage in ROLLOVER_STAGES),
            ROLLOVER_STAGES)
        downstream = tuple(
            stage for stage in pipeline.trace
            if stage in runner_tests.MAJOR_STAGES)
        self.assertEqual(downstream, runner_tests.MAJOR_STAGES[2:])
        patches["_write_memo"].assert_called_once_with(pipeline.memo)
        patches["_capture_controller_source_batch"].assert_not_called()
        patches["_capture_controller_source_successor_batch"].\
            assert_called_once()
        patches["_retain_controller_source_successor_batch"].\
            assert_called_once()
        self.assertEqual(result, pipeline.fresh_status)
        self.assertIsNot(result, pipeline.fresh_status)
        self.assertEqual(
            pipeline.memo["controller_source_committed"],
            pipeline.committed)

    def test_fixed_successor_crash_replays_without_recollection_or_new_ids(self):
        pipeline = _RolloverPipeline(self, crash_at_boundary=True)
        with pipeline.patched() as patches:
            with self.assertRaisesRegex(
                    KeyboardInterrupt,
                    "after successor fixed batch durability"):
                self.runner_v2()(
                    operation=pipeline.operation, clock=pipeline.clock)
            self.assertTrue(pipeline.successor_orphan)
            self.assertEqual(
                pipeline.memo["controller_source_committed"],
                pipeline.predecessor_committed)
            self.assertNotIn("controller_source_pending", pipeline.memo)

            result = self.runner_v2()(
                operation=pipeline.operation, clock=pipeline.clock)

        pipeline.operation.assert_not_called()
        pipeline.clock.assert_called_once_with()
        patches["_write_memo"].assert_called_once()
        patches["build_successor"].assert_called_once()
        patches["_capture_controller_source_successor_batch"].\
            assert_called_once()
        patches["_retain_controller_source_successor_batch"].\
            assert_called_once()
        patches["_controller_source_rollover_boundary"].\
            assert_called_once_with("successor-batch-durable")
        self.assertEqual(
            pipeline.trace.count("revalidate-completed"), 2)
        self.assertEqual(pipeline.trace.count("adopt-successor"), 1)
        self.assertEqual(result, pipeline.fresh_status)
        self.assertEqual(
            pipeline.memo["controller_source_committed"],
            pipeline.committed)

    def test_preexisting_fixed_successor_is_adopted_without_new_work(self):
        pipeline = _RolloverPipeline(self, orphan=True)
        pipeline.clock.side_effect = AssertionError(
            "fixed successor orphan requested a replacement clock")
        with pipeline.patched(
                forbid_creation=True, forbid_allocation=True) as patches:
            result = self.runner_v2()(
                operation=pipeline.operation, clock=pipeline.clock)

        pipeline.operation.assert_not_called()
        pipeline.clock.assert_not_called()
        patches["_write_memo"].assert_not_called()
        patches["build_successor"].assert_not_called()
        patches["_capture_controller_source_batch"].assert_not_called()
        patches["_capture_controller_source_successor_batch"].\
            assert_not_called()
        patches["_retain_controller_source_successor_batch"].\
            assert_not_called()
        patches["_controller_source_rollover_boundary"].assert_not_called()
        self.assertEqual(pipeline.trace.count("successor-probe"), 1)
        self.assertEqual(pipeline.trace.count("adopt-successor"), 1)
        self.assertEqual(result, pipeline.fresh_status)

    def test_abandoned_sequence_without_a_wal_allocates_a_later_sequence(self):
        pipeline = _RolloverPipeline(self, abandoned_sequence=True)
        with pipeline.patched() as patches:
            result = self.runner_v2()(
                operation=pipeline.operation, clock=pipeline.clock)

        patches["_write_memo"].assert_called_once()
        self.assertEqual(pipeline.memo["pulse_seq"], POST_GAP_SEQUENCE)
        self.assertEqual(pipeline.fresh_status["pulse_seq"],
                         POST_GAP_SEQUENCE)
        self.assertEqual(pipeline.trace.count("reserve-successor"), 1)
        pipeline.clock.assert_called_once_with()
        patches["build_successor"].assert_called_once()
        patches["_capture_controller_source_successor_batch"].\
            assert_called_once()
        patches["_retain_controller_source_successor_batch"].\
            assert_called_once()
        self.assertEqual(result, pipeline.fresh_status)

    def test_bad_orphan_ancestry_refuses_before_adoption_or_downstream(self):
        mutations = {
            "successor-wal-predecessor": lambda pipeline:
                pipeline.batch["epoch"]["predecessor"].__setitem__(
                    "source_batch_sha256", "0" * 64),
            "successor-wal-history": lambda pipeline:
                pipeline.batch["epoch"]["history"].__setitem__(
                    "entries", []),
        }
        for reason, mutate in mutations.items():
            with self.subTest(reason=reason):
                pipeline = _RolloverPipeline(self, orphan=True)
                mutate(pipeline)
                with pipeline.patched(
                        forbid_creation=True,
                        forbid_allocation=True) as patches, \
                        self.assertRaisesRegex(
                            RuntimeError,
                            "controller source runner refused: " + reason):
                    self.runner_v2()(
                        operation=pipeline.operation,
                        clock=pipeline.clock)
                pipeline.operation.assert_not_called()
                pipeline.clock.assert_not_called()
                patches["_write_memo"].assert_not_called()
                patches["_stage_controller_source_live_binding"].\
                    assert_not_called()
                patches["_publish_controller_source_effects"].\
                    assert_not_called()
                patches["_acknowledge_controller_source_batch"].\
                    assert_called_once()
                self.assertIn("controller_source_committed", pipeline.memo)
                self.assertNotIn("controller_source_pending", pipeline.memo)

    def test_validator_rejects_commit_predecessor_and_complete_history_drift(self):
        validator = getattr(
            self.runner_module, "validate_successor_wal", None)
        self.assertTrue(callable(validator),
                        "missing inspectable successor WAL validator")
        parameters = inspect.signature(validator).parameters
        self.assertEqual(tuple(parameters), (
            "owner", "retained_batch", "committed", "successor_batch",
            "expected_batch_sha256",
        ))
        for name in (
                "retained_batch", "committed", "successor_batch",
                "expected_batch_sha256"):
            self.assertEqual(parameters[name].kind,
                             inspect.Parameter.KEYWORD_ONLY)

        retained = {
            "batch_sha256": "b" * 64,
            "epoch": {
                "epoch_id": "fixture-epoch",
                "started_at": live_tests.START,
                "history": {"entries": [{"prior": "complete"}]},
            },
            "source_returns": {
                "returns_sha256": "a" * 64,
                "runs": [{"source_id": "fixture-source", "events": []}],
            },
            "event_closure": {
                "batches": [{"batch_sha256": "9" * 64}],
            },
        }
        committed = {
            "source_batch_sha256": retained["batch_sha256"],
            "live_generation_sha256": "8" * 64,
            "source_effects_receipt_sha256": "7" * 64,
        }
        successor = {
            "batch_sha256": "6" * 64,
            "epoch": {
                "epoch_id": retained["epoch"]["epoch_id"],
                "started_at": retained["epoch"]["started_at"],
                "predecessor": {
                    "source_batch_sha256": retained["batch_sha256"],
                    "live_generation_sha256": committed[
                        "live_generation_sha256"],
                },
                "history": {
                    "entries": copy.deepcopy(
                        retained["epoch"]["history"]["entries"])
                    + [_history_entry(retained)],
                },
            },
        }
        original_retained = copy.deepcopy(retained)
        original_committed = copy.deepcopy(committed)
        original_successor = copy.deepcopy(successor)
        source = importlib.import_module("siasourcebatch")
        with mock.patch.object(
                source, "validate_batch") as validate_batch:
            self.assertIsNone(validator(
                self.lib.__dict__, retained_batch=retained,
                committed=committed, successor_batch=successor,
                expected_batch_sha256=successor["batch_sha256"]))
        self.assertEqual(validate_batch.call_args_list, [
            mock.call(self.lib.__dict__, retained,
                      retained["batch_sha256"]),
            mock.call(self.lib.__dict__, successor,
                      successor["batch_sha256"]),
        ])
        self.assertEqual(retained, original_retained)
        self.assertEqual(committed, original_committed)
        self.assertEqual(successor, original_successor)

        corruptions = {
            "successor-wal-commit": lambda old, marker, new:
                marker.__setitem__("source_batch_sha256", "0" * 64),
            "successor-wal-predecessor": lambda old, marker, new:
                new["epoch"]["predecessor"].__setitem__(
                    "live_generation_sha256", "0" * 64),
            "successor-wal-history": lambda old, marker, new:
                new["epoch"]["history"]["entries"][0].__setitem__(
                    "prior", "changed"),
        }
        for reason, corrupt in corruptions.items():
            with self.subTest(reason=reason):
                old = copy.deepcopy(retained)
                marker = copy.deepcopy(committed)
                new = copy.deepcopy(successor)
                corrupt(old, marker, new)
                with mock.patch.object(source, "validate_batch"), \
                        self.assertRaisesRegex(
                            RuntimeError,
                            "controller source runner refused: " + reason):
                    validator(
                        self.lib.__dict__, retained_batch=old,
                        committed=marker, successor_batch=new,
                        expected_batch_sha256=new["batch_sha256"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
