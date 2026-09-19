"""Recurring controller-source idle replay and durable gist -- RED contract.

The v1 source-batch and live-input contracts remain exact and non-idle.  A
successor batch is additive v2: it carries one closed ``idle_input`` wrapper
only when every declared collector completed with zero events.  That wrapper
is captured once from the selected supported native chains through
``siabench.capture_native_history_v2`` and becomes part of the fixed-slot WAL.

The live loop may turn that pinned wrapper into gist proposals only on an idle
pulse.  Proposals are not consolidation: source effects must publish their
derived corpus pages, commit and index that corpus generation even when the
event closure is null, and retain the exact publication receipt across crash
recovery.  Original episode records remain immutable throughout.

These tests establish local source/history binding, deterministic replay and
durable publication ordering.  They do not establish complete machine
history, source truth, output delivery, biological sleep, or a held-out
retrieval win.  Root runs this module sequentially under the mission cap.
"""

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import contextlib
import base64
import copy
import hashlib
import importlib
import inspect
import os
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_capture as capture_tests
from tests import test_controller_source_effects as effects_tests
from tests import test_controller_source_rollover_storage as rollover_tests
from tests import test_live_gist_binding as gist_binding_tests
from tests import test_live_loop as live_tests
from tests import test_pulse_sync as pulse_tests


V2_BATCH_KEYS = set(capture_tests.BATCH_KEYS) | {"idle_input"}
IDLE_INPUT_KEYS = {
    "episode_bindings", "expected_episode_bindings_sha256",
    "gist_inputs", "expected_gist_inputs_sha256",
}
GIST_PREPARER = "_prepare_controller_source_gist_page_plan"
GIST_PUBLISHER = "_publish_controller_source_gist_page_plan"
GIST_COMMITTER = "_controller_source_corpus_commit_generation_v2"
GIST_PLAN_KEYS = {
    "schema", "status", "transition_sha256", "gist_pages_sha256",
    "pages", "target_versions", "non_claims", "plan_sha256",
}
GIST_PAGE_PLAN_KEYS = {
    "proposal", "raw_utf8_base64", "raw_bytes", "raw_sha256",
    "target_version",
}
GIST_RECEIPT_KEYS = {
    "schema", "status", "plan_sha256", "gist_pages_sha256",
    "target_versions", "non_claims", "publication_sha256",
}
V2_EFFECT_FIELDS = {
    "gist_page_plan_sha256", "gist_pages_sha256",
    "gist_publication", "content_publication_sha256",
}
REFUSALS = (ValueError, RuntimeError, OSError)


def _path_image(path):
    path = Path(path)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
        path.read_bytes(),
    )


class _Adopted(RuntimeError):
    """Stopped seam after the exact fixed successor has been adopted."""


class ControllerSourceIdle(unittest.TestCase):
    def setUp(self):
        self.source_batch = importlib.import_module("siasourcebatch")
        self.source_publication = importlib.import_module(
            "siasourcepublication")
        self.epoch = importlib.import_module("siacontrollerepoch")
        self.live_input = importlib.import_module("siacontrollerliveinput")
        self.live = importlib.import_module("sialiveloop")
        self.bench = importlib.import_module("siabench")

    @staticmethod
    def _align_live_policy(case):
        case.source.policy = copy.deepcopy(
            importlib.import_module("siacontrollerepoch").LIVE_POLICY)
        case.source.profile["live_policy_sha256"] = \
            capture_tests.digest(case.source.policy)
        case.source.epoch.update(
            profile=case.source.profile,
            live_policy=case.source.policy)
        case.source.reseal_epoch()

    @contextlib.contextmanager
    def completed(self):
        """Yield one real nonempty completed predecessor and its archives."""
        case = ack_tests.ControllerSourceAcknowledgment(
            methodName="runTest")
        try:
            case.setUp()
            self._align_live_policy(case)
            case.start_nonempty()
            self.assertIsNone(case.acknowledge())
            durable = case.assert_final()
            retained = copy.deepcopy(case.batch)
            committed = copy.deepcopy(
                durable["controller_source_committed"])
            status = copy.deepcopy(case.admitted_status())
            generation = copy.deepcopy(case.generation)
            self.assertEqual(
                case.archive_path().read_bytes(),
                capture_tests.canonical(retained))
            yield case, retained, committed, status, generation
        finally:
            case.doCleanups()

    @contextlib.contextmanager
    def source_owner(self, case):
        owner = case.source.lib
        history = importlib.import_module("siacognitivehistory")
        with mock.patch.object(
                owner, "MEMO_PATH", case.live.paths["MEMO_PATH"]), \
                mock.patch.object(
                    owner, "CONTROLLER_SOURCE_BATCH_PATH",
                    str(case.producer.source_path)), \
                mock.patch.object(self.bench, "sialib", owner), \
                mock.patch.object(history, "sialib", owner):
            yield owner

    def reserve(self, case):
        case.live.memo["pulse_seq"] = rollover_tests.SUCCESSOR_SEQUENCE
        case.live._write(case.live.paths["MEMO_PATH"], case.live.memo)
        self.assertEqual(case.live._read("MEMO_PATH"), case.live.memo)

    def successor_request(self, case, retained, committed):
        return self.epoch.build_successor(
            case.source.lib.__dict__, retained_batch=retained,
            committed=committed,
            observed_at=rollover_tests.SUCCESSOR_OBSERVED_AT)

    def capture_successor(
            self, case, retained, committed, *, history=None):
        request = self.successor_request(case, retained, committed)
        with self.source_owner(case), case.source.capture_boundary(), \
                contextlib.ExitStack() as stack:
            if history is not None:
                stack.enter_context(mock.patch.object(
                    self.bench, "capture_native_history_v2", history))
            batch = self.source_batch.capture_successor(
                case.source.lib.__dict__, memo=case.live.memo,
                retained_batch=retained, committed=committed, **request)
        return request, batch

    def assert_v2(self, case, batch, *, idle):
        self.assertEqual(set(batch), V2_BATCH_KEYS)
        self.assertEqual(batch["schema"],
                         "sia-controller-source-batch-v2")
        self.source_batch.validate_batch(
            case.source.lib.__dict__, batch, batch["batch_sha256"])
        self.assertEqual(
            all(not run["events"]
                for run in batch["source_returns"]["runs"]), idle)
        if idle:
            self.assertEqual(set(batch["idle_input"]), IDLE_INPUT_KEYS)
            for field in (
                    "expected_episode_bindings_sha256",
                    "expected_gist_inputs_sha256"):
                self.assertRegex(batch["idle_input"][field],
                                 r"^[0-9a-f]{64}$")
        else:
            self.assertIsNone(batch["idle_input"])

    def adopt_and_bind(self, case, retained, committed, batch):
        with self.source_owner(case):
            self.assertIsNone(self.source_publication.retain_successor(
                case.lib.__dict__, memo=case.live.memo,
                retained_batch=retained, committed=committed,
                batch=batch,
                expected_batch_sha256=batch["batch_sha256"],
                seq=rollover_tests.SUCCESSOR_SEQUENCE))
            self.assertIs(self.source_publication.recover_successor(
                case.lib.__dict__, memo=case.live.memo,
                retained_batch=retained, committed=committed,
                seq=rollover_tests.SUCCESSOR_SEQUENCE), True)

        status = case.admitted_status()
        self.assertIsNone(case.lib._stage_controller_source_live_binding(
            memo=case.live.memo, admitted_status=status,
            seq=rollover_tests.SUCCESSOR_SEQUENCE))
        candidate = case.lib._prepare_controller_source_live_candidate(
            memo=case.live.memo, admitted_status=status)
        transition = self.live.prepare_pulse(
            **candidate["prepare_inputs"])
        marker = copy.deepcopy(
            case.live.memo["controller_source_live_pending"])
        self.assertIsNone(case.lib._stage_controller_source_status_effects(
            memo=case.live.memo, admitted_status=status,
            batch=batch, expected_batch_sha256=batch["batch_sha256"],
            source_live_pending=marker, candidate=candidate,
            transition=transition,
            expected_transition_sha256=transition["transition_sha256"],
            started_at=status["ts"]))
        return status, candidate, transition, marker

    @staticmethod
    def _forbidden(name):
        return mock.Mock(side_effect=AssertionError(
            "idle transaction repeated forbidden operation: " + name))

    def test_v1_batch_maps_strictly_to_nonidle_without_native_capture(self):
        fixture = capture_tests.ControllerSourceCapture(
            methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.policy = copy.deepcopy(self.epoch.LIVE_POLICY)
        fixture.profile["live_policy_sha256"] = \
            capture_tests.digest(fixture.policy)
        fixture.epoch.update(
            profile=fixture.profile, live_policy=fixture.policy)
        fixture.reseal_epoch()
        batch = fixture.capture()
        fixture.assert_batch(batch)
        self.assertEqual(batch["schema"],
                         "sia-controller-source-batch-v1")

        history = self._forbidden("native-history")
        binder = self._forbidden("live-gist-binding")
        with mock.patch.object(
                self.bench, "capture_native_history_v2", history), \
                mock.patch("sialivegist.bind_replay_gist", binder):
            prepared = self.live_input.prepare_inputs(
                batch=batch, previous_state=None,
                expected_previous_state_sha256=None)
            transition = self.live.prepare_pulse(**prepared)

        self.assertIs(prepared["idle"], False)
        self.assertIsNone(prepared["gist_inputs"])
        self.assertEqual(transition["state"]["idle"], {
            "requested": False, "gist": None})
        self.assertEqual(transition["gist_pages"], [])
        history.assert_not_called()
        binder.assert_not_called()

    def test_v2_idle_requires_every_run_empty_and_only_native_frontdoor(self):
        with self.completed() as (
                case, retained, committed, _status, _generation):
            self.reserve(case)
            real_history = self.bench.capture_native_history_v2
            with mock.patch.object(
                    self.bench, "capture_native_history_v2",
                    wraps=real_history) as captured, \
                    mock.patch.object(
                        self.bench, "build_ledger_dataset",
                        self._forbidden("benchmark-dataset")):
                _request, batch = self.capture_successor(
                    case, retained, committed)

            self.assert_v2(case, batch, idle=True)
            captured.assert_called_once()
            supplied = captured.call_args.kwargs
            self.assertEqual(set(supplied), {
                "corpus", "chain_registry", "chain_names"})
            self.assertEqual(supplied["corpus"], case.lib.CORPUS)
            self.assertEqual(supplied["chain_names"], ["aegis"])
            self.assertEqual(
                supplied["chain_registry"]["aegis"],
                case.source.lib._chain_cmds()["aegis"])

        with self.completed() as (
                case, retained, committed, _status, _generation):
            alpha = Path(case.source.custom_entries[0]["path"])
            alpha.write_text(
                alpha.read_text(encoding="utf-8")
                + "successor non-idle observation\n",
                encoding="utf-8")
            self.reserve(case)
            history = self._forbidden("native-history-on-nonidle")
            _request, batch = self.capture_successor(
                case, retained, committed, history=history)
            self.assert_v2(case, batch, idle=False)
            self.assertTrue(any(
                run["events"]
                for run in batch["source_returns"]["runs"]))
            history.assert_not_called()

    def test_idle_input_validates_prepares_and_binds_gist_immutably(self):
        with self.completed() as (
                case, retained, committed, _status, generation):
            self.reserve(case)
            _request, batch = self.capture_successor(
                case, retained, committed)
            self.assert_v2(case, batch, idle=True)
            original_batch = copy.deepcopy(batch)
            original_parent = copy.deepcopy(
                generation["transition"]["state"])

            prepared = self.live_input.prepare_inputs(
                batch=batch, previous_state=original_parent,
                expected_previous_state_sha256=
                    generation["state_sha256"])
            self.assertIs(prepared["idle"], True)
            self.assertEqual(prepared["gist_inputs"],
                             batch["idle_input"])
            self.assertIsNot(prepared["gist_inputs"],
                             batch["idle_input"])
            first = self.live.prepare_pulse(**prepared)
            repeated = self.live.prepare_pulse(**prepared)
            self.assertEqual(first, repeated)
            self.assertEqual(first["state"]["idle"]["requested"], True)
            self.assertEqual(
                first["state"]["idle"]["binding"]["episode_bindings"],
                batch["idle_input"]["episode_bindings"])
            self.assertTrue(first["gist_pages"])
            self.assertTrue(all(
                page["origin"] == "derived"
                for page in first["gist_pages"]))

            outside_idle = copy.deepcopy(prepared)
            outside_idle["idle"] = False
            with self.assertRaises(self.live.LiveLoopRefusal):
                self.live.prepare_pulse(**outside_idle)

            changed = copy.deepcopy(prepared)
            episodes = changed["gist_inputs"][
                "episode_bindings"]["episodes"]
            self.assertTrue(episodes)
            episodes[0]["event_record"]["summary"] += " changed"
            with self.assertRaises(self.live.LiveLoopRefusal):
                self.live.prepare_pulse(**changed)

            detached = copy.deepcopy(first)
            detached["state"]["idle"]["binding"][
                "episode_bindings"]["episodes"][0][
                    "event_record"]["summary"] += " detached"
            self.assertEqual(batch, original_batch)
            self.assertEqual(generation["transition"]["state"],
                             original_parent)

            corrupted = copy.deepcopy(batch)
            corrupted["idle_input"]["episode_bindings"][
                "episodes"][0]["event_record"]["summary"] += " corrupt"
            with self.assertRaises(self.source_batch.SourceBatchRefusal):
                self.source_batch.validate_batch(
                    case.source.lib.__dict__, corrupted,
                    corrupted["batch_sha256"])
            self.assertEqual(batch, original_batch)

    def test_fixed_wal_retry_never_recaptures_native_history_or_clock(self):
        with self.completed() as (
                case, retained, committed, _status, _generation):
            operation = self._forbidden("initial-operation")
            clock = mock.Mock(
                return_value=rollover_tests.SUCCESSOR_OBSERVED_AT)
            real_history = self.bench.capture_native_history_v2
            boundary = mock.Mock(side_effect=KeyboardInterrupt(
                "cut after fixed idle successor"))
            real_build = self.epoch.build_successor
            real_capture = self.source_batch.capture_successor

            def build(owner, *, retained_batch, committed, observed_at):
                self.assertIs(owner, case.lib.__dict__)
                self.assertEqual(retained_batch, retained)
                self.assertEqual(committed, case.live.memo[
                    "controller_source_committed"])
                self.assertEqual(observed_at,
                                 rollover_tests.SUCCESSOR_OBSERVED_AT)
                return real_build(
                    case.source.lib.__dict__, retained_batch=retained_batch,
                    committed=committed, observed_at=observed_at)

            def capture(**request):
                self.assertEqual(request["retained_batch"], retained)
                self.assertEqual(request["committed"], committed)
                self.assertEqual(request["memo"],
                                 case.live._read("MEMO_PATH"))
                with case.source.capture_boundary():
                    return real_capture(case.source.lib.__dict__, **request)

            with self.source_owner(case), \
                    mock.patch.object(
                        self.epoch, "build_successor", side_effect=build), \
                    mock.patch.object(
                        case.lib,
                        "_capture_controller_source_successor_batch",
                        side_effect=capture), \
                    mock.patch.object(
                        self.bench, "capture_native_history_v2",
                        wraps=real_history) as captured, \
                    mock.patch.object(
                        case.lib, "_controller_source_rollover_boundary",
                        boundary):
                with self.assertRaises(KeyboardInterrupt):
                    case.lib._run_controller_source_transaction_v2(
                        operation=operation, clock=clock)

            clock.assert_called_once_with()
            captured.assert_called_once()
            operation.assert_not_called()
            fixed_raw = Path(case.producer.source_path).read_bytes()
            completed = case.live._read("MEMO_PATH")
            self.assertIn("controller_source_committed", completed)
            self.assertNotIn("controller_source_pending", completed)
            self.assertEqual(completed["pulse_seq"],
                             pulse_tests.FROZEN_EFFECTLESS_STATUS["pulse_seq"])

            def stop_after_adoption(*, memo, admitted_status, seq):
                self.assertEqual(seq, completed["pulse_seq"])
                self.assertEqual(memo, case.live._read("MEMO_PATH"))
                self.assertIn("controller_source_pending", memo)
                self.assertNotIn("controller_source_committed", memo)
                self.assertEqual(
                    Path(case.producer.source_path).read_bytes(), fixed_raw)
                raise _Adopted("successor adopted")

            no_clock = self._forbidden("clock")
            no_history = self._forbidden("native-history")
            no_build = self._forbidden("successor-build")
            no_capture = self._forbidden("successor-capture")
            with self.source_owner(case), \
                    mock.patch.object(
                        self.bench, "capture_native_history_v2", no_history), \
                    mock.patch.object(
                        self.epoch, "build_successor", no_build), \
                    mock.patch.object(
                        case.lib,
                        "_capture_controller_source_successor_batch",
                        no_capture), \
                    mock.patch.object(
                        case.lib,
                        "_stage_controller_source_live_binding",
                        side_effect=stop_after_adoption), \
                    self.assertRaises(_Adopted):
                case.lib._run_controller_source_transaction_v2(
                    operation=operation, clock=no_clock)

            for forbidden in (no_clock, no_history, no_build, no_capture):
                forbidden.assert_not_called()
            operation.assert_not_called()
            self.assertEqual(
                Path(case.producer.source_path).read_bytes(), fixed_raw)

    def test_gist_page_publisher_crash_retry_is_exact_and_immutable(self):
        fixture = gist_binding_tests.LiveGistBinding(
            methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        request = fixture.request(("1",))
        transition = fixture.pulse(
            request, wrapper=fixture.wrapper(request))
        self.assertTrue(transition["gist_pages"])
        original = copy.deepcopy(transition)

        component = importlib.import_module("siasourcegist")
        preparer = getattr(component, "prepare", None)
        publisher = getattr(component, "publish", None)
        self.assertTrue(callable(preparer),
                        "missing pure source gist page planner")
        self.assertTrue(callable(publisher),
                        "missing durable source gist page publisher")
        contracts = (
            (preparer, ("owner", "transition",
                        "expected_transition_sha256")),
            (publisher, ("owner", "plan", "expected_plan_sha256")),
        )
        for operation, names in contracts:
            parameters = inspect.signature(operation).parameters
            self.assertEqual(tuple(parameters), names)
            self.assertEqual(
                parameters["owner"].kind,
                inspect.Parameter.POSITIONAL_OR_KEYWORD)
            for name in names[1:]:
                self.assertEqual(parameters[name].kind,
                                 inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(parameters[name].default,
                              inspect.Parameter.empty)

        plan = preparer(
            fixture.lib.__dict__, transition=transition,
            expected_transition_sha256=transition["transition_sha256"])
        self.assertEqual(set(plan), GIST_PLAN_KEYS)
        self.assertEqual(plan["schema"],
                         "sia-controller-source-gist-page-plan-v1")
        self.assertEqual(plan["status"], "prepared-not-published")
        self.assertEqual(plan["transition_sha256"],
                         transition["transition_sha256"])
        self.assertEqual(plan["gist_pages_sha256"],
                         live_tests.digest(transition["gist_pages"]))
        self.assertEqual(plan["plan_sha256"], live_tests.digest({
            key: value for key, value in plan.items()
            if key != "plan_sha256"}))
        self.assertEqual(
            [row["proposal"] for row in plan["pages"]],
            transition["gist_pages"])
        self.assertEqual(
            plan["target_versions"],
            [{"slug": row["target_version"]["subject"],
              "source_sha256": row["target_version"]["source_sha256"],
              "version_sha256": row["target_version"]["version_sha256"]}
             for row in plan["pages"]])
        for row in plan["pages"]:
            self.assertEqual(set(row), GIST_PAGE_PLAN_KEYS)
            raw = base64.b64decode(
                row["raw_utf8_base64"], validate=True)
            self.assertEqual(row["raw_bytes"], len(raw))
            self.assertEqual(row["raw_sha256"],
                             hashlib.sha256(raw).hexdigest())
            self.assertEqual(row["target_version"],
                fixture.lib._corpus_page_version_from_bytes(
                    slug=row["proposal"]["subject"], raw=raw))
            self.assertEqual(row["target_version"]["origin"],
                             "derived")
            self.assertIn(row["proposal"]["content"],
                          row["target_version"]["content"])

        target = Path(fixture.lib.corpus_path(
            plan["target_versions"][0]["slug"]))
        real_publish = fixture.lib.siaqueue.fixed_atomic_publish
        cut = []

        def publish_then_crash(path, data, **kwargs):
            result = real_publish(path, data, **kwargs)
            if Path(path) == target and not cut:
                cut.append(True)
                raise KeyboardInterrupt(
                    "cut after exact gist page publication")
            return result

        with mock.patch.object(
                fixture.lib.siaqueue, "fixed_atomic_publish",
                side_effect=publish_then_crash), \
                self.assertRaises(KeyboardInterrupt):
            publisher(
                fixture.lib.__dict__, plan=plan,
                expected_plan_sha256=plan["plan_sha256"])
        self.assertEqual(cut, [True])
        self.assertTrue(target.is_file())
        partial = _path_image(target)

        receipt = publisher(
            fixture.lib.__dict__, plan=plan,
            expected_plan_sha256=plan["plan_sha256"])
        self.assertEqual(set(receipt), GIST_RECEIPT_KEYS)
        self.assertEqual(receipt["schema"],
                         "sia-controller-source-gist-publication-v1")
        self.assertEqual(receipt["status"], "gist-pages-published")
        self.assertEqual(receipt["plan_sha256"], plan["plan_sha256"])
        self.assertEqual(receipt["gist_pages_sha256"],
                         live_tests.digest(transition["gist_pages"]))
        self.assertEqual(receipt["publication_sha256"],
                         live_tests.digest({
                             key: value for key, value in receipt.items()
                             if key != "publication_sha256"}))
        self.assertEqual(receipt["non_claims"],
                         list(component.NON_CLAIMS))
        self.assertEqual(receipt["target_versions"],
                         plan["target_versions"])
        planned_pages = {
            row["target_version"]["subject"]: row["target_version"]
            for row in plan["pages"]}
        for published in receipt["target_versions"]:
            self.assertEqual(
                fixture.lib._capture_corpus_page_version(
                    published["slug"]),
                planned_pages[published["slug"]])
            self.assertEqual(
                planned_pages[published["slug"]]["origin"], "derived")
        complete = {page["slug"]: _path_image(
            fixture.lib.corpus_path(page["slug"]))
            for page in plan["target_versions"]}
        self.assertEqual(_path_image(target), partial)
        self.assertEqual(publisher(
            fixture.lib.__dict__, plan=plan,
            expected_plan_sha256=plan["plan_sha256"]),
            receipt)
        self.assertEqual({page["slug"]: _path_image(
            fixture.lib.corpus_path(page["slug"]))
            for page in plan["target_versions"]}, complete)

        changed = copy.deepcopy(plan)
        changed["pages"][0]["proposal"]["content"] += " mutation"
        with self.assertRaises(REFUSALS):
            publisher(
                fixture.lib.__dict__, plan=changed,
                expected_plan_sha256=plan["plan_sha256"])
        self.assertEqual(transition, original)
        self.assertEqual({page["slug"]: _path_image(
            fixture.lib.corpus_path(page["slug"]))
            for page in plan["target_versions"]}, complete)

    @contextlib.contextmanager
    def gist_effects(self, case, *, crash=False, recovery=False):
        """Extend the established effects observer only at the new seams."""
        fixture = case.effects
        real_prepare = getattr(fixture.lib, GIST_PREPARER, None)
        real_publish = getattr(fixture.lib, GIST_PUBLISHER, None)
        self.assertTrue(callable(real_prepare),
                        "missing source-effects gist planning front door")
        self.assertTrue(callable(real_publish),
                        "missing source-effects gist publication front door")
        plans, publications = [], []

        def prepare(*, transition, expected_transition_sha256):
            plan = real_prepare(
                transition=transition,
                expected_transition_sha256=expected_transition_sha256)
            plans.append(copy.deepcopy(plan))
            return plan

        def publish(*, plan, expected_plan_sha256):
            if recovery:
                raise AssertionError("recovery repeated gist publication")
            self.assertEqual(plan, plans[-1])
            self.assertEqual(expected_plan_sha256, plan["plan_sha256"])
            receipt = real_publish(
                plan=plan, expected_plan_sha256=expected_plan_sha256)
            publications.append(copy.deepcopy(receipt))
            observed["trace"].append("closure")
            return receipt

        def commit(*, source_batch_sha256,
                   content_publication_sha256):
            if recovery:
                raise AssertionError("recovery repeated corpus commit")
            self.assertEqual(observed["trace"], ["closure"])
            self.assertEqual(source_batch_sha256,
                             fixture.batch["batch_sha256"])
            identity = {
                "schema": "sia-controller-source-content-publication-v1",
                "event_closure_sha256": None,
                "closure_result_sha256": None,
                "gist_publication_sha256":
                    publications[0]["publication_sha256"],
            }
            self.assertEqual(content_publication_sha256,
                             live_tests.digest(identity))
            observed["trace"].append("corpus")
            return copy.deepcopy(fixture.corpus_generation)

        original_pending_keys = effects_tests.PENDING_KEYS
        fixture.lib._load_live_publication()
        with mock.patch.object(
                effects_tests, "PENDING_KEYS",
                set(original_pending_keys) | V2_EFFECT_FIELDS), \
                fixture.publication_effects(
                    null=False,
                    crash_at="effects-pending" if crash else None,
                    recovery=recovery,
                    predecessor_live=fixture.memo_before[
                        "live_loop_committed"]) as observed, \
                contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                fixture.lib, GIST_PREPARER, side_effect=prepare))
            stack.enter_context(mock.patch.object(
                fixture.lib, GIST_PUBLISHER, side_effect=publish))
            stack.enter_context(mock.patch.object(
                fixture.lib, GIST_COMMITTER,
                side_effect=commit, create=True))
            stack.enter_context(mock.patch.object(
                fixture.lib,
                "_controller_source_corpus_commit_generation",
                self._forbidden("legacy closure-only corpus commit")))
            yield {
                **observed, "gist_plans": plans,
                "gist_receipts": publications,
            }

    def test_source_effects_commit_null_closure_gist_and_recover_once(self):
        with self.completed() as (
                case, retained, committed, _status, _generation):
            predecessor_archive = case.archive_path().read_bytes()
            self.reserve(case)
            _request, batch = self.capture_successor(
                case, retained, committed)
            self.assert_v2(case, batch, idle=True)
            status, candidate, transition, marker = \
                self.adopt_and_bind(case, retained, committed, batch)
            self.assertIsNone(batch["event_closure"])
            self.assertTrue(transition["gist_pages"])
            original_batch = copy.deepcopy(batch)
            original_episodes = copy.deepcopy(
                batch["idle_input"]["episode_bindings"]["episodes"])

            fixture = case.effects
            fixture.admitted_status = status
            fixture.batch = copy.deepcopy(batch)
            fixture.candidate = copy.deepcopy(candidate)
            fixture.transition = copy.deepcopy(transition)
            fixture.binding = copy.deepcopy(marker)
            fixture.handoff = copy.deepcopy(
                case.live.memo["pulse_status_effects_pending"])
            fixture.memo_before = copy.deepcopy(case.live.memo)
            fixture.corpus_generation = fixture._corpus_generation()
            expected_plan = case.lib.__dict__[GIST_PREPARER](
                transition=transition,
                expected_transition_sha256=
                    transition["transition_sha256"])
            fixture.target_manifest = [{
                **row, "page_state": "live", "parse_error_codes": [],
                "expected_projection_sha256": "4" * 64,
                "current_projection_sha256": "4" * 64,
                "current_content_hash": "4" * 64,
                "current_content_hash_match": True,
                "projection_match": True,
            } for row in expected_plan["target_versions"]]
            fixture.sync_generation = fixture._sync_generation(
                fixture.target_manifest)

            history = self._forbidden("native-history-during-effects")
            with mock.patch.object(
                    self.bench, "capture_native_history_v2", history), \
                    self.gist_effects(case, crash=True) as first, \
                    self.assertRaisesRegex(
                        RuntimeError,
                        "injected source-effects crash: effects-pending"):
                fixture.publisher()(
                    memo=case.live.memo, admitted_status=status)
            history.assert_not_called()
            self.assertEqual(first["trace"], [
                "closure", "corpus", "sync", "graph", "pending"])
            first["published"].assert_not_called()
            first["committed"].assert_not_called()
            self.assertTrue(first["gist_plans"])
            self.assertTrue(all(
                plan == expected_plan for plan in first["gist_plans"]))
            self.assertEqual(len(first["gist_receipts"]), 1)
            pending = copy.deepcopy(case.live._read(
                "MEMO_PATH")["controller_source_effects_pending"])
            self.assertEqual(
                pending["gist_page_plan_sha256"],
                expected_plan["plan_sha256"])
            self.assertEqual(
                pending["gist_pages_sha256"],
                expected_plan["gist_pages_sha256"])
            self.assertEqual(
                pending["content_publication_sha256"],
                live_tests.digest({
                    "schema":
                        "sia-controller-source-content-publication-v1",
                    "event_closure_sha256": None,
                    "closure_result_sha256": None,
                    "gist_publication_sha256": pending[
                        "gist_publication"]["publication_sha256"],
                }))
            gist_images = {
                page["subject"]: _path_image(
                    case.lib.corpus_path(page["subject"]))
                for page in transition["gist_pages"]
            }
            self.assertTrue(all(
                image is not None for image in gist_images.values()))

            # Recovery consumes only the durable pending receipt.  Supplying
            # its retained gist receipt to the observer is not recapture.
            fixture.expected_status = copy.deepcopy(pending["status"])
            with mock.patch.object(
                    self.bench, "capture_native_history_v2",
                    self._forbidden("native-history-on-recovery")), \
                    mock.patch.object(
                        fixture.lib, GIST_PUBLISHER,
                        self._forbidden("gist-publication-on-recovery")), \
                    self.gist_effects(case, recovery=True) as recovered:
                # The recovery validator obtains the receipt from its pending
                # value; seed only the test observer's comparison roster.
                recovered["gist_receipts"].append(copy.deepcopy(
                    pending["gist_publication"]))
                self.assertIsNone(fixture.publisher()(
                    memo=case.live.memo, admitted_status=status))

            self.assertEqual(recovered["trace"], [
                "live-stage", "live-publish", "receipt"])
            receipt = case.live.memo[
                "controller_source_effects_committed"]
            self.assertEqual(receipt["schema"],
                             "sia-controller-source-effects-committed-v2")
            self.assertEqual(
                receipt["status"],
                "gist-index-status-live-committed-no-closure")
            self.assertEqual(receipt["gist_publication"],
                             pending["gist_publication"])
            self.assertEqual(
                receipt["gist_page_plan_sha256"],
                pending["gist_page_plan_sha256"])
            self.assertEqual(
                receipt["gist_pages_sha256"],
                pending["gist_pages_sha256"])
            self.assertIsNone(receipt["event_closure_sha256"])
            self.assertIsNotNone(receipt["corpus_generation"])
            self.assertIsNotNone(receipt["sync_generation"])
            self.assertEqual(
                {row["slug"] for row in receipt["target_manifest"]},
                {page["subject"] for page in transition["gist_pages"]})
            self.assertEqual({
                page["subject"]: _path_image(
                    case.lib.corpus_path(page["subject"]))
                for page in transition["gist_pages"]}, gist_images)
            self.assertEqual(case.archive_path(retained).read_bytes(),
                             predecessor_archive)
            self.assertEqual(fixture.batch, original_batch)
            self.assertEqual(
                fixture.batch["idle_input"][
                    "episode_bindings"]["episodes"],
                original_episodes)

            before = {
                "memo": _path_image(case.live.paths["MEMO_PATH"]),
                "source": _path_image(case.producer.source_path),
                "pages": gist_images,
            }
            with contextlib.ExitStack() as stack:
                for name in (
                        GIST_PREPARER, GIST_PUBLISHER, GIST_COMMITTER,
                        "_controller_source_corpus_commit_generation",
                        "_controller_source_sync_generation",
                        "_publish_event_page_batch_closure",
                        "export_graph", "_stage_live_generation",
                        "_publish_staged_live_generation", "atomic_write",
                        "_controller_source_effects_observed_at"):
                    stack.enter_context(mock.patch.object(
                        fixture.lib, name,
                        self._forbidden("completed retry " + name),
                        create=True))
                self.assertIsNone(fixture.publisher()(
                    memo=case.live.memo,
                    admitted_status=case.admitted_status()))
            self.assertEqual(_path_image(
                case.live.paths["MEMO_PATH"]), before["memo"])
            self.assertEqual(_path_image(
                case.producer.source_path), before["source"])
            self.assertEqual({
                page["subject"]: _path_image(
                    case.lib.corpus_path(page["subject"]))
                for page in transition["gist_pages"]}, before["pages"])


if __name__ == "__main__":
    unittest.main()
