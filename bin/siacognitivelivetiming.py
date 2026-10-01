"""New diagnostic timing of the live-use worker, never historical timing.

The complete comparison is replayed before clocks. This observer deliberately
cannot authorize a heldout claim or compose its worker spans with old raw runs.
Producer guards reuse the existing source/interpreter contract; neither those
guards nor clock observations attest the loaded heap or physical clock accuracy.
"""
import copy
import time

import siacognitiveenvelope as envelope
import siacognitiveexposuretiming as timing
import siacognitivemeasure as measurement

MAX_OUTPUT_BYTES = measurement.MAX_ARTIFACT_BYTES
POLICY = {
    'schema': 'sia-live-worker-diagnostic-timing-policy-v1',
    'purpose': 'new-post-inspection-diagnostic-only',
    'clock': 'time.perf_counter_ns', 'unit': 'ns',
    'schedule': 'query-order-live-use-once-v1',
    'scope': 'target-blind-worker-call-through-return-v1',
    'pre_observation': 'complete-untimed-comparison-replay-v2',
    'warmup': 'no-additional-warmup-cache-state-uncontrolled-v1',
    'raw_timings': 'retain-separate-no-composition-v1',
    'arithmetic': 'unevaluated-endpoint-differences-v1',
    'claim_gate': 'not-authorized',
}
NON_CLAIMS = [
    'This is a new diagnostic timed replay of an already supplied comparison, not timing of the earlier raw retrieval or untimed ranking run.',
    'Worker spans exclude admission, mandatory replay, hashing, output checks, source checks and metric preparation. No raw retrieval or complete pipeline duration is measured.',
    'Clock endpoints are local observations; eventual exact arithmetic cannot establish physical-clock accuracy, independent samples, comparative speed or statistical power.',
    'Mandatory untimed replay and prior activity leave cache state uncontrolled; there is no cold-start claim, additional warmup, retry or sample filtering.',
    'This diagnostic-only policy cannot earn a cognitive claim or retroactively supply missing timing pins to a heldout freeze.',
    'Source and interpreter generation guards do not attest the loaded Python heap, complete runtime, kernel or protection against hostile same-user mutation.',
    'The complete comparison and all nested baseline, source, history, activation and measurement nonclaims remain controlling.',
]
_REPLAY_LAYOUT = {key: None for key in (*measurement._SOURCE_KEYS, 'protocol',
    'expected_protocol_sha256', 'baseline', 'expected_baseline_sha256', 'expected_parameter_freeze_sha256')}
_LAYOUT = {'comparison_inputs': {'replay_inputs': _REPLAY_LAYOUT,
    'live_capture': None, 'expected_live_capture_sha256': None,
    'ranking_policy': None, 'expected_ranking_policy_sha256': None},
    'expected_comparison_sha256': None, 'timing_policy': None,
    'expected_timing_policy_sha256': None, 'producer_expectations': None,
    'expected_producer_sha256': None}


def _fail(reason):
    error = ValueError('live worker timing refused: ' + reason)
    error.non_claims = list(NON_CLAIMS)
    raise error


def _admit(kw):
    envelope.admit_compound(envelope=kw, layout=_LAYOUT,
        max_input_bytes=envelope.MAX_INPUT_BYTES, max_document_bytes=envelope.MAX_DOCUMENT_BYTES)
    if not measurement._same(kw['timing_policy'], POLICY):
        _fail('policy changes the fixed diagnostic-only observation contract')
    measurement._pin(kw['timing_policy'], kw['expected_timing_policy_sha256'])
    measurement._pin(kw['producer_expectations'], kw['expected_producer_sha256'])
    timing._producer_declaration(kw['producer_expectations'])
    if not measurement._digest(kw['expected_comparison_sha256']):
        _fail('independent comparison pin is missing')


def _body(kw, source, spans):
    return {'schema': 'sia-live-worker-diagnostic-timing-observation-v1',
        'status': 'observed', 'claim_gate': 'not-authorized', 'arithmetic_status': 'not-evaluated',
        'comparison': source, 'comparison_sha256': kw['expected_comparison_sha256'],
        'timing_policy': kw['timing_policy'], 'timing_policy_sha256': kw['expected_timing_policy_sha256'],
        'producer_expectations': kw['producer_expectations'], 'producer_sha256': kw['expected_producer_sha256'],
        'producer_checks': timing._PRODUCER_CHECKS, 'query_spans': spans,
        'jackal_requests': [{'tool': 'jackal_exact',
            'arguments': {'expression': str(span['end_ns']) + '-' + str(span['start_ns'])},
            'query_id': span['query_id'], 'unit': 'ns', 'metric': 'live_worker_duration_ns',
            'given': {'start_ns': span['start_ns'], 'end_ns': span['end_ns'],
                      'representation': 'bounded-json-integer-clock-endpoints-v1'}} for span in spans],
        'non_claims': list(NON_CLAIMS)}


def _observe(kw):
    _admit(kw)
    initial = timing._hash(kw, envelope.MAX_INPUT_BYTES)
    detached = copy.deepcopy(kw)
    _admit(detached)
    if timing._hash(detached, envelope.MAX_INPUT_BYTES) != initial:
        _fail('input generation changed while detaching')
    with timing._producer_sources(detached['producer_expectations']) as current:
        source = measurement.prepare_live_comparison_v2(**detached['comparison_inputs'])
        measurement._pin(source, detached['expected_comparison_sha256'], 'comparison_sha256')
        queries = source['live_history']['queries']
        if not 0 < len(queries) <= timing.MAX_QUERIES:
            _fail('complete query roster is outside capacity')
        policy = source['ranking_policy']
        prepared = []
        for query, order, activation in zip(queries, source['arms'][1]['query_orders'],
                                            source['activation'], strict=True):
            if query['id'] != order['id'] or query['id'] != activation['id']:
                _fail('query roster mismatch')
            arguments = {'rows': [{'row_ref': row['row_ref'], 'origin': row['origin'],
                'trace': None if row['history'] is None else row['history']['trace']}
                for row in query['rows']], 'observed_at': policy['observed_at'],
                'activation_policy': copy.deepcopy(policy['activation_policy'])}
            prepared.append((arguments, {'query_id': query['id'],
                'input_sha256': timing._hash(arguments),
                'output_sha256': timing._hash({'order': order['order'], 'activation': activation['receipt']})}))
        # Reserve widest admissible endpoint spellings before the first clock.
        reserved = [{**entry, 'start_ns': timing.MAX_CLOCK_NS, 'end_ns': timing.MAX_CLOCK_NS}
                    for _, entry in prepared]
        timing._finish(_body(detached, source, reserved), 'artifact_sha256', MAX_OUTPUT_BYTES)
        current()
        spans, previous = [], None
        for arguments, entry in prepared:
            if timing._hash(arguments) != entry['input_sha256']:
                _fail('worker input changed before clock')
            start = time.perf_counter_ns()
            result = measurement._rank_live_query(**arguments)
            end = time.perf_counter_ns()
            timing._span(start, end, previous, {'resources': {'max_clock_ns': timing.MAX_CLOCK_NS}})
            if timing._hash(arguments) != entry['input_sha256'] or timing._hash(result) != entry['output_sha256']:
                _fail('timed worker changed its input or differs from untimed replay')
            spans.append({**entry, 'start_ns': start, 'end_ns': end})
            previous = end
        measurement._pin(source, detached['expected_comparison_sha256'], 'comparison_sha256')
        if timing._hash(kw, envelope.MAX_INPUT_BYTES) != initial:
            _fail('caller generation changed during observation')
        result = timing._finish(_body(detached, source, spans), 'artifact_sha256', MAX_OUTPUT_BYTES)
        current()
        return result


def observe_live_comparison(*, comparison_inputs, expected_comparison_sha256, timing_policy,
                            expected_timing_policy_sha256, producer_expectations, expected_producer_sha256):
    """Observe the real worker once per query after complete replay and admission."""
    try:
        return _observe(locals())
    except (ValueError, RuntimeError, TypeError, KeyError, IndexError, OverflowError,
            RecursionError, OSError, StopIteration) as exc:
        # Sealed descriptor cleanup may wrap the original refusal. Retain the
        # exception chain and its boundaries instead of losing the reason.
        cause = exc.__cause__
        error = ValueError('live worker timing refused: ' + str(exc) +
                           ('; caused by: ' + str(cause) if cause is not None else ''))
        error.non_claims = list(NON_CLAIMS)
        error.upstream_non_claims = [getattr(item, 'non_claims', []) for item in (exc, cause)
                                    if item is not None]
        raise error from exc
