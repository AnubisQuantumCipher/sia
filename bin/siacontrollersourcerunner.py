"""Closed dispatchers for resident controller-source transactions.

The caller supplies the resident ``sialib`` global namespace as ``owner`` and
a lazy, zero-argument ``operation`` that constructs the initial source-capture
request.  Durable source-owned prefixes are always resumed without invoking
that operation or allocating another pulse sequence.  The v1 entry remains
terminal at a completed transaction.  The additive v2 entry advances a
completed transaction only through an explicit successor epoch, capture front
door, and fixed-slot write-ahead batch.

The additive v3 dispatcher advances a completed legacy/v3 source through an
actually adopted delivery epoch and genuine source-v3 capture. Its caller
holds the resident and corpus owners continuously. Existing initial/pending
transactions still delegate to the original dispatcher and may finish as
legacy; no source schema is relabeled and no resident mode is activated here.
"""

import copy
import re


_REQUEST_KEYS = frozenset({
    "epoch", "expected_epoch_sha256", "observed_at",
})
_SOURCE_PENDING_KEYS = frozenset({
    "controller_source_pending",
    "controller_source_live_pending",
    "pulse_status_effects_pending",
    "controller_source_effects_pending",
    "controller_source_effects_committed",
})
_COMMITTED_KEYS = frozenset({
    "source_batch_sha256", "live_generation_sha256",
    "source_effects_receipt_sha256",
})
_V3_RECOVERY_PREFLIGHT_KEYS = frozenset({
    "policy", "memo", "admitted_status", "retained_batch", "committed",
    "successor_batch",
})
# A fixed-WAL recovery preflight retains six separately bounded documents plus
# one structural-overhead unit. Individual state/memo ceilings remain intact.
# Arithmetic evidence: status=exact, parsed=7*16777216, exact=117440512.
# Exact rational arithmetic outside the Lean certificate chain; NOT
# formal-bounded.
MAX_V3_RECOVERY_PREFLIGHT_DOCUMENTS = 7
MAX_V3_RECOVERY_PREFLIGHT_BYTES = 117_440_512
_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _refuse(reason):
    raise RuntimeError("controller source runner refused: " + reason)


def _v3_recovery_preflight_capacity(owner):
    if type(MAX_V3_RECOVERY_PREFLIGHT_DOCUMENTS) is not int \
            or MAX_V3_RECOVERY_PREFLIGHT_DOCUMENTS \
            != len(_V3_RECOVERY_PREFLIGHT_KEYS) + 1 \
            or type(MAX_V3_RECOVERY_PREFLIGHT_BYTES) is not int \
            or MAX_V3_RECOVERY_PREFLIGHT_BYTES <= 0:
        _refuse("v3 recovery preflight capacity contract changed")
    scaled = (MAX_V3_RECOVERY_PREFLIGHT_DOCUMENTS
              * owner["MAX_STATE_JSON_BYTES"])
    return min(scaled, MAX_V3_RECOVERY_PREFLIGHT_BYTES)


def _history_entry(batch):
    """Return the exact history row contributed by one retained batch."""
    if type(batch) is not dict or type(batch.get("source_returns")) is not dict:
        _refuse("successor-wal-history")
    closure = batch.get("event_closure")
    if closure is None:
        batches = []
    elif type(closure) is dict and type(closure.get("batches")) is list:
        batches = closure["batches"]
    else:
        _refuse("successor-wal-history")
    try:
        return {
            "source_returns": copy.deepcopy(batch["source_returns"]),
            "expected_source_returns_sha256":
                batch["source_returns"]["returns_sha256"],
            "event_batches": [
                {
                    "batch": copy.deepcopy(member),
                    "expected_batch_sha256": member["batch_sha256"],
                }
                for member in batches
            ],
        }
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise RuntimeError(
            "controller source runner refused: successor-wal-history") \
            from exc


def validate_successor_wal(
        owner, *, retained_batch, committed, successor_batch,
        expected_batch_sha256):
    """Validate the complete predecessor/history relationship of a WAL.

    Batch validation is delegated to the source boundary first.  This
    additional check proves that the new retained batch is the one-step
    continuation of the exact compact completion authority supplied by the
    caller; it neither reads current sources nor publishes state.
    """
    if type(owner) is not dict:
        raise TypeError("owner must be a globals-style dictionary")
    import siasourcebatch as source

    if type(retained_batch) is not dict \
            or type(successor_batch) is not dict \
            or type(committed) is not dict \
            or set(committed) != _COMMITTED_KEYS \
            or any(type(value) is not str or _HEX.fullmatch(value) is None
                   for value in committed.values()) \
            or type(retained_batch.get("batch_sha256")) is not str \
            or retained_batch.get("batch_sha256") \
               != committed["source_batch_sha256"]:
        _refuse("successor-wal-commit")
    if type(expected_batch_sha256) is not str \
            or _HEX.fullmatch(expected_batch_sha256) is None \
            or successor_batch.get("batch_sha256") != expected_batch_sha256:
        _refuse("successor-wal-successor-pin")

    source.validate_batch(
        owner, retained_batch, retained_batch["batch_sha256"])
    source.validate_batch(
        owner, successor_batch, expected_batch_sha256)

    if retained_batch.get("schema") == "sia-controller-source-batch-v3" \
            and successor_batch.get("schema") != "sia-controller-source-batch-v3":
        _refuse("successor-wal-delivery-downgrade")
    if successor_batch.get("schema") == "sia-controller-source-batch-v3":
        delivery = successor_batch["delivery_input"]
        # Pure wrapper replay establishes represented consistency only.
        # Join its declaration to the actual retained source and complete
        # completion receipt, including the consumed effects receipt pin.
        if delivery["parent_source_schema"] != retained_batch.get("schema") \
                or delivery["epoch_view"]["parent_committed"] != committed:
            _refuse("successor-wal-delivery-parent")
        if retained_batch.get("schema") == "sia-controller-source-batch-v3" \
                and delivery["expected_adoption_sha256"] \
                != retained_batch["delivery_input"]["expected_adoption_sha256"]:
            _refuse("successor-wal-delivery-adoption")

    prior_epoch = retained_batch.get("epoch")
    next_epoch = successor_batch.get("epoch")
    if type(prior_epoch) is not dict or type(next_epoch) is not dict:
        _refuse("successor-wal-predecessor")
    expected_predecessor = {
        "source_batch_sha256": retained_batch["batch_sha256"],
        "live_generation_sha256": committed["live_generation_sha256"],
    }
    if next_epoch.get("predecessor") != expected_predecessor \
            or next_epoch.get("epoch_id") != prior_epoch.get("epoch_id") \
            or next_epoch.get("started_at") != prior_epoch.get("started_at"):
        _refuse("successor-wal-predecessor")

    prior_history = prior_epoch.get("history")
    next_history = next_epoch.get("history")
    if type(prior_history) is not dict or type(next_history) is not dict \
            or type(prior_history.get("entries")) is not list \
            or type(next_history.get("entries")) is not list:
        _refuse("successor-wal-history")
    expected_entries = copy.deepcopy(prior_history["entries"])
    expected_entries.append(_history_entry(retained_batch))
    if next_history["entries"] != expected_entries:
        _refuse("successor-wal-history")

    # The production epoch has these immutable documents.  Minimal stopped
    # seam fixtures omit them, but a one-sided omission in any represented
    # input is always a relationship failure (batch validation catches an
    # omission in a real source batch before this comparison).
    for field in (
            "configuration", "source_catalog", "profile", "live_policy",
            "expected_configuration_sha256",
            "expected_source_catalog_sha256", "expected_profile_sha256",
            "expected_live_policy_sha256", "non_claims"):
        if (field in prior_epoch) != (field in next_epoch) \
                or field in prior_epoch \
                and prior_epoch[field] != next_epoch[field]:
            _refuse("successor-wal-history")
    return None


def _published_effects_prefix(memo, effects, *, committed):
    """Join the published prefix that legitimately retires the handoff.

    This only selects a recovery branch. Effects replay and source ACK still
    validate the retained artifacts through their existing front doors.
    """
    source = memo.get("controller_source_pending")
    binding = memo.get("controller_source_live_pending")
    live = memo.get("live_loop_committed")
    if any(type(value) is not dict
           for value in (source, binding, live, effects)):
        return False
    if source.get("schema") != "sia-controller-source-pending-v1" \
            or binding.get("schema") != "sia-controller-source-live-pending-v1" \
            or live.get("schema") != "sia-live-publication-receipt-v1":
        return False
    status = effects.get("status_generation")
    publication_id = live.get("publication_id")
    seq = live.get("pulse_seq")
    if type(status) is not dict \
            or type(publication_id) is not str \
            or re.fullmatch(r"[0-9a-f]{32}", publication_id) is None \
            or publication_id != binding.get("publication_id") \
            or publication_id != status.get("publication_id") \
            or type(seq) is not int or seq < 0 \
            or type(binding.get("seq")) is not int \
            or type(memo.get("pulse_seq")) is not int \
            or seq != binding["seq"] or seq != memo["pulse_seq"] \
            or type(live.get("epoch_id")) is not str \
            or not live["epoch_id"] \
            or live["epoch_id"] != source.get("epoch_id"):
        return False
    for key in ("state_sha256", "transition_sha256", "candidate_sha256",
                "generation_sha256", "status_sha256"):
        if type(live.get(key)) is not str \
                or _HEX.fullmatch(live[key]) is None:
            return False
    parent = live.get("parent_generation_sha256")
    if "parent_generation_sha256" not in live \
            or "parent_generation_sha256" not in binding \
            or parent != binding["parent_generation_sha256"] \
            or parent is not None and (
                type(parent) is not str or _HEX.fullmatch(parent) is None):
        return False
    for key in ("state_sha256", "transition_sha256"):
        if live[key] != binding.get(key) or live[key] != effects.get(key):
            return False
    for key, source_key, binding_key in (
            ("source_batch_sha256", "batch_sha256", "source_batch_sha256"),
            ("source_batch_wire_sha256", "batch_wire_sha256",
             "source_batch_wire_sha256")):
        value = effects.get(key)
        if type(value) is not str or _HEX.fullmatch(value) is None \
                or value != source.get(source_key) \
                or value != binding.get(binding_key):
            return False
    for key, binding_key in (
            ("source_live_publication_sha256", "publication_sha256"),
            ("prepare_inputs_sha256", "prepare_inputs_sha256")):
        value = effects.get(key)
        if type(value) is not str or _HEX.fullmatch(value) is None \
                or value != binding.get(binding_key):
            return False
    if status.get("semantic_sha256") != live["status_sha256"]:
        return False
    if committed:
        generation = effects.get("live_generation")
        if type(generation) is not dict or any(
                generation.get(key) != live[key] for key in (
                    "publication_id", "candidate_sha256",
                    "generation_sha256", "status_sha256")):
            return False
    return True


def _source_state(memo):
    """Classify only the durable source prefixes this runner can resume."""
    if type(memo) is not dict:
        _refuse("memo is not an object")

    completed = "controller_source_committed" in memo
    source_pending = "controller_source_pending" in memo
    live_pending = "controller_source_live_pending" in memo
    handoff_pending = "pulse_status_effects_pending" in memo
    effects_pending = "controller_source_effects_pending" in memo
    effects_committed = "controller_source_effects_committed" in memo

    if completed:
        if any(key in memo for key in _SOURCE_PENDING_KEYS):
            _refuse("completed state retains pending authority")
        return "completed"

    if effects_pending and effects_committed:
        _refuse("effects state is ambiguous")
    if not source_pending:
        if live_pending or handoff_pending \
                or effects_pending or effects_committed:
            _refuse("downstream state lacks source authority")
        return "absent"
    if effects_pending or effects_committed:
        if not live_pending:
            _refuse("effects state lacks its durable prefix")
        if not handoff_pending:
            effects = memo["controller_source_effects_pending" if effects_pending
                           else "controller_source_effects_committed"]
            if not _published_effects_prefix(
                    memo, effects, committed=effects_committed):
                _refuse("effects state lacks its joined published prefix")
        return "effects-pending" if effects_pending else "effects-committed"
    if handoff_pending:
        if not live_pending:
            _refuse("status handoff lacks live binding")
        return "handoff"
    if live_pending:
        return "binding"
    return "batch"


def _sequence(owner, memo, *, reservable=False):
    seq = memo.get("pulse_seq", 0)
    ceiling = owner["MAX_JSON_SAFE_INTEGER"]
    if type(seq) is not int or seq < 0 or seq > ceiling:
        _refuse("pulse sequence is invalid")
    if reservable and seq >= ceiling:
        _refuse("pulse sequence is exhausted")
    return seq


def _admit_status(owner, memo):
    return owner["_require_status_sequence_not_ahead"](
        _sequence(owner, memo))


def _initial_request(owner, memo, operation):
    """Reserve once, then lazily capture and retain the initial batch."""
    current = _sequence(owner, memo, reservable=True)
    admitted_status = owner["_require_status_sequence_not_ahead"](current)
    seq = current + 1
    memo["pulse_seq"] = seq
    owner["_write_memo"](memo)

    request = operation()
    if type(request) is not dict or set(request) != _REQUEST_KEYS:
        _refuse("initial capture request fields differ")
    batch = owner["_capture_controller_source_batch"](
        memo=memo, epoch=request["epoch"],
        expected_epoch_sha256=request["expected_epoch_sha256"],
        observed_at=request["observed_at"])
    if type(batch) is not dict \
            or type(batch.get("batch_sha256")) is not str:
        _refuse("captured batch is invalid")
    owner["_stage_controller_source_batch"](
        memo=memo, batch=batch,
        expected_batch_sha256=batch["batch_sha256"])
    if _source_state(memo) != "batch":
        _refuse("batch stage did not publish its durable prefix")
    return admitted_status, seq


def _pending_batch(owner, memo):
    view = owner["_read_pending_controller_source_batch"](memo=memo)
    if type(view) is not dict or view.get("status") != "pending" \
            or type(view.get("batch")) is not dict:
        _refuse("pending batch is unavailable")
    batch = view["batch"]
    if type(batch.get("batch_sha256")) is not str:
        _refuse("pending batch digest is invalid")
    return batch


def _stage_handoff(owner, memo, admitted_status):
    """Replay the pure bound input and retain the status-effects handoff."""
    import sialiveloop

    batch = _pending_batch(owner, memo)
    binding = owner["_controller_source_live_binding_marker"](memo)
    if type(binding) is not dict:
        _refuse("live binding is unavailable")
    candidate = owner["_prepare_controller_source_live_candidate"](
        memo=memo, admitted_status=admitted_status)
    if type(candidate) is not dict \
            or set(candidate) != {
                "prepare_inputs", "expected_prepare_inputs_sha256"}:
        _refuse("live candidate is invalid")
    transition = sialiveloop.prepare_pulse(**candidate["prepare_inputs"])
    if type(transition) is not dict \
            or type(transition.get("transition_sha256")) is not str:
        _refuse("live transition is invalid")
    owner["_stage_controller_source_status_effects"](
        memo=memo, admitted_status=admitted_status, batch=batch,
        expected_batch_sha256=batch["batch_sha256"],
        source_live_pending=binding, candidate=candidate,
        transition=transition,
        expected_transition_sha256=transition["transition_sha256"],
        started_at=owner["iso"]())
    if _source_state(memo) != "handoff":
        _refuse("status handoff did not publish its durable prefix")


def run(owner, *, operation):
    """Run or recover the terminal initial controller-source transaction."""
    if type(owner) is not dict:
        raise TypeError("owner must be a globals-style dictionary")
    if not callable(operation):
        raise TypeError("operation must be callable")

    memo = owner["load_memo"]()
    owner["_require_status_memo_fields"](memo)
    state = _source_state(memo)

    if state == "completed":
        admitted_status = _admit_status(owner, memo)
        owner["_acknowledge_controller_source_batch"](
            memo=memo, admitted_status=admitted_status)
        fresh_status = _admit_status(owner, memo)
        return owner["copy"].deepcopy(fresh_status)

    if state == "absent":
        if owner["_controller_source_present"](memo):
            recovered = owner["_recover_orphan_controller_source_batch"](
                memo=memo)
            if recovered is not True or _source_state(memo) != "batch":
                _refuse("orphan batch recovery did not establish authority")
            state = "batch"
            seq = _sequence(owner, memo)
            admitted_status = owner[
                "_require_status_sequence_not_ahead"](seq)
        else:
            admitted_status, seq = _initial_request(
                owner, memo, operation)
            state = "batch"
    else:
        seq = _sequence(owner, memo)
        admitted_status = owner["_require_status_sequence_not_ahead"](seq)

    if state == "batch":
        owner["_stage_controller_source_live_binding"](
            memo=memo, admitted_status=admitted_status, seq=seq)
        if _source_state(memo) != "binding":
            _refuse("live binding did not publish its durable prefix")
        state = "binding"

    if state == "binding":
        _stage_handoff(owner, memo, admitted_status)
        state = "handoff"

    if state in ("handoff", "effects-pending"):
        owner["_publish_controller_source_effects"](
            memo=memo, admitted_status=admitted_status)
        if _source_state(memo) != "effects-committed":
            _refuse("source effects did not publish their durable receipt")
        fresh_status = _admit_status(owner, memo)
    elif state == "effects-committed":
        # This admission occurred after the durable effects prefix and is the
        # status authority the ACK seam revalidates.
        fresh_status = admitted_status
    else:
        _refuse("unhandled source state")

    owner["_acknowledge_controller_source_batch"](
        memo=memo, admitted_status=fresh_status)
    if _source_state(memo) != "completed":
        _refuse("acknowledgment did not publish terminal authority")
    return owner["copy"].deepcopy(fresh_status)


def _completed_view(owner, memo, admitted_status):
    view = owner["_read_committed_controller_source_batch"](
        memo=memo, admitted_status=admitted_status)
    if type(view) is not dict or set(view) != {
            "status", "batch", "committed"} \
            or view.get("status") != "available" \
            or type(view.get("batch")) is not dict \
            or type(view.get("committed")) is not dict:
        _refuse("completed source authority is unavailable")
    if view["committed"] != memo.get("controller_source_committed"):
        _refuse("completed source authority differs from memo")
    return view


def run_v2(owner, *, operation, clock):
    """Run/recover one transaction, rolling a completed epoch forward.

    A fixed successor batch is the only rollover WAL.  Until it is durable,
    the predecessor completion and readiness marker remain authoritative.  A
    retry that finds that WAL validates and adopts it without invoking the
    clock, epoch builder, collectors, capture, or allocation again.
    """
    if type(owner) is not dict:
        raise TypeError("owner must be a globals-style dictionary")
    if not callable(operation) or not callable(clock):
        raise TypeError("operation and clock must be callable")

    memo = owner["load_memo"]()
    owner["_require_status_memo_fields"](memo)
    state = _source_state(memo)
    if state != "completed":
        return run(owner, operation=operation)

    seq = _sequence(owner, memo)
    admitted_status = owner["_require_status_sequence_not_ahead"](seq)
    # Keep the v1 completed admission as a distinct, tested boundary.  Its
    # completed reader is successor-aware only insofar as it may ignore the
    # different fixed-slot digest while revalidating the predecessor archive.
    owner["_acknowledge_controller_source_batch"](
        memo=memo, admitted_status=admitted_status)
    view = _completed_view(owner, memo, admitted_status)
    retained_batch = view["batch"]
    committed = view["committed"]

    recovered = owner[
        "_recover_orphan_controller_source_successor_batch"](
            memo=memo, retained_batch=retained_batch,
            committed=committed, seq=seq)
    if recovered is True:
        if _source_state(memo) != "batch":
            _refuse("successor orphan adoption did not establish authority")
        return run(owner, operation=operation)
    if recovered is not False:
        _refuse("successor orphan probe returned an invalid result")

    seq = _sequence(owner, memo, reservable=True) + 1
    memo["pulse_seq"] = seq
    owner["_write_memo"](memo)

    observed_at = clock()
    import siacontrollerepoch
    request = siacontrollerepoch.build_successor(
        owner, retained_batch=retained_batch, committed=committed,
        observed_at=observed_at)
    if type(request) is not dict or set(request) != _REQUEST_KEYS:
        _refuse("successor capture request fields differ")
    batch = owner["_capture_controller_source_successor_batch"](
        memo=memo, retained_batch=retained_batch, committed=committed,
        epoch=request["epoch"],
        expected_epoch_sha256=request["expected_epoch_sha256"],
        observed_at=request["observed_at"])
    if type(batch) is not dict \
            or type(batch.get("batch_sha256")) is not str:
        _refuse("captured successor batch is invalid")
    validate_successor_wal(
        owner, retained_batch=retained_batch, committed=committed,
        successor_batch=batch,
        expected_batch_sha256=batch["batch_sha256"])
    owner["_retain_controller_source_successor_batch"](
        memo=memo, retained_batch=retained_batch, committed=committed,
        batch=batch, expected_batch_sha256=batch["batch_sha256"], seq=seq)
    owner["_controller_source_rollover_boundary"](
        "successor-batch-durable")

    recovered = owner[
        "_recover_orphan_controller_source_successor_batch"](
            memo=memo, retained_batch=retained_batch,
            committed=committed, seq=seq)
    if recovered is not True or _source_state(memo) != "batch":
        _refuse("successor batch adoption did not establish authority")
    return run(owner, operation=operation)


class _RunnerV3Admission:
    """Pin explicit rollover policy and owner scalars across its effects."""

    def __init__(self, owner, *, journal_limits, expected_journal_limits_sha256,
                 expected_adoption_sha256):
        import siadelivery
        import sialiveloop
        import siasourcebatch

        self.owner, self.source = owner, siasourcebatch
        self.paths = {name: owner.get(name) for name in (
            "HOME", "CORPUS", "STATE", "SHARE", "CONFIG_PATH", "CURSORS_PATH",
            "MEMO_PATH", "STATUS_PATH", "GRAPH_PATH", "LIVE_CANDIDATE_PATH",
            "LIVE_STATE_PATH", "CONTROLLER_SOURCE_BATCH_PATH",
            "CONTROLLER_SOURCE_ARCHIVE_DIR", "CONTROLLER_SOURCE_EFFECTS_ARCHIVE_DIR",
            "CONTROLLER_DELIVERY_EPOCH_ROOT", "CORPUS_OWNER_LOCK", "BRAINSTEM_OWNER_LOCK",
        )}
        self.capacities = {name: owner.get(name) for name in (
            "MAX_STATE_JSON_BYTES", "MAX_MEMO_BYTES", "MAX_CONFIG_PATH_CHARS",
            "MAX_CONFIG_TEXT_CHARS", "MAX_CONFIG_BYTES", "MAX_SOURCE_REPLAY_EVENTS",
            "MAX_SOURCE_REPLAY_SOURCES", "MAX_LEDGER_PENDING_RECORDS",
            "MAX_JSON_SAFE_INTEGER")}
        self.notification_key = owner.get("NOTIFY_BASELINE_ATTEMPT_KEY")
        if any(type(value) is not int or value <= 0 for value in self.capacities.values()) \
                or type(self.notification_key) is not str or not self.notification_key:
            _refuse("v3-owner-contract")
        self.recovery_capacity = _v3_recovery_preflight_capacity(owner)
        for name, value in self.paths.items():
            # Initial/pending legacy delegation does not invent an epoch
            # root. A completed rollover's actual epoch front door requires it.
            if name != "CONTROLLER_DELIVERY_EPOCH_ROOT" or value is not None:
                siasourcebatch._canonical_path(owner, value)
        self.basis_current()
        self.request = {
            "journal_limits": journal_limits,
            "expected_journal_limits_sha256": expected_journal_limits_sha256,
            "expected_adoption_sha256": expected_adoption_sha256,
        }
        self.raw = self.wire(self.request)
        self.basis_current()
        siadelivery._limits(journal_limits)
        if type(expected_journal_limits_sha256) is not str \
                or _HEX.fullmatch(expected_journal_limits_sha256) is None \
                or sialiveloop._sha(journal_limits) != expected_journal_limits_sha256:
            _refuse("v3-journal-limits-pin")
        if expected_adoption_sha256 is not None and (
                type(expected_adoption_sha256) is not str
                or _HEX.fullmatch(expected_adoption_sha256) is None):
            _refuse("v3-adoption-pin")
        self.basis_current()
        if self.wire(self.request) != self.raw:
            _refuse("v3-policy-input-changed")
        self.admitted = copy.deepcopy(self.request)
        self.current()

    def wire(self, value):
        return self.source.native_bytes(
            self.owner, value, ceiling=self.capacities["MAX_STATE_JSON_BYTES"])

    def recovery_wire(self, value):
        if type(value) is not dict \
                or set(value) != _V3_RECOVERY_PREFLIGHT_KEYS:
            _refuse("v3 recovery preflight shape")
        for name, member in value.items():
            self.source.native_bytes(
                self.owner, member,
                ceiling=(self.capacities["MAX_MEMO_BYTES"] if name == "memo"
                         else self.capacities["MAX_STATE_JSON_BYTES"]))
        try:
            return self.source.native_bytes(
                self.owner, value, ceiling=self.recovery_capacity)
        except self.source.SourceBatchRefusal as exc:
            if exc.reason == "complete-byte-capacity":
                _refuse("v3 recovery preflight aggregate exceeds its capacity")
            raise

    def basis_current(self):
        if _v3_recovery_preflight_capacity(self.owner) \
                != self.recovery_capacity:
            _refuse("v3-owner-basis-changed")
        for name, expected in {**self.paths, **self.capacities,
                               "NOTIFY_BASELINE_ATTEMPT_KEY": self.notification_key}.items():
            actual = self.owner.get(name)
            if type(actual) is not type(expected) or actual != expected:
                _refuse("v3-owner-basis-changed")

    def current(self):
        self.basis_current()
        if self.wire(self.request) != self.raw or self.wire(self.admitted) != self.raw:
            _refuse("v3-policy-input-changed")
        self.basis_current()


def _v3_completed_parent(owner, memo, admitted_status, marker):
    """Select the strict ready reader or the distinct capture-only reader."""
    if marker is None:
        owner["_acknowledge_controller_source_batch"](
            memo=memo, admitted_status=admitted_status)
        return _completed_view(owner, memo, admitted_status)
    import siasourceack
    import siasourcebatch

    marker_pin = siasourcebatch.native_sha(owner, marker)
    view = siasourceack.read_capturable_predecessor(
        owner, memo=memo, admitted_status=admitted_status,
        committed=memo.get("controller_source_committed"),
        notification_baseline_attempt=marker,
        expected_notification_baseline_attempt_sha256=marker_pin)
    if type(view) is not dict or set(view) != {
            "schema", "status", "batch", "committed", "notification_baseline_attempt",
            "expected_notification_baseline_attempt_sha256", "non_claims"} \
            or view["schema"] != "sia-controller-source-capturable-predecessor-v1" \
            or view["status"] != "capturable-not-ready" \
            or view["non_claims"] != list(siasourceack.CAPTURE_NON_CLAIMS) \
            or siasourcebatch.native_bytes(owner, view["notification_baseline_attempt"]) \
            != siasourcebatch.native_bytes(owner, marker) \
            or view["expected_notification_baseline_attempt_sha256"] != marker_pin \
            or view["committed"] != memo.get("controller_source_committed"):
        _refuse("v3-capturable-predecessor")
    return view


def _v3_adoption_pin(admission, memo, retained_batch):
    """Require caller authorization for every already committed adoption.

    None permits only unadopted legacy preparation, including a recoverable
    birth-pending prefix. It never adopts an existing pin from a wrapper.
    """
    import siacontrollerdeliveryepoch as epoch_api

    expected = admission.admitted["expected_adoption_sha256"]
    schema = retained_batch.get("schema")
    if schema not in {"sia-controller-source-batch-v1", "sia-controller-source-batch-v2",
                      "sia-controller-source-batch-v3"}:
        _refuse("v3-parent-source-schema")
    marker = memo.get(epoch_api._MARKER)
    if epoch_api._MARKER in memo:
        if type(marker) is not dict or set(marker) != epoch_api._MARKER_KEYS \
                or marker.get("schema") != "sia-controller-delivery-epoch-marker-v1":
            _refuse("v3-epoch-marker-shape")
    actual = None if marker is None else marker["adoption_sha256"]
    if expected is None:
        if schema == "sia-controller-source-batch-v3" or actual is not None:
            _refuse("v3-original-adoption-pin-required")
    elif actual != expected:
        _refuse("v3-original-adoption-pin-differs")
    admission.current()


def _v3_wal_parameters(admission, memo, batch, expected_adoption_sha256):
    """Join represented WAL parameters to caller pins and the actual memo.

    This pure relationship check does not promote its wrapper into source or
    epoch authority. The held WAL and existing recovery front door establish
    the actual immutable bytes and completed predecessor independently.
    """
    import siacontrollerdeliveryepoch as epoch_api

    if type(batch) is not dict or batch.get("schema") != "sia-controller-source-batch-v3" \
            or type(expected_adoption_sha256) is not str \
            or _HEX.fullmatch(expected_adoption_sha256) is None:
        _refuse("v3-successor-wal-required")
    wrapped = batch["delivery_input"]
    adopted = wrapped["epoch_view"]["epoch_adoption"]
    birth = adopted["birth"]
    if wrapped["expected_adoption_sha256"] != expected_adoption_sha256 \
            or adopted["expected_adoption_sha256"] != expected_adoption_sha256 \
            or admission.wire(birth["limits"]) != admission.wire(
                admission.admitted["journal_limits"]) \
            or birth["limits_sha256"] != admission.admitted["expected_journal_limits_sha256"] \
            or admission.wire(memo.get(epoch_api._MARKER)) != admission.wire(
                epoch_api._marker(birth, expected_adoption_sha256)):
        _refuse("v3-successor-wal-policy-or-adoption")
    admission.current()


def _recover_v3_wal(admission, *, memo, admitted_status, retained_batch,
                    committed, seq, expected_adoption_sha256):
    """Hold the exact fixed slot across policy admission and actual adoption."""
    import siasourcepublication as publication

    owner, source = admission.owner, admission.source
    admission.current()
    held = source.HeldFile(owner, admission.paths["CONTROLLER_SOURCE_BATCH_PATH"],
                           admission.capacities["MAX_STATE_JSON_BYTES"], allow_absent=True)
    try:
        publication._private(source, held)
        if held.raw is not None:
            batch = held.value
            # Bound the complete preflight before pure WAL replay copies any
            # history. The underlying artifact ceilings remain unchanged.
            admission.recovery_wire({
                "policy": admission.admitted, "memo": memo,
                "admitted_status": admitted_status,
                "retained_batch": retained_batch, "committed": committed,
                "successor_batch": batch,
            })
            if type(batch) is not dict or type(batch.get("batch_sha256")) is not str:
                _refuse("v3-successor-wal-shape")
            validate_successor_wal(
                owner, retained_batch=retained_batch, committed=committed,
                successor_batch=batch, expected_batch_sha256=batch["batch_sha256"])
            _v3_wal_parameters(admission, memo, batch, expected_adoption_sha256)
            if admission.wire(batch) != held.raw:
                _refuse("v3-successor-wal-not-canonical")
        held.current()
        admission.current()
        marker = source._notification_marker(owner, memo)
        if marker is None:
            recovered = owner["_recover_orphan_controller_source_successor_batch"](
                memo=memo, retained_batch=retained_batch, committed=committed, seq=seq)
        else:
            marker_pin = source.native_sha(owner, marker)
            admission.current()
            recovered = publication.recover_capturable_successor(
                owner, memo=memo, admitted_status=admitted_status,
                retained_batch=retained_batch, committed=committed, seq=seq,
                notification_baseline_attempt=marker,
                expected_notification_baseline_attempt_sha256=marker_pin)
        if recovered is not (held.raw is not None):
            _refuse("v3-successor-wal-recovery-result")
        held.current()
        if held.raw is not None and admission.wire(held.value) != held.raw:
            _refuse("v3-successor-wal-image-changed")
        admission.current()
        return recovered
    finally:
        held.close()


def run_v3(owner, *, operation, clock, journal_limits,
           expected_journal_limits_sha256, expected_adoption_sha256):
    """Advance one completed source through the adopted source-v3 pipeline.

    The owning wrapper must hold brainstem and corpus scopes continuously.
    This dispatcher creates no missing owner scope and activates no service.
    Non-completed initial/pending prefixes delegate to run and may return a
    legacy completion; this is not an assertion that every result is v3.

    On completed state, a genuine v3 WAL is admitted and recovered before
    preparation, sequence reservation, the supplied clock or any collector.
    With no WAL, only actual unadopted legacy state permits a None adoption
    pin. Existing adoption always requires the caller's original pin. An
    acquisition fence selects separate capture-only readers/storage calls;
    it is neither cleared nor treated as readiness. The existing retained
    publication/effects/ACK dispatcher completes the transaction afterward.
    """
    if type(owner) is not dict:
        raise TypeError("owner must be a globals-style dictionary")
    if not callable(operation) or not callable(clock):
        raise TypeError("operation and clock must be callable")
    import siacontrollerdeliveryepoch as epoch_api
    import siacontrollerepoch
    import siasourcepublication as publication

    admission = _RunnerV3Admission(
        owner, journal_limits=journal_limits,
        expected_journal_limits_sha256=expected_journal_limits_sha256,
        expected_adoption_sha256=expected_adoption_sha256)
    epoch_api._require_entered_corpus(owner)
    admission.current()
    memo = owner["load_memo"]()
    owner["_require_status_memo_fields"](memo)
    state = _source_state(memo)
    if state == "batch":
        # A fully retained but unpublished batch cannot cross a live-policy
        # change: its original bytes are the complete input to the downstream
        # transition. Preserve that evidence under a distinct refusal receipt
        # before starting a genuinely fresh capture under the checked-in
        # policy. Same-policy retries continue through the original path.
        pending_batch = _pending_batch(owner, memo)
        old_policy_sha256 = pending_batch.get("epoch", {}).get(
            "expected_live_policy_sha256")
        replacement_policy_sha256 = (
            siacontrollerepoch.EXPECTED_LIVE_POLICY_SHA256)
        if old_policy_sha256 != replacement_policy_sha256:
            admission.current()
            receipt = owner["_supersede_controller_source_policy"](
                memo=memo,
                replacement_live_policy=copy.deepcopy(
                    siacontrollerepoch.LIVE_POLICY),
                expected_replacement_live_policy_sha256=
                    replacement_policy_sha256)
            if type(receipt) is not dict \
                    or receipt.get("status") != "preserved-not-published" \
                    or receipt.get("source_batch_sha256") \
                       != pending_batch.get("batch_sha256") \
                    or receipt.get("old_live_policy_sha256") \
                       != old_policy_sha256 \
                    or receipt.get("replacement_live_policy_sha256") \
                       != replacement_policy_sha256:
                _refuse("v3-policy-supersession-result")
            admission.current()
            memo = owner["load_memo"]()
            owner["_require_status_memo_fields"](memo)
            state = _source_state(memo)
            if state != "absent":
                _refuse("v3-policy-supersession-state")
    if state != "completed":
        admission.current()
        result = run(owner, operation=operation)
        admission.current()
        return result

    seq = _sequence(owner, memo)
    admitted_status = owner["_require_status_sequence_not_ahead"](seq)
    source = admission.source
    marker = source._notification_marker(owner, memo)
    admission.current()
    view = _v3_completed_parent(owner, memo, admitted_status, marker)
    retained_batch, committed = view["batch"], view["committed"]
    _v3_adoption_pin(admission, memo, retained_batch)
    if _recover_v3_wal(
            admission, memo=memo, admitted_status=admitted_status,
            retained_batch=retained_batch, committed=committed, seq=seq,
            expected_adoption_sha256=expected_adoption_sha256):
        if _source_state(memo) != "batch":
            _refuse("v3-successor-orphan-adoption")
        result = run(owner, operation=operation)
        admission.current()
        return result

    epoch_arguments = {
        "memo": memo, "admitted_status": admitted_status,
        "retained_batch": retained_batch, "committed": committed,
        **admission.admitted,
    }
    if marker is None:
        adopted = epoch_api.prepare_epoch(owner, **epoch_arguments)
        if type(adopted) is not dict or type(adopted.get("expected_adoption_sha256")) is not str \
                or _HEX.fullmatch(adopted["expected_adoption_sha256"]) is None:
            _refuse("v3-prepared-adoption-result")
        adopted_pin = adopted["expected_adoption_sha256"]
        if expected_adoption_sha256 is not None and adopted_pin != expected_adoption_sha256:
            _refuse("v3-prepared-adoption-pin")
    else:
        # The fence can only continue an already adopted epoch. Do not call
        # ordinary preparation with hidden/filtered pending state or claim
        # that this no-fsync observation replays preparation durability.
        if expected_adoption_sha256 is None:
            _refuse("v3-fenced-adoption-pin-required")
        marker_pin = source.native_sha(owner, marker)
        admission.current()
        with epoch_api.hold_capturable_epoch(
                owner, **epoch_arguments, notification_baseline_attempt=marker,
                expected_notification_baseline_attempt_sha256=marker_pin) as held:
            held.current()
            admission.current()
        adopted_pin = expected_adoption_sha256
    admission.current()

    seq = _sequence(owner, memo, reservable=True) + 1
    memo["pulse_seq"] = seq
    owner["_write_memo"](memo)
    admission.current()
    observed_at = clock()
    admission.current()
    request = siacontrollerepoch.build_successor(
        owner, retained_batch=retained_batch, committed=committed, observed_at=observed_at)
    if type(request) is not dict or set(request) != _REQUEST_KEYS:
        _refuse("v3-successor-capture-request")
    admission.current()
    batch = source.capture_successor_v3(
        owner, memo=memo, admitted_status=admitted_status,
        retained_batch=retained_batch, committed=committed,
        epoch=request["epoch"], expected_epoch_sha256=request["expected_epoch_sha256"],
        observed_at=request["observed_at"],
        journal_limits=admission.admitted["journal_limits"],
        expected_journal_limits_sha256=admission.admitted["expected_journal_limits_sha256"],
        expected_adoption_sha256=adopted_pin)
    admission.current()
    if type(batch) is not dict or type(batch.get("batch_sha256")) is not str:
        _refuse("v3-captured-successor-batch")
    validate_successor_wal(
        owner, retained_batch=retained_batch, committed=committed,
        successor_batch=batch, expected_batch_sha256=batch["batch_sha256"])
    _v3_wal_parameters(admission, memo, batch, adopted_pin)
    marker = source._notification_marker(owner, memo)
    admission.current()
    retention = {
        "memo": memo, "retained_batch": retained_batch, "committed": committed,
        "batch": batch, "expected_batch_sha256": batch["batch_sha256"], "seq": seq,
    }
    if marker is None:
        owner["_retain_controller_source_successor_batch"](**retention)
    else:
        marker_pin = source.native_sha(owner, marker)
        admission.current()
        publication.retain_capturable_successor(
            owner, **retention, admitted_status=admitted_status,
            notification_baseline_attempt=marker,
            expected_notification_baseline_attempt_sha256=marker_pin)
    admission.current()
    owner["_controller_source_rollover_boundary"]("successor-batch-durable")
    admission.current()
    if not _recover_v3_wal(
            admission, memo=memo, admitted_status=admitted_status,
            retained_batch=retained_batch, committed=committed, seq=seq,
            expected_adoption_sha256=adopted_pin) or _source_state(memo) != "batch":
        _refuse("v3-successor-batch-adoption")
    result = run(owner, operation=operation)
    admission.current()
    return result
