"""Bounded UTF-8 counting must retain exact JSON admission without scalar loops."""
import json
import unittest
from unittest import mock

import sialiveloop as live


class Utf8JsonBudget(unittest.TestCase):
    def test_unicode_fast_path_does_not_visit_codepoints_in_python(self):
        value = {'text': ('machine → memory 🧠\n' * 4096)}
        expected = len(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                  ensure_ascii=False).encode('utf-8'))
        with mock.patch('builtins.ord', side_effect=AssertionError('scalar Unicode loop')), \
                mock.patch('json.dumps', side_effect=AssertionError('premature serialization')):
            self.assertEqual(live._size(value, expected), expected)

    def test_utf8_widths_controls_and_chunk_boundaries_match_serializer(self):
        text = 'é漢🧠\u007f\u0080\u07ff\u0800\uffff\U0010ffff' + ''.join(map(chr, range(32))) + '"\\'
        for prefix in ('', 'x' * 4095, 'x' * 4096, 'x' * 4097):
            for value in (prefix + text, {text: [prefix + text, text]}):
                with self.subTest(prefix_length=len(prefix), kind=type(value).__name__):
                    raw = json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode('utf-8')
                    self.assertEqual(live._canonical(value, len(raw)), raw)
                    with self.assertRaisesRegex(ValueError, 'complete-json-byte-capacity'):
                        live._size(value, len(raw[:-1]))

    def test_surrogates_remain_refused_in_every_chunk_position(self):
        for prefix in ('', 'x' * 4095, 'x' * 4096):
            for surrogate in ('\ud800', '\udfff'):
                with self.subTest(prefix_length=len(prefix), surrogate=repr(surrogate)):
                    with self.assertRaisesRegex(ValueError, 'unpaired-surrogate'):
                        live._size(prefix + surrogate, live.MAX_INPUT_BYTES)

    def test_oversize_unicode_refuses_before_serialization(self):
        with mock.patch('json.dumps', side_effect=AssertionError('premature serialization')):
            with self.assertRaisesRegex(ValueError, 'complete-json-byte-capacity'):
                live._canonical('🧠' * 4096, 100)
