"""Inert durable source-batch staging, using actual capture fixtures.

The fixture runs real private collectors and the existing page/intake pipeline.
Staging/readback must not recollect, rerender, publish corpus bytes, settle
refusals, acknowledge cursors, or claim that the live generation is available.
The fixed immutable slot is retained on every failure. A later explicit
acknowledgment/archive transition is outside this increment.
"""

import contextlib
import copy
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_source_capture as capture_tests


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


VIEW_KEYS = {"schema", "status", "batch", "receipt", "non_claims"}
RECEIPT_KEYS = {"schema", "epoch_id", "batch_id", "epoch_sha256",
                "batch_sha256", "batch_wire_sha256", "batch_bytes",
                "parent_batch_sha256"}


class ControllerSourcePublication(unittest.TestCase):
    def setUp(self):
        self.fixture = capture_tests.ControllerSourceCapture(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.memo = self.fixture.memo
        for name in ("_stage_controller_source_batch", "_read_pending_controller_source_batch"):
            self.assertTrue(callable(getattr(self.lib, name, None)),
                            "missing controller source durability API: " + name)
        self.assertTrue(hasattr(self.lib, "CONTROLLER_SOURCE_BATCH_PATH"))
        self.path = Path(self.lib.CONTROLLER_SOURCE_BATCH_PATH)
        self.memo_path = Path(self.lib.MEMO_PATH)
        self.batch = self.fixture.capture()

    @contextlib.contextmanager
    def inert(self):
        with contextlib.ExitStack() as stack:
            for name in ("_capture_controller_source_batch", "_prepare_event_page_plan",
                         "_compose_event_page_plans", "_compose_event_page_batch_closure",
                         "_publish_event_page_plan", "_publish_event_page_plan_batch", "_publish_event_page_batch_closure",
                         "update_day_page", "_commit_sense_cursors", "save_cursors",
                         "_settle_source_record_refusals", "_settle_source_entry_refusals",
                         "_settle_source_refusals", "_stage_live_generation",
                         "_publish_staged_live_generation", "export_status", "brain_sync", "gbrain", "gbrain_call"):
                stack.enter_context(mock.patch.object(
                    self.lib, name, side_effect=AssertionError("inert source stage invoked " + name)))
            yield

    def stage(self, batch=None, pin=None):
        batch = self.batch if batch is None else batch
        with self.inert():
            return self.lib._stage_controller_source_batch(
                memo=self.memo, batch=batch,
                expected_batch_sha256=batch["batch_sha256"] if pin is None else pin)

    def view(self):
        with self.inert():
            return self.lib._read_pending_controller_source_batch(memo=self.memo)

    def before(self):
        return {str(path): path.read_bytes() if path.exists() else None
                for path in (self.path, self.memo_path, Path(self.lib.CURSORS_PATH))}

    def assert_refusal(self, callback):
        with self.assertRaises((ValueError, RuntimeError)) as caught:
            callback()
        self.assertTrue(getattr(caught.exception, "non_claims", None))
        return caught.exception

    def assert_view(self, view, status):
        self.assertEqual(set(view), VIEW_KEYS)
        self.assertEqual(view["schema"], "sia-controller-source-batch-view-v1")
        self.assertEqual(view["status"], status)
        self.assertTrue(view["non_claims"])
        if status == "absent":
            self.assertIsNone(view["batch"])
            self.assertIsNone(view["receipt"])
            return
        self.assertEqual(canonical(view["batch"]), canonical(self.batch))
        receipt = view["receipt"]
        self.assertEqual(set(receipt), RECEIPT_KEYS)
        self.assertEqual(receipt["schema"], "sia-controller-source-pending-v1")
        self.assertEqual(receipt["batch_sha256"], self.batch["batch_sha256"])
        self.assertEqual(receipt["batch_wire_sha256"], digest(self.batch))
        self.assertEqual(receipt["batch_bytes"], len(canonical(self.batch)))
        self.assertEqual(receipt["epoch_id"], self.batch["epoch"]["epoch_id"])
        self.assertEqual(receipt["epoch_sha256"], self.batch["epoch_sha256"])
        self.assertEqual(receipt["batch_id"], self.batch["batch_id"])
        predecessor = self.batch["epoch"]["predecessor"]
        self.assertEqual(receipt["parent_batch_sha256"],
                         None if predecessor is None else predecessor["source_batch_sha256"])

    def test_exact_keyword_only_apis(self):
        for name, expected in {
                "_stage_controller_source_batch": ("memo", "batch", "expected_batch_sha256"),
                "_read_pending_controller_source_batch": ("memo",)}.items():
            parameters = inspect.signature(getattr(self.lib, name)).parameters
            self.assertEqual(tuple(parameters), expected)
            for parameter in parameters.values():
                self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(parameter.default, inspect.Parameter.empty)

    def test_empty_slot_is_absence_without_writes(self):
        before = self.before()
        self.assert_view(self.view(), "absent")
        self.assertEqual(self.before(), before)

    def test_stage_exact_bytes_then_compact_pointer_and_detached_readback(self):
        original = canonical(self.batch)
        corpus_before = self.fixture.pages.snapshot()
        cursors_before = Path(self.lib.CURSORS_PATH).read_bytes()
        self.assertIsNone(self.stage())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        durable = json.loads(self.memo_path.read_bytes())
        self.assertEqual(canonical(durable), canonical(self.memo))
        self.assertNotIn("ready", self.memo)
        self.assertIn("controller_source_pending", self.memo)
        view = self.view()
        self.assert_view(view, "pending")
        view["batch"]["non_claims"].append("caller mutation")
        view["receipt"]["batch_id"] = "caller mutation"
        self.assert_view(self.view(), "pending")
        self.assertEqual(canonical(self.batch), original)
        self.assertEqual(self.fixture.pages.snapshot(), corpus_before)
        self.assertEqual(Path(self.lib.CURSORS_PATH).read_bytes(), cursors_before)

    def test_exact_stage_retry_keeps_batch_inode_and_bytes(self):
        self.stage()
        generation = self.path.stat()
        original = self.path.read_bytes()
        self.stage()
        after = self.path.stat()
        self.assertEqual((after.st_dev, after.st_ino),
                         (generation.st_dev, generation.st_ino))
        self.assertEqual(self.path.read_bytes(), original)
        self.assert_view(self.view(), "pending")

    def test_bad_pin_and_changed_durable_memo_refuse_before_slot_write(self):
        before = self.before()
        self.assert_refusal(lambda: self.stage(pin="0" * 64))
        self.assertEqual(self.before(), before)
        self.memo["unpublished-caller-change"] = True
        self.assert_refusal(self.stage)
        self.assertEqual(self.before(), before)

    def test_published_batch_memo_failure_is_orphan_and_exact_retry_recovers(self):
        original_write = self.lib.atomic_write
        original_memo = canonical(self.memo)

        def fail_memo(path, data, **kwargs):
            if str(path) == str(self.memo_path):
                self.assertEqual(self.path.read_bytes(), canonical(self.batch))
                raise OSError("private injected memo publication failure")
            return original_write(path, data, **kwargs)

        with mock.patch.object(self.lib, "atomic_write", side_effect=fail_memo):
            with self.assertRaises((OSError, ValueError, RuntimeError)):
                self.stage()
        self.assertEqual(canonical(self.memo), original_memo)
        self.assertEqual(self.path.read_bytes(), canonical(self.batch))
        self.assert_refusal(self.view)
        self.assert_refusal(self.fixture.capture)
        self.stage()
        self.assert_view(self.view(), "pending")

    def test_different_coherently_rehashed_batch_cannot_replace_slot(self):
        self.stage()
        before = self.before()
        changed = copy.deepcopy(self.batch)
        changed["non_claims"].append("additional caller text")
        changed["batch_sha256"] = digest({key: value for key, value in changed.items()
                                          if key != "batch_sha256"})
        self.assert_refusal(lambda: self.stage(changed))
        self.assertEqual(self.before(), before)

    def test_pending_capture_refuses_without_fresh_collector(self):
        self.stage()
        before = self.before()
        with mock.patch.object(self.lib, "sense_custom",
                               side_effect=AssertionError("pending batch recollected")):
            self.assert_refusal(self.fixture.capture)
        self.assertEqual(self.before(), before)

    def test_retained_read_and_retry_do_not_adopt_current_configuration(self):
        self.stage()
        with mock.patch.object(self.lib, "CONFIG", {"changed-after-capture": True}), \
                mock.patch.object(self.lib, "CONFIG_ERRORS", ["current configuration error"]), \
                mock.patch.object(self.lib, "load_config",
                                  side_effect=AssertionError("retained batch reloaded config")):
            self.assert_view(self.view(), "pending")
            self.stage()
        self.assert_view(self.view(), "pending")

    def test_pending_receipt_tampering_is_not_absence(self):
        self.stage()
        self.memo["controller_source_pending"]["batch_wire_sha256"] = "0" * 64
        self.lib._write_memo(self.memo)
        self.assert_refusal(self.view)

    def test_whole_native_memo_capacity_refuses_before_batch_write(self):
        before = self.before()
        with mock.patch.object(self.lib, "MAX_MEMO_BYTES", len(self.memo_path.read_bytes())):
            self.assert_refusal(self.stage)
        self.assertEqual(self.before(), before)

    def test_pending_readiness_and_legacy_pulse_refuse_before_later_runtime(self):
        self.stage()
        with mock.patch.object(self.lib, "_read_committed_live_generation",
                               side_effect=AssertionError("pending source crossed live readiness")):
            ready, reason = self.lib.memory_readiness()
        self.assertIs(ready, False)
        self.assertIn("source", reason)
        with mock.patch.object(self.lib, "load_cursors",
                               side_effect=AssertionError("legacy pulse consumed pending source")), \
                mock.patch.object(self.lib, "load_thoughts",
                                  side_effect=AssertionError("legacy pulse loaded thoughts")):
            self.assert_refusal(lambda: self.lib._pulse_transaction_guarded(
                self.memo.get("pulse_seq", 0), {}, self.memo))

    def test_changed_live_policy_preserves_and_retires_unpublished_batch(self):
        """A now-impossible batch is evidence, not an eternal write lock."""
        self.stage()
        old_raw = self.path.read_bytes()
        old_receipt = copy.deepcopy(self.memo["controller_source_pending"])
        corpus_before = self.fixture.pages.snapshot()
        cursors_before = Path(self.lib.CURSORS_PATH).read_bytes()
        replacement = copy.deepcopy(self.batch["epoch"]["live_policy"])
        replacement["workspace"]["max_content_bytes"] += 1
        replacement_pin = digest(replacement)

        supersede = getattr(
            self.lib, "_supersede_controller_source_policy", None)
        self.assertTrue(callable(supersede),
                        "missing durable controller-source policy supersession API")
        result = supersede(
            memo=self.memo, replacement_live_policy=replacement,
            expected_replacement_live_policy_sha256=replacement_pin)

        self.assertEqual(result["status"], "preserved-not-published")
        self.assertEqual(result["old_live_policy_sha256"],
                         self.batch["epoch"]["expected_live_policy_sha256"])
        self.assertEqual(result["replacement_live_policy_sha256"], replacement_pin)
        self.assertFalse(self.path.exists())
        directory = self.path.parent / "controller-source-superseded"
        archived = directory / (self.batch["batch_sha256"] + ".batch.json")
        receipt = directory / (self.batch["batch_sha256"] + ".receipt.json")
        self.assertEqual(archived.read_bytes(), old_raw)
        self.assertEqual(archived.stat().st_mode & 0o777, 0o600)
        self.assertTrue(receipt.is_file())
        durable = json.loads(self.memo_path.read_bytes())
        self.assertEqual(canonical(durable), canonical(self.memo))
        self.assertNotIn("controller_source_pending", durable)
        marker = durable["controller_source_superseded"]
        self.assertEqual(marker["receipt_sha256"], result["receipt_sha256"])
        self.assertEqual(result["source_pending_receipt"], old_receipt)
        self.assertEqual(self.fixture.pages.snapshot(), corpus_before)
        self.assertEqual(Path(self.lib.CURSORS_PATH).read_bytes(), cursors_before)
        self.assert_view(self.view(), "absent")

    def test_policy_supersession_recovers_each_durable_cut(self):
        for cut in ("archive-durable", "receipt-durable"):
            with self.subTest(cut=cut):
                self.doCleanups()
                self.setUp()
                self.stage()
                replacement = copy.deepcopy(
                    self.batch["epoch"]["live_policy"])
                replacement["workspace"]["max_content_bytes"] += 1
                replacement_pin = digest(replacement)
                fired = False

                def boundary(stage):
                    nonlocal fired
                    if stage == cut and not fired:
                        fired = True
                        raise KeyboardInterrupt("fixture cut after " + stage)

                with mock.patch.object(
                        self.lib, "_controller_source_supersession_boundary",
                        side_effect=boundary), self.assertRaises(KeyboardInterrupt):
                    self.lib._supersede_controller_source_policy(
                        memo=self.memo, replacement_live_policy=replacement,
                        expected_replacement_live_policy_sha256=replacement_pin)
                self.memo.clear()
                self.memo.update(json.loads(self.memo_path.read_bytes()))
                result = self.lib._supersede_controller_source_policy(
                    memo=self.memo, replacement_live_policy=replacement,
                    expected_replacement_live_policy_sha256=replacement_pin)
                self.assertEqual(result["status"], "preserved-not-published")
                self.assertNotIn("controller_source_pending", self.memo)
                self.assertFalse(self.path.exists())

    def test_v3_runner_supersedes_old_policy_before_fresh_dispatch(self):
        self.stage()
        runner = importlib.import_module("siacontrollersourcerunner")
        delivery = importlib.import_module("siadelivery")
        epoch = importlib.import_module("siacontrollerepoch")
        loop = importlib.import_module("sialiveloop")
        self.assertNotEqual(
            self.batch["epoch"]["expected_live_policy_sha256"],
            epoch.EXPECTED_LIVE_POLICY_SHA256)
        sentinel = {"fresh": "dispatch"}

        def fresh(owner, *, operation):
            durable = owner["load_memo"]()
            self.assertNotIn("controller_source_pending", durable)
            self.assertIn("controller_source_superseded", durable)
            self.assertFalse(self.path.exists())
            self.assertIs(operation, initial)
            return sentinel

        initial = mock.Mock(side_effect=AssertionError(
            "supersession probe must not sample the new epoch clock"))
        limits = copy.deepcopy(delivery._LIMITS)
        with mock.patch.object(runner, "run", side_effect=fresh) as dispatched:
            result = self.lib._run_controller_source_transaction_v3(
                operation=initial, clock=mock.Mock(), journal_limits=limits,
                expected_journal_limits_sha256=loop._sha(limits),
                expected_adoption_sha256=None)
        self.assertIs(result, sentinel)
        dispatched.assert_called_once()
        initial.assert_not_called()

    def test_v3_runner_keeps_same_policy_pending_transaction(self):
        runner = importlib.import_module("siacontrollersourcerunner")
        delivery = importlib.import_module("siadelivery")
        epoch = importlib.import_module("siacontrollerepoch")
        loop = importlib.import_module("sialiveloop")
        self.fixture.policy = copy.deepcopy(epoch.LIVE_POLICY)
        self.fixture.epoch["live_policy"] = copy.deepcopy(epoch.LIVE_POLICY)
        self.fixture.profile["live_policy_sha256"] = \
            epoch.EXPECTED_LIVE_POLICY_SHA256
        self.fixture.epoch["profile"] = copy.deepcopy(self.fixture.profile)
        self.fixture.reseal_epoch()
        self.batch = self.fixture.capture()
        self.stage()
        sentinel = {"same": "policy"}
        limits = copy.deepcopy(delivery._LIMITS)
        forbidden = mock.Mock(side_effect=AssertionError(
            "same-policy pending source was superseded"))
        with mock.patch.object(runner, "run", return_value=sentinel) as dispatched, \
                mock.patch.object(
                    self.lib, "_supersede_controller_source_policy", forbidden):
            result = self.lib._run_controller_source_transaction_v3(
                operation=mock.Mock(), clock=mock.Mock(), journal_limits=limits,
                expected_journal_limits_sha256=loop._sha(limits),
                expected_adoption_sha256=None)
        self.assertIs(result, sentinel)
        dispatched.assert_called_once()
        forbidden.assert_not_called()
        self.assertTrue(self.path.exists())
        self.assertIn("controller_source_pending", self.lib.load_memo())

    def test_v3_runner_recovers_after_supersession_memo_cut(self):
        self.stage()
        runner = importlib.import_module("siacontrollersourcerunner")
        delivery = importlib.import_module("siadelivery")
        loop = importlib.import_module("sialiveloop")
        limits = copy.deepcopy(delivery._LIMITS)

        def boundary(stage):
            if stage == "memo-durable":
                raise KeyboardInterrupt("fixture cut after memo-durable")

        arguments = {
            "operation": mock.Mock(), "clock": mock.Mock(),
            "journal_limits": limits,
            "expected_journal_limits_sha256": loop._sha(limits),
            "expected_adoption_sha256": None,
        }
        with mock.patch.object(
                self.lib, "_controller_source_supersession_boundary",
                side_effect=boundary), self.assertRaises(KeyboardInterrupt):
            self.lib._run_controller_source_transaction_v3(**arguments)
        self.memo.clear()
        self.memo.update(self.lib.load_memo())
        sentinel = {"recovered": "fresh"}
        with mock.patch.object(runner, "run", return_value=sentinel) as dispatched:
            result = self.lib._run_controller_source_transaction_v3(**arguments)
        self.assertIs(result, sentinel)
        dispatched.assert_called_once()
        self.assertNotIn("controller_source_pending", self.memo)
        self.assertIn("controller_source_superseded", self.memo)


if __name__ == "__main__":
    unittest.main()
