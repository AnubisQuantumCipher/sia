"""Retained controller-source batch -> pure live producer contract.

Root alone executes this fixture.  Actual private collectors and the original
page/intake planners run only while the source fixture captures its batch.
The operation under test begins after that exact batch has been durably staged.
It may read the descriptor-bound pending view and, for an explicit stable live
parent, the existing committed-generation reader.  It may not recollect,
rerender, enter the legacy replay/mind transaction, or publish anything.

The result is only the existing ``prepare_inputs`` envelope consumed by
``sialiveloop.prepare_pulse``.  A successful empty source batch is still an
explicit complete observation frame.  Empty delivery history, ``idle=False``
and ``gist_inputs=None`` are deliberate first-producer contracts, not evidence
of output delivery, resident execution, biological cognition, or a held-out
win.  Source acknowledgment and the joined live publication/commit transition
remain outside this producer-only increment.
"""

import contextlib
import copy
import inspect
import json
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_source_capture as capture_tests
from tests import test_live_loop as live_tests
from tests import test_live_publication as publication_tests


PRODUCER = "_prepare_controller_source_live_candidate"
RESULT_KEYS = {"prepare_inputs", "expected_prepare_inputs_sha256"}
PREPARE_KEYS = {
    "intake", "expected_intake_sha256", "deliveries",
    "expected_deliveries_sha256", "previous_state",
    "expected_previous_state_sha256", "policy",
    "expected_policy_sha256", "observed_at", "idle", "gist_inputs",
}


class ControllerSourceLiveProducer(unittest.TestCase):
    def setUp(self):
        self.source = capture_tests.ControllerSourceCapture(methodName="runTest")
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)

        # This supplies real sialiveloop inputs and the descriptor-bound live
        # publication/reader implementation, in its own isolated artifact root.
        self.live = publication_tests.LivePublication(methodName="runTest")
        self.live.setUp()
        self.addCleanup(self.live.doCleanups)
        self.lib = self.live.lib
        self.loop = self.live.loop

        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.source_path = self.live.root / "controller-source-batch.json"
        for name, value in (
                ("CONTROLLER_SOURCE_BATCH_PATH", str(self.source_path)),
                ("BRAINSTEM_OWNER_LOCK", str(self.live.root / "brainstem-owner.lock"))):
            self.stack.enter_context(mock.patch.object(self.lib, name, value))

    def _producer(self):
        producer = getattr(self.lib, PRODUCER, None)
        self.assertTrue(callable(producer), "missing retained-source live producer: " + PRODUCER)
        return producer

    def _capture(self, *, empty=False):
        if empty:
            selected = [self.source.custom_entries[-1]]
            disabled = sorted(set(self.source.lib.BASE_ORGANS)
                              | set(self.source.lib.OPTIONAL_ORGANS))
            self.source.install_config({
                "senses": {"disable": disabled}, "custom_senses": selected})
            self.source.configure_selection([], selected)
        batch = self.source.capture()
        self.source.assert_batch(batch)
        if empty:
            self.assertIsNone(batch["event_closure"])
            self.assertEqual(batch["intake_projection"]["intake"]["observations"], [])
        else:
            self.assertIsNotNone(batch["event_closure"])
        return batch

    def _stage(self, batch):
        self.assertIsNone(self.lib._stage_controller_source_batch(
            memo=self.live.memo, batch=batch,
            expected_batch_sha256=batch["batch_sha256"]))
        durable = self.live._read("MEMO_PATH")
        self.assertEqual(durable, self.live.memo)
        self.assertIn("controller_source_pending", durable)
        self.assertNotIn("ready", durable)
        self.assertEqual(self.source_path.read_bytes(), capture_tests.canonical(batch))
        return json.loads(self.source_path.read_bytes())

    @staticmethod
    def _expected_inputs(batch, *, previous=None, previous_sha256=None):
        intake = copy.deepcopy(batch["intake_projection"]["intake"])
        deliveries = {
            "schema": "sia-live-deliveries-v1",
            "epoch_id": intake["epoch_id"],
            "complete": True,
            "records": [],
        }
        return {
            "intake": intake,
            "expected_intake_sha256": batch["intake_projection"]["intake_sha256"],
            "deliveries": deliveries,
            "expected_deliveries_sha256": live_tests.digest(deliveries),
            "previous_state": copy.deepcopy(previous),
            "expected_previous_state_sha256": previous_sha256,
            "policy": copy.deepcopy(batch["epoch"]["live_policy"]),
            "expected_policy_sha256": batch["epoch"]["expected_live_policy_sha256"],
            "observed_at": batch["observed_at"],
            "idle": False,
            "gist_inputs": None,
        }

    def _artifact_images(self):
        paths = {
            "source": self.source_path,
            "memo": Path(self.live.paths["MEMO_PATH"]),
            "status": Path(self.live.paths["STATUS_PATH"]),
            "graph": Path(self.live.paths["GRAPH_PATH"]),
            "candidate": Path(self.live.paths["LIVE_CANDIDATE_PATH"]),
            "generation": Path(self.live.paths["LIVE_STATE_PATH"]),
        }
        return {name: path.read_bytes() if path.exists() else None
                for name, path in paths.items()}

    @contextlib.contextmanager
    def _producer_boundary(self, *, parent=False):
        def forbidden(name):
            return mock.Mock(side_effect=AssertionError(
                "retained-source producer reached forbidden operation: " + name))

        with contextlib.ExitStack() as stack:
            # No fresh source authority, event render, legacy replay, live
            # publication, or legacy mind/database path belongs to this seam.
            names = (
                "_capture_controller_source_batch", "sense_aegis", "sense_custom",
                "_prepare_event_page_plan", "_compose_event_page_plans",
                "_compose_event_page_batch_closure", "_prepare_event_live_intake",
                "_publish_event_page_plan", "_publish_event_page_plan_batch",
                "_publish_event_page_batch_closure", "update_day_page",
                "_pending_source_replay_marker", "_authorize_pending_source_replay",
                "_source_replay_events", "_pulse_transaction_guarded",
                "_event_cognitive_transition", "load_cursors", "load_thoughts",
                "gbrain", "gbrain_call", "brain_sync", "save_mind",
                "_stage_live_generation", "_publish_staged_live_generation",
                "atomic_write", "_write_memo", "export_status",
            )
            for name in names:
                if hasattr(self.lib, name):
                    stack.enter_context(mock.patch.object(
                        self.lib, name, new=forbidden(name)))
            if hasattr(self.lib, "siamind"):
                for name in ("load_mind", "save_mind"):
                    if hasattr(self.lib.siamind, name):
                        stack.enter_context(mock.patch.object(
                            self.lib.siamind, name, new=forbidden("siamind." + name)))
            if not parent:
                stack.enter_context(mock.patch.object(
                    self.lib, "_read_committed_live_generation",
                    new=forbidden("_read_committed_live_generation")))
            yield

    def _prepare_candidate(self, *, parent=False, admitted_status=None):
        status = self.live.status if admitted_status is None else admitted_status
        before = self._artifact_images()
        retained_reader = self.lib._read_pending_controller_source_batch
        with mock.patch.object(
                self.lib, "_read_pending_controller_source_batch",
                wraps=retained_reader) as source_reader, \
                self._producer_boundary(parent=parent):
            result = self._producer()(
                memo=self.live.memo, admitted_status=status)
        source_reader.assert_called_once_with(memo=self.live.memo)
        self.assertEqual(self._artifact_images(), before)
        self.assertEqual(set(result), RESULT_KEYS)
        self.assertEqual(set(result["prepare_inputs"]), PREPARE_KEYS)
        self.assertEqual(result["expected_prepare_inputs_sha256"],
                         live_tests.digest(result["prepare_inputs"]))
        durable = self.live._read("MEMO_PATH")
        self.assertIn("controller_source_pending", self.live.memo)
        self.assertEqual(durable["controller_source_pending"],
                         self.live.memo["controller_source_pending"])
        self.assertNotIn("ready", self.live.memo)
        self.assertNotIn("ready", durable)
        return result

    def _commit_matching_parent(self, batch):
        inputs = self._expected_inputs(batch)
        self.live.inputs = copy.deepcopy(inputs)
        self.live.expected = self.loop.prepare_pulse(**inputs)
        self.live._stage()
        generation = self.live._publish()
        self.assertEqual(self.live._view()["status"], "available")
        self.assertIn("live_loop_committed", self.live.memo)
        self.assertIn("ready", self.live.memo)
        return generation

    def test_exact_api_reads_only_retained_batch_and_returns_existing_prepare_envelope(self):
        signature = inspect.signature(self._producer())
        self.assertEqual(tuple(signature.parameters), ("memo", "admitted_status"))
        for parameter in signature.parameters.values():
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)

        supplied = self._capture()
        retained = self._stage(supplied)
        # A caller's post-stage object cannot become producer authority.
        supplied["intake_projection"]["intake"]["observations"].clear()
        supplied["epoch"]["live_policy"]["activation_events"].clear()

        candidate = self._prepare_candidate()
        expected = self._expected_inputs(retained)
        self.assertEqual(candidate, {
            "prepare_inputs": expected,
            "expected_prepare_inputs_sha256": live_tests.digest(expected),
        })
        transition = self.loop.prepare_pulse(**candidate["prepare_inputs"])
        self.assertEqual(transition["state"]["intake"],
                         retained["intake_projection"]["intake"])
        self.assertEqual(transition["state"]["policy"],
                         retained["epoch"]["live_policy"])
        self.assertEqual(transition["state"]["observed_at"], retained["observed_at"])
        self.assertIs(transition["state"]["deliveries"]["complete"], True)
        self.assertEqual(transition["state"]["deliveries"]["records"], [])
        self.assertIs(transition["state"]["idle"]["requested"], False)
        self.assertIsNone(transition["state"]["idle"]["gist"])

    def test_successful_empty_batch_still_produces_a_complete_live_state(self):
        retained = self._stage(self._capture(empty=True))
        candidate = self._prepare_candidate()
        expected = self._expected_inputs(retained)
        self.assertEqual(candidate["prepare_inputs"], expected)
        self.assertEqual(expected["intake"]["observations"], [])
        self.assertEqual(expected["deliveries"]["records"], [])

        transition = self.loop.prepare_pulse(**candidate["prepare_inputs"])
        self.assertEqual(transition["schema"], "sia-live-loop-transition-v1")
        self.assertEqual(transition["state"]["schema"], "sia-live-loop-state-v1")
        self.assertEqual(transition["state"]["epoch_id"], expected["intake"]["epoch_id"])
        self.assertEqual(transition["state"]["intake"], expected["intake"])
        self.assertEqual(transition["state"]["uses"], [])
        self.assertEqual(transition["state"]["workspace"]["slots"], [])
        self.assertEqual(transition["gist_pages"], [])

    def test_explicit_validated_committed_generation_is_the_only_parent(self):
        batch = self._capture()
        generation = self._commit_matching_parent(batch)
        retained = self._stage(batch)
        parent_state = generation["transition"]["state"]
        parent_sha256 = generation["state_sha256"]
        original_reader = self.lib._read_committed_live_generation

        with mock.patch.object(
                self.lib, "_read_committed_live_generation",
                wraps=original_reader) as reader:
            candidate = self._prepare_candidate(parent=True)
        reader.assert_called_once_with(
            memo=self.live.memo, admitted_status=self.live.status)
        expected = self._expected_inputs(
            retained, previous=parent_state, previous_sha256=parent_sha256)
        self.assertEqual(candidate["prepare_inputs"], expected)
        transition = self.loop.prepare_pulse(**candidate["prepare_inputs"])
        self.assertEqual(transition["state"]["parent_state_sha256"], parent_sha256)
        self.assertEqual(transition["state"]["intake"],
                         retained["intake_projection"]["intake"])

    def test_invalid_legacy_parent_context_refuses_without_rebinding_or_writes(self):
        batch = self._capture()
        self._commit_matching_parent(batch)
        self._stage(batch)
        wrong_status = copy.deepcopy(self.live.status)
        wrong_status["publication_id"] = "d" * 32
        before = self._artifact_images()
        pending = copy.deepcopy(self.live.memo["controller_source_pending"])

        with self._producer_boundary(parent=True), self.assertRaises(RuntimeError):
            self._producer()(
                memo=self.live.memo, admitted_status=wrong_status)
        self.assertEqual(self._artifact_images(), before)
        self.assertEqual(self.live.memo["controller_source_pending"], pending)
        self.assertNotIn("ready", self.live.memo)


if __name__ == "__main__":
    unittest.main()
