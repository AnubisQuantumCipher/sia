"""Sealed transport for SIA's compiled raw-vector adapter.

Transport observations bind bytes and process results. The caller must still
admit the adapter protocol, build provenance, model generation, private index
identity, and complete ranked rows before making a benchmark comparison.
"""

import contextlib
import copy
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass

import sialib
import siaqueue

# JACKAL status=exact parsed=2^29 exact=536870912; exact rational arithmetic
# outside the Lean certificate chain, not formal-bounded or code correctness.
MAX_EXECUTABLE_BYTES = 536_870_912
MAX_REQUEST_BYTES = sialib.MAX_SOURCE_TAIL_BYTES
MAX_RESPONSE_BYTES = sialib.MAX_STATE_JSON_BYTES
_SEALS = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW
          | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
_DIGEST = re.compile(r"[0-9a-f]{64}")
_ENVIRONMENT = {
    "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
    "TZ": "UTC", "GBRAIN_SKIP_STARTUP_HOOKS": "1",
}


class VectorRefusal(RuntimeError):
    """The vector run did not admit its requested observation."""


def _canonical_bytes(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise VectorRefusal("vector JSON is not canonicalizable") from exc


def _write_all(descriptor, payload):
    pending = memoryview(payload)
    while pending:
        written = os.write(descriptor, pending)
        if written <= 0:
            raise VectorRefusal("vector snapshot write was incomplete")
        pending = pending[written:]


def _seal(descriptor):
    os.lseek(descriptor, 0, os.SEEK_SET)
    fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, _SEALS)
    if fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) & _SEALS != _SEALS:
        raise VectorRefusal("vector snapshot sealing failed")


@dataclass(frozen=True)
class SealedGeneration:
    fd: int
    sha256: str
    size: int
    source: dict

    def assert_current(self):
        if not sialib._chain_generation_matches(self.source):
            raise VectorRefusal("vector source generation changed")
        if fcntl.fcntl(self.fd, fcntl.F_GET_SEALS) & _SEALS != _SEALS:
            raise VectorRefusal("vector snapshot seals changed")


@contextlib.contextmanager
def sealed_file(path, expected_sha256, *, max_bytes, executable=False):
    """Stream a pinned source generation into an immutable memfd."""
    if not isinstance(path, str) or not os.path.isabs(path) \
            or not isinstance(expected_sha256, str) \
            or _DIGEST.fullmatch(expected_sha256) is None \
            or type(max_bytes) is not int \
            or not 0 < max_bytes <= MAX_EXECUTABLE_BYTES \
            or type(executable) is not bool:
        raise VectorRefusal("vector source admission request is invalid")
    original = reader = sealed = None
    try:
        original, generation = sialib._open_chain_generation(
            path, "vector source")
        source = {"fd": original, "generation": generation,
                  "path": path, "label": "vector source", "directory": False}
        info = os.fstat(original)
        if info.st_uid != os.geteuid() or info.st_nlink != 1 \
                or info.st_mode & 0o022 or info.st_size > max_bytes \
                or executable and not info.st_mode & 0o111:
            raise VectorRefusal("vector source is not a bounded owned file")
        reader = os.open(sialib._chain_descriptor_path(original),
                         os.O_RDONLY | os.O_CLOEXEC)
        if executable and os.pread(reader, 4, 0) != b"\x7fELF":
            raise VectorRefusal("vector runner must be a compiled ELF executable")
        sealed = os.memfd_create("sia-vector-source",
                                 os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        digest = hashlib.sha256()
        size = 0
        while True:
            block = os.read(reader, min(sialib.MAX_CONFIG_BYTES,
                                       max_bytes + 1 - size))
            if not block:
                break
            size += len(block)
            if size > max_bytes:
                raise VectorRefusal("vector source exceeds its byte ceiling")
            digest.update(block)
            _write_all(sealed, block)
        if size != info.st_size or digest.hexdigest() != expected_sha256:
            raise VectorRefusal("vector source digest or size mismatch")
        os.fchmod(sealed, 0o500 if executable else 0o400)
        _seal(sealed)
        result = SealedGeneration(sealed, digest.hexdigest(), size, source)
        result.assert_current()
        yield result
        result.assert_current()
    except VectorRefusal:
        raise
    except (OSError, ValueError) as exc:
        raise VectorRefusal("vector source could not be admitted") from exc
    finally:
        for descriptor in (sealed, reader, original):
            if descriptor is not None:
                os.close(descriptor)


@contextlib.contextmanager
def _sealed_request(payload):
    if len(payload) > MAX_REQUEST_BYTES:
        raise VectorRefusal("vector request exceeds its byte ceiling")
    descriptor = os.memfd_create("sia-vector-request",
                                os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        _write_all(descriptor, payload)
        os.fchmod(descriptor, 0o400)
        _seal(descriptor)
        yield descriptor
    finally:
        os.close(descriptor)


def _directory_identity(info):
    # PGlite owns mutable lock/WAL files in this PRIVATE copy. Logical data
    # identity is independently measured by the adapter before and after use.
    return info.st_dev, info.st_ino, info.st_uid, info.st_mode


@contextlib.contextmanager
def private_index_snapshot(archive_path, expected_sha256, *, scratch_parent):
    """Restore one physical index generation from byte-pinned sealed tar bytes.

    The source is an explicitly prepared, stopped PRIVATE index archive, never
    a resident database directory. Every query gets a new writable copy; all
    physical index files (including approximate-search topology) are bound by
    the archive digest. Logical/catalog pre/post checks remain the adapter's
    responsibility. The manifest describes this copy, not database validity.
    """
    with sealed_file(archive_path, expected_sha256,
                     max_bytes=MAX_EXECUTABLE_BYTES) as archive:
        try:
            with tempfile.TemporaryDirectory(
                    prefix="sia-vector-index-", dir=scratch_parent) as parent:
                # PGlite's filesystem bridge requires an ordinary final path
                # component, not the procfs descriptor symlink as its root.
                directory = os.path.join(parent, "index")
                os.mkdir(directory, 0o700)
                manifest = []
                seen = set()
                file_bytes = 0
                with os.fdopen(os.dup(archive.fd), "rb") as stream, \
                        tarfile.open(fileobj=stream, mode="r|") as tar:
                    for member in tar:
                        name = member.name
                        parts = name.split("/")
                        if not name or name.startswith("/") \
                                or any(part in ("", ".", "..") for part in parts) \
                                or "\x00" in name or name in seen \
                                or len(name.encode("utf-8")) > sialib.MAX_CONFIG_BYTES:
                            raise VectorRefusal("vector archive has an unsafe member path")
                        seen.add(name)
                        if len(seen) > 100_000:
                            raise VectorRefusal("vector archive exceeds its member ceiling")
                        target = os.path.join(directory, *parts)
                        if member.isdir():
                            os.makedirs(target, mode=0o700, exist_ok=True)
                            manifest.append({"path": name, "type": "directory"})
                        elif member.isfile() and not member.sparse:
                            if type(member.size) is not int or member.size < 0:
                                raise VectorRefusal("vector archive has an invalid file size")
                            file_bytes += member.size
                            if file_bytes > MAX_EXECUTABLE_BYTES:
                                raise VectorRefusal("vector archive exceeds its byte ceiling")
                            os.makedirs(os.path.dirname(target), mode=0o700,
                                        exist_ok=True)
                            source = tar.extractfile(member)
                            if source is None:
                                raise VectorRefusal("vector archive member is unreadable")
                            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT
                                                 | os.O_EXCL | os.O_NOFOLLOW
                                                 | os.O_CLOEXEC, 0o600)
                            digest = hashlib.sha256()
                            copied = 0
                            with source, os.fdopen(descriptor, "wb") as output:
                                while block := source.read(sialib.MAX_CONFIG_BYTES):
                                    copied += len(block)
                                    if copied > member.size:
                                        raise VectorRefusal("vector archive member exceeds declared size")
                                    output.write(block)
                                    digest.update(block)
                            if copied != member.size:
                                raise VectorRefusal("vector archive member is incomplete")
                            manifest.append({"path": name, "type": "file",
                                             "bytes": copied,
                                             "sha256": digest.hexdigest()})
                        else:
                            raise VectorRefusal("vector archive contains an unsupported member")
                if not manifest:
                    raise VectorRefusal("vector archive has no index files")
                archive.assert_current()
                yield {"directory": directory, "descriptor_parent": parent,
                       "archive_sha256": archive.sha256,
                       "manifest": manifest,
                       "manifest_sha256": hashlib.sha256(
                           _canonical_bytes(manifest)).hexdigest()}
                archive.assert_current()
        except VectorRefusal:
            raise
        except (OSError, ValueError, UnicodeError, tarfile.TarError) as exc:
            raise VectorRefusal("vector private index snapshot refused") from exc


def invoke_adapter(executable, expected_sha256, request, snapshot_directory,
                   *, timeout, scratch_parent=None):
    """Execute sealed code/request bytes against an explicit private index.

    This is a transport primitive. Returned payload is strict JSON but is not
    yet an admitted ranking. No query fallback or benchmark publication occurs
    here. Originals stay in the parent for post-execution generation checks.
    """
    if not isinstance(request, dict) \
            or not isinstance(request.get("snapshot"), dict):
        raise VectorRefusal("vector request must name its snapshot role")
    if len(_canonical_bytes(request)) > MAX_REQUEST_BYTES:
        raise VectorRefusal("vector request exceeds its byte ceiling")
    if not isinstance(snapshot_directory, str) \
            or not os.path.isabs(snapshot_directory):
        raise VectorRefusal("vector snapshot requires an absolute private path")
    forbidden = os.path.join(sialib.SHARE, ".gbrain")
    normalized = os.path.abspath(snapshot_directory)
    if normalized == forbidden or normalized.startswith(forbidden + os.sep):
        raise VectorRefusal("resident index cannot be used as a private snapshot")
    database_fd = index_fd = None
    try:
        database_fd = sialib._open_source_nofollow(
            normalized, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY)
        initial = os.fstat(database_fd)
        if not stat.S_ISDIR(initial.st_mode) \
                or initial.st_uid != os.geteuid() or initial.st_mode & 0o077:
            raise VectorRefusal("vector snapshot must be an owned private directory")
        index_fd = os.open("index", os.O_RDONLY | os.O_CLOEXEC
                           | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=database_fd)
        index_initial = os.fstat(index_fd)
        if index_initial.st_uid != os.geteuid() or index_initial.st_mode & 0o077:
            raise VectorRefusal("vector fixed index child must be an owned private directory")
        with sealed_file(executable, expected_sha256,
                         max_bytes=MAX_EXECUTABLE_BYTES, executable=True) as code:
            bound_request = copy.deepcopy(request)
            bound_request["snapshot"]["fd"] = database_fd
            request_bytes = _canonical_bytes(bound_request)
            with _sealed_request(request_bytes) as request_fd, \
                    tempfile.TemporaryDirectory(
                        prefix="sia-vector-launch-", dir=scratch_parent) as launch:
                temporary = os.path.join(launch, "tmp")
                os.mkdir(temporary, 0o700)
                environment = {**_ENVIRONMENT, "HOME": launch,
                               "TMPDIR": temporary, "GBRAIN_HOME": launch}
                environment_contract = {
                    **_ENVIRONMENT, "HOME": "private-launch",
                    "TMPDIR": "private-launch/tmp", "GBRAIN_HOME": "private-launch",
                }
                launch_contract = {
                    "schema": "sia-vector-launch-v1",
                    "executable_sha256": code.sha256,
                    "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
                    "argv": ["sealed-executable", "--request-fd", "sealed-request"],
                    "cwd": "private-launch", "environment": environment_contract,
                    "descriptor_roles": ["executable", "request", "private-index-parent"],
                    "index_leaf": "index",
                    "timeout": timeout, "output_limit": MAX_RESPONSE_BYTES,
                    "process_containment": "user-pid-namespace-private-proc",
                }
                command = [sialib._chain_descriptor_path(code.fd),
                           "--request-fd", str(request_fd)]
                started_ns = time.monotonic_ns()
                process = sialib._run_bounded_text_process(
                    command, env=environment, timeout=timeout, cwd=launch,
                    pass_fds=(code.fd, request_fd, database_fd),
                    label="raw-vector adapter", output_limit=MAX_RESPONSE_BYTES,
                    isolate_process_tree=True)
                wall_elapsed_ns = time.monotonic_ns() - started_ns
                code.assert_current()
                if process.returncode not in (0, 2) or process.stderr:
                    raise VectorRefusal("vector adapter process refused")
                if not isinstance(process.stdout, str) \
                        or not process.stdout.endswith("\n"):
                    raise VectorRefusal("vector adapter output is incomplete")
                stdout = process.stdout.encode("utf-8", errors="strict")
                if len(stdout) > MAX_RESPONSE_BYTES:
                    raise VectorRefusal("vector adapter output exceeds its byte ceiling")
                try:
                    payload = siaqueue.strict_json_loads(process.stdout)
                except (TypeError, ValueError, RecursionError) as exc:
                    raise VectorRefusal("vector adapter output is invalid JSON") from exc
                if not isinstance(payload, dict):
                    raise VectorRefusal("vector adapter output must be an object")
                if (process.returncode == 2) != (payload.get("status") == "refused"):
                    raise VectorRefusal("vector adapter exit verdict disagrees with output")
                rebound = sialib._open_source_nofollow(
                    normalized, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY)
                try:
                    if _directory_identity(os.fstat(database_fd)) \
                            != _directory_identity(initial) \
                            or _directory_identity(os.fstat(rebound)) \
                            != _directory_identity(initial):
                        raise VectorRefusal("vector snapshot directory changed")
                finally:
                    os.close(rebound)
                index_rebound = os.open("index", os.O_RDONLY | os.O_CLOEXEC
                                        | os.O_DIRECTORY | os.O_NOFOLLOW,
                                        dir_fd=database_fd)
                try:
                    if _directory_identity(os.fstat(index_fd)) \
                            != _directory_identity(index_initial) \
                            or _directory_identity(os.fstat(index_rebound)) \
                            != _directory_identity(index_initial):
                        raise VectorRefusal("vector fixed index child changed")
                finally:
                    os.close(index_rebound)
                return {
                    "payload": payload,
                    "returncode": process.returncode,
                    "wall_elapsed_ns": wall_elapsed_ns,
                    "executable_sha256": code.sha256,
                    "request_sha256": launch_contract["request_sha256"],
                    "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                    "launch_sha256": hashlib.sha256(
                        _canonical_bytes(launch_contract)).hexdigest(),
                    "launch_contract": launch_contract,
                }
    except VectorRefusal:
        raise
    except subprocess.TimeoutExpired as exc:
        raise VectorRefusal("vector adapter timeout") from exc
    except (OSError, ValueError, OverflowError) as exc:
        raise VectorRefusal("vector adapter transport refused") from exc
    finally:
        if index_fd is not None:
            os.close(index_fd)
        if database_fd is not None:
            os.close(database_fd)
