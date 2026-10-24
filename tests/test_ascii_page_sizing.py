"""UTF-8 JSON ASCII admission against the independent serializer oracle."""

import json
import unittest

import siaeventplan as plan


class AsciiPageSizing(unittest.TestCase):
    def assert_capacity(self, value, quoted):
        raw = (json.dumps(value, ensure_ascii=False).encode("utf-8")
               if quoted else value.encode("utf-8"))
        expected = len(raw)
        self.assertEqual(plan._text_size(value, expected, quoted=quoted), expected)
        with self.assertRaises(ValueError):
            plan._text_size(value, expected - 1, quoted=quoted)

    def test_every_ascii_codepoint_keeps_exact_limit(self):
        for point in range(128):
            for quoted in (False, True):
                with self.subTest(point=point, quoted=quoted):
                    self.assert_capacity(chr(point), quoted)

    def test_chunk_edges_and_del_stay_literal_in_utf8_json(self):
        for length in (0, 4095, 4096, 4097, 8193):
            for suffix in ("", "\x7f", "\x00", "\n", "\\", '"', "é", "😀"):
                for quoted in (False, True):
                    with self.subTest(length=length, suffix=suffix, quoted=quoted):
                        self.assert_capacity("a" * length + suffix, quoted)

    def test_non_builtin_text_is_still_refused(self):
        class Text(str):
            pass
        for value in (Text("plain"), b"plain", None):
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError):
                plan._text_size(value, 100)


if __name__ == "__main__":
    unittest.main()
