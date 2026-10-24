"""Exact-type gates must not consult hostile metaclass equality or hooks."""
import importlib
import json
import math
import unittest


TARGETS = (
    ("siasourcebatch", "_json_size", "owner"),
    ("sialiveloop", "_size", "limit"),
    ("siaeventplan", "_size", "limit"),
    ("siagist", "_json_size", "limit"),
    ("siacognitiveselect", "_bounded", "limit"),
    ("siacognitivebaseline", "_bounded", "limit"),
    ("siacognitivehistory", "_bounded_json", "value"),
    ("siacognitivesourcelink", "_measure", "limit"),
)


def exotic(trace, base, *, raising=False):
    def record(name):
        if len(trace) >= 32:
            raise AssertionError("test trace capacity")
        trace.append(name)

    class Spoof(type):
        __hash__ = None

        def __eq__(cls, other):
            record("equality")
            if raising:
                raise AssertionError("metaclass equality executed")
            return other is dict or other is list

    class Value(base, metaclass=Spoof):
        def __len__(self):
            record("length")
            return 0

        def __iter__(self):
            record("iteration")
            return iter(())

    return Value()


def invoke(target, value):
    name, function, mode = target
    operation = getattr(importlib.import_module(name), function)
    if mode == "owner":
        return operation({"json": json, "math": math}, value, 4096, ascii_only=True)
    if mode == "limit":
        return operation(value, 4096)
    if mode == "value":
        return operation(value)
    raise AssertionError("unknown fixture mode")


class ExactJsonTypes(unittest.TestCase):
    def check_exotic(self, *, raising):
        for target in TARGETS:
            for base in (object, list, dict):
                for placement in ("root", "list", "dict"):
                    trace = []
                    value = exotic(trace, base, raising=raising)
                    if placement == "list":
                        value = [value]
                    elif placement == "dict":
                        value = {"value": value}
                    with self.subTest(module=target[0], base=base.__name__,
                                      placement=placement):
                        with self.assertRaises((ValueError, RuntimeError)):
                            invoke(target, value)
                        self.assertEqual(trace, [], "exotic hooks must not execute")

    def test_equality_masquerade_is_refused_before_hooks(self):
        self.check_exotic(raising=False)

    def test_raising_equality_is_never_called(self):
        self.check_exotic(raising=True)

    def test_ordinary_json_values_remain_admitted(self):
        values = (None, True, False, 0, -1, "", "é", [], {},
                  {"value": [0, False, None, "é"]})
        for target in TARGETS:
            for value in values:
                with self.subTest(module=target[0], value=value):
                    invoke(target, value)

    def test_native_cycles_remain_refused(self):
        for target in TARGETS:
            value = []
            value.append(value)
            with self.subTest(module=target[0]):
                with self.assertRaises((ValueError, RuntimeError)):
                    invoke(target, value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
