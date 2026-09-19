"""Additive page effects of an actual adopted compact transaction."""

import copy

import siacheckpointadoption as adoption
import siasourceeffects as effects
import siasourcegist as gist


NON_CLAIMS = (
    "Page publication is not corpus commit, index synchronization, graph/status/live publication, source acknowledgment or readiness.",
    "The retained capture and its real historical parent are validated; this does not authenticate external event truth or claim current source freshness.",
    "Gist pages are derived additions and never replace source episodes; no held-out cognitive win is established.",
    "Exact existing page bytes permit retry but do not establish which attempt first wrote them.",
)


def publish_pages(owner, *, memo, admitted_status, directory,
                  expected_manifest_sha256, expected_root_sha256):
    """Publish exact retained event/gist pages under ordinary owner leases.

    A preexisting durable status handoff is mandatory. Source fixed slot, memo,
    retained package and owner inputs remain pinned across additive writes.
    Neither this call nor its receipt advances any transaction memo marker.
    """
    source, live, transaction = adoption.source, adoption.transaction.live, adoption.transaction
    args = dict(memo=memo, admitted_status=admitted_status, directory=directory,
                expected_manifest_sha256=expected_manifest_sha256, expected_root_sha256=expected_root_sha256)
    references = dict(owner)
    originals = {"memo": adoption._wire(owner, memo, memo=True),
                 "status": adoption._wire(owner, admitted_status)}
    with owner["brainstem_owner"](), owner["corpus_owner"](), adoption.publication._files(owner, source) as (files, observe, current, named_current):
        with transaction._hold_prepared(owner, directory=directory,
                expected_manifest_sha256=expected_manifest_sha256, expected_root_sha256=expected_root_sha256) as (retained, package_current):
            view = adoption.read_pending(owner, **args)
            if "pulse_status_effects_pending" not in memo:
                source.refuse("checkpoint-content-status-handoff-missing")
            artifacts = retained["artifacts"]
            batch, transition = artifacts["capture"], artifacts["transition"]
            closure = batch["event_closure"]
            plan = gist.prepare(owner, transition=transition,
                                expected_transition_sha256=transition["transition_sha256"])
            plan_raw = adoption._wire(owner, plan)
            expected_gist = gist.publication_receipt(owner, plan=plan, expected_plan_sha256=plan["plan_sha256"])
            targets = effects._target_versions(owner, source, closure) + copy.deepcopy(plan["target_versions"])
            if len({row["slug"] for row in targets}) != len(targets):
                source.refuse("checkpoint-content-target-collision")
            targets = sorted(targets, key=lambda row: row["slug"])

            def unchanged():
                if any(owner.get(name) is not value for name, value in references.items()) \
                        or adoption._wire(owner, memo, memo=True) != originals["memo"] \
                        or adoption._wire(owner, admitted_status) != originals["status"] \
                        or adoption._wire(owner, plan) != plan_raw:
                    source.refuse("checkpoint-content-input-changed")
                package_current()
                current()

            unchanged()
            closure_result = None
            if closure is not None:
                closure_result = owner["_publish_event_page_batch_closure"](
                    closure=closure, expected_closure_sha256=closure["closure_sha256"])
            effects._closure_result_identity(source, live, closure,
                None if closure_result is None else live._sha(closure_result))
            unchanged()
            gist_result = owner["_publish_controller_source_gist_page_plan"](
                plan=plan, expected_plan_sha256=plan["plan_sha256"])
            if adoption._wire(owner, gist_result) != adoption._wire(owner, expected_gist):
                source.refuse("checkpoint-content-gist-result-differs")
            unchanged()
            adoption.read_pending(owner, **args)
            result = {"schema": "sia-checkpoint-page-publication-v1", "status": "pages-published-not-indexed",
                "manifest_sha256": expected_manifest_sha256, "source_batch_sha256": batch["batch_sha256"],
                "closure_result": closure_result, "gist_publication": gist_result,
                "target_versions": targets, "content_publication_sha256": effects._content_identity(live, closure,
                    None if closure_result is None else live._sha(closure_result), gist_result),
                "non_claims": list(NON_CLAIMS)}
            raw = adoption._wire(owner, result)
            detached = copy.deepcopy(result)
            if adoption._wire(owner, detached) != raw:
                source.refuse("checkpoint-content-result-copy-differs")
            unchanged()
        # Package close callbacks run before the last durable authority sweep.
        adoption.read_pending(owner, **args)
        current()
        named_current()
        return detached


def synchronize(owner, *, memo, admitted_status, directory,
                expected_manifest_sha256, expected_root_sha256):
    """Commit compact pages and synchronize their exact targets via gbrain.

    The existing engine helper owns receipt/descriptor/process admission and
    synchronization. Its returned generation must join the actual corpus cut
    and complete target manifest; no row or receipt is fabricated here.
    """
    source, live = adoption.source, adoption.transaction.live
    args = dict(memo=memo, admitted_status=admitted_status, directory=directory,
                expected_manifest_sha256=expected_manifest_sha256, expected_root_sha256=expected_root_sha256)
    references = dict(owner)
    memo_raw, status_raw = adoption._wire(owner, memo, memo=True), adoption._wire(owner, admitted_status)
    with owner["brainstem_owner"](), owner["corpus_owner"](), adoption.publication._files(owner, source) as (files, observe, current, named_current):
        committed = commit_pages(owner, **args)
        committed_raw = adoption._wire(owner, committed)

        def unchanged():
            if any(owner.get(name) is not value for name, value in references.items()) \
                    or adoption._wire(owner, memo, memo=True) != memo_raw \
                    or adoption._wire(owner, admitted_status) != status_raw \
                    or adoption._wire(owner, committed) != committed_raw:
                source.refuse("checkpoint-content-sync-input-changed")
            current()

        unchanged()
        corpus = committed["corpus_generation"]
        targets = committed["pages"]["target_versions"]
        manifest, generation = [], None
        if corpus is not None:
            observed = owner["_controller_source_sync_generation"](
                corpus_generation=corpus, target_versions=targets)
            if type(observed) is not dict or set(observed) != {
                    "sync_generation", "target_manifest", "target_manifest_sha256"}:
                source.refuse("checkpoint-content-sync-result-shape")
            manifest = effects._target_manifest(owner, source, live, observed["target_manifest"], targets)
            manifest_pin = live._sha(manifest)
            if observed["target_manifest_sha256"] != manifest_pin:
                source.refuse("checkpoint-content-sync-manifest-differs")
            generation = effects._sync_generation(owner, source, live,
                observed["sync_generation"], corpus, manifest_pin, len(manifest))
        elif targets:
            source.refuse("checkpoint-content-sync-corpus-missing")
        unchanged()
        adoption.read_pending(owner, **args)
        result = {"schema": "sia-checkpoint-index-publication-v1",
            "status": "no-content-to-index" if generation is None else "content-index-synchronized-not-live",
            "committed": committed, "sync_generation": generation,
            "target_manifest": manifest, "target_manifest_sha256": live._sha(manifest),
            "non_claims": [
                "Content/index synchronization is not graph/status/live publication, source acknowledgment, current readiness or observed recall delivery.",
                "The original engine receipt, process and target-projection boundaries remain controlling; no cognitive benchmark win is established.",
                "An empty content set does not establish index synchronization; no engine call occurs for that case."]}
        raw = adoption._wire(owner, result)
        detached = copy.deepcopy(result)
        if adoption._wire(owner, detached) != raw:
            source.refuse("checkpoint-content-sync-result-copy-differs")
        unchanged()
        named_current()
        return detached


def commit_pages(owner, *, memo, admitted_status, directory,
                 expected_manifest_sha256, expected_root_sha256):
    """Publish/replay exact compact pages and obtain the original clean Git cut.

    No caller-supplied page receipt is accepted as permission to commit. Empty
    content performs no Git commit. The nested page receipt keeps its narrower
    claims; this outer result additionally records a validated corpus cut.
    """
    source, live = adoption.source, adoption.transaction.live
    args = dict(memo=memo, admitted_status=admitted_status, directory=directory,
                expected_manifest_sha256=expected_manifest_sha256, expected_root_sha256=expected_root_sha256)
    references = dict(owner)
    memo_raw, status_raw = adoption._wire(owner, memo, memo=True), adoption._wire(owner, admitted_status)
    with owner["brainstem_owner"](), owner["corpus_owner"](), adoption.publication._files(owner, source) as (files, observe, current, named_current):
        pages = publish_pages(owner, **args)
        pages_raw = adoption._wire(owner, pages)

        def unchanged():
            if any(owner.get(name) is not value for name, value in references.items()) \
                    or adoption._wire(owner, memo, memo=True) != memo_raw \
                    or adoption._wire(owner, admitted_status) != status_raw \
                    or adoption._wire(owner, pages) != pages_raw:
                source.refuse("checkpoint-content-commit-input-changed")
            current()

        unchanged()
        adoption.read_pending(owner, **args)
        generation = None
        if pages["target_versions"]:
            generation = owner["_controller_source_corpus_commit_generation_v2"](
                source_batch_sha256=pages["source_batch_sha256"],
                content_publication_sha256=pages["content_publication_sha256"])
            generation = effects._corpus_generation(owner, source, live, generation)
        unchanged()
        adoption.read_pending(owner, **args)
        result = {"schema": "sia-checkpoint-corpus-publication-v1",
            "status": "no-pages-to-commit" if generation is None else "pages-committed-not-indexed",
            "pages": pages, "corpus_generation": generation,
            "non_claims": [
                "A clean corpus Git cut is not index synchronization, graph/status/live publication, source acknowledgment or readiness.",
                "The nested page receipt retains its original content/origin and historical-capture boundaries; no cognitive win is established.",
                "Retry may observe a different before-commit field while retaining the same resulting clean commit; byte-identical receipts are not promised."]}
        raw = adoption._wire(owner, result)
        detached = copy.deepcopy(result)
        if adoption._wire(owner, detached) != raw:
            source.refuse("checkpoint-content-commit-result-copy-differs")
        unchanged()
        named_current()
        return detached
