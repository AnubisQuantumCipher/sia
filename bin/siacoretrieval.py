"""Joint-activity strengthening with separately declared retrieval hygiene.

The local positive product follows the bilinear term in Gerstner, Kistler,
Naud & Paninski, Neuronal Dynamics, section 19.2.1, equation 19.3:
https://neuronaldynamics.epfl.ch/online/Ch19.S2.html
The basic positive rule does not itself weaken weights. Applying its product
to discrete delivered activities and storing symmetric pair weights is an
engineering event mapping, not a measurement of neural activity.

Elapsed-period retention, exclusions, floor pruning and degree caps are
separate engineering hygiene. They are reconstructed from the complete
supplied trace at an explicit observation time, never applied per call.
All original delivery boundaries and positive contributions remain witnessed.
Only policy-retained learned adjacency is projected, always retrieval-only.
This module reads or writes no corpus, database, clock, model, or hidden state.
"""

import hashlib
import json
import math
import re


# Representation/resource ceilings copied from the admitted local protocols.
# Callers supply their operation-specific limits and all learning/hygiene
# choices separately; these ceilings are not fitted cognitive parameters.
MAX_SAFE_INTEGER = 9007199254740991
MAX_NODES = 256
MAX_RECORDS = 4096
MAX_INPUT_BYTES = 2097152
MAX_SUBJECT_BYTES = 1024
MAX_ID_BYTES = 128

COMMON_NON_CLAIMS = (
    "computed-unverified is a local floating-point software result, not a JACKAL assurance class or proof.",
    "Supplied delivery completeness, activity values, and timestamps are caller premises; hashes do not authenticate them.",
    "Learned co-retrieval adjacency is retrieval-only and does not establish the truth or origin of any page.",
    "Original content and origin labels remain unchanged.",
    "No biological learning mechanism or held-out retrieval improvement is established.",
)
DIRECT_NON_CLAIMS = COMMON_NON_CLAIMS + (
    "Joint-activity multiplication supplies only a local positive update, not a complete learning or forgetting model.",
)
LEARNING_NON_CLAIMS = COMMON_NON_CLAIMS + (
    "Mapping delivered activity to symmetric pair updates is an engineering event discretization, not measured neural activity.",
    "Floor-period retention, pruning thresholds, exclusions, and degree caps are explicit engineering hygiene, not the published continuous learning dynamics.",
    "Only the complete supplied delivery trace is reconstructed; no hidden initial weights or unreported history are included.",
    "The emitted graph is the complete policy-retained learned projection, not the factual corpus graph or the unpruned association population.",
)

_SUBJECT = re.compile(r"[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*")
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_ORIGINS = frozenset(("evidence", "derived", "model", "legacy-unlabeled"))
_POLICY_KEYS = {
    "v", "algorithm", "time_unit", "learning_rate", "excluded_subjects", "hygiene",
    "max_nodes", "max_deliveries", "max_activities_per_delivery", "max_total_activities",
    "max_pair_updates", "max_pairs", "max_graph_edges",
}
_HYGIENE_KEYS = {"algorithm", "period_seconds", "retention_per_period", "weight_floor", "degree_cap", "cap_order"}
_TRACE_KEYS = {"v", "complete", "nodes", "deliveries"}
_NODE_KEYS = {"id", "origin"}
_DELIVERY_KEYS = {"id", "timestamp", "complete", "source_sha256", "activities"}
_ACTIVITY_KEYS = {"id", "activation"}


class CoretrievalRefusal(ValueError):
    """The complete observation could not be admitted or represented."""

    def __init__(self, reason):
        self.reason = reason
        self.non_claims = COMMON_NON_CLAIMS
        super().__init__("co-retrieval refused: " + reason)


def _refuse(reason):
    raise CoretrievalRefusal(reason)


def _keys(value, required, label):
    if type(value) is not dict or len(value) != len(required) \
            or any(type(key) is not str for key in value) or set(value) != required:
        _refuse(label + "-shape")


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _number(value, *, positive=False):
    if type(value) not in (int, float):
        return False
    # Reject out-of-range Python integers before any floating conversion.
    return 0 <= value <= MAX_SAFE_INTEGER and (not positive or value > 0) \
        and math.isfinite(value)


def _token(value, *, subject=False):
    maximum, pattern = (MAX_SUBJECT_BYTES, _SUBJECT) if subject else (MAX_ID_BYTES, _IDENTITY)
    return type(value) is str and 0 < len(value) <= maximum and pattern.fullmatch(value) is not None


def _budget(value):
    """Bound shape-admitted ASCII JSON before detachment or serialization."""
    consumed = 0

    def count(item):
        nonlocal consumed
        kind = type(item)
        if kind is str:
            # Accepted token grammars and closed labels have no JSON escapes.
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
    _budget(value)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_INPUT_BYTES:
        _refuse("serialized-byte-capacity")
    return hashlib.sha256(encoded).hexdigest()


def _multiply(left, right, label):
    result = left * right
    if not math.isfinite(result):
        _refuse("numeric-" + label + "-overflow")
    if result == 0 and left != 0 and right != 0:
        _refuse("numeric-" + label + "-underflow")
    return result


def _delta(rate, pre, post):
    # An intentionally inactive side satisfies the zero-update contract even
    # if multiplying the other small factors first would underflow.
    if pre == 0 or post == 0:
        return 0.0
    return _multiply(_multiply(float(rate), float(pre), "joint-product"), float(post), "joint-product")


def pair_increment(*, learning_rate, pre_activity, post_activity):
    """Return only the local positive product, with no forgetting or caps."""
    try:
        if not _number(learning_rate, positive=True) \
                or not _number(pre_activity) or not _number(post_activity):
            _refuse("joint-activity-numeric-domain")
        inputs = {"learning_rate": learning_rate, "pre_activity": pre_activity, "post_activity": post_activity}
        _budget(inputs)
        delta = _delta(learning_rate, pre_activity, post_activity)
        return {"v": 1, "component": "joint-activity-increment", "status": "computed-unverified",
                "delta": delta, "input_sha256": _sha(inputs), "non_claims": list(DIRECT_NON_CLAIMS)}
    except CoretrievalRefusal:
        raise
    except (TypeError, ValueError, OverflowError, KeyError, RecursionError, UnicodeError) as exc:
        raise CoretrievalRefusal("joint-input-or-numeric-domain") from exc


def _admit_policy(policy):
    _keys(policy, _POLICY_KEYS, "policy")
    if not _integer(policy["v"], 1, 1):
        _refuse("policy-version")
    for key, required in (("algorithm", "joint-activity-product-v1"), ("time_unit", "unix-seconds-integer")):
        if type(policy[key]) is not str or policy[key] != required:
            _refuse("policy-contract")
    if not _number(policy["learning_rate"], positive=True):
        _refuse("policy-learning-rate")
    for key, ceiling in (("max_nodes", MAX_NODES), ("max_deliveries", MAX_RECORDS),
                         ("max_activities_per_delivery", MAX_NODES), ("max_total_activities", MAX_RECORDS),
                         ("max_pair_updates", MAX_RECORDS), ("max_pairs", MAX_RECORDS),
                         ("max_graph_edges", MAX_RECORDS)):
        if not _integer(policy[key], 1, ceiling):
            _refuse("policy-capacity")
    hygiene = policy["hygiene"]
    _keys(hygiene, _HYGIENE_KEYS, "hygiene")
    for key, required in (("algorithm", "elapsed-period-retention-v1"), ("cap_order", "weight-desc-pair-id")):
        if type(hygiene[key]) is not str or hygiene[key] != required:
            _refuse("hygiene-contract")
    if not _integer(hygiene["period_seconds"], 1, MAX_SAFE_INTEGER) \
            or not _integer(hygiene["degree_cap"], 1, MAX_NODES):
        _refuse("hygiene-capacity")
    if not _number(hygiene["retention_per_period"], positive=True) \
            or hygiene["retention_per_period"] > 1 or not _number(hygiene["weight_floor"]):
        _refuse("hygiene-numeric-domain")
    exclusions = policy["excluded_subjects"]
    if type(exclusions) is not list or len(exclusions) > policy["max_nodes"]:
        _refuse("exclusion-capacity")
    unique = set()
    for subject in exclusions:
        if not _token(subject, subject=True) or subject in unique:
            _refuse("exclusion-identity")
        unique.add(subject)


def _admit_trace(trace, observed_at, policy):
    _admit_policy(policy)
    if not _integer(observed_at, 0, MAX_SAFE_INTEGER):
        _refuse("observation-timestamp")
    _keys(trace, _TRACE_KEYS, "trace")
    if not _integer(trace["v"], 1, 1):
        _refuse("trace-version")
    if trace["complete"] is not True:
        _refuse("trace-incomplete")
    nodes, deliveries = trace["nodes"], trace["deliveries"]
    if type(nodes) is not list or len(nodes) > policy["max_nodes"]:
        _refuse("node-capacity")
    if type(deliveries) is not list or len(deliveries) > policy["max_deliveries"]:
        _refuse("delivery-capacity")
    subjects = set()
    for node in nodes:
        _keys(node, _NODE_KEYS, "node")
        if not _token(node["id"], subject=True) or node["id"] in subjects:
            _refuse("node-identity")
        if type(node["origin"]) is not str or node["origin"] not in _ORIGINS:
            _refuse("node-origin")
        subjects.add(node["id"])
    excluded = set(policy["excluded_subjects"])
    if not excluded <= subjects:
        _refuse("exclusion-unknown-subject")
    delivery_ids, unique_pairs = set(), set()
    total_activities, pair_updates, previous = 0, 0, None
    for delivery in deliveries:
        _keys(delivery, _DELIVERY_KEYS, "delivery")
        if not _token(delivery["id"]) or delivery["id"] in delivery_ids:
            _refuse("delivery-identity")
        if delivery["complete"] is not True:
            _refuse("delivery-incomplete")
        timestamp = delivery["timestamp"]
        if not _integer(timestamp, 0, MAX_SAFE_INTEGER):
            _refuse("delivery-timestamp")
        if timestamp > observed_at:
            _refuse("future-delivery")
        if previous is not None and timestamp < previous:
            _refuse("delivery-chronology")
        digest = delivery["source_sha256"]
        if type(digest) is not str or len(digest) != 64 or _DIGEST.fullmatch(digest) is None:
            _refuse("delivery-source-binding")
        activities = delivery["activities"]
        if type(activities) is not list or len(activities) > policy["max_activities_per_delivery"]:
            _refuse("delivery-activity-capacity")
        total_activities += len(activities)
        if total_activities > policy["max_total_activities"]:
            _refuse("total-activity-capacity")
        active_ids = set()
        for activity in activities:
            _keys(activity, _ACTIVITY_KEYS, "activity")
            if not _token(activity["id"], subject=True) \
                    or activity["id"] not in subjects or activity["id"] in active_ids:
                _refuse("activity-identity")
            if not _number(activity["activation"]):
                _refuse("activity-numeric-domain")
            active_ids.add(activity["id"])
        # Count the complete prospective witness population without score
        # arithmetic or a detached copy. Never admit an aggregate/truncated
        # prefix merely because a later floor or degree cap might remove it.
        for left, activity in enumerate(activities):
            if activity["id"] in excluded or activity["activation"] == 0:
                continue
            for right in range(left + 1, len(activities)):
                other = activities[right]
                if other["id"] in excluded or other["activation"] == 0:
                    continue
                pair_updates += 1
                if pair_updates > policy["max_pair_updates"]:
                    _refuse("pair-update-capacity")
                a, b = sorted((activity["id"], other["id"]))
                unique_pairs.add((a, b))
                if len(unique_pairs) > policy["max_pairs"]:
                    _refuse("pair-capacity")
        previous = timestamp
        delivery_ids.add(delivery["id"])
    _budget({"trace": trace, "observed_at": observed_at, "policy": policy})


def _snapshot(trace, observed_at, policy):
    _admit_trace(trace, observed_at, policy)
    admitted = {"v": trace["v"], "complete": trace["complete"],
                "nodes": [dict(node) for node in trace["nodes"]], "deliveries": []}
    for delivery in trace["deliveries"]:
        copied = dict(delivery)
        copied["activities"] = [dict(activity) for activity in delivery["activities"]]
        admitted["deliveries"].append(copied)
    admitted_policy = dict(policy)
    admitted_policy["hygiene"] = dict(policy["hygiene"])
    admitted_policy["excluded_subjects"] = list(policy["excluded_subjects"])
    # Computation only consumes this independently admitted private copy.
    _admit_trace(admitted, observed_at, admitted_policy)
    return admitted, admitted_policy


def _retention(retention, periods):
    result = math.pow(float(retention), periods)
    if result == 0:
        _refuse("numeric-retention-underflow")
    if not math.isfinite(result) or not 0 < result <= 1:
        _refuse("numeric-retention-domain")
    return result


def _positive_sum(values, label):
    try:
        result = math.fsum(values)
    except (OverflowError, ValueError) as exc:
        raise CoretrievalRefusal("numeric-" + label + "-range") from exc
    if not math.isfinite(result):
        _refuse("numeric-" + label + "-overflow")
    if result <= 0:
        _refuse("numeric-" + label + "-underflow")
    return result


def _reconstruct(trace, observed_at, policy):
    excluded = set(policy["excluded_subjects"])
    hygiene = policy["hygiene"]
    learned, delivery_witnesses = {}, []
    for delivery in trace["deliveries"]:
        delivery_sha256 = _sha(delivery)
        activities = {activity["id"]: activity["activation"] for activity in delivery["activities"]}
        eligible, zero, omitted = [], [], []
        for subject in sorted(activities):
            if subject in excluded:
                omitted.append(subject)
            elif activities[subject] == 0:
                zero.append(subject)
            else:
                eligible.append(subject)
        witness = {"id": delivery["id"], "timestamp": delivery["timestamp"],
                   "delivery_sha256": delivery_sha256, "eligible_subjects": eligible,
                   "zero_subjects": zero, "excluded_subjects": omitted, "pairs": []}
        delivery_witnesses.append(witness)
        multiplier = None
        # Integer subtraction and floor division precede any floating work.
        age = observed_at - delivery["timestamp"]
        periods = age // hygiene["period_seconds"]
        for left, a in enumerate(eligible):
            for right in range(left + 1, len(eligible)):
                b = eligible[right]
                if multiplier is None:
                    multiplier = _retention(hygiene["retention_per_period"], periods)
                raw = _delta(policy["learning_rate"], activities[a], activities[b])
                increment = _multiply(raw, multiplier, "retained-contribution")
                contribution = {"delivery_id": delivery["id"], "delivery_sha256": delivery_sha256,
                                "timestamp": delivery["timestamp"], "age_seconds": age,
                                "elapsed_periods": periods, "raw_increment": raw,
                                "retention_multiplier": multiplier, "increment": increment}
                pair = learned.setdefault((a, b), {"a": a, "b": b, "contributions": []})
                pair["contributions"].append(contribution)
                pair["last_use"] = delivery["timestamp"]
                witness["pairs"].append([a, b])
    pairs = []
    for key in sorted(learned):
        pair = learned[key]
        pair["raw_weight"] = _positive_sum((row["raw_increment"] for row in pair["contributions"]), "raw-weight")
        pair["weight"] = _positive_sum((row["increment"] for row in pair["contributions"]), "retained-weight")
        pair["retained"] = False
        pair["reason"] = "below-floor" if pair["weight"] < hygiene["weight_floor"] else None
        pairs.append(pair)
    # Greedy symmetric degree admission uses the same global deterministic
    # order regardless of delivery arrival order among equal timestamps.
    degree = {node["id"]: 0 for node in trace["nodes"]}
    ranked = sorted(pairs, key=lambda pair: (-pair["weight"], pair["a"], pair["b"]))
    for pair in ranked:
        if pair["reason"] is not None:
            continue
        a, b = pair["a"], pair["b"]
        if degree[a] >= hygiene["degree_cap"] or degree[b] >= hygiene["degree_cap"]:
            pair["reason"] = "degree-cap"
            continue
        pair["retained"] = True
        degree[a] += 1
        degree[b] += 1
    return pairs, delivery_witnesses


def _project(trace, pairs, policy):
    # Admit the entire reciprocal projection before constructing edge output.
    edge_count = 0
    for pair in pairs:
        if not pair["retained"]:
            continue
        if not _number(pair["weight"], positive=True):
            _refuse("projected-weight-representation")
        for _ in ("forward", "reverse"):
            edge_count += 1
            if edge_count > policy["max_graph_edges"]:
                _refuse("graph-edge-capacity")
    edges = []
    for pair in pairs:
        if not pair["retained"]:
            continue
        for source, target in ((pair["a"], pair["b"]), (pair["b"], pair["a"])):
            edges.append({"id": _sha({"s": source, "d": target, "t": "coreturn"}),
                          "s": source, "d": target, "t": "coreturn", "weight": pair["weight"],
                          "provenance": "learned-coreturn", "scope": "retrieval-only"})
    return {"v": 1, "complete": True, "nodes": [dict(node) for node in trace["nodes"]], "edges": edges}


def learn_coretrieval(trace, *, observed_at, policy):
    """Rebuild learned-only adjacency without hidden state or per-call decay.

    Admit the complete trace, scalar policies, capacities and byte budget
    before copying, serialization or score arithmetic. Every delivered event
    gets a witness, even if its activities are zero, empty or excluded. Every
    positive joint contribution remains in its pair's history before explicit
    hygiene pruning. The emitted reciprocal graph preserves all node origins
    but makes no factual adjacency claim.
    """
    try:
        admitted, admitted_policy = _snapshot(trace, observed_at, policy)
        pairs, witnesses = _reconstruct(admitted, observed_at, admitted_policy)
        graph = _project(admitted, pairs, admitted_policy)
        return {"v": 1, "component": "co-retrieval-strengthening", "status": "computed-unverified",
                "observed_at": observed_at, "trace_sha256": _sha(admitted), "policy_sha256": _sha(admitted_policy),
                "graph": graph, "graph_sha256": _sha(graph), "pairs": pairs,
                "delivery_witnesses": witnesses, "non_claims": list(LEARNING_NON_CLAIMS)}
    except CoretrievalRefusal:
        raise
    except (TypeError, ValueError, OverflowError, KeyError, RecursionError, UnicodeError) as exc:
        raise CoretrievalRefusal("trace-input-or-numeric-domain") from exc
