"""Pure dispatch checks over an actually committed no-handoff effects prefix.

The positive memo is produced by real source-v3 effects, not relabeled or
assembled authority. Only detached negative inputs are altered. Classifying
an admissible prefix is not effects-receipt validation, ACK, readiness,
source truth, output receipt, cognition or a held-out improvement.
Root alone executes tests sequentially.
"""

import copy
import unittest

from tests import test_controller_source_resident_v3_effects_prefix as prefix_tests


class ControllerSourceResidentV3EffectsClassifier(unittest.TestCase):
    def setUp(self):
        self.prefix = prefix_tests.ControllerSourceResidentV3EffectsPrefix(methodName="runTest")
        self.addCleanup(self.prefix.doCleanups)
        self.prefix.setUp()

    def test_actual_committed_effects_without_handoff_requires_exact_live_join(self):
        with self.prefix.published_prefix(interrupt=False) as (f, durable, observed):
            runner = self.prefix.runner
            self.assertEqual(observed["trace"], [
                "closure", "corpus", "sync", "graph", "pending", "live-stage", "live-publish", "receipt"])
            actual_receipt = self.prefix.effects.assert_receipt(f)
            self.assertEqual(durable["controller_source_effects_committed"], actual_receipt)
            self.assertNotIn("pulse_status_effects_pending", durable)
            self.assertNotIn("controller_source_effects_pending", durable)
            before = self.prefix.resident.capture.images(f)
            original = copy.deepcopy(durable)
            self.assertEqual(runner._source_state(durable), "effects-committed")
            self.assertEqual(durable, original)
            self.assertEqual(self.prefix.resident.capture.images(f), before)

            # These mismatches preserve every other observed field. A
            # compact live receipt cannot replace its actual effects join
            # just because a handoff has legitimately been retired.
            for field, wrong in (
                    ("generation_sha256", "0" * 64),
                    ("state_sha256", "0" * 64),
                    ("publication_id", "0" * 32),
                    ("transition_sha256", "0" * 64)):
                with self.subTest(detached_live_field=field):
                    changed = copy.deepcopy(durable)
                    self.assertNotEqual(changed["live_loop_committed"][field], wrong)
                    changed["live_loop_committed"][field] = wrong
                    image = copy.deepcopy(changed)
                    with self.assertRaises(RuntimeError):
                        runner._source_state(changed)
                    self.assertEqual(changed, image)
                    self.assertEqual(durable, original)
                    self.assertEqual(self.prefix.resident.capture.images(f), before)

            for absent in (False, True):
                with self.subTest(detached_live_absent=absent):
                    changed = copy.deepcopy(durable)
                    if absent:
                        changed.pop("live_loop_committed")
                    else:
                        changed["live_loop_committed"] = None
                    image = copy.deepcopy(changed)
                    with self.assertRaises(RuntimeError):
                        runner._source_state(changed)
                    self.assertEqual(changed, image)
                    self.assertEqual(durable, original)
                    self.assertEqual(self.prefix.resident.capture.images(f), before)


if __name__ == "__main__":
    unittest.main()
