"""Adversarial integrity contracts for the controller-source/live binding.

This fixture composes the frozen binding fixture without inheriting its test
roster.  It exercises authority and recovery boundaries that are deliberately
separate from the happy-path marker-shape contract.  Root alone executes it;
no host source, service, model, database, or external publication is used.
"""

import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_source_live_binding as binding_tests
from tests import test_live_loop as live_tests


class ControllerSourceLiveBindingIntegrity(unittest.TestCase):
    def setUp(self):
        self.case = binding_tests.ControllerSourceLiveBinding(
            methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.lib = self.case.lib
        self.live = self.case.live
        self.loop = self.case.loop
        self.ready = copy.deepcopy(self.live.memo["ready"])

    def _persist_memo(self, value):
        detached = copy.deepcopy(value)
        self.live._write(self.live.paths["MEMO_PATH"], detached)
        self.live.memo.clear()
        self.live.memo.update(detached)

    def _call_binding(self, *, memo=None, status=None, seq=None):
        admitted = self.live.status if status is None else status
        sequence = admitted["pulse_seq"] if seq is None else seq
        return self.case._stager()(
            memo=self.live.memo if memo is None else memo,
            admitted_status=admitted, seq=sequence)

    def _assert_refused_without_atomic_write(self, callback):
        memo_path = Path(self.live.paths["MEMO_PATH"])
        before = memo_path.read_bytes()
        with mock.patch.object(
                self.lib, "atomic_write",
                side_effect=AssertionError(
                    "invalid binding authority reached an atomic write")), \
                self.assertRaises((RuntimeError, ValueError)):
            callback()
        self.assertEqual(memo_path.read_bytes(), before)

    def _rehash_marker(self, marker):
        marker = copy.deepcopy(marker)
        publication_sha256 = live_tests.digest(
            self.case._publication_basis(marker))
        marker["publication_id"] = publication_sha256[:32]
        marker["publication_sha256"] = publication_sha256
        marker["marker_sha256"] = live_tests.digest({
            key: value for key, value in marker.items()
            if key != "marker_sha256"
        })
        return marker

    def _call_live_stage(self, memo, candidate):
        return self.lib._stage_live_generation(
            memo=memo, status=self.live.status,
            prepare_inputs=candidate["prepare_inputs"],
            expected_prepare_inputs_sha256=(
                candidate["expected_prepare_inputs_sha256"]))

    def test_sequence_and_durable_allocator_require_exact_integers(self):
        self.case._source()
        sequence = self.live.status["pulse_seq"]

        for impostor in (True, float(sequence)):
            with self.subTest(argument=type(impostor).__name__), \
                    mock.patch.object(
                        self.loop, "prepare_pulse",
                        side_effect=AssertionError(
                            "invalid sequence reached pure replay")):
                self._assert_refused_without_atomic_write(
                    lambda value=impostor: self._call_binding(seq=value))

        malformed = copy.deepcopy(self.live.memo)
        malformed["pulse_seq"] = float(sequence)
        self._persist_memo(malformed)
        with mock.patch.object(
                self.loop, "prepare_pulse",
                side_effect=AssertionError(
                    "non-integer durable allocator reached pure replay")):
            self._assert_refused_without_atomic_write(self._call_binding)

    def test_boolean_durable_allocator_cannot_equal_an_integer_sequence(self):
        self.case._source()
        admitted = copy.deepcopy(self.live.status)
        admitted["pulse_seq"] = 1
        malformed = copy.deepcopy(self.live.memo)
        malformed["pulse_seq"] = True
        self._persist_memo(malformed)

        with mock.patch.object(
                self.lib, "_require_status_admission_unchanged",
                return_value=copy.deepcopy(admitted)), \
                mock.patch.object(
                    self.loop, "prepare_pulse",
                    side_effect=AssertionError(
                        "boolean durable allocator reached pure replay")):
            self._assert_refused_without_atomic_write(
                lambda: self._call_binding(status=admitted, seq=1))

    def test_exact_retry_refuses_ready_coexisting_with_pending_binding(self):
        self.case._source()
        self.assertIsNone(self.case._stage()[0])
        malformed = copy.deepcopy(self.live.memo)
        malformed["ready"] = copy.deepcopy(self.ready)
        self._persist_memo(malformed)

        self._assert_refused_without_atomic_write(self._call_binding)
        self.assertIn("ready", self.live.memo)

    def test_existing_marker_shape_and_fixed_status_are_admitted_before_replay(self):
        self.case._source()
        self.assertIsNone(self.case._stage()[0])
        original = copy.deepcopy(self.live.memo)
        marker = copy.deepcopy(original["controller_source_live_pending"])
        marker["status"] = "forged-prepared-state"
        coherent_but_invalid = self._rehash_marker(marker)

        cases = (
            ("present-null", None),
            ("coherently-rehashed-fixed-field", coherent_but_invalid),
        )
        for label, selected in cases:
            with self.subTest(label=label):
                malformed = copy.deepcopy(original)
                malformed["controller_source_live_pending"] = copy.deepcopy(
                    selected)
                self._persist_memo(malformed)
                with mock.patch.object(
                        self.loop, "prepare_pulse",
                        side_effect=AssertionError(
                            "malformed recovery marker reached pure replay")):
                    self._assert_refused_without_atomic_write(
                        self._call_binding)

    def test_live_stage_requires_binding_presence_and_exact_durable_value(self):
        self.case._source()
        candidate = self.case.fixture._prepare_candidate()
        self.assertIsNone(self.case._stage()[0])
        durable = copy.deepcopy(self.live.memo)

        missing = copy.deepcopy(durable)
        missing.pop("controller_source_live_pending")
        changed = copy.deepcopy(durable)
        changed["controller_source_live_pending"]["observed_at"] = "changed"
        for label, proposed in (("missing", missing), ("changed", changed)):
            with self.subTest(label=label):
                self._persist_memo(durable)
                self._assert_refused_without_atomic_write(
                    lambda value=proposed: self._call_live_stage(
                        value, candidate))
                self.assertFalse(Path(
                    self.live.paths["LIVE_CANDIDATE_PATH"]).exists())

    def test_live_stage_validates_full_identity_self_hash_and_source_pin(self):
        self.case._source()
        candidate = self.case.fixture._prepare_candidate()
        self.assertIsNone(self.case._stage()[0])
        original = copy.deepcopy(self.live.memo)

        bad_full = copy.deepcopy(
            original["controller_source_live_pending"])
        bad_full["publication_sha256"] = "0" * 64
        bad_full["marker_sha256"] = live_tests.digest({
            key: value for key, value in bad_full.items()
            if key != "marker_sha256"
        })
        bad_self = copy.deepcopy(
            original["controller_source_live_pending"])
        bad_self["marker_sha256"] = "0" * 64
        bad_source = copy.deepcopy(
            original["controller_source_live_pending"])
        bad_source["source_batch_sha256"] = "0" * 64
        bad_source = self._rehash_marker(bad_source)

        cases = (
            ("full-identity", bad_full),
            ("self-hash", bad_self),
            ("coherent-source-pin", bad_source),
        )
        for label, marker in cases:
            with self.subTest(label=label):
                malformed = copy.deepcopy(original)
                malformed["controller_source_live_pending"] = marker
                self._persist_memo(malformed)
                self._assert_refused_without_atomic_write(
                    lambda: self._call_live_stage(
                        self.live.memo, candidate))
                self.assertFalse(Path(
                    self.live.paths["LIVE_CANDIDATE_PATH"]).exists())

    def test_candidate_derivation_uses_detached_admitted_snapshots(self):
        self.case._source()
        caller_memo = self.live.memo
        caller_status = self.live.status
        original_candidate = self.lib._prepare_controller_source_live_candidate
        observed = []

        def derive(*, memo, admitted_status):
            observed.append((memo is caller_memo,
                             admitted_status is caller_status))
            saved_memo = copy.deepcopy(caller_memo)
            saved_status = copy.deepcopy(caller_status)
            caller_memo["transient-caller-mutation"] = True
            caller_status["publication_id"] = "e" * 32
            try:
                return original_candidate(
                    memo=memo, admitted_status=admitted_status)
            finally:
                caller_memo.clear()
                caller_memo.update(saved_memo)
                caller_status.clear()
                caller_status.update(saved_status)

        with mock.patch.object(
                self.lib, "_prepare_controller_source_live_candidate",
                side_effect=derive):
            self.assertIsNone(self.case._stage()[0])

        self.assertEqual(observed, [(False, False)])
        self.assertNotIn("transient-caller-mutation", caller_memo)
        self.assertIn("controller_source_live_pending", caller_memo)

    def test_replaced_source_descriptor_refuses_before_marker_write(self):
        self.case._source()
        source_path = Path(self.case.fixture.source_path)
        source_raw = source_path.read_bytes()
        original_prepare = self.loop.prepare_pulse
        replaced = []

        def replace_once(**kwargs):
            result = original_prepare(**kwargs)
            if not replaced:
                temporary = source_path.with_name(
                    source_path.name + ".replacement")
                temporary.write_bytes(source_raw)
                temporary.chmod(0o600)
                temporary.replace(source_path)
                replaced.append(True)
            return result

        with mock.patch.object(
                self.loop, "prepare_pulse", side_effect=replace_once):
            self._assert_refused_without_atomic_write(self._call_binding)
        self.assertEqual(replaced, [True])
        self.assertNotIn("controller_source_live_pending", self.live.memo)

    def test_post_write_failure_recovers_by_write_free_reload_retry(self):
        self.case._source()
        memo_path = Path(self.live.paths["MEMO_PATH"])
        original_write = self.lib.atomic_write
        other_images = self.case._images()

        def write_then_fail(path, data, **kwargs):
            result = original_write(path, data, **kwargs)
            if str(path) == str(memo_path):
                raise OSError("synthetic failure after durable marker write")
            return result

        with mock.patch.object(
                self.lib, "atomic_write", side_effect=write_then_fail), \
                self.assertRaises(OSError):
            self._call_binding()

        self.assertNotIn("controller_source_live_pending", self.live.memo)
        durable = memo_path.read_bytes()
        reloaded = json.loads(durable)
        self.assertIn("controller_source_live_pending", reloaded)
        self.live.memo.clear()
        self.live.memo.update(reloaded)
        generation = memo_path.stat()

        with mock.patch.object(
                self.lib, "atomic_write",
                side_effect=AssertionError(
                    "exact recovery retry attempted a second write")):
            self.assertIsNone(self._call_binding())

        after = memo_path.stat()
        self.assertEqual((after.st_dev, after.st_ino),
                         (generation.st_dev, generation.st_ino))
        self.assertEqual(memo_path.read_bytes(), durable)
        self.assertEqual(self.case._images(), other_images)


if __name__ == "__main__":
    unittest.main()
