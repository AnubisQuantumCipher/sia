"""Synthetic raw-run replay joined to controller history; no live metric claim."""
import copy
import unittest

import siacognitivemeasure as measurement
import sialiveloop as live
from tests import test_cognitive_event_exposure as exposure_tests
from tests import test_live_loop as live_tests


class CognitiveLiveBinding(unittest.TestCase):
    def setUp(self):
        self.fixture = exposure_tests.CognitiveEventExposure(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture._inputs()
        self.replay = self.fixture.kw["replay_inputs"]
        source = live_tests.LiveLoopPureIntegration(methodName="runTest")
        source._inputs()
        self.addCleanup(source.doCleanups)
        intake = source.kw["intake"]
        intake["pages"] = []
        for page in self.replay["baseline"]["pages"]:
            item = {"subject": page["slug"], "content": page["text"], "origin": page["origin"],
                    "source_sha256": page["text_sha256"], "content_sha256": page["text_sha256"]}
            item["version_sha256"] = live_tests.version_digest(item)
            intake["pages"].append(item)
        intake["current_versions"] = [page["version_sha256"] for page in intake["pages"]]
        intake["observations"] = []
        source.kw["expected_intake_sha256"] = live_tests.digest(intake)
        self.live_arguments = source.kw
        self.capture = live.prepare_pulse(**source.kw)["history_capture"]

    def call(self, **overrides):
        with self.fixture.fixture._pure():
            return measurement.prepare_live_history(**{
                "replay_inputs": self.replay, "live_capture": self.capture,
                "expected_live_capture_sha256": self.capture["capture_sha256"], **overrides})

    def test_replays_raw_binding_and_preserves_all_rows_without_answer_fields(self):
        before = copy.deepcopy((self.replay, self.capture))
        result = self.call()
        self.assertEqual(result["schema"], "sia-cognitive-live-history-plan-v1")
        self.assertEqual(result["status"], "computed-unverified")
        self.assertEqual(result["baseline_sha256"], self.replay["expected_baseline_sha256"])
        raw = self.replay["baseline"]["observation"]["query"]["payload"]["results"]
        for query, original in zip(result["queries"], raw, strict=True):
            self.assertEqual(query["id"], original["id"])
            self.assertEqual([row["raw_row"] for row in query["rows"]], original["rows"])
            self.assertNotIn("answer_key", query)
            self.assertNotIn("class", query)
            for row in query["rows"]:
                self.assertEqual(row["availability"], "complete-within-controller-epoch")
                self.assertEqual(row["history"]["trace"]["uses"], [])
        self.assertEqual((self.replay, self.capture), before)
        self.assertEqual(result["plan_sha256"], live_tests.own_digest(result, "plan_sha256"))

    def test_rehashed_raw_chunk_mutation_is_refused(self):
        changed = copy.deepcopy(self.replay)
        changed["baseline"]["observation"]["query"]["payload"]["results"][0]["rows"][0]["chunk_text"] = "invented"
        changed["baseline"]["artifact_sha256"] = live_tests.own_digest(changed["baseline"], "artifact_sha256")
        changed["expected_baseline_sha256"] = changed["baseline"]["artifact_sha256"]
        with self.assertRaises(measurement.MeasurementRefusal):
            self.call(replay_inputs=changed)

    def test_encoding_use_keeps_controller_clock_in_bound_raw_candidate(self):
        intake = self.live_arguments["intake"]
        slug = self.replay["baseline"]["observation"]["query"]["payload"]["results"][0]["rows"][0]["slug"]
        page = next(page for page in intake["pages"] if page["subject"] == slug)
        intake["observations"] = [{"id": "synthetic-encoding-" + str(index), "timestamp": stamp,
            "version_sha256": page["version_sha256"], "symbol": symbol, "context": "aegis",
            "native_timestamp": "1900-01-01T00:00:00Z"}
            for index, (stamp, symbol) in enumerate(zip(live_tests.PERCEPTION_TIMES,
                ("outcome", "outcome", "intent", "outcome"), strict=True))]
        self.live_arguments["expected_intake_sha256"] = live_tests.digest(intake)
        self.capture = live.prepare_pulse(**self.live_arguments)["history_capture"]
        result = self.call()
        history = result["queries"][0]["rows"][0]["history"]
        self.assertTrue(history["uses"])
        self.assertEqual(history["uses"], self.capture["uses"])
        observations = {row["id"]: row for row in intake["observations"]}
        for use in history["uses"]:
            self.assertEqual(use["timestamp"], observations[use["record_id"]]["timestamp"])
            self.assertEqual(use["kind"], "encoding-admitted")

    def test_heldout_capture_must_be_declared_in_parameter_freeze(self):
        heldout = exposure_tests.CognitiveEventExposure(methodName="runTest")
        heldout.setUp()
        self.addCleanup(heldout.doCleanups)
        heldout._inputs(split="heldout")
        with self.assertRaisesRegex(measurement.MeasurementRefusal, "heldout freeze"):
            self.call(replay_inputs=heldout.kw["replay_inputs"])

    def test_missing_page_keeps_raw_candidate_with_unavailable_history(self):
        self.capture["intake"]["pages"] = []
        self.capture["intake"]["current_versions"] = []
        self.capture["capture_sha256"] = live_tests.own_digest(self.capture, "capture_sha256")
        result = self.call()
        for query in result["queries"]:
            self.assertTrue(query["rows"])
            for row in query["rows"]:
                self.assertEqual(row["availability"], "exact-version-not-captured")
                self.assertIsNone(row["history"])

    def test_ambiguous_source_versions_refuse_instead_of_selecting_first(self):
        page = copy.deepcopy(self.capture["intake"]["pages"][0])
        page["source_sha256"] = "0" * 64
        page["version_sha256"] = live_tests.version_digest(page)
        self.capture["intake"]["pages"].append(page)
        self.capture["capture_sha256"] = live_tests.own_digest(self.capture, "capture_sha256")
        with self.assertRaises(measurement.MeasurementRefusal):
            self.call()
