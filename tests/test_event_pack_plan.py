"""Exact transport coverage; no source authenticity or migration acceptance."""

from pathlib import Path
from types import ModuleType
import unittest
from unittest import mock

from tests import test_event_pack as wire_fixture

codec = wire_fixture.siaeventpack
SOURCE = Path(__file__).resolve().parents[1] / "bin/siaeventpackplan.py"
planner = ModuleType("siaeventpackplan")
with mock.patch.dict("sys.modules", {"siaeventpack": codec}):
    exec(compile(SOURCE.read_bytes(), str(SOURCE), "exec"), planner.__dict__)
LIMITS = (65_536, 65_536, 16_777_216)


def record(number, raw=b"x"):
    return f"abc{number:061x}".encode("ascii"), raw


class EventPackPlan(unittest.TestCase):
    def plan(self, records=(), prior=(), *, limits=LIMITS, organ="org"):
        original = None if not prior else wire_fixture.wire(prior, organ=organ.encode())
        result = planner.plan(organ, "abc", records, original, limits=limits)
        packed, represented, fallback = result
        self.assertIs(type(result), tuple)
        self.assertIs(type(represented), tuple)
        self.assertIs(type(fallback), tuple)
        self.assertEqual(tuple(sorted(represented + fallback)), records)
        self.assertTrue(set(dict(represented)).isdisjoint(dict(fallback)))
        decoded = () if packed is None else codec.decode(packed, organ, "abc")
        combined = dict(decoded)
        for identifier, raw in prior + represented:
            self.assertEqual(combined[identifier], raw)
        self.assertTrue(set(dict(fallback)).isdisjoint(combined))
        self.assertEqual(set(combined), set(dict(prior)) | set(dict(represented)))
        if packed is not None:
            self.assertEqual(packed, wire_fixture.wire(decoded, organ=organ.encode()))
        self.assertEqual(planner.plan(organ, "abc", records, original, limits=limits), result)
        return result

    def test_empty_inputs_and_unchanged_prior_frame(self):
        self.assertEqual(self.plan(), (None, (), ()))
        prior = (record(1),)
        packed, represented, fallback = self.plan(prior=prior)
        self.assertEqual(packed, wire_fixture.wire(prior))
        self.assertEqual((represented, fallback), ((), ()))

    def test_header_matches_independent_wire_for_short_and_long_organ(self):
        for organ in ("a", "org", "a" * 200):
            self.assertEqual(codec.header_size(organ, "abc"),
                             len(wire_fixture.wire((), organ=organ.encode())))

    def test_exact_frame_fit_and_one_byte_over_remains_legacy(self):
        for organ in ("org", "a" * 200):
            overhead = len(wire_fixture.wire((record(0),), organ=organ.encode())) - 1
            exact = (record(0, b"x" * (65_536 - overhead)),)
            packed, represented, fallback = self.plan(exact, organ=organ)
            self.assertEqual(len(packed), 65_536)
            self.assertEqual((represented, fallback), (exact, ()))
            over = (record(0, exact[0][1] + b"x"),)
            self.assertEqual(self.plan(over, organ=organ), (None, (), over))

    def test_oversized_valid_record_does_not_hide_later_smaller_record(self):
        records = (record(0, b"x" * 65_536), record(1))
        packed, represented, fallback = self.plan(records)
        self.assertEqual(represented, (records[1],))
        self.assertEqual(fallback, (records[0],))
        self.assertEqual(packed, wire_fixture.wire((records[1],)))

    def test_count_saturation_preserves_every_new_and_old_record(self):
        prior = tuple(record(i) for i in range(64))
        inputs = (record(0), record(64), record(65))
        packed, represented, fallback = self.plan(inputs, prior)
        self.assertEqual(packed, wire_fixture.wire(prior))
        self.assertEqual(represented, inputs[:1])
        self.assertEqual(fallback, inputs[1:])

    def test_prior_records_survive_interleaved_new_identifiers(self):
        prior = (record(1), record(3))
        inputs = (record(0), record(1), record(2), record(4))
        packed, represented, fallback = self.plan(inputs, prior)
        self.assertEqual(packed, wire_fixture.wire(tuple(record(i) for i in range(5))))
        self.assertEqual((represented, fallback), (inputs, ()))

    def test_late_conflicting_overlap_refuses_whole_plan(self):
        with self.assertRaisesRegex(ValueError, "representations conflict"):
            self.plan((record(0), record(1, b"changed")), (record(1),))

    def test_full_input_count_preserves_exact_complete_partition(self):
        records = tuple(record(i) for i in range(LIMITS[0]))
        _packed, represented, fallback = self.plan(records)
        self.assertEqual(represented, records[:64])
        self.assertEqual(fallback, records[64:])
        with self.assertRaisesRegex(ValueError, "input count"):
            planner.plan("org", "abc", records + (record(LIMITS[0]),), None, limits=LIMITS)

    def test_logical_input_byte_limit_includes_prior_and_framing(self):
        prior, inputs = (record(0),), (record(1, b"second"),)
        frame = wire_fixture.wire(prior)
        exact = len(wire_fixture.wire(())) + len(frame) + 68 + len(inputs[0][1])
        self.plan(inputs, prior, limits=(2, 65_536, exact))
        with self.assertRaisesRegex(ValueError, "input byte capacity"):
            self.plan(inputs, prior, limits=(2, 65_536, exact - 1))
        records = tuple(record(i, b"x" * 65_536) for i in range(257))
        with self.assertRaisesRegex(ValueError, "input byte capacity"):
            self.plan(records)

    def test_current_raw_limit_refuses_prior_even_if_unrequested(self):
        with self.assertRaisesRegex(ValueError, "prior record"):
            self.plan(prior=(record(0, b"long"),), limits=(1, 1, LIMITS[2]))
        with self.assertRaisesRegex(ValueError, "record exceeds current"):
            self.plan((record(0, b"long"),), limits=(1, 1, LIMITS[2]))
        with self.assertRaisesRegex(ValueError, "input count"):
            self.plan((record(0), record(1)), limits=(1, 65_536, LIMITS[2]))

    def test_malformed_prior_cannot_be_hidden_by_fallback(self):
        bad = (b"", b"invalid", wire_fixture.wire((record(0), record(0))),
               wire_fixture.wire((record(0),), prefix=b"def"))
        for prior in bad:
            with self.subTest(prior=prior), self.assertRaises(ValueError):
                planner.plan("org", "abc", (record(2, b"x" * 65_536),),
                             prior, limits=LIMITS)

    def test_all_inputs_are_validated_before_capacity_fallback(self):
        prior = wire_fixture.wire(tuple(record(i) for i in range(64)))
        invalid = ([], ((b"short", b"x"),), (record(65), record(64)),
                   (record(65), record(65)), (record(65, b""),),
                   ((b"def" + b"0" * 61, b"x"),), (record(65, b"x" * 65_537),))
        for records in invalid:
            with self.subTest(kind=type(records).__name__), self.assertRaises(ValueError):
                planner.plan("org", "abc", records, prior, limits=LIMITS)

    def test_exotic_native_shapes_refuse_without_dispatch(self):
        class HostileBytes(bytes):
            def __len__(self):
                raise AssertionError("exotic length dispatched")

        class HostileTuple(tuple):
            def __iter__(self):
                raise AssertionError("exotic iteration dispatched")

        cases = (HostileTuple(()), ((HostileBytes(record(0)[0]), b"x"),),
                 (record(0, HostileBytes(b"x")),), (HostileTuple(record(0)),))
        for records in cases:
            with self.assertRaises(ValueError):
                planner.plan("org", "abc", records, None, limits=LIMITS)
        with self.assertRaises(ValueError):
            planner.plan("org", "abc", (), HostileBytes(b"x"), limits=LIMITS)

    def test_limit_types_and_hard_ceilings_are_not_caller_overrides(self):
        for limits in ([1, 1, 1], (True, 1, 1), (1, False, 1), (1, 1, 0),
                       (65_537, 1, 1), (1, 65_537, 1), (1, 1, 16_777_217)):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                planner.plan("org", "abc", (), None, limits=limits)


if __name__ == "__main__":
    unittest.main()
