"""Linux retained-source admission and exact historical recovery controls."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


BIN = Path(__file__).resolve().parents[1] / "bin"
REL = "events/org/2026-01-05.md"
ORIGINAL = b"Retained evidence with exact bytes\n"
WORKER = """
import contextlib, json, os, sys
from unittest import mock
sys.path.insert(0, sys.argv[1])
import sialib
sialib.CORPUS = sys.argv[2]
request = json.loads(sys.argv[3])
fault = request.get('fault')
error = KeyboardInterrupt if request.get('interrupt') else OSError
patch = (mock.patch.object(sialib.siaqueue.os, 'fstat', side_effect=error('fault'))
         if fault == 'fstat' else
         mock.patch.object(sialib.siaqueue.os, 'fdopen', side_effect=error('fault'))
         if fault == 'fdopen' else contextlib.nullcontext())
before = len(os.listdir('/proc/self/fd'))
results = []
with patch:
    for _ in range(request.get('repeat', 16)):
        try:
            text = sialib._retained_source_text(
                request['rel'], request['digest'], 'epochs/org/fixture')
        except (ValueError, OSError, KeyboardInterrupt) as exc:
            results.append({'error': type(exc).__name__, 'message': str(exc)})
        else:
            results.append({'text': text})
print(json.dumps({'results': results, 'before': before,
                  'after': len(os.listdir('/proc/self/fd'))}))
"""


class RetainedSourceAdmission(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.corpus = self.root / "corpus"
        self.page = self.corpus / REL
        self.page.parent.mkdir(parents=True)
        self.home = self.root / "home"
        self.home.mkdir()
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith("GIT_")}
        self.environment["HOME"] = str(self.home)
        self.digest = self.lineage(ORIGINAL)
        self.git("init", "-q")

    def lineage(self, raw):
        return hashlib.sha256(REL.encode() + b"\0" + raw).hexdigest()

    def git(self, *arguments):
        result = subprocess.run(
            ["git", "-C", str(self.corpus), "-c", "user.name=fixture",
             "-c", "user.email=fixture@example.invalid", *arguments],
            env=self.environment, capture_output=True, timeout=5, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def retain(self):
        self.page.write_bytes(ORIGINAL)
        self.git("add", "--", REL)
        self.git("commit", "-qm", "retained source fixture")

    def read(self, *, expected=None, **options):
        request = dict(rel=REL, digest=self.digest, **options)
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-W", "error::ResourceWarning", "-c",
             WORKER, str(BIN), str(self.corpus), json.dumps(request)],
            env=self.environment, capture_output=True, text=True,
            timeout=5, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        report = json.loads(result.stdout)
        self.assertEqual(report["before"], report["after"])
        self.assertEqual(len(report["results"]), request.get("repeat", 16))
        for item in report["results"]:
            if expected is None:
                self.assertEqual(item, {"text": ORIGINAL.decode()})
            else:
                self.assertEqual(item["error"], expected)
        return report["results"]

    def test_exact_regular_source_preserves_bytes(self):
        self.page.write_bytes(ORIGINAL)
        self.read()

    def test_live_crlf_source_is_not_normalized(self):
        raw = b"Live evidence with CRLF\r\n"
        self.page.write_bytes(raw)
        self.digest = self.lineage(raw)
        # Assert the returned bytes separately from the shared LF fixture.
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", WORKER, str(BIN),
             str(self.corpus), json.dumps(dict(rel=REL, digest=self.digest))],
            env=self.environment, capture_output=True, text=True,
            timeout=5, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["before"], report["after"])
        self.assertEqual(report["results"], [{"text": raw.decode()}] * 16)

    def test_fifo_without_writer_refuses_without_waiting(self):
        os.mkfifo(self.page, 0o600)
        result = self.read(expected="ValueError")
        self.assertIn("not a regular file", result[0]["message"])

    def test_fifo_peer_is_not_consumed_even_with_matching_history(self):
        self.retain()
        self.page.unlink()
        os.mkfifo(self.page, 0o600)
        peer = os.open(self.page, os.O_RDWR | os.O_NONBLOCK)
        self.addCleanup(os.close, peer)
        self.assertEqual(os.write(peer, ORIGINAL), len(ORIGINAL))
        self.read(expected="ValueError")
        self.assertEqual(os.read(peer, len(ORIGINAL)), ORIGINAL)

    def test_directory_refuses_without_descriptor_leak(self):
        self.page.mkdir()
        self.read(expected="ValueError")

    def test_symlink_cannot_supply_matching_bytes(self):
        outside = self.root / "outside.md"
        outside.write_bytes(ORIGINAL)
        self.page.symlink_to(outside)
        self.read(expected="OSError")

    def test_fstat_and_fdopen_failures_close_owned_descriptor(self):
        self.page.write_bytes(ORIGINAL)
        for fault in ("fstat", "fdopen"):
            for interrupt in (False, True):
                with self.subTest(fault=fault, interrupt=interrupt):
                    self.read(expected="KeyboardInterrupt" if interrupt else
                              "OSError", fault=fault, interrupt=interrupt)

    def test_missing_source_recovers_exact_history(self):
        self.retain()
        self.page.unlink()
        self.read(repeat=1)

    def test_changed_source_recovers_exact_history(self):
        self.retain()
        self.page.write_bytes(b"Changed evidence\n")
        self.read(repeat=1)

    def test_oversized_source_recovers_exact_history(self):
        self.retain()
        # The production page bound is one MiB; avoid allocating that payload.
        with self.page.open("wb") as stream:
            stream.truncate(1_048_577)
        self.read(repeat=1)

    def test_nondirectory_parent_recovers_exact_history(self):
        self.retain()
        self.page.unlink()
        self.page.parent.rmdir()
        self.page.parent.write_bytes(b"parent replaced")
        self.read(repeat=1)

    def test_unretained_digest_refuses_without_guessing(self):
        self.retain()
        self.digest = "f" * 64
        result = self.read(expected="ValueError", repeat=1)
        self.assertIn("in neither", result[0]["message"])

    def test_matching_invalid_utf8_refuses(self):
        raw = b"invalid utf8: \xff"
        self.page.write_bytes(raw)
        self.digest = self.lineage(raw)
        self.read(expected="UnicodeDecodeError")

    def test_malformed_digest_refuses_before_fifo_open(self):
        os.mkfifo(self.page, 0o600)
        self.digest = "not-a-digest"
        result = self.read(expected="ValueError")
        self.assertIn("malformed", result[0]["message"])


if __name__ == "__main__":
    unittest.main()
