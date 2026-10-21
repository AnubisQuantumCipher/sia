"""Actual atomic_install_file heredoc controls; separate from CAS/open/race acceptance."""
from pathlib import Path
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


if __name__ == '__main__':
    unittest.main()
