"""Exact corpus-byte authority for the live intake page-version primitive.

Root alone executes this suite. Runtime imports are home-isolated, every source
is a private synthetic file, and no engine, CLI, keeper, clock or model runs.
The source/content hashes deliberately identify the SAME complete page bytes;
they are not source-event authentication or a claim of historical completeness.

Mutation hooks invoke real parsing/hashing first, then change the admitted
file. Success requires descriptor AND final named-generation checks through
the completed result construction, not merely around the initial read.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "bin"))
PAGE_KEYS = {
    "subject", "content", "origin", "source_sha256", "content_sha256",
    "version_sha256",
}
VERSION_KEYS = {"subject", "content_sha256", "source_sha256", "origin"}
REFUSALS = (RuntimeError, ValueError, OSError)
RAW = (b'---\ntype: event-day\ntitle: "Fixture"\n'
       b'origin: evidence\n---\n# original page\n')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def expected_page(slug, raw, origin):
    digest = hashlib.sha256(raw).hexdigest()
    page = {"subject": slug, "content": raw.decode("utf-8"), "origin": origin,
            "source_sha256": digest, "content_sha256": digest}
    page["version_sha256"] = hashlib.sha256(
        canonical({key: page[key] for key in VERSION_KEYS})).hexdigest()
    return page


class _OsShim:
    """Only this dynamically loaded core sees overridden syscalls."""

    def __init__(self, **overrides):
        self.overrides = overrides

    def __getattr__(self, name):
        return self.overrides[name] if name in self.overrides else getattr(os, name)


class _HashShim:
    """Keep real digests while exposing their finalization boundary."""

    def __init__(self, finalized):
        self.finalized = finalized

    def __getattr__(self, name):
        return getattr(hashlib, name)

    def sha256(self, data=b"", *args, **kwargs):
        actual = hashlib.sha256(data, *args, **kwargs)
        captured = bytearray(data)
        finalized = self.finalized

        class ObservedHash:
            def update(self, more):
                captured.extend(more)
                return actual.update(more)

            def hexdigest(self):
                result = actual.hexdigest()
                finalized(bytes(captured))
                return result

            def digest(self):
                result = actual.digest()
                finalized(bytes(captured))
                return result

        return ObservedHash()


class CorpusVersionCapture(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "sialib_corpus_version_capture_test", REPO / "bin/sialib.py")
        self.core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.core)
        self.temporary = tempfile.TemporaryDirectory(prefix="sia-page-version-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.owner = self.root / "owner"
        self.corpus = self.owner / "corpus"
        self.corpus.mkdir(parents=True, mode=0o700)
        self.core.CORPUS = str(self.corpus)
        self.slug = "events/journal/fixture"
        self.path = self.write(self.slug, RAW)
        self.capture = getattr(self.core, "_capture_corpus_page_version", None)
        self.assertTrue(callable(self.capture),
                        "sialib._capture_corpus_page_version is missing")

    def write(self, slug, raw):
        path = self.corpus / (slug + ".md")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(raw)
        path.chmod(0o600)
        return path

    def refuses(self, slug=None):
        with self.assertRaises(REFUSALS):
            self.capture(self.slug if slug is None else slug)

    def test_exact_closed_page_roster_and_same_byte_hashes(self):
        expected = expected_page(self.slug, RAW, "evidence")
        with mock.patch.object(
                self.core, "corpus_origin",
                side_effect=AssertionError("separate unfenced origin read")) as reread:
            observed = self.capture(self.slug)
        self.assertEqual(set(observed), PAGE_KEYS)
        self.assertEqual(observed, expected)
        reread.assert_not_called()
        self.assertEqual(self.path.read_bytes(), RAW)
        observed["content"] = "caller mutation of detached return"
        self.assertEqual(self.capture(self.slug), expected)

    def test_origin_rules_use_same_bytes_and_keep_all_existing_classes(self):
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
            path = self.write(slug, raw)
            with self.subTest(slug=slug), mock.patch.object(
                    self.core, "corpus_origin",
                    side_effect=AssertionError("origin must join captured bytes")):
                self.assertEqual(self.capture(slug), expected_page(slug, raw, origin))
                self.assertEqual(path.read_bytes(), raw)

    def test_unusual_valid_yaml_and_mixed_body_newlines_are_not_reserialized(self):
        raw = ("---\n# preserve this comment\n"
               "title:   'Quoted ''title'''\n\ntype:   event-day   \n"
               "origin:   \"evidence\"   \nextra: [untouched, metadata]\n"
               "---\n\r\n# café and cafe\u0301\r\n"
               "[[unaltered/link]]  \n\nfinal line without newline").encode("utf-8")
        self.path.write_bytes(raw)
        self.assertEqual(self.capture(self.slug), expected_page(self.slug, raw, "evidence"))
        self.assertEqual(self.path.read_bytes(), raw)

    def test_page_without_frontmatter_is_preserved_with_legacy_origin(self):
        slug = "unknown/plain"
        raw = b"Opaque original bytes\r\nNo generated frontmatter\n"
        self.write(slug, raw)
        self.assertEqual(self.capture(slug), expected_page(slug, raw, "legacy-unlabeled"))

    def test_existing_graph_tuple_and_metadata_shape_remain_unchanged(self):
        before = self.core._read_graph_corpus_page(self.slug)
        self.assertIs(type(before), tuple)
        self.assertEqual(set(before[0]),
                         {"slug", "type", "title", "updated_at", "origin", "sha256"})
        self.assertEqual(before[1], 'type: event-day\ntitle: "Fixture"\norigin: evidence')
        self.assertEqual(before[2], "# original page\n")
        captured = self.capture(self.slug)
        self.assertEqual(captured["source_sha256"], before[0]["sha256"])
        self.assertEqual(captured["origin"], before[0]["origin"])
        self.assertEqual(self.core._read_graph_corpus_page(self.slug), before)

    def test_noncanonical_slug_and_missing_page_refuse(self):
        for slug in ("../outside", "/events/journal/fixture", "events//journal/fixture",
                     "events/journal/fixture.md", "events/journal/absent"):
            with self.subTest(slug=slug):
                self.refuses(slug)

    def test_leaf_and_every_ancestor_symlink_refuse(self):
        for target in (self.path, self.path.parent, self.corpus, self.owner):
            with self.subTest(target=target):
                held = target.with_name(target.name + "-held")
                target.rename(held)
                target.symlink_to(held, target_is_directory=held.is_dir())
                try:
                    self.refuses()
                finally:
                    target.unlink()
                    held.rename(target)

    def test_hardlinked_page_refuses_without_mutation(self):
        alias = self.path.with_name("fixture-alias")
        os.link(self.path, alias)
        self.refuses()
        self.assertEqual(self.path.read_bytes(), RAW)
        self.assertEqual(alias.read_bytes(), RAW)

    def test_foreign_owner_refuses(self):
        identity = self.path.stat()

        def foreign_fstat(descriptor):
            info = os.fstat(descriptor)
            if (info.st_dev, info.st_ino) == (identity.st_dev, identity.st_ino):
                fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
                fields["st_uid"] = -1  # Deliberate foreign-owner syscall fixture, not a real chown.
                return SimpleNamespace(**fields)
            return info

        with mock.patch.object(self.core, "os", _OsShim(fstat=foreign_fstat)):
            self.refuses()
        self.assertEqual(self.path.read_bytes(), RAW)

    def test_directory_and_fifo_refuse_without_a_blocking_open(self):
        self.path.unlink()
        self.path.mkdir()
        self.refuses()
        self.path.rmdir()
        os.mkfifo(self.path, mode=0o600)
        opened = []

        def guarded_open(path, flags, *args, **kwargs):
            if os.path.basename(os.fspath(path)) == self.path.name:
                self.assertTrue(flags & os.O_NONBLOCK,
                                "FIFO admission attempted a potentially blocking leaf open")
                opened.append(path)
            return os.open(path, flags, *args, **kwargs)

        with mock.patch.object(self.core, "os", _OsShim(open=guarded_open)):
            self.refuses()
        self.assertTrue(opened, "the real FIFO admission path was not exercised")

    def test_complete_byte_bound_accepts_exact_boundary_and_refuses_before_hash(self):
        expected = expected_page(self.slug, RAW, "evidence")
        with mock.patch.object(self.core, "MAX_EVENT_PAGE_BYTES", len(RAW)):
            self.assertEqual(self.capture(self.slug), expected)
            self.path.write_bytes(RAW + b"x")
            with mock.patch.object(self.core, "hashlib", SimpleNamespace(
                    sha256=mock.Mock(side_effect=AssertionError("hashing over-cap page")))) as hashes:
                self.refuses()
                hashes.sha256.assert_not_called()

    def test_invalid_utf8_and_ambiguous_or_invalid_metadata_refuse(self):
        for raw in (
                RAW + b"\xff",
                b"---\ntype: event-day\norigin: evidence\norigin: model\n---\nbody\n",
                b"---\ntype: event-day\norigin: invented-class\n---\nbody\n",
                b"---\ntype: event-day\ntype: note\n---\nbody\n",
                b"---\ntype: ../invalid\n---\nbody\n"):
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                self.refuses()
                self.assertEqual(self.path.read_bytes(), raw)

    def mutate(self, kind):
        if kind == "content":
            prior = self.path.stat()
            changed = RAW.replace(b"original", b"modified")
            self.assertEqual(len(changed), len(RAW))
            self.path.write_bytes(changed)
            os.utime(self.path, ns=(prior.st_atime_ns, prior.st_mtime_ns))
        elif kind == "metadata":
            self.path.chmod(0o400)
        elif kind == "leaf-name":
            replacement = self.path.with_name("replacement.md")
            replacement.write_bytes(RAW)
            replacement.chmod(0o600)
            os.replace(replacement, self.path)
        elif kind == "ancestor-name":
            directory = self.path.parent
            directory.rename(directory.with_name("journal-held"))
            directory.mkdir(mode=0o700)
            self.path.write_bytes(RAW)
            self.path.chmod(0o600)
        else:
            self.fail("unknown fixture mutation")

    def test_mutation_during_origin_classification_refuses(self):
        actual = self.core.siamind.origin_class
        observed = []

        def classify(*args, **kwargs):
            result = actual(*args, **kwargs)
            if not observed:
                observed.append(args)
                self.mutate("content")
            return result

        with mock.patch.object(self.core.siamind, "origin_class", side_effect=classify):
            self.refuses()
        self.assertTrue(observed, "the real origin classification boundary was not exercised")

    def test_content_mutation_after_source_hash_finalization_refuses(self):
        observed = []

        def finalized(data):
            if data == RAW and not observed:
                observed.append(data)
                self.mutate("content")

        with mock.patch.object(self.core, "hashlib", _HashShim(finalized)):
            self.refuses()
        self.assertEqual(observed, [RAW])

    def assert_final_version_hash_mutation_refused(self, kind):
        expected = expected_page(self.slug, RAW, "evidence")
        observed = []

        def finalized(data):
            try:
                value = json.loads(data)
            except (ValueError, UnicodeError):
                return
            if isinstance(value, dict) and set(value) == VERSION_KEYS and not observed:
                self.assertEqual(value, {key: expected[key] for key in VERSION_KEYS})
                observed.append(value)
                self.mutate(kind)

        with mock.patch.object(self.core, "hashlib", _HashShim(finalized)):
            self.refuses()
        self.assertTrue(observed, "the final version digest boundary was not exercised")

    def test_content_mutation_after_final_version_hash_refuses(self):
        self.assert_final_version_hash_mutation_refused("content")

    def test_metadata_mutation_after_final_version_hash_refuses(self):
        self.assert_final_version_hash_mutation_refused("metadata")

    def test_identical_byte_leaf_replacement_after_final_version_hash_refuses(self):
        self.assert_final_version_hash_mutation_refused("leaf-name")

    def test_identical_byte_ancestor_replacement_after_final_version_hash_refuses(self):
        self.assert_final_version_hash_mutation_refused("ancestor-name")


if __name__ == "__main__":
    unittest.main()
