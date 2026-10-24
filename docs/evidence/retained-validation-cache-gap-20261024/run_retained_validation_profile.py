"""Retain bounded exact-source validation profile; never substitute a gate."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent
WORK = Path('/home/sicarii/Work/sia-assurance-kernel-20261019')


def source_pins():
    paths = sorted([*WORK.joinpath('bin').glob('*.py'), *WORK.joinpath('tests').glob('*.py')])
    if len(paths) > 4096:
        raise ValueError('source inventory capacity')
    return {str(path.relative_to(WORK)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths}


def main():
    output = ROOT / 'retained-validation-profile-receipt.json'
    if output.exists():
        raise FileExistsError('preserve profile evidence')
    script = ROOT / 'profile_retained_validation.py'
    command = json.loads((ROOT / 'baseline-retained-validation-context.json').read_text())['command']
    position = command.index('/home') - 1
    command[position:position] = ['--ro-bind', str(script), '/tmp/validation-profile.py']
    command[-1] = ('import sys,runpy; sys.path.insert(0,"/tmp/sia-review-source/bin"); '
                  'from tests import sia_test_home; '
                  'runpy.run_path("/tmp/validation-profile.py",run_name="__main__")')
    before = source_pins()
    record = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'command': command, 'source_before': before,
              'probe_sha256': hashlib.sha256(script.read_bytes()).hexdigest(),
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=70, check=False)
        raw, code = result.stdout, result.returncode
    except subprocess.TimeoutExpired as error:
        raw, code = error.stdout or b'', 124
    record.update(returncode=code, source_after=source_pins(),
                  status='OBSERVED' if code == 0 else 'TIMEOUT' if code == 124 else 'FAILED',
                  output_sha256=hashlib.sha256(raw).hexdigest())
    record['source_unchanged'] = before == record['source_after']
    (ROOT / 'retained-validation-profile-output.json').write_bytes(raw)
    output.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({key: record[key] for key in ('status', 'returncode', 'source_unchanged')}))
    if not record['source_unchanged']:
        raise RuntimeError('source changed during profile')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
