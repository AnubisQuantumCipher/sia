"""Publish one retained compact live successor without source acknowledgment."""

import copy
import hashlib

import siacheckpointadoption as adoption
import siacheckpointparent as parents
import siasourceeffects as effects


def _parent_join(owner, package, historical, *, directory):
    """Reconstruct the parent checkpoint from the actual archived ancestry.

    A successor package admits the predecessor's own projected checkpoint by
    the head's pin and links its entry to one pinned grandparent. The
    root-only lane keeps its original bootstrap reconstruction unchanged.
    """
    source, transaction = adoption.source, adoption.transaction
    batch = package["artifacts"]["capture"]
    archived = historical["batch"]
    committed = batch["epoch"]["predecessor"]
    successor = "head" in package
    if adoption._wire(owner, historical["generation"]) != adoption._wire(owner, batch["delivery_input"]["epoch_view"]["parent_generation"]):
        source.refuse("checkpoint-live-parent-differs")
    if successor:
        head = package["head"]
        grandparent_pin = package["parent"]["parent_sha256"]
        if grandparent_pin is None \
                or archived["epoch"]["root_sha256"] != package["manifest"]["root_sha256"] \
                or archived["intake_projection"]["checkpoint_sha256"] != head["checkpoint_sha256"]:
            source.refuse("checkpoint-live-parent-differs")
        grandparent = transaction.store.read(
            directory=directory, expected_block_sha256=grandparent_pin)
        parent = transaction.blocks.prepare_checkpoint_capture(owner, batch=archived,
            expected_batch_sha256=committed["source_batch_sha256"],
            parent=grandparent, expected_parent_sha256=grandparent_pin)
        if adoption._wire(owner, parent) != adoption._wire(owner, package["parent"]):
            source.refuse("checkpoint-live-root-entry-differs")
        checkpoint = transaction.checkpoint.checkpoints.admit(owner,
            checkpoint=archived["intake_projection"]["checkpoint"],
            expected_checkpoint_sha256=head["checkpoint_sha256"])
    else:
        if archived["epoch_sha256"] != package["root"]["legacy_epoch_sha256"] \
                or archived["epoch"]["expected_history_sha256"] != package["root"]["legacy_history_sha256"]:
            source.refuse("checkpoint-live-parent-differs")
        parent = transaction.blocks.prepare_captured(owner, batch=archived,
            expected_batch_sha256=committed["source_batch_sha256"], parent=None, expected_parent_sha256=None)
        if adoption._wire(owner, parent) != adoption._wire(owner, package["parent"]):
            source.refuse("checkpoint-live-root-entry-differs")
        history = copy.deepcopy(archived["epoch"]["history"])
        history["entries"].append(parent["entry"])
        request = {"history": history, "expected_history_sha256": source._component_sha(owner, history),
            "observed_at": archived["observed_at"],
            **{key: archived["epoch"][key] for key in transaction.checkpoint._DOC_KEYS}}
        checkpoint = transaction.checkpoint.checkpoints.bootstrap_episodes(owner, request=request,
            expected_request_sha256=hashlib.sha256(adoption._wire(owner, request)).hexdigest())
    if adoption._wire(owner, checkpoint) != adoption._wire(owner, batch["parent_checkpoint"]):
        source.refuse("checkpoint-live-bootstrap-differs")


def publish(owner, *, memo, admitted_status, directory, expected_manifest_sha256, expected_root_sha256):
    return _publish(owner, memo=memo, admitted_status=admitted_status, directory=directory,
        expected_manifest_sha256=expected_manifest_sha256, expected_root_sha256=expected_root_sha256,
        finalize_effects=False)


def finalize(owner, *, memo, admitted_status, directory, expected_manifest_sha256, expected_root_sha256):
    """Publish/recover live effects and retain their exact committed receipt.

    This does not acknowledge source cursors, clear notification fences or
    publish readiness. A finalized retry validates actual files without writes.
    """
    return _publish(owner, memo=memo, admitted_status=admitted_status, directory=directory,
        expected_manifest_sha256=expected_manifest_sha256, expected_root_sha256=expected_root_sha256,
        finalize_effects=True)


def _publish(owner, *, memo, admitted_status, directory, expected_manifest_sha256, expected_root_sha256, finalize_effects):
    """Recover the original live publisher from actual compact effects authority.

    Source slot, notification fence and effects WAL remain unacknowledged.
    Historical parent inputs are explicit; the actual memo is never filtered
    or substituted to make a current-file reader accept historical authority.
    """
    source, transaction = adoption.source, adoption.transaction
    owner["_load_live_publication"]()
    references = dict(owner)
    status_raw = adoption._wire(owner, admitted_status)
    original_memo = adoption._wire(owner, memo, memo=True)
    def same(left, right):
        return adoption._wire(owner, left) == adoption._wire(owner, right)
    with owner["brainstem_owner"](), owner["corpus_owner"](), \
            adoption.publication._files(owner, source) as (files, observe, current, named_current), \
            transaction._hold_prepared(owner, directory=directory, expected_manifest_sha256=expected_manifest_sha256,
                expected_root_sha256=expected_root_sha256) as (package, package_current):
        artifacts = package["artifacts"]
        batch = artifacts["capture"]
        hold = parents.hold_checkpoint_live if "head" in package else parents.hold_live
        with hold(owner, directory=directory, committed=batch["epoch"]["predecessor"]) as historical:
            _parent_join(owner, package, historical, directory=directory)
            raw = adoption._wire(owner, batch)
            source_receipt = adoption.publication._receipt(owner, source, batch, raw)
            parent_receipt = owner["_live_receipt"](historical["generation"])
            binding = adoption.publication._live_binding_marker_parent(owner, source, memo=memo,
                batch=batch, receipt=source_receipt, admitted_status=historical["status"],
                seq=memo.get("pulse_seq"), candidate=artifacts["candidate"], transition=artifacts["transition"],
                parent=parent_receipt)
            committed_effects = memo.get("controller_source_effects_committed")
            retained_pending = memo.get("controller_source_effects_pending")
            if (retained_pending is None) == (committed_effects is None):
                source.refuse("checkpoint-live-effects-phase")
            supplied = retained_pending if committed_effects is None else committed_effects
            if type(supplied) is not dict:
                source.refuse("checkpoint-live-effects-missing")
            projected_status = supplied["status"] if committed_effects is None else admitted_status
            prepared, handoff = adoption._status_handoff(owner, memo, historical["status"], artifacts,
                projected_status["history"][-1][0])
            closure = batch["event_closure"]
            reconstructed = effects.prepare_checkpoint_pending(owner, admitted_status=historical["status"],
                batch=batch, binding=binding, handoff=handoff, candidate=artifacts["candidate"], transition=artifacts["transition"],
                closure_result=None if closure is None else effects._closure_publication_result(closure),
                **{key: supplied[key] for key in ("target_manifest", "corpus_generation", "sync_generation",
                    "graph_generation", "status_generation")}, status=projected_status,
                content_fields={key: supplied[key] for key in effects.CONTENT_FIELDS})
            if retained_pending is not None and not same(reconstructed, retained_pending):
                source.refuse("checkpoint-live-effects-replay-differs")
            pending = reconstructed
            pending_raw = adoption._wire(owner, pending)
            committed_raw = None if committed_effects is None else adoption._wire(owner, committed_effects)
            inputs = artifacts["candidate"]["prepare_inputs"]
            candidate = {"schema": "sia-live-publication-candidate-v1", "prepare_inputs": inputs,
                "prepare_inputs_sha256": artifacts["candidate"]["expected_prepare_inputs_sha256"],
                "transition": artifacts["transition"], "status": pending["status"],
                "status_sha256": owner["_live_sha"](pending["status"]), "parent_committed": parent_receipt,
                "non_claims": list(owner["LIVE_PUBLICATION_NON_CLAIMS"])}
            candidate["candidate_sha256"] = owner["_live_sha"](candidate)
            generation = owner["_live_replay_candidate"](candidate)
            receipt = owner["_live_receipt"](generation)

            def authority():
                if any(owner.get(name) is not value for name, value in references.items()) \
                        or adoption._wire(owner, admitted_status) != status_raw \
                        or files["batch"].raw != raw or not same(memo.get("controller_source_pending"), source_receipt) \
                        or not same(memo.get("controller_source_live_pending"), binding) \
                        or (committed_raw is None and ("controller_source_effects_committed" in memo
                            or adoption._wire(owner, memo.get("controller_source_effects_pending")) != pending_raw)) \
                        or (committed_raw is not None and ("controller_source_effects_pending" in memo
                            or adoption._wire(owner, memo.get("controller_source_effects_committed")) != committed_raw)) \
                        or not same(memo.get("pulse_history"), prepared["history"]) \
                        or "ready" in memo or "controller_source_committed" in memo \
                        or (source._SUCCESSOR_PENDING_KEYS - {"controller_source_pending", "controller_source_live_pending",
                            "controller_source_effects_pending", "controller_source_effects_committed",
                            "pulse_status_effects_pending", "live_loop_pending"}).intersection(memo) \
                        or not same(source._notification_marker(owner, memo), batch["notification_baseline_attempt"]):
                    source.refuse("checkpoint-live-source-authority-differs")
                if adoption._wire(owner, files["memo"].value, memo=True) != adoption._wire(owner, memo, memo=True):
                    source.refuse("checkpoint-live-memo-differs")
                graph_generation, _graph = effects._graph_generation(owner, source, transaction.live)
                if not same(graph_generation, pending["graph_generation"]):
                    source.refuse("checkpoint-live-graph-differs")
                package_current()
                current()

            def phase():
                authority()
                with owner["_live_files"]() as (live_files, live_current, _write):
                    actual = {key: live_files[key].value for key in ("candidate", "generation", "status")}
                    done = same(memo.get("live_loop_committed"), receipt)
                    if committed_effects is not None and not done:
                        source.refuse("checkpoint-live-effects-before-live")
                    if done:
                        valid = "live_loop_pending" not in memo and "pulse_status_effects_pending" not in memo \
                            and all(same(actual[key], value) for key, value in (
                                ("candidate", candidate), ("generation", generation), ("status", pending["status"])))
                    else:
                        valid = same(memo.get("live_loop_committed"), parent_receipt) and same(memo.get("pulse_status_effects_pending"), handoff)
                        if "live_loop_pending" in memo:
                            valid = valid and same(memo["live_loop_pending"], receipt) and same(actual["candidate"], candidate) \
                                and any(same(actual["generation"], value) for value in (historical["generation"], generation)) \
                                and any(same(actual["status"], value) for value in (historical["status"], pending["status"])) \
                                and (not same(actual["status"], pending["status"]) or same(actual["generation"], generation))
                        else:
                            valid = valid and any(same(actual["candidate"], value) for value in (historical["candidate"], candidate)) \
                                and same(actual["generation"], historical["generation"]) and same(actual["status"], historical["status"])
                    if not valid:
                        source.refuse("checkpoint-live-publication-phase-differs")
                    live_current()
                return done

            def finish_effects():
                nonlocal committed_effects, committed_raw
                if not phase():
                    source.refuse("checkpoint-live-finalize-before-live")
                observed = effects._live_generation(owner, source, transaction.live, memo, pending["status"], expected_binding=pending)
                expected = effects._receipt_from_pending(owner, source, transaction.live, pending, observed)
                effects._receipt_shape(owner, source, transaction.live, expected, batch, binding,
                    retained_status=pending["status"], checkpoint=True)
                if committed_effects is not None:
                    if not same(committed_effects, expected):
                        source.refuse("checkpoint-live-effects-receipt-differs")
                    return False
                if not finalize_effects:
                    return False
                updated = copy.deepcopy(memo)
                updated.pop("controller_source_effects_pending")
                updated["controller_source_effects_committed"] = expected
                encoded = adoption._wire(owner, updated, memo=True)
                owner["_memo_text"](updated)
                authority()
                parent_identity = files["memo"].parent_identity
                owner["atomic_write"](owner["MEMO_PATH"], encoded.decode("utf-8"), mode=0o600)
                written = observe("memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
                if written.parent_identity != parent_identity or written.raw != encoded:
                    source.refuse("checkpoint-live-effects-memo-differs")
                memo.clear()
                memo.update(updated)
                committed_effects = expected
                committed_raw = adoption._wire(owner, expected)
                phase()
                return True

            owner["_require_status_admission_unchanged"](admitted_status)
            if phase():
                changed = finish_effects()
                named_current()
                return changed
            staged = copy.deepcopy(memo)
            staged["live_loop_pending"] = receipt
            final = owner["_live_final_memo"](staged, candidate, receipt)
            for image in (staged, final):
                adoption._wire(owner, image, memo=True)
                owner["_memo_text"](image)
            if adoption._wire(owner, memo, memo=True) != original_memo:
                source.refuse("checkpoint-live-input-changed")
            if "live_loop_pending" not in memo:
                owner["_stage_live_generation"](memo=memo, status=pending["status"], prepare_inputs=inputs,
                    expected_prepare_inputs_sha256=candidate["prepare_inputs_sha256"])
                observe("memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
                if not same(memo, staged):
                    source.refuse("checkpoint-live-staged-memo-differs")
                phase()
            owner["_publish_staged_live_generation"](memo=memo)
            observe("memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
            if not same(memo, final) or not phase():
                source.refuse("checkpoint-live-final-memo-differs")
            observed = effects._live_generation(owner, source, transaction.live, memo, pending["status"], expected_binding=pending)
            if observed["generation_sha256"] != generation["generation_sha256"]:
                source.refuse("checkpoint-live-final-generation-differs")
            finish_effects()
            named_current()
        authority()
        named_current()
        return True
