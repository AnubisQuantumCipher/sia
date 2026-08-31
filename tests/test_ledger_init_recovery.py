#!/usr/bin/env python3
"""Crash, corruption, and no-clobber tests for sia-ledger genesis."""

import contextlib
import importlib.machinery
import importlib.util
import io
import os
import stat
import tempfile
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "bin", "sia-ledger")
COMPONENTS = ("key.hex", "pub.hex", "ledger.tsv", "head.pin")


def _load_keeper():
    loader = importlib.machinery.SourceFileLoader(
        "sia_ledger_init_recovery", LEDGER)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


KEEPER = _load_keeper()


class LedgerInitRecovery(unittest.TestCase):
    def _call_init(self, state):
        with contextlib.redirect_stdout(io.StringIO()):
            return KEEPER.cmd_init(state)

    def _verify(self, state):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(KEEPER.cmd_verify(state, quiet=True), 0)

    def _crash_after(self, state, component):
        original = KEEPER._after_init_publication

        def injected(name):
            if name == component:
                raise OSError(f"injected crash after {name}")

        KEEPER._after_init_publication = injected
        try:
            with self.assertRaisesRegex(OSError, "injected crash"):
                self._call_init(state)
        finally:
            KEEPER._after_init_publication = original

    def _make_prior_prefix(self, state, target):
        position = COMPONENTS.index(target)
        if position:
            self._crash_after(state, COMPONENTS[position - 1])

    def _assert_no_later_components(self, state, target):
        position = COMPONENTS.index(target)
        for name in COMPONENTS[position + 1:]:
            self.assertFalse(os.path.lexists(os.path.join(state, name)), name)

    @staticmethod
    def _durable_new(path, data, mode):
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL \
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, mode)
        try:
            KEEPER._write_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        KEEPER._fsync_directory(os.path.dirname(path))

    @staticmethod
    def _durable_replace(path, data, mode):
        replacement = path + ".racing-writer"
        LedgerInitRecovery._durable_new(replacement, data, mode)
        os.replace(replacement, path)
        KEEPER._fsync_directory(os.path.dirname(path))

    def test_every_durable_prefix_resumes_without_clobber(self):
        for position, component in enumerate(COMPONENTS):
            with self.subTest(component=component), \
                    tempfile.TemporaryDirectory() as state:
                self._crash_after(state, component)
                for name in COMPONENTS[:position + 1]:
                    self.assertTrue(os.path.isfile(os.path.join(state, name)))
                self._assert_no_later_components(state, component)
                self.assertFalse(any(
                    ".stage" in name for name in os.listdir(state)))

                self.assertEqual(self._call_init(state), 0)
                self._verify(state)
                self.assertEqual(self._call_init(state), 0)

    def test_anonymous_stage_write_failure_leaves_no_authority_name(self):
        with tempfile.TemporaryDirectory() as state:
            original = KEEPER._write_all

            def interrupted(fd, data):
                os.write(fd, bytes(data[:1]))
                raise OSError("injected anonymous-stage interruption")

            KEEPER._write_all = interrupted
            try:
                with self.assertRaisesRegex(
                        OSError, "anonymous-stage interruption"):
                    self._call_init(state)
            finally:
                KEEPER._write_all = original
            self.assertEqual(os.listdir(state), ["ledger.lock"])
            self.assertEqual(self._call_init(state), 0)
            self._verify(state)

    def test_missing_anonymous_stage_support_refuses_by_name(self):
        with tempfile.TemporaryDirectory() as state:
            with mock.patch.object(KEEPER.os, "O_TMPFILE", 0):
                with self.assertRaisesRegex(
                        ValueError, "O_TMPFILE staging is unavailable"):
                    self._call_init(state)
            self.assertEqual(os.listdir(state), ["ledger.lock"])

    def test_visible_prefix_after_directory_sync_failure_is_resynced(self):
        for position, component in enumerate(COMPONENTS):
            with self.subTest(component=component), \
                    tempfile.TemporaryDirectory() as state:
                self._make_prior_prefix(state, component)
                original_link = KEEPER._link_fd_noreplace
                original_fsync = KEEPER.os.fsync
                linked = False
                failed = False

                def linked_publish(*args, **kwargs):
                    nonlocal linked
                    result = original_link(*args, **kwargs)
                    linked = True
                    return result

                def interrupted_fsync(fd):
                    nonlocal failed
                    if linked and not failed:
                        failed = True
                        raise OSError("injected directory fsync interruption")
                    return original_fsync(fd)

                KEEPER._link_fd_noreplace = linked_publish
                KEEPER.os.fsync = interrupted_fsync
                try:
                    with self.assertRaisesRegex(OSError, "fsync interruption"):
                        self._call_init(state)
                finally:
                    KEEPER.os.fsync = original_fsync
                    KEEPER._link_fd_noreplace = original_link
                self.assertTrue(os.path.isfile(os.path.join(state, component)))
                self._assert_no_later_components(state, component)

                original_sync_directory = KEEPER._fsync_directory
                original_publish = KEEPER._publish_new
                prefix_synced = False

                def observed_sync(path):
                    nonlocal prefix_synced
                    result = original_sync_directory(path)
                    if os.path.abspath(path) == os.path.abspath(state):
                        prefix_synced = True
                    return result

                def checked_publish(path, data, mode=0o644):
                    self.assertTrue(prefix_synced)
                    return original_publish(path, data, mode)

                KEEPER._fsync_directory = observed_sync
                KEEPER._publish_new = checked_publish
                try:
                    self.assertEqual(self._call_init(state), 0)
                finally:
                    KEEPER._publish_new = original_publish
                    KEEPER._fsync_directory = original_sync_directory
                self.assertTrue(prefix_synced)
                self._verify(state)

    def test_new_state_directory_is_parent_synced_before_key_publish(self):
        with tempfile.TemporaryDirectory() as parent:
            state = os.path.join(parent, "new-ledger-state")
            original_sync_directory = KEEPER._fsync_directory
            failed = False

            def interrupted_sync(path):
                nonlocal failed
                if os.path.abspath(path) == os.path.abspath(parent) \
                        and not failed:
                    failed = True
                    raise OSError("injected parent fsync interruption")
                return original_sync_directory(path)

            KEEPER._fsync_directory = interrupted_sync
            try:
                with self.assertRaisesRegex(OSError, "parent fsync"):
                    self._call_init(state)
            finally:
                KEEPER._fsync_directory = original_sync_directory
            self.assertTrue(os.path.isdir(state))
            self.assertEqual(os.listdir(state), [])

            parent_synced = False
            original_publish = KEEPER._publish_new

            def observed_sync(path):
                nonlocal parent_synced
                result = original_sync_directory(path)
                if os.path.abspath(path) == os.path.abspath(parent):
                    parent_synced = True
                return result

            def checked_publish(path, data, mode=0o644):
                self.assertTrue(parent_synced)
                return original_publish(path, data, mode)

            KEEPER._fsync_directory = observed_sync
            KEEPER._publish_new = checked_publish
            try:
                self.assertEqual(self._call_init(state), 0)
            finally:
                KEEPER._publish_new = original_publish
                KEEPER._fsync_directory = original_sync_directory
            self._verify(state)

    def test_writer_winning_before_publish_is_preserved(self):
        for component in COMPONENTS:
            with self.subTest(component=component), \
                    tempfile.TemporaryDirectory() as state:
                self._make_prior_prefix(state, component)
                target = os.path.join(state, component)
                foreign = b"concurrent writer bytes\n"
                mode = 0o600 if component == "key.hex" else 0o644
                original = KEEPER._publish_new
                raced = False

                def publish(path, data, publish_mode=0o644):
                    nonlocal raced
                    if path == target and not raced:
                        raced = True
                        self._durable_new(path, foreign, mode)
                    return original(path, data, publish_mode)

                KEEPER._publish_new = publish
                try:
                    with self.assertRaises(FileExistsError):
                        self._call_init(state)
                finally:
                    KEEPER._publish_new = original
                with open(target, "rb") as stream:
                    self.assertEqual(stream.read(), foreign)
                self._assert_no_later_components(state, component)

    def test_replacement_after_publish_is_detected_and_preserved(self):
        for component in COMPONENTS:
            with self.subTest(component=component), \
                    tempfile.TemporaryDirectory() as state:
                self._make_prior_prefix(state, component)
                target = os.path.join(state, component)
                foreign = b"replacement after publication\n"
                mode = 0o600 if component == "key.hex" else 0o644
                original = KEEPER._publish_new
                raced = False

                def publish(path, data, publish_mode=0o644):
                    nonlocal raced
                    result = original(path, data, publish_mode)
                    if path == target and not raced:
                        raced = True
                        self._durable_replace(path, foreign, mode)
                    return result

                KEEPER._publish_new = publish
                try:
                    with self.assertRaises((OSError, ValueError)):
                        self._call_init(state)
                finally:
                    KEEPER._publish_new = original
                with open(target, "rb") as stream:
                    self.assertEqual(stream.read(), foreign)
                self._assert_no_later_components(state, component)

    def test_nonprefix_names_and_pending_journal_refuse_without_adoption(self):
        for name in ("pub.hex", "ledger.tsv", "head.pin", "ledger.pending"):
            with self.subTest(name=name), \
                    tempfile.TemporaryDirectory() as state:
                path = os.path.join(state, name)
                self._durable_new(path, b"operator bytes\n", 0o644)
                with self.assertRaisesRegex(ValueError, "exact genesis prefix"):
                    self._call_init(state)
                with open(path, "rb") as stream:
                    self.assertEqual(stream.read(), b"operator bytes\n")
                self.assertFalse(os.path.lexists(
                    os.path.join(state, "key.hex")))

    def test_links_and_special_files_refuse_without_following(self):
        for component in COMPONENTS:
            for kind in ("symlink", "fifo"):
                with self.subTest(component=component, kind=kind), \
                        tempfile.TemporaryDirectory() as state:
                    self._make_prior_prefix(state, component)
                    target = os.path.join(state, component)
                    victim = os.path.join(state, "operator-file")
                    self._durable_new(victim, b"operator bytes\n", 0o600)
                    if kind == "symlink":
                        os.symlink(victim, target)
                    else:
                        os.mkfifo(target, 0o600)
                    with self.assertRaises((OSError, ValueError)):
                        self._call_init(state)
                    with open(victim, "rb") as stream:
                        self.assertEqual(stream.read(), b"operator bytes\n")
                    self.assertTrue(os.path.lexists(target))
                    self._assert_no_later_components(state, component)

    def test_private_key_owner_links_and_permissions_are_strict(self):
        with tempfile.TemporaryDirectory() as state:
            self._crash_after(state, "key.hex")
            key = os.path.join(state, "key.hex")
            os.chmod(key, 0o644)
            with self.assertRaisesRegex(ValueError, "permissions are unsafe"):
                self._call_init(state)
            self.assertFalse(os.path.lexists(os.path.join(state, "pub.hex")))

        with tempfile.TemporaryDirectory() as state:
            self._crash_after(state, "key.hex")
            key = os.path.join(state, "key.hex")
            alias = os.path.join(state, "operator-hardlink")
            os.link(key, alias)
            with self.assertRaisesRegex(ValueError, "unsafe link count"):
                self._call_init(state)
            self.assertFalse(os.path.lexists(os.path.join(state, "pub.hex")))

        with tempfile.TemporaryDirectory() as state:
            self._crash_after(state, "key.hex")
            # JACKAL exact: status=exact parsed=2^31 exact=2147483648;
            # not formal-bounded and no Lean-checked certificate.
            foreign_uid = 2_147_483_648
            with mock.patch.object(
                    KEEPER.os, "geteuid", return_value=foreign_uid):
                with self.assertRaisesRegex(ValueError, "not owned"):
                    KEEPER._cmd_init_locked(state)
            self.assertFalse(os.path.lexists(os.path.join(state, "pub.hex")))

    def test_mismatched_public_genesis_and_pin_bytes_are_never_adopted(self):
        with tempfile.TemporaryDirectory() as state:
            self._crash_after(state, "pub.hex")
            public_path = os.path.join(state, "pub.hex")
            replacement = KEEPER.Ed25519PrivateKey.generate() \
                .public_key().public_bytes_raw().hex().encode("ascii") + b"\n"
            self._durable_replace(public_path, replacement, 0o644)
            with self.assertRaisesRegex(ValueError, "DOES NOT MATCH"):
                self._call_init(state)
            with open(public_path, "rb") as stream:
                self.assertEqual(stream.read(), replacement)
            self.assertFalse(os.path.lexists(os.path.join(state, "ledger.tsv")))

        with tempfile.TemporaryDirectory() as state:
            self._crash_after(state, "ledger.tsv")
            ledger = os.path.join(state, "ledger.tsv")
            with open(ledger, "rb") as stream:
                genesis = stream.read()
            with open(ledger, "ab") as stream:
                stream.write(genesis)
                stream.flush()
                os.fsync(stream.fileno())
            with self.assertRaisesRegex(ValueError, "single genesis"):
                self._call_init(state)
            with open(ledger, "rb") as stream:
                self.assertEqual(stream.read(), genesis + genesis)
            self.assertFalse(os.path.lexists(os.path.join(state, "head.pin")))

        with tempfile.TemporaryDirectory() as state:
            self.assertEqual(self._call_init(state), 0)
            pin = os.path.join(state, "head.pin")
            replacement = b"1 " + b"0" * 64 + b"\n"
            self._durable_replace(pin, replacement, 0o644)
            with self.assertRaisesRegex(ValueError, "PIN MISMATCH"):
                self._call_init(state)
            with open(pin, "rb") as stream:
                self.assertEqual(stream.read(), replacement)

    def test_complete_extended_chain_remains_idempotent(self):
        with tempfile.TemporaryDirectory() as state:
            self.assertEqual(self._call_init(state), 0)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(KEEPER.cmd_append(
                    state, "TEST:extended", "a", "b", "0" * 64, 0), 0)
            self.assertEqual(self._call_init(state), 0)
            self._verify(state)


if __name__ == "__main__":
    unittest.main()
