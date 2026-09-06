"""Operation-owned journal scratch and cursor observations, never an ACK.

The owning core is explicit. This module neither imports nor binds sialib,
acquires runtime leases, nor selects or parses journal records. The existing
journal collector supplies its catalog and bounded processed prefix.
"""

import base64
import stat

import siaeventplan as _native


NON_CLAIMS = (
    "This receipt retains operation-observed cursor bytes and catalog order; it does not authenticate the journal or establish complete machine history.",
    "No real journal cursor is acknowledged or advanced by this capture; corpus publication, cursor commit, source acknowledgment, and live generation publication remain separate operations.",
    "Existing bounded journal parsing and catalog-prefix selection remain controlling; retained refusal records do not make omitted payloads complete.",
    "Named-path and descriptor guards cover the checked generations, not hostile same-user mutation or changes after the returned receipt.",
)
_SCOPES = ("sys", "user")
_LEAVES = tuple(scope + suffix for scope in _SCOPES
                for suffix in (".catalog", ".full", ".selected"))


def _refuse(reason):
    error = ValueError("journal capture refused: " + reason)
    error.reason = reason
    error.non_claims = list(NON_CLAIMS)
    raise error


def _generation(info):
    return {"device": info.st_dev, "inode": info.st_ino, "mode": info.st_mode,
            "uid": info.st_uid, "nlink": info.st_nlink, "size": info.st_size,
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns}


def _directory_identity(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid


def _path(owner, value):
    os = owner["os"]
    if type(value) is not str or not value or "\x00" in value \
            or len(value) > owner["MAX_CONFIG_PATH_CHARS"] \
            or not os.path.isabs(value) or os.path.normpath(value) != value:
        _refuse("noncanonical-path")
    return value


class _Directory:
    """Hold every ancestor and recheck each named edge without following links."""
    def __init__(self, owner, path, *, private=False):
        self.owner, self.path = owner, _path(owner, path)
        self.chain = []
        os = owner["os"]
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            root = os.open("/", flags)
            self.chain.append(("/", root, _directory_identity(os.fstat(root))))
            for name in self.path.split("/")[1:]:
                if not name:
                    continue
                descriptor = os.open(name, flags, dir_fd=self.chain[-1][1])
                self.chain.append((name, descriptor, _directory_identity(os.fstat(descriptor))))
            self.fd = self.chain[-1][1]
            info = os.fstat(self.fd)
            if private and (info.st_uid != os.geteuid()
                            or stat.S_IMODE(info.st_mode) != 0o700):
                _refuse("operation-directory-not-private")
            self.current()
        except BaseException:
            self.close()
            raise

    def current(self):
        os = self.owner["os"]
        if not self.chain:
            _refuse("closed-directory")
        parent = None
        for name, descriptor, original in self.chain:
            held = os.fstat(descriptor)
            named = os.stat(name, follow_symlinks=False,
                            **({} if parent is None else {"dir_fd": parent}))
            if not stat.S_ISDIR(held.st_mode) or not stat.S_ISDIR(named.st_mode) \
                    or _directory_identity(held) != original \
                    or _directory_identity(named) != original:
                _refuse("named-directory-generation-changed")
            parent = descriptor

    def close(self):
        os = self.owner["os"]
        for _name, descriptor, _identity in reversed(self.chain):
            os.close(descriptor)
        self.chain = []


class _Cursor:
    def __init__(self, owner, parent, name):
        self.owner, self.parent, self.name = owner, parent, name
        self.fd, self.original, self.raw = None, None, b""
        os = owner["os"]
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        parent.current()
        try:
            self.fd = os.open(name, flags, dir_fd=parent.fd)
        except FileNotFoundError:
            self.current()
            return
        try:
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
                    or info.st_nlink != 1 or info.st_size > owner["MAX_JOURNAL_CURSOR_BYTES"]:
                _refuse("unsafe-before-cursor")
            self.original = _generation(info)
            self.raw = self._read()
            self.current()
        except BaseException:
            self.close()
            raise

    def _read(self):
        os = self.owner["os"]
        maximum = self.owner["MAX_JOURNAL_CURSOR_BYTES"]
        if self.original["size"] > maximum:
            _refuse("before-cursor-capacity")
        data = bytearray()
        while len(data) <= maximum:
            amount = min(self.owner["MAX_JOURNAL_READ_BYTES"], maximum + 1 - len(data))
            block = os.pread(self.fd, amount, len(data))
            if not block:
                break
            data.extend(block)
        if len(data) > maximum or len(data) != self.original["size"]:
            _refuse("before-cursor-byte-change")
        return bytes(data)

    def current(self):
        os = self.owner["os"]
        self.parent.current()
        try:
            named = os.stat(self.name, dir_fd=self.parent.fd, follow_symlinks=False)
        except FileNotFoundError:
            if self.fd is None:
                self.parent.current()
                return
            _refuse("before-cursor-disappeared")
        if self.fd is None:
            _refuse("absent-before-cursor-appeared")
        held = os.fstat(self.fd)
        if _generation(held) != self.original or _generation(named) != self.original:
            _refuse("before-cursor-generation-changed")
        if self._read() != self.raw:
            _refuse("before-cursor-byte-change")
        # Re-resolve only after the complete retained-fd read.
        named = os.stat(self.name, dir_fd=self.parent.fd, follow_symlinks=False)
        if _generation(os.fstat(self.fd)) != self.original or _generation(named) != self.original:
            _refuse("before-cursor-final-generation-changed")
        self.parent.current()

    def close(self):
        if self.fd is not None:
            self.owner["os"].close(self.fd)
            self.fd = None


class JournalCaptureContext:
    """An explicitly owned, single-use sys/user capture capability."""
    def __init__(self, owner, *, operation_id, directory):
        self.owner, self.operation_id = owner, operation_id
        self.directory = self.source_directory = None
        self.sources, self.scratch, self.rows, self.active = {}, {}, {}, {}
        self.failed, self.closed = False, False
        if type(owner) is not dict or type(operation_id) is not str \
                or not operation_id or len(operation_id) > owner["MAX_SOURCE_NAME_CHARS"] \
                or owner["re"].fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", operation_id) is None:
            _refuse("operation-identity")
        try:
            self.directory = _Directory(owner, directory, private=True)
            os = owner["os"]
            for leaf in _LEAVES:
                try:
                    os.stat(leaf, dir_fd=self.directory.fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                _refuse("preexisting-operation-scratch")
            self.state_path = _path(owner, owner["STATE"])
            self.source_directory = _Directory(owner, self.state_path)
            for scope in _SCOPES:
                self.sources[scope] = _Cursor(owner, self.source_directory,
                                              "journal-" + scope + ".cursor")
            self.current()
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        self.current()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is None and not self.failed:
                self.current()
        finally:
            self.close()
        return False

    def _check(self):
        if self.closed or self.failed:
            _refuse("closed-or-failed-operation")

    def current(self):
        self._check()
        self.directory.current()
        for source in self.sources.values():
            source.current()
        os = self.owner["os"]
        for leaf, (descriptor, original) in self.scratch.items():
            held = os.fstat(descriptor)
            named = os.stat(leaf, dir_fd=self.directory.fd, follow_symlinks=False)
            if (held.st_dev, held.st_ino) != original \
                    or (named.st_dev, named.st_ino) != original \
                    or _generation(held) != _generation(named) \
                    or not stat.S_ISREG(held.st_mode) or held.st_uid != os.geteuid() \
                    or held.st_nlink != 1 or stat.S_IMODE(held.st_mode) != 0o600 \
                    or held.st_size > self.owner["MAX_JOURNAL_CURSOR_BYTES"]:
                _refuse("operation-scratch-generation-changed")
        self.source_directory.current()
        self.directory.current()

    def baseline(self, scope, cursor_file):
        self._source(scope, cursor_file)
        self.current()
        return self.sources[scope].original is None

    def _source(self, scope, cursor_file):
        self._check()
        if type(scope) is not str or scope not in _SCOPES \
                or type(cursor_file) is not str \
                or cursor_file != self.owner["os"].path.join(
                    self.state_path, "journal-" + scope + ".cursor"):
            _refuse("cursor-scope-or-path")

    def begin(self, scope, cursor_file, metadata_only):
        self._source(scope, cursor_file)
        if type(metadata_only) is not bool or scope in self.active or scope in self.rows:
            _refuse("repeated-or-invalid-scope")
        self.current()
        self.active[scope] = metadata_only
        return tuple(self.path(scope + suffix) for suffix in (".selected", ".catalog", ".full"))

    def path(self, leaf):
        if leaf not in _LEAVES:
            _refuse("unknown-operation-scratch")
        return "/proc/" + str(self.owner["os"].getpid()) + "/fd/" \
            + str(self.directory.fd) + "/" + leaf

    def seed(self, scope, path):
        self.current()
        leaf = next((name for name in _LEAVES if self.path(name) == path), None)
        if scope not in self.active or leaf not in (scope + ".catalog", scope + ".full") \
                or leaf in self.scratch:
            _refuse("operation-seed-path")
        os = self.owner["os"]
        descriptor = os.open(leaf, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=self.directory.fd)
        info = os.fstat(descriptor)
        self.scratch[leaf] = (descriptor, (info.st_dev, info.st_ino))
        raw = memoryview(self.sources[scope].raw)
        while raw:
            written = os.write(descriptor, raw)
            if written <= 0:
                _refuse("operation-seed-short-write")
            raw = raw[written:]
        os.fsync(descriptor)
        self.current()

    def _wire(self, value):
        maximum = self.owner["MAX_STATE_JSON_BYTES"]
        count = _native._size(value, maximum)
        raw = self.owner["json"].dumps(value, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(raw) != count:
            _refuse("capture-byte-count")
        return raw

    def _image(self, raw):
        if type(raw) is not bytes or len(raw) > self.owner["MAX_JOURNAL_CURSOR_BYTES"]:
            _refuse("cursor-image-capacity")
        encoded = base64.b64encode(raw).decode("ascii")
        value = {"raw_base64": encoded, "raw_bytes": len(raw), "raw_sha256": "0" * 64}
        _native._size(value, self.owner["MAX_STATE_JSON_BYTES"])
        value["raw_sha256"] = self.owner["hashlib"].sha256(raw).hexdigest()
        return value

    def finish(self, scope, catalog, processed_count):
        self.current()
        if scope not in self.active or type(catalog) is not list \
                or type(processed_count) is not int or not 0 <= processed_count <= len(catalog):
            _refuse("capture-prefix")
        _native._size(catalog, self.owner["MAX_STATE_JSON_BYTES"])
        for cursor in catalog:
            if self.owner["_journal_catalog_cursor"]({"__CURSOR": cursor}) != cursor:
                _refuse("capture-catalog")
        if len(catalog) != len(set(catalog)):
            _refuse("capture-catalog-duplicate")
        source = self.sources[scope]
        target = source.raw if not processed_count else catalog[processed_count - 1].encode("utf-8")
        before = None if source.original is None else {
            "generation": dict(source.original), **self._image(source.raw)}
        row = {"scope": scope, "cursor_name": source.name,
               "metadata_only": self.active[scope], "before": before,
               "target": self._image(target), "catalog": list(catalog),
               "processed_count": processed_count}
        original = self._wire(row)
        detached = self.owner["copy"].deepcopy(row)
        if self._wire(row) != original or self._wire(detached) != original:
            _refuse("scope-result-copy-change")
        self.current()
        self.rows[scope] = row
        del self.active[scope]
        return detached

    def result(self):
        self.current()
        if self.active or set(self.rows) != set(_SCOPES):
            _refuse("incomplete-capture")
        result = {"schema": "sia-journal-cursor-capture-v1", "status": "captured-not-acknowledged",
                  "operation_id": self.operation_id, "cursors": [self.rows[scope] for scope in _SCOPES],
                  "non_claims": list(NON_CLAIMS), "capture_sha256": "0" * 64}
        # Complete receipt capacity is admitted before its digest/copy callbacks.
        original = self._wire(result)
        body = {key: value for key, value in result.items() if key != "capture_sha256"}
        wire = self._wire(body)
        actual = self.owner["hashlib"].sha256(wire).hexdigest()
        if self._wire(result) != original or self._wire(body) != wire:
            _refuse("capture-digest-change")
        result["capture_sha256"] = actual
        original = self._wire(result)
        detached = self.owner["copy"].deepcopy(result)
        if self._wire(result) != original or self._wire(detached) != original:
            _refuse("capture-result-copy-change")
        self.current()
        return detached

    def abort(self):
        self.failed = True

    def close(self):
        if self.closed:
            return
        os = self.owner["os"]
        try:
            # Cleanup uses only held-directory children whose original inode
            # is still named. A replacement is not ours to remove.
            if self.directory is not None:
                for leaf, (descriptor, identity) in self.scratch.items():
                    try:
                        held = os.fstat(descriptor)
                        named = os.stat(leaf, dir_fd=self.directory.fd, follow_symlinks=False)
                        if (held.st_dev, held.st_ino) == identity \
                                and (named.st_dev, named.st_ino) == identity \
                                and stat.S_ISREG(named.st_mode):
                            os.unlink(leaf, dir_fd=self.directory.fd)
                    except OSError:
                        pass
                    finally:
                        os.close(descriptor)
                self.scratch.clear()
            for cursor in self.sources.values():
                cursor.close()
            if self.source_directory is not None:
                self.source_directory.close()
            if self.directory is not None:
                self.directory.close()
        finally:
            self.closed = True
