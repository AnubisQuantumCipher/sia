"""A byte-identical retained image validated once is not re-derived.

Transactions re-validate the retained capture and batch at every consistency
check; on a 12 MB capture each derivation cost 78 seconds while the identity
digest cost about one. The memo keeps the digest (every call) and skips only
the derivation of an image already validated under the same constants.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import copy
import importlib
import unittest
from unittest import mock

from tests import test_controller_source_idle as idle_tests


class RetainedImageMemo(unittest.TestCase):
    def setUp(self):
        self.idle = idle_tests.ControllerSourceIdle(methodName="runTest")
        self.idle.setUp()
        self.addCleanup(self.idle.doCleanups)
        self.source = importlib.import_module("siasourcebatch")
        self.source._VALIDATED_BATCHES.clear()
        self.addCleanup(self.source._VALIDATED_BATCHES.clear)

    def test_second_validation_of_the_same_batch_skips_derivation(self):
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
                self.assertEqual(calls, [pin], "the unchanged image is derived once")
                self.assertEqual(first, second)
                if first is not None:
                    self.assertIsNot(first, second, "callers receive their own copy")
                # A changed image is never served from the memo: it is derived
                # again and refused on its pin.
                mutated = copy.deepcopy(retained)
                mutated["status"] = "captured-not-published"
                mutated["observed_at"] = retained["observed_at"] + 1
                with self.assertRaises(self.source.SourceBatchRefusal):
                    self.source.validate_batch(owner, mutated, pin)
                self.assertEqual(len(calls), 2)
                # Different owner constants are a different key.
                with mock.patch.dict(owner, {"VERSION": "0.0.0"}):
                    self.source.validate_batch(owner, retained, pin)
                self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
