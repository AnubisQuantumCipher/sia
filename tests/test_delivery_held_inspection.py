"""RED contract for a descriptor-held, read-only delivery inspection.

Root alone executes this suite. Existing synthetic source/clock fixtures and
the real journal reserve/write/flush path prepare temporary input records.
Direct filesystem substitutions below simulate uncoordinated mutation of
those temporary fixtures; they do not create machine evidence or corpus use.

hold_deliveries has exactly the existing inspection's explicit keyword-only
directory/epoch_id/limits. Its handle.read() returns a detached, unchanged
sia-live-delivery-journal-v1 inspection. handle.current() validates the held
directory, every retained record and the whole entry roster. Both operations
refuse after exit. A normal context exit revalidates; every exit closes only
the descriptors it acquired. The caller's exception remains the exception.

No output, clock, publication, queue ACK, repair, native source acquisition or
new journal provenance is implied. Existing journal and pure-loop boundaries
remain unchanged. There is no new numerical result or arithmetic oracle.
"""

import copy
import errno
import importlib
import inspect
import os
import unittest
from unittest import mock

from tests import test_delivery_journal as journal_tests
from tests import test_live_loop as live_tests


class CallerFailure(RuntimeError):
    pass


class DeliveryHeldInspection(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("siadelivery")
        self.assertTrue(callable(getattr(self.module, "hold_deliveries", None)),
                        "missing descriptor-held delivery inspection")
        self.journal = journal_tests.DeliveryJournal(methodName="runTest")
        self.addCleanup(self.journal.doCleanups)
        self.journal.setUp()
        self.kw = {
            "directory": str(self.journal.directory),
            "epoch_id": live_tests.EPOCH,
            "limits": self.journal.limits,
        }

    def _hold(self, **changes):
        return self.module.hold_deliveries(**{**self.kw, **changes})

    def _complete(self, request_id=journal_tests.REQUEST_A, *, directory=None):
        changes = {"request_id": request_id}
        if directory is not None:
            changes["directory"] = str(directory)
        reservation = self.journal._reserve(**changes)
        delivery_changes = {} if directory is None else {"directory": str(directory)}
        return self.journal._deliver(reservation, **delivery_changes)

    def _refusal(self, action):
        return self.journal._refusal(action, "not-started")

    def _closed(self, handle):
        self._refusal(handle.read)
        self._refusal(handle.current)

    def _fds(self):
        """Read observed descriptor identities; omit the retired scan FD."""
        result = {}
        for leaf in os.listdir("/proc/self/fd"):
            descriptor = int(leaf)
            try:
                info = os.fstat(descriptor)
                target = os.readlink("/proc/self/fd/" + leaf)
            except OSError as exc:
                if exc.errno not in (errno.EBADF, errno.ENOENT):
                    raise
                continue
            result[descriptor] = (info.st_dev, info.st_ino, info.st_mode, target)
        return result

    def _assert_record_descriptors_held(self):
        targets = {item[-1] for item in self._fds().values()}
        self.assertIn(str(self.journal.directory), targets)
        for kind in ("intent", "attempt", "complete"):
            self.assertIn(str(self.journal._path(journal_tests.REQUEST_A, kind)), targets)

    def _late_files(self, directory, kinds):
        """Install prebuilt private fixture leaves outside the journal API."""
        for kind in kinds:
            name = journal_tests.REQUEST_B + "." + kind + ".json"
            target = self.journal.directory / name
            self.assertFalse(target.exists())
            target.write_bytes((directory / name).read_bytes())
            target.chmod(0o600)

    def test_keyword_only_context_handle_contract_and_complete_inspection_parity(self):
        self._complete()
        signature = inspect.signature(self.module.hold_deliveries)
        self.assertEqual(set(signature.parameters), set(self.kw))
        for parameter in signature.parameters.values():
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)
        expected = self.journal._inspect()
        manager = self._hold()
        self.assertTrue(callable(getattr(manager, "__enter__", None)))
        self.assertTrue(callable(getattr(manager, "__exit__", None)))
        with manager as held:
            for name in ("read", "current"):
                self.assertTrue(callable(getattr(held, name, None)))
                self.assertEqual(dict(inspect.signature(getattr(held, name)).parameters), {})
            self.assertEqual(held.read(), expected)
            self.assertEqual(set(held.read()), journal_tests.INSPECTION_KEYS)
            held.current()
            self._assert_record_descriptors_held()
        self._closed(held)

    def test_empty_and_pending_inspections_preserve_exact_existing_boundary(self):
        for prepare in (lambda: None, self.journal._reserve):
            prepare()
            expected = self.journal._inspect()
            disk = self.journal._snapshot()
            with self._hold() as held:
                self.assertEqual(held.read(), expected)
                self.assertEqual(held.read()["non_claims"], list(self.module.NON_CLAIMS))
                held.current()
            self.assertEqual(self.journal._snapshot(), disk)
            self._closed(held)
        self.assertIs(expected["complete"], False)
        self.assertEqual(expected["pending"], [journal_tests.REQUEST_A])
        self.assertEqual(expected["records"], [])

    def test_reads_are_detached_and_unchanged_context_writes_nothing(self):
        self._complete()
        expected = self.journal._inspect()
        before = copy.deepcopy(self.kw)
        disk = self.journal._snapshot()
        descriptors = self._fds()
        with mock.patch("time.time", side_effect=AssertionError("inspection acquired clock")), \
                mock.patch.object(self.module, "reserve_delivery",
                                  side_effect=AssertionError("inspection reserved output")), \
                mock.patch.object(self.module, "deliver_reserved",
                                  side_effect=AssertionError("inspection emitted output")), \
                mock.patch.object(self.module, "_publish",
                                  side_effect=AssertionError("inspection published data")):
            with self._hold() as held:
                first = held.read()
                first["records"][0]["rows"][0]["row"]["chunk_text"] = "caller edit"
                first["non_claims"].clear()
                first["pending"].append(journal_tests.REQUEST_C)
                self.assertEqual(held.read(), expected)
                held.current()
                self._assert_record_descriptors_held()
            self._closed(held)
        self.assertEqual(self.kw, before)
        self.assertEqual(self.journal._snapshot(), disk)
        self.assertEqual(self._fds(), descriptors)

    def test_descriptors_remain_held_across_real_pure_binding_and_caller_copy(self):
        self._complete()
        binder = importlib.import_module("siacontrollerdeliveryinput")
        fx = self.journal.fx
        parent = fx._prepare(self.journal.live)
        disk = self.journal._snapshot()
        with self._hold() as held:
            inspected = held.read()
            self._assert_record_descriptors_held()
            result = binder.bind(
                journal=inspected, expected_journal_sha256=live_tests.digest(inspected),
                previous_state=parent["state"],
                expected_previous_state_sha256=parent["state_sha256"],
                intake=fx.kw["intake"],
                expected_intake_sha256=fx.kw["expected_intake_sha256"],
                policy=fx.policy, expected_policy_sha256=fx.kw["expected_policy_sha256"],
                observed_at=live_tests.DELIVERED_AT)
            detached = copy.deepcopy(result)
            held.current()
            self._assert_record_descriptors_held()
            self.assertEqual(detached["deliveries"]["records"], inspected["records"])
            self.assertEqual(detached["journal_non_claims"], inspected["non_claims"])
        self._closed(held)
        self.assertEqual(self.journal._snapshot(), disk)

    def test_same_path_record_mutation_refuses_current_read_and_normal_exit(self):
        self._complete()
        path = self.journal._path(journal_tests.REQUEST_A, "complete")
        descriptors = self._fds()
        with self.assertRaises(self.module.DeliveryJournalRefusal):
            with self._hold() as held:
                held.read()
                path.write_bytes(path.read_bytes() + b" ")
                self._refusal(held.current)
                self._refusal(held.read)
        self._closed(held)
        self.assertEqual(self._fds(), descriptors)

    def test_same_bytes_new_record_inode_is_not_the_held_record(self):
        self._complete()
        path = self.journal._path(journal_tests.REQUEST_A, "intent")
        raw = path.read_bytes()
        displaced = self.journal.root / "displaced-intent.json"
        with self.assertRaises(self.module.DeliveryJournalRefusal):
            with self._hold() as held:
                path.rename(displaced)
                path.write_bytes(raw)
                path.chmod(0o600)
                self._refusal(held.current)
                self._refusal(held.read)
        self._closed(held)

    def test_directory_name_swap_never_rebinds_to_new_empty_journal(self):
        self._complete()
        displaced = self.journal.root / "displaced-journal"
        with self.assertRaises(self.module.DeliveryJournalRefusal):
            with self._hold() as held:
                self.journal.directory.rename(displaced)
                self.journal.directory.mkdir(mode=0o700)
                self._refusal(held.current)
                self._refusal(held.read)
        self._closed(held)

    def test_symlink_substitution_does_not_restore_name_authority(self):
        self._complete()
        displaced = self.journal.root / "displaced-journal"
        with self.assertRaises(self.module.DeliveryJournalRefusal):
            with self._hold() as held:
                self.journal.directory.rename(displaced)
                self.journal.directory.symlink_to(displaced, target_is_directory=True)
                self._refusal(held.current)
                self._refusal(held.read)
        self._closed(held)

    def test_late_private_intent_changes_whole_roster_not_just_returned_completions(self):
        self._complete()
        staged = self.journal._directory("late-journal")
        self.journal._reserve(request_id=journal_tests.REQUEST_B, directory=str(staged))
        with self.assertRaises(self.module.DeliveryJournalRefusal):
            with self._hold() as held:
                self.assertIs(held.read()["complete"], True)
                self._late_files(staged, ("intent",))
                self._refusal(held.current)
                self._refusal(held.read)
        self._closed(held)

    def test_late_complete_record_changes_whole_roster(self):
        self._complete()
        staged = self.journal._directory("late-journal")
        self._complete(journal_tests.REQUEST_B, directory=staged)
        with self.assertRaises(self.module.DeliveryJournalRefusal):
            with self._hold() as held:
                self._late_files(staged, ("intent", "attempt", "complete"))
                self._refusal(held.current)
                self._refusal(held.read)
        self._closed(held)

    def test_deleted_held_record_refuses_without_repair(self):
        self._complete()
        path = self.journal._path(journal_tests.REQUEST_A, "attempt")
        with self.assertRaises(self.module.DeliveryJournalRefusal):
            with self._hold() as held:
                path.unlink()
                self._refusal(held.current)
                self._refusal(held.read)
        self.assertFalse(path.exists())
        self._closed(held)

    def test_normal_exit_revalidates_even_if_caller_never_requests_current(self):
        self._complete()
        path = self.journal._path(journal_tests.REQUEST_A, "complete")
        with self.assertRaises(self.module.DeliveryJournalRefusal):
            with self._hold() as held:
                held.read()
                path.write_bytes(path.read_bytes() + b" ")
        self._closed(held)

    def test_exceptional_exit_preserves_caller_exception_and_closes_own_descriptors(self):
        self._complete()
        sentinel_path = self.journal.root / "caller-owned-sentinel"
        sentinel_path.write_bytes(b"caller-owned fixture\n")
        with sentinel_path.open("rb") as sentinel:
            sentinel_identity = os.fstat(sentinel.fileno())
            descriptors = self._fds()
            failure = CallerFailure("synthetic caller failure")
            with self.assertRaises(CallerFailure) as caught:
                with self._hold() as held:
                    self._assert_record_descriptors_held()
                    path = self.journal._path(journal_tests.REQUEST_A, "intent")
                    path.write_bytes(path.read_bytes() + b" ")
                    raise failure
            self.assertIs(caught.exception, failure)
            self.assertEqual(os.fstat(sentinel.fileno()), sentinel_identity)
            self.assertEqual(self._fds(), descriptors)
            self._closed(held)

    def test_failed_entry_does_not_leak_descriptors_or_create_missing_directory(self):
        self._complete()
        descriptors = self._fds()
        for changes in ({"epoch_id": "foreign-epoch"},
                        {"directory": str(self.journal.root / "missing-journal")}):
            with self.subTest(changes=changes):
                with self.assertRaises(self.module.DeliveryJournalRefusal):
                    with self._hold(**changes):
                        self.fail("invalid held inspection entered")
                self.assertEqual(self._fds(), descriptors)
        self.assertFalse((self.journal.root / "missing-journal").exists())


if __name__ == "__main__":
    unittest.main()
