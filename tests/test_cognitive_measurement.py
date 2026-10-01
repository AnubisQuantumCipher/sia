"""Frozen occurrence-target measurement plans, not executed cognitive scores.

The only runtime doubles are the already admitted baseline fixture. Pure new
APIs may not open files, invoke engines, or execute JACKAL. Root schedules tests.

Primary definitions: Stanford IR book, evaluation of unranked retrieval sets
and ranked retrieval results; TREC9 QA Track Scoring Metric. Occurrence targets
and exact canonical support chunks are an explicit engineering adaptation.

Fixture arithmetic routed to JACKAL, status=exact, formal=false:
parsed=1/2 exact=1/2; parsed=0/2 exact=0; parsed=2/2 exact=1;
parsed=1/1 exact=1; parsed=0/1 exact=0;
parsed=(1/2+1/1)/2 exact=3/4; parsed=(0+1)/2 exact=1/2;
parsed=(1/2+1/3)/2 exact=5/12;
parsed=5+1 exact=6; parsed=2048+2048 exact=4096.
Nonclaims: NOT formal-bounded: this lane carries no Lean-checked certificate;
The epistemic class above is the STRONGEST claim this result supports;
exact rational arithmetic (not yet checker-covered).
These fixture receipts do not assure the implementation or future data.
"""

import contextlib
import copy
import importlib
from pathlib import Path
import unittest
from unittest import mock

from tests import test_cognitive_baseline as baseline_tests
from tests import test_cognitive_selection as selection_tests
from tests import test_raw_vector_admission as raw_tests
from tests import test_raw_vector_prepare_admission as prepare_tests


sha = baseline_tests.sha
canonical = baseline_tests.canonical
body_digest = baseline_tests._body_digest
NON_CLAIMS = [
    "This plan contains unevaluated JACKAL requests, not arithmetic assurance, significance, or a cognitive win.",
    "Occurrence recall and first-any-target reciprocal rank are engineering adaptations, not document relevance or semantic-answer correctness.",
    "Recency contrast support is eligibility evidence, not an answer target; repetition targets remain the complete signed occurrence roster.",
    "First-any-target reciprocal rank does not establish that all repetition targets were retrieved or answered.",
    "Target credit requires the selected canonical support chunk and exact native excerpt; alternate copies and slug matches receive no credit.",
    "Queries are generated signed-history tasks with chain/raw-subject group dependence and shared pages, not independent population samples.",
    "Per-class query means do not establish class balance, statistical power, a temporal holdout, or machine-wide cognitive mechanisms.",
    "Pinned protocol and parameter-freeze identities declare chronology; they do not independently prove when tuning or result inspection occurred.",
    "Artifact replay checks represented consistency, not current archive bytes, historical process truth, loaded code, or resident memory.",
    "Source origins and every retained raw latency value remain controlling; arithmetic cannot promote model-origin text into evidence.",
    "Unavailable classes remain unavailable and source selection exclusions are not converted into zero-valued observations.",
    "All capture, selection, baseline, model, build, and raw-adapter nonclaims remain controlling.",
]


def policy_fixture():
    """Declared protocol choices, frozen without reference to retrieval output."""
    return {
        "schema": "sia-cognitive-retrieval-policy-v1", "cutoffs": [1, 2, 5],
        "targets": "signed-answer-occurrences-v1",
        "matching": "exact-selected-source-chunk-and-native-excerpt-v1",
        "recall": "distinct-target-union-at-k-v1",
        "reciprocal_rank": "first-any-target-row-at-k-v1",
        "aggregation": "macro-query-within-class-v1",
        "duplicates": "refuse-invalid-raw-roster-v1",
        "origins": "preserve-source-labels-no-promotion-v1",
        "missing": "zero-hit-no-denominator-shrink-v1",
        "dependence": "chain-raw-subject-groups-and-shared-pages-v1",
        "chronology": "externally-pinned-before-heldout-v1",
    }


class CognitiveMeasurement(unittest.TestCase):
    setUp = baseline_tests.CognitiveBaseline.setUp
    _capture = baseline_tests.CognitiveBaseline._capture
    _build = baseline_tests.CognitiveBaseline._build
    _baseline_inputs = baseline_tests.CognitiveBaseline._inputs
    _contract = baseline_tests.CognitiveBaseline._contract
    _freeze = baseline_tests.CognitiveBaseline._freeze
    _queries = baseline_tests.CognitiveBaseline._queries
    _model_identity = baseline_tests.CognitiveBaseline._model_identity
    _process_generation = baseline_tests.CognitiveBaseline._process_generation
    _serving = baseline_tests.CognitiveBaseline._serving
    _prepare = baseline_tests.CognitiveBaseline._prepare
    _observe = baseline_tests.CognitiveBaseline._observe
    _controls = baseline_tests.CognitiveBaseline._controls
    _run = baseline_tests.CognitiveBaseline._run
    _signed_rows = selection_tests.CognitiveSelection._signed_rows
    _resign_fixture = selection_tests.CognitiveSelection._resign_fixture
    _source = selection_tests.CognitiveSelection._source

    def _measurement_module(self):
        try:
            module = importlib.import_module("siacognitivemeasure")
        except ModuleNotFoundError as exc:
            self.fail("frozen cognitive measurement API must exist: " + str(exc))
        for name in ("build_protocol", "prepare_measurement"):
            self.assertTrue(callable(getattr(module, name, None)), name)
        self.assertTrue(hasattr(module, "MeasurementRefusal"))
        return module

    def _inputs(self, split="calibration"):
        self._baseline_inputs(importlib.import_module("siacognitivebaseline"), split)
        metric_policy = policy_fixture()
        self.pk = {
            **{key: copy.deepcopy(self.kw[key]) for key in (
                "capture", "expected_capture_sha256", "selection_policy", "expected_policy_sha256",
                "selection", "expected_selection_sha256")},
            "baseline_contract": self._contract(),
            "expected_baseline_contract_sha256": sha(canonical(self._contract())),
            "metric_policy": metric_policy,
            "expected_metric_policy_sha256": sha(canonical(metric_policy)),
        }

    @contextlib.contextmanager
    def _pure(self):
        with mock.patch("builtins.open", side_effect=AssertionError("pure measurement opened a path")), \
                mock.patch("os.open", side_effect=AssertionError("pure measurement opened a descriptor")), \
                mock.patch("os.scandir", side_effect=AssertionError("pure measurement enumerated files")), \
                mock.patch("subprocess.run", side_effect=AssertionError("pure measurement launched a child")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("pure measurement launched a child")), \
                mock.patch.object(self.module.runner, "prepare_bound", side_effect=AssertionError("measurement prepared index")), \
                mock.patch.object(self.module.runner, "observe_bound", side_effect=AssertionError("measurement queried engine")):
            yield

    def _protocol(self, module):
        with self._pure():
            return module.build_protocol(**self.pk)

    def _answers(self, klass, subject="wireplumber.service"):
        group = selection_tests.group_id("aegis", subject)
        return [row for row in self.kw["selection"]["answer_key"]
                if row["class"] == klass and row["group_id"] == group]

    def _rows(self, choices):
        pages = {row["slug"]: row for row in self.kw["selection"]["pages"]}
        rows = []
        for identity, (slug, index) in enumerate(choices, 1):
            page = pages[slug]
            rows.append(raw_tests._row(
                slug=slug, title=page["title"], type=page["type"],
                page_id=identity, chunk_id=identity, chunk_index=index,
                chunk_text=prepare_tests._chunks(page["text"])[index]))
        return rows

    def _baseline(self, protocol, choices=None, *, latency=False):
        if self.kw["split"] == "heldout":
            freeze = self._freeze()
            freeze["parameters"]["measurement_protocol_sha256"] = protocol["protocol_sha256"]
            freeze["parameters_sha256"] = sha(canonical(freeze["parameters"]))
            freeze["freeze_sha256"] = body_digest(freeze, "freeze_sha256")
            self.kw["expected_parameter_freeze_sha256"] = freeze["freeze_sha256"]

        def observe(**kwargs):
            value = self._observe(**kwargs)
            for result in value["query"]["payload"]["results"]:
                selected = [] if choices is None else choices.get(result["id"], [])
                raw_tests._bind_rows(result, self._rows(selected))
                if latency:
                    # Deliberately supplied producer measurements, not computed
                    # timing conversions or scores.
                    result["latency_ms"] = {"embedding": 1.25, "search": 2.5}
            if latency:
                value["query"]["payload"]["latency_ms"] = {"total": 7.75}
                value["capture"]["payload"]["latency_ms"] = {"total": 3.25}
                value["query"]["elapsed_ms"] = 9.5
                value["capture"]["elapsed_ms"] = 4.5
            # This double deliberately uses canonical JSON as its synthetic
            # wire encoding. Refresh its digest after editing rows/timings;
            # the original helper hash described the pre-edit payload. Real
            # stdout digests remain opaque and must never be reconstructed by
            # the measurement implementation from parsed producer JSON.
            for operation in ("capture", "query"):
                value[operation]["stdout_sha256"] = sha(canonical(value[operation]["payload"]))
            return value

        with self._controls(observe=observe):
            return self._run()

    def _measure(self, module, protocol, baseline, **overrides):
        kwargs = {
            **self.pk, "protocol": protocol,
            "expected_protocol_sha256": protocol["protocol_sha256"],
            "baseline": baseline, "expected_baseline_sha256": baseline["artifact_sha256"],
            "expected_parameter_freeze_sha256": self.kw["expected_parameter_freeze_sha256"],
        }
        kwargs.update(overrides)
        with self._pure():
            return module.prepare_measurement(**kwargs)

    def _query(self, plan, identifier):
        return next(row for row in plan["queries"] if row["id"] == identifier)

    def _cutoff(self, plan, identifier, k):
        return next(row for row in self._query(plan, identifier)["cutoffs"] if row["k"] == k)

    def _request(self, plan, kind, identifier, metric, k):
        matches = [row for row in plan["jackal_requests"]
                   if row["scope"] == {"kind": kind, "id": identifier}
                   and row["metric"] == metric and row["k"] == k]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["tool"], "jackal_exact")
        self.assertEqual(set(matches[0]["arguments"]), {"expression"})
        return matches[0]

    def _rehash_baseline(self, value):
        value["artifact_sha256"] = body_digest(value, "artifact_sha256")
        return value

    def test_public_frozen_protocol_and_measurement_request_apis_exist(self):
        self._measurement_module()

    def test_protocol_is_constructible_before_results_pure_detached_and_pinned(self):
        module = self._measurement_module()
        self._inputs()
        before = copy.deepcopy(self.pk)
        self.assertIsNone(self.prepared_result)
        self.assertIsNone(self.observed_result)
        self.assertFalse(Path(self.kw["output_directory"]).exists())
        result = self._protocol(module)
        repeated = self._protocol(module)
        self.assertEqual(result, repeated)
        self.assertEqual(self.pk, before)
        self.assertIsNot(result, repeated)
        self.assertEqual(set(result), {
            "schema", "capture_sha256", "policy_sha256", "selection_sha256", "pages_sha256",
            "baseline_contract_sha256", "metric_policy_sha256", "metric_policy",
            "groups", "queries", "coverage", "exclusions", "source_non_claims", "non_claims",
            "protocol_sha256"})
        self.assertEqual(result["schema"], "sia-cognitive-retrieval-protocol-v1")
        self.assertEqual(result["protocol_sha256"], body_digest(result, "protocol_sha256"))
        self.assertEqual(result["baseline_contract_sha256"], self.pk["expected_baseline_contract_sha256"])
        self.assertEqual(result["metric_policy_sha256"], self.pk["expected_metric_policy_sha256"])
        self.assertEqual(result["metric_policy"], self.pk["metric_policy"])
        self.assertEqual(result["groups"], self.kw["selection"]["groups"])
        self.assertEqual(result["coverage"], self.kw["selection"]["coverage"])
        self.assertEqual(result["exclusions"], self.kw["selection"]["exclusions"])
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        result["metric_policy"]["cutoffs"].clear()
        self.assertEqual(self.pk, before)
        self.assertNotEqual(result, repeated)

    def test_recency_targets_only_latest_repetition_all_and_novelty_first_occurrence(self):
        module = self._measurement_module()
        self._inputs()
        result = self._protocol(module)
        for klass in ("recency-heavy", "repetition-heavy", "novelty"):
            answer = self._answers(klass)[0]
            query = self._query(result, answer["id"])
            self.assertEqual(query["class"], klass)
            self.assertEqual(query["group_id"], answer["group_id"])
            self.assertEqual(query["action"], answer["action"])
            self.assertEqual(query["answer_kind"], answer["answer"]["kind"])
            self.assertEqual(query["scope"], answer["scope"])
            self.assertEqual(query["eligibility_support"], answer["support"])
            self.assertEqual([row["occurrence"]["seq"] for row in query["targets"]],
                             answer["answer"]["sequences"])
        recency = self._query(result, self._answers("recency-heavy")[0]["id"])
        self.assertEqual([row["occurrence"]["seq"] for row in recency["targets"]], ["2"])
        self.assertEqual({row["seq"] for row in recency["eligibility_support"]}, {"1", "2"})
        repetition = self._query(result, self._answers("repetition-heavy")[0]["id"])
        self.assertEqual([row["occurrence"]["seq"] for row in repetition["targets"]], ["1", "2"])
        novelty = self._query(result, self._answers("novelty")[0]["id"])
        self.assertEqual([row["occurrence"]["seq"] for row in novelty["targets"]], ["1"])

    def test_every_target_joins_exact_signed_occurrence_and_original_source_bytes(self):
        module = self._measurement_module()
        self._inputs()
        result = self._protocol(module)
        pages = {row["slug"]: row for row in self.kw["selection"]["pages"]}
        events = {(row["chain"], row["seq"]): row for row in self.kw["capture"]["events"]}
        for query in result["queries"]:
            for target in query["targets"]:
                self.assertEqual(set(target), {"occurrence", "witness"})
                occurrence, witness = target["occurrence"], target["witness"]
                self.assertEqual(set(occurrence), {"chain", "seq", "entry_hash"})
                event = events[(occurrence["chain"], occurrence["seq"])]
                self.assertEqual(occurrence["entry_hash"], event["entry_hash"])
                support = next(row for row in query["eligibility_support"]
                               if row["seq"] == occurrence["seq"] and row["chain"] == occurrence["chain"])
                page = pages[support["slug"]]
                chunk = prepare_tests._chunks(page["text"])[support["chunk_index"]].encode("utf-8")
                self.assertEqual(witness, {
                    "slug": support["slug"], "origin": page["origin"],
                    "page_text_sha256": page["text_sha256"], "excerpt": support["excerpt"],
                    "excerpt_sha256": sha(support["excerpt"].encode("utf-8")),
                    "chunk_index": support["chunk_index"], "chunk_sha256": sha(chunk)})
                self.assertIn(witness["excerpt"].encode("utf-8"), chunk)

    def test_protocol_external_source_contract_and_metric_policy_pins_are_required(self):
        module = self._measurement_module()
        self._inputs()
        for field in ("expected_capture_sha256", "expected_policy_sha256", "expected_selection_sha256",
                      "expected_baseline_contract_sha256", "expected_metric_policy_sha256"):
            for wrong in (None, "0" * 64, True):
                kwargs = {**self.pk, field: wrong}
                with self.subTest(field=field, wrong=wrong), self._pure(), \
                        self.assertRaises(module.MeasurementRefusal):
                    module.build_protocol(**kwargs)

    def test_rehashed_selection_answers_and_occurrence_ids_cannot_replace_source_replay(self):
        module = self._measurement_module()
        self._inputs()
        for member, replacement in (("answer", {"kind": "first-occurrence", "value": "forged", "sequences": ["5"]}),
                                    ("support", [])):
            kwargs = copy.deepcopy(self.pk)
            kwargs["selection"]["answer_key"][0][member] = replacement
            kwargs["selection"]["selection_sha256"] = body_digest(kwargs["selection"], "selection_sha256")
            kwargs["expected_selection_sha256"] = kwargs["selection"]["selection_sha256"]
            kwargs["baseline_contract"]["selection_sha256"] = kwargs["expected_selection_sha256"]
            kwargs["expected_baseline_contract_sha256"] = sha(canonical(kwargs["baseline_contract"]))
            with self.subTest(member=member), self._pure(), self.assertRaises(module.MeasurementRefusal):
                module.build_protocol(**kwargs)

    def test_policy_is_closed_and_rejects_wrong_types_cutoffs_and_denominator_switches(self):
        module = self._measurement_module()
        self._inputs()
        cases = [("cutoffs", []), ("cutoffs", [True]), ("cutoffs", [0]),
                 ("cutoffs", [2, 1]), ("cutoffs", [1, 1]), ("cutoffs", [6]),
                 ("cutoffs", [1.0]), ("cutoffs", "1"), ("targets", "slug"),
                 ("matching", "any-excerpt-copy"), ("aggregation", "pooled-occurrences"),
                 ("missing", "drop-missing-targets"), ("winner_threshold", 0.5)]
        for field, replacement in cases:
            kwargs = copy.deepcopy(self.pk)
            kwargs["metric_policy"][field] = replacement
            kwargs["expected_metric_policy_sha256"] = sha(canonical(kwargs["metric_policy"]))
            with self.subTest(field=field, replacement=replacement), self._pure(), \
                    self.assertRaises(module.MeasurementRefusal):
                module.build_protocol(**kwargs)

    def test_bounded_structure_refuses_before_copy_or_json_serialization(self):
        module = self._measurement_module()
        self._inputs()
        cyclic = policy_fixture()
        cyclic["cutoffs"] = cyclic
        for malformed in (cyclic, {"cutoffs": float("inf")}, {"cutoffs": float("nan")}):
            kwargs = {**self.pk, "metric_policy": malformed}
            with self._pure(), mock.patch("copy.deepcopy", side_effect=AssertionError("copied malformed input")), \
                    mock.patch("json.dumps", side_effect=AssertionError("serialized malformed input")), \
                    self.assertRaises(module.MeasurementRefusal):
                module.build_protocol(**kwargs)

    def test_old_recency_contrast_does_not_count_but_ranked_latest_does(self):
        module = self._measurement_module()
        self._inputs()
        protocol = self._protocol(module)
        answer = self._answers("recency-heavy")[0]
        support = {row["seq"]: row for row in answer["support"]}
        choices = [(support[seq]["slug"], support[seq]["chunk_index"]) for seq in ("1", "2")]
        baseline = self._baseline(protocol, {answer["id"]: choices})
        plan = self._measure(module, protocol, baseline)
        first, second = self._cutoff(plan, answer["id"], 1), self._cutoff(plan, answer["id"], 2)
        self.assertEqual(first["target_count"], 1)
        self.assertEqual(first["retrieved_target_count"], 0)
        self.assertIsNone(first["first_target_rank"])
        self.assertEqual(second["retrieved_target_count"], 1)
        self.assertEqual(second["first_target_rank"], 2)
        self.assertEqual(self._request(plan, "query", answer["id"], "recall_at_k", 1)["arguments"],
                         {"expression": "0/1"})
        self.assertEqual(self._request(plan, "query", answer["id"], "reciprocal_rank_at_k", 2)["arguments"],
                         {"expression": "1/2"})
        self.assertEqual(self._query(plan, answer["id"])["row_coverage"][0]["target_occurrences"], [])

    def test_repetition_denominator_is_complete_and_missing_occurrences_are_not_dropped(self):
        module = self._measurement_module()
        self._inputs()
        protocol = self._protocol(module)
        answer = self._answers("repetition-heavy")[0]
        support = answer["support"][0]
        baseline = self._baseline(protocol, {answer["id"]: [(support["slug"], support["chunk_index"])]})
        plan = self._measure(module, protocol, baseline)
        cutoff = self._cutoff(plan, answer["id"], 5)
        self.assertEqual(cutoff["target_count"], 2)
        self.assertEqual(cutoff["retrieved_target_count"], 1)
        self.assertEqual(cutoff["first_target_rank"], 1)
        self.assertEqual(self._request(plan, "query", answer["id"], "recall_at_k", 5)["arguments"],
                         {"expression": "1/2"})
        self.assertEqual(self._request(plan, "query", answer["id"], "reciprocal_rank_at_k", 5)["arguments"],
                         {"expression": "1/1"})
        self.assertIn(NON_CLAIMS[3], plan["non_claims"])

    def test_one_exact_chunk_can_cover_distinct_signed_occurrences_without_row_count_credit(self):
        module = self._measurement_module()
        rows = self._signed_rows()
        rows[2][1] = "2026-01-01T02:00:00Z"
        self._resign_fixture(rows)
        self._inputs()
        protocol = self._protocol(module)
        answer = self._answers("repetition-heavy")[0]
        support = answer["support"]
        self.assertEqual({(row["slug"], row["chunk_index"]) for row in support},
                         {(support[0]["slug"], support[0]["chunk_index"])})
        self.assertEqual([row["seq"] for row in support], ["1", "2"])
        baseline = self._baseline(protocol, {answer["id"]: [(support[0]["slug"], support[0]["chunk_index"])]})
        plan = self._measure(module, protocol, baseline)
        cutoff = self._cutoff(plan, answer["id"], 1)
        self.assertEqual(cutoff["retrieved_target_count"], 2)
        self.assertEqual(cutoff["target_count"], 2)
        self.assertEqual(self._request(plan, "query", answer["id"], "recall_at_k", 1)["arguments"],
                         {"expression": "2/2"})
        self.assertEqual(len(self._query(plan, answer["id"])["row_coverage"]), 1)
        self.assertEqual({row["seq"] for row in cutoff["covered_occurrences"]}, {"1", "2"})

    def test_same_slug_wrong_valid_chunk_gets_no_credit(self):
        module = self._measurement_module()
        source = self._source()
        source.write_bytes(source.read_bytes() + b"\n" + b"x" * 4096)
        self._inputs()
        protocol = self._protocol(module)
        answer = self._answers("novelty")[0]
        support = answer["support"][0]
        page = next(row for row in self.kw["selection"]["pages"] if row["slug"] == support["slug"])
        chunks = prepare_tests._chunks(page["text"])
        other_index = next(index for index, chunk in enumerate(chunks) if support["excerpt"] not in chunk)
        self.assertNotEqual(other_index, support["chunk_index"])
        baseline = self._baseline(protocol, {answer["id"]: [(page["slug"], other_index)]})
        plan = self._measure(module, protocol, baseline)
        self.assertEqual(self._cutoff(plan, answer["id"], 5)["retrieved_target_count"], 0)
        self.assertEqual(self._request(plan, "query", answer["id"], "reciprocal_rank_at_k", 5)["arguments"],
                         {"expression": "0"})

    def test_zero_hit_queries_remain_in_class_means_and_empty_classes_are_unavailable(self):
        module = self._measurement_module()
        self._inputs()
        protocol = self._protocol(module)
        baseline = self._baseline(protocol)
        plan = self._measure(module, protocol, baseline)
        query_classes = {row["class"] for row in baseline["answer_key"]}
        for klass in plan["classes"]:
            expected = [row["id"] for row in plan["queries"] if row["class"] == klass["class"]]
            self.assertEqual(klass["query_ids"], expected)
            self.assertEqual(klass["group_ids"], sorted({row["group_id"] for row in plan["queries"]
                                                       if row["class"] == klass["class"]}))
            if klass["class"] not in query_classes:
                self.assertEqual(klass["status"], "unavailable")
                self.assertTrue(klass["reason"])
                if klass["class"] == "associative-multi-hop":
                    self.assertEqual(klass["reason"], "no-witnessed-multi-hop-targets")
                if klass["class"] == "consolidation-gist":
                    self.assertEqual(klass["reason"], "no-witnessed-gist-facts")
                self.assertFalse(any(row["scope"] == {"kind": "class", "id": klass["class"]}
                                     for row in plan["jackal_requests"]))
            else:
                self.assertEqual(klass["status"], "prepared-for-jackal")
                for k in self.pk["metric_policy"]["cutoffs"]:
                    request = self._request(plan, "class", klass["class"], "mrr_at_k", k)
                    self.assertEqual(request["query_ids"], expected)
                    self.assertEqual(request["arguments"]["expression"],
                                     "(" + "+".join("(0)" for _ in expected) + ")/" + str(len(expected)))
        self.assertEqual({row["class"] for row in plan["classes"]}, set(selection_tests.CLASSES))
        self.assertEqual({row["id"] for row in plan["queries"]}, {row["id"] for row in baseline["queries"]})

    def test_requests_are_unevaluated_query_and_class_scoped_not_local_float_metrics(self):
        module = self._measurement_module()
        self._inputs()
        protocol = self._protocol(module)
        baseline = self._baseline(protocol)
        plan = self._measure(module, protocol, baseline)
        self.assertEqual(plan["schema"], "sia-cognitive-measurement-plan-v1")
        self.assertEqual(plan["status"], "prepared-for-jackal")
        self.assertEqual(plan["arithmetic_status"], "not-evaluated")
        self.assertEqual(plan["plan_sha256"], body_digest(plan, "plan_sha256"))
        self.assertEqual(plan["protocol_sha256"], protocol["protocol_sha256"])
        self.assertEqual(plan["baseline_sha256"], baseline["artifact_sha256"])
        self.assertEqual(plan["baseline_contract_sha256"], self.pk["expected_baseline_contract_sha256"])
        self.assertEqual(plan["query_roster_sha256"], baseline["query_roster_sha256"])
        for request in plan["jackal_requests"]:
            self.assertEqual(request["tool"], "jackal_exact")
            self.assertRegex(request["arguments"]["expression"], r"^[0-9+()/]+$")
            self.assertNotIn("result", request)
            self.assertNotIn("status", request)
            self.assertIn(request["scope"]["kind"], ("query", "class"))
        for forbidden in ("win", "significance", "p_value", "confidence_interval", "overall_score", "metrics"):
            self.assertNotIn(forbidden, plan)
        self.assertEqual(plan["non_claims"], NON_CLAIMS)

    def test_class_macro_keeps_each_query_denominator_and_raw_subject_groups(self):
        module = self._measurement_module()
        rows = self._signed_rows()
        for index in (3, 4):
            rows[index][2:5] = rows[5][2:5]
        self._resign_fixture(rows)
        self._inputs()
        protocol = self._protocol(module)
        answers = [self._answers("repetition-heavy", subject)[0]
                   for subject in ("wireplumber.service", "bluetooth.service")]
        self.assertEqual([len(row["answer"]["sequences"]) for row in answers], [2, 3])
        choices = {answer["id"]: [(answer["support"][0]["slug"], answer["support"][0]["chunk_index"])]
                   for answer in answers}
        baseline = self._baseline(protocol, choices)
        plan = self._measure(module, protocol, baseline)
        klass = next(row for row in plan["classes"] if row["class"] == "repetition-heavy")
        self.assertEqual(set(klass["query_ids"]), {row["id"] for row in answers})
        self.assertEqual(set(klass["group_ids"]), {row["group_id"] for row in answers})
        expressions = []
        for identifier in klass["query_ids"]:
            expression = self._request(plan, "query", identifier, "recall_at_k", 1)["arguments"]["expression"]
            expressions.append(expression)
        self.assertEqual(set(expressions), {"1/2", "1/3"})
        request = self._request(plan, "class", "repetition-heavy", "recall_at_k", 1)
        self.assertEqual(request["query_ids"], klass["query_ids"])
        self.assertEqual(request["arguments"]["expression"],
                         "(" + "+".join("(" + item + ")" for item in expressions) + ")/2")

    def test_model_origin_and_all_raw_latency_measurements_survive_without_promotion(self):
        module = self._measurement_module()
        source = self._source()
        source.write_bytes(source.read_bytes().replace(b"---\n", b"---\norigin: model\n", 1))
        self._inputs()
        protocol = self._protocol(module)
        answer = self._answers("novelty")[0]
        support = answer["support"][0]
        baseline = self._baseline(protocol, {answer["id"]: [(support["slug"], support["chunk_index"])]}, latency=True)
        before = copy.deepcopy((self.pk, protocol, baseline))
        plan = self._measure(module, protocol, baseline)
        self.assertEqual((self.pk, protocol, baseline), before)
        self.assertEqual(plan["baseline"], baseline)
        self.assertIsNot(plan["baseline"], baseline)
        self.assertEqual(plan["protocol"], protocol)
        query = self._query(plan, answer["id"])
        self.assertEqual(query["targets"][0]["witness"]["origin"], "model")
        self.assertEqual(query["row_coverage"][0]["origin"], "model")
        self.assertEqual(plan["baseline"]["observation"]["query"]["elapsed_ms"], 9.5)
        self.assertEqual(plan["source_non_claims"], {
            "protocol": protocol["non_claims"], "baseline": baseline["non_claims"],
            "history": baseline["source_non_claims"]})

    def test_baseline_and_protocol_pins_are_external_not_learned_from_artifacts(self):
        module = self._measurement_module()
        self._inputs()
        protocol = self._protocol(module)
        baseline = self._baseline(protocol)
        for field in ("expected_baseline_sha256", "expected_protocol_sha256", "expected_baseline_contract_sha256"):
            with self.subTest(field=field), self.assertRaises(module.MeasurementRefusal):
                self._measure(module, protocol, baseline, **{field: "0" * 64})

    def test_rehashed_target_protocol_cannot_redefine_targets_or_origin(self):
        module = self._measurement_module()
        self._inputs()
        protocol = self._protocol(module)
        baseline = self._baseline(protocol)
        for member in ("occurrence", "witness", "eligibility_support", "targets"):
            changed = copy.deepcopy(protocol)
            query = changed["queries"][0]
            if member == "occurrence":
                query["targets"][0][member]["entry_hash"] = "0" * 64
            elif member == "witness":
                query["targets"][0][member]["origin"] = "model" if query["targets"][0][member]["origin"] != "model" else "evidence"
            else:
                query[member] = []
            changed["protocol_sha256"] = body_digest(changed, "protocol_sha256")
            with self.subTest(member=member), self.assertRaises(module.MeasurementRefusal):
                self._measure(module, changed, baseline)

    def test_rehashed_baseline_answer_key_pages_and_labels_do_not_replace_source_replay(self):
        module = self._measurement_module()
        self._inputs()
        protocol = self._protocol(module)
        answer = self._answers("novelty")[0]
        support = answer["support"][0]
        baseline = self._baseline(protocol, {answer["id"]: [(support["slug"], support["chunk_index"])]})
        for field in ("answer_key", "pages", "retrieval_rows", "queries", "source_non_claims"):
            changed = copy.deepcopy(baseline)
            if field == "answer_key":
                # Genesis is never an answer target, whichever seeded query
                # happens to be first in the fixture roster.
                self.assertNotEqual(changed[field][0]["answer"]["sequences"], ["0"])
                changed[field][0]["answer"]["sequences"] = ["0"]
            elif field == "pages":
                page = changed[field][0]
                page["text"] += "\nforged replacement"
                page["text_sha256"] = sha(page["text"].encode())
            elif field == "retrieval_rows":
                row = next(item for query in changed[field] for item in query["rows"])
                row["origin"] = "model" if row["origin"] != "model" else "evidence"
            elif field == "queries":
                changed[field][0]["text"] += " forged"
                changed["query_roster_sha256"] = sha(canonical(changed[field]))
            else:
                changed[field] = {}
            self._rehash_baseline(changed)
            with self.subTest(field=field), self.assertRaises(module.MeasurementRefusal):
                self._measure(module, protocol, changed)

    def test_rehashed_raw_rows_wrong_bytes_boolean_index_and_duplicate_rows_refuse(self):
        module = self._measurement_module()
        self._inputs()
        protocol = self._protocol(module)
        answer = self._answers("novelty")[0]
        support = answer["support"][0]
        baseline = self._baseline(protocol, {answer["id"]: [(support["slug"], support["chunk_index"])]})
        for field, replacement in (("chunk_text", "forged exact-looking answer"), ("chunk_index", True),
                                   ("slug", "events/foreign/source"), ("title", "foreign title"),
                                   ("chunk_source", "model"), ("type", "foreign type"), ("duplicate", None)):
            changed = copy.deepcopy(baseline)
            query = next(row for row in changed["observation"]["query"]["payload"]["results"] if row["id"] == answer["id"])
            rows = copy.deepcopy(query["rows"])
            if field == "duplicate":
                rows.append(copy.deepcopy(rows[0]))
            else:
                rows[0][field] = replacement
            raw_tests._bind_rows(query, rows)
            self._rehash_baseline(changed)
            with self.subTest(field=field), self.assertRaises(module.MeasurementRefusal):
                self._measure(module, protocol, changed)

    def test_complete_raw_query_roster_and_producer_identity_replay_are_required(self):
        module = self._measurement_module()
        self._inputs()
        protocol = self._protocol(module)
        baseline = self._baseline(protocol)
        for field in ("missing-query", "query-order", "wire-binding", "capture-root", "model-process", "preparation-pages"):
            changed = copy.deepcopy(baseline)
            query = changed["observation"]["query"]
            if field == "missing-query":
                query["payload"]["results"].pop()
            elif field == "query-order":
                query["payload"]["results"].reverse()
            elif field == "wire-binding":
                query["payload"]["bindings"]["request_sha256"] = "0" * 64
            elif field == "capture-root":
                changed["observation"]["capture"]["payload"]["bindings"]["logical_sha256"] = "0" * 64
            elif field == "model-process":
                del query["model_serving"]["serving_generation"]["service"]
            else:
                changed["preparation"]["preparation"]["payload"]["pages"].pop()
            self._rehash_baseline(changed)
            with self.subTest(field=field), self.assertRaises(module.MeasurementRefusal):
                self._measure(module, protocol, changed)

    def test_archive_manifest_roster_replay_is_required_without_reopening_archive(self):
        module = self._measurement_module()
        self._inputs()
        protocol = self._protocol(module)
        baseline = self._baseline(protocol)
        for mutation in ("wrong-hash", "alias", "link", "duplicate"):
            changed = copy.deepcopy(baseline)
            manifest = changed["archive"]["manifest"]
            if mutation == "wrong-hash":
                changed["archive"]["manifest_sha256"] = "0" * 64
            else:
                if mutation == "alias":
                    manifest[0]["path"] = "../outside"
                elif mutation == "link":
                    manifest[0]["type"] = "symlink"
                else:
                    manifest.append(copy.deepcopy(manifest[0]))
                digest = sha(canonical(manifest))
                changed["archive"]["manifest_sha256"] = digest
                for operation in ("capture", "query"):
                    changed["observation"][operation]["physical_manifest_sha256"] = digest
            self._rehash_baseline(changed)
            with self.subTest(mutation=mutation), self.assertRaises(module.MeasurementRefusal):
                self._measure(module, protocol, changed)

    def test_heldout_requires_external_parameter_freeze_binding_this_protocol(self):
        module = self._measurement_module()
        self._inputs("heldout")
        protocol = self._protocol(module)
        baseline = self._baseline(protocol)
        plan = self._measure(module, protocol, baseline)
        self.assertEqual(plan["split"], "heldout")
        self.assertEqual(plan["parameter_freeze_sha256"], baseline["parameter_freeze_sha256"])
        self.assertEqual({row["id"] for row in plan["queries"]},
                         {row["id"] for row in self.kw["selection"]["queries"] if row["split"] == "heldout"})
        for pin in (None, "0" * 64):
            with self.subTest(pin=pin), self.assertRaises(module.MeasurementRefusal):
                self._measure(module, protocol, baseline, expected_parameter_freeze_sha256=pin)
        for replacement in (None, "0" * 64):
            changed = copy.deepcopy(baseline)
            freeze = changed["parameter_freeze"]
            if replacement is None:
                del freeze["parameters"]["measurement_protocol_sha256"]
            else:
                freeze["parameters"]["measurement_protocol_sha256"] = replacement
            freeze["parameters_sha256"] = sha(canonical(freeze["parameters"]))
            freeze["freeze_sha256"] = body_digest(freeze, "freeze_sha256")
            changed["parameter_freeze_sha256"] = freeze["freeze_sha256"]
            self._rehash_baseline(changed)
            with self.subTest(replacement=replacement), self.assertRaises(module.MeasurementRefusal):
                self._measure(module, protocol, changed, expected_parameter_freeze_sha256=freeze["freeze_sha256"])

    def test_changed_protocol_after_heldout_freeze_cannot_be_retrofitted(self):
        module = self._measurement_module()
        self._inputs("heldout")
        original = self._protocol(module)
        baseline = self._baseline(original)
        self.pk["metric_policy"]["cutoffs"] = [1]
        self.pk["expected_metric_policy_sha256"] = sha(canonical(self.pk["metric_policy"]))
        changed = self._protocol(module)
        self.assertNotEqual(original["protocol_sha256"], changed["protocol_sha256"])
        with self.assertRaises(module.MeasurementRefusal):
            self._measure(module, changed, baseline)


if __name__ == "__main__":
    unittest.main()
