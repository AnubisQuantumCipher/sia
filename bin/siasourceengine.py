"""Receipt-bound engine generation for one published source closure.

This adapter is intentionally narrower than the compatibility ``brain_sync``
helper.  It binds the installed pin and runtime receipts, holds every named
input generation, executes the pinned engine through its descriptor, admits
closed JSON from each mutating/readback phase, and returns one self-hashed
generation plus an exact source-page projection roster.
"""

import contextlib
import hashlib
import json
import os
import re
import stat
import tempfile


# JACKAL status=exact parsed=512*1024*1024 exact=536870912.
# Assurance: exact rational arithmetic (not yet checker-covered). NOT
# formal-bounded; this is not evidence of a safe capacity or code correctness.
MAX_EXECUTABLE_BYTES = 536_870_912
# JACKAL status=exact parsed=32*1024*1024 exact=33554432.
# Same assurance and nonclaims as above.
MAX_PROJECTION_REQUEST_BYTES = 33_554_432

_HEX = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_VERSION = re.compile(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))+" )
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_CORPUS_KEYS = frozenset({
    "schema", "object_format", "git_executable_sha256",
    "before_commit_oid", "corpus_commit_oid", "corpus_tree_oid", "clean",
    "generation_sha256",
})
_TARGET_VERSION_KEYS = frozenset({
    "slug", "source_sha256", "version_sha256",
})
_TARGET_RESULT_KEYS = frozenset({
    "slug", "page_state", "parse_error_codes",
    "expected_projection_sha256", "current_projection_sha256",
    "current_content_hash", "current_content_hash_match", "projection_match",
})
_TARGET_MANIFEST_KEYS = _TARGET_VERSION_KEYS | (
    _TARGET_RESULT_KEYS - {"slug"})
_SYNC_RESULT_KEYS = frozenset({
    "schema_version", "source_id", "sync_status", "added", "modified",
    "deleted", "chunks_created", "embedded",
})
_LINKS_RESULT_KEYS = frozenset({
    "action", "links_created", "timeline_created", "pages_processed",
    "stale_remaining", "budget_hit", "skipped_missing_target",
    "skipped_cross_source",
})
_MENTIONS_RESULT_KEYS = frozenset({
    "links_created", "timeline_entries_created", "pages_processed",
})
_STATUS_KEYS = frozenset({
    "schema_version", "version", "generated_at", "mode", "sync",
})
_STATUS_SYNC_KEYS = frozenset({
    "schema_version", "generated_at", "sources", "unacknowledged_failures",
    "embedding_column",
})
_STATUS_SOURCE_KEYS = frozenset({
    "source_id", "name", "local_path", "sync_enabled", "last_sync_at",
    "hours_since_last_sync", "staleness_hours", "staleness_class",
    "last_commit", "pages", "chunks_total", "chunks_unembedded",
    "embedding_coverage_pct", "backfill_queued", "backfill_active",
    "backfill_last_completed_at",
})
_PROJECTION_KEYS = frozenset({
    "schema_version", "source_id", "target_count",
    "retrieval_bookkeeping_updated", "operation_writes_performed",
    "all_match", "targets",
})
_GENERATION_KEYS_V2 = frozenset({
    "schema", "source_id", "engine_version", "gbrain_commit",
    "gbrain_bun_lock_sha256", "gbrain_pin_sha256",
    "gbrain_pin_receipt_sha256", "gbrain_release_receipt_sha256",
    "gbrain_executable_sha256", "version_raw_sha256",
    "sync_raw_sha256", "sync_stderr_sha256", "sync_result_sha256",
    "sync_status", "sync_requested_commit", "links_raw_sha256",
    "links_stderr_sha256", "links_result_sha256",
    "links_stale_remaining", "mentions_raw_sha256",
    "mentions_stderr_sha256", "mentions_result_sha256",
    "status_raw_sha256", "status_stderr_sha256", "status_result_sha256",
    "status_last_commit", "local_path", "index_manifest_sha256",
    "chunks_unembedded", "embedding_column", "unacknowledged_failures",
    "projection_request_sha256", "projection_raw_sha256",
    "projection_stderr_sha256", "projection_result_sha256",
    "projection_target_count", "projection_retrieval_bookkeeping_updated",
    "projection_operation_writes_performed", "generation_sha256",
})
_GENERATION_KEYS_V3 = _GENERATION_KEYS_V2 | frozenset({
    "gbrain_overlay_sha256", "gbrain_overlay_tree_oid",
})
_GENERATION_KEYS_V4 = _GENERATION_KEYS_V3 | frozenset({
    "embed_raw_sha256", "embed_stderr_sha256",
})


def _refuse(source, reason, *, upstream=None):
    source.refuse(reason, phase="effects", upstream=upstream)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _identity(info):
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
    )


def _nonnegative(owner, value):
    return type(value) is int and owner["_nonnegative_status_integer"](value)


class _Held:
    def __init__(self, owner, source, path, label, *, directory=False,
                 ceiling=None, executable=False):
        self.owner = owner
        self.source = source
        self.path = os.path.abspath(path)
        self.label = label
        self.directory = directory
        self.ceiling = ceiling
        self.executable = executable
        self.fd = None
        self.raw = None
        try:
            opener = (owner["_open_chain_directory_generation"]
                      if directory else owner["_open_chain_generation"])
            self.fd, self.generation = opener(self.path, label)
            self.record = {
                "fd": self.fd, "generation": self.generation,
                "path": self.path, "label": label, "directory": directory,
            }
            info = os.fstat(self.fd)
            if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                _refuse(source, "source-engine-unsafe-" + label)
            if directory:
                if not stat.S_ISDIR(info.st_mode):
                    _refuse(source, "source-engine-unsafe-" + label)
            else:
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 \
                        or type(ceiling) is not int \
                        or not 0 < info.st_size <= ceiling:
                    _refuse(source, "source-engine-unsafe-" + label)
                if executable and (info.st_mode & 0o111 == 0):
                    _refuse(source, "source-engine-unsafe-" + label)
                self.raw = self._read(info.st_size)
                if executable and self.raw[:4] != b"\x7fELF":
                    _refuse(source, "source-engine-executable-format")
            self.current()
        except BaseException:
            self.close()
            raise

    def _read(self, size):
        reader = None
        try:
            reader = os.open(
                self.owner["_chain_descriptor_path"](self.fd),
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
            blocks = []
            total = 0
            while total < size:
                block = os.read(reader, min(1_048_576, size - total))
                if not block:
                    break
                blocks.append(block)
                total += len(block)
            if total != size or _identity(os.fstat(reader)) \
                    != _identity(os.fstat(self.fd)):
                _refuse(self.source, "source-engine-short-or-changing-" + self.label)
            return b"".join(blocks)
        finally:
            if reader is not None:
                os.close(reader)

    def current(self):
        if self.fd is None or not self.owner["_chain_generation_matches"](
                self.record):
            _refuse(self.source, "source-engine-changed-" + self.label)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class _Boundary:
    def __init__(self, owner, source):
        self.owner = owner
        self.source = source
        self.held = []
        try:
            self.corpus = self._hold(
                owner["CORPUS"], "corpus-directory", directory=True)
            self.engine_root = self._hold(
                os.path.dirname(os.path.dirname(owner["GBRAIN"])),
                "engine-root", directory=True)
            self.executable = self._hold(
                owner["GBRAIN"], "engine-executable",
                ceiling=MAX_EXECUTABLE_BYTES, executable=True)
            self.pin = self._hold(
                owner["GBRAIN_PIN"], "engine-pin",
                ceiling=owner["MAX_CONFIG_BYTES"])
            self.pin_receipt = self._hold(
                owner["GBRAIN_PIN_RECEIPT"], "engine-pin-receipt",
                ceiling=owner["MAX_CONFIG_BYTES"])
            self.runtime_receipt = self._hold(
                owner["GBRAIN_RUNTIME_RECEIPT"], "engine-runtime-receipt",
                ceiling=owner["MAX_CONFIG_BYTES"])
            self.pin_fields = self._admit_pin()
            self._admit_receipts()
            self.current()
        except BaseException:
            self.close()
            raise

    def _hold(self, path, label, **kwargs):
        held = _Held(self.owner, self.source, path, label, **kwargs)
        self.held.append(held)
        return held

    def hold_page(self, path):
        return self._hold(
            path, "target-page", ceiling=self.owner["MAX_EVENT_PAGE_BYTES"])

    def _text(self, held, reason):
        try:
            return held.raw.decode("utf-8", errors="strict")
        except UnicodeError as exc:
            _refuse(self.source, reason, upstream=exc)

    def _admit_pin(self):
        text = self._text(self.pin, "source-engine-pin-utf8")
        if not text.endswith("\n"):
            _refuse(self.source, "source-engine-pin-wire")
        values = {}
        for line in text.splitlines():
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator or key not in {
                    "commit", "version", "bun_lock_sha256",
                    "overlay_sha256", "overlay_tree_oid", "verified"} \
                    or key in values or not value:
                _refuse(self.source, "source-engine-pin-fields")
            values[key] = value
        if set(values) != {
                "commit", "version", "bun_lock_sha256",
                "overlay_sha256", "overlay_tree_oid", "verified"} \
                or _COMMIT.fullmatch(values["commit"]) is None \
                or _VERSION.fullmatch(values["version"]) is None \
                or _HEX.fullmatch(values["bun_lock_sha256"]) is None \
                or _HEX.fullmatch(values["overlay_sha256"]) is None \
                or _COMMIT.fullmatch(values["overlay_tree_oid"]) is None \
                or _DATE.fullmatch(values["verified"]) is None:
            _refuse(self.source, "source-engine-pin-fields")
        return values

    def _fixed_lines(self, held, expected, reason):
        text = self._text(held, reason + "-utf8")
        if not text.endswith("\n") or text.splitlines() != expected:
            _refuse(self.source, reason)

    def _admit_receipts(self):
        pin_sha256 = hashlib.sha256(self.pin.raw).hexdigest()
        self._fixed_lines(self.pin_receipt, [
            "managed-by=khephri.sia",
            "kind=gbrain-pin",
            "path=" + self.pin.path,
            "sha256=" + pin_sha256,
        ], "source-engine-pin-receipt")
        executable_sha256 = hashlib.sha256(self.executable.raw).hexdigest()
        self._fixed_lines(self.runtime_receipt, [
            "managed-by=khephri.sia",
            "commit=" + self.pin_fields["commit"],
            "version=" + self.pin_fields["version"],
            "bun_lock_sha256=" + self.pin_fields["bun_lock_sha256"],
            "overlay_sha256=" + self.pin_fields["overlay_sha256"],
            "overlay_tree_oid=" + self.pin_fields["overlay_tree_oid"],
            "binary_sha256=" + executable_sha256,
        ], "source-engine-runtime-receipt")
        self.executable_sha256 = executable_sha256
        self.pin_sha256 = pin_sha256
        self.pin_receipt_sha256 = hashlib.sha256(
            self.pin_receipt.raw).hexdigest()
        self.runtime_receipt_sha256 = hashlib.sha256(
            self.runtime_receipt.raw).hexdigest()

    def current(self):
        for held in self.held:
            held.current()

    def close(self):
        for held in reversed(self.held):
            held.close()
        self.held.clear()


def _closed(source, value, keys, reason):
    if type(value) is not dict or set(value) != keys:
        _refuse(source, reason)


def _json_result(owner, source, result, reason):
    if result.returncode != 0 or type(result.stdout) is not str \
            or type(result.stderr) is not str \
            or not result.stdout.startswith("{") \
            or not result.stdout.endswith("}\n"):
        _refuse(source, reason + "-process")
    try:
        value = owner["_strict_json_loads"](result.stdout)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        _refuse(source, reason + "-json", upstream=exc)
    if type(value) is not dict:
        _refuse(source, reason + "-json")
    return value


def _admit_effect_process(source, result, reason):
    """Admit a bounded mutating process only through its later readback.

    The pinned engine has no structured ``embed`` result surface.  Its human
    stdout is retained by digest but never parsed into authority; the closed
    status document below is the postcondition that proves the source has no
    unembedded chunks.
    """
    if result.returncode != 0 or type(result.stdout) is not str \
            or type(result.stderr) is not str:
        _refuse(source, reason + "-process")


def _mention_json_result(owner, source, result):
    """Admit the pinned extractor's one documented optional JSONL prelude."""
    reason = "source-engine-mentions"
    if result.returncode != 0 or type(result.stdout) is not str \
            or type(result.stderr) is not str \
            or not result.stdout.startswith("{") \
            or not result.stdout.endswith("}\n"):
        _refuse(source, reason + "-process")
    prelude = None
    try:
        value = owner["_strict_json_loads"](result.stdout)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        head, separator, tail = result.stdout.partition("\n")
        if not separator or not tail:
            _refuse(source, reason + "-json")
        try:
            prelude = owner["_strict_json_loads"](head)
            value = owner["_strict_json_loads"](tail)
        except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
            _refuse(source, reason + "-json", upstream=exc)
    if type(value) is not dict:
        _refuse(source, reason + "-json")
    if prelude is not None:
        _closed(source, prelude, {"event", "message"},
                "source-engine-mentions-prelude-shape")
        if prelude != {
                "event": "no_gazetteer",
                "message":
                    "no linkable entity pages found; nothing to scan"}:
            _refuse(source, "source-engine-mentions-prelude-fields")
        if value != {
                "links_created": 0, "timeline_entries_created": 0,
                "pages_processed": 0}:
            _refuse(source, "source-engine-mentions-prelude-result")
    return value


def _run(owner, source, boundary, arguments, *, label, timeout):
    boundary.current()
    # This transaction is descriptor-bound; ambient database selectors,
    # mount routing, guardrail/preload modules, provider credentials and
    # proxy settings are not part of its authority.  gbrain reads its owned
    # config and secret file below GBRAIN_HOME.  BUN_OPTIONS is defense in
    # depth for standalone Bun executables; the managed build also disables
    # cwd dotenv/bunfig autoload at compile time.
    home = owner["HOME"]
    environment = {
        "HOME": home,
        "GBRAIN_HOME": owner["SHARE"],
        "PATH": owner["BUN_DIR"] + ":" + os.defpath,
        "TMPDIR": owner["STATE"],
        "BUN_OPTIONS": "--no-env-file",
        "DO_NOT_TRACK": "1",
        "NO_COLOR": "1",
        "GBRAIN_SKIP_STARTUP_HOOKS": "1",
        "GBRAIN_SYNC_NO_DELEGATE": "1",
        "GBRAIN_NO_BANNER": "1",
        "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC",
        "XDG_CONFIG_HOME": os.path.join(home, ".config"),
        "XDG_DATA_HOME": os.path.join(home, ".local", "share"),
        "XDG_CACHE_HOME": os.path.join(home, ".cache"),
        "XDG_STATE_HOME": os.path.join(home, ".local", "state"),
    }
    try:
        result = owner["_run_bounded_text_process"](
            [owner["_chain_descriptor_path"](boundary.executable.fd),
             *arguments],
            env=environment, timeout=timeout,
            cwd=owner["_chain_descriptor_path"](boundary.corpus.fd),
            pass_fds=(boundary.executable.fd, boundary.corpus.fd),
            label=label, output_limit=owner["MAX_EXTERNAL_OUTPUT_BYTES"])
    except (OSError, ValueError, RuntimeError, OverflowError,
            UnicodeError) as exc:
        _refuse(source, "source-engine-process", upstream=exc)
    boundary.current()
    return result


def _admit_corpus(owner, source, value):
    _closed(source, value, _CORPUS_KEYS, "source-engine-corpus-shape")
    if value.get("schema") \
            != "sia-controller-source-corpus-generation-v1" \
            or value.get("object_format") not in {"sha1", "sha256"} \
            or value.get("clean") is not True \
            or value.get("generation_sha256") != _sha({
                key: item for key, item in value.items()
                if key != "generation_sha256"}):
        _refuse(source, "source-engine-corpus-generation")
    for key in ("git_executable_sha256",):
        if type(value.get(key)) is not str \
                or _HEX.fullmatch(value[key]) is None:
            _refuse(source, "source-engine-corpus-digest")
    oid = (_COMMIT if value["object_format"] == "sha1" else _HEX)
    for key in ("before_commit_oid", "corpus_commit_oid", "corpus_tree_oid"):
        if type(value.get(key)) is not str or oid.fullmatch(value[key]) is None:
            _refuse(source, "source-engine-corpus-object-id")
    return value


def _target_request(owner, source, boundary, target_versions):
    if type(target_versions) is not list or not target_versions \
            or len(target_versions) > owner["MAX_EVENT_LOOKUP_PAGES"]:
        _refuse(source, "source-engine-target-roster")
    targets = []
    detached = []
    prior = None
    for value in target_versions:
        _closed(source, value, _TARGET_VERSION_KEYS,
                "source-engine-target-version-shape")
        slug = value.get("slug")
        if type(slug) is not str \
                or owner["_canonical_corpus_slug"](slug) != slug \
                or prior is not None and slug <= prior:
            _refuse(source, "source-engine-target-version-order")
        prior = slug
        for key in ("source_sha256", "version_sha256"):
            if type(value.get(key)) is not str \
                    or _HEX.fullmatch(value[key]) is None:
                _refuse(source, "source-engine-target-version-digest")
        page = boundary.hold_page(owner["corpus_path"](slug))
        if hashlib.sha256(page.raw).hexdigest() != value["source_sha256"]:
            _refuse(source, "source-engine-target-source-differs")
        try:
            markdown = page.raw.decode("utf-8", errors="strict")
        except UnicodeError as exc:
            _refuse(source, "source-engine-target-source-utf8", upstream=exc)
        targets.append({"slug": slug, "raw_markdown": markdown})
        detached.append(dict(value))
    request = {"source_id": owner["GBRAIN_SOURCE"], "targets": targets}
    try:
        encoded = _canonical(request)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        _refuse(source, "source-engine-projection-request", upstream=exc)
    if not encoded or len(encoded) > MAX_PROJECTION_REQUEST_BYTES:
        _refuse(source, "source-engine-projection-request-capacity")
    return detached, request, encoded


@contextlib.contextmanager
def _request_file(owner, source, encoded):
    descriptor = directory_fd = None
    try:
        with tempfile.TemporaryDirectory(
                prefix="sia-source-projection-", dir=owner["STATE"]) as root:
            path = os.path.join(root, "request.json")
            descriptor = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
                0o600)
            pending = memoryview(encoded)
            while pending:
                written = os.write(descriptor, pending)
                if written <= 0:
                    _refuse(source, "source-engine-projection-request-write")
                pending = pending[written:]
            os.fsync(descriptor)
            written_info = os.fstat(descriptor)
            if not stat.S_ISREG(written_info.st_mode) \
                    or written_info.st_uid != os.geteuid() \
                    or written_info.st_nlink != 1 \
                    or stat.S_IMODE(written_info.st_mode) != 0o600 \
                    or written_info.st_size != len(encoded):
                _refuse(source, "source-engine-projection-request-file")
            os.close(descriptor)
            descriptor = None
            directory_fd = os.open(
                root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0))
            os.fsync(directory_fd)
            before = _identity(os.lstat(path))
            yield path
            after = os.lstat(path)
            if _identity(after) != before or not stat.S_ISREG(after.st_mode):
                _refuse(source, "source-engine-projection-request-changed")
    except (OSError, ValueError) as exc:
        _refuse(source, "source-engine-projection-request-file", upstream=exc)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory_fd is not None:
            os.close(directory_fd)


def _command_digests(result, value):
    return {
        "raw": hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
        "stderr": hashlib.sha256(result.stderr.encode("utf-8")).hexdigest(),
        "result": _sha(value),
    }


def _admit_sync(owner, source, value):
    _closed(source, value, _SYNC_RESULT_KEYS, "source-engine-sync-shape")
    if value.get("schema_version") != 1 \
            or value.get("source_id") != owner["GBRAIN_SOURCE"] \
            or value.get("sync_status") not in {
                "synced", "first_sync", "up_to_date"} \
            or any(not _nonnegative(owner, value.get(key)) for key in (
                "added", "modified", "deleted", "chunks_created",
                "embedded")) \
            or value.get("embedded") != 0:
        _refuse(source, "source-engine-sync-fields")


def _admit_links(owner, source, value):
    _closed(source, value, _LINKS_RESULT_KEYS, "source-engine-links-shape")
    if value.get("action") != "extract_stale_done" \
            or value.get("budget_hit") is not False \
            or any(not _nonnegative(owner, value.get(key)) for key in (
                "links_created", "timeline_created", "pages_processed",
                "stale_remaining", "skipped_missing_target",
                "skipped_cross_source")) \
            or value.get("stale_remaining") != 0:
        _refuse(source, "source-engine-links-fields")


def _admit_mentions(owner, source, value):
    _closed(source, value, _MENTIONS_RESULT_KEYS,
            "source-engine-mentions-shape")
    if any(not _nonnegative(owner, value.get(key)) for key in (
            "links_created", "timeline_entries_created", "pages_processed")):
        _refuse(source, "source-engine-mentions-fields")


def _admit_status(owner, source, boundary, value, corpus):
    _closed(source, value, _STATUS_KEYS, "source-engine-status-shape")
    sync = value.get("sync")
    _closed(source, sync, _STATUS_SYNC_KEYS,
            "source-engine-status-sync-shape")
    sources = sync.get("sources")
    if value.get("schema_version") != 1 \
            or value.get("version") != boundary.pin_fields["version"] \
            or value.get("mode") != "local" \
            or type(value.get("generated_at")) is not str \
            or not value["generated_at"] \
            or sync.get("schema_version") != 1 \
            or type(sync.get("generated_at")) is not str \
            or not sync["generated_at"] \
            or type(sync.get("embedding_column")) is not str \
            or not sync["embedding_column"] \
            or not _nonnegative(owner, sync.get("unacknowledged_failures")) \
            or sync["unacknowledged_failures"] != 0 \
            or type(sources) is not list:
        _refuse(source, "source-engine-status-fields")
    selected = [row for row in sources
                if type(row) is dict
                and row.get("source_id") == owner["GBRAIN_SOURCE"]]
    if len(selected) != 1:
        _refuse(source, "source-engine-status-source-roster")
    row = selected[0]
    _closed(source, row, _STATUS_SOURCE_KEYS,
            "source-engine-status-source-shape")
    for key in (
            "pages", "chunks_total", "chunks_unembedded", "backfill_queued",
            "backfill_active"):
        if not _nonnegative(owner, row.get(key)):
            _refuse(source, "source-engine-status-source-count")
    local_path = row.get("local_path")
    if row.get("sync_enabled") is not True \
            or row.get("last_commit") != corpus["corpus_commit_oid"] \
            or row.get("chunks_unembedded") != 0 \
            or type(local_path) is not str or "\x00" in local_path \
            or not os.path.isabs(local_path) \
            or os.path.realpath(local_path) \
            != os.path.realpath(owner["CORPUS"]):
        _refuse(source, "source-engine-status-source-fields")
    return row, sync


def _admit_projection(owner, source, value, target_versions):
    _closed(source, value, _PROJECTION_KEYS,
            "source-engine-projection-shape")
    targets = value.get("targets")
    if value.get("schema_version") != 1 \
            or value.get("source_id") != owner["GBRAIN_SOURCE"] \
            or type(value.get("target_count")) is not int \
            or value["target_count"] != len(target_versions) \
            or value.get("retrieval_bookkeeping_updated") is not False \
            or value.get("operation_writes_performed") is not False \
            or value.get("all_match") is not True \
            or type(targets) is not list \
            or len(targets) != len(target_versions):
        _refuse(source, "source-engine-projection-fields")
    manifest = []
    for wanted, observed in zip(target_versions, targets):
        _closed(source, observed, _TARGET_RESULT_KEYS,
                "source-engine-projection-target-shape")
        expected = observed.get("expected_projection_sha256")
        current = observed.get("current_projection_sha256")
        content = observed.get("current_content_hash")
        if observed.get("slug") != wanted["slug"] \
                or observed.get("page_state") != "live" \
                or observed.get("parse_error_codes") != [] \
                or type(expected) is not str \
                or _HEX.fullmatch(expected) is None \
                or current != expected or content != expected \
                or observed.get("current_content_hash_match") is not True \
                or observed.get("projection_match") is not True:
            _refuse(source, "source-engine-projection-target-fields")
        row = {
            **wanted,
            **{key: observed[key]
               for key in _TARGET_RESULT_KEYS if key != "slug"},
        }
        if set(row) != _TARGET_MANIFEST_KEYS:
            _refuse(source, "source-engine-projection-manifest-shape")
        manifest.append(row)
    return manifest


def sync_generation(owner, *, corpus_generation, target_versions):
    """Run and admit one exact pinned engine generation."""
    import siasourcebatch as source

    corpus = _admit_corpus(owner, source, corpus_generation)
    boundary = _Boundary(owner, source)
    try:
        versions, request, request_raw = _target_request(
            owner, source, boundary, target_versions)

        version_result = _run(
            owner, source, boundary, ["--version"],
            label="source engine version", timeout=30)
        if version_result.returncode != 0 or version_result.stderr != "" \
                or version_result.stdout \
                != "gbrain " + boundary.pin_fields["version"] + "\n":
            _refuse(source, "source-engine-version")

        sync_result = _run(owner, source, boundary, [
            "sync", "--source", owner["GBRAIN_SOURCE"], "--json",
            "--no-pull", "--no-delegate", "--no-embed", "--no-extract",
        ], label="source engine sync", timeout=300)
        sync = _json_result(owner, source, sync_result, "source-engine-sync")
        _admit_sync(owner, source, sync)

        # ``sync --json`` in the pinned engine emits a second cost-gate JSON
        # document whenever implicit embedding is enabled.  It can also run
        # implicit link extraction before returning, even though this
        # transaction has separate admitted extraction phases below.  Keep
        # sync to one closed synchronization result by disabling both side
        # effects, then drain the exact source explicitly.  The embed CLI is
        # human-output-only, so its text is evidence by digest, not parsed
        # authority; the closed status readback below must observe zero
        # unembedded chunks and zero stale links.
        embed_result = _run(owner, source, boundary, [
            "embed", "--stale", "--source", owner["GBRAIN_SOURCE"],
            "--catch-up",
        ], label="source engine embedding", timeout=300)
        _admit_effect_process(
            source, embed_result, "source-engine-embedding")

        links_result = _run(owner, source, boundary, [
            "extract", "links", "--source", "db", "--stale",
            "--source-id", owner["GBRAIN_SOURCE"], "--json",
        ], label="source engine link extraction", timeout=300)
        links = _json_result(
            owner, source, links_result, "source-engine-links")
        _admit_links(owner, source, links)

        mentions_result = _run(owner, source, boundary, [
            "extract", "links", "--by-mention", "--ner",
            "--source", "db", "--source-id", owner["GBRAIN_SOURCE"],
            "--json",
        ], label="source engine mention extraction", timeout=300)
        mentions = _mention_json_result(owner, source, mentions_result)
        _admit_mentions(owner, source, mentions)

        status_result = _run(owner, source, boundary, [
            "status", "--section", "sync", "--json",
        ], label="source engine status", timeout=120)
        status = _json_result(
            owner, source, status_result, "source-engine-status")
        status_source, status_sync = _admit_status(
            owner, source, boundary, status, corpus)

        with _request_file(owner, source, request_raw) as request_path:
            projection_result = _run(owner, source, boundary, [
                "call", "--no-migrate", "--source",
                owner["GBRAIN_SOURCE"], "--params-file", request_path,
                "get_page_projection",
            ], label="source engine page projection", timeout=120)
            projection = _json_result(
                owner, source, projection_result,
                "source-engine-projection")
        manifest = _admit_projection(
            owner, source, projection, versions)
        manifest_sha256 = _sha(manifest)

        sync_digests = _command_digests(sync_result, sync)
        links_digests = _command_digests(links_result, links)
        mentions_digests = _command_digests(mentions_result, mentions)
        status_digests = _command_digests(status_result, status)
        projection_digests = _command_digests(
            projection_result, projection)
        body = {
            "schema": "sia-controller-source-sync-generation-v4",
            "source_id": owner["GBRAIN_SOURCE"],
            "engine_version": boundary.pin_fields["version"],
            "gbrain_commit": boundary.pin_fields["commit"],
            "gbrain_bun_lock_sha256":
                boundary.pin_fields["bun_lock_sha256"],
            "gbrain_overlay_sha256":
                boundary.pin_fields["overlay_sha256"],
            "gbrain_overlay_tree_oid":
                boundary.pin_fields["overlay_tree_oid"],
            "gbrain_pin_sha256": boundary.pin_sha256,
            "gbrain_pin_receipt_sha256": boundary.pin_receipt_sha256,
            "gbrain_release_receipt_sha256":
                boundary.runtime_receipt_sha256,
            "gbrain_executable_sha256": boundary.executable_sha256,
            "version_raw_sha256": hashlib.sha256(
                version_result.stdout.encode("utf-8")).hexdigest(),
            "sync_raw_sha256": sync_digests["raw"],
            "sync_stderr_sha256": sync_digests["stderr"],
            "sync_result_sha256": sync_digests["result"],
            "sync_status": sync["sync_status"],
            "sync_requested_commit": corpus["corpus_commit_oid"],
            "embed_raw_sha256": hashlib.sha256(
                embed_result.stdout.encode("utf-8")).hexdigest(),
            "embed_stderr_sha256": hashlib.sha256(
                embed_result.stderr.encode("utf-8")).hexdigest(),
            "links_raw_sha256": links_digests["raw"],
            "links_stderr_sha256": links_digests["stderr"],
            "links_result_sha256": links_digests["result"],
            "links_stale_remaining": links["stale_remaining"],
            "mentions_raw_sha256": mentions_digests["raw"],
            "mentions_stderr_sha256": mentions_digests["stderr"],
            "mentions_result_sha256": mentions_digests["result"],
            "status_raw_sha256": status_digests["raw"],
            "status_stderr_sha256": status_digests["stderr"],
            "status_result_sha256": status_digests["result"],
            "status_last_commit": status_source["last_commit"],
            "local_path": status_source["local_path"],
            "index_manifest_sha256": manifest_sha256,
            "chunks_unembedded": status_source["chunks_unembedded"],
            "embedding_column": status_sync["embedding_column"],
            "unacknowledged_failures":
                status_sync["unacknowledged_failures"],
            "projection_request_sha256": hashlib.sha256(
                request_raw).hexdigest(),
            "projection_raw_sha256": projection_digests["raw"],
            "projection_stderr_sha256": projection_digests["stderr"],
            "projection_result_sha256": projection_digests["result"],
            "projection_target_count": projection["target_count"],
            "projection_retrieval_bookkeeping_updated":
                projection["retrieval_bookkeeping_updated"],
            "projection_operation_writes_performed":
                projection["operation_writes_performed"],
        }
        result = {
            "sync_generation": {
                **body, "generation_sha256": _sha(body)},
            "target_manifest": manifest,
            "target_manifest_sha256": manifest_sha256,
        }
        if set(result["sync_generation"]) != _GENERATION_KEYS_V4:
            _refuse(source, "source-engine-generation-shape")
        boundary.current()
        return result
    finally:
        boundary.close()
