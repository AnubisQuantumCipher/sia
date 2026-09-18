"""Read-only, source-authorized live-loop inspection -- RED contract.

The composed ACK fixture supplies a real retained source batch, archived
effects receipt and matching live/status/graph generation.  Inspection must
revalidate that authority under the corpus owner while the resident lease is
unavailable.  Bare compatibility status or a self-consistent legacy live
generation cannot authorize this view.

The view reports retained component observations and selection reasons.  It
does not recompute metrics, certify cognition, assert consumer delivery or
turn gist proposals into publication receipts.  Root alone runs this module
sequentially under the mission memory cap.
"""

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import contextlib
import copy
import importlib
import inspect
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_capture as capture_tests


VIEW_KEYS = {
    "schema", "status", "origin", "as_of", "publication", "workspace",
    "encoding", "admission", "activation", "coretrieval", "idle",
    "non_claims", "upstream_non_claims", "view_sha256",
}
PUBLICATION_KEYS = {
    "publication_id", "pulse_seq", "status_timestamp", "epoch_id",
    "state_sha256", "transition_sha256", "generation_sha256",
    "source_batch_sha256", "source_effects_receipt_sha256", "policy_sha256",
}


class SourceAuthorizedLiveView(unittest.TestCase):
    def module(self):
        path = Path(__file__).resolve().parent.parent / "bin/sialiveview.py"
        self.assertTrue(path.is_file(), "missing source-authorized live view")
        module = importlib.import_module("sialiveview")
        self.assertTrue(callable(getattr(module, "read_view", None)))
        self.assertTrue(hasattr(module, "LiveViewRefusal"))
        return module

    @contextlib.contextmanager
    def completed(self, *, empty=False):
        case = ack_tests.ControllerSourceAcknowledgment(methodName="runTest")
        try:
            case.setUp()
            # Frozen fixture policy makes selection observable. These are
            # declared test inputs, not tuned parameters or numeric evidence.
            case.source.policy["novelty_admission"]["threshold"] = 0
            case.source.policy["workspace"]["ignition_threshold"] = -100
            case.source.profile["live_policy_sha256"] = \
                capture_tests.digest(case.source.policy)
            case.source.epoch.update(
                profile=case.source.profile, live_policy=case.source.policy)
            case.source.reseal_epoch()
            case.start_empty() if empty else case.start_nonempty()
            self.assertIsNone(case.acknowledge())
            case.assert_final()
            yield case
        finally:
            case.doCleanups()

    @contextlib.contextmanager
    def read_only(self, case):
        def forbidden(*_args, **_kwargs):
            raise AssertionError("inspection entered a writer or resident lease")

        with case.forbid_ack_effects(), contextlib.ExitStack() as stack:
            for name in (
                    "brainstem_owner", "_write_memo", "_capture_controller_source_batch",
                    "_prepare_controller_source_live_candidate",
                    "_acknowledge_controller_source_batch"):
                stack.enter_context(mock.patch.object(
                    case.lib, name, side_effect=forbidden))
            yield

    def images(self, case):
        return {
            "transaction": case.images(),
            "effects": ack_tests._path_image(case.effects_archive_path()),
        }

    def assert_refused_without_write(self, module, case):
        before = self.images(case)
        with self.read_only(case), self.assertRaises(module.LiveViewRefusal) as raised:
            module.read_view(case.lib.__dict__)
        self.assertEqual(raised.exception.status, "refused")
        self.assertRegex(raised.exception.reason, r"\A[a-z][a-z0-9-]*\Z")
        self.assertEqual(raised.exception.non_claims, list(module.NON_CLAIMS))
        self.assertEqual(self.images(case), before)

    def test_api_accepts_only_owner_and_has_closed_refusal(self):
        module = self.module()
        self.assertEqual(tuple(inspect.signature(module.read_view).parameters),
                         ("owner",))
        with self.assertRaises(module.LiveViewRefusal):
            module.read_view(None)

    def test_published_cache_is_identical_and_reads_without_corpus_owner(self):
        module = self.module()
        self.assertTrue(callable(getattr(module, "publish_cache", None)),
                        "missing source-authorized live-view cache publisher")
        self.assertTrue(callable(getattr(module, "read_cached_view", None)),
                        "missing nonblocking live-view cache reader")
        with self.completed() as case:
            expected = module.read_view(case.lib.__dict__)
            published = module.publish_cache(case.lib.__dict__)
            self.assertEqual(published, expected)
            with mock.patch.object(
                    case.lib, "corpus_owner", side_effect=AssertionError(
                        "cached live view reacquired the resident writer lease")):
                self.assertEqual(module.read_cached_view(case.lib.__dict__), expected)

    def test_cached_view_digest_corruption_refuses_without_source_fallback(self):
        module = self.module()
        with self.completed() as case:
            value = module.publish_cache(case.lib.__dict__)
            value["publication"]["pulse_seq"] += 1
            cache = Path(case.lib.STATE) / module.CACHE_BASENAME
            case.live._write(str(cache), value)
            with mock.patch.object(
                    module, "read_view", side_effect=AssertionError(
                        "invalid cache fell back to the source transaction")), \
                    self.assertRaises(module.LiveViewRefusal) as raised:
                module.read_cached_view(case.lib.__dict__)
            self.assertEqual(raised.exception.reason, "cached-view-digest")

    def test_failed_cache_replacement_preserves_prior_complete_view(self):
        module = self.module()
        with self.completed() as case:
            expected = module.publish_cache(case.lib.__dict__)
            cache = Path(case.lib.STATE) / module.CACHE_BASENAME
            before = ack_tests._path_image(cache)
            with mock.patch.object(
                    case.lib, "atomic_write", side_effect=OSError(
                        "fixture publication failure")), \
                    self.assertRaises(module.LiveViewRefusal) as raised:
                module.publish_cache(case.lib.__dict__)
            self.assertEqual(
                raised.exception.reason, "cached-view-publication-refusal")
            self.assertEqual(ack_tests._path_image(cache), before)
            self.assertEqual(module.read_cached_view(case.lib.__dict__), expected)

    def test_completed_view_rejoins_source_effects_live_status_without_resident_lease(self):
        module = self.module()
        with self.completed() as case:
            before = self.images(case)
            with self.read_only(case):
                result = module.read_view(case.lib.__dict__)
            self.assertEqual(self.images(case), before)
            self.assertEqual(set(result), VIEW_KEYS)
            self.assertEqual(result["schema"], "sia-controller-live-view-v1")
            self.assertEqual(result["status"], "available")
            self.assertEqual(result["origin"], "derived")
            state = case.generation["transition"]["state"]
            publication = result["publication"]
            self.assertEqual(set(publication), PUBLICATION_KEYS)
            for field in ("publication_id", "pulse_seq", "epoch_id",
                          "state_sha256", "transition_sha256", "generation_sha256"):
                self.assertEqual(publication[field], case.generation[field])
            self.assertEqual(publication["source_batch_sha256"],
                             case.batch["batch_sha256"])
            self.assertEqual(publication["source_effects_receipt_sha256"],
                             case.live.memo["controller_source_committed"][
                                 "source_effects_receipt_sha256"])
            self.assertEqual(publication["status_timestamp"],
                             case.admitted_status()["ts"])
            self.assertEqual(publication["policy_sha256"], state["policy_sha256"])
            self.assertEqual(result["as_of"], state["observed_at"])
            self.assertEqual(result["non_claims"], list(module.NON_CLAIMS))
            self.assertEqual(result["view_sha256"], capture_tests.digest({
                key: value for key, value in result.items() if key != "view_sha256"}))

    def test_workspace_explains_retained_selection_and_current_activation_separately(self):
        module = self.module()
        with self.completed() as case, self.read_only(case):
            result = module.read_view(case.lib.__dict__)
            state = case.generation["transition"]["state"]
            workspace = result["workspace"]
            held = state["held_selection_receipt"]
            self.assertTrue(state["workspace"]["slots"], "fixture must select a page")
            self.assertIsNotNone(held)
            for field in ("status", "transition", "release_reason", "slots",
                          "candidates", "payload_sha256"):
                self.assertEqual(workspace[field], state["workspace"][field])
            self.assertEqual(workspace["phase"], state["workspace"]["state"]["phase"])
            self.assertEqual(workspace["capacity"], state["policy"]["workspace"]["slots"])
            self.assertEqual(workspace["ignition_threshold"],
                             state["policy"]["workspace"]["ignition_threshold"])
            self.assertEqual(workspace["selection"]["observed_at"], held["observed_at"])
            self.assertEqual(workspace["selection"]["frame_sha256"], held["frame_sha256"])
            self.assertEqual(workspace["selection"]["activation"], held["activation"])
            self.assertEqual(workspace["selection"]["admission"], held["admission"])
            self.assertEqual(workspace["selection"]["payload_sha256"], held["payload_sha256"])
            self.assertEqual(result["activation"], state["activation"])
            self.assertEqual(workspace["expires_at"],
                             state["workspace"]["state"]["episode"]["expires_at"])

    def test_component_values_and_nonclaims_are_retained_observations(self):
        module = self.module()
        with self.completed() as case, self.read_only(case):
            result = module.read_view(case.lib.__dict__)
            state = case.generation["transition"]["state"]
            for field in ("encoding", "admission", "activation", "coretrieval"):
                self.assertEqual(result[field], state[field])
            self.assertEqual(result["upstream_non_claims"]["live_loop"], state["non_claims"])
            self.assertEqual(result["upstream_non_claims"]["live_publication"],
                             case.generation["non_claims"])
            self.assertEqual(result["upstream_non_claims"]["workspace"],
                             state["workspace"]["non_claims"])

    def test_nonidle_and_empty_workspace_do_not_imply_consolidation_or_missing_history(self):
        module = self.module()
        with self.completed(empty=True) as case, self.read_only(case):
            result = module.read_view(case.lib.__dict__)
            self.assertEqual(result["workspace"]["slots"], [])
            self.assertIsNone(result["workspace"]["selection"])
            self.assertFalse(result["idle"]["requested"])
            self.assertEqual(result["idle"]["gist_publication_status"], "not-requested")
            self.assertIsNone(result["idle"]["gist_publication"])
            self.assertEqual(result["idle"]["proposed_pages"], [])

    def test_view_contains_no_corpus_body_or_broadcast_payload(self):
        module = self.module()
        forbidden = {"content", "chunk_text", "payload_json", "artifact_json",
                     "raw_utf8_base64", "output_utf8_base64"}

        def inspect_value(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for child in value.values():
                    inspect_value(child)
            elif isinstance(value, list):
                for child in value:
                    inspect_value(child)

        with self.completed() as case, self.read_only(case):
            inspect_value(module.read_view(case.lib.__dict__))

    def test_view_is_detached_and_read_repeat_is_identical(self):
        module = self.module()
        with self.completed() as case, self.read_only(case):
            result = module.read_view(case.lib.__dict__)
            expected = copy.deepcopy(result)
            result["workspace"]["slots"].clear()
            result["encoding"]["events"].clear()
            result["non_claims"].append("mutated caller view")
            self.assertEqual(module.read_view(case.lib.__dict__), expected)

    def test_legacy_live_generation_cannot_stand_in_for_source_completion(self):
        module = self.module()
        with self.completed(empty=True) as case:
            case.live.memo.pop("controller_source_committed")
            case.live._write(case.live.paths["MEMO_PATH"], case.live.memo)
            self.assert_refused_without_write(module, case)

    def test_absent_source_completion_refuses_before_consuming_compatibility_status(self):
        module = self.module()
        with self.completed(empty=True) as case:
            case.live.memo.pop("controller_source_committed")
            case.live._write(case.live.paths["MEMO_PATH"], case.live.memo)
            with self.read_only(case), mock.patch.object(
                    case.lib, "read_state_json", side_effect=AssertionError(
                        "missing source completion must not consume compatibility STATUS")), \
                    self.assertRaises(module.LiveViewRefusal) as raised:
                module.read_view(case.lib.__dict__)
            self.assertEqual(raised.exception.reason, "source-completion-unavailable")

    def test_pending_source_or_live_authority_refuses(self):
        module = self.module()
        for field in ("controller_source_pending", "live_loop_pending"):
            with self.subTest(field=field), self.completed(empty=True) as case:
                case.live.memo[field] = {"deliberately": "malformed-pending-marker"}
                case.live._write(case.live.paths["MEMO_PATH"], case.live.memo)
                self.assert_refused_without_write(module, case)

    def test_missing_or_changed_retained_artifacts_refuse(self):
        module = self.module()
        for field in ("batch", "effects", "generation", "status"):
            with self.subTest(field=field), self.completed(empty=True) as case:
                path = {
                    "batch": case.archive_path(),
                    "effects": case.effects_archive_path(),
                    "generation": Path(case.live.paths["LIVE_STATE_PATH"]),
                    "status": Path(case.live.paths["STATUS_PATH"]),
                }[field]
                if field == "batch":
                    path.rename(path.with_suffix(".retained-test-copy"))
                else:
                    path.write_bytes(path.read_bytes() + b" ")
                self.assert_refused_without_write(module, case)

    def test_changed_authority_during_projection_refuses_without_repair(self):
        module = self.module()
        with self.completed(empty=True) as case:
            original = module._project

            def changed(*args, **kwargs):
                result = original(*args, **kwargs)
                path = case.archive_path()
                path.write_bytes(path.read_bytes() + b" ")
                return result

            with self.read_only(case), mock.patch.object(module, "_project", side_effect=changed), \
                    self.assertRaises(module.LiveViewRefusal):
                module.read_view(case.lib.__dict__)

    def test_output_capacity_refuses_whole_view(self):
        module = self.module()
        with self.completed() as case, mock.patch.object(module, "MAX_VIEW_BYTES", 1):
            self.assert_refused_without_write(module, case)
