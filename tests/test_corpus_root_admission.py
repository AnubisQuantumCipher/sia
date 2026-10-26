"""Exercise the complete extracted corpus-root receipt helper.

The helper's actual Python heredoc runs with private /dev/shm inputs.  This
tests the extracted helper, not installed qualification or the full installer.
The intended repository filename is tests/test_corpus_root_admission.py.
"""

from pathlib import Path
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

from tests.test_release_metadata_admission import (
    CHILD_SECONDS, MAX_OUTPUT_BYTES, REAP_SECONDS, REPO,
    close_pipes, collect, identity, reap,
)


INSTALLER = REPO / 'install.sh'
HARNESS = REPO / 'tests/test_release_metadata_admission.py'
MAX_SOURCE_BYTES = 1_048_576
MAX_FIXTURE_BYTES = 4_096
MAX_PROGRAM_BYTES = 4_096
MAX_REPORT_BYTES = 32_768
MAX_PATHS = 9
MAX_DIRECTORY_ENTRIES = 5
CASES = ('regular', 'fifo', 'wrong_corpus', 'absent', 'invalid_utf8')
SOURCE_ROLES = ('installer', 'harness', 'test_source')


class CorpusRootAdmission(unittest.TestCase):
    def setUp(self):
        self.assertEqual((CHILD_SECONDS, MAX_OUTPUT_BYTES, REAP_SECONDS), (3, 4096, 5))
        self.assertTrue(stat.S_ISDIR(Path('/dev/shm').lstat().st_mode))
        fixture = tempfile.TemporaryDirectory(prefix='sia-corpus-root-', dir='/dev/shm')
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name)
        self.assertLessEqual(len(os.fsencode(self.root)), 128)
        self.assertEqual(stat.S_IMODE(self.root.lstat().st_mode), 0o700)
        self.paths = {'root': self.root, 'installer': INSTALLER,
                      'harness': HARNESS, 'test_source': Path(__file__).resolve()}
        for role in ('home', 'tmp', 'corpus'):
            self.paths[role] = self.root / role
            self.paths[role].mkdir(mode=0o700)
        self.paths['receipt'] = self.root / 'receipt'
        self.paths['program'] = self.root / 'actual-helper.py'
        _metadata, self.installer_source = self._observe('installer', INSTALLER)
        self.assertIsInstance(self.installer_source, bytes)
        self._extract_program()

    def _write(self, role, data):
        self.assertLessEqual(len(data), MAX_FIXTURE_BYTES)
        with self.paths[role].open('xb') as stream:
            self.assertEqual(stream.write(data), len(data))
        self.paths[role].chmod(0o600)

    def _extract_program(self):
        source = self.installer_source
        start = b'corpus_receipt_recorded_root() {\n'
        following = b'corpus_prior_receipt_recognized() {\n'
        invocation = b'  python3 - "${1:-$CORPUS_RECEIPT}" "$SHARE/corpus" '
        opening = b"<<'PY'\n"
        closing = b'\nPY\n'
        self.assertEqual(source.count(start), 1)
        self.assertEqual(source.count(following), 1)
        function, separator, _tail = source.partition(start)[2].partition(following)
        self.assertTrue(separator)
        self.assertEqual(function.count(opening), 1)
        self.assertEqual(function.count(closing), 1)
        prefix, separator, body = function.partition(opening)
        self.assertTrue(separator)
        self.assertEqual(prefix, invocation)
        program, separator, suffix = body.partition(closing)
        self.assertTrue(separator)
        self.assertEqual(suffix.partition(b'\n\n')[0], b'}')
        self.assertTrue(program)
        program += b'\n'
        self.assertLessEqual(len(program), MAX_PROGRAM_BYTES)
        self._write('program', program)

    def _fixture(self, case):
        self.assertIn(case, CASES)
        self.case = case
        corpus = self.paths['corpus']
        info = corpus.lstat()
        token = f'{info.st_dev}:{info.st_ino}:{info.st_mode}:{info.st_uid}'
        if case == 'fifo':
            # No peer descriptor is opened: the FIFO has no writer.
            os.mkfifo(self.paths['receipt'], 0o600)
            receipt_info = self.paths['receipt'].lstat()
            self.assertTrue(stat.S_ISFIFO(receipt_info.st_mode))
            self.assertEqual(stat.S_IMODE(receipt_info.st_mode), 0o600)
        elif case == 'absent':
            self.assertFalse(os.path.lexists(self.paths['receipt']))
        elif case == 'invalid_utf8':
            self._write('receipt', b'\xff')
        else:
            recorded_path = str(corpus) + '-wrong' if case == 'wrong_corpus' else str(corpus)
            data = ('managed-by=khephri.sia\nkind=corpus-v2\n'
                    f'path={recorded_path}\nroot={token}\n').encode('ascii')
            self._write('receipt', data)
        return (token + '\n').encode('ascii') if case == 'regular' else b''

    def _observe(self, role, path):
        try:
            info = path.lstat()
        except FileNotFoundError:
            self.assertEqual(role, 'receipt')
            self.assertEqual(self.case, 'absent')
            return {'state': 'absent'}, None
        self.assertEqual(info.st_uid, os.geteuid())
        data, children = None, None
        if stat.S_ISREG(info.st_mode):
            limit = MAX_SOURCE_BYTES if role in SOURCE_ROLES else MAX_FIXTURE_BYTES
            with path.open('rb') as stream:
                data = stream.read(limit + 1)
            self.assertLessEqual(len(data), limit)
            self.assertEqual(len(data), info.st_size)
        elif stat.S_ISDIR(info.st_mode):
            children = []
            with os.scandir(path) as iterator:
                for entry in iterator:
                    children.append(entry.name)
                    self.assertLessEqual(len(children), MAX_DIRECTORY_ENTRIES)
            children.sort()
        else:
            self.assertEqual(role, 'receipt')
            self.assertTrue(stat.S_ISFIFO(info.st_mode))
            self.assertEqual(info.st_nlink, 1)
        self.assertEqual(identity(path.lstat()), identity(info))
        return {'state': 'present', 'identity': identity(info), 'children': children,
                'sha256': None if data is None else hashlib.sha256(data).hexdigest()}, data

    def _snapshot(self):
        self.assertEqual(len(self.paths), MAX_PATHS)
        return {role: self._observe(role, path) for role, path in self.paths.items()}

    def _preserved(self, before, case, command, output, child, timed_out):
        after = self._snapshot()
        report = {'case': case, 'child_command': command,
                  'child_deadline_seconds': CHILD_SECONDS, 'child_timeout': timed_out,
                  'child_pid': None if child is None else child.pid,
                  'child_exit': None if child is None else child.returncode,
                  'child_reap_state': 'NOT_STARTED' if child is None else
                      'UNKNOWN' if child.returncode is None else 'REAPED',
                  'installer_sha256': before['installer'][0]['sha256'],
                  'helper_sha256': before['program'][0]['sha256'],
                  'harness_sha256': before['harness'][0]['sha256'],
                  'test_source_sha256': before['test_source'][0]['sha256'],
                  'stdout_hex': bytes(output['stdout']).hex(),
                  'stderr_hex': bytes(output['stderr']).hex(),
                  'fixture_before': {role: value[0] for role, value in before.items()},
                  'fixture_after': {role: value[0] for role, value in after.items()}}
        encoded = json.dumps(report, sort_keys=True)
        self.assertLessEqual(len(encoded.encode('utf-8')), MAX_REPORT_BYTES)
        print(encoded)
        self.assertEqual(after.keys(), before.keys())
        for role in before:
            self.assertEqual(after[role][0], before[role][0], role + ' metadata changed')
            self.assertEqual(after[role][1], before[role][1], role + ' actual bytes changed')

    def _case(self, case):
        expected_stdout = self._fixture(case)
        command = [sys.executable, '-I', '-S', '-B', '-W', 'error',
                   str(self.paths['program']), str(self.paths['receipt']),
                   str(self.paths['corpus'])]
        environment = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
                       'HOME': str(self.paths['home']), 'TMPDIR': str(self.paths['tmp'])}
        before, output = self._snapshot(), {'stdout': bytearray(), 'stderr': bytearray()}
        self.assertEqual(before['installer'][1], self.installer_source)
        child, timed_out = None, False
        try:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, close_fds=True, cwd=self.root,
                                     env=environment)
            try:
                status = collect(child, command, output)
            except subprocess.TimeoutExpired:
                timed_out = True
                raise
            finally:
                try:
                    reap(child)
                finally:
                    close_pipes(child)
        finally:
            self._preserved(before, case, command, output, child, timed_out)
        self.assertIsNotNone(child)
        self.assertIsNotNone(child.returncode, 'child termination was not observed')
        self.assertEqual(status, 0 if case == 'regular' else 1)
        self.assertEqual(child.returncode, status)
        self.assertEqual(bytes(output['stdout']), expected_stdout)
        self.assertEqual(bytes(output['stderr']), b'')

    def test_regular_receipt_returns_recorded_root(self):
        self._case('regular')

    def test_no_writer_fifo_refuses(self):
        self._case('fifo')

    def test_wrong_corpus_path_refuses(self):
        self._case('wrong_corpus')

    def test_absent_receipt_refuses(self):
        self._case('absent')

    def test_invalid_utf8_receipt_refuses(self):
        self._case('invalid_utf8')


if __name__ == '__main__':
    unittest.main()
