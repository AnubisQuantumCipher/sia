"""Durable, bounded output intent/attempt/completion journal.

This is a controller primitive, not CLI dispatch or pulse acknowledgment.
The caller supplies a committed ranked plan, an explicit epoch, the entire
rendered body, a binary sink and a clock. No legacy touch record supplies
missing output history. Nothing in this module deletes or acknowledges a
record. An incomplete attempt cannot be retried as a fresh emission.
"""

import base64
import contextlib
import copy
import fcntl
import hashlib
import os
import re
import stat

import sialiveloop as live
import siaqueue as queue


NON_CLAIMS = (
    "A reservation is intended output, not a delivery; an attempted output without a complete record has an unknown outcome and prevents complete epoch history.",
    "write-all-and-flush-returned records the supplied binary sink's successful calls, not human receipt, reading, understanding, downstream MCP forwarding or successful use.",
    "The pure supplied-bytes-admitted-not-observed-output-v1 record retains its original boundary; only this controller envelope records the write and flush sequence.",
    "A retained completion is readmitted from immutable supplied records, not a fresh observation of historical output or proof against hostile same-user mutation.",
    "The caller supplies committed state, source authority, epoch completeness and the clock; this journal does not establish them or reconstruct legacy touch tails.",
    "Admission reserves complete terminal records and staging capacity without eviction; resource exhaustion refuses rather than omitting history.",
    "No corpus publication, pulse consumption, acknowledgment, live CLI deployment, JACKAL assurance, biological cognition or held-out win is established here.",
    "All complete rank-plan, source, pure-delivery and live-loop nonclaims remain controlling.",
)
_LIMITS = {
    "max_document_bytes": live.MAX_INPUT_BYTES,
    "max_body_bytes": live.MAX_CONTENT_BYTES,
    "max_pending_bytes": queue.MAX_PENDING_BYTES,
    "max_requests": queue.MAX_PENDING_REQUESTS,
    "max_scan_entries": queue.MAX_QUEUE_SCAN_ENTRIES,
}
_INTENT = {
    "schema", "id", "epoch_id", "consumer", "ranked", "rank_sha256",
    "emitted_row_refs", "output_scope", "output_utf8_base64", "output_bytes",
    "output_sha256", "non_claims",
}
_RESERVATION = {"schema", "status", "intent", "intent_sha256", "non_claims", "reservation_sha256"}
_ATTEMPT = {"schema", "id", "epoch_id", "intent_sha256", "non_claims", "attempt_sha256"}
_COMPLETION = {"schema", "status", "intent_sha256", "record", "boundary", "non_claims", "completion_sha256"}
_ID = re.compile(r"[0-9a-f]{32}")
_LEAF = re.compile(r"([0-9a-f]{32})\.(intent|attempt|complete)\.json")
_STAGING = ".publish"
_STAT = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
_ERRORS = (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError,
           RuntimeError, OverflowError, RecursionError)


class DeliveryJournalRefusal(ValueError):
    def __init__(self, reason, output_state="not-started", upstream_non_claims=()):
        self.reason = reason
        self.output_state = output_state
        self.non_claims = list(NON_CLAIMS)
        self.upstream_non_claims = upstream_non_claims
        super().__init__("delivery journal refused: " + reason)


def _fail(reason):
    raise DeliveryJournalRefusal(reason)


def _raise(exc, phase):
    reason = exc.reason if isinstance(exc, DeliveryJournalRefusal) else str(exc)
    raise DeliveryJournalRefusal(reason, phase, {
        "non_claims": getattr(exc, "non_claims", []),
        "upstream_non_claims": getattr(exc, "upstream_non_claims", []),
    }) from exc


def _limits(value):
    live._keys(value, set(_LIMITS), "journal-limits")
    if any(type(value[key]) is not int or not 0 < value[key] <= ceiling
           for key, ceiling in _LIMITS.items()):
        _fail("journal-limit-outside-declared-ceiling")


def _wire(value, limits):
    # Include the final newline in the original individual file ceiling.
    raw = live._canonical(value, limits["max_document_bytes"])
    if len(raw) >= limits["max_document_bytes"]:
        _fail("complete-document-wire-capacity")
    return raw + b"\n"


def _signed(value, field):
    return {**value, field: live._sha(value)}


def _same(left, right, limits):
    # Ordinary Python equality conflates Boolean, integer and float values.
    # These joins preserve the canonical bytes of the entire typed record.
    return _wire(left, limits) == _wire(right, limits)


def _identity(value):
    return tuple(getattr(value, key) for key in _STAT)


def _directory_identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid)


def _request_id(value):
    if type(value) is not str or _ID.fullmatch(value) is None:
        _fail("request-id-not-canonical-uuid-hex")


def _body(encoded, count, digest, limits):
    if type(encoded) is not str or not live._integer(count, limits["max_body_bytes"]) \
            or not live._digest(digest):
        _fail("output-body-contract")
    padding = 2 if encoded.endswith("==") else 1 if encoded.endswith("=") else 0
    if len(encoded) % 4 or len(encoded) // 4 * 3 - padding != count:
        _fail("output-representation-capacity")
    raw = base64.b64decode(encoded, validate=True)
    raw.decode("utf-8", "strict")
    if len(raw) != count or base64.b64encode(raw).decode("ascii") != encoded \
            or hashlib.sha256(raw).hexdigest() != digest:
        _fail("output-body-binding")
    return raw


def _rank_versions(ranked):
    policy = ranked["policy"]
    live._policy(policy)
    pages = ranked["versions"]
    if type(pages) is not list or len(pages) > policy["limits"]["max_versions"]:
        _fail("ranked-version-capacity")
    seen = set()
    for page in pages:
        live._keys(page, live._PAGE_KEYS, "ranked-version")
        if not live._token(page["subject"], live.activation.MAX_SUBJECT_BYTES, live._SUBJECT) \
                or type(page["origin"]) is not str or page["origin"] not in live._ORIGINS \
                or type(page["content"]) is not str \
                or any(not live._digest(page[key]) for key in
                       ("source_sha256", "content_sha256", "version_sha256")):
            _fail("ranked-version-contract")
        live.workspace._text_length(page["content"], policy["limits"]["max_content_bytes"])
        if page["version_sha256"] in seen \
                or hashlib.sha256(page["content"].encode("utf-8")).hexdigest() != page["content_sha256"] \
                or live._version(page) != page["version_sha256"]:
            _fail("ranked-immutable-version-binding")
        seen.add(page["version_sha256"])
    if [page["version_sha256"] for page in pages] != list(dict.fromkeys(
            row["version_sha256"] for row in ranked["rows"])):
        _fail("ranked-version-roster-join")


def _pure(intent, body, completed_at):
    return live.complete_delivery(
        ranked=intent["ranked"], expected_ranked_sha256=intent["rank_sha256"],
        emitted_row_refs=intent["emitted_row_refs"], output_utf8=body,
        request_id=intent["id"], completed_at=completed_at)


def _admit_intent(intent, limits):
    live._size(intent, limits["max_document_bytes"])
    live._keys(intent, _INTENT, "delivery-intent")
    _request_id(intent["id"])
    if intent["schema"] != "sia-live-delivery-intent-v1" \
            or intent["non_claims"] != list(NON_CLAIMS) \
            or type(intent["consumer"]) is not str or intent["consumer"] not in {"cli.ask", "cli.recall"} \
            or not live._token(intent["epoch_id"]) \
            or intent["epoch_id"] != intent["ranked"]["epoch_id"] \
            or intent["output_scope"] != live.BODY_SCOPE:
        _fail("delivery-intent-contract")
    _rank_versions(intent["ranked"])
    body = _body(intent["output_utf8_base64"], intent["output_bytes"], intent["output_sha256"], limits)
    # A domain admission at the plan's own supplied clock, not a completion
    # observation. This value is never published as a completed record.
    _pure(intent, body, intent["ranked"]["observed_at"])
    return body


def _reservation(intent):
    return _signed({"schema": "sia-live-delivery-reservation-v1", "status": "reserved",
                    "intent": intent, "intent_sha256": live._sha(intent),
                    "non_claims": list(NON_CLAIMS)}, "reservation_sha256")


def _attempt(intent):
    return _signed({"schema": "sia-live-delivery-attempt-v1", "id": intent["id"],
                    "epoch_id": intent["epoch_id"], "intent_sha256": live._sha(intent),
                    "non_claims": list(NON_CLAIMS)}, "attempt_sha256")


def _completion(intent, record):
    return _signed({"schema": "sia-live-delivery-completion-v1", "status": "service-output-completed",
                    "intent_sha256": live._sha(intent), "record": record,
                    "boundary": "write-all-and-flush-returned", "non_claims": list(NON_CLAIMS)},
                   "completion_sha256")


def _terminal(intent, limits):
    body = _admit_intent(intent, limits)
    # Fixed-width digests and the largest admitted integer clock reserve the
    # entire future completion wire before output, without reading a clock.
    template = _completion(intent, _pure(intent, body, live.MAX_SAFE_INTEGER))
    wires = [_wire(intent, limits), _wire(_attempt(intent), limits), _wire(template, limits)]
    _wire(_reservation(intent), limits)
    return sum(map(len, wires)), max(map(len, wires))


class _Directory:
    def __init__(self, path):
        if type(path) is not str or not os.path.isabs(path) or os.path.normpath(path) != path \
                or path == "/" or "\x00" in path or ".gbrain" in path.split("/"):
            _fail("journal-directory-path")
        self.path, self.chain = path, []
        self.fd = None
        try:
            parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            self.chain.append((None, "", parent, None))
            self.chain[-1] = (None, "", parent, _directory_identity(os.fstat(parent)))
            for part in path.split("/")[1:]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                                dir_fd=parent)
                self.chain.append((parent, part, child, None))
                self.chain[-1] = (parent, part, child, _directory_identity(os.fstat(child)))
                parent = child
            self.fd = parent
            info = os.fstat(self.fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                _fail("journal-directory-not-owner-private")
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.current()
        except BaseException:
            self.close()
            raise

    def current(self):
        for parent, name, fd, identity in self.chain:
            if _directory_identity(os.fstat(fd)) != identity:
                _fail("journal-directory-descriptor-changed")
            if parent is not None:
                named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if _directory_identity(named) != identity:
                    _fail("journal-directory-name-changed")

    def close(self):
        for _parent, _name, fd, _identity_value in reversed(self.chain):
            os.close(fd)
        self.chain.clear()


class _File:
    def __init__(self, directory, name, maximum):
        self.directory, self.name = directory, name
        self.fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                          dir_fd=directory.fd)
        try:
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 \
                    or not 0 <= info.st_size <= maximum:
                _fail("journal-file-not-bounded-private-single-link")
            self.generation = _identity(info)
            self.raw = os.pread(self.fd, info.st_size + 1, 0)
            if len(self.raw) != info.st_size:
                _fail("journal-file-read-size-changed")
            self.current()
        except BaseException:
            os.close(self.fd)
            raise

    def current(self):
        self.directory.current()
        if _identity(os.fstat(self.fd)) != self.generation \
                or _identity(os.stat(self.name, dir_fd=self.directory.fd, follow_symlinks=False)) != self.generation:
            _fail("journal-authoritative-file-generation-changed")

    def close(self):
        os.close(self.fd)


def _infrastructure(directory, limits):
    try:
        info = os.stat(_STAGING, dir_fd=directory.fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        _fail("journal-staging-not-owner-private")
    descriptor = os.open(_STAGING, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=directory.fd)
    try:
        with os.scandir(descriptor) as entries:
            seen = set()
            for entry in entries:
                if entry.name not in {queue.STAGING_LOCK_NAME, queue.STAGING_PAYLOAD_NAME} or entry.name in seen:
                    _fail("journal-staging-entry-roster")
                seen.add(entry.name)
                meta = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid() \
                        or stat.S_IMODE(meta.st_mode) != 0o600 or meta.st_nlink != 1 \
                        or meta.st_size > limits["max_document_bytes"] \
                        or entry.name == queue.STAGING_LOCK_NAME and meta.st_size != 0:
                    _fail("journal-staging-file-contract")
        if _directory_identity(os.fstat(descriptor)) != _directory_identity(info) \
                or _directory_identity(os.stat(_STAGING, dir_fd=directory.fd, follow_symlinks=False)) \
                != _directory_identity(info):
            _fail("journal-staging-generation-changed")
    finally:
        os.close(descriptor)


class _Snapshot:
    def __init__(self, directory, epoch_id, limits, stack):
        self.directory, self.files, self.records = directory, [], {}
        directory.current()
        before = _identity(os.fstat(directory.fd))
        names, total = [], 0
        with os.scandir(directory.fd) as entries:
            for entry in entries:
                if len(names) >= limits["max_scan_entries"]:
                    _fail("journal-scan-capacity")
                names.append(entry.name)
                if entry.name == _STAGING:
                    continue
                match = _LEAF.fullmatch(entry.name)
                if match is None:
                    _fail("journal-unknown-entry")
                info = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_size > limits["max_document_bytes"] \
                        or info.st_size > limits["max_pending_bytes"] - total:
                    _fail("journal-physical-roster-capacity")
                total += info.st_size
        _infrastructure(directory, limits)
        for name in sorted(names):
            if name == _STAGING:
                continue
            match = _LEAF.fullmatch(name)
            source = _File(directory, name, limits["max_document_bytes"])
            self.files.append(source)
            stack.callback(source.close)
            value = queue.strict_json_loads(source.raw)
            if _wire(value, limits) != source.raw:
                _fail("journal-wire-not-canonical")
            request_id, kind = match.groups()
            self.records.setdefault(request_id, {})[kind] = value
        for request_id, rows in self.records.items():
            if "intent" not in rows or "complete" in rows and "attempt" not in rows:
                _fail("journal-orphan-record")
            intent = rows["intent"]
            body = _admit_intent(intent, limits)
            if intent["id"] != request_id or intent["epoch_id"] != epoch_id:
                _fail("journal-record-epoch-or-name-binding")
            if "attempt" in rows:
                live._keys(rows["attempt"], _ATTEMPT, "journal-attempt")
                if not _same(rows["attempt"], _attempt(intent), limits):
                    _fail("journal-attempt-intent-binding")
            if "complete" in rows:
                complete = rows["complete"]
                live._keys(complete, _COMPLETION, "journal-completion")
                replay = _completion(intent, _pure(intent, body, complete["record"]["completed_at"]))
                if not _same(complete, replay, limits):
                    _fail("journal-completion-replay-binding")
        self._capacity(limits)
        if _identity(os.fstat(directory.fd)) != before:
            _fail("journal-directory-changed-during-scan")
        self.generation = before
        self.current()

    def _capacity(self, limits, addition=None):
        intents = [rows["intent"] for rows in self.records.values()]
        if addition is not None:
            intents.append(addition)
        if len(intents) > limits["max_requests"] or len(intents) * 3 + 1 > limits["max_scan_entries"]:
            _fail("journal-terminal-file-slot-capacity")
        total, staging = 0, 0
        for intent in intents:
            size, maximum = _terminal(intent, limits)
            total += size
            staging = max(staging, maximum)
            if total + staging > limits["max_pending_bytes"]:
                _fail("journal-complete-terminal-byte-capacity")

    def current(self, *, entries=True):
        self.directory.current()
        for source in self.files:
            source.current()
        if entries and _identity(os.fstat(self.directory.fd)) != self.generation:
            _fail("journal-roster-generation-changed")


def _publish(directory, name, value, limits):
    directory.current()
    _infrastructure(directory, limits)
    raw = _wire(value, limits)
    queue.fixed_atomic_publish(os.path.join(directory.path, name), raw, exclusive=True,
                               staging_dir=os.path.join(directory.path, _STAGING), nonblocking=True,
                               destination_dir_fd=directory.fd)
    directory.current()
    with contextlib.closing(_File(directory, name, limits["max_document_bytes"])) as written:
        if written.raw != raw:
            _fail("journal-published-byte-readback")
        written.current()
    _infrastructure(directory, limits)


def _new_intent(*, ranked, expected_ranked_sha256, emitted_row_refs,
                output_utf8, request_id, consumer, limits):
    """Share the unchanged v1 intent and terminal-capacity admission."""
    _limits(limits)
    live._size({"ranked": ranked, "refs": emitted_row_refs, "id": request_id,
                "consumer": consumer}, limits["max_document_bytes"])
    if type(output_utf8) is not bytes or len(output_utf8) > limits["max_body_bytes"]:
        _fail("supplied-output-byte-capacity")
    output_utf8.decode("utf-8", "strict")
    intent = {"schema": "sia-live-delivery-intent-v1", "id": request_id,
              "epoch_id": ranked["epoch_id"], "consumer": consumer,
              "ranked": ranked, "rank_sha256": expected_ranked_sha256,
              "emitted_row_refs": emitted_row_refs, "output_scope": live.BODY_SCOPE,
              "output_utf8_base64": base64.b64encode(output_utf8).decode("ascii"),
              "output_bytes": len(output_utf8), "output_sha256": hashlib.sha256(output_utf8).hexdigest(),
              "non_claims": list(NON_CLAIMS)}
    _terminal(intent, limits)
    return intent


def _delivery_inputs(reservation, expected_reservation_sha256, limits):
    """Admit the same complete reservation for short or held transactions."""
    _limits(limits)
    live._size(reservation, limits["max_document_bytes"])
    live._keys(reservation, _RESERVATION, "delivery-reservation")
    if reservation["schema"] != "sia-live-delivery-reservation-v1" \
            or reservation["status"] != "reserved" or reservation["non_claims"] != list(NON_CLAIMS) \
            or not live._digest(expected_reservation_sha256) \
            or reservation["reservation_sha256"] != expected_reservation_sha256 \
            or live._own(reservation, "reservation_sha256") != expected_reservation_sha256 \
            or live._sha(reservation["intent"]) != reservation["intent_sha256"]:
        _fail("independent-reservation-binding")
    intent = copy.deepcopy(reservation["intent"])
    body = _admit_intent(intent, limits)
    _terminal(intent, limits)
    return intent, body


def reserve_delivery(*, directory, ranked, expected_ranked_sha256, emitted_row_refs,
                     output_utf8, request_id, consumer, limits):
    try:
        intent = _new_intent(
            ranked=ranked, expected_ranked_sha256=expected_ranked_sha256,
            emitted_row_refs=emitted_row_refs, output_utf8=output_utf8,
            request_id=request_id, consumer=consumer, limits=limits)
        intent = copy.deepcopy(intent)
        result = _reservation(intent)
        _wire(result, limits)
        with contextlib.ExitStack() as stack:
            owned = _Directory(directory)
            stack.callback(owned.close)
            before = _Snapshot(owned, intent["epoch_id"], limits, stack)
            prior = before.records.get(request_id)
            if prior is not None:
                if not _same(prior["intent"], intent, limits):
                    _fail("conflicting-request-id-reuse")
            else:
                before._capacity(limits, addition=intent)
            before.current()
            # Exact retries also close a possible prior directory-fsync gap.
            _publish(owned, request_id + ".intent.json", intent, limits)
            before.current(entries=False)
            final = _Snapshot(owned, intent["epoch_id"], limits, stack)
            if not _same(final.records[request_id]["intent"], intent, limits):
                _fail("intent-final-readback")
            result = copy.deepcopy(result)
            final.current()
            return result
    except _ERRORS as exc:
        _raise(exc, "not-started")


def deliver_reserved(*, directory, reservation, expected_reservation_sha256,
                     binary_sink, clock, limits):
    phase = "not-started"
    try:
        intent, body = _delivery_inputs(reservation, expected_reservation_sha256, limits)
        request_id = intent["id"]
        with contextlib.ExitStack() as stack:
            owned = _Directory(directory)
            stack.callback(owned.close)
            before = _Snapshot(owned, intent["epoch_id"], limits, stack)
            prior = before.records.get(request_id)
            if prior is None or not _same(prior["intent"], intent, limits):
                _fail("reserved-intent-not-durably-bound")
            if "complete" in prior:
                # Do not repeat emission or acquire a new completion clock.
                os.fsync(owned.fd)
                result = copy.deepcopy(prior["complete"])
                before.current()
                return result
            if "attempt" in prior:
                phase = "unknown"
                _fail("previous-output-attempt-outcome-unknown")
            if not callable(getattr(binary_sink, "write", None)) \
                    or not callable(getattr(binary_sink, "flush", None)) or not callable(clock):
                _fail("explicit-binary-output-and-clock-required")
            _publish(owned, request_id + ".attempt.json", _attempt(intent), limits)
            before.current(entries=False)
            attempted = _Snapshot(owned, intent["epoch_id"], limits, stack)
            attempted.current()
            phase = "unknown"
            view = memoryview(body)
            while view:
                written = binary_sink.write(view)
                if type(written) is not int or not 0 < written <= len(view):
                    _fail("output-write-return-not-a-complete-byte-count")
                view = view[written:]
            binary_sink.flush()
            phase = "completed-unrecorded"
            completed_at = clock()
            result = _completion(intent, _pure(intent, body, completed_at))
            _wire(result, limits)
            attempted.current()
            _publish(owned, request_id + ".complete.json", result, limits)
            attempted.current(entries=False)
            final = _Snapshot(owned, intent["epoch_id"], limits, stack)
            if not _same(final.records[request_id]["complete"], result, limits):
                _fail("completion-final-readback")
            result = copy.deepcopy(result)
            final.current()
            return result
    except _ERRORS as exc:
        _raise(exc, phase)


class _HeldDeliveryInspection:
    """Read-only lifetime around an already admitted descriptor snapshot."""

    def __init__(self, snapshot, epoch_id, limits):
        self._snapshot = snapshot
        self._epoch_id = epoch_id
        self._limits = limits
        self._closed = False

    def current(self):
        try:
            if self._closed:
                _fail("held-inspection-closed")
            self._snapshot.current()
        except _ERRORS as exc:
            _raise(exc, "not-started")

    def directory_identity(self):
        """Return detached native stat fields for the actually held directory.

        The whole record roster remains controlling. This observation alone
        is neither adoption authority nor permission to emit or consume output.
        """
        try:
            self.current()
            info = os.fstat(self._snapshot.directory.fd)
            result = {name: getattr(info, "st_" + name)
                      for name in ("dev", "ino", "mode", "uid", "gid")}
            self.current()
            return result
        except _ERRORS as exc:
            _raise(exc, "not-started")

    def read(self):
        try:
            self.current()
            records = [row["complete"]["record"]
                       for row in self._snapshot.records.values() if "complete" in row]
            pending = sorted(key for key, row in self._snapshot.records.items()
                             if "complete" not in row)
            records.sort(key=lambda row: (row["completed_at"], row["id"]))
            result = {"schema": "sia-live-delivery-journal-v1", "epoch_id": self._epoch_id,
                      "complete": not pending, "records": records, "pending": pending,
                      "non_claims": list(NON_CLAIMS)}
            original = _wire(result, self._limits)
            detached = copy.deepcopy(result)
            if _wire(result, self._limits) != original \
                    or _wire(detached, self._limits) != original:
                _fail("held-inspection-copy-changed")
            self.current()
            return detached
        except _ERRORS as exc:
            _raise(exc, "not-started")

    def _retire(self):
        # Never leave a usable handle pointing at file descriptors that may
        # later be recycled for a different caller's files.
        self._closed = True


def _native_directory_pin(value):
    names = ("dev", "ino", "mode", "uid", "gid")
    if type(value) is not dict or set(value) != set(names) \
            or any(type(value[name]) is not int or not 0 <= value[name] < 1 << 64
                   for name in names):
        _fail("held-writer-native-directory-identity")
    # Native stat identities are not live-loop JSON numbers. In particular,
    # never round or stringify an inode to pass the live safe-integer bound.
    return tuple(value[name] for name in names)


class _HeldDeliveryWriter:
    """One mutable journal lease; outer source authority remains a premise."""

    def __init__(self, directory, epoch_id, limits, admitted_limits, limits_raw,
                 identity, identity_pin, authority_current):
        self._directory, self._path = directory, directory.path
        self._epoch_id = epoch_id
        self._original_limits, self._limits, self._limits_raw = limits, admitted_limits, limits_raw
        self._identity, self._identity_pin = identity, identity_pin
        self._authority_current = authority_current
        self._closed, self._busy, self._phase = False, False, "not-started"
        self._snapshots = contextlib.ExitStack()
        try:
            self._basis_current()
            self._snapshot = _Snapshot(directory, epoch_id, self._limits, self._snapshots)
            self.current()
        except BaseException:
            self._close()
            raise

    def _basis_current(self):
        if self._closed:
            _fail("held-writer-closed")
        if self._directory.path != self._path \
                or _native_directory_pin(self._identity) != self._identity_pin \
                or _directory_identity(os.fstat(self._directory.fd)) != self._identity_pin:
            _fail("held-writer-directory-adoption-differs")
        if live._canonical(self._original_limits) != self._limits_raw \
                or live._canonical(self._limits) != self._limits_raw:
            _fail("held-writer-limits-changed")
        self._directory.current()

    def _check(self, *, entries=True):
        self._basis_current()
        self._snapshot.current(entries=entries)
        if self._authority_current() is not None:
            _fail("held-writer-authority-check-result")
        self._basis_current()
        self._snapshot.current(entries=entries)

    def current(self):
        phase = "not-started" if self._closed else self._phase
        try:
            self._check()
        except _ERRORS as exc:
            self._closed = True
            _raise(exc, phase)
        except BaseException:
            self._closed = True
            raise

    def read(self):
        phase = "not-started" if self._closed else self._phase
        try:
            self.current()
            reader = _HeldDeliveryInspection(self._snapshot, self._epoch_id, self._limits)
            result = reader.read()
            expected = _wire(result, self._limits)
            self.current()
            if _wire(result, self._limits) != expected:
                _fail("held-writer-read-copy-changed")
            self._basis_current()
            self._snapshot.current()
            return result
        except _ERRORS as exc:
            self._closed = True
            _raise(exc, phase)
        except BaseException:
            self._closed = True
            raise

    def _begin(self):
        if self._closed:
            _fail("held-writer-closed")
        if self._busy:
            _fail("held-writer-operation-active")
        self._phase = "not-started"
        self.current()
        self._busy = True

    def _request_current(self, value, raw):
        if _wire(value, self._limits) != raw:
            _fail("held-writer-request-changed")
        self.current()
        if _wire(value, self._limits) != raw:
            _fail("held-writer-request-changed")
        self._basis_current()
        self._snapshot.current()

    def _publish_record(self, request_id, kind, value, request, request_raw):
        """Refresh only the exact intended addition, retaining old file joins."""
        self._request_current(request, request_raw)
        before = self._snapshot
        expected = {key: {field: _wire(document, self._limits)
                          for field, document in fields.items()}
                    for key, fields in before.records.items()}
        wire = _wire(value, self._limits)
        fields = expected.setdefault(request_id, {})
        if kind in fields and fields[kind] != wire:
            _fail("held-writer-immutable-record-differs")
        fields[kind] = wire
        self._request_current(request, request_raw)
        _publish(self._directory, request_id + "." + kind + ".json", value, self._limits)
        # A successful own publication may change the roster, never an old
        # file. Keep those descriptors while admitting the exact next roster.
        self._check(entries=False)
        fresh_stack = contextlib.ExitStack()
        try:
            fresh = _Snapshot(self._directory, self._epoch_id, self._limits, fresh_stack)
            actual = {key: {field: _wire(document, self._limits)
                            for field, document in fields.items()}
                      for key, fields in fresh.records.items()}
            if actual != expected:
                _fail("held-writer-unexpected-record-progress")
            self._check(entries=False)
            if _wire(request, self._limits) != request_raw:
                _fail("held-writer-request-changed")
            fresh.current()
            old_stack = self._snapshots
            self._snapshot, self._snapshots = fresh, fresh_stack
            old_stack.close()
        except BaseException:
            fresh_stack.close()
            raise
        self._request_current(request, request_raw)

    def reserve(self, *, ranked, expected_ranked_sha256, emitted_row_refs,
                output_utf8, request_id, consumer):
        phase = "not-started"
        try:
            self._begin()
            request = {"ranked": ranked, "expected_ranked_sha256": expected_ranked_sha256,
                       "emitted_row_refs": emitted_row_refs, "request_id": request_id,
                       "consumer": consumer}
            raw = _wire(request, self._limits)
            intent = _new_intent(
                **request, output_utf8=output_utf8, limits=self._limits)
            if intent["epoch_id"] != self._epoch_id:
                _fail("held-writer-request-epoch")
            intent_raw = _wire(intent, self._limits)
            detached = copy.deepcopy(intent)
            self._request_current(request, raw)
            if _wire(intent, self._limits) != intent_raw or _wire(detached, self._limits) != intent_raw:
                _fail("held-writer-intent-copy-changed")
            prior = self._snapshot.records.get(request_id)
            if prior is not None:
                if not _same(prior["intent"], detached, self._limits):
                    _fail("conflicting-request-id-reuse")
            else:
                self._snapshot._capacity(self._limits, addition=detached)
            result = _reservation(detached)
            result_raw = _wire(result, self._limits)
            self._publish_record(request_id, "intent", detached, request, raw)
            result = copy.deepcopy(result)
            self._request_current(request, raw)
            if _wire(result, self._limits) != result_raw:
                _fail("held-writer-reservation-copy-changed")
            self._basis_current()
            self._snapshot.current()
            return result
        except _ERRORS as exc:
            self._closed = True
            _raise(exc, phase)
        except BaseException:
            self._closed = True
            raise
        finally:
            self._busy = False

    def deliver(self, *, reservation, expected_reservation_sha256, binary_sink, clock):
        phase = "not-started"
        try:
            self._begin()
            raw = _wire(reservation, self._limits)
            intent, body = _delivery_inputs(reservation, expected_reservation_sha256, self._limits)
            self._request_current(reservation, raw)
            if intent["epoch_id"] != self._epoch_id:
                _fail("held-writer-request-epoch")
            request_id = intent["id"]
            prior = self._snapshot.records.get(request_id)
            if prior is None or not _same(prior["intent"], intent, self._limits):
                _fail("reserved-intent-not-durably-bound")
            if "complete" in prior:
                retained_raw = _wire(prior["complete"], self._limits)
                self._request_current(reservation, raw)
                os.fsync(self._directory.fd)
                result = copy.deepcopy(prior["complete"])
                if _wire(result, self._limits) != retained_raw \
                        or _wire(prior["complete"], self._limits) != retained_raw:
                    _fail("held-writer-retained-completion-copy-changed")
            else:
                if "attempt" in prior:
                    phase = self._phase = "unknown"
                    _fail("previous-output-attempt-outcome-unknown")
                if not callable(getattr(binary_sink, "write", None)) \
                        or not callable(getattr(binary_sink, "flush", None)) or not callable(clock):
                    _fail("explicit-binary-output-and-clock-required")
                self._publish_record(request_id, "attempt", _attempt(intent), reservation, raw)
                phase = self._phase = "unknown"
                view = memoryview(body)
                while view:
                    self._request_current(reservation, raw)
                    written = binary_sink.write(view)
                    self._request_current(reservation, raw)
                    if type(written) is not int or not 0 < written <= len(view):
                        _fail("output-write-return-not-a-complete-byte-count")
                    view = view[written:]
                self._request_current(reservation, raw)
                binary_sink.flush()
                phase = self._phase = "completed-unrecorded"
                self._request_current(reservation, raw)
                completed_at = clock()
                self._request_current(reservation, raw)
                result = _completion(intent, _pure(intent, body, completed_at))
                _wire(result, self._limits)
                self._publish_record(request_id, "complete", result, reservation, raw)
            result_raw = _wire(result, self._limits)
            result = copy.deepcopy(result)
            self._request_current(reservation, raw)
            if _wire(result, self._limits) != result_raw:
                _fail("held-writer-completion-copy-changed")
            self._basis_current()
            self._snapshot.current()
            return result
        except _ERRORS as exc:
            self._closed = True
            _raise(exc, phase)
        except BaseException:
            self._closed = True
            raise
        finally:
            self._busy = False

    def _close(self):
        self._closed = True
        self._snapshots.close()


@contextlib.contextmanager
def hold_delivery_writer(*, directory, epoch_id, limits,
                         expected_directory_identity, authority_current):
    """Hold one existing, independently pinned journal through output.

    The caller supplies and continuously holds actual source authority. Its
    callback must return None or raise, and is checked around each effect.
    This primitive checks that premise; it does not authenticate an adoption
    or decide that a source transaction is acknowledged. Incomplete journals
    remain inspectable for exact retry; an attempted output is never repeated.

    Failed mutable methods retire the handle. Reopen actual durable records
    for retry. Normal exit revalidates; exceptional exit preserves the caller
    exception. Only owned descriptors close; no record is removed or repaired.
    """
    with contextlib.ExitStack() as stack:
        try:
            _limits(limits)
            if not live._token(epoch_id) or not callable(authority_current):
                _fail("held-writer-epoch-and-authority-required")
            pin = _native_directory_pin(expected_directory_identity)
            limits_raw = live._canonical(limits)
            admitted_limits = copy.deepcopy(limits)
            if live._canonical(limits) != limits_raw \
                    or live._canonical(admitted_limits) != limits_raw:
                _fail("held-writer-limits-changed")
            if authority_current() is not None:
                _fail("held-writer-authority-check-result")
            owned = _Directory(directory)
            stack.callback(owned.close)
            held = _HeldDeliveryWriter(owned, epoch_id, limits, admitted_limits, limits_raw,
                                       expected_directory_identity, pin, authority_current)
            stack.callback(held._close)
        except _ERRORS as exc:
            _raise(exc, "not-started")
        try:
            yield held
        except BaseException:
            raise
        else:
            held.current()
        finally:
            held._closed = True


@contextlib.contextmanager
def hold_deliveries(*, directory, epoch_id, limits):
    """Hold the whole inspected epoch through caller computation and copying.

    The caller owns source authority and any wider corpus transaction. This
    context only locks/adopts existing journal descriptors; it never creates
    a directory, reads a clock, repairs output or changes the v1 boundary.
    Normal exit revalidates. Exceptional exit preserves the caller's error
    and closes acquired descriptors without masking it with a later check.
    """
    with contextlib.ExitStack() as stack:
        try:
            _limits(limits)
            original = live._canonical(limits)
            admitted_limits = copy.deepcopy(limits)
            if live._canonical(limits) != original \
                    or live._canonical(admitted_limits) != original:
                _fail("inspection-limits-changed")
            if not live._token(epoch_id):
                _fail("explicit-inspection-epoch")
            owned = _Directory(directory)
            stack.callback(owned.close)
            snapshot = _Snapshot(owned, epoch_id, admitted_limits, stack)
            held = _HeldDeliveryInspection(snapshot, epoch_id, admitted_limits)
            held.current()
        except _ERRORS as exc:
            _raise(exc, "not-started")
        try:
            yield held
        except BaseException:
            raise
        else:
            held.current()
        finally:
            held._retire()


def inspect_deliveries(*, directory, epoch_id, limits):
    with hold_deliveries(directory=directory, epoch_id=epoch_id, limits=limits) as held:
        return held.read()
