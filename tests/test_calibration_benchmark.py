#!/usr/bin/env python3
"""Deterministic calibration and signed-ledger QA fixtures."""

import hashlib
import copy
import contextlib
import datetime
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import types
import unittest
import unicodedata
import xml.etree.ElementTree as ET
from unittest import mock

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")
sys.path.insert(0, BIN)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(text)


def _read_path(path):
    with open(path, encoding="utf-8") as stream:
        return stream.read()


siatakes = _load("siatakes_calibration", os.path.join(BIN, "siatakes.py"))
siabench = _load("siabench_signed", os.path.join(BIN, "siabench.py"))


def _write_projected_event_pages(corpus, chain, rows):
    by_day = {}
    for row in rows:
        event = siabench.sialib.signed_ledger_event_projection(chain, row)
        if event is None:
            continue
        event_id = siabench.sialib.event_memory_identity(event)
        semantic_id = siabench.sialib.event_semantic_identity(event)
        line, _payload, _base = siabench.sialib._event_line(
            event, event_id, semantic_id)
        day = event.ts.astimezone(
            datetime.timezone.utc).date().isoformat()
        state = by_day.setdefault((event.organ, day), {
            "part": 1, "counts": {}, "tags": set(), "bullets": []})
        state["counts"][event.kind] = \
            state["counts"].get(event.kind, 0) + 1
        state["tags"] |= event.tags
        state["bullets"].append(line)
    for (organ, day), state in by_day.items():
        state["slug"] = f"events/{organ}/{day}"
        frontmatter, body = siabench.sialib._render_event_shard(
            organ, day, state)
        _write(os.path.join(corpus, state["slug"] + ".md"),
               "---\n" + "\n".join(frontmatter) + "\n---\n" + body)


def _signed_fixture(root):
    """Write the same attest-ledger bytes on every run (no private key file)."""
    state = os.path.join(root, "signed")
    corpus = os.path.join(root, "corpus")
    os.makedirs(state)
    os.makedirs(corpus)
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("01" * 32))
    pub = key.public_key().public_bytes_raw().hex()
    with open(os.path.join(state, "pub.hex"), "w") as stream:
        stream.write(pub + "\n")
    genesis_prev = hashlib.sha256(b"attest-genesis-v1").hexdigest()
    rows = [
        ["0", "2026-01-01T00:00:00Z", "GENESIS:init", "fixture", "-",
         hashlib.sha256(b"genesis").hexdigest(), "0", genesis_prev, ""],
        ["1", "2026-01-01T01:00:00Z", "OUTCOME:restart",
         "wireplumber.service", "ok", hashlib.sha256(b"one").hexdigest(),
         "3", "", ""],
        ["2", "2026-01-02T01:00:00Z", "OUTCOME:restart",
         "wireplumber.service", "held", hashlib.sha256(b"two").hexdigest(),
         "3", "", ""],
        ["3", "2026-01-03T01:00:00Z", "INTENT:restart",
         "pipewire.service", "requested", hashlib.sha256(b"three").hexdigest(),
         "5", "", ""],
        ["4", "2026-01-04T01:00:00Z", "OUTCOME:restart",
         "pipewire.service", "ok", hashlib.sha256(b"four").hexdigest(),
         "4", "", ""],
        ["5", "2026-01-05T01:00:00Z", "CHECK:unit",
         "bluetooth.service", "healthy", hashlib.sha256(b"five").hexdigest(),
         "4", "", ""],
    ]
    previous = genesis_prev
    encoded = []
    for row in rows:
        row[7] = previous
        entry = siabench._entry_hash(row)
        row[8] = key.sign(bytes.fromhex(entry)).hex()
        encoded.append("\t".join(row))
        previous = entry
    with open(os.path.join(state, "ledger.tsv"), "w") as stream:
        stream.write("\n".join(encoded) + "\n")
    with open(os.path.join(state, "head.pin"), "w") as stream:
        stream.write(f"{len(rows)} {previous}\n")

    _write_projected_event_pages(corpus, "aegis", rows)
    registry = {
        "aegis": (os.path.join(state, "ledger.tsv"),
                  os.path.join(BIN, "sia-ledger"),
                  [sys.executable, os.path.join(BIN, "sia-ledger"),
                   "verify", state, "--quiet"]),
    }
    return state, corpus, registry


def _custos_fixture(root):
    """Write structurally valid legacy Custos rows and matching corpus pages."""
    state = os.path.join(root, "custos-signed")
    corpus = os.path.join(root, "custos-corpus")
    os.makedirs(state)
    os.makedirs(corpus)
    rows = [
        ["0", "0", "genesis", "-", "-",
         hashlib.sha256(b"custos-genesis").hexdigest(), "0", "", ""],
        ["1", "1", "OUTCOME:restart", "wireplumber.service", "ok",
         hashlib.sha256(b"custos-one").hexdigest(), "3", "", ""],
        ["2", "2", "OUTCOME:restart", "wireplumber.service", "held",
         hashlib.sha256(b"custos-two").hexdigest(), "3", "", ""],
        ["3", "3", "INTENT:restart", "pipewire.service", "requested",
         hashlib.sha256(b"custos-three").hexdigest(), "5", "", ""],
        ["4", "4", "OUTCOME:restart", "pipewire.service", "ok",
         hashlib.sha256(b"custos-four").hexdigest(), "4", "", ""],
        ["5", "5", "CHECK:unit", "bluetooth.service", "healthy",
         hashlib.sha256(b"custos-five").hexdigest(), "4", "", ""],
    ]
    previous = hashlib.sha256(b"custos-genesis-v1").hexdigest()
    encoded = []
    for row in rows:
        row[7] = previous
        row[8] = "ab" * 64
        line = "\t".join(row)
        encoded.append(line)
        previous = hashlib.sha256(line.encode("utf-8")).hexdigest()
    ledger = os.path.join(state, "ledger.tsv")
    _write(ledger, "\n".join(encoded) + "\n")

    _write_projected_event_pages(corpus, "custos", rows)

    verifier = shutil.which("true")
    registry = {"custos": (ledger, verifier, [verifier])}
    return state, corpus, registry, rows, encoded, previous


def _take(confidence, outcome, domain="general", status=None, **extra):
    if status is None:
        status = "resolved-true" if outcome == 1 else "resolved-false"
    row = {"status": status, "confidence": confidence, "outcome": outcome,
           "domain": domain, "brier": 999}
    row.update(extra)
    return row


class JsonParserBoundaries(unittest.TestCase):
    def test_take_authority_parser_limits_are_named_and_retain_files(self):
        with tempfile.TemporaryDirectory() as root:
            proposal_path = os.path.join(root, "proposals.json")
            transaction_path = os.path.join(root, "transaction.json")
            history_path = os.path.join(root, "history.json")
            record_path = os.path.join(root, "record.json")
            for path, payload in (
                    (proposal_path, "[]"), (transaction_path, "{}"),
                    (history_path, "{}"), (record_path, "{}")):
                _write(path, payload)
                os.chmod(path, 0o600)
            paths = {"state": history_path}
            cases = (
                (lambda: siatakes._load_proposal_queue(proposal_path),
                 "proposal queue is invalid JSON"),
                (lambda: siatakes._read_transaction_json(transaction_path),
                 "transaction journal is malformed"),
                (lambda: siatakes._load_history_state("take"),
                 "natural-history state is malformed"),
                (lambda: siatakes._read_history_json(
                    record_path, "natural-history record"),
                 "natural-history record is malformed"),
                (lambda: siatakes._history_page_metadata(
                    "take", os.path.join(root, "take.md"),
                    "sia_take: {}\n"),
                 "take page metadata is invalid"),
                (lambda: siatakes._legacy_v1_page(
                    os.path.join(root, "take.md"), "sia_take: {}\n"),
                 "legacy take metadata JSON is invalid"),
            )
            with mock.patch.object(siatakes, "_history_paths",
                                   return_value=paths):
                for parser_error in (ValueError, RecursionError):
                    for call, expected in cases:
                        with self.subTest(
                                parser_error=parser_error.__name__,
                                expected=expected), \
                                mock.patch.object(
                                    siatakes.json, "loads",
                                    side_effect=parser_error(
                                        "private source content")), \
                                self.assertRaises(ValueError) as raised:
                            call()
                        self.assertEqual(str(raised.exception), expected)
            self.assertTrue(all(os.path.exists(path) for path in (
                proposal_path, transaction_path, history_path, record_path)))

    def test_benchmark_parser_limits_are_clean_refusals(self):
        completed = mock.Mock(returncode=0, stdout="[]", stderr="")
        for parser_error in (ValueError, RecursionError):
            with self.subTest(parser_error=parser_error.__name__), \
                    mock.patch.object(siabench.sialib, "gbrain",
                                      return_value=completed), \
                    mock.patch.object(
                        siabench.json, "loads",
                        side_effect=parser_error("private source content")), \
                    self.assertRaises(
                        siabench.BenchmarkRefusal) as engine_refusal:
                siabench._engine(["query", "fixture"])
            self.assertEqual(
                str(engine_refusal.exception),
                "gbrain retrieval output could not be admitted")

            with self.subTest(parser_error=parser_error.__name__), \
                    mock.patch.object(
                        siabench.json, "loads",
                        side_effect=parser_error("private source content")), \
                    self.assertRaises(
                        siabench.BenchmarkRefusal) as row_refusal:
                siabench._parse_jsonl("{}\n", "answers.jsonl")
            self.assertEqual(
                str(row_refusal.exception),
                "benchmark JSONL row is malformed at line 1")

            artifact = (b"{}", (1, 2, 3, 4, 5), "0" * 64)
            with self.subTest(parser_error=parser_error.__name__), \
                    mock.patch.object(
                        siabench, "_read_nofollow_regular",
                        return_value=artifact), \
                    mock.patch.object(
                        siabench.json, "loads",
                        side_effect=parser_error("private source content")), \
                    self.assertRaises(
                        siabench.BenchmarkRefusal) as manifest_refusal:
                siabench.load_dataset("/unused")
            self.assertEqual(
                str(manifest_refusal.exception),
                "benchmark dataset manifests are malformed")


class JudgeIsolation(unittest.TestCase):
    def _head_v1_take(self, takes_dir, *, claim, deadline, domain,
                      status="resolved-true", justification="legacy witness",
                      links=()):
        created = "2026-08-29T12:00:00Z"
        take_id = hashlib.sha256(
            f"{claim}|{created}".encode()).hexdigest()[:10]
        confidence = 0.7
        if status == "open":
            outcome = brier = graded = None
        else:
            graded = "2026-08-30T12:00:00Z"
            if status == "unresolvable":
                outcome = brier = None
            else:
                outcome = 1.0 if status == "resolved-true" else 0.0
                brier = round((confidence - outcome) ** 2, 4)
        meta = {
            "id": take_id, "claim": claim, "confidence": confidence,
            "deadline": deadline[:10], "domain": domain.lower(),
            "holder": "user", "status": status, "created": created,
            "outcome": outcome, "brier": brier, "graded": graded,
        }
        linkline = " ".join(f"[[{link}]]" for link in links)
        text = (
            "---\n"
            "type: take\n"
            f"title: {json.dumps(claim[:70], ensure_ascii=False)}\n"
            f"tags: [take, {status}, {meta['domain']}]\n"
            f"date: {created[:10]}\n"
            f"sia_take: {json.dumps(meta, sort_keys=True)}\n"
            "---\n"
            f"# take · {take_id}\n\n"
            f"**Claim:** {claim}\n\n"
            f"**Holder:** user · confidence {confidence:.2f} · "
            f"due {meta['deadline']} · domain {meta['domain']}\n\n"
            "A falsifiable prediction. When due it will be graded against "
            "recalled evidence and Brier-scored; the grade updates this page.\n\n"
            f"{linkline} [[sia/cortex]]\n")
        if status != "open":
            verdict = {"resolved-true": "TRUE", "resolved-false": "FALSE",
                       "unresolvable": "UNRESOLVABLE"}[status]
            text += (f"\n## Grade · {graded}\n\n"
                     f"**{verdict}**"
                     + (f" · Brier {brier}" if brier is not None else "")
                     + " — judged by safe-legacy-label against recalled "
                     "evidence; model-assisted, verify via the cited "
                     "memories.\n\n"
                     f"{justification}\n")
        path = os.path.join(takes_dir, f"{created[:10]}-{take_id}.md")
        _write(path, text)
        return meta, path, text

    def _legacy_resolved_take(self, takes_dir, justification):
        siatakes.create_take(
            "legacy model grade", deadline="2099-01-01",
            links=("operator/source",))
        take = siatakes.load_takes()[0]
        source = _read_path(take["path"])
        take.update({
            "status": "resolved-true",
            "outcome": 1,
            "brier": 0.09,
            "graded": "2026-08-30T12:00:00Z",
            "judge_model": "claude:legacy",
            "_grade_source_sha256": hashlib.sha256(
                source.encode()).hexdigest(),
        })
        _path, _source, current_target = siatakes._render_take_page(
            take, "TRUE", "seed justification")
        legacy = current_target.replace("origin: model\n", "", 1)
        legacy = legacy.replace(
            "Model justification (inert prose): seed justification",
            justification, 1)
        _write(take["path"], legacy)
        return take, legacy

    def test_judge_config_requires_explicit_well_formed_consent(self):
        with tempfile.TemporaryDirectory() as home:
            old_home = siatakes.HOME
            siatakes.HOME = home
            config = os.path.join(home, ".config/sia/config.json")
            cases = (
                None,
                "{",
                "[]",
                '{"judge":null}',
                '{"judge":"claude"}',
                '{"judge":{}}',
                '{"judge":{"backend":""}}',
                '{"judge":{"backend":"unknown","model":"x"}}',
                '{"judge":{"backend":"claude","model":3}}',
            )
            try:
                for content in cases:
                    with self.subTest(content=content):
                        if os.path.exists(config):
                            os.unlink(config)
                        if content is not None:
                            _write(config, content)
                        with mock.patch.object(
                                siatakes.subprocess, "run") as run:
                            self.assertEqual(siatakes._judge_config(),
                                             ("none", ""))
                            text, error = siatakes._judge_run("private")
                        self.assertIsNone(text)
                        self.assertIn("no inference-only judge", error)
                        run.assert_not_called()
                _write(config, json.dumps(
                    {"judge": {"backend": "claude",
                               "model": "claude-opus-5"}}))
                self.assertEqual(siatakes._judge_config(),
                                 ("claude", "claude-opus-5"))
                _write(config, json.dumps(
                    {"judge": {"backend": "none", "model": "ignored"}}))
                self.assertEqual(siatakes._judge_config(), ("none", ""))
                _write(config, "x" * (siatakes.MAX_CONFIG_BYTES + 1))
                self.assertEqual(siatakes._judge_config(), ("none", ""))
                os.unlink(config)
                outside = os.path.join(home, "outside-config.json")
                _write(outside, json.dumps({
                    "judge": {"backend": "claude", "model": "secret"}}))
                os.symlink(outside, config)
                self.assertEqual(siatakes._judge_config(), ("none", ""))
            finally:
                siatakes.HOME = old_home

    def test_claude_judge_has_no_tools_mcp_or_workspace_context(self):
        observed = {}

        def run(command, prompt, **kwargs):
            observed["command"] = command
            observed["prompt"] = prompt
            observed.update(kwargs)
            self.assertEqual(os.listdir(kwargs["cwd"]), [])
            return (0, "VERDICT: UNRESOLVABLE\n"
                    "JUSTIFICATION: no witness", "")

        with mock.patch.object(siatakes, "_judge_config",
                               return_value=("claude", "claude-opus-5")), \
                mock.patch.object(siatakes, "_bounded_judge_process",
                                  side_effect=run), \
                mock.patch.dict(os.environ,
                                {"SIA_TEST_LOCAL_SECRET": "must-not-pass"}):
            text, error = siatakes._judge_run("untrusted evidence")
        self.assertIsNone(error)
        self.assertIn("VERDICT: UNRESOLVABLE", text)
        command = observed["command"]
        self.assertEqual(command[command.index("--tools") + 1], "")
        self.assertIn("--strict-mcp-config", command)
        self.assertIn('{"mcpServers":{}}', command)
        self.assertIn("--safe-mode", command)
        self.assertIn("--no-session-persistence", command)
        self.assertIn("--system-prompt", command)
        self.assertEqual(command[command.index("--model") + 1],
                         "claude-opus-5")
        self.assertEqual(observed["prompt"], "untrusted evidence")
        self.assertNotIn("SIA_TEST_LOCAL_SECRET", observed["env"])

    def test_judge_process_refuses_bounded_output_overflow(self):
        command = [sys.executable, "-c",
                   "import os; os.write(1, b'x' * 65)"]
        with tempfile.TemporaryDirectory() as cwd, \
                mock.patch.object(siatakes, "MAX_JUDGE_OUTPUT_BYTES", 64), \
                self.assertRaisesRegex(OverflowError,
                                            "judge output exceeded"):
            siatakes._bounded_judge_process(
                command, "prompt", timeout=30, cwd=cwd, env=os.environ)

    def test_judge_process_refuses_invalid_utf8_stdout(self):
        command = [sys.executable, "-c",
                   "import os; os.write(1, bytes([255]))"]
        with tempfile.TemporaryDirectory() as cwd, \
                self.assertRaises(UnicodeDecodeError):
            siatakes._bounded_judge_process(
                command, "prompt", timeout=30, cwd=cwd, env=os.environ)

    def test_judge_process_refuses_oversized_prompt_before_spawn(self):
        with mock.patch.object(siatakes, "MAX_JUDGE_INPUT_BYTES", 64), \
                mock.patch.object(siatakes.subprocess, "Popen") as popen, \
                self.assertRaisesRegex(OverflowError,
                                            "judge prompt exceeded"):
            siatakes._bounded_judge_process(
                ["unused"], "x" * 65, timeout=30, cwd="/", env={})
        popen.assert_not_called()

    def test_judge_timeout_kills_descendant_after_parent_exits(self):
        with tempfile.TemporaryDirectory() as cwd:
            pid_file = os.path.join(cwd, "descendant.pid")
            parent = (
                "import pathlib,subprocess,sys; "
                "child=subprocess.Popen([sys.executable,'-c',"
                "'import time; time.sleep(60)']); "
                "pathlib.Path(sys.argv[1]).write_text(str(child.pid))")
            with self.assertRaises(subprocess.TimeoutExpired):
                siatakes._bounded_judge_process(
                    [sys.executable, "-c", parent, pid_file], "prompt",
                    timeout=1, cwd=cwd, env=os.environ)
            with open(pid_file, encoding="utf-8") as stream:
                child_pid = int(stream.read())
            deadline = time.monotonic() + 2
            alive = True
            while time.monotonic() < deadline:
                try:
                    with open(f"/proc/{child_pid}/stat",
                              encoding="utf-8") as stream:
                        state = stream.read().split()[2]
                except FileNotFoundError:
                    alive = False
                    break
                if state == "Z":
                    alive = False
                    break
                time.sleep(0.01)
            self.assertFalse(alive, "judge descendant survived group kill")

    def test_claude_judge_refuses_implicit_model(self):
        with mock.patch.object(siatakes, "_judge_config",
                               return_value=("claude", "")), \
                mock.patch.object(siatakes.subprocess, "run") as run:
            text, error, label = siatakes._judge_run(
                "untrusted evidence", include_label=True)
        self.assertIsNone(text)
        self.assertIn("explicit judge.model", error)
        self.assertEqual(label, "no-judge")
        run.assert_not_called()

    def test_grade_and_audit_prompts_are_blind_to_confidence(self):
        prompts = []

        def judge(prompt, include_label=False, **_kwargs):
            prompts.append(prompt)
            base = ("VERDICT: UNRESOLVABLE\nJUSTIFICATION: no witness", None)
            return base + ("claude:claude-opus-5",) if include_label else base

        take = {"id": "a" * 20, "claim": "the event occurs",
                "confidence": 0.7, "created": "2026-01-01T00:00:00Z",
                "deadline": "2026-01-02", "status": "open"}
        completed_empty = siatakes.RecallEvidence(
            True, "", frozenset())
        with mock.patch.object(siatakes, "_recall",
                               return_value=completed_empty), \
                mock.patch.object(siatakes, "_organ_evidence",
                                  return_value=("", set())), \
                mock.patch.object(siatakes, "_judge_run", side_effect=judge):
            graded = siatakes.grade_take(take, persist=lambda *_args: None)
            audited = siatakes.judge_claim(
                take["claim"], created=take["created"],
                confidence=take["confidence"], deadline=take["deadline"])
        self.assertEqual(graded["status"], "unresolvable")
        self.assertEqual(audited[0], "UNRESOLVABLE")
        self.assertEqual(len(prompts), 2)
        self.assertTrue(all("confidence" not in prompt.casefold()
                            for prompt in prompts))

    def test_model_grade_is_inert_and_persisted_with_model_origin(self):
        raw = ("VERDICT: TRUE\nJUSTIFICATION: "
               "[[events/journal/day]] <img src=x> *bold* "
               "[remote](https://invalid.example) `code` | _cell_ ~~old~~")
        verdict, justification = siatakes._parse_judgment(
            raw, {"events/journal/day"})
        self.assertEqual(verdict, "TRUE")
        self.assertIn("⟦⟦events/journal/day⟧⟧", justification)
        for active in ("[[", "]]", "<", ">", "*", "`", "|", "_", "~"):
            self.assertNotIn(active, justification)

        old_dir = siatakes.TAKES_DIR
        with tempfile.TemporaryDirectory() as takes_dir:
            siatakes.TAKES_DIR = takes_dir
            try:
                deadline = (siatakes._utcnow()
                            + siatakes.datetime.timedelta(days=1)) \
                    .strftime("%Y-%m-%d")
                siatakes.create_take("model-origin grade", deadline=deadline)
                take = siatakes.load_takes()[0]
                with open(take["path"], encoding="utf-8") as stream:
                    source = stream.read()
                self.assertIn("\norigin: derived\n", source)
                take.update({
                    "status": "resolved-true",
                    "outcome": 1,
                    "brier": 0.09,
                    "graded": "2026-08-30T12:00:00Z",
                    "judge_model": "claude:claude-opus-5",
                    "_grade_source_sha256": hashlib.sha256(
                        source.encode()).hexdigest(),
                })
                _path, _source, target = siatakes._render_take_page(
                    take, verdict, justification)
                self.assertEqual(target.count("\norigin: model\n"), 1)
                self.assertNotIn("[[events/journal/day]]", target)
                self.assertIn("⟦⟦events/journal/day⟧⟧", target)
                self.assertIn("Model justification (inert prose):", target)
            finally:
                siatakes.TAKES_DIR = old_dir

    def test_grade_recovery_marks_debt_when_target_is_already_published(self):
        old_takes = siatakes.TAKES_DIR
        old_transactions = siatakes.GRADE_TX_DIR
        with tempfile.TemporaryDirectory() as root:
            siatakes.TAKES_DIR = os.path.join(root, "takes")
            siatakes.GRADE_TX_DIR = os.path.join(root, "grade-transactions")
            try:
                siatakes.create_take(
                    "already published grade", deadline="2099-01-01")
                take = siatakes.load_takes()[0]
                source = _read_path(take["path"])
                take.update({
                    "status": "resolved-true",
                    "outcome": 1,
                    "brier": 0.09,
                    "graded": "2026-08-30T12:00:00Z",
                    "judge_model": "claude:fixture",
                    "_grade_source_sha256": hashlib.sha256(
                        source.encode()).hexdigest(),
                })
                path, source_text, target = siatakes._render_take_page(
                    take, "TRUE", "admitted fixture witness")
                payload = siatakes._grade_tx_payload(
                    take, path, source_text, target)
                os.makedirs(siatakes.GRADE_TX_DIR)
                journal = os.path.join(
                    siatakes.GRADE_TX_DIR, take["id"] + ".json")
                _write(journal, json.dumps(payload, sort_keys=True))
                os.chmod(journal, 0o600)
                _write(path, target)

                marked = []
                append = mock.Mock(
                    side_effect=AssertionError("must not sign twice"))
                fake_sialib = types.SimpleNamespace(
                    ledger_contains=lambda *_row: True,
                    ledger_append=append)

                def before_publish():
                    self.assertEqual(_read_path(path), target)
                    marked.append("sync-owed")

                with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                    recovered, errors = siatakes.recover_grade_transactions(
                        before_publish=before_publish)

                self.assertEqual(errors, [])
                self.assertEqual(recovered, [take["id"]])
                self.assertEqual(marked, ["sync-owed"])
                self.assertFalse(os.path.exists(journal))
                self.assertEqual(_read_path(path), target)
                append.assert_not_called()
            finally:
                siatakes.TAKES_DIR = old_takes
                siatakes.GRADE_TX_DIR = old_transactions

    def test_grade_transaction_refuses_oversized_resolved_page(self):
        old_takes = siatakes.TAKES_DIR
        with tempfile.TemporaryDirectory() as root:
            siatakes.TAKES_DIR = os.path.join(root, "takes")
            os.mkdir(siatakes.TAKES_DIR)
            try:
                take = {"id": "0" * 20, "status": "resolved-true"}
                path = os.path.join(siatakes.TAKES_DIR, "target.md")
                target = "x" * (siatakes.MAX_TAKE_PAGE_BYTES + 1)
                with self.assertRaisesRegex(ValueError, "bounded size"):
                    siatakes._grade_tx_payload(
                        take, path, "source", target)
            finally:
                siatakes.TAKES_DIR = old_takes

    def test_legacy_grade_migration_signs_before_inert_publication(self):
        trace = []
        signed = {"present": False, "row": None}
        old_takes = siatakes.TAKES_DIR
        old_transactions = siatakes.TAKE_MIGRATION_TX_DIR
        with tempfile.TemporaryDirectory() as root:
            takes_dir = os.path.join(root, "takes")
            transactions = os.path.join(root, "take-migrations")
            siatakes.TAKES_DIR = takes_dir
            siatakes.TAKE_MIGRATION_TX_DIR = transactions
            try:
                take, legacy = self._legacy_resolved_take(
                    takes_dir,
                    "[[model/forged]] <img src=x> *bold* `code`")

                def contains(action, take_id, kind, target):
                    return signed["present"] and signed["row"] == (
                        action, take_id, kind, target)

                def append(action, take_id, kind, target, required=False):
                    self.assertTrue(required)
                    self.assertEqual(_read_path(take["path"]), legacy)
                    trace.append("signed")
                    signed["present"] = True
                    signed["row"] = (action, take_id, kind, target)

                def before_publish():
                    self.assertTrue(signed["present"])
                    self.assertEqual(_read_path(take["path"]), legacy)
                    trace.append("sync-owed")

                fake_sialib = types.SimpleNamespace(
                    ledger_contains=contains, ledger_append=append)
                with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                    self.assertTrue(siatakes.take_migration_required())
                    migrated, errors = siatakes.migrate_legacy_take_pages(
                        before_publish=before_publish)

                self.assertEqual(errors, [])
                self.assertEqual(migrated, [take["id"]])
                self.assertEqual(trace, ["signed", "sync-owed"])
                target = _read_path(take["path"])
                self.assertIn("\norigin: model\n", target)
                self.assertIn("[[operator/source]]", target)
                self.assertNotIn("[[model/forged]]", target)
                self.assertIn("⟦⟦model/forged⟧⟧", target)
                self.assertFalse(siatakes.take_migration_required())
                self.assertEqual(os.listdir(transactions), [])
                self.assertEqual(signed["row"][:3], (
                    "MIGRATE:take-origin", take["id"], "model-inert-v1"))
                self.assertEqual(signed["row"][3], target)
            finally:
                siatakes.TAKES_DIR = old_takes
                siatakes.TAKE_MIGRATION_TX_DIR = old_transactions

    def test_legacy_grade_migration_recovers_without_duplicate_signature(self):
        old_takes = siatakes.TAKES_DIR
        old_transactions = siatakes.TAKE_MIGRATION_TX_DIR
        with tempfile.TemporaryDirectory() as root:
            siatakes.TAKES_DIR = os.path.join(root, "takes")
            siatakes.TAKE_MIGRATION_TX_DIR = os.path.join(
                root, "take-migrations")
            try:
                take, legacy = self._legacy_resolved_take(
                    siatakes.TAKES_DIR, "[[model/retry]]")
                signed_rows = []

                def contains(*row):
                    return row in signed_rows

                def append(*row, required=False):
                    self.assertTrue(required)
                    signed_rows.append(row)

                fake_sialib = types.SimpleNamespace(
                    ledger_contains=contains, ledger_append=append)
                with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                    first, first_errors = siatakes.migrate_legacy_take_pages(
                        before_publish=lambda: (_ for _ in ()).throw(
                            RuntimeError("simulated crash")))
                    self.assertEqual(first, [])
                    self.assertEqual(len(first_errors), 1)
                    self.assertEqual(_read_path(take["path"]), legacy)
                    self.assertEqual(len(signed_rows), 1)

                    recovered, errors = siatakes.migrate_legacy_take_pages(
                        before_publish=lambda: None)

                self.assertEqual(errors, [])
                self.assertEqual(recovered, [take["id"]])
                self.assertEqual(len(signed_rows), 1)
                self.assertIn("\norigin: model\n", _read_path(take["path"]))
                self.assertEqual(os.listdir(
                    siatakes.TAKE_MIGRATION_TX_DIR), [])
            finally:
                siatakes.TAKES_DIR = old_takes
                siatakes.TAKE_MIGRATION_TX_DIR = old_transactions

    def test_legacy_empty_justification_is_preserved_as_explicit_absence(self):
        old_takes = siatakes.TAKES_DIR
        old_transactions = siatakes.TAKE_MIGRATION_TX_DIR
        with tempfile.TemporaryDirectory() as root:
            siatakes.TAKES_DIR = os.path.join(root, "takes")
            siatakes.TAKE_MIGRATION_TX_DIR = os.path.join(
                root, "take-migrations")
            try:
                take, _legacy = self._legacy_resolved_take(
                    siatakes.TAKES_DIR, "")
                signed_rows = []
                fake_sialib = types.SimpleNamespace(
                    ledger_contains=lambda *row: row in signed_rows,
                    ledger_append=lambda *row, **_kwargs: signed_rows.append(row))
                with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                    migrated, errors = siatakes.migrate_legacy_take_pages()
                self.assertEqual(errors, [])
                self.assertEqual(migrated, [take["id"]])
                self.assertIn(
                    "Model justification (inert prose): Legacy judge "
                    "supplied no justification.", _read_path(take["path"]))
            finally:
                siatakes.TAKES_DIR = old_takes
                siatakes.TAKE_MIGRATION_TX_DIR = old_transactions

    def test_exact_v1_take_shapes_normalize_stricter_fields(self):
        old_takes = siatakes.TAKES_DIR
        old_transactions = siatakes.TAKE_MIGRATION_TX_DIR
        with tempfile.TemporaryDirectory() as root:
            siatakes.TAKES_DIR = os.path.join(root, "takes")
            siatakes.TAKE_MIGRATION_TX_DIR = os.path.join(
                root, "take-migrations")
            try:
                nfd_claim = unicodedata.normalize("NFD", "café held")
                fixtures = [
                    self._head_v1_take(
                        siatakes.TAKES_DIR, claim="slash domain held",
                        deadline="2026-08-30", domain="linux/audio",
                        justification="[[model/forged]] <img src=x>"),
                    self._head_v1_take(
                        siatakes.TAKES_DIR, claim="invalid deadline held",
                        deadline="yesterday", domain="general",
                        status="resolved-false"),
                    self._head_v1_take(
                        siatakes.TAKES_DIR, claim=nfd_claim,
                        deadline="2026-08-30", domain="general",
                        status="unresolvable", justification=""),
                    self._head_v1_take(
                        siatakes.TAKES_DIR, claim="open legacy prediction",
                        deadline="not-a-date", domain="spaced domain",
                        status="open", links=("operator/source",)),
                    self._head_v1_take(
                        siatakes.TAKES_DIR, claim="blank legacy deadline",
                        deadline=" ", domain="general", status="open"),
                ]
                signed_rows = []
                fake_sialib = types.SimpleNamespace(
                    ledger_contains=lambda *row: row in signed_rows,
                    ledger_append=lambda *row, **_kwargs: signed_rows.append(row))
                with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                    migrated, errors = siatakes.migrate_legacy_take_pages()
                self.assertEqual(errors, [])
                self.assertEqual(set(migrated), {
                    fixture[0]["id"] for fixture in fixtures})
                self.assertEqual(len(signed_rows), len(fixtures))
                self.assertTrue(all(
                    row[2] == "legacy-v1-normalize" for row in signed_rows))
                loaded = siatakes.load_takes()
                self.assertTrue(all(row["status"] != "invalid-record"
                                    for row in loaded))
                by_id = {row["id"]: row for row in loaded}
                for meta, path, source in fixtures:
                    row = by_id[meta["id"]]
                    target = _read_path(path)
                    expected_origin = ("derived" if meta["status"] == "open"
                                       else "model")
                    self.assertIn(f"\norigin: {expected_origin}\n", target)
                    self.assertEqual(
                        row["legacy_v1"]["source_sha256"],
                        hashlib.sha256(source.encode()).hexdigest())
                    self.assertRegex(row["domain"], siatakes._DOMAIN_RE)
                    siatakes.datetime.date.fromisoformat(row["deadline"])
                hostile_target = _read_path(fixtures[0][1])
                self.assertNotIn("[[model/forged]]", hostile_target)
                self.assertIn("⟦⟦model/forged⟧⟧", hostile_target)
                linked_open_target = _read_path(fixtures[-2][1])
                self.assertIn("[[operator/source]]", linked_open_target)
                blocked = [row for row in loaded
                           if isinstance(row.get("legacy_v1"), dict)
                           and row["legacy_v1"].get("deadline_state")
                           == "invalid-open-blocked"]
                self.assertEqual(len(blocked), 2)
                self.assertTrue(all(row not in siatakes.due_takes(loaded)
                                    for row in blocked))
                for row in blocked:
                    with mock.patch.object(siatakes, "_recall") as recall, \
                            mock.patch.object(siatakes, "_judge_run") as judge:
                        with self.assertRaisesRegex(
                                ValueError, "repair it before grading"):
                            siatakes.grade_take(row)
                    recall.assert_not_called()
                    judge.assert_not_called()
                self.assertFalse(siatakes.take_migration_required())
            finally:
                siatakes.TAKES_DIR = old_takes
                siatakes.TAKE_MIGRATION_TX_DIR = old_transactions

    def test_near_miss_v1_grade_refuses_without_sign_or_mutation(self):
        old_takes = siatakes.TAKES_DIR
        old_transactions = siatakes.TAKE_MIGRATION_TX_DIR
        with tempfile.TemporaryDirectory() as root:
            siatakes.TAKES_DIR = os.path.join(root, "takes")
            siatakes.TAKE_MIGRATION_TX_DIR = os.path.join(
                root, "take-migrations")
            try:
                _meta, path, source = self._head_v1_take(
                    siatakes.TAKES_DIR, claim="visible binding",
                    deadline="yesterday", domain="linux/audio")
                malformed = source.replace(
                    "**Claim:** visible binding",
                    "**Claim:** different visible text")
                _write(path, malformed)
                append = mock.Mock()
                fake_sialib = types.SimpleNamespace(
                    ledger_contains=lambda *_row: False,
                    ledger_append=append)
                with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                    migrated, errors = siatakes.migrate_legacy_take_pages()
                self.assertEqual(migrated, [])
                self.assertEqual(len(errors), 1)
                append.assert_not_called()
                self.assertEqual(_read_path(path), malformed)
                self.assertFalse(os.path.exists(
                    siatakes.TAKE_MIGRATION_TX_DIR))
                with self.assertRaisesRegex(ValueError, "producer shape"):
                    siatakes.take_migration_required()
            finally:
                siatakes.TAKES_DIR = old_takes
                siatakes.TAKE_MIGRATION_TX_DIR = old_transactions

    def test_recall_infrastructure_failure_leaves_due_take_open(self):
        take = {"id": "a" * 20, "claim": "the event occurs",
                "confidence": 0.7, "created": "2026-01-01T00:00:00Z",
                "deadline": "2026-01-02", "status": "open"}
        before = dict(take)
        persist = mock.Mock()
        recall_failure = siatakes.RecallEvidence(
            False, "", frozenset(),
            "grading recall query did not complete successfully")
        with mock.patch.object(
                siatakes, "_recall", return_value=recall_failure), \
                mock.patch.object(siatakes, "_organ_evidence") as organs, \
                mock.patch.object(siatakes, "_judge_run") as judge:
            with self.assertRaises(siatakes.GradingEvidenceUnavailable):
                siatakes.grade_take(take, persist=persist)
        self.assertEqual(take, before)
        persist.assert_not_called()
        organs.assert_not_called()
        judge.assert_not_called()

    def test_malformed_recall_row_is_an_infrastructure_refusal(self):
        result = type("Result", (), {
            "returncode": 0, "stdout": "[17]", "stderr": ""})()
        with mock.patch.object(
                sys.modules["sialib"], "gbrain", return_value=result):
            recalled = siatakes._recall("what happened")
        self.assertFalse(recalled.completed)
        self.assertEqual(recalled.text, "")
        self.assertIn("could not be admitted", recalled.reason)

    def test_cited_page_reopen_failure_leaves_due_take_open(self):
        take = {"id": "a" * 20, "claim": "the event occurs",
                "confidence": 0.7, "created": "2026-01-01T00:00:00Z",
                "deadline": "2026-01-02", "status": "open"}
        before = dict(take)
        persist = mock.Mock()
        judge = mock.Mock()
        recall = siatakes.RecallEvidence(
            True, "[events/journal/missing] observed event",
            frozenset({"events/journal/missing"}))
        with tempfile.TemporaryDirectory() as corpus:
            _write(os.path.join(corpus, "events/journal/missing.md"),
                   "observed event\n")
            with mock.patch.object(siatakes, "CORPUS", corpus), \
                    mock.patch.object(siatakes, "_recall",
                                      return_value=recall), \
                    mock.patch.object(siatakes, "_organ_evidence",
                                      return_value=("", set())), \
                    mock.patch.object(siatakes, "_read_regular_text",
                                      side_effect=OSError("reopen failed")), \
                    mock.patch.object(siatakes, "_judge_run", judge):
                with self.assertRaisesRegex(
                        siatakes.GradingEvidenceUnavailable,
                        "could not be re-opened"):
                    siatakes.grade_take(take, persist=persist)
        self.assertEqual(take, before)
        persist.assert_not_called()
        judge.assert_not_called()

    def test_stale_cited_excerpt_leaves_due_take_open(self):
        take = {"id": "a" * 20, "claim": "the event occurs",
                "confidence": 0.7, "created": "2026-01-01T00:00:00Z",
                "deadline": "2026-01-02", "status": "open"}
        persist = mock.Mock()
        judge = mock.Mock()
        recall = siatakes.RecallEvidence(
            True, "[events/journal/day] stale indexed excerpt",
            frozenset({"events/journal/day"}))
        with tempfile.TemporaryDirectory() as corpus:
            _write(os.path.join(corpus, "events/journal/day.md"),
                   "# current page\n\ndifferent evidence\n")
            with mock.patch.object(siatakes, "CORPUS", corpus), \
                    mock.patch.object(siatakes, "_recall",
                                      return_value=recall), \
                    mock.patch.object(siatakes, "_organ_evidence",
                                      return_value=("", set())), \
                    mock.patch.object(siatakes, "_judge_run", judge):
                with self.assertRaisesRegex(
                        siatakes.GradingEvidenceUnavailable, "excerpt is stale"):
                    siatakes.grade_take(take, persist=persist)
        persist.assert_not_called()
        judge.assert_not_called()

    def test_audit_reports_recall_refusal_without_running_judge(self):
        recall_failure = siatakes.RecallEvidence(
            False, "", frozenset(), "grading recall unavailable")
        with mock.patch.object(
                siatakes, "_recall", return_value=recall_failure), \
                mock.patch.object(siatakes, "_judge_run") as judge:
            verdict, reason = siatakes.judge_claim("the event occurs")
        self.assertIsNone(verdict)
        self.assertIn("recall unavailable", reason)
        judge.assert_not_called()

    def test_grade_refuses_take_changed_while_judge_runs(self):
        old_dir = siatakes.TAKES_DIR
        with tempfile.TemporaryDirectory() as takes_dir:
            siatakes.TAKES_DIR = takes_dir
            try:
                deadline = (siatakes._utcnow()
                            + siatakes.datetime.timedelta(days=1)) \
                    .strftime("%Y-%m-%d")
                siatakes.create_take("stable claim", deadline=deadline)
                take = siatakes.load_takes()[0]

                def mutate_then_judge(*_args, **_kwargs):
                    with open(take["path"], "a") as stream:
                        stream.write("\nconcurrent edit\n")
                    return ("VERDICT: UNRESOLVABLE\n"
                            "JUSTIFICATION: no witness", None,
                            "claude:claude-opus-5")

                def persist(row, verdict, justification, snapshots):
                    siatakes._render_take_page(
                        row, verdict, justification, snapshots)

                with mock.patch.object(
                        siatakes, "_grading_evidence",
                        return_value=("", set(), [])), \
                        mock.patch.object(
                            siatakes, "_judge_run",
                            side_effect=mutate_then_judge):
                    with self.assertRaisesRegex(ValueError,
                                                "changed while the judge"):
                        siatakes.grade_take(take, persist=persist)
            finally:
                siatakes.TAKES_DIR = old_dir

    def test_grade_refuses_visible_claim_changed_before_judge(self):
        old_dir = siatakes.TAKES_DIR
        with tempfile.TemporaryDirectory() as takes_dir:
            siatakes.TAKES_DIR = takes_dir
            try:
                deadline = (siatakes._utcnow()
                            + siatakes.datetime.timedelta(days=1)) \
                    .strftime("%Y-%m-%d")
                siatakes.create_take("metadata claim", deadline=deadline)
                take = siatakes.load_takes()[0]
                with open(take["path"]) as stream:
                    text = stream.read()
                with open(take["path"], "w") as stream:
                    stream.write(text.replace(
                        "**Claim:** metadata claim",
                        "**Claim:** different visible claim"))

                with mock.patch.object(siatakes, "_judge_run") as judge:
                    with self.assertRaisesRegex(
                            ValueError,
                            "visible-take-fields-do-not-match-metadata"):
                        siatakes.grade_take(
                            take, persist=lambda *_args: None)
                judge.assert_not_called()
                invalid = siatakes.load_takes()
                self.assertEqual(invalid[0]["status"], "invalid-record")
                self.assertIn("visible-take-fields",
                              invalid[0]["invalid_reason"])
            finally:
                siatakes.TAKES_DIR = old_dir

    def test_codex_judge_refuses_without_documented_no_tool_mode(self):
        with mock.patch.object(siatakes, "_judge_config",
                               return_value=("codex", "")), \
                mock.patch.object(siatakes.subprocess, "run") as run:
            text, error = siatakes._judge_run("untrusted evidence")
        self.assertIsNone(text)
        self.assertIn("grading refused", error)
        run.assert_not_called()

    def test_organ_evidence_refuses_incomplete_directory_snapshot(self):
        with tempfile.TemporaryDirectory() as corpus:
            directory = os.path.join(corpus, "events/journal")
            _write(os.path.join(directory, "junk-a"), "x")
            _write(os.path.join(directory, "junk-b"), "x")
            with mock.patch.object(siatakes, "CORPUS", corpus), \
                    mock.patch.object(
                        siatakes, "MAX_HISTORY_BASELINE_SCAN", 1), \
                    self.assertRaisesRegex(
                        siatakes.GradingEvidenceUnavailable,
                        "complete bounded snapshot"):
                siatakes._organ_evidence("journal remains quiet")

    def test_organ_evidence_refuses_directory_change_after_page_read(self):
        with tempfile.TemporaryDirectory() as corpus:
            directory = os.path.join(corpus, "events/journal")
            page = os.path.join(directory, "2026-08-30.md")
            _write(page, "observed journal evidence")
            read = siatakes._read_regular_text

            def mutate_after_read(path):
                text = read(path)
                _write(os.path.join(directory, "concurrent.md"), "changed")
                return text

            with mock.patch.object(siatakes, "CORPUS", corpus), \
                    mock.patch.object(
                        siatakes, "_read_regular_text",
                        side_effect=mutate_after_read), \
                    self.assertRaisesRegex(
                        siatakes.GradingEvidenceUnavailable,
                        "changed while reading"):
                siatakes._organ_evidence("journal remains quiet")

    def test_unverified_jackal_pages_cannot_resolve_a_take(self):
        with tempfile.TemporaryDirectory() as corpus:
            event_slug = "events/jackal/2026-08-30"
            epoch_slug = "epochs/jackal/2026-W35"
            _write(os.path.join(corpus, event_slug + ".md"),
                   "unverified result ledger row")
            _write(os.path.join(corpus, epoch_slug + ".md"),
                   "unverified aggregate")
            with mock.patch.object(siatakes, "CORPUS", corpus):
                self.assertFalse(siatakes._admitted_evidence_slug(event_slug))
                self.assertFalse(siatakes._admitted_evidence_slug(epoch_slug))
                self.assertEqual(
                    siatakes._organ_evidence(
                        "JACKAL will report a result", with_citations=True),
                    ("", set()))
                take = {
                    "id": "fixture", "claim": "JACKAL will report a result",
                    "confidence": 0.8, "deadline": "2099-01-01",
                    "created": "2026-08-30T00:00:00Z", "status": "open",
                    "domain": "math", "source": "sia/cortex",
                }
                persisted = []
                with mock.patch.object(
                        siatakes, "_recall",
                        return_value=siatakes.RecallEvidence(
                            True, "", frozenset())), \
                        mock.patch.object(
                            siatakes, "_judge_run",
                            return_value=(
                                "VERDICT: TRUE\nJUSTIFICATION: guessed",
                                "", "fixture-judge")):
                    graded = siatakes.grade_take(
                        take, persist=lambda *args: persisted.append(args))
            self.assertEqual(graded["status"], "unresolvable")
            self.assertIsNone(graded["outcome"])
            self.assertEqual(persisted[0][1], "UNRESOLVABLE")


class NaturalHistoryProjection(unittest.TestCase):
    @contextlib.contextmanager
    def projection_roots(self, root):
        with mock.patch.object(
                siatakes, "TAKES_DIR", os.path.join(root, "takes")), \
                mock.patch.object(
                    siatakes, "INTENTS_DIR", os.path.join(root, "intents")), \
                mock.patch.object(
                    siatakes, "GRADE_TX_DIR", os.path.join(root, "grades")), \
                mock.patch.object(
                    siatakes, "TAKE_MIGRATION_TX_DIR",
                    os.path.join(root, "migrations")):
            yield

    def graded_take(self, claim="authority fixture"):
        made = siatakes.create_take(
            claim, confidence=0.8, deadline="2099-01-01")
        take = siatakes.get_take(made["id"])
        source = _read_path(take["path"])
        take.update({
            "status": "resolved-true", "outcome": 1,
            "brier": siatakes.brier_score(0.8, 1),
            "graded": "2026-08-30T12:00:00Z",
            "judge_model": "claude:fixture",
            "_grade_source_sha256": hashlib.sha256(
                source.encode()).hexdigest(),
        })
        siatakes.commit_grade_transition(
            take, "TRUE", "fixture evidence")
        return siatakes.get_take(made["id"])

    def settle_authority(self, kind):
        attempts = []
        while siatakes.natural_history_debt(kind):
            attempts.append(True)
            self.assertLess(len(attempts), 20)
            if kind == "take":
                _changed, errors = siatakes.migrate_legacy_take_pages()
            else:
                _changed, errors = siatakes.advance_intent_history()
            self.assertEqual(errors, [])

    def test_external_take_deletion_retires_signed_contribution(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            signed = []
            fake_sialib = types.SimpleNamespace(
                ledger_contains=lambda *row: row in signed,
                ledger_append=lambda *row, **_kwargs: signed.append(row))
            with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                take = self.graded_take("deleted signed outcome")
                self.assertEqual(
                    siatakes.calibration_report()["overall"]["resolved"], 1)
                os.unlink(take["path"])
                self.assertTrue(siatakes.natural_history_debt("take"))
                with self.assertRaisesRegex(
                        ValueError, "authority reconciliation"):
                    siatakes.calibration_report()
                self.settle_authority("take")
            overall = siatakes.calibration_report()["overall"]
            self.assertEqual(overall["resolved"], 0)
            self.assertEqual(overall["invalid_resolved"], 0)
            self.assertIsNone(siatakes.get_take(take["id"]))
            self.assertEqual(siatakes.list_takes_page()["items"], [])

    def test_external_signed_page_edit_removes_and_exact_restore_rebuilds(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            signed = []
            fake_sialib = types.SimpleNamespace(
                ledger_contains=lambda *row: row in signed,
                ledger_append=lambda *row, **_kwargs: signed.append(row))
            with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                take = self.graded_take("edited signed outcome")
                signed_page = _read_path(take["path"])
                _write(take["path"], signed_page + "\n")
                changed, errors, _inspected = \
                    siatakes.audit_natural_history_authority(
                        "take", limit=1)
                self.assertEqual(errors, [])
                self.assertTrue(changed)
                self.assertTrue(siatakes.natural_history_debt("take"))
                with self.assertRaisesRegex(
                        ValueError, "authority reconciliation"):
                    siatakes.calibration_report()
                self.settle_authority("take")
                edited = siatakes.calibration_report()["overall"]
                self.assertEqual(edited["resolved"], 0)
                self.assertEqual(edited["invalid_resolved"], 1)

                _write(take["path"], signed_page)
                _changed, errors, _inspected = \
                    siatakes.audit_natural_history_authority(
                        "take", limit=1)
                self.assertEqual(errors, [])
                self.assertTrue(siatakes.natural_history_debt("take"))
                self.settle_authority("take")
            restored = siatakes.calibration_report()["overall"]
            self.assertEqual(restored["resolved"], 1)
            self.assertEqual(restored["invalid_resolved"], 0)

    def test_external_intent_resolution_reconciles_open_projection(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            made = siatakes.create_intent(
                "externally completed", "2099-01-01")
            intent = siatakes.get_intent(made["id"])
            source = _read_path(intent["path"])
            metadata = {key: value for key, value in intent.items()
                        if key not in ("slug", "path")}
            metadata.update({
                "status": "done", "closed": "2026-08-30T12:00:00Z",
                "note": "external authority",
            })
            target = re.sub(
                r"^sia_intent: .*$",
                "sia_intent: " + json.dumps(metadata, sort_keys=True),
                source, count=1, flags=re.M)
            _write(intent["path"], target)
            _changed, errors, _inspected = \
                siatakes.audit_natural_history_authority(
                    "intent", limit=1)
            self.assertEqual(errors, [])
            self.assertTrue(siatakes.natural_history_debt("intent"))
            self.settle_authority("intent")
            self.assertEqual(
                siatakes.get_intent(made["id"])["status"], "done")
            self.assertEqual(siatakes.open_intents(), [])

    def test_external_unsigned_take_resolution_leaves_score_denominator(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            made = siatakes.create_take(
                "externally resolved", confidence=0.8,
                deadline="2099-01-01")
            take = siatakes.get_take(made["id"])
            source = _read_path(take["path"])
            take.update({
                "status": "resolved-false", "outcome": 0,
                "brier": siatakes.brier_score(0.8, 0),
                "graded": "2026-08-30T12:00:00Z",
                "judge_model": "claude:external",
                "_grade_source_sha256": hashlib.sha256(
                    source.encode()).hexdigest(),
            })
            _path, _source, target = siatakes._render_take_page(
                take, "FALSE", "external bytes have no signed grade")
            _write(take["path"], target)
            fake_sialib = types.SimpleNamespace(
                ledger_contains=lambda *_row: False)
            with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                _changed, errors, _inspected = \
                    siatakes.audit_natural_history_authority(
                        "take", limit=1)
                self.assertEqual(errors, [])
                self.assertTrue(siatakes.natural_history_debt("take"))
                self.settle_authority("take")
            overall = siatakes.calibration_report()["overall"]
            self.assertEqual(overall["open"], 0)
            self.assertEqual(overall["resolved"], 0)
            self.assertEqual(overall["invalid_resolved"], 1)

    def test_external_malformed_take_retires_resolved_score_as_invalid(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            signed = []
            fake_sialib = types.SimpleNamespace(
                ledger_contains=lambda *row: row in signed,
                ledger_append=lambda *row, **_kwargs: signed.append(row))
            with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                take = self.graded_take("malformed authority")
                _write(take["path"], "malformed corpus bytes\n")
                _changed, errors, _inspected = \
                    siatakes.audit_natural_history_authority(
                        "take", limit=1)
                self.assertEqual(errors, [])
                self.settle_authority("take")
            overall = siatakes.calibration_report()["overall"]
            self.assertEqual(overall["resolved"], 0)
            self.assertEqual(overall["invalid_records"], 1)
            page = siatakes.list_takes_page()["items"]
            self.assertEqual(len(page), 1)
            self.assertEqual(page[0]["status"], "invalid-record")

    def test_authority_cursor_schema_is_fixed_and_bounded(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            state = siatakes._history_initial_state("take")
            state["authority"]["cursor"] = {
                "cookie": 0, "unbounded": 0}
            with self.assertRaisesRegex(ValueError,
                                        "generation is invalid"):
                siatakes._validate_history_state(state, "take")

            legacy = siatakes._history_initial_state("take")
            legacy["next_catalog"] = 1
            legacy["authority"]["audit_cursor"] = 1
            legacy["authority"].pop("audit_limit")
            migrated = siatakes._validate_history_state(legacy, "take")
            self.assertEqual(migrated["authority"]["audit_cursor"], 0)
            self.assertEqual(migrated["authority"]["audit_limit"], 0)

            interrupted = siatakes._history_initial_state("take")
            interrupted["next_catalog"] = 1
            interrupted["authority"].update({
                "complete": False, "phase": "scan", "audit_cursor": 1,
                "checkpoint": {},
            })
            interrupted["authority"].pop("audit_limit")
            migrated = siatakes._validate_history_state(
                interrupted, "take")
            self.assertEqual(migrated["authority"]["audit_cursor"], 0)

            malformed = siatakes._history_initial_state("take")
            malformed["next_catalog"] = 1
            malformed["authority"]["audit_limit"] = 1
            with self.assertRaisesRegex(ValueError, "phase cursor"):
                siatakes._validate_history_state(malformed, "take")

    def test_stable_advance_completes_one_explicit_audit_generation(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            siatakes.create_intent("stable checkpoint", "2099-01-01")
            # The paired audit scheduler observes both ready authorities before
            # entering a new cycle; establish the empty sibling before the
            # assertion forbids any directory-page helper call.
            siatakes._load_history_state("take", create=True)
            state_path = siatakes._history_paths("intent")["state"]
            before = siatakes._load_history_state("intent")
            with mock.patch.object(
                    siatakes, "_bounded_history_entries",
                    side_effect=AssertionError(
                        "direct audit must not launch a corpus scan")):
                changed, errors = \
                    siatakes.advance_natural_history_authority("intent")
            self.assertEqual(changed, [])
            self.assertEqual(errors, [])
            after = siatakes._load_history_state("intent")
            self.assertEqual(
                after["authority"]["generation"],
                before["authority"]["generation"] + 1)
            self.assertEqual(after["authority"]["phase"], "ready")
            self.assertTrue(after["authority"]["complete"])
            self.assertEqual(after["authority"]["audit_cursor"], 0)
            self.assertEqual(after["authority"]["audit_limit"], 0)
            self.assertFalse(siatakes.natural_history_debt("intent"))

    def test_partial_audit_closes_calibration_before_later_changed_row(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            signed = []
            fake_sialib = types.SimpleNamespace(
                ledger_contains=lambda *row: row in signed,
                ledger_append=lambda *row, **_kwargs: signed.append(row))
            with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                first = self.graded_take("first pinned audit row")
                second = self.graded_take("changed beyond first audit slice")
                self.assertEqual(
                    siatakes.calibration_report()["overall"]["resolved"], 2)
                _write(second["path"], _read_path(second["path"]) + "\n")
                # Same-inode edits after the prior checkpoint are outside the
                # stated instantaneous-detection claim until an audit starts.
                self.assertFalse(siatakes.natural_history_debt("take"))

                before = siatakes._load_history_state("take")
                audited, errors, inspected = \
                    siatakes.audit_natural_history_authority(
                        "take", limit=1)
                self.assertEqual(errors, [])
                self.assertEqual(inspected, 1)
                self.assertEqual(audited, [first["id"]])
                partial = siatakes._load_history_state("take")
                self.assertEqual(partial["authority"]["phase"], "audit")
                self.assertFalse(partial["authority"]["complete"])
                self.assertEqual(partial["authority"]["audit_cursor"], 1)
                self.assertEqual(partial["authority"]["audit_limit"], 2)
                self.assertEqual(
                    partial["authority"]["generation"],
                    before["authority"]["generation"] + 1)
                self.assertTrue(siatakes.natural_history_debt("take"))
                with self.assertRaisesRegex(
                        ValueError, "authority reconciliation"):
                    siatakes.calibration_report()

                changed, audit_errors, changed_inspected = \
                    siatakes.audit_natural_history_authority(
                        "take", limit=1)
                self.assertEqual(audit_errors, [])
                self.assertEqual(changed_inspected, 1)
                self.assertEqual(changed, [second["id"]])
                self.assertEqual(
                    siatakes._load_history_state(
                        "take")["authority"]["phase"], "scan")
                self.settle_authority("take")

            overall = siatakes.calibration_report()["overall"]
            self.assertEqual(overall["resolved"], 1)
            self.assertEqual(overall["invalid_resolved"], 1)

    def test_audit_crash_resumes_pinned_cursor_limit_and_generation(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            for text in ("first", "second", "third"):
                siatakes.create_intent(text, "2099-01-01")
            _audited, errors, inspected = \
                siatakes.audit_natural_history_authority(
                    "intent", limit=1)
            self.assertEqual(errors, [])
            self.assertEqual(inspected, 1)
            pinned = siatakes._load_history_state("intent")["authority"]
            self.assertEqual(pinned["phase"], "audit")
            self.assertEqual(pinned["audit_cursor"], 1)
            real_save = siatakes._save_history_state
            failed = []

            def crash_on_second_cursor(kind, state):
                authority = state["authority"]
                if kind == "intent" and authority["phase"] == "audit" \
                        and authority["audit_cursor"] == 2 and not failed:
                    failed.append(True)
                    raise RuntimeError("simulated audit progress crash")
                return real_save(kind, state)

            with mock.patch.object(
                    siatakes, "_save_history_state",
                    side_effect=crash_on_second_cursor), \
                    self.assertRaisesRegex(
                        RuntimeError, "audit progress crash"):
                siatakes.audit_natural_history_authority(
                    "intent", limit=1)
            after_crash = siatakes._load_history_state(
                "intent")["authority"]
            for field in ("generation", "audit_limit", "audit_cursor",
                          "checkpoint"):
                self.assertEqual(after_crash[field], pinned[field])
            _audited, retry_errors, retry_inspected = \
                siatakes.audit_natural_history_authority(
                    "intent", limit=1)
            self.assertEqual(retry_errors, [])
            self.assertEqual(retry_inspected, 1)
            resumed = siatakes._load_history_state("intent")["authority"]
            self.assertEqual(resumed["generation"], pinned["generation"])
            self.assertEqual(resumed["audit_limit"], pinned["audit_limit"])
            self.assertEqual(resumed["audit_cursor"], 2)
            self.assertTrue(siatakes.natural_history_debt("intent"))

    def test_append_after_pre_ready_crash_cannot_certify_pinned_limit(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            siatakes.create_intent("before audit", "2099-01-01")
            before_generation = siatakes._load_history_state(
                "intent")["authority"]["generation"]
            real_save = siatakes._save_history_state
            failed = []

            def crash_before_ready(kind, state):
                authority = state["authority"]
                if kind == "intent" and authority["phase"] == "ready" \
                        and authority["generation"] > before_generation \
                        and not failed:
                    failed.append(True)
                    raise RuntimeError("simulated pre-ready crash")
                return real_save(kind, state)

            with mock.patch.object(
                    siatakes, "_save_history_state",
                    side_effect=crash_before_ready), \
                    self.assertRaisesRegex(
                        RuntimeError, "pre-ready crash"):
                siatakes.audit_natural_history_authority(
                    "intent", limit=1)
            pinned = siatakes._load_history_state("intent")["authority"]
            self.assertEqual(pinned["phase"], "audit")
            self.assertEqual(pinned["audit_cursor"], pinned["audit_limit"])
            self.assertTrue(siatakes.natural_history_debt("intent"))

            # Model a supported append whose caller passed its readiness gate
            # immediately before the audit transition became visible.
            with mock.patch.object(
                    siatakes, "natural_history_debt", return_value=False):
                siatakes.create_intent("append during audit", "2099-01-01")
            appended = siatakes._load_history_state("intent")
            self.assertEqual(appended["next_catalog"], 2)
            self.assertEqual(appended["authority"]["phase"], "scan")
            self.assertFalse(appended["authority"]["complete"])
            self.assertGreater(
                appended["authority"]["generation"], pinned["generation"])
            self.assertTrue(siatakes.natural_history_debt("intent"))
            self.settle_authority("intent")
            ready = siatakes._load_history_state("intent")
            self.assertEqual(ready["next_catalog"], 2)
            self.assertEqual(ready["authority"]["phase"], "ready")

    def test_pending_transaction_prevents_audit_ready_publication(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            siatakes.create_intent("pending at audit cut", "2099-01-01")
            pending = siatakes._history_paths("intent")["pending"]
            _write(pending, "{}")
            _audited, errors, inspected = \
                siatakes.audit_natural_history_authority(
                    "intent", limit=1)
            self.assertEqual(errors, [])
            self.assertEqual(inspected, 1)
            state = siatakes._load_history_state("intent")
            self.assertEqual(state["authority"]["phase"], "scan")
            self.assertFalse(state["authority"]["complete"])
            self.assertTrue(siatakes.natural_history_debt("intent"))
            os.unlink(pending)
            self.settle_authority("intent")
            self.assertFalse(siatakes.natural_history_debt("intent"))

    def test_supported_mutation_dirties_authority_before_page_write(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            made = siatakes.create_intent(
                "dirty before mutation", "2099-01-01")
            intent = siatakes.get_intent(made["id"])
            atomic = siatakes._atomic_text
            failed = []

            def crash_at_page(path, text, *args, **kwargs):
                if path == intent["path"] and not failed:
                    failed.append(True)
                    state = siatakes._load_history_state("intent")
                    self.assertFalse(state["authority"]["complete"])
                    raise RuntimeError("simulated page publication crash")
                return atomic(path, text, *args, **kwargs)

            with mock.patch.object(
                    siatakes, "_atomic_text", side_effect=crash_at_page), \
                    self.assertRaisesRegex(
                        RuntimeError, "page publication crash"):
                siatakes.close_intent(made["id"], "done")
            self.assertTrue(
                siatakes.natural_history_recovery_required("intent"))
            recovered, errors = \
                siatakes.recover_natural_history_transactions()
            self.assertEqual(errors, [])
            self.assertEqual(recovered, [made["id"]])
            self.assertFalse(siatakes.natural_history_debt("intent"))
            self.assertEqual(
                siatakes.get_intent(made["id"])["status"], "done")

    def test_exact_open_page_replacement_refreshes_identity_without_event(self):
        for kind in ("take", "intent"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as root, \
                    self.projection_roots(root):
                if kind == "take":
                    made = siatakes.create_take(
                        "exact replacement", confidence=0.8,
                        deadline="2099-01-01")
                    row = siatakes.get_take(made["id"])
                else:
                    made = siatakes.create_intent(
                        "exact replacement", "2099-01-01")
                    row = siatakes.get_intent(made["id"])
                self.assertFalse(siatakes.natural_history_debt(kind))
                before_state = copy.deepcopy(
                    siatakes._load_history_state(kind))
                before_direct = copy.deepcopy(
                    siatakes._history_direct(kind, row["id"]))
                before_open = copy.deepcopy(
                    before_state["open"][row["id"]])
                text = _read_path(row["path"])
                replacement = row["path"] + ".replacement"
                _write(replacement, text)
                os.replace(replacement, row["path"])
                current_info = os.stat(row["path"], follow_symlinks=False)
                self.assertNotEqual(current_info.st_ino,
                                    before_open["inode"])
                self.assertTrue(siatakes.natural_history_debt(kind))

                with mock.patch.object(
                        siatakes, "_history_mark_direct_generation",
                        side_effect=RuntimeError(
                            "crash after open identity refresh")):
                    changed, errors = \
                        siatakes.advance_natural_history_authority(kind)
                self.assertEqual(changed, [])
                self.assertIn("open identity refresh", errors[0]["error"])
                crashed = siatakes._load_history_state(kind)
                projected = crashed["open"][row["id"]]
                self.assertEqual(
                    (projected["device"], projected["inode"],
                     projected["size"], projected["mtime_ns"],
                     projected["ctime_ns"]),
                    (current_info.st_dev, current_info.st_ino,
                     current_info.st_size, current_info.st_mtime_ns,
                     current_info.st_ctime_ns))
                self.assertTrue(siatakes.natural_history_debt(kind))
                self.assertEqual(crashed["next_event"],
                                 before_state["next_event"])
                self.assertEqual(crashed["applied_event"],
                                 before_state["applied_event"])
                self.assertEqual(crashed["overall"], before_state["overall"])
                crashed_direct = siatakes._history_direct(kind, row["id"])
                for field in ("event_id", "event_sequence", "page_sha256",
                              "catalog_index", "signed_grade"):
                    self.assertEqual(crashed_direct[field],
                                     before_direct[field])

                attempts = []
                while siatakes.natural_history_debt(kind):
                    attempts.append(True)
                    self.assertLess(len(attempts), 20)
                    changed, retry_errors = \
                        siatakes.advance_natural_history_authority(kind)
                    self.assertEqual(changed, [])
                    self.assertEqual(retry_errors, [])
                ready = siatakes._load_history_state(kind)
                self.assertEqual(ready["authority"]["phase"], "ready")
                self.assertEqual(ready["next_event"],
                                 before_state["next_event"])
                self.assertEqual(ready["applied_event"],
                                 before_state["applied_event"])
                self.assertEqual(ready["overall"], before_state["overall"])
                final_direct = siatakes._history_direct(kind, row["id"])
                for field in ("event_id", "event_sequence", "page_sha256",
                              "catalog_index", "signed_grade"):
                    self.assertEqual(final_direct[field],
                                     before_direct[field])

    def test_transient_intent_baseline_race_clears_on_quiescent_retry(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            intent_id = "0000000001"
            created = "2026-08-30T00:00:00Z"
            metadata = {
                "id": intent_id, "text": "retry bounded baseline",
                "due": "2099-01-01", "holder": "user", "status": "open",
                "created": created, "closed": None, "note": None,
            }
            path = os.path.join(
                siatakes.INTENTS_DIR, f"{created[:10]}-{intent_id}.md")
            _write(path, "---\ntype: intent\n"
                   f"sia_intent: {json.dumps(metadata, sort_keys=True)}\n"
                   "---\nretry intent\n")
            siatakes._load_history_state("intent", create=True)
            with mock.patch.object(
                    siatakes, "_bounded_history_entries",
                    side_effect=RuntimeError("transient bounded scan race")):
                imported, errors = siatakes.advance_intent_history()
            self.assertEqual(imported, [])
            self.assertIn("bounded scan race", errors[0]["error"])
            failed = siatakes._load_history_state("intent")
            self.assertTrue(failed["legacy"]["external_debt"])
            self.assertIn("bounded scan race", failed["legacy"]["error"])
            self.assertTrue(siatakes.intent_history_required())

            attempts = []
            while siatakes.intent_history_required():
                attempts.append(True)
                self.assertLess(len(attempts), 20)
                _imported, retry_errors = siatakes.advance_intent_history()
                self.assertEqual(retry_errors, [])
            recovered = siatakes._load_history_state("intent")
            self.assertFalse(recovered["legacy"]["external_debt"])
            self.assertNotIn("error", recovered["legacy"])
            self.assertEqual(siatakes.get_intent(intent_id)["text"],
                             metadata["text"])
            self.assertFalse(siatakes.natural_history_debt("intent"))

    def test_invalid_utf8_cannot_alias_signed_replacement_character(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            signed, ledger_calls = [], []

            def ledger_contains(*row):
                ledger_calls.append(("contains", row))
                return row in signed

            def ledger_append(*row, **_kwargs):
                ledger_calls.append(("append", row))
                signed.append(row)

            fake_sialib = types.SimpleNamespace(
                ledger_contains=ledger_contains, ledger_append=ledger_append)
            with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                take = self.graded_take("literal replacement � target")
                legitimate = _read_path(take["path"])
                legitimate_bytes = legitimate.encode("utf-8")
                self.assertIn(b"\xef\xbf\xbd", legitimate_bytes)
                self.assertTrue(any(
                    "�" in row[-1] for row in signed
                    if row and isinstance(row[-1], str)))
                before_direct = copy.deepcopy(
                    siatakes._history_direct("take", take["id"]))
                before_stats = copy.deepcopy(
                    siatakes._load_history_state("take")["overall"])

                grade_dir = siatakes._grade_transaction_dir()
                migration_dir = siatakes._take_migration_transaction_dir()
                for directory in (grade_dir, migration_dir):
                    os.makedirs(directory, mode=0o700, exist_ok=True)
                    os.chmod(directory, 0o700)
                grade_journal = os.path.join(grade_dir, take["id"] + ".json")
                grade_value = siatakes._grade_tx_payload(
                    take, take["path"], legitimate, legitimate)
                _write(grade_journal, json.dumps(grade_value, sort_keys=True))
                os.chmod(grade_journal, 0o600)
                migration_journal = os.path.join(
                    migration_dir, take["id"] + ".json")
                migration_value = siatakes._take_migration_payload(
                    take, legitimate, legitimate, "model-inert-v1",
                    grade_observed=True)
                _write(migration_journal,
                       json.dumps(migration_value, sort_keys=True))
                os.chmod(migration_journal, 0o600)

                invalid = legitimate_bytes.replace(
                    b"\xef\xbf\xbd", b"\xff")
                replacement = take["path"] + ".replacement"
                with open(replacement, "wb") as stream:
                    stream.write(invalid)
                os.replace(replacement, take["path"])
                calls_before_refusal = list(ledger_calls)

                _changed, authority_errors = \
                    siatakes.advance_natural_history_authority("take")
                self.assertIn("not valid UTF-8",
                              authority_errors[0]["error"])
                grade_recovered, grade_errors = \
                    siatakes.recover_grade_transactions()
                self.assertEqual(grade_recovered, [])
                self.assertIn("not valid UTF-8", grade_errors[0]["error"])
                migration_recovered, migration_errors = \
                    siatakes.recover_take_migrations()
                self.assertEqual(migration_recovered, [])
                self.assertIn("not valid UTF-8",
                              migration_errors[0]["error"])
                self.assertEqual(ledger_calls, calls_before_refusal)
                self.assertTrue(siatakes.natural_history_debt("take"))
                self.assertTrue(siatakes.grade_recovery_required())
                self.assertTrue(siatakes.take_migration_required())
                after_direct = siatakes._history_direct("take", take["id"])
                self.assertEqual(after_direct, before_direct)
                self.assertEqual(
                    siatakes._load_history_state("take")["overall"],
                    before_stats)

                private_invalid = os.path.join(grade_dir, "private-invalid.json")
                with open(private_invalid, "wb") as stream:
                    stream.write(b'{"target":"\xff"}')
                os.chmod(private_invalid, 0o600)
                with self.assertRaisesRegex(ValueError, "not valid UTF-8"):
                    siatakes._read_transaction_json(private_invalid)

    def test_pinned_audit_advances_tombstones_but_keeps_partial_debt(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            intents = [siatakes.create_intent(text, "2099-01-01")
                       for text in ("first", "second", "third")]
            second = siatakes.get_intent(intents[1]["id"])
            os.unlink(second["path"])
            self.settle_authority("intent")
            validate = siatakes._history_validate_direct
            seen, cursors = [], []

            def observe(record):
                seen.append(record["key"])
                return validate(record)

            with mock.patch.object(
                    siatakes, "_history_validate_direct",
                    side_effect=observe):
                for index, _expected in enumerate(intents):
                    _audited, errors, inspected = \
                        siatakes.audit_natural_history_authority(
                            "intent", limit=1)
                    self.assertEqual(errors, [])
                    self.assertEqual(inspected, 1)
                    state = siatakes._load_history_state("intent")
                    self.assertEqual(
                        siatakes.natural_history_debt("intent"),
                        index < len(intents) - 1)
                    cursors.append(state["authority"]["audit_cursor"])
            self.assertEqual(seen, [intents[0]["id"], intents[2]["id"]])
            self.assertEqual(cursors, [1, 2, 0])

    def test_unequal_audit_catalogs_wait_for_shared_cycle_completion(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            fake_sialib = types.SimpleNamespace(
                ledger_contains=lambda *_row: False,
                ledger_append=lambda *_row, **_kwargs: None)
            with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                for claim in ("take first", "take second"):
                    siatakes.create_take(
                        claim, confidence=0.8, deadline="2099-01-01")
                for text in ("intent first", "intent second", "intent third"):
                    siatakes.create_intent(text, "2099-01-01")

                slower_limit = max(
                    siatakes._load_history_state(kind)["next_catalog"]
                    for kind in ("take", "intent"))
                waiting_generation = None
                with mock.patch.object(
                        siatakes, "MAX_HISTORY_BASELINE_SCAN", 1):
                    for _pulse in range(slower_limit):
                        _takes, take_errors = \
                            siatakes.migrate_legacy_take_pages()
                        _intents, intent_errors = \
                            siatakes.advance_intent_history(limit=1)
                        self.assertEqual(take_errors, [])
                        self.assertEqual(intent_errors, [])
                        take_authority = siatakes._load_history_state(
                            "take")["authority"]
                        intent_authority = siatakes._load_history_state(
                            "intent")["authority"]
                        if take_authority["phase"] == "ready" \
                                and intent_authority["phase"] == "audit":
                            if waiting_generation is None:
                                waiting_generation = \
                                    take_authority["generation"]
                            else:
                                self.assertEqual(
                                    take_authority["generation"],
                                    waiting_generation)

                self.assertIsNotNone(waiting_generation)
                self.assertFalse(siatakes.natural_history_debt("take"))
                self.assertFalse(siatakes.natural_history_debt("intent"))
                take_authority = siatakes._load_history_state(
                    "take")["authority"]
                intent_authority = siatakes._load_history_state(
                    "intent")["authority"]
                self.assertEqual(take_authority["phase"], "ready")
                self.assertEqual(intent_authority["phase"], "ready")
                self.assertEqual(
                    take_authority["audit_cycle"],
                    intent_authority["audit_cycle"])

    def test_paired_recovery_closes_interrupted_cycle_without_reopening(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            fake_sialib = types.SimpleNamespace(
                ledger_contains=lambda *_row: False,
                ledger_append=lambda *_row, **_kwargs: None)
            with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                siatakes.create_take(
                    "interrupted audit", confidence=0.8,
                    deadline="2099-01-01")
                siatakes.create_intent(
                    "interrupted audit follower", "2099-01-01")

                _audited, errors, inspected = \
                    siatakes.audit_natural_history_authority(
                        "intent", limit=1)
                self.assertEqual(errors, [])
                self.assertEqual(inspected, 1)
                interrupted_take = siatakes._load_history_state(
                    "take")["authority"]
                completed_intent = siatakes._load_history_state(
                    "intent")["authority"]
                self.assertEqual(interrupted_take["phase"], "audit")
                self.assertEqual(interrupted_take["audit_cursor"], 0)
                self.assertEqual(completed_intent["phase"], "ready")
                self.assertEqual(
                    interrupted_take["audit_cycle"],
                    completed_intent["audit_cycle"])

                _takes, take_errors = \
                    siatakes.migrate_legacy_take_pages()
                _intents, intent_errors = \
                    siatakes.advance_intent_history(
                        start_audit_cycle=False)
                self.assertEqual(take_errors, [])
                self.assertEqual(intent_errors, [])

                ready_take = siatakes._load_history_state(
                    "take")["authority"]
                ready_intent = siatakes._load_history_state(
                    "intent")["authority"]
                self.assertEqual(ready_take["phase"], "ready")
                self.assertEqual(ready_intent["phase"], "ready")
                self.assertEqual(
                    ready_take["audit_cycle"],
                    interrupted_take["audit_cycle"])
                self.assertEqual(
                    ready_intent["audit_cycle"],
                    interrupted_take["audit_cycle"])
                self.assertFalse(siatakes.natural_history_debt("take"))
                self.assertFalse(siatakes.natural_history_debt("intent"))

    def test_retirement_recovery_subtracts_exactly_once_after_tombstone(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            signed = []
            fake_sialib = types.SimpleNamespace(
                ledger_contains=lambda *row: row in signed,
                ledger_append=lambda *row, **_kwargs: signed.append(row))
            with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                take = self.graded_take("retirement crash")
                os.unlink(take["path"])
                domain_apply = siatakes._history_apply_domain
                failed = []

                def crash_after_tombstone(*args, **kwargs):
                    if not failed:
                        failed.append(True)
                        raise RuntimeError("simulated subtraction crash")
                    return domain_apply(*args, **kwargs)

                with mock.patch.object(
                        siatakes, "_history_apply_domain",
                        side_effect=crash_after_tombstone):
                    _changed, errors = \
                        siatakes.migrate_legacy_take_pages()
                self.assertEqual(len(errors), 1)
                direct = siatakes._history_direct("take", take["id"])
                self.assertTrue(direct["tombstone"])
                self.assertEqual(
                    siatakes._load_history_state(
                        "take")["overall"]["resolved"], 1)
                recovered, recovery_errors = \
                    siatakes.recover_natural_history_transactions()
                self.assertEqual(recovery_errors, [])
                self.assertEqual(recovered, [take["id"]])
                self.settle_authority("take")
            overall = siatakes.calibration_report()["overall"]
            self.assertEqual(overall["resolved"], 0)
            self.assertEqual(overall["invalid_resolved"], 0)

    def test_update_recovery_does_not_double_apply_new_contribution(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            signed = []
            fake_sialib = types.SimpleNamespace(
                ledger_contains=lambda *row: row in signed,
                ledger_append=lambda *row, **_kwargs: signed.append(row))
            with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                take = self.graded_take("update crash")
                _write(take["path"], _read_path(take["path"]) + "\n")
                _changed, audit_errors, _inspected = \
                    siatakes.audit_natural_history_authority("take")
                self.assertEqual(audit_errors, [])
                pending = siatakes._history_paths("take")["pending"]
                unlink = siatakes._unlink_durable
                failed = []

                def crash_before_ack(path):
                    if path == pending and not failed:
                        failed.append(True)
                        raise RuntimeError("simulated update ack crash")
                    return unlink(path)

                with mock.patch.object(
                        siatakes, "_unlink_durable",
                        side_effect=crash_before_ack):
                    _changed, errors = \
                        siatakes.advance_natural_history_authority("take")
                self.assertEqual(len(errors), 1)
                interim = siatakes._load_history_state("take")["overall"]
                self.assertEqual(interim["resolved"], 0)
                self.assertEqual(interim["invalid_resolved"], 1)
                recovered, recovery_errors = \
                    siatakes.recover_natural_history_transactions()
                self.assertEqual(recovery_errors, [])
                self.assertEqual(recovered, [take["id"]])
                self.settle_authority("take")
            overall = siatakes.calibration_report()["overall"]
            self.assertEqual(overall["resolved"], 0)
            self.assertEqual(overall["invalid_resolved"], 1)

    def test_transaction_journal_batch_refuses_junk_entry_overflow(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(
                    siatakes, "MAX_TRANSACTION_RECOVERY_BATCH", 1):
            _write(os.path.join(directory, "junk-a"), "x")
            _write(os.path.join(directory, "junk-b"), "x")
            with self.assertRaisesRegex(
                    ValueError, "bounded directory-entry scan"):
                siatakes._transaction_journal_names(
                    directory, "fixture transaction")

    def test_transaction_pending_refuses_junk_entry_overflow(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(
                    siatakes, "MAX_TRANSACTION_RECOVERY_BATCH", 1):
            _write(os.path.join(directory, "junk-a"), "x")
            _write(os.path.join(directory, "junk-b"), "x")
            with self.assertRaisesRegex(
                    ValueError, "bounded directory-entry scan"):
                siatakes._transaction_pending(
                    directory, "fixture transaction")

    def test_domain_catalog_crash_replays_exact_create_event(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            atomic = siatakes._atomic_text
            failed = []

            def crash_at_domain(path, text, *args, **kwargs):
                marker = os.sep + "domains" + os.sep
                if marker in path and not failed:
                    failed.append(path)
                    raise RuntimeError("simulated domain-record crash")
                return atomic(path, text, *args, **kwargs)

            with mock.patch.object(
                    siatakes, "_atomic_text",
                    side_effect=crash_at_domain):
                with self.assertRaisesRegex(
                        RuntimeError, "domain-record crash"):
                    siatakes.create_take(
                        "projection replay", deadline="2099-01-01",
                        domain="recovery")

            self.assertTrue(
                siatakes.natural_history_recovery_required("take"))
            recovered, errors = \
                siatakes.recover_natural_history_transactions()
            self.assertEqual(errors, [])
            self.assertEqual(len(recovered), 1)
            self.assertFalse(
                siatakes.natural_history_recovery_required("take"))
            self.assertEqual(siatakes.summary()["open"], 1)
            domains = siatakes.list_calibration_domains_page()["items"]
            self.assertEqual([row["domain"] for row in domains],
                             ["recovery"])

    def test_grade_projection_scores_only_after_exact_signed_row(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            made = siatakes.create_take(
                "signed calibration", confidence=0.8,
                deadline="2099-01-01")
            take = siatakes.get_take(made["id"])
            source = _read_path(take["path"])
            take.update({
                "status": "resolved-true", "outcome": 1,
                "brier": siatakes.brier_score(0.8, 1),
                "graded": "2026-08-30T12:00:00Z",
                "judge_model": "claude:fixture",
                "_grade_source_sha256": hashlib.sha256(
                    source.encode()).hexdigest(),
            })
            signed = []

            def append(*row, required=False):
                self.assertTrue(required)
                signed.append(row)

            fake_sialib = types.SimpleNamespace(
                ledger_contains=lambda *row: row in signed,
                ledger_append=append)
            with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                siatakes.commit_grade_transition(
                    take, "TRUE", "fixture evidence")

            overall = siatakes.calibration_report()["overall"]
            self.assertEqual(overall["resolved"], 1)
            self.assertEqual(overall["invalid_resolved"], 0)
            self.assertEqual(len(signed), 1)

    def test_unsigned_legacy_resolution_never_enters_score_denominator(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            JudgeIsolation()._head_v1_take(
                siatakes.TAKES_DIR, claim="unsigned legacy outcome",
                deadline="2026-08-30", domain="legacy")
            signed = []
            fake_sialib = types.SimpleNamespace(
                ledger_contains=lambda *row: row in signed,
                ledger_append=lambda *row, **_kwargs: signed.append(row))
            with mock.patch.dict(sys.modules, {"sialib": fake_sialib}):
                migrated, errors = siatakes.migrate_legacy_take_pages()
            self.assertEqual(errors, [])
            self.assertEqual(len(migrated), 1)
            overall = siatakes.calibration_report()["overall"]
            self.assertEqual(overall["resolved"], 0)
            self.assertEqual(overall["invalid_resolved"], 1)
            self.assertIsNone(overall["brier"])

    def test_history_listing_is_paginated_without_directory_listing(self):
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            expected = []
            for text in ("first", "second", "third"):
                expected.append(siatakes.create_intent(
                    text, "2099-01-01")["id"])
            with mock.patch.object(
                    siatakes.os, "listdir",
                    side_effect=AssertionError("unbounded list refused")):
                first = siatakes.list_intents_page(limit=2)
                second = siatakes.list_intents_page(
                    limit=2, cursor=first["next_cursor"])
                opened = siatakes.open_intents()
            observed = [row["id"] for row in
                        first["items"] + second["items"]]
            self.assertEqual(observed, expected)
            self.assertIsNotNone(first["next_cursor"])
            self.assertIsNone(second["next_cursor"])
            self.assertEqual({row["id"] for row in opened}, set(expected))

    def test_changed_directory_generation_restarts_cookie(self):
        with tempfile.TemporaryDirectory() as directory:
            _write(os.path.join(directory, "a.md"), "a")
            _write(os.path.join(directory, "b.md"), "b")
            first, complete, inspected, cursor = \
                siatakes._bounded_history_entries(directory, limit=1)
            self.assertFalse(complete)
            self.assertEqual(inspected, 1)
            self.assertEqual(len(first), 1)
            cursor["cookie"] = sys.maxsize
            _write(os.path.join(directory, "c.md"), "c")
            restarted, _complete, inspected, _next = \
                siatakes._bounded_history_entries(
                    directory, cursor, limit=1)
            self.assertEqual(inspected, 1)
            self.assertEqual(len(restarted), 1)

    def test_bounded_page_read_refuses_change_during_read(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "page.md")
            _write(path, "stable bytes")
            real_fstat = siatakes.os.fstat
            calls = []

            def changed_after_read(fd):
                info = real_fstat(fd)
                calls.append(True)
                if len(calls) == 2:
                    return types.SimpleNamespace(
                        st_mode=info.st_mode, st_uid=info.st_uid,
                        st_dev=info.st_dev, st_ino=info.st_ino,
                        st_size=info.st_size,
                        st_mtime_ns=info.st_mtime_ns, st_ctime_ns=-1)
                return info

            with mock.patch.object(
                    siatakes.os, "fstat",
                    side_effect=changed_after_read):
                with self.assertRaisesRegex(RuntimeError,
                                            "changed while reading"):
                    siatakes._read_bounded_regular_text(
                        path, siatakes.MAX_TAKE_PAGE_BYTES, "fixture page")

    def test_bounded_page_read_refuses_replaced_leaf(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "page.md")
            _write(path, "stable bytes")
            real_stat = siatakes.os.stat

            def replaced_target(candidate, *args, **kwargs):
                info = real_stat(candidate, *args, **kwargs)
                if candidate == path and kwargs.get("follow_symlinks") is False:
                    return types.SimpleNamespace(
                        st_dev=-1, st_ino=info.st_ino,
                        st_size=info.st_size,
                        st_mtime_ns=info.st_mtime_ns,
                        st_ctime_ns=info.st_ctime_ns)
                return info

            with mock.patch.object(
                    siatakes.os, "stat", side_effect=replaced_target):
                with self.assertRaisesRegex(RuntimeError,
                                            "changed while reading"):
                    siatakes._read_bounded_regular_text(
                        path, siatakes.MAX_TAKE_PAGE_BYTES, "fixture page")

    def test_legacy_intent_baseline_remains_bounded_and_resumable(self):
        fixtures = (
            ("0000000001", "2026-08-28T00:00:00Z", "first"),
            ("0000000002", "2026-08-29T00:00:00Z", "second"),
            ("0000000003", "2026-08-30T00:00:00Z", "third"),
        )
        with tempfile.TemporaryDirectory() as root, \
                self.projection_roots(root):
            for intent_id, created, text in fixtures:
                meta = {"id": intent_id, "text": text,
                        "due": "2099-01-01", "holder": "user",
                        "status": "open", "created": created,
                        "closed": None, "note": None}
                path = os.path.join(
                    siatakes.INTENTS_DIR,
                    f"{created[:10]}-{intent_id}.md")
                _write(path, "---\ntype: intent\n"
                       f"sia_intent: {json.dumps(meta, sort_keys=True)}\n"
                       "---\nlegacy intent\n")
            imported, errors = siatakes.advance_intent_history(limit=2)
            self.assertEqual(errors, [])
            self.assertLessEqual(len(imported), 2)
            self.assertTrue(siatakes.intent_history_required())
            attempts = []
            while siatakes.intent_history_required():
                attempts.append(True)
                self.assertLess(len(attempts), 20)
                _imported, errors = \
                    siatakes.advance_intent_history(limit=2)
                self.assertEqual(errors, [])
            first = siatakes.list_intents_page(limit=2)
            second = siatakes.list_intents_page(
                limit=2, cursor=first["next_cursor"])
            self.assertEqual(
                {row["id"] for row in first["items"] + second["items"]},
                {row[0] for row in fixtures})


class CalibrationPopulation(unittest.TestCase):

    def test_single_case_is_not_population_claim(self):
        report = siatakes.calibration_report([_take("0.9", 1)])
        overall = report["overall"]
        self.assertEqual(overall["resolved"], 1)
        self.assertEqual(overall["brier"], 0.01)
        self.assertEqual(overall["population_status"], "single-case")
        self.assertFalse(overall["monitoring_display_eligible"])
        self.assertIn("not a random", " ".join(overall["non_claims"]))

    def test_unresolvable_and_invalid_are_explicitly_excluded(self):
        rows = [_take("0.8", 1),
                {"status": "unresolvable", "confidence": 0.7,
                 "outcome": None, "domain": "general"},
                _take("0.7", 0, status="resolved-true"),
                {"status": "mystery", "domain": "general"}]
        overall = siatakes.calibration_report(rows)["overall"]
        self.assertEqual(overall["resolved"], 1)
        self.assertEqual(overall["unresolvable"], 1)
        self.assertEqual(overall["invalid_resolved"], 1)
        self.assertEqual(overall["invalid_records"], 1)

    def test_malformed_take_page_remains_visible(self):
        old_dir = siatakes.TAKES_DIR
        with tempfile.TemporaryDirectory() as takes_dir:
            siatakes.TAKES_DIR = takes_dir
            try:
                with open(os.path.join(takes_dir, "broken.md"), "w") as stream:
                    stream.write("---\ntype: take\n---\nmissing metadata\n")
                loaded = siatakes.load_takes()
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0]["status"], "invalid-record")
                overall = siatakes.calibration_report(loaded)["overall"]
                self.assertEqual(overall["invalid_records"], 1)
                self.assertEqual(overall["resolved"], 0)
            finally:
                siatakes.TAKES_DIR = old_dir

    def test_declared_display_gate_needs_both_outcomes(self):
        balanced = ([_take("0.8", 1) for _ in range(15)]
                    + [_take("0.2", 0) for _ in range(15)])
        overall = siatakes.calibration_report(balanced)["overall"]
        self.assertEqual(overall["population_status"],
                         "monitoring-population")
        self.assertTrue(overall["monitoring_display_eligible"])
        self.assertEqual(overall["brier"], 0.04)
        one_sided = [_take("0.8", 1) for _ in range(30)]
        skew = siatakes.calibration_report(one_sided)["overall"]
        self.assertEqual(skew["population_status"], "outcome-imbalanced")
        self.assertFalse(skew["monitoring_display_eligible"])

    def test_empty_report_has_no_division_or_score(self):
        overall = siatakes.calibration_report([])["overall"]
        self.assertEqual(overall["population_status"],
                         "no-resolved-outcomes")
        self.assertIsNone(overall["brier"])
        self.assertEqual(siatakes.calibration_text({}), [])

    def test_natural_history_report_forwards_domain_cursor(self):
        state = {
            "overall": {},
            "legacy": {"complete": True},
            "authority": {"generation": 9},
        }
        page = {"items": [], "next_cursor": None}
        with mock.patch.object(
                siatakes, "natural_history_debt", return_value=False), \
                mock.patch.object(
                    siatakes, "_load_history_state", return_value=state), \
                mock.patch.object(
                    siatakes, "list_calibration_domains_page",
                    return_value=page) as domains:
            report = siatakes.calibration_report(domain_cursor="17")
        domains.assert_called_once_with(cursor="17")
        self.assertEqual(report["domains"], {})

    def test_history_cursor_has_a_digit_bound(self):
        with self.assertRaisesRegex(ValueError, "cursor is invalid"):
            siatakes._history_cursor(
                "1" * (siatakes.MAX_HISTORY_CURSOR_DIGITS + 1))


class TakeDeadlineIntegrity(unittest.TestCase):
    NOW = siatakes.datetime.datetime(
        2026, 1, 1, tzinfo=siatakes.datetime.timezone.utc)

    def test_new_take_requires_future_deadline(self):
        old_dir = siatakes.TAKES_DIR
        with tempfile.TemporaryDirectory() as takes_dir, \
                mock.patch.object(siatakes, "_utcnow", return_value=self.NOW):
            siatakes.TAKES_DIR = takes_dir
            try:
                for deadline in ("2025-12-31", "2026-01-01"):
                    with self.assertRaisesRegex(ValueError, "after the UTC"):
                        siatakes.create_take("future claim", deadline=deadline)
                made = siatakes.create_take(
                    "future claim", deadline="2026-01-02")
                self.assertEqual(made["deadline"], "2026-01-02")
            finally:
                siatakes.TAKES_DIR = old_dir

    def test_new_take_refuses_non_finite_confidence(self):
        old_dir = siatakes.TAKES_DIR
        with tempfile.TemporaryDirectory() as takes_dir, \
                mock.patch.object(siatakes, "_utcnow", return_value=self.NOW):
            siatakes.TAKES_DIR = takes_dir
            try:
                for confidence in (float("nan"), float("inf"), float("-inf")):
                    with self.subTest(confidence=confidence), \
                            self.assertRaisesRegex(ValueError, "finite number"):
                        siatakes.create_take(
                            "future claim", confidence=confidence,
                            deadline="2026-01-02")
            finally:
                siatakes.TAKES_DIR = old_dir

    def test_proposal_is_rechecked_at_accept_time(self):
        proposal = {"claim": "future claim", "confidence": 0.7,
                    "deadline": "2026-01-02", "domain": "general",
                    "source": "sia/cortex", "proposed": "test"}
        accepted = siatakes.validate_proposal(
            proposal, require_future=True, now=self.NOW)
        self.assertEqual(accepted["deadline"], "2026-01-02")
        next_day = self.NOW + siatakes.datetime.timedelta(days=1)
        with self.assertRaisesRegex(ValueError, "after the UTC"):
            siatakes.validate_proposal(
                accepted, require_future=True, now=next_day)

    def test_persisted_take_proposal_and_intent_text_neutralize_controls(self):
        old_takes = siatakes.TAKES_DIR
        old_intents = siatakes.INTENTS_DIR
        with tempfile.TemporaryDirectory() as root, \
                mock.patch.object(siatakes, "_utcnow", return_value=self.NOW):
            siatakes.TAKES_DIR = os.path.join(root, "takes")
            siatakes.INTENTS_DIR = os.path.join(root, "intents")
            controls = "\x1b\x85\u202e\u2066"
            try:
                made = siatakes.create_take(
                    "alpha" + controls + " omega", holder="u\x07ser",
                    deadline="2026-01-02")
                self.assertEqual(made["claim"], "alpha omega")
                self.assertEqual(made["holder"], "u ser")
                proposal = siatakes.validate_proposal({
                    "claim": "future\u202e claim", "confidence": 0.7,
                    "deadline": "2026-01-02", "domain": "general",
                    "source": "sia/cortex", "proposed": "agent\x00 prose"})
                self.assertEqual(proposal["claim"], "future claim")
                self.assertEqual(proposal["proposed"], "agent prose")
                intent = siatakes.create_intent(
                    "rotate\u202e keys", "2026-01-02",
                    holder="u\x1fser")
                closed = siatakes.close_intent(
                    intent["id"], "done\x9b safely\u2069")
                self.assertEqual(closed["text"], "rotate keys")
                self.assertEqual(closed["holder"], "u ser")
                self.assertEqual(closed["note"], "done safely")
                for directory in (siatakes.TAKES_DIR, siatakes.INTENTS_DIR):
                    for name in os.listdir(directory):
                        body = _read_path(os.path.join(directory, name))
                        self.assertFalse(any(
                            ord(character) < 0x20
                            and character not in "\n"
                            for character in body))
                        self.assertNotIn("\u202e", body)
                        self.assertNotIn("\u2066", body)
                        self.assertNotIn("\u2069", body)
            finally:
                siatakes.TAKES_DIR = old_takes
                siatakes.INTENTS_DIR = old_intents

    def test_proposal_queue_refuses_count_and_byte_quota_without_mutation(self):
        proposal = {"claim": "future claim", "confidence": 0.7,
                    "deadline": "2026-01-02", "domain": "general",
                    "source": "sia/cortex", "proposed": "test"}
        with tempfile.TemporaryDirectory() as state:
            with mock.patch.object(siatakes, "MAX_PENDING_PROPOSALS", 1):
                first = siatakes.locked_proposals(
                    state, lambda pending: pending + [proposal])
                before = _read_path(os.path.join(
                    state, "take-proposals.json"))
                with self.assertRaisesRegex(ValueError,
                                            "pending-count quota"):
                    siatakes.locked_proposals(
                        state, lambda pending: pending + [{
                            **proposal, "claim": "second future claim"}])
                self.assertEqual(_read_path(os.path.join(
                    state, "take-proposals.json")), before)
                self.assertEqual(len(first), 1)
        with tempfile.TemporaryDirectory() as state, \
                mock.patch.object(siatakes, "MAX_PROPOSAL_QUEUE_BYTES", 8):
            with self.assertRaisesRegex(ValueError, "byte quota"):
                siatakes.locked_proposals(
                    state, lambda pending: pending + [proposal])
            self.assertFalse(os.path.exists(os.path.join(
                state, "take-proposals.json")))


class LegacySlugTripwire(unittest.TestCase):
    def _retrieval_row(self, *_args, **_kwargs):
        return [{"slug": "integrity/failure", "score": 1.0,
                 "type": "event-day"}]

    def test_nightly_fields_refuse_answer_metric_names(self):
        with tempfile.TemporaryDirectory() as corpus, \
                mock.patch.object(siabench, "CORPUS", corpus), \
                mock.patch.object(siabench, "_engine",
                                  side_effect=self._retrieval_row), \
                mock.patch.object(siabench.sialib, "read_json",
                                  return_value={}), \
                mock.patch.object(siabench.siamind, "load_mind",
                                  return_value={"nodes": {}, "edges": {}}):
            result = siabench.run_quick(day="2026-08-30")
        self.assertEqual(
            result["kind"], "heuristic-slug-retrieval-drift-tripwire")
        self.assertIn("slug_match_at_5_keyword", result)
        self.assertIn("reciprocal_slug_rank_blend", result)
        self.assertIn("not answer keys", " ".join(result["non_claims"]))
        self.assertFalse(any(
            key.startswith(("hit", "mrr")) for key in result))

    def test_probe_discovery_never_uses_recursive_walk(self):
        with tempfile.TemporaryDirectory() as corpus, \
                mock.patch.object(siabench, "CORPUS", corpus), \
                mock.patch.object(
                    siabench.os, "walk",
                    side_effect=AssertionError("recursive walk forbidden")):
            present, absent = siabench.build_questions()
        self.assertTrue(present)
        self.assertTrue(absent)

    def test_negative_organ_probe_refuses_at_directory_ceiling(self):
        with mock.patch.object(
                siabench.sialib, "_bounded_source_entries",
                return_value=([], False, 1, {})), \
                self.assertRaisesRegex(
                    siabench.BenchmarkRefusal, "directory bound"):
            siabench._probe_organ_directory("events/journal")

    def test_positive_sibling_can_settle_an_incomplete_organ_probe(self):
        partial = ([], False, 1, {})
        positive = ([{"name": "week.md", "mode": stat.S_IFREG}],
                    True, 1, {})
        responses = iter((partial, positive))

        def bounded_entries(*_args, **_kwargs):
            try:
                return next(responses)
            except StopIteration:
                raise FileNotFoundError

        with mock.patch.object(
                siabench.sialib, "_bounded_source_entries",
                side_effect=bounded_entries):
            present, _absent = siabench.build_questions()
        self.assertTrue(any(
            question == "when did sekhmet restart wireplumber"
            for question, _accepts in present))

    def test_organ_probe_refuses_symlinked_directory(self):
        with tempfile.TemporaryDirectory() as root:
            outside = os.path.join(root, "outside")
            corpus = os.path.join(root, "corpus")
            os.makedirs(outside)
            os.makedirs(os.path.join(corpus, "events"))
            os.symlink(outside, os.path.join(corpus, "events", "journal"))
            with mock.patch.object(siabench, "CORPUS", corpus), \
                    self.assertRaisesRegex(
                        siabench.BenchmarkRefusal, "probe refused"):
                siabench._probe_organ_directory("events/journal")

    def test_legacy_report_labels_slug_heuristics_not_ground_truth(self):
        with tempfile.TemporaryDirectory() as root:
            output = os.path.join(root, "tripwire.md")
            stdout = io.StringIO()
            with mock.patch.object(siabench, "CORPUS", root), \
                    mock.patch.object(siabench, "_engine",
                                      side_effect=self._retrieval_row), \
                    mock.patch.object(siabench.sialib, "read_json",
                                      return_value={}), \
                    mock.patch.object(siabench.siamind, "load_mind",
                                      return_value={"nodes": {},
                                                    "edges": {}}), \
                    mock.patch.object(siabench.os.path, "expanduser",
                                      return_value=output), \
                    contextlib.redirect_stdout(stdout):
                report = siabench.run_legacy()
        self.assertIn("legacy slug-retrieval drift tripwire", report)
        self.assertIn("slug match@5", report)
        self.assertIn("Neither set is answer-bearing ground truth", report)
        self.assertNotIn("provably hold the answer", report)
        self.assertNotIn("correct answer = abstain", report)
        self.assertNotIn("hit@5", report)

    def test_engine_failure_refuses_instead_of_scoring_a_miss(self):
        failed = mock.Mock(returncode=1, stdout="", stderr="engine failed")
        with mock.patch.object(siabench.sialib, "gbrain",
                               return_value=failed):
            with self.assertRaisesRegex(siabench.BenchmarkRefusal,
                                        "did not complete"):
                siabench._engine(["query", "memory"])

    def test_malformed_engine_output_refuses_instead_of_scoring_a_miss(self):
        malformed = mock.Mock(returncode=0, stdout='[{"slug": 7}]',
                              stderr="")
        with mock.patch.object(siabench.sialib, "gbrain",
                               return_value=malformed):
            with self.assertRaisesRegex(siabench.BenchmarkRefusal,
                                        "could not be admitted"):
                siabench._engine(["query", "memory"])


class SignedLedgerDataset(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state, self.corpus, self.registry = _signed_fixture(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _bundle(self):
        return siabench.build_ledger_dataset(
            corpus=self.corpus, chain_registry=self.registry)

    def _signed_rows(self):
        with open(self.registry["aegis"][0], encoding="utf-8") as stream:
            return [line.split("\t") for line in stream.read().splitlines()]

    def _projected_row(self, sequence):
        row = next(row for row in self._signed_rows()
                   if row[0] == str(sequence))
        event = siabench.sialib.signed_ledger_event_projection("aegis", row)
        event_id = siabench.sialib.event_memory_identity(event)
        semantic_id = siabench.sialib.event_semantic_identity(event)
        line, payload, _base = siabench.sialib._event_line(
            event, event_id, semantic_id)
        day = event.ts.date().isoformat()
        return row, event, event_id, semantic_id, line, payload, day

    def _replace_marker_with_split_decoys(self, sequence):
        row, event, event_id, semantic_id, line, payload, day = \
            self._projected_row(sequence)
        path = os.path.join(
            self.corpus, "events", event.organ, day + ".md")
        text = _read_path(path)
        self.assertIn(line, text)
        decoys = (
            f"- 00:00:00Z action-only {row[2]}\n"
            f"- 00:00:01Z label-only {row[3]}\n"
            f"- 00:00:02Z value-only {row[4]}")
        _write(path, text.replace(line, decoys))
        return row, event, event_id, semantic_id, line, payload, day

    def _write_overflow_marker(self, sequence):
        row, event, event_id, semantic_id, line, payload, day = \
            self._projected_row(sequence)
        shard = {"slug": f"events/{event.organ}/{day}-part-2",
                 "part": 2, "counts": {event.kind: 1},
                 "tags": set(event.tags), "bullets": [line]}
        frontmatter, body = siabench.sialib._render_event_shard(
            event.organ, day, shard)
        relative = shard["slug"] + ".md"
        _write(os.path.join(self.corpus, *relative.split("/")),
               "---\n" + "\n".join(frontmatter) + "\n---\n" + body)
        return relative

    def _consolidate_sequence_fixture(self, sequence, *, retain_exemplar=True):
        row, event, event_id, semantic_id, line, payload, day = \
            self._projected_row(sequence)
        source_rel = f"events/{event.organ}/{day}.md"
        source_path = os.path.join(self.corpus, *source_rel.split("/"))
        with open(source_path, "rb") as stream:
            source_raw = stream.read()
        source_id = hashlib.sha256(
            source_rel.encode("utf-8") + b"\0" + source_raw).hexdigest()
        epoch_slug = siabench.sialib._epoch_slug_for_day(event.organ, day)
        manifest = [{"rel": source_rel, "sha256": source_id}]
        frontmatter = [
            "type: epoch",
            siabench.sialib.fm_title(f"{event.organ} consolidated fixture"),
            f"tags: [{event.organ}]",
            f"date: {day}",
            "sia_sources: " + json.dumps(
                [source_id], separators=(",", ":")),
            "sia_source_manifest: " + json.dumps(
                manifest, separators=(",", ":")),
            "sia_dates: " + json.dumps([day], separators=(",", ":")),
            f"sia_counts: {json.dumps({event.kind: 1}, sort_keys=True)}",
        ]
        exemplar = (f"## Exemplars\n- {day} ·{line[1:]}\n"
                    if retain_exemplar else
                    f"## Exemplars\n- unrelated status token: {row[4]}\n")
        body = (
            f"# {event.organ} consolidated fixture\n\n"
            f"Consolidated from 1 day-memories ({day} … {day}); "
            "originals verbatim in corpus git history.\n\n"
            + exemplar)
        _write(os.path.join(self.corpus, epoch_slug + ".md"),
               "---\n" + "\n".join(frontmatter) + "\n---\n" + body)
        entry = {
            "schema": siabench.sialib.EVENT_INDEX_SCHEMA,
            "organ": event.organ,
            "event_id": event_id,
            "semantic_id": semantic_id,
            "payload_sha256": siabench.sialib._event_payload_digest(payload),
            "source_rel": source_rel,
            "source_sha256": source_id,
            "epoch_slug": epoch_slug,
        }
        index_rel = siabench.sialib._event_index_relative(
            event.organ, event_id).replace(os.sep, "/")
        index_raw = siabench.sialib._event_index_encoded(entry)
        _write(os.path.join(self.corpus, *index_rel.split("/")),
               index_raw.decode("utf-8"))
        os.unlink(source_path)
        return {"row": row, "event": event, "event_id": event_id,
                "epoch_slug": epoch_slug, "index_rel": index_rel,
                "index_raw": index_raw}

    @staticmethod
    def _coverage_reasons(bundle):
        return {item["reason"] for item in
                bundle["manifest"].get("witness_coverage", [])}

    def test_complete_snapshot_ceiling_refuses_instead_of_truncating(self):
        ledger = self.registry["aegis"][0]
        with mock.patch.object(
                siabench, "MAX_BENCH_LEDGER_BYTES",
                os.path.getsize(ledger) - 1):
            bundle = self._bundle()
        self.assertTrue(any(
            item.get("reason") == "ledger-open-refused"
            and "complete-snapshot byte ceiling" in item.get("detail", "")
            for item in bundle["diagnostics"]))
        with self.assertRaisesRegex(
                siabench.BenchmarkRefusal, "chain intake refused"):
            siabench._require_usable_bundle(bundle)

    def test_source_page_aggregate_ceiling_is_an_explicit_refusal(self):
        with mock.patch.object(siabench, "MAX_BENCH_SOURCE_BYTES", 1), \
                self.assertRaisesRegex(
                    siabench.BenchmarkRefusal, "source-page bytes"):
            self._bundle()

    def test_crafted_source_manifest_enforces_all_verifier_ceilings(self):
        bundle = self._bundle()
        with mock.patch.object(siabench, "MAX_BENCH_SOURCE_PAGES", 0), \
                self.assertRaisesRegex(
                    siabench.BenchmarkRefusal, "page-count ceiling"):
            siabench._verify_source_pages(bundle, corpus=self.corpus)
        with mock.patch.object(
                siabench, "MAX_BENCH_SOURCE_PAGE_BYTES", 0), \
                self.assertRaisesRegex(
                    siabench.BenchmarkRefusal, "per-page byte ceiling"):
            siabench._verify_source_pages(bundle, corpus=self.corpus)
        with mock.patch.object(siabench, "MAX_BENCH_SOURCE_BYTES", 0), \
                self.assertRaisesRegex(
                    siabench.BenchmarkRefusal, "aggregate-byte ceiling"):
            siabench._verify_source_pages(bundle, corpus=self.corpus)

    def test_dataset_reader_bounds_rows_bytes_and_private_artifacts(self):
        bundle = self._bundle()
        with tempfile.TemporaryDirectory() as output:
            siabench.write_dataset(bundle, output, corpus=self.corpus)
            private_manifest = os.path.join(
                output, "private-manifest.json")
            os.chmod(private_manifest, 0o644)
            with self.assertRaisesRegex(OSError, "owner-private"):
                siabench.load_dataset(output)
            os.chmod(private_manifest, 0o600)
            questions = os.path.join(output, "questions.jsonl")
            with mock.patch.object(
                    siabench, "MAX_BENCH_FILE_BYTES",
                    os.path.getsize(questions) - 1), \
                    self.assertRaisesRegex(
                        OSError, "complete-snapshot byte ceiling"):
                siabench.load_dataset(output)
        with mock.patch.object(siabench, "MAX_BENCH_ROWS", 1), \
                self.assertRaisesRegex(ValueError, "row ceiling"):
            siabench._parse_jsonl('{"id":"a"}\n{"id":"b"}\n',
                                  "answers.jsonl")

    def test_jsonl_uses_literal_lf_not_unicode_line_separators(self):
        for separator in ("\u0085", "\u2028", "\u2029"):
            payload = (json.dumps(
                {"id": "row", "answer": f"left{separator}right"},
                ensure_ascii=False) + "\n").encode("utf-8")
            rows = siabench._parse_jsonl(
                payload, "predictions.jsonl", require_trailing_lf=False)
            self.assertEqual(rows[0]["answer"], f"left{separator}right")
        self.assertEqual(
            siabench._parse_jsonl(
                b'{"id":"row"}', "predictions.jsonl",
                require_trailing_lf=False)[0]["id"],
            "row")
        with self.assertRaisesRegex(ValueError, "trailing LF"):
            siabench._parse_jsonl(
                b'{"id":"row"}', "questions.jsonl",
                require_trailing_lf=True)
        with self.assertRaisesRegex(
                siabench.BenchmarkRefusal, "not valid UTF-8"):
            siabench._parse_jsonl(b'{"id":"\xff"}\n', "bad.jsonl")

    def test_generation_is_deterministic_and_covers_abilities(self):
        first, second = self._bundle(), self._bundle()
        self.assertEqual(first["manifest"]["dataset_id"],
                         second["manifest"]["dataset_id"])
        self.assertEqual(first["questions"], second["questions"])
        categories = {q["category"] for q in first["questions"]}
        self.assertTrue({"information-extraction", "temporal-reasoning",
                         "knowledge-update", "multi-event-aggregation",
                         "abstention"} <= categories)
        self.assertNotIn("multi-session-reasoning", categories)
        self.assertTrue(any(q["answer"] == siabench.ABSTAIN
                            for q in first["questions"]))
        self.assertTrue(all(chain.get("verifier_sha256")
                            for chain in first["manifest"]["chains"]))
        self.assertEqual(first["manifest"]["chains"][0]["chain_format"],
                         siabench.ATTEST_CHAIN_FORMAT)
        self.assertEqual(
            first["manifest"]["capacity_policy"]["kind"],
            "complete-snapshot-refusal-v1")
        self.assertIn(
            "no signed snapshot or witness is truncated",
            " ".join(first["manifest"]["non_claims"]))
        self.assertTrue(all(q["provenance"].get("ledger_head")
                            for q in first["questions"]))
        self.assertIn("same-user in-place ABA",
                      " ".join(first["manifest"]["non_claims"]))
        source_pages = first["manifest"]["source_pages"]
        self.assertTrue(source_pages)
        for page in source_pages:
            with open(os.path.join(self.corpus, page["slug"] + ".md"),
                      "rb") as stream:
                content = stream.read()
            self.assertEqual(page["sha256"],
                             hashlib.sha256(content).hexdigest())
            self.assertEqual(page["size"], len(content))

        present = [question for question in first["questions"]
                   if question["answer"] != siabench.ABSTAIN]
        absent = [question for question in first["questions"]
                  if question["answer"] == siabench.ABSTAIN]
        self.assertTrue(present)
        self.assertTrue(all("answer_witness" in question
                            for question in present))
        self.assertTrue(all("answer_witness" not in question
                            for question in absent))
        for question in present:
            witness = question["answer_witness"]
            self.assertEqual(witness["schema"],
                             siabench.ANSWER_WITNESS_SCHEMA)
            self.assertIn(witness["match"],
                          {"any-excerpt", "all-excerpts"})
            self.assertTrue(witness["excerpts"])
            for item in witness["excerpts"]:
                self.assertIn(item["slug"], question["sources"])
                self.assertEqual(item["sha256"],
                                 siabench._sha_text(item["excerpt"]))
                page = _read_path(os.path.join(
                    self.corpus, item["slug"] + ".md"))
                self.assertIn(
                    item["excerpt"],
                    siabench._normalize_witness_excerpt(page))

    def test_custom_chain_cross_matches_never_guess_a_projection(self):
        _write(
            os.path.join(self.corpus, "events", "custom",
                         "2026-01-01.md"),
            "---\ntype: event-day\ndate: 2026-01-01\n---\n"
            "## Log\n"
            "- 00:00:00Z OUTCOME:restart\n"
            "- 00:00:01Z wireplumber.service\n"
            "- 00:00:02Z ok\n")
        bundle = siabench.build_ledger_dataset(
            corpus=self.corpus,
            chain_registry={"custom": self.registry["aegis"]})

        self.assertEqual(bundle["questions"], [])
        self.assertIn("undefined-corpus-projection",
                      self._coverage_reasons(bundle))
        self.assertEqual(bundle["diagnostics"][0]["status"], "verified")

    def test_split_decoys_do_not_admit_row_but_exact_overflow_marker_does(self):
        self._replace_marker_with_split_decoys("1")
        overflow = self._write_overflow_marker("1")

        bundle = self._bundle()
        rows = [question for question in bundle["questions"]
                if question["provenance"].get("seq") == "1"]
        self.assertTrue(rows)
        self.assertTrue(all(question["sources"] == [overflow[:-3]]
                            for question in rows))
        self.assertTrue(all(
            question["provenance"]["witness_kind"] == "live-event-marker"
            for question in rows))

    def test_missing_exact_marker_is_coverage_excluded(self):
        _row, _event, event_id, _semantic_id, _line, _payload, _day = \
            self._replace_marker_with_split_decoys("1")

        bundle = self._bundle()
        self.assertIn("event-witness-missing",
                      self._coverage_reasons(bundle))
        self.assertNotIn(
            event_id,
            json.dumps([question["provenance"]
                        for question in bundle["questions"]], sort_keys=True))

    def test_duplicate_exact_markers_are_coverage_excluded_as_ambiguous(self):
        _row, _event, event_id, _semantic_id, _line, _payload, _day = \
            self._projected_row("1")
        self._write_overflow_marker("1")

        bundle = self._bundle()
        self.assertIn("event-marker-ambiguous",
                      self._coverage_reasons(bundle))
        self.assertNotIn(
            event_id,
            json.dumps([question["provenance"]
                        for question in bundle["questions"]], sort_keys=True))

    def test_huge_overflow_shard_number_refuses_without_range_materialization(self):
        huge = "9" * 40
        _write(os.path.join(
            self.corpus, "events", "aegis",
            f"2026-01-01-part-{huge}.md"), "not an admissible shard\n")

        bundle = self._bundle()
        self.assertIn("event-shard-set-invalid",
                      self._coverage_reasons(bundle))

    def test_consolidated_epoch_uses_exact_event_index_lineage(self):
        fixture = self._consolidate_sequence_fixture("3")

        bundle = self._bundle()
        rows = [question for question in bundle["questions"]
                if question["provenance"].get("seq") == "3"]
        self.assertTrue(rows)
        self.assertTrue(all(
            question["sources"] == [fixture["epoch_slug"]]
            and question["provenance"]["event_id"] == fixture["event_id"]
            and question["provenance"]["witness_kind"] == "epoch-lineage"
            and question["provenance"]["event_index"]["path"]
            == fixture["index_rel"]
            for question in rows))
        self.assertEqual(
            [item["path"] for item in bundle["manifest"]["witness_files"]],
            [fixture["index_rel"]])
        siabench._verify_source_pages(bundle, corpus=self.corpus)

    def test_epoch_unrelated_value_token_does_not_admit_value_question(self):
        fixture = self._consolidate_sequence_fixture(
            "3", retain_exemplar=False)

        bundle = self._bundle()
        rows = [question for question in bundle["questions"]
                if question["provenance"].get("seq") == "3"]
        # The event index/epoch lineage authenticates where the event went,
        # but the indexed epoch body carries no exact event excerpt. Its slug
        # therefore cannot stand in for answer-bearing temporal evidence.
        self.assertEqual(rows, [])
        self.assertNotIn(
            fixture["event_id"],
            json.dumps([question.get("answer_witness")
                        for question in bundle["questions"]],
                       sort_keys=True))
        self.assertEqual(
            bundle["manifest"]["question_coverage"],
            [{"chain": "aegis",
              "reason": "projected-event-answer-not-retained",
              "affected_rows": 1}])

    def test_event_index_digest_and_path_replacement_are_refused(self):
        fixture = self._consolidate_sequence_fixture("3")
        bundle = self._bundle()
        index_path = os.path.join(
            self.corpus, *fixture["index_rel"].split("/"))
        entry = json.loads(fixture["index_raw"].decode("utf-8"))
        entry["payload_sha256"] = "0" * 64
        changed = siabench.sialib._event_index_encoded(entry)
        _write(index_path, changed.decode("utf-8"))
        with self.assertRaisesRegex(
                siabench.BenchmarkRefusal,
                "witness file .* changed after dataset generation"):
            siabench._verify_source_pages(bundle, corpus=self.corpus)

        _write(index_path, fixture["index_raw"].decode("utf-8"))
        replacement = index_path + ".replacement"
        os.replace(index_path, replacement)
        os.symlink(replacement, index_path)
        with self.assertRaisesRegex(
                siabench.BenchmarkRefusal,
                "witness file .* cannot be re-opened"):
            siabench._verify_source_pages(bundle, corpus=self.corpus)

    def test_builtin_custos_uses_signed_line_hashes_in_manifest_and_provenance(self):
        _state, corpus, registry, rows, encoded, expected_head = \
            _custos_fixture(self.temp.name)
        bundle = siabench.build_ledger_dataset(
            corpus=corpus, chain_registry=registry)

        self.assertEqual(bundle["diagnostics"][0]["status"], "verified")
        self.assertEqual(bundle["diagnostics"][0]["chain_format"],
                         siabench.CUSTOS_CHAIN_FORMAT)
        chain = bundle["manifest"]["chains"][0]
        self.assertEqual(chain["chain_format"],
                         siabench.CUSTOS_CHAIN_FORMAT)
        self.assertEqual(chain["head"], expected_head)
        self.assertEqual(
            expected_head,
            hashlib.sha256(encoded[-1].encode("utf-8")).hexdigest())
        self.assertNotEqual(expected_head, siabench._entry_hash(rows[-1]))
        self.assertTrue(bundle["questions"])
        self.assertIn("does not re-open or re-hash files",
                      " ".join(bundle["manifest"]["non_claims"]))
        self.assertFalse(any(
            question["category"] in {
                "information-extraction", "knowledge-update"}
            for question in bundle["questions"]
            if question["provenance"].get("chain") == "custos"))
        self.assertIn("projected-value-answer-not-retained",
                      {item["reason"] for item in
                       bundle["manifest"]["question_coverage"]})
        native_entry_hashes = {
            hashlib.sha256(line.encode("utf-8")).hexdigest()
            for line in encoded
        }
        for question in bundle["questions"]:
            provenance = question["provenance"]
            self.assertEqual(provenance["chain_format"],
                             siabench.CUSTOS_CHAIN_FORMAT)
            self.assertEqual(provenance["ledger_head"], expected_head)
            if "seq" in provenance:
                sequence = int(provenance["seq"])
                self.assertEqual(
                    provenance["entry_hash"],
                    hashlib.sha256(
                        encoded[sequence].encode("utf-8")).hexdigest())
            if "entry_hashes" in provenance:
                self.assertTrue(
                    set(provenance["entry_hashes"]) <= native_entry_hashes)

    def test_malformed_builtin_custos_rows_refuse_after_keeper_success(self):
        state, corpus, registry, _rows, encoded, _head = \
            _custos_fixture(self.temp.name)
        ledger = os.path.join(state, "ledger.tsv")

        def replace_field(lines, row_index, field_index, value):
            changed = list(lines)
            fields = changed[row_index].split("\t")
            fields[field_index] = value
            changed[row_index] = "\t".join(fields)
            return changed

        malformed = {
            "wrong genesis predecessor": replace_field(
                encoded, 0, 7,
                hashlib.sha256(b"attest-genesis-v1").hexdigest()),
            "non-canonical sequence": replace_field(encoded, 1, 0, "01"),
            "non-Unix timestamp": replace_field(
                encoded, 0, 1, "2026-01-01T00:00:00Z"),
            "non-canonical Unix timestamp": replace_field(
                encoded, 1, 1, "01"),
            "uppercase content hash": replace_field(
                encoded, 0, 5,
                encoded[0].split("\t")[5].upper()),
            "uppercase predecessor": replace_field(
                encoded, 0, 7,
                encoded[0].split("\t")[7].upper()),
            "non-canonical size": replace_field(encoded, 1, 6, "03"),
            "newline-inclusive predecessor": replace_field(
                encoded, 1, 7,
                hashlib.sha256((encoded[0] + "\n").encode("utf-8"))
                .hexdigest()),
            "uppercase signature": replace_field(
                encoded, 0, 8, encoded[0].split("\t")[8].upper()),
            "short signature": replace_field(encoded, 0, 8, "ab"),
        }
        for label, lines in malformed.items():
            with self.subTest(label=label):
                _write(ledger, "\n".join(lines) + "\n")
                bundle = siabench.build_ledger_dataset(
                    corpus=corpus, chain_registry=registry)
                self.assertEqual(bundle["questions"], [])
                self.assertEqual(bundle["diagnostics"][0]["reason"],
                                 "strict-row-parse-refused")
                self.assertEqual(
                    bundle["diagnostics"][0]["chain_format"],
                    siabench.CUSTOS_CHAIN_FORMAT)

    def test_custom_chain_cannot_select_custos_legacy_grammar(self):
        _state, corpus, custos_registry, _rows, _encoded, _head = \
            _custos_fixture(self.temp.name)
        bundle = siabench.build_ledger_dataset(
            corpus=corpus,
            chain_registry={"custom": custos_registry["custos"]})
        self.assertEqual(bundle["questions"], [])
        self.assertEqual(bundle["diagnostics"][0]["reason"],
                         "strict-row-parse-refused")
        self.assertEqual(bundle["diagnostics"][0]["chain_format"],
                         siabench.ATTEST_CHAIN_FORMAT)

    def test_fresh_standalone_sia_install_rows_form_usable_held_out_bundle(self):
        share = os.path.join(self.temp.name, "standalone-share")
        corpus = os.path.join(share, "corpus")
        os.makedirs(corpus)
        keeper = os.path.join(BIN, "sia-ledger")
        subprocess.run(
            [sys.executable, keeper, "init", share],
            check=True, capture_output=True, text=True)
        empty_hash = hashlib.sha256(b"").hexdigest()
        for action, arg1, arg2 in (
                ("INSTALL:runtime", "sia-1.3.0", "prepared"),
                ("INSTALL:index", "sia", "registered")):
            subprocess.run(
                [sys.executable, keeper, "append", share,
                 action, arg1, arg2, empty_hash, "0"],
                check=True, capture_output=True, text=True)

        projection = _load(
            "sialib_standalone_benchmark",
            os.path.join(BIN, "sialib.py"))
        projection.SHARE = share
        projection.CORPUS = corpus
        projection.BIN = BIN
        cursors = {}
        with mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
            events = projection.sense_sia(cursors)
        self.assertEqual(
            {event.summary.split(": ", 1)[1] for event in events},
            {"INSTALL:runtime sia-1.3.0 prepared",
             "INSTALL:index sia registered"})
        by_day = {}
        for event in events:
            by_day.setdefault(event.ts.date().isoformat(), []).append(event)
        for day, day_events in by_day.items():
            projection.update_day_page("sia", day, day_events)

        registry = {
            "sia": (os.path.join(share, "ledger.tsv"), keeper,
                    [sys.executable, keeper, "verify", share, "--quiet"]),
        }
        bundle = siabench.build_ledger_dataset(
            corpus=corpus, chain_registry=registry)
        siabench._require_usable_bundle(bundle)
        self.assertEqual(bundle["diagnostics"][0]["status"], "verified")
        self.assertEqual(bundle["manifest"]["chains"][0]["chain_format"],
                         siabench.ATTEST_CHAIN_FORMAT)
        self.assertEqual({question["split"] for question in
                          bundle["questions"]},
                         {"calibration", "evaluation"})
        self.assertEqual(
            {question["answer"] for question in bundle["questions"]
             if question["answer"] != siabench.ABSTAIN}
            & {"prepared", "registered"},
            {"prepared", "registered"})
        self.assertTrue(all(
            source.startswith("events/sia/")
            for question in bundle["questions"]
            for source in question["sources"]))

        # Fresh-install rows share one dated source page. Publishing that slug,
        # or the per-sequence signed timestamp, reveals every temporal answer
        # without consulting the owner-private key.
        temporal_answers = {
            question["answer"] for question in bundle["questions"]
            if question["category"] == "temporal-reasoning"
        }
        self.assertTrue(temporal_answers)
        output = os.path.join(self.temp.name, "standalone-export")
        siabench.write_dataset(bundle, output, corpus=corpus)
        with open(os.path.join(output, "manifest.json"),
                  encoding="utf-8") as stream:
            public_manifest_text = stream.read()
        with open(os.path.join(output, "questions.jsonl"),
                  encoding="utf-8") as stream:
            public_questions_text = stream.read()
        public_artifacts = public_manifest_text + public_questions_text
        for page in bundle["manifest"]["source_pages"]:
            self.assertNotIn(page["slug"], public_artifacts)
        for answer in temporal_answers:
            self.assertNotIn(answer, public_artifacts)
        with open(os.path.join(output, "private-manifest.json"),
                  encoding="utf-8") as stream:
            private_manifest = json.load(stream)
        self.assertEqual(
            private_manifest["evaluation_manifest"]["source_pages"],
            bundle["manifest"]["source_pages"])

    def test_dataset_identity_binds_observed_source_page_bytes(self):
        before = self._bundle()
        page = os.path.join(self.corpus, "events", "aegis",
                            "2026-01-01.md")
        with open(page, "a") as stream:
            stream.write("\n- later harmless annotation\n")
        after = self._bundle()
        self.assertNotEqual(before["manifest"]["dataset_id"],
                            after["manifest"]["dataset_id"])

    def test_page_slug_or_title_without_exact_excerpt_cannot_score(self):
        bundle = self._bundle()
        question = next(
            row for row in bundle["questions"]
            if row["answer"] != siabench.ABSTAIN
            and row["answer_witness"]["match"] == "any-excerpt")
        excerpt = question["answer_witness"]["excerpts"][0]
        slug_only = siabench._full_results([{
            "slug": excerpt["slug"], "score": 1.0,
            "title": excerpt["excerpt"],
            "chunk_text": "same page, unrelated chunk",
        }])
        self.assertIsNone(siabench._evidence_rank(question, slug_only))

        wrong_page = [{"slug": "events/aegis/wrong", "score": 1.0,
                       "chunk_text": excerpt["excerpt"]}]
        self.assertIsNone(siabench._evidence_rank(question, wrong_page))

        witnessed = [{"slug": excerpt["slug"], "score": 1.0,
                      "chunk_text": "prefix\n" + excerpt["excerpt"]
                                    + "\nsuffix"}]
        self.assertIsNotNone(siabench._evidence_rank(question, witnessed))

        calibration_present = {
            **copy.deepcopy(question), "id": "calibration-present",
            "question": "calibration present", "split": "calibration"}
        calibration_absent = {
            "id": "calibration-absent", "question": "calibration absent",
            "split": "calibration", "answer": siabench.ABSTAIN,
            "sources": [], "category": "abstention"}
        evaluation_present = {
            **copy.deepcopy(question), "id": "evaluation-present",
            "question": "evaluation present", "split": "evaluation"}
        synthetic = {"questions": [calibration_present,
                                    calibration_absent,
                                    evaluation_present]}

        def query(text):
            if text == "calibration absent":
                return {"fixture": []}
            chunk = (excerpt["excerpt"] if text == "calibration present"
                     else "same page, unrelated chunk")
            return {"fixture": [{"slug": excerpt["slug"], "score": 1.0,
                                  "chunk_text": chunk}]}

        report = siabench.evaluate_retrieval(
            synthetic, query_fn=query)["fixture"]
        self.assertTrue(report["scored"])
        self.assertEqual(report["present_evidence_correct"], 0)
        self.assertEqual(report["wrong_evidence"], 1)

    def test_multi_event_rank_requires_every_exact_event_excerpt(self):
        bundle = self._bundle()
        question = next(
            row for row in bundle["questions"]
            if row["category"] == "multi-event-aggregation")
        witness = question["answer_witness"]
        self.assertEqual(witness["match"], "all-excerpts")
        by_slug = {}
        for item in witness["excerpts"]:
            by_slug.setdefault(item["slug"], []).append(item["excerpt"])
        complete = [
            {"slug": slug, "score": 1.0,
             "chunk_text": "\n".join(excerpts)}
            for slug, excerpts in sorted(by_slug.items())]
        self.assertIsNotNone(siabench._evidence_rank(question, complete))

        missing = copy.deepcopy(complete)
        omitted = witness["excerpts"][-1]
        target = next(row for row in missing
                      if row["slug"] == omitted["slug"])
        target["chunk_text"] = target["chunk_text"].replace(
            omitted["excerpt"], "witness omitted")
        self.assertIsNone(siabench._evidence_rank(question, missing))

    def test_evaluation_refuses_source_page_changed_during_queries(self):
        bundle = self._bundle()
        page = os.path.join(self.corpus, "events", "aegis",
                            "2026-01-01.md")
        mutated = False

        def query(_question):
            nonlocal mutated
            if not mutated:
                with open(page, "a") as stream:
                    stream.write("\n- mutation during evaluation\n")
                mutated = True
            return {"fixture": []}

        with self.assertRaisesRegex(
                siabench.BenchmarkRefusal, "changed after dataset generation"):
            siabench.evaluate_retrieval(
                bundle, query_fn=query, corpus=self.corpus)

    def test_evaluation_refuses_replaced_corpus_root_path(self):
        bundle = self._bundle()
        replacement = self.corpus + "-replacement"
        os.replace(self.corpus, replacement)
        os.symlink(replacement, self.corpus)

        with self.assertRaisesRegex(
                siabench.BenchmarkRefusal,
                "source page .* cannot be re-opened"):
            siabench._verify_source_pages(bundle, corpus=self.corpus)

    def test_multi_event_questions_fit_the_scored_retrieval_window(self):
        original = siabench.TOP_K
        siabench.TOP_K = 1
        try:
            bundle = self._bundle()
        finally:
            siabench.TOP_K = original
        multi = [q for q in bundle["questions"]
                 if q["category"] == "multi-event-aggregation"]
        self.assertTrue(all(len(q["sources"]) <= 1 for q in multi))
        self.assertFalse(any("OUTCOME:restart" in q["question"]
                             for q in multi))

    def test_invalid_chain_config_is_an_explicit_refusal(self):
        original = siabench.sialib.CONFIG
        siabench.sialib.CONFIG = {**original, "chains": [{
            "name": "unbound",
            "ledger": os.path.join(self.state, "ledger.tsv"),
            "verify": [sys.executable, os.path.join(BIN, "sia-ledger"),
                       "verify", self.state, "--quiet"],
        }]}
        try:
            registry = {
                name: binding
                for name, binding in siabench.sialib._chain_cmds().items()
                if binding[2]
                and binding[2][0] == siabench.sialib.INVALID_CHAIN_SENTINEL
            }
            bundle = siabench.build_ledger_dataset(
                corpus=self.corpus, chain_registry=registry)
        finally:
            siabench.sialib.CONFIG = original
        self.assertTrue(registry)
        self.assertEqual(bundle["questions"], [])
        self.assertEqual(bundle["diagnostics"][0]["reason"],
                         "invalid-chain-config")

    def test_explicitly_disabled_chain_config_is_omitted_without_refusal(self):
        original = siabench.sialib.CONFIG
        siabench.sialib.CONFIG = {**original, "chains": [
            {"name": "example", "enabled": False}
        ]}
        try:
            registry = siabench.sialib._chain_cmds()
        finally:
            siabench.sialib.CONFIG = original
        self.assertFalse(any(name.startswith("config-error-")
                             for name in registry))

    def test_partial_known_chain_remains_in_scope_as_a_refusal(self):
        original = (siabench.sialib.HOME, siabench.sialib.ATTEST,
                    siabench.sialib.AEGIS_LEDGER_TOOL,
                    siabench.sialib.CONFIG)
        integration_home = os.path.join(self.temp.name, "integration-home")
        os.makedirs(os.path.join(integration_home, ".local", "share", "custos"))
        siabench.sialib.HOME = integration_home
        siabench.sialib.ATTEST = os.path.join(
            integration_home, ".local", "bin", "attest")
        siabench.sialib.AEGIS_LEDGER_TOOL = os.path.join(
            integration_home, ".local", "bin", "aegis-ledger")
        siabench.sialib.CONFIG = {"chains": []}
        try:
            binding = siabench.sialib._chain_cmds()["custos"]
            bundle = siabench.build_ledger_dataset(
                corpus=self.corpus, chain_registry={"custos": binding})
        finally:
            (siabench.sialib.HOME, siabench.sialib.ATTEST,
             siabench.sialib.AEGIS_LEDGER_TOOL,
             siabench.sialib.CONFIG) = original
        self.assertEqual(bundle["questions"], [])
        self.assertEqual(bundle["diagnostics"][0]["reason"],
                         "ledger-open-refused")

    def test_custom_chain_config_accepts_direct_and_python_script_verifiers(self):
        verifier = os.path.join(BIN, "sia-ledger")
        ledger = os.path.join(self.state, "ledger.tsv")
        original = siabench.sialib.CONFIG
        base = {"name": "custom", "ledger": ledger,
                "verifier": verifier}
        try:
            siabench.sialib.CONFIG = {**original, "chains": [{
                **base, "verify": [verifier, ledger, "--quiet"]
            }]}
            direct = siabench.sialib._chain_cmds()
            self.assertIn("custom", direct)

            siabench.sialib.CONFIG = {**original, "chains": [{
                **base, "verify": [sys.executable, verifier, "verify",
                                   ledger, "--quiet"]
            }]}
            interpreted = siabench.sialib._chain_cmds()
            self.assertIn("custom", interpreted)
        finally:
            siabench.sialib.CONFIG = original

    def test_custom_chain_config_rejects_unexecuted_verifier_and_unbound_ledger(self):
        verifier = os.path.join(BIN, "sia-ledger")
        ledger = os.path.join(self.state, "ledger.tsv")
        original = siabench.sialib.CONFIG
        base = {"name": "custom", "ledger": ledger,
                "verifier": verifier}
        cases = (
            ([shutil.which("true"), ledger, verifier],
             "exactly the executed program"),
            ([shutil.which("env"), verifier, ledger],
             "immediate script operand"),
            ([sys.executable, verifier, "verify", self.state, "--quiet"],
             "ledger is not an explicit path"),
        )
        try:
            for command, refusal in cases:
                with self.subTest(command=command):
                    siabench.sialib.CONFIG = {**original, "chains": [{
                        **base, "verify": command
                    }]}
                    registry = siabench.sialib._chain_cmds()
                    errors = [binding[2][1]
                              for name, binding in registry.items()
                              if name.startswith("config-error-")]
                    self.assertTrue(errors)
                    self.assertIn(refusal, errors[0])
                    self.assertNotIn("custom", registry)
        finally:
            siabench.sialib.CONFIG = original

    def test_unsafe_injected_verifier_binding_refuses_before_execution(self):
        ledger = os.path.join(self.state, "ledger.tsv")
        verifier = os.path.join(BIN, "sia-ledger")
        command = [shutil.which("true"), ledger, verifier]
        registry = {"fixture": (ledger, verifier, command)}

        with mock.patch.object(siabench.subprocess, "run") as execute:
            snapshots, diagnostics = siabench._snapshot_chains(
                chain_registry=registry)
        self.assertEqual(snapshots, [])
        self.assertEqual(diagnostics[0]["reason"],
                         "invalid-verifier-binding")
        execute.assert_not_called()

        with mock.patch.object(siabench.sialib, "_chain_cmds",
                               return_value=registry), \
                mock.patch.object(siabench.sialib.subprocess,
                                  "run") as execute:
            verdicts = siabench.sialib.verify_chains()
        self.assertEqual(verdicts, {"fixture": "fail"})
        execute.assert_not_called()

    def test_chain_verification_never_captures_verifier_output(self):
        ledger = os.path.join(self.state, "ledger.tsv")
        verifier = os.path.join(BIN, "sia-ledger")
        command = [sys.executable, verifier, "verify", ledger]
        registry = {"fixture": (ledger, verifier, command)}
        with open(ledger, "w"):
            pass
        with mock.patch.object(siabench.sialib, "_chain_cmds",
                               return_value=registry), \
                mock.patch.object(
                    siabench.sialib, "_run_bounded_text_process",
                    return_value=mock.Mock(returncode=0)) \
                as execute:
            verdicts = siabench.sialib.verify_chains()
        self.assertEqual(verdicts, {"fixture": "pass"})
        _args, kwargs = execute.call_args
        self.assertEqual(_args[0], command)
        self.assertEqual(kwargs["output_limit"],
                         siabench.sialib.MAX_CONFIG_BYTES)
        self.assertIsNone(kwargs["cwd"])

    def test_benchmark_snapshot_never_captures_verifier_output(self):
        with mock.patch.object(
                siabench.sialib, "_run_bounded_text_process",
                return_value=mock.Mock(returncode=0)) as execute:
            snapshots, diagnostics = siabench._snapshot_chains(
                chain_registry=self.registry)
        self.assertTrue(snapshots)
        self.assertEqual(diagnostics[0]["status"], "verified")
        _args, kwargs = execute.call_args
        self.assertEqual(_args[0], self.registry["aegis"][2])
        self.assertEqual(kwargs["output_limit"],
                         siabench.sialib.MAX_CONFIG_BYTES)
        self.assertIsNone(kwargs["cwd"])
        self.assertNotIn("text", kwargs)

    def test_attest_snapshot_splits_only_on_literal_lf(self):
        state = os.path.join(self.temp.name, "unicode-ledger")
        keeper = os.path.join(BIN, "sia-ledger")
        subprocess.run(
            [sys.executable, keeper, "init", state], check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        content_hash = hashlib.sha256(b"").hexdigest()
        signed_field = "unit\u2028name"
        subprocess.run(
            [sys.executable, keeper, "append", state, "CHECK:unit",
             signed_field, "healthy", content_hash, "0"], check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ledger = os.path.join(state, "ledger.tsv")
        registry = {
            "unicode": (
                ledger, keeper,
                [sys.executable, keeper, "verify", state, "--quiet"]),
        }
        snapshots, diagnostics = siabench._snapshot_chains(
            chain_registry=registry)
        self.assertEqual(diagnostics[0]["status"], "verified")
        self.assertEqual(snapshots[0]["rows"][-1][3], signed_field)

    def test_question_id_does_not_commit_to_private_answer(self):
        common = {
            "category": "information-extraction",
            "question": "What was recorded?",
        }
        first = siabench._make_question(
            answer="first", sources=["events/fixture/first"],
            provenance={"chain": "fixture", "entry_hash": "answer-one"},
            **common)
        second = siabench._make_question(
            answer="second", sources=["events/fixture/second"],
            provenance={"chain": "fixture", "entry_hash": "answer-two"},
            **common)
        different_private_category = siabench._make_question(
            category="abstention", question=common["question"],
            answer=siabench.ABSTAIN, sources=[],
            provenance={"chain": "fixture", "negative_witness": "private"})
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["id"], different_private_category["id"])
        self.assertEqual(
            first["id"],
            siabench._question_id({"question": common["question"]}))

    def test_abstention_template_and_public_id_do_not_reveal_answer_class(self):
        bundle = self._bundle()
        shared = [q for q in bundle["questions"]
                  if q["question"].startswith("What result did signed ")
                  and " concerning `" in q["question"]]
        self.assertTrue(any(q["answer"] == siabench.ABSTAIN for q in shared))
        self.assertTrue(any(q["answer"] != siabench.ABSTAIN for q in shared))
        templates = {
            re.sub(r"`[^`]+`", "`FIELD`", q["question"])
            for q in shared
        }
        self.assertEqual(
            templates,
            {"What result did signed aegis record for `FIELD` "
             "concerning `FIELD`?"})
        for question in shared:
            self.assertEqual(
                question["id"],
                siabench._question_id({"question": question["question"]}))

    def test_changed_results_have_distinct_public_question_wording(self):
        bundle = self._bundle()
        rows = [q for q in bundle["questions"]
                if q["category"] == "information-extraction"
                and "wireplumber.service" in q["question"]]
        self.assertEqual({q["answer"] for q in rows}, {"ok", "held"})
        self.assertEqual(len({q["question"] for q in rows}), len(rows))
        self.assertTrue(all("sequence" in q["question"] for q in rows))

    def test_latest_questions_require_latest_verified_row_source_page(self):
        os.unlink(os.path.join(self.corpus, "events", "aegis",
                               "2026-01-02.md"))
        bundle = self._bundle()
        latest = [q for q in bundle["questions"]
                  if q["category"] in ("temporal-reasoning",
                                       "knowledge-update")
                  and "`OUTCOME:restart`" in q["question"]
                  and "`wireplumber.service`" in q["question"]]
        self.assertEqual(latest, [])

    def test_public_answer_leakage_and_conflicting_wording_are_excluded(self):
        visible = siabench._make_question(
            "information-extraction", "Was the result healthy?", "healthy",
            ["events/x/day"], {"chain": "x"})
        conflict_a = siabench._make_question(
            "information-extraction", "What was the result?", "one",
            ["events/x/a"], {"chain": "x", "seq": "a"})
        conflict_b = siabench._make_question(
            "information-extraction", "What was the result?", "two",
            ["events/x/b"], {"chain": "x", "seq": "b"})
        kept, excluded = siabench._audit_questions(
            [visible, conflict_a, conflict_b])
        self.assertEqual(kept, [])
        self.assertEqual(excluded["answer_visible"], 1)
        self.assertEqual(excluded["conflicting_wording"], 2)

    def test_public_leak_audit_canonicalizes_encoded_private_values(self):
        temporal = siabench._make_question(
            "temporal-reasoning", "When was signed aegis sequence nine?",
            "2026-01-01", ["events/aegis/2026-01-01"], {"chain": "aegis"})
        encoded_slug = siabench._make_question(
            "information-extraction",
            "What happened to `events%252Faegis%252Fprivate-page`?", "ok",
            ["events/aegis/private-page"], {"chain": "aegis"})
        html_slug = siabench._make_question(
            "information-extraction",
            "What happened to `events&amp;#x2f;aegis&amp;#x2f;private-page`?",
            "ok", ["events/aegis/private-page"], {"chain": "aegis"})
        wide_date = siabench._make_question(
            "information-extraction", "What happened on `２０２６－０１－０１`?",
            "ok", ["events/aegis/other"], {"chain": "aegis"})
        kept, excluded = siabench._audit_questions(
            [temporal, encoded_slug, html_slug, wide_date],
            {"events/aegis/2026-01-01", "events/aegis/private-page"})
        self.assertEqual(kept, [temporal])
        self.assertEqual(excluded["source_slug_visible"], 2)
        self.assertEqual(excluded["temporal_answer_visible"], 1)

    def test_canonical_public_wording_closes_id_and_conflict_aliases(self):
        plain = siabench._make_question(
            "information-extraction", "What happened to `alpha/beta`?",
            "one", ["events/a"], {"chain": "aegis"})
        encoded = siabench._make_question(
            "information-extraction", "What happened to `alpha%2Fbeta`?",
            "two", ["events/b"], {"chain": "aegis"})
        self.assertEqual(plain["id"], encoded["id"])
        kept, excluded = siabench._audit_questions([plain, encoded])
        self.assertEqual(kept, [])
        self.assertEqual(excluded["conflicting_wording"], 2)

    def test_question_fields_reject_controls_bidi_and_noncharacters(self):
        for unsafe in ("alpha\x00omega", "alpha\u202eomega",
                       "alpha\ufffeomega"):
            with self.subTest(unsafe=repr(unsafe)):
                self.assertIsNone(siabench._safe_field(unsafe))
        self.assertEqual(siabench._safe_field("wireplumber.service"),
                         "wireplumber.service")

    def test_public_questions_do_not_contain_answer_keys(self):
        bundle = self._bundle()
        out = os.path.join(self.temp.name, "export")
        manifest = siabench.write_dataset(bundle, out, corpus=self.corpus)
        public = siabench._read_jsonl(os.path.join(out, "questions.jsonl"))
        private_key = siabench._read_jsonl(
            os.path.join(out, "answer-key.jsonl"))
        self.assertTrue(public)
        for row in public:
            self.assertNotIn("answer", row)
            self.assertNotIn("category", row)
            self.assertNotIn("provenance", row)
            self.assertNotIn("sources", row)
            self.assertNotIn("answer_witness", row)
        self.assertTrue(all(
            "answer_witness" in row
            for row in private_key if row["answer"] != siabench.ABSTAIN))
        self.assertTrue(all(
            "answer_witness" not in row
            for row in private_key if row["answer"] == siabench.ABSTAIN))
        mode = stat.S_IMODE(os.stat(os.path.join(out, "answer-key.jsonl")).st_mode)
        self.assertEqual(mode, 0o600)
        private_manifest_path = os.path.join(out, "private-manifest.json")
        self.assertEqual(stat.S_IMODE(os.stat(private_manifest_path).st_mode),
                         0o600)
        with open(private_manifest_path) as stream:
            private_manifest = json.load(stream)
        self.assertIn("answer_key_sha256", private_manifest)
        self.assertIn("mcp_evaluation_sha256", private_manifest)
        with open(os.path.join(out, "manifest.json")) as stream:
            public_manifest_text = stream.read()
        public_manifest = json.loads(public_manifest_text)
        self.assertEqual(private_manifest["public_manifest_sha256"],
                         siabench._sha_text(public_manifest_text))
        self.assertNotIn("source_pages", public_manifest)
        self.assertNotIn("witness_files", public_manifest)
        self.assertNotIn("chains", public_manifest)
        self.assertEqual(set(public_manifest),
                         siabench.PUBLIC_MANIFEST_FIELDS)
        private_evaluation = private_manifest["evaluation_manifest"]
        self.assertEqual(
            private_manifest["evaluation_manifest_sha256"],
            siabench._sha_text(siabench._canonical(private_evaluation)))
        self.assertEqual(private_evaluation["source_pages"],
                         bundle["manifest"]["source_pages"])
        self.assertEqual(private_evaluation["witness_files"],
                         bundle["manifest"]["witness_files"])
        self.assertNotIn("answer_key_sha256", manifest)
        self.assertNotIn("mcp_evaluation_sha256", manifest)
        evaluation_path = os.path.join(out, "mcp-evaluation.xml")
        self.assertEqual(stat.S_IMODE(os.stat(evaluation_path).st_mode), 0o600)
        root = ET.parse(evaluation_path).getroot()
        pairs = root.findall("qa_pair")
        self.assertTrue(pairs)
        self.assertLessEqual(len(pairs), siabench.MCP_EVALUATION_LIMIT)
        self.assertTrue(all(pair.findtext("question")
                            and pair.findtext("answer") for pair in pairs))
        self.assertEqual(manifest["answer_key_location"],
                         "separate-file-outside-indexed-corpus")
        with self.assertRaisesRegex(ValueError, "inside indexed corpus"):
            siabench.write_dataset(bundle, os.path.join(self.corpus, "leak"),
                                   corpus=self.corpus)

        # Even a self-consistent local rewrite cannot add private evaluation
        # fields back to the v2 public schema.
        public_manifest["source_pages"] = bundle["manifest"]["source_pages"]
        leaked_text = json.dumps(
            public_manifest, indent=2, sort_keys=True) + "\n"
        with open(os.path.join(out, "manifest.json"), "w",
                  encoding="utf-8") as stream:
            stream.write(leaked_text)
        private_manifest["public_manifest_sha256"] = \
            siabench._sha_text(leaked_text)
        with open(private_manifest_path, "w", encoding="utf-8") as stream:
            json.dump(private_manifest, stream)
        with self.assertRaisesRegex(
                ValueError, "public benchmark manifest fields"):
            siabench.load_dataset(out)

    def test_normalized_scorer_counts_abstention_and_missing_is_not_abstain(self):
        bundle = self._bundle()
        out = os.path.join(self.temp.name, "dataset")
        siabench.write_dataset(bundle, out, corpus=self.corpus)
        predictions = os.path.join(self.temp.name, "answers.jsonl")
        eval_rows = [q for q in bundle["questions"]
                     if q["split"] == "evaluation"]
        with open(predictions, "w") as stream:
            for row in eval_rows:
                stream.write(json.dumps({"id": row["id"],
                                         "answer": row["answer"]}) + "\n")
        score = siabench.score_answer_file(out, predictions)
        self.assertEqual(score["correct"], score["evaluation_total"])
        self.assertEqual(score["abstention_correct"], score["abstention_total"])
        self.assertTrue(all("expected" not in row for row in score["rows"]))
        self.assertTrue(all("category" not in row for row in score["rows"]))
        with open(predictions, "w") as stream:
            stream.write("")
        empty = siabench.score_answer_file(out, predictions)
        self.assertEqual(empty["submitted"], 0)
        self.assertEqual(empty["correct"], 0)

        with open(predictions, "w") as stream:
            stream.write(json.dumps({"id": eval_rows[0]["id"]}) + "\n")
        with self.assertRaisesRegex(ValueError, "explicit string answer"):
            siabench.score_answer_file(out, predictions)
        with open(predictions, "w") as stream:
            stream.write(json.dumps({"id": eval_rows[0]["id"],
                                     "answer": None}) + "\n")
        with self.assertRaisesRegex(ValueError, "explicit string answer"):
            siabench.score_answer_file(out, predictions)

    def test_verified_buffers_are_parsed_once_and_duplicate_keys_refuse(self):
        bundle = self._bundle()
        out = os.path.join(self.temp.name, "dataset")
        siabench.write_dataset(bundle, out, corpus=self.corpus)
        old_reader = siabench._read_jsonl
        siabench._read_jsonl = lambda _path: self.fail(
            "load_dataset reopened a digest-checked JSONL path")
        try:
            _manifest, questions, keys = siabench.load_dataset(out)
        finally:
            siabench._read_jsonl = old_reader
        self.assertEqual({q["id"] for q in questions},
                         {k["id"] for k in keys})

        key_path = os.path.join(out, "answer-key.jsonl")
        with open(key_path) as stream:
            key_text = stream.read()
        duplicated = key_text + key_text.splitlines()[0] + "\n"
        with open(key_path, "w") as stream:
            stream.write(duplicated)
        private_path = os.path.join(out, "private-manifest.json")
        with open(private_path) as stream:
            private_manifest = json.load(stream)
        private_manifest["answer_key_sha256"] = siabench._sha_text(duplicated)
        with open(private_path, "w") as stream:
            json.dump(private_manifest, stream)
        with self.assertRaisesRegex(ValueError, "answer-key IDs must be unique"):
            siabench.load_dataset(out)

    def test_keeper_rejection_yields_refusal_not_questions(self):
        ledger = os.path.join(self.state, "ledger.tsv")
        with open(ledger) as stream:
            text = stream.read().replace("\theld\t", "\nBAD\t", 1)
        with open(ledger, "w") as stream:
            stream.write(text)
        bundle = self._bundle()
        self.assertEqual(bundle["questions"], [])
        self.assertEqual(bundle["diagnostics"][0]["status"], "refused")
        self.assertEqual(bundle["diagnostics"][0]["reason"], "keeper-rejected")
        with self.assertRaises(siabench.BenchmarkRefusal):
            siabench.write_dataset(
                bundle, os.path.join(self.temp.name, "rejected"),
                corpus=self.corpus)

    def test_unknown_chain_and_empty_generation_refuse(self):
        unknown = siabench.build_ledger_dataset(
            corpus=self.corpus, chain_registry=self.registry,
            chain_names=["not-registered"])
        self.assertEqual(unknown["diagnostics"][0]["reason"],
                         "unknown-requested-chain")
        with self.assertRaises(siabench.BenchmarkRefusal):
            siabench.write_dataset(
                unknown, os.path.join(self.temp.name, "unknown"),
                corpus=self.corpus)

        empty = {"questions": [], "diagnostics": [
            {"chain": "fixture", "status": "verified"}]}
        old_builder = siabench.build_ledger_dataset
        siabench.build_ledger_dataset = lambda **_kwargs: empty
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(stderr):
                status_code = siabench.main([
                    "generate", "--out", os.path.join(self.temp.name, "empty")])
        finally:
            siabench.build_ledger_dataset = old_builder
        self.assertNotEqual(status_code, 0)
        self.assertIn("REFUSED", stderr.getvalue())

    def test_symlink_and_observed_ledger_mutation_refuse(self):
        ledger = os.path.join(self.state, "ledger.tsv")
        target = ledger + ".regular"
        os.replace(ledger, target)
        os.symlink(target, ledger)
        linked = self._bundle()
        self.assertEqual(linked["diagnostics"][0]["reason"],
                         "ledger-open-refused")

        os.unlink(ledger)
        os.replace(target, ledger)
        real_run = siabench.sialib._run_bounded_text_process

        def mutate_after_verify(*args, **kwargs):
            result = real_run(*args, **kwargs)
            with open(ledger, "a") as stream:
                stream.write("\n")
            return result

        siabench.sialib._run_bounded_text_process = mutate_after_verify
        try:
            raced = self._bundle()
        finally:
            siabench.sialib._run_bounded_text_process = real_run
        self.assertEqual(raced["diagnostics"][0]["reason"],
                         "ledger-changed-during-verification")

    def test_symlinked_parent_components_refuse_snapshot_intake(self):
        state_link = os.path.join(self.temp.name, "linked-state")
        os.symlink(self.state, state_link)
        ledger_registry = {
            "fixture": (os.path.join(state_link, "ledger.tsv"),
                        self.registry["aegis"][1],
                        self.registry["aegis"][2]),
        }
        ledger_bundle = siabench.build_ledger_dataset(
            corpus=self.corpus, chain_registry=ledger_registry)
        self.assertEqual(ledger_bundle["diagnostics"][0]["reason"],
                         "ledger-open-refused")

        verifier_dir = os.path.join(self.temp.name, "verifier-real")
        os.makedirs(verifier_dir)
        verifier = os.path.join(verifier_dir, "sia-ledger")
        shutil.copyfile(os.path.join(BIN, "sia-ledger"), verifier)
        verifier_link = os.path.join(self.temp.name, "verifier-linked")
        os.symlink(verifier_dir, verifier_link)
        linked_verifier = os.path.join(verifier_link, "sia-ledger")
        verifier_registry = {
            "fixture": (os.path.join(self.state, "ledger.tsv"),
                        linked_verifier,
                        [sys.executable, linked_verifier, "verify",
                         self.state, "--quiet"]),
        }
        verifier_bundle = siabench.build_ledger_dataset(
            corpus=self.corpus, chain_registry=verifier_registry)
        self.assertEqual(verifier_bundle["diagnostics"][0]["reason"],
                         "keeper-verifier-open-refused")

    def test_symlink_source_page_refuses_dataset_intake(self):
        page = os.path.join(self.corpus, "events", "aegis",
                            "2026-01-01.md")
        target = page + ".regular"
        os.replace(page, target)
        os.symlink(target, page)
        bundle = self._bundle()
        refused = [item for item in bundle["diagnostics"]
                   if item.get("reason") == "corpus-page-open-refused"]
        self.assertTrue(refused)
        with self.assertRaises(siabench.BenchmarkRefusal):
            siabench.write_dataset(
                bundle, os.path.join(self.temp.name, "source-refused"),
                corpus=self.corpus)

    def test_symlinked_source_page_parent_refuses_dataset_intake(self):
        fixture_dir = os.path.join(self.corpus, "events", "aegis")
        real_dir = os.path.join(self.corpus, "events", "aegis-real")
        os.replace(fixture_dir, real_dir)
        os.symlink(real_dir, fixture_dir)
        bundle = self._bundle()
        refused = [item for item in bundle["diagnostics"]
                   if item.get("reason") in {
                       "corpus-page-open-refused",
                       "event-directory-open-refused"}]
        self.assertTrue(refused)

    def test_observed_verifier_mutation_refuses_snapshot(self):
        verifier = os.path.join(self.temp.name, "fixture-verifier")
        shutil.copyfile(os.path.join(BIN, "sia-ledger"), verifier)
        registry = {
            "fixture": (os.path.join(self.state, "ledger.tsv"), verifier,
                        [sys.executable, verifier, "verify", self.state,
                         "--quiet"]),
        }
        real_run = siabench.sialib._run_bounded_text_process

        def mutate_after_verify(*args, **kwargs):
            result = real_run(*args, **kwargs)
            with open(verifier, "a") as stream:
                stream.write("\n# observed mutation\n")
            return result

        siabench.sialib._run_bounded_text_process = mutate_after_verify
        try:
            bundle = siabench.build_ledger_dataset(
                corpus=self.corpus, chain_registry=registry)
        finally:
            siabench.sialib._run_bounded_text_process = real_run
        self.assertEqual(bundle["diagnostics"][0]["reason"],
                         "keeper-verifier-changed-during-verification")

    def test_permissive_verifier_cannot_admit_malformed_attest_rows(self):
        ledger = os.path.join(self.state, "ledger.tsv")
        with open(ledger) as stream:
            rows = stream.read().splitlines()
        columns = rows[-1].split("\t")
        columns[-1] = "00"
        rows[-1] = "\t".join(columns)
        with open(ledger, "w") as stream:
            stream.write("\n".join(rows) + "\n")
        true_tool = shutil.which("true")
        registry = {"fixture": (ledger, true_tool, [true_tool])}
        bundle = siabench.build_ledger_dataset(
            corpus=self.corpus, chain_registry=registry)
        self.assertEqual(bundle["questions"], [])
        self.assertEqual(bundle["diagnostics"][0]["reason"],
                         "strict-row-parse-refused")

    def test_sparse_threshold_fails_closed(self):
        threshold, status_name = siabench.choose_abstention_threshold(
            [(0.5, True)])
        self.assertIsNone(threshold)
        self.assertEqual(status_name, "insufficient-calibration-classes")

        bundle = {"questions": [
            {"id": "cal", "question": "calibration negative",
             "split": "calibration", "answer": siabench.ABSTAIN,
             "sources": [], "category": "abstention"},
            {"id": "eval", "question": "evaluation negative",
             "split": "evaluation", "answer": siabench.ABSTAIN,
             "sources": [], "category": "abstention"},
        ]}
        report = siabench.evaluate_retrieval(
            bundle, query_fn=lambda _question: {"fixture": []})["fixture"]
        self.assertFalse(report["scored"])
        self.assertIsNone(report["correct"])
        self.assertIsNone(report["false_nonabstentions"])

    def test_negative_retrieval_is_labeled_nonabstention_not_answer(self):
        bundle = {"manifest": {"dataset_id": "fixture",
                               "non_claims": []},
                  "questions": [
            {"id": "present", "question": "calibration present",
             "split": "calibration", "answer": "recorded",
             "sources": ["events/fixture/day"],
             "category": "information-extraction"},
            {"id": "absent", "question": "calibration absent",
             "split": "calibration", "answer": siabench.ABSTAIN,
             "sources": [], "category": "abstention"},
            {"id": "heldout", "question": "held-out absent",
             "split": "evaluation", "answer": siabench.ABSTAIN,
             "sources": [], "category": "abstention"},
        ]}

        def query(question):
            if question == "calibration absent":
                return {"fixture": []}
            return {"fixture": [{"slug": "events/fixture/day",
                                  "score": 1.0}]}

        report = siabench.evaluate_retrieval(bundle, query_fn=query)["fixture"]
        self.assertTrue(report["scored"])
        self.assertEqual(report["false_nonabstentions"], 1)
        self.assertNotIn("false_answers", report)
        rendered = siabench.render_retrieval_report(
            bundle, {"fixture": report})
        self.assertIn("retrieval non-abstention proxy", rendered)
        self.assertNotIn("false answers", rendered)


if __name__ == "__main__":
    unittest.main()
