"""Build one ordinary recall exclusively from current local authorities.

This is the narrow composition seam between CLI-selected operation inputs and
the existing source-bound output primitive.  It accepts no caller-authored
source, epoch, engine, policy, rank or rendering document.  All such inputs
are observed under the corpus owner and independently rechecked downstream.
"""

import copy

import siacontrollerdeliverywriter as writer
import siacontrollerrecalloutput as output
import siadelivery as journal
import siainstalledengine as engine
import siainstalledexpectations as installed
import sialiveloop as live
import siasourceack as acknowledgment


NON_CLAIMS = (
    "This compositor selects a current acknowledged local source-v3 completion, live generation and installed engine receipt relation; local observations are not remote build provenance or protection against a hostile same-user process.",
    "The caller supplies only an ordinary canonical subject, bounded timeout, request identity, binary sink and completion clock. The compositor does not accept caller-authored source, epoch, engine, rank or render authority and has no legacy retrieval fallback.",
    "A successful return is the existing write-all-and-flush-returned journal completion, not human receipt, understanding, source consumption, later pulse acknowledgment or reinforcement.",
    "The source observation and installed selection are held through the composed output operation; ordinary GET may still perform the migrations or retrieval bookkeeping admitted by the installed-engine boundary.",
    "No configuration change, daemon activation, runtime installation, JACKAL assurance, biological cognition, cognitive-mechanism warrant or held-out retrieval win is established.",
)
_CALLS = (
    "corpus_owner", "load_memo", "_require_status_sequence_not_ahead",
    "_load_live_publication", "_read_committed_live_generation",
    "_configured_controller_source_adoption",
)
_ERRORS = (OSError, ValueError, RuntimeError, TypeError, KeyError, IndexError,
           AttributeError, OverflowError, RecursionError)


class ControllerRecallCliRefusal(ValueError):
    """No caller-visible body may be synthesized after a closed refusal."""

    def __init__(self, reason, *, upstream=None):
        self.reason = reason
        self.output_state = getattr(upstream, "output_state", "not-started")
        self.non_claims = list(NON_CLAIMS)
        self.upstream_reason = getattr(upstream, "reason", None)
        self.upstream_status = getattr(upstream, "status", None)
        self.upstream_non_claims = {
            "non_claims": copy.deepcopy(
                getattr(upstream, "non_claims", ())),
            "upstream_non_claims": copy.deepcopy(
                getattr(upstream, "upstream_non_claims", ())),
        }
        super().__init__("CLI recall composition refused: " + reason)


def _refuse(reason):
    raise ControllerRecallCliRefusal(reason)


def _operation(owner, subject, timeout, request_id, binary_sink, clock):
    if type(owner) is not dict \
            or any(not callable(owner.get(name)) for name in _CALLS):
        _refuse("owner-contract")
    if type(subject) is not str or not 0 < len(subject) <= 200 \
            or engine._GET_SUBJECT.fullmatch(subject) is None:
        _refuse("canonical-recall-subject")
    maximum = owner.get("MAX_JSON_SAFE_INTEGER")
    if type(timeout) is not int or type(maximum) is not int \
            or not 0 < timeout <= maximum:
        _refuse("timeout-contract")
    try:
        journal._request_id(request_id)
    except journal.DeliveryJournalRefusal as exc:
        raise ControllerRecallCliRefusal(
            "request-id-contract", upstream=exc) from exc
    if not callable(getattr(binary_sink, "write", None)) \
            or not callable(getattr(binary_sink, "flush", None)) \
            or not callable(clock):
        _refuse("output-operation-contract")


def _source(owner):
    memo = owner["load_memo"]()
    if type(memo) is not dict:
        _refuse("source-memo-unavailable")
    sequence = memo.get("pulse_seq")
    status = owner["_require_status_sequence_not_ahead"](sequence)
    if type(status) is not dict:
        _refuse("source-status-unavailable")
    owner["_load_live_publication"]()
    completed = acknowledgment.read_completed(
        owner, memo=memo, admitted_status=status)
    if type(completed) is not dict \
            or set(completed) != {"status", "batch", "committed"} \
            or completed.get("status") != "available":
        _refuse("completed-source-unavailable")
    retained = completed["batch"]
    committed = completed["committed"]
    if type(retained) is not dict \
            or retained.get("schema") != "sia-controller-source-batch-v3" \
            or type(committed) is not dict:
        _refuse("acknowledged-source-v3-required")
    view = owner["_read_committed_live_generation"](
        memo=memo, admitted_status=status)
    generation = view.get("generation") if type(view) is dict else None
    if type(view) is not dict or view.get("status") != "available" \
            or type(generation) is not dict \
            or generation.get("generation_sha256") \
            != committed.get("live_generation_sha256"):
        _refuse("committed-live-generation-unavailable")
    state = generation.get("transition", {}).get("state") \
        if type(generation.get("transition")) is dict else None
    if type(state) is not dict or not live._integer(state.get("observed_at")):
        _refuse("source-observation-time-unavailable")
    adoption = owner["_configured_controller_source_adoption"](memo)
    if not live._digest(adoption):
        _refuse("installed-delivery-adoption-unavailable")
    return memo, status, retained, committed, state, adoption


def recall_from_current_source(owner, *, subject, timeout, request_id,
                               binary_sink, clock):
    """Deliver one literal recall after deriving all authority under lease."""
    try:
        _operation(owner, subject, timeout, request_id, binary_sink, clock)
        with owner["corpus_owner"]():
            memo, status, retained, committed, state, adoption = _source(owner)
            observed_engine = installed.observe_installed_expectations(owner)
            limits = copy.deepcopy(journal._LIMITS)
            journal._limits(limits)
            render = {
                "schema": writer.RENDER_CONFIG_SCHEMA,
                "selection": "rank-prefix-v1",
                "display_limit": 1,
                "max_body_bytes": limits["max_body_bytes"],
            }
            result = output.recall_and_deliver(
                owner, memo=memo, admitted_status=status,
                retained_batch=retained, committed=committed,
                journal_limits=limits,
                expected_journal_limits_sha256=live._sha(limits),
                expected_adoption_sha256=adoption,
                engine_expectations=observed_engine["expectations"],
                expected_engine_expectations_sha256=
                    observed_engine["expected_expectations_sha256"],
                render_config=render,
                expected_render_config_sha256=live._sha(render),
                subject=subject, timeout=timeout,
                observed_at=state["observed_at"], request_id=request_id,
                binary_sink=binary_sink, clock=clock)
        return result
    except ControllerRecallCliRefusal:
        raise
    except _ERRORS as exc:
        raise ControllerRecallCliRefusal(
            "current-source-recall-unavailable", upstream=exc) from exc
