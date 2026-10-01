"""Epoch completeness needs retained source coverage and one observed file."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home


REPO = Path(__file__).resolve().parents[1]


class EpochCompletenessIntegrity(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "sialib_epoch_completeness_integrity", REPO / "bin/sialib.py")
        self.lib = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.lib)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lib.CORPUS = self.tmp.name
        self.lib.log = lambda *_args: None
        for name, value in (
                ("MIND_PATH", os.path.join(self.tmp.name, "mind.json")),
                ("EPISODIC_DAYS", 1)):
            prior = getattr(self.lib.siamind, name)
            self.addCleanup(setattr, self.lib.siamind, name, prior)
            setattr(self.lib.siamind, name, value)
        self.slug = self.lib._epoch_slug_for_day("org", "2026-01-05")
        self.path = Path(self.lib.corpus_path(self.slug))
        self.path.parent.mkdir(parents=True)

    def _epoch(self, *, sources=None, manifest=None, event_ids=None,
               day_count=1):
        fields = ["type: epoch", 'title: "epoch fixture"', "tags: [org]",
                  "date: 2026-01-05", 'sia_dates: ["2026-01-05"]',
                  'sia_counts: {"obs": 1}']
        for name, value in (("sia_sources", sources),
                            ("sia_source_manifest", manifest),
                            ("sia_event_ids", event_ids)):
            if value is not None:
                fields.append(name + ": " + json.dumps(value))
        text = ("---\n" + "\n".join(fields) + "\n---\n# epoch\n\n"
                f"Consolidated from {day_count} day-memories "
                "(2026-01-05 … 2026-01-05).\n")
        self.path.write_text(text, encoding="utf-8")
        return text

    def _record(self, source_id="a" * 64):
        return {"rel": "events/org/2026-01-05.md", "sha256": source_id}

    def _item(self, record):
        _organ, date, part = self.lib._event_source_parts(record["rel"])
        return (date, "unused", "", set(), record["sha256"],
                record["rel"], part)

    def test_declared_event_completeness_cannot_cover_source_subset(self):
        self._epoch(sources=["a" * 64, "b" * 64],
                    manifest=[self._record()], event_ids=["c" * 64])
        with self.assertRaisesRegex(RuntimeError, "source lineage"):
            self.lib._read_epoch_state(self.slug)

    def test_declared_completeness_cannot_erase_unidentified_legacy_days(self):
        self._epoch(sources=[], manifest=[], event_ids=[], day_count=1)
        with self.assertRaisesRegex(RuntimeError, "source lineage"):
            self.lib._read_epoch_state(self.slug)

    def test_upgrade_requires_prior_hashes_missing_from_partial_manifest(self):
        self._epoch(sources=["a" * 64, "b" * 64],
                    manifest=[self._record()])
        state = self.lib._read_epoch_state(self.slug)
        with self.assertRaisesRegex(
                self.lib.ConsolidationCompletenessError,
                "cannot be reconstructed"):
            self.lib._merge_epoch_event_ids(
                state, [self._item(self._record())],
                [{"event_id": "c" * 64}])

    def test_exact_retained_sources_can_upgrade_partial_manifest(self):
        first = self._record()
        second = {"rel": "events/org/2026-01-05-part-2.md",
                  "sha256": "b" * 64}
        self._epoch(sources=[first["sha256"], second["sha256"]],
                    manifest=[first])
        state = self.lib._read_epoch_state(self.slug)
        self.assertEqual(self.lib._merge_epoch_event_ids(
            state, [self._item(first), self._item(second)],
            [{"event_id": "c" * 64}]), ["c" * 64])

    def test_unidentified_legacy_days_keep_epoch_and_live_source_unchanged(self):
        before = self._epoch()
        stamp = self.lib.datetime.datetime(
            2026, 1, 6, 12, tzinfo=self.lib.datetime.timezone.utc)
        event = self.lib.Event(
            "org", stamp, "obs", "new exact source",
            occurrence="native:unknown-legacy:extension")
        self.lib.update_day_page("org", "2026-01-06", [event])
        source = Path(self.lib.corpus_path("events/org/2026-01-06"))
        source_before = source.read_bytes()
        subprocess.run(["git", "init", "-q", self.tmp.name], check=True)
        subprocess.run(["git", "-C", self.tmp.name, "add", "-A"], check=True)
        subprocess.run([
            "git", "-C", self.tmp.name, "-c", "user.email=t@t", "-c",
            "user.name=t", "commit", "-qm", "epoch fixture"], check=True)

        self.assertEqual(self.lib.consolidate_corpus(), (0, 0, 1))

        self.assertEqual(self.path.read_text(encoding="utf-8"), before)
        self.assertEqual(source.read_bytes(), source_before)
        self.assertFalse((Path(self.tmp.name) / "event-index").exists())

    def test_genuinely_absent_epoch_can_admit_first_exact_source(self):
        state = self.lib._read_epoch_state(self.slug)
        self.assertEqual(state["text"], "")
        self.assertEqual(self.lib._merge_epoch_event_ids(
            state, [self._item(self._record())],
            [{"event_id": "c" * 64}]), ["c" * 64])

    def test_enumerated_epoch_cannot_disappear_or_become_legacy(self):
        event_id = "c" * 64
        real_snapshot = self.lib._bounded_event_directory_snapshot
        for mutation in ("vanish", "directory", "symlink", "replace",
                         "same_inode_rewrite"):
            with self.subTest(mutation=mutation):
                if self.path.is_symlink() or self.path.is_file():
                    self.path.unlink()
                elif self.path.is_dir():
                    self.path.rmdir()
                self._epoch(sources=["a" * 64], manifest=[self._record()],
                            event_ids=[event_id])

                def change_after_snapshot(root):
                    entries = real_snapshot(root)
                    if mutation == "same_inode_rewrite":
                        prior = self.path.stat()
                        self._epoch(sources=["a" * 64])
                        os.utime(self.path, ns=(prior.st_atime_ns,
                                               prior.st_mtime_ns))
                    else:
                        held = self.path.with_suffix(".held")
                        os.replace(self.path, held)
                        if mutation == "directory":
                            self.path.mkdir()
                        elif mutation == "symlink":
                            self.path.symlink_to(held)
                        elif mutation == "replace":
                            self._epoch(sources=["a" * 64])
                    return entries

                with mock.patch.object(
                        self.lib, "_bounded_event_directory_snapshot",
                        side_effect=change_after_snapshot):
                    with self.assertRaisesRegex(
                            (RuntimeError, ValueError, OSError),
                            "changed|regular|safely"):
                        self.lib._missing_event_index_expectations(
                            "org", {event_id})

    def test_same_inode_equal_size_rewrite_after_open_is_refused(self):
        event_id = "c" * 64
        before = self._epoch(sources=["a" * 64], manifest=[self._record()],
                             event_ids=[event_id])
        changed = before.replace(event_id, "d" * 64)
        self.assertEqual(len(changed), len(before))
        real_fdopen = self.lib.os.fdopen
        mutated = []

        def rewrite_before_read(fd, *args, **kwargs):
            if not mutated and os.readlink(f"/proc/self/fd/{fd}") \
                    == str(self.path):
                prior = self.path.stat()
                self.path.write_text(changed, encoding="utf-8")
                os.utime(self.path, ns=(prior.st_atime_ns, prior.st_mtime_ns))
                mutated.append(True)
            return real_fdopen(fd, *args, **kwargs)

        local_os = SimpleNamespace(**vars(os))
        local_os.fdopen = rewrite_before_read
        with mock.patch.object(self.lib, "os", local_os):
            self.assertIs(os.fdopen, real_fdopen)
            with self.assertRaisesRegex(
                    (RuntimeError, ValueError), "changed"):
                self.lib._missing_event_index_expectations("org", {event_id})
        self.assertEqual(mutated, [True])

    def test_name_replacement_after_descriptor_read_is_refused(self):
        event_id = "c" * 64
        self._epoch(sources=["a" * 64], manifest=[self._record()],
                    event_ids=[event_id])
        real_fstat = self.lib.os.fstat
        observed = []

        def replace_after_read(fd):
            info = real_fstat(fd)
            if os.readlink(f"/proc/self/fd/{fd}") == str(self.path):
                observed.append(info)
                if len(observed) == 2:
                    os.replace(self.path, self.path.with_suffix(".held"))
                    self._epoch(sources=["a" * 64])
            return info

        local_os = SimpleNamespace(**vars(os))
        local_os.fstat = replace_after_read
        with mock.patch.object(self.lib, "os", local_os):
            self.assertIs(os.fstat, real_fstat)
            with self.assertRaisesRegex(
                    (RuntimeError, ValueError), "changed"):
                self.lib._missing_event_index_expectations("org", {event_id})
        self.assertTrue(observed)


if __name__ == "__main__":
    unittest.main()
