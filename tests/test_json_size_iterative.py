"""Differential controls; Python runtime assumptions are not formal proof."""
import importlib.util
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bin'))
candidate = importlib.import_module('siasourcebatch')


def load_original():
    spec = importlib.util.spec_from_file_location(
        'original_sourcebatch', ROOT / 'tests/fixtures/json-size-recursive-baseline.py')
    if spec is None or spec.loader is None:
        raise RuntimeError('original loader unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ORIGINAL = load_original()
OWNER = {'math': math, 'json': json}


def current_stack_depth():
    frame = sys._getframe()
    try:
        for depth in range(1, 65):
            frame = frame.f_back
            if frame is None:
                return depth - 1
        raise RuntimeError('test harness stack exceeds observation bound')
    finally:
        frame = None


def outcome(module, value, ceiling, ascii_only, owner=None):
    try:
        result = module._json_size(
            OWNER if owner is None else owner, value, ceiling,
            ascii_only=ascii_only)
    except (ValueError, RuntimeError) as error:
        return ('refusal', type(error).__name__, str(error))
    return ('size', result)


class IterativeSize(unittest.TestCase):
    def compare(self, value, ceiling, ascii_only):
        expected = outcome(ORIGINAL, value, ceiling, ascii_only)
        actual = outcome(candidate, value, ceiling, ascii_only)
        self.assertEqual(actual, expected)
        return actual

    def test_serialized_exact_and_short_boundaries(self):
        leaves = [None, True, False, 0, -1, 1.25, -0.0, '', 'é😀', '\x00\n"\\']
        values = leaves + [[v] for v in leaves]
        values += [{'first': v, 'last': [v, 'tail']} for v in leaves]
        for value in values:
            for ascii_only in (False, True):
                raw = json.dumps(value, ensure_ascii=ascii_only, sort_keys=True,
                                 separators=(',', ':')).encode('utf-8')
                with self.subTest(value=value, ascii_only=ascii_only):
                    self.assertEqual(self.compare(value, len(raw), ascii_only),
                                     ('size', len(raw)))
                    self.compare(value, len(raw) - 1, ascii_only)
                    self.compare(value, len(raw) + 1, ascii_only)

    def test_invalid_inputs_and_refusal_order(self):
        class ListChild(list):
            pass
        values = [float('nan'), float('inf'), '\ud800', b'x', (1,),
                  {1: 'x'}, ListChild(), [object()], 1 << 1000,
                  {'\ud800': float('nan')}, {'x': {1: '\ud800'}}]
        for value in values:
            for ceiling in (0, True, 1, 2, 3, 8, 1024, 4096):
                for ascii_only in (False, True):
                    with self.subTest(kind=type(value).__name__, ceiling=ceiling):
                        self.compare(value, ceiling, ascii_only)

    def test_depth_bound_empty_and_nonempty(self):
        for leaf in ([], {}, 0, 'x'):
            for depth in range(67):
                value = leaf
                for _ in range(depth):
                    value = [value]
                for ascii_only in (False, True):
                    with self.subTest(depth=depth, leaf=type(leaf).__name__):
                        self.compare(value, 4096, ascii_only)

    def test_cycles_and_shared_noncyclic_values(self):
        direct = []
        direct.append(direct)
        mapping = {}
        mapping['self'] = mapping
        indirect = []
        middle = {'back': indirect}
        indirect.append(middle)
        shared = [1, {'text': 'é'}]
        for value in (direct, mapping, indirect, [shared, shared]):
            for ceiling in (1, 4, 4096):
                self.compare(value, ceiling, False)

    def test_wide_container_uses_depth_bounded_frames(self):
        value = [{'v': [i]} for i in range(1024)]
        live, peak = [0], [0]
        original_frame = candidate._JsonSizeFrame

        class ObservedFrame(original_frame):
            def __init__(self, item):
                super().__init__(item)
                live[0] += 1
                peak[0] = max(peak[0], live[0])

            def __del__(self):
                live[0] -= 1

        with patch.object(candidate, '_JsonSizeFrame', ObservedFrame):
            self.compare(value, 65536, False)
        self.assertLessEqual(peak[0], 4)
        self.assertEqual(live[0], 0)

    def test_native_container_mutation_at_float_callback(self):
        for mode in ('append', 'replace', 'dict_resize'):
            results = []
            for module in (ORIGINAL, candidate):
                value = {'x': 1.5} if mode == 'dict_resize' else [1.5, 'old']
                calls = []

                class Math:
                    @staticmethod
                    def isfinite(number, *, calls=calls, mode=mode, value=value):
                        calls.append(number)
                        if mode == 'append':
                            value.append('new')
                        elif mode == 'replace':
                            value[1] = 'new'
                        else:
                            value['new'] = 'new'
                        return math.isfinite(number)

                results.append((outcome(module, value, 4096, False,
                                        {'math': Math}), calls))
            self.assertEqual(results[0], results[1])

    def test_mapping_child_is_captured_before_key_callback(self):
        results = []
        for module in (ORIGINAL, candidate):
            value = {'key': 'old'}
            trace = []
            original = module._live._count_ascii_json_string

            def counting(text, add, *, ascii_only, trace=trace,
                         value=value, original=original):
                trace.append(text)
                if text == 'key':
                    value['key'] = 'replacement'
                return original(text, add, ascii_only=ascii_only)

            with patch.object(module._live, '_count_ascii_json_string', counting):
                result = outcome(module, value, 4096, True)
            results.append((result, trace))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1][1], ['key', 'old'])

    def test_runtime_recursion_budget_no_longer_scales_with_input_depth(self):
        value = []
        for _ in range(64):
            value = [value]
        expected = len(json.dumps(value, separators=(',', ':')))
        previous = sys.getrecursionlimit()
        # Reserve the same call-depth allowance regardless of unittest's caller
        # depth. A fixed global limit made this witness depend on suite loading.
        limit = current_stack_depth() + 32
        self.assertLess(limit, previous)
        try:
            sys.setrecursionlimit(limit)
            with self.assertRaises(RecursionError):
                ORIGINAL._json_size(OWNER, value, 4096, ascii_only=False)
            self.assertEqual(candidate._json_size(
                OWNER, value, 4096, ascii_only=False), expected)
        finally:
            sys.setrecursionlimit(previous)


if __name__ == '__main__':
    unittest.main()
