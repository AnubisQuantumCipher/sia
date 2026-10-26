"""Replay must refuse source-roster drift before page/member processing."""
import copy
import unittest
from unittest import mock

import siaeventintake as replay
from tests import test_event_live_intake as fixtures

MUTATIONS = ('left-shrink', 'right-shrink', 'both-shrink',
             'left-grow', 'right-grow', 'both-grow')


def mutate(left, right, change):
    targets = (left, right) if change.startswith('both') else (
        left if change.startswith('left') else right,)
    for target in targets:
        if change.endswith('grow'):
            target.append(copy.deepcopy(target[-1]))
        else:
            target.pop()


class IntakePairedRosters(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.EventLiveIntakeProjection(methodName='runTest')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def fold(self, owner, request):
        intake, associations, versions, current, first = replay._intake(request), [], {}, {}, {}
        replay._fold_entry(owner, request, request['history']['entries'][0],
                           intake, associations, versions, current, first)
        return intake, associations, versions, current, first

    def test_decoder_roster_drift_refuses_before_member_processing(self):
        for change in MUTATIONS:
            with self.subTest(change=change):
                request = copy.deepcopy(self.case.request())
                self.case.project(request)  # Valid unchanged front-door control.
                left = request['source_catalog']['sources']
                right = request['history']['entries'][0]['source_returns']['runs']
                original, calls = self.case.lib._event_from_replay_record, []

                def decoder(record, *, left=left, right=right, calls=calls,
                            original=original, change=change):
                    calls.append(record['event_id'])
                    if len(calls) == 1:
                        mutate(left, right, change)
                    return original(record)

                owner = dict(vars(self.case.lib), _event_from_replay_record=decoder)
                with mock.patch.object(replay, '_member', wraps=replay._member) as member:
                    with self.assertRaises(ValueError) as caught:
                        self.fold(owner, request)
                self.assertEqual(caught.exception.reason, 'complete-collector-roster')
                member.assert_not_called()
                self.assertLessEqual(len(calls), 2)

    def test_initial_roster_mismatch_refuses_before_decoder(self):
        for side in ('left', 'right'):
            with self.subTest(side=side):
                request = copy.deepcopy(self.case.request())
                left = request['source_catalog']['sources']
                right = request['history']['entries'][0]['source_returns']['runs']
                (left if side == 'left' else right).pop()
                decoder = mock.Mock(side_effect=AssertionError('decoder must not run'))
                owner = dict(vars(self.case.lib), _event_from_replay_record=decoder)
                with self.assertRaises(ValueError) as caught:
                    self.fold(owner, request)
                self.assertEqual(caught.exception.reason, 'complete-collector-roster')
                decoder.assert_not_called()

    def test_decoder_failure_keeps_original_identity(self):
        request = self.case.request()
        failure = ValueError('controlled decoder failure')
        owner = dict(vars(self.case.lib),
                     _event_from_replay_record=mock.Mock(side_effect=failure))
        with self.assertRaises(ValueError) as caught:
            self.fold(owner, request)
        self.assertIs(caught.exception, failure)

    def test_valid_roster_preserves_complete_fold(self):
        request = self.case.request()
        expected = self.case.project(request)
        intake, associations, versions, current, _first = self.fold(vars(self.case.lib), request)
        intake['pages'] = list(versions.values())
        intake['current_versions'] = list(current.values())
        self.assertEqual(intake, expected['intake'])
        self.assertEqual(associations, expected['associations'])


if __name__ == '__main__':
    unittest.main()
