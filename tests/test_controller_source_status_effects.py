"""Frozen phase-one status effects for a retained controller-source pulse.

The real source capture, fixed-slot publication and live-binding fixtures build
the authority supplied here.  The operation under test is pure: it validates
the complete source/live binding, projects only ``effects``, ``history`` and
the shallow compatibility workspace, and returns detached JSON values.  A
separate memo-only seam may then make the effects/history handoff durable
before event closure publication.  Neither seam publishes pages, graph,
status or live state, acknowledges sources, or enters the legacy mind path.

There are three different clocks.  ``batch.observed_at`` remains the integer
source/live-state observation clock.  ``started_at`` is one caller-observed
canonical UTC second used for the effects day and one history row.  A later
status publication observes ``status.ts`` only after graph synchronization;
this phase neither accepts nor invents that third clock.
"""

import collections
import contextlib
import copy
import datetime
import inspect
import json
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_source_capture as capture_tests
from tests import test_controller_source_live_binding as binding_tests
from tests import test_live_loop as live_tests


PREPARER = "_prepare_controller_source_status_effects"
STAGER = "_stage_controller_source_status_effects"
PREPARE_PARAMETERS = (
    "admitted_status", "batch", "expected_batch_sha256",
    "source_live_pending", "candidate", "transition",
    "expected_transition_sha256", "started_at",
)
RESULT_KEYS = {"effects", "history", "workspace"}
STARTED_AT = "2026-09-06T12:00:00Z"
PRIOR_STATUS_TS = "2026-09-06T11:59:58Z"
CURRENT_EVENT = datetime.datetime(
    2026, 9, 6, 11, 30, tzinfo=datetime.timezone.utc)
OLD_EVENT = datetime.datetime(
    2026, 9, 5, 23, 30, tzinfo=datetime.timezone.utc)


class ControllerSourceStatusEffects(unittest.TestCase):
    def setUp(self):
        self.binding = binding_tests.ControllerSourceLiveBinding(
            methodName="runTest")
        self.binding.setUp()
        self.addCleanup(self.binding.doCleanups)
        self.producer = self.binding.fixture
        self.source = self.producer.source
        self.live = self.binding.live
        self.lib = self.binding.lib
        self.loop = self.binding.loop

    def _preparer(self):
        value = getattr(self.lib, PREPARER, None)
        self.assertTrue(callable(value), "missing pure status-effects API: " + PREPARER)
        return value

    def _stager(self):
        value = getattr(self.lib, STAGER, None)
        self.assertTrue(callable(value), "missing durable status-effects API: " + STAGER)
        return value

    def _install_status(self, *, day="2026-09-06", organs=None,
                        history=None, ts=PRIOR_STATUS_TS):
        status = copy.deepcopy(self.live.status)
        status.update({
            "ts": ts,
            "day": day,
            "events_pulse": 0,
            "organs": copy.deepcopy({} if organs is None else organs),
            "history": copy.deepcopy([] if history is None else history),
        })
        status["events_today"] = sum(
            row["today"] for row in status["organs"].values())
        self.assertIsNotNone(self.lib._recoverable_status_integrity(status))
        self.live.status.clear()
        self.live.status.update(copy.deepcopy(status))
        self.live.memo["pulse_history"] = copy.deepcopy(status["history"])
        self.live._write(self.live.paths["STATUS_PATH"], self.live.status)
        self.live._write(self.live.paths["MEMO_PATH"], self.live.memo)
        return self.live.status

    @staticmethod
    def _restamp(lib, event, stamp):
        return lib.Event(
            event.organ, stamp, event.kind, event.summary,
            set(event.links), set(event.tags), occurrence=event.occurrence)

    def _mixed_batch(self):
        """Use real plans: retained rows plus new current/old rows and duplicates."""
        seed = self.producer._capture()
        closure = seed["event_closure"]
        self.assertIsNotNone(closure)
        self.source.lib._publish_event_page_batch_closure(
            closure=closure,
            expected_closure_sha256=closure["closure_sha256"])

        alpha = Path(self.source.custom_entries[0]["path"])
        alpha.write_text(
            alpha.read_text(encoding="utf-8")
            + "third observed line\nfourth observed line\n",
            encoding="utf-8")
        self.source.calls.clear()
        shared = {}

        def mixed(source_id, events):
            if source_id == "sense_custom:alpha":
                self.assertGreaterEqual(len(events), 4)
                projected = [
                    self._restamp(
                        self.source.lib, event,
                        OLD_EVENT if index == len(events) - 1 else CURRENT_EVENT)
                    for index, event in enumerate(events)
                ]
                shared["event"] = projected[0]
                return projected + [projected[0]]
            if source_id == "sense_custom:empty":
                self.assertIn("event", shared)
                return [shared["event"]]
            return events

        with self.source.observe_returns(mixed):
            batch = self.source.capture()
            self.source.assert_batch(batch)
        return batch

    def _old_appended_batch(self):
        def old_only(_source_id, events):
            return [self._restamp(self.source.lib, event, OLD_EVENT)
                    for event in events]

        self.source.calls.clear()
        with self.source.observe_returns(old_only):
            batch = self.source.capture()
            self.source.assert_batch(batch)
        return batch

    def _bind(self, batch, *, status=None, parent=False):
        status = self.live.status if status is None else status
        retained = self.producer._stage(batch)
        candidate = self.producer._prepare_candidate(
            parent=parent, admitted_status=status)
        transition = self.loop.prepare_pulse(**candidate["prepare_inputs"])
        result, writes = self.binding._stage(status=status)
        self.assertIsNone(result)
        self.assertEqual(len(writes), 1)
        marker = copy.deepcopy(
            self.live.memo["controller_source_live_pending"])
        return retained, candidate, transition, marker

    @contextlib.contextmanager
    def _pure_boundary(self):
        def forbidden(name):
            return mock.Mock(side_effect=AssertionError(
                "pure status effects reached an effect: " + name))

        names = (
            "atomic_write", "_write_memo", "read_state_json", "load_memo",
            "_read_pending_controller_source_batch", "_capture_controller_source_batch",
            "_publish_event_page_plan", "_publish_event_page_plan_batch",
            "_publish_event_page_batch_closure", "update_day_page",
            "_stage_live_generation", "_publish_staged_live_generation",
            "_commit_sense_cursors", "save_cursors", "export_status",
            "export_graph", "brain_sync", "gbrain", "gbrain_call",
            "save_mind", "_pulse_transaction_guarded",
        )
        with contextlib.ExitStack() as stack:
            for name in names:
                if hasattr(self.lib, name):
                    stack.enter_context(mock.patch.object(
                        self.lib, name, new=forbidden(name)))
            stack.enter_context(mock.patch(
                "builtins.open", side_effect=AssertionError(
                    "pure status effects opened a path")))
            yield

    def _arguments(self, bound, *, started_at=STARTED_AT):
        batch, candidate, transition, marker = bound
        return {
            "admitted_status": self.live.status,
            "batch": batch,
            "expected_batch_sha256": batch["batch_sha256"],
            "source_live_pending": marker,
            "candidate": candidate,
            "transition": transition,
            "expected_transition_sha256": transition["transition_sha256"],
            "started_at": started_at,
        }

    def _call(self, arguments):
        before = copy.deepcopy(arguments)
        with self._pure_boundary():
            result = self._preparer()(**arguments)
        self.assertEqual(arguments, before)
        self.assertEqual(set(result), RESULT_KEYS)
        return result

    def _assert_refuses(self, arguments):
        before = copy.deepcopy(arguments)
        with self._pure_boundary(), self.assertRaises((RuntimeError, ValueError)):
            self._preparer()(**arguments)
        self.assertEqual(arguments, before)

    @staticmethod
    def _records(batch):
        records = collections.OrderedDict()
        for run in batch["source_returns"]["runs"]:
            for record in run["events"]:
                old = records.setdefault(record["event_id"], record)
                if old["semantic_id"] != record["semantic_id"]:
                    raise AssertionError("fixture repeats an occurrence with changed meaning")
        return records

    @staticmethod
    def _admissions(batch):
        closure = batch["event_closure"]
        if closure is None:
            return collections.OrderedDict()
        rows = collections.OrderedDict()
        for grouped in closure["batches"]:
            for member in grouped["members"]:
                for row in member["admissions"]:
                    old = rows.setdefault(row["event_id"], row)
                    if old != row:
                        raise AssertionError("fixture closure reassigns one occurrence")
        return rows

    def _expected(self, status, batch, transition, started_at):
        records = self._records(batch)
        admissions = self._admissions(batch)
        self.assertEqual(set(records), set(admissions))
        day = started_at[:10]
        organs = copy.deepcopy(status["organs"])
        if status["day"] != day:
            for row in organs.values():
                row["today"] = 0
        for event_id, admission in admissions.items():
            if admission["disposition"] != "appended":
                continue
            record = records[event_id]
            organ = organs.setdefault(
                record["organ"], {"today": 0, "last_ts": ""})
            if record["ts"][:10] == day:
                organ["today"] += 1
            organ["last_ts"] = max(organ["last_ts"], record["ts"])
        history = copy.deepcopy(status["history"])
        history.append([started_at, len(records)])
        history = history[-self.lib.MAX_PULSE_HISTORY_ROWS:]
        return {
            "effects": {"day": day, "events_pulse": len(records),
                        "organs": organs},
            "history": history,
            "workspace": copy.deepcopy(
                transition["state"]["workspace"]["slots"]),
        }

    @staticmethod
    def _reidentify(marker):
        marker = copy.deepcopy(marker)
        fields = {key: copy.deepcopy(marker[key])
                  for key in sorted(binding_tests.IDENTITY_KEYS)}
        publication_sha256 = live_tests.digest({
            "schema": "sia-controller-source-live-publication-identity-v1",
            "binding": fields,
        })
        marker["publication_id"] = publication_sha256[:32]
        marker["publication_sha256"] = publication_sha256
        marker["marker_sha256"] = live_tests.digest({
            key: value for key, value in marker.items()
            if key != "marker_sha256"})
        return marker

    @staticmethod
    def _reseal_marker_only(marker):
        marker = copy.deepcopy(marker)
        marker["marker_sha256"] = live_tests.digest({
            key: value for key, value in marker.items()
            if key != "marker_sha256"})
        return marker

    def test_exact_keyword_only_pure_and_memo_stage_apis(self):
        for function, expected in (
                (self._preparer(), PREPARE_PARAMETERS),
                (self._stager(), ("memo", *PREPARE_PARAMETERS))):
            signature = inspect.signature(function)
            self.assertEqual(tuple(signature.parameters), expected)
            for parameter in signature.parameters.values():
                self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(parameter.default, inspect.Parameter.empty)

    def test_mixed_real_closure_projects_unique_pulse_append_only_counters_and_rollover(self):
        status = self._install_status(
            day="2026-09-05",
            organs={
                "org": {"today": 9, "last_ts": "2026-09-05T10:00:00Z"},
                "quiet": {"today": 4, "last_ts": "2026-09-05T09:00:00Z"},
            },
            history=[["2026-09-05T10:00:01Z", 3]])
        batch = self._mixed_batch()
        bound = self._bind(batch, status=status)
        arguments = self._arguments(bound)
        records = self._records(batch)
        admissions = self._admissions(batch)
        raw_ids = [record["event_id"]
                   for run in batch["source_returns"]["runs"]
                   for record in run["events"]]
        dispositions = {row["disposition"] for row in admissions.values()}
        self.assertGreater(len(raw_ids), len(records))
        self.assertEqual(set(records), set(admissions))
        self.assertIn("appended", dispositions)
        self.assertTrue(dispositions & {"retained-day", "retained-epoch"})
        self.assertTrue(any(
            row["disposition"] == "appended"
            and records[event_id]["ts"][:10] != STARTED_AT[:10]
            for event_id, row in admissions.items()))

        result = self._call(arguments)
        self.assertEqual(result, self._expected(
            status, batch, bound[2], STARTED_AT))
        self.assertEqual(result["effects"]["organs"]["quiet"], {
            "today": 0, "last_ts": "2026-09-05T09:00:00Z"})
        self.assertEqual(result["history"][:-1], status["history"])
        self.assertEqual(result["history"][-1], [
            STARTED_AT, result["effects"]["events_pulse"]])

    def test_old_dated_append_updates_last_timestamp_but_not_today(self):
        status = self._install_status(
            day="2026-09-04",
            organs={"org": {"today": 7, "last_ts": ""}})
        batch = self._old_appended_batch()
        bound = self._bind(batch, status=status)
        result = self._call(self._arguments(bound))
        self.assertTrue(self._admissions(batch))
        self.assertEqual(
            {row["disposition"] for row in self._admissions(batch).values()},
            {"appended"})
        self.assertEqual(result, self._expected(
            status, batch, bound[2], STARTED_AT))
        self.assertEqual(result["effects"]["organs"]["org"], {
            "today": 0, "last_ts": "2026-09-05T23:30:00Z"})

    def test_empty_initial_is_zero_and_exact_cumulative_parent_can_sustain(self):
        status = self._install_status(organs={
            "quiet": {"today": 2, "last_ts": "2026-09-06T10:00:00Z"}})
        initial = self.producer._capture(empty=True)
        initial_bound = self._bind(initial, status=status)
        projected = self._call(self._arguments(initial_bound))
        self.assertIsNone(initial["event_closure"])
        self.assertEqual(projected, self._expected(
            status, initial, initial_bound[2], STARTED_AT))
        self.assertEqual(projected["effects"], {
            "day": "2026-09-06", "events_pulse": 0,
            "organs": status["organs"]})
        self.assertEqual(projected["workspace"], [])
        self.assertEqual(projected["history"][-1], [STARTED_AT, 0])

        # A separate fixture is required because the fixed source slot is
        # immutable.  The exact cumulative/equal intake is the only admitted
        # continuation until source acknowledgment binds predecessor history.
        other = type(self)(methodName="runTest")
        other.setUp()
        self.addCleanup(other.doCleanups)
        other_status = other._install_status()
        parent_batch = other.producer._capture()
        other.producer._commit_matching_parent(parent_batch)
        sustained_bound = other._bind(
            parent_batch, status=other_status, parent=True)
        sustained = other._call(other._arguments(sustained_bound))
        slots = sustained_bound[2]["state"]["workspace"]["slots"]
        self.assertTrue(slots, "nonempty parent did not supply held workspace slots")
        self.assertEqual(sustained, other._expected(
            other_status, parent_batch, sustained_bound[2], STARTED_AT))
        self.assertEqual(sustained["workspace"], slots)

    def test_every_binding_identity_pin_and_full_hash_not_just_prefix_is_validated(self):
        status = self._install_status()
        batch = self.producer._capture()
        bound = self._bind(batch, status=status)
        arguments = self._arguments(bound)
        marker = arguments["source_live_pending"]

        for field in sorted(binding_tests.IDENTITY_KEYS):
            changed = copy.deepcopy(marker)
            value = changed[field]
            if field == "source_pending_receipt":
                value["batch_wire_sha256"] = "0" * 64
            elif field == "non_claims":
                value.append("caller changed the binding")
            elif value is None:
                changed[field] = "0" * 64
            elif type(value) is int:
                changed[field] = value + 1
            elif isinstance(value, str) and len(value) == 64:
                changed[field] = ("0" if value[0] != "0" else "1") + value[1:]
            else:
                changed[field] = str(value) + "-changed"
            changed = self._reseal_marker_only(changed)
            with self.subTest(identity_pin=field):
                self._assert_refuses({
                    **arguments, "source_live_pending": changed})

        changed = copy.deepcopy(marker)
        suffix = "0" * 32
        if marker["publication_sha256"] == marker["publication_id"] + suffix:
            suffix = "f" * 32
        changed["publication_sha256"] = marker["publication_id"] + suffix
        changed = self._reseal_marker_only(changed)
        self.assertEqual(changed["publication_id"], marker["publication_id"])
        self.assertNotEqual(changed["publication_sha256"],
                            marker["publication_sha256"])
        self._assert_refuses({**arguments, "source_live_pending": changed})

        for label, changed in (
                ("missing-key", {key: value for key, value in marker.items()
                                 if key != "state_sha256"}),
                ("extra-key", {**marker, "unbound": True}),
                ("marker-hash", {**marker, "marker_sha256": "0" * 64}),
                ("compact-id", {**marker, "publication_id": "0" * 32}),
                ("schema", {**marker, "schema": "changed"})):
            with self.subTest(marker_shape=label):
                self._assert_refuses({
                    **arguments, "source_live_pending": changed})

        changed_candidate = copy.deepcopy(arguments["candidate"])
        changed_candidate["prepare_inputs"]["observed_at"] += 1
        changed_candidate["expected_prepare_inputs_sha256"] = live_tests.digest(
            changed_candidate["prepare_inputs"])
        changed_transition = copy.deepcopy(arguments["transition"])
        changed_transition["state"]["observed_at"] += 1
        changed_transition["state_sha256"] = live_tests.digest(
            changed_transition["state"])
        changed_transition["transition_sha256"] = live_tests.digest({
            key: value for key, value in changed_transition.items()
            if key != "transition_sha256"})
        changed_status = copy.deepcopy(status)
        changed_status["sync_note"] = "different admitted status"
        for label, changes in (
                ("batch-pin", {"expected_batch_sha256": "0" * 64}),
                ("prepare-pin", {"candidate": changed_candidate}),
                ("transition-pin", {"expected_transition_sha256": "0" * 64}),
                ("transition-state", {
                    "transition": changed_transition,
                    "expected_transition_sha256":
                        changed_transition["transition_sha256"]}),
                ("status-pin", {"admitted_status": changed_status})):
            with self.subTest(external_pin=label):
                self._assert_refuses({**arguments, **changes})

    def test_closure_event_set_equality_and_null_symmetry_fail_closed(self):
        status = self._install_status()
        batch = self.producer._capture()
        bound = self._bind(batch, status=status)
        arguments = self._arguments(bound)
        self.assertEqual(set(self._records(batch)), set(self._admissions(batch)))

        missing = copy.deepcopy(arguments["source_live_pending"])
        missing["event_closure_sha256"] = None
        missing = self._reidentify(missing)
        self._assert_refuses({**arguments, "source_live_pending": missing})

        changed_batch = copy.deepcopy(batch)
        counts = collections.Counter(
            record["event_id"]
            for run in changed_batch["source_returns"]["runs"]
            for record in run["events"])
        target = next(event_id for event_id, count in counts.items()
                      if count == 1)
        for run in changed_batch["source_returns"]["runs"]:
            run["events"] = [record for record in run["events"]
                             if record["event_id"] != target]
        returns = changed_batch["source_returns"]
        returns["returns_sha256"] = capture_tests.digest({
            key: value for key, value in returns.items()
            if key != "returns_sha256"})
        changed_batch["batch_sha256"] = capture_tests.digest({
            key: value for key, value in changed_batch.items()
            if key != "batch_sha256"})
        changed_marker = copy.deepcopy(arguments["source_live_pending"])
        receipt = changed_marker["source_pending_receipt"]
        receipt["batch_sha256"] = changed_batch["batch_sha256"]
        receipt["batch_wire_sha256"] = capture_tests.digest(changed_batch)
        receipt["batch_bytes"] = len(capture_tests.canonical(changed_batch))
        changed_marker["source_batch_sha256"] = receipt["batch_sha256"]
        changed_marker["source_batch_wire_sha256"] = receipt["batch_wire_sha256"]
        changed_marker = self._reidentify(changed_marker)
        self.assertNotEqual(set(self._records(changed_batch)),
                            set(self._admissions(changed_batch)))
        self._assert_refuses({
            **arguments,
            "batch": changed_batch,
            "expected_batch_sha256": changed_batch["batch_sha256"],
            "source_live_pending": changed_marker,
        })

        other = type(self)(methodName="runTest")
        other.setUp()
        self.addCleanup(other.doCleanups)
        other_status = other._install_status()
        empty = other.producer._capture(empty=True)
        empty_bound = other._bind(empty, status=other_status)
        empty_arguments = other._arguments(empty_bound)
        self.assertIsNone(empty["event_closure"])
        spurious = copy.deepcopy(empty_arguments["source_live_pending"])
        spurious["event_closure_sha256"] = "f" * 64
        spurious = other._reidentify(spurious)
        other._assert_refuses({
            **empty_arguments, "source_live_pending": spurious})

    def test_history_is_one_exact_retry_row_workspace_is_detached_and_capped(self):
        status = self._install_status(history=[
            ["2026-09-06T11:59:50Z", 1]])
        batch = self.producer._capture()
        bound = self._bind(batch, status=status)
        arguments = self._arguments(bound)
        first = self._call(arguments)
        second = self._call(arguments)
        self.assertEqual(second, first)
        self.assertEqual(first["history"][:-1], status["history"])
        self.assertEqual(first["history"][-1], [
            STARTED_AT, first["effects"]["events_pulse"]])
        self.assertEqual(status["history"], [["2026-09-06T11:59:50Z", 1]])

        transition_slots = bound[2]["state"]["workspace"]["slots"]
        self.assertEqual(first["workspace"], transition_slots)
        first["workspace"].append("notes/caller-mutation")
        self.assertNotEqual(first["workspace"], transition_slots)

        oversized = copy.deepcopy(arguments["transition"])
        oversized["state"]["workspace"]["slots"] = [
            "notes/slot-" + str(index)
            for index in range(self.lib.siamind.WORKSPACE_K + 1)]
        oversized["state_sha256"] = live_tests.digest(oversized["state"])
        oversized["transition_sha256"] = live_tests.digest({
            key: value for key, value in oversized.items()
            if key != "transition_sha256"})
        marker = copy.deepcopy(arguments["source_live_pending"])
        marker["state_sha256"] = oversized["state_sha256"]
        marker["transition_sha256"] = oversized["transition_sha256"]
        marker = self._reidentify(marker)
        self._assert_refuses({
            **arguments,
            "source_live_pending": marker,
            "transition": oversized,
            "expected_transition_sha256": oversized["transition_sha256"],
        })

    def test_three_clocks_remain_distinct_and_started_at_is_not_reobserved(self):
        status = self._install_status(ts=PRIOR_STATUS_TS)
        batch = self.producer._capture()
        bound = self._bind(batch, status=status)
        arguments = self._arguments(bound)
        self.assertIs(type(batch["observed_at"]), int)
        self.assertEqual(bound[1]["prepare_inputs"]["observed_at"],
                         batch["observed_at"])
        self.assertEqual(bound[2]["state"]["observed_at"],
                         batch["observed_at"])
        self.assertEqual(status["ts"], PRIOR_STATUS_TS)
        result = self._call(arguments)
        self.assertEqual(result["history"][-1][0], STARTED_AT)
        self.assertEqual(result["effects"]["day"], STARTED_AT[:10])
        self.assertNotIn("ts", result)
        self.assertNotIn("observed_at", result)

        for bad in (
                "2026-09-06T12:00:00.000000Z",
                "2026-09-06T08:00:00-04:00", batch["observed_at"]):
            with self.subTest(started_at=bad):
                self._assert_refuses({**arguments, "started_at": bad})

    def test_memo_stage_is_write_ahead_exact_and_retry_does_not_duplicate_history(self):
        status = self._install_status(history=[
            ["2026-09-06T11:59:50Z", 1]])
        batch = self.producer._capture()
        bound = self._bind(batch, status=status)
        arguments = self._arguments(bound)
        prepared = self._call(arguments)
        expected_handoff = {
            "v": 1,
            "publication_id": arguments["source_live_pending"]["publication_id"],
            "effects": prepared["effects"],
            "history": prepared["history"][-1],
        }
        before_nonmemo = self.binding._images()
        memo_path = Path(self.live.paths["MEMO_PATH"])
        original_write = self.lib.atomic_write
        writes = []

        def write(path, data, **kwargs):
            self.assertEqual(str(path), str(memo_path))
            value = json.loads(data)
            self.assertEqual(value["pulse_history"], prepared["history"])
            self.assertEqual(value["pulse_status_effects_pending"],
                             expected_handoff)
            self.assertEqual(value["controller_source_live_pending"],
                             arguments["source_live_pending"])
            writes.append(copy.deepcopy(value))
            return original_write(path, data, **kwargs)

        def forbidden(name):
            def reject(*_args, **_kwargs):
                durable = json.loads(memo_path.read_bytes())
                self.assertEqual(
                    durable.get("pulse_status_effects_pending"),
                    expected_handoff,
                    name + " preceded the durable status-effects handoff")
                raise AssertionError("status-effects stage invoked " + name)
            return reject

        effect_names = (
            "_publish_event_page_plan", "_publish_event_page_plan_batch",
            "_publish_event_page_batch_closure", "update_day_page",
            "_stage_live_generation", "_publish_staged_live_generation",
            "_commit_sense_cursors", "save_cursors", "export_status",
            "export_graph", "brain_sync", "gbrain", "gbrain_call",
            "save_mind", "_pulse_transaction_guarded",
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                self.lib, "atomic_write", side_effect=write))
            for name in effect_names:
                if hasattr(self.lib, name):
                    stack.enter_context(mock.patch.object(
                        self.lib, name, side_effect=forbidden(name)))
            result = self._stager()(memo=self.live.memo, **arguments)
        self.assertIsNone(result)
        self.assertEqual(len(writes), 1)
        self.assertEqual(self.binding._images(), before_nonmemo)
        self.assertEqual(self.live.memo["pulse_history"], prepared["history"])
        self.assertEqual(self.live.memo["pulse_status_effects_pending"],
                         expected_handoff)
        self.assertIsNotNone(
            self.lib._pending_pulse_status_effects(self.live.memo))

        durable = memo_path.read_bytes()
        with mock.patch.object(
                self.lib, "atomic_write",
                side_effect=AssertionError("exact retry rewrote the memo")):
            self.assertIsNone(
                self._stager()(memo=self.live.memo, **arguments))
        self.assertEqual(memo_path.read_bytes(), durable)
        self.assertEqual(self.live.memo["pulse_history"], prepared["history"])


if __name__ == "__main__":
    unittest.main()
