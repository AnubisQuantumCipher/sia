"""RED coverage for fixture cleanup before an AF_UNIX bind can succeed.

These tests execute the actual lifecycle testcase through TestCase.run and
its normal cleanup stack, but inject a bind failure into real sockets. A
process-launch guard ensures that no release worker or source process runs.
The intercepted sockets stay referenced until after assertions, so garbage
collection cannot hide an unclosed descriptor. Our final cleanup releases
any deliberately exposed leak without making the nested testcase pass.
"""

import contextlib
import errno
import socket
import tempfile
import unittest
from unittest import mock

from tests import test_lifecycle_process_ownership as lifecycle_tests


class _RecordingResult(unittest.TestResult):
    """Keep error identity without changing unittest's error bookkeeping."""

    def __init__(self):
        super().__init__()
        self.observed_errors = []

    def addError(self, test, err):
        self.observed_errors.append(err[1])
        super().addError(test, err)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self.observed_errors.append(err[1])
        super().addSubTest(test, subtest, err)


class LifecycleFixtureCleanup(unittest.TestCase):
    @contextlib.contextmanager
    def refused_bind(self):
        channels, attempts, temporaries = [], [], []
        real_socket = socket.socket
        real_temporary = tempfile.TemporaryDirectory
        failure = OSError(errno.ENAMETOOLONG, "synthetic fixture bind refusal")

        class RefusedBindSocket(real_socket):
            def bind(self, address):
                attempts.append((self, address))
                raise failure

        def socket_factory(*args, **kwargs):
            channel = RefusedBindSocket(*args, **kwargs)
            channels.append(channel)
            return channel

        def temporary_factory(*args, **kwargs):
            temporary = real_temporary(*args, **kwargs)
            temporaries.append(temporary)
            return temporary

        try:
            with mock.patch.object(lifecycle_tests.socket, "socket", socket_factory), \
                    mock.patch.object(lifecycle_tests.tempfile, "TemporaryDirectory",
                                      temporary_factory), \
                    mock.patch.object(lifecycle_tests.subprocess, "Popen",
                                      side_effect=AssertionError(
                                          "bind-failure fixture reached process launch")) as launch:
                yield channels, attempts, failure, launch
        finally:
            # These are only the actual sockets/temporary directories created
            # by this nested test run; retain and close them even in RED.
            for channel in channels:
                channel.close()
            for temporary in temporaries:
                temporary.cleanup()

    def assert_bind_failure_preserved_and_sockets_closed(
            self, result, channels, attempts, failure, launch):
        launch.assert_not_called()
        self.assertTrue(attempts, "actual fixture never reached socket.bind")
        self.assertEqual([channel for channel, _address in attempts], channels)
        self.assertEqual(result.failures, [])
        self.assertEqual(result.skipped, [])
        self.assertTrue(result.errors, "nested test lost the injected bind error")
        self.assertEqual(result.observed_errors, [failure for _attempt in attempts])
        for error in result.observed_errors:
            self.assertIs(error, failure)
            self.assertEqual(error.errno, errno.ENAMETOOLONG)
        for channel, address in attempts:
            with self.subTest(address=address):
                self.assertEqual(channel.family, socket.AF_UNIX)
                self.assertEqual(channel.type, socket.SOCK_STREAM)
                self.assertEqual(
                    channel.fileno(), -1,
                    "socket remained open after actual testcase cleanup: " + str(address))

    def test_release_root_rebind_fixture_closes_socket_when_bind_fails(self):
        subject = lifecycle_tests.LifecycleProcessOwnershipTests(
            "test_admitted_worker_keeps_original_release_root_after_path_rebind")
        result = _RecordingResult()
        with self.refused_bind() as (channels, attempts, failure, launch):
            subject.run(result)
            self.assert_bind_failure_preserved_and_sockets_closed(
                result, channels, attempts, failure, launch)

    def test_release_rig_constructor_closes_socket_through_testcase_cleanup(self):
        class RigConstruction(unittest.TestCase):
            def runTest(self):
                # Constructor failure occurs before a rig can enter its own
                # context manager. Its acquisition must already be owned.
                lifecycle_tests._ReleaseRig(self, "install.sh")
                self.fail("injected socket.bind failure did not propagate")

        subject = RigConstruction()
        result = _RecordingResult()
        with self.refused_bind() as (channels, attempts, failure, launch):
            subject.run(result)
            self.assert_bind_failure_preserved_and_sockets_closed(
                result, channels, attempts, failure, launch)


if __name__ == "__main__":
    unittest.main()
