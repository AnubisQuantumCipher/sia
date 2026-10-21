"""Execute the exact extracted writer with real files and bounded injected faults."""
from pathlib import Path
import errno
import hashlib
import json
import os
import stat
import sys
from unittest import mock

MAX_BYTES = 1_048_576
REAL_OPEN, REAL_WRITE, REAL_CLOSE = os.open, os.write, os.close
REAL_FCHMOD, REAL_FSYNC, REAL_FSTAT = os.fchmod, os.fsync, os.fstat


def read_bounded(path):
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 2)
    if len(data) > MAX_BYTES + 1:
        raise ValueError('fixture byte cap')
    return data


def identity(path):
    value = path.stat()
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns]


class Hooks:
    def __init__(self, source, stage, log, fault):
        self.source, self.stage, self.log, self.fault = source, stage, log, fault
        self.expected = read_bounded(source)
        self.events, self.descriptors = [], {}
        self.zero_logged = False

    def append(self, event):
        if len(self.events) >= 4096:
            raise ValueError('event cap')
        self.events.append(event)
        self.log.write_text(json.dumps({'events':self.events}, sort_keys=True))

    def open_descriptor(self, path, flags, *args, **kwargs):
        descriptor = REAL_OPEN(path, flags, *args, **kwargs)
        name = str(path)
        if name in (str(self.source), str(self.stage)):
            self.descriptors[name] = descriptor
        return descriptor

    def write(self, descriptor, data):
        if descriptor != self.descriptors.get(str(self.stage)):
            raise AssertionError('unexpected write descriptor')
        if self.fault == 'zero':
            if not self.zero_logged:
                self.zero_logged = True
                self.append({'kind':'write', 'offered':len(data), 'returned':0})
            return 0
        if self.fault == 'overcount':
            written = len(data) + 1
        elif self.fault == 'error' and self.events:
            self.append({'kind':'write_error', 'offered':len(data)})
            raise OSError('injected atomic write failure')
        else:
            take = min(len(data), 7 if self.fault == 'short' else 5 if self.fault == 'error' else len(data))
            written = REAL_WRITE(descriptor, data[:take])
        self.append({'kind':'write', 'offered':len(data), 'returned':written})
        return written

    def snapshot(self, descriptor):
        if descriptor != self.descriptors.get(str(self.stage)):
            raise AssertionError('unexpected snapshot descriptor')
        data = read_bounded(self.stage)
        return {'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest(),
                'exact_original_fixture':data == self.expected,
                'mode':stat.S_IMODE(REAL_FSTAT(descriptor).st_mode)}

    def fchmod(self, descriptor, mode):
        self.append({'kind':'fchmod', 'requested_mode':mode,
                     'immediately_before':self.snapshot(descriptor)})
        return REAL_FCHMOD(descriptor, mode)

    def fsync(self, descriptor):
        self.append({'kind':'fsync', 'immediately_before':self.snapshot(descriptor)})
        return REAL_FSYNC(descriptor)

    def close(self, descriptor):
        result = REAL_CLOSE(descriptor)
        if descriptor in self.descriptors.values():
            self.append({'kind':'close', 'descriptor':descriptor})
        return result


def closed(descriptor):
    try:
        REAL_FSTAT(descriptor)
    except OSError as error:
        return error.errno == errno.EBADF
    return False


def main():
    program, source, stage, mode, fault, log = sys.argv[1:]
    source, stage, log = Path(source), Path(stage), Path(log)
    hooks = Hooks(source, stage, log, fault)
    original = {'identity':identity(source), 'sha256':hashlib.sha256(hooks.expected).hexdigest()}
    with Path(program).open('rb') as stream:
        raw = stream.read(16385)
    if len(raw) > 16384 or fault not in ('normal', 'short', 'zero', 'error', 'overcount'):
        raise ValueError('program/fault admission')
    namespace, failure = {'__name__':'__main__'}, None
    arguments = ['atomic_install_file', str(source), str(stage), mode]
    with mock.patch.object(sys, 'argv', arguments), \
            mock.patch.object(os, 'open', hooks.open_descriptor), \
            mock.patch.object(os, 'write', hooks.write), \
            mock.patch.object(os, 'fchmod', hooks.fchmod), \
            mock.patch.object(os, 'fsync', hooks.fsync), \
            mock.patch.object(os, 'close', hooks.close):
        try:
            exec(compile(raw, 'install.sh:atomic_install_file', 'exec'), namespace)
        except (OSError, RuntimeError) as error:
            failure = {'type':type(error).__name__, 'message':str(error)}
    closures = {name:closed(descriptor) for name,descriptor in hooks.descriptors.items()}
    current = read_bounded(source)
    report = {'program_sha256':hashlib.sha256(raw).hexdigest(), 'failure':failure,
        'source_preserved':identity(source) == original['identity'] and current == hooks.expected,
        'source_sha256':original['sha256'], 'source_bytes':len(hooks.expected),
        'stage_sha256':hashlib.sha256(read_bounded(stage)).hexdigest(),
        'stage_bytes':stage.stat().st_size, 'stage_mode':stat.S_IMODE(stage.stat().st_mode),
        'descriptors':hooks.descriptors, 'closed_before_child_exit':closures,
        'events':hooks.events}
    print(json.dumps(report, sort_keys=True))
    return 0 if failure is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
