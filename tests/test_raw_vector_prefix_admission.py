"""Synthetic v2 parent admission: prefix input is never original source text.

JACKAL-first boundary: status=exact,
parsed=(8000-(1+1+1+1+1+1+1+1+1+1+1+1+1+1))/2, exact=3993.
non_claims: NOT formal-bounded: this lane carries no Lean-checked certificate;
The epistemic class above is the STRONGEST claim this result supports;
exact rational arithmetic (not yet checker-covered). This does not prove code.
"""

import copy
import importlib
import unittest
from unittest import mock

from tests import test_raw_vector_admission as raw
from tests import test_raw_vector_prepare_admission as prep

EMBEDDING_INPUT_NON_CLAIMS = [
    "Embedding input prefixes affect only provider input; original query, page and chunk text identities are retained.",
    "Embedding-input digests bind adapter-supplied UTF-8 text, not an independently observed HTTP body or proof of model computation.",
]


def policy(mode="nomic-prefix-v1"):
    return {"schema": "sia-embedding-input-policy-v1", "mode": mode,
            "document_prefix": "" if mode == "bare-v1" else "search_document: ",
            "query_prefix": "" if mode == "bare-v1" else "search_query: ",
            "encoding": "utf-8", "document_stage": "after-lossless-chunking",
            "query_stage": "original-query", "overflow": "refuse"}


def configuration(embedding, limit, input_policy):
    """Independent frozen config oracle, not a response-derived expectation."""
    return {"engine": "pglite", "embedding": copy.deepcopy(embedding),
            "search": {"limit": limit, "offset": 0, "sourceId": "sia", "detail": "high",
                       "exclude_slug_prefixes": ["test/", "attachments/", ".raw/"],
                       "include_slug_prefixes": [], "excludePrivate": False,
                       "embeddingColumn": {"name": "embedding", "type": "vector",
                                           "dimensions": embedding["dimensions"],
                                           "embeddingModel": embedding["model"]}},
            "env": {"GBRAIN_SEARCH_EXCLUDE": "", "GBRAIN_SOURCE_BOOST": "",
                    "GBRAIN_PGLITE_WAL_REPAIR": "off", "TZ": "UTC"},
            "embedding_input_policy": copy.deepcopy(input_policy),
            "embedding_input_policy_sha256": raw._sha(raw._json(input_policy))}


def query_fixture(mode="nomic-prefix-v1", operation="query"):
    payload, request, expected = raw._fixture(operation)
    request["v"] = payload["v"] = 2
    request["embedding"] = {"model": "ollama:nomic-embed-text:v1.5", "dimensions": 3,
                            "endpoint": "http://127.0.0.1:11434/v1"}
    request["embedding_input_policy"] = policy(mode)
    digest = raw._sha(raw._json(request["embedding_input_policy"]))
    request["embedding_input_policy_sha256"] = digest
    payload["embedding_input_policy"] = policy(mode)
    payload["bindings"]["embedding_input_policy_sha256"] = digest
    payload["non_claims"] += list(EMBEDDING_INPUT_NON_CLAIMS)
    if operation == "query":
        request["queries"][0]["text"] = "search_query: original é\n"
    for source, row in zip(request["queries"], payload["results"]):
        text = source["text"].encode("utf-8")
        encoded = (request["embedding_input_policy"]["query_prefix"] + source["text"]).encode("utf-8")
        row.update(query_sha256=raw._sha(text), embedding_input_sha256=raw._sha(encoded),
                   embedding_input_bytes=len(encoded))
    expected["config_sha256"] = raw._sha(raw._json(configuration(
        request["embedding"], request["limit"], request["embedding_input_policy"])))
    sealed = copy.deepcopy(request)
    sealed["snapshot"]["fd"] = 9
    expected["request_sha256"] = raw._sha(raw._json(sealed))
    payload["bindings"].update(expected)
    return payload, request, expected


def prepare_fixture(mode="nomic-prefix-v1"):
    payload, request, expected = prep._fixture()
    request["v"] = payload["v"] = 2
    request["embedding"] = {"model": "ollama:nomic-embed-text:v1.5", "dimensions": 3,
                            "endpoint": "http://127.0.0.1:11434/v1"}
    request["embedding_input_policy"] = policy(mode)
    digest = raw._sha(raw._json(request["embedding_input_policy"]))
    request["embedding_input_policy_sha256"] = digest
    payload["embedding_input_policy"] = policy(mode)
    payload["bindings"]["embedding_input_policy_sha256"] = digest
    payload["embedding"] = copy.deepcopy(request["embedding"])
    payload["bindings"]["embedding_sha256"] = raw._sha(raw._json(request["embedding"]))
    payload["non_claims"] += list(EMBEDDING_INPUT_NON_CLAIMS)
    for page, receipt in zip(request["pages"], payload["pages"]):
        for original, witness in zip(prep._chunks(page["text"]), receipt["chunks"]):
            encoded = (request["embedding_input_policy"]["document_prefix"] + original).encode("utf-8")
            witness.update(embedding_input_sha256=raw._sha(encoded), embedding_input_bytes=len(encoded))
    sealed = copy.deepcopy(request)
    sealed["output"]["parent_fd"] = 9
    expected["request_sha256"] = raw._sha(raw._json(sealed))
    payload["bindings"].update(expected)
    return payload, request, expected


class PrefixAdmission(unittest.TestCase):
    def setUp(self):
        self.raw = importlib.import_module("siavectoradmit")
        self.prep = importlib.import_module("siavectorprepare")
        self.refusal = importlib.import_module("siavector").VectorRefusal

    def _admit(self, module, fixture):
        payload, request, expectations = fixture
        return module.admit_response(payload, request, **expectations)

    def test_v2_raw_capture_and_query_are_detached_complete_and_policy_bound(self):
        for mode in ("bare-v1", "nomic-prefix-v1"):
            for operation in ("capture", "query"):
                with self.subTest(mode=mode, operation=operation):
                    fixture = query_fixture(mode, operation)
                    before = copy.deepcopy(fixture)
                    self.assertEqual(self.raw.admit_request(fixture[1]), fixture[1])
                    admitted = self._admit(self.raw, fixture)
                    self.assertEqual(admitted, fixture[0])
                    admitted["embedding_input_policy"]["mode"] = "changed caller copy"
                    admitted["non_claims"].clear()
                    self.assertEqual(fixture, before)

    def test_v2_preparation_retains_original_pages_origins_chunks_and_diagnostics(self):
        for mode in ("bare-v1", "nomic-prefix-v1"):
            fixture = prepare_fixture(mode)
            before = copy.deepcopy(fixture)
            self.assertEqual(self.prep.admit_request(fixture[1]), fixture[1])
            admitted = self._admit(self.prep, fixture)
            self.assertEqual(admitted, fixture[0])
            admitted["pages"][0]["chunks"].clear()
            admitted["setup_diagnostics"]["non_claims"].clear()
            self.assertEqual(fixture, before)

    def test_v1_complete_payloads_still_admit_without_new_policy_fields(self):
        for module, fixture in ((self.raw, raw._fixture()), (self.prep, prep._fixture())):
            self.assertEqual(self._admit(module, fixture), fixture[0])
            self.assertNotIn("embedding_input_policy", fixture[0])

    def test_query_utf8_combined_cap_and_literal_original_prefix_are_not_rewritten(self):
        request = query_fixture()[1]
        request["queries"][0]["text"] = "é" * 3993
        self.assertEqual(len(("search_query: " + request["queries"][0]["text"]).encode("utf-8")), 8000)
        self.assertEqual(self.raw.admit_request(request), request)
        request["queries"][0]["text"] += "é"
        with mock.patch.object(self.raw.copy, "deepcopy", side_effect=AssertionError("copied before byte admission")):
            with self.assertRaises(self.refusal):
                self.raw.admit_request(request)
        fixture = query_fixture()
        admitted = self._admit(self.raw, fixture)
        self.assertEqual(admitted["results"][0]["query_sha256"], raw._sha(b"search_query: original \xc3\xa9\n"))
        self.assertEqual(admitted["results"][0]["embedding_input_sha256"],
                         raw._sha(b"search_query: search_query: original \xc3\xa9\n"))

    def test_closed_policy_rejects_self_consistent_foreign_transforms_before_copy(self):
        for module, factory in ((self.raw, query_fixture), (self.prep, prepare_fixture)):
            for key, value in (("mode", "auto"), ("document_prefix", "search_document:"),
                               ("query_prefix", " search_query: "), ("encoding", "utf-16"),
                               ("overflow", "truncate"), ("document_stage", "before-chunking"),
                               ("query_stage", "normalized-query"), ("unknown", True)):
                request = factory()[1]
                request["embedding_input_policy"][key] = value
                request["embedding_input_policy_sha256"] = raw._sha(raw._json(request["embedding_input_policy"]))
                with self.subTest(module=module.__name__, key=key), \
                        mock.patch.object(module.copy, "deepcopy", side_effect=AssertionError("copied invalid policy")):
                    with self.assertRaises(self.refusal):
                        module.admit_request(request)
            for key in ("embedding_input_policy", "embedding_input_policy_sha256"):
                request = factory()[1]
                del request[key]
                with self.assertRaises(self.refusal): module.admit_request(request)
            request = factory()[1]
            request["embedding"]["model"] = "ollama:other"
            with self.assertRaises(self.refusal): module.admit_request(request)

    def test_response_policy_cannot_authorize_itself_against_caller_request(self):
        for module, factory in ((self.raw, query_fixture), (self.prep, prepare_fixture)):
            fixture = factory()
            fixture[0]["embedding_input_policy"] = policy("bare-v1")
            fixture[0]["bindings"]["embedding_input_policy_sha256"] = raw._sha(raw._json(policy("bare-v1")))
            with self.assertRaises(self.refusal): self._admit(module, fixture)
            fixture = factory()
            fixture[0]["bindings"]["embedding_input_policy_sha256"] = raw._sha(b"foreign policy")
            with self.assertRaises(self.refusal): self._admit(module, fixture)

    def test_every_query_input_witness_uses_original_bytes_plus_declared_prefix(self):
        for field, value in (("embedding_input_sha256", raw._sha(b"unprefixed or unrelated")),
                             ("embedding_input_bytes", True), ("embedding_input_bytes", 0),
                             ("query_sha256", raw._sha(b"prefixed source masquerading as original"))):
            fixture = query_fixture()
            fixture[0]["results"][0][field] = value
            with self.subTest(field=field), self.assertRaises(self.refusal): self._admit(self.raw, fixture)
        for field in ("embedding_input_sha256", "embedding_input_bytes"):
            fixture = query_fixture()
            del fixture[0]["results"][0][field]
            with self.assertRaises(self.refusal): self._admit(self.raw, fixture)

    def test_every_document_input_witness_uses_unchanged_complete_original_chunk_roster(self):
        for field, value in (("embedding_input_sha256", raw._sha(b"unrelated")),
                             ("embedding_input_bytes", True), ("embedding_input_bytes", 0),
                             ("text_sha256", raw._sha(b"prefixed content")),
                             ("vector_sha256", "not-a-vector-digest")):
            fixture = prepare_fixture()
            fixture[0]["pages"][0]["chunks"][0][field] = value
            with self.subTest(field=field), self.assertRaises(self.refusal): self._admit(self.prep, fixture)
        for change in ("omit", "origin", "order"):
            fixture = prepare_fixture()
            if change == "omit": fixture[0]["pages"][0]["chunks"].pop()
            elif change == "origin": fixture[0]["pages"][0]["origin"] = "model"
            else: fixture[0]["pages"][0]["chunks"].reverse()
            with self.assertRaises(self.refusal): self._admit(self.prep, fixture)

    def test_vector_digest_roster_is_not_independent_vector_reconstruction(self):
        fixture = prepare_fixture()
        fixture[0]["pages"][0]["chunks"][0]["vector_sha256"] = raw._sha(b"another producer-reported vector")
        self.assertEqual(self._admit(self.prep, fixture), fixture[0])

    def test_complete_original_and_prefix_nonclaims_cannot_be_removed_or_promoted(self):
        for module, factory in ((self.raw, query_fixture), (self.prep, prepare_fixture)):
            for action in ("drop-original", "drop-prefix", "replace-prefix"):
                fixture = factory()
                if action == "drop-original": fixture[0]["non_claims"].pop(0)
                elif action == "drop-prefix": fixture[0]["non_claims"].pop()
                else: fixture[0]["non_claims"][-1] = "Independent proof of model input."
                with self.assertRaises(self.refusal): self._admit(module, fixture)

    def test_named_v2_refusals_retain_boundaries_without_becoming_success(self):
        for module, factory, exception in ((self.raw, query_fixture, self.raw.AdapterRefusal),
                                           (self.prep, prepare_fixture, self.prep.PreparationRefusal)):
            complete, request, expected = factory()
            refused = {"v": 2, "status": "refused", "operation": request["operation"],
                       "reason": "embedding-input-policy-mismatch", "non_claims": complete["non_claims"]}
            if module is self.raw: refused["lane"] = "raw_vector"
            with self.assertRaises(exception) as caught:
                self._admit(module, (refused, request, expected))
            self.assertEqual(caught.exception.reason, "embedding-input-policy-mismatch")
            self.assertEqual(list(caught.exception.non_claims), complete["non_claims"])


if __name__ == "__main__":
    unittest.main()
