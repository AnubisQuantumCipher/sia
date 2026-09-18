"""Intake samples cannot turn unknown source hours into observed silence."""

import copy
import datetime
import importlib.util
import os
import unittest
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")


def _load(filename, name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(BIN, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SurpriseObservationIntegrity(unittest.TestCase):
    def setUp(self):
        self.mind_module = _load(
            "siamind.py", "siamind_surprise_observation_integrity")
        self.mind = self.mind_module._empty_mind()

    def _update(self, counts, hour):
        return self.mind_module.surprisal_update(
            self.mind, counts, ts=hour * 3600 + 10)

    def _warm(self):
        # The existing all-band positive fixture supplies explicit intake.
        for hour in range(1344):
            self._update({"org": 5}, hour)

    def test_empty_updates_do_not_invent_observed_zero_hours(self):
        self._warm()
        self._update({}, 1344)
        found = self._update({}, 1345)

        self.assertFalse(any(kind == "absence" for _, kind, _ in found))
        self.assertTrue(all(value > 0
                            for values in self.mind["hist"].values()
                            for value in values))
        self.assertNotEqual(
            self.mind["hourbuf"].get("org"),
            {"hour": 1345, "count": 0})

    def test_other_organ_cannot_certify_missing_organ_silence(self):
        self._warm()
        self._update({"other": 1}, 1344)
        found = self._update({"other": 1}, 1345)

        self.assertFalse(any(organ == "org" and kind == "absence"
                             for organ, kind, _ in found))
        self.assertTrue(all(value > 0
                            for key, values in self.mind["hist"].items()
                            if key.startswith("org|")
                            for value in values))

    def test_gap_closes_only_the_actual_recorded_bucket(self):
        self._update({"org": 5}, 10)
        self._update({"org": 7}, 14)

        self.assertEqual(
            [value for values in self.mind["hist"].values()
             for value in values], [5])
        self.assertEqual(
            self.mind["hourbuf"]["org"], {"hour": 14, "count": 7})

    def test_explicit_zero_sample_is_reachable_but_not_source_inactivity(self):
        self._warm()
        self._update({"org": 0}, 1344)
        found = self._update({"org": 1}, 1345)
        absence = [text for organ, kind, text in found
                   if organ == "org" and kind == "absence"]

        self.assertTrue(absence, "explicit zero intake must remain observable")
        for text in absence:
            self.assertIn("intake", text)
            self.assertIn("does not establish source inactivity", text)
            self.assertNotIn("went silent", text)
            self.assertNotIn("expected activity is missing", text)

    def test_spike_describes_admitted_intake_not_source_production(self):
        self._warm()
        self._update({"org": 50}, 1344)
        found = self._update({"org": 1}, 1345)
        spikes = [text for organ, kind, text in found
                  if organ == "org" and kind == "spike"]

        self.assertTrue(spikes)
        for text in spikes:
            self.assertIn("intake", text)
            self.assertIn("admitted", text)
            self.assertNotIn("produced", text)

    def test_reversed_hour_refuses_before_losing_accumulated_intake(self):
        self._update({"org": 5}, 14)
        previous = copy.deepcopy(self.mind)

        with self.assertRaisesRegex(ValueError, "backward"):
            self._update({"other": 1, "org": 7}, 10)

        self.assertEqual(self.mind, previous)

    def test_explicit_epoch_timestamp_never_reads_wall_clock(self):
        with mock.patch.object(
                self.mind_module.time, "time",
                side_effect=AssertionError("explicit time was discarded")):
            self.mind_module.surprisal_update(
                self.mind, {"org": 5}, ts=0)

        self.assertEqual(self.mind["hourbuf"]["org"]["hour"], 0)

    def test_invalid_counts_refuse_atomically(self):
        self._update({"org": 5}, 14)
        for invalid in (True, -1, 1.5, "1", None):
            with self.subTest(invalid=invalid):
                previous = copy.deepcopy(self.mind)
                with self.assertRaisesRegex(ValueError, "count"):
                    self._update({"another": 1, "org": invalid}, 14)
                self.assertEqual(self.mind, previous)

    def test_legacy_uncovered_history_cannot_seed_current_findings(self):
        self.mind.pop("surprise_basis", None)
        self.mind.update({
            "hourbuf": {"org": {"hour": 10, "count": 0}},
            "hist": {"org|wd:1": [5] * 120},
            "cooldown": {"s:org|wd:1": 10, "other-policy": 10},
            "seen": {"events/org/retained": 10},
        })

        found = self._update({}, 14)

        self.assertEqual(found, [])
        self.assertEqual(self.mind["hist"], {})
        self.assertEqual(self.mind["hourbuf"], {})
        self.assertEqual(self.mind["cooldown"], {"other-policy": 10})
        self.assertEqual(self.mind["seen"], {"events/org/retained": 10})

    def test_unknown_observation_basis_refuses_without_relabeling_history(self):
        self.mind["surprise_basis"] = "unknown-future-basis"
        previous = copy.deepcopy(self.mind)

        with self.assertRaisesRegex(ValueError, "basis"):
            self._update({"org": 5}, 14)

        self.assertEqual(self.mind, previous)

    def test_real_admission_transition_cannot_infer_other_source_silence(self):
        core = _load("sialib.py", "sialib_surprise_observation_integrity")
        self._warm()
        self._update({}, 1344)
        timestamp = 1345 * 3600 + 10
        when = datetime.datetime.fromtimestamp(
            timestamp, tz=datetime.timezone.utc)
        day = when.strftime("%Y-%m-%d")
        event = core.Event(
            "other", when, "observe", "admitted observation",
            occurrence="fixture:other:row")

        transition = core._event_cognitive_transition(
            self.mind, [(event, "events/other/" + day)],
            timestamp, day, "a" * 32)
        replay = core._event_cognitive_transition(
            self.mind, [(event, "events/other/" + day)],
            timestamp, day, "a" * 32)

        self.assertFalse(any(organ == "org" and kind == "absence"
                             for organ, kind, _ in transition["findings"]))
        self.assertEqual(replay["findings"], transition["findings"])
        self.assertTrue(replay["already_applied"])

    def test_coincidence_keeps_intake_counts_and_names_detection_pass(self):
        core = _load("sialib.py", "sialib_intake_coincidence_integrity")
        findings = [
            ("a", "spike", "SIA admitted 50 events into an hourly intake "
             "bucket (previous max 5)"),
            ("b", "spike", "SIA admitted 10 events into an hourly intake "
             "bucket (previous max 5)"),
        ]

        pairs = core.coincidence_findings({}, findings, now=1345 * 3600)

        self.assertTrue(pairs)
        self.assertIn("a (50 vs max 5)", pairs[0][0])
        self.assertIn("b (10 vs max 5)", pairs[0][0])
        self.assertIn("same detection pass", pairs[0][0])
        self.assertIn("does not establish simultaneous source activity",
                      pairs[0][0])


if __name__ == "__main__":
    unittest.main()
