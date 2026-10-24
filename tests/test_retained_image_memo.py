"""Experimental fresh-admission checks; not an approved R05 oracle replacement.

The original reuse assertion remains required. Its replacement below was made
under a misbound approval; docs/R05-AUTHORIZATION-CORRECTION-20261024.md records
the correction. These experimental checks do not establish reuse compliance.
Image identity cannot certify mutable callbacks or current policy.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import copy
import importlib
import os
import unittest
from unittest import mock

from tests import test_controller_source_idle as idle_tests


class RetainedImageMemo(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.path.expanduser("~"), sia_test_home.ISOLATED_HOME)
        self.idle = idle_tests.ControllerSourceIdle(methodName="runTest")
        self.idle.setUp()
        self.addCleanup(self.idle.doCleanups)
        self.source = importlib.import_module("siasourcebatch")
        self.source._VALIDATED_BATCHES.clear()
        self.addCleanup(self.source._VALIDATED_BATCHES.clear)

    def test_repeated_validation_preserves_image_and_context_checks(self):
        with self.idle.completed() as (case, retained, _committed, _status, _generation):
            owner = case.lib.__dict__
            pin = retained["batch_sha256"]
            # The fixture itself validated this batch; start from an empty memo.
            self.source._VALIDATED_BATCHES.clear()
            real = self.source._validate_batch_image
            calls = []

            def counted(owner_, batch, expected):
                calls.append(expected)
                return real(owner_, batch, expected)

            with mock.patch.object(self.source, "_validate_batch_image", counted):
                first = self.source.validate_batch(owner, retained, pin)
                second = self.source.validate_batch(owner, retained, pin)
                self.assertEqual(calls, [pin, pin], "every call checks current policy")
                self.assertEqual(first, second)
                if first is not None:
                    self.assertIsNot(first, second, "callers receive their own copy")
                # A changed image is checked again and refused on its pin.
                mutated = copy.deepcopy(retained)
                mutated["status"] = "captured-not-published"
                mutated["observed_at"] = retained["observed_at"] + 1
                with self.assertRaises(self.source.SourceBatchRefusal):
                    self.source.validate_batch(owner, mutated, pin)
                self.assertEqual(len(calls), 3)
                # Changed owner constants still require full admission.
                with mock.patch.dict(owner, {"VERSION": "0.0.0"}):
                    self.source.validate_batch(owner, retained, pin)
                self.assertEqual(len(calls), 4)
                self.assertEqual(self.source._VALIDATED_BATCHES, {})


if __name__ == "__main__":
    unittest.main()
