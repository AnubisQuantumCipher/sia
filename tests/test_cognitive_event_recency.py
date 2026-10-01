"""A new event-time task, not a reinterpretation of frozen outcome recency.

Every capture is built from the existing private signed-ledger fixture. No
actual captured history, heldout queries, answers, or results are inspected.
Root alone runs this file. Selection/measurement calls are pure; any baseline
execution below uses the pre-existing isolated fixture doubles only.

Native timestamps are retained as original UTC strings, not converted to
Unix seconds in expected results. The civil-date ordering fixtures were
routed before writing; their exact-given class does not certify clock times.
"""

import copy
import importlib
import unittest
from unittest import mock

from tests import test_cognitive_selection as selected_tests
from tests import test_cognitive_measurement as measured_tests


sha = selected_tests.sha
canonical = selected_tests.canonical
POLICY_SCHEMA = "sia-cognitive-selection-policy-v2"
SELECTION_SCHEMA = "sia-cognitive-selection-v2"
TEMPLATES = "signed-history-event-recency-v2"
ANSWER_KIND = "latest-event-time-occurrence"
RECENCY = {
    "population": "complete-chain-exact-action-raw-subject-v1",
    "time": "canonical-native-event-time-utc-v1",
    "target": "unique-maximum-event-time-v1",
    "contrast": "nearest-strictly-older-global-v1",
    "contrast_ties": "highest-signed-sequence-v1",
    "page_relation": "distinct-target-contrast-source-pages-v1",
    "witnesses": "target-and-contrast-required-no-substitution-v1",
}
DATE_GIVEN = {
    "datum": "calendar convention", "calendar": "proleptic Gregorian",
    "day_length": "one civil day, NOT 86400 SI seconds",
    "excludes": "timezones, DST transitions, leap seconds",
    "source": "Python datetime.date proleptic-Gregorian calendar semantics",
    "as_of": "JACKAL measurement definition 1.1.0 (this convention is not time-varying)",
}
DATE_ROUTES = [
    {"parsed": "diff(2026-01-01 -> 2026-01-02)", "status": "exact-given", "exact_days": "1",
     "delegated": {"parsed": "739618-739617", "status": "exact", "exact": "1"}},
    {"parsed": "diff(2026-01-02 -> 2026-01-03)", "status": "exact-given", "exact_days": "1",
     "delegated": {"parsed": "739619-739618", "status": "exact", "exact": "1"}},
]
DATE_CONSEQUENCE_CEILING = "informational"
DATE_NON_CLAIMS = [
    "Civil-date arithmetic ONLY: no timezone, no DST, no leap seconds, no wall-clock times",
    "A civil day is not a fixed number of seconds; do not convert this result to seconds by multiplying by 86400 unless that assumption is stated",
    "Dates before the 1582 Gregorian adoption are interpreted proleptic Gregorianly and will NOT match historical Julian records",
    "`exact-given` is NOT a weaker `exact`: the day count is exact under the declared calendar convention",
    "The JACKAL measurement orchestrator is identity-pinned but remains outside the Lean certificate chain",
    "The measurement orchestrator performs no arithmetic of its own: every arithmetic result here was produced by a delegated JACKAL runtime call recorded in `delegated_to`; library metadata such as calendar ordinals, collection counts, and lexical offsets is not an arithmetic claim",
    "The epistemic class above is the STRONGEST claim this result supports",
]
EXACT_ROUTES = [
    {"parsed": "2+1", "status": "exact", "exact": "3"},
    {"parsed": "1/1", "status": "exact", "exact": "1"},
    {"parsed": "0/1", "status": "exact", "exact": "0"},
]
EXACT_NON_CLAIMS = [
    "NOT formal-bounded: this lane carries no Lean-checked certificate",
    "The epistemic class above is the STRONGEST claim this result supports",
    "exact rational arithmetic (not yet checker-covered)",
]


def policy_fixture():
    value = selected_tests.policy_fixture()
    value["schema"] = POLICY_SCHEMA
    value["queries"].update(templates=TEMPLATES, recency=copy.deepcopy(RECENCY))
    return value


def event_rows(fixture):
    """Declared inputs: sequence order opposes native event-time order."""
    rows = fixture._signed_rows()
    by_sequence = {row[0]: row for row in rows}
    earliest = by_sequence["1"][1]
    middle = by_sequence["2"][1]
    latest = by_sequence["3"][1]
    for sequence, stamp in (("1", latest), ("2", middle), ("3", earliest)):
        by_sequence[sequence][1:5] = [stamp, "CHECK:unit", "wireplumber.service", "steady"]
    fixture._resign_fixture(rows)
    return rows


class EventTimeRecencySelection(unittest.TestCase):
    def setUp(self):
        self.fx = selected_tests.CognitiveSelection(methodName="runTest")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.module = importlib.import_module("siacognitiveselect")
        self.rows = event_rows(self.fx)
        self.by_sequence = {row[0]: row for row in self.rows}

    def _capture(self):
        return self.fx._capture()

    def _select(self, *, capture=None, policy=None):
        capture = self._capture() if capture is None else capture
        policy = policy_fixture() if policy is None else policy
        with mock.patch("builtins.open", side_effect=AssertionError("selection opened a path")), \
                mock.patch("os.open", side_effect=AssertionError("selection opened a descriptor")), \
                mock.patch("subprocess.run", side_effect=AssertionError("selection launched a child")):
            return self.fx._select(self.module, capture, policy)

    def _recency(self, selection):
        return self.fx._answers(selection, "recency-heavy")

    def _excluded(self):
        result = self._select()
        self.assertEqual(self._recency(result), [])
        exclusions = [item for item in result["exclusions"]
                      if item["class"] == "recency-heavy"
                      and item["group_id"] == selected_tests.group_id("aegis", "wireplumber.service")]
        self.assertTrue(exclusions, "an unavailable event-time task needs an explicit exclusion")
        self.assertTrue(all(type(item["reason"]) is str and item["reason"] for item in exclusions))
        return result

    def test_new_policy_explicitly_admits_timestamp_recency_without_outcome_or_value_change(self):
        capture, policy = self._capture(), policy_fixture()
        before = copy.deepcopy((capture, policy))
        result = self._select(capture=capture, policy=policy)
        self.assertEqual(result["schema"], SELECTION_SCHEMA)
        answers = self._recency(result)
        self.assertEqual([row["answer"]["kind"] for row in answers], [ANSWER_KIND])
        answer = answers[0]
        self.assertEqual(answer["action"], "CHECK:unit")
        self.assertEqual(answer["answer"], {
            "kind": ANSWER_KIND, "value": self.by_sequence["1"][1], "sequences": ["1"]})
        self.assertEqual({item["seq"] for item in answer["support"]}, {"1", "2"})
        self.assertNotEqual(*[item["slug"] for item in answer["support"]])
        question = next(row["text"] for row in result["queries"] if row["id"] == answer["id"])
        self.assertIn("event-time", question)
        self.assertNotIn("latest recorded outcome", question.casefold())
        self.assertNotIn("Use signed sequence order", question)
        self.assertEqual((capture, policy), before)
        self.assertEqual(result, self.fx._admit(self.module, result, capture, policy))

    def test_v1_artifact_and_group_split_are_not_rewritten_by_v2(self):
        capture = self._capture()
        v1_policy = selected_tests.policy_fixture()
        v1_before = self._select(capture=capture, policy=v1_policy)
        encoded = canonical(v1_before)
        v2 = self._select(capture=capture)
        self.assertEqual(canonical(self._select(capture=capture, policy=v1_policy)), encoded)
        self.assertEqual(v1_before["schema"], "sia-cognitive-selection-v1")
        self.assertEqual(v1_before["non_claims"], selected_tests.NON_CLAIMS)
        self.assertEqual(self._recency(v1_before), [])
        self.assertEqual(v2["groups"], v1_before["groups"])
        self.assertEqual(v2["pages"], v1_before["pages"])
        self.assertEqual(v2["pages_sha256"], v1_before["pages_sha256"])
        for statement in selected_tests.NON_CLAIMS:
            if statement != "Latest recorded outcome follows signed sequence order, not necessarily event-time chronology.":
                self.assertIn(statement, v2["non_claims"])
        self.assertNotIn("Latest recorded outcome follows signed sequence order, not necessarily event-time chronology.", v2["non_claims"])

    def test_v2_rule_map_is_closed_and_cannot_be_smuggled_under_v1(self):
        capture = self._capture()
        self._select(capture=capture)  # Establish v2 support before negative cases.
        variants = []
        for key in RECENCY:
            missing = policy_fixture()
            del missing["queries"]["recency"][key]
            variants.append(missing)
            changed = policy_fixture()
            changed["queries"]["recency"][key] = "unreviewed-rule"
            variants.append(changed)
        extra = policy_fixture()
        extra["queries"]["recency"]["fallback"] = "nearest-retained"
        variants.append(extra)
        variants.append({**policy_fixture(), "schema": "sia-cognitive-selection-policy-v1"})
        no_map = policy_fixture()
        del no_map["queries"]["recency"]
        variants.append(no_map)
        for value in variants:
            with self.subTest(policy=value), self.assertRaises(self.module.SelectionRefusal):
                self._select(capture=capture, policy=value)

    def test_equal_maximum_native_timestamps_exclude_instead_of_using_sequence_tie_break(self):
        self.by_sequence["2"][1] = self.by_sequence["1"][1]
        self.fx._resign_fixture(self.rows)
        self._excluded()

    def test_single_occurrence_has_no_invented_older_contrast(self):
        for sequence in ("2", "3"):
            self.by_sequence[sequence][3] = "different-" + sequence + ".service"
        self.fx._resign_fixture(self.rows)
        self._excluded()

    def test_nearest_older_same_page_is_not_skipped_for_a_farther_cross_page_witness(self):
        self.by_sequence["1"][1] = "2026-01-02T02:00:00Z"
        self.fx._resign_fixture(self.rows)
        # The farther row remains on a different day/page and is retained.
        capture = self._capture()
        events = {row["seq"]: row for row in capture["events"]}
        self.assertEqual(events["1"]["retention"]["source_slug"], events["2"]["retention"]["source_slug"])
        self.assertNotEqual(events["1"]["retention"]["source_slug"], events["3"]["retention"]["source_slug"])
        self._excluded()

    def test_unretained_true_latest_is_not_replaced_by_the_latest_retained_subset(self):
        self.fx._replace_marker_with_split_decoys("1")
        capture = self._capture()
        events = {row["seq"]: row for row in capture["events"]}
        self.assertEqual(events["1"]["retention"]["status"], "no-admitted-witness")
        self.assertEqual(events["2"]["retention"]["status"], "retained")
        self.assertEqual(events["3"]["retention"]["status"], "retained")
        self._excluded()

    def test_nearest_older_without_a_location_or_witness_is_not_skipped(self):
        self.fx._replace_marker_with_split_decoys("2")
        capture = self._capture()
        events = {row["seq"]: row for row in capture["events"]}
        self.assertEqual(events["2"]["retention"]["status"], "no-admitted-witness")
        self.assertIsNone(events["2"]["retention"]["source_slug"])
        self.assertEqual(events["3"]["retention"]["status"], "retained")
        self._excluded()

    def test_older_timestamp_ties_use_declared_highest_sequence_before_witness_checks(self):
        self.by_sequence["3"][1] = self.by_sequence["2"][1]
        self.fx._resign_fixture(self.rows)
        selected = self._select()
        answer = self._recency(selected)[0]
        self.assertEqual(answer["answer"]["sequences"], ["1"])
        self.assertEqual({row["seq"] for row in answer["support"]}, {"1", "3"})
        self.fx._replace_marker_with_split_decoys("3")
        self._excluded()

    def test_required_recency_remains_a_refusal_when_v2_has_no_eligible_task(self):
        self.by_sequence["2"][1] = self.by_sequence["1"][1]
        self.fx._resign_fixture(self.rows)
        policy = policy_fixture()
        policy["required_classes"] = ["recency-heavy"]
        with self.assertRaises(self.module.SelectionRefusal):
            self._select(policy=policy)

    def test_raw_page_bytes_and_origins_survive_event_time_selection(self):
        source = self.fx._source("2026-01-03")
        original = source.read_bytes().replace(b"---\n", b"---\norigin: model\n", 1)
        original += "\r\nOriginal Ω尾 bytes.\r\n".encode("utf-8")
        source.write_bytes(original)
        capture = self._capture()
        result = self._select(capture=capture)
        captured = {row["slug"]: row for row in capture["pages"]}
        for page in result["pages"]:
            self.assertEqual(page["text"], captured[page["slug"]]["text"])
            self.assertEqual(page["origin"], captured[page["slug"]]["origin"])
            self.assertEqual(page["text_sha256"], captured[page["slug"]]["sha256"])
        target = next(page for page in result["pages"] if page["slug"] == "events/aegis/2026-01-03")
        self.assertEqual(target["text"].encode("utf-8"), original)
        self.assertEqual(target["origin"], "model")

    def test_projected_timestamp_disagreement_refuses_even_after_capture_rehash(self):
        capture = self._capture()
        self._select(capture=capture)
        changed = copy.deepcopy(capture)
        event = next(row for row in changed["events"] if row["seq"] == "1")
        event["projection"]["event_time_utc"] = self.by_sequence["2"][1]
        changed["capture_sha256"] = sha(canonical({key: value for key, value in changed.items()
                                                   if key != "capture_sha256"}))
        with self.assertRaises(self.module.SelectionRefusal):
            self._select(capture=changed)

    def test_noncanonical_native_timestamp_in_an_older_unretained_row_is_not_ignored(self):
        # The existing native parser accepts this date spelling, while the
        # new event-time task explicitly requires canonical UTC row text.
        # Keep the row in the complete signed population even without a page
        # witness; selecting only the available newer rows must not excuse it.
        self.by_sequence["3"][1] = "2026-1-01T01:00:00Z"
        self.fx._resign_fixture(self.rows)
        self.fx._replace_marker_with_split_decoys("3")
        capture = self._capture()
        event = next(row for row in capture["events"] if row["seq"] == "3")
        self.assertEqual(event["row"][1], self.by_sequence["3"][1])
        self.assertEqual(event["retention"]["status"], "no-admitted-witness")
        with self.assertRaises(self.module.SelectionRefusal):
            self._select(capture=capture)


class EventTimeRecencyMeasurement(unittest.TestCase):
    def setUp(self):
        self.fx = measured_tests.CognitiveMeasurement(methodName="runTest")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.rows = event_rows(self.fx)

    def _configure(self, *, v2=True):
        self.fx._inputs()
        if v2:
            policy = policy_fixture()
            policy["split"] = copy.deepcopy(self.fx.kw["selection_policy"]["split"])
            selector = importlib.import_module("siacognitiveselect")
            capture = self.fx.kw["capture"]
            selected = selector.select_history(capture, expected_capture_sha256=capture["capture_sha256"],
                                               policy=policy, expected_policy_sha256=sha(canonical(policy)))
            self.fx.kw.update(selection_policy=policy, expected_policy_sha256=sha(canonical(policy)),
                              selection=selected, expected_selection_sha256=selected["selection_sha256"])
            self.fx.pk.update({key: copy.deepcopy(self.fx.kw[key]) for key in (
                "selection_policy", "expected_policy_sha256", "selection", "expected_selection_sha256")})
            contract = self.fx._contract()
            self.fx.pk.update(baseline_contract=contract, expected_baseline_contract_sha256=sha(canonical(contract)))
        return importlib.import_module("siacognitivemeasure")

    def test_v2_measurement_targets_unique_latest_occurrence_not_eligibility_contrast(self):
        module = self._configure()
        protocol = self.fx._protocol(module)
        answer = self.fx._answers("recency-heavy")[0]
        query = next(row for row in protocol["queries"] if row["id"] == answer["id"])
        self.assertEqual(query["answer_kind"], ANSWER_KIND)
        self.assertEqual([row["occurrence"]["seq"] for row in query["targets"]], ["1"])
        self.assertEqual({row["seq"] for row in query["eligibility_support"]}, {"1", "2"})
        witnesses = {row["seq"]: row for row in answer["support"]}
        old = witnesses["2"]
        observed = self.fx._baseline(protocol, {answer["id"]: [(old["slug"], old["chunk_index"])]})
        plan = self.fx._measure(module, protocol, observed)
        cutoff = self.fx._cutoff(plan, answer["id"], 1)
        self.assertEqual(cutoff["target_count"], 1)
        self.assertEqual(cutoff["retrieved_target_count"], 0)
        self.assertIsNone(cutoff["first_target_rank"])
        self.assertEqual(self.fx._request(plan, "query", answer["id"], "recall_at_k", 1)["arguments"],
                         {"expression": "0/1"})

    def test_v2_target_hit_keeps_exact_timestamp_occurrence_and_source_origin(self):
        module = self._configure()
        protocol = self.fx._protocol(module)
        answer = self.fx._answers("recency-heavy")[0]
        latest = next(row for row in answer["support"] if row["seq"] == "1")
        self.assertEqual(answer["answer"]["value"], self.rows[1][1])
        observed = self.fx._baseline(protocol, {answer["id"]: [(latest["slug"], latest["chunk_index"])]})
        plan = self.fx._measure(module, protocol, observed)
        cutoff = self.fx._cutoff(plan, answer["id"], 1)
        self.assertEqual(cutoff["target_count"], 1)
        self.assertEqual(cutoff["retrieved_target_count"], 1)
        self.assertEqual([row["seq"] for row in cutoff["covered_occurrences"]], ["1"])
        self.assertEqual(self.fx._request(plan, "query", answer["id"], "recall_at_k", 1)["arguments"],
                         {"expression": "1/1"})

    def test_new_answer_kind_cannot_reinterpret_a_rehashed_v1_selection(self):
        module = self._configure(v2=False)
        self.fx._protocol(module)
        changed = copy.deepcopy(self.fx.pk["selection"])
        item = next(row for row in changed["answer_key"] if row["class"] == "novelty")
        item["class"] = "recency-heavy"
        item["answer"]["kind"] = ANSWER_KIND
        changed["selection_sha256"] = sha(canonical({key: value for key, value in changed.items()
                                                      if key != "selection_sha256"}))
        self.fx.pk.update(selection=changed, expected_selection_sha256=changed["selection_sha256"])
        contract = self.fx.pk["baseline_contract"]
        contract["selection_sha256"] = changed["selection_sha256"]
        self.fx.pk["expected_baseline_contract_sha256"] = sha(canonical(contract))
        with self.assertRaises(module.MeasurementRefusal):
            self.fx._protocol(module)


if __name__ == "__main__":
    unittest.main()
