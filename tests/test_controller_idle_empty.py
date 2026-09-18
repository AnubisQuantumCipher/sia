"""An empty custom-source pulse is idle even without native gist support.

The custom lines come through the real collector/page/acknowledgment fixture.
No fake native capture, signed occurrence, replay exposure or cognitive win is
created. Root runs this module sequentially under the mission memory cap.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import contextlib
import copy
import importlib
import unittest
from unittest import mock

from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_capture as capture_tests
from tests import test_controller_source_idle as idle_tests
from tests import test_controller_source_rollover_storage as rollover_tests
from tests import test_live_loop as live_tests


WRAPPER_KEYS = {
    "idle_without_native", "expected_idle_without_native_sha256",
}
DOCUMENT_KEYS = {
    "schema", "availability", "epoch_id", "intake_sha256", "observed_at",
    "live_policy_sha256", "source_ids", "episodes", "non_claims",
}
RECEIPT_KEYS = {
    "schema", "status", "availability", "idle_without_native",
    "idle_without_native_sha256", "gist", "non_claims", "binding_sha256",
}
NON_CLAIMS = [
    "No selected controller source has a supported native gist binding; this does not establish that the machine has no native history.",
    "Controller episodes and their origins remain unchanged; no native occurrence, capture, replay exposure, gist candidate or consolidation is manufactured.",
    "An idle disposition is a local selection result, not source truth, publication, delivery, biological sleep or a cognitive win.",
]


class ControllerIdleWithoutNative(unittest.TestCase):
    def setUp(self):
        self.source_batch = importlib.import_module("siasourcebatch")
        self.live_input = importlib.import_module("siacontrollerliveinput")
        self.loop = importlib.import_module("sialiveloop")
        self.epoch = importlib.import_module("siacontrollerepoch")
        self.bench = importlib.import_module("siabench")
        self.gist = importlib.import_module("siagist")

    @contextlib.contextmanager
    def completed(self, *, empty=False):
        case = ack_tests.ControllerSourceAcknowledgment(methodName="runTest")
        try:
            case.setUp()
            idle_tests.ControllerSourceIdle._align_live_policy(case)
            selected = (case.source.custom_entries[-1:] if empty
                        else case.source.custom_entries)
            disabled = sorted(set(case.source.lib.BASE_ORGANS)
                              | set(case.source.lib.OPTIONAL_ORGANS))
            case.source.install_config({
                "senses": {"disable": disabled},
                "custom_senses": selected,
            })
            case.source.configure_selection([], selected)
            batch = case.source.capture()
            case.source.assert_batch(batch)
            case.commit_live(batch)
            self.assertIsNone(case.acknowledge())
            durable = case.assert_final()
            retained = copy.deepcopy(case.batch)
            committed = copy.deepcopy(durable["controller_source_committed"])
            generation = copy.deepcopy(case.generation)
            case.live.memo["pulse_seq"] = rollover_tests.SUCCESSOR_SEQUENCE
            case.live._write(case.live.paths["MEMO_PATH"], case.live.memo)
            yield case, retained, committed, generation
        finally:
            case.doCleanups()

    @contextlib.contextmanager
    def forbid_native(self, case):
        with contextlib.ExitStack() as stack:
            blocked = []
            for owner, name in (
                    (case.source.lib, "_chain_cmds"),
                    (self.bench, "capture_native_history"),
                    (self.bench, "capture_native_history_v2"),
                    (self.gist, "replay_gist")):
                operation = mock.Mock(side_effect=AssertionError(
                    "no-native idle crossed " + name))
                blocked.append(operation)
                stack.enter_context(mock.patch.object(owner, name, operation))
            yield blocked
            for operation in blocked:
                operation.assert_not_called()

    def successor(self, case, retained, committed):
        request = self.epoch.build_successor(
            case.source.lib.__dict__, retained_batch=retained,
            committed=committed,
            observed_at=rollover_tests.SUCCESSOR_OBSERVED_AT)
        with mock.patch.object(
                case.source.lib, "MEMO_PATH", case.live.paths["MEMO_PATH"]), \
                mock.patch.object(
                    case.source.lib, "CONTROLLER_SOURCE_BATCH_PATH",
                    str(case.producer.source_path)), \
                case.source.capture_boundary():
            return self.source_batch.capture_successor(
                case.source.lib.__dict__, memo=case.live.memo,
                retained_batch=retained, committed=committed, **request)

    def prepare(self, batch, generation):
        return self.live_input.prepare_inputs(
            batch=batch, previous_state=generation["transition"]["state"],
            expected_previous_state_sha256=generation["state_sha256"])

    def assert_wrapper(self, batch, *, empty):
        self.assertEqual(batch["schema"], "sia-controller-source-batch-v2")
        self.assertTrue(all(not run["events"]
                            for run in batch["source_returns"]["runs"]))
        value = batch["idle_input"]
        self.assertEqual(set(value), WRAPPER_KEYS)
        document = value["idle_without_native"]
        self.assertEqual(set(document), DOCUMENT_KEYS)
        self.assertEqual(document["schema"], "sia-live-idle-without-native-v1")
        self.assertEqual(document["availability"],
                         "no-selected-supported-native-source")
        self.assertEqual(value["expected_idle_without_native_sha256"],
                         live_tests.digest(document))
        intake = batch["intake_projection"]["intake"]
        self.assertEqual(document["source_ids"], intake["symbols"])
        self.assertEqual(document["intake_sha256"],
                         batch["intake_projection"]["intake_sha256"])
        self.assertEqual(document["live_policy_sha256"],
                         batch["epoch"]["expected_live_policy_sha256"])
        self.assertEqual(document["observed_at"], batch["observed_at"])
        self.assertEqual(document["non_claims"], NON_CLAIMS)
        if empty:
            self.assertEqual(document["episodes"], [])
        else:
            self.assertTrue(document["episodes"])
        self.assertEqual([row["observation_id"] for row in document["episodes"]],
                         [row["id"] for row in intake["observations"]])
        records = {}
        for entry in batch["epoch"]["history"]["entries"]:
            for run in entry["source_returns"]["runs"]:
                for record in run["events"]:
                    records.setdefault((run["source_id"], record["event_id"]), record)
        for row in document["episodes"]:
            self.assertIsNone(row["native_occurrence"])
            self.assertEqual(row["event_record"], records[(
                row["source_id"], row["event_record"]["event_id"])])
        return value

    def test_custom_history_stays_idle_without_native_capture_or_replay(self):
        for empty in (False, True):
            with self.subTest(empty=empty), self.completed(empty=empty) as (
                    case, retained, committed, generation):
                before = copy.deepcopy(generation)
                with self.forbid_native(case):
                    batch = self.successor(case, retained, committed)
                    wrapper = self.assert_wrapper(batch, empty=empty)
                    self.source_batch.validate_batch(
                        case.source.lib.__dict__, batch, batch["batch_sha256"])
                    request = self.prepare(batch, generation)
                    self.assertIs(request["idle"], True)
                    self.assertEqual(request["gist_inputs"], wrapper)
                    self.assertIsNot(request["gist_inputs"], wrapper)
                    first = self.loop.prepare_pulse(**request)
                    repeated = self.loop.prepare_pulse(**request)
                self.assertEqual(first, repeated)
                self.assertEqual(first["gist_pages"], [])
                self.assertIs(first["state"]["idle"]["requested"], True)
                receipt = first["state"]["idle"]["binding"]
                self.assertEqual(set(receipt), RECEIPT_KEYS)
                self.assertEqual(receipt["schema"],
                                 "sia-live-idle-without-native-binding-v1")
                self.assertEqual(receipt["status"], "bound-no-gist")
                self.assertEqual(receipt["availability"],
                                 "no-selected-supported-native-source")
                self.assertEqual(receipt["idle_without_native"],
                                 wrapper["idle_without_native"])
                self.assertEqual(receipt["idle_without_native_sha256"],
                                 wrapper["expected_idle_without_native_sha256"])
                self.assertIsNone(receipt["gist"])
                self.assertEqual(receipt["non_claims"], NON_CLAIMS)
                self.assertEqual(receipt["binding_sha256"], live_tests.digest({
                    key: value for key, value in receipt.items()
                    if key != "binding_sha256"}))
                self.assertEqual(first["state"]["intake"],
                                 batch["intake_projection"]["intake"])
                self.assertEqual(generation, before)

    def test_no_native_input_refuses_relabeling_missing_episodes_and_outer_drift(self):
        with self.completed() as (case, retained, committed, generation):
            with self.forbid_native(case):
                batch = self.successor(case, retained, committed)
                request = self.prepare(batch, generation)
                self.loop.prepare_pulse(**request)
                original = copy.deepcopy(request)
                mutations = (
                    ("record", lambda doc: doc["episodes"][0][
                        "event_record"].update(summary="rewritten")),
                    ("missing-episode", lambda doc: doc["episodes"].pop()),
                    ("native-occurrence", lambda doc: doc["episodes"][0].update(
                        native_occurrence={"chain": "aegis", "seq": "1",
                                           "entry_hash": "a" * 64})),
                    ("native-roster", lambda doc: doc["source_ids"].append("sense_aegis")),
                    ("clock", lambda doc: doc.update(observed_at=live_tests.START)),
                    ("intake-pin", lambda doc: doc.update(intake_sha256="a" * 64)),
                    ("policy-pin", lambda doc: doc.update(live_policy_sha256="a" * 64)),
                    ("nonclaims", lambda doc: doc.update(non_claims=[])),
                    ("extra-field", lambda doc: doc.update(capture={})),
                )
                for label, mutate in mutations:
                    changed = copy.deepcopy(request)
                    value = changed["gist_inputs"]
                    mutate(value["idle_without_native"])
                    value["expected_idle_without_native_sha256"] = \
                        live_tests.digest(value["idle_without_native"])
                    with self.subTest(mutation=label), \
                            self.assertRaises(self.loop.LiveLoopRefusal):
                        self.loop.prepare_pulse(**changed)
                changed = copy.deepcopy(request)
                changed["idle"] = False
                with self.assertRaises(self.loop.LiveLoopRefusal):
                    self.loop.prepare_pulse(**changed)
                self.assertEqual(request, original)

    def test_retained_custom_idle_binding_rejects_resealed_episode_edits(self):
        with self.completed() as (case, retained, committed, _generation):
            with self.forbid_native(case):
                batch = self.successor(case, retained, committed)
                self.assert_wrapper(batch, empty=False)
                changed = copy.deepcopy(batch)
                wrapper = changed["idle_input"]
                wrapper["idle_without_native"]["episodes"][0][
                    "event_record"]["summary"] = "rewritten"
                wrapper["expected_idle_without_native_sha256"] = \
                    live_tests.digest(wrapper["idle_without_native"])
                changed["batch_sha256"] = capture_tests.own(
                    changed, "batch_sha256")
                with self.assertRaises(self.source_batch.SourceBatchRefusal):
                    self.source_batch.validate_batch(
                        case.source.lib.__dict__, changed, changed["batch_sha256"])


if __name__ == "__main__":
    unittest.main()
