"""Explicit-owner event render plans and byte-only, replayable publication.

This module has no bound global SIA namespace and no independent lock. The
core entrypoints hold corpus_owner throughout every callback and final check.
Readers remain the shared thought implementation, with an explicit captured
before-view for validation. No source, index, cursor or delivery is committed.
"""

import base64
import os
import re
import stat


NON_CLAIMS = [
    "This bounded render plan binds controller-supplied normalized event records and observed corpus bytes; it does not authenticate source events or establish complete machine history.",
    "Page-byte publication is not a corpus commit, index synchronization, source cursor acknowledgment, live-loop candidate admission, status/memo readiness, or observed recall delivery.",
    "Retried publication preserves the original plan and append/admission roster; a matching target is not evidence that this attempt appended the event.",
    "Original retained page bytes and event-entry content/order remain bound; title/count/timeline regeneration does not preserve the whole old file as an unchanged prefix.",
]
PLAN_KEYS = frozenset({
    "schema", "organ", "date", "input_records", "day_slugs", "appended_event_ids",
    "admissions", "pages", "read_dependencies", "non_claims", "plan_sha256"})
PAGE_KEYS = frozenset({"slug", "write", "before", "raw_utf8_base64", "raw_bytes",
                       "raw_sha256", "version_sha256", "origin"})
ADMISSION_KEYS = frozenset({"event_id", "semantic_id", "slug", "version_sha256",
                            "disposition"})
F_KEYS = ("device", "inode", "mode", "uid", "gid", "nlink", "size", "mtime_ns", "ctime_ns")
D_KEYS = ("device", "inode", "mode", "uid", "gid")
BEFORE_KEYS = frozenset({"generation", "raw_bytes", "raw_sha256"})
PAGE_BEFORE_KEYS = BEFORE_KEYS | {"raw_utf8_base64"}
_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _refuse(reason):
    error = ValueError("event page plan refused: " + reason)
    error.non_claims = list(NON_CLAIMS)
    raise error


def _text_size(value, limit, *, quoted=True):
    if type(value) is not str:
        _refuse("text-type")
    size = 2 if quoted else 0
    for character in value:
        code = ord(character)
        if 0xD800 <= code <= 0xDFFF:
            _refuse("invalid-unicode")
        if quoted and (character in '\\"' or character in "\b\f\n\r\t"):
            size += 2
        elif quoted and code < 0x20:
            size += 6
        else:
            size += 1 if code < 0x80 else 2 if code < 0x800 else 3 if code < 0x10000 else 4
        if size > limit:
            _refuse("complete-byte-capacity")
    return size


def _size(value, limit, active=None, depth=0):
    """Admission before serialization/copy/hash, retaining native stat ints."""
    if type(limit) is not int or limit <= 0 or depth > 64:
        _refuse("complete-byte-capacity")
    kind = type(value)
    if value is None:
        size = 4
    elif kind is bool:
        size = 4 if value else 5
    elif kind is int:
        if value.bit_length() > limit:
            _refuse("complete-byte-capacity")
        try:
            size = len(str(value))
        except ValueError:
            _refuse("native-integer-capacity")
    elif kind is str:
        return _text_size(value, limit)
    elif kind in (dict, list):
        if len(value) > limit:
            _refuse("complete-byte-capacity")
        active = set() if active is None else active
        identity = id(value)
        if identity in active:
            _refuse("cyclic-json")
        active.add(identity)
        try:
            size = 2
            for position, item in enumerate(value):
                size += bool(position)
                if kind is dict:
                    size += _text_size(item, limit - size) + 1
                    child = value[item]
                else:
                    child = item
                size += _size(child, limit - size, active, depth + 1)
                if size > limit:
                    _refuse("complete-byte-capacity")
        finally:
            active.remove(identity)
    else:
        _refuse("non-native-json")
    if size > limit:
        _refuse("complete-byte-capacity")
    return size


def _json(owner, value):
    _size(value, owner["MAX_STATE_JSON_BYTES"])
    return owner["json"].dumps(value, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False).encode("utf-8")


def _same(owner, first, second):
    return _json(owner, first) == _json(owner, second)


def _hash(owner, raw):
    return owner["hashlib"].sha256(raw).hexdigest()


def _generation(info):
    return dict(zip(F_KEYS, (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
                            info.st_gid, info.st_nlink, info.st_size,
                            info.st_mtime_ns, info.st_ctime_ns)))


def _directory(info):
    value = _generation(info)
    return {key: value[key] for key in D_KEYS}


def _generation_shape(value, keys):
    if type(value) is not dict or set(value) != set(keys) \
            or any(type(value[key]) is not int
                   or (key not in ("mtime_ns", "ctime_ns") and value[key] < 0)
                   for key in keys):
        _refuse("generation-shape")


def _regular(info):
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
            or info.st_nlink != 1 or info.st_mode & 0o022:
        _refuse("unsafe-source-file")


def _owned_directory(info):
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() \
            or info.st_mode & 0o022:
        _refuse("unsafe-source-directory")


def _relative(value):
    if type(value) is not str or not value or value.startswith("/") \
            or any(part in ("", ".", "..") for part in value.split("/")) \
            or "\x00" in value:
        _refuse("relative-path")
    return value


def _ancestors(relative):
    parts = relative.split("/")
    return ["/".join(parts[:index]) for index in range(1, len(parts))]


def _flags(directory=False):
    return (os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
            | (os.O_DIRECTORY if directory else 0))


class _Budget:
    def __init__(self, owner, initial):
        self.limit = owner["MAX_STATE_JSON_BYTES"]
        self.items = {"input-and-envelope": initial}
        self.total = initial
        self.check()

    def check(self):
        if type(self.limit) is not int or self.limit <= 0 or self.total > self.limit:
            _refuse("complete-byte-capacity")

    def reserve(self, key, amount):
        self.total += amount - self.items.get(key, 0)
        self.items[key] = amount
        self.check()


class _Capture:
    """Retain exact raw observations and live descriptors, never a mutable cache."""
    def __init__(self, owner, budget):
        self.owner, self.budget = owner, budget
        self.root = os.path.abspath(owner["CORPUS"])
        self.files, self.directories, self.images, self._scans = {}, {}, {}, {}
        self.root_fd = owner["_open_source_nofollow"](self.root, _flags(True))
        try:
            info = os.fstat(self.root_fd)
            _owned_directory(info)
            self.root_identity = _directory(info)
            self.named_current()
        except BaseException:
            os.close(self.root_fd)
            raise

    def close(self):
        for collection in (self.files, self.directories):
            for item in collection.values():
                if item is not None:
                    os.close(item["fd"])
        os.close(self.root_fd)

    def relative(self, path):
        path = os.path.abspath(path)
        if os.path.commonpath((path, self.root)) != self.root or path == self.root:
            _refuse("source-outside-corpus")
        return _relative(os.path.relpath(path, self.root))

    def path(self, relative):
        return os.path.join(self.root, _relative(relative))

    def anchor(self, relative, *, include=False):
        names = _ancestors(relative) + ([relative] if include else [])
        for name in names:
            if name in self.directories:
                continue
            self.budget.reserve(("directory", name), 1024 + _text_size(name, self.budget.limit))
            try:
                fd = self.owner["_open_source_nofollow"](self.path(name), _flags(True))
            except FileNotFoundError:
                self.directories[name] = None
                continue
            try:
                info = os.fstat(fd)
                _owned_directory(info)
                self.directories[name] = {"fd": fd, "identity": _directory(info),
                                          "generation": _generation(info), "entries": None}
            except BaseException:
                os.close(fd)
                raise

    def read_file(self, path, maximum, *, expected_generation=None):
        relative = self.relative(path)
        self.anchor(relative)
        if relative in self.files:
            self.check_file(path)
            item = self.files[relative]
            if item is None:
                raise FileNotFoundError(path)
            if expected_generation is not None and tuple(item["generation"][key] for key in
                    ("device", "inode", "size", "mtime_ns", "ctime_ns")) != expected_generation:
                _refuse("source-generation")
            if len(item["raw"]) > maximum:
                _refuse("source-byte-capacity")
            return item["raw"]
        self.budget.reserve(("file", relative), 1024 + _text_size(relative, self.budget.limit))
        try:
            fd = self.owner["_open_source_nofollow"](path, _flags())
        except FileNotFoundError:
            self.files[relative] = None
            raise
        try:
            before = os.fstat(fd)
            _regular(before)
            if before.st_size > maximum:
                _refuse("source-byte-capacity")
            # Reserve raw retention and both possible page byte projections
            # before allocating a read buffer or hashing source bytes.
            self.budget.reserve(("file", relative),
                                2048 + _text_size(relative, self.budget.limit)
                                + before.st_size + 2 * ((before.st_size + 2) // 3 * 4))
            if expected_generation is not None \
                    and self.owner["_file_generation"](before) != expected_generation:
                _refuse("source-generation")
            raw = os.pread(fd, maximum + 1, 0)
            if len(raw) != before.st_size or _generation(os.fstat(fd)) != _generation(before):
                _refuse("source-changed-during-read")
            self.files[relative] = {"fd": fd, "generation": _generation(before), "raw": raw}
            self.check_file(path)
        except BaseException:
            if relative not in self.files:
                os.close(fd)
            raise
        return raw

    def check_file(self, path):
        relative = self.relative(path)
        item = self.files[relative]
        try:
            named = self.owner["_source_path_identity"](path, _flags())
        except FileNotFoundError:
            if item is None:
                return
            _refuse("source-disappeared")
        if item is None:
            _refuse("source-absence-changed")
        if _generation(named) != item["generation"] \
                or _generation(os.fstat(item["fd"])) != item["generation"]:
            _refuse("source-generation-changed")

    def scan_open(self, directory, descriptor, info):
        relative = self.relative(directory)
        self.anchor(relative, include=True)
        item = self.directories[relative]
        if item is None or _directory(info) != item["identity"] \
                or _generation(info) != item["generation"]:
            _refuse("directory-generation-changed")

    def scan_entry(self, directory, name, info):
        relative = self.relative(directory)
        if type(name) is not str or name in ("", ".", "..") or "/" in name:
            _refuse("directory-entry-name")
        entry = {"name": name, "generation": _generation(info)}
        self.budget.reserve(("entry", relative, name),
                            1024 + _text_size(relative, self.budget.limit)
                            + _text_size(name, self.budget.limit))
        if name in self._scans[relative]:
            _refuse("repeated-directory-entry")
        self._scans[relative][name] = entry

    def directory_snapshot(self, directory):
        relative = self.relative(directory)
        self.anchor(relative, include=True)
        if self.directories[relative] is None:
            return []
        self._scans[relative] = {}
        result, state, inspected_total = [], None, 0
        while True:
            remaining = self.owner["MAX_EVENT_DIRECTORY_INSPECTIONS"] - inspected_total
            if remaining <= 0:
                _refuse("event-directory-capacity")
            page, complete, inspected, next_state = self.owner["_bounded_source_entries"](
                directory, state, min(remaining, self.owner["MAX_SOURCE_SCAN_ENTRIES"]),
                cleanup_legacy_atomic=False, dependency_capture=self)
            if state is not None and next_state.get("reset", False):
                _refuse("directory-generation-changed")
            inspected_total += inspected
            if inspected_total > self.owner["MAX_EVENT_LOOKUP_PAGES"]:
                _refuse("event-directory-capacity")
            result.extend(page)
            if complete:
                break
            state = next_state
        captured = [self._scans[relative][name] for name in sorted(self._scans[relative])]
        old = self.directories[relative]["entries"]
        if old is not None and not _same(self.owner, old, captured):
            _refuse("directory-roster-changed")
        self.directories[relative]["entries"] = captured
        return sorted(result, key=lambda entry: entry["name"])

    def reserve_render(self, slug, frontmatter, body):
        maximum = self.owner["MAX_EVENT_PAGE_BYTES"]
        amount = 8 + _text_size(body, self.budget.limit, quoted=False)
        for line in frontmatter:
            amount += _text_size(line, self.budget.limit, quoted=False) + 1
        if amount > maximum:
            raise ValueError("rendered event shard exceeds its byte bound")
        self.budget.reserve(("render", slug), 2048 + ((amount + 2) // 3 * 4))

    def rendered(self, slug, raw):
        self.images[slug] = raw

    def dependencies(self):
        files = []
        for relative in sorted(self.files):
            item = self.files[relative]
            before = None if item is None else {
                "generation": item["generation"], "raw_bytes": len(item["raw"]),
                "raw_sha256": _hash(self.owner, item["raw"])}
            files.append({"relative": relative, "before": before})
        directories = []
        for relative in sorted(self.directories):
            item = self.directories[relative]
            before = None if item is None else {
                "identity": item["identity"], "entries": item["entries"]}
            directories.append({"relative": relative, "before": before})
        return {"schema": "sia-event-page-read-dependencies-v1",
                "corpus_identity": self.root_identity,
                "directories": directories, "files": files}

    def named_current(self, *, exempt_files=frozenset(), exempt_directories=frozenset()):
        named = self.owner["_source_path_identity"](self.root, _flags(True))
        if _directory(named) != self.root_identity \
                or _directory(os.fstat(self.root_fd)) != self.root_identity:
            _refuse("corpus-generation-changed")
        for relative, item in self.directories.items():
            try:
                named = self.owner["_source_path_identity"](self.path(relative), _flags(True))
            except FileNotFoundError:
                if item is None:
                    continue
                _refuse("directory-disappeared")
            if item is None:
                if relative in exempt_directories:
                    continue
                _refuse("directory-absence-changed")
            if _directory(named) != item["identity"] \
                    or _directory(os.fstat(item["fd"])) != item["identity"]:
                _refuse("directory-identity-changed")
            if item["entries"] is not None and relative not in exempt_directories \
                    and _generation(named) != item["generation"]:
                _refuse("directory-generation-changed")
        for relative in self.files:
            if relative not in exempt_files:
                self.check_file(self.path(relative))

    def current(self, *, exempt_files=frozenset(), exempt_directories=frozenset()):
        self.named_current(exempt_files=exempt_files, exempt_directories=exempt_directories)
        for relative, item in self.files.items():
            if item is None or relative in exempt_files:
                continue
            raw = os.pread(item["fd"], len(item["raw"]) + 1, 0)
            if raw != item["raw"]:
                _refuse("source-bytes-changed")
            _hash(self.owner, raw)
        # No hash/copy follows this complete named roster sweep.
        self.named_current(exempt_files=exempt_files, exempt_directories=exempt_directories)


def _input_reservation(owner, organ, date, events):
    limit = owner["MAX_STATE_JSON_BYTES"]
    if type(events) is not list or len(events) > owner["MAX_SOURCE_REPLAY_EVENTS"]:
        _refuse("input-event-capacity")
    if type(organ) is not str or type(date) is not str:
        _refuse("day-identity")
    owner["_event_source_parts"]("events/" + organ + "/" + date + ".md")
    amount = 4096 + _text_size(organ, limit) + _text_size(date, limit)
    for event in events:
        if not isinstance(event, owner["Event"]) or event.organ != organ:
            _refuse("event-owner")
        amount += 2048
        for field in ("organ", "kind", "summary", "occurrence"):
            amount += 4 * _text_size(getattr(event, field), limit)
        for field in ("links", "tags"):
            values = getattr(event, field)
            if type(values) is not set or len(values) > owner["MAX_LEDGER_PENDING_RECORDS"]:
                _refuse("event-field-capacity")
            for value in values:
                amount += 4 * (_text_size(value, limit) + 1)
        if amount > limit:
            _refuse("complete-byte-capacity")
    if amount > limit:
        _refuse("complete-byte-capacity")
    return amount


def _inputs_current(owner, organ, date, events, records):
    # Re-admit the complete current caller roster before any late identity
    # hashes. A callback may have replaced a bounded field with an oversized
    # one; it must not reach the replay serializer on the old reservation.
    _input_reservation(owner, organ, date, events)
    current = [owner["_event_replay_record"](event) for event in tuple(events)]
    if not _same(owner, current, records):
        _refuse("caller-event-roster-changed")


def prepare(owner, *, organ, date, events):
    initial = _input_reservation(owner, organ, date, events)
    budget = _Budget(owner, initial)
    capture = _Capture(owner, budget)
    try:
        event_roster = tuple(events)
        records = [owner["_event_replay_record"](event) for event in event_roster]
        event_records = {id(event): record for event, record in zip(event_roster, records)}
        planned = owner["_plan_event_day_update"](
            organ, date, event_roster, dependency_capture=capture)
        selected = {shard["slug"] for shard in planned["shards"]
                    if shard["dirty"] or shard["slug"] + ".md" in capture.files}
        selected.update(slug for _event, slug in planned["admitted_pages"])
        for slug in sorted(selected):
            try:
                capture.read_file(owner["corpus_path"](slug), owner["MAX_EVENT_PAGE_BYTES"])
            except FileNotFoundError:
                if slug not in capture.images:
                    _refuse("missing-admitted-page")
        deps = capture.dependencies()
        file_rows = {row["relative"]: row["before"] for row in deps["files"]}
        pages = []
        encoder = owner.get("base64", base64)
        for slug in sorted(selected):
            original = capture.files[slug + ".md"]
            raw = capture.images.get(slug)
            write = raw is not None
            if raw is None:
                raw = original["raw"]
            projected = owner["_corpus_page_version_from_bytes"](slug=slug, raw=raw)
            before = None
            if original is not None:
                previous = owner["_corpus_page_version_from_bytes"](slug=slug, raw=original["raw"])
                if projected["origin"] != previous["origin"]:
                    _refuse("retained-page-origin-change")
                before = dict(file_rows[slug + ".md"])
                before["raw_utf8_base64"] = encoder.b64encode(original["raw"]).decode("ascii")
            pages.append({"slug": slug, "write": write, "before": before,
                          "raw_utf8_base64": encoder.b64encode(raw).decode("ascii"),
                          "raw_bytes": len(raw), "raw_sha256": projected["source_sha256"],
                          "version_sha256": projected["version_sha256"], "origin": projected["origin"]})
        versions = {page["slug"]: page["version_sha256"] for page in pages}
        _inputs_current(owner, organ, date, events, records)
        # The assignment pass retains Event object references for its legacy
        # API. Output identities come only from the original admitted records,
        # never another hash of those mutable objects after the check.
        appended = [event_records[id(event)]["event_id"] for event in planned["appended"]]
        appended_set = set(appended)
        admissions = [{"event_id": event_records[id(event)]["event_id"],
                       "semantic_id": event_records[id(event)]["semantic_id"],
                       "slug": slug, "version_sha256": versions[slug],
                       "disposition": ("appended" if event_records[id(event)]["event_id"] in appended_set
                                       else "retained-epoch" if slug.startswith("epochs/") else "retained-day")}
                      for event, slug in planned["admitted_pages"]]
        result = {"schema": "sia-event-page-render-plan-v1", "organ": organ, "date": date,
                  "input_records": records, "day_slugs": [shard["slug"] for shard in planned["shards"]],
                  "appended_event_ids": appended, "admissions": admissions, "pages": pages,
                  "read_dependencies": deps, "non_claims": list(NON_CLAIMS)}
        _size(dict(result, plan_sha256="0" * 64), owner["MAX_STATE_JSON_BYTES"])
        result["plan_sha256"] = _hash(owner, _json(owner, result))
        detached = owner["copy"].deepcopy(result)
        if not _same(owner, detached, result):
            _refuse("output-copy-change")
        _inputs_current(owner, organ, date, events, records)
        capture.current()
        return detached
    finally:
        capture.close()


def _hex(value):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        _refuse("digest-shape")


def _before_shape(value, *, page=False):
    if value is None:
        return
    expected = PAGE_BEFORE_KEYS if page else BEFORE_KEYS
    if type(value) is not dict or set(value) != expected:
        _refuse("before-shape")
    _generation_shape(value["generation"], F_KEYS)
    generation = value["generation"]
    if type(value["raw_bytes"]) is not int or value["raw_bytes"] < 0 \
            or generation["size"] != value["raw_bytes"] \
            or not stat.S_ISREG(generation["mode"]) \
            or generation["uid"] != os.geteuid() or generation["nlink"] != 1 \
            or generation["mode"] & 0o022:
        _refuse("before-generation")
    _hex(value["raw_sha256"])
    if page and type(value["raw_utf8_base64"]) is not str:
        _refuse("before-byte-encoding")


def _rows(value, keys, field):
    if type(value) is not list:
        _refuse("roster-shape")
    previous = None
    for row in value:
        if type(row) is not dict or set(row) != keys or type(row[field]) is not str:
            _refuse("roster-row-shape")
        name = row[field]
        if previous is not None and name <= previous:
            _refuse("roster-order-or-duplicate")
        previous = name


def _shape(owner, plan):
    if type(plan) is not dict or set(plan) != PLAN_KEYS \
            or plan["schema"] != "sia-event-page-render-plan-v1":
        _refuse("plan-shape")
    for key in ("organ", "date"):
        if type(plan[key]) is not str:
            _refuse("day-identity")
    owner["_event_source_parts"]("events/" + plan["organ"] + "/" + plan["date"] + ".md")
    if not _same(owner, plan["non_claims"], NON_CLAIMS):
        _refuse("nonclaims")
    _hex(plan["plan_sha256"])
    for key in ("input_records", "admissions", "appended_event_ids", "day_slugs", "pages"):
        if type(plan[key]) is not list:
            _refuse("plan-roster-shape")
    if len(plan["input_records"]) > owner["MAX_SOURCE_REPLAY_EVENTS"]:
        _refuse("input-event-capacity")
    for value in plan["appended_event_ids"]:
        _hex(value)
    for value in plan["day_slugs"]:
        if type(value) is not str:
            _refuse("day-roster-shape")
    for admission in plan["admissions"]:
        if type(admission) is not dict or set(admission) != ADMISSION_KEYS:
            _refuse("admission-shape")
        for key in ("event_id", "semantic_id", "version_sha256"):
            _hex(admission[key])
        if type(admission["slug"]) is not str \
                or admission["disposition"] not in ("appended", "retained-day", "retained-epoch"):
            _refuse("admission-shape")
    _rows(plan["pages"], PAGE_KEYS, "slug")
    for page in plan["pages"]:
        if type(page["write"]) is not bool or type(page["raw_bytes"]) is not int \
                or page["raw_bytes"] < 0 or page["raw_bytes"] > owner["MAX_EVENT_PAGE_BYTES"] \
                or type(page["raw_utf8_base64"]) is not str or type(page["origin"]) is not str:
            _refuse("page-shape")
        slug = owner["_canonical_corpus_slug"](page["slug"])
        if slug != page["slug"] or not slug.startswith((
                "events/" + plan["organ"] + "/", "epochs/" + plan["organ"] + "/")):
            _refuse("page-domain")
        if page["write"]:
            organ, date, _part = owner["_event_source_parts"](slug + ".md")
            if organ != plan["organ"] or date != plan["date"]:
                _refuse("write-domain")
        for key in ("raw_sha256", "version_sha256"):
            _hex(page[key])
        _before_shape(page["before"], page=True)
    deps = plan["read_dependencies"]
    if type(deps) is not dict or set(deps) != {"schema", "corpus_identity", "directories", "files"} \
            or deps["schema"] != "sia-event-page-read-dependencies-v1":
        _refuse("dependency-shape")
    _generation_shape(deps["corpus_identity"], D_KEYS)
    for field in ("directories", "files"):
        _rows(deps[field], {"relative", "before"}, "relative")
        for row in deps[field]:
            _relative(row["relative"])
            before = row["before"]
            if field == "files":
                _before_shape(before)
            elif before is not None:
                if type(before) is not dict or set(before) != {"identity", "entries"}:
                    _refuse("directory-before-shape")
                _generation_shape(before["identity"], D_KEYS)
                if not stat.S_ISDIR(before["identity"]["mode"]) \
                        or before["identity"]["uid"] != os.geteuid() \
                        or before["identity"]["mode"] & 0o022:
                    _refuse("directory-before-identity")
                if before["entries"] is not None:
                    _rows(before["entries"], {"name", "generation"}, "name")
                    for entry in before["entries"]:
                        if entry["name"] in ("", ".", "..") or "/" in entry["name"] or "\x00" in entry["name"]:
                            _refuse("directory-entry-name")
                        _generation_shape(entry["generation"], F_KEYS)


def _decode(owner, value):
    encoder = owner.get("base64", base64)
    raw = encoder.b64decode(value["raw_utf8_base64"], validate=True)
    if len(raw) != value["raw_bytes"] or len(raw) > owner["MAX_EVENT_PAGE_BYTES"] \
            or encoder.b64encode(raw).decode("ascii") != value["raw_utf8_base64"] \
            or _hash(owner, raw) != value["raw_sha256"]:
        _refuse("page-byte-binding")
    raw.decode("utf-8", errors="strict")
    return raw


def _images(owner, plan):
    files = {row["relative"]: row["before"] for row in plan["read_dependencies"]["files"]}
    result = {}
    for page in plan["pages"]:
        relative = page["slug"] + ".md"
        if relative not in files:
            _refuse("missing-page-dependency")
        before = page["before"]
        projection = None if before is None else {key: before[key] for key in BEFORE_KEYS}
        if not _same(owner, projection, files[relative]):
            _refuse("before-dependency-binding")
        raw = _decode(owner, page)
        old = None if before is None else _decode(owner, before)
        if not page["write"] and (old is None or old != raw):
            _refuse("nonwrite-page-byte-change")
        if page["write"] and raw == old:
            _refuse("write-without-appended-image")
        version = owner["_corpus_page_version_from_bytes"](slug=page["slug"], raw=raw)
        if version["version_sha256"] != page["version_sha256"] or version["origin"] != page["origin"]:
            _refuse("target-version-binding")
        if old is not None:
            previous = owner["_corpus_page_version_from_bytes"](slug=page["slug"], raw=old)
            if previous["origin"] != version["origin"]:
                _refuse("retained-page-origin-change")
        result[relative] = {"raw": raw, "before": old, "page": page}
    return result


def _observe(owner, plan, images, required_targets=frozenset()):
    """Admit original dependencies plus only exact declared target transitions."""
    return _observe_closure(owner, plan["read_dependencies"], images, required_targets)


def _observe_closure(owner, deps, images, required_targets=frozenset(), *,
                     allow_target_deltas=True, budget=None):
    """Observe one complete closure under an explicit original/delta policy."""
    writes = {relative for relative, image in images.items()
              if allow_target_deltas and image["page"]["write"]}
    allowed_dirs = {ancestor for relative in writes for ancestor in _ancestors(relative)}
    capture = _Capture(owner, _Budget(owner, 4096) if budget is None else budget)
    targets = set()
    try:
        if not _same(owner, capture.root_identity, deps["corpus_identity"]):
            _refuse("corpus-identity")
        for row in deps["directories"]:
            relative, before = row["relative"], row["before"]
            capture.anchor(relative, include=True)
            actual = capture.directories[relative]
            if before is None:
                if actual is not None:
                    if relative not in allowed_dirs:
                        _refuse("directory-absence-changed")
                    capture.directory_snapshot(capture.path(relative))
            else:
                if actual is None or not _same(owner, actual["identity"], before["identity"]):
                    _refuse("directory-identity")
                if before["entries"] is not None:
                    capture.directory_snapshot(capture.path(relative))
        for row in deps["files"]:
            relative, before = row["relative"], row["before"]
            try:
                raw = capture.read_file(capture.path(relative), owner["MAX_EVENT_PAGE_BYTES"])
            except FileNotFoundError:
                if before is not None or relative in required_targets:
                    _refuse("required-source-missing")
                continue
            actual = capture.files[relative]
            if relative in writes and raw == images[relative]["raw"]:
                targets.add(relative)
            elif before is None or relative in required_targets \
                    or not _same(owner, actual["generation"], before["generation"]) \
                    or len(raw) != before["raw_bytes"] or _hash(owner, raw) != before["raw_sha256"]:
                _refuse("original-source-binding")
        for row in deps["directories"]:
            relative, before = row["relative"], row["before"]
            actual = capture.directories[relative]
            if actual is None:
                continue
            if before is not None and before["entries"] is None:
                continue
            entries = actual["entries"]
            if before is None:
                for entry in entries:
                    path = relative + "/" + entry["name"]
                    if path not in writes and path not in allowed_dirs:
                        _refuse("foreign-created-directory-member")
                    if path in allowed_dirs and not stat.S_ISDIR(entry["generation"]["mode"]):
                        _refuse("created-directory-kind")
            else:
                old = {entry["name"]: entry["generation"] for entry in before["entries"]}
                now = {entry["name"]: entry["generation"] for entry in entries}
                exempt = {os.path.basename(path) for path in writes if os.path.dirname(path) == relative}
                for name in set(old) | set(now):
                    path = relative + "/" + name
                    if name in exempt and path in targets:
                        continue
                    if name not in old or name not in now or not _same(owner, old[name], now[name]):
                        _refuse("complete-directory-roster")
            for entry in entries:
                path = relative + "/" + entry["name"]
                if path in capture.files and capture.files[path] is not None \
                        and not _same(owner, entry["generation"], capture.files[path]["generation"]):
                    _refuse("scan-file-generation-binding")
        capture.current()
        return capture, targets
    except BaseException:
        capture.close()
        raise


class _BeforeView:
    """Read-only explicit provider for the original dependency view.

    Shared readers still perform all event/index/epoch validation. Only their
    byte/roster source is replaced explicitly, never their global namespace.
    The live capture independently binds unchanged files and allowed targets.
    """
    def __init__(self, owner, plan, images, live):
        self.owner, self.live = owner, live
        self.files = {row["relative"]: row["before"] for row in plan["read_dependencies"]["files"]}
        self.directories = {row["relative"]: row["before"] for row in plan["read_dependencies"]["directories"]}
        self.images = images
        self.used_files, self.used_directories, self.scanned = set(), set(), set()

    def _anchor(self, relative, *, include=False):
        for name in _ancestors(relative) + ([relative] if include else []):
            if name not in self.directories:
                _refuse("missing-ancestor-dependency")
            self.used_directories.add(name)

    def read_file(self, path, maximum, *, expected_generation=None):
        relative = self.live.relative(path)
        self._anchor(relative)
        if relative not in self.files:
            _refuse("missing-read-dependency")
        self.used_files.add(relative)
        before = self.files[relative]
        if before is None:
            raise FileNotFoundError(path)
        if expected_generation is not None and tuple(before["generation"][key] for key in
                ("device", "inode", "size", "mtime_ns", "ctime_ns")) != expected_generation:
            _refuse("before-scan-generation-binding")
        raw = self.images[relative]["before"] if relative in self.images else self.live.files[relative]["raw"]
        if raw is None or len(raw) > maximum:
            _refuse("before-source-capacity")
        return raw

    def check_file(self, path):
        relative = self.live.relative(path)
        if relative not in self.used_files:
            _refuse("unread-index-dependency")

    def directory_snapshot(self, directory):
        relative = self.live.relative(directory)
        self._anchor(relative, include=True)
        self.scanned.add(relative)
        before = self.directories[relative]
        if before is None:
            return []
        if before["entries"] is None:
            _refuse("missing-complete-scan")
        return [dict(entry["generation"], name=entry["name"]) for entry in before["entries"]]

    def complete(self):
        if self.used_files != set(self.files) or self.used_directories != set(self.directories):
            _refuse("unreplayed-dependency-roster")
        for relative, before in self.directories.items():
            if before is not None and before["entries"] is not None and relative not in self.scanned:
                _refuse("unreplayed-scan-roster")


class _TargetView:
    """Supply one already admitted target image to the native page parser."""
    def __init__(self, owner, slug, raw):
        self.path = os.path.abspath(owner["corpus_path"](slug))
        self.raw = raw

    def read_file(self, path, maximum, *, expected_generation=None):
        if os.path.abspath(path) != self.path or expected_generation is not None:
            _refuse("target-parser-source")
        if len(self.raw) > maximum:
            _refuse("target-parser-capacity")
        return self.raw


def _entries(owner, raw):
    text = raw.decode("utf-8", errors="strict")
    match = owner["FM_RE"].match(text)
    if match is None:
        _refuse("event-frontmatter")
    body = text[match.end():].split("## Timeline", 1)[0]
    if "## Log" in body:
        body = body.split("## Log", 1)[1]
    return [line for line in body.splitlines() if line.startswith("- ")]


def _semantic_join(owner, plan, images, live):
    """Validate fidelity/assignments against original readers without rendering."""
    organ, date = plan["organ"], plan["date"]
    view = _BeforeView(owner, plan, images, live)
    shards = owner["_event_day_shards"](organ, date, dependency_capture=view)
    known = {}
    legacy = set()
    for shard in shards:
        for line in shard["bullets"]:
            marker = owner["EVENT_MARKER_RE"].fullmatch(line)
            if marker is None:
                if "sia-event:" in line:
                    _refuse("malformed-retained-event-marker")
                legacy.add(line)
                continue
            event_id = marker.group("id")
            if event_id in known:
                _refuse("duplicate-retained-event")
            known[event_id] = (shard["slug"], marker.group("payload"), marker.group("semantic"))
    records, prepared, wanted = {}, [], set()
    for record in plan["input_records"]:
        event = owner["_event_from_replay_record"](record)
        if event.organ != organ or not _same(owner, owner["_event_replay_record"](event), record):
            _refuse("input-record-binding")
        event_id, semantic = record["event_id"], record["semantic_id"]
        line, payload, base_line = owner["_event_line"](event, event_id, semantic)
        if event_id in records:
            if records[event_id][0] != semantic or records[event_id][1] != payload:
                _refuse("input-occurrence-conflict")
        else:
            records[event_id] = (semantic, payload)
            prepared.append((event_id, semantic, line, payload, base_line))
        if event.occurrence and event_id not in known:
            wanted.add(event_id)
    excluded = {shard["slug"] for shard in shards} or {owner["_event_shard_slug"](organ, date, 1)}
    other = owner["_other_event_occurrences"](organ, wanted, excluded, dependency_capture=view)
    owner["_bounded_event_directory_snapshot"](
        os.path.join(owner["CORPUS"], "events", organ), dependency_capture=view)
    if [row["event_id"] for row in plan["admissions"]] != list(records):
        _refuse("complete-admission-roster")
    pages = {page["slug"]: page for page in plan["pages"]}
    additions, appended = {}, []
    prior_appended_part = None
    for values, admission in zip(prepared, plan["admissions"]):
        event_id, semantic, line, payload, base_line = values
        slug = admission["slug"]
        if slug not in pages or admission["semantic_id"] != semantic \
                or admission["version_sha256"] != pages[slug]["version_sha256"]:
            _refuse("admission-version-binding")
        if event_id in known:
            original_slug, stored_payload, stored_semantic = known[event_id]
            expected_disposition = "retained-day"
            if slug != original_slug or payload != stored_payload or semantic != stored_semantic:
                _refuse("retained-day-binding")
        elif event_id in other:
            original_slug, payload_digest, stored_semantic = other[event_id]
            expected_disposition = "retained-epoch" if original_slug.startswith("epochs/") else "retained-day"
            if slug != original_slug or owner["_event_payload_digest"](payload) != payload_digest \
                    or semantic != stored_semantic:
                _refuse("retained-occurrence-binding")
        else:
            expected_disposition = "appended"
            if base_line in legacy or not pages[slug]["write"]:
                _refuse("unwitnessed-appended-event")
            source_organ, source_date, part = owner["_event_source_parts"](slug + ".md")
            if source_organ != organ or source_date != date \
                    or (shards and part < shards[-1]["part"]) \
                    or (prior_appended_part is not None and part < prior_appended_part):
                _refuse("appended-event-order-or-domain")
            prior_appended_part = part
            additions.setdefault(slug, []).append(line)
            appended.append(event_id)
        if admission["disposition"] != expected_disposition:
            _refuse("admission-disposition")
    if plan["appended_event_ids"] != appended:
        _refuse("complete-appended-roster")
    day_parts = {}
    actual_day = set()
    for page in plan["pages"]:
        slug = page["slug"]
        relative = slug + ".md"
        try:
            view.read_file(owner["corpus_path"](slug), owner["MAX_EVENT_PAGE_BYTES"])
        except FileNotFoundError:
            if not page["write"]:
                _refuse("retained-page-absence")
        if slug.startswith("events/"):
            source_organ, source_date, part = owner["_event_source_parts"](relative)
            if source_organ != organ:
                _refuse("event-page-organ")
            if source_date == date:
                actual_day.add(slug)
                day_parts[part] = slug
        if page["write"]:
            raw, old = images[relative]["raw"], images[relative]["before"]
            target = owner["_event_page_state"](
                organ, date, part,
                dependency_capture=_TargetView(owner, slug, raw))
            before_entries = [] if old is None else _entries(owner, old)
            if not additions.get(slug) or target["bullets"] != before_entries + additions[slug]:
                _refuse("exact-event-entry-preservation")
    if any(shard["slug"] not in actual_day for shard in shards):
        _refuse("omitted-existing-day-page")
    ordered_parts = sorted(day_parts)
    if any(part != position for position, part in enumerate(ordered_parts, start=1)):
        _refuse("day-shard-contiguity")
    expected_days = [day_parts[part] for part in ordered_parts] or [owner["_event_shard_slug"](organ, date, 1)]
    if plan["day_slugs"] != expected_days:
        _refuse("day-shard-roster")
    if set(pages) != actual_day | {row["slug"] for row in plan["admissions"]}:
        _refuse("extra-or-missing-target-page")
    view.complete()


def _result(plan):
    return {"schema": "sia-event-page-render-publication-v1", "status": "page-bytes-published",
            "plan_sha256": plan["plan_sha256"], "day_slugs": plan["day_slugs"],
            "appended_event_ids": plan["appended_event_ids"], "admissions": plan["admissions"],
            "page_versions": [{key: page[key] for key in ("slug", "raw_sha256", "version_sha256")}
                              for page in plan["pages"]], "non_claims": plan["non_claims"]}


def _publish_images(owner, deps, images, write_paths, state, *, shared_budget=None):
    """The single guarded write engine; state always owns the latest handles.

    Individual publication retains its original observation budget behavior.
    Batch publication supplies one union budget through every observation,
    never a fresh allowance per member. No result is materialized here.
    """
    for relative in write_paths:
        live, targets = state["live"], state["targets"]
        if relative in targets:
            continue
        live.current()
        owner["_before_corpus_mutation"]()
        live.current()
        path = owner["corpus_path"](images[relative]["page"]["slug"])
        owner["ensure_durable_directory"](os.path.dirname(path))
        affected_dirs = frozenset(_ancestors(relative))
        live.current(exempt_directories=affected_dirs)
        interim, interim_targets = _observe_closure(
            owner, deps, images, targets, budget=shared_budget)
        try:
            live.named_current(exempt_directories=affected_dirs)
        except BaseException:
            interim.close()
            raise
        live.close()
        live, targets = interim, interim_targets
        state.update(live=live, targets=targets)
        live.current()
        owner["atomic_write"](path, images[relative]["raw"].decode("utf-8", errors="strict"))
        live.current(exempt_files=frozenset({relative}), exempt_directories=affected_dirs)
        refreshed, refreshed_targets = _observe_closure(
            owner, deps, images, targets | {relative}, budget=shared_budget)
        try:
            live.named_current(exempt_files=frozenset({relative}), exempt_directories=affected_dirs)
        except BaseException:
            refreshed.close()
            raise
        live.close()
        state.update(live=refreshed, targets=refreshed_targets)


def publish(owner, *, plan, expected_plan_sha256):
    # The complete original document includes all before/target/dependency
    # rosters. Admit it, and the complete result, before decoding or copying.
    _size(plan, owner["MAX_STATE_JSON_BYTES"])
    _shape(owner, plan)
    _size(_result(plan), owner["MAX_STATE_JSON_BYTES"])
    _hex(expected_plan_sha256)
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if plan["plan_sha256"] != expected_plan_sha256 or _hash(owner, _json(owner, body)) != expected_plan_sha256:
        _refuse("external-plan-pin")
    original = _json(owner, plan)
    admitted = owner["copy"].deepcopy(plan)
    if _json(owner, admitted) != original:
        _refuse("input-copy-change")
    images = _images(owner, admitted)
    live, targets = _observe(owner, admitted, images)
    state = {"live": live, "targets": targets}
    try:
        _semantic_join(owner, admitted, images, live)
        live.current()
        _publish_images(owner, admitted["read_dependencies"], images,
                        [page["slug"] + ".md" for page in admitted["pages"] if page["write"]], state)
        result = _result(admitted)
        _size(result, owner["MAX_STATE_JSON_BYTES"])
        detached = owner["copy"].deepcopy(result)
        if not _same(owner, detached, result) or _json(owner, plan) != original:
            _refuse("result-or-input-change")
        # All result materialization and serialization precedes this final
        # hash-then-whole-roster sweep. Only returning/closing follows it.
        state["live"].current()
        return detached
    finally:
        state["live"].close()


BATCH_KEYS = frozenset({"schema", "organ", "members", "read_dependencies",
                        "write_order", "new_directories", "non_claims", "batch_sha256"})
BATCH_NON_CLAIMS = NON_CLAIMS + [
    "Batch composition does not resolve shared-page write conflicts or reassign event occurrences; conflicting member targets require a separately admitted original assignment cut.",
]


def _member_structure(owner, plans):
    """Complete cheap member/count/page gates before any member digest work."""
    _size(plans, owner["MAX_STATE_JSON_BYTES"])
    if type(plans) is not list or not plans:
        _refuse("batch-member-roster")
    total_events = 0
    for plan in plans:
        if type(plan) is not dict or type(plan.get("input_records")) is not list:
            _refuse("batch-member-shape")
        total_events += len(plan["input_records"])
        if total_events > owner["MAX_SOURCE_REPLAY_EVENTS"]:
            _refuse("batch-input-event-capacity")
    for plan in plans:
        _shape(owner, plan)
        for page in plan["pages"]:
            if page["before"] is not None \
                    and page["before"]["raw_bytes"] > owner["MAX_EVENT_PAGE_BYTES"]:
                _refuse("batch-before-page-capacity")
    organ = plans[0]["organ"]
    dates, identities = set(), set()
    for plan in plans:
        if plan["organ"] != organ or plan["date"] in dates \
                or plan["plan_sha256"] in identities:
            _refuse("batch-organ-day-or-member-conflict")
        dates.add(plan["date"])
        identities.add(plan["plan_sha256"])
    return sorted(plans, key=lambda plan: plan["date"])


def _member_pins(owner, plans, expected):
    if type(expected) is not list or len(expected) != len(plans):
        _refuse("batch-independent-member-pins")
    for plan, pin in zip(plans, expected):
        _hex(pin)
        if plan["plan_sha256"] != pin:
            _refuse("batch-independent-member-pins")
    # Caller order is checked above, before the deterministic output sort.
    for plan, pin in zip(plans, expected):
        body = {key: value for key, value in plan.items() if key != "plan_sha256"}
        if _hash(owner, _json(owner, body)) != pin:
            _refuse("batch-member-digest")


def _batch_body(owner, members):
    """Join original witnesses and derive effects without observing or rendering."""
    files, directories, pages, occurrences = {}, {}, {}, {}
    corpus_identity = members[0]["read_dependencies"]["corpus_identity"]
    write_order = []
    for member in members:
        deps = member["read_dependencies"]
        if not _same(owner, deps["corpus_identity"], corpus_identity):
            _refuse("batch-corpus-identity-conflict")
        for row in deps["files"]:
            relative = row["relative"]
            if relative in files and not _same(owner, files[relative], row):
                _refuse("batch-original-file-conflict")
            files[relative] = row
        for row in deps["directories"]:
            relative, before = row["relative"], row["before"]
            if relative not in directories:
                directories[relative] = row
                continue
            previous = directories[relative]["before"]
            if before is None or previous is None:
                if before is not None or previous is not None:
                    _refuse("batch-original-directory-conflict")
                continue
            if not _same(owner, previous["identity"], before["identity"]):
                _refuse("batch-original-directory-conflict")
            if previous["entries"] is None:
                directories[relative] = row
            elif before["entries"] is not None \
                    and not _same(owner, previous["entries"], before["entries"]):
                _refuse("batch-original-scan-conflict")
        for page in member["pages"]:
            relative = page["slug"] + ".md"
            prior = pages.get(relative)
            if prior is not None:
                if page["write"] or prior["write"]:
                    _refuse("batch-target-write-conflict")
                if not _same(owner, page, prior):
                    _refuse("batch-retained-target-conflict")
            pages[relative] = page
            if page["write"]:
                write_order.append({"plan_sha256": member["plan_sha256"], "slug": page["slug"]})
        for admission in member["admissions"]:
            event_id = admission["event_id"]
            previous = occurrences.get(event_id)
            if previous is not None:
                if previous["disposition"] == "appended" or admission["disposition"] == "appended":
                    _refuse("batch-occurrence-reassigned")
                if not _same(owner, previous, admission):
                    _refuse("batch-retained-occurrence-conflict")
            occurrences[event_id] = admission
    ancestors = {name for relative, page in pages.items() if page["write"]
                 for name in _ancestors(relative)}
    if not ancestors.issubset(directories):
        _refuse("batch-missing-write-ancestor")
    organ_root = "events/" + members[0]["organ"]
    if organ_root not in directories:
        _refuse("batch-missing-complete-day-scan")
    before = directories[organ_root]["before"]
    if before is not None and before["entries"] is None:
        _refuse("batch-missing-complete-day-scan")
    entries = [] if before is None else before["entries"]
    names = {entry["name"] for entry in entries}
    new_names = {os.path.basename(relative) for relative, page in pages.items()
                 if page["write"] and os.path.basename(relative) not in names}
    if len(names) + len(new_names) > owner["MAX_EVENT_LOOKUP_PAGES"] \
            or len(names) + len(new_names) > owner["MAX_EVENT_DIRECTORY_INSPECTIONS"]:
        _refuse("batch-event-directory-capacity")
    live_pages = {organ_root + "/" + entry["name"] for entry in entries
                  if stat.S_ISREG(entry["generation"]["mode"]) and entry["name"].endswith(".md")}
    planned_pages = {slug + ".md" for member in members for slug in member["day_slugs"]}
    if len(live_pages | planned_pages) > owner["MAX_EVENT_LOOKUP_PAGES"]:
        _refuse("batch-event-path-capacity")
    return {"schema": "sia-event-page-render-batch-v1", "organ": members[0]["organ"],
            "members": members,
            "read_dependencies": {"schema": "sia-event-page-read-dependencies-v1",
                                  "corpus_identity": corpus_identity,
                                  "directories": [directories[name] for name in sorted(directories)],
                                  "files": [files[name] for name in sorted(files)]},
            "write_order": write_order,
            "new_directories": sorted(name for name in ancestors if directories[name]["before"] is None),
            "non_claims": list(BATCH_NON_CLAIMS)}


def _batch_result(batch):
    return {"schema": "sia-event-page-render-batch-publication-v1",
            "status": "page-bytes-published", "batch_sha256": batch["batch_sha256"],
            "members": [_result(member) for member in batch["members"]],
            "non_claims": batch["non_claims"]}


def _batch_reservation(owner, body):
    # The enclosing document counts every retained member in full, including
    # repeated member dependencies; only the additional union deduplicates.
    bounded = dict(body, batch_sha256="0" * 64)
    _size(bounded, owner["MAX_STATE_JSON_BYTES"])
    _size(_batch_result(bounded), owner["MAX_STATE_JSON_BYTES"])


def _union_images(owner, members):
    result = {}
    for member in members:
        for relative, image in _images(owner, member).items():
            if relative not in result:
                result[relative] = image
    return result


def compose(owner, *, plans, expected_plan_sha256s):
    # The request's complete original documents and external pin roster share
    # the existing cap. No member gets a separate count or output allowance.
    request = {"plans": plans, "expected_plan_sha256s": expected_plan_sha256s}
    _size(request, owner["MAX_STATE_JSON_BYTES"])
    members = _member_structure(owner, plans)
    body = _batch_body(owner, members)
    _batch_reservation(owner, body)
    # Freeze the admitted input and derived body before the first digest
    # callback. A later member's hash may otherwise change an earlier member
    # after its check and have that changed value adopted as the baseline.
    original_request = _json(owner, request)
    original_body = _json(owner, body)
    _member_pins(owner, plans, expected_plan_sha256s)
    if _json(owner, request) != original_request or _json(owner, body) != original_body:
        _refuse("batch-input-changed-during-pins")
    admitted = owner["copy"].deepcopy(body)
    if _json(owner, admitted) != original_body or _json(owner, request) != original_request:
        _refuse("batch-input-copy-change")
    images = _union_images(owner, admitted["members"])
    budget = _Budget(owner, 4096)
    live, _targets = _observe_closure(owner, admitted["read_dependencies"], images,
                                     allow_target_deltas=False, budget=budget)
    try:
        for member in admitted["members"]:
            # The view keeps this member's exact dependency roster, but any
            # shared page is sourced from the union's original before image.
            _semantic_join(owner, member, images, live)
        admitted["batch_sha256"] = _hash(owner, _json(owner, admitted))
        detached = owner["copy"].deepcopy(admitted)
        if not _same(owner, admitted, detached) or _json(owner, request) != original_request:
            _refuse("batch-result-or-input-change")
        live.current()
        return detached
    finally:
        live.close()


def publish_batch(owner, *, batch, expected_batch_sha256):
    _size(batch, owner["MAX_STATE_JSON_BYTES"])
    if type(batch) is not dict or set(batch) != BATCH_KEYS \
            or batch["schema"] != "sia-event-page-render-batch-v1":
        _refuse("batch-shape")
    members = _member_structure(owner, batch["members"])
    body = _batch_body(owner, members)
    _batch_reservation(owner, body)
    supplied_body = {key: value for key, value in batch.items() if key != "batch_sha256"}
    if not _same(owner, supplied_body, body):
        _refuse("batch-original-union-or-effect-roster")
    _hex(expected_batch_sha256)
    _hex(batch["batch_sha256"])
    original = _json(owner, batch)
    original_body = _json(owner, body)
    if batch["batch_sha256"] != expected_batch_sha256 \
            or _hash(owner, original_body) != expected_batch_sha256:
        _refuse("external-batch-pin")
    # The independent whole-batch pin binds the original member pin roster;
    # this is validation of those bytes, not reconstruction of new authority.
    _member_pins(owner, batch["members"], [member["plan_sha256"] for member in batch["members"]])
    if _json(owner, batch) != original or _json(owner, body) != original_body:
        _refuse("batch-input-changed-during-pins")
    admitted = owner["copy"].deepcopy(batch)
    if _json(owner, admitted) != original or _json(owner, batch) != original:
        _refuse("batch-input-copy-change")
    images = _union_images(owner, admitted["members"])
    budget = _Budget(owner, 4096)
    live, targets = _observe_closure(owner, admitted["read_dependencies"], images, budget=budget)
    state = {"live": live, "targets": targets}
    try:
        for member in admitted["members"]:
            _semantic_join(owner, member, images, live)
        live.current()
        _publish_images(owner, admitted["read_dependencies"], images,
                        [row["slug"] + ".md" for row in admitted["write_order"]], state,
                        shared_budget=budget)
        result = _batch_result(admitted)
        _size(result, owner["MAX_STATE_JSON_BYTES"])
        detached = owner["copy"].deepcopy(result)
        if not _same(owner, detached, result) or _json(owner, batch) != original:
            _refuse("batch-result-or-input-change")
        state["live"].current()
        return detached
    finally:
        state["live"].close()
