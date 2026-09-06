"""Execute one pinned private raw-vector baseline split, without scoring.

The source selection, private model, compiled build and exact prepared chunk
roster are controlling. There is no resident-index, hybrid-query or ambient
model fallback. Partial private artifacts survive refusal; baseline.json is
published only after complete admission and final generation checks.
"""

import contextlib
import copy
import hashlib
import json
import math
import os
import re
import stat
import tarfile

import siacognitiveselect as selection_module
import sialib
import siaqueue
import siavector
import siavectoradmit as raw_admission
import siavectormodel
import siavectorprepare as preparation_admission
import siavectorrun as runner


MAX_ARCHIVE_BYTES = siavector.MAX_EXECUTABLE_BYTES
MAX_ARTIFACT_BYTES = sialib.MAX_STATE_JSON_BYTES
MAX_MEMBERS = 100_000  # The existing private_index_snapshot member ceiling.
NON_CLAIMS = [
    "This is a bound raw-vector observation, not a cognitive win or a significance result.",
    "No recall, MRR, target denominator, or slug-match credit is defined by this execution artifact.",
    "Eligibility support and answer target sequences remain distinct; a separate frozen retrieval-target protocol is required before scoring.",
    "A pinned parameter freeze declares calibration-only tuning; it does not independently prove historical tuning chronology.",
    "Code-file identities do not attest loaded Python heap/interpreter behavior or the complete third-party runtime.",
    "The stopped private archive and owned model generations do not attest a resident index or complete machine history.",
    "Source origins are bound from selected pages, not inferred from raw scores or promoted by signed-row provenance.",
    "All retained capture, selection, build, preparer, model and adapter nonclaims remain controlling.",
]
FREEZE_NON_CLAIMS = [
    "This externally pinned manifest declares calibration-only tuning; it does not independently prove historical tuning chronology.",
    "Frozen parameters and identities do not establish retrieval relevance, significance, or a cognitive win.",
]
_DIGEST = re.compile(r"[0-9a-f]{64}")


class BaselineRefusal(RuntimeError):
    """A private baseline observation was not admitted or published."""


def _fail(reason):
    raise BaselineRefusal("cognitive baseline refused: " + reason)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _bounded(value, maximum=MAX_ARTIFACT_BYTES):
    """Bound structure before copies/serialization, retaining finite wire floats."""
    active, used = set(), 0

    def visit(item, depth):
        nonlocal used
        used += 1
        if depth > 64 or used > maximum:
            _fail("JSON structure exceeds its ceiling")
        kind = type(item)
        if kind is str:
            if len(item) > maximum - used:
                _fail("JSON text exceeds its ceiling")
            used += len(item.encode("utf-8", "strict"))
        elif kind is int:
            if not -raw_admission.MAX_SAFE_INTEGER <= item <= raw_admission.MAX_SAFE_INTEGER:
                _fail("JSON integer exceeds its exact range")
        elif kind is float:
            if not math.isfinite(item):
                _fail("nonfinite JSON value")
        elif kind is bool or item is None:
            pass
        elif kind in (dict, list):
            if id(item) in active or len(item) > maximum - used:
                _fail("cyclic or excessive JSON container")
            active.add(id(item))
            try:
                if kind is dict:
                    for key, child in item.items():
                        if type(key) is not str:
                            _fail("JSON object key is not text")
                        visit(key, depth + 1)
                        visit(child, depth + 1)
                else:
                    for child in item:
                        visit(child, depth + 1)
            finally:
                active.remove(id(item))
        else:
            _fail("unsupported JSON value")
        if used > maximum:
            _fail("JSON structure exceeds its ceiling")

    visit(value, 0)


def _canonical(value, maximum=MAX_ARTIFACT_BYTES):
    _bounded(value, maximum)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) > maximum:
        _fail("serialized JSON exceeds its ceiling")
    return raw


def _same(left, right):
    return _canonical(left) == _canonical(right)


def _keys(value, names, label):
    if type(value) is not dict or set(value) != set(names):
        _fail(label + " fields are invalid")


def _digest(value):
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _nonclaims(value):
    if type(value) is not list or not value or any(type(item) is not str or not item for item in value):
        _fail("upstream nonclaims are missing")


def _path(value):
    # Reuse the owned model lane's no-resident, canonical absolute path rule.
    if type(value) is not str or len(value) > sialib.MAX_CONFIG_BYTES:
        _fail("artifact path exceeds its text ceiling")
    siavectormodel._path(value)
    if value == "/":
        _fail("filesystem root is not a private artifact operand")
    return value


def _generation(info):
    return siavectormodel._generation(info)


class _Directory:
    def __init__(self, path, *, private=True):
        self.path = _path(path)
        self.fd = siavectormodel._open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            info = os.fstat(self.fd)
            if info.st_uid != os.geteuid() or info.st_mode & (0o077 if private else 0o022):
                _fail("directory is not an owned private generation")
            self.identity = siavector._directory_identity(info)
        except BaseException:
            os.close(self.fd)
            raise

    def current(self):
        if siavector._directory_identity(os.fstat(self.fd)) != self.identity:
            _fail("directory descriptor generation changed")
        other = siavectormodel._open(self.path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            if siavector._directory_identity(os.fstat(other)) != self.identity:
                _fail("directory named generation changed")
        finally:
            os.close(other)

    def close(self):
        os.close(self.fd)


class _FilePin:
    """Stream/hash a source without retaining another executable-sized memfd."""
    def __init__(self, path, expected, *, executable=False):
        self.path = _path(path)
        self.fd = siavectormodel._open(path, os.O_RDONLY)
        try:
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
                    or info.st_nlink != 1 or info.st_mode & 0o022 \
                    or info.st_size > siavector.MAX_EXECUTABLE_BYTES \
                    or executable and (not info.st_mode & 0o111 or os.pread(self.fd, 4, 0) != b"\x7fELF"):
                _fail("artifact source is not a bounded owned ordinary file")
            self.generation = _generation(info)
            digest, size = hashlib.sha256(), 0
            while block := os.read(self.fd, sialib.MAX_CONFIG_BYTES):
                size += len(block)
                if size > siavector.MAX_EXECUTABLE_BYTES:
                    _fail("artifact source grew past its ceiling")
                digest.update(block)
            if size != info.st_size or digest.hexdigest() != expected:
                _fail("artifact source digest mismatch")
            self.current()
        except BaseException:
            os.close(self.fd)
            raise

    def current(self):
        if _generation(os.fstat(self.fd)) != self.generation:
            _fail("artifact source generation changed")
        other = siavectormodel._open(self.path, os.O_RDONLY)
        try:
            if _generation(os.fstat(other)) != self.generation:
                _fail("artifact named generation changed")
        finally:
            os.close(other)

    def close(self):
        os.close(self.fd)


def _code_roster(directory):
    entries = list(os.scandir(directory.fd))
    if len(entries) > siavectormodel.MAX_ENTRIES:
        _fail("code source inventory exceeds its ceiling")
    names = []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        info = entry.stat(follow_symlinks=False)
        if entry.name == "__pycache__" and stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode):
            _fail("code source inventory contains a nonordinary source")
        names.append(entry.name)
    return sorted(names)


def _code_sources(expected, stack):
    directory = _Directory(os.path.dirname(os.path.abspath(__file__)), private=False)
    stack.callback(directory.close)
    roster = _code_roster(directory)
    if roster != sorted(expected["files"]):
        _fail("code source inventory is incomplete or changed")
    sealed, total = [], 0
    for name in roster:
        item = stack.enter_context(siavector.sealed_file(
            os.path.join(directory.path, name), expected["files"][name], max_bytes=MAX_ARTIFACT_BYTES))
        total += item.size
        if total > MAX_ARTIFACT_BYTES:
            _fail("code source inventory exceeds its aggregate ceiling")
        sealed.append(item)

    def current():
        directory.current()
        if _code_roster(directory) != roster:
            _fail("code source roster changed")
        for item in sealed:
            item.assert_current()
    current()
    return current


def _runtime(value):
    if type(value) is not list or not value or len(value) > siavectormodel.MAX_ENTRIES:
        _fail("explicit shared runtime is required")
    destinations = set()
    for row in value:
        _keys(row, {"source", "destination", "sha256"}, "runtime leaf")
        _path(row["source"])
        destination = _path(row["destination"])
        if destination in destinations or not _digest(row["sha256"]) \
                or not (destination == "/usr/bin/python3" or destination.startswith("/usr/lib/")) \
                or any(part in ("site-packages", "dri", "cuda", "vulkan") for part in destination.split("/")):
            _fail("runtime leaf declaration is invalid")
        destinations.add(destination)
    if "/usr/bin/python3" not in destinations:
        _fail("runtime has no pinned Python executable")


def _preflight(kw):
    # Check bounded structure before any copy, hash, source open or output write.
    for key in ("capture", "selection_policy", "selection", "preparer", "adapter", "embedding",
                "model_expectations", "shared_runtime", "code_expectations", "parameter_freeze"):
        _bounded(kw[key])
    for key in ("expected_capture_sha256", "expected_policy_sha256", "expected_selection_sha256"):
        if not _digest(kw[key]):
            _fail("external source pins are required")
    if type(kw["split"]) is not str or kw["split"] not in ("calibration", "heldout"):
        _fail("one explicit query split is required")
    if type(kw["timeout"]) not in (int, float) or not math.isfinite(kw["timeout"]) \
            or not 0 < kw["timeout"] <= 1800:
        _fail("timeout is invalid")
    for key in ("scratch_parent", "output_directory"):
        _path(kw[key])
    for role in ("preparer", "adapter"):
        build = kw[role]
        _keys(build, {"executable", "expected", "build_receipt", "build_receipt_sha256"}, role)
        _path(build["executable"])
        _path(build["build_receipt"])
        runner._expectation_values(build["expected"])
        if not _digest(build["build_receipt_sha256"]):
            _fail("build receipt external pin is invalid")
    model = kw["model_expectations"]
    runner._bound_model_inputs(model, kw["shared_runtime"])
    for key in ("package_root", "model_root"):
        _path(model[key])
    for key in ("package_sha256", "manifest_sha256", "release_archive_sha256"):
        if not _digest(model[key]):
            _fail("model external pin is invalid")
    if type(model["model_name"]) is not str or siavectormodel._MODEL.fullmatch(model["model_name"]) is None \
            or type(model["release_version"]) is not str or not model["release_version"]:
        _fail("model name or release is invalid")
    _runtime(kw["shared_runtime"])
    code = kw["code_expectations"]
    _keys(code, {"schema", "files"}, "code inventory")
    if code["schema"] != "sia-bin-source-inventory-v1" or type(code["files"]) is not dict \
            or not code["files"] or len(code["files"]) > siavectormodel.MAX_ENTRIES \
            or any(not name or name.startswith(".") or "/" in name or "\\" in name
                   or not _digest(digest) for name, digest in code["files"].items()):
        _fail("code inventory contract is invalid")
    selected = selection_module.admit_selection(
        kw["selection"], capture=kw["capture"], policy=kw["selection_policy"],
        expected_capture_sha256=kw["expected_capture_sha256"], expected_policy_sha256=kw["expected_policy_sha256"])
    if selected["selection_sha256"] != kw["expected_selection_sha256"]:
        _fail("external selection pin mismatch")
    queries = [{"id": row["id"], "text": row["text"]}
               for row in selected["queries"] if row["split"] == kw["split"]]
    if not queries:
        _fail("requested split has no queries; rebalancing is forbidden")
    raw_admission.admit_request(_query_request(kw, "query", queries, {
        "logical_sha256": "0" * 64, "catalog_sha256": "0" * 64}))
    embedding = kw["embedding"]
    if embedding["model"] != "ollama:" + model["model_name"] \
            or embedding["endpoint"] != "http://127.0.0.1:11434/v1":
        _fail("embedding does not identify the owned private model")
    request = preparation_admission.admit_request({
        "v": 1, "operation": "prepare_index", "source": "sia",
        "dataset_sha256": selected["selection_sha256"], "pages_sha256": selected["pages_sha256"],
        "embedding": embedding, "output": {"parent_fd": None}, "pages": selected["pages"]})
    contract = {
        "schema": "sia-cognitive-baseline-contract-v1", "capture_sha256": kw["expected_capture_sha256"],
        "policy_sha256": kw["expected_policy_sha256"], "selection_sha256": kw["expected_selection_sha256"],
        "pages_sha256": selected["pages_sha256"],
        **{role: {"expected": kw[role]["expected"], "build_receipt_sha256": kw[role]["build_receipt_sha256"]}
           for role in ("preparer", "adapter")}, "embedding": embedding,
        "model": {key: value for key, value in model.items() if key not in ("package_root", "model_root")},
        "runtime": sorted(({"destination": row["destination"], "sha256": row["sha256"]}
                           for row in kw["shared_runtime"]), key=lambda row: row["destination"]),
        "code_expectations": code, "limit": kw["limit"], "timeout": kw["timeout"],
    }
    contract_sha = _sha(_canonical(contract))
    freeze = kw["parameter_freeze"]
    if kw["split"] == "calibration":
        if freeze is not None or kw["expected_parameter_freeze_sha256"] is not None:
            _fail("calibration execution does not consume a heldout freeze")
    else:
        _keys(freeze, {"schema", "capture_sha256", "policy_sha256", "selection_sha256",
                       "baseline_contract_sha256", "calibration_run_sha256", "tuning_split",
                       "parameters", "parameters_sha256", "non_claims", "freeze_sha256"}, "parameter freeze")
        if freeze["schema"] != "sia-cognitive-parameter-freeze-v1" or freeze["tuning_split"] != "calibration" \
                or type(freeze["parameters"]) is not dict or not _digest(freeze["calibration_run_sha256"]) \
                or not _same(freeze["non_claims"], FREEZE_NON_CLAIMS) \
                or freeze["parameters_sha256"] != _sha(_canonical(freeze["parameters"])) \
                or freeze["baseline_contract_sha256"] != contract_sha \
                or any(freeze[key] != contract[key] for key in (
                    "capture_sha256", "policy_sha256", "selection_sha256")):
            _fail("parameter freeze does not bind this baseline contract")
        digest = _sha(_canonical({key: value for key, value in freeze.items() if key != "freeze_sha256"}))
        if not _digest(kw["expected_parameter_freeze_sha256"]) \
                or freeze["freeze_sha256"] != digest or digest != kw["expected_parameter_freeze_sha256"]:
            _fail("external parameter freeze pin mismatch")
    return selected, queries, request, copy.deepcopy(contract), copy.deepcopy(freeze)


def _query_request(kw, operation, queries, roots):
    return {"v": 1, "lane": "raw_vector", "operation": operation,
            "queries": queries if operation == "query" else [], "limit": kw["limit"],
            "snapshot": {"fd": None, **(roots if operation == "query" else {
                "logical_sha256": None, "catalog_sha256": None})},
            "embedding": kw["embedding"], "binding": {
                "executable_sha256": kw["adapter"]["expected"]["executable_sha256"],
                "build_receipt_sha256": kw["adapter"]["build_receipt_sha256"]}}


def _model_identity(identity, expected):
    if type(identity) is not dict or any(identity.get(key) != expected[key] for key in (
            "model_name", "manifest_sha256", "package_sha256")):
        _fail("observed model identity differs from caller expectations")
    for key in ("release_version", "release_archive_sha256"):
        if key in identity and identity[key] != expected[key]:
            _fail("observed model release differs from caller expectations")


def _transport_observation(observation, request, build, model, kw):
    if type(observation) is not dict or type(observation.get("returncode")) is not int \
            or observation["returncode"] != 0 \
            or observation.get("executable_sha256") != build["expected"]["executable_sha256"] \
            or not _digest(observation.get("request_sha256")) \
            or not _digest(observation.get("stdout_sha256")):
        _fail("transport observation is not complete and build-bound")
    original_sha = _sha(_canonical(request))
    if observation.get("bound_request_sha256") != original_sha:
        _fail("transport original request binding disagrees")
    # stdout_sha256 hashes actual producer stdout, including its original JSON
    # spelling and final LF. It must never be reconstructed from parsed payload.
    served = observation.get("model_serving")
    _keys(served, {"schema", "status", "model_identity", "launch_config", "launch_config_sha256",
                   "serving_generation", "non_claims"}, "owned serving observation")
    if served["schema"] != "sia-raw-vector-served-observation-v1" or served["status"] != "observed" \
            or not _same(served["model_identity"], model) \
            or not _same(served["non_claims"], siavectormodel.NON_CLAIMS):
        _fail("owned serving envelope disagrees")
    config = served["launch_config"]
    if type(config) is not dict or config.get("schema") != "sia-raw-vector-model-launch-v1" \
            or config.get("operation") != request["operation"] \
            or not _same(config.get("embedding"), kw["embedding"]) \
            or not _same(config.get("model_identity"), model) \
            or config.get("adapter_sha256") != build["expected"]["executable_sha256"] \
            or config.get("request_sha256") != original_sha \
            or served["launch_config_sha256"] != _sha(_canonical(config)):
        _fail("owned model launch configuration disagrees")
    generation = served["serving_generation"]
    if type(generation) is not dict or generation.get("model_manifest_sha256") != model["manifest_sha256"] \
            or generation.get("execution_policy") != "ollama-cpu-only-v1":
        _fail("owned CPU serving generation disagrees")
    runtime = config.get("system_runtime")
    if type(runtime) is not list or len(runtime) != len(kw["shared_runtime"]):
        _fail("served runtime roster disagrees")
    observed = {}
    for row in runtime:
        _keys(row, {"destination", "sha256", "bytes"}, "served runtime leaf")
        if type(row["destination"]) is not str or row["destination"] in observed \
                or type(row["bytes"]) is not int or not 0 <= row["bytes"] <= siavectormodel.MAX_SEALED_BYTES:
            _fail("served runtime leaf is invalid")
        observed[row["destination"]] = row["sha256"]
    if observed != {row["destination"]: row["sha256"] for row in kw["shared_runtime"]}:
        _fail("served runtime bytes disagree with declared runtime pins")


def _preparation(value, request, kw):
    _bounded(value)
    _keys(value, {"schema", "status", "dataset_sha256", "pages_sha256", "build_receipt_sha256", "expected",
                  "model_identity", "preparation", "build_non_claims", "non_claims"}, "bound preparation")
    if value["schema"] != "sia-raw-vector-bound-preparation-v1" or value["status"] != "observed" \
            or value["dataset_sha256"] != request["dataset_sha256"] \
            or value["pages_sha256"] != request["pages_sha256"] \
            or value["build_receipt_sha256"] != kw["preparer"]["build_receipt_sha256"] \
            or not _same(value["expected"], kw["preparer"]["expected"]):
        _fail("bound preparation identities disagree")
    _nonclaims(value["build_non_claims"])
    _nonclaims(value["non_claims"])
    _model_identity(value["model_identity"], kw["model_expectations"])
    observation = value["preparation"]
    _transport_observation(observation, request, kw["preparer"], value["model_identity"], kw)
    preparation_admission.admit_response(
        observation.get("payload"), request, request_sha256=observation["request_sha256"])
    return copy.deepcopy(value)


def _observation(value, archive, preparation, queries, selected, kw):
    _bounded(value)
    _keys(value, {"schema", "status", "lane", "build_receipt_sha256", "index_archive_sha256", "expected",
                  "embedding", "config_sha256", "capture", "query", "model_identity",
                  "build_non_claims", "non_claims"}, "bound raw observation")
    config_sha = runner.configuration_sha256(kw["embedding"], kw["limit"])
    if value["schema"] != "sia-raw-vector-bound-observation-v1" or value["status"] != "observed" \
            or value["lane"] != "raw_vector" or value["index_archive_sha256"] != archive["sha256"] \
            or value["build_receipt_sha256"] != kw["adapter"]["build_receipt_sha256"] \
            or not _same(value["expected"], kw["adapter"]["expected"]) \
            or not _same(value["embedding"], kw["embedding"]) or value["config_sha256"] != config_sha \
            or not _same(value["model_identity"], preparation["model_identity"]):
        _fail("bound observation identities disagree with preparation and contract")
    _nonclaims(value["build_non_claims"])
    _nonclaims(value["non_claims"])
    _model_identity(value["model_identity"], kw["model_expectations"])
    roots = {}
    for operation in ("capture", "query"):
        observation = value[operation]
        request = _query_request(kw, operation, queries, roots)
        _transport_observation(observation, request, kw["adapter"], value["model_identity"], kw)
        if observation.get("physical_manifest_sha256") != archive["manifest_sha256"]:
            _fail("raw observation refers to a different physical archive generation")
        payload = raw_admission.admit_response(
            observation.get("payload"), request,
            executable_sha256=kw["adapter"]["expected"]["executable_sha256"],
            request_sha256=observation["request_sha256"], config_sha256=config_sha)
        if operation == "capture":
            roots = {key: payload["bindings"][key] for key in ("logical_sha256", "catalog_sha256")}
    pages = {page["slug"]: page for page in selected["pages"]}
    chunks = {slug: tuple(preparation_admission._chunk_bytes(page["text"])) for slug, page in pages.items()}
    joined = []
    for result in value["query"]["payload"]["results"]:
        labels = []
        for row in result["rows"]:
            page = pages.get(row["slug"])
            index = row["chunk_index"]
            if page is None or row["source_id"] != "sia" or row["chunk_source"] != "compiled_truth" \
                    or row["title"] != page["title"] or row["type"] != page["type"] \
                    or row["stale"] is not False or not 0 <= index < len(chunks[page["slug"]]) \
                    or row["chunk_text"].encode("utf-8") != chunks[page["slug"]][index]:
                _fail("raw row is not the exact selected prepared source chunk")
            labels.append({"slug": row["slug"], "chunk_index": index, "origin": page["origin"],
                           "page_text_sha256": page["text_sha256"],
                           "chunk_text_sha256": _sha(chunks[page["slug"]][index])})
        joined.append({"id": result["id"], "rows": labels})
    return copy.deepcopy(value), joined


def _tree(path):
    """Snapshot a stopped ordinary tree without following any member links."""
    rows, seen, total = [], set(), 0

    def visit(directory, prefix, depth):
        nonlocal total
        if depth > 64:
            _fail("private index directory depth exceeds its ceiling")
        fd = siavectormodel._open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            before = _generation(os.fstat(fd))
            for entry in sorted(os.scandir(fd), key=lambda item: item.name):
                name = prefix + entry.name
                if not entry.name or entry.name in (".", "..") or "\x00" in name \
                        or len(name.encode("utf-8")) > sialib.MAX_CONFIG_BYTES:
                    _fail("unsafe private index member name")
                info = entry.stat(follow_symlinks=False)
                if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                    _fail("private index member is not owner controlled")
                identity = (info.st_dev, info.st_ino)
                if identity in seen:
                    _fail("private index member aliases another member")
                seen.add(identity)
                if len(seen) > MAX_MEMBERS:
                    _fail("private index member count exceeds its ceiling")
                if stat.S_ISDIR(info.st_mode):
                    kind = "directory"
                elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                    kind = "file"
                    total += info.st_size
                    if total > MAX_ARCHIVE_BYTES:
                        _fail("private index exceeds archive byte ceiling")
                else:
                    _fail("private index contains a link or special member")
                rows.append({"path": name, "type": kind, "generation": _generation(info)})
                if kind == "directory":
                    visit(os.path.join(directory, entry.name), name + "/", depth + 1)
            if _generation(os.fstat(fd)) != before:
                _fail("private index directory changed while enumerating")
        finally:
            os.close(fd)
    visit(path, "", 0)
    if not any(row["type"] == "file" for row in rows):
        _fail("private index has no ordinary files")
    return rows


class _ArchiveWriter:
    def __init__(self, fd):
        self.fd, self.bytes, self.digest = fd, 0, hashlib.sha256()

    def write(self, data):
        if self.bytes + len(data) > MAX_ARCHIVE_BYTES:
            _fail("serialized private archive exceeds its byte ceiling")
        siavector._write_all(self.fd, data)
        self.bytes += len(data)
        self.digest.update(data)
        return len(data)

    def flush(self):
        os.fsync(self.fd)


class _HashReader:
    def __init__(self, stream):
        self.stream, self.digest, self.bytes = stream, hashlib.sha256(), 0

    def read(self, size):
        data = self.stream.read(size)
        self.digest.update(data)
        self.bytes += len(data)
        return data


def _archive(prepared, output):
    source_path = os.path.join(prepared.path, "index")
    source = _Directory(source_path)
    fd = None
    try:
        before = _tree(source_path)
        fd = os.open("index.tar", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=output.fd)
        writer, manifest = _ArchiveWriter(fd), []
        with tarfile.open(fileobj=writer, mode="w|", format=tarfile.PAX_FORMAT) as archive:
            for row in before:
                name, kind = row["path"], row["type"]
                info = tarfile.TarInfo(name)
                info.mode = 0o700 if kind == "directory" else 0o600
                if kind == "directory":
                    info.type = tarfile.DIRTYPE
                    archive.addfile(info)
                    manifest.append({"path": name, "type": kind})
                    continue
                member = siavectormodel._open(os.path.join(source_path, name), os.O_RDONLY)
                with os.fdopen(member, "rb") as stream:
                    current = os.fstat(stream.fileno())
                    if _generation(current) != row["generation"]:
                        _fail("private source member changed before copy")
                    info.size = current.st_size
                    reader = _HashReader(stream)
                    archive.addfile(info, reader)
                    if reader.bytes != info.size or _generation(os.fstat(stream.fileno())) != row["generation"]:
                        _fail("private source member changed during copy")
                    manifest.append({"path": name, "type": kind, "bytes": reader.bytes,
                                     "sha256": reader.digest.hexdigest()})
        writer.flush()
        source.current()
        prepared.current()
        output.current()
        if _tree(source_path) != before:
            _fail("stopped private source tree changed during archive construction")
        return {"path": "index.tar", "sha256": writer.digest.hexdigest(),
                "manifest": manifest, "manifest_sha256": _sha(_canonical(manifest))}
    finally:
        if fd is not None:
            os.close(fd)
        source.close()


def _publish(output, result, current):
    raw = _canonical(result) + b"\n"
    if len(raw) > MAX_ARTIFACT_BYTES:
        _fail("baseline publication exceeds its byte ceiling")
    fd = os.open(".baseline-pending", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600, dir_fd=output.fd)
    try:
        siavector._write_all(fd, raw)
        os.fsync(fd)
        identity = (os.fstat(fd).st_dev, os.fstat(fd).st_ino)
    finally:
        os.close(fd)
    current()
    output.current()
    try:
        os.link(".baseline-pending", "baseline.json", src_dir_fd=output.fd,
                dst_dir_fd=output.fd, follow_symlinks=False)
        os.unlink(".baseline-pending", dir_fd=output.fd)
        os.fsync(output.fd)
    except BaseException:
        _discard_success(output, identity)
        raise
    return identity


def _discard_success(output, identity):
    """Only unlink this invocation's exact success inode, never a replacement."""
    try:
        info = os.stat("baseline.json", dir_fd=output.fd, follow_symlinks=False)
        if stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) == identity:
            os.unlink("baseline.json", dir_fd=output.fd)
    except OSError:
        pass


def _execute(kw):
    selected, queries, request, contract, freeze = _preflight(kw)
    # Detach the small execution configuration only after preflight bounded it.
    execution = {key: copy.deepcopy(value) for key, value in kw.items()
                 if key not in ("capture", "selection", "selection_policy")}
    kw = execution
    output = prepared = None
    published = None
    try:
        with contextlib.ExitStack() as stack:
            scratch = _Directory(kw["scratch_parent"])
            stack.callback(scratch.close)
            current_code = _code_sources(kw["code_expectations"], stack)
            pins, receipts = [], []
            for role in ("preparer", "adapter"):
                build = kw[role]
                pin = _FilePin(build["executable"], build["expected"]["executable_sha256"], executable=True)
                stack.callback(pin.close)
                pins.append(pin)
                sealed = stack.enter_context(siavector.sealed_file(
                    build["build_receipt"], build["build_receipt_sha256"], max_bytes=MAX_ARTIFACT_BYTES))
                receipt = siaqueue.strict_json_loads(os.pread(sealed.fd, sealed.size, 0).decode("utf-8"))
                runner._admit_build(receipt, build["expected"])
                receipts.append(sealed)
            # Fresh output is created relative to an admitted physical parent.
            parent = _Directory(os.path.dirname(kw["output_directory"]), private=False)
            stack.callback(parent.close)
            parent.current()
            os.mkdir(os.path.basename(kw["output_directory"]), 0o700, dir_fd=parent.fd)
            output = _Directory(kw["output_directory"])
            os.mkdir("prepared", 0o700, dir_fd=output.fd)
            prepared = _Directory(os.path.join(output.path, "prepared"))

            def current():
                scratch.current()
                parent.current()
                output.current()
                prepared.current()
                current_code()
                for pin in pins:
                    pin.current()
                for receipt in receipts:
                    receipt.assert_current()

            current()
            preparation = _preparation(runner.prepare_bound(
                **kw["preparer"], request=request, output_directory=prepared.path,
                timeout=kw["timeout"], scratch_parent=kw["scratch_parent"],
                model_expectations=kw["model_expectations"], shared_runtime=kw["shared_runtime"]), request, kw)
            current()
            archive = _archive(prepared, output)
            archive_pin = _FilePin(os.path.join(output.path, archive["path"]), archive["sha256"])
            stack.callback(archive_pin.close)
            pins.append(archive_pin)
            observation, labels = _observation(runner.observe_bound(
                **kw["adapter"], index_archive=archive_pin.path, index_sha256=archive["sha256"],
                embedding=kw["embedding"], queries=queries, limit=kw["limit"], timeout=kw["timeout"],
                scratch_parent=kw["scratch_parent"], model_expectations=kw["model_expectations"],
                shared_runtime=kw["shared_runtime"]), archive, preparation, queries, selected, kw)
            current()
            ids = {row["id"] for row in queries}
            body = {
                "schema": "sia-cognitive-baseline-v1", "status": "observed", "lane": "raw_vector", "split": kw["split"],
                "capture_sha256": kw["expected_capture_sha256"], "policy_sha256": kw["expected_policy_sha256"],
                "selection_sha256": kw["expected_selection_sha256"], "pages_sha256": selected["pages_sha256"],
                "query_roster_sha256": _sha(_canonical(queries)), "baseline_contract_sha256": _sha(_canonical(contract)),
                "parameter_freeze_sha256": kw["expected_parameter_freeze_sha256"], "parameter_freeze": freeze,
                "contract": contract, "queries": queries, "pages": selected["pages"],
                "answer_key": [row for row in selected["answer_key"] if row["id"] in ids],
                "preparation": preparation, "observation": observation, "retrieval_rows": labels, "archive": archive,
                "source_non_claims": {"selection": selected["non_claims"], "history": selected["source_non_claims"]},
                "non_claims": list(NON_CLAIMS),
            }
            result = {**body, "artifact_sha256": _sha(_canonical(body))}
            published = _publish(output, result, current)
            current()
        return result
    except BaseException:
        # Remove only our exact just-published success file, never a replacement
        # or operator data. All preparation/archive/pending partials remain.
        if output is not None and published is not None:
            _discard_success(output, published)
        raise
    finally:
        if prepared is not None:
            prepared.close()
        if output is not None:
            output.close()


def run_baseline(*, capture, expected_capture_sha256, selection_policy, expected_policy_sha256,
                 selection, expected_selection_sha256, split, preparer, adapter, embedding,
                 model_expectations, shared_runtime, code_expectations, limit, timeout,
                 scratch_parent, output_directory, parameter_freeze=None,
                 expected_parameter_freeze_sha256=None):
    """Run only an admitted split, retaining private evidence without a win claim."""
    inputs = locals()
    try:
        return _execute(inputs)
    except BaselineRefusal:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError,
            siavector.VectorRefusal, siavectormodel.ModelRefusal, tarfile.TarError) as exc:
        error = BaselineRefusal("cognitive baseline refused: " + str(exc))
        error.non_claims = list(NON_CLAIMS)
        error.upstream_non_claims = copy.deepcopy(getattr(exc, "non_claims", []))
        raise error from exc
