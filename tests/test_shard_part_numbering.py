"""Shard part-numbering regression tests.

A day page overflows into continuation shards named ``YYYY-MM-DD-part-N.md``.
The part-number digit class ``[2-9][0-9]*`` accepted 2-9, 20-99, 200-999, ...
but rejected every number starting with 1: part-10 through part-19, 100-199,
and so on. On a day busy enough to cross nine shards, the tenth shard could
not be admitted (write refused), was invisible to the shard-set listing
(silently dropped from consolidation), and was rejected by the replay identity
gate (marker replayed forever), while the numeric ``MAX_EVENT_SHARDS`` bound
never saw the number at all.

These tests pin the repaired contract: any part number >= 2 is a well-formed
candidate, part-1 remains malformed (the base page carries no part suffix),
and the numeric bound -- not the digit class -- is what refuses oversized
numbers. Tests are red against the defective regex and green after it.
"""

import datetime
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")


def _load(name, path):
    if not path.endswith(".py"):
        loader = importlib.machinery.SourceFileLoader(name, path)
        spec = importlib.util.spec_from_loader(name, loader)
    else:
        spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sialib = _load("sialib_shard_parts_test", os.path.join(BIN, "sialib.py"))
siamind = _load("siamind_shard_parts_test", os.path.join(BIN, "siamind.py"))

EVENT_ID = "a" * 64
SEMANTIC_ID = "b" * 64


class EventSourceRegexAdmitsSecondDigitOne(unittest.TestCase):
    """Write admission: the slug regex must accept part numbers 10-19, 100-199."""

    def test_part_10_through_19_are_admissible_slugs(self):
        for part in (10, 11, 19):
            slug = f"events/org/2026-01-05-part-{part}.md"
            match = sialib.EVENT_SOURCE_RE.fullmatch(slug)
            self.assertIsNotNone(
                match, f"part-{part} slug must be admissible: {slug}")
            self.assertEqual(match.group("part"), str(part))

    def test_part_100_and_199_are_admissible_slugs(self):
        for part in (100, 199):
            slug = f"events/org/2026-01-05-part-{part}.md"
            match = sialib.EVENT_SOURCE_RE.fullmatch(slug)
            self.assertIsNotNone(match, slug)
            self.assertEqual(match.group("part"), str(part))

    def test_base_page_and_part_2_still_admissible(self):
        base = sialib.EVENT_SOURCE_RE.fullmatch("events/org/2026-01-05.md")
        self.assertIsNotNone(base)
        self.assertIsNone(base.group("part"))
        second = sialib.EVENT_SOURCE_RE.fullmatch(
            "events/org/2026-01-05-part-2.md")
        self.assertIsNotNone(second)
        self.assertEqual(second.group("part"), "2")

    def test_part_1_remains_malformed(self):
        # The base page carries no part suffix; "part-1" is not a name the
        # writer ever produces, and admitting it would alias the base page.
        self.assertIsNone(
            sialib.EVENT_SOURCE_RE.fullmatch("events/org/2026-01-05-part-1.md"))

    def test_oversized_part_number_still_refused_by_numeric_bound(self):
        # The digit class must not become the bound: a huge number is a
        # well-formed candidate that the numeric MAX_EVENT_SHARDS check
        # refuses, exactly as before.
        huge = "9" * 40
        match = sialib.EVENT_SOURCE_RE.fullmatch(
            f"events/org/2026-01-05-part-{huge}.md")
        self.assertIsNotNone(match)
        self.assertGreater(int(match.group("part")), sialib.MAX_EVENT_SHARDS)


class DayShardListingSeesTwoDigitParts(unittest.TestCase):
    """Consolidation listing: shards 10+ must appear, not silently vanish."""

    def test_listing_includes_parts_2_through_12(self):
        sialib_test = _load(
            "sialib_shard_parts_corpus", os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as corpus:
            sialib_test.CORPUS = corpus
            when = datetime.datetime(
                2026, 1, 5, 12, 0, tzinfo=datetime.timezone.utc)
            events = [
                sialib_test.Event(
                    "org", when, "obs", f"observation {number}",
                    occurrence=f"native:shard:{number}")
                for number in range(6000)
            ]
            sialib_test.update_day_page("org", "2026-01-05", events)

            states = sialib_test._event_day_shards("org", "2026-01-05")
            parts = [state["part"] for state in states]
            # ~450 events shard per page, so 6000 overflow past part-12.
            self.assertGreaterEqual(max(parts), 12)
            self.assertEqual(parts, list(range(1, max(parts) + 1)))

    def test_listing_still_refuses_huge_shard_numbers(self):
        sialib_test = _load(
            "sialib_shard_parts_huge", os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as corpus:
            sialib_test.CORPUS = corpus
            event_dir = os.path.join(corpus, "events", "org")
            os.makedirs(event_dir)
            with open(os.path.join(event_dir, "2026-01-05.md"), "w",
                      encoding="utf-8") as stream:
                stream.write("base\n")
            with open(os.path.join(
                    event_dir, f"2026-01-05-part-{'9' * 40}.md"), "w",
                    encoding="utf-8") as stream:
                stream.write("overflow\n")

            with self.assertRaisesRegex(
                    ValueError, "invalid or exceeds its bound"):
                sialib_test._event_day_shards("org", "2026-01-05")


class EventReplayKeyAdmitsTwoDigitParts(unittest.TestCase):
    """Replay identity: a part-10 day slug must not be called invalid."""

    def test_replay_key_accepts_part_10_and_part_11(self):
        for part in (10, 11):
            slug = f"events/org/2026-01-05-part-{part}"
            siamind._validate_event_replay_key(slug, EVENT_ID)

    def test_replay_key_accepts_part_100(self):
        siamind._validate_event_replay_key(
            "events/org/2026-01-05-part-100", EVENT_ID)

    def test_replay_key_still_refuses_part_1_and_garbage(self):
        with self.assertRaises(ValueError):
            siamind._validate_event_replay_key(
                "events/org/2026-01-05-part-1", EVENT_ID)
        with self.assertRaises(ValueError):
            siamind._validate_event_replay_key("not-a-day-slug", EVENT_ID)
        with self.assertRaises(ValueError):
            siamind._validate_event_replay_key(
                "events/org/2026-01-05-part-10", "nothex")


class OtherDayOccurrenceScanSeesTwoDigitParts(unittest.TestCase):
    """Cross-day identity scan: a part-11 page must be readable for dedupe."""

    def _corpus_with_marker_on_part_11(self, corpus):
        event_dir = os.path.join(corpus, "events", "org")
        os.makedirs(event_dir)
        marker = (f"- 12:00:00Z observed row "
                  f"<!-- sia-event:{EVENT_ID}:{SEMANTIC_ID} -->")
        with open(os.path.join(event_dir, "2026-01-05.md"), "w",
                  encoding="utf-8") as stream:
            stream.write("base, excluded from the scan\n")
        with open(os.path.join(event_dir, "2026-01-04-part-11.md"), "w",
                  encoding="utf-8") as stream:
            stream.write(marker + "\n")

    def test_occurrence_scan_finds_event_on_part_11(self):
        sialib_test = _load(
            "sialib_shard_parts_scan", os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as corpus:
            sialib_test.CORPUS = corpus
            self._corpus_with_marker_on_part_11(corpus)

            found = sialib_test._other_event_occurrences(
                "org", {EVENT_ID: True}, {"events/org/2026-01-05"})
            self.assertIn(EVENT_ID, found)
            self.assertEqual(
                found[EVENT_ID][0], "events/org/2026-01-04-part-11")


if __name__ == "__main__":
    unittest.main()
