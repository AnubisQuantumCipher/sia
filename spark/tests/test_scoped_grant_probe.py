"""Test-only v2 grant/packet/lifetime handoff; inputs are not authenticated."""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest

from test_admission_probe import fixture_frame
from test_grant_probe import encoded_record
from test_grant_record import grant
from test_request_probe import ROOT, packet

PROBE = ROOT / "bin/scoped_grant_probe"
BOOT = bytes(range(32))
SERVICE = bytes(range(32, 64))


class ScopedHandoff(unittest.TestCase):
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

    def inputs(self, expected=None, request=None, boot=BOOT, service=SERVICE, **fields):
        if expected is None:
            expected = fixture_frame()
        if request is None:
            request = expected
        fields.setdefault("subject", os.getuid())
        raw = (b"sia-grant-v2\nboot=" + boot.hex().encode("ascii")
               + b"\nservice=" + service.hex().encode("ascii") + b"\n"
               + encoded_record(expected, **fields).split(b"\n", 1)[1])
        path = self.root / grant.GRANT_NAME
        path.write_bytes(raw)
        path.chmod(0o600)
        observed = grant.load_scoped_record(self.fd)
        self.assertEqual(self.writer.send(request), len(request))
        received = packet.receive_once(self.reader)
        self.assertIsNotNone(received)
        self.assertEqual(received.uid, os.getuid())
        metadata = observed.grant
        command = [str(PROBE), str(metadata.subject), str(received.uid), "10",
                   str(metadata.not_before), str(metadata.expires),
                   "1" if metadata.active else "0"]
        return command, observed.boot + observed.service, metadata.expected_frame + received.payload

    def run_probe(self, inputs, current=BOOT + SERVICE):
        command, retained, frames = inputs
        return subprocess.run(command, input=retained + current + frames,
                              capture_output=True, timeout=5, check=False)

    def decision(self, result, expected):
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, expected, b""))

    def test_loaded_v2_and_actual_packet_classify_both_operations(self):
        for action, expected in ((1, b"O"), (2, b"P")):
            frame = fixture_frame(action)
            frame[104:136] = bytes(range(64, 96))
            self.decision(self.run_probe(self.inputs(expected=frame)), expected)

    def test_every_current_and_retained_domain_byte_is_binding(self):
        command, retained, frames = self.inputs()
        for index in range(len(retained)):
            changed = bytearray(retained)
            changed[index] ^= 1
            with self.subTest(index=index):
                self.decision(self.run_probe((command, retained, frames), bytes(changed)), b"D")
                self.decision(self.run_probe((command, bytes(changed), frames)), b"D")
        self.decision(self.run_probe((command, retained, frames), SERVICE + BOOT), b"D")

    def test_matching_zero_domains_are_denied_by_ada(self):
        for boot, service in ((bytes(32), SERVICE), (BOOT, bytes(32)), (bytes(32), bytes(32))):
            self.decision(self.run_probe(self.inputs(boot=boot, service=service), boot + service), b"D")

    def test_scope_match_preserves_original_policy_refusals(self):
        foreign = 1 if os.getuid() == 0 else 0
        for fields in ({"active": 0}, {"subject": foreign}, {"end": 10}, {"start": 20}):
            self.decision(self.run_probe(self.inputs(**fields)), b"D")
        changed = fixture_frame()
        changed[104] ^= 1
        self.decision(self.run_probe(self.inputs(request=changed)), b"D")
        for expected, request in ((bytes(192), fixture_frame()), (fixture_frame(), bytes(192))):
            self.decision(self.run_probe(self.inputs(expected=expected, request=request)), b"D")

    def test_exact_input_and_canonical_metadata_are_required(self):
        command, retained, frames = self.inputs()
        body = retained + BOOT + SERVICE + frames
        for size in (0, 31, 32, 63, 64, 95, 96, 127, 128, 319, 320, 511):
            result = subprocess.run(command, input=body[:size], capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")
        result = subprocess.run(command, input=body + b"x", capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        for index, bad in ((1, "00"), (1, "4294967296"), (3, "-1"),
                           (4, "9223372036854775808"), (5, " 20"), (6, "true")):
            changed = command.copy()
            changed[index] = bad
            result = subprocess.run(changed, input=body, capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")

    def test_eof_wait_and_descriptor_errors_are_not_success(self):
        command, retained, frames = self.inputs()
        body = retained + BOOT + SERVICE + frames
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE) as child:
            try:
                child.stdin.write(body)
                child.stdin.flush()
                with self.assertRaises(subprocess.TimeoutExpired):
                    child.wait(timeout=0.05)
                stdout, stderr = child.communicate(timeout=5)
                self.assertEqual((child.returncode, stdout, stderr), (0, b"P", b""))
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate(timeout=5)
        result = subprocess.run(command, stdin=self.fd, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        with open("/dev/full", "wb") as full:
            result = subprocess.run(command, input=body, stdout=full,
                                    stderr=subprocess.PIPE, timeout=5)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
