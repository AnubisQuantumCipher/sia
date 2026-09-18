"""Legacy source adapters cannot discard a newly supplied delivery wrapper.

These tests use real temporary-root source captures. The unexpected values
are adversarial fields, not admitted source-v3 inputs or output receipts.
"""

import copy
import unittest
from unittest import mock

from tests import test_controller_source_idle as idle_tests


class ControllerLegacyDeliveryRefusal(unittest.TestCase):
    def test_legacy_input_rejects_delivery_membership_and_late_insertion(self):
        fixture = idle_tests.ControllerSourceIdle(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        adapter = fixture.live_input
        with fixture.completed() as (
                case, retained, committed, _status, generation):
            fixture.reserve(case)
            _request, successor = fixture.capture_successor(case, retained, committed)
            for source_batch, previous, pin in (
                    (retained, None, None),
                    (successor, generation["transition"]["state"], generation["state_sha256"])):
                kw = {"batch": source_batch, "previous_state": previous,
                      "expected_previous_state_sha256": pin}
                control = adapter.prepare_inputs(**kw)
                self.assertEqual(control["intake"], source_batch["intake_projection"]["intake"])
                for unadmitted in (None, {}, {"status": "not-a-receipt"}):
                    changed = copy.deepcopy(source_batch)
                    changed["delivery_input"] = unadmitted
                    before = copy.deepcopy(changed)
                    with self.subTest(schema=source_batch["schema"], value=unadmitted), \
                            self.assertRaises(adapter.ControllerLiveInputRefusal):
                        adapter.prepare_inputs(**dict(kw, batch=changed))
                    self.assertEqual(changed, before)

                changed = copy.deepcopy(source_batch)
                real_copy = copy.deepcopy
                fired = []

                def insert_after_copy(value, *args, **kwargs):
                    detached = real_copy(value, *args, **kwargs)
                    if type(value) is dict and set(value) == set(control) and not fired:
                        fired.append(True)
                        changed["delivery_input"] = None
                    return detached

                with self.subTest(schema=source_batch["schema"], phase="final-copy"), \
                        mock.patch.object(copy, "deepcopy", side_effect=insert_after_copy), \
                        self.assertRaises(adapter.ControllerLiveInputRefusal):
                    adapter.prepare_inputs(**dict(kw, batch=changed))
                self.assertTrue(fired)
