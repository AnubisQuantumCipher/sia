#!/usr/bin/env python3
"""RED contract for the six literature-bound cognitive claim decisions.

The fixtures are synthetic identity/relationship records.  They contain no
benchmark measurements and perform no metric arithmetic.  A future green
implementation must consume separately retained JACKAL results; these tests
only specify the registry, binding, chronology, completeness, and honesty
boundary around those results.
"""

import base64
import copy
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "bin"))

REGISTRY_SCHEMA = "sia-cognitive-mechanism-registry-v1"
EVIDENCE_SCHEMA = "sia-cognitive-mechanism-evidence-v1"
DECISION_SCHEMA = "sia-cognitive-claim-decision-v1"
VERIFICATION_SCHEMA = "sia-cognitive-jackal-verification-v1"
BASELINE_ID = "descriptor-bound-raw-vector-dense"
JACKAL_VERIFY_ARTIFACT = "/home/sicarii/.config/omarchy/plugins/khephri.jackal/verify_artifact.py"
JACKAL_OPERATOR_EXPECTATIONS = "/home/sicarii/.config/omarchy/jackal-expectations.json"
OPERATOR_EXPECTATIONS_SHA256 = hashlib.sha256(
    b"synthetic-operator-expectations-fixture").hexdigest()
REQUIRED_METRICS = [
    "recall_at_k", "mrr", "query_latency_ms", "sia_memory_fidelity",
]
FIDELITY_DIMENSIONS = [
    "episode-retention", "content-immutability", "origin-preservation",
    "unsupported-and-exception-retention",
]
WIN_RULE = "registered-primary-strictly-better-all-required-guardrails-noninferior-v1"
CHRONOLOGY = "registry-and-policy-frozen-before-heldout-results-no-heldout-tuning-v1"
INFERENCE_REQUIREMENT = "fixed-component-paired-one-sided-test-with-declared-model-and-multiplicity-v1"

REGISTRY_NON_CLAIMS = [
    "This registry records literature-grounded, falsifiable hypotheses; it is not benchmark evidence or a cognitive claim.",
    "A held-out win authorizes only the registered mechanism, task scope, baseline, metrics, implementation, and wording bound by that evidence.",
    "JACKAL status classes describe the retained arithmetic or model result and must be carried verbatim; they do not authenticate history or prove biology.",
    "No registry entry or benchmark result establishes a biological brain, consciousness, dopamine, sleep physiology, or a literal neural implementation.",
]

EVIDENCE_NON_CLAIMS = [
    "Digest equality binds supplied bytes but does not authenticate machine history, execution, dataset provenance, or a JACKAL receipt.",
    "A raw evidence bundle carries artifact identities only; it cannot authorize a cognitive claim without fresh module-owned verification.",
]

JACKAL_NON_CLAIMS = [
    "A JACKAL result establishes only the returned arithmetic or model relation under its stated inputs, assumptions, status class, and consequence ceiling.",
    "It does not authenticate dataset provenance, causal isolation, implementation behavior, or biological equivalence.",
]

VERIFICATION_NON_CLAIMS = [
    "Verifier acceptance authenticates only the retained artifact authorized by fixed operator expectations and preserves its returned status, assumptions, non-claims, and consequence ceiling.",
    "Receipt verification does not establish dataset provenance, causal isolation, implementation behavior, biological equivalence, or a cognitive claim.",
]

BEHAVIOR_VERIFICATION_NON_CLAIMS = [
    "Behavior-witness verification binds retained component or delivery artifacts; it does not turn their content into a biological observation.",
]

COMMON_BENCHMARK = {
    "control": BASELINE_ID,
    "causal_unit": "same-heldout-query-target-and-source-generation-v1",
    "split": "heldout",
    "tuning_split": "calibration",
    "dataset_source": "front-door-only-real-machine-history-v1",
    "other_mechanisms": "disabled-or-neutral-v1",
    "required_metrics": REQUIRED_METRICS,
    "fidelity_dimensions": FIDELITY_DIMENSIONS,
    "inference_requirement": INFERENCE_REQUIREMENT,
    "win_rule": WIN_RULE,
    "chronology": CHRONOLOGY,
}

OPERATOR_LABELS = {
    "usage-salience": "ACT-R base-level activation",
    "co-retrieval-strengthening": "Hebbian co-recall",
    "maintained-workspace": "Global Workspace",
    "typed-fan-spreading": "HippoRAG-style spreading activation",
    "prediction-conditioned-encoding": "dopaminergic novelty gating",
    "replay-gist": "sleep/gist consolidation",
}

WITNESS_REQUIREMENTS = {
    "usage-salience": "complete-use-trace-recency-and-frequency-effects-v1",
    "co-retrieval-strengthening": "learned-edge-and-expanded-reachability-v1",
    "maintained-workspace": "complete-consumer-delivery-and-acknowledgment-receipts-v1",
    "typed-fan-spreading": "out-of-window-multihop-retrieval-with-complete-fan-v1",
    "prediction-conditioned-encoding": "prequential-novelty-strength-and-later-retrieval-v1",
    "replay-gist": "durable-gist-and-immutable-episode-population-v1",
}

CLAIM_ELIGIBILITY = {
    product_id: "heldout-evidence-required-v1" for product_id in OPERATOR_LABELS
}
CLAIM_ELIGIBILITY["prediction-conditioned-encoding"] = (
    "permanently-stripped-current-registry-no-reward-prediction-error-"
    "plasticity-gain-witness-v1"
)

MECHANISMS = {
    "usage-salience": {
        "product_label": "Usage salience",
        "candidate_neurocognitive_label": "ACT-R base-level activation",
        "definition": (
            "Activation is the natural logarithm of the sum of every admitted "
            "past use's power-decayed age; frequency and recency are distinct "
            "contributors, and no complete use trace means no finite score."
        ),
        "falsifiable_behavior": (
            "With all other inputs fixed, another use and a more recent use each "
            "raise rank availability; an absent or incomplete trace cannot be "
            "silently assigned a numeric activation."
        ),
        "literature": [
            {
                "source": "/home/sicarii/Dropbox/Cog.pdf",
                "locator": "printed pages 135-137, ACT-R architecture",
            },
            {
                "source": "Anderson & Schunn (2000), Implications of the ACT-R Learning Theory: No Magic Bullets",
                "locator": "manuscript page 8, Base-Level Equation",
            },
        ],
        "implementation": {
            "module": "siaactivation", "callable": "rank_traces",
            "component": "usage-salience",
        },
        "task_classes": ["recency-heavy", "repetition-heavy"],
        "intervention": "rank-by-complete-power-law-use-trace-v1",
        "primary_metric": "recall_at_k",
    },
    "co-retrieval-strengthening": {
        "product_label": "Co-retrieval strengthening",
        "candidate_neurocognitive_label": "Hebbian co-recall",
        "definition": (
            "Joint pre/post activity supplies a positive weight increment; "
            "repeated coactivation strengthens the connection without an error "
            "teacher, while forgetting hygiene remains separately declared."
        ),
        "falsifiable_behavior": (
            "Repeated complete co-retrieval episodes strengthen a symmetric "
            "learned-only edge, and that edge makes a previously disconnected "
            "partner retrievable; retrying one episode cannot learn it twice."
        ),
        "literature": [
            {
                "source": "/home/sicarii/Dropbox/Cognitive_Science.pdf",
                "locator": "printed pages 173-182, Hebbian learning and long-term potentiation",
            },
            {
                "source": "cognitive-science/chapters/ch07-network-approach.md",
                "locator": "Hebbian (unsupervised) learning: co-activation increments connection weight",
            },
            {
                "source": "Gerstner, Kistler, Naud & Paninski, Neuronal Dynamics",
                "locator": "section 19.2.1, equation 19.3 and paragraph following equation 19.4",
            },
        ],
        "implementation": {
            "module": "siacoretrieval", "callable": "learn_coretrieval",
            "component": "co-retrieval-strengthening",
        },
        "task_classes": ["associative-multi-hop"],
        "intervention": "learned-co-retrieval-edges-only-v1",
        "primary_metric": "recall_at_k",
    },
    "maintained-workspace": {
        "product_label": "Maintained workspace",
        "candidate_neurocognitive_label": "Global Workspace",
        "definition": (
            "Candidates compete at a selective ignition boundary; selected "
            "content persists for a bounded interval and the same maintained "
            "payload is made available to every declared consumer."
        ),
        "falsifiable_behavior": (
            "Above-threshold activation selects a bounded winner set, preserves "
            "it against weaker challengers until explicit release or expiry, and "
            "broadcasts byte-equivalent content to the complete consumer roster."
        ),
        "literature": [
            {
                "source": "Dehaene, Kerszberg & Changeux (1998), A neuronal model of a global workspace in effortful cognitive tasks",
                "locator": "Theoretical Premises: Selective Gating and Spatio-Temporal Dynamics; Simulation Results: maintained activity",
            },
            {
                "source": "cognitive-science/chapters/ch05-cognitive-approach-2.md",
                "locator": "Working memory: active workspace and executive control",
            },
        ],
        "implementation": {
            "module": "siaworkspace", "callable": "advance_workspace",
            "component": "maintained-workspace",
        },
        "task_classes": ["recency-heavy", "associative-multi-hop"],
        "intervention": "activation-competition-maintenance-and-broadcast-v1",
        "primary_metric": "mrr",
    },
    "typed-fan-spreading": {
        "product_label": "Typed graph propagation",
        "candidate_neurocognitive_label": "HippoRAG-style spreading activation",
        "definition": (
            "Activation propagates from retrieval cues through typed semantic "
            "links, weakens across distance, and divides over a complete outgoing "
            "fan so highly connected cues contribute less per neighbor."
        ),
        "falsifiable_behavior": (
            "A query seed reaches an unseeded multi-hop candidate outside the "
            "dense result window, while hop attenuation and capped complete-fan "
            "accounting bound the propagated signal."
        ),
        "literature": [
            {
                "source": "/home/sicarii/Dropbox/Cognitive_Science.pdf",
                "locator": "printed pages 203-210, semantic networks and spreading activation",
            },
            {
                "source": "cognitive-science/chapters/ch07-network-approach.md",
                "locator": "Semantic networks: typed links, distance weakening, and degree of fan",
            },
            {
                "source": "Collins & Loftus (1975), A spreading-activation theory of semantic processing",
                "locator": "spreading activation model and fan-dependent propagation",
            },
            {
                "source": "Gutiérrez et al. (2024), HippoRAG, NeurIPS",
                "locator": "knowledge-graph retrieval with query-seeded Personalized PageRank",
            },
        ],
        "implementation": {
            "module": "siaspreading", "callable": "spread",
            "component": "typed-fan-spreading",
        },
        "task_classes": ["associative-multi-hop"],
        "intervention": "query-seeded-typed-multihop-expansion-v1",
        "primary_metric": "recall_at_k",
    },
    "prediction-conditioned-encoding": {
        "product_label": "Prediction-conditioned encoding",
        "candidate_neurocognitive_label": None,
        "definition": (
            "Novelty is evaluated prequentially against stored frequency or "
            "context prediction before counts update; a novelty/plasticity "
            "hypothesis predicts stronger later accessibility after mismatch."
        ),
        "falsifiable_behavior": (
            "A surprising event receives greater encoding strength than a "
            "repeated event under the frozen map, then updates the prediction, "
            "and the strength difference changes later held-out retrieval."
        ),
        "literature": [
            {
                "source": "Xu et al. (2021), Novelty is not surprise",
                "locator": "equations 1-2, relative novelty versus conditional surprise",
            },
            {
                "source": "Lisman & Grace (2005), The hippocampal-VTA loop: controlling the entry of information into long-term memory",
                "locator": "novelty-prediction mismatch and enhanced plasticity hypothesis; doi:10.1016/j.neuron.2005.05.002",
            },
        ],
        "implementation": {
            "module": "siaencoding", "callable": "replay_encoding",
            "component": "prediction-conditioned-encoding",
        },
        "task_classes": ["novelty"],
        "intervention": "prequential-novelty-to-encoding-strength-v1",
        "primary_metric": "mrr",
    },
    "replay-gist": {
        "product_label": "Witnessed replay gist",
        "candidate_neurocognitive_label": "sleep/gist consolidation",
        "definition": (
            "A fixed episodic population is replayed into a slower shared "
            "representation whose readout captures recurring structure while "
            "the original episodes and exceptions remain available."
        ),
        "falsifiable_behavior": (
            "Offline replay changes accessibility of an already witnessed "
            "episode meaning, durably adds a provenance-bound gist, improves "
            "later meaning retrieval, and neither deletes nor rewrites any episode."
        ),
        "literature": [
            {
                "source": "/home/sicarii/Dropbox/Cognitive_Science.pdf",
                "locator": "printed pages 173-182, hippocampal memory and consolidation",
            },
            {
                "source": "cognitive-science/chapters/ch06-neuroscience-approach.md",
                "locator": "Consolidation: hippocampal transfer to long-term memory",
            },
            {
                "source": "Schapiro et al. (2017), Complementary learning systems within the hippocampus",
                "locator": "Methods: Learning and Testing; representational analyses after interleaved learning",
            },
        ],
        "implementation": {
            "module": "siagist", "callable": "replay_gist",
            "component": "replay-gist",
        },
        "task_classes": ["consolidation-gist"],
        "intervention": "witnessed-offline-replay-gist-readout-v1",
        "primary_metric": "mrr",
    },
}


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf-8")


def _digest(label):
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _body_digest(value, field):
    return hashlib.sha256(_canonical({
        key: item for key, item in value.items() if key != field
    })).hexdigest()


def _expected_entry(product_id):
    expected = copy.deepcopy(MECHANISMS[product_id])
    expected["product_id"] = product_id
    expected["operator_neurocognitive_label"] = OPERATOR_LABELS[product_id]
    expected["claim_eligibility"] = CLAIM_ELIGIBILITY[product_id]
    expected["benchmark"] = {
        **copy.deepcopy(COMMON_BENCHMARK),
        "arm": "dense-plus-only-" + product_id,
        "intervention": expected.pop("intervention"),
        "task_classes": expected.pop("task_classes"),
        "primary_metric": expected.pop("primary_metric"),
        "behavior_witness": WITNESS_REQUIREMENTS[product_id],
    }
    expected["claim_wording"] = {
        "admitted": None if expected["candidate_neurocognitive_label"] is None else (
            expected["candidate_neurocognitive_label"]
            + " improved its registered primary metric over the descriptor-bound "
            "raw-vector dense baseline on the pinned held-out task scope."),
        "stripped": (
            expected["product_label"]
            + "; cognitive ancestry only, with no admitted held-out win."
        ),
    }
    return expected


def _behavior_witness(product_id):
    common = {
        "schema": "sia-cognitive-behavior-witness-v1",
        "mechanism_id": product_id,
        "requirement": WITNESS_REQUIREMENTS[product_id],
        "status": "complete",
        "artifact_sha256": _digest(product_id + ":behavior-witness"),
    }
    if product_id == "maintained-workspace":
        payload = _digest(product_id + ":delivered-payload")
        return {
            **common,
            "consumer_roster": ["resident-status", "context-selection"],
            "consumer_roster_sha256": _digest(product_id + ":consumer-roster"),
            "payload_sha256": payload,
            "delivery_receipts": [
                {
                    "consumer": consumer,
                    "payload_sha256": payload,
                    "status": "delivered-and-acknowledged",
                    "receipt_sha256": _digest(
                        product_id + ":delivery:" + consumer),
                }
                for consumer in ("resident-status", "context-selection")
            ],
        }
    if product_id == "prediction-conditioned-encoding":
        return {
            **common,
            "signal": "prequential-frequency-or-context-information",
            "reward_prediction_error_witness": None,
            "plasticity_gain_witness": None,
        }
    return common


def _jackal_metric(product_id, metric):
    return {
        "metric": metric,
        "scope": "registered-heldout-task-classes",
        "direction": "lower" if metric == "query_latency_ms" else "higher",
        "baseline_observation_sha256": _digest(product_id + ":baseline:" + metric),
        "arm_observation_sha256": _digest(product_id + ":arm:" + metric),
        "fidelity_dimensions": (
            FIDELITY_DIMENSIONS if metric == "sia_memory_fidelity" else []),
        "jackal_artifact": {
            "tool": "jackal_exact",
            "request_sha256": _digest(product_id + ":request:" + metric),
            "receipt_sha256": _digest(product_id + ":receipt:" + metric),
        },
    }


def _evidence(registry, product_id):
    entry = _expected_entry(product_id)
    primary = entry["benchmark"]["primary_metric"]
    metrics = []
    for metric in REQUIRED_METRICS:
        metrics.append(_jackal_metric(product_id, metric))
    value = {
        "schema": EVIDENCE_SCHEMA,
        "mechanism_id": product_id,
        "registry_sha256": registry["registry_sha256"],
        "dataset": {
            "source": COMMON_BENCHMARK["dataset_source"],
            "manifest_sha256": _digest("heldout:manifest"),
            "capture_sha256": _digest("heldout:capture"),
            "selection_sha256": _digest("heldout:selection"),
            "heldout_query_roster_sha256": _digest("heldout:queries"),
            "heldout_target_roster_sha256": _digest("heldout:targets"),
            "split": "heldout", "tuning_split": "calibration", "complete": True,
        },
        "implementation": {
            **entry["implementation"],
            "source_sha256": _digest(product_id + ":implementation"),
            "policy_sha256": _digest(product_id + ":policy"),
        },
        "causal_comparison": {
            "baseline_id": BASELINE_ID,
            "control_run_sha256": _digest("heldout:dense-control-run"),
            "arm_id": entry["benchmark"]["arm"],
            "arm_run_sha256": _digest(product_id + ":arm-run"),
            "intervention": entry["benchmark"]["intervention"],
            "task_classes": entry["benchmark"]["task_classes"],
            "causal_unit": COMMON_BENCHMARK["causal_unit"],
            "same_query_roster": True,
            "same_target_roster": True,
            "same_engine_index_model_config": True,
            "other_mechanisms": COMMON_BENCHMARK["other_mechanisms"],
            "complete": True,
        },
        "behavior_witness": _behavior_witness(product_id),
        "chronology": {
            "policy": CHRONOLOGY,
            "order": [
                {"event": "registry-and-policy-frozen", "artifact_sha256": _digest(product_id + ":freeze")},
                {"event": "heldout-run-started", "artifact_sha256": _digest(product_id + ":start")},
                {"event": "heldout-results-opened", "artifact_sha256": _digest(product_id + ":open")},
            ],
            "no_heldout_tuning": True,
        },
        "metrics": metrics,
        "inference": {
            "requirement": INFERENCE_REQUIREMENT,
            "paired_unit": "complete-source-dependency-component-v1",
            "test": "one-sided-positive-sign-exact-binomial-tail-v1",
            "alternative": "greater",
            "multiplicity": "fixed-familywise-correction-v1",
            "jackal_artifact": {
                "tool": "jackal_hypothesis",
                "request_sha256": _digest(product_id + ":inference-request"),
                "receipt_sha256": _digest(product_id + ":inference-receipt"),
            },
        },
        "decision": {
            "primary_metric": primary,
            "rule": WIN_RULE,
        },
        "non_claims": EVIDENCE_NON_CLAIMS,
        "evidence_sha256": "",
    }
    value["evidence_sha256"] = _body_digest(value, "evidence_sha256")
    return value


def _verification(evidence):
    product_id = evidence["mechanism_id"]
    primary = evidence["decision"]["primary_metric"]
    artifacts = []
    for metric in evidence["metrics"]:
        name = metric["metric"]
        artifact = metric["jackal_artifact"]
        artifacts.append({
            "kind": "metric", "metric": name,
            "request_sha256": artifact["request_sha256"],
            "receipt_sha256": artifact["receipt_sha256"],
            "verification_receipt_sha256": _digest(
                product_id + ":verification:" + name),
            "baseline_observation_sha256": metric["baseline_observation_sha256"],
            "arm_observation_sha256": metric["arm_observation_sha256"],
            "status": "exact",
            "parsed": "synthetic-retained-expression:" + product_id + ":" + name,
            "relation": "greater" if name == primary else "equal",
            "reason": None,
            "consequence_ceiling": "informational",
            "non_claims": JACKAL_NON_CLAIMS,
        })
    inference = evidence["inference"]["jackal_artifact"]
    artifacts.append({
        "kind": "inference", "metric": "heldout_inference",
        "request_sha256": inference["request_sha256"],
        "receipt_sha256": inference["receipt_sha256"],
        "verification_receipt_sha256": _digest(
            product_id + ":inference-verification"),
        "status": "model-based",
        "parsed": "synthetic-retained-model:" + product_id,
        "decision": "supports-registered-alternative",
        "reason": None,
        "assumptions": [
            "fixed admitted component roster",
            "independent component signs conditional on the null",
            "constant null positive-sign probability among non-ties",
        ],
        "consequence_ceiling": "informational",
        "non_claims": JACKAL_NON_CLAIMS,
    })
    result = {
        "schema": VERIFICATION_SCHEMA,
        "status": "verified",
        "reason": None,
        "evidence_sha256": evidence["evidence_sha256"],
        "operator_expectations_sha256": OPERATOR_EXPECTATIONS_SHA256,
        "verifier": {
            "entrypoint": JACKAL_VERIFY_ARTIFACT,
            "entrypoint_sha256": _digest("jackal-verify-artifact-entrypoint"),
            "runtime_sha256": _digest("jackal-private-runtime"),
            "operator_expectations_path": JACKAL_OPERATOR_EXPECTATIONS,
            "execution_policy": "descriptor-bound-owner-private-front-door-v1",
        },
        "behavior": _verified_behavior(evidence),
        "artifacts": artifacts,
        "complete": True,
        "non_claims": VERIFICATION_NON_CLAIMS,
        "verification_sha256": "",
    }
    result["verification_sha256"] = _body_digest(
        result, "verification_sha256")
    return result


def _verified_behavior(evidence):
    witness = evidence["behavior_witness"]
    result = {
        "schema": "sia-cognitive-behavior-verification-v1",
        "status": "verified",
        "mechanism_id": evidence["mechanism_id"],
        "requirement": witness["requirement"],
        "artifact_sha256": witness["artifact_sha256"],
        "receipt_archive_generation_sha256": _digest(
            evidence["mechanism_id"] + ":behavior-receipt-archive"),
        "delivery_receipts": copy.deepcopy(
            witness.get("delivery_receipts", [])),
        "complete": True,
        "non_claims": BEHAVIOR_VERIFICATION_NON_CLAIMS,
    }
    return result


def _frontdoor_result(artifact, verifier):
    return {
        "schema": "sia-cognitive-jackal-artifact-verification-v1",
        "status": "accepted",
        "artifact": copy.deepcopy(artifact),
        "verifier": copy.deepcopy(verifier),
        "non_claims": VERIFICATION_NON_CLAIMS,
    }


def _reseal(value):
    value["evidence_sha256"] = _body_digest(value, "evidence_sha256")
    return value


def _reseal_verification(value):
    value["verification_sha256"] = _body_digest(
        value, "verification_sha256")
    return value


_AUTO_VERIFICATION = object()


class CognitiveMechanismRegistryContract(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("siacognitiveregistry")
        except ModuleNotFoundError as exc:
            self.fail(
                "the bounded six-mechanism evidence/claim registry must exist: "
                + str(exc))

    def registry(self):
        return self.module.mechanism_registry()

    def decide(self, product_id, evidence=None, *, registry_pin=None,
               evidence_pin=None, verification=_AUTO_VERIFICATION,
               operator_expectations_pin=OPERATOR_EXPECTATIONS_SHA256):
        registry = self.registry()
        if verification is _AUTO_VERIFICATION:
            verification = _verification(evidence)
        with mock.patch.object(
                self.module, "verify_retained_evidence",
                return_value=copy.deepcopy(verification)) as verifier:
            result = self.module.decide_claim(
                product_id, evidence,
                expected_registry_sha256=(
                    registry["registry_sha256"] if registry_pin is None
                    else registry_pin),
                expected_evidence_sha256=(
                    evidence.get("evidence_sha256")
                    if evidence is not None and evidence_pin is None
                    else evidence_pin),
                expected_operator_expectations_sha256=operator_expectations_pin,
            )
        self.last_verifier = verifier
        return result

    def assert_stripped(self, result, product_id, reason):
        expected = _expected_entry(product_id)
        self.assertEqual(result["schema"], DECISION_SCHEMA)
        self.assertEqual(result["mechanism_id"], product_id)
        self.assertEqual(result["status"], "stripped")
        self.assertEqual(result["disposition"], "strip-neurocognitive-label")
        self.assertEqual(result["reason"], reason)
        self.assertEqual(result["public_label"], expected["product_label"])
        self.assertIsNone(result["neurocognitive_label"])
        self.assertEqual(result["claim"], expected["claim_wording"]["stripped"])
        self.assertEqual(result["consequence_ceiling"], "informational")
        self.assertEqual(result["registry_non_claims"], REGISTRY_NON_CLAIMS)

    def test_public_api_is_small_and_the_ordinary_result_is_strip(self):
        self.assertEqual(
            list(inspect.signature(self.module.mechanism_registry).parameters), [])
        parameters = inspect.signature(self.module.decide_claim).parameters
        self.assertEqual(list(parameters), [
            "mechanism_id", "evidence_bundle", "expected_registry_sha256",
            "expected_evidence_sha256", "expected_operator_expectations_sha256",
        ])
        self.assertIsNone(parameters["evidence_bundle"].default)
        self.assertIsNone(parameters["expected_registry_sha256"].default)
        self.assertIsNone(parameters["expected_evidence_sha256"].default)
        self.assertIsNone(
            parameters["expected_operator_expectations_sha256"].default)
        for name in ("expected_registry_sha256", "expected_evidence_sha256",
                     "expected_operator_expectations_sha256"):
            self.assertEqual(parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)
        verification = inspect.signature(
            self.module.verify_retained_evidence).parameters
        self.assertEqual(list(verification), [
            "evidence_bundle", "expected_evidence_sha256",
            "expected_operator_expectations_sha256",
        ])
        self.assertTrue(all(
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            and parameter.default is inspect.Parameter.empty
            for parameter in verification.values()))
        with mock.patch.object(
                self.module, "verify_retained_evidence",
                side_effect=AssertionError("verified absent evidence")) as verifier:
            result = self.module.decide_claim("usage-salience")
        verifier.assert_not_called()
        self.assert_stripped(result, "usage-salience", "evidence-required")
        self.assertEqual(result["jackal_statuses"], {})
        self.assertEqual(result["evidence_sha256"], None)

    def test_retained_receipts_are_reverified_through_the_fixed_front_door(self):
        registry = self.registry()
        evidence = _evidence(registry, "usage-salience")
        expected = _verification(evidence)
        verifier_identity = expected["verifier"]
        replies = [
            _frontdoor_result(artifact, verifier_identity)
            for artifact in expected["artifacts"]
        ]
        helper = self.module._verify_retained_receipt
        parameters = inspect.signature(helper).parameters
        self.assertEqual(list(parameters), [
            "receipt_sha256", "expected_request_sha256", "artifact_kind",
            "metric", "expected_operator_expectations_sha256",
        ])
        self.assertTrue(all(
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            and parameter.default is inspect.Parameter.empty
            for parameter in parameters.values()))
        source = inspect.getsource(helper)
        self.assertEqual(
            self.module.JACKAL_VERIFY_ARTIFACT, JACKAL_VERIFY_ARTIFACT)
        self.assertEqual(
            self.module.JACKAL_OPERATOR_EXPECTATIONS,
            JACKAL_OPERATOR_EXPECTATIONS)
        self.assertIn("JACKAL_VERIFY_ARTIFACT", source)
        self.assertIn("JACKAL_OPERATOR_EXPECTATIONS", source)
        self.assertIn("--artifact-file", source)
        self.assertIn("--expectations", source)
        self.assertIn("--runtime", source)
        self.assertNotIn("shell=True", source.replace(" ", ""))

        behavior_helper = self.module._verify_retained_behavior_witness
        behavior_parameters = inspect.signature(behavior_helper).parameters
        self.assertEqual(list(behavior_parameters), [
            "mechanism_id", "evidence_sha256", "requirement",
            "artifact_sha256",
        ])
        self.assertTrue(all(
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            and parameter.default is inspect.Parameter.empty
            for parameter in behavior_parameters.values()))

        with mock.patch.object(
                self.module, "_verify_retained_receipt",
                side_effect=replies) as front_door, \
                mock.patch.object(
                    self.module, "_verify_retained_behavior_witness",
                    return_value=expected["behavior"]) as behavior_front_door:
            result = self.module.verify_retained_evidence(
                evidence_bundle=evidence,
                expected_evidence_sha256=evidence["evidence_sha256"],
                expected_operator_expectations_sha256=(
                    OPERATOR_EXPECTATIONS_SHA256),
            )
        self.assertEqual(result, expected)
        self.assertEqual(front_door.call_args_list, [
            mock.call(
                receipt_sha256=row["receipt_sha256"],
                expected_request_sha256=row["request_sha256"],
                artifact_kind=row["kind"], metric=row["metric"],
                expected_operator_expectations_sha256=(
                    OPERATOR_EXPECTATIONS_SHA256),
            )
            for row in expected["artifacts"]
        ])
        behavior_front_door.assert_called_once_with(
            mechanism_id=evidence["mechanism_id"],
            evidence_sha256=evidence["evidence_sha256"],
            requirement=evidence["behavior_witness"]["requirement"],
            artifact_sha256=evidence["behavior_witness"]["artifact_sha256"],
        )

    def test_stable_file_reads_use_nofollow_fds_and_fstat_generations(self):
        helper = self.module._read_stable_regular
        source = inspect.getsource(helper)
        self.assertIn("os.open", source)
        self.assertIn("O_NOFOLLOW", source)
        self.assertGreaterEqual(source.count("os.fstat"), 2)
        self.assertNotIn(".read_bytes(", source)
        self.assertNotIn(".lstat(", source)
        for field in (
                "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"):
            self.assertIn(field, source)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "operator-owned.json"
            held = root / "operator-owned.held"
            attacker = root / "attacker.json"
            trusted_bytes = b'{"source":"operator"}'
            attacker_bytes = b'{"source":"caller"}'
            target.write_bytes(trusted_bytes)
            attacker.write_bytes(attacker_bytes)
            ordinary_read_bytes = Path.read_bytes

            def swap_named_path(path):
                if path != target:
                    return ordinary_read_bytes(path)
                target.rename(held)
                target.symlink_to(attacker)
                try:
                    return ordinary_read_bytes(target)
                finally:
                    target.unlink()
                    held.rename(target)

            with mock.patch.object(
                    Path, "read_bytes", autospec=True,
                    side_effect=swap_named_path):
                raw, _ = helper(target, max_bytes=4096)
        self.assertEqual(raw, trusted_bytes)

    def test_runtime_identity_binds_descriptor_bytes_and_package_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_root = root / "runtimes"
            runtime_root.mkdir(mode=0o700)
            runtime = runtime_root / "fixture-runtime"
            runtime.mkdir(mode=0o700)
            package_sha256 = _digest("runtime-package")
            descriptor = {
                "schema": "jackal-codex-plugin-runtime-v1",
                "epoch": "fixture-epoch",
                "package_sha256": package_sha256,
                "package_size": 1,
                "runtime_path": str(runtime),
            }
            descriptor_raw = _canonical(descriptor)
            descriptor_path = root / "runtime.json"
            descriptor_path.write_bytes(descriptor_raw)
            descriptor_sha256 = hashlib.sha256(descriptor_raw).hexdigest()
            expected_binding = hashlib.sha256(_canonical({
                "descriptor_sha256": descriptor_sha256,
                "package_sha256": package_sha256,
            })).hexdigest()

            with mock.patch.object(
                    self.module, "JACKAL_RUNTIME_DESCRIPTOR",
                    str(descriptor_path)), mock.patch.object(
                    self.module, "JACKAL_RUNTIME_ROOT", str(runtime_root),
                    create=True):
                resolved, runtime_binding = self.module._runtime_path()

        self.assertEqual(resolved, runtime.resolve())
        self.assertEqual(runtime_binding, expected_binding)

    def test_retained_request_pin_is_recovered_from_receipt_bytes(self):
        request = {"operation": "registered-comparison-fixture"}
        canonical_pin = hashlib.sha256(_canonical(request)).hexdigest()
        self.assertEqual(
            self.module._retained_request_sha256({"request": request}),
            canonical_pin,
        )
        committed_pin = _digest("jackal-request-commitment")
        committed_request = {
            **request,
            "request_commitment_b64": base64.b64encode(
                committed_pin.encode("ascii")).decode("ascii"),
        }
        self.assertEqual(
            self.module._retained_request_sha256(
                {"request": committed_request}),
            committed_pin,
        )
        for malformed in (None, "not-base64", base64.b64encode(
                b"not-a-sha256").decode("ascii")):
            bad_request = dict(request)
            if malformed is not None:
                bad_request["request_commitment_b64"] = malformed
            else:
                bad_request = []
            with self.subTest(commitment=malformed), self.assertRaises(
                    self.module._BoundaryError) as refused:
                self.module._retained_request_sha256(
                    {"request": bad_request})
            self.assertEqual(
                refused.exception.reason,
                "retained-receipt-request-pin-mismatch",
            )

    def test_front_door_launch_uses_held_fds_after_names_disappear(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entrypoint = root / "verify_artifact.py"
            expectations = root / "expectations.json"
            archive = root / "receipts"
            runtime = root / "runtime"
            archive.mkdir(mode=0o700)
            runtime.mkdir(mode=0o755)
            runtime.chmod(0o755)
            entrypoint_raw = b"#!/usr/bin/env python3\n"
            expectations_raw = _canonical({
                "schema": "khephri.jackal-expectations-v1",
            })
            entrypoint.write_bytes(entrypoint_raw)
            expectations.write_bytes(expectations_raw)
            receipt_sha256 = _digest("held-receipt")
            request = {"operation": "registered-comparison-fixture"}
            request_sha256 = hashlib.sha256(_canonical(request)).hexdigest()
            receipt_raw = _canonical({
                "schema": "jackal-formal-receipt-v1",
                "receipt_digest_sha256": receipt_sha256,
                "request": request,
            })
            receipt_path = archive / (receipt_sha256 + ".json")
            receipt_path.write_bytes(receipt_raw)
            expected_expectations_sha256 = hashlib.sha256(
                expectations_raw).hexdigest()
            captured = {}

            def fake_run(command, **kwargs):
                for original in (entrypoint, expectations, receipt_path, runtime):
                    original.rename(original.with_name(original.name + ".moved"))
                captured["command"] = list(command)
                captured["cwd"] = kwargs.get("cwd")
                captured["pass_fds"] = tuple(kwargs.get("pass_fds", ()))

                def flag_value(flag):
                    return command[command.index(flag) + 1]

                captured["verifier"] = command[3]
                captured["expectations"] = flag_value("--expectations")
                captured["artifact"] = flag_value("--artifact-file")
                captured["runtime"] = flag_value("--runtime")
                for name in ("verifier", "expectations", "artifact"):
                    value = captured[name]
                    captured[name + "_bytes"] = Path(value).read_bytes()
                captured["runtime_is_dir"] = Path(captured["cwd"]).is_dir()
                captured["held_regular_bytes"] = []
                for descriptor in captured["pass_fds"]:
                    info = os.fstat(descriptor)
                    if stat.S_ISREG(info.st_mode):
                        captured["held_regular_bytes"].append(
                            os.pread(descriptor, info.st_size, 0))
                private_info = os.stat(Path(captured["expectations"]).parent)
                captured["private_mode"] = stat.S_IMODE(private_info.st_mode)
                captured["private_owner"] = private_info.st_uid
                return mock.Mock(
                    stdout=json.dumps({
                        "schema": "khephri.jackal-verify-v1",
                        "status": "verified",
                    }),
                    stderr="", returncode=0,
                )

            with mock.patch.object(
                    self.module, "JACKAL_VERIFY_ARTIFACT", str(entrypoint)), \
                    mock.patch.object(
                        self.module, "JACKAL_OPERATOR_EXPECTATIONS",
                        str(expectations)), \
                    mock.patch.object(
                        self.module, "JACKAL_RECEIPT_ARCHIVE", str(archive)), \
                    mock.patch.object(
                        self.module, "_runtime_path",
                        return_value=(runtime, _digest("runtime-binding"))), \
                    mock.patch.object(
                        self.module, "_run_bounded_front_door",
                        side_effect=fake_run) as runner:
                self.module._verify_retained_receipt(
                    receipt_sha256=receipt_sha256,
                    expected_request_sha256=request_sha256,
                    artifact_kind="metric", metric="recall_at_k",
                    expected_operator_expectations_sha256=(
                        expected_expectations_sha256),
                )

            runner.assert_called_once()
            self.assertIn(
                "_retained_request_sha256",
                inspect.getsource(self.module._verify_retained_receipt),
            )
            command = captured["command"]
            self.assertNotIn(str(entrypoint), command)
            self.assertNotIn(str(expectations), command)
            self.assertNotIn(str(receipt_path), command)
            self.assertNotIn(str(runtime), command)
            self.assertTrue(captured["verifier"].startswith("/proc/self/fd/"))
            private_parent = Path(captured["expectations"]).parent
            self.assertEqual(Path(captured["artifact"]).parent, private_parent)
            self.assertEqual(captured["verifier_bytes"], entrypoint_raw)
            self.assertEqual(captured["expectations_bytes"], expectations_raw)
            self.assertEqual(captured["artifact_bytes"], receipt_raw)
            self.assertIn(entrypoint_raw, captured["held_regular_bytes"])
            self.assertIn(expectations_raw, captured["held_regular_bytes"])
            self.assertIn(receipt_raw, captured["held_regular_bytes"])
            self.assertTrue(captured["runtime_is_dir"])
            descriptor_numbers = {
                int(captured[name].rsplit("/", 1)[1])
                for name in ("verifier",)
            }
            self.assertTrue(captured["cwd"].startswith("/proc/self/fd/"))
            descriptor_numbers.add(int(captured["cwd"].rsplit("/", 1)[1]))
            self.assertTrue(
                descriptor_numbers.issubset(set(captured["pass_fds"])))
            self.assertEqual(captured["runtime"], ".")
            self.assertNotEqual(Path(captured["cwd"]), runtime)
            self.assertEqual(captured["private_mode"], 0o700)
            self.assertEqual(captured["private_owner"], os.getuid())

    def test_front_door_output_and_return_code_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entrypoint = root / "verify_artifact.py"
            expectations = root / "expectations.json"
            archive = root / "receipts"
            runtime = root / "runtime"
            archive.mkdir(mode=0o700)
            runtime.mkdir(mode=0o700)
            entrypoint.write_bytes(b"#!/usr/bin/env python3\n")
            expectations_raw = _canonical({
                "schema": "khephri.jackal-expectations-v1",
            })
            expectations.write_bytes(expectations_raw)
            receipt_sha256 = _digest("bounded-output-receipt")
            request = {"operation": "bounded-output-fixture"}
            request_sha256 = hashlib.sha256(_canonical(request)).hexdigest()
            (archive / (receipt_sha256 + ".json")).write_bytes(_canonical({
                "schema": "jackal-formal-receipt-v1",
                "receipt_digest_sha256": receipt_sha256,
                "request": request,
            }))
            expectations_sha256 = hashlib.sha256(
                expectations_raw).hexdigest()
            valid_stdout = json.dumps({
                "schema": "khephri.jackal-verify-v1",
                "status": "verified",
            })
            output_cap = len(valid_stdout.encode("utf-8"))

            def invoke(*, stdout, stderr, returncode):
                completed = mock.Mock(
                    stdout=stdout, stderr=stderr, returncode=returncode)
                with mock.patch.object(
                        self.module, "JACKAL_VERIFY_ARTIFACT",
                        str(entrypoint)), mock.patch.object(
                        self.module, "JACKAL_OPERATOR_EXPECTATIONS",
                        str(expectations)), mock.patch.object(
                        self.module, "JACKAL_RECEIPT_ARCHIVE", str(archive)), \
                        mock.patch.object(
                            self.module, "MAX_FRONT_DOOR_OUTPUT_BYTES",
                            output_cap), mock.patch.object(
                        self.module, "_runtime_path",
                        return_value=(runtime, _digest("runtime-binding"))), \
                        mock.patch.object(
                            self.module, "_run_bounded_front_door",
                            return_value=completed):
                    return self.module._verify_retained_receipt(
                        receipt_sha256=receipt_sha256,
                        expected_request_sha256=request_sha256,
                        artifact_kind="metric", metric="recall_at_k",
                        expected_operator_expectations_sha256=(
                            expectations_sha256),
                    )

            source = inspect.getsource(self.module._verify_retained_receipt)
            self.assertNotIn("capture_output=True", source.replace(" ", ""))
            cases = (
                (
                    "stdout", valid_stdout + " ", "", 0,
                    "jackal-front-door-stdout-oversize",
                ),
                (
                    "stderr", valid_stdout, "x" + valid_stdout, 0,
                    "jackal-front-door-stderr-oversize",
                ),
                (
                    "return-code", valid_stdout, "", 9,
                    "jackal-front-door-nonzero-exit",
                ),
            )
            for label, stdout, stderr, returncode, reason in cases:
                with self.subTest(boundary=label):
                    result = invoke(
                        stdout=stdout, stderr=stderr,
                        returncode=returncode)
                    self.assertEqual(result["status"], "refused")
                    self.assertEqual(result["reason"], reason)
                    self.assertEqual(
                        result["non_claims"], VERIFICATION_NON_CLAIMS)

    def test_bounded_runner_stops_each_stream_at_the_byte_ceiling(self):
        environment = {
            "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        for stream, descriptor, reason in (
                ("stdout", 1, "jackal-front-door-stdout-oversize"),
                ("stderr", 2, "jackal-front-door-stderr-oversize")):
            with self.subTest(stream=stream):
                command = [
                    "/usr/bin/python3", "-I", "-B", "-c",
                    "import os; os.write(%d, b'x' * 65)" % descriptor,
                ]
                with self.assertRaises(
                        self.module._BoundaryError) as refused:
                    self.module._run_bounded_front_door(
                        command, cwd="/", pass_fds=(), timeout=5,
                        env=environment, max_output_bytes=64)
                self.assertEqual(refused.exception.reason, reason)

    def test_registry_is_exactly_six_honest_products_with_grounded_contracts(self):
        result = self.registry()
        self.assertEqual(set(result), {
            "schema", "status", "baseline", "required_metrics", "mechanisms",
            "verification", "resource_limits", "non_claims", "registry_sha256",
        })
        self.assertEqual(result["schema"], REGISTRY_SCHEMA)
        self.assertEqual(result["status"], "candidate-only")
        self.assertEqual(result["baseline"], {
            "product_id": BASELINE_ID,
            "lane": "raw_vector",
            "implementation": {
                "module": "siacognitivebaseline", "callable": "run_baseline_v2",
            },
            "role": "same-pinned-input causal control",
            "retrieval_transform": "none",
        })
        self.assertEqual(result["required_metrics"], REQUIRED_METRICS)
        self.assertEqual(result["verification"], {
            "method": "fresh-retained-receipt-reverification-v1",
            "api": "verify_retained_evidence",
            "entrypoint": JACKAL_VERIFY_ARTIFACT,
            "operator_expectations": JACKAL_OPERATOR_EXPECTATIONS,
            "execution_policy": "descriptor-bound-owner-private-front-door-v1",
            "behavior_witnesses": "retained-artifact-reverification-required-v1",
            "caller_declared_results": "never-trusted",
        })
        self.assertEqual(result["non_claims"], REGISTRY_NON_CLAIMS)
        self.assertEqual(result["registry_sha256"], _body_digest(
            result, "registry_sha256"))
        limits = result["resource_limits"]
        self.assertEqual(set(limits), {
            "max_evidence_bytes", "max_metrics", "max_task_classes",
            "max_literature_citations",
        })
        self.assertTrue(all(type(value) is int and value > 0
                            for value in limits.values()))
        rows = result["mechanisms"]
        self.assertEqual([row["product_id"] for row in rows], list(MECHANISMS))
        self.assertEqual(len(rows), len(MECHANISMS))
        self.assertEqual({row["product_id"] for row in rows}, set(MECHANISMS))
        self.assertEqual(
            {row["operator_neurocognitive_label"] for row in rows},
            set(OPERATOR_LABELS.values()))
        for row in rows:
            with self.subTest(mechanism=row["product_id"]):
                self.assertEqual(row, _expected_entry(row["product_id"]))
                self.assertNotEqual(
                    row["product_label"], row["candidate_neurocognitive_label"])
                self.assertTrue(row["literature"])
                self.assertTrue(row["definition"])
                self.assertTrue(row["falsifiable_behavior"])
                self.assertEqual(
                    row["benchmark"]["required_metrics"], REQUIRED_METRICS)

    def test_each_mechanism_requires_its_own_complete_causal_heldout_bundle(self):
        registry = self.registry()
        separately_verified_runs = set()
        for product_id in MECHANISMS:
            evidence = _evidence(registry, product_id)
            before = copy.deepcopy(evidence)
            verification = _verification(evidence)
            result = self.decide(product_id, evidence)
            expected = _expected_entry(product_id)
            with self.subTest(mechanism=product_id):
                self.assertEqual(result["schema"], DECISION_SCHEMA)
                if expected["candidate_neurocognitive_label"] is None:
                    self.assert_stripped(
                        result, product_id,
                        "neurocognitive-label-permanently-stripped")
                else:
                    self.assertEqual(result["status"], "admitted")
                    self.assertEqual(
                        result["disposition"], "keep-neurocognitive-label")
                    self.assertEqual(result["reason"], "heldout-win-admitted")
                    self.assertEqual(result["public_label"],
                                     expected["candidate_neurocognitive_label"])
                    self.assertEqual(result["neurocognitive_label"],
                                     expected["candidate_neurocognitive_label"])
                    self.assertEqual(result["claim"],
                                     expected["claim_wording"]["admitted"])
                self.assertEqual(result["registry_sha256"],
                                 registry["registry_sha256"])
                self.assertEqual(result["evidence_sha256"],
                                 evidence["evidence_sha256"])
                self.assertEqual(result["verification_sha256"],
                                 verification["verification_sha256"])
                self.assertEqual(result["operator_expectations_sha256"],
                                 OPERATOR_EXPECTATIONS_SHA256)
                self.assertEqual(result["jackal_statuses"], {
                    **{metric: "exact" for metric in REQUIRED_METRICS},
                    "heldout_inference": "model-based",
                })
                self.assertEqual(
                    result["metric_evidence"],
                    [row for row in verification["artifacts"]
                     if row["kind"] == "metric"])
                self.assertEqual(
                    result["inference_evidence"],
                    next(row for row in verification["artifacts"]
                         if row["kind"] == "inference"))
                self.assertEqual(
                    result["behavior_evidence"], verification["behavior"])
                self.assertEqual(result["consequence_ceiling"], "informational")
                self.assertEqual(result["registry_non_claims"], REGISTRY_NON_CLAIMS)
                self.assertEqual(result["evidence_non_claims"], EVIDENCE_NON_CLAIMS)
                self.assertEqual(result["verification_non_claims"],
                                 VERIFICATION_NON_CLAIMS)
                self.assertEqual(evidence, before)
                self.last_verifier.assert_called_once_with(
                    evidence_bundle=evidence,
                    expected_evidence_sha256=evidence["evidence_sha256"],
                    expected_operator_expectations_sha256=(
                        OPERATOR_EXPECTATIONS_SHA256),
                )
            separately_verified_runs.add(
                evidence["causal_comparison"]["arm_run_sha256"])
        self.assertEqual(len(separately_verified_runs), len(MECHANISMS))

        first, second = list(MECHANISMS)[:2]
        foreign = _evidence(registry, first)
        self.assert_stripped(
            self.decide(second, foreign), second, "mechanism-evidence-mismatch")

    def test_tie_loss_and_jackal_refusal_are_reported_as_strips(self):
        registry = self.registry()
        product_id = "usage-salience"
        primary = MECHANISMS[product_id]["primary_metric"]

        evidence = _evidence(registry, product_id)
        tie = _verification(evidence)
        next(row for row in tie["artifacts"]
             if row["metric"] == primary)["relation"] = "equal"
        self.assert_stripped(
            self.decide(
                product_id, evidence,
                verification=_reseal_verification(tie)), product_id,
            "primary-not-strictly-better")

        loss = _verification(evidence)
        next(row for row in loss["artifacts"]
             if row["metric"] == "mrr")["relation"] = "less"
        self.assert_stripped(
            self.decide(
                product_id, evidence,
                verification=_reseal_verification(loss)), product_id,
            "required-metric-regression")

        refused = _verification(evidence)
        row = next(row for row in refused["artifacts"]
                   if row["metric"] == primary)
        row.update({
            "status": "refused", "relation": "unavailable",
            "reason": "synthetic-jackal-refusal",
        })
        result = self.decide(
            product_id, evidence,
            verification=_reseal_verification(refused))
        self.assert_stripped(result, product_id, "jackal-result-refused")
        self.assertEqual(result["jackal_statuses"][primary], "refused")
        self.assertEqual(result["jackal_refusals"], {
            primary: "synthetic-jackal-refusal",
        })

    def test_missing_fidelity_or_unrecognized_assurance_cannot_be_laundered(self):
        registry = self.registry()
        product_id = "prediction-conditioned-encoding"
        missing = _evidence(registry, product_id)
        missing["metrics"] = [
            row for row in missing["metrics"]
            if row["metric"] != "sia_memory_fidelity"
        ]
        self.assert_stripped(
            self.decide(product_id, _reseal(missing)), product_id,
            "missing-required-metric")

        evidence = _evidence(registry, product_id)
        local = _verification(evidence)
        local["artifacts"][0]["status"] = "computed-unverified"
        self.assert_stripped(
            self.decide(
                product_id, evidence,
                verification=_reseal_verification(local)), product_id,
            "unrecognized-jackal-status")

        dropped = _verification(evidence)
        dropped["artifacts"][0].pop("non_claims")
        self.assert_stripped(
            self.decide(
                product_id, evidence,
                verification=_reseal_verification(dropped)), product_id,
            "incomplete-jackal-result")

        no_inference = _evidence(registry, product_id)
        no_inference.pop("inference")
        _reseal(no_inference)
        with mock.patch.object(
                self.module, "verify_retained_evidence",
                side_effect=AssertionError("verified malformed evidence")) as verifier:
            result = self.module.decide_claim(
                product_id, no_inference,
                expected_registry_sha256=registry["registry_sha256"],
                expected_evidence_sha256=no_inference["evidence_sha256"],
                expected_operator_expectations_sha256=(
                    OPERATOR_EXPECTATIONS_SHA256),
            )
        verifier.assert_not_called()
        self.assert_stripped(result, product_id, "evidence-fields-invalid")

        unsupported = _verification(evidence)
        next(row for row in unsupported["artifacts"]
             if row["kind"] == "inference")["decision"] = (
                 "does-not-support-alternative")
        self.assert_stripped(
            self.decide(
                product_id, evidence,
                verification=_reseal_verification(unsupported)), product_id,
            "heldout-inference-not-supportive")

    def test_controlling_non_claims_cannot_be_replaced_with_caller_prose(self):
        registry = self.registry()
        product_id = "usage-salience"
        arbitrary = [
            "Caller says this disclaimer is equivalent and the claim may pass.",
        ]

        evidence = _evidence(registry, product_id)
        evidence["non_claims"] = arbitrary
        self.assert_stripped(
            self.decide(product_id, _reseal(evidence)), product_id,
            "evidence-fields-invalid")

        changes = (
            (
                "verification",
                lambda value: value.update({"non_claims": arbitrary}),
                "trusted-verification-refused",
            ),
            (
                "metric",
                lambda value: next(
                    row for row in value["artifacts"]
                    if row["kind"] == "metric"
                ).update({"non_claims": arbitrary}),
                "incomplete-jackal-result",
            ),
            (
                "inference",
                lambda value: next(
                    row for row in value["artifacts"]
                    if row["kind"] == "inference"
                ).update({"non_claims": arbitrary}),
                "incomplete-jackal-result",
            ),
            (
                "behavior",
                lambda value: value["behavior"].update(
                    {"non_claims": arbitrary}),
                "verification-behavior-witness-mismatch",
            ),
        )
        for label, change, reason in changes:
            evidence = _evidence(registry, product_id)
            verification = _verification(evidence)
            change(verification)
            with self.subTest(boundary=label):
                self.assert_stripped(
                    self.decide(
                        product_id, evidence,
                        verification=_reseal_verification(verification)),
                    product_id, reason)

        evidence = _evidence(registry, product_id)
        verification = _verification(evidence)
        verification["verifier"]["entrypoint"] = "/tmp/caller-verifier.py"
        self.assert_stripped(
            self.decide(
                product_id, evidence,
                verification=_reseal_verification(verification)),
            product_id, "trusted-verification-refused")

    def test_missing_changed_or_self_minted_pins_strip_the_claim(self):
        registry = self.registry()
        product_id = "typed-fan-spreading"
        evidence = _evidence(registry, product_id)
        self.assert_stripped(
            self.module.decide_claim(
                product_id, evidence,
                expected_registry_sha256=None,
                expected_evidence_sha256=evidence["evidence_sha256"],
                expected_operator_expectations_sha256=(
                    OPERATOR_EXPECTATIONS_SHA256)),
            product_id, "external-pin-required")
        self.assert_stripped(
            self.module.decide_claim(
                product_id, evidence,
                expected_registry_sha256=registry["registry_sha256"],
                expected_evidence_sha256=None,
                expected_operator_expectations_sha256=(
                    OPERATOR_EXPECTATIONS_SHA256)),
            product_id, "external-pin-required")
        with mock.patch.object(
                self.module, "verify_retained_evidence",
                side_effect=AssertionError("verified without operator pin")) as verifier:
            raw = self.module.decide_claim(
                product_id, evidence,
                expected_registry_sha256=registry["registry_sha256"],
                expected_evidence_sha256=evidence["evidence_sha256"],
                expected_operator_expectations_sha256=None,
            )
        verifier.assert_not_called()
        self.assert_stripped(
            raw, product_id, "trusted-verification-required")
        self.assert_stripped(
            self.decide(product_id, evidence, evidence_pin=_digest("foreign")),
            product_id, "external-evidence-pin-mismatch")

        changed = copy.deepcopy(evidence)
        changed["decision"]["rule"] = "caller-says-win"
        self.assert_stripped(
            self.decide(product_id, changed), product_id,
            "evidence-self-pin-mismatch")

        foreign_registry = _evidence(registry, product_id)
        foreign_registry["registry_sha256"] = _digest("foreign-registry")
        self.assert_stripped(
            self.decide(product_id, _reseal(foreign_registry)), product_id,
            "evidence-registry-mismatch")

    def test_raw_or_caller_forged_jackal_results_never_authorize_a_claim(self):
        registry = self.registry()
        product_id = "usage-salience"
        evidence = _evidence(registry, product_id)
        for row in evidence["metrics"]:
            self.assertEqual(set(row["jackal_artifact"]), {
                "tool", "request_sha256", "receipt_sha256",
            })
            self.assertFalse(
                {"status", "parsed", "relation", "decision"}
                & set(row["jackal_artifact"]))
        self.assertFalse(
            {"status", "parsed", "relation", "decision"}
            & set(evidence["inference"]["jackal_artifact"]))

        # Even a fully pinned raw bundle has no authority without a fresh call
        # through the module-owned retained-receipt verification boundary.
        refused_verification = _verification(evidence)
        refused_verification.update({
            "status": "refused", "reason": "retained-receipt-not-accepted",
            "complete": False, "artifacts": [],
        })
        result = self.decide(
            product_id, evidence,
            verification=_reseal_verification(refused_verification))
        self.assert_stripped(
            result, product_id, "trusted-verification-refused")
        self.assertEqual(
            result["verification_reason"], "retained-receipt-not-accepted")
        self.assertEqual(result["jackal_statuses"], {})

        forged = copy.deepcopy(evidence)
        forged["verification"] = _verification(evidence)
        _reseal(forged)
        with mock.patch.object(
                self.module, "verify_retained_evidence",
                side_effect=AssertionError("trusted caller verification")) as verifier:
            result = self.module.decide_claim(
                product_id, forged,
                expected_registry_sha256=registry["registry_sha256"],
                expected_evidence_sha256=forged["evidence_sha256"],
                expected_operator_expectations_sha256=(
                    OPERATOR_EXPECTATIONS_SHA256),
            )
        verifier.assert_not_called()
        self.assert_stripped(result, product_id, "evidence-fields-invalid")

        verification = _verification(evidence)
        verification["artifacts"][0]["receipt_sha256"] = _digest(
            "caller-minted-receipt")
        self.assert_stripped(
            self.decide(
                product_id, evidence,
                verification=_reseal_verification(verification)),
            product_id, "verification-artifact-pin-mismatch")

        verification = _verification(evidence)
        verification["operator_expectations_sha256"] = _digest(
            "caller-minted-expectations")
        self.assert_stripped(
            self.decide(
                product_id, evidence,
                verification=_reseal_verification(verification)),
            product_id, "verification-operator-expectations-mismatch")

    def test_chronology_or_heldout_tuning_failure_strips_even_a_numeric_win(self):
        registry = self.registry()
        product_id = "replay-gist"
        reversed_order = _evidence(registry, product_id)
        reversed_order["chronology"]["order"].reverse()
        self.assert_stripped(
            self.decide(product_id, _reseal(reversed_order)), product_id,
            "heldout-chronology-invalid")

        tuned = _evidence(registry, product_id)
        tuned["chronology"]["no_heldout_tuning"] = False
        self.assert_stripped(
            self.decide(product_id, _reseal(tuned)), product_id,
            "heldout-tuning-detected")

        calibration = _evidence(registry, product_id)
        calibration["dataset"]["split"] = "calibration"
        self.assert_stripped(
            self.decide(product_id, _reseal(calibration)), product_id,
            "heldout-dataset-required")

    def test_dense_control_and_single_intervention_are_not_optional(self):
        registry = self.registry()
        product_id = "co-retrieval-strengthening"
        changes = (
            ("baseline", lambda value: value["causal_comparison"].update(
                {"baseline_id": "hybrid-query"})),
            ("combined", lambda value: value["causal_comparison"].update(
                {"other_mechanisms": "combined"})),
            ("queries", lambda value: value["causal_comparison"].update(
                {"same_query_roster": False})),
            ("targets", lambda value: value["causal_comparison"].update(
                {"same_target_roster": False})),
            ("runtime", lambda value: value["causal_comparison"].update(
                {"same_engine_index_model_config": False})),
            ("task", lambda value: value["causal_comparison"].update(
                {"task_classes": ["novelty"]})),
            ("component", lambda value: value["implementation"].update(
                {"module": "siamind"})),
            ("source", lambda value: value["dataset"].update(
                {"source": "direct-gbrain-files"})),
        )
        for label, change in changes:
            evidence = _evidence(registry, product_id)
            change(evidence)
            with self.subTest(change=label):
                self.assert_stripped(
                    self.decide(product_id, _reseal(evidence)), product_id,
                    "causal-heldout-contract-mismatch")

    def test_workspace_requires_actual_acknowledged_consumer_deliveries(self):
        registry = self.registry()
        product_id = "maintained-workspace"
        for label, change in (
                ("missing-consumer", lambda witness:
                 witness["delivery_receipts"].pop()),
                ("unacknowledged", lambda witness:
                 witness["delivery_receipts"][0].update(
                     {"status": "payload-created"})),
                ("different-payload", lambda witness:
                 witness["delivery_receipts"][0].update(
                     {"payload_sha256": _digest("different-payload")}))):
            evidence = _evidence(registry, product_id)
            change(evidence["behavior_witness"])
            with self.subTest(change=label):
                self.assert_stripped(
                    self.decide(product_id, _reseal(evidence)), product_id,
                    "behavior-witness-invalid")

        evidence = _evidence(registry, product_id)
        verification = _verification(evidence)
        verification["behavior"]["delivery_receipts"].pop()
        self.assert_stripped(
            self.decide(
                product_id, evidence,
                verification=_reseal_verification(verification)),
            product_id, "verification-behavior-witness-mismatch")

    def test_self_hashed_behavior_file_cannot_authenticate_its_own_claims(self):
        registry = self.registry()
        product_id = "maintained-workspace"
        evidence = _evidence(registry, product_id)
        witness = evidence["behavior_witness"]
        document = {
            "schema": "sia-cognitive-behavior-receipt-v1",
            "mechanism_id": product_id,
            "requirement": witness["requirement"],
            "delivery_receipts": copy.deepcopy(witness["delivery_receipts"]),
            "complete": True,
            "non_claims": BEHAVIOR_VERIFICATION_NON_CLAIMS,
        }
        self.assertTrue(document["delivery_receipts"])
        raw = _canonical(document)
        caller_digest = hashlib.sha256(raw).hexdigest()

        with tempfile.TemporaryDirectory() as archive:
            retained = Path(archive) / (caller_digest + ".json")
            retained.write_bytes(raw)
            with mock.patch.object(
                    self.module, "BEHAVIOR_WITNESS_ARCHIVE", archive):
                result = self.module._verify_retained_behavior_witness(
                    mechanism_id=product_id,
                    evidence_sha256=evidence["evidence_sha256"],
                    requirement=witness["requirement"],
                    artifact_sha256=caller_digest,
                )

        self.assertEqual(
            result["schema"], "sia-cognitive-behavior-verification-v1")
        self.assertEqual(result["status"], "refused")
        self.assertEqual(
            result["reason"], "behavior-witness-authentication-required")
        self.assertFalse(result["complete"])
        self.assertEqual(result["delivery_receipts"], [])
        self.assertEqual(
            result["non_claims"], BEHAVIOR_VERIFICATION_NON_CLAIMS)

    def test_surprisal_only_encoding_can_never_admit_dopaminergic_wording(self):
        registry = self.registry()
        product_id = "prediction-conditioned-encoding"
        entry = next(row for row in registry["mechanisms"]
                     if row["product_id"] == product_id)
        self.assertEqual(
            entry["operator_neurocognitive_label"],
            "dopaminergic novelty gating")
        self.assertIsNone(entry["candidate_neurocognitive_label"])
        self.assertEqual(
            entry["claim_eligibility"],
            "permanently-stripped-current-registry-no-reward-prediction-error-"
            "plasticity-gain-witness-v1")
        evidence = _evidence(registry, product_id)
        self.assertIsNone(
            evidence["behavior_witness"]["reward_prediction_error_witness"])
        self.assertIsNone(
            evidence["behavior_witness"]["plasticity_gain_witness"])
        result = self.decide(product_id, evidence)
        self.assert_stripped(
            result, product_id, "neurocognitive-label-permanently-stripped")
        self.assertNotIn("dopamin", result["public_label"].casefold())
        self.assertNotIn("dopamin", result["claim"].casefold())

    def test_evidence_is_closed_bounded_json_and_outputs_are_detached(self):
        registry = self.registry()
        product_id = "maintained-workspace"
        evidence = _evidence(registry, product_id)
        evidence["unregistered_result"] = {"win": True}
        self.assert_stripped(
            self.decide(product_id, _reseal(evidence)), product_id,
            "evidence-fields-invalid")

        ordinary = _evidence(registry, product_id)
        with mock.patch.object(self.module, "MAX_EVIDENCE_BYTES", 1):
            self.assert_stripped(
                self.decide(product_id, ordinary), product_id,
                "evidence-byte-capacity")
        self.last_verifier.assert_not_called()

        cyclic = _evidence(registry, product_id)
        cyclic["metrics"].append(cyclic["metrics"])
        with mock.patch.object(
                self.module, "verify_retained_evidence",
                side_effect=AssertionError("verified cyclic evidence")) as verifier:
            result = self.module.decide_claim(
                product_id, cyclic,
                expected_registry_sha256=registry["registry_sha256"],
                expected_evidence_sha256=_digest("cyclic-fixture"),
                expected_operator_expectations_sha256=(
                    OPERATOR_EXPECTATIONS_SHA256),
            )
        verifier.assert_not_called()
        self.assert_stripped(
            result, product_id, "evidence-not-canonical-bounded-json")

        first = self.registry()
        first["mechanisms"].clear()
        first["non_claims"].clear()
        self.assertEqual(self.registry(), registry)


if __name__ == "__main__":
    unittest.main()
