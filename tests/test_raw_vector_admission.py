"""The raw-vector boundary admits complete bound observations or refuses."""

import base64
import copy
import hashlib
import importlib
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "bin"))

# This literal is the adapter's required public boundary, independently pinned
# here so an implementation cannot make a shortened roster self-consistent.
NON_CLAIMS = [
    "The embedding model identifier and endpoint are bound; served model weights are not attested by this adapter.",
    "Raw-vector search retains gbrain page pooling, visibility filters, and bounded approximate candidate retrieval.",
    "The parent admits the executable and build receipt; their supplied identities are not self-attestation.",
    "A private benchmark snapshot does not attest the resident index or the completeness of machine history.",
    "Pre/post logical identity checks rely on the private snapshot and exclusive engine owner; they are not a hostile same-user sandbox.",
    "Scores and vectors are observed floating-point engine output, not JACKAL-certified arithmetic or a cognitive win.",
    "Returned chunks retain their text; this adapter does not infer an origin label that the raw API did not return.",
]


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _b64(value):
    return base64.b64encode(value).decode("ascii")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _row(**changes):
    row = {
        "slug": "events/audio/repair", "source_id": "sia", "page_id": 1,
        "title": "Audio repair", "type": "event-day", "chunk_id": 1,
        "chunk_index": 0, "chunk_source": "compiled_truth",
        "chunk_text": "wireplumber restarted\n[origin:evidence] retained text",
        "score": 0.75, "score_f64le_base64": _b64(struct.pack("<d", 0.75)),
        "stale": False,
    }
    row.update(changes)
    return row


def _bind_rows(result, rows, encoded=None):
    result["rows"] = copy.deepcopy(rows)
    encoded = _json(rows) if encoded is None else encoded
    result["ranked_rows_canonical_base64"] = _b64(encoded)
    result["ranked_rows_sha256"] = _sha(encoded)


def _fixture(operation="query"):
    expected = {
        "executable_sha256": _sha(b"compiled adapter"),
        "request_sha256": _sha(b"sealed descriptor-bearing request"),
        "config_sha256": _sha(b"independently admitted config"),
    }
    identity = {
        "logical_sha256": _sha(b"private snapshot logical identity"),
        "catalog_sha256": _sha(b"private snapshot catalog identity"),
    }
    request = {
        "v": 1, "operation": operation, "lane": "raw_vector",
        "queries": ([{"id": "held-out-a", "text": "What repaired audio?"},
                     {"id": "held-out-b", "text": "What happened later?"}]
                    if operation == "query" else []),
        "limit": 5,
        "snapshot": {"fd": None, **(identity if operation == "query" else {
            "logical_sha256": None, "catalog_sha256": None})},
        "embedding": {"model": "llama-server:private-fixture", "dimensions": 3,
                      "endpoint": "http://127.0.0.1:8080/v1"},
        "binding": {"executable_sha256": expected["executable_sha256"],
                    "build_receipt_sha256": _sha(b"admitted build receipt")},
    }
    payload = {
        "v": 1, "status": "ok", "operation": operation, "lane": "raw_vector",
        "bindings": {**identity, **request["binding"],
                     "request_sha256": expected["request_sha256"],
                     "config_sha256": expected["config_sha256"]},
        "results": [], "latency_ms": {"total": 0},
        "non_claims": list(NON_CLAIMS),
    }
    for query in request["queries"]:
        vector = struct.pack("<fff", 1.0, 0.0, 0.0)
        result = {
            "id": query["id"], "query_sha256": _sha(query["text"].encode()),
            "vector_f32le_base64": _b64(vector), "vector_sha256": _sha(vector),
            "latency_ms": {"embedding": 0, "search": 0},
        }
        _bind_rows(result, [_row()])
        payload["results"].append(result)
    return payload, request, expected


class RawVectorAdmission(unittest.TestCase):
    def setUp(self):
        try:
            self.admission = importlib.import_module("siavectoradmit")
        except ModuleNotFoundError as exc:
            self.fail(f"raw-vector response admission must exist: {exc}")
        self.refusal = importlib.import_module("siavector").VectorRefusal

    def _admit(self, fixture):
        payload, request, expected = fixture
        return self.admission.admit_response(payload, request, **expected)

    def _reject(self, fixture, reason=None):
        before = copy.deepcopy(fixture)
        assertion = (self.assertRaises(self.refusal) if reason is None else
                     self.assertRaisesRegex(self.refusal, reason))
        with assertion:
            self._admit(fixture)
        self.assertEqual(fixture, before, "refusal must not repair its inputs")

    def test_capture_and_query_are_admitted_as_distinct_operations(self):
        for operation in ("capture", "query"):
            fixture = _fixture(operation)
            before = copy.deepcopy(fixture)
            with self.subTest(operation=operation):
                admitted = self._admit(fixture)
                self.assertEqual(admitted, fixture[0])
                self.assertIsNot(admitted, fixture[0])
                self.assertEqual(fixture, before)
                admitted["non_claims"].clear()
                self.assertEqual(fixture, before)

    def test_every_response_roster_is_exact(self):
        paths = ((), ("bindings",), ("latency_ms",), ("results", 0),
                 ("results", 0, "latency_ms"), ("results", 0, "rows", 0))
        for path in paths:
            for action in ("missing", "extra"):
                fixture = _fixture()
                target = fixture[0]
                for part in path:
                    target = target[part]
                if action == "missing":
                    del target[next(iter(target))]
                else:
                    target["unexpected"] = "unadmitted"
                if path == ("results", 0, "rows", 0):
                    result = fixture[0]["results"][0]
                    _bind_rows(result, result["rows"])
                with self.subTest(path=path, action=action):
                    self._reject(fixture)

    def test_nonobject_envelopes_and_type_confused_containers_refuse(self):
        for payload in (None, True, "ok", [], 0):
            _, request, expected = _fixture()
            with self.subTest(payload=payload):
                self._reject((payload, request, expected))
        for path, bad in ((("bindings",), []), (("results",), {}),
                          (("latency_ms",), []), (("results", 0), None),
                          (("results", 0, "rows"), {}),
                          (("results", 0, "latency_ms"), [])):
            fixture = _fixture()
            target = fixture[0]
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = bad
            with self.subTest(path=path):
                self._reject(fixture)

    def test_top_level_status_lane_operation_and_version_are_exact(self):
        for key, bad in (("v", True), ("v", 1.0), ("v", "1"),
                         ("status", "estimated"), ("lane", "hybrid_query"),
                         ("operation", "capture"), ("status", None)):
            fixture = _fixture()
            fixture[0][key] = bad
            with self.subTest(key=key, bad=bad):
                self._reject(fixture)

    def test_capture_cannot_return_query_results_or_accept_query_expectations(self):
        fixture = _fixture("capture")
        fixture[0]["results"] = _fixture()[0]["results"]
        self._reject(fixture)
        payload, _, expected = _fixture("capture")
        self._reject((payload, _fixture()[1], expected))

    def test_all_process_build_config_request_and_snapshot_identities_are_bound(self):
        for key in _fixture()[0]["bindings"]:
            fixture = _fixture()
            fixture[0]["bindings"][key] = _sha(b"unrelated generation")
            with self.subTest(key=key):
                self._reject(fixture)
        fixture = _fixture()
        fixture[2]["executable_sha256"] = _sha(b"different transport executable")
        self._reject(fixture)
        for key in ("logical_sha256", "catalog_sha256"):
            fixture = _fixture("capture")
            fixture[0]["bindings"][key] = "not-a-digest"
            self._reject(fixture)

    def test_query_ids_hashes_count_and_order_cannot_be_rewritten(self):
        for action in ("missing", "extra", "reverse", "duplicate", "wrong-id",
                       "wrong-text-hash"):
            fixture = _fixture()
            results = fixture[0]["results"]
            if action == "missing":
                results.pop()
            elif action == "extra":
                results.append(copy.deepcopy(results[0]))
            elif action == "reverse":
                results.reverse()
            elif action == "duplicate":
                results[1]["id"] = results[0]["id"]
            elif action == "wrong-id":
                results[0]["id"] = "unrequested"
            else:
                results[0]["query_sha256"] = _sha(b"different query")
            with self.subTest(action=action):
                self._reject(fixture)

    def test_query_vectors_are_exact_finite_nonzero_binary32_observations(self):
        vectors = (b"", struct.pack("<f", 1.0), struct.pack("<ffff", 1, 0, 0, 0),
                   struct.pack("<fff", 0, 0, 0),
                   struct.pack("<fff", float("nan"), 0, 0),
                   struct.pack("<fff", float("inf"), 0, 0))
        for vector in vectors:
            fixture = _fixture()
            fixture[0]["results"][0].update(
                vector_f32le_base64=_b64(vector), vector_sha256=_sha(vector))
            with self.subTest(vector=vector.hex()):
                self._reject(fixture)
        fixture = _fixture()
        fixture[0]["results"][0]["vector_sha256"] = _sha(b"different vector")
        self._reject(fixture)
        fixture = _fixture()
        fixture[1]["embedding"]["dimensions"] = True
        self._reject(fixture)

    def test_binary_fields_require_canonical_base64(self):
        for field in ("vector_f32le_base64", "ranked_rows_canonical_base64"):
            for bad in ("!", "AAAA\n", True, None):
                fixture = _fixture()
                fixture[0]["results"][0][field] = bad
                with self.subTest(field=field, bad=bad):
                    self._reject(fixture)
        fixture = _fixture()
        row = _row(score_f64le_base64=_b64(struct.pack("<d", 0.75)) + "\n")
        _bind_rows(fixture[0]["results"][0], [row])
        self._reject(fixture)

    def test_score_base64_padding_bits_cannot_relabel_identical_bytes(self):
        fixture = _fixture()
        encoded = _row()["score_f64le_base64"]
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        # Change an unused low padding bit without changing the decoded score.
        changed = encoded[:-2] + alphabet[alphabet.index(encoded[-2]) + 1] + "="
        self.assertEqual(base64.b64decode(changed), base64.b64decode(encoded))
        _bind_rows(fixture[0]["results"][0], [
            _row(score_f64le_base64=changed)])
        self._reject(fixture)

    def test_original_adapter_row_bytes_are_hashed_without_python_float_reserialization(self):
        fixture = _fixture()
        row = _row(score=1e-7, score_f64le_base64=_b64(struct.pack("<d", 1e-7)))
        # JS canonicalJson emits 1e-7; Python's json encoder emits 1e-07.
        # This is a serialization fixture, not a recomputed ranking score.
        encoded = _json([row]).replace(b'"score":1e-07', b'"score":1e-7')
        _bind_rows(fixture[0]["results"][0], [row], encoded)
        admitted = self._admit(fixture)
        self.assertEqual(
            base64.b64decode(admitted["results"][0]["ranked_rows_canonical_base64"]),
            encoded)

    def test_signed_zero_score_bytes_are_retained_despite_json_zero_spelling(self):
        fixture = _fixture()
        score_bytes = struct.pack("<d", -0.0)
        row = _row(score=0, score_f64le_base64=_b64(score_bytes))
        _bind_rows(fixture[0]["results"][0], [row])
        admitted = self._admit(fixture)
        self.assertEqual(
            base64.b64decode(admitted["results"][0]["rows"][0]["score_f64le_base64"]),
            score_bytes)

    def test_row_bytes_must_hash_parse_strictly_and_match_the_returned_rows(self):
        encodings = (b"\xff", b"{}", b"[", b'[{"score":1,"score":2}]',
                     b'[{"score":NaN}]')
        for encoded in encodings:
            fixture = _fixture()
            result = fixture[0]["results"][0]
            _bind_rows(result, result["rows"], encoded)
            with self.subTest(encoded=encoded):
                self._reject(fixture)
        fixture = _fixture()
        fixture[0]["results"][0]["ranked_rows_sha256"] = _sha(b"other rows")
        self._reject(fixture)
        fixture = _fixture()
        fixture[0]["results"][0]["rows"][0]["chunk_text"] = "rewritten content"
        self._reject(fixture)
        fixture = _fixture()
        fixture[0]["results"][0]["rows"][0]["page_id"] = True
        self._reject(fixture)

    def test_duplicate_members_inside_bound_row_bytes_cannot_use_last_key_wins(self):
        fixture = _fixture()
        row = _row()
        encoded = _json([row]).replace(
            b'"score":0.75,', b'"score":0.5,"score":0.75,', 1)
        self.assertEqual(json.loads(encoded), [row])
        _bind_rows(fixture[0]["results"][0], [row], encoded)
        self._reject(fixture)

    def test_row_identity_source_and_scalar_fields_are_strict(self):
        changes = (
            {"page_id": True}, {"page_id": 1.0}, {"page_id": 0},
            {"chunk_id": False}, {"chunk_id": -1}, {"chunk_index": True},
            {"chunk_index": -1}, {"source_id": "default"},
            {"stale": 0}, {"chunk_source": "invented"}, {"slug": ""},
            {"slug": "test/hidden"}, {"slug": "attachments/hidden"},
            {"slug": ".raw/hidden"}, {"title": None}, {"type": True},
            {"chunk_text": ["rewritten"]}, {"score": True},
        )
        for change in changes:
            fixture = _fixture()
            _bind_rows(fixture[0]["results"][0], [_row(**change)])
            with self.subTest(change=change):
                self._reject(fixture)

    def test_score_binary64_bytes_are_finite_complete_and_match_numeric_score(self):
        for encoded in (b"", struct.pack("<f", 0.75),
                        struct.pack("<d", 0.5), struct.pack("<d", float("inf")),
                        struct.pack("<d", float("nan"))):
            fixture = _fixture()
            _bind_rows(fixture[0]["results"][0], [
                _row(score_f64le_base64=_b64(encoded))])
            with self.subTest(encoded=encoded.hex()):
                self._reject(fixture)

    def test_row_order_and_unique_page_chunk_slug_identities_are_preserved(self):
        base = _row()
        next_row = _row(slug="events/audio/later", page_id=2, chunk_id=2)
        bad_rows = (
            [base, base],
            [base, {**next_row, "page_id": base["page_id"]}],
            [base, {**next_row, "chunk_id": base["chunk_id"]}],
            [next_row, base],
            [_row(score=0.5, score_f64le_base64=_b64(struct.pack("<d", 0.5))),
             next_row],
        )
        for rows in bad_rows:
            fixture = _fixture()
            _bind_rows(fixture[0]["results"][0], rows)
            with self.subTest(rows=rows):
                self._reject(fixture)
        fixture = _fixture()
        _bind_rows(fixture[0]["results"][0], [base, next_row])
        self.assertEqual(self._admit(fixture), fixture[0])

    def test_requested_row_limit_and_text_byte_budgets_are_enforced(self):
        fixture = _fixture()
        fixture[1]["limit"] = 1
        _bind_rows(fixture[0]["results"][0], [
            _row(), _row(slug="events/audio/later", page_id=2, chunk_id=2)])
        self._reject(fixture)
        # JACKAL status=exact: parsed=1024+1 exact=1025;
        # parsed=4096+1 exact=4097; parsed=128+1 exact=129.
        # Exact rational arithmetic (not yet checker-covered), not formal-bounded.
        for field, text in (("slug", "s" * 1025), ("title", "t" * 4097),
                            ("type", "t" * 129),
                            ("chunk_text", "é" * 65536)):
            fixture = _fixture()
            _bind_rows(fixture[0]["results"][0], [_row(**{field: text})])
            with self.subTest(field=field):
                self._reject(fixture)

    def test_empty_ranked_rows_remain_empty_without_an_absence_claim(self):
        fixture = _fixture()
        for result in fixture[0]["results"]:
            _bind_rows(result, [])
        admitted = self._admit(fixture)
        self.assertEqual(admitted, fixture[0])
        self.assertEqual(admitted["non_claims"], NON_CLAIMS)

    def test_latencies_are_finite_nonnegative_numbers_with_exact_rosters(self):
        for bad in (True, "0", -1, float("inf"), float("nan")):
            fixture = _fixture()
            fixture[0]["latency_ms"]["total"] = bad
            with self.subTest(bad=repr(bad)), self.assertRaises(self.refusal):
                self._admit(fixture)
            fixture = _fixture()
            fixture[0]["results"][0]["latency_ms"]["search"] = bad
            with self.subTest(stage_bad=repr(bad)), self.assertRaises(self.refusal):
                self._admit(fixture)
        fixture = _fixture()
        fixture[0]["results"][0]["latency_ms"]["search"] = 1
        self._reject(fixture)

    def test_nonclaims_cannot_be_removed_extended_reworded_or_type_confused(self):
        for bad in (None, "", [], NON_CLAIMS[:-1],
                    [*NON_CLAIMS, "A cognitive win is established."],
                    ["All model weights are attested.", *NON_CLAIMS[1:]]):
            fixture = _fixture()
            fixture[0]["non_claims"] = bad
            with self.subTest(bad=bad):
                self._reject(fixture)

    def test_adapter_refusal_preserves_named_reason_without_returning_rows(self):
        fixture = _fixture()
        refused = {"v": 1, "status": "refused", "lane": "raw_vector",
                   "reason": "snapshot-identity-mismatch",
                   "non_claims": list(NON_CLAIMS)}
        with self.assertRaisesRegex(
                self.refusal, "snapshot-identity-mismatch") as raised:
            self._admit((refused, fixture[1], fixture[2]))
        self.assertEqual(raised.exception.reason, "snapshot-identity-mismatch")
        self.assertEqual(list(raised.exception.non_claims), NON_CLAIMS)
        refused["results"] = fixture[0]["results"]
        self._reject((refused, fixture[1], fixture[2]))


class RawVectorRequestAdmission(unittest.TestCase):
    def setUp(self):
        self.admission = importlib.import_module("siavectoradmit")
        self.refusal = importlib.import_module("siavector").VectorRefusal
        self.assertTrue(callable(getattr(self.admission, "admit_request", None)),
                        "public request admission must exist before any launch")

    def _refuse_before_serialization(self, request):
        before = copy.deepcopy(request)
        with mock.patch.object(
                self.admission, "_canonical_bytes",
                side_effect=AssertionError("unbounded input reached serialization")), \
                mock.patch.object(
                    self.admission.copy, "deepcopy",
                    side_effect=AssertionError("unbounded input reached copying")), \
                self.assertRaises(self.refusal):
            self.admission.admit_request(request)
        self.assertEqual(request, before)

    def test_valid_capture_and_query_requests_are_detached_after_admission(self):
        for operation in ("capture", "query"):
            request = _fixture(operation)[1]
            before = copy.deepcopy(request)
            with self.subTest(operation=operation):
                admitted = self.admission.admit_request(request)
                self.assertEqual(admitted, request)
                self.assertIsNot(admitted, request)
                self.assertIsNone(admitted["snapshot"]["fd"])
                admitted["embedding"]["model"] = "changed detached copy"
                admitted["queries"].clear()
                self.assertEqual(request, before)

    def test_wrong_top_level_and_nested_shapes_refuse_before_serialization(self):
        for request in (None, [], True, "request", 0):
            with self.subTest(request=request):
                self._refuse_before_serialization(request)
        cases = []
        for path, bad in ((("queries",), {}), (("queries", 0), []),
                          (("queries", 0, "text"), {"nested": ["unbounded"]}),
                          (("embedding",), []), (("snapshot",), "snapshot"),
                          (("binding",), None)):
            request = _fixture()[1]
            target = request
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = bad
            cases.append(request)
        extra = _fixture()[1]
        extra["unexpected"] = {"nested": ["not an admitted field"]}
        cases.append(extra)
        missing = _fixture()[1]
        del missing["embedding"]
        cases.append(missing)
        for request in cases:
            with self.subTest(request=request):
                self._refuse_before_serialization(request)

    def test_boolean_nonfinite_and_string_numeric_fields_refuse_before_serialization(self):
        for path in (("v",), ("limit",), ("embedding", "dimensions"),
                     ("snapshot", "fd")):
            for bad in (True, False, float("inf"), "1", 0):
                request = _fixture()[1]
                target = request
                for part in path[:-1]:
                    target = target[part]
                target[path[-1]] = bad
                with self.subTest(path=path, bad=bad):
                    self._refuse_before_serialization(request)

    def test_query_count_and_per_query_byte_limits_precede_serialization(self):
        # JACKAL status=exact parsed=64+1 exact=65;
        # status=exact parsed=8000+1 exact=8001. Exact rational arithmetic
        # (not yet checker-covered), not formal-bounded.
        request = _fixture()[1]
        request["queries"] = [{"id": f"query-{index}", "text": "bounded"}
                              for index in range(65)]
        self._refuse_before_serialization(request)
        for text in ("x" * 8001, "é" * 8000):
            request = _fixture()[1]
            request["queries"][0]["text"] = text
            self._refuse_before_serialization(request)

    def test_exact_ascii_and_unicode_query_byte_boundaries_are_preserved(self):
        # JACKAL status=exact parsed=8000/2 exact=4000; exact rational
        # arithmetic (not yet checker-covered), not formal-bounded.
        for text in ("x" * 8000, "é" * 4000):
            request = _fixture()[1]
            request["queries"] = [{"id": "boundary", "text": text}]
            with self.subTest(kind=text[0]):
                self.assertEqual(len(text.encode("utf-8")), 8000)
                admitted = self.admission.admit_request(request)
                self.assertEqual(admitted["queries"][0]["text"], text)
                request["queries"][0]["text"] = text + "x"
                self._refuse_before_serialization(request)

    def test_combined_request_budget_refuses_without_mutating_admitted_fields(self):
        request = _fixture()[1]
        request["queries"] = [{"id": f"query-{index}", "text": "x" * 8000}
                              for index in range(64)]
        before = copy.deepcopy(request)
        with self.assertRaisesRegex(self.refusal, "byte ceiling"):
            self.admission.admit_request(request)
        self.assertEqual(request, before)

    def test_request_operation_identity_and_query_text_contracts_precede_serialization(self):
        cases = []
        for path, bad in (
                (("operation",), "search"), (("lane",), "hybrid_query"),
                (("queries", 0, "id"), "ambiguous/id"),
                (("queries", 0, "text"), " \t\n"),
                (("queries", 0, "text"), "surrogate\ud800"),
                (("snapshot", "logical_sha256"), None),
                (("binding", "executable_sha256"), "unbound"),
                (("embedding", "endpoint"), "https://remote.example/v1"),
                (("embedding", "model"), "unqualified-model")):
            request = _fixture()[1]
            target = request
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = bad
            cases.append(request)
        duplicate = _fixture()[1]
        duplicate["queries"][1]["id"] = duplicate["queries"][0]["id"]
        cases.append(duplicate)
        capture_with_queries = _fixture()[1]
        capture_with_queries["operation"] = "capture"
        cases.append(capture_with_queries)
        query_without_queries = _fixture()[1]
        query_without_queries["queries"] = []
        cases.append(query_without_queries)
        for request in cases:
            with self.subTest(request=request):
                self._refuse_before_serialization(request)


if __name__ == "__main__":
    unittest.main()
