"""Pin the real front-door source capture before any mechanism tuning.

Literal identities below were observed from the front-door command and file
hash output. They do not authenticate a future substituted private artifact.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / 'benchmarks/cognitive/history-capture-v1.json'


class CognitiveCaptureFreeze(unittest.TestCase):
    def test_recorded_source_identity_and_failed_initial_task_are_not_reinterpreted(self):
        self.assertTrue(FILE.is_file(), 'pre-tuning real source capture identity must be committed')
        record = json.loads(FILE.read_text(encoding='utf-8'))
        self.assertEqual(record['schema'], 'sia-mission-history-capture-freeze-v1')
        self.assertEqual(record['dataset_id'], '3216e7f4cae8dfb0fc25f8f7044673bfc0f9a1471a877f6669bfbad6a9e16bda')
        self.assertEqual(record['capture_sha256'], '8db421fa76e2878f1488fb56bedccf74ab971709195161ce7ca390ba1b57fd9a')
        self.assertEqual(record['capture_wire_sha256'], 'e30fad4fa823f3341c76700e8d477eb64caa21bbd9c869505c24a01285e2d6cf')
        self.assertEqual(record['producer_checkout_commit'], '40167f6')
        self.assertEqual(record['source'], 'sia bench generate --cognitive-history')
        self.assertEqual(record['initial_selection'], {
            'policy_sha256': '7373e388a775faf78e1911d0cbe28e3b69226e9e5bff6276a38e159f640bd1a0',
            'status': 'refused',
            'reason': 'required class is unavailable: recency-heavy (no-feasible-selected-queries)',
            'diagnosis': 'no-competing-recorded-outcome',
        })
        self.assertEqual(record['chronology'], 'source-captured-before-mechanism-tuning-and-heldout-evaluation')
        self.assertTrue(record['non_claims'])
        for field in ('queries', 'answer_key', 'scores', 'win', 'selection_sha256'):
            self.assertNotIn(field, record)

    def test_selected_v2_identity_is_committed_without_private_material_or_scores(self):
        selected = FILE.with_name('history-selection-v2.json')
        self.assertTrue(selected.is_file(), 'selected real query split must be pinned before tuning')
        record = json.loads(selected.read_text(encoding='utf-8'))
        self.assertEqual(record['schema'], 'sia-mission-history-selection-freeze-v1')
        self.assertEqual(record['selection_sha256'], 'aa82aa03624db6418b09bb3de862b0b6cb433900d579c2b54175fa4ebbed994f')
        self.assertEqual(record['selection_wire_sha256'], 'da984fb67eb7cfc049e6e4bd75961956d2fc1776c0965ece5f41d6952ad72673')
        self.assertEqual(record['selection_policy_sha256'], 'b08f02a09391f17a53a50480ed3ead17c3d3878864882380efe9791049a6eb6f')
        self.assertEqual(record['capture_sha256'], '8db421fa76e2878f1488fb56bedccf74ab971709195161ce7ca390ba1b57fd9a')
        self.assertEqual(record['pages_sha256'], '8e5226d85ffe2a8e45b6c48bbc9ed20080c8bd859c315cc756b9f05b951494e3')
        self.assertEqual(record['producer_checkout_commit'], '86df68f')
        self.assertEqual(record['chronology'], 'selection-frozen-before-mechanism-tuning-and-heldout-evaluation')
        self.assertTrue(record['non_claims'])
        for field in ('queries', 'answer_key', 'scores', 'win'):
            self.assertNotIn(field, record)


if __name__ == '__main__':
    unittest.main()
