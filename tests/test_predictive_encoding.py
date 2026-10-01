"""Prequential relative novelty and context-surprisal encoding contracts.

Xu et al. (2021), PLOS Computational Biology, equations 1–2 and discussion
'Novelty is not surprise' distinguish state frequency from conditional
expectations: https://doi.org/10.1371/journal.pcbi.1009070
Poole & Mackworth, section 7.8, supplies Dirichlet count updates:
https://www.cs.ubc.ca/~poole/aibook/html1e/ArtInt_196.html
Lisman & Grace (2005), doi:10.1016/j.neuron.2005.05.002, motivates the
separate novelty-to-plasticity hypothesis, not a numeric gain equation.

The capped linear encoding map is an explicit engineering hypothesis. No
dopamine, SurNoR replication, conditional i.i.d. validity or recall win is
claimed. Tests use privately supplied event traces, never resident history.
"""

import copy
from fractions import Fraction
import hashlib
import importlib
import inspect
import json
import math
from pathlib import Path
import sys
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'bin'))
LN = json.loads((REPO / 'tests/fixtures/novelty-ln-v1.json').read_text())['ln']
POLICY = {
    'v': 1, 'algorithm': 'dirichlet-prequential-information-v1',
    'time_unit': 'unix-seconds-integer', 'pseudocount': 1,
    'signal': 'relative-novelty', 'strength_base': 1,
    'strength_scale': 1, 'strength_cap': 8,
    'max_events': 4096, 'max_symbols': 256, 'max_contexts': 256,
}
EXACT_NON_CLAIMS = [
    'NOT formal-bounded: this lane carries no Lean-checked certificate',
    'The epistemic class above is the STRONGEST claim this result supports',
    'exact rational arithmetic (not yet checker-covered)',
]
# JACKAL status=exact, parsed inputs retained verbatim. This does not grant
# exact assurance to the module's local floating-point probabilities.
RATIONALS = {
    '(0+1)/(0+2)': '1/2', '(1+1)/(1+2)': '2/3',
    '(0+1)/(2+2)': '1/4', '(2+1)/(3+2)': '3/5',
    '(2+1)/(2+2)': '3/4', '(0+2)/(0+2*2)': '1/2',
    '(1+2)/(1+2*2)': '3/5',
    '9007199254740991+1': '9007199254740992',
    '4096+1': '4097', '256+1': '257',
}


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def trace():
    rows = [('a', 96, 'pass', 'alpha'), ('b', 97, 'pass', 'alpha'),
            ('c', 98, 'fail', 'beta'), ('d', 99, 'pass', 'alpha')]
    return {'v': 1, 'complete': True, 'symbols': ['pass', 'fail'],
            'contexts': ['alpha', 'beta'], 'events': [
                {'id': identity, 'timestamp': stamp, 'symbol': symbol,
                 'context': context, 'origin': 'evidence', 'source_sha256': 'a' * 64}
                for identity, stamp, symbol, context in rows]}


class PredictiveEncoding(unittest.TestCase):
    def setUp(self):
        try:
            self.component = importlib.import_module('siaencoding')
        except ModuleNotFoundError as exc:
            self.fail(f'prequential encoding component must exist: {exc}')

    def run_trace(self, value=None, policy=None, observed_at=100):
        return self.component.replay_encoding(
            trace() if value is None else value, observed_at=observed_at,
            policy=copy.deepcopy(POLICY) if policy is None else policy)

    def assert_information(self, row, probability):
        self.assertEqual(row['probability'], float(Fraction(probability)))
        # Negate the observed local score for comparison with the original
        # ln(p) enclosure; no locally derived enclosure is substituted.
        local_log = Fraction.from_float(-row['information_nats'])
        bound = LN[probability]['result']
        self.assertGreaterEqual(local_log, Fraction(bound['enclosure_lo']))
        self.assertLessEqual(local_log, Fraction(bound['enclosure_hi']))

    def test_public_api_requires_all_policy_inputs_and_observation_time(self):
        sig = inspect.signature(self.component.replay_encoding)
        for key in ('policy', 'observed_at'):
            self.assertIs(sig.parameters[key].default, inspect.Parameter.empty)
            self.assertEqual(sig.parameters[key].kind, inspect.Parameter.KEYWORD_ONLY)
        for key in POLICY:
            policy = copy.deepcopy(POLICY)
            del policy[key]
            with self.subTest(key=key), self.assertRaises(self.component.EncodingRefusal):
                self.run_trace(policy=policy)

    def test_predicts_before_each_event_and_updates_complete_counts_after_it(self):
        result = self.run_trace()
        for row, probability in zip(result['events'], ('1/2', '2/3', '1/4', '3/5'), strict=True):
            self.assert_information(row['relative_novelty'], probability)
        self.assertEqual(result['events'][0]['relative_novelty']['prior_count'], 0)
        self.assertEqual(result['events'][0]['relative_novelty']['prior_total'], 0)
        self.assertEqual(result['final_counts'], {'global': {'pass': 3, 'fail': 1},
                                                'contexts': {'alpha': {'pass': 3, 'fail': 0},
                                                             'beta': {'pass': 0, 'fail': 1}}})

    def test_repetition_weakens_new_encoding_but_unexpected_symbol_encodes_stronger(self):
        rows = self.run_trace()['events']
        self.assertGreater(rows[0]['encoding_strength'], rows[1]['encoding_strength'])
        self.assertGreater(rows[2]['encoding_strength'], rows[0]['encoding_strength'])
        self.assertTrue(all(row['encoding_strength'] > 0 for row in rows))

    def test_global_rarity_and_context_prediction_are_distinct_and_declared(self):
        result = self.run_trace()
        row = result['events'][-1]
        self.assert_information(row['relative_novelty'], '3/5')
        self.assert_information(row['context_surprisal'], '3/4')
        self.assert_information(result['events'][2]['context_surprisal'], '1/2')
        alternate = self.run_trace(policy={**POLICY, 'signal': 'context-surprisal'})
        self.assertLess(alternate['events'][-1]['encoding_strength'], row['encoding_strength'])
        self.assertNotEqual(alternate['policy_sha256'], result['policy_sha256'])

    def test_future_observations_never_retroactively_change_old_encoding(self):
        value = trace()
        prefix = copy.deepcopy(value)
        prefix['events'] = prefix['events'][:1]
        self.assertEqual(self.run_trace(prefix)['events'], self.run_trace(value)['events'][:1])

    def test_declared_prior_changes_prediction_and_is_not_hidden_fitted_state(self):
        rows = self.run_trace(policy={**POLICY, 'pseudocount': 2})['events']
        self.assert_information(rows[0]['relative_novelty'], '1/2')
        self.assert_information(rows[1]['relative_novelty'], '3/5')

    def test_engineering_strength_map_has_explicit_zero_scale_and_cap_decisions(self):
        neutral = self.run_trace(policy={**POLICY, 'strength_scale': 0})
        self.assertTrue(all(row['encoding_strength'] == 1 for row in neutral['events']))
        capped = self.run_trace(policy={**POLICY, 'strength_cap': 1})
        self.assertTrue(all(row['encoding_strength'] == 1 and row['capped'] for row in capped['events']))

    def test_every_event_origin_and_source_remain_unchanged_even_with_zero_gain(self):
        value = trace()
        for event, origin in zip(value['events'], ('evidence', 'derived', 'model', 'legacy-unlabeled'), strict=True):
            event['origin'] = origin
        before = copy.deepcopy(value)
        result = self.run_trace(value, {**POLICY, 'strength_scale': 0})
        self.assertEqual(value, before)
        self.assertEqual([row['event'] for row in result['events']], value['events'])
        result['events'][0]['event']['origin'] = 'model'
        self.assertEqual(value, before)
        self.assertEqual(result['trace_sha256'], sha(value))
        self.assertEqual(result['status'], 'computed-unverified')
        self.assertEqual(result['component'], 'prediction-conditioned-encoding')
        self.assertTrue(result['non_claims'])
        self.assertNotIn('heldout_win', result)

    def test_replay_is_deterministic_without_a_clock_or_ambient_memory(self):
        value = trace()
        self.assertEqual(self.run_trace(value), self.run_trace(copy.deepcopy(value)))
        with mock.patch('time.time', side_effect=AssertionError('ambient time')):
            self.assertEqual(self.run_trace(value), self.run_trace(value))

    def test_incomplete_unbounded_or_aggregate_history_refuses_without_guessing(self):
        for extra in ({'complete': False}, {'counts': {'pass': 3}}, {'v': True},
                      {'events': None}, {'symbols': []}, {'contexts': []}):
            with self.subTest(extra=extra), self.assertRaises(self.component.EncodingRefusal):
                self.run_trace({**trace(), **extra})
        value = trace()
        value['events'] = []
        result = self.run_trace(value)
        self.assertEqual(result['events'], [])

    def test_duplicate_unknown_malformed_and_reverse_events_refuse_atomically(self):
        variations = []
        for key, bad in (('id', 'a'), ('symbol', 'unknown'), ('context', 'unknown'),
                         ('origin', 'promoted'), ('source_sha256', 'not-a-digest'),
                         ('timestamp', 95), ('timestamp', True), ('timestamp', 100.0),
                         ('timestamp', 9007199254740992), ('timestamp', 101),
                         ('weight', 8)):
            value = trace()
            value['events'][-1][key] = bad
            variations.append(value)
        for value in variations:
            before = copy.deepcopy(value)
            with self.subTest(value=value), self.assertRaises(self.component.EncodingRefusal):
                self.run_trace(value)
            self.assertEqual(value, before)

    def test_rosters_are_unique_canonical_bounded_and_not_inferred_from_future(self):
        for key in ('symbols', 'contexts'):
            for roster in (['a', 'a'], [''], ['x' * 4097], [True], [' space']):
                with self.subTest(key=key, roster=roster), self.assertRaises(self.component.EncodingRefusal):
                    self.run_trace({**trace(), key: roster})

    def test_numeric_and_capacity_admission_precedes_log_and_copy(self):
        invalid = [('strength_base', 0), ('strength_base', -1), ('strength_cap', 0),
                   ('strength_scale', True), ('strength_scale', -1), ('strength_scale', '1'),
                   ('strength_scale', float('nan')), ('strength_scale', float('inf')),
                   ('strength_scale', 1e308), ('pseudocount', 0), ('pseudocount', 0.5),
                   ('pseudocount', True), ('max_events', 1), ('max_events', 4097),
                   ('max_symbols', 1), ('max_contexts', 257), ('signal', 'dopamine'),
                   ('time_unit', 'milliseconds'), ('hidden_weights', {})]
        with mock.patch.object(self.component.math, 'log', side_effect=AssertionError('numeric work before admission')), \
                mock.patch.object(self.component.copy, 'deepcopy', side_effect=AssertionError('copy before admission')):
            for key, bad in invalid:
                with self.subTest(key=key, bad=repr(bad)), self.assertRaises(self.component.EncodingRefusal):
                    self.run_trace(policy={**POLICY, key: bad})

    def test_whole_input_byte_budget_refuses_before_hash_copy_or_numerics(self):
        with mock.patch.object(self.component, 'MAX_INPUT_BYTES', 1), \
                mock.patch.object(self.component.copy, 'deepcopy', side_effect=AssertionError('copy')), \
                mock.patch.object(self.component.math, 'log', side_effect=AssertionError('log')):
            with self.assertRaisesRegex(self.component.EncodingRefusal, 'byte'):
                self.run_trace(policy=POLICY)

    def test_positive_strength_gain_underflow_refuses_without_dropping_an_event(self):
        value = trace()
        before = copy.deepcopy(value)
        # Observe the runtime's smallest positive float; no calculated expected
        # score or new JACKAL assurance is assigned to this refusal fixture.
        smallest_positive = math.ulp(0.0)
        policy = {**POLICY, 'strength_base': smallest_positive,
                  'strength_scale': smallest_positive}
        with self.assertRaisesRegex(self.component.EncodingRefusal, 'underflow'):
            self.run_trace(value, policy)
        self.assertEqual(value, before)

    def test_positive_strength_gain_lost_to_addition_rounding_refuses(self):
        value = trace()
        before = copy.deepcopy(value)
        policy = {**POLICY, 'strength_scale': math.ulp(0.0)}
        with self.assertRaisesRegex(self.component.EncodingRefusal, 'rounding-loss'):
            self.run_trace(value, policy)
        self.assertEqual(value, before)

    def test_whole_input_byte_budget_precedes_hash_construction(self):
        with mock.patch.object(self.component, 'MAX_INPUT_BYTES', 1), \
                mock.patch.object(self.component.hashlib, 'sha256',
                                  side_effect=AssertionError('hash before byte admission')):
            with self.assertRaisesRegex(self.component.EncodingRefusal, 'byte'):
                self.run_trace(policy=POLICY)


if __name__ == '__main__':
    unittest.main()
