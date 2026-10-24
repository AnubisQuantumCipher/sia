"""Retained replay must preserve first aliases and early refusal frontiers."""
import hashlib
import unittest
from unittest import mock

import siaeventintake as replay
from tests import test_event_live_intake as fixtures


def replace_content(version):
    version['content'] = 'changed first callback mapping\n'
    pin = hashlib.sha256(version['content'].encode('utf-8')).hexdigest()
    version['source_sha256'] = pin
    version['content_sha256'] = pin
    version['version_sha256'] = fixtures.digest({key: version[key] for key in (
        'subject', 'content_sha256', 'source_sha256', 'origin')})


class ReplayTransitionOrder(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.EventLiveIntakeProjection(methodName='runTest')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def repeated(self):
        event = self.case.event()
        first = self.case.entry({'sense_custom:alpha': [event]})
        self.case.publish_entry_fixture(first)
        later = self.case.entry({'sense_custom:alpha': [event]}, batch_id='duplicate-version')
        return self.case.request([first, later])

    def test_equal_replay_retains_first_mapping_until_final_identity_check(self):
        request = self.repeated()
        real_member, real_version = replay._member, replay.pages._checked_version
        real_derive = replay._derive_association
        stages, retained, equal_calls, changed = [], [], [], []
        phase = {'fold': False}

        def member(*args):
            phase['fold'] = False
            result = real_member(*args)
            stages.append(True)
            phase['fold'] = True
            return result

        def version(*args, **kwargs):
            result = real_version(*args, **kwargs)
            if phase['fold']:
                if len(stages) == 1:
                    retained.append(result)
                elif result['version_sha256'] == retained[0]['version_sha256']:
                    equal_calls.append(result)
            return result

        def derive(*args):
            if len(equal_calls) == 2 and not changed:
                replace_content(retained[0])
                changed.append(True)
            return real_derive(*args)

        with mock.patch.object(replay, '_member', member), \
                mock.patch.object(replay.pages, '_checked_version', version), \
                mock.patch.object(replay, '_derive_association', derive):
            with self.assertRaises(ValueError) as caught:
                self.case.project(request)
        self.assertTrue(changed, 'mutation must follow the equal before-image replay')
        self.assertEqual(len(equal_calls), 2)
        self.assertIsNot(equal_calls[0], retained[0])
        self.assertEqual(caught.exception.reason, 'page-version-identity-changed')

    def fold(self, request, versions, current, trace):
        intake = replay._intake(request)
        real_member, real_version = replay._member, replay.pages._checked_version

        def member(*args):
            result = real_member(*args)
            trace.clear()
            return result

        def version(*args, **kwargs):
            trace.append(('projector', kwargs.get('before', False)))
            return real_version(*args, **kwargs)

        with mock.patch.object(replay, '_member', member), \
                mock.patch.object(replay.pages, '_checked_version', version):
            replay._fold_entry(vars(self.case.lib), request, request['history']['entries'][0],
                               intake, [], versions, current, {})

    def test_before_mismatch_refuses_before_next_projector(self):
        request = self.case.request()
        expected = self.case.project(request)
        version = dict(expected['intake']['pages'][0])
        # A controlled predecessor is inconsistent with the first plan's absent before image.
        trace = []
        with self.assertRaises(ValueError) as caught:
            self.fold(request, {version['version_sha256']: version},
                      {version['subject']: version['version_sha256']}, trace)
        self.assertEqual(caught.exception.reason, 'unexplained-page-version-change')
        self.assertEqual(trace, [])

    def test_collision_refuses_before_later_projector(self):
        request = self.case.request()
        expected = self.case.project(request)
        first = dict(expected['intake']['pages'][0])
        first['content'] = 'controlled inconsistent private predecessor'
        trace = []
        with self.assertRaises(ValueError) as caught:
            self.fold(request, {first['version_sha256']: first}, {}, trace)
        self.assertEqual(caught.exception.reason, 'page-version-collision')
        self.assertEqual(trace, [('projector', False)])


if __name__ == '__main__':
    unittest.main()
