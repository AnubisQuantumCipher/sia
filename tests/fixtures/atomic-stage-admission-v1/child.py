"""Observe the actual atomic writer's admission with private real descriptors."""
from pathlib import Path
import errno
import fcntl
import hashlib
import json
import os
import stat
import sys
from unittest import mock

MAX_BYTES = 1_048_576
REAL_OPEN, REAL_CLOSE, REAL_FSTAT = os.open, os.close, os.fstat
REAL_WRITE, REAL_FTRUNCATE = os.write, os.ftruncate
REAL_FCHMOD, REAL_FSYNC = os.fchmod, os.fsync


def fields(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def snapshot(path):
    value = path.lstat()
    result = {'identity': fields(value), 'regular': stat.S_ISREG(value.st_mode)}
    if result['regular']:
        with path.open('rb') as stream:
            data = stream.read(MAX_BYTES + 2)
        if len(data) > MAX_BYTES + 1:
            raise ValueError('fixture byte cap')
        result.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                      small_hex=data.hex() if len(data) <= 64 else None)
    return result


def closed(descriptor):
    try:
        REAL_FSTAT(descriptor)
    except OSError as error:
        if error.errno == errno.EBADF:
            return True
        raise
    return False


class Hooks:
    def __init__(self, source, stage, log, fault):
        self.source, self.stage, self.log, self.fault = source, stage, log, fault
        self.events, self.acquired, self.roles = [], {}, {}
        self.open_attempts, self.close_attempts, self.namespace = 0, [], {}
        self.truncate_error = OSError(errno.EIO, 'injected atomic truncate failure')
        self.native_truncate_error = None

    def append(self, event):
        if len(self.events) >= 64:
            raise ValueError('admission fixture event cap')
        self.events.append(event)
        self.log.write_text(json.dumps({'events': self.events}, sort_keys=True))

    def open(self, path, flags, *args, **kwargs):
        if self.open_attempts >= 2:
            raise AssertionError('unexpected additional target open')
        role = ('source', 'stage')[self.open_attempts]
        expected = self.source if role == 'source' else self.stage
        if str(path) != str(expected):
            raise AssertionError('unexpected target open path')
        self.open_attempts += 1
        actual = flags
        if self.fault == 'readonly_stage' and role == 'stage':
            actual = (flags & ~os.O_ACCMODE) | os.O_RDONLY
        self.append({'kind': 'open_attempt', 'role': role, 'flags': flags,
                     'actual_flags': actual})
        descriptor = REAL_OPEN(path, actual, *args, **kwargs)
        self.roles[descriptor] = role
        row = {'fd': descriptor, 'identity': fields(REAL_FSTAT(descriptor))}
        self.acquired[role] = row
        self.append({'kind': 'open_completed', 'role': role, **row})
        return descriptor

    def fstat(self, descriptor):
        value = REAL_FSTAT(descriptor)
        if descriptor not in self.roles:
            raise AssertionError('unexpected target fstat descriptor')
        self.append({'kind': 'fstat', 'role': self.roles[descriptor],
                     'identity': fields(value)})
        return value

    def ftruncate(self, descriptor, length):
        if self.roles.get(descriptor) != 'stage':
            raise AssertionError('unexpected truncate descriptor')
        self.append({'kind': 'ftruncate_attempt', 'length': length,
                     'source': snapshot(self.source), 'stage': snapshot(self.stage),
                     'fd_identity': fields(REAL_FSTAT(descriptor))})
        if self.fault == 'truncate_error':
            raise self.truncate_error
        try:
            result = REAL_FTRUNCATE(descriptor, length)
        except OSError as error:
            self.native_truncate_error = error
            self.append({'kind': 'ftruncate_native_error', 'fd': descriptor,
                         'errno': error.errno, 'length': length,
                         'access_flags': fcntl.fcntl(descriptor, fcntl.F_GETFL),
                         'identity': fields(REAL_FSTAT(descriptor))})
            raise
        self.append({'kind': 'ftruncate_completed', 'stage': snapshot(self.stage),
                     'fd_identity': fields(REAL_FSTAT(descriptor))})
        return result

    def write(self, descriptor, data):
        if self.roles.get(descriptor) != 'stage':
            raise AssertionError('unexpected write descriptor')
        result = REAL_WRITE(descriptor, data)
        self.append({'kind': 'write', 'offered': len(data), 'written': result})
        return result

    def fchmod(self, descriptor, mode):
        if self.roles.get(descriptor) != 'stage':
            raise AssertionError('unexpected fchmod descriptor')
        self.append({'kind': 'fchmod', 'mode': mode, 'stage': snapshot(self.stage)})
        return REAL_FCHMOD(descriptor, mode)

    def fsync(self, descriptor):
        if self.roles.get(descriptor) != 'stage':
            raise AssertionError('unexpected fsync descriptor')
        self.append({'kind': 'fsync', 'stage': snapshot(self.stage)})
        return REAL_FSYNC(descriptor)

    def close(self, descriptor):
        role = self.roles.get(descriptor)
        if role is None or role in self.close_attempts or len(self.close_attempts) >= 2:
            raise AssertionError('unexpected or repeated target close')
        self.close_attempts.append(role)
        slot = 'source_fd' if role == 'source' else 'temporary_fd'
        before = {'kind': 'close', 'role': role, 'fd': descriptor,
                  'own_slot_none_before_close': self.namespace.get(slot) is None,
                  'identity': fields(REAL_FSTAT(descriptor))}
        result = REAL_CLOSE(descriptor)
        self.append({**before, 'real_close_completed': True})
        return result


def execute(raw, hooks, arguments):
    with mock.patch.object(sys, 'argv', arguments), \
            mock.patch.object(os, 'open', hooks.open), \
            mock.patch.object(os, 'fstat', hooks.fstat), \
            mock.patch.object(os, 'ftruncate', hooks.ftruncate), \
            mock.patch.object(os, 'write', hooks.write), \
            mock.patch.object(os, 'fchmod', hooks.fchmod), \
            mock.patch.object(os, 'fsync', hooks.fsync), \
            mock.patch.object(os, 'close', hooks.close):
        try:
            exec(compile(raw, 'install.sh:atomic_install_file', 'exec'), hooks.namespace)
        except (OSError, RuntimeError) as error:
            return error
    return None


def failure_record(error, hooks):
    if error is None:
        return None
    return {'type': type(error).__name__, 'message': str(error),
            'errno': error.errno if isinstance(error, OSError) else None,
            'exact_injected_truncate_object': error is hooks.truncate_error,
            'exact_native_truncate_object': error is hooks.native_truncate_error,
            'context_none': error.__context__ is None,
            'cause_none': error.__cause__ is None,
            'suppress_context': error.__suppress_context__}


def main():
    program, source, stage, mode, fault, log = sys.argv[1:]
    if fault not in ('normal', 'truncate_error', 'readonly_stage'):
        raise ValueError('admission fixture fault')
    with Path(program).open('rb') as stream:
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise ValueError('admission fixture program cap')
    hooks = Hooks(Path(source), Path(stage), Path(log), fault)
    hooks.namespace = {'__name__': '__main__'}
    failure = execute(raw, hooks, ['atomic_install_file', source, stage, mode])
    closures = {role: closed(row['fd']) for role, row in hooks.acquired.items()}
    report = {'program_sha256': hashlib.sha256(raw).hexdigest(),
              'failure': failure_record(failure, hooks), 'acquired': hooks.acquired,
              'closed_before_child_exit': closures, 'close_attempts': hooks.close_attempts,
              'slots_none_before_exit': {name: hooks.namespace.get(name) is None
                  for name in ('source_fd', 'temporary_fd')},
              'events': hooks.events}
    print(json.dumps(report, sort_keys=True))
    return 0 if failure is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
