"""Focused structural joins beyond the frozen initial live-loop suite.

Root owns all executions. These cases compose that suite's synthetic fixture
without inheriting its tests. Rehashing a contradictory packet is deliberate:
the external pin is a byte premise, not permission to transfer another content
version's uses, contradict a held payload, or allocate past a declared cap.
No new clock, numerical score oracle, resident output, or runtime claim is used.
"""

import base64
import copy
import importlib
import unittest
from unittest import mock

from tests import test_live_loop as loop_tests


class LiveLoopStructuralIntegrity(unittest.TestCase):
    def setUp(self):
        self.component = importlib.import_module("sialiveloop")
        self.fixture = loop_tests.LiveLoopPureIntegration(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture._inputs()

    def rank(self, state, rows):
        return self.component.rank_recall(
            rows=rows, expected_rows_sha256=loop_tests.digest(rows),
            state=state, expected_state_sha256=loop_tests.digest(state),
            policy=self.fixture.policy, expected_policy_sha256=loop_tests.digest(self.fixture.policy),
            observed_at=loop_tests.NOW)

    def refresh_traces(self, state):
        """Make the false typed uses and trace view agree with each other.

        Refusal must therefore check original observation/delivery joins, not
        merely compare two mutually consistent but invented derived views.
        """
        versions = {page["version_sha256"]: page for page in state["intake"]["pages"]}
        state["traces"] = [
            {"v": 1, "subject": versions[version]["subject"], "complete": True,
             "uses": [{"id": use["id"], "timestamp": use["timestamp"]}
                      for use in state["uses"] if use["version_sha256"] == version]}
            for version in state["intake"]["current_versions"]]

    def test_control_preserves_generated_state_and_exact_version_bound_rows(self):
        prepared = self.fixture._prepare(self.component)
        before = copy.deepcopy(prepared)
        rows = self.fixture._rows()
        result = self.rank(prepared["state"], rows)
        self.assertEqual(result["rows"], rows)
        self.assertEqual(result["state_sha256"], prepared["state_sha256"])
        self.assertEqual(prepared, before)

    def test_rehashed_new_current_version_cannot_inherit_old_subject_trace(self):
        prepared = self.fixture._prepare(self.component)
        state = copy.deepcopy(prepared["state"])
        selected = state["workspace"]["slots"][0]
        original = next(page for page in state["intake"]["pages"] if page["subject"] == selected)
        changed = {**original, "content": original["content"] + "A distinct immutable page version.\n"}
        changed["content_sha256"] = loop_tests.bytes_digest(changed["content"].encode("utf-8"))
        changed["version_sha256"] = loop_tests.version_digest(changed)
        state["intake"]["pages"].append(changed)
        state["intake"]["current_versions"] = [
            changed["version_sha256"] if version == original["version_sha256"] else version
            for version in state["intake"]["current_versions"]]
        # Old uses remain correctly labelled as old-version history; only the
        # persisted subject-only trace is stale for the new current version.
        self.assertTrue(any(use["version_sha256"] == original["version_sha256"] for use in state["uses"]))
        row = {"row_ref": "new-current-version", "version_sha256": changed["version_sha256"],
               "row": {"slug": changed["subject"], "score": 1.0, "title": changed["subject"],
                       "type": "event", "chunk_text": changed["content"]}}
        with self.assertRaises(self.component.LiveLoopRefusal):
            self.rank(state, [row])

    def test_rehashed_uses_and_traces_must_reconstruct_from_original_typed_records(self):
        prepared = self.fixture._prepare(self.component)
        rows = self.fixture._rows()
        for label in ("omitted-use", "unknown-record", "source-origin"):
            state = copy.deepcopy(prepared["state"])
            self.assertTrue(state["uses"])
            if label == "omitted-use":
                state["uses"].pop()
            elif label == "unknown-record":
                use = state["uses"][0]
                use["record_id"] = "not-in-the-complete-observation-roster"
                use["id"] = loop_tests.digest({key: use[key] for key in
                                                ("kind", "record_id", "version_sha256")})
            else:
                use = next(use for use in state["uses"] if use["subject_origin"] == "model")
                use["subject_origin"] = "evidence"
            self.refresh_traces(state)
            with self.subTest(label=label), self.assertRaises(self.component.LiveLoopRefusal):
                self.rank(state, rows)

    def test_rehashed_held_frame_cannot_contradict_the_retained_payload(self):
        prepared = self.fixture._prepare(self.component)
        for label in ("origin", "content"):
            state = copy.deepcopy(prepared["state"])
            # Break deepcopy's preserved alias intentionally so this mutates
            # only the retained selection receipt, not current-frame inputs.
            held = copy.deepcopy(state["held_selection_receipt"])
            state["held_selection_receipt"] = held
            selected = held["frame"]["candidates"][0]
            if label == "origin":
                self.assertEqual(selected["origin"], "model")
                selected["origin"] = "evidence"
            else:
                selected["content"] = "Contradictory held-selection provenance.\n"
            held["frame_sha256"] = loop_tests.digest(held["frame"])
            self.assertEqual(held["payload_sha256"], state["workspace"]["payload_sha256"])
            with self.subTest(label=label), self.assertRaises(self.component.LiveLoopRefusal):
                self.fixture._prepare(
                    self.component, previous_state=state,
                    expected_previous_state_sha256=loop_tests.digest(state),
                    observed_at=loop_tests.DELIVERED_AT)

    def test_encoded_delivery_capacity_is_checked_before_decoding_a_false_small_claim(self):
        policy = copy.deepcopy(self.fixture.policy)
        policy["limits"]["max_delivery_bytes"] = 1
        self.fixture.policy = policy
        self.fixture.kw.update(policy=policy, expected_policy_sha256=loop_tests.digest(policy))
        prepared = self.fixture._prepare(self.component)
        ranked = self.fixture._rank(self.component, prepared)
        record = self.fixture._delivery(self.component, ranked, body=b"x")
        record["output_utf8_base64"] = base64.b64encode(b"oversized complete witness").decode("ascii")
        record["record_sha256"] = loop_tests.own_digest(record, "record_sha256")
        inputs = self.fixture._with_delivery(record)
        with mock.patch("base64.b64decode", side_effect=AssertionError("decoded beyond declared body cap")) as decode, \
                self.assertRaises(self.component.LiveLoopRefusal):
            self.fixture._prepare(
                self.component, **self.fixture._resume(prepared, observed_at=loop_tests.DELIVERED_AT), **inputs)
        decode.assert_not_called()
