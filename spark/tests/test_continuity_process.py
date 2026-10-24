"""Actual disposable continuity I/O, independent vectors and refusal controls."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'continuity_process', ROOT / 'transport/continuity_process.py')
process = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = process
SPEC.loader.exec_module(process)
PROBE = ROOT / 'bin/continuity_probe'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checkpoint(*, ready=False):
    # Independent zero-based literal layout, not production payload helpers.
    data = bytearray(10816)
    data[0], data[32], data[64], data[160], data[263] = 1, 2, 3, 6, 1
    for index in range(64):
        start = 320 + index * 128
        data[start + 105], data[start + 106] = 3, 2
    if ready:
        data[271], data[293] = 4, 4
        data[280:293] = bytes([2] * 13)
        for index, kind in enumerate((0, 1, 6, 10)):
            data[280 + kind] = 4
            start = 320 + index * 128
            data[start] = data[start + 32] = data[start + 103] = index + 1
            data[start + 104:start + 107] = bytes((kind, 0, 0))
    return data


def restore_vector():
    before = checkpoint(ready=True)
    current = bytearray(12128)
    current[:160] = before[:160]
    current[160:192] = before[160:192]
    current[192:224] = before[224:256]
    current[224:248] = before[256:280]
    for start in (248, 296):
        current[start:start + 2] = b'\x01\x01'
        current[start + 9] = 1
        current[start + 10] = 6
    for index in range(64):
        start = 352 + index * 144
        current[start] = 2 if index < 4 else 0
        current[start + 1:start + 129] = before[320 + index * 128:448 + index * 128]
    frame = bytearray(32768)
    frame[:8] = b'SIAC\x01\x01\x59\xc0'
    frame[32:10848], frame[10848:22976] = before, current
    return bytes(frame)


def transition_vector():
    before, after = checkpoint(), checkpoint()
    after[160], after[192], after[263] = 7, 6, 2
    frame = bytearray(32768)
    frame[:8] = b'SIAC\x01\x02\x70\xa0'
    frame[32:10848], frame[10848:21664] = before, after
    for index in range(16):
        frame[21664 + index * 448 + 433] = 1
    return bytes(frame)


def response(operation, code):
    return b'SIAR\x01' + bytes((operation, operation, code)) + bytes(56)


class ContinuityProcess(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PROBE.is_file():
            raise RuntimeError('build spark/transport/continuity_probe.gpr first')
        cls.identity = sha(PROBE)

    def run_probe(self, payload, operation=1, **kwargs):
        return process.run(PROBE, self.identity, payload, operation, **kwargs)

    def raw(self, payload, *, stdin=None, stdout=subprocess.PIPE):
        descriptor = process.pin_executable(PROBE, self.identity)
        try:
            return subprocess.run(process.command(descriptor), input=payload,
                                  stdin=stdin, stdout=stdout, stderr=subprocess.PIPE,
                                  pass_fds=(descriptor,), restore_signals=False,
                                  timeout=5, check=False)
        finally:
            os.close(descriptor)

    def test_real_restore_and_transition_and_policy_refusals(self):
        for vector, operation, expected in ((restore_vector(), 1, 7),
                                            (transition_vector(), 2, 9)):
            result = self.run_probe(vector, operation)
            self.assertEqual((result.operation, result.code, result.transport_refused),
                             (operation, expected, False))
            self.assertEqual(result.request_sha256, hashlib.sha256(vector).hexdigest())
            self.assertEqual(result.executable_sha256, self.identity)
        changed = bytearray(restore_vector())
        changed[10848 + 96] = 9
        self.assertEqual(self.run_probe(bytes(changed)).code, 5)
        changed = bytearray(transition_vector())
        changed[10848 + 32] = 9
        self.assertEqual(self.run_probe(bytes(changed), 2).code, 3)

    def test_syntax_failures_do_not_become_policy_results(self):
        for index, value in ((0, 0), (4, 2), (5, 0), (6, 0), (8, 1),
                             (32767, 1), (32 + 293, 65), (32 + 256, 128)):
            bad = bytearray(restore_vector())
            bad[index] = value
            with self.subTest(index=index):
                result = self.run_probe(bytes(bad))
                self.assertEqual((result.operation, result.code, result.transport_refused),
                                 (0, 1, True))

    def test_truncation_excess_and_exact_eof(self):
        vector = restore_vector()
        for length in (0, 1, 31, 10848, 22976, 32767, 32768, 32769):
            payload = (vector + b'x')[:length]
            result = self.raw(payload)
            with self.subTest(length=length):
                self.assertEqual(result.stderr, b'')
                self.assertEqual(result.returncode, 0 if length == 32768 else 65)
                self.assertEqual(result.stdout, response(1, 7) if length == 32768
                                 else response(0, 1))

    def test_descriptor_read_and_write_errors(self):
        descriptor = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            result = self.raw(None, stdin=descriptor)
        finally:
            os.close(descriptor)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (74, b'', b''))
        with open('/dev/full', 'wb', buffering=0) as output:
            result = self.raw(restore_vector(), stdout=output)
        self.assertEqual((result.returncode, result.stderr), (74, b''))

    def test_broken_pipe_is_checked_with_inherited_sigpipe_ignore(self):
        reader, writer = os.pipe()
        os.close(reader)
        try:
            result = self.raw(restore_vector(), stdout=writer)
        finally:
            os.close(writer)
        self.assertEqual((result.returncode, result.stderr), (74, b''))

    def test_live_limits_eof_wait_and_fragmented_input(self):
        descriptor = process.pin_executable(PROBE, self.identity)
        child = subprocess.Popen(process.command(descriptor), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 pass_fds=(descriptor,), restore_signals=False,
                                 start_new_session=True)
        os.close(descriptor)
        try:
            for _ in range(200):
                if Path(f'/proc/{child.pid}/exe').resolve() == PROBE.resolve():
                    break
                if child.poll() is not None:
                    self.fail('adapter died before resource readback')
                time.sleep(0.01)
            else:
                self.fail('adapter exec not observed')
            expected = {resource.RLIMIT_AS: 268435456, resource.RLIMIT_STACK: 16777216,
                        resource.RLIMIT_CPU: 10, resource.RLIMIT_NOFILE: 16,
                        resource.RLIMIT_NPROC: 0, resource.RLIMIT_FSIZE: 0,
                        resource.RLIMIT_CORE: 0}
            observed = {str(kind): resource.prlimit(child.pid, kind) for kind in expected}
            for kind, value in expected.items():
                self.assertEqual(observed[str(kind)], (value, value))
            status = Path(f'/proc/{child.pid}/status').read_text()
            ignored = int(next(row.split()[1] for row in status.splitlines()
                               if row.startswith('SigIgn:')), 16)
            self.assertTrue(ignored & (1 << (signal.SIGPIPE - 1)))
            print('resource-readback=' + json.dumps(observed, sort_keys=True), flush=True)
            vector = restore_vector()
            for start in range(0, len(vector), 97):
                child.stdin.write(vector[start:start + 97])
                child.stdin.flush()
            with self.assertRaises(subprocess.TimeoutExpired):
                child.wait(timeout=0.1)
            output, error, status = process.exchange(child, b'', 5)
            self.assertEqual((status, output, error), (0, response(1, 7), b''))
        finally:
            process.stop_and_reap(child)
            process.close_pipes(child)

    def test_wrong_missing_symlink_and_fifo_executables(self):
        with self.assertRaises(process.ProbeRefusal):
            process.run(PROBE, '0' * 64, restore_vector(), 1)
        with tempfile.TemporaryDirectory() as folder:
            absent, link = Path(folder) / 'absent', Path(folder) / 'link'
            with self.assertRaises(FileNotFoundError):
                process.run(absent, self.identity, restore_vector(), 1)
            link.symlink_to(PROBE)
            with self.assertRaises(OSError):
                process.run(link, self.identity, restore_vector(), 1)
            fifo = Path(folder) / 'fifo'
            os.mkfifo(fifo)
            with self.assertRaises(process.ProbeRefusal):
                process.run(fifo, self.identity, restore_vector(), 1)

    def test_executable_observed_change_during_hashing_refuses(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'changing'
            path.write_bytes(b'executable fixture')
            path.chmod(0o700)
            expected, actual_read = sha(path), os.read

            def read_and_change(descriptor, count):
                block = actual_read(descriptor, count)
                if block:
                    path.write_bytes(b'changed')
                return block

            with mock.patch.object(process.os, 'read', side_effect=read_and_change):
                with self.assertRaisesRegex(process.ProbeRefusal, 'changed during hashing'):
                    process.pin_executable(path, expected)

    def fake(self, body, *, seconds=1):
        # No authority or live effects. The same child limits precede interpreter exec.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fake'
            path.write_text('#!/usr/bin/python3 -I\nimport os, signal, time\n'
                            'for _ in range(32769):\n'
                            '    if not os.read(0, 32768):\n'
                            '        break\n' + body + '\n')
            path.chmod(0o700)
            return process.run(path, sha(path), restore_vector(), 1, seconds=seconds)

    def test_malformed_extra_stderr_and_exit_mismatch_refuse(self):
        bodies = ('pass', "os.write(1, b'x' * 64)",
                  f'os.write(1, {response(1, 7)!r}); os.write(2, b"diagnostic")',
                  f'os.write(1, {response(1, 7)!r}); raise SystemExit(65)',
                  f'os.write(1, {response(2, 9)!r})',
                  f'os.write(1, {response(0, 1)!r})',
                  'os.write(1, b"x" * 65536)', 'os.write(2, b"x" * 65536)')
        for body in bodies:
            with self.subTest(body=body), self.assertRaises(process.ProbeRefusal):
                self.fake(body)

    def test_death_and_deadline_are_not_results_and_are_reaped(self):
        spawn = subprocess.Popen
        children = []

        def retain_child(*args, **kwargs):
            child = spawn(*args, **kwargs)
            children.append(child)
            return child

        for body in ('os.kill(os.getpid(), signal.SIGKILL)', 'time.sleep(10)',
                     f'os.write(1, {response(1, 7)!r}); time.sleep(10)'):
            with self.subTest(body=body):
                with mock.patch.object(process.subprocess, 'Popen', side_effect=retain_child):
                    with self.assertRaises(process.ProbeRefusal):
                        self.fake(body, seconds=0.2)
                child = children[-1]
                self.assertIsNotNone(child.returncode)
                with self.assertRaises(ChildProcessError):
                    os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG)

    def test_cleanup_attempts_group_termination_after_leader_exit(self):
        child = mock.Mock(pid=12345, returncode=None)
        with mock.patch.object(process.os, 'killpg') as terminate:
            process.stop_and_reap(child)
        terminate.assert_called_once_with(12345, signal.SIGKILL)
        child.wait.assert_called_once_with(timeout=1)

    def test_uncertain_reaping_refuses(self):
        child = mock.Mock(pid=12345, returncode=None)
        child.wait.side_effect = subprocess.TimeoutExpired('fixture', 1)
        with mock.patch.object(process.os, 'killpg'):
            with self.assertRaisesRegex(process.ProbeRefusal, 'cleanup outcome uncertain'):
                process.stop_and_reap(child)

    def test_termination_error_still_attempts_reaping(self):
        child = mock.Mock(pid=12345, returncode=None)
        with mock.patch.object(process.os, 'killpg', side_effect=PermissionError('fixture')):
            with self.assertRaisesRegex(process.ProbeRefusal, 'direct child reaped'):
                process.stop_and_reap(child)
        child.wait.assert_called_once_with(timeout=1)

    def test_unprivileged_fork_refuses_with_effective_nproc_limit(self):
        self.assertNotEqual(os.geteuid(), 0, 'qualification requires ordinary UID')
        body = ('try:\n    os.fork()\n'
                'except OSError as error:\n'
                '    if error.errno != 11:\n        raise\n'
                f'    os.write(1, {response(1, 7)!r})\n'
                'else:\n    raise SystemExit(99)')
        self.assertEqual(self.fake(body).code, 7)

class ContinuityEnvelope(unittest.TestCase):
    def test_parent_refuses_an_automatic_or_foreign_child_reaper(self):
        with mock.patch.object(process.signal, 'getsignal',
                               side_effect=(signal.SIG_IGN, signal.SIG_IGN)):
            with self.assertRaisesRegex(process.ProbeRefusal, 'own child reaping'):
                process.run(PROBE, '0' * 64, restore_vector(), 1)

    def test_parent_envelope_controls_cover_all_result_values(self):
        for operation, count in ((1, 7), (2, 9)):
            for code in range(1, count + 1):
                result = process.classify_response(response(operation, code), b'', 0,
                                                   operation, 'request', 'binary')
                self.assertEqual((result.operation, result.code), (operation, code))
                with self.assertRaises(process.ProbeRefusal):
                    process.classify_response(response(operation, code), b'', 65,
                                              operation, 'request', 'binary')
        for operation, code in ((1, 0), (1, 8), (2, 0), (2, 10), (3, 1)):
            with self.assertRaises(process.ProbeRefusal):
                process.classify_response(response(operation, code), b'', 0,
                                          operation, 'request', 'binary')

    def test_parent_rejects_out_of_budget_inputs(self):
        for payload, operation, seconds in ((b'', 1, 1), (restore_vector(), 3, 1),
                                             (restore_vector(), 1, 6),
                                             (restore_vector(), 1, float('nan'))):
            with self.assertRaises(process.ProbeRefusal):
                process.run(PROBE, '0' * 64, payload, operation, seconds=seconds)


if __name__ == '__main__':
    unittest.main()
