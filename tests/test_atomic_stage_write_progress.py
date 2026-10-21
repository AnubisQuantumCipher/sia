"""Actual atomic_install_file heredoc controls; separate from CAS/open/race acceptance."""
from pathlib import Path
import errno
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
CHILD = REPO / 'tests/fixtures/atomic-stage-write-progress-v1/child.py'
MAX_BYTES = 1_048_576


def generation(path):
    value = path.stat()
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


class AtomicStageWriteProgress(unittest.TestCase):
    def setUp(self):
        self.fixture = tempfile.TemporaryDirectory(prefix='sia-atomic-write-')
        self.addCleanup(self.fixture.cleanup)
        self.root = Path(self.fixture.name)

    def _program(self):
        with (REPO / 'install.sh').open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        self.assertLessEqual(len(data), MAX_BYTES)
        marker = b'atomic_install_file() {\n'
        self.assertEqual(data.count(marker), 1)
        function, separator, _ = data.partition(marker)[2].partition(b'\n}\n\nollama_client_version()')
        self.assertTrue(separator)
        opening = b'  if ! python3 - "$source" "$temporary" "$mode" <<\'PY\'\n'
        self.assertEqual(function.count(opening), 1)
        program, separator, _ = function.partition(opening)[2].partition(b'\nPY\n  then\n')
        self.assertTrue(separator)
        program += b'\n'
        path = self.root / 'actual-program.py'
        path.write_bytes(program)
        return path, hashlib.sha256(program).hexdigest()

    def _run(self, payload, fault='normal', mode='0755'):
        program, program_sha = self._program()
        source, stage, log = (self.root / name for name in ('source', 'stage', 'events.json'))
        source.write_bytes(payload)
        source.chmod(0o640)
        descriptor = os.open(stage, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        before = generation(source)
        try:
            result = subprocess.run([sys.executable, '-I', '-B', '-W', 'error',
                str(CHILD), str(program), str(source), str(stage), mode, fault, str(log)],
                capture_output=True, text=True, check=False, timeout=3, cwd=self.root)
        finally:
            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(generation(source), before)
            self.assertEqual(hashlib.sha256(program.read_bytes()).hexdigest(), program_sha)
            self.assertTrue(log.is_file())
            self.assertLessEqual(log.stat().st_size, MAX_BYTES)
            events = json.loads(log.read_text())['events']
            if fault == 'zero':
                self.assertEqual(events[0], {'kind':'write', 'offered':len(payload), 'returned':0})
                self.assertLessEqual(len(events), 3)
            print(json.dumps({'fault':fault, 'retained_event_log':events}, sort_keys=True))
        self.assertEqual(result.stderr, '')
        report = json.loads(result.stdout)
        print(result.stdout, end='')
        self.assertEqual(report['program_sha256'], program_sha)
        self.assertTrue(report['source_preserved'])
        self.assertEqual(report['source_sha256'], hashlib.sha256(payload).hexdigest())
        self.assertEqual(set(report['descriptors']), {str(source), str(stage)})
        self.assertTrue(all(report['closed_before_child_exit'].values()))
        return result, report

    def _complete(self, payload, fault='normal', mode='0755'):
        result, report = self._run(payload, fault, mode)
        self.assertEqual(result.returncode, 0)
        self.assertIsNone(report['failure'])
        self.assertEqual(report['stage_sha256'], hashlib.sha256(payload).hexdigest())
        self.assertEqual(report['stage_bytes'], len(payload))
        self.assertEqual(report['stage_mode'], int(mode, 8))
        events = report['events']
        names = [event['kind'] for event in events]
        self.assertEqual(names.count('fchmod'), 1)
        self.assertEqual(names.count('fsync'), 1)
        self.assertEqual(names[-2:], ['close', 'close'])
        self.assertLess(names.index('fchmod'), names.index('fsync'))
        self.assertLess(names.index('fsync'), len(names) - 2)
        writes = [i for i,event in enumerate(events) if event['kind'] == 'write']
        if writes:
            self.assertLess(writes[-1], names.index('fchmod'))
        for kind, previous_mode in (('fchmod', 0o600), ('fsync', int(mode, 8))):
            snapshot = events[names.index(kind)]['immediately_before']
            self.assertTrue(snapshot['exact_original_fixture'])
            self.assertEqual(snapshot['sha256'], hashlib.sha256(payload).hexdigest())
            self.assertEqual(snapshot['bytes'], len(payload))
            self.assertEqual(snapshot['mode'], previous_mode)
        self.assertEqual(events[names.index('fchmod')]['requested_mode'], int(mode, 8))
        return report

    def _refused(self, payload, fault, message):
        result, report = self._run(payload, fault)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report['failure'], {'type':'OSError', 'message':message})
        self.assertEqual(report['stage_mode'], 0o600)
        self.assertFalse(any(event['kind'] in ('fchmod', 'fsync') for event in report['events']))
        self.assertEqual([event['kind'] for event in report['events']][-2:], ['close', 'close'])
        return report

    def test_normal_nonempty_binary_bytes_and_completion_before_mode_sync(self):
        self._complete(b'actual\x00atomic\xffbytes\n', mode='0644')

    def test_positive_short_writes_finish_all_bytes_before_activation(self):
        report = self._complete(bytes(range(256)) * 4, fault='short')
        writes = [event for event in report['events'] if event['kind'] == 'write']
        self.assertGreater(len(writes), 1)
        self.assertTrue(any(0 < event['returned'] < event['offered'] for event in writes))
        self.assertTrue(all(0 < event['returned'] <= event['offered'] for event in writes))

    def test_empty_regular_source_still_sets_mode_syncs_and_closes(self):
        report = self._complete(b'')
        self.assertFalse(any(event['kind'] == 'write' for event in report['events']))

    def test_exact_existing_source_byte_bound_remains_accepted(self):
        self._complete(b'x' * MAX_BYTES, mode='0644')

    def test_over_source_byte_bound_retains_original_refusal(self):
        result, report = self._run(b'x' * (MAX_BYTES + 1))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report['failure'], {'type':'RuntimeError',
            'message':'atomic install source is unsafe or oversized'})
        self.assertFalse(any(event['kind'] in ('write', 'fchmod', 'fsync') for event in report['events']))
        self.assertEqual(report['stage_mode'], 0o600)

    def test_zero_write_refuses_before_activation_and_closes(self):
        report = self._refused(b'zero-progress-source', 'zero', 'short atomic install write')
        self.assertEqual(report['stage_bytes'], 0)

    def test_error_after_positive_partial_write_propagates_and_closes(self):
        report = self._refused(b'partial-then-error', 'error', 'injected atomic write failure')
        self.assertGreater(report['stage_bytes'], 0)
        self.assertLess(report['stage_bytes'], len(b'partial-then-error'))

    def test_impossible_overcount_refuses_before_activation_and_closes(self):
        report = self._refused(b'impossible-count', 'overcount', 'short atomic install write')
        self.assertEqual(report['stage_bytes'], 0)


    def _fd_run(self, fault):
        payload, retained_stage = b'fd-lifetime-original-payload', b'untouched-private-stage'
        program, program_sha = self._program()
        source, stage, log = (self.root / name for name in ('source', 'stage', 'events.json'))
        source.write_bytes(payload)
        source.chmod(0o640)
        stage.write_bytes(retained_stage)
        stage.chmod(0o600)
        before, stage_before = generation(source), generation(stage)
        try:
            result = subprocess.run([sys.executable, '-I', '-B', '-W', 'error',
                str(CHILD), str(program), str(source), str(stage), '0755', fault, str(log)],
                capture_output=True, text=True, check=False, timeout=3, cwd=self.root)
        finally:
            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(generation(source), before)
            self.assertEqual(hashlib.sha256(program.read_bytes()).hexdigest(), program_sha)
            self.assertTrue(log.is_file())
            self.assertLessEqual(log.stat().st_size, MAX_BYTES)
            if fault in ('source_open_error', 'stage_open_error'):
                self.assertEqual(stage.read_bytes(), retained_stage)
                self.assertEqual(generation(stage), stage_before)
        self.assertEqual(result.stderr, '')
        self.assertLessEqual(len(result.stdout), MAX_BYTES)
        report = json.loads(result.stdout)
        print(result.stdout, end='')
        self.assertEqual(report['program_sha256'], program_sha)
        self.assertTrue(report['source_preserved'])
        self.assertEqual(report['source_sha256'], hashlib.sha256(payload).hexdigest())
        self.assertEqual(json.loads(log.read_text())['events'], report['events'])
        self.assertTrue(all(report['slots_none_before_exit'].values()))
        self.assertLessEqual(len(report['close_attempts']), 2)
        failed_role = 'stage' if fault == 'stage_close_before' else 'source' if fault == 'source_close_before' else None
        for row in report['close_attempts']:
            self.assertTrue(row['own_slot_none_before_close'])
            self.assertEqual(row['real_close_completed'], row['role'] != failed_role)
            self.assertEqual(row['injected_before_real_close'], row['role'] == failed_role)
        self.assertEqual(result.returncode, 0 if fault == 'fd_zero' else 1)
        return report

    def _fd_case(self, fault, top, expected_attempts):
        report = self._fd_run(fault)
        attempts = report['close_attempts']
        self.assertEqual([row['role'] for row in attempts], expected_attempts)
        self.assertEqual(set(report['acquired']), set(expected_attempts))
        for row in attempts:
            acquired = report['acquired'][row['role']]
            self.assertEqual(row['fd'], acquired['fd'])
            self.assertEqual(row['before_identity'][:2], acquired['identity'][:2])
            self.assertEqual(row['before_identity'][3], acquired['identity'][3])
        graph = report['failure_graph']
        self.assertEqual(graph['top'], top)
        self.assertTrue(all(node['exact_injected_object'] for node in graph['nodes']))
        nodes = {node['label']:node for node in graph['nodes']}
        self.assertEqual(len(nodes), len(graph['nodes']))
        messages = {'source_open':'injected source open failure',
                    'stage_open':'injected stage open failure',
                    'body':'injected body write failure',
                    'body_cause':'original explicit body cause',
                    'stage_close':'injected stage close failure',
                    'source_close':'injected source close failure'}
        for label, node in nodes.items():
            self.assertEqual(node['message'], messages[label])
            self.assertEqual(node['type'], 'ValueError' if label == 'body_cause' else 'OSError')
            if label.endswith('_close') or label.endswith('_open'):
                self.assertIsNone(node['__cause__'])
                self.assertFalse(node['suppress_context'])
        for role, state in report['numeric_fd_state_after_cleanup'].items():
            if role == 'stage' and report['sentinel'] is not None:
                self.assertTrue(state['open'])
                self.assertNotEqual(state['identity'], report['acquired'][role]['identity'])
            else:
                self.assertFalse(state['open'])
                self.assertEqual(state['errno'], errno.EBADF)
        return report, nodes

    def _fd_complete_bytes(self, report):
        payload = b'fd-lifetime-original-payload'
        self.assertEqual(report['stage_hex'], payload.hex())
        self.assertEqual(report['stage_sha256'], hashlib.sha256(payload).hexdigest())
        self.assertEqual(report['stage_mode'], 0o755)
        self.assertEqual([event['kind'] for event in report['events']].count('fchmod'), 1)
        self.assertEqual([event['kind'] for event in report['events']].count('fsync'), 1)
        for event in report['events']:
            if event['kind'] in ('fchmod', 'fsync'):
                self.assertTrue(event['immediately_before']['exact_original_fixture'])

    def _fd_sentinel(self, report):
        self.assertIsNotNone(report['sentinel'])
        for field in ('reuses_released_stage_number', 'open_after_source_cleanup',
                      'dev_null_read_eof', 'different_from_original_stage_identity'):
            self.assertTrue(report['sentinel'][field])
        self.assertTrue(report['fixture_sentinel_closed_after_snapshot'])
        self.assertEqual(report['sentinel']['fd'], report['acquired']['stage']['fd'])
        self.assertEqual([row['role'] for row in report['close_attempts']], ['stage', 'source'])
        self.assertTrue(all(row['real_close_completed'] for row in report['close_attempts']))

    def _fd_body_graph(self, report, nodes):
        body = nodes['body']
        self.assertEqual(body['type'], 'OSError')
        self.assertEqual(body['message'], 'injected body write failure')
        self.assertEqual(body['__cause__'], 'body_cause')
        self.assertIsNone(body['__context__'])
        self.assertTrue(body['suppress_context'])
        self.assertEqual(nodes['body_cause']['type'], 'ValueError')
        self.assertEqual(nodes['body_cause']['message'], 'original explicit body cause')
        self.assertIsNone(nodes['body_cause']['__cause__'])
        self.assertIsNone(nodes['body_cause']['__context__'])
        self.assertFalse(nodes['body_cause']['suppress_context'])
        payload = b'fd-lifetime-original-payload'
        self.assertGreater(report['body_prefix'], 0)
        self.assertLess(report['body_prefix'], len(payload))
        self.assertEqual(report['stage_hex'], payload[:report['body_prefix']].hex())
        self.assertEqual(report['stage_mode'], 0o600)
        self.assertFalse(any(row['kind'] in ('fchmod', 'fsync') for row in report['events']))

    def test_source_open_failure_preserves_fixture_without_close(self):
        report, nodes = self._fd_case('source_open_error', 'source_open', [])
        self.assertEqual(set(nodes), {'source_open'})
        self.assertEqual(nodes['source_open']['message'], 'injected source open failure')
        self.assertIsNone(nodes['source_open']['__context__'])
        self.assertFalse(any(row['kind'] in ('write', 'fchmod', 'fsync') for row in report['events']))
        self.assertEqual(report['stage_hex'], b'untouched-private-stage'.hex())

    def test_stage_open_failure_closes_only_acquired_source(self):
        report, nodes = self._fd_case('stage_open_error', 'stage_open', ['source'])
        self.assertEqual(set(nodes), {'stage_open'})
        self.assertEqual(nodes['stage_open']['message'], 'injected stage open failure')
        self.assertIsNone(nodes['stage_open']['__context__'])
        self.assertFalse(any(row['kind'] in ('write', 'fchmod', 'fsync') for row in report['events']))
        self.assertEqual(report['stage_hex'], b'untouched-private-stage'.hex())

    def test_stage_close_failure_keeps_reused_number_open_while_source_closes(self):
        report, nodes = self._fd_case('stage_close_error_reuse', 'stage_close', ['stage', 'source'])
        self._fd_complete_bytes(report)
        self._fd_sentinel(report)
        self.assertEqual(set(nodes), {'stage_close'})
        self.assertIsNone(nodes['stage_close']['__context__'])
        self.assertFalse(nodes['stage_close']['suppress_context'])

    def test_source_close_failure_keeps_native_refusal(self):
        report, nodes = self._fd_case('source_close_error', 'source_close', ['stage', 'source'])
        self._fd_complete_bytes(report)
        self.assertIsNone(report['sentinel'])
        self.assertEqual(set(nodes), {'source_close'})
        self.assertIsNone(nodes['source_close']['__context__'])

    def test_both_close_failures_preserve_both_actual_error_objects(self):
        report, nodes = self._fd_case('both_close_error', 'source_close', ['stage', 'source'])
        self._fd_complete_bytes(report)
        self._fd_sentinel(report)
        self.assertEqual(set(nodes), {'source_close', 'stage_close'})
        self.assertEqual(nodes['source_close']['__context__'], 'stage_close')
        self.assertIsNone(nodes['stage_close']['__context__'])
        self.assertTrue(all(not node['suppress_context'] for node in nodes.values()))

    def test_body_error_and_both_close_failures_preserve_explicit_cause(self):
        report, nodes = self._fd_case('body_both_close_error', 'source_close', ['stage', 'source'])
        self._fd_sentinel(report)
        self._fd_body_graph(report, nodes)
        self.assertEqual(set(nodes), {'source_close', 'stage_close', 'body', 'body_cause'})
        self.assertEqual(nodes['source_close']['__context__'], 'stage_close')
        self.assertEqual(nodes['stage_close']['__context__'], 'body')
        self.assertIsNone(nodes['source_close']['__cause__'])
        self.assertIsNone(nodes['stage_close']['__cause__'])
        self.assertFalse(nodes['source_close']['suppress_context'])
        self.assertFalse(nodes['stage_close']['suppress_context'])

    def test_body_error_with_successful_cleanup_retains_original_exception(self):
        report, nodes = self._fd_case('body_error_cleanup_ok', 'body', ['stage', 'source'])
        self.assertIsNone(report['sentinel'])
        self.assertEqual(set(nodes), {'body', 'body_cause'})
        self._fd_body_graph(report, nodes)

    def test_source_descriptor_zero_is_owned_and_closed(self):
        report, nodes = self._fd_case('fd_zero', None, ['stage', 'source'])
        self._fd_complete_bytes(report)
        self.assertEqual(nodes, {})
        self.assertEqual(report['acquired']['source']['fd'], 0)
        self.assertFalse(report['numeric_fd_state_after_cleanup']['source']['open'])
        self.assertTrue(report['source_zero_EBADF_after_report_reads'])


    def _fd_before_case(self, failed_role):
        report = self._fd_run(failed_role + '_close_before')
        self._fd_complete_bytes(report)
        self.assertIsNone(report['sentinel'])
        self.assertEqual(set(report['acquired']), {'stage', 'source'})
        attempts = report['close_attempts']
        self.assertEqual([row['role'] for row in attempts], ['stage', 'source'])
        self.assertEqual([row['role'] for row in attempts if not row['real_close_completed']], [failed_role])
        self.assertEqual(report['held_originals'], {failed_role:report['acquired'][failed_role]['fd']})
        self.assertEqual(report['held_originals_open_after_report_reads'], {failed_role:True})
        self.assertEqual(report['fixture_held_original_closed_after_snapshot'], {failed_role:True})
        for row in attempts:
            acquired = report['acquired'][row['role']]
            self.assertEqual(row['fd'], acquired['fd'])
            self.assertEqual(row['before_identity'][:2], acquired['identity'][:2])
            self.assertEqual(row['before_identity'][3], acquired['identity'][3])
            state = report['numeric_fd_state_after_cleanup'][row['role']]
            self.assertEqual(state['open'], row['role'] == failed_role)
            if row['role'] == failed_role:
                self.assertEqual(state['identity'], row['before_identity'])
            else:
                self.assertEqual(state['errno'], errno.EBADF)
        graph = report['failure_graph']
        self.assertEqual(graph['top'], failed_role + '_close')
        self.assertEqual(len(graph['nodes']), 1)
        node = graph['nodes'][0]
        self.assertEqual(node['label'], failed_role + '_close')
        self.assertTrue(node['exact_injected_object'])
        self.assertEqual(node['type'], 'OSError')
        self.assertEqual(node['message'], 'injected ' + failed_role + ' close failure')
        self.assertIsNone(node['__context__'])
        self.assertIsNone(node['__cause__'])
        self.assertFalse(node['suppress_context'])

    def test_before_stage_close_failure_retains_ambiguous_original_and_cleans_source(self):
        self._fd_before_case('stage')

    def test_before_source_close_failure_retains_ambiguous_original_and_cleans_stage(self):
        self._fd_before_case('source')


if __name__ == '__main__':
    unittest.main()
