"""Explicit cortex-boundary repair, not a pulse or an installation migration.

The caller supplies its already-loaded core.  No canonical sialib import may
silently select a different installation or mutable root.  All publication
authority comes from the named command journal and the existing append-only
cortex receipt; generic sync debt never grants recovery authority here.
"""

import copy
import hashlib
import json
import os
import re
import stat
import time
import uuid


PUBLICATION_SCHEMA = "sia-cortex-boundary-publication-v1"
LEGACY_PUBLICATION_SCHEMA = "sia-cortex-boundary-publication-v2"
LEGACY_GRAPH_SCHEMA = "sia-cortex-boundary-legacy-graph-v1"
LEGACY_GRAPH_LEAF = "cortex-boundary-legacy-graph.json"
LEGACY_GRAPH_AUTHORITY = "legacy-shape-only-not-ranking"
COMMAND_SCHEMA = "sia-cortex-boundary-command-v1"
TARGET_PATH = "sia/cortex.md"
NON_CLAIMS = (
    "This is an append-only product-prose repair, not evidence of cognition or a biological brain.",
    "No mind migration, pulse, consolidation, touch consumption, or daemon installation is performed.",
    "Publication does not establish cognitive improvement or replace the ordinary memory-readiness gate.",
    "Owner leases serialize cooperating SIA writers; the operating system, Git, and keeper remain trusted runtime dependencies.",
    "Generation witnesses are not authentication against a hostile same-user process able to rewrite both the journal and its inputs.",
    "Explicit legacy graph regeneration preserves old output as shape-only provenance; it neither invents historical publication identity nor admits that output to ranking.",
)
_HASH = re.compile(r"[0-9a-f]{64}")
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_REFUSAL_PHASES = {
    "runtime-owned": "ownership", "unclassified-repair-refusal": "unknown",
    "unrelated-publication-debt": "preflight", "unrelated-memo-debt": "preflight",
    "invalid-memo-marker": "preflight", "invalid-status-memo": "preflight",
    "unrelated-consolidation-debt": "preflight", "unrelated-thought-debt": "preflight",
    "unrelated-natural-history-debt": "preflight", "unrelated-recovery-entry": "preflight",
    "unrelated-thought-recovery-entry": "preflight", "unrelated-take-grade-entry": "preflight",
    "unrelated-take-migration-entry": "preflight", "unrelated-ledger-pending-entry": "preflight",
    "unrelated-graph-debt": "preflight", "unrelated-mind-recovery": "preflight",
    "unrelated-corpus-dirt": "preflight", "restore-policy-not-authorized": "preflight",
    "memo-generation-changed": "preflight", "graph-generation-not-authorized": "preflight",
    "unsafe-debt-directory": "preflight", "invalid-graph-snapshot": "preflight",
    "index-sync-failed": "publication", "graph-publication-failed": "publication",
    "legacy-graph-flag-required": "preflight", "legacy-graph-mode-mismatch": "preflight",
    "legacy-graph-only-not-authorized": "preflight", "legacy-graph-generation-changed": "preflight",
    "legacy-graph-preservation-conflict": "preflight", "legacy-graph-not-regenerated": "publication",
    "regenerated-graph-generation-changed": "publication",
}


class RepairRefusal(RuntimeError):
    """A closed code, never an arbitrary external error's display text."""
    def __init__(self, code):
        if code not in _REFUSAL_PHASES:
            raise ValueError("unknown cortex repair refusal code")
        self.reason_code = code
        self.phase = _REFUSAL_PHASES[code]
        super().__init__("cortex repair refused: " + code)


def refusal_result(error):
    code = error.reason_code if isinstance(error, RepairRefusal) \
        and error.reason_code in _REFUSAL_PHASES else "unclassified-repair-refusal"
    return {**_result("refused"), "reason_code": code, "phase": _REFUSAL_PHASES[code]}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _path(core):
    return os.path.join(core.STATE, "cortex-boundary-publication.json")


def _read(core, path, limit, label, *, missing=False, mode=None):
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        fd = core._open_source_nofollow(path, flags)
    except FileNotFoundError:
        if missing:
            return None
        raise RuntimeError(label + " is missing") from None
    except OSError as exc:
        raise RuntimeError(label + " cannot be opened safely") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() \
                or before.st_nlink != 1 or before.st_size > limit \
                or mode is not None and stat.S_IMODE(before.st_mode) != mode:
            raise RuntimeError(label + " is not a bounded owned single-link file")
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        current = core._source_path_identity(path, flags)
        if len(raw) > limit or core._file_generation(before) != core._file_generation(after) \
                or core._file_generation(after) != core._file_generation(current) \
                or not stat.S_ISREG(current.st_mode) or current.st_nlink != 1 \
                or current.st_uid != os.geteuid() \
                or mode is not None and stat.S_IMODE(current.st_mode) != mode:
            raise RuntimeError(label + " changed during admission")
        return raw
    finally:
        if fd >= 0:
            os.close(fd)


def _read_json(core, path, limit, label, *, missing=False):
    raw = _read(core, path, limit, label, missing=missing)
    if raw is None:
        return None
    try:
        value = core._strict_json_loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RuntimeError(label + " is malformed") from exc
    if not isinstance(value, dict):
        raise RuntimeError(label + " must be an object")
    return value


def _legacy_path(core):
    return os.path.join(core.STATE, LEGACY_GRAPH_LEAF)


def _read_graph(core):
    # The byte ceiling and complete no-follow walk precede decoding, JSON
    # materialization, and any preservation copy.
    raw = _read(core, core.GRAPH_PATH, core.MAX_STATE_JSON_BYTES, "graph snapshot")
    try:
        value = core._strict_json_loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RepairRefusal("invalid-graph-snapshot") from exc
    if not isinstance(value, dict):
        raise RepairRefusal("invalid-graph-snapshot")
    return raw, value


def _legacy_descriptor(raw):
    return {"schema": LEGACY_GRAPH_SCHEMA, "path": LEGACY_GRAPH_LEAF,
            "sha256": _digest(raw), "bytes": len(raw),
            "authority": LEGACY_GRAPH_AUTHORITY}


def _matches_legacy(raw, publication):
    descriptor = publication["legacy_graph"]
    return len(raw) == descriptor["bytes"] and _digest(raw) == descriptor["sha256"]


def _preserved_legacy(core, publication, *, missing=False):
    raw = _read(core, _legacy_path(core), core.MAX_STATE_JSON_BYTES,
                "preserved legacy graph", missing=missing, mode=0o600)
    if raw is not None and not _matches_legacy(raw, publication):
        raise RepairRefusal("legacy-graph-generation-changed")
    return raw


def _regenerated_graph(core, publication, projection):
    raw, value = _read_graph(core)
    counts = core._recoverable_graph_snapshot(value)
    if counts is None or value["snapshot"]["complete"] is not True \
            or projection["phase"] != "ready" \
            or projection["generation"] != publication["graph_dirty"]["generation"]:
        raise RepairRefusal("legacy-graph-not-regenerated")
    return {"publication_id": counts["publication_id"], "sha256": _digest(raw),
            "bytes": len(raw), "generation": projection["generation"]}


def _admit_legacy_publication_graph(core, memo, publication, projection):
    raw, value = _read_graph(core)
    preserved = _preserved_legacy(core, publication, missing=True)
    original = _matches_legacy(raw, publication)
    if preserved is None:
        # A write-ahead witness may outlive an interruption before preservation.
        # It cannot excuse a missing copy after any publication mutation.
        if publication["phase"] != "pending" or not original \
                or _digest(_json(memo)) != publication["memo_original_sha256"] \
                or _digest(_json(projection)) != publication["graph_original_sha256"]:
            raise RepairRefusal("legacy-graph-generation-changed")
    if publication["phase"] in {"ready", "complete"}:
        if _regenerated_graph(core, publication, projection) != publication["graph_regeneration"]:
            raise RepairRefusal("regenerated-graph-generation-changed")
        return
    if original:
        if not core._legacy_graph_snapshot_body_valid(value):
            raise RepairRefusal("invalid-graph-snapshot")
        original_projection = _digest(_json(projection)) == publication["graph_original_sha256"]
        if not original_projection and projection["phase"] != "scan":
            raise RepairRefusal("legacy-graph-not-regenerated")
        return
    # A bounded owned export can leave a canonical partial output.  It is never
    # returned as read authority: the pending transaction resets its recorded
    # empty projection and builds anew from the corpus on retry.
    if preserved is None or not memo.get("sync_needed", False) \
            or projection["generation"] != publication["graph_dirty"]["generation"] \
            or core._recoverable_graph_snapshot(value) is None:
        raise RepairRefusal("legacy-graph-generation-changed")


def _preserve_legacy_graph(core, publication):
    if _preserved_legacy(core, publication, missing=True) is not None:
        return
    raw, value = _read_graph(core)
    if not _matches_legacy(raw, publication) \
            or not core._legacy_graph_snapshot_body_valid(value):
        raise RepairRefusal("legacy-graph-generation-changed")
    parent = core._open_source_nofollow(core.STATE, os.O_RDONLY | os.O_DIRECTORY)
    try:
        before = os.fstat(parent)
        if before.st_uid != os.geteuid() or before.st_mode & 0o022:
            raise RuntimeError("legacy graph preservation parent is not owner-controlled")
        # Exclusive fixed-leaf creation never overwrites an unknown file.
        # A killed partial write is retained and refused, not silently deleted.
        descriptor = os.open(LEGACY_GRAPH_LEAF,
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=parent)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(parent)
        current = core._source_path_identity(core.STATE, os.O_RDONLY | os.O_DIRECTORY)
        if (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino) \
                or current.st_uid != os.geteuid() or current.st_mode & 0o022:
            raise RuntimeError("legacy graph preservation parent generation changed")
    finally:
        os.close(parent)
    if _preserved_legacy(core, publication) != raw:
        raise RepairRefusal("legacy-graph-generation-changed")
    source, _value = _read_graph(core)
    if source != raw:
        raise RepairRefusal("legacy-graph-generation-changed")


def _scan(core, directory, *, allowed=None, reason_code="unrelated-recovery-entry"):
    """No cleanup, chmod, creation, or swallowed unknown directory entries."""
    if reason_code not in {
            "unrelated-recovery-entry", "unrelated-thought-recovery-entry",
            "unrelated-take-grade-entry", "unrelated-take-migration-entry",
            "unrelated-ledger-pending-entry"}:
        raise ValueError("unknown recovery-directory refusal routing")
    try:
        fd = core._open_source_nofollow(directory, os.O_RDONLY | os.O_DIRECTORY)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RepairRefusal("unsafe-debt-directory") from exc
    try:
        before = os.fstat(fd)
        if before.st_uid != os.geteuid() or before.st_mode & 0o022:
            raise RuntimeError("repair debt directory is not owner-controlled")
        inspected = 0
        with os.scandir(fd) as entries:
            for entry in entries:
                inspected += 1
                if inspected > core.MAX_LEDGER_PENDING_RECORDS:
                    raise RuntimeError("repair debt directory exceeds its scan bound")
                if allowed is None or entry.name != allowed["record_id"] + ".json":
                    raise RepairRefusal(reason_code)
                info = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
                        or info.st_nlink != 1:
                    raise RuntimeError("repair ledger pending file is unsafe")
                record, _generation = core._read_pending_record(os.path.join(directory, entry.name))
                if record.get("schema") != core.LEDGER_PENDING_SCHEMA \
                        or any(record.get(key) != value for key, value in allowed.items()):
                    raise RuntimeError("repair ledger pending occurrence does not match")
        after = os.fstat(fd)
        target = core._source_path_identity(directory, os.O_RDONLY | os.O_DIRECTORY)
        if core._file_generation(before) != core._file_generation(after) \
                or core._file_generation(after) != core._file_generation(target):
            raise RuntimeError("repair debt directory generation changed")
    finally:
        os.close(fd)


def _memo_base(memo):
    return {key: value for key, value in memo.items() if key not in {"ready", "sync_needed"}}


def _readonly_debt(core, memo, publication, *, regenerate_legacy_graph=False):
    if core.load_memo() != memo:
        raise RepairRefusal("memo-generation-changed")
    if os.environ.get("SIA_RESTORE_FULL_SYNC") == "1":
        raise RepairRefusal("restore-policy-not-authorized")
    if not isinstance(memo.get("sync_needed", False), bool):
        raise RuntimeError("repair sync-needed state is malformed")
    # These validators do not settle a marker or withdraw an existing receipt.
    for name in ("_pending_notify_baseline_attempt", "_pending_source_replay_marker",
                 "_pending_pulse_marker", "_pending_dream_marker",
                 "_pending_consolidation_marker", "_pending_pulse_status_effects",
                 "_pending_brainstem_failure_publication"):
        try:
            pending = getattr(core, name)(memo)
        except (RuntimeError, ValueError) as exc:
            raise RepairRefusal("invalid-memo-marker") from exc
        if pending is not None:
            raise RepairRefusal("unrelated-memo-debt")
    if not core._status_history_shape(memo.get("pulse_history", [])) \
            or not core._status_dream_shape(memo.get("dream", {})) \
            or not core._status_redactions_shape(memo.get("redactions", {})):
        raise RepairRefusal("invalid-status-memo")
    core._agent_note_redaction_receipts(memo.get("agent_note_redaction_receipts"))
    if core._ready_receipt(memo) is None:
        raise RuntimeError("repair requires a previous successful publication receipt")
    debt = core._consolidation_scan_debt()
    if debt:
        raise RepairRefusal("unrelated-consolidation-debt")
    for path in (core._thought_recovery_claim_path(), core._thought_mind_replay_path()):
        if os.path.lexists(path):
            raise RepairRefusal("unrelated-thought-debt")
    _scan(core, core._thought_recovery_dir(), reason_code="unrelated-thought-recovery-entry")
    if core._load_thought_legacy_scan()["phase"] != "complete":
        raise RepairRefusal("unrelated-thought-debt")
    takes = core.siatakes
    for path, reason_code in (
            (takes._grade_transaction_dir(), "unrelated-take-grade-entry"),
            (takes._take_migration_transaction_dir(), "unrelated-take-migration-entry")):
        _scan(core, path, reason_code=reason_code)
    for kind in ("take", "intent"):
        if os.path.lexists(takes._history_paths(kind)["pending"]):
            raise RepairRefusal("unrelated-natural-history-debt")
        # This metadata-only function has no legacy-temp cleanup side effect;
        # unlike take_migration_required it does not use _transaction_pending.
        if takes.natural_history_debt(kind):
            raise RepairRefusal("unrelated-natural-history-debt")
    raw_mind = _read(core, core.siamind.MIND_PATH, core.siamind.MAX_MIND_BYTES, "raw mind state")
    try:
        mind = core._strict_json_loads(raw_mind.decode("utf-8"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RuntimeError("raw mind state is malformed") from exc
    if not isinstance(mind, dict) or type(mind.get("v")) is not int \
            or mind["v"] not in {1, 2, 3, core.siamind.MIND_VERSION}:
        raise RuntimeError("raw mind state version is unsupported")
    if mind.get("event_applied") or mind.get("event_batch_applied") is not None \
            or core._pending_dream_unit(mind) is not None:
        raise RepairRefusal("unrelated-mind-recovery")
    graph = _read_json(core, core._graph_projection_state_path(),
                       core.MAX_STATE_JSON_BYTES, "graph projection")
    graph = core._canonical_graph_projection_state(graph)
    if graph["failed_ops"]:
        raise RepairRefusal("unrelated-graph-debt")
    if publication is None:
        if memo.get("sync_needed", False) or graph["phase"] != "ready":
            raise RepairRefusal("unrelated-publication-debt")
        allowed = None
    else:
        if _digest(_json(_memo_base(memo))) != publication["memo_base_sha256"] \
                or _digest(raw_mind) != publication["mind_sha256"]:
            raise RuntimeError("repair original memo or mind generation changed")
        permitted_ready = [publication["original_ready"]]
        if publication["ready_receipt"] is not None:
            permitted_ready.append(publication["ready_receipt"])
        if memo["ready"] not in permitted_ready:
            raise RuntimeError("repair readiness receipt generation changed")
        original_graph = _digest(_json(graph)) == publication["graph_original_sha256"]
        own_graph = all(graph[key] == publication["graph_dirty"][key]
                        for key in ("schema", "generation", "started_at", "cutoff"))
        if not original_graph and not own_graph:
            raise RepairRefusal("graph-generation-not-authorized")
        if not memo.get("sync_needed", False):
            initial = _digest(_json(memo)) == publication["memo_original_sha256"]
            completed = (publication["ready_receipt"] is not None
                         and memo["ready"] == publication["ready_receipt"]
                         and own_graph and graph["phase"] == "ready")
            if not initial and not completed:
                raise RuntimeError("repair generic publication barrier was replaced")
        allowed = _occurrence(core, publication["repair"])
    _scan(core, core._ledger_pending_dir(), allowed=allowed,
          reason_code="unrelated-ledger-pending-entry")
    if publication is not None and publication["schema"] == LEGACY_PUBLICATION_SCHEMA:
        if not regenerate_legacy_graph:
            raise RepairRefusal("legacy-graph-flag-required")
        _admit_legacy_publication_graph(core, memo, publication, graph)
        return graph, _digest(raw_mind)
    if regenerate_legacy_graph:
        if publication is not None:
            raise RepairRefusal("legacy-graph-mode-mismatch")
        _raw, graph_snapshot = _read_graph(core)
        if not core._legacy_graph_snapshot_body_valid(graph_snapshot):
            raise RepairRefusal("invalid-graph-snapshot")
        if os.path.lexists(_legacy_path(core)):
            raise RepairRefusal("legacy-graph-preservation-conflict")
        return graph, _digest(raw_mind)
    graph_snapshot = core.read_state_json(core.GRAPH_PATH, {}, "graph snapshot")
    try:
        core._require_recoverable_graph_snapshot(graph_snapshot)
    except RuntimeError:
        # A killed bounded scan may have emitted an explicitly partial graph.
        # It is not read authority. Only this command's bound in-progress graph
        # generation may replace it; sync_needed alone is never sufficient.
        if publication is None or not memo.get("sync_needed", False) \
                or graph["phase"] != "scan" \
                or graph["generation"] != publication["graph_dirty"]["generation"] \
                or core._recoverable_graph_snapshot(graph_snapshot) is None:
            raise RepairRefusal("invalid-graph-snapshot") from None
    return graph, _digest(raw_mind)


def _git(core, *args):
    # No inherited GIT_DIR/INDEX_FILE/config parameters, external filters,
    # fsmonitor, hooks, signing commands, optional index refresh, or prompts.
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1",
           "GIT_TERMINAL_PROMPT": "0"}
    command = ["git", "-c", "core.hooksPath=" + os.devnull,
               "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
               "-c", "commit.gpgsign=false", "-c", "user.email=sia@omarchy.local",
               "-c", "user.name=SIA", *args]
    result = core._run_bounded_text_process(
        command, env=env, cwd=core.CORPUS, timeout=60,
        label="cortex repair git", output_limit=core.MAX_CONFIG_BYTES)
    if result.returncode != 0:
        # Do not echo corpus paths or arbitrary Git stderr to the front door.
        raise RuntimeError("cortex repair Git operation refused")
    return result.stdout


def _oid(value):
    if not isinstance(value, str):
        raise RuntimeError("cortex repair Git object identity is invalid")
    value = value.strip()
    if _OID.fullmatch(value) is None:
        raise RuntimeError("cortex repair Git object identity is invalid")
    return value


def _git_view(core):
    for path in (core.CORPUS, os.path.join(core.CORPUS, ".git")):
        info = core._source_path_identity(path, os.O_RDONLY | os.O_DIRECTORY)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() \
                or info.st_mode & 0o022:
            raise RuntimeError("cortex repair requires an owned ordinary Git corpus")
    if _git(core, "rev-parse", "--show-toplevel").strip() != os.path.abspath(core.CORPUS):
        raise RuntimeError("cortex repair Git root does not match corpus")
    # Operations such as cherry-pick/merge/rebase must not become this command's commit.
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-apply", "rebase-merge", "BISECT_LOG"):
        if os.path.lexists(os.path.join(core.CORPUS, ".git", marker)):
            raise RuntimeError("unrelated Git operation is pending")
    head = _oid(_git(core, "rev-parse", "--verify", "HEAD"))
    listing = _git(core, "ls-tree", "-z", head, "--", TARGET_PATH)
    match = re.fullmatch(r"100644 blob ([0-9a-f]{40}|[0-9a-f]{64})\t" + re.escape(TARGET_PATH) + "\x00", listing)
    if match is None:
        raise RuntimeError("cortex repair source is not an ordinary tracked root")
    head_raw = _git(core, "cat-file", "blob", match.group(1)).encode("utf-8")
    index_raw = _git(core, "show", ":" + TARGET_PATH).encode("utf-8")
    raw_status = _git(core, "status", "--porcelain=v1", "-z", "--untracked-files=all",
                      "--ignored=matching", "--ignore-submodules=none")
    dirty = []
    if raw_status:
        if not raw_status.endswith("\0"):
            raise RuntimeError("cortex repair Git status is truncated")
        for row in raw_status[:-1].split("\0"):
            if len(row) < 4 or row[2] != " " or row[:2] not in {" M", "M ", "MM"} \
                    or row[3:] != TARGET_PATH:
                raise RepairRefusal("unrelated-corpus-dirt")
            dirty.append(row)
        if len(dirty) != 1:
            raise RuntimeError("cortex repair Git status is ambiguous")
    return {"head": head, "head_raw": head_raw, "index_raw": index_raw, "dirty": dirty}


def _receipt(core, repair):
    value = {key: repair[key] for key in core._CORTEX_REPAIR_RECEIPT_KEYS}
    value["schema"] = core.CORTEX_BOUNDARY_REPAIR_SCHEMA
    return core._validate_cortex_repair_receipt(value)


def _occurrence(core, repair):
    basis = core._pending_basis(repair["order"], repair["action"], repair["arg1"],
                               repair["arg2"], repair["content"])
    return {**basis, "record_id": core._pending_identity(basis)}


def _message(publication):
    return "SIA: cortex product-metaphor boundary " + publication["id"]


def _validate_publication(core, value):
    keys = {"schema", "id", "path", "source_head", "repair", "phase",
            "memo_original_sha256", "memo_base_sha256", "original_ready",
            "graph_original_sha256", "graph_dirty", "mind_sha256",
            "commit_head", "ready_receipt"}
    legacy = isinstance(value, dict) and value.get("schema") == LEGACY_PUBLICATION_SCHEMA
    if legacy:
        keys |= {"legacy_graph", "graph_regeneration"}
    if not isinstance(value, dict) or set(value) != keys \
            or value.get("schema") not in {PUBLICATION_SCHEMA, LEGACY_PUBLICATION_SCHEMA} \
            or value.get("path") != TARGET_PATH \
            or not isinstance(value.get("id"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", value["id"]) is None \
            or value.get("phase") not in {"pending", "ready", "complete"}:
        raise RuntimeError("cortex publication witness is invalid")
    _oid(value["source_head"])
    if value["commit_head"] is not None:
        _oid(value["commit_head"])
    for key in ("memo_original_sha256", "memo_base_sha256", "graph_original_sha256", "mind_sha256"):
        if not isinstance(value[key], str) or _HASH.fullmatch(value[key]) is None:
            raise RuntimeError("cortex publication witness digest is invalid")
    core._validate_cortex_repair_journal(value["repair"])
    core._ready_receipt({"ready": value["original_ready"]})
    graph = core._canonical_graph_projection_state(value["graph_dirty"])
    if graph["phase"] != "scan" or graph["failed_ops"] or graph["candidates"] \
            or graph["pages_seen"] or graph["eligible_seen"] \
            or graph["queue"] != [{"relative": "", "levels": core.MAX_GRAPH_TREE_LEVELS, "page": {}}]:
        raise RuntimeError("cortex publication write-ahead graph is not fresh")
    if legacy:
        descriptor = value["legacy_graph"]
        if not isinstance(descriptor, dict) \
                or set(descriptor) != {"schema", "path", "sha256", "bytes", "authority"} \
                or descriptor.get("schema") != LEGACY_GRAPH_SCHEMA \
                or descriptor.get("path") != LEGACY_GRAPH_LEAF \
                or descriptor.get("authority") != LEGACY_GRAPH_AUTHORITY \
                or not isinstance(descriptor.get("sha256"), str) \
                or _HASH.fullmatch(descriptor["sha256"]) is None \
                or type(descriptor.get("bytes")) is not int \
                or not 0 < descriptor["bytes"] <= core.MAX_STATE_JSON_BYTES:
            raise RuntimeError("legacy graph preservation witness is invalid")
        regenerated = value["graph_regeneration"]
        if value["phase"] == "pending":
            if regenerated is not None:
                raise RuntimeError("pending legacy graph has a premature output receipt")
        elif not isinstance(regenerated, dict) \
                or set(regenerated) != {"publication_id", "sha256", "bytes", "generation"} \
                or not core._status_publication_id(regenerated.get("publication_id")) \
                or not isinstance(regenerated.get("sha256"), str) \
                or _HASH.fullmatch(regenerated["sha256"]) is None \
                or type(regenerated.get("bytes")) is not int \
                or not 0 < regenerated["bytes"] <= core.MAX_STATE_JSON_BYTES \
                or regenerated.get("generation") != graph["generation"]:
            raise RuntimeError("regenerated graph publication witness is invalid")
    if value["phase"] == "pending":
        if value["ready_receipt"] is not None:
            raise RuntimeError("pending cortex publication has a premature ready receipt")
    else:
        ready = core._ready_receipt({"ready": value["ready_receipt"]})
        if ready is None or ready["identity"] != value["id"] or ready["kind"] != "recovery" \
                or value["commit_head"] is None:
            raise RuntimeError("cortex publication completed receipt is misbound")
    return value


def _load_publication(core):
    value = _read_json(core, _path(core), core.MAX_CONFIG_BYTES, "cortex publication witness", missing=True)
    return None if value is None else _validate_publication(core, value)


def _save_publication(core, expected, value):
    _validate_publication(core, value)
    encoded = _json(value)
    if len(encoded) > core.MAX_CONFIG_BYTES:
        raise RuntimeError("cortex publication witness exceeds its bound")
    if _load_publication(core) != expected:
        raise RuntimeError("cortex publication witness changed before write")
    core.atomic_write(_path(core), encoded.decode("utf-8"), mode=0o600)
    if _load_publication(core) != value:
        raise RuntimeError("cortex publication witness did not persist")


def _root_generation(core, publication, view, current):
    repair = publication["repair"]
    source = _git(core, "cat-file", "blob", publication["source_head"] + ":" + TARGET_PATH).encode("utf-8")
    target = source + repair["append_text"].encode("utf-8")
    if len(source) != repair["source_bytes"] or _digest(source) != repair["source_sha256"] \
            or len(target) != repair["target_bytes"] or _digest(target) != repair["target_sha256"]:
        raise RuntimeError("cortex publication source/target witness changed")
    core._validate_cortex_root(source)
    core._validate_cortex_root(target)
    if current not in (source, target) or view["index_raw"] not in (source, target):
        raise RuntimeError("cortex repair worktree or staged bytes changed")
    if view["head"] == publication["source_head"]:
        if publication["commit_head"] is not None or view["head_raw"] != source:
            raise RuntimeError("cortex repair source Git generation changed")
    else:
        if current != target or view["head_raw"] != target or view["index_raw"] != target or view["dirty"]:
            raise RuntimeError("cortex repair committed target generation changed")
        if publication["commit_head"] is not None and view["head"] != publication["commit_head"]:
            raise RuntimeError("cortex repair commit identity changed")
        parents = _git(core, "rev-list", "--parents", "-n", "1", view["head"]).split()
        changed = _git(core, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z",
                       publication["source_head"], view["head"])
        message = _git(core, "log", "-1", "--format=%B", view["head"]).strip()
        if parents != [view["head"], publication["source_head"]] \
                or changed != TARGET_PATH + "\0" or message != _message(publication):
            raise RuntimeError("unrelated Git history cannot resume cortex repair")
    existing = core._load_cortex_repair_journal()
    if existing is not None and existing != repair:
        raise RuntimeError("cortex repair journal generation changed")
    receipt = core._load_cortex_repair_receipt()
    if receipt is not None and receipt != _receipt(core, repair):
        raise RuntimeError("cortex repair receipt generation changed")
    if current == target and receipt is None:
        raise RuntimeError("dirty cortex target has no exact receipt witness")
    return source, target


def _publication_barrier(core, memo, publication):
    """Install compatible generic debt with this journal's exact graph UUID.

    Intentionally no automatic corpus_mutation_barrier callback: the generic
    callback marks an additional random graph generation.  Both explicit
    durable writes below precede ensure_cortex, its receipt, root, and ledger.
    """
    core._mark_sync_needed(memo)
    core._save_graph_projection_state(copy.deepcopy(publication["graph_dirty"]))


def _commit_cortex(core, publication):
    view = _git_view(core)
    current = core._read_cortex_root_bytes()
    _source, target = _root_generation(core, publication, view, current)
    if current != target:
        raise RuntimeError("cortex repair target is not ready to commit")
    if view["head"] != publication["source_head"]:
        return view["head"]
    # hash-object --no-filters avoids repository clean filters entirely.
    # update-index stages only this fixed path, without add -A or attrs.
    blob = _oid(_git(core, "hash-object", "-w", "--no-filters", "--", TARGET_PATH))
    if core._read_cortex_root_bytes() != target \
            or _git(core, "cat-file", "blob", blob).encode("utf-8") != target:
        raise RuntimeError("cortex target changed before scoped staging")
    _git(core, "update-index", "--add", "--cacheinfo", "100644", blob, TARGET_PATH)
    staged = _git_view(core)
    _root_generation(core, publication, staged, core._read_cortex_root_bytes())
    if staged["head"] != publication["source_head"] or staged["index_raw"] != target:
        raise RuntimeError("cortex staged generation changed before commit")
    _git(core, "commit", "-q", "-m", _message(publication))
    committed = _git_view(core)
    _root_generation(core, publication, committed, core._read_cortex_root_bytes())
    if committed["head"] == publication["source_head"]:
        raise RuntimeError("cortex scoped commit did not persist")
    return committed["head"]


def _result(status, receipt=None):
    return {"schema": COMMAND_SCHEMA, "status": status, "slug": "sia/cortex",
            "repair": receipt, "non_claims": list(NON_CLAIMS)}


def repair_cortex_boundary(core, *, regenerate_legacy_graph=False):
    """Publish exactly one historical cortex suffix, or refuse without repair.

    The public CLI already holds its lifecycle reader.  These leases never
    stop/restart a service; an active resident owner causes a normal refusal.
    """
    if type(regenerate_legacy_graph) is not bool:
        raise ValueError("legacy graph regeneration option must be Boolean")
    with core.brainstem_owner(), core.corpus_owner():
        if core._CORPUS_MUTATION_BARRIER.get() is not None:
            raise RuntimeError("cortex repair cannot inherit another publication callback")
        publication = _load_publication(core)
        if publication is not None:
            legacy = publication["schema"] == LEGACY_PUBLICATION_SCHEMA
            if legacy and not regenerate_legacy_graph:
                raise RepairRefusal("legacy-graph-flag-required")
            if regenerate_legacy_graph and not legacy:
                raise RepairRefusal("legacy-graph-mode-mismatch")
        memo = core.load_memo()
        graph, mind_sha256 = _readonly_debt(
            core, memo, publication, regenerate_legacy_graph=regenerate_legacy_graph)
        view = _git_view(core)
        current = core._read_cortex_root_bytes()
        core._validate_cortex_root(current)
        if publication is None:
            if view["dirty"] or current != view["head_raw"] or current != view["index_raw"]:
                raise RuntimeError("unwitnessed dirty cortex cannot start repair")
            ready, _reason = core._cortex_boundary_status()
            if ready:
                if regenerate_legacy_graph:
                    raise RepairRefusal("legacy-graph-only-not-authorized")
                return _result("already-ready", core._load_cortex_repair_receipt())
            if core._load_cortex_repair_journal() is not None \
                    or core._load_cortex_repair_receipt() is not None:
                raise RuntimeError("unowned cortex repair cannot be adopted")
            if core.BRAIN_METAPHOR_BOUNDARY.encode("utf-8") in current:
                raise RuntimeError("cortex repair source already contains an unwitnessed boundary")
            target = current + core.CORTEX_BOUNDARY_REPAIR_SUFFIX.encode("utf-8")
            core._validate_cortex_root(target)
            order = time.time_ns()
            receipt = core._cortex_repair_receipt(current, target,
                                               core.CORTEX_BOUNDARY_REPAIR_SUFFIX.encode("utf-8"), order)
            repair = {**receipt, "schema": core.CORTEX_BOUNDARY_REPAIR_JOURNAL_SCHEMA,
                      "append_text": core.CORTEX_BOUNDARY_REPAIR_SUFFIX, "order": order,
                      "action": "MIGRATE:cortex-boundary-repair", "arg1": "sia/cortex",
                      "arg2": "product-metaphor-boundary-additive-v1",
                      "content": core._cortex_receipt_text(receipt)}
            publication = {
                "schema": PUBLICATION_SCHEMA, "id": uuid.uuid4().hex, "path": TARGET_PATH,
                "source_head": view["head"], "repair": repair, "phase": "pending",
                "memo_original_sha256": _digest(_json(memo)),
                "memo_base_sha256": _digest(_json(_memo_base(memo))),
                "original_ready": copy.deepcopy(memo["ready"]),
                "graph_original_sha256": _digest(_json(graph)),
                "graph_dirty": core._fresh_graph_projection_state(), "mind_sha256": mind_sha256,
                "commit_head": None, "ready_receipt": None}
            if regenerate_legacy_graph:
                raw, legacy_graph = _read_graph(core)
                if not core._legacy_graph_snapshot_body_valid(legacy_graph):
                    raise RepairRefusal("invalid-graph-snapshot")
                publication.update(schema=LEGACY_PUBLICATION_SCHEMA,
                                   legacy_graph=_legacy_descriptor(raw), graph_regeneration=None)
            _save_publication(core, None, publication)
        else:
            _root_generation(core, publication, view, current)
            if publication["phase"] == "complete":
                ready, reason = core._cortex_boundary_status()
                if not ready or memo.get("sync_needed", False) \
                        or memo["ready"] != publication["ready_receipt"]:
                    raise RuntimeError("completed cortex publication changed: " + reason)
                return _result("already-ready", _receipt(core, publication["repair"]))
            if regenerate_legacy_graph and publication["phase"] == "ready":
                # A fresh output receipt is already durable. Recheck its exact
                # bytes and finish that generation; do not re-export beneath it.
                _finish_publication(core, memo, publication)
                return _result("repaired", _receipt(core, publication["repair"]))

        # Repeat every read-only admission before the first corpus/ledger effect.
        _readonly_debt(core, memo, publication, regenerate_legacy_graph=regenerate_legacy_graph)
        _root_generation(core, publication, _git_view(core), core._read_cortex_root_bytes())
        if regenerate_legacy_graph:
            _preserve_legacy_graph(core, publication)
        _publication_barrier(core, memo, publication)
        if core._load_cortex_repair_journal() is None:
            ready, _reason = core._cortex_boundary_status()
            if not ready:
                core._write_cortex_repair_state(core.CORTEX_BOUNDARY_REPAIR_JOURNAL,
                                              publication["repair"])
        core.ensure_cortex()
        ready, reason = core._cortex_boundary_status()
        if not ready:
            raise RuntimeError("cortex append-only receipt did not settle: " + reason)
        commit_head = _commit_cortex(core, publication)
        if publication["commit_head"] != commit_head:
            updated = dict(publication, commit_head=commit_head)
            _save_publication(core, publication, updated)
            publication = updated
        synced, _note = core.brain_sync()
        if not synced:
            raise RepairRefusal("index-sync-failed")
        try:
            core._export_graph_publication()
        except Exception as exc:
            raise RepairRefusal("graph-publication-failed") from exc
        # Recheck exact live/committed bytes and unrelated state before issuing
        # the compatible ready receipt. No mind loader or generic recovery runs.
        graph, _mind = _readonly_debt(
            core, memo, publication, regenerate_legacy_graph=regenerate_legacy_graph)
        _root_generation(core, publication, _git_view(core), core._read_cortex_root_bytes())
        if graph["generation"] != publication["graph_dirty"]["generation"] or graph["phase"] != "ready":
            raise RuntimeError("cortex graph publication did not complete its bound generation")
        if publication["ready_receipt"] is None:
            ready_memo = core._with_ready_receipt(memo, "recovery", publication["id"])
            updated = dict(publication, phase="ready", ready_receipt=ready_memo["ready"])
            if regenerate_legacy_graph:
                updated["graph_regeneration"] = _regenerated_graph(core, publication, graph)
            _save_publication(core, publication, updated)
            publication = updated
        _finish_publication(core, memo, publication)
        return _result("repaired", _receipt(core, publication["repair"]))


def _finish_publication(core, memo, publication):
    if publication["schema"] == LEGACY_PUBLICATION_SCHEMA:
        # This check occurs after the ready witness persisted, not merely
        # before it. A substituted output must not receive memo readiness.
        _readonly_debt(core, memo, publication, regenerate_legacy_graph=True)
        _root_generation(core, publication, _git_view(core), core._read_cortex_root_bytes())
    updated_memo = dict(memo, ready=copy.deepcopy(publication["ready_receipt"]))
    updated_memo.pop("sync_needed", None)
    core._write_memo(updated_memo)
    if core.load_memo() != updated_memo:
        raise RuntimeError("cortex publication readiness receipt did not persist")
    completed = dict(publication, phase="complete")
    _save_publication(core, publication, completed)
