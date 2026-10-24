"""Owner-free association semantics and real replay callback ordering."""

import copy
import unittest
from unittest import mock

import siaeventintake as replay
from tests import test_event_live_intake as fixtures


def supplied_row():
    return {"source_returns_sha256": "returns-first", "source_id": "source-alpha",
            "return_index": 0, "event_id": "event-first", "semantic_id": "semantic-first",
            "admission": {"event_batch_sha256": "batch-first", "plan_sha256": "plan-first",
                          "slug": "events/first", "version_sha256": "version-first",
                          "disposition": "appended"}}


def first_candidate():
    return {"id": "observation-first", "timestamp": 100, "version_sha256": "version-first",
            "symbol": "source-alpha", "context": "controller-source-return",
            "native_timestamp": "2026-01-06T12:00:00Z"}


class AssociationDerivation(unittest.TestCase):
    def test_first_observation_preserves_every_supplied_field(self):
        row, candidate = supplied_row(), first_candidate()
        reason, observation, association = replay._derive_association(row, candidate, None)
        self.assertIsNone(reason)
        self.assertEqual(observation, candidate)
        self.assertIsNot(observation, candidate)
        self.assertEqual(association, {
            **row, "observation_id": candidate["id"],
            "observation_version_sha256": candidate["version_sha256"],
            "observation_timestamp": candidate["timestamp"], "status": "first-observation"})

    def test_repeat_keeps_original_observation_and_current_admission(self):
        row, first = supplied_row(), first_candidate()
        row.update(return_index=7, source_returns_sha256="later-returns")
        row["admission"].update(version_sha256="later-version", disposition="retained-day")
        reason, new, association = replay._derive_association(row, None, (row["semantic_id"], first))
        self.assertIsNone(reason)
        self.assertIsNone(new)
        self.assertEqual(association, {
            **row, "observation_id": "observation-first",
            "observation_version_sha256": "version-first",
            "observation_timestamp": 100, "status": "already-observed"})

    def test_conflict_returns_no_update_and_changes_no_inputs(self):
        row, prior = supplied_row(), ("different-semantic", first_candidate())
        before = copy.deepcopy((row, prior))
        self.assertEqual(replay._derive_association(row, None, prior),
                         ("repeated-source-association-conflict", None, None))
        self.assertEqual((row, prior), before)

    def test_missing_first_candidate_refuses_without_partial_result(self):
        row = supplied_row()
        before = copy.deepcopy(row)
        self.assertEqual(replay._derive_association(row, None, None),
                         ("missing-first-observation", None, None))
        self.assertEqual(row, before)

    def test_results_do_not_alias_admitted_scalar_records(self):
        row, candidate = supplied_row(), first_candidate()
        original = copy.deepcopy((row, candidate))
        _reason, observation, association = replay._derive_association(row, candidate, None)
        self.assertEqual((row, candidate), original)
        observation["timestamp"] = 999
        association["admission"]["slug"] = "changed-result"
        self.assertEqual((row, candidate), original)
        row["admission"]["version_sha256"] = "changed-input"
        candidate["id"] = "changed-input"
        self.assertEqual(association["admission"]["version_sha256"], "version-first")
        self.assertEqual(observation["id"], "observation-first")

    def test_repeat_is_deterministic_and_leaves_prior_unchanged(self):
        row, prior = supplied_row(), ("semantic-first", first_candidate())
        before = copy.deepcopy((row, prior))
        one = replay._derive_association(row, None, prior)
        two = replay._derive_association(copy.deepcopy(row), None, copy.deepcopy(prior))
        self.assertEqual(one, two)
        self.assertEqual((row, prior), before)


class AssociationReplayOrdering(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.EventLiveIntakeProjection(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def project_and_record_identities(self, request):
        identities = []
        original = replay._sha

        def observed(owner, value):
            if type(value) is dict and value.get("schema") == "sia-controller-event-association-v1":
                identities.append((value["source_id"], value["event_id"]))
            return original(owner, value)

        with mock.patch.object(replay, "_sha", observed):
            result = self.case.project(request)
        return result, identities

    def test_duplicate_and_cross_source_identity_calls_keep_original_order(self):
        event = self.case.event()
        entry = self.case.entry({"sense_custom:alpha": [event, event],
                                 "sense_custom:beta": [event]})
        result, calls = self.project_and_record_identities(self.case.request([entry]))
        event_id = self.case.lib.event_memory_identity(event)
        self.assertEqual(calls, [("sense_custom:alpha", event_id), ("sense_custom:beta", event_id)])
        self.assertEqual([row["status"] for row in result["associations"]],
                         ["first-observation", "already-observed", "first-observation"])
        self.assertEqual([row["symbol"] for row in result["intake"]["observations"]],
                         ["sense_custom:alpha", "sense_custom:beta"])

    def test_later_entry_does_not_rehash_or_replace_first_observation(self):
        first = self.case.entry({"sense_custom:alpha": [self.case.event()]})
        self.case.publish_entry_fixture(first)
        later = self.case.entry({"sense_custom:alpha": [self.case.event("2026-01-07")]},
                                stamp=fixtures.live_tests.DELIVERED_AT, batch_id="later-source-return")
        original = self.case.project(self.case.request([first]))
        result, calls = self.project_and_record_identities(self.case.request([first, later]))
        event_id = first["source_returns"]["runs"][0]["events"][0]["event_id"]
        self.assertEqual(calls, [("sense_custom:alpha", event_id)])
        self.assertEqual(result["intake"]["observations"], original["intake"]["observations"])
        self.assertEqual([row["status"] for row in result["associations"]],
                         ["first-observation", "already-observed"])


if __name__ == "__main__":
    unittest.main()
