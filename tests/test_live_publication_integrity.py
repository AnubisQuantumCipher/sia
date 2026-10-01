"""Late real-filesystem mutations must not escape live publication guards.

Root alone executes these tests. They compose the frozen synthetic publication
fixture without inheriting its suite or changing any clocks. No resident data,
engine, model, keeper or CLI is used. Every digest remains hashlib's real
result; only its finalization exposes a deterministic mutation boundary.

The attack is armed only when the existing _live_files context is exiting,
after the public reader/publisher has constructed its result. A renamed parent
does not mutate held child files. Replacing an earlier roster member while the
last member is hashed likewise leaves that last descriptor unchanged. Both
cases require late named and complete-roster checks, not another held-fd hash.
"""

import contextlib
import hashlib
import os
from pathlib import Path
import unittest
from unittest import mock

from tests import test_live_publication as publication_tests


PUBLICATION_PATHS = (
    "MEMO_PATH", "STATUS_PATH", "GRAPH_PATH", "LIVE_CANDIDATE_PATH", "LIVE_STATE_PATH",
)


class _RealHashFinalization:
    """Forward actual hashing and invoke the callback after the real result."""

    def __init__(self, callback):
        self.callback = callback

    def __getattr__(self, name):
        return getattr(hashlib, name)

    def sha256(self, data=b"", *args, **kwargs):
        actual = hashlib.sha256(data, *args, **kwargs)
        raw = bytearray(data)
        callback = self.callback

        class Digest:
            def update(self, block):
                raw.extend(block)
                return actual.update(block)

            def hexdigest(self):
                result = actual.hexdigest()
                callback(bytes(raw), result)
                return result

            def digest(self):
                result = actual.digest()
                callback(bytes(raw), actual.hexdigest())
                return result

        return Digest()


class LivePublicationLateGenerationIntegrity(unittest.TestCase):
    def setUp(self):
        self.fixture = publication_tests.LivePublication(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        # The publication parent is separate from the fixture's held owner
        # lock and temp root. Renaming it neither replaces the owner lease nor
        # leaves test files outside the root's ordinary cleanup boundary.
        self.directory = self.fixture.root / "publication"
        self.directory.mkdir(mode=0o700)
        for name in PUBLICATION_PATHS:
            prior = Path(self.fixture.paths[name])
            current = self.directory / prior.name
            if prior.exists():
                prior.rename(current)
            self.fixture.paths[name] = str(current)
            self.fixture.stack.enter_context(mock.patch.object(self.lib, name, str(current)))
        self.retained = self.fixture.root / "publication-retained"

    def publish_control(self):
        self.fixture._stage()
        generation = self.fixture._publish()
        view = self.fixture._view()
        self.fixture._assert_view(view, "available")
        self.assertEqual(view["generation"], generation)
        return generation

    def replace_parent_with_identical_files(self, _files):
        self.directory.rename(self.retained)
        self.directory.mkdir(mode=0o700)
        for name in PUBLICATION_PATHS:
            path = Path(self.fixture.paths[name])
            original = self.retained / path.name
            if original.exists():
                path.write_bytes(original.read_bytes())
                path.chmod(0o600)
        self.assertNotEqual(self.directory.stat().st_ino, self.retained.stat().st_ino)

    def replace_earlier_member_with_identical_bytes(self, files):
        last = next(reversed(files))
        earlier = next(name for name in files if name != last and files[name].fd is not None)
        owned = files[earlier]
        path = Path(owned.path)
        original = path.read_bytes()
        replacement = self.directory / "identical-replacement.json"
        replacement.write_bytes(original)
        replacement.chmod(0o600)
        os.replace(replacement, path)
        self.assertEqual(path.read_bytes(), original)
        self.assertNotEqual(path.stat().st_ino, os.fstat(owned.fd).st_ino)

    @contextlib.contextmanager
    def mutate_during_last_scope_exit_hash(self, mutation):
        original_files = self.lib._live_files
        original_current = self.lib._LivePublicationFile.current
        phase = {"exiting": False, "files": None, "target": None, "owned": None}
        observed = []

        @contextlib.contextmanager
        def tracked_files():
            with original_files() as resources:
                yield resources
                # The public function's return expression is already built.
                # Original context exit still performs its real final guard.
                files = resources[0]
                phase.update(exiting=True, files=files,
                             target=files[next(reversed(files))].path)

        def tracked_current(owned):
            previous = phase["owned"]
            phase["owned"] = owned
            try:
                return original_current(owned)
            finally:
                phase["owned"] = previous

        def finalized(raw, actual_digest):
            owned = phase["owned"]
            if not phase["exiting"] or owned is None or owned.path != phase["target"] or observed:
                return
            # This is an actual complete file hash, not a fabricated replay,
            # altered JSON parse or replacement of the guard's result.
            self.assertEqual(raw, Path(owned.path).read_bytes())
            self.assertEqual(actual_digest, owned.wire_sha256)
            self.assertEqual(actual_digest, hashlib.sha256(raw).hexdigest())
            before = owned.identity(os.fstat(owned.fd))
            observed.append(owned.path)
            mutation(phase["files"])
            self.assertEqual(owned.identity(os.fstat(owned.fd)), before,
                             "fixture changed the last held file, not just named authority")

        with mock.patch.object(self.lib, "_live_files", tracked_files), \
                mock.patch.object(self.lib._LivePublicationFile, "current", tracked_current), \
                mock.patch.object(self.lib, "hashlib", _RealHashFinalization(finalized)):
            yield observed

    def test_unchanged_reader_and_publisher_control_remains_available(self):
        self.publish_control()

    def test_reader_refuses_parent_replacement_during_final_scope_exit_hash(self):
        self.publish_control()
        with self.mutate_during_last_scope_exit_hash(self.replace_parent_with_identical_files) as observed:
            with self.assertRaises(RuntimeError):
                self.fixture._view()
        self.assertTrue(observed, "the final scope-exit hash boundary was not reached")

    def test_publisher_refuses_parent_replacement_during_final_scope_exit_hash(self):
        self.fixture._stage()
        with self.mutate_during_last_scope_exit_hash(self.replace_parent_with_identical_files) as observed:
            with self.assertRaises(RuntimeError):
                self.fixture._publish()
        self.assertTrue(observed, "the final scope-exit hash boundary was not reached")
        # A late refusal must not pretend already published bytes never existed
        # or require deletion of the independently retained original image.
        self.assertTrue((self.retained / Path(self.fixture.paths["LIVE_STATE_PATH"]).name).is_file())

    def test_reader_refuses_earlier_member_replacement_during_last_member_hash(self):
        self.publish_control()
        with self.mutate_during_last_scope_exit_hash(
                self.replace_earlier_member_with_identical_bytes) as observed:
            with self.assertRaises(RuntimeError):
                self.fixture._view()
        self.assertTrue(observed, "the final scope-exit hash boundary was not reached")

    def test_publisher_refuses_earlier_member_replacement_during_last_member_hash(self):
        self.fixture._stage()
        with self.mutate_during_last_scope_exit_hash(
                self.replace_earlier_member_with_identical_bytes) as observed:
            with self.assertRaises(RuntimeError):
                self.fixture._publish()
        self.assertTrue(observed, "the final scope-exit hash boundary was not reached")


if __name__ == "__main__":
    unittest.main()
