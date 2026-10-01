"""Versioned preparation envelope retains every individual byte boundary."""
import copy
import sys
from pathlib import Path
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bin'))
import sialib
import siacontrollerdeliverywrapper as wrapper
import siasourcebatch as source


class PreparationCompoundAdmission(unittest.TestCase):
    def setUp(self):
        self.owner = dict(vars(sialib))
        self.owner['MAX_STATE_JSON_BYTES'] = 4096
        self.request = {'batch': {'body': 'b' * 3000},
                        'previous_generation': {'body': 'g' * 3000},
                        'expected_previous_generation_sha256': 'a' * 64}

    def admit(self):
        self.assertTrue(hasattr(wrapper, 'PreparationAdmissionV1'),
                        'missing explicit compound admission')
        return wrapper.PreparationAdmissionV1(self.owner, self.request)

    def test_closed_compound_admits_while_original_aggregate_still_refuses(self):
        with self.assertRaises(source.SourceBatchRefusal):
            wrapper._Admission(self.owner, self.request)
        admitted = self.admit()
        self.assertEqual(admitted.schema, 'sia-live-preparation-compound-v1')
        self.assertEqual(admitted.admitted, self.request)
        self.assertIsNot(admitted.admitted, self.request)
        admitted.current()

    def test_each_oversize_slot_refuses_before_any_copy(self):
        for key in ('batch', 'previous_generation'):
            with self.subTest(key=key):
                original = self.request[key]
                self.request[key] = {'body': 'x' * 4096}
                with mock.patch.object(wrapper.copy, 'deepcopy',
                                       side_effect=AssertionError('premature copy')):
                    with self.assertRaises(source.SourceBatchRefusal):
                        self.admit()
                self.request[key] = original

    def test_extra_missing_and_malformed_slots_refuse(self):
        for change in ('extra', 'missing', 'pin', 'batch'):
            with self.subTest(change=change):
                original = copy.deepcopy(self.request)
                if change == 'extra':
                    self.request['unbound'] = 'x'
                elif change == 'missing':
                    del self.request['previous_generation']
                elif change == 'pin':
                    self.request['expected_previous_generation_sha256'] = 'bad'
                else:
                    self.request['batch'] = []
                with self.assertRaises(wrapper.ControllerDeliveryWrapperRefusal):
                    self.admit()
                self.request = original

    def test_original_detached_owner_and_operation_mutations_refuse(self):
        for target in ('original', 'detached', 'owner', 'operation',
                       'detached_owner'):
            with self.subTest(target=target):
                self.setUp()
                admitted = self.admit()
                if target == 'original':
                    self.request['batch']['body'] = 'changed'
                elif target == 'detached':
                    admitted.admitted['previous_generation']['body'] = 'changed'
                elif target == 'owner':
                    self.owner['MAX_CONFIG_TAGS'] += 1
                elif target == 'operation':
                    self.owner['_canonical_utc_timestamp'] = lambda value: value
                else:
                    admitted.owner['MAX_STATE_JSON_BYTES'] = 8192
                with self.assertRaises(wrapper.ControllerDeliveryWrapperRefusal):
                    admitted.current()

    def test_unicode_cycles_and_owner_basis_overflow_refuse_before_copy(self):
        for target in ('unicode', 'cycle', 'basis'):
            with self.subTest(target=target):
                self.setUp()
                if target == 'unicode':
                    self.request['batch'] = {'body': 'é' * 3000}
                elif target == 'cycle':
                    self.request['batch']['cycle'] = self.request['batch']
                else:
                    self.owner['LIVE_PUBLICATION_NON_CLAIMS'] = ['x' * 4096]
                with mock.patch.object(wrapper.copy, 'deepcopy',
                                       side_effect=AssertionError('premature copy')):
                    with self.assertRaises(source.SourceBatchRefusal):
                        self.admit()


if __name__ == '__main__':
    unittest.main()
