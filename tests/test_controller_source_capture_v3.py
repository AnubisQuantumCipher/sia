"""First genuine source-v3 capture over an actually acknowledged legacy parent.

Root alone executes this module sequentially. Real source ACK,
delivery-epoch preparation, recurring-runner reservation and source capture
provide the positive lane. No v2 batch is relabeled into a v3 success and no
future v3 acknowledgment, writer permit or delivery record is manufactured.

The notification fixture genuinely ACKs its selected notification collector.
Its safe baseline therefore normally does not need a new acquisition fence.
The fenced case performs the real marker operation before capture and runs
the real notification collector with that retained fence; it does not erase
acknowledged cursor state to force another first-baseline callback.

These checks concern local contracts and descriptor lifetimes, not complete
machine history, source truth, observed output, biological cognition, JACKAL
assurance or held-out retrieval improvement.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import contextlib
import copy
import functools
import importlib
import inspect
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import test_controller_delivery_epoch as epoch_tests
from tests import test_controller_delivery_epoch_hold as hold_tests
from tests import test_controller_delivery_wrapper as wrapper_tests
from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_capture as capture_tests


SCHEMA = "sia-controller-source-batch-v3"
BATCH_KEYS = set(capture_tests.BATCH_KEYS) | {"idle_input", "delivery_input"}
PARAMETERS = (
    "owner", "memo", "admitted_status", "retained_batch", "committed",
    "epoch", "expected_epoch_sha256", "observed_at", "journal_limits",
    "expected_journal_limits_sha256", "expected_adoption_sha256",
)
AUTHORITY_PATHS = (
    "MEMO_PATH", "STATUS_PATH", "GRAPH_PATH", "LIVE_CANDIDATE_PATH",
    "LIVE_STATE_PATH", "CONTROLLER_SOURCE_BATCH_PATH",
    "CONTROLLER_SOURCE_ARCHIVE_DIR", "CONTROLLER_SOURCE_EFFECTS_ARCHIVE_DIR",
    epoch_tests.ROOT_KEY,
)
REFUSALS = (ValueError, RuntimeError, OSError)


class _ReservedAtClock(BaseException):
    pass


class ControllerSourceCaptureV3(unittest.TestCase):
    def setUp(self):
        self.source = importlib.import_module("siasourcebatch")
        self.operation = getattr(self.source, "capture_successor_v3", None)
        self.assertTrue(callable(self.operation), "missing genuine source-v3 capture")
        self.epoch = epoch_tests.ControllerDeliveryEpoch(methodName="runTest")
        self.addCleanup(self.epoch.doCleanups)
        self.epoch.setUp()
        self.epoch_module = self.epoch.module
        self.runner = importlib.import_module("siacontrollersourcerunner")
        self.wrapper = importlib.import_module("siacontrollerdeliverywrapper")
        self.idle = importlib.import_module("siacontrolleridle")
        self.journal = importlib.import_module("siadelivery")
        self.live = importlib.import_module("sialiveloop")
        # Only its descriptor/closed-handle helper methods are used. Do not
        # import/subclass the fixture TestCase and rediscover its test suite.
        self.fd_fixture = hold_tests.ControllerDeliveryEpochHold(methodName="runTest")

    @contextlib.contextmanager
    def notify_completed(self):
        case = ack_tests.ControllerSourceAcknowledgment(methodName="runTest")
        try:
            case.setUp()
            self.epoch.idle._align_live_policy(case)
            notification_path = case.source.select_notifications()
            self.assertFalse(notification_path.exists())
            batch = case.source.capture()
            case.source.assert_batch(batch)
            self.assertIsNotNone(batch["notification_baseline_attempt"])
            case.commit_live(batch)
            self.assertIsNone(case.acknowledge())
            durable = case.assert_final()
            retained = copy.deepcopy(case.batch)
            committed = copy.deepcopy(durable["controller_source_committed"])
            status = copy.deepcopy(case.admitted_status())
            generation = copy.deepcopy(case.generation)
            root = case.live.root / "controller-delivery-epochs"
            with mock.patch.object(case.lib, epoch_tests.ROOT_KEY, str(root), create=True), \
                    mock.patch.object(case.lib, epoch_tests.BOUNDARY_KEY, mock.Mock(), create=True):
                yield case, retained, committed, status, generation, root
        finally:
            case.doCleanups()

    def reserve(self, case):
        original = copy.deepcopy(case.live.memo)
        writes = []
        write_memo = case.lib._write_memo

        def write(value):
            result = write_memo(value)
            writes.append(copy.deepcopy(value))
            return result

        def stop_after_reserved():
            self.assertTrue(writes)
            self.assertEqual(case.lib.load_memo(), writes[-1])
            raise _ReservedAtClock()

        forbidden = mock.Mock(side_effect=AssertionError(
            "reservation called the initial capture operation"))
        with mock.patch.object(case.lib, "_write_memo", side_effect=write), \
                self.assertRaises(_ReservedAtClock):
            self.runner.run_v2(case.lib.__dict__, operation=forbidden,
                               clock=stop_after_reserved)
        forbidden.assert_not_called()
        durable = case.lib.load_memo()
        self.assertGreater(durable["pulse_seq"], original["pulse_seq"])
        self.assertEqual(durable, {**original, "pulse_seq": durable["pulse_seq"]})
        case.live.memo.clear()
        case.live.memo.update(durable)

    @contextlib.contextmanager
    def prepared(self, *, notifications=False, fenced=False, nonidle=False):
        if notifications and nonidle:
            raise ValueError("this fixture does not synthesize notification output")
        completed = self.notify_completed if notifications else self.epoch.completed
        with completed() as (case, retained, committed, status, generation, root):
            adopted = self.epoch.prepare(case, retained, committed, status)
            self.reserve(case)
            marker = None
            if fenced:
                marker = copy.deepcopy(case.lib._mark_notify_baseline_attempt(case.live.memo))
            if nonidle:
                custom = Path(case.source.custom_entries[0]["path"])
                custom.write_bytes(custom.read_bytes() + b"new controlled successor line\n")
            request = self.epoch.idle.successor_request(case, retained, committed)
            request.update({
                "memo": case.live.memo, "admitted_status": status,
                "retained_batch": retained, "committed": committed,
                "journal_limits": copy.deepcopy(self.epoch.limits),
                "expected_journal_limits_sha256": self.live._sha(self.epoch.limits),
                "expected_adoption_sha256": adopted["expected_adoption_sha256"],
            })
            yield SimpleNamespace(case=case, retained=retained, committed=committed,
                status=status, generation=generation, root=root, adopted=adopted,
                marker=marker, request=request, notifications=notifications,
                nonidle=nonidle, owner=case.source.lib.__dict__)

    @contextlib.contextmanager
    def capture_owner(self, f):
        # Capture fixture source configuration and collectors belong to one
        # isolated sialib module; publication authority belongs to another.
        # Join their REAL paths, not snapshots returned by mocked readers.
        with self.epoch.idle.source_owner(f.case), contextlib.ExitStack() as stack:
            owner = f.case.source.lib
            for name in AUTHORITY_PATHS:
                stack.enter_context(mock.patch.object(
                    owner, name, getattr(f.case.lib, name),
                    create=name == epoch_tests.ROOT_KEY))
            with owner.brainstem_owner(), owner.corpus_owner():
                yield owner

    @contextlib.contextmanager
    def no_effects(self, f, owner):
        blocked = mock.Mock(side_effect=AssertionError(
            "source-v3 capture crossed publication/ACK/clock boundary"))
        actual_iso = owner.iso

        def retained_time(dt=None):
            if not isinstance(dt, owner.datetime.datetime):
                raise AssertionError("source-v3 sampled a new observation clock")
            return actual_iso(dt)

        with f.case.source.capture_boundary(), contextlib.ExitStack() as stack:
            # Ordinary owner infrastructure is already entered. These guards
            # concern acquisition effects, not setup or caller fixture writes.
            for module in (owner, f.case.lib):
                for name in (
                        "_write_memo", "atomic_write", "save_cursors",
                        "_commit_sense_cursors", "_discard_pending_cursor_renames",
                        "_settle_source_refusals", "_settle_source_record_refusals",
                        "_settle_source_entry_refusals", "_acknowledge_controller_source_batch",
                        "_stage_controller_source_batch", "_stage_live_generation",
                        "_publish_staged_live_generation", "export_status", "export_graph",
                        "_mark_notify_baseline_attempt", "_clear_notify_baseline_attempt",
                        "utcnow"):
                    stack.enter_context(mock.patch.object(module, name, blocked))
            stack.enter_context(mock.patch.object(owner, "iso", side_effect=retained_time))
            if f.nonidle:
                # The genuine custom collector stamps newly appended lines.
                # Supply its controlled, retained fixture timestamp only
                # during that collector call; v3 infrastructure still cannot
                # acquire a fresh clock. These are not live machine events.
                stamp = owner.datetime.datetime.fromisoformat(
                    f.status["ts"].replace("Z", "+00:00"))
                original_custom = owner.sense_custom
                collecting = []

                @functools.wraps(original_custom)
                def custom(*args, **kwargs):
                    collecting.append(True)
                    try:
                        return original_custom(*args, **kwargs)
                    finally:
                        collecting.pop()

                def collector_clock():
                    if not collecting:
                        raise AssertionError("v3 infrastructure sampled collector clock")
                    return stamp

                stack.enter_context(mock.patch.object(owner, "sense_custom", custom))
                stack.enter_context(mock.patch.object(owner, "SENSES", [
                    custom if sense is original_custom else sense for sense in owner.SENSES]))
                stack.enter_context(mock.patch.object(owner, "utcnow", side_effect=collector_clock))
            for module, name in (
                    (self.epoch_module, "prepare_epoch"),
                    (self.epoch.idle.epoch, "build_successor"),
                    (self.journal, "reserve_delivery"),
                    (self.journal, "deliver_reserved"),
                    (owner.siaqueue, "fixed_atomic_publish")):
                stack.enter_context(mock.patch.object(module, name, blocked))
            yield
        blocked.assert_not_called()

    def images(self, f):
        return (f.case.images(), epoch_tests._tree(f.root),
                ack_tests._path_image(f.case.effects_archive_path()),
                copy.deepcopy(f.case.live.memo),
                list(f.case.source.lib.PENDING_CURSOR_RENAMES))

    def capture(self, f, **changes):
        with self.capture_owner(f) as owner, self.no_effects(f, owner):
            return self.operation(owner.__dict__, **{**f.request, **changes})

    def assert_batch(self, f, owner, result):
        self.assertIs(type(result), dict)
        self.assertEqual(set(result), BATCH_KEYS)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["status"], "captured-not-published")
        self.assertEqual(result["batch_sha256"], capture_tests.own(result, "batch_sha256"))
        self.assertEqual(result["epoch"], f.request["epoch"])
        self.assertEqual(result["epoch_sha256"], f.request["expected_epoch_sha256"])
        self.assertEqual(result["observed_at"], f.request["observed_at"])
        self.assertEqual(result["notification_baseline_attempt"], f.marker)
        self.assertEqual(result["non_claims"], list(self.source.NON_CLAIMS))
        wrapped = result["delivery_input"]
        self.assertEqual(set(wrapped), wrapper_tests.WRAPPER_KEYS)
        self.assertEqual(wrapped["schema"], wrapper_tests.SCHEMA)
        self.assertEqual(wrapped["status"], "bound-not-consumed")
        self.assertEqual(wrapped["parent_source_schema"], f.retained["schema"])
        self.assertEqual(wrapped["non_claims"], list(self.wrapper.NON_CLAIMS))
        self.assertEqual(wrapped["expected_adoption_sha256"],
                         f.adopted["expected_adoption_sha256"])
        view = wrapped["epoch_view"]
        self.assertEqual(view["epoch_adoption"], f.adopted)
        self.assertEqual(view["parent_generation"], f.generation)
        self.assertEqual(view["parent_committed"], f.committed)
        self.assertEqual(view["records_identity"], f.adopted["adoption"]["records_identity"])
        self.assertEqual(view["expected_parent_generation_sha256"],
                         f.committed["live_generation_sha256"])
        self.assertEqual(wrapped["expected_epoch_view_sha256"],
                         self.source.native_sha(owner.__dict__, view))
        self.assertEqual(wrapped["journal"]["records"], [])
        self.assertEqual(wrapped["journal"]["pending"], [])
        self.assertIs(wrapped["journal"]["complete"], True)
        self.assertEqual(wrapped["expected_journal_sha256"],
                         self.live._sha(wrapped["journal"]))
        self.assertEqual(wrapped["input_sha256"],
                         capture_tests.own(wrapped, "input_sha256"))
        if f.marker is None:
            self.assertEqual(view["schema"], "sia-controller-delivery-epoch-view-v1")
            self.assertEqual(view["status"], "held-not-consumed")
        else:
            self.assertEqual(view["schema"], "sia-controller-delivery-epoch-capture-view-v1")
            self.assertEqual(view["status"], "held-capturable-not-ready")
            self.assertEqual(view["notification_baseline_attempt"], f.marker)
            self.assertEqual(view["expected_notification_baseline_attempt_sha256"],
                             self.source.native_sha(owner.__dict__, f.marker))
        projection = result["intake_projection"]
        self.assertEqual(wrapped["binding"]["intake_sha256"], projection["intake_sha256"])
        self.assertIsNone(self.wrapper.validate(owner.__dict__,
            delivery_input=wrapped, expected_input_sha256=wrapped["input_sha256"],
            epoch=result["epoch"], expected_epoch_sha256=result["epoch_sha256"],
            projection=projection, expected_projection_sha256=projection["projection_sha256"],
            observed_at=result["observed_at"], notification_baseline_attempt=f.marker))

    @contextlib.contextmanager
    def lifetime(self, f, *, at_build=None, at_copy=None, at_epoch_exit=None):
        original_copy = copy.deepcopy
        trace = SimpleNamespace(active_epochs=[], active_journals=[], epochs=[], journals=[],
                                steps=[], collected=[], idle=[], projection=[], swept=False)
        epoch_holds = {
            name: getattr(self.epoch_module, name)
            for name in ("hold_epoch", "hold_capturable_epoch")}
        journal_hold = self.journal.hold_deliveries
        build = self.wrapper.build
        validate = self.source.validate_batch
        collect = self.source._collect
        capture_idle = self.idle.capture
        project = self.source._intake_projection
        named = self.source._CaptureFiles.named_current

        def assert_active():
            self.assertFalse(trace.swept, "source work followed the final named sweep")
            self.assertTrue(trace.active_epochs, "epoch closed before completed batch work")
            self.assertTrue(trace.active_journals, "journal closed before completed batch work")
            for held in trace.active_epochs:
                held.current()
                self.assertEqual(held.read()["records_identity"],
                                 f.adopted["adoption"]["records_identity"])
            for held in trace.active_journals:
                held.current()
                self.assertEqual(held.directory_identity(),
                                 f.adopted["adoption"]["records_identity"])

        def epoch_operation(name):
            @contextlib.contextmanager
            def hold(owner, **kwargs):
                with epoch_holds[name](owner, **kwargs) as held:
                    trace.epochs.append(held)
                    trace.active_epochs.append(held)
                    try:
                        yield held
                    finally:
                        if at_epoch_exit is not None and "wrapper" in trace.steps:
                            at_epoch_exit()
                        trace.active_epochs.remove(held)
            return hold

        @contextlib.contextmanager
        def hold_journal(**kwargs):
            with journal_hold(**kwargs) as held:
                trace.journals.append(held)
                trace.active_journals.append(held)
                try:
                    yield held
                finally:
                    trace.active_journals.remove(held)

        def wrapper_build(owner, **kwargs):
            assert_active()
            self.assertEqual(kwargs["parent_source_schema"], f.retained["schema"])
            self.assertEqual(kwargs["epoch_view"]["records_identity"],
                             trace.active_journals[-1].directory_identity())
            result = build(owner, **kwargs)
            trace.steps.append("wrapper")
            if at_build is not None:
                at_build()
            return result

        def validate_batch(owner, batch, pin):
            if type(batch) is dict and batch.get("schema") == SCHEMA:
                assert_active()
                trace.steps.append("validate-v3")
            return validate(owner, batch, pin)

        def detach(value, *args, **kwargs):
            selected = type(value) is dict and value.get("schema") == SCHEMA
            if selected:
                assert_active()
                trace.steps.append("copy-v3")
            result = original_copy(value, *args, **kwargs)
            if selected and at_copy is not None:
                at_copy()
            return result

        def collect_once(*args, **kwargs):
            self.assertEqual(trace.collected, [], "source-v3 duplicated real collection")
            result = collect(*args, **kwargs)
            trace.collected.append(original_copy(result))
            return result

        def idle_once(*args, **kwargs):
            self.assertEqual(trace.idle, [], "source-v3 duplicated native idle capture")
            result = capture_idle(*args, **kwargs)
            trace.idle.append(original_copy(result))
            return result

        def projection(*args, **kwargs):
            result = project(*args, **kwargs)
            trace.projection.append(original_copy(result))
            return result

        def final_names(files):
            self.assertFalse(trace.active_epochs, "epoch close followed final source sweep")
            self.assertFalse(trace.active_journals, "journal close followed final source sweep")
            result = named(files)
            trace.steps.append("source-final-named")
            trace.swept = True
            return result

        with contextlib.ExitStack() as stack:
            for name in epoch_holds:
                stack.enter_context(mock.patch.object(self.epoch_module, name, epoch_operation(name)))
            for module, name, function in (
                    (self.journal, "hold_deliveries", hold_journal),
                    (self.wrapper, "build", wrapper_build),
                    (self.source, "validate_batch", validate_batch),
                    (self.source, "_collect", collect_once),
                    (self.idle, "capture", idle_once),
                    (self.source, "_intake_projection", projection),
                    (self.source._CaptureFiles, "named_current", final_names),
                    (copy, "deepcopy", detach)):
                stack.enter_context(mock.patch.object(module, name, function))
            yield trace
        self.assertEqual(trace.active_epochs, [])
        self.assertEqual(trace.active_journals, [])
        for held in (*trace.epochs, *trace.journals):
            for operation in (held.read, held.current):
                with self.assertRaises(REFUSALS):
                    operation()

    def test_exact_mandatory_additive_api_and_closed_batch_keys(self):
        parameters = inspect.signature(self.operation).parameters
        self.assertEqual(tuple(parameters), PARAMETERS)
        for name, parameter in parameters.items():
            self.assertIs(parameter.default, inspect.Parameter.empty)
            self.assertEqual(parameter.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD
                             if name == "owner" else inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(set(self.source.BATCH_V2_KEYS) | {"delivery_input"}, BATCH_KEYS)

    def test_outer_capture_refusal_exposes_only_the_exception_class(self):
        with mock.patch.object(
                self.source, "_DeliveryCaptureRequest",
                side_effect=RuntimeError("private upstream detail")), \
                self.assertRaisesRegex(
                    ValueError,
                    "delivery-successor-capture-admission-runtime") as raised:
            self.operation(
                {}, memo=None, admitted_status=None, retained_batch=None,
                committed=None, epoch=None, expected_epoch_sha256=None,
                observed_at=None, journal_limits=None,
                expected_journal_limits_sha256=None,
                expected_adoption_sha256=None)
        self.assertNotIn("private upstream detail", str(raised.exception))

    def test_real_idle_capture_keeps_gist_origins_and_bound_empty_journal(self):
        with self.prepared() as f, self.capture_owner(f) as owner:
            before = self.images(f)
            frozen = copy.deepcopy(f.request)
            with self.no_effects(f, owner):
                descriptors = self.fd_fixture.fds()
                with self.lifetime(f) as trace:
                    result = self.operation(owner.__dict__, **f.request)
                self.assertEqual(self.fd_fixture.fds(), descriptors)
            self.assert_batch(f, owner, result)
            self.assertTrue(trace.collected)
            self.assertEqual(result["source_returns"]["runs"], trace.collected[0]["runs"])
            self.assertTrue(all(not run["events"] for run in result["source_returns"]["runs"]))
            self.assertEqual(trace.idle, [result["idle_input"]])
            self.assertIsNotNone(result["idle_input"]["gist_inputs"])
            self.assertEqual(trace.projection, [result["intake_projection"]])
            old_pages = f.generation["transition"]["state"]["intake"]["pages"]
            self.assertTrue(old_pages)
            pages = result["intake_projection"]["intake"]["pages"]
            self.assertEqual(pages[:len(old_pages)], old_pages)
            self.assertEqual([page["origin"] for page in pages[:len(old_pages)]],
                             [page["origin"] for page in old_pages])
            self.assertIn("wrapper", trace.steps)
            self.assertIn("validate-v3", trace.steps)
            self.assertIn("copy-v3", trace.steps)
            self.assertEqual(trace.steps[-1], "source-final-named")
            self.assertEqual(self.images(f), before)
            self.assertEqual(f.request, frozen)
            result["delivery_input"]["epoch_view"]["parent_generation"].clear()
            result["delivery_input"]["journal"]["records"].append({"not": "a receipt"})
            self.assertEqual(self.images(f), before)
            self.assertEqual(f.request, frozen)

    def test_actual_notification_collector_supports_ordinary_and_fenced_parents(self):
        for fenced in (False, True):
            with self.subTest(fenced=fenced), self.prepared(
                    notifications=True, fenced=fenced) as f, self.capture_owner(f) as owner:
                before = self.images(f)
                actual_notify = owner.sense_notify
                seen = []

                @functools.wraps(actual_notify)
                def notify(*args, **kwargs):
                    result = actual_notify(*args, **kwargs)
                    seen.append([owner._event_replay_record(event) for event in result])
                    return result

                with self.no_effects(f, owner), mock.patch.object(
                        owner, "sense_notify", notify), mock.patch.object(
                        owner, "SENSES", [notify, owner.sense_custom]), self.lifetime(f):
                    result = self.operation(owner.__dict__, **f.request)
                self.assert_batch(f, owner, result)
                self.assertEqual(seen, [result["source_returns"]["runs"][0]["events"]])
                self.assertEqual(result["source_returns"]["runs"][0]["source_id"], "sense_notify")
                self.assertEqual(result["notification_baseline_attempt"], f.marker)
                self.assertEqual(self.images(f), before)

    def test_real_nonidle_custom_return_keeps_original_projection_and_no_gist(self):
        with self.prepared(nonidle=True) as f, self.capture_owner(f) as owner:
            before = self.images(f)
            with self.no_effects(f, owner), self.lifetime(f) as trace:
                result = self.operation(owner.__dict__, **f.request)
            self.assert_batch(f, owner, result)
            self.assertEqual(result["source_returns"]["runs"], trace.collected[0]["runs"])
            self.assertTrue(any(run["events"] for run in result["source_returns"]["runs"]))
            self.assertIsNone(result["idle_input"])
            self.assertEqual(trace.idle, [])
            self.assertEqual(trace.projection, [result["intake_projection"]])
            self.assertEqual(self.images(f), before)

    def test_adoption_and_limits_pins_refuse_before_real_collection(self):
        with self.prepared() as f, self.capture_owner(f) as owner:
            wrong = f.committed["source_batch_sha256"]
            self.assertNotEqual(wrong, f.request["expected_adoption_sha256"])
            changed_limits = dict(self.epoch.limits, unadmitted=True)
            for changes in (
                    {"expected_adoption_sha256": None},
                    {"expected_adoption_sha256": wrong},
                    {"expected_journal_limits_sha256": None},
                    {"expected_journal_limits_sha256": wrong},
                    {"journal_limits": changed_limits,
                     "expected_journal_limits_sha256": self.live._sha(changed_limits)}):
                with self.subTest(changes=changes):
                    before = self.images(f)
                    with self.no_effects(f, owner), mock.patch.object(
                            self.source, "_collect", side_effect=AssertionError(
                                "unadmitted delivery epoch reached collectors")), \
                            self.assertRaises(REFUSALS):
                        self.operation(owner.__dict__, **{**f.request, **changes})
                    self.assertEqual(self.images(f), before)

    def test_missing_explicit_delivery_inputs_never_infer_an_adoption(self):
        with self.prepared() as f, self.capture_owner(f) as owner:
            for name in ("admitted_status", "journal_limits",
                         "expected_journal_limits_sha256", "expected_adoption_sha256"):
                request = dict(f.request)
                request.pop(name)
                before = self.images(f)
                with self.no_effects(f, owner), self.assertRaises(TypeError):
                    self.operation(owner.__dict__, **request)
                self.assertEqual(self.images(f), before)

    def test_complete_request_is_bounded_before_copy_or_additional_acquisition(self):
        with self.prepared() as f, self.capture_owner(f) as owner:
            before = self.images(f)
            ceiling = len(self.source.native_bytes(owner.__dict__, f.request["epoch"]))
            self.assertGreater(len(self.source.native_bytes(owner.__dict__, f.request)), ceiling)
            forbidden = mock.Mock(side_effect=AssertionError(
                "oversized complete source-v3 request reached copy/acquisition"))
            with self.no_effects(f, owner), mock.patch.object(
                    owner, "MAX_STATE_JSON_BYTES", ceiling), mock.patch.object(
                    copy, "deepcopy", forbidden), mock.patch.object(
                    owner, "brainstem_owner", forbidden), mock.patch.object(
                    owner, "corpus_owner", forbidden), mock.patch.object(
                    self.source, "_collect", forbidden), self.assertRaises(REFUSALS):
                self.operation(owner.__dict__, **f.request)
            forbidden.assert_not_called()
            self.assertEqual(self.images(f), before)

    def test_replaced_records_identity_refuses_before_collection_without_repair(self):
        with self.prepared() as f, self.capture_owner(f) as owner:
            records = self.epoch.paths(f.retained, f.root)[-1]
            records.rename(records.with_name("records-before-substitution"))
            records.mkdir(mode=0o700)
            before = self.images(f)
            with self.no_effects(f, owner), mock.patch.object(
                    self.source, "_collect", side_effect=AssertionError(
                        "replacement journal reached collectors")), \
                    self.assertRaises(REFUSALS):
                self.operation(owner.__dict__, **f.request)
            self.assertEqual(self.images(f), before)

    def test_held_authority_changes_after_wrapper_build_refuse_without_publication(self):
        for target in ("status", "source-archive", "adoption", "records"):
            with self.subTest(target=target), self.prepared() as f, self.capture_owner(f) as owner:
                paths = self.epoch.paths(f.retained, f.root)
                before_memo = ack_tests._path_image(f.case.live.paths["MEMO_PATH"])
                fixed = ack_tests._path_image(f.case.producer.source_path)

                def change():
                    if target == "records":
                        records = paths[-1]
                        records.rename(records.with_name("records-late-substitution"))
                        records.mkdir(mode=0o700)
                    else:
                        path = {"status": f.case.live.paths["STATUS_PATH"],
                                "source-archive": f.case.archive_path(),
                                "adoption": paths[-2]}[target]
                        f.case.replace_same_bytes(path)

                with self.no_effects(f, owner):
                    descriptors = self.fd_fixture.fds()
                    with self.lifetime(f, at_build=change), self.assertRaises(REFUSALS):
                        self.operation(owner.__dict__, **f.request)
                    self.assertEqual(self.fd_fixture.fds(), descriptors)
                self.assertEqual(ack_tests._path_image(f.case.live.paths["MEMO_PATH"]), before_memo)
                self.assertEqual(ack_tests._path_image(f.case.producer.source_path), fixed)

    def test_late_final_batch_copy_keeps_epoch_and_journal_authority_current(self):
        with self.prepared(fenced=True) as f, self.capture_owner(f) as owner:
            memo_before = ack_tests._path_image(f.case.live.paths["MEMO_PATH"])
            changed = []

            def change():
                if not changed:
                    changed.append(True)
                    f.case.replace_same_bytes(f.case.effects_archive_path())

            with self.no_effects(f, owner):
                descriptors = self.fd_fixture.fds()
                with self.lifetime(f, at_copy=change), self.assertRaises(REFUSALS):
                    self.operation(owner.__dict__, **f.request)
                self.assertEqual(self.fd_fixture.fds(), descriptors)
            self.assertTrue(changed)
            self.assertEqual(ack_tests._path_image(f.case.live.paths["MEMO_PATH"]), memo_before)
            self.assertFalse(Path(f.case.producer.source_path).exists())

    def test_epoch_exit_precedes_last_source_named_sweep(self):
        with self.prepared() as f, self.capture_owner(f) as owner:
            changed = []

            def change():
                if not changed:
                    changed.append(True)
                    f.case.replace_same_bytes(f.case.source.config_path)

            with self.no_effects(f, owner), self.lifetime(f, at_epoch_exit=change), \
                    self.assertRaises(REFUSALS):
                self.operation(owner.__dict__, **f.request)
            self.assertTrue(changed)
            self.assertFalse(Path(f.case.producer.source_path).exists())

    def test_wrapper_body_interruption_preserves_exception_and_closes_handles(self):
        with self.prepared() as f, self.capture_owner(f) as owner:
            before = self.images(f)
            death = KeyboardInterrupt("controlled source-v3 wrapper interruption")

            def stop():
                raise death

            with self.no_effects(f, owner):
                descriptors = self.fd_fixture.fds()
                with self.lifetime(f, at_build=stop), self.assertRaises(KeyboardInterrupt) as caught:
                    self.operation(owner.__dict__, **f.request)
                self.assertIs(caught.exception, death)
                self.assertEqual(self.fd_fixture.fds(), descriptors)
            self.assertEqual(self.images(f), before)

    def test_retained_v3_validation_does_not_reopen_epoch_journal_or_sources(self):
        with self.prepared() as f, self.capture_owner(f) as owner:
            with self.no_effects(f, owner):
                result = self.operation(owner.__dict__, **f.request)
            before = self.images(f)
            forbidden = mock.Mock(side_effect=AssertionError(
                "retained v3 validation reacquired source/delivery storage"))
            with contextlib.ExitStack() as stack:
                for module, name in (
                        (self.epoch_module, "prepare_epoch"),
                        (self.epoch_module, "hold_epoch"),
                        (self.epoch_module, "hold_capturable_epoch"),
                        (self.journal, "hold_deliveries"),
                        (self.journal, "inspect_deliveries"),
                        (self.source, "_collect"), (self.idle, "capture")):
                    stack.enter_context(mock.patch.object(module, name, forbidden))
                for target in ("builtins.open", "os.open", "os.stat", "os.lstat", "os.scandir"):
                    stack.enter_context(mock.patch(target, forbidden))
                self.assertIsNone(self.source.validate_batch(
                    owner.__dict__, result, result["batch_sha256"]))
            forbidden.assert_not_called()
            self.assertEqual(self.images(f), before)


if __name__ == "__main__":
    unittest.main()
