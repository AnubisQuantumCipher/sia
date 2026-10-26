"""Malformed result controls for the disposable cgroup acceptance oracle."""
import copy
import unittest

from check_cgroup_boundary import validate_result


def baseline():
    observed = {'LoadState': 'loaded', 'MemoryMax': '67108864',
                'MemorySwapMax': '0', 'TasksMax': '8', 'Result': 'oom-kill',
                'ExecMainCode': '2', 'ExecMainStatus': '9'}
    events = {'max': 0, 'oom': 0, 'oom_kill': 0, 'oom_group_kill': 0}
    rows = [
        {'event': 'bounds-checked', 'pid': 10, 'cgroup': 'fixture', 'memory_events': events},
        {'event': 'bounds-checked', 'pid': 11, 'cgroup': 'fixture'},
        {'event': 'child-memory-ready', 'pid': 11, 'blocks': 40, 'cgroup': 'fixture'},
        {'event': 'parent-memory-start', 'pid': 10, 'child_pid': 11},
        {'event': 'after-workload', 'cgroup': 'fixture',
         'memory_events': {key: 1 for key in events}},
    ]
    return observed, rows


class CgroupResultControls(unittest.TestCase):
    def test_complete_synthetic_result_is_accepted(self):
        observed, rows = baseline()
        validate_result('memory-child', observed, rows, 1)

    def test_missing_or_foreign_child_evidence_refuses(self):
        for mutation in (
                lambda rows: rows.pop(1),
                lambda rows: rows[1].update(cgroup='foreign'),
                lambda rows: rows[2].update(cgroup='foreign'),
                lambda rows: rows[3].update(child_pid=12),
                lambda rows: rows[3].update(pid=12),
                lambda rows: rows[2].update(blocks=0),
                lambda rows: rows.append(copy.deepcopy(rows[2]))):
            observed, rows = baseline()
            mutation(rows)
            with self.assertRaises(RuntimeError):
                validate_result('memory-child', observed, rows, 1)

    def test_missing_local_events_or_counter_identity_refuses(self):
        for key in ('max', 'oom', 'oom_kill', 'oom_group_kill'):
            observed, rows = baseline()
            rows[-1]['memory_events'][key] = 0
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                validate_result('memory-child', observed, rows, 1)
        observed, rows = baseline()
        rows[-1]['cgroup'] = 'foreign'
        with self.assertRaises(RuntimeError):
            validate_result('memory-child', observed, rows, 1)

    def test_non_oom_and_successful_termination_refuse(self):
        for key, value in (('LoadState', 'not-found'), ('Result', 'signal'),
                           ('ExecMainCode', '1'), ('ExecMainStatus', '15'),
                           ('MemoryMax', 'infinity')):
            observed, rows = baseline()
            observed[key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                validate_result('memory-child', observed, rows, 1)
        observed, rows = baseline()
        with self.assertRaises(RuntimeError):
            validate_result('memory-child', observed, rows, 0)


if __name__ == '__main__':
    unittest.main()
