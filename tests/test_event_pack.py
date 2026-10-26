"""Independent wire oracle; transport integrity is not source authority."""
import hashlib
from pathlib import Path
import struct
from types import ModuleType
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "bin/siaeventpack.py"
siaeventpack = ModuleType("siaeventpack")
# Compile the reviewed bytes directly; a timestamp-matched .pyc is not evidence.
exec(compile(SOURCE.read_bytes(), str(SOURCE), "exec"), siaeventpack.__dict__)


def wire(records, *, count=None, organ=b"org", prefix=b"abc"):
    body = b"".join(key + struct.pack(">I", len(raw)) + raw
                    for key, raw in records)
    return (b"SIA-EVENT-PACK-1\n" + struct.pack("B", len(organ)) + organ
            + prefix + struct.pack("B", len(records) if count is None else count)
            + struct.pack(">I", len(body)) + hashlib.sha256(body).digest() + body)


class EventPackTests(unittest.TestCase):
    def test_exact_bytes_roundtrip_and_independent_wire_oracle(self):
        records = ((b"abc" + b"0" * 61, b"\x00\xffopaque legacy bytes\n"),
                   (b"abc" + b"1" * 61, b"second\n"))
        self.assertEqual(siaeventpack.encode("org", "abc", records), wire(records))
        self.assertEqual(siaeventpack.decode(wire(records), "org", "abc"), records)

    def test_every_truncation_and_single_bit_corruption_is_refused(self):
        value = wire(((b"abc" + b"0" * 61, b"legacy\n"),))
        for end in range(len(value)):
            with self.subTest(end=end), self.assertRaises(ValueError):
                siaeventpack.decode(value[:end], "org", "abc")
        for position in range(len(value)):
            altered = value[:position] + bytes([value[position] ^ 1]) + value[position + 1:]
            with self.subTest(position=position), self.assertRaises(ValueError):
                siaeventpack.decode(altered, "org", "abc")

    def test_semantic_transport_faults_with_recomputed_digest_are_refused(self):
        first = (b"abc" + b"0" * 61, b"a")
        second = (b"abc" + b"1" * 61, b"b")
        cases = (wire((first, first)), wire((second, first)),
                 wire(((b"def" + b"0" * 61, b"a"),)),
                 wire(((first[0], b""),)), wire((first,), count=0),
                 wire((first,), count=2), wire((first,), count=65),
                 wire((first, second), count=1),
                 wire((first,), organ=b"other"), wire((first,), prefix=b"def"))
        for value in cases:
            with self.subTest(digest=hashlib.sha256(value).hexdigest()):
                with self.assertRaises(ValueError):
                    siaeventpack.decode(value, "org", "abc")

    def test_record_and_byte_capacity_edges(self):
        records = tuple((f"abc{i:061x}".encode(), b"x") for i in range(64))
        self.assertEqual(siaeventpack.decode(wire(records), "org", "abc"), records)
        with self.assertRaises(ValueError):
            siaeventpack.encode("org", "abc", records + ((b"abc" + b"f" * 61, b"x"),))
        key = records[0][0]
        overhead = len(wire(((key, b"x"),))) - 1
        exact = ((key, b"x" * (65536 - overhead)),)
        self.assertEqual(len(siaeventpack.encode("org", "abc", exact)), 65536)
        self.assertEqual(siaeventpack.decode(wire(exact), "org", "abc"), exact)
        for raw in (b"x" * (65537 - overhead), b"x" * 65536):
            with self.assertRaises(ValueError):
                siaeventpack.encode("org", "abc", ((key, raw),))
        with self.assertRaises(ValueError):
            siaeventpack.decode(wire(exact) + b"x", "org", "abc")

    def test_rehashed_payload_is_transport_valid_not_authenticated(self):
        record = (b"abc" + b"0" * 61, b"untrusted bytes")
        self.assertEqual(siaeventpack.decode(wire((record,)), "org", "abc"),
                         (record,))

    def test_invalid_native_shapes_and_routes_are_refused(self):
        key = b"abc" + b"0" * 61
        for records in ([], (), ((key, "text"),), ((key,),),
                        ((b"short", b"x"),), ((b"z" * 64, b"x"),)):
            with self.subTest(records=records), self.assertRaises(ValueError):
                siaeventpack.encode("org", "abc", records)
        for organ, prefix in (("../org", "abc"), ("org", "ab"),
                              ("org", "ABC"), (None, "abc")):
            with self.subTest(organ=organ, prefix=prefix):
                with self.assertRaises(ValueError):
                    siaeventpack.encode(organ, prefix, ((key, b"x"),))


class LegacyEntryEquivalence(unittest.TestCase):
    def setUp(self):
        from tests.test_event_epoch_admission_integrity import (
            EventEpochAdmissionIntegrity)
        self.fixture = EventEpochAdmissionIntegrity(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        event, _source, _record = self.fixture._source()
        self.fixture._commit_corpus()
        self.fixture.lib.consolidate_corpus()
        self.lib = self.fixture.lib
        self.event_id = self.lib.event_memory_identity(event)
        self.path = Path(self.lib.CORPUS) / self.lib._event_index_relative(
            "org", self.event_id)

    def _roundtrip(self, raw):
        encoded = siaeventpack.encode("org", self.event_id[:3],
                                      ((self.event_id.encode(), raw),))
        records = siaeventpack.decode(encoded, "org", self.event_id[:3])
        self.assertEqual(records, ((self.event_id.encode(), raw),))
        return records[0][1]

    def test_retained_legacy_bytes_preserve_original_lineage_decision(self):
        original = self.lib._read_event_index_entry("org", self.event_id)
        raw = self.path.read_bytes()
        self.path.write_bytes(self._roundtrip(raw))
        self.assertEqual(self.lib._read_event_index_entry("org", self.event_id),
                         original)

    def test_transport_digest_does_not_authorize_forged_source_lineage(self):
        original = self.lib._read_event_index_entry("org", self.event_id)
        forged = dict(original, source_sha256="f" * 64)
        raw = self.lib._event_index_encoded(forged)
        self.path.write_bytes(self._roundtrip(raw))
        with self.assertRaisesRegex(ValueError, "exact epoch lineage"):
            self.lib._read_event_index_entry("org", self.event_id)


if __name__ == "__main__":
    unittest.main()
