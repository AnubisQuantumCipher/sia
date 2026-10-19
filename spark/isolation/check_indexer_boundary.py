"""Disposable Linux boundary experiment, not a service installer."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile


def broker_once(listener):
    connection, _ = listener.accept()
    with connection:
        connection.settimeout(3)
        if connection.recv(64) != b"bounded-test-request":
            raise RuntimeError("broker request mismatch")
        if connection.send(b"bounded-test-response") != len(b"bounded-test-response"):
            raise RuntimeError("partial broker response")


def host_positive(listener):
    with socket.create_connection(listener.getsockname(), timeout=1) as client:
        connection, _ = listener.accept()
        with connection:
            connection.sendall(b"reachable")
        if client.recv(32) != b"reachable":
            raise RuntimeError("host listener positive control failed")


def command(bwrap, root, probe, port):
    return [bwrap, "--unshare-user", "--unshare-net", "--unshare-pid",
            "--unshare-ipc", "--unshare-uts", "--disable-userns",
            "--die-with-parent", "--new-session", "--cap-drop", "ALL",
            "--clearenv", "--setenv", "PATH", "/usr/bin",
            "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib",
            "--proc", "/proc", "--dev", "/dev",
            "--ro-bind", str(root / "export"), "/source",
            "--ro-bind", str(root / "embedding.sock"), "/embedding.sock",
            "--ro-bind", str(probe), "/probe.py", "--chdir", "/",
            "--", "/usr/bin/python3", "-I", "-B", "/probe.py", str(port),
            str(root / "host-secret")]


def experiment(root, output, bwrap, probe):
    namespace_control = subprocess.run(
        ["/usr/bin/unshare", "--user", "--map-root-user", "/usr/bin/true"],
        capture_output=True, timeout=3, check=True)
    if namespace_control.stdout or namespace_control.stderr:
        raise RuntimeError("unexpected host namespace positive-control output")
    export = root / "export"
    export.mkdir()
    (export / "record").write_bytes(b"source-evidence\n")
    (root / "host-secret").write_bytes(b"not-exported\n")
    with socket.socket() as network, socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as broker:
        network.settimeout(3)
        network.bind(("127.0.0.1", 0))
        network.listen(1)
        host_positive(network)
        broker.settimeout(5)
        broker.bind(str(root / "embedding.sock"))
        broker.listen(1)
        invocation = command(bwrap, root, probe, network.getsockname()[1])
        (output / "command.json").write_text(json.dumps(invocation) + "\n")
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(broker_once, broker)
            result = subprocess.run(invocation, stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=10, check=False,
                                    close_fds=True)
            (output / "child.stdout").write_bytes(result.stdout)
            (output / "child.stderr").write_bytes(result.stderr)
            (output / "child.exit").write_text(str(result.returncode) + "\n")
            if result.returncode or result.stderr:
                raise RuntimeError("sandbox experiment failed; inspect retained output")
            future.result(timeout=5)
    observed = json.loads(result.stdout)
    host_namespaces = {name: str(Path("/proc/self/ns", name).readlink())
                       for name in ("user", "pid", "ipc", "uts", "net")}
    for name, identity in host_namespaces.items():
        if observed["namespaces"][name] == identity:
            raise RuntimeError(name + " namespace did not change")
    if (export / "record").read_bytes() != b"source-evidence\n":
        raise RuntimeError("host source changed")
    return {"status": "TESTED", "host_listener_positive": True,
            "host_namespaces": host_namespaces, "child": observed,
            "host_user_namespace_positive": True,
            "scope": "disposable indexer boundary only; no installed service or production broker"}


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_indexer_boundary.py NEW_EVIDENCE_DIR")
    output = Path(sys.argv[1]).resolve()
    output.mkdir(mode=0o700)
    bwrap = str(Path(shutil.which("bwrap") or "/missing-bwrap").resolve(strict=True))
    probe = Path(__file__).with_name("indexer_probe.py").resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="sia-isolation-") as temporary:
        report = experiment(Path(temporary), output, bwrap, probe)
    files = {"driver": Path(__file__), "probe": probe, "bwrap": Path(bwrap),
             "python3": Path("/usr/bin/python3").resolve()}
    report["sha256"] = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                        for name, path in files.items()}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
