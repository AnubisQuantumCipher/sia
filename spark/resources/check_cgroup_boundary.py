"""Exercise transient user-service resource enforcement in disposable units."""
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import uuid


def manager(arguments, **kwargs):
    env = dict(os.environ, XDG_RUNTIME_DIR='/run/user/' + str(os.getuid()))
    return subprocess.run(arguments, env=env, timeout=45, **kwargs)


def properties(unit):
    result = manager(['/usr/bin/systemctl', '--user', 'show', unit,
                      '-p', 'LoadState', '-p', 'ActiveState', '-p', 'ControlGroup', '-p', 'Result', '-p', 'ExecMainCode', '-p', 'ExecMainStatus',
                      '-p', 'MemoryMax', '-p', 'MemorySwapMax', '-p', 'TasksMax',
                      '-p', 'MemoryPeak'], capture_output=True, text=True, check=True)
    return dict(row.split('=', 1) for row in result.stdout.splitlines())


def cleanup(output, mode, unit):
    attempts = {}
    for operation in ('stop', 'reset-failed'):
        try:
            result = manager(['/usr/bin/systemctl', '--user', operation, unit],
                             capture_output=True, text=True, check=False)
            attempts[operation] = {'exit': result.returncode, 'stderr': result.stderr}
        except subprocess.TimeoutExpired:
            attempts[operation] = {'error': 'timeout'}
    try:
        observed = properties(unit)
        attempts['after'] = observed
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        attempts['verification_error'] = type(exc).__name__
        raise
    finally:
        (output / (mode + '.cleanup.json')).write_text(json.dumps(attempts, indent=2) + '\n')
    if observed['LoadState'] == 'not-found':
        return
    if observed['ActiveState'] != 'inactive' or observed['ControlGroup'] \
            or any(attempts[name].get('exit') != 0 for name in ('stop', 'reset-failed')):
        raise RuntimeError('disposable unit cleanup unresolved')


def run_case(output, mode, probe):
    unit = 'sia-assurance-resource-' + uuid.uuid4().hex + '.service'
    command = ['/usr/bin/systemd-run', '--user', '--wait', '--pipe', '--unit=' + unit,
               '-p', 'MemoryMax=64M', '-p', 'MemorySwapMax=0', '-p', 'TasksMax=8',
               '-p', 'OOMPolicy=kill',
               '-p', 'RuntimeMaxSec=30s', '-p', 'TimeoutStopSec=5s',
               '-p', 'ExecStopPost=/usr/bin/python3 -B ' + str(probe) + ' report',
               '/usr/bin/python3', '-B', str(probe), mode]
    (output / (mode + '.command.json')).write_text(json.dumps(command) + '\n')
    try:
        with (output / (mode + '.log')).open('wb') as log:
            result = manager(command, stdout=log, stderr=subprocess.STDOUT, check=False)
        (output / (mode + '.exit')).write_text(str(result.returncode) + '\n')
        observed = properties(unit)
        (output / (mode + '.properties.json')).write_text(json.dumps(observed, indent=2) + '\n')
        with (output / (mode + '.log')).open('rb') as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise RuntimeError('unexpected output volume')
        rows = [json.loads(line) for line in raw.decode().splitlines() if line.startswith('{')]
        if not rows or rows[0].get('event') != 'bounds-checked':
            raise RuntimeError('workload did not verify effective limits')
        after = [row for row in rows if row.get('event') == 'after-workload']
        if len(after) != 1 or after[0].get('cgroup') != rows[0].get('cgroup'):
            raise RuntimeError('missing post-workload kernel counters')
        if mode == 'process':
            if result.returncode != 0 or rows[1].get('event') != 'process-limit-refused':
                raise RuntimeError('process limit control failed')
        elif observed['LoadState'] != 'loaded' or result.returncode == 0 \
                or observed['MemoryMax'] != '67108864' or observed['MemorySwapMax'] != '0' \
                or observed['TasksMax'] != '8' or observed['Result'] != 'oom-kill' \
                or observed['ExecMainCode'] != '2' or observed['ExecMainStatus'] != '9':
            raise RuntimeError('expected kernel OOM kill not observed')
        if mode == 'memory' and any(after[0]['memory_events'][key] <=
                rows[0]['memory_events'][key] for key in ('max', 'oom', 'oom_kill')):
            raise RuntimeError('missing cgroup-local OOM attribution')
        return {'manager': observed if observed['LoadState'] != 'not-found'
                else {'LoadState': 'not-found'}, 'probe': rows}
    finally:
        cleanup(output, mode, unit)


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: check_cgroup_boundary.py NEW_EVIDENCE_DIR')
    output = Path(sys.argv[1]).resolve()
    output.mkdir(mode=0o700)
    probe = Path(__file__).with_name('cgroup_probe.py').resolve(strict=True)
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(probe)):
        raise RuntimeError('probe path not supported by fixture unit syntax')
    reports = {mode: run_case(output, mode, probe) for mode in ('process', 'memory')}
    report = {'status': 'TESTED', 'controls': reports,
              'scope': 'transient user-service memory/process containment; no production authority or disk budget'}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
