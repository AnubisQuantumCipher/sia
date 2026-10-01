"""Scoped mechanism fidelity predicates require complete independent replay.

Only the existing public signed ordered-measurement fixtures and their owned
stopped-process doubles are used. Root alone schedules execution. No private
result, model, DB, real retrieval, parameter choice or JACKAL call is used.

This compact report retains policy, predicates, identities and full upstream
nonclaims. Capture/ordered documents and all referenced subtrees remain
externally retained complete documents: their hashes are not a source archive.
There are no fabricated percentages or locally derived metric expectations.
Resource literals are existing declared envelope, capture and activation caps.
"""

import contextlib
import copy
import importlib
import inspect
import unittest
from unittest import mock

from tests import test_cognitive_ordered_measurement as ordered_tests
from tests import test_cognitive_ordered_measurement_envelope as ordered_envelope
from tests import test_cognitive_event_exposure_envelope as exposure_envelope


sha = ordered_tests.sha
canonical = ordered_tests.canonical
body_digest = ordered_tests.body_digest
ARMS = ordered_tests.ARMS
PREDICATES = [
    "complete-captured-source-bindings",
    "complete-returned-candidate-membership",
    "unchanged-raw-chunk-and-score-values",
    "unchanged-source-origins",
    "complete-exposure-and-activation-traces",
    "unchanged-native-targets-and-coverage",
    "complete-fixed-arm-permutations",
    "complete-upstream-nonclaims",
]
SCOPE = {
    "sources": "admitted-captured-history-only",
    "candidates": "returned-raw-candidate-roster-only",
    "storage": "identity-references-not-a-source-archive",
    "resident_state": "not-observed",
}
NON_CLAIMS = [
    "These Boolean predicates describe independently replayed represented consistency within the admitted capture and returned candidate roster, not a memory-fidelity percentage.",
    "Identity references are not source archives; the caller must retain the complete externally referenced documents.",
    "Independent replay does not authenticate historical sources, establish current resident-state bytes, or prove that no live corpus page was deleted.",
    "Preserving raw chunk/score values and source origins does not establish truth, semantic-answer correctness, biological memory fidelity, recall improvement or a cognitive win.",
    "Full traces, targets, fixed arms, raw latency observations, and upstream nonclaims remain controlling; this boundary does not tune, select an arm, or evaluate JACKAL expressions.",
    "Heldout policy pins declare calibration-only chronology but do not independently prove when tuning or private result inspection occurred.",
    "No model, index, filesystem, clock, corpus mutation, source publication or durable storage is invoked.",
]
SOURCE_PINS = (
    "capture_sha256", "policy_sha256", "selection_sha256", "pages_sha256",
    "metric_policy_sha256", "baseline_contract_sha256", "protocol_sha256",
    "baseline_sha256", "query_roster_sha256", "parameter_freeze_sha256",
    "measurement_plan_sha256", "rerank_policy_sha256", "activation_grid_sha256",
    "activation_policy_sha256", "exposure_sha256", "ordered_policy_sha256",
)


def policy_fixture(protocol_sha256):
    return {
        "schema": "sia-cognitive-memory-fidelity-policy-v1",
        "ordered_schema": "sia-cognitive-ordered-measurement-plan-v1",
        "metric_protocol_sha256": protocol_sha256,
        "arms": list(ARMS), "predicates": list(PREDICATES), "scope": dict(SCOPE),
        "replay": "complete-independent-ordered-replay-v1",
        "references": "complete-documents-and-subtrees-no-archive-claim-v1",
        "chronology": "externally-pinned-before-heldout-v1",
        "overflow": "refuse-complete-artifact-v1",
        "resources": {
            "max_input_bytes": 67108864, "max_document_bytes": 16777216,
            "max_output_bytes": 16777216, "max_queries": 64,
            "max_source_events": 65536, "max_source_pages": 4096,
            "max_candidates_per_query": 256, "max_trace_bytes": 2097152,
        },
    }


def expected_layout():
    # This topology is a closed API contract, never supplied by an artifact.
    return {
        "ordered_plan": None, "expected_ordered_plan_sha256": None,
        "ordered_inputs": ordered_envelope.expected_layout(),
        "fidelity_policy": None, "expected_fidelity_policy_sha256": None,
    }


class CognitiveFidelity(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("siacognitivefidelity")
        except ModuleNotFoundError as exc:
            self.fail("pure independently replayed mechanism fidelity API must exist: " + str(exc))
        self.assertTrue(callable(getattr(self.module, "prepare_mechanism_fidelity", None)))
        self.assertTrue(hasattr(self.module, "FidelityRefusal"))
        self.fx = ordered_tests.CognitiveOrderedMeasurement(methodName="runTest")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.ordered = importlib.import_module("siacognitiveorderedmeasure")

    def _inputs(self, *, split="calibration", choices=None, freeze_fidelity="correct", compound=False):
        fixture = self.fx.fx.fixture
        original_freeze = fixture._freeze

        def frozen_before_observation():
            value = original_freeze()
            protocol = fixture._protocol(importlib.import_module("siacognitivemeasure"))
            policy = policy_fixture(protocol["protocol_sha256"])
            if freeze_fidelity != "missing":
                value["parameters"]["memory_fidelity_policy_sha256"] = (
                    sha(canonical(policy)) if freeze_fidelity == "correct" else "0" * 64)
            value["parameters_sha256"] = sha(canonical(value["parameters"]))
            value["freeze_sha256"] = body_digest(value, "freeze_sha256")
            fixture.kw["expected_parameter_freeze_sha256"] = value["freeze_sha256"]
            return value

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(fixture, "_freeze", side_effect=frozen_before_observation))
            if compound:
                stack.enter_context(mock.patch.object(ordered_tests, "policy_fixture",
                                                      side_effect=ordered_envelope.policy_fixture))
                stack.enter_context(mock.patch.object(ordered_tests.exposure_tests, "policy_fixture",
                                                      side_effect=exposure_envelope.policy_fixture))
            self.fx._inputs(split=split, choices=choices)
        plan = self.fx._call(self.ordered)
        policy = policy_fixture(plan["protocol_sha256"])
        self.kw = {
            "ordered_plan": plan, "expected_ordered_plan_sha256": plan["plan_sha256"],
            "ordered_inputs": copy.deepcopy(self.fx.kw), "fidelity_policy": policy,
            "expected_fidelity_policy_sha256": sha(canonical(policy)),
        }

    def _call(self, **overrides):
        with self.fx.fx.fixture._pure():
            return self.module.prepare_mechanism_fidelity(**{**self.kw, **overrides})

    def _policy_override(self, policy):
        return {"fidelity_policy": policy, "expected_fidelity_policy_sha256": sha(canonical(policy))}

    def _capture(self):
        return self.kw["ordered_inputs"]["exposure_inputs"]["replay_inputs"]["capture"]

    def _bindings(self):
        plan, capture = self.kw["ordered_plan"], self._capture()
        baseline = plan["exposure"]["measurement_plan"]["baseline"]
        rows = [
            {"name": "capture", "sha256": capture["capture_sha256"],
             "digest_rule": "embedded-body-sha256", "retention": "externally-retained-complete-document"},
            {"name": "ordered_plan", "sha256": plan["plan_sha256"],
             "digest_rule": "embedded-body-sha256", "retention": "externally-retained-complete-document"},
        ]
        material = (
            ("capture.events", capture["events"]), ("capture.pages", capture["pages"]),
            ("capture.witness_files", capture["witness_files"]),
            ("baseline.pages", baseline["pages"]), ("baseline.observation", baseline["observation"]),
            ("baseline.retrieval_rows", baseline["retrieval_rows"]),
            ("exposure.queries", plan["exposure"]["queries"]), ("ordered_plan.arms", plan["arms"]),
        )
        return rows + [{"name": name, "sha256": sha(canonical(value)),
                        "digest_rule": "canonical-json-sha256", "retention": "externally-retained-complete-subtree"}
                       for name, value in material]

    def _source_nonclaims(self):
        plan, capture = self.kw["ordered_plan"], self._capture()
        return {"ordered": plan["non_claims"], "ordered_sources": plan["source_non_claims"],
                "capture": capture["non_claims"], "capture_sources": capture["source_non_claims"]}

    def test_public_api_requires_only_explicit_keyword_only_independent_inputs(self):
        parameters = inspect.signature(self.module.prepare_mechanism_fidelity).parameters
        self.assertEqual(set(parameters), {
            "ordered_plan", "expected_ordered_plan_sha256", "ordered_inputs",
            "fidelity_policy", "expected_fidelity_policy_sha256"})
        for parameter in parameters.values():
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)
        self._inputs()
        for forbidden in ("desired_score", "answer_override", "choose_arm", "trust_plan", "resident_path"):
            with self.subTest(forbidden=forbidden), self.assertRaises(TypeError):
                self._call(**{forbidden: True})

    def test_complete_ordered_replay_precedes_compact_detached_consistency_report(self):
        self._inputs()
        before = copy.deepcopy(self.kw)
        with mock.patch.object(self.ordered, "prepare_ordered_measurement",
                               wraps=self.ordered.prepare_ordered_measurement) as replay:
            result = self._call()
        self.assertEqual(replay.call_args_list, [mock.call(**self.kw["ordered_inputs"])])
        self.assertEqual(result, self._call())
        self.assertEqual(self.kw, before)
        self.assertEqual(set(result), {
            "schema", "status", "ordered_plan_sha256", "fidelity_policy", "fidelity_policy_sha256",
            "source_pins", "split", "scope", "predicates", "material_bindings", "source_non_claims",
            "non_claims", "artifact_sha256"})
        self.assertEqual(result["schema"], "sia-cognitive-memory-fidelity-v1")
        self.assertEqual(result["status"], "computed-unverified")
        self.assertEqual(result["artifact_sha256"], body_digest(result, "artifact_sha256"))
        self.assertEqual(result["ordered_plan_sha256"], self.kw["expected_ordered_plan_sha256"])
        self.assertEqual(result["fidelity_policy_sha256"], self.kw["expected_fidelity_policy_sha256"])
        self.assertEqual(result["fidelity_policy"], self.kw["fidelity_policy"])
        self.assertEqual(result["source_pins"], {key: self.kw["ordered_plan"][key] for key in SOURCE_PINS})
        self.assertEqual(result["split"], self.kw["ordered_plan"]["split"])
        self.assertEqual(result["scope"], SCOPE)
        self.assertEqual(result["predicates"], [{"name": name, "holds": True} for name in PREDICATES])
        self.assertEqual(result["material_bindings"], self._bindings())
        self.assertEqual(result["source_non_claims"], self._source_nonclaims())
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        result["fidelity_policy"]["predicates"].clear()
        result["source_non_claims"]["ordered_sources"].clear()
        result["material_bindings"].clear()
        self.assertEqual(self.kw, before)

    def test_full_sources_chunks_scores_origins_traces_targets_and_arms_are_referenced_not_archived(self):
        self._inputs()
        result = self._call()
        self.assertEqual(result["material_bindings"], self._bindings())
        self.assertNotIn("capture", result)
        self.assertNotIn("ordered_plan", result)
        self.assertNotIn("ordered_inputs", result)
        for row in result["material_bindings"]:
            self.assertEqual(set(row), {"name", "sha256", "digest_rule", "retention"})
        material = {row["name"] for row in result["material_bindings"]}
        for name in ("capture.events", "capture.pages", "capture.witness_files", "baseline.pages",
                     "baseline.observation", "baseline.retrieval_rows", "exposure.queries", "ordered_plan.arms"):
            self.assertIn(name, material)
        for forbidden in ("fidelity_percent", "retention_rate", "loss_rate", "semantic_accuracy",
                          "deleted_pages", "resident_page_count", "no_live_deletions", "biological_fidelity",
                          "best_arm", "win", "p_value", "latency_ms", "jackal_requests"):
            self.assertNotIn(forbidden, result)

    def test_rehashed_plan_changes_cannot_replace_independent_complete_replay(self):
        self._inputs()
        self._call()
        for change in ("source-page", "raw-chunk", "raw-score", "origin", "exposure", "trace", "activation",
                       "target", "coverage", "missing-arm", "arm-order", "missing-query", "upstream-nonclaims"):
            plan = copy.deepcopy(self.kw["ordered_plan"])
            exposure = plan["exposure"]
            candidate = exposure["queries"][-1]["candidates"][-1]
            if change == "source-page":
                exposure["measurement_plan"]["baseline"]["pages"][0]["text"] += "\nsubstituted source\n"
            elif change == "raw-chunk":
                candidate["raw_row"]["chunk_text"] = "substituted chunk"
            elif change == "raw-score":
                candidate["raw_row"]["score"] = "substituted score"
            elif change == "origin":
                candidate["origin"] = "model" if candidate["origin"] != "model" else "evidence"
            elif change == "exposure":
                candidate["exposures"] = []
            elif change == "trace":
                candidate["trace"]["complete"] = False
            elif change == "activation":
                exposure["queries"][-1]["activation"]["order"].reverse()
            elif change == "target":
                plan["arms"][-1]["queries"][-1]["targets"] = []
            elif change == "coverage":
                plan["arms"][-1]["queries"][-1]["row_coverage"] = []
            elif change == "missing-arm":
                plan["arms"].pop()
            elif change == "arm-order":
                plan["arms"][-1]["query_orders"][-1]["order"].reverse()
            elif change == "missing-query":
                exposure["queries"].pop()
            else:
                plan["source_non_claims"] = {}
            self.assertNotEqual(plan, self.kw["ordered_plan"], change)
            plan["plan_sha256"] = body_digest(plan, "plan_sha256")
            with self.subTest(change=change), self.assertRaises(self.module.FidelityRefusal):
                self._call(ordered_plan=plan, expected_ordered_plan_sha256=plan["plan_sha256"])

    def test_independent_expectations_are_required_at_every_upstream_layer(self):
        self._inputs()
        for field in ("expected_ordered_plan_sha256", "expected_fidelity_policy_sha256"):
            for wrong in (None, True, "0" * 64):
                with self.subTest(field=field, wrong=wrong), self.assertRaises(self.module.FidelityRefusal):
                    self._call(**{field: wrong})
        paths = []
        inputs = self.kw["ordered_inputs"]
        paths.extend((key,) for key in inputs if key.startswith("expected_"))
        paths.extend(("exposure_inputs", key) for key in inputs["exposure_inputs"] if key.startswith("expected_"))
        paths.extend(("exposure_inputs", "replay_inputs", key)
                     for key in inputs["exposure_inputs"]["replay_inputs"]
                     if key.startswith("expected_") and key != "expected_parameter_freeze_sha256")
        for path in paths:
            changed = copy.deepcopy(inputs)
            owner = changed
            for key in path[:-1]:
                owner = owner[key]
            owner[path[-1]] = "0" * 64
            with self.subTest(path=path), self.assertRaises(self.module.FidelityRefusal):
                self._call(ordered_inputs=changed)

    def test_closed_policy_cannot_weaken_predicates_scope_arms_or_chronology(self):
        self._inputs()
        for key in self.kw["fidelity_policy"]:
            policy = copy.deepcopy(self.kw["fidelity_policy"])
            del policy[key]
            with self.subTest(missing=key), self.assertRaises(self.module.FidelityRefusal):
                self._call(**self._policy_override(policy))
        changes = (("schema", "unreviewed"), ("ordered_schema", "unreplayed"),
                   ("metric_protocol_sha256", "0" * 64), ("arms", [ARMS[-1]]),
                   ("predicates", PREDICATES[:-1]), ("scope", {**SCOPE, "resident_state": "verified"}),
                   ("replay", "trust-self-hash"), ("references", "archive-claim"),
                   ("chronology", "refit-after-heldout"), ("overflow", "drop-late-query"),
                   ("target_percentage", "claimed-perfect"))
        for key, value in changes:
            policy = copy.deepcopy(self.kw["fidelity_policy"])
            policy[key] = value
            with self.subTest(key=key), self.assertRaises(self.module.FidelityRefusal):
                self._call(**self._policy_override(policy))
        for key in ("arms", "predicates"):
            policy = copy.deepcopy(self.kw["fidelity_policy"])
            policy[key].reverse()
            with self.subTest(reordered=key), self.assertRaises(self.module.FidelityRefusal):
                self._call(**self._policy_override(policy))

    def test_literal_compound_layout_keeps_every_underlying_document_whole(self):
        self._inputs(compound=True)
        before = copy.deepcopy(self.kw)
        envelope = importlib.import_module("siacognitiveenvelope")
        with mock.patch.object(envelope, "admit_compound", wraps=envelope.admit_compound) as admission:
            result = self._call()
        calls = [call for call in admission.call_args_list if "ordered_inputs" in call.kwargs["envelope"]]
        self.assertTrue(calls)
        for call in calls:
            self.assertEqual(call.kwargs["envelope"], before)
            self.assertEqual(call.kwargs["layout"], expected_layout())
            self.assertEqual(call.kwargs["max_input_bytes"], self.kw["fidelity_policy"]["resources"]["max_input_bytes"])
            self.assertEqual(call.kwargs["max_document_bytes"], self.kw["fidelity_policy"]["resources"]["max_document_bytes"])
            self.assertIsNone(call.kwargs["layout"]["ordered_plan"])
            self.assertIsNone(call.kwargs["layout"]["ordered_inputs"]["exposure"])
        self.assertEqual(result["ordered_plan_sha256"], self.kw["expected_ordered_plan_sha256"])
        self.assertEqual(self.kw, before)

    def test_late_invalid_domain_refuses_before_copy_hash_serialization_or_replay(self):
        self._inputs()
        cycle = {}
        cycle["cycle"] = cycle
        for field, invalid in (("capture", cycle), ("protocol", {"bad": float("inf")}),
                               ("baseline", {"bad": float("nan")})):
            inputs = copy.deepcopy(self.kw["ordered_inputs"])
            inputs["exposure_inputs"]["replay_inputs"][field] = invalid
            with self.subTest(field=field), \
                    mock.patch("copy.deepcopy", side_effect=AssertionError("copy before complete domain admission")), \
                    mock.patch("hashlib.sha256", side_effect=AssertionError("hash before complete domain admission")), \
                    mock.patch("json.dumps", side_effect=AssertionError("serialization before complete domain admission")), \
                    mock.patch.object(self.ordered, "prepare_ordered_measurement", side_effect=AssertionError("replay before complete domain admission")), \
                    self.assertRaises(self.module.FidelityRefusal):
                self._call(ordered_inputs=inputs)

    def test_all_resource_and_output_reservations_precede_copy_hash_and_replay(self):
        self._inputs()
        for field in self.kw["fidelity_policy"]["resources"]:
            for invalid in (None, True, 0, 1.0, 1):
                policy = copy.deepcopy(self.kw["fidelity_policy"])
                policy["resources"][field] = invalid
                overrides = self._policy_override(policy)
                with self.subTest(field=field, invalid=invalid), \
                        mock.patch("copy.deepcopy", side_effect=AssertionError("copy before complete resource admission")), \
                        mock.patch("hashlib.sha256", side_effect=AssertionError("hash before complete resource admission")), \
                        mock.patch.object(self.ordered, "prepare_ordered_measurement", side_effect=AssertionError("replay before complete resource admission")), \
                        self.assertRaises(self.module.FidelityRefusal):
                    self._call(**overrides)
        for field in self.kw["fidelity_policy"]["resources"]:
            policy = copy.deepcopy(self.kw["fidelity_policy"])
            del policy["resources"][field]
            with self.subTest(missing=field), self.assertRaises(self.module.FidelityRefusal):
                self._call(**self._policy_override(policy))
        policy = copy.deepcopy(self.kw["fidelity_policy"])
        policy["resources"]["ignore_document_bounds"] = True
        with self.assertRaises(self.module.FidelityRefusal):
            self._call(**self._policy_override(policy))

    def test_hard_envelope_and_whole_document_caps_cannot_expand(self):
        self._inputs()
        # Boundary literals are copied from the already JACKAL-routed ordered
        # envelope fixtures: status=exact, parsed=67108864+1 exact=67108865;
        # parsed=16777216+1 exact=16777217. NOT formal-bounded: this lane
        # carries no Lean-checked certificate; the epistemic class above is
        # the STRONGEST claim supported; exact rational arithmetic is not yet
        # checker-covered. These literals do not assure this implementation.
        for field, invalid in (("max_input_bytes", 67108865),
                               ("max_document_bytes", 16777217),
                               ("max_output_bytes", 16777217)):
            policy = copy.deepcopy(self.kw["fidelity_policy"])
            policy["resources"][field] = invalid
            overrides = self._policy_override(policy)
            with self.subTest(field=field), \
                    mock.patch("copy.deepcopy", side_effect=AssertionError("copy before hard ceiling")), \
                    mock.patch("hashlib.sha256", side_effect=AssertionError("hash before hard ceiling")), \
                    mock.patch.object(self.ordered, "prepare_ordered_measurement", side_effect=AssertionError("replay before hard ceiling")), \
                    self.assertRaises(self.module.FidelityRefusal):
                self._call(**overrides)

    def test_complete_nested_argument_topology_cannot_drop_or_ignore_inputs(self):
        self._inputs()
        for path in ((), ("exposure_inputs",), ("exposure_inputs", "replay_inputs")):
            for change in ("extra", "missing", "retyped"):
                inputs = copy.deepcopy(self.kw["ordered_inputs"])
                owner = inputs
                for key in path:
                    owner = owner[key]
                if change == "extra":
                    owner["ignored_document"] = {}
                elif change == "missing":
                    del owner[next(iter(owner))]
                elif path:
                    parent = inputs
                    for key in path[:-1]:
                        parent = parent[key]
                    parent[path[-1]] = []
                else:
                    inputs = []
                with self.subTest(path=path, change=change), self.assertRaises(self.module.FidelityRefusal):
                    self._call(ordered_inputs=inputs)

    def test_heldout_requires_preexisting_fidelity_policy_plus_every_upstream_freeze(self):
        self._inputs(split="heldout")
        result = self._call()
        baseline = self.kw["ordered_plan"]["exposure"]["measurement_plan"]["baseline"]
        freeze = baseline["parameter_freeze"]
        self.assertEqual(freeze["parameters"]["memory_fidelity_policy_sha256"],
                         self.kw["expected_fidelity_policy_sha256"])
        self.assertEqual(result["source_pins"]["parameter_freeze_sha256"], freeze["freeze_sha256"])
        for field in ("measurement_protocol_sha256", "event_exposure_policy_sha256", "activation_grid_sha256",
                      "selected_activation_policy_sha256", "ordered_measurement_policy_sha256"):
            self.assertIn(field, freeze["parameters"])
        inputs = copy.deepcopy(self.kw["ordered_inputs"])
        inputs["exposure_inputs"]["replay_inputs"]["expected_parameter_freeze_sha256"] = "0" * 64
        with self.assertRaises(self.module.FidelityRefusal):
            self._call(ordered_inputs=inputs)

    def test_missing_fidelity_freeze_refuses_after_valid_upstream_control(self):
        self._inputs(split="heldout", freeze_fidelity="missing")
        self.assertEqual(self.kw["ordered_plan"]["split"], "heldout")
        with self.assertRaises(self.module.FidelityRefusal):
            self._call()

    def test_foreign_fidelity_freeze_refuses_after_valid_upstream_control(self):
        self._inputs(split="heldout", freeze_fidelity="foreign")
        self.assertEqual(self.kw["ordered_plan"]["split"], "heldout")
        with self.assertRaises(self.module.FidelityRefusal):
            self._call()

    def test_empty_candidates_preserve_all_queries_arms_denominators_and_nonclaims(self):
        self._inputs(choices={})
        before = copy.deepcopy(self.kw)
        result = self._call()
        self.assertEqual(result["material_bindings"], self._bindings())
        for query in self.kw["ordered_plan"]["exposure"]["queries"]:
            self.assertEqual(query["candidates"], [])
            self.assertEqual([arm["name"] for arm in query["arms"]], ARMS)
        self.assertEqual(result["predicates"], [{"name": name, "holds": True} for name in PREDICATES])
        self.assertEqual(result["source_non_claims"], self._source_nonclaims())
        self.assertEqual(self.kw, before)

    def test_model_origin_and_non_ascii_source_bytes_remain_controlling(self):
        source = self.fx.fx.fixture._source()
        original = source.read_bytes().replace(b"---\n", b"---\norigin: model\n", 1)
        original += "\r\nOriginal Ω尾 bytes.\r\n".encode("utf-8")
        source.write_bytes(original)
        self._inputs()
        result = self._call()
        capture = self._capture()
        page = next(row for row in capture["pages"] if row["slug"] == "events/aegis/2026-01-01")
        self.assertEqual(page["origin"], "model")
        self.assertEqual(page["text"].encode("utf-8"), original)
        self.assertEqual(result["material_bindings"], self._bindings())
        self.assertEqual(result["source_non_claims"], self._source_nonclaims())
        self.assertEqual(result["non_claims"], NON_CLAIMS)

    def test_pure_boundary_does_not_open_execute_metrics_or_mutate_live_state(self):
        self._inputs()
        before = copy.deepcopy(self.kw)
        # Independent ordered replay legitimately reruns its upstream pure
        # scorer/ranker; only external execution and ambient state are barred.
        with mock.patch("time.time", side_effect=AssertionError("ambient wall clock")):
            first = self._call()
            second = self._call()
        self.assertEqual(first, second)
        self.assertEqual(self.kw, before)
        self.assertEqual(first["non_claims"], NON_CLAIMS)


if __name__ == "__main__":
    unittest.main()
