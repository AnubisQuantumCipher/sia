"""Source-authorized output under one corpus and adopted journal lifetime.

This additive controller front door does not dispatch CLI recall or turn a
represented wrapper into permission. It reopens the actual acknowledged
source, complete live generation and original delivery-epoch storage before
using the journal's held writer. No legacy touch, UUID or observation clock
is acquired here; rendered bytes and row references remain caller premises.
"""

import copy

import siacontrollerdeliveryepoch as epoch_api
import siacontrollerdeliveryinput as binding_api
import siacontrollerdeliverywrapper as wrapper_api
import siadelivery as journal_api
import sialiveloop as live
import siasourcebatch as source


NON_CLAIMS = (
    "Writer admission requires an actual fully acknowledged source-v3 generation, its original adopted journal and an absent source WAL; represented wrapper bytes alone are not writer authorization.",
    "The returned unchanged journal completion records write-all-and-flush-returned at the supplied binary sink, not human receipt, reading, understanding, downstream forwarding or successful use.",
    "Rows, emitted references, rendered body bytes, request identity and rank observation time are caller premises; this component does not query an engine, independently render the body, allocate an identity or sample an observation clock.",
    "Complete journal prefix binding is not pulse consumption or source acknowledgment; the subsequent native source-v3 capture and publication remain separate operations.",
    "A chronology ceiling selected from supplied and already retained completion clocks validates the existing journal prefix only; it is not a new clock observation or a freshness claim.",
    "Incomplete journals, including intent-only histories, refuse this writer front door; no legacy touch history, missing record or ambiguous output is reconstructed, retried as fresh output, deleted or repaired.",
    "Continuous local descriptor and corpus ownership is not protection against hostile same-user mutation; no CLI deployment, JACKAL assurance, biological cognition or held-out retrieval improvement is established.",
    "All source, live-loop, adoption, held-epoch, delivery-binding and journal nonclaims remain controlling.",
)

_PATHS = (
    "HOME", "CORPUS", "STATE", "SHARE", "CONFIG_PATH", "CURSORS_PATH",
    "MEMO_PATH", "STATUS_PATH", "GRAPH_PATH", "LIVE_CANDIDATE_PATH",
    "LIVE_STATE_PATH", "CONTROLLER_SOURCE_BATCH_PATH",
    "CONTROLLER_SOURCE_ARCHIVE_DIR", "CONTROLLER_SOURCE_EFFECTS_ARCHIVE_DIR",
    "CONTROLLER_DELIVERY_EPOCH_ROOT", "CORPUS_OWNER_LOCK",
)
_CAPACITIES = (
    "MAX_MEMO_BYTES", "MAX_STATE_JSON_BYTES", "MAX_CONFIG_PATH_CHARS",
    "MAX_CONFIG_TEXT_CHARS", "MAX_CONFIG_BYTES", "MAX_SOURCE_REPLAY_EVENTS",
    "MAX_SOURCE_REPLAY_SOURCES", "MAX_LEDGER_PENDING_RECORDS",
    "MAX_JSON_SAFE_INTEGER",
)
_ERRORS = (OSError, ValueError, RuntimeError, TypeError, KeyError, IndexError,
           AttributeError, OverflowError, RecursionError)


class ControllerDeliveryWriterRefusal(ValueError):
    def __init__(self, reason, *, output_state="not-started", upstream=None):
        self.reason = reason
        self.output_state = output_state
        self.non_claims = list(NON_CLAIMS)
        self.upstream_reason = getattr(upstream, "reason", None)
        self.upstream_non_claims = copy.deepcopy({
            "non_claims": getattr(upstream, "non_claims", ()),
            "upstream_non_claims": getattr(upstream, "upstream_non_claims", ()),
        })
        super().__init__("controller delivery writer refused: " + reason)


def _refuse(reason):
    raise ControllerDeliveryWriterRefusal(reason)


def _plain_pin(value):
    """Freeze already byte/depth-admitted plain values without callbacks.

    This is only an in-process exit-tail comparison, not another serializer
    or an authority document. Immutable scalar values remain native; float
    spelling distinguishes signed zero and exact type distinguishes booleans.
    """
    kind = type(value)
    if value is None or kind in (bool, int, str):
        return kind, value
    if kind is float:
        return kind, value.hex()
    if kind in (list, tuple):
        return kind, tuple(_plain_pin(child) for child in value)
    if kind is dict and all(type(key) is str for key in value):
        return kind, tuple((key, _plain_pin(child)) for key, child in value.items())
    _refuse("exit-tail-nonplain-value")


def _plain_same(value, pin):
    """Compare the admitted bounded shape using only exact built-in types."""
    kind, expected = pin
    if type(value) is not kind:
        return False
    if kind is dict:
        return len(value) == len(expected) \
            and all(type(key) is str for key in value) \
            and all(key in value and _plain_same(value[key], child)
                    for key, child in expected)
    if kind in (list, tuple):
        return len(value) == len(expected) \
            and all(_plain_same(child, child_pin)
                    for child, child_pin in zip(value, expected))
    if kind is float:
        return value.hex() == expected
    return value == expected


class _Request:
    """Pin scalar authority selection before the first request wire or copy."""

    def __init__(self, owner, arguments, output_utf8):
        if type(owner) is not dict:
            _refuse("owner-contract")
        self.owner = owner
        self.paths = {name: owner.get(name) for name in _PATHS}
        self.capacities = {name: owner.get(name) for name in _CAPACITIES}
        self.notification_key = owner.get("NOTIFY_BASELINE_ATTEMPT_KEY")
        self.version = owner.get("VERSION")
        self.corpus_owner = owner.get("corpus_owner")
        if any(type(value) is not int or value <= 0
               for value in self.capacities.values()) \
                or type(self.notification_key) is not str or not self.notification_key \
                or type(self.version) is not str or not self.version \
                or not callable(self.corpus_owner):
            _refuse("owner-contract")
        for path in self.paths.values():
            source._canonical_path(owner, path)
        self.basis_current()
        limits = arguments["journal_limits"]
        journal_api._limits(limits)
        # Bound original bytes before decoding or any base64 representation.
        if type(output_utf8) is not bytes \
                or len(output_utf8) > limits["max_body_bytes"] \
                or len(output_utf8) > live.MAX_CONTENT_BYTES \
                or len(output_utf8) > self.capacities["MAX_STATE_JSON_BYTES"]:
            _refuse("output-byte-capacity")
        self.output_utf8 = output_utf8
        text = output_utf8.decode("utf-8", "strict")
        self.arguments = {**arguments, "output_utf8_text": text}
        self.basis = {
            "paths": self.paths, "capacities": self.capacities,
            "notification_key": self.notification_key, "version": self.version,
        }
        self.pure = wrapper_api._Admission(owner, {
            "writer_basis": self.basis, "arguments": self.arguments})
        self.admitted = self.pure.admitted["arguments"]
        self.current()
        data = self.admitted
        if type(data["retained_batch"]) is not dict \
                or data["retained_batch"].get("schema") \
                != "sia-controller-source-batch-v3":
            _refuse("acknowledged-source-v3-required")
        if not live._digest(data["expected_adoption_sha256"]) \
                or not live._digest(data["expected_journal_limits_sha256"]) \
                or live._sha(data["journal_limits"]) \
                != data["expected_journal_limits_sha256"]:
            _refuse("adoption-or-journal-limits-pin")
        if not live._integer(data["observed_at"]):
            _refuse("explicit-rank-clock")
        live._pin(data["rows"], data["expected_rows_sha256"])
        journal_api._request_id(data["request_id"])
        if data["consumer"] not in ("cli.ask", "cli.recall") \
                or type(data["consumer"]) is not str:
            _refuse("consumer-contract")
        source.native_bytes(owner, data["memo"],
                            ceiling=self.capacities["MAX_MEMO_BYTES"])
        self.current()
        # Freeze while all input admission is current, not from potentially
        # changed values after an owner's normal-exit callback has run.
        self._tail_request = _plain_pin(self.pure.supplied)
        self._tail_basis = _plain_pin(self.pure.basis)
        self._tail_owner_values = {
            name: _plain_pin(owner[name]) for name in (
                *wrapper_api._CAPACITIES, "_SENSE_ORGAN",
                "LIVE_PUBLICATION_NON_CLAIMS", "NOTIFY_BASELINE_ATTEMPT_KEY")}
        self._tail_references = dict(self.pure.references)
        self.final_current()

    def basis_current(self):
        for name, expected in {**self.paths, **self.capacities,
                               "NOTIFY_BASELINE_ATTEMPT_KEY": self.notification_key,
                               "VERSION": self.version}.items():
            actual = self.owner.get(name)
            if type(actual) is not type(expected) or actual != expected:
                _refuse("owner-basis-changed")
        if self.owner.get("corpus_owner") is not self.corpus_owner:
            _refuse("owner-operation-changed")

    def current(self):
        self.basis_current()
        self.pure.current()
        if self.admitted["output_utf8_text"].encode("utf-8") != self.output_utf8:
            _refuse("output-bytes-changed")
        self.basis_current()

    def budget(self, **additional):
        # A complete represented-wire budget, not a claim about Python heap.
        source.native_bytes(self.owner, {
            "request": self.pure.admitted, **additional},
            ceiling=self.capacities["MAX_STATE_JSON_BYTES"])
        self.current()

    def final_current(self):
        """No provider, serializer, copy, clock or filesystem call on success."""
        self.basis_current()
        if not _plain_same(self.pure.supplied, self._tail_request) \
                or not _plain_same(self.pure.admitted, self._tail_request) \
                or not _plain_same(self.pure.basis, self._tail_basis) \
                or any(not _plain_same(self.owner.get(name), pin)
                       for name, pin in self._tail_owner_values.items()) \
                or any(self.owner.get(name) is not reference
                       for name, reference in self._tail_references.items()):
            _refuse("exit-tail-request-or-owner-changed")
        self.basis_current()


def _rank_current(owner, ranked, data, generation):
    if type(ranked) is not dict \
            or ranked.get("schema") != "sia-live-recall-plan-v1" \
            or ranked.get("status") != "computed-unverified" \
            or ranked.get("state_sha256") != generation["state_sha256"] \
            or ranked.get("epoch_id") != generation["epoch_id"] \
            or ranked.get("observed_at") != data["observed_at"] \
            or ranked.get("rows_sha256") != data["expected_rows_sha256"] \
            or ranked.get("policy_sha256") != generation["transition"]["state"]["policy_sha256"] \
            or source.native_bytes(owner, ranked.get("rows")) \
            != source.native_bytes(owner, data["rows"]) \
            or source.native_bytes(owner, ranked.get("policy")) \
            != source.native_bytes(owner, generation["transition"]["state"]["policy"]) \
            or ranked.get("rank_sha256") != live._own(ranked, "rank_sha256"):
        _refuse("actual-parent-rank-binding")


def deliver(owner, *, memo, admitted_status, retained_batch, committed,
            journal_limits, expected_journal_limits_sha256,
            expected_adoption_sha256, rows, expected_rows_sha256,
            observed_at, emitted_row_refs, output_utf8, request_id, consumer,
            binary_sink, clock):
    """Journal actual output under strict current source-v3 authority.

    All arguments are mandatory. Caller-supplied row/body/identity/observation
    inputs acquire no authority themselves. The output clock is invoked only
    by the journal after actual flush returns. This first entry point refuses
    every incomplete epoch, including intent-only requests; a separate future
    pending-output retry interface must not be inferred from this function.
    """
    phase = "not-started"
    try:
        arguments = {
            "memo": memo, "admitted_status": admitted_status,
            "retained_batch": retained_batch, "committed": committed,
            "journal_limits": journal_limits,
            "expected_journal_limits_sha256": expected_journal_limits_sha256,
            "expected_adoption_sha256": expected_adoption_sha256,
            "rows": rows, "expected_rows_sha256": expected_rows_sha256,
            "observed_at": observed_at, "emitted_row_refs": emitted_row_refs,
            "request_id": request_id, "consumer": consumer,
        }
        request = _Request(owner, arguments, output_utf8)
        data = request.admitted
        if not callable(getattr(binary_sink, "write", None)) \
                or not callable(getattr(binary_sink, "flush", None)) or not callable(clock):
            _refuse("explicit-binary-output-and-clock-required")
        request.current()
        # Never acquire the resident brainstem lease on an output path.
        with request.corpus_owner():
            request.current()
            with epoch_api.hold_epoch(
                    owner, memo=memo, admitted_status=data["admitted_status"],
                    retained_batch=data["retained_batch"], committed=data["committed"],
                    journal_limits=data["journal_limits"],
                    expected_journal_limits_sha256=data["expected_journal_limits_sha256"],
                    expected_adoption_sha256=data["expected_adoption_sha256"]) as epoch:
                view = epoch.read()
                view_raw = source.native_bytes(owner, view)
                generation = view["parent_generation"]
                state = generation["transition"]["state"]
                if view["parent_committed"] != data["committed"] \
                        or view["expected_parent_generation_sha256"] \
                        != data["committed"]["live_generation_sha256"] \
                        or generation["generation_sha256"] \
                        != data["committed"]["live_generation_sha256"] \
                        or view["epoch_adoption"]["expected_adoption_sha256"] \
                        != data["expected_adoption_sha256"] \
                        or source.native_bytes(owner, view["epoch_adoption"]) \
                        != source.native_bytes(owner, data["retained_batch"]["delivery_input"]["epoch_view"]["epoch_adoption"]) \
                        or view["records_identity"] \
                        != view["epoch_adoption"]["adoption"]["records_identity"]:
                    _refuse("actual-source-generation-or-adoption-binding")

                def authority_current():
                    request.current()
                    epoch.current()
                    if source.native_bytes(owner, view) != view_raw:
                        _refuse("held-epoch-view-changed")
                    request.current()
                    return None

                authority_current()
                with journal_api.hold_delivery_writer(
                        directory=view["records_directory"],
                        epoch_id=generation["epoch_id"], limits=data["journal_limits"],
                        expected_directory_identity=view["records_identity"],
                        authority_current=authority_current) as writer:
                    inspected = writer.read()
                    if inspected.get("complete") is not True \
                            or type(inspected.get("pending")) is not list \
                            or inspected["pending"]:
                        _refuse("complete-delivery-journal-required")
                    # Actual journal inspection validated these complete
                    # records. Select retained chronology only, never a new
                    # clock or a substitute for the caller's rank timestamp.
                    chronology = data["observed_at"]
                    for record in inspected["records"]:
                        if not live._integer(record["completed_at"]):
                            _refuse("retained-completion-clock")
                        chronology = max(chronology, record["completed_at"])
                    bound = binding_api.bind(
                        journal=inspected, expected_journal_sha256=live._sha(inspected),
                        previous_state=state, expected_previous_state_sha256=generation["state_sha256"],
                        intake=state["intake"], expected_intake_sha256=live._sha(state["intake"]),
                        policy=state["policy"], expected_policy_sha256=state["policy_sha256"],
                        observed_at=chronology)
                    writer.current()
                    authority_current()
                    ranked = live.rank_recall(
                        rows=data["rows"], expected_rows_sha256=data["expected_rows_sha256"],
                        state=state, expected_state_sha256=generation["state_sha256"],
                        policy=state["policy"], expected_policy_sha256=state["policy_sha256"],
                        observed_at=data["observed_at"])
                    _rank_current(owner, ranked, data, generation)
                    writer.current()
                    intent = journal_api._new_intent(
                        ranked=ranked, expected_ranked_sha256=ranked["rank_sha256"],
                        emitted_row_refs=data["emitted_row_refs"], output_utf8=output_utf8,
                        request_id=data["request_id"], consumer=data["consumer"],
                        limits=data["journal_limits"])
                    expected_reservation = journal_api._reservation(intent)
                    reservation_raw = journal_api._wire(expected_reservation, data["journal_limits"])
                    # Reserve the future terminal representation before any
                    # intent publication or output, without acquiring a clock.
                    terminal = journal_api._completion(intent, journal_api._pure(
                        intent, output_utf8, live.MAX_SAFE_INTEGER))
                    request.budget(epoch_view=view, journal=inspected, binding=bound,
                                   ranked=ranked, reservation=expected_reservation,
                                   terminal=terminal)
                    writer.current()
                    authority_current()
                    reservation = writer.reserve(
                        ranked=ranked, expected_ranked_sha256=ranked["rank_sha256"],
                        emitted_row_refs=data["emitted_row_refs"], output_utf8=output_utf8,
                        request_id=data["request_id"], consumer=data["consumer"])
                    if journal_api._wire(reservation, data["journal_limits"]) != reservation_raw:
                        _refuse("journal-reservation-differs")
                    writer.current()
                    authority_current()
                    completed = writer.deliver(
                        reservation=reservation,
                        expected_reservation_sha256=reservation["reservation_sha256"],
                        binary_sink=binary_sink, clock=clock)
                    # A subsequent wrapper refusal must not claim that this
                    # already returned output never started.
                    phase = "completed-unrecorded"
                    completed_raw = journal_api._wire(completed, data["journal_limits"])
                    replay = journal_api._completion(intent, journal_api._pure(
                        intent, output_utf8, completed["record"]["completed_at"]))
                    if journal_api._wire(replay, data["journal_limits"]) != completed_raw:
                        _refuse("journal-completion-differs")
                    writer.current()
                    authority_current()
                    completed_pin = _plain_pin(completed)
                    detached = copy.deepcopy(completed)
                    if journal_api._wire(completed, data["journal_limits"]) != completed_raw \
                            or journal_api._wire(detached, data["journal_limits"]) != completed_raw:
                        _refuse("completion-copy-changed")
                    writer.current()
                    authority_current()
                # Journal exit has run; the actual source/epoch descriptors
                # are still held. Admit its callbacks before closing them.
                request.current()
                if journal_api._wire(completed, data["journal_limits"]) != completed_raw \
                        or journal_api._wire(detached, data["journal_limits"]) != completed_raw:
                    _refuse("journal-exit-completion-changed")
                epoch.current()
                request.final_current()
                if not _plain_same(completed, completed_pin) \
                        or not _plain_same(detached, completed_pin):
                    _refuse("journal-exit-completion-changed")
            # Epoch exit has run under the still-continuous corpus lease.
            # Its closed descriptors are not reused and no path is reopened.
            request.final_current()
            if not _plain_same(completed, completed_pin) \
                    or not _plain_same(detached, completed_pin):
                _refuse("epoch-exit-completion-changed")
        # A provider's normal corpus exit can itself mutate in-memory caller
        # inputs or the detached response. Check those values without another
        # provider/serializer call or a new defensive copy after release.
        # This is not a fresh filesystem observation after ownership ends.
        request.final_current()
        if not _plain_same(completed, completed_pin) \
                or not _plain_same(detached, completed_pin):
            _refuse("corpus-exit-completion-changed")
        return detached
    except _ERRORS as exc:
        state = getattr(exc, "output_state", phase)
        if phase != "not-started":
            state = phase
        reason = (exc.reason if isinstance(exc, ControllerDeliveryWriterRefusal)
                  else "source-writer-domain-refused")
        raise ControllerDeliveryWriterRefusal(reason, output_state=state, upstream=exc) from exc
