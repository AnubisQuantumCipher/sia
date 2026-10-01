#!/usr/bin/env python3
"""Runtime measurement owns descriptors even across non-Exception failures."""

import errno
import hashlib
import os
from pathlib import Path
import tempfile
import types
import unittest
from contextlib import contextmanager
from unittest import mock


RELEASE_SOURCE = Path(__file__).resolve().parent.parent / "bin/siarelease.py"


def _load_release_source():
    # This standard-library-only authority has no SIA corpus/index imports.
    # Compile its current source directly rather than accepting cached bytecode
    # or importing test_release and its process-wide home-isolation machinery.
    module = types.ModuleType("siarelease_descriptor_failure_test")
    module.__file__ = os.fspath(RELEASE_SOURCE)
    with RELEASE_SOURCE.open("rb") as stream:
        source = stream.read()
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


class _OsShim:
    """Forward real syscalls except for overrides local to this module load."""

    def __init__(self, **overrides):
        self._overrides = overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(os, name)


class _InspectionInterrupted(BaseException):
    pass


class RuntimeDescriptorFailureIntegrity(unittest.TestCase):
    def setUp(self):
        if not getattr(os, "O_PATH", 0):
            self.skipTest("mode-zero descriptor inspection requires O_PATH")
        self.release = _load_release_source()

    @contextmanager
    def _fenced_runtime(self):
        ladder = ((b"sia-runtime-v1\0", ("member",), ()),)
        with tempfile.TemporaryDirectory(
                prefix="sia-runtime-descriptor-") as runtime, \
                mock.patch.object(self.release, "RUNTIME_LADDER", ladder):
            member = os.path.join(runtime, "member")
            payload = b"stable attested runtime member\n"
            with open(member, "wb") as stream:
                stream.write(payload)
            os.chmod(member, 0o600)
            expected_digest = self.release.runtime_tree_digest(runtime)
            identity = os.stat(member, follow_symlinks=False)
            entries = {member: {
                "device": identity.st_dev,
                "inode": identity.st_ino,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }}
            os.chmod(member, 0)
            yield runtime, entries, expected_digest

    @contextmanager
    def _capture_measurement(self, runtime, *, interruption=None):
        opened = {}
        flags_seen = {}

        def capture_open(path, flags, *args, **kwargs):
            descriptor = os.open(path, flags, *args, **kwargs)
            name = os.fspath(path)
            if name == runtime:
                opened["root"] = descriptor
                flags_seen["root"] = flags
            elif name == "member":
                opened["member"] = descriptor
                flags_seen["member"] = flags
            return descriptor

        def inspect(descriptor):
            if interruption is not None and descriptor == opened.get("member"):
                raise interruption
            return os.fstat(descriptor)

        try:
            with mock.patch.object(
                    self.release, "os",
                    _OsShim(open=capture_open, fstat=inspect)):
                yield opened, flags_seen
        finally:
            # A deliberately weakened handler must fail the assertion below,
            # but must not leak its descriptor into the next suite test.
            for descriptor in opened.values():
                try:
                    os.fstat(descriptor)
                except OSError as error:
                    if error.errno != errno.EBADF:
                        raise
                else:
                    os.close(descriptor)

    def _assert_measurement_descriptors_closed(self, opened, flags_seen):
        self.assertEqual(set(opened), {"root", "member"})
        self.assertTrue(flags_seen["member"] & os.O_PATH)
        for name, descriptor in opened.items():
            with self.subTest(descriptor_owner=name):
                with self.assertRaises(OSError) as caught:
                    os.fstat(descriptor)
                self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_mode_zero_inspection_baseexception_propagates_and_closes_descriptors(
            self):
        interruption = _InspectionInterrupted("member inspection interrupted")
        with self._fenced_runtime() as (runtime, entries, _expected), \
                self._capture_measurement(
                    runtime, interruption=interruption) as (opened, flags_seen):
            with self.assertRaises(_InspectionInterrupted) as caught:
                self.release._measure_runtime_tree(runtime, entries)
            self.assertIs(caught.exception, interruption)
            self._assert_measurement_descriptors_closed(opened, flags_seen)

    def test_ancestor_rebind_is_not_held_runtime_authority(self):
        ladder = ((b"sia-runtime-v1\0", ("member",), ()),)
        for fenced in (False, True):
            with self.subTest(fenced=fenced), tempfile.TemporaryDirectory(
                    prefix="sia-runtime-ancestor-") as container, \
                    mock.patch.object(self.release, "RUNTIME_LADDER", ladder):
                named = Path(container) / "named"
                held = Path(container) / "held"
                runtime = named / "runtime"
                runtime.mkdir(parents=True)
                member = runtime / "member"
                member.write_bytes(b"same runtime member\n")
                member.chmod(0o600)
                before = self.release._runtime_generation(runtime.stat())
                real_hash = self.release._hash_runtime_member
                rebound = False

                def rebind_ancestor(descriptor, name, uid):
                    nonlocal rebound
                    measured = real_hash(descriptor, name, uid)
                    named.rename(held)
                    runtime.mkdir(parents=True)
                    replacement = runtime / "member"
                    replacement.write_bytes(b"same runtime member\n")
                    replacement.chmod(0o600)
                    rebound = True
                    return measured

                with mock.patch.object(
                        self.release, "_hash_runtime_member",
                        side_effect=rebind_ancestor), \
                        self.assertRaisesRegex(ValueError, "runtime tree changed"):
                    self.release._measure_runtime_tree(
                        os.fspath(runtime), {} if fenced else None)
                self.assertTrue(rebound)
                self.assertEqual(
                    self.release._runtime_generation((held / "runtime").stat()),
                    before, "the held runtime must not change in this fixture")

    def test_stable_mode_zero_measurement_matches_digest_and_closes_descriptors(
            self):
        with self._fenced_runtime() as (runtime, entries, expected), \
                self._capture_measurement(runtime) as (opened, flags_seen):
            self.assertEqual(
                self.release._measure_runtime_tree(runtime, entries), expected)
            self._assert_measurement_descriptors_closed(opened, flags_seen)


if __name__ == "__main__":
    unittest.main()
