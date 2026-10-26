"""Native fence-metadata admission; no installer, service, or live store runs.

Each case owns a fresh /dev/shm directory.  The three heredocs are extracted
whole from their real consumers; uninstall runtime uses the real release CLI.
The fixed legacy runtime is a supported complete rung, not an installed-runtime
acceptance claim.  Three seconds is the existing atomic-admission deadline.
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


REPO = Path(__file__).resolve().parents[1]
MAX_SOURCE_BYTES = 1_048_576
MAX_PROGRAM_BYTES = 16_384
MAX_FIXTURE_BYTES = 4_096
MAX_OUTPUT_BYTES = 4_096
MAX_REPORT_BYTES = 32_768
MAX_DIRECTORY_ENTRIES = 16
CHILD_SECONDS = 3
REAP_SECONDS = 5
LEGACY_NAMES = (
    'sia-brainstem', 'sia-ledger', 'sia-mcp', 'siabench.py', 'sialib.py',
    'siamind.py', 'siaqueue.py', 'siatakes.py',
)
HEREDOCS = {
    'install-managed': ('install.sh', 'fenced_managed_file_authorized',
                        'fenced_runtime_authorized'),
    'install-runtime': ('install.sh', 'fenced_runtime_authorized',
                        'write_runtime_receipt'),
    'uninstall-managed': ('uninstall.sh', 'fenced_managed_file_authorized',
                          'fenced_runtime_authorized'),
}
CASES = ('regular', 'mismatch', 'journal_fifo', 'receipt_fifo')


def identity(value):
    """Reads may change atime; every other retained field must be unchanged."""
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, value.st_nlink, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns]


def bounded_read(path, limit):
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('test source exceeds declared read bound')
    return data


def reap(child):
    """The selected programs create no descendants; retain direct-child exit."""
    if child.poll() is None:
        child.kill()
    child.wait(timeout=REAP_SECONDS)


def collect(child, command, output):
    """Bound both pipes during collection, not after unbounded communicate()."""
    deadline = time.monotonic() + CHILD_SECONDS
    with selectors.DefaultSelector() as selector:
        for label, stream in (('stdout', child.stdout), ('stderr', child.stderr)):
            if stream is None:
                raise ValueError('child output pipe is missing')
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)
        # Each successful read consumes the finite output allowance or EOF;
        # the monotonic deadline also bounds silence and delayed EOF.
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


class FencedMetadataAdmission(unittest.TestCase):
    def setUp(self):
        self.assertTrue(stat.S_ISDIR(Path('/dev/shm').lstat().st_mode))
        fixture = tempfile.TemporaryDirectory(
            prefix='sia-fenced-metadata-', dir='/dev/shm')
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name)
        self.assertLessEqual(len(os.fsencode(self.root)), 128)
        self.paths = {'root': self.root}
        self.held = {}
        for name in ('home', 'tmp', 'runtime'):
            path = self.root / name
            path.mkdir(mode=0o700)
            self.paths[name] = path

    def _write(self, role, data, mode=0o600):
        self.assertLessEqual(len(data), MAX_FIXTURE_BYTES)
        path = self.paths[role]
        with path.open('xb') as stream:
            self.assertEqual(stream.write(data), len(data))
        path.chmod(mode)

    def _fenced_member(self, role, path, data):
        self.paths[role] = path
        self._write(role, data, 0o755)
        info = path.lstat()
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        self.addCleanup(os.close, descriptor)
        self.held[role] = descriptor
        self.assertEqual(identity(os.fstat(descriptor)), identity(info))
        path.chmod(0)
        return {'path': str(path), 'device': info.st_dev, 'inode': info.st_ino,
                'mode': stat.S_IMODE(info.st_mode),
                'sha256': hashlib.sha256(data).hexdigest()}

    def _members(self, consumer):
        if consumer.endswith('-managed'):
            target = self.root / 'managed-target'
            entry = self._fenced_member('target', target, b'fenced CLI bytes\n')
            return [entry], 'cli', target, entry['sha256']
        entries = []
        digest = hashlib.sha256(b'sia-runtime-v1\0')
        for name in LEGACY_NAMES:
            data = ('fenced fixture ' + name + '\n').encode('ascii')
            entry = self._fenced_member(
                name, self.paths['runtime'] / name, data)
            entries.append(entry)
            digest.update(name.encode('ascii') + b'\0' + hashlib.sha256(data).digest())
        return entries, 'runtime', self.paths['runtime'], digest.hexdigest()

    def _fixture(self, consumer, case):
        self.assertIn(case, CASES)
        entries, kind, target, digest = self._members(consumer)
        for role in ('journal', 'receipt', 'tombstone'):
            self.paths[role] = self.root / role
        payload = {'schema': 'sia-launch-fence-v1', 'entries': entries,
                   'runtime_before_digest': digest if kind == 'runtime' else '',
                   'runtime_digest': '', 'cli_digest': ''}
        receipt_digest = hashlib.sha256(b'mismatched receipt\n').hexdigest() \
            if case == 'mismatch' else digest
        if case == 'mismatch':
            self.assertNotEqual(receipt_digest, digest)
        receipt = (f'managed-by=khephri.sia\nkind={kind}\npath={target}\n'
                   f'sha256={receipt_digest}\n').encode('utf-8')
        data_by_role = {'journal': json.dumps(payload, sort_keys=True).encode('utf-8'),
                        'receipt': receipt, 'tombstone': b'removed-by=khephri.sia\n'}
        for role, data in data_by_role.items():
            if case == role + '_fifo':
                # No peer descriptor is ever opened: this is a native no-writer FIFO.
                os.mkfifo(self.paths[role], 0o600)
                self.assertTrue(stat.S_ISFIFO(self.paths[role].lstat().st_mode))
            else:
                self._write(role, data)
        return kind, target

    def _program(self, consumer):
        if consumer == 'uninstall-runtime':
            path = REPO / 'bin/siarelease.py'
            self.paths['program'] = path
            return path
        self.assertIn(consumer, HEREDOCS)
        source, name, next_name = HEREDOCS[consumer]
        data = bounded_read(REPO / source, MAX_SOURCE_BYTES)
        marker = (name + '() {\n').encode('ascii')
        following = (next_name + '() {\n').encode('ascii')
        self.assertEqual(data.count(marker), 1)
        function, separator, _ = data.partition(marker)[2].partition(following)
        self.assertTrue(separator)
        opening = b"<<'PY'\n"
        self.assertEqual(function.count(opening), 1)
        program, separator, suffix = function.partition(opening)[2].partition(b'\nPY\n')
        self.assertTrue(separator)
        self.assertEqual(suffix, b'}\n\n')
        program += b'\n'
        self.assertLessEqual(len(program), MAX_PROGRAM_BYTES)
        path = self.root / 'actual-program.py'
        with path.open('xb') as stream:
            self.assertEqual(stream.write(program), len(program))
        self.paths['program'] = path
        return path

    def _arguments(self, consumer, kind, target):
        journal, receipt, tombstone = (str(self.paths[role])
                                      for role in ('journal', 'receipt', 'tombstone'))
        if consumer == 'install-managed':
            return [journal, receipt, kind, str(target), 'check', tombstone]
        if consumer == 'install-runtime':
            return [journal, receipt, str(target), tombstone]
        if consumer == 'uninstall-managed':
            return [journal, tombstone, receipt, kind, str(target)]
        self.assertEqual(consumer, 'uninstall-runtime')
        return ['runtime-authorize-fence', journal, tombstone, receipt, str(target)]

    def _observe(self, role, path):
        info = path.lstat()
        self.assertEqual(info.st_uid, os.geteuid())
        data, children = None, None
        if stat.S_ISREG(info.st_mode):
            limit = MAX_SOURCE_BYTES if role == 'program' else MAX_FIXTURE_BYTES
            if role in self.held:
                descriptor = self.held[role]
                self.assertEqual(identity(os.fstat(descriptor)), identity(info))
                data = os.pread(descriptor, limit + 1, 0)
            else:
                data = bounded_read(path, limit)
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
            self.assertTrue(stat.S_ISFIFO(info.st_mode))
            self.assertEqual(info.st_nlink, 1)
        self.assertEqual(identity(path.lstat()), identity(info))
        return {'identity': identity(info), 'children': children,
                'sha256': None if data is None else hashlib.sha256(data).hexdigest()}, data

    def _snapshot(self):
        self.assertLessEqual(len(self.paths), 16)
        return {role: self._observe(role, path) for role, path in self.paths.items()}

    def _preserved(self, before, consumer, case, command, output, child, timed_out):
        after = self._snapshot()
        report = {'consumer': consumer, 'case': case, 'child_command': command,
                  'child_deadline_seconds': CHILD_SECONDS, 'child_timeout': timed_out,
                  'child_pid': None if child is None else child.pid,
                  'child_exit': None if child is None else child.returncode,
                  'child_reap_state': 'NOT_STARTED' if child is None else
                      'UNKNOWN' if child.returncode is None else 'REAPED',
                  'stdout_hex': bytes(output['stdout']).hex(),
                  'stderr_hex': bytes(output['stderr']).hex(),
                  'fixture_before': {key: value[0] for key, value in before.items()},
                  'fixture_after': {key: value[0] for key, value in after.items()}}
        encoded = json.dumps(report, sort_keys=True)
        self.assertLessEqual(len(encoded.encode('utf-8')), MAX_REPORT_BYTES)
        print(encoded)
        self.assertEqual(after.keys(), before.keys())
        for role in before:
            self.assertEqual(after[role][0], before[role][0], role + ' metadata changed')
            self.assertEqual(after[role][1], before[role][1], role + ' actual bytes changed')

    def _case(self, consumer, case):
        kind, target = self._fixture(consumer, case)
        program = self._program(consumer)
        command = [sys.executable, '-I', '-S', '-B', '-W', 'error', str(program)]
        command.extend(self._arguments(consumer, kind, target))
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
                    try:
                        if child.stdout is not None:
                            child.stdout.close()
                    finally:
                        if child.stderr is not None:
                            child.stderr.close()
        finally:
            self._preserved(before, consumer, case, command, output, child, timed_out)
        expected = 0 if case == 'regular' else 2 if consumer == 'uninstall-runtime' else 1
        self.assertEqual(status, expected)
        self.assertEqual(bytes(output['stdout']), b'')
        stderr = b''
        if consumer == 'uninstall-runtime' and case != 'regular':
            reason = b'runtime receipt does not match launch fence' if case == 'mismatch' \
                else b'unsafe managed metadata'
            stderr = b'SIA runtime fence refused: ' + reason + b'\n'
        self.assertEqual(bytes(output['stderr']), stderr)

    def test_install_managed_regular_accepts(self):
        self._case('install-managed', 'regular')

    def test_install_managed_mismatched_receipt_refuses(self):
        self._case('install-managed', 'mismatch')

    def test_install_managed_journal_fifo_refuses(self):
        self._case('install-managed', 'journal_fifo')

    def test_install_managed_receipt_fifo_refuses(self):
        self._case('install-managed', 'receipt_fifo')

    def test_install_runtime_regular_accepts(self):
        self._case('install-runtime', 'regular')

    def test_install_runtime_mismatched_receipt_refuses(self):
        self._case('install-runtime', 'mismatch')

    def test_install_runtime_journal_fifo_refuses(self):
        self._case('install-runtime', 'journal_fifo')

    def test_install_runtime_receipt_fifo_refuses(self):
        self._case('install-runtime', 'receipt_fifo')

    def test_uninstall_managed_regular_accepts(self):
        self._case('uninstall-managed', 'regular')

    def test_uninstall_managed_mismatched_receipt_refuses(self):
        self._case('uninstall-managed', 'mismatch')

    def test_uninstall_managed_journal_fifo_refuses(self):
        self._case('uninstall-managed', 'journal_fifo')

    def test_uninstall_managed_receipt_fifo_refuses(self):
        self._case('uninstall-managed', 'receipt_fifo')

    def test_uninstall_runtime_regular_accepts(self):
        self._case('uninstall-runtime', 'regular')

    def test_uninstall_runtime_mismatched_receipt_refuses(self):
        self._case('uninstall-runtime', 'mismatch')

    def test_uninstall_runtime_journal_fifo_refuses(self):
        self._case('uninstall-runtime', 'journal_fifo')

    def test_uninstall_runtime_receipt_fifo_refuses(self):
        self._case('uninstall-runtime', 'receipt_fifo')


if __name__ == '__main__':
    unittest.main()
