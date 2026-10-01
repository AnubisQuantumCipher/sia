"""Durable selection and recurring dispatch of one adopted compact package.

A recurring pulse holds no pins in memory, so an interrupted compact
transaction must be recoverable from durable state alone. This marker records
which retained package a later pulse has to finish. It is never authority:
each phase still re-reads the actual package, memo, status and live files
through the existing readers, which refuse when a recorded pin does not match
real bytes. The marker layer itself captures nothing, prepares nothing,
chooses nothing among candidates, starts no timer and installs no unit; it
also acknowledges nothing of its own. Completion is delegated whole to the
existing runner, which does publish, commit and acknowledge the source, so a
successful dispatch is an acknowledged transaction and must be read that way.

Journal limits and the adoption pin never come from a marker or a package
payload. A recorded package may say which bytes a later pulse has to finish;
it may never say that the package was authorized.
"""

import copy
import os

import siacheckpointadoption as adoption
import siacheckpointrunner as runner
import siacheckpointtransaction as transaction
import sialiveloop as live
import siasourcebatch as source
import siasourcepublication as publication


NON_CLAIMS = (
    "The marker records which retained package a later pulse must finish. It is not adoption, publication, acknowledgment, readiness, or evidence that the package is still present on disk.",
    "Recorded pins are premises for a later independent read. They do not authenticate the package, its preparation claim, or current source, journal and publication authority.",
    "Selection performs no capture, no preparation, no choice among candidate packages, no timer, no unit installation and no service activation.",
    "Retirement records only that this dispatcher will not retry the package. It is not proof that every downstream effect of the transaction succeeded.",
)

_SCHEMA = "sia-checkpoint-package-marker-v1"
_STATUS = "selected-not-completed"
_MARKER = "controller_checkpoint_package"
_MARKER_KEYS = frozenset({
    "schema", "status", "directory", "manifest_sha256", "root_sha256",
    "source_batch_sha256", "started_at", "seq", "non_claims", "marker_sha256",
})


def _wire(owner, value, *, memo=False):
    return source.native_bytes(owner, value,
        ceiling=owner["MAX_MEMO_BYTES"] if memo else owner["MAX_STATE_JSON_BYTES"])


def _digest(marker):
    return live._sha({key: value for key, value in marker.items()
                      if key != "marker_sha256"})


def _build(owner, *, directory, manifest_sha256, root_sha256,
           source_batch_sha256, started_at, seq):
    marker = {
        "schema": _SCHEMA,
        "status": _STATUS,
        "directory": directory,
        "manifest_sha256": manifest_sha256,
        "root_sha256": root_sha256,
        "source_batch_sha256": source_batch_sha256,
        "started_at": started_at,
        "seq": seq,
        "non_claims": list(NON_CLAIMS),
    }
    marker["marker_sha256"] = _digest(marker)
    return _validate(owner, marker)


def _validate(owner, marker):
    """Admit a represented marker, or refuse; never repair one in place."""
    if type(marker) is not dict or set(marker) != _MARKER_KEYS \
            or marker["schema"] != _SCHEMA or marker["status"] != _STATUS \
            or type(marker["started_at"]) is not str \
            or type(marker["seq"]) is not int or type(marker["seq"]) is bool \
            or marker["seq"] < 0 or marker["seq"] > owner["MAX_JSON_SAFE_INTEGER"] \
            or marker["non_claims"] != list(NON_CLAIMS):
        source.refuse("checkpoint-dispatch-marker-shape")
    for name in ("manifest_sha256", "root_sha256", "source_batch_sha256"):
        source._hex(marker[name], "checkpoint-dispatch-marker-pin")
    directory = marker["directory"]
    if type(directory) is not str or not directory.startswith("/") \
            or os.path.normpath(directory) != directory:
        source.refuse("checkpoint-dispatch-marker-directory")
    if marker["marker_sha256"] != _digest(marker):
        source.refuse("checkpoint-dispatch-marker-digest")
    return copy.deepcopy(marker)


def select(owner, *, memo):
    """Return the pins a later pulse must finish, or None when none is held.

    Absence of a marker is absence of a selected package, never evidence that
    no compact transaction exists; the memo's own source state remains the
    authority on what is pending.
    """
    if type(memo) is not dict:
        source.refuse("checkpoint-dispatch-memo-shape")
    if _MARKER not in memo:
        return None
    return _validate(owner, memo[_MARKER])


def record(owner, *, memo, directory, expected_manifest_sha256,
           expected_root_sha256, started_at, seq):
    """Bind one prepared package's pins durably, ahead of its adoption.

    The recorded source batch is read out of the actual retained package, not
    accepted from the caller. An identical marker is an idempotent no-op; a
    different one is refused rather than replaced, because the recorded
    package may still be in flight and would become unreachable.
    """
    if type(owner) is not dict:
        raise TypeError("owner must be a globals-style dictionary")
    if type(memo) is not dict:
        source.refuse("checkpoint-dispatch-memo-shape")
    if type(started_at) is not str:
        source.refuse("checkpoint-dispatch-started-at")
    if type(seq) is not int or type(seq) is bool or seq < 0 \
            or seq > owner["MAX_JSON_SAFE_INTEGER"] or memo.get("pulse_seq") != seq:
        source.refuse("checkpoint-dispatch-sequence")
    references = dict(owner)
    original_memo = _wire(owner, memo, memo=True)
    with owner["brainstem_owner"](), owner["corpus_owner"]():
        view = transaction.read_prepared(owner, directory=directory,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_root_sha256=expected_root_sha256)
        marker = _build(owner, directory=directory,
            manifest_sha256=expected_manifest_sha256,
            root_sha256=expected_root_sha256,
            source_batch_sha256=view["manifest"]["source_batch_sha256"],
            started_at=started_at, seq=seq)
        with publication._files(owner, source) as (files, observe, current, named_current):
            def unchanged():
                if any(owner.get(name) is not value
                       for name, value in references.items()) \
                        or _wire(owner, memo, memo=True) != original_memo:
                    source.refuse("checkpoint-dispatch-input-changed")
                current()

            unchanged()
            if _wire(owner, files["memo"].value, memo=True) != original_memo:
                source.refuse("checkpoint-dispatch-memo-authority")
            if _MARKER in memo:
                if _wire(owner, _validate(owner, memo[_MARKER])) != _wire(owner, marker):
                    source.refuse("checkpoint-dispatch-marker-differs")
                named_current()
                return False
            updated = copy.deepcopy(memo)
            updated[_MARKER] = marker
            updated_raw = _wire(owner, updated, memo=True)
            owner["_memo_text"](updated)
            unchanged()
            parent = files["memo"].parent_identity
            owner["atomic_write"](owner["MEMO_PATH"],
                updated_raw.decode("utf-8"), mode=0o600)
            actual = observe("memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
            if actual.parent_identity != parent or actual.raw != updated_raw:
                source.refuse("checkpoint-dispatch-memo-image-differs")
            unchanged()
            named_current()
            memo.clear()
            memo.update(updated)
            named_current()
            return True


def _adopted(memo, batch_sha256):
    """Whether durable memo actually shows this exact batch adopted."""
    pending = memo.get("controller_source_pending")
    committed = memo.get("controller_source_committed")
    return (type(pending) is dict
            and pending.get("batch_sha256") == batch_sha256) \
        or (type(committed) is dict
            and committed.get("source_batch_sha256") == batch_sha256)


def advance(owner, *, admitted_status, journal_limits,
            expected_journal_limits_sha256, expected_adoption_sha256):
    """Adopt a recorded-but-unadopted package, then finish it.

    This is the recurring entry for a pulse holding no pins, including the
    one interrupted between the durable marker and adoption. Which package
    is resumed comes from the marker; whether it may be adopted at all stays
    an independent caller premise — the configured journal limits and epoch
    adoption pin — which the ordinary adoption readers check against actual
    retained bytes. Returns None when no package is selected.
    """
    if type(owner) is not dict:
        raise TypeError("owner must be a globals-style dictionary")
    with owner["brainstem_owner"](), owner["corpus_owner"]():
        memo = owner["load_memo"]()
        marker = select(owner, memo=memo)
        if marker is None:
            return None
        if not _adopted(memo, marker["source_batch_sha256"]):
            adoption.adopt_root(owner, memo=memo, admitted_status=admitted_status,
                directory=marker["directory"],
                expected_manifest_sha256=marker["manifest_sha256"],
                expected_root_sha256=marker["root_sha256"],
                journal_limits=journal_limits,
                expected_journal_limits_sha256=expected_journal_limits_sha256,
                expected_adoption_sha256=expected_adoption_sha256,
                seq=marker["seq"])
            if not _adopted(memo, marker["source_batch_sha256"]):
                source.refuse("checkpoint-dispatch-adopted-batch-differs")
        return dispatch(owner)


def dispatch(owner):
    """Finish an already-adopted selected package, or return None.

    The caller supplies no pins. Only the package a previous pulse already
    recorded is finished, and only when the actual durable memo shows that
    exact source batch adopted or already acknowledged. A marker naming a
    package neither state admits is refused, never completed on trust; use
    advance() for the recorded-but-unadopted case, which needs premises a
    marker is not allowed to supply. Completion runs the full existing
    runner, so a returned view is an acknowledged transaction.
    """
    if type(owner) is not dict:
        raise TypeError("owner must be a globals-style dictionary")
    with owner["brainstem_owner"](), owner["corpus_owner"]():
        memo = owner["load_memo"]()
        marker = select(owner, memo=memo)
        if marker is None:
            return None
        batch_sha256 = marker["source_batch_sha256"]
        if not _adopted(memo, batch_sha256):
            source.refuse("checkpoint-dispatch-package-not-adopted")
        view = runner.complete_adopted(owner, directory=marker["directory"],
            expected_manifest_sha256=marker["manifest_sha256"],
            expected_root_sha256=marker["root_sha256"],
            started_at=marker["started_at"])
        if view["batch"]["batch_sha256"] != batch_sha256:
            source.refuse("checkpoint-dispatch-completed-batch-differs")
        # Order matters and is not interchangeable. The pointer is created
        # or advanced first; only then is the package marker dropped. A
        # crash after the marker went but before the pointer moved could
        # never remake the join, and would leave nothing naming the
        # directory or head.
        _advance_chain(owner, marker)
        _retire(owner, marker)
        return view


def _advance_chain(owner, package):
    """Create or advance the continuation pointer for an acknowledged package.

    Called only after complete_adopted returned a validated view, so the
    acknowledgment is established by the caller rather than assumed here.

    The join is against the retained package re-read by pin, never against
    this dispatcher's own marker. The pointer is created on bootstrap and
    transitioned on continuation, never dropped: the acknowledged batch
    carries a root pin but neither the directory nor the head, so this is
    the only durable record of where the chain lives. Its head is never
    discovered by scanning the directory.

    The head recorded here stays the package's input head by design. The
    acknowledged link has no successor document yet; the next pulse builds
    one from this head and the actual current acknowledgment. Advancing the
    recorded head to something the chain has not produced would be a pin
    for a document that does not exist.
    """
    import siahistoryroot as roots

    memo = owner["load_memo"]()
    selection = select_chain(owner, memo=memo)
    view = transaction.read_prepared(owner, directory=package["directory"],
        expected_manifest_sha256=package["manifest_sha256"],
        expected_root_sha256=package["root_sha256"])
    manifest = view["manifest"]
    if manifest["source_batch_sha256"] != package["source_batch_sha256"]:
        source.refuse("checkpoint-chain-package-differs")
    # A root-only package has no head document of its own; the bootstrap
    # root is the head, which the chain reader already admits at
    # generation zero.
    head_sha256 = manifest.get("head_sha256", package["root_sha256"])
    # Re-admit both chain documents by pin instead of deriving a generation
    # arithmetically from a marker.
    chain = roots.read_successor(owner, directory=package["directory"],
        expected_root_sha256=package["root_sha256"],
        expected_head_sha256=head_sha256)
    pointer = _build_chain(owner, directory=package["directory"],
        root_sha256=package["root_sha256"], head_sha256=head_sha256,
        next_generation=chain["next_generation"],
        committed=manifest["predecessor"], status=_CHAIN_CONTINUED)
    if selection is not None:
        if package["directory"] != selection["directory"] \
                or package["root_sha256"] != selection["root_sha256"] \
                or head_sha256 != selection["head_sha256"] \
                or _wire(owner, manifest["predecessor"]) \
                != _wire(owner, selection["committed"]):
            source.refuse("checkpoint-chain-package-differs")
        if selection["status"] == _CHAIN_CONTINUED:
            if _wire(owner, selection) != _wire(owner, pointer):
                source.refuse("checkpoint-chain-package-differs")
            return False
    return _write_chain(owner, selection, pointer)


def _write_chain(owner, expected, pointer):
    """Durably replace or create the pointer, under the ordinary checks."""
    references = dict(owner)
    with publication._files(owner, source) as (files, observe, current, named_current):
        memo = files["memo"].value
        if type(memo) is not dict:
            source.refuse("checkpoint-dispatch-memo-shape")
        # Key membership, not .get(): a present-but-null pointer is
        # malformed and must refuse, never be treated as absent and
        # silently overwritten.
        present = _CHAIN in memo
        if present != (expected is not None):
            source.refuse("checkpoint-chain-pointer-differs")
        if present and _wire(owner, _validate_chain(owner, memo[_CHAIN])) \
                != _wire(owner, expected):
            source.refuse("checkpoint-chain-pointer-differs")
        updated = copy.deepcopy(memo)
        updated[_CHAIN] = copy.deepcopy(pointer)
        updated_raw = _wire(owner, updated, memo=True)
        owner["_memo_text"](updated)
        if any(owner.get(name) is not value for name, value in references.items()):
            source.refuse("checkpoint-dispatch-input-changed")
        current()
        parent = files["memo"].parent_identity
        owner["atomic_write"](owner["MEMO_PATH"],
            updated_raw.decode("utf-8"), mode=0o600)
        actual = observe("memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
        if actual.parent_identity != parent or actual.raw != updated_raw:
            source.refuse("checkpoint-dispatch-memo-image-differs")
        named_current()
        return True


def _retire(owner, marker):
    """Drop the exact recorded marker once its transaction is acknowledged."""
    references = dict(owner)
    with publication._files(owner, source) as (files, observe, current, named_current):
        memo = files["memo"].value
        if type(memo) is not dict:
            source.refuse("checkpoint-dispatch-memo-shape")
        if _MARKER not in memo:
            named_current()
            return False
        if _wire(owner, _validate(owner, memo[_MARKER])) != _wire(owner, marker):
            source.refuse("checkpoint-dispatch-retire-marker-differs")
        if "controller_source_pending" in memo:
            source.refuse("checkpoint-dispatch-retire-still-pending")
        updated = copy.deepcopy(memo)
        updated.pop(_MARKER)
        updated_raw = _wire(owner, updated, memo=True)
        owner["_memo_text"](updated)
        if any(owner.get(name) is not value for name, value in references.items()):
            source.refuse("checkpoint-dispatch-input-changed")
        current()
        parent = files["memo"].parent_identity
        owner["atomic_write"](owner["MEMO_PATH"],
            updated_raw.decode("utf-8"), mode=0o600)
        actual = observe("memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
        if actual.parent_identity != parent or actual.raw != updated_raw:
            source.refuse("checkpoint-dispatch-memo-image-differs")
        named_current()
        return True


CHAIN_NON_CLAIMS = (
    "The chain selection records which retained root and head a pulse committed to extend, before any capture could raise a notification fence. It is not capture, preparation, adoption, publication, acknowledgment or readiness.",
    "Its head is the head a package was or will be built ON, the input to that link. It is never a head produced by a completed package, and a continued pointer does not assert that a successor document exists for the most recently acknowledged transaction.",
    "Its pins are premises for a later independent reopen by pin. They do not authenticate the chain documents, and no pin is ever discovered by scanning the directory for plausible file names.",
    "Selection does not choose among candidate chains, replace the bootstrap root, re-bootstrap ancestry, start a timer, install a unit or activate a service.",
    "Retirement records only that this selection is superseded by a prepared package. It is not proof that the capture, its effects or its acknowledgment succeeded.",
)

_CHAIN_SCHEMA = "sia-checkpoint-chain-selection-v1"
_CHAIN_STATUS = "selected-not-captured"
# The same pointer, after its package was acknowledged. It is not retired,
# because it is the only durable carrier of the directory and head: the
# acknowledged batch keeps a root pin and neither of those.
#
# Read head_sha256 on a continued pointer carefully. It is the head the
# last package was built ON — that package's INPUT head — and deliberately
# not a head the package produced. No successor document exists for the
# newly acknowledged link yet: the next pulse creates it by calling
# prepare_successor with this input head plus the actual current
# acknowledgment. So a continued pointer is "where the chain resumes
# from", never "the chain's completed head".
_CHAIN_CONTINUED = "continued"
_CHAIN_STATES = frozenset({_CHAIN_STATUS, _CHAIN_CONTINUED})
_CHAIN = "controller_checkpoint_chain"
_CHAIN_KEYS = frozenset({
    "schema", "status", "directory", "root_sha256", "head_sha256",
    "next_generation", "committed", "non_claims", "marker_sha256",
})


def _chain_digest(marker):
    return live._sha({key: value for key, value in marker.items()
                      if key != "marker_sha256"})


def _validate_chain(owner, marker):
    """Admit a represented chain selection, or refuse; never repair one."""
    if type(marker) is not dict or set(marker) != _CHAIN_KEYS \
            or marker["schema"] != _CHAIN_SCHEMA \
            or type(marker["status"]) is not str \
            or marker["status"] not in _CHAIN_STATES \
            or type(marker["next_generation"]) is not int \
            or type(marker["next_generation"]) is bool \
            or marker["next_generation"] < 1 \
            or marker["next_generation"] >= owner["MAX_JSON_SAFE_INTEGER"] \
            or marker["non_claims"] != list(CHAIN_NON_CLAIMS):
        source.refuse("checkpoint-chain-marker-shape")
    for name in ("root_sha256", "head_sha256"):
        source._hex(marker[name], "checkpoint-chain-marker-pin")
    committed = marker["committed"]
    if type(committed) is not dict or set(committed) != {
            "source_batch_sha256", "live_generation_sha256",
            "source_effects_receipt_sha256"}:
        source.refuse("checkpoint-chain-marker-committed")
    for value in committed.values():
        source._hex(value, "checkpoint-chain-marker-pin")
    directory = marker["directory"]
    if type(directory) is not str or not directory.startswith("/") \
            or os.path.normpath(directory) != directory:
        source.refuse("checkpoint-chain-marker-directory")
    if marker["marker_sha256"] != _chain_digest(marker):
        source.refuse("checkpoint-chain-marker-digest")
    return copy.deepcopy(marker)


def _build_chain(owner, *, directory, root_sha256, head_sha256,
                 next_generation, committed, status):
    """One pointer shape, shared by bootstrap creation and continuation."""
    marker = {
        "schema": _CHAIN_SCHEMA,
        "status": status,
        "directory": directory,
        "root_sha256": root_sha256,
        "head_sha256": head_sha256,
        "next_generation": next_generation,
        "committed": copy.deepcopy(committed),
        "non_claims": list(CHAIN_NON_CLAIMS),
    }
    marker["marker_sha256"] = _chain_digest(marker)
    return _validate_chain(owner, marker)


def select_chain(owner, *, memo):
    """Return the root/head a pulse already committed to extend, or None.

    Absence is absence of a selection, never evidence that no chain exists.
    """
    if type(memo) is not dict:
        source.refuse("checkpoint-dispatch-memo-shape")
    if _CHAIN not in memo:
        return None
    return _validate_chain(owner, memo[_CHAIN])


def record_chain(owner, *, memo, directory, expected_root_sha256, expected_head_sha256):
    """Pin the chain head durably before any capture can raise a fence.

    Written ahead of capture so a pulse interrupted after the notification
    collector wrote a fence can reopen the head it already chose, by pin,
    under capturable authority. Without this the retry would have to consult
    the strict completed reader, which refuses beneath a fence, or discover
    the head by scanning file names, which would invent a trusted pin.

    The head is reopened and admitted here, so a selection can never name a
    chain the directory does not actually hold. An identical selection is an
    idempotent no-op; a different one is refused rather than replaced.
    """
    if type(owner) is not dict:
        raise TypeError("owner must be a globals-style dictionary")
    if type(memo) is not dict:
        source.refuse("checkpoint-dispatch-memo-shape")
    committed = memo.get("controller_source_committed")
    if type(committed) is not dict:
        source.refuse("checkpoint-chain-source-authority")
    references = dict(owner)
    original_memo = _wire(owner, memo, memo=True)
    with owner["brainstem_owner"](), owner["corpus_owner"]():
        import siahistoryroot as roots

        view = roots.read_successor(owner, directory=directory,
            expected_root_sha256=expected_root_sha256,
            expected_head_sha256=expected_head_sha256)
        marker = _build_chain(owner, directory=directory,
            root_sha256=expected_root_sha256, head_sha256=expected_head_sha256,
            next_generation=view["next_generation"], committed=committed,
            status=_CHAIN_STATUS)
        with publication._files(owner, source) as (files, observe, current, named_current):
            def unchanged():
                if any(owner.get(name) is not value
                       for name, value in references.items()) \
                        or _wire(owner, memo, memo=True) != original_memo:
                    source.refuse("checkpoint-dispatch-input-changed")
                current()

            unchanged()
            if _wire(owner, files["memo"].value, memo=True) != original_memo:
                source.refuse("checkpoint-dispatch-memo-authority")
            if _CHAIN in memo:
                existing = _validate_chain(owner, memo[_CHAIN])
                if existing["status"] != _CHAIN_CONTINUED:
                    # Still in flight: identical is idempotent, different is
                    # refused rather than replaced.
                    if _wire(owner, existing) != _wire(owner, marker):
                        source.refuse("checkpoint-chain-marker-differs")
                    named_current()
                    return False
                # Continued: the chain may move forward exactly one real
                # link, proved on the head document's own parent pin rather
                # than on any marker.
                if existing["directory"] != directory \
                        or existing["root_sha256"] != expected_root_sha256 \
                        or view["head"].get("parent_sha256") != existing["head_sha256"]:
                    source.refuse("checkpoint-chain-progression-differs")
            updated = copy.deepcopy(memo)
            updated[_CHAIN] = marker
            updated_raw = _wire(owner, updated, memo=True)
            owner["_memo_text"](updated)
            unchanged()
            parent = files["memo"].parent_identity
            owner["atomic_write"](owner["MEMO_PATH"],
                updated_raw.decode("utf-8"), mode=0o600)
            actual = observe("memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
            if actual.parent_identity != parent or actual.raw != updated_raw:
                source.refuse("checkpoint-dispatch-memo-image-differs")
            unchanged()
            named_current()
            memo.clear()
            memo.update(updated)
            named_current()
            return True


def reopen_chain(owner, *, memo):
    """Reopen the selected head by its recorded pins, fence or no fence.

    This is the interrupted pulse's recovery entry. It consults no source
    authority at all, so it behaves identically beneath an outstanding
    notification fence, and it reads only the two documents the recorded
    pins name. Returns None when no selection is held.

    Consulting no authority is the point and also the limit: this proves
    nothing about the current committed state. The recorded triple is what
    was committed when the selection was made, not a claim about now. A
    capture resuming from here must still rejoin the actual current or
    fenced predecessor through its own reader before using any of it.
    """
    import siahistoryroot as roots

    marker = select_chain(owner, memo=memo)
    if marker is None:
        return None
    view = roots.read_successor(owner, directory=marker["directory"],
        expected_root_sha256=marker["root_sha256"],
        expected_head_sha256=marker["head_sha256"])
    if view["next_generation"] != marker["next_generation"]:
        source.refuse("checkpoint-chain-generation-differs")
    return {"selection": marker, "chain": view}
