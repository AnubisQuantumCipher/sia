"""Source-bound delivery-epoch adoption against controlled source fixtures.

Ordinary bootstrap uses a genuinely acknowledged legacy source transaction
from the existing controlled local fixture; no resident source, real user
journal, engine, model, or live corpus is accessed.

Storage adoption is not writer authorization. An acknowledged source-v3 batch
must later retain the exact adoption pin before any new writer is admitted.
The adopted memo pin bridges a death before that first source-v3 WAL. A supplied
adoption pin is mandatory as a keyword and never grants permission to bootstrap
missing storage. Parent-v3 acquisition/consumption belongs to separate tests.

The immutable birth seed uses the actual stable predecessor, policy and limits,
not a newly allocated successor sequence or sampled time. Boundary callbacks
receive one literal phase after the named durability cut and before the next
effect. KeyboardInterrupt models process death, not a recoverable refusal.

Directory identities and limits are observed fixture values; digest comparison
is protocol binding, not a numeric metric or JACKAL assurance. These tests make
no claim about source truth, historical recall completeness, human receipt,
biological cognition, or a held-out retrieval win.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import contextlib
import copy
import importlib
import inspect
import json
import os
from pathlib import Path
import stat
import unittest
from unittest import mock

from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_idle as idle_tests
from tests import test_controller_source_rollover_storage as rollover_tests
from tests import test_live_loop as live_tests


ROOT_KEY = "CONTROLLER_DELIVERY_EPOCH_ROOT"
MARKER_KEY = "controller_delivery_epoch"
BOUNDARY_KEY = "_controller_delivery_epoch_boundary"
PHASES = (
    "birth-durable",
    "birth-pending",
    "records-directory-durable",
    "adoption-receipt-durable",
    "adoption-memo-durable",
)
RESULT_KEYS = {
    "schema", "status", "birth", "expected_birth_sha256", "adoption",
    "expected_adoption_sha256", "non_claims",
}
BIRTH_KEYS = {
    "schema", "status", "epoch_id", "started_at", "epoch_key_sha256",
    "bootstrap_parent", "policy_sha256", "limits", "limits_sha256",
    "non_claims", "birth_sha256",
}
ADOPTION_KEYS = {
    "schema", "status", "epoch_id", "started_at", "birth_sha256",
    "records_identity", "initial_journal_sha256", "non_claims",
    "adoption_sha256",
}
MARKER_KEYS = {
    "schema", "epoch_id", "started_at", "birth_sha256", "adoption_sha256",
}
NON_CLAIMS = [
    "Birth and adoption establish a bounded local storage transaction, not delivery, pulse consumption, source acknowledgment or writer authorization.",
    "New writers require a fully acknowledged source-v3 batch retaining this exact adoption; legacy source completion or an adopted memo marker alone cannot enable output recording.",
    "Bootstrap requires an acknowledged legacy parent with no prior live deliveries; no legacy touch history or missing journal records are reconstructed.",
    "Directory and file joins concern the checked local descriptor generations, not protection against hostile same-user mutation or complete historical recall.",
    "No output is emitted and no clock is sampled by adoption; no human receipt, JACKAL assurance, biological cognition or held-out retrieval win is established.",
    "All source, live-loop and delivery-journal nonclaims remain controlling.",
]


class _EpochDeath(KeyboardInterrupt):
    pass


def _sealed(value, field):
    return {**value, field: live_tests.digest(value)}


def _wire(value):
    return live_tests.canonical(value) + b"\n"


def _tree(path):
    path = Path(path)
    image = {".": ack_tests._path_image(path)}
    if path.is_dir() and not path.is_symlink():
        for child in sorted(path.rglob("*")):
            image[str(child.relative_to(path))] = ack_tests._path_image(child)
    return image


class ControllerDeliveryEpoch(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("siacontrollerdeliveryepoch")
        except ModuleNotFoundError as exc:
            self.fail("source-bound delivery epoch must exist: " + str(exc))
        self.assertTrue(callable(getattr(self.module, "prepare_epoch", None)))
        self.assertTrue(hasattr(self.module, "ControllerDeliveryEpochRefusal"))
        self.assertEqual(list(self.module.NON_CLAIMS), NON_CLAIMS)
        self.idle = idle_tests.ControllerSourceIdle(methodName="runTest")
        self.idle.setUp()
        self.addCleanup(self.idle.doCleanups)
        self.journal = importlib.import_module("siadelivery")
        self.live = importlib.import_module("sialiveloop")
        self.queue = importlib.import_module("siaqueue")
        self.limits = {
            "max_document_bytes": self.live.MAX_INPUT_BYTES,
            "max_body_bytes": self.live.MAX_CONTENT_BYTES,
            "max_pending_bytes": self.queue.MAX_PENDING_BYTES,
            "max_requests": self.queue.MAX_PENDING_REQUESTS,
            "max_scan_entries": self.queue.MAX_QUEUE_SCAN_ENTRIES,
        }

    @contextlib.contextmanager
    def completed(self):
        with self.idle.completed() as fixture:
            case, retained, committed, status, generation = fixture
            self.assertEqual(retained["schema"], "sia-controller-source-batch-v1")
            self.assertEqual(generation["transition"]["state"]["deliveries"]["records"], [])
            root = case.live.root / "controller-delivery-epochs"
            with mock.patch.object(case.lib, ROOT_KEY, str(root), create=True), \
                    mock.patch.object(case.lib, BOUNDARY_KEY, mock.Mock(), create=True):
                yield (*fixture, root)

    def paths(self, retained, root):
        epoch = retained["epoch"]
        key = live_tests.digest({
            "schema": "sia-controller-delivery-epoch-path-v1",
            "epoch_id": epoch["epoch_id"], "started_at": epoch["started_at"],
        })
        directory = root / key
        return key, directory, directory / "birth.json", directory / "adoption.json", directory / "records"

    def birth(self, retained, committed, generation):
        epoch = retained["epoch"]
        key = live_tests.digest({
            "schema": "sia-controller-delivery-epoch-path-v1",
            "epoch_id": epoch["epoch_id"], "started_at": epoch["started_at"],
        })
        return _sealed({
            "schema": "sia-controller-delivery-epoch-birth-v1",
            "status": "birth-pending", "epoch_id": epoch["epoch_id"],
            "started_at": epoch["started_at"], "epoch_key_sha256": key,
            "bootstrap_parent": {
                "source_batch_sha256": retained["batch_sha256"],
                "live_generation_sha256": committed["live_generation_sha256"],
                "state_sha256": generation["state_sha256"],
            },
            "policy_sha256": epoch["expected_live_policy_sha256"],
            "limits": copy.deepcopy(self.limits),
            "limits_sha256": live_tests.digest(self.limits),
            "non_claims": list(NON_CLAIMS),
        }, "birth_sha256")

    @staticmethod
    def marker(birth, adoption_sha256):
        return {
            "schema": "sia-controller-delivery-epoch-marker-v1",
            "epoch_id": birth["epoch_id"], "started_at": birth["started_at"],
            "birth_sha256": birth["birth_sha256"],
            "adoption_sha256": adoption_sha256,
        }

    def prepare(self, case, retained, committed, status, **changes):
        request = {
            "memo": case.live.memo, "admitted_status": status,
            "retained_batch": retained, "committed": committed,
            "journal_limits": self.limits,
            "expected_journal_limits_sha256": live_tests.digest(self.limits),
            "expected_adoption_sha256": None,
        }
        request.update(changes)
        with self.idle.source_owner(case), case.lib.brainstem_owner(), case.lib.corpus_owner():
            return self.module.prepare_epoch(case.lib.__dict__, **request)

    def refuse(self, case, retained, committed, status, **changes):
        with self.assertRaises(self.module.ControllerDeliveryEpochRefusal) as caught:
            self.prepare(case, retained, committed, status, **changes)
        self.assertRegex(caught.exception.reason, r"\A[a-z][a-z0-9-]*\Z")
        self.assertEqual(caught.exception.non_claims, NON_CLAIMS)
        return caught.exception

    @contextlib.contextmanager
    def no_new_work(self, case):
        with contextlib.ExitStack() as stack:
            blocked = []
            for owner, name in (
                    (self.journal, "reserve_delivery"),
                    (self.journal, "deliver_reserved"),
                    (self.idle.epoch, "build_successor"),
                    (case.lib, "_run_controller_source_cycle"),
                    (case.lib, "_controller_source_effects_observed_at"),
                    (case.lib, "_publish_staged_live_generation"),
                    (case.lib, "_stage_live_generation"),
                    (case.lib, "_publish_event_page_batch_closure"),
                    (case.lib, "save_cursors"),
                    (case.lib, "export_status"),
                    (case.lib, "export_graph")):
                operation = mock.Mock(side_effect=AssertionError("adoption crossed " + name))
                blocked.append(operation)
                stack.enter_context(mock.patch.object(owner, name, operation))
            clock = stack.enter_context(mock.patch("time.time", side_effect=AssertionError("adoption sampled clock")))
            yield
            clock.assert_not_called()
            for operation in blocked:
                operation.assert_not_called()

    def assert_adopted(self, case, retained, committed, generation, root, result):
        key, directory, birth_path, adoption_path, records = self.paths(retained, root)
        birth = self.birth(retained, committed, generation)
        self.assertEqual(set(result), RESULT_KEYS)
        self.assertEqual(result["schema"], "sia-controller-delivery-epoch-v1")
        self.assertEqual(result["status"], "adopted-not-enabled")
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertEqual(set(result["birth"]), BIRTH_KEYS)
        self.assertEqual(result["birth"], birth)
        self.assertEqual(result["expected_birth_sha256"], birth["birth_sha256"])
        self.assertEqual(key, birth["epoch_key_sha256"])
        info = os.lstat(records)
        self.assertTrue(stat.S_ISDIR(info.st_mode))
        self.assertEqual(stat.S_IMODE(info.st_mode), 0o700)
        self.assertEqual(info.st_uid, os.geteuid())
        self.assertEqual(list(records.iterdir()), [])
        empty = {
            "schema": "sia-live-delivery-journal-v1", "epoch_id": birth["epoch_id"],
            "complete": True, "records": [], "pending": [],
            "non_claims": list(self.journal.NON_CLAIMS),
        }
        adoption = _sealed({
            "schema": "sia-controller-delivery-epoch-adoption-v1",
            "status": "adopted-not-enabled", "epoch_id": birth["epoch_id"],
            "started_at": birth["started_at"], "birth_sha256": birth["birth_sha256"],
            "records_identity": {
                "dev": info.st_dev, "ino": info.st_ino, "mode": info.st_mode,
                "uid": info.st_uid, "gid": info.st_gid,
            },
            "initial_journal_sha256": live_tests.digest(empty),
            "non_claims": list(NON_CLAIMS),
        }, "adoption_sha256")
        self.assertEqual(set(result["adoption"]), ADOPTION_KEYS)
        self.assertEqual(result["adoption"], adoption)
        self.assertEqual(result["expected_adoption_sha256"], adoption["adoption_sha256"])
        for path, value in ((birth_path, birth), (adoption_path, adoption)):
            self.assertEqual(path.read_bytes(), _wire(value))
            file_info = os.lstat(path)
            self.assertTrue(stat.S_ISREG(file_info.st_mode))
            self.assertEqual(stat.S_IMODE(file_info.st_mode), 0o600)
            self.assertEqual(file_info.st_uid, os.geteuid())
            self.assertEqual(file_info.st_nlink, 1)
            self.assertEqual(path.parent, directory)
            self.assertNotEqual(path.parent, records)
        marker = self.marker(birth, adoption["adoption_sha256"])
        self.assertEqual(set(case.live.memo[MARKER_KEY]), MARKER_KEYS)
        self.assertEqual(case.live.memo[MARKER_KEY], marker)
        self.assertEqual(case.live._read("MEMO_PATH"), case.live.memo)
        self.assertEqual(case.live.memo["controller_source_committed"], committed)
        return birth, adoption

    def test_api_requires_external_adoption_pin_and_accepts_no_fresh_clock(self):
        signature = inspect.signature(self.module.prepare_epoch)
        self.assertEqual(set(signature.parameters), {
            "owner", "memo", "admitted_status", "retained_batch", "committed",
            "journal_limits", "expected_journal_limits_sha256", "expected_adoption_sha256",
        })
        self.assertEqual(signature.parameters["owner"].kind, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for name, parameter in signature.parameters.items():
            if name != "owner":
                self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(parameter.default, inspect.Parameter.empty)

    def test_acknowledged_legacy_bootstrap_is_exact_private_and_not_writer_enable(self):
        with self.completed() as (case, retained, committed, status, generation, root):
            before = case.images()
            old_memo = copy.deepcopy(case.live.memo)
            inputs = copy.deepcopy((retained, committed, status, generation, self.limits))
            with self.no_new_work(case):
                result = self.prepare(case, retained, committed, status)
            self.assert_adopted(case, retained, committed, generation, root, result)
            self.assertEqual((retained, committed, status, generation, self.limits), inputs)
            self.assertEqual({key: value for key, value in case.live.memo.items() if key != MARKER_KEY}, old_memo)
            self.assertEqual({key: value for key, value in case.images().items() if key != "memo"},
                             {key: value for key, value in before.items() if key != "memo"})
            self.assertEqual(getattr(case.lib, BOUNDARY_KEY).call_args_list,
                             [mock.call(phase) for phase in PHASES])
            disk = (_tree(root), ack_tests._path_image(case.live.paths["MEMO_PATH"]))
            original = copy.deepcopy(result)
            result["birth"]["limits"].clear()
            result["adoption"]["non_claims"].clear()
            with self.no_new_work(case):
                retried = self.prepare(case, retained, committed, status,
                                       expected_adoption_sha256=original["expected_adoption_sha256"])
            self.assertEqual(retried, original)
            self.assertEqual((_tree(root), ack_tests._path_image(case.live.paths["MEMO_PATH"])), disk)

    def test_actual_acknowledged_v2_parent_with_empty_deliveries_can_upgrade(self):
        from tests import test_controller_source_gist_receipt_integrity as receipt_tests

        helper = receipt_tests.ControllerSourceGistReceiptIntegrity(methodName="runTest")
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        with helper.transaction(complete=True, acknowledge=True) as fixture:
            case, retained, _transition, _pending, _receipt = fixture
            self.assertEqual(retained["schema"], "sia-controller-source-batch-v2")
            generation = copy.deepcopy(case.generation)
            self.assertEqual(generation["transition"]["state"]["deliveries"]["records"], [])
            committed = copy.deepcopy(case.live.memo["controller_source_committed"])
            status = case.admitted_status()
            root = case.live.root / "controller-delivery-epochs"
            with mock.patch.object(case.lib, ROOT_KEY, str(root), create=True), \
                    mock.patch.object(case.lib, BOUNDARY_KEY, mock.Mock(), create=True), \
                    self.no_new_work(case):
                result = self.prepare(case, retained, committed, status)
                self.assert_adopted(case, retained, committed, generation, root, result)

    def test_each_durable_cut_recovers_without_replacing_retained_objects(self):
        for phase in PHASES:
            with self.subTest(phase=phase), self.completed() as fixture:
                case, retained, committed, status, generation, root = fixture
                birth = self.birth(retained, committed, generation)
                _key, _directory, birth_path, adoption_path, records = self.paths(retained, root)

                def crash(observed):
                    self.assertIn(observed, PHASES)
                    if observed != phase:
                        return
                    self.assertEqual(birth_path.read_bytes(), _wire(birth))
                    durable = case.live._read("MEMO_PATH")
                    if observed == "birth-durable":
                        self.assertNotIn(MARKER_KEY, durable)
                    elif observed == "adoption-memo-durable":
                        adoption = json.loads(adoption_path.read_bytes())
                        self.assertEqual(durable[MARKER_KEY], self.marker(birth, adoption["adoption_sha256"]))
                    else:
                        self.assertEqual(durable[MARKER_KEY], self.marker(birth, None))
                    if observed in {"birth-durable", "birth-pending"}:
                        self.assertFalse(records.exists())
                    else:
                        self.assertEqual(list(records.iterdir()), [])
                    if observed in {"birth-durable", "birth-pending", "records-directory-durable"}:
                        self.assertFalse(adoption_path.exists())
                    raise _EpochDeath(observed)

                with mock.patch.object(case.lib, BOUNDARY_KEY, crash), self.no_new_work(case), \
                        self.assertRaises(_EpochDeath):
                    self.prepare(case, retained, committed, status)
                retained_files = {path: ack_tests._path_image(path)
                                  for path in (birth_path, adoption_path) if path.exists()}
                record_identity = None if not records.exists() else os.lstat(records)
                durable = case.live._read("MEMO_PATH")
                case.live.memo.clear()
                case.live.memo.update(durable)
                with self.no_new_work(case):
                    result = self.prepare(case, retained, committed, status)
                self.assert_adopted(case, retained, committed, generation, root, result)
                for path, observed_image in retained_files.items():
                    self.assertEqual(ack_tests._path_image(path), observed_image)
                if record_identity is not None:
                    self.assertEqual((os.lstat(records).st_dev, os.lstat(records).st_ino),
                                     (record_identity.st_dev, record_identity.st_ino))

    def test_adopted_legacy_gap_survives_a_new_reserved_sequence_without_rebirth(self):
        with self.completed() as (case, retained, committed, status, generation, root):
            original = self.prepare(case, retained, committed, status)
            retained_tree = _tree(root)
            case.live.memo["pulse_seq"] = rollover_tests.SUCCESSOR_SEQUENCE
            case.live._write(case.live.paths["MEMO_PATH"], case.live.memo)
            with self.no_new_work(case):
                result = self.prepare(case, retained, committed, status)
            self.assertEqual(result, original)
            self.assertEqual(_tree(root), retained_tree)
            self.assertEqual(case.live.memo["pulse_seq"], rollover_tests.SUCCESSOR_SEQUENCE)
            self.assertEqual(result["birth"], self.birth(retained, committed, generation))

    def _interrupt_memo_before_parent_fsync(
            self, case, retained, committed, status, *, adopted):
        """Exercise the real rename, then die before its directory flush."""
        memo_path = Path(case.live.paths["MEMO_PATH"])
        publish = self.queue.fixed_atomic_publish
        boundary = self.queue._publish_boundary
        death = _EpochDeath("memo-target-published-before-parent-fsync")

        def selected_publish(path, data, **kwargs):
            if Path(path) != memo_path:
                return publish(path, data, **kwargs)
            marker = json.loads(data)[MARKER_KEY]
            if (marker["adoption_sha256"] is not None) != adopted:
                return publish(path, data, **kwargs)

            def interrupt(phase):
                if phase == "target-published":
                    self.assertEqual(memo_path.read_bytes(), data)
                    raise death
                return boundary(phase)

            with mock.patch.object(self.queue, "_publish_boundary", interrupt):
                return publish(path, data, **kwargs)

        with mock.patch.object(self.queue, "fixed_atomic_publish", selected_publish), \
                self.no_new_work(case), self.assertRaises(_EpochDeath) as caught:
            self.prepare(case, retained, committed, status)
        self.assertIs(caught.exception, death)
        visible = case.live._read("MEMO_PATH")
        self.assertEqual((visible[MARKER_KEY]["adoption_sha256"] is not None), adopted)
        # This is fresh disk readback, not the still-stale caller dictionary.
        # Visibility here is deliberately not asserted to imply durability.
        case.live.memo.clear()
        case.live.memo.update(visible)

    @contextlib.contextmanager
    def _observe_memo_parent_fsync(self, memo_path):
        parent = os.lstat(Path(memo_path).parent)
        identity = (parent.st_dev, parent.st_ino)
        fsync = os.fsync
        synced = []

        def observe(descriptor):
            info = os.fstat(descriptor)
            result = fsync(descriptor)
            if stat.S_ISDIR(info.st_mode) \
                    and (info.st_dev, info.st_ino) == identity:
                synced.append(identity)
            return result

        with mock.patch.object(os, "fsync", observe):
            yield synced

    def test_pending_memo_rename_retry_syncs_parent_before_records_effect(self):
        with self.completed() as (case, retained, committed, status, generation, root):
            self._interrupt_memo_before_parent_fsync(
                case, retained, committed, status, adopted=False)
            _key, directory, birth_path, adoption_path, records = self.paths(retained, root)
            self.assertFalse(records.exists())
            self.assertFalse(adoption_path.exists())
            memo_path = case.live.paths["MEMO_PATH"]
            memo_image = ack_tests._path_image(memo_path)
            birth_image = ack_tests._path_image(birth_path)
            epoch = os.lstat(directory)
            epoch_identity = (epoch.st_dev, epoch.st_ino)
            mkdir = os.mkdir
            records_effect = []

            def ordered_mkdir(path, *args, dir_fd=None, **kwargs):
                if os.fspath(path) == "records" and dir_fd is not None:
                    parent = os.fstat(dir_fd)
                    if (parent.st_dev, parent.st_ino) == epoch_identity:
                        self.assertTrue(
                            synced,
                            "pending memo parent must be fsynced before records creation")
                        self.assertEqual(ack_tests._path_image(memo_path), memo_image)
                        self.assertEqual(ack_tests._path_image(birth_path), birth_image)
                        records_effect.append("records")
                return mkdir(path, *args, dir_fd=dir_fd, **kwargs)

            # Acquire ordinary fixture/front-door leases before observing the
            # retry, so setup cannot stand in for the memo persistence step.
            with self.idle.source_owner(case), case.lib.brainstem_owner(), \
                    case.lib.corpus_owner(), self.no_new_work(case), \
                    self._observe_memo_parent_fsync(memo_path) as synced, \
                    mock.patch.object(os, "mkdir", ordered_mkdir):
                result = self.prepare(case, retained, committed, status)
            self.assertEqual(records_effect, ["records"])
            self.assertEqual(ack_tests._path_image(birth_path), birth_image)
            self.assert_adopted(case, retained, committed, generation, root, result)

    def test_adopted_memo_rename_retry_syncs_parent_without_replacement(self):
        with self.completed() as (case, retained, committed, status, generation, root):
            self._interrupt_memo_before_parent_fsync(
                case, retained, committed, status, adopted=True)
            memo_path = case.live.paths["MEMO_PATH"]
            retained_disk = (_tree(root), ack_tests._path_image(memo_path))
            marker = copy.deepcopy(case.live.memo[MARKER_KEY])
            publication = mock.Mock(
                side_effect=AssertionError("adopted retry replaced a retained publication"))
            with self.idle.source_owner(case), case.lib.brainstem_owner(), \
                    case.lib.corpus_owner(), self.no_new_work(case), \
                    self._observe_memo_parent_fsync(memo_path) as synced, \
                    mock.patch.object(self.queue, "fixed_atomic_publish", publication):
                result = self.prepare(
                    case, retained, committed, status,
                    expected_adoption_sha256=marker["adoption_sha256"])
                self.assertTrue(
                    synced,
                    "adopted memo parent must be fsynced before a successful retry returns")
            publication.assert_not_called()
            self.assertEqual((_tree(root), ack_tests._path_image(memo_path)), retained_disk)
            self.assert_adopted(case, retained, committed, generation, root, result)

    def test_nonnull_external_pin_cannot_bootstrap_absent_epoch_storage(self):
        with self.completed() as (case, retained, committed, status, _generation, root):
            before = (case.images(), _tree(root))
            with self.no_new_work(case):
                self.refuse(case, retained, committed, status,
                            expected_adoption_sha256=live_tests.digest("externally-retained-adoption"))
            self.assertEqual((case.images(), _tree(root)), before)

    def _assert_derived_path_capacity_refuses_before_effects(self, stage):
        with self.completed() as (case, retained, committed, status, _generation, _root):
            # Keep every configured authority path and existing source archive
            # within the reduced limit. The only overlong paths are prospective
            # epoch storage, not a source-reader setup failure. Fixed short
            # padding components avoid relying on filesystem basename capacity.
            configured = [getattr(case.lib, name) for name in (
                "MEMO_PATH", "STATUS_PATH", "GRAPH_PATH", "LIVE_STATE_PATH",
                "LIVE_CANDIDATE_PATH", "CONTROLLER_SOURCE_BATCH_PATH",
                "CONTROLLER_SOURCE_ARCHIVE_DIR", "CONTROLLER_SOURCE_EFFECTS_ARCHIVE_DIR",
                "CORPUS", "STATE", "SHARE")]
            configured.extend((str(case.archive_path()), str(case.effects_archive_path())))
            pending = [retained]
            while pending:
                value = pending.pop()
                if type(value) is dict:
                    pending.extend(value.values())
                elif type(value) is list:
                    pending.extend(value)
                elif type(value) is str and os.path.isabs(value):
                    configured.append(value)
            existing_longest = max(map(len, configured))
            parent = case.live.root / "derived-path-capacity-fixture"
            while len(str(parent / "epochs")) <= existing_longest:
                parent = parent / "bounded-path-padding"
            parent.mkdir(parents=True, mode=0o700)
            root = parent / "epochs"
            _key, epoch, birth, adoption, records = self.paths(retained, root)
            if stage == "epoch":
                limit = len(str(root))
                self.assertGreater(len(str(epoch)), limit)
            else:
                self.assertEqual(stage, "documents")
                limit = len(str(epoch))
                self.assertLessEqual(len(str(epoch)), limit)
                for path in (birth, adoption, records):
                    self.assertGreater(len(str(path)), limit)
            for path in (*configured, str(root)):
                self.assertLessEqual(len(path), limit)
            boundary = mock.Mock()
            before = (case.images(), _tree(parent), copy.deepcopy(case.live.memo))
            with mock.patch.object(case.lib, ROOT_KEY, str(root)), \
                    mock.patch.object(case.lib, "MAX_CONFIG_PATH_CHARS", limit), \
                    mock.patch.object(case.lib, BOUNDARY_KEY, boundary), \
                    self.no_new_work(case):
                self.refuse(case, retained, committed, status)
            boundary.assert_not_called()
            self.assertEqual((case.images(), _tree(parent), case.live.memo), before)
            self.assertFalse(root.exists())

    def test_derived_epoch_path_capacity_refuses_before_any_directory_creation(self):
        self._assert_derived_path_capacity_refuses_before_effects("epoch")

    def test_derived_document_paths_capacity_refuses_before_any_directory_creation(self):
        self._assert_derived_path_capacity_refuses_before_effects("documents")

    def test_missing_adopted_file_or_records_directory_never_recreates_history(self):
        with self.completed() as (case, retained, committed, status, generation, root):
            result = self.prepare(case, retained, committed, status)
            _key, _directory, birth_path, adoption_path, records = self.paths(retained, root)
            for target in (birth_path, adoption_path, records):
                with self.subTest(missing=target.name):
                    saved = root.parent / ("held-delivery-epoch-" + target.name)
                    target.rename(saved)
                    try:
                        before = (case.images(), _tree(root))
                        self.refuse(case, retained, committed, status,
                                    expected_adoption_sha256=result["expected_adoption_sha256"])
                        self.assertFalse(target.exists())
                        self.assertEqual((case.images(), _tree(root)), before)
                    finally:
                        saved.rename(target)
            self.assert_adopted(case, retained, committed, generation, root, result)

    def test_erased_memo_and_adoption_cannot_fall_back_when_external_pin_is_present(self):
        with self.completed() as (case, retained, committed, status, _generation, root):
            result = self.prepare(case, retained, committed, status)
            _key, _directory, _birth_path, adoption_path, _records = self.paths(retained, root)
            adoption_path.rename(root.parent / "held-erased-adoption.json")
            case.live.memo.pop(MARKER_KEY)
            case.live._write(case.live.paths["MEMO_PATH"], case.live.memo)
            before = (case.images(), _tree(root))
            self.refuse(case, retained, committed, status,
                        expected_adoption_sha256=result["expected_adoption_sha256"])
            self.assertEqual((case.images(), _tree(root)), before)

    def test_replaced_empty_records_directory_refuses_its_new_identity(self):
        with self.completed() as (case, retained, committed, status, _generation, root):
            result = self.prepare(case, retained, committed, status)
            _key, _directory, _birth_path, _adoption_path, records = self.paths(retained, root)
            records.rename(root.parent / "held-original-records")
            records.mkdir(mode=0o700)
            before = (case.images(), _tree(root))
            self.refuse(case, retained, committed, status,
                        expected_adoption_sha256=result["expected_adoption_sha256"])
            self.assertEqual((case.images(), _tree(root)), before)

    def test_existing_unadmitted_records_are_not_bootstrapped_as_an_empty_journal(self):
        with self.completed() as (case, retained, committed, status, _generation, root):
            _key, directory, _birth_path, _adoption_path, records = self.paths(retained, root)
            root.mkdir(mode=0o700)
            directory.mkdir(mode=0o700)
            records.mkdir(mode=0o700)
            sentinel = records / "unadmitted-record.json"
            sentinel.write_bytes(b"retained unknown history\n")
            sentinel.chmod(0o600)
            before = (case.images(), _tree(root))
            self.refuse(case, retained, committed, status)
            self.assertEqual((case.images(), _tree(root)), before)

    def test_adopted_but_not_v3_committed_epoch_cannot_admit_nonempty_records(self):
        with self.completed() as (case, retained, committed, status, _generation, root):
            result = self.prepare(case, retained, committed, status)
            _key, _directory, _birth_path, _adoption_path, records = self.paths(retained, root)
            sentinel = records / "unexpected-pre-v3-output.json"
            sentinel.write_bytes(b"not authorized by source-v3\n")
            sentinel.chmod(0o600)
            before = (case.images(), _tree(root))
            self.refuse(case, retained, committed, status,
                        expected_adoption_sha256=result["expected_adoption_sha256"])
            self.assertEqual((case.images(), _tree(root)), before)

    def test_external_pin_and_limits_drift_refuse_before_effects(self):
        with self.completed() as (case, retained, committed, status, _generation, root):
            result = self.prepare(case, retained, committed, status)
            bad_limits = {**self.limits, "max_requests": True}
            changes = (
                {"expected_adoption_sha256": live_tests.digest("foreign-adoption")},
                {"expected_journal_limits_sha256": live_tests.digest("foreign-limits")},
                {"journal_limits": bad_limits,
                 "expected_journal_limits_sha256": live_tests.digest(bad_limits)},
            )
            for change in changes:
                with self.subTest(change=change):
                    before = (case.images(), _tree(root))
                    self.refuse(case, retained, committed, status,
                                **{"expected_adoption_sha256": result["expected_adoption_sha256"], **change})
                    self.assertEqual((case.images(), _tree(root)), before)

    def test_actual_completed_source_archive_is_required_not_only_caller_pins(self):
        with self.completed() as (case, retained, committed, status, _generation, root):
            case.archive_path().rename(root.parent / "held-source-archive.json")
            before = (case.images(), _tree(root))
            with self.no_new_work(case):
                self.refuse(case, retained, committed, status)
            self.assertEqual((case.images(), _tree(root)), before)

    def test_orphan_successor_slot_prevents_new_birth_without_attempting_recovery(self):
        with self.completed() as (case, retained, committed, status, _generation, root):
            self.assertFalse(case.producer.source_path.exists())
            case.producer.source_path.write_bytes(b"retained successor WAL must be handled by source runner\n")
            case.producer.source_path.chmod(0o600)
            before = (case.images(), _tree(root))
            with self.no_new_work(case):
                self.refuse(case, retained, committed, status)
            self.assertEqual((case.images(), _tree(root)), before)

    def test_changed_bootstrap_input_at_pending_boundary_refuses_before_records_mkdir(self):
        with self.completed() as (case, retained, committed, status, _generation, root):
            _key, _directory, _birth_path, adoption_path, records = self.paths(retained, root)

            def mutate(phase):
                if phase == "birth-pending":
                    retained["non_claims"].clear()

            with mock.patch.object(case.lib, BOUNDARY_KEY, mutate):
                self.refuse(case, retained, committed, status)
            self.assertFalse(records.exists())
            self.assertFalse(adoption_path.exists())
            self.assertIsNone(case.live._read("MEMO_PATH")[MARKER_KEY]["adoption_sha256"])

    def test_epoch_parent_swap_at_pending_boundary_cannot_redirect_records_creation(self):
        with self.completed() as (case, retained, committed, status, _generation, root):
            _key, directory, _birth_path, _adoption_path, _records = self.paths(retained, root)
            foreign = root.parent / "foreign-epoch-parent"
            foreign.mkdir(mode=0o700)
            foreign_before = _tree(foreign)

            def swap(phase):
                if phase == "birth-pending":
                    directory.rename(root.parent / "held-epoch-parent")
                    directory.symlink_to(foreign, target_is_directory=True)

            with mock.patch.object(case.lib, BOUNDARY_KEY, swap):
                self.refuse(case, retained, committed, status)
            self.assertEqual(_tree(foreign), foreign_before)
            self.assertFalse((foreign / "records").exists())
            self.assertIsNone(case.live._read("MEMO_PATH")[MARKER_KEY]["adoption_sha256"])


if __name__ == "__main__":
    unittest.main()
