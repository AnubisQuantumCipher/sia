"""Closed compound input admission retains the original per-document ceiling.

JACKAL fixture boundaries: status=exact, formal=false;
parsed=64*1024*1024 exact=67108864;
parsed=67108864+1 exact=67108865;
parsed=16777216+1 exact=16777217.
Nonclaims: NOT formal-bounded: this lane carries no Lean-checked certificate;
The epistemic class above is the STRONGEST claim this result supports;
exact rational arithmetic (not yet checker-covered).
These arithmetic fixtures do not establish software correctness.
"""

import copy
import importlib
import inspect
import unittest
from unittest import mock

from tests import test_cognitive_measurement


class CognitiveEnvelope(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("siacognitiveenvelope")
        except ModuleNotFoundError as exc:
            self.fail("bounded closed compound-envelope helper must exist: " + str(exc))
        self.layout = {"document": None, "replay": {"source": None, "pin": None}}
        self.value = {"document": {"text": "read-only"},
                      "replay": {"source": {"value": -0.0}, "pin": "a" * 64}}

    def _call(self, value=None, **kwargs):
        return self.module.admit_compound(
            envelope=self.value if value is None else value,
            **{"layout": self.layout, "max_input_bytes": 4096,
               "max_document_bytes": 1024, **kwargs})

    def test_explicit_keyword_only_contract_and_no_mutation_or_output_copy(self):
        parameters = inspect.signature(self.module.admit_compound).parameters
        self.assertEqual(set(parameters), {"envelope", "layout", "max_input_bytes", "max_document_bytes"})
        for item in parameters.values():
            self.assertEqual(item.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(item.default, inspect.Parameter.empty)
        before = copy.deepcopy(self.value)
        with mock.patch("copy.deepcopy", side_effect=AssertionError("admission must not copy")):
            self.assertIsNone(self._call())
        self.assertEqual(before, self.value)

    def test_closed_topology_rejects_missing_extra_and_wrong_container_fields(self):
        for value in ({}, {**self.value, "unaccounted": {}},
                      {**self.value, "replay": {"source": {}, "pin": "a", "extra": "x"}},
                      {**self.value, "replay": []}):
            with self.subTest(value=value), self.assertRaises(self.module.EnvelopeRefusal):
                self._call(value)

    def test_all_structure_is_admitted_before_any_serialization(self):
        cyclic = {}
        cyclic["self"] = cyclic
        for bad in (cyclic, {"bad": float("inf")}, {"bad": float("nan")}, {1: "key"}, object()):
            value = {**self.value, "replay": {"source": bad, "pin": "a"}}
            with self.subTest(bad=type(bad)), \
                    mock.patch("json.dumps", side_effect=AssertionError("serialized before complete admission")), \
                    self.assertRaises(self.module.EnvelopeRefusal):
                self._call(value)

    def test_each_original_document_ceiling_survives_larger_envelope_budget(self):
        value = {**self.value, "document": {"text": "x" * 128}}
        with self.assertRaises(self.module.EnvelopeRefusal):
            self._call(value, max_document_bytes=100)

    def test_complete_aggregate_ceiling_counts_repeated_references_again(self):
        value = "x" * 64
        with self.assertRaises(self.module.EnvelopeRefusal):
            self._call({"left": value, "right": value}, layout={"left": None, "right": None},
                       max_input_bytes=128, max_document_bytes=128)

    def test_exact_serialized_document_and_envelope_bounds_include_json_escaping(self):
        # Deliberately chosen strings; no calculated wire length is asserted.
        with self.assertRaises(self.module.EnvelopeRefusal):
            self._call({"doc": "\x01" * 24}, layout={"doc": None},
                       max_input_bytes=1024, max_document_bytes=100)
        with self.assertRaises(self.module.EnvelopeRefusal):
            self._call({"a": "\x01" * 16, "b": "\x01" * 16},
                       layout={"a": None, "b": None},
                       max_input_bytes=128, max_document_bytes=128)

    def test_declared_limits_are_strict_and_cannot_exceed_either_hard_ceiling(self):
        for key, bad in (("max_input_bytes", 67108865), ("max_document_bytes", 16777217),
                         ("max_input_bytes", True), ("max_document_bytes", 0),
                         ("max_input_bytes", -1), ("max_document_bytes", 1.0),
                         ("max_input_bytes", None), ("max_document_bytes", "1024")):
            with self.subTest(key=key, bad=bad), self.assertRaises(self.module.EnvelopeRefusal):
                self._call(**{key: bad})
        with self.assertRaises(self.module.EnvelopeRefusal):
            self._call(max_input_bytes=100, max_document_bytes=1024)

    def test_layout_is_a_bounded_closed_tree_not_an_ignore_or_wildcard_instruction(self):
        cyclic = {}
        cyclic["self"] = cyclic
        for layout in (None, [], {"document": True}, cyclic, {1: None}):
            with self.subTest(layout=type(layout)), self.assertRaises(self.module.EnvelopeRefusal):
                self._call(layout=layout)


if __name__ == "__main__":
    unittest.main()
