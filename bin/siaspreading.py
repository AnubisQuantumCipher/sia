"""Direct cue fan association and a separate typed propagation experiment.

The direct single-cue term follows Marewski & Mehlhorn (2011), section 4.2,
equations 3 and 4: W * (S - ln fan), with an explicit complete target fan.
https://dlab.sauder.ubc.ca/sjdm/journal/11/101112/jdm101112.html

The finite-hop normalized pulse algorithm is an engineering extension, not
that equation or a complete cognitive architecture. It normalizes the full
admitted outgoing effective fan before applying a deterministic emission cap.
Omitted mass is reported, not redistributed. Directed sinks terminate pulses;
seeds are not reinjected. All scores and paths remain retrieval-only signals.

Neither API reads a corpus, clock, model, configuration, or learned graph.
Caller-supplied completeness is an admission premise, not authenticated fact.
Local floating-point results have only the status computed-unverified.
"""

import hashlib
import json
import math
import re


# Representation ceilings reuse the local admitted protocols. The step ceiling
# is the explicit engineering bound in this component's contract. Callers also
# supply every operation-specific capacity; none is a fitted model parameter.
MAX_SAFE_INTEGER = 9007199254740991
MAX_NODES = 256
MAX_EDGES = 4096
MAX_STEPS = 32
MAX_INPUT_BYTES = 2097152
MAX_SUBJECT_BYTES = 1024
MAX_TOKEN_BYTES = 128

COMMON_NON_CLAIMS = (
    "computed-unverified is a local floating-point software result, not a JACKAL assurance class or proof.",
    "Completeness is a caller admission premise; hashes bind supplied records but do not authenticate their history.",
    "Scores and transfer paths are retrieval-only signals, not evidence for the content or truth of a node.",
    "Original content and origin labels are not rewritten by this component.",
    "No human-memory mechanism or held-out retrieval improvement is established.",
)
DIRECT_NON_CLAIMS = COMMON_NON_CLAIMS + (
    "The signed direct-cue fan term is not a probability, latency prediction, or complete cognitive architecture.",
)
SPREAD_NON_CLAIMS = COMMON_NON_CLAIMS + (
    "Finite-hop normalization is an engineering extension, not the published W * (S - ln fan) association equation.",
    "Attenuation, edge-type gains, work caps, and tie policy are explicit engineering choices, not fitted cognitive parameters.",
    "Learned or retrieval-only adjacency remains retrieval-only even when it reaches an evidence-origin node.",
)

_SUBJECT = re.compile(r"[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_ORIGINS = frozenset(("evidence", "derived", "model", "legacy-unlabeled"))
_PROVENANCE = {"factual-graph": "corpus-graph", "learned-coreturn": "retrieval-only"}
_FAN_KEYS = {"v", "cue", "complete", "targets"}
_GRAPH_KEYS = {"v", "complete", "nodes", "edges"}
_NODE_KEYS = {"id", "origin"}
_EDGE_KEYS = {"id", "s", "d", "t", "weight", "provenance", "scope"}
_SEED_KEYS = {"id", "activation", "source_sha256"}
_POLICY_KEYS = {
    "v", "algorithm", "steps", "hop_attenuation", "type_gains", "fanout_limit",
    "fanout_order", "score_mode", "candidate_scope", "tie_break", "max_nodes",
    "max_edges", "max_seeds", "max_transfers",
}


class SpreadingRefusal(ValueError):
    """No partial score or rank observation is returned on this refusal."""

    def __init__(self, reason):
        self.reason = reason
        self.non_claims = COMMON_NON_CLAIMS
        super().__init__("spreading refused: " + reason)


def _refuse(reason):
    raise SpreadingRefusal(reason)


def _keys(value, required, label):
    if type(value) is not dict or len(value) != len(required) \
            or any(type(key) is not str for key in value) or set(value) != required:
        _refuse(label + "-shape")


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _number(value, *, signed=False, positive=False):
    if type(value) not in (int, float):
        return False
    low = -MAX_SAFE_INTEGER if signed else 0
    # Compare magnitude before converting an arbitrary Python integer.
    return low <= value <= MAX_SAFE_INTEGER and (not positive or value > 0) \
        and math.isfinite(value)


def _token(value, *, subject=False):
    maximum, pattern = (MAX_SUBJECT_BYTES, _SUBJECT) if subject else (MAX_TOKEN_BYTES, _TOKEN)
    return type(value) is str and 0 < len(value) <= maximum and pattern.fullmatch(value) is not None


def _budget(value):
    """Bound already shape-admitted ASCII JSON before copying or encoding."""
    consumed = 0

    def count(item):
        nonlocal consumed
        kind = type(item)
        if kind is str:
            # Admitted tokens exclude non-ASCII and JSON escape characters.
            consumed += len(item) + len('""')
        elif kind is bool:
            consumed += len("true" if item else "false")
        elif kind in (int, float):
            consumed += len(str(item))
        elif kind is list:
            consumed += len("[]") + max(len(item) - 1, 0)
            for child in item:
                count(child)
        elif kind is dict:
            consumed += len("{}") + max(len(item) - 1, 0) + len(item)
            for key, child in item.items():
                count(key)
                count(child)
        else:
            _refuse("input-value")
        if consumed > MAX_INPUT_BYTES:
            _refuse("input-byte-capacity")

    count(value)


def _sha(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_INPUT_BYTES:
        _refuse("serialized-byte-capacity")
    return hashlib.sha256(encoded).hexdigest()


def _admit_fan(fan, target, source_activation, strength, max_targets):
    if not _integer(max_targets, 1, MAX_NODES):
        _refuse("fan-capacity-policy")
    if not _number(source_activation) or not _number(strength, signed=True):
        _refuse("cue-numeric-policy")
    if not _token(target, subject=True):
        _refuse("cue-target")
    _keys(fan, _FAN_KEYS, "fan")
    if not _integer(fan["v"], 1, 1) or not _token(fan["cue"], subject=True):
        _refuse("fan-identity")
    if fan["complete"] is not True:
        _refuse("fan-incomplete")
    targets = fan["targets"]
    if type(targets) is not list or not 0 < len(targets) <= max_targets:
        _refuse("fan-target-capacity")
    unique = set()
    for identity in targets:
        if not _token(identity, subject=True) or identity in unique:
            _refuse("fan-target-identity")
        unique.add(identity)
    if target not in unique:
        _refuse("target-not-in-complete-fan")
    _budget({"fan": fan, "target": target, "source_activation": source_activation,
             "max_associative_strength": strength, "max_targets": max_targets})


def _multiply(left, right, label):
    result = left * right
    if not math.isfinite(result):
        _refuse("numeric-" + label + "-overflow")
    if result == 0 and left != 0 and right != 0:
        _refuse("numeric-" + label + "-underflow")
    return result


def _sum(values, label):
    try:
        result = math.fsum(values)
    except (OverflowError, ValueError) as exc:
        raise SpreadingRefusal("numeric-" + label + "-range") from exc
    if not math.isfinite(result) or result < 0:
        _refuse("numeric-" + label + "-domain")
    return result


def cue_association(fan, *, target, source_activation, max_associative_strength, max_targets):
    """Compute the signed literal single-cue term; never clip or exponentiate.

    The complete unique target roster defines fan. W, S, and capacity have no
    defaults. Their original JSON integer/float representations remain bound
    in the policy digest independently of the floating-point computation.
    """
    try:
        _admit_fan(fan, target, source_activation, max_associative_strength, max_targets)
        admitted = {"v": fan["v"], "cue": fan["cue"], "complete": fan["complete"],
                    "targets": list(fan["targets"])}
        _admit_fan(admitted, target, source_activation, max_associative_strength, max_targets)
        policy = {"source_activation": source_activation,
                  "max_associative_strength": max_associative_strength, "max_targets": max_targets}
        association = float(max_associative_strength) - math.log(len(admitted["targets"]))
        if not math.isfinite(association):
            _refuse("numeric-association-domain")
        score = _multiply(float(source_activation), association, "cue-score")
        return {"v": 1, "component": "cue-fan-association", "status": "computed-unverified",
                "scope": "retrieval-only", "cue": admitted["cue"], "target": target,
                "fan_count": len(admitted["targets"]), "source_activation": source_activation,
                "max_associative_strength": max_associative_strength, "score": score,
                "fan_sha256": _sha(admitted), "policy_sha256": _sha(policy),
                "non_claims": list(DIRECT_NON_CLAIMS)}
    except SpreadingRefusal:
        raise
    except (TypeError, ValueError, OverflowError, KeyError, RecursionError, UnicodeError) as exc:
        raise SpreadingRefusal("cue-input-or-numeric-domain") from exc


def _admit_policy(policy):
    _keys(policy, _POLICY_KEYS, "policy")
    if not _integer(policy["v"], 1, 1):
        _refuse("policy-version")
    required = {"algorithm": "typed-fan-pulse-v1", "fanout_order": "edge-id",
                "score_mode": "received-sum", "candidate_scope": "positive-received",
                "tie_break": "node-input-order"}
    if any(type(policy[key]) is not str or policy[key] != value for key, value in required.items()):
        _refuse("policy-contract")
    for key, ceiling in (("steps", MAX_STEPS), ("fanout_limit", MAX_NODES),
                         ("max_nodes", MAX_NODES), ("max_edges", MAX_EDGES),
                         ("max_seeds", MAX_NODES), ("max_transfers", MAX_EDGES)):
        if not _integer(policy[key], 1, ceiling):
            _refuse("policy-capacity")
    if not _number(policy["hop_attenuation"]) or policy["hop_attenuation"] > 1:
        _refuse("policy-attenuation")
    gains = policy["type_gains"]
    if type(gains) is not dict or not 0 < len(gains) <= MAX_NODES:
        _refuse("policy-type-capacity")
    for kind, gain in gains.items():
        if not _token(kind) or not _number(gain):
            _refuse("policy-type-gain")


def _admit_graph(graph, seeds, policy):
    _admit_policy(policy)
    _keys(graph, _GRAPH_KEYS, "graph")
    if not _integer(graph["v"], 1, 1):
        _refuse("graph-version")
    if graph["complete"] is not True:
        _refuse("graph-incomplete")
    nodes, edges = graph["nodes"], graph["edges"]
    if type(nodes) is not list or len(nodes) > policy["max_nodes"]:
        _refuse("node-capacity")
    if type(edges) is not list or len(edges) > policy["max_edges"]:
        _refuse("edge-capacity")
    if type(seeds) is not list or len(seeds) > policy["max_seeds"]:
        _refuse("seed-capacity")
    identities = set()
    for node in nodes:
        _keys(node, _NODE_KEYS, "node")
        if not _token(node["id"], subject=True) or node["id"] in identities:
            _refuse("node-identity")
        if type(node["origin"]) is not str or node["origin"] not in _ORIGINS:
            _refuse("node-origin")
        identities.add(node["id"])
    edge_ids, triples = set(), set()
    for edge in edges:
        _keys(edge, _EDGE_KEYS, "edge")
        if not _token(edge["id"]) or edge["id"] in edge_ids:
            _refuse("edge-identity")
        if not _token(edge["s"], subject=True) or not _token(edge["d"], subject=True) \
                or edge["s"] not in identities or edge["d"] not in identities:
            _refuse("edge-endpoint")
        if not _token(edge["t"]) or edge["t"] not in policy["type_gains"]:
            _refuse("edge-undeclared-type")
        triple = (edge["s"], edge["d"], edge["t"])
        if triple in triples:
            _refuse("edge-duplicate-typed-direction")
        if not _number(edge["weight"], positive=True):
            _refuse("edge-weight")
        if type(edge["provenance"]) is not str or edge["provenance"] not in _PROVENANCE \
                or type(edge["scope"]) is not str or edge["scope"] != _PROVENANCE[edge["provenance"]]:
            _refuse("edge-provenance-scope")
        edge_ids.add(edge["id"])
        triples.add(triple)
    seeded = set()
    for seed in seeds:
        _keys(seed, _SEED_KEYS, "seed")
        if not _token(seed["id"], subject=True) or seed["id"] not in identities or seed["id"] in seeded:
            _refuse("seed-identity")
        if not _number(seed["activation"]):
            _refuse("seed-activation")
        digest = seed["source_sha256"]
        if type(digest) is not str or _DIGEST.fullmatch(digest) is None:
            _refuse("seed-source-binding")
        seeded.add(seed["id"])
    _budget({"graph": graph, "seeds": seeds, "policy": policy})


def _snapshot(graph, seeds, policy):
    _admit_graph(graph, seeds, policy)
    admitted_graph = {"v": graph["v"], "complete": graph["complete"],
                      "nodes": [dict(node) for node in graph["nodes"]],
                      "edges": [dict(edge) for edge in graph["edges"]]}
    admitted_seeds = [dict(seed) for seed in seeds]
    admitted_policy = dict(policy)
    admitted_policy["type_gains"] = dict(policy["type_gains"])
    _admit_graph(admitted_graph, admitted_seeds, admitted_policy)
    return admitted_graph, admitted_seeds, admitted_policy


def _full_fans(graph, policy):
    """Normalize every eligible edge before any fanout emission cap."""
    outgoing = {node["id"]: [] for node in graph["nodes"]}
    for edge in graph["edges"]:
        gain = float(policy["type_gains"][edge["t"]])
        # A declared zero gain disables a type. Positive products vanishing
        # through representation loss are refusals, never disabled edges.
        if gain == 0:
            continue
        effective = _multiply(float(edge["weight"]), gain, "effective-weight")
        outgoing[edge["s"]].append((edge, effective))
    normalized = {}
    for source, entries in outgoing.items():
        entries.sort(key=lambda item: item[0]["id"])
        total = _sum((weight for _, weight in entries), "full-fan-weight")
        shares = []
        for edge, weight in entries:
            share = weight / total
            if not math.isfinite(share) or not 0 < share <= 1:
                _refuse("numeric-normalized-share-domain-or-underflow")
            shares.append((edge, share))
        normalized[source] = (total, shares)
    return normalized


def _propagate(graph, seeds, policy):
    fans = _full_fans(graph, policy)
    pulse = {seed["id"]: float(seed["activation"]) for seed in seeds if seed["activation"] > 0}
    received = {node["id"]: [] for node in graph["nodes"]}
    attenuation = float(policy["hop_attenuation"])
    rounds, transfer_count = [], 0
    for step in range(1, policy["steps"] + 1):
        transfers, fan_caps, sinks = [], [], []
        incoming = {node["id"]: [] for node in graph["nodes"]}
        for node in graph["nodes"]:
            source = node["id"]
            activation = pulse.get(source, 0.0)
            if activation == 0:
                continue
            total, full_fan = fans[source]
            if not full_fan:
                sinks.append({"source": source, "activation": activation})
                continue
            outgoing_activation = _multiply(activation, attenuation, "attenuated-pulse")
            if outgoing_activation == 0:
                continue
            # Full normalization above cannot be changed by the cap below.
            admitted_fan = full_fan[:policy["fanout_limit"]]
            transfer_count += len(admitted_fan)
            if transfer_count > policy["max_transfers"]:
                _refuse("transfer-capacity")
            for edge, share in admitted_fan:
                contribution = _multiply(outgoing_activation, share, "transfer-contribution")
                incoming[edge["d"]].append(contribution)
                received[edge["d"]].append(contribution)
                transfers.append({"edge_id": edge["id"], "s": source, "d": edge["d"], "t": edge["t"],
                                  "provenance": edge["provenance"], "edge_scope": edge["scope"],
                                  "source_activation": activation, "full_fan_count": len(full_fan),
                                  "full_fan_weight": total, "normalized_share": share,
                                  "activation": contribution})
            if len(admitted_fan) < len(full_fan):
                omitted_share = _sum((share for _, share in full_fan[len(admitted_fan):]), "omitted-share")
                dropped = _multiply(outgoing_activation, omitted_share, "dropped-activation")
                fan_caps.append({"source": source, "full_fan_count": len(full_fan),
                                 "emitted_count": len(admitted_fan), "dropped_activation": dropped})
        # Synchronous pulses: no within-round cascading and no seed restart.
        pulse = {identity: _sum(values, "received-pulse") for identity, values in incoming.items() if values}
        rounds.append({"step": step, "transfers": transfers, "fan_caps": fan_caps, "sinks": sinks})
    seeded = {seed["id"] for seed in seeds}
    rows = []
    for node in graph["nodes"]:
        values = received[node["id"]]
        if values:
            score = _sum(values, "cumulative-score")
            if score <= 0:
                _refuse("numeric-cumulative-score-underflow")
            rows.append({"subject": node["id"], "origin": node["origin"], "score": score,
                         "scope": "retrieval-only", "in_seed": node["id"] in seeded})
    # Python's stable sort preserves the explicitly declared node-input tie.
    rows.sort(key=lambda row: -row["score"])
    return rows, rounds


def spread(graph, seeds, *, policy):
    """Return bounded received-sum ranks and transfer witnesses, never content.

    All shapes, capacities, scalar domains and the whole request byte budget
    admit before detachment or score work. Every edge in the admitted graph
    participates in full fan construction, including edges later omitted by
    the emission cap. Zero seed activity and zero type/attenuation policy are
    explicit; positive numerical contributions may not silently become zero.
    """
    try:
        admitted_graph, admitted_seeds, admitted_policy = _snapshot(graph, seeds, policy)
        rows, rounds = _propagate(admitted_graph, admitted_seeds, admitted_policy)
        return {"v": 1, "component": "typed-fan-spreading", "status": "computed-unverified",
                "scope": "retrieval-only", "graph_sha256": _sha(admitted_graph),
                "seeds_sha256": _sha(admitted_seeds), "policy_sha256": _sha(admitted_policy),
                "order": [row["subject"] for row in rows], "rows": rows, "rounds": rounds,
                "non_claims": list(SPREAD_NON_CLAIMS)}
    except SpreadingRefusal:
        raise
    except (TypeError, ValueError, OverflowError, KeyError, RecursionError, UnicodeError) as exc:
        raise SpreadingRefusal("graph-input-or-numeric-domain") from exc
