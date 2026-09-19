"""Event novelty and epoch completeness require every declared source day."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home


REPO = Path(__file__).resolve().parents[1]


class EventEpochAdmissionIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        spec = importlib.util.spec_from_file_location(
            "sialib_event_epoch_admission", REPO / "bin/sialib.py")
        self.lib = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.lib)
        self.lib.CORPUS = str(self.root / "corpus")
        Path(self.lib.CORPUS).mkdir()
        self.lib.STATE = str(self.root / "state")
        Path(self.lib.STATE).mkdir()
        self.lib.log = lambda *_args: None
        for name, value in (
                ("MIND_PATH", str(self.root / "state" / "mind.json")),
                ("EPISODIC_DAYS", 1)):
            prior = getattr(self.lib.siamind, name)
            self.addCleanup(setattr, self.lib.siamind, name, prior)
            setattr(self.lib.siamind, name, value)
        self.epoch_slug = self.lib._epoch_slug_for_day("org", "2026-01-05")

    def _event(self, day, occurrence="native:admission:retained"):
        stamp = self.lib.datetime.datetime.fromisoformat(day + "T12:00:00+00:00")
        return self.lib.Event("org", stamp, "obs", "retained observation",
                              occurrence=occurrence)

    def _source(self, day="2026-01-05", occurrence="native:admission:retained"):
        event = self._event(day, occurrence)
        self.lib.update_day_page("org", day, [event])
        relative = f"events/org/{day}.md"
        path = Path(self.lib.CORPUS) / relative
        raw = path.read_bytes()
        digest = hashlib.sha256(relative.encode() + b"\0" + raw).hexdigest()
        return event, path, {"rel": relative, "sha256": digest}

    def _epoch(self, record, *, dates, day_count, event_ids):
        fields = [
            "type: epoch", 'title: "retained epoch"', "tags: [org, obs]",
            "date: 2026-01-05", 'sia_counts: {"obs": 1}',
            "sia_sources: " + json.dumps([record["sha256"]]),
            "sia_source_manifest: " + json.dumps([record]),
            "sia_dates: " + json.dumps(dates),
        ]
        if event_ids is not None:
            fields.append("sia_event_ids: " + json.dumps(event_ids))
        text = ("---\n" + "\n".join(fields) + "\n---\n# epoch\n\n"
                f"Consolidated from {day_count} day-memories "
                "(2026-01-05 … 2026-01-06).\n")
        path = Path(self.lib.corpus_path(self.epoch_slug))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _commit_corpus(self):
        subprocess.run(["git", "init", "-q", self.lib.CORPUS], check=True)
        subprocess.run(["git", "-C", self.lib.CORPUS, "add", "-A"], check=True)
        subprocess.run([
            "git", "-C", self.lib.CORPUS, "-c", "user.email=t@t", "-c",
            "user.name=t", "commit", "-qm", "retained event fixture"], check=True)

    def test_declared_completeness_requires_every_declared_date(self):
        event, _path, record = self._source()
        self._epoch(record, dates=["2026-01-05", "2026-01-06"],
                    day_count=2, event_ids=[self.lib.event_memory_identity(event)])

        with self.assertRaises((RuntimeError, ValueError)):
            self.lib._read_epoch_state(self.epoch_slug)

    def test_declared_day_count_cannot_exceed_exact_source_days(self):
        event, _path, record = self._source()
        self._epoch(record, dates=["2026-01-05"], day_count=2,
                    event_ids=[self.lib.event_memory_identity(event)])

        with self.assertRaises((RuntimeError, ValueError)):
            self.lib._read_epoch_state(self.epoch_slug)

    def test_partial_legacy_day_coverage_retains_epoch_and_live_sources(self):
        _event, old_path, record = self._source()
        _new, new_path, _new_record = self._source(
            "2026-01-07", "native:admission:new")
        epoch = self._epoch(record, dates=["2026-01-05", "2026-01-06"],
                            day_count=2, event_ids=None)
        before = {path: path.read_bytes() for path in (epoch, old_path, new_path)}
        self._commit_corpus()

        result = self.lib.consolidate_corpus()

        self.assertEqual(result[:2], (0, 0))
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertFalse((Path(self.lib.CORPUS) / "event-index").exists())

    def test_complete_retained_day_can_upgrade_and_extend(self):
        _event, old_path, record = self._source()
        _new, new_path, _new_record = self._source(
            "2026-01-07", "native:admission:new")
        self._epoch(record, dates=["2026-01-05"], day_count=1, event_ids=None)
        self._commit_corpus()

        self.lib.consolidate_corpus()

        state = self.lib._read_epoch_state(self.epoch_slug)
        self.assertEqual(state["dates"], ["2026-01-05", "2026-01-07"])
        self.assertTrue(state["event_ids_declared"])
        self.assertFalse(old_path.exists())
        self.assertFalse(new_path.exists())

    def test_nonregular_historical_day_cannot_be_skipped_as_novel(self):
        _event, source, _record = self._source()
        retained = source.with_suffix(".held")
        source.rename(retained)
        source.symlink_to(retained)
        replay = self._event("2026-01-07")
        target = Path(self.lib.corpus_path("events/org/2026-01-07"))

        with self.assertRaises((RuntimeError, ValueError, OSError)):
            self.lib.update_day_page("org", "2026-01-07", [replay])

        self.assertFalse(target.exists())
        self.assertTrue(source.is_symlink())
        self.assertTrue(retained.is_file())

    def test_nonregular_base_day_cannot_be_replaced_with_fresh_history(self):
        _event, source, _record = self._source()
        retained = source.with_suffix(".held")
        source.rename(retained)
        source.symlink_to(retained)
        original = retained.read_bytes()
        new_event = self._event("2026-01-05", "native:admission:new")

        with self.assertRaises((RuntimeError, ValueError, OSError)):
            self.lib.update_day_page("org", "2026-01-05", [new_event])

        self.assertTrue(source.is_symlink())
        self.assertEqual(retained.read_bytes(), original)

    def test_malformed_historical_identity_cannot_be_skipped_as_novel(self):
        _event, source, _record = self._source()
        malformed = source.read_text(encoding="utf-8").replace(
            "<!-- sia-event:", "<!-- sia-event:broken-")
        source.write_text(malformed, encoding="utf-8")
        target = Path(self.lib.corpus_path("events/org/2026-01-07"))

        with self.assertRaises((RuntimeError, ValueError)):
            self.lib.update_day_page("org", "2026-01-07", [self._event("2026-01-07")])

        self.assertFalse(target.exists())
        self.assertEqual(source.read_text(encoding="utf-8"), malformed)

    def test_enumerated_historical_day_must_match_the_bounded_read(self):
        event, source, _record = self._source()
        event_id = self.lib.event_memory_identity(event)
        original = self.lib._read_event_page
        mutated = []

        def change_before_read(slug, **kwargs):
            if slug == "events/org/2026-01-05" and not mutated:
                info = source.stat()
                text = source.read_text(encoding="utf-8")
                source.write_text(text.replace(event_id, "f" * 64), encoding="utf-8")
                os.utime(source, ns=(info.st_atime_ns, info.st_mtime_ns))
                mutated.append(slug)
            return original(slug, **kwargs)

        with mock.patch.object(self.lib, "_read_event_page", change_before_read):
            with self.assertRaises((RuntimeError, ValueError)):
                self.lib.update_day_page(
                    "org", "2026-01-07", [self._event("2026-01-07")])

        self.assertEqual(mutated, ["events/org/2026-01-05"])
        self.assertFalse(Path(self.lib.corpus_path("events/org/2026-01-07")).exists())

    def test_index_leaf_replaced_during_epoch_validation_is_refused(self):
        event, _source, _record = self._source()
        self._commit_corpus()
        self.lib.consolidate_corpus()
        event_id = self.lib.event_memory_identity(event)
        index = Path(self.lib.CORPUS) / self.lib._event_index_relative("org", event_id)
        original = self.lib._read_epoch_state
        changed = []

        def replace_after_index_read(slug, **kwargs):
            if not changed:
                retained = index.with_suffix(".held")
                index.rename(retained)
                index.write_bytes(retained.read_bytes())
                changed.append(retained)
            return original(slug, **kwargs)

        with mock.patch.object(self.lib, "_read_epoch_state", replace_after_index_read):
            with self.assertRaises((RuntimeError, ValueError)):
                self.lib._read_event_index_entry("org", event_id)

        self.assertTrue(changed)
        self.assertEqual(index.read_bytes(), changed[0].read_bytes())


if __name__ == "__main__":
    unittest.main()
