"""Native admission of the complete install/uninstall tree-CAS journals.

Only exact extracted heredocs run against private /dev/shm trees.  Existing
lock bookkeeping and valid journal retirement are explicit permitted effects;
this is neither a mutation-free operation nor installed qualification.
"""

from pathlib import Path
import errno
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest

from tests import sia_test_home
from tests.test_release_metadata_admission import (
    CHILD_SECONDS, MAX_OUTPUT_BYTES, REAP_SECONDS, REPO,
    close_pipes, collect, identity, reap,
)


MAX_SOURCE_BYTES = 1_048_576
MAX_PROGRAM_BYTES = 32_768
MAX_FIXTURE_BYTES = 4_096
MAX_REPORT_BYTES = 32_768
MAX_PATHS = 16
MAX_DIRECTORY_ENTRIES = 16
CONSUMERS = ('install', 'uninstall')
CASES = ('regular', 'absent', 'fifo', 'symlink', 'directory', 'malformed', 'schema')
OPTIONAL_ROLES = ('journal', 'lock', 'stage', 'archive', 'backup', 'link_target')
SOURCE_ROLES = ('source', 'harness', 'isolation_source', 'test_source')
TOKEN = re.compile(rb'tree:(?:[0-9]+:){8}[0-9a-f]{64}\n')


class TreeJournalAdmission(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.path.expanduser('~'), sia_test_home.ISOLATED_HOME)
        self.assertEqual((CHILD_SECONDS, MAX_OUTPUT_BYTES, REAP_SECONDS), (3, 4096, 5))
        self.assertTrue(stat.S_ISDIR(Path('/dev/shm').lstat().st_mode))
        fixture = tempfile.TemporaryDirectory(prefix='sia-tree-journal-', dir='/dev/shm')
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name)
        self.assertLessEqual(len(os.fsencode(self.root)), 128)
        self.assertEqual(stat.S_IMODE(self.root.lstat().st_mode), 0o700)
        self.paths = {'root': self.root, 'test_source': Path(__file__).resolve(),
                      'harness': REPO / 'tests/test_release_metadata_admission.py',
                      'isolation_source': Path(sia_test_home.__file__).resolve()}
        for role in ('home', 'tmp', 'target'):
            self.paths[role] = self.root / role
            self.paths[role].mkdir(mode=0o700)
        self.paths['member'] = self.paths['target'] / 'member'
        self.paths['program'] = self.root / 'actual-tree-cas.py'
        for role in ('stage', 'archive', 'backup', 'link_target'):
            self.paths[role] = self.root / role
        suffix = hashlib.sha256(os.fsencode(self.paths['target'])).hexdigest()
        self.paths['journal'] = self.root / ('.sia-tree-cas-journal-' + suffix)
        self.paths['lock'] = self.root / ('.sia-tree-cas-lock-' + suffix)
        self._write('member', b'immutable tree member\n')
        self.child_count = 0

    def _write(self, role, data):
        limit = MAX_PROGRAM_BYTES if role == 'program' else MAX_FIXTURE_BYTES
        self.assertLessEqual(len(data), limit)
        with self.paths[role].open('xb') as stream:
            self.assertEqual(stream.write(data), len(data))
        self.paths[role].chmod(0o600)

    def _program(self, consumer):
        self.assertIn(consumer, CONSUMERS)
        self.paths['source'] = REPO / (consumer + '.sh')
        _metadata, self.source_bytes = self._observe('source', self.paths['source'])
        self.assertIsInstance(self.source_bytes, bytes)
        opening = b'owned_tree_cas() {\n  python3 - "$@" <<\'PY\'\n'
        following = b'owned_tree_generation() {\n'
        closing = b'\nPY\n}\n'
        self.assertEqual(self.source_bytes.count(opening), 1)
        self.assertEqual(self.source_bytes.count(following), 1)
        body, separator, _tail = self.source_bytes.partition(opening)[2].partition(following)
        self.assertTrue(separator)
        self.assertEqual(body.count(closing), 1)
        program, separator, suffix = body.partition(closing)
        self.assertTrue(separator)
        self.assertEqual(suffix, b'\n')
        self.assertTrue(program)
        self._write('program', program + b'\n')

    def _regular_journal(self, consumer, token):
        record = {'version': 1, 'target': 'target', 'backup': 'backup',
                  'archive': 'archive', 'expected': token}
        if consumer == 'install':
            # A completed fresh publication: the desired tree is current,
            # while its prior target, stage and archive are absent.
            record.update({'expected': 'absent', 'desired': token, 'staged': 'stage'})
        # Uninstall's prepared archive has not renamed the unchanged target.
        self._write('journal', (json.dumps(record, sort_keys=True) + '\n').encode('ascii'))

    def _fixture(self, consumer, case):
        self.assertIn(case, CASES)
        self._program(consumer)
        if case != 'absent':
            self._write('lock', b'')
        if case == 'regular':
            status, stdout, stderr = self._invoke(consumer, case, 'generation')
            self.assertEqual((status, stderr), (0, b''))
            self.assertIsNotNone(TOKEN.fullmatch(stdout))
            self._regular_journal(consumer, stdout[:-1].decode('ascii'))
        elif case == 'fifo':
            # No peer is opened: this is a native FIFO without a writer.
            os.mkfifo(self.paths['journal'], 0o600)
            self.assertTrue(stat.S_ISFIFO(self.paths['journal'].lstat().st_mode))
        elif case == 'symlink':
            self._write('link_target', b'unchanged symlink destination\n')
            self.paths['journal'].symlink_to(self.paths['link_target'])
        elif case == 'directory':
            self.paths['journal'].mkdir(mode=0o700)
        elif case == 'malformed':
            self._write('journal', b'{')
        elif case == 'schema':
            self._write('journal', b'{}')
        else:
            self.assertEqual(case, 'absent')
            self.assertFalse(os.path.lexists(self.paths['journal']))
            self.assertFalse(os.path.lexists(self.paths['lock']))

    def _observe(self, role, path):
        try:
            info = path.lstat()
        except FileNotFoundError:
            self.assertIn(role, OPTIONAL_ROLES)
            return {'state': 'absent'}, None
        self.assertEqual(info.st_uid, os.geteuid())
        data, children, link = None, None, None
        if stat.S_ISREG(info.st_mode):
            limit = MAX_SOURCE_BYTES if role in SOURCE_ROLES else MAX_PROGRAM_BYTES \
                if role == 'program' else MAX_FIXTURE_BYTES
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
        elif stat.S_ISLNK(info.st_mode):
            self.assertEqual(role, 'journal')
            link = os.readlink(path)
            self.assertEqual(link, str(self.paths['link_target']))
        else:
            self.assertEqual(role, 'journal')
            self.assertTrue(stat.S_ISFIFO(info.st_mode))
            self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
            self.assertEqual(info.st_nlink, 1)
        self.assertEqual(identity(path.lstat()), identity(info))
        return {'state': 'present', 'identity': identity(info), 'children': children,
                'link': link, 'sha256': None if data is None else hashlib.sha256(data).hexdigest()}, data

    def _snapshot(self):
        self.assertEqual(len(self.paths), MAX_PATHS)
        return {role: self._observe(role, path) for role, path in self.paths.items()}

    def _lock_effect(self, before, after):
        lock_meta, lock_bytes = after
        self.assertEqual(lock_meta['state'], 'present')
        fields = lock_meta['identity']
        self.assertTrue(stat.S_ISREG(fields[2]))
        self.assertEqual(stat.S_IMODE(fields[2]), 0o600)
        self.assertEqual((fields[3], fields[5], fields[6]), (os.geteuid(), 1, 0))
        self.assertEqual(lock_bytes, b'')
        if before[0]['state'] == 'present':
            self.assertEqual(fields[:-1], before[0]['identity'][:-1])
            self.assertEqual(lock_bytes, before[1])
            self.assertEqual(lock_meta['children'], before[0]['children'])
            self.assertEqual(lock_meta['link'], before[0]['link'])
            self.assertEqual(lock_meta['sha256'], before[0]['sha256'])

    def _changes(self, before, after, case, phase):
        self.assertEqual(after.keys(), before.keys())
        if phase == 'generation':
            self.assertEqual(after, before, 'generation changed fixture or source')
            return
        self._lock_effect(before['lock'], after['lock'])
        changed_root = case in ('regular', 'absent')
        for role in before:
            if role == 'lock':
                continue
            if role == 'journal' and case == 'regular':
                self.assertEqual(after[role], ({'state': 'absent'}, None))
            elif role == 'root' and changed_root:
                old, new = before[role][0], after[role][0]
                self.assertEqual(new['identity'][:6], old['identity'][:6])
                children = list(old['children'])
                if case == 'regular':
                    children.remove(self.paths['journal'].name)
                else:
                    children.append(self.paths['lock'].name)
                self.assertEqual(new['children'], sorted(children))
                self.assertEqual((new['link'], new['sha256'], after[role][1]), (None, None, None))
            else:
                self.assertEqual(after[role], before[role], role + ' bytes or metadata changed')

    def _preserved(self, before, consumer, case, phase, command, output, child, timed_out):
        after = self._snapshot()
        report = {'consumer': consumer, 'case': case, 'phase': phase,
                  'child_ordinal': self.child_count, 'child_command': command,
                  'child_deadline_seconds': CHILD_SECONDS, 'child_timeout': timed_out,
                  'child_pid': None if child is None else child.pid,
                  'child_exit': None if child is None else child.returncode,
                  'child_reap_state': 'NOT_STARTED' if child is None else
                      'UNKNOWN' if child.returncode is None else 'REAPED',
                  'source_sha256': before['source'][0]['sha256'],
                  'helper_sha256': before['program'][0]['sha256'],
                  'harness_sha256': before['harness'][0]['sha256'],
                  'test_sha256': before['test_source'][0]['sha256'],
                  'stdout_hex': bytes(output['stdout']).hex(),
                  'stderr_hex': bytes(output['stderr']).hex(),
                  'fixture_before': {role: value[0] for role, value in before.items()},
                  'fixture_after': {role: value[0] for role, value in after.items()}}
        encoded = json.dumps(report, sort_keys=True)
        self.assertLessEqual(len(encoded.encode('utf-8')), MAX_REPORT_BYTES)
        print(encoded)
        self._changes(before, after, case, phase)

    def _invoke(self, consumer, case, phase):
        self.assertIn(phase, ('generation', 'recover'))
        self.child_count += 1
        self.assertLessEqual(self.child_count, 2 if case == 'regular' else 1)
        command = [sys.executable, '-I', '-S', '-B', '-W', 'error',
                   str(self.paths['program']), phase, str(self.paths['target'])]
        environment = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
                       'HOME': str(self.paths['home']), 'TMPDIR': str(self.paths['tmp'])}
        before, output = self._snapshot(), {'stdout': bytearray(), 'stderr': bytearray()}
        self.assertEqual(before['source'][1], self.source_bytes)
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
            self._preserved(before, consumer, case, phase, command, output, child, timed_out)
        self.assertIsNotNone(child)
        self.assertIsNotNone(child.returncode, 'child terminal state was not observed')
        self.assertEqual(child.returncode, status)
        return status, bytes(output['stdout']), bytes(output['stderr'])

    def _refusal(self, case):
        if case in ('fifo', 'directory'):
            return b'ValueError: unsafe tree CAS journal\n'
        if case == 'symlink':
            return (f'OSError: [Errno {errno.ELOOP}] Too many levels of symbolic links: '
                    f'{self.paths["journal"].name!r}\n').encode('ascii')
        if case == 'schema':
            return b'ValueError: invalid tree CAS journal\n'
        self.assertEqual(case, 'malformed')
        return (b'json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: '
                b'line 1 column 2 (char 1)\n')

    def _case(self, consumer, case):
        self._fixture(consumer, case)
        status, stdout, stderr = self._invoke(consumer, case, 'recover')
        self.assertEqual(self.child_count, 2 if case == 'regular' else 1)
        self.assertEqual(stdout, b'')
        if case in ('regular', 'absent'):
            self.assertEqual((status, stderr), (0, b''))
        else:
            self.assertEqual(status, 1)
            self.assertTrue(stderr.startswith(b'Traceback (most recent call last):\n'))
            self.assertTrue(stderr.endswith(self._refusal(case)), stderr)

    def test_install_regular_journal_recovers(self):
        self._case('install', 'regular')

    def test_install_absent_journal_accepts(self):
        self._case('install', 'absent')

    def test_install_fifo_journal_refuses(self):
        self._case('install', 'fifo')

    def test_install_symlink_journal_refuses(self):
        self._case('install', 'symlink')

    def test_install_directory_journal_refuses(self):
        self._case('install', 'directory')

    def test_install_malformed_journal_refuses(self):
        self._case('install', 'malformed')

    def test_install_invalid_schema_journal_refuses(self):
        self._case('install', 'schema')

    def test_uninstall_regular_journal_recovers(self):
        self._case('uninstall', 'regular')

    def test_uninstall_absent_journal_accepts(self):
        self._case('uninstall', 'absent')

    def test_uninstall_fifo_journal_refuses(self):
        self._case('uninstall', 'fifo')

    def test_uninstall_symlink_journal_refuses(self):
        self._case('uninstall', 'symlink')

    def test_uninstall_directory_journal_refuses(self):
        self._case('uninstall', 'directory')

    def test_uninstall_malformed_journal_refuses(self):
        self._case('uninstall', 'malformed')

    def test_uninstall_invalid_schema_journal_refuses(self):
        self._case('uninstall', 'schema')


if __name__ == '__main__':
    unittest.main()
