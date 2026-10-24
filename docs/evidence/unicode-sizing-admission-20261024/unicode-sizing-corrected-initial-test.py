"""Bound scratch encoding before admission; keep the original byte oracle."""

import json
import math
import tracemalloc
import unittest
from unittest import mock

import siaeventplan as plan
import sialiveloop as live
import siasourcebatch as source


OWNER = {"json": json, "math": math, "MAX_STATE_JSON_BYTES": 8_000_000}
CHUNK_CHARACTERS = 4096


def native_size(value, limit):
    return source._json_size(OWNER, value, limit, ascii_only=True)


def component_size(value, limit):
    return source._json_size(OWNER, value, limit, ascii_only=False)


class UnicodeSizingAdmission(unittest.TestCase):
    def test_obvious_oversize_is_refused_before_encoding(self):
        value = "é" * 1_048_576
        for module, size in ((live, live._size), (live, native_size),
                             (live, component_size), (plan, plan._text_size)):
            seen = []
            original = module._utf8_length

            def observed(text, original=original, seen=seen):
                seen.append(len(text))
                return original(text)

            with self.subTest(module=module.__name__, size=size.__name__), \
                    mock.patch.object(module, "_utf8_length", observed):
                with self.assertRaises(ValueError):
                    size(value, 32)
                self.assertEqual(seen, [], "reject before any encoding request")

    def test_accepted_encoding_calls_have_fixed_chunk_bounds(self):
        value = ("é😀\n\x7f" * 5000) + "tail"
        for module, size, ascii_only in (
                (live, live._size, False), (live, native_size, True),
                (live, component_size, False), (plan, plan._text_size, False)):
            with self.subTest(module=module.__name__, size=size.__name__), \
                    mock.patch.object(module, "_utf8_length", wraps=module._utf8_length) as encode:
                expected = len(json.dumps(value, ensure_ascii=ascii_only).encode("utf-8"))
                self.assertEqual(size(value, expected), expected)
                self.assertTrue(encode.call_args_list)
                for call in encode.call_args_list:
                    self.assertLessEqual(len(call.args[0]), CHUNK_CHARACTERS)

    def test_large_refusal_has_small_observed_traced_scratch(self):
        values = ("x" * 1_048_576, "é" * 1_048_576, "😀" * 1_048_576)
        for value in values:
            for size in (live._size, native_size, component_size, plan._text_size):
                with self.subTest(character=value[0], size=size.__name__):
                    tracemalloc.start()
                    try:
                        with self.assertRaises(ValueError):
                            size(value, 32)
                        _current, peak = tracemalloc.get_traced_memory()
                    finally:
                        tracemalloc.stop()
                    self.assertLess(peak, 262_144, "observed scratch, not a process RSS bound")

    def test_chunk_edges_match_serializer_at_exact_capacity(self):
        for count in (4095, 4096, 4097, 8192):
            value = ('x' * count) + '\x00é😀"\\\n\x7f'
            for size, ascii_only in ((live._size, False), (native_size, True),
                                     (component_size, False), (plan._text_size, False)):
                with self.subTest(count=count, size=size.__name__):
                    expected = len(json.dumps(value, ensure_ascii=ascii_only).encode("utf-8"))
                    self.assertEqual(size(value, expected), expected)
                    with self.assertRaises(ValueError):
                        size(value, expected - 1)

    def test_nested_values_and_keys_keep_complete_budget(self):
        value = {"é😀": ["a" * 4096 + "é", {"\x7f": "\n😀"}]}
        for size, ascii_only in ((live._size, False), (native_size, True),
                                 (component_size, False), (plan._size, False)):
            with self.subTest(size=size.__name__):
                expected = len(json.dumps(value, ensure_ascii=ascii_only,
                                          separators=(",", ":")).encode("utf-8"))
                self.assertEqual(size(value, expected), expected)
                with self.assertRaises(ValueError):
                    size(value, expected - 1)

    def test_surrogates_at_chunk_edges_remain_refused(self):
        for offset in (0, 4095, 4096, 8192):
            for surrogate in ("\ud800", "\udfff"):
                value = "é" * offset + surrogate
                for size in (live._size, native_size, component_size, plan._text_size):
                    with self.subTest(offset=offset, size=size.__name__), \
                            self.assertRaises(ValueError):
                        size(value, OWNER["MAX_STATE_JSON_BYTES"])

    def test_unquoted_page_size_remains_exact_and_bounded(self):
        for value in ("", "é😀\n\x7f", "é" * 8193):
            expected = len(value.encode("utf-8"))
            with self.subTest(length=len(value)):
                self.assertEqual(plan._text_size(value, expected, quoted=False), expected)
                with self.assertRaises(ValueError):
                    plan._text_size(value, expected - 1, quoted=False)


if __name__ == "__main__":
    unittest.main()
