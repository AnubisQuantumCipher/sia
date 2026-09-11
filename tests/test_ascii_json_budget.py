"""Canonical byte budgets must retain their bounds without Python ASCII walks."""

import json
import math
from pathlib import Path
import sys
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

import sialiveloop as live
import siasourcebatch as source


class AsciiJsonBudget(unittest.TestCase):
    owner = {"json": json, "math": math}

    def test_ascii_payloads_do_not_enter_per_character_python_path(self):
        value = {"document": "".join(map(chr, range(128))) * 100,
                 "nested": ["ordinary text", "\\\"quoted\\\"", "line\nline"]}
        for module, ascii_only in ((live, False), (source, True)):
            expected = len(json.dumps(value, sort_keys=True,
                separators=(",", ":"), ensure_ascii=ascii_only).encode())
            with self.subTest(module=module.__name__), mock.patch.object(
                    module, "ord", create=True,
                    side_effect=AssertionError("ASCII walked in Python")):
                actual = (live._size(value, expected) if module is live
                          else source._json_size(self.owner, value, expected,
                                                 ascii_only=ascii_only))
                self.assertEqual(actual, expected)

    def test_all_ascii_characters_and_unicode_keep_exact_serialized_boundary(self):
        values = ["", *map(chr, range(128)), "é漢😀", "\x7fé", "\n😀\\\"",
                  {"ascii": ["x\ny", "\u0000"], "unicode": "漢😀"}]
        for value in values:
            for ascii_only in (False, True):
                raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=ascii_only).encode("utf-8")
                with self.subTest(value=value, ascii_only=ascii_only):
                    self.assertEqual(source._json_bytes(
                        self.owner, value, len(raw), ascii_only=ascii_only), raw)
                    with self.assertRaises(source.SourceBatchRefusal):
                        source._json_bytes(self.owner, value, len(raw) - 1,
                                           ascii_only=ascii_only)
                    if not ascii_only:
                        self.assertEqual(live._size(value, len(raw)), len(raw))
                        with self.assertRaises(live.LiveLoopRefusal):
                            live._size(value, len(raw) - 1)

    def test_surrogates_and_cycles_still_refuse(self):
        cycle = []
        cycle.append(cycle)
        for value in ("\ud800", "ascii\udfff", cycle):
            with self.subTest(value=repr(value)):
                with self.assertRaises(live.LiveLoopRefusal):
                    live._size(value, 4096)
                for ascii_only in (False, True):
                    with self.assertRaises(source.SourceBatchRefusal):
                        source._json_size(self.owner, value, 4096,
                                          ascii_only=ascii_only)


if __name__ == "__main__":
    unittest.main()
