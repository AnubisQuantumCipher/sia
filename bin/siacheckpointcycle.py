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

import siacheckpointadoption as adoption
import siacheckpointdispatch as dispatch
import siacheckpointparent as parents
import siacheckpointtransaction as transaction
import siacontrollersourcerunner as runner
import siahistoryroot as roots
import siasourcebatch as source


NON_CLAIMS = (
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
