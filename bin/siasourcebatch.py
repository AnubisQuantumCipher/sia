"""Descriptor-bound capture and validation of one controller source batch.

The owning core is explicit.  Capture holds the resident source and corpus
leases, observes current configuration/cursor/memo generations, invokes each
selected collector exactly once, and returns an inert batch.  It does not
publish page bytes, acknowledge a cursor, settle a refusal, stage a live
generation, or make the batch durable.

Source-v3 additionally observes an already adopted delivery epoch and its
independently held journal. It preserves the source-v2 idle contract and
returns an inert delivery wrapper, not a writer permit or consumed history.
Retained batch validation never reacquires these authority front doors.

The outer source documents use ASCII canonical JSON because they retain
native finite configuration floats and stat integers.  Nested event, page,
intake, policy, and journal documents retain their original UTF-8 canonical
serializers and validators.
"""

import base64
import contextlib
import os
import re
import stat

import siaeventintake as _intake
import siaeventplan as _pages
import siajournalcapture as _journal
import sialiveloop as _live


CONFIG_NON_CLAIMS = (
    "This receipt observes current config.json bytes or absence and an equivalent active CONFIG value; it does not recover the bytes, file generation, or optional-source probes used at module import or the original load.",
    "Runtime collector names and configuration pins describe the held effective selection; they do not establish source installation, collector success, source freshness, or completeness outside that roster.",
    "Revalidation binds observed configuration and registry state at capture boundaries; it does not establish uninterrupted immutability against concurrent or hostile same-user changes.",
    "This configuration receipt is not a source return, durable source batch, cursor acknowledgment, live publication, or cognitive win.",
)
NON_CLAIMS = (
    "Collector completion means an admitted successful return from every declared source in this attempt; bounded windows, filtering and explicit record or entry refusals do not establish complete raw source history.",
    "Normalized Events, their source-return order and duplicates are retained; native Event timestamps remain metadata and do not replace the original integer controller observation clock.",
    "Cursor changes, journal cursor images and source-refusal rows are proposed effects only; capture and staging do not acknowledge cursors, settle refusals, publish pages or a live generation, or establish readiness.",
    "A notification baseline-attempt marker is an acquisition fence, not acknowledgment; its timestamp does not replace the supplied controller observation clock.",
    "Configuration receipts and collector execution are local observations, not source truth, uninterrupted source immutability, authenticated complete machine history, or a hostile same-user sandbox.",
    "All original configuration, source-return, event-plan, closure, intake and live-policy nonclaims remain controlling; this captured batch is not cognitive authorization or a held-out win.",
)

EPOCH_KEYS = frozenset({
    "schema", "epoch_id", "started_at", "configuration",
    "expected_configuration_sha256", "source_catalog",
    "expected_source_catalog_sha256", "profile",
    "expected_profile_sha256", "live_policy",
    "expected_live_policy_sha256", "history",
    "expected_history_sha256", "predecessor", "non_claims",
})
BATCH_KEYS = frozenset({
    "schema", "status", "batch_id", "observed_at", "epoch",
    "epoch_sha256", "configuration_receipt", "source_returns",
    "cursor_proposal", "journal_proposals", "refusal_intents",
    "notification_baseline_attempt", "event_closure",
    "intake_projection", "non_claims", "batch_sha256",
})
BATCH_V2_KEYS = BATCH_KEYS | frozenset({"idle_input"})
BATCH_V3_KEYS = BATCH_V2_KEYS | frozenset({"delivery_input"})
_DELIVERY_CAPTURE_REQUEST_KEYS = frozenset({
    "memo", "admitted_status", "retained_batch", "committed", "epoch",
    "expected_epoch_sha256", "observed_at", "journal_limits",
    "expected_journal_limits_sha256", "expected_adoption_sha256",
})
# A source-v3 delivery capture request has ten separately bounded fields plus
# one structural-overhead unit. The aggregate is not one state document, while
# each member remains subject to its original state/memo ceiling.
# Arithmetic evidence: status=exact, parsed=11*16777216, exact=184549376.
# Exact rational arithmetic outside the Lean certificate chain; NOT
# formal-bounded.
MAX_DELIVERY_CAPTURE_REQUEST_DOCUMENTS = 11
MAX_DELIVERY_CAPTURE_REQUEST_BYTES = 184_549_376
CONFIG_RECEIPT_KEYS = frozenset({
    "schema", "scope", "observed_at", "config_file", "decoded_config",
    "active_config", "runtime_selection", "configuration_sha256",
    "source_catalog_sha256", "profile_sha256", "live_policy_sha256",
    "non_claims", "receipt_sha256",
})
CURSOR_KEYS = frozenset({
    "schema", "state_identity", "before", "before_value", "steps",
    "after", "after_sha256",
})
CURSOR_STEP_KEYS = frozenset({
    "source_id", "removed_keys", "set_values", "after_sha256",
})
REFUSAL_INTENT_KEYS = frozenset({
    "source_id", "record_refusals", "entry_refusals",
})
FILE_GENERATION_KEYS = (
    "device", "inode", "mode", "uid", "gid", "nlink", "size",
    "mtime_ns", "ctime_ns",
)
DIRECTORY_GENERATION_KEYS = (
    "device", "inode", "mode", "uid", "gid",
)
JOURNAL_GENERATION_KEYS = (
    "device", "inode", "mode", "uid", "nlink", "size", "mtime_ns",
    "ctime_ns",
)
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_OPERATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_REASON = re.compile(r"[a-z][a-z0-9-]*\Z")
_AUTHORITY_KEYS = frozenset({
    "source_replay_pending", "pulse_publication", "dream_publication",
    "consolidation_pending", "live_loop_pending",
    "controller_source_pending", "controller_source_live_pending",
    "controller_source_committed",
})
_COMMITTED_KEYS = frozenset({
    "source_batch_sha256", "live_generation_sha256",
    "source_effects_receipt_sha256",
})
_SUCCESSOR_PENDING_KEYS = (_AUTHORITY_KEYS - frozenset({
    "controller_source_committed",
})) | frozenset({
    "pulse_status_effects_pending", "controller_source_effects_pending",
    "controller_source_effects_committed",
})


class SourceBatchRefusal(ValueError):
    """A closed refusal that never incorporates an upstream exception text."""

    def __init__(self, reason, *, phase="admit", source_id=None, upstream=None):
        self.reason = reason
        self.phase = phase
        self.source_id = source_id
        self.non_claims = list(NON_CLAIMS)
        upstream_reason = getattr(upstream, "reason", None)
        self.upstream_reason = (upstream_reason if type(upstream_reason) is str
                                and _REASON.fullmatch(upstream_reason) else None)
        self.upstream_non_claims = list(
            getattr(upstream, "non_claims", ()))[:64]
        super().__init__("controller source batch refused: " + reason)


def refuse(reason, *, phase="admit", source_id=None, upstream=None):
    """Raise one path-free, machine-readable refusal."""
    if type(reason) is not str or _REASON.fullmatch(reason) is None:
        reason = "closed-refusal"
    if type(phase) is not str or _REASON.fullmatch(phase) is None:
        phase = "admit"
    if source_id is not None and type(source_id) is not str:
        source_id = None
    raise SourceBatchRefusal(
        reason, phase=phase, source_id=source_id, upstream=upstream)


def _delivery_capture_request_capacity(owner):
    if type(MAX_DELIVERY_CAPTURE_REQUEST_DOCUMENTS) is not int \
            or MAX_DELIVERY_CAPTURE_REQUEST_DOCUMENTS \
            != len(_DELIVERY_CAPTURE_REQUEST_KEYS) + 1 \
            or type(MAX_DELIVERY_CAPTURE_REQUEST_BYTES) is not int \
            or MAX_DELIVERY_CAPTURE_REQUEST_BYTES <= 0:
        refuse("delivery-capture-capacity-contract")
    scaled = (MAX_DELIVERY_CAPTURE_REQUEST_DOCUMENTS
              * owner["MAX_STATE_JSON_BYTES"])
    return min(scaled, MAX_DELIVERY_CAPTURE_REQUEST_BYTES)


def _admission_exception_class(exc):
    """Return one path-free class for an otherwise closed exception."""
    if isinstance(exc, UnicodeError):
        return "unicode"
    if isinstance(exc, RecursionError):
        return "recursion"
    if isinstance(exc, OSError):
        return "os"
    if isinstance(exc, KeyError):
        return "key"
    if isinstance(exc, AttributeError):
        return "attribute"
    if isinstance(exc, TypeError):
        return "type"
    if isinstance(exc, RuntimeError):
        return "runtime"
    if isinstance(exc, ValueError):
        # Preserve only the closed reason grammars owned by components in
        # this capture pipeline.  Arbitrary upstream text remains private.
        for message_prefix, reason_prefix in (
                ("event page plan refused: ", "event-page-plan-"),
                ("event live intake refused: ", "event-live-intake-"),
                ("live-loop refused: ", "live-loop-"),
                ("controller idle input refused: ", "controller-idle-"),
                ("controller delivery epoch refused: ",
                 "controller-delivery-epoch-"),
                ("controller delivery wrapper refused: ",
                 "controller-delivery-wrapper-"),
                ("delivery journal refused: ", "delivery-journal-")):
            matched = re.fullmatch(
                re.escape(message_prefix) + r"([a-z0-9-]+)", str(exc))
            if matched is not None:
                return reason_prefix + matched.group(1)
        return "value"
    return "closed"


def _keys(value, expected, reason):
    if type(value) is not dict or set(value) != set(expected) \
            or any(type(key) is not str for key in value):
        refuse(reason)


def _hex(value, reason="digest-shape"):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        refuse(reason)


def _json_size(owner, value, ceiling, *, ascii_only):
    """Count canonical JSON before allocation, copying, or hashing."""
    if type(ceiling) is not int or ceiling <= 0:
        refuse("complete-byte-capacity")
    active = set()
    total = 0

    def add(amount):
        nonlocal total
        total += amount
        if total > ceiling:
            refuse("complete-byte-capacity")

    def visit(item, depth):
        if depth > 64:
            refuse("complete-json-depth")
        kind = type(item)
        if item is None:
            add(4)
        elif kind is bool:
            add(4 if item else 5)
        elif kind is int:
            if item.bit_length() > ceiling:
                refuse("native-integer-capacity")
            try:
                add(len(str(item)))
            except ValueError:
                refuse("native-integer-capacity")
        elif kind is float:
            if not owner["math"].isfinite(item):
                refuse("nonfinite-json-number")
            add(len(repr(item)))
        elif kind is str:
            if _live._count_ascii_json_string(item, add, ascii_only=ascii_only):
                return
            add(2)
            for character in item:
                point = ord(character)
                if 0xD800 <= point <= 0xDFFF:
                    refuse("unpaired-surrogate")
                if character in '"\\\b\f\n\r\t':
                    add(2)
                elif point < 0x20:
                    add(6)
                elif ascii_only and point >= 0x7F:
                    add(6 if point <= 0xFFFF else 12)
                else:
                    add(len(character.encode("utf-8")))
        elif kind in (dict, list):
            identity = id(item)
            if identity in active:
                refuse("cyclic-json")
            if len(item) > ceiling:
                refuse("complete-byte-capacity")
            active.add(identity)
            try:
                add(2)
                entries = item.items() if kind is dict else item
                for index, entry in enumerate(entries):
                    if index:
                        add(1)
                    if kind is dict:
                        key, child = entry
                        if type(key) is not str:
                            refuse("nontext-json-key")
                        visit(key, depth + 1)
                        add(1)
                        visit(child, depth + 1)
                    else:
                        visit(entry, depth + 1)
            finally:
                active.remove(identity)
        else:
            refuse("noncanonical-json-value")

    visit(value, 0)
    return total


def _json_bytes(owner, value, ceiling, *, ascii_only):
    expected = _json_size(owner, value, ceiling, ascii_only=ascii_only)
    try:
        raw = owner["json"].dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=ascii_only, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        refuse("canonical-json-serialization", upstream=exc)
    if len(raw) != expected or len(raw) > ceiling:
        refuse("canonical-byte-count")
    return raw


def native_bytes(owner, value, ceiling=None):
    """ASCII canonical JSON for native configuration/stat identities."""
    limit = owner["MAX_STATE_JSON_BYTES"] if ceiling is None else ceiling
    return _json_bytes(owner, value, limit, ascii_only=True)


def native_sha(owner, value):
    return owner["hashlib"].sha256(native_bytes(owner, value)).hexdigest()


def _component_bytes(owner, value, ceiling=None):
    limit = owner["MAX_STATE_JSON_BYTES"] if ceiling is None else ceiling
    return _json_bytes(owner, value, limit, ascii_only=False)


def _component_sha(owner, value):
    return owner["hashlib"].sha256(
        _component_bytes(owner, value)).hexdigest()


def _same_native(owner, first, second, *, ceiling=None):
    return native_bytes(owner, first, ceiling=ceiling) == native_bytes(
        owner, second, ceiling=ceiling)


def _same_component(owner, first, second):
    return _component_bytes(owner, first) == _component_bytes(owner, second)


def _generation(info):
    return dict(zip(FILE_GENERATION_KEYS, (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)))


def _directory_generation(info):
    complete = _generation(info)
    return {key: complete[key] for key in DIRECTORY_GENERATION_KEYS}


def _directory_identity(info):
    return tuple(getattr(info, "st_" + key) for key in
                 ("dev", "ino", "mode", "uid", "gid"))


def _canonical_path(owner, value):
    path = owner["os"]
    if type(value) is not str or not value or "\x00" in value \
            or len(value) > owner["MAX_CONFIG_PATH_CHARS"] \
            or not path.path.isabs(value) or path.path.normpath(value) != value:
        refuse("noncanonical-path")
    return value


class _DirectoryChain:
    """Hold every named directory edge in an absolute no-follow path."""

    def __init__(self, owner, path, *, private_terminal=False):
        self.owner = owner
        self.path = _canonical_path(owner, path)
        self.chain = []
        system = owner["os"]
        flags = (system.O_RDONLY | system.O_DIRECTORY | system.O_NOFOLLOW
                 | system.O_CLOEXEC)
        try:
            descriptor = system.open(system.sep, flags)
            # Own the descriptor before any fallible stat/identity work.
            self.chain.append((system.sep, descriptor, None))
            info = system.fstat(descriptor)
            self.chain[-1] = (system.sep, descriptor, _directory_identity(info))
            for name in self.path.split(system.sep)[1:]:
                if not name:
                    continue
                descriptor = system.open(
                    name, flags, dir_fd=self.chain[-1][1])
                self.chain.append((name, descriptor, None))
                info = system.fstat(descriptor)
                self.chain[-1] = (name, descriptor, _directory_identity(info))
            terminal = system.fstat(self.chain[-1][1])
            if not stat.S_ISDIR(terminal.st_mode) \
                    or terminal.st_uid != system.geteuid() \
                    or terminal.st_mode & 0o022 \
                    or private_terminal and stat.S_IMODE(terminal.st_mode) != 0o700:
                refuse("unsafe-owned-directory")
            self.current()
        except BaseException:
            self.close()
            raise

    @property
    def fd(self):
        if not self.chain:
            refuse("closed-directory")
        return self.chain[-1][1]

    @property
    def identity(self):
        if not self.chain:
            refuse("closed-directory")
        return self.chain[-1][2]

    @property
    def generation(self):
        return _directory_generation(self.owner["os"].fstat(self.fd))

    def current(self):
        system = self.owner["os"]
        if not self.chain:
            refuse("closed-directory")
        parent = None
        for index, (name, descriptor, original) in enumerate(self.chain):
            held = system.fstat(descriptor)
            named = system.stat(
                system.sep if index == 0 else name,
                follow_symlinks=False,
                **({} if parent is None else {"dir_fd": parent}))
            if not stat.S_ISDIR(held.st_mode) \
                    or not stat.S_ISDIR(named.st_mode) \
                    or _directory_identity(held) != original \
                    or _directory_identity(named) != original:
                refuse("named-directory-generation-changed")
            parent = descriptor

    def close(self):
        system = self.owner["os"]
        for _name, descriptor, _identity in reversed(self.chain):
            try:
                system.close(descriptor)
            except OSError:
                pass
        self.chain = []


class HeldFile:
    """One bounded file/absence held with its complete named parent chain."""

    def __init__(self, owner, path, ceiling, allow_absent=True):
        self.owner = owner
        self.path = _canonical_path(owner, path)
        self.ceiling = ceiling
        self.allow_absent = allow_absent
        self.fd = None
        self.directories = None
        self.raw = self.value = self.generation = None
        if type(ceiling) is not int or ceiling <= 0 \
                or type(allow_absent) is not bool:
            refuse("held-file-contract")
        try:
            parent = owner["os"].path.dirname(self.path)
            self.name = owner["os"].path.basename(self.path)
            if not self.name or self.name in (".", ".."):
                refuse("held-file-leaf")
            self.directories = _DirectoryChain(owner, parent)
            system = owner["os"]
            flags = (system.O_RDONLY | system.O_NOFOLLOW | system.O_CLOEXEC
                     | system.O_NONBLOCK)
            try:
                self.fd = system.open(
                    self.name, flags, dir_fd=self.directories.fd)
            except FileNotFoundError:
                if not allow_absent:
                    refuse("required-file-absent")
                self.named_current()
                return
            info = system.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) \
                    or info.st_uid != system.geteuid() or info.st_nlink != 1 \
                    or info.st_size < 0 or info.st_size > ceiling:
                refuse("unsafe-held-file")
            self.generation = _generation(info)
            self.raw = system.pread(self.fd, ceiling + 1, 0)
            if len(self.raw) != info.st_size or len(self.raw) > ceiling:
                refuse("held-file-byte-change")
            try:
                self.value = owner["_strict_json_loads"](
                    self.raw.decode("utf-8", errors="strict"))
            except (UnicodeError, ValueError, RecursionError) as exc:
                refuse("held-file-json", upstream=exc)
            self.current()
        except SourceBatchRefusal:
            self.close()
            raise
        except (OSError, ValueError, RuntimeError) as exc:
            self.close()
            refuse("held-file-admission", upstream=exc)
        except BaseException:
            self.close()
            raise

    @property
    def parent_identity(self):
        return self.directories.identity

    @property
    def parent_generation(self):
        return self.directories.generation

    def named_current(self):
        if self.directories is None:
            refuse("closed-held-file")
        system = self.owner["os"]
        self.directories.current()
        try:
            named = system.stat(
                self.name, dir_fd=self.directories.fd,
                follow_symlinks=False)
        except FileNotFoundError:
            if self.fd is not None:
                refuse("held-file-disappeared")
            self.directories.current()
            return
        if self.fd is None or _generation(named) != self.generation \
                or _generation(system.fstat(self.fd)) != self.generation:
            refuse("held-file-generation-changed")
        self.directories.current()

    def current(self):
        self.named_current()
        if self.fd is None:
            return
        system = self.owner["os"]
        raw = system.pread(self.fd, self.ceiling + 1, 0)
        if raw != self.raw or len(raw) != self.generation["size"] \
                or _generation(system.fstat(self.fd)) != self.generation:
            refuse("held-file-byte-change")
        self.named_current()

    def close(self):
        if self.fd is not None:
            try:
                self.owner["os"].close(self.fd)
            except OSError:
                pass
            self.fd = None
        if self.directories is not None:
            self.directories.close()
            self.directories = None


def _file_image(owner, held, *, path=False, status=False):
    if held.raw is None:
        value = {"generation": None, "raw_utf8_base64": None,
                 "raw_bytes": None, "raw_sha256": None}
        if status:
            value["status"] = "absent"
        if path:
            value["path"] = held.path
        return value
    value = {
        "generation": dict(held.generation),
        "raw_utf8_base64": base64.b64encode(held.raw).decode("ascii"),
        "raw_bytes": len(held.raw),
        "raw_sha256": owner["hashlib"].sha256(held.raw).hexdigest(),
    }
    if status:
        value["status"] = "owned-regular"
    if path:
        value["path"] = held.path
    return value


def _source_nonclaims(owner, value):
    if not _same_component(owner, value, list(_intake.SOURCE_NON_CLAIMS)):
        refuse("source-nonclaims")


def _component_pin(owner, value, expected, reason):
    _hex(expected, reason)
    if _component_sha(owner, value) != expected:
        refuse(reason)


def _validate_epoch_context(owner, epoch, *, include_history=False):
    """Shared source selection/policy contract, not epoch or source authority."""
    documents = ("configuration", "source_catalog", "profile")
    if include_history:
        documents += ("history",)
    for name in documents:
        _component_pin(
            owner, epoch[name], epoch["expected_" + name + "_sha256"],
            name + "-pin")
    _component_pin(owner, epoch["live_policy"],
                   epoch["expected_live_policy_sha256"], "live-policy-pin")
    try:
        _live._policy(epoch["live_policy"])
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        refuse("live-policy-contract", upstream=exc)

    configuration = epoch["configuration"]
    _keys(configuration, {"schema", "native_collectors",
                          "custom_collectors", "non_claims"},
          "configuration-shape")
    if configuration["schema"] != "sia-controller-source-selection-v1":
        refuse("configuration-schema")
    _source_nonclaims(owner, configuration["non_claims"])
    for field in ("native_collectors", "custom_collectors"):
        if type(configuration[field]) is not list \
                or len(configuration[field]) > owner["MAX_SOURCE_REPLAY_EVENTS"]:
            refuse("selected-source-capacity")
    native = configuration["native_collectors"]
    if any(type(name) is not str or not name for name in native) \
            or len(native) != len(set(native)):
        refuse("native-source-roster")
    custom_ids = []
    for entry in configuration["custom_collectors"]:
        try:
            normalized = owner["_validated_custom_sense_entry"](entry)
        except (TypeError, ValueError) as exc:
            refuse("custom-source-selection", upstream=exc)
        if normalized is None:
            refuse("custom-source-selection")
        custom_ids.append(normalized["source_id"])
    if len(custom_ids) != len(set(custom_ids)):
        refuse("custom-source-selection")

    catalog = epoch["source_catalog"]
    _keys(catalog, {"schema", "configuration_sha256", "sources",
                    "non_claims"}, "source-catalog-shape")
    if catalog["schema"] != "sia-controller-source-catalog-v1" \
            or catalog["configuration_sha256"] \
            != epoch["expected_configuration_sha256"]:
        refuse("source-catalog-binding")
    _source_nonclaims(owner, catalog["non_claims"])
    if type(catalog["sources"]) is not list or not catalog["sources"] \
            or len(catalog["sources"]) > owner["MAX_SOURCE_REPLAY_SOURCES"]:
        refuse("source-catalog-capacity")
    expected_ids = native + custom_ids
    if len(catalog["sources"]) != len(expected_ids):
        refuse("source-catalog-roster")
    for position, (row, source_id) in enumerate(
            zip(catalog["sources"], expected_ids)):
        _keys(row, {"source_id", "collector", "organ", "custom_name"},
              "source-catalog-row")
        if row["source_id"] != source_id \
                or any(type(row[field]) is not str or not row[field]
                       for field in ("source_id", "collector", "organ")):
            refuse("source-catalog-order")
        if position < len(native):
            if row["collector"] != source_id or row["custom_name"] is not None \
                    or owner["_SENSE_ORGAN"].get(source_id) != row["organ"]:
                refuse("native-source-catalog")
        else:
            normalized = owner["_validated_custom_sense_entry"](
                configuration["custom_collectors"][position - len(native)])
            if row["collector"] != "sense_custom" \
                    or row["custom_name"] != normalized["name"] \
                    or row["organ"] != normalized["organ"]:
                refuse("custom-source-catalog")

    profile = epoch["profile"]
    _keys(profile, set(_intake._PROFILE) | {"live_policy_sha256",
                                            "non_claims"},
          "profile-shape")
    if any(type(profile.get(key)) is not str or profile[key] != value
           for key, value in _intake._PROFILE.items()) \
            or profile["live_policy_sha256"] \
            != epoch["expected_live_policy_sha256"]:
        refuse("profile-contract")
    _source_nonclaims(owner, profile["non_claims"])
    return expected_ids


def _validate_epoch(owner, epoch, expected_epoch_sha256, observed_at,
                    *, initial):
    _keys(epoch, EPOCH_KEYS, "epoch-shape")
    _hex(expected_epoch_sha256, "epoch-pin")
    if native_sha(owner, epoch) != expected_epoch_sha256:
        refuse("epoch-pin")
    if epoch["schema"] != "sia-controller-source-epoch-v1" \
            or not _live._token(epoch["epoch_id"]) \
            or type(epoch["started_at"]) is not int \
            or type(observed_at) is not int \
            or epoch["started_at"] > observed_at:
        refuse("epoch-identity-or-clock")
    if not _same_native(owner, epoch["non_claims"], list(NON_CLAIMS)):
        refuse("batch-nonclaims")
    expected_ids = _validate_epoch_context(owner, epoch, include_history=True)

    history = epoch["history"]
    _keys(history, {"schema", "epoch_id", "started_at", "complete",
                    "entries", "non_claims"}, "history-shape")
    if history["schema"] != "sia-controller-event-history-v1" \
            or history["epoch_id"] != epoch["epoch_id"] \
            or history["started_at"] != epoch["started_at"] \
            or history["complete"] is not True \
            or type(history["entries"]) is not list \
            or len(history["entries"]) > owner["MAX_SOURCE_REPLAY_EVENTS"]:
        refuse("history-contract")
    _source_nonclaims(owner, history["non_claims"])
    predecessor = epoch["predecessor"]
    if predecessor is not None:
        _keys(predecessor, {"source_batch_sha256",
                            "live_generation_sha256"},
              "predecessor-shape")
        _hex(predecessor["source_batch_sha256"], "predecessor-pin")
        _hex(predecessor["live_generation_sha256"], "predecessor-pin")
    if initial and (history["entries"] or predecessor is not None):
        refuse("unbound-prior-source-history", phase="admit")
    return expected_ids


def _has_prior_authority(value):
    return type(value) is dict and bool(_AUTHORITY_KEYS.intersection(value))


def _initial_memo(owner, memo):
    if type(memo) is not dict:
        refuse("memo-shape")
    if _has_prior_authority(memo):
        refuse("unbound-prior-source-history", phase="admit")
    marker_key = owner["NOTIFY_BASELINE_ATTEMPT_KEY"]
    if marker_key in memo and memo[marker_key] is None:
        refuse("notification-baseline-marker")


def _disabled_policy(owner, config):
    senses = config.get("senses", {})
    if type(senses) is not dict or set(senses) - {"_comment", "disable"}:
        refuse("active-disable-policy")
    disabled = senses.get("disable", [])
    if type(disabled) is not list \
            or len(disabled) > owner["MAX_CONFIG_BYTES"] \
            or any(type(value) is not str or not value for value in disabled):
        refuse("active-disable-policy")
    return {owner["sanitize_slugpart"](value) for value in disabled}


def _owned_home(owner):
    home = owner.get("HOME")
    maximum = owner.get("MAX_CONFIG_PATH_CHARS")
    if type(home) is not str or not home or "\x00" in home \
            or type(maximum) is not int or maximum <= 0 \
            or len(home) > maximum or not os.path.isabs(home) \
            or os.path.normpath(home) != home:
        refuse("owned-home-contract")
    return home


def _canonical_custom_path(owner, raw):
    """Expand only the runtime owner's home and return an absolute path."""
    if type(raw) is not str or not raw or "\x00" in raw:
        refuse("custom-selection-path")
    if raw == "~":
        expanded = _owned_home(owner)
    elif raw.startswith("~/"):
        expanded = os.path.join(_owned_home(owner), raw[2:])
    elif raw.startswith("~"):
        refuse("custom-selection-path")
    else:
        expanded = raw
    if not os.path.isabs(expanded):
        refuse("custom-selection-path")
    canonical = os.path.normpath(expanded)
    maximum = owner.get("MAX_CONFIG_PATH_CHARS")
    if type(maximum) is not int or maximum <= 0 \
            or len(canonical) > maximum or not os.path.isabs(canonical) \
            or os.path.normpath(canonical) != canonical:
        refuse("custom-selection-path")
    return canonical


def _canonical_custom_selection_entry(owner, entry, normalized):
    """Materialize the exact intake configuration represented by defaults."""
    normalized_fields = {
        "name", "source_id", "organ", "description", "path",
        "stream_type", "match_literals", "exclude_literals", "field",
        "kind", "tags",
    }
    if type(entry) is not dict or type(normalized) is not dict \
            or set(normalized) != normalized_fields:
        refuse("runtime-custom-selection")
    for field in ("name", "source_id", "organ", "description", "path",
                  "stream_type", "field", "kind"):
        if type(normalized[field]) is not str or not normalized[field]:
            refuse("runtime-custom-selection")
    if normalized["source_id"] != "sense_custom:" + normalized["name"] \
            or normalized["stream_type"] not in {"lines", "jsonl"}:
        refuse("runtime-custom-selection")
    for field in ("match_literals", "exclude_literals"):
        values = normalized[field]
        if type(values) is not tuple \
                or any(type(value) is not str or not value or "|" in value
                       for value in values):
            refuse("runtime-custom-selection")
    tags = normalized["tags"]
    if type(tags) is not set \
            or any(type(tag) is not str or not tag for tag in tags):
        refuse("runtime-custom-selection")
    value = {
        "name": normalized["name"],
        "organ": normalized["organ"],
        "description": normalized["description"],
        "path": _canonical_custom_path(owner, entry.get("path")),
        "type": normalized["stream_type"],
        "enabled": True,
        "match": "|".join(normalized["match_literals"]),
        "exclude": "|".join(normalized["exclude_literals"]),
        "field": normalized["field"],
        "kind": normalized["kind"],
        "tags": sorted(tags),
    }
    try:
        repeated = owner["_validated_custom_sense_entry"](value)
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        refuse("runtime-custom-selection", upstream=exc)
    expected = dict(normalized)
    expected["path"] = value["path"]
    if repeated != expected:
        refuse("custom-selection-normalization")
    return value


def _runtime_projection(owner, epoch):
    config = owner["CONFIG"]
    if type(config) is not dict:
        refuse("active-configuration-shape")
    disabled = _disabled_policy(owner, config)
    organs = owner["ORGANS"]
    senses = owner["SENSES"]
    if type(organs) is not dict or type(senses) is not list:
        refuse("runtime-selection-shape")
    organ_rows = []
    for organ, values in organs.items():
        if type(organ) is not str or type(values) is not tuple \
                or len(values) != 2 \
                or any(type(value) is not str for value in values):
            refuse("runtime-organ-contract")
        organ_rows.append({"organ": organ, "name": values[0],
                           "description": values[1]})

    sense_names = []
    sense_objects = []
    exported = []
    for sense in senses:
        if not callable(sense) or type(getattr(sense, "__name__", None)) is not str:
            refuse("runtime-sense-contract")
        name = sense.__name__
        if not name or name in sense_names or owner.get(name) is not sense:
            refuse("runtime-sense-identity")
        sense_names.append(name)
        sense_objects.append(sense)
        exported.append(owner.get(name))
    if not sense_names or sense_names[-1] != "sense_custom" \
            or sense_names.count("sense_custom") != 1:
        refuse("runtime-custom-sense-roster")
    actual_native = sense_names[:-1]
    expected = epoch["configuration"]
    if actual_native != expected["native_collectors"]:
        refuse("runtime-native-selection")
    for name in actual_native:
        organ = owner["_SENSE_ORGAN"].get(name)
        if type(organ) is not str or organ not in organs \
                or owner["sanitize_slugpart"](organ) in disabled \
                or owner["sanitize_slugpart"](name) in disabled:
            refuse("runtime-native-selection")

    configured = config.get("custom_senses", [])
    if type(configured) is not list \
            or len(configured) > owner["MAX_LEDGER_PENDING_RECORDS"]:
        refuse("runtime-custom-selection")
    selected_raw = []
    selected_rows = []
    custom_indexes = {}
    seen = set()
    for index, entry in enumerate(configured):
        try:
            normalized = owner["_validated_custom_sense_entry"](entry)
        except (TypeError, ValueError) as exc:
            refuse("runtime-custom-selection", upstream=exc)
        if normalized is None:
            continue
        name = normalized["name"]
        if name in seen:
            refuse("runtime-custom-selection")
        seen.add(name)
        if name in disabled or normalized["organ"] in disabled:
            continue
        source_id = normalized["source_id"]
        if normalized["organ"] not in organs:
            refuse("runtime-custom-selection")
        selected_raw.append(_canonical_custom_selection_entry(
            owner, entry, normalized))
        selected_rows.append({"entry_index": index, "source_id": source_id})
        custom_indexes[source_id] = index
    if not _same_native(owner, selected_raw, expected["custom_collectors"]):
        refuse("runtime-custom-selection")

    selected_ids = actual_native + [row["source_id"] for row in selected_rows]
    catalog_ids = [row["source_id"] for row in epoch["source_catalog"]["sources"]]
    if selected_ids != catalog_ids:
        refuse("runtime-source-catalog")
    projection = {"organs": organ_rows, "senses": sense_names,
                  "custom_entries": selected_rows}
    identities = {"senses": tuple(sense_objects),
                  "exported": tuple(exported)}
    return projection, custom_indexes, identities


class _RuntimeConfiguration:
    """Freeze active config, registry order, and callable identities."""

    def __init__(self, owner, epoch, held, observed_at):
        self.owner = owner
        self.epoch = epoch
        self.held = held
        self.config_object = owner["CONFIG"]
        self.relation = ("last-loaded-object"
                         if self.config_object is owner["_LAST_LOADED_CONFIG"]
                         else "explicit-config-object")
        self.projection, self.custom_indexes, self.identities = \
            _runtime_projection(owner, epoch)
        self.projection_raw = native_bytes(owner, self.projection)
        self.config_raw = native_bytes(owner, self.config_object)
        self.current()
        decoded = owner["copy"].deepcopy(
            {} if held.raw is None else held.value)
        active = owner["copy"].deepcopy(self.config_object)
        self.current()
        body = {
            "schema": "sia-controller-observed-configuration-v1",
            "scope": "current-file-equivalent-active-config-and-selected-roster-v1",
            "observed_at": observed_at,
            "config_file": _file_image(owner, held, path=True, status=True),
            "decoded_config": decoded,
            "active_config": {
                "object_relation": self.relation,
                "active_load_valid": True,
                "errors": [],
                "config_sha256": native_sha(owner, active),
            },
            "runtime_selection": owner["copy"].deepcopy(self.projection),
            "configuration_sha256": epoch["expected_configuration_sha256"],
            "source_catalog_sha256": epoch["expected_source_catalog_sha256"],
            "profile_sha256": epoch["expected_profile_sha256"],
            "live_policy_sha256": epoch["expected_live_policy_sha256"],
            "non_claims": list(CONFIG_NON_CLAIMS),
        }
        _json_size(owner, dict(body, receipt_sha256="0" * 64),
                   owner["MAX_STATE_JSON_BYTES"], ascii_only=True)
        self.current()
        body["receipt_sha256"] = native_sha(owner, body)
        self.current()
        self.receipt = body

    def current(self):
        owner = self.owner
        self.held.current()
        if owner["CONFIG"] is not self.config_object \
                or not owner["_active_config_load_valid"]() \
                or type(owner["CONFIG_ERRORS"]) is not list \
                or owner["CONFIG_ERRORS"]:
            refuse("active-configuration-changed")
        relation = ("last-loaded-object"
                    if owner["CONFIG"] is owner["_LAST_LOADED_CONFIG"]
                    else "explicit-config-object")
        decoded = {} if self.held.raw is None else self.held.value
        if relation != self.relation \
                or native_bytes(owner, owner["CONFIG"]) != self.config_raw \
                or not _same_native(owner, decoded, owner["CONFIG"]):
            refuse("active-configuration-changed")
        projection, custom_indexes, identities = _runtime_projection(
            owner, self.epoch)
        if native_bytes(owner, projection) != self.projection_raw \
                or custom_indexes != self.custom_indexes \
                or len(identities["senses"]) != len(self.identities["senses"]) \
                or any(current is not original for current, original in zip(
                    identities["senses"], self.identities["senses"])) \
                or any(current is not original for current, original in zip(
                    identities["exported"], self.identities["exported"])):
            refuse("runtime-selection-changed")
        self.held.current()


class _CaptureFiles:
    """Hold all state/config named generations through the final sweep."""

    def __init__(self, owner):
        self.owner = owner
        self.stack = contextlib.ExitStack()
        self.files = {}
        try:
            self._add("memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
            self._add("cursor", owner["CURSORS_PATH"],
                      owner["MAX_STATE_JSON_BYTES"])
            self._add("config", owner["CONFIG_PATH"],
                      owner["MAX_CONFIG_BYTES"])
            self._add("batch", owner["CONTROLLER_SOURCE_BATCH_PATH"],
                      owner["MAX_STATE_JSON_BYTES"])
        except BaseException:
            self.close()
            raise

    def _add(self, name, path, ceiling):
        held = HeldFile(self.owner, path, ceiling, allow_absent=True)
        self.stack.callback(held.close)
        self.files[name] = held
        return held

    def current(self):
        for held in self.files.values():
            held.current()

    def named_current(self):
        for held in self.files.values():
            held.named_current()

    def refresh_memo(self, expected):
        old = self.files["memo"]
        parent_identity = old.parent_identity
        held = HeldFile(
            self.owner, self.owner["MEMO_PATH"],
            self.owner["MAX_MEMO_BYTES"], allow_absent=False)
        self.stack.callback(held.close)
        if held.parent_identity != parent_identity \
                or type(held.value) is not dict \
                or not _same_native(self.owner, held.value, expected,
                                    ceiling=self.owner["MAX_MEMO_BYTES"]):
            refuse("notification-memo-transition")
        old.close()
        self.files["memo"] = held
        held.current()

    def close(self):
        self.stack.close()


def _durable_initial_authority(owner, files, memo):
    durable = files.files["memo"].value
    if durable is None:
        durable = {}
    if type(durable) is not dict:
        refuse("memo-shape")
    if _has_prior_authority(durable) \
            or files.files["batch"].raw is not None:
        refuse("unbound-prior-source-history", phase="admit")
    if not _same_native(owner, durable, memo,
                        ceiling=owner["MAX_MEMO_BYTES"]):
        refuse("source-memo-authority")


def _successor_history(owner, retained_batch):
    history = owner["copy"].deepcopy(retained_batch["epoch"]["history"])
    batches = ([] if retained_batch["event_closure"] is None else
               retained_batch["event_closure"]["batches"])
    history["entries"].append({
        "source_returns": owner["copy"].deepcopy(
            retained_batch["source_returns"]),
        "expected_source_returns_sha256":
            retained_batch["source_returns"]["returns_sha256"],
        "event_batches": [
            {
                "batch": owner["copy"].deepcopy(batch),
                "expected_batch_sha256": batch["batch_sha256"],
            }
            for batch in batches
        ],
    })
    return history


def _validate_successor_request(
        owner, retained_batch, committed, epoch, expected_epoch_sha256,
        observed_at):
    """Bind a non-initial epoch to one exact retained completed capture."""
    _keys(committed, _COMMITTED_KEYS, "successor-commit-shape")
    for value in committed.values():
        _hex(value, "successor-commit-digest")
    if type(retained_batch) is dict \
            and retained_batch.get("batch_sha256") \
            != committed["source_batch_sha256"]:
        refuse("successor-commit-mismatch")
    validate_batch(
        owner, retained_batch, committed["source_batch_sha256"])
    _validate_epoch(
        owner, epoch, expected_epoch_sha256, observed_at, initial=False)
    if observed_at < retained_batch["observed_at"]:
        refuse("successor-clock-gap")

    prior = retained_batch["epoch"]
    if epoch["epoch_id"] != prior["epoch_id"] \
            or epoch["started_at"] != prior["started_at"]:
        refuse("successor-epoch-identity")
    for field in (
            "configuration", "source_catalog", "profile", "live_policy"):
        if not _same_native(owner, epoch[field], prior[field]) \
                or epoch["expected_" + field + "_sha256"] \
                != prior["expected_" + field + "_sha256"]:
            refuse("successor-" + field.replace("_", "-") + "-drift")

    expected_predecessor = {
        "source_batch_sha256": retained_batch["batch_sha256"],
        "live_generation_sha256": committed["live_generation_sha256"],
    }
    if not _same_native(
            owner, epoch["predecessor"], expected_predecessor):
        refuse("successor-predecessor-mismatch")
    expected_history = _successor_history(owner, retained_batch)
    if not _same_component(owner, epoch["history"], expected_history) \
            or epoch["expected_history_sha256"] \
            != _component_sha(owner, expected_history):
        refuse("successor-history-mismatch")


def _successor_memo(owner, value, committed):
    if type(value) is not dict:
        refuse("successor-memo-shape")
    if _SUCCESSOR_PENDING_KEYS.intersection(value):
        refuse("successor-pending-authority")
    if not _same_native(
            owner, value.get("controller_source_committed"), committed):
        refuse("successor-commit-authority")


def _durable_successor_authority(
        owner, files, memo, committed):
    durable = files.files["memo"].value
    _successor_memo(owner, memo, committed)
    _successor_memo(owner, durable, committed)
    if files.files["batch"].raw is not None:
        refuse("successor-pending-authority")
    if not _same_native(owner, durable, memo,
                        ceiling=owner["MAX_MEMO_BYTES"]):
        refuse("successor-memo-authority")


def _epoch_current(owner, epoch, original):
    if native_bytes(owner, epoch) != original:
        refuse("epoch-input-changed")


def _notification_marker(owner, memo):
    key = owner["NOTIFY_BASELINE_ATTEMPT_KEY"]
    if key in memo and memo[key] is None:
        refuse("notification-baseline-marker")
    try:
        return owner["_pending_notify_baseline_attempt"](memo)
    except (TypeError, ValueError, RuntimeError) as exc:
        refuse("notification-baseline-marker", upstream=exc)


class _ScratchDirectory:
    """One fixed operation directory outside enumerated authority roots."""

    def __init__(self, owner, operation_id):
        self.owner = owner
        self.parent = self.fd = None
        self.created = False
        system = owner["os"]
        root = owner["siaqueue"].staging_dir_for(
            owner["CONTROLLER_SOURCE_BATCH_PATH"],
            authority_roots=(owner["CORPUS"], owner["STATE"], owner["SHARE"]))
        root = system.path.abspath(root)
        try:
            owner["ensure_durable_directory"](root, mode=0o700)
            self.parent = _DirectoryChain(
                owner, root, private_terminal=True)
            self.name = "controller-source-" + operation_id
            if len(self.name) > owner["MAX_CONFIG_PATH_CHARS"] \
                    or "/" in self.name or "\x00" in self.name:
                refuse("journal-operation-path")
            system.mkdir(self.name, 0o700, dir_fd=self.parent.fd)
            self.created = True
            flags = (system.O_RDONLY | system.O_DIRECTORY | system.O_NOFOLLOW
                     | system.O_CLOEXEC)
            self.fd = system.open(self.name, flags, dir_fd=self.parent.fd)
            info = system.fstat(self.fd)
            if not stat.S_ISDIR(info.st_mode) \
                    or info.st_uid != system.geteuid() \
                    or stat.S_IMODE(info.st_mode) != 0o700:
                refuse("journal-operation-directory")
            self.identity = _directory_identity(info)
            self.path = system.path.join(root, self.name)
            self.current()
        except SourceBatchRefusal:
            self.close()
            raise
        except (OSError, ValueError, RuntimeError) as exc:
            self.close()
            refuse("journal-operation-directory", upstream=exc)

    def current(self):
        system = self.owner["os"]
        if self.parent is None or self.fd is None:
            refuse("journal-operation-directory")
        self.parent.current()
        held = system.fstat(self.fd)
        named = system.stat(
            self.name, dir_fd=self.parent.fd, follow_symlinks=False)
        if not stat.S_ISDIR(held.st_mode) or not stat.S_ISDIR(named.st_mode) \
                or _directory_identity(held) != self.identity \
                or _directory_identity(named) != self.identity:
            refuse("journal-operation-directory-changed")
        self.parent.current()

    def close(self):
        system = self.owner["os"]
        failure = None
        try:
            if self.fd is not None:
                try:
                    self.current()
                    system.rmdir(self.name, dir_fd=self.parent.fd)
                    self.created = False
                    self.parent.current()
                except OSError as exc:
                    failure = exc
                finally:
                    system.close(self.fd)
                    self.fd = None
        finally:
            if self.parent is not None:
                self.parent.close()
                self.parent = None
        if failure is not None:
            refuse("journal-operation-cleanup", upstream=failure)


@contextlib.contextmanager
def _journal_operation(owner, operation_id):
    directory = _ScratchDirectory(owner, operation_id)
    try:
        context = owner["_journal_capture_context"](
            operation_id=operation_id, directory=directory.path)
        with context:
            directory.current()
            yield context
            directory.current()
    finally:
        # Context exit removes only its held scratch leaves.  The operation
        # directory itself is removed by its separately held parent/leaf.
        directory.close()


def _cursor_delta(owner, source_id, before, after):
    if type(before) is not dict or type(after) is not dict:
        refuse("cursor-shape", phase="collect", source_id=source_id)
    removed = sorted(key for key in before if key not in after)
    changed = {}
    for key in sorted(after):
        if key not in before or not _same_native(owner, before[key], after[key]):
            changed[key] = owner["copy"].deepcopy(after[key])
    step = {"source_id": source_id, "removed_keys": removed,
            "set_values": changed, "after_sha256": native_sha(owner, after)}
    _json_size(owner, step, owner["MAX_STATE_JSON_BYTES"], ascii_only=True)
    return step


def _events_current(owner, events, records):
    current = [owner["_event_replay_record"](event) for event in tuple(events)]
    if not _same_component(owner, current, records):
        refuse("source-event-roster-changed")


def _collector_result(owner, runtime, source, trial, memo, files,
                      operation_id, notification_marker, custom_seen):
    source_id = source["source_id"]
    sense = owner[source["collector"]]
    journal_receipt = None
    marker = notification_marker

    def before_initial_baseline():
        nonlocal marker
        prior = _notification_marker(owner, memo)
        try:
            returned = owner["_mark_notify_baseline_attempt"](memo)
        except (TypeError, ValueError, RuntimeError, OSError) as exc:
            refuse("notification-baseline-attempt", phase="collect",
                   source_id=source_id, upstream=exc)
        if prior is not None and returned != prior:
            refuse("notification-baseline-attempt", phase="collect",
                   source_id=source_id)
        files.refresh_memo(memo)
        marker = _notification_marker(owner, memo)
        if returned != marker:
            refuse("notification-baseline-attempt", phase="collect",
                   source_id=source_id)
        return returned

    try:
        if source["collector"] == "sense_custom":
            result = sense(
                trial, include_sources=True,
                entry_index=runtime.custom_indexes[source_id],
                seen_names=custom_seen)
        elif source["collector"] == "sense_journal":
            with _journal_operation(owner, operation_id) as journal_context:
                result = sense(trial, journal_context=journal_context)
                journal_receipt = journal_context.result()
        elif source["collector"] == "sense_notify":
            if marker is not None:
                trial = owner["_notify_recover_interrupted_baseline"](trial)
            result = sense(
                trial, before_initial_baseline=before_initial_baseline)
        else:
            result = sense(trial)
    except AssertionError:
        raise
    except SourceBatchRefusal:
        raise
    except (OSError, ValueError, RuntimeError, TypeError, UnicodeError) as exc:
        refuse("source-collection-failed", phase="collect",
               source_id=source_id, upstream=exc)

    if source["collector"] == "sense_custom":
        if type(result) is not tuple or len(result) != 3:
            refuse("custom-source-return", phase="collect",
                   source_id=source_id)
        events, errors, evaluated = result
        if errors or type(evaluated) is not list or evaluated != [source_id]:
            refuse("custom-source-return", phase="collect",
                   source_id=source_id)
    else:
        events = result
    if type(events) is not list:
        refuse("source-return-shape", phase="collect", source_id=source_id)
    try:
        records = [owner["_event_replay_record"](event) for event in events]
    except AssertionError:
        raise
    except (TypeError, ValueError, RuntimeError) as exc:
        refuse("source-event-return", phase="collect",
               source_id=source_id, upstream=exc)
    return events, records, trial, journal_receipt, marker


def _take_refusal_intent(owner, sense, source_id, trial,
                         entry_present, entry_before):
    try:
        records = owner["_take_source_record_refusals"](trial)
        entries = owner["_take_owned_source_entry_refusals"](
            sense, trial, entry_present, entry_before)
    except AssertionError:
        raise
    except (TypeError, ValueError, RuntimeError) as exc:
        refuse("source-refusal-intent", phase="collect",
               source_id=source_id, upstream=exc)
    return {"source_id": source_id, "record_refusals": records,
            "entry_refusals": entries}


def _collect(owner, epoch, memo, files, runtime, operation_id,
             epoch_raw):
    cursor = files.files["cursor"]
    if cursor.raw is None:
        current = {}
        before_image = None
    elif type(cursor.value) is dict:
        current = owner["copy"].deepcopy(cursor.value)
        before_image = _file_image(owner, cursor)
    else:
        refuse("cursor-shape")
    initial = owner["copy"].deepcopy(current)
    before_native = native_bytes(owner, current)
    notification_marker = _notification_marker(owner, memo)
    pending_boundary = len(owner["PENDING_CURSOR_RENAMES"])
    source_runs = []
    refusal_intents = []
    journal_proposals = []
    event_runs = []
    steps = []
    custom_seen = set()
    total_events = 0
    try:
        for source in epoch["source_catalog"]["sources"]:
            source_id = source["source_id"]
            runtime.current()
            files.current()
            _epoch_current(owner, epoch, epoch_raw)
            trial = owner["copy"].deepcopy(current)
            step_before = owner["copy"].deepcopy(current)
            entry_present = owner["SOURCE_ENTRY_REFUSALS_KEY"] in trial
            entry_before = owner["copy"].deepcopy(
                trial.get(owner["SOURCE_ENTRY_REFUSALS_KEY"]))
            sense = owner[source["collector"]]
            events, records, trial, journal_receipt, notification_marker = \
                _collector_result(
                    owner, runtime, source, trial, memo, files,
                    operation_id, notification_marker, custom_seen)
            runtime.current()
            files.current()
            _epoch_current(owner, epoch, epoch_raw)
            intent = _take_refusal_intent(
                owner, sense, source_id, trial, entry_present, entry_before)
            total_events += len(records)
            if total_events > owner["MAX_SOURCE_REPLAY_EVENTS"]:
                refuse("source-event-capacity", phase="collect",
                       source_id=source_id)
            _json_size(owner, records, owner["MAX_STATE_JSON_BYTES"],
                       ascii_only=False)
            step = _cursor_delta(owner, source_id, step_before, trial)
            source_runs.append({"source_id": source_id, "events": records})
            refusal_intents.append(intent)
            event_runs.append((source_id, list(events), records))
            if journal_receipt is not None:
                journal_proposals.append(journal_receipt)
            current = owner["copy"].deepcopy(trial)
            runtime.current()
            files.current()
            _epoch_current(owner, epoch, epoch_raw)
            if len(owner["PENDING_CURSOR_RENAMES"]) != pending_boundary:
                refuse("legacy-cursor-scratch", phase="collect",
                       source_id=source_id)
            steps.append(step)
    finally:
        if len(owner["PENDING_CURSOR_RENAMES"]) != pending_boundary:
            owner["_discard_pending_cursor_renames"](pending_boundary)
    if native_bytes(owner, initial) != before_native:
        refuse("cursor-input-changed")
    return {
        "before": before_image,
        "before_value": initial,
        "after": current,
        "steps": steps,
        "runs": source_runs,
        "events": event_runs,
        "refusal_intents": refusal_intents,
        "journal_proposals": journal_proposals,
        "notification_baseline_attempt": notification_marker,
    }


def _plan_events(owner, collected, runtime, files, epoch, epoch_raw):
    grouped = {}
    for _source_id, events, records in collected["events"]:
        _events_current(owner, events, records)
        for event, record in zip(events, records):
            grouped.setdefault((record["organ"], record["ts"][:10]), []).append(
                event)
    plans_by_organ = {}
    for (organ, date), events in sorted(grouped.items()):
        runtime.current()
        files.current()
        _epoch_current(owner, epoch, epoch_raw)
        plan = owner["_prepare_event_page_plan"](
            organ=organ, date=date, events=events)
        runtime.current()
        files.current()
        _epoch_current(owner, epoch, epoch_raw)
        plans_by_organ.setdefault(organ, []).append(plan)
    batches = []
    for organ in sorted(plans_by_organ):
        plans = plans_by_organ[organ]
        batch = owner["_compose_event_page_plans"](
            plans=plans,
            expected_plan_sha256s=[plan["plan_sha256"] for plan in plans])
        batches.append(batch)
        runtime.current()
        files.current()
        _epoch_current(owner, epoch, epoch_raw)
    if not batches:
        return None
    closure = owner["_compose_event_page_batch_closure"](
        batches=batches,
        expected_batch_sha256s=[batch["batch_sha256"] for batch in batches])
    runtime.current()
    files.current()
    _epoch_current(owner, epoch, epoch_raw)
    return closure


def _source_returns(owner, epoch, observed_at, batch_id, runs):
    result = {
        "schema": "sia-controller-source-returns-v1",
        "batch_id": batch_id,
        "epoch_id": epoch["epoch_id"],
        "observed_at": observed_at,
        "complete": True,
        "configuration_sha256": epoch["expected_configuration_sha256"],
        "source_catalog_sha256": epoch["expected_source_catalog_sha256"],
        "profile_sha256": epoch["expected_profile_sha256"],
        "live_policy_sha256": epoch["expected_live_policy_sha256"],
        "runs": runs,
        "non_claims": list(_intake.SOURCE_NON_CLAIMS),
    }
    _json_size(owner, dict(result, returns_sha256="0" * 64),
               owner["MAX_STATE_JSON_BYTES"], ascii_only=False)
    result["returns_sha256"] = _component_sha(owner, result)
    return result


def _cursor_proposal(owner, files, collected):
    proposal = {
        "schema": "sia-controller-cursor-proposal-v1",
        "state_identity": dict(files.files["cursor"].parent_generation),
        "before": collected["before"],
        "before_value": collected["before_value"],
        "steps": collected["steps"],
        "after": collected["after"],
        "after_sha256": native_sha(owner, collected["after"]),
    }
    _json_size(owner, proposal, owner["MAX_STATE_JSON_BYTES"],
               ascii_only=True)
    return proposal


def _intake_projection(owner, epoch, returns, closure, observed_at):
    history = owner["copy"].deepcopy(epoch["history"])
    batches = [] if closure is None else closure["batches"]
    history["entries"].append({
        "source_returns": returns,
        "expected_source_returns_sha256": returns["returns_sha256"],
        "event_batches": [
            {"batch": batch,
             "expected_batch_sha256": batch["batch_sha256"]}
            for batch in batches],
    })
    request = {
        "history": history,
        "expected_history_sha256": _component_sha(owner, history),
        "configuration": epoch["configuration"],
        "expected_configuration_sha256": epoch["expected_configuration_sha256"],
        "source_catalog": epoch["source_catalog"],
        "expected_source_catalog_sha256": epoch["expected_source_catalog_sha256"],
        "profile": epoch["profile"],
        "expected_profile_sha256": epoch["expected_profile_sha256"],
        "live_policy": epoch["live_policy"],
        "expected_live_policy_sha256": epoch["expected_live_policy_sha256"],
        "observed_at": observed_at,
    }
    return owner["_prepare_event_live_intake"](**request)


def _batch_id(owner, epoch_sha256, observed_at, receipt, cursor):
    return native_sha(owner, {
        "schema": "sia-controller-source-batch-id-v1",
        "epoch_sha256": epoch_sha256,
        "observed_at": observed_at,
        "configuration_receipt_sha256": receipt["receipt_sha256"],
        "cursor_before": cursor,
    })


class _DeliveryCaptureFiles(_CaptureFiles):
    """Retain the existing collector's actual notification memo transitions.

    This does not authorize a memo write. The sole refresh entry point is the
    shared notification collector callback, after its existing marker write.
    Initial and v2 capture retain their original file-holder behavior.
    """

    def __init__(self, owner):
        self.notification_refreshes = []
        super().__init__(owner)

    def refresh_memo(self, expected):
        before = native_bytes(self.owner, self.files["memo"].value,
                              ceiling=self.owner["MAX_MEMO_BYTES"])
        super().refresh_memo(expected)
        after = native_bytes(self.owner, self.files["memo"].value,
                             ceiling=self.owner["MAX_MEMO_BYTES"])
        self.notification_refreshes.append((before, after))


class _DeliveryCaptureRequest:
    """A source-v3 request, not a readiness bypass or a publication owner.

    The complete represented request is bounded before any copy or lease.
    Scalar authority paths, capacities and the notification key are selected
    before its first serialization. A collector-produced notification refresh
    may add only that exact valid marker to the otherwise unchanged memo.
    The admitted original remains separately pinned throughout capture.
    """

    def __init__(self, owner, request):
        self.owner, self.request = owner, request
        if type(owner) is not dict:
            refuse("delivery-capture-owner-contract")
        _keys(request, _DELIVERY_CAPTURE_REQUEST_KEYS,
              "delivery-capture-request")
        self.paths = {name: owner.get(name) for name in (
            "HOME", "CORPUS", "STATE", "SHARE", "CONFIG_PATH", "CURSORS_PATH",
            "MEMO_PATH", "STATUS_PATH", "GRAPH_PATH", "LIVE_CANDIDATE_PATH",
            "LIVE_STATE_PATH", "CONTROLLER_SOURCE_BATCH_PATH",
            "CONTROLLER_SOURCE_ARCHIVE_DIR", "CONTROLLER_SOURCE_EFFECTS_ARCHIVE_DIR",
            "CONTROLLER_DELIVERY_EPOCH_ROOT", "CORPUS_OWNER_LOCK", "BRAINSTEM_OWNER_LOCK",
        )}
        self.capacities = {name: owner.get(name) for name in (
            "MAX_MEMO_BYTES", "MAX_STATE_JSON_BYTES", "MAX_CONFIG_PATH_CHARS",
            "MAX_CONFIG_TEXT_CHARS", "MAX_CONFIG_BYTES", "MAX_SOURCE_REPLAY_EVENTS",
            "MAX_SOURCE_REPLAY_SOURCES", "MAX_LEDGER_PENDING_RECORDS",
            "MAX_JSON_SAFE_INTEGER",
        )}
        self.notification_key = owner.get("NOTIFY_BASELINE_ATTEMPT_KEY")
        if any(type(value) is not int or value <= 0
               for value in self.capacities.values()) \
                or type(self.notification_key) is not str or not self.notification_key:
            refuse("delivery-capture-owner-contract")
        self.request_capacity = _delivery_capture_request_capacity(owner)
        for name, value in request.items():
            native_bytes(
                owner, value,
                ceiling=(self.capacities["MAX_MEMO_BYTES"] if name == "memo"
                         else self.capacities["MAX_STATE_JSON_BYTES"]))
        for path in self.paths.values():
            _canonical_path(owner, path)
        self.basis_current()
        self.original_raw = self.wire(request, complete_request=True)
        self.expected_raw = self.original_raw
        self.basis_current()
        self.memo_raw = self.wire(request["memo"], memo=True)
        self.basis_current()
        if self.wire(request, complete_request=True) != self.original_raw:
            refuse("delivery-capture-request-changed")
        _successor_memo(owner, request["memo"], request["committed"])
        _hex(request["expected_adoption_sha256"], "delivery-adoption-pin")
        _hex(request["expected_journal_limits_sha256"], "delivery-journal-limits-pin")
        import siadelivery
        siadelivery._limits(request["journal_limits"])
        if _live._sha(request["journal_limits"]) \
                != request["expected_journal_limits_sha256"]:
            refuse("delivery-journal-limits-pin")
        _validate_successor_request(
            owner, request["retained_batch"], request["committed"], request["epoch"],
            request["expected_epoch_sha256"], request["observed_at"])
        _notification_marker(owner, request["memo"])
        self.basis_current()
        if self.wire(request, complete_request=True) != self.original_raw:
            refuse("delivery-capture-request-changed")
        self.admitted = owner["copy"].deepcopy(request)
        self.held_epoch = self.held_journal = None
        self.epoch_view = self.journal_view = None
        self.epoch_view_raw = self.journal_view_raw = None
        self.collected = False
        self.inputs_current()

    def wire(self, value, *, memo=False, complete_request=False):
        ceiling = (self.request_capacity if complete_request else
                   self.capacities[
                       "MAX_MEMO_BYTES" if memo else "MAX_STATE_JSON_BYTES"])
        try:
            return native_bytes(self.owner, value, ceiling=ceiling)
        except SourceBatchRefusal as exc:
            if complete_request and exc.reason == "complete-byte-capacity":
                refuse("delivery-capture-complete-byte-capacity", upstream=exc)
            raise

    def basis_current(self):
        if _delivery_capture_request_capacity(self.owner) \
                != self.request_capacity:
            refuse("delivery-capture-owner-basis-changed")
        for name, expected in {**self.paths, **self.capacities,
                               "NOTIFY_BASELINE_ATTEMPT_KEY": self.notification_key}.items():
            actual = self.owner.get(name)
            if type(actual) is not type(expected) or actual != expected:
                refuse("delivery-capture-owner-basis-changed")

    def inputs_current(self):
        self.basis_current()
        if self.wire(self.request, complete_request=True) != self.expected_raw \
                or self.wire(self.admitted, complete_request=True) \
                != self.original_raw \
                or self.wire(self.request["memo"], memo=True) != self.memo_raw:
            refuse("delivery-capture-request-changed")
        self.basis_current()

    def authority(self, files):
        self.inputs_current()
        _durable_successor_authority(
            self.owner, files, self.request["memo"], self.admitted["committed"])
        self.inputs_current()

    def epoch_context(self):
        import siacontrollerdeliveryepoch
        self.inputs_current()
        request = self.admitted
        arguments = {key: request[key] for key in (
            "admitted_status", "retained_batch", "committed", "journal_limits",
            "expected_journal_limits_sha256", "expected_adoption_sha256")}
        arguments["memo"] = self.request["memo"]
        marker = _notification_marker(self.owner, self.request["memo"])
        self.inputs_current()
        if marker is None:
            return siacontrollerdeliveryepoch.hold_epoch(self.owner, **arguments)
        marker_pin = native_sha(self.owner, marker)
        self.inputs_current()
        return siacontrollerdeliveryepoch.hold_capturable_epoch(
            self.owner, **arguments, notification_baseline_attempt=marker,
            expected_notification_baseline_attempt_sha256=marker_pin)

    def preflight(self):
        # Preparation must already have completed. This genuine held read
        # refuses missing/rebound adopted storage before source acquisition.
        # Close it before the collector's existing legal memo refresh.
        self.inputs_current()
        with self.epoch_context() as held:
            held.current()
            self.inputs_current()
        self.inputs_current()

    def accept_collection(self, files, collected):
        if self.collected:
            refuse("delivery-capture-duplicate-collection")
        self.basis_current()
        if self.wire(self.admitted, complete_request=True) != self.original_raw:
            refuse("delivery-capture-request-changed")
        transitions = files.notification_refreshes
        actual_marker = _notification_marker(self.owner, self.request["memo"])
        if self.wire(actual_marker) != self.wire(collected["notification_baseline_attempt"]):
            refuse("delivery-capture-notification-binding")
        if transitions:
            original_memo = self.admitted["memo"]
            if len(transitions) != 1 or actual_marker is None \
                    or transitions[0][0] != self.memo_raw:
                refuse("delivery-capture-notification-transition")
            prior = _notification_marker(self.owner, original_memo)
            if prior is not None and self.wire(prior) != self.wire(actual_marker):
                refuse("delivery-capture-notification-transition")
            expected_memo = {**original_memo, self.notification_key: actual_marker}
            expected_request = {**self.admitted, "memo": expected_memo}
            updated_raw = self.wire(expected_request, complete_request=True)
            updated_memo_raw = self.wire(expected_memo, memo=True)
            if transitions[0][1] != updated_memo_raw \
                    or self.wire(self.request, complete_request=True) \
                    != updated_raw \
                    or self.wire(files.files["memo"].value, memo=True) != updated_memo_raw:
                refuse("delivery-capture-notification-transition")
            self.expected_raw, self.memo_raw = updated_raw, updated_memo_raw
        self.inputs_current()
        self.collected = True

    def bind(self, stack, result):
        import siacontrollerdeliverywrapper
        import siadelivery
        self.inputs_current()
        if not self.collected or self.held_epoch is not None:
            refuse("delivery-capture-phase")
        self.held_epoch = stack.enter_context(self.epoch_context())
        self.epoch_view = self.held_epoch.read()
        self.epoch_view_raw = self.wire(self.epoch_view)
        self.held_journal = stack.enter_context(siadelivery.hold_deliveries(
            directory=self.epoch_view["records_directory"],
            epoch_id=self.admitted["epoch"]["epoch_id"],
            limits=self.admitted["journal_limits"]))
        if self.held_journal.directory_identity() != self.epoch_view["records_identity"]:
            refuse("delivery-capture-records-identity")
        self.journal_view = self.held_journal.read()
        self.journal_view_raw = self.wire(self.journal_view)
        self.current()
        projection = result["intake_projection"]
        wrapped = siacontrollerdeliverywrapper.build(
            self.owner, parent_source_schema=self.admitted["retained_batch"]["schema"],
            epoch_view=self.epoch_view,
            expected_epoch_view_sha256=native_sha(self.owner, self.epoch_view),
            expected_adoption_sha256=self.admitted["expected_adoption_sha256"],
            journal=self.journal_view, expected_journal_sha256=_live._sha(self.journal_view),
            epoch=result["epoch"], expected_epoch_sha256=result["epoch_sha256"],
            projection=projection, expected_projection_sha256=projection["projection_sha256"],
            observed_at=result["observed_at"],
            notification_baseline_attempt=result["notification_baseline_attempt"])
        self.current()
        return wrapped

    def current(self):
        self.inputs_current()
        if self.held_epoch is not None:
            self.held_epoch.current()
            self.held_journal.current()
            if self.wire(self.epoch_view) != self.epoch_view_raw \
                    or self.wire(self.journal_view) != self.journal_view_raw \
                    or self.held_journal.directory_identity() != self.epoch_view["records_identity"]:
                refuse("delivery-capture-held-image-changed")
            self.held_epoch.current()
            self.held_journal.current()
        self.inputs_current()


def _capture_locked(owner, *, memo, epoch, expected_epoch_sha256,
                    observed_at, authority, successor=False, delivery=None, checkpoint=None):
    if checkpoint is not None and (successor or delivery is not None):
        refuse("checkpoint-capture-is-not-controller-publication")
    checkpoint_raw = None if checkpoint is None else native_bytes(owner, checkpoint)
    epoch_raw = native_bytes(owner, epoch)
    admitted_epoch = owner["copy"].deepcopy(epoch)
    if native_bytes(owner, admitted_epoch) != epoch_raw \
            or native_bytes(owner, epoch) != epoch_raw:
        refuse("epoch-copy-changed")
    files = (_CaptureFiles(owner) if delivery is None
             else _DeliveryCaptureFiles(owner))
    try:
        def current():
            files.current()
            authority(files)
            if checkpoint is not None and native_bytes(owner, checkpoint) != checkpoint_raw:
                refuse("capture-checkpoint-changed")
            if delivery is not None:
                delivery.current()

        with contextlib.ExitStack() as delivery_holds:
            current()
            runtime = _RuntimeConfiguration(
                owner, admitted_epoch, files.files["config"], observed_at)
            runtime.current()
            current()
            _epoch_current(owner, epoch, epoch_raw)
            if delivery is not None:
                delivery.preflight()
                runtime.current()
                current()
                _epoch_current(owner, epoch, epoch_raw)
            cursor_value = ({} if files.files["cursor"].raw is None
                            else files.files["cursor"].value)
            if type(cursor_value) is not dict:
                refuse("cursor-shape")
            operation_id = _batch_id(
                owner, expected_epoch_sha256, observed_at,
                runtime.receipt, cursor_value)
            collected = _collect(
                owner, admitted_epoch, memo, files, runtime, operation_id,
                epoch_raw)
            if delivery is not None:
                delivery.accept_collection(files, collected)
            runtime.current()
            current()
            _epoch_current(owner, epoch, epoch_raw)
            returns = _source_returns(
                owner, admitted_epoch, observed_at, operation_id,
                collected["runs"])
            closure = _plan_events(
                owner, collected, runtime, files, epoch, epoch_raw)
            if checkpoint is None:
                projection = _intake_projection(
                    owner, admitted_epoch, returns, closure, observed_at)
            else:
                import siasourcecheckpoint
                projection = siasourcecheckpoint.project_capture_entry(
                    owner, epoch=admitted_epoch, expected_epoch_sha256=expected_epoch_sha256,
                    checkpoint=checkpoint, returns=returns, closure=closure, observed_at=observed_at)
            runtime.current()
            current()
            _epoch_current(owner, epoch, epoch_raw)
            result = {
                "schema": "sia-controller-source-batch-v1",
                "status": "captured-not-published",
                "batch_id": operation_id,
                "observed_at": observed_at,
                "epoch": admitted_epoch,
                "epoch_sha256": expected_epoch_sha256,
                "configuration_receipt": runtime.receipt,
                "source_returns": returns,
                "cursor_proposal": _cursor_proposal(owner, files, collected),
                "journal_proposals": collected["journal_proposals"],
                "refusal_intents": collected["refusal_intents"],
                "notification_baseline_attempt": collected[
                    "notification_baseline_attempt"],
                "event_closure": closure,
                "intake_projection": projection,
                "non_claims": list(NON_CLAIMS),
                "batch_sha256": "0" * 64,
            }
            if checkpoint is not None:
                result["schema"] = "sia-controller-source-checkpoint-capture-v1"
                result["parent_checkpoint"] = owner["copy"].deepcopy(checkpoint)
                result["non_claims"] = list(siasourcecheckpoint.CAPTURE_NON_CLAIMS)
            if successor:
                result["schema"] = "sia-controller-source-batch-v2"
                result["idle_input"] = None
                if all(not run["events"] for run in returns["runs"]):
                    import siacontrolleridle
                    result["idle_input"] = siacontrolleridle.capture(
                        owner, epoch=admitted_epoch, projection=projection,
                        observed_at=observed_at)
                    runtime.current()
                    current()
                    _epoch_current(owner, epoch, epoch_raw)
            if delivery is not None:
                result["schema"] = "sia-controller-source-batch-v3"
                result["delivery_input"] = delivery.bind(delivery_holds, result)
            _json_size(owner, result, owner["MAX_STATE_JSON_BYTES"],
                       ascii_only=True)
            runtime.current()
            current()
            _epoch_current(owner, epoch, epoch_raw)
            body = {key: value for key, value in result.items()
                    if key != "batch_sha256"}
            result["batch_sha256"] = native_sha(owner, body)
            runtime.current()
            current()
            _epoch_current(owner, epoch, epoch_raw)
            if checkpoint is None:
                validate_batch(owner, result, result["batch_sha256"])
            else:
                siasourcecheckpoint.validate_capture(owner, result, result["batch_sha256"])
            result_raw = native_bytes(owner, result)
            runtime.current()
            current()
            _epoch_current(owner, epoch, epoch_raw)
            detached = owner["copy"].deepcopy(result)
            if native_bytes(owner, result) != result_raw \
                    or native_bytes(owner, detached) != result_raw:
                refuse("batch-result-copy-changed")
            runtime.current()
            current()
            _epoch_current(owner, epoch, epoch_raw)
            if native_bytes(owner, result) != result_raw \
                    or native_bytes(owner, detached) != result_raw:
                refuse("batch-final-image-changed")
            runtime.current()
            current()
            _epoch_current(owner, epoch, epoch_raw)
        # Held journal then epoch contexts close before the final source
        # sweep; their exit checks/callbacks must not follow that sweep.
        if delivery is not None:
            runtime.current()
            files.current()
            authority(files)
            _epoch_current(owner, epoch, epoch_raw)
            # Normal hold exits may run callbacks. They cannot change the
            # detached result after its last in-hold image check, nor can
            # tail serialization change the pinned scalar owner basis.
            if native_bytes(owner, result) != result_raw \
                    or native_bytes(owner, detached) != result_raw:
                refuse("batch-post-hold-image-changed")
            delivery.basis_current()
        # No serialization, hash, copy, or callback follows this sweep.
        files.named_current()
        return detached
    finally:
        files.close()


def _capture_controller_source_batch(
        owner, *, memo, epoch, expected_epoch_sha256, observed_at):
    """Capture one initial source epoch under the actual owner leases."""
    request = {"memo": memo, "epoch": epoch,
               "expected_epoch_sha256": expected_epoch_sha256,
               "observed_at": observed_at}
    # This is deliberately the first represented-input operation.
    _json_size(owner, request, owner["MAX_STATE_JSON_BYTES"],
               ascii_only=True)
    _initial_memo(owner, memo)
    _validate_epoch(
        owner, epoch, expected_epoch_sha256, observed_at, initial=True)

    def authority(files):
        _durable_initial_authority(owner, files, memo)

    with owner["brainstem_owner"](), owner["corpus_owner"]():
        try:
            return _capture_locked(
                owner, memo=memo, epoch=epoch,
                expected_epoch_sha256=expected_epoch_sha256,
                observed_at=observed_at, authority=authority)
        except AssertionError:
            raise
        except SourceBatchRefusal:
            raise
        except (OSError, ValueError, RuntimeError, TypeError, KeyError,
                AttributeError, UnicodeError, RecursionError) as exc:
            refuse("capture-admission", upstream=exc)


def capture(owner, *, memo, epoch, expected_epoch_sha256, observed_at):
    return _capture_controller_source_batch(
        owner, memo=memo, epoch=epoch,
        expected_epoch_sha256=expected_epoch_sha256,
        observed_at=observed_at)


def capture_successor(
        owner, *, memo, retained_batch, committed, epoch,
        expected_epoch_sha256, observed_at):
    """Capture one exact successor while completed authority remains durable."""
    if type(retained_batch) is dict \
            and retained_batch.get("schema") == "sia-controller-source-batch-v3":
        refuse("delivery-predecessor-requires-source-v3-capture")
    request = {
        "memo": memo, "retained_batch": retained_batch,
        "committed": committed, "epoch": epoch,
        "expected_epoch_sha256": expected_epoch_sha256,
        "observed_at": observed_at,
    }
    # Admit the complete represented request before copies, acquisition, or
    # authority descriptors.  The initial entry point remains separate.
    _json_size(owner, request, owner["MAX_STATE_JSON_BYTES"],
               ascii_only=True)
    retained_raw = native_bytes(owner, retained_batch)
    committed_raw = native_bytes(owner, committed)
    epoch_raw = native_bytes(owner, epoch)
    _successor_memo(owner, memo, committed)
    _validate_successor_request(
        owner, retained_batch, committed, epoch,
        expected_epoch_sha256, observed_at)
    if native_bytes(owner, retained_batch) != retained_raw \
            or native_bytes(owner, committed) != committed_raw \
            or native_bytes(owner, epoch) != epoch_raw:
        refuse("successor-input-changed")

    admitted_retained = owner["copy"].deepcopy(retained_batch)
    admitted_committed = owner["copy"].deepcopy(committed)
    if native_bytes(owner, admitted_retained) != retained_raw \
            or native_bytes(owner, admitted_committed) != committed_raw:
        refuse("successor-input-copy-changed")

    def authority(files):
        _durable_successor_authority(
            owner, files, memo, admitted_committed)
        if native_bytes(owner, retained_batch) != retained_raw \
                or native_bytes(owner, committed) != committed_raw \
                or native_bytes(owner, admitted_retained) != retained_raw \
                or native_bytes(
                    owner, admitted_committed) != committed_raw \
                or native_bytes(owner, epoch) != epoch_raw:
            refuse("successor-input-changed")

    with owner["brainstem_owner"](), owner["corpus_owner"]():
        try:
            return _capture_locked(
                owner, memo=memo, epoch=epoch,
                expected_epoch_sha256=expected_epoch_sha256,
                observed_at=observed_at, authority=authority,
                successor=True)
        except AssertionError:
            raise
        except SourceBatchRefusal:
            raise
        except (OSError, ValueError, RuntimeError, TypeError, KeyError,
                AttributeError, UnicodeError, RecursionError) as exc:
            refuse("successor-capture-admission", upstream=exc)


def capture_successor_v3(
        owner, *, memo, admitted_status, retained_batch, committed,
        epoch, expected_epoch_sha256, observed_at, journal_limits,
        expected_journal_limits_sha256, expected_adoption_sha256):
    """Capture sources, idle input and a held adopted delivery epoch once.

    Preparation is a separate durable front door and must have completed.
    The epoch is preflighted before collectors run, then held anew after any
    notification collector's permitted memo refresh. The final epoch and
    journal observations cover wrapper construction, complete batch hashing,
    pure validation and detachment. They close before the last source-name
    sweep. Capture neither consumes delivery records nor publishes a source
    slot, advances delivery state, acknowledges sources or authorizes output.
    """
    request = {
        "memo": memo, "admitted_status": admitted_status,
        "retained_batch": retained_batch, "committed": committed,
        "epoch": epoch, "expected_epoch_sha256": expected_epoch_sha256,
        "observed_at": observed_at, "journal_limits": journal_limits,
        "expected_journal_limits_sha256": expected_journal_limits_sha256,
        "expected_adoption_sha256": expected_adoption_sha256,
    }
    try:
        delivery = _DeliveryCaptureRequest(owner, request)
        with owner["brainstem_owner"](), owner["corpus_owner"]():
            delivery.inputs_current()
            return _capture_locked(
                owner, memo=memo, epoch=epoch,
                expected_epoch_sha256=expected_epoch_sha256,
                observed_at=observed_at, authority=delivery.authority,
                successor=True, delivery=delivery)
    except AssertionError:
        raise
    except SourceBatchRefusal:
        raise
    except (OSError, ValueError, RuntimeError, TypeError, KeyError,
            AttributeError, UnicodeError, RecursionError) as exc:
        refuse("delivery-successor-capture-admission-"
               + _admission_exception_class(exc), upstream=exc)


def _validate_file_image(owner, value, *, allow_absent):
    if value is None and allow_absent:
        return
    expected = {"generation", "raw_utf8_base64", "raw_bytes", "raw_sha256"}
    _keys(value, expected, "file-image-shape")
    generation = value["generation"]
    if generation is None:
        if not allow_absent or any(value[key] is not None for key in
                                   ("raw_utf8_base64", "raw_bytes",
                                    "raw_sha256")):
            refuse("file-image-absence")
        return
    _keys(generation, FILE_GENERATION_KEYS, "file-generation-shape")
    if any(type(generation[key]) is not int for key in FILE_GENERATION_KEYS) \
            or not stat.S_ISREG(generation["mode"]) \
            or generation["nlink"] != 1 \
            or generation["uid"] != owner["os"].geteuid() \
            or type(value["raw_utf8_base64"]) is not str \
            or type(value["raw_bytes"]) is not int \
            or value["raw_bytes"] != generation["size"] \
            or value["raw_bytes"] < 0:
        refuse("file-image-generation")
    try:
        raw = base64.b64decode(value["raw_utf8_base64"], validate=True)
    except (ValueError, TypeError) as exc:
        refuse("file-image-encoding", upstream=exc)
    _hex(value["raw_sha256"], "file-image-digest")
    if len(raw) != value["raw_bytes"] \
            or base64.b64encode(raw).decode("ascii") \
            != value["raw_utf8_base64"] \
            or owner["hashlib"].sha256(raw).hexdigest() \
            != value["raw_sha256"]:
        refuse("file-image-binding")
    return raw


def _validate_configuration_receipt(owner, receipt, epoch):
    _keys(receipt, CONFIG_RECEIPT_KEYS, "configuration-receipt-shape")
    if receipt["schema"] != "sia-controller-observed-configuration-v1" \
            or receipt["scope"] \
            != "current-file-equivalent-active-config-and-selected-roster-v1" \
            or receipt["observed_at"] < epoch["started_at"] \
            or type(receipt["observed_at"]) is not int \
            or not _same_native(owner, receipt["non_claims"],
                                list(CONFIG_NON_CLAIMS)):
        refuse("configuration-receipt-contract")
    file = receipt["config_file"]
    _keys(file, {"path", "status", "generation", "raw_utf8_base64",
                 "raw_bytes", "raw_sha256"}, "config-file-image-shape")
    if type(file["path"]) is not str or file["status"] not in {
            "absent", "owned-regular"}:
        refuse("config-file-image-contract")
    image = {key: file[key] for key in
             ("generation", "raw_utf8_base64", "raw_bytes", "raw_sha256")}
    raw = _validate_file_image(owner, image, allow_absent=True)
    if file["status"] == "absent":
        if raw is not None or receipt["decoded_config"] != {}:
            refuse("config-file-image-contract")
    else:
        if raw is None:
            refuse("config-file-image-contract")
        try:
            decoded = owner["_strict_json_loads"](raw.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError) as exc:
            refuse("config-file-image-json", upstream=exc)
        if not _same_native(owner, decoded, receipt["decoded_config"]):
            refuse("config-file-image-json")
    active = receipt["active_config"]
    _keys(active, {"object_relation", "active_load_valid", "errors",
                   "config_sha256"}, "active-config-receipt-shape")
    if active["object_relation"] not in {
            "last-loaded-object", "explicit-config-object"} \
            or active["active_load_valid"] is not True \
            or active["errors"] != []:
        refuse("active-config-receipt-contract")
    _hex(active["config_sha256"], "active-config-receipt-digest")
    if native_sha(owner, receipt["decoded_config"]) \
            != active["config_sha256"]:
        refuse("active-config-receipt-binding")
    selection = receipt["runtime_selection"]
    _keys(selection, {"organs", "senses", "custom_entries"},
          "runtime-selection-receipt-shape")
    if any(type(selection[field]) is not list
           for field in ("organs", "senses", "custom_entries")):
        refuse("runtime-selection-receipt-shape")
    for row in selection["organs"]:
        _keys(row, {"organ", "name", "description"},
              "runtime-organ-receipt-shape")
        if any(type(row[key]) is not str for key in row):
            refuse("runtime-organ-receipt-shape")
    if any(type(name) is not str or not name for name in selection["senses"]):
        refuse("runtime-sense-receipt-shape")
    for row in selection["custom_entries"]:
        _keys(row, {"entry_index", "source_id"},
              "runtime-custom-receipt-shape")
        if type(row["entry_index"]) is not int \
                or type(row["source_id"]) is not str:
            refuse("runtime-custom-receipt-shape")
    for name in ("configuration", "source_catalog", "profile", "live_policy"):
        if receipt[name + "_sha256"] != epoch["expected_" + name + "_sha256"]:
            refuse("configuration-receipt-epoch-binding")
    _hex(receipt["receipt_sha256"], "configuration-receipt-digest")
    if native_sha(owner, {key: value for key, value in receipt.items()
                          if key != "receipt_sha256"}) \
            != receipt["receipt_sha256"]:
        refuse("configuration-receipt-digest")


def _validate_journal_proposal(owner, value):
    _keys(value, {"schema", "status", "operation_id", "cursors",
                  "non_claims", "capture_sha256"},
          "journal-proposal-shape")
    if value["schema"] != "sia-journal-cursor-capture-v1" \
            or value["status"] != "captured-not-acknowledged" \
            or type(value["operation_id"]) is not str \
            or _OPERATION.fullmatch(value["operation_id"]) is None \
            or not _same_component(owner, value["non_claims"],
                                   list(_journal.NON_CLAIMS)) \
            or type(value["cursors"]) is not list \
            or [row.get("scope") if type(row) is dict else None
                for row in value["cursors"]] != ["sys", "user"]:
        refuse("journal-proposal-contract")
    for row in value["cursors"]:
        _keys(row, {"scope", "cursor_name", "metadata_only", "before",
                    "target", "catalog", "processed_count"},
              "journal-cursor-proposal-shape")
        if row["cursor_name"] != "journal-" + row["scope"] + ".cursor" \
                or type(row["metadata_only"]) is not bool \
                or type(row["catalog"]) is not list \
                or type(row["processed_count"]) is not int \
                or not 0 <= row["processed_count"] <= len(row["catalog"]):
            refuse("journal-cursor-proposal-contract")
        for image in (row["target"], row["before"]):
            if image is None:
                continue
            expected = {"raw_base64", "raw_bytes", "raw_sha256"}
            if image is row["before"]:
                expected = expected | {"generation"}
            _keys(image, expected, "journal-cursor-image-shape")
            try:
                raw = base64.b64decode(image["raw_base64"], validate=True)
            except (TypeError, ValueError) as exc:
                refuse("journal-cursor-image", upstream=exc)
            if type(image["raw_bytes"]) is not int \
                    or len(raw) != image["raw_bytes"] \
                    or owner["hashlib"].sha256(raw).hexdigest() \
                    != image["raw_sha256"]:
                refuse("journal-cursor-image")
            _hex(image["raw_sha256"], "journal-cursor-image")
            if "generation" in image:
                _keys(image["generation"], JOURNAL_GENERATION_KEYS,
                      "journal-generation-shape")
    _hex(value["capture_sha256"], "journal-proposal-digest")
    if _component_sha(owner, {key: item for key, item in value.items()
                              if key != "capture_sha256"}) \
            != value["capture_sha256"]:
        refuse("journal-proposal-digest")


def _validate_cursor(owner, proposal, source_ids):
    _keys(proposal, CURSOR_KEYS, "cursor-proposal-shape")
    if proposal["schema"] != "sia-controller-cursor-proposal-v1":
        refuse("cursor-proposal-schema")
    _keys(proposal["state_identity"], DIRECTORY_GENERATION_KEYS,
          "cursor-state-identity")
    if any(type(value) is not int
           for value in proposal["state_identity"].values()) \
            or not stat.S_ISDIR(proposal["state_identity"]["mode"]):
        refuse("cursor-state-identity")
    _validate_file_image(owner, proposal["before"], allow_absent=True)
    if type(proposal["before_value"]) is not dict \
            or type(proposal["after"]) is not dict \
            or type(proposal["steps"]) is not list \
            or len(proposal["steps"]) != len(source_ids):
        refuse("cursor-proposal-contract")
    cursor = owner["copy"].deepcopy(proposal["before_value"])
    for source_id, step in zip(source_ids, proposal["steps"]):
        _keys(step, CURSOR_STEP_KEYS, "cursor-step-shape")
        if step["source_id"] != source_id \
                or type(step["removed_keys"]) is not list \
                or step["removed_keys"] != sorted(set(step["removed_keys"])) \
                or type(step["set_values"]) is not dict \
                or set(step["removed_keys"]) & set(step["set_values"]):
            refuse("cursor-step-contract")
        for key in step["removed_keys"]:
            if type(key) is not str or key not in cursor:
                refuse("cursor-step-removal")
            del cursor[key]
        cursor.update(owner["copy"].deepcopy(step["set_values"]))
        _hex(step["after_sha256"], "cursor-step-digest")
        if native_sha(owner, cursor) != step["after_sha256"]:
            refuse("cursor-step-digest")
    if not _same_native(owner, cursor, proposal["after"]):
        refuse("cursor-proposal-after")
    _hex(proposal["after_sha256"], "cursor-proposal-digest")
    if native_sha(owner, proposal["after"]) != proposal["after_sha256"]:
        refuse("cursor-proposal-digest")


def _validate_refusal_intents(owner, intents, source_ids):
    if type(intents) is not list or len(intents) != len(source_ids):
        refuse("refusal-intent-roster")
    for source_id, intent in zip(source_ids, intents):
        _keys(intent, REFUSAL_INTENT_KEYS, "refusal-intent-shape")
        if intent["source_id"] != source_id \
                or type(intent["record_refusals"]) is not list \
                or type(intent["entry_refusals"]) is not list:
            refuse("refusal-intent-contract")
        record_trial = {
            owner["SOURCE_RECORD_REFUSALS_KEY"]:
                owner["copy"].deepcopy(intent["record_refusals"])}
        entry_trial = {
            owner["SOURCE_ENTRY_REFUSALS_KEY"]:
                owner["copy"].deepcopy(intent["entry_refusals"])}
        try:
            if owner["_take_source_record_refusals"](record_trial) \
                    != intent["record_refusals"] \
                    or owner["_take_source_entry_refusals"](
                        entry_trial, source_id) != intent["entry_refusals"]:
                refuse("refusal-intent-contract")
        except SourceBatchRefusal:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            refuse("refusal-intent-contract", upstream=exc)


def _validate_closure(owner, closure, returns):
    grouped = {}
    for run in returns["runs"]:
        for record in run["events"]:
            grouped.setdefault((record["organ"], record["ts"][:10]), []).append(
                record)
    if closure is None:
        if grouped:
            refuse("missing-event-closure")
        return []
    if not grouped:
        refuse("spurious-event-closure")
    _keys(closure, _pages.CLOSURE_KEYS, "event-closure-shape")
    try:
        body = _pages._closure_body(owner, closure["batches"])
        _pages._closure_reservation(owner, body)
        _pages._batch_pins(
            owner, closure["batches"],
            [batch["batch_sha256"] for batch in closure["batches"]])
    except (ValueError, RuntimeError, TypeError, KeyError) as exc:
        refuse("event-closure-contract", upstream=exc)
    supplied = {key: value for key, value in closure.items()
                if key != "closure_sha256"}
    if not _same_component(owner, supplied, body) \
            or _component_sha(owner, body) != closure["closure_sha256"]:
        refuse("event-closure-binding")
    seen = {}
    for batch in closure["batches"]:
        for plan in batch["members"]:
            key = (plan["organ"], plan["date"])
            if key in seen:
                refuse("event-plan-duplicate-day")
            seen[key] = plan["input_records"]
    if set(seen) != set(grouped) \
            or any(not _same_component(owner, seen[key], grouped[key])
                   for key in grouped):
        refuse("event-plan-return-binding")
    return [{"batch": batch,
             "expected_batch_sha256": batch["batch_sha256"]}
            for batch in closure["batches"]]


def _validate_retained_projection(owner, batch, event_batches):
    history = owner["copy"].deepcopy(batch["epoch"]["history"])
    history["entries"].append({
        "source_returns": batch["source_returns"],
        "expected_source_returns_sha256":
            batch["source_returns"]["returns_sha256"],
        "event_batches": event_batches,
    })
    request = {
        "history": history,
        "expected_history_sha256": _component_sha(owner, history),
        "configuration": batch["epoch"]["configuration"],
        "expected_configuration_sha256":
            batch["epoch"]["expected_configuration_sha256"],
        "source_catalog": batch["epoch"]["source_catalog"],
        "expected_source_catalog_sha256":
            batch["epoch"]["expected_source_catalog_sha256"],
        "profile": batch["epoch"]["profile"],
        "expected_profile_sha256": batch["epoch"]["expected_profile_sha256"],
        "live_policy": batch["epoch"]["live_policy"],
        "expected_live_policy_sha256":
            batch["epoch"]["expected_live_policy_sha256"],
        "observed_at": batch["observed_at"],
    }
    try:
        projected = _intake.prepare(owner, **request)
    except (ValueError, RuntimeError, TypeError, KeyError) as exc:
        refuse("intake-projection-contract", upstream=exc)
    if not _same_component(owner, projected, batch["intake_projection"]):
        refuse("intake-projection-binding")


def validate_batch(owner, batch, expected_batch_sha256):
    """Validate a retained source batch without consulting current sources."""
    _json_size(owner, batch, owner["MAX_STATE_JSON_BYTES"], ascii_only=True)
    delivery = type(batch) is dict and batch.get("schema") \
        == "sia-controller-source-batch-v3"
    successor = delivery or (type(batch) is dict and batch.get("schema")
                            == "sia-controller-source-batch-v2")
    _keys(batch, BATCH_V3_KEYS if delivery else BATCH_V2_KEYS if successor else BATCH_KEYS,
          "source-batch-shape")
    if batch["schema"] not in {
            "sia-controller-source-batch-v1",
            "sia-controller-source-batch-v2",
            "sia-controller-source-batch-v3"} \
            or batch["status"] != "captured-not-published" \
            or type(batch["batch_id"]) is not str \
            or _OPERATION.fullmatch(batch["batch_id"]) is None \
            or type(batch["observed_at"]) is not int \
            or not _same_native(owner, batch["non_claims"], list(NON_CLAIMS)):
        refuse("source-batch-contract")
    _hex(expected_batch_sha256, "source-batch-pin")
    _hex(batch["batch_sha256"], "source-batch-pin")
    if batch["batch_sha256"] != expected_batch_sha256 \
            or native_sha(owner, {key: value for key, value in batch.items()
                                  if key != "batch_sha256"}) \
            != expected_batch_sha256:
        refuse("source-batch-pin")
    _hex(batch["epoch_sha256"], "source-epoch-pin")
    if native_sha(owner, batch["epoch"]) != batch["epoch_sha256"]:
        refuse("source-epoch-pin")
    _validate_epoch(
        owner, batch["epoch"], batch["epoch_sha256"],
        batch["observed_at"], initial=False)
    event_batches = _validate_observation(owner, batch)
    return _validate_batch_completion(owner, batch, event_batches, successor, delivery)


def _validate_observation(owner, batch):
    """Shared exact collector/cursor/plan contract, not continuation authority."""
    _validate_configuration_receipt(
        owner, batch["configuration_receipt"], batch["epoch"])
    if batch["configuration_receipt"]["observed_at"] \
            != batch["observed_at"]:
        refuse("configuration-receipt-clock")

    returns = batch["source_returns"]
    if type(returns) is not dict or returns.get("batch_id") != batch["batch_id"] \
            or returns.get("observed_at") != batch["observed_at"] \
            or type(returns.get("runs")) is not list:
        refuse("source-return-contract")
    source_ids = [row["source_id"]
                  for row in batch["epoch"]["source_catalog"]["sources"]]
    if [run.get("source_id") if type(run) is dict else None
            for run in returns["runs"]] != source_ids:
        refuse("source-return-roster")
    for run in returns["runs"]:
        _keys(run, {"source_id", "events"}, "source-return-run-shape")
        if type(run["events"]) is not list:
            refuse("source-return-run-shape")
        for record in run["events"]:
            try:
                owner["_event_from_replay_record"](record)
            except (TypeError, ValueError, RuntimeError) as exc:
                refuse("source-event-record", upstream=exc)
    _hex(returns.get("returns_sha256"), "source-return-digest")
    if _component_sha(owner, {key: value for key, value in returns.items()
                              if key != "returns_sha256"}) \
            != returns["returns_sha256"]:
        refuse("source-return-digest")
    _validate_cursor(owner, batch["cursor_proposal"], source_ids)
    _validate_refusal_intents(owner, batch["refusal_intents"], source_ids)
    if type(batch["journal_proposals"]) is not list:
        refuse("journal-proposal-roster")
    for proposal in batch["journal_proposals"]:
        _validate_journal_proposal(owner, proposal)
    journal_ids = [source_id for source_id in source_ids
                   if source_id == "sense_journal"]
    if len(batch["journal_proposals"]) != len(journal_ids) \
            or any(proposal["operation_id"] != batch["batch_id"]
                   for proposal in batch["journal_proposals"]):
        refuse("journal-proposal-roster")
    marker = batch["notification_baseline_attempt"]
    if marker is not None:
        try:
            if owner["_pending_notify_baseline_attempt"]({
                    owner["NOTIFY_BASELINE_ATTEMPT_KEY"]: marker}) != marker:
                refuse("notification-baseline-marker")
        except SourceBatchRefusal:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            refuse("notification-baseline-marker", upstream=exc)
    return _validate_closure(owner, batch["event_closure"], returns)


def _validate_batch_completion(owner, batch, event_batches, successor, delivery):
    _validate_retained_projection(owner, batch, event_batches)
    returns = batch["source_returns"]
    if successor:
        if batch["epoch"]["predecessor"] is None:
            refuse("idle-successor-predecessor-required")
        if any(run["events"] for run in returns["runs"]):
            if batch["idle_input"] is not None:
                refuse("idle-input-on-nonempty-source-batch")
        else:
            try:
                import siacontrolleridle
                siacontrolleridle.validate(
                    owner, epoch=batch["epoch"],
                    projection=batch["intake_projection"],
                    observed_at=batch["observed_at"],
                    idle_input=batch["idle_input"])
            except (ValueError, RuntimeError, TypeError, KeyError) as exc:
                refuse("idle-input-contract", upstream=exc)
    if delivery:
        try:
            import siacontrollerdeliverywrapper
            wrapped = batch["delivery_input"]
            siacontrollerdeliverywrapper.validate(
                owner, delivery_input=wrapped,
                expected_input_sha256=wrapped["input_sha256"],
                epoch=batch["epoch"], expected_epoch_sha256=batch["epoch_sha256"],
                projection=batch["intake_projection"],
                expected_projection_sha256=batch["intake_projection"]["projection_sha256"],
                observed_at=batch["observed_at"],
                notification_baseline_attempt=batch["notification_baseline_attempt"])
        except (ValueError, RuntimeError, TypeError, KeyError) as exc:
            refuse("delivery-input-contract", upstream=exc)
    return None
