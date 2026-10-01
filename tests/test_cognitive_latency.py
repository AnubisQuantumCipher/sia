"""Unevaluated, provenance-bound latency requests for existing bound observations.

Root schedules execution. The new API is pure and may neither reopen evidence
nor call an engine or JACKAL. Retrieval-policy-v1 remains unchanged.

Fixture arithmetic routed through JACKAL, status=exact, formal=false:
parsed=(1.25+2.5)/2 exact=15/8; parsed=0/1 exact=0;
parsed=(1.0+2.0)/2 exact=3/2;
parsed=(1*10^-6+1*10^20)/2 exact=100000000000000000000000001/2000000.
Nonclaims: NOT formal-bounded: this lane carries no Lean-checked certificate;
The epistemic class above is the STRONGEST claim this result supports;
exact rational arithmetic (not yet checker-covered).
These are arithmetic fixture receipts, not physical-clock or code assurance.
"""

import copy
import importlib
import json
import unittest
from unittest import mock

from tests import test_cognitive_measurement as measurement_tests


sha = measurement_tests.sha
canonical = measurement_tests.canonical
body_digest = measurement_tests.body_digest
NON_CLAIMS = [
    "This plan contains unevaluated JACKAL requests, not arithmetic assurance, physical-clock accuracy, significance, or a cognitive win.",
    "Eventual exact arithmetic is conditional on supplied shortest-roundtrip JSON number text; it does not authenticate original wire tokens or physical durations.",
    "Embedding spans include vector validation and byte preparation; search spans include row normalization and canonical-row byte binding.",
    "Adapter operation totals include connection, snapshots, query loop and receipt work; they exclude prior request admission and later engine close.",
    "Operation totals are not per-query totals and are never allocated across queries or classes.",
    "The bound producer does not report per-query total, owned-model startup or warmup, preparation duration, or controller wall duration.",
    "Uncontracted diagnostic durations and unbound-controller wall measurements are retained but are not admitted latency samples.",
    "Class means use the same selected query roster, including zero samples; group dependence and shared pages do not establish independent sampling or statistical power.",
    "Source origins and model/build lineage are preserved; raw timing lineage does not establish CPU, model, machine, or cognitive comparisons.",
    "A pinned latency policy in the heldout parameter freeze declares chronology but does not independently prove when policy selection or result inspection occurred.",
    "Unavailable timing scopes and query classes are not assigned zero durations or fabricated component breakdowns.",
    "All retained measurement, retrieval, source, baseline, model, build, and raw-adapter nonclaims remain controlling.",
]
TIMING_CONTRACT = {
    "schema": "sia-raw-vector-timing-scope-v1",
    "producer": "raw-vector/adapter.ts:runRawVector", "clock": "performance.now", "unit": "ms",
    "query_embedding": "embed-start-through-validation-and-vector-bytes-before-search",
    "query_search": "search-start-through-normalization-and-row-byte-binding",
    "operation_total": "post-admission-through-connect-snapshots-query-loop-receipt-before-close",
}
UNAVAILABLE = [
    {"scope": "query", "component": "total", "reason": "not-reported-by-adapter-query-v1"},
    {"scope": "owned-model", "component": "startup", "reason": "not-reported-by-bound-model-v1"},
    {"scope": "owned-model", "component": "warmup", "reason": "not-reported-by-bound-model-v1"},
    {"scope": "preparation", "component": "total", "reason": "not-reported-by-bound-preparer-v1"},
    {"scope": "controller", "component": "wall", "reason": "not-reported-by-bound-controller-v1"},
]


def policy_fixture():
    return {
        "schema": "sia-cognitive-latency-policy-v1",
        "samples": "adapter-query-embedding-search-v1",
        "aggregation": "macro-query-within-class-v1",
        "numbers": "retained-json-roundtrip-decimal-as-given-v1",
        "units": "producer-ms-no-conversion-v1",
        "roster": "same-admitted-query-roster-v1",
        "missing": "refuse-sample-drop-v1",
        "operation_timings": "retain-separate-no-query-allocation-v1",
        "chronology": "externally-pinned-before-heldout-v1",
    }


class CognitiveLatency(unittest.TestCase):
    def setUp(self):
        # Compose the existing fixture rather than inherit its test methods.
        self.fixture = measurement_tests.CognitiveMeasurement(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def _module(self):
        try:
            module = importlib.import_module("siacognitivelatency")
        except ModuleNotFoundError as exc:
            self.fail("pure latency request preparation API must exist: " + str(exc))
        self.assertTrue(callable(getattr(module, "prepare_latency", None)))
        self.assertTrue(hasattr(module, "LatencyRefusal"))
        return module

    def _inputs(self, *, split="calibration", timings=None, total=100.0,
                diagnostics=False, include_latency_pin=True):
        fixture = self.fixture
        fixture._inputs(split)
        measurement = importlib.import_module("siacognitivemeasure")
        protocol = fixture._protocol(measurement)
        policy = policy_fixture()
        policy_sha = sha(canonical(policy))
        original_freeze, original_observe = fixture._freeze, fixture._observe

        def freeze_with_latency_policy():
            freeze = original_freeze()
            if include_latency_pin:
                freeze["parameters"]["latency_policy_sha256"] = policy_sha
                freeze["parameters_sha256"] = sha(canonical(freeze["parameters"]))
                freeze["freeze_sha256"] = body_digest(freeze, "freeze_sha256")
                fixture.kw["expected_parameter_freeze_sha256"] = freeze["freeze_sha256"]
            # The measurement fixture adds its retrieval-protocol pin and
            # rehashes before executing the baseline double, never afterward.
            return freeze

        def observe_with_reported_samples(**kwargs):
            value = original_observe(**kwargs)
            for index, row in enumerate(value["query"]["payload"]["results"]):
                row["latency_ms"] = ({"embedding": 1.25, "search": 2.5} if timings is None
                                     else timings(row["id"], index))
            value["query"]["payload"]["latency_ms"] = {"total": total}
            value["capture"]["payload"]["latency_ms"] = {"total": 3.25}
            if diagnostics:
                # Deliberately uncontracted extras. The complete artifact must
                # preserve them, but no timing policy may silently adopt them.
                value["query"]["elapsed_ms"] = 9.5
                value["query"]["wall_elapsed_ns"] = 1000
                value["capture"]["model_startup_ms"] = 7.5
            # The existing measurement fixture refreshes synthetic canonical
            # stdout bytes after its last row changes, before baseline admission.
            return value

        with mock.patch.object(fixture, "_freeze", side_effect=freeze_with_latency_policy), \
                mock.patch.object(fixture, "_observe", side_effect=observe_with_reported_samples):
            baseline = fixture._baseline(protocol)
        replay_inputs = {
            **fixture.pk, "protocol": protocol, "expected_protocol_sha256": protocol["protocol_sha256"],
            "baseline": baseline, "expected_baseline_sha256": baseline["artifact_sha256"],
            "expected_parameter_freeze_sha256": fixture.kw["expected_parameter_freeze_sha256"],
        }
        with fixture._pure():
            plan = measurement.prepare_measurement(**replay_inputs)
        self.kw = {
            "measurement_plan": plan, "expected_measurement_plan_sha256": plan["plan_sha256"],
            "replay_inputs": replay_inputs, "latency_policy": policy,
            "expected_latency_policy_sha256": policy_sha,
        }

    def _call(self, module, **overrides):
        with self.fixture._pure():
            return module.prepare_latency(**{**self.kw, **overrides})

    def _request(self, result, klass, component):
        rows = [row for row in result["jackal_requests"]
                if row["scope"] == {"kind": "class", "id": klass}
                and row["metric"] == "mean_" + component + "_ms"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tool"], "jackal_exact")
        self.assertEqual(set(rows[0]["arguments"]), {"expression"})
        return rows[0]

    def _rehashed_plan(self, plan):
        plan["plan_sha256"] = body_digest(plan, "plan_sha256")
        return plan

    def _bound_baseline_override(self, baseline):
        """Keep envelope pins consistent so raw-domain assertions are causal.

        Timing-only edits leave the retrieval sufficient statistics unchanged.
        This deliberately supplies a newly pinned but malformed raw observation;
        replay must reject its domain, not merely notice a stale outer selfhash.
        """
        baseline["artifact_sha256"] = body_digest(baseline, "artifact_sha256")
        replay = copy.deepcopy(self.kw["replay_inputs"])
        replay["baseline"] = baseline
        replay["expected_baseline_sha256"] = baseline["artifact_sha256"]
        plan = copy.deepcopy(self.kw["measurement_plan"])
        plan["baseline"] = baseline
        plan["baseline_sha256"] = baseline["artifact_sha256"]
        self._rehashed_plan(plan)
        return {"replay_inputs": replay, "measurement_plan": plan,
                "expected_measurement_plan_sha256": plan["plan_sha256"]}

    def test_public_pure_latency_preparation_api_exists(self):
        self._module()

    def test_detached_deterministic_plan_replays_sources_and_keeps_retrieval_policy_unchanged(self):
        module = self._module()
        self._inputs()
        before = copy.deepcopy(self.kw)
        result = self._call(module)
        repeated = self._call(module)
        self.assertEqual(self.kw, before)
        self.assertEqual(result, repeated)
        self.assertIsNot(result, repeated)
        self.assertEqual(result["schema"], "sia-cognitive-latency-plan-v1")
        self.assertEqual(result["status"], "prepared-for-jackal")
        self.assertEqual(result["arithmetic_status"], "not-evaluated")
        self.assertEqual(result["plan_sha256"], body_digest(result, "plan_sha256"))
        self.assertEqual(result["measurement_plan_sha256"], self.kw["expected_measurement_plan_sha256"])
        self.assertEqual(result["latency_policy_sha256"], self.kw["expected_latency_policy_sha256"])
        self.assertEqual(result["latency_policy"], self.kw["latency_policy"])
        self.assertEqual(result["measurement_plan"], self.kw["measurement_plan"])
        self.assertIsNot(result["measurement_plan"], self.kw["measurement_plan"])
        self.assertEqual(result["measurement_plan"]["protocol"]["metric_policy"], measurement_tests.policy_fixture())
        result["measurement_plan"]["queries"].clear()
        self.assertEqual(self.kw, before)

    def test_samples_preserve_exact_roster_numeric_type_units_and_given_source_pointers(self):
        module = self._module()
        self._inputs()
        result = self._call(module)
        measurement = self.kw["measurement_plan"]
        raw = measurement["baseline"]["observation"]["query"]["payload"]["results"]
        metadata = {row["id"]: row for row in measurement["queries"]}
        expected_order = [(row["id"], component) for row in raw for component in ("embedding", "search")]
        self.assertEqual([(row["query_id"], row["component"]) for row in result["query_samples"]], expected_order)
        for index, source in enumerate(raw):
            for component in ("embedding", "search"):
                sample = next(row for row in result["query_samples"]
                              if row["query_id"] == source["id"] and row["component"] == component)
                value = source["latency_ms"][component]
                self.assertEqual(set(sample), {"query_id", "class", "group_id", "component", "unit",
                                               "value", "json_number", "expression_literal", "given"})
                self.assertEqual(sample["class"], metadata[source["id"]]["class"])
                self.assertEqual(sample["group_id"], metadata[source["id"]]["group_id"])
                self.assertIs(type(sample["value"]), type(value))
                self.assertEqual(sample["value"], value)
                self.assertEqual(sample["unit"], "ms")
                self.assertEqual(sample["json_number"], json.dumps(value, allow_nan=False))
                self.assertEqual(sample["expression_literal"], sample["json_number"])
                self.assertEqual(sample["given"], {
                    "baseline_sha256": measurement["baseline_sha256"],
                    "source_pointer": f"/observation/query/payload/results/{index}/latency_ms/{component}",
                    "representation": "retained-json-number-shortest-roundtrip-v1", "unit": "ms"})
        self.assertEqual(result["query_roster_sha256"], measurement["query_roster_sha256"])

    def test_query_class_means_use_same_roster_including_zero_samples_and_no_cutoff_duplication(self):
        module = self._module()
        self._inputs(timings=lambda _identifier, _index: {"embedding": 0, "search": 0})
        result = self._call(module)
        measurement = self.kw["measurement_plan"]
        self.assertEqual(result["classes"], measurement["classes"])
        for klass in measurement["classes"]:
            if not klass["query_ids"]:
                self.assertFalse(any(row["scope"] == {"kind": "class", "id": klass["class"]}
                                     for row in result["jackal_requests"]))
                continue
            for component in ("embedding", "search"):
                request = self._request(result, klass["class"], component)
                samples = [row for row in result["query_samples"]
                           if row["class"] == klass["class"] and row["component"] == component]
                self.assertEqual(request["query_ids"], klass["query_ids"])
                self.assertEqual(request["group_ids"], klass["group_ids"])
                self.assertEqual(request["given"], samples)
                self.assertEqual(request["unit"], "ms")
                self.assertNotIn("k", request)
                self.assertEqual(request["arguments"]["expression"],
                                 "(" + "+".join("(0)" for _ in samples) + ")/" + str(len(samples)))

    def test_fractional_query_samples_form_exact_requests_without_local_mean_values(self):
        module = self._module()
        # Raw-subject groups are fixed independently of observed latency.
        fixture = self.fixture
        novelty_group = measurement_tests.selection_tests.group_id("aegis", "bluetooth.service")

        def timings(identifier, _index):
            answer = next(row for row in fixture.kw["selection"]["answer_key"] if row["id"] == identifier)
            return {"embedding": 2.5 if answer["group_id"] == novelty_group else 1.25, "search": 0}

        self._inputs(timings=timings)
        result = self._call(module)
        request = self._request(result, "novelty", "embedding")
        samples = request["given"]
        self.assertEqual({row["json_number"] for row in samples}, {"1.25", "2.5"})
        self.assertEqual(request["arguments"]["expression"],
                         "(" + "+".join("(" + row["expression_literal"] + ")" for row in samples) + ")/2")
        self.assertNotIn("mean", request)
        self.assertNotIn("result", request)
        self.assertNotIn("status", request)
        self.assertNotIn("assurance", request)

    def test_integer_float_and_negative_zero_representations_remain_distinct_given_inputs(self):
        module = self._module()
        self._inputs(timings=lambda _identifier, index: {"embedding": 0 if index == 0 else 1.0, "search": -0.0})
        result = self._call(module)
        values = result["query_samples"]
        self.assertTrue(any(type(row["value"]) is int and row["json_number"] == "0" for row in values))
        self.assertTrue(any(type(row["value"]) is float and row["json_number"] == "1.0" for row in values))
        self.assertTrue(any(row["json_number"] == "-0.0" and row["expression_literal"] == "-0.0" for row in values))
        self.assertEqual(result["measurement_plan"], self.kw["measurement_plan"])

    def test_exponent_notation_is_transcribed_as_an_expression_without_local_unit_conversion(self):
        module = self._module()
        self._inputs(timings=lambda _identifier, _index: {"embedding": 1e-6, "search": 1e20}, total=1e21)
        result = self._call(module)
        for sample in result["query_samples"]:
            self.assertEqual(sample["unit"], "ms")
            if sample["component"] == "embedding":
                self.assertEqual(sample["json_number"], "1e-06")
                self.assertEqual(sample["expression_literal"], "(1*10^(-6))")
            else:
                self.assertEqual(sample["json_number"], "1e+20")
                self.assertEqual(sample["expression_literal"], "(1*10^(20))")
        self.assertFalse(any("e-" in row["arguments"]["expression"] or "e+" in row["arguments"]["expression"]
                             for row in result["jackal_requests"]))

    def test_operation_totals_remain_separate_and_no_query_total_or_startup_is_fabricated(self):
        module = self._module()
        self._inputs()
        result = self._call(module)
        self.assertEqual(result["timing_contract"], TIMING_CONTRACT)
        self.assertEqual(result["unavailable"], UNAVAILABLE)
        self.assertEqual([row["operation"] for row in result["operation_samples"]], ["capture", "query"])
        baseline = self.kw["measurement_plan"]["baseline"]
        for sample in result["operation_samples"]:
            operation = sample["operation"]
            self.assertEqual(sample["component"], "total")
            self.assertEqual(sample["unit"], "ms")
            self.assertEqual(sample["value"], baseline["observation"][operation]["payload"]["latency_ms"]["total"])
            self.assertEqual(sample["given"]["source_pointer"], f"/observation/{operation}/payload/latency_ms/total")
            self.assertNotIn("query_id", sample)
            self.assertNotIn("class", sample)
        self.assertEqual({row["component"] for row in result["query_samples"]}, {"embedding", "search"})
        self.assertTrue(all(row["metric"] in ("mean_embedding_ms", "mean_search_ms")
                            for row in result["jackal_requests"]))

    def test_arbitrary_diagnostics_and_unbound_wall_names_are_preserved_but_not_adopted(self):
        module = self._module()
        self._inputs(diagnostics=True)
        result = self._call(module)
        observation = result["measurement_plan"]["baseline"]["observation"]
        self.assertEqual(observation["query"]["elapsed_ms"], 9.5)
        self.assertEqual(observation["query"]["wall_elapsed_ns"], 1000)
        self.assertEqual(observation["capture"]["model_startup_ms"], 7.5)
        self.assertTrue(all(row["unit"] == "ms" for row in result["query_samples"] + result["operation_samples"]))
        self.assertFalse(any("elapsed_ms" in row["given"]["source_pointer"]
                             or "wall_elapsed_ns" in row["given"]["source_pointer"]
                             or "model_startup_ms" in row["given"]["source_pointer"]
                             for row in result["query_samples"] + result["operation_samples"]))
        self.assertEqual(result["unavailable"], UNAVAILABLE)

    def test_policy_is_separate_closed_and_cannot_allocate_totals_or_change_units(self):
        module = self._module()
        self._inputs()
        for key, replacement in (("schema", "sia-cognitive-retrieval-policy-v1"), ("samples", "total-per-query"),
                                 ("units", "seconds"), ("operation_timings", "divide-total-by-query-count"),
                                 ("missing", "drop-samples"), ("aggregation", "class-weighted"),
                                 ("sample_limit", 1), ("cutoffs", [1]), ("numbers", True)):
            policy = copy.deepcopy(self.kw["latency_policy"])
            policy[key] = replacement
            with self.subTest(key=key), self.assertRaises(module.LatencyRefusal):
                self._call(module, latency_policy=policy, expected_latency_policy_sha256=sha(canonical(policy)))

    def test_measurement_and_latency_policy_external_pins_are_required(self):
        module = self._module()
        self._inputs()
        for field in ("expected_measurement_plan_sha256", "expected_latency_policy_sha256"):
            for replacement in (None, True, "0" * 64):
                with self.subTest(field=field, replacement=replacement), self.assertRaises(module.LatencyRefusal):
                    self._call(module, **{field: replacement})

    def test_replay_inputs_are_closed_and_require_independent_source_contract_and_baseline_pins(self):
        module = self._module()
        self._inputs()
        for field in ("expected_capture_sha256", "expected_policy_sha256", "expected_selection_sha256",
                      "expected_baseline_contract_sha256", "expected_metric_policy_sha256",
                      "expected_protocol_sha256", "expected_baseline_sha256"):
            replay = copy.deepcopy(self.kw["replay_inputs"])
            replay[field] = "0" * 64
            with self.subTest(field=field), self.assertRaises(module.LatencyRefusal):
                self._call(module, replay_inputs=replay)
        replay = {**self.kw["replay_inputs"], "trusted_scores": {}}
        with self.assertRaises(module.LatencyRefusal):
            self._call(module, replay_inputs=replay)

    def test_rehashed_measurement_samples_answers_and_query_rosters_require_full_replay(self):
        module = self._module()
        self._inputs()
        for field in ("latency", "answer", "query-roster", "source-origin", "metric-request"):
            changed = copy.deepcopy(self.kw["measurement_plan"])
            baseline = changed["baseline"]
            if field == "latency":
                baseline["observation"]["query"]["payload"]["results"][0]["latency_ms"]["embedding"] = 0
            elif field == "answer":
                baseline["answer_key"][0]["answer"]["sequences"] = ["0"]
            elif field == "query-roster":
                changed["queries"].pop()
            elif field == "source-origin":
                page = baseline["pages"][0]
                page["origin"] = "model" if page["origin"] != "model" else "evidence"
            else:
                changed["jackal_requests"][0]["arguments"]["expression"] = "999"
            self._rehashed_plan(changed)
            with self.subTest(field=field), self.assertRaises(module.LatencyRefusal):
                self._call(module, measurement_plan=changed, expected_measurement_plan_sha256=changed["plan_sha256"])

    def test_missing_extra_boolean_negative_and_nonfinite_query_samples_are_never_zero_filled(self):
        module = self._module()
        self._inputs()
        for replacement in ({"search": 0}, {"embedding": 0, "search": 0, "total": 0},
                            {"embedding": True, "search": 0}, {"embedding": -1, "search": 0},
                            {"embedding": "1.25", "search": 0}):
            baseline = copy.deepcopy(self.kw["replay_inputs"]["baseline"])
            baseline["observation"]["query"]["payload"]["results"][0]["latency_ms"] = replacement
            overrides = self._bound_baseline_override(baseline)
            with self.subTest(replacement=replacement), self.assertRaises(module.LatencyRefusal):
                self._call(module, **overrides)
        for invalid in (float("nan"), float("inf")):
            replay = copy.deepcopy(self.kw["replay_inputs"])
            replay["baseline"]["observation"]["query"]["payload"]["results"][0]["latency_ms"]["embedding"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(module.LatencyRefusal):
                self._call(module, replay_inputs=replay)

    def test_component_above_operation_total_refuses_without_fabricating_an_adjustment(self):
        module = self._module()
        self._inputs()
        baseline = copy.deepcopy(self.kw["replay_inputs"]["baseline"])
        baseline["observation"]["query"]["payload"]["latency_ms"]["total"] = 0
        overrides = self._bound_baseline_override(baseline)
        with self.assertRaises(module.LatencyRefusal):
            self._call(module, **overrides)

    def test_refused_or_unobserved_envelopes_are_not_timing_observations(self):
        module = self._module()
        self._inputs()
        for place, status in (("measurement", "observed"), ("baseline", "refused"), ("raw", "refused")):
            changed = copy.deepcopy(self.kw["measurement_plan"])
            if place == "measurement":
                changed["status"] = status
            elif place == "baseline":
                changed["baseline"]["status"] = status
            else:
                changed["baseline"]["observation"]["query"]["payload"]["status"] = status
            self._rehashed_plan(changed)
            with self.subTest(place=place), self.assertRaises(module.LatencyRefusal):
                self._call(module, measurement_plan=changed, expected_measurement_plan_sha256=changed["plan_sha256"])

    def test_bounded_structure_admission_precedes_copy_and_serialization(self):
        module = self._module()
        self._inputs()
        policy = policy_fixture()
        policy["samples"] = policy
        for field, replacement in (("latency_policy", policy),
                                   ("measurement_plan", {"value": float("inf")}),
                                   ("replay_inputs", {"value": float("nan")})):
            with mock.patch("copy.deepcopy", side_effect=AssertionError("copied unadmitted structure")), \
                    mock.patch("json.dumps", side_effect=AssertionError("serialized unadmitted structure")), \
                    self.assertRaises(module.LatencyRefusal):
                self._call(module, **{field: replacement})

    def test_heldout_requires_latency_policy_pin_already_present_in_external_parameter_freeze(self):
        module = self._module()
        self._inputs(split="heldout")
        result = self._call(module)
        freeze = self.kw["measurement_plan"]["baseline"]["parameter_freeze"]
        self.assertEqual(freeze["parameters"]["latency_policy_sha256"], self.kw["expected_latency_policy_sha256"])
        self.assertEqual(result["split"], "heldout")
        self.assertEqual(result["parameter_freeze_sha256"], self.kw["replay_inputs"]["expected_parameter_freeze_sha256"])
        replay = copy.deepcopy(self.kw["replay_inputs"])
        replay["expected_parameter_freeze_sha256"] = "0" * 64
        with self.assertRaises(module.LatencyRefusal):
            self._call(module, replay_inputs=replay)

    def test_preexisting_heldout_retrieval_freeze_without_latency_policy_cannot_be_retrofitted(self):
        module = self._module()
        self._inputs(split="heldout", include_latency_pin=False)
        self.assertNotIn("latency_policy_sha256", self.kw["measurement_plan"]["baseline"]["parameter_freeze"]["parameters"])
        with self.assertRaises(module.LatencyRefusal):
            self._call(module)

    def test_foreign_latency_policy_pin_refuses_even_after_full_measurement_replay(self):
        module = self._module()
        self._inputs(split="heldout")
        replay = copy.deepcopy(self.kw["replay_inputs"])
        baseline = replay["baseline"]
        freeze = baseline["parameter_freeze"]
        freeze["parameters"]["latency_policy_sha256"] = "0" * 64
        freeze["parameters_sha256"] = sha(canonical(freeze["parameters"]))
        freeze["freeze_sha256"] = body_digest(freeze, "freeze_sha256")
        baseline["parameter_freeze_sha256"] = freeze["freeze_sha256"]
        baseline["artifact_sha256"] = body_digest(baseline, "artifact_sha256")
        replay["expected_parameter_freeze_sha256"] = freeze["freeze_sha256"]
        replay["expected_baseline_sha256"] = baseline["artifact_sha256"]
        measurement = importlib.import_module("siacognitivemeasure")
        with self.fixture._pure():
            plan = measurement.prepare_measurement(**replay)
        with self.assertRaises(module.LatencyRefusal):
            self._call(module, replay_inputs=replay, measurement_plan=plan, expected_measurement_plan_sha256=plan["plan_sha256"])

    def test_nonclaims_and_unavailable_classes_remain_controlling_without_comparison_or_assurance(self):
        module = self._module()
        self._inputs()
        result = self._call(module)
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertEqual(result["source_non_claims"], {
            "measurement": self.kw["measurement_plan"]["non_claims"],
            "history": self.kw["measurement_plan"]["source_non_claims"]})
        for klass in result["classes"]:
            if klass["status"] == "unavailable":
                self.assertEqual(klass["query_ids"], [])
                self.assertFalse(any(row["scope"]["id"] == klass["class"] for row in result["jackal_requests"]))
        for forbidden in ("win", "speedup", "cpu_comparison", "model_comparison", "p_value", "iid", "statistical_power", "mean_latency"):
            self.assertNotIn(forbidden, result)
        for request in result["jackal_requests"]:
            self.assertNotIn("status", request)
            self.assertNotIn("assurance", request)
            self.assertNotIn("result", request)


if __name__ == "__main__":
    unittest.main()
