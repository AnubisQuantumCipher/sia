"""Direct descriptor-backed controller-source rollover storage contract.

These tests compose the existing real source capture, live publication,
effects, acknowledgment, and temporary-root fixtures.  A completed predecessor
is therefore backed by its digest-named source archive, effects-receipt archive,
committed live generation, resident status, and compact memo authority before
the successor APIs are exercised.

The successor fixed slot is a WAL, not completion: its bytes may coexist with
the old immutable archive while the old completed memo remains the sole
authority.  One later memo replacement adopts those exact bytes as the
ordinary v1 pending receipt.  None of these local checks establishes source
truth, complete machine history, output delivery, hostile same-user
immutability, biological cognition, or a held-out retrieval win.

Root runs this composed module sequentially under the mission memory cap.
"""

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import contextlib
import copy
import functools
import importlib
import inspect
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_capture as capture_tests
from tests import test_live_loop as live_tests


SUCCESSOR_SEQUENCE = 10
SUCCESSOR_OBSERVED_AT = live_tests.EXPIRED_AT


class ControllerSourceRolloverStorage(unittest.TestCase):
    def setUp(self):
        self.source_batch = importlib.import_module("siasourcebatch")
        self.source_ack = importlib.import_module("siasourceack")
        self.source_publication = importlib.import_module(
            "siasourcepublication")
        self.epoch = importlib.import_module("siacontrollerepoch")

    @contextlib.contextmanager
    def completed(self):
        case = ack_tests.ControllerSourceAcknowledgment(
            methodName="runTest")
        try:
            case.setUp()
            case.source.policy = copy.deepcopy(self.epoch.LIVE_POLICY)
            case.source.profile["live_policy_sha256"] = \
                capture_tests.digest(case.source.policy)
            case.source.epoch.update(
                profile=case.source.profile,
                live_policy=case.source.policy)
            case.source.reseal_epoch()
            case.start_empty()
            self.assertIsNone(case.acknowledge())
            durable = case.assert_final()
            retained = copy.deepcopy(case.batch)
            committed = copy.deepcopy(
                durable["controller_source_committed"])
            status = copy.deepcopy(case.admitted_status())
            self.assertEqual(
                case.archive_path().read_bytes(),
                capture_tests.canonical(retained))
            yield case, retained, committed, status
        finally:
            case.doCleanups()

    @contextlib.contextmanager
    def successor_capture_owner(self, case):
        owner = case.source.lib
        with mock.patch.object(
                owner, "MEMO_PATH", case.live.paths["MEMO_PATH"]), \
                mock.patch.object(
                    owner, "CONTROLLER_SOURCE_BATCH_PATH",
                    str(case.producer.source_path)):
            yield owner

    def reserve_successor(self, case):
        self.assertLess(
            case.live.memo["pulse_seq"], SUCCESSOR_SEQUENCE)
        case.live.memo["pulse_seq"] = SUCCESSOR_SEQUENCE
        case.live._write(
            case.live.paths["MEMO_PATH"], case.live.memo)
        self.assertEqual(
            case.live._read("MEMO_PATH"), case.live.memo)

    def build_request(self, case, retained, committed):
        return self.epoch.build_successor(
            case.source.lib.__dict__, retained_batch=retained,
            committed=committed, observed_at=SUCCESSOR_OBSERVED_AT)

    def capture(self, case, retained, committed, request):
        with self.successor_capture_owner(case), \
                case.source.capture_boundary():
            result = self.source_batch.capture_successor(
                case.source.lib.__dict__, memo=case.live.memo,
                retained_batch=retained, committed=committed,
                **request)
        self.source_batch.validate_batch(
            case.source.lib.__dict__, result, result["batch_sha256"])
        self.assertEqual(result["epoch"], request["epoch"])
        self.assertEqual(result["epoch"]["predecessor"], {
            "source_batch_sha256": retained["batch_sha256"],
            "live_generation_sha256": committed[
                "live_generation_sha256"],
        })
        expected_history = copy.deepcopy(
            retained["epoch"]["history"])
        batches = ([] if retained["event_closure"] is None else
                   retained["event_closure"]["batches"])
        expected_history["entries"].append({
            "source_returns": copy.deepcopy(retained["source_returns"]),
            "expected_source_returns_sha256":
                retained["source_returns"]["returns_sha256"],
            "event_batches": [
                {
                    "batch": copy.deepcopy(batch),
                    "expected_batch_sha256": batch["batch_sha256"],
                }
                for batch in batches
            ],
        })
        self.assertEqual(result["epoch"]["history"], expected_history)
        return result

    def prepared(self, case, retained, committed):
        self.reserve_successor(case)
        request = self.build_request(case, retained, committed)
        batch = self.capture(case, retained, committed, request)
        return request, batch

    def retain(self, case, retained, committed, batch):
        return self.source_publication.retain_successor(
            case.lib.__dict__, memo=case.live.memo,
            retained_batch=retained, committed=committed,
            batch=batch, expected_batch_sha256=batch["batch_sha256"],
            seq=SUCCESSOR_SEQUENCE)

    def recover(self, case, retained, committed, *, memo=None):
        return self.source_publication.recover_successor(
            case.lib.__dict__,
            memo=case.live.memo if memo is None else memo,
            retained_batch=retained, committed=committed,
            seq=SUCCESSOR_SEQUENCE)

    def test_exact_additive_low_level_apis(self):
        contracts = (
            (self.source_batch.capture_successor, (
                "owner", "memo", "retained_batch", "committed", "epoch",
                "expected_epoch_sha256", "observed_at")),
            (self.source_ack.read_completed, (
                "owner", "memo", "admitted_status")),
            (self.source_publication.retain_successor, (
                "owner", "memo", "retained_batch", "committed", "batch",
                "expected_batch_sha256", "seq")),
            (self.source_publication.recover_successor, (
                "owner", "memo", "retained_batch", "committed", "seq")),
        )
        for operation, names in contracts:
            with self.subTest(operation=operation.__name__):
                parameters = inspect.signature(operation).parameters
                self.assertEqual(tuple(parameters), names)
                self.assertEqual(
                    parameters["owner"].kind,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD)
                for name in names[1:]:
                    self.assertEqual(
                        parameters[name].kind,
                        inspect.Parameter.KEYWORD_ONLY)
                    self.assertIs(
                        parameters[name].default,
                        inspect.Parameter.empty)

    def test_real_completed_archive_fixed_wal_and_pending_adoption(self):
        with self.completed() as (case, retained, committed, status):
            self.reserve_successor(case)
            completed_memo = capture_tests.canonical(case.live.memo)
            archive_raw = case.archive_path().read_bytes()
            fixed = Path(case.producer.source_path)

            view = self.source_ack.read_completed(
                case.lib.__dict__, memo=case.live.memo,
                admitted_status=status)
            self.assertEqual(view["status"], "available")
            self.assertEqual(view["batch"], retained)
            self.assertEqual(view["committed"], committed)

            request = self.build_request(case, retained, committed)
            forbidden = mock.Mock(side_effect=AssertionError(
                "initial-only capture reached successor collectors"))
            with self.successor_capture_owner(case), \
                    mock.patch.object(
                        case.source.lib, "sense_custom", forbidden), \
                    self.assertRaises(
                        self.source_batch.SourceBatchRefusal) as caught:
                self.source_batch.capture(
                    case.source.lib.__dict__, memo=case.live.memo,
                    **request)
            self.assertEqual(
                caught.exception.reason, "unbound-prior-source-history")
            forbidden.assert_not_called()

            successor = self.capture(
                case, retained, committed, request)
            self.assertFalse(fixed.exists())
            self.assertEqual(
                capture_tests.canonical(case.live.memo), completed_memo)
            self.assertEqual(case.archive_path().read_bytes(), archive_raw)

            self.assertIsNone(
                self.retain(case, retained, committed, successor))
            self.assertEqual(
                fixed.read_bytes(), capture_tests.canonical(successor))
            self.assertEqual(case.archive_path().read_bytes(), archive_raw)
            self.assertEqual(
                capture_tests.canonical(case.live.memo), completed_memo)
            self.assertIn("controller_source_committed", case.live.memo)
            self.assertIn("ready", case.live.memo)
            self.assertNotIn("controller_source_pending", case.live.memo)

            coexistence = self.source_ack.read_completed(
                case.lib.__dict__, memo=case.live.memo,
                admitted_status=status)
            self.assertEqual(coexistence["batch"], retained)
            self.assertEqual(coexistence["committed"], committed)

            before_v1 = case.images()
            with self.assertRaises(
                    self.source_batch.SourceBatchRefusal) as ambiguous:
                self.source_publication.recover_orphan(
                    case.lib.__dict__, memo=case.live.memo)
            self.assertEqual(
                ambiguous.exception.reason,
                "source-publication-other-recovery-authority")
            self.assertEqual(case.images(), before_v1)

            self.assertIs(
                self.recover(case, retained, committed), True)
            self.assertNotIn("controller_source_committed", case.live.memo)
            self.assertNotIn("ready", case.live.memo)
            self.assertIn("controller_source_pending", case.live.memo)
            self.assertEqual(
                case.live.memo["controller_source_pending"][
                    "batch_sha256"],
                successor["batch_sha256"])
            pending = self.source_publication.read_pending(
                case.lib.__dict__, memo=case.live.memo)
            self.assertEqual(pending["status"], "pending")
            self.assertEqual(pending["batch"], successor)
            self.assertIs(
                self.source_publication.recover_orphan(
                    case.lib.__dict__, memo=case.live.memo),
                False)

    def test_fixed_publication_precedes_the_only_memo_replacement(self):
        with self.completed() as (case, retained, committed, _status):
            _request, successor = self.prepared(
                case, retained, committed)
            fixed = Path(case.producer.source_path)
            completed_raw = Path(
                case.live.paths["MEMO_PATH"]).read_bytes()
            archive_raw = case.archive_path().read_bytes()
            events = []
            publish = case.lib.siaqueue.fixed_atomic_publish
            replace = case.lib.atomic_write

            def observed_publish(path, data, **kwargs):
                result = publish(path, data, **kwargs)
                if Path(path) != fixed:
                    return result
                self.assertEqual(
                    fixed.read_bytes(), capture_tests.canonical(successor))
                self.assertIn(
                    "controller_source_committed",
                    case.live._read("MEMO_PATH"))
                events.append("fixed-durable")
                return result

            def observed_replace(*args, **kwargs):
                self.assertEqual(
                    fixed.read_bytes(), capture_tests.canonical(successor))
                self.assertIn(
                    "controller_source_committed",
                    case.live._read("MEMO_PATH"))
                events.append("memo-replace")
                return replace(*args, **kwargs)

            with mock.patch.object(
                    case.lib.siaqueue, "fixed_atomic_publish",
                    side_effect=observed_publish), \
                    mock.patch.object(
                        case.lib, "atomic_write",
                        side_effect=observed_replace):
                self.assertIsNone(
                    self.retain(case, retained, committed, successor))
                self.assertEqual(events, ["fixed-durable"])
                self.assertEqual(
                    Path(case.live.paths["MEMO_PATH"]).read_bytes(),
                    completed_raw)
                self.assertIs(
                    self.recover(case, retained, committed), True)

            self.assertEqual(events, [
                "fixed-durable", "fixed-durable", "memo-replace",
            ])
            self.assertEqual(events.count("memo-replace"), 1)
            self.assertEqual(case.archive_path().read_bytes(), archive_raw)
            self.assertIn("controller_source_pending", case.live.memo)

    def test_fixed_wal_recovers_without_epoch_build_capture_or_collectors(self):
        with self.completed() as (case, retained, committed, _status):
            request, successor = self.prepared(
                case, retained, committed)
            self.assertIsNone(
                self.retain(case, retained, committed, successor))
            successor_raw = capture_tests.canonical(successor)
            successor_sha256 = successor["batch_sha256"]
            durable = case.live._read("MEMO_PATH")
            del request
            del successor

            def forbidden(*_args, **_kwargs):
                raise AssertionError(
                    "fixed successor recovery rebuilt or recollected")

            with mock.patch.object(
                    self.epoch, "build_successor",
                    side_effect=forbidden), \
                    mock.patch.object(
                        self.source_batch, "capture_successor",
                        side_effect=forbidden), \
                    mock.patch.object(
                        case.source.lib, "sense_custom",
                        side_effect=forbidden):
                self.assertIs(
                    self.recover(
                        case, retained, committed, memo=durable),
                    True)

            self.assertEqual(
                Path(case.producer.source_path).read_bytes(),
                successor_raw)
            self.assertEqual(
                durable["controller_source_pending"]["batch_sha256"],
                successor_sha256)
            self.assertNotIn("controller_source_committed", durable)
            self.assertEqual(case.live._read("MEMO_PATH"), durable)

    def test_relationship_and_mid_operation_mutations_refuse_closed(self):
        with self.completed() as (case, retained, committed, _status):
            self.reserve_successor(case)
            request = self.build_request(case, retained, committed)
            fixed = Path(case.producer.source_path)
            archive_raw = case.archive_path().read_bytes()
            memo_raw = Path(case.live.paths["MEMO_PATH"]).read_bytes()

            corruptions = {
                "successor-predecessor-mismatch": lambda epoch:
                    epoch["predecessor"].__setitem__(
                        "source_batch_sha256", "0" * 64),
                "successor-history-mismatch": lambda epoch:
                    epoch["history"].__setitem__(
                        "entries", copy.deepcopy(
                            retained["epoch"]["history"]["entries"])),
            }
            for reason, corrupt in corruptions.items():
                with self.subTest(reason=reason):
                    epoch = copy.deepcopy(request["epoch"])
                    corrupt(epoch)
                    epoch["expected_history_sha256"] = \
                        self.source_batch._component_sha(
                            case.source.lib.__dict__, epoch["history"])
                    expected = self.source_batch.native_sha(
                        case.source.lib.__dict__, epoch)
                    collector = mock.Mock(side_effect=AssertionError(
                        "invalid successor relationship reached collector"))
                    with self.successor_capture_owner(case), \
                            mock.patch.object(
                                case.source.lib, "sense_custom",
                                collector), \
                            self.assertRaises(
                                self.source_batch.SourceBatchRefusal) as caught:
                        self.source_batch.capture_successor(
                            case.source.lib.__dict__, memo=case.live.memo,
                            retained_batch=retained,
                            committed=committed, epoch=epoch,
                            expected_epoch_sha256=expected,
                            observed_at=SUCCESSOR_OBSERVED_AT)
                    self.assertEqual(caught.exception.reason, reason)
                    collector.assert_not_called()
                    self.assertFalse(fixed.exists())
                    self.assertEqual(
                        Path(case.live.paths["MEMO_PATH"]).read_bytes(),
                        memo_raw)
                    self.assertEqual(
                        case.archive_path().read_bytes(), archive_raw)

            moving_commit = copy.deepcopy(committed)
            original_custom = case.source.lib.sense_custom

            @functools.wraps(original_custom)
            def mutating_collector(*args, **kwargs):
                result = original_custom(*args, **kwargs)
                moving_commit["source_effects_receipt_sha256"] = "0" * 64
                return result

            senses = [
                mutating_collector if sense is original_custom else sense
                for sense in case.source.lib.SENSES
            ]
            with self.successor_capture_owner(case), \
                    case.source.capture_boundary(), \
                    mock.patch.object(
                        case.source.lib, "sense_custom",
                        mutating_collector), \
                    mock.patch.object(case.source.lib, "SENSES", senses), \
                    self.assertRaises(
                        self.source_batch.SourceBatchRefusal):
                self.source_batch.capture_successor(
                    case.source.lib.__dict__, memo=case.live.memo,
                    retained_batch=retained, committed=moving_commit,
                    **request)
            self.assertFalse(fixed.exists())
            self.assertEqual(
                Path(case.live.paths["MEMO_PATH"]).read_bytes(), memo_raw)
            self.assertEqual(case.archive_path().read_bytes(), archive_raw)

            successor = self.capture(
                case, retained, committed, request)
            moving_batch = copy.deepcopy(successor)
            publish = case.lib.siaqueue.fixed_atomic_publish

            def publish_then_mutate(*args, **kwargs):
                result = publish(*args, **kwargs)
                moving_batch["status"] = "mutated-after-fixed-publication"
                return result

            with mock.patch.object(
                    case.lib.siaqueue, "fixed_atomic_publish",
                    side_effect=publish_then_mutate), \
                    self.assertRaises(
                        self.source_batch.SourceBatchRefusal) as caught:
                self.retain(
                    case, retained, committed, moving_batch)
            self.assertEqual(
                caught.exception.reason, "source-successor-input-changed")
            self.assertEqual(
                fixed.read_bytes(), capture_tests.canonical(successor))
            self.assertIn("controller_source_committed", case.live.memo)
            self.assertNotIn("controller_source_pending", case.live.memo)
            self.assertEqual(
                Path(case.live.paths["MEMO_PATH"]).read_bytes(), memo_raw)
            self.assertEqual(case.archive_path().read_bytes(), archive_raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
