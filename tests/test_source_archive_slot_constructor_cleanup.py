"""Regression for archive-slot cleanup when decoding does not return.

The private archive has deliberately unadmitted fixture bytes. Only decoding
is replaced to inject an explicit refusal or interruption after a real held
file and its real directory chain have been acquired and checked. Neither
the file name nor its body is claimed to be an admitted source transaction.

The complete observed descriptor roster and independently caller-owned file
and directory handles must survive unchanged. The test retains the actual
held object solely to clean an expected RED leak before the next case. No
full ACK fixture, live corpus, source capture, writer or clock is involved.
"""

import contextlib
import errno
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

import siasourceack as acknowledgment
import siasourcebatch as source


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def _descriptors():
    result = {}
    for leaf in os.listdir("/proc/self/fd"):
        descriptor = int(leaf)
        try:
            info = os.fstat(descriptor)
            target = os.readlink("/proc/self/fd/" + leaf)
            inheritable = os.get_inheritable(descriptor)
        except OSError as exc:
            if exc.errno not in (errno.EBADF, errno.ENOENT):
                raise
            continue
        result[descriptor] = (_identity(info), target, inheritable)
    return result


class _DecodeInterrupted(KeyboardInterrupt):
    pass


class SourceArchiveSlotConstructorCleanup(unittest.TestCase):
    def test_decode_failure_retires_real_hold_and_preserves_caller_descriptors(self):
        with tempfile.TemporaryDirectory(prefix="sia-archive-slot-cleanup-") as root:
            root = Path(root)
            archive = root / "archive"
            archive.mkdir(mode=0o700)
            source_path = root / "unoccupied-source-slot.json"
            # A syntactically digest-shaped fixture name, not an admitted pin.
            expected = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            selected = archive / (expected + ".json")
            raw = b'{"fixture":"unadmitted archive body"}'
            selected.write_bytes(raw)
            selected.chmod(0o600)
            owner = {
                "os": os,
                "MAX_CONFIG_PATH_CHARS": 4096,
                "MAX_STATE_JSON_BYTES": len(raw),
                "CONTROLLER_SOURCE_BATCH_PATH": str(source_path),
                "CONTROLLER_SOURCE_ARCHIVE_DIR": str(archive),
            }
            directory_fd = os.open(
                root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                regular_fd = os.open(
                    root / "caller-owned", os.O_RDONLY | os.O_CREAT
                    | os.O_EXCL | os.O_CLOEXEC, 0o600)
                try:
                    caller = {
                        descriptor: (_identity(os.fstat(descriptor)),
                                     os.get_inheritable(descriptor))
                        for descriptor in (directory_fd, regular_fd)
                    }
                    failures = (
                        source.SourceBatchRefusal("injected-archive-decode", phase="ack"),
                        _DecodeInterrupted("injected archive decode interruption"),
                    )
                    real_hold = acknowledgment._HeldRaw
                    for failure in failures:
                        with self.subTest(failure=type(failure).__name__):
                            acquired = []
                            decoded_while_held = []

                            def capture_real_hold(*args, **kwargs):
                                held = real_hold(*args, **kwargs)
                                acquired.append(held)
                                return held

                            def interrupt_decode(actual_owner, actual_source,
                                                 actual_raw, actual_expected,
                                                 *, checkpoint=False):
                                self.assertIs(actual_owner, owner)
                                self.assertIs(actual_source, source)
                                self.assertEqual(actual_raw, raw)
                                self.assertEqual(actual_expected, expected)
                                # _ArchiveSlot forwards its own decoder
                                # selection; this slot is built without one,
                                # so the legacy decoder must be the one asked
                                # for. Accepting the argument silently would
                                # let a compact decoder slip through here.
                                self.assertIs(checkpoint, False)
                                self.assertTrue(acquired,
                                                "decode ran without a completed real hold")
                                held = acquired[-1]
                                held.current()
                                self.assertEqual(held.path, str(selected))
                                roster = _descriptors()
                                self.assertIn(held.fd, roster)
                                self.assertEqual(roster[held.fd][1], str(selected))
                                self.assertTrue(held.directories.chain)
                                for _name, descriptor, original in held.directories.chain:
                                    self.assertIn(descriptor, roster)
                                    self.assertEqual(_identity(os.fstat(descriptor)), original)
                                    self.assertNotIn(descriptor, caller)
                                self.assertNotIn(held.fd, caller)
                                decoded_while_held.append(True)
                                raise failure

                            before = _descriptors()
                            try:
                                with mock.patch.object(
                                        acknowledgment, "_HeldRaw", side_effect=capture_real_hold) as constructor, \
                                        mock.patch.object(
                                            acknowledgment, "_decode_batch", side_effect=interrupt_decode) as decode:
                                    with self.assertRaises(type(failure)) as caught:
                                        with contextlib.closing(acknowledgment._ArchiveSlot(
                                                owner, source, expected, archive_only=True)):
                                            self.fail("failed archive decode entered its caller")
                                self.assertIs(caught.exception, failure,
                                              "constructor cleanup replaced the decode exception")
                                constructor.assert_called_once_with(
                                    owner, source, str(selected), len(raw), allow_absent=False)
                                decode.assert_called_once_with(
                                    owner, source, raw, expected, checkpoint=False)
                                self.assertTrue(decoded_while_held)
                                for descriptor, identity in caller.items():
                                    self.assertEqual(
                                        (_identity(os.fstat(descriptor)),
                                         os.get_inheritable(descriptor)), identity)
                                self.assertFalse(source_path.exists())
                                self.assertEqual(selected.read_bytes(), raw)
                                self.assertEqual(
                                    _descriptors(), before,
                                    "failed archive decode leaked its file or parent-chain descriptors")
                            finally:
                                # Operate only on objects actually returned by the
                                # real hold constructor, never on a global FD sweep.
                                for held in reversed(acquired):
                                    held.close()
                finally:
                    os.close(regular_fd)
            finally:
                os.close(directory_fd)


if __name__ == "__main__":
    unittest.main()
