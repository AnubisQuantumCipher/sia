"""Consumer integration fixtures, not installed packing or migration authority."""

import contextlib
import json
from pathlib import Path
import unittest
from unittest import mock

from tests import test_event_pack_reader as lookup
from tests import test_consolidation_outcomes as outcomes


@contextlib.contextmanager
def captured_lookup(lib):
    """One lease/capture for a read-only operation; not an after-write view."""
    import siaeventplan
    with lib.corpus_owner():
        capture = siaeventplan._Capture(lib.__dict__, siaeventplan._Budget(lib.__dict__, 4096))

        def read(organ, identifier, *, dependency_capture=None):
            if lib._CORPUS_OWNER_DEPTH.get() <= 0:
                raise AssertionError("consumer lost corpus lease")
            if dependency_capture is not None and dependency_capture is not capture:
                raise AssertionError("consumer supplied a different capture")
            return lookup.reader.read_captured(lib.__dict__, organ, identifier, capture)

        try:
            with mock.patch.object(lib, "_read_event_index_entry", read):
                yield capture
                capture.current()
        finally:
            capture.close()


class PublicationReadback(unittest.TestCase):
    def setUp(self):
        self.fixture = lookup.CapturedEventPackTests(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.lib.CORPUS_OWNER_LOCK = str(Path(self.lib.STATE) / "consumer-owner.lock")

    def test_changed_entry_after_preflight_refuses(self):
        original = self.lib._read_event_index_entry
        changed = self.lib._event_index_encoded(
            dict(self.fixture.original, payload_sha256="f" * 64))
        calls = 0

        def read(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.fixture.legacy.write_bytes(changed)
            return original(*args, **kwargs)

        with self.lib.corpus_owner(), \
                mock.patch.object(self.lib, "_read_event_index_entry", read), \
                mock.patch.object(self.lib, "_before_corpus_mutation",
                                  side_effect=AssertionError("unexpected product write")):
            with self.assertRaisesRegex(ValueError, "conflicts with durable consolidation index"):
                self.lib._publish_event_index_entries([self.fixture.original])
        self.assertEqual(calls, 2)
        self.assertEqual(self.fixture.legacy.read_bytes(), changed)

    def test_packed_duplicate_preflight_and_publication_remain_read_only(self):
        self.fixture._write_pack()
        self.fixture.legacy.unlink()
        before = self.fixture.pack.read_bytes()
        with captured_lookup(self.lib), \
                mock.patch.object(self.lib, "_before_corpus_mutation",
                                  side_effect=AssertionError("packed duplicate rewritten")):
            self.lib._preflight_event_index_entries([self.fixture.original])
            self.lib._publish_event_index_entries([self.fixture.original])
            self.lib._publish_event_index_entries([self.fixture.original])
        self.assertFalse(self.fixture.legacy.exists())
        self.assertEqual(self.fixture.pack.read_bytes(), before)

    def test_packed_conflict_refuses_before_any_write(self):
        self.fixture._write_pack()
        self.fixture.legacy.unlink()
        changed = dict(self.fixture.original, payload_sha256="f" * 64)
        for name in ("_preflight_event_index_entries", "_publish_event_index_entries"):
            with self.subTest(operation=name), captured_lookup(self.lib), \
                    mock.patch.object(self.lib, "_before_corpus_mutation",
                                      side_effect=AssertionError("conflict reached write")):
                with self.assertRaisesRegex(ValueError, "conflicts with durable consolidation index"):
                    getattr(self.lib, name)([changed])
        self.assertFalse(self.fixture.legacy.exists())

    def test_malformed_pack_does_not_fall_back_during_preflight(self):
        self.fixture.pack.write_bytes(b"malformed")
        with captured_lookup(self.lib):
            with self.assertRaises(ValueError):
                self.lib._preflight_event_index_entries([self.fixture.original])
        self.assertEqual(self.fixture.legacy.read_bytes(), self.fixture.raw)

    def test_novel_legacy_write_needs_a_qualified_after_write_view(self):
        self.fixture._alternate_roster(2)
        first, second = lookup.siaeventpack.decode(
            self.fixture.pack.read_bytes(), "org", self.fixture.event_id[:3])
        self.fixture.pack.write_bytes(lookup.siaeventpack.encode(
            "org", self.fixture.event_id[:3], (first,)))
        entry = json.loads(second[1])
        target = Path(self.lib.CORPUS) / self.lib._event_index_relative("org", entry["event_id"])
        self.assertFalse(target.exists())
        # This read-only substitution is deliberately NOT a mutation protocol.
        # An error after the product's write cannot be reported as no effect.
        with self.assertRaisesRegex(ValueError, "source-absence-changed"), captured_lookup(self.lib):
            self.lib._publish_event_index_entries([entry])
        self.assertEqual(target.read_bytes(), second[1])
        self.assertEqual(self.fixture.pack.read_bytes(), lookup.siaeventpack.encode(
            "org", self.fixture.event_id[:3], (first,)))


class PackedConsolidationOutcomes(unittest.TestCase):
    def setUp(self):
        self.fixture = outcomes.ConsolidationOutcomes(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.pending = self.fixture.execute()
        self.expected = self.fixture.inspect()
        self.packs, self.legacy = self._pack_entries()

    def _pack_entries(self):
        epoch = self.lib._read_epoch_state("epochs/org/2026-w02")
        groups, legacy = {}, []
        for identifier in epoch["event_ids"]:
            path = Path(self.lib.CORPUS) / self.lib._event_index_relative("org", identifier)
            groups.setdefault(identifier[:3], []).append((identifier.encode(), path.read_bytes()))
            legacy.append(path)
        packs = []
        for prefix, records in sorted(groups.items()):
            path = Path(self.lib.CORPUS) / "event-packs" / "org" / prefix[:2] / (prefix + ".siaep")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(lookup.siaeventpack.encode("org", prefix, tuple(sorted(records))))
            packs.append(path)
        for path in legacy:
            path.unlink()
        return packs, legacy

    def test_actual_outcomes_match_legacy_without_ack_or_new_writes(self):
        with captured_lookup(self.lib):
            self.assertEqual(self.fixture.inspect(), self.expected)
            self.assertEqual(self.fixture.inspect(), self.expected)
        self.fixture.assert_pending_unchanged(self.pending)
        self.assertTrue(all(not path.exists() for path in self.legacy))

    def test_wrong_packed_payload_still_fails_exact_original_source_comparison(self):
        path = self.packs[0]
        prefix = path.stem
        records = list(lookup.siaeventpack.decode(path.read_bytes(), "org", prefix))
        identifier, raw = records[0]
        records[0] = (identifier, self.lib._event_index_encoded(
            dict(json.loads(raw), payload_sha256="f" * 64)))
        path.write_bytes(lookup.siaeventpack.encode("org", prefix, tuple(records)))
        with captured_lookup(self.lib):
            with self.assertRaisesRegex(ValueError, "exact event-index entry"):
                self.fixture.inspect()
        self.fixture.assert_pending_unchanged(self.pending)

    def test_later_missing_pack_refuses_without_claiming_complete_coverage(self):
        self.packs[-1].unlink()
        with captured_lookup(self.lib):
            with self.assertRaisesRegex(ValueError, "exact event-index entry"):
                self.fixture.inspect()
        self.fixture.assert_pending_unchanged(self.pending)


if __name__ == "__main__":
    unittest.main()
