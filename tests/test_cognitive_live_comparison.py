"""Synthetic live-use ranking and ordered metric requests, not executed wins."""
import copy
import unittest
from unittest import mock

import siacognitivemeasure as measurement
import sialiveloop as live
from tests import test_cognitive_live_binding as binding_tests
from tests import test_live_loop as live_tests
from tests import test_activation_trace as activation_tests
from tests import test_cognitive_event_exposure as exposure_tests


def policy_fixture():
    activation = copy.deepcopy(activation_tests.POLICY)
    return {"schema": "sia-cognitive-live-ranking-policy-v1",
            "observed_at": live_tests.NOW, "activation_policy": activation,
            "activation_policy_sha256": live_tests.digest(activation),
            "ordering": "origin-slot-preserving-activation-v1",
            "unavailable": "last-within-origin-stable-v1"}


class CognitiveLiveComparison(unittest.TestCase):
    def setUp(self):
        self.fixture = binding_tests.CognitiveLiveBinding(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.policy = policy_fixture()

    def call(self, **overrides):
        with self.fixture.fixture.fixture._pure():
            return measurement.prepare_live_comparison(**{
                "replay_inputs": self.fixture.replay, "live_capture": self.fixture.capture,
                "expected_live_capture_sha256": self.fixture.capture["capture_sha256"],
                "ranking_policy": self.policy,
                "expected_ranking_policy_sha256": live_tests.digest(self.policy), **overrides})

    def test_empty_histories_tie_raw_with_identical_metric_requests(self):
        before = copy.deepcopy((self.fixture.replay, self.fixture.capture, self.policy))
        result = self.call()
        self.assertEqual(result["schema"], "sia-cognitive-live-comparison-v1")
        self.assertEqual(result["arithmetic_status"], "not-evaluated")
        self.assertEqual([arm["name"] for arm in result["arms"]], ["raw-original", "live-use"])
        raw, live = result["arms"]
        for field in ("queries", "classes", "jackal_requests", "query_orders"):
            self.assertEqual(raw[field], live[field])
        self.assertTrue(raw["jackal_requests"])
        self.assertEqual((self.fixture.replay, self.fixture.capture, self.policy), before)
        self.assertEqual(result["comparison_sha256"], live_tests.own_digest(result, "comparison_sha256"))

    def test_rank_worker_preserves_origin_slots_and_separated_duplicate_ties(self):
        def row(ref, origin, timestamp=None, subject=None):
            return {"row_ref": ref, "origin": origin,
                    "trace": None if timestamp is None else {"v": 1, "subject": subject or ref,
                        "complete": True, "uses": [{"id": "use-" + ref, "timestamp": timestamp}]}}
        rows = [row("older", "evidence", live_tests.START), row("model", "model", live_tests.START),
                row("recent", "evidence", live_tests.PERCEPTION_TIMES[-1]), row("absent", "evidence")]
        result = measurement._rank_live_query(rows=rows, observed_at=live_tests.NOW,
                                              activation_policy=self.policy["activation_policy"])
        self.assertEqual(result["order"], ["recent", "model", "older", "absent"])
        equal = [row("first", "evidence", live_tests.START), row("second", "evidence", live_tests.START)]
        equal.append({**copy.deepcopy(equal[0]), "row_ref": "same-version-later-chunk"})
        result = measurement._rank_live_query(rows=equal, observed_at=live_tests.NOW,
                                              activation_policy=self.policy["activation_policy"])
        self.assertEqual(result["order"], [row["row_ref"] for row in equal])

    def test_bad_policy_or_clock_refuses_before_ranking(self):
        for field, value in (("observed_at", live_tests.START), ("ordering", "global-promotion"),
                             ("answer_key", "forbidden")):
            policy = {**self.policy, field: value}
            with self.subTest(field=field), mock.patch.object(measurement, "_rank_live_query",
                    side_effect=AssertionError("ranking before admission")):
                with self.assertRaises(measurement.MeasurementRefusal):
                    self.call(ranking_policy=policy, expected_ranking_policy_sha256=live_tests.digest(policy))

    def test_worker_candidate_loss_is_rejected_before_metric_credit(self):
        with mock.patch.object(measurement, "_rank_live_query", return_value={"order": [], "activation": {}}):
            with self.assertRaisesRegex(measurement.MeasurementRefusal, "bijection"):
                self.call()

    def test_worker_cannot_relabel_its_input_to_evade_origin_slot_check(self):
        def relabel(**kw):
            kw["rows"][0]["origin"] = "legacy-unlabeled"
            return {"order": [row["row_ref"] for row in kw["rows"]], "activation": {}}
        with mock.patch.object(measurement, "_rank_live_query", side_effect=relabel):
            with self.assertRaises(measurement.MeasurementRefusal):
                self.call()

    def test_witnessed_encoding_changes_order_and_preserves_target_denominators(self):
        baseline = self.fixture.replay["baseline"]
        raw_rows = baseline["observation"]["query"]["payload"]["results"][0]["rows"]
        intake = self.fixture.live_arguments["intake"]
        page = next(page for page in intake["pages"] if page["subject"] == raw_rows[-1]["slug"])
        intake["observations"] = [{"id": "encoding-" + str(index), "timestamp": stamp,
            "version_sha256": page["version_sha256"], "symbol": symbol, "context": "aegis",
            "native_timestamp": None} for index, (stamp, symbol) in enumerate(zip(
                live_tests.PERCEPTION_TIMES, ("outcome", "outcome", "intent", "outcome"), strict=True))]
        self.fixture.live_arguments["expected_intake_sha256"] = live_tests.digest(intake)
        self.fixture.capture = live.prepare_pulse(**self.fixture.live_arguments)["history_capture"]
        self.assertTrue(self.fixture.capture["uses"])
        result = self.call()
        original, changed = result["arms"]
        self.assertNotEqual(original["query_orders"], changed["query_orders"])
        for before, after in zip(original["queries"], changed["queries"], strict=True):
            self.assertEqual(before["id"], after["id"])
            self.assertEqual(before["targets"], after["targets"])
            self.assertEqual([cutoff["target_count"] for cutoff in before["cutoffs"]],
                             [cutoff["target_count"] for cutoff in after["cutoffs"]])
        self.assertEqual(result["measurement_plan"]["baseline"], baseline)
        self.assertEqual(result["arithmetic_status"], "not-evaluated")

    def test_heldout_accepts_predeclared_policy_and_refuses_a_rehashed_change(self):
        heldout = exposure_tests.CognitiveEventExposure(methodName="runTest")
        heldout.setUp()
        self.addCleanup(heldout.doCleanups)
        original_freeze = heldout.fixture._freeze

        def freeze_before_observation():
            value = original_freeze()
            value["parameters"].update(
                live_history_capture_sha256=self.fixture.capture["capture_sha256"],
                live_ranking_policy_sha256=live_tests.digest(self.policy))
            value["parameters_sha256"] = live_tests.digest(value["parameters"])
            value["freeze_sha256"] = live_tests.own_digest(value, "freeze_sha256")
            heldout.fixture.kw["expected_parameter_freeze_sha256"] = value["freeze_sha256"]
            return value

        with mock.patch.object(heldout.fixture, "_freeze", side_effect=freeze_before_observation):
            heldout._inputs(split="heldout")
        replay = heldout.kw["replay_inputs"]
        result = self.call(replay_inputs=replay)
        self.assertEqual(result["measurement_plan"]["split"], "heldout")
        changed = copy.deepcopy(self.policy)
        changed["activation_policy"]["decay"] = 0.75
        changed["activation_policy_sha256"] = live_tests.digest(changed["activation_policy"])
        with mock.patch.object(measurement, "_rank_live_query", side_effect=AssertionError("late freeze check")):
            with self.assertRaisesRegex(measurement.MeasurementRefusal, "heldout freeze.*ranking"):
                self.call(replay_inputs=replay, ranking_policy=changed,
                          expected_ranking_policy_sha256=live_tests.digest(changed))
