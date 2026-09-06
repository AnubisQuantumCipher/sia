"""Publication-only RED contract for a committed live-loop generation.

Root alone executes this file. The real pulse transaction and real pure live
pipeline are exercised with existing synthetic fixtures. The producer seam's
complete inputs are a CALLER PREMISE here: these tests do not establish source
capture, durable delivery claims, journal ACK, live CLI use or a held-out win.

Status v1/v2 stay closed and unchanged. A fixed candidate retains the complete
prepare inputs, transition, staged status and prior compact committed receipt.
The generation exposes the complete transition with exact status/parent/pulse
bindings. Pending/committed memo receipts are compact identities, not copies
of the histories. All hashes use canonical complete JSON; candidate and
generation hashes omit only their own self-hash field.

Stage publishes candidate then pending memo only. Publish writes generation,
the exact staged status, and the final committed memo in that order. Recovery
replays the original pure inputs and publishes the same candidate, even when
the allocator has subsequently reserved a later sequence. Orphans, changed
authority and unadmitted policies are refusals, not absence or availability.
The fixed files need not be deleted. Every selected input/output and complete
memo must fit its existing byte ceiling before a first publication write.
"""

import contextlib
import copy
import importlib
import inspect
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from tests import test_live_loop as live_tests
from tests import test_pulse_sync as pulse_tests


CANDIDATE_KEYS = {
    "schema", "prepare_inputs", "prepare_inputs_sha256", "transition", "status",
    "status_sha256", "parent_committed", "non_claims", "candidate_sha256",
}
GENERATION_KEYS = {
    "schema", "publication_id", "pulse_seq", "epoch_id", "state_sha256",
    "transition_sha256", "candidate_sha256", "status_sha256", "parent_committed",
    "transition", "non_claims", "generation_sha256",
}
RECEIPT_KEYS = {
    "schema", "publication_id", "pulse_seq", "epoch_id", "state_sha256",
    "transition_sha256", "candidate_sha256", "generation_sha256", "status_sha256",
    "parent_generation_sha256",
}
VIEW_KEYS = {"schema", "status", "generation", "non_claims"}


class LivePublication(unittest.TestCase):
    def setUp(self):
        self.pulse = pulse_tests.PulseSyncRetry(methodName="runTest")
        self.pulse.setUp()
        self.addCleanup(self.pulse.doCleanups)
        self.lib = self.pulse.sialib
        for name in ("_prepare_live_pulse_candidate", "_stage_live_generation",
                     "_publish_staged_live_generation", "_recover_pending_live_generation",
                     "_read_committed_live_generation"):
            self.assertTrue(callable(getattr(self.lib, name, None)), "committed live barrier missing: " + name)
        for name in ("LIVE_CANDIDATE_PATH", "LIVE_STATE_PATH", "LIVE_PUBLICATION_NON_CLAIMS"):
            self.assertTrue(hasattr(self.lib, name), name)
        self.loop = importlib.import_module("sialiveloop")
        self.fixture = live_tests.LiveLoopPureIntegration(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture._inputs()
        self.inputs = copy.deepcopy(self.fixture.kw)
        self.expected = self.loop.prepare_pulse(**self.inputs)
        self.temp = tempfile.TemporaryDirectory(prefix="sia-live-publication-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = {
            "STATE": str(self.root), "MEMO_PATH": str(self.root / "memo.json"),
            "STATUS_PATH": str(self.root / "status.json"), "GRAPH_PATH": str(self.root / "graph.json"),
            "LIVE_CANDIDATE_PATH": str(self.root / "live-loop-candidate.json"),
            "LIVE_STATE_PATH": str(self.root / "live-loop.json"),
            "CORPUS_OWNER_LOCK": str(self.root / "corpus-owner.lock"),
        }
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in self.paths.items():
            self.stack.enter_context(mock.patch.object(self.lib, name, value))
        self.original = {name: getattr(self.lib, name) for name in
                         ("atomic_write", "export_status", "read_json", "export_graph", "load_memo")}
        self.graph = self.pulse._empty_graph()
        self.status = self.pulse._complete_status()
        self.status["v"] = 2
        self.status["mind"]["familiarity_status"] = "complete"
        self.memo = {
            "pulse_seq": self.status["pulse_seq"], "pulse_history": copy.deepcopy(self.status["history"]),
            "chains": {"sia": "pass"}, "chains_checked_at": self.status["integrity"]["checked_at"],
            "redactions": {}, "ready": copy.deepcopy(pulse_tests.READY),
        }
        self._write(self.paths["GRAPH_PATH"], self.graph)
        self._write(self.paths["STATUS_PATH"], self.status)
        self._write(self.paths["MEMO_PATH"], self.memo)
        # The predecessor helper calls the internal transaction directly;
        # supply the real scoped owner that public pulse() normally holds.
        self.stack.enter_context(self.lib.corpus_owner())

    def _write(self, path, value):
        Path(path).write_bytes(live_tests.canonical(value) + b"\n")
        Path(path).chmod(0o600)

    def _read(self, name):
        return json.loads(Path(self.paths[name]).read_bytes())

    def _stage(self, **changes):
        return self.lib._stage_live_generation(**{
            "memo": self.memo, "status": self.status, "prepare_inputs": self.inputs,
            "expected_prepare_inputs_sha256": live_tests.digest(self.inputs), **changes,
        })

    def _publish(self):
        return self.lib._publish_staged_live_generation(memo=self.memo)

    def _view(self, *, memo=None, status=None):
        return self.lib._read_committed_live_generation(
            memo=self._read("MEMO_PATH") if memo is None else memo,
            admitted_status=self._read("STATUS_PATH") if status is None else status)

    def _assert_view(self, result, status):
        self.assertEqual(set(result), VIEW_KEYS)
        self.assertEqual(result["schema"], "sia-live-generation-view-v1")
        self.assertEqual(result["status"], status)
        self.assertEqual(result["non_claims"], list(self.lib.LIVE_PUBLICATION_NON_CLAIMS))
        if status != "available":
            self.assertIsNone(result["generation"])

    def _assert_bound(self, generation, candidate, receipt, status):
        self.assertEqual(set(candidate), CANDIDATE_KEYS)
        self.assertEqual(candidate["schema"], "sia-live-publication-candidate-v1")
        self.assertEqual(candidate["candidate_sha256"], live_tests.own_digest(candidate, "candidate_sha256"))
        self.assertEqual(candidate["prepare_inputs_sha256"], live_tests.digest(candidate["prepare_inputs"]))
        self.assertEqual(candidate["status"], status)
        self.assertEqual(candidate["status_sha256"], live_tests.digest(status))
        self.assertEqual(candidate["non_claims"], list(self.lib.LIVE_PUBLICATION_NON_CLAIMS))
        self.assertEqual(set(generation), GENERATION_KEYS)
        self.assertEqual(generation["schema"], "sia-live-committed-generation-v1")
        self.assertEqual(generation["generation_sha256"], live_tests.own_digest(generation, "generation_sha256"))
        self.assertEqual(generation["candidate_sha256"], candidate["candidate_sha256"])
        self.assertEqual(generation["parent_committed"], candidate["parent_committed"])
        self.assertEqual(generation["transition"], candidate["transition"])
        self.assertEqual(generation["non_claims"], list(self.lib.LIVE_PUBLICATION_NON_CLAIMS))
        self.assertEqual(set(receipt), RECEIPT_KEYS)
        self.assertEqual(receipt["schema"], "sia-live-publication-receipt-v1")
        for key in ("publication_id", "pulse_seq", "epoch_id", "state_sha256", "transition_sha256",
                    "candidate_sha256", "generation_sha256", "status_sha256"):
            self.assertEqual(receipt[key], generation[key], key)
        self.assertEqual(generation["publication_id"], status["publication_id"])
        self.assertEqual(generation["pulse_seq"], status["pulse_seq"])
        self.assertEqual(generation["status_sha256"], live_tests.digest(status))
        self.assertEqual(generation["state_sha256"], generation["transition"]["state_sha256"])
        self.assertEqual(generation["transition_sha256"], generation["transition"]["transition_sha256"])
        self.assertEqual(generation["epoch_id"], generation["transition"]["state"]["epoch_id"])
        parent = candidate["parent_committed"]
        self.assertEqual(receipt["parent_generation_sha256"], None if parent is None else parent["generation_sha256"])
        self.assertEqual(generation["transition"]["non_claims"], live_tests.NON_CLAIMS)
        self.assertEqual(generation["transition"]["state"]["non_claims"], live_tests.NON_CLAIMS)
        self.assertIsNotNone(self.lib._recoverable_status_integrity(status))

    def _inject_write_failure(self, target):
        original = self.lib.atomic_write

        def write(path, data, **kwargs):
            value = json.loads(data)
            selected = (str(path) == self.paths[target] if target != "final-memo"
                        else str(path) == self.paths["MEMO_PATH"] and "live_loop_committed" in value
                        and "live_loop_pending" not in value)
            if selected:
                raise OSError("synthetic publication boundary failure: " + target)
            return original(path, data, **kwargs)

        return mock.patch.object(self.lib, "atomic_write", side_effect=write)

    def _bridge_pulse_io(self):
        """Keep old pulse controls, but make only our scoped artifacts real."""
        if self.bridged:
            return
        self.bridged = True
        old_write, old_status = self.lib.atomic_write, self.lib.export_status
        old_read, old_graph = self.lib.read_json, self.lib.export_graph
        graph = old_read(self.lib.GRAPH_PATH, {})
        self.lib.GRAPH_PATH = self.paths["GRAPH_PATH"]
        self._write(self.paths["GRAPH_PATH"], graph)
        self._write(self.paths["MEMO_PATH"], self.pulse.barrier_persisted)

        def write(path, data, **kwargs):
            # Preserve the predecessor fixture's memo/cursor trace. Never
            # turn its unrelated mocked corpus writes into filesystem work.
            old_write(path, data, **kwargs)
            if str(path) in set(self.paths.values()) - {self.paths["STATE"], self.paths["CORPUS_OWNER_LOCK"]}:
                return self.original["atomic_write"](path, data, **kwargs)

        def status(value):
            old_status(value)
            return self.original["export_status"](value)

        def read(path, default):
            if str(path) in {self.paths["GRAPH_PATH"], self.paths["STATUS_PATH"],
                             self.paths["LIVE_CANDIDATE_PATH"], self.paths["LIVE_STATE_PATH"]}:
                return self.original["read_json"](path, default)
            return old_read(path, default)

        def graph_export():
            result = old_graph()
            self._write(self.paths["GRAPH_PATH"], old_read(self.lib.GRAPH_PATH, {}))
            return result

        self.lib.atomic_write = write
        self.lib.export_status = status
        self.lib.read_json = read
        self.lib.export_graph = graph_export

    def _run_pulse(self, *, started=True, eventful=False, initial_memo=None):
        self.bridged = False
        self.producer_calls = []
        observed_inputs = []
        admit = self.lib._require_status_sequence_not_ahead

        def admission(sequence):
            self._bridge_pulse_io()
            return admit(sequence)

        def producer(*, memo, status, events, observed_at, idle):
            self.producer_calls.append({"memo": copy.deepcopy(memo), "status": copy.deepcopy(status),
                                        "events": list(events), "observed_at": observed_at, "idle": idle})
            if not started:
                return None
            inputs = copy.deepcopy(self.inputs)
            inputs["observed_at"] = live_tests.NOW
            inputs["idle"] = idle
            inputs["gist_inputs"] = copy.deepcopy(self.fixture.gist_inputs) if idle else None
            observed_inputs.append(inputs)
            return {"prepare_inputs": inputs, "expected_prepare_inputs_sha256": live_tests.digest(inputs)}

        # This clock is the existing pure fixture input, merely represented
        # through the runtime's UTC formatter; no new timestamp is invented.
        fixed_utc = self.lib.datetime.datetime.fromtimestamp(live_tests.NOW, self.lib.datetime.timezone.utc)
        event = self.lib.Event("notify", fixed_utc, "notification", "synthetic publication event",
                               occurrence="fixture:live-publication")

        def sense_fixture(cursors):
            return [event]

        def event_page(organ, day, events, **kwargs):
            return (["events/fixture"], list(events), [(item, "events/fixture") for item in events])

        legacy_transition = {"workspace": [], "memory_state": {}, "novelty_thoughts": [],
                             "findings": [], "coincidences": [], "already_applied": False}
        try:
            with contextlib.ExitStack() as patches:
                patches.enter_context(mock.patch.object(self.lib, "_require_status_sequence_not_ahead", side_effect=admission))
                patches.enter_context(mock.patch.object(self.lib, "_prepare_live_pulse_candidate", side_effect=producer))
                patches.enter_context(mock.patch.object(self.lib, "utcnow", return_value=fixed_utc))
                patches.enter_context(mock.patch.object(self.lib.time, "time", return_value=live_tests.NOW))
                patches.enter_context(mock.patch.object(self.lib, "verify_chains", return_value={"sia": "pass"}))
                patches.enter_context(mock.patch.object(self.lib, "gbrain_call", return_value=[]))
                patches.enter_context(mock.patch.object(self.lib, "gbrain", side_effect=AssertionError("no live database")))
                if eventful:
                    patches.enter_context(mock.patch.object(self.lib, "update_day_page", side_effect=event_page))
                    patches.enter_context(mock.patch.object(self.lib, "ensure_event_entities", return_value=False))
                    patches.enter_context(mock.patch.object(self.lib, "_preflight_event_path_plan", return_value=None))
                    patches.enter_context(mock.patch.object(self.lib, "_event_cognitive_transition", return_value=legacy_transition))
                    patches.enter_context(mock.patch.object(self.lib.siamind, "compact_mind_for_persistence", side_effect=lambda value: value))
                result = self.pulse._run_barrier_pulse(
                    page_activity=False, senses=[sense_fixture] if eventful else [],
                    initial_memo=self.memo if initial_memo is None else initial_memo,
                    initial_graph=self.graph)
        finally:
            for name, value in self.original.items():
                setattr(self.lib, name, value)
            self.lib.GRAPH_PATH = self.paths["GRAPH_PATH"]
        self.pulse_inputs = observed_inputs
        return result

    def test_helpers_have_exact_keyword_only_rosters_and_no_defaults(self):
        expected = {
            "_prepare_live_pulse_candidate": {"memo", "status", "events", "observed_at", "idle"},
            "_stage_live_generation": {"memo", "status", "prepare_inputs", "expected_prepare_inputs_sha256"},
            "_publish_staged_live_generation": {"memo"}, "_recover_pending_live_generation": {"memo"},
            "_read_committed_live_generation": {"memo", "admitted_status"},
        }
        for name, fields in expected.items():
            signature = inspect.signature(getattr(self.lib, name))
            self.assertEqual(set(signature.parameters), fields)
            for parameter in signature.parameters.values():
                self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(parameter.default, inspect.Parameter.empty)

    def test_unstarted_reader_and_recovery_do_not_create_a_controller_epoch(self):
        self._assert_view(self._view(), "not-started")
        self.assertIs(self.lib._recover_pending_live_generation(memo=self.memo), False)
        self.assertIs(self.lib._prepare_live_pulse_candidate(
            memo=self.memo, status=self.status, events=[], observed_at=live_tests.NOW, idle=True), None)
        self.assertFalse(Path(self.paths["LIVE_CANDIDATE_PATH"]).exists())
        self.assertFalse(Path(self.paths["LIVE_STATE_PATH"]).exists())

    def test_stage_is_pending_and_publisher_commits_exact_complete_transition(self):
        before = copy.deepcopy(self.inputs)
        with mock.patch.object(self.loop, "prepare_pulse", wraps=self.loop.prepare_pulse) as replay:
            self._stage()
        self.assertTrue(replay.called)
        candidate = self._read("LIVE_CANDIDATE_PATH")
        self.assertEqual(candidate["prepare_inputs"], self.inputs)
        self.assertEqual(candidate["transition"], self.expected)
        self.assertIsNone(candidate["parent_committed"])
        self.assertEqual(self.inputs, before)
        self.assertIn("live_loop_pending", self._read("MEMO_PATH"))
        self.assertNotIn("live_loop_committed", self._read("MEMO_PATH"))
        self.assertFalse(Path(self.paths["LIVE_STATE_PATH"]).exists())
        self._assert_view(self._view(), "pending")
        result = self._publish()
        generation = self._read("LIVE_STATE_PATH")
        self.assertEqual(result, generation)
        memo = self._read("MEMO_PATH")
        self.assertNotIn("live_loop_pending", memo)
        self._assert_bound(generation, candidate, memo["live_loop_committed"], self._read("STATUS_PATH"))
        view = self._view()
        self._assert_view(view, "available")
        self.assertEqual(view["generation"], generation)
        view["generation"]["transition"]["state"]["uses"].clear()
        self.assertEqual(self._read("LIVE_STATE_PATH"), generation)

    def test_real_idle_pulse_uses_durable_status_identity_without_corpus_sync(self):
        with mock.patch.object(self.loop, "prepare_pulse", wraps=self.loop.prepare_pulse) as replay:
            status = self._run_pulse()
        self.assertTrue(replay.called)
        self.assertTrue(self.producer_calls)
        self.assertTrue(self.producer_calls[-1]["idle"])
        self.assertEqual(self.producer_calls[-1]["events"], [])
        self.assertEqual(self.producer_calls[-1]["observed_at"], live_tests.NOW)
        self.assertFalse(any(row[0] in {"commit", "sync", "graph"} for row in self.pulse.barrier_trace))
        self.assertEqual(status["v"], 2)
        self.assertEqual(set(status), self.lib._RECOVERABLE_STATUS_KEYS)
        candidate, generation, memo = self._read("LIVE_CANDIDATE_PATH"), self._read("LIVE_STATE_PATH"), self._read("MEMO_PATH")
        self._assert_bound(generation, candidate, memo["live_loop_committed"], status)
        self.assertEqual(candidate["prepare_inputs"], self.pulse_inputs[-1])
        self.assertNotIn("pulse_publication", memo)
        self._assert_view(self._view(), "available")

    def test_real_event_pulse_joins_existing_named_publication_without_new_source_authority_claim(self):
        status = self._run_pulse(eventful=True)
        self.assertTrue(self.producer_calls)
        call = self.producer_calls[-1]
        self.assertFalse(call["idle"])
        self.assertEqual([event.occurrence for event in call["events"]], ["fixture:live-publication"])
        self.assertEqual(status["events_pulse"], len(call["events"]))
        self.assertTrue(any(row[0] == "commit" for row in self.pulse.barrier_trace))
        self.assertTrue(any(row[0] == "sync" for row in self.pulse.barrier_trace))
        self.assertEqual(status["ledger_transition"]["state"], "signed")
        self._assert_bound(self._read("LIVE_STATE_PATH"), self._read("LIVE_CANDIDATE_PATH"),
                           self._read("MEMO_PATH")["live_loop_committed"], status)
        self.assertNotIn("pulse_publication", self._read("MEMO_PATH"))

    def test_no_candidate_pulse_preserves_the_legacy_status_contract(self):
        status = self._run_pulse(started=False)
        self.assertEqual(status["v"], 2)
        self.assertEqual(set(status), self.lib._RECOVERABLE_STATUS_KEYS)
        self.assertNotIn("live_loop", status)
        self.assertNotIn("live_loop_pending", self._read("MEMO_PATH"))
        self.assertNotIn("live_loop_committed", self._read("MEMO_PATH"))
        self._assert_view(self._view(), "not-started")

    def test_status_v1_v2_validators_remain_closed_and_legacy_effectless_roster_unchanged(self):
        for version in (1, 2):
            status = self.pulse._complete_status()
            status["v"] = version
            if version == 2:
                status["mind"]["familiarity_status"] = "complete"
            self.assertIsNotNone(self.lib._recoverable_status_integrity(status))
            self.assertIsNone(self.lib._recoverable_status_integrity({**status, "live_loop": {}}))
        self.assertEqual(self.lib._LEGACY_EFFECTLESS_STATUS_KEYS,
                         self.lib._RECOVERABLE_STATUS_KEYS - {"graph_publication_id"})

    def test_each_pre_final_write_failure_retains_pending_without_availability(self):
        for target in ("LIVE_STATE_PATH", "STATUS_PATH", "final-memo"):
            with self.subTest(target=target):
                self._stage()
                with self._inject_write_failure(target), self.assertRaises((OSError, RuntimeError)):
                    self._publish()
                retained = self._read("MEMO_PATH")
                self.assertIn("live_loop_pending", retained)
                self.assertNotIn("live_loop_committed", retained)
                self._assert_view(self._view(), "pending")
                self.memo = retained
        self.assertTrue(Path(self.paths["LIVE_STATE_PATH"]).exists())
        self.assertEqual(self._read("STATUS_PATH"), self.status)

    def test_candidate_published_before_pending_crash_is_orphan_not_absence_and_exact_retry_recovers(self):
        original = self.lib.atomic_write

        def refuse_pending(path, data, **kwargs):
            if str(path) == self.paths["MEMO_PATH"] and "live_loop_pending" in json.loads(data):
                raise OSError("synthetic pending-memo publication failure")
            return original(path, data, **kwargs)

        with mock.patch.object(self.lib, "atomic_write", side_effect=refuse_pending), self.assertRaises((OSError, RuntimeError)):
            self._stage()
        candidate_bytes = Path(self.paths["LIVE_CANDIDATE_PATH"]).read_bytes()
        self.assertNotIn("live_loop_pending", self._read("MEMO_PATH"))
        self.assertFalse(Path(self.paths["LIVE_STATE_PATH"]).exists())
        with self.assertRaises(RuntimeError):
            self._view()
        with self.assertRaises(RuntimeError):
            self.lib._recover_pending_live_generation(memo=self._read("MEMO_PATH"))
        self.memo = self._read("MEMO_PATH")
        self._stage()
        self.assertEqual(Path(self.paths["LIVE_CANDIDATE_PATH"]).read_bytes(), candidate_bytes)
        self._publish()
        self._assert_view(self._view(), "available")

    def test_reader_cannot_use_in_memory_final_receipt_before_its_durable_memo(self):
        self._stage()
        original = self.lib.atomic_write
        proposed = []

        def refuse_final(path, data, **kwargs):
            value = json.loads(data)
            if str(path) == self.paths["MEMO_PATH"] and "live_loop_committed" in value and "live_loop_pending" not in value:
                proposed.append(copy.deepcopy(value))
                raise OSError("synthetic final memo failure")
            return original(path, data, **kwargs)

        with mock.patch.object(self.lib, "atomic_write", side_effect=refuse_final), self.assertRaises((OSError, RuntimeError)):
            self._publish()
        self.assertTrue(proposed)
        self._assert_view(self._view(), "pending")
        with self.assertRaises(RuntimeError):
            self._view(memo=proposed[-1])

    def test_recovery_replays_frozen_inputs_at_original_sequence_without_new_producer_or_clock(self):
        self._stage()
        candidate = self._read("LIVE_CANDIDATE_PATH")
        memo = self._read("MEMO_PATH")
        # Both literals already belong to the predecessor pulse fixture; the
        # candidate used its existing status sequence, and this is a later
        # observed fixture allocator value, not a derived timestamp or count.
        later = pulse_tests.FROZEN_EFFECTLESS_STATUS["pulse_seq"]
        self.assertGreater(later, candidate["status"]["pulse_seq"])
        memo["pulse_seq"] = later
        self._write(self.paths["MEMO_PATH"], memo)
        with mock.patch.object(self.loop, "prepare_pulse", wraps=self.loop.prepare_pulse) as replay, \
                mock.patch.object(self.lib, "_prepare_live_pulse_candidate", side_effect=AssertionError("no new inputs")), \
                mock.patch.object(self.lib, "utcnow", side_effect=AssertionError("no replacement clock")), \
                mock.patch.object(self.lib.time, "time", side_effect=AssertionError("no replacement clock")):
            result = self.lib._recover_pending_live_generation(memo=memo)
        self.assertIsNot(result, False)
        self.assertTrue(replay.called)
        self.assertTrue(any(call.kwargs == candidate["prepare_inputs"] for call in replay.call_args_list))
        generation = self._read("LIVE_STATE_PATH")
        self.assertEqual(generation["pulse_seq"], candidate["status"]["pulse_seq"])
        self.assertEqual(generation["publication_id"], candidate["status"]["publication_id"])
        self.assertEqual(generation["transition"], candidate["transition"])
        self.assertEqual(self._read("MEMO_PATH")["pulse_seq"], later)
        self.assertEqual(self._read("STATUS_PATH"), candidate["status"])
        self._assert_view(self._view(), "available")

    def test_recovery_is_attempted_before_old_pulse_recovery_and_refreshes_status_admission(self):
        predecessor_status = copy.deepcopy(self.status)
        predecessor_status["publication_id"] = "e" * 32
        self.assertNotEqual(predecessor_status, self.status)
        self._write(self.paths["STATUS_PATH"], predecessor_status)
        self._stage()
        original = self.lib._recover_pending_live_generation
        seen = []

        def recover(*, memo):
            seen.append("live-recover")
            result = original(memo=memo)
            seen.append("live-recovered")
            return result

        old_recovery = self.lib._recover_before_pulse

        def remaining(*args, **kwargs):
            self.assertIn("live-recovered", seen)
            self.assertNotIn("live_loop_pending", self._read("MEMO_PATH"))
            return old_recovery(*args, **kwargs)

        # This new pulse intentionally supplies no next candidate. Its status
        # may advance, but the recovered generation must retain its old ID.
        candidate = self._read("LIVE_CANDIDATE_PATH")
        with mock.patch.object(self.lib, "_recover_pending_live_generation", side_effect=recover), \
                mock.patch.object(self.lib, "_recover_before_pulse", side_effect=remaining):
            status = self._run_pulse(started=False, initial_memo=self._read("MEMO_PATH"))
        self.assertIsNotNone(self.lib._recoverable_status_integrity(status))
        generation = self._read("LIVE_STATE_PATH")
        self.assertEqual(generation["publication_id"], candidate["status"]["publication_id"])
        self.assertEqual(generation["pulse_seq"], candidate["status"]["pulse_seq"])

    def test_changed_graph_or_parent_refuses_recovery_without_rebinding_candidate(self):
        self._stage()
        candidate = Path(self.paths["LIVE_CANDIDATE_PATH"]).read_bytes()
        graph = copy.deepcopy(self.graph)
        graph["publication_id"] = "c" * 32
        self._write(self.paths["GRAPH_PATH"], graph)
        with self.assertRaises(RuntimeError):
            self.lib._recover_pending_live_generation(memo=self._read("MEMO_PATH"))
        self.assertEqual(Path(self.paths["LIVE_CANDIDATE_PATH"]).read_bytes(), candidate)
        self.assertIn("live_loop_pending", self._read("MEMO_PATH"))
        self._write(self.paths["GRAPH_PATH"], self.graph)
        memo = self._read("MEMO_PATH")
        memo["live_loop_pending"]["parent_generation_sha256"] = "0" * 64
        self._write(self.paths["MEMO_PATH"], memo)
        with self.assertRaises(RuntimeError):
            self.lib._recover_pending_live_generation(memo=memo)
        self.assertEqual(Path(self.paths["LIVE_CANDIDATE_PATH"]).read_bytes(), candidate)

    def test_changed_status_state_or_policy_is_not_available_even_with_a_rehashed_outer_file(self):
        self._stage()
        self._publish()
        generation = self._read("LIVE_STATE_PATH")
        candidate = self._read("LIVE_CANDIDATE_PATH")
        wrong_status = copy.deepcopy(self.status)
        wrong_status["publication_id"] = "d" * 32
        with self.assertRaises(RuntimeError):
            self._view(status=wrong_status)
        changed = copy.deepcopy(generation)
        changed["transition"]["state"]["uses"].clear()
        changed["generation_sha256"] = live_tests.own_digest(changed, "generation_sha256")
        self._write(self.paths["LIVE_STATE_PATH"], changed)
        with self.assertRaises(RuntimeError):
            self._view()
        self._write(self.paths["LIVE_STATE_PATH"], generation)
        changed = copy.deepcopy(candidate)
        changed["prepare_inputs"]["policy"]["activation_events"] = []
        changed["prepare_inputs"]["expected_policy_sha256"] = live_tests.digest(changed["prepare_inputs"]["policy"])
        changed["prepare_inputs_sha256"] = live_tests.digest(changed["prepare_inputs"])
        changed["candidate_sha256"] = live_tests.own_digest(changed, "candidate_sha256")
        self._write(self.paths["LIVE_CANDIDATE_PATH"], changed)
        with self.assertRaises(RuntimeError):
            self._view()

    def test_whole_memo_capacity_is_preflighted_before_candidate_publication(self):
        before = Path(self.paths["MEMO_PATH"]).read_bytes()
        with mock.patch.object(self.lib, "MAX_MEMO_BYTES", 1), \
                mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("capacity before writes")), \
                self.assertRaises((RuntimeError, ValueError)):
            self._stage()
        self.assertEqual(Path(self.paths["MEMO_PATH"]).read_bytes(), before)
        self.assertFalse(Path(self.paths["LIVE_CANDIDATE_PATH"]).exists())

    def test_candidate_domains_and_independent_input_pin_refuse_before_writes(self):
        malformed = copy.deepcopy(self.inputs)
        malformed["extra"] = malformed
        for changes in ({"prepare_inputs": malformed}, {"expected_prepare_inputs_sha256": "0" * 64},
                        {"prepare_inputs": {**self.inputs, "source_claim": {"trust": True}}}):
            with self.subTest(fields=list(changes)), \
                    mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("admission before writes")), \
                    self.assertRaises((RuntimeError, ValueError)):
                self._stage(**changes)
        self.assertFalse(Path(self.paths["LIVE_CANDIDATE_PATH"]).exists())

    def test_candidate_and_generation_are_private_ordinary_nofollow_and_orphans_refuse(self):
        self._stage()
        self._publish()
        for name in ("LIVE_CANDIDATE_PATH", "LIVE_STATE_PATH"):
            path = Path(self.paths[name])
            info = path.lstat()
            self.assertTrue(stat.S_ISREG(info.st_mode))
            self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
            self.assertEqual(info.st_uid, os.geteuid())
            self.assertEqual(info.st_nlink, 1)
            retained = self.root / (name + ".retained")
            path.rename(retained)
            path.symlink_to(retained)
            with self.assertRaises(RuntimeError):
                self._view()
            path.unlink()
            retained.rename(path)
        memo = self._read("MEMO_PATH")
        memo.pop("live_loop_committed")
        self._write(self.paths["MEMO_PATH"], memo)
        with self.assertRaises(RuntimeError):
            self._view()
        with self.assertRaises(RuntimeError):
            self.lib._recover_pending_live_generation(memo=memo)


if __name__ == "__main__":
    unittest.main()
