"""New diagnostic worker observations, never retrospective heldout timing."""
import copy
import importlib
import unittest
from unittest import mock

import siacognitivemeasure as measurement
from tests import test_cognitive_live_comparison as comparisons
from tests import test_cognitive_exposure_timing as timing_tests


class CognitiveLiveTiming(unittest.TestCase):
    def setUp(self):
        self.fx = comparisons.CognitiveLiveComparison(methodName='runTest')
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.inputs = {'replay_inputs': self.fx.fixture.replay,
            'live_capture': self.fx.fixture.capture,
            'expected_live_capture_sha256': self.fx.fixture.capture['capture_sha256'],
            'ranking_policy': self.fx.policy,
            'expected_ranking_policy_sha256': comparisons.live_tests.digest(self.fx.policy)}
        self.source = measurement.prepare_live_comparison_v2(**self.inputs)

    def call(self, **overrides):
        module = importlib.import_module('siacognitivelivetiming')
        policy = copy.deepcopy(module.POLICY)
        producer = timing_tests.producer_fixture()
        return module.observe_live_comparison(**{
            'comparison_inputs': self.inputs,
            'expected_comparison_sha256': self.source['comparison_sha256'],
            'timing_policy': policy,
            'expected_timing_policy_sha256': comparisons.live_tests.digest(policy),
            'producer_expectations': producer,
            'expected_producer_sha256': comparisons.live_tests.digest(producer), **overrides})

    def test_real_worker_observation_retains_comparison_without_composed_latency(self):
        result = self.call()
        self.assertEqual(result['comparison'], self.source)
        self.assertEqual(result['claim_gate'], 'not-authorized')
        self.assertEqual(result['status'], 'observed')
        self.assertEqual([row['query_id'] for row in result['query_spans']],
                         [query['id'] for query in self.source['live_history']['queries']])
        for span, request in zip(result['query_spans'], result['jackal_requests'], strict=True):
            self.assertGreaterEqual(span['end_ns'], span['start_ns'])
            self.assertEqual(request['arguments']['expression'],
                             str(span['end_ns']) + '-' + str(span['start_ns']))
        self.assertNotIn('total_ms', result)

    def test_bad_comparison_pin_precedes_clock(self):
        with mock.patch('time.perf_counter_ns', side_effect=AssertionError('early clock')):
            with self.assertRaises(ValueError):
                self.call(expected_comparison_sha256='0' * 64)

    def test_policy_cannot_claim_heldout_confirmation(self):
        module = importlib.import_module('siacognitivelivetiming')
        policy = {**module.POLICY, 'purpose': 'heldout-confirmation'}
        with mock.patch('time.perf_counter_ns', side_effect=AssertionError('early clock')):
            with self.assertRaises(ValueError):
                self.call(timing_policy=policy,
                          expected_timing_policy_sha256=comparisons.live_tests.digest(policy))

    def test_reversed_clock_is_rejected(self):
        with mock.patch('time.perf_counter_ns', side_effect=[130, 100]):
            with self.assertRaisesRegex(ValueError, 'clock'):
                self.call()

    def test_timed_worker_mutation_refuses(self):
        original = measurement._rank_live_query
        timing = False

        def clock():
            nonlocal timing
            timing = True
            return 100

        def worker(**kw):
            result = original(**kw)
            if timing:
                kw['rows'][0]['origin'] = 'model'
            return result

        with mock.patch('time.perf_counter_ns', side_effect=clock), \
                mock.patch.object(measurement, '_rank_live_query', side_effect=worker):
            with self.assertRaisesRegex(ValueError, 'worker'):
                self.call()

    def test_output_budget_admission_precedes_clock(self):
        module = importlib.import_module('siacognitivelivetiming')
        with mock.patch.object(module, 'MAX_OUTPUT_BYTES', 100), \
                mock.patch('time.perf_counter_ns', side_effect=AssertionError('early clock')):
            with self.assertRaises(ValueError):
                self.call()
