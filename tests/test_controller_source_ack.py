"""Descriptor-bound controller-source acknowledgment and immutable archive.

Root alone executes this composed fixture, sequentially.  A source batch is
captured through the existing private collector fixture, retained in the fixed
pending slot, bound to the pure live transition, and committed through the
existing source-effects transaction before the operation under test begins.

Acknowledgment may settle only the effects already proposed by that exact
batch.  It must retain the complete batch under a digest-derived immutable
archive name, sign refusals before advancing their source cursors, apply each
cursor with before-or-exact-target compare-and-swap semantics, and make the
final memo the sole readiness point.  It may not recollect, replan, publish a
missing event closure after the live commit, adopt a third cursor state, or
consume legacy ``PENDING_CURSOR_RENAMES`` entries.

These tests establish local transaction ordering and recovery, not source
truth, complete machine history, output delivery, biological cognition, a
held-out benchmark win, or protection from hostile same-user mutation outside
the checked descriptor generations.
"""

import base64
import contextlib
import copy
import inspect
import json
import os
from pathlib import Path
import stat
import unittest
from unittest import mock

from tests import test_controller_source_capture as capture_tests
from tests import test_controller_source_journal as journal_tests
from tests import test_controller_source_effects as effects_tests
from tests import test_event_page_plan as page_tests
from tests import test_journal_capture_context as journal_context_tests
from tests import test_live_loop as live_tests


ACK = "_acknowledge_controller_source_batch"
BOUNDARY = "_controller_source_ack_boundary"
EFFECTS = "_publish_controller_source_effects"
ARCHIVE_DIR = "CONTROLLER_SOURCE_ARCHIVE_DIR"
COMMITTED_KEYS = {
    "source_batch_sha256", "live_generation_sha256",
    "source_effects_receipt_sha256",
}
CORE_PHASES = (
    "archive-durable",
    "refusals-durable",
    "cursor-state-durable",
    "memo-durable",
)
JOURNAL_PHASES = ("journal-sys-durable", "journal-user-durable")
REFUSALS = (ValueError, RuntimeError, OSError)


def _path_image(path):
    path = Path(path)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    identity = (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
    )
    if stat.S_ISREG(info.st_mode):
        payload = path.read_bytes()
    elif stat.S_ISLNK(info.st_mode):
        payload = os.readlink(path)
    else:
        payload = None
    return identity, payload


class ControllerSourceAcknowledgment(unittest.TestCase):
    def setUp(self):
        self.effects = effects_tests.ControllerSourceEffects(
            methodName="runTest")
        self.effects.setUp()
        self.addCleanup(self.effects.doCleanups)
        self.binding = self.effects.effects.binding
        self.producer = self.effects.producer
        self.source = self.producer.source
        self.live = self.effects.live
        self.lib = self.effects.lib
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)

        self.source_state = self.source.root / "state"
        self.archive_dir = self.live.root / "controller-source-archive"
        self.archive_constant_existed = hasattr(self.lib, ARCHIVE_DIR)
        # ``create=True`` keeps the first RED focused on the missing behavior;
        # the API-shape test separately requires the production constant.
        self.stack.enter_context(mock.patch.object(
            self.lib, ARCHIVE_DIR, str(self.archive_dir), create=True))
        for name, value in (
                ("STATE", str(self.source_state)),
                ("CURSORS_PATH", str(self.source.cursors_path)),
                ("CORPUS", str(self.source.lib.CORPUS)),
                ("SHARE", str(self.source.lib.SHARE))):
            self.stack.enter_context(mock.patch.object(
                self.lib, name, value))
        self.batch = None
        self.generation = None
        self.memo_before_ack = None
        self.status_before_ack = None
        self.live_artifacts_before_ack = None

    @contextlib.contextmanager
    def fresh(self):
        case = type(self)(methodName="runTest")
        case.setUp()
        try:
            yield case
        finally:
            case.doCleanups()

    def acker(self):
        operation = getattr(self.lib, ACK, None)
        self.assertTrue(callable(operation),
                        "missing controller-source acknowledgment: " + ACK)
        return operation

    def archive_path(self, batch=None):
        selected = self.batch if batch is None else batch
        self.assertIsNotNone(selected)
        return self.archive_dir / (selected["batch_sha256"] + ".json")

    def _copy_acquisition_fences(self):
        key = self.source.lib.NOTIFY_BASELINE_ATTEMPT_KEY
        if key not in self.source.memo:
            return
        self.live.memo[key] = copy.deepcopy(self.source.memo[key])
        self.live._write(self.live.paths["MEMO_PATH"], self.live.memo)

    def _remember_committed(self, retained, generation):
        self.assertIn("controller_source_effects_committed", self.live.memo)
        receipt = self.live.memo["controller_source_effects_committed"]
        self.assertEqual(receipt["source_batch_sha256"],
                         retained["batch_sha256"])
        self.assertEqual(receipt["live_generation"]["generation_sha256"],
                         generation["generation_sha256"])
        self.assertNotIn("pulse_status_effects_pending", self.live.memo)
        self.assertNotIn("controller_source_effects_pending", self.live.memo)
        self.assertIn("controller_source_pending", self.live.memo)
        self.assertIn("controller_source_live_pending", self.live.memo)
        self.assertIn("live_loop_committed", self.live.memo)
        self.assertNotIn("ready", self.live.memo)
        self.batch = retained
        self.generation = generation
        self.memo_before_ack = copy.deepcopy(self.live.memo)
        self.status_before_ack = self.admitted_status()
        self.live_artifacts_before_ack = {
            name: _path_image(self.live.paths[name])
            for name in (
                "STATUS_PATH", "GRAPH_PATH", "LIVE_CANDIDATE_PATH",
                "LIVE_STATE_PATH")
        }
        return retained, generation

    def commit_live(self, batch):
        self._copy_acquisition_fences()
        retained = self.effects.start(batch=batch)
        self.assertEqual(retained["batch_sha256"], batch["batch_sha256"])
        publish = getattr(self.lib, EFFECTS, None)
        self.assertTrue(callable(publish),
                        "missing controller-source effects publisher: "
                        + EFFECTS)
        with self.effects.publication_effects(
                null=batch["event_closure"] is None):
            self.assertIsNone(publish(
                memo=self.live.memo,
                admitted_status=self.effects.admitted_status))
        return self._remember_committed(
            copy.deepcopy(self.effects.batch),
            copy.deepcopy(self.effects.committed_generation))

    def commit_incomplete_live(self, batch):
        """Construct the pre-effects legacy prefix used only by refusal tests."""
        self._copy_acquisition_fences()
        retained = self.producer._stage(batch)
        self.assertEqual(retained["batch_sha256"], batch["batch_sha256"])
        self.assertIsNone(self.lib._stage_controller_source_live_binding(
            memo=self.live.memo, admitted_status=self.live.status,
            seq=self.live.status["pulse_seq"]))
        candidate = self.lib._prepare_controller_source_live_candidate(
            memo=self.live.memo, admitted_status=self.live.status)
        self.assertIsNone(self.lib._stage_live_generation(
            memo=self.live.memo, status=self.live.status,
            **candidate))
        generation = self.lib._publish_staged_live_generation(
            memo=self.live.memo)
        self.assertNotIn("controller_source_effects_committed", self.live.memo)
        self.assertIn("controller_source_pending", self.live.memo)
        self.assertIn("controller_source_live_pending", self.live.memo)
        self.assertIn("live_loop_committed", self.live.memo)
        self.assertNotIn("ready", self.live.memo)
        self.batch = retained
        self.generation = generation
        self.memo_before_ack = copy.deepcopy(self.live.memo)
        self.status_before_ack = self.admitted_status()
        self.live_artifacts_before_ack = {
            name: _path_image(self.live.paths[name])
            for name in (
                "STATUS_PATH", "GRAPH_PATH", "LIVE_CANDIDATE_PATH",
                "LIVE_STATE_PATH")
        }
        return retained, generation

    def start_empty(self):
        return self.commit_live(self.producer._capture(empty=True))

    def start_nonempty(self):
        return self.commit_live(self.producer._capture())

    def start_refusal_only(self):
        configured = copy.deepcopy(self.source.custom_entries)
        for entry in configured:
            entry["type"] = "jsonl"
            Path(entry["path"]).write_text(
                '{"private":"not-the-selected-field"}\n',
                encoding="utf-8")
        disabled = sorted(set(self.source.lib.BASE_ORGANS)
                          | set(self.source.lib.OPTIONAL_ORGANS))
        self.source.install_config({
            "senses": {"disable": disabled},
            "custom_senses": configured,
        })
        self.source.configure_selection([], configured)
        batch = self.source.capture()
        self.source.assert_batch(batch)
        self.assertIsNone(batch["event_closure"])
        self.assertTrue(any(
            row["record_refusals"] for row in batch["refusal_intents"]))
        return self.commit_live(batch)

    def start_journal(self):
        helper = journal_tests.ControllerSourceJournal(methodName="runTest")
        state = self.source_state
        state.mkdir(parents=True, exist_ok=True)
        pending = [("capture-unrelated-temp", "capture-unrelated-real")]
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                self.source.lib, "STATE", str(state)))
            stack.enter_context(mock.patch.object(
                self.source.lib, "subprocess",
                journal_context_tests._ModuleShim(
                    journal_tests.subprocess)))
            stack.enter_context(mock.patch.object(
                self.source.lib, "PENDING_CURSOR_RENAMES", pending))
            stack.enter_context(mock.patch.object(
                self.source.lib, "utcnow",
                return_value=journal_context_tests.STAMP))
            disabled = sorted(
                (set(self.source.lib.BASE_ORGANS)
                 | set(self.source.lib.OPTIONAL_ORGANS)) - {"journal"})
            self.source.install_config({
                "senses": {"disable": disabled}, "custom_senses": []})
            self.source.configure_selection(["sense_journal"], [])
            paths = helper.seed_journal_cursors(self.source)
            with helper.synthetic_journal(self.source), \
                    helper.observe_actual_journal(self.source):
                batch = self.source.capture()
        self.source.assert_batch(batch)
        self.assertEqual(len(batch["journal_proposals"]), 1)
        self.journal_paths = paths
        return self.commit_live(batch)

    def start_notify(self):
        self.source.select_notifications()
        batch = self.source.capture()
        self.source.assert_batch(batch)
        marker = batch["notification_baseline_attempt"]
        self.assertIsNotNone(marker)
        self.assertEqual(
            self.source.memo[self.source.lib.NOTIFY_BASELINE_ATTEMPT_KEY],
            marker)
        self.commit_live(batch)
        return marker

    def admitted_status(self):
        return self.live._read("STATUS_PATH")

    def acknowledge(self, *, memo=None, status=None):
        return self.acker()(
            memo=self.live.memo if memo is None else memo,
            admitted_status=(self.admitted_status()
                             if status is None else status))

    def images(self):
        paths = {
            "source": self.producer.source_path,
            "archive-dir": self.archive_dir,
            "archive": None if self.batch is None else self.archive_path(),
            "memo": Path(self.live.paths["MEMO_PATH"]),
            "status": Path(self.live.paths["STATUS_PATH"]),
            "graph": Path(self.live.paths["GRAPH_PATH"]),
            "candidate": Path(self.live.paths["LIVE_CANDIDATE_PATH"]),
            "generation": Path(self.live.paths["LIVE_STATE_PATH"]),
            "cursors": self.source.cursors_path,
            "journal-sys": self.source_state / "journal-sys.cursor",
            "journal-user": self.source_state / "journal-user.cursor",
        }
        result = {
            name: None if path is None else _path_image(path)
            for name, path in paths.items()
        }
        result["corpus"] = self.source.pages.snapshot()
        return result

    @contextlib.contextmanager
    def forbid_ack_effects(self):
        def forbidden(*_args, **_kwargs):
            raise AssertionError(
                "refused acknowledgment crossed an effect boundary")

        shim = page_tests._ModuleShim(
            self.lib.siaqueue,
            _rename_noreplace=forbidden,
            fixed_atomic_publish=forbidden)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                self.lib, "siaqueue", shim))
            for name in (
                    "atomic_write", "save_cursors", "_commit_sense_cursors",
                    "_discard_pending_cursor_renames",
                    "_settle_source_refusals",
                    "_settle_source_record_refusals",
                    "_settle_source_entry_refusals",
                    "_publish_event_page_plan",
                    "_publish_event_page_plan_batch",
                    "_publish_event_page_batch_closure",
                    "brain_sync", "export_status", "export_graph"):
                if hasattr(self.lib, name):
                    stack.enter_context(mock.patch.object(
                        self.lib, name, side_effect=forbidden))
            yield

    def assert_refused_without_effect(self, callback):
        before = self.images()
        pending = copy.deepcopy(self.live.memo)
        with self.forbid_ack_effects(), self.assertRaises(REFUSALS):
            callback()
        self.assertEqual(self.images(), before)
        self.assertEqual(self.live.memo, pending)

    def cursor_target_bytes(self):
        return json.dumps(
            self.batch["cursor_proposal"]["after"], indent=1,
            sort_keys=True, allow_nan=False).encode("utf-8")

    def expected_final_memo(self):
        committed = {
            "source_batch_sha256": self.batch["batch_sha256"],
            "live_generation_sha256": self.generation[
                "generation_sha256"],
            "source_effects_receipt_sha256": self.memo_before_ack[
                "controller_source_effects_committed"]["receipt_sha256"],
        }
        ready = {
            "v": 1,
            "completed_at": self.status_before_ack["ts"],
            "kind": "pulse",
            "identity": self.generation["publication_id"],
        }
        expected = copy.deepcopy(self.memo_before_ack)
        expected.pop("controller_source_pending")
        expected.pop("controller_source_live_pending")
        expected.pop("controller_source_effects_committed")
        expected.pop("pulse_status_effects_pending", None)
        expected.pop("live_loop_pending", None)
        if self.batch["notification_baseline_attempt"] is not None:
            expected.pop(self.lib.NOTIFY_BASELINE_ATTEMPT_KEY)
        expected["controller_source_committed"] = committed
        expected["ready"] = ready
        return expected

    def assert_final(self):
        archive = self.archive_path()
        durable = self.live._read("MEMO_PATH")
        expected = self.expected_final_memo()
        committed = expected["controller_source_committed"]
        ready = expected["ready"]
        self.assertFalse(os.path.lexists(self.producer.source_path))
        self.assertTrue(archive.is_file())
        self.assertEqual(archive.read_bytes(), capture_tests.canonical(
            self.batch))
        self.assertEqual(durable, self.live.memo)
        self.assertNotIn("controller_source_pending", durable)
        self.assertNotIn("controller_source_live_pending", durable)
        self.assertNotIn("live_loop_pending", durable)
        self.assertEqual(set(durable["controller_source_committed"]),
                         COMMITTED_KEYS)
        self.assertEqual(durable["controller_source_committed"], committed)
        self.assertEqual(
            durable["controller_source_committed"][
                "live_generation_sha256"],
            durable["live_loop_committed"]["generation_sha256"])
        self.assertEqual(durable["ready"], ready)
        self.assertEqual(durable, expected)
        self.assertEqual({
            name: _path_image(self.live.paths[name])
            for name in (
                "STATUS_PATH", "GRAPH_PATH", "LIVE_CANDIDATE_PATH",
                "LIVE_STATE_PATH")
        }, self.live_artifacts_before_ack)
        self.assertEqual(
            self.source.cursors_path.read_bytes(),
            self.cursor_target_bytes())
        return durable

    @contextlib.contextmanager
    def otherwise_ready(self):
        with contextlib.ExitStack() as stack:
            for name in (
                    "_consolidation_scan_debt", "_thought_recovery_debt",
                    "_graph_projection_debt"):
                stack.enter_context(mock.patch.object(
                    self.lib, name, return_value=""))
            stack.enter_context(mock.patch.object(
                self.lib, "_cortex_boundary_status",
                return_value=(True, "")))
            stack.enter_context(mock.patch.object(
                self.lib.siamind, "load_mind", return_value={}))
            for name in (
                    "natural_history_recovery_required",
                    "grade_recovery_required", "take_migration_required",
                    "intent_history_required"):
                stack.enter_context(mock.patch.object(
                    self.lib.siatakes, name, return_value=False))
            yield

    def seed_unrelated_pending_rename(self):
        temporary = self.live.root / "unrelated.cursor.pulse"
        destination = self.live.root / "unrelated.cursor"
        temporary.write_bytes(b"unrelated pending bytes")
        destination.write_bytes(b"unrelated durable bytes")
        pending = [(str(temporary), str(destination))]
        return pending, temporary, destination

    def replace_same_bytes(self, path):
        path = Path(path)
        before = path.stat()
        replacement = path.with_name(path.name + ".same-bytes-replacement")
        replacement.write_bytes(path.read_bytes())
        replacement.chmod(stat.S_IMODE(before.st_mode))
        os.replace(replacement, path)
        after = path.stat()
        self.assertNotEqual((after.st_dev, after.st_ino),
                            (before.st_dev, before.st_ino))
        return path.read_bytes()

    def journal_target(self, scope):
        proposal = self.batch["journal_proposals"][0]
        row = next(row for row in proposal["cursors"]
                   if row["scope"] == scope)
        return base64.b64decode(row["target"]["raw_base64"], validate=True)

    def test_exact_keyword_only_api_and_archive_constant(self):
        self.assertTrue(self.archive_constant_existed,
                        "missing source archive directory constant: "
                        + ARCHIVE_DIR)
        operation = self.acker()
        parameters = inspect.signature(operation).parameters
        self.assertEqual(tuple(parameters), ("memo", "admitted_status"))
        for parameter in parameters.values():
            self.assertEqual(parameter.kind,
                             inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)
        self.assertTrue(callable(getattr(self.lib, BOUNDARY, None)),
                        "missing acknowledgment crash seam: " + BOUNDARY)

    def test_empty_real_source_moves_same_inode_and_completes_readiness(self):
        self.start_empty()
        source = Path(self.producer.source_path)
        source_raw = source.read_bytes()
        source_info = source.stat()
        pending, temporary, destination = \
            self.seed_unrelated_pending_rename()
        rename = self.lib.siaqueue._rename_noreplace

        with mock.patch.object(
                self.lib, "PENDING_CURSOR_RENAMES", pending), \
                mock.patch.object(
                    self.lib.siaqueue, "_rename_noreplace",
                    wraps=rename) as archive_move:
            self.assertIsNone(self.acknowledge())
            self.assertIs(self.lib.PENDING_CURSOR_RENAMES, pending)
            self.assertEqual(self.lib.PENDING_CURSOR_RENAMES, [
                (str(temporary), str(destination))])
        self.assertEqual(archive_move.call_count, 1)
        archive = self.archive_path()
        archive_info = archive.stat()
        self.assertEqual(archive.read_bytes(), source_raw)
        self.assertEqual((archive_info.st_dev, archive_info.st_ino),
                         (source_info.st_dev, source_info.st_ino))
        self.assertEqual(stat.S_IMODE(archive_info.st_mode), 0o600)
        self.assertEqual(archive_info.st_uid, os.geteuid())
        self.assertEqual(archive_info.st_nlink, 1)
        self.assertEqual(stat.S_IMODE(self.archive_dir.stat().st_mode),
                         0o700)
        self.assertEqual(temporary.read_bytes(), b"unrelated pending bytes")
        self.assertEqual(destination.read_bytes(), b"unrelated durable bytes")
        self.assert_final()

        with self.otherwise_ready():
            self.assertEqual(self.lib.memory_readiness(), (True, ""))

    def test_completed_retry_is_write_free_and_keeps_archive_generation(self):
        self.start_empty()
        self.assertIsNone(self.acknowledge())
        pending, temporary, destination = \
            self.seed_unrelated_pending_rename()

        def forbidden(*_args, **_kwargs):
            raise AssertionError("exact completed retry attempted an effect")

        shim = page_tests._ModuleShim(
            self.lib.siaqueue,
            _rename_noreplace=forbidden,
            fixed_atomic_publish=forbidden)
        with mock.patch.object(
                self.lib, "PENDING_CURSOR_RENAMES", pending), \
                mock.patch.object(self.lib, "siaqueue", shim), \
                mock.patch.object(self.lib, "atomic_write",
                                  side_effect=forbidden), \
                mock.patch.object(self.lib, "_write_memo",
                                  side_effect=forbidden), \
                mock.patch.object(self.lib, "save_cursors",
                                  side_effect=forbidden), \
                mock.patch.object(self.lib, "_commit_sense_cursors",
                                  side_effect=forbidden), \
                mock.patch.object(
                    self.lib, "_discard_pending_cursor_renames",
                    side_effect=forbidden), \
                mock.patch.object(
                    self.lib, "_settle_source_record_refusals",
                    side_effect=forbidden), \
                mock.patch.object(
                    self.lib, "_settle_source_entry_refusals",
                    side_effect=forbidden):
            before = self.images()
            archive_before = self.archive_path().stat()
            self.assertIsNone(self.acknowledge())
            archive_after = self.archive_path().stat()
            self.assertEqual((archive_after.st_dev, archive_after.st_ino),
                             (archive_before.st_dev, archive_before.st_ino))
            self.assertEqual(self.images(), before)
            self.assertEqual(pending, [
                (str(temporary), str(destination))])
        self.assertEqual(temporary.read_bytes(), b"unrelated pending bytes")
        self.assertEqual(destination.read_bytes(), b"unrelated durable bytes")

    def test_each_core_prefix_crash_recovers_the_same_commit(self):
        for selected in CORE_PHASES:
            with self.subTest(phase=selected), self.fresh() as case:
                case.start_empty()
                cursor_before = case.source.cursors_path.read_bytes()
                calls = []

                def cut(phase):
                    calls.append(phase)
                    if phase == selected:
                        raise KeyboardInterrupt(
                            "fixture cut after " + selected)

                with mock.patch.object(
                        case.lib, BOUNDARY, side_effect=cut, create=True), \
                        self.assertRaisesRegex(
                            KeyboardInterrupt, "fixture cut"):
                    case.acknowledge()
                self.assertEqual(
                    tuple(calls),
                    CORE_PHASES[:CORE_PHASES.index(selected) + 1])
                self.assertFalse(os.path.lexists(case.producer.source_path))
                self.assertEqual(
                    case.archive_path().read_bytes(),
                    capture_tests.canonical(case.batch))
                if selected in ("archive-durable", "refusals-durable"):
                    self.assertEqual(
                        case.source.cursors_path.read_bytes(), cursor_before)
                else:
                    self.assertEqual(
                        case.source.cursors_path.read_bytes(),
                        case.cursor_target_bytes())
                durable = case.live._read("MEMO_PATH")
                case.live.memo.clear()
                case.live.memo.update(copy.deepcopy(durable))
                if selected != "memo-durable":
                    self.assertIn("controller_source_pending", durable)
                    self.assertIn("controller_source_live_pending", durable)
                    self.assertNotIn("ready", durable)
                else:
                    self.assertEqual(durable, case.expected_final_memo())
                self.assertIsNone(case.acknowledge())
                case.assert_final()

    def test_archive_only_exact_bytes_recovers_an_observed_move_prefix(self):
        self.start_empty()
        source = Path(self.producer.source_path)
        original = source.stat()
        self.archive_dir.mkdir(mode=0o700)
        archive = self.archive_path()
        os.rename(source, archive)
        moved = archive.stat()
        self.assertEqual((moved.st_dev, moved.st_ino),
                         (original.st_dev, original.st_ino))

        self.assertIsNone(self.acknowledge())
        self.assert_final()

    def test_main_cursor_accepts_exact_target_retry_but_refuses_third_state(self):
        with self.fresh() as case:
            case.start_empty()
            case.source.lib.save_cursors(
                copy.deepcopy(case.batch["cursor_proposal"]["after"]))
            target = case.source.cursors_path.read_bytes()
            self.assertIsNone(case.acknowledge())
            self.assertEqual(case.source.cursors_path.read_bytes(), target)
            case.assert_final()

        with self.fresh() as case:
            case.start_empty()
            case.source.cursors_path.write_bytes(b'{"foreign":true}')
            case.source.cursors_path.chmod(0o600)
            pending, temporary, destination = \
                case.seed_unrelated_pending_rename()
            with mock.patch.object(
                    case.lib, "PENDING_CURSOR_RENAMES", pending):
                case.assert_refused_without_effect(case.acknowledge)
            self.assertEqual(pending, [
                (str(temporary), str(destination))])
            self.assertEqual(temporary.read_bytes(),
                             b"unrelated pending bytes")
            self.assertEqual(destination.read_bytes(),
                             b"unrelated durable bytes")

    def test_main_cursor_same_before_bytes_new_inode_is_a_third_state(self):
        self.start_refusal_only()
        proposal = self.batch["cursor_proposal"]
        self.assertNotEqual(
            capture_tests.canonical(proposal["before_value"]),
            capture_tests.canonical(proposal["after"]))
        before = self.replace_same_bytes(self.source.cursors_path)

        self.assert_refused_without_effect(self.acknowledge)
        self.assertEqual(self.source.cursors_path.read_bytes(), before)

    def test_main_cursor_semantic_target_with_different_wire_is_third_state(self):
        self.start_refusal_only()
        compact = capture_tests.canonical(
            self.batch["cursor_proposal"]["after"])
        self.assertNotEqual(compact, self.cursor_target_bytes())
        self.source.cursors_path.write_bytes(compact)
        self.source.cursors_path.chmod(0o600)

        self.assert_refused_without_effect(self.acknowledge)
        self.assertEqual(self.source.cursors_path.read_bytes(), compact)

    def test_main_cursor_generation_is_rechecked_after_archive_prefix(self):
        self.start_refusal_only()
        source_raw = Path(self.producer.source_path).read_bytes()
        memo_raw = Path(self.live.paths["MEMO_PATH"]).read_bytes()
        cursor_raw = self.source.cursors_path.read_bytes()
        phases = []

        def boundary(phase):
            phases.append(phase)
            if phase == "archive-durable":
                self.replace_same_bytes(self.source.cursors_path)

        def forbidden(*_args, **_kwargs):
            raise AssertionError(
                "post-archive cursor race reached a later effect")

        shim = page_tests._ModuleShim(
            self.lib.siaqueue,
            _rename_noreplace=self.lib.siaqueue._rename_noreplace,
            fixed_atomic_publish=forbidden)
        with mock.patch.object(self.lib, BOUNDARY,
                               side_effect=boundary, create=True), \
                mock.patch.object(self.lib, "siaqueue", shim), \
                mock.patch.object(self.lib, "atomic_write",
                                  side_effect=forbidden), \
                mock.patch.object(
                    self.lib, "_settle_source_record_refusals",
                    side_effect=forbidden), \
                mock.patch.object(
                    self.lib, "_settle_source_entry_refusals",
                    side_effect=forbidden), \
                self.assertRaises(REFUSALS):
            self.acknowledge()
        self.assertEqual(phases, ["archive-durable"])
        self.assertFalse(os.path.lexists(self.producer.source_path))
        self.assertEqual(self.archive_path().read_bytes(), source_raw)
        self.assertEqual(self.source.cursors_path.read_bytes(), cursor_raw)
        self.assertEqual(
            Path(self.live.paths["MEMO_PATH"]).read_bytes(), memo_raw)

    def test_journal_before_and_exact_target_prefixes_commit_in_scope_order(self):
        self.start_journal()
        sys_path = self.source_state / "journal-sys.cursor"
        user_path = self.source_state / "journal-user.cursor"
        sys_path.write_bytes(self.journal_target("sys"))
        sys_path.chmod(0o600)
        phases = []
        with mock.patch.object(
                self.lib, BOUNDARY,
                side_effect=lambda phase: phases.append(phase), create=True):
            self.assertIsNone(self.acknowledge())
        self.assertEqual(sys_path.read_bytes(), self.journal_target("sys"))
        self.assertEqual(user_path.read_bytes(), self.journal_target("user"))
        self.assertEqual(tuple(phases), (
            "archive-durable", "refusals-durable",
            "journal-sys-durable", "journal-user-durable",
            "cursor-state-durable", "memo-durable",
        ))
        self.assert_final()

    def test_later_journal_third_state_refuses_before_earlier_scope_changes(self):
        self.start_journal()
        sys_path = self.source_state / "journal-sys.cursor"
        user_path = self.source_state / "journal-user.cursor"
        before_sys = sys_path.read_bytes()
        user_path.write_bytes(b"foreign-user-cursor")
        user_path.chmod(0o600)

        self.assert_refused_without_effect(self.acknowledge)
        self.assertEqual(sys_path.read_bytes(), before_sys)
        self.assertEqual(user_path.read_bytes(), b"foreign-user-cursor")

    def test_journal_same_before_bytes_new_inode_refuses_before_archive(self):
        self.start_journal()
        sys_path = self.source_state / "journal-sys.cursor"
        before = self.replace_same_bytes(sys_path)

        self.assert_refused_without_effect(self.acknowledge)
        self.assertEqual(sys_path.read_bytes(), before)

    def test_journal_generation_is_rechecked_after_prior_durable_prefixes(self):
        self.start_journal()
        source_raw = Path(self.producer.source_path).read_bytes()
        memo_raw = Path(self.live.paths["MEMO_PATH"]).read_bytes()
        sys_path = self.source_state / "journal-sys.cursor"
        user_path = self.source_state / "journal-user.cursor"
        sys_before = sys_path.read_bytes()
        user_before = user_path.read_bytes()
        phases = []

        def boundary(phase):
            phases.append(phase)
            if phase == "refusals-durable":
                self.replace_same_bytes(user_path)

        def forbidden(*_args, **_kwargs):
            raise AssertionError(
                "journal cursor race reached a later effect")

        shim = page_tests._ModuleShim(
            self.lib.siaqueue,
            _rename_noreplace=self.lib.siaqueue._rename_noreplace,
            fixed_atomic_publish=forbidden)
        with mock.patch.object(self.lib, BOUNDARY,
                               side_effect=boundary, create=True), \
                mock.patch.object(self.lib, "siaqueue", shim), \
                mock.patch.object(self.lib, "atomic_write",
                                  side_effect=forbidden), \
                self.assertRaises(REFUSALS):
            self.acknowledge()
        self.assertEqual(phases, [
            "archive-durable", "refusals-durable"])
        self.assertFalse(os.path.lexists(self.producer.source_path))
        self.assertEqual(self.archive_path().read_bytes(), source_raw)
        self.assertEqual(sys_path.read_bytes(), sys_before)
        self.assertEqual(user_path.read_bytes(), user_before)
        self.assertEqual(
            Path(self.live.paths["MEMO_PATH"]).read_bytes(), memo_raw)

    def test_each_journal_prefix_crash_recovers_without_legacy_pending_use(self):
        for selected in JOURNAL_PHASES:
            with self.subTest(phase=selected), self.fresh() as case:
                case.start_journal()
                main_before = case.source.cursors_path.read_bytes()
                sys_path = case.source_state / "journal-sys.cursor"
                user_path = case.source_state / "journal-user.cursor"
                sys_before = sys_path.read_bytes()
                user_before = user_path.read_bytes()
                calls = []
                pending, temporary, destination = \
                    case.seed_unrelated_pending_rename()

                def cut(phase):
                    calls.append(phase)
                    if phase in (
                            "archive-durable", "refusals-durable"):
                        self.assertEqual(sys_path.read_bytes(), sys_before)
                        self.assertEqual(user_path.read_bytes(), user_before)
                    if phase == "archive-durable":
                        self.assertFalse(os.path.lexists(
                            case.producer.source_path))
                        self.assertEqual(
                            case.archive_path().read_bytes(),
                            capture_tests.canonical(case.batch))
                    if phase == selected:
                        raise KeyboardInterrupt("fixture journal cut")

                with mock.patch.object(
                        case.lib, "PENDING_CURSOR_RENAMES", pending), \
                        mock.patch.object(
                            case.lib, BOUNDARY, side_effect=cut, create=True), \
                        self.assertRaisesRegex(
                            KeyboardInterrupt, "fixture journal cut"):
                    case.acknowledge()
                prefix = (
                    "archive-durable", "refusals-durable",
                    "journal-sys-durable", "journal-user-durable",
                )
                self.assertEqual(
                    tuple(calls), prefix[:prefix.index(selected) + 1])
                self.assertFalse(os.path.lexists(
                    case.producer.source_path))
                self.assertEqual(
                    case.archive_path().read_bytes(),
                    capture_tests.canonical(case.batch))
                self.assertEqual(sys_path.read_bytes(),
                                 case.journal_target("sys"))
                if selected == "journal-sys-durable":
                    self.assertEqual(user_path.read_bytes(), user_before)
                else:
                    self.assertEqual(user_path.read_bytes(),
                                     case.journal_target("user"))
                self.assertNotEqual(sys_path.read_bytes(), sys_before)
                self.assertEqual(
                    case.source.cursors_path.read_bytes(), main_before)
                self.assertEqual(pending, [
                    (str(temporary), str(destination))])
                durable = case.live._read("MEMO_PATH")
                case.live.memo.clear()
                case.live.memo.update(copy.deepcopy(durable))
                with mock.patch.object(
                        case.lib, "PENDING_CURSOR_RENAMES", pending):
                    self.assertIsNone(case.acknowledge())
                self.assertEqual(temporary.read_bytes(),
                                 b"unrelated pending bytes")
                self.assertEqual(destination.read_bytes(),
                                 b"unrelated durable bytes")
                case.assert_final()

    def test_live_status_and_binding_mismatches_refuse_before_ack_effects(self):
        cases = ("status", "binding", "live-receipt", "generation")
        for selected in cases:
            with self.subTest(case=selected), self.fresh() as case:
                case.start_empty()
                status = case.admitted_status()
                if selected == "status":
                    status = copy.deepcopy(status)
                    status["publication_id"] = "d" * 32
                elif selected == "binding":
                    marker = copy.deepcopy(case.live.memo[
                        "controller_source_live_pending"])
                    marker["state_sha256"] = "0" * 64
                    publication_sha256 = live_tests.digest(
                        case.binding._publication_basis(marker))
                    marker["publication_id"] = publication_sha256[:32]
                    marker["publication_sha256"] = publication_sha256
                    marker["marker_sha256"] = live_tests.digest({
                        key: value for key, value in marker.items()
                        if key != "marker_sha256"
                    })
                    case.live.memo[
                        "controller_source_live_pending"] = marker
                    case.live._write(
                        case.live.paths["MEMO_PATH"], case.live.memo)
                elif selected == "live-receipt":
                    case.live.memo["live_loop_committed"][
                        "generation_sha256"] = "0" * 64
                    case.live._write(
                        case.live.paths["MEMO_PATH"], case.live.memo)
                else:
                    path = Path(case.live.paths["LIVE_STATE_PATH"])
                    changed = json.loads(path.read_bytes())
                    changed["generation_sha256"] = "0" * 64
                    case.live._write(path, changed)
                case.assert_refused_without_effect(
                    lambda: case.acknowledge(status=status))

    def test_archive_ambiguous_or_unsafe_states_are_never_adopted(self):
        cases = (
            "both", "neither", "different", "wrong-mode",
            "symlink", "hardlink",
        )
        for selected in cases:
            with self.subTest(case=selected), self.fresh() as case:
                case.start_empty()
                source = Path(case.producer.source_path)
                case.archive_dir.mkdir(mode=0o700)
                archive = case.archive_path()
                if selected == "both":
                    archive.write_bytes(source.read_bytes())
                    archive.chmod(0o600)
                elif selected == "neither":
                    source.unlink()
                elif selected == "different":
                    source.unlink()
                    archive.write_bytes(b"different retained batch")
                    archive.chmod(0o600)
                elif selected == "wrong-mode":
                    source.unlink()
                    archive.write_bytes(capture_tests.canonical(case.batch))
                    archive.chmod(0o640)
                elif selected == "symlink":
                    archive.symlink_to(source)
                else:
                    os.link(source, archive)
                before_archive = _path_image(archive)
                case.assert_refused_without_effect(case.acknowledge)
                self.assertEqual(_path_image(archive), before_archive)

    def test_rename_time_archive_collision_never_clobbers_foreign_target(self):
        self.start_empty()
        source = Path(self.producer.source_path)
        source_before = _path_image(source)
        self.archive_dir.mkdir(mode=0o700)
        archive = self.archive_path()
        memo_before = Path(self.live.paths["MEMO_PATH"]).read_bytes()
        cursor_before = self.source.cursors_path.read_bytes()
        rename = self.lib.siaqueue._rename_noreplace
        foreign = b"foreign archive collision"

        def collide(source_descriptor, source_name,
                    destination_descriptor, destination_name):
            self.assertEqual(source_name, source.name)
            self.assertEqual(destination_name, archive.name)
            descriptor = os.open(
                destination_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600, dir_fd=destination_descriptor)
            try:
                os.write(descriptor, foreign)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.fsync(destination_descriptor)
            return rename(
                source_descriptor, source_name,
                destination_descriptor, destination_name)

        with mock.patch.object(
                self.lib.siaqueue, "_rename_noreplace",
                side_effect=collide), self.assertRaises(REFUSALS):
            self.acknowledge()
        self.assertEqual(_path_image(source), source_before)
        self.assertEqual(archive.read_bytes(), foreign)
        self.assertEqual(
            Path(self.live.paths["MEMO_PATH"]).read_bytes(), memo_before)
        self.assertEqual(self.source.cursors_path.read_bytes(), cursor_before)

    def test_refusal_rows_settle_in_catalog_order_before_any_cursor_ack(self):
        self.start_refusal_only()
        cursor_before = self.source.cursors_path.read_bytes()
        expected = []
        for intent in self.batch["refusal_intents"]:
            if intent["record_refusals"]:
                expected.append((
                    "record", intent["source_id"],
                    copy.deepcopy(intent["record_refusals"])))
            if intent["entry_refusals"]:
                expected.append((
                    "entry", intent["source_id"],
                    copy.deepcopy(intent["entry_refusals"])))
        self.assertEqual(
            [row[1] for row in expected],
            [row["source_id"]
             for row in self.batch["epoch"]["source_catalog"]["sources"]])
        settled = []
        trace = []

        def settle_records(source, rows):
            self.assertEqual(
                self.source.cursors_path.read_bytes(), cursor_before)
            self.assertTrue(rows)
            item = ("record", source, copy.deepcopy(rows))
            settled.append(item)
            trace.append(("settle", item))

        def settle_entries(source, rows):
            self.assertEqual(
                self.source.cursors_path.read_bytes(), cursor_before)
            self.assertTrue(rows)
            item = ("entry", source, copy.deepcopy(rows))
            settled.append(item)
            trace.append(("settle", item))

        def boundary(phase):
            if phase == "refusals-durable":
                self.assertEqual(settled, expected)
                self.assertEqual(
                    self.source.cursors_path.read_bytes(), cursor_before)
            if phase == "cursor-state-durable":
                self.assertEqual(
                    json.loads(self.source.cursors_path.read_bytes()),
                    self.batch["cursor_proposal"]["after"])
            trace.append(("phase", phase))

        with mock.patch.object(
                self.lib, "_settle_source_record_refusals",
                side_effect=settle_records), \
                mock.patch.object(
                    self.lib, "_settle_source_entry_refusals",
                    side_effect=settle_entries), \
                mock.patch.object(
                    self.lib, BOUNDARY,
                    side_effect=boundary,
                    create=True):
            self.assertIsNone(self.acknowledge())
        self.assertEqual(settled, expected)
        self.assertEqual(trace, [
            ("phase", "archive-durable"),
            *[("settle", item) for item in expected],
            ("phase", "refusals-durable"),
            ("phase", "cursor-state-durable"),
            ("phase", "memo-durable"),
        ])
        self.assert_final()

    def test_notification_fence_clears_only_after_safe_cursor_checkpoint(self):
        marker = self.start_notify()
        key = self.lib.NOTIFY_BASELINE_ATTEMPT_KEY
        self.assertEqual(self.live.memo[key], marker)
        original = copy.deepcopy(self.live.memo)
        changed = copy.deepcopy(original)
        changed[key]["id"] = "f" * 32
        self.live._write(self.live.paths["MEMO_PATH"], changed)
        self.live.memo.clear()
        self.live.memo.update(changed)
        self.assert_refused_without_effect(self.acknowledge)
        self.live._write(self.live.paths["MEMO_PATH"], original)
        self.live.memo.clear()
        self.live.memo.update(original)
        before = self.images()
        with mock.patch.object(
                self.lib, "_notify_cursor_checkpoint_safe",
                return_value=False):
            self.assert_refused_without_effect(self.acknowledge)
        self.assertEqual(self.images(), before)
        self.assertEqual(self.live.memo[key], marker)

        def cut(phase):
            if phase == "cursor-state-durable":
                durable = self.live._read("MEMO_PATH")
                self.assertEqual(durable[key], marker)
                self.assertEqual(
                    json.loads(self.source.cursors_path.read_bytes()),
                    self.batch["cursor_proposal"]["after"])
                raise KeyboardInterrupt("fixture notification cut")

        with mock.patch.object(
                self.lib, BOUNDARY, side_effect=cut, create=True), \
                self.assertRaisesRegex(
                    KeyboardInterrupt, "fixture notification cut"):
            self.acknowledge()
        durable = self.live._read("MEMO_PATH")
        self.assertEqual(durable[key], marker)
        self.live.memo.clear()
        self.live.memo.update(copy.deepcopy(durable))
        self.assertIsNone(self.acknowledge())
        self.assertNotIn(key, self.assert_final())

    def test_unpublished_nonempty_closure_refuses_instead_of_mutating_after_live(self):
        self.commit_incomplete_live(self.producer._capture())
        closure = self.batch["event_closure"]
        self.assertIsNotNone(closure)
        missing = []
        for batch in closure["batches"]:
            for plan in batch["members"]:
                for page in plan["pages"]:
                    path = Path(self.source.lib.corpus_path(page["slug"]))
                    if not path.exists():
                        missing.append(path)
        self.assertTrue(missing,
                        "fixture unexpectedly published its frozen closure")
        self.assert_refused_without_effect(self.acknowledge)

    def test_published_nonempty_closure_without_exact_sync_still_refuses(self):
        batch = self.producer._capture()
        closure = batch["event_closure"]
        self.assertIsNotNone(closure)
        result = self.source.lib._publish_event_page_batch_closure(
            closure=closure,
            expected_closure_sha256=closure["closure_sha256"])
        self.assertEqual(result["status"], "page-bytes-published")
        self.commit_incomplete_live(batch)

        self.assert_refused_without_effect(self.acknowledge)


if __name__ == "__main__":
    unittest.main()
