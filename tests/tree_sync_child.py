"""One real regular-member substitution before the unchanged native open."""
import hashlib
import json
import os
from pathlib import Path
import resource
import stat
import sys


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def execute(arguments):
    require(len(arguments) >= 6 and os.geteuid() != 0, 'ordinary-user fixed child arguments')
    program, expected, directory, case, *operation = arguments
    require(case in ('plain', 'regular', 'fifo', 'symlink', 'directory', 'missing', 'generation-fifo'), 'case')
    root = Path(directory)
    require(root.resolve(strict=True) == root and root.parent == Path('/dev/shm'), 'private fixture path')
    info = root.lstat()
    require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, 'private fixture owner/mode')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_AS, (268435456, 268435456))
    resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
    with open(program, 'rb') as source:
        raw = source.read(32769)
    require(len(raw) <= 32768 and hashlib.sha256(raw).hexdigest() == expected, 'complete source identity')
    state = {'armed': case != 'plain'}
    def hook(descriptor, name, observed, synchronize):
        if not state['armed'] or (not synchronize and case != 'generation-fifo'):
            return
        state['armed'] = False
        substitute(root, case, descriptor, name, observed, synchronize)
        # No fake open, sleep or errno: return directly into original os.open.
    sys.argv = ['owned-tree-cas-control', *operation]
    exec(compile(raw, program, 'exec'), {'_admission_hook': hook})


def substitute(root, case, descriptor, name, observed, synchronize):
    require(name == 'value' and stat.S_ISREG(observed.st_mode), 'regular member window')
    opened = os.fstat(descriptor)
    stage = (root / 'stage').lstat()
    require((opened.st_dev, opened.st_ino) == (stage.st_dev, stage.st_ino), 'exact staged directory')
    require(synchronize is (case != 'generation-fifo'), 'expected synchronization path')
    retained = root / 'retained-original'
    if case != 'regular':
        os.rename(name, retained, src_dir_fd=descriptor)
        if case in ('fifo', 'generation-fifo'):
            os.mkfifo(name, 0o600, dir_fd=descriptor)
        elif case == 'symlink':
            os.symlink('../retained-original', name, dir_fd=descriptor)
        elif case == 'directory':
            os.mkdir(name, 0o700, dir_fd=descriptor)
        else:
            require(case == 'missing', 'unknown substitution')
        info = retained.lstat()
        require((info.st_dev, info.st_ino) == (observed.st_dev, observed.st_ino), 'retained original inode')
    record = {'case': case, 'observed_inode': observed.st_ino,
              'observed_device': observed.st_dev, 'synchronize': synchronize}
    raw = (json.dumps(record, sort_keys=True) + '\n').encode('ascii')
    require(len(raw) <= 1024, 'window evidence bound')
    with (root / 'window.json').open('xb') as output:
        require(output.write(raw) == len(raw), 'window evidence write')


if __name__ == '__main__':
    execute(sys.argv[1:])
