"""Descriptive use-trace scores and rank-only candidate ordering.

The strict positive-age variant follows the Base-Level Equation in Anderson
and Schunn (2000), manuscript p. 8, "Implications of the ACT-R Learning Theory:
No Magic Bullets": the natural logarithm of summed power-decayed use ages.
https://act-r.psy.cmu.edu/wordpress/wp-content/uploads/2012/12/39jra_cds_2000_a.pdf

This standalone component supplies no default decay, age offset, observation
clock, admission history, or retrieval integration. A positive age offset is
an explicitly labelled engineering variant. Context, noise, probabilities,
latency, and content/origin rewriting are outside its contract. Computation
uses local floating-point arithmetic, never a borrowed JACKAL status.
"""

import hashlib
import json
import math
import re


# Representation/resource ceilings copied from the admitted local protocols,
# not fitted memory parameters. Every caller must also supply its own limits.
MAX_SAFE_INTEGER = 9007199254740991
MAX_USES = 4096
MAX_CANDIDATES = 256
MAX_INPUT_BYTES = 2097152
MAX_SUBJECT_BYTES = 1024
MAX_USE_ID_BYTES = 128
NON_CLAIMS = (
    "computed-unverified is a local floating-point software result, not a JACKAL assurance class or proof.",
    "Trace completeness is a caller admission premise; hashes bind supplied records but do not authenticate their history.",
    "Positive age offsets are an explicit engineering regularization, not the strict positive-age literature equation.",
    "The component changes only candidate order; it does not rewrite original content or origin labels.",
    "No human-memory mechanism, retrieval probability, latency prediction, or held-out retrieval improvement is established.",
)
_POLICY_KEYS = {
    "v", "algorithm", "time_unit", "decay", "age_offset_seconds", "tie_break",
    "unavailable", "max_uses", "max_total_uses", "max_candidates",
}
_TRACE_KEYS = {"v", "subject", "complete", "uses"}
_USE_KEYS = {"id", "timestamp"}
_SUBJECT = re.compile(r"[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*")
_USE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*")


class ActivationRefusal(ValueError):
    """A complete rank observation could not be admitted or represented."""

    def __init__(self, reason):
        self.reason = reason
        self.non_claims = NON_CLAIMS
        super().__init__("usage-salience refused: " + reason)


def _refuse(reason):
    raise ActivationRefusal(reason)


def _keys(value, required, label):
    if type(value) is not dict or len(value) != len(required) \
            or any(type(key) is not str for key in value) or set(value) != required:
        _refuse(label + "-shape")


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _number(value, *, positive):
    if type(value) not in (int, float):
        return False
    # Check the magnitude before converting an arbitrary Python integer.
    if not 0 <= value <= MAX_SAFE_INTEGER or positive and value == 0:
        return False
    return math.isfinite(value)


def _token(value, maximum, pattern):
    # The closed token grammars are ASCII, so accepted characters are also
    # byte-exact without an unbounded UTF-8 serialization step.
    return type(value) is str and 0 < len(value) <= maximum \
        and pattern.fullmatch(value) is not None


def _policy(value):
    _keys(value, _POLICY_KEYS, "policy")
    if not _integer(value["v"], 1, 1):
        _refuse("policy-version")
    required = {"algorithm": "log-sum-power-law-v1", "time_unit": "unix-seconds-integer",
                "tie_break": "stable-input-order", "unavailable": "last"}
    if any(type(value[key]) is not str or value[key] != expected for key, expected in required.items()):
        _refuse("policy-contract")
    if not _number(value["decay"], positive=True) \
            or not _number(value["age_offset_seconds"], positive=False):
        _refuse("policy-numeric-domain")
    for key, ceiling in (("max_uses", MAX_USES), ("max_total_uses", MAX_USES),
                         ("max_candidates", MAX_CANDIDATES)):
        if not _integer(value[key], 1, ceiling):
            _refuse("policy-capacity")


def _trace(value, observed_at, policy):
    _keys(value, _TRACE_KEYS, "trace")
    if not _integer(value["v"], 1, 1) \
            or not _token(value["subject"], MAX_SUBJECT_BYTES, _SUBJECT):
        _refuse("trace-identity")
    if value["complete"] is not True:
        _refuse("trace-incomplete")
    uses = value["uses"]
    if type(uses) is not list or len(uses) > policy["max_uses"]:
        _refuse("trace-use-capacity")
    identities = set()
    previous = None
    for use in uses:
        _keys(use, _USE_KEYS, "use")
        if not _token(use["id"], MAX_USE_ID_BYTES, _USE_ID) or use["id"] in identities:
            _refuse("use-identity")
        timestamp = use["timestamp"]
        if not _integer(timestamp, 0, MAX_SAFE_INTEGER):
            _refuse("use-timestamp")
        if timestamp > observed_at:
            _refuse("future-use")
        if previous is not None and timestamp < previous:
            _refuse("use-chronology")
        if timestamp == observed_at and policy["age_offset_seconds"] == 0:
            _refuse("zero-age-undefined")
        previous = timestamp
        identities.add(use["id"])


def _input_byte_budget(value):
    """Count the already shape-admitted ASCII JSON before copying/encoding."""
    consumed = 0

    def count(item):
        nonlocal consumed
        kind = type(item)
        if kind is str:
            # Every admitted string and field name is from an ASCII grammar
            # excluding JSON escapes. No private page text is accepted here.
            consumed += len(item) + len('""')
        elif kind is bool:
            consumed += len("true" if item else "false")
        elif kind in (int, float):
            # Integers are bounded and floats finite before reaching this code.
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


def _validate_set(traces, observed_at, policy):
    _policy(policy)
    if not _integer(observed_at, 0, MAX_SAFE_INTEGER):
        _refuse("observation-timestamp")
    if type(traces) is not list or len(traces) > policy["max_candidates"]:
        _refuse("candidate-capacity")
    subjects = set()
    total_uses = 0
    for trace in traces:
        _trace(trace, observed_at, policy)
        if trace["subject"] in subjects:
            _refuse("duplicate-subject")
        subjects.add(trace["subject"])
        total_uses += len(trace["uses"])
        if total_uses > policy["max_total_uses"]:
            _refuse("total-use-capacity")
    _input_byte_budget({"traces": traces, "observed_at": observed_at, "policy": policy})


def _snapshot_inputs(traces, observed_at, policy):
    # Admit the complete candidate set before any scoring, serialization or
    # detachment. Copy every use verbatim: no synthetic or aggregate tail.
    _validate_set(traces, observed_at, policy)
    detached_policy = dict(policy)
    detached_traces = [{"v": trace["v"], "subject": trace["subject"], "complete": trace["complete"],
                        "uses": [{"id": use["id"], "timestamp": use["timestamp"]} for use in trace["uses"]]}
                       for trace in traces]
    # Also check what was actually copied; later computation reads only this
    # private representation, not the caller's mutable input containers.
    _validate_set(detached_traces, observed_at, detached_policy)
    return detached_traces, detached_policy


def _sha(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_INPUT_BYTES:
        _refuse("serialized-byte-capacity")
    return hashlib.sha256(encoded).hexdigest()


def _score(uses, observed_at, policy):
    if not uses:
        return None
    logarithms = []
    decay = float(policy["decay"])
    offset = policy["age_offset_seconds"]
    try:
        for use in uses:
            # Subtract the admitted integers before floating conversion, never
            # convert the epoch timestamps first and lose their difference.
            elapsed = observed_at - use["timestamp"]
            age = elapsed + offset if type(offset) is int else math.fsum((elapsed, offset))
            if not math.isfinite(age) or age <= 0:
                _refuse("numeric-age-domain")
            log_age = math.log(age)
            log_weight = -decay * log_age
            if not math.isfinite(log_weight):
                _refuse("numeric-log-weight-overflow")
            if log_weight == 0 and log_age != 0:
                _refuse("numeric-log-weight-underflow")
            logarithms.append(log_weight)
        # Shift before exponentiation so old valid traces need not first
        # materialize a vanishing absolute power-law sum. This remains local
        # floating-point computation, not a certified enclosure.
        largest = max(logarithms)
        weights = []
        for log_weight in logarithms:
            shifted = log_weight - largest
            if not math.isfinite(shifted):
                _refuse("numeric-shift-overflow")
            weight = math.exp(shifted)
            if weight == 0:
                _refuse("numeric-use-contribution-underflow")
            if not math.isfinite(weight) or weight < 0:
                _refuse("numeric-use-contribution-domain")
            weights.append(weight)
        total = math.fsum(weights)
        if not math.isfinite(total) or total <= 0:
            _refuse("numeric-sum-domain")
        result = largest + math.log(total)
        if not math.isfinite(result):
            _refuse("numeric-score-overflow")
        return result
    except (OverflowError, ValueError) as exc:
        if isinstance(exc, ActivationRefusal):
            raise
        raise ActivationRefusal("numeric-domain-or-range") from exc


def _evaluate_admitted(trace, observed_at, policy, policy_sha256):
    score = _score(trace["uses"], observed_at, policy)
    return {"v": 1, "component": "usage-salience", "status": "computed-unverified" if score is not None else "unavailable",
            "subject": trace["subject"], "observed_at": observed_at, "score": score,
            "reason": None if score is not None else "no-use-history", "uses_count": len(trace["uses"]),
            "trace_sha256": _sha(trace), "policy_sha256": policy_sha256,
            "variant": "strict-positive-age" if policy["age_offset_seconds"] == 0 else "positive-age-offset",
            "non_claims": list(NON_CLAIMS)}


def evaluate_trace(trace, *, observed_at, policy):
    """Score a complete admitted trace without reading any ambient history."""
    try:
        traces, admitted_policy = _snapshot_inputs([trace], observed_at, policy)
        return _evaluate_admitted(traces[0], observed_at, admitted_policy, _sha(admitted_policy))
    except ActivationRefusal:
        raise
    except (TypeError, ValueError, OverflowError, KeyError, RecursionError, UnicodeError) as exc:
        raise ActivationRefusal("input-admission") from exc


def rank_traces(traces, *, observed_at, policy):
    """Return only subject order and witnesses; no page bytes enter this API.

    All candidates admit before numerical work. Unavailable subjects remain in
    the complete roster, ordered last; stable input order resolves score ties
    and unavailable ties. No partial ranking is returned on any refusal.
    """
    try:
        admitted, admitted_policy = _snapshot_inputs(traces, observed_at, policy)
        policy_sha256 = _sha(admitted_policy)
        activations = [_evaluate_admitted(trace, observed_at, admitted_policy, policy_sha256) for trace in admitted]
        ordered = sorted(activations, key=lambda item: (item["score"] is None,
                         -item["score"] if item["score"] is not None else 0))
        return {"v": 1, "component": "usage-salience", "status": "computed-unverified",
                "observed_at": observed_at, "policy_sha256": policy_sha256,
                "trace_set_sha256": _sha(admitted), "order": [item["subject"] for item in ordered],
                "activations": activations, "non_claims": list(NON_CLAIMS)}
    except ActivationRefusal:
        raise
    except (TypeError, ValueError, OverflowError, KeyError, RecursionError, UnicodeError) as exc:
        raise ActivationRefusal("input-admission") from exc
