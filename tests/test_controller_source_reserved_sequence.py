"""Reserved controller sequence binds prior status and publishes the reservation.

The resident caller durably allocates a pulse sequence before source effects.
Its admitted status is therefore the immediately preceding published status,
not a fabricated status carrying the new sequence.  Equal sequence inputs
remain covered by the component suites as replay compatibility; this module
proves the real prior-to-reserved direction and the final status projection.
"""

import copy
import importlib
import unittest

from tests import test_controller_source_effects as effects_tests
from tests import test_controller_source_status_effects as status_tests
from tests import test_live_publication as publication_tests


class ControllerSourceReservedSequence(unittest.TestCase):
    def setUp(self):
        self.fixture = effects_tests.ControllerSourceEffects(
            methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.lib = self.fixture.lib
        self.live = self.fixture.live
        self.loop = self.fixture.effects.loop
        self.source_batch = importlib.import_module("siasourcebatch")
        self.source_effects = importlib.import_module("siasourceeffects")

    def test_prior_status_binds_reserved_sequence_and_projection_publishes_it(self):
        prior = copy.deepcopy(self.fixture.admitted_status)
        reserved = publication_tests.pulse_tests.FROZEN_EFFECTLESS_STATUS[
            "pulse_seq"]
        self.assertGreater(reserved, prior["pulse_seq"])

        batch = self.fixture.producer._capture()
        retained = self.fixture.producer._stage(batch)
        self.assertEqual(retained, batch)
        self.live.memo["pulse_seq"] = reserved
        self.live._write(self.live.paths["MEMO_PATH"], self.live.memo)

        candidate = self.fixture.producer._prepare_candidate(
            admitted_status=prior)
        transition = self.loop.prepare_pulse(**candidate["prepare_inputs"])
        self.assertIsNone(self.lib._stage_controller_source_live_binding(
            memo=self.live.memo, admitted_status=prior, seq=reserved))
        binding = copy.deepcopy(
            self.live.memo["controller_source_live_pending"])
        self.assertEqual(binding["seq"], reserved)
        self.assertEqual(
            binding["admitted_status_sha256"],
            status_tests.live_tests.digest(prior))

        arguments = {
            "admitted_status": prior,
            "batch": retained,
            "expected_batch_sha256": retained["batch_sha256"],
            "source_live_pending": binding,
            "candidate": candidate,
            "transition": transition,
            "expected_transition_sha256": transition[
                "transition_sha256"],
            "started_at": status_tests.STARTED_AT,
        }
        prepared = self.lib._prepare_controller_source_status_effects(
            **arguments)
        projected = self.source_effects._project_status(
            vars(self.lib), self.source_batch, self.loop,
            prior, binding, prepared, transition,
            self.fixture._new_graph(), prepared["history"],
            effects_tests.STATUS_AT)

        self.assertEqual(prior["pulse_seq"], self.fixture.admitted_status[
            "pulse_seq"])
        self.assertEqual(projected["pulse_seq"], reserved)
        self.assertIsNotNone(
            self.lib._recoverable_status_integrity(projected))


if __name__ == "__main__":
    unittest.main()
