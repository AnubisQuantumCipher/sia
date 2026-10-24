"""Admitted replay rosters cannot extend callback traversal indefinitely."""
import copy
from types import SimpleNamespace
import unittest
from unittest import mock

import siaeventintake as replay
from tests import test_event_live_intake as fixtures


def change_rows(rows, change):
    if change == 'grow':
        rows.append(rows[-1])
    else:
        rows.pop()


class IntakeBoundedTraversal(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.EventLiveIntakeProjection(methodName='runTest')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def request(self):
        entry = self.case.entry({'sense_custom:alpha': [
            self.case.event(occurrence='bounded:first'),
            self.case.event(occurrence='bounded:second')]})
        request = copy.deepcopy(self.case.request([entry]))
        self.case.project(request)
        return request

    def fold(self, request, owner=None):
        intake, associations, versions, current, first = replay._intake(request), [], {}, {}, {}
        replay._fold_entry(vars(self.case.lib) if owner is None else owner, request,
                           request['history']['entries'][0], intake,
                           associations, versions, current, first)
        return intake, associations, versions, current, first

    def test_decoder_growth_stops_at_initial_event_count(self):
        request = self.request()
        events = request['history']['entries'][0]['source_returns']['runs'][0]['events']
        original, calls, limit = self.case.lib._event_from_replay_record, [], len(events)

        def decoder(record):
            calls.append(record['event_id'])
            if len(calls) > limit + 2:
                raise AssertionError('test sentinel: original traversal continues growing')
            events.append(record)
            return original(record)

        owner = dict(vars(self.case.lib), _event_from_replay_record=decoder)
        with mock.patch.object(replay, '_member', wraps=replay._member) as member:
            with self.assertRaises(ValueError) as caught:
                self.fold(request, owner)
        self.assertEqual(caught.exception.reason, 'returned-event-roster-changed')
        self.assertEqual(len(calls), limit)
        member.assert_not_called()

    def test_decoder_shrink_refuses_before_member_processing(self):
        request = self.request()
        events = request['history']['entries'][0]['source_returns']['runs'][0]['events']
        original, calls = self.case.lib._event_from_replay_record, []

        def decoder(record):
            calls.append(record['event_id'])
            events.pop()
            return original(record)

        owner = dict(vars(self.case.lib), _event_from_replay_record=decoder)
        with mock.patch.object(replay, '_member', wraps=replay._member) as member:
            with self.assertRaises(ValueError) as caught:
                self.fold(request, owner)
        self.assertEqual(caught.exception.reason, 'returned-event-roster-changed')
        self.assertEqual(len(calls), 1)
        member.assert_not_called()

    def test_association_event_drift_refuses_instead_of_returning_partial_roster(self):
        for change in ('grow', 'shrink'):
            with self.subTest(change=change):
                request = self.request()
                events = request['history']['entries'][0]['source_returns']['runs'][0]['events']
                real, calls, limit = replay._derive_association, [], len(events)

                def derive(*args, events=events, real=real, calls=calls,
                           limit=limit, change=change):
                    calls.append(True)
                    if len(calls) > limit + 2:
                        raise AssertionError('test sentinel: growing association traversal')
                    result = real(*args)
                    change_rows(events, change)
                    return result

                with mock.patch.object(replay, '_derive_association', derive):
                    with self.assertRaises(ValueError) as caught:
                        self.fold(request)
                self.assertEqual(caught.exception.reason, 'returned-event-roster-changed')
                self.assertLessEqual(len(calls), limit)

    def test_association_source_drift_refuses(self):
        for change in ('grow', 'shrink'):
            with self.subTest(change=change):
                request = self.request()
                rows = request['history']['entries'][0]['source_returns']['runs']
                real, calls = replay._derive_association, []

                def derive(*args, rows=rows, real=real, calls=calls, change=change):
                    result = real(*args)
                    calls.append(True)
                    if len(calls) == 1:
                        change_rows(rows, change)
                    return result

                with mock.patch.object(replay, '_derive_association', derive):
                    with self.assertRaises(ValueError) as caught:
                        self.fold(request)
                self.assertEqual(caught.exception.reason, 'complete-collector-roster')
                self.assertEqual(len(calls), 2)

    def test_member_callback_batch_drift_refuses_before_another_batch(self):
        for change in ('grow', 'shrink'):
            with self.subTest(change=change):
                request = self.request()
                rows = request['history']['entries'][0]['event_batches']
                real, calls = replay._member, []

                def member(*args, rows=rows, real=real, calls=calls, change=change):
                    result = real(*args)
                    calls.append(True)
                    change_rows(rows, change)
                    return result

                with mock.patch.object(replay, '_member', member):
                    with self.assertRaises(ValueError) as caught:
                        self.fold(request)
                self.assertEqual(caught.exception.reason, 'complete-event-batch-roster')
                self.assertEqual(len(calls), 1)

    def test_completed_entry_history_drift_refuses_before_another_fold(self):
        for change in ('grow', 'shrink'):
            with self.subTest(change=change):
                request = self.request()
                rows = request['history']['entries']
                real, calls = replay._fold_entry, []

                def fold(*args, rows=rows, real=real, calls=calls, change=change):
                    result = real(*args)
                    calls.append(True)
                    change_rows(rows, change)
                    return result

                with mock.patch.object(replay, '_fold_entry', fold):
                    with self.assertRaises(ValueError) as caught:
                        replay._project(vars(self.case.lib), request)
                self.assertEqual(caught.exception.reason, 'history-entry-roster-changed')
                self.assertEqual(len(calls), 1)

    def test_valid_folding_keeps_unchanged_input_and_complete_result(self):
        request = self.request()
        before = copy.deepcopy(request)
        expected = self.case.project(request)
        intake, associations, versions, current, _first = self.fold(request)
        intake['pages'], intake['current_versions'] = list(versions.values()), list(current.values())
        self.assertEqual(intake, expected['intake'])
        self.assertEqual(associations, expected['associations'])
        self.assertEqual(request, before)

    def member_inputs(self):
        request = self.request()
        plans = request['history']['entries'][0]['event_batches'][0]['batch']['members']
        return plans[0], replay.pages._union_images(vars(self.case.lib), plans)

    def test_member_decoder_cannot_grow_or_shrink_input_roster(self):
        for change in ('grow', 'shrink'):
            with self.subTest(change=change):
                plan, images = self.member_inputs()
                rows, calls = plan['input_records'], []
                real, limit = self.case.lib._event_from_replay_record, len(rows)

                def decode(record, rows=rows, calls=calls, real=real, limit=limit, change=change):
                    calls.append(True)
                    if len(calls) > limit + 2:
                        raise AssertionError('test sentinel: growing member inputs')
                    value = real(record)
                    change_rows(rows, change)
                    return value

                owner = dict(vars(self.case.lib), _event_from_replay_record=decode)
                with self.assertRaises(ValueError) as caught:
                    replay._member(owner, plan, images)
                self.assertEqual(caught.exception.reason, 'plan-record-roster-changed')
                self.assertLessEqual(len(calls), limit)

    def test_page_state_callback_cannot_grow_or_shrink_page_roster(self):
        for change in ('grow', 'shrink'):
            with self.subTest(change=change):
                plan, images = self.member_inputs()
                rows, calls = plan['pages'], []
                real, limit = self.case.lib._event_page_state, len(rows)

                def state(*args, rows=rows, calls=calls, real=real,
                          limit=limit, change=change, **kwargs):
                    calls.append(True)
                    if len(calls) > limit + 2:
                        raise AssertionError('test sentinel: growing page roster')
                    value = real(*args, **kwargs)
                    change_rows(rows, change)
                    return value

                owner = dict(vars(self.case.lib), _event_page_state=state)
                with self.assertRaises(ValueError) as caught:
                    replay._member(owner, plan, images)
                self.assertEqual(caught.exception.reason, 'complete-target-page-roster')
                self.assertLessEqual(len(calls), limit)

    def test_marker_callback_cannot_change_admission_roster(self):
        for change in ('grow', 'shrink'):
            with self.subTest(change=change):
                plan, images = self.member_inputs()
                rows, calls = plan['admissions'], []
                real = self.case.lib.EVENT_MARKER_RE

                def fullmatch(line, rows=rows, calls=calls, real=real, change=change):
                    calls.append(True)
                    if len(calls) == 1:
                        change_rows(rows, change)
                    return real.fullmatch(line)

                owner = dict(vars(self.case.lib), EVENT_MARKER_RE=SimpleNamespace(fullmatch=fullmatch))
                with self.assertRaises(ValueError) as caught:
                    replay._member(owner, plan, images)
                self.assertEqual(caught.exception.reason, 'complete-plan-admissions')

    def test_marker_callback_cannot_extend_target_line_traversal(self):
        plan, images = self.member_inputs()
        real_state, real_pattern = self.case.lib._event_page_state, self.case.lib.EVENT_MARKER_RE
        retained, calls = [], []

        def state(*args, **kwargs):
            value = real_state(*args, **kwargs)
            retained.append(value['bullets'])
            return value

        def fullmatch(line):
            calls.append(True)
            if len(calls) > 4:
                raise AssertionError('test sentinel: growing marker traversal')
            retained[0].append(line)
            return real_pattern.fullmatch(line)

        owner = dict(vars(self.case.lib), _event_page_state=state,
                     EVENT_MARKER_RE=SimpleNamespace(fullmatch=fullmatch))
        with self.assertRaises(ValueError) as caught:
            replay._member(owner, plan, images)
        self.assertEqual(caught.exception.reason, 'event-marker-roster-changed')
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
