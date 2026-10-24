"""Source-bound isolated regression execution; no installed state writes."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
WORK = Path('/home/sicarii/Work/sia-note-boundary-checkpoint-20261024')
AUDIT = Path('/home/sicarii/Documents/sia-repository-audit-20261024')
FILES = ('bin/siajournalcapture.py', 'bin/sialib.py', 'bin/siasenses.py', 'bin/siaeventplan.py', 'tests/test_journal_capture_ownership.py', 'tests/test_journal_capture_context.py', 'tests/test_sia.py')


def source_pins():
    return {name: hashlib.sha256((WORK / name).read_bytes()).hexdigest()
            for name in FILES}


def command_for(names):
    command = json.loads((AUDIT / 'workspace-event-test-receipt.json').read_text())['command']
    command[command.index(str(AUDIT / 'thought-recovery-source'))] = str(WORK)
    position = command.index('--tmpfs')
    command[position:position] = [
        '--ro-bind', str(AUDIT / 'git-review-executable'), '/usr/bin/git']
    command[-1] = (
        'import sys,unittest; sys.path.insert(0,"/tmp/sia-review-source/bin"); '
        'from tests import sia_test_home; '
        'suite=unittest.defaultTestLoader.loadTestsFromNames(' + repr(names) + '); '
        'result=unittest.TextTestRunner(verbosity=2).run(suite); '
        'raise SystemExit(0 if result.wasSuccessful() else 1)')
    return command


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('baseline-final',):
        raise ValueError('expected a declared test phase')
    phase = sys.argv[1]
    if (ROOT / (phase + '-journal-capture-ownership.json')).exists():
        raise FileExistsError('preserve the existing test receipt')
    names = ['tests.test_journal_capture_ownership', 'tests.test_journal_capture_context']
    command = command_for(names)
    before = source_pins()
    record = {'phase': phase, 'command': command, 'source_before': before,
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'scope': 'Actual journal capture owners and private files, injected post-open metadata faults, normal/replacement/persistent failure controls; original synthetic producer tests. No host journal, source ACK, installed capture or physical fault qualification.'}
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=70, check=False)
        raw, code = result.stdout, result.returncode
    except subprocess.TimeoutExpired as error:
        raw, code = error.stdout or b'', 124
    record.update(returncode=code, source_after=source_pins(),
                  status='PASS' if code == 0 else 'TIMEOUT' if code == 124 else 'FAILED',
                  output_sha256=hashlib.sha256(raw).hexdigest())
    footer = re.search(rb'Ran (\d+) tests? in ([0-9.]+)s', raw)
    if footer:
        record.update(tests_reported=int(footer[1]), elapsed_seconds=float(footer[2]))
    record['source_unchanged'] = before == record['source_after']
    (ROOT / (phase + '-journal-capture-ownership.log')).write_bytes(raw)
    (ROOT / (phase + '-journal-capture-ownership.json')).write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
    if not record['source_unchanged']:
        raise RuntimeError('source changed during execution')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
