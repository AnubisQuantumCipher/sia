"""Dual-format candidate through real temporary corpus and dependency capture."""

from pathlib import Path
from types import ModuleType
import json
import unittest
from unittest import mock

from tests import test_event_pack as pack_fixtures

siaeventpack = pack_fixtures.siaeventpack


SOURCE = Path(__file__).resolve().parents[1] / "bin/siaeventpackreader.py"
reader = ModuleType("siaeventpackreader")
with mock.patch.dict("sys.modules", {"siaeventpack": siaeventpack}):
    exec(compile(SOURCE.read_bytes(), str(SOURCE), "exec"), reader.__dict__)


class CapturedEventPackTests(unittest.TestCase):
    def setUp(self):
        fixture = pack_fixtures.LegacyEntryEquivalence(methodName="runTest")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        self.lib, self.event_id = fixture.lib, fixture.event_id
        self.legacy = fixture.path
        self.raw = self.legacy.read_bytes()
        self.original = self.lib._read_event_index_entry("org", self.event_id)
        self.pack = (Path(self.lib.CORPUS) / "event-packs" / "org"
                     / self.event_id[:2] / (self.event_id[:3] + ".siaep"))
        self.pack.parent.mkdir(parents=True)

    def _write_pack(self, raw=None, key=None):
        self.pack.write_bytes(siaeventpack.encode(
            "org", self.event_id[:3],
            (((key or self.event_id).encode(), self.raw if raw is None else raw),)))

    def _capture(self):
        from siaeventplan import _Budget, _Capture
        capture = _Capture(self.lib.__dict__, _Budget(self.lib.__dict__, 4096))
        self.addCleanup(capture.close)
        return capture

    def _read(self, capture=None):
        capture = self._capture() if capture is None else capture
        result = reader.read_captured(self.lib.__dict__, "org", self.event_id, capture)
        capture.current()
        return result

    def test_legacy_only_exact_duplicate_and_pack_only_match_original(self):
        self.assertEqual(self._read(), self.original)
        self._write_pack()
        self.assertEqual(self._read(), self.original)
        self.legacy.unlink()
        self.assertEqual(self._read(), self.original)
        self.assertIsNone(self.lib._read_event_index_entry("org", self.event_id))

    def test_both_absent_remains_absent(self):
        self.legacy.unlink()
        self.assertIsNone(self._read())

    def _alternate_roster(self, count):
        """Controlled canonical roster, not evidence of captured occurrences."""
        identifiers = [self.event_id[:3] + f"{index:061x}" for index in range(count)]
        self.assertNotIn(self.event_id, identifiers)
        epoch = Path(self.lib.corpus_path(self.original["epoch_slug"]))
        lines = epoch.read_text().splitlines(keepends=True)
        lines = [("sia_event_ids: " + json.dumps(identifiers + [self.event_id]) + "\n")
                 if line.startswith("sia_event_ids:") else line for line in lines]
        epoch.write_text("".join(lines))
        records = tuple((key.encode(), self.lib._event_index_encoded(
            dict(self.original, event_id=key))) for key in identifiers)
        self.pack.write_bytes(siaeventpack.encode("org", self.event_id[:3], records))

    def test_full_pack_keeps_unrepresented_legacy_entry_readable(self):
        self._alternate_roster(64)
        self.assertEqual(self._read(), self.original)
        self.legacy.unlink()
        self.assertIsNone(self._read())

    def test_nonselected_entry_with_invalid_lineage_refuses(self):
        self._alternate_roster(1)
        records = siaeventpack.decode(self.pack.read_bytes(), "org", self.event_id[:3])
        key, raw = records[0]
        invalid = dict(json.loads(raw), source_sha256="f" * 64)
        self.pack.write_bytes(siaeventpack.encode("org", self.event_id[:3], (
            (key, self.lib._event_index_encoded(invalid)),)))
        with self.assertRaisesRegex(ValueError, "exact epoch lineage"):
            self._read()

    def test_valid_selected_record_does_not_skip_later_invalid_record(self):
        key = self.event_id[:3] + "f" * 61
        self.assertLess(self.event_id, key)
        invalid = dict(self.original, event_id=key, source_sha256="f" * 64)
        records = ((self.event_id.encode(), self.raw),
                   (key.encode(), self.lib._event_index_encoded(invalid)))
        self.pack.write_bytes(siaeventpack.encode("org", self.event_id[:3], records))
        with self.assertRaisesRegex(ValueError, "exact epoch lineage"):
            self._read()

    def test_structurally_invalid_pack_cannot_fall_back_to_valid_legacy(self):
        for raw in (b"", b"not a pack", b"x" * (siaeventpack.MAX_BYTES + 1)):
            with self.subTest(size=len(raw)):
                self.pack.write_bytes(raw)
                with self.assertRaises(ValueError):
                    self._read()

    def test_rehashed_forged_lineage_cannot_fall_back(self):
        forged = dict(self.original, source_sha256="f" * 64)
        self._write_pack(self.lib._event_index_encoded(forged))
        with self.assertRaisesRegex(ValueError, "exact epoch lineage"):
            self._read()

    def test_canonical_but_conflicting_duplicates_refuse(self):
        forged = dict(self.original, payload_sha256="f" * 64)
        self._write_pack(self.lib._event_index_encoded(forged))
        with self.assertRaisesRegex(ValueError, "representations conflict"):
            self._read()

    def test_noncanonical_inner_bytes_refuse(self):
        self._write_pack(self.raw + b" ")
        with self.assertRaisesRegex(ValueError, "path binding"):
            self._read()

    def test_inner_outer_identity_mismatch_refuses(self):
        other = self.event_id[:3] + ("f" if self.event_id[3] != "f" else "e") * 61
        self._write_pack(key=other)
        with self.assertRaisesRegex(ValueError, "path binding"):
            self._read()

    def test_current_record_limit_is_reapplied_on_same_capture(self):
        self._write_pack()
        self.legacy.unlink()
        capture = self._capture()
        self.assertEqual(self._read(capture), self.original)
        with mock.patch.object(self.lib, "MAX_EVENT_INDEX_BYTES", len(self.raw) - 1):
            with self.assertRaisesRegex(ValueError, "exceeds its bound"):
                self._read(capture)

    def test_current_epoch_policy_is_reapplied(self):
        self._write_pack()
        self.legacy.unlink()
        capture = self._capture()
        self.assertEqual(self._read(capture), self.original)
        with mock.patch.object(self.lib, "_read_epoch_state",
                               side_effect=ValueError("fresh epoch refusal")):
            with self.assertRaisesRegex(ValueError, "fresh epoch refusal"):
                self._read(capture)

    def test_shared_validator_binds_each_owner_and_parent_patch(self):
        from tests import test_epoch_module_ownership as ownership
        other = ownership._load_core("sialib_pack_reader_other")
        helper = self.lib._validate_event_index_raw.__wrapped__
        self.assertIs(other._validate_event_index_raw.__wrapped__, helper)
        state = self.lib._read_epoch_state(self.original["epoch_slug"])
        with mock.patch.object(other, "_read_epoch_state", return_value=state), \
                mock.patch.object(self.lib, "MAX_EVENT_INDEX_BYTES", 1):
            for owner in (other, self.lib, other):
                if owner is self.lib:
                    with self.assertRaisesRegex(ValueError, "exceeds its bound"):
                        owner._validate_event_index_raw(self.raw, "org", self.event_id)
                else:
                    self.assertEqual(owner._validate_event_index_raw(
                        self.raw, "org", self.event_id), self.original)
        with mock.patch.object(self.lib, "_validate_event_index_raw",
                               side_effect=ValueError("parent validator refusal")):
            with self.assertRaisesRegex(ValueError, "parent validator refusal"):
                self.lib._read_event_index_entry("org", self.event_id)
        self.assertEqual(self.lib._read_event_index_entry("org", self.event_id),
                         self.original)

    def test_missing_legacy_appearing_during_validation_refuses(self):
        self._write_pack()
        self.legacy.unlink()
        original = self.lib._read_epoch_state

        def inject(slug, **kwargs):
            self.legacy.write_bytes(self.raw)
            return original(slug, **kwargs)

        with mock.patch.object(self.lib, "_read_epoch_state", inject):
            with self.assertRaisesRegex(ValueError, "source-absence-changed"):
                self._read()

    def test_missing_pack_appearing_during_validation_refuses(self):
        original = self.lib._read_epoch_state

        def inject(slug, **kwargs):
            self._write_pack()
            return original(slug, **kwargs)

        with mock.patch.object(self.lib, "_read_epoch_state", inject):
            with self.assertRaisesRegex(ValueError, "source-absence-changed"):
                self._read()

    def test_pack_replaced_during_validation_refuses(self):
        self._write_pack()
        original = self.lib._read_epoch_state

        def inject(slug, **kwargs):
            replacement = self.pack.with_suffix(".new")
            replacement.write_bytes(self.pack.read_bytes())
            replacement.replace(self.pack)
            return original(slug, **kwargs)

        with mock.patch.object(self.lib, "_read_epoch_state", inject):
            with self.assertRaisesRegex(ValueError, "source-generation-changed"):
                self._read()

    def test_symlink_pack_or_parent_refuses(self):
        self._write_pack()
        held = self.pack.with_suffix(".held")
        self.pack.rename(held)
        self.pack.symlink_to(held)
        with self.assertRaises((ValueError, OSError)):
            self._read()
        self.pack.unlink()
        held.rename(self.pack)
        directory = self.pack.parent
        retained = directory.with_name(directory.name + "-held")
        directory.rename(retained)
        directory.symlink_to(retained, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            self._read()


if __name__ == "__main__":
    unittest.main()
