"""Versioned controller-epoch composition, with no resident side effects.

The component contracts in siaencoding, siaactivation, siaworkspace,
siacoretrieval and siagist retain their own literature and nonclaims. This
module adds explicit engineering joins: threshold admission, one unweighted
use per admitted occurrence/version, immutable held selection reasons, and
rank-only recall. It supplies no clock, policy defaults, source authority,
filesystem publication, consumer execution or retrospective legacy history.

Runtime wrappers must separately witness output, journal unresolved delivery
intents, and commit a complete generation before describing it as available.
An externally pinned state is prior caller authority, not a proof of its
historical workspace chronology. History admission reconstructs typed uses.
"""

import base64
import binascii
import copy
import hashlib
import json
import math
import re

import siaactivation as activation
import siacoretrieval as coretrieval
import siaencoding as encoding
import siaworkspace as workspace


# Existing representation ceilings, not fitted cognitive parameters. Each
# operation also obeys the independently supplied policy's tighter limits.
MAX_INPUT_BYTES = 16777216
MAX_OUTPUT_BYTES = 16777216
MAX_CONTENT_BYTES = 1048576
MAX_SAFE_INTEGER = activation.MAX_SAFE_INTEGER
SCOPE = "complete-controller-observations-since-declared-epoch-v1"
BODY_SCOPE = "result-body-before-queue-health-footer-v1"
DELIVERY_BOUNDARY = "supplied-bytes-admitted-not-observed-output-v1"
NON_CLAIMS = (
    "This is an integrated computed-unverified software transition, not JACKAL assurance, biological cognition, or a held-out win.",
    "A planned state, broadcast, or gist proposal is not durable publication, consumer delivery, acknowledgment, or execution of the resident loop.",
    "Novelty-threshold admission and explicit-delivery exemption are engineering workspace policies, not weighted ACT-R activation or a biological gain law.",
    "Controller encoding and service-output-completed times are distinct from native event times and do not establish human reading, understanding, or successful use.",
    "Complete history is scoped to the externally declared controller epoch; legacy recent-use tails and missing earlier observations are not reconstructed as complete traces.",
    "Hashes bind supplied bytes and version joins, not source authentication, historical completeness, loaded runtime behavior, or protection against hostile same-user mutation.",
    "Original content and origins remain unchanged; learned co-retrieval edges are retrieval-only and gist proposals are derived additions, not replacements for episodes.",
    "All encoding, activation, workspace, co-retrieval, gist, source and delivery nonclaims remain controlling.",
)
_POLICY_KEYS = {
    "schema", "scope", "time_unit", "encoding", "activation", "workspace",
    "coretrieval", "novelty_admission", "activation_events", "workspace_release",
    "recall_order", "delivery_body", "delivery_activity", "idle", "limits",
}
_LIMITS = {
    "max_input_bytes": MAX_INPUT_BYTES, "max_output_bytes": MAX_OUTPUT_BYTES,
    "max_versions": activation.MAX_CANDIDATES,
    "max_observations": encoding.MAX_EVENTS,
    "max_deliveries": coretrieval.MAX_RECORDS,
    "max_rows": activation.MAX_CANDIDATES,
    "max_content_bytes": MAX_CONTENT_BYTES, "max_delivery_bytes": MAX_CONTENT_BYTES,
}
_INTAKE_KEYS = {
    "schema", "epoch_id", "started_at", "complete", "pages", "current_versions",
    "symbols", "contexts", "observations",
}
_PAGE_KEYS = {
    "subject", "content", "origin", "source_sha256", "content_sha256", "version_sha256",
}
_OBSERVATION_KEYS = {
    "id", "timestamp", "version_sha256", "symbol", "context", "native_timestamp",
}
_STATE_KEYS = {
    "schema", "epoch_id", "observed_at", "parent_state_sha256", "intake", "deliveries",
    "policy", "policy_sha256", "uses", "traces", "encoding", "admission", "activation",
    "workspace", "held_selection_receipt", "coretrieval_trace", "coretrieval", "idle",
    "non_claims",
}
_CAPTURE_KEYS = {
    "schema", "epoch_id", "complete", "scope", "intake", "deliveries", "policy",
    "policy_sha256", "observed_at", "uses", "state_sha256", "non_claims", "capture_sha256",
}
_RANK_KEYS = {
    "schema", "status", "epoch_id", "observed_at", "state_sha256", "policy",
    "policy_sha256", "rows", "rows_sha256", "versions", "traces", "activation",
    "order", "non_claims", "rank_sha256",
}
_DELIVERY_KEYS = {
    "schema", "origin", "id", "epoch_id", "completed_at", "ranked_at",
    "rank_sha256", "state_sha256", "policy_sha256", "emitted_row_refs", "rows",
    "output_scope", "output_utf8_base64", "output_bytes", "output_sha256",
    "boundary", "non_claims", "record_sha256",
}
_HEX = re.compile(r"[0-9a-f]{64}")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*")
_SUBJECT = re.compile(r"[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*")
_ORIGINS = frozenset({"evidence", "derived", "model", "legacy-unlabeled"})


class LiveLoopRefusal(ValueError):
    """No partial planned transition or reconstructed trace is returned."""

    def __init__(self, reason, upstream_non_claims=()):
        self.reason = reason
        self.non_claims = list(NON_CLAIMS)
        self.upstream_non_claims = list(upstream_non_claims)
        super().__init__("live-loop refused: " + reason)


def _fail(reason):
    raise LiveLoopRefusal(reason)


def _keys(value, fields, label):
    if type(value) is not dict or any(type(key) is not str for key in value) \
            or set(value) != fields:
        _fail(label + "-shape")


def _integer(value, maximum=MAX_SAFE_INTEGER, minimum=0):
    return type(value) is int and minimum <= value <= maximum


def _digest(value):
    return type(value) is str and _HEX.fullmatch(value) is not None


def _token(value, maximum=activation.MAX_USE_ID_BYTES, pattern=_TOKEN):
    return type(value) is str and 0 < len(value) <= maximum \
        and pattern.fullmatch(value) is not None


_JSON_SHORT_ESCAPES = '"\\\b\f\n\r\t'
_JSON_ASCII_ESCAPABLE = re.compile(r'["\\\x00-\x1f\x7f]')
_JSON_LONG_ASCII_ESCAPES = tuple(
    chr(point) for point in range(0x20)
    if chr(point) not in _JSON_SHORT_ESCAPES)


_CONTROL_LONG_ESCAPES = re.compile("[\\x00-\\x07\\x0b\\x0e-\\x1f]")


def _utf8_length(value):
    """UTF-8 byte count with C-speed encoding, or None for a lone surrogate."""
    try:
        return len(value.encode("utf-8", "strict"))
    except UnicodeEncodeError:
        return None


def _json_string_bytes(value, utf8_length, *, ascii_only=False):
    """Escaped JSON-string bytes (with quotes) from C-speed counts only.

    Identical to serializing the string: ASCII short escapes cost one extra
    byte, other control characters five extra, and under ensure_ascii every
    non-ASCII BMP character is six bytes and every astral character twelve.
    No serializer runs and no JSON text is allocated.
    """
    short = sum(value.count(character) for character in '"\\\b\f\n\r\t')
    long_control = sum(1 for _match in _CONTROL_LONG_ESCAPES.finditer(value))
    if not ascii_only:
        return 2 + utf8_length + short + 5 * long_control
    ascii_length = len(value.encode("ascii", "ignore"))
    non_ascii = len(value) - ascii_length
    astral = len(value.encode("utf-16-le")) // 2 - len(value)
    delete = value.count("\x7f")
    return (2 + ascii_length + short + 5 * long_control + 5 * delete
            + 6 * (non_ascii - astral) + 12 * astral)


def _count_ascii_json_string(item, add, *, ascii_only=False):
    """Count a JSON string's canonical bytes with C-speed scans.

    ASCII contributes its original bytes first, then escape overhead, with no
    encoded copy. Non-ASCII is counted arithmetically from C-speed string
    primitives — exactly the bytes the document will carry; the per-character
    Python loop this replaced made every consistency check of a multi-megabyte
    retained batch take seconds, and a first light with a week's backlog take
    hours. Every addition still passes through the caller's complete-document
    cap. Only a lone surrogate returns to the caller's validation path.
    """
    if not item.isascii():
        # Non-ASCII is counted arithmetically from C-speed string primitives:
        # exactly the escaped bytes the serializer will write, with no
        # serializer call and no JSON text allocated before the bound. A
        # lone surrogate returns to the caller's path, which refuses it.
        utf8_length = _utf8_length(item)
        if utf8_length is None:
            return False
        add(_json_string_bytes(item, utf8_length, ascii_only=ascii_only))
        return True
    add(len('""'))
    add(len(item))
    if _JSON_ASCII_ESCAPABLE.search(item) is None:
        return True
    for character in _JSON_SHORT_ESCAPES:
        add(item.count(character))
    for character in _JSON_LONG_ASCII_ESCAPES:
        # JACKAL status=exact parsed=6-1 exact=5; no formal certificate.
        add(5 * item.count(character))
    if ascii_only:
        # Python's ensure_ascii serializer also escapes DEL.
        add(5 * item.count('\x7f'))
    return True


def _size(value, ceiling):
    """Exact canonical JSON size before copying, hashing or JSON allocation.

    Count every occurrence, including aliased containers. Active-path cycle
    detection and bounded depth also apply to ignored-looking late fields.
    Only built-in JSON values enter; no caller copy or conversion hooks run.
    """
    size, active = 0, set()

    def add(amount):
        nonlocal size
        size += amount
        if size > ceiling:
            _fail("complete-json-byte-capacity")

    def visit(item, depth):
        if depth > 64:
            _fail("complete-json-depth")
        kind = type(item)
        if kind is str:
            if _count_ascii_json_string(item, add):
                return
            add(len('""'))
            # A Unicode page must not force a Python call per codepoint on
            # every replay. Encode only bounded slices, never the complete
            # unchecked document. Strict UTF-8 encoding rejects surrogates.
            for offset in range(0, len(item), 4096):
                chunk = item[offset:offset + 4096]
                try:
                    encoded = chunk.encode('utf-8')
                except UnicodeEncodeError:
                    _fail("unpaired-surrogate")
                add(len(encoded))
                if _JSON_ASCII_ESCAPABLE.search(chunk) is not None:
                    for character in _JSON_SHORT_ESCAPES:
                        add(chunk.count(character))
                    for character in _JSON_LONG_ASCII_ESCAPES:
                        # Same JSON escape overhead as the ASCII lane above.
                        add(5 * chunk.count(character))
        elif kind is bool:
            add(len("true" if item else "false"))
        elif item is None:
            add(len("null"))
        elif kind is int:
            if not -MAX_SAFE_INTEGER <= item <= MAX_SAFE_INTEGER:
                _fail("integer-json-range")
            add(len(str(item)))
        elif kind is float:
            if not math.isfinite(item):
                _fail("nonfinite-json-number")
            add(len(repr(item)))
        elif kind in (dict, list):
            if id(item) in active:
                _fail("cyclic-json")
            active.add(id(item))
            add(len("{}" if kind is dict else "[]"))
            for index, entry in enumerate(item.items() if kind is dict else item):
                if index:
                    add(len(","))
                if kind is dict:
                    key, child = entry
                    if type(key) is not str:
                        _fail("nontext-json-key")
                    visit(key, depth + 1)
                    add(len(":"))
                    visit(child, depth + 1)
                else:
                    visit(entry, depth + 1)
            active.remove(id(item))
        else:
            _fail("noncanonical-json-value")

    visit(value, 0)
    return size


def _canonical(value, ceiling=MAX_OUTPUT_BYTES):
    expected = _size(value, ceiling)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) != expected:
        _fail("canonical-byte-count-mismatch")
    return raw


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _pin(value, expected):
    if not _digest(expected) or _sha(value) != expected:
        _fail("external-pin-mismatch")


def _own(value, field):
    return _sha({key: item for key, item in value.items() if key != field})


def _version(page):
    return _sha({key: page[key] for key in
                 ("subject", "content_sha256", "source_sha256", "origin")})


def _policy(policy):
    _keys(policy, _POLICY_KEYS, "policy")
    _keys(policy["limits"], set(_LIMITS), "limits")
    for key, maximum in _LIMITS.items():
        if not _integer(policy["limits"][key], maximum, 1):
            _fail("policy-capacity")
    if type(policy["schema"]) is not str or type(policy["idle"]) is not str \
            or (policy["schema"], policy["idle"]) not in (
            ("sia-live-loop-policy-v1", "supported-capture-replay-gist-fresh-derived-only-v1"),
            ("sia-live-loop-policy-v2", "bound-native-episodes-replay-gist-fresh-derived-only-v2")):
        _fail("policy-contract")
    for key, literal in (
            ("scope", SCOPE),
            ("time_unit", "unix-seconds-integer"),
            ("workspace_release", "expiry-only-v1"),
            ("delivery_body", BODY_SCOPE)):
        if type(policy[key]) is not str or policy[key] != literal:
            _fail("policy-contract")
    if type(policy["recall_order"]) is not str or policy["recall_order"] not in {
            "activation-desc-stable-input-v1", "origin-slot-preserving-activation-v1"}:
        _fail("policy-contract")
    if policy["activation_events"] != ["encoding-admitted", "service-output-completed"]:
        _fail("activation-event-roster")
    gate = policy["novelty_admission"]
    _keys(gate, {"comparison", "threshold", "aggregation", "explicit_delivery"}, "novelty-admission")
    if gate["comparison"] != "strength-at-least-v1" \
            or gate["aggregation"] != "any-admitted-occurrence-per-version-v1" \
            or gate["explicit_delivery"] != "admit-without-novelty-filter-v1" \
            or not encoding._number(gate["threshold"], positive=False) \
            or not coretrieval._number(policy["delivery_activity"], positive=True):
        _fail("engineering-admission-policy")
    encoding._policy(policy["encoding"])
    activation._policy(policy["activation"])
    workspace._policy(policy["workspace"])
    coretrieval._admit_policy(policy["coretrieval"])


def _budget(policy, value):
    # Whole unknown input domains admit before policy validators, private
    # copies, pin calculations or any component's numerical work.
    _size(value, MAX_INPUT_BYTES)
    _policy(policy)
    _size(value, policy["limits"]["max_input_bytes"])
    # The fixed output envelope alone must fit before any component runs.
    _size({"schema": "sia-live-loop-transition-v1", "non_claims": list(NON_CLAIMS)},
          policy["limits"]["max_output_bytes"])


def _pages(intake, observed_at, policy):
    _keys(intake, _INTAKE_KEYS, "intake")
    if intake["schema"] != "sia-live-intake-v1" or intake["complete"] is not True \
            or not _token(intake["epoch_id"]) \
            or not _integer(intake["started_at"]) or intake["started_at"] > observed_at:
        _fail("intake-epoch-or-completeness")
    pages = intake["pages"]
    if type(pages) is not list or len(pages) > policy["limits"]["max_versions"]:
        _fail("version-capacity")
    versions = {}
    for page in pages:
        _keys(page, _PAGE_KEYS, "page-version")
        if not _token(page["subject"], activation.MAX_SUBJECT_BYTES, _SUBJECT) \
                or type(page["origin"]) is not str or page["origin"] not in _ORIGINS \
                or any(not _digest(page[key]) for key in
                       ("source_sha256", "content_sha256", "version_sha256")) \
                or type(page["content"]) is not str:
            _fail("page-version-identity")
        workspace._text_length(page["content"], policy["limits"]["max_content_bytes"])
        if page["version_sha256"] in versions:
            _fail("duplicate-version")
        versions[page["version_sha256"]] = page
    current, subjects = intake["current_versions"], set()
    if type(current) is not list or len(current) > policy["limits"]["max_versions"]:
        _fail("current-version-capacity")
    for version in current:
        if not _digest(version) or version not in versions:
            _fail("current-version-unknown")
        subject = versions[version]["subject"]
        if subject in subjects:
            _fail("current-subject-ambiguous")
        subjects.add(subject)
    symbols = encoding._roster(intake["symbols"], policy["encoding"]["max_symbols"], "symbols")
    contexts = encoding._roster(intake["contexts"], policy["encoding"]["max_contexts"], "contexts")
    observations = intake["observations"]
    if type(observations) is not list or len(observations) > policy["limits"]["max_observations"]:
        _fail("observation-capacity")
    previous, seen = intake["started_at"], set()
    for row in observations:
        _keys(row, _OBSERVATION_KEYS, "controller-observation")
        if not _token(row["id"]) or row["id"] in seen \
                or not _digest(row["version_sha256"]) or row["version_sha256"] not in versions:
            _fail("observation-identity")
        if not _integer(row["timestamp"]) or not previous <= row["timestamp"] <= observed_at:
            _fail("observation-controller-chronology")
        if type(row["symbol"]) is not str or row["symbol"] not in symbols \
                or type(row["context"]) is not str or row["context"] not in contexts:
            _fail("observation-roster")
        if row["native_timestamp"] is not None:
            if type(row["native_timestamp"]) is not str:
                _fail("native-timestamp-metadata")
            workspace._text_length(row["native_timestamp"], encoding.MAX_TOKEN_BYTES)
        previous = row["timestamp"]
        seen.add(row["id"])
    # All shapes and capacities precede all content or version hashing.
    for page in pages:
        if hashlib.sha256(page["content"].encode("utf-8")).hexdigest() != page["content_sha256"] \
                or _version(page) != page["version_sha256"]:
            _fail("page-content-or-origin-version-binding")
    return versions


def _rows(rows, versions, policy, *, current=None):
    if type(rows) is not list or len(rows) > policy["limits"]["max_rows"]:
        _fail("row-capacity")
    seen = set()
    for wrapper in rows:
        _keys(wrapper, {"row_ref", "version_sha256", "row"}, "row-reference")
        ref, version, row = wrapper["row_ref"], wrapper["version_sha256"], wrapper["row"]
        if not _token(ref, activation.MAX_SUBJECT_BYTES) or ref in seen \
                or not _digest(version) or version not in versions \
                or current is not None and version not in current:
            _fail("row-reference-version")
        if type(row) is not dict or type(row.get("slug")) is not str \
                or row["slug"] != versions[version]["subject"] \
                or type(row.get("chunk_text")) is not str \
                or row["chunk_text"] not in versions[version]["content"]:
            _fail("row-source-content-join")
        if "score" in row and (type(row["score"]) not in (int, float) or not math.isfinite(row["score"])):
            _fail("row-engine-score")
        if "origin" in row and row["origin"] != versions[version]["origin"]:
            _fail("row-origin-join")
        seen.add(ref)


def _delivery_roster(deliveries, intake, versions, policy, observed_at):
    _keys(deliveries, {"schema", "epoch_id", "complete", "records"}, "deliveries")
    if deliveries["schema"] != "sia-live-deliveries-v1" or deliveries["complete"] is not True \
            or deliveries["epoch_id"] != intake["epoch_id"]:
        _fail("delivery-epoch-or-completeness")
    records = deliveries["records"]
    if type(records) is not list or len(records) > policy["limits"]["max_deliveries"]:
        _fail("delivery-record-capacity")
    previous, identities = intake["started_at"], set()
    policy_sha = _sha(policy)
    for record in records:
        _keys(record, _DELIVERY_KEYS, "delivery-record")
        if record["schema"] != "sia-live-delivery-v1" or record["origin"] != "derived" \
                or record["epoch_id"] != intake["epoch_id"] or not _token(record["id"]) \
                or record["id"] in identities or record["policy_sha256"] != policy_sha \
                or record["boundary"] != DELIVERY_BOUNDARY or record["output_scope"] != BODY_SCOPE \
                or record["non_claims"] != list(NON_CLAIMS):
            _fail("delivery-record-contract")
        if not _integer(record["completed_at"]) or not _integer(record["ranked_at"]) \
                or not previous <= record["completed_at"] <= observed_at \
                or not intake["started_at"] <= record["ranked_at"] <= record["completed_at"]:
            _fail("delivery-controller-chronology")
        for key in ("rank_sha256", "state_sha256", "policy_sha256", "output_sha256", "record_sha256"):
            if not _digest(record[key]):
                _fail("delivery-digest")
        _rows(record["rows"], versions, policy)
        refs = [row["row_ref"] for row in record["rows"]]
        if record["emitted_row_refs"] != refs:
            _fail("delivery-exact-row-order")
        encoded = record["output_utf8_base64"]
        if type(encoded) is not str or not _integer(record["output_bytes"], policy["limits"]["max_delivery_bytes"]):
            _fail("delivery-body-capacity")
        # Check the actual representation, not just the caller's byte claim,
        # before the decoder can allocate a body. Canonical spelling is still
        # checked below; padding in any other position is rejected by decode.
        padding = 2 if encoded.endswith("==") else 1 if encoded.endswith("=") else 0
        if len(encoded) % 4 or len(encoded) // 4 * 3 - padding != record["output_bytes"]:
            _fail("delivery-body-capacity")
        raw = base64.b64decode(encoded, validate=True)
        raw.decode("utf-8", "strict")
        if base64.b64encode(raw).decode("ascii") != encoded or len(raw) != record["output_bytes"] \
                or hashlib.sha256(raw).hexdigest() != record["output_sha256"] \
                or _own(record, "record_sha256") != record["record_sha256"]:
            _fail("delivery-body-or-record-binding")
        identities.add(record["id"])
        previous = record["completed_at"]


def _inputs(intake, deliveries, policy, observed_at):
    if not _integer(observed_at):
        _fail("explicit-observation-clock")
    versions = _pages(intake, observed_at, policy)
    _delivery_roster(deliveries, intake, versions, policy, observed_at)
    trace = {"v": 1, "complete": True, "symbols": intake["symbols"], "contexts": intake["contexts"],
             "events": [{"id": row["id"], "timestamp": row["timestamp"], "symbol": row["symbol"],
                         "context": row["context"], "origin": versions[row["version_sha256"]]["origin"],
                         "source_sha256": versions[row["version_sha256"]]["source_sha256"]}
                        for row in intake["observations"]]}
    encoding._validate_inputs(trace, observed_at, policy["encoding"])
    return versions, trace


def _state(state, expected, policy, observed_at):
    _keys(state, _STATE_KEYS, "prior-state")
    if state["schema"] != "sia-live-loop-state-v1" \
            or state["non_claims"] != list(NON_CLAIMS) \
            or not _integer(state["observed_at"]) or state["observed_at"] > observed_at \
            or state["policy"] != policy or state["policy_sha256"] != _sha(policy) \
            or state["epoch_id"] != state["intake"]["epoch_id"] \
            or state["parent_state_sha256"] is not None and not _digest(state["parent_state_sha256"]):
        _fail("prior-state-contract")
    _pin(state, expected)
    versions, trace = _inputs(state["intake"], state["deliveries"], policy, state["observed_at"])
    encoded, admission, uses = _reconstruct(
        state["intake"], state["deliveries"], versions, trace, policy, state["observed_at"])
    if state["encoding"] != encoded or state["admission"] != admission or state["uses"] != uses:
        _fail("prior-state-typed-use-reconstruction")
    if state["traces"] != _traces(state["intake"], versions, uses):
        _fail("prior-state-exact-version-trace-join")
    # Reconstruct typed admission, but do not rerank activation at an old
    # clock. rank_recall evaluates its selected traces at the requested clock.
    activation._validate_set(state["traces"], state["observed_at"], policy["activation"])
    _held_receipt(state, policy)
    return versions


def _held_receipt(state, policy):
    maintained, held = state["workspace"], state["held_selection_receipt"]
    prior = maintained["state"]
    workspace._prior(prior, maintained["state_sha256"], state["observed_at"], policy["workspace"])
    _pin(prior, maintained["state_sha256"])
    if prior["observed_at"] != state["observed_at"]:
        _fail("held-workspace-clock-binding")
    episode = prior["episode"]
    if episode is None:
        if held is not None or maintained["slots"]:
            _fail("idle-workspace-has-held-receipt")
        return
    _keys(held, {"observed_at", "payload_sha256", "frame", "frame_sha256", "admission", "activation"},
          "held-selection-receipt")
    workspace._frame(held["frame"], held["observed_at"], policy["workspace"], policy["activation"])
    payload = _canonical(episode)
    if _own(episode, "generation") != episode["generation"] \
            or hashlib.sha256(payload).hexdigest() != maintained["payload_sha256"] \
            or payload.decode("utf-8") != maintained["payload_json"] \
            or held["payload_sha256"] != maintained["payload_sha256"] \
            or held["observed_at"] != episode["as_of"] \
            or held["frame_sha256"] != episode["frame_sha256"] \
            or _sha(held["frame"]) != held["frame_sha256"] \
            or held["frame"]["generation_sha256"] != episode["source_generation_sha256"] \
            or maintained["slots"] != [item["subject"] for item in episode["selected"]]:
        _fail("held-selection-receipt-binding")
    candidates = {item["subject"]: item for item in held["frame"]["candidates"]}
    for item in episode["selected"]:
        candidate = candidates.get(item["subject"])
        if candidate is None or any(candidate[key] != item[key] for key in workspace._ITEM_KEYS) \
                or not any(all(page[key] == item[key] for key in workspace._ITEM_KEYS)
                           for page in state["intake"]["pages"]):
            _fail("held-selection-source-version-join")


def _continuation(previous, intake, deliveries):
    old = previous["intake"]
    for field in ("schema", "epoch_id", "started_at", "complete", "symbols", "contexts"):
        if intake[field] != old[field]:
            _fail("epoch-contract-changed")
    for field in ("pages", "observations"):
        if intake[field][:len(old[field])] != old[field]:
            _fail("epoch-history-not-append-only")
    old_records = previous["deliveries"]["records"]
    if deliveries["records"][:len(old_records)] != old_records:
        _fail("delivery-history-not-append-only")


def _use(kind, record_id, timestamp, version, page):
    identity = {"kind": kind, "record_id": record_id, "version_sha256": version}
    return {"id": _sha(identity), **identity, "timestamp": timestamp, "origin": "derived",
            "subject": page["subject"], "subject_origin": page["origin"],
            "source_sha256": page["source_sha256"], "content_sha256": page["content_sha256"]}


def _reconstruct(intake, deliveries, versions, trace, policy, observed_at):
    encoded = encoding.replay_encoding(trace, observed_at=observed_at, policy=policy["encoding"])
    admission, uses = [], []
    for row, score in zip(intake["observations"], encoded["events"], strict=True):
        eligible = score["encoding_strength"] >= policy["novelty_admission"]["threshold"]
        version = row["version_sha256"]
        admission.append({"kind": "perception", "record_id": row["id"], "version_sha256": version,
                          "eligible": eligible, "reason": "encoding-strength-admitted" if eligible
                          else "encoding-strength-below-threshold"})
        if eligible:
            uses.append(_use("encoding-admitted", row["id"], row["timestamp"], version, versions[version]))
    for record in deliveries["records"]:
        seen = set()
        for row in record["rows"]:
            version = row["version_sha256"]
            if version in seen:
                continue
            seen.add(version)
            admission.append({"kind": "delivery", "record_id": record["id"], "version_sha256": version,
                              "eligible": True, "reason": "explicit-delivery-admitted"})
            uses.append(_use("service-output-completed", record["id"], record["completed_at"],
                             version, versions[version]))
    # Stable order within equal timestamps retains each original roster's
    # order. No native event clock, strength multiplier or aggregate tail.
    uses.sort(key=lambda row: row["timestamp"])
    return encoded, admission, uses


def _traces(intake, versions, uses):
    return [{"v": 1, "subject": versions[version]["subject"], "complete": True,
             "uses": [{"id": row["id"], "timestamp": row["timestamp"]}
                      for row in uses if row["version_sha256"] == version]}
            for version in intake["current_versions"]]


def _coretrace(intake, deliveries, policy):
    rows = []
    for record in deliveries["records"]:
        versions = list(dict.fromkeys(row["version_sha256"] for row in record["rows"]))
        rows.append({"id": record["id"], "timestamp": record["completed_at"], "complete": True,
                     "source_sha256": record["record_sha256"],
                     "activities": [{"id": "versions/" + version, "activation": policy["delivery_activity"]}
                                    for version in versions]})
    return {"v": 1, "complete": True,
            "nodes": [{"id": "versions/" + page["version_sha256"], "origin": page["origin"]}
                      for page in intake["pages"]], "deliveries": rows}


def _gist_inputs(value, intake, policy, idle, *, expected_intake_sha256=None,
                 expected_policy_sha256=None, observed_at=None):
    if type(idle) is not bool:
        _fail("idle-contract")
    if not idle:
        if value is not None:
            _fail("gist-outside-idle")
        return
    if policy["schema"] == "sia-live-loop-policy-v2":
        if type(value) is dict and "idle_without_native" in value:
            import sialiveidle
            return sialiveidle.reservation(
                intake=intake, expected_intake_sha256=expected_intake_sha256,
                policy=policy, expected_policy_sha256=expected_policy_sha256,
                observed_at=observed_at, idle_input=value)
        _keys(value, {"episode_bindings", "expected_episode_bindings_sha256",
                      "gist_inputs", "expected_gist_inputs_sha256"}, "bound-idle-gist-inputs")
        bindings = value["episode_bindings"]
        if type(bindings) is not dict \
                or not _integer(observed_at) \
                or type(bindings.get("observed_at")) is not int \
                or bindings["observed_at"] != observed_at \
                or bindings.get("epoch_id") != intake["epoch_id"] \
                or bindings.get("intake_sha256") != expected_intake_sha256 \
                or bindings.get("live_policy_sha256") != expected_policy_sha256 \
                or _canonical(bindings.get("live_policy")) != _canonical(policy):
            _fail("bound-idle-outer-pulse-binding")
        # Lazy, one-directional integration. This is admission/reservation,
        # not replay; the public binder is invoked once by the idle stage.
        import sialivegist
        _original, _dispositions, _ceiling, reserved = sialivegist._prepare_request_with_reservation(
            {"intake": intake, "expected_intake_sha256": expected_intake_sha256, **value})
        return reserved
    _keys(value, {"capture", "expected_capture_sha256", "replay", "expected_replay_sha256",
                  "policy", "expected_policy_sha256"}, "idle-gist-inputs")
    if not _digest(value["expected_capture_sha256"]) \
            or not any(page["source_sha256"] == value["expected_capture_sha256"] for page in intake["pages"]):
        _fail("gist-capture-outside-epoch-source")
    import siagist
    siagist._preflight(value["capture"], value["expected_capture_sha256"], value["replay"],
                      value["expected_replay_sha256"], value["policy"], value["expected_policy_sha256"])
    siagist._admit_pins(value["capture"], value["expected_capture_sha256"], value["replay"],
                       value["expected_replay_sha256"], value["policy"], value["expected_policy_sha256"])
    source_pages = {page["slug"]: page for page in value["capture"]["pages"]}
    for page in intake["pages"]:
        if page["source_sha256"] == value["expected_capture_sha256"]:
            source = source_pages.get(page["subject"])
            if source is None or source["sha256"] != page["content_sha256"] \
                    or source["text"] != page["content"] or source["origin"] != page["origin"]:
                _fail("gist-source-version-join")


def _idle(value, intake, idle, *, policy=None, expected_intake_sha256=None,
          observed_at=None):
    if not idle:
        return {"requested": False, "gist": None}, []
    if policy is not None and policy["schema"] == "sia-live-loop-policy-v2":
        if type(value) is dict and "idle_without_native" in value:
            import sialiveidle
            receipt = sialiveidle.bind(
                intake=intake, expected_intake_sha256=expected_intake_sha256,
                policy=policy, expected_policy_sha256=_sha(policy),
                observed_at=observed_at, idle_input=value)
            return {"requested": True, "binding": receipt}, []
        import sialivegist
        binding = sialivegist.bind_replay_gist(
            intake=intake, expected_intake_sha256=expected_intake_sha256, **value)
        artifact = binding["gist"]
        selected = set(binding["proposed_candidate_ids"])
        idle_state = {"requested": True, "binding": binding}
    else:
        import siagist
        artifact = siagist.replay_gist(**value)
        selected = None
        idle_state = {"requested": True, "gist": artifact}
    body = json.loads(artifact["artifact_json"])
    if selected is None:
        selected = {identity for row in body["readout"] for identity in row["selected"]}
    old = {page["subject"] for page in intake["pages"]}
    pages = []
    for candidate in body["candidates"]:
        if candidate["id"] not in selected:
            continue
        subject = "gists/live/" + _sha({"gist": artifact["artifact_sha256"], "candidate": candidate["id"]})
        if subject in old:
            _fail("gist-addition-already-present")
        page = {"subject": subject, "content": candidate["text"], "origin": "derived",
                "source_sha256": artifact["artifact_sha256"],
                "content_sha256": hashlib.sha256(candidate["text"].encode("utf-8")).hexdigest()}
        pages.append({**page, "version_sha256": _version(page)})
    return idle_state, pages


def _capture(state, state_sha):
    body = {"schema": "sia-live-history-capture-v1", "epoch_id": state["epoch_id"], "complete": True,
            "scope": SCOPE, "intake": state["intake"], "deliveries": state["deliveries"],
            "policy": state["policy"], "policy_sha256": state["policy_sha256"],
            "observed_at": state["observed_at"], "uses": state["uses"],
            "state_sha256": state_sha, "non_claims": list(NON_CLAIMS)}
    return {**body, "capture_sha256": _sha(body)}


def _upstream(exc):
    if isinstance(exc, LiveLoopRefusal):
        return exc
    return LiveLoopRefusal("component-input-or-representation-refusal", getattr(exc, "non_claims", ()))


def _bound_pulse_output_reservation(*, intake, deliveries, policy, expected_policy_sha256,
                                    expected_previous_state_sha256, observed_at, idle,
                                    binding_reservation):
    """Reserve known v2 enclosing documents before any numerical component.

    Count each actual retained occurrence, including aliasing. The nested
    binding uses its existing complete reservation, not a copied gist formula.
    This is deliberately NOT a bound for the later encoding, activation,
    workspace, co-retrieval or proposed-page traces. Their component limits
    and the complete post-computation output checks remain controlling.
    """
    placeholder = "0" * 64
    shared = {"epoch_id": intake["epoch_id"], "observed_at": observed_at,
              "intake": intake, "deliveries": deliveries, "policy": policy,
              "policy_sha256": expected_policy_sha256, "non_claims": list(NON_CLAIMS)}
    state = {**shared, "schema": "sia-live-loop-state-v1",
             "parent_state_sha256": expected_previous_state_sha256,
             "idle": {"requested": True, "binding": None} if idle else
                     {"requested": False, "gist": None}}
    captured = {**shared, "schema": "sia-live-history-capture-v1", "complete": True,
                "scope": SCOPE, "state_sha256": placeholder, "capture_sha256": placeholder}
    known = {"schema": "sia-live-loop-transition-v1", "status": "planned",
             "state": state, "state_sha256": placeholder, "history_capture": captured,
             "history_capture_sha256": placeholder, "gist_pages": [],
             "non_claims": list(NON_CLAIMS), "transition_sha256": placeholder}
    ceiling = policy["limits"]["max_output_bytes"]
    try:
        amount = _size(known, ceiling)
    except LiveLoopRefusal as exc:
        if exc.reason != "complete-json-byte-capacity":
            raise
        _fail("bound-pulse-output-reservation-capacity")
    if idle:
        # Replace the counted null at exactly state.idle.binding. The bound
        # already includes that binding's full intake and variable nonclaims.
        amount += binding_reservation - _size(None, ceiling)
    if amount > ceiling:
        _fail("bound-pulse-output-reservation-capacity")


def prepare_pulse(*, intake, expected_intake_sha256, deliveries, expected_deliveries_sha256,
                  previous_state, expected_previous_state_sha256, policy, expected_policy_sha256,
                  observed_at, idle, gist_inputs):
    """Compose one inert transition; all required stages succeed or refuse."""
    try:
        args = locals().copy()
        _budget(policy, args)
        bound_v2 = policy["schema"] == "sia-live-loop-policy-v2"
        original_args = _canonical(args) if bound_v2 else None
        versions, trace = _inputs(intake, deliveries, policy, observed_at)
        _pin(intake, expected_intake_sha256)
        _pin(deliveries, expected_deliveries_sha256)
        _pin(policy, expected_policy_sha256)
        if bound_v2:
            binding_reservation = _gist_inputs(
                gist_inputs, intake, policy, idle, expected_intake_sha256=expected_intake_sha256,
                expected_policy_sha256=expected_policy_sha256, observed_at=observed_at)
            _bound_pulse_output_reservation(
                intake=intake, deliveries=deliveries, policy=policy,
                expected_policy_sha256=expected_policy_sha256,
                expected_previous_state_sha256=expected_previous_state_sha256,
                observed_at=observed_at, idle=idle, binding_reservation=binding_reservation)
            if _canonical(args) != original_args:
                _fail("bound-pulse-input-changed-before-learning")
        if previous_state is None:
            if expected_previous_state_sha256 is not None:
                _fail("unexpected-initial-state-pin")
        else:
            _state(previous_state, expected_previous_state_sha256, policy, observed_at)
            _continuation(previous_state, intake, deliveries)
        if not bound_v2:
            _gist_inputs(gist_inputs, intake, policy, idle,
                         expected_intake_sha256=expected_intake_sha256,
                         expected_policy_sha256=expected_policy_sha256, observed_at=observed_at)
        if bound_v2 and _canonical(args) != original_args:
            _fail("bound-pulse-input-changed")
        detached = copy.deepcopy(args)
        if bound_v2 and (_canonical(args) != original_args or _canonical(detached) != original_args):
            _fail("bound-pulse-input-changed-during-copy")
        intake, deliveries, policy = detached["intake"], detached["deliveries"], detached["policy"]
        previous_state, gist_inputs = detached["previous_state"], detached["gist_inputs"]
        versions, trace = _inputs(intake, deliveries, policy, observed_at)
        _pin(intake, expected_intake_sha256)
        _pin(deliveries, expected_deliveries_sha256)
        _pin(policy, expected_policy_sha256)
        if bound_v2:
            binding_reservation = _gist_inputs(
                gist_inputs, intake, policy, idle, expected_intake_sha256=expected_intake_sha256,
                expected_policy_sha256=expected_policy_sha256, observed_at=observed_at)
            _bound_pulse_output_reservation(
                intake=intake, deliveries=deliveries, policy=policy,
                expected_policy_sha256=expected_policy_sha256,
                expected_previous_state_sha256=expected_previous_state_sha256,
                observed_at=observed_at, idle=idle, binding_reservation=binding_reservation)
            if _canonical(args) != original_args or _canonical(detached) != original_args:
                _fail("bound-pulse-input-changed-before-learning")
        encoded, admission, uses = _reconstruct(intake, deliveries, versions, trace, policy, observed_at)
        traces = _traces(intake, versions, uses)
        ranked = activation.rank_traces(traces, observed_at=observed_at, policy=policy["activation"])
        eligible = {row["version_sha256"] for row in admission if row["eligible"]}
        by_subject = {trace["subject"]: trace for trace in traces}
        frame = {"v": 1, "complete": True,
                 "generation_sha256": _sha({"intake": expected_intake_sha256,
                                            "deliveries": expected_deliveries_sha256}),
                 "candidates": [{**{key: versions[version][key] for key in
                                     ("subject", "content", "origin", "source_sha256")},
                                 "trace": by_subject[versions[version]["subject"]]}
                                for version in intake["current_versions"] if version in eligible]}
        prior_ws = None if previous_state is None else previous_state["workspace"]["state"]
        prior_pin = None if previous_state is None else previous_state["workspace"]["state_sha256"]
        maintained = workspace.advance_workspace(
            frame, observed_at=observed_at, previous_state=prior_ws, expected_previous_state_sha256=prior_pin,
            policy=policy["workspace"], activation_policy=policy["activation"],
            consumers=policy["workspace"]["consumer_roster"], release=False)
        held = None
        if maintained["transition"] == "sustained":
            held = previous_state["held_selection_receipt"]
            if type(held) is not dict or held.get("payload_sha256") != maintained["payload_sha256"]:
                _fail("held-selection-receipt-binding")
        elif maintained["slots"]:
            held = {"observed_at": observed_at, "payload_sha256": maintained["payload_sha256"],
                    "frame": frame, "frame_sha256": maintained["state"]["frame_sha256"],
                    "admission": admission, "activation": ranked}
        core_trace = _coretrace(intake, deliveries, policy)
        learned = coretrieval.learn_coretrieval(core_trace, observed_at=observed_at, policy=policy["coretrieval"])
        idle_state, gist_pages = _idle(gist_inputs, intake, idle, policy=policy,
                                      expected_intake_sha256=expected_intake_sha256,
                                      observed_at=observed_at)
        state = {"schema": "sia-live-loop-state-v1", "epoch_id": intake["epoch_id"],
                 "observed_at": observed_at, "parent_state_sha256": expected_previous_state_sha256,
                 "intake": intake, "deliveries": deliveries, "policy": policy, "policy_sha256": expected_policy_sha256,
                 "uses": uses, "traces": traces, "encoding": encoded, "admission": admission,
                 "activation": ranked, "workspace": maintained, "held_selection_receipt": held,
                 "coretrieval_trace": core_trace, "coretrieval": learned, "idle": idle_state,
                 "non_claims": list(NON_CLAIMS)}
        _size(state, policy["limits"]["max_output_bytes"])
        original_state = _canonical(state) if bound_v2 else None
        state_sha = _sha(state)
        captured = _capture(state, state_sha)
        if bound_v2 and _canonical(state) != original_state:
            _fail("bound-pulse-state-changed-during-digest")
        result = {"schema": "sia-live-loop-transition-v1", "status": "planned", "state": state,
                  "state_sha256": state_sha, "history_capture": captured,
                  "history_capture_sha256": captured["capture_sha256"], "gist_pages": gist_pages,
                  "non_claims": list(NON_CLAIMS)}
        _size(result, policy["limits"]["max_output_bytes"])
        original_result = _canonical(result) if bound_v2 else None
        result["transition_sha256"] = _sha(result)
        if bound_v2 and _canonical({key: value for key, value in result.items()
                                    if key != "transition_sha256"}) != original_result:
            _fail("bound-pulse-result-changed-during-digest")
        _size(result, policy["limits"]["max_output_bytes"])
        if bound_v2:
            final_bytes = _canonical(result)
            final = copy.deepcopy(result)
            if _canonical(result) != final_bytes or _canonical(final) != final_bytes \
                    or _canonical(args) != original_args or _canonical(detached) != original_args:
                _fail("bound-pulse-result-or-input-changed-during-copy")
            return final
        return result
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise _upstream(exc) from exc


def rank_recall(*, rows, expected_rows_sha256, state, expected_state_sha256,
                policy, expected_policy_sha256, observed_at):
    """Rank current version-bound references at an explicit fresh clock."""
    try:
        _budget(policy, locals().copy())
        if not _integer(observed_at):
            _fail("recall-observation-clock")
        _pin(policy, expected_policy_sha256)
        versions = _state(state, expected_state_sha256, policy, observed_at)
        _pin(rows, expected_rows_sha256)
        _rows(rows, versions, policy, current=state["intake"]["current_versions"])
        detached = copy.deepcopy({"rows": rows, "state": state, "policy": policy})
        rows, state, policy = detached["rows"], detached["state"], detached["policy"]
        unique = list(dict.fromkeys(row["version_sha256"] for row in rows))
        lookup = {trace["subject"]: trace for trace in state["traces"]}
        traces = [lookup[versions[version]["subject"]] for version in unique]
        ranked = activation.rank_traces(traces, observed_at=observed_at, policy=policy["activation"])
        if policy["recall_order"] == "origin-slot-preserving-activation-v1":
            # The supplied base order is the caller's admitted hybrid/PPR
            # order, not independently recomputed origin weighting here.
            # Preserve every origin slot, including display-prefix slots.
            # Sort rows, not grouped versions: equal/unavailable scores must
            # preserve separated references to the same immutable version.
            scores = {item["subject"]: item["score"] for item in ranked["activations"]}

            def origin(row):
                return versions[row["version_sha256"]]["origin"]

            def key(row):
                score = scores[versions[row["version_sha256"]]["subject"]]
                return score is None, -score if score is not None else 0

            slots = {label: iter(sorted((row for row in rows if origin(row) == label), key=key))
                     for label in _ORIGINS}
            order = [next(slots[origin(row)])["row_ref"] for row in rows]
        else:
            order = [row["row_ref"] for subject in ranked["order"] for row in rows if row["row"]["slug"] == subject]
        result = {"schema": "sia-live-recall-plan-v1", "status": "computed-unverified",
                  "epoch_id": state["epoch_id"], "observed_at": observed_at,
                  "state_sha256": expected_state_sha256, "policy": policy, "policy_sha256": expected_policy_sha256,
                  "rows": rows, "rows_sha256": expected_rows_sha256,
                  "versions": [copy.deepcopy(versions[version]) for version in unique],
                  "traces": traces, "activation": ranked, "order": order, "non_claims": list(NON_CLAIMS)}
        _size(result, policy["limits"]["max_output_bytes"])
        result["rank_sha256"] = _sha(result)
        _size(result, policy["limits"]["max_output_bytes"])
        return result
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise _upstream(exc) from exc


def complete_delivery(*, ranked, expected_ranked_sha256, emitted_row_refs, output_utf8,
                      request_id, completed_at):
    """Admit supplied output bytes, never assert that this function sent them."""
    try:
        _size(ranked, MAX_INPUT_BYTES)
        _keys(ranked, _RANK_KEYS, "recall-plan")
        policy = ranked["policy"]
        _budget(policy, {"ranked": ranked, "refs": emitted_row_refs,
                         "request_id": request_id, "completed_at": completed_at})
        if type(output_utf8) is not bytes or len(output_utf8) > policy["limits"]["max_delivery_bytes"]:
            _fail("output-byte-witness-capacity")
        output_utf8.decode("utf-8", "strict")
        if ranked["schema"] != "sia-live-recall-plan-v1" or ranked["status"] != "computed-unverified" \
                or ranked["non_claims"] != list(NON_CLAIMS) \
                or not _digest(expected_ranked_sha256) or ranked["rank_sha256"] != expected_ranked_sha256 \
                or _own(ranked, "rank_sha256") != expected_ranked_sha256:
            _fail("rank-plan-binding")
        _pin(policy, ranked["policy_sha256"])
        _pin(ranked["rows"], ranked["rows_sha256"])
        if not _token(request_id) or not _integer(completed_at) \
                or not _integer(ranked["observed_at"]) or completed_at < ranked["observed_at"]:
            _fail("completed-output-clock-or-identity")
        versions = {page["version_sha256"]: page for page in ranked["versions"]}
        _rows(ranked["rows"], versions, policy)
        references = [row["row_ref"] for row in ranked["rows"]]
        if type(ranked["order"]) is not list or len(ranked["order"]) != len(references) \
                or set(ranked["order"]) != set(references):
            _fail("rank-order-not-permutation")
        if type(emitted_row_refs) is not list or len(emitted_row_refs) > len(references) \
                or any(not _token(ref, activation.MAX_SUBJECT_BYTES) for ref in emitted_row_refs) \
                or len(set(emitted_row_refs)) != len(emitted_row_refs) \
                or any(ref not in references for ref in emitted_row_refs) \
                or [ref for ref in ranked["order"] if ref in set(emitted_row_refs)] != emitted_row_refs:
            _fail("emitted-row-roster")
        by_ref = {row["row_ref"]: row for row in ranked["rows"]}
        result = {"schema": "sia-live-delivery-v1", "origin": "derived", "id": request_id,
                  "epoch_id": ranked["epoch_id"], "completed_at": completed_at,
                  "ranked_at": ranked["observed_at"], "rank_sha256": expected_ranked_sha256,
                  "state_sha256": ranked["state_sha256"], "policy_sha256": ranked["policy_sha256"],
                  "emitted_row_refs": list(emitted_row_refs),
                  "rows": copy.deepcopy([by_ref[ref] for ref in emitted_row_refs]),
                  "output_scope": BODY_SCOPE, "output_utf8_base64": base64.b64encode(output_utf8).decode("ascii"),
                  "output_bytes": len(output_utf8), "output_sha256": hashlib.sha256(output_utf8).hexdigest(),
                  "boundary": DELIVERY_BOUNDARY, "non_claims": list(NON_CLAIMS)}
        _size(result, policy["limits"]["max_output_bytes"])
        result["record_sha256"] = _sha(result)
        _size(result, policy["limits"]["max_output_bytes"])
        return result
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, binascii.Error) as exc:
        raise _upstream(exc) from exc


def project_history_traces(*, capture, expected_capture_sha256,
                           candidates, expected_candidates_sha256):
    """Target-blind exact-version bridge for captured benchmark candidates.

    Candidates contain only row_ref, subject, origin, source_sha256 and the
    FULL PAGE content_sha256, never a chunk hash or an answer key. Their
    linkage to a descriptor-bound engine snapshot remains the caller's
    obligation. Historical retained versions are eligible, not only current
    versions; trace subjects are version digests to prevent cross-version
    aggregation. Duplicate chunks may reference the same version but are
    not additional uses. This operation neither ranks nor grades results.
    """
    try:
        _size([capture, candidates], MAX_INPUT_BYTES)
        _keys(capture, _CAPTURE_KEYS, "history-capture")
        _budget(capture["policy"], [capture, candidates])
        if type(candidates) is not list or len(candidates) > capture["policy"]["limits"]["max_rows"]:
            _fail("history-candidate-capacity")
        seen = set()
        for candidate in candidates:
            _keys(candidate, {"row_ref", "subject", "origin", "source_sha256", "content_sha256"},
                  "history-candidate")
            if not _token(candidate["row_ref"], activation.MAX_SUBJECT_BYTES) \
                    or candidate["row_ref"] in seen \
                    or not _token(candidate["subject"], activation.MAX_SUBJECT_BYTES, _SUBJECT) \
                    or type(candidate["origin"]) is not str or candidate["origin"] not in _ORIGINS \
                    or not _digest(candidate["source_sha256"]) or not _digest(candidate["content_sha256"]):
                _fail("history-candidate-identity")
            seen.add(candidate["row_ref"])
        _pin(candidates, expected_candidates_sha256)
        admitted = admit_history_capture(capture, expected_capture_sha256=expected_capture_sha256)
        versions = {page["version_sha256"] for page in admitted["intake"]["pages"]}
        by_version = {}
        for use in admitted["uses"]:
            by_version.setdefault(use["version_sha256"], []).append(use)
        rows = []
        for candidate in candidates:
            version = _version(candidate)
            available = version in versions
            uses = by_version.get(version, []) if available else []
            rows.append({"candidate": candidate, "version_sha256": version,
                         "availability": "complete-within-controller-epoch" if available
                         else "exact-version-not-captured", "uses": uses,
                         "trace": {"v": 1, "subject": version, "complete": True,
                                   "uses": [{"id": use["id"], "timestamp": use["timestamp"]}
                                            for use in uses]} if available else None})
        result = {"schema": "sia-live-history-projection-v1", "status": "computed-unverified",
                  "epoch_id": admitted["epoch_id"], "scope": admitted["scope"],
                  "started_at": admitted["intake"]["started_at"], "observed_at": admitted["observed_at"],
                  "capture_sha256": expected_capture_sha256,
                  "candidates_sha256": expected_candidates_sha256, "rows": rows,
                  "source_non_claims": admitted["non_claims"],
                  "non_claims": [
                      "Candidate full-page identities are caller premises, not proof of linkage to a raw-vector runner or index snapshot.",
                      "Exact-version traces cover the declared controller epoch only; unmatched versions are unavailable, not empty complete histories.",
                      "Typed encoding and service-output times are not native event clocks or proof of human use; repeated candidate rows add no uses.",
                      "This target-blind projection does not establish ranking quality, held-out independence, JACKAL assurance, or a cognitive win.",
                  ]}
        # Include the final digest field in the reservation before copying or
        # serializing potentially repeated per-row histories.
        _size({**result, "projection_sha256": "0" * 64},
              admitted["policy"]["limits"]["max_output_bytes"])
        result["projection_sha256"] = _sha(result)
        return copy.deepcopy(result)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise _upstream(exc) from exc


def admit_history_capture(capture, *, expected_capture_sha256):
    """Reconstruct typed uses; state linkage does not replay workspace history."""
    try:
        _size(capture, MAX_INPUT_BYTES)
        _keys(capture, _CAPTURE_KEYS, "history-capture")
        policy = capture["policy"]
        _budget(policy, capture)
        if capture["schema"] != "sia-live-history-capture-v1" or capture["complete"] is not True \
                or capture["scope"] != SCOPE or capture["non_claims"] != list(NON_CLAIMS) \
                or not _digest(capture["state_sha256"]) or not _digest(expected_capture_sha256) \
                or capture["capture_sha256"] != expected_capture_sha256 \
                or _own(capture, "capture_sha256") != expected_capture_sha256 \
                or capture["epoch_id"] != capture["intake"]["epoch_id"]:
            _fail("history-contract-or-binding")
        _pin(policy, capture["policy_sha256"])
        versions, trace = _inputs(capture["intake"], capture["deliveries"], policy, capture["observed_at"])
        _encoded, _admission, uses = _reconstruct(capture["intake"], capture["deliveries"], versions,
                                                trace, policy, capture["observed_at"])
        if uses != capture["uses"]:
            _fail("history-typed-use-reconstruction")
        return copy.deepcopy(capture)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise _upstream(exc) from exc
