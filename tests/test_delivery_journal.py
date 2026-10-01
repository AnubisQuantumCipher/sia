"""RED contract for a durable output journal, not CLI or pulse integration.

Root alone runs this suite. Real pure-loop fixtures supply the ranked plan,
source versions, origins and already-declared timestamps. The byte sink is a
synthetic controller output endpoint, not a person, terminal or live service.
No new arithmetic score or timestamp oracle is introduced.

All public parameters are keyword-only and required. The journal directory
contains immutable <id>.intent.json, <id>.attempt.json and <id>.complete.json
leaves, plus its private lock/fixed publisher infrastructure. IDs are lowercase
UUID hex. Reserve is idempotent; an attempt is durable BEFORE output. An
attempt without completion cannot authorize another emission. Inspection is
read-only, retains pending intent IDs and never trims, acknowledges or repairs.

Closed intent: schema/id/epoch_id/consumer/ranked/rank_sha256/emitted_row_refs/
output_scope/output_utf8_base64/output_bytes/output_sha256/non_claims.
Closed reservation: schema/status/intent/intent_sha256/non_claims/
reservation_sha256. The intent file contains the intent, not its envelope.
Closed attempt: schema/id/epoch_id/intent_sha256/non_claims/attempt_sha256.
Closed completion: schema/status/intent_sha256/record/boundary/non_claims/
completion_sha256. The record is the unchanged real pure complete_delivery
result; its supplied-byte boundary remains distinct from the runtime envelope.
Closed inspection: schema/epoch_id/complete/records/pending/non_claims.

Reservation accounts for complete terminal JSON/body and future file slots,
not just existing physical bytes. Limits may be tighter, never wider. Failed
write/flush means outcome unknown. A returned flush followed by clock or
completion-publication failure is completed-unrecorded, not not-started.
No pulse claim/ACK, no-touch, CLI, model or database behavior is added here.
"""

import base64
import copy
import importlib
import inspect
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

from tests import test_live_loop as live_tests


REQUEST_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
REQUEST_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
REQUEST_C = "cccccccccccccccccccccccccccccccc"
INTENT_KEYS = {
    "schema", "id", "epoch_id", "consumer", "ranked", "rank_sha256",
    "emitted_row_refs", "output_scope", "output_utf8_base64", "output_bytes",
    "output_sha256", "non_claims",
}
RESERVATION_KEYS = {
    "schema", "status", "intent", "intent_sha256", "non_claims", "reservation_sha256",
}
ATTEMPT_KEYS = {
    "schema", "id", "epoch_id", "intent_sha256", "non_claims", "attempt_sha256",
}
COMPLETION_KEYS = {
    "schema", "status", "intent_sha256", "record", "boundary", "non_claims", "completion_sha256",
}
INSPECTION_KEYS = {"schema", "epoch_id", "complete", "records", "pending", "non_claims"}


class ByteSink:
    """An actual bounded test sink; hooks observe write/flush sequencing."""

    def __init__(self, *, short=False, before_write=None, before_flush=None):
        self.body = bytearray()
        self.events = []
        self.short = short
        self.before_write = before_write
        self.before_flush = before_flush

    def write(self, value):
        raw = bytes(value)
        self.events.append("write")
        if self.before_write is not None:
            self.before_write(raw)
        accepted = raw[:1] if self.short and self.events.count("write") == 1 else raw
        self.body.extend(accepted)
        return len(accepted)

    def flush(self):
        self.events.append("flush")
        if self.before_flush is not None:
            self.before_flush()


class DeliveryJournal(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("siadelivery")
        except ModuleNotFoundError as exc:
            self.fail("durable delivery journal must exist: " + str(exc))
        for name in ("reserve_delivery", "deliver_reserved", "inspect_deliveries"):
            self.assertTrue(callable(getattr(self.module, name, None)), name)
        self.assertTrue(hasattr(self.module, "DeliveryJournalRefusal"))
        self.assertTrue(hasattr(self.module, "NON_CLAIMS"))
        self.live = importlib.import_module("sialiveloop")
        self.queue = importlib.import_module("siaqueue")
        self.fx = live_tests.LiveLoopPureIntegration(methodName="runTest")
        self.fx._inputs()
        self.addCleanup(self.fx.doCleanups)
        prepared = self.fx._prepare(self.live)
        self.ranked = self.fx._rank(self.live, prepared)
        self.refs = list(self.ranked["order"])
        by_ref = {row["row_ref"]: row for row in self.ranked["rows"]}
        self.body = "π synthetic UTF-8 output\n".encode("utf-8") + live_tests.canonical(
            [by_ref[ref] for ref in self.refs]) + b"\n"
        self.temporary = tempfile.TemporaryDirectory(prefix="sia-delivery-journal-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self._directory("journal")
        self.limits = {
            "max_document_bytes": self.live.MAX_INPUT_BYTES,
            "max_body_bytes": self.live.MAX_CONTENT_BYTES,
            "max_pending_bytes": self.queue.MAX_PENDING_BYTES,
            "max_requests": self.queue.MAX_PENDING_REQUESTS,
            "max_scan_entries": self.queue.MAX_QUEUE_SCAN_ENTRIES,
        }
        self.kw = {
            "directory": str(self.directory), "ranked": self.ranked,
            "expected_ranked_sha256": self.ranked["rank_sha256"],
            "emitted_row_refs": self.refs, "output_utf8": self.body,
            "request_id": REQUEST_A, "consumer": "cli.ask", "limits": self.limits,
        }

    def _directory(self, name):
        path = self.root / name
        path.mkdir(mode=0o700)
        return path

    def _reserve(self, **changes):
        return self.module.reserve_delivery(**{**self.kw, **changes})

    def _deliver(self, reservation, *, sink=None, clock=None, **changes):
        sink = ByteSink() if sink is None else sink
        clock = (lambda: live_tests.DELIVERED_AT) if clock is None else clock
        return self.module.deliver_reserved(**{
            "directory": str(self.directory), "reservation": reservation,
            "expected_reservation_sha256": reservation["reservation_sha256"],
            "binary_sink": sink, "clock": clock, "limits": self.limits, **changes,
        })

    def _inspect(self, **changes):
        return self.module.inspect_deliveries(**{
            "directory": str(self.directory), "epoch_id": live_tests.EPOCH,
            "limits": self.limits, **changes,
        })

    def _path(self, request_id, kind):
        return self.directory / (request_id + "." + kind + ".json")

    def _disk(self, request_id, kind):
        return json.loads(self._path(request_id, kind).read_bytes())

    def _write_fixture(self, path, value):
        path.write_bytes(live_tests.canonical(value) + b"\n")
        path.chmod(0o600)

    def _refusal(self, action, output_state):
        with self.assertRaises(self.module.DeliveryJournalRefusal) as caught:
            action()
        self.assertIs(type(caught.exception.reason), str)
        self.assertTrue(caught.exception.reason)
        self.assertEqual(caught.exception.output_state, output_state)
        return caught.exception

    def _snapshot(self, *, records_only=False):
        result = {}
        for path in self.root.rglob("*"):
            if records_only and path.suffix != ".json":
                continue
            info = path.lstat()
            identity = (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                        info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            raw = path.read_bytes() if stat.S_ISREG(info.st_mode) else None
            result[str(path.relative_to(self.root))] = (identity, raw)
        return result

    def _assert_pending(self, *ids):
        inspected = self._inspect()
        self.assertEqual(inspected["pending"], sorted(ids))
        self.assertEqual(inspected["complete"], not ids)
        return inspected

    def _assert_no_output_files(self):
        self.assertFalse(self._path(REQUEST_A, "attempt").exists())
        self.assertFalse(self._path(REQUEST_A, "complete").exists())

    def test_public_api_is_closed_keyword_only_and_has_no_ambient_defaults(self):
        expected = {
            "reserve_delivery": set(self.kw),
            "deliver_reserved": {"directory", "reservation", "expected_reservation_sha256",
                                 "binary_sink", "clock", "limits"},
            "inspect_deliveries": {"directory", "epoch_id", "limits"},
        }
        for name, fields in expected.items():
            signature = inspect.signature(getattr(self.module, name))
            self.assertEqual(set(signature.parameters), fields)
            for parameter in signature.parameters.values():
                self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(parameter.default, inspect.Parameter.empty)
        self.assertTrue(self.module.NON_CLAIMS)
        self.assertTrue(all(type(value) is str and value for value in self.module.NON_CLAIMS))

    def test_reservation_retains_exact_plan_versions_refs_and_utf8_without_completion(self):
        before = copy.deepcopy(self.kw)
        reservation = self._reserve()
        self.assertEqual(set(reservation), RESERVATION_KEYS)
        self.assertEqual(reservation["schema"], "sia-live-delivery-reservation-v1")
        self.assertEqual(reservation["status"], "reserved")
        self.assertEqual(reservation["reservation_sha256"], live_tests.own_digest(reservation, "reservation_sha256"))
        self.assertEqual(reservation["non_claims"], list(self.module.NON_CLAIMS))
        intent = reservation["intent"]
        self.assertEqual(set(intent), INTENT_KEYS)
        self.assertEqual(intent["schema"], "sia-live-delivery-intent-v1")
        self.assertEqual(intent["id"], REQUEST_A)
        self.assertEqual(intent["epoch_id"], live_tests.EPOCH)
        self.assertEqual(intent["consumer"], "cli.ask")
        self.assertEqual(intent["ranked"], self.ranked)
        self.assertEqual(intent["rank_sha256"], self.ranked["rank_sha256"])
        self.assertEqual(intent["ranked"]["non_claims"], live_tests.NON_CLAIMS)
        self.assertEqual(intent["emitted_row_refs"], self.refs)
        self.assertEqual(intent["output_scope"], live_tests.BODY_SCOPE)
        self.assertEqual(base64.b64decode(intent["output_utf8_base64"], validate=True), self.body)
        self.assertEqual(intent["output_bytes"], len(self.body))
        self.assertEqual(intent["output_sha256"], live_tests.bytes_digest(self.body))
        self.assertEqual(intent["non_claims"], list(self.module.NON_CLAIMS))
        self.assertEqual(reservation["intent_sha256"], live_tests.digest(intent))
        self.assertEqual(self._disk(REQUEST_A, "intent"), intent)
        self._assert_no_output_files()
        self.assertEqual(self.kw, before)
        reservation["intent"]["ranked"]["versions"][0]["content"] = "detached caller edit"
        self.assertEqual(self.kw, before)
        self.assertNotEqual(self._disk(REQUEST_A, "intent")["ranked"]["versions"][0]["content"],
                            "detached caller edit")

    def test_exact_reservation_retry_is_idempotent_and_conflicting_reuse_refuses(self):
        reservation = self._reserve()
        before = self._path(REQUEST_A, "intent").stat()
        raw = self._path(REQUEST_A, "intent").read_bytes()
        self.assertEqual(self._reserve(), reservation)
        after = self._path(REQUEST_A, "intent").stat()
        self.assertEqual((before.st_dev, before.st_ino, before.st_mtime_ns),
                         (after.st_dev, after.st_ino, after.st_mtime_ns))
        for change in ({"output_utf8": b"different body\n"}, {"consumer": "cli.recall"},
                       {"emitted_row_refs": self.refs[:1]}):
            with self.subTest(change=change):
                self._refusal(lambda: self._reserve(**change), "not-started")
        self.assertEqual(self._path(REQUEST_A, "intent").read_bytes(), raw)
        self._assert_no_output_files()

    def test_short_write_all_and_flush_precede_clock_and_real_pure_completion(self):
        reservation = self._reserve()
        completed = []

        def before_write(raw):
            self.assertTrue(raw)
            attempt = self._disk(REQUEST_A, "attempt")
            self.assertEqual(set(attempt), ATTEMPT_KEYS)
            self.assertEqual(attempt["schema"], "sia-live-delivery-attempt-v1")
            self.assertEqual(attempt["id"], REQUEST_A)
            self.assertEqual(attempt["epoch_id"], live_tests.EPOCH)
            self.assertEqual(attempt["intent_sha256"], reservation["intent_sha256"])
            self.assertEqual(attempt["attempt_sha256"], live_tests.own_digest(attempt, "attempt_sha256"))
            self.assertEqual(attempt["non_claims"], list(self.module.NON_CLAIMS))
            self.assertFalse(self._path(REQUEST_A, "complete").exists())

        sink = ByteSink(short=True, before_write=before_write)

        def clock():
            self.assertEqual(sink.events[-1], "flush")
            self.assertEqual(bytes(sink.body), self.body)
            completed.append("clock")
            return live_tests.DELIVERED_AT

        with mock.patch.object(self.live, "complete_delivery", wraps=self.live.complete_delivery) as pure:
            result = self._deliver(reservation, sink=sink, clock=clock)
        self.assertEqual(completed, ["clock"])
        self.assertGreater(sink.events.count("write"), 1)
        self.assertEqual(sink.events.count("flush"), 1)
        self.assertEqual(bytes(sink.body), self.body)
        self.assertTrue(pure.called)
        self.assertEqual(set(result), COMPLETION_KEYS)
        self.assertEqual(result["schema"], "sia-live-delivery-completion-v1")
        self.assertEqual(result["status"], "service-output-completed")
        self.assertEqual(result["intent_sha256"], reservation["intent_sha256"])
        self.assertEqual(result["boundary"], "write-all-and-flush-returned")
        self.assertEqual(result["non_claims"], list(self.module.NON_CLAIMS))
        self.assertEqual(result["completion_sha256"], live_tests.own_digest(result, "completion_sha256"))
        expected = self.fx._delivery(self.live, self.ranked, refs=self.refs, body=self.body, request_id=REQUEST_A)
        self.assertEqual(result["record"], expected)
        self.assertEqual(result["record"]["boundary"], "supplied-bytes-admitted-not-observed-output-v1")
        self.assertEqual(result["record"]["non_claims"], live_tests.NON_CLAIMS)
        self.assertEqual(self._disk(REQUEST_A, "complete"), result)

    def test_completed_retry_returns_exact_receipt_without_emit_flush_or_clock(self):
        reservation = self._reserve()
        completed = self._deliver(reservation)
        before = self._snapshot(records_only=True)
        sink = mock.Mock()
        sink.write.side_effect = AssertionError("completed output must not repeat")
        sink.flush.side_effect = AssertionError("completed output must not flush again")
        clock = mock.Mock(side_effect=AssertionError("completed output must not acquire another clock"))
        self.assertEqual(self._deliver(reservation, sink=sink, clock=clock), completed)
        sink.write.assert_not_called()
        sink.flush.assert_not_called()
        clock.assert_not_called()
        self.assertEqual(self._snapshot(records_only=True), before)

    def test_write_exception_retains_unknown_attempt_and_refuses_ambiguous_retry(self):
        reservation = self._reserve()
        sink = ByteSink()

        def fail(value):
            sink.body.extend(bytes(value)[:1])
            raise BrokenPipeError("synthetic partial output")

        sink.write = fail
        self._refusal(lambda: self._deliver(reservation, sink=sink), "unknown")
        self.assertTrue(sink.body)
        self.assertTrue(self._path(REQUEST_A, "attempt").exists())
        self.assertFalse(self._path(REQUEST_A, "complete").exists())
        before = self._snapshot(records_only=True)
        retry = ByteSink()
        clock = mock.Mock(side_effect=AssertionError("unknown attempt must not read a clock"))
        self._refusal(lambda: self._deliver(reservation, sink=retry, clock=clock), "unknown")
        self.assertFalse(retry.events)
        clock.assert_not_called()
        self.assertEqual(self._snapshot(records_only=True), before)
        self._assert_pending(REQUEST_A)

    def test_invalid_write_return_is_unknown_not_a_successful_byte_witness(self):
        for invalid in (None, True, 0, -1, "written", sys.maxsize):
            with self.subTest(invalid=invalid):
                directory = self._directory("return-" + str(invalid))
                reservation = self._reserve(directory=str(directory))
                sink = mock.Mock()
                sink.write.return_value = invalid
                clock = mock.Mock(side_effect=AssertionError("invalid write must not read clock"))
                self._refusal(lambda: self._deliver(reservation, directory=str(directory), sink=sink, clock=clock),
                              "unknown")
                sink.flush.assert_not_called()
                clock.assert_not_called()
                self.assertFalse((directory / (REQUEST_A + ".complete.json")).exists())

    def test_flush_failure_is_unknown_and_cannot_create_completion(self):
        reservation = self._reserve()

        def broken_flush():
            raise OSError("synthetic flush failure")

        sink = ByteSink(before_flush=broken_flush)
        clock = mock.Mock(side_effect=AssertionError("failed flush must not read clock"))
        self._refusal(lambda: self._deliver(reservation, sink=sink, clock=clock), "unknown")
        self.assertEqual(bytes(sink.body), self.body)
        clock.assert_not_called()
        self.assertFalse(self._path(REQUEST_A, "complete").exists())
        self._assert_pending(REQUEST_A)

    def test_clock_failure_after_returned_flush_is_completed_unrecorded(self):
        reservation = self._reserve()
        sink = ByteSink()
        clock = mock.Mock(side_effect=OSError("synthetic clock unavailable"))
        self._refusal(lambda: self._deliver(reservation, sink=sink, clock=clock), "completed-unrecorded")
        self.assertEqual(bytes(sink.body), self.body)
        self.assertEqual(sink.events[-1], "flush")
        clock.assert_called_once_with()
        self.assertFalse(self._path(REQUEST_A, "complete").exists())
        self._assert_pending(REQUEST_A)

    def test_invalid_completion_clock_retains_completed_unrecorded_not_fabricated_time(self):
        for stamp in (True, float("inf"), "2000000009", live_tests.START):
            with self.subTest(stamp=stamp):
                directory = self._directory("clock-" + str(stamp))
                reservation = self._reserve(directory=str(directory))
                sink = ByteSink()
                self._refusal(lambda: self._deliver(reservation, directory=str(directory), sink=sink,
                                                   clock=lambda: stamp), "completed-unrecorded")
                self.assertEqual(bytes(sink.body), self.body)
                self.assertFalse((directory / (REQUEST_A + ".complete.json")).exists())

    def test_attempt_publication_must_return_durable_before_first_write(self):
        reservation = self._reserve()
        publish = self.queue.fixed_atomic_publish

        def refuse_attempt(path, data, **kwargs):
            if str(path).endswith(".attempt.json"):
                raise OSError("synthetic attempt publication failure")
            return publish(path, data, **kwargs)

        sink = ByteSink()
        clock = mock.Mock(side_effect=AssertionError("unstarted output must not read clock"))
        with mock.patch.object(self.queue, "fixed_atomic_publish", side_effect=refuse_attempt):
            self._refusal(lambda: self._deliver(reservation, sink=sink, clock=clock), "not-started")
        self.assertFalse(sink.events)
        clock.assert_not_called()
        self.assertFalse(self._path(REQUEST_A, "complete").exists())

    def test_completion_publication_failure_does_not_relabel_emitted_output(self):
        reservation = self._reserve()
        publish = self.queue.fixed_atomic_publish

        def refuse_completion(path, data, **kwargs):
            if str(path).endswith(".complete.json"):
                raise OSError("synthetic completion publication failure")
            return publish(path, data, **kwargs)

        sink = ByteSink()
        with mock.patch.object(self.queue, "fixed_atomic_publish", side_effect=refuse_completion):
            self._refusal(lambda: self._deliver(reservation, sink=sink), "completed-unrecorded")
        self.assertEqual(bytes(sink.body), self.body)
        self.assertEqual(sink.events[-1], "flush")
        self.assertFalse(self._path(REQUEST_A, "complete").exists())
        self._assert_pending(REQUEST_A)

    def test_attempt_published_but_enqueue_return_failed_still_blocks_an_ambiguous_retry(self):
        reservation = self._reserve()
        publish = self.queue.fixed_atomic_publish

        def late_attempt_failure(path, data, **kwargs):
            result = publish(path, data, **kwargs)
            if str(path).endswith(".attempt.json"):
                raise OSError("synthetic post-publication return failure")
            return result

        sink = ByteSink()
        with mock.patch.object(self.queue, "fixed_atomic_publish", side_effect=late_attempt_failure):
            self._refusal(lambda: self._deliver(reservation, sink=sink), "not-started")
        self.assertFalse(sink.events)
        self.assertTrue(self._path(REQUEST_A, "attempt").exists())
        self._refusal(lambda: self._deliver(reservation, sink=sink), "unknown")
        self.assertFalse(sink.events)
        self._assert_pending(REQUEST_A)

    def test_completion_published_but_return_failed_can_be_readmitted_without_reemission(self):
        reservation = self._reserve()
        publish = self.queue.fixed_atomic_publish

        def late_completion_failure(path, data, **kwargs):
            result = publish(path, data, **kwargs)
            if str(path).endswith(".complete.json"):
                raise OSError("synthetic post-publication return failure")
            return result

        sink = ByteSink()
        with mock.patch.object(self.queue, "fixed_atomic_publish", side_effect=late_completion_failure):
            self._refusal(lambda: self._deliver(reservation, sink=sink), "completed-unrecorded")
        self.assertEqual(bytes(sink.body), self.body)
        existing = self._disk(REQUEST_A, "complete")
        retry = ByteSink()
        clock = mock.Mock(side_effect=AssertionError("retained completion does not need a new clock"))
        self.assertEqual(self._deliver(reservation, sink=retry, clock=clock), existing)
        self.assertFalse(retry.events)
        clock.assert_not_called()

    def test_inspect_is_read_only_and_distinguishes_empty_pending_and_completed(self):
        empty_before = self._snapshot()
        empty = self._inspect()
        self.assertEqual(self._snapshot(), empty_before)
        self.assertEqual(set(empty), INSPECTION_KEYS)
        self.assertEqual(empty, {"schema": "sia-live-delivery-journal-v1", "epoch_id": live_tests.EPOCH,
                                 "complete": True, "records": [], "pending": [],
                                 "non_claims": list(self.module.NON_CLAIMS)})
        reservation = self._reserve()
        self._assert_pending(REQUEST_A)
        completed = self._deliver(reservation)
        before = self._snapshot()
        inspected = self._assert_pending()
        self.assertEqual(inspected["records"], [completed["record"]])
        self.assertEqual(self._snapshot(), before)
        inspected["records"][0]["rows"].clear()
        self.assertEqual(self._inspect()["records"], [completed["record"]])

    def test_inspection_order_is_completion_time_then_id_not_filename_or_directory_order(self):
        later = self._reserve(request_id=REQUEST_A)
        tied = self._reserve(request_id=REQUEST_C)
        earlier = self._reserve(request_id=REQUEST_B)
        result_later = self._deliver(later, clock=lambda: live_tests.DELIVERED_AT)
        result_tied = self._deliver(tied, clock=lambda: live_tests.NOW)
        result_earlier = self._deliver(earlier, clock=lambda: live_tests.NOW)
        self.assertEqual(self._inspect()["records"],
                         [result_earlier["record"], result_tied["record"], result_later["record"]])

    def test_inspect_pending_after_attempt_does_not_infer_unsuccessful_delivery(self):
        reservation = self._reserve()
        self._refusal(lambda: self._deliver(reservation, clock=lambda: (_ for _ in ()).throw(OSError("clock"))),
                      "completed-unrecorded")
        before = self._snapshot()
        inspected = self._assert_pending(REQUEST_A)
        self.assertEqual(inspected["records"], [])
        self.assertEqual(self._snapshot(), before)
        self.assertNotIn("not_delivered", inspected)
        self.assertNotIn("acknowledged", inspected)
        self.assertNotIn("consumed", inspected)

    def test_request_ids_and_consumers_are_closed_not_pure_loop_path_tokens(self):
        invalid_ids = ("", "A" * 32, "delivery/fixture", "../outside", REQUEST_A + ".json", True)
        for request_id in invalid_ids:
            with self.subTest(request_id=request_id):
                self._refusal(lambda: self._reserve(request_id=request_id), "not-started")
        for consumer in ("mcp", "user", "cli.query", "cli.ask ", True):
            with self.subTest(consumer=consumer):
                self._refusal(lambda: self._reserve(consumer=consumer), "not-started")
        self.assertFalse(list(self.directory.glob("*.json")))
        recall = self._reserve(consumer="cli.recall")
        self.assertEqual(recall["intent"]["consumer"], "cli.recall")

    def test_limits_are_complete_strict_positive_bounded_and_cannot_widen(self):
        for key in self.limits:
            missing = dict(self.limits)
            del missing[key]
            with self.subTest(key=key, case="missing"):
                self._refusal(lambda: self._reserve(limits=missing), "not-started")
            for value in (True, 0, -1, float("inf"), "1", sys.maxsize):
                with self.subTest(key=key, value=value):
                    self._refusal(lambda: self._reserve(limits={**self.limits, key: value}), "not-started")
        self._refusal(lambda: self._reserve(limits={**self.limits, "allow_overflow": True}), "not-started")
        self.assertFalse(list(self.directory.glob("*.json")))

    def test_each_capacity_refuses_before_publication_without_clipping(self):
        publish = mock.Mock(side_effect=AssertionError("capacity refusal must precede publication"))
        for key in ("max_document_bytes", "max_body_bytes", "max_pending_bytes", "max_scan_entries"):
            with self.subTest(key=key), mock.patch.object(self.queue, "fixed_atomic_publish", publish):
                self._refusal(lambda: self._reserve(limits={**self.limits, key: 1}), "not-started")
        publish.assert_not_called()
        self.assertFalse(list(self.directory.glob("*.json")))

    def test_terminal_footprint_is_reserved_not_only_current_intent_bytes(self):
        probe = self._directory("probe")
        self._reserve(directory=str(probe))
        intent_bytes = (probe / (REQUEST_A + ".intent.json")).stat().st_size
        self.assertLess(intent_bytes, self.limits["max_pending_bytes"])
        publish = mock.Mock(side_effect=AssertionError("incomplete terminal footprint must not publish"))
        with mock.patch.object(self.queue, "fixed_atomic_publish", publish):
            self._refusal(lambda: self._reserve(limits={**self.limits, "max_pending_bytes": intent_bytes}),
                          "not-started")
        publish.assert_not_called()
        self.assertFalse(self._path(REQUEST_A, "intent").exists())

    def test_retained_reservations_count_even_after_completion_and_never_evict(self):
        limits = {**self.limits, "max_requests": 1}
        reservation = self._reserve(limits=limits)
        self._refusal(lambda: self._reserve(request_id=REQUEST_B, limits=limits), "not-started")
        self._deliver(reservation, limits=limits)
        before = self._snapshot(records_only=True)
        self._refusal(lambda: self._reserve(request_id=REQUEST_B, limits=limits), "not-started")
        self.assertEqual(self._snapshot(records_only=True), before)
        self.assertTrue(self._path(REQUEST_A, "intent").exists())
        self.assertTrue(self._path(REQUEST_A, "attempt").exists())
        self.assertTrue(self._path(REQUEST_A, "complete").exists())

    def test_input_body_and_complete_plan_refusals_precede_any_immutable_record(self):
        bad_rank = copy.deepcopy(self.ranked)
        bad_rank["rows"][0]["row"]["score"] = float("inf")
        cyclic = copy.deepcopy(self.ranked)
        cyclic["extra"] = cyclic
        changes = (
            {"expected_ranked_sha256": "0" * 64}, {"ranked": bad_rank}, {"ranked": cyclic},
            {"output_utf8": self.body.decode("utf-8")}, {"output_utf8": b"\xff"},
            {"emitted_row_refs": [self.refs[0], self.refs[0]]},
            {"emitted_row_refs": ["foreign-row"]},
        )
        with mock.patch.object(self.queue, "fixed_atomic_publish",
                               side_effect=AssertionError("invalid domain must precede publication")):
            for change in changes:
                with self.subTest(fields=list(change)):
                    self._refusal(lambda: self._reserve(**change), "not-started")
        self.assertFalse(list(self.directory.glob("*.json")))

    def test_reservation_and_named_intent_hashes_are_independently_admitted_before_output(self):
        reservation = self._reserve()
        bad = copy.deepcopy(reservation)
        bad["intent"]["output_sha256"] = "0" * 64
        sink = ByteSink()
        self._refusal(lambda: self._deliver(bad, sink=sink), "not-started")
        bad["intent_sha256"] = live_tests.digest(bad["intent"])
        bad["reservation_sha256"] = live_tests.own_digest(bad, "reservation_sha256")
        self._refusal(lambda: self._deliver(bad, sink=sink), "not-started")
        self.assertFalse(sink.events)
        self._assert_no_output_files()
        self.assertEqual(self._disk(REQUEST_A, "intent"), reservation["intent"])

    def test_same_slug_source_substitution_and_origin_relabeling_are_not_admitted(self):
        for field, value in (("content", "different source bytes"), ("origin", "legacy-unlabeled"),
                             ("source_sha256", "0" * 64)):
            with self.subTest(field=field):
                ranked = copy.deepcopy(self.ranked)
                self.assertNotEqual(ranked["versions"][0][field], value)
                ranked["versions"][0][field] = value
                ranked["rank_sha256"] = live_tests.own_digest(ranked, "rank_sha256")
                self._refusal(lambda: self._reserve(ranked=ranked, expected_ranked_sha256=ranked["rank_sha256"]),
                              "not-started")
        self.assertFalse(list(self.directory.glob("*.json")))

    def test_private_regular_single_link_records_and_directory_are_required(self):
        reservation = self._reserve()
        self._deliver(reservation)
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        for kind in ("intent", "attempt", "complete"):
            info = self._path(REQUEST_A, kind).lstat()
            self.assertTrue(stat.S_ISREG(info.st_mode))
            self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
            self.assertEqual(info.st_uid, os.geteuid())
            self.assertEqual(info.st_nlink, 1)
        self.directory.chmod(0o755)
        self._refusal(self._inspect, "not-started")
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o755)

    def test_symlink_directory_or_record_is_not_followed_or_repaired(self):
        alias = self.root / "alias"
        alias.symlink_to(self.directory, target_is_directory=True)
        self._refusal(lambda: self._reserve(directory=str(alias)), "not-started")
        reservation = self._reserve()
        target = self.root / "retained-intent.json"
        self._path(REQUEST_A, "intent").rename(target)
        self._path(REQUEST_A, "intent").symlink_to(target)
        sink = ByteSink()
        self._refusal(lambda: self._deliver(reservation, sink=sink), "not-started")
        self._refusal(self._inspect, "not-started")
        self.assertFalse(sink.events)
        self.assertTrue(self._path(REQUEST_A, "intent").is_symlink())
        self.assertEqual(json.loads(target.read_bytes()), reservation["intent"])

    def test_record_permissions_and_hardlink_aliases_refuse_without_chmod_or_cleanup(self):
        self._reserve()
        path = self._path(REQUEST_A, "intent")
        path.chmod(0o644)
        self._refusal(self._inspect, "not-started")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        path.chmod(0o600)
        alias = self.root / "hardlink.json"
        os.link(path, alias)
        self._refusal(self._inspect, "not-started")
        self.assertTrue(alias.exists())
        self.assertTrue(path.exists())

    def test_inspection_replays_complete_intent_attempt_and_pure_record_bindings(self):
        reservation = self._reserve()
        completed = self._deliver(reservation)
        complete_path = self._path(REQUEST_A, "complete")
        original = complete_path.read_bytes()
        for mutate in (lambda value: value.update(intent_sha256="0" * 64),
                       lambda value: value["record"].update(id=REQUEST_B),
                       lambda value: value["record"].update(output_sha256="0" * 64),
                       lambda value: value["record"]["rows"].clear(),
                       lambda value: value.update(non_claims=[])):
            with self.subTest(mutate=mutate):
                changed = copy.deepcopy(completed)
                mutate(changed)
                changed["record"]["record_sha256"] = live_tests.own_digest(changed["record"], "record_sha256")
                changed["completion_sha256"] = live_tests.own_digest(changed, "completion_sha256")
                self._write_fixture(complete_path, changed)
                self._refusal(self._inspect, "not-started")
                complete_path.write_bytes(original)
        attempt_path = self._path(REQUEST_A, "attempt")
        attempt = self._disk(REQUEST_A, "attempt")
        attempt["intent_sha256"] = "0" * 64
        attempt["attempt_sha256"] = live_tests.own_digest(attempt, "attempt_sha256")
        self._write_fixture(attempt_path, attempt)
        self._refusal(self._inspect, "not-started")

    def test_missing_attempt_or_intent_never_turns_an_orphan_completion_into_delivery(self):
        reservation = self._reserve()
        self._deliver(reservation)
        for kind in ("attempt", "intent"):
            path = self._path(REQUEST_A, kind)
            held = self.root / (kind + ".retained")
            path.rename(held)
            self._refusal(self._inspect, "not-started")
            self.assertTrue(self._path(REQUEST_A, "complete").exists())
            held.rename(path)

    def test_foreign_epoch_records_refuse_instead_of_silently_filtering(self):
        self._reserve()
        before = self._snapshot()
        self._refusal(lambda: self._inspect(epoch_id="another-controller-epoch"), "not-started")
        self.assertEqual(self._snapshot(), before)

    def test_malformed_or_extra_record_fields_are_retained_and_not_tail_repaired(self):
        self._reserve()
        path = self._path(REQUEST_A, "intent")
        original = path.read_bytes()
        for raw in (b'{"schema":', b'{"schema":"x","schema":"y"}\n',
                    live_tests.canonical({**json.loads(original), "trust": True}) + b"\n"):
            with self.subTest(raw=raw[:40]):
                path.write_bytes(raw)
                self._refusal(self._inspect, "not-started")
                self.assertEqual(path.read_bytes(), raw)
        path.write_bytes(original)

    def test_late_intent_or_completion_replacement_refuses_before_returning_success(self):
        reservation = self._reserve()
        original_publish = self.queue.fixed_atomic_publish

        def changed_after_attempt(path, data, **kwargs):
            result = original_publish(path, data, **kwargs)
            if str(path).endswith(".attempt.json"):
                intent = self._disk(REQUEST_A, "intent")
                intent["consumer"] = "cli.recall"
                self._write_fixture(self._path(REQUEST_A, "intent"), intent)
            return result

        sink = ByteSink()
        with mock.patch.object(self.queue, "fixed_atomic_publish", side_effect=changed_after_attempt):
            self._refusal(lambda: self._deliver(reservation, sink=sink), "not-started")
        self.assertFalse(sink.events)
        self.assertFalse(self._path(REQUEST_A, "complete").exists())
        self._write_fixture(self._path(REQUEST_A, "intent"), reservation["intent"])
        other = self._reserve(request_id=REQUEST_B)

        def changed_after_complete(path, data, **kwargs):
            result = original_publish(path, data, **kwargs)
            if str(path).endswith(".complete.json"):
                value = json.loads(Path(path).read_bytes())
                value["boundary"] = "unobserved"
                self._write_fixture(Path(path), value)
            return result

        sink = ByteSink()
        with mock.patch.object(self.queue, "fixed_atomic_publish", side_effect=changed_after_complete):
            self._refusal(lambda: self._deliver(other, sink=sink), "completed-unrecorded")
        self.assertEqual(bytes(sink.body), self.body)


if __name__ == "__main__":
    unittest.main()
