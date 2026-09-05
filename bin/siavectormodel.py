"""Descriptor-bound, deliberately CPU-only private Ollama serving.

Host entrypoints admit explicit expectations before construction. The inner
supervisor is this same sealed source, launched with an explicitly enumerated
Python/system runtime; it never imports SIA or consults a resident model service.
No namespace or dependency failure has a host-server/library fallback.
"""

import contextlib
import dataclasses
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time


MAX_SEALED_BYTES = 536_870_912
MAX_PACKAGE_BYTES = 3_000_000_000  # Streaming provenance ceiling, not RAM allocation.
MAX_PLAN_BYTES = 1_000_000_000
MAX_ENTRIES = 10_000
MAX_JSON_BYTES = 1_048_576
MAX_OUTPUT_BYTES = 16_777_216
_DIGEST = re.compile(r"[0-9a-f]{64}")
_MODEL = re.compile(r"([a-z0-9][a-z0-9._-]*):([a-zA-Z0-9][a-zA-Z0-9._-]*)")
_SEALS = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW
          | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
_ENV = {
    "PATH": "/runtime/ollama/bin:/usr/bin", "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8", "TZ": "UTC", "HOME": "/work/home",
    "TMPDIR": "/work/tmp", "GBRAIN_HOME": "/work/gbrain",
    "GBRAIN_SKIP_STARTUP_HOOKS": "1", "PYTHONDONTWRITEBYTECODE": "1",
    "OLLAMA_HOST": "127.0.0.1:11434", "OLLAMA_MODELS": "/models",
    "OLLAMA_LLM_LIBRARY": "cpu", "OLLAMA_NO_CLOUD": "1",
    "OLLAMA_NOPRUNE": "1", "OLLAMA_NUM_PARALLEL": "1",
    "OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_MAX_QUEUE": "1",
    "OLLAMA_KEEP_ALIVE": "30m", "OLLAMA_CONTEXT_LENGTH": "8192",
    "CUDA_VISIBLE_DEVICES": "-1", "HIP_VISIBLE_DEVICES": "-1",
    "ROCR_VISIBLE_DEVICES": "-1", "GGML_VK_VISIBLE_DEVICES": "-1",
}
NON_CLAIMS = [
    "CPU-only execution excludes GPU package backends; full package hashes are provenance, not full-feature execution.",
    "Selected shared system runtime source files are identity-pinned and sealed; the complete host, kernel, hardware and all possible dependencies are not attested.",
    "Release and model expectations come from the caller; local receipts are not independent supply-chain authentication.",
    "Input and process binding does not prove model computation, vector semantics, ranking relevance or a cognitive claim.",
    "Adapter non_claims remain controlling and must be retained by the observation controller.",
    "Bubblewrap namespace construction and the host launch-time loader are trusted system mechanisms, not independently proved.",
]


class ModelRefusal(RuntimeError):
    """A private serving observation could not be admitted."""


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ModelRefusal("model JSON is not canonicalizable") from exc


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    try:
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError("JSON ceiling")
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ModelRefusal("model metadata is not bounded strict JSON") from exc


def _path(path):
    if type(path) is not str or not os.path.isabs(path) \
            or os.path.normpath(path) != path or "\x00" in path \
            or ".gbrain" in path.split("/"):
        raise ModelRefusal("model input requires an explicit nonresident absolute path")
    return path


def _open(path, flags):
    _path(path)
    parts = path.split("/")[1:]
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                              | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return os.open(parts[-1], flags | os.O_NOFOLLOW | os.O_CLOEXEC
                       | os.O_NONBLOCK, dir_fd=fd)
    finally:
        os.close(fd)


def _generation(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _valid_file(info, ceiling, *, system=False):
    return (stat.S_ISREG(info.st_mode) and info.st_uid in (
        (0, os.geteuid()) if system else (os.geteuid(),))
        and info.st_nlink == 1 and not info.st_mode & 0o022
        and 0 <= info.st_size <= ceiling)


def _hash_fd(fd, ceiling):
    digest = hashlib.sha256()
    size = 0
    os.lseek(fd, 0, os.SEEK_SET)
    while block := os.read(fd, 262_144):
        size += len(block)
        if size > ceiling:
            raise ModelRefusal("model input exceeds byte ceiling")
        digest.update(block)
    return digest.hexdigest(), size


def _cpu_path(name):
    if name == "bin/ollama":
        return True
    parts = name.split("/")
    if len(parts) != 3 or parts[:2] != ["lib", "ollama"]:
        return False
    leaf = parts[-1]
    return leaf in ("llama-server", "llama-quantize") or bool(re.fullmatch(
        r"(?:libllama(?:-server-impl|-quantize-impl|-common)?|libmtmd|"
        r"libggml(?:-base|-cpu-armv[0-9._]+)?|libgomp|libomp)\.so(?:\.[0-9.]+)?", leaf))


def _package_scan(root):
    """Hash every package leaf, retaining metadata separately from provenance."""
    root = _path(root)
    entries, generations = [], {}
    total = 0
    root_fd = _open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        def visit(fd, prefix):
            nonlocal total
            info = os.fstat(fd)
            if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise ModelRefusal("package directory is not owned and nonwritable by others")
            generations[prefix] = _generation(info)
            for leaf in sorted(os.listdir(fd)):
                name = prefix + "/" + leaf if prefix else leaf
                if len(entries) >= MAX_ENTRIES or "\x00" in name:
                    raise ModelRefusal("package entry ceiling or name refused")
                info = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
                generations[name] = _generation(info)
                mode = stat.S_IMODE(info.st_mode)
                if stat.S_ISDIR(info.st_mode):
                    entries.append({"path": name, "type": "directory", "mode": mode})
                    child = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                                    | os.O_CLOEXEC, dir_fd=fd)
                    try:
                        visit(child, name)
                    finally:
                        os.close(child)
                elif stat.S_ISLNK(info.st_mode):
                    target = os.readlink(leaf, dir_fd=fd)
                    resolved = os.path.normpath(os.path.join(os.path.dirname(name), target))
                    if os.path.isabs(target) or resolved.startswith("../") \
                            or resolved == ".." or info.st_uid != os.geteuid() \
                            or _cpu_path(name) and not _cpu_path(resolved):
                        raise ModelRefusal("package link escapes admitted CPU closure")
                    entries.append({"path": name, "type": "symlink", "target": target})
                elif _valid_file(info, MAX_PACKAGE_BYTES):
                    total += info.st_size
                    if total > MAX_PACKAGE_BYTES:
                        raise ModelRefusal("package inventory byte ceiling exceeded")
                    source = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                     dir_fd=fd)
                    try:
                        sha, size = _hash_fd(source, MAX_PACKAGE_BYTES)
                        if _generation(os.fstat(source)) != _generation(info):
                            raise ModelRefusal("package file generation changed")
                    finally:
                        os.close(source)
                    entries.append({"path": name, "type": "file", "mode": mode,
                                    "bytes": size, "sha256": sha})
                else:
                    raise ModelRefusal("package contains an unsafe file or alias")
        visit(root_fd, "")
        by_path = {entry["path"]: entry for entry in entries}
        for entry in entries:
            if entry["type"] == "symlink":
                seen, current = set(), entry["path"]
                while by_path.get(current, {}).get("type") == "symlink":
                    if current in seen:
                        raise ModelRefusal("package symlink cycle")
                    seen.add(current)
                    current = os.path.normpath(os.path.join(os.path.dirname(current),
                                                           by_path[current]["target"]))
                if by_path.get(current, {}).get("type") != "file":
                    raise ModelRefusal("package symlink does not resolve to a regular leaf")
        return entries, generations
    except (OSError, ValueError) as exc:
        raise ModelRefusal("package inventory refused") from exc
    finally:
        os.close(root_fd)


def inventory_package(root):
    return _package_scan(root)[0]


@dataclasses.dataclass
class _Sealed:
    fd: int
    sha256: str
    size: int
    path: str
    source_fd: int
    generation: tuple

    def assert_current(self):
        rebound = None
        try:
            rebound = _open(self.path, os.O_RDONLY)
            if _generation(os.fstat(self.source_fd)) != self.generation \
                    or _generation(os.fstat(rebound)) != self.generation \
                    or fcntl.fcntl(self.fd, fcntl.F_GET_SEALS) & _SEALS != _SEALS:
                raise ModelRefusal("model source generation changed")
        except OSError as exc:
            raise ModelRefusal("model source generation changed") from exc
        finally:
            if rebound is not None:
                os.close(rebound)


def _write(fd, data):
    pending = memoryview(data)
    while pending:
        count = os.write(fd, pending)
        if count <= 0:
            raise ModelRefusal("sealed model write incomplete")
        pending = pending[count:]


def _seal(fd, executable=False):
    os.fchmod(fd, 0o500 if executable else 0o400)
    os.lseek(fd, 0, os.SEEK_SET)
    fcntl.fcntl(fd, fcntl.F_ADD_SEALS, _SEALS)
    if fcntl.fcntl(fd, fcntl.F_GET_SEALS) & _SEALS != _SEALS:
        raise ModelRefusal("model input sealing failed")


@contextlib.contextmanager
def _sealed_file(path, expected, *, system=False, executable=False):
    if type(expected) is not str or not _DIGEST.fullmatch(expected):
        raise ModelRefusal("model expectation digest is invalid")
    source = sealed = None
    try:
        source = _open(path, os.O_RDONLY)
        info = os.fstat(source)
        if not _valid_file(info, MAX_SEALED_BYTES, system=system) \
                or executable and (not info.st_mode & 0o111
                                    or os.pread(source, 4, 0) != b"\x7fELF"):
            raise ModelRefusal("model source is not an admitted bounded regular file")
        sealed = os.memfd_create("sia-model-input", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        digest, size = hashlib.sha256(), 0
        while block := os.read(source, 262_144):
            size += len(block)
            if size > MAX_SEALED_BYTES:
                raise ModelRefusal("model sealed input byte ceiling exceeded")
            digest.update(block)
            _write(sealed, block)
        if size != info.st_size or digest.hexdigest() != expected:
            raise ModelRefusal("model source digest or size mismatch")
        _seal(sealed, executable)
        result = _Sealed(sealed, expected, size, path, source, _generation(info))
        result.assert_current()
        yield result
        result.assert_current()
    except (OSError, ValueError) as exc:
        raise ModelRefusal("model sealed input admission failed") from exc
    finally:
        for fd in (sealed, source):
            if fd is not None:
                os.close(fd)


@contextlib.contextmanager
def _sealed_bytes(payload):
    if len(payload) > MAX_JSON_BYTES:
        raise ModelRefusal("model configuration byte ceiling exceeded")
    fd = os.memfd_create("sia-model-config", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        _write(fd, payload)
        _seal(fd)
        yield fd
    finally:
        os.close(fd)


@dataclasses.dataclass
class AdmittedModel:
    identity: dict
    mounts: list
    _sealed: list
    _root: str
    _generations: dict

    def assert_current(self):
        for item in self._sealed:
            item.assert_current()
        # Includes excluded GPU provenance, not merely the selected CPU bytes.
        entries, generations = _package_scan(self._root)
        if generations != self._generations \
                or _sha(_canonical(entries)) != self.identity["package_sha256"]:
            raise ModelRefusal("model package generation changed")


def _mount(sealed, destination, executable=False):
    return {"kind": "file", "fd": sealed.fd, "destination": destination,
            "sha256": sealed.sha256, "bytes": sealed.size,
            "executable": executable}


@contextlib.contextmanager
def admit_model(*, package_root, package_sha256, model_root, model_name,
                manifest_sha256, release_version, release_archive_sha256):
    """Pin all package provenance, then seal only CPU execution and model bytes."""
    match = _MODEL.fullmatch(model_name) if type(model_name) is str else None
    if not match or match.group(2).lower() == "latest" or release_version != "0.33.2" \
            or not all(type(value) is str and _DIGEST.fullmatch(value)
                       for value in (package_sha256, manifest_sha256, release_archive_sha256)):
        raise ModelRefusal("model/release expectations are not explicitly pinned")
    _path(model_root)
    entries, generations = _package_scan(package_root)
    if _sha(_canonical(entries)) != package_sha256:
        raise ModelRefusal("model package inventory digest mismatch")
    files = {entry["path"]: entry for entry in entries}
    for required in ("bin/ollama", "lib/ollama/llama-server", ".sia-release"):
        if files.get(required, {}).get("type") != "file":
            raise ModelRefusal("model package required executable or receipt missing")
    with contextlib.ExitStack() as stack:
        sealed_inputs, mounts, total = [], [], 0

        def add(path, sha, destination, executable=False):
            nonlocal total
            item = stack.enter_context(_sealed_file(path, sha, executable=executable))
            total += item.size
            if total > MAX_SEALED_BYTES:
                raise ModelRefusal("model CPU plus model sealed byte ceiling exceeded")
            sealed_inputs.append(item)
            mounts.append(_mount(item, destination, executable))
            return item

        receipt = add(os.path.join(package_root, ".sia-release"), files[".sia-release"]["sha256"],
                      "/runtime/ollama/.sia-release")
        if receipt.size > MAX_JSON_BYTES:
            raise ModelRefusal("model package release receipt metadata ceiling exceeded")
        try:
            values = {}
            for line in os.pread(receipt.fd, receipt.size, 0).decode("utf-8").splitlines():
                key, value = line.split("=", 1)
                if key in values:
                    raise ValueError("duplicate release key")
                values[key] = value
            if values.get("managed-by") != "khephri.sia" \
                    or values.get("version") != release_version \
                    or values.get("asset") != "ollama-linux-arm64.tar.zst" \
                    or values.get("sha256") != release_archive_sha256 \
                    or values.get("binary_sha256") != files["bin/ollama"]["sha256"]:
                raise ValueError("release expectation mismatch")
        except (ValueError, UnicodeError) as exc:
            raise ModelRefusal("model package release receipt mismatch") from exc
        selected = []
        for entry in entries:
            name = entry["path"]
            if _cpu_path(name):
                selected.append(name)
                destination = "/runtime/ollama/" + name
                if entry["type"] == "file":
                    add(os.path.join(package_root, name), entry["sha256"], destination,
                        name in ("bin/ollama", "lib/ollama/llama-server", "lib/ollama/llama-quantize"))
                elif entry["type"] == "symlink":
                    mounts.append({"kind": "symlink", "destination": destination,
                                   "target": entry["target"]})
                else:
                    raise ModelRefusal("CPU execution entry has unsupported type")
            elif name.startswith("lib/ollama/") and len(name.split("/")) == 3 \
                    and entry["type"] != "directory":
                raise ModelRefusal("unknown direct CPU runtime leaf")
        manifest_relative = "manifests/registry.ollama.ai/library/" + match.group(1) + "/" + match.group(2)
        manifest_file = add(os.path.join(model_root, manifest_relative), manifest_sha256,
                            "/models/" + manifest_relative)
        if manifest_file.size > MAX_JSON_BYTES:
            raise ModelRefusal("model manifest byte ceiling exceeded")
        manifest = _json(os.pread(manifest_file.fd, manifest_file.size, 0))
        if type(manifest) is not dict or set(manifest) != {"schemaVersion", "mediaType", "config", "layers"} \
                or type(manifest["schemaVersion"]) is not int or manifest["schemaVersion"] != 2 \
                or manifest["mediaType"] != "application/vnd.docker.distribution.manifest.v2+json" \
                or type(manifest["layers"]) is not list or not manifest["layers"]:
            raise ModelRefusal("model manifest schema refused")
        references = [manifest["config"], *manifest["layers"]]
        model_paths, seen, blob_identity = [], set(), []
        for index, reference in enumerate(references):
            if type(reference) is not dict or set(reference) != {"mediaType", "digest", "size"} \
                    or type(reference["digest"]) is not str \
                    or not re.fullmatch(r"sha256:[0-9a-f]{64}", reference["digest"]) \
                    or type(reference["size"]) is not int \
                    or not 0 < reference["size"] <= MAX_SEALED_BYTES \
                    or reference["digest"] in seen:
                raise ModelRefusal("model blob reference refused")
            seen.add(reference["digest"])
            kind = reference["mediaType"]
            if index == 0 and kind != "application/vnd.docker.container.image.v1+json" \
                    or index != 0 and kind not in {
                        "application/vnd.ollama.image.model", "application/vnd.ollama.image.params",
                        "application/vnd.ollama.image.license"}:
                raise ModelRefusal("model reference media type refused")
            relative = "blobs/" + reference["digest"].replace(":", "-")
            blob = add(os.path.join(model_root, relative), reference["digest"].split(":")[1],
                       "/models/" + relative)
            if blob.size != reference["size"]:
                raise ModelRefusal("model blob declared size mismatch")
            blob_identity.append(dict(reference))
            if kind == "application/vnd.ollama.image.model":
                if os.pread(blob.fd, 4, 0) != b"GGUF":
                    raise ModelRefusal("model weights are not a GGUF input")
                model_paths.append("/models/" + relative)
        if len(model_paths) != 1:
            raise ModelRefusal("model execution requires exactly one GGUF model layer")
        identity = {"schema": "sia-raw-vector-model-input-v1", "model_name": model_name,
                    "package_sha256": package_sha256, "manifest_sha256": manifest_sha256,
                    "release_version": release_version, "release_archive_sha256": release_archive_sha256,
                    "ollama_sha256": files["bin/ollama"]["sha256"],
                    "runner_sha256": files["lib/ollama/llama-server"]["sha256"],
                    "execution_policy": "ollama-cpu-only-v1", "selected_execution_paths": selected,
                    "excluded_execution_paths": [e["path"] for e in entries
                        if e["type"] != "directory" and e["path"] not in selected and e["path"] != ".sia-release"],
                    "model_path": model_paths[0], "blobs": blob_identity, "sealed_bytes": total,
                    "non_claims": list(NON_CLAIMS)}
        admitted = AdmittedModel(identity, mounts, sealed_inputs, package_root, generations)
        admitted.assert_current()
        yield admitted
        admitted.assert_current()


@dataclasses.dataclass
class LaunchPlan:
    argv: list
    pass_fds: tuple
    input_fds: tuple
    environment: dict
    config: dict
    config_sha256: str
    non_claims: list


@contextlib.contextmanager
def launch_plan(*, admitted, executable, executable_sha256, request,
                snapshot_directory, shared_runtime, timeout):
    """Construct descriptor-backed mounts, not an ambient installed-runtime launch.

Despite the historical argument name, shared_runtime leaves are copied into
sealed descriptors too. There are no shared host directory mounts.
"""
    if not isinstance(admitted, AdmittedModel) or type(timeout) not in (int, float) \
            or not 0 < timeout <= 1800 or not isinstance(request, dict) \
            or not isinstance(request.get("snapshot"), dict) \
            or not isinstance(request.get("embedding"), dict):
        raise ModelRefusal("model launch request is invalid")
    embedding = request["embedding"]
    if embedding.get("model") != "ollama:" + admitted.identity["model_name"] \
            or embedding.get("endpoint") != "http://127.0.0.1:11434/v1":
        raise ModelRefusal("model launch requires its exact model and private endpoint")
    if type(shared_runtime) is not list or not shared_runtime or len(shared_runtime) > MAX_ENTRIES:
        raise ModelRefusal("model launch needs an explicit bounded system runtime profile")
    with contextlib.ExitStack() as stack:
        files = list(admitted.mounts)
        sealed_inputs, runtime_identity, destinations = [], [], set()
        total = admitted.identity["sealed_bytes"]
        for item in shared_runtime:
            if type(item) is not dict or set(item) != {"source", "destination", "sha256"}:
                raise ModelRefusal("system runtime leaf declaration invalid")
            destination = _path(item["destination"])
            if destination in destinations or not (
                    destination.startswith("/usr/lib/") or destination == "/usr/bin/python3") \
                    or any(part in ("site-packages", "dri", "cuda", "vulkan")
                           for part in destination.split("/")):
                raise ModelRefusal("system runtime destination is not an allowed individual leaf")
            destinations.add(destination)
            runtime_executable = destination in (
                "/usr/bin/python3", "/usr/lib/ld-linux-aarch64.so.1")
            sealed = stack.enter_context(_sealed_file(item["source"], item["sha256"],
                system=True, executable=runtime_executable))
            sealed_inputs.append(sealed)
            files.append(_mount(sealed, destination, runtime_executable))
            runtime_identity.append({"destination": destination, "sha256": sealed.sha256,
                                     "bytes": sealed.size})
            total += sealed.size
        if "/usr/bin/python3" not in destinations:
            raise ModelRefusal("system runtime has no explicitly pinned Python executable")
        adapter = stack.enter_context(_sealed_file(executable, executable_sha256, executable=True))
        sealed_inputs.append(adapter)
        files.append(_mount(adapter, "/runtime/adapter", True))
        source = os.path.realpath(__file__)
        fd = _open(source, os.O_RDONLY)
        try:
            supervisor_sha, _ = _hash_fd(fd, MAX_JSON_BYTES)
        finally:
            os.close(fd)
        supervisor = stack.enter_context(_sealed_file(source, supervisor_sha))
        sealed_inputs.append(supervisor)
        files.append(_mount(supervisor, "/runtime/supervisor.py"))
        total += adapter.size + supervisor.size
        if total > MAX_PLAN_BYTES:
            raise ModelRefusal("complete sealed model launch exceeds byte ceiling")
        snapshot_directory = _path(snapshot_directory)
        parent_fd = _open(snapshot_directory, os.O_RDONLY | os.O_DIRECTORY)
        stack.callback(os.close, parent_fd)
        parent_info = os.fstat(parent_fd)
        child_fd = os.open("index", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                           | os.O_CLOEXEC, dir_fd=parent_fd)
        stack.callback(os.close, child_fd)
        child_info = os.fstat(child_fd)
        for info in (parent_info, child_info):
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise ModelRefusal("index parent and fixed child must be owned private directories")
        configuration = {"schema": "sia-raw-vector-model-launch-v1",
                         "model_name": admitted.identity["model_name"],
                         "model_identity": admitted.identity, "embedding": dict(embedding),
                         "environment": dict(_ENV), "timeout": timeout,
                         "adapter_sha256": adapter.sha256, "supervisor_sha256": supervisor.sha256,
                         "system_runtime": runtime_identity, "sealed_bytes": total,
                         "request": _json(_canonical(request)), "non_claims": list(NON_CLAIMS)}
        config_bytes = _canonical(configuration)
        config_fd = stack.enter_context(_sealed_bytes(config_bytes))
        files.append({"kind": "file", "fd": config_fd,
                      "destination": "/runtime/config.json", "sha256": _sha(config_bytes),
                      "bytes": len(config_bytes), "executable": False})
        argv = ["/usr/bin/bwrap", "--unshare-user", "--unshare-pid", "--unshare-net",
                "--unshare-ipc", "--unshare-uts", "--die-with-parent", "--new-session",
                "--clearenv", "--cap-drop", "ALL", "--proc", "/proc", "--dev", "/dev",
                "--size", "64000000", "--tmpfs", "/work", "--dir", "/work/home", "--dir", "/work/tmp",
                "--dir", "/work/gbrain",
                "--size", "64000000", "--tmpfs", "/runtime",
                "--size", "64000000", "--tmpfs", "/models",
                "--size", "64000000", "--tmpfs", "/usr",
                "--size", "64000000", "--tmpfs", "/empty", "--chdir", "/empty",
                "--symlink", "usr/lib", "/lib"]
        directories = set()
        for item in files:
            parent = str(Path(item["destination"]).parent)
            while parent != "/":
                directories.add(parent)
                parent = str(Path(parent).parent)
        for directory in sorted(directories, key=lambda value: (value.count("/"), value)):
            argv.extend(["--dir", directory])
        inputs = []
        for item in files:
            if item["kind"] == "symlink":
                argv.extend(["--symlink", item["target"], item["destination"]])
            else:
                os.lseek(item["fd"], 0, os.SEEK_SET)
                argv.extend(["--perms", "0500" if item.get("executable") else "0400",
                             "--ro-bind-data", str(item["fd"]), item["destination"]])
                inputs.append(item["fd"])
        # bwrap --bind consumes an already-open DIRECTORY fd pathname. Unlike
        # memfds this source has a real path; the parent identity is rechecked.
        argv.extend(["--bind", f"/proc/self/fd/{parent_fd}", "/private-index",
                     "--remount-ro", "/runtime", "--remount-ro", "/models",
                     "--remount-ro", "/usr", "--remount-ro", "/empty"])
        inputs.append(parent_fd)
        for key, value in sorted(_ENV.items()):
            argv.extend(["--setenv", key, value])
        argv.extend(["--", "/usr/bin/python3", "-I", "-S", "-B",
                     "/runtime/supervisor.py", "--supervise", "/runtime/config.json"])
        admitted.assert_current()
        plan = LaunchPlan(argv, tuple(inputs), tuple(inputs), dict(_ENV), configuration,
                          _sha(config_bytes), list(NON_CLAIMS))
        yield plan
        for item in sealed_inputs:
            item.assert_current()
        # Mutable private PGlite files do not invalidate the directory inode.
        rebound = _open(snapshot_directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            info = os.fstat(rebound)
            if (info.st_dev, info.st_ino, info.st_uid, info.st_mode) != (
                    parent_info.st_dev, parent_info.st_ino, parent_info.st_uid, parent_info.st_mode):
                raise ModelRefusal("private index descriptor parent generation changed")
        finally:
            os.close(rebound)
        child_rebound = None
        try:
            child_rebound = os.open("index", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                                    | os.O_CLOEXEC, dir_fd=parent_fd)
            for info in (os.fstat(child_fd), os.fstat(child_rebound)):
                if (info.st_dev, info.st_ino, info.st_uid, info.st_mode) != (
                        child_info.st_dev, child_info.st_ino, child_info.st_uid, child_info.st_mode):
                    raise ModelRefusal("private index child generation changed")
        except OSError as exc:
            raise ModelRefusal("private index child generation changed") from exc
        finally:
            if child_rebound is not None:
                os.close(child_rebound)
        admitted.assert_current()


def _api(method, path, payload=None, timeout=1):
    connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=timeout)
    try:
        raw = None if payload is None else _canonical(payload)
        connection.request(method, path, body=raw,
                           headers={"Content-Type": "application/json"} if raw else {})
        response = connection.getresponse()
        body = response.read(MAX_JSON_BYTES + 1)
        if response.status != 200:
            raise ModelRefusal("owned model API returned a failure")
        return _json(body)
    finally:
        connection.close()


def _spawn_service(config):
    # Logs are bounded by the private work tmpfs and the enclosing scope; they
    # are not allowed to corrupt the adapter's JSON stdout channel.
    log = open("/work/ollama.log", "xb", buffering=0)
    try:
        process = subprocess.Popen(["/runtime/ollama/bin/ollama", "serve"],
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   close_fds=True, env=dict(_ENV), cwd="/empty")
    finally:
        log.close()
    return process


def _warm_model(config, service):
    deadline = time.monotonic() + config["timeout"]
    while True:
        if service.poll() is not None:
            raise ModelRefusal("owned model service exited before readiness")
        try:
            _api("GET", "/api/tags")
            break
        except (OSError, http.client.HTTPException, ModelRefusal):
            if time.monotonic() >= deadline:
                raise ModelRefusal("owned model readiness timeout")
            time.sleep(0.05)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ModelRefusal("owned model warmup timeout")
    _api("POST", "/api/embed", {"model": config["model_name"], "input": "binding probe"},
         timeout=remaining)


def _process(pid):
    prefix = "/proc/" + str(pid)
    raw = Path(prefix + "/stat").read_text()
    fields = raw[raw.rindex(")") + 2:].split()
    executable = os.readlink(prefix + "/exe")
    with open(prefix + "/exe", "rb") as stream:
        before = os.fstat(stream.fileno())
        sha, size = _hash_fd(stream.fileno(), MAX_SEALED_BYTES)
        if _generation(before) != _generation(os.fstat(stream.fileno())):
            raise ModelRefusal("process executable generation changed while hashing")
    return {"pid": pid, "ppid": int(fields[1]), "starttime": fields[19],
            "executable": executable, "executable_sha256": sha,
            "executable_device": before.st_dev, "executable_inode": before.st_ino,
            "executable_bytes": size,
            "argv": Path(prefix + "/cmdline").read_bytes().rstrip(b"\0").decode().split("\0"),
            "network_namespace": os.readlink(prefix + "/ns/net"),
            "mount_namespace": os.readlink(prefix + "/ns/mnt"),
            "pid_namespace": os.readlink(prefix + "/ns/pid")}


def _mounted_executable_identity(path):
    """Read the immutable mount object, independently of /proc display names.

ro-bind-data can expose an already-unlinked backing inode. Its link count is
not a source-package alias admission rule: the namespace's immutable mount,
opened without following links, supplies the actual object authority here.
"""
    descriptor = None
    try:
        descriptor = _open(path, os.O_RDONLY)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not before.st_mode & 0o111 \
                or not 0 < before.st_size <= MAX_SEALED_BYTES \
                or os.pread(descriptor, 4, 0) != b"\x7fELF":
            raise ModelRefusal("mounted runtime executable is not a bounded regular ELF")
        sha, size = _hash_fd(descriptor, MAX_SEALED_BYTES)
        if _generation(before) != _generation(os.fstat(descriptor)) or size != before.st_size:
            raise ModelRefusal("mounted runtime executable generation changed")
        return {"device": before.st_dev, "inode": before.st_ino, "sha256": sha}
    except (OSError, ValueError) as exc:
        raise ModelRefusal("mounted runtime executable identity refused") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _serving_generation(config, service):
    if service.poll() is not None:
        raise ModelRefusal("owned model service generation exited")
    identity = config["model_identity"]
    try:
        service_mount = _mounted_executable_identity("/runtime/ollama/bin/ollama")
        runner_mount = _mounted_executable_identity("/runtime/ollama/lib/ollama/llama-server")
        parent = _process(service.pid)
        if parent["executable_device"] != service_mount["device"] \
                or parent["executable_inode"] != service_mount["inode"] \
                or parent["executable_sha256"] != identity["ollama_sha256"] \
                or service_mount["sha256"] != identity["ollama_sha256"] \
                or runner_mount["sha256"] != identity["runner_sha256"]:
            raise ModelRefusal("owned model service executable generation mismatch")
        runners = []
        for name in os.listdir("/proc"):
            if name.isdigit():
                try:
                    info = _process(int(name))
                except (OSError, ValueError, ModelRefusal):
                    continue
                if info["ppid"] == service.pid \
                        and info["executable_device"] == runner_mount["device"] \
                        and info["executable_inode"] == runner_mount["inode"]:
                    runners.append(info)
        if len(runners) != 1:
            raise ModelRefusal("owned model runner generation is missing or ambiguous")
        runner = runners[0]
        args = runner["argv"]
        if runner["executable_sha256"] != identity["runner_sha256"] \
                or "--model" not in args \
                or args[args.index("--model") + 1] != identity["model_path"] \
                or runner["network_namespace"] != parent["network_namespace"]:
            raise ModelRefusal("owned model runner input generation mismatch")
        loaded = _api("GET", "/api/ps")
        models = loaded.get("models") if type(loaded) is dict else None
        if type(models) is not list or len(models) != 1 \
                or models[0].get("digest") != identity["manifest_sha256"] \
                or models[0].get("name") != config["model_name"] \
                or models[0].get("size_vram") != 0:
            raise ModelRefusal("owned model loaded identity or CPU policy mismatch")
        return {"service": parent, "runner": runner,
                "model_manifest_sha256": identity["manifest_sha256"],
                "execution_policy": "ollama-cpu-only-v1"}
    except (OSError, ValueError, KeyError, IndexError, UnicodeError) as exc:
        raise ModelRefusal("owned model generation inspection refused") from exc


def _invoke_in_namespace(config):
    request = _json(_canonical(config["request"]))
    parent_fd = os.open("/private-index", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        request["snapshot"]["fd"] = parent_fd
        raw = _canonical(request)
        with _sealed_bytes(raw) as request_fd:
            result = _bounded_adapter(["/runtime/adapter", "--request-fd", str(request_fd)],
                                      (parent_fd, request_fd), config["timeout"])
        if len(result.stdout) + len(result.stderr) > MAX_OUTPUT_BYTES \
                or result.stderr or result.returncode not in (0, 2) \
                or not result.stdout.endswith(b"\n"):
            raise ModelRefusal("owned adapter output contract refused")
        payload = _json(result.stdout)
        if type(payload) is not dict:
            raise ModelRefusal("owned adapter output is not an object")
        return {"payload": payload, "returncode": result.returncode,
                "request_sha256": _sha(raw), "stdout_sha256": _sha(result.stdout),
                "executable_sha256": config["adapter_sha256"]}
    finally:
        os.close(parent_fd)


def _bounded_adapter(argv, descriptors, timeout):
    """Drain bounded bytes continuously, including a producer's stderr."""
    process = None
    output = {"stdout": bytearray(), "stderr": bytearray()}
    deadline, count = time.monotonic() + timeout, 0
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, pass_fds=descriptors, close_fds=True, env=dict(_ENV), cwd="/empty")
        with selectors.DefaultSelector() as selector:
            for name in output:
                stream = getattr(process, name)
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(argv, timeout)
                for key, _ in selector.select(min(remaining, 0.1)):
                    block = os.read(key.fileobj.fileno(), 262_144)
                    if not block:
                        selector.unregister(key.fileobj)
                        continue
                    count += len(block)
                    if count > MAX_OUTPUT_BYTES:
                        raise ModelRefusal("owned adapter output byte ceiling exceeded")
                    output[key.data].extend(block)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, timeout)
            code = process.wait(timeout=remaining)
        return subprocess.CompletedProcess(argv, code, bytes(output["stdout"]), bytes(output["stderr"]))
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=1)
            for name in output:
                getattr(process, name).close()


def run_owned_session(config):
    """Own only a new service; PID namespace death owns all descendants."""
    service = None
    try:
        service = _spawn_service(config)
        if service.poll() is not None:
            raise ModelRefusal("owned model service failed to start")
        _warm_model(config, service)
        before = _serving_generation(config, service)
        observation = _invoke_in_namespace(config)
        after = _serving_generation(config, service)
        if before != after:
            raise ModelRefusal("owned model serving generation changed")
        return {"schema": "sia-raw-vector-served-observation-v1", "status": "observed",
                "observation": observation, "serving_generation": before,
                "launch_config_sha256": _sha(_canonical(config)),
                "non_claims": list(NON_CLAIMS)}
    except subprocess.TimeoutExpired as exc:
        raise ModelRefusal("owned model or adapter timeout") from exc
    except OSError as exc:
        raise ModelRefusal("owned model launch or communication refused") from exc
    finally:
        if service is not None:
            if service.poll() is None:
                service.terminate()
            try:
                service.wait(timeout=1)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait(timeout=1)


def invoke_model_adapter(*, admitted, shared_runtime, executable, executable_sha256,
                         request, snapshot_directory, timeout, scratch_parent):
    """Host transport; caller must still admit adapter and benchmark semantics."""
    import sialib
    with launch_plan(admitted=admitted, shared_runtime=shared_runtime,
                     executable=executable, executable_sha256=executable_sha256,
                     request=request, snapshot_directory=snapshot_directory,
                     timeout=timeout) as plan:
        try:
            result = sialib._run_bounded_text_process(
                plan.argv, env={"PATH": "/usr/bin", "LANG": "C.UTF-8"},
                timeout=timeout, cwd=scratch_parent, pass_fds=plan.pass_fds,
                label="private model namespace", output_limit=sialib.MAX_STATE_JSON_BYTES)
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            raise ModelRefusal("private model namespace launch refused") from exc
        if result.returncode != 0 or result.stderr or not result.stdout.endswith("\n"):
            raise ModelRefusal("private model namespace output refused: " + result.stderr[:4096])
        payload = _json(result.stdout)
        if type(payload) is not dict or payload.get("status") != "observed" \
                or payload.get("launch_config_sha256") != plan.config_sha256:
            raise ModelRefusal("private model namespace observation identity refused")
        payload["model_identity"] = admitted.identity
        payload["launch_config"] = plan.config
        return payload


def _main():
    if len(sys.argv) != 3 or sys.argv[1] != "--supervise" \
            or sys.argv[2] != "/runtime/config.json":
        raise ModelRefusal("private model supervisor has no ambient launch mode")
    with open(sys.argv[2], "rb") as stream:
        config = _json(stream.read(MAX_JSON_BYTES + 1))
    result = run_owned_session(config)
    sys.stdout.buffer.write(_canonical(result) + b"\n")
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        _main()
    except ModelRefusal as error:
        sys.stderr.write(str(error) + "\n")
        try:
            with open("/work/ollama.log", "rb") as stream:
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                stream.seek(max(0, size - 4096))
                sys.stderr.write(stream.read(4096).decode("utf-8", errors="replace"))
        except OSError:
            pass
        raise SystemExit(2)
