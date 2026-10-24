"""Test-only socket/credential handoff into the pure composed admission entry."""
import os
import socket
import subprocess
import unittest

from test_request_probe import ROOT, packet

PROBE = ROOT / "bin/admission_probe"


def fixture_frame(action=2):
    body = bytearray(192)
    body[:4] = bytes((1, action, 2, 3))
    for start, fill in ((8, 1), (40, 2), (72, 3), (104, 4), (136, 5)):
        body[start:start + 32] = bytes((fill,)) * 32
    body[175], body[183] = 6, 7
    return body


def invoke(payload, subject, sender, now=10, action="propose"):
    # Fixed-output trusted fixture only. This is not a production grant broker.
    return subprocess.run([str(PROBE), str(subject), str(sender), str(now), action],
                          input=payload, capture_output=True, timeout=5,
                          check=False)


class AdmissionProbe(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PROBE.is_file(), "build request_probe.gpr first")
        self.reader, self.writer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(self.reader.close)
        self.addCleanup(self.writer.close)
        self.reader.setblocking(False)
        self.reader.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)

    def receive(self, payload):
        self.assertEqual(self.writer.send(payload), len(payload))
        received = packet.receive_once(self.reader)
        self.assertIsNotNone(received)
        self.assertEqual(received.uid, os.getuid())
        return received

    def decision(self, result, expected):
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(result.stdout, expected)

    def test_real_packet_uid_and_bytes_reach_composed_policy(self):
        for action, name, expected in ((1, "observe", b"O"), (2, "propose", b"P")):
            received = self.receive(fixture_frame(action))
            self.decision(invoke(received.payload, os.getuid(), received.uid,
                                 action=name), expected)
            foreign = 1 if received.uid == 0 else 0
            self.decision(invoke(received.payload, foreign, received.uid,
                                 action=name), b"D")
            self.decision(invoke(received.payload, os.getuid(), received.uid,
                                 now=20, action=name), b"D")

    def test_every_changed_byte_refuses_against_original_grant(self):
        base = fixture_frame()
        for index in range(len(base)):
            changed = base.copy()
            changed[index] ^= 1
            received = self.receive(changed)
            with self.subTest(index=index):
                self.decision(invoke(received.payload, os.getuid(), received.uid), b"D")

    def test_action_and_time_boundaries(self):
        for action, wrong_grant in ((1, "propose"), (2, "observe")):
            received = self.receive(fixture_frame(action))
            self.decision(invoke(received.payload, received.uid, received.uid,
                                 action=wrong_grant), b"D")
        received = self.receive(fixture_frame())
        for now, expected in ((9, b"D"), (19, b"P")):
            self.decision(invoke(received.payload, received.uid, received.uid,
                                 now=now), expected)

    def test_metadata_count_and_exact_scalar_maxima(self):
        base = [str(PROBE), "0", "0", "10", "propose"]
        for command in (base[:-1], base + ["extra"]):
            result = subprocess.run(command, input=fixture_frame(), capture_output=True,
                                    timeout=5, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")
        self.decision(invoke(fixture_frame(), "4294967295", "4294967295"), b"P")
        self.decision(invoke(fixture_frame(), 0, 0, "9223372036854775807"), b"D")

    def test_adapter_refuses_short_or_trailing_stream(self):
        base = fixture_frame()
        for payload in (base[:-1], base + b"x", b""):
            self.decision(invoke(payload, os.getuid(), os.getuid()), b"D")

    def test_bad_fixture_metadata_is_process_failure(self):
        for subject, sender, now, action in (
                (-1, 0, 10, "propose"), (0, "x", 10, "propose"),
                (0, 0, -1, "propose"), (0, 0, "9" * 20, "propose"),
                ("4294967296", 0, 10, "propose"),
                (0, 0, "9223372036854775808", "propose"),
                (0, 0, 10, "mutate")):
            result = invoke(fixture_frame(), subject, sender, now, action)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")

    def test_io_errors_are_not_successful_policy_denials(self):
        command = [str(PROBE), str(os.getuid()), str(os.getuid()), "10", "propose"]
        descriptor = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            result = subprocess.run(command, stdin=descriptor, capture_output=True,
                                    timeout=5, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")
        finally:
            os.close(descriptor)
        with open("/dev/full", "wb", buffering=0) as full:
            result = subprocess.run(command, input=fixture_frame(), stdout=full,
                                    stderr=subprocess.PIPE, timeout=5, check=False)
            self.assertNotEqual(result.returncode, 0)
        descriptor = os.open(__file__, os.O_RDONLY | os.O_CLOEXEC)
        try:
            result = subprocess.run(command, input=fixture_frame(), stdout=descriptor,
                                    stderr=subprocess.PIPE, timeout=5, check=False)
            self.assertNotEqual(result.returncode, 0)
        finally:
            os.close(descriptor)


if __name__ == "__main__":
    unittest.main()
