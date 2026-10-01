"""Explicit origin-slot-preserving recall composition, before CLI wiring.

Root owns all executions. Original row order is the caller's independently
admitted origin-weighted hybrid/PPR premise; this pure component does not
recompute or prove that earlier weighting. The new literal preserves that
order's origin slots and uses the real activation component only within each
origin. No gain, invented activation score, source rewrite or earned cognitive
claim is added. The old activation-only literal remains unchanged.

Clock and policy fixtures are reused from the frozen pure-loop suite. These
tests assert permutations, identities and causal inequalities, not new numeric
score or duration oracles.
"""

import copy
import importlib
import unittest

from tests import test_delivery_journal as journal_tests
from tests import test_live_loop as loop_tests


ORIGIN_SLOTS = "origin-slot-preserving-activation-v1"
OLD_ORDER = "activation-desc-stable-input-v1"


class LiveLoopOriginSlots(unittest.TestCase):
    def setUp(self):
        self.live = importlib.import_module("sialiveloop")
        self.fixture = loop_tests.LiveLoopPureIntegration(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture._inputs()

    def configure(self, order):
        policy = copy.deepcopy(self.fixture.policy)
        policy["recall_order"] = order
        self.fixture.policy = policy
        self.fixture.kw.update(policy=policy, expected_policy_sha256=loop_tests.digest(policy))

    def origin_sequence(self, ranked, refs):
        pages = {page["version_sha256"]: page for page in ranked["versions"]}
        rows = {row["row_ref"]: row for row in ranked["rows"]}
        return [pages[rows[ref]["version_sha256"]]["origin"] for ref in refs]

    def assert_plan(self, ranked, rows):
        self.assertEqual(ranked["rows"], rows)
        self.assertEqual(ranked["rows_sha256"], loop_tests.digest(rows))
        self.assertEqual(ranked["rank_sha256"], loop_tests.own_digest(ranked, "rank_sha256"))
        self.assertEqual(ranked["policy"], self.fixture.policy)
        self.assertEqual(ranked["policy_sha256"], loop_tests.digest(self.fixture.policy))
        self.assertEqual(ranked["non_claims"], loop_tests.NON_CLAIMS)
        self.assertEqual(sorted(ranked["order"]), sorted(row["row_ref"] for row in rows))
        self.assertEqual(self.origin_sequence(ranked, ranked["order"]),
                         self.origin_sequence(ranked, [row["row_ref"] for row in rows]))

    def test_old_activation_only_policy_keeps_its_existing_cross_origin_order(self):
        self.assertEqual(self.fixture.policy["recall_order"], OLD_ORDER)
        before = copy.deepcopy(self.fixture.kw)
        prepared = self.fixture._prepare(self.live)
        rows = self.fixture._rows()
        ranked = self.fixture._rank(self.live, prepared, rows=rows)
        self.assertEqual(ranked["policy"]["recall_order"], OLD_ORDER)
        self.assertEqual(self.fixture.kw, before)
        self.assertEqual(ranked["rows"], rows)
        self.assertNotEqual(ranked["order"], [row["row_ref"] for row in rows])
        self.assertEqual(self.origin_sequence(ranked, ranked["order"])[0], "model")
        self.assertNotEqual(self.origin_sequence(ranked, ranked["order"]),
                            self.origin_sequence(ranked, [row["row_ref"] for row in rows]))

    def test_stronger_model_activation_cannot_move_model_across_an_origin_slot(self):
        self.configure(ORIGIN_SLOTS)
        prepared = self.fixture._prepare(self.live)
        rows = self.fixture._rows()
        before = copy.deepcopy(rows)
        ranked = self.fixture._rank(self.live, prepared, rows=rows)
        self.assert_plan(ranked, rows)
        self.assertEqual(rows, before)
        strongest_subject = ranked["activation"]["order"][0]
        strongest = next(page for page in ranked["versions"] if page["subject"] == strongest_subject)
        self.assertEqual(strongest["origin"], "model")
        self.assertEqual(ranked["order"], [row["row_ref"] for row in rows],
                         "all evidence slots remain stable and the model stays in its original slot")

    def test_same_origin_completed_use_changes_order_without_changing_any_origin_slot(self):
        self.configure(ORIGIN_SLOTS)
        first = self.fixture._prepare(self.live)
        rows = self.fixture._rows()
        original = copy.deepcopy(rows)
        before = self.fixture._rank(self.live, first, rows=rows)
        evidence = [ref for ref in before["order"]
                    if self.origin_sequence(before, [ref]) == ["evidence"]]
        target = evidence[-1]
        record = self.fixture._delivery(self.live, before, refs=[target], body=b"explicit evidence recall\n")
        resumed = self.fixture._prepare(
            self.live, **self.fixture._resume(first, observed_at=loop_tests.DELIVERED_AT),
            **self.fixture._with_delivery(record))
        after = self.fixture._rank(self.live, resumed, rows=rows, observed_at=loop_tests.DELIVERED_AT)
        self.assert_plan(after, rows)
        self.assertEqual(rows, original)
        self.assertNotEqual(after["order"], before["order"])
        self.assertLess(after["order"].index(target), after["order"].index(evidence[0]))
        self.assertEqual(self.origin_sequence(after, after["order"]),
                         self.origin_sequence(before, before["order"]))

    def test_unavailable_and_equal_activation_preserve_base_row_ties_with_multiple_refs(self):
        self.configure(ORIGIN_SLOTS)
        intake = copy.deepcopy(self.fixture.kw["intake"])
        intake["observations"] = []
        for label in ("derived", "legacy-unlabeled"):
            text = "Original synthetic " + label + " source.\n"
            page = {"subject": "fixture/" + label, "content": text, "origin": label,
                    "source_sha256": loop_tests.digest({"fixture": label}),
                    "content_sha256": loop_tests.bytes_digest(text.encode("utf-8"))}
            page["version_sha256"] = loop_tests.version_digest(page)
            intake["pages"].append(page)
            intake["current_versions"].append(page["version_sha256"])
        self.fixture.kw.update(intake=intake, expected_intake_sha256=loop_tests.digest(intake))
        first = self.fixture._prepare(self.live)
        all_rows = self.fixture._rows()
        origins = {page["version_sha256"]: page["origin"] for page in intake["pages"]}
        evidence = [row for row in all_rows if origins[row["version_sha256"]] == "evidence"]
        model = next(row for row in all_rows if origins[row["version_sha256"]] == "model")
        derived = next(row for row in all_rows if origins[row["version_sha256"]] == "derived")
        legacy = next(row for row in all_rows if origins[row["version_sha256"]] == "legacy-unlabeled")
        other_ref = copy.deepcopy(evidence[0])
        other_ref["row_ref"] = "another-exact-version-chunk"
        other_ref["row"]["chunk_text"] = other_ref["row"]["chunk_text"].splitlines()[0]
        rows = [evidence[0], model, evidence[-1], other_ref, derived, legacy]
        base = [row["row_ref"] for row in rows]
        unavailable = self.fixture._rank(self.live, first, rows=rows)
        self.assert_plan(unavailable, rows)
        self.assertEqual(unavailable["order"], base)
        self.assertTrue(all(row["score"] is None for row in unavailable["activation"]["activations"]))
        self.assertEqual(set(self.origin_sequence(unavailable, base)),
                         {"evidence", "derived", "model", "legacy-unlabeled"})
        record = self.fixture._delivery(
            self.live, unavailable, refs=[evidence[0]["row_ref"], evidence[-1]["row_ref"]],
            body=b"same completed delivery gives these exact versions equal use times\n")
        resumed = self.fixture._prepare(
            self.live, **self.fixture._resume(first, observed_at=loop_tests.DELIVERED_AT),
            **self.fixture._with_delivery(record))
        tied = self.fixture._rank(self.live, resumed, rows=rows, observed_at=loop_tests.DELIVERED_AT)
        self.assert_plan(tied, rows)
        self.assertEqual(tied["order"], base,
                         "per-version ties must not regroup separated row refs or disturb row-level stability")

    def test_active_state_requires_its_exact_policy_not_a_relabelled_old_generation(self):
        old = self.fixture._prepare(self.live)
        self.configure(ORIGIN_SLOTS)
        with self.assertRaises(self.live.LiveLoopRefusal):
            self.fixture._rank(self.live, old)

    def test_origin_slots_use_admitted_versions_not_a_relabelled_result_row(self):
        self.configure(ORIGIN_SLOTS)
        prepared = self.fixture._prepare(self.live)
        rows = self.fixture._rows()
        model_versions = {page["version_sha256"] for page in prepared["state"]["intake"]["pages"]
                          if page["origin"] == "model"}
        next(row for row in rows if row["version_sha256"] in model_versions)["row"]["origin"] = "evidence"
        with self.assertRaises(self.live.LiveLoopRefusal):
            self.fixture._rank(self.live, prepared, rows=rows)

    def test_journal_completes_the_exact_origin_composed_plan_without_posthoc_reordering(self):
        self.configure(ORIGIN_SLOTS)
        prepared = self.fixture._prepare(self.live)
        rows = self.fixture._rows()
        ranked = self.fixture._rank(self.live, prepared, rows=rows)
        self.assert_plan(ranked, rows)
        journal = journal_tests.DeliveryJournal(methodName="runTest")
        self.addCleanup(journal.doCleanups)
        journal.setUp()
        refs = list(ranked["order"])
        by_ref = {row["row_ref"]: row for row in ranked["rows"]}
        body = loop_tests.canonical([by_ref[ref] for ref in refs]) + b"\n"
        journal.kw.update(ranked=ranked, expected_ranked_sha256=ranked["rank_sha256"],
                          emitted_row_refs=refs, output_utf8=body)
        reservation = journal._reserve()
        sink = journal_tests.ByteSink()
        completed = journal._deliver(reservation, sink=sink)
        self.assertEqual(bytes(sink.body), body)
        self.assertEqual(completed["record"], self.fixture._delivery(
            self.live, ranked, refs=refs, body=body, request_id=journal_tests.REQUEST_A))
        self.assertEqual(completed["record"]["rank_sha256"], ranked["rank_sha256"])
        self.assertEqual(completed["record"]["emitted_row_refs"], refs)
        self.assertEqual(completed["record"]["rows"], [by_ref[ref] for ref in refs])
        self.assertEqual(completed["record"]["non_claims"], loop_tests.NON_CLAIMS)
        self.assertEqual(journal._inspect()["records"], [completed["record"]])
