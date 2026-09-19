"""Private, lossless history capture is additive to signed-ledger QA exports."""

import base64
import contextlib
import copy
import hashlib
import importlib
import inspect
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_calibration_benchmark as ledger_tests


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


class CognitiveHistoryCapture(unittest.TestCase):
    def setUp(self):
        self.bench = ledger_tests.siabench
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state, self.corpus, self.registry = ledger_tests._signed_fixture(
            self.temp.name)

    _signed_rows = ledger_tests.SignedLedgerDataset._signed_rows
    _projected_row = ledger_tests.SignedLedgerDataset._projected_row
    _replace_marker_with_split_decoys = (
        ledger_tests.SignedLedgerDataset._replace_marker_with_split_decoys)
    _consolidate_sequence_fixture = (
        ledger_tests.SignedLedgerDataset._consolidate_sequence_fixture)

    def _history_module(self):
        try:
            history = importlib.import_module("siacognitivehistory")
        except ModuleNotFoundError as exc:
            self.fail("private cognitive history capture API must exist: " + str(exc))
        for name in ("build_capture", "admit_capture"):
            self.assertTrue(callable(getattr(history, name, None)),
                            "private history API is required: " + name)
        self.assertTrue(hasattr(history, "HistoryRefusal"))
        return history

    def _enabled_bundle(self):
        self.assertIn(
            "cognitive_history",
            inspect.signature(self.bench.build_ledger_dataset).parameters,
            "signed generation needs an explicit opt-in capture hook")
        bundle = self.bench.build_ledger_dataset(
            corpus=self.corpus, chain_registry=self.registry,
            cognitive_history=True)
        self.assertIn("cognitive_history", bundle,
                      "opt-in generation must retain its captured history")
        return bundle

    def _legacy_bundle(self):
        return self.bench.build_ledger_dataset(
            corpus=self.corpus, chain_registry=self.registry)

    def _capture(self):
        return self._enabled_bundle()["cognitive_history"]

    def _source(self, day="2026-01-01"):
        return Path(self.corpus) / "events" / "aegis" / (day + ".md")

    def _published_artifacts(self, directory, *, captured=False):
        modes = {"questions.jsonl": 0o644, "manifest.json": 0o644,
                 "answer-key.jsonl": 0o600, "private-manifest.json": 0o600,
                 "mcp-evaluation.xml": 0o600}
        if captured:
            modes["cognitive-history.json"] = 0o600
        self.assertEqual({path.name for path in directory.iterdir()},
                         set(modes) | {".sia-stage"})
        for name, mode in modes.items():
            info = (directory / name).lstat()
            self.assertTrue(stat.S_ISREG(info.st_mode), name)
            self.assertEqual(info.st_uid, os.geteuid(), name)
            self.assertEqual(info.st_nlink, 1, name)
            self.assertEqual(stat.S_IMODE(info.st_mode), mode, name)
        staging = directory / ".sia-stage"
        info = staging.lstat()
        self.assertTrue(stat.S_ISDIR(info.st_mode))
        self.assertEqual(info.st_uid, os.geteuid())
        self.assertEqual(stat.S_IMODE(info.st_mode), 0o700)
        self.assertEqual({path.name for path in staging.iterdir()}, {"publish.lock"})
        lock = (staging / "publish.lock").lstat()
        self.assertTrue(stat.S_ISREG(lock.st_mode))
        self.assertEqual(lock.st_uid, os.geteuid())
        self.assertEqual(lock.st_nlink, 1)
        self.assertEqual(stat.S_IMODE(lock.st_mode), 0o600)
        return {name: directory / name for name in modes}

    def test_public_capture_api_exists(self):
        self._history_module()

    def test_default_bundle_and_legacy_export_bytes_are_unchanged(self):
        captured = self._enabled_bundle()
        legacy = self._legacy_bundle()
        self.assertNotIn("cognitive_history", legacy)
        self.assertEqual({key: value for key, value in captured.items()
                          if key != "cognitive_history"}, legacy)
        plain_dir, captured_dir = self.root / "plain", self.root / "captured"
        self.bench.write_dataset(legacy, str(plain_dir), corpus=self.corpus)
        self.bench.write_dataset(captured, str(captured_dir), corpus=self.corpus)
        legacy_files = self._published_artifacts(plain_dir)
        captured_files = self._published_artifacts(captured_dir, captured=True)
        self.assertEqual(set(captured_files),
                         set(legacy_files) | {"cognitive-history.json"})
        for name in sorted(legacy_files):
            with self.subTest(name=name):
                self.assertEqual(legacy_files[name].read_bytes(),
                                 captured_files[name].read_bytes())
        self.bench.load_dataset(str(captured_dir))

    def test_capture_preserves_full_exact_page_text_and_origin_from_captured_bytes(self):
        source = self._source()
        raw = source.read_bytes()
        self.assertNotIn(b"origin:", raw)
        raw = raw.replace(b"---\n", b"---\norigin: model\n", 1)
        raw += "\r\nFULL CAPTURE TAIL Ω\u0085and\u2028unchanged\r\n".encode("utf-8")
        source.write_bytes(raw)
        with mock.patch.object(
                self.bench.sialib, "corpus_origin",
                side_effect=AssertionError("must not reopen page to label origin")):
            capture = self._capture()
        page = next(page for page in capture["pages"]
                    if page["slug"] == "events/aegis/2026-01-01")
        self.assertEqual(page["text"].encode("utf-8"), raw)
        self.assertEqual(page["size"], len(raw))
        self.assertEqual(page["sha256"], sha(raw))
        self.assertEqual(page["origin"], "model")
        self.assertEqual(page["declared_origin"], "model")
        self.assertEqual(page["type"], "event-day")
        self.assertEqual(page["role"], "answer-witness")

    def test_origin_labels_do_not_promote_duplicate_or_invalid_declarations(self):
        source = self._source()
        original = source.read_bytes()
        for declaration, expected in (
                (b"origin: derived\n", "derived"),
                (b"origin: evidence\n", "evidence"),
                (b"origin: invented\n", "legacy-unlabeled"),
                (b"origin: evidence\norigin: model\n", "legacy-unlabeled")):
            with self.subTest(declaration=declaration):
                source.write_bytes(original.replace(
                    b"---\n", b"---\n" + declaration, 1))
                page = next(page for page in self._capture()["pages"]
                            if page["slug"] == "events/aegis/2026-01-01")
                self.assertEqual(page["origin"], expected)
                self.assertEqual(page["text"].encode("utf-8"), source.read_bytes())

    def test_every_verified_row_remains_exact_with_native_identity_and_projection(self):
        capture = self._capture()
        rows = self._signed_rows()
        observed = sorted(capture["events"], key=lambda event: int(event["seq"]))
        self.assertEqual([event["row"] for event in observed], rows)
        chain = next(item for item in capture["chains"] if item["chain"] == "aegis")
        self.assertEqual(chain["row_count"], len(rows))
        self.assertEqual(chain["ledger_sha256"],
                         sha(Path(self.registry["aegis"][0]).read_bytes()))
        for event, row in zip(observed, rows):
            with self.subTest(sequence=row[0]):
                self.assertEqual(event["chain"], "aegis")
                self.assertEqual(event["seq"], row[0])
                self.assertEqual(event["entry_hash"], self.bench._entry_hash(row))
                if row[2].startswith("GENESIS:"):
                    self.assertIsNone(event["projection"])
                    self.assertEqual(event["retention"]["status"], "not-projected")
                    continue
                projected = self.bench.sialib.signed_ledger_event_projection("aegis", row)
                self.assertEqual(event["projection"]["event_time_utc"], row[1])
                self.assertEqual(event["projection"]["event_id"],
                                 self.bench.sialib.event_memory_identity(projected))
                self.assertEqual(event["projection"]["semantic_id"],
                                 self.bench.sialib.event_semantic_identity(projected))
                self.assertEqual(event["projection"]["summary"], projected.summary)
                self.assertEqual(event["projection"]["links"], sorted(projected.links))
                self.assertEqual(event["projection"]["tags"], sorted(projected.tags))

    def test_missing_text_lineage_only_and_retained_are_distinct_not_silently_dropped(self):
        self._replace_marker_with_split_decoys("1")
        consolidated = self._consolidate_sequence_fixture("3", retain_exemplar=False)
        capture = self._capture()
        events = {event["seq"]: event for event in capture["events"]}
        self.assertEqual(events["0"]["retention"]["status"], "not-projected")
        self.assertEqual(events["1"]["retention"]["status"], "no-admitted-witness")
        self.assertEqual(events["2"]["retention"]["status"], "retained")
        self.assertEqual(events["3"]["retention"]["status"], "lineage-only")
        self.assertIsNone(events["1"]["retention"]["retrieval_excerpt"])
        self.assertIsNone(events["3"]["retention"]["retrieval_excerpt"])
        self.assertEqual(events["3"]["retention"]["source_slug"],
                         consolidated["epoch_slug"])
        self.assertEqual(events["3"]["retention"]["witness_kind"], "epoch-lineage")
        self.assertEqual(events["3"]["retention"]["index_file"]["path"],
                         consolidated["index_rel"])
        self.assertTrue(events["2"]["retention"]["retrieval_excerpt"])
        self.assertEqual([event["row"] for event in capture["events"]],
                         self._signed_rows())

    def test_accepted_consolidation_witness_bytes_are_preserved_losslessly(self):
        consolidated = self._consolidate_sequence_fixture("3", retain_exemplar=False)
        capture = self._capture()
        witness = next(item for item in capture["witness_files"]
                       if item["path"] == consolidated["index_rel"])
        raw = base64.b64decode(witness["content_base64"], validate=True)
        self.assertEqual(raw, consolidated["index_raw"])
        self.assertEqual(witness["sha256"], sha(raw))
        self.assertEqual(witness["size"], len(raw))
        self.assertEqual(witness["kind"], "event-index")
        page = next(page for page in capture["pages"]
                    if page["slug"] == consolidated["epoch_slug"])
        self.assertEqual(page["text"].encode("utf-8"),
                         (Path(self.corpus) / (consolidated["epoch_slug"] + ".md")).read_bytes())
        self.assertEqual(page["role"], "inspected-only")

    def test_inspected_sibling_pages_are_explicitly_scoped_not_fabricated_witnesses(self):
        sibling = self._source("2026-01-01-part-2")
        raw = ("---\ntype: event-day\norigin: model\ndate: 2026-01-01\n"
               "sia_shard: 2\n---\n## Log\n- unrelated inspected note\n").encode()
        sibling.write_bytes(raw)
        capture = self._capture()
        page = next(page for page in capture["pages"]
                    if page["slug"] == "events/aegis/2026-01-01-part-2")
        self.assertEqual(page["role"], "inspected-only")
        self.assertEqual(page["origin"], "model")
        self.assertEqual(page["text"].encode(), raw)
        self.assertEqual(capture["scope"]["kind"], "verified-ledger-projection-cache")
        self.assertIs(capture["scope"]["entire_corpus"], False)
        for field in ("queries", "query_classes", "tuned_parameters", "benchmark_wins"):
            self.assertNotIn(field, capture)
        self.assertIn("No query classes, tuned parameters, or cognitive wins are established.",
                      capture["non_claims"])

    def test_capture_identity_is_deterministic_detached_and_binds_full_page_bytes(self):
        history = self._history_module()
        first, second = self._capture(), self._capture()
        self.assertEqual(first, second)
        self.assertEqual(first["schema"], "sia-cognitive-history-capture-v1")
        body = {key: value for key, value in first.items() if key != "capture_sha256"}
        self.assertEqual(first["capture_sha256"], sha(canonical(body)))
        admitted = history.admit_capture(first)
        self.assertEqual(admitted, first)
        admitted["pages"][0]["text"] += "caller-only mutation"
        self.assertNotEqual(admitted, first)
        source = self._source()
        source.write_bytes(source.read_bytes() + b"\nnew retained tail\n")
        changed = self._capture()
        self.assertNotEqual(first["capture_sha256"], changed["capture_sha256"])

    def test_admission_rejects_changed_capture_and_component_hashes(self):
        history = self._history_module()
        capture = self._capture()
        changed = copy.deepcopy(capture)
        changed["pages"][0]["text"] += "unbound change"
        with self.assertRaises(history.HistoryRefusal):
            history.admit_capture(changed)
        changed["capture_sha256"] = sha(canonical({
            key: value for key, value in changed.items() if key != "capture_sha256"}))
        with self.assertRaises(history.HistoryRefusal):
            history.admit_capture(changed)

    def test_writer_uses_captured_bytes_after_source_changes_without_reopening_corpus(self):
        bundle = self._enabled_bundle()
        captured = copy.deepcopy(bundle["cognitive_history"])
        self._source().write_bytes(b"replaced after lease capture\n")
        output = self.root / "export"
        with mock.patch.object(
                self.bench, "_read_nofollow_regular",
                side_effect=AssertionError("export must not reread source generations")), \
                mock.patch.object(
                    self.bench.sialib, "corpus_origin",
                    side_effect=AssertionError("export must not reopen source origins")):
            self.bench.write_dataset(bundle, str(output), corpus=self.corpus)
        artifact = output / "cognitive-history.json"
        self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(artifact.read_bytes()), captured)
        self.assertEqual(bundle["cognitive_history"], captured)

    def test_capture_file_ceiling_refuses_before_any_artifact_is_published(self):
        source = self._source()
        source.write_bytes(source.read_bytes() + b"x" * self.bench.sialib.MAX_CONFIG_BYTES)
        bundle = self._enabled_bundle()
        legacy = {key: value for key, value in bundle.items() if key != "cognitive_history"}
        plain = self.root / "plain"
        self.bench.write_dataset(legacy, str(plain), corpus=self.corpus)
        for path in self._published_artifacts(plain).values():
            self.assertLess(path.stat().st_size, self.bench.sialib.MAX_CONFIG_BYTES)
        output = self.root / "over-limit"
        with mock.patch.object(self.bench, "MAX_BENCH_FILE_BYTES",
                               self.bench.sialib.MAX_CONFIG_BYTES), \
                self.assertRaises(self.bench.BenchmarkRefusal):
            self.bench.write_dataset(bundle, str(output), corpus=self.corpus)
        self.assertFalse(output.exists() and any(output.iterdir()))

    def test_capture_is_included_in_existing_aggregate_export_budget(self):
        bundle = self._enabled_bundle()
        legacy = {key: value for key, value in bundle.items() if key != "cognitive_history"}
        plain = self.root / "plain"
        self.bench.write_dataset(legacy, str(plain), corpus=self.corpus)
        legacy_bytes = sum(len(path.read_bytes())
                           for path in self._published_artifacts(plain).values())
        output = self.root / "over-aggregate"
        with mock.patch.object(self.bench, "MAX_BENCH_AGGREGATE_BYTES", legacy_bytes), \
                self.assertRaises(self.bench.BenchmarkRefusal):
            self.bench.write_dataset(bundle, str(output), corpus=self.corpus)
        self.assertFalse(output.exists() and any(output.iterdir()))

    def test_private_capture_cannot_be_written_inside_indexed_corpus(self):
        bundle = self._enabled_bundle()
        output = Path(self.corpus) / "private-answer-leak"
        with self.assertRaisesRegex(ValueError, "inside indexed corpus"):
            self.bench.write_dataset(bundle, str(output), corpus=self.corpus)
        self.assertFalse(output.exists())

    def test_cli_capture_and_publication_remain_in_one_existing_owner_lease(self):
        bundle = self._enabled_bundle()
        original_write = self.bench.write_dataset
        held = {"value": False}

        @contextlib.contextmanager
        def owner():
            self.assertFalse(held["value"])
            held["value"] = True
            try:
                yield
            finally:
                held["value"] = False

        def build(**kwargs):
            self.assertTrue(held["value"])
            self.assertIs(kwargs.get("cognitive_history"), True)
            return bundle

        def write(*args, **kwargs):
            self.assertTrue(held["value"])
            return original_write(*args, corpus=self.corpus, **kwargs)

        output = self.root / "cli-export"
        stdout = io.StringIO()
        with mock.patch.object(self.bench.sialib, "corpus_owner", side_effect=owner), \
                mock.patch.object(self.bench, "build_ledger_dataset", side_effect=build), \
                mock.patch.object(self.bench, "write_dataset", side_effect=write), \
                contextlib.redirect_stdout(stdout):
            try:
                result = self.bench.main([
                    "generate", "--cognitive-history", "--out", str(output)])
            except SystemExit as exc:
                self.fail("generate needs the additive --cognitive-history flag: " + str(exc))
        self.assertEqual(result, 0)
        self.assertFalse(held["value"])
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["cognitive_history"], "cognitive-history.json (mode 0600)")
        self.assertEqual(report["capture_sha256"], bundle["cognitive_history"]["capture_sha256"])
        self.assertTrue((output / "cognitive-history.json").is_file())


if __name__ == "__main__":
    unittest.main()
