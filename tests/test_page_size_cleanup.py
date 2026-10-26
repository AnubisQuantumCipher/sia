"""Compare cleanup attempts and exception precedence with recursive unwinding."""
import unittest

from tests import page_size_recursive_reference as recursive_reference
import siaeventplan as plan


def observe(sizer, value, failures, remove_first):
    trace = []

    class Active(set):
        def remove(self, identity):
            trace.append(identity)
            if remove_first or identity not in failures:
                super().remove(identity)
            if identity in failures:
                raise RuntimeError(f'cleanup-{failures[identity]}')

    active = Active({123456})
    result, chain = None, []
    try:
        result = sizer(value, 1000, active)
    except (RuntimeError, ValueError, KeyError) as error:
        for _position in range(8):
            chain.append((type(error).__name__, str(error)))
            error = error.__context__
            if error is None:
                break
        else:
            raise AssertionError('exception chain capacity') from error
    return result, trace, chain, active


class PageSizeCleanup(unittest.TestCase):
    def test_exception_context_does_not_dispatch_subclass_hooks(self):
        dispatches = []

        class CleanupFailure(RuntimeError):
            def __getattribute__(self, name):
                if name == '__context__':
                    dispatches.append('get')
                    raise AssertionError('custom context get')
                return super().__getattribute__(name)

            def __setattr__(self, name, value):
                if name == '__context__':
                    dispatches.append('set')
                    raise AssertionError('custom context set')
                super().__setattr__(name, value)

        class Active(set):
            def remove(self, identity):
                super().remove(identity)
                raise CleanupFailure('expected cleanup failure')

        for sizer in (recursive_reference._size, plan._size):
            active = Active()
            with self.subTest(sizer=sizer.__module__):
                with self.assertRaises(CleanupFailure):
                    sizer([[[object()]]], 1000, active)
                self.assertEqual(dispatches, [])
                self.assertEqual(active, set())

    def test_cleanup_failures_match_original_unwind(self):
        for leaf in (None, object()):
            inner = [leaf]
            middle = [inner]
            root = [middle]
            choices = ({id(inner): 'inner'}, {id(middle): 'middle'},
                       {id(root): 'outer'},
                       {id(inner): 'inner', id(middle): 'middle', id(root): 'outer'})
            for failures in choices:
                for remove_first in (False, True):
                    with self.subTest(invalid=leaf is not None,
                                      failures=tuple(failures.values()),
                                      remove_first=remove_first):
                        expected = observe(recursive_reference._size, root,
                                           failures, remove_first)
                        actual = observe(plan._size, root, failures, remove_first)
                        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
