"""Pure prequential novelty/surprisal replay and an engineering encoding map.

Xu et al. (2021), equations 1--2, motivate negative log relative frequency
and distinguish rarity from conditional expectation:
https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1009070
Poole and Mackworth, section 7.8, supply the Dirichlet count update and
posterior-predictive mean used here, independently within each supplied context:
https://www.cs.ubc.ca/~poole/aibook/html1e/ArtInt_196.html
Lisman and Grace (2005) motivate a novelty/plasticity hypothesis, not the
numeric capped-linear gain map below: https://pubmed.ncbi.nlm.nih.gov/15924857/

This is not SurNoR's surprise-modulated leaky transition model, its Bayes
Factor surprise, or Bayesian-KL surprise. Roster, prior, observation time,
signal choice, gains and resource limits are explicit caller inputs. No
clock, filesystem, resident memory, random state or external service is read.
"""

import copy
import hashlib
import json
import math
import re


# Representation ceilings, not fitted cognitive parameters. Callers must
# independently supply their own capacities within these protocol limits.
MAX_SAFE_INTEGER = 9007199254740991
MAX_EVENTS = 4096
MAX_SYMBOLS = 256
MAX_CONTEXTS = 256
MAX_TOKEN_BYTES = 4096
MAX_EVENT_ID_BYTES = 128
MAX_INPUT_BYTES = 2097152
NON_CLAIMS = (
    "computed-unverified labels local floating-point arithmetic, not JACKAL exact or formal-bounded assurance.",
    "Complete history and predeclared rosters are caller premises; hashes bind supplied bytes but do not authenticate events, source provenance, or completeness.",
    "The Dirichlet interpretation assumes categorical observations independent given fixed model probabilities, globally and within each supplied context; this assumption is not established for real history.",
    "The capped-linear encoding-strength map is an explicit engineering hypothesis, not a measured biological gain law.",
    "No dopamine, synaptic plasticity, biological memory mechanism, cognition, or neuroscience equivalence is established.",
    "Context surprisal is posterior-predictive Shannon information, not Bayesian-KL or Bayes Factor surprise; this does not reproduce SurNoR's surprise-modulated leaky transition model.",
    "All admitted events retain their original fields and origin labels; encoding strength neither removes evidence nor promotes model output to evidence.",
    "No retrieval probability, recall improvement, held-out win, or runtime integration is established.",
)
_POLICY_KEYS = {
    "v", "algorithm", "time_unit", "pseudocount", "signal", "strength_base",
    "strength_scale", "strength_cap", "max_events", "max_symbols", "max_contexts",
}
_TRACE_KEYS = {"v", "complete", "symbols", "contexts", "events"}
_EVENT_KEYS = {"id", "timestamp", "symbol", "context", "origin", "source_sha256"}
_TOKEN = re.compile(r"[a-z0-9][a-z0-9._:/-]*")
_EVENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ORIGINS = frozenset({"evidence", "derived", "model", "legacy-unlabeled"})
_SIGNALS = frozenset({"relative-novelty", "context-surprisal"})


class EncodingRefusal(ValueError):
    """The complete supplied replay could not be admitted or represented."""

    def __init__(self, reason):
        self.reason = reason
        self.non_claims = NON_CLAIMS
        super().__init__("prediction-conditioned-encoding refused: " + reason)


def _refuse(reason):
    raise EncodingRefusal(reason)


def _keys(value, expected, label):
    if type(value) is not dict or len(value) != len(expected) \
            or any(type(key) is not str for key in value) or set(value) != expected:
        _refuse(label + "-shape")


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _number(value, *, positive):
    # Bound arbitrary Python integers before any conversion to binary float.
    if type(value) not in (int, float) or not 0 <= value <= MAX_SAFE_INTEGER \
            or positive and value == 0:
        return False
    return math.isfinite(value)


def _token(value, maximum, pattern):
    # Closed ASCII grammars exclude JSON escaping and allow a byte budget to
    # be checked without first serializing potentially large input strings.
    return type(value) is str and 0 < len(value) <= maximum \
        and pattern.fullmatch(value) is not None


def _policy(value):
    _keys(value, _POLICY_KEYS, "policy")
    if not _integer(value["v"], 1, 1):
        _refuse("policy-version")
    for key, required in (
            ("algorithm", "dirichlet-prequential-information-v1"),
            ("time_unit", "unix-seconds-integer")):
        if type(value[key]) is not str or value[key] != required:
            _refuse("policy-contract")
    if type(value["signal"]) is not str or value["signal"] not in _SIGNALS:
        _refuse("policy-signal")
    if not _integer(value["pseudocount"], 1, MAX_SAFE_INTEGER):
        _refuse("policy-pseudocount")
    if not _number(value["strength_base"], positive=True) \
            or not _number(value["strength_scale"], positive=False) \
            or not _number(value["strength_cap"], positive=True):
        _refuse("policy-numeric-domain")
    for key, ceiling in (("max_events", MAX_EVENTS), ("max_symbols", MAX_SYMBOLS),
                         ("max_contexts", MAX_CONTEXTS)):
        if not _integer(value[key], 1, ceiling):
            _refuse("policy-capacity")


def _roster(value, maximum, label):
    if type(value) is not list or not 0 < len(value) <= maximum:
        _refuse(label + "-capacity")
    seen = set()
    for name in value:
        if not _token(name, MAX_TOKEN_BYTES, _TOKEN) or name in seen:
            _refuse(label + "-identity")
        seen.add(name)
    return seen


def _trace(value, observed_at, policy):
    _keys(value, _TRACE_KEYS, "trace")
    if not _integer(value["v"], 1, 1):
        _refuse("trace-version")
    if value["complete"] is not True:
        _refuse("trace-incomplete")
    symbols = _roster(value["symbols"], policy["max_symbols"], "symbol-roster")
    contexts = _roster(value["contexts"], policy["max_contexts"], "context-roster")
    events = value["events"]
    if type(events) is not list or len(events) > policy["max_events"]:
        _refuse("event-capacity")
    identities = set()
    previous = None
    for event in events:
        _keys(event, _EVENT_KEYS, "event")
        if not _token(event["id"], MAX_EVENT_ID_BYTES, _EVENT_ID) \
                or event["id"] in identities:
            _refuse("event-identity")
        if not _token(event["symbol"], MAX_TOKEN_BYTES, _TOKEN) \
                or event["symbol"] not in symbols \
                or not _token(event["context"], MAX_TOKEN_BYTES, _TOKEN) \
                or event["context"] not in contexts:
            _refuse("event-outside-declared-roster")
        if type(event["origin"]) is not str or event["origin"] not in _ORIGINS \
                or not _token(event["source_sha256"], 64, _SHA256):
            _refuse("event-provenance")
        timestamp = event["timestamp"]
        if not _integer(timestamp, 0, MAX_SAFE_INTEGER):
            _refuse("event-timestamp")
        if timestamp > observed_at:
            _refuse("future-event")
        if previous is not None and timestamp < previous:
            _refuse("event-chronology")
        previous = timestamp
        identities.add(event["id"])


def _input_byte_budget(value):
    """Count admitted ASCII JSON without making a serialized copy or hash."""
    consumed = 0

    def count(item):
        nonlocal consumed
        kind = type(item)
        if kind is str:
            consumed += len(item) + len('""')
        elif kind is bool:
            consumed += len("true" if item else "false")
        elif kind in (int, float):
            # Already admitted: bounded integers and finite binary floats.
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


def _validate_inputs(trace, observed_at, policy):
    _policy(policy)
    if not _integer(observed_at, 0, MAX_SAFE_INTEGER):
        _refuse("observation-timestamp")
    _trace(trace, observed_at, policy)
    _input_byte_budget({"trace": trace, "observed_at": observed_at, "policy": policy})


def _snapshot_inputs(trace, observed_at, policy):
    # The entire trace, including late events, admits before copying, hashing,
    # or scoring. Strict built-in types exclude caller-defined copy hooks.
    _validate_inputs(trace, observed_at, policy)
    detached_trace = copy.deepcopy(trace)
    detached_policy = copy.deepcopy(policy)
    _validate_inputs(detached_trace, observed_at, detached_policy)
    return detached_trace, detached_policy


def _sha(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_INPUT_BYTES:
        _refuse("serialized-byte-capacity")
    return hashlib.sha256(encoded).hexdigest()


def _information(prior_count, prior_total, symbols_count, pseudocount):
    # These counters remain Python integers. Only the predictive probability
    # and logarithm are floating-point observations, with no certified status.
    numerator = prior_count + pseudocount
    denominator = prior_total + pseudocount * symbols_count
    probability = numerator / denominator
    if not math.isfinite(probability) or not 0 < probability <= 1:
        _refuse("numeric-probability-domain-or-underflow")
    if numerator < denominator and probability == 1:
        _refuse("numeric-probability-rounding-loss")
    information = -math.log(probability)
    if not math.isfinite(information) or information < 0:
        _refuse("numeric-information-domain")
    if probability < 1 and information == 0:
        _refuse("numeric-information-underflow")
    if information == 0:
        information = 0.0  # Canonical zero for a genuinely certain outcome.
    return {"prior_count": prior_count, "prior_total": prior_total,
            "pseudocount": pseudocount, "symbols_count": symbols_count,
            "probability": probability, "information_nats": information}


def _strength(information, policy):
    base = float(policy["strength_base"])
    scale = float(policy["strength_scale"])
    cap = float(policy["strength_cap"])
    gain = scale * information
    if not math.isfinite(gain) or gain < 0:
        _refuse("numeric-strength-gain-domain")
    if scale > 0 and information > 0 and gain == 0:
        _refuse("numeric-strength-gain-underflow")
    uncapped = base + gain
    if not math.isfinite(uncapped) or uncapped <= 0:
        _refuse("numeric-strength-domain")
    if gain > 0 and (uncapped <= base or uncapped <= gain):
        _refuse("numeric-strength-rounding-loss")
    # Zero scale is intentional neutral encoding; clipping is a distinct,
    # reported engineering choice, never a repair for numeric underflow.
    capped = uncapped > cap
    return {"encoding_strength": cap if capped else uncapped, "capped": capped,
            "strength_gain": gain, "uncapped_strength": uncapped}


def replay_encoding(trace, *, observed_at, policy):
    """Replay a complete trace without mutating or filtering caller events.

    Each score uses counts strictly before its event. The global and the
    event's context-specific counts advance only after the score is retained.
    Equal timestamps preserve caller order; future events never alter earlier
    scores. A refusal returns no partial result and changes no input state.
    """
    try:
        admitted, admitted_policy = _snapshot_inputs(trace, observed_at, policy)
        trace_sha256 = _sha(admitted)
        policy_sha256 = _sha(admitted_policy)
        global_counts = {symbol: 0 for symbol in admitted["symbols"]}
        context_counts = {context: {symbol: 0 for symbol in admitted["symbols"]}
                          for context in admitted["contexts"]}
        global_total = 0
        context_totals = {context: 0 for context in admitted["contexts"]}
        symbols_count = len(admitted["symbols"])
        pseudocount = admitted_policy["pseudocount"]
        rows = []
        for event in admitted["events"]:
            symbol, context = event["symbol"], event["context"]
            novelty = _information(global_counts[symbol], global_total,
                                   symbols_count, pseudocount)
            surprisal = _information(context_counts[context][symbol], context_totals[context],
                                     symbols_count, pseudocount)
            selected = novelty if admitted_policy["signal"] == "relative-novelty" else surprisal
            rows.append({"event": event, "relative_novelty": novelty,
                         "context_surprisal": surprisal,
                         **_strength(selected["information_nats"], admitted_policy)})
            global_counts[symbol] += 1
            global_total += 1
            context_counts[context][symbol] += 1
            context_totals[context] += 1
        return {"v": 1, "component": "prediction-conditioned-encoding",
                "status": "computed-unverified", "complete": True,
                "observed_at": observed_at, "policy": admitted_policy,
                "policy_sha256": policy_sha256, "trace_sha256": trace_sha256,
                "symbols": admitted["symbols"], "contexts": admitted["contexts"],
                "events": rows,
                "final_counts": {"global": global_counts, "contexts": context_counts},
                "non_claims": list(NON_CLAIMS)}
    except EncodingRefusal:
        raise
    except (TypeError, ValueError, OverflowError, KeyError, RecursionError, UnicodeError) as exc:
        raise EncodingRefusal("input-admission-or-numeric-range") from exc
