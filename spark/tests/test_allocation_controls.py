"""Negative controls for the compiler-result gate, not compiler proof."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    'allocation_controls', Path(__file__).parents[1] / 'check-allocation-controls.py')
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class AllocationControls(unittest.TestCase):
    def test_every_required_directive_is_binding(self):
        raw = (Path(__file__).parents[1] / 'restrictions.adc').read_bytes()
        CHECK.policy(raw)
        for line in raw.splitlines(keepends=True):
            with self.subTest(line=line), self.assertRaises(ValueError):
                CHECK.policy(raw.replace(line, b'', 1))
        for suffix in (b'pragma Assertion_Policy (Ignore);\n', raw[:40], b'-- suffix\n'):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                CHECK.policy(raw + suffix)

    def test_configuration_and_log_bounds(self):
        with self.assertRaises(ValueError):
            CHECK.policy(b'x' * (CHECK.LIMIT + 1))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'output'
            path.write_bytes(b'x' * (CHECK.LIMIT + 1))
            with self.assertRaises(ValueError):
                CHECK.bounded_read(path)

    def test_success_cannot_hide_warnings_failures_or_timeout(self):
        args = ('task_allocator', 'No_Task_Allocators', 11, 'positive')
        self.assertTrue(CHECK.diagnostics(0, b'', b'', *args))
        for code in (1, 124, 137, -9):
            self.assertFalse(CHECK.diagnostics(code, b'', b'', *args))
        self.assertFalse(CHECK.diagnostics(0, b'', b'warning', *args))
        self.assertFalse(CHECK.diagnostics(0, b'output', b'', *args))

    def test_named_violation_requires_exact_site_and_no_extra_diagnostic(self):
        args = ('task_allocator', 'No_Task_Allocators', 11, 'negative')
        line = (b'task_allocator.adb:11:40: error: violation of restriction '
                b'"No_Task_Allocators" at /tmp/control/restricted.adc:1\n')
        self.assertTrue(CHECK.diagnostics(1, b'', line, *args))
        for bad in (line.replace(b':11:', b':12:'), line.replace(b'task_', b'other_'),
                    line.replace(b'No_Task', b'No_Other'), b'prefix\n' + line,
                    line + b'unrelated warning\n', b'', line * 2):
            with self.subTest(bad=bad):
                self.assertFalse(CHECK.diagnostics(1, b'', bad, *args))
        for code in (0, 2, 124, 137, -9):
            self.assertFalse(CHECK.diagnostics(code, b'', line, *args))

    def test_allocator_warning_does_not_replace_restriction_diagnostic(self):
        args = ('anonymous_allocator', 'No_Anonymous_Allocators', 2)
        warning = ('anonymous_allocator.adb:2:39: ' + CHECK.WARNING + '\n').encode()
        violation = (b'anonymous_allocator.adb:2:39: error: violation of restriction '
                     b'"No_Anonymous_Allocators" at /tmp/control/restricted.adc:1\n')
        self.assertTrue(CHECK.diagnostics(1, b'', warning, *args, 'baseline'))
        self.assertFalse(CHECK.diagnostics(1, b'', warning, *args, 'negative'))
        self.assertFalse(CHECK.diagnostics(1, b'', violation, *args, 'negative'))
        self.assertTrue(CHECK.diagnostics(1, b'', violation + warning, *args, 'negative'))
        self.assertFalse(CHECK.diagnostics(0, b'', warning, *args, 'baseline'))

    def test_existing_output_is_refused_before_compiler_execution(self):
        spark = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(CHECK, 'execute') as execute:
                with self.assertRaises(FileExistsError):
                    CHECK.run(Path('/unused/compiler'), spark, Path(directory))
                execute.assert_not_called()

    def test_missing_policy_is_refused_before_compiler_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            spark = Path(directory)
            (spark / 'restrictions.adc').write_bytes(b'')
            with mock.patch.object(CHECK, 'execute') as execute:
                with self.assertRaises(ValueError):
                    CHECK.run(Path('/unused/compiler'), spark, spark / 'output')
                execute.assert_not_called()
            self.assertFalse((spark / 'output').exists())


if __name__ == '__main__':
    unittest.main()
