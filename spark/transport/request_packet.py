"""Experimental Linux packet intake; no policy decision or mutation authority.

The caller owns one connected, nonblocking AF_UNIX/SOCK_SEQPACKET socket and
enables SO_PASSCRED before accepting input. One call consumes at most one
packet. A service must separately bound connections, scheduling and retries.
"""
import array
from dataclasses import dataclass
import os
import socket
import struct

FRAME_BYTES = 192
CREDENTIAL_BYTES = struct.calcsize("3i")
# Space for credentials and one descriptor control message lets us explicitly
# close delivered rights; Linux closes excess rights truncated by this bound.
CONTROL_BYTES = (socket.CMSG_SPACE(CREDENTIAL_BYTES)
                 + socket.CMSG_SPACE(array.array("i").itemsize))


class IntakeRefusal(Exception):
    """A packet cannot be supplied to the syntax decoder."""


@dataclass(frozen=True)
class Packet:
    payload: bytes
    pid: int
    uid: int
    gid: int


def _credentials(ancillary):
    credentials = []
    unexpected = False
    cleanup_failed = False
    for level, kind, content in ancillary:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
            # Kernel-delivered descriptors are ours even when refusing input.
            descriptors = array.array("i")
            size = len(content) - len(content) % descriptors.itemsize
            descriptors.frombytes(content[:size])
            for descriptor in descriptors:
                try:
                    os.close(descriptor)
                except OSError:
                    # Attempt every delivered descriptor, but never retry a
                    # Linux close: its number may already have been reused.
                    cleanup_failed = True
            unexpected = True
        elif level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS:
            if len(content) != CREDENTIAL_BYTES:
                unexpected = True
            else:
                credentials.append(struct.unpack("3i", content))
        else:
            unexpected = True
    if cleanup_failed:
        raise IntakeRefusal("descriptor-cleanup-failed")
    if unexpected or len(credentials) != 1 or credentials[0][0] <= 0:
        raise IntakeRefusal("unexpected-or-missing-credentials")
    return credentials[0]


def receive_once(channel):
    """Return one bounded packet, or None if not currently readable.

    Credentials identify this packet's sender, not a capability or a grant.
    Kernel socket semantics and Python's recvmsg binding remain assumptions.
    """
    if channel.family != socket.AF_UNIX or channel.gettimeout() != 0.0:
        raise IntakeRefusal("nonblocking-unix-socket-required")
    if channel.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_SEQPACKET:
        raise IntakeRefusal("sequenced-packet-socket-required")
    if channel.getsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED) != 1:
        raise IntakeRefusal("per-packet-credentials-required")
    frame = bytearray(FRAME_BYTES)
    try:
        length, ancillary, flags, _address = channel.recvmsg_into(
            [frame], CONTROL_BYTES, socket.MSG_DONTWAIT | socket.MSG_CMSG_CLOEXEC)
    except BlockingIOError:
        return None
    credentials = _credentials(ancillary)
    if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
        raise IntakeRefusal("truncated-packet-or-control")
    if length != FRAME_BYTES:
        raise IntakeRefusal("incorrect-packet-length")
    return Packet(bytes(frame), *credentials)
