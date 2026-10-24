"""Package retained SDK source and terminal evidence; never execute members."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

DIRECTORIES = ('sdk-fixtures-constant-clock-v1', 'sdk-scratch-profile-v1',
               'sdk-scratch-sweep-v1', 'sdk-scratch-sweep-v2',
               'sdk-frontier-profile-v2', 'sdk-scratch-sweep-v3',
               'sdk-scratch-sweep-v3/preexecution-static-failure',
               'sdk-scratch-sweep-v4')
RUNNERS = ('run_sdk_sweep.py', 'run_sdk_frontier_profile.py', 'run_sdk_cell_v3.py',
           'run_sdk_fixture_v4.py')


def collect(root):
    paths = [root / name for name in RUNNERS]
    for name in DIRECTORIES:
        iterator = (root / name).iterdir()
        for _ in range(513):
            path = next(iterator, None)
            if path is None:
                break
            if len(paths) == 512:
                raise ValueError('snapshot path capacity')
            paths.append(path)
    entries, total = [], 0
    for path in sorted(paths):
        if path.is_symlink():
            raise ValueError('snapshot symlink refused')
        if path.is_dir():
            if str(path.relative_to(root)) not in DIRECTORIES:
                raise ValueError('unexpected snapshot subdirectory')
            continue
        size = path.stat().st_size
        if size > 16 * 1024 * 1024 or total + size > 32 * 1024 * 1024:
            raise ValueError('snapshot byte capacity')
        data = path.read_bytes()
        if len(data) != size:
            raise ValueError('snapshot source changed while reading')
        total += size
        entries.append((str(path.relative_to(root)), data))
    return entries


def archive(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w', format=tarfile.USTAR_FORMAT) as bundle:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o444
            bundle.addfile(info, io.BytesIO(data))
    return gzip.compress(output.getvalue(), mtime=0)


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ('write', 'check'):
        raise ValueError('expected write|check SOURCE_DIRECTORY OUTPUT_DIRECTORY')
    mode, source, output = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    for name in ('sdk-scratch-sweep-v1/full-result.json',
                 'sdk-scratch-sweep-v3/full-result.json',
                 'sdk-frontier-profile-v2/result.json'):
        value = json.loads((source / name).read_text())
        if type(value.get('exit')) is not int or value.get('source_unchanged') is not True:
            raise ValueError('terminal unchanged-source receipt missing')
    entries = collect(source)
    payload = archive(entries)
    if payload != archive(entries) or entries != collect(source):
        raise ValueError('snapshot reproduction or source stability failure')
    manifest = {'schema': 'sia.sdk-fixture-evidence-snapshot.v1',
                'scope': 'Forensic source/evidence snapshot, not an executable acceptance bundle.',
                'archive_sha256': hashlib.sha256(payload).hexdigest(),
                'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                          for name, data in entries}}
    products = {'snapshot.tar.gz': payload,
                'inventory.json': (json.dumps(manifest, indent=2) + '\n').encode()}
    output.mkdir(exist_ok=True, parents=True)
    for name, data in products.items():
        path = output / name
        if mode == 'check':
            if path.read_bytes() != data:
                raise ValueError('snapshot differs: ' + name)
        else:
            with path.open('xb') as stream:
                if stream.write(data) != len(data):
                    raise OSError('short snapshot write')
    print(json.dumps({'mode': mode, 'files': len(entries),
                      'archive_bytes': len(payload), 'archive_sha256': manifest['archive_sha256']}))


if __name__ == '__main__':
    main()
