"""Whole-request coverage with one capture; no installed format activation."""

import json
from pathlib import Path
import unittest
from unittest import mock

from tests import test_event_pack_reader as lookup
from tests import test_event_page_plan as plans


def wanted_trap(raising):
    hooks = []

    class DeceptiveMeta(type):
        def __hash__(cls):
            hooks.append("hash")
            raise AssertionError("untrusted metaclass hash executed")

        def __eq__(cls, other):
            hooks.append("equality")
            if raising:
                raise AssertionError("untrusted metaclass equality executed")
            return True

    class DeceptiveWanted(metaclass=DeceptiveMeta):
        def __len__(self):
            hooks.append("length")
            raise AssertionError("untrusted container length executed")

        def __iter__(self):
            hooks.append("iteration")
            raise AssertionError("untrusted container iteration executed")

    return DeceptiveWanted(), hooks


class PackedRosterBoundary(unittest.TestCase):
    def setUp(self):
        self.fixture = lookup.CapturedEventPackTests(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.fixture._alternate_roster(64)
        self.records = lookup.siaeventpack.decode(
            self.fixture.pack.read_bytes(), "org", self.fixture.event_id[:3])
        self.identifiers = tuple(sorted(
            [key.decode() for key, _raw in self.records] + [self.fixture.event_id]))

    def _join(self, wanted=None, found=None, capture=None):
        return lookup.reader.join_occurrences_captured(
            self.lib.__dict__, "org",
            set(self.identifiers) if wanted is None else wanted,
            {} if found is None else found,
            self.fixture._capture() if capture is None else capture)

    def test_saturated_prefix_keeps_every_packed_and_legacy_record(self):
        capture = self.fixture._capture()
        groups = []
        original = lookup.reader.read_group_captured

        def read(owner, organ, identifiers, current):
            self.assertIs(current, capture)
            groups.append(identifiers)
            return original(owner, organ, identifiers, current)

        found = {}
        with mock.patch.object(lookup.reader, "read_group_captured", read):
            self.assertEqual(self._join(found=found, capture=capture), set())
        capture.current()
        self.assertEqual([len(group) for group in groups], [64, 1])
        self.assertEqual(tuple(key for group in groups for key in group), self.identifiers)
        entries = {key.decode(): json.loads(raw) for key, raw in self.records}
        entries[self.fixture.event_id] = self.fixture.original
        self.assertEqual(found, {key: (value["epoch_slug"], value["payload_sha256"],
                                     value["semantic_id"]) for key, value in entries.items()})

    def test_empty_roster_needs_no_io(self):
        capture = mock.Mock()
        self.assertEqual(self._join(set(), capture=capture), set())
        capture.read_file.assert_not_called()

    def test_invalid_roster_refuses_before_io(self):
        first, second = self.identifiers[:2]
        capture = mock.Mock()
        invalid = ([first], (first, first), (second, first), (None,), ("../bad",))
        for identifiers in invalid:
            with self.subTest(identifiers=identifiers), self.assertRaises(ValueError):
                list(lookup.reader.iter_roster_captured(
                    self.lib.__dict__, "org", identifiers, capture))
        with mock.patch.object(self.lib, "MAX_EVENT_INDEX_RECORDS", 1):
            with self.assertRaisesRegex(ValueError, "identity bound"):
                self._join(capture=capture)
        capture.read_file.assert_not_called()

    def test_native_inputs_and_result_scope_are_checked_before_io(self):
        class Text(str):
            pass

        capture = mock.Mock()
        invalid = ((list(self.identifiers), {}), ({Text(self.identifiers[0])}, {}),
                   (set(self.identifiers), {"outside": ("x", None, None)}),
                   (set(self.identifiers), {self.identifiers[0]: ["x", None, None]}))
        for wanted, found in invalid:
            with self.subTest(wanted=wanted), self.assertRaises(ValueError):
                self._join(wanted, found, capture)
        capture.read_file.assert_not_called()

    def test_deceptive_and_raising_container_metaclasses_refuse_without_hooks(self):
        capture = mock.Mock()
        for raising in (False, True):
            wanted, hooks = wanted_trap(raising)
            with self.subTest(raising=raising):
                with self.assertRaisesRegex(ValueError, "roster shape"):
                    self._join(wanted=wanted, capture=capture)
                self.assertEqual(hooks, [])
        capture.read_file.assert_not_called()

    def test_later_group_failure_cannot_publish_partial_found(self):
        original = lookup.reader.read_group_captured
        calls = []

        def read(*args):
            calls.append(args[2])
            if len(calls) == 2:
                raise ValueError("later group refused")
            return original(*args)

        found = {}
        with mock.patch.object(lookup.reader, "read_group_captured", read):
            with self.assertRaisesRegex(ValueError, "later group refused"):
                self._join(found=found)
        self.assertEqual(found, {})
        self.assertEqual([len(group) for group in calls], [64, 1])

    def test_identity_policy_change_after_final_yield_refuses(self):
        capture = self.fixture._capture()
        iterator = lookup.reader.iter_roster_captured(
            self.lib.__dict__, "org", (self.fixture.event_id,), capture)
        self.assertEqual(next(iterator)[0], self.fixture.event_id)
        with mock.patch.object(self.lib, "MAX_EVENT_INDEX_RECORDS", 1):
            with self.assertRaisesRegex(ValueError, "policy changed"):
                next(iterator)

    def test_input_mutation_during_validation_refuses(self):
        original = self.lib._validate_event_index_raw
        for mutate_found in (False, True):
            wanted, found = set(self.identifiers), {}

            def validate(*args, change=mutate_found, result=found, request=wanted, **kwargs):
                if change:
                    result[self.fixture.event_id] = ("changed", None, None)
                else:
                    request.discard(self.fixture.event_id)
                return original(*args, **kwargs)

            with self.subTest(mutate_found=mutate_found), \
                    mock.patch.object(self.lib, "_validate_event_index_raw", validate):
                with self.assertRaises(ValueError):
                    self._join(wanted, found)
            self.assertLessEqual(len(found), 1)


class PackedRosterPlanner(unittest.TestCase):
    def setUp(self):
        self.fixture = plans.EventPageRenderPlan(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.events = [self.fixture.event(occurrence="native:roster:" + str(index))
                       for index in range(4)]
        self.lib.update_day_page("org", self.fixture.day, self.events)
        self.fixture.fixture._commit_corpus()
        self.lib.consolidate_corpus()
        self.packs = self._pack_fixture()
        self.views, self.rosters = set(), []
        self.fixture.stack.enter_context(mock.patch.object(
            self.lib, "_join_event_index_occurrences", self._join))

    def _pack_fixture(self):
        groups, paths = {}, []
        for event in self.events:
            identifier = self.lib.event_memory_identity(event)
            path = Path(self.lib.CORPUS) / self.lib._event_index_relative("org", identifier)
            groups.setdefault(identifier[:3], []).append((identifier.encode(), path.read_bytes()))
            paths.append(path)
        self.assertGreater(len(groups), 1)
        packs = []
        for prefix, records in sorted(groups.items()):
            pack = Path(self.lib.CORPUS) / "event-packs" / "org" / prefix[:2] / (prefix + ".siaep")
            pack.parent.mkdir(parents=True, exist_ok=True)
            pack.write_bytes(lookup.siaeventpack.encode("org", prefix, tuple(sorted(records))))
            packs.append(pack)
        for path in paths:
            path.unlink()
        return packs

    def _join(self, organ, wanted, found, *, dependency_capture=None):
        self.fixture.assert_owned()
        self.assertIsNotNone(dependency_capture)
        self.views.add(type(dependency_capture).__name__)
        self.rosters.append(frozenset(wanted))
        return lookup.reader.join_occurrences_captured(
            self.lib.__dict__, organ, wanted, found, dependency_capture)

    def _prepare(self):
        events = [self.fixture.event("2026-01-07", event.occurrence) for event in self.events]
        events.append(self.fixture.event("2026-01-07", "native:roster:new"))
        return self.fixture.prepare(events, day="2026-01-07")

    def test_mixed_prefix_complete_plan_publish_and_retry(self):
        plan = self._prepare()
        self.fixture.assert_plan(plan)
        self.assertEqual([row["disposition"] for row in plan["admissions"]],
                         ["retained-epoch"] * len(self.events) + ["appended"])
        expected = {self.lib.event_memory_identity(event) for event in self.events}
        expected.add(self.lib.event_memory_identity(
            self.fixture.event("2026-01-07", "native:roster:new")))
        for _ in range(2):
            self.fixture.assert_result(self.fixture.publish(plan), plan)
        self.assertTrue(self.rosters)
        self.assertTrue(all(roster == expected for roster in self.rosters))
        self.assertEqual(self.views, {"_Capture", "_BeforeView"})
        self.fixture.assert_owner_released()
        page = Path(self.lib.corpus_path("events/org/2026-01-07"))
        self.assertEqual(len(self.fixture.entries(page.read_bytes())), 1)
        observed = {row["relative"] for row in plan["read_dependencies"]["files"]}
        self.assertTrue({str(path.relative_to(self.lib.CORPUS)) for path in self.packs} <= observed)

    def test_missing_lineage_gate_is_not_bypassed(self):
        self.packs[-1].unlink()
        with self.assertRaisesRegex(ValueError, "consolidated event index leaf is missing"):
            self._prepare()

    def test_later_pack_replacement_refuses_publication_without_writes(self):
        plan = self._prepare()
        self.fixture.replace_same_bytes(self.packs[-1], "held-roster-pack")
        self.fixture.assert_refused_without_writes(plan)


class LegacyOccurrenceJoin(unittest.TestCase):
    def setUp(self):
        self.fixture = lookup.CapturedEventPackTests(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib

    def test_legacy_conflict_precedes_later_lookup(self):
        first, second = "0" * 64, "f" * 64
        found = {first: ("live", "digest", None)}
        with mock.patch.object(self.lib, "_read_event_index_entry",
                               return_value=self.fixture.original) as read:
            with self.assertRaisesRegex(ValueError, "live and consolidated"):
                self.lib._join_event_index_occurrences("org", {second, first}, found)
        read.assert_called_once_with("org", first)
        self.assertEqual(found, {first: ("live", "digest", None)})

    def test_legacy_owner_and_parent_rebinding_remain_local(self):
        from tests import test_epoch_module_ownership as ownership
        other = ownership._load_core("sialib_roster_other")
        helper = self.lib._join_event_index_occurrences.__wrapped__
        self.assertIs(other._join_event_index_occurrences.__wrapped__, helper)
        identifier = self.fixture.event_id
        with mock.patch.object(other, "_read_event_index_entry", return_value=None), \
                mock.patch.object(self.lib, "_read_event_index_entry",
                                  side_effect=ValueError("parent policy")):
            for owner in (other, self.lib, other):
                if owner is self.lib:
                    with self.assertRaisesRegex(ValueError, "parent policy"):
                        owner._join_event_index_occurrences("org", {identifier}, {})
                else:
                    self.assertEqual(owner._join_event_index_occurrences(
                        "org", {identifier}, {}), {identifier})


if __name__ == "__main__":
    unittest.main()
