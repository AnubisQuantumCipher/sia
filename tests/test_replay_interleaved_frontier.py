"""Source-pinned counterexample for the experimental version-step insertion."""
import unittest
from unittest import mock

import siaeventintake as replay
from tests import test_event_live_intake as fixtures


class InterleavedFrontier(unittest.TestCase):
    def test_unused_equal_candidate_can_change_after_comparison(self):
        case = fixtures.EventLiveIntakeProjection(methodName='runTest')
        case.setUp()
        self.addCleanup(case.doCleanups)
        event = case.event()
        first = case.entry({'sense_custom:alpha': [event]})
        case.publish_entry_fixture(first)
        later = case.entry({'sense_custom:alpha': [event]}, batch_id='same-version-later')
        request = case.request([first, later])
        expected = case.project(request)
        original, changed = replay._same, []

        def compare(owner, left, right):
            result = original(owner, left, right)
            if result and type(left) is dict and type(right) is dict \
                    and set(left) == fixtures.PAGE_KEYS and left is not right:
                left['content'] = 'unused candidate changed after comparison'
                changed.append(True)
            return result

        with mock.patch.object(replay, '_same', compare):
            actual = case.project(request)
        self.assertTrue(changed, 'real version collision comparison did not run')
        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
