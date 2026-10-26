"""Real-file admission controls; writer-through-CAS and races remain separate."""
from pathlib import Path
import errno
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
CHILD = REPO / 'tests/fixtures/atomic-stage-admission-v1/child.py'
MAX_BYTES = 1_048_576
PAYLOAD = b'admitted-source\x00\xff\n'
STAGE_BYTES = b'preserve-prepopulated-stage\n'
SOURCE_UNSAFE = 'atomic install source is unsafe or oversized'
STAGE_UNSAFE = 'atomic install stage is unsafe or aliases source'


def observe(path):
    value = path.lstat()
    identity = [value.st_dev, value.st_ino, value.st_mode, value.st_uid,
                value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns]
    data = None
    if stat.S_ISREG(value.st_mode):
        with path.open('rb') as stream:
            data = stream.read(MAX_BYTES + 2)
        if len(data) > MAX_BYTES + 1:
            raise ValueError('admission fixture byte cap')
    return {'identity': identity,
            'sha256': None if data is None else hashlib.sha256(data).hexdigest(),
            'small_hex': data.hex() if data is not None and len(data) <= 64 else None}, data


class AtomicStageAdmission(unittest.TestCase):
    def setUp(self):
        fixture = tempfile.TemporaryDirectory(prefix='sia-atomic-admission-')
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name)
        (self.root / 'home').mkdir(mode=0o700)
        (self.root / 'tmp').mkdir(mode=0o700)
        self.paths = {'source': self.root / 'source', 'stage': self.root / 'stage'}
        self.stage_peer = None

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

    def _regular(self, role, data, mode):
        path = self.paths[role]
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
        os.close(descriptor)
        path.write_bytes(data)
        path.chmod(mode)

    def _fixture(self, kind):
        if kind in ('source_symlink', 'stage_symlink'):
            self._symlink_fixture(kind)
            return
        source_fifo = kind in ('source_fifo', 'source_fifo_peer')
        stage_fifo = kind in ('stage_fifo', 'stage_fifo_peer')
        if source_fifo:
            os.mkfifo(self.paths['source'], 0o600)
        else:
            payload = b'x' * (MAX_BYTES + 1) if kind == 'oversized' else PAYLOAD
            self._regular('source', payload, 0o640)
        if kind == 'same_path':
            self.paths['stage'] = self.paths['source']
        elif kind == 'hardlink_alias':
            os.link(self.paths['source'], self.paths['stage'])
        elif stage_fifo:
            os.mkfifo(self.paths['stage'], 0o600)
        else:
            self._regular('stage', STAGE_BYTES, 0o600)
        if kind == 'hardlinked_stage':
            self.paths['related'] = self.root / 'related'
            os.link(self.paths['stage'], self.paths['related'])
        if kind == 'hardlinked_source':
            self.paths['related'] = self.root / 'related'
            os.link(self.paths['source'], self.paths['related'])
        if kind == 'source_fifo_peer':
            self._peer('source', os.O_RDWR)
        if kind == 'stage_fifo_peer':
            self.stage_peer = self._peer('stage', os.O_RDONLY)

    def _symlink_fixture(self, kind):
        self.paths['related'] = self.root / 'related'
        self._regular('related', PAYLOAD if kind == 'source_symlink' else STAGE_BYTES, 0o600)
        if kind == 'source_symlink':
            self.paths['source'].symlink_to(self.paths['related'])
            self._regular('stage', STAGE_BYTES, 0o600)
        else:
            self._regular('source', PAYLOAD, 0o640)
            self.paths['stage'].symlink_to(self.paths['related'])

    def _peer(self, role, access):
        descriptor = os.open(self.paths[role], access | os.O_NONBLOCK | os.O_CLOEXEC)
        self.addCleanup(os.close, descriptor)
        held, current = os.fstat(descriptor), self.paths[role].lstat()
        self.assertTrue(stat.S_ISFIFO(held.st_mode))
        self.assertEqual((held.st_dev, held.st_ino), (current.st_dev, current.st_ino))
        return descriptor

    def _after(self, before, preserve, program, program_sha, log, timed_out):
        after = {role: observe(path) for role, path in self.paths.items()}
        peer_data = None
        if self.stage_peer is not None:
            try:
                peer_data = os.read(self.stage_peer, MAX_BYTES + 1)
            except BlockingIOError as error:
                peer_data = {'errno': error.errno}
        self.assertTrue(log.is_file())
        self.assertLessEqual(log.stat().st_size, MAX_BYTES)
        events = json.loads(log.read_text())['events']
        print(json.dumps({'fixture_before': {k: v[0] for k, v in before.items()},
                          'fixture_after': {k: v[0] for k, v in after.items()},
                          'retained_events': events, 'child_timeout': timed_out,
                          'stage_peer_hex': peer_data.hex() if isinstance(peer_data, bytes) else peer_data},
                         sort_keys=True))
        self.assertEqual(hashlib.sha256(program.read_bytes()).hexdigest(), program_sha)
        for role in preserve:
            self.assertEqual(after[role][0], before[role][0], role + ' metadata changed')
            self.assertEqual(after[role][1], before[role][1], role + ' actual bytes changed')
        return peer_data

    def _run(self, kind, preserve=('source', 'stage'), fault='normal'):
        self._fixture(kind)
        program, program_sha = self._program()
        before = {role: observe(path) for role, path in self.paths.items()}
        log, timed_out = self.root / 'events.json', False
        result, timeout_output = None, (b'', b'')
        command = [sys.executable, '-I', '-B', '-W', 'error', str(CHILD), str(program),
                   str(self.paths['source']), str(self.paths['stage']), '0755', fault, str(log)]
        environment = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
                       'HOME': str(self.root / 'home'), 'TMPDIR': str(self.root / 'tmp')}
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                    check=False, timeout=3, cwd=self.root, env=environment)
        except subprocess.TimeoutExpired as error:
            timed_out = True
            timeout_output = (error.stdout or b'', error.stderr or b'')
            raise
        finally:
            stdout, stderr = timeout_output if result is None else (result.stdout, result.stderr)
            print(json.dumps({'child_command': command, 'child_timeout_seconds': 3,
                              'child_exit': None if result is None else result.returncode,
                              'child_stdout_hex': stdout.hex(), 'child_stderr_hex': stderr.hex()},
                             sort_keys=True))
            peer_data = self._after(before, preserve, program, program_sha, log, timed_out)
        self.assertEqual(result.stderr, b'')
        self.assertLessEqual(len(result.stdout), MAX_BYTES)
        report = json.loads(result.stdout)
        self.assertEqual(report['program_sha256'], program_sha)
        self.assertEqual(json.loads(log.read_text())['events'], report['events'])
        return result, report, before, peer_data

    def _closed(self, report, roles=('source', 'stage')):
        self.assertEqual(set(report['acquired']), set(roles))
        self.assertEqual(report['closed_before_child_exit'], {role: True for role in roles})
        self.assertEqual(report['slots_none_before_exit'], {'source_fd': True, 'temporary_fd': True})
        self.assertEqual(report['close_attempts'], list(reversed(roles)))
        attempts = [row for row in report['events'] if row['kind'] == 'close']
        self.assertEqual(len(attempts), len(roles))
        for row in attempts:
            self.assertTrue(row['own_slot_none_before_close'])
            self.assertTrue(row['real_close_completed'])
            self.assertEqual(row['fd'], report['acquired'][row['role']]['fd'])
            self.assertEqual(row['identity'][:2], report['acquired'][row['role']]['identity'][:2])

    def _refused(self, kind, message, preserve=('source', 'stage')):
        result, report, before, peer_data = self._run(kind, preserve)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report['failure']['type'], 'RuntimeError')
        self.assertEqual(report['failure']['message'], message)
        self.assertIsNone(report['failure']['errno'])
        self.assertFalse(report['failure']['exact_injected_truncate_object'])
        self.assertTrue(report['failure']['context_none'])
        self.assertTrue(report['failure']['cause_none'])
        self.assertFalse(report['failure']['suppress_context'])
        self._closed(report)
        forbidden = ('ftruncate_attempt', 'write', 'fchmod', 'fsync')
        self.assertFalse(any(row['kind'] in forbidden for row in report['events']))
        return report, before, peer_data

    def test_source_fifo_without_peer_refuses_without_stage_mutation(self):
        report, before, _ = self._refused('source_fifo', SOURCE_UNSAFE)
        self.assertTrue(stat.S_ISFIFO(before['source'][0]['identity'][2]))
        opens = [row for row in report['events'] if row['kind'] == 'open_attempt']
        self.assertTrue(opens[0]['flags'] & os.O_NONBLOCK)

    def test_source_fifo_with_peer_refuses_without_stage_mutation(self):
        report, before, _ = self._refused('source_fifo_peer', SOURCE_UNSAFE)
        self.assertTrue(stat.S_ISFIFO(before['source'][0]['identity'][2]))
        self.assertEqual(set(report['acquired']), {'source', 'stage'})

    def test_stage_fifo_without_peer_refuses_without_source_mutation(self):
        result, report, before, _ = self._run('stage_fifo')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report['failure']['type'], 'OSError')
        self.assertEqual(report['failure']['errno'], errno.ENXIO)
        self.assertTrue(stat.S_ISFIFO(before['stage'][0]['identity'][2]))
        self._closed(report, ('source',))
        self.assertFalse(any(row['kind'] in ('ftruncate_attempt', 'write', 'fchmod', 'fsync')
                             for row in report['events']))

    def test_stage_fifo_with_reader_refuses_without_fifo_write_or_mode_change(self):
        report, before, peer_data = self._refused('stage_fifo_peer', STAGE_UNSAFE)
        self.assertTrue(stat.S_ISFIFO(before['stage'][0]['identity'][2]))
        self.assertEqual(peer_data, b'')
        self.assertEqual(set(report['acquired']), {'source', 'stage'})

    def test_same_path_refuses_without_destroying_source(self):
        report, before, _ = self._refused('same_path', STAGE_UNSAFE)
        self.assertEqual(before['source'], before['stage'])
        self.assertNotEqual(report['acquired']['source']['fd'], report['acquired']['stage']['fd'])
        self.assertEqual(report['acquired']['source']['identity'][:2],
                         report['acquired']['stage']['identity'][:2])

    def test_hardlink_alias_refuses_without_destroying_source(self):
        report, before, _ = self._refused('hardlink_alias', STAGE_UNSAFE)
        self.assertNotEqual(str(self.paths['source']), str(self.paths['stage']))
        self.assertEqual(before['source'], before['stage'])
        self.assertEqual(before['stage'][0]['identity'][4], 2)
        self.assertEqual(report['acquired']['source']['identity'][:2],
                         report['acquired']['stage']['identity'][:2])

    def test_unrelated_hardlinked_stage_preserves_both_names(self):
        _, before, _ = self._refused('hardlinked_stage', STAGE_UNSAFE,
                                     ('source', 'stage', 'related'))
        self.assertNotEqual(before['source'][0]['identity'][:2], before['stage'][0]['identity'][:2])
        self.assertEqual(before['stage'], before['related'])
        self.assertEqual(before['stage'][0]['identity'][4], 2)

    def test_oversized_source_preserves_prepopulated_stage(self):
        _, before, _ = self._refused('oversized', SOURCE_UNSAFE)
        self.assertEqual(before['source'][0]['identity'][5], MAX_BYTES + 1)
        self.assertEqual(before['stage'][1], STAGE_BYTES)

    def _successful_truncate(self, report, before):
        events = report['events']
        names = [row['kind'] for row in events]
        self.assertEqual(names.count('ftruncate_attempt'), 1)
        self.assertEqual(names.count('ftruncate_completed'), 1)
        at = names.index('ftruncate_attempt')
        self.assertEqual([row['role'] for row in events[:at] if row['kind'] == 'fstat'],
                         ['source', 'stage'])
        attempt, completed = events[at], events[names.index('ftruncate_completed')]
        self.assertEqual(attempt['length'], 0)
        self.assertEqual(attempt['stage']['small_hex'], STAGE_BYTES.hex())
        self.assertEqual(attempt['stage']['identity'], before['stage'][0]['identity'])
        self.assertEqual(attempt['source']['small_hex'], PAYLOAD.hex())
        self.assertEqual(attempt['source']['identity'], before['source'][0]['identity'])
        self.assertEqual(completed['stage']['small_hex'], '')
        self.assertEqual(completed['stage']['bytes'], 0)
        self.assertEqual(completed['stage']['identity'][:5], before['stage'][0]['identity'][:5])
        self.assertLess(names.index('ftruncate_completed'), names.index('write'))
        for kind in ('fchmod', 'fsync'):
            self.assertEqual(names.count(kind), 1)
            self.assertLess(names.index('write'), names.index(kind))
            row = events[names.index(kind)]
            self.assertEqual(row['stage']['small_hex'], PAYLOAD.hex())
            self.assertEqual(row['stage']['bytes'], len(PAYLOAD))
        self.assertLess(names.index('fchmod'), names.index('fsync'))

    def test_prepopulated_regular_stage_truncates_only_after_admission(self):
        result, report, before, _ = self._run('normal', ('source',))
        self.assertEqual(result.returncode, 0)
        self.assertIsNone(report['failure'])
        self._closed(report)
        opens = [row for row in report['events'] if row['kind'] == 'open_attempt']
        self.assertEqual([row['role'] for row in opens], ['source', 'stage'])
        self.assertTrue(all(row['flags'] & os.O_NONBLOCK for row in opens))
        self.assertTrue(all(not row['flags'] & os.O_TRUNC for row in opens))
        for role in ('source', 'stage'):
            value = report['acquired'][role]['identity']
            self.assertTrue(stat.S_ISREG(value[2]))
            self.assertEqual(value[3], os.geteuid())
        self.assertEqual(report['acquired']['stage']['identity'][4], 1)
        self.assertNotEqual(report['acquired']['stage']['identity'][:2],
                            report['acquired']['source']['identity'][:2])
        self._successful_truncate(report, before)
        self.assertEqual(self.paths['stage'].read_bytes(), PAYLOAD)
        self.assertEqual(stat.S_IMODE(self.paths['stage'].stat().st_mode), 0o755)

    def test_truncate_error_preserves_stage_and_closes_both(self):
        result, report, before, _ = self._run('normal', fault='truncate_error')
        self.assertEqual(result.returncode, 1)
        error = report['failure']
        self.assertEqual(error['type'], 'OSError')
        self.assertEqual(error['message'], '[Errno 5] injected atomic truncate failure')
        self.assertEqual(error['errno'], errno.EIO)
        self.assertTrue(error['exact_injected_truncate_object'])
        self.assertTrue(error['context_none'])
        self.assertTrue(error['cause_none'])
        self.assertFalse(error['suppress_context'])
        self._closed(report)
        names = [row['kind'] for row in report['events']]
        self.assertEqual(names.count('ftruncate_attempt'), 1)
        self.assertFalse(any(name in ('ftruncate_completed', 'write', 'fchmod', 'fsync') for name in names))
        self.assertEqual(before['stage'][1], STAGE_BYTES)


    def _symlink_refused(self, kind, roles):
        result, report, before, _ = self._run(kind, ('source', 'stage', 'related'))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report['failure']['type'], 'OSError')
        self.assertEqual(report['failure']['errno'], errno.ELOOP)
        self.assertTrue(report['failure']['context_none'])
        self.assertTrue(report['failure']['cause_none'])
        self.assertFalse(report['failure']['suppress_context'])
        self._closed(report, roles)
        role = 'source' if kind == 'source_symlink' else 'stage'
        self.assertTrue(stat.S_ISLNK(before[role][0]['identity'][2]))
        self.assertEqual(os.readlink(self.paths[role]), str(self.paths['related']))
        forbidden = ('ftruncate_attempt', 'write', 'fchmod', 'fsync')
        self.assertFalse(any(row['kind'] in forbidden for row in report['events']))

    def test_source_final_symlink_refuses_without_touching_stage_or_target(self):
        self._symlink_refused('source_symlink', ())

    def test_stage_final_symlink_refuses_without_touching_source_or_target(self):
        self._symlink_refused('stage_symlink', ('source',))

    def test_hardlinked_source_remains_accepted_with_distinct_singlelink_stage(self):
        result, report, before, _ = self._run('hardlinked_source', ('source', 'related'))
        self.assertEqual(result.returncode, 0)
        self.assertIsNone(report['failure'])
        self._closed(report)
        self.assertEqual(before['source'], before['related'])
        self.assertEqual(before['source'][0]['identity'][4], 2)
        self.assertEqual(before['stage'][0]['identity'][4], 1)
        self.assertNotEqual(before['source'][0]['identity'][:2], before['stage'][0]['identity'][:2])
        self.assertEqual(self.paths['stage'].read_bytes(), PAYLOAD)
        self.assertEqual(stat.S_IMODE(self.paths['stage'].stat().st_mode), 0o755)
        activations = [row for row in report['events'] if row['kind'] in ('fchmod', 'fsync')]
        self.assertEqual([row['kind'] for row in activations], ['fchmod', 'fsync'])
        self.assertTrue(all(row['stage']['small_hex'] == PAYLOAD.hex() for row in activations))

    def test_readonly_acquisition_seam_executes_native_ftruncate_refusal_and_cleanup(self):
        result, report, _, _ = self._run('normal', fault='readonly_stage')
        self.assertEqual(result.returncode, 1)
        error = report['failure']
        self.assertEqual(error['type'], 'OSError')
        self.assertIn(error['errno'], (errno.EBADF, errno.EINVAL))
        self.assertTrue(error['exact_native_truncate_object'])
        self.assertFalse(error['exact_injected_truncate_object'])
        self.assertTrue(error['context_none'])
        self.assertTrue(error['cause_none'])
        self.assertFalse(error['suppress_context'])
        self._closed(report)
        events = report['events']
        opens = [row for row in events if row['kind'] == 'open_attempt' and row['role'] == 'stage']
        self.assertEqual(len(opens), 1)
        self.assertEqual(opens[0]['flags'] & os.O_ACCMODE, os.O_WRONLY)
        self.assertEqual(opens[0]['actual_flags'] & os.O_ACCMODE, os.O_RDONLY)
        at = next(i for i, row in enumerate(events) if row['kind'] == 'ftruncate_attempt')
        self.assertEqual([row['role'] for row in events[:at] if row['kind'] == 'fstat'],
                         ['source', 'stage'])
        errors = [row for row in events if row['kind'] == 'ftruncate_native_error']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['fd'], report['acquired']['stage']['fd'])
        self.assertEqual(errors[0]['identity'], report['acquired']['stage']['identity'])
        self.assertEqual(errors[0]['errno'], error['errno'])
        self.assertEqual(errors[0]['access_flags'] & os.O_ACCMODE, os.O_RDONLY)
        self.assertEqual(errors[0]['length'], 0)
        forbidden = ('ftruncate_completed', 'write', 'fchmod', 'fsync')
        self.assertFalse(any(row['kind'] in forbidden for row in events))


if __name__ == '__main__':
    unittest.main()
