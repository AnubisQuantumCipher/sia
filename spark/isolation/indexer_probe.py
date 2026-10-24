"""Runs only inside the disposable namespace experiment."""
import errno
import json
import os
from pathlib import Path
import socket
import sys


def main():
    port = int(sys.argv[1])
    namespaces = {name: str(Path("/proc/self/ns", name).readlink())
                  for name in ("user", "pid", "ipc", "uts", "net")}
    with open("/proc/self/status") as status_file:
        raw = status_file.read(8193)
    if len(raw) > 8192:
        raise RuntimeError("process status exceeded declared bound")
    status = dict(line.split(":", 1) for line in raw.splitlines())
    for name in ("CapEff", "CapPrm", "CapAmb"):
        if int(status[name].strip(), 16) != 0:
            raise RuntimeError("process retained capabilities")
    if status["NoNewPrivs"].strip() != "1":
        raise RuntimeError("no-new-privileges missing")
    try:
        os.unshare(os.CLONE_NEWUSER)
    except OSError as error:
        if error.errno != errno.ENOSPC:
            raise
        nested_errno = error.errno
    else:
        raise RuntimeError("nested user namespace was permitted")
    exported = Path("/source/record")
    if exported.read_bytes() != b"source-evidence\n":
        raise RuntimeError("source export unreadable or changed")
    try:
        exported.write_bytes(b"unauthorized-change")
    except OSError as error:
        if error.errno != errno.EROFS:
            raise
    else:
        raise RuntimeError("read-only export was writable")
    if Path(sys.argv[2]).exists() or Path("/home").exists():
        raise RuntimeError("unexported host data visible")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as network:
        network.settimeout(1)
        try:
            network.connect(("127.0.0.1", port))
        except OSError as error:
            if error.errno not in (errno.ECONNREFUSED, errno.ENETUNREACH):
                raise
            refused_errno = error.errno
        else:
            raise RuntimeError("host loopback listener reachable")
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as broker:
        broker.settimeout(3)
        broker.connect("/embedding.sock")
        if broker.send(b"bounded-test-request") != len(b"bounded-test-request"):
            raise RuntimeError("partial broker request")
        if broker.recv(64) != b"bounded-test-response":
            raise RuntimeError("broker response mismatch")
    print(json.dumps({"status": "TESTED", "source_read": True,
                      "source_write_errno": errno.EROFS,
                      "host_loopback_errno": refused_errno,
                      "broker_response": "matched",
                      "namespaces": namespaces,
                      "capabilities": {name: status[name].strip()
                                       for name in ("CapEff", "CapPrm", "CapAmb")},
                      "no_new_privileges": status["NoNewPrivs"].strip(),
                      "nested_user_namespace_errno": nested_errno}))


if __name__ == "__main__":
    main()
