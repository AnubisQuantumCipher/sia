"""Experimental mutation-view tests in disposable corpora, not activation."""

import json
import importlib
import os
import errno
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

from tests import test_event_page_plan as pages
from tests import test_event_pack_consumers as consumers
from tests import test_event_pack_reader as lookup


SOURCE = Path(__file__).resolve().parents[1] / "bin/siaeventindexdelta.py"
delta = ModuleType("siaeventindexdelta")
with mock.patch.dict("sys.modules", {"siaeventpackreader": lookup.reader}):
    exec(compile(SOURCE.read_bytes(), str(SOURCE), "exec"), delta.__dict__)


class IndexDelta(unittest.TestCase):
    def setUp(self):
        self.fixture = consumers.PublicationReadback(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.lookup = self.fixture.fixture
        self.lookup._alternate_roster(3)
        rows = lookup.siaeventpack.decode(
            self.lookup.pack.read_bytes(), "org", self.lookup.event_id[:3])
        self.lookup.pack.write_bytes(lookup.siaeventpack.encode(
            "org", self.lookup.event_id[:3], rows[:1]))
        self.records = tuple((key.decode(), raw) for key, raw in rows)
        self.pack_bytes = self.lookup.pack.read_bytes()
        self.targets = tuple(Path(self.lib.CORPUS) /
                             self.lib._event_index_relative("org", key)
                             for key, _raw in self.records[1:])

    def publish(self, records=None):
        with self.lib.corpus_owner():
            return delta.publish_legacy_fallbacks(
                self.lib.__dict__, organ="org",
                records=self.records if records is None else records)

    def assert_targets_absent(self):
        self.assertTrue(all(not path.exists() for path in self.targets))
        self.assertEqual(self.lookup.pack.read_bytes(), self.pack_bytes)

    def test_mixed_pack_and_novel_fallback_publication_and_retry(self):
        expected = tuple(path.relative_to(self.lib.CORPUS).as_posix() for path in self.targets)
        self.assertEqual(self.publish(), expected)
        self.assertEqual(tuple(path.read_bytes() for path in self.targets),
                         tuple(raw for _key, raw in self.records[1:]))
        with mock.patch.object(self.lib, "_before_corpus_mutation",
                               side_effect=AssertionError("duplicate retry wrote")):
            self.assertEqual(self.publish(), ())
        self.assertEqual(self.lookup.pack.read_bytes(), self.pack_bytes)
        packed_legacy = Path(self.lib.CORPUS) / self.lib._event_index_relative(
            "org", self.records[0][0])
        self.assertFalse(packed_legacy.exists())

    def test_later_conflict_precedes_every_write(self):
        key, raw = self.records[-1]
        wrong = self.lib._event_index_encoded(dict(json.loads(raw), payload_sha256="f" * 64))
        self.targets[-1].write_bytes(wrong)
        with mock.patch.object(self.lib, "_before_corpus_mutation",
                               side_effect=AssertionError("late conflict reached write")):
            with self.assertRaisesRegex(ValueError, "conflicts with durable"):
                self.publish()
        self.assertFalse(self.targets[0].exists())
        self.assertEqual(self.targets[-1].read_bytes(), wrong)

    def test_later_malformed_input_precedes_every_write(self):
        changed = self.records[:-1] + ((self.records[-1][0], b"malformed"),)
        with self.assertRaisesRegex(ValueError, "malformed"):
            self.publish(changed)
        self.assert_targets_absent()

    def test_missing_lease_and_invalid_input_refuse_before_capture(self):
        with mock.patch.object(delta.plan, "_Capture", side_effect=AssertionError("opened capture")):
            with self.assertRaisesRegex(ValueError, "requires the corpus lease"):
                delta.publish_legacy_fallbacks(self.lib.__dict__, organ="org", records=self.records)
            for records in (list(self.records), self.records[::-1], (self.records[0],) * 2,
                            ((self.records[0][0], bytearray(b"bad")),)):
                with self.subTest(records=type(records)), self.assertRaises(ValueError):
                    self.publish(records)
        self.assert_targets_absent()

    def test_policy_change_from_mutation_guard_refuses_before_write(self):
        def changed():
            self.lib.MAX_EVENT_INDEX_BYTES = True
        with mock.patch.object(self.lib, "MAX_EVENT_INDEX_BYTES", self.lib.MAX_EVENT_INDEX_BYTES), \
                mock.patch.object(self.lib, "_before_corpus_mutation", changed):
            with self.assertRaisesRegex(ValueError, "policy is invalid"):
                self.publish()
        self.assert_targets_absent()

    def test_pack_change_from_guard_refuses_before_write(self):
        def changed():
            self.lookup.pack.write_bytes(b"malformed")
        with mock.patch.object(self.lib, "_before_corpus_mutation", changed):
            with self.assertRaises(ValueError):
                self.publish()
        self.assertTrue(all(not path.exists() for path in self.targets))
        self.assertEqual(self.lookup.pack.read_bytes(), b"malformed")

    def test_unrelated_directory_member_change_is_not_an_allowed_delta(self):
        foreign = self.targets[0].parent / "foreign.json"
        original = self.lib.ensure_durable_directory

        def changed(path):
            original(path)
            foreign.write_bytes(b"foreign")

        with mock.patch.object(self.lib, "ensure_durable_directory", changed):
            with self.assertRaisesRegex(ValueError, "complete-directory-roster"):
                self.publish()
        self.assert_targets_absent()
        self.assertEqual(foreign.read_bytes(), b"foreign")

    def test_incorrect_atomic_write_is_observed_and_refused(self):
        def wrong(path, text):
            Path(path).write_text(text + " ")
        with mock.patch.object(self.lib, "atomic_write", wrong):
            with self.assertRaisesRegex(ValueError, "original-source-binding"):
                self.publish()
        self.assertEqual(self.targets[0].read_bytes(), self.records[1][1] + b" ")
        self.assertFalse(self.targets[1].exists())

    def test_cut_after_write_preserves_known_effect_and_exact_retry(self):
        original = self.lib.atomic_write

        def cut(path, text):
            original(path, text)
            raise OSError("injected after write")

        with mock.patch.object(self.lib, "atomic_write", cut):
            with self.assertRaisesRegex(OSError, "injected after write"):
                self.publish()
        self.assertEqual(self.targets[0].read_bytes(), self.records[1][1])
        self.assertFalse(self.targets[1].exists())
        self.assertEqual(self.publish(), (self.targets[1].relative_to(self.lib.CORPUS).as_posix(),))
        self.assertEqual(self.publish(), ())

    def test_shared_budget_survives_all_refreshes(self):
        observed = []
        original = delta.plan._observe_closure

        def observe(*args, **kwargs):
            budget = kwargs["budget"]
            observed.append(budget)
            return original(*args, **kwargs)

        with mock.patch.object(delta.plan, "_observe_closure", observe):
            self.publish()
        self.assertEqual(len(observed), 4)
        self.assertTrue(all(item is observed[0] for item in observed))

    def test_default_observer_policy_still_refuses_directory_entry_delta(self):
        original = delta.plan._observe_closure

        def strict(*args, **kwargs):
            kwargs.pop("allow_directory_entry_deltas")
            return original(*args, **kwargs)

        with mock.patch.object(delta.plan, "_observe_closure", strict):
            with self.assertRaisesRegex(ValueError, "complete-directory-roster"):
                self.publish()
        self.assertEqual(self.targets[0].read_bytes(), self.records[1][1])
        self.assertFalse(self.targets[1].exists())

    def test_unscanned_child_cannot_be_exempted_from_parent_comparison(self):
        original = delta.plan._observe_closure

        def incomplete(owner, deps, images, *args, **kwargs):
            child = self.targets[0].parent.relative_to(self.lib.CORPUS).as_posix()
            changed = json.loads(json.dumps(deps))
            for row in changed["directories"]:
                if row["relative"] == child:
                    row["before"]["entries"] = None
            return original(owner, changed, images, *args, **kwargs)

        with mock.patch.object(delta.plan, "_observe_closure", incomplete):
            with self.assertRaisesRegex(ValueError, "directory-delta-closure"):
                self.publish()
        self.assert_targets_absent()

    def test_late_policy_change_in_final_capture_is_refused_after_known_writes(self):
        finished = False
        write, current = delta._write, delta.plan._Capture.current

        def mark(*args, **kwargs):
            nonlocal finished
            write(*args, **kwargs)
            if args[2] == self.records[-1]:
                finished = True

        def changed(capture, **kwargs):
            current(capture, **kwargs)
            if finished:
                self.lib.MAX_STATE_JSON_BYTES = True

        with mock.patch.object(self.lib, "MAX_STATE_JSON_BYTES", self.lib.MAX_STATE_JSON_BYTES), \
                mock.patch.object(delta, "_write", mark), \
                mock.patch.object(delta.plan._Capture, "current", changed):
            with self.assertRaisesRegex(ValueError, "policy is invalid"):
                self.publish()
        self.assertEqual(tuple(path.read_bytes() for path in self.targets),
                         tuple(raw for _key, raw in self.records[1:]))

    def test_all_capture_root_descriptors_close_after_success(self):
        descriptors = []
        original = delta.plan._Capture

        def capture(*args, **kwargs):
            result = original(*args, **kwargs)
            descriptors.append(result.root_fd)
            return result

        with mock.patch.object(delta.plan, "_Capture", capture):
            self.publish()
        self.assertEqual(len(descriptors), 5)
        for descriptor in descriptors:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_full_pack_keeps_exact_unrepresented_legacy_fallback(self):
        self.lookup._alternate_roster(64)
        pack = self.lookup.pack.read_bytes()
        rows = lookup.siaeventpack.decode(pack, "org", self.lookup.event_id[:3])
        records = tuple(sorted(((key.decode(), raw) for key, raw in rows)))
        records = tuple(sorted(records + ((self.lookup.event_id, self.lookup.raw),)))
        self.lookup.legacy.unlink()
        expected = self.lookup.legacy.relative_to(self.lib.CORPUS).as_posix()
        self.assertEqual(self.publish(records), (expected,))
        self.assertEqual(self.lookup.legacy.read_bytes(), self.lookup.raw)
        self.assertEqual(self.lookup.pack.read_bytes(), pack)
        self.assertEqual(self.publish(records), ())

    def test_nonboolean_directory_delta_policy_refuses_before_capture(self):
        with mock.patch.object(delta.plan, "_Capture", side_effect=AssertionError("opened capture")):
            for value in (1, "yes", None):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "directory-delta-policy"):
                    delta.plan._observe_closure({}, {}, {}, allow_directory_entry_deltas=value)

    def test_budget_exhaustion_after_write_keeps_effect_and_refuses_remainder(self):
        original = delta._refresh

        def exhausted(*args, **kwargs):
            original(*args, **kwargs)
            if kwargs["files"]:
                budget = args[5]
                budget.reserve("injected-after-write", budget.limit)

        with mock.patch.object(delta, "_refresh", exhausted):
            with self.assertRaisesRegex(ValueError, "complete-byte-capacity"):
                self.publish()
        self.assertEqual(self.targets[0].read_bytes(), self.records[1][1])
        self.assertFalse(self.targets[1].exists())
        self.assertEqual(self.publish(), (self.targets[1].relative_to(self.lib.CORPUS).as_posix(),))

    def _assert_handoff_close_error(self, operation, module=None):
        module = delta.plan if module is None else module
        captures = []
        create, close = module._Capture, module._Capture.close
        os_close = os.close
        injected = False
        held = set()

        def capture(*args, **kwargs):
            result = create(*args, **kwargs)
            captures.append(result)
            return result

        def failed_close(descriptor):
            nonlocal injected
            os_close(descriptor)
            if not injected:
                injected = True
                raise OSError(errno.EIO, "injected close after descriptor release")

        def closing(item):
            held.update(entry["fd"] for table in (item.files, item.directories)
                        for entry in table.values() if entry is not None and entry["fd"] is not None)
            if item.root_fd is not None:
                held.add(item.root_fd)
            if item is captures[0] and not injected:
                shim = SimpleNamespace(**(vars(module.os) | {"close": failed_close}))
                with mock.patch.object(module, "os", shim):
                    return close(item)
            return close(item)

        with mock.patch.object(create, "close", closing), \
                mock.patch.object(module, "_Capture", capture):
            with self.assertRaises(OSError):
                operation()
        self.assertTrue(injected)
        live = []
        for item in captures:
            descriptors = [item.root_fd] + [entry["fd"] for table in (item.files, item.directories)
                                            for entry in table.values() if entry is not None]
            held.update(descriptor for descriptor in descriptors if descriptor is not None)
        for descriptor in held:
            try:
                os.fstat(descriptor)
            except OSError as exc:
                self.assertEqual(exc.errno, errno.EBADF)
            else:
                live.append(descriptor)
        # Retain the failure, but do not leak this negative fixture's descriptors.
        for descriptor in set(live):
            os_close(descriptor)
        self.assertEqual(live, [])

    def test_handoff_close_error_cleans_every_registered_capture(self):
        self._assert_handoff_close_error(self.publish)

    def test_original_page_publication_handoff_closes_every_capture(self):
        fixture = pages.EventPageRenderPlan(methodName="runTest")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        prepared = fixture.prepare([fixture.event()])
        self._assert_handoff_close_error(
            lambda: fixture.publish(prepared), importlib.import_module("siaeventplan"))
        self.assertFalse(Path(fixture.lib.corpus_path(fixture.slug)).exists())

    def test_close_attempts_all_owned_descriptors_once_despite_multiple_errors(self):
        capture = delta.plan._Capture(self.lib.__dict__, delta.plan._Budget(self.lib.__dict__, 4096))
        capture.read_file(str(self.lookup.legacy), self.lib.MAX_EVENT_INDEX_BYTES)
        descriptors = [entry["fd"] for table in (capture.files, capture.directories)
                       for entry in table.values() if entry is not None] + [capture.root_fd]
        attempted = []
        original = os.close

        def close(descriptor):
            attempted.append(descriptor)
            original(descriptor)
            if descriptor in descriptors[:2]:
                raise OSError(errno.EIO, "injected descriptor close error")

        shim = SimpleNamespace(**(vars(os) | {"close": close}))
        with mock.patch.object(delta.plan, "os", shim):
            with self.assertRaises(OSError) as raised:
                capture.close()
        self.assertEqual(attempted, descriptors)
        self.assertIn("capture cleanup reported 2 descriptor close errors", raised.exception.__notes__)
        shim.close = mock.Mock(side_effect=AssertionError("descriptor retried"))
        with mock.patch.object(delta.plan, "os", shim):
            capture.close()
        for descriptor in descriptors:
            with self.assertRaises(OSError) as gone:
                os.fstat(descriptor)
            self.assertEqual(gone.exception.errno, errno.EBADF)

    def test_primary_and_both_cleanup_errors_remain_visible(self):
        first, second = OSError("first cleanup"), OSError("second cleanup")
        captures = tuple(SimpleNamespace(close=mock.Mock(side_effect=error)) for error in (first, second))
        primary = ValueError("original refusal")
        try:
            raise primary
        except ValueError:
            with self.assertRaises(ExceptionGroup) as raised:
                delta.plan._close_known(captures)
        self.assertEqual(raised.exception.exceptions, (primary, first, second))
        for capture in captures:
            capture.close.assert_called_once_with()

    def test_shared_observer_preserves_primary_when_cleanup_also_fails(self):
        close = delta.plan._Capture.close
        cleanup = OSError("injected cleanup after close")

        def failed(capture):
            close(capture)
            raise cleanup

        with mock.patch.object(delta.plan._Capture, "close", failed):
            with self.assertRaises(ExceptionGroup) as raised:
                delta.plan._observe_closure(self.lib.__dict__, {"corpus_identity": {}}, {})
        primary, observed = raised.exception.exceptions
        self.assertIsInstance(primary, ValueError)
        self.assertIn("corpus-identity", str(primary))
        self.assertIs(observed, cleanup)

    def _remove_legacy_tree(self):
        self.lookup.legacy.unlink()
        parent = self.lookup.legacy.parent
        for _level in range(3):
            parent.rmdir()
            parent = parent.parent

    def test_absent_index_ancestor_chain_is_created_and_reconciled(self):
        self._remove_legacy_tree()
        self.publish()
        self.assertEqual(tuple(path.read_bytes() for path in self.targets),
                         tuple(raw for _key, raw in self.records[1:]))
        self.assertEqual(self.publish(), ())

    def test_foreign_member_in_new_ancestor_chain_refuses_before_leaf_write(self):
        self._remove_legacy_tree()
        original = self.lib.ensure_durable_directory
        foreign = Path(self.lib.CORPUS) / "event-index" / "foreign"

        def changed(path):
            original(path)
            foreign.write_bytes(b"unexpected")

        with mock.patch.object(self.lib, "ensure_durable_directory", changed):
            with self.assertRaisesRegex(ValueError, "foreign-created-directory-member"):
                self.publish()
        self.assert_targets_absent()
        self.assertEqual(foreign.read_bytes(), b"unexpected")

    def test_close_error_does_not_retry_a_reused_descriptor_number(self):
        capture = delta.plan._Capture(self.lib.__dict__, delta.plan._Budget(self.lib.__dict__, 4096))
        original = os.close
        replacement = []

        def close(descriptor):
            original(descriptor)
            opened = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
            if opened != descriptor:
                os.dup2(opened, descriptor, inheritable=False)
                original(opened)
            replacement.append(descriptor)
            raise OSError(errno.EIO, "reported after descriptor reuse")

        try:
            shim = SimpleNamespace(**(vars(os) | {"close": close}))
            with mock.patch.object(delta.plan, "os", shim):
                with self.assertRaises(OSError):
                    capture.close()
            capture.close()
            os.fstat(replacement[0])
        finally:
            for descriptor in replacement:
                original(descriptor)


if __name__ == "__main__":
    unittest.main()
