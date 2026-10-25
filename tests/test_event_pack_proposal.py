"""Captured proposal correspondence; no installed or protected authority claim."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tests import test_event_pack_capture as source

joined = source.joined
wire = joined.proposal
OPERATION = (0x0102030405060708, bytes(range(32)), b"R" * 32, b"P" * 32)


def tagged(tag, raw):
    return hashlib.sha256(b"SIA-PACK-" + tag + b"-v1\0" + raw).digest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def entry(identifier, raw):
    return bytes.fromhex(identifier) + hashlib.sha256(raw).digest() + len(raw).to_bytes(8, "big")


class CapturedProposal(unittest.TestCase):
    def setUp(self):
        self.fixture = source.CapturedPackPlan(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib, self.key = self.fixture.lib, self.fixture.key
        self.capture = self.fixture._capture()

    def prepare(self, identifiers=None, operation=OPERATION):
        with self.lib.corpus_owner():
            return joined.prepare_proposal(self.lib.__dict__, organ="org",
                prefix=self.key[:3], identifiers=(self.key,) if identifiers is None else identifiers,
                capture=self.capture, operation=operation)

    def expected_legacy_frame(self, result):
        frame, selected, fallback, dependencies, transport = result
        raw = self.fixture.fixture.raw
        expected_entry = entry(self.key, raw)
        self.assertEqual(selected, b"SIA-PACK-RECORDS-v1\0" + (1).to_bytes(8, "big") + expected_entry)
        self.assertEqual(fallback, b"SIA-PACK-RECORDS-v1\0" + bytes(8))
        captured = json.loads(dependencies)
        self.assertEqual(captured["sources"], self.capture.dependencies())
        self.assertEqual(captured["policies"], [self.lib.__dict__[n] for n in joined.POLICIES])
        self.assertEqual(captured["policy_names"], list(joined.POLICIES))
        expected = bytearray(16384)
        expected[0] = 1
        expected[40:48] = OPERATION[0].to_bytes(8, "big")
        digests = (OPERATION[1], tagged(b"CORPUS", canonical(self.capture.root_identity)),
                   tagged(b"ORGAN", b"org"), tagged(b"PREFIX", self.key[:3].encode()),
                   OPERATION[2], tagged(b"CAPTURE", dependencies),
                   tagged(b"SELECTION", selected), tagged(b"FALLBACK", fallback),
                   tagged(b"TARGET", b"\0"), tagged(b"TARGET", b"\1" + transport[0]),
                   OPERATION[3])
        for index, digest in enumerate(digests):
            expected[48 + 32 * index:80 + 32 * index] = digest
        expected[400:408] = (3).to_bytes(8, "big")
        expected[408:416] = (1).to_bytes(8, "big")
        for start in (5040, 9656):
            expected[start:start + 8] = (1).to_bytes(8, "big")
            expected[start + 8:start + 80] = expected_entry
        expected[14272] = 1
        relative = self.lib._event_index_relative("org", self.key)
        generation = canonical(self.capture.files[relative]["generation"])
        expected[14336:14368] = tagged(b"LEGACY-GENERATION", generation)
        expected[8:40] = hashlib.sha256(
            b"SIA-PACK-PLAN-BINDING-v1\0" + expected[:8] + expected[40:]).digest()
        self.assertEqual(frame, bytes(expected))

    def test_complete_nonuniform_source_and_frame_correspondence(self):
        self.expected_legacy_frame(self.prepare())
        self.assertFalse(self.fixture.fixture.pack.exists())
        self.assertEqual(self.fixture.fixture.legacy.read_bytes(), self.fixture.fixture.raw)

    def test_pack_only_presence_and_prior_are_explicit(self):
        self.fixture.fixture._write_pack()
        prior = self.fixture.fixture.pack.read_bytes()
        self.fixture.fixture.legacy.unlink()
        frame, _selected, _fallback, _dependencies, _result = self.prepare()
        expected_entry = entry(self.key, self.fixture.fixture.raw)
        self.assertEqual(frame[304:336], tagged(b"TARGET", b"\1" + prior))
        self.assertEqual(frame[424:5040], (1).to_bytes(8, "big") + expected_entry + bytes(63 * 72))
        self.assertEqual(frame[14272:], bytes(2112))

    def test_exact_fallback_manifest_preserves_full_prior(self):
        self.fixture.fixture._alternate_roster(64)
        prior = self.fixture.fixture.pack.read_bytes()
        frame, selected, fallback, _deps, result = self.prepare()
        self.assertEqual(selected, fallback)
        self.assertEqual(result[0], prior)
        self.assertEqual(frame[408:424], (1).to_bytes(8, "big") * 2)
        self.assertEqual(frame[9656:14272], bytes(4616))
        self.assertEqual(frame[304:336], frame[336:368])

    def test_no_target_refuses_without_changing_transport_contract(self):
        with self.assertRaisesRegex(ValueError, "has no target"):
            self.prepare(())
        self.assertFalse(self.fixture.fixture.pack.exists())
        self.assertEqual(self.fixture.prepare(()), (None, (), ()))

    def test_coherent_selection_omission_refuses(self):
        original = joined.planner.plan

        def omit(*args, **kwargs):
            packed, _represented, fallback = original(*args, **kwargs)
            return packed, (), fallback

        with mock.patch.object(joined.planner, "plan", omit):
            with self.assertRaisesRegex(ValueError, "selection correspondence"):
                self.prepare()

    def test_coherent_source_and_target_substitution_refuses(self):
        fake = ((self.key.encode(), b"unrelated"),)
        packed = joined.codec.encode("org", self.key[:3], fake)
        with mock.patch.object(joined.planner, "plan", return_value=(packed, fake, ())):
            with self.assertRaisesRegex(ValueError, "selection bytes mismatch"):
                self.prepare()

    def test_fallback_substitution_refuses(self):
        self.fixture.fixture._alternate_roster(64)
        prior = self.fixture.fixture.pack.read_bytes()
        fake = ((self.key.encode(), b"unrelated"),)
        with mock.patch.object(joined.planner, "plan", return_value=(prior, (), fake)):
            with self.assertRaisesRegex(ValueError, "selection bytes mismatch"):
                self.prepare()

    def test_post_identity_policy_change_refuses(self):
        original = wire.encode

        def changed(*args, **kwargs):
            frame = original(*args, **kwargs)
            self.lib.MAX_EVENT_PAGE_BYTES = 1
            return frame

        with mock.patch.object(self.lib, "MAX_EVENT_PAGE_BYTES", self.lib.MAX_EVENT_PAGE_BYTES), \
                mock.patch.object(wire, "encode", changed):
            with self.assertRaisesRegex(ValueError, "policy changed"):
                self.prepare()

    def test_post_identity_source_change_refuses(self):
        original = wire.encode

        def changed(*args, **kwargs):
            frame = original(*args, **kwargs)
            self.fixture.fixture.legacy.write_bytes(self.fixture.fixture.raw + b" ")
            return frame

        with mock.patch.object(wire, "encode", changed):
            with self.assertRaises(ValueError):
                self.prepare()

    def test_complete_frame_hash_binding_and_no_authentication_claim(self):
        frame = self.prepare()[0]
        self.assertTrue(wire.identity_matches(frame))
        for position in range(len(frame)):
            changed = bytearray(frame)
            changed[position] ^= 1
            self.assertFalse(wire.identity_matches(bytes(changed)), position)
        changed = bytearray(frame)
        changed[368] ^= 1  # Untrusted permission reference can be rehashed.
        changed[8:40] = wire.identity(bytes(changed))
        self.assertTrue(wire.identity_matches(bytes(changed)))

    def test_request_types_and_failed_reservation_remain_visible(self):
        for operation in (None, list(OPERATION), (True, *OPERATION[1:]),
                          (0, *OPERATION[1:]), (2**63, *OPERATION[1:]),
                          (1, b"short", *OPERATION[2:])):
            before = dict(self.capture.budget.items)
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                self.prepare(operation=operation)
            self.assertEqual(self.capture.budget.items, before)
        self.capture.budget.reserve("other", self.capture.budget.limit - self.capture.budget.total)
        with mock.patch.object(joined.reader, "_optional", side_effect=AssertionError("read")):
            with self.assertRaisesRegex(ValueError, "complete-byte-capacity"):
                self.prepare()
        self.assertIn(("event-pack-proposal", "org", self.key[:3]), self.capture.budget.items)

    def native(self, frame):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "proposal.bin"
            path.write_bytes(frame)
            return subprocess.run([os.environ["SIA_PACK_PROPOSAL_PROBE"], str(path)],
                                  capture_output=True, timeout=5, check=False)

    def require_native(self, frame, accepted=True):
        result = self.native(frame)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b"")
        expected = b"ACCEPTED\n" + frame.hex().encode() + b"\n" if accepted else b"REFUSED\n"
        self.assertEqual(result.stdout, expected)

    @unittest.skipUnless(os.environ.get("SIA_PACK_PROPOSAL_PROBE"),
                         "native SPARK file adapter UNRUN; no integration evidence")
    def test_native_decoded_complete_plan_and_refusals(self):
        original = self.prepare()[0]
        self.require_native(original)
        for offset, value in ((0, 2), (415, 0), (14272, 2), (5047, 0)):
            changed = bytearray(original)
            changed[offset] = value
            self.require_native(bytes(changed), False)
        for changed in (original[:-1], original + b"\0"):
            self.assertNotEqual(self.native(changed).returncode, 0)
        changed = bytearray(original)
        changed[8] ^= 1
        self.assertFalse(wire.identity_matches(bytes(changed)))
        self.require_native(bytes(changed))  # Decoder alone does not authenticate.
        self.fixture.fixture._write_pack()
        self.fixture.fixture.legacy.unlink()
        self.capture = self.fixture._capture()
        self.require_native(self.prepare()[0])
        self.fixture.fixture.legacy.write_bytes(self.fixture.fixture.raw)
        self.fixture.fixture._alternate_roster(64)
        self.capture = self.fixture._capture()
        self.require_native(self.prepare()[0])


if __name__ == "__main__":
    unittest.main()
