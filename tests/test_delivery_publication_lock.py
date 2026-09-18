"""Opt-in nonblocking fixed publication for pre-output journal boundaries.

Root alone executes these tests. A distinct open file description holds the
real staging lock. A syscall guard prevents a broken implementation from
hanging the sequential gate: required LOCK_NB is asserted before delegation
to the real flock, which must observe actual kernel lock contention.
No measured duration or derived numerical fixture is asserted.
"""

import contextlib
import errno
import fcntl
import importlib
import inspect
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "bin"))


class DeliveryPublicationLock(unittest.TestCase):
    def setUp(self):
        self.queue = importlib.import_module("siaqueue")
        self.temporary = tempfile.TemporaryDirectory(prefix="sia-publication-lock-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.destination = self.root / "journal"
        self.staging = self.root / "staging"
        self.destination.mkdir(mode=0o700)
        self.staging.mkdir(mode=0o700)
        self.target = self.destination / "intent.json"
        self.payload = b"private immutable journal payload\n"

    @contextlib.contextmanager
    def hold_staging_lock(self):
        flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        descriptor = os.open(self.staging / self.queue.STAGING_LOCK_NAME, flags, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield descriptor
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @contextlib.contextmanager
    def require_nonblocking_syscall(self):
        actual = fcntl.flock
        acquired = []

        def guarded(descriptor, operation):
            if operation != fcntl.LOCK_UN:
                self.assertTrue(operation & fcntl.LOCK_NB,
                                "blocking syscall must not hang the pre-output gate")
                acquired.append(descriptor)
            return actual(descriptor, operation)

        with mock.patch("fcntl.flock", side_effect=guarded):
            yield acquired

    def assert_contended(self, action):
        # TypeError from a missing optional flag is intentionally NOT caught:
        # the original implementation must fail this RED for the right reason.
        with self.assertRaises(OSError) as caught:
            action()
        self.assertIn(caught.exception.errno, (errno.EWOULDBLOCK, errno.EAGAIN))
        self.assertFalse(self.target.exists())
        self.assertFalse((self.staging / self.queue.STAGING_PAYLOAD_NAME).exists())

    def test_public_and_staging_lock_flags_are_optional_keyword_only_and_default_false(self):
        for function in (self.queue.fixed_atomic_publish, self.queue._staging_lock):
            parameters = inspect.signature(function).parameters
            self.assertIn("nonblocking", parameters)
            self.assertEqual(parameters["nonblocking"].kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameters["nonblocking"].default, False)

    def test_contended_staging_lock_refuses_without_entering_or_waiting(self):
        directory = os.open(self.staging, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        self.addCleanup(os.close, directory)

        def enter():
            with self.queue._staging_lock(directory, nonblocking=True):
                self.fail("contended staging lock was incorrectly acquired")

        with self.hold_staging_lock() as held:
            with self.require_nonblocking_syscall() as acquired:
                self.assert_contended(enter)
            self.assertTrue(acquired)
            self.assertTrue(all(descriptor != held for descriptor in acquired))

    def test_contended_publisher_refuses_before_payload_or_target_output(self):
        with self.hold_staging_lock() as held:
            with self.require_nonblocking_syscall() as acquired:
                self.assert_contended(lambda: self.queue.fixed_atomic_publish(
                    str(self.target), self.payload, exclusive=True,
                    staging_dir=str(self.staging), nonblocking=True))
            self.assertTrue(acquired)
            self.assertTrue(all(descriptor != held for descriptor in acquired))
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_uncontended_nonblocking_publication_and_exact_retry_remain_durable(self):
        with self.require_nonblocking_syscall() as acquired:
            self.assertEqual(self.queue.fixed_atomic_publish(
                str(self.target), self.payload, exclusive=True,
                staging_dir=str(self.staging), nonblocking=True), "published")
            self.assertEqual(self.queue.fixed_atomic_publish(
                str(self.target), self.payload, exclusive=True,
                staging_dir=str(self.staging), nonblocking=True), "existing")
        self.assertTrue(acquired)
        self.assertEqual(self.target.read_bytes(), self.payload)
        self.assertFalse((self.staging / self.queue.STAGING_PAYLOAD_NAME).exists())

    def test_omitted_and_explicit_false_keep_existing_blocking_default(self):
        actual = fcntl.flock
        acquisitions = []

        def guarded(descriptor, operation):
            if operation != fcntl.LOCK_UN:
                self.assertFalse(operation & fcntl.LOCK_NB,
                                 "legacy callers must retain their existing lock mode")
                acquisitions.append(descriptor)
            return actual(descriptor, operation)

        with mock.patch("fcntl.flock", side_effect=guarded):
            self.assertEqual(self.queue.fixed_atomic_publish(
                str(self.target), self.payload, exclusive=True,
                staging_dir=str(self.staging)), "published")
            self.assertEqual(self.queue.fixed_atomic_publish(
                str(self.target), self.payload, exclusive=True,
                staging_dir=str(self.staging), nonblocking=False), "existing")
        self.assertTrue(acquisitions)
        self.assertEqual(self.target.read_bytes(), self.payload)
