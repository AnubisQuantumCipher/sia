"""Resealed source gist receipts must retain their actual live/content joins.

The fixture executes native capture, successor retention, gist publication
and live publication through their real local front doors. Git and index
generations remain the existing controlled observations. These tests exercise
byte/identity admission, not source truth or cognitive benefit.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import contextlib
import copy
import importlib
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_source_capture as capture_tests
from tests import test_controller_source_idle as idle_tests
from tests import test_live_loop as live_tests


REFUSALS = (ValueError, RuntimeError, OSError)


class ControllerSourceGistReceiptIntegrity(unittest.TestCase):
    def setUp(self):
        self.idle = idle_tests.ControllerSourceIdle(methodName="runTest")
        self.idle.setUp()
        self.addCleanup(self.idle.doCleanups)
        self.effects = importlib.import_module("siasourceeffects")
        self.gist = importlib.import_module("siasourcegist")

    @staticmethod
    def seal(value, field):
        value[field] = live_tests.digest({key: item for key, item in value.items() if key != field})

    @staticmethod
    def content_identity(value):
        return live_tests.digest({
            "schema": "sia-controller-source-content-publication-v1",
            "event_closure_sha256": value["event_closure_sha256"],
            "closure_result_sha256": value["closure_result_sha256"],
            "gist_publication_sha256": value["gist_publication"]["publication_sha256"],
        })

    def reseal_content(self, value):
        self.seal(value["gist_publication"], "publication_sha256")
        value["content_publication_sha256"] = self.content_identity(value)

    @contextlib.contextmanager
    def transaction(self, *, complete=False, acknowledge=False):
        with self.idle.completed() as (case, retained, committed, _status, _generation):
            self.idle.reserve(case)
            _request, batch = self.idle.capture_successor(case, retained, committed)
            status, candidate, transition, marker = self.idle.adopt_and_bind(
                case, retained, committed, batch)
            self.assertIsNone(batch["event_closure"])
            self.assertTrue(transition["gist_pages"])
            fixture = case.effects
            fixture.admitted_status = status
            fixture.batch = copy.deepcopy(batch)
            fixture.candidate = copy.deepcopy(candidate)
            fixture.transition = copy.deepcopy(transition)
            fixture.binding = copy.deepcopy(marker)
            fixture.handoff = copy.deepcopy(case.live.memo["pulse_status_effects_pending"])
            fixture.memo_before = copy.deepcopy(case.live.memo)
            fixture.corpus_generation = fixture._corpus_generation()
            expected_plan = case.lib.__dict__[idle_tests.GIST_PREPARER](
                transition=transition, expected_transition_sha256=transition["transition_sha256"])
            fixture.target_manifest = [{
                **row, "page_state": "live", "parse_error_codes": [],
                "expected_projection_sha256": "4" * 64,
                "current_projection_sha256": "4" * 64,
                "current_content_hash": "4" * 64,
                "current_content_hash_match": True, "projection_match": True,
            } for row in expected_plan["target_versions"]]
            fixture.sync_generation = fixture._sync_generation(fixture.target_manifest)
            with self.idle.gist_effects(case, crash=True), self.assertRaisesRegex(
                    RuntimeError, "injected source-effects crash: effects-pending"):
                fixture.publisher()(memo=case.live.memo, admitted_status=status)
            pending = copy.deepcopy(case.live._read("MEMO_PATH")["controller_source_effects_pending"])
            self.assertEqual(pending["gist_page_plan_sha256"], expected_plan["plan_sha256"])
            self.assertEqual(pending["gist_pages_sha256"], expected_plan["gist_pages_sha256"])
            if complete:
                fixture.expected_status = copy.deepcopy(pending["status"])
                with self.idle.gist_effects(case, recovery=True) as recovered:
                    recovered["gist_receipts"].append(copy.deepcopy(pending["gist_publication"]))
                    self.assertIsNone(fixture.publisher()(memo=case.live.memo, admitted_status=status))
                case._remember_committed(copy.deepcopy(batch), copy.deepcopy(fixture.committed_generation))
                receipt = copy.deepcopy(case.live.memo["controller_source_effects_committed"])
                self.assertEqual(receipt["gist_publication"], pending["gist_publication"])
                if acknowledge:
                    self.assertIsNone(case.acknowledge())
                    self.assertNotIn("controller_source_effects_committed", case.live.memo)
                    self.assertEqual(case.effects_archive_path(receipt).read_bytes(),
                                     capture_tests.canonical(receipt))
                yield case, batch, transition, pending, receipt
            else:
                yield case, batch, transition, pending, None

    @contextlib.contextmanager
    def forbid_effects(self, case):
        with contextlib.ExitStack() as stack:
            for name in (
                    idle_tests.GIST_PREPARER, idle_tests.GIST_PUBLISHER, idle_tests.GIST_COMMITTER,
                    "_controller_source_corpus_commit_generation", "_controller_source_sync_generation",
                    "_publish_event_page_batch_closure", "export_graph", "export_status",
                    "_stage_live_generation", "_publish_staged_live_generation", "atomic_write",
                    "_write_memo", "_controller_source_effects_observed_at", "save_cursors"):
                stack.enter_context(mock.patch.object(case.lib, name, side_effect=AssertionError(
                    "resealed receipt crossed effect boundary: " + name)))
            stack.enter_context(mock.patch.object(case.lib.siaqueue, "fixed_atomic_publish",
                                                 side_effect=AssertionError("receipt published bytes")))
            yield

    def images(self, case, transition):
        return {
            "transaction": case.images(),
            "gists": {page["subject"]: idle_tests._path_image(case.lib.corpus_path(page["subject"]))
                      for page in transition["gist_pages"]},
        }

    def mutation_roster(self, case, transition):
        def plan_pin(value):
            value["gist_page_plan_sha256"] = live_tests.digest("foreign-gist-plan")
            value["gist_publication"]["plan_sha256"] = value["gist_page_plan_sha256"]
            self.reseal_content(value)

        def gist_pin(value):
            value["gist_pages_sha256"] = live_tests.digest("foreign-gist-roster")
            value["gist_publication"]["gist_pages_sha256"] = value["gist_pages_sha256"]
            self.reseal_content(value)

        def absent_targets(value):
            value["gist_publication"]["target_versions"] = []
            value["target_manifest"] = []
            value["target_manifest_sha256"] = live_tests.digest([])
            value["corpus_generation"] = None
            value["sync_generation"] = None
            self.reseal_content(value)

        def origin_boundary(value):
            value["gist_publication"]["non_claims"] = []
            self.reseal_content(value)

        def false_publication(value):
            value["gist_publication"]["status"] = "prepared-not-published"
            self.reseal_content(value)

        def foreign_content(value):
            value["content_publication_sha256"] = live_tests.digest("foreign-content-publication")

        def omitted_manifest(value):
            value["target_manifest"] = []
            value["target_manifest_sha256"] = live_tests.digest([])

        def relabelled_target(value):
            value["target_manifest"][0]["source_sha256"] = live_tests.digest("foreign-page-bytes")
            value["target_manifest_sha256"] = live_tests.digest(value["target_manifest"])

        def foreign_transition(value):
            value["transition_sha256"] = live_tests.digest("foreign-live-transition")
            plan = self.gist.prepare_pages(
                case.lib.__dict__, gist_pages=transition["gist_pages"],
                expected_gist_pages_sha256=live_tests.digest(transition["gist_pages"]),
                transition_sha256=value["transition_sha256"])
            value["gist_page_plan_sha256"] = plan["plan_sha256"]
            value["gist_pages_sha256"] = plan["gist_pages_sha256"]
            value["gist_publication"] = self.gist.publication_receipt(
                case.lib.__dict__, plan=plan, expected_plan_sha256=plan["plan_sha256"])
            value["content_publication_sha256"] = self.content_identity(value)

        return (
            ("gist plan", plan_pin), ("gist roster", gist_pin),
            ("all targets suppressed", absent_targets), ("gist boundary", origin_boundary),
            ("publication status", false_publication), ("content identity", foreign_content),
            ("manifest omitted", omitted_manifest), ("manifest bytes", relabelled_target),
            ("foreign transition with internally matching gist plan", foreign_transition),
            ("foreign state", lambda value: value.update(state_sha256=live_tests.digest("foreign-live-state"))),
            ("foreign prepare inputs", lambda value: value.update(
                prepare_inputs_sha256=live_tests.digest("foreign-live-inputs"))),
        )

    def test_pending_reseals_refuse_before_recovery_or_content_effects(self):
        with self.transaction() as (case, _batch, transition, pending, _receipt):
            original_memo = copy.deepcopy(case.live.memo)
            for label, mutate in self.mutation_roster(case, transition):
                with self.subTest(mutation=label):
                    changed = copy.deepcopy(pending)
                    mutate(changed)
                    self.seal(changed, "pending_sha256")
                    case.live.memo.clear()
                    case.live.memo.update(copy.deepcopy(original_memo))
                    case.live.memo["controller_source_effects_pending"] = changed
                    case.live._write(case.live.paths["MEMO_PATH"], case.live.memo)
                    before = self.images(case, transition)
                    with self.forbid_effects(case), self.assertRaises(REFUSALS):
                        case.effects.publisher()(memo=case.live.memo, admitted_status=case.effects.admitted_status)
                    self.assertEqual(self.images(case, transition), before)

    def test_committed_reseals_refuse_before_any_completed_retry_effect(self):
        with self.transaction(complete=True) as (case, _batch, transition, _pending, receipt):
            original_memo = copy.deepcopy(case.live.memo)
            self.assertEqual(self.effects.committed_receipt(
                case.lib.__dict__, memo=case.live.memo, admitted_status=case.admitted_status()), receipt)
            for label, mutate in self.mutation_roster(case, transition):
                with self.subTest(mutation=label):
                    changed = copy.deepcopy(receipt)
                    mutate(changed)
                    self.seal(changed, "receipt_sha256")
                    case.live.memo.clear()
                    case.live.memo.update(copy.deepcopy(original_memo))
                    case.live.memo["controller_source_effects_committed"] = changed
                    case.live._write(case.live.paths["MEMO_PATH"], case.live.memo)
                    before = self.images(case, transition)
                    with self.forbid_effects(case), self.assertRaises(REFUSALS):
                        self.effects.committed_receipt(
                            case.lib.__dict__, memo=case.live.memo, admitted_status=case.admitted_status())
                    self.assertEqual(self.images(case, transition), before)

    def test_archived_reseals_must_join_the_actual_retained_live_generation(self):
        with self.transaction(complete=True, acknowledge=True) as (case, batch, transition, _pending, receipt):
            def validate(value):
                return self.effects.validate_archived_receipt(
                    case.lib.__dict__, raw=capture_tests.canonical(value), retained_batch=batch,
                    memo=case.live.memo, admitted_status=case.admitted_status(),
                    expected_receipt_sha256=value["receipt_sha256"])

            self.assertEqual(validate(receipt), receipt)
            before = self.images(case, transition)
            archive_before = idle_tests._path_image(case.effects_archive_path(receipt))
            for label, mutate in self.mutation_roster(case, transition):
                with self.subTest(mutation=label):
                    changed = copy.deepcopy(receipt)
                    mutate(changed)
                    self.seal(changed, "receipt_sha256")
                    with self.forbid_effects(case), self.assertRaises(REFUSALS):
                        validate(changed)
                    self.assertEqual(self.images(case, transition), before)
                    self.assertEqual(idle_tests._path_image(case.effects_archive_path(receipt)), archive_before)
