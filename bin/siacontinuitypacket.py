"""Experimental, inert checkpoint proposals; no capture, grants or I/O.

All source identities and classifications are caller-supplied premises. This
module checks a bounded format and returns references, never executable text.
It is not the SPARK authority gate or a qualified harness restore adapter.
"""

import hashlib
import json
import re

SCHEMA = "sia-agent-checkpoint-proposal-v1"
MAX_BYTES = 65_536
MAX_DEPTH = 6
MAX_CLAIMS = 64
MAX_OPERATIONS = 16
MAX_SEQUENCE = 9_223_372_036_854_775_807
KINDS = (
    "goal", "acceptance", "constraint", "correction", "decision", "rejection",
    "source", "completed", "verification", "failure", "next_action",
    "permission_reference", "pending_approval",
)
STATES = ("planned", "dispatched", "uncertain", "observed_complete")
ORIGINS = ("evidence", "derived", "model", "legacy-unlabeled")
COVERAGE = ("not_observed", "unavailable", "observed_empty", "partial", "complete")
BINDING_KEYS = frozenset((
    "task", "session", "repository", "revision", "dirty", "capture",
))
PACKET_KEYS = frozenset((
    "schema", "binding", "checkpoint", "generation", "previous", "through",
    "coverage", "claims", "operations",
))
CLAIM_KEYS = frozenset((
    "id", "slot", "kind", "source", "sequence", "origin", "role", "replaces",
))
OPERATION_KEYS = frozenset(("id", "action", "state", "source", "result"))
HEX = re.compile(r"[0-9a-f]{64}\Z")
NON_CLAIMS = (
    "UNVERIFIED caller-supplied checkpoint proposal",
    "No original evidence was read or authenticated",
    "No approval is granted and no next action is executed",
    "No durable acknowledgment, freshness or complete capture is established",
)


class PacketRefusal(ValueError):
    """A fixed reason code; never echo untrusted payloads into diagnostics."""


def _fail(reason):
    raise PacketRefusal(reason)


def _keys(value, expected):
    if type(value) is not dict or len(value) != len(expected) or set(value) != expected:
        _fail("keys")


def _member(value, choices):
    if type(value) is not str or value not in choices:
        _fail("enum")


def _digest(value):
    if type(value) is not str or HEX.fullmatch(value) is None:
        _fail("digest")


def _sequence(value, *, positive=False):
    if type(value) is not int or not (int(positive) <= value <= MAX_SEQUENCE):
        _fail("sequence")


def _list(value, limit):
    if type(value) is not list or len(value) > limit:
        _fail("list-capacity")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            _fail("duplicate-key")
        result[key] = value
    return result


def _number(_value):
    _fail("non-integer-number")


def _integer(value):
    if len(value) > 19:
        _fail("integer-capacity")
    return int(value)


def _depth(raw):
    """Bound JSON container depth before the runtime decoder can recurse."""
    depth, quoted, escaped = 0, False, False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > MAX_DEPTH:
                _fail("json-depth")
        elif byte in (93, 125):
            depth -= 1
            if depth < 0:
                _fail("json-depth")
    if depth != 0 or quoted:
        _fail("json-shape")


def _binding(value):
    _keys(value, BINDING_KEYS)
    for field in BINDING_KEYS:
        _digest(value[field])


def _claims(value, through):
    _list(value, MAX_CLAIMS)
    seen, active, prior = {}, {}, 0
    for row in value:
        _keys(row, CLAIM_KEYS)
        for field in ("id", "slot", "source"):
            _digest(row[field])
        _sequence(row["sequence"], positive=True)
        if not prior < row["sequence"] <= through or row["id"] in seen:
            _fail("claim-order-or-identity")
        _member(row["kind"], KINDS)
        _member(row["origin"], ORIGINS)
        _member(row["role"], ("user", "assistant", "tool", "system"))
        if row["role"] == "assistant" and row["origin"] != "model":
            _fail("assistant-origin")
        _replacement(row, seen, active)
        seen[row["id"]] = row
        active[row["slot"]] = row["id"]
        prior = row["sequence"]
    return seen, active


def _replacement(row, seen, active):
    replaced = row["replaces"]
    if replaced is None:
        if row["slot"] in active:
            _fail("missing-supersession")
        return
    _digest(replaced)
    if active.get(row["slot"]) != replaced or replaced not in seen:
        _fail("supersession-predecessor")
    previous = seen[replaced]
    if any(row[key] != previous[key] for key in ("kind", "origin", "role")):
        _fail("supersession-classification")


def _coverage(value, claims):
    _keys(value, frozenset(KINDS))
    for kind in KINDS:
        _member(value[kind], COVERAGE)
        present = any(row["kind"] == kind for row in claims)
        if present != (value[kind] in ("partial", "complete")):
            _fail("coverage-contradiction")


def _operations(value):
    _list(value, MAX_OPERATIONS)
    seen = set()
    for row in value:
        _keys(row, OPERATION_KEYS)
        for field in ("id", "action", "source"):
            _digest(row[field])
        if row["id"] in seen:
            _fail("operation-identity")
        seen.add(row["id"])
        _member(row["state"], STATES)
        if row["result"] is not None:
            _digest(row["result"])
        if row["state"] == "planned" and row["result"] is not None:
            _fail("planned-result")
        if row["state"] == "observed_complete" and row["result"] is None:
            _fail("missing-result-reference")


def decode(raw):
    """Decode only proposal structure. Coverage is a claim, not verified truth."""
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        _fail("input-capacity")
    _depth(raw)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_int=_integer, parse_float=_number,
                           parse_constant=_number)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise PacketRefusal("json") from None
    _keys(value, PACKET_KEYS)
    _member(value["schema"], (SCHEMA,))
    _binding(value["binding"])
    _digest(value["checkpoint"])
    _sequence(value["generation"], positive=True)
    _sequence(value["through"])
    if value["previous"] is not None:
        _digest(value["previous"])
        if value["previous"] == value["checkpoint"]:
            _fail("checkpoint-self-parent")
    if (value["generation"] == 1) != (value["previous"] is None):
        _fail("checkpoint-parent")
    _claims(value["claims"], value["through"])
    _coverage(value["coverage"], value["claims"])
    _operations(value["operations"])
    return value


def references(raw, expected_binding, expected_checkpoint, budget):
    """All-or-refuse reference packet; supplied expected values are not authority.

    Never selects an operation to retry, translates an approval into a grant,
    or embeds caller text. Full supersession history remains in the packet.
    """
    _binding(expected_binding)
    _digest(expected_checkpoint)
    if type(budget) is not int or not 1 <= budget <= MAX_BYTES:
        _fail("output-budget")
    value = decode(raw)
    if value["binding"] != expected_binding \
            or value["checkpoint"] != expected_checkpoint:
        _fail("expected-identity")
    result = {"status": "UNVERIFIED",
              "input_sha256": hashlib.sha256(raw).hexdigest(),
              "non_claims": list(NON_CLAIMS),
              "proposal": value}
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(encoded) > budget:
        _fail("output-capacity")
    return encoded
