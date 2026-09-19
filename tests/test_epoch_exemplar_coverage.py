"""Consolidation bounds must not erase a newly represented action class."""

import importlib.util
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


class EpochExemplarCoverage(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "sialib_epoch_exemplar_coverage", REPO / "bin/sialib.py")
        self.lib = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.lib)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.lib.SHARE = str(root / "share")
        self.lib.CORPUS = str(root / "share" / "corpus")
        self.lib.STATE = str(root / "state")
        Path(self.lib.CORPUS).mkdir(parents=True)
        Path(self.lib.STATE).mkdir()
        self.lib.log = lambda *_args: None
        patcher = mock.patch.multiple(
            self.lib.siamind, CORPUS=self.lib.CORPUS,
            MIND_PATH=str(root / "state" / "mind.json"),
            TOUCH_QUEUE=str(root / "state" / "touches.jsonl"),
            EPISODIC_DAYS=1)
        patcher.start()
        self.addCleanup(patcher.stop)
        subprocess.run(["git", "init", "-q", self.lib.CORPUS], check=True)
        self.epoch = Path(self.lib.corpus_path(
            self.lib._epoch_slug_for_day("org", "2026-01-05")))

    def _day(self, date, kinds):
        stamp = self.lib.datetime.datetime.fromisoformat(
            date + "T12:00:00+00:00")
        events = [self.lib.Event(
            "org", stamp, kind.lower(), f"{kind}:fixture {date}",
            occurrence=f"fixture:{date}:{kind}") for kind in kinds]
        self.lib.update_day_page("org", date, events)
        return Path(self.lib.corpus_path(f"events/org/{date}"))

    def _commit(self):
        subprocess.run(["git", "-C", self.lib.CORPUS, "add", "-A"],
                       check=True)
        subprocess.run([
            "git", "-C", self.lib.CORPUS, "-c", "user.email=t@t",
            "-c", "user.name=t", "commit", "-qm", "exemplar fixture"],
            check=True)

    def _routine_days(self):
        for date in ("2026-01-05", "2026-01-06", "2026-01-07",
                     "2026-01-08"):
            self._day(date, ("GENESIS", "INTENT", "OBS", "BOOT", "START",
                             "CHECK"))

    def test_weekly_cap_keeps_late_outcome_class(self):
        self._routine_days()
        self._day("2026-01-09", ("OUTCOME",))
        self._commit()

        self.lib.consolidate_corpus()

        text = self.epoch.read_text(encoding="utf-8")
        for kind in ("GENESIS", "INTENT", "OBS", "BOOT", "START", "CHECK",
                     "OUTCOME"):
            self.assertIn(kind + ":fixture", text)
        exemplars = text.split("## Exemplars", 1)[1].split("## Timeline", 1)[0]
        self.assertLessEqual(len([
            line for line in exemplars.splitlines() if line.startswith("- ")]),
            24)

    def test_extension_keeps_new_class_after_existing_full_gist(self):
        self._routine_days()
        self._commit()
        self.lib.consolidate_corpus()
        self.assertNotIn("OUTCOME:fixture", self.epoch.read_text())
        self._day("2026-01-09", ("OUTCOME",))
        self._commit()

        self.lib.consolidate_corpus()

        text = self.epoch.read_text(encoding="utf-8")
        self.assertIn("OUTCOME:fixture", text)
        self.assertIn("INTENT:fixture", text)

    def test_daily_anchors_cannot_displace_representable_kinds(self):
        kinds = ("OBS", "OBS", "GENESIS", "INTENT", "OUTCOME", "BOOT",
                 "START", "CHECK", "STOP", "OBS")
        lines = [f"- 12:00:00Z {kind}:fixture" for kind in kinds]

        selected = self.lib._epoch_exemplars(lines)

        self.assertEqual(
            {line.split()[2].split(":")[0] for line in selected}, set(kinds))
        self.assertLessEqual(len(selected), self.lib.MAX_EPOCH_EXEMPLARS)
        self.assertEqual(selected, sorted(selected, key=lines.index))

    def test_unrepresentable_day_retains_source_instead_of_partial_gist(self):
        source = self._day("2026-01-05", (
            "OBS", "GENESIS", "INTENT", "OUTCOME", "BOOT", "START",
            "CHECK", "STOP", "REFUSED"))
        before = source.read_bytes()
        self._commit()

        self.lib.consolidate_corpus()

        self.assertTrue(source.exists())
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse(self.epoch.exists())

    def test_consolidation_cannot_delete_a_source_changed_after_git_status(self):
        source = self._day("2026-01-05", ("OBS",))
        self._commit()
        real_run = self.lib._run_bounded_text_process
        changed = []

        def append_after_clean_status(*arguments, **options):
            result = real_run(*arguments, **options)
            if options.get("label") == "git source status" \
                    and result.returncode == 0 and not result.stdout.strip() \
                    and not changed:
                self._day("2026-01-05", ("OUTCOME",))
                changed.append(source.read_bytes())
            return result

        with mock.patch.object(
                self.lib, "_run_bounded_text_process",
                side_effect=append_after_clean_status):
            with self.assertRaisesRegex(
                    RuntimeError, "claim|lineage|changed"):
                self.lib.consolidate_corpus()

        self.assertTrue(changed)
        self.assertTrue(source.exists())
        self.assertEqual(source.read_bytes(), changed[0])
        self.assertFalse(self.epoch.exists())


if __name__ == "__main__":
    unittest.main()
