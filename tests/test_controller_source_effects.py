"""Commit one bound controller-source pulse through its observable effects.

The fixture composes real source capture/retention, source-live binding and the
durable status-effects handoff.  The operation under test must then publish an
exact non-null closure, obtain structured Git and source-scoped gbrain
generations, publish a fresh graph and matching status/live generation, and
only then write its effects receipt.  A null closure skips Git/gbrain but still
publishes the staged status effects, live generation and receipt.

Structured Git/gbrain returns are controlled observations here.  They prove
the caller's validation and ordering contract, not the external programs.  A
separate real-boundary lane must prove their parsers and descriptor ownership.
"""

import contextlib
import copy
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import stat
import unittest
from unittest import mock

from tests import test_controller_source_status_effects as status_tests
from tests import test_live_loop as live_tests


PUBLISHER = "_publish_controller_source_effects"
COMMITTER = "_controller_source_corpus_commit_generation"
SYNCER = "_controller_source_sync_generation"
BOUNDARY = "_controller_source_effects_boundary"
CLOCK = "_controller_source_effects_observed_at"
NON_CLAIMS_NAME = "CONTROLLER_SOURCE_EFFECTS_NON_CLAIMS"
GRAPH_AT = "2026-09-06T12:00:02Z"
STATUS_AT = "2026-09-06T12:00:03Z"
NON_CLAIMS = (
    "The effects receipt binds one retained source/live transition, staged status-effects handoff, local artifact bytes, structured corpus generation and source-scoped index witnesses; it does not authenticate source truth, complete machine history or a hostile same-user environment.",
    "Matching logical page witnesses and a zero-unembedded count do not prove embedding-vector values, ranking behavior, retrieval quality or a held-out cognitive-mechanism win.",
    "Publication does not acknowledge source cursors, settle source refusals, archive the retained batch, prove output delivery or establish readiness.",
    "The receipt is local transaction evidence, not JACKAL assurance or biological cognition.",
)
RECEIPT_KEYS = {
    "schema", "status", "source_batch_sha256",
    "source_batch_wire_sha256", "source_live_publication_sha256",
    "event_closure_sha256", "closure_result_sha256",
    "status_effects_sha256", "target_manifest",
    "target_manifest_sha256", "corpus_generation", "sync_generation",
    "graph_generation", "status_generation", "live_generation",
    "prepare_inputs_sha256", "state_sha256", "transition_sha256",
    "non_claims", "receipt_sha256",
}
PENDING_KEYS = {
    "schema", "source_batch_sha256", "source_batch_wire_sha256",
    "source_live_publication_sha256", "event_closure_sha256",
    "closure_result_sha256", "status_effects_sha256", "target_manifest",
    "target_manifest_sha256", "corpus_generation", "sync_generation",
    "graph_generation", "status_generation", "status",
    "prepare_inputs_sha256", "state_sha256", "transition_sha256",
    "non_claims", "pending_sha256",
}
CORPUS_KEYS = {
    "schema", "object_format", "git_executable_sha256",
    "before_commit_oid", "corpus_commit_oid", "corpus_tree_oid", "clean",
    "generation_sha256",
}
SYNC_KEYS = {
    "schema", "source_id", "engine_version", "gbrain_commit",
    "gbrain_bun_lock_sha256", "gbrain_pin_sha256",
    "gbrain_pin_receipt_sha256", "gbrain_release_receipt_sha256",
    "gbrain_executable_sha256", "version_raw_sha256",
    "sync_raw_sha256", "sync_stderr_sha256", "sync_result_sha256",
    "sync_status", "sync_requested_commit", "links_raw_sha256",
    "links_stderr_sha256", "links_result_sha256",
    "links_stale_remaining", "mentions_raw_sha256",
    "mentions_stderr_sha256", "mentions_result_sha256",
    "status_raw_sha256", "status_stderr_sha256", "status_result_sha256",
    "status_last_commit", "local_path", "index_manifest_sha256",
    "chunks_unembedded", "embedding_column", "unacknowledged_failures",
    "projection_request_sha256", "projection_raw_sha256",
    "projection_stderr_sha256", "projection_result_sha256",
    "projection_target_count", "projection_retrieval_bookkeeping_updated",
    "projection_operation_writes_performed", "generation_sha256",
}
TARGET_KEYS = {
    "slug", "source_sha256", "version_sha256", "page_state",
    "parse_error_codes", "expected_projection_sha256",
    "current_projection_sha256", "current_content_hash",
    "current_content_hash_match", "projection_match",
}
GRAPH_KEYS = {
    "publication_id", "raw_bytes", "raw_sha256", "nodes", "edges",
    "pages", "complete", "generation_sha256",
}
STATUS_KEYS = {
    "publication_id", "ts", "raw_bytes", "raw_sha256",
    "semantic_sha256", "generation_sha256",
}
LIVE_KEYS = {
    "publication_id", "candidate_sha256", "generation_sha256",
    "status_sha256", "candidate_raw_sha256", "generation_raw_sha256",
}
REFUSALS = (ValueError, RuntimeError, OSError)


def _path_image(path):
    path = Path(path)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    identity = (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
    )
    if stat.S_ISREG(info.st_mode):
        payload = path.read_bytes()
    elif stat.S_ISLNK(info.st_mode):
        payload = os.readlink(path)
    else:
        payload = None
    return identity, payload


def _wire(path):
    raw = Path(path).read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def _own(value):
    return live_tests.digest({
        key: item for key, item in value.items()
        if key != "generation_sha256"
    })


def _plan_result(plan):
    return {
        "schema": "sia-event-page-render-publication-v1",
        "status": "page-bytes-published",
        "plan_sha256": plan["plan_sha256"],
        "day_slugs": plan["day_slugs"],
        "appended_event_ids": plan["appended_event_ids"],
        "admissions": plan["admissions"],
        "page_versions": [
            {key: page[key]
             for key in ("slug", "raw_sha256", "version_sha256")}
            for page in plan["pages"]
        ],
        "non_claims": plan["non_claims"],
    }


def _closure_result(closure):
    batches = []
    for batch in closure["batches"]:
        batches.append({
            "schema": "sia-event-page-render-batch-publication-v1",
            "status": "page-bytes-published",
            "batch_sha256": batch["batch_sha256"],
            "members": [_plan_result(plan) for plan in batch["members"]],
            "non_claims": batch["non_claims"],
        })
    return {
        "schema": "sia-event-page-closure-publication-v1",
        "status": "page-bytes-published",
        "closure_sha256": closure["closure_sha256"],
        "batches": batches,
        "non_claims": closure["non_claims"],
    }


class ControllerSourceEffects(unittest.TestCase):
    def setUp(self):
        self.effects = status_tests.ControllerSourceStatusEffects(
            methodName="runTest")
        self.effects.setUp()
        self.addCleanup(self.effects.doCleanups)
        self.producer = self.effects.producer
        self.source = self.effects.source
        self.live = self.effects.live
        self.lib = self.effects.lib
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in (
                ("CORPUS", str(self.source.lib.CORPUS)),
                ("SHARE", str(self.source.lib.SHARE))):
            self.stack.enter_context(mock.patch.object(
                self.lib, name, value))
        self.admitted_status = self.effects._install_status()
        self.batch = None
        self.candidate = None
        self.transition = None
        self.binding = None
        self.handoff = None
        self.memo_before = None
        self.fresh_graph = None
        self.expected_status = None
        self.corpus_generation = self._corpus_generation()
        self.target_manifest = []
        self.sync_generation = None
        self.memo_after_live = None
        self.committed_generation = None

    @contextlib.contextmanager
    def fresh(self):
        case = type(self)(methodName="runTest")
        case.setUp()
        try:
            yield case
        finally:
            case.doCleanups()

    @staticmethod
    def _corpus_generation(**changes):
        body = {
            "schema": "sia-controller-source-corpus-generation-v1",
            "object_format": "sha1",
            "git_executable_sha256": "3" * 64,
            "before_commit_oid": "b" * 40,
            "corpus_commit_oid": "a" * 40,
            "corpus_tree_oid": "c" * 40,
            "clean": True,
        }
        body.update(changes)
        body.pop("generation_sha256", None)
        return {**body, "generation_sha256": live_tests.digest(body)}

    def _manifest(self, closure):
        if closure is None:
            return []
        rows = {}
        for batch in closure["batches"]:
            for plan in batch["members"]:
                for page in plan["pages"]:
                    row = {
                        "slug": page["slug"],
                        "source_sha256": page["raw_sha256"],
                        "version_sha256": page["version_sha256"],
                        "page_state": "live", "parse_error_codes": [],
                        "expected_projection_sha256": "4" * 64,
                        "current_projection_sha256": "4" * 64,
                        "current_content_hash": "4" * 64,
                        "current_content_hash_match": True,
                        "projection_match": True,
                    }
                    previous = rows.setdefault(page["slug"], row)
                    self.assertEqual(previous, row)
        return [rows[slug] for slug in sorted(rows)]

    def _sync_generation(self, manifest, **changes):
        body = {
            "schema": "sia-controller-source-sync-generation-v2",
            "source_id": "sia",
            "engine_version": "fixture-engine",
            "gbrain_commit": "7" * 40,
            "gbrain_bun_lock_sha256": "8" * 64,
            "gbrain_pin_sha256": "9" * 64,
            "gbrain_pin_receipt_sha256": "0" * 64,
            "gbrain_release_receipt_sha256": "a" * 64,
            "gbrain_executable_sha256": "d" * 64,
            "version_raw_sha256": "b" * 64,
            "sync_raw_sha256": "e" * 64,
            "sync_stderr_sha256": "c" * 64,
            "sync_result_sha256": "f" * 64,
            "sync_status": "synced",
            # The installed sync JSON has no returned ``toCommit`` field.
            # Bind the locally requested commit and use the independently
            # parsed plain ``status --json`` row as the postcondition.
            "sync_requested_commit":
                self.corpus_generation["corpus_commit_oid"],
            "links_raw_sha256": "1" * 64,
            "links_stderr_sha256": "2" * 64,
            "links_result_sha256": "3" * 64,
            "links_stale_remaining": 0,
            "mentions_raw_sha256": "4" * 64,
            "mentions_stderr_sha256": "5" * 64,
            "mentions_result_sha256": "6" * 64,
            "status_raw_sha256": "1" * 64,
            "status_stderr_sha256": "2" * 64,
            "status_result_sha256": "2" * 64,
            "status_last_commit":
                self.corpus_generation["corpus_commit_oid"],
            "local_path": str(self.source.lib.CORPUS),
            "index_manifest_sha256": live_tests.digest(manifest),
            "chunks_unembedded": 0,
            "embedding_column": "embedding",
            "unacknowledged_failures": 0,
            "projection_request_sha256": "3" * 64,
            "projection_raw_sha256": "4" * 64,
            "projection_stderr_sha256": "5" * 64,
            "projection_result_sha256": "6" * 64,
            "projection_target_count": len(manifest),
            "projection_retrieval_bookkeeping_updated": False,
            "projection_operation_writes_performed": False,
        }
        body.update(changes)
        body.pop("generation_sha256", None)
        return {**body, "generation_sha256": live_tests.digest(body)}

    def _target_versions(self):
        return [{
            key: row[key]
            for key in ("slug", "source_sha256", "version_sha256")
        } for row in self.target_manifest]

    def publisher(self):
        value = getattr(self.lib, PUBLISHER, None)
        self.assertTrue(callable(value),
                        "missing controller-source effects publisher: "
                        + PUBLISHER)
        return value

    def start(self, *, empty=False, batch=None):
        if batch is not None and empty:
            raise ValueError("an explicit source batch cannot also be empty")
        batch = (self.producer._capture(empty=empty)
                 if batch is None else copy.deepcopy(batch))
        bound = self.effects._bind(batch, status=self.admitted_status)
        arguments = self.effects._arguments(bound)
        prepared = self.effects._call(arguments)
        self.assertIsNone(self.effects._stager()(
            memo=self.live.memo, **arguments))
        self.batch, self.candidate, self.transition, self.binding = bound
        self.handoff = copy.deepcopy(
            self.live.memo["pulse_status_effects_pending"])
        self.memo_before = copy.deepcopy(self.live.memo)
        self.target_manifest = self._manifest(batch["event_closure"])
        self.sync_generation = self._sync_generation(self.target_manifest)
        self.assertEqual(self.handoff["effects"], prepared["effects"])
        self.assertEqual(self.live.memo["pulse_history"], prepared["history"])
        self.assertNotIn("live_loop_committed", self.live.memo)
        self.assertNotIn("controller_source_effects_committed", self.live.memo)
        self.assertNotIn("ready", self.live.memo)
        return batch

    def _paths(self):
        return {
            "source": Path(self.producer.source_path),
            "memo": Path(self.live.paths["MEMO_PATH"]),
            "status": Path(self.live.paths["STATUS_PATH"]),
            "graph": Path(self.live.paths["GRAPH_PATH"]),
            "candidate": Path(self.live.paths["LIVE_CANDIDATE_PATH"]),
            "generation": Path(self.live.paths["LIVE_STATE_PATH"]),
            "cursor": self.source.cursors_path,
            "journal-sys": self.source.root / "state/journal-sys.cursor",
            "journal-user": self.source.root / "state/journal-user.cursor",
            "archive": self.live.root / "controller-source-archive",
        }

    def _images(self):
        return {name: _path_image(path)
                for name, path in self._paths().items()}

    def _new_graph(self):
        graph = self.live._read("GRAPH_PATH")
        graph["ts"] = GRAPH_AT
        graph["publication_id"] = "3" * 32
        self.assertIsNotNone(self.lib._recoverable_graph_snapshot(graph))
        return graph

    def _new_status(self, graph):
        snapshot = self.lib._recoverable_graph_snapshot(graph)
        self.assertIsNotNone(snapshot)
        status = copy.deepcopy(self.admitted_status)
        effects = self.handoff["effects"]
        status.update({
            "version": self.lib.VERSION,
            "ts": STATUS_AT,
            "state": ("thinking" if effects["events_pulse"] else "ok"),
            "publication_id": self.binding["publication_id"],
            "graph_publication_id": snapshot["publication_id"],
            "day": effects["day"],
            "events_pulse": effects["events_pulse"],
            "events_today": sum(
                row["today"] for row in effects["organs"].values()),
            "organs": copy.deepcopy(effects["organs"]),
            "pages": snapshot["pages"],
            "graph_nodes": snapshot["nodes"],
            "graph_edges": snapshot["edges"],
            "history": copy.deepcopy(self.live.memo["pulse_history"]),
            "workspace": copy.deepcopy(
                self.transition["state"]["workspace"]["slots"]),
            "sync_note": "",
        })
        self.assertIsNotNone(self.lib._recoverable_status_integrity(status))
        return status

    def _graph_generation(self):
        graph = self.live._read("GRAPH_PATH")
        snapshot = self.lib._recoverable_graph_snapshot(graph)
        size, wire_sha256 = _wire(self.live.paths["GRAPH_PATH"])
        body = {
            "publication_id": snapshot["publication_id"],
            "raw_bytes": size,
            "raw_sha256": wire_sha256,
            "nodes": snapshot["nodes"],
            "edges": snapshot["edges"],
            "pages": snapshot["pages"],
            "complete": graph["snapshot"]["complete"],
        }
        return {**body, "generation_sha256": live_tests.digest(body)}

    def _status_generation(self):
        status = self.live._read("STATUS_PATH")
        size, wire_sha256 = _wire(self.live.paths["STATUS_PATH"])
        body = {
            "publication_id": status["publication_id"],
            "ts": status["ts"],
            "raw_bytes": size,
            "raw_sha256": wire_sha256,
            "semantic_sha256": live_tests.digest(status),
        }
        return {**body, "generation_sha256": live_tests.digest(body)}

    def _status_generation_for(self, status):
        # Live staging retains canonical sorted-key candidate bytes. The
        # publisher reopens that candidate before export_status preserves its
        # ordering, so this is the exact eventual status wire image.
        raw = json.dumps(
            status, sort_keys=True, allow_nan=False).encode("utf-8")
        body = {
            "publication_id": status["publication_id"],
            "ts": status["ts"],
            "raw_bytes": len(raw),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "semantic_sha256": live_tests.digest(status),
        }
        return {**body, "generation_sha256": live_tests.digest(body)}

    def _live_generation(self):
        generation = self.live._read("LIVE_STATE_PATH")
        _candidate_size, candidate_wire = _wire(
            self.live.paths["LIVE_CANDIDATE_PATH"])
        _generation_size, generation_wire = _wire(
            self.live.paths["LIVE_STATE_PATH"])
        return {
            "publication_id": generation["publication_id"],
            "candidate_sha256": generation["candidate_sha256"],
            "generation_sha256": generation["generation_sha256"],
            "status_sha256": generation["status_sha256"],
            "candidate_raw_sha256": candidate_wire,
            "generation_raw_sha256": generation_wire,
        }

    def _expected_pending(self):
        closure = self.batch["event_closure"]
        body = {
            "schema": "sia-controller-source-effects-pending-v1",
            "source_batch_sha256": self.batch["batch_sha256"],
            "source_batch_wire_sha256":
                self.binding["source_batch_wire_sha256"],
            "source_live_publication_sha256":
                self.binding["publication_sha256"],
            "event_closure_sha256": (
                None if closure is None else closure["closure_sha256"]),
            "closure_result_sha256": (
                None if closure is None else live_tests.digest(
                    _closure_result(closure))),
            "status_effects_sha256": live_tests.digest(self.handoff),
            "target_manifest": copy.deepcopy(self.target_manifest),
            "target_manifest_sha256": live_tests.digest(
                self.target_manifest),
            "corpus_generation": (
                None if closure is None
                else copy.deepcopy(self.corpus_generation)),
            "sync_generation": (
                None if closure is None
                else copy.deepcopy(self.sync_generation)),
            "graph_generation": self._graph_generation(),
            "status_generation": self._status_generation_for(
                self.expected_status),
            "status": copy.deepcopy(self.expected_status),
            "prepare_inputs_sha256":
                self.binding["prepare_inputs_sha256"],
            "state_sha256": self.binding["state_sha256"],
            "transition_sha256": self.binding["transition_sha256"],
            "non_claims": list(NON_CLAIMS),
        }
        return {**body, "pending_sha256": live_tests.digest(body)}

    def _expected_receipt(self):
        closure = self.batch["event_closure"]
        body = {
            "schema": "sia-controller-source-effects-committed-v1",
            "status": ("status-live-committed-no-closure"
                       if closure is None
                       else "closure-index-status-live-committed"),
            "source_batch_sha256": self.batch["batch_sha256"],
            "source_batch_wire_sha256":
                self.binding["source_batch_wire_sha256"],
            "source_live_publication_sha256":
                self.binding["publication_sha256"],
            "event_closure_sha256": (
                None if closure is None else closure["closure_sha256"]),
            "closure_result_sha256": (
                None if closure is None else live_tests.digest(
                    _closure_result(closure))),
            "status_effects_sha256": live_tests.digest(self.handoff),
            "target_manifest": copy.deepcopy(self.target_manifest),
            "target_manifest_sha256": live_tests.digest(
                self.target_manifest),
            "corpus_generation": (
                None if closure is None
                else copy.deepcopy(self.corpus_generation)),
            "sync_generation": (
                None if closure is None
                else copy.deepcopy(self.sync_generation)),
            "graph_generation": self._graph_generation(),
            "status_generation": self._status_generation(),
            "live_generation": self._live_generation(),
            "prepare_inputs_sha256":
                self.binding["prepare_inputs_sha256"],
            "state_sha256": self.binding["state_sha256"],
            "transition_sha256": self.binding["transition_sha256"],
            "non_claims": list(NON_CLAIMS),
        }
        return {**body, "receipt_sha256": live_tests.digest(body)}

    @contextlib.contextmanager
    def _forbid_ack_effects(self):
        def forbidden(name):
            return mock.Mock(side_effect=AssertionError(
                "source effects crossed into " + name))

        names = (
            "_capture_controller_source_batch",
            "_stage_controller_source_live_binding",
            "_stage_controller_source_status_effects",
            "_commit_sense_cursors", "save_cursors",
            "_discard_pending_cursor_renames", "_settle_source_refusals",
            "_settle_source_record_refusals",
            "_settle_source_entry_refusals",
            "_acknowledge_controller_source_batch",
            "_controller_source_ack_boundary",
        )
        with contextlib.ExitStack() as stack:
            for name in names:
                if hasattr(self.lib, name):
                    stack.enter_context(mock.patch.object(
                        self.lib, name, new=forbidden(name)))
            yield

    @contextlib.contextmanager
    def publication_effects(
            self, *, corpus_generation=None, sync_generation=None,
            target_manifest=None, null=False, crash_at=None,
            recovery=False, predecessor_live=None):
        trace = []
        pending_images = []
        selected_corpus = copy.deepcopy(
            self.corpus_generation if corpus_generation is None
            else corpus_generation)
        selected_sync = copy.deepcopy(
            self.sync_generation if sync_generation is None
            else sync_generation)
        selected_manifest = copy.deepcopy(
            self.target_manifest if target_manifest is None
            else target_manifest)
        # Patch the final lazy-module delegates, not the bootstrap wrappers
        # which the first live operation intentionally replaces.
        self.lib._load_live_publication()
        real_publish_closure = self.lib._publish_event_page_batch_closure
        real_stage_live = self.lib._stage_live_generation
        real_publish_live = self.lib._publish_staged_live_generation
        real_atomic = self.lib.atomic_write
        closure_results = []

        def publish_closure(*, closure, expected_closure_sha256):
            if recovery:
                raise AssertionError("recovery repeated closure publication")
            self.assertEqual(trace, [])
            result = real_publish_closure(
                closure=closure,
                expected_closure_sha256=expected_closure_sha256)
            closure_results.append(copy.deepcopy(result))
            trace.append("closure")
            return result

        def commit(*, source_batch_sha256, event_closure_sha256):
            if recovery:
                raise AssertionError("recovery repeated corpus commit")
            self.assertEqual(trace, ["closure"])
            self.assertEqual(source_batch_sha256,
                             self.batch["batch_sha256"])
            self.assertEqual(event_closure_sha256,
                             self.batch["event_closure"]["closure_sha256"])
            trace.append("corpus")
            return copy.deepcopy(selected_corpus)

        def sync(*, corpus_generation, target_versions):
            if recovery:
                raise AssertionError("recovery repeated engine sync")
            self.assertEqual(trace, ["closure", "corpus"])
            self.assertEqual(corpus_generation, selected_corpus)
            self.assertEqual(target_versions, self._target_versions())
            trace.append("sync")
            return {
                "sync_generation": copy.deepcopy(selected_sync),
                "target_manifest": copy.deepcopy(selected_manifest),
                "target_manifest_sha256": live_tests.digest(
                    selected_manifest),
            }

        def graph(*_args, **_kwargs):
            if recovery:
                raise AssertionError("recovery repeated graph publication")
            expected = [] if null else ["closure", "corpus", "sync"]
            self.assertEqual(trace, expected)
            self.fresh_graph = self._new_graph()
            real_atomic(
                self.live.paths["GRAPH_PATH"],
                json.dumps(self.fresh_graph), mode=0o600)
            self.expected_status = self._new_status(self.fresh_graph)
            trace.append("graph")
            snapshot = self.lib._recoverable_graph_snapshot(self.fresh_graph)
            return snapshot["nodes"], snapshot["edges"], snapshot["pages"]

        def status_clock():
            if recovery:
                raise AssertionError("recovery reobserved the status clock")
            self.assertEqual(trace[-1], "graph")
            return STATUS_AT

        def stage_live(*, memo, status, prepare_inputs,
                       expected_prepare_inputs_sha256):
            self.assertEqual(trace[-1] if trace else None,
                             None if recovery else "pending")
            self.assertEqual(status, self.expected_status)
            self.assertEqual(prepare_inputs, self.candidate["prepare_inputs"])
            self.assertEqual(
                expected_prepare_inputs_sha256,
                self.candidate["expected_prepare_inputs_sha256"])
            trace.append("live-stage")
            return real_stage_live(
                memo=memo, status=status, prepare_inputs=prepare_inputs,
                expected_prepare_inputs_sha256=
                    expected_prepare_inputs_sha256)

        def publish_live(*, memo):
            self.assertEqual(trace[-1], "live-stage")
            result = real_publish_live(memo=memo)
            self.committed_generation = copy.deepcopy(result)
            self.memo_after_live = copy.deepcopy(memo)
            trace.append("live-publish")
            return result

        def write(path, data, **kwargs):
            if str(path) == str(self.live.paths["MEMO_PATH"]):
                value = json.loads(data)
                if "controller_source_effects_pending" in value \
                        and "controller_source_effects_committed" not in value \
                        and "live_loop_pending" not in value \
                        and ("live_loop_committed" not in value
                             or predecessor_live is not None
                             and value["live_loop_committed"] == predecessor_live):
                    if predecessor_live is not None:
                        self.assertEqual(value["live_loop_committed"],
                                         predecessor_live)
                    self.assertEqual(trace[-1], "graph")
                    pending = value["controller_source_effects_pending"]
                    self.assertEqual(set(pending), PENDING_KEYS)
                    self.assertEqual(
                        pending["pending_sha256"], live_tests.digest({
                            key: item for key, item in pending.items()
                            if key != "pending_sha256"
                        }))
                    pending_images.append(copy.deepcopy(pending))
                    trace.append("pending")
                elif predecessor_live is not None \
                        and "controller_source_effects_pending" in value \
                        and "live_loop_pending" not in value:
                    self.assertEqual(trace[-1], "live-stage")
                    self.assertEqual(
                        value["live_loop_committed"]["publication_id"],
                        self.binding["publication_id"])
                    self.assertEqual(
                        value["live_loop_committed"]["transition_sha256"],
                        self.binding["transition_sha256"])
                if "controller_source_effects_committed" in value:
                    if recovery and "live_loop_committed" in self.live.memo \
                            and not trace:
                        pass
                    else:
                        self.assertEqual(trace[-1], "live-publish")
                    self.assertNotIn(
                        "controller_source_effects_pending", value)
                    trace.append("receipt")
            return real_atomic(path, data, **kwargs)

        def boundary(stage):
            self.assertIn(stage, ("effects-pending", "live-published"))
            if stage == crash_at:
                raise RuntimeError("injected source-effects crash: " + stage)

        with self._forbid_ack_effects(), \
                mock.patch.object(
                    self.lib, "_publish_event_page_batch_closure",
                    side_effect=publish_closure) as published, \
                mock.patch.object(
                    self.lib, COMMITTER, side_effect=commit,
                    create=True) as committed, \
                mock.patch.object(
                    self.lib, SYNCER, side_effect=sync,
                    create=True) as synced, \
                mock.patch.object(
                    self.lib, "_export_graph_publication",
                    side_effect=graph) as graphed, \
                mock.patch.object(
                    self.lib, CLOCK, side_effect=status_clock,
                    create=True) as clocked, \
                mock.patch.object(
                    self.lib, BOUNDARY, side_effect=boundary,
                    create=True) as bounded, \
                mock.patch.object(
                    self.lib, "_stage_live_generation",
                    side_effect=stage_live) as staged, \
                mock.patch.object(
                    self.lib, "_publish_staged_live_generation",
                    side_effect=publish_live) as live_published, \
                mock.patch.object(
                    self.lib, "corpus_commit",
                    side_effect=AssertionError(
                        "unstructured corpus commit result used")), \
                mock.patch.object(
                    self.lib, "brain_sync",
                    side_effect=AssertionError(
                        "unstructured gbrain sync result used")), \
                mock.patch.object(
                    self.lib, "atomic_write", side_effect=write):
            yield {
                "trace": trace, "closure_results": closure_results,
                "pending_images": pending_images,
                "published": published, "committed": committed,
                "synced": synced, "graphed": graphed,
                "clocked": clocked, "bounded": bounded,
                "staged": staged, "live_published": live_published,
            }

    @contextlib.contextmanager
    def no_effect_boundary(self):
        def forbidden(*_args, **_kwargs):
            raise AssertionError(
                "refused or completed source-effects call attempted an effect")

        with self._forbid_ack_effects(), contextlib.ExitStack() as stack:
            for name in (
                    "_publish_event_page_batch_closure", COMMITTER, SYNCER,
                    BOUNDARY,
                    "export_graph", "_export_graph_publication",
                    "_stage_live_generation",
                    "_publish_staged_live_generation", "export_status",
                    "atomic_write", "_write_memo", CLOCK, "corpus_commit",
                    "brain_sync"):
                stack.enter_context(mock.patch.object(
                    self.lib, name, side_effect=forbidden, create=True))
            yield

    def _assert_pages(self):
        for batch in self.batch["event_closure"]["batches"]:
            for plan in batch["members"]:
                for page in plan["pages"]:
                    path = Path(self.source.lib.corpus_path(page["slug"]))
                    self.assertEqual(
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                        page["raw_sha256"])

    def _assert_receipt(self, expected):
        durable = self.live._read("MEMO_PATH")
        self.assertEqual(durable, self.live.memo)
        final = copy.deepcopy(self.memo_after_live)
        final.pop("controller_source_effects_pending")
        final["controller_source_effects_committed"] = expected
        self.assertEqual(durable, final)
        receipt = durable["controller_source_effects_committed"]
        self.assertEqual(set(receipt), RECEIPT_KEYS)
        self.assertEqual(receipt, expected)
        self.assertEqual(set(receipt["graph_generation"]), GRAPH_KEYS)
        self.assertEqual(set(receipt["status_generation"]), STATUS_KEYS)
        self.assertEqual(set(receipt["live_generation"]), LIVE_KEYS)
        self.assertEqual(receipt["graph_generation"]["generation_sha256"],
                         _own(receipt["graph_generation"]))
        self.assertEqual(receipt["status_generation"]["generation_sha256"],
                         _own(receipt["status_generation"]))
        self.assertNotIn("pulse_status_effects_pending", durable)
        self.assertNotIn("controller_source_effects_pending", durable)
        self.assertIn("controller_source_live_pending", durable)
        self.assertIn("live_loop_committed", durable)
        self.assertNotIn("ready", durable)

    def test_exact_keyword_only_api_and_nonclaims(self):
        parameters = inspect.signature(self.publisher()).parameters
        self.assertEqual(tuple(parameters), ("memo", "admitted_status"))
        for parameter in parameters.values():
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)
        self.assertEqual(
            tuple(getattr(self.lib, NON_CLAIMS_NAME, ())), NON_CLAIMS)

    def test_legacy_public_graph_is_resealed_in_place_only_by_explicit_lane(self):
        module = importlib.import_module("siasourceeffects")
        source = importlib.import_module("siasourcebatch")
        path = Path(self.live.paths["GRAPH_PATH"])
        original = path.read_bytes()
        path.chmod(0o644)
        before = path.stat()

        raw, value = module._held_json(
            self.lib.__dict__, source, str(path),
            self.lib.MAX_STATE_JSON_BYTES, seal_legacy_public=True)

        after = path.stat()
        self.assertEqual(raw, original)
        self.assertEqual(value, json.loads(original))
        self.assertEqual((after.st_dev, after.st_ino),
                         (before.st_dev, before.st_ino))
        self.assertEqual(stat.S_IMODE(after.st_mode), 0o600)

        path.chmod(0o644)
        with self.assertRaises(REFUSALS):
            module._held_json(
                self.lib.__dict__, source, str(path),
                self.lib.MAX_STATE_JSON_BYTES)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

        path.chmod(0o640)
        with self.assertRaises(REFUSALS):
            module._held_json(
                self.lib.__dict__, source, str(path),
                self.lib.MAX_STATE_JSON_BYTES, seal_legacy_public=True)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)

    def test_legacy_public_status_is_resealed_before_live_publication(self):
        self.start()
        path = Path(self.live.paths["STATUS_PATH"])
        original = path.read_bytes()
        before = path.stat()
        path.chmod(0o644)

        with self.publication_effects():
            self.assertIsNone(self.publisher()(
                memo=self.live.memo,
                admitted_status=self.admitted_status))

        after = path.stat()
        self.assertEqual(path.read_bytes(), json.dumps(
            self.expected_status, sort_keys=True, allow_nan=False).encode())
        self.assertNotEqual(path.read_bytes(), original)
        self.assertNotEqual((after.st_dev, after.st_ino),
                            (before.st_dev, before.st_ino))
        self.assertEqual(stat.S_IMODE(after.st_mode), 0o600)

    def test_nonempty_full_order_and_exact_bound_receipt(self):
        self.start()
        with self.publication_effects() as observed:
            self.assertIsNone(self.publisher()(
                memo=self.live.memo,
                admitted_status=self.admitted_status))

        self.assertEqual(observed["trace"], [
            "closure", "corpus", "sync", "graph",
            "pending", "live-stage", "live-publish", "receipt"])
        observed["published"].assert_called_once_with(
            closure=self.batch["event_closure"],
            expected_closure_sha256=
                self.batch["event_closure"]["closure_sha256"])
        observed["committed"].assert_called_once_with(
            source_batch_sha256=self.batch["batch_sha256"],
            event_closure_sha256=
                self.batch["event_closure"]["closure_sha256"])
        observed["synced"].assert_called_once_with(
            corpus_generation=self.corpus_generation,
            target_versions=self._target_versions())
        observed["graphed"].assert_called_once_with()
        observed["clocked"].assert_called_once_with()
        self.assertEqual(observed["pending_images"], [
            self._expected_pending()])
        self.assertEqual(
            [call.args for call in observed["bounded"].call_args_list],
            [("effects-pending",), ("live-published",)])
        self.assertEqual(observed["closure_results"], [
            _closure_result(self.batch["event_closure"])])
        self._assert_pages()
        expected = self._expected_receipt()
        self._assert_receipt(expected)
        self.assertEqual(set(expected["corpus_generation"]), CORPUS_KEYS)
        self.assertEqual(set(expected["sync_generation"]), SYNC_KEYS)
        self.assertEqual(expected["corpus_generation"]["generation_sha256"],
                         _own(expected["corpus_generation"]))
        self.assertEqual(expected["sync_generation"]["generation_sha256"],
                         _own(expected["sync_generation"]))
        self.assertEqual(
            expected["sync_generation"]["sync_requested_commit"],
            expected["corpus_generation"]["corpus_commit_oid"])
        self.assertEqual(
            expected["sync_generation"]["status_last_commit"],
            expected["corpus_generation"]["corpus_commit_oid"])
        self.assertEqual(
            expected["target_manifest_sha256"],
            expected["sync_generation"]["index_manifest_sha256"])
        for row in expected["target_manifest"]:
            self.assertEqual(set(row), TARGET_KEYS)
            self.assertEqual(row["page_state"], "live")
            self.assertEqual(row["parse_error_codes"], [])
            self.assertEqual(row["expected_projection_sha256"],
                             row["current_projection_sha256"])
            self.assertEqual(row["expected_projection_sha256"],
                             row["current_content_hash"])
            self.assertIs(row["current_content_hash_match"], True)
            self.assertIs(row["projection_match"], True)

    def test_exact_completed_retry_is_effect_and_write_free(self):
        self.start()
        with self.publication_effects():
            self.assertIsNone(self.publisher()(
                memo=self.live.memo,
                admitted_status=self.admitted_status))
        before = self._images()
        corpus_before = self.source.pages.snapshot()
        current_status = self.live._read("STATUS_PATH")

        with self.no_effect_boundary():
            self.assertIsNone(self.publisher()(
                memo=self.live.memo, admitted_status=current_status))

        self.assertEqual(self._images(), before)
        self.assertEqual(self.source.pages.snapshot(), corpus_before)

    def test_null_closure_skips_git_and_sync_but_commits_status_live_receipt(self):
        self.start(empty=True)
        self.assertIsNone(self.batch["event_closure"])
        with self.publication_effects(null=True) as observed:
            self.assertIsNone(self.publisher()(
                memo=self.live.memo,
                admitted_status=self.admitted_status))

        self.assertEqual(observed["trace"], [
            "graph", "pending", "live-stage", "live-publish", "receipt"])
        observed["published"].assert_not_called()
        observed["committed"].assert_not_called()
        observed["synced"].assert_not_called()
        observed["clocked"].assert_called_once_with()
        self.assertEqual(observed["pending_images"], [
            self._expected_pending()])
        expected = self._expected_receipt()
        self._assert_receipt(expected)
        self.assertEqual(expected["target_manifest"], [])
        self.assertIsNone(expected["corpus_generation"])
        self.assertIsNone(expected["sync_generation"])

    def test_overlay_bound_v3_sync_generation_is_admitted_without_relabeling_v2(self):
        self.start()
        v3 = copy.deepcopy(self.sync_generation)
        v3["schema"] = "sia-controller-source-sync-generation-v3"
        v3["gbrain_overlay_sha256"] = "6" * 64
        v3["gbrain_overlay_tree_oid"] = "7" * 40
        v3["generation_sha256"] = live_tests.digest({
            key: value for key, value in v3.items()
            if key != "generation_sha256"})
        with self.publication_effects(sync_generation=v3):
            self.assertIsNone(self.publisher()(
                memo=self.live.memo,
                admitted_status=self.admitted_status))
        receipt = self.live.memo["controller_source_effects_committed"]
        self.assertEqual(receipt["sync_generation"], v3)
        self.assertEqual(receipt["sync_generation"]["schema"],
                         "sia-controller-source-sync-generation-v3")

    def test_explicit_embedding_v4_generation_is_admitted_without_relabeling_history(self):
        self.start()
        v4 = copy.deepcopy(self.sync_generation)
        v4["schema"] = "sia-controller-source-sync-generation-v4"
        v4["gbrain_overlay_sha256"] = "6" * 64
        v4["gbrain_overlay_tree_oid"] = "7" * 40
        v4["embed_raw_sha256"] = "8" * 64
        v4["embed_stderr_sha256"] = "9" * 64
        v4["generation_sha256"] = live_tests.digest({
            key: value for key, value in v4.items()
            if key != "generation_sha256"})
        with self.publication_effects(sync_generation=v4):
            self.assertIsNone(self.publisher()(
                memo=self.live.memo,
                admitted_status=self.admitted_status))
        receipt = self.live.memo["controller_source_effects_committed"]
        self.assertEqual(receipt["sync_generation"], v4)
        self.assertEqual(receipt["sync_generation"]["schema"],
                         "sia-controller-source-sync-generation-v4")

    def test_retained_status_handoff_recovers_an_individually_valid_graph_ahead(self):
        self.start()
        graph_ahead = self.live._read("GRAPH_PATH")
        graph_ahead["publication_id"] = "4" * 32
        graph_ahead["ts"] = GRAPH_AT
        self.assertIsNotNone(
            self.lib._recoverable_graph_snapshot(graph_ahead))
        self.lib.atomic_write(
            self.live.paths["GRAPH_PATH"], json.dumps(graph_ahead),
            mode=0o600)
        with mock.patch.object(
                self.lib, "_live_graph_status",
                wraps=self.lib._live_graph_status) as joined, \
                self.publication_effects() as observed:
            self.assertIsNone(self.publisher()(
                memo=self.live.memo,
                admitted_status=self.admitted_status))
        self.assertGreaterEqual(joined.call_count, 2)
        self.assertEqual(observed["trace"], [
            "closure", "corpus", "sync", "graph", "pending",
            "live-stage", "live-publish", "receipt"])

    def test_projected_status_retains_unresolved_errors_as_degraded(self):
        self.start()
        admitted = copy.deepcopy(self.admitted_status)
        admitted["errors"] = {
            "fixture": "retained unresolved failure"}
        admitted["state"] = "degraded"
        graph = self.live._read("GRAPH_PATH")
        module = importlib.import_module("siasourceeffects")
        source = importlib.import_module("siasourcebatch")
        live = importlib.import_module("sialiveloop")
        projected = module._project_status(
            self.lib.__dict__, source, live,
            admitted, self.binding, self.handoff, self.transition, graph,
            self.live.memo["pulse_history"], STATUS_AT)
        self.assertEqual(projected["errors"], {
            "fixture": "retained unresolved failure"})
        self.assertEqual(projected["state"], "degraded")
        self.assertIsNotNone(
            self.lib._recoverable_status_integrity(projected))

    def test_each_durable_crash_prefix_recovers_without_repeating_effects(self):
        for crash_at in ("effects-pending", "live-published"):
            with self.subTest(crash_at=crash_at), self.fresh() as case:
                case.start()
                with case.publication_effects(
                        crash_at=crash_at) as first, \
                        self.assertRaisesRegex(
                            RuntimeError,
                            "injected source-effects crash: " + crash_at):
                    case.publisher()(
                        memo=case.live.memo,
                        admitted_status=case.admitted_status)

                durable = case.live._read("MEMO_PATH")
                self.assertIn("controller_source_effects_pending", durable)
                self.assertNotIn(
                    "controller_source_effects_committed", durable)
                self.assertEqual(
                    durable["controller_source_effects_pending"],
                    case._expected_pending())
                pending_image = copy.deepcopy(
                    durable["controller_source_effects_pending"])
                if crash_at == "effects-pending":
                    self.assertNotIn("live_loop_committed", durable)
                    self.assertEqual(first["trace"], [
                        "closure", "corpus", "sync", "graph", "pending"])
                    retry_status = case.admitted_status
                else:
                    self.assertIn("live_loop_committed", durable)
                    self.assertEqual(first["trace"], [
                        "closure", "corpus", "sync", "graph", "pending",
                        "live-stage", "live-publish"])
                    retry_status = case.live._read("STATUS_PATH")

                with case.publication_effects(recovery=True) as recovered:
                    self.assertIsNone(case.publisher()(
                        memo=case.live.memo,
                        admitted_status=retry_status))

                self.assertEqual(
                    recovered["trace"],
                    ["live-stage", "live-publish", "receipt"]
                    if crash_at == "effects-pending" else ["receipt"])
                recovered["published"].assert_not_called()
                recovered["committed"].assert_not_called()
                recovered["synced"].assert_not_called()
                recovered["graphed"].assert_not_called()
                recovered["clocked"].assert_not_called()
                expected = case._expected_receipt()
                case._assert_receipt(expected)
                for key in (
                        "source_batch_sha256", "source_batch_wire_sha256",
                        "source_live_publication_sha256",
                        "event_closure_sha256", "closure_result_sha256",
                        "status_effects_sha256", "target_manifest",
                        "target_manifest_sha256", "corpus_generation",
                        "sync_generation", "graph_generation",
                        "status_generation", "prepare_inputs_sha256",
                        "state_sha256", "transition_sha256", "non_claims"):
                    self.assertEqual(expected[key], pending_image[key], key)

    def test_pending_recovery_reseals_legacy_public_status(self):
        self.start()
        with self.publication_effects(crash_at="effects-pending"), \
                self.assertRaisesRegex(
                    RuntimeError,
                    "injected source-effects crash: effects-pending"):
            self.publisher()(
                memo=self.live.memo,
                admitted_status=self.admitted_status)

        path = Path(self.live.paths["STATUS_PATH"])
        path.chmod(0o644)
        with self.publication_effects(recovery=True):
            self.assertIsNone(self.publisher()(
                memo=self.live.memo,
                admitted_status=self.admitted_status))

        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self._assert_receipt(self._expected_receipt())

    def test_changed_authority_refuses_before_first_effect(self):
        cases = (
            "caller-memo", "resident-memo", "caller-status", "status",
            "graph", "source", "binding", "status-effects",
        )
        for selected in cases:
            with self.subTest(case=selected), self.fresh() as case:
                case.start()
                supplied_memo = case.live.memo
                supplied_status = case.admitted_status
                if selected == "caller-memo":
                    supplied_memo = copy.deepcopy(case.live.memo)
                    supplied_memo["foreign"] = True
                elif selected == "resident-memo":
                    changed = copy.deepcopy(case.live.memo)
                    changed["foreign"] = True
                    case.live._write(case.live.paths["MEMO_PATH"], changed)
                elif selected == "caller-status":
                    supplied_status = copy.deepcopy(case.admitted_status)
                    supplied_status["sync_note"] = "changed caller status"
                elif selected == "status":
                    changed = copy.deepcopy(case.admitted_status)
                    changed["sync_note"] = "changed resident status"
                    case.live._write(case.live.paths["STATUS_PATH"], changed)
                elif selected == "graph":
                    graph = case.live._read("GRAPH_PATH")
                    graph["publication_id"] = "0" * 32
                    case.live._write(case.live.paths["GRAPH_PATH"], graph)
                elif selected == "source":
                    path = Path(case.producer.source_path)
                    path.write_bytes(path.read_bytes() + b" ")
                elif selected == "binding":
                    changed = copy.deepcopy(case.live.memo)
                    changed["controller_source_live_pending"][
                        "marker_sha256"] = "0" * 64
                    case.live._write(case.live.paths["MEMO_PATH"], changed)
                    case.live.memo.clear()
                    case.live.memo.update(changed)
                else:
                    changed = copy.deepcopy(case.live.memo)
                    changed["pulse_status_effects_pending"]["effects"][
                        "events_pulse"] += 1
                    case.live._write(case.live.paths["MEMO_PATH"], changed)
                    case.live.memo.clear()
                    case.live.memo.update(changed)

                before = case._images()
                corpus_before = case.source.pages.snapshot()
                with case.no_effect_boundary(), \
                        self.assertRaises(REFUSALS):
                    case.publisher()(
                        memo=supplied_memo,
                        admitted_status=supplied_status)
                self.assertEqual(case._images(), before)
                self.assertEqual(case.source.pages.snapshot(), corpus_before)

    def test_commit_sync_wrong_body_or_same_count_wrong_target_refuses(self):
        cases = ("commit", "sync", "wrong-body", "wrong-target")
        for selected in cases:
            with self.subTest(case=selected), self.fresh() as case:
                case.start()
                corpus = case.corpus_generation
                sync = case.sync_generation
                manifest = case.target_manifest
                if selected == "commit":
                    corpus = case._corpus_generation(clean=False)
                elif selected == "sync":
                    sync = case._sync_generation(
                        manifest, status_last_commit="9" * 40)
                elif selected == "wrong-body":
                    manifest = copy.deepcopy(manifest)
                    manifest[0]["current_projection_sha256"] = "8" * 64
                    sync = case._sync_generation(manifest)
                else:
                    manifest = copy.deepcopy(manifest)
                    manifest[0]["slug"] += "-foreign"
                    sync = case._sync_generation(manifest)
                before = case._images()

                with case.publication_effects(
                        corpus_generation=corpus,
                        sync_generation=sync,
                        target_manifest=manifest) as observed, \
                        self.assertRaises(REFUSALS):
                    case.publisher()(
                        memo=case.live.memo,
                        admitted_status=case.admitted_status)

                self.assertEqual(observed["trace"], (
                    ["closure", "corpus"] if selected == "commit"
                    else ["closure", "corpus", "sync"]))
                durable = case.live._read("MEMO_PATH")
                self.assertEqual(durable, case.live.memo)
                self.assertNotIn(
                    "controller_source_effects_committed", durable)
                self.assertNotIn("live_loop_committed", durable)
                self.assertIn("pulse_status_effects_pending", durable)
                after = case._images()
                for name in before:
                    if name != "memo":
                        self.assertEqual(after[name], before[name], name)


if __name__ == "__main__":
    unittest.main()
