#!/usr/bin/env python3
"""Bounded traceability checks, never an acceptance or action authority.

No argv is executed and no referenced source is imported. Hash/metadata matches
do not authenticate a producer, prove an oracle or establish system assurance.
CPython/JSON allocation and file custody remain outside the SPARK boundary.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

MAX_BYTES = 1024 * 1024
MAX_DEPTH = 16
MAX_NODES = 10000
MAX_ITEMS = 256
MAX_STRING = 4096
MAX_TOTAL_BYTES = 16 * MAX_BYTES
MAX_READS = 1024
TABLES = (('docs/ASSURANCE-GOAL.md', 'A', 24, 4),
          ('docs/ASSURANCE-IMPLEMENTATION-GATES.md', 'G', 6, 3),
          ('docs/AGENT-CONTINUITY.md', 'C', 14, 3))
POWER_TEN = 'docs/POWER-OF-TEN-ASSESSMENT.md'
INPUTS = tuple(row[0] for row in TABLES) + (
    'docs/ASSURANCE-COMPLETION-CONTRACT-20261021-V2.txt', POWER_TEN)
IDS = tuple(f'{prefix}{number:02}' if prefix != 'G' else f'G{number}'
            for _, prefix, count, _ in TABLES for number in range(1, count + 1)) + tuple(
                f'P{number:02}' for number in range(1, 11))
LIMITS = {'prover_jobs': 1, 'prover_memlimit_mib': 512, 'per_check_seconds': 10,
          'build_wall_seconds': 120, 'runtime_wall_seconds': 30,
          'focused_proof_wall_seconds': 120, 'full_proof_wall_seconds': 600,
          'recall_wall_seconds': 240}
SCOPES = {'component', 'model', 'installed', 'harness', 'off-host', 'release', 'documentation'}
KINDS = {'execution', 'independent-execution', 'source-review', 'correspondence-review',
         'proof-report', 'model-report'}
RESULTS = {'SUCCESS', 'REFUSAL', 'COUNTEREXAMPLE'}
DOMAINS = {
    'A01': ('documentation',), 'A02': ('component', 'installed'),
    'A03': ('component', 'model', 'installed'), 'A04': ('component', 'installed'),
    'A05': ('component', 'model', 'installed', 'off-host'), 'A06': ('component', 'installed'),
    'A07': ('component', 'installed'), 'A08': ('installed',),
    'A09': ('installed',), 'A10': ('off-host',), 'A11': ('component', 'installed'),
    'A12': ('component', 'installed'), 'A13': ('component', 'installed', 'off-host', 'release'),
    'A14': ('documentation', 'installed'), 'A15': ('installed',), 'A16': ('component', 'installed'),
    'A17': ('component', 'installed'), 'A18': ('component', 'installed'),
    'A19': ('installed',), 'A20': ('installed', 'off-host'),
    'A21': ('documentation', 'component', 'installed', 'release'),
    'A22': ('harness', 'installed'), 'A23': ('harness', 'installed'), 'A24': ('installed',),
    'G1': ('documentation',), 'G2': ('component',), 'G3': ('installed',),
    'G4': ('installed',), 'G5': ('installed',), 'G6': ('component', 'installed', 'off-host', 'release'),
    'C01': ('harness', 'installed'), 'C02': ('harness', 'installed'), 'C03': ('harness', 'installed'),
    'C04': ('harness', 'installed'), 'C05': ('harness', 'installed'), 'C06': ('harness', 'installed'),
    'C07': ('harness', 'installed'), 'C08': ('harness', 'installed'),
    'C09': ('harness', 'installed'), 'C10': ('harness', 'installed'),
    'C11': ('component', 'harness', 'installed'), 'C12': ('harness', 'installed'),
    'C13': ('component', 'harness', 'installed'), 'C14': ('harness', 'installed')}
SPECIAL_KINDS = {'A02': ('proof-report', 'independent-execution'),
                 'A03': ('proof-report',), 'A04': ('proof-report',),
                 'A05': ('proof-report',), 'A06': ('proof-report',),
                 'A07': ('proof-report',), 'A08': ('independent-execution',),
                 'A11': ('proof-report',), 'A15': ('independent-execution',),
                 'A16': ('proof-report',), 'A17': ('proof-report',),
                 'A18': ('proof-report',), 'A19': ('independent-execution',),
                 'C11': ('proof-report',), 'C13': ('proof-report',),
                 'G1': ('source-review',),
                 'G2': ('proof-report', 'independent-execution'),
                 'G4': ('independent-execution',), 'G5': ('independent-execution',),
                 'G6': ('proof-report', 'independent-execution', 'source-review'),
                 'A13': ('proof-report', 'independent-execution', 'source-review'),
                 'A21': ('proof-report', 'source-review'), 'A22': ('independent-execution',),
                 'A23': ('independent-execution',)}
# These are minimum metadata joins, not an exhaustive semantic test roster.
# Positive and hostile/fault cases cannot substitute for one another.
NEGATIVE_IDS = set(IDS) - {'A01', 'A14', 'A21'} - {
    f'P{number:02}' for number in range(1, 11)}
P10_CATEGORIES = ('production', 'adapters', 'scripts', 'tests', 'libraries',
                  'experiments', 'runtime-third-party')
ASSESSMENTS = {'OPEN', 'FAILED', 'PROVED', 'TESTED', 'OBSERVED', 'ASSUMED', 'UNPROVEN'}


class Refusal(ValueError):
    """Contradictory/unsupported data; no classification authorizes an action."""


def read_descriptor(descriptor, limit):
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise Refusal('input type or byte budget')
    chunks, size = [], 0
    for _ in range(MAX_BYTES // 4096 + 1):
        chunk = os.read(descriptor, min(4096, limit + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > limit:
            raise Refusal('input exceeded byte budget')
    else:
        raise Refusal('input read iteration budget')
    raw = b''.join(chunks)
    after = os.fstat(descriptor)
    first = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
    last = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    if len(raw) != before.st_size or len(raw) > limit or first != last:
        raise Refusal('input changed or exceeded byte budget')
    return raw


def read_file(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        return read_descriptor(descriptor, MAX_BYTES)
    finally:
        os.close(descriptor)


def path_parts(name):
    if not isinstance(name, str) or len(name) > 1024 or '\x00' in name:
        raise Refusal('artifact path type/budget')
    parts = name.split('/')
    if len(parts) > 16 or any(part in ('', '.', '..') for part in parts) or '\\' in name:
        raise Refusal('noncanonical artifact path')
    return parts


class Checkout:
    """Pin the selected root; never follow a reference's parent symlink.

    Hard links, mount changes and hostile writes to already opened inodes are
    not excluded. Hashes and observed metadata are not authenticated custody.
    """
    def __init__(self, root):
        self.descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.remaining = MAX_TOTAL_BYTES
        self.reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        os.close(self.descriptor)

    def open_parent(self, parts):
        parent = os.dup(self.descriptor)
        try:
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=parent)
                previous, parent = parent, child
                os.close(previous)
            return parent
        except BaseException:
            os.close(parent)
            raise

    def read(self, name):
        if self.reads >= MAX_READS or self.remaining <= 0:
            raise Refusal('aggregate artifact budget')
        parts = path_parts(name)
        parent = self.open_parent(parts)
        descriptor = None
        try:
            descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=parent)
        finally:
            try:
                os.close(parent)
            except BaseException:
                if descriptor is not None:
                    os.close(descriptor)
                raise
        try:
            self.reads += 1
            raw = read_descriptor(descriptor, min(MAX_BYTES, self.remaining))
            self.remaining -= len(raw)
            return raw
        except BaseException:
            self.remaining = 0
            raise
        finally:
            os.close(descriptor)

    def names(self, name):
        parts = path_parts(name + '/placeholder')
        descriptor = self.open_parent(parts)
        try:
            names = []
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    if len(names) >= MAX_ITEMS:
                        raise Refusal('source-directory entry budget')
                    names.append(entry.name)
            return sorted(names)
        finally:
            os.close(descriptor)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def object_fields(pairs):
    result = {}
    if len(pairs) > MAX_ITEMS:
        raise Refusal('JSON object budget')
    for key, value in pairs:
        if key in result:
            raise Refusal('duplicate JSON key')
        result[key] = value
    return result


def reject_number(_):
    raise Refusal('noninteger/nonfinite JSON number')


def depth_check(raw):
    depth, quoted, escaped = 0, False, False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > MAX_DEPTH:
                raise Refusal('JSON nesting budget')
        elif byte in (93, 125):
            depth -= 1
            if depth < 0:
                raise Refusal('JSON nesting mismatch')
    if depth or quoted:
        raise Refusal('incomplete JSON framing')


def node_check(value):
    pending = [value]
    for _ in range(MAX_NODES):
        if not pending:
            return
        item = pending.pop()
        if isinstance(item, (dict, list)):
            if len(item) > MAX_ITEMS:
                raise Refusal('JSON collection budget')
            children = list(item.values()) + list(item) if isinstance(item, dict) else item
            if len(pending) + len(children) > MAX_NODES:
                raise Refusal('JSON work budget')
            pending.extend(children)
        elif isinstance(item, str):
            if len(item) > MAX_STRING:
                raise Refusal('JSON string budget')
        elif type(item) is int and item.bit_length() > 64:
            raise Refusal('JSON integer budget')
    if pending:
        raise Refusal('JSON node budget')


def decode(raw):
    if len(raw) > MAX_BYTES:
        raise Refusal('JSON byte budget')
    depth_check(raw)
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=object_fields,
                       parse_float=reject_number, parse_constant=reject_number)
    node_check(value)
    return value


def keys(value, expected):
    if type(value) is not dict or set(value) != set(expected.split()):
        raise Refusal('missing or unsupported fields')


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_STRING:
        raise Refusal('invalid text field')


def identifiers(values, allowed=None):
    if type(values) is not list or len(values) > MAX_ITEMS:
        raise Refusal('identifier list budget/type')
    for value in values:
        if not isinstance(value, str) or not re.fullmatch('[A-Za-z0-9_.:-]{1,64}', value):
            raise Refusal('identifier syntax')
    if len(set(values)) != len(values) or (allowed is not None and not set(values) <= set(allowed)):
        raise Refusal('duplicate or unknown identifier')


def reference(root, value):
    keys(value, 'path sha256')
    if not isinstance(value['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', value['sha256']):
        raise Refusal('artifact digest syntax')
    raw = root.read(value['path'])
    if digest(raw) != value['sha256']:
        raise Refusal('artifact hash mismatch')
    return raw


def coverage(identity, scopes):
    requirements = []
    for scope in scopes:
        kinds = ['execution', 'source-review', *SPECIAL_KINDS.get(identity, ())]
        kinds = list(dict.fromkeys(kinds))
        if scope != 'component':
            kinds = [kind for kind in kinds if kind != 'proof-report']
        if scope == 'model':
            kinds.append('model-report')
        requirements.append({'scope': scope, 'role': 'positive', 'kinds': kinds})
        if identity in NEGATIVE_IDS:
            negative_kinds = [kind for kind in kinds if kind != 'proof-report']
            requirements.append({'scope': scope, 'role': 'negative',
                                 'kinds': negative_kinds})
    return requirements


def obligation(identity, name, raw, number, line, scopes):
    return {'id': identity, 'document': name, 'document_sha256': digest(raw),
            'line': number, 'normative_row': line, 'mandatory': True,
            'required_coverage': coverage(identity, scopes),
            'case_ids': [], 'dependencies': [], 'dependency_basis': None}


def table_rows(root, name, prefix, count, columns):
    raw, rows, found = root.read(name), [], []
    expected = [f'{prefix}{i:02}' if prefix != 'G' else f'G{i}' for i in range(1, count + 1)]
    for number, line in enumerate(raw.decode('utf-8').splitlines(), 1):
        if not line.lstrip().startswith('|'):
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        identity = cells[0].split(':', 1)[0]
        if not re.match(prefix + '[0-9]', identity):
            continue
        if (not re.fullmatch(prefix + ('[0-9]{2}' if prefix != 'G' else '[0-9]'), identity)
                or len(cells) != columns or identity not in expected):
            raise Refusal('normative table structure/identity changed')
        found.append(identity)
        rows.append(obligation(identity, name, raw, number, line, DOMAINS[identity]))
    if found != expected:
        raise Refusal('normative obligation roster changed')
    return rows


def power_ten_rows(root):
    raw, rows, found = root.read(POWER_TEN), [], []
    for number, line in enumerate(raw.decode('utf-8').splitlines(), 1):
        if not line.lstrip().startswith('|'):
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if not re.match('[0-9]', cells[0]):
            continue
        match = re.match(r'^([1-9]|10) — ', cells[0])
        if match is None or len(cells) != 4:
            raise Refusal('Power of Ten mapping structure changed')
        rule = int(match[1])
        found.append(rule)
        rows.append(obligation(f'P{rule:02}', POWER_TEN, raw, number, line,
                               ('documentation',)))
    if found != list(range(1, 11)):
        raise Refusal('Power of Ten rule roster changed')
    return rows


def normative_rows(root):
    rows = []
    for name, prefix, count, columns in TABLES:
        rows.extend(table_rows(root, name, prefix, count, columns))
    rows.extend(power_ten_rows(root))
    return rows


def proof_inventory(root):
    project = root.read('spark/sia_assurance.gpr')
    declarations = re.findall(r'for\s+Source_Dirs\s+use\s*([^;]+);',
                              project.decode('utf-8'), flags=re.IGNORECASE)
    if len(declarations) != 1 or re.sub(r'\s+', '', declarations[0]) != '("src","tests")':
        raise Refusal('unsupported proof project source layout')
    paths = []
    for directory in ('src', 'tests'):
        for name in root.names('spark/' + directory):
            if name.endswith(('.ads', '.adb')):
                paths.append('spark/' + directory + '/' + name)
    names = [Path(path).name for path in paths]
    if not paths or len(paths) > 128 or len(set(names)) != len(names):
        raise Refusal('proof source inventory budget/duplicates')
    return {'project_sha256': digest(project),
            'restrictions_sha256': digest(root.read('spark/restrictions.adc')),
            'sources': {path: digest(root.read(path)) for path in sorted(paths)},
            'units': sorted({Path(path).stem for path in paths})}


def draft(root):
    return {'schema': 'sia-assurance-traceability/1',
            'plan': {'candidate': {name: None for name in
                     ('revision', 'configuration', 'toolchain', 'platform', 'harness',
                      'threat_model', 'fault_model', 'assumption_ledger')},
                     'inputs': {name: digest(root.read(name)) for name in INPUTS},
                     'proof_inventory': proof_inventory(root),
                     'limits': dict(LIMITS), 'obligations': normative_rows(root),
                     'power_of_ten': [
                         {'rule': f'P{number:02}', 'category': category,
                          'source_scope': None, 'controls': []}
                         for number in range(1, 11) for category in P10_CATEGORIES],
                     'cases': []},
            'plan_seal': None, 'evidence': []}


def graph_check(rows):
    pending = {row['id']: set(row['dependencies']) for row in rows}
    completed = set()
    for _ in range(len(IDS)):
        ready = {identity for identity, dependencies in pending.items() if dependencies <= completed}
        if not ready:
            if pending:
                raise Refusal('cyclic obligation dependencies')
            return
        completed.update(ready)
        for identity in ready:
            del pending[identity]
    if pending:
        raise Refusal('dependency traversal budget')


def check_obligations(root, rows, gaps):
    if (type(rows) is not list or len(rows) != len(IDS)
            or [row.get('id') for row in rows if type(row) is dict] != list(IDS)):
        raise Refusal('missing, reordered, duplicate or unknown obligation')
    expected = normative_rows(root)
    fixed = ('id', 'document', 'document_sha256', 'line', 'normative_row', 'mandatory',
             'required_coverage')
    for row, original in zip(rows, expected, strict=True):
        keys(row, 'id document document_sha256 line normative_row mandatory required_coverage case_ids dependencies dependency_basis')
        if any(row[key] != original[key] for key in fixed) or row['mandatory'] is not True:
            raise Refusal('normative requirement weakened or mismatched')
        identifiers(row['case_ids'])
        identifiers(row['dependencies'], IDS)
        if not row['case_ids']:
            gaps.append(row['id'] + ': mandatory cases absent')
        if row['dependency_basis'] is None:
            gaps.append(row['id'] + ': dependency basis OPEN')
        else:
            text(row['dependency_basis'])
    graph_check(rows)


def check_candidate(root, candidate, gaps):
    keys(candidate, 'revision configuration toolchain platform harness threat_model fault_model assumption_ledger')
    for name, value in candidate.items():
        if value is None:
            gaps.append('candidate.' + name + ': OPEN')
        elif name in ('threat_model', 'fault_model', 'assumption_ledger'):
            reference(root, value)
        elif name in ('revision', 'configuration', 'toolchain'):
            width = 40 if name == 'revision' else 64
            if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{' + str(width) + '}', value):
                raise Refusal('candidate identity syntax')
        else:
            text(value)


def check_case_identity(case, candidate, gaps):
    for field, bound in (('source', 'revision'), ('configuration', 'configuration'), ('toolchain', 'toolchain')):
        if candidate[bound] is None:
            gaps.append(case['id'] + ': candidate identity OPEN')
        elif case[field] != candidate[bound]:
            raise Refusal('stale case identity')


def check_command(case):
    for name in ('workload', 'fault_cut', 'cwd'):
        text(case[name])
    if type(case['argv']) is not list or not 1 <= len(case['argv']) <= 64:
        raise Refusal('argv budget/type')
    for value in case['argv']:
        text(value)
    if type(case['environment']) is not dict or len(case['environment']) > 32:
        raise Refusal('environment budget/type')
    for name, value in case['environment'].items():
        text(name)
        text(value)
    label = str(case['wall_class']) + '_wall_seconds'
    if label not in LIMITS or type(case['wall_seconds']) is not int or case['wall_seconds'] != LIMITS[label]:
        raise Refusal('unapproved/mismatched deadline cap')


def check_case_oracle(root, case, inventory, gaps):
    for name in ('resource_plan', 'oracle'):
        if case[name] is None:
            gaps.append(case['id'] + ': ' + name + ' OPEN')
        else:
            reference(root, case[name])
    identifiers(case['required_evidence'], KINDS)
    identifiers(case['required_units'])
    if 'execution' not in case['required_evidence']:
        gaps.append(case['id'] + ': execution evidence requirement absent')
    scope = case['proof_scope']
    if scope not in ('none', 'scoped', 'full-project'):
        raise Refusal('proof scope syntax')
    if scope == 'none' and (case['required_units'] or 'proof-report' in case['required_evidence']):
        raise Refusal('proof role without declared proof scope')
    if scope != 'none' and ('proof-report' not in case['required_evidence'] or not case['required_units']):
        raise Refusal('proof inventory/role absent')
    if not set(case['required_units']) <= set(inventory['units']):
        raise Refusal('unknown intended proof unit')
    if scope == 'full-project' and set(case['required_units']) != set(inventory['units']):
        raise Refusal('partial full-project proof roster')
    if (type(case['expected_exit']) is not int or not -255 <= case['expected_exit'] <= 255
            or case['expected_result'] not in RESULTS):
        raise Refusal('oracle result/exit syntax')
    if case['role'] == 'positive' and (case['expected_exit'] != 0 or case['expected_result'] != 'SUCCESS'):
        raise Refusal('positive case cannot expect failure')


def check_case(root, case, plan, gaps):
    keys(case, 'id obligations role scope source configuration toolchain workload fault_cut argv cwd environment wall_class wall_seconds resource_plan oracle expected_exit expected_result required_evidence required_units proof_scope')
    identifiers([case['id']])
    identifiers(case['obligations'], IDS)
    if not case['obligations'] or case['role'] not in ('positive', 'negative') or case['scope'] not in SCOPES:
        raise Refusal('case coverage/role/scope')
    check_case_identity(case, plan['candidate'], gaps)
    check_command(case)
    check_case_oracle(root, case, plan['proof_inventory'], gaps)


def check_coverage(row, linked, gaps):
    for required in row['required_coverage']:
        matches = [case for case in linked if case['scope'] == required['scope']
                   and case['role'] == required['role']
                   and set(required['kinds']) <= set(case['required_evidence'])]
        if (row['id'] in ('G2', 'G6', 'A13') and required['scope'] == 'component'
                and required['role'] == 'positive'):
            matches = [case for case in matches if case['proof_scope'] == 'full-project']
        if not matches:
            gaps.append(row['id'] + ': missing joined ' + required['scope'] + '/' +
                        required['role'] + '/' + ','.join(required['kinds']))


def check_cases(root, plan, gaps):
    cases = plan['cases']
    if type(cases) is not list or len(cases) > MAX_ITEMS:
        raise Refusal('case list budget/type')
    identities = [case.get('id') for case in cases if type(case) is dict]
    identifiers(identities)
    if len(identities) != len(cases):
        raise Refusal('case object type')
    for case in cases:
        check_case(root, case, plan, gaps)
    by_id = {case['id']: case for case in cases}
    for row in plan['obligations']:
        identifiers(row['case_ids'], by_id)
        linked = [case for case in cases if row['id'] in case['obligations']]
        if set(row['case_ids']) != {case['id'] for case in linked}:
            raise Refusal('asymmetric case/obligation links')
        check_coverage(row, linked, gaps)
    return by_id


def check_review(record, case):
    review = record['review']
    if record['kind'] in ('source-review', 'correspondence-review'):
        if record['exit'] != 0 or record['result_class'] != 'SUCCESS':
            raise Refusal('review did not complete successfully')
        keys(review, 'model source configuration scope case_ids')
        if review['model'] != 'gpt-6.1-sol':
            raise Refusal('required actual GPT-6.1 review model declaration absent')
        for field in ('source', 'configuration', 'scope'):
            if review[field] != case[field]:
                raise Refusal('review scope identity mismatch')
        identifiers(review['case_ids'])
        if case['id'] not in review['case_ids']:
            raise Refusal('review does not cover case')
    elif review is not None:
        raise Refusal('review metadata on non-review evidence')


def check_record(root, record, case, seal, gaps):
    keys(record, 'case kind artifact plan_sha256 source configuration toolchain scope producer run_id exit result_class reported_units review')
    if record['kind'] not in KINDS:
        raise Refusal('unsupported evidence kind')
    reference(root, record['artifact'])
    for field in ('source', 'configuration', 'toolchain', 'scope'):
        if record[field] != case[field]:
            raise Refusal('stale or mismatched evidence identity/scope')
    if seal is None:
        gaps.append(case['id'] + ': evidence has no frozen plan')
    elif record['plan_sha256'] != seal['sha256']:
        raise Refusal('evidence from another plan')
    text(record['producer'])
    text(record['run_id'])
    if type(record['exit']) is not int or not -255 <= record['exit'] <= 255 or record['result_class'] not in RESULTS:
        raise Refusal('unsupported result/exit')
    if case['role'] == 'positive' and (record['exit'] != 0 or record['result_class'] != 'SUCCESS'):
        raise Refusal('required positive case did not succeed')
    if (record['kind'] in ('execution', 'independent-execution', 'proof-report', 'model-report')
            and (record['exit'] != case['expected_exit'] or record['result_class'] != case['expected_result'])):
        raise Refusal('result differs from frozen expected outcome')
    identifiers(record['reported_units'])
    if record['kind'] == 'proof-report' and set(record['reported_units']) != set(case['required_units']):
        raise Refusal('incomplete or mismatched proof inventory')
    check_review(record, case)


def check_records(root, records, cases, seal, gaps):
    if type(records) is not list or len(records) > MAX_ITEMS:
        raise Refusal('evidence list budget/type')
    observed = {}
    for record in records:
        if type(record) is not dict or record.get('case') not in cases:
            raise Refusal('unknown evidence case')
        case = cases[record['case']]
        check_record(root, record, case, seal, gaps)
        key = (record['case'], record['kind'])
        if key in observed:
            raise Refusal('duplicate evidence role')
        observed[key] = record
    for case in cases.values():
        for kind in case['required_evidence']:
            if (case['id'], kind) not in observed:
                gaps.append(case['id'] + ': missing ' + kind)
        first = observed.get((case['id'], 'execution'))
        second = observed.get((case['id'], 'independent-execution'))
        if first and second and (first['producer'] == second['producer'] or first['run_id'] == second['run_id']):
            raise Refusal('reproduction metadata is not independent')


def text_list(values):
    if type(values) is not list or len(values) > MAX_ITEMS:
        raise Refusal('text list type/budget')
    for value in values:
        text(value)


def check_source_scope(root, value):
    scope = decode(reference(root, value))
    keys(scope, 'files runtime_assumptions')
    if type(scope['files']) is not dict or len(scope['files']) > MAX_ITEMS:
        raise Refusal('source-scope inventory type/budget')
    text_list(scope['runtime_assumptions'])
    if not scope['files'] and not scope['runtime_assumptions']:
        raise Refusal('empty source scope')
    for path, sha256 in scope['files'].items():
        reference(root, {'path': path, 'sha256': sha256})
    return scope


def proved_scope_units(scope, inventory):
    if scope is None or not scope['files'] or scope['runtime_assumptions']:
        raise Refusal('PROVED requires exact intended SPARK source scope')
    for path, sha256 in scope['files'].items():
        if inventory['sources'].get(path) != sha256:
            raise Refusal('PROVED source path/hash outside intended proof inventory')
    return {Path(path).stem for path in scope['files']}


def check_power_control(control, row, cases, scope, inventory, gaps):
    keys(control, 'id adaptation assessment violations limitations case_ids deviation')
    identifiers([control['id']])
    text(control['adaptation'])
    text_list(control['violations'])
    text_list(control['limitations'])
    identifiers(control['case_ids'], cases)
    if control['assessment'] not in ASSESSMENTS:
        raise Refusal('unsupported Power of Ten assessment class')
    label = row['rule'] + '/' + row['category'] + '/' + control['id']
    if control['deviation'] is not None:
        raise Refusal('no deviation acceptance implemented or operator approval authenticated')
    if control['assessment'] not in ('PROVED', 'TESTED') or control['violations']:
        gaps.append(label + ': unresolved assessment/violations')
    if not control['case_ids']:
        gaps.append(label + ': check command/results/evidence OPEN')
    for identity in control['case_ids']:
        case = cases[identity]
        if row['rule'] not in case['obligations']:
            raise Refusal('Power of Ten check is not linked to its rule')
        required = {'execution', 'source-review'}
        if control['assessment'] == 'PROVED':
            required.add('proof-report')
            units = proved_scope_units(scope, inventory)
            if (case['role'] != 'positive' or case['expected_exit'] != 0
                    or case['expected_result'] != 'SUCCESS' or not units
                    or not units <= set(case['required_units'])):
                raise Refusal('PROVED control requires successful source-bound proof case')
        if not required <= set(case['required_evidence']):
            gaps.append(label + ': check lacks required verification roles')


def check_power_ten(root, rows, cases, inventory, gaps):
    expected = [(f'P{number:02}', category) for number in range(1, 11)
                for category in P10_CATEGORIES]
    if type(rows) is not list or len(rows) != len(expected):
        raise Refusal('missing Power of Ten applicability roster')
    for row, pair in zip(rows, expected, strict=True):
        keys(row, 'rule category source_scope controls')
        if (row['rule'], row['category']) != pair:
            raise Refusal('Power of Ten applicability roster changed')
        scope = None
        if row['source_scope'] is None:
            gaps.append('/'.join(pair) + ': exact source scope OPEN')
        else:
            scope = check_source_scope(root, row['source_scope'])
        controls = row['controls']
        if type(controls) is not list or len(controls) > MAX_ITEMS:
            raise Refusal('Power of Ten control list type/budget')
        identities = [control.get('id') for control in controls if type(control) is dict]
        identifiers(identities)
        if len(identities) != len(controls):
            raise Refusal('Power of Ten control object type')
        if not controls:
            gaps.append('/'.join(pair) + ': applicable controls OPEN')
        for control in controls:
            check_power_control(control, row, cases, scope, inventory, gaps)


def audit(root, manifest):
    keys(manifest, 'schema plan plan_seal evidence')
    if manifest['schema'] != 'sia-assurance-traceability/1':
        raise Refusal('unsupported manifest schema')
    plan, gaps = manifest['plan'], []
    keys(plan, 'candidate inputs proof_inventory limits obligations power_of_ten cases')
    if plan['limits'] != LIMITS or any(type(value) is not int for value in plan['limits'].values()):
        raise Refusal('approved diagnostic caps changed')
    expected_inputs = {name: digest(root.read(name)) for name in INPUTS}
    if plan['inputs'] != expected_inputs:
        raise Refusal('normative source identity mismatch')
    if plan['proof_inventory'] != proof_inventory(root):
        raise Refusal('intended proof source roster mismatch')
    check_candidate(root, plan['candidate'], gaps)
    check_obligations(root, plan['obligations'], gaps)
    cases = check_cases(root, plan, gaps)
    seal = manifest['plan_seal']
    if seal is None:
        gaps.append('acceptance plan not frozen')
    else:
        frozen = decode(reference(root, seal))
        if frozen != plan or digest(canonical(plan)) != seal['sha256']:
            raise Refusal('plan changed after frozen snapshot')
    check_records(root, manifest['evidence'], cases, seal, gaps)
    check_power_ten(root, plan['power_of_ten'], cases, plan['proof_inventory'], gaps)
    return {'status': 'INCOMPLETE' if gaps else 'STRUCTURALLY_VALID',
            'gaps': sorted(set(gaps)), 'authority': 'NONE',
            'limits': ['No command execution or authenticated acceptance.',
                       'Metadata cannot establish oracle truth, semantic criterion completeness, chronology or independent identity.',
                       'Source scopes and runtime assumptions require independent completeness and adequacy review.',
                       'Reads are not an atomic authenticated snapshot; hard links and hostile inode/mount changes are outside custody.',
                       'Whole-system assurance, release and installed operation are not established.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('draft', 'audit'))
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    try:
        if args.mode == 'draft':
            if args.manifest is not None:
                raise Refusal('draft writes stdout only')
            with Checkout(args.root) as root:
                result = draft(root)
            sys.stdout.buffer.write(canonical(result))
            return 0
        if args.manifest is None:
            raise Refusal('audit requires a manifest')
        manifest = decode(read_file(args.manifest))
        with Checkout(args.root) as root:
            result = audit(root, manifest)
        sys.stdout.buffer.write(canonical(result))
        return 0 if result['status'] == 'STRUCTURALLY_VALID' else 2
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError, MemoryError) as error:
        print(json.dumps({'status': 'REFUSED', 'authority': 'NONE', 'reason': str(error)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
