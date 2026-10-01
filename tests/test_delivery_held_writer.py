"""Contract for one descriptor-held mutable delivery journal.

Existing pure-loop and journal fixtures supply the real ranked plan and
already-declared clocks. The sink actually receives the supplied UTF-8
bytes; it is a controlled local endpoint, not a human or deployed service.
No source completion, v3 adoption, writer permission or legacy touch history
is manufactured here. An outer controller must supply those authorities.

hold_delivery_writer requires directory/epoch_id/limits plus the externally
admitted native directory identity and an explicit authority_current callback.
The callback must return None to keep authority; any other result or exception
refuses. A failed mutable method retires its handle; durable retry reopens it.
The handle owns a single journal lock through read/current/reserve/deliver,
revalidates on normal exit, and becomes unusable on every exit. Its immutable
v1 intent, attempt, completion and inspection schemas stay unchanged.

The callback is checked across effects, not only at context entry. An output
write that returns after authority loss may already have emitted bytes: the
outcome is unknown, with no later flush, clock or completion. Authority loss
after a returned flush is completed-unrecorded. Existing attempt retries may
not emit again. This is primitive construction, not source-writer admission,
machine evidence, JACKAL assurance or a held-out cognitive improvement.
Root alone runs tests sequentially.
"""

import copy
import importlib
import inspect
import os
from pathlib import Path
import sys
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "bin"))

from tests import sia_test_home
from tests import test_delivery_held_inspection as held_tests
from tests import test_delivery_journal as journal_tests
from tests import test_live_loop as live_tests


IDENTITY_KEYS = {"dev", "ino", "mode", "uid", "gid"}
RESERVE_KEYS = {
    "ranked", "expected_ranked_sha256", "emitted_row_refs", "output_utf8",
    "request_id", "consumer",
}
DELIVER_KEYS = {
    "reservation", "expected_reservation_sha256", "binary_sink", "clock",
}


class AuthorityLost(RuntimeError):
    pass


class CallerInterrupted(KeyboardInterrupt):
    pass


class DeliveryPublisherBinding(unittest.TestCase):
    def test_architecture_names_held_writer_without_claiming_source_admission(self):
        architecture = (REPO / "docs" / "ARCHITECTURE.md").read_text()
        self.assertTrue("`siadelivery.hold_delivery_writer`" in architecture,
                        "held writer contract is undocumented")
        self.assertTrue("The held writer is not source-v3 writer authorization" in architecture,
                        "held writer source-authority limitation is missing")
        self.assertFalse("not connected to\nresident recall or source successors" in architecture,
                         "native source-successor binder integration is now implemented")

    def test_publication_joins_the_already_held_directory_before_staging(self):
        fixture = journal_tests.DeliveryJournal(methodName="runTest")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        actual = fixture.queue.fixed_atomic_publish
        observed = DeliveryHeldWriter.observed(fixture.directory)

        def publish(*args, **kwargs):
            descriptor = kwargs.get("destination_dir_fd")
            self.assertIs(type(descriptor), int,
                          "journal publication must bind its held directory")
            info = os.fstat(descriptor)
            self.assertEqual({name: getattr(info, "st_" + name)
                              for name in IDENTITY_KEYS}, observed)
            return actual(*args, **kwargs)

        with mock.patch.object(fixture.queue, "fixed_atomic_publish", side_effect=publish) as written:
            reserved = fixture._reserve()
        self.assertTrue(written.called)
        self.assertEqual(fixture._disk(journal_tests.REQUEST_A, "intent"), reserved["intent"])


class DeliveryHeldWriter(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("siadelivery")
        self.operation = getattr(self.module, "hold_delivery_writer", None)
        self.assertTrue(callable(self.operation),
                        "missing adopted-identity held delivery writer")
        self.journal = journal_tests.DeliveryJournal(methodName="runTest")
        self.addCleanup(self.journal.doCleanups)
        self.journal.setUp()
        self.authority = mock.Mock(return_value=None)
        self.kw = {
            "directory": str(self.journal.directory),
            "epoch_id": live_tests.EPOCH,
            "limits": copy.deepcopy(self.journal.limits),
            "expected_directory_identity": self.observed(self.journal.directory),
            "authority_current": self.authority,
        }
        self.reserve_kw = {key: value for key, value in self.journal.kw.items()
                           if key in RESERVE_KEYS}
        self.caller_fd = os.open(str(self.journal.root),
                                 os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, self.caller_fd)

    @staticmethod
    def observed(path):
        info = os.stat(path, follow_symlinks=False)
        return {name: getattr(info, "st_" + name) for name in IDENTITY_KEYS}

    def fds(self):
        return held_tests.DeliveryHeldInspection._fds(self)

    def hold(self, **changes):
        return self.operation(**{**self.kw, **changes})

    def reserve(self, held, **changes):
        return held.reserve(**{**self.reserve_kw, **changes})

    def deliver(self, held, reservation, *, sink=None, clock=None):
        if sink is None:
            sink = journal_tests.ByteSink()
        if clock is None:
            clock = lambda: live_tests.DELIVERED_AT
        return held.deliver(
            reservation=reservation,
            expected_reservation_sha256=reservation["reservation_sha256"],
            binary_sink=sink, clock=clock)

    def refusal(self, action, state="not-started"):
        return self.journal._refusal(action, state)

    def closed(self, held, reservation=None):
        self.refusal(held.current)
        self.refusal(held.read)
        self.refusal(lambda: self.reserve(held))
        if reservation is not None:
            sink = mock.Mock()
            clock = mock.Mock(side_effect=AssertionError("closed writer sampled clock"))
            self.refusal(lambda: self.deliver(held, reservation, sink=sink, clock=clock))
            sink.write.assert_not_called()
            sink.flush.assert_not_called()
            clock.assert_not_called()

    def test_explicit_context_and_method_contract_without_public_fd(self):
        signature = inspect.signature(self.operation)
        self.assertEqual(set(signature.parameters), set(self.kw))
        for parameter in signature.parameters.values():
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)
        disk, descriptors = self.journal._snapshot(), self.fds()
        with self.hold() as held:
            for name, fields in (("read", set()), ("current", set()),
                                 ("reserve", RESERVE_KEYS), ("deliver", DELIVER_KEYS)):
                method = getattr(held, name, None)
                self.assertTrue(callable(method), name)
                parameters = inspect.signature(method).parameters
                self.assertEqual(set(parameters), fields)
                for parameter in parameters.values():
                    self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
                    self.assertIs(parameter.default, inspect.Parameter.empty)
            for name in ("fd", "directory_fd", "fileno"):
                self.assertFalse(hasattr(held, name), "writer exposes caller-usable descriptor: " + name)
            self.assertEqual(set(held.read()), journal_tests.INSPECTION_KEYS)
            self.assertEqual(held.read()["non_claims"], list(self.module.NON_CLAIMS))
            self.assertIs(held.read()["complete"], True)
            self.assertEqual(held.read()["records"], [])
            self.assertEqual(held.read()["pending"], [])
            held.current()
        self.closed(held)
        self.assertTrue(self.authority.called)
        self.assertEqual(self.journal._snapshot(), disk)
        self.assertEqual(self.fds(), descriptors)

    def test_one_lock_real_write_flush_completion_and_exact_retry(self):
        descriptors = self.fds()
        original = copy.deepcopy(self.reserve_kw)
        clock_calls = []

        def before_write(raw):
            self.assertTrue(raw)
            self.assertTrue(self.journal._path(journal_tests.REQUEST_A, "attempt").exists())
            self.assertFalse(self.journal._path(journal_tests.REQUEST_A, "complete").exists())

        sink = journal_tests.ByteSink(short=True, before_write=before_write)

        def clock():
            self.assertEqual(sink.events[-1], "flush")
            self.assertEqual(bytes(sink.body), self.journal.body)
            clock_calls.append("clock")
            return live_tests.DELIVERED_AT

        with mock.patch.object(self.module, "_Directory", wraps=self.module._Directory) as directory, \
                mock.patch.object(self.module, "reserve_delivery",
                                  side_effect=AssertionError("held writer reacquired reservation lock")) as legacy_reserve, \
                mock.patch.object(self.module, "deliver_reserved",
                                  side_effect=AssertionError("held writer reacquired delivery lock")) as legacy_deliver:
            with self.hold() as held:
                reservation = self.reserve(held)
                self.assertEqual(set(reservation), journal_tests.RESERVATION_KEYS)
                self.assertEqual(self.journal._disk(journal_tests.REQUEST_A, "intent"), reservation["intent"])
                self.assertIs(held.read()["complete"], False)
                self.assertEqual(held.read()["pending"], [journal_tests.REQUEST_A])
                intent_disk = self.journal._snapshot(records_only=True)
                self.assertEqual(self.reserve(held), reservation)
                self.assertEqual(self.journal._snapshot(records_only=True), intent_disk)
                held.current()
                completed = self.deliver(held, reservation, sink=sink, clock=clock)
                self.assertEqual(clock_calls, ["clock"])
                self.assertEqual(bytes(sink.body), self.journal.body)
                self.assertEqual(completed["status"], "service-output-completed")
                self.assertEqual(completed["boundary"], "write-all-and-flush-returned")
                expected = self.journal.fx._delivery(
                    self.journal.live, self.journal.ranked,
                    refs=self.journal.refs, body=self.journal.body,
                    request_id=journal_tests.REQUEST_A)
                self.assertEqual(completed["record"], expected)
                self.assertEqual(self.journal._disk(journal_tests.REQUEST_A, "complete"), completed)
                read = held.read()
                self.assertEqual(read["records"], [completed["record"]])
                self.assertIs(read["complete"], True)
                self.assertEqual(read["pending"], [])
                read["records"].clear()
                self.assertEqual(held.read()["records"], [completed["record"]])
                completed_disk = self.journal._snapshot(records_only=True)
                forbidden_sink = mock.Mock()
                forbidden_clock = mock.Mock(side_effect=AssertionError("completed retry read clock"))
                self.assertEqual(self.deliver(held, reservation,
                    sink=forbidden_sink, clock=forbidden_clock), completed)
                forbidden_sink.write.assert_not_called()
                forbidden_sink.flush.assert_not_called()
                forbidden_clock.assert_not_called()
                self.assertEqual(self.journal._snapshot(records_only=True), completed_disk)
                held.current()
            directory.assert_called_once()
            legacy_reserve.assert_not_called()
            legacy_deliver.assert_not_called()
        self.closed(held, reservation)
        self.assertEqual(self.journal._inspect()["records"], [completed["record"]])
        self.assertEqual(self.reserve_kw, original)
        self.assertEqual(self.fds(), descriptors)

    def test_foreign_identity_or_refusing_authority_cannot_reach_effects(self):
        foreign = self.observed(self.journal.root)
        self.assertNotEqual(foreign, self.kw["expected_directory_identity"])
        unavailable = mock.Mock(side_effect=AuthorityLost("outer epoch unavailable"))
        for changes in ({"expected_directory_identity": foreign},
                        {"authority_current": unavailable},
                        {"authority_current": mock.Mock(return_value=False)},
                        {"authority_current": mock.Mock(return_value=True)},
                        {"authority_current": mock.Mock(return_value="permitted")}):
            with self.subTest(changes=tuple(changes)):
                disk, descriptors = self.journal._snapshot(), self.fds()
                blocked = mock.Mock(side_effect=AssertionError("refused writer caused storage effect"))
                with mock.patch.object(self.module, "_publish", blocked), \
                        mock.patch("os.mkdir", blocked), mock.patch("os.fsync", blocked):
                    with self.assertRaises(self.module.DeliveryJournalRefusal) as caught:
                        with self.hold(**changes):
                            self.fail("writer admitted foreign identity or absent authority")
                self.assertEqual(caught.exception.output_state, "not-started")
                blocked.assert_not_called()
                self.assertEqual(self.journal._snapshot(), disk)
                self.assertEqual(self.fds(), descriptors)
        self.assertTrue(unavailable.called)

    def test_authority_loss_after_entry_refuses_reservation_without_writes(self):
        allowed = [True]

        def current():
            if not allowed[0]:
                raise AuthorityLost("outer epoch changed after entry")

        disk, descriptors = self.journal._snapshot(), self.fds()
        blocked = mock.Mock(side_effect=AssertionError("authority loss published an intent"))
        with mock.patch.object(self.module, "_publish", blocked):
            with self.assertRaises(self.module.DeliveryJournalRefusal) as caught:
                with self.hold(authority_current=current) as held:
                    allowed[0] = False
                    self.reserve(held)
        self.assertEqual(caught.exception.output_state, "not-started")
        blocked.assert_not_called()
        self.closed(held)
        self.assertEqual(self.journal._snapshot(), disk)
        self.assertEqual(self.fds(), descriptors)

    def test_authority_loss_inside_write_keeps_unknown_attempt_and_stops_output(self):
        allowed = [True]

        def current():
            if not allowed[0]:
                raise AuthorityLost("outer epoch changed during write")

        def lose_after_attempt(raw):
            self.assertTrue(raw)
            self.assertTrue(self.journal._path(journal_tests.REQUEST_A, "attempt").exists())
            allowed[0] = False

        descriptors = self.fds()
        sink = journal_tests.ByteSink(short=True, before_write=lose_after_attempt)
        clock = mock.Mock(side_effect=AssertionError("lost output authority sampled clock"))
        with self.assertRaises(self.module.DeliveryJournalRefusal) as caught:
            with self.hold(authority_current=current) as held:
                reservation = self.reserve(held)
                self.deliver(held, reservation, sink=sink, clock=clock)
        self.assertEqual(caught.exception.output_state, "unknown")
        self.assertEqual(sink.events, ["write"])
        self.assertEqual(bytes(sink.body), self.journal.body[:1])
        clock.assert_not_called()
        self.assertTrue(self.journal._path(journal_tests.REQUEST_A, "attempt").exists())
        self.assertFalse(self.journal._path(journal_tests.REQUEST_A, "complete").exists())
        self.closed(held, reservation)
        self.assertEqual(self.fds(), descriptors)

        allowed[0] = True
        disk = self.journal._snapshot(records_only=True)
        retry_sink = mock.Mock()
        with self.assertRaises(self.module.DeliveryJournalRefusal) as retried:
            with self.hold(authority_current=current) as retry:
                self.assertEqual(retry.read()["pending"], [journal_tests.REQUEST_A])
                self.assertIs(retry.read()["complete"], False)
                self.deliver(retry, reservation, sink=retry_sink, clock=clock)
        self.assertEqual(retried.exception.output_state, "unknown")
        self.closed(retry, reservation)
        retry_sink.write.assert_not_called()
        retry_sink.flush.assert_not_called()
        clock.assert_not_called()
        self.assertEqual(self.journal._snapshot(records_only=True), disk)
        self.assertEqual(self.fds(), descriptors)

    def test_authority_loss_after_returned_flush_is_completed_unrecorded(self):
        allowed = [True]

        def current():
            if not allowed[0]:
                raise AuthorityLost("outer epoch changed at returned flush")

        def lose_at_flush():
            allowed[0] = False

        descriptors = self.fds()
        sink = journal_tests.ByteSink(before_flush=lose_at_flush)
        clock = mock.Mock(side_effect=AssertionError("authority loss after flush sampled clock"))
        with self.assertRaises(self.module.DeliveryJournalRefusal) as caught:
            with self.hold(authority_current=current) as held:
                reservation = self.reserve(held)
                self.deliver(held, reservation, sink=sink, clock=clock)
        self.assertEqual(caught.exception.output_state, "completed-unrecorded")
        self.assertEqual(sink.events, ["write", "flush"])
        self.assertEqual(bytes(sink.body), self.journal.body)
        clock.assert_not_called()
        self.assertFalse(self.journal._path(journal_tests.REQUEST_A, "complete").exists())
        self.assertEqual(self.fds(), descriptors)

    def test_unrelated_record_mutation_is_not_readmitted_as_own_progress(self):
        descriptors = self.fds()
        with self.assertRaises(self.module.DeliveryJournalRefusal):
            with self.hold() as held:
                reservation = self.reserve(held)
                held.current()
                path = self.journal._path(journal_tests.REQUEST_A, "intent")
                path.write_bytes(path.read_bytes() + b" ")
                held.current()
        self.closed(held, reservation)
        self.assertFalse(self.journal._path(journal_tests.REQUEST_A, "attempt").exists())
        self.assertFalse(self.journal._path(journal_tests.REQUEST_A, "complete").exists())
        self.assertEqual(self.fds(), descriptors)

    def test_normal_exit_checks_authority_and_exceptional_exit_preserves_caller(self):
        for failure in (None, CallerInterrupted("caller interruption wins")):
            with self.subTest(exceptional=failure is not None):
                allowed = [True]

                def current():
                    if not allowed[0]:
                        raise AuthorityLost("outer epoch lost at exit")

                disk, descriptors = self.journal._snapshot(), self.fds()
                error_type = self.module.DeliveryJournalRefusal if failure is None else CallerInterrupted
                with self.assertRaises(error_type) as caught:
                    with self.hold(authority_current=current) as held:
                        held.current()
                        allowed[0] = False
                        if failure is not None:
                            raise failure
                if failure is not None:
                    self.assertIs(caught.exception, failure)
                else:
                    self.assertEqual(caught.exception.output_state, "not-started")
                self.closed(held)
                self.assertEqual(self.journal._snapshot(), disk)
        self.assertEqual(self.fds(), descriptors)

    def test_failed_mutable_method_retires_handle_before_context_exit(self):
        disk, descriptors = self.journal._snapshot(), self.fds()
        with self.assertRaises(self.module.DeliveryJournalRefusal) as caught:
            with self.hold() as held:
                try:
                    self.reserve(held, output_utf8="not bytes")
                except self.module.DeliveryJournalRefusal:
                    # No second request on a handle whose mutation failed;
                    # the caller must reopen the actual durable journal.
                    self.closed(held)
                    raise
                self.fail("invalid reservation unexpectedly succeeded")
        self.assertEqual(caught.exception.output_state, "not-started")
        self.closed(held)
        self.assertEqual(self.journal._snapshot(), disk)
        self.assertEqual(self.fds(), descriptors)

    def test_legacy_entrypoints_keep_signatures_and_interoperate_with_held_records(self):
        expected = {
            "reserve_delivery": set(self.journal.kw),
            "deliver_reserved": DELIVER_KEYS | {"directory", "limits"},
            "inspect_deliveries": {"directory", "epoch_id", "limits"},
        }
        for name, fields in expected.items():
            parameters = inspect.signature(getattr(self.module, name)).parameters
            self.assertEqual(set(parameters), fields)
            for parameter in parameters.values():
                self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(parameter.default, inspect.Parameter.empty)
        reservation = self.journal._reserve()
        descriptors = self.fds()
        with self.hold() as held:
            self.assertEqual(held.read()["pending"], [journal_tests.REQUEST_A])
            completed = self.deliver(held, reservation)
        self.assertEqual(self.journal._inspect()["records"], [completed["record"]])
        forbidden_sink = mock.Mock()
        forbidden_clock = mock.Mock(side_effect=AssertionError("legacy retry repeated completion clock"))
        self.assertEqual(self.journal._deliver(reservation,
            sink=forbidden_sink, clock=forbidden_clock), completed)
        forbidden_sink.write.assert_not_called()
        forbidden_sink.flush.assert_not_called()
        forbidden_clock.assert_not_called()
        self.assertEqual(self.fds(), descriptors)


if __name__ == "__main__":
    unittest.main()
