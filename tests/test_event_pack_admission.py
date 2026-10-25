"""Compiled captured-stream correspondence; no authentication or effect authority."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests import test_event_pack_proposal as source


def row(identifier):
    return identifier.to_bytes(32, "big") + bytes(range(32)) + (1).to_bytes(8, "big")


def manifest(rows):
    return b"SIA-PACK-RECORDS-v1\0" + len(rows).to_bytes(8, "big") + b"".join(rows)


def synthetic(selected_count, represented_count, *, overlap=False):
    """Independent literal frame layout; selected identities are increasing."""
    rows = tuple(row(index) for index in range(1, selected_count + 1))
    represented = rows[:represented_count]
    prior = (rows[0],) if overlap else (row(0),) if not represented else ()
    target = prior if prior else represented
    frame = bytearray(16384)
    frame[0] = 1
    frame[40:48] = (1).to_bytes(8, "big")
    frame[400:408] = (3).to_bytes(8, "big")
    frame[408:416] = selected_count.to_bytes(8, "big")
    frame[416:424] = (selected_count - represented_count).to_bytes(8, "big")
    for offset, roster in ((424, prior), (5040, target), (9656, represented)):
        frame[offset:offset + 8] = len(roster).to_bytes(8, "big")
        frame[offset + 8:offset + 8 + len(roster) * 72] = b"".join(roster)
    frame[14272:14272 + represented_count] = b"\1" * represented_count
    frame[8:40] = hashlib.sha256(
        b"SIA-PACK-PLAN-BINDING-v1\0" + frame[:8] + frame[40:]).digest()
    return bytes(frame), manifest(rows), manifest(rows[represented_count:])


def changed(data, offset, value):
    result = bytearray(data)
    result[offset] = value
    return bytes(result)


@unittest.skipUnless(os.environ.get("SIA_PACK_PROPOSAL_PROBE"),
                     "compiled full-stream adapter UNRUN; no integration evidence")
class CapturedAdmission(unittest.TestCase):
    def setUp(self):
        self.fixture = source.CapturedProposal(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()

    def native(self, proposal, selected, fallback):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("proposal", "selected", "fallback")]
            for path, data in zip(paths, (proposal, selected, fallback), strict=True):
                self.assertEqual(path.write_bytes(data), len(data))
            result = subprocess.run([os.environ["SIA_PACK_PROPOSAL_PROBE"],
                                     *(str(path) for path in paths)],
                                    capture_output=True, timeout=5, check=False)
            self.assertEqual(tuple(path.read_bytes() for path in paths),
                             (proposal, selected, fallback))
            return result

    def require(self, value, accepted=True):
        frame, selected, fallback = value[:3]
        result = self.native(frame, selected, fallback)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b"")
        expected = b"ACCEPTED\n" + frame.hex().encode() + b"\n" if accepted else b"REFUSED\n"
        self.assertEqual(result.stdout, expected)

    def test_captured_legacy_plan_and_original_files(self):
        result = self.fixture.prepare()
        self.fixture.expected_legacy_frame(result)
        self.require(result)
        original = self.fixture.fixture.fixture
        self.assertFalse(original.pack.exists())
        self.assertEqual(original.legacy.read_bytes(), original.raw)

    def test_captured_pack_only_and_full_prior_fallback(self):
        original = self.fixture.fixture.fixture
        original._write_pack()
        original.legacy.unlink()
        self.fixture.capture = self.fixture.fixture._capture()
        self.require(self.fixture.prepare())
        original.legacy.write_bytes(original.raw)
        original._alternate_roster(64)
        prior = original.pack.read_bytes()
        self.fixture.capture = self.fixture.fixture._capture()
        self.require(self.fixture.prepare())
        self.assertEqual(original.pack.read_bytes(), prior)
        self.assertEqual(original.legacy.read_bytes(), original.raw)

    def test_every_manifest_header_truncation_and_bad_tag(self):
        frame, selected, fallback = self.fixture.prepare()[:3]
        for length in range(28):
            with self.subTest(stream="selected", length=length):
                self.require((frame, selected[:length], fallback), False)
            with self.subTest(stream="fallback", length=length):
                self.require((frame, selected, fallback[:length]), False)
        for index in range(20):
            self.require((frame, changed(selected, index, selected[index] ^ 1), fallback), False)
            self.require((frame, selected, changed(fallback, index, fallback[index] ^ 1)), False)

    def test_actual_trailing_bytes_and_declared_counts(self):
        frame, selected, fallback = self.fixture.prepare()[:3]
        for suffix in (b"\0", row(42)):
            self.require((frame, selected + suffix, fallback), False)
            self.require((frame, selected, fallback + suffix), False)
        for count in (0, 2, 65536, 65537, 2**63, 2**64 - 1):
            self.require((frame, selected[:20] + count.to_bytes(8, "big") + selected[28:], fallback), False)
        self.require((frame, selected, fallback[:20] + (1).to_bytes(8, "big")), False)

    def test_all_record_truncations_and_semantic_bytes(self):
        for represented in (0, 1):
            frame, selected, fallback = synthetic(1, represented)
            self.require((frame, selected, fallback))
            for length in range(72):
                self.require((frame, selected[:28 + length], fallback), False)
                if not represented:
                    self.require((frame, selected, fallback[:28 + length]), False)
            for offset in range(72):
                self.require((frame, changed(selected, 28 + offset, selected[28 + offset] ^ 1), fallback), False)
                if not represented:
                    self.require((frame, selected, changed(fallback, 28 + offset, fallback[28 + offset] ^ 1)), False)

    def test_duplicate_reordered_and_coherently_wrong_records(self):
        frame, selected, fallback = synthetic(3, 1)
        self.require((frame, selected, fallback))
        selected_rows = [selected[28 + index * 72:100 + index * 72] for index in range(3)]
        for rows in ((selected_rows[0], selected_rows[0], selected_rows[2]),
                     (selected_rows[1], selected_rows[0], selected_rows[2])):
            self.require((frame, manifest(rows), fallback), False)
        self.require((frame, selected, manifest((selected_rows[2], selected_rows[1]))), False)
        self.require(synthetic(1, 0, overlap=True), False)
        frame, selected, _fallback = synthetic(1, 0, overlap=True)
        other = changed(selected, 60, selected[60] ^ 1)
        self.require((frame, other, other), False)

    def test_interleaved_partition_and_payload_length_boundaries(self):
        frame, _selected, _fallback = synthetic(5, 3)
        represented = b"".join(row(index) for index in (1, 3, 5))
        candidate = bytearray(frame)
        for offset in (5048, 9664):
            candidate[offset:offset + len(represented)] = represented
        candidate[8:40] = source.wire.identity(bytes(candidate))
        self.require((bytes(candidate), manifest(tuple(row(i) for i in range(1, 6))),
                      manifest((row(2), row(4)))))
        frame, selected, _fallback = synthetic(1, 0)
        for length in (0, 65536, 65537, 2**64 - 1):
            stream = selected[:-8] + length.to_bytes(8, "big")
            self.require((frame, stream, stream), length == 65536)

    def test_invalid_frame_and_failed_manifest_open_never_succeed(self):
        frame, selected, fallback = self.fixture.prepare()[:3]
        self.require((changed(frame, 0, 2), selected, fallback), False)
        for invalid in (frame[:-1], frame + b"\0"):
            result = self.native(invalid, selected, fallback)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "proposal"
            self.assertEqual(path.write_bytes(frame), len(frame))
            missing = str(Path(directory) / "absent")
            for arguments in ((missing, missing), (str(path), missing)):
                result = subprocess.run([os.environ["SIA_PACK_PROPOSAL_PROBE"], str(path),
                                         *arguments], capture_output=True, timeout=5, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")

    def test_no_claim_of_digest_or_source_authentication(self):
        frame, selected, fallback = synthetic(2, 0)
        self.require((frame, selected, fallback))
        self.require((changed(frame, 8, frame[8] ^ 1), selected, fallback))
        other = changed(selected, 60, selected[60] ^ 1)
        self.require((frame, other, other))  # Matching opaque hashes are not source evidence.

    def test_empty_selection_and_full_selected_bound(self):
        self.require(synthetic(0, 0))
        self.require(synthetic(65536, 0))

    def test_full_roster_and_selected_bounds_together(self):
        self.require(synthetic(65536, 64))


if __name__ == "__main__":
    unittest.main()
