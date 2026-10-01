"""Separately staged regression for retained, variable-size occurrence labels.

The full source control uses only the existing public signed fixture. A copied
native chain is given an unsupported label and no projected-witness claims;
the existing pure history validator, not a mocked admission result, admits it.
The output ceiling is chosen from an observed public-API artifact size, not a
private reservation helper or a hand-calculated expected result.
"""

import copy
import json
import unittest
from unittest import mock

from tests import test_replay_gist as contract


class ReplayGistVariableMetadataBudget(unittest.TestCase):
    def test_long_unsupported_chain_references_are_reserved_before_copy_hash_or_learning(self):
        # Reuse only the public fixture setup, without inheriting or invoking
        # the frozen test methods in this separately staged regression class.
        fixture = contract.ReplayGist(
            "test_public_api_is_explicit_and_has_no_target_or_query_input")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        capture = copy.deepcopy(fixture.capture)
        original = next(row for row in capture["chains"] if row["chain"] == "aegis")
        copied_chain = copy.deepcopy(original)
        # A declared synthetic stress size, within the existing per-string
        # ceiling; this is not a measured or inferred real registry identity.
        unsupported_name = "unsupported-" + "x" * 524288
        copied_chain["chain"] = unsupported_name
        copied_events = []
        for event in capture["events"]:
            if event["chain"] != "aegis":
                continue
            copied = copy.deepcopy(event)
            copied["chain"] = unsupported_name
            copied["projection"] = None
            copied["retention"] = {
                "status": "not-projected", "witness_kind": None,
                "source_slug": None, "index_file": None, "retrieval_excerpt": None,
                "projected_event_retained": False, "value_answer_retained": False,
            }
            copied_events.append(copied)
        capture["chains"].append(copied_chain)
        capture["events"].extend(copied_events)
        capture["capture_sha256"] = contract.sha({
            key: value for key, value in capture.items() if key != "capture_sha256"})

        # Nonvacuity: the complete captured native rows/head, original source
        # pages, origin classifications and internal hashes are still valid.
        fixture.history.admit_capture(capture)
        replay = contract.schedule(capture)
        generous_arguments = fixture.arguments(capture=capture, replay=replay)
        generous = fixture.component.replay_gist(**generous_arguments)
        observed = generous["artifact_json"].encode("utf-8")
        body = json.loads(observed)
        self.assertEqual(body["capture"], capture)
        actual = [row for row in body["occurrences"]
                  if row["occurrence"]["chain"] == unsupported_name]
        self.assertEqual(len(actual), len(copied_events))
        self.assertTrue(all(row["status"] == "unsupported" for row in actual))
        self.assertTrue(all(row["reason"] == "unsupported-native-chain" for row in actual))

        # Leave the complete input admissible while requesting less than the
        # observed complete output. A whole policy's encoded length is a
        # measured margin, also covering changes to the limit's own spelling.
        policy = copy.deepcopy(contract.POLICY)
        policy["limits"]["max_output_bytes"] = len(observed) - len(contract.canonical(policy))
        arguments = fixture.arguments(capture=capture, replay=replay, policy=policy)
        self.assertGreater(policy["limits"]["max_output_bytes"], len(contract.canonical(arguments)))
        with self.assertRaises(fixture.component.GistRefusal):
            fixture.component.replay_gist(**arguments)

        before = copy.deepcopy(arguments)
        with mock.patch.object(fixture.component.copy, "deepcopy",
                               side_effect=AssertionError("copy before complete variable-metadata reservation")), \
                mock.patch.object(fixture.component.hashlib, "sha256",
                                  side_effect=AssertionError("hash before complete variable-metadata reservation")), \
                mock.patch.object(fixture.component, "Fraction",
                                  side_effect=AssertionError("learning before complete variable-metadata reservation")):
            with self.assertRaises(fixture.component.GistRefusal):
                fixture.component.replay_gist(**arguments)
        self.assertEqual(arguments, before)


if __name__ == "__main__":
    unittest.main()
