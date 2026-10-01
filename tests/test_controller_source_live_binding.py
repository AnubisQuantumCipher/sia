"""Write-ahead binding for one retained-source live transition.

Root alone executes this fixture.  The composed producer fixture captures and
stages the real bounded source batch before the operation under test.  This
increment may replay the pure ``sialiveloop`` transition, but its sole durable
effect is a compact ``controller_source_live_pending`` memo marker.  It may
not publish event closure pages, a live candidate/generation, source cursors,
refusal settlements, status, graph, or legacy mind state.

The marker is write-ahead recovery authority, not source acknowledgment, live
availability, output delivery, biological cognition, or a held-out win.  Its
32-hex publication ID is only a compact handle for a retained full identity
hash; every downstream effect must continue to validate the full pins.
"""

import contextlib
import copy
import inspect
import json
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_source_live_transaction as producer_tests
from tests import test_live_loop as live_tests
from tests import test_live_publication as publication_tests


STAGER = "_stage_controller_source_live_binding"
NON_CLAIMS = "CONTROLLER_SOURCE_LIVE_BINDING_NON_CLAIMS"
MARKER_KEYS = {
    "schema", "status", "seq", "publication_id", "publication_sha256",
    "source_pending_receipt", "source_batch_sha256",
    "source_batch_wire_sha256", "observed_at", "prepare_inputs_sha256",
    "state_sha256", "transition_sha256", "parent_generation_sha256",
    "parent_state_sha256", "event_closure_sha256",
    "admitted_status_sha256", "non_claims", "marker_sha256",
}
IDENTITY_KEYS = MARKER_KEYS - {
    "schema", "publication_id", "publication_sha256", "marker_sha256",
}


class ControllerSourceLiveBinding(unittest.TestCase):
    def setUp(self):
        self.fixture = producer_tests.ControllerSourceLiveProducer(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.lib = self.fixture.lib
        self.live = self.fixture.live
        self.loop = self.fixture.loop

    def _stager(self):
        stage = getattr(self.lib, STAGER, None)
        self.assertTrue(callable(stage), "missing controller-source live binding stage: " + STAGER)
        self.assertTrue(hasattr(self.lib, NON_CLAIMS),
                        "missing controller-source live binding nonclaims")
        return stage

    def _source(self, *, parent=False, empty=False):
        batch = self.fixture._capture(empty=empty)
        generation = self.fixture._commit_matching_parent(batch) if parent else None
        retained = self.fixture._stage(batch)
        return retained, generation

    @staticmethod
    def _publication_basis(fields):
        return {
            "schema": "sia-controller-source-live-publication-identity-v1",
            "binding": {key: copy.deepcopy(fields[key])
                        for key in sorted(IDENTITY_KEYS)},
        }

    def _expected(self, batch, candidate, transition, *, generation=None,
                  admitted_status=None, seq=None):
        status = self.live.status if admitted_status is None else admitted_status
        sequence = status["pulse_seq"] if seq is None else seq
        receipt = copy.deepcopy(self.live.memo["controller_source_pending"])
        fields = {
            "status": "prepared-not-published",
            "seq": sequence,
            "source_pending_receipt": receipt,
            "source_batch_sha256": receipt["batch_sha256"],
            "source_batch_wire_sha256": receipt["batch_wire_sha256"],
            "observed_at": batch["observed_at"],
            "prepare_inputs_sha256": candidate["expected_prepare_inputs_sha256"],
            "state_sha256": transition["state_sha256"],
            "transition_sha256": transition["transition_sha256"],
            "parent_generation_sha256": (
                None if generation is None else generation["generation_sha256"]),
            "parent_state_sha256": (
                None if generation is None else generation["state_sha256"]),
            "event_closure_sha256": (
                None if batch["event_closure"] is None
                else batch["event_closure"]["closure_sha256"]),
            "admitted_status_sha256": live_tests.digest(status),
            "non_claims": list(getattr(self.lib, NON_CLAIMS)),
        }
        publication_sha256 = live_tests.digest(self._publication_basis(fields))
        marker = {
            "schema": "sia-controller-source-live-pending-v1",
            **fields,
            "publication_id": publication_sha256[:32],
            "publication_sha256": publication_sha256,
        }
        marker["marker_sha256"] = live_tests.digest(marker)
        return marker

    def _images(self):
        images = self.fixture._artifact_images()
        images.pop("memo")
        images["source-cursors"] = Path(
            self.fixture.source.lib.CURSORS_PATH).read_bytes()
        images["source-corpus"] = self.fixture.source.pages.snapshot()
        return images

    @contextlib.contextmanager
    def _effect_boundary(self, *, permit_marker_write):
        writes = []
        attempted_effects = []
        original_write = self.lib.atomic_write
        memo_path = Path(self.live.paths["MEMO_PATH"])

        def write(path, data, **kwargs):
            if not permit_marker_write:
                raise AssertionError("binding retry/refusal attempted a write")
            self.assertEqual(str(path), str(memo_path),
                             "binding stage may write only the durable memo")
            self.assertEqual(attempted_effects, [],
                             "an effect was attempted before the binding marker")
            value = json.loads(data)
            self.assertIn("controller_source_live_pending", value)
            writes.append(copy.deepcopy(value["controller_source_live_pending"]))
            return original_write(path, data, **kwargs)

        def forbidden(name):
            def reject(*_args, **_kwargs):
                attempted_effects.append(name)
                durable = json.loads(memo_path.read_bytes())
                self.assertIn("controller_source_live_pending", durable,
                              name + " preceded the durable binding marker")
                raise AssertionError("binding stage invoked forbidden effect: " + name)
            return reject

        effect_names = (
            "_capture_controller_source_batch", "_publish_event_page_plan",
            "_publish_event_page_plan_batch", "_publish_event_page_batch_closure",
            "update_day_page", "_stage_live_generation",
            "_publish_staged_live_generation", "_commit_sense_cursors",
            "save_cursors", "_settle_source_refusals",
            "_settle_source_record_refusals", "_settle_source_entry_refusals",
            "_pulse_transaction_guarded", "_event_cognitive_transition",
            "load_thoughts", "save_mind", "brain_sync", "gbrain", "gbrain_call",
            "export_status", "export_graph",
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                self.lib, "atomic_write", side_effect=write))
            for name in effect_names:
                if hasattr(self.lib, name):
                    stack.enter_context(mock.patch.object(
                        self.lib, name, side_effect=forbidden(name)))
            if hasattr(self.lib, "siamind"):
                for name in ("load_mind", "save_mind"):
                    if hasattr(self.lib.siamind, name):
                        stack.enter_context(mock.patch.object(
                            self.lib.siamind, name,
                            side_effect=forbidden("siamind." + name)))
            yield writes

    def _stage(self, *, status=None, seq=None, permit_marker_write=True,
               memo=None):
        admitted = self.live.status if status is None else status
        sequence = admitted["pulse_seq"] if seq is None else seq
        selected_memo = self.live.memo if memo is None else memo
        before = self._images()
        with self._effect_boundary(
                permit_marker_write=permit_marker_write) as writes:
            result = self._stager()(
                memo=selected_memo, admitted_status=admitted, seq=sequence)
        self.assertEqual(self._images(), before)
        return result, writes

    def test_exact_api_writes_full_pinned_marker_before_every_later_effect(self):
        signature = inspect.signature(self._stager())
        self.assertEqual(tuple(signature.parameters),
                         ("memo", "admitted_status", "seq"))
        for parameter in signature.parameters.values():
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)

        retained, _generation = self._source()
        candidate = self.fixture._prepare_candidate()
        transition = self.loop.prepare_pulse(**candidate["prepare_inputs"])
        expected = self._expected(retained, candidate, transition)
        original_prepare = self.loop.prepare_pulse

        with mock.patch.object(
                self.loop, "prepare_pulse", wraps=original_prepare) as prepare:
            result, writes = self._stage()
        self.assertIsNone(result)
        self.assertTrue(prepare.called)
        self.assertTrue(all(call.kwargs == candidate["prepare_inputs"]
                            for call in prepare.call_args_list))
        self.assertEqual(writes, [expected])
        self.assertEqual(self.live.memo["controller_source_live_pending"], expected)
        self.assertEqual(self.live._read("MEMO_PATH")["controller_source_live_pending"],
                         expected)
        self.assertEqual(set(expected), MARKER_KEYS)
        self.assertRegex(expected["publication_id"], r"^[0-9a-f]{32}$")
        self.assertRegex(expected["publication_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(expected["publication_id"],
                         expected["publication_sha256"][:32])
        self.assertEqual(expected["publication_sha256"], live_tests.digest(
            self._publication_basis(expected)))
        self.assertEqual(expected["marker_sha256"], live_tests.digest({
            key: value for key, value in expected.items()
            if key != "marker_sha256"}))
        self.assertEqual(expected["source_pending_receipt"],
                         self.live.memo["controller_source_pending"])
        self.assertEqual(expected["event_closure_sha256"],
                         retained["event_closure"]["closure_sha256"])
        self.assertNotIn("ready", self.live.memo)

    def test_exact_retry_is_write_free_and_changed_seq_status_or_source_refuses(self):
        retained, _generation = self._source()
        candidate = self.fixture._prepare_candidate()
        transition = self.loop.prepare_pulse(**candidate["prepare_inputs"])
        expected = self._expected(retained, candidate, transition)
        self.assertIsNone(self._stage()[0])
        durable_before = Path(self.live.paths["MEMO_PATH"]).read_bytes()
        generation_before = Path(self.live.paths["MEMO_PATH"]).stat()

        result, writes = self._stage(permit_marker_write=False)
        self.assertIsNone(result)
        self.assertEqual(writes, [])
        generation_after = Path(self.live.paths["MEMO_PATH"]).stat()
        self.assertEqual((generation_after.st_dev, generation_after.st_ino),
                         (generation_before.st_dev, generation_before.st_ino))
        self.assertEqual(Path(self.live.paths["MEMO_PATH"]).read_bytes(), durable_before)
        self.assertEqual(self.live.memo["controller_source_live_pending"], expected)

        later_seq = publication_tests.pulse_tests.FROZEN_EFFECTLESS_STATUS["pulse_seq"]
        changed_status = copy.deepcopy(self.live.status)
        changed_status["publication_id"] = "d" * 32
        changed_source = copy.deepcopy(self.live.memo)
        changed_source["controller_source_pending"]["batch_sha256"] = "0" * 64
        cases = (
            ("seq", {"seq": later_seq}),
            ("status", {"status": changed_status}),
            ("source", {"memo": changed_source}),
        )
        for label, changes in cases:
            with self.subTest(label=label), self.assertRaises((RuntimeError, ValueError)):
                self._stage(permit_marker_write=False, **changes)
            self.assertEqual(Path(self.live.paths["MEMO_PATH"]).read_bytes(), durable_before)
            self.assertEqual(self.live.memo["controller_source_live_pending"], expected)

    def test_validated_parent_hashes_are_bound_and_changed_parent_refuses(self):
        retained, generation = self._source(parent=True)
        candidate = self.fixture._prepare_candidate(parent=True)
        transition = self.loop.prepare_pulse(**candidate["prepare_inputs"])
        expected = self._expected(
            retained, candidate, transition, generation=generation)
        self.assertIsNone(self._stage()[0])
        marker = self.live.memo["controller_source_live_pending"]
        self.assertEqual(marker, expected)
        self.assertEqual(marker["parent_generation_sha256"],
                         generation["generation_sha256"])
        self.assertEqual(marker["parent_state_sha256"], generation["state_sha256"])
        durable_before = Path(self.live.paths["MEMO_PATH"]).read_bytes()

        changed_parent = copy.deepcopy(self.live.memo)
        changed_parent["live_loop_committed"]["generation_sha256"] = "0" * 64
        with self.assertRaises((RuntimeError, ValueError)):
            self._stage(memo=changed_parent, permit_marker_write=False)
        self.assertEqual(Path(self.live.paths["MEMO_PATH"]).read_bytes(), durable_before)
        self.assertEqual(self.live.memo["controller_source_live_pending"], expected)

    def test_successful_empty_source_binds_absent_closure_as_explicit_null(self):
        retained, _generation = self._source(empty=True)
        candidate = self.fixture._prepare_candidate()
        transition = self.loop.prepare_pulse(**candidate["prepare_inputs"])
        expected = self._expected(retained, candidate, transition)
        self.assertIsNone(self._stage()[0])
        self.assertIsNone(expected["event_closure_sha256"])
        marker = self.live.memo["controller_source_live_pending"]
        self.assertEqual(marker, expected)
        self.assertIsNone(marker["event_closure_sha256"])

    def test_whole_memo_capacity_refuses_before_first_marker_write(self):
        self._source()
        memo_path = Path(self.live.paths["MEMO_PATH"])
        before = memo_path.read_bytes()
        before_images = self._images()
        with mock.patch.object(self.lib, "MAX_MEMO_BYTES", len(before)), \
                self.assertRaises((RuntimeError, ValueError)):
            self._stage(permit_marker_write=False)
        self.assertEqual(memo_path.read_bytes(), before)
        self.assertEqual(self._images(), before_images)
        self.assertNotIn("controller_source_live_pending", self.live.memo)


if __name__ == "__main__":
    unittest.main()
