"""Temporary-corpus source joins, not installed migration or authorization."""

from pathlib import Path
from types import ModuleType
import json
import unittest
from unittest import mock

from tests import test_event_pack_reader as lookup
from tests import test_event_pack_plan as partition


SOURCE = Path(__file__).resolve().parents[1] / "bin/siaeventpackcapture.py"
joined = ModuleType("siaeventpackcapture")
with mock.patch.dict("sys.modules", {"siaeventpack": lookup.siaeventpack,
        "siaeventpackreader": lookup.reader, "siaeventpackplan": partition.planner}):
    exec(compile(SOURCE.read_bytes(), str(SOURCE), "exec"), joined.__dict__)


class CapturedPackPlan(unittest.TestCase):
    def setUp(self):
        self.fixture = lookup.CapturedEventPackTests(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.key = self.fixture.event_id

    def _capture(self):
        capture = joined.capture_module._Capture(
            self.lib.__dict__, joined.capture_module._Budget(self.lib.__dict__, 4096))
        self.addCleanup(capture.close)
        return capture

    def prepare(self, identifiers=None, capture=None):
        capture = self._capture() if capture is None else capture
        with self.lib.corpus_owner():
            return joined.prepare_captured(self.lib.__dict__, organ="org",
                prefix=self.key[:3], identifiers=(self.key,) if identifiers is None else identifiers,
                capture=capture)

    def test_legacy_plan_matches_independent_wire_without_filesystem_writes(self):
        original = self.fixture.legacy.read_bytes()
        packed, represented, fallback = self.prepare()
        records = ((self.key.encode(), original),)
        expected = partition.wire_fixture.wire(records, prefix=self.key[:3].encode())
        self.assertEqual((packed, represented, fallback), (expected, records, ()))
        self.assertEqual(self.fixture.legacy.read_bytes(), original)
        self.assertFalse(self.fixture.pack.exists())

    def test_pack_only_and_duplicate_sources_have_same_partition(self):
        self.fixture._write_pack()
        duplicated = self.prepare()
        self.fixture.legacy.unlink()
        self.assertEqual(self.prepare(), duplicated)
        self.assertEqual(duplicated[0], self.fixture.pack.read_bytes())

    def test_empty_selection_preserves_prior_but_does_not_invent_input(self):
        self.assertEqual(self.prepare(()), (None, (), ()))
        self.fixture._write_pack()
        self.assertEqual(self.prepare(()), (self.fixture.pack.read_bytes(), (), ()))

    def test_saturated_prior_keeps_exact_selected_legacy_fallback(self):
        self.fixture._alternate_roster(64)
        original = self.fixture.pack.read_bytes()
        self.assertEqual(self.prepare(),
                         (original, (), ((self.key.encode(), self.fixture.raw),)))
        self.assertEqual(self.fixture.legacy.read_bytes(), self.fixture.raw)
        self.assertEqual(self.fixture.pack.read_bytes(), original)

    def test_missing_selected_record_refuses_complete_plan(self):
        missing = self.key[:3] + "f" * 61
        self.assertGreater(missing, self.key)
        with self.assertRaisesRegex(ValueError, "selected record missing"):
            self.prepare((self.key, missing))
        self.assertFalse(self.fixture.pack.exists())

    def test_prior_unselected_legacy_conflict_refuses_even_empty_selection(self):
        self.fixture._write_pack()
        conflict = self.lib._event_index_encoded(
            dict(self.fixture.original, payload_sha256="f" * 64))
        self.fixture.legacy.write_bytes(conflict)
        with self.assertRaisesRegex(ValueError, "representations conflict"):
            self.prepare(())

    def test_unselected_prior_lineage_is_required(self):
        self.fixture._alternate_roster(1)
        records = lookup.siaeventpack.decode(
            self.fixture.pack.read_bytes(), "org", self.key[:3])
        key, raw = records[0]
        wrong = self.lib._event_index_encoded(dict(json.loads(raw), source_sha256="f" * 64))
        self.fixture.pack.write_bytes(lookup.siaeventpack.encode(
            "org", self.key[:3], ((key, wrong),)))
        with self.assertRaisesRegex(ValueError, "exact epoch lineage"):
            self.prepare()

    def test_malformed_pack_never_becomes_legacy_fallback(self):
        self.fixture.pack.write_bytes(b"malformed")
        with self.assertRaises(ValueError):
            self.prepare()

    def test_missing_lease_or_foreign_capture_refuses_before_reads(self):
        capture = self._capture()
        with mock.patch.object(joined.reader, "_optional", side_effect=AssertionError("read")):
            with self.assertRaisesRegex(ValueError, "requires the corpus lease"):
                joined.prepare_captured(self.lib.__dict__, organ="org", prefix=self.key[:3],
                                        identifiers=(self.key,), capture=capture)
            with self.lib.corpus_owner():
                with self.assertRaisesRegex(ValueError, "owner mismatch"):
                    joined.prepare_captured(dict(self.lib.__dict__), organ="org",
                        prefix=self.key[:3], identifiers=(self.key,), capture=capture)

    def test_invalid_selection_refuses_before_io_or_reservation(self):
        class Hostile(str):
            def __len__(self):
                raise AssertionError("subclass invoked")

        cases = ([self.key], (self.key, self.key), ("invalid",), (Hostile(self.key),))
        for identifiers in cases:
            capture = self._capture()
            before = dict(capture.budget.items)
            with mock.patch.object(joined.reader, "_optional", side_effect=AssertionError("read")):
                with self.assertRaises(ValueError):
                    self.prepare(identifiers, capture)
            self.assertEqual(capture.budget.items, before)

    def test_one_attempt_per_prefix_retains_budget_on_success_and_failure(self):
        for missing in (False, True):
            capture = self._capture()
            identifier = self.key[:3] + "f" * 61 if missing else self.key
            if missing:
                with self.assertRaisesRegex(ValueError, "selected record missing"):
                    self.prepare((identifier,), capture)
            else:
                self.prepare((identifier,), capture)
            amount = capture.budget.total
            with self.assertRaisesRegex(ValueError, "already attempted"):
                self.prepare((identifier,), capture)
            self.assertEqual(capture.budget.total, amount)

    def test_shared_budget_exhaustion_precedes_source_reads(self):
        capture = self._capture()
        capture.budget.reserve("other-work", capture.budget.limit - capture.budget.total)
        with mock.patch.object(joined.reader, "_optional", side_effect=AssertionError("read")):
            with self.assertRaisesRegex(ValueError, "complete-byte-capacity"):
                self.prepare(capture=capture)

    def test_epoch_replacement_after_planning_refuses_result(self):
        original = joined.planner.plan

        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            epoch = Path(self.lib.corpus_path(self.fixture.original["epoch_slug"]))
            replacement = epoch.with_suffix(".new")
            replacement.write_bytes(epoch.read_bytes())
            replacement.replace(epoch)
            return result

        with mock.patch.object(joined.planner, "plan", changed):
            with self.assertRaisesRegex(ValueError, "source-generation-changed"):
                self.prepare()

    def test_absent_pack_appearing_after_planning_refuses_result(self):
        original = joined.planner.plan

        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            self.fixture._write_pack()
            return result

        with mock.patch.object(joined.planner, "plan", changed):
            with self.assertRaisesRegex(ValueError, "source-absence-changed"):
                self.prepare()

    def test_final_current_policy_change_refuses_result(self):
        original = joined.capture_module._Capture.current

        def changed(capture, **kwargs):
            original(capture, **kwargs)
            self.lib.MAX_EPOCH_EVENT_IDS = True

        with mock.patch.object(self.lib, "MAX_EPOCH_EVENT_IDS", self.lib.MAX_EPOCH_EVENT_IDS), \
                mock.patch.object(joined.capture_module._Capture, "current", changed):
            with self.assertRaisesRegex(ValueError, "policy is invalid"):
                self.prepare()

    def test_actual_epoch_read_limit_change_after_final_check_refuses(self):
        original = joined.capture_module._Capture.current

        def changed(capture, **kwargs):
            original(capture, **kwargs)
            self.lib.MAX_EVENT_PAGE_BYTES = 1

        with mock.patch.object(self.lib, "MAX_EVENT_PAGE_BYTES", self.lib.MAX_EVENT_PAGE_BYTES), \
                mock.patch.object(joined.capture_module._Capture, "current", changed):
            with self.assertRaisesRegex(ValueError, "policy changed"):
                self.prepare()

    def test_caller_capture_remains_open_and_can_detect_later_source_changes(self):
        capture = self._capture()
        self.prepare(capture=capture)
        self.assertIsNotNone(capture.root_fd)
        self.fixture.legacy.write_bytes(self.fixture.raw + b" ")
        with self.assertRaises(ValueError):
            capture.current()


if __name__ == "__main__":
    unittest.main()
