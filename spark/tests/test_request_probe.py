"""Socket-to-Ada test adapter integration; no live service or authority."""
import importlib.util
import os
from pathlib import Path
import random
import socket
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "probe_packet", ROOT / "transport/request_packet.py")
packet = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = packet
SPEC.loader.exec_module(packet)
PROBE = ROOT / "bin/request_probe"


def run_probe(payload):
    # This exact test binary emits a fixed 193-byte response. This is not a
    # general subprocess broker or a safe runner for untrusted executables.
    result = subprocess.run([str(PROBE)], input=payload, capture_output=True,
                            timeout=5, check=True)
    if result.stderr or len(result.stdout) != 193:
        raise AssertionError("unexpected probe output")
    return result.stdout


class RequestProbe(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PROBE.is_file(), "build spark/transport/request_probe.gpr first")
        self.reader, self.writer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(self.reader.close)
        self.addCleanup(self.writer.close)
        self.reader.setblocking(False)
        self.reader.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)

    def through_socket(self, body):
        self.assertEqual(self.writer.send(body), len(body))
        received = packet.receive_once(self.reader)
        self.assertIsNotNone(received)
        return run_probe(received.payload)

    def test_all_supported_phase_pairs_and_actions(self):
        generator = random.Random(20261019)
        for action in (1, 2):
            for before in range(11):
                for after in range(11):
                    body = bytearray(192)
                    body[:4] = bytes((1, action, before, after))
                    body[8:184] = generator.randbytes(176)
                    body[168] &= 127
                    body[176] &= 127
                    with self.subTest(action=action, before=before, after=after):
                        self.assertEqual(self.through_socket(body), b"\x01" + body)

    def test_generation_and_identity_boundaries(self):
        for fill in (0, 255):
            body = bytearray(192)
            body[:4] = bytes((1, 2, 0, 10))
            body[8:184] = bytes((fill,)) * 176
            body[168] &= 127
            body[176] &= 127
            self.assertEqual(self.through_socket(body), b"\x01" + body)

    def test_supported_length_does_not_imply_valid_syntax(self):
        base = bytearray(192)
        base[:4] = bytes((1, 1, 0, 1))
        bad_values = ((0, 0), (0, 2), (1, 0), (1, 3), (2, 11),
                      (3, 11), (168, 128), (176, 128))
        for index, value in (*bad_values, *((i, 1) for i in (*range(4, 8), *range(184, 192)))):
            body = base.copy()
            body[index] = value
            with self.subTest(index=index, value=value):
                self.assertEqual(self.through_socket(body), bytes(193))

    def test_probe_also_rejects_incorrect_raw_input_length(self):
        valid = bytes((1, 1, 0, 1)) + bytes(188)
        self.assertEqual(run_probe(valid), b"\x01" + valid)
        for length in (*range(192), 193, 4096):
            with self.subTest(length=length):
                body = valid[:length] if length < 192 else valid + b"x" * (length - 192)
                self.assertEqual(run_probe(body), bytes(193))

    def test_probe_consumes_fragmented_stream(self):
        body = bytes((1, 1, 0, 1)) + bytes(188)
        with subprocess.Popen([str(PROBE)], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as child:
            try:
                for offset in range(0, 192, 3):
                    child.stdin.write(body[offset:offset + 3])
                    child.stdin.flush()
                output, error = child.communicate(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                child.kill()
                child.communicate(timeout=5)
                raise
            self.assertEqual(child.returncode, 0)
            self.assertEqual(error, b"")
            self.assertEqual(output, b"\x01" + body)

    def test_exact_prefix_waits_for_eof_before_accepting(self):
        body = bytes((1, 1, 0, 1)) + bytes(188)
        with subprocess.Popen([str(PROBE)], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as child:
            try:
                child.stdin.write(body)
                child.stdin.flush()
                with self.assertRaises(subprocess.TimeoutExpired):
                    child.wait(timeout=0.2)
                output, error = child.communicate(timeout=5)
                self.assertEqual(child.returncode, 0)
                self.assertEqual(error, b"")
                self.assertEqual(output, b"\x01" + body)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate(timeout=5)

    def test_read_error_is_not_a_successful_refusal_response(self):
        descriptor = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            result = subprocess.run([str(PROBE)], stdin=descriptor,
                                    capture_output=True, timeout=5)
        finally:
            os.close(descriptor)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")

    def test_output_failure_returns_failure_status(self):
        with open("/dev/full", "wb", buffering=0) as output:
            result = subprocess.run([str(PROBE)], input=bytes(192), stdout=output,
                                    stderr=subprocess.PIPE, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, b"")


if __name__ == "__main__":
    unittest.main()
