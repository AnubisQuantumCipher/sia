"""A held epoch reader cannot acquire missing ordinary scope as a fallback.

The real prepared-epoch fixture already owns a corpus lease. These negative
cases temporarily hide or replace only its ContextVar values, never close or
release that original descriptor, and require refusal before corpus_owner or
any infrastructure/writer operation is called. Context tokens are restored
before the fixture unwinds. A raw inherited descriptor is not entered scope.

The fixture TestCase is module-qualified to avoid duplicate unittest discovery.
No live source, corpus, model, output or cognitive claim is exercised here.
"""

import contextlib
import copy
import os
import stat
import unittest
from unittest import mock

from tests import test_controller_delivery_epoch_hold as hold_tests


def _identity(descriptor):
    info = os.fstat(descriptor)
    # Read-only fixture snapshots may update atime. It is not lease identity.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid, info.st_nlink)


class ControllerDeliveryEpochHeldScope(unittest.TestCase):
    def setUp(self):
        self.fixture = hold_tests.ControllerDeliveryEpochHold(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.module = self.fixture.module

    @contextlib.contextmanager
    def scope_values(self, case, *, depth, descriptor):
        depth_token = case.lib._CORPUS_OWNER_DEPTH.set(depth)
        fd_token = case.lib._CORPUS_OWNER_FD.set(descriptor)
        try:
            yield
        finally:
            case.lib._CORPUS_OWNER_FD.reset(fd_token)
            case.lib._CORPUS_OWNER_DEPTH.reset(depth_token)

    @contextlib.contextmanager
    def no_acquisition_or_effects(self, case):
        # No reader_scope helper here: it enters corpus_owner before its spies
        # and would conceal the exact precondition this file is testing.
        with self.fixture.epoch.idle.source_owner(case), contextlib.ExitStack() as stack:
            blocked = []
            for owner, name in (
                    (case.lib, "corpus_owner"),
                    (case.lib, "brainstem_owner"),
                    (case.lib, "_owner_lease"),
                    (case.lib, "ensure_dirs"),
                    (case.lib, "ensure_durable_directory"),
                    (case.lib, "atomic_write"),
                    (case.lib, "_write_memo"),
                    (self.fixture.epoch.queue, "fixed_atomic_publish"),
                    (os, "mkdir"),
                    (os, "fsync"),
                    (os, "fchmod")):
                operation = mock.Mock(side_effect=AssertionError(
                    "unowned held reader reached acquisition/effect: " + name))
                blocked.append(operation)
                stack.enter_context(mock.patch.object(owner, name, operation))
            yield
            for operation in blocked:
                operation.assert_not_called()

    def images(self, case, root):
        return (case.images(), hold_tests.epoch_tests._tree(case.live.root),
                hold_tests.epoch_tests._tree(root), copy.deepcopy(case.live.memo))

    def refuse(self, case, request, *, owner=None):
        selected = case.lib.__dict__ if owner is None else owner
        with self.assertRaises(self.module.ControllerDeliveryEpochRefusal) as caught:
            with self.module.hold_epoch(selected, **request):
                self.fail("unentered or invalid corpus scope admitted a held epoch")
        self.assertRegex(caught.exception.reason, r"\A[a-z][a-z0-9-]*\Z")

    def test_unowned_entry_refuses_without_trying_ordinary_or_inherited_acquisition(self):
        with self.fixture.prepared() as fixture:
            case, retained, committed, status, _generation, root, adopted = fixture
            request = self.fixture.request(case, retained, committed, status, adopted)
            original_fd = case.lib._CORPUS_OWNER_FD.get()
            original_depth = case.lib._CORPUS_OWNER_DEPTH.get()
            self.assertIs(type(original_fd), int)
            self.assertIs(type(original_depth), int)
            self.assertGreater(original_depth, 0)
            original_identity = _identity(original_fd)
            before = self.images(case, root)
            # If queried this would return the genuinely open original lease.
            # The reader must not query/adopt it until its caller enters the
            # ordinary scope, regardless of inherited descriptor availability.
            inherited = mock.Mock(return_value=original_fd)
            with self.scope_values(case, depth=0, descriptor=None), \
                    mock.patch.object(case.lib, "_validated_inherited_corpus_fd", inherited), \
                    self.no_acquisition_or_effects(case):
                self.refuse(case, request)
            inherited.assert_not_called()
            self.assertEqual(case.lib._CORPUS_OWNER_DEPTH.get(), original_depth)
            self.assertEqual(case.lib._CORPUS_OWNER_FD.get(), original_fd)
            self.assertEqual(_identity(original_fd), original_identity)
            self.assertEqual(self.images(case, root), before)

    def test_depth_must_be_an_actual_positive_integer_even_with_a_live_scope_fd(self):
        with self.fixture.prepared() as fixture:
            case, retained, committed, status, _generation, root, adopted = fixture
            request = self.fixture.request(case, retained, committed, status, adopted)
            original_fd = case.lib._CORPUS_OWNER_FD.get()
            original_identity = _identity(original_fd)
            for depth in (None, 0, -1, False, True, "1"):
                with self.subTest(depth=depth):
                    before = self.images(case, root)
                    with self.scope_values(case, depth=depth, descriptor=original_fd), \
                            self.no_acquisition_or_effects(case):
                        self.refuse(case, request)
                    self.assertEqual(_identity(original_fd), original_identity)
                    self.assertEqual(self.images(case, root), before)

    def test_missing_or_nonnative_scoped_fd_refuses_without_a_new_owner_call(self):
        with self.fixture.prepared() as fixture:
            case, retained, committed, status, _generation, root, adopted = fixture
            request = self.fixture.request(case, retained, committed, status, adopted)
            original_fd = case.lib._CORPUS_OWNER_FD.get()
            original_depth = case.lib._CORPUS_OWNER_DEPTH.get()
            original_identity = _identity(original_fd)
            for descriptor in (None, -1, False, True, str(original_fd)):
                with self.subTest(descriptor=descriptor):
                    before = self.images(case, root)
                    with self.scope_values(case, depth=original_depth, descriptor=descriptor), \
                            self.no_acquisition_or_effects(case):
                        self.refuse(case, request)
                    self.assertEqual(_identity(original_fd), original_identity)
                    self.assertEqual(self.images(case, root), before)

    def test_closed_duplicate_is_not_a_live_scope_and_never_closes_the_original(self):
        with self.fixture.prepared() as fixture:
            case, retained, committed, status, _generation, root, adopted = fixture
            request = self.fixture.request(case, retained, committed, status, adopted)
            original_fd = case.lib._CORPUS_OWNER_FD.get()
            original_depth = case.lib._CORPUS_OWNER_DEPTH.get()
            original_identity = _identity(original_fd)
            before = self.images(case, root)
            duplicate = os.dup(original_fd)
            self.assertNotEqual(duplicate, original_fd)
            os.close(duplicate)
            # Do not open fixture files between retiring the duplicate and
            # invoking the guard; its number must remain an actually closed FD.
            with self.scope_values(case, depth=original_depth, descriptor=duplicate), \
                    self.no_acquisition_or_effects(case):
                self.refuse(case, request)
            self.assertEqual(_identity(original_fd), original_identity)
            self.assertEqual(self.images(case, root), before)

    def test_directory_and_nonprivate_regular_descriptors_are_not_scope_leases(self):
        with self.fixture.prepared() as fixture:
            case, retained, committed, status, _generation, root, adopted = fixture
            request = self.fixture.request(case, retained, committed, status, adopted)
            original_fd = case.lib._CORPUS_OWNER_FD.get()
            original_depth = case.lib._CORPUS_OWNER_DEPTH.get()
            original_identity = _identity(original_fd)
            sentinel = root.parent / "nonprivate-scope-fixture"
            sentinel.write_bytes(b"not an owner-private lease\n")
            sentinel.chmod(0o644)
            for path, flags in (
                    (root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW),
                    (sentinel, os.O_RDONLY | os.O_NOFOLLOW)):
                with self.subTest(path=path.name):
                    descriptor = os.open(path, flags)
                    try:
                        candidate_info = os.fstat(descriptor)
                        candidate_identity = _identity(descriptor)
                        self.assertTrue(stat.S_ISDIR(candidate_info.st_mode)
                                        or stat.S_IMODE(candidate_info.st_mode) != 0o600)
                        before = self.images(case, root)
                        with self.scope_values(case, depth=original_depth, descriptor=descriptor), \
                                self.no_acquisition_or_effects(case):
                            self.refuse(case, request)
                        self.assertEqual(_identity(descriptor), candidate_identity)
                        self.assertEqual(_identity(original_fd), original_identity)
                        self.assertEqual(self.images(case, root), before)
                    finally:
                        os.close(descriptor)

    def test_missing_scope_contextvar_objects_refuse_before_calling_owner(self):
        with self.fixture.prepared() as fixture:
            case, retained, committed, status, _generation, root, adopted = fixture
            request = self.fixture.request(case, retained, committed, status, adopted)
            original_fd = case.lib._CORPUS_OWNER_FD.get()
            original_identity = _identity(original_fd)
            for missing in ("_CORPUS_OWNER_DEPTH", "_CORPUS_OWNER_FD"):
                with self.subTest(missing=missing):
                    before = self.images(case, root)
                    with self.no_acquisition_or_effects(case):
                        # Copy after spies are installed so the isolated owner
                        # cannot retain an uninstrumented acquisition function.
                        owner = dict(case.lib.__dict__)
                        owner.pop(missing)
                        self.refuse(case, request, owner=owner)
                    self.assertEqual(_identity(original_fd), original_identity)
                    self.assertEqual(self.images(case, root), before)


if __name__ == "__main__":
    unittest.main()
