"""Controller-native capture retains projected source metadata without QA.

The real private AEGIS collector emits GENESIS. Its original normalized
Event and published corpus marker must survive the additive native capture
front door, even though that action is unsupported by the gist grammar.
The original capture front door retains its frozen QA-era exclusion.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import copy
import importlib
import inspect
import unittest
from unittest import mock

from tests import test_controller_source_capture as source_tests


class NativeControllerMetadataCapture(unittest.TestCase):
    def setUp(self):
        self.fixture = source_tests.ControllerSourceCapture(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.lib = self.fixture.lib
        self.bench = importlib.import_module("siabench")
        self.history = importlib.import_module("siacognitivehistory")
        self.gist = importlib.import_module("siagist")
        for module in (self.bench, self.history):
            patcher = mock.patch.object(module, "sialib", self.lib)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_additive_controller_capture_retains_exact_genesis_event_and_witness(self):
        operation = getattr(self.bench, "capture_native_history_v2", None)
        self.assertTrue(callable(operation),
                        "missing controller-native metadata capture front door")
        parameters = inspect.signature(operation).parameters
        self.assertEqual(tuple(parameters),
                         ("corpus", "chain_registry", "chain_names"))
        self.assertTrue(all(parameter.kind == inspect.Parameter.KEYWORD_ONLY
                            for parameter in parameters.values()))
        self.assertTrue(all(parameter.default is inspect.Parameter.empty
                            for parameter in parameters.values()))
        source = self.fixture.capture()
        original = copy.deepcopy(source)
        records = next(run["events"] for run in source["source_returns"]["runs"]
                       if run["source_id"] == "sense_aegis")
        metadata = next(row for row in records
                        if row["summary"].startswith("GENESIS:"))
        closure = source["event_closure"]
        self.assertIsNotNone(closure)
        self.lib._publish_event_page_batch_closure(
            closure=closure, expected_closure_sha256=closure["closure_sha256"])
        request = {"corpus": self.lib.CORPUS,
                   "chain_registry": self.lib._chain_cmds(),
                   "chain_names": ["aegis"]}
        with mock.patch.object(self.bench, "build_ledger_dataset",
                               side_effect=AssertionError("source capture generated QA")):
            legacy = self.bench.capture_native_history(**request)
            captured = operation(**request)
            repeated = operation(**request)
        self.assertEqual(captured, repeated)
        self.history.admit_capture(captured)
        self.assertEqual(captured["generator"]["schema"],
                         "sia-native-controller-source-capture-v2")
        old_metadata = next(row for row in legacy["events"]
                            if row["row"][2].startswith("GENESIS:"))
        self.assertIsNone(old_metadata["projection"])
        self.assertEqual(old_metadata["retention"]["status"], "not-projected")
        native = next(row for row in captured["events"]
                      if row["row"][2].startswith("GENESIS:"))
        self.assertEqual(native["row"], old_metadata["row"])
        self.assertEqual(native["entry_hash"], old_metadata["entry_hash"])
        self.assertEqual(native["projection"], self.history._projection(
            self.lib._event_from_replay_record(metadata)))
        self.assertEqual(self.lib._event_replay_record(
            self.lib.signed_ledger_event_projection("aegis", native["row"])), metadata)
        self.assertEqual(native["retention"]["status"], "retained")
        self.assertEqual(native["retention"]["witness_kind"], "live-event-marker")
        self.assertIs(native["retention"]["projected_event_retained"], True)
        retained_page = next(page for page in captured["pages"]
                             if page["slug"] == native["retention"]["source_slug"])
        self.assertIn(metadata["event_id"], retained_page["text"])
        self.assertIn(metadata["summary"], retained_page["text"])
        self.assertEqual(self.gist._native_relation(native),
                         (None, "unsupported-action-stage"))
        self.assertEqual(source, original)


if __name__ == "__main__":
    unittest.main()
