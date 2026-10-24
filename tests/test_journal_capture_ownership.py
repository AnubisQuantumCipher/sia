"""Acquired journal descriptors remain owned across injected metadata faults."""

import errno
import importlib
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock


class FaultOS:
    def __init__(self, cut=None, error=OSError, persistent=False):
        self.cut, self.error, self.persistent = cut, error, persistent
        self.opened, self.closed = [], []
        self.pending, self.hits = None, 0

    def __getattr__(self, name):
        return getattr(os, name)

    def open(self, path, flags, *args, **kwargs):
        descriptor = os.open(path, flags, *args, **kwargs)
        self.opened.append(descriptor)
        if self.cut == len(self.opened) or self.cut == path:
            self.pending = descriptor
        return descriptor

    def fstat(self, descriptor):
        if descriptor == self.pending:
            if not self.persistent:
                self.pending = None
            self.hits += 1
            raise self.error("injected post-open metadata failure")
        return os.fstat(descriptor)

    def close(self, descriptor):
        os.close(descriptor)
        self.closed.append(descriptor)

    def unclosed(self):
        result = []
        for descriptor in set(self.opened):
            try:
                os.fstat(descriptor)
            except OSError as exc:
                if exc.errno != errno.EBADF:
                    raise
            else:
                result.append(descriptor)
        return result

    def release_leaks(self):
        for descriptor in self.unclosed():
            os.close(descriptor)


class JournalCaptureOwnership(unittest.TestCase):
    def setUp(self):
        binary = str(Path(__file__).resolve().parents[1] / "bin")
        previous = list(sys.path)
        try:
            sys.path.insert(0, binary)
            self.capture = importlib.import_module("siajournalcapture")
        finally:
            sys.path[:] = previous
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state, self.operation = self.root / "state", self.root / "operation"
        self.state.mkdir(mode=0o700)
        self.operation.mkdir(mode=0o700)
        self.cursor = self.state / "journal-sys.cursor"
        self.cursor.write_bytes(b"retained-cursor")
        self.cursor.chmod(0o600)

    def owner(self, probe):
        return {"os": probe, "re": re, "STATE": str(self.state),
                "MAX_CONFIG_PATH_CHARS": 4096, "MAX_SOURCE_NAME_CHARS": 128,
                "MAX_JOURNAL_CURSOR_BYTES": 4096, "MAX_JOURNAL_READ_BYTES": 4096}

    def context(self, probe):
        self.addCleanup(probe.release_leaks)
        context = self.capture.JournalCaptureContext(
            self.owner(probe), operation_id="ownership-fixture",
            directory=str(self.operation))
        self.addCleanup(context.close)
        return context

    def seed_path(self, context, scope="sys", suffix="catalog"):
        context.begin(scope, str(self.state / ("journal-" + scope + ".cursor")), True)
        return context.path(scope + "." + suffix)

    def assert_released(self, probe):
        self.assertEqual(probe.unclosed(), [])
        self.assertCountEqual(probe.closed, probe.opened)

    def test_each_directory_acquisition_is_owned_before_metadata(self):
        # Every component of this bounded private path, including the root.
        for error in (OSError, KeyboardInterrupt):
            for cut in range(1, len(self.operation.parts) + 1):
                with self.subTest(error=error.__name__, cut=cut):
                    probe = FaultOS(cut, error)
                    try:
                        with self.assertRaisesRegex(error, "post-open metadata"):
                            self.capture._Directory(self.owner(probe), str(self.operation))
                        self.assertEqual(probe.hits, 1)
                        self.assert_released(probe)
                    finally:
                        probe.release_leaks()

    def test_successful_directory_preserves_identity_and_releases_once(self):
        probe = FaultOS()
        directory = self.capture._Directory(self.owner(probe), str(self.operation))
        try:
            directory.current()
            self.assertEqual(len(directory.chain), len(self.operation.parts))
        finally:
            directory.close()
        directory.close()
        self.assert_released(probe)

    def test_seed_faults_are_terminal_and_release_scratch(self):
        for scope in ("sys", "user"):
            for suffix in ("catalog", "full"):
                for error in (OSError, KeyboardInterrupt):
                    leaf = scope + "." + suffix
                    with self.subTest(leaf=leaf, error=error.__name__), \
                            tempfile.TemporaryDirectory(dir=self.root) as operation:
                        self.operation = Path(operation)
                        self.check_seed_fault(scope, suffix, error)

    def check_seed_fault(self, scope, suffix, error):
        probe = FaultOS(scope + "." + suffix, error)
        context = self.context(probe)
        path = self.seed_path(context, scope, suffix)
        try:
            with self.assertRaisesRegex(error, "post-open metadata"):
                context.seed(scope, path)
            self.assertEqual(probe.hits, 1)
            failed = context.failed
            refusal = None
            try:
                context.current()
            except ValueError as exc:
                refusal = str(exc)
        finally:
            context.close()
        try:
            self.assert_released(probe)
            self.assertTrue(failed)
            self.assertIsNotNone(refusal)
            self.assertIn("closed-or-failed", refusal)
            self.assertEqual(list(self.operation.iterdir()), [])
            self.assertEqual(self.cursor.read_bytes(), b"retained-cursor")
        finally:
            probe.release_leaks()

    def test_failed_seed_does_not_unlink_a_replacement(self):
        probe = FaultOS("sys.catalog")
        context = self.context(probe)
        path = self.seed_path(context)
        with self.assertRaises(OSError):
            context.seed("sys", path)
        leaf = self.operation / "sys.catalog"
        leaf.unlink()
        leaf.write_bytes(b"replacement is not ours")
        context.close()
        self.assert_released(probe)
        self.assertEqual(leaf.read_bytes(), b"replacement is not ours")

    def test_persistent_metadata_failure_retains_uncertain_file_but_closes(self):
        probe = FaultOS("sys.catalog", persistent=True)
        context = self.context(probe)
        path = self.seed_path(context)
        with self.assertRaises(OSError):
            context.seed("sys", path)
        context.close()
        self.assert_released(probe)
        self.assertTrue((self.operation / "sys.catalog").is_file())
        self.assertGreaterEqual(probe.hits, 2)
        other = FaultOS()
        with self.assertRaisesRegex(ValueError, "preexisting-operation-scratch"):
            self.capture.JournalCaptureContext(
                self.owner(other), operation_id="retry-fixture", directory=str(self.operation))
        self.assert_released(other)

    def test_normal_seed_preserves_cursor_and_cleans_scratch(self):
        probe = FaultOS()
        context = self.context(probe)
        path = self.seed_path(context)
        context.seed("sys", path)
        self.assertEqual((self.operation / "sys.catalog").read_bytes(), b"retained-cursor")
        context.current()
        context.close()
        context.close()
        self.assert_released(probe)
        self.assertEqual(list(self.operation.iterdir()), [])
        self.assertEqual(self.cursor.read_bytes(), b"retained-cursor")

    def check_seed_io_failure(self, operation, error):
        probe = FaultOS()
        context = self.context(probe)
        path = self.seed_path(context)
        options = {"return_value": 0} if error is None else {
            "side_effect": error("injected seed I/O failure")}
        try:
            with mock.patch.object(probe, operation, **options) as injected:
                with self.assertRaises(ValueError if error is None else error):
                    context.seed("sys", path)
                injected.assert_called_once()
            self.assertTrue(context.failed)
            with self.assertRaisesRegex(ValueError, "closed-or-failed"):
                context.current()
        finally:
            context.close()
        self.assert_released(probe)
        self.assertEqual(list(self.operation.iterdir()), [])
        self.assertEqual(self.cursor.read_bytes(), b"retained-cursor")

    def test_write_and_sync_failure_invalidate_capture(self):
        for operation in ("write", "fsync"):
            for error in (OSError, KeyboardInterrupt):
                with self.subTest(operation=operation, error=error.__name__):
                    self.check_seed_io_failure(operation, error)

    def test_zero_write_invalidates_capture(self):
        self.check_seed_io_failure("write", None)


if __name__ == "__main__":
    unittest.main()
