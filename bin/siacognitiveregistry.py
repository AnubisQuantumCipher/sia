#!/usr/bin/env python3
"""Fail-closed registry and evidence gate for SIA's cognitive ancestry claims.

The registry is a hypothesis catalogue, not proof.  The only transition from a
product description to a neurocognitive label is a complete, separately pinned
held-out evidence bundle whose retained artifacts have just been re-verified by
this module.  Caller-declared results are deliberately absent from the raw
evidence schema.
"""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import os
from pathlib import Path
import selectors
import stat
import subprocess
import tempfile
import time


REGISTRY_SCHEMA = "sia-cognitive-mechanism-registry-v1"
EVIDENCE_SCHEMA = "sia-cognitive-mechanism-evidence-v1"
DECISION_SCHEMA = "sia-cognitive-claim-decision-v1"
VERIFICATION_SCHEMA = "sia-cognitive-jackal-verification-v1"

BASELINE_ID = "descriptor-bound-raw-vector-dense"
JACKAL_VERIFY_ARTIFACT = (
    "/home/sicarii/.config/omarchy/plugins/khephri.jackal/verify_artifact.py"
)
JACKAL_OPERATOR_EXPECTATIONS = (
    "/home/sicarii/.config/omarchy/jackal-expectations.json"
)
JACKAL_RUNTIME_DESCRIPTOR = (
    "/home/sicarii/.local/share/JACKAL/codex-plugin/runtime.json"
)
JACKAL_RUNTIME_ROOT = "/home/sicarii/.local/share/JACKAL/runtimes"
JACKAL_RECEIPT_ARCHIVE = "/home/sicarii/.local/state/jackal/receipts"
BEHAVIOR_WITNESS_ARCHIVE = (
    "/home/sicarii/.local/state/sia/cognitive/behavior-witnesses"
)

MAX_EVIDENCE_BYTES = 1048576
MAX_VERIFICATION_BYTES = 1048576
MAX_REGISTRY_BYTES = 1048576
MAX_METRICS = 4
MAX_TASK_CLASSES = 8
MAX_LITERATURE_CITATIONS = 8
MAX_JSON_DEPTH = 64
MAX_FRONT_DOOR_OUTPUT_BYTES = 1048576
MAX_RETAINED_ARTIFACT_BYTES = 67108864
VERIFY_TIMEOUT_SECONDS = 60

REQUIRED_METRICS = [
    "recall_at_k", "mrr", "query_latency_ms", "sia_memory_fidelity",
]
FIDELITY_DIMENSIONS = [
    "episode-retention", "content-immutability", "origin-preservation",
    "unsupported-and-exception-retention",
]
WIN_RULE = (
    "registered-primary-strictly-better-all-required-guardrails-"
    "noninferior-v1"
)
CHRONOLOGY = (
    "registry-and-policy-frozen-before-heldout-results-no-heldout-tuning-v1"
)
INFERENCE_REQUIREMENT = (
    "fixed-component-paired-one-sided-test-with-declared-model-and-"
    "multiplicity-v1"
)

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
    "maintained-workspace": (
        "complete-consumer-delivery-and-acknowledgment-receipts-v1"
    ),
    "typed-fan-spreading": "out-of-window-multihop-retrieval-with-complete-fan-v1",
    "prediction-conditioned-encoding": (
        "prequential-novelty-strength-and-later-retrieval-v1"
    ),
    "replay-gist": "durable-gist-and-immutable-episode-population-v1",
}

CLAIM_ELIGIBILITY = {
    product_id: "heldout-evidence-required-v1" for product_id in OPERATOR_LABELS
}
CLAIM_ELIGIBILITY["prediction-conditioned-encoding"] = (
    "permanently-stripped-current-registry-no-reward-prediction-error-"
    "plasticity-gain-witness-v1"
)

_MECHANISM_SPECS = {
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


class _BoundaryError(Exception):
    """An internal fail-closed boundary result."""

    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_json_tree(value, *, active: set[int] | None = None,
                        depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise _BoundaryError("evidence-not-canonical-bounded-json")
    if value is None or type(value) in (str, int, bool):
        return
    if type(value) not in (dict, list):
        raise _BoundaryError("evidence-not-canonical-bounded-json")
    if active is None:
        active = set()
    identity = id(value)
    if identity in active:
        raise _BoundaryError("evidence-not-canonical-bounded-json")
    active.add(identity)
    try:
        if type(value) is list:
            for item in value:
                _validate_json_tree(item, active=active, depth=depth + 1)
            return
        for key, item in value.items():
            if type(key) is not str:
                raise _BoundaryError("evidence-not-canonical-bounded-json")
            _validate_json_tree(item, active=active, depth=depth + 1)
    finally:
        active.remove(identity)


def _canonical(value, *, max_bytes: int,
               capacity_reason: str) -> bytes:
    _validate_json_tree(value)
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        raise _BoundaryError("evidence-not-canonical-bounded-json") from None
    if len(encoded) > max_bytes:
        raise _BoundaryError(capacity_reason)
    return encoded


def _body_digest(value: dict, field: str, *, max_bytes: int) -> str:
    body = {key: item for key, item in value.items() if key != field}
    encoded = _canonical(
        body, max_bytes=max_bytes, capacity_reason="evidence-byte-capacity"
    )
    return hashlib.sha256(encoded).hexdigest()


def _mechanism_entry(product_id: str) -> dict:
    result = copy.deepcopy(_MECHANISM_SPECS[product_id])
    result["product_id"] = product_id
    result["operator_neurocognitive_label"] = OPERATOR_LABELS[product_id]
    result["claim_eligibility"] = CLAIM_ELIGIBILITY[product_id]
    result["benchmark"] = {
        **copy.deepcopy(COMMON_BENCHMARK),
        "arm": "dense-plus-only-" + product_id,
        "intervention": result.pop("intervention"),
        "task_classes": result.pop("task_classes"),
        "primary_metric": result.pop("primary_metric"),
        "behavior_witness": WITNESS_REQUIREMENTS[product_id],
    }
    candidate = result["candidate_neurocognitive_label"]
    result["claim_wording"] = {
        "admitted": None if candidate is None else (
            candidate
            + " improved its registered primary metric over the descriptor-bound "
            "raw-vector dense baseline on the pinned held-out task scope."
        ),
        "stripped": (
            result["product_label"]
            + "; cognitive ancestry only, with no admitted held-out win."
        ),
    }
    return result


def mechanism_registry():
    """Return a detached, content-addressed candidate registry."""

    result = {
        "schema": REGISTRY_SCHEMA,
        "status": "candidate-only",
        "baseline": {
            "product_id": BASELINE_ID,
            "lane": "raw_vector",
            "implementation": {
                "module": "siacognitivebaseline",
                "callable": "run_baseline_v2",
            },
            "role": "same-pinned-input causal control",
            "retrieval_transform": "none",
        },
        "required_metrics": copy.deepcopy(REQUIRED_METRICS),
        "mechanisms": [
            _mechanism_entry(product_id) for product_id in _MECHANISM_SPECS
        ],
        "verification": {
            "method": "fresh-retained-receipt-reverification-v1",
            "api": "verify_retained_evidence",
            "entrypoint": JACKAL_VERIFY_ARTIFACT,
            "operator_expectations": JACKAL_OPERATOR_EXPECTATIONS,
            "execution_policy": "descriptor-bound-owner-private-front-door-v1",
            "behavior_witnesses": (
                "retained-artifact-reverification-required-v1"
            ),
            "caller_declared_results": "never-trusted",
        },
        "resource_limits": {
            "max_evidence_bytes": MAX_EVIDENCE_BYTES,
            "max_metrics": MAX_METRICS,
            "max_task_classes": MAX_TASK_CLASSES,
            "max_literature_citations": MAX_LITERATURE_CITATIONS,
        },
        "non_claims": copy.deepcopy(REGISTRY_NON_CLAIMS),
        "registry_sha256": "",
    }
    result["registry_sha256"] = _body_digest(
        result, "registry_sha256", max_bytes=MAX_REGISTRY_BYTES
    )
    return copy.deepcopy(result)


_EVIDENCE_FIELDS = {
    "schema", "mechanism_id", "registry_sha256", "dataset",
    "implementation", "causal_comparison", "behavior_witness", "chronology",
    "metrics", "inference", "decision", "non_claims", "evidence_sha256",
}
_DATASET_FIELDS = {
    "source", "manifest_sha256", "capture_sha256", "selection_sha256",
    "heldout_query_roster_sha256", "heldout_target_roster_sha256", "split",
    "tuning_split", "complete",
}
_IMPLEMENTATION_FIELDS = {
    "module", "callable", "component", "source_sha256", "policy_sha256",
}
_CAUSAL_FIELDS = {
    "baseline_id", "control_run_sha256", "arm_id", "arm_run_sha256",
    "intervention", "task_classes", "causal_unit", "same_query_roster",
    "same_target_roster", "same_engine_index_model_config", "other_mechanisms",
    "complete",
}
_METRIC_FIELDS = {
    "metric", "scope", "direction", "baseline_observation_sha256",
    "arm_observation_sha256", "fidelity_dimensions", "jackal_artifact",
}
_RAW_ARTIFACT_FIELDS = {"tool", "request_sha256", "receipt_sha256"}
_INFERENCE_FIELDS = {
    "requirement", "paired_unit", "test", "alternative", "multiplicity",
    "jackal_artifact",
}
_DECISION_FIELDS = {"primary_metric", "rule"}
_CHRONOLOGY_FIELDS = {"policy", "order", "no_heldout_tuning"}
_CHRONOLOGY_ROW_FIELDS = {"event", "artifact_sha256"}


def _closed_dict(value, fields: set[str]) -> bool:
    return type(value) is dict and set(value) == fields


def _all_sha256(value: dict, fields: tuple[str, ...]) -> bool:
    return all(_is_sha256(value.get(field)) for field in fields)


def _raw_behavior_reason(mechanism_id: str, witness) -> str | None:
    common = {
        "schema", "mechanism_id", "requirement", "status", "artifact_sha256",
    }
    if mechanism_id == "maintained-workspace":
        expected_fields = common | {
            "consumer_roster", "consumer_roster_sha256", "payload_sha256",
            "delivery_receipts",
        }
    elif mechanism_id == "prediction-conditioned-encoding":
        expected_fields = common | {
            "signal", "reward_prediction_error_witness",
            "plasticity_gain_witness",
        }
    else:
        expected_fields = common
    if not _closed_dict(witness, expected_fields):
        return "behavior-witness-invalid"
    if (
        witness["schema"] != "sia-cognitive-behavior-witness-v1"
        or witness["mechanism_id"] != mechanism_id
        or witness["requirement"] != WITNESS_REQUIREMENTS[mechanism_id]
        or witness["status"] != "complete"
        or not _is_sha256(witness["artifact_sha256"])
    ):
        return "behavior-witness-invalid"
    if mechanism_id == "prediction-conditioned-encoding":
        if (
            witness["signal"]
            != "prequential-frequency-or-context-information"
            or witness["reward_prediction_error_witness"] is not None
            or witness["plasticity_gain_witness"] is not None
        ):
            return "behavior-witness-invalid"
    if mechanism_id != "maintained-workspace":
        return None
    roster = ["resident-status", "context-selection"]
    if (
        witness["consumer_roster"] != roster
        or not _is_sha256(witness["consumer_roster_sha256"])
        or not _is_sha256(witness["payload_sha256"])
        or type(witness["delivery_receipts"]) is not list
    ):
        return "behavior-witness-invalid"
    receipts = witness["delivery_receipts"]
    if len(receipts) != len(roster):
        return "behavior-witness-invalid"
    seen = []
    for receipt in receipts:
        if not _closed_dict(
            receipt, {"consumer", "payload_sha256", "status", "receipt_sha256"}
        ):
            return "behavior-witness-invalid"
        if (
            receipt["consumer"] not in roster
            or receipt["consumer"] in seen
            or receipt["payload_sha256"] != witness["payload_sha256"]
            or receipt["status"] != "delivered-and-acknowledged"
            or not _is_sha256(receipt["receipt_sha256"])
        ):
            return "behavior-witness-invalid"
        seen.append(receipt["consumer"])
    if seen != roster:
        return "behavior-witness-invalid"
    return None


def _validate_evidence_contract(evidence: dict, entry: dict) -> str | None:
    if not _closed_dict(evidence, _EVIDENCE_FIELDS):
        return "evidence-fields-invalid"
    if (
        evidence["schema"] != EVIDENCE_SCHEMA
        or evidence["non_claims"] != EVIDENCE_NON_CLAIMS
    ):
        return "evidence-fields-invalid"

    dataset = evidence["dataset"]
    implementation = evidence["implementation"]
    causal = evidence["causal_comparison"]
    chronology = evidence["chronology"]
    inference = evidence["inference"]
    decision = evidence["decision"]
    if not all((
        _closed_dict(dataset, _DATASET_FIELDS),
        _closed_dict(implementation, _IMPLEMENTATION_FIELDS),
        _closed_dict(causal, _CAUSAL_FIELDS),
        _closed_dict(chronology, _CHRONOLOGY_FIELDS),
        _closed_dict(inference, _INFERENCE_FIELDS),
        _closed_dict(decision, _DECISION_FIELDS),
    )):
        return "evidence-fields-invalid"
    if not _all_sha256(dataset, (
        "manifest_sha256", "capture_sha256", "selection_sha256",
        "heldout_query_roster_sha256", "heldout_target_roster_sha256",
    )):
        return "evidence-fields-invalid"
    if not _all_sha256(implementation, ("source_sha256", "policy_sha256")):
        return "evidence-fields-invalid"
    if not _all_sha256(causal, ("control_run_sha256", "arm_run_sha256")):
        return "evidence-fields-invalid"

    metrics = evidence["metrics"]
    if type(metrics) is not list or len(metrics) > MAX_METRICS:
        return "evidence-fields-invalid"
    if not all(type(row) is dict and isinstance(row.get("metric"), str)
               for row in metrics):
        return "evidence-fields-invalid"
    names = [row["metric"] for row in metrics]
    if any(metric not in names for metric in REQUIRED_METRICS):
        return "missing-required-metric"
    if names != REQUIRED_METRICS:
        return "evidence-fields-invalid"
    for row in metrics:
        if not _closed_dict(row, _METRIC_FIELDS):
            return "evidence-fields-invalid"
        artifact = row["jackal_artifact"]
        if not _closed_dict(artifact, _RAW_ARTIFACT_FIELDS):
            return "evidence-fields-invalid"
        name = row["metric"]
        if (
            row["scope"] != "registered-heldout-task-classes"
            or row["direction"]
            != ("lower" if name == "query_latency_ms" else "higher")
            or not _all_sha256(
                row, ("baseline_observation_sha256", "arm_observation_sha256")
            )
            or row["fidelity_dimensions"]
            != (FIDELITY_DIMENSIONS if name == "sia_memory_fidelity" else [])
            or artifact["tool"] != "jackal_exact"
            or not _all_sha256(artifact, ("request_sha256", "receipt_sha256"))
        ):
            return "evidence-fields-invalid"

    inference_artifact = inference["jackal_artifact"]
    if (
        not _closed_dict(inference_artifact, _RAW_ARTIFACT_FIELDS)
        or inference["requirement"] != INFERENCE_REQUIREMENT
        or inference["paired_unit"]
        != "complete-source-dependency-component-v1"
        or inference["test"]
        != "one-sided-positive-sign-exact-binomial-tail-v1"
        or inference["alternative"] != "greater"
        or inference["multiplicity"] != "fixed-familywise-correction-v1"
        or inference_artifact["tool"] != "jackal_hypothesis"
        or not _all_sha256(
            inference_artifact, ("request_sha256", "receipt_sha256")
        )
    ):
        return "evidence-fields-invalid"
    if (
        decision["primary_metric"] != entry["benchmark"]["primary_metric"]
        or decision["rule"] != WIN_RULE
    ):
        return "causal-heldout-contract-mismatch"

    if dataset["split"] != "heldout":
        return "heldout-dataset-required"
    order = chronology["order"]
    expected_events = [
        "registry-and-policy-frozen", "heldout-run-started",
        "heldout-results-opened",
    ]
    if (
        chronology["policy"] != CHRONOLOGY
        or type(order) is not list
        or not all(_closed_dict(row, _CHRONOLOGY_ROW_FIELDS) for row in order)
        or [row["event"] for row in order] != expected_events
        or not all(_is_sha256(row["artifact_sha256"]) for row in order)
    ):
        return "heldout-chronology-invalid"
    if chronology["no_heldout_tuning"] is not True:
        return "heldout-tuning-detected"

    expected_implementation = entry["implementation"]
    expected_causal = entry["benchmark"]
    if (
        dataset["source"] != COMMON_BENCHMARK["dataset_source"]
        or dataset["tuning_split"] != "calibration"
        or dataset["complete"] is not True
        or any(
            implementation[key] != expected_implementation[key]
            for key in ("module", "callable", "component")
        )
        or causal["baseline_id"] != BASELINE_ID
        or causal["arm_id"] != expected_causal["arm"]
        or causal["intervention"] != expected_causal["intervention"]
        or causal["task_classes"] != expected_causal["task_classes"]
        or type(causal["task_classes"]) is not list
        or len(causal["task_classes"]) > MAX_TASK_CLASSES
        or causal["causal_unit"] != COMMON_BENCHMARK["causal_unit"]
        or causal["same_query_roster"] is not True
        or causal["same_target_roster"] is not True
        or causal["same_engine_index_model_config"] is not True
        or causal["other_mechanisms"]
        != COMMON_BENCHMARK["other_mechanisms"]
        or causal["complete"] is not True
    ):
        return "causal-heldout-contract-mismatch"
    return _raw_behavior_reason(entry["product_id"], evidence["behavior_witness"])


def _strip(mechanism_id: str, entry: dict | None, reason: str, *,
           evidence_sha256=None, registry_sha256=None, jackal_statuses=None,
           **details) -> dict:
    if entry is None:
        product_label = "Unregistered mechanism"
        claim = "Unregistered mechanism; no cognitive claim is admitted."
    else:
        product_label = entry["product_label"]
        claim = entry["claim_wording"]["stripped"]
    result = {
        "schema": DECISION_SCHEMA,
        "mechanism_id": mechanism_id,
        "status": "stripped",
        "disposition": "strip-neurocognitive-label",
        "reason": reason,
        "public_label": product_label,
        "neurocognitive_label": None,
        "claim": claim,
        "consequence_ceiling": "informational",
        "registry_non_claims": copy.deepcopy(REGISTRY_NON_CLAIMS),
        "registry_sha256": registry_sha256,
        "evidence_sha256": evidence_sha256,
        "jackal_statuses": copy.deepcopy(jackal_statuses or {}),
    }
    result.update(copy.deepcopy(details))
    return result


def _verified_behavior_matches(evidence: dict, behavior) -> bool:
    fields = {
        "schema", "status", "mechanism_id", "requirement", "artifact_sha256",
        "receipt_archive_generation_sha256", "delivery_receipts", "complete",
        "non_claims",
    }
    if not _closed_dict(behavior, fields):
        return False
    witness = evidence["behavior_witness"]
    expected_receipts = witness.get("delivery_receipts", [])
    return (
        behavior["schema"] == "sia-cognitive-behavior-verification-v1"
        and behavior["status"] == "verified"
        and behavior["mechanism_id"] == evidence["mechanism_id"]
        and behavior["requirement"] == witness["requirement"]
        and behavior["artifact_sha256"] == witness["artifact_sha256"]
        and _is_sha256(behavior["receipt_archive_generation_sha256"])
        and behavior["delivery_receipts"] == expected_receipts
        and behavior["complete"] is True
        and behavior["non_claims"] == BEHAVIOR_VERIFICATION_NON_CLAIMS
    )


_VERIFICATION_FIELDS = {
    "schema", "status", "reason", "evidence_sha256",
    "operator_expectations_sha256", "verifier", "behavior", "artifacts",
    "complete", "non_claims", "verification_sha256",
}
_VERIFIER_FIELDS = {
    "entrypoint", "entrypoint_sha256", "runtime_sha256",
    "operator_expectations_path", "execution_policy",
}
_VERIFIED_METRIC_FIELDS = {
    "kind", "metric", "request_sha256", "receipt_sha256",
    "verification_receipt_sha256", "baseline_observation_sha256",
    "arm_observation_sha256", "status", "parsed", "relation", "reason",
    "consequence_ceiling", "non_claims",
}
_VERIFIED_INFERENCE_FIELDS = {
    "kind", "metric", "request_sha256", "receipt_sha256",
    "verification_receipt_sha256", "status", "parsed", "decision", "reason",
    "assumptions", "consequence_ceiling", "non_claims",
}
_KNOWN_JACKAL_STATUSES = {
    "exact", "bounded", "formal-bounded", "checked", "estimated",
    "model-based", "refused",
}
_KNOWN_CONSEQUENCE_CEILINGS = {
    "informational", "advisory", "decision-boundary", "safety-critical",
}


def _verification_digest_valid(verification: dict) -> bool:
    if not _is_sha256(verification.get("verification_sha256")):
        return False
    try:
        actual = _body_digest(
            verification, "verification_sha256",
            max_bytes=MAX_VERIFICATION_BYTES,
        )
    except _BoundaryError:
        return False
    return actual == verification["verification_sha256"]


def _base_verified_details(evidence: dict, verification: dict,
                           statuses: dict) -> dict:
    details = {
        "verification_sha256": verification["verification_sha256"],
        "operator_expectations_sha256": (
            verification["operator_expectations_sha256"]
        ),
        "jackal_statuses": copy.deepcopy(statuses),
        "metric_evidence": copy.deepcopy([
            row for row in verification["artifacts"]
            if row.get("kind") == "metric"
        ]),
        "inference_evidence": copy.deepcopy(next(
            (row for row in verification["artifacts"]
             if row.get("kind") == "inference"),
            None,
        )),
        "behavior_evidence": copy.deepcopy(verification["behavior"]),
        "evidence_non_claims": copy.deepcopy(evidence["non_claims"]),
        "verification_non_claims": copy.deepcopy(verification["non_claims"]),
    }
    refusals = {
        row.get("metric"): row.get("reason")
        for row in verification["artifacts"]
        if row.get("status") == "refused"
    }
    if refusals:
        details["jackal_refusals"] = refusals
    return details


def _assess_verification(evidence: dict, entry: dict, verification: object,
                         expected_operator_expectations_sha256: str,
                         registry_sha256: str) -> dict:
    mechanism_id = entry["product_id"]
    evidence_sha = evidence["evidence_sha256"]
    try:
        _canonical(
            verification, max_bytes=MAX_VERIFICATION_BYTES,
            capacity_reason="verification-byte-capacity",
        )
    except _BoundaryError:
        return _strip(
            mechanism_id, entry, "trusted-verification-refused",
            evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
            verification_reason="verification-not-canonical-bounded-json",
        )
    if (
        not _closed_dict(verification, _VERIFICATION_FIELDS)
        or verification["schema"] != VERIFICATION_SCHEMA
        or not _verification_digest_valid(verification)
        or verification["evidence_sha256"] != evidence_sha
    ):
        return _strip(
            mechanism_id, entry, "trusted-verification-refused",
            evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
            verification_reason="verification-envelope-invalid",
        )
    if (
        verification["operator_expectations_sha256"]
        != expected_operator_expectations_sha256
    ):
        return _strip(
            mechanism_id, entry, "verification-operator-expectations-mismatch",
            evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
        )
    if verification["status"] != "verified" or verification["complete"] is not True:
        return _strip(
            mechanism_id, entry, "trusted-verification-refused",
            evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
            verification_reason=verification.get("reason"),
        )
    verifier = verification["verifier"]
    if (
        not _closed_dict(verifier, _VERIFIER_FIELDS)
        or verifier["entrypoint"] != JACKAL_VERIFY_ARTIFACT
        or verifier["operator_expectations_path"] != JACKAL_OPERATOR_EXPECTATIONS
        or verifier["execution_policy"]
        != "descriptor-bound-owner-private-front-door-v1"
        or not _all_sha256(verifier, ("entrypoint_sha256", "runtime_sha256"))
        or verification["non_claims"] != VERIFICATION_NON_CLAIMS
    ):
        return _strip(
            mechanism_id, entry, "trusted-verification-refused",
            evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
            verification_reason="verification-identity-invalid",
        )
    if not _verified_behavior_matches(evidence, verification["behavior"]):
        return _strip(
            mechanism_id, entry, "verification-behavior-witness-mismatch",
            evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
        )

    raw_by_metric = {
        row["metric"]: row for row in evidence["metrics"]
    }
    raw_inference = evidence["inference"]["jackal_artifact"]
    artifacts = verification["artifacts"]
    if type(artifacts) is not list:
        return _strip(
            mechanism_id, entry, "incomplete-jackal-result",
            evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
        )
    statuses = {}
    seen_metrics = []
    inference_row = None
    for row in artifacts:
        if type(row) is not dict or "non_claims" not in row:
            return _strip(
                mechanism_id, entry, "incomplete-jackal-result",
                evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
                jackal_statuses=statuses,
            )
        kind = row.get("kind")
        expected_fields = (
            _VERIFIED_METRIC_FIELDS if kind == "metric"
            else _VERIFIED_INFERENCE_FIELDS if kind == "inference" else None
        )
        if expected_fields is None or set(row) != expected_fields:
            return _strip(
                mechanism_id, entry, "incomplete-jackal-result",
                evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
                jackal_statuses=statuses,
            )
        metric = row.get("metric")
        status_class = row.get("status")
        if isinstance(metric, str) and isinstance(status_class, str):
            statuses[metric] = status_class
        if status_class not in _KNOWN_JACKAL_STATUSES:
            return _strip(
                mechanism_id, entry, "unrecognized-jackal-status",
                evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
                **_base_verified_details(evidence, verification, statuses),
            )
        if (
            row["non_claims"] != JACKAL_NON_CLAIMS
            or not isinstance(row["parsed"], str)
            or not row["parsed"]
            or not _all_sha256(
                row, ("request_sha256", "receipt_sha256",
                      "verification_receipt_sha256")
            )
        ):
            return _strip(
                mechanism_id, entry, "incomplete-jackal-result",
                evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
                jackal_statuses=statuses,
            )
        if kind == "metric":
            if metric not in raw_by_metric or metric in seen_metrics:
                return _strip(
                    mechanism_id, entry, "incomplete-jackal-result",
                    evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
                    jackal_statuses=statuses,
                )
            raw = raw_by_metric[metric]
            if (
                row["request_sha256"]
                != raw["jackal_artifact"]["request_sha256"]
                or row["receipt_sha256"]
                != raw["jackal_artifact"]["receipt_sha256"]
                or row["baseline_observation_sha256"]
                != raw["baseline_observation_sha256"]
                or row["arm_observation_sha256"]
                != raw["arm_observation_sha256"]
            ):
                return _strip(
                    mechanism_id, entry, "verification-artifact-pin-mismatch",
                    evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
                    jackal_statuses=statuses,
                )
            if not _all_sha256(
                row, ("baseline_observation_sha256", "arm_observation_sha256")
            ):
                return _strip(
                    mechanism_id, entry, "incomplete-jackal-result",
                    evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
                    jackal_statuses=statuses,
                )
            seen_metrics.append(metric)
        else:
            if metric != "heldout_inference" or inference_row is not None:
                return _strip(
                    mechanism_id, entry, "incomplete-jackal-result",
                    evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
                    jackal_statuses=statuses,
                )
            if (
                row["request_sha256"] != raw_inference["request_sha256"]
                or row["receipt_sha256"] != raw_inference["receipt_sha256"]
            ):
                return _strip(
                    mechanism_id, entry, "verification-artifact-pin-mismatch",
                    evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
                    jackal_statuses=statuses,
                )
            if type(row["assumptions"]) is not list or not row["assumptions"]:
                return _strip(
                    mechanism_id, entry, "incomplete-jackal-result",
                    evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
                    jackal_statuses=statuses,
                )
            inference_row = row

    if seen_metrics != REQUIRED_METRICS or inference_row is None:
        return _strip(
            mechanism_id, entry, "incomplete-jackal-result",
            evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
            jackal_statuses=statuses,
        )
    details = _base_verified_details(evidence, verification, statuses)
    if any(row["status"] == "refused" for row in artifacts):
        return _strip(
            mechanism_id, entry, "jackal-result-refused",
            evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
            **details,
        )
    if any(
        row["consequence_ceiling"] not in _KNOWN_CONSEQUENCE_CEILINGS
        for row in artifacts
    ):
        return _strip(
            mechanism_id, entry, "unrecognized-jackal-consequence-ceiling",
            evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
            **details,
        )
    if any(
        row["status"] != "exact" for row in artifacts if row["kind"] == "metric"
    ) or inference_row["status"] != "model-based":
        return _strip(
            mechanism_id, entry, "jackal-status-class-mismatch",
            evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
            **details,
        )
    if inference_row["decision"] != "supports-registered-alternative":
        return _strip(
            mechanism_id, entry, "heldout-inference-not-supportive",
            evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
            **details,
        )

    primary = entry["benchmark"]["primary_metric"]
    for row in artifacts:
        if row["kind"] != "metric":
            continue
        direction = raw_by_metric[row["metric"]]["direction"]
        better = "less" if direction == "lower" else "greater"
        worse = "greater" if direction == "lower" else "less"
        if row["metric"] == primary and row["relation"] != better:
            return _strip(
                mechanism_id, entry, "primary-not-strictly-better",
                evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
                **details,
            )
        if row["metric"] != primary and row["relation"] == worse:
            return _strip(
                mechanism_id, entry, "required-metric-regression",
                evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
                **details,
            )
        if row["relation"] not in {"less", "equal", "greater"}:
            return _strip(
                mechanism_id, entry, "incomplete-jackal-result",
                evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
                **details,
            )

    if entry["candidate_neurocognitive_label"] is None:
        return _strip(
            mechanism_id, entry, "neurocognitive-label-permanently-stripped",
            evidence_sha256=evidence_sha, registry_sha256=registry_sha256,
            **details,
        )
    return {
        "schema": DECISION_SCHEMA,
        "mechanism_id": mechanism_id,
        "status": "admitted",
        "disposition": "keep-neurocognitive-label",
        "reason": "heldout-win-admitted",
        "public_label": entry["candidate_neurocognitive_label"],
        "neurocognitive_label": entry["candidate_neurocognitive_label"],
        "claim": entry["claim_wording"]["admitted"],
        "consequence_ceiling": "informational",
        "registry_non_claims": copy.deepcopy(REGISTRY_NON_CLAIMS),
        "registry_sha256": registry_sha256,
        "evidence_sha256": evidence_sha,
        **details,
    }


def decide_claim(
    mechanism_id,
    evidence_bundle=None,
    *,
    expected_registry_sha256=None,
    expected_evidence_sha256=None,
    expected_operator_expectations_sha256=None,
):
    """Admit only a freshly verified, registered held-out causal win."""

    registry = mechanism_registry()
    entries = {row["product_id"]: row for row in registry["mechanisms"]}
    entry = entries.get(mechanism_id)
    if entry is None:
        return _strip(
            mechanism_id, None, "mechanism-not-registered",
            registry_sha256=registry["registry_sha256"],
        )
    if evidence_bundle is None:
        return _strip(
            mechanism_id, entry, "evidence-required",
            registry_sha256=registry["registry_sha256"],
        )
    try:
        _canonical(
            evidence_bundle, max_bytes=MAX_EVIDENCE_BYTES,
            capacity_reason="evidence-byte-capacity",
        )
    except _BoundaryError as error:
        return _strip(
            mechanism_id, entry, error.reason,
            registry_sha256=registry["registry_sha256"],
        )
    if not _closed_dict(evidence_bundle, _EVIDENCE_FIELDS):
        return _strip(
            mechanism_id, entry, "evidence-fields-invalid",
            evidence_sha256=evidence_bundle.get("evidence_sha256"),
            registry_sha256=registry["registry_sha256"],
        )
    if evidence_bundle.get("mechanism_id") != mechanism_id:
        return _strip(
            mechanism_id, entry, "mechanism-evidence-mismatch",
            evidence_sha256=evidence_bundle.get("evidence_sha256"),
            registry_sha256=registry["registry_sha256"],
        )
    if expected_registry_sha256 is None or expected_evidence_sha256 is None:
        return _strip(
            mechanism_id, entry, "external-pin-required",
            evidence_sha256=evidence_bundle.get("evidence_sha256"),
            registry_sha256=registry["registry_sha256"],
        )
    if expected_operator_expectations_sha256 is None:
        return _strip(
            mechanism_id, entry, "trusted-verification-required",
            evidence_sha256=evidence_bundle.get("evidence_sha256"),
            registry_sha256=registry["registry_sha256"],
        )
    if expected_registry_sha256 != registry["registry_sha256"]:
        return _strip(
            mechanism_id, entry, "external-registry-pin-mismatch",
            evidence_sha256=evidence_bundle.get("evidence_sha256"),
            registry_sha256=registry["registry_sha256"],
        )
    evidence_sha = evidence_bundle.get("evidence_sha256")
    if expected_evidence_sha256 != evidence_sha:
        return _strip(
            mechanism_id, entry, "external-evidence-pin-mismatch",
            evidence_sha256=evidence_sha,
            registry_sha256=registry["registry_sha256"],
        )
    try:
        self_digest = _body_digest(
            evidence_bundle, "evidence_sha256", max_bytes=MAX_EVIDENCE_BYTES
        )
    except _BoundaryError as error:
        return _strip(
            mechanism_id, entry, error.reason,
            evidence_sha256=evidence_sha,
            registry_sha256=registry["registry_sha256"],
        )
    if not _is_sha256(evidence_sha) or self_digest != evidence_sha:
        return _strip(
            mechanism_id, entry, "evidence-self-pin-mismatch",
            evidence_sha256=evidence_sha,
            registry_sha256=registry["registry_sha256"],
        )
    if evidence_bundle.get("registry_sha256") != registry["registry_sha256"]:
        return _strip(
            mechanism_id, entry, "evidence-registry-mismatch",
            evidence_sha256=evidence_sha,
            registry_sha256=registry["registry_sha256"],
        )
    reason = _validate_evidence_contract(evidence_bundle, entry)
    if reason is not None:
        return _strip(
            mechanism_id, entry, reason, evidence_sha256=evidence_sha,
            registry_sha256=registry["registry_sha256"],
        )
    try:
        verification = verify_retained_evidence(
            evidence_bundle=evidence_bundle,
            expected_evidence_sha256=expected_evidence_sha256,
            expected_operator_expectations_sha256=(
                expected_operator_expectations_sha256
            ),
        )
    except Exception:
        return _strip(
            mechanism_id, entry, "trusted-verification-refused",
            evidence_sha256=evidence_sha,
            registry_sha256=registry["registry_sha256"],
            verification_reason="verification-boundary-failed",
        )
    return _assess_verification(
        evidence_bundle, entry, verification,
        expected_operator_expectations_sha256,
        registry["registry_sha256"],
    )


def _refused_verification(evidence_sha256: object,
                          operator_expectations_sha256: object,
                          reason: str, verifier=None) -> dict:
    result = {
        "schema": VERIFICATION_SCHEMA,
        "status": "refused",
        "reason": reason,
        "evidence_sha256": evidence_sha256,
        "operator_expectations_sha256": operator_expectations_sha256,
        "verifier": copy.deepcopy(verifier),
        "behavior": None,
        "artifacts": [],
        "complete": False,
        "non_claims": copy.deepcopy(VERIFICATION_NON_CLAIMS),
        "verification_sha256": "",
    }
    result["verification_sha256"] = _body_digest(
        result, "verification_sha256", max_bytes=MAX_VERIFICATION_BYTES
    )
    return result


def _accepted_front_door_reply(reply, expected_artifact: dict):
    fields = {"schema", "status", "artifact", "verifier", "non_claims"}
    if not _closed_dict(reply, fields):
        raise _BoundaryError("retained-receipt-verification-envelope-invalid")
    if reply["schema"] != "sia-cognitive-jackal-artifact-verification-v1":
        raise _BoundaryError("retained-receipt-verification-envelope-invalid")
    if reply["status"] != "accepted":
        raise _BoundaryError(
            reply.get("reason") or "retained-receipt-not-accepted"
        )
    if reply["non_claims"] != VERIFICATION_NON_CLAIMS:
        raise _BoundaryError("retained-receipt-verification-envelope-invalid")
    if reply["artifact"] != expected_artifact:
        raise _BoundaryError("retained-receipt-artifact-mismatch")
    if not _closed_dict(reply["verifier"], _VERIFIER_FIELDS):
        raise _BoundaryError("retained-receipt-verifier-identity-invalid")
    return copy.deepcopy(reply["artifact"]), copy.deepcopy(reply["verifier"])


def verify_retained_evidence(
    *, evidence_bundle, expected_evidence_sha256,
    expected_operator_expectations_sha256,
):
    """Re-verify every retained result and behavior witness through owned paths."""

    evidence_sha = (
        evidence_bundle.get("evidence_sha256")
        if type(evidence_bundle) is dict else None
    )
    if (
        type(evidence_bundle) is not dict
        or evidence_sha != expected_evidence_sha256
        or not _is_sha256(expected_evidence_sha256)
        or not _is_sha256(expected_operator_expectations_sha256)
    ):
        return _refused_verification(
            evidence_sha, expected_operator_expectations_sha256,
            "verification-input-pin-mismatch",
        )
    try:
        if _body_digest(
            evidence_bundle, "evidence_sha256", max_bytes=MAX_EVIDENCE_BYTES
        ) != expected_evidence_sha256:
            raise _BoundaryError("verification-evidence-self-pin-mismatch")
        artifacts = []
        verifier_identity = None
        expected_artifacts = []
        for metric in evidence_bundle["metrics"]:
            raw = metric["jackal_artifact"]
            expected_artifacts.append({
                "kind": "metric",
                "metric": metric["metric"],
                "request_sha256": raw["request_sha256"],
                "receipt_sha256": raw["receipt_sha256"],
                "baseline_observation_sha256": (
                    metric["baseline_observation_sha256"]
                ),
                "arm_observation_sha256": metric["arm_observation_sha256"],
            })
        raw_inference = evidence_bundle["inference"]["jackal_artifact"]
        expected_artifacts.append({
            "kind": "inference",
            "metric": "heldout_inference",
            "request_sha256": raw_inference["request_sha256"],
            "receipt_sha256": raw_inference["receipt_sha256"],
        })
        for expected in expected_artifacts:
            reply = _verify_retained_receipt(
                receipt_sha256=expected["receipt_sha256"],
                expected_request_sha256=expected["request_sha256"],
                artifact_kind=expected["kind"],
                metric=expected["metric"],
                expected_operator_expectations_sha256=(
                    expected_operator_expectations_sha256
                ),
            )
            if type(reply) is not dict or type(reply.get("artifact")) is not dict:
                raise _BoundaryError(
                    reply.get("reason", "retained-receipt-not-accepted")
                    if type(reply) is dict
                    else "retained-receipt-not-accepted"
                )
            artifact = reply["artifact"]
            for key, value in expected.items():
                if artifact.get(key) != value:
                    raise _BoundaryError("retained-receipt-artifact-mismatch")
            accepted_artifact, verifier = _accepted_front_door_reply(
                reply, artifact
            )
            if verifier_identity is None:
                verifier_identity = verifier
            elif verifier_identity != verifier:
                raise _BoundaryError("retained-receipt-verifier-identity-mismatch")
            artifacts.append(accepted_artifact)
        witness = evidence_bundle["behavior_witness"]
        behavior = _verify_retained_behavior_witness(
            mechanism_id=evidence_bundle["mechanism_id"],
            evidence_sha256=evidence_sha,
            requirement=witness["requirement"],
            artifact_sha256=witness["artifact_sha256"],
        )
        if not _verified_behavior_matches(evidence_bundle, behavior):
            raise _BoundaryError("retained-behavior-witness-not-accepted")
        result = {
            "schema": VERIFICATION_SCHEMA,
            "status": "verified",
            "reason": None,
            "evidence_sha256": evidence_sha,
            "operator_expectations_sha256": (
                expected_operator_expectations_sha256
            ),
            "verifier": verifier_identity,
            "behavior": copy.deepcopy(behavior),
            "artifacts": artifacts,
            "complete": True,
            "non_claims": copy.deepcopy(VERIFICATION_NON_CLAIMS),
            "verification_sha256": "",
        }
        result["verification_sha256"] = _body_digest(
            result, "verification_sha256", max_bytes=MAX_VERIFICATION_BYTES
        )
        return result
    except (_BoundaryError, KeyError, TypeError) as error:
        reason = (
            error.reason if isinstance(error, _BoundaryError)
            else "verification-evidence-fields-invalid"
        )
        return _refused_verification(
            evidence_sha, expected_operator_expectations_sha256, reason,
        )


def _read_stable_regular(path: Path, *, max_bytes: int) -> tuple[bytes, os.stat_result]:
    if type(max_bytes) is not int or max_bytes < 1:
        raise _BoundaryError("retained-artifact-size-refused")
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0))
    descriptor = os.open(os.fspath(path), flags)
    try:
        first = os.fstat(descriptor)
        if not stat.S_ISREG(first.st_mode):
            raise _BoundaryError("retained-artifact-not-regular")
        if (first.st_uid != os.geteuid() or first.st_nlink != 1
                or first.st_mode & 0o022):
            raise _BoundaryError("retained-artifact-owner-policy-refused")
        if first.st_size < 1 or first.st_size > max_bytes:
            raise _BoundaryError("retained-artifact-size-refused")
        chunks = []
        remaining = first.st_size
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        extra = os.read(descriptor, 1)
        second = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    generation = (
        first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns,
        first.st_ctime_ns,
    )
    second_generation = (
        second.st_dev, second.st_ino, second.st_size, second.st_mtime_ns,
        second.st_ctime_ns,
    )
    raw = b"".join(chunks)
    if (generation != second_generation or remaining != 0 or extra
            or len(raw) != first.st_size):
        raise _BoundaryError("retained-artifact-generation-changed")
    return raw, first


def _strict_json_bytes(raw: bytes, reason: str):
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeError, ValueError, RecursionError):
        raise _BoundaryError(reason) from None


def _runtime_path() -> tuple[Path, str]:
    raw, _ = _read_stable_regular(
        Path(JACKAL_RUNTIME_DESCRIPTOR), max_bytes=MAX_VERIFICATION_BYTES
    )
    descriptor = _strict_json_bytes(raw, "jackal-runtime-descriptor-malformed")
    if (
        type(descriptor) is not dict
        or set(descriptor) != {
            "schema", "epoch", "package_sha256", "package_size",
            "runtime_path",
        }
        or descriptor.get("schema") != "jackal-codex-plugin-runtime-v1"
        or not isinstance(descriptor.get("epoch"), str)
        or not descriptor["epoch"]
        or not _is_sha256(descriptor.get("package_sha256"))
        or type(descriptor.get("package_size")) is not int
        or descriptor["package_size"] < 1
        or not isinstance(descriptor.get("runtime_path"), str)
    ):
        raise _BoundaryError("jackal-runtime-descriptor-malformed")
    runtime = Path(descriptor["runtime_path"])
    allowed_parent = Path(JACKAL_RUNTIME_ROOT)
    try:
        resolved = runtime.resolve(strict=True)
        parent = allowed_parent.resolve(strict=True)
        info = runtime.lstat()
    except OSError:
        raise _BoundaryError("jackal-runtime-descriptor-unavailable") from None
    if (
        runtime.is_symlink() or not stat.S_ISDIR(info.st_mode)
        or resolved.parent != parent or info.st_uid != os.getuid()
        or info.st_mode & 0o022
    ):
        raise _BoundaryError("jackal-runtime-descriptor-refused")
    descriptor_sha = hashlib.sha256(raw).hexdigest()
    binding = hashlib.sha256(_canonical(
        {
            "descriptor_sha256": descriptor_sha,
            "package_sha256": descriptor["package_sha256"],
        },
        max_bytes=MAX_VERIFICATION_BYTES,
        capacity_reason="jackal-runtime-descriptor-malformed",
    )).hexdigest()
    return resolved, binding


def _front_door_identity(runtime_sha256: str, entrypoint_raw: bytes) -> dict:
    return {
        "entrypoint": JACKAL_VERIFY_ARTIFACT,
        "entrypoint_sha256": hashlib.sha256(entrypoint_raw).hexdigest(),
        "runtime_sha256": runtime_sha256,
        "operator_expectations_path": JACKAL_OPERATOR_EXPECTATIONS,
        "execution_policy": "descriptor-bound-owner-private-front-door-v1",
    }


def _retained_request_sha256(receipt: dict) -> str:
    request = receipt.get("request") if type(receipt) is dict else None
    if type(request) is not dict:
        raise _BoundaryError("retained-receipt-request-pin-mismatch")
    commitment = request.get("request_commitment_b64")
    if commitment is None:
        return hashlib.sha256(_canonical(
            request,
            max_bytes=MAX_RETAINED_ARTIFACT_BYTES,
            capacity_reason="retained-receipt-request-over-bound",
        )).hexdigest()
    if not isinstance(commitment, str):
        raise _BoundaryError("retained-receipt-request-pin-mismatch")
    try:
        decoded = base64.b64decode(
            commitment.encode("ascii"), validate=True).decode("ascii")
    except (UnicodeError, ValueError, binascii.Error):
        raise _BoundaryError("retained-receipt-request-pin-mismatch") from None
    if not _is_sha256(decoded):
        raise _BoundaryError("retained-receipt-request-pin-mismatch")
    return decoded


def _stage_private_file(root_fd: int, name: str, raw: bytes) -> int:
    """Write admitted bytes once, then return a held read descriptor."""
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
             | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    descriptor = os.open(name, flags, 0o600, dir_fd=root_fd)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written < 1:
                raise OSError("private front-door stage write stopped")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return os.open(
        name,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=root_fd,
    )


def _open_runtime_directory(runtime: Path) -> int:
    descriptor = os.open(
        os.fspath(runtime),
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o022):
            raise _BoundaryError("jackal-runtime-descriptor-refused")
        held_target = os.readlink(f"/proc/self/fd/{descriptor}")
        if " (deleted)" in held_target \
                or Path(held_target).resolve(strict=True) != runtime:
            raise _BoundaryError("jackal-runtime-generation-changed")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _run_bounded_front_door(
        command, *, cwd, pass_fds, timeout, env, max_output_bytes):
    """Capture each child stream with a hard in-memory byte ceiling."""
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=cwd, pass_fds=pass_fds, close_fds=True, env=env,
    )
    streams = {"stdout": bytearray(), "stderr": bytearray()}
    selector = selectors.DefaultSelector()
    assert process.stdout is not None and process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    deadline = time.monotonic() + timeout
    overflow = None
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            for key, _mask in selector.select(min(remaining, 1)):
                label = key.data
                budget = max_output_bytes + 1 - len(streams[label])
                chunk = os.read(key.fileobj.fileno(), max(1, min(65536, budget)))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                streams[label].extend(chunk)
                if len(streams[label]) > max_output_bytes:
                    overflow = label
                    process.kill()
                    break
            if overflow is not None:
                break
        if overflow is not None:
            process.wait(timeout=timeout)
            raise _BoundaryError(
                "jackal-front-door-" + overflow + "-oversize")
        returncode = process.wait(timeout=max(1, deadline - time.monotonic()))
    except Exception:
        if process.poll() is None:
            process.kill()
        process.wait()
        raise
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
    return subprocess.CompletedProcess(
        command, returncode,
        stdout=bytes(streams["stdout"]), stderr=bytes(streams["stderr"]),
    )


def _verify_retained_receipt(
    *, receipt_sha256, expected_request_sha256, artifact_kind, metric,
    expected_operator_expectations_sha256,
):
    """Run a retained receipt through the fixed operator-authorized front door.

    A current JACKAL formal receipt verifies its own certified computation but
    does not carry the benchmark comparison record required by this registry.
    Such a receipt is therefore re-verified and then still refused here unless
    the front door itself returns a closed registered comparison artifact.
    """

    refusal_base = {
        "schema": "sia-cognitive-jackal-artifact-verification-v1",
        "status": "refused",
        "artifact": None,
        "verifier": None,
        "non_claims": copy.deepcopy(VERIFICATION_NON_CLAIMS),
    }
    if (
        not _is_sha256(receipt_sha256)
        or not _is_sha256(expected_request_sha256)
        or artifact_kind not in {"metric", "inference"}
        or not isinstance(metric, str) or not metric
        or not _is_sha256(expected_operator_expectations_sha256)
    ):
        return {**refusal_base, "reason": "retained-receipt-request-invalid"}
    try:
        entrypoint_raw, _ = _read_stable_regular(
            Path(JACKAL_VERIFY_ARTIFACT), max_bytes=MAX_VERIFICATION_BYTES
        )
        expectations_raw, _ = _read_stable_regular(
            Path(JACKAL_OPERATOR_EXPECTATIONS),
            max_bytes=MAX_VERIFICATION_BYTES,
        )
        if (
            hashlib.sha256(expectations_raw).hexdigest()
            != expected_operator_expectations_sha256
        ):
            raise _BoundaryError("operator-expectations-pin-mismatch")
        runtime, runtime_sha = _runtime_path()
        verifier = _front_door_identity(runtime_sha, entrypoint_raw)
        receipt_path = Path(JACKAL_RECEIPT_ARCHIVE) / (receipt_sha256 + ".json")
        receipt_raw, _ = _read_stable_regular(
            receipt_path, max_bytes=MAX_RETAINED_ARTIFACT_BYTES
        )
        receipt = _strict_json_bytes(
            receipt_raw, "retained-receipt-malformed"
        )
        if (
            type(receipt) is not dict
            or receipt.get("receipt_digest_sha256") != receipt_sha256
        ):
            raise _BoundaryError("retained-receipt-pin-mismatch")
        if _retained_request_sha256(receipt) != expected_request_sha256:
            raise _BoundaryError("retained-receipt-request-pin-mismatch")
        with tempfile.TemporaryDirectory(
                prefix="sia-cognitive-front-door-") as private_root:
            root_info = os.stat(private_root, follow_symlinks=False)
            if (not stat.S_ISDIR(root_info.st_mode)
                    or root_info.st_uid != os.geteuid()
                    or stat.S_IMODE(root_info.st_mode) != 0o700):
                raise _BoundaryError("jackal-front-door-private-root-refused")
            root_fd = os.open(
                private_root,
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            held = []
            try:
                entrypoint_fd = _stage_private_file(
                    root_fd, "verify_artifact.py", entrypoint_raw)
                held.append(entrypoint_fd)
                expectations_fd = _stage_private_file(
                    root_fd, "expectations.json", expectations_raw)
                held.append(expectations_fd)
                artifact_fd = _stage_private_file(
                    root_fd, "artifact.json", receipt_raw)
                held.append(artifact_fd)
                runtime_fd = _open_runtime_directory(runtime)
                held.append(runtime_fd)
                private_expectations = os.path.join(
                    private_root, "expectations.json")
                private_artifact = os.path.join(private_root, "artifact.json")
                command = [
                    "/usr/bin/python3", "-I", "-B",
                    f"/proc/self/fd/{entrypoint_fd}",
                    # Popen resolves the held runtime cwd before its child
                    # closes non-standard descriptors.  The fixed verifier's
                    # nested launch can therefore resolve this relative path
                    # without relying on the original runtime pathname.
                    "--runtime", ".",
                    "--expectations", private_expectations,
                    "--now-unix", str(int(time.time())),
                    "--timeout", str(VERIFY_TIMEOUT_SECONDS),
                    "--artifact-file", private_artifact,
                ]
                process = _run_bounded_front_door(
                    command,
                    cwd=f"/proc/self/fd/{runtime_fd}",
                    pass_fds=tuple(held),
                    timeout=VERIFY_TIMEOUT_SECONDS,
                    max_output_bytes=MAX_FRONT_DOOR_OUTPUT_BYTES,
                    env={
                        "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                        "LC_ALL": "C.UTF-8",
                    },
                )
            finally:
                for descriptor in reversed(held):
                    os.close(descriptor)
                os.close(root_fd)
        stdout_value = process.stdout or b""
        stderr_value = process.stderr or b""
        try:
            stdout = (stdout_value.encode("utf-8")
                      if isinstance(stdout_value, str) else bytes(stdout_value))
            stderr = (stderr_value.encode("utf-8")
                      if isinstance(stderr_value, str) else bytes(stderr_value))
        except (UnicodeError, TypeError, ValueError):
            raise _BoundaryError("jackal-front-door-output-malformed")
        if len(stdout) > MAX_FRONT_DOOR_OUTPUT_BYTES:
            raise _BoundaryError("jackal-front-door-stdout-oversize")
        if len(stderr) > MAX_FRONT_DOOR_OUTPUT_BYTES:
            raise _BoundaryError("jackal-front-door-stderr-oversize")
        if not stdout:
            raise _BoundaryError("jackal-front-door-output-refused")
        report = _strict_json_bytes(stdout, "jackal-front-door-output-malformed")
        if type(report) is not dict or report.get("schema") != "khephri.jackal-verify-v1":
            raise _BoundaryError("jackal-front-door-output-malformed")
        if type(process.returncode) is not int or process.returncode != 0:
            if report.get("status") == "refused" \
                    and isinstance(report.get("reason"), str) \
                    and report["reason"]:
                raise _BoundaryError(report["reason"])
            raise _BoundaryError("jackal-front-door-nonzero-exit")
        if report.get("status") != "verified":
            reason = report.get("reason")
            raise _BoundaryError(
                reason if isinstance(reason, str) and reason
                else "retained-receipt-not-accepted"
            )
        # The fixed verifier presently authenticates formal receipts and claim
        # bundles.  Neither schema exposes a closed per-metric relation record
        # bound to the two observation pins.  Do not manufacture one locally.
        raise _BoundaryError(
            "verified-receipt-lacks-registered-comparison-record"
        )
    except (OSError, subprocess.SubprocessError, _BoundaryError) as error:
        reason = (
            error.reason if isinstance(error, _BoundaryError)
            else "jackal-front-door-execution-failed"
        )
        return {
            **refusal_base,
            "reason": reason,
            "verifier": locals().get("verifier"),
        }


def _verify_retained_behavior_witness(
    *, mechanism_id, evidence_sha256, requirement, artifact_sha256,
):
    """Re-read a content-addressed behavior receipt and bind it to this run."""

    refused = {
        "schema": "sia-cognitive-behavior-verification-v1",
        "status": "refused",
        "reason": "behavior-witness-authentication-required",
        "mechanism_id": mechanism_id,
        "requirement": requirement,
        "artifact_sha256": artifact_sha256,
        "receipt_archive_generation_sha256": None,
        "delivery_receipts": [],
        "complete": False,
        "non_claims": copy.deepcopy(BEHAVIOR_VERIFICATION_NON_CLAIMS),
    }
    if (
        mechanism_id not in _MECHANISM_SPECS
        or not _is_sha256(evidence_sha256)
        or requirement != WITNESS_REQUIREMENTS.get(mechanism_id)
        or not _is_sha256(artifact_sha256)
    ):
        return refused
    path = Path(BEHAVIOR_WITNESS_ARCHIVE) / (artifact_sha256 + ".json")
    try:
        raw, info = _read_stable_regular(path, max_bytes=MAX_EVIDENCE_BYTES)
        if hashlib.sha256(raw).hexdigest() != artifact_sha256:
            raise _BoundaryError("behavior-witness-content-pin-mismatch")
        document = _strict_json_bytes(raw, "behavior-witness-malformed")
        fields = {
            "schema", "mechanism_id", "requirement", "delivery_receipts",
            "complete", "non_claims",
        }
        if (
            not _closed_dict(document, fields)
            or document["schema"] != "sia-cognitive-behavior-receipt-v1"
            or document["mechanism_id"] != mechanism_id
            or document["requirement"] != requirement
            or type(document["delivery_receipts"]) is not list
            or document["complete"] is not True
            or type(document["non_claims"]) is not list
            or not document["non_claims"]
        ):
            raise _BoundaryError("behavior-witness-fields-invalid")
        generation = {
            "device": info.st_dev, "inode": info.st_ino, "size": info.st_size,
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns,
        }
        generation_sha = hashlib.sha256(json.dumps(
            generation, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        # A content hash and owner-only workspace file do not authenticate the
        # producer, execution, or delivery acknowledgements asserted inside it.
        # Keep this front door closed until an independently authenticated
        # behavior-receipt producer is installed and verified here.
        _ = generation_sha
        raise _BoundaryError("behavior-witness-authentication-required")
    except (OSError, _BoundaryError):
        return refused
