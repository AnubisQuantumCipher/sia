"""Contract for an existing, descriptor-held epoch view.

The module-qualified adoption fixture supplies actual acknowledged legacy
source authority in temporary
storage. Positive cases run prepare_epoch first to settle adoption durability;
a held read never substitutes for that recovery or enables a writer.

The caller acquires its ordinary corpus lease before no-effects observation.
hold_epoch may nest that lease, but must not request the resident brainstem
lease or create, flush, publish or repair epoch, memo or journal storage.
Temporary path substitutions below are caller-induced drift, not source truth.

The full generation, paths and identity fields are observed fixture values.
No machine-history acquisition, live corpus use, numeric oracle, source-v3
success, output receipt, cognitive claim or held-out improvement is fabricated.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import contextlib
import copy
import errno
import inspect
import os
from pathlib import Path
import re
import unittest
from unittest import mock

from tests import test_controller_delivery_epoch as epoch_tests
from tests import test_live_loop as live_tests


VIEW_KEYS = {
    "schema", "status", "epoch_adoption", "parent_committed",
    "parent_generation", "expected_parent_generation_sha256",
    "records_directory", "records_identity", "non_claims",
}


class CallerFailure(RuntimeError):
    pass


class ControllerDeliveryEpochHold(unittest.TestCase):
    def setUp(self):
        # Do not subclass/import the fixture TestCase into this module's test
        # namespace: the parent suite must not be discovered a second time.
        self.epoch = epoch_tests.ControllerDeliveryEpoch(methodName="runTest")
        self.addCleanup(self.epoch.doCleanups)
        self.epoch.setUp()
        self.module = self.epoch.module
        self.assertTrue(callable(getattr(self.module, "hold_epoch", None)),
                        "missing corpus-owned held delivery epoch")
        self.assertTrue(hasattr(self.module, "HELD_NON_CLAIMS"),
                        "held epoch needs its own readable nonclaims")

    @contextlib.contextmanager
    def prepared(self):
        with self.epoch.completed() as fixture:
            case, retained, committed, status, _generation, _root = fixture
            adopted = self.epoch.prepare(case, retained, committed, status)
            yield (*fixture, adopted)

    def request(self, case, retained, committed, status, adopted):
        return {
            "memo": case.live.memo, "admitted_status": status,
            "retained_batch": retained, "committed": committed,
            "journal_limits": self.epoch.limits,
            "expected_journal_limits_sha256": live_tests.digest(self.epoch.limits),
            "expected_adoption_sha256": adopted["expected_adoption_sha256"],
        }

    def expected(self, retained, committed, generation, root, adopted):
        _key, _directory, _birth, _adoption, records = self.epoch.paths(retained, root)
        return copy.deepcopy({
            "schema": "sia-controller-delivery-epoch-view-v1",
            "status": "held-not-consumed", "epoch_adoption": adopted,
            "parent_committed": committed, "parent_generation": generation,
            "expected_parent_generation_sha256": committed["live_generation_sha256"],
            "records_directory": str(records),
            "records_identity": adopted["adoption"]["records_identity"],
            "non_claims": list(self.module.HELD_NON_CLAIMS),
        })

    @contextlib.contextmanager
    def reader_scope(self, case):
        with self.epoch.idle.source_owner(case), case.lib.corpus_owner():
            # These spies begin after ordinary owner infrastructure is open.
            with contextlib.ExitStack() as stack:
                stack.enter_context(self.epoch.no_new_work(case))
                blocked = []
                for owner, name in (
                        (case.lib, "brainstem_owner"),
                        (case.lib, "_write_memo"),
                        (case.lib, "atomic_write"),
                        (case.lib, "ensure_durable_directory"),
                        (self.module, "prepare_epoch"),
                        (self.epoch.queue, "fixed_atomic_publish"),
                        (os, "mkdir"),
                        (os, "fsync")):
                    operation = mock.Mock(
                        side_effect=AssertionError("held epoch attempted " + name))
                    blocked.append(operation)
                    stack.enter_context(mock.patch.object(owner, name, operation))
                yield
                for operation in blocked:
                    operation.assert_not_called()

    def hold(self, case, request, **changes):
        return self.module.hold_epoch(case.lib.__dict__, **{**request, **changes})

    def refuse(self, action):
        with self.assertRaises(self.module.ControllerDeliveryEpochRefusal) as caught:
            action()
        self.assertRegex(caught.exception.reason, r"\A[a-z][a-z0-9-]*\Z")
        return caught.exception

    def closed(self, held):
        self.refuse(held.current)
        self.refuse(held.read)

    def fds(self):
        """Observe descriptor identities while excluding the retired scan FD."""
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

    def assert_authority_descriptors_held(self, case, retained, root):
        _key, directory, birth, adoption, records = self.epoch.paths(retained, root)
        expected = {str(path) for path in (
            root, directory, birth, adoption, records,
            case.archive_path(), case.effects_archive_path(),
        )}
        expected.update(str(case.live.paths[name]) for name in (
            "MEMO_PATH", "STATUS_PATH", "GRAPH_PATH",
            "LIVE_STATE_PATH", "LIVE_CANDIDATE_PATH",
        ))
        actual = {identity[-1] for identity in self.fds().values()}
        self.assertTrue(expected.issubset(actual),
                        "authority descriptors absent: " + repr(expected - actual))

    def test_signature_keeps_mandatory_keyword_inputs_and_held_boundaries(self):
        signature = inspect.signature(self.module.hold_epoch)
        prepare_signature = inspect.signature(self.module.prepare_epoch)
        self.assertEqual(set(signature.parameters), set(prepare_signature.parameters))
        for name, parameter in signature.parameters.items():
            self.assertIs(parameter.default, inspect.Parameter.empty)
            self.assertEqual(parameter.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD
                             if name == "owner" else inspect.Parameter.KEYWORD_ONLY)
        nonclaims = list(self.module.HELD_NON_CLAIMS)
        self.assertTrue(nonclaims)
        self.assertTrue(all(type(claim) is str and claim.strip() for claim in nonclaims))
        # Require readable denials, not an invented exact prose label.
        for subject in (r"durab", r"writer", r"receipt", r"cognit|biolog", r"held[- ]?out"):
            mentions = [claim for claim in nonclaims if re.search(subject, claim, re.I)]
            self.assertTrue(mentions, "missing held boundary: " + subject)
            self.assertTrue(any(re.search(r"\b(no|not|never|without|cannot)\b", claim, re.I)
                                for claim in mentions), "missing denial: " + subject)

    def test_held_authority_has_a_distinct_bounded_aggregate_ceiling(self):
        with self.prepared() as (
                case, retained, committed, status, _generation, _root, adopted):
            request = self.request(case, retained, committed, status, adopted)
            with self.reader_scope(case), mock.patch.object(
                    self.module, "MAX_HELD_AUTHORITY_BYTES", 1):
                refusal = self.refuse(lambda: self.hold(case, request).__enter__())
            self.assertEqual(refusal.reason, "complete-authority-byte-capacity")

    def test_exact_prepared_legacy_view_holds_authority_through_body_and_copy(self):
        with self.prepared() as (case, retained, committed, status, generation, root, adopted):
            request = self.request(case, retained, committed, status, adopted)
            expected = self.expected(retained, committed, generation, root, adopted)
            inputs = copy.deepcopy(request)
            before = (case.images(), epoch_tests._tree(root))
            with self.reader_scope(case):
                descriptors = self.fds()
                with self.hold(case, request) as held:
                    for name in ("current", "read"):
                        self.assertTrue(callable(getattr(held, name, None)))
                        self.assertEqual(dict(inspect.signature(getattr(held, name)).parameters), {})
                    self.assertEqual(set(held.read()), VIEW_KEYS)
                    self.assertEqual(held.read(), expected)
                    self.assert_authority_descriptors_held(case, retained, root)
                    detached = copy.deepcopy(held.read())
                    held.current()
                    self.assertEqual(detached, expected)
                    self.assert_authority_descriptors_held(case, retained, root)
                self.closed(held)
                self.assertEqual(self.fds(), descriptors)
            self.assertEqual(request, inputs)
            self.assertEqual((case.images(), epoch_tests._tree(root)), before)

    def test_view_copies_cannot_mutate_retained_parent_adoption_or_identity(self):
        with self.prepared() as (case, retained, committed, status, generation, root, adopted):
            request = self.request(case, retained, committed, status, adopted)
            expected = self.expected(retained, committed, generation, root, adopted)
            before = (case.images(), epoch_tests._tree(root), copy.deepcopy(request))
            with self.reader_scope(case):
                with self.hold(case, request) as held:
                    first = held.read()
                    first["epoch_adoption"]["birth"]["limits"].clear()
                    first["parent_committed"].clear()
                    first["parent_generation"].clear()
                    first["records_identity"].clear()
                    first["non_claims"].clear()
                    self.assertEqual(held.read(), expected)
                    held.current()
                self.closed(held)
            self.assertEqual((case.images(), epoch_tests._tree(root), request), before)

    def test_missing_none_and_wrong_adoption_pins_refuse_without_effects(self):
        with self.prepared() as (case, retained, committed, status, _generation, root, adopted):
            request = self.request(case, retained, committed, status, adopted)
            before = (case.images(), epoch_tests._tree(root), copy.deepcopy(request))
            self.assertNotEqual(retained["batch_sha256"], adopted["expected_adoption_sha256"])
            with self.reader_scope(case):
                descriptors = self.fds()
                absent = {key: value for key, value in request.items()
                          if key != "expected_adoption_sha256"}
                with self.assertRaises(TypeError):
                    with self.hold(case, absent):
                        self.fail("missing mandatory adoption pin entered")
                for pin in (None, retained["batch_sha256"]):
                    with self.subTest(pin=pin), \
                            self.assertRaises(self.module.ControllerDeliveryEpochRefusal):
                        with self.hold(case, request, expected_adoption_sha256=pin):
                            self.fail("non-authorizing adoption pin entered")
                    self.assertEqual(self.fds(), descriptors)
            self.assertEqual((case.images(), epoch_tests._tree(root), request), before)

    def test_absent_adoption_storage_is_not_bootstrapped_by_held_reader(self):
        with self.epoch.completed() as (case, retained, committed, status, _generation, root):
            request = self.request(case, retained, committed, status,
                                   {"expected_adoption_sha256": retained["batch_sha256"]})
            before = (case.images(), epoch_tests._tree(root))
            with self.reader_scope(case):
                descriptors = self.fds()
                with self.assertRaises(self.module.ControllerDeliveryEpochRefusal):
                    with self.hold(case, request):
                        self.fail("unprepared legacy epoch entered")
                self.assertEqual(self.fds(), descriptors)
            self.assertFalse(root.exists())
            self.assertEqual((case.images(), epoch_tests._tree(root)), before)

    def test_pending_marker_is_not_repaired_by_held_reader(self):
        with self.prepared() as (case, retained, committed, status, _generation, root, adopted):
            request = self.request(case, retained, committed, status, adopted)
            case.live.memo[epoch_tests.MARKER_KEY]["adoption_sha256"] = None
            case.live._write(case.live.paths["MEMO_PATH"], case.live.memo)
            before = (case.images(), epoch_tests._tree(root))
            with self.reader_scope(case):
                descriptors = self.fds()
                with self.assertRaises(self.module.ControllerDeliveryEpochRefusal):
                    with self.hold(case, request):
                        self.fail("pending adoption marker entered")
                self.assertEqual(self.fds(), descriptors)
            self.assertEqual((case.images(), epoch_tests._tree(root)), before)

    def test_same_path_memo_rewrite_refuses_current_read_and_normal_exit(self):
        with self.prepared() as (case, retained, committed, status, _generation, _root, adopted):
            request = self.request(case, retained, committed, status, adopted)
            path = Path(case.live.paths["MEMO_PATH"])
            with self.reader_scope(case):
                descriptors = self.fds()
                with self.assertRaises(self.module.ControllerDeliveryEpochRefusal):
                    with self.hold(case, request) as held:
                        held.read()
                        path.write_bytes(path.read_bytes() + b" ")
                        self.refuse(held.current)
                        self.refuse(held.read)
                self.closed(held)
                self.assertEqual(self.fds(), descriptors)

    def test_same_bytes_new_adoption_inode_is_not_the_held_file(self):
        with self.prepared() as (case, retained, committed, status, _generation, root, adopted):
            request = self.request(case, retained, committed, status, adopted)
            _key, _directory, _birth, path, _records = self.epoch.paths(retained, root)
            raw = path.read_bytes()
            displaced = root.parent / "held-displaced-adoption.json"
            with self.reader_scope(case):
                descriptors = self.fds()
                with self.assertRaises(self.module.ControllerDeliveryEpochRefusal):
                    with self.hold(case, request) as held:
                        path.rename(displaced)
                        path.write_bytes(raw)
                        path.chmod(0o600)
                        self.refuse(held.current)
                        self.refuse(held.read)
                self.closed(held)
                self.assertEqual(self.fds(), descriptors)

    def test_records_directory_name_swap_does_not_rebind_held_identity(self):
        with self.prepared() as (case, retained, committed, status, _generation, root, adopted):
            request = self.request(case, retained, committed, status, adopted)
            _key, _directory, _birth, _adoption, records = self.epoch.paths(retained, root)
            displaced = root.parent / "held-displaced-records"
            fixture_mkdir = os.mkdir
            with self.reader_scope(case):
                descriptors = self.fds()
                with self.assertRaises(self.module.ControllerDeliveryEpochRefusal):
                    with self.hold(case, request) as held:
                        records.rename(displaced)
                        # Deliberate caller fixture mutation bypasses only its
                        # own no-production-mkdir spy, not the reader contract.
                        fixture_mkdir(records, mode=0o700)
                        self.refuse(held.current)
                        self.refuse(held.read)
                self.closed(held)
                self.assertEqual(self.fds(), descriptors)

    def test_source_slot_appearance_invalidates_the_held_predecessor(self):
        with self.prepared() as (case, retained, committed, status, _generation, _root, adopted):
            request = self.request(case, retained, committed, status, adopted)
            path = Path(case.producer.source_path)
            self.assertFalse(path.exists())
            archived = case.archive_path().read_bytes()
            with self.reader_scope(case):
                descriptors = self.fds()
                with self.assertRaises(self.module.ControllerDeliveryEpochRefusal):
                    with self.hold(case, request) as held:
                        path.write_bytes(archived)
                        path.chmod(0o600)
                        self.refuse(held.current)
                        self.refuse(held.read)
                self.closed(held)
                self.assertEqual(self.fds(), descriptors)

    def test_normal_exit_revalidates_without_an_explicit_current_call(self):
        with self.prepared() as (case, retained, committed, status, _generation, root, adopted):
            request = self.request(case, retained, committed, status, adopted)
            _key, _directory, birth, _adoption, _records = self.epoch.paths(retained, root)
            with self.reader_scope(case):
                descriptors = self.fds()
                with self.assertRaises(self.module.ControllerDeliveryEpochRefusal):
                    with self.hold(case, request) as held:
                        held.read()
                        birth.write_bytes(birth.read_bytes() + b" ")
                self.closed(held)
                self.assertEqual(self.fds(), descriptors)

    def test_exceptional_exit_preserves_caller_error_and_closes_only_own_fds(self):
        with self.prepared() as (case, retained, committed, status, _generation, root, adopted):
            request = self.request(case, retained, committed, status, adopted)
            sentinel_path = root.parent / "held-caller-owned-sentinel"
            sentinel_path.write_bytes(b"caller-owned fixture\n")
            failure = CallerFailure("synthetic held-epoch caller failure")
            with sentinel_path.open("rb") as sentinel, self.reader_scope(case):
                sentinel_identity = os.fstat(sentinel.fileno())
                descriptors = self.fds()
                with self.assertRaises(CallerFailure) as caught:
                    with self.hold(case, request) as held:
                        self.assert_authority_descriptors_held(case, retained, root)
                        path = Path(case.live.paths["MEMO_PATH"])
                        path.write_bytes(path.read_bytes() + b" ")
                        raise failure
                self.assertIs(caught.exception, failure)
                self.assertEqual(os.fstat(sentinel.fileno()), sentinel_identity)
                self.closed(held)
                self.assertEqual(self.fds(), descriptors)


if __name__ == "__main__":
    unittest.main()
