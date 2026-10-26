"""Disposable Linux cgroup controls; never run a workload before bound checks."""
import errno
import json
import os
from pathlib import Path
import sys


def memory_events(directory):
    rows = (directory / 'memory.events.local').read_text().splitlines()
    return {key: int(value) for key, value in (row.split() for row in rows)}


def boundary():
    rows = Path('/proc/self/cgroup').read_text().splitlines()
    if len(rows) != 1 or not rows[0].startswith('0::/'):
        raise RuntimeError('unified cgroup required')
    relative = rows[0][4:]
    if not relative.endswith('.service') or 'sia-assurance-resource-' not in relative:
        raise RuntimeError('unexpected service boundary')
    directory = Path('/sys/fs/cgroup') / relative
    limits = {name: (directory / name).read_text().strip()
              for name in ('memory.max', 'memory.swap.max', 'pids.max', 'memory.oom.group')}
    if limits != {'memory.max': '67108864', 'memory.swap.max': '0', 'pids.max': '8', 'memory.oom.group': '1'}:
        raise RuntimeError('effective cgroup limits differ')
    print(json.dumps({'event': 'bounds-checked', 'pid': os.getpid(), 'cgroup': relative, 'limits': limits,
                      'memory_events': memory_events(directory)}), flush=True)
    return directory


def process_control(directory):
    read_fd, write_fd = os.pipe()
    children = []
    refused = False
    try:
        for _ in range(16):
            try:
                pid = os.fork()
            except OSError as exc:
                if exc.errno != errno.EAGAIN:
                    raise
                refused = True
                break
            if pid == 0:
                os.close(write_fd)
                os.read(read_fd, 1)
                os.close(read_fd)
                os._exit(0)
            children.append(pid)
        if not refused or not children:
            raise RuntimeError('missing process admission refusal or positive child')
        events = (directory / 'pids.events').read_text().split()
        if len(events) != 2 or events[0] != 'max' or int(events[1]) < 1:
            raise RuntimeError('missing kernel process-limit event')
        print(json.dumps({'event': 'process-limit-refused', 'children': len(children),
                          'pids_events': events}), flush=True)
    finally:
        os.close(write_fd)
        os.close(read_fd)
        for pid in children:
            waited, status = os.waitpid(pid, 0)
            if waited != pid or status != 0:
                raise RuntimeError('child cleanup failed')


def allocate_blocks(count):
    if count not in (40, 128):
        raise ValueError('unsupported fixed workload')
    blocks = []
    for _ in range(count):
        block = bytearray(1024 * 1024)
        for offset in range(0, len(block), 4096):
            block[offset] = 1
        blocks.append(block)
    return blocks


def descendant_memory(directory):
    ready_read, ready_write = os.pipe()
    release_read, release_write = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(ready_read)
        os.close(release_write)
        if boundary() != directory:
            raise RuntimeError('child escaped configured cgroup')
        blocks = allocate_blocks(40)
        print(json.dumps({'event': 'child-memory-ready', 'pid': os.getpid(),
                          'blocks': len(blocks),
                          'cgroup': str(directory.relative_to('/sys/fs/cgroup'))}), flush=True)
        if os.write(ready_write, b'R') != 1:
            os._exit(2)
        os.close(ready_write)
        os.read(release_read, 1)
        os.close(release_read)
        os._exit(0)
    os.close(ready_write)
    os.close(release_read)
    try:
        if os.read(ready_read, 1) != b'R':
            raise RuntimeError('child allocation did not complete')
        print(json.dumps({'event': 'parent-memory-start', 'pid': os.getpid(),
                          'child_pid': pid}), flush=True)
        blocks = allocate_blocks(40)
        raise RuntimeError('combined workload completed: ' + str(len(blocks)))
    finally:
        os.close(ready_read)
        os.close(release_write)
        waited, status = os.waitpid(pid, 0)
        if waited != pid or status != 0:
            raise RuntimeError('descendant cleanup failed')


def main():
    if sys.argv[1:] not in (['process'], ['memory'], ['allocation'], ['memory-child'], ['report']):
        raise SystemExit('expected process, memory, allocation, memory-child or report mode')
    directory = boundary()
    if sys.argv[1] == 'process':
        process_control(directory)
    elif sys.argv[1] == 'memory':
        blocks = allocate_blocks(128)
        raise RuntimeError('memory workload completed: ' + str(len(blocks)))
    elif sys.argv[1] == 'allocation':
        blocks = allocate_blocks(40)
        print(json.dumps({'event': 'allocation-completed', 'blocks': len(blocks)}), flush=True)
    elif sys.argv[1] == 'memory-child':
        descendant_memory(directory)
    else:
        print(json.dumps({'event': 'after-workload',
                          'cgroup': str(directory.relative_to('/sys/fs/cgroup')),
                          'memory_events': memory_events(directory)}), flush=True)


if __name__ == '__main__':
    main()
