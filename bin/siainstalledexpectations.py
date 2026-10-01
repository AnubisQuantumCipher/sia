"""Observe the active installed-overlay selection as a closed local input.

The installed pin is the local selection record.  Its managed receipt, the
overlay runtime receipt and the selected executable must all agree while held
through ordinary descriptors.  The resulting expectations document is input
for the separate installed-engine verifier; this observer never runs it.
"""

import copy
import hashlib
import json
import math
import os
import stat

import siainstalledengine as engine
import siasourcebatch as source


NON_CLAIMS = (
    "This is an observed local installed selection and exact receipt/artifact consistency relation, not independently authenticated build provenance or permission supplied by a remote authority.",
    "The pin selects the installed overlay; its managed receipt and runtime receipt must agree exactly, but mutually replaced files are not protected against a hostile same-user process.",
    "The executable is read only to bind its current bytes and ELF shape. No engine operation, index access, migration, synchronization, retrieval or output occurs.",
    "The returned expectations document is a detached input to the separate installed-engine boundary; observing it does not establish source truth, current corpus versions, delivery or human receipt.",
    "No installation, configuration change, clock observation, JACKAL assurance, biological cognition, cognitive authorization or held-out retrieval win is established.",
)
_RESULT_KEYS = {
    "schema", "status", "expectations", "expected_expectations_sha256",
    "non_claims", "observation_sha256",
}
_ERRORS = (OSError, ValueError, RuntimeError, TypeError, KeyError,
           IndexError, AttributeError, OverflowError, RecursionError)


class InstalledExpectationsRefusal(ValueError):
    """The complete installed selection could not be observed consistently."""

    def __init__(self, reason, *, upstream=None):
        self.reason = reason
        self.non_claims = list(NON_CLAIMS)
        self.upstream_reason = getattr(upstream, "reason", None)
        self.upstream_non_claims = copy.deepcopy(
            getattr(upstream, "non_claims", ()))
        super().__init__("installed expectations refused: " + reason)


def _refuse(reason):
    raise InstalledExpectationsRefusal(reason)


def _digest(value):
    return type(value) is str and engine._DIGEST.fullmatch(value) is not None


def _native(owner):
    if type(owner) is not dict:
        _refuse("owner-contract")
    capacities = {key: owner.get(key) for key in engine._CAPACITIES}
    if any(type(value) is not int or value <= 0
           for value in capacities.values()):
        _refuse("owner-capacity-contract")
    return {"os": os, "json": json, "hashlib": hashlib, "math": math,
            **capacities}


class _Artifact:
    """Hold one installed artifact and its complete streamed digest."""

    def __init__(self, native, path, ceiling, *, executable=False):
        self.native, self.path = native, path
        self.parent = self.fd = None
        self.raw = None
        try:
            source._canonical_path(native, path)
            if path == os.sep or ".gbrain" in path.split(os.sep):
                _refuse("artifact-path-contract")
            self.parent = source._DirectoryChain(native, os.path.dirname(path))
            self.name = os.path.basename(path)
            self.fd = os.open(
                self.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                dir_fd=self.parent.fd)
            info = os.fstat(self.fd)
            if type(ceiling) is not int or ceiling <= 0 \
                    or not stat.S_ISREG(info.st_mode) \
                    or info.st_uid != os.geteuid() or info.st_nlink != 1 \
                    or info.st_mode & 0o022 \
                    or not 0 < info.st_size <= ceiling \
                    or executable and not info.st_mode & 0o111:
                _refuse("unsafe-installed-artifact")
            self.identity = source._generation(info)
            if executable and os.pread(self.fd, 4, 0) != b"\x7fELF":
                _refuse("installed-executable-format")
            digest = hashlib.sha256()
            offset, chunks = 0, []
            while offset < info.st_size:
                block = os.pread(
                    self.fd, min(1_048_576, info.st_size - offset), offset)
                if not block:
                    _refuse("installed-artifact-short-read")
                digest.update(block)
                if not executable:
                    chunks.append(block)
                offset += len(block)
            if os.pread(self.fd, 1, offset):
                _refuse("installed-artifact-grew-during-read")
            self.sha256 = digest.hexdigest()
            if not executable:
                self.raw = b"".join(chunks)
            self.current()
        except BaseException:
            self.close()
            raise

    def current(self):
        if self.parent is None or self.fd is None:
            _refuse("closed-installed-artifact")
        self.parent.current()
        named = os.stat(
            self.name, dir_fd=self.parent.fd, follow_symlinks=False)
        if source._generation(named) != self.identity \
                or source._generation(os.fstat(self.fd)) != self.identity:
            _refuse("installed-artifact-generation-changed")
        self.parent.current()

    def close(self):
        descriptor, self.fd = self.fd, None
        try:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        finally:
            parent, self.parent = self.parent, None
            if parent is not None:
                parent.close()


def _pin(raw):
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise InstalledExpectationsRefusal("installed-pin-encoding", upstream=exc) from exc
    values = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        if line.count("=") != 1:
            _refuse("installed-pin-fields")
        key, value = line.split("=", 1)
        if key not in engine._PIN_KEYS or key in values or not value:
            _refuse("installed-pin-fields")
        values[key] = value
    try:
        engine._Admission._pin_fields(values)
    except engine.InstalledEngineRefusal as exc:
        raise InstalledExpectationsRefusal("installed-pin-fields", upstream=exc) from exc
    return values


def _selection(owner, native):
    paths = {key: owner.get(key) for key in engine._PATHS}
    for path in paths.values():
        if type(path) is not str:
            _refuse("owner-path-contract")
        source._canonical_path(native, path)
    joins = {
        "GBRAIN": os.path.join(paths["TOOLCHAIN"], "gbrain", "bin", "gbrain"),
        "GBRAIN_PIN": os.path.join(paths["SHARE"], "GBRAIN_PIN"),
        "GBRAIN_PIN_RECEIPT": os.path.join(
            paths["STATE"], "managed-install", "gbrain-pin"),
        "GBRAIN_RUNTIME_RECEIPT": os.path.join(
            paths["TOOLCHAIN"], "gbrain", ".sia-release"),
        "CORPUS_OWNER_LOCK": os.path.join(paths["STATE"], "corpus-owner.lock"),
        "GBRAIN_OWNER_LOCK": os.path.join(paths["STATE"], "gbrain-owner.lock"),
    }
    if any(paths[key] != value for key, value in joins.items()) \
            or owner.get("GBRAIN_SOURCE") != "sia":
        _refuse("installed-path-or-source-join")
    return paths


def _observe(owner):
    native = _native(owner)
    paths = _selection(owner, native)
    metadata_ceiling = owner["MAX_CONFIG_BYTES"]
    executable_ceiling = engine.structural.MAX_EXECUTABLE_BYTES
    artifacts = []
    try:
        pin = _Artifact(native, paths["GBRAIN_PIN"], metadata_ceiling)
        artifacts.append(pin)
        pin_receipt = _Artifact(
            native, paths["GBRAIN_PIN_RECEIPT"], metadata_ceiling)
        artifacts.append(pin_receipt)
        runtime_receipt = _Artifact(
            native, paths["GBRAIN_RUNTIME_RECEIPT"], metadata_ceiling)
        artifacts.append(runtime_receipt)
        executable = _Artifact(
            native, paths["GBRAIN"], executable_ceiling, executable=True)
        artifacts.append(executable)
        fields = _pin(pin.raw)
        expected_pin_receipt = "\n".join((
            "managed-by=khephri.sia", "kind=gbrain-pin",
            "path=" + paths["GBRAIN_PIN"], "sha256=" + pin.sha256, ""))
        if pin_receipt.raw != expected_pin_receipt.encode("utf-8"):
            _refuse("installed-pin-receipt")
        expected_runtime = "\n".join((
            "managed-by=khephri.sia", "commit=" + fields["commit"],
            "version=" + fields["version"],
            "bun_lock_sha256=" + fields["bun_lock_sha256"],
            "overlay_sha256=" + fields["overlay_sha256"],
            "overlay_tree_oid=" + fields["overlay_tree_oid"],
            "binary_sha256=" + executable.sha256, ""))
        if runtime_receipt.raw != expected_runtime.encode("utf-8"):
            _refuse("installed-overlay-runtime-receipt")
        limits = {
            "max_executable_bytes": executable_ceiling,
            "max_metadata_bytes": metadata_ceiling,
            "max_request_bytes": engine.structural.MAX_PROJECTION_REQUEST_BYTES,
            "max_output_bytes": min(
                owner["MAX_EXTERNAL_OUTPUT_BYTES"],
                owner["MAX_STATE_JSON_BYTES"]),
        }
        expectations = {
            "schema": engine.EXPECTATIONS_SCHEMA,
            "source_id": "sia", **fields,
            "gbrain_pin_sha256": pin.sha256,
            "gbrain_pin_receipt_sha256": pin_receipt.sha256,
            "gbrain_runtime_receipt_sha256": runtime_receipt.sha256,
            "gbrain_executable_sha256": executable.sha256,
            "limits": limits,
        }
        wire = source.native_bytes(native, expectations)
        expected = hashlib.sha256(wire).hexdigest()
        body = {
            "schema": "sia-installed-overlay-engine-expectations-observation-v1",
            "status": "observed-local-install-selection",
            "expectations": expectations,
            "expected_expectations_sha256": expected,
            "non_claims": list(NON_CLAIMS),
        }
        body["observation_sha256"] = hashlib.sha256(
            source.native_bytes(native, body)).hexdigest()
        source._json_size(
            native, body, owner["MAX_STATE_JSON_BYTES"], ascii_only=True)
        result = copy.deepcopy(body)
        if source.native_bytes(native, result) \
                != source.native_bytes(native, body):
            _refuse("observation-copy-changed")
        for artifact in artifacts:
            artifact.current()
        if set(result) != _RESULT_KEYS:
            _refuse("observation-result-shape")
        return result
    finally:
        for artifact in reversed(artifacts):
            artifact.close()


def observe_installed_expectations(owner):
    """Return one complete detached observation of the installed selection."""
    try:
        if type(owner) is not dict or not callable(owner.get("corpus_owner")):
            _refuse("owner-contract")
        with owner["corpus_owner"]():
            return _observe(owner)
    except InstalledExpectationsRefusal:
        raise
    except _ERRORS as exc:
        raise InstalledExpectationsRefusal(
            "installed-selection-observation", upstream=exc) from exc
