"""Retained admission must agree with fresh checks after policy changes."""

import contextlib
import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import siahistoryroot as roots
import siasourcebatch as batches
import siasourcecheckpoint as captures
from tests.test_source_checkpoint_capture import SourceCheckpointCapture


_CUSTOM_POLICY = {"refuse": False}


def global_custom_policy(original, entry):
    if _CUSTOM_POLICY["refuse"]:
        return None
    return original(entry)


def clear_validation_memos():
    batches._VALIDATED_BATCHES.clear()
    captures._VALIDATED_CAPTURES.clear()


def outcome(validate, owner, image):
    try:
        value = validate(owner, image, image["batch_sha256"])
    except (ValueError, RuntimeError) as error:
        return ("refused", type(error).__name__, getattr(error, "reason", None))
    return ("accepted", value)


class RetainedValidationContext(unittest.TestCase):
    def setUp(self):
        self.case = SourceCheckpointCapture(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.addCleanup(clear_validation_memos)
        clear_validation_memos()

    @contextlib.contextmanager
    def images(self, *, nonempty=False):
        with self.case.fixture.completed() as (case, prior, _commit, status, _generation), \
                tempfile.TemporaryDirectory(prefix="sia-validation-context-") as directory:
            root = roots.prepare(vars(case.lib), memo=case.live.memo,
                                 admitted_status=status, directory=directory)
            if nonempty:
                path = Path(case.source.custom_entries[0]["path"])
                with path.open("a", encoding="utf-8") as stream:
                    stream.write("new validation context event\n")
            with self.case.fixture.source_owner(case), case.source.capture_boundary():
                captured = self.case.capture(case, status, directory, root)
            if nonempty:
                self.assertTrue(any(run["events"] for run in captured["source_returns"]["runs"]))
            owner = vars(case.source.lib)
            yield owner, ((batches.validate_batch, prior),
                          (captures.validate_capture, captured))

    def compare_changed_context(self, validate, owner, image, changed, mutate):
        clear_validation_memos()
        self.assertEqual(outcome(validate, owner, image), ("accepted", None))
        mutate()
        warm = outcome(validate, changed, image)
        clear_validation_memos()
        cold = outcome(validate, changed, image)
        self.assertEqual(cold[0], "refused", "changed policy must actually reject")
        self.assertEqual(warm, cold, "prior admission must not bypass changed policy")

    def test_changed_source_and_event_limits_match_fresh_refusal(self):
        with self.images() as (owner, images):
            for validate, image in images:
                for key in ("MAX_SOURCE_REPLAY_SOURCES", "MAX_SOURCE_REPLAY_EVENTS"):
                    with self.subTest(schema=image["schema"], limit=key):
                        changed = dict(owner, **{key: 1})
                        self.compare_changed_context(validate, owner, image, changed, lambda: None)

    def test_mutated_nested_policy_alias_matches_fresh_refusal(self):
        with self.images() as (owner, images):
            for validate, image in images:
                with self.subTest(schema=image["schema"]):
                    organs = dict(owner["_SENSE_ORGAN"])
                    selected = image["epoch"]["configuration"]["native_collectors"][0]
                    changed = dict(owner, _SENSE_ORGAN=organs)
                    alias = dict(changed)
                    self.assertIs(alias["_SENSE_ORGAN"], organs)
                    self.compare_changed_context(
                        validate, changed, image, alias,
                        lambda organs=organs, selected=selected:
                        organs.__setitem__(selected, "different-organ"))

    def test_same_callback_with_changed_closure_matches_fresh_refusal(self):
        with self.images() as (owner, images):
            for validate, image in images:
                with self.subTest(schema=image["schema"]):
                    policy = {"refuse": False}
                    original = owner["_validated_custom_sense_entry"]

                    def custom(entry, policy=policy, original=original):
                        return None if policy["refuse"] else original(entry)

                    changed = dict(owner, _validated_custom_sense_entry=custom)
                    self.compare_changed_context(
                        validate, changed, image, changed,
                        lambda policy=policy: policy.__setitem__("refuse", True))

    def test_same_callback_with_changed_global_matches_fresh_refusal(self):
        with self.images() as (owner, images):
            for validate, image in images:
                with self.subTest(schema=image["schema"]), \
                        mock.patch.dict(_CUSTOM_POLICY, {"refuse": False}):
                    original = owner["_validated_custom_sense_entry"]

                    def custom(entry, original=original):
                        return global_custom_policy(original, entry)

                    changed = dict(owner, _validated_custom_sense_entry=custom)
                    self.compare_changed_context(
                        validate, changed, image, changed,
                        lambda: _CUSTOM_POLICY.__setitem__("refuse", True))

    def test_changed_event_decoder_matches_fresh_refusal(self):
        def refuse_record(_record):
            raise ValueError("new decoder policy refuses this record")

        with self.images(nonempty=True) as (owner, images):
            for validate, image in images:
                with self.subTest(schema=image["schema"]):
                    changed = dict(owner, _event_from_replay_record=refuse_record)
                    self.compare_changed_context(validate, owner, image, changed, lambda: None)

    def test_unchanged_reuse_and_changed_image_controls(self):
        with self.images() as (owner, images):
            for validate, image in images:
                with self.subTest(schema=image["schema"]):
                    clear_validation_memos()
                    self.assertEqual(outcome(validate, owner, image), ("accepted", None))
                    self.assertEqual(outcome(validate, dict(owner), image), ("accepted", None))
                    changed = copy.deepcopy(image)
                    changed["observed_at"] += 1
                    self.assertEqual(outcome(validate, owner, changed)[0], "refused")
                    self.assertEqual(outcome(validate, owner, image), ("accepted", None))


if __name__ == "__main__":
    unittest.main()
