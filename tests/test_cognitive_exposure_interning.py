"""Lossless, closed interning for event-exposure artifacts.

This is a RED construction contract for a representation boundary only.  The
codec may deduplicate repeated represented values, but it may not omit a
source event, query, candidate, exposure occurrence, source hash, nonclaim, or
legacy artifact field.  Canonical JSON bytes are the comparison domain because
the public Python API receives detached JSON values rather than source text.

Only existing synthetic stopped-process fixtures are used.  No model, index,
resident corpus, package manager, network, metric execution, JACKAL call, or
live SIA state is used.  Existing envelope ceilings are reused verbatim; this
module defines no larger capacity and no new assurance class.
"""

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import copy
import importlib
import inspect
import unittest
from unittest import mock

from tests import test_cognitive_event_exposure as exposure_tests
from tests import test_cognitive_fidelity as fidelity_tests


canonical = exposure_tests.canonical
sha = exposure_tests.sha
body_digest = exposure_tests.body_digest

INTERNED_SCHEMA = "sia-cognitive-event-exposure-interned-v1"
INTERNED_FIELDS = {
    "schema", "status", "source_schema", "source_sha256", "root", "tables",
    "artifact_sha256",
}
ROOT_FIELDS = {"value", "source_record_refs", "query_refs"}
TABLES = ("source_records", "queries", "candidates", "occurrences")
PLAIN_ENTRY_FIELDS = {"ref", "sha256", "value"}
QUERY_ENTRY_FIELDS = {*PLAIN_ENTRY_FIELDS, "candidate_refs"}
CANDIDATE_ENTRY_FIELDS = {*PLAIN_ENTRY_FIELDS, "occurrence_refs"}
PREFIXES = {
    "source_records": "source-record:",
    "queries": "query:",
    "candidates": "candidate:",
    "occurrences": "occurrence:",
}


def _reference(table, value):
    digest = sha(canonical(value))
    return PREFIXES[table] + digest, digest


def _append_unique(table, entry, seen):
    if entry["ref"] not in seen[table]:
        seen[table].add(entry["ref"])
        return [entry]
    return []


def expected_interned(source):
    """Spell the complete deterministic wire contract independent of production."""
    tables = {name: [] for name in TABLES}
    seen = {name: set() for name in TABLES}
    source_refs = []
    for record in source["event_population"]:
        reference, digest = _reference("source_records", record)
        source_refs.append(reference)
        tables["source_records"].extend(_append_unique(
            "source_records",
            {"ref": reference, "sha256": digest, "value": copy.deepcopy(record)},
            seen,
        ))

    query_refs = []
    for query in source["queries"]:
        candidate_refs = []
        for candidate in query["candidates"]:
            occurrence_refs = []
            for occurrence in candidate["exposures"]:
                reference, digest = _reference("occurrences", occurrence)
                occurrence_refs.append(reference)
                tables["occurrences"].extend(_append_unique(
                    "occurrences",
                    {"ref": reference, "sha256": digest,
                     "value": copy.deepcopy(occurrence)},
                    seen,
                ))
            reference, digest = _reference("candidates", candidate)
            candidate_refs.append(reference)
            value = {key: copy.deepcopy(item) for key, item in candidate.items()
                     if key != "exposures"}
            tables["candidates"].extend(_append_unique(
                "candidates",
                {"ref": reference, "sha256": digest, "value": value,
                 "occurrence_refs": occurrence_refs},
                seen,
            ))
        reference, digest = _reference("queries", query)
        query_refs.append(reference)
        value = {key: copy.deepcopy(item) for key, item in query.items()
                 if key != "candidates"}
        tables["queries"].extend(_append_unique(
            "queries",
            {"ref": reference, "sha256": digest, "value": value,
             "candidate_refs": candidate_refs},
            seen,
        ))

    root_value = {key: copy.deepcopy(item) for key, item in source.items()
                  if key not in ("event_population", "queries")}
    body = {
        "schema": INTERNED_SCHEMA,
        "status": source["status"],
        "source_schema": source["schema"],
        "source_sha256": sha(canonical(source)),
        "root": {
            "value": root_value,
            "source_record_refs": source_refs,
            "query_refs": query_refs,
        },
        "tables": tables,
    }
    return {**body, "artifact_sha256": sha(canonical(body))}


def _rosters(source):
    candidates = [candidate for query in source["queries"]
                  for candidate in query["candidates"]]
    occurrences = [occurrence for candidate in candidates
                   for occurrence in candidate["exposures"]]
    return {
        "source_records": [canonical(value) for value in source["event_population"]],
        "queries": [canonical(value) for value in source["queries"]],
        "candidates": [canonical(value) for value in candidates],
        "occurrences": [canonical(value) for value in occurrences],
    }


class CognitiveExposureInterning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = exposure_tests.CognitiveEventExposure(methodName="runTest")
        try:
            cls.fx.setUp()
            cls.exposure_module = importlib.import_module("siacognitiveexposure")
            cls.envelope = importlib.import_module("siacognitiveenvelope")
            cls.fx._inputs()
            cls.source = cls.fx._call(cls.exposure_module)
        except BaseException:
            cls.fx.doCleanups()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.fx.doCleanups()

    def _codec(self):
        pack = getattr(self.envelope, "intern_exposure", None)
        expand = getattr(self.envelope, "expand_interned_exposure", None)
        self.assertTrue(callable(pack),
                        "siacognitiveenvelope.intern_exposure must be implemented")
        self.assertTrue(callable(expand),
                        "siacognitiveenvelope.expand_interned_exposure must be implemented")
        return pack, expand

    def _pack(self):
        pack, _expand = self._codec()
        return pack(
            exposure=self.source,
            max_input_bytes=self.envelope.MAX_INPUT_BYTES,
            max_document_bytes=self.envelope.MAX_DOCUMENT_BYTES,
        )

    def _expand(self, packed):
        _pack, expand = self._codec()
        return expand(
            interned=packed,
            max_input_bytes=self.envelope.MAX_INPUT_BYTES,
            max_document_bytes=self.envelope.MAX_DOCUMENT_BYTES,
        )

    def _resign(self, packed):
        packed["artifact_sha256"] = body_digest(packed, "artifact_sha256")
        return packed

    def test_public_codec_seam_is_exact_keyword_only_and_reuses_hard_ceilings(self):
        pack, expand = self._codec()
        expected = {
            "intern_exposure": {"exposure", "max_input_bytes", "max_document_bytes"},
            "expand_interned_exposure": {"interned", "max_input_bytes", "max_document_bytes"},
        }
        for name, target in (("intern_exposure", pack),
                             ("expand_interned_exposure", expand)):
            parameters = inspect.signature(target).parameters
            self.assertEqual(set(parameters), expected[name])
            for parameter in parameters.values():
                self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(parameter.default, inspect.Parameter.empty)
        self.assertEqual(self.envelope.MAX_INPUT_BYTES, 67108864)
        self.assertEqual(self.envelope.MAX_DOCUMENT_BYTES, 16777216)

    def test_wire_form_is_deterministic_content_addressed_and_exactly_versioned(self):
        before = copy.deepcopy(self.source)
        first = self._pack()
        second = self._pack()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertEqual(self.source, before)
        self.assertEqual(first, expected_interned(before))
        self.assertEqual(set(first), INTERNED_FIELDS)
        self.assertEqual(first["schema"], INTERNED_SCHEMA)
        self.assertEqual(first["status"], before["status"])
        self.assertEqual(first["source_schema"], "sia-cognitive-event-exposure-v1")
        self.assertEqual(first["source_sha256"], sha(canonical(before)))
        self.assertEqual(first["artifact_sha256"], body_digest(first, "artifact_sha256"))
        self.assertEqual(set(first["root"]), ROOT_FIELDS)
        self.assertEqual(tuple(first["tables"]), TABLES)
        for table, rows in first["tables"].items():
            expected_fields = PLAIN_ENTRY_FIELDS
            if table == "queries":
                expected_fields = QUERY_ENTRY_FIELDS
            elif table == "candidates":
                expected_fields = CANDIDATE_ENTRY_FIELDS
            refs = [row["ref"] for row in rows]
            self.assertEqual(len(refs), len(set(refs)), table)
            for row in rows:
                self.assertEqual(set(row), expected_fields)
                self.assertEqual(row["ref"], PREFIXES[table] + row["sha256"])

    def test_round_trip_preserves_every_ordered_record_as_canonical_bytes(self):
        packed = self._pack()
        before_packed = copy.deepcopy(packed)
        expanded = self._expand(packed)
        self.assertEqual(packed, before_packed)
        self.assertIsNot(expanded, self.source)
        self.assertEqual(canonical(expanded), canonical(self.source))
        self.assertEqual(_rosters(expanded), _rosters(self.source))
        flattened = _rosters(self.source)["occurrences"]
        pooled = self._pack()["tables"]["occurrences"]
        # The fixture deliberately reuses source occurrences across public
        # query variants; the pool must actually intern those equal bytes.
        self.assertLess(len(pooled), len(flattened))

    def test_decoder_refuses_missing_duplicate_foreign_reordered_and_hash_mismatched_refs(self):
        packed = self._pack()
        source_ref = packed["tables"]["source_records"][0]["ref"]
        candidate = next(row for row in packed["tables"]["candidates"]
                         if row["occurrence_refs"])
        occurrence_ref = candidate["occurrence_refs"][0]

        missing = copy.deepcopy(packed)
        missing["tables"]["occurrences"] = [
            row for row in missing["tables"]["occurrences"]
            if row["ref"] != occurrence_ref
        ]

        duplicate = copy.deepcopy(packed)
        duplicate["tables"]["source_records"].append(
            copy.deepcopy(duplicate["tables"]["source_records"][0]))

        foreign = copy.deepcopy(packed)
        foreign_candidate = next(row for row in foreign["tables"]["candidates"]
                                 if row["occurrence_refs"])
        foreign_candidate["occurrence_refs"][0] = source_ref

        reordered = copy.deepcopy(packed)
        self.assertGreater(len(reordered["root"]["query_refs"]), 1)
        reordered["root"]["query_refs"].reverse()

        hash_mismatch = copy.deepcopy(packed)
        hash_mismatch["tables"]["occurrences"][0]["sha256"] = "0" * 64

        for label, malformed in (
                ("missing", missing), ("duplicate", duplicate),
                ("foreign", foreign), ("reordered", reordered),
                ("hash-mismatched", hash_mismatch)):
            malformed = self._resign(malformed)
            before = copy.deepcopy(malformed)
            with self.subTest(label=label), self.assertRaises(
                    self.envelope.EnvelopeRefusal) as refused:
                self._expand(malformed)
            self.assertEqual(malformed, before)
            self.assertIn("cognitive envelope refused:", str(refused.exception))

    def test_codec_refuses_foreign_schema_bad_outer_hash_and_tighter_declared_bounds(self):
        pack, expand = self._codec()
        foreign = copy.deepcopy(self.source)
        foreign["schema"] = "foreign-exposure-schema"
        with self.assertRaises(self.envelope.EnvelopeRefusal):
            pack(exposure=foreign,
                 max_input_bytes=self.envelope.MAX_INPUT_BYTES,
                 max_document_bytes=self.envelope.MAX_DOCUMENT_BYTES)

        packed = self._pack()
        bad_outer_hash = copy.deepcopy(packed)
        bad_outer_hash["artifact_sha256"] = "0" * 64
        with self.assertRaises(self.envelope.EnvelopeRefusal):
            self._expand(bad_outer_hash)

        with self.assertRaises(self.envelope.EnvelopeRefusal):
            pack(exposure=self.source, max_input_bytes=1, max_document_bytes=1)
        with self.assertRaises(self.envelope.EnvelopeRefusal):
            expand(interned=packed, max_input_bytes=1, max_document_bytes=1)

    def test_codec_is_detached_and_has_no_file_process_network_or_clock_boundary(self):
        pack, expand = self._codec()
        before = copy.deepcopy(self.source)
        with mock.patch("builtins.open", side_effect=AssertionError("file access")), \
                mock.patch("subprocess.run", side_effect=AssertionError("process execution")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("process execution")), \
                mock.patch("socket.socket", side_effect=AssertionError("network access")), \
                mock.patch("time.time", side_effect=AssertionError("ambient clock")):
            packed = pack(
                exposure=self.source,
                max_input_bytes=self.envelope.MAX_INPUT_BYTES,
                max_document_bytes=self.envelope.MAX_DOCUMENT_BYTES,
            )
            expanded = expand(
                interned=packed,
                max_input_bytes=self.envelope.MAX_INPUT_BYTES,
                max_document_bytes=self.envelope.MAX_DOCUMENT_BYTES,
            )
        self.assertEqual(canonical(expanded), canonical(before))
        self.assertEqual(self.source, before)

    def test_legacy_exposure_schema_api_and_refusal_are_unchanged(self):
        parameters = inspect.signature(
            self.exposure_module.rerank_event_exposure).parameters
        self.assertEqual(set(parameters), {
            "measurement_plan", "expected_measurement_plan_sha256", "replay_inputs",
            "rerank_policy", "expected_rerank_policy_sha256", "activation_policy",
            "expected_activation_policy_sha256",
        })
        repeated = self.fx._call(self.exposure_module)
        self.assertEqual(repeated["schema"], "sia-cognitive-event-exposure-v1")
        self.assertEqual(canonical(repeated), canonical(self.source))

        policy = copy.deepcopy(self.fx.kw["rerank_policy"])
        policy["schema"] = "foreign-exposure-policy"
        overrides = self.fx._policy_override(policy)
        with self.assertRaises(self.exposure_module.ExposureRefusal) as refused:
            self.fx._call(self.exposure_module, **overrides)
        self.assertIn("cognitive event exposure refused:", str(refused.exception))

    def test_legacy_fidelity_schema_api_and_refusal_are_unchanged(self):
        fixture = fidelity_tests.CognitiveFidelity(methodName="runTest")
        fixture.setUp()
        try:
            parameters = inspect.signature(
                fixture.module.prepare_mechanism_fidelity).parameters
            self.assertEqual(set(parameters), {
                "ordered_plan", "expected_ordered_plan_sha256", "ordered_inputs",
                "fidelity_policy", "expected_fidelity_policy_sha256",
            })
            fixture._inputs()
            result = fixture._call()
            self.assertEqual(result["schema"], "sia-cognitive-memory-fidelity-v1")
            self.assertEqual(result["status"], "computed-unverified")

            policy = copy.deepcopy(fixture.kw["fidelity_policy"])
            policy["schema"] = "foreign-fidelity-policy"
            with self.assertRaises(fixture.module.FidelityRefusal) as refused:
                fixture._call(**fixture._policy_override(policy))
            self.assertIn("cognitive fidelity refused:", str(refused.exception))
        finally:
            fixture.doCleanups()


if __name__ == "__main__":
    unittest.main(verbosity=2)
