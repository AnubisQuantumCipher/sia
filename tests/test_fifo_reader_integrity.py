"""Bounded file readers must reach their refusal when a leaf is a FIFO."""

import datetime
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import signal
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
READER_CASES = (
    "config", "display-json", "state-json", "source-tail", "source-json",
    "source-window", "judge-config", "proposal-queue",
    "agent-note", "agent-request", "cli-pin",
    "thought-inbox", "ledger-pending", "memo", "bench-trend",
    "graph-lines", "graph-page", "mind-load", "mind-save", "touch-queue",
    "benchmark-file", "thought-page", "thought-recovery-record",
    "thought-recovery-claim", "thought-legacy-index", "history-file", "event-index",
    "consolidation-source", "consolidation-cleanup",
)


class ReaderDeadline(BaseException):
    pass


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(BIN, filename),
        loader=importlib.machinery.SourceFileLoader(
            name, os.path.join(BIN, filename)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _install_leaf(path, payload, mode):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    if mode == "fifo":
        os.mkfifo(path, 0o600)
    elif mode == "directory":
        os.mkdir(path, 0o700)
    else:
        with open(path, "wb") as stream:
            stream.write(payload)
        os.chmod(path, 0o600)


def _bounded_call(mode, operation, accepted, refused=None):
    def deadline(_signum, _frame):
        raise ReaderDeadline("reader did not refuse within its deadline")

    old_handler = signal.signal(signal.SIGALRM, deadline)
    signal.alarm(2)
    descriptors_before = set(os.listdir("/proc/self/fd"))
    try:
        try:
            result = operation()
        except (OSError, RuntimeError, ValueError):
            if mode == "regular":
                raise
            return
        if mode != "regular":
            if refused is None:
                raise AssertionError("special leaf was accepted as a regular file")
            refused(result)
        else:
            accepted(result)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
        if set(os.listdir("/proc/self/fd")) != descriptors_before:
            raise AssertionError("reader leaked a descriptor")


def _equal(actual, expected):
    if actual != expected:
        raise AssertionError(f"unexpected reader result: {actual!r}")


def _core_for_case(root):
    core = _load("sialib_fifo_reader", "sialib.py")
    core.SHARE = os.path.join(root, "share")
    core.CORPUS = os.path.join(core.SHARE, "corpus")
    core.STATE = os.path.join(root, "state")
    core.CONFIG_PATH = os.path.join(root, "config.json")
    core.MEMO_PATH = os.path.join(core.STATE, "memo.json")
    core.log = lambda *_arguments: None
    core.siamind.CORPUS = core.CORPUS
    core.siamind.MIND_PATH = os.path.join(core.STATE, "mind.json")
    core.siamind.TOUCH_QUEUE = os.path.join(core.STATE, "touches.jsonl")
    core.siatakes.HOME = root
    for directory in (core.SHARE, core.CORPUS, core.STATE):
        os.makedirs(directory, mode=0o700, exist_ok=True)
    return core


def _thought_record(core):
    return core._canonical_thought_page_record({
        "ts": "2026-01-05T12:00:00Z", "kind": "note",
        "text": "Fixture thought", "links": ["sia/cortex"],
        "urgent": False, "origin": "model",
        "slug": "thoughts/fixture",
    })


def _prepare_event_index(core, mode):
    event_id = "b" * 64
    source_id = "a" * 64
    source = "events/fixture/2026-01-05.md"
    epoch = core._epoch_slug_for_day("fixture", "2026-01-05")
    entry = {
        "schema": core.EVENT_INDEX_SCHEMA, "organ": "fixture",
        "event_id": event_id, "semantic_id": "c" * 64,
        "payload_sha256": hashlib.sha256(b"observation").hexdigest(),
        "source_rel": source, "source_sha256": source_id,
        "epoch_slug": epoch,
    }
    core.write_page(
        epoch,
        ["type: epoch", core.fm_title("Fixture epoch"),
         "date: 2026-01-05", "tags: [fixture]",
         "sia_sources: " + json.dumps([source_id]),
         "sia_source_manifest: " + json.dumps(
             [{"rel": source, "sha256": source_id}]),
         "sia_event_ids: " + json.dumps([event_id]),
         'sia_dates: ["2026-01-05"]', 'sia_counts: {"obs": 1}'],
        "# Fixture epoch\n\nConsolidated from 1 day-memories "
        "(2026-01-05 … 2026-01-05).\n")
    path = os.path.join(
        core.CORPUS, core._event_index_relative("fixture", event_id))
    _install_leaf(path, core._event_index_encoded(entry), mode)
    return lambda: core._read_event_index_entry("fixture", event_id), entry


def _consolidation_case(core, case, mode):
    def git(*arguments):
        return subprocess.run(
            ["git", "-C", core.CORPUS, *arguments], check=True,
            capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    core.siamind.EPISODIC_DAYS = 1
    stamp = datetime.datetime(
        2026, 1, 5, 12, tzinfo=datetime.timezone.utc)
    event = core.Event(
        "fixture", stamp, "obs", "Fixture observation",
        occurrence="fixture:fifo-consolidation")
    core.update_day_page("fixture", "2026-01-05", [event])
    git("add", "-A")
    git("commit", "-qm", "Fixture source")
    source = core.corpus_path(core.day_slug("fixture", "2026-01-05"))
    retained = source + ".retained"
    changed = []

    def substitute_source():
        if mode != "regular" and not changed:
            os.replace(source, retained)
            _install_leaf(source, b"", mode)
            changed.append(source)

    real_run = core._run_bounded_text_process
    real_publish = core._publish_event_index_entries

    def after_tracked_status(*arguments, **options):
        result = real_run(*arguments, **options)
        if options.get("label") == "git source status" \
                and result.returncode == 0 and not result.stdout.strip():
            substitute_source()
        return result

    def after_index_publication(entries):
        result = real_publish(entries)
        substitute_source()
        return result

    helper, wrapper = (
        ("_run_bounded_text_process", after_tracked_status)
        if case == "consolidation-source" else
        ("_publish_event_index_entries", after_index_publication))
    with mock.patch.object(core, helper, side_effect=wrapper):
        _bounded_call(
            mode, core.consolidate_corpus,
            lambda result: _equal(result, (1, 1, 0)))
    if mode != "regular":
        _equal(changed, [source])
        if not os.path.isfile(retained):
            raise AssertionError("exact fixture source was not retained")
    elif os.path.lexists(source):
        raise AssertionError("regular fixture source was not consolidated")


def _reader_case(case, root, mode):
    core = _core_for_case(root)
    path = os.path.join(root, "reader-input")
    payload = b"fixture\n"
    accepted = lambda result: _equal(result, "fixture\n")
    refused = None

    if case.startswith("consolidation-"):
        _consolidation_case(core, case, mode)
        return
    if case == "config":
        path, payload = core.CONFIG_PATH, b"{}\n"
        operation = core.load_config
        accepted = lambda result: _equal(
            (result, core.CONFIG_ERRORS), ({}, []))
        refused = lambda result: _equal(
            (result, core._LAST_CONFIG_LOAD_VALID), ({}, False))
    elif case == "display-json":
        payload = b"{}\n"
        fallback = {"refused": True}
        operation = lambda: core.read_json(path, fallback)
        accepted = lambda result: _equal(result, {})
        refused = lambda result: _equal(result, fallback)
    elif case == "state-json":
        payload = b"{}\n"
        operation = lambda: core.read_state_json(path, {}, "fixture")
        accepted = lambda result: _equal(result, {})
    elif case == "source-tail":
        operation = lambda: core.tail_lines(path, {"fixture": 0}, "fixture")
        accepted = lambda result: _equal(result, ["fixture"])
    elif case == "source-json":
        payload = b"{}\n"
        operation = lambda: core._read_bounded_source_json(path, "fixture")
        accepted = lambda result: _equal(result, {})
    elif case == "source-window":
        operation = lambda: core._stable_bounded_source_tail(path)
        accepted = lambda result: _equal(result, (payload, False))
    elif case == "judge-config":
        path = os.path.join(root, ".config", "sia", "config.json")
        payload = b"{}\n"
        operation = core.siatakes._judge_config
        accepted = refused = lambda result: _equal(result, ("none", ""))
    elif case == "proposal-queue":
        payload = b"[]\n"
        operation = lambda: core.siatakes._load_proposal_queue(path)
        accepted = lambda result: _equal(result, [])
    elif case == "agent-note":
        slug = "notes/fixture"
        path = core.corpus_path(slug)
        operation = lambda: core._read_existing_agent_note(slug)
    elif case == "agent-request":
        record = {
            "schema": core.siaqueue.SCHEMA, "request_id": "a" * 32,
            "queued_at": "2026-01-05T12:00:00Z", "operation": "note",
            "payload": {"author": "fixture", "text": "fixture"},
        }
        name = "20260105T120000Z-" + record["request_id"] + ".json"
        path = os.path.join(root, name)
        payload = (json.dumps(record) + "\n").encode("utf-8")
        operation = lambda: core.siaqueue._read_open_request(path, name)
        accepted = lambda result: _equal(result[0], record)
    elif case == "cli-pin":
        cli = _load("sia_cli_fifo_reader", "sia")
        cli.sialib = core
        payload = b"version=fixture-version\n"

        def read_pin():
            output = io.StringIO()
            with mock.patch.object(
                    core, "_run_bounded_text_process",
                    return_value=subprocess.CompletedProcess(
                        [], 0, stdout="fixture-version\n", stderr="")), \
                    contextlib.redirect_stdout(output):
                cli._gbrain_pin_check(pin_paths=[path])
            return output.getvalue()

        operation = read_pin
        accepted = lambda result: _equal("fixture-version" in result, True)
        refused = lambda result: _equal(result, "")
    elif case == "thought-inbox":
        payload = b"[]\n"
        operation = lambda: core._read_thought_inbox(path)
        accepted = lambda result: _equal(result, [])
    elif case == "ledger-pending":
        basis = core._pending_basis(0, "FIXTURE:record", "", "", "fixture")
        record_id = core._pending_identity(basis)
        record = {"schema": core.LEDGER_PENDING_SCHEMA,
                  "queued_at": core.iso(), "record_id": record_id, **basis}
        path = os.path.join(root, record_id + ".json")
        payload = (json.dumps(record) + "\n").encode("utf-8")
        operation = lambda: core._read_pending_record(path)
        accepted = lambda result: _equal(result[0], record)
    elif case == "memo":
        path, payload = core.MEMO_PATH, b"{}\n"
        operation = core.load_memo
        accepted = lambda result: _equal(result, {})
    elif case == "bench-trend":
        operation = lambda: core._read_bench_trend_tail(path)
        accepted = lambda result: _equal(result, (("fixture",), False))
    elif case == "graph-lines":
        operation = lambda: core._read_owned_stable_lines(
            path, max_bytes=core.MAX_CONFIG_BYTES,
            max_lines=core.MAX_CONFIG_TAGS,
            max_line_bytes=core.MAX_CONFIG_BYTES, label="fixture")
        accepted = lambda result: _equal(result, ("fixture",))
    elif case == "graph-page":
        slug = "events/fixture/page"
        path = core.corpus_path(slug)
        payload = (b'---\ntype: event-day\ntitle: "Fixture"\n'
                   b'date: 2026-01-05\n---\n# Fixture\n')
        operation = lambda: core._read_graph_corpus_page(slug)
        accepted = lambda result: _equal(result[0]["slug"], slug)
    elif case in {"mind-load", "mind-save"}:
        path, payload = core.siamind.MIND_PATH, b"{}\n"
        if case == "mind-load":
            operation = core.siamind.load_mind
            accepted = lambda result: _equal(
                result["v"], core.siamind.MIND_VERSION)
        else:
            operation = lambda: core.siamind.save_mind(
                core.siamind._empty_mind())
            accepted = lambda result: _equal(result, None)
    elif case == "touch-queue":
        operation = lambda: core.siamind._read_touch_queue_bytes_locked(path)
        accepted = lambda result: _equal(result[0], payload)
    elif case == "benchmark-file":
        benchmark = _load("siabench_fifo_reader", "siabench.py")
        operation = lambda: benchmark._read_nofollow_regular(path)
        accepted = lambda result: _equal(result[0], payload)
    elif case == "thought-page":
        slug = "thoughts/fixture"
        path = core.corpus_path(slug)
        operation = lambda: core._read_thought_page_text(slug)
    elif case == "thought-recovery-record":
        record = core._thought_recovery_record(_thought_record(core))
        path = os.path.join(root, record["record_id"] + ".json")
        payload = core._thought_recovery_record_bytes(record)
        operation = lambda: core._read_thought_recovery_record(path)
        accepted = lambda result: _equal(result[0], record)
    elif case == "thought-recovery-claim":
        claim = core._thought_recovery_claim_document([], [], None)
        path = core._thought_recovery_claim_path()
        payload = core._thought_recovery_claim_bytes(claim)
        operation = core._read_thought_recovery_claim
        accepted = lambda result: _equal(result, claim)
    elif case == "history-file":
        operation = lambda: core.siatakes._read_bounded_regular_text(
            path, core.siatakes.MAX_TAKE_PAGE_BYTES, "fixture")
    elif case == "thought-legacy-index":
        record = core._thought_legacy_index_entry(
            "fixture.md", _thought_record(core), "fixture\n")
        path = os.path.join(root, record["index_name"])
        payload = core._thought_legacy_index_bytes(record)
        operation = lambda: core._read_thought_legacy_index_entry(path)
        accepted = lambda result: _equal(result, record)
    elif case == "event-index":
        operation, expected = _prepare_event_index(core, mode)
        _bounded_call(mode, operation, lambda result: _equal(result, expected))
        return
    else:
        raise AssertionError("unknown bounded-reader fixture")

    _install_leaf(path, payload, mode)
    _bounded_call(mode, operation, accepted, refused)


class FifoReaderIntegrity(unittest.TestCase):
    def _run_case(self, case, mode):
        with tempfile.TemporaryDirectory(prefix="sia-fifo-reader-test-") \
                as root:
            environment = dict(os.environ)
            environment["HOME"] = root
            environment["PYTHONWARNINGS"] = "error::ResourceWarning"
            result = subprocess.run(
                [sys.executable, os.path.abspath(__file__),
                 "--reader-case", case, root, mode],
                cwd=REPO, env=environment, capture_output=True,
                text=True, timeout=20)
            self.assertEqual(
                result.returncode, 0,
                f"{case}/{mode}: {result.stdout}\n{result.stderr}")
            self.assertEqual(result.stdout, mode + ":complete\n")
            self.assertEqual(result.stderr, "")

    def test_regular_file_controls_remain_readable(self):
        for case in READER_CASES:
            with self.subTest(reader=case):
                self._run_case(case, "regular")

    def test_fifo_leaves_refuse_without_waiting_for_a_writer(self):
        for case in READER_CASES:
            with self.subTest(reader=case):
                self._run_case(case, "fifo")

    def test_directory_leaves_refuse_without_leaking_descriptors(self):
        for case in READER_CASES:
            with self.subTest(reader=case):
                self._run_case(case, "directory")


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--reader-case":
        _reader_case(sys.argv[2], sys.argv[3], sys.argv[4])
        print(sys.argv[4] + ":complete")
    else:
        unittest.main()
