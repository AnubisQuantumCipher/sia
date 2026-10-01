"""Configured resident controller-source dispatch must enter v3 explicitly.

These controls exercise only the zero-argument routing seam. The full v3
transaction's storage, capture, recovery, publication and ACK behavior remains
covered by its dedicated integration suites.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import contextlib
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

import siacontrollerdeliveryepoch as epoch_api
import siadelivery
import sialib
import sialiveloop


NOW = 1730000000
RESULT = {"status": "configured-v3-route-observed"}


class ConfiguredResidentV3(unittest.TestCase):
    def marker(self, adoption):
        return {
            "schema": "sia-controller-delivery-epoch-marker-v1",
            "epoch_id": "epoch-configured-v3",
            "started_at": NOW,
            "birth_sha256": "b" * 64,
            "adoption_sha256": adoption,
        }

    @contextlib.contextmanager
    def owned(self, active, name):
        self.assertFalse(active[name])
        active[name] = True
        try:
            yield
        finally:
            active[name] = False

    def invoke(self, memo):
        active = {"brainstem": False, "corpus": False}
        expected_limits = copy.deepcopy(siadelivery._LIMITS)
        expected_pin = sialiveloop._sha(expected_limits)

        def transaction(*, operation, clock, journal_limits,
                        expected_journal_limits_sha256,
                        expected_adoption_sha256):
            self.assertTrue(active["brainstem"])
            self.assertTrue(active["corpus"])
            self.assertEqual(journal_limits, expected_limits)
            self.assertIsNot(journal_limits, siadelivery._LIMITS)
            self.assertEqual(expected_journal_limits_sha256, expected_pin)
            self.assertEqual(expected_adoption_sha256,
                             None if epoch_api._MARKER not in memo
                             else memo[epoch_api._MARKER]["adoption_sha256"])
            self.assertTrue(callable(operation))
            self.assertTrue(callable(clock))
            return copy.deepcopy(RESULT)

        with mock.patch.object(
                sialib, "brainstem_owner",
                side_effect=lambda: self.owned(active, "brainstem")), \
                mock.patch.object(
                    sialib, "corpus_owner",
                    side_effect=lambda: self.owned(active, "corpus")), \
                mock.patch.object(sialib, "load_memo", return_value=memo) as loaded, \
                mock.patch.object(
                    sialib, "_run_controller_source_transaction_v3",
                    side_effect=transaction) as v3, \
                mock.patch.object(
                    sialib, "_run_controller_source_transaction_v2",
                    side_effect=AssertionError("configured cycle dispatched v2")):
            result = sialib._run_controller_source_cycle()
        loaded.assert_called_once_with()
        v3.assert_called_once()
        self.assertEqual(result, RESULT)
        self.assertEqual(active, {"brainstem": False, "corpus": False})

    def test_unadopted_state_routes_v3_with_explicit_null_original_pin(self):
        self.invoke({"pulse_seq": 0, "sync_needed": False})

    def test_existing_adoption_routes_v3_with_the_original_persisted_pin(self):
        self.invoke({
            "pulse_seq": 1,
            "sync_needed": False,
            epoch_api._MARKER: self.marker("a" * 64),
        })

    def test_clock_and_initial_builder_remain_lazy_callbacks_of_v3(self):
        memo = {"pulse_seq": 0, "sync_needed": False}
        active = {"brainstem": False, "corpus": False}
        built = {"initial": "controlled"}

        def transaction(*, operation, clock, **kwargs):
            self.assertTrue(active["brainstem"])
            self.assertTrue(active["corpus"])
            self.assertEqual(clock(), NOW)
            self.assertEqual(operation(), built)
            return copy.deepcopy(RESULT)

        with mock.patch.object(
                sialib, "brainstem_owner",
                side_effect=lambda: self.owned(active, "brainstem")), \
                mock.patch.object(
                    sialib, "corpus_owner",
                    side_effect=lambda: self.owned(active, "corpus")), \
                mock.patch.object(sialib, "load_memo", return_value=memo), \
                mock.patch.object(sialib.time, "time", return_value=NOW), \
                mock.patch("siacontrollerepoch.build_initial",
                           return_value=built) as initial, \
                mock.patch.object(
                    sialib, "_run_controller_source_transaction_v3",
                    side_effect=transaction), \
                mock.patch.object(
                    sialib, "_run_controller_source_transaction_v2",
                    side_effect=AssertionError("configured cycle dispatched v2")):
            self.assertEqual(sialib._run_controller_source_cycle(), RESULT)
        initial.assert_called_once_with(sialib.__dict__, observed_at=NOW)

    def test_malformed_persisted_marker_refuses_before_either_dispatch(self):
        for marker in (
                {"schema": "sia-controller-delivery-epoch-marker-v1"},
                self.marker(True),
                {**self.marker("a" * 64), "birth_sha256": "not-a-digest"},
                {**self.marker("a" * 64), "started_at": True},
                {**self.marker("a" * 64), "epoch_id": ""},
        ):
            with self.subTest(marker=marker), \
                    mock.patch.object(sialib, "brainstem_owner",
                                      return_value=contextlib.nullcontext()), \
                    mock.patch.object(sialib, "corpus_owner",
                                      return_value=contextlib.nullcontext()), \
                    mock.patch.object(
                        sialib, "load_memo",
                        return_value={epoch_api._MARKER: marker}), \
                    mock.patch.object(
                        sialib, "_run_controller_source_transaction_v3") as v3, \
                    mock.patch.object(
                        sialib, "_run_controller_source_transaction_v2") as v2:
                with self.assertRaises((ValueError, RuntimeError, TypeError)):
                    sialib._run_controller_source_cycle()
                v3.assert_not_called()
                v2.assert_not_called()


if __name__ == "__main__":
    unittest.main()
