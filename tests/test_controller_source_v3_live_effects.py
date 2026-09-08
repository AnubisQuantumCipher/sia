"""Genuine source-v3 WAL dispatch and the existing content-effects lane.

Positive cases actually acknowledge a legacy source parent, prepare its empty
delivery epoch, reserve a successor, and capture v3 under the real front door.
The same outer corpus lease covers that capture and fixed-slot retention.
No source schema is relabeled and no v3 acknowledgment or output is invented.

Candidate dispatch uses the real pending-source and committed-live readers.
Page publication, live binding, status handoff and live publication are real
fixture operations. The existing effects observer supplies controlled Git and
index witnesses: those prove local validation/order only, not the external
programs, embedding quality, machine-history truth or a held-out cognitive win.
Effects completion below deliberately stops before successor source ACK.
"""

import base64
import contextlib
import copy
import importlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import test_controller_source_capture_v3 as capture_tests
from tests import test_controller_source_effects as effects_tests
from tests import test_controller_source_idle as idle_tests
from tests import test_controller_source_live_transaction as producer_tests


REFUSALS = (ValueError, RuntimeError, OSError)


class ControllerSourceV3LiveEffects(unittest.TestCase):
    def setUp(self):
        self.capture_fixture = capture_tests.ControllerSourceCaptureV3(methodName="runTest")
        self.addCleanup(self.capture_fixture.doCleanups)
        self.capture_fixture.setUp()
        self.source = self.capture_fixture.source
        self.live = self.capture_fixture.live
        self.publication = importlib.import_module("siasourcepublication")
        self.effects_module = importlib.import_module("siasourceeffects")
        self.adapter = importlib.import_module("siacontrollerliveinput")
        self.assertTrue(callable(getattr(self.adapter, "prepare_inputs_v3", None)))

    @staticmethod
    def forbidden(name):
        return mock.Mock(side_effect=AssertionError("source-v3 repeated forbidden work: " + name))

    @contextlib.contextmanager
    def pending(self, *, nonidle=False):
        fixture = self.capture_fixture
        with fixture.prepared(nonidle=nonidle) as original:
            # Do not use a manually staged copy or release the caller's
            # corpus lease between actual capture and the fixed WAL.
            with fixture.capture_owner(original) as owner:
                with fixture.no_effects(original, owner):
                    batch = fixture.operation(owner.__dict__, **original.request)
                self.assertEqual(batch["schema"], "sia-controller-source-batch-v3")
                self.assertEqual(batch["delivery_input"]["epoch_view"]["parent_generation"],
                                 original.generation)
                sequence = original.case.live.memo["pulse_seq"]
                self.assertIsNone(self.publication.retain_successor(
                    owner.__dict__, memo=original.case.live.memo,
                    retained_batch=original.retained, committed=original.committed,
                    batch=batch, expected_batch_sha256=batch["batch_sha256"], seq=sequence))
                self.assertIs(self.publication.recover_successor(
                    owner.__dict__, memo=original.case.live.memo,
                    retained_batch=original.retained, committed=original.committed,
                    seq=sequence), True)
            fields = dict(vars(original))
            fields.update(batch=batch, seq=sequence, status=original.case.admitted_status())
            f = SimpleNamespace(**fields)
            self.assertEqual(Path(f.case.producer.source_path).read_bytes(),
                             self.source.native_bytes(f.case.lib.__dict__, batch))
            self.assertEqual(f.case.live.memo["controller_source_pending"]["batch_sha256"],
                             batch["batch_sha256"])
            self.assertNotIn("controller_source_committed", f.case.live.memo)
            self.assertEqual(batch["delivery_input"]["epoch_view"]["parent_committed"], f.committed)
            self.assertNotIn("ready", f.case.live.memo)
            yield f

    @contextlib.contextmanager
    def no_recapture(self, f):
        blocked = self.forbidden("capture, delivery acquisition or legacy input adaptation")
        with contextlib.ExitStack() as stack:
            for module, name in (
                    (self.source, "capture"), (self.source, "capture_successor"),
                    (self.source, "capture_successor_v3"), (self.source, "_collect"),
                    (self.capture_fixture.idle, "capture"),
                    (self.capture_fixture.epoch.idle.bench, "capture_native_history_v2"),
                    (self.capture_fixture.epoch_module, "prepare_epoch"),
                    (self.capture_fixture.epoch_module, "hold_epoch"),
                    (self.capture_fixture.epoch_module, "hold_capturable_epoch"),
                    (self.capture_fixture.journal, "hold_deliveries"),
                    (self.capture_fixture.journal, "inspect_deliveries"),
                    (self.capture_fixture.journal, "reserve_delivery"),
                    (self.capture_fixture.journal, "deliver_reserved"),
                    (self.adapter, "prepare_inputs")):
                stack.enter_context(mock.patch.object(module, name, blocked))
            yield
        blocked.assert_not_called()

    def bind_status(self, f):
        case = f.case
        with self.no_recapture(f):
            self.assertIsNone(case.lib._stage_controller_source_live_binding(
                memo=case.live.memo, admitted_status=f.status, seq=f.seq))
            candidate = case.lib._prepare_controller_source_live_candidate(
                memo=case.live.memo, admitted_status=f.status)
            transition = self.live.prepare_pulse(**candidate["prepare_inputs"])
            binding = copy.deepcopy(case.live.memo["controller_source_live_pending"])
            self.assertIsNone(case.lib._stage_controller_source_status_effects(
                memo=case.live.memo, admitted_status=f.status,
                batch=f.batch, expected_batch_sha256=f.batch["batch_sha256"],
                source_live_pending=binding, candidate=candidate, transition=transition,
                expected_transition_sha256=transition["transition_sha256"],
                started_at=f.status["ts"]))
        fixture = case.effects
        fixture.admitted_status = copy.deepcopy(f.status)
        fixture.batch, fixture.candidate = copy.deepcopy(f.batch), copy.deepcopy(candidate)
        fixture.transition, fixture.binding = copy.deepcopy(transition), copy.deepcopy(binding)
        fixture.handoff = copy.deepcopy(case.live.memo["pulse_status_effects_pending"])
        fixture.memo_before = copy.deepcopy(case.live.memo)
        fixture.corpus_generation = fixture._corpus_generation()
        plan = getattr(case.lib, idle_tests.GIST_PREPARER)(
            transition=transition, expected_transition_sha256=transition["transition_sha256"])
        rows = fixture._manifest(f.batch["event_closure"])
        rows.extend({
            **row, "page_state": "live", "parse_error_codes": [],
            "expected_projection_sha256": "4" * 64,
            "current_projection_sha256": "4" * 64,
            "current_content_hash": "4" * 64,
            "current_content_hash_match": True, "projection_match": True,
        } for row in plan["target_versions"])
        self.assertEqual(len({row["slug"] for row in rows}), len(rows))
        fixture.target_manifest = sorted(rows, key=lambda row: row["slug"])
        fixture.sync_generation = fixture._sync_generation(fixture.target_manifest)
        f.candidate, f.transition, f.binding, f.gist_plan = candidate, transition, binding, plan

    @contextlib.contextmanager
    def content_effects(self, f, *, crash=False, recovery=False):
        """Reuse the real-effects observer, extending only its content seams."""
        fixture = f.case.effects
        prepare = getattr(fixture.lib, idle_tests.GIST_PREPARER)
        publish = getattr(fixture.lib, idle_tests.GIST_PUBLISHER)
        original_status = fixture._new_status
        plans, publications = [], []

        def prepare_gist(**kwargs):
            plan = prepare(**kwargs)
            plans.append(copy.deepcopy(plan))
            return plan

        def publish_gist(*, plan, expected_plan_sha256):
            if recovery:
                raise AssertionError("v3 recovery repeated gist publication")
            self.assertEqual(plan, f.gist_plan)
            self.assertEqual(expected_plan_sha256, f.gist_plan["plan_sha256"])
            receipt = publish(plan=plan, expected_plan_sha256=expected_plan_sha256)
            publications.append(copy.deepcopy(receipt))
            if f.batch["event_closure"] is None:
                self.assertEqual(observed["trace"], [])
                observed["trace"].append("closure")
            else:
                self.assertEqual(observed["trace"], ["closure"])
            return receipt

        def commit_content(*, source_batch_sha256, content_publication_sha256):
            if recovery:
                raise AssertionError("v3 recovery repeated content commit")
            self.assertEqual(observed["trace"], ["closure"])
            self.assertEqual(source_batch_sha256, f.batch["batch_sha256"])
            closure = f.batch["event_closure"]
            self.assertEqual(content_publication_sha256, self.live._sha({
                "schema": "sia-controller-source-content-publication-v1",
                "event_closure_sha256": None if closure is None else closure["closure_sha256"],
                "closure_result_sha256": None if closure is None
                    else self.live._sha(observed["closure_results"][0]),
                "gist_publication_sha256": publications[0]["publication_sha256"],
            }))
            observed["trace"].append("corpus")
            return copy.deepcopy(fixture.corpus_generation)

        def successor_status(graph):
            # The old observer's initial-pulse fixture kept one sequence.
            # This real successor has a separately reserved sequence: retain
            # the original expected status and copy that observed binding.
            expected = original_status(graph)
            expected["pulse_seq"] = f.binding["seq"]
            return expected

        fixture.lib._load_live_publication()
        with mock.patch.object(effects_tests, "PENDING_KEYS",
                set(effects_tests.PENDING_KEYS) | idle_tests.V2_EFFECT_FIELDS), \
                mock.patch.object(fixture, "_new_status", side_effect=successor_status), \
                fixture.publication_effects(
                    null=False, crash_at="effects-pending" if crash else None,
                    recovery=recovery,
                    predecessor_live=fixture.memo_before["live_loop_committed"]) as observed, \
                contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                fixture.lib, idle_tests.GIST_PREPARER, side_effect=prepare_gist))
            stack.enter_context(mock.patch.object(
                fixture.lib, idle_tests.GIST_PUBLISHER, side_effect=publish_gist))
            content_commit = stack.enter_context(mock.patch.object(
                fixture.lib, idle_tests.GIST_COMMITTER, side_effect=commit_content))
            stack.enter_context(mock.patch.object(
                fixture.lib, effects_tests.COMMITTER,
                self.forbidden("legacy closure-only commit for source v3")))
            yield {**observed, "gist_plans": plans, "gist_receipts": publications,
                   "content_committed": content_commit}

    def content_images(self, f):
        versions = f.case.effects._target_versions()
        return {row["slug"]: effects_tests._path_image(f.case.lib.corpus_path(row["slug"]))
                for row in versions}

    def assert_receipt(self, f):
        fixture, memo = f.case.effects, f.case.live.memo
        self.assertEqual(f.case.live._read("MEMO_PATH"), memo)
        receipt = memo["controller_source_effects_committed"]
        self.assertEqual(set(receipt), effects_tests.RECEIPT_KEYS | idle_tests.V2_EFFECT_FIELDS)
        self.assertEqual(receipt["schema"], "sia-controller-source-effects-committed-v2")
        self.assertEqual(receipt["receipt_sha256"], self.live._own(receipt, "receipt_sha256"))
        self.assertEqual(receipt["source_batch_sha256"], f.batch["batch_sha256"])
        self.assertEqual(receipt["prepare_inputs_sha256"], f.candidate["expected_prepare_inputs_sha256"])
        self.assertEqual(receipt["state_sha256"], f.transition["state_sha256"])
        self.assertEqual(receipt["transition_sha256"], f.transition["transition_sha256"])
        self.assertEqual(receipt["non_claims"], list(self.effects_module.NON_CLAIMS))
        self.assertEqual(receipt["gist_page_plan_sha256"], f.gist_plan["plan_sha256"])
        self.assertEqual(receipt["gist_pages_sha256"], f.gist_plan["gist_pages_sha256"])
        self.assertEqual(receipt["gist_publication"]["target_versions"], f.gist_plan["target_versions"])
        self.assertEqual(receipt["content_publication_sha256"], self.live._sha({
            "schema": "sia-controller-source-content-publication-v1",
            "event_closure_sha256": receipt["event_closure_sha256"],
            "closure_result_sha256": receipt["closure_result_sha256"],
            "gist_publication_sha256": receipt["gist_publication"]["publication_sha256"],
        }))
        self.assertEqual(receipt["target_manifest"], fixture.target_manifest)
        self.assertIsNotNone(receipt["corpus_generation"])
        self.assertIsNotNone(receipt["sync_generation"])
        self.assertEqual(receipt["live_generation"]["generation_sha256"],
                         f.case.live._read("LIVE_STATE_PATH")["generation_sha256"])
        self.assertNotIn("controller_source_committed", memo)
        self.assertEqual(f.batch["delivery_input"]["epoch_view"]["parent_committed"], f.committed)
        self.assertIn("controller_source_pending", memo)
        self.assertIn("controller_source_live_pending", memo)
        self.assertNotIn("controller_source_effects_pending", memo)
        self.assertNotIn("pulse_status_effects_pending", memo)
        self.assertNotIn("ready", memo)
        self.assertFalse(f.case.archive_path(f.batch).exists(), "effects silently acknowledged source v3")
        self.assertEqual(Path(f.case.producer.source_path).read_bytes(),
                         self.source.native_bytes(f.case.lib.__dict__, f.batch))
        return receipt

    def test_real_sialib_candidate_dispatches_full_read_parent_to_v3_adapter(self):
        with self.pending(nonidle=True) as f:
            before = self.capture_fixture.images(f)
            original_batch = copy.deepcopy(f.batch)
            reader = f.case.lib._read_committed_live_generation
            adapter = self.adapter.prepare_inputs_v3
            reads, calls = [], []

            def read_parent(**kwargs):
                result = reader(**kwargs)
                self.assertEqual(result["status"], "available")
                self.assertEqual(result["generation"], f.generation)
                reads.append(copy.deepcopy(result["generation"]))
                return result

            def adapt(owner, **kwargs):
                self.assertTrue(reads, "core adapted an unobserved parent")
                self.assertIs(owner, f.case.lib.__dict__)
                self.assertEqual(set(kwargs), {
                    "batch", "previous_generation", "expected_previous_generation_sha256"})
                self.assertEqual(kwargs["batch"]["schema"], "sia-controller-source-batch-v3")
                self.assertEqual(kwargs["batch"], original_batch)
                self.assertEqual(kwargs["previous_generation"], reads[-1])
                self.assertEqual(kwargs["expected_previous_generation_sha256"],
                                 reads[-1]["generation_sha256"])
                result = adapter(owner, **kwargs)
                calls.append(copy.deepcopy(kwargs))
                return result

            with self.no_recapture(f), mock.patch.object(
                    f.case.lib, "_read_committed_live_generation", side_effect=read_parent), \
                    mock.patch.object(self.adapter, "prepare_inputs_v3", side_effect=adapt):
                candidate = f.case.producer._prepare_candidate(parent=True, admitted_status=f.status)
            self.assertTrue(calls)
            self.assertEqual(set(candidate), producer_tests.RESULT_KEYS)
            inputs = candidate["prepare_inputs"]
            self.assertEqual(set(inputs), producer_tests.PREPARE_KEYS)
            self.assertEqual(candidate["expected_prepare_inputs_sha256"], self.live._sha(inputs))
            self.assertEqual(inputs["previous_state"], f.generation["transition"]["state"])
            self.assertEqual(inputs["expected_previous_state_sha256"], f.generation["state_sha256"])
            self.assertEqual(inputs["deliveries"], f.batch["delivery_input"]["binding"]["deliveries"])
            self.assertEqual(self.capture_fixture.images(f), before)
            self.assertEqual(f.batch, original_batch)

            # Actual retained authority disappears; do not substitute the
            # wrapper's still-present copy of that generation as authority.
            path = Path(f.case.live.paths["LIVE_STATE_PATH"])
            held = path.with_name("live-generation-controlled-absence.json")
            path.rename(held)
            try:
                absent = self.capture_fixture.images(f)
                adapter_called = self.forbidden("adapter before missing actual parent refusal")
                with self.no_recapture(f), mock.patch.object(
                        self.adapter, "prepare_inputs_v3", adapter_called), self.assertRaises(REFUSALS):
                    f.case.producer._prepare_candidate(parent=True, admitted_status=f.status)
                adapter_called.assert_not_called()
                self.assertEqual(self.capture_fixture.images(f), absent)
            finally:
                held.rename(path)

    def test_v3_event_content_uses_shared_receipt_lane_and_exact_page_bytes(self):
        with self.pending(nonidle=True) as f:
            old_archive = f.case.archive_path(f.retained).read_bytes()
            epoch_images = self.capture_fixture.epoch.paths(f.retained, f.root)
            old_adoption = effects_tests._path_image(epoch_images[-2])
            self.bind_status(f)
            self.assertIsNotNone(f.batch["event_closure"])
            self.assertEqual(f.transition["gist_pages"], [])
            self.assertEqual(f.gist_plan["target_versions"], [])
            with self.no_recapture(f), self.content_effects(f) as observed:
                self.assertIsNone(f.case.effects.publisher()(memo=f.case.live.memo, admitted_status=f.status))
            self.assertEqual(observed["trace"], [
                "closure", "corpus", "sync", "graph", "pending", "live-stage", "live-publish", "receipt"])
            observed["published"].assert_called_once()
            observed["content_committed"].assert_called_once()
            observed["committed"].assert_not_called()
            self.assertTrue(observed["gist_receipts"], "v3 dropped the explicit empty gist disposition")
            receipt = self.assert_receipt(f)
            self.assertEqual(receipt["status"], "closure-index-status-live-committed")
            self.assertEqual(receipt["event_closure_sha256"], f.batch["event_closure"]["closure_sha256"])
            self.assertEqual(receipt["closure_result_sha256"], self.live._sha(observed["closure_results"][0]))
            for group in f.batch["event_closure"]["batches"]:
                for plan in group["members"]:
                    for page in plan["pages"]:
                        actual = Path(f.case.lib.corpus_path(page["slug"])).read_bytes()
                        self.assertEqual(actual, base64.b64decode(page["raw_utf8_base64"], validate=True))
            self.assertEqual(f.case.archive_path(f.retained).read_bytes(), old_archive)
            self.assertEqual(effects_tests._path_image(epoch_images[-2]), old_adoption)

    def test_v3_idle_gist_pending_recovers_without_recapture_or_duplicate_content(self):
        with self.pending() as f:
            old_archive = f.case.archive_path(f.retained).read_bytes()
            original_batch = copy.deepcopy(f.batch)
            self.bind_status(f)
            self.assertIsNone(f.batch["event_closure"])
            self.assertTrue(f.transition["gist_pages"])
            self.assertTrue(all(page["origin"] == "derived" for page in f.transition["gist_pages"]))
            with self.no_recapture(f), self.content_effects(f, crash=True) as first, \
                    self.assertRaisesRegex(RuntimeError, "injected source-effects crash: effects-pending"):
                f.case.effects.publisher()(memo=f.case.live.memo, admitted_status=f.status)
            self.assertEqual(first["trace"], ["closure", "corpus", "sync", "graph", "pending"])
            first["published"].assert_not_called()
            first["content_committed"].assert_called_once()
            pending = copy.deepcopy(f.case.live._read("MEMO_PATH")["controller_source_effects_pending"])
            self.assertEqual(pending["schema"], "sia-controller-source-effects-pending-v2")
            self.assertEqual(pending["gist_page_plan_sha256"], f.gist_plan["plan_sha256"])
            self.assertEqual(pending["gist_pages_sha256"], f.gist_plan["gist_pages_sha256"])
            images = self.content_images(f)
            self.assertTrue(all(value is not None for value in images.values()))
            for page in f.gist_plan["pages"]:
                self.assertEqual(Path(f.case.lib.corpus_path(page["proposal"]["subject"])).read_bytes(),
                                 base64.b64decode(page["raw_utf8_base64"], validate=True))
            f.case.effects.expected_status = copy.deepcopy(pending["status"])
            with self.no_recapture(f), self.content_effects(f, recovery=True) as recovery:
                self.assertIsNone(f.case.effects.publisher()(memo=f.case.live.memo, admitted_status=f.status))
            self.assertEqual(recovery["trace"], ["live-stage", "live-publish", "receipt"])
            recovery["content_committed"].assert_not_called()
            self.assertEqual(recovery["gist_receipts"], [])
            receipt = self.assert_receipt(f)
            self.assertEqual(receipt["status"], "gist-index-status-live-committed-no-closure")
            for name in idle_tests.V2_EFFECT_FIELDS:
                self.assertEqual(receipt[name], pending[name])
            self.assertEqual(self.content_images(f), images)
            self.assertEqual(f.batch, original_batch)
            self.assertEqual(f.case.archive_path(f.retained).read_bytes(), old_archive)
            before = self.capture_fixture.images(f)
            with self.no_recapture(f), f.case.effects.no_effect_boundary(), contextlib.ExitStack() as stack:
                for name in (idle_tests.GIST_PREPARER, idle_tests.GIST_PUBLISHER, idle_tests.GIST_COMMITTER):
                    stack.enter_context(mock.patch.object(f.case.lib, name, self.forbidden("completed " + name)))
                self.assertIsNone(f.case.effects.publisher()(
                    memo=f.case.live.memo, admitted_status=f.case.admitted_status()))
            self.assertEqual(self.capture_fixture.images(f), before)


if __name__ == "__main__":
    unittest.main()
