"""Parent admission checks the frozen preparer's receipt against caller inputs."""

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

NON_CLAIMS = [
    "Origin labels are retained from the supplied frozen export; this preparer does not independently attest its source evidence.",
    "This is a new benchmark projection of exported pages, not a copy or attestation of the resident index.",
    "The provider model identifier and endpoint are bound; the parent must separately attest served model weights.",
    "Preparation timestamps are index-construction metadata, not the original event times.",
    "Lossless deterministic chunking is a declared benchmark policy, not a cognitive mechanism or a demonstrated retrieval improvement.",
    "Failure can leave a partial private index; it is never reported as an admitted completed snapshot.",
]
DIAGNOSTIC_NON_CLAIMS = [
    "Captured setup diagnostics are informational output, not proof of schema or data correctness.",
    "When truncated is true, text/base64 and sha256 describe only the retained prefix, not the complete diagnostic stream.",
]
POLICY = {"chunking": "utf8-contiguous-codepoint-v1", "max_chunk_bytes": 2048,
          "source": "sia", "chunk_source": "compiled_truth", "input_type": "document"}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _chunks(text):
    """Independent byte-slicing oracle, unlike the producer's codepoint loop."""
    encoded = text.encode("utf-8")
    result = []
    start = 0
    while start < len(encoded):
        end = min(start + 2048, len(encoded))
        while True:
            try:
                part = encoded[start:end].decode("utf-8", "strict")
                break
            except UnicodeDecodeError:
                end -= 1
        result.append(part)
        start = end
    return result


def _diagnostics(text=None, **changes):
    if text is None:
        text = ("  Setting up brain schema (v144)...\n"
                "  v142: takes.embedding resized to vector(3); existing take vectors cleared\n"
                "  139 migration(s) applied\n")
    encoded = text.encode("utf-8")
    result = {"source": "gbrain.initSchema/process.stderr", "classification": "known-setup-diagnostics",
              "text": text, "utf8_base64": base64.b64encode(encoded).decode("ascii"),
              "sha256": _sha(encoded), "bytes_seen": len(encoded), "truncated": False,
              "non_claims": list(DIAGNOSTIC_NON_CLAIMS)}
    result.update(changes)
    return result


def _fixture():
    pages = [
        {"slug": "events/audio/repair", "title": "Audio — repair", "type": "event-day", "origin": "evidence",
         "text": "[origin:evidence]\nLeading whitespace retained.\n" + "é漢😀 " * 400 + "\nlast\n"},
        {"slug": "thoughts/a-note", "title": "An attributed note", "type": "thought", "origin": "model",
         "text": "[origin:model]\nThis is model-origin prose.\n"},
    ]
    for page in pages:
        page["text_sha256"] = _sha(page["text"].encode("utf-8"))
    request = {"v": 1, "operation": "prepare_index", "source": "sia", "dataset_sha256": _sha(b"frozen source dataset"),
               "pages_sha256": _sha(_json(pages)), "embedding": {"model": "llama-server:private-fixture", "dimensions": 3,
               "endpoint": "http://127.0.0.1:8080/v1"}, "output": {"parent_fd": None}, "pages": pages}
    sealed = copy.deepcopy(request)
    sealed["output"]["parent_fd"] = 9
    expected = {"request_sha256": _sha(_json(sealed))}
    payload = {"v": 1, "status": "ok", "operation": "prepare_index", "index_leaf": "index",
               "bindings": {"dataset_sha256": request["dataset_sha256"], "pages_sha256": request["pages_sha256"],
               "request_sha256": expected["request_sha256"], "policy_sha256": _sha(_json(POLICY)),
               "embedding_sha256": _sha(_json(request["embedding"]))}, "policy": copy.deepcopy(POLICY),
               "embedding": copy.deepcopy(request["embedding"]), "pages": [], "setup_diagnostics": _diagnostics(),
               "non_claims": list(NON_CLAIMS)}
    for page in pages:
        receipts = [{"chunk_index": index, "text_sha256": _sha(chunk.encode("utf-8")),
                     "vector_sha256": _sha(struct.pack("<fff", 1.0, 0.0, 0.0)), "bytes": len(chunk.encode("utf-8"))}
                    for index, chunk in enumerate(_chunks(page["text"]))]
        payload["pages"].append({"slug": page["slug"], "origin": page["origin"],
                                 "text_sha256": page["text_sha256"], "chunks": receipts})
    return payload, request, expected


class RawVectorPrepareAdmission(unittest.TestCase):
    def setUp(self):
        try:
            self.admission = importlib.import_module("siavectorprepare")
        except ModuleNotFoundError as exc:
            self.fail(f"preparer request/response admission must exist: {exc}")
        self.refusal = importlib.import_module("siavector").VectorRefusal

    def _admit(self, fixture):
        payload, request, expected = fixture
        return self.admission.admit_response(payload, request, **expected)

    def _reject(self, fixture):
        before = copy.deepcopy(fixture)
        with self.assertRaises(self.refusal):
            self._admit(fixture)
        self.assertEqual(fixture, before, "admission must not repair caller inputs")

    def test_complete_unicode_receipt_is_detached_and_every_boundary_is_retained(self):
        fixture = _fixture()
        before = copy.deepcopy(fixture)
        admitted = self._admit(fixture)
        self.assertEqual(admitted, fixture[0])
        self.assertIsNot(admitted, fixture[0])
        admitted["pages"][0]["chunks"].clear()
        admitted["setup_diagnostics"]["non_claims"].clear()
        self.assertEqual(fixture, before)

    def test_request_admission_detaches_original_pages_without_inventing_descriptor(self):
        request = _fixture()[1]
        admitted = self.admission.admit_request(request)
        self.assertEqual(admitted, request)
        self.assertIsNone(admitted["output"]["parent_fd"])
        admitted["pages"][0]["text"] = "changed by caller"
        self.assertNotEqual(admitted, request)

    def test_request_shapes_labels_hashes_and_budgets_precede_copying_and_serialization(self):
        mutations = [
            ((), "unexpected", "answer-key"), (("output",), "parent_fd", True),
            (("embedding",), "dimensions", True), (("embedding",), "endpoint", "http://remote.example:8080/v1"),
            (("embedding",), "endpoint", "http://127.0.0.1:08080/v1"),
            (("pages", 0), "origin", "verified"), (("pages", 0), "slug", "events/Audio"),
            (("pages", 0), "text_sha256", _sha(b"wrong")),
            (("pages", 0), "text", "x" * 131073), (("pages", 0), "text", "unpaired\ud800"),
            (("pages", 0), "text", "null\0byte"), ((), "pages_sha256", _sha(b"different roster")),
        ]
        for path, key, value in mutations:
            request = _fixture()[1]
            target = request
            for part in path:
                target = target[part]
            target[key] = value
            with self.subTest(path=path, key=key):
                with mock.patch.object(self.admission.copy, "deepcopy", side_effect=AssertionError("copied invalid request")):
                    with self.assertRaises(self.refusal):
                        self.admission.admit_request(request)
        for pages in ([], [_fixture()[1]["pages"][0]] * 257):
            request = _fixture()[1]
            request["pages"] = pages
            with self.assertRaises(self.refusal):
                self.admission.admit_request(request)

    def test_complete_request_roster_cannot_contain_duplicate_slugs(self):
        request = _fixture()[1]
        request["pages"].append(copy.deepcopy(request["pages"][0]))
        request["pages_sha256"] = _sha(_json(request["pages"]))
        with self.assertRaises(self.refusal):
            self.admission.admit_request(request)

    def test_response_envelopes_and_nested_rosters_are_exact(self):
        paths = ((), ("bindings",), ("policy",), ("embedding",), ("pages", 0),
                 ("pages", 0, "chunks", 0), ("setup_diagnostics",))
        for path in paths:
            for action in ("extra", "missing"):
                fixture = _fixture()
                target = fixture[0]
                for part in path:
                    target = target[part]
                if action == "extra":
                    target["unexpected"] = "unadmitted"
                else:
                    del target[next(iter(target))]
                with self.subTest(path=path, action=action):
                    self._reject(fixture)

    def test_status_version_operation_leaf_and_scalar_types_are_exact(self):
        for path, key, value in [
            ((), "v", True), ((), "v", 1.0), ((), "status", "observed"), ((), "operation", "query"),
            ((), "index_leaf", "../index"), (("policy",), "max_chunk_bytes", True),
            (("embedding",), "dimensions", 3.0), (("pages", 0, "chunks", 0), "chunk_index", False),
            (("pages", 0, "chunks", 0), "bytes", True), (("setup_diagnostics",), "bytes_seen", True),
            (("setup_diagnostics",), "truncated", 0),
        ]:
            fixture = _fixture()
            target = fixture[0]
            for part in path:
                target = target[part]
            target[key] = value
            with self.subTest(path=path, key=key):
                self._reject(fixture)

    def test_all_identity_expectations_come_from_caller_not_response(self):
        for binding in _fixture()[0]["bindings"]:
            fixture = _fixture()
            fixture[0]["bindings"][binding] = _sha(b"self-consistent unrelated identity")
            with self.subTest(binding=binding):
                self._reject(fixture)
        fixture = _fixture()
        fixture[0]["embedding"]["model"] = "llama-server:other"
        fixture[0]["bindings"]["embedding_sha256"] = _sha(_json(fixture[0]["embedding"]))
        self._reject(fixture)
        fixture = _fixture()
        fixture[0]["policy"]["max_chunk_bytes"] = 1024
        fixture[0]["bindings"]["policy_sha256"] = _sha(_json(fixture[0]["policy"]))
        self._reject(fixture)
        fixture = _fixture()
        fixture[2]["request_sha256"] = "not-a-digest"
        self._reject(fixture)

    def test_page_roster_cannot_omit_add_reorder_duplicate_or_relabel_sources(self):
        for action in ("omit", "add", "reverse", "duplicate", "slug", "origin", "text"):
            fixture = _fixture()
            pages = fixture[0]["pages"]
            if action == "omit": pages.pop()
            elif action == "add": pages.append(copy.deepcopy(pages[-1]))
            elif action == "reverse": pages.reverse()
            elif action == "duplicate": pages[-1] = copy.deepcopy(pages[0])
            elif action == "slug": pages[0]["slug"] = "events/unrelated"
            elif action == "origin": pages[0]["origin"] = "model"
            else: pages[0]["text_sha256"] = _sha(b"rewritten text")
            with self.subTest(action=action): self._reject(fixture)

    def test_chunk_witnesses_cover_exact_contiguous_original_bytes_in_order(self):
        for action in ("omit", "add", "reverse", "index", "bytes", "text", "vector"):
            fixture = _fixture()
            chunks = fixture[0]["pages"][0]["chunks"]
            if action == "omit": chunks.pop()
            elif action == "add": chunks.append(copy.deepcopy(chunks[-1]))
            elif action == "reverse": chunks.reverse()
            elif action == "index": chunks[0]["chunk_index"] = 1
            elif action == "bytes": chunks[0]["bytes"] = 1
            elif action == "text": chunks[0]["text_sha256"] = _sha(b"truncated or rewritten chunk")
            else: chunks[0]["vector_sha256"] = "unwitnessed"
            with self.subTest(action=action): self._reject(fixture)

    def test_vector_witness_digests_are_complete_without_claiming_independent_reconstruction(self):
        fixture = _fixture()
        fixture[0]["pages"][0]["chunks"][0]["vector_sha256"] = _sha(b"a different observed vector")
        self.assertEqual(self._admit(fixture), fixture[0])
        for value in (None, True, "A" * 64, "a" * 63, "a" * 65):
            fixture = _fixture()
            fixture[0]["pages"][0]["chunks"][0]["vector_sha256"] = value
            with self.subTest(value=value): self._reject(fixture)

    def test_success_diagnostics_must_be_complete_known_correctly_hashed_original_bytes(self):
        changes = [
            {"classification": "schema-initialization-failed"}, {"source": "operator"}, {"truncated": True},
            {"text": "different bytes"}, {"sha256": _sha(b"different")}, {"bytes_seen": 0},
            {"utf8_base64": "%%%"}, {"non_claims": []},
        ]
        for change in changes:
            fixture = _fixture()
            fixture[0]["setup_diagnostics"].update(change)
            with self.subTest(change=change): self._reject(fixture)
        for text in ("ERROR: partial schema\n", "  v142: takes.embedding resized to vector(4); existing take vectors cleared\n"):
            fixture = _fixture()
            fixture[0]["setup_diagnostics"] = _diagnostics(text)
            self._reject(fixture)

    def test_success_cannot_drop_or_rewrite_any_nonclaim(self):
        for keypath in (("non_claims",), ("setup_diagnostics", "non_claims")):
            for action in ("missing", "rewrite", "duplicate"):
                fixture = _fixture()
                target = fixture[0]
                for key in keypath[:-1]: target = target[key]
                claims = target[keypath[-1]]
                if action == "missing": claims.pop()
                elif action == "rewrite": claims[0] = "A stronger assertion"
                else: claims.append(claims[0])
                with self.subTest(path=keypath, action=action): self._reject(fixture)

    def test_named_refusal_retains_its_diagnostics_and_nonclaims_without_becoming_success(self):
        _, request, expected = _fixture()
        payload = {"v": 1, "status": "refused", "operation": "prepare_index",
                   "reason": "setup-diagnostics-unrecognized", "non_claims": list(NON_CLAIMS),
                   "setup_diagnostics": _diagnostics("ERROR: migration failed\n", classification="unrecognized-setup-diagnostics")}
        with self.assertRaises(self.admission.PreparationRefusal) as caught:
            self.admission.admit_response(payload, request, **expected)
        self.assertEqual(caught.exception.reason, payload["reason"])
        self.assertEqual(list(caught.exception.non_claims), NON_CLAIMS)
        self.assertEqual(caught.exception.setup_diagnostics, payload["setup_diagnostics"])
        caught.exception.setup_diagnostics["text"] = "changed caller copy"
        self.assertEqual(payload["setup_diagnostics"]["text"], "ERROR: migration failed\n")
        payload["pages"] = _fixture()[0]["pages"]
        with self.assertRaises(self.refusal):
            self.admission.admit_response(payload, request, **expected)

    def test_refused_truncated_diagnostics_describe_only_retained_prefix(self):
        _, request, expected = _fixture()
        prefix = "x" * 65536
        payload = {"v": 1, "status": "refused", "operation": "prepare_index",
                   "reason": "setup-diagnostics-byte-budget", "non_claims": list(NON_CLAIMS),
                   "setup_diagnostics": _diagnostics(prefix, classification="setup-diagnostics-byte-budget",
                                                      truncated=True, bytes_seen=65537)}
        with self.assertRaises(self.admission.PreparationRefusal) as caught:
            self.admission.admit_response(payload, request, **expected)
        self.assertEqual(caught.exception.setup_diagnostics["text"], prefix)
        self.assertTrue(caught.exception.setup_diagnostics["truncated"])
        payload["setup_diagnostics"]["sha256"] = _sha(b"invented full-stream digest")
        with self.assertRaises(self.refusal):
            self.admission.admit_response(payload, request, **expected)

    def test_wire_decoder_rejects_duplicate_members_nonfinite_numbers_and_oversized_bytes(self):
        payload, request, expected = _fixture()
        encoded = _json(payload)
        self.assertEqual(self.admission.admit_response_bytes(encoded, request, **expected), payload)
        for bad in (encoded.replace(b'"v":1', b'"v":1,"v":1'), b'{"v":NaN}', b'\xff', b'x' * 2097153):
            with self.subTest(prefix=bad[:20]):
                with self.assertRaises(self.refusal):
                    self.admission.admit_response_bytes(bad, request, **expected)


if __name__ == "__main__":
    unittest.main()
