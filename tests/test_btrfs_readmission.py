"""Btrfs reboot readmission: opt-in authority and real receipt publication."""
import contextlib
import copy
import io
import json
import os
import stat
import struct
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home
from tests.test_cli import sia
import siacontrollerdeliveryepoch as epochs


class BtrfsReadmission(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.home = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.corpus = os.path.join(self.home, 'corpus')
        self.state = os.path.join(self.home, 'state')
        self.managed = os.path.join(self.state, 'managed-install')
        os.mkdir(self.corpus, 0o700)
        os.makedirs(self.managed, mode=0o700)
        for key, value in {'CORPUS': self.corpus, 'STATE': self.state}.items():
            self.stack.enter_context(mock.patch.object(sia.sialib, key, value))
        self.stack.enter_context(mock.patch.object(sia.sialib, 'load_memo', return_value={}))
        self.epoch = {'status': 'absent'}
        self.stack.enter_context(mock.patch.object(epochs, 'readmit_epoch',
                                                   side_effect=lambda *a, **k: copy.deepcopy(self.epoch)))
        self.root = sia._corpus_root_identity()
        self.write_receipt(self.root)
        self.stack.enter_context(mock.patch.object(sia.fcntl, 'ioctl', side_effect=self.ioctl))

    def ioctl(self, fd, request, buffer, mutate=True):
        if request == 2214630431:
            buffer[16:32] = b'f' * 16
        elif request == 2180551740:
            struct.pack_into('=Q', buffer, 0, 257)
            buffer[296:312] = b's' * 16
        else:
            self.fail('unexpected ioctl')
        return 0

    def write_receipt(self, root):
        self.receipt = os.path.join(self.managed, 'corpus')
        with open(self.receipt, 'w') as stream:
            stream.write('managed-by=khephri.sia\nkind=corpus-v2\npath=' + self.corpus + '\nroot=' + root + '\n')
        os.chmod(self.receipt, 0o600)

    def read_receipt(self):
        with open(self.receipt) as stream:
            return stream.read()

    def enroll(self):
        self.assertEqual(sia._btrfs_readmit(enroll=True)['status'], 'enrolled')

    def drift_device(self):
        self.write_receipt('999999:' + self.root.split(':', 1)[1])

    def test_absent_enrollment_never_observes_or_mutates(self):
        self.drift_device()
        before = self.read_receipt()
        with mock.patch.object(sia, '_btrfs_binding', side_effect=AssertionError):
            self.assertEqual(sia._btrfs_readmit(enroll=False)['status'], 'disabled')
        self.assertEqual(self.read_receipt(), before)

    def test_enrollment_requires_bound_receipts_and_explicit_yes(self):
        self.drift_device()
        with self.assertRaisesRegex(ValueError, 'before enrollment'):
            sia._btrfs_readmit(enroll=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sia.cmd_readmit(['--enroll-btrfs']), 2)
        self.assertFalse(os.path.exists(sia._btrfs_enrollment_path()))

    def test_device_change_refreshes_receipt_retains_audit_and_is_idempotent(self):
        self.enroll()
        self.drift_device()
        result = sia._btrfs_readmit(enroll=False)
        self.assertEqual(result['status'], 'readmitted')
        self.assertIn('root=' + self.root + '\n', self.read_receipt())
        with open(result['audit']) as stream:
            event = json.load(stream)
        self.assertEqual(event['phase'], 'completed')
        self.assertEqual(event['corpus_receipt']['previous_root'].split(':')[0], '999999')
        self.assertEqual(stat.S_IMODE(os.stat(result['audit']).st_mode), 0o600)
        self.assertIn('sha256', event)
        self.assertIn('non_claims', event)
        entries = sorted(os.listdir(self.managed))
        self.assertEqual(sia._btrfs_readmit(enroll=False)['status'], 'bound')
        self.assertEqual(sorted(os.listdir(self.managed)), entries)

    def test_changed_filesystem_subvolume_inode_owner_mode_or_path_refuses(self):
        self.enroll()
        self.drift_device()
        before = self.read_receipt()
        original = sia._btrfs_directory_identity(self.corpus)
        for field, value in {'fsid': 'a'*32, 'subvolume_id': 256,
                             'subvolume_uuid': 'b'*32, 'inode': 42,
                             'mode': 0o40755, 'uid': 42, 'gid': 42,
                             'path': '/different'}.items():
            with self.subTest(field=field), mock.patch.object(
                    sia, '_btrfs_directory_identity', return_value={**original, field: value}):
                with self.assertRaisesRegex(ValueError, 'durable identity changed'):
                    sia._btrfs_readmit(enroll=False)
                self.assertEqual(self.read_receipt(), before)

    def test_receipt_inode_change_is_not_reinterpreted_as_device_change(self):
        self.enroll()
        self.write_receipt('999999:42:' + ':'.join(self.root.split(':')[2:]))
        before = self.read_receipt()
        with self.assertRaisesRegex(ValueError, 'beyond its device'):
            sia._btrfs_readmit(enroll=False)
        self.assertEqual(self.read_receipt(), before)

    def test_ioctl_failure_never_falls_back_to_stat(self):
        self.enroll()
        self.drift_device()
        before = self.read_receipt()
        with mock.patch.object(sia.fcntl, 'ioctl', side_effect=OSError('unsupported')):
            with self.assertRaises(OSError):
                sia._btrfs_readmit(enroll=False)
        self.assertEqual(self.read_receipt(), before)

    def test_changed_enrollment_seal_refuses(self):
        self.enroll()
        self.drift_device()
        path = sia._btrfs_enrollment_path()
        with open(path) as stream:
            value = json.load(stream)
        value['binding']['corpus']['inode'] = 42
        with open(path, 'w') as stream:
            json.dump(value, stream)
        with self.assertRaisesRegex(ValueError, 'seal mismatch'):
            sia._btrfs_readmit(enroll=False)

    def test_symlinked_corpus_is_refused(self):
        original = self.corpus + '-original'
        os.rename(self.corpus, original)
        os.symlink(original, self.corpus)
        with self.assertRaises(OSError):
            sia._btrfs_directory_identity(self.corpus)

    def test_ready_surfaces_receipt_mismatch_with_healthy_memory(self):
        self.drift_device()
        with mock.patch.object(sia.sialib, 'corpus_owner', contextlib.nullcontext), \
                mock.patch.object(sia.sialib, 'memory_readiness', return_value=(True, '')), \
                mock.patch.object(sia, '_print_pulse_failure'), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(sia.cmd_ready(), 1)
        self.assertIn('corpus-receipt-root-mismatch', out.getvalue())

    def test_binding_change_at_publication_keeps_receipt_and_intent(self):
        self.enroll()
        self.drift_device()
        before = self.read_receipt()
        real = sia._btrfs_binding
        initial = real(self.epoch)
        changed = copy.deepcopy(initial)
        changed['corpus']['subvolume_uuid'] = 'b' * 32
        with mock.patch.object(sia, '_btrfs_binding', side_effect=[initial, changed]):
            with self.assertRaisesRegex(ValueError, 'authority changed'):
                sia._btrfs_readmit(enroll=False)
        self.assertEqual(self.read_receipt(), before)
        events = [name for name in os.listdir(self.managed)
                  if name.startswith('btrfs-readmission-')]
        self.assertTrue(events)
        with open(os.path.join(self.managed, events[0])) as stream:
            self.assertEqual(json.load(stream)['phase'], 'intent')

    def test_epoch_failure_after_corpus_refresh_preserves_audit_and_allows_retry(self):
        self.enroll()
        self.drift_device()
        with mock.patch.object(epochs, 'readmit_epoch',
                               side_effect=[{'status': 'absent'}, RuntimeError('interrupted')]):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                sia._btrfs_readmit(enroll=False)
        self.assertIn('root=' + self.root + '\n', self.read_receipt())
        events = [name for name in os.listdir(self.managed)
                  if name.startswith('btrfs-readmission-')]
        with open(os.path.join(self.managed, events[0])) as stream:
            self.assertEqual(json.load(stream)['phase'], 'intent')
        self.assertEqual(sia._btrfs_readmit(enroll=False)['status'], 'bound')

    def test_later_epoch_adoption_requires_explicit_enrollment(self):
        self.enroll()
        self.drift_device()
        self.epoch = {'status': 'bound', 'adoption_sha256': 'a' * 64,
                      'records_directory': self.corpus,
                      'effective_identity': {'dev': 1, 'ino': 2},
                      'observed_identity': {'dev': 1, 'ino': 2}}
        before = self.read_receipt()
        with self.assertRaisesRegex(ValueError, 'durable identity changed'):
            sia._btrfs_readmit(enroll=False)
        self.assertEqual(self.read_receipt(), before)

    def test_busy_runtime_retry_preserves_enrollment_intent(self):
        with mock.patch.object(sia.sialib, 'brainstem_owner',
                               side_effect=sia.sialib.OwnerBusy('owned')), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(sia.cmd_readmit(['--enroll-btrfs', '--yes']), 1)
        self.assertIn('sia readmit --enroll-btrfs --yes &&', out.getvalue())
        self.assertFalse(os.path.exists(sia._btrfs_enrollment_path()))

    def test_service_orders_opt_in_check_before_daemon(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / 'systemd/sia-brainstem.service').read_text()
        self.assertIn('sia-cli readmit --btrfs-boot', text)
        self.assertLess(text.index('ExecStartPre='), text.index('ExecStart='))


if __name__ == '__main__':
    unittest.main()
