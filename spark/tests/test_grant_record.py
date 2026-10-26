"""Real disposable file and malformed-input controls for grant observations."""
import importlib.util
import os
import errno
from pathlib import Path
import tempfile
import types
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("grant_record", ROOT / "transport/grant_record.py")
grant = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = grant
SPEC.loader.exec_module(grant)


def record():
    return ("sia-grant-v1\nsubject=1000\nnot-before=10\nexpires=20\nactive=1\nrequest="
            + bytes(192).hex() + "\n").encode("ascii")


class GrantRecordControls(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / grant.GRANT_NAME
        self.path.write_bytes(record())
        self.path.chmod(0o600)
        self.descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, self.descriptor)

    def test_exact_private_record_loads_without_authorizing_its_frame(self):
        observed = grant.load_record(self.descriptor)
        self.assertEqual(observed, grant.parse_record(record()))
        self.assertEqual(observed.expected_frame, bytes(192))  # syntax-invalid frame retained
        self.assertEqual(observed.subject, 1000)
        self.assertTrue(observed.active)
        self.assertEqual(self.path.read_bytes(), record())
        self.path.chmod(0o400)
        self.root.chmod(0o500)
        try:
            self.assertEqual(grant.load_record(self.descriptor), observed)
        finally:
            self.root.chmod(0o700)

    def test_flat_syntax_rejects_ambiguous_or_out_of_range_values(self):
        base = record()
        candidates = [b"", b"x" * 1025, base + b"\n", base[:-1],
                      base.replace(b"subject=1000", b"subject=01000"),
                      base.replace(b"subject=1000", b"subject=-1"),
                      base.replace(b"subject=1000", b"subject=4294967296"),
                      base.replace(b"expires=20", b"expires=9223372036854775808"),
                      base.replace(b"active=1", b"active=true"),
                      base.replace(b"not-before=", b"subject="),
                      base.replace(b"\n", b"\r\n"),
                      base.replace(b"request=0", b"request=G"), b"\xff" + base]
        for raw in candidates:
            with self.subTest(raw=raw[:64]), self.assertRaises(grant.GrantRefusal):
                grant.parse_record(raw)

    def test_parser_preserves_inactive_and_invalid_policy_interval(self):
        parsed = grant.parse_record(record().replace(b"active=1", b"active=0")
                                    .replace(b"expires=20", b"expires=0"))
        self.assertFalse(parsed.active)
        self.assertEqual(parsed.expires, 0)  # policy must deny; parser cannot authorize

    def test_independent_field_and_nonuniform_frame_oracle(self):
        frame = bytes(range(192))
        raw = record().replace(bytes(192).hex().encode("ascii"), frame.hex().encode("ascii"))
        self.path.write_bytes(raw)
        observed = grant.load_record(self.descriptor)
        self.assertEqual((observed.subject, observed.not_before, observed.expires,
                          observed.active, observed.expected_frame),
                         (1000, 10, 20, True, frame))

    def test_unsafe_permissions_and_hard_links_refuse(self):
        for mode in (0o640, 0o660, 0o644, 0o700):
            self.path.chmod(mode)
            with self.assertRaises(grant.GrantRefusal):
                grant.load_record(self.descriptor)
        self.path.chmod(0o600)
        self.root.chmod(0o750)
        with self.assertRaises(grant.GrantRefusal):
            grant.load_record(self.descriptor)
        self.root.chmod(0o700)
        os.link(self.path, self.root / "alias")
        with self.assertRaises(grant.GrantRefusal):
            grant.load_record(self.descriptor)

    def test_nonregular_missing_and_oversize_files_refuse(self):
        self.path.unlink()
        with self.assertRaises(OSError):
            grant.load_record(self.descriptor)
        self.path.symlink_to(self.root / "missing")
        with self.assertRaises(OSError):
            grant.load_record(self.descriptor)
        self.path.unlink()
        os.mkfifo(self.path, 0o600)
        with self.assertRaises(grant.GrantRefusal):
            grant.load_record(self.descriptor)
        self.path.unlink()
        self.path.write_bytes(b"x" * 1025)
        self.path.chmod(0o600)
        with self.assertRaises(grant.GrantRefusal):
            grant.load_record(self.descriptor)

    def test_changed_read_or_replaced_name_refuses(self):
        original_read = os.read
        for replace in (False, True):
            self.path.write_bytes(record())
            def racing_read(fd, count):
                raw = original_read(fd, count)
                if replace:
                    self.path.unlink()
                self.path.write_bytes(record() + b"x")
                return raw
            shim = types.SimpleNamespace(**vars(os))
            shim.read = racing_read
            with mock.patch.object(grant, "os", shim), self.assertRaises(grant.GrantRefusal):
                grant.load_record(self.descriptor)

    def test_foreign_owner_observation_refuses(self):
        original_fstat = os.fstat
        foreign = 1 if os.geteuid() == 0 else 0
        for target in ("directory", "file"):
            def fstat(fd):
                info = original_fstat(fd)
                if (fd == self.descriptor) == (target == "directory"):
                    return types.SimpleNamespace(st_mode=info.st_mode, st_uid=foreign)
                return info
            shim = types.SimpleNamespace(**vars(os))
            shim.fstat = fstat
            with mock.patch.object(grant, "os", shim), self.assertRaises(grant.GrantRefusal):
                grant.load_record(self.descriptor)

    def test_short_read_and_read_error_close_record_descriptor(self):
        original_open, original_read = os.open, os.read
        opened = []
        def opening(*args, **kwargs):
            fd = original_open(*args, **kwargs)
            opened.append(fd)
            return fd
        for mode in ("normal", "short", "error"):
            shim = types.SimpleNamespace(**vars(os))
            shim.open = opening
            def reading(fd, count):
                if mode == "error":
                    raise OSError(errno.EIO, "injected read failure")
                raw = original_read(fd, count)
                return raw[:-1] if mode == "short" else raw
            shim.read = reading
            with mock.patch.object(grant, "os", shim):
                if mode != "normal":
                    with self.assertRaises(grant.GrantRefusal if mode == "short" else OSError):
                        grant.load_record(self.descriptor)
                else:
                    self.assertEqual(grant.load_record(self.descriptor), grant.parse_record(record()))
            with self.assertRaises(OSError) as caught:
                os.fstat(opened[-1])
            self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_directory_generation_change_refuses(self):
        original_read = os.read
        def reading(fd, count):
            raw = original_read(fd, count)
            (self.root / "generation-change").write_bytes(b"fixture")
            return raw
        shim = types.SimpleNamespace(**vars(os))
        shim.read = reading
        with mock.patch.object(grant, "os", shim), \
                self.assertRaisesRegex(grant.GrantRefusal, "grant-binding-changed"):
            grant.load_record(self.descriptor)

    def test_current_name_mismatch_refuses_independently_of_held_file(self):
        # Synthetic name observation isolates this branch: an actual unlink
        # also changes the held inode's link count and can fail earlier.
        other = self.root / "other"
        other.write_bytes(record())
        other.chmod(0o600)
        foreign = other.stat()
        shim = types.SimpleNamespace(**vars(os))
        shim.stat = lambda *args, **kwargs: foreign
        with mock.patch.object(grant, "os", shim), \
                self.assertRaisesRegex(grant.GrantRefusal, "grant-binding-changed"):
            grant.load_record(self.descriptor)


if __name__ == "__main__":
    unittest.main()
