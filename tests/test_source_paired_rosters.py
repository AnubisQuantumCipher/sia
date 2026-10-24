"""Typed refusal and finite traversal controls; no callback isolation claim."""
import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bin'))
source = importlib.import_module('siasourcebatch')


def encode(_owner, value):
    return json.dumps(value, sort_keys=True).encode()


class PairedRosters(unittest.TestCase):
    def test_order_identity_and_empty_rosters(self):
        left, right = [object(), object()], [object(), object()]
        pairs = list(source._paired_rows(left, right, 'source-catalog-roster'))
        self.assertEqual(pairs, [(left[0], right[0]), (left[1], right[1])])
        self.assertEqual(list(source._paired_rows([], [], 'source-catalog-roster')), [])

    def test_initial_mismatch_is_typed_in_both_directions(self):
        for left, right in (([], [1]), ([1], [])):
            with self.subTest(left=left, right=right):
                with self.assertRaises(source.SourceBatchRefusal) as caught:
                    list(source._paired_rows(left, right, 'source-catalog-roster'))
                self.assertEqual(caught.exception.reason, 'source-catalog-roster')

    def test_mutation_during_traversal_is_typed_and_bounded(self):
        mutations = ('left-shrink', 'right-shrink', 'both-shrink',
                     'left-grow', 'right-grow', 'both-grow')
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                left, right = [1, 2], [3, 4]
                pairs = source._paired_rows(left, right, 'cursor-proposal-contract')
                self.assertEqual(next(pairs), (1, 3))
                targets = (left, right) if mutation.startswith('both') else (
                    left if mutation.startswith('left') else right,)
                for target in targets:
                    if mutation.endswith('grow'):
                        target.append(5)
                    else:
                        target.pop()
                with self.assertRaises(source.SourceBatchRefusal) as caught:
                    list(pairs)
                self.assertEqual(caught.exception.reason, 'cursor-proposal-contract')

    def test_body_value_error_is_not_reclassified(self):
        failure = ValueError('fixture body error')
        with self.assertRaises(ValueError) as caught:
            for _pair in source._paired_rows([1], [2], 'refusal-intent-roster'):
                raise failure
        self.assertIs(caught.exception, failure)

    def test_same_length_replacement_is_not_claimed_detected(self):
        left, right = [1, 2], [3, 4]
        pairs = source._paired_rows(left, right, 'source-catalog-roster')
        self.assertEqual(next(pairs), (1, 3))
        left[1] = 5
        self.assertEqual(list(pairs), [(5, 4)])

    def test_event_callback_roster_mutation_refuses_before_plan(self):
        for mutation in ('append', 'clear'):
            with self.subTest(mutation=mutation):
                event = object()
                events = [event]
                record = {'organ': 'fixture', 'ts': '2026-10-24T00:00:00Z'}
                records = [record]
                calls = []

                def replay(value, *, calls=calls, mutation=mutation,
                           events=events, record=record):
                    calls.append(value)
                    if mutation == 'append':
                        events.append(object())
                    else:
                        events.clear()
                    return record

                planner = Mock(side_effect=AssertionError('planner must not run'))
                owner = {'_event_replay_record': replay, '_prepare_event_page_plan': planner}
                with patch.object(source, '_component_bytes', side_effect=encode), \
                        patch.object(source, '_epoch_current', return_value=None):
                    with self.assertRaises(source.SourceBatchRefusal) as caught:
                        source._plan_events(owner, {'events': [('fixture', events, records)]},
                                            Mock(), Mock(), None, None)
                self.assertEqual(caught.exception.reason, 'source-event-roster-changed')
                self.assertEqual(calls, [event])
                planner.assert_not_called()


if __name__ == '__main__':
    unittest.main()
