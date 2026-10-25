"""Native forwarding and failure propagation, outside the SPARK proof claim."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ('-std=c11', '-O2', '-g', '-Wall', '-Wextra', '-Wpedantic', '-Werror',
         '-Wconversion', '-Wshadow', '-Wstrict-prototypes', '-Wmissing-prototypes',
         '-Wformat=2', '-Wundef', '-Wcast-align=strict', '-Wwrite-strings',
         '-Wvla', '-fanalyzer', '-fstack-usage')


class StartupGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('gcc')
        if compiler is None:
            raise RuntimeError('GCC is required for native guard controls')
        temporary = tempfile.TemporaryDirectory(prefix='sia-startup-guard-')
        cls.addClassCleanup(temporary.cleanup)
        cls.binary = Path(temporary.name) / 'guard-contract'
        result = subprocess.run(
            ['/usr/bin/prlimit', '--as=2147483648', '--fsize=536870912',
             '--core=0', '--', compiler, *FLAGS,
             str(ROOT / 'transport/native/startup_guard.c'),
             str(ROOT / 'tests/native/startup_guard_contract.c'),
             '-o', str(cls.binary)], cwd=temporary.name,
            capture_output=True, timeout=30, check=False)
        if result.returncode != 0 or result.stdout or result.stderr:
            raise RuntimeError('native guard compilation failed or emitted diagnostics: '
                               + repr((result.returncode, result.stdout, result.stderr)))

    def run_contract(self, mode, expected):
        result = subprocess.run(
            ['/usr/bin/prlimit', '--as=268435456', '--stack=16777216',
             '--cpu=10', '--nofile=16', '--nproc=0', '--fsize=0', '--core=0',
             '--', str(self.binary), mode], capture_output=True, timeout=5,
            check=False)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (expected, b'', b''))

    def test_success_preserves_arguments_results_errno_and_call_count(self):
        self.run_contract('s', 0)

    def test_outside_initialization_preserves_failures(self):
        self.run_contract('x', 0)

    def test_initialization_errors_terminate_without_output(self):
        for mode in ('a', 'b', 'e'):
            with self.subTest(mode=mode):
                self.run_contract(mode, 74)


if __name__ == '__main__':
    unittest.main()
