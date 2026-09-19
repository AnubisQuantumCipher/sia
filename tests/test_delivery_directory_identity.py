"""Contract for the directory actually held by journal inspection.

Reuse the real temporary journal fixture by
module-qualified composition, not TestCase inheritance or imported TestCase
aliases that duplicate discovery. Stat values below are observed native
integers, not derived metrics. Filesystem substitutions affect only fixture
directories and simulate uncoordinated mutation; they do not create evidence.

directory_identity() adds a detached {dev, ino, mode, uid, gid} observation to
the held handle. It is not an adoption receipt, does not authorize a writer,
and does not change read()'s existing journal-v1 bytes or public arguments.
"""

import copy
import inspect
import os
import unittest
from unittest import mock

from tests import test_delivery_held_inspection as held_tests
from tests import test_delivery_journal as journal_tests
from tests import test_live_loop as live_tests


IDENTITY_KEYS = {"dev", "ino", "mode", "uid", "gid"}


class DeliveryHeldDirectoryIdentity(unittest.TestCase):
    def setUp(self):
        self.fixture = held_tests.DeliveryHeldInspection(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.module = self.fixture.module
        self.journal = self.fixture.journal

    def _api(self, held):
        method = getattr(held, "directory_identity", None)
        self.assertTrue(callable(method), "missing held directory_identity()")
        self.assertEqual(dict(inspect.signature(method).parameters), {})
        return method

    def _observed(self):
        info = os.stat(self.journal.directory, follow_symlinks=False)
        return {name: getattr(info, "st_" + name) for name in IDENTITY_KEYS}

    def _closed(self, held, method):
        self.fixture._refusal(method)
        self.fixture._closed(held)

    def test_exact_observed_identity_and_unchanged_journal_read_contract(self):
        self.fixture._complete()
        expected = self._observed()
        journal = self.journal._inspect()
        journal_raw = live_tests.canonical(journal)
        disk = self.journal._snapshot()
        descriptors = self.fixture._fds()
        public = inspect.signature(self.module.hold_deliveries)
        self.assertEqual(set(public.parameters), set(self.fixture.kw))
        for parameter in public.parameters.values():
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)
        with self.fixture._hold() as held:
            method = self._api(held)
            result = method()
            self.assertIs(type(result), dict)
            self.assertEqual(set(result), IDENTITY_KEYS)
            self.assertEqual(result, expected)
            for value in result.values():
                self.assertIs(type(value), int)
            self.assertEqual(live_tests.canonical(held.read()), journal_raw)
            self.assertEqual(set(held.read()), journal_tests.INSPECTION_KEYS)
            self.assertEqual(held.read()["schema"], "sia-live-delivery-journal-v1")
            self.assertEqual(held.read()["non_claims"], list(self.module.NON_CLAIMS))
            self.fixture._assert_record_descriptors_held()
        self._closed(held, method)
        self.assertEqual(self.journal._snapshot(), disk)
        self.assertEqual(self.fixture._fds(), descriptors)

    def test_empty_and_pending_journals_expose_identity_without_claiming_complete(self):
        for prepare in (lambda: None, self.journal._reserve):
            prepare()
            expected = self._observed()
            inspected = self.journal._inspect()
            disk = self.journal._snapshot()
            with self.fixture._hold() as held:
                method = self._api(held)
                self.assertEqual(method(), expected)
                self.assertEqual(live_tests.canonical(held.read()),
                                 live_tests.canonical(inspected))
            self._closed(held, method)
            self.assertEqual(self.journal._snapshot(), disk)
        self.assertIs(inspected["complete"], False)
        self.assertEqual(inspected["pending"], [journal_tests.REQUEST_A])
        self.assertEqual(inspected["records"], [])

    def test_returned_mapping_is_detached_and_identity_reads_have_no_effects(self):
        self.fixture._complete()
        expected = self._observed()
        original_arguments = copy.deepcopy(self.fixture.kw)
        disk = self.journal._snapshot()
        with mock.patch("time.time", side_effect=AssertionError("identity sampled clock")), \
                mock.patch.object(self.module, "reserve_delivery",
                                  side_effect=AssertionError("identity reserved output")), \
                mock.patch.object(self.module, "deliver_reserved",
                                  side_effect=AssertionError("identity emitted output")), \
                mock.patch.object(self.module, "_publish",
                                  side_effect=AssertionError("identity published data")):
            with self.fixture._hold() as held:
                method = self._api(held)
                first = method()
                first.clear()
                first.update({name: "caller mutation" for name in IDENTITY_KEYS})
                first["schema"] = "not-an-adoption"
                self.assertEqual(method(), expected)
                self.fixture._assert_record_descriptors_held()
            self._closed(held, method)
        self.assertEqual(self.fixture.kw, original_arguments)
        self.assertEqual(self.journal._snapshot(), disk)

    def test_successful_identity_read_calls_full_current_before_and_after(self):
        self.fixture._complete()
        expected = self._observed()
        with self.fixture._hold() as held:
            method = self._api(held)
            with mock.patch.object(held, "current", wraps=held.current) as checked:
                self.assertEqual(method(), expected)
                self.assertGreaterEqual(checked.call_count, 2,
                                        "identity must bracket its result with full checks")

    def test_record_change_after_first_current_cannot_escape_final_check(self):
        self.fixture._complete()
        path = self.journal._path(journal_tests.REQUEST_A, "complete")
        changed = []
        with self.assertRaises(self.module.DeliveryJournalRefusal):
            with self.fixture._hold() as held:
                method = self._api(held)
                original_current = held.current

                def checked_then_change():
                    original_current()
                    if not changed:
                        path.write_bytes(path.read_bytes() + b" ")
                        changed.append(True)

                with mock.patch.object(held, "current", side_effect=checked_then_change):
                    self.fixture._refusal(method)
                self.assertTrue(changed, "control must mutate after the first full check")
                self.fixture._refusal(method)
        self._closed(held, method)

    def test_same_bytes_replaced_record_inode_refuses_identity(self):
        self.fixture._complete()
        path = self.journal._path(journal_tests.REQUEST_A, "intent")
        raw = path.read_bytes()
        displaced = self.journal.root / "displaced-intent.json"
        with self.assertRaises(self.module.DeliveryJournalRefusal):
            with self.fixture._hold() as held:
                method = self._api(held)
                method()
                path.rename(displaced)
                path.write_bytes(raw)
                path.chmod(0o600)
                self.fixture._refusal(method)
        self._closed(held, method)

    def test_directory_name_swap_cannot_report_new_empty_directory_identity(self):
        self.fixture._complete()
        displaced = self.journal.root / "displaced-journal"
        with self.assertRaises(self.module.DeliveryJournalRefusal):
            with self.fixture._hold() as held:
                method = self._api(held)
                previous = method()
                self.journal.directory.rename(displaced)
                self.journal.directory.mkdir(mode=0o700)
                self.assertNotEqual(self._observed(), previous)
                self.fixture._refusal(method)
        self._closed(held, method)

    def test_symlink_substitution_cannot_restore_original_directory_identity(self):
        self.fixture._complete()
        displaced = self.journal.root / "displaced-journal"
        with self.assertRaises(self.module.DeliveryJournalRefusal):
            with self.fixture._hold() as held:
                method = self._api(held)
                method()
                self.journal.directory.rename(displaced)
                self.journal.directory.symlink_to(displaced, target_is_directory=True)
                self.fixture._refusal(method)
        self._closed(held, method)

    def test_directory_mode_drift_refuses_instead_of_reporting_new_permissions(self):
        self.fixture._complete()
        with self.assertRaises(self.module.DeliveryJournalRefusal):
            with self.fixture._hold() as held:
                method = self._api(held)
                method()
                self.journal.directory.chmod(0o750)
                self.fixture._refusal(method)
        self._closed(held, method)

    def test_late_pending_intent_is_whole_roster_drift_even_when_identity_is_stable(self):
        self.fixture._complete()
        staged = self.journal._directory("late-journal")
        self.journal._reserve(request_id=journal_tests.REQUEST_B, directory=str(staged))
        with self.assertRaises(self.module.DeliveryJournalRefusal):
            with self.fixture._hold() as held:
                method = self._api(held)
                before = method()
                self.fixture._late_files(staged, ("intent",))
                self.assertEqual(self._observed(), before)
                self.fixture._refusal(method)
        self._closed(held, method)

    def test_exceptional_context_exit_preserves_caller_error_and_retires_identity_api(self):
        self.fixture._complete()
        descriptors = self.fixture._fds()
        failure = held_tests.CallerFailure("synthetic caller failure")
        with self.assertRaises(held_tests.CallerFailure) as raised:
            with self.fixture._hold() as held:
                method = self._api(held)
                method()
                raise failure
        self.assertIs(raised.exception, failure)
        self._closed(held, method)
        self.assertEqual(self.fixture._fds(), descriptors)


if __name__ == "__main__":
    unittest.main()
