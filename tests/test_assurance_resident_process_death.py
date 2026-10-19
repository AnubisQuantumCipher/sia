"""Kill a resident-cycle worker at durable WAL, then recover in another worker.

The real owning entry, leases, WAL, publication and ACK run. Git/index and
clock observations retain the existing controlled fixture. Forked workers
inherit test configuration; this is not a fresh service exec or power-loss
campaign, and does not close the full resident acceptance obligation.
"""
import copy
import json
import multiprocessing
import os
from pathlib import Path
import signal
import unittest
from unittest import mock

from tests import sia_test_home  # noqa: F401 -- isolate before runtime imports
from tests import test_controller_source_resident_v3 as resident_tests


def die_after_wal(resident, fixture):
    with resident.instrument(fixture) as trace:
        boundary = trace.owner._controller_source_rollover_boundary

        def cut(stage):
            boundary(stage)
            if stage == "successor-batch-durable":
                os.kill(os.getpid(), signal.SIGKILL)

        with mock.patch.object(trace.owner, "_controller_source_rollover_boundary", cut):
            trace.invoke(None)
    raise AssertionError("durable WAL death boundary not reached")


def recover(resident, fixture, reserved, raw):
    with resident.instrument(fixture, recovery=True) as trace:
        status = trace.invoke(fixture.adopted["expected_adoption_sha256"])
    durable = resident.assert_completed(fixture, status, trace)
    resident.assertEqual(durable["pulse_seq"], reserved["pulse_seq"])
    resident.assertEqual(fixture.case.archive_path(fixture.batch).read_bytes(), raw)
    resident.assertEqual(trace.prepares, [])
    resident.assertEqual(trace.captures, [])
    resident.assertEqual(trace.retained, [])
    resident.assertNotIn("reserve", trace.stages)
    resident.assertNotIn("clock", trace.stages)


@unittest.skipUnless("fork" in multiprocessing.get_all_start_methods(),
                     "Linux fork worker fixture required")
class AssuranceResidentProcessDeath(unittest.TestCase):
    def worker(self, target, arguments, expected):
        child = multiprocessing.get_context("fork").Process(target=target, args=arguments)
        child.start()
        try:
            child.join(timeout=60)
            if child.is_alive():
                child.kill()
                child.join(timeout=5)
                self.fail("resident fixture worker exceeded deadline")
            self.assertEqual(child.exitcode, expected)
        finally:
            if child.is_alive():
                child.kill()
                child.join(timeout=5)
            child.close()

    def test_killed_wal_worker_recovers_from_retained_bytes_without_recapture(self):
        resident = resident_tests.ControllerSourceResidentV3(methodName="runTest")
        self.addCleanup(resident.doCleanups)
        resident.setUp()
        with resident.legacy() as fixture:
            parent_ready = copy.deepcopy(fixture.case.live.memo["ready"])
            self.worker(die_after_wal, (resident, fixture), -signal.SIGKILL)
            # Child mutations cannot populate these parent-process attributes.
            self.assertIsNone(fixture.batch)
            self.assertIsNone(fixture.adopted)
            raw = Path(fixture.case.producer.source_path).read_bytes()
            fixture.batch = json.loads(raw)
            fixture.adopted = copy.deepcopy(
                fixture.batch["delivery_input"]["epoch_view"]["epoch_adoption"])
            with resident.resident_owner(fixture) as owner:
                reserved = owner.load_memo()
            fixture.case.live.memo.clear()
            fixture.case.live.memo.update(copy.deepcopy(reserved))
            # The durable WAL precedes adoption: the previous generation
            # remains recorded, not a ready acknowledgment for the successor.
            self.assertEqual(reserved["ready"], parent_ready)
            self.assertEqual(reserved["controller_source_committed"], fixture.committed)
            self.assertNotEqual(fixture.batch["batch_sha256"],
                                reserved["controller_source_committed"]["source_batch_sha256"])
            self.assertFalse(fixture.case.archive_path(fixture.batch).exists())
            self.worker(recover, (resident, fixture, reserved, raw), 0)
            self.assertEqual(fixture.case.archive_path(fixture.batch).read_bytes(), raw)
            with resident.resident_owner(fixture) as owner:
                completed = owner.load_memo()
            self.assertIn("controller_source_committed", completed)
            self.assertNotIn("controller_source_pending", completed)
            self.assertEqual(completed["pulse_seq"], reserved["pulse_seq"])


if __name__ == "__main__":
    unittest.main()
