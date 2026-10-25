#!/usr/bin/env python3
"""Administrator-installed Ollama account guard. No privileged fallback."""

import json
import os
import selectors
import signal
import stat
import subprocess
import sys
import time


TABLE = "sia_ollama_owner_v1"
SERVICE = "sia-ollama-guard.service"
HELPER = "/usr/local/libexec/sia-ollama-guard"
CONFIG = "/etc/sia/ollama-owner"
SUDOERS = "/etc/sudoers.d/sia-ollama-guard"
UNIT = "/etc/systemd/system/" + SERVICE
LIMIT = 16384
ROOT_UNIT = """[Unit]
Description=SIA Ollama local-account firewall
DefaultDependencies=no
After=local-fs.target nftables.service ufw.service firewalld.service
Before=systemd-user-sessions.service
RequiresMountsFor=/usr/local/libexec /etc/sia

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -I -S -B /usr/local/libexec/sia-ollama-guard apply
RemainAfterExit=yes
TimeoutStartSec=45
NoNewPrivileges=yes
CapabilityBoundingSet=CAP_NET_ADMIN
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
RestrictAddressFamilies=AF_NETLINK AF_UNIX

[Install]
WantedBy=multi-user.target
"""


class Refusal(Exception):
    """A required guard property could not be established."""


def owner_uid(raw):
    """One canonical decimal Linux UID, followed by exactly one newline."""
    if not 2 <= len(raw) <= 11 or raw[-1:] != b"\n":
        raise Refusal("invalid owner UID configuration")
    digits = raw[:-1]
    if not all(48 <= octet <= 57 for octet in digits):
        raise Refusal("invalid owner UID configuration")
    uid = int(digits)
    if str(uid).encode("ascii") != digits or uid >= 4294967295:
        raise Refusal("invalid owner UID configuration")
    return uid


def _stable(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def sudoers_rule(uid):
    owner_uid(str(uid).encode("ascii") + b"\n")
    return (f"#{uid} ALL=(root) NOPASSWD: NOSETENV: /usr/bin/python3 "
            "-I -S -B /usr/local/libexec/sia-ollama-guard check-kernel\n").encode("ascii")


def _root_file(path, limit):
    """Read one bounded root-owned file through protected no-follow parents."""
    parts = path.split("/")
    if parts[0] or len(parts) > 8 or any(p in ("", ".", "..") for p in parts[1:]):
        raise Refusal("invalid protected path")
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
            info = os.fstat(directory)
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise Refusal("unprotected guard parent")
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0
                    or before.st_mode & 0o022 or before.st_nlink != 1
                    or before.st_size > limit):
                raise Refusal("unprotected guard artifact")
            raw = os.read(fd, limit + 1)
            if (len(raw) != before.st_size or len(raw) > limit
                    or _stable(before) != _stable(os.fstat(fd))):
                raise Refusal("changed or oversized guard artifact")
            named = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            if _stable(before) != _stable(named):
                raise Refusal("replaced guard artifact")
            return raw
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def _drain(process, deadline):
    """Bound capture by bytes, time and iteration count."""
    output = bytearray()
    with selectors.DefaultSelector() as selector:
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        for _ in range(LIMIT + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise Refusal("guard inspector timed out")
            chunk = os.read(process.stdout.fileno(), min(4096, LIMIT + 1 - len(output)))
            if not chunk:
                return bytes(output)
            output.extend(chunk)
            if len(output) > LIMIT:
                raise Refusal("guard inspector output exceeded limit")
    raise Refusal("guard inspector iteration limit")


def _run(argv, payload=b""):
    if len(payload) > 4096:
        raise Refusal("guard command input exceeded limit")
    deadline = time.monotonic() + 10
    process = subprocess.Popen(
        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, start_new_session=True,
        env={"PATH": "/usr/sbin:/usr/bin", "LC_ALL": "C"},
        cwd="/", close_fds=True)
    try:
        # One write smaller than Linux PIPE_BUF, into a newly empty pipe.
        process.stdin.write(payload)
        process.stdin.close()
        output = _drain(process, deadline)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Refusal("guard inspector timed out")
        return process.wait(timeout=remaining), output
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
        process.stdin.close()
        process.stdout.close()


def rules(uid):
    owner_uid(str(uid).encode("ascii") + b"\n")
    return (f"create table inet {TABLE} {{\n"
            " chain output {\n"
            "  type filter hook output priority 0; policy accept;\n"
            f"  ip daddr 127.0.0.0/8 tcp dport 11434 meta skuid != {uid} reject with tcp reset\n"
            f"  ip6 daddr ::1 tcp dport 11434 meta skuid != {uid} reject with tcp reset\n"
            " }\n chain input {\n"
            "  type filter hook input priority 0; policy accept;\n"
            '  tcp dport 11434 iifname != "lo" drop\n'
            " }\n}\n").encode("ascii")


def _match(left, right, op="=="):
    return {"match": {"op": op, "left": left, "right": right}}


def _payload(protocol, field):
    return {"payload": {"protocol": protocol, "field": field}}


def _expected(uid):
    table = {"family": "inet", "table": TABLE}
    entries = [{"table": {"family": "inet", "name": TABLE}}]
    for name in ("output", "input"):
        entries.append({"chain": dict(table, name=name, type="filter",
                                     hook=name, prio=0, policy="accept")})
    port = _match(_payload("tcp", "dport"), 11434)
    owner = _match({"meta": {"key": "skuid"}}, uid, "!=")
    for protocol, address in (("ip", {"prefix": {"addr": "127.0.0.0", "len": 8}}),
                              ("ip6", "::1")):
        expr = [_match(_payload(protocol, "daddr"), address),
                port, owner, {"reject": {"type": "tcp reset"}}]
        entries.append({"rule": dict(table, chain="output", expr=expr)})
    expr = [port, _match({"meta": {"key": "iifname"}}, "lo", "!="), {"drop": None}]
    entries.append({"rule": dict(table, chain="input", expr=expr)})
    return entries


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Refusal("duplicate inspector field")
        result[key] = value
    return result


def table_matches(raw, uid):
    if len(raw) > LIMIT:
        return False
    try:
        decoded = json.loads(raw, object_pairs_hook=_unique)
        if type(decoded) is not dict or set(decoded) != {"nftables"}:
            return False
        entries = decoded["nftables"]
        if type(entries) is not list or len(entries) != 7:
            return False
        if set(entries[0]) != {"metainfo"}:
            return False
        meta = entries[0]["metainfo"]
        if (type(meta) is not dict
                or set(meta) != {"version", "release_name", "json_schema_version"}
                or type(meta["version"]) is not str
                or type(meta["release_name"]) is not str
                or type(meta["json_schema_version"]) is not int
                or meta["json_schema_version"] != 1):
            return False
        for entry in entries[1:]:
            if type(entry) is not dict or len(entry) != 1:
                return False
            kind = next(iter(entry))
            if kind not in ("table", "chain", "rule") or type(entry[kind]) is not dict:
                return False
            handle = entry[kind].pop("handle", None)
            if type(handle) is not int or handle <= 0:
                return False
        # Compare canonical JSON too: Python equality conflates bool and int.
        return json.dumps(entries[1:], sort_keys=True) == json.dumps(
            _expected(uid), sort_keys=True)
    except (ValueError, TypeError, KeyError, RecursionError, Refusal):
        return False


def check_kernel(uid):
    code, raw = _run(["/usr/bin/nft", "-j", "-n", "list", "table", "inet", TABLE])
    if code != 0 or not table_matches(raw, uid):
        raise Refusal("kernel guard does not match the required account policy")


def apply(uid):
    if os.geteuid() != 0:
        raise Refusal("administrator service is required")
    code, raw = _run(["/usr/bin/nft", "-j", "-n", "list", "table", "inet", TABLE])
    if code == 0:
        if not table_matches(raw, uid):
            raise Refusal("existing guard differs; administrator review required")
    else:
        # Exclusive creation is one nft transaction. Never flush or replace
        # an existing table, including when its inspection failed.
        code, _ = _run(["/usr/bin/nft", "-f", "-"], rules(uid))
        if code != 0:
            raise Refusal("exclusive kernel guard creation failed")
    check_kernel(uid)


def _manager_matches(raw):
    expected = {
        "LoadState": "loaded", "ActiveState": "active", "SubState": "exited",
        "Result": "success", "ExecMainStatus": "0", "DropInPaths": "",
        "FragmentPath": UNIT, "NeedDaemonReload": "no", "UnitFileState": "enabled",
    }
    try:
        lines = raw.decode("utf-8", "strict").splitlines()
        if len(lines) != len(expected):
            return False
        pairs = [line.split("=", 1) for line in lines]
        return _unique(pairs) == expected
    except (ValueError, Refusal):
        return False


def gate():
    uid = owner_uid(_root_file(CONFIG, 11))
    if uid != os.getuid() or os.getuid() != os.geteuid():
        raise Refusal("guard is configured for a different Linux account")
    installed = _root_file(HELPER, 32768)
    with open(__file__, "rb") as source:
        current = source.read(32769)
    if installed != current or len(current) > 32768:
        raise Refusal("administrator guard helper does not match this release")
    if _root_file(UNIT, 4096) != ROOT_UNIT.encode("ascii"):
        raise Refusal("administrator guard unit does not match this release")
    properties = ("LoadState,ActiveState,SubState,Result,ExecMainStatus,"
                  "DropInPaths,FragmentPath,NeedDaemonReload,UnitFileState")
    code, raw = _run(["/usr/bin/systemctl", "--system", "--no-pager", "show",
                      SERVICE, "--property=" + properties])
    if code != 0 or not _manager_matches(raw):
        raise Refusal("administrator guard service is not active and enabled")
    code, _ = _run(["/usr/bin/sudo", "-n", "--", "/usr/bin/python3", "-I", "-S",
                   "-B", HELPER, "check-kernel"])
    if code != 0:
        raise Refusal("fresh administrator kernel check failed or is not authorized")


def main(argv):
    try:
        if argv == ["gate"]:
            gate()
        elif argv == ["sudoers"]:
            sys.stdout.write(sudoers_rule(os.getuid()).decode("ascii"))
        elif argv in (["apply"], ["check-kernel"]):
            if os.geteuid() != 0:
                raise Refusal("administrator service is required")
            uid = owner_uid(_root_file(CONFIG, 11))
            if argv == ["apply"]:
                apply(uid)
            else:
                if _root_file(SUDOERS, 512) != sudoers_rule(uid):
                    raise Refusal("read-only checker delegation differs from this release")
                check_kernel(uid)
        else:
            raise Refusal("expected gate, sudoers, apply, or check-kernel")
    except (Refusal, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print("SIA Ollama guard refused: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
