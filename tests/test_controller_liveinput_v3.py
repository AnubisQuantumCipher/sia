"""Pure v3 live-input adaptation from a genuinely captured source successor.

The root runs this module sequentially after the real capture-v3 fixture is
admitted. That fixture prepares delivery storage from an actually acknowledged
legacy source parent, then invokes source.capture_successor_v3. No successful
case relabels a v2 batch, invents a v3 acknowledgment, or manufactures delivery
records. The first-adoption journal is empty; nonempty consumption requires a
later genuine acknowledged-v3 fixture and is not claimed by these tests.

The independently supplied generation is the actual retained ACK parent.
Adversarial copies below change represented bytes only, never storage facts.
Generation pins and canonical comparisons are protocol checks, not JACKAL
assurance, output observations, machine-history claims or retrieval metrics.
"""

import contextlib
import copy
import importlib
import inspect
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

PARAMETERS = (
    "owner", "batch", "previous_generation", "expected_previous_generation_sha256",
)
PREPARE_KEYS = {
    "intake", "expected_intake_sha256", "deliveries", "expected_deliveries_sha256",
    "previous_state", "expected_previous_state_sha256", "policy", "expected_policy_sha256",
    "observed_at", "idle", "gist_inputs",
}
REFUSALS = (ValueError, RuntimeError, OSError)


class ControllerLiveInputV3(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("siacontrollerliveinput")
        # A missing adapter is the controlling RED, before an expensive ACK,
        # storage adoption, source acquisition or any capture fixture setup.
        self.assertTrue(callable(getattr(self.module, "prepare_inputs_v3", None)),
                        "missing source-v3 full-generation live input adapter")
        self.source = importlib.import_module("siasourcebatch")
        self.live = importlib.import_module("sialiveloop")
        self.epoch = importlib.import_module("siacontrollerdeliveryepoch")
        self.journal = importlib.import_module("siadelivery")
        self.ack = importlib.import_module("siasourceack")
        self.bench = importlib.import_module("siabench")

    @contextlib.contextmanager
    def captured(self, *, nonidle=False, fenced=False):
        # Module qualification and composition avoid rediscovering the
        # source fixture's TestCase methods as tests in this module.
        capture_tests = importlib.import_module("tests.test_controller_source_capture_v3")
        fixture = capture_tests.ControllerSourceCaptureV3(methodName="runTest")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        with fixture.prepared(nonidle=nonidle, fenced=fenced) as source_fixture:
            batch = fixture.capture(source_fixture)
            self.assertEqual(batch["schema"], "sia-controller-source-batch-v3")
            self.assertEqual(batch["delivery_input"]["journal"]["records"], [])
            self.assertEqual(batch["delivery_input"]["epoch_view"]["parent_generation"],
                             source_fixture.generation)
            yield SimpleNamespace(**vars(source_fixture), batch=batch, fixture=fixture)

    def images(self, f):
        return f.fixture.images(f)

    @contextlib.contextmanager
    def no_acquisition(self, f):
        def forbidden(*_args, **_kwargs):
            raise AssertionError("pure v3 adapter acquired source/storage/clock or used legacy adapter")

        with contextlib.ExitStack() as stack:
            for target in ("builtins.open", "os.open", "os.stat", "os.lstat",
                           "os.scandir", "os.listdir", "os.mkdir", "os.fsync", "time.time"):
                stack.enter_context(mock.patch(target, side_effect=forbidden))
            for owner, name in (
                    (self.module, "prepare_inputs"),
                    (self.live, "prepare_pulse"),
                    (self.source, "capture"), (self.source, "capture_successor"),
                    (self.source, "capture_successor_v3"), (self.source, "_collect"),
                    (self.ack, "read_completed"),
                    (self.ack, "read_capturable_predecessor"),
                    (self.epoch, "prepare_epoch"), (self.epoch, "hold_epoch"),
                    (self.epoch, "hold_capturable_epoch"),
                    (self.journal, "hold_deliveries"), (self.journal, "inspect_deliveries"),
                    (self.journal, "reserve_delivery"), (self.journal, "deliver_reserved"),
                    (self.bench, "capture_native_history"),
                    (self.bench, "capture_native_history_v2")):
                stack.enter_context(mock.patch.object(owner, name, side_effect=forbidden))
            # The fixture has separate source and publication core aliases;
            # neither may reacquire authority while preparing retained bytes.
            for owner in (f.case.lib, f.case.source.lib):
                for name in (
                        "load_memo", "_write_memo", "_read_committed_live_generation",
                        "_require_status_admission_unchanged", "_mark_notify_baseline_attempt",
                        "brainstem_owner", "corpus_owner", "utcnow"):
                    stack.enter_context(mock.patch.object(owner, name, side_effect=forbidden))
            yield

    def prepare(self, f, **changes):
        arguments = {
            "batch": f.batch, "previous_generation": f.generation,
            "expected_previous_generation_sha256": f.generation["generation_sha256"],
        }
        arguments.update(changes)
        return self.module.prepare_inputs_v3(f.owner, **arguments)

    def assert_request(self, f, result):
        generation, batch = f.generation, f.batch
        binding = batch["delivery_input"]["binding"]
        idle = all(not run["events"] for run in batch["source_returns"]["runs"])
        expected = {
            "intake": batch["intake_projection"]["intake"],
            "expected_intake_sha256": batch["intake_projection"]["intake_sha256"],
            "deliveries": binding["deliveries"],
            "expected_deliveries_sha256": binding["deliveries_sha256"],
            "previous_state": generation["transition"]["state"],
            "expected_previous_state_sha256": generation["state_sha256"],
            "policy": batch["epoch"]["live_policy"],
            "expected_policy_sha256": batch["epoch"]["expected_live_policy_sha256"],
            "observed_at": batch["observed_at"],
            "idle": idle, "gist_inputs": batch["idle_input"],
        }
        self.assertEqual(set(result), PREPARE_KEYS)
        self.assertEqual(self.live._canonical(result), self.live._canonical(expected))
        for name in ("intake", "deliveries", "previous_state", "policy"):
            self.assertIsNot(result[name], expected[name])
        if expected["gist_inputs"] is not None:
            self.assertIsNot(result["gist_inputs"], expected["gist_inputs"])
        previous = generation["transition"]["state"]["intake"]
        for name in ("pages", "observations"):
            self.assertEqual(self.live._canonical(result["intake"][name][:len(previous[name])]),
                             self.live._canonical(previous[name]))
        self.assertEqual(result["expected_deliveries_sha256"], self.live._sha(result["deliveries"]))
        self.assertIs(result["idle"], idle)

    def native_seal(self, f, value, field):
        value[field] = self.source.native_sha(
            f.owner, {key: item for key, item in value.items() if key != field})

    def assert_refused(self, f, **changes):
        before = (copy.deepcopy(f.batch), copy.deepcopy(f.generation),
                  copy.deepcopy(changes), self.images(f))
        with self.no_acquisition(f), self.assertRaises(REFUSALS):
            self.prepare(f, **changes)
        self.assertEqual((f.batch, f.generation, changes, self.images(f)), before)

    def test_exact_api_has_explicit_full_generation_and_no_ambient_default(self):
        parameters = inspect.signature(self.module.prepare_inputs_v3).parameters
        self.assertEqual(tuple(parameters), PARAMETERS)
        for name, parameter in parameters.items():
            self.assertIs(parameter.default, inspect.Parameter.empty)
            self.assertEqual(parameter.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD
                             if name == "owner" else inspect.Parameter.KEYWORD_ONLY)

    def test_genuine_nonidle_capture_uses_real_source_gate_and_exact_bound_request(self):
        with self.captured(nonidle=True) as f:
            before = (copy.deepcopy(f.batch), copy.deepcopy(f.generation), self.images(f))
            real_validate = self.source.validate_batch
            with self.no_acquisition(f), mock.patch.object(
                    self.source, "validate_batch", wraps=real_validate) as source_gate:
                result = self.prepare(f)
                self.assert_request(f, result)
                source_gate.assert_called()
                self.assertEqual(self.prepare(f), result)
            self.assertIs(result["idle"], False)
            self.assertIsNone(result["gist_inputs"])
            # The component returns a request, not an already executed pulse.
            transition = self.live.prepare_pulse(**result)
            self.assertEqual(transition["state"]["deliveries"],
                             f.batch["delivery_input"]["binding"]["deliveries"])
            self.assertEqual(transition["state"]["idle"], {"requested": False, "gist": None})
            for name in ("intake", "deliveries", "previous_state", "policy"):
                result[name].clear()
            with self.no_acquisition(f):
                self.assert_request(f, self.prepare(f))
            self.assertEqual((f.batch, f.generation, self.images(f)), before)

    def test_genuine_idle_and_fenced_capture_preserve_original_gist_wrapper(self):
        for fenced in (False, True):
            with self.subTest(fenced=fenced), self.captured(fenced=fenced) as f:
                before = (copy.deepcopy(f.batch), copy.deepcopy(f.generation), self.images(f))
                with self.no_acquisition(f):
                    result = self.prepare(f)
                    self.assert_request(f, result)
                self.assertIs(result["idle"], True)
                self.assertEqual(result["gist_inputs"], f.batch["idle_input"])
                if fenced:
                    self.assertIsNotNone(f.batch["notification_baseline_attempt"])
                    self.assertEqual(f.batch["delivery_input"]["epoch_view"]["status"],
                                     "held-capturable-not-ready")
                transition = self.live.prepare_pulse(**result)
                self.assertIs(transition["state"]["idle"]["requested"], True)
                self.assertEqual(transition["state"]["idle"]["binding"]["episode_bindings"],
                                 f.batch["idle_input"]["episode_bindings"])
                self.assertTrue(transition["gist_pages"])
                self.assertTrue(all(page["origin"] == "derived" for page in transition["gist_pages"]))
                result["gist_inputs"].clear()
                with self.no_acquisition(f):
                    self.assert_request(f, self.prepare(f))
                self.assertEqual((f.batch, f.generation, self.images(f)), before)

    def test_full_actual_parent_is_required_even_when_state_bytes_match(self):
        with self.captured(nonidle=True) as f:
            for changes in (
                    {"previous_generation": None, "expected_previous_generation_sha256": None},
                    {"previous_generation": {}},
                    {"expected_previous_generation_sha256": None},
                    {"expected_previous_generation_sha256": "0" * 64}):
                with self.subTest(changes=tuple(changes)):
                    self.assert_refused(f, **changes)
            for reseal in (False, True):
                changed = copy.deepcopy(f.generation)
                self.assertNotEqual(changed["candidate_sha256"], "0" * 64)
                changed["candidate_sha256"] = "0" * 64
                if reseal:
                    changed["generation_sha256"] = self.live._own(changed, "generation_sha256")
                self.assertEqual(changed["state_sha256"], f.generation["state_sha256"])
                self.assertEqual(changed["transition"]["state"], f.generation["transition"]["state"])
                with self.subTest(resealed_generation=reseal):
                    self.assert_refused(f, previous_generation=changed,
                        expected_previous_generation_sha256=changed["generation_sha256"])

    def test_rehashed_source_schema_wrapper_adoption_and_projection_fail_real_gate(self):
        with self.captured(nonidle=True) as f:
            for selected in ("schema", "missing-wrapper", "wrapper-status", "adoption-pin", "intake-prefix"):
                with self.subTest(selected=selected):
                    changed = copy.deepcopy(f.batch)
                    if selected == "schema":
                        changed["schema"] = "sia-controller-source-batch-v2"
                    elif selected == "missing-wrapper":
                        changed.pop("delivery_input")
                    elif selected == "wrapper-status":
                        changed["delivery_input"]["status"] = "consumed"
                        self.native_seal(f, changed["delivery_input"], "input_sha256")
                    elif selected == "adoption-pin":
                        changed["delivery_input"]["expected_adoption_sha256"] = "0" * 64
                        self.native_seal(f, changed["delivery_input"], "input_sha256")
                    else:
                        projection = changed["intake_projection"]
                        self.assertTrue(f.generation["transition"]["state"]["intake"]["observations"])
                        projection["intake"]["observations"] = []
                        projection["intake_sha256"] = self.live._sha(projection["intake"])
                        projection["projection_sha256"] = self.source._component_sha(f.owner,
                            {key: item for key, item in projection.items() if key != "projection_sha256"})
                    self.native_seal(f, changed, "batch_sha256")
                    before = copy.deepcopy(changed)
                    # Never replace the source gate with a permissive stub.
                    with self.no_acquisition(f), self.assertRaises(REFUSALS):
                        self.source.validate_batch(f.owner, changed, changed["batch_sha256"])
                    self.assert_refused(f, batch=changed)
                    self.assertEqual(changed, before)

    def test_legacy_adapter_still_refuses_delivery_membership_without_relabeling(self):
        with self.captured() as f:
            before = copy.deepcopy(f.batch)
            with self.assertRaises(self.module.ControllerLiveInputRefusal) as caught:
                self.module.prepare_inputs(batch=f.batch,
                    previous_state=f.generation["transition"]["state"],
                    expected_previous_state_sha256=f.generation["state_sha256"])
            self.assertEqual(caught.exception.reason, "legacy-delivery-input")
            self.assertEqual(f.batch, before)

    def test_final_detached_request_cannot_hide_batch_or_parent_drift(self):
        with self.captured(nonidle=True) as f:
            original_copy = copy.deepcopy
            for selected in ("batch", "parent"):
                batch, generation = original_copy(f.batch), original_copy(f.generation)
                fired = []

                def during_final_copy(value, *args, **kwargs):
                    detached = original_copy(value, *args, **kwargs)
                    if type(value) is dict and set(value) == PREPARE_KEYS and not fired:
                        fired.append(True)
                        if selected == "batch":
                            batch["delivery_input"]["expected_adoption_sha256"] = "0" * 64
                        else:
                            generation["candidate_sha256"] = "0" * 64
                    return detached

                before = self.images(f)
                with self.subTest(selected=selected), self.no_acquisition(f), \
                        mock.patch.object(copy, "deepcopy", side_effect=during_final_copy), \
                        self.assertRaises(REFUSALS):
                    self.prepare(f, batch=batch, previous_generation=generation)
                self.assertTrue(fired, "adapter's final detached prepare request was not exercised")
                self.assertEqual(self.images(f), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
