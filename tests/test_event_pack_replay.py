"""Experimental reader through real leased prepare/publication and before-view.

The candidate is substituted only inside temporary test fixtures. No installed
runtime is changed; page publication is not source acknowledgement or readiness.
"""

import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import test_event_page_plan as plans
from tests import test_event_pack_reader as lookup


class PackedEventReplay(unittest.TestCase):
    def setUp(self):
        self.fixture = plans.EventPageRenderPlan(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        event, _source, _record = self.fixture.fixture._source()
        self.fixture.fixture._commit_corpus()
        self.lib.consolidate_corpus()
        self.event_id = self.lib.event_memory_identity(event)
        self.legacy = Path(self.lib.CORPUS) / self.lib._event_index_relative(
            "org", self.event_id)
        self.raw = self.legacy.read_bytes()
        self.pack = (Path(self.lib.CORPUS) / "event-packs" / "org"
                     / self.event_id[:2] / (self.event_id[:3] + ".siaep"))
        self.pack.parent.mkdir(parents=True)
        self.pack.write_bytes(lookup.siaeventpack.encode("org", self.event_id[:3], (
            (self.event_id.encode(), self.raw),)))
        self.legacy.unlink()
        self.views = set()
        self.complete_calls = 0
        self.fixture.stack.enter_context(mock.patch.object(
            self.lib, "_read_event_index_entry", self._lookup))
        self._watch_complete_capture()

    def _lookup(self, organ, event_id, *, dependency_capture=None):
        self.fixture.assert_owned()
        self.assertIsNotNone(dependency_capture)
        self.views.add(type(dependency_capture).__name__)
        return lookup.reader.read_captured(
            self.lib.__dict__, organ, event_id, dependency_capture)

    def _watch_complete_capture(self):
        import siaeventplan
        original = siaeventplan._Capture.current

        def checked(capture, **kwargs):
            self.fixture.assert_owned()
            result = original(capture, **kwargs)
            self.complete_calls += 1
            return result

        self.fixture.stack.enter_context(mock.patch.object(
            siaeventplan._Capture, "current", checked))

    def _prepare(self, *, include_new=False):
        events = [self.fixture.event("2026-01-07")]
        if include_new:
            events.append(self.fixture.event("2026-01-07", "native:pack:new"))
        return self.fixture.prepare(events, day="2026-01-07")

    def test_actual_leased_prepare_before_view_publish_and_retry(self):
        plan = self._prepare(include_new=True)
        self.fixture.assert_plan(plan)
        self.assertEqual([row["disposition"] for row in plan["admissions"]],
                         ["retained-epoch", "appended"])
        for _ in range(2):
            self.fixture.assert_result(self.fixture.publish(plan), plan)
        self.assertEqual(self.views, {"_Capture", "_BeforeView"})
        self.assertGreater(self.complete_calls, 0)
        self.fixture.assert_owner_released()
        source = Path(self.lib.corpus_path("events/org/2026-01-07"))
        self.assertEqual(len(self.fixture.entries(source.read_bytes())), 1)
        self.assertEqual(self.pack.read_bytes(), lookup.siaeventpack.encode(
            "org", self.event_id[:3], ((self.event_id.encode(), self.raw),)))
        self.assertFalse(self.legacy.exists())

    def test_removed_pack_dependency_cannot_be_reauthorized_by_rehash(self):
        plan = self._prepare()
        relative = str(self.pack.relative_to(self.lib.CORPUS))
        plan["read_dependencies"]["files"] = [
            row for row in plan["read_dependencies"]["files"]
            if row["relative"] != relative]
        plan["plan_sha256"] = plans.own(plan)
        self.fixture.assert_refused_without_writes(plan)

    def test_pack_replacement_after_prepare_refuses_without_writes(self):
        plan = self._prepare(include_new=True)
        self.fixture.replace_same_bytes(self.pack, "held-pack")
        self.fixture.assert_refused_without_writes(plan)

    def test_legacy_appearance_after_prepare_refuses_without_writes(self):
        plan = self._prepare(include_new=True)
        self.legacy.write_bytes(self.raw)
        self.fixture.assert_refused_without_writes(plan)

    def test_pack_appearance_after_legacy_prepare_refuses_without_writes(self):
        raw = self.pack.read_bytes()
        self.pack.unlink()
        self.legacy.write_bytes(self.raw)
        plan = self._prepare(include_new=True)
        self.pack.write_bytes(raw)
        self.fixture.assert_refused_without_writes(plan)

    def test_current_epoch_refusal_during_before_view_precedes_writes(self):
        plan = self._prepare(include_new=True)
        with mock.patch.object(self.lib, "_read_epoch_state",
                               side_effect=ValueError("current epoch policy")):
            self.fixture.assert_refused_without_writes(plan)

    def test_aggregate_plan_cap_includes_pack_dependencies(self):
        plan = self._prepare(include_new=True)
        original = copy.deepcopy(plan)
        with mock.patch.object(self.lib, "MAX_STATE_JSON_BYTES",
                               len(plans.canonical(plan)) - 1):
            self.fixture.assert_refused_without_writes(plan)
        self.assertEqual(plan, original)

    def test_exhausted_capture_budget_refuses_before_reread_or_decode(self):
        import siaeventplan
        with self.lib.corpus_owner():
            capture = siaeventplan._Capture(
                self.lib.__dict__, siaeventplan._Budget(self.lib.__dict__, 4096))
            try:
                with self.assertRaises(FileNotFoundError):
                    capture.read_file(str(self.legacy), self.lib.MAX_EVENT_INDEX_BYTES)
                capture.read_file(str(self.pack), lookup.siaeventpack.MAX_BYTES)
                capture.release_bytes(str(self.pack))
                capture.budget.limit = capture.budget.total
                shim = SimpleNamespace(**vars(siaeventplan.os))
                shim.pread = mock.Mock(side_effect=AssertionError("unreserved read"))
                with mock.patch.object(siaeventplan, "os", shim), \
                        mock.patch.object(lookup.siaeventpack, "decode",
                                          side_effect=AssertionError("unreserved decode")):
                    with self.assertRaisesRegex(ValueError, "complete-byte-capacity"):
                        self._lookup("org", self.event_id, dependency_capture=capture)
            finally:
                capture.close()


if __name__ == "__main__":
    unittest.main()
