"""Pure consistency admission of supplied GET-render projection premises.

This is not an observation or authority front door.  It cannot establish that
an engine executed, that a source version is current, or that output was sent.
It does not parse Markdown or reproduce the engine's logical content hash.
All documents are plain, bounded values; raw UTF-8 pins and native document
pins remain distinct.  The mandatory callback is a caller-supplied premise.
"""

import copy
import hashlib
import json
import math
import re

import siaactivation as _activation
import sialiveloop as _live
import siasourcebatch as _source


GET_RENDER_PROJECTION_NON_CLAIMS = (
    "This receipt compares supplied retained-source bytes and supplied GET stdout with one current local engine page projection; supplied source/version pins and origin are not independently authenticated here.",
    "The logical contentHash comparison keeps gbrain's existing exclusions; the separate complete-display comparison does not discard timestamp or gate-derived frontmatter.",
    "Serialized GET Markdown is a canonical rendering, not the original source-file byte representation; the original content, source, version and origin bindings remain unchanged.",
    "The no-write flags describe this probe operation, not request scratch, the preceding ordinary GET, database connection bookkeeping, or every process and storage-layer effect.",
    "A matching projection is not output delivery, human reading, successful use, controller readiness, acknowledgment, historical completeness, or a new observation clock.",
    "This receipt grants no JACKAL status, biological cognition claim, cognitive-mechanism warrant, or held-out retrieval win.",
)
NON_CLAIMS = (
    "This result checks consistency of supplied source-version, GET stdout and projection-receipt premises; it does not prove actual engine execution, executable identity, installation or transport provenance.",
    "The caller's input_current callback is a supplied check, not independent source authority, an entered lease, a current source generation, authenticated origin or uninterrupted immutability.",
    "Raw source bytes and their original source, content, version and origin bindings remain unchanged; logical hashes, complete-display matches and source-explicit or current-index-preserved type basis remain producer premises, not a Python Markdown reparse or semantic proof.",
    "The retained no-write flags cover the supplied projection probe only, not request scratch, preceding ordinary GET retrieval bookkeeping, connection bookkeeping or every process and storage effect.",
    "Consistency is not output delivery, human reading, successful use, controller readiness, acknowledgment, historical completeness, freshness or a new observation clock.",
    "This result grants no JACKAL status, biological cognition claim, cognitive-mechanism warrant or held-out retrieval win; every original projection nonclaim remains controlling.",
)

_VERSION_KEYS = frozenset({
    "subject", "content", "origin", "source_sha256", "content_sha256",
    "version_sha256",
})
_REFERENCE_KEYS = _VERSION_KEYS - {"content"}
_RECEIPT_KEYS = frozenset({
    "schema", "status", "source_id", "source_reference",
    "get_stdout_sha256", "page_state", "parse_error_codes", "type_basis",
    "expected_projection_sha256", "current_projection_sha256",
    "current_content_hash", "current_content_hash_match", "projection_match",
    "display_fields_match", "current_get_stdout_sha256", "get_stdout_match",
    "mismatch_reasons", "retrieval_bookkeeping_updated",
    "operation_writes_performed", "non_claims",
})
_CAPACITY_KEYS = (
    "MAX_STATE_JSON_BYTES", "MAX_CONFIG_BYTES", "MAX_EXTERNAL_OUTPUT_BYTES",
)
_ORIGINS = frozenset({"evidence", "derived", "model", "legacy-unlabeled"})
_TYPE_BASES = frozenset({
    "source-explicit", "current-index-preserved",
    "source-inferred-without-current-page", "parse-refused",
})
_MATCH_TYPE_BASES = frozenset({"source-explicit", "current-index-preserved"})
_MISMATCH_REASONS = (
    "page-missing-or-deleted", "source-parse-refused",
    "stored-content-hash-mismatch", "logical-source-projection-mismatch",
    "complete-display-fields-mismatch", "get-stdout-mismatch",
)
_MATCH_FLAGS = (
    "current_content_hash_match", "projection_match", "display_fields_match",
    "get_stdout_match",
)
_NO_WRITE_FLAGS = ("retrieval_bookkeeping_updated", "operation_writes_performed")
_LOGICAL_HASHES = (
    "expected_projection_sha256", "current_projection_sha256",
    "current_content_hash",
)
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SUBJECT = re.compile(r"[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*\Z")


class GetRenderAdmissionRefusal(ValueError):
    """Closed refusal; upstream non-match remains a refusal, never a match."""

    def __init__(self, reason, *, upstream_status=None, mismatch_reasons=()):
        self.reason = reason
        self.non_claims = list(NON_CLAIMS)
        self.upstream_status = upstream_status
        self.upstream_mismatch_reasons = list(mismatch_reasons)
        self.upstream_non_claims = list(GET_RENDER_PROJECTION_NON_CLAIMS)
        super().__init__("GET render consistency refused: " + reason)


def _fail(reason, *, upstream_status=None, mismatch_reasons=()):
    raise GetRenderAdmissionRefusal(
        reason, upstream_status=upstream_status, mismatch_reasons=mismatch_reasons)


def _keys(value, keys, reason):
    if type(value) is not dict or len(value) != len(keys) \
            or any(type(key) is not str for key in value) or set(value) != keys:
        _fail(reason)


def _hex(value, reason):
    if type(value) is not str or len(value) != 64 or _HEX.fullmatch(value) is None:
        _fail(reason)


class _Basis:
    def __init__(self, owner):
        if type(owner) is not dict:
            _fail("owner-shape")
        self.owner = owner
        self.original = {}
        self.limits = {}
        for key in _CAPACITY_KEYS:
            value = owner.get(key)
            if type(value) is not int or value <= 0:
                _fail("owner-capacity")
            self.original[key] = value
            self.limits[key] = min(value, _live.MAX_INPUT_BYTES)
        self.native_owner = {
            "json": json, "hashlib": hashlib, "math": math,
            "MAX_STATE_JSON_BYTES": self.limits["MAX_STATE_JSON_BYTES"],
        }

    def current(self):
        for key, expected in self.original.items():
            value = self.owner.get(key)
            if type(value) is not int or value != expected:
                _fail("owner-capacity-changed")

    def size(self, value, ceiling=None):
        if ceiling is None:
            ceiling = self.limits["MAX_STATE_JSON_BYTES"]
        try:
            _source._json_size(self.native_owner, value, ceiling, ascii_only=True)
        except (_source.SourceBatchRefusal, RecursionError) as exc:
            raise GetRenderAdmissionRefusal("native-byte-capacity-or-shape") from exc

    def wire(self, value):
        try:
            return _source.native_bytes(self.native_owner, value)
        except (_source.SourceBatchRefusal, RecursionError) as exc:
            raise GetRenderAdmissionRefusal("native-byte-capacity-or-shape") from exc

    def sha(self, value):
        return hashlib.sha256(self.wire(value)).hexdigest()


def _snapshot(value):
    """Freeze already budgeted plain data; this is not a second serializer."""
    kind = type(value)
    if kind is dict:
        return (dict, tuple((key, _snapshot(child)) for key, child in value.items()))
    if kind is list:
        return (list, tuple(_snapshot(child) for child in value))
    return (kind, value)


def _same(value, snapshot):
    """Bound comparison by the admitted shape, including after final callback."""
    kind, expected = snapshot
    if type(value) is not kind:
        return False
    if kind is dict:
        if len(value) != len(expected) or any(type(key) is not str for key in value):
            return False
        return all(key in value and _same(value[key], child) for key, child in expected)
    if kind is list:
        return len(value) == len(expected) and all(
            _same(child, prior) for child, prior in zip(value, expected))
    if kind is str:
        return len(value) == len(expected) and value == expected
    return value == expected


def _containers(value):
    """Identify mutable containers only after the bounded plain check."""
    if type(value) not in (dict, list):
        return set()
    found = {id(value)}
    children = value.values() if type(value) is dict else value
    for child in children:
        found.update(_containers(child))
    return found


def _utf8(value, ceiling, reason):
    if type(value) is not str or len(value) > ceiling:
        _fail(reason)
    total = 0
    for character in value:
        point = ord(character)
        if 0xD800 <= point <= 0xDFFF:
            _fail("unpaired-surrogate")
        total += (1 if point <= 0x7F else 2 if point <= 0x7FF
                  else 3 if point <= 0xFFFF else 4)
        if total > ceiling:
            _fail(reason)
    return value.encode("utf-8")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("projection-json-duplicate-key")
        result[key] = value
    return result


def _number(_value):
    # The closed upstream receipt has no numeric fields, finite or otherwise.
    _fail("projection-json-number")


def _decode(basis, text):
    try:
        result = json.loads(text, object_pairs_hook=_pairs,
                            parse_int=_number, parse_float=_number,
                            parse_constant=_number)
    except (json.JSONDecodeError, UnicodeError, RecursionError) as exc:
        raise GetRenderAdmissionRefusal("projection-json") from exc
    basis.size(result, basis.limits["MAX_CONFIG_BYTES"])
    return result


def _receipt(basis, value, page, get_sha):
    _keys(value, _RECEIPT_KEYS, "projection-receipt-keys")
    _keys(value["source_reference"], _REFERENCE_KEYS, "source-reference-keys")
    for field, literal in (("schema", "sia-gbrain-get-render-projection-v1"),
                           ("source_id", "sia")):
        if type(value[field]) is not str or value[field] != literal:
            _fail("projection-receipt-contract")
    reference = value["source_reference"]
    for key in _REFERENCE_KEYS:
        if type(reference[key]) is not str or reference[key] != page[key]:
            _fail("source-reference-mismatch")
    if type(value["non_claims"]) is not list \
            or not _same(value["non_claims"], _snapshot(list(GET_RENDER_PROJECTION_NON_CLAIMS))):
        _fail("projection-non-claims")
    if type(value["status"]) is not str or value["status"] not in {"matched", "mismatch"}:
        _fail("projection-status")
    if type(value["page_state"]) is not str \
            or value["page_state"] not in {"live", "missing_or_deleted"}:
        _fail("projection-page-state")
    if type(value["type_basis"]) is not str or value["type_basis"] not in _TYPE_BASES:
        _fail("projection-type-basis")
    for field in _MATCH_FLAGS + _NO_WRITE_FLAGS:
        if type(value[field]) is not bool:
            _fail("projection-boolean")
    if any(value[field] is not False for field in _NO_WRITE_FLAGS):
        _fail("projection-no-write-scope")
    for field in ("parse_error_codes", "mismatch_reasons"):
        codes = value[field]
        if type(codes) is not list or any(type(code) is not str or not code for code in codes):
            _fail("projection-reason-shape")
    reasons = value["mismatch_reasons"]
    if reasons != [reason for reason in _MISMATCH_REASONS if reason in reasons]:
        _fail("projection-mismatch-reason-roster")
    _hex(value["get_stdout_sha256"], "projection-get-digest")
    if value["get_stdout_sha256"] != get_sha:
        _fail("projection-get-mismatch")
    for field in _LOGICAL_HASHES + ("current_get_stdout_sha256",):
        if value[field] is not None:
            _hex(value[field], "projection-digest")
    if value["status"] == "mismatch":
        if not reasons:
            _fail("projection-mismatch-reason-roster")
        _fail("upstream-non-match", upstream_status="mismatch", mismatch_reasons=reasons)
    if value["page_state"] != "live" or value["parse_error_codes"] or reasons \
            or value["type_basis"] not in _MATCH_TYPE_BASES:
        _fail("projection-match-contract")
    if any(value[field] is not True for field in _MATCH_FLAGS):
        _fail("projection-match-flag")
    expected = value["expected_projection_sha256"]
    if expected is None or any(value[field] != expected for field in _LOGICAL_HASHES):
        _fail("logical-projection-digest-join")
    if value["current_get_stdout_sha256"] != get_sha:
        _fail("current-get-digest-join")


def admit(owner, *, source_version, expected_source_version_native_sha256,
          get_stdout, expected_get_stdout_sha256, projection_stdout,
          expected_projection_stdout_sha256, input_current):
    """Admit only supplied consistency, with explicit pins and caller callback.

    ``input_current`` must return None or raise. Its exceptions propagate
    unchanged; a boolean is not a permission result. The callback is invoked
    only after all supplied receipt premises pass consistency admission.
    No file, process, lease, clock, source observer or output sink is accessed.
    """
    basis = _Basis(owner)
    if not callable(input_current):
        _fail("input-current-required")
    _keys(source_version, _VERSION_KEYS, "source-version-keys")
    if any(type(source_version[key]) is not str for key in _VERSION_KEYS):
        _fail("source-version-values")
    request = {
        "source_version": source_version,
        "expected_source_version_native_sha256": expected_source_version_native_sha256,
        "get_stdout": get_stdout,
        "expected_get_stdout_sha256": expected_get_stdout_sha256,
        "projection_stdout": projection_stdout,
        "expected_projection_stdout_sha256": expected_projection_stdout_sha256,
    }
    # Closed shallow types and cheap lengths precede complete native preflight.
    for value in (get_stdout, projection_stdout, expected_source_version_native_sha256,
                  expected_get_stdout_sha256, expected_projection_stdout_sha256):
        if type(value) is not str:
            _fail("request-text-shape")
    if len(source_version["content"]) > _live.MAX_CONTENT_BYTES \
            or len(get_stdout) > _live.MAX_CONTENT_BYTES \
            or len(projection_stdout) > basis.limits["MAX_EXTERNAL_OUTPUT_BYTES"]:
        _fail("request-text-capacity")
    basis.size(request)
    request_snapshot = _snapshot(request)
    for expected in (expected_source_version_native_sha256,
                     expected_get_stdout_sha256, expected_projection_stdout_sha256):
        _hex(expected, "external-pin-shape")
    subject = source_version["subject"]
    if not subject or len(subject) > _activation.MAX_SUBJECT_BYTES \
            or _SUBJECT.fullmatch(subject) is None or source_version["origin"] not in _ORIGINS:
        _fail("source-version-identity")
    for field in ("source_sha256", "content_sha256", "version_sha256"):
        _hex(source_version[field], "source-version-digest")
    if basis.sha(source_version) != expected_source_version_native_sha256:
        _fail("source-version-native-pin")
    raw_source = _utf8(source_version["content"], _live.MAX_CONTENT_BYTES, "source-content-capacity")
    source_sha = hashlib.sha256(raw_source).hexdigest()
    if source_version["source_sha256"] != source_sha or source_version["content_sha256"] != source_sha:
        _fail("source-raw-content-pin")
    # Reuse the original live UTF-8 version family; never hash normalized text.
    if _live._version(source_version) != source_version["version_sha256"]:
        _fail("source-version-family-pin")
    raw_get = _utf8(get_stdout, min(_live.MAX_CONTENT_BYTES,
                    basis.limits["MAX_EXTERNAL_OUTPUT_BYTES"]), "get-stdout-capacity")
    if hashlib.sha256(raw_get).hexdigest() != expected_get_stdout_sha256:
        _fail("get-stdout-raw-pin")
    raw_projection = _utf8(projection_stdout, basis.limits["MAX_EXTERNAL_OUTPUT_BYTES"],
                           "projection-stdout-capacity")
    if hashlib.sha256(raw_projection).hexdigest() != expected_projection_stdout_sha256:
        _fail("projection-stdout-raw-pin")
    receipt = _decode(basis, projection_stdout)
    _receipt(basis, receipt, source_version, expected_get_stdout_sha256)
    receipt_snapshot = _snapshot(receipt)
    result = {
        "schema": "sia-get-render-consistency-v1",
        "status": "supplied-match-consistent-not-observed",
        "source_id": "sia",
        "source_version": source_version,
        "source_version_native_sha256": expected_source_version_native_sha256,
        "get_stdout": get_stdout,
        "get_stdout_sha256": expected_get_stdout_sha256,
        "projection_stdout": projection_stdout,
        "projection_stdout_sha256": expected_projection_stdout_sha256,
        "projection_receipt": receipt,
        "projection_receipt_native_sha256": basis.sha(receipt),
        "non_claims": list(NON_CLAIMS),
    }
    # Reserve the complete returned representation, including its digest leaf,
    # before allocating its final wire or detaching caller-owned dictionaries.
    result["consistency_sha256"] = "0" * 64
    basis.size({"request": request, "receipt": receipt,
                "result": result, "result_copy": result})
    result["consistency_sha256"] = basis.sha({
        key: value for key, value in result.items() if key != "consistency_sha256"})
    result_snapshot = _snapshot(result)

    def check(*, detached=None, has_copy=False):
        basis.current()
        if not _same(request, request_snapshot) or not _same(receipt, receipt_snapshot) \
                or not _same(result, result_snapshot):
            _fail("admitted-input-changed")
        if has_copy:
            if not _same(detached, result_snapshot):
                _fail("returned-copy-changed")
            retained = _containers(request) | _containers(receipt) | _containers(result)
            if retained & _containers(detached):
                _fail("returned-copy-not-detached")

    def current(*, detached=None, has_copy=False):
        check(detached=detached, has_copy=has_copy)
        returned = input_current()
        check(detached=detached, has_copy=has_copy)
        if returned is not None:
            _fail("input-current-return")

    current()
    detached = copy.deepcopy(result)
    current(detached=detached, has_copy=True)
    # No callback, serializer or copy follows this bounded plain comparison.
    check(detached=detached, has_copy=True)
    return detached
