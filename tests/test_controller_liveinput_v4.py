"""Explicit compound preparation preserves genuine v3 source semantics."""
import ast
import copy
import importlib
import inspect
import unittest
from unittest import mock

from tests import test_controller_liveinput_v3 as prior


class ControllerLiveInputV4(unittest.TestCase):
    def setUp(self):
        self.fixture = prior.ControllerLiveInputV3(methodName='runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.module = self.fixture.module
        self.assertTrue(callable(getattr(self.module, 'prepare_inputs_v4', None)),
                        'missing explicit compound preparation entrypoint')

    def test_candidate_and_status_explicitly_select_the_same_version(self):
        for name in ('siacontrollercandidate', 'siacontrollerstatus'):
            with self.subTest(module=name):
                tree = ast.parse(inspect.getsource(importlib.import_module(name)))
                called = {node.func.attr for node in ast.walk(tree)
                          if isinstance(node, ast.Call)
                          and isinstance(node.func, ast.Attribute)
                          and isinstance(node.func.value, ast.Name)
                          and node.func.value.id == 'siacontrollerliveinput'}
                self.assertIn('prepare_inputs_v4', called)
                self.assertNotIn('prepare_inputs_v3', called)

    def test_genuine_source_preserves_outputs_and_selects_compound_explicitly(self):
        wrapper = importlib.import_module('siacontrollerdeliverywrapper')
        with self.fixture.captured(nonidle=True) as f:
            before = self.fixture.images(f)
            expected = self.fixture.prepare(f)
            with self.fixture.no_acquisition(f), mock.patch.object(
                    wrapper, 'PreparationAdmissionV1',
                    wraps=wrapper.PreparationAdmissionV1) as admission:
                result = self.module.prepare_inputs_v4(
                    f.owner, batch=f.batch, previous_generation=f.generation,
                    expected_previous_generation_sha256=f.generation['generation_sha256'])
            admission.assert_called_once()
            self.assertEqual(result, expected)
            self.fixture.assert_request(f, result)
            self.assertEqual(self.fixture.images(f), before)

    def test_rehashed_full_parent_change_does_not_pass_on_same_state(self):
        with self.fixture.captured(nonidle=True) as f:
            changed = copy.deepcopy(f.generation)
            changed['publication_id'] = 'f' * 32
            changed['generation_sha256'] = self.fixture.live._own(
                changed, 'generation_sha256')
            self.assertEqual(changed['transition']['state'],
                             f.generation['transition']['state'])
            with self.fixture.no_acquisition(f), self.assertRaises(
                    self.module.ControllerLiveInputRefusal) as caught:
                self.module.prepare_inputs_v4(
                    f.owner, batch=f.batch, previous_generation=changed,
                    expected_previous_generation_sha256=changed['generation_sha256'])
            self.assertEqual(caught.exception.reason, 'v3-full-parent-generation-differs')


if __name__ == '__main__':
    unittest.main()
