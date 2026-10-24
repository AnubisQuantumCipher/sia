"""A previous admission must not bypass current source-output binding."""
import hashlib
import json
import unittest

from tests import test_event_live_intake as replay_fixtures
from tests import test_retained_validation_context as context_fixtures
from tests.test_retained_validation_context import clear_validation_memos, outcome


def changing_projector(original, enabled, calls):
    def projector(**arguments):
        result = original(**arguments)
        calls.append(True)
        if enabled:
            result["content"] += "\nUnbound projector addition.\n"
            pin = hashlib.sha256(result["content"].encode("utf-8")).hexdigest()
            result["source_sha256"] = pin
            result["content_sha256"] = pin
            result["version_sha256"] = replay_fixtures.digest({
                key: result[key] for key in (
                    "subject", "content_sha256", "source_sha256", "origin")})
        return result
    return projector


class RetainedProjectorContext(unittest.TestCase):
    def setUp(self):
        self.fixture = context_fixtures.RetainedValidationContext(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_same_projector_with_changed_output_matches_fresh_refusal(self):
        with self.fixture.images(nonempty=True) as (owner, images):
            for validate, image in images:
                with self.subTest(schema=image["schema"]):
                    enabled, calls = [], []
                    original = owner["_corpus_page_version_from_bytes"]

                    projector = changing_projector(original, enabled, calls)

                    changed_owner = dict(owner, _corpus_page_version_from_bytes=projector)
                    clear_validation_memos()
                    self.assertEqual(outcome(validate, changed_owner, image), ("accepted", None))
                    self.assertTrue(calls, "baseline did not exercise the actual projector")
                    baseline_calls = len(calls)
                    enabled.append(True)
                    warm = outcome(validate, changed_owner, image)
                    warm_calls = len(calls)
                    clear_validation_memos()
                    cold = outcome(validate, changed_owner, image)
                    print(json.dumps({"schema": image["schema"], "warm": warm, "cold": cold,
                                      "baseline_calls": baseline_calls, "after_warm_calls": warm_calls,
                                      "after_cold_calls": len(calls)}))
                    self.assertEqual(cold[0], "refused", "changed output must actually refuse")
                    self.assertGreater(len(calls), warm_calls, "cold check did not call projector")
                    self.assertEqual(warm, cold, "cached admission bypassed current projector binding")


if __name__ == "__main__":
    unittest.main()
