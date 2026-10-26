"""Real lstat/open substitutions against the complete installer CAS program."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import unittest

from tests import sia_test_home
from tests.test_release_metadata_admission import (
    CHILD_SECONDS, MAX_OUTPUT_BYTES, REAP_SECONDS, REPO,
    close_pipes, collect, reap,
)

OLD = b'operator original bytes\n'
NEW = b'installer desired bytes\n'
CHILD = REPO / 'tests/tree_sync_child.py'
TOKEN = re.compile(rb'tree:(?:[0-9]+:){8}[0-9a-f]{64}')


class TreeSyncAdmission(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.path.expanduser('~'), sia_test_home.ISOLATED_HOME)
        self.assertNotEqual(os.geteuid(), 0)
        self.assertEqual((CHILD_SECONDS, MAX_OUTPUT_BYTES, REAP_SECONDS), (3, 4096, 5))
        fixture = tempfile.TemporaryDirectory(prefix='sia-tree-sync-', dir='/dev/shm')
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name)
        self.assertEqual(stat.S_IMODE(self.root.lstat().st_mode), 0o700)
        for name in ('target', 'stage', 'home', 'tmp'):
            (self.root / name).mkdir(mode=0o700)
        self._write(self.root / 'target/value', OLD)
        self._write(self.root / 'stage/value', NEW)
        self.install = self._bounded(REPO / 'install.sh', 1048576)
        self.child_source = self._bounded(CHILD, 16384)
        opening = b'owned_tree_cas() {\n  python3 - "$@" <<\'PY\'\n'
        closing = b'\nPY\n}\n\nowned_tree_generation() {\n'
        self.assertEqual(self.install.count(opening), 1)
        body, separator, _tail = self.install.split(opening, 1)[1].partition(closing)
        self.assertTrue(separator)
        self.assertTrue(body)
        self.assertLessEqual(len(body), 32767)
        window = b'            elif stat.S_ISREG(observed.st_mode):\n'
        self.assertEqual(body.count(window), 1)
        hook = b'                _admission_hook(descriptor, child, observed, synchronize)\n'
        self.program = body.replace(window, window + hook) + b'\n'
        self.assertLessEqual(len(self.program), 32768)
        self._write(self.root / 'program.py', self.program)
        self.records = []

    def _bounded(self, path, limit):
        with path.open('rb') as source:
            raw = source.read(limit + 1)
        self.assertLessEqual(len(raw), limit)
        return raw

    def _write(self, path, raw):
        self.assertLessEqual(len(raw), 32768)
        with path.open('xb') as output:
            self.assertEqual(output.write(raw), len(raw))
        path.chmod(0o600)

    def _invoke(self, case, operation):
        argv = [sys.executable, '-I', '-S', '-B', '-W', 'error', str(CHILD),
                str(self.root / 'program.py'), hashlib.sha256(self.program).hexdigest(),
                str(self.root), case, *operation]
        environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
                       'HOME': str(self.root / 'home'), 'TMPDIR': str(self.root / 'tmp')}
        output = {'stdout': bytearray(), 'stderr': bytearray()}
        child, timed_out = None, False
        try:
            child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, env=environment, close_fds=True)
            try:
                status = collect(child, argv, output)
            except subprocess.TimeoutExpired:
                timed_out = True
                raise
        finally:
            if child is not None:
                try:
                    reap(child)
                finally:
                    close_pipes(child)
                record = {'case': case, 'argv': argv, 'pid': child.pid,
                          'actual_return': child.returncode, 'timed_out': timed_out,
                          'reaped': child.returncode is not None,
                          'stdout_hex': bytes(output['stdout']).hex(),
                          'stderr_hex': bytes(output['stderr']).hex(),
                          'install_sha256': hashlib.sha256(self.install).hexdigest(),
                          'child_sha256': hashlib.sha256(self.child_source).hexdigest()}
                self.records.append(record)
                print(json.dumps(record, sort_keys=True))
            self.assertEqual(self._bounded(REPO / 'install.sh', 1048576), self.install)
            self.assertEqual(self._bounded(CHILD, 16384), self.child_source)
        return status, bytes(output['stdout']), bytes(output['stderr'])

    def _run_case(self, case):
        status, stdout, stderr = self._invoke('plain', ['generation', str(self.root / 'target')])
        self.assertEqual((status, stderr), (0, b''))
        expected = stdout.strip()
        self.assertIsNotNone(TOKEN.fullmatch(expected))
        staged = (self.root / 'stage/value').lstat()
        arguments = ['generation', str(self.root / 'stage')] if case == 'generation-fifo' else [
            'publish', str(self.root / 'stage'), str(self.root / 'target'),
            str(self.root / 'backup'), expected.decode('ascii')]
        status, stdout, stderr = self._invoke(case, arguments)
        event = json.loads(self._bounded(self.root / 'window.json', 1024))
        self.assertEqual(event, {'case': case, 'observed_inode': staged.st_ino,
                               'observed_device': staged.st_dev, 'synchronize': case != 'generation-fifo'})
        if case == 'regular':
            self.assertEqual((status, stderr), (0, b''))
            token, tab, backup = stdout.rstrip(b'\n').partition(b'\t')
            self.assertIsNotNone(TOKEN.fullmatch(token))
            self.assertEqual((tab, backup), (b'\t', os.fsencode(self.root / 'backup')))
            self.assertEqual(self._bounded(self.root / 'target/value', 128), NEW)
            self.assertEqual(self._bounded(self.root / 'backup/value', 128), OLD)
            self.assertFalse(os.path.lexists(self.root / 'stage'))
        else:
            self._refusal(case, status, stdout, stderr, staged)
        self.assertEqual(len(self.records), 2)
        self.assertTrue(all(record['reaped'] and not record['timed_out'] for record in self.records))

    def _refusal(self, case, status, stdout, stderr, staged):
        self.assertEqual((status, stdout), (1, b''))
        expected = {
            'fifo': b'ValueError: tree file changed before open',
            'generation-fifo': b'ValueError: tree file changed before open',
            'directory': b'ValueError: tree file changed before open',
            'symlink': b"OSError: [Errno 40] Too many levels of symbolic links: 'value'",
            'missing': b"FileNotFoundError: [Errno 2] No such file or directory: 'value'",
        }
        self.assertEqual(stderr.splitlines()[-1], expected[case])
        self.assertEqual(self._bounded(self.root / 'target/value', 128), OLD)
        self.assertFalse(os.path.lexists(self.root / 'backup'))
        retained = (self.root / 'retained-original').lstat()
        self.assertEqual((retained.st_dev, retained.st_ino), (staged.st_dev, staged.st_ino))
        self.assertEqual(self._bounded(self.root / 'retained-original', 128), NEW)
        if case in ('fifo', 'generation-fifo'):
            self.assertTrue(stat.S_ISFIFO((self.root / 'stage/value').lstat().st_mode))
        journals = [path.name for path in self.root.iterdir() if path.name.startswith('.sia-tree-cas-journal-')]
        self.assertEqual(journals, [])

    def test_regular_publish(self):
        self._run_case('regular')

    def test_fifo_substitution_refuses_without_waiting_for_writer(self):
        self._run_case('fifo')

    def test_symlink_substitution(self):
        self._run_case('symlink')

    def test_directory_substitution(self):
        self._run_case('directory')

    def test_missing_substitution(self):
        self._run_case('missing')

    def test_generation_fifo_substitution(self):
        self._run_case('generation-fifo')


if __name__ == '__main__':
    unittest.main()
