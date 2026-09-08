"""Additive installed-overlay transport, not a source/index generation.

The caller supplies its own expectation document and pin, and already owns
the ordinary corpus lease. This boundary admits the installed pin, managed
pin receipt, overlay-aware release receipt and actual executable bytes before
entering SIA's gbrain_owner. It never selects/adopts/builds/syncs a runtime.

Projection requests use an identity-bound private directory and regular file,
not a kernel-sealed memfd: the existing no-follow --params-file parser rejects
a direct /proc/self/fd/<file> symlink. The directory descriptor selects the
known regular request leaf. Local scratch writes are not engine no-write
evidence. Existing siasourceengine APIs and generation schemas are untouched.

The additive ordinary GET method captures source-qualified CLI stdout, not
source-version or rendered-field admission. It does not pass --no-migrate:
ordinary GET can run connection migrations and retrieval bookkeeping. Its
separate result/nonclaims do not inherit the projection operation's no-write
fields. Existing version/projection schemas, keys and statuses are unchanged;
their shared nonclaims now scope the projection allowance to projection calls.
"""

import contextlib
import contextvars
import copy
import datetime
import hashlib
import json
import math
import os
import re
import stat
import sys
import tempfile

import siasourcebatch as source
import siasourceengine as structural


NON_CLAIMS = (
    "Installed artifact bytes and native descriptor identities are joined to independently supplied expectations; receipts alone do not select or authorize their own expected runtime.",
    "This is an installed-overlay transport observation, not a source generation, synchronized index, engine-page truth, current-version projection admission or held-out retrieval evidence.",
    "Projection calls expose only the explicitly allowlisted no-migrate render-projection front door; operation semantics and every returned projection field still require the caller's separate admission.",
    "Request transport uses an identity-bound private directory and regular leaf, not a kernel-sealed file; its bounded scratch writes are not evidence that an engine operation performed no writes.",
    "The existing SIA engine lease coordinates participating local processes; descriptor checks do not protect against hostile same-user mutation or prove receipt build provenance beyond the checked bytes.",
    "No runtime selection, adoption, installation, synchronization, migration, source publication, memory use, clock observation, CLI activation, JACKAL assurance or biological cognition is established.",
    "Returned objects remain checked through this context's normal exit; a retained observation is not fresh authority after its descriptor lifetime ends.",
)

GET_NON_CLAIMS = (
    "Installed artifact bytes and native descriptor identities are joined to independently supplied expectations; receipts alone do not select or authorize their own expected runtime.",
    "This captures stdout and stderr from one ordinary source-qualified GET through the held executable; it is not a source generation, synchronized index, source-version join, rendered-field admission, output delivery or held-out retrieval evidence.",
    "Ordinary GET is not the no-migrate render-projection operation: connection migrations and retrieval bookkeeping may occur; this transport does not establish whether they occurred or that no engine writes occurred.",
    "GET stdout is the engine's CLI rendition, not necessarily original Markdown bytes; source identity, complete displayed fields and exact current-version fidelity still require separate projection admission.",
    "The existing SIA engine lease coordinates participating local processes; descriptor checks do not protect against hostile same-user mutation or prove receipt build provenance beyond the checked bytes.",
    "No runtime selection, adoption, installation, source publication, memory-use acknowledgment, clock observation, CLI activation, JACKAL assurance or biological cognition is established.",
    "Returned objects remain checked through this context's normal exit; a retained observation is not fresh authority after its descriptor lifetime ends.",
)

EXPECTATIONS_SCHEMA = "sia-installed-overlay-engine-expectations-v1"
PROJECTION_OPERATION = "get_page_render_projection"
# Reuse the admitted source/live subject representation, not a fitted or
# widened transport limit. Its grammar is ASCII, so character and byte
# lengths agree for every admitted subject.
MAX_GET_SUBJECT_BYTES = source._live.activation.MAX_SUBJECT_BYTES
_GET_SUBJECT = source._live._SUBJECT
_PIN_KEYS = {
    "commit", "version", "bun_lock_sha256", "overlay_sha256",
    "overlay_tree_oid", "verified",
}
_ARTIFACT_KEYS = {
    "gbrain_pin_sha256", "gbrain_pin_receipt_sha256",
    "gbrain_runtime_receipt_sha256", "gbrain_executable_sha256",
}
_LIMIT_KEYS = {
    "max_executable_bytes", "max_metadata_bytes", "max_request_bytes",
    "max_output_bytes",
}
_EXPECTATION_KEYS = {"schema", "source_id", "limits"} | _PIN_KEYS | _ARTIFACT_KEYS
_PATHS = (
    "HOME", "SHARE", "STATE", "CORPUS", "TOOLCHAIN", "BUN_DIR", "GBRAIN",
    "GBRAIN_PIN", "GBRAIN_PIN_RECEIPT", "GBRAIN_RUNTIME_RECEIPT",
    "CORPUS_OWNER_LOCK", "GBRAIN_OWNER_LOCK",
)
_CAPACITIES = (
    "MAX_CONFIG_BYTES", "MAX_CONFIG_PATH_CHARS", "MAX_STATE_JSON_BYTES",
    "MAX_EXTERNAL_OUTPUT_BYTES", "MAX_JSON_SAFE_INTEGER",
)
_OPERATIONS = (
    "corpus_owner", "gbrain_owner", "_chain_descriptor_path",
    "_run_bounded_text_process", "_strict_json_loads",
)
_CONTEXTS = ("_CORPUS_OWNER_DEPTH", "_CORPUS_OWNER_FD", "_GBRAIN_OWNER_FD")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_OID = re.compile(r"[0-9a-f]{40}")
_VERSION = structural._VERSION
_ERRORS = (OSError, ValueError, RuntimeError, TypeError, KeyError, IndexError,
           AttributeError, OverflowError, RecursionError)


class InstalledEngineRefusal(ValueError):
    def __init__(self, reason, *, upstream=None):
        self.reason = reason
        self.non_claims = list(NON_CLAIMS)
        self.upstream_reason = getattr(upstream, "reason", None)
        self.upstream_non_claims = getattr(upstream, "non_claims", ())
        super().__init__("installed engine refused: " + reason)


class InstalledEngineGetRefusal(InstalledEngineRefusal):
    """Ordinary GET failed admission; no projection no-write claim follows."""

    def __init__(self, reason, *, upstream=None):
        super().__init__(reason, upstream=upstream)
        self.non_claims = list(GET_NON_CLAIMS)


def _get_refusal(exc, fallback):
    reason = exc.reason if isinstance(exc, InstalledEngineRefusal) else fallback
    return InstalledEngineGetRefusal(reason, upstream=exc)


def _refuse(reason):
    raise InstalledEngineRefusal(reason)


def _digest(value):
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _keys(value, keys, reason):
    if type(value) is not dict or len(value) != len(keys) \
            or any(type(key) is not str for key in value) \
            or set(value) != keys:
        _refuse(reason)


def _plain_pin(value):
    kind = type(value)
    if value is None or kind in (bool, int, str):
        return kind, value
    if kind is list:
        return kind, tuple(_plain_pin(child) for child in value)
    if kind is dict and all(type(key) is str for key in value):
        return kind, tuple((key, _plain_pin(child)) for key, child in value.items())
    _refuse("nonplain-tail-value")


def _plain_same(value, pin):
    kind, expected = pin
    if type(value) is not kind:
        return False
    if kind is dict:
        return len(value) == len(expected) \
            and all(type(key) is str for key in value) \
            and all(key in value and _plain_same(value[key], child)
                    for key, child in expected)
    if kind is list:
        return len(value) == len(expected) \
            and all(_plain_same(child, child_pin)
                    for child, child_pin in zip(value, expected))
    return value == expected


def _close_fd(descriptor):
    if descriptor is not None:
        try:
            os.close(descriptor)
        except OSError:
            pass


def _cleanup(resource):
    preserving = sys.exc_info()[0] is not None
    try:
        resource.close()
    except BaseException:
        if not preserving:
            raise


@contextlib.contextmanager
def _preserve_exception(manager):
    value = manager.__enter__()
    try:
        yield value
    except BaseException:
        error = sys.exc_info()
        try:
            manager.__exit__(*error)
        except BaseException:
            pass
        raise
    else:
        manager.__exit__(None, None, None)


class _Admission:
    def __init__(self, owner, expectations, expected, authority_current):
        if type(owner) is not dict or not callable(authority_current) or not _digest(expected):
            _refuse("explicit-owner-expectations-authority-contract")
        self.owner = owner
        self.authority = authority_current
        self.expected = expected
        self.paths = {key: owner.get(key) for key in _PATHS}
        self.capacities = {key: owner.get(key) for key in _CAPACITIES}
        self.operations = {key: owner.get(key) for key in _OPERATIONS}
        self.contexts = {key: owner.get(key) for key in _CONTEXTS}
        self.source_id = owner.get("GBRAIN_SOURCE")
        if any(type(value) is not int or value <= 0 for value in self.capacities.values()) \
                or any(not callable(value) for value in self.operations.values()) \
                or any(type(value) is not contextvars.ContextVar for value in self.contexts.values()) \
                or type(self.source_id) is not str or self.source_id != "sia":
            _refuse("owner-basis-contract")
        # Use the native source serializer with captured standard providers;
        # native stat identities are never routed through live JSON floats.
        self.native_owner = {
            "os": os, "json": json, "hashlib": hashlib, "math": math,
            **self.capacities,
        }
        for value in self.paths.values():
            source._canonical_path(self.native_owner, value)
            if value == os.sep or ".gbrain" in value.split(os.sep):
                _refuse("owner-path-contract")
        joins = {
            "GBRAIN": os.path.join(self.paths["TOOLCHAIN"], "gbrain", "bin", "gbrain"),
            "GBRAIN_PIN": os.path.join(self.paths["SHARE"], "GBRAIN_PIN"),
            "GBRAIN_PIN_RECEIPT": os.path.join(self.paths["STATE"], "managed-install", "gbrain-pin"),
            "GBRAIN_RUNTIME_RECEIPT": os.path.join(self.paths["TOOLCHAIN"], "gbrain", ".sia-release"),
            "CORPUS_OWNER_LOCK": os.path.join(self.paths["STATE"], "corpus-owner.lock"),
            "GBRAIN_OWNER_LOCK": os.path.join(self.paths["STATE"], "gbrain-owner.lock"),
        }
        if any(self.paths[key] != value for key, value in joins.items()):
            _refuse("installed-path-join")
        self.basis_current()
        _keys(expectations, _EXPECTATION_KEYS, "expectations-shape")
        _keys(expectations["limits"], _LIMIT_KEYS, "expectation-limits-shape")
        # Bound the complete native representation before variable-length
        # semantic regex/date work; final wire/hash admission remains below.
        source._json_size(self.native_owner, expectations,
                          self.capacities["MAX_STATE_JSON_BYTES"], ascii_only=True)
        if expectations["schema"] != EXPECTATIONS_SCHEMA \
                or type(expectations["schema"]) is not str \
                or expectations["source_id"] != self.source_id \
                or type(expectations["source_id"]) is not str \
                or any(not _digest(expectations[key]) for key in _ARTIFACT_KEYS):
            _refuse("expectations-contract")
        self._pin_fields({key: expectations[key] for key in _PIN_KEYS})
        ceilings = {
            "max_executable_bytes": structural.MAX_EXECUTABLE_BYTES,
            "max_metadata_bytes": self.capacities["MAX_CONFIG_BYTES"],
            "max_request_bytes": structural.MAX_PROJECTION_REQUEST_BYTES,
            "max_output_bytes": self.capacities["MAX_EXTERNAL_OUTPUT_BYTES"],
        }
        for key, ceiling in ceilings.items():
            value = expectations["limits"][key]
            if type(value) is not int or not 0 < value <= ceiling:
                _refuse("expectation-byte-ceiling")
        if expectations["limits"]["max_output_bytes"] > self.capacities["MAX_STATE_JSON_BYTES"]:
            _refuse("expectation-byte-ceiling")
        self.supplied = expectations
        self.raw = self.wire(expectations)
        if hashlib.sha256(self.raw).hexdigest() != expected:
            _refuse("external-expectations-pin")
        self.tail = _plain_pin(expectations)
        self.expectations = copy.deepcopy(expectations)
        self.limits = self.expectations["limits"]
        self.current()

    @staticmethod
    def _pin_fields(values):
        _keys(values, _PIN_KEYS, "pin-fields")
        if any(type(value) is not str for value in values.values()) \
                or _OID.fullmatch(values["commit"]) is None \
                or _OID.fullmatch(values["overlay_tree_oid"]) is None \
                or _VERSION.fullmatch(values["version"]) is None \
                or not _digest(values["bun_lock_sha256"]) \
                or not _digest(values["overlay_sha256"]):
            _refuse("pin-fields")
        try:
            date = datetime.date.fromisoformat(values["verified"])
        except ValueError as exc:
            raise InstalledEngineRefusal("pin-verified-date", upstream=exc) from exc
        if date.isoformat() != values["verified"]:
            _refuse("pin-verified-date")

    def wire(self, value):
        return source.native_bytes(self.native_owner, value)

    def basis_current(self):
        for key, expected in {**self.paths, **self.capacities,
                              "GBRAIN_SOURCE": self.source_id}.items():
            actual = self.owner.get(key)
            if type(actual) is not type(expected) or actual != expected:
                _refuse("owner-basis-changed")
        if any(self.owner.get(key) is not value
               for key, value in {**self.operations, **self.contexts}.items()):
            _refuse("owner-operation-changed")

    def final_current(self):
        self.basis_current()
        if not _plain_same(self.supplied, self.tail) \
                or not _plain_same(self.expectations, self.tail):
            _refuse("expectations-changed")

    def current(self):
        self.final_current()

    def authority_current(self):
        self.current()
        result = self.authority()
        if result is not None:
            _refuse("authority-callback-contract")
        self.current()

    def descriptor_path(self, descriptor):
        result = self.operations["_chain_descriptor_path"](descriptor)
        if type(result) is not str or result != f"/proc/self/fd/{descriptor}":
            _refuse("descriptor-path-contract")
        self.current()
        return result


class _Lease:
    """Borrow a real entered lease; own only its no-follow parent chain."""

    def __init__(self, admission, kind, *, expected_fd=None):
        self.admission, self.kind = admission, kind
        self.parent = None
        self.path = admission.paths[kind.upper() + "_OWNER_LOCK"]
        self.context = admission.contexts["_" + kind.upper() + "_OWNER_FD"]
        self.depth = admission.contexts["_CORPUS_OWNER_DEPTH"] if kind == "corpus" else None
        self.fd = self.context.get()
        if type(self.fd) is not int or self.fd < 0 \
                or expected_fd is not None and (type(expected_fd) is not int or self.fd != expected_fd) \
                or self.depth is not None and (type(self.depth.get()) is not int or self.depth.get() <= 0):
            _refuse("entered-" + kind + "-scope-required")
        observed = os.fstat(self.fd)
        if not stat.S_ISREG(observed.st_mode) or observed.st_uid != os.geteuid() \
                or stat.S_IMODE(observed.st_mode) != 0o600 or observed.st_nlink != 1:
            _refuse("entered-" + kind + "-descriptor-contract")
        self.identity = source._generation(observed)
        try:
            self.parent = source._DirectoryChain(admission.native_owner, os.path.dirname(self.path))
            self.current()
        except BaseException:
            _cleanup(self)
            raise

    def current(self):
        self.admission.current()
        if self.parent is None or self.context.get() != self.fd \
                or type(self.context.get()) is not int \
                or self.depth is not None and (type(self.depth.get()) is not int or self.depth.get() <= 0):
            _refuse("entered-" + self.kind + "-scope-changed")
        self.parent.current()
        named = os.stat(os.path.basename(self.path), dir_fd=self.parent.fd, follow_symlinks=False)
        if source._generation(named) != self.identity \
                or source._generation(os.fstat(self.fd)) != self.identity:
            _refuse("entered-" + self.kind + "-descriptor-changed")
        self.parent.current()
        self.admission.current()

    def close(self):
        if self.parent is not None:
            self.parent.close()
            self.parent = None


class _File:
    """Held ancestry and streamed artifact digest, without copying the ELF."""

    def __init__(self, admission, path, expected, ceiling, *, executable=False):
        self.admission, self.path = admission, path
        self.parent = None
        self.fd = None
        self.raw = None
        try:
            self.parent = source._DirectoryChain(admission.native_owner, os.path.dirname(path))
            self.name = os.path.basename(path)
            self.fd = os.open(self.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                              dir_fd=self.parent.fd)
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
                    or info.st_mode & 0o022 or info.st_nlink != 1 \
                    or not 0 < info.st_size <= ceiling \
                    or executable and not info.st_mode & 0o111:
                _refuse("unsafe-installed-artifact")
            self.identity = source._generation(info)
            if executable and os.pread(self.fd, 4, 0) != b"\x7fELF":
                _refuse("installed-executable-format")
            digest = hashlib.sha256()
            offset, chunks = 0, []
            while offset < info.st_size:
                block = os.pread(self.fd, min(1_048_576, info.st_size - offset), offset)
                if not block:
                    _refuse("installed-artifact-short-read")
                digest.update(block)
                if not executable:
                    chunks.append(block)
                offset += len(block)
            if os.pread(self.fd, 1, offset) or digest.hexdigest() != expected:
                _refuse("installed-artifact-digest")
            self.sha256 = digest.hexdigest()
            if not executable:
                self.raw = b"".join(chunks)
            self.current()
        except BaseException:
            _cleanup(self)
            raise

    def current(self):
        if self.fd is None or self.parent is None:
            _refuse("closed-installed-artifact")
        self.admission.current()
        self.parent.current()
        named = os.stat(self.name, dir_fd=self.parent.fd, follow_symlinks=False)
        if source._generation(named) != self.identity \
                or source._generation(os.fstat(self.fd)) != self.identity:
            _refuse("installed-artifact-generation-changed")
        self.parent.current()
        self.admission.current()

    def observation(self):
        return {"path": self.path, "sha256": self.sha256, "identity": self.identity}

    def close(self):
        descriptor, self.fd = self.fd, None
        try:
            _close_fd(descriptor)
        finally:
            if self.parent is not None:
                self.parent.close()
                self.parent = None


class _Boundary:
    def __init__(self, admission):
        self.admission, self.held = admission, []
        self.closed = False
        try:
            self.corpus = self._directory(admission.paths["CORPUS"])
            self.state = self._directory(admission.paths["STATE"])
            self.root = self._directory(os.path.dirname(os.path.dirname(admission.paths["GBRAIN"])))
            self.pin = self._file("GBRAIN_PIN", "gbrain_pin_sha256")
            self.pin_receipt = self._file("GBRAIN_PIN_RECEIPT", "gbrain_pin_receipt_sha256")
            self.runtime_receipt = self._file("GBRAIN_RUNTIME_RECEIPT", "gbrain_runtime_receipt_sha256")
            self.executable = self._file("GBRAIN", "gbrain_executable_sha256", executable=True)
            self.pin_fields = self._pin()
            expected_pin_receipt = "\n".join((
                "managed-by=khephri.sia", "kind=gbrain-pin", "path=" + self.pin.path,
                "sha256=" + self.pin.sha256, ""))
            if self.pin_receipt.raw != expected_pin_receipt.encode("utf-8"):
                _refuse("installed-pin-receipt")
            expected_runtime = "\n".join((
                "managed-by=khephri.sia", "commit=" + self.pin_fields["commit"],
                "version=" + self.pin_fields["version"],
                "bun_lock_sha256=" + self.pin_fields["bun_lock_sha256"],
                "overlay_sha256=" + self.pin_fields["overlay_sha256"],
                "overlay_tree_oid=" + self.pin_fields["overlay_tree_oid"],
                "binary_sha256=" + self.executable.sha256, ""))
            if self.runtime_receipt.raw != expected_runtime.encode("utf-8"):
                _refuse("installed-overlay-runtime-receipt")
            self._documents()
            self.current()
        except BaseException:
            _cleanup(self)
            raise

    def _directory(self, path):
        value = source._DirectoryChain(self.admission.native_owner, path)
        self.held.append(value)
        return value

    def _file(self, path_key, digest_key, *, executable=False):
        value = _File(self.admission, self.admission.paths[path_key],
                      self.admission.expectations[digest_key],
                      self.admission.limits["max_executable_bytes" if executable else "max_metadata_bytes"],
                      executable=executable)
        self.held.append(value)
        return value

    def _pin(self):
        text = self.pin.raw.decode("utf-8", "strict")
        values = {}
        for line in text.splitlines():
            if not line or line.startswith("#"):
                continue
            if line.count("=") != 1:
                _refuse("installed-pin-fields")
            key, value = line.split("=", 1)
            if key not in _PIN_KEYS or key in values or not value:
                _refuse("installed-pin-fields")
            values[key] = value
        self.admission._pin_fields(values)
        if values != {key: self.admission.expectations[key] for key in _PIN_KEYS}:
            _refuse("installed-pin-expectation-join")
        return values

    def _documents(self):
        admission = self.admission
        self.metadata = {
            "pin": self.pin.raw.decode("utf-8", "strict"),
            "pin_receipt": self.pin_receipt.raw.decode("utf-8", "strict"),
            "runtime_receipt": self.runtime_receipt.raw.decode("utf-8", "strict"),
        }
        self.binding = {
            "schema": "sia-installed-overlay-engine-binding-v1",
            "status": "bound-installed-artifacts",
            "source_id": admission.source_id,
            "expected_expectations_sha256": admission.expected,
            "pin_fields": self.pin_fields,
            "artifacts": {"pin": self.pin.observation(),
                          "pin_receipt": self.pin_receipt.observation(),
                          "runtime_receipt": self.runtime_receipt.observation(),
                          "executable": self.executable.observation()},
            "corpus": {"path": admission.paths["CORPUS"],
                       "identity": source._directory_generation(os.fstat(self.corpus.fd))},
            "non_claims": list(NON_CLAIMS),
        }
        self.binding["binding_sha256"] = hashlib.sha256(admission.wire(self.binding)).hexdigest()
        # Admit the exact initial compound representation before the engine
        # owner is acquired, not only when a later read copies its documents.
        admission.wire({"expectations": admission.expectations,
                        "binding": self.binding, "metadata": self.metadata,
                        "requests": [], "returned": []})
        self.binding_pin, self.metadata_pin = _plain_pin(self.binding), _plain_pin(self.metadata)

    def current(self):
        if self.closed:
            _refuse("closed-installed-boundary")
        self.admission.current()
        for held in self.held:
            held.current()
        if not _plain_same(self.binding, self.binding_pin) \
                or not _plain_same(self.metadata, self.metadata_pin):
            _refuse("installed-boundary-documents-changed")
        self.admission.current()

    def close(self):
        self.closed = True
        held, self.held = self.held, []
        failure = None
        for value in reversed(held):
            try:
                value.close()
            except BaseException as exc:
                if failure is None:
                    failure = exc
        if failure is not None and sys.exc_info()[0] is None:
            raise failure


class _RequestFile:
    """A known regular scratch leaf selected through a held STATE child."""

    def __init__(self, admission, state, payload):
        self.admission, self.state, self.payload = admission, state, payload
        self.directory_fd = self.fd = None
        self.name = None
        self.directory_identity = self.identity = None
        self.leaf = "request.json"
        try:
            state.current()
            # Select a scratch basename before effects so the complete derived
            # path is admitted first. A collision refuses; it does not rebase
            # any retained request or select another installed runtime.
            candidate = next(tempfile._get_candidate_names())
            if type(candidate) is not str or re.fullmatch(r"[a-z0-9_]+", candidate) is None:
                _refuse("request-directory-name")
            self.name = "sia-installed-projection-" + candidate
            root = os.path.join(admission.paths["STATE"], self.name)
            source._canonical_path(admission.native_owner, root)
            source._canonical_path(admission.native_owner, os.path.join(root, self.leaf))
            admission.current()
            state.current()
            os.mkdir(self.name, 0o700, dir_fd=state.fd)
            self.directory_fd = os.open(self.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                        dir_fd=state.fd)
            info = os.fstat(self.directory_fd)
            self.directory_identity = source._directory_identity(info)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() \
                    or stat.S_IMODE(info.st_mode) != 0o700:
                _refuse("request-directory-contract")
            self.fd = os.open(self.leaf, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                              0o600, dir_fd=self.directory_fd)
            pending = memoryview(payload)
            while pending:
                written = os.write(self.fd, pending)
                if written <= 0:
                    _refuse("request-file-short-write")
                pending = pending[written:]
            self.identity = source._generation(os.fstat(self.fd))
            self.current()
            self.path = admission.descriptor_path(self.directory_fd) + "/" + self.leaf
        except BaseException:
            _cleanup(self)
            raise

    def _directory_current(self):
        if self.directory_fd is None or self.directory_identity is None:
            _refuse("closed-request-directory")
        self.state.current()
        named = os.stat(self.name, dir_fd=self.state.fd, follow_symlinks=False)
        if source._directory_identity(named) != self.directory_identity \
                or source._directory_identity(os.fstat(self.directory_fd)) != self.directory_identity:
            _refuse("request-directory-changed")

    def current(self):
        self._directory_current()
        if self.fd is None or self.identity is None:
            _refuse("closed-request-file")
        named = os.stat(self.leaf, dir_fd=self.directory_fd, follow_symlinks=False)
        if source._generation(named) != self.identity \
                or source._generation(os.fstat(self.fd)) != self.identity \
                or not stat.S_ISREG(named.st_mode) or named.st_nlink != 1 \
                or named.st_uid != os.geteuid() or stat.S_IMODE(named.st_mode) != 0o600 \
                or named.st_size != len(self.payload):
            _refuse("request-file-generation-changed")
        offset = 0
        while offset < len(self.payload):
            block = os.pread(self.fd, min(1_048_576, len(self.payload) - offset), offset)
            if not block or block != self.payload[offset:offset + len(block)]:
                _refuse("request-file-bytes-changed")
            offset += len(block)
        if os.pread(self.fd, 1, offset):
            _refuse("request-file-bytes-changed")
        if source._generation(os.fstat(self.fd)) != self.identity:
            _refuse("request-file-generation-changed")
        self._directory_current()

    def close(self):
        # Never recurse or follow a replacement. A changed or incompletely
        # admitted scratch generation is retained rather than deleting it.
        if self.fd is None and self.directory_fd is None:
            return
        try:
            if self.identity is not None:
                try:
                    self.current()
                except _ERRORS:
                    pass
                else:
                    os.unlink(self.leaf, dir_fd=self.directory_fd)
            if self.directory_identity is not None:
                try:
                    self._directory_current()
                except _ERRORS:
                    pass
                else:
                    # A still-named empty directory must actually be removed;
                    # do not report successful cleanup when rmdir itself fails.
                    # Nonempty/changed scratch is retained on the failure path.
                    os.rmdir(self.name, dir_fd=self.state.fd)
        finally:
            descriptor, self.fd = self.fd, None
            directory, self.directory_fd = self.directory_fd, None
            self.identity = self.directory_identity = None
            try:
                _close_fd(descriptor)
            finally:
                _close_fd(directory)


class _Engine:
    def __init__(self, admission, corpus_lease, engine_lease, boundary):
        self.admission, self.corpus_lease = admission, corpus_lease
        self.engine_lease, self.boundary = engine_lease, boundary
        self.alive = True
        self.get_invoked = False
        self.returns = []
        self.requests = []
        self.active_request = None
        self.metadata, self.metadata_pin = boundary.metadata, boundary.metadata_pin
        self.binding, self.binding_pin = boundary.binding, boundary.binding_pin
        self._budget()
        self.current()

    def _tails(self):
        self.admission.final_current()
        if not _plain_same(self.binding, self.binding_pin) \
                or not _plain_same(self.metadata, self.metadata_pin) \
                or any(not _plain_same(value, pin) for value, pin in self.returns) \
                or any(not _plain_same(value, pin) for value, pin in self.requests):
            _refuse("retained-engine-observation-changed")

    def _current(self, *, engine=True):
        if not self.alive:
            _refuse("retired-installed-engine")
        self._tails()
        self.corpus_lease.current()
        if engine:
            self.engine_lease.current()
        self.boundary.current()
        if self.active_request is not None:
            self.active_request.current()
        self.admission.authority_current()
        self.corpus_lease.current()
        if engine:
            self.engine_lease.current()
        self.boundary.current()
        if self.active_request is not None:
            self.active_request.current()
        self._tails()

    def _retire(self):
        self.alive = False
        request, self.active_request = self.active_request, None
        failure = None
        for resource in (request, self.boundary):
            if resource is not None:
                try:
                    resource.close()
                except BaseException as exc:
                    if failure is None:
                        failure = exc
        if failure is not None and sys.exc_info()[0] is None:
            raise failure

    def current(self):
        try:
            self._current()
        except _ERRORS as exc:
            self._retire()
            if self.get_invoked:
                raise _get_refusal(exc, "installed-engine-currentness") from exc
            if isinstance(exc, InstalledEngineRefusal):
                raise
            raise InstalledEngineRefusal("installed-engine-currentness", upstream=exc) from exc
        except BaseException:
            self._retire()
            raise

    def _budget(self, *, prospective_returns=None, prospective_requests=None, **values):
        self.admission.wire({
            "expectations": self.admission.expectations,
            "binding": self.binding,
            "metadata": self.metadata,
            "requests": ([value for value, _pin in self.requests]
                         if prospective_requests is None else prospective_requests),
            "returned": ([value for value, _pin in self.returns]
                         if prospective_returns is None else prospective_returns),
            **values,
        })

    def _copy(self, value):
        self._budget(prospective_returns=[
            *(returned for returned, _pin in self.returns), value, value])
        pin = _plain_pin(value)
        detached = copy.deepcopy(value)
        if not _plain_same(value, pin) or not _plain_same(detached, pin):
            _refuse("engine-result-copy-changed")
        self.returns.extend(((value, pin), (detached, pin)))
        self.current()
        return detached

    def read(self):
        try:
            self.current()
            return self._copy(self.binding)
        except _ERRORS as exc:
            self._retire()
            if isinstance(exc, InstalledEngineRefusal):
                raise
            raise InstalledEngineRefusal("installed-engine-read", upstream=exc) from exc
        except BaseException:
            self._retire()
            raise

    def _environment(self):
        paths = self.admission.paths
        home = paths["HOME"]
        return {
            "HOME": home, "GBRAIN_HOME": paths["SHARE"],
            # Fix the brain axis as well as the source axis. The resolver's
            # environment tier precedes ancestor mounts, and its .env loader
            # cannot replace an existing key. Host backend configuration is
            # still trusted; ordinary GET retains migrations/bookkeeping.
            "GBRAIN_BRAIN_ID": "host",
            "PATH": paths["BUN_DIR"] + ":" + os.defpath,
            "TMPDIR": paths["STATE"], "BUN_OPTIONS": "--no-env-file",
            "DO_NOT_TRACK": "1", "NO_COLOR": "1",
            "GBRAIN_SKIP_STARTUP_HOOKS": "1", "GBRAIN_SYNC_NO_DELEGATE": "1",
            "GBRAIN_SELF_UPGRADE_MODE": "off", "GBRAIN_NO_BANNER": "1",
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC",
            "XDG_CONFIG_HOME": os.path.join(home, ".config"),
            "XDG_DATA_HOME": os.path.join(home, ".local", "share"),
            "XDG_CACHE_HOME": os.path.join(home, ".cache"),
            "XDG_STATE_HOME": os.path.join(home, ".local", "state"),
        }

    def _timeout(self, timeout):
        if type(timeout) is not int \
                or not 0 < timeout <= self.admission.capacities["MAX_JSON_SAFE_INTEGER"]:
            _refuse("explicit-process-timeout")

    def _run_installed_gbrain(self, arguments, operation, timeout, request_sha256, *, subject=None):
        self._timeout(timeout)
        get_mode = operation == "get"
        if get_mode:
            if type(subject) is not str or not 0 < len(subject) <= MAX_GET_SUBJECT_BYTES \
                    or _GET_SUBJECT.fullmatch(subject) is None \
                    or not _digest(request_sha256) \
                    or arguments != ["get", subject, "--source", self.admission.source_id]:
                _refuse("get-command-contract")
        elif subject is not None:
            _refuse("unexpected-get-subject")
        # Keep the held executable visible to the unchanged argv coverage gate.
        GBRAIN = self.admission.descriptor_path(self.boundary.executable.fd)
        cwd = self.admission.descriptor_path(self.boundary.corpus.fd)
        descriptors = (self.boundary.executable.fd, self.boundary.corpus.fd,
                       self.corpus_lease.fd, self.engine_lease.fd)
        if self.active_request is not None:
            descriptors += (self.active_request.directory_fd, self.active_request.fd)
        self._budget(command=[GBRAIN] + arguments, environment=self._environment())
        self.current()
        result = self.admission.operations["_run_bounded_text_process"](
            [GBRAIN] + arguments, env=self._environment(), timeout=timeout, cwd=cwd,
            pass_fds=descriptors, label="installed engine " + operation,
            output_limit=self.admission.limits["max_output_bytes"])
        # Snapshot the returned plain producer fields before any authority
        # callback can alter its mutable CompletedProcess wrapper.
        returncode, stdout_text, stderr_text = result.returncode, result.stdout, result.stderr
        if type(returncode) is not int or returncode != 0 \
                or type(stdout_text) is not str or type(stderr_text) is not str:
            _refuse("installed-engine-process")
        ceiling = self.admission.limits["max_output_bytes"]
        if len(stdout_text) > ceiling or len(stderr_text) > ceiling:
            _refuse("installed-engine-output-capacity")
        stdout, stderr = stdout_text.encode("utf-8", "strict"), stderr_text.encode("utf-8", "strict")
        if len(stdout) + len(stderr) > ceiling:
            _refuse("installed-engine-output-capacity")
        if operation == "--version" and (
                stderr_text != "" or stdout_text != "gbrain " + self.boundary.pin_fields["version"] + "\n"):
            _refuse("installed-engine-version")
        value = {
            "schema": ("sia-installed-overlay-engine-get-transport-v1" if get_mode
                       else "sia-installed-overlay-engine-transport-v1"),
            "status": ("captured-unadmitted-get" if get_mode else
                       "observed-version-only" if operation == "--version" else
                       "captured-unadmitted-projection"),
            "operation": operation, "source_id": self.admission.source_id,
            "binding_sha256": self.binding["binding_sha256"],
            "expected_expectations_sha256": self.admission.expected,
            "request_sha256": request_sha256, "returncode": returncode,
            "timeout": timeout, "stdout": stdout_text, "stderr": stderr_text,
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
            "non_claims": list(GET_NON_CLAIMS if get_mode else NON_CLAIMS),
        }
        if get_mode:
            value["subject"] = subject
        value["transport_sha256"] = hashlib.sha256(self.admission.wire(value)).hexdigest()
        self.current()
        return self._copy(value)

    def version(self, *, timeout):
        try:
            self.current()
            return self._run_installed_gbrain(arguments=["--version"], operation="--version",
                             timeout=timeout, request_sha256=None)
        except _ERRORS as exc:
            self._retire()
            if isinstance(exc, InstalledEngineRefusal):
                raise
            raise InstalledEngineRefusal("installed-engine-version", upstream=exc) from exc
        except BaseException:
            self._retire()
            raise

    def get(self, *, subject, timeout):
        """Capture one ordinary CLI GET, never admit its source or rendition.

        The source and argv are fixed by this method. GET allocates no
        projection request file and has no migration/bookkeeping suppression
        flag. The request pin binds its exact canonical native envelope.
        """
        try:
            # Select ordinary-GET refusal semantics before any fallible
            # request work; keep them for this handle's later current/exits.
            self.get_invoked = True
            self.current()
            self._timeout(timeout)
            # Reject oversized or foreign native values before regex work,
            # request serialization, hashing, command copies or execution.
            if type(subject) is not str or not 0 < len(subject) <= MAX_GET_SUBJECT_BYTES \
                    or _GET_SUBJECT.fullmatch(subject) is None:
                _refuse("get-subject-contract")
            request = {"operation": "get", "source_id": self.admission.source_id,
                       "subject": subject, "timeout": timeout}
            request_pin = _plain_pin(request)
            source._json_size(
                self.admission.native_owner, request,
                self.admission.limits["max_request_bytes"], ascii_only=True)
            # Account for both the retained request and its prospective
            # canonical wire image before allocating that wire image.
            self._budget(prospective_requests=[
                *(retained for retained, _pin in self.requests), request],
                get_request_wire=request)
            request_raw = self.admission.wire(request)
            if not _plain_same(request, request_pin):
                _refuse("get-request-changed")
            if len(request_raw) > self.admission.limits["max_request_bytes"]:
                _refuse("get-request-capacity")
            request_sha256 = hashlib.sha256(request_raw).hexdigest()
            del request_raw
            self.requests.append((request, request_pin))
            self.current()
            return self._run_installed_gbrain(
                arguments=["get", subject, "--source", self.admission.source_id],
                operation="get", timeout=timeout, request_sha256=request_sha256,
                subject=subject)
        except _ERRORS as exc:
            self._retire()
            if isinstance(exc, InstalledEngineGetRefusal):
                raise
            raise _get_refusal(exc, "installed-engine-get") from exc
        except BaseException:
            self._retire()
            raise

    def project(self, *, operation, request_utf8, expected_request_sha256, timeout):
        try:
            self.current()
            self._timeout(timeout)
            if type(operation) is not str or operation != PROJECTION_OPERATION:
                _refuse("projection-operation-not-allowlisted")
            if type(request_utf8) is not bytes or not request_utf8 \
                    or len(request_utf8) > self.admission.limits["max_request_bytes"] \
                    or not _digest(expected_request_sha256):
                _refuse("projection-request-capacity-or-pin")
            if hashlib.sha256(request_utf8).hexdigest() != expected_request_sha256:
                _refuse("projection-request-pin")
            text = request_utf8.decode("utf-8", "strict")
            request = self.admission.operations["_strict_json_loads"](text)
            if type(request) is not dict or request.get("source_id") != self.admission.source_id \
                    or type(request.get("source_id")) is not str:
                _refuse("projection-request-source")
            premise = {"request_utf8_text": text, "parsed_request": request,
                       "expected_request_sha256": expected_request_sha256,
                       "operation": operation, "timeout": timeout}
            self._budget(prospective_requests=[
                *(retained for retained, _pin in self.requests), premise])
            self.requests.append((premise, _plain_pin(premise)))
            self.current()
            self.active_request = _RequestFile(self.admission, self.boundary.state, request_utf8)
            result = self._run_installed_gbrain(arguments=[
                "call", "--no-migrate", "--source", self.admission.source_id,
                "--params-file", self.active_request.path, operation,
            ], operation=operation, timeout=timeout,
                request_sha256=expected_request_sha256)
            self.current()
            self.active_request.close()
            self.active_request = None
            self.current()
            return result
        except _ERRORS as exc:
            self._retire()
            if isinstance(exc, InstalledEngineRefusal):
                raise
            raise InstalledEngineRefusal("installed-engine-projection", upstream=exc) from exc
        except BaseException:
            self._retire()
            raise


@contextlib.contextmanager
def hold_overlay_engine(owner, *, expectations, expected_expectations_sha256, authority_current):
    """Admit explicit installed-overlay authority under an entered corpus scope.

    The opaque handle exposes read/current/version/get/project, never
    executable descriptors or arbitrary argv. Project allows only
    get_page_render_projection; get is a separate ordinary source-qualified
    GET and does not promise no migration or retrieval bookkeeping.
    Exceptions from the caller's body remain the original exceptions. A failed
    handle retires; retry uses a fresh admitted context, never automatic repair.
    """
    admission = corpus = engine = boundary = held = None
    entered_body = returned_body = False
    try:
        try:
            admission = _Admission(owner, expectations, expected_expectations_sha256, authority_current)
            corpus = _Lease(admission, "corpus")
            admission.authority_current()
        except InstalledEngineRefusal:
            raise
        except _ERRORS as exc:
            raise InstalledEngineRefusal("installed-engine-entry", upstream=exc) from exc
        with _preserve_exception(admission.operations["corpus_owner"]()) as corpus_fd:
            if type(corpus_fd) is not int or corpus_fd != corpus.fd:
                _refuse("entered-corpus-return-binding")
            corpus.current()
            boundary = _Boundary(admission)
            admission.authority_current()
            corpus.current()
            boundary.current()
            with _preserve_exception(admission.operations["gbrain_owner"]()) as engine_fd:
                engine = _Lease(admission, "gbrain", expected_fd=engine_fd)
                held = _Engine(admission, corpus, engine, boundary)
                # Keep caller exceptions outside any domain conversion.
                entered_body = True
                yield held
                returned_body = True
                held.current()
            # The engine owner's normal-exit callback has run. Source/corpus
            # and installed artifacts remain held; do not reuse its closed FD.
            held._current(engine=False)
            engine.close()
            engine = None
            held._tails()
        # The nested corpus exit has run; the caller's original lease remains.
        corpus.current()
        boundary.current()
        admission.authority_current()
        corpus.current()
        boundary.current()
        held._tails()
    except InstalledEngineRefusal as exc:
        if held is not None and held.get_invoked \
                and (not entered_body or returned_body):
            raise _get_refusal(exc, "installed-engine-boundary") from exc
        raise
    except _ERRORS as exc:
        if entered_body and not returned_body:
            raise
        if held is not None and held.get_invoked:
            raise _get_refusal(exc, "installed-engine-boundary") from exc
        raise InstalledEngineRefusal("installed-engine-boundary", upstream=exc) from exc
    finally:
        # All resources here are ours except the two borrowed lease FDs,
        # whose actual owner contexts close them. Never close caller leases.
        failure = None
        for resource in (held, boundary, engine, corpus):
            if resource is not None:
                try:
                    resource._retire() if resource is held else resource.close()
                except BaseException as exc:
                    if failure is None:
                        failure = exc
        if failure is not None and sys.exc_info()[0] is None:
            if held is not None and held.get_invoked and isinstance(failure, _ERRORS):
                raise _get_refusal(failure, "installed-engine-cleanup") from failure
            raise failure
    # Callback-free comparisons after owned descriptor cleanup. No path or
    # lease is reacquired here and no defensive copy follows the final check.
    try:
        admission.final_current()
        held._tails()
    except _ERRORS as exc:
        if held.get_invoked:
            raise _get_refusal(exc, "installed-engine-final-currentness") from exc
        raise
