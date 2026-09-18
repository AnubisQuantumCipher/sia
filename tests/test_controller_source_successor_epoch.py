"""Fail-closed contract for a production controller-source successor epoch.

The retained batch comes through the real capture front door.  The successor
builder must validate that immutable evidence, append its return exactly once,
and return detached kwargs for the next capture without invoking a collector
or changing controller state.  The compact committed marker is supplied local
authority; these tests do not claim that three digests alone prove publication,
external delivery, source truth, or complete pre-epoch machine history.
"""

import contextlib
import copy
import functools
import importlib
import inspect
from pathlib import Path
import sys
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "bin"))

from tests import test_controller_source_capture as capture_tests
from tests import test_live_loop as live_tests


COMMITTED_KEYS = {
    "source_batch_sha256", "live_generation_sha256",
    "source_effects_receipt_sha256",
}


class SuccessorControllerSourceEpoch(unittest.TestCase):
    def setUp(self):
        try:
            self.component = importlib.import_module("siacontrollerepoch")
        except ModuleNotFoundError as exc:
            self.fail("production controller epoch builder must exist: " + str(exc))
        self.source = importlib.import_module("siasourcebatch")

    @contextlib.contextmanager
    def captured(self, *, empty_only=False):
        case = capture_tests.ControllerSourceCapture(methodName="runTest")
        try:
            case.setUp()
            case.policy = copy.deepcopy(self.component.LIVE_POLICY)
            case.profile["live_policy_sha256"] = capture_tests.digest(
                case.policy)
            case.epoch.update(
                profile=case.profile, live_policy=case.policy)
            case.reseal_epoch()
            if empty_only:
                selected = [case.custom_entries[-1]]
                disabled = sorted(
                    set(case.lib.BASE_ORGANS) | set(case.lib.OPTIONAL_ORGANS))
                case.install_config({
                    "senses": {"disable": disabled},
                    "custom_senses": selected,
                })
                case.configure_selection([], selected)
            batch = case.capture()
            case.assert_batch(batch)
            case.calls.clear()
            yield case, batch
        finally:
            case.doCleanups()

    @staticmethod
    def committed(batch):
        return {
            "source_batch_sha256": batch["batch_sha256"],
            "live_generation_sha256": "9" * 64,
            "source_effects_receipt_sha256": "a" * 64,
        }

    @staticmethod
    def history_entry(batch):
        batches = ([] if batch["event_closure"] is None
                   else batch["event_closure"]["batches"])
        return {
            "source_returns": copy.deepcopy(batch["source_returns"]),
            "expected_source_returns_sha256":
                batch["source_returns"]["returns_sha256"],
            "event_batches": [
                {
                    "batch": copy.deepcopy(member),
                    "expected_batch_sha256": member["batch_sha256"],
                }
                for member in batches
            ],
        }

    @contextlib.contextmanager
    def collectors_forbidden(self, case):
        original_native = case.lib.sense_aegis
        original_custom = case.lib.sense_custom

        @functools.wraps(original_native)
        def native(*_args, **_kwargs):
            raise AssertionError("successor construction invoked a native collector")

        @functools.wraps(original_custom)
        def custom(*_args, **_kwargs):
            raise AssertionError("successor construction invoked the custom collector")

        with mock.patch.object(case.lib, "sense_aegis", native), \
                mock.patch.object(case.lib, "sense_custom", custom), \
                mock.patch.object(case.lib, "SENSES", [native, custom]), \
                mock.patch.object(
                    case.lib, "_verified_builtin_attest_rows",
                    side_effect=AssertionError(
                        "successor construction reached native acquisition")), \
                mock.patch.object(
                    case.lib, "_open_source_nofollow",
                    side_effect=AssertionError(
                        "successor construction reached custom acquisition")):
            yield

    def build(self, case, batch, committed=None, *,
              observed_at=live_tests.EXPIRED_AT):
        marker = self.committed(batch) if committed is None else committed
        before = case.inert_before()
        with self.collectors_forbidden(case):
            result = self.component.build_successor(
                case.lib.__dict__, retained_batch=batch,
                committed=marker, observed_at=observed_at)
        case.assert_inert(before)
        return result

    def assert_refusal(self, case, batch, reason, *, committed=None,
                       observed_at=live_tests.EXPIRED_AT):
        marker = self.committed(batch) if committed is None else committed
        batch_before = capture_tests.canonical(batch)
        marker_before = capture_tests.canonical(marker)
        config_before = capture_tests.canonical(case.lib.CONFIG)
        before = case.inert_before()
        with self.collectors_forbidden(case), \
                self.assertRaises(
                    self.component.ControllerEpochRefusal) as caught:
            self.component.build_successor(
                case.lib.__dict__, retained_batch=batch,
                committed=marker, observed_at=observed_at)
        self.assertEqual(caught.exception.reason, reason)
        self.assertTrue(caught.exception.non_claims)
        self.assertEqual(capture_tests.canonical(batch), batch_before)
        self.assertEqual(capture_tests.canonical(marker), marker_before)
        self.assertEqual(capture_tests.canonical(case.lib.CONFIG), config_before)
        case.assert_inert(before)
        return caught.exception

    def reseal_batch(self, case, batch):
        batch["epoch"]["expected_history_sha256"] = \
            self.source._component_sha(
                case.lib.__dict__, batch["epoch"]["history"])
        batch["epoch_sha256"] = self.source.native_sha(
            case.lib.__dict__, batch["epoch"])
        batch["batch_sha256"] = self.source.native_sha(
            case.lib.__dict__, {
                key: value for key, value in batch.items()
                if key != "batch_sha256"
            })

    def seed_prior_empty_return(self, case, batch):
        prior = copy.deepcopy(batch["source_returns"])
        prior["batch_id"] = "fixture-prior-source-batch"
        prior["observed_at"] = batch["epoch"]["started_at"]
        prior["runs"] = [
            {"source_id": run["source_id"], "events": []}
            for run in prior["runs"]
        ]
        prior["returns_sha256"] = self.source._component_sha(
            case.lib.__dict__, {
                key: value for key, value in prior.items()
                if key != "returns_sha256"
            })
        batch["epoch"]["history"]["entries"] = [{
            "source_returns": prior,
            "expected_source_returns_sha256": prior["returns_sha256"],
            "event_batches": [],
        }]
        batch["intake_projection"] = case.bridge.project(
            case.assembled_request(batch))
        self.reseal_batch(case, batch)
        self.source.validate_batch(
            case.lib.__dict__, batch, batch["batch_sha256"])

    def test_exact_explicit_successor_api(self):
        builder = getattr(self.component, "build_successor", None)
        self.assertTrue(callable(builder),
                        "missing production successor epoch builder")
        parameters = inspect.signature(builder).parameters
        self.assertEqual(tuple(parameters), (
            "owner", "retained_batch", "committed", "observed_at"))
        self.assertEqual(parameters["owner"].kind,
                         inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for name in ("retained_batch", "committed", "observed_at"):
            self.assertEqual(parameters[name].kind,
                             inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameters[name].default, inspect.Parameter.empty)

    def test_appends_retained_batch_once_and_returns_capture_ready_epoch(self):
        with self.captured() as (case, batch):
            batch_before = copy.deepcopy(batch)
            marker = self.committed(batch)
            marker_before = copy.deepcopy(marker)
            self.assertEqual(set(marker), COMMITTED_KEYS)
            result = self.build(case, batch, marker)

            self.assertEqual(set(result), {
                "epoch", "expected_epoch_sha256", "observed_at"})
            self.assertEqual(result["observed_at"], live_tests.EXPIRED_AT)
            self.assertIs(type(result["observed_at"]), int)
            epoch = result["epoch"]
            self.assertEqual(epoch["epoch_id"],
                             batch["epoch"]["epoch_id"])
            self.assertEqual(epoch["started_at"],
                             batch["epoch"]["started_at"])
            expected_history = copy.deepcopy(batch["epoch"]["history"])
            expected_history["entries"].append(self.history_entry(batch))
            self.assertEqual(epoch["history"], expected_history)
            self.assertEqual(len(epoch["history"]["entries"]),
                             len(batch["epoch"]["history"]["entries"]) + 1)
            self.assertEqual(epoch["predecessor"], {
                "source_batch_sha256": batch["batch_sha256"],
                "live_generation_sha256":
                    marker["live_generation_sha256"],
            })
            for field in (
                    "configuration", "source_catalog", "profile"):
                self.assertEqual(epoch[field], batch["epoch"][field])
                self.assertIsNot(epoch[field], batch["epoch"][field])
            self.assertEqual(epoch["live_policy"],
                             self.component.LIVE_POLICY)
            self.assertIsNot(epoch["live_policy"],
                             self.component.LIVE_POLICY)
            for field in (
                    "configuration", "source_catalog", "profile",
                    "live_policy", "history"):
                self.assertEqual(
                    epoch["expected_" + field + "_sha256"],
                    self.source._component_sha(
                        case.lib.__dict__, epoch[field]))
            self.assertEqual(
                result["expected_epoch_sha256"],
                self.source.native_sha(case.lib.__dict__, epoch))
            self.source._validate_epoch(
                case.lib.__dict__, epoch,
                result["expected_epoch_sha256"],
                live_tests.EXPIRED_AT, initial=False)
            projection, custom_indexes, identities = \
                self.source._runtime_projection(case.lib.__dict__, epoch)
            self.assertTrue(projection["senses"])
            self.assertEqual(
                list(custom_indexes),
                [row["source_id"] for row in
                 epoch["source_catalog"]["sources"]
                 if row["collector"] == "sense_custom"])
            self.assertTrue(identities["senses"])
            self.assertEqual(batch, batch_before)
            self.assertEqual(marker, marker_before)

            epoch["history"]["entries"][0]["source_returns"][
                "batch_id"] = "mutated-detached-output"
            epoch["configuration"]["custom_collectors"][0][
                "description"] = "mutated-detached-output"
            epoch["predecessor"]["live_generation_sha256"] = "0" * 64
            self.assertEqual(batch, batch_before)
            self.assertEqual(marker, marker_before)

    def test_revalidates_retained_batch_pin_before_construction(self):
        with self.captured() as (case, batch):
            batch["status"] = "mutated-unvalidated-input"
            error = self.assert_refusal(
                case, batch, "source-batch-contract")
            self.assertEqual(error.upstream_reason,
                             "source-batch-contract")

    def test_rejects_noncompact_or_mismatched_commit(self):
        with self.captured() as (case, batch):
            foreign = self.committed(batch)
            foreign["foreign"] = "not-compact"
            self.assert_refusal(
                case, batch, "successor-commit-shape",
                committed=foreign)

            malformed = self.committed(batch)
            malformed["source_effects_receipt_sha256"] = "not-a-digest"
            self.assert_refusal(
                case, batch, "successor-commit-digest",
                committed=malformed)

            mismatch = self.committed(batch)
            mismatch["source_batch_sha256"] = "0" * 64
            self.assert_refusal(
                case, batch, "successor-commit-mismatch",
                committed=mismatch)

    def test_rejects_clock_and_predecessor_history_gaps(self):
        with self.captured() as (case, batch):
            self.assert_refusal(
                case, batch, "successor-clock-gap",
                observed_at=live_tests.START)

            gap = copy.deepcopy(batch)
            gap["epoch"]["predecessor"] = {
                "source_batch_sha256": "c" * 64,
                "live_generation_sha256": "d" * 64,
            }
            self.reseal_batch(case, gap)
            self.assert_refusal(
                case, gap, "successor-history-gap")

    def test_rejects_duplicate_current_return_in_prior_history(self):
        with self.captured() as (case, batch):
            duplicate = copy.deepcopy(batch)
            duplicate["epoch"]["history"]["entries"].append(
                self.history_entry(duplicate))
            self.reseal_batch(case, duplicate)
            self.assert_refusal(
                case, duplicate, "successor-history-duplicate")

    def test_rejects_history_capacity_before_appending(self):
        with self.captured(empty_only=True) as (case, batch):
            self.seed_prior_empty_return(case, batch)
            before = case.inert_before()
            with mock.patch.object(case.lib, "MAX_SOURCE_REPLAY_EVENTS", 1):
                self.assert_refusal(
                    case, batch, "successor-history-capacity")
            case.assert_inert(before)

    def test_rejects_valid_current_configuration_drift(self):
        with self.captured() as (case, batch):
            changed = copy.deepcopy(case.lib.CONFIG)
            changed["custom_senses"][0]["description"] = \
                "valid but different current source description"
            with mock.patch.object(case.lib, "CONFIG", changed):
                self.assert_refusal(
                    case, batch, "successor-configuration-drift")


if __name__ == "__main__":
    unittest.main()
