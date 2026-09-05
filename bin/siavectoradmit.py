"""Admit a raw-vector adapter response against independently bound inputs.

This boundary checks the wire observation. It does not admit a build receipt,
attest serving weights, or establish a benchmark win. In particular, ranked
row hashes are checked over the adapter's original supplied UTF-8 bytes;
Python never reserializes floating-point rows to reconstruct that identity.
"""

import base64
import binascii
import copy
import hashlib
import math
import re
import struct

import siaqueue
from siavector import MAX_RESPONSE_BYTES, VectorRefusal, _canonical_bytes


# Wire budgets are the adapter's published constants, not computed estimates.
MAX_REQUEST_BYTES = 262144
# The pinned gateway truncates at 8000 UTF-16 code units. This UTF-8 byte
# ceiling is conservative across admitted Unicode and prevents truncation.
MAX_QUERY_BYTES = 8000
MAX_QUERIES = 64
MAX_RESULTS = 100
MAX_RESULT_BYTES = 4194304
MAX_CHUNK_BYTES = 65536
MAX_DIMENSIONS = 16000
MAX_SAFE_INTEGER = 9007199254740991
_DIGEST = re.compile(r"[a-f0-9]{64}")
_QUERY_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]*")
_MODEL = re.compile(r"(?:llama-server|ollama):[A-Za-z0-9][A-Za-z0-9._:/-]*")
_ENDPOINT = re.compile(r"http://(?:127\.0\.0\.1|\[::1\]):([0-9]+)/v1")
_EXCLUDES = ("test/", "attachments/", ".raw/")
_ROW_KEYS = {
    "slug", "source_id", "page_id", "title", "type", "chunk_id",
    "chunk_index", "chunk_source", "chunk_text", "score",
    "score_f64le_base64", "stale",
}
NON_CLAIMS = (
    "The embedding model identifier and endpoint are bound; served model weights are not attested by this adapter.",
    "Raw-vector search retains gbrain page pooling, visibility filters, and bounded approximate candidate retrieval.",
    "The parent admits the executable and build receipt; their supplied identities are not self-attestation.",
    "A private benchmark snapshot does not attest the resident index or the completeness of machine history.",
    "Pre/post logical identity checks rely on the private snapshot and exclusive engine owner; they are not a hostile same-user sandbox.",
    "Scores and vectors are observed floating-point engine output, not JACKAL-certified arithmetic or a cognitive win.",
    "Returned chunks retain their text; this adapter does not infer an origin label that the raw API did not return.",
)


class AdapterRefusal(VectorRefusal):
    """A well-shaped adapter refusal, with its named reason and boundaries."""

    def __init__(self, reason, non_claims):
        self.reason = reason
        self.non_claims = tuple(non_claims)
        super().__init__("vector adapter refused: " + reason)


def _refuse(reason):
    raise VectorRefusal("vector response " + reason)


def _keys(value, names, label):
    if type(value) is not dict or len(value) != len(names) \
            or set(value) != set(names):
        _refuse(label + " shape is invalid")


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _text(value, maximum, *, empty=False, controls=False):
    if type(value) is not str or len(value) > maximum \
            or not empty and not value:
        return False
    try:
        if len(value.encode("utf-8", errors="strict")) > maximum:
            return False
    except UnicodeError:
        return False
    return controls or not any(
        ord(char) < 32 and char not in "\t\r\n" or ord(char) == 127
        for char in value)


def _digest(value):
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _blob(value, maximum, label):
    if type(value) is not str \
            or len(value) > 4 * ((maximum + 2) // 3):
        _refuse(label + " bytes are invalid")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        _refuse(label + " bytes are invalid")
    if len(decoded) > maximum \
            or base64.b64encode(decoded).decode("ascii") != value:
        _refuse(label + " bytes are invalid")
    return decoded


def _request(request):
    _keys(request, {
        "v", "operation", "lane", "queries", "limit", "snapshot",
        "embedding", "binding",
    }, "request")
    if not _integer(request["v"], 1, 1) \
            or request["operation"] not in ("capture", "query") \
            or request["lane"] != "raw_vector" \
            or not _integer(request["limit"], 1, MAX_RESULTS) \
            or type(request["queries"]) is not list \
            or len(request["queries"]) > MAX_QUERIES \
            or (request["operation"] == "capture") != (not request["queries"]):
        _refuse("request contract is invalid")
    ids = set()
    for query in request["queries"]:
        _keys(query, {"id", "text"}, "request query")
        if not _text(query["id"], 128) \
                or _QUERY_ID.fullmatch(query["id"]) is None \
                or query["id"] in ids \
                or not _text(query["text"], MAX_QUERY_BYTES) \
                or not query["text"].strip():
            _refuse("request query is invalid")
        ids.add(query["id"])
    snapshot = request["snapshot"]
    _keys(snapshot, {"fd", "logical_sha256", "catalog_sha256"},
          "request snapshot")
    if snapshot["fd"] is not None \
            and not _integer(snapshot["fd"], 3, 1048576):
        _refuse("request snapshot descriptor is invalid")
    for key in ("logical_sha256", "catalog_sha256"):
        if request["operation"] == "capture":
            if snapshot[key] is not None:
                _refuse("capture request already names an observed identity")
        elif not _digest(snapshot[key]):
            _refuse("request snapshot identity is invalid")
    embedding = request["embedding"]
    _keys(embedding, {"model", "dimensions", "endpoint"}, "request embedding")
    if not _text(embedding["model"], 256) \
            or _MODEL.fullmatch(embedding["model"]) is None \
            or not _integer(embedding["dimensions"], 1, MAX_DIMENSIONS) \
            or not _text(embedding["endpoint"], 256):
        _refuse("request embedding is invalid")
    endpoint = _ENDPOINT.fullmatch(embedding["endpoint"])
    if endpoint is None:
        _refuse("request endpoint is invalid")
    port = endpoint.group(1)
    if len(port) > 5 or not 1 <= int(port) <= 65535 \
            or str(int(port)) != port or int(port) == 80:
        _refuse("request endpoint is not canonical")
    _keys(request["binding"], {"executable_sha256", "build_receipt_sha256"},
          "request binding")
    if any(not _digest(value) for value in request["binding"].values()):
        _refuse("request binding is invalid")
    if len(_canonical_bytes(request)) > MAX_REQUEST_BYTES:
        _refuse("request exceeds its byte ceiling")


def admit_request(request):
    """Detach a complete bounded request before capture, I/O, or launch.

    Shape, collection counts, scalar types, and per-field byte limits precede
    serialization and copying. The logical request may retain snapshot.fd=None
    until transport assigns the private descriptor in its sealed request.
    """
    try:
        _request(request)
        return copy.deepcopy(request)
    except VectorRefusal:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError,
            UnicodeError, KeyError) as exc:
        raise VectorRefusal("vector request could not be admitted") from exc


def _same_json(left, right, depth=0):
    """Compare JSON values without Python's bool/int equivalence."""
    if depth > 32:
        return False
    if type(left) in (int, float) and type(right) in (int, float):
        return _number(left) and _number(right) and left == right
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(
            _same_json(left[key], right[key], depth + 1) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(
            _same_json(a, b, depth + 1) for a, b in zip(left, right))
    return type(left) in (str, bool, type(None)) and left == right


def _rows(rows, limit):
    if type(rows) is not list or len(rows) > limit:
        _refuse("ranked row roster is invalid")
    slugs, pages, chunks = set(), set(), set()
    previous = None
    for row in rows:
        _keys(row, _ROW_KEYS, "ranked row")
        if not _text(row["slug"], 1024) \
                or row["slug"].startswith(_EXCLUDES) \
                or row["source_id"] != "sia" \
                or not _integer(row["page_id"], 1, MAX_SAFE_INTEGER) \
                or not _integer(row["chunk_id"], 1, MAX_SAFE_INTEGER) \
                or not _integer(row["chunk_index"], 0, MAX_SAFE_INTEGER) \
                or not _text(row["title"], 4096) \
                or not _text(row["type"], 128) \
                or row["chunk_source"] not in ("compiled_truth", "timeline") \
                or not _text(row["chunk_text"], MAX_CHUNK_BYTES,
                             empty=True, controls=True) \
                or type(row["stale"]) is not bool or not _number(row["score"]):
            _refuse("ranked row fields are invalid")
        score_bytes = _blob(row["score_f64le_base64"],
                            struct.calcsize("<d"), "score")
        if len(score_bytes) != struct.calcsize("<d"):
            _refuse("score width is invalid")
        score = struct.unpack("<d", score_bytes)[0]
        # JSON.stringify maps negative zero to 0. Preserve the binary witness,
        # while requiring equality of the finite numeric JSON value it emits.
        if not math.isfinite(score) or row["score"] != score:
            _refuse("score bytes disagree with the numeric score")
        if row["slug"] in slugs or row["page_id"] in pages \
                or row["chunk_id"] in chunks:
            _refuse("ranked row identities are duplicated")
        current = (score, row["page_id"], row["chunk_id"])
        if previous is not None and (
                score > previous[0]
                or score == previous[0] and current[1:] < previous[1:]):
            _refuse("ranked row order is invalid")
        previous = current
        slugs.add(row["slug"])
        pages.add(row["page_id"])
        chunks.add(row["chunk_id"])


def _latency(value, keys, total=None):
    _keys(value, keys, "latency")
    if any(not _number(number) or number < 0
           or total is not None and number > total for number in value.values()):
        _refuse("latency is invalid")


def _admit(payload, request, executable_sha256, request_sha256, config_sha256):
    _request(request)
    if any(not _digest(value) for value in (
            executable_sha256, request_sha256, config_sha256)) \
            or executable_sha256 != request["binding"]["executable_sha256"]:
        _refuse("caller binding is invalid")
    if type(payload) is not dict:
        _refuse("envelope must be an object")
    # This is only a local allocation ceiling. It is never used to recreate
    # the adapter's original row or stdout identity.
    if len(_canonical_bytes(payload)) > MAX_RESPONSE_BYTES:
        _refuse("envelope exceeds its byte ceiling")
    if type(payload.get("non_claims")) is not list \
            or not _same_json(payload["non_claims"], list(NON_CLAIMS)):
        _refuse("non-claim roster is invalid")
    if payload.get("status") == "refused":
        _keys(payload, {"v", "status", "lane", "reason", "non_claims"},
              "refusal")
        if not _integer(payload["v"], 1, 1) \
                or payload["lane"] != "raw_vector" \
                or type(payload["reason"]) is not str \
                or re.fullmatch(r"[a-z][a-z0-9-]{0,127}", payload["reason"]) is None:
            _refuse("refusal contract is invalid")
        raise AdapterRefusal(payload["reason"], payload["non_claims"])
    _keys(payload, {"v", "status", "operation", "lane", "bindings",
                    "results", "latency_ms", "non_claims"}, "envelope")
    if not _integer(payload["v"], 1, 1) or payload["status"] != "ok" \
            or payload["operation"] != request["operation"] \
            or payload["lane"] != "raw_vector":
        _refuse("envelope contract is invalid")
    bindings = payload["bindings"]
    _keys(bindings, {
        "logical_sha256", "catalog_sha256", "executable_sha256",
        "build_receipt_sha256", "config_sha256", "request_sha256",
    }, "binding")
    if any(not _digest(value) for value in bindings.values()):
        _refuse("binding digests are invalid")
    expected = {
        **request["binding"], "executable_sha256": executable_sha256,
        "request_sha256": request_sha256, "config_sha256": config_sha256,
    }
    if request["operation"] == "query":
        expected.update({key: request["snapshot"][key]
                         for key in ("logical_sha256", "catalog_sha256")})
    if any(bindings[key] != value for key, value in expected.items()):
        _refuse("binding disagrees with the requested observation")
    _latency(payload["latency_ms"], {"total"})
    total = payload["latency_ms"]["total"]
    if type(payload["results"]) is not list \
            or len(payload["results"]) != len(request["queries"]):
        _refuse("query result roster is incomplete")
    for result, query in zip(payload["results"], request["queries"]):
        _keys(result, {
            "id", "query_sha256", "vector_f32le_base64", "vector_sha256",
            "rows", "ranked_rows_canonical_base64", "ranked_rows_sha256",
            "latency_ms",
        }, "query result")
        if result["id"] != query["id"] \
                or result["query_sha256"] != hashlib.sha256(
                    query["text"].encode("utf-8")).hexdigest():
            _refuse("query identity or order disagrees with the request")
        width = request["embedding"]["dimensions"] * struct.calcsize("<f")
        vector = _blob(result["vector_f32le_base64"], width, "query vector")
        if len(vector) != width or not _digest(result["vector_sha256"]) \
                or hashlib.sha256(vector).hexdigest() != result["vector_sha256"]:
            _refuse("query vector identity or dimensions are invalid")
        components = [item[0] for item in struct.iter_unpack("<f", vector)]
        if not all(math.isfinite(value) for value in components) \
                or not any(value != 0 for value in components):
            _refuse("query vector must be finite and nonzero")
        encoded_rows = _blob(result["ranked_rows_canonical_base64"],
                             MAX_RESULT_BYTES, "ranked rows")
        if not _digest(result["ranked_rows_sha256"]) \
                or hashlib.sha256(encoded_rows).hexdigest() \
                != result["ranked_rows_sha256"]:
            _refuse("ranked row byte identity is invalid")
        try:
            wire_rows = siaqueue.strict_json_loads(
                encoded_rows.decode("utf-8", errors="strict"))
        except (ValueError, TypeError, UnicodeError, RecursionError):
            _refuse("ranked row bytes are not strict UTF-8 JSON")
        if not _same_json(result["rows"], wire_rows):
            _refuse("ranked row bytes disagree with the returned rows")
        _rows(result["rows"], request["limit"])
        _rows(wire_rows, request["limit"])
        _latency(result["latency_ms"], {"embedding", "search"}, total)
    return copy.deepcopy(payload)


def admit_response(payload, request, *, executable_sha256,
                   request_sha256, config_sha256):
    """Return a detached observation after every response field is admitted.

    ``request`` is the caller-held logical request. Its snapshot fd may be
    None before transport assigns the sealed request's actual descriptor.
    ``request_sha256`` and ``executable_sha256`` come from that transport;
    ``config_sha256`` must come from independently admitted caller policy.
    Never fill any expectation from the response being reviewed.
    """
    try:
        return _admit(payload, request, executable_sha256,
                      request_sha256, config_sha256)
    except VectorRefusal:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError,
            UnicodeError, KeyError, struct.error) as exc:
        raise VectorRefusal("vector response could not be admitted") from exc
