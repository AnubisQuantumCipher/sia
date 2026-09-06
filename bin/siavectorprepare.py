"""Admit the frozen preparer's request and complete readback receipt.

Caller-held exported pages determine text, origin, roster and chunk expectations.
The launch supplies the sealed request digest independently. Vector witnesses are
checked for complete coverage and digest shape; this module cannot reconstruct
vectors from hashes. Executable admission, model-service attestation and the
subsequent physical/logical index capture remain separate parent obligations.
"""

import base64
import binascii
import copy
import hashlib
import re

import siaqueue
from siavector import VectorRefusal, _canonical_bytes


# These are the frozen preparer's published admission limits and policy.
MAX_CHUNK_BYTES = 2048
MAX_PAGE_BYTES = 131072
MAX_TOTAL_PAGE_BYTES = 4194304
MAX_REQUEST_BYTES = 8388608
MAX_PAGES = 256
MAX_CHUNKS = 4096
MAX_SETUP_DIAGNOSTIC_BYTES = 65536
MAX_RECEIPT_BYTES = 2097152
MAX_SAFE_INTEGER = 9007199254740991
POLICY = {"chunking": "utf8-contiguous-codepoint-v1",
          "max_chunk_bytes": MAX_CHUNK_BYTES, "source": "sia",
          "chunk_source": "compiled_truth", "input_type": "document"}
NON_CLAIMS = (
    "Origin labels are retained from the supplied frozen export; this preparer does not independently attest its source evidence.",
    "This is a new benchmark projection of exported pages, not a copy or attestation of the resident index.",
    "The provider model identifier and endpoint are bound; the parent must separately attest served model weights.",
    "Preparation timestamps are index-construction metadata, not the original event times.",
    "Lossless deterministic chunking is a declared benchmark policy, not a cognitive mechanism or a demonstrated retrieval improvement.",
    "Failure can leave a partial private index; it is never reported as an admitted completed snapshot.",
)
DIAGNOSTIC_NON_CLAIMS = (
    "Captured setup diagnostics are informational output, not proof of schema or data correctness.",
    "When truncated is true, text/base64 and sha256 describe only the retained prefix, not the complete diagnostic stream.",
)
_DIGEST = re.compile(r"[a-f0-9]{64}")
_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*")
_TYPE = re.compile(r"[a-z][a-z0-9_-]*")
_MODEL = re.compile(r"(?:ollama|llama-server):[A-Za-z0-9][A-Za-z0-9._:/-]*")
_ENDPOINT = re.compile(r"http://(?:127\.0\.0\.1|\[::1\]):([0-9]+)/v1")
_REASON = re.compile(r"[a-z][a-z0-9-]{0,127}")
_ORIGINS = ("evidence", "derived", "model", "legacy-unlabeled")
_EXCLUDES = ("test/", "attachments/", ".raw/")
_DIAGNOSTIC_CLASSES = (
    "known-setup-diagnostics", "unrecognized-setup-diagnostics",
    "setup-diagnostics-byte-budget", "setup-diagnostics-write-invalid",
    "schema-initialization-failed", "setup-diagnostics-utf8-invalid",
)


class PreparationRefusal(VectorRefusal):
    """A producer refusal, retained with its stated boundaries and diagnostics."""

    def __init__(self, reason, non_claims, setup_diagnostics=None):
        self.reason = reason
        self.non_claims = tuple(non_claims)
        self.setup_diagnostics = copy.deepcopy(setup_diagnostics)
        super().__init__("vector preparer refused: " + reason)


def _refuse(reason):
    raise VectorRefusal("vector preparer admission: " + reason)


def _keys(value, names, label):
    if type(value) is not dict or len(value) != len(names) \
            or set(value) != set(names):
        _refuse(label + " shape is invalid")


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _text(value, maximum, *, empty=False):
    if type(value) is not str or len(value) > maximum \
            or not empty and not value or "\0" in value:
        return False
    try:
        return len(value.encode("utf-8", "strict")) <= maximum
    except UnicodeError:
        return False


def _digest(value):
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _same(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(_same(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return type(left) in (str, int, bool, type(None)) and left == right


def _chunk_bytes(text):
    """Cut bounded UTF-8 byte slices, backing up only across partial codepoints."""
    encoded = text.encode("utf-8", "strict")
    start = 0
    while start < len(encoded):
        end = min(start + MAX_CHUNK_BYTES, len(encoded))
        while True:
            try:
                encoded[start:end].decode("utf-8", "strict")
                break
            except UnicodeDecodeError:
                end -= 1
        yield encoded[start:end]
        start = end


def _embedding(value):
    _keys(value, {"model", "dimensions", "endpoint"}, "embedding")
    if not _text(value["model"], 256) or _MODEL.fullmatch(value["model"]) is None \
            or not _integer(value["dimensions"], 1, 16000) \
            or not _text(value["endpoint"], 256):
        _refuse("embedding contract is invalid")
    endpoint = _ENDPOINT.fullmatch(value["endpoint"])
    if endpoint is None:
        _refuse("embedding endpoint is invalid")
    port = endpoint.group(1)
    if len(port) > 5 or not 1 <= int(port) <= 65535 \
            or str(int(port)) != port or int(port) == 80:
        _refuse("embedding endpoint is not canonical")


def _request(request):
    _keys(request, {"v", "operation", "source", "dataset_sha256", "pages_sha256",
                    "embedding", "output", "pages"}, "request")
    if not _integer(request["v"], 1, 1) or request["operation"] != "prepare_index" \
            or request["source"] != "sia" or not _digest(request["dataset_sha256"]) \
            or not _digest(request["pages_sha256"]):
        _refuse("request contract is invalid")
    _keys(request["output"], {"parent_fd"}, "output")
    descriptor = request["output"]["parent_fd"]
    if descriptor is not None and not _integer(descriptor, 3, 1048576):
        _refuse("output descriptor is invalid")
    _embedding(request["embedding"])
    pages = request["pages"]
    if type(pages) is not list or not 1 <= len(pages) <= MAX_PAGES:
        _refuse("page roster is outside its count ceiling")
    slugs = set()
    total_bytes = 0
    total_chunks = 0
    for page in pages:
        _keys(page, {"slug", "title", "type", "origin", "text", "text_sha256"}, "input page")
        if not _text(page["slug"], 1024) or _SLUG.fullmatch(page["slug"]) is None \
                or page["slug"] in slugs or page["slug"].startswith(_EXCLUDES) \
                or not _text(page["title"], 4096) or not _text(page["type"], 128) \
                or _TYPE.fullmatch(page["type"]) is None or type(page["origin"]) is not str \
                or page["origin"] not in _ORIGINS or not _text(page["text"], MAX_PAGE_BYTES):
            _refuse("input page contract is invalid")
        content = page["text"].encode("utf-8")
        if not _digest(page["text_sha256"]) or _sha(content) != page["text_sha256"]:
            _refuse("input page text identity is invalid")
        slugs.add(page["slug"])
        total_bytes += len(content)
        if total_bytes > MAX_TOTAL_PAGE_BYTES:
            _refuse("input pages exceed the aggregate byte ceiling")
        total_chunks += sum(1 for _ in _chunk_bytes(page["text"]))
        if total_chunks > MAX_CHUNKS:
            _refuse("input pages exceed the chunk count ceiling")
    if _sha(_canonical_bytes(pages)) != request["pages_sha256"]:
        _refuse("input page roster identity is invalid")
    if len(_canonical_bytes(request)) > MAX_REQUEST_BYTES:
        _refuse("request exceeds its byte ceiling")


def admit_request(request):
    """Detach bounded caller inputs before I/O; parent_fd may await assignment."""
    try:
        _request(request)
        return copy.deepcopy(request)
    except VectorRefusal:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError, KeyError) as exc:
        raise VectorRefusal("vector preparer request could not be admitted") from exc


def _non_claims(value, expected, label):
    if type(value) is not list or len(value) != len(expected) \
            or any(type(item) is not str for item in value) or tuple(value) != expected:
        _refuse(label + " nonclaims are incomplete or changed")


def _diagnostics(value, dimensions, *, success):
    _keys(value, {"source", "classification", "text", "utf8_base64", "sha256",
                  "bytes_seen", "truncated", "non_claims"}, "setup diagnostics")
    if value["source"] != "gbrain.initSchema/process.stderr" \
            or type(value["classification"]) is not str \
            or value["classification"] not in _DIAGNOSTIC_CLASSES \
            or not _integer(value["bytes_seen"], 0, MAX_SAFE_INTEGER) \
            or type(value["truncated"]) is not bool or not _digest(value["sha256"]):
        _refuse("setup diagnostic contract is invalid")
    encoded = value["utf8_base64"]
    if type(encoded) is not str or len(encoded) > 4 * ((MAX_SETUP_DIAGNOSTIC_BYTES + 2) // 3):
        _refuse("setup diagnostic bytes exceed the byte ceiling")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        _refuse("setup diagnostic base64 is invalid")
    if len(raw) > MAX_SETUP_DIAGNOSTIC_BYTES or base64.b64encode(raw).decode("ascii") != encoded \
            or _sha(raw) != value["sha256"]:
        _refuse("setup diagnostic byte identity is invalid")
    try:
        decoded = raw.decode("utf-8", "strict")
    except UnicodeError:
        decoded = None
    if type(value["text"]) is not type(decoded) or value["text"] != decoded:
        _refuse("setup diagnostic text differs from its original bytes")
    _non_claims(value["non_claims"], DIAGNOSTIC_NON_CLAIMS, "setup diagnostic")
    classification = value["classification"]
    if value["truncated"]:
        if len(raw) != MAX_SETUP_DIAGNOSTIC_BYTES or value["bytes_seen"] <= MAX_SETUP_DIAGNOSTIC_BYTES \
                or classification != "setup-diagnostics-byte-budget":
            _refuse("truncated setup diagnostic prefix is inconsistent")
    elif value["bytes_seen"] != len(raw) or classification == "setup-diagnostics-byte-budget":
        _refuse("complete setup diagnostic byte count is inconsistent")
    if classification == "setup-diagnostics-utf8-invalid" and decoded is not None:
        _refuse("setup diagnostic UTF-8 classification is inconsistent")
    if classification == "known-setup-diagnostics":
        if decoded is None or value["truncated"] or decoded and not decoded.endswith("\n"):
            _refuse("known setup diagnostics are not complete UTF-8")
        lines = decoded[:-1].split("\n") if decoded else []
        for line in lines:
            if line != "  Setting up brain schema (v144)..." \
                    and line != f"  v142: takes.embedding resized to vector({dimensions}); existing take vectors cleared" \
                    and re.fullmatch(r"  [0-9]+ migration\(s\) applied", line) is None:
                _refuse("unknown diagnostic was classified as known setup output")
    if success and classification != "known-setup-diagnostics":
        _refuse("failed or unrecognized setup diagnostics cannot accompany success")


def _admit(payload, request, request_sha256):
    _request(request)
    if not _digest(request_sha256):
        _refuse("caller-held sealed request identity is invalid")
    if type(payload) is not dict:
        _refuse("response is not an object")
    if payload.get("status") == "refused":
        fields = {"v", "status", "operation", "reason", "non_claims"}
        if "setup_diagnostics" in payload:
            fields.add("setup_diagnostics")
        _keys(payload, fields, "refusal")
        if not _integer(payload["v"], 1, 1) or payload["operation"] != "prepare_index" \
                or type(payload["reason"]) is not str or _REASON.fullmatch(payload["reason"]) is None:
            _refuse("refusal contract is invalid")
        _non_claims(payload["non_claims"], NON_CLAIMS, "preparer")
        diagnostic = payload.get("setup_diagnostics")
        if "setup_diagnostics" in payload:
            _diagnostics(diagnostic, request["embedding"]["dimensions"], success=False)
        if len(_canonical_bytes(payload)) > MAX_RECEIPT_BYTES:
            _refuse("refusal exceeds its byte ceiling")
        raise PreparationRefusal(payload["reason"], payload["non_claims"], diagnostic)
    _keys(payload, {"v", "status", "operation", "index_leaf", "bindings", "policy",
                    "embedding", "pages", "setup_diagnostics", "non_claims"}, "success")
    if not _integer(payload["v"], 1, 1) or payload["status"] != "ok" \
            or payload["operation"] != "prepare_index" or payload["index_leaf"] != "index":
        _refuse("success contract is invalid")
    _non_claims(payload["non_claims"], NON_CLAIMS, "preparer")
    _keys(payload["policy"], set(POLICY), "chunk policy")
    if not _same(payload["policy"], POLICY):
        _refuse("preparer changed the admitted chunk policy")
    _embedding(payload["embedding"])
    if not _same(payload["embedding"], request["embedding"]):
        _refuse("preparer changed the caller-held embedding configuration")
    expected_bindings = {"dataset_sha256": request["dataset_sha256"], "pages_sha256": request["pages_sha256"],
                         "request_sha256": request_sha256, "policy_sha256": _sha(_canonical_bytes(POLICY)),
                         "embedding_sha256": _sha(_canonical_bytes(request["embedding"]))}
    _keys(payload["bindings"], set(expected_bindings), "bindings")
    if not _same(payload["bindings"], expected_bindings):
        _refuse("preparer bindings differ from independently held expectations")
    pages = payload["pages"]
    if type(pages) is not list or len(pages) != len(request["pages"]):
        _refuse("preparer did not cover the complete caller-held page roster")
    for page, original in zip(pages, request["pages"]):
        _keys(page, {"slug", "origin", "text_sha256", "chunks"}, "page witness")
        if any(type(page[key]) is not str or page[key] != original[key]
               for key in ("slug", "origin", "text_sha256")):
            _refuse("page witness changed source order, origin or original text")
        chunks = page["chunks"]
        expected_chunks = list(_chunk_bytes(original["text"]))
        if type(chunks) is not list or len(chunks) != len(expected_chunks):
            _refuse("page witness omitted or added a chunk")
        for index, (chunk, content) in enumerate(zip(chunks, expected_chunks)):
            _keys(chunk, {"chunk_index", "text_sha256", "vector_sha256", "bytes"}, "chunk witness")
            if not _integer(chunk["chunk_index"], index, index) \
                    or not _integer(chunk["bytes"], len(content), len(content)) \
                    or not _digest(chunk["text_sha256"]) or chunk["text_sha256"] != _sha(content) \
                    or not _digest(chunk["vector_sha256"]):
                _refuse("chunk witness does not preserve exact ordered input bytes or a vector digest")
    _diagnostics(payload["setup_diagnostics"], request["embedding"]["dimensions"], success=True)
    if len(_canonical_bytes(payload)) > MAX_RECEIPT_BYTES:
        _refuse("receipt exceeds its byte ceiling")
    return copy.deepcopy(payload)


def admit_response(payload, request, *, request_sha256):
    """Return a detached receipt bound to caller pages and sealed launch identity.

    No expectation is learned from this response. In particular, the accepted
    vector hashes remain readback witnesses reported by the admitted preparer;
    their mathematical or model correctness is not established here.
    """
    try:
        return _admit(payload, request, request_sha256)
    except VectorRefusal:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError, KeyError) as exc:
        raise VectorRefusal("vector preparer response could not be admitted") from exc


def admit_response_bytes(encoded, request, *, request_sha256):
    """Decode a bounded strict UTF-8 JSON envelope before semantic admission."""
    if type(encoded) is not bytes or len(encoded) > MAX_RECEIPT_BYTES:
        _refuse("response wire bytes exceed the admitted boundary")
    try:
        payload = siaqueue.strict_json_loads(encoded.decode("utf-8", "strict"))
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise VectorRefusal("vector preparer response is not strict UTF-8 JSON") from exc
    return admit_response(payload, request, request_sha256=request_sha256)
