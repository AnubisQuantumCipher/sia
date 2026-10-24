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


FD_FAULTS = ('source_open_error', 'stage_open_error', 'stage_close_error_reuse',
             'source_close_error', 'both_close_error', 'body_both_close_error',
             'body_error_cleanup_ok', 'fd_zero', 'stage_close_before', 'source_close_before')


def fd_identity(descriptor):
    value = REAL_FSTAT(descriptor)
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid]


class FdHooks(Hooks):
    def __init__(self, source, stage, log, fault):
        super().__init__(source, stage, log, fault)
        self.namespace, self.roles, self.acquired, self.attempts = {}, {}, {}, []
        self.sentinel_fd, self.sentinel_identity = None, None
        self.body_prefix = 0
        self.held_originals, self.held_original_identities = {}, {}
        self.errors = {
            'source_open': OSError('injected source open failure'),
            'stage_open': OSError('injected stage open failure'),
            'body': OSError('injected body write failure'),
            'body_cause': ValueError('original explicit body cause'),
            'stage_close': OSError('injected stage close failure'),
            'source_close': OSError('injected source close failure')}

    def open_descriptor(self, path, flags, *args, **kwargs):
        role = 'source' if str(path) == str(self.source) else 'stage'
        if str(path) not in (str(self.source), str(self.stage)):
            raise AssertionError('unexpected fd-lifetime open path')
        if self.fault == role + '_open_error':
            self.append({'kind':'open_error', 'role':role})
            raise self.errors[role + '_open']
        descriptor = super().open_descriptor(path, flags, *args, **kwargs)
        self.roles[descriptor] = role
        self.acquired[role] = {'fd':descriptor, 'identity':fd_identity(descriptor)}
        self.append({'kind':'open', 'role':role, 'fd':descriptor})
        return descriptor

    def write(self, descriptor, data):
        if self.fault not in ('body_both_close_error', 'body_error_cleanup_ok'):
            return super().write(descriptor, data)
        if descriptor != self.descriptors.get(str(self.stage)):
            raise AssertionError('unexpected body-fault write descriptor')
        if self.body_prefix:
            self.append({'kind':'body_write_error', 'offered':len(data)})
            raise self.errors['body'] from self.errors['body_cause']
        written = REAL_WRITE(descriptor, data[:min(5, len(data))])
        self.body_prefix = written
        self.append({'kind':'write', 'offered':len(data), 'returned':written})
        return written

    def close(self, descriptor):
        role = self.roles.get(descriptor)
        if role is None or len(self.attempts) >= 2:
            raise AssertionError('unexpected or excess close attempt')
        if any(row['role'] == role for row in self.attempts):
            raise AssertionError('retried ambiguous close')
        slot = 'temporary_fd' if role == 'stage' else 'source_fd'
        attempt = {'role':role, 'fd':descriptor,
                   'own_slot_none_before_close':self.namespace[slot] is None,
                   'before_identity':fd_identity(descriptor), 'real_close_completed':False}
        self.attempts.append(attempt)
        before_fault = self.fault == role + '_close_before'
        attempt['injected_before_real_close'] = before_fault
        if before_fault:
            if self.held_originals:
                raise AssertionError('excess held original descriptor')
            self.held_originals[role] = descriptor
            self.held_original_identities[role] = fd_identity(descriptor)
            self.append({'kind':'close_attempt', **attempt})
            raise self.errors[role + '_close']
        result = REAL_CLOSE(descriptor)
        attempt['real_close_completed'] = True
        fail_stage = self.fault in ('stage_close_error_reuse', 'both_close_error',
                                   'body_both_close_error')
        fail_source = self.fault in ('source_close_error', 'both_close_error',
                                    'body_both_close_error')
        if role == 'stage' and fail_stage:
            self.sentinel_fd = REAL_OPEN('/dev/null', os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0))
            self.sentinel_identity = fd_identity(self.sentinel_fd)
            if self.sentinel_fd != descriptor:
                raise AssertionError('native released descriptor number not reused')
            self.append({'kind':'sentinel_held', 'fd':self.sentinel_fd})
        self.append({'kind':'close_attempt', **attempt})
        if (role == 'stage' and fail_stage) or (role == 'source' and fail_source):
            raise self.errors[role + '_close']
        return result


def fd_exception_graph(error, hooks):
    pending, seen, records = ([error] if error is not None else []), set(), []
    labels = {id(value):label for label,value in hooks.errors.items()}
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        if len(seen) >= 8 or id(current) not in labels:
            raise AssertionError('unexpected/unbounded exception graph')
        seen.add(id(current))
        links = {}
        for field in ('__context__', '__cause__'):
            related = getattr(current, field)
            if related is not None and id(related) not in labels:
                raise AssertionError('exception provenance object replaced')
            links[field] = labels.get(id(related))
            if related is not None:
                pending.append(related)
        records.append({'label':labels[id(current)],
                        'exact_injected_object':current is hooks.errors[labels[id(current)]],
                        'type':type(current).__name__, 'message':str(current),
                        'suppress_context':current.__suppress_context__, **links})
    return {'top':labels.get(id(error)), 'nodes':records}


def fd_numeric_state(descriptor):
    try:
        return {'open':True, 'identity':fd_identity(descriptor)}
    except OSError as error:
        if error.errno != errno.EBADF:
            raise
        return {'open':False, 'errno':errno.EBADF}


def fd_observations(hooks):
    numeric = {role:fd_numeric_state(row['fd']) for role,row in hooks.acquired.items()}
    sentinel = None
    if hooks.sentinel_fd is not None:
        sentinel = {'fd':hooks.sentinel_fd,
            'reuses_released_stage_number':hooks.sentinel_fd == hooks.acquired['stage']['fd'],
            'open_after_source_cleanup':fd_identity(hooks.sentinel_fd) == hooks.sentinel_identity,
            'dev_null_read_eof':os.read(hooks.sentinel_fd, 1) == b'',
            'different_from_original_stage_identity':hooks.sentinel_identity != hooks.acquired['stage']['identity']}
    return {'acquired':hooks.acquired, 'close_attempts':hooks.attempts,
            'numeric_fd_state_after_cleanup':numeric, 'sentinel':sentinel,
            'held_originals':hooks.held_originals,
            'slots_none_before_exit':{name:hooks.namespace.get(name) is None
                                      for name in ('source_fd', 'temporary_fd')}}


def fd_execute(raw, hooks, arguments):
    with mock.patch.object(sys, 'argv', arguments), \
            mock.patch.object(os, 'open', hooks.open_descriptor), \
            mock.patch.object(os, 'write', hooks.write), \
            mock.patch.object(os, 'fchmod', hooks.fchmod), \
            mock.patch.object(os, 'fsync', hooks.fsync), \
            mock.patch.object(os, 'close', hooks.close):
        try:
            exec(compile(raw, 'install.sh:atomic_install_file', 'exec'), hooks.namespace)
        except (OSError, RuntimeError) as error:
            return error
    return None


def fd_report(raw, hooks, original, failure):
    observations = fd_observations(hooks)
    current = read_bounded(hooks.source)
    stage = read_bounded(hooks.stage)
    return {'program_sha256':hashlib.sha256(raw).hexdigest(),
        'source_preserved':identity(hooks.source) == original['identity'] and current == hooks.expected,
        'source_sha256':original['sha256'], 'stage_sha256':hashlib.sha256(stage).hexdigest(),
        'stage_hex':stage.hex(), 'stage_bytes':len(stage),
        'stage_mode':stat.S_IMODE(hooks.stage.stat().st_mode),
        'body_prefix':hooks.body_prefix, 'failure_graph':fd_exception_graph(failure, hooks),
        'events':hooks.events, **observations}


def fd_main():
    program, source, stage, mode, fault, log = sys.argv[1:]
    source, stage, log = Path(source), Path(stage), Path(log)
    hooks = FdHooks(source, stage, log, fault)
    original = {'identity':identity(source), 'sha256':hashlib.sha256(hooks.expected).hexdigest()}
    with Path(program).open('rb') as stream:
        raw = stream.read(16385)
    if len(raw) > 16384 or fault not in FD_FAULTS:
        raise ValueError('fd-lifetime program/fault admission')
    hooks.namespace = {'__name__':'__main__'}
    if fault == 'fd_zero':
        REAL_FSTAT(0)
        REAL_CLOSE(0)
    try:
        failure = fd_execute(raw, hooks, ['atomic_install_file', str(source), str(stage), mode])
        report = fd_report(raw, hooks, original, failure)
        if fault == 'fd_zero':
            report['source_zero_EBADF_after_report_reads'] = closed(0)
        report['held_originals_open_after_report_reads'] = {
            role:fd_identity(descriptor) == hooks.held_original_identities[role]
            for role,descriptor in hooks.held_originals.items()}
    finally:
        if hooks.sentinel_fd is not None:
            REAL_CLOSE(hooks.sentinel_fd)
        for descriptor in hooks.held_originals.values():
            REAL_CLOSE(descriptor)
    report['fixture_held_original_closed_after_snapshot'] = {
        role:closed(descriptor) for role,descriptor in hooks.held_originals.items()}
    if hooks.sentinel_fd is not None:
        report['fixture_sentinel_closed_after_snapshot'] = closed(hooks.sentinel_fd)
    print(json.dumps(report, sort_keys=True))
    return 0 if failure is None else 1


if __name__ == '__main__':
    if len(sys.argv) == 7 and sys.argv[5] in FD_FAULTS:
        raise SystemExit(fd_main())
    raise SystemExit(main())
