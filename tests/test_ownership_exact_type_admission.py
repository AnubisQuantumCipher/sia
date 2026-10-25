"""Exact-type ownership gates; no installed service or protected write claim."""
try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import hashlib
import importlib
import json
import math
import os
import unittest
from unittest import mock


def exotic(trace, matched, base=object):
    def record(name):
        if len(trace) >= 32:
            raise AssertionError("trace capacity")
        trace.append(name)

    class Spoof(type):
        __hash__ = None

        def __eq__(cls, other):
            record("type-equality")
            return any(other is item for item in matched)

    class Value(base, metaclass=Spoof):
        def __len__(self):
            record("length")
            return 1

        def __iter__(self):
            record("iteration")
            return iter(("fixture",))

        def __bool__(self):
            record("truth")
            return True

    return Value()


def forbidden(*_args, **_kwargs):
    raise AssertionError("unexpected downstream operation")


def owner_fixture(module, claims):
    owner = dict.fromkeys(module._CAPACITIES, 4096)
    owner.update({"_SENSE_ORGAN": {}, "LIVE_PUBLICATION_NON_CLAIMS": claims,
                  "NOTIFY_BASELINE_ATTEMPT_KEY": "fixture-key",
                  "_validated_custom_sense_entry": forbidden,
                  "_canonical_utc_timestamp": forbidden,
                  "json": json, "hashlib": hashlib, "math": math, "os": os})
    return owner


class OwnershipTypes(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.path.expanduser("~"), sia_test_home.ISOLATED_HOME)

    def test_pin_builders_reject_exotic_values_before_hooks(self):
        for name in ("siacontrollerdeliverywriter", "siainstalledengine"):
            module = importlib.import_module(name)
            for base in (object, str, int, list):
                for matched in ((str,), (list, tuple)):
                    for position in ("root", "nested"):
                        trace = []
                        value = exotic(trace, matched, base)
                        if position == "nested":
                            value = {"child": [value]}
                        with self.subTest(module=name, base=base.__name__,
                                          matched=matched, position=position):
                            with self.assertRaises(ValueError):
                                module._plain_pin(value)
                            self.assertEqual(trace, [])

    def test_pins_preserve_native_types_and_detect_late_changes(self):
        for name in ("siacontrollerdeliverywriter", "siainstalledengine"):
            module = importlib.import_module(name)
            value = {"items": [True, 1, "one", None]}
            pin = module._plain_pin(value)
            self.assertTrue(module._plain_same(value, pin))
            value["items"][0] = 1
            self.assertFalse(module._plain_same(value, pin))
            trace = []
            self.assertFalse(module._plain_same(exotic(trace, (dict,)), pin))
            self.assertEqual(trace, [])
        writer = importlib.import_module("siacontrollerdeliverywriter")
        value = (0.0, -0.0, {"items": (1, "two")})
        pin = writer._plain_pin(value)
        self.assertTrue(writer._plain_same(value, pin))
        self.assertFalse(writer._plain_same((-0.0, -0.0, value[2]), pin))
        self.assertFalse(writer._plain_same(list(value), pin))

    def test_registry_rejects_exotic_scalar_and_container_identity(self):
        registry = importlib.import_module("siacognitiveregistry")
        for matched in ((str,), (dict, list)):
            for base in (object, str, list):
                trace = []
                value = {"value": [exotic(trace, matched, base)]}
                with self.subTest(matched=matched, base=base.__name__):
                    with self.assertRaisesRegex(registry._BoundaryError,
                                                "^evidence-not-canonical-bounded-json$"):
                        registry._validate_json_tree(value)
                    self.assertEqual(trace, [])
        registry._validate_json_tree({"value": [1, True, "x", None]})

    def test_container_inventory_does_not_invoke_exotic_hooks(self):
        render = importlib.import_module("siagetrenderadmit")
        trace = []
        self.assertEqual(render._containers(exotic(trace, (dict, list))), set())
        self.assertEqual(trace, [])
        child = []
        value = {"first": child, "second": child}
        self.assertEqual(render._containers(value), {id(value), id(child)})

    def test_owner_claim_roster_rejects_exotic_types_before_iteration(self):
        wrapper = importlib.import_module("siacontrollerdeliverywrapper")
        for base in (object, list, tuple):
            trace = []
            owner = owner_fixture(wrapper, exotic(trace, (list, tuple), base))
            with self.subTest(base=base.__name__):
                with self.assertRaisesRegex(ValueError, "owner-live-nonclaims-contract"):
                    wrapper._owner_basis(owner)
                self.assertEqual(trace, [])
        for claims in (["fixture"], ("fixture",)):
            self.assertEqual(wrapper._owner_basis(owner_fixture(wrapper, claims))[
                "live_publication_non_claims"], ["fixture"])

    def test_publication_facade_refuses_exotic_values_before_serialization(self):
        core = importlib.import_module("sialib")
        for matched in ((str,), (dict, list)):
            for base in (object, str, list):
                trace = []
                value = {"value": exotic(trace, matched, base)}
                with self.subTest(matched=matched, base=base.__name__), \
                        mock.patch.object(core, "_memo_text", side_effect=forbidden):
                    with self.assertRaisesRegex(RuntimeError, "native memo contains a non-JSON value"):
                        core._live_memo_bytes(value)
                    self.assertEqual(trace, [])

    def test_publication_facade_native_wire_remains_exact(self):
        core = importlib.import_module("sialib")
        value = {"native_ns": 1 << 80, "float": -0.0, "nested": [True, None, "é"]}
        expected = json.dumps(value, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=True, allow_nan=False).encode("utf-8")
        self.assertEqual(core._live_memo_bytes(value), expected)
        cyclic = []
        cyclic.append(cyclic)
        with self.assertRaisesRegex(RuntimeError, "native memo JSON is cyclic"):
            core._live_memo_bytes(cyclic)
        with self.assertRaisesRegex(RuntimeError, "native memo contains a non-JSON value"):
            core._live_memo_bytes(float("nan"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
