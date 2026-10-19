"""Real Linux socket tests; these do not establish policy authorization."""
import array
import errno
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "transport/request_packet.py"
SPEC = importlib.util.spec_from_file_location("request_packet", SOURCE)
packet = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = packet
SPEC.loader.exec_module(packet)


class RequestPacket(unittest.TestCase):
    def setUp(self):
        self.reader, self.writer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(self.reader.close)
        self.addCleanup(self.writer.close)
        self.reader.setblocking(False)
        self.reader.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)

    def test_exact_payload_and_kernel_sender(self):
        body = bytes(range(192))
        self.assertEqual(self.writer.send(body), len(body))
        observed = packet.receive_once(self.reader)
        self.assertEqual(observed.payload, body)
        self.assertEqual((observed.pid, observed.uid, observed.gid),
                         (os.getpid(), os.getuid(), os.getgid()))

    def test_empty_queue_returns_without_waiting(self):
        self.assertIsNone(packet.receive_once(self.reader))

    def test_credentials_identify_actual_child_sender(self):
        code = ("import socket,sys; "
                "s=socket.socket(fileno=int(sys.argv[1])); "
                "s.sendall(b'x'*192); s.close()")
        with subprocess.Popen([sys.executable, "-c", code, str(self.writer.fileno())],
                              pass_fds=(self.writer.fileno(),)) as child:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
                self.fail("child sender deadline exceeded")
            self.assertEqual(child.returncode, 0)
            observed = packet.receive_once(self.reader)
            self.assertEqual(observed.pid, child.pid)
            self.assertEqual((observed.uid, observed.gid), (os.getuid(), os.getgid()))

    def test_every_short_length_and_oversize_refuse(self):
        for length in (*range(192), 193, 4096):
            with self.subTest(length=length):
                self.assertEqual(self.writer.send(b"x" * length), length)
                with self.assertRaises(packet.IntakeRefusal):
                    packet.receive_once(self.reader)

    def test_packets_are_not_concatenated(self):
        self.writer.sendall(b"x" * 96)
        self.writer.sendall(b"y" * 96)
        for _ in range(2):
            with self.assertRaisesRegex(packet.IntakeRefusal, "incorrect-packet-length"):
                packet.receive_once(self.reader)
        self.assertIsNone(packet.receive_once(self.reader))

    def test_attached_descriptors_refuse_without_leak(self):
        descriptor = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
        self.addCleanup(os.close, descriptor)
        before = set(os.listdir("/proc/self/fd"))
        for count in (1, 16):
            rights = array.array("i", [descriptor] * count)
            self.writer.sendmsg([b"x" * 192],
                                [(socket.SOL_SOCKET, socket.SCM_RIGHTS, rights)])
            with patch.object(packet.os, "close", wraps=os.close) as close:
                with self.assertRaises(packet.IntakeRefusal):
                    packet.receive_once(self.reader)
                self.assertGreater(close.call_count, 0)
            self.assertEqual(set(os.listdir("/proc/self/fd")), before)

    def test_blocking_and_missing_credentials_configuration_refuse(self):
        self.reader.setblocking(True)
        with self.assertRaisesRegex(packet.IntakeRefusal, "nonblocking"):
            packet.receive_once(self.reader)
        self.reader.setblocking(False)
        self.reader.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 0)
        with self.assertRaisesRegex(packet.IntakeRefusal, "credentials"):
            packet.receive_once(self.reader)

    def test_cleanup_attempts_remaining_descriptors_after_error(self):
        descriptors = [os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
                       for _ in range(3)]
        original_close = os.close
        attempted = []

        def close_then_fail_first(descriptor):
            attempted.append(descriptor)
            original_close(descriptor)
            if len(attempted) == 1:
                raise OSError(errno.EIO, "injected close error")

        try:
            controls = [(socket.SOL_SOCKET, socket.SCM_RIGHTS,
                         array.array("i", descriptors).tobytes())]
            with patch.object(packet.os, "close", side_effect=close_then_fail_first):
                with self.assertRaisesRegex(packet.IntakeRefusal, "cleanup-failed"):
                    packet._credentials(controls)
            self.assertEqual(attempted, descriptors)
        finally:
            for descriptor in descriptors:
                if descriptor not in attempted:
                    original_close(descriptor)

    def test_stream_socket_refuses(self):
        left, right = socket.socketpair()
        with left, right:
            left.setblocking(False)
            with self.assertRaisesRegex(packet.IntakeRefusal, "sequenced-packet"):
                packet.receive_once(left)

    def test_closed_sender_refuses(self):
        self.writer.close()
        with self.assertRaises(packet.IntakeRefusal):
            packet.receive_once(self.reader)


if __name__ == "__main__":
    unittest.main()
