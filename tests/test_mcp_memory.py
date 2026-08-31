#!/usr/bin/env python3
"""Multi-writer queue and MCP resource contract tests."""

import concurrent.futures
import fcntl
import importlib.machinery
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from unittest import mock


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


siaqueue = _load("siaqueue_test", os.path.join(BIN, "siaqueue.py"))
siamcp = _load("siamcp_test", os.path.join(BIN, "sia-mcp"))
sialib = _load("sialib_mcp_test", os.path.join(BIN, "sialib.py"))


class AgentSpool(unittest.TestCase):
    def test_unexpected_directory_entries_have_a_hard_scan_ceiling(self):
        with tempfile.TemporaryDirectory() as state:
            queue_dir = os.path.join(state, siaqueue.QUEUE_DIRNAME)
            os.makedirs(queue_dir)
            # JACKAL status=exact: parsed=2+1, exact=3. Exact rational
            # arithmetic outside the Lean certificate chain
            # (NOT formal-bounded).
            for index in range(3):
                with open(os.path.join(queue_dir, f"noise-{index}"), "w") \
                        as stream:
                    stream.write("ignored")
            with mock.patch.object(siaqueue, "MAX_QUEUE_SCAN_ENTRIES", 3):
                pending, errors = siaqueue.pending(state)
            self.assertEqual(pending, [])
            self.assertTrue(errors)
            self.assertIn("scan bound", errors[0]["error"])

    def test_aggregate_queue_capacity_refuses_with_visible_health_error(self):
        with tempfile.TemporaryDirectory() as state:
            old_limit = siaqueue.MAX_PENDING_REQUESTS
            siaqueue.MAX_PENDING_REQUESTS = 1
            try:
                siaqueue.enqueue_note(state, "first", "one")
                with self.assertRaisesRegex(ValueError, "at capacity"):
                    siaqueue.enqueue_note(state, "second", "two")
                requests, errors = siaqueue.pending(state)
                self.assertEqual(len(requests), 1)
                self.assertTrue(any("capacity" in row["error"]
                                    for row in errors))
            finally:
                siaqueue.MAX_PENDING_REQUESTS = old_limit

    def test_concurrent_writers_get_distinct_durable_requests(self):
        with tempfile.TemporaryDirectory() as state:
            authors = tuple("abcdefgh")
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=len(authors)) as pool:
                receipts = list(pool.map(
                    lambda author: siaqueue.enqueue_note(
                        state, author, f"message from {author}"), authors))

            pending, errors = siaqueue.pending(state)
            self.assertEqual(errors, [])
            self.assertEqual(len(pending), len(authors))
            self.assertEqual(len({r["request_id"] for r in receipts}),
                             len(receipts))
            queue_dir = os.path.join(state, siaqueue.QUEUE_DIRNAME)
            self.assertEqual(stat.S_IMODE(os.stat(queue_dir).st_mode), 0o700)
            for path, record, identity in pending:
                self.assertEqual(record["schema"], siaqueue.SCHEMA)
                self.assertEqual(identity["request_id"], record["request_id"])
                self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_acknowledge_removes_only_processed_request(self):
        with tempfile.TemporaryDirectory() as state:
            siaqueue.enqueue_note(state, "one", "first")
            siaqueue.enqueue_note(state, "two", "second")
            pending, _ = siaqueue.pending(state)
            siaqueue.acknowledge(pending[0][0], pending[0][2])
            remaining, errors = siaqueue.pending(state)
            self.assertEqual(errors, [])
            self.assertEqual(
                {item[1]["request_id"] for item in remaining},
                {pending[1][1]["request_id"]})

    def test_malformed_request_is_reported_and_preserved(self):
        with tempfile.TemporaryDirectory() as state:
            queue_dir = os.path.join(state, siaqueue.QUEUE_DIRNAME)
            os.makedirs(queue_dir)
            path = os.path.join(queue_dir, "broken.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("not json")
            pending, errors = siaqueue.pending(state)
            self.assertEqual(pending, [])
            self.assertTrue(errors)
            self.assertTrue(os.path.exists(path),
                            "a refusal must not silently delete input")

    def test_request_parser_limits_are_named_and_preserve_the_claim(self):
        for parser_error in (ValueError, RecursionError):
            with self.subTest(parser_error=parser_error.__name__), \
                    tempfile.TemporaryDirectory() as state:
                queue_dir = os.path.join(state, siaqueue.QUEUE_DIRNAME)
                os.makedirs(queue_dir)
                path = os.path.join(queue_dir, "bounded.json")
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write("{}")
                os.chmod(path, 0o600)
                with mock.patch.object(
                        siaqueue.json, "loads",
                        side_effect=parser_error("private source content")):
                    pending, errors = siaqueue.pending(state)
                self.assertEqual(pending, [])
                self.assertEqual(errors[0]["error"],
                                 "request is malformed JSON")
                self.assertTrue(os.path.exists(path))

    def test_symlink_request_is_refused_without_reading_target(self):
        with tempfile.TemporaryDirectory() as state:
            queue_dir = os.path.join(state, siaqueue.QUEUE_DIRNAME)
            os.makedirs(queue_dir)
            target = os.path.join(state, "outside")
            with open(target, "w", encoding="utf-8") as stream:
                stream.write("private")
            link = os.path.join(queue_dir, "request.json")
            os.symlink(target, link)
            pending, errors = siaqueue.pending(state)
            self.assertEqual(pending, [])
            self.assertTrue(errors)
            self.assertTrue(os.path.islink(link))

    def test_symlink_queue_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as state:
            outside = os.path.join(state, "outside")
            os.makedirs(outside)
            os.symlink(outside, os.path.join(state, siaqueue.QUEUE_DIRNAME))
            with self.assertRaises(ValueError):
                siaqueue.enqueue_note(state, "agent", "do not redirect")
            pending, errors = siaqueue.pending(state)
            self.assertEqual(pending, [])
            self.assertTrue(errors)
            self.assertEqual(os.listdir(outside), [])

    def test_queue_api_rejects_oversized_note_before_writing(self):
        with tempfile.TemporaryDirectory() as state:
            with self.assertRaises(ValueError):
                siaqueue.enqueue_note(state, "agent", "x" * 2001)
            self.assertEqual(siaqueue.pending(state), ([], []))

    def test_acknowledge_refuses_and_preserves_path_replacement(self):
        with tempfile.TemporaryDirectory() as state:
            siaqueue.enqueue_note(state, "agent", "original")
            pending, _ = siaqueue.pending(state)
            path, _record, identity = pending[0]
            os.unlink(path)
            replacement = siaqueue.enqueue_note(state, "agent", "replacement")
            replacement_rows, _ = siaqueue.pending(state)
            replacement_path = next(
                item[0] for item in replacement_rows
                if item[1]["request_id"] == replacement["request_id"])
            os.replace(replacement_path, path)
            with self.assertRaisesRegex(ValueError, "identity changed"):
                siaqueue.acknowledge(path, identity)
            rows, errors = siaqueue.pending(state)
            self.assertEqual(rows, [])
            self.assertTrue(errors)
            self.assertTrue(os.path.exists(path),
                            "the replacement must be preserved, not deleted")
            with open(path) as stream:
                self.assertEqual(json.load(stream)["request_id"],
                                 replacement["request_id"])

    def test_directory_fsync_failure_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as state:
            with mock.patch.object(
                    siaqueue, "_fsync_dir", side_effect=OSError("no fsync")):
                with self.assertRaisesRegex(OSError, "no fsync"):
                    siaqueue.enqueue_note(state, "agent", "durability matters")

    def test_retry_repairs_queue_parent_link_durability(self):
        with tempfile.TemporaryDirectory() as state:
            real_fsync = siaqueue._fsync_dir
            failed = False

            def fail_first_parent(path):
                nonlocal failed
                if path == state and not failed:
                    failed = True
                    raise OSError("parent fsync interrupted")
                return real_fsync(path)

            with mock.patch.object(
                    siaqueue, "_fsync_dir", side_effect=fail_first_parent):
                with self.assertRaisesRegex(OSError, "interrupted"):
                    siaqueue.enqueue_note(state, "agent", "first attempt")
                receipt = siaqueue.enqueue_note(
                    state, "agent", "retry repairs parent")
            rows, errors = siaqueue.pending(state)
            self.assertEqual(errors, [])
            self.assertEqual(
                [row[1]["request_id"] for row in rows],
                [receipt["request_id"]])


class PgliteOwnership(unittest.TestCase):
    def test_owner_lease_excludes_another_runtime_process_handle(self):
        with tempfile.TemporaryDirectory() as state:
            old_state, old_lock = sialib.STATE, sialib.GBRAIN_OWNER_LOCK
            sialib.STATE = state
            sialib.GBRAIN_OWNER_LOCK = os.path.join(state, "owner.lock")
            try:
                with sialib.gbrain_owner():
                    with open(sialib.GBRAIN_OWNER_LOCK, "a") as contender:
                        with self.assertRaises(BlockingIOError):
                            fcntl.flock(contender, fcntl.LOCK_EX
                                       | fcntl.LOCK_NB)
                with open(sialib.GBRAIN_OWNER_LOCK, "a") as contender:
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(contender, fcntl.LOCK_UN)
            finally:
                sialib.STATE, sialib.GBRAIN_OWNER_LOCK = old_state, old_lock

    def test_corpus_transaction_and_brainstem_leases_exclude_contenders(self):
        with tempfile.TemporaryDirectory() as state:
            old = (sialib.STATE, sialib.CORPUS_OWNER_LOCK,
                   sialib.BRAINSTEM_OWNER_LOCK)
            sialib.STATE = state
            sialib.CORPUS_OWNER_LOCK = os.path.join(state, "corpus.lock")
            sialib.BRAINSTEM_OWNER_LOCK = os.path.join(state, "brainstem.lock")
            try:
                with sialib.corpus_owner():
                    with open(sialib.CORPUS_OWNER_LOCK, "a") as contender:
                        with self.assertRaises(BlockingIOError):
                            fcntl.flock(contender, fcntl.LOCK_EX
                                       | fcntl.LOCK_NB)
                with sialib.brainstem_owner():
                    with self.assertRaises(sialib.OwnerBusy):
                        with sialib.brainstem_owner():
                            pass
            finally:
                (sialib.STATE, sialib.CORPUS_OWNER_LOCK,
                 sialib.BRAINSTEM_OWNER_LOCK) = old

    def test_thought_inbox_rmw_is_locked_and_drained_as_one_batch(self):
        with tempfile.TemporaryDirectory() as state:
            old = (sialib.STATE, sialib.THOUGHT_INBOX_PATH,
                   sialib.THOUGHT_INBOX_LOCK)
            sialib.STATE = state
            sialib.THOUGHT_INBOX_PATH = os.path.join(state, "thoughts.json")
            sialib.THOUGHT_INBOX_LOCK = os.path.join(state, "thoughts.lock")
            items = [{"kind": "one", "text": "first"},
                     {"kind": "two", "text": "second"}]
            try:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    list(pool.map(sialib.append_thought_inbox, items))
                drained = sialib.drain_thought_inbox()
                self.assertEqual({item["kind"] for item in drained},
                                 {"one", "two"})
                self.assertEqual(sialib.drain_thought_inbox(), [])
            finally:
                (sialib.STATE, sialib.THOUGHT_INBOX_PATH,
                 sialib.THOUGHT_INBOX_LOCK) = old

    def test_thought_inbox_metadata_and_timestamp_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            state = os.path.join(root, "state")
            corpus = os.path.join(root, "corpus")
            os.makedirs(state)
            os.makedirs(corpus)
            old = (sialib.STATE, sialib.CORPUS,
                   sialib.THOUGHT_INBOX_PATH, sialib.THOUGHT_INBOX_LOCK)
            sialib.STATE, sialib.CORPUS = state, corpus
            sialib.THOUGHT_INBOX_PATH = os.path.join(state, "thoughts.json")
            sialib.THOUGHT_INBOX_LOCK = os.path.join(state, "thoughts.lock")
            try:
                with self.assertRaisesRegex(ValueError, "reserved"):
                    sialib.append_thought_inbox({
                        "kind": "note", "text": "held",
                        "_queued_at": "../../../outside"})
                corrupt = [{"kind": "note", "text": "held", "links": [],
                            "urgent": False, "_queue_id": "a" * 32,
                            "_queued_at": "../../../outside"}]
                with open(sialib.THOUGHT_INBOX_PATH, "w") as stream:
                    json.dump(corrupt, stream)
                with self.assertRaisesRegex(ValueError,
                                            "timestamp is invalid"):
                    sialib.drain_thought_inbox(defer_ack=True)
                self.assertTrue(os.path.lexists(
                    sialib._thought_inbox_claim_path()))
                with self.assertRaisesRegex(ValueError,
                                            "timestamp is invalid"):
                    sialib.write_thought({
                        "ts": "../../../outside", "kind": "note",
                        "text": "held", "links": []})
                self.assertEqual(os.listdir(corpus), [])
            finally:
                (sialib.STATE, sialib.CORPUS,
                 sialib.THOUGHT_INBOX_PATH,
                 sialib.THOUGHT_INBOX_LOCK) = old


class NoteMaterialization(unittest.TestCase):
    def test_agent_markup_cannot_mint_corpus_links_or_terminal_controls(self):
        with tempfile.TemporaryDirectory() as root:
            state = os.path.join(root, "state")
            corpus = os.path.join(root, "corpus")
            os.makedirs(state)
            os.makedirs(corpus)
            old_state, old_corpus = sialib.STATE, sialib.CORPUS
            sialib.STATE, sialib.CORPUS = state, corpus
            try:
                siaqueue.enqueue_note(
                    state, "agent",
                    "[[events/forged]]\n# forged heading\x1b]52;c;bad\x07")
                store = {"v": 1, "thoughts": []}
                processed, pages, _thoughts, errors = \
                    sialib.materialize_agent_notes(store)
                self.assertTrue(processed)
                self.assertEqual(errors, [])
                with open(sialib.corpus_path(pages[0])) as stream:
                    page = stream.read()
                self.assertNotIn("[[events/forged]]", page)
                self.assertNotIn("\x1b", page)
                self.assertNotIn("\x07", page)
                self.assertIn("&#91;&#91;events/forged&#93;&#93;", page)
                self.assertEqual(page.count("[[organs/agents]]"), 1)
                self.assertEqual(page.count("[[sia/cortex]]"), 1)
            finally:
                sialib.STATE, sialib.CORPUS = old_state, old_corpus

    def test_agent_author_cannot_inject_html_or_markdown(self):
        with tempfile.TemporaryDirectory() as root:
            state = os.path.join(root, "state")
            corpus = os.path.join(root, "corpus")
            os.makedirs(state)
            os.makedirs(corpus)
            old_state, old_corpus = sialib.STATE, sialib.CORPUS
            sialib.STATE, sialib.CORPUS = state, corpus
            try:
                siaqueue.enqueue_note(
                    state, "<img src=x> [click](bad)",
                    "safe body")
                store = {"v": 1, "thoughts": []}
                processed, pages, _thoughts, errors = \
                    sialib.materialize_agent_notes(store)
                self.assertTrue(processed)
                self.assertEqual(errors, [])
                with open(sialib.corpus_path(pages[0])) as stream:
                    rendered = stream.read()
                self.assertNotIn("<img", rendered)
                self.assertNotIn("[click](bad)", rendered)
            finally:
                sialib.STATE, sialib.CORPUS = old_state, old_corpus

    def test_preexisting_wrong_identity_is_preserved_and_request_retried(self):
        with tempfile.TemporaryDirectory() as root:
            state = os.path.join(root, "state")
            corpus = os.path.join(root, "corpus")
            os.makedirs(state)
            os.makedirs(corpus)
            old_state, old_corpus = sialib.STATE, sialib.CORPUS
            sialib.STATE, sialib.CORPUS = state, corpus
            try:
                siaqueue.enqueue_note(state, "codex", "keep this request")
                requests, _ = siaqueue.pending(state)
                path, request, _identity = requests[0]
                queued_date, queued_time = request["queued_at"][:-1].split("T")
                queued = queued_date + "-" + queued_time.replace(":", "")
                slug = (f"notes/{queued}-codex-"
                        f"{request['request_id']}")
                sialib.write_page(slug, ["type: note",
                                         "request_id: another"], "# collision\n")
                processed, _pages, _thoughts, errors = \
                    sialib.materialize_agent_notes({"v": 1, "thoughts": []})
                self.assertEqual(processed, [])
                self.assertTrue(errors)
                self.assertTrue(os.path.exists(path))
                with open(sialib.corpus_path(slug)) as stream:
                    self.assertIn("# collision", stream.read())
            finally:
                sialib.STATE, sialib.CORPUS = old_state, old_corpus

    def test_oversized_preexisting_page_is_refused_without_acknowledgment(self):
        with tempfile.TemporaryDirectory() as root:
            state = os.path.join(root, "state")
            corpus = os.path.join(root, "corpus")
            os.makedirs(state)
            os.makedirs(corpus)
            old_state, old_corpus = sialib.STATE, sialib.CORPUS
            sialib.STATE, sialib.CORPUS = state, corpus
            try:
                siaqueue.enqueue_note(state, "codex", "bounded retry")
                requests, _ = siaqueue.pending(state)
                request_path, request, _identity = requests[0]
                queued_date, queued_time = request["queued_at"][:-1].split("T")
                queued = queued_date + "-" + queued_time.replace(":", "")
                slug = (f"notes/{queued}-codex-"
                        f"{request['request_id']}")
                target = sialib.corpus_path(slug)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                oversized = b"x" * (sialib.MAX_THOUGHT_INBOX_BYTES + 1)
                with open(target, "wb") as stream:
                    stream.write(oversized)

                processed, _pages, _thoughts, errors = \
                    sialib.materialize_agent_notes(
                        {"v": 1, "thoughts": []})

                self.assertEqual(processed, [])
                self.assertRegex(errors[0]["error"], "bounded owner file")
                self.assertTrue(os.path.exists(request_path))
                self.assertEqual(os.stat(target).st_size, len(oversized))
            finally:
                sialib.STATE, sialib.CORPUS = old_state, old_corpus

    def test_daemon_materialization_is_idempotent_until_acknowledged(self):
        with tempfile.TemporaryDirectory() as root:
            state = os.path.join(root, "state")
            corpus = os.path.join(root, "corpus")
            os.makedirs(state)
            os.makedirs(corpus)
            old_state, old_corpus = sialib.STATE, sialib.CORPUS
            old_log = sialib.log
            sialib.STATE, sialib.CORPUS = state, corpus
            sialib.log = lambda _message: None
            store = {"v": 1, "thoughts": []}
            try:
                siaqueue.enqueue_note(state, "codex", "durable handoff")
                paths, pages, thoughts, errors = \
                    sialib.materialize_agent_notes(store)
                self.assertEqual(errors, [])
                self.assertEqual(len(paths), len(pages))
                self.assertEqual(len(thoughts), len(pages))
                self.assertTrue(sialib.page_exists(pages[0]))
                self.assertTrue(os.path.exists(paths[0][0]),
                                "commit/sync must precede acknowledgment")

                retry_paths, retry_pages, retry_thoughts, retry_errors = \
                    sialib.materialize_agent_notes(store)
                self.assertEqual(retry_errors, [])
                self.assertEqual(retry_paths, paths)
                self.assertEqual(retry_pages, pages)
                self.assertEqual(retry_thoughts, [],
                                 "retry must not duplicate the thought")
                siaqueue.acknowledge(paths[0][0], paths[0][1])
                self.assertEqual(siaqueue.pending(state), ([], []))
            finally:
                sialib.STATE, sialib.CORPUS = old_state, old_corpus
                sialib.log = old_log

    def test_acknowledgment_is_gated_and_reports_partial_success(self):
        paths = [("/queue/one.json", {"request_id": "one"}),
                 ("/queue/two.json", {"request_id": "two"})]
        old_ack = sialib.siaqueue.acknowledge
        calls = []

        def fake_ack(path, identity):
            calls.append(path)
            if path.endswith("two.json"):
                raise OSError("still busy")

        sialib.siaqueue.acknowledge = fake_ack
        try:
            self.assertEqual(
                sialib.acknowledge_agent_notes(paths, "error", True),
                (0, []))
            self.assertEqual(
                sialib.acknowledge_agent_notes(paths, "committed", False),
                (0, []))
            self.assertEqual(calls, [])

            acknowledged, errors = sialib.acknowledge_agent_notes(
                paths, "committed", True)
            self.assertEqual(acknowledged, 1)
            self.assertEqual(calls, [path for path, _identity in paths])
            self.assertEqual(errors[0]["file"], "two.json")
        finally:
            sialib.siaqueue.acknowledge = old_ack


class McpResources(unittest.TestCase):
    def setUp(self):
        self.old_run_sia = siamcp.run_sia
        self.calls = []

        def fake(argv, timeout=240):
            self.calls.append(argv)
            return "content for " + " ".join(argv), False

        siamcp.run_sia = fake

    def tearDown(self):
        siamcp.run_sia = self.old_run_sia

    def test_cli_output_is_bounded_before_mcp_framing(self):
        old_sia = siamcp.SIA
        siamcp.SIA = sys.executable
        try:
            output, returncode = self.old_run_sia([
                "-c", "import sys; sys.stdout.write('x' * %d)" %
                (siamcp.MAX_SIA_OUTPUT_BYTES + 1)
            ])
        finally:
            siamcp.SIA = old_sia
        self.assertNotEqual(returncode, 0)
        self.assertIn("output exceeded", output)

    def test_cli_invalid_utf8_output_is_refused(self):
        old_sia = siamcp.SIA
        siamcp.SIA = sys.executable
        try:
            output, returncode = self.old_run_sia([
                "-c", "import os; os.write(1, bytes([255]))"
            ])
        finally:
            siamcp.SIA = old_sia
        self.assertNotEqual(returncode, 0)
        self.assertIn("not valid UTF-8", output)

    def test_cli_timeout_kills_descendant_after_parent_exits(self):
        old_sia = siamcp.SIA
        with tempfile.TemporaryDirectory() as cwd:
            pid_file = os.path.join(cwd, "descendant.pid")
            parent = (
                "import pathlib,subprocess,sys; "
                "child=subprocess.Popen([sys.executable,'-c',"
                "'import time; time.sleep(60)']); "
                "pathlib.Path(sys.argv[1]).write_text(str(child.pid))")
            siamcp.SIA = sys.executable
            try:
                output, returncode = self.old_run_sia(
                    ["-c", parent, pid_file], timeout=1)
            finally:
                siamcp.SIA = old_sia
            self.assertNotEqual(returncode, 0)
            self.assertIn("timed out", output)
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
            self.assertFalse(alive, "MCP CLI descendant survived group kill")

    def test_oversized_frame_is_rejected_and_next_request_survives(self):
        oversized = "{" + (" " * siamcp.MAX_REQUEST_BYTES) + "}\n"
        valid = json.dumps({"jsonrpc": "2.0", "id": "after",
                            "method": "ping"}) + "\n"
        incoming = io.StringIO(oversized + valid)
        outgoing = io.StringIO()
        old_stdin, old_stdout = siamcp.sys.stdin, siamcp.sys.stdout
        try:
            siamcp.sys.stdin, siamcp.sys.stdout = incoming, outgoing
            siamcp.main()
        finally:
            siamcp.sys.stdin, siamcp.sys.stdout = old_stdin, old_stdout
        replies = [json.loads(line)
                   for line in outgoing.getvalue().splitlines()]
        self.assertEqual(replies[0]["error"]["code"], -32600)
        self.assertEqual(replies[1]["id"], "after")
        self.assertEqual(replies[1]["result"], {})

    def test_invalid_utf8_is_a_parse_error_and_does_not_desynchronize(self):
        class BinaryInput:
            def __init__(self, payload):
                self.buffer = io.BytesIO(payload)

        valid = json.dumps({"jsonrpc": "2.0", "id": "after-utf8",
                            "method": "ping"}).encode("utf-8") + b"\n"
        incoming = BinaryInput(b"\xff\n" + valid)
        outgoing = io.StringIO()
        old_stdin, old_stdout = siamcp.sys.stdin, siamcp.sys.stdout
        try:
            siamcp.sys.stdin, siamcp.sys.stdout = incoming, outgoing
            siamcp.main()
        finally:
            siamcp.sys.stdin, siamcp.sys.stdout = old_stdin, old_stdout
        replies = [json.loads(line)
                   for line in outgoing.getvalue().splitlines()]
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertEqual(replies[1]["id"], "after-utf8")

    def test_batch_and_serialized_response_have_global_bounds(self):
        oversized_batch = [
            {"jsonrpc": "2.0", "id": index, "method": "ping"}
            for index in range(siamcp.MAX_BATCH_ITEMS + 1)
        ]
        rejected = siamcp.handle_message(
            oversized_batch, protocol_version="2025-03-26")
        self.assertEqual(rejected["error"]["code"], -32600)

        outgoing = io.StringIO()
        old_stdout = siamcp.sys.stdout
        try:
            siamcp.sys.stdout = outgoing
            siamcp._write_message({
                "jsonrpc": "2.0", "id": "large",
                "result": {"text": "x" * siamcp.MAX_RESPONSE_BYTES},
            })
        finally:
            siamcp.sys.stdout = old_stdout
        response = json.loads(outgoing.getvalue())
        self.assertEqual(response["id"], "large")
        self.assertEqual(response["error"]["code"], -32603)

    def test_static_resource_uses_cli_not_database(self):
        result, error = siamcp.read_resource("sia://status")
        self.assertIsNone(error)
        self.assertEqual(self.calls, [["status"]])
        self.assertEqual(result["contents"][0]["mimeType"], "text/plain")

    def test_memory_template_reads_valid_slug(self):
        result, error = siamcp.read_resource(
            "sia://memory/events/jackal/2026-08-29")
        self.assertIsNone(error)
        self.assertEqual(self.calls,
                         [["recall", "events/jackal/2026-08-29",
                           "--no-touch"]])
        self.assertEqual(result["contents"][0]["mimeType"],
                         "text/markdown")

    def test_memory_template_rejects_traversal_and_arbitrary_schemes(self):
        bad = [
            "sia://memory/../../.ssh/id_ed25519",
            "sia://memory/%2e%2e/%2e%2e/etc/passwd",
            "file:///etc/passwd",
            "sia://memory/UPPERCASE",
        ]
        for uri in bad:
            with self.subTest(uri=uri):
                result, error = siamcp.read_resource(uri)
                self.assertIsNone(result)
                self.assertIsNotNone(error)
        self.assertEqual(self.calls, [])

    def test_missing_memory_and_infrastructure_failures_are_distinct(self):
        prior = siamcp.run_sia
        metadata = {
            "io.modelcontextprotocol/protocolVersion":
                siamcp.MODERN_PROTOCOL,
            "io.modelcontextprotocol/clientCapabilities": {},
        }
        try:
            siamcp.run_sia = lambda _argv, timeout=240: ("not found", 3)
            legacy = siamcp.handle_message({
                "jsonrpc": "2.0", "id": "legacy",
                "method": "resources/read",
                "params": {"uri": "sia://memory/organs/missing"}},
                protocol_version="2025-11-25")
            modern = siamcp.handle_message({
                "jsonrpc": "2.0", "id": "modern",
                "method": "resources/read",
                "params": {"uri": "sia://memory/organs/missing",
                           "_meta": metadata}},
                protocol_version=siamcp.MODERN_PROTOCOL)
            self.assertEqual(legacy["error"]["code"], -32002)
            self.assertEqual(modern["error"]["code"], -32602)

            siamcp.run_sia = lambda _argv, timeout=240: ("owner busy", 1)
            unavailable = siamcp.handle_message({
                "jsonrpc": "2.0", "id": "infra",
                "method": "resources/read",
                "params": {"uri": "sia://memory/organs/existing",
                           "_meta": metadata}},
                protocol_version=siamcp.MODERN_PROTOCOL)
            self.assertEqual(unavailable["error"]["code"], -32603)
        finally:
            siamcp.run_sia = prior

    def test_resource_inventory_has_unique_uris(self):
        uris = [resource["uri"] for resource in siamcp.RESOURCES]
        self.assertEqual(len(uris), len(set(uris)))
        self.assertTrue(siamcp.RESOURCE_TEMPLATES)

    def test_tool_contracts_are_bounded_annotated_and_structured(self):
        for tool in siamcp.TOOLS:
            self.assertIn("annotations", tool)
            self.assertIn("outputSchema", tool)
            self.assertFalse(tool["annotations"]["destructiveHint"])
            self.assertFalse(tool["annotations"]["openWorldHint"])
            self.assertFalse(
                tool["inputSchema"].get("additionalProperties", True))
        self.assertIsNone(siamcp._validate_tool_args(
            "sia_ask", {"question": "what changed?"}))
        search = next(tool for tool in siamcp.TOOLS
                      if tool["name"] == "sia_search")
        self.assertTrue(search["annotations"]["readOnlyHint"])
        self.assertTrue(search["annotations"]["idempotentHint"])
        text, is_error = siamcp.call_tool(
            "sia_search", {"question": "audit memory"})
        self.assertFalse(is_error)
        self.assertIn("content for", text)
        self.assertEqual(self.calls[-1],
                         ["ask", "--no-touch", "audit memory"])
        self.assertIsNone(siamcp._validate_tool_args(
            "sia_calibration", {"cursor": "17"}))
        text, is_error = siamcp.call_tool(
            "sia_calibration", {"cursor": "17"})
        self.assertFalse(is_error)
        self.assertIn("content for", text)
        self.assertEqual(self.calls[-1],
                         ["calibration", "--cursor", "17"])
        self.assertIsNotNone(siamcp._validate_tool_args(
            "sia_calibration", {"cursor": "not-a-cursor"}))
        cursor_rule = next(
            tool for tool in siamcp.TOOLS
            if tool["name"] == "sia_calibration"
        )["inputSchema"]["properties"]["cursor"]
        self.assertIsNotNone(siamcp._validate_tool_args(
            "sia_calibration",
            {"cursor": "1" * (cursor_rule["maxLength"] + 1)}))
        calls_before = list(self.calls)
        rejected = siamcp.handle_message({
            "jsonrpc": "2.0", "id": "long-cursor",
            "method": "tools/call", "params": {
                "name": "sia_calibration",
                "arguments": {
                    "cursor": "1" * (cursor_rule["maxLength"] + 1),
                },
            },
        }, protocol_version="2025-03-26")
        self.assertTrue(rejected["result"]["isError"])
        self.assertIn("cursor is too long",
                      rejected["result"]["structuredContent"]["text"])
        self.assertEqual(self.calls, calls_before)
        self.assertIsNotNone(siamcp._validate_tool_args(
            "sia_ask", {"question": "", "extra": True}))
        self.assertIsNotNone(siamcp._validate_tool_args(
            "sia_propose_take", {"claim": "x", "confidence": float("nan"),
                                 "deadline": "2026-02-30"}))

    def test_proposal_tool_requires_future_deadline_at_queue_time(self):
        text, is_error = siamcp.call_tool(
            "sia_propose_take", {
                "claim": "future claim", "confidence": 0.7,
                "deadline": "2026-12-31", "author": "agent"})
        self.assertFalse(is_error)
        self.assertIn("proposed", text)
        self.assertEqual(self.calls[-1][0], "agent-propose")
        proposal = json.loads(self.calls[-1][1])
        self.assertEqual(proposal, {
            "claim": "future claim", "confidence": 0.7,
            "deadline": "2026-12-31", "domain": "general",
            "proposed": "agent", "source": "sia/cortex"})

    def test_json_rpc_advertises_and_serves_resources(self):
        messages = [
            {"jsonrpc": "2.0", "id": "init", "method": "initialize",
             "params": {"protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "unit", "version": "1"}}},
            {"jsonrpc": "2.0", "id": "list",
             "method": "resources/list"},
            {"jsonrpc": "2.0", "id": "templates",
             "method": "resources/templates/list"},
            {"jsonrpc": "2.0", "id": "read",
             "method": "resources/read",
             "params": {"uri": "sia://status"}},
            {"jsonrpc": "2.0", "id": "reject",
             "method": "resources/read",
             "params": {"uri": "sia://memory/../../private"}},
        ]
        incoming = io.StringIO(
            "".join(json.dumps(message) + "\n" for message in messages))
        outgoing = io.StringIO()
        old_stdin, old_stdout = siamcp.sys.stdin, siamcp.sys.stdout
        try:
            siamcp.sys.stdin, siamcp.sys.stdout = incoming, outgoing
            siamcp.main()
        finally:
            siamcp.sys.stdin, siamcp.sys.stdout = old_stdin, old_stdout
        replies = {row["id"]: row for row in map(
            json.loads, outgoing.getvalue().splitlines())}
        self.assertIn("resources", replies["init"]["result"]["capabilities"])
        self.assertTrue(replies["list"]["result"]["resources"])
        self.assertTrue(
            replies["templates"]["result"]["resourceTemplates"])
        self.assertEqual(replies["read"]["result"]["contents"][0]["uri"],
                         "sia://status")
        self.assertEqual(replies["reject"]["error"]["code"], -32602)

    def test_legacy_revisions_negotiate_and_newer_legacy_rejects_batches(self):
        for revision in ("2025-06-18", "2025-11-25"):
            with self.subTest(revision=revision):
                response = siamcp.handle_message({
                    "jsonrpc": "2.0", "id": "init", "method": "initialize",
                    "params": {"protocolVersion": revision,
                               "capabilities": {},
                               "clientInfo": {"name": "test",
                                              "version": "1"}}})
                self.assertEqual(response["result"]["protocolVersion"],
                                 revision)
                rejected = siamcp.handle_message([
                    {"jsonrpc": "2.0", "id": "ping", "method": "ping"}],
                    protocol_version=revision)
                self.assertEqual(rejected["error"]["code"], -32600)

        malformed = siamcp.handle_message({
            "jsonrpc": "2.0", "id": "init", "method": "initialize",
            "params": {"protocolVersion": "2025-11-25"}})
        self.assertEqual(malformed["error"]["code"], -32602)
        fallback = siamcp.handle_message({
            "jsonrpc": "2.0", "id": "init", "method": "initialize",
            "params": {"protocolVersion": "2099-01-01",
                       "capabilities": {},
                       "clientInfo": {"name": "unit", "version": "1"}}})
        self.assertEqual(fallback["result"]["protocolVersion"],
                         siamcp.LEGACY_PROTOCOLS[0])

    def test_modern_discovery_and_stateless_results_follow_current_revision(self):
        metadata = {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": {
                "name": "unit", "version": "1"},
        }
        discover = siamcp.handle_message({
            "jsonrpc": "2.0", "id": "discover",
            "method": "server/discover", "params": {"_meta": metadata}})
        result = discover["result"]
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual(result["supportedVersions"], ["2026-07-28"])
        self.assertFalse(set(result["supportedVersions"])
                         & set(siamcp.LEGACY_PROTOCOLS))
        self.assertEqual(result["cacheScope"], "public")
        self.assertIn("io.modelcontextprotocol/serverInfo", result["_meta"])

        listed = siamcp.handle_message({
            "jsonrpc": "2.0", "id": "tools", "method": "tools/list",
            "params": {"_meta": metadata}})["result"]
        self.assertEqual(listed["resultType"], "complete")
        self.assertEqual(listed["cacheScope"], "public")
        self.assertTrue(listed["tools"])

        read = siamcp.handle_message({
            "jsonrpc": "2.0", "id": "read", "method": "resources/read",
            "params": {"_meta": metadata, "uri": "sia://status"}})["result"]
        self.assertEqual(read["cacheScope"], "private")

        old_ping = siamcp.handle_message({
            "jsonrpc": "2.0", "id": "ping", "method": "ping",
            "params": {"_meta": metadata}})
        self.assertEqual(old_ping["error"]["code"], -32601)
        batch = siamcp.handle_message([
            {"jsonrpc": "2.0", "id": "tools", "method": "tools/list",
             "params": {"_meta": metadata}}],
            protocol_version="2026-07-28")
        self.assertEqual(batch["error"]["code"], -32600)

        for implicit_batch in (
                [{"jsonrpc": "2.0", "id": "tools",
                  "method": "tools/list", "params": {"_meta": metadata}}],
                [{"jsonrpc": "2.0", "id": "discover",
                  "method": "server/discover", "params": {}}]):
            with self.subTest(batch=implicit_batch):
                rejected = siamcp.handle_message(implicit_batch)
                self.assertEqual(rejected["error"]["code"], -32600)
        mismatched_session = siamcp.handle_message([
            {"jsonrpc": "2.0", "id": "tools", "method": "tools/list",
             "params": {"_meta": metadata}}],
            protocol_version="2025-03-26")
        self.assertEqual(mismatched_session["error"]["code"], -32600)

    def test_modern_discovery_does_not_pin_stdio_before_legacy_initialize(self):
        metadata = {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": {
                "name": "unit", "version": "1"},
        }
        messages = [
            {"jsonrpc": "2.0", "id": "discover",
             "method": "server/discover", "params": {"_meta": metadata}},
            {"jsonrpc": "2.0", "id": "init", "method": "initialize",
             "params": {"protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "unit", "version": "1"}}},
            {"jsonrpc": "2.0", "id": "tools", "method": "tools/list"},
        ]
        incoming = io.StringIO(
            "".join(json.dumps(message) + "\n" for message in messages))
        outgoing = io.StringIO()
        old_stdin, old_stdout = siamcp.sys.stdin, siamcp.sys.stdout
        try:
            siamcp.sys.stdin, siamcp.sys.stdout = incoming, outgoing
            siamcp.main()
        finally:
            siamcp.sys.stdin, siamcp.sys.stdout = old_stdin, old_stdout
        replies = {row["id"]: row for row in map(
            json.loads, outgoing.getvalue().splitlines())}
        self.assertEqual(replies["discover"]["result"]["resultType"],
                         "complete")
        self.assertEqual(replies["init"]["result"]["protocolVersion"],
                         "2025-11-25")
        self.assertTrue(replies["tools"]["result"]["tools"])

    def test_modern_metadata_and_version_fail_closed(self):
        missing = siamcp.handle_message({
            "jsonrpc": "2.0", "id": "discover",
            "method": "server/discover", "params": {}})
        self.assertEqual(missing["error"]["code"], -32602)
        unsupported = siamcp.handle_message({
            "jsonrpc": "2.0", "id": "tools", "method": "tools/list",
            "params": {"_meta": {
                "io.modelcontextprotocol/protocolVersion": "2099-01-01",
                "io.modelcontextprotocol/clientCapabilities": {},
                "io.modelcontextprotocol/clientInfo": {
                    "name": "unit", "version": "1"}}}})
        self.assertEqual(unsupported["error"]["code"], -32022)
        self.assertEqual(unsupported["error"]["data"]["supported"],
                         [siamcp.MODERN_PROTOCOL])

        missing_client_info = siamcp.handle_message({
            "jsonrpc": "2.0", "id": "tools", "method": "tools/list",
            "params": {"_meta": {
                "io.modelcontextprotocol/protocolVersion":
                    siamcp.MODERN_PROTOCOL,
                "io.modelcontextprotocol/clientCapabilities": {}}}})
        self.assertTrue(missing_client_info["result"]["tools"])

        malformed_client_info = siamcp.handle_message({
            "jsonrpc": "2.0", "id": "tools", "method": "tools/list",
            "params": {"_meta": {
                "io.modelcontextprotocol/protocolVersion":
                    siamcp.MODERN_PROTOCOL,
                "io.modelcontextprotocol/clientCapabilities": {},
                "io.modelcontextprotocol/clientInfo": {"name": "unit"}}}})
        self.assertEqual(malformed_client_info["error"]["code"], -32602)

        null_client_info = siamcp.handle_message({
            "jsonrpc": "2.0", "id": "tools", "method": "tools/list",
            "params": {"_meta": {
                "io.modelcontextprotocol/protocolVersion":
                    siamcp.MODERN_PROTOCOL,
                "io.modelcontextprotocol/clientCapabilities": {},
                "io.modelcontextprotocol/clientInfo": None}}})
        self.assertEqual(null_client_info["error"]["code"], -32602)

        selected_without_metadata = siamcp.handle_message({
            "jsonrpc": "2.0", "id": "tools", "method": "tools/list",
            "params": {}}, protocol_version=siamcp.MODERN_PROTOCOL)
        self.assertEqual(
            selected_without_metadata["error"]["code"], -32602)

        modern_on_legacy_session = siamcp.handle_message({
            "jsonrpc": "2.0", "id": "tools", "method": "tools/list",
            "params": {"_meta": {
                "io.modelcontextprotocol/protocolVersion":
                    siamcp.MODERN_PROTOCOL,
                "io.modelcontextprotocol/clientCapabilities": {},
                "io.modelcontextprotocol/clientInfo": {
                    "name": "unit", "version": "1"}}}},
            protocol_version="2025-03-26")
        self.assertEqual(modern_on_legacy_session["error"]["code"], -32602)

    def test_client_info_validates_standard_implementation_fields(self):
        # The schema requires strings but imposes no minimum length.
        self.assertTrue(siamcp._valid_client_info({
            "name": "", "version": ""}))
        self.assertTrue(siamcp._valid_client_info({
            "name": "unit",
            "title": "Unit client",
            "version": "1",
            "description": "MCP test client",
            "websiteUrl": "https://example.test/client",
            "icons": [{
                "src": "data:image/png;base64,AA==",
                "mimeType": "image/png",
                "sizes": ["48x48", "any"],
                "theme": "dark",
            }],
        }))
        invalid_values = [
            {"name": "unit", "version": "1", "title": True},
            {"name": "unit", "version": "1",
             "websiteUrl": "not a URI"},
            {"name": "unit", "version": "1",
             "websiteUrl": "https://example.test/%zz"},
            {"name": "unit", "version": "1",
             "websiteUrl": "https://example.test/caf\u00e9"},
            {"name": "unit", "version": "1",
             "websiteUrl": "https://example.test/a\x00b"},
            {"name": "unit", "version": "1",
             "websiteUrl": "https://example.test:invalid/path"},
            {"name": "unit", "version": "1", "icons": {}},
            {"name": "unit", "version": "1",
             "icons": [{"src": "https:///missing-host.png"}]},
            {"name": "unit", "version": "1",
             "icons": [{"src": "data:image/png;base64,AA==",
                         "sizes": "48x48"}]},
            {"name": "unit", "version": "1", "icons": None},
            {"name": "unit", "version": "1",
             "icons": [{"src": "data:image/png;base64,AA==",
                         "sizes": None}]},
            {"name": "unit", "version": "1",
             "icons": [{"src": "data:image/png;base64,AA==",
                         "theme": "sepia"}]},
            {"name": "unit", "version": "1",
             "icons": [{"src": "data:image/png;base64,AA==",
                         "theme": None}]},
            {"name": "unit", "version": "1",
             "icons": [{"src": "data:image/png;base64,AA==",
                         "theme": {}}]},
        ]
        for value in invalid_values:
            with self.subTest(value=value):
                self.assertFalse(siamcp._valid_client_info(value))

    def test_main_enforces_legacy_lifecycle_and_modern_request_metadata(self):
        metadata = {
            "io.modelcontextprotocol/protocolVersion":
                siamcp.MODERN_PROTOCOL,
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": {
                "name": "unit", "version": "1"},
        }
        legacy_messages = [
            {"jsonrpc": "2.0", "id": "before", "method": "tools/list"},
            {"jsonrpc": "2.0", "method": "tools/call",
             "params": {"name": "sia_ask",
                        "arguments": {"question": "must not execute"}}},
            {"jsonrpc": "2.0", "id": "init", "method": "initialize",
             "params": {"protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "unit", "version": "1"}}},
            {"jsonrpc": "2.0", "id": "after", "method": "tools/list"},
        ]
        modern_messages = [
            {"jsonrpc": "2.0", "id": "discover",
             "method": "server/discover", "params": {"_meta": metadata}},
            {"jsonrpc": "2.0", "method": "tools/call",
             "params": {"name": "sia_ask",
                        "arguments": {"question": "must not execute"}}},
            {"jsonrpc": "2.0", "id": "missing-meta",
             "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": "with-meta",
             "method": "tools/list", "params": {"_meta": metadata}},
        ]

        preinit_batch = siamcp.handle_message([
            {"jsonrpc": "2.0", "id": "batch-before",
             "method": "tools/list"},
            {"jsonrpc": "2.0", "method": "tools/call",
             "params": {"name": "sia_ask",
                        "arguments": {"question": "must not execute"}}},
        ], require_initialization=True)
        self.assertEqual(
            tuple(row["id"] for row in preinit_batch), ("batch-before",))
        self.assertEqual(preinit_batch[0]["error"]["code"], -32600)

        for messages, expected in (
                (legacy_messages, ("before", "init", "after")),
                (modern_messages,
                 ("discover", "missing-meta", "with-meta"))):
            with self.subTest(messages=messages):
                incoming = io.StringIO("".join(
                    json.dumps(message) + "\n" for message in messages))
                outgoing = io.StringIO()
                old_stdin, old_stdout = siamcp.sys.stdin, siamcp.sys.stdout
                try:
                    siamcp.sys.stdin, siamcp.sys.stdout = incoming, outgoing
                    siamcp.main()
                finally:
                    siamcp.sys.stdin, siamcp.sys.stdout = \
                        old_stdin, old_stdout
                replies = [json.loads(line) for line in
                           outgoing.getvalue().splitlines()]
                self.assertEqual(tuple(row["id"] for row in replies),
                                 expected)

                by_id = {row["id"]: row for row in replies}
                if messages is legacy_messages:
                    self.assertEqual(by_id["before"]["error"]["code"],
                                     -32600)
                    self.assertTrue(by_id["after"]["result"]["tools"])
                else:
                    self.assertEqual(
                        by_id["missing-meta"]["error"]["code"], -32600)
                    self.assertTrue(by_id["with-meta"]["result"]["tools"])
        self.assertEqual(self.calls, [],
                         "rejected notifications must not execute tools")

    def test_json_rpc_reports_parse_and_argument_errors(self):
        messages = [
            "{not-json}\n",
            json.dumps({"jsonrpc": "2.0", "id": "init",
                        "method": "initialize", "params": {
                            "protocolVersion": "2025-03-26",
                            "capabilities": {},
                            "clientInfo": {"name": "unit",
                                           "version": "1"}}}) + "\n",
            json.dumps({"jsonrpc": "2.0", "id": "bad", "method": "tools/call",
                        "params": {"name": "sia_ask", "arguments": {}}}) + "\n",
            json.dumps({"jsonrpc": "2.0", "id": "params",
                        "method": "tools/call", "params": []}) + "\n",
            json.dumps({"jsonrpc": "2.0", "method": "ping"}) + "\n",
            json.dumps({"jsonrpc": "2.0", "id": "after",
                        "method": "ping"}) + "\n",
        ]
        incoming = io.StringIO("".join(messages))
        outgoing = io.StringIO()
        old_stdin, old_stdout = siamcp.sys.stdin, siamcp.sys.stdout
        try:
            siamcp.sys.stdin, siamcp.sys.stdout = incoming, outgoing
            siamcp.main()
        finally:
            siamcp.sys.stdin, siamcp.sys.stdout = old_stdin, old_stdout
        rows = [json.loads(line) for line in outgoing.getvalue().splitlines()]
        self.assertEqual(rows[0]["error"]["code"], -32700)
        replies = {row.get("id"): row for row in rows}
        self.assertTrue(replies["bad"]["result"]["isError"])
        self.assertNotIn("error", replies["bad"])
        self.assertEqual(replies["params"]["error"]["code"], -32602)
        self.assertEqual(replies["after"]["result"], {})
        self.assertEqual(
            tuple(row.get("id") for row in rows),
            (None, "init", "bad", "params", "after"),
            "a valid JSON-RPC notification gets no reply")

    def test_hostile_json_scalars_and_parser_limits_do_not_kill_stdio(self):
        initialize = json.dumps({
            "jsonrpc": "2.0", "id": "init", "method": "initialize",
            "params": {"protocolVersion": "2025-03-26",
                       "capabilities": {},
                       "clientInfo": {"name": "unit", "version": "1"}},
        })
        escaped_surrogate = (
            r'{"jsonrpc":"2.0","id":"surrogate",'
            r'"method":"missing-\ud800"}')
        nesting = sys.getrecursionlimit() * 2
        deeply_nested = "[" * nesting + "]" * nesting
        digit_limit = sys.get_int_max_str_digits()
        oversized_integer = ("1" * (digit_limit + 1)
                             if digit_limit else deeply_nested)
        after = json.dumps({"jsonrpc": "2.0", "id": "after",
                            "method": "ping"})
        incoming = io.StringIO("\n".join((
            initialize, escaped_surrogate, deeply_nested,
            oversized_integer, after)) + "\n")
        outgoing = io.StringIO()
        old_stdin, old_stdout = siamcp.sys.stdin, siamcp.sys.stdout
        try:
            siamcp.sys.stdin, siamcp.sys.stdout = incoming, outgoing
            siamcp.main()
        finally:
            siamcp.sys.stdin, siamcp.sys.stdout = old_stdin, old_stdout

        replies = [json.loads(line)
                   for line in outgoing.getvalue().splitlines()]
        by_id = {row.get("id"): row for row in replies
                 if isinstance(row, dict) and row.get("id") is not None}
        self.assertEqual(by_id["surrogate"]["error"]["code"], -32601)
        self.assertIn(r"\ud800", outgoing.getvalue())
        parse_errors = [row for row in replies
                        if isinstance(row, dict)
                        and row.get("error", {}).get("code") == -32700]
        nested_replies = [row for row in replies if isinstance(row, list)]
        # CPython revisions differ on whether the C JSON decoder itself
        # refuses this depth.  Either boundary must reject it and continue.
        self.assertEqual(len(parse_errors) + len(nested_replies), 2)
        self.assertIn(len(parse_errors), (1, 2))
        if nested_replies:
            self.assertEqual(nested_replies[0][0]["error"]["code"], -32600)
        self.assertEqual(by_id["after"]["result"], {})

    def test_parser_recursion_failure_becomes_parse_error_and_continues(self):
        initialize = json.dumps({
            "jsonrpc": "2.0", "id": "init", "method": "initialize",
            "params": {"protocolVersion": "2025-03-26",
                       "capabilities": {},
                       "clientInfo": {"name": "unit", "version": "1"}},
        })
        incoming = io.StringIO("{}\n" + initialize + "\n")
        outgoing = io.StringIO()
        old_stdin, old_stdout = siamcp.sys.stdin, siamcp.sys.stdout
        real_loads = json.loads
        calls = iter((RecursionError("nesting ceiling"), None))

        def bounded_parser(value):
            failure = next(calls)
            if failure is not None:
                raise failure
            return real_loads(value)

        try:
            siamcp.sys.stdin, siamcp.sys.stdout = incoming, outgoing
            with mock.patch.object(siamcp.json, "loads",
                                   side_effect=bounded_parser):
                siamcp.main()
        finally:
            siamcp.sys.stdin, siamcp.sys.stdout = old_stdin, old_stdout
        replies = [json.loads(line)
                   for line in outgoing.getvalue().splitlines()]
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertEqual(replies[1]["id"], "init")

    def test_json_rpc_batch_aggregates_and_suppresses_notifications(self):
        batch = [
            {"jsonrpc": "2.0", "id": 7, "method": "ping"},
            {"jsonrpc": "2.0", "method": "ping"},
            19,
            {"jsonrpc": "2.0", "id": "tools", "method": "tools/list"},
        ]
        notifications = [
            {"jsonrpc": "2.0", "method": "ping"},
            {"jsonrpc": "2.0", "method": "missing/method"},
            {"jsonrpc": "2.0", "method": "tools/call",
             "params": {"name": "sia_ask",
                        "arguments": {"question": "must not execute"}}},
        ]
        incoming = io.StringIO(
            json.dumps({"jsonrpc": "2.0", "id": "init",
                        "method": "initialize", "params": {
                            "protocolVersion": "2025-03-26",
                            "capabilities": {},
                            "clientInfo": {"name": "unit",
                                           "version": "1"}}}) + "\n"
            + json.dumps(batch) + "\n"
            + json.dumps(notifications) + "\n")
        outgoing = io.StringIO()
        old_stdin, old_stdout = siamcp.sys.stdin, siamcp.sys.stdout
        try:
            siamcp.sys.stdin, siamcp.sys.stdout = incoming, outgoing
            siamcp.main()
        finally:
            siamcp.sys.stdin, siamcp.sys.stdout = old_stdin, old_stdout

        init_reply, replies = [json.loads(line) for line in
                               outgoing.getvalue().splitlines()]
        self.assertEqual(init_reply["id"], "init")
        self.assertIsInstance(replies, list)
        self.assertEqual([row.get("id") for row in replies],
                         [7, None, "tools"])
        self.assertEqual(replies[1]["error"]["code"], -32600)
        self.assertEqual(replies[0]["result"], {})
        self.assertTrue(replies[2]["result"]["tools"])
        self.assertEqual(self.calls, [],
                         "request-only notifications must not execute")

    def test_initialize_batch_and_pre_batch_revision_are_rejected(self):
        batched_initialize = siamcp.handle_message([{
            "jsonrpc": "2.0", "id": "init", "method": "initialize",
            "params": {"protocolVersion": "2025-03-26",
                       "capabilities": {},
                       "clientInfo": {"name": "unit", "version": "1"}}}])
        self.assertEqual(batched_initialize["error"]["code"], -32600)
        self.assertNotIn("id", batched_initialize)

        old_batch = siamcp.handle_message(
            [{"jsonrpc": "2.0", "id": "ping", "method": "ping"}],
            protocol_version="2024-11-05")
        self.assertEqual(old_batch["error"]["code"], -32600)
        self.assertNotIn("id", old_batch)

    def test_empty_batch_and_invalid_request_ids_are_invalid_requests(self):
        invalid_ids = [None, True, False, 1.5, {}, []]
        messages = [[]] + [
            {"jsonrpc": "2.0", "id": value, "method": "ping"}
            for value in invalid_ids
        ]
        incoming = io.StringIO(
            "".join(json.dumps(message) + "\n" for message in messages))
        outgoing = io.StringIO()
        old_stdin, old_stdout = siamcp.sys.stdin, siamcp.sys.stdout
        try:
            siamcp.sys.stdin, siamcp.sys.stdout = incoming, outgoing
            siamcp.main()
        finally:
            siamcp.sys.stdin, siamcp.sys.stdout = old_stdin, old_stdout

        replies = [json.loads(line)
                   for line in outgoing.getvalue().splitlines()]
        self.assertEqual(len(replies), len(messages))
        for reply in replies:
            self.assertNotIn("id", reply)
            self.assertEqual(reply["error"]["code"], -32600)

        for request_id in (0, -4, "", "request-id"):
            with self.subTest(request_id=request_id):
                response = siamcp.handle_message({
                    "jsonrpc": "2.0", "id": request_id, "method": "ping"})
                self.assertEqual(response["id"], request_id)
                self.assertEqual(response["result"], {})

    def test_tool_protocol_errors_are_distinct_from_execution_failures(self):
        messages = [
            {"jsonrpc": "2.0", "id": "unknown", "method": "tools/call",
             "params": {"name": "sia_does_not_exist", "arguments": {}}},
            {"jsonrpc": "2.0", "id": "invalid", "method": "tools/call",
             "params": {"name": "sia_ask", "arguments": {}}},
            {"jsonrpc": "2.0", "id": "execution", "method": "tools/call",
             "params": {"name": "sia_ask",
                        "arguments": {"question": "owner available?"}}},
        ]
        prior_run_sia = siamcp.run_sia
        siamcp.run_sia = lambda _argv, timeout=240: ("owner unavailable", True)
        try:
            replies = siamcp.handle_message(messages)
        finally:
            siamcp.run_sia = prior_run_sia
        by_id = {reply["id"]: reply for reply in replies}

        self.assertEqual(by_id["unknown"]["error"]["code"], -32602)
        self.assertNotIn("result", by_id["unknown"])
        self.assertTrue(by_id["invalid"]["result"]["isError"])
        self.assertNotIn("error", by_id["invalid"])
        self.assertNotIn("error", by_id["execution"])
        self.assertTrue(by_id["execution"]["result"]["isError"])
        self.assertIn("structuredContent", by_id["execution"]["result"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
