"""Pure exact-byte projection prerequisite for a future event render plan.

Root alone executes these tests. The existing captured-source fixture supplies
the byte/hash/origin oracle and private files; none is machine history. The
new helper owns no reads, writes, clock, model or source-authentication claim.
It must be core-owned, while the graph child's frozen export roster remains
unchanged. Capture delegates its already admitted full bytes to this helper.

Full raw UTF-8 includes frontmatter, comments, original normalization and mixed
body newlines. Input is exact bytes, not a coercible object. The complete byte
ceiling applies before decoding, copying, parsing or hashing; the negative
capacity control includes invalid UTF-8 to distinguish capacity from decode
refusal without allocating a large source or deriving a numerical oracle.
"""

import contextlib
import inspect
import unittest
from unittest import mock

from tests import test_corpus_version_capture as captured


RAW = captured.RAW
PAGE_KEYS = captured.PAGE_KEYS
REFUSALS = (RuntimeError, ValueError, TypeError)


class _Forbidden:
    def __getattr__(self, name):
        raise AssertionError("pure projection accessed ambient operation: " + name)


class CorpusVersionProjection(unittest.TestCase):
    def setUp(self):
        self.fixture = captured.CorpusVersionCapture(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.core = self.fixture.core
        self.slug = self.fixture.slug
        self.project = getattr(self.core, "_corpus_page_version_from_bytes", None)
        self.assertTrue(callable(self.project),
                        "sialib._corpus_page_version_from_bytes is missing")

    def _project(self, *, slug=None, raw=RAW):
        return self.project(slug=self.slug if slug is None else slug, raw=raw)

    def _no_work(self):
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(
            self.core, "hashlib", _Forbidden()))
        stack.enter_context(mock.patch.object(
            self.core, "copy", _Forbidden()))
        stack.enter_context(mock.patch.object(
            self.core, "FM_RE", _Forbidden()))
        stack.enter_context(mock.patch.object(
            self.core, "_yaml_scalar", side_effect=AssertionError("parsing before admission")))
        stack.enter_context(mock.patch.object(
            self.core.siamind, "origin_class",
            side_effect=AssertionError("origin work before admission")))
        return stack

    def test_core_owned_exact_keyword_only_signature_and_closed_page_roster(self):
        signature = inspect.signature(self.project)
        self.assertEqual(set(signature.parameters), {"slug", "raw"})
        for parameter in signature.parameters.values():
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)
        self.assertEqual(self.project.__module__, self.core.__name__)
        self.assertIsNot(self.project.__dict__.get("_sia_senses_delegate"), True)
        result = self._project()
        self.assertEqual(set(result), PAGE_KEYS)
        self.assertEqual(result, captured.expected_page(self.slug, RAW, "evidence"))
        self.assertEqual(result["content"].encode("utf-8"), RAW)

    def test_same_full_byte_oracle_and_detached_result(self):
        expected = captured.expected_page(self.slug, RAW, "evidence")
        result = self._project()
        self.assertEqual(result, expected)
        self.assertEqual(result["source_sha256"], result["content_sha256"])
        result["content"] = "caller changes only its detached result"
        result["origin"] = "model"
        self.assertEqual(self._project(), expected)
        self.assertEqual(self.fixture.path.read_bytes(), RAW)

    def test_source_capture_origin_cases_match_pure_projection_exactly(self):
        # These cases and expected classes are the frozen source-capture
        # literals, not newly inferred namespace or source-authentication rules.
        cases = (
            ("events/journal/unlabeled", b"type: event-day\n", "evidence"),
            ("events/jackal/namespace", b"type: event-day\norigin: evidence\n", "derived"),
            ("thoughts/derived", b"type: thought\norigin: derived\n", "derived"),
            ("notes/declared", b"type: note\norigin: model\n", "model"),
            ("notes/unlabeled", b"type: note\n", "model"),
            ("thoughts/unlabeled", b"type: thought\n", "legacy-unlabeled"),
            ("unknown/namespace", b"type: event-day\n", "legacy-unlabeled"),
            ("events/journal/misplaced-type", b"type: note\n", "legacy-unlabeled"),
        )
        for slug, fields, origin in cases:
            raw = b"---\n" + fields + b'\ntitle: "Origin fixture"\n---\nbody\n'
            self.fixture.write(slug, raw)
            with self.subTest(slug=slug), mock.patch.object(
                    self.core, "corpus_origin",
                    side_effect=AssertionError("separate unfenced origin read")):
                expected = captured.expected_page(slug, raw, origin)
                self.assertEqual(self._project(slug=slug, raw=raw), expected)
                self.assertEqual(self.fixture.capture(slug), expected)

    def test_unusual_frontmatter_unicode_and_mixed_newlines_remain_exact(self):
        raw = ("---\n# preserve this comment\n"
               "title:   'Quoted ''title'''\n\ntype:   event-day   \n"
               "origin:   \"evidence\"   \nextra: [untouched, metadata]\n"
               "---\n\r\n# café and cafe\u0301\r\n"
               "[[unaltered/link]]  \n\nfinal line without newline").encode("utf-8")
        expected = captured.expected_page(self.slug, raw, "evidence")
        self.fixture.path.write_bytes(raw)
        result = self._project(raw=raw)
        self.assertEqual(result, expected)
        self.assertEqual(result["content"].encode("utf-8"), raw)
        self.assertEqual(self.fixture.capture(self.slug), expected)

    def test_no_frontmatter_keeps_original_bytes_and_legacy_origin(self):
        slug = "unknown/plain"
        raw = b"Opaque original bytes\r\nNo generated frontmatter\n"
        expected = captured.expected_page(slug, raw, "legacy-unlabeled")
        self.fixture.write(slug, raw)
        self.assertEqual(self._project(slug=slug, raw=raw), expected)
        self.assertEqual(self.fixture.capture(slug), expected)

    def test_pure_projection_never_reads_files_clock_or_model(self):
        expected = captured.expected_page(self.slug, RAW, "evidence")
        forbidden = mock.Mock(side_effect=AssertionError("pure projection performed I/O"))
        overrides = {name: forbidden for name in (
            "open", "read", "write", "stat", "lstat", "fstat", "scandir",
            "listdir", "getcwd", "mkdir", "makedirs", "unlink", "replace")}
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("builtins.open", forbidden))
            stack.enter_context(mock.patch.object(
                self.core, "os", captured._OsShim(**overrides)))
            for name in ("_open_source_nofollow", "_source_path_identity",
                         "_read_graph_corpus_page", "_capture_corpus_page_version",
                         "corpus_origin", "atomic_write", "gbrain", "gbrain_call",
                         "utcnow", "iso"):
                stack.enter_context(mock.patch.object(self.core, name, forbidden))
            for name in ("time", "datetime", "subprocess", "sqlite3"):
                stack.enter_context(mock.patch.object(self.core, name, _Forbidden()))
            observed = self._project()
        self.assertEqual(observed, expected)
        forbidden.assert_not_called()

    def test_capture_delegates_admitted_complete_bytes_to_core_projection(self):
        with mock.patch.object(
                self.core, "_corpus_page_version_from_bytes", wraps=self.project) as projection:
            observed = self.fixture.capture(self.slug)
        projection.assert_called_once_with(slug=self.slug, raw=RAW)
        self.assertEqual(observed, captured.expected_page(self.slug, RAW, "evidence"))

    def test_graph_child_facade_roster_and_legacy_tuple_remain_unchanged(self):
        # Reuse the independently frozen release roster instead of creating a
        # new child export or copying an implementation-derived allowlist.
        from tests.test_release import ReleaseContract
        expected_exports = ReleaseContract.FACADE_CHILD_EXPORTS["siagraph"]
        self.assertEqual(sorted(self.core._siagraph._EXPORTED_FUNCTIONS),
                         sorted(expected_exports))
        self.assertNotIn("_corpus_page_version_from_bytes",
                         self.core._siagraph._EXPORTED_FUNCTIONS)
        before = self.core._read_graph_corpus_page(self.slug)
        self.assertIs(type(before), tuple)
        self.assertEqual(set(before[0]),
                         {"slug", "type", "title", "updated_at", "origin", "sha256"})
        self.assertEqual(before[1], 'type: event-day\ntitle: "Fixture"\norigin: evidence')
        self.assertEqual(before[2], "# original page\n")
        self._project()
        self.fixture.capture(self.slug)
        self.assertEqual(self.core._read_graph_corpus_page(self.slug), before)

    def test_exact_bytes_type_refuses_coercions_and_subclasses_before_work(self):
        class Coercible:
            def __bytes__(self):
                raise AssertionError("raw input was coerced to bytes")

            def __str__(self):
                raise AssertionError("raw input was coerced to text")

        class BytesSubclass(bytes):
            def decode(self, *args, **kwargs):
                raise AssertionError("bytes subclass was decoded")

        for raw in (RAW.decode("utf-8"), bytearray(RAW), memoryview(RAW),
                    BytesSubclass(RAW), Coercible(), None, True, {}, []):
            with self.subTest(kind=type(raw).__name__), self._no_work(), \
                    self.assertRaises(REFUSALS):
                self.project(slug=self.slug, raw=raw)

    def test_noncanonical_slug_refuses_before_page_work(self):
        # A suffix such as '.md' is not included here: the frozen capture test
        # rejects its missing physical leaf, whereas this API is lexical only.
        for slug in ("", "../outside", "/events/journal/fixture",
                     "events//journal/fixture", "events/journal/../fixture",
                     "events/journal/fixture/", "Events/journal/fixture",
                     "events\\journal\\fixture", None, True, [], {}):
            with self.subTest(slug=slug), self._no_work(), self.assertRaises(REFUSALS):
                self.project(slug=slug, raw=RAW)

    def test_complete_byte_ceiling_accepts_exact_boundary(self):
        expected = captured.expected_page(self.slug, RAW, "evidence")
        with mock.patch.object(self.core, "MAX_EVENT_PAGE_BYTES", len(RAW)):
            self.assertEqual(self._project(), expected)

    def test_over_cap_invalid_utf8_refuses_capacity_before_decode_copy_or_hash(self):
        with mock.patch.object(self.core, "MAX_EVENT_PAGE_BYTES", len(RAW)), \
                self._no_work(), self.assertRaisesRegex(
                    (RuntimeError, ValueError), r"(?i)(byte.*bound|capacity|bounded)"):
            self._project(raw=RAW + b"\xff")

    def test_invalid_utf8_or_ambiguous_metadata_refuses_like_captured_reader(self):
        for raw in (
                RAW + b"\xff",
                b"---\ntype: event-day\norigin: evidence\norigin: model\n---\nbody\n",
                b"---\ntype: event-day\norigin: invented-class\n---\nbody\n",
                b"---\ntype: event-day\ntype: note\n---\nbody\n",
                b"---\ntype: ../invalid\n---\nbody\n"):
            with self.subTest(raw=raw):
                self.fixture.path.write_bytes(raw)
                with self.assertRaises(REFUSALS):
                    self._project(raw=raw)
                with self.assertRaises(captured.REFUSALS):
                    self.fixture.capture(self.slug)
                self.assertEqual(self.fixture.path.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
