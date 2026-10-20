"""Observed source outcomes must not hide missing index or original evidence."""
import json
from pathlib import Path
import re
import subprocess
import unittest
from unittest import mock

from tests import test_consolidation_delivery_execution as execution_fixture


class ConsolidationOutcomes(unittest.TestCase):
    def setUp(self):
        self.fixture = execution_fixture.ConsolidationDeliveryExecution(
            methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.delivery = self.fixture.delivery
        self.discovery = self.fixture.fixture.fixture
        self.sources = self.fixture.sources
        self.epoch = self.fixture.epoch
        self.journal = self.fixture.path

    def inspect(self):
        return self.delivery.inspect_outcomes(self.lib, self.fixture.record)

    def execute(self):
        self.fixture.stage()
        self.fixture.execute()
        return self.journal.read_bytes()

    def leaf(self):
        epoch = self.lib._read_epoch_state("epochs/org/2026-w02")
        identity = epoch["event_ids"][0]
        return identity, Path(self.lib.CORPUS) / self.lib._event_index_relative(
            "org", identity)

    def assert_pending_unchanged(self, before):
        self.assertEqual(self.journal.read_bytes(), before)
        self.assertEqual(self.fixture.memo_path.read_bytes(),
                         self.fixture.memo_bytes)

    def test_selected_compacted_outcomes_are_recomputed_without_ack(self):
        before = self.execute()
        epoch = self.epoch.read_bytes()
        result = self.inspect()
        self.assertEqual(result["coverage"], "selected-claims-only")
        self.assertEqual(result["admission"], self.fixture.record)
        self.assertEqual(result["unclaimed_days"], [])
        self.assertEqual([item["date"] for item in result["outcomes"]],
                         ["2026-01-05", "2026-01-06", "2026-01-07"])
        for item in result["outcomes"]:
            self.assertEqual(item["disposition"], "compacted")
            self.assertEqual(item["epoch"], "epochs/org/2026-w02")
            self.assertEqual(len(item["sources"]), 1)
        original = self.inspect()
        result["outcomes"].clear()
        self.assertEqual(self.inspect(), original)
        self.assertEqual(self.epoch.read_bytes(), epoch)
        self.assert_pending_unchanged(before)

    def test_mixed_retained_and_compacted_days_have_distinct_outcomes(self):
        self.fixture.stage()
        protected = self.sources[0]
        pin = protected.relative_to(self.lib.CORPUS).as_posix()[:-3]
        original = protected.read_bytes()
        with mock.patch.object(self.lib.siamind, "pending_user_pin_slugs",
                               return_value={pin}):
            self.fixture.execute()
        before = self.journal.read_bytes()
        result = self.inspect()
        self.assertEqual([item["disposition"] for item in result["outcomes"]],
                         ["retained", "compacted", "compacted"])
        self.assertIsNone(result["outcomes"][0]["epoch"])
        self.assertEqual(protected.read_bytes(), original)
        self.assert_pending_unchanged(before)

    def test_missing_index_refuses_even_after_a_previous_successful_observation(self):
        before = self.execute()
        expected = self.inspect()
        identity, leaf = self.leaf()
        raw = leaf.read_bytes()
        leaf.unlink()
        self.assertIsNone(self.lib._read_event_index_entry("org", identity))
        with self.assertRaisesRegex(ValueError, "exact event-index entry"):
            self.inspect()
        self.assertFalse(leaf.exists())
        self.assert_pending_unchanged(before)
        leaf.write_bytes(raw)
        self.assertEqual(self.inspect(), expected)

    def test_structurally_valid_wrong_event_entry_refuses(self):
        before = self.execute()
        identity, leaf = self.leaf()
        entry = self.lib._read_event_index_entry("org", identity)
        changed = dict(entry, payload_sha256="0" * 64)
        self.assertNotEqual(changed, entry)
        leaf.write_bytes(self.lib._event_index_encoded(changed))
        self.assertEqual(self.lib._read_event_index_entry("org", identity), changed)
        with self.assertRaisesRegex(ValueError, "exact event-index entry"):
            self.inspect()
        self.assert_pending_unchanged(before)

    def test_omitted_epoch_roster_cannot_hide_original_source_events(self):
        before = self.execute()
        text, count = re.subn(r"^sia_event_ids: .*$", "sia_event_ids: []",
                             self.epoch.read_text(), flags=re.M)
        self.assertEqual(count, 1)
        self.epoch.write_text(text)
        self.assertEqual(self.lib._read_epoch_state(
            "epochs/org/2026-w02")["event_ids"], [])
        with self.assertRaisesRegex(ValueError, "epoch event completeness"):
            self.inspect()
        self.assert_pending_unchanged(before)

    def test_later_live_claim_uses_exact_history_and_refuses_after_that_history_is_lost(self):
        source = self.sources[0]
        source.write_bytes(source.read_bytes() + b"\nnew live version\n")
        self.discovery.fixture._commit()
        newer = self.discovery.git("rev-parse", "HEAD")
        self.assertNotEqual(newer, self.fixture.record["commit"])
        before = self.execute()
        self.assertEqual(self.inspect()["outcomes"][0]["disposition"], "compacted")
        self.discovery.git("add", "-u")
        tree = self.discovery.git("write-tree")
        root = self.discovery.git("-c", "user.name=Fixture",
                                  "-c", "user.email=t@t", "commit-tree",
                                  tree, "-m", "independent fixture root")
        self.discovery.git("update-ref", "HEAD", root)
        self.discovery.git("reflog", "expire", "--expire=now", "--all")
        self.discovery.git("gc", "--prune=now", "--quiet")
        self.assertEqual(self.discovery.git("cat-file", "-t", root), "commit")
        gone = subprocess.run(
            ["git", "-C", self.lib.CORPUS, "cat-file", "-e", newer],
            capture_output=True, timeout=10)
        self.assertEqual((gone.returncode, gone.stdout, gone.stderr), (1, b"", b""))
        with self.assertRaisesRegex(ValueError, "original is unavailable"):
            self.inspect()
        self.assert_pending_unchanged(before)

    def test_history_budget_exhaustion_refuses_without_claiming_original_absence(self):
        source = self.sources[0]
        raw = source.read_bytes() + b"\nnewer claimed version\n"
        source.write_bytes(raw)
        self.discovery.fixture._commit()
        version = self.discovery.git("rev-parse", "HEAD")
        before = self.execute()
        self.assertEqual(self.lib.corpus_commit("record fixture cleanup"), "committed")
        expected = self.inspect()
        with mock.patch.object(self.delivery.outcomes, "MAX_HISTORY_COMMITS", 1):
            with self.assertRaisesRegex(ValueError, "original is unavailable"):
                self.inspect()
        relative = source.relative_to(self.lib.CORPUS).as_posix()
        self.assertEqual(subprocess.check_output(
            ["git", "-C", self.lib.CORPUS, "cat-file", "blob",
             version + ":" + relative], timeout=10), raw)
        self.assertEqual(self.inspect(), expected)
        self.assert_pending_unchanged(before)

    def test_malformed_oversized_or_failed_history_results_refuse(self):
        self.sources[0].write_bytes(
            self.sources[0].read_bytes() + b"\nnew claimed bytes\n")
        self.discovery.fixture._commit()
        before = self.execute()
        expected = self.inspect()
        run = self.lib._run_bounded_text_process
        oversized = (self.fixture.record["commit"] + "\n") * 65
        for code, stdout, stderr, message in (
                (1, "", "failure", "history is unavailable"),
                (0, "bad-identity\n", "", "full object identity"),
                (0, oversized, "", "history exceeds its bound"),
                (0, "", "unexpected warning\n", "unexpected diagnostic")):
            def injected(command, **kwargs):
                if "log" in command:
                    return subprocess.CompletedProcess(
                        command, code, stdout=stdout, stderr=stderr)
                return run(command, **kwargs)
            with self.subTest(message=message), mock.patch.object(
                    self.lib, "_run_bounded_text_process", injected):
                with self.assertRaisesRegex(ValueError, message):
                    self.inspect()
            self.assert_pending_unchanged(before)
        self.assertEqual(self.inspect(), expected)

    def test_legacy_unmarked_source_has_no_invented_event_index_obligation(self):
        source = self.sources[0]
        text, count = re.subn(
            r" <!-- sia-event:[0-9a-f]{64}:[0-9a-f]{64} -->", "",
            source.read_text())
        self.assertEqual(count, 1)
        source.write_text(text)
        self.discovery.fixture._commit()
        before = self.execute()
        result = self.inspect()
        self.assertEqual(result["outcomes"][0]["disposition"], "compacted")
        epoch = self.lib._read_epoch_state("epochs/org/2026-w02")
        self.assertEqual(len(epoch["event_ids"]), 2)
        self.assert_pending_unchanged(before)

    def test_unclaimed_batch_days_remain_explicit(self):
        with mock.patch.object(self.lib, "MAX_CONSOLIDATION_DAYS_PER_RUN", 1):
            before = self.execute()
            result = self.inspect()
        self.assertEqual(len(result["outcomes"]), 1)
        self.assertEqual(result["unclaimed_days"], [
            {"organ": "org", "date": "2026-01-06"},
            {"organ": "org", "date": "2026-01-07"}])
        self.assertTrue(all(path.exists() for path in self.sources[1:]))
        self.assert_pending_unchanged(before)

    def test_forged_phase_observation_does_not_authenticate_execution_history(self):
        self.fixture.stage()
        with self.assertRaisesRegex(ValueError, "effects have not returned"):
            self.inspect()
        unlink = self.lib._unlink_consolidation_source
        def cut(item):
            unlink(item)
            raise RuntimeError("cut after source")
        with mock.patch.object(self.lib, "_unlink_consolidation_source", cut):
            with self.assertRaisesRegex(RuntimeError, "cut after source"):
                self.fixture.execute()
        with self.assertRaisesRegex(ValueError, "effects have not returned"):
            self.inspect()
        # These observations cannot authenticate a phase's execution history.
        state = json.loads(self.journal.read_text())
        state["phase"] = "effects-returned"
        self.lib.atomic_write(str(self.journal), json.dumps(state))
        # Each fixture day has one source: content outcomes can be observed even
        # though this is a forged phase. Protected journal ownership remains open.
        result = self.inspect()
        self.assertEqual([item["disposition"] for item in result["outcomes"]],
                         ["compacted", "retained", "retained"])
        self.assertEqual(result["coverage"], "selected-claims-only")

    def test_partial_same_day_cleanup_cannot_be_qualified_by_a_forged_phase(self):
        stamp = self.lib.datetime.datetime.fromisoformat(
            "2026-01-05T13:00:00+00:00")
        with mock.patch.object(self.lib, "MAX_EVENT_BULLETS", 1):
            self.lib.update_day_page("org", "2026-01-05", [
                self.lib.Event("org", stamp, "obs", "OBS:extra shard " + str(number),
                               occurrence="outcome-shard:" + str(number))
                for number in (1, 2)])
        self.discovery.fixture._commit()
        self.fixture.stage()
        unlink = self.lib._unlink_consolidation_source
        def cut(item):
            unlink(item)
            raise RuntimeError("first shard removed")
        with mock.patch.object(self.lib, "_unlink_consolidation_source", cut):
            with self.assertRaisesRegex(RuntimeError, "first shard removed"):
                self.fixture.execute()
        state = json.loads(self.journal.read_text())
        self.assertGreater(len(state["claims"]["claims"][0]["sources"]), 1)
        state["phase"] = "effects-returned"
        self.lib.atomic_write(str(self.journal), json.dumps(state))
        before = self.journal.read_bytes()
        with self.assertRaisesRegex(ValueError, "partial source cleanup"):
            self.inspect()
        self.assert_pending_unchanged(before)


if __name__ == "__main__":
    unittest.main()
