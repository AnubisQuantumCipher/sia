"""Receipt-bound gbrain sync and exact page-projection generation.

The fixture supplies controlled command observations while exercising the real
file, receipt, descriptor and request-manifest boundary.  A separate pinned
gbrain integration lane proves the engine's parsers and database behavior.
"""

import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

import sialib


API = "_controller_source_sync_generation"
BATCH_SHA256 = "8" * 64
CLOSURE_SHA256 = "9" * 64
COMMIT = "a" * 40
VERSION = "0.47.6.0"
PINNED_COMMIT = "7b7921d86141c4e4086e50828de9a867a6814247"
LOCK_SHA256 = "d9f9ac4f848d7e3c8a92be4ede6e82285aa5677dcd3844aa600fc714ddf6d1cc"
OVERLAY_SHA256 = "beb2dfbeacee51d321cab9f78d05ca514c6db40e7039c9d8b4e592a16a8bfc0a"
OVERLAY_TREE_OID = "c6074727cb43987953279460f9502708dd5d1bd8"
TARGET_KEYS = {
    "slug", "source_sha256", "version_sha256", "page_state",
    "parse_error_codes", "expected_projection_sha256",
    "current_projection_sha256", "current_content_hash",
    "current_content_hash_match", "projection_match",
}
GENERATION_KEYS = {
    "schema", "source_id", "engine_version", "gbrain_commit",
    "gbrain_bun_lock_sha256", "gbrain_overlay_sha256",
    "gbrain_overlay_tree_oid", "gbrain_pin_sha256",
    "gbrain_pin_receipt_sha256", "gbrain_release_receipt_sha256",
    "gbrain_executable_sha256", "version_raw_sha256",
    "sync_raw_sha256", "sync_stderr_sha256", "sync_result_sha256",
    "sync_status", "sync_requested_commit", "links_raw_sha256",
    "embed_raw_sha256", "embed_stderr_sha256",
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
REFUSALS = (RuntimeError, ValueError, OSError)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _wire(value):
    return json.dumps(value, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False) + "\n"


class ControllerSourceEngineGeneration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.share = self.root / "share"
        self.state = self.root / "state"
        self.corpus = self.share / "corpus"
        self.toolchain = self.share / "toolchain"
        self.engine_root = self.toolchain / "gbrain"
        self.engine_bin = self.engine_root / "bin/gbrain"
        self.release_receipt = self.engine_root / ".sia-release"
        self.pin = self.share / "GBRAIN_PIN"
        self.managed = self.state / "managed-install"
        self.pin_receipt = self.managed / "gbrain-pin"
        self.corpus.mkdir(parents=True)
        self.engine_bin.parent.mkdir(parents=True)
        self.managed.mkdir(parents=True)
        shutil.copyfile("/usr/bin/true", self.engine_bin)
        self.engine_bin.chmod(0o755)
        self.binary_sha256 = hashlib.sha256(
            self.engine_bin.read_bytes()).hexdigest()
        self.pin.write_text(
            "# fixture pin\n"
            f"commit={PINNED_COMMIT}\n"
            f"version={VERSION}\n"
            f"bun_lock_sha256={LOCK_SHA256}\n"
            f"overlay_sha256={OVERLAY_SHA256}\n"
            f"overlay_tree_oid={OVERLAY_TREE_OID}\n"
            "verified=2026-08-30\n", encoding="utf-8")
        self.pin_sha256 = hashlib.sha256(self.pin.read_bytes()).hexdigest()
        self.pin_receipt.write_text(
            "managed-by=khephri.sia\n"
            "kind=gbrain-pin\n"
            f"path={self.pin}\n"
            f"sha256={self.pin_sha256}\n", encoding="utf-8")
        self.release_receipt.write_text(
            "managed-by=khephri.sia\n"
            f"commit={PINNED_COMMIT}\n"
            f"version={VERSION}\n"
            f"bun_lock_sha256={LOCK_SHA256}\n"
            f"overlay_sha256={OVERLAY_SHA256}\n"
            f"overlay_tree_oid={OVERLAY_TREE_OID}\n"
            f"binary_sha256={self.binary_sha256}\n", encoding="utf-8")
        self.slug = "events/2026-09-06"
        self.raw = (
            "---\ntype: event\ntags: [event, system]\n---\n"
            "# Event\n\n- 2026-09-06T12:00:00Z — retained fact\n")
        page = self.corpus / (self.slug + ".md")
        page.parent.mkdir(parents=True)
        page.write_text(self.raw, encoding="utf-8")
        self.source_sha256 = hashlib.sha256(
            self.raw.encode("utf-8")).hexdigest()
        self.target_versions = [{
            "slug": self.slug,
            "source_sha256": self.source_sha256,
            "version_sha256": "b" * 64,
        }]
        body = {
            "schema": "sia-controller-source-corpus-generation-v1",
            "object_format": "sha1",
            "git_executable_sha256": "c" * 64,
            "before_commit_oid": "e" * 40,
            "corpus_commit_oid": COMMIT,
            "corpus_tree_oid": "f" * 40,
            "clean": True,
        }
        self.corpus_generation = {
            **body, "generation_sha256": _digest(body)}
        self.projection_sha256 = "4" * 64
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in (
                ("HOME", str(self.root)),
                ("SHARE", str(self.share)),
                ("STATE", str(self.state)),
                ("CORPUS", str(self.corpus)),
                ("TOOLCHAIN", str(self.toolchain)),
                ("BUN_DIR", str(self.toolchain / "bun/bin")),
                ("GBRAIN", str(self.engine_bin)),
                ("GBRAIN_PIN", str(self.pin)),
                ("GBRAIN_PIN_RECEIPT", str(self.pin_receipt)),
                ("GBRAIN_RUNTIME_RECEIPT", str(self.release_receipt)),
                ("GBRAIN_SOURCE", "sia"),
                ("GBRAIN_OWNER_LOCK", str(self.state / "gbrain-owner.lock")),
                ("CORPUS_OWNER_LOCK", str(self.state / "corpus-owner.lock")),
                ("LIFECYCLE_LOCK", str(self.state / "lifecycle.lock")),
                ("LIFECYCLE_TOMBSTONE", str(self.state / "lifecycle-removed")),
                ("RESTORE_BARRIER_PATH", str(self.state / "restore.json")),
                ("RESTORE_MASK_PATH", str(self.state / "restore-mask")),
                ("RESTORE_SUPERVISOR_PATH", str(self.state / "restore-supervisor.json"))):
            self.stack.enter_context(mock.patch.object(
                sialib, name, value, create=True))
        self.calls = []
        self.request_paths = []

    def helper(self):
        value = getattr(sialib, API, None)
        self.assertTrue(callable(value), "missing engine generation API: " + API)
        return value

    def _status_source(self, **changes):
        row = {
            "source_id": "sia", "name": "SIA",
            "local_path": str(self.corpus), "sync_enabled": True,
            "last_sync_at": "2026-09-06T12:00:01.000Z",
            "hours_since_last_sync": 0, "staleness_hours": 0,
            "staleness_class": "fresh", "last_commit": COMMIT,
            "pages": 1, "chunks_total": 1, "chunks_unembedded": 0,
            "embedding_coverage_pct": 100, "backfill_queued": 0,
            "backfill_active": 0, "backfill_last_completed_at": None,
        }
        row.update(changes)
        return row

    def _outputs(self):
        return {
            "version": (f"gbrain {VERSION}\n", ""),
            "sync": (_wire({
                "schema_version": 1, "source_id": "sia",
                "sync_status": "synced", "added": 1, "modified": 0,
                "deleted": 0, "chunks_created": 1, "embedded": 0,
            }), "sync progress\n"),
            "embed": ("Embedded 1 chunks across 1 pages\n", ""),
            "links": (_wire({
                "action": "extract_stale_done", "links_created": 1,
                "timeline_created": 1, "pages_processed": 1,
                "stale_remaining": 0, "budget_hit": False,
                "skipped_missing_target": 0, "skipped_cross_source": 0,
            }), ""),
            "mentions": (_wire({
                "links_created": 0, "timeline_entries_created": 0,
                "pages_processed": 1,
            }), ""),
            "status": (_wire({
                "schema_version": 1, "version": VERSION,
                "generated_at": "2026-09-06T12:00:02.000Z", "mode": "local",
                "sync": {
                    "schema_version": 1,
                    "generated_at": "2026-09-06T12:00:02.000Z",
                    "sources": [self._status_source()],
                    "unacknowledged_failures": 0,
                    "embedding_column": "embedding",
                },
            }), ""),
            "projection": (_wire({
                "schema_version": 1, "source_id": "sia", "target_count": 1,
                "retrieval_bookkeeping_updated": False,
                "operation_writes_performed": False, "all_match": True,
                "targets": [{
                    "slug": self.slug, "page_state": "live",
                    "parse_error_codes": [],
                    "expected_projection_sha256": self.projection_sha256,
                    "current_projection_sha256": self.projection_sha256,
                    "current_content_hash": self.projection_sha256,
                    "current_content_hash_match": True,
                    "projection_match": True,
                }],
            }), ""),
        }

    def _runner(self, outputs=None, *, replace=None):
        outputs = copy.deepcopy(self._outputs() if outputs is None else outputs)

        def run(command, **kwargs):
            self.assertTrue(command[0].startswith("/proc/self/fd/"))
            self.assertTrue(str(kwargs["cwd"]).startswith("/proc/self/fd/"))
            descriptors = tuple(kwargs.get("pass_fds", ()))
            self.assertGreaterEqual(len(descriptors), 2)
            for descriptor in descriptors:
                os.fstat(descriptor)
            args = tuple(command[1:])
            if args == ("--version",):
                name = "version"
            elif args == (
                    "sync", "--source", "sia", "--json", "--no-pull",
                    "--no-delegate", "--no-embed", "--no-extract"):
                name = "sync"
            elif args == (
                    "embed", "--stale", "--source", "sia", "--catch-up"):
                name = "embed"
            elif args == (
                    "extract", "links", "--source", "db", "--stale",
                    "--source-id", "sia", "--json"):
                name = "links"
            elif args == (
                    "extract", "links", "--by-mention", "--ner",
                    "--source", "db", "--source-id", "sia", "--json"):
                name = "mentions"
            elif args == ("status", "--section", "sync", "--json"):
                name = "status"
            elif len(args) == 7 and args[:4] == (
                    "call", "--no-migrate", "--source", "sia") \
                    and args[4] == "--params-file" \
                    and args[6] == "get_page_projection":
                name = "projection"
                request_path = Path(args[5])
                self.request_paths.append(str(request_path))
                request = json.loads(request_path.read_text(encoding="utf-8"))
                self.assertEqual(request, {
                    "source_id": "sia",
                    "targets": [{"slug": self.slug,
                                 "raw_markdown": self.raw}],
                })
            else:
                raise AssertionError("unexpected engine command: " + repr(args))
            self.calls.append(name)
            if replace is not None:
                replace(name)
            stdout, stderr = outputs[name]
            return subprocess.CompletedProcess(
                command, 0, stdout=stdout, stderr=stderr)

        return run

    def _call(self):
        return self.helper()(
            corpus_generation=copy.deepcopy(self.corpus_generation),
            target_versions=copy.deepcopy(self.target_versions))

    def test_generation_binds_receipts_descriptors_and_exact_projection_roster(self):
        outputs = self._outputs()
        with mock.patch.object(
                sialib, "_run_bounded_text_process",
                side_effect=self._runner(outputs)):
            result = self._call()

        self.assertEqual(self.calls, [
            "version", "sync", "embed", "links", "mentions", "status",
            "projection"])
        self.assertEqual(set(result), {"sync_generation", "target_manifest",
                                       "target_manifest_sha256"})
        generation = result["sync_generation"]
        self.assertEqual(
            generation["schema"], "sia-controller-source-sync-generation-v4")
        manifest = result["target_manifest"]
        self.assertEqual(set(generation), GENERATION_KEYS)
        self.assertEqual(len(manifest), 1)
        self.assertEqual(set(manifest[0]), TARGET_KEYS)
        self.assertEqual(manifest[0], {
            "slug": self.slug, "source_sha256": self.source_sha256,
            "version_sha256": "b" * 64, "page_state": "live",
            "parse_error_codes": [],
            "expected_projection_sha256": self.projection_sha256,
            "current_projection_sha256": self.projection_sha256,
            "current_content_hash": self.projection_sha256,
            "current_content_hash_match": True, "projection_match": True,
        })
        self.assertEqual(result["target_manifest_sha256"], _digest(manifest))
        self.assertEqual(generation["index_manifest_sha256"], _digest(manifest))
        self.assertEqual(generation["gbrain_executable_sha256"],
                         self.binary_sha256)
        self.assertEqual(generation["gbrain_commit"], PINNED_COMMIT)
        self.assertEqual(generation["gbrain_bun_lock_sha256"], LOCK_SHA256)
        self.assertEqual(generation["gbrain_overlay_sha256"], OVERLAY_SHA256)
        self.assertEqual(
            generation["gbrain_overlay_tree_oid"], OVERLAY_TREE_OID)
        self.assertEqual(generation["gbrain_pin_sha256"], self.pin_sha256)
        self.assertEqual(generation["gbrain_pin_receipt_sha256"],
                         hashlib.sha256(self.pin_receipt.read_bytes()).hexdigest())
        self.assertEqual(generation["gbrain_release_receipt_sha256"],
                         hashlib.sha256(self.release_receipt.read_bytes()).hexdigest())
        self.assertEqual(generation["sync_requested_commit"], COMMIT)
        self.assertEqual(generation["status_last_commit"], COMMIT)
        self.assertEqual(generation["chunks_unembedded"], 0)
        self.assertEqual(generation["links_stale_remaining"], 0)
        self.assertIs(generation["projection_retrieval_bookkeeping_updated"],
                      False)
        self.assertIs(generation["projection_operation_writes_performed"],
                      False)
        self.assertEqual(generation["generation_sha256"], _digest({
            key: item for key, item in generation.items()
            if key != "generation_sha256"
        }))
        self.assertEqual(generation["sync_raw_sha256"], hashlib.sha256(
            outputs["sync"][0].encode("utf-8")).hexdigest())
        self.assertEqual(generation["sync_stderr_sha256"], hashlib.sha256(
            outputs["sync"][1].encode("utf-8")).hexdigest())
        self.assertEqual(generation["embed_raw_sha256"], hashlib.sha256(
            outputs["embed"][0].encode("utf-8")).hexdigest())
        self.assertEqual(generation["embed_stderr_sha256"], hashlib.sha256(
            outputs["embed"][1].encode("utf-8")).hexdigest())
        self.assertTrue(self.request_paths)
        self.assertTrue(all(not os.path.exists(path)
                            for path in self.request_paths))

    def test_engine_process_environment_is_closed_and_descriptor_bound(self):
        poison = {
            "DATABASE_URL": "postgresql://live.example/production",
            "GBRAIN_DATABASE_URL": "postgresql://live.example/brain",
            "GBRAIN_BRAIN_ID": "foreign-brain",
            "GBRAIN_MOUNTS_PATH": "/tmp/foreign-mounts.json",
            "GBRAIN_GUARDRAILS_MODULE": "/tmp/foreign-guardrail.mjs",
            "NODE_OPTIONS": "--require=/tmp/foreign-preload.cjs",
            "BUN_PRELOAD": "/tmp/foreign-preload.ts",
            "OPENAI_API_KEY": "ambient-provider-secret",
            "HTTPS_PROXY": "http://ambient-proxy.invalid",
        }
        expected = {
            "HOME": str(self.root),
            "GBRAIN_HOME": str(self.share),
            "PATH": str(self.toolchain / "bun/bin") + ":" + os.defpath,
            "TMPDIR": str(self.state),
            "BUN_OPTIONS": "--no-env-file",
            "DO_NOT_TRACK": "1",
            "NO_COLOR": "1",
            "GBRAIN_SKIP_STARTUP_HOOKS": "1",
            "GBRAIN_SYNC_NO_DELEGATE": "1",
            "GBRAIN_NO_BANNER": "1",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
            "XDG_CONFIG_HOME": str(self.root / ".config"),
            "XDG_DATA_HOME": str(self.root / ".local/share"),
            "XDG_CACHE_HOME": str(self.root / ".cache"),
            "XDG_STATE_HOME": str(self.root / ".local/state"),
        }
        observed = []
        runner = self._runner()

        def inspect_environment(command, **kwargs):
            observed.append(dict(kwargs["env"]))
            return runner(command, **kwargs)

        with mock.patch.object(sialib, "GBRAIN_ENV", poison), \
                mock.patch.dict(os.environ, poison, clear=False), \
                mock.patch.object(
                    sialib, "_run_bounded_text_process",
                    side_effect=inspect_environment):
            self._call()

        self.assertEqual(len(observed), len(self.calls))
        self.assertTrue(observed)
        self.assertTrue(all(environment == expected
                            for environment in observed))

    def test_receipt_or_executable_drift_refuses_before_any_process(self):
        for selected in (
                "pin-receipt", "runtime-receipt", "runtime-overlay",
                "executable"):
            with self.subTest(selected=selected):
                with self.fresh() as case:
                    if selected == "pin-receipt":
                        case.pin_receipt.write_text(
                            case.pin_receipt.read_text(encoding="utf-8").replace(
                                case.pin_sha256, "1" * 64), encoding="utf-8")
                    elif selected == "runtime-receipt":
                        case.release_receipt.write_text(
                            case.release_receipt.read_text(encoding="utf-8").replace(
                                case.binary_sha256, "2" * 64), encoding="utf-8")
                    elif selected == "runtime-overlay":
                        case.release_receipt.write_text(
                            case.release_receipt.read_text(encoding="utf-8").replace(
                                OVERLAY_SHA256, "3" * 64), encoding="utf-8")
                    else:
                        case.engine_bin.write_bytes(b"\x7fELFchanged")
                    with mock.patch.object(
                            sialib, "_run_bounded_text_process",
                            side_effect=AssertionError("unsafe engine executed")), \
                            self.assertRaises(REFUSALS):
                        case._call()

    @contextlib.contextmanager
    def fresh(self):
        case = type(self)(methodName="runTest")
        case.setUp()
        try:
            yield case
        finally:
            case.doCleanups()

    def test_closed_command_results_and_target_matches_fail_closed(self):
        for selected in (
                "sync-extra", "status-commit", "projection-false",
                "projection-foreign"):
            with self.subTest(selected=selected), self.fresh() as case:
                outputs = case._outputs()
                if selected == "sync-extra":
                    parsed = json.loads(outputs["sync"][0])
                    outputs["sync"] = (_wire({**parsed, "extra": True}),
                                       outputs["sync"][1])
                elif selected == "status-commit":
                    parsed = json.loads(outputs["status"][0])
                    parsed["sync"]["sources"][0]["last_commit"] = "0" * 40
                    outputs["status"] = (_wire(parsed), outputs["status"][1])
                elif selected == "projection-false":
                    parsed = json.loads(outputs["projection"][0])
                    parsed["all_match"] = False
                    parsed["targets"][0]["projection_match"] = False
                    outputs["projection"] = (
                        _wire(parsed), outputs["projection"][1])
                else:
                    parsed = json.loads(outputs["projection"][0])
                    parsed["targets"][0]["slug"] = "events/foreign"
                    outputs["projection"] = (
                        _wire(parsed), outputs["projection"][1])
                with mock.patch.object(
                        sialib, "_run_bounded_text_process",
                        side_effect=case._runner(outputs)), \
                        self.assertRaises(REFUSALS):
                    case._call()

    def test_embedding_process_failure_refuses_before_readback(self):
        runner = self._runner()

        def fail_embedding(command, **kwargs):
            if tuple(command[1:]) == (
                    "embed", "--stale", "--source", "sia", "--catch-up"):
                return subprocess.CompletedProcess(
                    command, 1, stdout="", stderr="embedding failed\n")
            return runner(command, **kwargs)

        with mock.patch.object(
                sialib, "_run_bounded_text_process",
                side_effect=fail_embedding), self.assertRaisesRegex(
                    REFUSALS, "source-engine-embedding-process"):
            self._call()
        self.assertEqual(self.calls, ["version", "sync"])

    def test_no_gazetteer_mention_jsonl_prelude_is_admitted(self):
        outputs = self._outputs()
        outputs["mentions"] = (
            _wire({
                "event": "no_gazetteer",
                "message": "no linkable entity pages found; nothing to scan",
            }) + _wire({
                "links_created": 0, "timeline_entries_created": 0,
                "pages_processed": 0,
            }),
            outputs["mentions"][1],
        )
        with mock.patch.object(
                sialib, "_run_bounded_text_process",
                side_effect=self._runner(outputs)):
            result = self._call()
        self.assertEqual(result["sync_generation"]["schema"],
                         "sia-controller-source-sync-generation-v4")

    def test_mention_jsonl_accepts_no_other_prelude_or_nonzero_summary(self):
        for selected in ("foreign-event", "nonzero-summary", "third-document"):
            with self.subTest(selected=selected), self.fresh() as case:
                outputs = case._outputs()
                event = {
                    "event": "no_gazetteer",
                    "message":
                        "no linkable entity pages found; nothing to scan",
                }
                summary = {
                    "links_created": 0, "timeline_entries_created": 0,
                    "pages_processed": 0,
                }
                if selected == "foreign-event":
                    event["event"] = "progress"
                elif selected == "nonzero-summary":
                    summary["pages_processed"] = 1
                wire = _wire(event) + _wire(summary)
                if selected == "third-document":
                    wire = _wire(event) + _wire(event) + _wire(summary)
                outputs["mentions"] = (wire, "")
                with mock.patch.object(
                        sialib, "_run_bounded_text_process",
                        side_effect=case._runner(outputs)), \
                        self.assertRaises(REFUSALS):
                    case._call()

    def test_named_engine_replacement_refuses_held_authority(self):
        retired = self.root / "retired-gbrain"
        swapped = False

        def replace(name):
            nonlocal swapped
            if name == "version" and not swapped:
                swapped = True
                self.engine_root.rename(retired)
                self.engine_root.mkdir()

        with mock.patch.object(
                sialib, "_run_bounded_text_process",
                side_effect=self._runner(replace=replace)), \
                self.assertRaises(REFUSALS):
            self._call()
        self.assertTrue(swapped)

    def test_source_bytes_must_match_the_retained_target_before_execution(self):
        page = self.corpus / (self.slug + ".md")
        page.write_text(self.raw + "changed\n", encoding="utf-8")
        with mock.patch.object(
                sialib, "_run_bounded_text_process",
                side_effect=AssertionError("mismatched source executed")), \
                self.assertRaises(REFUSALS):
            self._call()


if __name__ == "__main__":
    unittest.main()
