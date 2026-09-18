"""Checkpoint bootstrap preserves the admitted whole-history projection."""

import copy
import importlib
import unittest
from unittest import mock

from tests import test_event_live_intake as fixtures
from tests.test_history_block import digest
from tests import test_live_loop as live_tests


class EventCheckpoint(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("siaeventcheckpoint")
        self.case = fixtures.EventLiveIntakeProjection(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def bootstrap(self):
        request = self.case.request()
        return request, self.api.bootstrap(vars(self.case.lib), request=request,
                                           expected_request_sha256=digest(request))

    def test_bootstrap_preserves_intake_and_first_associations_without_raw_prefix(self):
        request, checkpoint = self.bootstrap()
        projection = self.case.project(request)
        self.assertEqual(checkpoint["intake"], projection["intake"])
        self.assertNotIn("history", checkpoint)
        self.assertNotIn("entries", checkpoint)
        self.assertEqual(checkpoint["prefix_history_sha256"], request["expected_history_sha256"])
        self.assertEqual(checkpoint["source_non_claims"], projection["source_non_claims"])
        self.assertEqual(self.api.admit(vars(self.case.lib), checkpoint=checkpoint,
                                       expected_checkpoint_sha256=digest(checkpoint)), checkpoint)

    def test_wrong_request_pin_and_changed_full_history_refuse(self):
        request = self.case.request()
        with self.assertRaises(ValueError):
            self.api.bootstrap(vars(self.case.lib), request=request, expected_request_sha256="a" * 64)
        request["history"]["entries"][0]["source_returns"]["complete"] = False
        with self.assertRaises(ValueError):
            self.api.bootstrap(vars(self.case.lib), request=request,
                               expected_request_sha256=digest(request))

    def test_resealed_checkpoint_cannot_omit_observation_index_or_duplicate_batch(self):
        request, checkpoint = self.bootstrap()
        for change in ("first", "batches", "origin", "nonclaims"):
            candidate = copy.deepcopy(checkpoint)
            if change == "first":
                candidate["first_associations"].clear()
            elif change == "batches":
                candidate["seen_batch_ids"].append(candidate["seen_batch_ids"][0])
            elif change == "origin":
                candidate["intake"]["pages"][0]["origin"] = "invented"
            else:
                candidate["non_claims"].clear()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.api.admit(vars(self.case.lib), checkpoint=candidate,
                               expected_checkpoint_sha256=digest(candidate))

    def test_repeated_events_keep_original_observation_and_unique_first_index(self):
        first = self.case.entry({"sense_custom:alpha": [self.case.event()]})
        self.case.publish_entry_fixture(first)
        later = self.case.entry({"sense_custom:alpha": [self.case.event("2026-01-07")]},
                                stamp=live_tests.DELIVERED_AT, batch_id="checkpoint-repeat")
        request = self.case.request([first, later])
        checkpoint = self.api.bootstrap(vars(self.case.lib), request=request,
                                        expected_request_sha256=digest(request))
        initial = self.case.project(self.case.request([first]))
        self.assertEqual(checkpoint["intake"]["observations"], initial["intake"]["observations"])
        self.assertEqual([row["observation_id"] for row in checkpoint["first_associations"]],
                         [row["id"] for row in initial["intake"]["observations"]])

    def test_admission_detects_input_mutation_during_detachment(self):
        request, checkpoint = self.bootstrap()
        pin = digest(checkpoint)
        original = self.api.json.loads

        def changing(raw):
            result = original(raw)
            checkpoint["non_claims"].clear()
            return result

        with mock.patch.object(self.api.json, "loads", side_effect=changing):
            with self.assertRaises(ValueError):
                self.api.admit(vars(self.case.lib), checkpoint=checkpoint,
                               expected_checkpoint_sha256=pin)

    def test_owner_document_ceiling_precedes_serialization(self):
        request, checkpoint = self.bootstrap()
        pin = digest(checkpoint)
        owner = {**vars(self.case.lib), "MAX_STATE_JSON_BYTES": 256}
        with mock.patch.object(self.api.json, "dumps", side_effect=AssertionError("oversized serialization")):
            with self.assertRaises(ValueError):
                self.api.admit(owner, checkpoint=checkpoint, expected_checkpoint_sha256=pin)
