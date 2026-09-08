"""Acknowledge or re-read one fully published controller-source transaction.

This module consumes an exact committed source-effects receipt.  It does not
collect sources, publish pages, invoke Git or gbrain, or construct a live
generation.  Its effects are limited, in order, to immutable full-receipt
retention, immutable batch archival, refusal settlement, journal/main cursor
publication and the final memo/readiness transition.

The additive completed reader selects the predecessor's digest-named archive
directly, so a different successor WAL may occupy the fixed slot without
making predecessor validation ambiguous.  It performs no durable write.

The separate capture-only reader admits the full notification-fenced memo
without claiming readiness. It retains the prior historical joins and the
current file generations through copying, but neither authorizes capture
nor relaxes the general completed reader or acknowledgment path.
"""

import base64
import contextlib
import copy
import os
import re
import stat


NON_CLAIMS = (
    "Acknowledgment validates and retires one already-published local source transaction; it does not authenticate source truth, complete machine history or hostile same-user immutability.",
    "An archived effects receipt, archived batch and advanced cursors prove only this local durable ordering; they do not prove external delivery, retrieval quality, biological cognition or a held-out win.",
    "The compact committed marker cross-pins the retained effects receipt and live generation but is not a replacement for revalidating the full archived receipt.",
)
CAPTURE_NON_CLAIMS = (
    "Capture-only predecessor observation is not current readiness and does not acknowledge, adopt or recover a source transaction.",
    "This view retains the complete notification-fenced memo and prior historical joins; it does not authorize capture or establish notification cursor correctness.",
    "No output or delivery is emitted, observed or consumed, and this view grants no writer authority.",
    "The unrelated fixed source slot is not interpreted, adopted or certified; predecessor selection comes from the committed archive pins.",
    "Checked local generations do not establish source truth, complete machine history or protection against hostile same-user mutation.",
    "No cognitive benchmark win or held-out retrieval win is established; all source, effects, live publication and acknowledgment nonclaims remain controlling.",
)

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_COMMITTED_KEYS = frozenset({
    "source_batch_sha256", "live_generation_sha256",
    "source_effects_receipt_sha256",
})
_PENDING_ONLY = frozenset({
    "controller_source_pending", "controller_source_live_pending",
    "controller_source_effects_pending",
    "controller_source_effects_committed", "pulse_status_effects_pending",
    "live_loop_pending",
})


def _refuse(source, reason, upstream=None):
    source.refuse(reason, phase="ack", upstream=upstream)


def _same(owner, source, first, second, *, memo=False):
    ceiling = owner["MAX_MEMO_BYTES"] if memo \
        else owner["MAX_STATE_JSON_BYTES"]
    return source.native_bytes(owner, first, ceiling=ceiling) \
        == source.native_bytes(owner, second, ceiling=ceiling)


def _generation(info):
    return {
        "device": info.st_dev, "inode": info.st_ino,
        "mode": info.st_mode, "uid": info.st_uid, "gid": info.st_gid,
        "nlink": info.st_nlink, "size": info.st_size,
        "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns,
    }


def _stable_identity(info):
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
        info.st_nlink, info.st_size, info.st_mtime_ns,
    )


class _HeldRaw:
    """One private regular file or absence under a retained parent chain."""

    def __init__(self, owner, source, path, ceiling, *, allow_absent=True):
        self.owner = owner
        self.source = source
        self.path = source._canonical_path(owner, path)
        self.ceiling = ceiling
        self.directories = source._DirectoryChain(
            owner, os.path.dirname(self.path))
        self.name = os.path.basename(self.path)
        self.fd = None
        self.raw = None
        self.generation = None
        if not self.name or self.name in (".", "..") \
                or type(ceiling) is not int or ceiling <= 0 \
                or type(allow_absent) is not bool:
            self.close()
            _refuse(source, "ack-held-file-contract")
        flags = (os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
                 | os.O_NONBLOCK)
        try:
            self.fd = os.open(
                self.name, flags, dir_fd=self.directories.fd)
        except FileNotFoundError:
            if not allow_absent:
                self.close()
                _refuse(source, "ack-required-file-absent")
            self.current()
            return
        except OSError as exc:
            self.close()
            _refuse(source, "ack-file-open", exc)
        try:
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) \
                    or info.st_uid != os.geteuid() or info.st_nlink != 1 \
                    or stat.S_IMODE(info.st_mode) != 0o600 \
                    or info.st_size < 0 or info.st_size > ceiling:
                _refuse(source, "ack-unsafe-file")
            self.generation = _generation(info)
            self.raw = os.pread(self.fd, ceiling + 1, 0)
            if len(self.raw) != info.st_size or len(self.raw) > ceiling:
                _refuse(source, "ack-file-byte-change")
            self.current()
        except BaseException:
            self.close()
            raise

    def current(self):
        self.directories.current()
        try:
            named = os.stat(
                self.name, dir_fd=self.directories.fd,
                follow_symlinks=False)
        except FileNotFoundError:
            if self.fd is None:
                self.directories.current()
                return
            _refuse(self.source, "ack-file-disappeared")
        if self.fd is None:
            _refuse(self.source, "ack-absent-file-appeared")
        held = os.fstat(self.fd)
        if _generation(held) != self.generation \
                or _generation(named) != self.generation \
                or os.pread(self.fd, self.ceiling + 1, 0) != self.raw:
            _refuse(self.source, "ack-file-generation-changed")
        self.directories.current()

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
        if getattr(self, "directories", None) is not None:
            self.directories.close()
            self.directories = None


def _path_present(path):
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def _private_archive_directory(owner, source, path, *, required):
    if not _path_present(path):
        if required:
            _refuse(source, "ack-archive-directory-absent")
        return None
    try:
        chain = source._DirectoryChain(
            owner, path, private_terminal=True)
    except (OSError, ValueError, RuntimeError) as exc:
        _refuse(source, "ack-archive-directory", exc)
    return chain


def _decode_batch(owner, source, raw, expected_sha256):
    try:
        batch = owner["_strict_json_loads"](
            raw.decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        _refuse(source, "ack-archive-json", exc)
    source.validate_batch(owner, batch, expected_sha256)
    if source.native_bytes(owner, batch) != raw:
        _refuse(source, "ack-source-batch-not-canonical")
    return batch


class _ArchiveSlot:
    def __init__(self, owner, source, expected_sha256, *, archive_only=False):
        if type(archive_only) is not bool:
            _refuse(source, "ack-archive-selection-contract")
        self.owner = owner
        self.source = source
        self.source_path = source._canonical_path(
            owner, owner["CONTROLLER_SOURCE_BATCH_PATH"])
        self.directory_path = source._canonical_path(
            owner, owner["CONTROLLER_SOURCE_ARCHIVE_DIR"])
        self.archive_path = os.path.join(
            self.directory_path, expected_sha256 + ".json")
        source_present = _path_present(self.source_path)
        directory_present = _path_present(self.directory_path)
        archive_present = directory_present and _path_present(
            self.archive_path)
        if directory_present:
            directory = _private_archive_directory(
                owner, source, self.directory_path, required=True)
            directory.close()
        if archive_only:
            # A completed predecessor is selected only by the digest in its
            # compact memo authority.  The fixed slot may now contain a
            # different, not-yet-adopted successor WAL; it is deliberately
            # outside this predecessor read and is validated by the rollover
            # boundary before adoption.
            if not archive_present:
                _refuse(source, "ack-completed-archive-absent")
            self.state = "archive"
            selected = self.archive_path
        else:
            # Preserve the v1 move-recovery rule: before completion, exactly
            # one of the fixed source name and digest archive may exist.
            if source_present == archive_present:
                _refuse(source, "ack-archive-state-ambiguous")
            self.state = "source" if source_present else "archive"
            selected = (self.source_path if source_present
                        else self.archive_path)
        self.held = _HeldRaw(
            owner, source, selected, owner["MAX_STATE_JSON_BYTES"],
            allow_absent=False)
        try:
            self.batch = _decode_batch(
                owner, source, self.held.raw, expected_sha256)
            self.raw = self.held.raw
        except BaseException:
            self.close()
            raise

    def current(self):
        self.held.current()

    def move(self):
        if self.state == "archive":
            self.current()
            return
        self.current()
        owner = self.owner
        source = self.source
        owner["ensure_durable_directory"](self.directory_path, mode=0o700)
        destination = _private_archive_directory(
            owner, source, self.directory_path, required=True)
        try:
            self.current()
            before = os.fstat(self.held.fd)
            try:
                owner["siaqueue"]._rename_noreplace(
                    self.held.directories.fd, self.held.name,
                    destination.fd, os.path.basename(self.archive_path))
            except (OSError, ValueError, RuntimeError) as exc:
                _refuse(source, "ack-archive-move", exc)
            os.fsync(self.held.directories.fd)
            os.fsync(destination.fd)
            try:
                os.stat(
                    self.held.name, dir_fd=self.held.directories.fd,
                    follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                _refuse(source, "ack-source-name-survived-move")
            moved = _HeldRaw(
                owner, source, self.archive_path,
                owner["MAX_STATE_JSON_BYTES"], allow_absent=False)
            try:
                after = os.fstat(moved.fd)
                if moved.raw != self.raw \
                        or _stable_identity(before) \
                        != _stable_identity(after):
                    _refuse(source, "ack-archive-generation-differs")
            except BaseException:
                moved.close()
                raise
            self.held.close()
            self.held = moved
            self.state = "archive"
            self.current()
        finally:
            destination.close()

    def close(self):
        self.held.close()


class _EffectsArchiveSlot:
    """One digest-named immutable source-effects receipt or exact absence."""

    def __init__(self, owner, source, expected_sha256, *,
                 expected_raw=None, required=False):
        if type(expected_sha256) is not str \
                or _HEX.fullmatch(expected_sha256) is None \
                or expected_raw is not None \
                and not isinstance(expected_raw, bytes) \
                or type(required) is not bool:
            _refuse(source, "ack-effects-archive-contract")
        self.owner = owner
        self.source = source
        self.directory_path = source._canonical_path(
            owner, owner["CONTROLLER_SOURCE_EFFECTS_ARCHIVE_DIR"])
        self.archive_path = os.path.join(
            self.directory_path, expected_sha256 + ".json")
        self.expected_raw = expected_raw
        self.held = None
        if _path_present(self.directory_path):
            directory = _private_archive_directory(
                owner, source, self.directory_path, required=True)
            directory.close()
        if not _path_present(self.archive_path):
            if required:
                _refuse(source, "ack-effects-archive-absent")
            self.state = "absent"
            return
        self.held = _HeldRaw(
            owner, source, self.archive_path, owner["MAX_MEMO_BYTES"],
            allow_absent=False)
        if expected_raw is not None and self.held.raw != expected_raw:
            self.close()
            _refuse(source, "ack-effects-archive-differs")
        self.state = "archive"

    @property
    def raw(self):
        return None if self.held is None else self.held.raw

    def current(self):
        if self.held is not None:
            self.held.current()
            if self.expected_raw is not None \
                    and self.held.raw != self.expected_raw:
                _refuse(self.source, "ack-effects-archive-differs")
        elif _path_present(self.archive_path):
            _refuse(self.source, "ack-effects-archive-appeared")

    def publish(self):
        if self.expected_raw is None:
            _refuse(self.source, "ack-effects-archive-payload")
        if self.state == "archive":
            self.current()
            return
        self.current()
        owner = self.owner
        source = self.source
        owner["ensure_durable_directory"](self.directory_path, mode=0o700)
        directory = _private_archive_directory(
            owner, source, self.directory_path, required=True)
        directory.close()
        try:
            owner["siaqueue"].fixed_atomic_publish(
                self.archive_path, self.expected_raw, mode=0o600,
                exclusive=True,
                staging_dir=owner["siaqueue"].staging_dir_for(
                    self.archive_path,
                    authority_roots=(owner["CORPUS"], owner["STATE"],
                                     owner["SHARE"])))
        except (OSError, ValueError, RuntimeError) as exc:
            _refuse(source, "ack-effects-archive-publication", exc)
        self.held = _HeldRaw(
            owner, source, self.archive_path, owner["MAX_MEMO_BYTES"],
            allow_absent=False)
        if self.held.raw != self.expected_raw:
            self.close()
            _refuse(source, "ack-effects-archive-publication-differs")
        self.state = "archive"
        self.current()

    def close(self):
        if self.held is not None:
            self.held.close()
            self.held = None


def _image_raw(source, image, reason):
    if image is None:
        return None
    try:
        return base64.b64decode(image["raw_utf8_base64"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        _refuse(source, reason, exc)


def _journal_image_raw(source, image, reason):
    if image is None:
        return None
    try:
        return base64.b64decode(image["raw_base64"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        _refuse(source, reason, exc)


class _CursorAuthority:
    def __init__(self, owner, source, *, path, ceiling, before,
                 target_raw, state_identity=None, main=False):
        self.owner = owner
        self.source = source
        self.path = path
        self.ceiling = ceiling
        self.before = before
        self.target_raw = target_raw
        self.state_identity = state_identity
        self.main = main
        self.held = _HeldRaw(
            owner, source, path, ceiling, allow_absent=True)
        try:
            if state_identity is not None \
                    and self.held.directories.generation != state_identity:
                _refuse(source, "ack-cursor-directory-generation")
            self.state = self._classify()
        except BaseException:
            self.close()
            raise

    def _before_matches(self):
        if self.before is None:
            return self.held.fd is None
        expected_raw = (_image_raw(
            self.source, self.before, "ack-main-cursor-image")
            if self.main else _journal_image_raw(
                self.source, self.before, "ack-journal-cursor-image"))
        generation = self.before.get("generation")
        if type(generation) is not dict or self.held.fd is None \
                or self.held.raw != expected_raw:
            return False
        return all(self.held.generation.get(key) == value
                   for key, value in generation.items())

    def _classify(self):
        if self._before_matches():
            return "before"
        if self.held.fd is not None and self.held.raw == self.target_raw:
            return "target"
        _refuse(self.source, "ack-cursor-third-state")

    def current(self):
        self.held.current()
        if self.state == "before" and not self._before_matches():
            _refuse(self.source, "ack-cursor-generation-changed")
        if self.state == "target" \
                and (self.held.fd is None
                     or self.held.raw != self.target_raw):
            _refuse(self.source, "ack-cursor-target-changed")

    def publish(self, value=None):
        self.current()
        if self.state == "target":
            return
        if self.main:
            self.owner["save_cursors"](value)
        else:
            try:
                text = self.target_raw.decode("utf-8", errors="strict")
            except UnicodeError as exc:
                _refuse(self.source, "ack-journal-cursor-utf8", exc)
            self.owner["atomic_write"](self.path, text, mode=0o600)
        self.held.close()
        self.held = _HeldRaw(
            self.owner, self.source, self.path, self.ceiling,
            allow_absent=False)
        if self.held.raw != self.target_raw:
            _refuse(self.source, "ack-cursor-publication-differs")
        self.state = "target"
        self.current()

    def close(self):
        self.held.close()


def _main_cursor(owner, source, proposal):
    try:
        target = owner["json"].dumps(
            proposal["after"], indent=1, sort_keys=True,
            allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        _refuse(source, "ack-main-cursor-target", exc)
    if owner["hashlib"].sha256(
            source.native_bytes(owner, proposal["after"])).hexdigest() \
            != proposal["after_sha256"]:
        _refuse(source, "ack-main-cursor-target")
    return _CursorAuthority(
        owner, source, path=owner["CURSORS_PATH"],
        ceiling=owner["MAX_STATE_JSON_BYTES"], before=proposal["before"],
        target_raw=target, state_identity=proposal["state_identity"],
        main=True)


def _journal_cursors(owner, source, batch):
    result = []
    try:
        for proposal in batch["journal_proposals"]:
            for row in proposal["cursors"]:
                target = _journal_image_raw(
                    source, row["target"], "ack-journal-cursor-target")
                if target is None:
                    _refuse(source, "ack-journal-cursor-target")
                result.append((row["scope"], _CursorAuthority(
                    owner, source,
                    path=os.path.join(owner["STATE"], row["cursor_name"]),
                    ceiling=owner["MAX_JOURNAL_CURSOR_BYTES"],
                    before=row["before"], target_raw=target)))
    except BaseException:
        for _scope, cursor in result:
            cursor.close()
        raise
    return result


def _all_current(effects_archive, archive, main, journals):
    effects_archive.current()
    archive.current()
    main.current()
    for _scope, cursor in journals:
        cursor.current()


def _memo_current(owner, source, memo, original, admitted_status):
    durable = owner["load_memo"]()
    if not _same(owner, source, memo, original, memo=True) \
            or not _same(owner, source, durable, original, memo=True):
        _refuse(source, "ack-memo-authority")
    owner["_require_status_admission_unchanged"](admitted_status)


def _committed_shape(source, committed):
    if type(committed) is not dict or set(committed) != _COMMITTED_KEYS:
        _refuse(source, "ack-committed-shape")
    for value in committed.values():
        if type(value) is not str or _HEX.fullmatch(value) is None:
            _refuse(source, "ack-committed-digest")


@contextlib.contextmanager
def _historical_predecessor(owner, source, effects, memo, admitted_status,
                            committed):
    """Hold historical archive/effects/live joins without claiming ready.

    Entry-point policy decides which complete memo authority is allowed.
    This helper neither filters that memo nor supplies a pending bypass;
    both actual source-effects and live readers receive it unchanged.
    """
    _committed_shape(source, committed)
    archive = _ArchiveSlot(
        owner, source, committed["source_batch_sha256"],
        archive_only=True)
    effects_archive = None
    try:
        effects_archive = _EffectsArchiveSlot(
            owner, source, committed["source_effects_receipt_sha256"],
            required=True)
        if archive.state != "archive":
            _refuse(source, "ack-completed-source-not-retired")
        status = owner["_require_status_admission_unchanged"](
            admitted_status)
        receipt = effects.validate_archived_receipt(
            owner, raw=effects_archive.raw, retained_batch=archive.batch,
            memo=memo, admitted_status=status,
            expected_receipt_sha256=
                committed["source_effects_receipt_sha256"])
        view = owner["_read_committed_live_generation"](
            memo=memo, admitted_status=status)
        generation = view.get("generation")
        if view.get("status") != "available" \
                or type(generation) is not dict \
                or generation.get("generation_sha256") \
                != committed["live_generation_sha256"] \
                or receipt["source_batch_sha256"] \
                != committed["source_batch_sha256"] \
                or receipt["live_generation"]["generation_sha256"] \
                != committed["live_generation_sha256"]:
            _refuse(source, "ack-completed-live-generation")
        effects_archive.current()
        archive.current()
        yield archive, effects_archive, status, generation
    finally:
        if effects_archive is not None:
            effects_archive.close()
        archive.close()


def _historical_ready_receipt(owner, source, memo, status, generation):
    """Check the old completion receipt, not present-tense readiness."""
    ready = owner["_ready_receipt"](memo)
    expected_ready = {
        "v": 1, "completed_at": status["ts"], "kind": "pulse",
        "identity": generation["publication_id"],
    }
    if ready != expected_ready:
        _refuse(source, "ack-completed-readiness")


def _completed(owner, source, effects, live, memo, admitted_status,
               committed):
    _committed_shape(source, committed)
    if _PENDING_ONLY.intersection(memo) \
            or owner["NOTIFY_BASELINE_ATTEMPT_KEY"] in memo:
        _refuse(source, "ack-completed-has-pending-authority")
    with _historical_predecessor(
            owner, source, effects, memo, admitted_status, committed) as (
            archive, effects_archive, status, generation):
        _historical_ready_receipt(owner, source, memo, status, generation)
        durable = owner["load_memo"]()
        if not _same(owner, source, durable, memo, memo=True) \
                or owner["_require_status_admission_unchanged"](
                    admitted_status) != status:
            _refuse(source, "ack-completed-authority-changed")
        effects_archive.current()
        archive.current()
        detached_batch = owner["copy"].deepcopy(archive.batch)
        detached_committed = owner["copy"].deepcopy(committed)
        if source.native_bytes(owner, detached_batch) != archive.raw \
                or not _same(
                    owner, source, detached_committed, committed):
            _refuse(source, "ack-completed-detachment")
        effects_archive.current()
        archive.current()
        return {
            "status": "available", "batch": detached_batch,
            "committed": detached_committed,
        }


def acknowledge(owner, *, memo, admitted_status):
    """Retire one exact fully published source generation, or recover it."""
    import siasourcebatch as source
    import siasourceeffects as effects
    import siasourcepublication as publication
    import sialiveloop as live

    if type(memo) is not dict:
        _refuse(source, "ack-memo-shape")
    original = copy.deepcopy(memo)
    durable = owner["load_memo"]()
    if not _same(owner, source, original, memo, memo=True) \
            or not _same(owner, source, durable, memo, memo=True):
        _refuse(source, "ack-memo-authority")
    committed = memo.get("controller_source_committed")
    if committed is not None:
        _completed(
            owner, source, effects, live, memo, admitted_status, committed)
        # The shipped v1 acknowledgment is intentionally effectless and
        # returns None on a completed retry.  The additive reader below owns
        # the detached completed view needed by recurring rollover.
        return None
    pending = memo.get("controller_source_pending")
    if type(pending) is not dict \
            or type(pending.get("batch_sha256")) is not str \
            or _HEX.fullmatch(pending["batch_sha256"]) is None:
        _refuse(source, "ack-source-pending-authority")

    archive = _ArchiveSlot(owner, source, pending["batch_sha256"])
    effects_archive = None
    main = None
    journals = []
    try:
        batch = archive.batch
        expected_pending = publication._receipt(
            owner, source, batch, archive.raw)
        if not _same(owner, source, pending, expected_pending):
            _refuse(source, "ack-source-pending-receipt")
        receipt = effects.committed_receipt(
            owner, memo=memo, admitted_status=admitted_status,
            retained_batch=batch)
        binding = owner["_controller_source_live_binding_marker"](memo)
        if binding is None:
            _refuse(source, "ack-live-binding")
        status = owner["_require_status_admission_unchanged"](
            admitted_status)
        live_view = owner["_read_committed_live_generation"](
            memo=memo, admitted_status=status)
        generation = live_view.get("generation")
        if live_view.get("status") != "available" \
                or type(generation) is not dict \
                or receipt["live_generation"]["generation_sha256"] \
                != generation.get("generation_sha256") \
                or receipt["source_batch_sha256"] != batch["batch_sha256"]:
            _refuse(source, "ack-effects-live-join")
        receipt_raw = source.native_bytes(
            owner, receipt, ceiling=owner["MAX_MEMO_BYTES"])
        effects_archive = _EffectsArchiveSlot(
            owner, source, receipt["receipt_sha256"],
            expected_raw=receipt_raw)

        marker = batch["notification_baseline_attempt"]
        retained_marker = memo.get(owner["NOTIFY_BASELINE_ATTEMPT_KEY"])
        if (marker is None) != (
                owner["NOTIFY_BASELINE_ATTEMPT_KEY"] not in memo) \
                or marker is not None and retained_marker != marker:
            _refuse(source, "ack-notification-fence")
        if marker is not None \
                and not owner["_notify_cursor_checkpoint_safe"](
                    batch["cursor_proposal"]["after"]):
            _refuse(source, "ack-notification-checkpoint")

        main = _main_cursor(owner, source, batch["cursor_proposal"])
        journals = _journal_cursors(owner, source, batch)
        _all_current(effects_archive, archive, main, journals)
        _memo_current(owner, source, memo, original, admitted_status)

        effects_archive.publish()
        retained_receipt = effects.validate_archived_receipt(
            owner, raw=effects_archive.raw, retained_batch=batch,
            memo=memo, admitted_status=status,
            expected_receipt_sha256=receipt["receipt_sha256"])
        if not _same(owner, source, retained_receipt, receipt):
            _refuse(source, "ack-effects-archive-receipt-differs")
        owner["_controller_source_ack_boundary"](
            "effects-receipt-archive-durable")
        _all_current(effects_archive, archive, main, journals)
        _memo_current(owner, source, memo, original, admitted_status)

        archive.move()
        owner["_controller_source_ack_boundary"]("archive-durable")
        _all_current(effects_archive, archive, main, journals)
        _memo_current(owner, source, memo, original, admitted_status)

        for intent in batch["refusal_intents"]:
            if intent["record_refusals"]:
                owner["_settle_source_record_refusals"](
                    intent["source_id"],
                    copy.deepcopy(intent["record_refusals"]))
            if intent["entry_refusals"]:
                owner["_settle_source_entry_refusals"](
                    intent["source_id"],
                    copy.deepcopy(intent["entry_refusals"]))
        owner["_controller_source_ack_boundary"]("refusals-durable")
        _all_current(effects_archive, archive, main, journals)
        _memo_current(owner, source, memo, original, admitted_status)

        for index, (scope, cursor) in enumerate(journals):
            for _later_scope, later in journals[index:]:
                later.current()
            main.current()
            cursor.publish()
            owner["_controller_source_ack_boundary"](
                "journal-" + scope + "-durable")
            effects_archive.current()
            archive.current()
            _memo_current(owner, source, memo, original, admitted_status)

        main.current()
        main.publish(copy.deepcopy(batch["cursor_proposal"]["after"]))
        owner["_controller_source_ack_boundary"]("cursor-state-durable")
        effects_archive.current()
        archive.current()
        main.current()
        for _scope, cursor in journals:
            cursor.current()
        _memo_current(owner, source, memo, original, admitted_status)

        updated = copy.deepcopy(memo)
        for key in _PENDING_ONLY:
            updated.pop(key, None)
        if marker is not None:
            updated.pop(owner["NOTIFY_BASELINE_ATTEMPT_KEY"], None)
        updated["controller_source_committed"] = {
            "source_batch_sha256": batch["batch_sha256"],
            "live_generation_sha256": generation["generation_sha256"],
            "source_effects_receipt_sha256": receipt["receipt_sha256"],
        }
        updated["ready"] = {
            "v": 1, "completed_at": status["ts"], "kind": "pulse",
            "identity": generation["publication_id"],
        }
        owner["_ready_receipt"](updated)
        owner["_memo_text"](updated)
        owner["_write_memo"](updated)
        published = owner["load_memo"]()
        if not _same(owner, source, published, updated, memo=True):
            _refuse(source, "ack-memo-publication")
        memo.clear()
        memo.update(copy.deepcopy(updated))
        owner["_controller_source_ack_boundary"]("memo-durable")
        return None
    finally:
        if main is not None:
            main.close()
        for _scope, cursor in journals:
            cursor.close()
        if effects_archive is not None:
            effects_archive.close()
        archive.close()


def read_completed(owner, *, memo, admitted_status):
    """Return one fully revalidated, detached completed predecessor view.

    Selection is by the digest-named immutable archive.  A different batch in
    the fixed slot is permitted because it is only successor WAL bytes; this
    function does not adopt, acknowledge, or otherwise interpret that slot.
    """
    import siasourcebatch as source
    import siasourceeffects as effects
    import sialiveloop as live

    if type(memo) is not dict:
        _refuse(source, "ack-memo-shape")
    original = copy.deepcopy(memo)
    durable = owner["load_memo"]()
    if not _same(owner, source, original, memo, memo=True) \
            or not _same(owner, source, durable, memo, memo=True):
        _refuse(source, "ack-memo-authority")
    committed = memo.get("controller_source_committed")
    if committed is None:
        _refuse(source, "ack-completed-authority-absent")
    result = _completed(
        owner, source, effects, live, memo, admitted_status, committed)
    if not _same(owner, source, original, memo, memo=True) \
            or result.get("committed") != committed:
        _refuse(source, "ack-completed-authority-changed")
    return result


def _capturable_fence(owner, source, publication, memo, committed,
                      attempt, expected_attempt_sha256):
    """Admit the sole allowed pending fence without suppressing any key."""
    if type(memo) is not dict:
        _refuse(source, "ack-capturable-memo-shape")
    if publication.SUCCESSOR_PENDING_KEYS.intersection(memo):
        _refuse(source, "ack-capturable-other-pending-authority")
    _committed_shape(source, committed)
    if not _same(owner, source, memo.get("controller_source_committed"), committed):
        _refuse(source, "ack-capturable-committed-authority")
    if type(expected_attempt_sha256) is not str \
            or _HEX.fullmatch(expected_attempt_sha256) is None:
        _refuse(source, "ack-capturable-fence-pin")
    key = owner["NOTIFY_BASELINE_ATTEMPT_KEY"]
    if key not in memo or memo[key] is None:
        _refuse(source, "ack-capturable-fence-absent")
    actual = owner["_pending_notify_baseline_attempt"](memo)
    if actual is None or not _same(owner, source, actual, attempt) \
            or source.native_sha(owner, attempt) != expected_attempt_sha256:
        _refuse(source, "ack-capturable-fence-authority")


def _capture_held_object(owner, source, held):
    try:
        value = owner["_strict_json_loads"](
            held.raw.decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        _refuse(source, "ack-capturable-authority-json", exc)
    if type(value) is not dict:
        _refuse(source, "ack-capturable-authority-shape")
    return value


def read_capturable_predecessor(
        owner, *, memo, admitted_status, committed,
        notification_baseline_attempt,
        expected_notification_baseline_attempt_sha256):
    """Read a historical predecessor beneath the exact notification fence.

    This entry point is neither the completed reader nor an ACK operation.
    It receives the caller's ordinary owner scope and creates none itself.
    The full actual memo, including its notification marker, is passed to
    existing effects/live verification; the old ready receipt is checked only
    as a historical join. No fixed-slot content is acquired or interpreted.
    """
    import siasourcebatch as source
    import siasourceeffects as effects
    import siasourcepublication as publication

    try:
        if type(owner) is not dict or type(memo) is not dict \
                or type(admitted_status) is not dict:
            _refuse(source, "ack-capturable-input-shape")
        capacities = {name: owner[name] for name in (
            "MAX_MEMO_BYTES", "MAX_STATE_JSON_BYTES", "MAX_CONFIG_PATH_CHARS")}
        if any(type(value) is not int or value <= 0 for value in capacities.values()):
            _refuse(source, "ack-capturable-capacity-contract")
        # Snapshot owner selection before serialization or defensive copying
        # can call out; a changed path must not become the initial basis.
        paths = {name: source._canonical_path(owner, owner[name]) for name in (
            "MEMO_PATH", "STATUS_PATH", "GRAPH_PATH",
            "LIVE_CANDIDATE_PATH", "LIVE_STATE_PATH",
            "CONTROLLER_SOURCE_BATCH_PATH",
            "CONTROLLER_SOURCE_ARCHIVE_DIR", "CONTROLLER_SOURCE_EFFECTS_ARCHIVE_DIR",
        )}
        basis = {
            "paths": paths, "capacities": capacities,
            "notification_key": owner["NOTIFY_BASELINE_ATTEMPT_KEY"],
        }
        basis_raw = source.native_bytes(owner, basis)
        request = {
            "memo": memo, "admitted_status": admitted_status,
            "committed": committed,
            "notification_baseline_attempt": notification_baseline_attempt,
            "expected_notification_baseline_attempt_sha256":
                expected_notification_baseline_attempt_sha256,
        }
        # Bound the complete compound request before any defensive copy, not
        # merely its individually bounded memo, status and marker members.
        request_raw = source.native_bytes(
            owner, request, ceiling=capacities["MAX_STATE_JSON_BYTES"])
        memo_raw = source.native_bytes(
            owner, memo, ceiling=capacities["MAX_MEMO_BYTES"])
        status_raw = source.native_bytes(
            owner, admitted_status, ceiling=capacities["MAX_STATE_JSON_BYTES"])
        _capturable_fence(
            owner, source, publication, memo, committed,
            notification_baseline_attempt,
            expected_notification_baseline_attempt_sha256)
        admitted = copy.deepcopy(request)
        if source.native_bytes(owner, request) != request_raw \
                or source.native_bytes(owner, admitted) != request_raw:
            _refuse(source, "ack-capturable-request-copy-changed")

        def inputs_current():
            current_basis = {
                "paths": {name: owner.get(name) for name in paths},
                "capacities": {name: owner.get(name) for name in capacities},
                "notification_key": owner.get("NOTIFY_BASELINE_ATTEMPT_KEY"),
            }
            if source.native_bytes(owner, current_basis) != basis_raw \
                    or source.native_bytes(owner, request) != request_raw \
                    or source.native_bytes(owner, admitted) != request_raw:
                _refuse(source, "ack-capturable-request-changed")

        inputs_current()
        with contextlib.ExitStack() as stack:
            held = {}
            retained_bytes = len(request_raw)
            for name in ("MEMO_PATH", "STATUS_PATH", "GRAPH_PATH",
                         "LIVE_CANDIDATE_PATH", "LIVE_STATE_PATH"):
                ceiling = capacities["MAX_MEMO_BYTES"] if name == "MEMO_PATH" \
                    else capacities["MAX_STATE_JSON_BYTES"]
                held[name] = _HeldRaw(
                    owner, source, paths[name], ceiling, allow_absent=False)
                stack.callback(held[name].close)
                retained_bytes += len(held[name].raw)
                if retained_bytes > capacities["MAX_STATE_JSON_BYTES"]:
                    _refuse(source, "ack-capturable-held-byte-capacity")
            durable = _capture_held_object(owner, source, held["MEMO_PATH"])
            retained_status = _capture_held_object(owner, source, held["STATUS_PATH"])
            if source.native_bytes(owner, durable, ceiling=capacities["MAX_MEMO_BYTES"]) != memo_raw \
                    or source.native_bytes(owner, retained_status) != status_raw:
                _refuse(source, "ack-capturable-durable-authority")
            _capturable_fence(
                owner, source, publication, durable, admitted["committed"],
                admitted["notification_baseline_attempt"],
                admitted["expected_notification_baseline_attempt_sha256"])

            def files_current():
                inputs_current()
                for file in held.values():
                    file.current()
                inputs_current()

            def current():
                files_current()
                actual_memo = owner["load_memo"]()
                actual_status = owner["_require_status_admission_unchanged"](
                    admitted["admitted_status"])
                if source.native_bytes(
                        owner, actual_memo, ceiling=capacities["MAX_MEMO_BYTES"]) != memo_raw \
                        or source.native_bytes(owner, actual_status) != status_raw:
                    _refuse(source, "ack-capturable-authority-changed")
                files_current()

            current()
            with _historical_predecessor(
                    owner, source, effects, memo, admitted_status, committed) as (
                    archive, effects_archive, status, generation):
                retained_bytes += len(archive.raw) + len(effects_archive.raw)
                if retained_bytes > capacities["MAX_STATE_JSON_BYTES"]:
                    _refuse(source, "ack-capturable-held-byte-capacity")
                _historical_ready_receipt(owner, source, memo, status, generation)
                if source.native_bytes(owner, status) != status_raw:
                    _refuse(source, "ack-capturable-historical-status-changed")
                current()
                result = {
                    "schema": "sia-controller-source-capturable-predecessor-v1",
                    "status": "capturable-not-ready", "batch": archive.batch,
                    "committed": admitted["committed"],
                    "notification_baseline_attempt": admitted["notification_baseline_attempt"],
                    "expected_notification_baseline_attempt_sha256":
                        admitted["expected_notification_baseline_attempt_sha256"],
                    "non_claims": list(CAPTURE_NON_CLAIMS),
                }
                # Keep every historical and current descriptor alive while
                # admitting the entire returned envelope and detaching it.
                result_raw = source.native_bytes(
                    owner, result, ceiling=capacities["MAX_STATE_JSON_BYTES"])
                # Declared retained-wire budget: the complete caller request,
                # each held memo/status/graph/candidate/generation raw body,
                # both source/effects archive bodies, and the complete result
                # envelope. Each listed representation is counted once; this
                # is not a claim to measure Python heap or process memory.
                if retained_bytes + len(result_raw) > capacities["MAX_STATE_JSON_BYTES"]:
                    _refuse(source, "ack-capturable-result-byte-capacity")
                current()
                effects_archive.current()
                archive.current()
                detached = copy.deepcopy(result)
                if source.native_bytes(owner, result) != result_raw \
                        or source.native_bytes(owner, detached) != result_raw \
                        or source.native_bytes(owner, detached["batch"]) != archive.raw:
                    _refuse(source, "ack-capturable-result-copy-changed")
                current()
                if source.native_bytes(owner, result) != result_raw \
                        or source.native_bytes(owner, detached) != result_raw:
                    _refuse(source, "ack-capturable-result-changed")
                effects_archive.current()
                archive.current()
                files_current()
                return detached
    except source.SourceBatchRefusal:
        raise
    except (OSError, ValueError, RuntimeError, TypeError, KeyError,
            AttributeError, UnicodeError, RecursionError, OverflowError,
            IndexError) as exc:
        _refuse(source, "ack-capturable-predecessor-refused", exc)
