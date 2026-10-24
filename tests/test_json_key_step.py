"""Compare key/value stepping against the exact preceding iterative walker."""
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import siasourcebatch as candidate


def original_module():
    root = Path(candidate.__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        'key_step_original', root / 'tests/fixtures/json-size-key-step-baseline.py')
    if spec is None or spec.loader is None:
        raise RuntimeError('missing baseline loader')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ORIGINAL = original_module()


def observed(module, factory, ceiling, ascii_only, mutation=None):
    value, target = factory()
    trace = []
    add, text = module._JsonSizeCounter.add, module._live._count_ascii_json_string

    def count(counter, amount):
        if len(trace) >= 4096:
            raise RuntimeError('test trace capacity')
        trace.append(('add', amount))
        return add(counter, amount)

    def string(item, append, *, ascii_only):
        trace.append(('string', item))
        if item == 'key' and mutation is not None:
            mutation(target)
        return text(item, append, ascii_only=ascii_only)

    def finite(number):
        trace.append(('finite', number))
        return math.isfinite(number)

    with patch.object(module._JsonSizeCounter, 'add', count), \
            patch.object(module._live, '_count_ascii_json_string', string):
        try:
            size = module._json_size({'math': SimpleNamespace(isfinite=finite), 'json': json},
                                     value, ceiling, ascii_only=ascii_only)
        except (ValueError, RuntimeError, TypeError, KeyError) as error:
            result = ('refusal', type(error).__name__, str(error))
        else:
            result = ('size', size)
    return result, trace


class JsonKeyStep(unittest.TestCase):
    def compare(self, factory, ceiling, ascii_only, mutation=None):
        expected = observed(ORIGINAL, factory, ceiling, ascii_only, mutation)
        actual = observed(candidate, factory, ceiling, ascii_only, mutation)
        self.assertEqual(actual, expected)
        return actual

    def test_exact_budget_and_callback_trace(self):
        for key in ('', 'key', '\x00"\\', 'é😀', '\ud800'):
            for ceiling in (1, 2, 3, 4, 5, 6, 7, 8, 20, 4096):
                for ascii_only in (False, True):
                    def fixture(key=key):
                        value = {key: [1.5, 'tail'], 'last': True}
                        return value, value
                    with self.subTest(key=key, ceiling=ceiling, ascii_only=ascii_only):
                        self.compare(fixture, ceiling, ascii_only)

    def test_mapping_depth_and_nontext_key_refusal_order(self):
        for key in ('key', 1, '\ud800'):
            for depth in (63, 64, 65, 66):
                def fixture(key=key, depth=depth):
                    value = {key: float('inf')}
                    target = value
                    for _ in range(depth):
                        value = [value]
                    return value, target
                with self.subTest(key=key, depth=depth):
                    self.compare(fixture, 4096, True)

    def test_mapping_value_replacement_preserves_captured_child(self):
        def fixture():
            value = {'key': [1.5, 'old'], 'last': 'tail'}
            return value, value
        result, trace = self.compare(fixture, 4096, True,
                                    lambda target: target.update(key=['replacement']))
        self.assertEqual(result[0], 'size')
        self.assertIn(('string', 'old'), trace)
        self.assertNotIn(('string', 'replacement'), trace)

    def test_captured_child_live_alias_is_preserved(self):
        def fixture():
            child = [1.5, 'old']
            return {'key': child}, child
        result, trace = self.compare(fixture, 4096, True,
                                    lambda target: target.append('appended'))
        self.assertEqual(result[0], 'size')
        self.assertIn(('string', 'appended'), trace)

    def test_mapping_resize_keeps_iterator_failure_frontier(self):
        def fixture():
            value = {'key': 1.5}
            return value, value
        result, trace = self.compare(fixture, 4096, True,
                                    lambda target: target.update(added=True))
        self.assertEqual(result[:2], ('refusal', 'RuntimeError'))
        self.assertIn(('finite', 1.5), trace)

    def test_key_callback_exception_precedes_colon_and_child(self):
        def fixture():
            value = {'key': 1.5}
            return value, value
        def fail(_target):
            raise RuntimeError('injected key failure')
        result, trace = self.compare(fixture, 4096, True, fail)
        self.assertEqual(result, ('refusal', 'RuntimeError', 'injected key failure'))
        self.assertNotIn(('finite', 1.5), trace)

    def test_key_deletion_still_processes_captured_value(self):
        def fixture():
            value = {'key': 1.5}
            return value, value
        result, trace = self.compare(fixture, 4096, True, lambda target: target.clear())
        self.assertEqual(result[:2], ('refusal', 'RuntimeError'))
        self.assertIn(('finite', 1.5), trace)

    def test_colon_capacity_refuses_before_child_callback(self):
        def fixture():
            value = {'key': 1.5}
            return value, value
        result, trace = self.compare(fixture, 7, True)
        self.assertEqual(result[0], 'refusal')
        self.assertNotIn(('finite', 1.5), trace)


if __name__ == '__main__':
    unittest.main()
