"""Scoped syntax/observation controls; no epoch authentication claim."""
import errno
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

from test_grant_record import grant, record


def scoped_record():
    return (b"sia-grant-v2\nboot=" + bytes(range(32)).hex().encode("ascii")
            + b"\nservice=" + bytes(range(32, 64)).hex().encode("ascii") + b"\n"
            + record().split(b"\n", 1)[1])


class ScopedRecord(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / grant.GRANT_NAME
        self.path.write_bytes(scoped_record())
        self.path.chmod(0o600)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, self.fd)

    def test_independent_domains_and_legacy_fields_preserved(self):
        observed = grant.load_scoped_record(self.fd)
        self.assertEqual(observed.boot, bytes(range(32)))
        self.assertEqual(observed.service, bytes(range(32, 64)))
        self.assertEqual((observed.grant.subject, observed.grant.not_before,
                          observed.grant.expires, observed.grant.active,
                          observed.grant.expected_frame), (1000, 10, 20, True, bytes(192)))

    def test_versions_cannot_be_silently_upgraded_or_downgraded(self):
        with self.assertRaises(grant.GrantRefusal):
            grant.load_record(self.fd)
        self.path.write_bytes(record())
        with self.assertRaises(grant.GrantRefusal):
            grant.load_scoped_record(self.fd)

    def test_malformed_domains_and_scalar_fields_refuse(self):
        base = scoped_record()
        malformed = [base.replace(b"boot=", b"service="), base.replace(b"service=", b"boot="),
                     base.replace(b"boot=0", b"boot=G"), base.replace(b"boot=00", b"boot=0"),
                     base.replace(b"boot=00", b"boot=000"), base.replace(b"\n", b"\r\n"),
                     base.replace(b"subject=1000", b"subject=01000"),
                     base.replace(b"active=1", b"active=2"), base + b"\n", base[:-1],
                     b"\xff" + base, b"x" * 1025]
        for raw in malformed:
            with self.subTest(raw=raw[:80]), self.assertRaises(grant.GrantRefusal):
                grant.parse_scoped_record(raw)

    def test_zero_domains_and_invalid_policy_interval_are_preserved(self):
        for field, value in (("boot", bytes(range(32))), ("service", bytes(range(32, 64)))):
            base = scoped_record().replace(value.hex().encode(), b"0" * 64)
            base = base.replace(b"active=1", b"active=0").replace(b"expires=20", b"expires=0")
            observed = grant.parse_scoped_record(base)
            self.assertEqual(getattr(observed, field), bytes(32))
            self.assertFalse(observed.grant.active)
            self.assertEqual(observed.grant.expires, 0)

    def test_scoped_loader_retains_file_safety_checks(self):
        self.path.chmod(0o644)
        with self.assertRaises(grant.GrantRefusal):
            grant.load_scoped_record(self.fd)
        self.path.unlink()
        self.path.symlink_to(self.root / "missing")
        with self.assertRaises(OSError):
            grant.load_scoped_record(self.fd)

    def test_close_uncertainty_prevents_either_loader_returning_a_record(self):
        original_close = os.close
        def failing_close(fd):
            original_close(fd)
            raise OSError(errno.EIO, "injected close uncertainty")
        shim = types.SimpleNamespace(**vars(os))
        shim.close = failing_close
        for loader, raw in ((grant.load_record, record()),
                            (grant.load_scoped_record, scoped_record())):
            self.path.write_bytes(raw)
            with mock.patch.object(grant, "os", shim), self.assertRaises(OSError):
                loader(self.fd)


if __name__ == "__main__":
    unittest.main()
