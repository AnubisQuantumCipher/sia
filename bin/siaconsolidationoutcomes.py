"""Read-only qualification of selected consolidation claims, not settlement.

The caller holds the corpus lease and validates the retained delivery/admission.
Git and the existing source/index parsers remain trusted dependencies.
"""
import hashlib
import os

import siaconsolidationsnapshot as snapshot

MAX_HISTORY_COMMITS = 64
MAX_HISTORY_BYTES = 8192


def _committed_text(owner, commit, source):
    snapshot.object_id(commit)
    owner._event_source_parts(source["rel"])
    result = snapshot._git(
        owner._run_bounded_text_process, owner.CORPUS,
        ["cat-file", "blob", commit + ":" + source["rel"]],
        owner.MAX_EVENT_PAGE_BYTES)
    if result.returncode != 0:
        return None
    raw = result.stdout.encode("utf-8")
    if len(raw) > owner.MAX_EVENT_PAGE_BYTES:
        raise ValueError("consolidation original exceeds its byte bound")
    digest = hashlib.sha256(
        source["rel"].encode("utf-8") + b"\0" + raw).hexdigest()
    return result.stdout if digest == source["sha256"] else None


def _original_text(owner, record, source):
    """Prefer pinned history; bounded HEAD history covers later live claims."""
    text = _committed_text(owner, record["commit"], source)
    if text is not None:
        return text
    history = snapshot._git(
        owner._run_bounded_text_process, owner.CORPUS,
        ["log", "--format=%H", "-n" + str(MAX_HISTORY_COMMITS),
         "--", source["rel"]], MAX_HISTORY_BYTES)
    if history.returncode != 0:
        raise ValueError("consolidation original history is unavailable")
    commits = history.stdout.splitlines()
    if len(commits) > MAX_HISTORY_COMMITS:
        raise ValueError("consolidation original history exceeds its bound")
    for commit in commits:
        snapshot.object_id(commit)
    for commit in commits:
        if commit == record["commit"]:
            continue
        text = _committed_text(owner, commit, source)
        if text is not None:
            return text
    raise ValueError("exact consolidation original is unavailable")


def _verify_compacted_source(owner, record, source, epoch):
    if source not in epoch["source_manifest"]:
        raise ValueError("compacted source lacks exact epoch lineage")
    organ, date, part = owner._event_source_parts(source["rel"])
    text = _original_text(owner, record, source)
    item = (date, os.path.join(owner.CORPUS, source["rel"]), text,
            set(), source["sha256"], source["rel"], part)
    expected = owner._event_index_entries_for_sources([item], epoch["slug"])
    for entry in expected:
        if entry["event_id"] not in epoch["event_ids"]:
            raise ValueError("compacted source lacks epoch event completeness")
        observed = owner._read_event_index_entry(organ, entry["event_id"])
        if observed != entry:
            raise ValueError("compacted source lacks an exact event-index entry")


def _verify_compacted_day(owner, record, claim):
    slug = owner._epoch_slug_for_day(claim["organ"], claim["date"])
    epoch = owner._read_epoch_state(slug)
    if not epoch["source_manifest_declared"] or not epoch["event_ids_declared"] \
            or claim["date"] not in epoch["dates"]:
        raise ValueError("compacted day lacks declared epoch completeness")
    for source in claim["sources"]:
        _verify_compacted_source(owner, record, source, epoch)
    return slug


def inspect_claims(owner, record, claims):
    """Observe each selected day as intact or exactly represented after removal.

    This does not acknowledge a batch, authenticate the journal, verify unrelated
    epoch sources, or establish filesystem durability or publication readiness.
    """
    claims = owner._canonical_consolidation_scan(claims)
    live = set(owner._claimed_consolidation_paths(claims))
    outcomes = []
    for claim in claims["claims"]:
        paths = {os.path.join(owner.CORPUS, source["rel"])
                 for source in claim["sources"]}
        present = paths & live
        if present and present != paths:
            raise ValueError("consolidation day still has partial source cleanup")
        epoch = None if present else _verify_compacted_day(owner, record, claim)
        outcomes.append({
            "organ": claim["organ"], "date": claim["date"],
            "disposition": "retained" if present else "compacted",
            "sources": [dict(source) for source in claim["sources"]],
            "epoch": epoch})
    return outcomes
