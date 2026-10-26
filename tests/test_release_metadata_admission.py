"""Native admission of release metadata and ordinary runtime members.

The actual release CLI runs inside fresh /dev/shm fixtures.  No installer,
service or live state is invoked.  The deadlines and pipe bounds match the
existing fenced-metadata regression harness.
"""

from pathlib import Path
import hashlib
import json
import os
import selectors
import stat
import subprocess
import sys
import tempfile
import time
import unittest

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home


REPO = Path(__file__).resolve().parents[1]
PROGRAM = REPO / 'bin/siarelease.py'
MAX_SOURCE_BYTES = 1_048_576
MAX_FIXTURE_BYTES = 4_096
MAX_OUTPUT_BYTES = 4_096
MAX_REPORT_BYTES = 32_768
MAX_PATHS = 16
MAX_DIRECTORY_ENTRIES = 8
CHILD_SECONDS = 3
REAP_SECONDS = 5
ROLES = ('source', 'resident', 'completion')
LABELS = {'source': 'installer runtime', 'resident': 'resident runtime',
          'completion': 'first-light completion'}
CASES = ('source_fifo', 'resident_fifo', 'completion_fifo', 'regular',
         'optional_absent', 'resident_newer', 'completion_newer')
LEGACY_NAMES = ('sia-brainstem', 'sia-ledger', 'sia-mcp', 'siabench.py',
                'sialib.py', 'siamind.py', 'siaqueue.py', 'siatakes.py')


def identity(value):
    """Reading may alter atime; all other retained fields must stay fixed."""
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, value.st_nlink, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns]


def collect(child, command, output):
    """Consume bounded pipes until EOF under one monotonic deadline."""
    deadline = time.monotonic() + CHILD_SECONDS
    with selectors.DefaultSelector() as selector:
        for label, stream in (('stdout', child.stdout), ('stderr', child.stderr)):
            if stream is None:
                raise ValueError('child output pipe is missing')
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)
        # A read consumes finite output capacity or EOF; silence is bounded
        # by the deadline.  No unbounded communicate() output buffer is used.
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, CHILD_SECONDS)
            for key, _events in selector.select(remaining):
                room = MAX_OUTPUT_BYTES - len(output[key.data])
                chunk = os.read(key.fileobj.fileno(), room + 1)
                if len(chunk) > room:
                    raise ValueError('child output exceeds declared byte bound')
                if chunk:
                    output[key.data].extend(chunk)
                else:
                    selector.unregister(key.fileobj)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, CHILD_SECONDS)
        return child.wait(timeout=remaining)


def reap(child):
    """One cleanup attempt; the actual release CLI creates no descendants."""
    if child.poll() is None:
        child.kill()
    child.wait(timeout=REAP_SECONDS)


def close_pipes(child):
    try:
        if child.stdout is not None:
            child.stdout.close()
    finally:
        if child.stderr is not None:
            child.stderr.close()


class ReleaseMetadataAdmission(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.path.expanduser('~'), sia_test_home.ISOLATED_HOME)
        self.assertTrue(stat.S_ISDIR(Path('/dev/shm').lstat().st_mode))
        fixture = tempfile.TemporaryDirectory(
            prefix='sia-release-metadata-', dir='/dev/shm')
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name)
        self.assertLessEqual(len(os.fsencode(self.root)), 128)
        self.assertEqual(stat.S_IMODE(self.root.lstat().st_mode), 0o700)
        self.paths = {'root': self.root, 'program': PROGRAM}
        self.assertTrue(stat.S_ISREG(PROGRAM.lstat().st_mode))
        for role in ('home', 'tmp'):
            self.paths[role] = self.root / role
            self.paths[role].mkdir(mode=0o700)

    def _write(self, role, data):
        self.assertLessEqual(len(data), MAX_FIXTURE_BYTES)
        with self.paths[role].open('xb') as stream:
            self.assertEqual(stream.write(data), len(data))
        self.paths[role].chmod(0o600)

    def _fixture(self, case):
        self.assertIn(case, CASES)
        for role in ROLES:
            self.paths[role] = self.root / role
        versions = {'source': '2.0.0', 'resident': '2.0.0', 'completion': '2.0.0'}
        if case == 'resident_newer':
            versions['resident'] = '3.0.0'
        if case == 'completion_newer':
            versions['completion'] = '3.0.0'
        for role in ROLES:
            if case == 'optional_absent' and role != 'source':
                continue
            if case == role + '_fifo':
                # No test peer is opened: the FIFO has no writer.
                os.mkfifo(self.paths[role], 0o600)
                self.assertTrue(stat.S_ISFIFO(self.paths[role].lstat().st_mode))
                continue
            if role == 'completion':
                data = json.dumps({'v': 1, 'version': versions[role],
                                   'state': 'ready'}, sort_keys=True).encode('ascii')
            else:
                data = ('VERSION = "' + versions[role] + '"\n').encode('ascii')
            self._write(role, data)

    def _runtime_fixture(self, fifo):
        self.paths['runtime'] = self.root / 'runtime'
        self.paths['runtime'].mkdir(mode=0o700)
        # Independent receipt construction: no helper under test is imported.
        digest = hashlib.sha256(b'sia-runtime-v1\0')
        for name in LEGACY_NAMES:
            self.paths[name] = self.paths['runtime'] / name
            data = ('ordinary runtime fixture ' + name + '\n').encode('ascii')
            if fifo and name == 'sia-brainstem':
                os.mkfifo(self.paths[name], 0o600)
                info = self.paths[name].lstat()
                self.assertTrue(stat.S_ISFIFO(info.st_mode))
                self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
            else:
                self._write(name, data)
            digest.update(name.encode('ascii') + b'\0' + hashlib.sha256(data).digest())
        return digest.hexdigest()

    def _runtime_journal(self, digest):
        # Nonzero-mode regular members are measured from bytes, without
        # consulting mode-zero fence entries.  The empty list is valid here.
        payload = {'schema': 'sia-launch-fence-v1', 'entries': [],
                   'runtime_before_digest': digest, 'runtime_digest': '', 'cli_digest': ''}
        receipt = ('managed-by=khephri.sia\nkind=runtime\n'
                   f'path={self.paths["runtime"]}\nsha256={digest}\n').encode('utf-8')
        data_by_role = {'journal': json.dumps(payload, sort_keys=True).encode('ascii'),
                        'receipt': receipt, 'tombstone': b'removed-by=khephri.sia\n'}
        for role, data in data_by_role.items():
            self.paths[role] = self.root / role
            self._write(role, data)

    def _observe(self, role, path):
        try:
            info = path.lstat()
        except FileNotFoundError:
            self.assertIn(role, ('resident', 'completion'))
            return {'state': 'absent'}, None
        self.assertEqual(info.st_uid, os.geteuid())
        data, children = None, None
        if stat.S_ISREG(info.st_mode):
            limit = MAX_SOURCE_BYTES if role == 'program' else MAX_FIXTURE_BYTES
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
            self.assertIn(role, ROLES + ('sia-brainstem',))
            self.assertTrue(stat.S_ISFIFO(info.st_mode))
            self.assertEqual(info.st_nlink, 1)
        self.assertEqual(identity(path.lstat()), identity(info))
        return {'state': 'present', 'identity': identity(info), 'children': children,
                'sha256': None if data is None else hashlib.sha256(data).hexdigest()}, data

    def _snapshot(self):
        self.assertLessEqual(len(self.paths), MAX_PATHS)
        return {role: self._observe(role, path) for role, path in self.paths.items()}

    def _preserved(self, before, case, command, output, child, timed_out):
        after = self._snapshot()
        report = {'case': case, 'child_command': command,
                  'child_deadline_seconds': CHILD_SECONDS, 'child_timeout': timed_out,
                  'child_pid': None if child is None else child.pid,
                  'child_exit': None if child is None else child.returncode,
                  'child_reap_state': 'NOT_STARTED' if child is None else
                      'UNKNOWN' if child.returncode is None else 'REAPED',
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

    def _expected(self, case):
        if case in ('regular', 'optional_absent'):
            return 0, b''
        if case.endswith('_fifo'):
            role = case.removesuffix('_fifo')
            reason = LABELS[role] + ' is not an owner-controlled regular file'
        else:
            self.assertIn(case, ('resident_newer', 'completion_newer'))
            role = case.removesuffix('_newer')
            reason = ('release downgrade refused: ' + LABELS[role]
                      + ' 3.0.0 is newer than installer 2.0.0')
        return 2, ('SIA installer refused: ' + reason + '\n').encode('ascii')

    def _run(self, case, arguments, expected_status, expected_stdout, expected_stderr):
        command = [sys.executable, '-I', '-S', '-B', '-W', 'error', str(PROGRAM)]
        command.extend(arguments)
        environment = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
                       'HOME': str(self.paths['home']), 'TMPDIR': str(self.paths['tmp'])}
        before, output = self._snapshot(), {'stdout': bytearray(), 'stderr': bytearray()}
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
        self.assertEqual(status, expected_status)
        self.assertEqual(child.returncode, status)
        self.assertEqual(bytes(output['stdout']), expected_stdout)
        self.assertEqual(bytes(output['stderr']), expected_stderr)

    def _case(self, case):
        self._fixture(case)
        expected_status, expected_stderr = self._expected(case)
        arguments = [str(self.paths[role]) for role in ROLES]
        self._run(case, arguments, expected_status, b'', expected_stderr)

    def _runtime_case(self, consumer, fifo):
        self.assertIn(consumer, ('runtime-tree-digest', 'runtime-authorize-fence'))
        self.assertIsInstance(fifo, bool)
        digest = self._runtime_fixture(fifo)
        arguments = [consumer]
        if consumer == 'runtime-authorize-fence':
            self._runtime_journal(digest)
            arguments.extend(str(self.paths[role])
                             for role in ('journal', 'tombstone', 'receipt'))
        arguments.append(str(self.paths['runtime']))
        expected_status, expected_stdout, expected_stderr = 0, b'', b''
        if fifo:
            expected_status = 2
            prefix = 'digest' if consumer == 'runtime-tree-digest' else 'fence'
            expected_stderr = (f'SIA runtime {prefix} refused: '
                               'unsafe runtime member: sia-brainstem\n').encode('ascii')
        elif consumer == 'runtime-tree-digest':
            expected_stdout = (digest + '\n').encode('ascii')
        case = consumer + ('-fifo' if fifo else '-regular')
        self._run(case, arguments, expected_status, expected_stdout, expected_stderr)

    def test_source_fifo_refuses(self):
        self._case('source_fifo')

    def test_resident_fifo_refuses(self):
        self._case('resident_fifo')

    def test_completion_fifo_refuses(self):
        self._case('completion_fifo')

    def test_regular_metadata_accepts(self):
        self._case('regular')

    def test_absent_optional_metadata_accepts(self):
        self._case('optional_absent')

    def test_newer_resident_refuses_downgrade(self):
        self._case('resident_newer')

    def test_newer_completion_refuses_downgrade(self):
        self._case('completion_newer')

    def test_runtime_digest_regular_accepts(self):
        self._runtime_case('runtime-tree-digest', False)

    def test_runtime_digest_fifo_refuses(self):
        self._runtime_case('runtime-tree-digest', True)

    def test_runtime_authorize_regular_accepts(self):
        self._runtime_case('runtime-authorize-fence', False)

    def test_runtime_authorize_fifo_refuses(self):
        self._runtime_case('runtime-authorize-fence', True)


if __name__ == '__main__':
    unittest.main()
