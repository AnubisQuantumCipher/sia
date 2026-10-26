"""Structural controls only; synthetic receipts are never proof evidence."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

REPO = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    'acceptance_manifest', REPO / 'scripts/assurance_acceptance_manifest.py')
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class ManifestControls(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in CHECK.INPUTS:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPO / name).read_bytes())
        for directory in ('src', 'tests'):
            (self.root / 'spark' / directory).mkdir(parents=True)
        self.put('spark/sia_assurance.gpr', b'for Source_Dirs use ("src", "tests");')
        self.put('spark/restrictions.adc', b'-- synthetic, not compiled\n')
        self.put('spark/src/policy.ads', b'-- synthetic policy unit\n')
        self.put('spark/tests/harness.adb', b'-- synthetic harness unit\n')
        self.fixture = self.put('fixture.txt', b'synthetic result, not real acceptance\n')
        with CHECK.Checkout(self.root) as root:
            self.manifest = CHECK.draft(root)

    def put(self, name, raw):
        (self.root / name).write_bytes(raw)
        return {'path': name, 'sha256': CHECK.digest(raw)}

    def audit(self):
        with CHECK.Checkout(self.root) as root:
            return CHECK.audit(root, self.manifest)

    def seal(self):
        self.manifest['plan_seal'] = self.put('plan.json', CHECK.canonical(self.manifest['plan']))
        for record in self.manifest['evidence']:
            record['plan_sha256'] = self.manifest['plan_seal']['sha256']

    def make_case(self, identity, scope, role, kinds):
        plan = self.manifest['plan']
        units = plan['proof_inventory']['units'] if 'proof-report' in kinds else []
        return {'id': identity, 'obligations': [], 'role': role, 'scope': scope,
                'source': plan['candidate']['revision'],
                'configuration': plan['candidate']['configuration'],
                'toolchain': plan['candidate']['toolchain'], 'workload': 'synthetic',
                'fault_cut': 'synthetic control', 'argv': ['never-executed'], 'cwd': '.',
                'environment': {}, 'wall_class': 'runtime', 'wall_seconds': 30,
                'resource_plan': self.fixture, 'oracle': self.fixture,
                'expected_exit': 0 if role == 'positive' else 1,
                'expected_result': 'SUCCESS' if role == 'positive' else 'REFUSAL',
                'required_evidence': sorted(kinds), 'required_units': units,
                'proof_scope': 'full-project' if units else 'none'}

    def make_record(self, case, kind):
        review = None
        if kind in ('source-review', 'correspondence-review'):
            review = {'model': 'gpt-6.1-sol', 'source': case['source'],
                      'configuration': case['configuration'], 'scope': case['scope'],
                      'case_ids': [case['id']]}
        execution = kind not in ('source-review', 'correspondence-review')
        return {'case': case['id'], 'kind': kind, 'artifact': self.fixture,
                'plan_sha256': None, 'source': case['source'],
                'configuration': case['configuration'], 'toolchain': case['toolchain'],
                'scope': case['scope'], 'producer': kind, 'run_id': case['id'] + ':' + kind,
                'exit': case['expected_exit'] if execution else 0,
                'result_class': case['expected_result'] if execution else 'SUCCESS',
                'reported_units': case['required_units'] if kind == 'proof-report' else [],
                'review': review}

    def populate_cases(self):
        plan, grouped = self.manifest['plan'], {}
        for row in plan['obligations']:
            row['dependency_basis'] = 'synthetic independent criterion, not real adequacy'
            for requirement in row['required_coverage']:
                key = (requirement['scope'], requirement['role'])
                group = grouped.setdefault(key, {'kinds': set(), 'rows': []})
                group['kinds'].update(requirement['kinds'])
                group['rows'].append(row)
        for (scope, role), group in grouped.items():
            case = self.make_case(scope + ':' + role, scope, role, group['kinds'])
            case['obligations'] = sorted({row['id'] for row in group['rows']})
            for row in group['rows']:
                row['case_ids'].append(case['id'])
            plan['cases'].append(case)
            self.manifest['evidence'].extend(
                self.make_record(case, kind) for kind in case['required_evidence'])

    def populated(self):
        candidate = self.manifest['plan']['candidate']
        candidate.update({'revision': 'a' * 40, 'configuration': 'b' * 64,
                          'toolchain': 'c' * 64, 'platform': 'synthetic', 'harness': 'synthetic',
                          'threat_model': self.fixture, 'fault_model': self.fixture,
                          'assumption_ledger': self.fixture})
        self.populate_cases()
        scope = self.put('scope.json', CHECK.canonical({
            'files': {'spark/src/policy.ads': CHECK.digest(
                (self.root / 'spark/src/policy.ads').read_bytes())},
            'runtime_assumptions': ['Synthetic scope only, not real completeness']}))
        for row in self.manifest['plan']['power_of_ten']:
            row['source_scope'] = scope
            row['controls'] = [{'id': 'synthetic', 'adaptation': 'Synthetic check only',
                                'assessment': 'TESTED', 'violations': [],
                                'limitations': ['No actual compliance established'],
                                'case_ids': ['documentation:positive'], 'deviation': None}]
        self.seal()

    def case(self, scope='installed', role='positive'):
        return next(case for case in self.manifest['plan']['cases']
                    if (case['scope'], case['role']) == (scope, role))

    def test_draft_preserves_every_obligation_and_open_power_rule(self):
        result = self.audit()
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['authority'], 'NONE')
        self.assertEqual([row['id'] for row in self.manifest['plan']['obligations']], list(CHECK.IDS))
        self.assertEqual(len(self.manifest['plan']['power_of_ten']), 70)
        self.assertTrue(any('P10/runtime-third-party' in gap for gap in result['gaps']))

    def test_synthetic_complete_metadata_is_only_structurally_valid(self):
        self.populated()
        CHECK.decode(CHECK.canonical(self.manifest))
        result = self.audit()
        self.assertEqual(result['status'], 'STRUCTURALLY_VALID')
        self.assertEqual(result['authority'], 'NONE')
        self.assertTrue(any('semantic criterion completeness' in limit for limit in result['limits']))

    def test_missing_unknown_reordered_or_weakened_obligation_refuses(self):
        original = copy.deepcopy(self.manifest)
        for mutation in ('missing', 'duplicate', 'unknown', 'scope', 'mandatory'):
            with self.subTest(mutation=mutation):
                self.manifest = copy.deepcopy(original)
                rows = self.manifest['plan']['obligations']
                if mutation == 'missing':
                    rows.pop()
                elif mutation == 'duplicate':
                    rows[-1] = rows[0]
                elif mutation == 'unknown':
                    rows[-1]['id'] = 'P11'
                elif mutation == 'scope':
                    rows[0]['required_coverage'] = []
                else:
                    rows[0]['mandatory'] = False
                with self.assertRaises(CHECK.Refusal):
                    self.audit()

    def test_extra_normative_ids_are_typed_refusals(self):
        for name, prefix, count, columns in CHECK.TABLES:
            with self.subTest(prefix=prefix):
                path = self.root / name
                original = path.read_bytes()
                extra = f'{prefix}{count + 1:02}' if prefix != 'G' else f'G{count + 1}'
                path.write_bytes(original + ('\n| ' + extra + ' | x' * (columns - 1) + ' |\n').encode())
                try:
                    with CHECK.Checkout(self.root) as root:
                        with self.assertRaises(CHECK.Refusal):
                            CHECK.normative_rows(root)
                finally:
                    path.write_bytes(original)

    def test_positive_and_negative_scope_roles_cannot_substitute(self):
        self.populated()
        self.case(role='negative')['required_evidence'].remove('execution')
        self.seal()
        result = self.audit()
        self.assertTrue(any('A04: missing joined installed/negative' in gap for gap in result['gaps']))

    def test_wide_or_noncanonical_numeric_rows_cannot_disappear(self):
        for name, prefix, _count, columns in CHECK.TABLES:
            original = (self.root / name).read_bytes()
            for suffix in ('100', '10', '001', '1bad'):
                for spacing in ('| ', '|', '  |\t'):
                    extra = spacing + prefix + suffix + ' | x' * (columns - 1) + ' |\n'
                    with self.subTest(prefix=prefix, suffix=suffix, spacing=spacing):
                        (self.root / name).write_bytes(original + extra.encode())
                        try:
                            with CHECK.Checkout(self.root) as root:
                                with self.assertRaises(CHECK.Refusal):
                                    CHECK.draft(root)
                        finally:
                            (self.root / name).write_bytes(original)

    def test_wide_or_noncanonical_power_rule_cannot_disappear(self):
        path = self.root / CHECK.POWER_TEN
        original = path.read_bytes()
        for label in ('100 — extra', '11 — extra', '01 — extra', '1bad — extra'):
            for spacing in ('| ', '|', '  |\t'):
                with self.subTest(label=label, spacing=spacing):
                    path.write_bytes(original + (spacing + label + ' | x | x | x |\n').encode())
                    try:
                        with CHECK.Checkout(self.root) as root:
                            with self.assertRaises(CHECK.Refusal):
                                CHECK.draft(root)
                    finally:
                        path.write_bytes(original)

    def test_independent_and_proof_roles_cannot_move_to_negative_case(self):
        self.populated()
        self.case('component')['required_evidence'].remove('independent-execution')
        self.seal()
        result = self.audit()
        self.assertTrue(any('G2: missing joined component/positive' in gap for gap in result['gaps']))

    def test_partial_or_invented_full_project_proof_refuses(self):
        self.populated()
        original = copy.deepcopy(self.manifest)
        for units in (['policy'], ['imaginary']):
            self.manifest = copy.deepcopy(original)
            self.case('component')['required_units'] = units
            self.seal()
            with self.assertRaises(CHECK.Refusal):
                self.audit()

    def test_scoped_proof_cannot_cover_g2_full_project(self):
        self.populated()
        self.case('component')['proof_scope'] = 'scoped'
        self.case('component')['required_units'] = ['policy']
        for record in self.manifest['evidence']:
            if record['case'] == 'component:positive' and record['kind'] == 'proof-report':
                record['reported_units'] = ['policy']
        self.seal()
        self.assertTrue(any('G2: missing joined' in gap for gap in self.audit()['gaps']))

    def test_changed_proof_source_or_project_inventory_refuses(self):
        (self.root / 'spark/src/policy.ads').write_bytes(b'changed')
        with self.assertRaises(CHECK.Refusal):
            self.audit()

    def test_900_second_cap_and_stale_identity_refuse(self):
        self.populated()
        original = copy.deepcopy(self.manifest)
        for mutation in ('cap', 'case-source', 'record-tool', 'record-scope'):
            with self.subTest(mutation=mutation):
                self.manifest = copy.deepcopy(original)
                if mutation == 'cap':
                    self.manifest['plan']['limits']['full_proof_wall_seconds'] = 900
                elif mutation == 'case-source':
                    self.case()['source'] = 'd' * 40
                else:
                    self.manifest['evidence'][0]['toolchain' if mutation == 'record-tool' else 'scope'] = 'wrong'
                self.seal()
                with self.assertRaises(CHECK.Refusal):
                    self.audit()

    def test_failed_positive_and_wrong_negative_outcome_refuse(self):
        self.populated()
        for role in ('positive', 'negative'):
            record = next(row for row in self.manifest['evidence']
                          if row['case'] == 'installed:' + role and row['kind'] == 'execution')
            prior = record['exit']
            record['exit'] = 124
            with self.assertRaises(CHECK.Refusal):
                self.audit()
            record['exit'] = prior

    def test_review_metadata_cannot_replace_reproduction(self):
        self.populated()
        self.manifest['evidence'] = [row for row in self.manifest['evidence']
                                     if row['kind'] != 'independent-execution']
        self.assertTrue(any('missing independent-execution' in gap for gap in self.audit()['gaps']))

    def test_review_requires_actual_model_and_exact_case_scope(self):
        self.populated()
        record = next(row for row in self.manifest['evidence'] if row['kind'] == 'source-review')
        original = copy.deepcopy(record['review'])
        for field, value in (('model', 'gpt-6-luna'), ('scope', 'wrong'), ('case_ids', [])):
            record['review'] = {**original, field: value}
            with self.assertRaises(CHECK.Refusal):
                self.audit()

    def test_same_producer_or_run_is_not_independent(self):
        self.populated()
        first = next(row for row in self.manifest['evidence']
                     if row['case'] == 'installed:positive' and row['kind'] == 'execution')
        second = next(row for row in self.manifest['evidence']
                      if row['case'] == first['case'] and row['kind'] == 'independent-execution')
        second['producer'] = first['producer']
        with self.assertRaises(CHECK.Refusal):
            self.audit()

    def test_negative_review_timeout_or_adverse_result_cannot_count(self):
        self.populated()
        record = next(row for row in self.manifest['evidence']
                      if row['case'] == 'installed:negative' and row['kind'] == 'source-review')
        for code, result in ((124, 'REFUSAL'), (1, 'COUNTEREXAMPLE')):
            record['exit'], record['result_class'] = code, result
            with self.assertRaises(CHECK.Refusal):
                self.audit()

    def test_failed_negative_proof_cannot_support_proved_control(self):
        self.populated()
        case = self.case('component', 'negative')
        case['proof_scope'] = 'full-project'
        case['required_units'] = self.manifest['plan']['proof_inventory']['units']
        case['required_evidence'].append('proof-report')
        case['obligations'].append('P01')
        row = next(row for row in self.manifest['plan']['obligations'] if row['id'] == 'P01')
        row['case_ids'].append(case['id'])
        self.manifest['evidence'].append(self.make_record(case, 'proof-report'))
        control = self.manifest['plan']['power_of_ten'][0]['controls'][0]
        control['assessment'] = 'PROVED'
        control['case_ids'] = [case['id']]
        self.manifest['plan']['power_of_ten'][0]['source_scope'] = self.put(
            'negative-proof-scope.json', CHECK.canonical({
                'files': {'spark/src/policy.ads': self.manifest['plan']['proof_inventory']['sources']['spark/src/policy.ads']},
                'runtime_assumptions': []}))
        self.seal()
        with self.assertRaisesRegex(CHECK.Refusal, 'successful source-bound proof case'):
            self.audit()

    def test_proved_scope_requires_exact_paths_not_matching_stems(self):
        self.populated()
        case = self.case('component')
        case['obligations'].append('P01')
        row = next(row for row in self.manifest['plan']['obligations'] if row['id'] == 'P01')
        row['case_ids'].append(case['id'])
        entry = self.manifest['plan']['power_of_ten'][0]
        entry['controls'][0]['assessment'] = 'PROVED'
        entry['controls'][0]['case_ids'] = [case['id']]
        files = {'spark/src/policy.ads': self.manifest['plan']['proof_inventory']['sources']['spark/src/policy.ads']}
        entry['source_scope'] = self.put('pure-scope.json', CHECK.canonical({
            'files': files, 'runtime_assumptions': []}))
        self.seal()
        self.assertEqual(self.audit()['status'], 'STRUCTURALLY_VALID')
        (self.root / 'spark/src/other').mkdir()
        other = self.put('spark/src/other/policy.ads', b'-- other same-name source\n')
        entry['source_scope'] = self.put('wrong-scope.json', CHECK.canonical({
            'files': {other['path']: other['sha256']}, 'runtime_assumptions': []}))
        self.seal()
        with self.assertRaises(CHECK.Refusal):
            self.audit()

    def test_unsealed_changed_plan_or_cycles_do_not_pass(self):
        self.populated()
        self.manifest['plan']['candidate']['harness'] = 'changed after freeze'
        with self.assertRaises(CHECK.Refusal):
            self.audit()
        rows = self.manifest['plan']['obligations']
        rows[0]['dependencies'] = [rows[1]['id']]
        rows[1]['dependencies'] = [rows[0]['id']]
        self.seal()
        with self.assertRaises(CHECK.Refusal):
            self.audit()

    def test_power_rules_cannot_omit_category_or_hide_violations(self):
        self.populated()
        original = copy.deepcopy(self.manifest)
        self.manifest['plan']['power_of_ten'].pop()
        self.seal()
        with self.assertRaises(CHECK.Refusal):
            self.audit()
        self.manifest = original
        control = self.manifest['plan']['power_of_ten'][-1]['controls'][0]
        control['assessment'] = 'FAILED'
        control['violations'] = ['Dynamic allocation remains']
        self.seal()
        self.assertTrue(any('unresolved assessment/violations' in gap for gap in self.audit()['gaps']))
        control['deviation'] = {'approval': 'model summary says approved'}
        self.seal()
        with self.assertRaises(CHECK.Refusal):
            self.audit()

    def test_referenced_commands_and_source_are_never_executed(self):
        self.populated()
        marker = self.root / 'must-not-exist'
        self.case()['argv'] = [sys.executable, '-c', f'open({str(marker)!r}, "w").close()']
        self.put('fixture.txt', b'raise RuntimeError("do not import")\n')
        self.fixture['sha256'] = CHECK.digest((self.root / 'fixture.txt').read_bytes())
        self.seal()
        with mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('execution')):
            self.audit()
        self.assertFalse(marker.exists())

    def test_json_duplicates_depth_nodes_numbers_and_utf8_refuse(self):
        malformed = (b'{"a":1,"a":2}', b'NaN', b'1.25', b'\xff', b'[' * 17 + b']' * 17,
                     b'"' + b'x' * (CHECK.MAX_STRING + 1) + b'"', b'1' * 50)
        for raw in malformed:
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                CHECK.decode(raw)
        with mock.patch.object(CHECK, 'MAX_NODES', 1), self.assertRaises(CHECK.Refusal):
            CHECK.decode(b'[1]')

    def test_paths_symlink_ancestors_fifo_and_budgets_refuse(self):
        (self.root / 'link').symlink_to(self.root / 'spark', target_is_directory=True)
        (self.root / 'loop').symlink_to(self.root / 'loop')
        os.mkfifo(self.root / 'fifo')
        with CHECK.Checkout(self.root) as root:
            for name in ('../fixture.txt', '/fixture.txt', 'a//b', 'link/src/policy.ads',
                         'loop/file', 'fifo', 'spark/src/../src/policy.ads'):
                with self.subTest(name=name), self.assertRaises((OSError, CHECK.Refusal)):
                    root.read(name)
            root.remaining = 1
            with self.assertRaises(CHECK.Refusal):
                root.read('fixture.txt')
            root.reads = CHECK.MAX_READS
            with self.assertRaises(CHECK.Refusal):
                root.read('fixture.txt')

    def test_parent_replacement_cannot_redirect_open_to_symlink(self):
        real_open = os.open
        moved = self.root / 'spark-saved'
        def replace(path, flags, *args, **kwargs):
            if path == 'spark' and 'dir_fd' in kwargs and not moved.exists():
                (self.root / 'spark').rename(moved)
                (self.root / 'spark').symlink_to(moved, target_is_directory=True)
            return real_open(path, flags, *args, **kwargs)
        os_shim = SimpleNamespace(**vars(os))
        os_shim.open = replace
        with CHECK.Checkout(self.root) as root, mock.patch.object(CHECK, 'os', os_shim):
            self.assertIs(os.open, real_open)
            with self.assertRaises(OSError):
                root.read('spark/src/policy.ads')
        self.assertTrue(moved.is_dir())
        self.assertTrue((self.root / 'spark').is_symlink())

    def test_cli_refusal_has_no_traceback_or_authority(self):
        manifest = self.root / 'bad.json'
        manifest.write_bytes(b'{"duplicate":0,"duplicate":1}')
        result = subprocess.run([sys.executable, '-B', str(REPO / 'scripts/assurance_acceptance_manifest.py'),
                                 'audit', '--root', str(self.root), '--manifest', str(manifest)],
                                capture_output=True, timeout=5, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['status'], 'REFUSED')
        self.assertEqual(result.stderr, b'')


if __name__ == '__main__':
    unittest.main()
