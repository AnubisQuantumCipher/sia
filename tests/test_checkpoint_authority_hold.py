"""Actual predecessor and delivery authority remain held across recovery use."""

import copy
import contextlib
import unittest
from unittest import mock

import siacheckpointtransaction as api
import siacontrollerdeliveryepoch as epochs
from tests import test_checkpoint_transaction as fixtures


class CheckpointAuthorityHold(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(getattr(api, "hold_root_preparation", None)), "missing held recovery authority")
        self.case = fixtures.CheckpointTransaction(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_actual_authority_is_held_without_recollection_and_handle_expires(self):
        self.exercise()

    def test_actual_fenced_authority_keeps_marker_and_idle_package(self):
        self.exercise(fenced=True)

    def exercise(self, *, fenced=False):
        prepare = api.prepare_root

        def inspect(owner, **kwargs):
            result = prepare(owner, **kwargs)
            before = copy.deepcopy(kwargs["memo"])
            request = {key: kwargs[key] for key in (
                "memo", "admitted_status", "directory", "expected_root_sha256", "journal_limits",
                "expected_journal_limits_sha256", "expected_adoption_sha256")}
            request["expected_manifest_sha256"] = result["manifest_sha256"]
            with mock.patch.object(api.checkpoint, "capture_root_delivery", side_effect=AssertionError("recovery recollected")), \
                    mock.patch.object(api.queue, "fixed_atomic_publish", side_effect=AssertionError("recovery published")):
                with api.hold_root_preparation(owner, **request) as held:
                    view = held.read()
                    held.current()
                    self.assertEqual(view["manifest"], result["manifest"])
                    self.assertEqual(kwargs["memo"], before)
                    if fenced:
                        self.assertIsNotNone(view["artifacts"]["capture"]["notification_baseline_attempt"])
                        self.assertTrue(view["artifacts"]["candidate"]["prepare_inputs"]["idle"])
                    actual_copy = api.copy.deepcopy

                    def changed_copy(value, *args, **arguments):
                        detached = actual_copy(value, *args, **arguments)
                        if value is held._view:
                            detached["manifest_sha256"] = "f" * 64
                        return detached

                    with mock.patch.object(api.copy, "deepcopy", side_effect=changed_copy):
                        with self.assertRaises(ValueError):
                            held.read()
                with self.assertRaises(ValueError):
                    held.current()
                with self.assertRaises(ValueError):
                    with api.hold_root_preparation(owner, **{**request, "expected_adoption_sha256": "f" * 64}):
                        self.fail("wrong adoption acquired")
                bootstrap = api.checkpoint.checkpoints.bootstrap_episodes

                def changed_bootstrap(*args, **arguments):
                    value = bootstrap(*args, **arguments)
                    self.assertTrue(value["source_non_claims"])
                    value["source_non_claims"] = []
                    return value

                with mock.patch.object(api.checkpoint.checkpoints, "bootstrap_episodes", side_effect=changed_bootstrap):
                    with self.assertRaises(ValueError):
                        with api.hold_root_preparation(owner, **request):
                            pass
                if not fenced:
                    for module, name in ((epochs, "hold_epoch"), (api, "_hold_prepared")):
                        actual_context = getattr(module, name)

                        @contextlib.contextmanager
                        def changed_exit(*args, **arguments):
                            with actual_context(*args, **arguments) as value:
                                yield value
                            kwargs["memo"]["late_test_change"] = True

                        try:
                            with mock.patch.object(module, name, side_effect=changed_exit):
                                with self.assertRaises(ValueError):
                                    with api.hold_root_preparation(owner, **request):
                                        pass
                        finally:
                            kwargs["memo"].clear()
                            kwargs["memo"].update(before)
            return result

        with mock.patch.object(api, "prepare_root", side_effect=inspect):
            self.case.exercise(fenced=fenced)
