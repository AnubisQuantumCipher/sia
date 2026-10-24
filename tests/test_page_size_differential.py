"""Traversal differential campaign against the frozen recursive reference."""
import unittest

from tests import page_size_recursive_reference as reference
import siaeventplan as plan


def outcome(function, value, limit, depth):
    active = {123456}
    try:
        result = ('accepted', function(value, limit, active, depth))
    except (ValueError, TypeError, RuntimeError) as error:
        result = ('refused', type(error).__name__, str(error))
    return result, active


class PageSizeDifferential(unittest.TestCase):
    def test_ancestor_registration_precedes_dictionary_iterator_creation(self):
        def measured(function):
            value = {'original': None}

            class Active(set):
                def add(self, identity):
                    super().add(identity)
                    value['added-at-registration'] = None

            active = Active()
            try:
                result = ('accepted', function(value, 1000, active))
            except (ValueError, RuntimeError) as error:
                result = ('refused', type(error).__name__, str(error))
            self.assertFalse(active)
            return result

        self.assertEqual(measured(plan._size), measured(reference._size))

    def test_deterministic_vocabulary_and_nested_combinations(self):
        class Text(str):
            pass

        values = [None, True, False, 0, -1, 123, 2**256, -(2**256), '', 'x',
                  'é😀\n\x7f', '\ud800', [], {}, (), 1.0, b'x', Text('x')]
        base = list(values)
        for value in base:
            values.extend(([value], {'key': value}, {7: value}))
        for left in base[:8]:
            for right in base[:8]:
                values.append([left, {'key': right}])
        cycle = []
        cycle.append(cycle)
        values.extend((cycle, {'cycle': cycle}))
        nested = None
        for _count in range(66):
            nested = [nested]
        values.append(nested)
        for position, value in enumerate(values):
            for limit in (0, 1, 2, 3, 4, 7, 16, 64, 256, 1000, True, 1.5):
                for depth in (-1, 0, 64, 65):
                    with self.subTest(position=position, limit=limit, depth=depth):
                        self.assertEqual(outcome(plan._size, value, limit, depth),
                                         outcome(reference._size, value, limit, depth))


if __name__ == '__main__':
    unittest.main()
