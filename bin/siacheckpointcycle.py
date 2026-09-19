"""Route one resident pulse through the compact lane before the legacy one.

This is the resident entry, not a new scheduler. It creates no timer, no
unit and no service, and it never activates anything: the caller's existing
cycle already decided that a pulse is due.

Four states, checked in this order, because recovery must precede any
fresh work and fresh work must precede starting anything new:

1. A retained package marker. The transaction is already captured and
   adopted, so it is finished from durable state alone. This path samples
   no clock, reserves no pulse sequence and runs no collector.
2. A retained chain pointer. The machine is on the compact lane, so the
   chain continues: the parent is retained, the next head is built from
   the pointer plus the actual current acknowledgment, that selection is
   made durable BEFORE any capture, and only then is the package prepared.
   Capture may raise a notification fence; the already-persisted selection
   is what makes that recoverable without scanning for pins.
   A selection left in flight by an earlier pulse is resumed by its own
   recorded pins rather than chosen again, and a selection still at
   root=head is resumed as a ROOT package, not a successor one.
3. Neither of those, but an eligible controller: already enabled by the
   caller, already adopted, and with an independently admitted completed
   legacy predecessor. That starts a chain in this module's own bounded
   storage. It adds no operator choice and reads no configuration — the
   authority is the one already established.
4. Anything else, including the no-adoption, initial and pending legacy
   routes. The caller's legacy lane owns the pulse untouched.
"""

import os

import siacheckpointadoption as adoption
import siacheckpointdispatch as dispatch
import siacheckpointparent as parents
import siacheckpointtransaction as transaction
import siacontrollersourcerunner as runner
import siahistoryroot as roots
import siasourcebatch as source


NON_CLAIMS = (
    "Selecting the epoch marker's recorded adoption is a scalar read of a represented value. It does not reopen or validate the epoch files; the v3 runner does that independently.",
    "Routing one pulse is not scheduling, activation, installation or readiness. The caller decided a pulse is due; this only chooses which lane owns it.",
    "A compact lane is entered from durable state that already names a package or a chain, or by bootstrapping an eligible controller that is already enabled, already adopted and independently acknowledged. Bootstrapping grants nothing: it adds no operator choice, creates and reads no configuration, and carries only the authority already established.",
    "Eligibility is not readiness. Declining to bootstrap leaves the legacy lane exactly as it was, and the absence of a package, a chain and an eligible controller is not evidence that no compact chain could exist.",
    "Recovery finishes what is already durable. It establishes no new observation, and its completion view carries the original runner's claims, not stronger ones.",
    "The resident route operates only inside its configured root. A retained pointer or marker naming any other directory is refused, not followed; the lower-level readers keep their own explicit-directory contracts unchanged.",
)


def _owned(owner, directory, configured_directory):
    """Bind a retained directory to the resident configured root.

    A memo-supplied absolute path is a premise, not a permission. The
    resident route creates and operates exactly one owned directory, so a
    pointer or marker naming a different one is refused here — before any
    write, any capture and any collector. Lower-level APIs that take an
    explicit directory keep their existing contracts; this binding is the
    resident layer's own, and it never broadens writes to arbitrary user
    paths or to a private index.
    """
    if type(configured_directory) is not str or not configured_directory:
        source.refuse("checkpoint-cycle-configured-root")
    if directory != configured_directory:
        source.refuse("checkpoint-cycle-directory-differs")
    return directory


def _status(owner, memo):
    owner["_require_status_memo_fields"](memo)
    return runner._admit_status(owner, memo)


_COMPLETED_VIEW_KEYS = frozenset({"status", "batch", "committed"})


def pulse_status(owner, result):
    """Return the admitted status a pulse consumer renders for a cycle result.

    The legacy lane already returns the fresh admitted status. The compact
    lane returns the completed reader's evidence view, the contract its own
    tests pin, which names no pulse state at all; the status that completion
    published is read again from durable state, never rebuilt from the view.
    Anything else is passed through untouched, so a consumer that already
    holds a status keeps it.
    """
    if type(result) is not dict or set(result) != _COMPLETED_VIEW_KEYS:
        return result
    memo = owner["load_memo"]()
    return _status(owner, memo)


def configured_adoption(memo):
    """Select only the closed persisted epoch marker's original adoption.

    Moved here from the resident wrapper, which keeps the facade name and
    delegates. The v3 runner independently reopens and validates the epoch
    files; this scalar selection merely prevents the configured
    zero-argument route from silently taking an adoption out of a
    represented source wrapper.
    """
    import siacontrollerdeliveryepoch as epoch_api
    import sialiveloop

    if type(memo) is not dict:
        raise ValueError("configured controller-source memo must be an object")
    marker = memo.get(epoch_api._MARKER)
    if marker is None:
        return None
    if type(marker) is not dict or set(marker) != epoch_api._MARKER_KEYS \
            or marker.get("schema") != "sia-controller-delivery-epoch-marker-v1" \
            or not sialiveloop._token(marker.get("epoch_id")) \
            or not sialiveloop._integer(marker.get("started_at")) \
            or not sialiveloop._digest(marker.get("birth_sha256")):
        raise ValueError("configured controller-source epoch marker is invalid")
    adoption = marker.get("adoption_sha256")
    if adoption is not None and not sialiveloop._digest(adoption):
        raise ValueError("configured controller-source adoption pin is invalid")
    return adoption


def recover(owner, *, memo, configured_directory, journal_limits,
            expected_journal_limits_sha256, expected_adoption_sha256):
    """Finish a retained compact package, or return None.

    The package marker is written BEFORE adoption, so a crash between the
    two is legitimate and leaves a recorded-but-unadopted package. Going
    straight to dispatch would refuse that with
    checkpoint-dispatch-package-not-adopted, so recovery goes through
    dispatch.advance, which adopts first when needed and then completes.

    Adoption needs premises a marker is never allowed to supply, so the
    journal limits and the epoch adoption pin are passed in by the caller.

    Still narrow in what it spends: the package is already captured, so no
    clock is sampled, no collector runs, and no sequence is reserved — the
    adoption reuses the sequence the marker already bound.
    """
    marker = dispatch.select(owner, memo=memo)
    if marker is None:
        return None
    _owned(owner, marker["directory"], configured_directory)
    # Only once a marker is actually present is a compact admitted status
    # required. Demanding it earlier would put a new status condition on a
    # pure legacy pulse that never had one.
    admitted_status = _status(owner, memo)
    return dispatch.advance(owner, admitted_status=admitted_status,
        journal_limits=journal_limits,
        expected_journal_limits_sha256=expected_journal_limits_sha256,
        expected_adoption_sha256=expected_adoption_sha256)


def chain_pending(owner, *, memo):
    """Whether durable state already names a chain for this pulse to continue.

    A pure question about retained state. Answering it costs no clock, no
    reserved sequence and no collector, so the caller can ask before
    deciding to sample anything. False is not evidence that no compact
    chain could exist, only that this memo names none.
    """
    return dispatch.select_chain(owner, memo=memo) is not None


def route(owner, *, memo, configured_directory, clock, journal_limits,
          expected_journal_limits_sha256, expected_adoption_sha256):
    """Take this pulse for the compact lane, or return None for the legacy one.

    The whole ordering lives here rather than at the call site, so the
    resident wrapper cannot drift from it.

    Recovery first: the package is already captured, so it samples no
    clock, runs no collector and reserves no sequence, reusing the one the
    marker bound. It goes through the adopting entry because a marker is
    written before adoption, so a legitimate crash can leave a
    recorded-but-unadopted package.

    Then continuation, which captures and therefore reserves a sequence
    and samples the clock — but only once it is certain there is a chain
    to continue, never to discover whether there is one. The clock stays a
    lazy closure, as on the legacy lane.

    Then bootstrap, which may start a chain for an already enabled,
    already adopted and independently acknowledged controller. It returns
    None whenever the legacy lane should keep the pulse, so the
    no-adoption, initial and pending routes are reached exactly as before.
    """
    premises = dict(journal_limits=journal_limits,
        expected_journal_limits_sha256=expected_journal_limits_sha256,
        expected_adoption_sha256=expected_adoption_sha256)
    recovered = recover(owner, memo=memo,
        configured_directory=configured_directory, **premises)
    if recovered is not None:
        return recovered
    # A pointer naming any other directory is refused before any write; the
    # prelude below commits notes and settles thought pages, so the head's
    # directory is admitted first, exactly as advance() will admit it again.
    pointer = dispatch.select_chain(owner, memo=memo)
    if pointer is not None:
        _owned(owner, pointer["directory"], configured_directory)
    notes = converge_legacy_authority(owner, memo)
    try:
        if chain_pending(owner, memo=memo):
            view = advance(owner, memo=memo, clock=clock,
                configured_directory=configured_directory, **premises)
        else:
            view = bootstrap(owner, memo=memo, clock=clock,
                configured_directory=configured_directory, **premises)
    except source.SourceBatchRefusal as exc:
        if exc.reason not in CAPACITY_REASONS:
            raise
        # The retained lane has no rollover: every capture carries every
        # page version and observation since adoption, and the ceilings
        # are final. Left alone this refusal repeats on every later pulse
        # with nothing an operator could change. Retire the lane under a
        # receipt and hand this pulse back to the legacy route; with the
        # opt-in still on, the next capture starts a fresh segment.
        retire(owner, memo=memo, apply=True,
               reason="capacity: " + exc.reason,
               retired_at=int(owner["time"].time()))
        owner["log"]("controller-source lane retired at capacity ("
                     + exc.reason + "): " + RETIREMENT_NOTE)
        return None
    if view is not None:
        if notes:
            acknowledge_agent_notes(owner, memo, notes)
        # The legacy pulse finalizes the native thought mind replay after
        # every transaction's final memo image: applied receipts whose exact
        # producer (an acknowledged queue id) is gone are retired and an
        # empty catalog is removed. Until then readiness names it pending,
        # so this runs after every completed compact pulse, notes or not.
        owner["_finalize_native_thought_mind_replay"]()
    return view


CAPACITY_REASONS = frozenset({
    "complete-byte-capacity", "complete-json-byte-capacity",
    "complete-version-or-observation-capacity", "complete-content-capacity",
})
RETIRED_KEYS = ("controller_source_committed", "controller_checkpoint_chain",
                "controller_delivery_epoch", "live_loop_committed")
RETIRED_FILES = (("live_generation", "LIVE_STATE_PATH"),
                 ("live_candidate", "LIVE_CANDIDATE_PATH"))
RETIREMENT_SCHEMA = "sia-controller-source-retirement-v1"
RETIREMENT_DIRECTORY = "controller-source-superseded"
RETIREMENT_NOTE = ("the checkpoint chain has no rollover; its archives, chain "
                   "and epoch records are retained and named by the receipt; "
                   "with mind.controller_source still true the next pulse "
                   "starts a fresh segment, with it false the released lane "
                   "resumes")
RETIREMENT_NON_CLAIMS = (
    "Retirement releases the memo's controller-source, checkpoint-chain and delivery-epoch authority; it deletes no archive, chain document, epoch record or corpus page.",
    "The retained receipt names what was released and why; it is not an acknowledgment, a publication, a cursor change or evidence about the retired lane's content.",
    "A fresh segment after retirement starts a new live lineage: the retired live generation and candidate are moved beside the receipt, named by digest, not carried forward.",
)


def retirement_pending(owner, memo):
    """Name the in-flight authority that forbids retirement, or None.

    A pending source batch is in flight only while it continues the lane
    being retired. With no committed predecessor it is the initial batch of
    a fresh segment; retiring the stale live lineage under it is exactly the
    repair that lets it complete.
    """
    held = [key for key in (dispatch._MARKER, "controller_source_live_pending",
                            "controller_source_effects_pending",
                            "controller_source_effects_committed",
                            "pulse_status_effects_pending", "live_loop_pending")
            if key in memo]
    if "controller_source_committed" in memo:
        if "controller_source_pending" in memo:
            held.append("controller_source_pending")
        if owner["_live_present"](owner["CONTROLLER_SOURCE_BATCH_PATH"]):
            held.append("controller-source-batch")
    return held or None


def retire(owner, *, memo, apply, reason, retired_at):
    """Release the retained lane's memo authority under a receipt.

    The receipt is durable before the memo changes, so an interrupted
    retirement leaves both the receipt and the still-authoritative memo,
    never a released memo without its receipt. Nothing under
    controller-source-archive, controller-checkpoint-chain or the epoch
    records directory is touched. With apply false the report names what
    would be released and writes nothing.
    """
    if type(owner) is not dict or type(memo) is not dict:
        raise TypeError("owner and memo must be dictionaries")
    if type(reason) is not str or not reason or len(reason) > 160:
        source.refuse("controller-retirement-reason")
    if type(retired_at) is not int or isinstance(retired_at, bool) or retired_at < 0:
        source.refuse("controller-retirement-clock")
    held = retirement_pending(owner, memo)
    if held is not None:
        source.refuse("controller-retirement-in-flight")
    retired = {key: memo[key] for key in RETIRED_KEYS if key in memo}
    files = {}
    for label, name in RETIRED_FILES:
        path = owner[name]
        if owner["_live_present"](path):
            with open(path, "rb") as stream:
                digest = owner["hashlib"].sha256(stream.read()).hexdigest()
            files[label] = {"path": path, "sha256": digest}
    if not retired and not files:
        source.refuse("controller-retirement-nothing-retained")
    directory = os.path.join(owner["STATE"], RETIREMENT_DIRECTORY)
    receipt = {
        "schema": RETIREMENT_SCHEMA, "retired_at": retired_at, "reason": reason,
        "retired": retired,
        "retired_sha256": {key: source.native_sha(owner, value)
                           for key, value in retired.items()},
        "retired_files": {label: dict(row, retained_as=os.path.join(
            directory, "retired-" + row["sha256"] + "." + label + ".json"))
            for label, row in files.items()},
        "retained": ["controller-source-archive", "controller-checkpoint-chain",
                     "controller-source-effects-archive", "controller-delivery-epochs"],
        "non_claims": list(RETIREMENT_NON_CLAIMS),
    }
    receipt["receipt_sha256"] = source.native_sha(
        owner, {key: value for key, value in receipt.items() if key != "receipt_sha256"})
    report = {"schema": RETIREMENT_SCHEMA, "applied": bool(apply),
              "reason": reason, "released": sorted(retired),
              "moved": sorted(files), "receipt_sha256": receipt["receipt_sha256"]}
    if not apply:
        return report
    owner["ensure_durable_directory"](directory, mode=0o700)
    path = os.path.join(directory, "retired-" + receipt["receipt_sha256"] + ".json")
    owner["atomic_write"](path, source.native_bytes(owner, receipt).decode("ascii"), mode=0o600)
    # Receipt first, then the files, then the memo: an interruption leaves
    # the receipt naming what was meant, never a released memo without one.
    for label, row in receipt["retired_files"].items():
        os.replace(row["path"], row["retained_as"])
    released = {key: value for key, value in memo.items() if key not in retired}
    owner["_write_memo"](released)
    memo.clear()
    memo.update(owner["load_memo"]())
    if any(key in memo for key in retired) or owner["_live_started"](memo):
        source.refuse("controller-retirement-not-released")
    report["receipt"] = path
    return report


def converge_legacy_authority(owner, memo):
    """Advance take/intent provenance before a fresh compact link captures.

    The legacy lane converged upgrade provenance in its recovery prelude on
    every pulse: interrupted natural-history and grade transactions, then
    legacy take migration and intent history. The compact lane never did,
    so once it owned the resident pulse a filesystem move, an external
    corpus edit or a runtime upgrade closed every memory surface behind
    `take_migration_required` / `intent_history_required` with no pulse
    that could ever clear them. This runs only ahead of a fresh capture,
    never between a captured package and its completion, so nothing is
    published inside a package's window. Refusals are the same closed
    reason codes the legacy prelude raised.
    """
    takes = owner["siatakes"]
    fence = lambda: owner["_mark_external_corpus_mutation"](memo)
    _recovered, errors = takes.recover_natural_history_transactions(
        before_publish=fence)
    if errors:
        raise RuntimeError(f"natural-history recovery refused: {errors}")
    _recovered, errors = takes.recover_grade_transactions(before_publish=fence)
    if errors:
        raise RuntimeError(f"grade recovery refused: {errors}")
    owner["_reconcile_legacy_memory_authority"](memo)
    return materialize_agent_notes(owner, memo)


def materialize_agent_notes(owner, memo):
    """Write queued agent-note pages before a fresh capture.

    Agents queue immutable note requests; only the resident pulse turns
    them into corpus pages. The legacy pulse did that inside its own
    transaction and acknowledged the requests after its commit and index
    sync. The compact lane never did either, so on a machine where it owns
    the pulse every `sia note` and MCP `note` stayed queued (56 requests
    over nine days on the maintainer machine). Materialization is the
    legacy lane's own deterministic writer: a page named by request id,
    identical on every repeat, one thought per request. The pages are
    committed here so the capture that follows observes a clean tree, and
    the requests are acknowledged only after that capture's pulse completes
    (its effects synchronize the corpus into the index). A refused pulse
    leaves them queued; the next prelude repeats without duplication.
    Returns the materialized (path, identity) pairs to acknowledge.
    """
    dumps = owner["json"].dumps
    store = owner["load_thoughts"]()
    receipts = dumps(memo.get("agent_note_redaction_receipts"), sort_keys=True)
    paths, pages, thoughts, errors = owner["materialize_agent_notes"](store, memo)
    if thoughts:
        owner["export_thoughts"](store)
    # A note's thought registers a page-recovery intent that only the legacy
    # settlement writes, exports and acknowledges; without it `sia ready`
    # refuses "thought page recovery intents are pending" on every read.
    # Settle here, before the capture, exactly as the legacy pulse does
    # before new work. Bounded legacy baselines that remain are named by
    # readiness and retried by the next prelude.
    # The settlement acquires the corpus lease itself when the caller does
    # not hold it; the prelude never re-enters a lease. The resident pulse
    # always holds it here, and a driver that does not is not a pulse.
    if owner["_CORPUS_OWNER_DEPTH"].get() > 0:
        try:
            owner["_settle_thought_page_signals"](store)
        except owner["ThoughtRecoveryPending"] as exc:
            owner["log"]("thought page recovery still pending: " + str(exc)[:160])
    if pages:
        pass
    if pages or owner["corpus_dirty"]():
        if owner["corpus_commit"]("SIA agent notes") == "error":
            raise RuntimeError("agent-note corpus commit refused")
        owner["_mark_external_corpus_mutation"](memo)
    if dumps(memo.get("agent_note_redaction_receipts"), sort_keys=True) != receipts:
        owner["_write_memo"](memo)
    for error in errors:
        owner["log"]("agent note REFUSED: " + str(error.get("file"))[:80]
                     + ": " + str(error.get("error"))[:160])
    return paths


def acknowledge_agent_notes(owner, memo, notes):
    """Acknowledge materialized requests once their pulse has completed."""
    memo.clear()
    memo.update(owner["load_memo"]())
    acknowledged, errors = owner["acknowledge_agent_notes"](
        notes, "committed", True,
        after_ack=lambda identity:
            owner["_forget_agent_note_redaction_receipt"](memo, identity))
    if acknowledged:
        owner["_write_memo"](memo)
        owner["log"](f"agent notes acknowledged: {acknowledged}")
    for error in errors:
        owner["log"]("agent note acknowledgement REFUSED: "
                     + str(error.get("file"))[:80] + ": "
                     + str(error.get("error"))[:160])


def advance(owner, *, memo, configured_directory, clock, journal_limits,
            expected_journal_limits_sha256, expected_adoption_sha256):
    """Continue the retained chain by one link, or return None.

    The selection is persisted before the capture that may fence, so an
    interrupted pulse reopens the head it chose rather than inferring one.
    A pointer whose head is the bootstrap root is the ordinary first link.

    A fresh link reserves the pulse sequence exactly once, durably, before
    the clock is sampled and before anything is captured. A retry — a
    selection already in flight — reuses that reservation instead of
    manufacturing a new observation. A crash between the reservation and
    the selection leaves a sequence gap, which the existing design already
    tolerates; what it never does is reuse a sequence.
    """
    pointer = dispatch.select_chain(owner, memo=memo)
    if pointer is None:
        return None
    directory = _owned(owner, pointer["directory"], configured_directory)
    # Creation happens only after the binding is admitted. Creating the
    # configured root first would mean a mismatched pointer had already
    # caused a write before it was refused.
    owner["ensure_durable_directory"](directory, mode=0o700)
    committed = memo.get("controller_source_committed")
    if type(committed) is not dict:
        source.refuse("checkpoint-cycle-source-authority")
    status = _status(owner, memo)
    root_sha256 = pointer["root_sha256"]

    if pointer["status"] == dispatch._CHAIN_STATUS:
        # A selection is already in flight from an earlier pulse. Reopen it
        # by its recorded pins; do not choose a new head.
        head = pointer["head_sha256"]
        dispatch.reopen_chain(owner, memo=memo)
    else:
        # Fresh link: reserve once, durably, ahead of clock and capture.
        reserved = runner._sequence(owner, memo, reservable=True) + 1
        memo["pulse_seq"] = reserved
        owner["_write_memo"](memo)
        status = _status(owner, memo)
        retained = dict(directory=directory, committed=committed)
        parents.retain_graph(owner, **retained)
        parents.retain_checkpoint_live(owner, **retained, memo=memo,
            admitted_status=status)
        built = roots.prepare_successor(owner, memo=memo, admitted_status=status,
            directory=directory, expected_root_sha256=root_sha256,
            expected_head_sha256=pointer["head_sha256"])
        head = built["successor_sha256"]
        # Durable before capture. Capture is what can raise the fence.
        dispatch.record_chain(owner, memo=memo, directory=directory,
            expected_root_sha256=root_sha256, expected_head_sha256=head)

    memo.clear()
    memo.update(owner["load_memo"]())
    status = _status(owner, memo)
    shared = dict(memo=memo, admitted_status=status, directory=directory,
        expected_root_sha256=root_sha256, observed_at=clock(),
        journal_limits=journal_limits,
        expected_journal_limits_sha256=expected_journal_limits_sha256,
        expected_adoption_sha256=expected_adoption_sha256)
    if head == root_sha256:
        # An interrupted bootstrap, resumed. The chain is still at
        # generation zero, so its package is a ROOT package. Using the
        # successor preparer here would aim a compact predecessor reader
        # at a legacy acknowledgment, which rightly refuses
        # checkpoint-capture-shape. The reservation and pins already made
        # are reused; nothing is chosen again.
        package = transaction.prepare_root(owner, **shared)
    else:
        package = transaction.prepare_successor(
            owner, expected_head_sha256=head, **shared)
    return _finish(owner, memo=memo, directory=directory,
        root_sha256=root_sha256, package=package,
        journal_limits=journal_limits,
        expected_journal_limits_sha256=expected_journal_limits_sha256,
        expected_adoption_sha256=expected_adoption_sha256)


def _finish(owner, *, memo, directory, root_sha256, package, journal_limits,
            expected_journal_limits_sha256, expected_adoption_sha256):
    """Record, adopt and dispatch one prepared package.

    Shared by bootstrap and continuation because the tail is genuinely the
    same: only how the package was prepared differs.
    """
    pins = dict(directory=directory,
        expected_manifest_sha256=package["manifest_sha256"],
        expected_root_sha256=root_sha256)
    memo.clear()
    memo.update(owner["load_memo"]())
    status = _status(owner, memo)
    dispatch.record(owner, memo=memo, **pins, started_at=status["ts"],
        seq=memo["pulse_seq"])
    adoption.adopt_root(owner, memo=memo, admitted_status=status, **pins,
        seq=memo["pulse_seq"], journal_limits=journal_limits,
        expected_journal_limits_sha256=expected_journal_limits_sha256,
        expected_adoption_sha256=expected_adoption_sha256)
    return dispatch.dispatch(owner)


def bootstrap(owner, *, memo, configured_directory, clock, journal_limits,
              expected_journal_limits_sha256, expected_adoption_sha256):
    """Start a compact chain from an adopted, acknowledged controller.

    No new operator choice gates this, and none is invented. Continuing a
    controller the operator already enabled, inside storage this code
    already owns, is internal. The authority is what is already present:
    the opt-in the caller established before routing here, a completed
    legacy predecessor admitted through its own reader rather than
    believed from the memo, and an actual adopted delivery epoch.
    _controller_source_enabled is neither read nor altered here.

    Returns None whenever the legacy lane should keep this pulse, so the
    no-adoption, initial and pending routes are left exactly as they are.
    """
    import siasourceack as ack

    if dispatch.select(owner, memo=memo) is not None \
            or dispatch.select_chain(owner, memo=memo) is not None:
        # Those belong to the other two branches; arriving here with
        # either is a contradiction, not something to work around.
        source.refuse("checkpoint-bootstrap-chain-present")
    if expected_adoption_sha256 is None:
        return None                       # legacy no-adoption route
    if source._SUCCESSOR_PENDING_KEYS.intersection(memo):
        return None                       # legacy initial/pending prefix
    committed = memo.get("controller_source_committed")
    if type(committed) is not dict:
        return None
    # A fence outstanding before any root selection exists is a named
    # fail-closed boundary: there is nothing yet to recover to. A fence
    # raised BY the capture below is a different case and does recover,
    # because the root=head selection is durable before capture starts.
    if source._notification_marker(owner, memo) is not None:
        source.refuse("checkpoint-bootstrap-notification-fence")
    status = _status(owner, memo)
    completed = ack.read_completed(owner, memo=memo, admitted_status=status)
    if type(completed) is not dict or completed.get("status") != "available" \
            or completed.get("committed") != committed:
        source.refuse("checkpoint-bootstrap-source-authority")

    # Only now, once eligible, is anything created.
    owner["ensure_durable_directory"](configured_directory, mode=0o700)
    root = roots.prepare(owner, memo=memo, admitted_status=status,
        directory=configured_directory)
    root_sha256 = root["root_sha256"]
    reserved = runner._sequence(owner, memo, reservable=True) + 1
    memo["pulse_seq"] = reserved
    owner["_write_memo"](memo)
    memo.clear()
    memo.update(owner["load_memo"]())
    status = _status(owner, memo)
    # root = head at generation zero, durable before the capture that can
    # raise a fence. This is what makes such a fence recoverable.
    dispatch.record_chain(owner, memo=memo, directory=configured_directory,
        expected_root_sha256=root_sha256, expected_head_sha256=root_sha256)
    memo.clear()
    memo.update(owner["load_memo"]())
    status = _status(owner, memo)
    # A root package, not a successor one: prepare_successor needs a head
    # document that does not exist until this chain has a link.
    package = transaction.prepare_root(owner, memo=memo,
        admitted_status=status, directory=configured_directory,
        expected_root_sha256=root_sha256, observed_at=clock(),
        journal_limits=journal_limits,
        expected_journal_limits_sha256=expected_journal_limits_sha256,
        expected_adoption_sha256=expected_adoption_sha256)
    return _finish(owner, memo=memo, directory=configured_directory,
        root_sha256=root_sha256, package=package,
        journal_limits=journal_limits,
        expected_journal_limits_sha256=expected_journal_limits_sha256,
        expected_adoption_sha256=expected_adoption_sha256)
