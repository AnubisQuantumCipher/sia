"""Exact serializer, refusal-order, ancestry and bounded-scratch controls."""
import json
import tracemalloc
import unittest
from unittest import mock

import siaeventplan as plan


def nest(value, count):
    for _position in range(count):
        value = [value]
    return value


class PageSizeTraversal(unittest.TestCase):
    def test_native_domain_matches_serializer_at_exact_capacity(self):
        values = [None, True, False, 0, -1, '', 'é😀\x00\\"',
                  [], {}, [0, False, None], {'é': ['text', {'key': -1}]}]
        for value in values:
            expected = len(json.dumps(value, ensure_ascii=False,
                                      separators=(',', ':')).encode('utf-8'))
            with self.subTest(kind=type(value).__name__, expected=expected):
                self.assertEqual(plan._size(value, expected), expected)
                with self.assertRaisesRegex(ValueError, 'complete-byte-capacity'):
                    plan._size(value, expected - 1)

    def test_original_native_integer_bit_bound_remains_stricter_than_text(self):
        for value in (2**80, -(2**80), 2**256, -(2**256)):
            with self.subTest(sign=value < 0, bits=value.bit_length()):
                with self.assertRaisesRegex(ValueError, 'complete-byte-capacity'):
                    plan._size(value, len(str(value)))
                self.assertEqual(plan._size(value, value.bit_length()), len(str(value)))

    def test_original_depth_boundary_and_offset_are_preserved(self):
        self.assertEqual(plan._size(nest(None, 64), 1000),
                         len(json.dumps(nest(None, 64), separators=(',', ':'))))
        with self.assertRaisesRegex(ValueError, 'complete-byte-capacity'):
            plan._size(nest(None, 65), 1000)
        self.assertEqual(plan._size(nest(None, 65), 1000, depth=-1),
                         len(json.dumps(nest(None, 65), separators=(',', ':'))))
        with self.assertRaisesRegex(ValueError, 'complete-byte-capacity'):
            plan._size(None, 1000, depth=65)

    def test_cycle_rejection_restores_supplied_ancestor_set(self):
        root = [0]
        root.append({'cycle': root})
        active = {123456}
        with self.assertRaisesRegex(ValueError, 'cyclic-json'):
            plan._size(root, 1000, active)
        self.assertEqual(active, {123456})

    def test_repeated_noncyclic_alias_is_counted_each_time(self):
        shared = ['same']
        root = [shared, shared]
        expected = len(json.dumps(root, separators=(',', ':')))
        self.assertEqual(plan._size(root, expected), expected)

    def test_nontext_key_precedes_child_and_negative_remaining_budget(self):
        for limit in (1, 2, 3, 100):
            with self.subTest(limit=limit), self.assertRaisesRegex(ValueError, 'text-type'):
                plan._size({7: object()}, limit)

    def test_empty_container_still_requires_its_delimiters(self):
        for value in ([], {}):
            with self.subTest(value=value):
                self.assertEqual(plan._size(value, 2), 2)
                with self.assertRaisesRegex(ValueError, 'complete-byte-capacity'):
                    plan._size(value, 1)

    def test_dictionary_lookup_remains_after_key_size(self):
        value, original, seen = {'key': 'before'}, plan._text_size, []

        def sized(text, limit, **kwargs):
            if text == 'key':
                value['key'] = 'after'
                seen.append(True)
            return original(text, limit, **kwargs)

        with mock.patch.object(plan, '_text_size', sized):
            actual = plan._size(value, 100)
        self.assertTrue(seen)
        self.assertEqual(actual, len(json.dumps({'key': 'after'}, separators=(',', ':'))))

    def test_ancestor_registration_still_precedes_iterator_creation(self):
        value = {'original': None}

        class Active(set):
            def add(self, identity):
                super().add(identity)
                value['added-at-registration'] = None

        active = Active()
        actual = plan._size(value, 1000, active)
        self.assertFalse(active)
        self.assertEqual(actual, len(json.dumps(value, separators=(',', ':'))))

    def test_frame_allocation_failure_restores_active_ancestors(self):
        active = {123456}
        with mock.patch.object(plan, '_PageSizeFrame', side_effect=MemoryError('controlled allocation')):
            with self.assertRaises(MemoryError):
                plan._size([None], 100, active)
        self.assertEqual(active, {123456})

    def test_frame_registration_failure_restores_active_ancestors(self):
        class FailingFrames(list):
            def append(self, _frame):
                raise MemoryError('controlled frame registration')

        active = {123456}
        with self.assertRaises(MemoryError):
            plan._open_size_frame([None], 100, 0, active, FailingFrames())
        self.assertEqual(active, {123456})

    def test_depth_is_only_incremented_on_descent(self):
        trace = []

        class Depth:
            def __gt__(self, _other):
                trace.append('compare')
                return False

            def __add__(self, _other):
                trace.append('increment')
                return 1

        for value in (None, []):
            trace.clear()
            plan._size(value, 100, depth=Depth())
            self.assertEqual(trace, ['compare'])
        trace.clear()
        plan._size([None], 100, depth=Depth())
        self.assertEqual(trace, ['compare', 'increment'])

    def test_wide_input_does_not_create_a_width_sized_scratch_queue(self):
        value = [None] * 50000
        expected = len(json.dumps(value, separators=(',', ':')))
        tracemalloc.start()
        try:
            self.assertEqual(plan._size(value, expected), expected)
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 262144, 'traced sizing scratch, not process RSS or a proof')

    def test_failure_restores_active_ancestors(self):
        active = {123456}
        for value in ([{'bad': object()}], [1] * 100):
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError):
                plan._size(value, 32, active)
            self.assertEqual(active, {123456})


if __name__ == '__main__':
    unittest.main()
