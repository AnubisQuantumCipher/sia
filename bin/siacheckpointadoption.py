"""Fixed-slot WAL and memo adoption for an exact prepared compact capture.

The generic source pending receipt keeps its byte-binding contract. The batch
keeps its compact schema, which legacy publication readers still reject.
"""

import contextlib
import copy
import hashlib

import siacheckpointtransaction as transaction
import siasourcebatch as source
import siasourcepublication as publication
import siasourceeffects as effects


def _wire(owner, value, *, memo=False):
    return source.native_bytes(owner, value, ceiling=owner["MAX_MEMO_BYTES"] if memo else owner["MAX_STATE_JSON_BYTES"])


def read_pending(owner, *, memo, admitted_status, directory, expected_manifest_sha256, expected_root_sha256):
    """Join an adopted fixed capture to its real historical source/live parent.

    Full actual pending memo is passed to the original historical readers.
    This initial pending view is not acknowledgment, readiness, or evidence of
    present-tense delivery completion. No source or notification fence is reset.
    """
    references = dict(owner)
    memo_raw, status_raw = _wire(owner, memo, memo=True), _wire(owner, admitted_status)
    with owner["brainstem_owner"](), owner["corpus_owner"](), publication._files(owner, source) as (files, observe, current, named_current):
        with contextlib.ExitStack() as stack:
            view, package_current = stack.enter_context(transaction._hold_prepared(owner, directory=directory,
                expected_manifest_sha256=expected_manifest_sha256, expected_root_sha256=expected_root_sha256))
            batch = view["artifacts"]["capture"]
            raw = _wire(owner, batch)
            receipt = publication._receipt(owner, source, batch, raw)

            def authority():
                if any(owner.get(name) is not value for name, value in references.items()) \
                        or _wire(owner, memo, memo=True) != memo_raw or _wire(owner, admitted_status) != status_raw \
                        or _wire(owner, files["memo"].value, memo=True) != memo_raw or files["batch"].raw != raw \
                        or memo.get("controller_source_pending") != receipt \
                        or "controller_source_committed" in memo or "ready" in memo \
                        or (source._SUCCESSOR_PENDING_KEYS - {"controller_source_pending", "controller_source_live_pending", "pulse_status_effects_pending"}).intersection(memo) \
                        or transaction.checkpoint._wire(owner, source._notification_marker(owner, memo)) \
                        != transaction.checkpoint._wire(owner, batch["notification_baseline_attempt"]):
                    source.refuse("checkpoint-adopted-authority-differs")
                current()

                if "controller_source_live_pending" in memo:
                    expected = publication._live_binding_marker(owner, source, memo=memo,
                        batch=batch, receipt=receipt, admitted_status=admitted_status,
                        seq=memo.get("pulse_seq"), candidate=view["artifacts"]["candidate"],
                        transition=view["artifacts"]["transition"])
                    if _wire(owner, memo["controller_source_live_pending"]) != _wire(owner, expected):
                        source.refuse("checkpoint-adopted-live-binding-differs")
                if "pulse_status_effects_pending" in memo:
                    retained = owner["_pending_pulse_status_effects"](memo)
                    if retained is None or "controller_source_live_pending" not in memo:
                        source.refuse("checkpoint-adopted-status-binding-missing")
                    prepared, handoff = _status_handoff(owner, memo, admitted_status,
                        view["artifacts"], retained["history"][0])
                    if _wire(owner, retained) != _wire(owner, handoff) \
                            or _wire(owner, memo.get("pulse_history")) != _wire(owner, prepared["history"]):
                        source.refuse("checkpoint-adopted-status-handoff-differs")

            authority()
            committed = batch["epoch"]["predecessor"]
            historical = stack.enter_context(transaction.ack._historical_predecessor(
                owner, source, effects, memo, admitted_status, committed))
            archive, effects_archive, _status, generation = historical
            if _wire(owner, generation) != _wire(owner, batch["delivery_input"]["epoch_view"]["parent_generation"]) \
                    or archive.batch["epoch_sha256"] != view["root"]["legacy_epoch_sha256"] \
                    or archive.batch["epoch"]["expected_history_sha256"] != view["root"]["legacy_history_sha256"]:
                source.refuse("checkpoint-adopted-parent-differs")
            parent = transaction.blocks.prepare_captured(owner, batch=archive.batch,
                expected_batch_sha256=committed["source_batch_sha256"], parent=None, expected_parent_sha256=None)
            if _wire(owner, parent) != _wire(owner, view["parent"]):
                source.refuse("checkpoint-adopted-root-entry-differs")
            # Reconstruct the retained checkpoint from actual raw ancestry,
            # not merely from a self-consistent package supplied on disk.
            history = copy.deepcopy(archive.batch["epoch"]["history"])
            history["entries"].append(parent["entry"])
            request = {"history": history, "expected_history_sha256": source._component_sha(owner, history),
                "observed_at": archive.batch["observed_at"],
                **{key: archive.batch["epoch"][key] for key in transaction.checkpoint._DOC_KEYS}}
            checkpoint = transaction.checkpoint.checkpoints.bootstrap_episodes(owner, request=request,
                expected_request_sha256=hashlib.sha256(_wire(owner, request)).hexdigest())
            if _wire(owner, checkpoint) != _wire(owner, batch["parent_checkpoint"]):
                source.refuse("checkpoint-adopted-bootstrap-differs")
            result = {"schema": "sia-checkpoint-adoption-view-v1", "status": "pending-not-published",
                      "package": view, "receipt": receipt}
            archive.current()
            effects_archive.current()
            package_current()
            authority()
        # Historical/package cleanup precedes the last durable memo/slot sweep.
        authority()
        named_current()
        return result


def adopt_root(owner, *, memo, admitted_status, directory, expected_manifest_sha256,
                expected_root_sha256, journal_limits, expected_journal_limits_sha256,
                expected_adoption_sha256, seq):
    """Adopt once, or validate an exact already-adopted retry without capture."""
    if type(seq) is not int or seq < 0 or seq > owner["MAX_JSON_SAFE_INTEGER"] or memo.get("pulse_seq") != seq:
        source.refuse("checkpoint-adoption-sequence")
    read_args = dict(memo=memo, admitted_status=admitted_status, directory=directory,
                     expected_manifest_sha256=expected_manifest_sha256, expected_root_sha256=expected_root_sha256)
    hold_args = {**read_args, "journal_limits": journal_limits,
                 "expected_journal_limits_sha256": expected_journal_limits_sha256,
                 "expected_adoption_sha256": expected_adoption_sha256, "allow_fixed": True}
    references = dict(owner)
    original_memo = _wire(owner, memo, memo=True)
    with owner["brainstem_owner"](), owner["corpus_owner"]():
        if "controller_source_pending" in memo:
            recovered = read_pending(owner, **read_args)
            retained = recovered["package"]["artifacts"]["capture"]["delivery_input"]
            birth = retained["epoch_view"]["epoch_adoption"]["birth"]
            if retained["expected_adoption_sha256"] != expected_adoption_sha256 \
                    or transaction.live._sha(journal_limits) != expected_journal_limits_sha256 \
                    or birth["limits_sha256"] != expected_journal_limits_sha256 \
                    or _wire(owner, birth["limits"]) != _wire(owner, journal_limits):
                source.refuse("checkpoint-adoption-retry-input-differs")
            return False
        with transaction._hold_root_preparation(owner, **hold_args) as held:
            view = held.read()
            batch = view["artifacts"]["capture"]
            raw = _wire(owner, batch)
            receipt = publication._receipt(owner, source, batch, raw)
            updated = copy.deepcopy(memo)
            updated.pop("controller_source_committed", None)
            updated.pop("ready", None)
            updated["controller_source_pending"] = copy.deepcopy(receipt)
            updated_raw = _wire(owner, updated, memo=True)
            owner["_memo_text"](updated)
            held.current()
        with publication._files(owner, source) as (files, observe, current, named_current):
            def inputs_current():
                if any(owner.get(name) is not value for name, value in references.items()) \
                        or _wire(owner, memo, memo=True) != original_memo \
                        or _wire(owner, updated, memo=True) != updated_raw \
                        or _wire(owner, batch) != raw or memo.get("pulse_seq") != seq:
                    source.refuse("checkpoint-adoption-input-changed")
                current()

            if _wire(owner, files["memo"].value, memo=True) != original_memo or files["batch"].raw not in (None, raw):
                source.refuse("checkpoint-adoption-fixed-authority")
            inputs_current()
            prior = files["batch"]
            owner["siaqueue"].fixed_atomic_publish(owner["CONTROLLER_SOURCE_BATCH_PATH"], raw,
                mode=0o600, exclusive=True, staging_dir=owner["siaqueue"].staging_dir_for(
                    owner["CONTROLLER_SOURCE_BATCH_PATH"], authority_roots=(owner["CORPUS"], owner["STATE"], owner["SHARE"])))
            fixed = observe("batch", owner["CONTROLLER_SOURCE_BATCH_PATH"], owner["MAX_STATE_JSON_BYTES"])
            if fixed.raw != raw or fixed.parent_identity != prior.parent_identity:
                source.refuse("checkpoint-adoption-fixed-image-differs")
            # Recheck the whole live join after fixed-slot retention, including
            # an interrupted publisher's exact-slot durability retry.
            with transaction._hold_root_preparation(owner, **hold_args) as held:
                held.current()
            inputs_current()
            memo_parent = files["memo"].parent_identity
            owner["atomic_write"](owner["MEMO_PATH"], updated_raw.decode("utf-8"), mode=0o600)
            actual = observe("memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
            if actual.raw != updated_raw or actual.parent_identity != memo_parent:
                source.refuse("checkpoint-adoption-memo-image-differs")
            inputs_current()
            # Verify the actual new pending state before updating the caller.
            read_pending(owner, **{**read_args, "memo": updated})
            inputs_current()
            named_current()
            memo.clear()
            memo.update(updated)
            named_current()
            return True


def stage_live_binding(owner, *, memo, admitted_status, directory,
                       expected_manifest_sha256, expected_root_sha256, seq):
    """Durably bind an adopted compact source to its replay-verified live pulse.

    Only the original generic source/live pending marker is written. Nothing
    publishes the pulse, effects, pages, readiness or a source acknowledgment.
    A crash after memo replacement is recovered using the actual reloaded memo.
    """
    return _stage_pending_marker(owner, memo=memo, admitted_status=admitted_status,
        directory=directory, expected_manifest_sha256=expected_manifest_sha256,
        expected_root_sha256=expected_root_sha256, seq=seq)


def _status_handoff(owner, memo, admitted_status, artifacts, started_at):
    import siacontrollerstatus
    binding = memo.get("controller_source_live_pending")
    if type(binding) is not dict:
        source.refuse("checkpoint-status-live-binding-missing")
    batch, transition = artifacts["capture"], artifacts["transition"]
    prepared = siacontrollerstatus.prepare_checkpoint(owner, admitted_status=admitted_status,
        batch=batch, expected_batch_sha256=batch["batch_sha256"], source_live_pending=binding,
        candidate=artifacts["candidate"], transition=transition,
        expected_transition_sha256=transition["transition_sha256"], started_at=started_at)
    handoff = {"v": 1, "publication_id": binding["publication_id"],
               "effects": copy.deepcopy(prepared["effects"]), "history": copy.deepcopy(prepared["history"][-1])}
    return prepared, handoff


def stage_status_effects(owner, *, memo, admitted_status, directory,
                         expected_manifest_sha256, expected_root_sha256, seq, started_at):
    """Persist exact compact pulse counters/history before any closure effect.

    The original generic status handoff remains pending, not published. Retry
    requires its exact start-time premise and full reconstructed history.
    """
    if type(started_at) is not str:
        source.refuse("checkpoint-status-started-at")
    return _stage_pending_marker(owner, memo=memo, admitted_status=admitted_status,
        directory=directory, expected_manifest_sha256=expected_manifest_sha256,
        expected_root_sha256=expected_root_sha256, seq=seq, started_at=started_at)


def _stage_pending_marker(owner, *, memo, admitted_status, directory,
                          expected_manifest_sha256, expected_root_sha256, seq, started_at=None):
    if type(seq) is not int or seq < 0 or seq > owner["MAX_JSON_SAFE_INTEGER"] or memo.get("pulse_seq") != seq:
        source.refuse("checkpoint-live-binding-sequence")
    references = dict(owner)
    original_memo, original_status = _wire(owner, memo, memo=True), _wire(owner, admitted_status)
    args = dict(memo=memo, admitted_status=admitted_status, directory=directory,
                expected_manifest_sha256=expected_manifest_sha256, expected_root_sha256=expected_root_sha256)
    with owner["brainstem_owner"](), owner["corpus_owner"](), publication._files(owner, source) as (files, observe, current, named_current):
        def unchanged():
            if any(owner.get(name) is not value for name, value in references.items()) \
                    or _wire(owner, memo, memo=True) != original_memo \
                    or _wire(owner, admitted_status) != original_status:
                source.refuse("checkpoint-live-binding-input-changed")
            owner["_require_status_admission_unchanged"](admitted_status)
            current()

        unchanged()
        view = read_pending(owner, **args)
        artifacts = view["package"]["artifacts"]
        marker = publication._live_binding_marker(owner, source, memo=memo,
            batch=artifacts["capture"], receipt=view["receipt"], admitted_status=admitted_status,
            seq=seq, candidate=artifacts["candidate"], transition=artifacts["transition"])
        updated = copy.deepcopy(memo)
        key = "controller_source_live_pending"
        if started_at is None:
            updated[key] = marker
        else:
            key = "pulse_status_effects_pending"
            prepared, handoff = _status_handoff(owner, memo, admitted_status, artifacts, started_at)
            if key in memo:
                if _wire(owner, memo[key]) != _wire(owner, handoff) \
                        or _wire(owner, memo.get("pulse_history")) != _wire(owner, prepared["history"]):
                    source.refuse("checkpoint-status-retry-differs")
            elif memo.get("pulse_history") != admitted_status["history"]:
                source.refuse("checkpoint-status-history-authority")
            updated["pulse_history"] = copy.deepcopy(prepared["history"])
            updated[key] = handoff
        updated_raw = _wire(owner, updated, memo=True)
        owner["_memo_text"](updated)
        unchanged()
        if key in memo:
            named_current()
            return False
        # Rejoin the actual retained package immediately before memo mutation;
        # the outer ordinary leases stay held across both observations.
        verified = read_pending(owner, **args)
        if _wire(owner, verified["package"]["manifest"]) != _wire(owner, view["package"]["manifest"]) \
                or _wire(owner, updated, memo=True) != updated_raw:
            source.refuse("checkpoint-live-binding-image-changed")
        unchanged()
        parent = files["memo"].parent_identity
        owner["atomic_write"](owner["MEMO_PATH"], updated_raw.decode("utf-8"), mode=0o600)
        actual = observe("memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
        if actual.parent_identity != parent or actual.raw != updated_raw:
            source.refuse("checkpoint-live-binding-memo-image-differs")
        unchanged()
        read_pending(owner, **{**args, "memo": updated})
        unchanged()
        if _wire(owner, updated, memo=True) != updated_raw:
            source.refuse("checkpoint-live-binding-image-changed")
        named_current()
        memo.clear()
        memo.update(updated)
        named_current()
        return True
