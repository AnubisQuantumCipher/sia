"""Projection-only no-native idle visibility -- targeted RED contract.

The no-native binding comes from the real custom-source successor and pure
live pipeline fixtures. This file exercises the display projection after its
caller has supplied a binding and an empty gist-page receipt. It does not
claim that the constructed display arguments were durably published together;
the public read_view source/effects/live authority is exercised separately in
test_live_view. Root alone executes this module sequentially.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import contextlib
import copy
import importlib
import unittest

from tests import test_controller_idle_empty as idle_tests
from tests import test_live_loop as live_tests


class NoNativeLiveViewProjection(unittest.TestCase):
    def setUp(self):
        self.view = importlib.import_module("sialiveview")
        self.idle = importlib.import_module("sialiveidle")
        self.gist_pages = importlib.import_module("siasourcegist")
        self.fixture = idle_tests.ControllerIdleWithoutNative(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    @contextlib.contextmanager
    def projection(self):
        with self.fixture.completed() as (case, retained, committed, previous):
            with self.fixture.forbid_native(case):
                batch = self.fixture.successor(case, retained, committed)
                transition = self.fixture.loop.prepare_pulse(
                    **self.fixture.prepare(batch, previous))
            self.assertTrue(transition["state"]["idle"]["requested"])
            self.assertEqual(transition["gist_pages"], [])
            plan = self.gist_pages.prepare_pages(
                case.lib.__dict__, gist_pages=[],
                expected_gist_pages_sha256=live_tests.digest([]),
                transition_sha256=transition["transition_sha256"])
            publication = self.gist_pages._receipt(case.lib.__dict__, plan)
            receipt = copy.deepcopy(case.memo_before_ack[
                "controller_source_effects_committed"])
            receipt["gist_publication"] = publication
            generation = copy.deepcopy(previous)
            generation.update(
                transition=transition,
                state_sha256=transition["state_sha256"],
                transition_sha256=transition["transition_sha256"])
            yield {
                "completed": {"batch": batch, "committed": committed},
                "status": case.admitted_status(),
                "generation": generation,
                "receipt": receipt,
            }

    def test_explicit_no_native_schema_shows_availability_and_preserves_receipt_status(self):
        with self.projection() as arguments:
            result = self.view._project(**arguments)
            binding = arguments["generation"]["transition"]["state"]["idle"]["binding"]
            self.assertEqual(binding["schema"], "sia-live-idle-without-native-binding-v1")
            self.assertNotIn("source_non_claims", binding)
            self.assertEqual(result["idle"]["availability"],
                             "no-selected-supported-native-source")
            self.assertEqual(result["idle"]["binding_status"], "bound-no-gist")
            self.assertEqual(result["idle"]["binding_sha256"], binding["binding_sha256"])
            self.assertEqual(result["idle"]["gist_publication_status"], "gist-pages-published")
            self.assertEqual(result["idle"]["gist_publication"],
                             arguments["receipt"]["gist_publication"])
            self.assertIsNone(result["idle"]["gist_artifact_sha256"])
            self.assertEqual(result["idle"]["proposed_pages"], [])
            self.assertEqual(result["upstream_non_claims"]["gist_binding"],
                             list(self.idle.NON_CLAIMS))
            self.assertEqual(result["upstream_non_claims"]["gist_binding_sources"], {})

    def test_missing_fields_are_not_a_generic_no_native_fallback(self):
        for mutation in ("unknown-schema", "changed-nonclaims", "missing-episode"):
            with self.subTest(mutation=mutation), self.projection() as arguments:
                binding = arguments["generation"]["transition"]["state"]["idle"]["binding"]
                if mutation == "unknown-schema":
                    binding["schema"] = "invented-no-native-binding-v1"
                elif mutation == "changed-nonclaims":
                    binding["non_claims"] = []
                else:
                    self.assertTrue(binding["idle_without_native"]["episodes"])
                    binding["idle_without_native"]["episodes"].pop()
                with self.assertRaises(self.view.LiveViewRefusal):
                    self.view._project(**arguments)


if __name__ == "__main__":
    unittest.main()
