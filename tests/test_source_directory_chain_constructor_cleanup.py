"""Regression for the directory-chain constructor's unregistered FD.

Only temporary fixture directories are opened. The injected failure occurs
after a real open and real fstat, before the constructor receives that stat
result and registers its descriptor for cleanup. This reaches both the root
open and a descriptor-relative child open without mocking ownership checks.

Caller-owned regular and directory descriptors must remain open and unchanged.
Each case also compares the full observed descriptor roster. A final recovery
closes only still-open descriptors created by this constructor attempt, so a
failing RED run cannot leak its deliberately exposed descriptor into later
tests. No live source, corpus, journal, acquisition lease or writer is used.
"""

import contextlib
import errno
import os
from pathlib import Path
import sys
import tempfile
import unittest


try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

import siasourcebatch as source


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def _descriptors():
    """Observe live descriptors, excluding the retired /proc scan descriptor."""
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
        result[descriptor] = (_identity(info), target,
                              os.get_inheritable(descriptor))
    return result


class _ConstructorInterrupted(KeyboardInterrupt):
    pass


class _OpeningSystem:
    """Delegate real operations; interrupt one newly opened FD's first stat."""

    def __init__(self, *, site, child_parent, child_leaf, failure):
        self.site = site
        self.child_parent = child_parent
        self.child_leaf = child_leaf
        self.failure = failure
        self.target_fd = None
        self.injected = False
        self.opened = []
        self.closed = []

    def __getattr__(self, name):
        return getattr(os, name)

    def open(self, path, flags, *args, **kwargs):
        descriptor = os.open(path, flags, *args, **kwargs)
        observed = os.fstat(descriptor)
        self.opened.append((descriptor, _identity(observed)))
        root_open = path == os.sep and "dir_fd" not in kwargs
        child_open = (
            path == self.child_leaf and "dir_fd" in kwargs
            and _identity(os.fstat(kwargs["dir_fd"])) == self.child_parent
        )
        if ((self.site == "root" and root_open)
                or (self.site == "child" and child_open)):
            self.target_fd = descriptor
        return descriptor

    def fstat(self, descriptor):
        observed = os.fstat(descriptor)
        if descriptor == self.target_fd and not self.injected:
            self.injected = True
            raise self.failure
        return observed

    def close(self, descriptor):
        self.closed.append(descriptor)
        os.close(descriptor)

    def recover_test_leaks(self):
        # Never sweep arbitrary descriptors or close the caller's handles.
        # This also avoids closing a reused number with a different identity.
        for descriptor, expected in reversed(self.opened):
            try:
                actual = os.fstat(descriptor)
            except OSError as exc:
                if exc.errno != errno.EBADF:
                    raise
                continue
            if _identity(actual) == expected:
                os.close(descriptor)


class SourceDirectoryChainConstructorCleanup(unittest.TestCase):
    def test_failed_stat_retires_every_opened_fd_and_preserves_caller_fds(self):
        with tempfile.TemporaryDirectory(prefix="sia-chain-constructor-") as root:
            directory = Path(root) / "child"
            directory.mkdir(mode=0o700)
            directory_fd = os.open(
                root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                regular_fd = os.open(
                    Path(root) / "caller-owned", os.O_RDONLY | os.O_CREAT
                    | os.O_EXCL | os.O_CLOEXEC, 0o600)
                try:
                    caller = {
                        descriptor: (_identity(os.fstat(descriptor)),
                                     os.get_inheritable(descriptor))
                        for descriptor in (directory_fd, regular_fd)
                    }
                    parent_identity = _identity(os.fstat(directory_fd))
                    for site in ("root", "child"):
                        for failure_type in (OSError, _ConstructorInterrupted):
                            with self.subTest(site=site, failure=failure_type.__name__):
                                failure = (OSError(errno.EIO, "injected constructor stat failure")
                                           if failure_type is OSError else
                                           _ConstructorInterrupted("injected constructor interruption"))
                                system = _OpeningSystem(
                                    site=site, child_parent=parent_identity,
                                    child_leaf=directory.name, failure=failure)
                                # Capacity copied from the reviewed core contract;
                                # descriptor identities are observed fixture values.
                                owner = {"os": system, "MAX_CONFIG_PATH_CHARS": 4096}
                                before = _descriptors()
                                try:
                                    with self.assertRaises(failure_type) as caught:
                                        with contextlib.closing(source._DirectoryChain(
                                                owner, str(directory))):
                                            self.fail("interrupted constructor entered")
                                    self.assertIs(caught.exception, failure,
                                                  "cleanup replaced the original exception")
                                    self.assertTrue(system.injected,
                                                    "target constructor boundary was not reached")
                                    self.assertIsNotNone(system.target_fd)
                                    for descriptor, expected in caller.items():
                                        self.assertNotIn(descriptor, system.closed)
                                        self.assertEqual(
                                            (_identity(os.fstat(descriptor)),
                                             os.get_inheritable(descriptor)), expected)
                                    self.assertEqual(
                                        _descriptors(), before,
                                        "constructor left an unregistered descriptor open")
                                finally:
                                    system.recover_test_leaks()
                finally:
                    os.close(regular_fd)
            finally:
                os.close(directory_fd)


if __name__ == "__main__":
    unittest.main()
