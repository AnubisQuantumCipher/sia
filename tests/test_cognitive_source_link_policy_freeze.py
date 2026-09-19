"""Freeze a feasibility design before inspecting retained-source yield."""
import json
from pathlib import Path
import unittest

from tests.test_cognitive_source_link_selection import policy_fixture


class SourceLinkPolicyFreeze(unittest.TestCase):
    def test_complete_declared_policy_is_fixed_before_real_source_selection(self):
        path = Path(__file__).resolve().parents[1] / 'benchmarks/cognitive/source-link-feasibility-policy-v1.json'
        self.assertTrue(path.is_file(), 'source-link feasibility policy must be frozen before the real-source check')
        expected = policy_fixture()
        expected['seed'] = 'source-link-retained-feasibility-v1'
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), expected)


if __name__ == '__main__':
    unittest.main()
