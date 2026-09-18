"""Real ACK acquisition lifetime, not a process-wide leak attribution.

These tests compose existing actual source/effects/ACK fixtures.
Only successful _HeldRaw construction is observed: real storage, native
descriptors, ancestor ownership, refusal checks and publication remain intact.
No live data is used.
"""

import contextlib
import errno
import os
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_controller_source_ack as ack_tests


def native_identity(info):
    """Native stable ownership identity, not content/mtime equivalence."""
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


class ControllerSourceAckDescriptorLifetime(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self, *, journal=False):
        case = ack_tests.ControllerSourceAcknowledgment(methodName="runTest")
        try:
            case.setUp()
            if journal:
                case.start_journal()
            else:
                case.start_empty()
            yield case
        finally:
            case.doCleanups()

    @contextlib.contextmanager
    def caller_leases(self, case):
        # ACK must neither close these independently owned descriptors nor
        # change the caller's reentrant ownership context on success/refusal.
        with case.lib.brainstem_owner() as brainstem_fd, \
                case.lib.corpus_owner() as corpus_fd:
            before = {
                "brainstem": (brainstem_fd, native_identity(os.fstat(brainstem_fd))),
                "corpus": (corpus_fd, native_identity(os.fstat(corpus_fd))),
            }
            depth = case.lib._CORPUS_OWNER_DEPTH.get()
            try:
                yield before
            finally:
                self.assertEqual(case.lib._CORPUS_OWNER_DEPTH.get(), depth)
                self.assertEqual(case.lib._CORPUS_OWNER_FD.get(), corpus_fd)
                self.assertEqual(case.lib._BRAINSTEM_OWNER_FD.get(), brainstem_fd)
                for descriptor, identity in before.values():
                    self.assertEqual(native_identity(os.fstat(descriptor)), identity)

    @contextlib.contextmanager
    def observe_acquisitions(self, *, caller_leases):
        import siasourceack as ack

        original = ack._HeldRaw.__init__
        acquisitions = []
        caller_descriptors = {descriptor for descriptor, _identity
                              in caller_leases.values()}

        def construct(held, *args, **kwargs):
            original(held, *args, **kwargs)
            # Observe only AFTER the actual constructor accepted the file or
            # exact absence. No object, descriptor or success is fabricated.
            slots = []
            if held.fd is not None:
                slots.append(("file", held.fd,
                              native_identity(os.fstat(held.fd))))
            directories = held.directories
            for name, descriptor, _admitted_identity in directories.chain:
                slots.append(("ancestor:" + name, descriptor,
                              native_identity(os.fstat(descriptor))))
            acquisitions.append({"held": held, "path": held.path,
                                 "directories": directories, "slots": slots})
            for _kind, descriptor, _identity in slots:
                self.assertNotIn(descriptor, caller_descriptors)

        try:
            with mock.patch.object(ack._HeldRaw, "__init__", construct):
                yield acquisitions
        finally:
            # RED must not itself leave the real leaked fixture FDs behind.
            # Close only still-owned slots from successful acquisitions. A
            # closed object's old FD number may have been reused, so object
            # ownership AND the saved native identity must both agree first.
            for row in reversed(acquisitions):
                held = row["held"]
                directories = row["directories"]
                referenced = set()
                if held.fd is not None:
                    referenced.add(held.fd)
                if held.directories is directories:
                    referenced.update(descriptor for _name, descriptor, _identity
                                      in directories.chain)
                for _kind, descriptor, identity in reversed(row["slots"]):
                    if descriptor not in referenced or descriptor in caller_descriptors:
                        continue
                    try:
                        current = os.fstat(descriptor)
                    except OSError as exc:
                        if exc.errno == errno.EBADF:
                            continue
                        raise
                    if native_identity(current) != identity:
                        raise AssertionError(
                            "test cleanup refused a changed descriptor identity: " + row["path"])
                    os.close(descriptor)
                # No destructor exists on these storage holders. Make their
                # already-released state explicit so cleanup cannot close a
                # reused descriptor through a retained observer object.
                if held.fd in referenced:
                    held.fd = None
                if held.directories is directories:
                    directories.chain = []
                    held.directories = None

    def assert_closed(self, acquisitions, *, required_paths):
        self.assertTrue(acquisitions, "ACK never reached real _HeldRaw acquisition")
        observed_paths = {row["path"] for row in acquisitions}
        self.assertTrue(set(map(str, required_paths)) <= observed_paths,
                        "ACK did not acquire every required real cursor")
        failures = []
        for row in acquisitions:
            held = row["held"]
            if held.fd is not None or held.directories is not None \
                    or row["directories"].chain:
                failures.append((row["path"], "holder-not-closed"))
            for kind, descriptor, identity in row["slots"]:
                try:
                    current = os.fstat(descriptor)
                except OSError as exc:
                    self.assertEqual(exc.errno, errno.EBADF)
                    continue
                # FD-number reuse alone is not evidence of a leak. Any same
                # native object left open is still an acquisition failure;
                # all ACK-owned holders must have exited before this point.
                if native_identity(current) == identity:
                    failures.append((row["path"], kind, "native-slot-still-open"))
        self.assertEqual(failures, [], "ACK leaked real cursor/ancestor acquisitions")

    def refuse_without_effect(self, case):
        reasons = []

        def acknowledge():
            try:
                return case.acknowledge()
            except ack_tests.REFUSALS as exc:
                reasons.append(getattr(exc, "reason", None))
                raise

        # Preserve the existing real image/memo and forbidden-effect checks;
        # descriptor assertions supplement them rather than replacing them.
        case.assert_refused_without_effect(acknowledge)
        self.assertEqual(reasons, ["ack-cursor-third-state"])

    def test_main_constructor_refusal_closes_cursor_and_native_ancestors(self):
        with self.fixture() as case:
            cursor = case.source.cursors_path
            cursor.write_bytes(b'{"foreign":true}')
            cursor.chmod(0o600)
            with self.caller_leases(case) as leases, \
                    self.observe_acquisitions(caller_leases=leases) as acquired:
                self.refuse_without_effect(case)
                self.assert_closed(acquired, required_paths=[cursor])

    def test_later_user_refusal_closes_earlier_sys_and_failed_user_acquisitions(self):
        with self.fixture(journal=True) as case:
            system_cursor = case.source_state / "journal-sys.cursor"
            user_cursor = case.source_state / "journal-user.cursor"
            system_before = system_cursor.read_bytes()
            user_cursor.write_bytes(b"foreign-user-cursor")
            user_cursor.chmod(0o600)
            with self.caller_leases(case) as leases, \
                    self.observe_acquisitions(caller_leases=leases) as acquired:
                self.refuse_without_effect(case)
                self.assertEqual(system_cursor.read_bytes(), system_before)
                self.assertEqual(user_cursor.read_bytes(), b"foreign-user-cursor")
                self.assert_closed(acquired, required_paths=[
                    case.source.cursors_path, system_cursor, user_cursor])

    def test_successful_actual_journal_ack_closes_all_acquisitions_not_caller_leases(self):
        with self.fixture(journal=True) as case:
            with self.caller_leases(case) as leases, \
                    self.observe_acquisitions(caller_leases=leases) as acquired:
                self.assertIsNone(case.acknowledge())
                self.assert_closed(acquired, required_paths=[
                    case.source.cursors_path,
                    case.source_state / "journal-sys.cursor",
                    case.source_state / "journal-user.cursor"])
                case.assert_final()


if __name__ == "__main__":
    unittest.main()
