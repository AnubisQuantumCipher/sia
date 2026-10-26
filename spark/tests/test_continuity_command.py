"""Descriptor representation controls; no descriptor custody or stack proof."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'continuity_command_contract', ROOT / 'transport/continuity_process.py')
process = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = process
SPEC.loader.exec_module(process)


class HostileDescriptor:
    def __format__(self, spec):
        raise AssertionError('format hook called')

    def __str__(self):
        raise AssertionError('string hook called')

    def __le__(self, other):
        raise AssertionError('comparison hook called')

    def __ge__(self, other):
        raise AssertionError('comparison hook called')


class IntegerSubclass(int):
    def __format__(self, spec):
        raise AssertionError('subclass format hook called')

    def __ge__(self, other):
        raise AssertionError('subclass comparison hook called')


class DescriptorContract(unittest.TestCase):
    def test_supported_endpoints_preserve_complete_command(self):
        prefix = ['/usr/bin/prlimit', '--as=268435456', '--stack=16777216',
                  '--cpu=10', '--nofile=16', '--nproc=0', '--fsize=0',
                  '--core=0', '--']
        for descriptor, suffix in ((0, '0'), (3, '3'), (2147483647, '2147483647')):
            with self.subTest(descriptor=descriptor):
                self.assertEqual(process.command(descriptor),
                                 prefix + ['/proc/self/fd/' + suffix])

    def test_rejects_wrong_types_without_conversion_or_comparison(self):
        cases = (True, False, None, '3', 3.0, HostileDescriptor(), IntegerSubclass(3))
        for index, descriptor in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(process.ProbeRefusal):
                process.command(descriptor)

    def test_rejects_range_before_decimal_formatting(self):
        # Larger than Python's normal decimal-conversion limit; must refuse
        # before any attempt to format, rather than raising that runtime error.
        for index, descriptor in enumerate((-1, 2147483648, 1 << 20000)):
            with self.subTest(index=index), self.assertRaises(process.ProbeRefusal):
                process.command(descriptor)

    def test_unsupported_native_abi_refuses(self):
        with mock.patch.object(process.struct, 'calcsize', return_value=8):
            with self.assertRaisesRegex(process.ProbeRefusal, 'unsupported native'):
                process.command(3)

    def test_invalid_internal_result_never_launches_with_mocked_cleanup(self):
        # Fault injection exercises run -> command -> Popen, with cleanup mocked.
        # A real close(-1) raises OSError; this is not a cleanup qualification.
        with (mock.patch.object(process, 'pin_executable', return_value=-1),
              mock.patch.object(process.signal, 'getsignal',
                                side_effect=[process.signal.SIG_IGN,
                                             process.signal.SIG_DFL]),
              mock.patch.object(process.os, 'close') as close,
              mock.patch.object(process.subprocess, 'Popen') as launch):
            with self.assertRaises(process.ProbeRefusal):
                process.run('unused', '0' * 64, bytes(32768), 1)
            launch.assert_not_called()
            close.assert_called_once_with(-1)


if __name__ == '__main__':
    unittest.main()
