"""The C-speed string sizers count exactly what the per-character loops did.

The per-character loops made every consistency check of a multi-megabyte
retained batch take seconds, and a first light with a week's backlog take
hours. Their replacements must be byte-identical, including the escapes the
serializer writes and the refusal of lone surrogates.
"""

try:
    import sia_test_home  # noqa: F401
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore  # noqa: F401

import importlib
import json
import os
import random
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin")
if BIN not in sys.path:
    sys.path.insert(0, BIN)


def reference_json_string(value, *, ascii_only=False):
    """The original per-character accounting, kept here as the oracle."""
    size = 2
    for character in value:
        point = ord(character)
        if 0xD800 <= point <= 0xDFFF:
            return None
        if character in '"\\\b\f\n\r\t':
            size += 2
        elif point < 0x20:
            size += 6
        elif ascii_only and point >= 0x7F:
            size += 6 if point <= 0xFFFF else 12
        else:
            size += len(character.encode("utf-8"))
    return size


def reference_utf8(value):
    total = 0
    for character in value:
        point = ord(character)
        if 0xD800 <= point <= 0xDFFF:
            return None
        total += 1 if point <= 0x7F else 2 if point <= 0x7FF else 3 if point <= 0xFFFF else 4
    return total


SAMPLES = [
    "", "plain ascii", 'quote " and backslash \\', "tab\tnewline\nreturn\rbell\x07",
    "\x00\x01\x1f control", "del\x7fchar", "café · résumé — ok", "λx.x → y",
    "emoji 😀 and 𝄞", "mixed \n é 😀 \" \\ \x1b", "x" * 5000 + "é", "日本語テキスト",
    "   separators", "trailing backslash \\",
]
SURROGATES = ["lone \ud800 surrogate", "\udfff", "ok \ud83d then broken"]


class JsonSizeFastPath(unittest.TestCase):
    def setUp(self):
        random.seed(20260919)
        alphabet = ['"', "\\", "\n", "\t", "\x01", "\x7f", "a", "é", "λ", "😀", "日", " "]
        self.samples = list(SAMPLES) + [
            "".join(random.choice(alphabet) for _ in range(random.randint(0, 80)))
            for _ in range(300)]

    def test_event_plan_text_size_matches_the_reference(self):
        plan = importlib.import_module("siaeventplan")
        for value in self.samples:
            with self.subTest(value=value[:20]):
                self.assertEqual(plan._text_size(value, 10 ** 9), reference_json_string(value))
                self.assertEqual(plan._text_size(value, 10 ** 9, quoted=False), reference_utf8(value))
                self.assertEqual(plan._text_size(value, 10 ** 9),
                                 len(json.dumps(value, ensure_ascii=False).encode("utf-8")))
        for value in SURROGATES:
            with self.assertRaises(ValueError):
                plan._text_size(value, 10 ** 9)
        with self.assertRaises(ValueError):
            plan._text_size("é" * 10, 19)
        self.assertEqual(plan._text_size("é" * 10, 22), 22)

    def test_workspace_text_length_matches_the_reference(self):
        workspace = importlib.import_module("siaworkspace")
        for value in self.samples:
            with self.subTest(value=value[:20]):
                self.assertEqual(workspace._text_length(value, 10 ** 9, json_string=True),
                                 reference_json_string(value))
                self.assertEqual(workspace._text_length(value, 10 ** 9), reference_utf8(value))
        for value in SURROGATES:
            with self.assertRaises(workspace.WorkspaceRefusal):
                workspace._text_length(value, 10 ** 9)
        with self.assertRaises(workspace.WorkspaceRefusal):
            workspace._text_length("é" * 10, 19)

    def test_live_loop_string_count_matches_the_reference_in_both_modes(self):
        live = importlib.import_module("sialiveloop")
        for ascii_only in (False, True):
            for value in self.samples:
                with self.subTest(value=value[:20], ascii_only=ascii_only):
                    total = []
                    handled = live._count_ascii_json_string(
                        value, total.append, ascii_only=ascii_only)
                    self.assertTrue(handled)
                    self.assertEqual(sum(total), reference_json_string(value, ascii_only=ascii_only))
                    self.assertEqual(sum(total),
                                     len(json.dumps(value, ensure_ascii=ascii_only).encode("utf-8")))
            for value in SURROGATES:
                total = []
                self.assertFalse(live._count_ascii_json_string(
                    value, total.append, ascii_only=ascii_only))

    def test_source_batch_native_bytes_refuses_surrogates_and_stays_exact(self):
        source = importlib.import_module("siasourcebatch")
        lib = importlib.import_module("sialib")
        owner = lib.__dict__
        for value in self.samples:
            with self.subTest(value=value[:20]):
                raw = source.native_bytes(owner, {"text": value})
                # native_bytes writes ASCII-only JSON; its admission count
                # runs through the ascii_only sizer and must match exactly.
                self.assertEqual(raw, json.dumps({"text": value}, sort_keys=True,
                                                 separators=(",", ":"), ensure_ascii=True,
                                                 allow_nan=False).encode("utf-8"))
        for value in SURROGATES:
            with self.assertRaises(source.SourceBatchRefusal):
                source.native_bytes(owner, {"text": value})

    def test_multi_megabyte_non_ascii_text_is_sized_in_well_under_a_second(self):
        plan = importlib.import_module("siaeventplan")
        value = ("journal line · with — non-ASCII marks and \"quotes\"\n" * 120_000)
        self.assertGreater(len(value.encode("utf-8")), 6_000_000)
        started = time.monotonic()
        size = plan._text_size(value, 10 ** 9)
        elapsed = time.monotonic() - started
        self.assertEqual(size, len(json.dumps(value, ensure_ascii=False).encode("utf-8")))
        self.assertLess(elapsed, 1.0, f"sizing took {elapsed:.2f}s")


if __name__ == "__main__":
    unittest.main()
