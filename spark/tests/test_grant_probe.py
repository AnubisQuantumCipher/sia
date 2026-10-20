"""Disposable grant-file/packet handoff; no authenticated service installed."""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest

from test_admission_probe import fixture_frame
from test_grant_record import grant
from test_request_probe import ROOT, packet

PROBE = ROOT / "bin/grant_probe"


def encoded_record(frame, subject, active=1, start=10, end=20):
    return (f"sia-grant-v1\nsubject={subject}\nnot-before={start}\nexpires={end}\n"
            f"active={active}\nrequest={bytes(frame).hex()}\n").encode("ascii")


def invoke(observed, received, now=10):
    # All metadata remains test-supplied: no issuer or clock authentication.
    command = [str(PROBE), str(observed.subject), str(received.uid), str(now),
               str(observed.not_before), str(observed.expires),
               "1" if observed.active else "0"]
    return subprocess.run(command, input=observed.expected_frame + received.payload,
                          capture_output=True, timeout=5, check=False)


class GrantHandoff(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PROBE.is_file(), "build request_probe.gpr first")
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, self.fd)
        self.reader, self.writer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(self.reader.close)
        self.addCleanup(self.writer.close)
        self.reader.setblocking(False)
        self.reader.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)

    def observed(self, frame, **fields):
        fields.setdefault("subject", os.getuid())
        path = self.root / grant.GRANT_NAME
        path.write_bytes(encoded_record(frame, **fields))
        path.chmod(0o600)
        return grant.load_record(self.fd)

    def received(self, frame):
        self.assertEqual(self.writer.send(frame), len(frame))
        value = packet.receive_once(self.reader)
        self.assertIsNotNone(value)
        self.assertEqual(value.uid, os.getuid())
        return value

    def decision(self, result, expected):
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(result.stdout, expected)

    def test_loaded_grant_and_kernel_packet_reach_classifier(self):
        for action, expected in ((1, b"O"), (2, b"P")):
            frame = fixture_frame(action)
            self.decision(invoke(self.observed(frame), self.received(frame)), expected)
            # A different valid payload is allowed only by a matching grant.
            frame[104:136] = bytes(range(32))
            self.decision(invoke(self.observed(frame), self.received(frame)), expected)

    def test_revocation_identity_and_interval_are_decided_by_policy(self):
        frame = fixture_frame()
        received = self.received(frame)
        foreign = 1 if received.uid == 0 else 0
        for fields in ({"active": 0}, {"subject": foreign}, {"end": 10},
                       {"start": 20, "end": 10}):
            with self.subTest(fields=fields):
                self.decision(invoke(self.observed(frame, **fields), received), b"D")
        observed = self.observed(frame)
        for now, expected in ((9, b"D"), (10, b"P"), (19, b"P"), (20, b"D")):
            self.decision(invoke(observed, received, now), expected)

    def test_each_grant_byte_change_refuses_original_request(self):
        frame = fixture_frame()
        received = self.received(frame)
        for index in range(len(frame)):
            changed = frame.copy()
            changed[index] ^= 1
            with self.subTest(index=index):
                self.decision(invoke(self.observed(changed), received), b"D")

    def test_invalid_grant_or_request_never_classifies_as_proposal(self):
        frame = fixture_frame()
        for expected, request in ((bytes(192), frame), (frame, bytes(192)),
                                  (bytes(192), bytes(192))):
            self.decision(invoke(self.observed(expected), self.received(request)), b"D")

    def test_zero_capability_and_action_mismatch_deny(self):
        zero = fixture_frame()
        zero[8:40] = bytes(32)
        self.decision(invoke(self.observed(zero), self.received(zero)), b"D")
        for grant_action, request_action in ((1, 2), (2, 1)):
            self.decision(invoke(self.observed(fixture_frame(grant_action)),
                                 self.received(fixture_frame(request_action))), b"D")

    def test_argument_count_and_scalar_maxima(self):
        command = [str(PROBE), "4294967295", "4294967295",
                   "9223372036854775806", "0", "9223372036854775807", "1"]
        pair = bytes(fixture_frame()) * 2
        self.decision(subprocess.run(command, input=pair, capture_output=True, timeout=5), b"P")
        command[3] = "9223372036854775807"
        self.decision(subprocess.run(command, input=pair, capture_output=True, timeout=5), b"D")
        for changed in (command[:-1], command + ["0"]):
            result = subprocess.run(changed, input=pair, capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")

    def test_complete_pair_waits_for_eof_and_small_writes_preserve_length(self):
        command = [str(PROBE), "0", "0", "10", "10", "20", "1"]
        pair = bytes(fixture_frame()) * 2
        for suffix in (b"", b"x"):
            with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE) as child:
                try:
                    # Kernel coalescing is allowed; this does not force syscall fragmentation.
                    for byte in pair:
                        child.stdin.write(bytes((byte,)))
                        child.stdin.flush()
                    with self.assertRaises(subprocess.TimeoutExpired):
                        child.wait(timeout=0.05)
                    child.stdin.write(suffix)
                    child.stdin.close()
                    child.stdin = None
                    stdout, stderr = child.communicate(timeout=5)
                    self.assertEqual(stderr, b"")
                    self.assertEqual(stdout, b"" if suffix else b"P")
                    self.assertEqual(child.returncode == 0, not suffix)
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.communicate(timeout=5)

    def test_exact_pair_and_canonical_metadata_required(self):
        frame = fixture_frame()
        command = [str(PROBE), "0", "0", "10", "10", "20", "1"]
        pair = bytes(frame) * 2
        for body in (b"", pair[:-1], pair + b"x", bytes(frame)):
            result = subprocess.run(command, input=body, capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")
        for index, bad in ((1, "00"), (1, "4294967296"), (3, "-1"),
                           (4, "9223372036854775808"), (5, " 20"), (6, "true")):
            changed = command.copy()
            changed[index] = bad
            result = subprocess.run(changed, input=pair, capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")

    def test_input_and_output_descriptor_errors_fail(self):
        command = [str(PROBE), "0", "0", "10", "10", "20", "1"]
        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            result = subprocess.run(command, stdin=directory, capture_output=True, timeout=5)
        finally:
            os.close(directory)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        with open("/dev/full", "wb") as full:
            result = subprocess.run(command, input=bytes(fixture_frame()) * 2,
                                    stdout=full, stderr=subprocess.PIPE, timeout=5)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
