#!/usr/bin/env python3
"""Regression contracts for the historical ``sia/cortex`` claim boundary.

Every fixture lives below a per-test home.  These tests must never inspect or
mutate the operator's resident corpus or gbrain state.
"""

import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")
SIALIB_PATH = os.path.join(BIN, "sialib.py")
SIA_PATH = os.path.join(BIN, "sia")

BRAIN_METAPHOR_BOUNDARY = (
    "“Brain” is a product metaphor for auditable local machine memory; it is "
    "not a biological brain and does not establish cognition or neuroscience."
)

# This is the page emitted by the historical root constructor.  It is corpus
# history, not a template that the repair may silently replace.
LEGACY_CORTEX = (
    "---\n"
    "type: organ\n"
    "title: \"SIA cortex\"\n"
    "---\n"
    "# SIA cortex\n\n"
    "I am SIA, the Omarchy Brain — the associative memory of this machine.\n"
    "Every enabled organ below reports what it observes. Each configured\n"
    "signed chain is checked by its own keeper verifier; Custos also uses\n"
    "the SPARK-proved `attest` verifier. Deterministic thought generators\n"
    "are evidence-derived; user/model prose is origin-labeled.\n\n"
)

REPAIR_SCHEMA = "sia-cortex-boundary-repair-v1"
JOURNAL_SCHEMA = "sia-cortex-boundary-repair-journal-v1"


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class CortexBoundaryRepair(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name

        def expanduser(path):
            if path == "~":
                return self.home
            if isinstance(path, str) and path.startswith("~/"):
                return os.path.join(self.home, path[2:])
            return sia_test_home._REAL_EXPANDUSER(path)

        # Resolve every import-time mutable path into this test's private home.
        with mock.patch("os.path.expanduser", side_effect=expanduser):
            self.sialib = _load(
                "sialib_cortex_" + self._testMethodName, SIALIB_PATH)
        self.sialib.ORGANS = {}
        self.sialib.ensure_dirs()
        self.cortex = self.sialib.corpus_path("sia/cortex")
        os.makedirs(os.path.dirname(self.cortex), exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_cortex(self, value=LEGACY_CORTEX):
        mode = "wb" if isinstance(value, bytes) else "w"
        kwargs = {} if isinstance(value, bytes) else {"encoding": "utf-8"}
        with open(self.cortex, mode, **kwargs) as stream:
            stream.write(value)

    def _cortex_bytes(self):
        with open(self.cortex, "rb") as stream:
            return stream.read()

    def _state_records(self, schema):
        records = []
        for directory, _children, names in os.walk(self.sialib.STATE):
            for name in names:
                if not name.endswith(".json"):
                    continue
                path = os.path.join(directory, name)
                try:
                    with open(path, encoding="utf-8") as stream:
                        value = json.load(stream)
                except (OSError, UnicodeError, ValueError):
                    continue
                if isinstance(value, dict) and value.get("schema") == schema:
                    records.append((path, value))
        return records

    def _readiness(self):
        sialib = self.sialib
        real_read_json = sialib.read_json

        def read_json(path, default=None):
            if path == sialib.GRAPH_PATH:
                return {}
            return real_read_json(path, default)

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                sialib, "corpus_owner",
                return_value=contextlib.nullcontext()))
            stack.enter_context(mock.patch.object(
                sialib, "load_memo", return_value={"sync_needed": False}))
            for name in (
                    "_pending_notify_baseline_attempt",
                    "_pending_source_replay_marker",
                    "_pending_pulse_marker",
                    "_pending_dream_marker",
                    "_pending_consolidation_marker",
                    "_pending_pulse_status_effects",
                    "_pending_dream_unit"):
                stack.enter_context(mock.patch.object(
                    sialib, name, return_value=None))
            for name in (
                    "_consolidation_scan_debt", "_thought_recovery_debt",
                    "_graph_projection_debt"):
                stack.enter_context(mock.patch.object(
                    sialib, name, return_value=""))
            stack.enter_context(mock.patch.object(
                sialib, "_ready_receipt", return_value={"v": 1}))
            stack.enter_context(mock.patch.object(
                sialib.siamind, "load_mind", return_value={}))
            for name in (
                    "natural_history_recovery_required",
                    "grade_recovery_required", "take_migration_required",
                    "intent_history_required"):
                stack.enter_context(mock.patch.object(
                    sialib.siatakes, name, return_value=False))
            stack.enter_context(mock.patch.object(
                sialib, "read_json", side_effect=read_json))
            stack.enter_context(mock.patch.object(
                sialib, "_require_recoverable_graph_snapshot",
                return_value={}))
            stack.enter_context(mock.patch.object(
                sialib, "ledger_contains", return_value=True))
            stack.enter_context(mock.patch.object(
                sialib, "_durable_status_log_message",
                side_effect=lambda value, limit=400: str(value)))
            return sialib.memory_readiness()

    def _repair_records_for(self, source, target):
        appended = target[len(source):]
        order = 123456789
        receipt = self.sialib._cortex_repair_receipt(
            source, target, appended, order)
        journal = {
            **receipt,
            "schema": self.sialib.CORTEX_BOUNDARY_REPAIR_JOURNAL_SCHEMA,
            "append_text": appended.decode("utf-8"),
            "order": order,
            "action": "MIGRATE:cortex-boundary-repair",
            "arg1": "sia/cortex",
            "arg2": "product-metaphor-boundary-additive-v1",
            "content": self.sialib._cortex_receipt_text(receipt),
        }
        return receipt, journal

    def test_historical_root_repair_is_append_only_and_ledger_bound_once(self):
        self._write_cortex()
        original = self._cortex_bytes()
        sentinel = os.path.join(self.sialib.CORPUS, "notes", "keep.md")
        os.makedirs(os.path.dirname(sentinel), exist_ok=True)
        sentinel_bytes = b"retained corpus page\n"
        with open(sentinel, "wb") as stream:
            stream.write(sentinel_bytes)

        observations = []

        def settle(action, arg1, arg2, content="", order=None):
            observations.append({
                "action": action, "arg1": arg1, "arg2": arg2,
                "content": content, "order": order,
                "root": self._cortex_bytes(),
                "journals": self._state_records(JOURNAL_SCHEMA),
                "receipts": self._state_records(REPAIR_SCHEMA),
            })
            return True

        with mock.patch.object(
                self.sialib, "durable_ledger_append",
                side_effect=settle):
            self.assertTrue(self.sialib.ensure_organs())
            repaired = self._cortex_bytes()
            self.assertEqual(repaired[:len(original)], original)
            self.assertEqual(
                repaired.count(BRAIN_METAPHOR_BOUNDARY.encode("utf-8")), 1)
            self.assertEqual(self._cortex_bytes(), observations[0]["root"])
            self.assertTrue(observations[0]["journals"])
            self.assertEqual(len(observations[0]["receipts"]), 1)

            receipts = self._state_records(REPAIR_SCHEMA)
            self.assertEqual(len(receipts), 1)
            receipt = receipts[0][1]
            self.assertEqual(receipt["slug"], "sia/cortex")
            self.assertEqual(receipt["operation"], "append-only")
            self.assertEqual(
                receipt["source_sha256"], hashlib.sha256(original).hexdigest())
            self.assertEqual(
                receipt["target_sha256"], hashlib.sha256(repaired).hexdigest())
            self.assertEqual(
                receipt["appended_sha256"],
                hashlib.sha256(repaired[len(original):]).hexdigest())
            self.assertEqual(
                json.loads(observations[0]["content"]), receipt)
            self.assertIn("repair", observations[0]["action"].casefold())
            self.assertEqual(observations[0]["arg1"], "sia/cortex")
            self.assertIn("boundary", observations[0]["arg2"].casefold())
            self.assertEqual(self._state_records(JOURNAL_SCHEMA), [])

            # A completed witness makes retries inert: no second suffix and no
            # second signed occurrence are attempted.
            self.assertFalse(self.sialib.ensure_organs())
        self.assertEqual(len(observations), 1)
        self.assertEqual(self._cortex_bytes(), repaired)
        with open(sentinel, "rb") as stream:
            self.assertEqual(stream.read(), sentinel_bytes)

    def test_write_ahead_journal_recovers_the_unmodified_source_state(self):
        self._write_cortex()
        source = self._cortex_bytes()
        real_atomic_write = self.sialib.atomic_write
        barrier_seen = []
        attempted = {}

        def fail_cortex_write(path, data, **kwargs):
            if path == self.cortex:
                attempted["target"] = data.encode("utf-8")
                attempted["journals"] = self._state_records(JOURNAL_SCHEMA)
                attempted["barrier_seen"] = bool(barrier_seen)
                raise OSError("fixture interruption before cortex publish")
            return real_atomic_write(path, data, **kwargs)

        with mock.patch.object(
                self.sialib, "_before_corpus_mutation",
                side_effect=lambda: barrier_seen.append(True)), \
                mock.patch.object(
                    self.sialib, "atomic_write",
                    side_effect=fail_cortex_write), \
                mock.patch.object(
                    self.sialib, "durable_ledger_append") as ledger:
            with self.assertRaisesRegex(OSError, "fixture interruption"):
                self.sialib.ensure_organs()
        ledger.assert_not_called()
        self.assertEqual(self._cortex_bytes(), source)
        self.assertTrue(attempted["barrier_seen"])
        self.assertEqual(len(attempted["journals"]), 1)
        journal = attempted["journals"][0][1]
        self.assertEqual(
            journal["source_sha256"], hashlib.sha256(source).hexdigest())
        self.assertEqual(
            journal["target_sha256"],
            hashlib.sha256(attempted["target"]).hexdigest())

        with mock.patch.object(
                self.sialib, "durable_ledger_append",
                return_value=True) as ledger:
            self.assertTrue(self.sialib.ensure_organs())
        ledger.assert_called_once()
        self.assertEqual(self._state_records(JOURNAL_SCHEMA), [])
        repaired = self._cortex_bytes()
        self.assertEqual(repaired[:len(source)], source)
        self.assertEqual(
            repaired.count(BRAIN_METAPHOR_BOUNDARY.encode("utf-8")), 1)

    def test_repair_separates_boundary_after_source_without_terminal_newline(self):
        source = LEGACY_CORTEX.rstrip("\n").encode("utf-8")
        self._write_cortex(source)

        with mock.patch.object(
                self.sialib, "durable_ledger_append", return_value=True):
            self.assertTrue(self.sialib.ensure_organs())

        repaired = self._cortex_bytes()
        self.assertEqual(repaired[:len(source)], source)
        self.assertTrue(repaired[len(source):].startswith(
            b"\n\n## Current product-metaphor boundary\n"))

    def test_barrier_change_is_refused_without_overwriting_new_cortex_bytes(self):
        self._write_cortex()
        replacement = (
            LEGACY_CORTEX
            + "\n# retained concurrent edit\n\noperator-owned update\n").encode(
                "utf-8")
        barrier_calls = []

        def replace_during_barrier():
            barrier_calls.append(True)
            with open(self.cortex, "wb") as stream:
                stream.write(replacement)

        with mock.patch.object(
                self.sialib, "_before_corpus_mutation",
                side_effect=replace_during_barrier), \
                mock.patch.object(
                    self.sialib, "durable_ledger_append") as ledger, \
                self.assertRaisesRegex(
                    RuntimeError, "changed before repair publication"):
            self.sialib.ensure_organs()

        self.assertEqual(barrier_calls, [True])
        ledger.assert_not_called()
        self.assertEqual(self._cortex_bytes(), replacement)
        self.assertEqual(len(self._state_records(JOURNAL_SCHEMA)), 1)

    def test_inert_boundary_occurrence_is_not_a_current_or_witnessed_root(self):
        source = (
            "---\n"
            "type: organ\n"
            "title: \"SIA cortex\"\n"
            "---\n"
            "# SIA cortex\n\n"
            "<!-- " + BRAIN_METAPHOR_BOUNDARY + " -->\n\n"
            "I am SIA, the Omarchy Brain.\n"
        )
        self._write_cortex(source)

        with mock.patch.object(
                self.sialib, "durable_ledger_append") as ledger, \
                self.assertRaisesRegex(
                    RuntimeError, "neither the current root nor a witnessed"):
            self.sialib.ensure_organs()

        ledger.assert_not_called()
        self.assertEqual(self._cortex_bytes(), source.encode("utf-8"))

    def test_malformed_exact_target_recovery_refuses_before_signed_ledger(self):
        source = b"not a cortex root"
        target = source + self.sialib.CORTEX_BOUNDARY_REPAIR_SUFFIX.encode(
            "utf-8")
        receipt, journal = self._repair_records_for(source, target)
        self._write_cortex(target)
        self.sialib._write_cortex_repair_state(
            self.sialib.CORTEX_BOUNDARY_REPAIR_RECEIPT, receipt)
        self.sialib._write_cortex_repair_state(
            self.sialib.CORTEX_BOUNDARY_REPAIR_JOURNAL, journal)

        with mock.patch.object(
                self.sialib, "durable_ledger_append") as ledger, \
                self.assertRaisesRegex(RuntimeError, "frontmatter is malformed"):
            self.sialib.ensure_organs()

        ledger.assert_not_called()
        self.assertEqual(self._cortex_bytes(), target)
        self.assertEqual(len(self._state_records(JOURNAL_SCHEMA)), 1)

    def test_fresh_root_is_exact_current_bytes_and_needs_no_repair_receipt(self):
        with mock.patch.object(
                self.sialib, "durable_ledger_append") as ledger:
            self.assertTrue(self.sialib.ensure_organs())
            self.assertFalse(self.sialib.ensure_organs())

        ledger.assert_not_called()
        self.assertEqual(
            self._cortex_bytes(), self.sialib._current_cortex_root_bytes())
        self.assertEqual(self._state_records(REPAIR_SCHEMA), [])
        self.assertEqual(self._state_records(JOURNAL_SCHEMA), [])
        self.assertEqual(
            self.sialib._cortex_boundary_status(require_ledger=True),
            (True, ""))

    def test_root_admission_refuses_unsafe_identity_encoding_and_size(self):
        cases = (
            ("invalid-utf8", b"---\ntype: organ\n---\n# cortex\n\xff", None),
            ("group-writable", LEGACY_CORTEX.encode("utf-8"), 0o660),
            ("world-writable", LEGACY_CORTEX.encode("utf-8"), 0o606),
            ("over-bound", LEGACY_CORTEX.encode("utf-8")
             + b"x" * self.sialib.MAX_CONFIG_BYTES, None),
        )
        for label, raw, mode in cases:
            with self.subTest(label=label):
                self._write_cortex(raw)
                os.chmod(self.cortex, 0o644 if mode is None else mode)
                before = self._cortex_bytes()
                with mock.patch.object(
                        self.sialib, "durable_ledger_append") as ledger, \
                        self.assertRaises(RuntimeError):
                    self.sialib.ensure_organs()
                ledger.assert_not_called()
                self.assertEqual(self._cortex_bytes(), before)
                self.assertEqual(self._state_records(REPAIR_SCHEMA), [])
                self.assertEqual(self._state_records(JOURNAL_SCHEMA), [])

        self._write_cortex()
        alias = self.cortex + ".alias"
        os.link(self.cortex, alias)
        try:
            before = self._cortex_bytes()
            with mock.patch.object(
                    self.sialib, "durable_ledger_append") as ledger, \
                    self.assertRaisesRegex(RuntimeError, "single-link"):
                self.sialib.ensure_organs()
            ledger.assert_not_called()
            self.assertEqual(self._cortex_bytes(), before)
        finally:
            os.unlink(alias)

    def test_root_shape_and_duplicate_boundary_refuse_before_repair(self):
        cases = (
            "---\ntype: thought\n---\n# SIA cortex\n",
            "---\ntype: organ\n---\nnot an h1\n",
            "---\ntype: organ\n---\n# SIA cortex\n\n"
            + BRAIN_METAPHOR_BOUNDARY + "\n"
            + BRAIN_METAPHOR_BOUNDARY + "\n",
        )
        for source in cases:
            with self.subTest(source=source[:40]):
                self._write_cortex(source)
                with mock.patch.object(
                        self.sialib, "durable_ledger_append") as ledger, \
                        self.assertRaises(RuntimeError):
                    self.sialib.ensure_organs()
                ledger.assert_not_called()
                self.assertEqual(self._cortex_bytes(), source.encode("utf-8"))
                self.assertEqual(self._state_records(REPAIR_SCHEMA), [])
                self.assertEqual(self._state_records(JOURNAL_SCHEMA), [])

    def test_post_ledger_target_change_retains_journal_and_refuses(self):
        self._write_cortex()
        changed = []

        def mutate_after_sign(*_args, **_kwargs):
            with open(self.cortex, "ab") as stream:
                stream.write(b"\npost-ledger mutation\n")
            changed.append(True)
            return True

        with mock.patch.object(
                self.sialib, "durable_ledger_append",
                side_effect=mutate_after_sign), \
                self.assertRaisesRegex(
                    RuntimeError, "changed before retirement"):
            self.sialib.ensure_organs()

        self.assertEqual(changed, [True])
        self.assertEqual(len(self._state_records(JOURNAL_SCHEMA)), 1)

    def test_repaired_root_readiness_requires_exact_ledger_occurrence(self):
        self._write_cortex()
        with mock.patch.object(
                self.sialib, "durable_ledger_append", return_value=True):
            self.assertTrue(self.sialib.ensure_organs())
        receipt = self._state_records(REPAIR_SCHEMA)[0][1]
        expected_basis = self.sialib._pending_basis(
            receipt["ledger_order"], "MIGRATE:cortex-boundary-repair",
            "sia/cortex", "product-metaphor-boundary-additive-v1",
            self.sialib._cortex_receipt_text(receipt))

        with mock.patch.object(
                self.sialib, "ledger_contains", return_value=False) as contains:
            ready, reason = self.sialib._cortex_boundary_status()
        self.assertFalse(ready)
        self.assertIn("ledger receipt is missing", reason)
        self.assertEqual(
            contains.call_args.kwargs["occurrence_id"],
            self.sialib._pending_identity(expected_basis))

        with mock.patch.object(
                self.sialib, "ledger_contains", return_value=True):
            self.assertEqual(self.sialib._cortex_boundary_status(), (True, ""))

    def test_readiness_blocks_old_and_unsettled_target_states(self):
        self._write_cortex()
        ready, reason = self._readiness()
        self.assertFalse(ready)
        self.assertIn("cortex", reason.casefold())
        self.assertIn("boundary", reason.casefold())

        first_ledger_attempt = []

        def indeterminate_settlement(*args, **kwargs):
            first_ledger_attempt.append(mock.call(*args, **kwargs))
            raise self.sialib.LedgerTransitionError(
                "fixture keeper acknowledgment lost")

        with mock.patch.object(
                self.sialib, "durable_ledger_append",
                side_effect=indeterminate_settlement):
            with self.assertRaisesRegex(
                    self.sialib.LedgerTransitionError,
                    "fixture keeper acknowledgment lost"):
                self.sialib.ensure_organs()
        target = self._cortex_bytes()
        self.assertIn(BRAIN_METAPHOR_BOUNDARY.encode("utf-8"), target)
        self.assertEqual(len(self._state_records(JOURNAL_SCHEMA)), 1)

        ready, reason = self._readiness()
        self.assertFalse(ready)
        self.assertIn("cortex", reason.casefold())
        self.assertIn("pending", reason.casefold())

        with mock.patch.object(
                self.sialib, "durable_ledger_append",
                return_value=True) as ledger:
            self.assertTrue(self.sialib.ensure_organs())
        ledger.assert_called_once()
        self.assertEqual(first_ledger_attempt, [ledger.call_args])
        args, kwargs = ledger.call_args
        order = kwargs.get("order", args[4] if len(args) > 4 else None)
        self.assertIsNotNone(order)
        self.assertEqual(self._cortex_bytes(), target)
        self.assertEqual(self._state_records(JOURNAL_SCHEMA), [])
        self.assertEqual(self._readiness(), (True, ""))

class AskCortexBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name

        def expanduser(path):
            if path == "~":
                return self.home
            if isinstance(path, str) and path.startswith("~/"):
                return os.path.join(self.home, path[2:])
            return sia_test_home._REAL_EXPANDUSER(path)

        with mock.patch("os.path.expanduser", side_effect=expanduser):
            self.sialib = _load("sialib_cortex_ask", SIALIB_PATH)
        with mock.patch.dict(sys.modules, {"sialib": self.sialib}):
            self.cli = _load("sia_cortex_ask", SIA_PATH)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ask_prints_full_boundary_before_the_cortex_excerpt(self):
        result = subprocess.CompletedProcess(
            [], 0,
            json.dumps([{
                "slug": "sia/cortex", "type": "organ",
                "title": "SIA cortex", "score": 1.0,
                "chunk_text": (
                    "historical cortex prose that does not carry the "
                    "current product-metaphor disclosure"),
            }]),
            "",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(
                self.cli, "_gbrain_query", return_value=result), \
                mock.patch.object(
                    self.sialib, "associative_rerank_enabled",
                    return_value=False), \
                mock.patch.object(
                    self.sialib, "corpus_origin", return_value="evidence"), \
                mock.patch.object(
                    self.sialib.siamind, "ppr_rerank",
                    return_value=[("sia/cortex", 1.0)]), \
                mock.patch.object(
                    self.cli, "_health_footer",
                    return_value="boundary: fixture"), \
                contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            status = self.cli.cmd_ask("what is sia", touch=False)

        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")
        rendered = stdout.getvalue()
        self.assertEqual(rendered.count(BRAIN_METAPHOR_BOUNDARY), 1)
        self.assertLess(rendered.index("sia/cortex"),
                        rendered.index(BRAIN_METAPHOR_BOUNDARY))
        self.assertLess(rendered.index(BRAIN_METAPHOR_BOUNDARY),
                        rendered.index("historical cortex prose"))

    def test_recall_prints_full_boundary_before_returned_cortex_prose(self):
        stale = subprocess.CompletedProcess(
            [], 0, "historical unqualified cortex prose\n", "")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(
                self.sialib, "page_exists", return_value=True), \
                mock.patch.object(
                    self.sialib, "unverified_jackal_recall_page",
                    return_value=False), \
                mock.patch.object(
                    self.sialib, "corpus_origin", return_value="evidence"), \
                mock.patch.object(
                    self.cli, "_gbrain_read", return_value=stale), \
                contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            status = self.cli.cmd_recall("sia/cortex", touch=False)

        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")
        rendered = stdout.getvalue()
        self.assertEqual(rendered.count(BRAIN_METAPHOR_BOUNDARY), 1)
        self.assertLess(rendered.index(BRAIN_METAPHOR_BOUNDARY),
                        rendered.index("historical unqualified cortex prose"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
