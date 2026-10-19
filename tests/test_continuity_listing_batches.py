"""Complete bounded traversal of immutable recovery snapshots."""
import json
import posixpath
import unittest
from unittest import mock
from test_continuity import siabackup


class ListingBatches(unittest.TestCase):
    def fixture(self):
        rows = [{'message_type': 'snapshot', 'id': 'abc123', 'tags': ['sia-capsule']},
                {'message_type': 'node', 'type': 'dir', 'path': '/.capsule-test'},
                {'message_type': 'node', 'type': 'file', 'size': 1,
                 'path': '/.capsule-test/manifest.json'},
                {'message_type': 'node', 'type': 'dir', 'path': '/.capsule-test/payload'}]
        for index in range(130):
            directory = '/.capsule-test/payload/d' + str(index)
            rows.extend([
                {'message_type': 'node', 'type': 'dir', 'path': directory},
                {'message_type': 'node', 'type': 'file', 'size': 2,
                 'path': directory + '/file'}])
        return rows

    def runner(self, rows, calls):
        def run(arguments, **kwargs):
            calls.append(arguments)
            scopes = arguments[3:]
            result = [r for r in rows if r.get('message_type') == 'snapshot'
                      or r.get('path') in scopes
                      or posixpath.dirname(r.get('path', '')) in scopes]
            raw = '\n'.join(map(json.dumps, result))
            self.assertLessEqual(len(raw), 20000)
            self.assertLessEqual(len(scopes), 64)
            return raw
        return run

    def test_tree_larger_than_response_budget_is_fully_checked(self):
        rows = self.fixture()
        self.assertGreater(len('\n'.join(map(json.dumps, rows))), 20000)
        calls = []
        with mock.patch.object(siabackup, '_run_restic', side_effect=self.runner(rows, calls)):
            result = siabackup._preflight_snapshot('abc123')
        self.assertEqual(result, {'entries': len(rows) - 1,
                                 'total_bytes': sum(r.get('size', 0) for r in rows),
                                 'capsule_root': '.capsule-test'})
        queried = [p for args in calls for p in args[3:]]
        self.assertEqual(set(queried), {'/'} | {r['path'] for r in rows if r.get('type') == 'dir'})
        self.assertEqual(len(queried), len(set(queried)))
        self.assertGreater(len(calls), 3)

    def test_aggregate_byte_entry_and_depth_limits_are_preserved(self):
        rows = self.fixture()
        for constant, value, reason in (
                ('MAX_SPOOL_BYTES', sum(r.get('size', 0) for r in rows) - 1, 'byte policy'),
                ('MAX_SPOOL_ENTRIES', len(rows) - 2, 'path policy'),
                ('MAX_SPOOL_DEPTH', 3, 'path policy')):
            with self.subTest(constant=constant), mock.patch.object(
                    siabackup, '_run_restic', side_effect=self.runner(rows, [])), \
                    mock.patch.object(siabackup, constant, value), \
                    self.assertRaisesRegex(ValueError, reason):
                siabackup._preflight_snapshot('abc123')

    def test_incomplete_conflicting_and_out_of_scope_pages_refuse(self):
        header, directory = self.fixture()[:2]
        invalid = [
            [dict(header, id='def456'), directory],
            [dict(header, tags=[]), directory],
            [header, header, directory], [directory], [header],
            [header, dict(directory, type='file', size=1)],
            [header, dict(directory, mode=123)],
            [header, directory, directory],
            [header, directory, {'message_type': 'node', 'type': 'file', 'path': '/outside', 'size': 1}],
            [header, directory, {'message_type': 'node', 'type': 'file', 'path': '/.capsule-test/link', 'struct_type': 'dir'}],
        ]
        for page in invalid:
            with self.subTest(page=page), mock.patch.object(siabackup, '_run_restic', side_effect=[
                    '\n'.join(map(json.dumps, [header, directory])),
                    '\n'.join(map(json.dumps, page))]), self.assertRaises(ValueError):
                siabackup._preflight_snapshot('abc123')

    def test_oversized_page_still_refuses(self):
        with mock.patch.object(siabackup, '_run_restic', side_effect=OverflowError('response limit')), \
                self.assertRaises(OverflowError):
            siabackup._preflight_snapshot('abc123')
