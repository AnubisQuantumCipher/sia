"""Pin-pair traversal refuses roster drift rather than truncating or growing."""
import hashlib
import json
from types import SimpleNamespace
import unittest

import siaeventplan as pages


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def rows(kind):
    key = 'plan_sha256' if kind == 'member' else 'batch_sha256'
    items = []
    for label in ('first', 'second'):
        body = {'label': label}
        if kind == 'batch':
            body['members'] = []
        items.append(dict(body, **{key: hashlib.sha256(wire(body)).hexdigest()}))
    return items, [item[key] for item in items]


def changed_hash(left, right, mutation, calls):
    def digest(raw):
        calls.append(raw)
        if len(calls) == 1:
            targets = (left, right) if mutation.startswith('both') else (
                left if mutation.startswith('left') else right,)
            for target in targets:
                if mutation.endswith('grow'):
                    target.append(target[-1])
                else:
                    target.pop()
        return hashlib.sha256(raw)
    return digest


class PagePairedRosters(unittest.TestCase):
    def test_initial_mismatch_refuses_before_yielding(self):
        for left, right in (([], [1]), ([1], [])):
            with self.subTest(left=left, right=right):
                with self.assertRaisesRegex(ValueError, 'fixture-roster'):
                    next(pages._paired_rows(left, right, 'fixture-roster'))

    def test_body_error_keeps_its_identity(self):
        error = ValueError('body failure')
        with self.assertRaises(ValueError) as caught:
            for _pair in pages._paired_rows([1], [2], 'fixture-roster'):
                raise error
        self.assertIs(caught.exception, error)

    def test_same_length_replacement_remains_a_live_read(self):
        left, right = [1, 2], [3, 4]
        pairs = pages._paired_rows(left, right, 'fixture-roster')
        self.assertEqual(next(pairs), (1, 3))
        left[1] = 5
        self.assertEqual(list(pairs), [(5, 4)])

    def test_pin_roster_drift_during_digest_is_refused(self):
        for kind, check, reason in (
                ('member', pages._member_pins, 'batch-independent-member-pins'),
                ('batch', pages._batch_pins, 'closure-independent-batch-pins')):
            for mutation in ('left-shrink', 'right-shrink', 'both-shrink',
                             'left-grow', 'right-grow', 'both-grow'):
                with self.subTest(kind=kind, mutation=mutation):
                    left, right = rows(kind)
                    calls = []
                    owner = {'MAX_STATE_JSON_BYTES': 10000, 'json': json,
                             'hashlib': SimpleNamespace(sha256=changed_hash(
                                 left, right, mutation, calls))}
                    with self.assertRaisesRegex(ValueError, reason):
                        check(owner, left, right)
                    self.assertLessEqual(len(calls), 2, 'initial roster bounds digest work')

    def test_unchanged_pin_rosters_and_empty_rosters_are_accepted(self):
        owner = {'MAX_STATE_JSON_BYTES': 10000, 'json': json, 'hashlib': hashlib}
        for kind, check in (('member', pages._member_pins), ('batch', pages._batch_pins)):
            with self.subTest(kind=kind):
                self.assertIsNone(check(owner, *rows(kind)))
                self.assertIsNone(check(owner, [], []))


if __name__ == '__main__':
    unittest.main()
