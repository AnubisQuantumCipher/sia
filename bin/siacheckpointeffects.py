"""Durable compact effects WAL before status/live publication."""

import copy

import siacheckpointadoption as adoption
import siacheckpointcontent as content
import siasourceeffects as effects


def validate_pending(owner, *, memo, admitted_status, artifacts, pending):
    """Reconstruct the entire retained effects envelope and bind current graph."""
    source, live = adoption.source, adoption.transaction.live
    batch, transition = artifacts["capture"], artifacts["transition"]
    closure = batch["event_closure"]
    reconstructed = effects.prepare_checkpoint_pending(owner, admitted_status=admitted_status,
        batch=batch, binding=memo["controller_source_live_pending"], handoff=memo["pulse_status_effects_pending"],
        candidate=artifacts["candidate"], transition=transition,
        closure_result=None if closure is None else effects._closure_publication_result(closure),
        **{key: pending[key] for key in ("target_manifest", "corpus_generation", "sync_generation",
            "graph_generation", "status_generation", "status")},
        content_fields={key: pending[key] for key in effects.CONTENT_FIELDS})
    if adoption._wire(owner, reconstructed) != adoption._wire(owner, pending):
        source.refuse("checkpoint-effects-pending-replay-differs")
    graph_generation, _graph = effects._graph_generation(owner, source, live)
    if adoption._wire(owner, graph_generation) != adoption._wire(owner, pending["graph_generation"]):
        source.refuse("checkpoint-effects-pending-graph-differs")


def stage(owner, *, memo, admitted_status, directory, expected_manifest_sha256, expected_root_sha256):
    """Synchronize content, export graph and durably retain exact pending effects.

    Retry reads the actual memo/slot/package and graph, without content, engine
    or graph writes. This does not publish status/live state or acknowledge.
    """
    source, live = adoption.source, adoption.transaction.live
    args = dict(memo=memo, admitted_status=admitted_status, directory=directory,
                expected_manifest_sha256=expected_manifest_sha256, expected_root_sha256=expected_root_sha256)
    references = dict(owner)
    memo_raw, status_raw = adoption._wire(owner, memo, memo=True), adoption._wire(owner, admitted_status)
    with owner["brainstem_owner"](), owner["corpus_owner"](), adoption.publication._files(owner, source) as (files, observe, current, named_current):
        def unchanged():
            if any(owner.get(name) is not value for name, value in references.items()) \
                    or adoption._wire(owner, memo, memo=True) != memo_raw \
                    or adoption._wire(owner, admitted_status) != status_raw:
                source.refuse("checkpoint-effects-stage-input-changed")
            current()

        view = adoption.read_pending(owner, **args)
        if "controller_source_effects_pending" in memo:
            unchanged()
            named_current()
            return False
        indexed = content.synchronize(owner, **args)
        unchanged()
        artifacts = view["package"]["artifacts"]
        batch, transition = artifacts["capture"], artifacts["transition"]
        binding, handoff = memo["controller_source_live_pending"], memo["pulse_status_effects_pending"]
        owner["_require_status_admission_unchanged"](admitted_status)
        import siacheckpointparent
        siacheckpointparent.retain_graph(owner, directory=directory, committed=batch["epoch"]["predecessor"])
        # A successor's predecessor is itself a compact capture, which the
        # legacy parent retainer refuses by design.
        retain = siacheckpointparent.retain_checkpoint_live \
            if "head" in view["package"] else siacheckpointparent.retain_live
        retain(owner, directory=directory, committed=batch["epoch"]["predecessor"],
            memo=memo, admitted_status=admitted_status)
        owner["_export_graph_publication"]()
        graph_generation, graph = effects._graph_generation(owner, source, live)
        status = effects._project_status(owner, source, live, admitted_status, binding, handoff,
            transition, graph, memo["pulse_history"], owner["_controller_source_effects_observed_at"]())
        pages = indexed["committed"]["pages"]
        gist = pages["gist_publication"]
        pending = effects.prepare_checkpoint_pending(owner, admitted_status=admitted_status,
            batch=batch, binding=binding, handoff=handoff, candidate=artifacts["candidate"], transition=transition,
            closure_result=pages["closure_result"], target_manifest=indexed["target_manifest"],
            corpus_generation=indexed["committed"]["corpus_generation"], sync_generation=indexed["sync_generation"],
            graph_generation=graph_generation, status=status,
            status_generation=effects._status_generation_value(owner, source, live, status),
            content_fields={"gist_page_plan_sha256": gist["plan_sha256"], "gist_pages_sha256": gist["gist_pages_sha256"],
                "gist_publication": gist, "content_publication_sha256": pages["content_publication_sha256"]})
        updated = copy.deepcopy(memo)
        updated["controller_source_effects_pending"] = pending
        updated_raw = adoption._wire(owner, updated, memo=True)
        owner["_memo_text"](updated)
        adoption.read_pending(owner, **args)
        validate_pending(owner, memo=updated, admitted_status=admitted_status, artifacts=artifacts, pending=pending)
        unchanged()
        parent = files["memo"].parent_identity
        owner["atomic_write"](owner["MEMO_PATH"], updated_raw.decode("utf-8"), mode=0o600)
        written = observe("memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
        if written.parent_identity != parent or written.raw != updated_raw:
            source.refuse("checkpoint-effects-stage-memo-differs")
        adoption.read_pending(owner, **{**args, "memo": updated})
        unchanged()
        if adoption._wire(owner, updated, memo=True) != updated_raw:
            source.refuse("checkpoint-effects-stage-output-changed")
        named_current()
        memo.clear()
        memo.update(updated)
        named_current()
        return True
