#!/usr/bin/env python3
"""Compile-only GNAT controls; no RTS, stack, proof or release authority.

Run under the documented outer deadline and OS resource limits. Compiler and
workspace are trusted inputs. Intentional invalid fixtures are never linked
or executed. Python, the compiler and its subprocesses are not proved here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

LIMIT = 16384
RESTRICTIONS = (
    'No_Anonymous_Allocators', 'No_Coextensions',
    'No_Access_Parameter_Allocators', 'Immediate_Reclamation',
    'No_Task_Allocators', 'No_Allocators', 'No_Implicit_Heap_Allocations',
    'No_Unchecked_Deallocation', 'No_Recursion', 'No_Dispatch',
    'No_Access_Subprograms')
CASES = (('anonymous_allocator', 'No_Anonymous_Allocators', 2),
         ('coextension', 'No_Coextensions', 3),
         ('parameter_allocator', 'No_Access_Parameter_Allocators', 9),
         ('task_allocator', 'No_Task_Allocators', 11))
FLAGS = ('-c', '-gnat2022', '-gnatwae', '-gnatVa', '-gnata', '-gnatf', '-gnatw.o')
WARNING = 'warning: use of an anonymous access type allocator [-gnatw_a]'


def bounded_read(path):
    with path.open('rb') as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('control input/output byte limit')
    return raw


def policy(raw):
    """Closed configuration grammar, not a general Ada semantic analyzer."""
    if len(raw) > LIMIT:
        raise ValueError('configuration byte limit')
    expected = [f'pragma Restrictions ({name});' for name in RESTRICTIONS]
    expected.append('pragma Assertion_Policy (Check);')
    lines = [line.strip() for line in raw.decode('ascii').splitlines()]
    if lines != expected:
        raise ValueError('allocation configuration differs from reviewed policy')


def diagnostics(code, stdout, stderr, unit, restriction, line, variant):
    """Only the declared allocator warning is expected in invalid fixtures."""
    if len(stdout) > LIMIT or len(stderr) > LIMIT or stdout:
        return False
    if variant == 'positive' or (variant == 'baseline' and unit == 'task_allocator'):
        return code == 0 and not stderr
    if code != 1:
        return False
    prefix = re.escape(f'{unit}.adb:{line}:') + r'[0-9]+: '
    warning = prefix + re.escape(WARNING)
    violation = prefix + re.escape('error: violation of restriction "' + restriction)
    violation += r'" at [^\r\n]+/restricted\.adc:1'
    lines = stderr.decode('utf-8', errors='strict').splitlines()
    expected = [warning] if variant == 'baseline' else [violation]
    if variant == 'negative' and unit != 'task_allocator':
        expected.append(warning)
    return len(lines) == len(expected) and all(
        re.fullmatch(pattern, actual, re.IGNORECASE) is not None
        for pattern, actual in zip(expected, lines, strict=True))


def execute(compiler, directory, source, config):
    command = ['/usr/bin/timeout', '--kill-after=5s', '5s', str(compiler),
               *FLAGS, '-gnatec=' + str(config), str(source)]
    environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}
    with (directory / 'stdout').open('xb') as out, (directory / 'stderr').open('xb') as err:
        result = subprocess.run(command, cwd=directory, env=environment,
                                stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                check=False)
    stdout, stderr = bounded_read(directory / 'stdout'), bounded_read(directory / 'stderr')
    return result.returncode, stdout, stderr, command


def control(compiler, fixtures, work, case, variant):
    unit, restriction, line = case
    directory = work / (unit + '-' + variant)
    directory.mkdir()
    name = 'restriction_control' if variant == 'positive' else unit
    raw = bounded_read(fixtures / (name + '.adb'))
    source = directory / (name + '.adb')
    source.write_bytes(raw)
    config = directory / ('baseline.adc' if variant == 'baseline' else 'restricted.adc')
    text = '' if variant == 'baseline' else f'pragma Restrictions ({restriction});\n'
    config.write_text(text + 'pragma Assertion_Policy (Check);\n', encoding='ascii')
    code, stdout, stderr, command = execute(compiler, directory, source, config)
    return {'unit': unit, 'variant': variant, 'command': command, 'exit': code,
            'source_sha256': hashlib.sha256(raw).hexdigest(),
            'config_sha256': hashlib.sha256(bounded_read(config)).hexdigest(),
            'expected': diagnostics(code, stdout, stderr, unit, restriction, line, variant)}


def run(compiler, spark, output):
    """A closed finite roster; the outer 60-second budget covers all cases."""
    raw = bounded_read(spark / 'restrictions.adc')
    policy(raw)
    output.mkdir()  # Refuse stale results and existing output directories.
    fixtures = spark / 'allocation-controls'
    directory = output / 'shared-positive'
    directory.mkdir()
    source = directory / 'restriction_control.adb'
    source.write_bytes(bounded_read(fixtures / source.name))
    config = directory / 'shared.adc'
    config.write_bytes(raw)
    code, stdout, stderr, command = execute(compiler, directory, source, config)
    rows = [{'unit': 'shared', 'variant': 'positive', 'command': command, 'exit': code,
             'config_sha256': hashlib.sha256(raw).hexdigest(),
             'expected': code == 0 and not stdout and not stderr}]
    for case in CASES:
        for variant in ('positive', 'negative', 'baseline'):
            rows.append(control(compiler, fixtures, output, case, variant))
    (output / 'results.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    if not all(row['expected'] for row in rows):
        raise ValueError('compiler control failed; inspect retained diagnostics')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    if not compiler.is_file() or not os.access(compiler, os.X_OK):
        raise ValueError('compiler must be an executable file')
    run(compiler, Path(__file__).resolve().parent, args.output.resolve())
    print('PASS: compile-only allocation controls; no whole-system assurance claim')


if __name__ == '__main__':
    main()
