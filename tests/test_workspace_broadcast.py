"""Maintained software workspace contracts; no resident state or delivery.

Dehaene, Kerszberg & Changeux (1998), THEORETICAL PREMISES: Selective Gating
and Spatio-Temporal Dynamics, and Simulation Results (maintained activity):
https://pmc.ncbi.nlm.nih.gov/articles/PMC24407/
Those passages motivate competition, persistence and common availability.
The finite timer below is an engineering latch, not recurrent neural dynamics,
consciousness, a complete GNW model, or evidence of a held-out improvement.
"""

import copy
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

try:
    import sia_test_home
    from test_activation_trace import POLICY as ACTIVATION_POLICY
except ModuleNotFoundError:
    from tests import sia_test_home
    from tests.test_activation_trace import POLICY as ACTIVATION_POLICY

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "bin"))
CONSUMERS = ["resident-status", "context-selection"]
POLICY = {
    "v": 1, "algorithm": "activation-competition-held-payload-v1",
    "time_unit": "unix-seconds-integer", "slots": 1,
    "ignition_threshold": -2, "hold_seconds": 10, "max_hold_seconds": 60,
    "tie_break": "stable-input-order", "release_policy": "expire-or-explicit",
    "consumer_roster": CONSUMERS,
    "max_candidates": 256, "max_consumers": 16,
    "max_content_bytes": 4096, "max_payload_bytes": 65536,
    "max_broadcast_bytes": 1048576,
}
# Direct JACKAL observations made before these fixture values were written.
# status=exact concerns only the supplied integer arithmetic, not this module.
EXACT_FIXTURES = {
    "expiry": {"status": "exact", "parsed": "100+10", "exact": "110"},
    "before_expiry": {"status": "exact", "parsed": "100+10-1", "exact": "109"},
    "replacement_expiry": {"status": "exact", "parsed": "110+10", "exact": "120"},
    "time_overflow": {"status": "exact", "parsed": "9007199254740991+10",
                      "exact": "9007199254741001"},
    "roster_overflow": {"status": "exact", "parsed": "256+1", "exact": "257"},
    "content_overflow": {"status": "exact", "parsed": "4096+1", "exact": "4097"},
    "held_challenger_mass_difference": {
        "status": "exact", "parsed": "(109-96)^-1+(109-108)^-1-(109-99)^-1",
        "exact": "127/130"},
    "expired_challenger_mass_difference": {
        "status": "exact", "parsed": "(110-96)^-1+(110-108)^-1-(110-99)^-1",
        "exact": "37/77"},
}
EXACT_NON_CLAIMS = [
    "NOT formal-bounded: this lane carries no Lean-checked certificate",
    "The epistemic class above is the STRONGEST claim this result supports",
    "exact rational arithmetic (not yet checker-covered)",
]


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def candidate(subject, stamps, *, origin="evidence", content="Original source content.\n"):
    return {"subject": subject, "content": content, "origin": origin,
            "source_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "trace": {"v": 1, "subject": subject, "complete": True,
                      "uses": [{"id": "use-" + str(index), "timestamp": stamp}
                               for index, stamp in enumerate(stamps)]}}


def frame():
    return {"v": 1, "complete": True, "generation_sha256": "a" * 64,
            "candidates": [candidate("units/older", [96]),
                           candidate("units/recent", [99], origin="model",
                                     content="Untrusted model prose: λ remains prose.\n")]}


def payload_item(value):
    return {key: value[key] for key in ("subject", "content", "origin", "source_sha256")}


class WorkspaceBroadcast(unittest.TestCase):
    def setUp(self):
        try:
            self.component = importlib.import_module("siaworkspace")
        except ModuleNotFoundError as exc:
            self.fail("bounded maintained-workspace component must exist: " + str(exc))

    def advance(self, value=None, *, observed_at=100, previous_state=None,
                expected_previous_state_sha256=None, policy=POLICY,
                activation_policy=ACTIVATION_POLICY, consumers=CONSUMERS, release=False):
        # Convenience defaults are test-only. The production API has none.
        return self.component.advance_workspace(
            frame() if value is None else value, observed_at=observed_at,
            previous_state=previous_state,
            expected_previous_state_sha256=expected_previous_state_sha256,
            policy=policy, activation_policy=activation_policy,
            consumers=consumers, release=release)

    def resume(self, prior, value=None, **kwargs):
        return self.advance(value, previous_state=prior["state"],
                            expected_previous_state_sha256=prior["state_sha256"], **kwargs)

    def assert_broadcast(self, result):
        self.assertEqual(set(result["broadcast"]), set(CONSUMERS))
        payload_json = result["payload_json"]
        self.assertIs(type(payload_json), str, "payload transport must be immutable text")
        payload = json.loads(payload_json)
        self.assertEqual(payload_json.encode("utf-8"), encoded(payload))
        self.assertEqual(result["payload_sha256"],
                         hashlib.sha256(payload_json.encode("utf-8")).hexdigest())
        expected = {"generation": payload["generation"],
                    "payload_sha256": result["payload_sha256"], "payload_json": payload_json}
        for consumer in CONSUMERS:
            self.assertEqual(result["broadcast"][consumer], expected)
        self.assertEqual(result["state_sha256"], sha(result["state"]))
        self.assertNotIn("acknowledged", result)
        self.assertNotIn("delivered", result)
        return payload

    def test_public_api_requires_explicit_state_policies_time_release_and_roster(self):
        signature = inspect.signature(self.component.advance_workspace)
        for name in ("observed_at", "previous_state", "expected_previous_state_sha256",
                     "policy", "activation_policy", "consumers", "release"):
            self.assertIs(signature.parameters[name].default, inspect.Parameter.empty)
            self.assertEqual(signature.parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)
        for key in POLICY:
            changed = copy.deepcopy(POLICY)
            del changed[key]
            with self.subTest(missing=key), self.assertRaises(self.component.WorkspaceRefusal):
                self.advance(policy=changed)
        for key in ACTIVATION_POLICY:
            changed = copy.deepcopy(ACTIVATION_POLICY)
            del changed[key]
            with self.subTest(activation_missing=key), self.assertRaises(self.component.WorkspaceRefusal):
                self.advance(activation_policy=changed)

    def test_competition_uses_complete_activation_and_distinguishes_eligible_from_selected(self):
        value = frame()
        expected = self.component.siaactivation.rank_traces(
            [item["trace"] for item in value["candidates"]],
            observed_at=100, policy=ACTIVATION_POLICY)
        result = self.advance(value)
        self.assertEqual(result["activation"], expected)
        self.assertEqual(result["transition"], "ignited")
        self.assertIsNone(result["release_reason"])
        self.assertEqual(result["slots"], ["units/recent"])
        rows = {row["subject"]: row for row in result["candidates"]}
        self.assertTrue(rows["units/older"]["eligible"])
        self.assertFalse(rows["units/older"]["selected"])
        self.assertTrue(rows["units/recent"]["eligible"])
        self.assertTrue(rows["units/recent"]["selected"])
        self.assertEqual(result["state"]["phase"], "holding")
        self.assertEqual(result["state"]["episode"]["ignited_at"], 100)
        self.assertEqual(result["state"]["episode"]["expires_at"],
                         int(EXACT_FIXTURES["expiry"]["exact"]))

    def test_payload_preserves_origin_source_and_content_for_all_named_consumers(self):
        value = frame()
        before = copy.deepcopy(value)
        result = self.advance(value)
        payload = self.assert_broadcast(result)
        self.assertEqual(payload["selected"], [payload_item(value["candidates"][-1])])
        self.assertEqual(value, before)
        self.assertEqual(result["state"]["episode"], payload)
        self.assertEqual(result["state"]["frame_sha256"], sha(value))
        self.assertEqual(result["state"]["policy_sha256"], sha(POLICY))
        self.assertEqual(result["state"]["activation_policy_sha256"], sha(ACTIVATION_POLICY))
        self.assertEqual(result["state"]["consumers_sha256"], sha(CONSUMERS))
        result["broadcast"][CONSUMERS[0]]["payload_json"] = "consumer-local replacement"
        self.assertEqual(result["broadcast"][CONSUMERS[-1]]["payload_json"], encoded(payload).decode())
        result["state"]["episode"]["selected"][0]["origin"] = "evidence"
        self.assertEqual(value, before, "output mutation must not promote input model origin")

    def test_hold_sustains_frozen_episode_despite_a_stronger_challenger(self):
        first = self.advance()
        value = frame()
        value["generation_sha256"] = "b" * 64
        value["candidates"][0]["trace"]["uses"].append({"id": "later-use", "timestamp": 108})
        result = self.resume(first, value, observed_at=int(EXACT_FIXTURES["before_expiry"]["exact"]))
        self.assertEqual(result["activation"]["order"][0], "units/older")
        self.assertEqual(result["transition"], "sustained")
        self.assertEqual(result["slots"], first["slots"])
        self.assertEqual(result["payload_json"], first["payload_json"])
        self.assertEqual(result["payload_sha256"], first["payload_sha256"])
        self.assertEqual(result["state"]["episode"], first["state"]["episode"])
        self.assertEqual(result["state"]["parent_state_sha256"], first["state_sha256"])
        self.assertNotEqual(result["state_sha256"], first["state_sha256"])
        self.assert_broadcast(result)

    def test_expiry_and_replacement_are_both_explicit_in_one_transition(self):
        first = self.advance()
        value = frame()
        value["candidates"][0]["trace"]["uses"].append({"id": "later-use", "timestamp": 108})
        result = self.resume(first, value, observed_at=int(EXACT_FIXTURES["expiry"]["exact"]))
        self.assertEqual(result["transition"], "replaced")
        self.assertEqual(result["release_reason"], "hold-expired")
        self.assertEqual(result["slots"], ["units/older"])
        self.assertEqual(result["state"]["episode"]["expires_at"],
                         int(EXACT_FIXTURES["replacement_expiry"]["exact"]))
        self.assertNotEqual(result["payload_sha256"], first["payload_sha256"])
        self.assert_broadcast(result)

    def test_explicit_release_clears_episode_without_reigniting_in_the_same_call(self):
        first = self.advance()
        result = self.resume(first, observed_at=101, release=True)
        self.assertEqual(result["transition"], "released")
        self.assertEqual(result["release_reason"], "explicit-release")
        self.assertEqual(result["state"]["phase"], "idle")
        self.assertIsNone(result["state"]["episode"])
        self.assertEqual(result["slots"], [])
        self.assertEqual(self.assert_broadcast(result)["selected"], [])

    def test_ineligible_or_unavailable_candidates_remain_inspectable_without_ignition(self):
        result = self.advance(policy={**POLICY, "ignition_threshold": 1})
        self.assertEqual(result["transition"], "idle")
        self.assertEqual(result["slots"], [])
        self.assertIsNone(result["state"]["episode"])
        self.assertTrue(all(not row["eligible"] and not row["selected"] for row in result["candidates"]))
        value = frame()
        for item in value["candidates"]:
            item["trace"]["uses"] = []
        result = self.advance(value)
        self.assertEqual(result["transition"], "idle")
        self.assertTrue(all(row["status"] == "unavailable" for row in result["activation"]["activations"]))
        self.assertEqual(self.assert_broadcast(result)["selected"], [])

    def test_oversized_candidate_is_ineligible_rather_than_refusing_the_cycle(self):
        """The shipped policy admits 1 MiB of candidate content but a 64 KiB
        payload. A candidate whose item cannot be carried is ineligible for
        a slot, like one below the ignition threshold, and the cycle
        proceeds with what fits; it used to refuse every cycle with
        payload-byte-capacity as soon as one day page grew past ~60 KB."""
        roomy = dict(POLICY, max_content_bytes=1048576)
        big = candidate("units/huge", [99], content="x" * (roomy["max_payload_bytes"] + 1))
        small = candidate("units/small", [97])
        value = {"v": 1, "complete": True, "generation_sha256": "a" * 64,
                 "candidates": [big, small]}
        result = self.advance(value, policy=roomy)
        payload = self.assert_broadcast(result)
        self.assertEqual([item["subject"] for item in payload["selected"]], ["units/small"])
        self.assertEqual(result["state"]["phase"], "holding")
        self.assertIn("units/huge", {row["subject"] for row in result["activation"]["activations"]},
                      "the oversized candidate is still inspectable")
        self.assertEqual(self.component._oversized_subjects(value, roomy, 100), {"units/huge"})
        # Nothing fitting: the cycle idles honestly instead of refusing.
        alone = {"v": 1, "complete": True, "generation_sha256": "a" * 64, "candidates": [big]}
        idle = self.advance(alone, policy=roomy)
        self.assertEqual(idle["state"]["phase"], "idle")
        self.assertIsNone(idle["state"]["episode"])
        # A held episode that cannot be carried under the policy still refuses by name.
        widened = dict(roomy, max_payload_bytes=roomy["max_payload_bytes"] * 4)
        wide_prior = self.advance(value, policy=widened)
        self.assertEqual([item["subject"] for item in json.loads(
            wide_prior["payload_json"])["selected"]], ["units/huge"])
        with self.assertRaises(Exception) as caught:
            self.advance(value, previous_state=wide_prior["state"],
                         expected_previous_state_sha256=wide_prior["state_sha256"],
                         observed_at=105, policy=roomy)
        self.assertIn("payload-byte-capacity", str(caught.exception)
                      + str(getattr(caught.exception, "reason", "")))

    def test_stable_input_order_resolves_equal_activation_competition(self):
        value = frame()
        value["candidates"][0]["trace"]["uses"] = [{"id": "tie-use", "timestamp": 99}]
        first = self.advance(value)
        self.assertEqual(first["slots"], [value["candidates"][0]["subject"]])
        value["candidates"].reverse()
        second = self.advance(value)
        self.assertEqual(second["slots"], [value["candidates"][0]["subject"]])

    def test_changed_or_missing_held_source_refuses_without_mixing_episode_payload(self):
        first = self.advance()
        before_state = copy.deepcopy(first["state"])
        for key, replacement in (("content", "Replaced content"), ("origin", "evidence"),
                                 ("source_sha256", "f" * 64)):
            value = frame()
            value["candidates"][-1][key] = replacement
            before_frame = copy.deepcopy(value)
            with self.subTest(changed=key), self.assertRaisesRegex(self.component.WorkspaceRefusal, "held"):
                self.resume(first, value, observed_at=101)
            self.assertEqual(value, before_frame)
            self.assertEqual(first["state"], before_state)
        value = frame()
        value["candidates"].pop()
        with self.assertRaisesRegex(self.component.WorkspaceRefusal, "held"):
            self.resume(first, value, observed_at=101)

    def test_source_change_can_be_explicitly_released_but_never_silently_rebound(self):
        first = self.advance()
        value = frame()
        value["candidates"][-1]["content"] = "A different source generation"
        result = self.resume(first, value, observed_at=101, release=True)
        self.assertEqual(result["transition"], "released")
        self.assertEqual(result["slots"], [])
        self.assertEqual(result["release_reason"], "explicit-release")

    def test_prior_state_requires_an_external_pin_not_just_its_own_witness(self):
        first = self.advance()
        for expected in (None, "f" * 64):
            with self.subTest(expected=expected), self.assertRaises(self.component.WorkspaceRefusal):
                self.advance(previous_state=first["state"], expected_previous_state_sha256=expected,
                             observed_at=101)
        altered = copy.deepcopy(first["state"])
        altered["episode"]["selected"][0]["origin"] = "evidence"
        with self.assertRaises(self.component.WorkspaceRefusal):
            self.advance(previous_state=altered, expected_previous_state_sha256=first["state_sha256"],
                         observed_at=101)
        with self.assertRaises(self.component.WorkspaceRefusal):
            self.advance(expected_previous_state_sha256="f" * 64)

    def test_even_externally_pinned_prior_state_must_obey_episode_shape_and_hold_limit(self):
        first = self.advance()
        for altered in ({**first["state"], "phase": "unbounded"},
                        {**first["state"], "episode": {**first["state"]["episode"],
                                                       "expires_at": 9007199254740991}}):
            with self.subTest(altered=altered), self.assertRaises(self.component.WorkspaceRefusal):
                self.advance(previous_state=altered, expected_previous_state_sha256=sha(altered),
                             observed_at=101)

    def test_protocol_and_complete_named_consumer_roster_cannot_change_beneath_a_hold(self):
        first = self.advance()
        for consumers in ([], [CONSUMERS[0]], [*CONSUMERS, "unknown"],
                          [CONSUMERS[0], CONSUMERS[0]], list(reversed(CONSUMERS)), [None]):
            with self.subTest(consumers=consumers), self.assertRaises(self.component.WorkspaceRefusal):
                self.advance(consumers=consumers)
        for options in ({"policy": {**POLICY, "ignition_threshold": -1}},
                        {"activation_policy": {**ACTIVATION_POLICY, "decay": 2}},
                        {"policy": {**POLICY, "consumer_roster": ["different"]},
                         "consumers": ["different"]}):
            with self.subTest(options=options), self.assertRaises(self.component.WorkspaceRefusal):
                self.resume(first, observed_at=101, **options)

    def test_time_must_be_explicit_integer_nondecreasing_and_hold_representable(self):
        first = self.advance()
        for timestamp in (True, 100.0, -1, 9007199254740992):
            with self.subTest(timestamp=timestamp), self.assertRaises(self.component.WorkspaceRefusal):
                self.advance(observed_at=timestamp)
        with self.assertRaises(self.component.WorkspaceRefusal):
            self.resume(first, observed_at=99)
        with mock.patch.object(self.component.siaactivation, "rank_traces",
                               side_effect=AssertionError("activation before hold range admission")):
            with self.assertRaises(self.component.WorkspaceRefusal):
                self.advance(observed_at=9007199254740991)

    def test_whole_frame_admits_before_activation_copy_or_hash(self):
        value = frame()
        value["candidates"][-1]["trace"]["uses"][-1]["timestamp"] = 101
        before = copy.deepcopy(value)
        with mock.patch.object(self.component.siaactivation, "rank_traces", side_effect=AssertionError("activation")), \
                mock.patch.object(self.component.copy, "deepcopy", side_effect=AssertionError("copy")), \
                mock.patch.object(self.component.hashlib, "sha256", side_effect=AssertionError("hash")):
            with self.assertRaises(self.component.WorkspaceRefusal):
                self.advance(value)
        self.assertEqual(value, before)

    def test_whole_input_byte_budget_precedes_activation_copy_and_hash(self):
        value = frame()
        with mock.patch.object(self.component, "MAX_INPUT_BYTES", 1), \
                mock.patch.object(self.component.siaactivation, "rank_traces", side_effect=AssertionError("activation")), \
                mock.patch.object(self.component.copy, "deepcopy", side_effect=AssertionError("copy")), \
                mock.patch.object(self.component.hashlib, "sha256", side_effect=AssertionError("hash")):
            with self.assertRaisesRegex(self.component.WorkspaceRefusal, "byte"):
                self.advance(value)

    def test_closed_shape_origin_trace_and_finite_work_limits_are_atomic(self):
        invalid_frames = []
        for extra in ({"complete": False}, {"v": True}, {"generation_sha256": "not-a-generation"},
                      {"candidates": None}, {"hidden_score": 1}):
            invalid_frames.append({**frame(), **extra})
        value = frame()
        value["candidates"][-1]["origin"] = "promoted"
        invalid_frames.append(value)
        value = frame()
        value["candidates"][-1]["trace"]["complete"] = False
        invalid_frames.append(value)
        value = frame()
        value["candidates"][-1]["trace"]["subject"] = "units/different"
        invalid_frames.append(value)
        value = frame()
        value["candidates"][-1] = copy.deepcopy(value["candidates"][0])
        invalid_frames.append(value)
        for value in invalid_frames:
            before = copy.deepcopy(value)
            with self.subTest(value=value), self.assertRaises(self.component.WorkspaceRefusal):
                self.advance(value)
            self.assertEqual(value, before)
        for key, bad in (("slots", 0), ("max_candidates", 1), ("max_candidates", 257),
                         ("max_consumers", 1), ("max_consumers", 257),
                         ("max_content_bytes", 1), ("hold_seconds", 0),
                         ("hold_seconds", 100), ("max_hold_seconds", 0),
                         ("ignition_threshold", float("nan")), ("ignition_threshold", float("inf")),
                         ("ignition_threshold", True), ("release_policy", "forever"),
                         ("tie_break", "random"), ("max_payload_bytes", 1), ("max_broadcast_bytes", 1)):
            with self.subTest(key=key, bad=bad), self.assertRaises(self.component.WorkspaceRefusal):
                self.advance(policy={**POLICY, key: bad})
        for release in (None, 1, "yes"):
            with self.subTest(release=release), self.assertRaises(self.component.WorkspaceRefusal):
                self.advance(release=release)

    def test_output_has_explicit_engineering_nonclaims_and_no_clock_or_delivery_side_effect(self):
        value = frame()
        with mock.patch("time.time", side_effect=AssertionError("ambient clock")):
            first = self.advance(value)
            second = self.advance(value)
        self.assertEqual(first, second)
        self.assertEqual(first["component"], "maintained-workspace")
        self.assertEqual(first["status"], "computed-unverified")
        self.assertTrue(first["non_claims"])
        self.assertNotIn("consciousness", first)
        self.assertNotIn("heldout_win", first)
        self.assertNotIn("acknowledged", first)


if __name__ == "__main__":
    unittest.main()
