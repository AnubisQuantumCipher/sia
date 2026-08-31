#!/usr/bin/env python3
"""SIA test suite — the invariants the whitepaper claims were verified in
review, now shipped as executable checks. Pure stdlib (unittest), no
network, no daemon, no brain. Run: python3 -m unittest -v tests.test_sia
(from the repo root), or ./tests/test_sia.py.

Covers the load-bearing correctness properties a reviewer would poke at
first: cursor/replay semantics, epoch-merge idempotence, ledger verify,
PageRank mass conservation, novelty-as-absence, empirical surprise incl.
absence detection, redaction fail-closed, and touch-source weighting.
"""

import contextlib, copy, datetime, hashlib, importlib.machinery, importlib.util, json, os, re, sqlite3, stat
import subprocess, sys, tempfile, time, unittest
from unittest import mock

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")


def _load(name, path):
    if not path.endswith(".py"):
        loader = importlib.machinery.SourceFileLoader(name, path)
        spec = importlib.util.spec_from_loader(name, loader)
    else:
        spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

siamind = _load("siamind", os.path.join(BIN, "siamind.py"))


class TailCursors(unittest.TestCase):
    """Cursor semantics: first-run establishes without replay; truncation
    resets without replay; append yields only the new tail; torn byte
    tails wait for a whole line."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".log",
                                               delete=False)
        self.path = self.tmp.name
        self.tmp.close()
        self.cur = {}

    def tearDown(self):
        os.unlink(self.path)

    def _write(self, lines):
        with open(self.path, "w") as f:
            f.write("".join(l + "\n" for l in lines))

    def test_first_run_no_replay(self):
        self._write(["a", "b", "c"])
        self.assertEqual(siamind and [] or [], [])  # module import sanity
        import importlib
        sialib = _load("sialib", os.path.join(BIN, "sialib.py"))
        got = sialib.tail_lines(self.path, self.cur, "k")
        self.assertEqual(got, [], "first run must emit nothing")
        self.assertEqual(self.cur["k"], 3)

    def test_append_tail_only(self):
        sialib = _load("sialib", os.path.join(BIN, "sialib.py"))
        self._write(["a", "b"])
        sialib.tail_lines(self.path, self.cur, "k")
        self._write(["a", "b", "c", "d"])
        got = sialib.tail_lines(self.path, self.cur, "k")
        self.assertEqual(got, ["c", "d"])

    def test_truncation_replays_reachable_replacement(self):
        sialib = _load("sialib", os.path.join(BIN, "sialib.py"))
        self._write(["a", "b", "c", "d", "e"])
        sialib.tail_lines(self.path, self.cur, "k")
        self._write(["x", "y"])            # file shrank (rotation)
        got = sialib.tail_lines(self.path, self.cur, "k")
        self.assertEqual(got, ["x", "y"],
                         "replacement rows must not be silently skipped")
        self.assertEqual(self.cur["k"], 2)

    def test_same_or_larger_replacement_replays_after_digest_bootstrap(self):
        sialib = _load("sialib", os.path.join(BIN, "sialib.py"))
        self._write(["a", "b"])
        sialib.tail_lines(self.path, self.cur, "k")
        self._write(["x", "y", "z"])
        got = sialib.tail_lines(self.path, self.cur, "k")
        self.assertEqual(got, ["x", "y", "z"])
        self.assertEqual(self.cur["k.generation"], 1)

    def test_legacy_cursor_without_digest_replays_once_on_upgrade(self):
        sialib = _load("sialib", os.path.join(BIN, "sialib.py"))
        self._write(["a", "b", "c"])
        self.cur["k"] = 2
        got = sialib.tail_lines(self.path, self.cur, "k")
        self.assertEqual(got, ["a", "b", "c"])
        self.assertIn("k.prefix_sha256", self.cur)

    def test_torn_byte_tail_waits(self):
        sialib = _load("sialib", os.path.join(BIN, "sialib.py"))
        with open(self.path, "w") as f:
            f.write("first line\n")
        sialib.tail_bytes(self.path, self.cur, "b")
        with open(self.path, "a") as f:
            f.write("second line\nthird partial")   # no trailing newline
        data = sialib.tail_bytes(self.path, self.cur, "b")
        self.assertTrue(data.endswith(b"line\n"))
        self.assertNotIn(b"partial", data)          # torn tail withheld

    def test_bounded_line_windows_make_resumable_progress(self):
        sialib = _load("sialib_tail_window", os.path.join(BIN, "sialib.py"))
        self._write(["aa", "bb", "cc", "dd"])
        with mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}), \
                mock.patch.object(sialib, "MAX_SOURCE_TAIL_BYTES", 16), \
                mock.patch.object(sialib, "MAX_SOURCE_TAIL_RECORDS", 2), \
                mock.patch.object(sialib, "SOURCE_CURSOR_GUARD_BYTES", 4):
            first = sialib.tail_line_records(self.path, self.cur, "window")
            first_offset = self.cur["window.offset"]
            second = sialib.tail_line_records(self.path, self.cur, "window")
        self.assertEqual([row[2] for row in first], ["aa", "bb"])
        self.assertEqual([row[2] for row in second], ["cc", "dd"])
        self.assertLess(first_offset, self.cur["window.offset"])

    def test_only_literal_lf_advances_the_physical_record_ordinal(self):
        sialib = _load("sialib_literal_lf", os.path.join(BIN, "sialib.py"))
        with open(self.path, "w", encoding="utf-8") as stream:
            stream.write("alpha\u2028omega\nsecond\n")
        with mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
            rows = sialib.tail_line_records(self.path, self.cur, "physical")
        self.assertEqual([row[1] for row in rows], [0, 1])
        self.assertEqual([row[2] for row in rows],
                         ["alpha\u2028omega", "second"])

    def test_invalid_utf8_signable_refusal_advances_only_one_record(self):
        sialib = _load("sialib_invalid_utf8", os.path.join(BIN, "sialib.py"))
        with open(self.path, "wb") as stream:
            stream.write(b"invalid-\xff\nlater\n")
        with mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
            rows = sialib.tail_line_records(
                self.path, self.cur, "invalid")
            refusal = sialib._take_source_record_refusals(self.cur)
            later = sialib.tail_line_records(
                self.path, self.cur, "invalid")
        self.assertEqual(rows, [])
        self.assertEqual(len(refusal), 1)
        self.assertEqual(refusal[0]["reason"], "invalid-utf8-record")
        self.assertEqual(refusal[0]["ordinal"], 0)
        self.assertEqual([row[2] for row in later], ["later"])


class SourceReplayJournal(unittest.TestCase):
    def setUp(self):
        self.sialib = _load(
            "sialib_source_replay_test", os.path.join(BIN, "sialib.py"))
        self.when = datetime.datetime(
            2026, 8, 30, 12, 0, tzinfo=datetime.timezone.utc)

    def _event(self, summary="observed row"):
        return self.sialib.Event(
            "custom", self.when, "event", summary,
            {"organs/custom"}, {"custom"},
            occurrence="custom:demo:0:7")

    def _effects(self):
        return {"day": "2026-08-30", "events_pulse": 1,
                "organs": {"custom": {
                    "today": 1, "last_ts": "2026-08-30T12:00:00Z"}}}

    def test_replay_record_round_trip_binds_timestamp_and_meaning(self):
        original = self._event()
        record = self.sialib._event_replay_record(original)
        replay = self.sialib._event_from_replay_record(record)
        self.assertEqual(replay.ts, original.ts)
        self.assertEqual(
            self.sialib.event_memory_identity(replay),
            self.sialib.event_memory_identity(original))
        self.assertEqual(
            self.sialib.event_semantic_identity(replay),
            self.sialib.event_semantic_identity(original))

    def test_source_replay_clock_is_marker_bound_across_midnight(self):
        marker = {"started_at": "2026-08-30T23:59:59Z"}
        first = self.sialib._source_replay_clock(marker)
        second = self.sialib._source_replay_clock(marker)
        self.assertEqual(first, second)
        self.assertEqual(first[1], "2026-08-30")

    def test_marker_is_durable_and_semantic_conflicts_refuse(self):
        with tempfile.TemporaryDirectory() as state, mock.patch.object(
                self.sialib, "MEMO_PATH", os.path.join(state, "memo.json")):
            memo = {}
            self.sialib._mark_source_replay_pending(
                memo, 9, {"sense_custom:demo"}, [self._event()],
                self._effects())
            persisted = self.sialib.load_memo()
            marker = self.sialib._pending_source_replay_marker(persisted)
            self.assertEqual(len(marker["events"]), 1)
            with self.assertRaisesRegex(ValueError, "conflicts"):
                self.sialib._mark_source_replay_pending(
                    memo, 9, {"sense_custom:demo"},
                    [self._event("different meaning")], self._effects())

    def test_marker_preserves_duplicate_filtered_cognitive_admission(self):
        with tempfile.TemporaryDirectory() as state, mock.patch.object(
                self.sialib, "MEMO_PATH", os.path.join(state, "memo.json")):
            memo = {}
            self.sialib._mark_source_replay_pending(
                memo, 9, {"sense_custom:demo"}, [self._event()],
                self._effects(), cognitive_ids=[])
            marker = self.sialib._pending_source_replay_marker(
                self.sialib.load_memo())
        self.assertEqual(len(marker["events"]), 1)
        self.assertEqual(marker["cognitive_ids"], [])

    def test_one_batch_receipt_makes_cognitive_replay_idempotent(self):
        mind = self.sialib.siamind._empty_mind()
        event = self._event()
        admitted = [(event, "events/custom/2026-08-30")]
        identity = "a" * 32
        first = self.sialib._event_cognitive_transition(
            mind, admitted, self.when.timestamp(), "2026-08-30", identity)
        touches = mind["nodes"]["events/custom/2026-08-30"]["n"]
        second = self.sialib._event_cognitive_transition(
            mind, admitted, self.when.timestamp(), "2026-08-30", identity)
        self.assertFalse(first["already_applied"])
        self.assertTrue(second["already_applied"])
        self.assertEqual(
            mind["nodes"]["events/custom/2026-08-30"]["n"], touches)
        self.assertEqual(mind["event_batch_applied"], identity)

    def test_full_cognitive_candidate_detects_retained_pin_growth(self):
        mind = self.sialib.siamind._empty_mind()
        pinned = self.sialib.siamind.touch(
            mind, "organs/custom", ts=1, src="organ")
        pinned["pins"] = ["user"]
        pinned["padding"] = "x" * 800
        limit = len(self.sialib.siamind._mind_text(mind).encode("utf-8")) + 1
        self.sialib._event_cognitive_transition(
            mind, [(self._event(), "events/custom/2026-08-30")],
            self.when.timestamp(), "2026-08-30", "b" * 32)
        with mock.patch.object(
                self.sialib.siamind, "MAX_MIND_BYTES", limit), \
                self.assertRaisesRegex(ValueError, "persistence bound"):
            self.sialib.siamind.compact_mind_for_persistence(mind)

    def test_ordinary_pin_generation_settles_before_source_candidate(self):
        with tempfile.TemporaryDirectory() as root:
            corpus = os.path.join(root, "corpus")
            state = os.path.join(root, "state")
            os.makedirs(os.path.join(corpus, "events", "custom"))
            os.makedirs(state)
            slug = "events/custom/old"
            with open(os.path.join(corpus, slug + ".md"), "w") as stream:
                stream.write("# retained\n")
            queue = os.path.join(state, "touch-queue.jsonl")
            mind_path = os.path.join(state, "mind.json")
            with mock.patch.object(self.sialib, "CORPUS", corpus), \
                    mock.patch.object(
                        self.sialib.siamind, "MIND_PATH", mind_path), \
                    mock.patch.object(
                        self.sialib.siamind, "TOUCH_QUEUE", queue):
                self.sialib.siamind.save_mind(
                    self.sialib.siamind._empty_mind())
                self.assertTrue(self.sialib.siamind.queue_pin(
                    slug, True, ts=10))
                mind = self.sialib.siamind.load_mind(now=11)
                drained, refused = self.sialib._drain_ordinary_touches(
                    mind, 11)
                persisted = self.sialib.siamind.load_mind(now=11)
            self.assertEqual((drained, refused), (1, 0))
            self.assertIn("user", persisted["nodes"][slug]["pins"])
            self.assertNotIn("touch_queue_claim_sha256", persisted)
            self.assertFalse(os.path.exists(queue + ".draining"))

    def test_custom_source_success_is_reported_without_an_emitted_row(self):
        with tempfile.NamedTemporaryFile(mode="w") as stream, \
                mock.patch.object(self.sialib, "CONFIG", {
                    "custom_senses": [{"name": "demo", "path": stream.name}]
                }):
            events, errors, sources = self.sialib.sense_custom(
                {}, include_sources=True)
        self.assertEqual(events, [])
        self.assertEqual(errors, [])
        self.assertEqual(sources, ["sense_custom:demo"])

    def test_batch_occurrence_dedupes_across_dates_and_refuses_conflict(self):
        first = self._event()
        later = self._event()
        later.ts = later.ts + datetime.timedelta(days=1)
        self.assertEqual(self.sialib._dedupe_event_batch([first, later]),
                         [first])
        conflict = self._event("different meaning")
        conflict.ts = later.ts
        with self.assertRaisesRegex(ValueError, "identity conflicts"):
            self.sialib._dedupe_event_batch([first, conflict])

    def test_batch_path_preflight_counts_all_planned_dates_together(self):
        with tempfile.TemporaryDirectory() as corpus, \
                mock.patch.object(self.sialib, "CORPUS", corpus), \
                mock.patch.object(
                    self.sialib, "MAX_EVENT_LOOKUP_PAGES", 2):
            root = os.path.join(corpus, "events", "custom")
            os.makedirs(root)
            with open(os.path.join(root, "2026-08-29.md"), "w") as stream:
                stream.write("existing")
            planned = {"custom": {
                os.path.join(root, "2026-08-30.md"),
                os.path.join(root, "2026-08-31.md"),
            }}
            with self.assertRaisesRegex(ValueError, "bounded occurrence"):
                self.sialib._preflight_event_path_plan(planned)

    def test_event_directory_snapshot_refuses_before_unbounded_materialization(self):
        with tempfile.TemporaryDirectory() as corpus, \
                mock.patch.object(self.sialib, "CORPUS", corpus), \
                mock.patch.object(
                    self.sialib, "MAX_EVENT_LOOKUP_PAGES", 2), \
                mock.patch.object(
                    self.sialib, "MAX_EVENT_DIRECTORY_INSPECTIONS", 3), \
                mock.patch.object(
                    self.sialib.glob, "glob",
                    side_effect=AssertionError("glob is unbounded")):
            root = os.path.join(corpus, "events", "custom")
            os.makedirs(root)
            for name in ("alpha.md", "bravo.md", "charlie.md"):
                with open(os.path.join(root, name), "w") as stream:
                    stream.write("fixture")
            with self.assertRaisesRegex(ValueError, "page bound"):
                self.sialib._bounded_event_directory_snapshot(root)

    def test_event_directory_snapshot_does_not_turn_disappearance_into_empty(self):
        first_page = ([{"name": "alpha.md", "mode": stat.S_IFREG}],
                      False, 1, {"device": 1, "inode": 2, "cookie": 3,
                                 "size": 4, "mtime_ns": 5,
                                 "ctime_ns": 6, "reset": False})
        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=[first_page, FileNotFoundError("gone")]), \
                self.assertRaisesRegex(RuntimeError, "disappeared"):
            self.sialib._bounded_event_directory_snapshot("/fixture")

    def test_source_refusal_is_signed_with_stable_event_identity(self):
        event = self._event()
        event_id = self.sialib.event_memory_identity(event)
        with mock.patch.object(
                self.sialib, "durable_ledger_append") as append:
            self.sialib._settle_source_refusals(
                "sense_custom:demo", [event], "event-capacity")
            first = append.call_args
            append.reset_mock()
            self.sialib._settle_source_refusals(
                "sense_custom:demo", [event], "event-capacity")
            second = append.call_args
        self.assertEqual(first, second)
        args, kwargs = first
        self.assertEqual(args[:3], (
            "SOURCE:refuse", "sense_custom:demo", "event-capacity"))
        payload = json.loads(args[3])
        self.assertEqual(payload["event_id"], event_id)
        self.assertEqual(payload["source"], "sense_custom:demo")
        self.assertEqual(kwargs, {"order": int(event_id, 16)})

    def test_legacy_event_identity_collision_is_a_signed_refusal_class(self):
        refusal = self.sialib._source_refusal_code(ValueError(
            "legacy event cannot be identity-upgraded automatically"))
        self.assertEqual(refusal, "legacy-event-identity")
        self.assertIsNone(self.sialib._source_refusal_code(ValueError(
            "event identity conflicts with its day page")))

    def test_source_preflight_memo_refusal_has_no_corpus_side_effect(self):
        with tempfile.TemporaryDirectory() as corpus, \
                mock.patch.object(self.sialib, "CORPUS", corpus), \
                mock.patch.object(self.sialib, "MAX_MEMO_BYTES", 1):
            organs = {"custom": {"today": 0, "last_ts": ""}}
            with self.assertRaisesRegex(
                    ValueError, "brainstem memo exceeds its byte bound"):
                self.sialib._preflight_source_admission_image(
                    {}, 1, {"sense_custom:demo"}, [self._event()],
                    "2026-08-30", organs)
            self.assertEqual(os.listdir(corpus), [])


class WorldlineCursor(unittest.TestCase):
    """WORLDLINE pagination is total even when a page shares one timestamp."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        state = os.path.join(
            self.tmp.name, ".local", "state", "worldline")
        os.makedirs(state)
        self.db = os.path.join(state, "worldline.sqlite3")
        with contextlib.closing(sqlite3.connect(self.db)) as con:
            con.execute(
                "CREATE TABLE causal_events ("
                "event_id TEXT PRIMARY KEY, kind TEXT NOT NULL, actor TEXT, "
                "tool TEXT, reason TEXT, path_display TEXT, "
                "created_at TEXT NOT NULL, world_instance TEXT NOT NULL)")
            con.commit()
        self.sialib = _load(
            "sialib_worldline_cursor", os.path.join(BIN, "sialib.py"))
        self.sialib.HOME = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _insert(self, rows):
        with contextlib.closing(sqlite3.connect(self.db)) as con:
            con.executemany(
                "INSERT INTO causal_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows)
            con.commit()

    def test_composite_cursor_keeps_every_tied_row_across_pages(self):
        stamp = "2026-08-30T12:00:00.000000Z"
        # JACKAL exact: parsed=2000+1 exact=2001 (not formal-bounded).
        row_count = 2001
        with contextlib.closing(sqlite3.connect(self.db)) as con:
            con.executemany(
                "INSERT INTO causal_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(f"event-{index:04d}", "result", "tester",
                  f"tool-{index:04d}", "", "", stamp, "world-a")
                 for index in range(row_count)])
            con.commit()

        # This is the v1.2 timestamp-only cursor.  Replaying its tied instant
        # is safe and migrates it to the stable (created_at, event_id) pair.
        cursors = {"worldline.created_at": stamp}
        first = self.sialib.sense_worldline(cursors)
        second = self.sialib.sense_worldline(cursors)
        third = self.sialib.sense_worldline(cursors)

        self.assertEqual(len(first), 2000)
        self.assertEqual(len(second), 1)
        self.assertEqual(third, [])
        observed = first + second
        self.assertEqual(len(observed), row_count)
        self.assertEqual(len({event.summary for event in observed}), row_count)
        self.assertEqual(cursors, {
            "worldline.created_at": stamp,
            "worldline.event_id": "event-2000",
        })

    def test_malformed_composite_cursor_refuses_without_mutation(self):
        stamp = "2026-08-30T12:00:00.000000Z"
        malformed = [
            {"worldline.created_at": []},
            {"worldline.created_at": "not-a-timestamp"},
            {"worldline.event_id": "event-a"},
            {"worldline.created_at": "", "worldline.event_id": "event-a"},
            {"worldline.created_at": stamp, "worldline.event_id": []},
        ]
        for cursors in malformed:
            with self.subTest(cursors=cursors):
                before = copy.deepcopy(cursors)
                with self.assertRaisesRegex(ValueError, "worldline cursor"):
                    self.sialib.sense_worldline(cursors)
                self.assertEqual(cursors, before)

    def test_bad_page_row_never_partially_advances_cursor(self):
        self._insert([
            ("event-a", "result", "tester", "", "r" * (
                self.sialib.MAX_CONFIG_TEXT_CHARS + 1), "",
             "2026-08-30T12:00:00.000000Z", "world-a"),
            ("event-b", "result", "tester", "tool-b", "", "",
             "not-a-timestamp", "world-a"),
        ])
        cursors = {
            "worldline.created_at": "",
            "worldline.event_id": "",
        }
        before = copy.deepcopy(cursors)
        with self.assertRaisesRegex(ValueError, "worldline cursor"):
            self.sialib.sense_worldline(cursors)
        self.assertEqual(cursors, before)

    def test_guarded_query_is_rowwise_and_never_materializes_whole_text(self):
        stamp = "2026-08-30T12:00:00.000000Z"
        self._insert([("event-a", "result", "tester", "tool-a", "", "",
                      stamp, "world-a")])
        real_connect = sqlite3.connect
        statements = []

        class GuardCursor:
            def __init__(self, cursor):
                self.cursor = cursor

            def fetchone(self):
                return self.cursor.fetchone()

            def fetchall(self):
                raise AssertionError("WORLDLINE must not use fetchall")

        class GuardConnection:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, statement, parameters=()):
                statements.append(statement)
                return GuardCursor(self.connection.execute(
                    statement, parameters))

            def close(self):
                self.connection.close()

        def guarded_connect(*args, **kwargs):
            return GuardConnection(real_connect(*args, **kwargs))

        cursors = {"worldline.created_at": "",
                   "worldline.event_id": ""}
        with mock.patch.object(
                self.sialib.sqlite3, "connect",
                side_effect=guarded_connect):
            events = self.sialib.sense_worldline(cursors)

        self.assertEqual(len(events), 1)
        self.assertEqual(cursors["worldline.event_id"], "event-a")
        self.assertEqual(len(statements), 1)
        statement = statements[0]
        self.assertIn("typeof(event_id)", statement)
        self.assertIn("length(CAST(event_id AS BLOB))", statement)
        self.assertIn("substr(CAST(reason AS BLOB), 1, ?)", statement)
        self.assertIn("LIMIT ?", statement)

    def test_oversized_fields_refuse_and_later_row_progresses(self):
        stamp = "2026-08-30T12:00:00.000000Z"
        huge_kind = "k" * (self.sialib.MAX_SOURCE_NAME_CHARS + 1)
        huge_reason = "r" * (self.sialib.MAX_CONFIG_TEXT_CHARS + 1)
        self._insert([
            ("event-a", huge_kind, "tester", "", "", "", stamp,
             "world-a"),
            ("event-b", "result", "tester", "", huge_reason, "", stamp,
             "world-a"),
            ("event-c", "result", "tester", "tool-c", "", "", stamp,
             "bad world"),
            ("event-z", "result", "tester", "tool-z", "", "", stamp,
             "world-a"),
        ])
        cursors = {"worldline.created_at": "",
                   "worldline.event_id": ""}

        events = self.sialib.sense_worldline(cursors)

        self.assertEqual([event.kind for event in events], [
            "source-entry-refused", "source-entry-refused",
            "source-entry-refused", "result"])
        self.assertEqual(cursors["worldline.event_id"], "event-z")
        refusals = self.sialib._take_source_entry_refusals(
            cursors, "sense_worldline")
        self.assertEqual([row["reason"] for row in refusals], [
            "worldline-kind-capacity", "worldline-reason-capacity",
            "worldline-world-identity-invalid"])
        payload = json.dumps(refusals, sort_keys=True)
        self.assertNotIn(huge_kind, payload)
        self.assertNotIn(huge_reason, payload)

    def test_selected_byte_budget_paginates_without_drop_or_replay(self):
        stamp = "2026-08-30T12:00:00.000000Z"
        self._insert([
            (f"event-{letter}", "result", "tester", f"tool-{letter}",
             "", "", stamp, "world-a")
            for letter in "abc"
        ])
        cursors = {"worldline.created_at": "",
                   "worldline.event_id": ""}
        # JACKAL status=exact, parsed=7+6+6+6+27+7, exact=59;
        # parsed=59*2, exact=118. Both results are exact rational
        # arithmetic outside the Lean certificate chain (NOT formal-bounded).
        with mock.patch.object(
                self.sialib, "MAX_WORLDLINE_PAGE_BYTES", 100):
            pages = [self.sialib.sense_worldline(cursors)
                     for _index in range(4)]

        self.assertEqual([len(page) for page in pages], [1, 1, 1, 0])
        occurrences = [event.occurrence
                       for page in pages for event in page]
        self.assertEqual(occurrences, [
            "worldline:event-a", "worldline:event-b", "worldline:event-c"])
        self.assertEqual(cursors["worldline.event_id"], "event-c")

    def test_refusal_signing_retries_exactly_and_is_source_namespaced(self):
        stamp = "2026-08-30T12:00:00.000000Z"
        huge_reason = "r" * (self.sialib.MAX_CONFIG_TEXT_CHARS + 1)
        self._insert([
            ("event-a", "result", "tester", "", huge_reason, "", stamp,
             "world-a"),
            ("event-b", "result", "tester", "tool-b", "", "", stamp,
             "world-a"),
        ])
        durable = {"worldline.created_at": "",
                   "worldline.event_id": ""}
        attempts = []
        append_calls = []
        for _attempt in range(2):
            trial = copy.deepcopy(durable)
            events = self.sialib.sense_worldline(trial)
            pending = self.sialib._take_source_entry_refusals(
                trial, "sense_worldline")
            with mock.patch.object(
                    self.sialib, "durable_ledger_append") as append:
                self.sialib._settle_source_entry_refusals(
                    "sense_worldline", pending)
                append_calls.append((
                    copy.deepcopy(append.call_args.args),
                    copy.deepcopy(append.call_args.kwargs)))
            attempts.append((
                [event.occurrence for event in events], pending, trial))

        # The first settled trial is discarded as though the process died
        # before cursor publication. Its exact refusal is regenerated and
        # keeper settlement receives the same idempotent occurrence.
        self.assertEqual(attempts[0], attempts[1])
        self.assertEqual(append_calls[0], append_calls[1])
        self.assertEqual(durable["worldline.event_id"], "")
        durable.clear()
        durable.update(attempts[1][2])
        self.assertEqual(durable["worldline.event_id"], "event-b")
        persisted = {
            self.sialib.SOURCE_ENTRY_REFUSALS_KEY:
                copy.deepcopy(attempts[1][1])}
        carried = copy.deepcopy(persisted)
        self.assertEqual(self.sialib._take_owned_source_entry_refusals(
            lambda _cursors: [], carried, True,
            persisted[self.sialib.SOURCE_ENTRY_REFUSALS_KEY]), [])
        self.assertEqual(carried, persisted)
        injected = {
            self.sialib.SOURCE_ENTRY_REFUSALS_KEY:
                copy.deepcopy(attempts[1][1])}
        with self.assertRaisesRegex(ValueError, "reserved for sense_worldline"):
            self.sialib._take_owned_source_entry_refusals(
                lambda _cursors: [], injected, False, None)
        wrong_source = {
            self.sialib.SOURCE_ENTRY_REFUSALS_KEY:
                copy.deepcopy(attempts[1][1])}
        with self.assertRaisesRegex(
                ValueError, "source entry refusal state is invalid"):
            self.sialib._take_source_entry_refusals(
                wrong_source, "sense_journal")

    def test_oversized_ordering_identity_never_advances(self):
        stamp = "2026-08-30T12:00:00.000000Z"
        self._insert([(
            "e" * (self.sialib.MAX_SOURCE_NAME_CHARS + 1),
            "result", "tester", "tool-a", "", "", stamp, "world-a")])
        cursors = {"worldline.created_at": "",
                   "worldline.event_id": ""}
        before = copy.deepcopy(cursors)
        with self.assertRaisesRegex(ValueError, "worldline cursor event id"):
            self.sialib.sense_worldline(cursors)
        self.assertEqual(cursors, before)


class PPRMass(unittest.TestCase):
    """Personalized PageRank: dangling mass returns to the personalization
    vector (no rank leaks to zero); dense order is the primary signal."""

    def test_dangling_conserved(self):
        graph = {"nodes": [{"id": c} for c in "abcde"],
                 "edges": [{"s": "a", "d": "b"}, {"s": "b", "d": "c"}]}
        # 'd' is dangling (no edges); its mass must not vanish
        out = siamind.ppr_rerank(graph, [("a", 1.0), ("d", 0.5)])
        self.assertTrue(out, "must return results")
        slugs = [s for s, _ in out]
        self.assertIn("a", slugs)
        self.assertIn("d", slugs)
        # top hit is the strongest dense seed
        self.assertEqual(out[0][0], "a")

    def test_uncertainty_fallback(self):
        # empty graph -> pure dense order preserved
        out = siamind.ppr_rerank({"nodes": [], "edges": []},
                                 [("x", 0.9), ("y", 0.3)])
        self.assertEqual([s for s, _ in out], ["x", "y"])

    def test_declared_model_origin_is_demoted_with_and_without_graph(self):
        hits = [("thoughts/model", 1.0), ("events/evidence", 1.0)]
        origins = {"thoughts/model": "model",
                   "events/evidence": "evidence"}
        for graph in (None, {"nodes": [], "edges": []}):
            with self.subTest(graph=graph):
                out = siamind.ppr_rerank(graph, hits, origins=origins)
                self.assertEqual(out[0][0], "events/evidence")
                self.assertLess(dict(out)["thoughts/model"],
                                dict(out)["events/evidence"])

        graph = {
            "nodes": [
                {"id": "thoughts/model", "t": "thought",
                 "origin": "model"},
                {"id": "events/evidence", "t": "event-day",
                 "origin": "evidence"},
            ],
            "edges": [{"s": "thoughts/model", "d": "events/evidence"}],
        }
        out = siamind.ppr_rerank(graph, hits)
        self.assertEqual(out[0][0], "events/evidence")

    def test_legacy_thought_and_invalid_origin_fail_safe(self):
        self.assertEqual(siamind.origin_class(
            "thoughts/old", "thought"), "legacy-unlabeled")
        self.assertEqual(siamind.origin_class(
            "thoughts/old", "thought", "invented"),
            "legacy-unlabeled")
        self.assertEqual(siamind.origin_class(
            "thoughts/new", "thought", "model"), "model")
        self.assertEqual(siamind.origin_class(
            "takes/legacy-graded", "take"), "legacy-unlabeled")
        self.assertEqual(siamind.origin_class(
            "takes/new-open", "take", "derived"), "derived")


class Novelty(unittest.TestCase):
    """Novelty measures ABSENCE, not first-sighting age: a continuously
    seen entity never re-fires the 30-day bonus."""

    def test_absence_not_age(self):
        mind = {"seen": {}}
        now = 1_000_000_000.0
        s1, _ = siamind.novelty(mind, "o", "k", ["e"], ["k"] * 10, now)
        self.assertGreaterEqual(s1, 0.4)               # first sighting
        # seen again one hour later: no bonus (not absent)
        s2, _ = siamind.novelty(mind, "o", "k", ["e"], ["k"] * 10, now + 3600)
        self.assertLess(s2, 0.4)
        # seen again 40 days after THAT: genuine return
        s3, _ = siamind.novelty(mind, "o", "k", ["e"], ["k"] * 10,
                                now + 3600 + 40 * 86400)
        self.assertGreaterEqual(s3, 0.2)


class Surprise(unittest.TestCase):
    """Empirical-band surprise: no Poisson, and absence is reachable for a
    paced band once it has enough samples."""

    def test_no_poisson_symbols(self):
        self.assertFalse(hasattr(siamind, "SURPRISAL_BITS"))
        self.assertFalse(hasattr(siamind, "EWMA_HALFLIFE_H"))

    def test_absence_reachable(self):
        mind = {"hourbuf": {}, "hist": {}, "ewma": {}, "cooldown": {}}
        # Cover every weekday/weekend × six-hour band with a fully active
        # history independent of the wall-clock day on which CI runs. JACKAL
        # exact: parsed=8*7*24, exact=1344 (not formal-bounded).
        active_hours = 1344
        for hour in range(active_hours):
            siamind.surprisal_update(
                mind, {"org": 5}, hour * 3600 + 10)
        # Advance twice: the first call opens the silent bucket; the second
        # closes and evaluates it while another organ keeps time advancing.
        siamind.surprisal_update(
            mind, {"other": 1}, active_hours * 3600 + 10)
        found = siamind.surprisal_update(
            mind, {"other": 1}, (active_hours + 1) * 3600 + 10)
        self.assertTrue(any(o == "org" and k == "absence"
                            for o, k, _ in found),
                        "absence-surprise must fire for a paced band")


class ChainVerdict(unittest.TestCase):
    def test_absent_chain_never_aggregates_to_pass(self):
        sialib = _load("sialib_chain_verdict", os.path.join(BIN, "sialib.py"))
        self.assertEqual(sialib.chain_verdict({"sia": "absent"}),
                         "degraded")
        self.assertEqual(sialib.chain_verdict(
            {"sia": "pass", "custos": "absent"}), "degraded")
        self.assertEqual(sialib.chain_verdict(
            {"sia": "pass", "custos": "fail"}), "fail")
        self.assertEqual(sialib.chain_verdict({"sia": "pass"}), "pass")

    def test_removed_verified_chain_emits_absent_transition_once(self):
        sialib = _load("sialib_chain_transition",
                       os.path.join(BIN, "sialib.py"))
        memo = {"chains": {"sia": "pass", "custos": "pass"}}

        def thought(_store, kind, text, links, urgent=False, **_metadata):
            return {"kind": kind, "text": text, "links": links,
                    "urgent": urgent}

        with mock.patch.object(sialib, "add_thought", side_effect=thought):
            first = sialib.think({}, memo, [], {"sia": "pass"}, [], [])
            after_first = copy.deepcopy(memo["chains"])
            repeated = sialib.think({}, memo, [], {"sia": "pass"}, [], [])
            recovered = sialib.think(
                {}, memo, [], {"sia": "pass", "custos": "pass"}, [], [])
        self.assertIn("no longer verifiable: custos", first[0]["text"])
        self.assertTrue(first[0]["urgent"])
        self.assertEqual(after_first, {"sia": "pass"})
        self.assertEqual(memo["chains"], {"sia": "pass", "custos": "pass"})
        self.assertEqual(repeated, [])
        self.assertIn("Newly observed evidence chain verifies",
                      recovered[0]["text"])

    def test_new_absent_chain_never_claims_all_verify(self):
        sialib = _load("sialib_chain_new_absent",
                       os.path.join(BIN, "sialib.py"))
        memo = {"chains": {"sia": "pass"}}

        def thought(_store, kind, text, links, urgent=False, **_metadata):
            return {"kind": kind, "text": text, "links": links,
                    "urgent": urgent}

        with mock.patch.object(sialib, "add_thought", side_effect=thought):
            emitted = sialib.think(
                {}, memo, [], {"sia": "pass", "custos": "absent"}, [], [])
        texts = [item["text"] for item in emitted]
        self.assertTrue(any("no longer verifiable: custos" in text
                            for text in texts))
        self.assertFalse(any("All evidence chains verify again" in text
                             for text in texts))

    def test_event_thought_identity_uses_source_day_not_retry_day(self):
        sialib = _load("sialib_think_source_clock",
                       os.path.join(BIN, "sialib.py"))
        event = sialib.Event(
            "journal", datetime.datetime.now(datetime.timezone.utc),
            "error", "process crashed", {"units/example"}, {"coredump"},
            occurrence="journal:stable")
        observed = []

        def thought(_store, kind, text, links, urgent=False, **metadata):
            observed.append(metadata["queue_id"])
            return {"kind": kind, "text": text}

        with mock.patch.object(sialib, "today", return_value="2026-08-31"), \
                mock.patch.object(sialib, "add_thought", side_effect=thought):
            sialib.think(
                {}, {}, [event], {}, [], [], event_day="2026-08-30")
        text = "Something crashed: process crashed."
        expected = sialib.thought_queue_identity(
            "think.generated", "crash", text, ["units/example"], True,
            day="2026-08-30")
        self.assertEqual(observed, [expected])

    def test_refusal_thought_attribution_preserves_source_boundary(self):
        sialib = _load("sialib_think_refusal_boundary",
                       os.path.join(BIN, "sialib.py"))
        emitted = []

        def thought(_store, kind, text, links, urgent=False, **_metadata):
            emitted.append((kind, text, links))
            return {"kind": kind, "text": text}

        journal = sialib.Event(
            "journal", datetime.datetime.now(datetime.timezone.utc),
            "source-entry-refused", "row could not be admitted",
            {"organs/journal"}, {"refusal"}, occurrence="journal:refusal")
        jackal = sialib.Event(
            "jackal", datetime.datetime.now(datetime.timezone.utc),
            "refused", "fixture → refused", {"organs/jackal"},
            {"refusal", "unverified-observation"},
            occurrence="jackal:refusal")
        with mock.patch.object(sialib, "add_thought", side_effect=thought):
            sialib.think({}, {}, [journal], {}, [], [],
                         event_day="2026-08-30")
        self.assertNotIn("JACKAL", emitted[0][1])
        self.assertIn("journal source refused", emitted[0][1])
        emitted.clear()
        with mock.patch.object(sialib, "add_thought", side_effect=thought):
            sialib.think({}, {}, [jackal], {}, [], [],
                         event_day="2026-08-30")
        self.assertIn("unverified JACKAL recall ledger reports", emitted[0][1])
        self.assertIn("not front-door reverified", emitted[0][1])
        self.assertNotIn("JACKAL refused to answer", emitted[0][1])

    def test_anomaly_and_attention_identities_preserve_recurrence(self):
        sialib = _load("sialib_think_recurring_identity",
                       os.path.join(BIN, "sialib.py"))
        observed = []

        def thought(_store, kind, text, links, urgent=False, **metadata):
            observed.append((kind, metadata["queue_id"]))
            return {"kind": kind, "text": text}

        anomaly = [{"cohort_kind": "organ", "cohort_value": "journal",
                    "count": 9, "baseline_mean": 2, "baseline_stddev": 1}]
        memo = {"salience_top": "events/old"}
        with mock.patch.object(sialib, "today", return_value="2026-08-30"), \
                mock.patch.object(sialib, "add_thought", side_effect=thought):
            sialib.think({}, memo, [], {},
                         [{"slug": "events/new", "title": "New"}], anomaly)
        first = dict(observed)
        observed.clear()
        memo["anomaly_keys"] = []
        memo["salience_top"] = "events/new"
        with mock.patch.object(sialib, "today", return_value="2026-08-31"), \
                mock.patch.object(sialib, "add_thought", side_effect=thought):
            sialib.think({}, memo, [], {},
                         [{"slug": "events/old", "title": "Old"}], anomaly)
        second = dict(observed)
        self.assertNotEqual(first["anomaly"], second["anomaly"])
        self.assertNotEqual(first["attention"], second["attention"])


class Ledger(unittest.TestCase):
    """The signed run ledger initializes and verifies; a tampered row is
    rejected (sticky)."""

    def _ledger_command(self, *args):
        return subprocess.run(
            [sys.executable, os.path.join(BIN, "sia-ledger"), *args],
            capture_output=True, text=True, timeout=30)

    def _initialize(self, state):
        initialized = self._ledger_command("init", state)
        self.assertEqual(initialized.returncode, 0, initialized.stderr)

    def test_init_verify_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            led = os.path.join(BIN, "sia-ledger")
            r = subprocess.run([sys.executable, led, "init", d],
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            v = subprocess.run([sys.executable, led, "verify", d, "--quiet"],
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(v.returncode, 0, "fresh ledger must verify")
            # append a row, verify still good
            subprocess.run([sys.executable, led, "append", d, "TEST:row",
                            "a", "b",
                            "0" * 64, "0"], capture_output=True, timeout=30)
            v2 = subprocess.run([sys.executable, led, "verify", d, "--quiet"],
                                capture_output=True, timeout=30)
            self.assertEqual(v2.returncode, 0)
            # tamper: flip a byte in the ledger, expect failure
            lp = os.path.join(d, "ledger.tsv")
            with open(lp) as stream:
                rows = stream.read().splitlines()
            rows[-1] = rows[-1].replace("\tb\t", "\tZ\t", 1)
            with open(lp, "w") as stream:
                stream.write("\n".join(rows) + "\n")
            v3 = subprocess.run([sys.executable, led, "verify", d, "--quiet"],
                                capture_output=True, timeout=30)
            self.assertNotEqual(v3.returncode, 0, "tampered row must reject")

    def test_signed_tail_recovers_after_pin_publish_interruption(self):
        with tempfile.TemporaryDirectory() as state:
            led = os.path.join(BIN, "sia-ledger")
            initialized = subprocess.run(
                [sys.executable, led, "init", state], capture_output=True,
                text=True, timeout=30)
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            keeper = _load("sia_ledger_recovery", led)
            original_atomic = keeper._atomic_write

            def interrupt_pin(path, data):
                if path.endswith("head.pin"):
                    raise OSError("injected pin publish interruption")
                return original_atomic(path, data)

            keeper._atomic_write = interrupt_pin
            try:
                with keeper._ledger_lock(state):
                    with self.assertRaisesRegex(
                            OSError, "injected pin publish interruption"):
                        keeper._append_row(
                            state, "TEST:recovery", "a", "b", "0" * 64, 0)
            finally:
                keeper._atomic_write = original_atomic

            verified = subprocess.run(
                [sys.executable, led, "verify", state, "--quiet"],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(verified.returncode, 0, verified.stdout)
            with open(os.path.join(state, "ledger.tsv")) as stream:
                rows = stream.read().splitlines()
            with open(os.path.join(state, "head.pin")) as stream:
                count, _head = stream.read().split()
            self.assertEqual(int(count), len(rows))

    def test_authoritative_file_reads_refuse_symlinks(self):
        for name in ("ledger.tsv", "key.hex", "pub.hex", "head.pin"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as state:
                self._initialize(state)
                path = os.path.join(state, name)
                real = path + ".real"
                os.replace(path, real)
                os.symlink(os.path.basename(real), path)
                with open(real, "rb") as stream:
                    before = stream.read()
                if name == "key.hex":
                    result = self._ledger_command(
                        "append", state, "TEST:symlink", "a", "b",
                        "0" * 64, "0")
                else:
                    result = self._ledger_command(
                        "verify", state, "--quiet")
                self.assertNotEqual(result.returncode, 0)
                with open(real, "rb") as stream:
                    self.assertEqual(stream.read(), before)

    def test_dangling_authoritative_link_refuses_fresh_init(self):
        with tempfile.TemporaryDirectory() as state:
            ledger = os.path.join(state, "ledger.tsv")
            target = os.path.join(state, "must-not-be-created")
            os.symlink(target, ledger)
            refused = self._ledger_command("init", state)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("incomplete initialized state", refused.stderr)
            self.assertTrue(os.path.islink(ledger))
            self.assertFalse(os.path.exists(target))
            for name in ("key.hex", "pub.hex", "head.pin"):
                self.assertFalse(os.path.lexists(os.path.join(state, name)))

    def test_predictable_stage_symlinks_are_never_followed(self):
        with tempfile.TemporaryDirectory() as state:
            self._initialize(state)
            victim = os.path.join(state, "victim")
            with open(victim, "wb") as stream:
                stream.write(b"unchanged")
            traps = [os.path.join(state, "ledger.tsv.new"),
                     os.path.join(state, "head.pin.new")]
            for trap in traps:
                os.symlink(victim, trap)
            appended = self._ledger_command(
                "append", state, "TEST:staging", "a", "b",
                "0" * 64, "0")
            self.assertEqual(appended.returncode, 0, appended.stderr)
            with open(victim, "rb") as stream:
                self.assertEqual(stream.read(), b"unchanged")
            self.assertTrue(all(os.path.islink(trap) for trap in traps))
            stage_names = [name for name in os.listdir(state)
                           if ".stage." in name]
            self.assertEqual(stage_names, [])

    def test_pending_journal_symlink_refuses_without_following(self):
        with tempfile.TemporaryDirectory() as state:
            self._initialize(state)
            victim = os.path.join(state, "victim")
            with open(victim, "wb") as stream:
                stream.write(b"do not touch")
            os.symlink(victim, os.path.join(state, "ledger.pending"))
            ledger = os.path.join(state, "ledger.tsv")
            with open(ledger, "rb") as stream:
                before = stream.read()
            refused = self._ledger_command(
                "append", state, "TEST:journal-link", "a", "b",
                "0" * 64, "0")
            self.assertNotEqual(refused.returncode, 0)
            with open(victim, "rb") as stream:
                self.assertEqual(stream.read(), b"do not touch")
            with open(ledger, "rb") as stream:
                self.assertEqual(stream.read(), before)

    def test_torn_append_recovers_only_from_exact_pending_row(self):
        with tempfile.TemporaryDirectory() as state:
            self._initialize(state)
            led = os.path.join(BIN, "sia-ledger")
            keeper = _load("sia_ledger_torn_recovery", led)
            original_append = keeper._append_bytes

            def interrupt_append(path, data, _expected_info):
                fd = os.open(path, os.O_WRONLY | os.O_APPEND)
                try:
                    os.write(fd, data[:8])
                    os.fsync(fd)
                finally:
                    os.close(fd)
                raise OSError("injected partial append")

            keeper._append_bytes = interrupt_append
            try:
                with keeper._ledger_lock(state):
                    with self.assertRaisesRegex(
                            OSError, "injected partial append"):
                        keeper._append_row(
                            state, "TEST:torn", "a", "b", "0" * 64, 0)
            finally:
                keeper._append_bytes = original_append

            self.assertTrue(os.path.exists(
                os.path.join(state, "ledger.pending")))
            verified = self._ledger_command("verify", state, "--quiet")
            self.assertEqual(verified.returncode, 0, verified.stdout)
            self.assertFalse(os.path.lexists(
                os.path.join(state, "ledger.pending")))
            with open(os.path.join(state, "ledger.tsv")) as stream:
                self.assertEqual(len(stream.read().splitlines()), 2)

    def test_published_journal_recovers_before_any_append_byte(self):
        with tempfile.TemporaryDirectory() as state:
            self._initialize(state)
            led = os.path.join(BIN, "sia-ledger")
            keeper = _load("sia_ledger_preappend_recovery", led)
            original_append = keeper._append_bytes

            def interrupt_before_append(_path, _data, _expected_info):
                raise OSError("injected pre-append interruption")

            keeper._append_bytes = interrupt_before_append
            try:
                with keeper._ledger_lock(state):
                    with self.assertRaisesRegex(
                            OSError, "injected pre-append interruption"):
                        keeper._append_row(
                            state, "TEST:preappend", "a", "b", "0" * 64, 0)
            finally:
                keeper._append_bytes = original_append

            verified = self._ledger_command("verify", state, "--quiet")
            self.assertEqual(verified.returncode, 0, verified.stdout)
            with open(os.path.join(state, "ledger.tsv")) as stream:
                rows = stream.read().splitlines()
            self.assertEqual([row.split("\t")[2] for row in rows],
                             ["GENESIS:init", "TEST:preappend"])
            self.assertFalse(os.path.lexists(
                os.path.join(state, "ledger.pending")))

    def test_pin_durable_before_cleanup_recovers_without_duplicate(self):
        with tempfile.TemporaryDirectory() as state:
            self._initialize(state)
            led = os.path.join(BIN, "sia-ledger")
            keeper = _load("sia_ledger_postpin_recovery", led)
            original_remove = keeper._remove_pending

            def interrupt_cleanup(_state, _expected_info):
                raise OSError("injected journal cleanup interruption")

            keeper._remove_pending = interrupt_cleanup
            try:
                with keeper._ledger_lock(state):
                    with self.assertRaisesRegex(
                            OSError, "injected journal cleanup interruption"):
                        keeper._append_row(
                            state, "TEST:postpin", "a", "b", "0" * 64, 0)
            finally:
                keeper._remove_pending = original_remove

            verified = self._ledger_command("verify", state, "--quiet")
            self.assertEqual(verified.returncode, 0, verified.stdout)
            with open(os.path.join(state, "ledger.tsv")) as stream:
                rows = stream.read().splitlines()
            self.assertEqual([row.split("\t")[2] for row in rows],
                             ["GENESIS:init", "TEST:postpin"])
            self.assertFalse(os.path.lexists(
                os.path.join(state, "ledger.pending")))

    def test_torn_tail_without_journal_refuses_without_mutation(self):
        with tempfile.TemporaryDirectory() as state:
            self._initialize(state)
            ledger = os.path.join(state, "ledger.tsv")
            with open(ledger, "ab") as stream:
                stream.write(b"unsigned partial tail")
                stream.flush()
                os.fsync(stream.fileno())
            with open(ledger, "rb") as stream:
                before = stream.read()
            refused = self._ledger_command("verify", state, "--quiet")
            self.assertNotEqual(refused.returncode, 0)
            with open(ledger, "rb") as stream:
                self.assertEqual(stream.read(), before)

    def test_mismatched_torn_tail_and_journal_refuse_without_truncation(self):
        with tempfile.TemporaryDirectory() as state:
            self._initialize(state)
            led = os.path.join(BIN, "sia-ledger")
            keeper = _load("sia_ledger_mismatched_torn_tail", led)
            original_append = keeper._append_bytes

            def interrupt_before_append(_path, _data, _expected_info):
                raise OSError("injected pre-append interruption")

            keeper._append_bytes = interrupt_before_append
            try:
                with keeper._ledger_lock(state):
                    with self.assertRaisesRegex(
                            OSError, "injected pre-append interruption"):
                        keeper._append_row(
                            state, "TEST:mismatch", "a", "b", "0" * 64, 0)
            finally:
                keeper._append_bytes = original_append

            ledger = os.path.join(state, "ledger.tsv")
            with open(ledger, "ab") as stream:
                stream.write(b"not-the-journal-row")
                stream.flush()
                os.fsync(stream.fileno())
            with open(ledger, "rb") as stream:
                before = stream.read()
            refused = self._ledger_command("verify", state, "--quiet")
            self.assertNotEqual(refused.returncode, 0)
            with open(ledger, "rb") as stream:
                self.assertEqual(stream.read(), before)
            self.assertTrue(os.path.exists(
                os.path.join(state, "ledger.pending")))

    def test_exact_signed_tail_recovers_without_journal(self):
        with tempfile.TemporaryDirectory() as state:
            self._initialize(state)
            led = os.path.join(BIN, "sia-ledger")
            keeper = _load("sia_ledger_legacy_tail", led)
            original_atomic = keeper._atomic_write

            def interrupt_pin(path, data):
                if path.endswith("head.pin"):
                    raise OSError("injected pin publish interruption")
                return original_atomic(path, data)

            keeper._atomic_write = interrupt_pin
            try:
                with keeper._ledger_lock(state):
                    with self.assertRaisesRegex(
                            OSError, "injected pin publish interruption"):
                        keeper._append_row(
                            state, "TEST:exact-tail", "a", "b",
                            "0" * 64, 0)
            finally:
                keeper._atomic_write = original_atomic
            os.unlink(os.path.join(state, "ledger.pending"))

            verified = self._ledger_command("verify", state, "--quiet")
            self.assertEqual(verified.returncode, 0, verified.stdout)
            with open(os.path.join(state, "ledger.tsv")) as stream:
                rows = stream.read().splitlines()
            with open(os.path.join(state, "head.pin")) as stream:
                count, _head = stream.read().split()
            self.assertEqual(int(count), len(rows))

    def test_append_is_in_place_and_preserves_ledger_inode(self):
        with tempfile.TemporaryDirectory() as state:
            self._initialize(state)
            ledger = os.path.join(state, "ledger.tsv")
            before = os.stat(ledger)
            appended = self._ledger_command(
                "append", state, "TEST:inode", "a", "b",
                "0" * 64, "0")
            self.assertEqual(appended.returncode, 0, appended.stderr)
            after = os.stat(ledger)
            self.assertEqual((after.st_dev, after.st_ino),
                             (before.st_dev, before.st_ino))

    def test_ledger_rollback_behind_pin_is_rejected(self):
        with tempfile.TemporaryDirectory() as state:
            self._initialize(state)
            ledger = os.path.join(state, "ledger.tsv")
            with open(ledger, "rb") as stream:
                genesis = stream.read()
            appended = self._ledger_command(
                "append", state, "TEST:rollback", "a", "b",
                "0" * 64, "0")
            self.assertEqual(appended.returncode, 0, appended.stderr)
            with open(ledger, "wb") as stream:
                stream.write(genesis)
                stream.flush()
                os.fsync(stream.fileno())
            refused = self._ledger_command("verify", state, "--quiet")
            self.assertNotEqual(refused.returncode, 0)
            with open(ledger, "rb") as stream:
                self.assertEqual(stream.read(), genesis)

    def test_size_ceiling_refuses_before_journal_or_ledger_mutation(self):
        with tempfile.TemporaryDirectory() as state:
            self._initialize(state)
            led = os.path.join(BIN, "sia-ledger")
            keeper = _load("sia_ledger_size_ceiling", led)
            ledger = os.path.join(state, "ledger.tsv")
            with open(ledger, "rb") as stream:
                before = stream.read()
            original_limit = keeper.MAX_LEDGER_BYTES
            keeper.MAX_LEDGER_BYTES = len(before)
            try:
                with keeper._ledger_lock(state):
                    with self.assertRaisesRegex(
                            ValueError, "LEDGER SIZE LIMIT"):
                        keeper._append_row(
                            state, "TEST:ceiling", "a", "b", "0" * 64, 0)
            finally:
                keeper.MAX_LEDGER_BYTES = original_limit
            with open(ledger, "rb") as stream:
                self.assertEqual(stream.read(), before)
            self.assertFalse(os.path.lexists(
                os.path.join(state, "ledger.pending")))

    def test_mismatched_private_key_refuses_before_ledger_mutation(self):
        with tempfile.TemporaryDirectory() as state:
            led = os.path.join(BIN, "sia-ledger")
            initialized = subprocess.run(
                [sys.executable, led, "init", state], capture_output=True,
                text=True, timeout=30)
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            ledger_path = os.path.join(state, "ledger.tsv")
            with open(ledger_path) as stream:
                before = stream.read()
            with open(os.path.join(state, "pub.hex")) as stream:
                expected_public = stream.read().strip()
            replacement = Ed25519PrivateKey.generate()
            while replacement.public_key().public_bytes_raw().hex() \
                    == expected_public:
                replacement = Ed25519PrivateKey.generate()
            with open(os.path.join(state, "key.hex"), "w") as stream:
                stream.write(replacement.private_bytes_raw().hex() + "\n")

            refused = subprocess.run(
                [sys.executable, led, "append", state, "TEST:key", "a", "b",
                 "0" * 64, "0"], capture_output=True, text=True, timeout=30)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("DOES NOT MATCH", refused.stderr)
            with open(ledger_path) as stream:
                self.assertEqual(stream.read(), before)
            verified = subprocess.run(
                [sys.executable, led, "verify", state, "--quiet"],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(verified.returncode, 0, verified.stdout)

    def test_public_key_swap_after_signer_binding_refuses_before_append(self):
        with tempfile.TemporaryDirectory() as state:
            self._initialize(state)
            led = os.path.join(BIN, "sia-ledger")
            keeper = _load("sia_ledger_key_swap", led)
            ledger = os.path.join(state, "ledger.tsv")
            public_path = os.path.join(state, "pub.hex")
            with open(ledger, "rb") as stream:
                before = stream.read()
            with open(public_path, "rb") as stream:
                original_public = stream.read()
            replacement_public = Ed25519PrivateKey.generate() \
                .public_key().public_bytes_raw().hex()
            original_signing_key = keeper._signing_key

            def swap_after_binding(bound_state):
                signing_key = original_signing_key(bound_state)
                with open(public_path, "w") as stream:
                    stream.write(replacement_public + "\n")
                return signing_key

            keeper._signing_key = swap_after_binding
            try:
                with keeper._ledger_lock(state):
                    with self.assertRaisesRegex(
                            ValueError, "PUBLIC KEY CHANGED"):
                        keeper._append_row(
                            state, "TEST:key-swap", "a", "b", "0" * 64, 0)
            finally:
                keeper._signing_key = original_signing_key
                with open(public_path, "wb") as stream:
                    stream.write(original_public)
            with open(ledger, "rb") as stream:
                self.assertEqual(stream.read(), before)
            self.assertFalse(os.path.lexists(
                os.path.join(state, "ledger.pending")))


class SessionMetadataPrivacy(unittest.TestCase):
    def test_claude_session_sense_never_opens_jsonl_payload(self):
        sialib = _load("sialib_claude_metadata",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as home:
            directory = os.path.join(home, ".claude", "projects", "fixture")
            os.makedirs(directory)
            session = os.path.join(directory, "session.jsonl")
            with open(session, "w") as stream:
                stream.write('{"type":"user","message":"private"}\n')
            old_home = sialib.HOME
            sialib.HOME = home
            cursors = {}
            try:
                first = sialib.sense_claude(cursors)
                self.assertTrue(first)
                with open(session, "a") as stream:
                    stream.write(
                        '{"type":"assistant","message":"also private"}\n')
                with mock.patch("builtins.open",
                                side_effect=AssertionError(
                                    "session payload must remain unopened")):
                    later = sialib.sense_claude(cursors)
            finally:
                sialib.HOME = old_home
            self.assertTrue(later)
            self.assertTrue(all("private" not in event.summary
                                for event in later))


class GbrainProcessBounds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sialib = _load(
            "sialib_gbrain_process_bounds", os.path.join(BIN, "sialib.py"))

    def _run(self, code, *, timeout=30):
        with tempfile.TemporaryDirectory() as cwd:
            return self.sialib._run_bounded_text_process(
                [sys.executable, "-c", code], env=dict(os.environ),
                timeout=timeout, cwd=cwd)

    def test_combined_stdout_stderr_overflow_is_refused(self):
        code = (
            "import os; os.write(1, b'x' * 40); "
            "os.write(2, b'y' * 25)")
        with mock.patch.object(
                self.sialib, "MAX_EXTERNAL_OUTPUT_BYTES", 64), \
                self.assertRaisesRegex(
                    OverflowError, "fixture output exceeded"):
            with tempfile.TemporaryDirectory() as cwd:
                self.sialib._run_bounded_text_process(
                    [sys.executable, "-c", code], env=dict(os.environ),
                    timeout=30, cwd=cwd, label="fixture")

    def test_invalid_utf8_is_refused_before_text_admission(self):
        with self.assertRaises(UnicodeDecodeError):
            self._run("import os; os.write(1, bytes([255]))")

    def test_timeout_kills_descendant_after_direct_parent_exits(self):
        with tempfile.TemporaryDirectory() as cwd:
            pid_file = os.path.join(cwd, "descendant.pid")
            parent = (
                "import pathlib,subprocess,sys; "
                "child=subprocess.Popen([sys.executable,'-c',"
                "'import time; time.sleep(60)']); "
                "pathlib.Path(sys.argv[1]).write_text(str(child.pid))")
            with self.assertRaises(subprocess.TimeoutExpired):
                self.sialib._run_bounded_text_process(
                    [sys.executable, "-c", parent, pid_file],
                    env=dict(os.environ), timeout=1, cwd=cwd)
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
            self.assertFalse(alive, "gbrain descendant survived group kill")

    def test_public_wrappers_share_the_bounded_runner(self):
        completed = subprocess.CompletedProcess(
            ["gbrain"], 0, stdout='{"ok":true}', stderr="")
        with mock.patch.object(
                self.sialib, "gbrain_owner",
                return_value=contextlib.nullcontext(9)), \
                mock.patch.object(
                    self.sialib, "_run_bounded_text_process",
                    return_value=completed) as bounded:
            result = self.sialib.gbrain(["query", "bounded"])
            called = self.sialib._gbrain_call_unlocked(
                "bounded-op", {"value": 1}, owner_fd=9)
        self.assertIs(result, completed)
        self.assertEqual(called, {"ok": True})
        self.assertEqual(bounded.call_count, 2)

    def test_git_corpus_helpers_use_bounded_output_and_preserve_tristate(self):
        with tempfile.TemporaryDirectory() as corpus:
            subprocess.run(["git", "init", "-q", corpus], check=True)
            page = os.path.join(corpus, "page.md")
            with open(page, "w", encoding="utf-8") as stream:
                stream.write("first\n")
            with mock.patch.object(self.sialib, "CORPUS", corpus):
                self.assertEqual(self.sialib.corpus_commit("fixture"),
                                 "committed")
                self.assertEqual(self.sialib.corpus_commit("fixture"),
                                 "clean")
                with open(page, "a", encoding="utf-8") as stream:
                    stream.write("second\n")
                self.assertTrue(self.sialib.corpus_dirty())
            with mock.patch.object(
                    self.sialib, "_run_bounded_text_process",
                    side_effect=OverflowError("git output refused")):
                self.assertEqual(self.sialib.corpus_commit("fixture"),
                                 "error")
                self.assertIsNone(self.sialib.corpus_dirty())

    def test_keeper_invalid_utf8_refuses_without_cursor_progress(self):
        with tempfile.TemporaryDirectory() as share:
            keeper = os.path.join(share, "sia-ledger")
            with open(keeper, "w", encoding="utf-8") as stream:
                stream.write(
                    "import os\nos.write(1, bytes([255]))\n")
            cursor = {"sia.lines": 0}
            with mock.patch.object(self.sialib, "SHARE", share), \
                    mock.patch.object(self.sialib, "BIN", share), \
                    self.assertRaisesRegex(
                        RuntimeError, "projection keeper is incomplete"):
                self.sialib.sense_sia(cursor)
            self.assertEqual(cursor, {"sia.lines": 0})

    def test_keeper_and_git_callers_fail_closed_on_bounded_runner_refusal(self):
        refusal = OverflowError("bounded fixture refusal")
        with mock.patch.object(
                self.sialib, "_run_bounded_text_process",
                side_effect=refusal) as bounded:
            with self.assertRaisesRegex(RuntimeError, "signed ledger refused"):
                self.sialib.ledger_append(
                    "TEST:bounded", "a", "b", required=True)
            with self.assertRaises(OverflowError):
                self.sialib.ledger_contains("TEST:bounded", "a", "b", "")
            with self.assertRaises(OverflowError):
                self.sialib.ledger_settle("TEST:bounded", "a", "b", "")
            self.assertEqual(self.sialib.ledger_head(), (0, ""))
        labels = [call.kwargs["label"] for call in bounded.call_args_list]
        self.assertEqual(labels, [
            "signed ledger append", "signed ledger presence",
            "signed ledger settlement", "signed ledger head",
        ])


class BuiltinSourceBounds(unittest.TestCase):
    def setUp(self):
        self.sialib = _load("sialib_source_bounds",
                            os.path.join(BIN, "sialib.py"))

    def test_directory_pages_resume_instead_of_repeating_a_prefix(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
                self.sialib, "MAX_SOURCE_SCAN_ENTRIES", 2):
            names = ["alpha", "bravo", "charlie", "delta"]
            for name in names:
                with open(os.path.join(directory, name), "w"):
                    pass
            page_state = None
            observed = []
            complete = False
            for _unused in names:
                page, complete, _inspected, page_state = \
                    self.sialib._bounded_source_entries(
                        directory, page_state)
                self.assertLessEqual(len(page),
                                     self.sialib.MAX_SOURCE_SCAN_ENTRIES)
                observed.extend(entry["name"] for entry in page)
                if complete:
                    break
            self.assertTrue(complete)
            self.assertEqual(set(observed), set(names))

    def test_snapshot_sources_refuse_linked_files_and_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            target_file = os.path.join(directory, "target.jsonl")
            target_directory = os.path.join(directory, "target-directory")
            with open(target_file, "w") as stream:
                stream.write("{}\n")
            os.makedirs(target_directory)
            linked_file = os.path.join(directory, "linked.jsonl")
            linked_directory = os.path.join(directory, "linked-directory")
            os.symlink(target_file, linked_file)
            os.symlink(target_directory, linked_directory)
            with self.assertRaises(OSError):
                self.sialib._stable_bounded_source_tail(linked_file)
            with self.assertRaises(OSError):
                self.sialib._bounded_source_entries(linked_directory)

    def test_jackal_uses_bounded_tail_and_skips_nonfinite_timestamps(self):
        with tempfile.TemporaryDirectory() as home:
            ledger = os.path.join(
                home, ".local", "state", "jackal", "results.jsonl")
            os.makedirs(os.path.dirname(ledger))
            long_status = "s" * 253
            old = json.dumps({"ts": 0, "tool": "old", "status": "exact"}) \
                + "\n"
            current = json.dumps(
                {"ts": 1, "tool": "bounded", "status": long_status}) + "\n"
            invalid = json.dumps(
                {"ts": float("nan"), "tool": "bad", "status": "exact"}) \
                + "\n"
            with open(ledger, "w") as stream:
                stream.write(old + current + invalid)
            bound = len(("\n" + current + invalid).encode("utf-8"))
            old_home = self.sialib.HOME
            self.sialib.HOME = home
            try:
                with mock.patch.object(
                        self.sialib, "MAX_SOURCE_TAIL_BYTES", bound), \
                        mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
                    cursors = {}
                    events = self.sialib.sense_jackal(cursors)
            finally:
                self.sialib.HOME = old_home
            self.assertTrue(any(event.kind == "source-truncated"
                                for event in events))
            admitted = [event for event in events
                        if event.summary.startswith("bounded")]
            self.assertEqual(len(admitted), 1)
            self.assertTrue(admitted[0].kind.startswith("jackal-status_h"))
            self.assertNotIn("jackal.ts", cursors)
            self.assertEqual(
                cursors["jackal.window"]["schema"],
                "sia-jackal-window-v1")

    def test_jackal_literal_unicode_separator_remains_one_json_record(self):
        with tempfile.TemporaryDirectory() as home:
            ledger = os.path.join(
                home, ".local", "state", "jackal", "results.jsonl")
            os.makedirs(os.path.dirname(ledger))
            row = {"ts": 1, "tool": "jack\u2028al", "status": "exact"}
            with open(ledger, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            old_home = self.sialib.HOME
            self.sialib.HOME = home
            try:
                with mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
                    cursors = {}
                    events = self.sialib.sense_jackal(cursors)
            finally:
                self.sialib.HOME = old_home
            admitted = [event for event in events
                        if event.organ == "jackal" and event.kind == "exact"]
            self.assertEqual(len(admitted), 1)
            self.assertEqual(len(cursors["jackal.window"]["seen"]), 1)

    def test_jackal_claimed_formal_rows_and_corrupt_receipts_are_unverified(self):
        with tempfile.TemporaryDirectory() as home:
            state = os.path.join(home, ".local", "state", "jackal")
            receipts = os.path.join(state, "receipts")
            os.makedirs(receipts)
            ledger = os.path.join(state, "results.jsonl")
            with open(ledger, "w", encoding="utf-8") as stream:
                stream.write(json.dumps({
                    "ts": 1, "tool": "fixture", "status": "checked",
                    "formal": True}) + "\n")
            with open(os.path.join(receipts, "corrupt.json"), "w",
                      encoding="utf-8") as stream:
                stream.write("{torn")
            old_home = self.sialib.HOME
            self.sialib.HOME = home
            cursors = {}
            try:
                with mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
                    first = self.sialib.sense_jackal(cursors)
                claimed = [event for event in first
                           if event.summary.startswith("fixture")]
                self.assertEqual(len(claimed), 1)
                self.assertIn("unverified-observation", claimed[0].tags)
                self.assertNotIn("formal-receipt", claimed[0].tags)

                with open(os.path.join(receipts, "arbitrary.json"), "w",
                          encoding="utf-8") as stream:
                    stream.write("not a receipt")
                observed = []
                for _attempt in range(4):
                    observed.extend(self.sialib.sense_jackal(cursors))
                    if any(event.kind == "receipt-observed"
                           for event in observed):
                        break
            finally:
                self.sialib.HOME = old_home
            receipt_events = [
                event for event in observed
                if event.kind == "receipt-observed"]
            self.assertTrue(receipt_events)
            self.assertTrue(all(
                event.tags == {"jackal", "unverified-observation"}
                for event in receipt_events))
            self.assertTrue(all("formal" not in event.summary.casefold()
                                for event in receipt_events))

    def test_jackal_window_identity_admits_same_and_lower_timestamp_rewrites(self):
        with tempfile.TemporaryDirectory() as home:
            ledger = os.path.join(
                home, ".local", "state", "jackal", "results.jsonl")
            os.makedirs(os.path.dirname(ledger))
            first = {"ts": 10, "tool": "first", "status": "exact"}
            same = {"ts": 10, "tool": "same", "status": "bounded"}
            lower = {"ts": 9, "tool": "lower", "status": "checked"}
            with open(ledger, "w") as stream:
                stream.write(json.dumps(first) + "\n")
            old_home = self.sialib.HOME
            self.sialib.HOME = home
            cursors = {}
            try:
                with mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
                    initial = self.sialib.sense_jackal(cursors)
                replacement = ledger + ".new"
                with open(replacement, "w") as stream:
                    for row in (first, same, lower):
                        stream.write(json.dumps(row) + "\n")
                os.replace(replacement, ledger)
                rewritten = self.sialib.sense_jackal(cursors)
                repeated = self.sialib.sense_jackal(cursors)
            finally:
                self.sialib.HOME = old_home
            self.assertEqual([event.summary.split(" ", 1)[0]
                              for event in initial], ["first"])
            self.assertEqual(
                {event.summary.split(" ", 1)[0] for event in rewritten},
                {"same", "lower"})
            self.assertEqual(repeated, [])

    def test_source_entity_tokens_do_not_collapse_lossy_slug_pairs(self):
        plus = self.sialib._source_entity_token("a+b", "project")
        hyphen = self.sialib._source_entity_token("a-b", "project")
        underscore = self.sialib._source_entity_token("a_b", "project")
        escaped = self.sialib._source_entity_token("a_2bb", "project")
        self.assertEqual(len({plus, hyphen, underscore, escaped}), 4)
        self.assertEqual(hyphen, "a-b")
        self.assertEqual(plus, "a_2bb")

    def test_versioned_source_state_does_not_reencode_canonical_tokens(self):
        cursors = {}
        state, truncated = self.sialib._bounded_source_state(
            cursors, "sessions", "session")
        self.assertFalse(truncated)
        token = self.sialib._source_entity_token("A", "session")
        state[token] = {"size": 1}
        again, truncated = self.sialib._bounded_source_state(
            cursors, "sessions", "session")
        self.assertFalse(truncated)
        self.assertEqual(again, {token: {"size": 1}})
        self.assertNotIn("_5f41", again)

    def test_source_entity_token_accepts_surrogateescaped_filenames(self):
        raw = os.fsdecode(b"session-\xff")
        token = self.sialib._source_entity_token(raw, "session")
        self.assertRegex(token, r"^[a-z0-9_][a-z0-9._-]*$")
        self.assertLessEqual(
            len(token.encode("utf-8")), self.sialib.MAX_CORPUS_LEAF_BYTES)

    def test_directory_cookie_resets_on_between_page_generation_change(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("alpha", "bravo"):
                with open(os.path.join(directory, name), "w"):
                    pass
            _page, complete, _inspected, state = \
                self.sialib._bounded_source_entries(
                    directory, None, limit=1)
            self.assertFalse(complete)
            with open(os.path.join(directory, "charlie"), "w"):
                pass
            _page, _complete, _inspected, restarted = \
                self.sialib._bounded_source_entries(
                    directory, state, limit=1)
            self.assertTrue(restarted["reset"])

    def test_source_tree_missing_frame_taints_cycle_and_reappearance_rebaselines(self):
        with tempfile.TemporaryDirectory() as root:
            gone = os.path.join(root, "gone")
            stay = os.path.join(root, "stay")
            os.makedirs(gone)
            os.makedirs(stay)
            with open(os.path.join(gone, "gone.jsonl"), "w"):
                pass
            with open(os.path.join(stay, "stay.jsonl"), "w"):
                pass
            key = "source.fixture.tree"
            cursors = {key: {
                "schema": self.sialib.SOURCE_TREE_SCHEMA,
                "generation": 7, "phase": "scan", "coverage": True,
                "queue": [
                    {"relative": "gone", "levels": 0, "page": {}},
                    {"relative": "stay", "levels": 0, "page": {}},
                ],
                "directories": [
                    {"relative": "", "generation":
                        self.sialib._source_tree_path_generation(root)},
                    {"relative": "gone", "generation":
                        self.sialib._source_tree_path_generation(gone)},
                ],
                "validation_cursor": 0,
            }}
            held = root + ".held"
            os.replace(gone, held)
            try:
                with mock.patch.object(
                        self.sialib, "MAX_SOURCE_SCAN_ENTRIES", 3):
                    _files, complete, refused, generation = \
                        self.sialib._bounded_source_tree_files(
                            root, cursors, key, 1, ".jsonl")
                    self.assertFalse(complete)
                    self.assertEqual(generation, 7)
                    self.assertIn("gone", refused)
                    self.assertFalse(cursors[key]["coverage"])

                    # Reappearance cannot erase the refusal carried by this
                    # generation. It is admitted by the following clean one.
                    os.replace(held, gone)
                    for _attempt in range(20):
                        if cursors[key]["generation"] != 7:
                            break
                        _files, complete, _refused, _generation = \
                            self.sialib._bounded_source_tree_files(
                                root, cursors, key, 1, ".jsonl")
                        self.assertFalse(complete)
                    self.assertNotEqual(cursors[key]["generation"], 7)
                    admitted = set()
                    complete = False
                    for _attempt in range(20):
                        files, complete, refused, generation = \
                            self.sialib._bounded_source_tree_files(
                                root, cursors, key, 1, ".jsonl")
                        self.assertEqual(refused, [])
                        admitted.update(os.path.basename(row["path"])
                                        for row in files)
                        if complete:
                            break
                    self.assertTrue(complete)
                self.assertEqual(generation, 8)
                self.assertEqual(admitted, {"gone.jsonl", "stay.jsonl"})
            finally:
                if os.path.exists(held):
                    os.replace(held, gone)

    def test_source_tree_revalidates_nested_frames_after_restore(self):
        with tempfile.TemporaryDirectory() as root:
            active = os.path.join(root, "active")
            restored = os.path.join(root, "restored")
            os.makedirs(active)
            os.makedirs(restored)
            with open(os.path.join(active, "active.jsonl"), "w"):
                pass
            with open(os.path.join(restored, "restored.jsonl"), "w"):
                pass
            key = "source.fixture.tree"
            cursors = {key: {
                "schema": self.sialib.SOURCE_TREE_SCHEMA,
                "generation": 11, "phase": "scan", "coverage": True,
                "queue": [{"relative": "active", "levels": 0,
                           "page": {}}],
                "directories": [
                    {"relative": "", "generation":
                        self.sialib._source_tree_path_generation(root)},
                    {"relative": "restored", "generation":
                        self.sialib._source_tree_path_generation(restored)},
                ],
                "validation_cursor": 0,
            }}
            held = root + ".nested-held"
            original = self.sialib._bounded_source_entries
            changed = []

            def disappear_during_active(directory, page=None, limit=None):
                if directory == active and not changed:
                    changed.append(True)
                    os.replace(restored, held)
                    try:
                        return original(directory, page, limit)
                    finally:
                        os.replace(held, restored)
                return original(directory, page, limit)

            with mock.patch.object(
                    self.sialib, "MAX_SOURCE_SCAN_ENTRIES", 4), \
                    mock.patch.object(
                        self.sialib, "_bounded_source_entries",
                        side_effect=disappear_during_active):
                _files, complete, refused, generation = \
                    self.sialib._bounded_source_tree_files(
                        root, cursors, key, 1, ".jsonl")
            self.assertTrue(changed)
            self.assertFalse(complete)
            self.assertEqual(generation, 11)
            self.assertIn(".", refused)

    def test_claude_restored_nested_frame_cannot_authorize_prune(self):
        with tempfile.TemporaryDirectory() as home:
            root = os.path.join(home, ".claude", "projects")
            active = os.path.join(root, "active")
            restored = os.path.join(root, "restored")
            os.makedirs(active)
            os.makedirs(restored)
            with open(os.path.join(active, "active.jsonl"), "w"):
                pass
            with open(os.path.join(restored, "restored.jsonl"), "w"):
                pass
            old_home = self.sialib.HOME
            self.sialib.HOME = home
            cursors = {}
            try:
                self.sialib.sense_claude(cursors)
                restored_id = self.sialib._source_entity_token(
                    "restored", "claude-session")
                generation = cursors["source.claude.tree"]["generation"]
                cursors["source.claude.tree"] = {
                    "schema": self.sialib.SOURCE_TREE_SCHEMA,
                    "generation": generation, "phase": "scan",
                    "coverage": True,
                    "queue": [{"relative": "active", "levels": 0,
                               "page": {}}],
                    "directories": [
                        {"relative": "", "generation":
                            self.sialib._source_tree_path_generation(root)},
                        {"relative": "restored", "generation":
                            self.sialib._source_tree_path_generation(
                                restored)},
                    ],
                    "validation_cursor": 0,
                }
                held = os.path.join(home, "restored-held")
                original = self.sialib._bounded_source_entries
                changed = []

                def disappear(directory, page=None, limit=None):
                    if directory == active and not changed:
                        changed.append(True)
                        os.replace(restored, held)
                        try:
                            return original(directory, page, limit)
                        finally:
                            os.replace(held, restored)
                    return original(directory, page, limit)

                with mock.patch.object(
                        self.sialib, "MAX_SOURCE_SCAN_ENTRIES", 4), \
                        mock.patch.object(
                            self.sialib, "_bounded_source_entries",
                            side_effect=disappear):
                    events = self.sialib.sense_claude(cursors)
                sessions = cursors["claude.sessions"][1]
                self.assertTrue(changed)
                self.assertIn(restored_id, sessions)
                self.assertTrue(any(event.kind == "source-entry-refused"
                                    for event in events))
            finally:
                self.sialib.HOME = old_home

    def test_codex_restored_nested_frame_cannot_authorize_prune(self):
        with tempfile.TemporaryDirectory() as home:
            root = os.path.join(home, ".codex", "sessions")
            active = os.path.join(root, "2026", "09", "30")
            restored = os.path.join(root, "2026", "08")
            os.makedirs(active)
            os.makedirs(os.path.join(restored, "30"))
            with open(os.path.join(active, "rollout-active.jsonl"), "w"):
                pass
            with open(os.path.join(
                    restored, "30", "rollout-restored.jsonl"), "w"):
                pass
            old_home = self.sialib.HOME
            self.sialib.HOME = home
            cursors = {}
            try:
                self.sialib.sense_codex(cursors)
                restored_id = self.sialib._source_entity_token(
                    "restored", "codex-session")
                generation = cursors["source.codex.tree"]["generation"]
                directory_relatives = ["", "2026", "2026/08",
                                        "2026/08/30", "2026/09"]
                cursors["source.codex.tree"] = {
                    "schema": self.sialib.SOURCE_TREE_SCHEMA,
                    "generation": generation, "phase": "scan",
                    "coverage": True,
                    "queue": [{"relative": "2026/09/30",
                               "levels": 0, "page": {}}],
                    "directories": [{
                        "relative": relative,
                        "generation": self.sialib
                            ._source_tree_path_generation(
                                os.path.join(root, relative))}
                        for relative in directory_relatives],
                    "validation_cursor": 0,
                }
                held = os.path.join(home, "codex-restored-held")
                original = self.sialib._bounded_source_entries
                changed = []

                def disappear(directory, page=None, limit=None):
                    if directory == active and not changed:
                        changed.append(True)
                        os.replace(restored, held)
                        try:
                            return original(directory, page, limit)
                        finally:
                            os.replace(held, restored)
                    return original(directory, page, limit)

                with mock.patch.object(
                        self.sialib, "MAX_SOURCE_SCAN_ENTRIES", 8), \
                        mock.patch.object(
                            self.sialib, "_bounded_source_entries",
                            side_effect=disappear):
                    events = self.sialib.sense_codex(cursors)
                sessions = cursors["codex.sessions"][1]
                self.assertTrue(changed)
                self.assertIn(restored_id, sessions)
                self.assertTrue(any(event.kind == "source-entry-refused"
                                    for event in events))
            finally:
                self.sialib.HOME = old_home

    def test_claude_nested_rename_never_false_prunes_and_reappears(self):
        with tempfile.TemporaryDirectory() as home:
            root = os.path.join(home, ".claude", "projects")
            project = os.path.join(root, "project")
            os.makedirs(project)
            with open(os.path.join(project, "existing.jsonl"), "w"):
                pass
            old_home = self.sialib.HOME
            self.sialib.HOME = home
            cursors = {}
            try:
                self.sialib.sense_claude(cursors)
                existing = self.sialib._source_entity_token(
                    "existing", "claude-session")
                sessions = cursors["claude.sessions"][1]
                self.assertIn(existing, sessions)
                generation = cursors["source.claude.tree"]["generation"]
                cursors["source.claude.tree"] = {
                    "schema": self.sialib.SOURCE_TREE_SCHEMA,
                    "generation": generation, "phase": "scan",
                    "coverage": True,
                    "queue": [{"relative": "project", "levels": 0,
                               "page": {}}],
                    "directories": [{
                        "relative": "", "generation":
                            self.sialib._source_tree_path_generation(root)}],
                    "validation_cursor": 0,
                }
                held = os.path.join(home, "project-held")
                os.replace(project, held)
                with mock.patch.object(
                        self.sialib, "MAX_SOURCE_SCAN_ENTRIES", 4):
                    refused = self.sialib.sense_claude(cursors)
                    self.assertTrue(any(event.kind == "source-entry-refused"
                                        for event in refused))
                    self.assertIn(existing, sessions)
                    os.replace(held, project)
                    with open(os.path.join(project, "new.jsonl"), "w"):
                        pass
                    target_generation = cursors[
                        "source.claude.tree"]["generation"]
                    for _attempt in range(20):
                        if cursors["source.claude.tree"]["generation"] \
                                != target_generation:
                            break
                        self.sialib.sense_claude(cursors)
                    self.assertNotEqual(
                        cursors["source.claude.tree"]["generation"],
                        target_generation)
                new = self.sialib._source_entity_token(
                    "new", "claude-session")
                sessions = cursors["claude.sessions"][1]
                self.assertIn(existing, sessions)
                self.assertIn(new, sessions)
            finally:
                self.sialib.HOME = old_home

    def test_codex_paginated_clean_generation_prunes_by_durable_marks(self):
        with tempfile.TemporaryDirectory() as home:
            root = os.path.join(
                home, ".codex", "sessions", "2026", "08", "30")
            os.makedirs(root)
            with open(os.path.join(root, "rollout-live.jsonl"), "w"):
                pass
            old_home = self.sialib.HOME
            self.sialib.HOME = home
            stale = self.sialib._source_entity_token(
                "stale", "codex-session")
            live = self.sialib._source_entity_token(
                "live", "codex-session")
            cursors = {"codex.sessions": [
                "sia-source-entity-state-v1",
                {stale: {"size": 0, "announced": False,
                         "generation": 0}}]}
            try:
                with mock.patch.object(
                        self.sialib, "MAX_SOURCE_SCAN_ENTRIES", 4):
                    for _attempt in range(20):
                        self.sialib.sense_codex(cursors)
                        if cursors["source.codex.tree"]["generation"]:
                            break
                    self.assertTrue(
                        cursors["source.codex.tree"]["generation"])
                sessions = cursors["codex.sessions"][1]
                self.assertIn(live, sessions)
                self.assertNotIn(stale, sessions)
            finally:
                self.sialib.HOME = old_home

    def test_overbound_line_progresses_by_bounded_chunks_then_signs_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "source.log")
            refused = b"x" * 11 + b"\n"
            with open(path, "wb") as stream:
                stream.write(refused + b"ok\n")
            cursors = {}
            pending = []
            with mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
                for _unused in range(10):
                    _generation, _ordinal, data = \
                        self.sialib._stable_tail_chunk(
                            path, cursors, "fixture.lines", 4)
                    self.assertEqual(data, b"")
                    pending = self.sialib._take_source_record_refusals(
                        cursors)
                    if pending:
                        break
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["bytes"], len(refused))
            self.assertEqual(
                pending[0]["end"] - pending[0]["start"], len(refused))
            with mock.patch.object(
                    self.sialib, "durable_ledger_append") as append:
                self.sialib._settle_source_record_refusals(
                    "sense_fixture", pending)
            self.assertEqual(
                append.call_args.args[:3],
                ("SOURCE:refuse", "sense_fixture", "over-bound-record"))
            _generation, _ordinal, data = self.sialib._stable_tail_chunk(
                path, cursors, "fixture.lines", 4)
            self.assertEqual(data, b"ok\n")

    def test_overlong_unit_and_package_fields_are_hashed_before_events(self):
        raw = "x" * 300
        with mock.patch.object(
                self.sialib, "_verified_builtin_attest_rows", return_value=[
                    ("1", "2026-08-30T00:00:00Z", "OUTCOME:restart",
                     raw, "ok", "digest", "0", "prev", "signature")]):
            sekhmet = self.sialib.sense_sekhmet({})
        with mock.patch.object(
                self.sialib, "tail_line_records", return_value=[(
                    0, 0,
                    f"[2026-08-30T00:00:00+00:00] [ALPM] installed "
                    f"{raw} 1.0")]):
            pacman = self.sialib.sense_pacman({})
        expected_unit = "units/" + self.sialib._source_entity_token(
            raw, "unit")
        expected_package = "packages/" + self.sialib._source_entity_token(
            raw, "package")
        self.assertIn(expected_unit, sekhmet[0].links)
        self.assertIn(expected_package, pacman[0].links)

    def test_long_repository_name_is_hashed_before_event_construction(self):
        with tempfile.TemporaryDirectory() as home:
            repo = "r" * 253
            head_log = os.path.join(
                home, "Projects", repo, ".git", "logs", "HEAD")
            os.makedirs(os.path.dirname(head_log))
            with open(head_log, "w") as stream:
                stream.write("metadata\tcommit: bounded repository\n")
            old_home = self.sialib.HOME
            self.sialib.HOME = home
            try:
                with mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
                    events = self.sialib.sense_git({})
            finally:
                self.sialib.HOME = old_home
            self.assertEqual(len(events), 1)
            project_links = [link for link in events[0].links
                             if link.startswith("projects/")]
            self.assertEqual(len(project_links), 1)
            leaf = project_links[0].split("/")[-1]
            self.assertTrue(leaf.startswith("project_h"))
            self.assertLessEqual(len(leaf.encode("utf-8")),
                                 self.sialib.MAX_CORPUS_LEAF_BYTES)

    def test_lossy_repository_names_have_independent_tail_cursors(self):
        with tempfile.TemporaryDirectory() as home:
            for repo in ("a+b", "a-b"):
                head_log = os.path.join(
                    home, "Projects", repo, ".git", "logs", "HEAD")
                os.makedirs(os.path.dirname(head_log))
                with open(head_log, "w") as stream:
                    stream.write(f"metadata\tcommit: {repo}\n")
            old_home = self.sialib.HOME
            self.sialib.HOME = home
            cursors = {}
            try:
                with mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
                    events = self.sialib.sense_git(cursors)
                repeated = self.sialib.sense_git(cursors)
            finally:
                self.sialib.HOME = old_home
            project_links = {
                link for event in events for link in event.links
                if link.startswith("projects/")}
            self.assertEqual(len(project_links), 2)
            self.assertIn("git.a-b", cursors)
            self.assertIn("git.a_2bb", cursors)
            self.assertEqual(repeated, [])

    def test_paginated_notifications_refuse_overflow_per_entry(self):
        with tempfile.TemporaryDirectory() as home:
            history = os.path.join(
                home, ".local/state/omarchy/notifications/history")
            os.makedirs(history)
            names = ["alpha.json", "bravo.json", "charlie.json",
                     "delta.json"]
            for name in names:
                with open(os.path.join(history, name), "w") as stream:
                    json.dump({"app": "fixture", "summary": name}, stream)
            old_home = self.sialib.HOME
            self.sialib.HOME = home
            cursors = {"notify.last": ""}
            events = []
            try:
                with mock.patch.object(
                        self.sialib, "MAX_SOURCE_SCAN_ENTRIES", 2):
                    for _unused in range(len(names) + 1):
                        events.extend(self.sialib.sense_notify(cursors))
                        page = cursors.get("source.notify.page", {})
                        if cursors.get("notify.paginated") \
                                and page.get("cookie") == 0 \
                                and not cursors.get("notify.pending"):
                            break
            finally:
                self.sialib.HOME = old_home
            self.assertTrue(any(event.kind == "notification"
                                for event in events))
            self.assertTrue(any(event.kind == "source-entry-refused"
                                for event in events))
            self.assertEqual(cursors["notify.last"], max(names))

    def test_builtin_snapshot_senses_do_not_use_listdir_or_glob(self):
        with tempfile.TemporaryDirectory() as home:
            guardian = os.path.join(
                home, ".local/state/omarchy-guardian/checkpoints")
            agents = os.path.join(
                home, ".local/state/omarchy/agents/usage")
            receipts = os.path.join(
                home, ".local/state/jackal/receipts")
            claude = os.path.join(home, ".claude/projects/demo")
            codex = os.path.join(home, ".codex/sessions/2026/08/30")
            notify = os.path.join(
                home, ".local/state/omarchy/notifications/history")
            git_log = os.path.join(
                home, "Projects/demo/.git/logs/HEAD")
            for directory in (guardian, agents, receipts, claude, codex,
                              notify, os.path.dirname(git_log)):
                os.makedirs(directory)
            with open(os.path.join(guardian, "checkpoint"), "w"):
                pass
            with open(os.path.join(receipts, "receipt.json"), "w"):
                pass
            with open(os.path.join(claude, "session.jsonl"), "w"):
                pass
            with open(os.path.join(codex, "rollout-session.jsonl"), "w"):
                pass
            with open(git_log, "w") as stream:
                stream.write("metadata\tcommit: fixture\n")
            with open(os.path.join(agents, "agent.json"), "w") as stream:
                json.dump({"id": "fixture", "todayTotalTokens": 0}, stream)
            with open(os.path.join(notify, "notice.json"), "w") as stream:
                json.dump({"app": "fixture"}, stream)
            old_home = self.sialib.HOME
            self.sialib.HOME = home
            try:
                with mock.patch.object(
                        self.sialib.os, "listdir",
                        side_effect=AssertionError("listdir is unbounded")), \
                        mock.patch.object(
                            self.sialib.glob, "glob",
                            side_effect=AssertionError("glob is unbounded")):
                    self.sialib.sense_jackal({})
                    self.sialib.sense_guardian({})
                    self.sialib.sense_git({})
                    self.sialib.sense_claude({})
                    self.sialib.sense_codex({})
                    self.sialib.sense_notify({})
                    self.sialib.sense_agents({})
            finally:
                self.sialib.HOME = old_home


class Redaction(unittest.TestCase):
    """Secret-shaped spans are dropped at the sense boundary; hex ledger
    digests are preserved (they are evidence)."""

    def setUp(self):
        self.sialib = _load("sialib_r", os.path.join(BIN, "sialib.py"))

    def test_secrets_redacted(self):
        for secret in ["sk-abcdef0123456789ABCDEF01",
                       "Bearer abcdef0123456789ABCDEFxyz",
                       "AKIAIOSFODNN7EXAMPLE",
                       "password=hunter2supersecret"]:
            out = self.sialib.redact(f"log line {secret} tail", "t")
            self.assertIn("redacted", out, secret)
            self.assertNotIn(secret.split("=")[-1][:8], out)

    def test_hex_digest_preserved(self):
        digest = "a" * 64
        out = self.sialib.redact(f"chain head {digest}", "t")
        self.assertIn(digest, out, "ledger digests must survive redaction")

    def test_terminal_and_bidi_controls_are_removed(self):
        hostile = "plain\x1b]52;c;payload\x07\x1b[31mred\u202eevil"
        out = self.sialib.redact(hostile, "t")
        for control in ("\x1b", "\x07", "\u202e"):
            self.assertNotIn(control, out)
        self.assertIn("plain", out)

    def test_event_boundary_makes_untrusted_graph_markup_inert(self):
        event = self.sialib.Event(
            "notify", self.sialib.utcnow(), "notification",
            "app [[events/forged]]\n## injected **Timeline**",
            {"organs/notify"})
        self.assertNotIn("[[events/forged]]", event.summary)
        self.assertNotIn("\n", event.summary)
        self.assertNotIn("**", event.summary)

    def test_event_boundary_neutralizes_html_and_markdown_links(self):
        event = self.sialib.Event(
            "notify", self.sialib.utcnow(), "notification",
            "![forged](https://example.invalid/x) "
            "<img src=x onerror=alert(1)>", {"organs/notify"})
        self.assertNotIn("![", event.summary)
        self.assertNotIn("<img", event.summary)
        self.assertNotIn("[forged](", event.summary)


class SignedSiaLedgerProjection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sialib = _load("sialib_sia_projection",
                            os.path.join(BIN, "sialib.py"))
        self.sialib.SHARE = self.temp.name
        # Exercise the keeper shipped by this checkout.  A developer machine
        # may already have SIA installed under ~/.local/share/sia/bin, while a
        # clean CI runner does not; leaving BIN at its import-time default
        # makes this fixture accidentally depend on that ambient installation.
        self.sialib.BIN = BIN
        self.keeper = os.path.join(BIN, "sia-ledger")
        subprocess.run([sys.executable, self.keeper, "init", self.temp.name],
                       check=True, capture_output=True, text=True)

    def tearDown(self):
        self.temp.cleanup()

    def _append(self, action, arg1, arg2):
        subprocess.run(
            [sys.executable, self.keeper, "append", self.temp.name,
             action, arg1, arg2, hashlib.sha256(b"").hexdigest(), "0"],
            check=True, capture_output=True, text=True)

    def test_projection_is_verified_answer_bearing_and_non_recursive(self):
        self._append("INSTALL:runtime", "sia-1.3.0", "prepared")
        self._append("PULSE:ingest", "pulse=1", "ok")
        self._append("DREAM:bench", "passed", "local")
        self._append("SOURCE:refuse", "journal", "event-capacity")
        self._append("BOOT:brainstem", "1.3.0", "pulse=60s")
        cursors = {"sia.lines": 0}
        events = self.sialib.sense_sia(cursors)
        self.assertEqual(len(events), 2)
        summaries = [event.summary for event in events]
        self.assertTrue(any("INSTALL:runtime sia-1.3.0 prepared" in value
                            for value in summaries))
        self.assertTrue(any("BOOT:brainstem 1.3.0 pulse=60s" in value
                            for value in summaries))
        self.assertFalse(any("PULSE:ingest" in value for value in summaries))
        self.assertFalse(any("DREAM:bench" in value for value in summaries))
        self.assertFalse(any("SOURCE:refuse" in value for value in summaries))
        self.assertEqual(self.sialib.sense_sia(cursors), [])

    def test_keeper_refusal_does_not_advance_projection_cursor(self):
        self._append("INSTALL:runtime", "sia-1.3.0", "prepared")
        ledger = os.path.join(self.temp.name, "ledger.tsv")
        with open(ledger, "r+b") as stream:
            stream.seek(-2, os.SEEK_END)
            byte = stream.read(1)
            stream.seek(-1, os.SEEK_CUR)
            stream.write(bytes([byte[0] ^ 1]))
        cursors = {"sia.lines": 0}
        with self.assertRaisesRegex(RuntimeError, "projection refused"):
            self.sialib.sense_sia(cursors)
        self.assertEqual(cursors, {"sia.lines": 0})

    def test_optional_chain_refuses_invalid_row_before_projection(self):
        ledger = os.path.join(self.temp.name, "optional.tsv")
        verifier = os.path.join(self.temp.name, "verify.py")
        with open(verifier, "w", encoding="utf-8") as stream:
            stream.write(
                "import pathlib,sys\n"
                "raw=pathlib.Path(sys.argv[1]).read_bytes()\n"
                "raise SystemExit(0 if raw.endswith(b'\\tvalid\\n') else 1)\n")
        with open(ledger, "w", encoding="utf-8") as stream:
            stream.write(
                "1\t2026-08-30T00:00:00Z\tOUTCOME:restart\tunit\tok\t"
                "digest\t0\tprev\tinvalid\n")
        binding = (ledger, verifier,
                   [sys.executable, verifier, ledger])
        cursors = {"sekhmet.lines": 0}
        with mock.patch.object(
                self.sialib, "_chain_cmds",
                return_value={"sekhmet": binding}):
            with self.assertRaisesRegex(RuntimeError, "projection refused"):
                self.sialib.sense_sekhmet(cursors)
        self.assertEqual(cursors, {"sekhmet.lines": 0})

    def test_mutation_after_keeper_success_cannot_project_or_advance(self):
        ledger = os.path.join(self.temp.name, "optional.tsv")
        verifier = os.path.join(self.temp.name, "verify.py")
        with open(verifier, "w", encoding="utf-8") as stream:
            stream.write("raise SystemExit(0)\n")
        valid = (
            "1\t2026-08-30T00:00:00Z\tOUTCOME:restart\tunit\tok\t"
            "digest\t0\tprev\tvalid\n")
        with open(ledger, "w", encoding="utf-8") as stream:
            stream.write(valid)
        binding = (ledger, verifier,
                   [sys.executable, verifier, ledger])
        cursors = {"sekhmet.lines": 0}

        def mutate_after_verify(*_args, **_kwargs):
            with open(ledger, "a", encoding="utf-8") as stream:
                stream.write(
                    "2\t2026-08-30T00:00:01Z\tOUTCOME:restart\tforged\t"
                    "ok\tdigest\t0\tprev\tinvalid\n")
            return subprocess.CompletedProcess([], 0, "", "")

        with mock.patch.object(
                self.sialib, "_chain_cmds",
                return_value={"sekhmet": binding}), \
                mock.patch.object(
                    self.sialib, "_run_bounded_text_process",
                    side_effect=mutate_after_verify):
            with self.assertRaisesRegex(RuntimeError, "changed after keeper"):
                self.sialib.sense_sekhmet(cursors)
        self.assertEqual(cursors, {"sekhmet.lines": 0})


class CorpusOriginLabels(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sialib = _load("sialib_corpus_origins",
                            os.path.join(BIN, "sialib.py"))
        self.sialib.CORPUS = self.temp.name

    def tearDown(self):
        self.temp.cleanup()

    def _page(self, slug, frontmatter):
        path = os.path.join(self.temp.name, slug + ".md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as stream:
            stream.write(f"---\n{frontmatter}\n---\nbody\n")

    def test_declared_origins_win_and_legacy_is_conservative(self):
        self._page("thoughts/model", "type: thought\norigin: model")
        self._page("thoughts/derived", "type: thought\norigin: derived")
        self._page("thoughts/legacy", "type: thought")
        self._page("events/day", "type: event-day")
        self._page("thoughts/invalid", "type: thought\norigin: user")
        self._page("events/missing-type", "title: missing")
        self._page("events/duplicate-type",
                   "type: event-day\ntype: thought\norigin: evidence")
        self.assertEqual(self.sialib.corpus_origin("thoughts/model"),
                         "model")
        self.assertEqual(self.sialib.corpus_origin("thoughts/derived"),
                         "derived")
        self.assertEqual(self.sialib.corpus_origin("thoughts/legacy"),
                         "legacy-unlabeled")
        self.assertEqual(self.sialib.corpus_origin("events/day"),
                         "evidence")
        self.assertEqual(self.sialib.corpus_origin("thoughts/invalid"),
                         "legacy-unlabeled")
        self.assertEqual(self.sialib.corpus_origin("events/missing-type",
                                                  "event-day"),
                         "legacy-unlabeled")
        self.assertEqual(self.sialib.corpus_origin("events/duplicate-type",
                                                  "event-day"),
                         "legacy-unlabeled")

    def test_legacy_jackal_pages_are_non_evidence_and_false_prose_is_inert(self):
        self._page(
            "events/jackal/2026-08-30",
            "type: event-day\norigin: evidence\ntags: [formal-receipt]")
        self._page(
            "events/jackal/2026-08-31",
            "type: event-day\norigin: derived\n"
            "tags: [unverified-observation]")
        self._page(
            "epochs/jackal/2026-w35",
            "type: epoch\norigin: evidence\ntags: [formal-receipt]")
        self._page(
            "thoughts/legacy-formal",
            "type: thought\norigin: derived")
        thought = os.path.join(
            self.temp.name, "thoughts", "legacy-formal.md")
        with open(thought, "a", encoding="utf-8") as stream:
            stream.write(
                "JACKAL retained a formal receipt today — Lean-checked "
                "mathematics entered my memory.\n")
        self.assertEqual(
            self.sialib.corpus_origin("events/jackal/2026-08-30"),
            "derived")
        self.assertEqual(self.sialib.siamind.origin_class(
            "events/jackal/2026-08-30", "event-day", "evidence"),
            "derived")
        self.assertEqual(
            self.sialib.corpus_origin("epochs/jackal/2026-w35"),
            "derived")
        for slug in ("events/jackal/2026-08-30",
                     "epochs/jackal/2026-w35",
                     "thoughts/legacy-formal"):
            rendered = self.sialib.neutralize_unverified_jackal_recall(
                slug, "apparently formal")
            self.assertEqual(
                rendered, self.sialib.UNVERIFIED_JACKAL_RECALL_NOTICE)
            self.assertNotIn("Lean-checked", rendered)
        self.assertEqual(
            self.sialib.neutralize_unverified_jackal_recall(
                "events/jackal/2026-08-31",
                "unverified result record observed"),
            "unverified result record observed")

    def test_linked_parent_cannot_supply_origin(self):
        outside = os.path.join(self.temp.name, "outside")
        os.makedirs(outside)
        with open(os.path.join(outside, "page.md"), "w") as stream:
            stream.write("---\ntype: thought\norigin: evidence\n---\n")
        os.symlink(outside, os.path.join(self.temp.name, "linked"))
        self.assertEqual(self.sialib.corpus_origin("linked/page"),
                         "legacy-unlabeled")


class EvidenceCursorHealth(unittest.TestCase):
    def setUp(self):
        self.sialib = _load("sialib_cursor_health",
                            os.path.join(BIN, "sialib.py"))
        self.journal_commands = []

    def _journal_process(self, producer, *, returncode=0,
                         cursor_bytes=b"next-cursor", metadata=None):
        real_popen = subprocess.Popen

        def launch(cmd, **kwargs):
            self.journal_commands.append(list(cmd))
            cursor_args = [
                arg for arg in cmd if arg.startswith("--cursor-file=")]
            cursor_path = (cursor_args[0].split("=", 1)[1]
                           if cursor_args else None)
            cursor_write = (
                "" if cursor_path is None or cursor_bytes is None else
                f"open({cursor_path!r}, 'wb').write({cursor_bytes!r})\n")
            selected = producer
            if "--output-fields=__CURSOR" in cmd:
                selected = (metadata if metadata is not None else
                            producer if cursor_bytes is None else
                            "os.write(1, b'{\"__CURSOR\":"
                            "\"next-cursor\"}\\n')")
            program = (
                "import os,sys,time\n"
                f"{cursor_write}"
                f"{selected}\n"
                f"sys.exit({returncode!r})\n")
            return real_popen([sys.executable, "-c", program], **kwargs)

        return mock.patch.object(
            self.sialib.subprocess, "Popen", side_effect=launch)

    def test_cursor_state_missing_bootstraps_but_damage_refuses(self):
        with tempfile.TemporaryDirectory() as state:
            old_path = self.sialib.CURSORS_PATH
            self.sialib.CURSORS_PATH = os.path.join(state, "cursors.json")
            try:
                self.assertEqual(self.sialib.load_cursors(), {})
                with open(self.sialib.CURSORS_PATH, "w") as stream:
                    stream.write("{broken")
                with self.assertRaisesRegex(RuntimeError, "malformed"):
                    self.sialib.load_cursors()
                os.unlink(self.sialib.CURSORS_PATH)
                target = os.path.join(state, "target.json")
                with open(target, "w") as stream:
                    stream.write("{}")
                os.symlink(target, self.sialib.CURSORS_PATH)
                with self.assertRaisesRegex(RuntimeError, "safely"):
                    self.sialib.load_cursors()
            finally:
                self.sialib.CURSORS_PATH = old_path

    def test_negative_line_and_byte_cursors_refuse_without_advancing(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as stream:
            stream.write("first\nsecond\nthird\n")
            path = stream.name
        try:
            for cursor, reader in (({"line": -1}, self.sialib.tail_lines),
                                   ({"byte": -1}, self.sialib.tail_bytes)):
                key = next(iter(cursor))
                with self.assertRaisesRegex(ValueError, "cursor"):
                    reader(path, cursor, key)
                self.assertEqual(cursor[key], -1)
        finally:
            os.unlink(path)

    def test_journal_failure_never_queues_cursor_rename(self):
        with tempfile.TemporaryDirectory() as state:
            cursor = os.path.join(state, "journal.cursor")
            old_pending = list(self.sialib.PENDING_CURSOR_RENAMES)
            self.sialib.PENDING_CURSOR_RENAMES.clear()
            try:
                with self._journal_process(
                        "os.write(2, b'denied')", returncode=1):
                    with self.assertRaisesRegex(RuntimeError, "refused"):
                        self.sialib._journalctl(["-n", "0"], cursor)
                self.assertEqual(self.sialib.PENDING_CURSOR_RENAMES, [])
                self.assertFalse(os.path.lexists(cursor + ".pulse"))
            finally:
                self.sialib.PENDING_CURSOR_RENAMES[:] = old_pending

    def test_journal_newline_free_overflow_binds_cursor_refusal(self):
        with tempfile.TemporaryDirectory() as state:
            cursor = os.path.join(state, "journal.cursor")
            with open(cursor, "wb") as stream:
                stream.write(b"old-cursor")
            with self._journal_process("os.write(1, b'x' * 32)"), \
                    mock.patch.object(
                        self.sialib, "MAX_JOURNAL_RECORD_BYTES", 16), \
                    mock.patch.object(
                        self.sialib, "MAX_JOURNAL_OUTPUT_BYTES", 16):
                records, pending, refusals = self.sialib._journalctl(
                    [], cursor)
            self.assertEqual(records, [])
            self.assertEqual(refusals[0]["reason"],
                             "journal-record-over-aggregate")
            self.assertFalse(refusals[0]["complete"])
            with open(cursor, "rb") as stream:
                self.assertEqual(stream.read(), b"old-cursor")
            with open(pending[0], "rb") as stream:
                self.assertEqual(stream.read(), b"next-cursor")
            os.unlink(pending[0])

    def test_journal_vacuum_cannot_rebind_oversized_later_row(self):
        with tempfile.TemporaryDirectory() as state:
            cursor = os.path.join(state, "journal.cursor")
            with open(cursor, "wb") as stream:
                stream.write(b"old-cursor")
            real_popen = subprocess.Popen

            def launch(cmd, **kwargs):
                cursor_args = [
                    arg for arg in cmd if arg.startswith("--cursor-file=")]
                cursor_write = ""
                if cursor_args:
                    cursor_path = cursor_args[0].split("=", 1)[1]
                    cursor_write = (
                        f"open({cursor_path!r}, 'wb').write(b'cursor-B')\n")
                if "--cursor=cursor-A" in cmd:
                    # A was vacuumed between the catalog and full pass; an
                    # exact query can no longer bind the poison row to A.
                    payload = b'{"__CURSOR":"cursor-B"}\n'
                elif "--output-fields=__CURSOR" in cmd:
                    payload = (
                        b'{"__CURSOR":"cursor-A"}\n'
                        b'{"__CURSOR":"cursor-B"}\n')
                else:
                    payload = (
                        b'{"MESSAGE":"' + b'x' * 64
                        + b'","__CURSOR":"cursor-B"}\n')
                program = (
                    "import os\n" + cursor_write
                    + f"os.write(1, {payload!r})\n")
                return real_popen(
                    [sys.executable, "-c", program], **kwargs)

            with mock.patch.object(
                    self.sialib.subprocess, "Popen", side_effect=launch), \
                    mock.patch.object(
                        self.sialib, "MAX_JOURNAL_RECORD_BYTES", 16), \
                    mock.patch.object(
                        self.sialib, "MAX_JOURNAL_OUTPUT_BYTES", 16):
                with self.assertRaisesRegex(
                        RuntimeError, "poison cursor changed"):
                    self.sialib._journalctl([], cursor)
            with open(cursor, "rb") as stream:
                self.assertEqual(stream.read(), b"old-cursor")
            self.assertFalse(os.path.lexists(cursor + ".pulse"))

    def test_journal_huge_complete_row_signably_advances_one_cursor(self):
        with tempfile.TemporaryDirectory() as state:
            cursor = os.path.join(state, "journal.cursor")
            with open(cursor, "wb") as stream:
                stream.write(b"old-cursor")
            producer = (
                "os.write(1, b'{\"MESSAGE\":\"' + b'x' * 32 + "
                "b'\",\"__CURSOR\":\"next-cursor\"}\\n')")
            with self._journal_process(producer), \
                    mock.patch.object(
                        self.sialib, "MAX_JOURNAL_RECORD_BYTES", 16), \
                    mock.patch.object(
                        self.sialib, "MAX_JOURNAL_OUTPUT_BYTES", 128):
                records, pending, refusals = self.sialib._journalctl(
                    [], cursor)
            self.assertEqual(records, [])
            self.assertEqual(refusals[0]["reason"],
                             "journal-record-over-bound")
            self.assertTrue(refusals[0]["complete"])
            with open(cursor, "rb") as stream:
                self.assertEqual(stream.read(), b"old-cursor")
            with open(pending[0], "rb") as stream:
                self.assertEqual(stream.read(), b"next-cursor")
            os.unlink(pending[0])

    def test_journal_poison_refusal_retries_then_signs_before_cursor(self):
        with tempfile.TemporaryDirectory() as state:
            old_state = self.sialib.STATE
            old_cursors_path = self.sialib.CURSORS_PATH
            old_pending = list(self.sialib.PENDING_CURSOR_RENAMES)
            self.sialib.STATE = state
            self.sialib.CURSORS_PATH = os.path.join(state, "cursors.json")
            self.sialib.PENDING_CURSOR_RENAMES.clear()
            for scope in ("sys", "user"):
                with open(os.path.join(state, f"journal-{scope}.cursor"),
                          "wb") as stream:
                    stream.write(b"old-cursor")
            producer = (
                "os.write(1, b'{\"MESSAGE\":\"' + b'x' * 32 + "
                "b'\",\"__CURSOR\":\"next-cursor\"}\\n')")
            try:
                first_trial = {}
                with self._journal_process(producer), mock.patch.object(
                        self.sialib, "MAX_JOURNAL_RECORD_BYTES", 16), \
                        mock.patch.object(
                            self.sialib, "MAX_JOURNAL_OUTPUT_BYTES", 128):
                    self.assertEqual(
                        self.sialib.sense_journal(first_trial), [])
                first = self.sialib._take_source_record_refusals(
                    first_trial)
                self.sialib._discard_pending_cursor_renames()
                for scope in ("sys", "user"):
                    with open(os.path.join(
                            state, f"journal-{scope}.cursor"), "rb") as stream:
                        self.assertEqual(stream.read(), b"old-cursor")

                retry_trial = {}
                with self._journal_process(producer), mock.patch.object(
                        self.sialib, "MAX_JOURNAL_RECORD_BYTES", 16), \
                        mock.patch.object(
                            self.sialib, "MAX_JOURNAL_OUTPUT_BYTES", 128):
                    self.sialib.sense_journal(retry_trial)
                retry = self.sialib._take_source_record_refusals(
                    retry_trial)
                self.assertEqual(first, retry)
                with mock.patch.object(
                        self.sialib, "durable_ledger_append") as append:
                    self.sialib._settle_source_record_refusals(
                        "sense_journal", retry)
                self.assertEqual(append.call_count, 2)
                rename_errors, save_error = \
                    self.sialib._commit_sense_cursors(retry_trial)
                self.assertEqual(rename_errors, [])
                self.assertIsNone(save_error)
                for scope in ("sys", "user"):
                    with open(os.path.join(
                            state, f"journal-{scope}.cursor"), "rb") as stream:
                        self.assertEqual(stream.read(), b"next-cursor")
            finally:
                self.sialib._discard_pending_cursor_renames()
                self.sialib.STATE = old_state
                self.sialib.CURSORS_PATH = old_cursors_path
                self.sialib.PENDING_CURSOR_RENAMES[:] = old_pending

    def test_journal_aggregate_budget_commits_only_valid_prefix(self):
        with tempfile.TemporaryDirectory() as state:
            cursor = os.path.join(state, "journal.cursor")
            with open(cursor, "wb") as stream:
                stream.write(b"old-cursor")
            rows = [(json.dumps({"MESSAGE": f"row-{index}",
                                 "__CURSOR": f"cursor-{index}"},
                                separators=(",", ":")) + "\n").encode()
                    for index in range(3)]
            metadata_rows = [(json.dumps(
                {"__CURSOR": f"cursor-{index}"}, separators=(",", ":"))
                              + "\n").encode() for index in range(3)]
            producer = f"os.write(1, {b''.join(rows)!r})"
            metadata = f"os.write(1, {b''.join(metadata_rows)!r})"
            budget = sum(len(row) for row in rows[:2])
            with self._journal_process(producer, metadata=metadata), \
                    mock.patch.object(
                        self.sialib, "MAX_JOURNAL_RECORD_BYTES", 128), \
                    mock.patch.object(
                        self.sialib, "MAX_JOURNAL_OUTPUT_BYTES", budget):
                records, pending, refusals = self.sialib._journalctl(
                    [], cursor)
            self.assertEqual([row["MESSAGE"] for row in records],
                             ["row-0", "row-1"])
            self.assertEqual(refusals, [])
            with open(cursor, "rb") as stream:
                self.assertEqual(stream.read(), b"old-cursor")
            with open(pending[0], "rb") as stream:
                self.assertEqual(stream.read(), b"cursor-1")
            os.unlink(pending[0])

    def test_journal_unterminated_valid_json_never_advances_cursor(self):
        with tempfile.TemporaryDirectory() as state:
            cursor = os.path.join(state, "journal.cursor")
            with open(cursor, "wb") as stream:
                stream.write(b"old-cursor")
            with self._journal_process("os.write(1, b'{}')"):
                with self.assertRaisesRegex(RuntimeError, "unterminated"):
                    self.sialib._journalctl([], cursor)
            with open(cursor, "rb") as stream:
                self.assertEqual(stream.read(), b"old-cursor")
            self.assertFalse(os.path.lexists(cursor + ".pulse"))

    def test_journal_success_returns_only_complete_records_and_temp_cursor(self):
        with tempfile.TemporaryDirectory() as state:
            cursor = os.path.join(state, "journal.cursor")
            with open(cursor, "wb") as stream:
                stream.write(b"old-cursor")
            producer = (
                "os.write(1, b'{\"MESSAGE\":\"ok\","
                "\"__CURSOR\":\"next-cursor\"}\\n')")
            with self._journal_process(producer):
                records, pending, refusals = self.sialib._journalctl(
                    [], cursor)
            self.assertEqual(records, [{
                "MESSAGE": "ok", "__CURSOR": "next-cursor"}])
            self.assertEqual(refusals, [])
            self.assertEqual(pending, (cursor + ".pulse", cursor))
            with open(cursor, "rb") as stream:
                self.assertEqual(stream.read(), b"old-cursor")
            with open(cursor + ".pulse", "rb") as stream:
                self.assertEqual(stream.read(), b"next-cursor")

    def test_journal_timeout_kills_process_and_retains_cursor(self):
        with tempfile.TemporaryDirectory() as state:
            cursor = os.path.join(state, "journal.cursor")
            with open(cursor, "wb") as stream:
                stream.write(b"old-cursor")
            with self._journal_process("time.sleep(2)"), \
                    mock.patch.object(
                        self.sialib, "JOURNAL_TIMEOUT_SECONDS", 0.05):
                with self.assertRaisesRegex(RuntimeError, "timed out"):
                    self.sialib._journalctl([], cursor)
            with open(cursor, "rb") as stream:
                self.assertEqual(stream.read(), b"old-cursor")
            self.assertFalse(os.path.lexists(cursor + ".pulse"))

    def test_journal_timeout_kills_descendant_after_parent_exit(self):
        with tempfile.TemporaryDirectory() as state:
            cursor = os.path.join(state, "journal.cursor")
            pid_file = os.path.join(state, "descendant.pid")
            with open(cursor, "wb") as stream:
                stream.write(b"old-cursor")
            producer = (
                "import subprocess; "
                "child=subprocess.Popen([sys.executable,'-c',"
                "'import time; time.sleep(60)']); "
                f"open({pid_file!r},'w').write(str(child.pid)); "
                "sys.exit(0)")
            with self._journal_process(producer), \
                    mock.patch.object(
                        self.sialib, "JOURNAL_TIMEOUT_SECONDS", 0.05):
                with self.assertRaisesRegex(RuntimeError, "timed out"):
                    self.sialib._journalctl([], cursor)
            with open(cursor, "rb") as stream:
                self.assertEqual(stream.read(), b"old-cursor")
            self.assertFalse(os.path.lexists(cursor + ".pulse"))
            with open(pid_file, encoding="utf-8") as stream:
                child_pid = int(stream.read())
            deadline = time.monotonic() + 2
            alive = True
            while time.monotonic() < deadline:
                try:
                    with open(f"/proc/{child_pid}/stat",
                              encoding="utf-8") as stream:
                        status = stream.read().split()[2]
                except FileNotFoundError:
                    alive = False
                    break
                if status == "Z":
                    alive = False
                    break
                time.sleep(0.01)
            self.assertFalse(alive, "journal descendant survived group kill")

    def test_journal_seed_cursor_is_bounded_and_no_follow(self):
        with tempfile.TemporaryDirectory() as state:
            cursor = os.path.join(state, "journal.cursor")
            with open(cursor, "wb") as stream:
                stream.write(b"oversized")
            with mock.patch.object(
                    self.sialib, "MAX_JOURNAL_CURSOR_BYTES", 4), \
                    mock.patch.object(self.sialib.subprocess, "Popen") \
                    as launch:
                with self.assertRaisesRegex(RuntimeError, "bounded"):
                    self.sialib._journalctl([], cursor)
                launch.assert_not_called()
            os.unlink(cursor)
            target = os.path.join(state, "target")
            with open(target, "wb") as stream:
                stream.write(b"cursor")
            os.symlink(target, cursor)
            with mock.patch.object(self.sialib.subprocess, "Popen") as launch:
                with self.assertRaises(OSError):
                    self.sialib._journalctl([], cursor)
                launch.assert_not_called()
            self.assertFalse(os.path.lexists(cursor + ".pulse"))

    def test_fresh_nonempty_journal_discards_newest_baseline_row(self):
        with tempfile.TemporaryDirectory() as state:
            old_state = self.sialib.STATE
            old_pending = list(self.sialib.PENDING_CURSOR_RENAMES)
            self.sialib.STATE = state
            self.sialib.PENDING_CURSOR_RENAMES.clear()
            producer = (
                "os.write(1, b'{\"MESSAGE\":\"historical\","
                "\"__CURSOR\":\"baseline\"}\\n')")
            try:
                with self._journal_process(producer):
                    events = self.sialib.sense_journal({})
                self.assertEqual(events, [])
                self.assertEqual(len(self.sialib.PENDING_CURSOR_RENAMES), 2)
                for command in self.journal_commands:
                    self.assertIn("1", command)
                    self.assertNotIn("+300", command)
                for tmp, real in self.sialib.PENDING_CURSOR_RENAMES:
                    self.assertFalse(os.path.lexists(real))
                    with open(tmp, "rb") as stream:
                        self.assertEqual(stream.read(), b"next-cursor")
            finally:
                self.sialib._discard_pending_cursor_renames()
                self.sialib.STATE = old_state
                self.sialib.PENDING_CURSOR_RENAMES[:] = old_pending

    def test_fresh_empty_journal_persists_empty_cursor_then_reads_future(self):
        with tempfile.TemporaryDirectory() as state:
            old_state = self.sialib.STATE
            old_cursors_path = self.sialib.CURSORS_PATH
            old_pending = list(self.sialib.PENDING_CURSOR_RENAMES)
            self.sialib.STATE = state
            self.sialib.CURSORS_PATH = os.path.join(state, "cursors.json")
            self.sialib.PENDING_CURSOR_RENAMES.clear()
            try:
                with self._journal_process("pass", cursor_bytes=None):
                    self.assertEqual(self.sialib.sense_journal({}), [])
                rename_errors, save_error = \
                    self.sialib._commit_sense_cursors({})
                self.assertEqual(rename_errors, [])
                self.assertIsNone(save_error)
                for scope in ("sys", "user"):
                    real = os.path.join(
                        state, f"journal-{scope}.cursor")
                    with open(real, "rb") as stream:
                        self.assertEqual(stream.read(), b"")

                self.journal_commands.clear()
                producer = (
                    "os.write(1, b'{\"MESSAGE\":\"future\","
                    "\"__CURSOR\":\"next-cursor\"}\\n')")
                with self._journal_process(producer):
                    events = self.sialib.sense_journal({})
                self.assertEqual(len(events), 2)
                self.assertTrue(all("future" in event.summary
                                    for event in events))
                self.assertTrue(all("+300" in command
                                    for command in self.journal_commands))
            finally:
                self.sialib._discard_pending_cursor_renames()
                self.sialib.STATE = old_state
                self.sialib.CURSORS_PATH = old_cursors_path
                self.sialib.PENDING_CURSOR_RENAMES[:] = old_pending

    def test_journal_backlog_requests_oldest_pending_batch(self):
        with tempfile.TemporaryDirectory() as state:
            old_state = self.sialib.STATE
            old_pending = list(self.sialib.PENDING_CURSOR_RENAMES)
            self.sialib.STATE = state
            self.sialib.PENDING_CURSOR_RENAMES.clear()
            for scope in ("sys", "user"):
                with open(os.path.join(state, f"journal-{scope}.cursor"),
                          "w") as stream:
                    stream.write("cursor")
            calls = []

            def capture(args, cursor_file, **_kwargs):
                calls.append(list(args))
                return [], (cursor_file + ".pulse", cursor_file), []

            try:
                with mock.patch.object(self.sialib, "_journalctl",
                                       side_effect=capture):
                    self.sialib.sense_journal({})
                self.assertTrue(calls)
                for args in calls:
                    self.assertIn("+300", args)
                    self.assertNotIn("300", args)
            finally:
                self.sialib.STATE = old_state
                self.sialib.PENDING_CURSOR_RENAMES[:] = old_pending

    def test_custom_jsonl_bad_row_is_bound_and_later_row_is_reachable(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as stream:
            stream.write("[]\n{bad json\n{\"message\":\"later\"}\n")
            path = stream.name
        old_config = self.sialib.CONFIG
        cursors = {"custom.fixture": 0}
        self.sialib.CONFIG = {"custom_senses": [{
            "name": "fixture", "path": path, "type": "jsonl",
            "field": "message", "kind": "event", "tags": []}]}
        try:
            events, errors = self.sialib.sense_custom(cursors)
            self.assertEqual(events, [])
            self.assertEqual(errors, [])
            first = self.sialib._take_source_record_refusals(cursors)
            self.assertEqual(first[0]["reason"],
                             "non-object-json-record")
            self.assertEqual(first[0]["ordinal"], 0)
            events, errors = self.sialib.sense_custom(cursors)
            self.assertEqual((events, errors), ([], []))
            second = self.sialib._take_source_record_refusals(cursors)
            self.assertEqual(second[0]["reason"],
                             "malformed-json-record")
            self.assertEqual(second[0]["ordinal"], 1)
            events, errors = self.sialib.sense_custom(cursors)
            self.assertEqual(errors, [])
            self.assertEqual([event.summary for event in events], ["later"])
            self.assertEqual(cursors["custom.fixture"], 3)
        finally:
            self.sialib.CONFIG = old_config
            os.unlink(path)

    def test_custom_jsonl_missing_field_refuses_without_exposing_other_fields(self):
        secret = "unrelated-private-value-must-never-render"
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as stream:
            stream.write(json.dumps({"detail": secret}) + "\n")
            stream.write(json.dumps({"message": "reachable"}) + "\n")
            stream.write(json.dumps({"message": "reachable"}) + "\n")
            path = stream.name
        old_config = self.sialib.CONFIG
        cursors = {"custom.fixture": 0}
        self.sialib.CONFIG = {"custom_senses": [{
            "name": "fixture", "path": path, "type": "jsonl",
            "field": "message", "kind": "event", "tags": []}]}
        try:
            events, errors = self.sialib.sense_custom(cursors)
            self.assertEqual((events, errors), ([], []))
            first = self.sialib._take_source_record_refusals(cursors)
            self.assertEqual(len(first), 1)
            self.assertEqual(first[0]["reason"], "missing-json-field")
            self.assertEqual(first[0]["ordinal"], 0)
            self.assertNotIn(secret, json.dumps(first, sort_keys=True))
            self.assertEqual(cursors["custom.fixture"], 1)
            with mock.patch.object(
                    self.sialib, "durable_ledger_append") as append:
                self.sialib._settle_source_record_refusals(
                    "sense_custom:fixture", first)
            self.assertEqual(
                append.call_args.args[:3],
                ("SOURCE:refuse", "sense_custom:fixture",
                 "missing-json-field"))
            self.assertNotIn(secret, append.call_args.args[3])

            events, errors = self.sialib.sense_custom(cursors)
            self.assertEqual(errors, [])
            self.assertEqual([event.summary for event in events],
                             ["reachable", "reachable"])
            self.assertNotEqual(events[0].occurrence, events[1].occurrence)
            self.assertNotIn(secret, "".join(
                event.summary for event in events))
            self.assertEqual(cursors["custom.fixture"], 3)
            self.assertEqual(
                self.sialib._take_source_record_refusals(cursors), [])
        finally:
            self.sialib.CONFIG = old_config
            os.unlink(path)

    def test_custom_invalid_utf8_refusal_retries_exactly_until_signed(self):
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as stream:
            stream.write(b"\xff\n{\"message\":\"reachable\"}\n")
            path = stream.name
        old_config = self.sialib.CONFIG
        self.sialib.CONFIG = {"custom_senses": [{
            "name": "fixture", "path": path, "type": "jsonl",
            "field": "message", "kind": "event", "tags": []}]}
        base = {"custom.fixture": 0}
        try:
            first_trial = copy.deepcopy(base)
            first_events, first_errors = self.sialib.sense_custom(
                first_trial)
            first = self.sialib._take_source_record_refusals(first_trial)
            retry_trial = copy.deepcopy(base)
            self.sialib.sense_custom(retry_trial)
            retry = self.sialib._take_source_record_refusals(retry_trial)
            self.assertEqual((first_events, first_errors), ([], []))
            self.assertEqual(first, retry)
            self.assertEqual(first[0]["reason"], "invalid-utf8-record")
            with mock.patch.object(
                    self.sialib, "durable_ledger_append") as append:
                self.sialib._settle_source_record_refusals(
                    "sense_custom:fixture", first)
            self.assertEqual(
                append.call_args.args[:3],
                ("SOURCE:refuse", "sense_custom:fixture",
                 "invalid-utf8-record"))
            events, errors = self.sialib.sense_custom(first_trial)
            self.assertEqual(errors, [])
            self.assertEqual([event.summary for event in events],
                             ["reachable"])
        finally:
            self.sialib.CONFIG = old_config
            os.unlink(path)

    def test_custom_json_parser_limits_refuse_per_physical_row(self):
        deep = ('{"message":' + ('[' * 100000) + '0'
                + (']' * 100000) + '}')
        huge_integer = '{"message":' + ('9' * 5000) + '}'
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as stream:
            stream.write(deep + "\n" + huge_integer
                         + '\n{"message":"reachable"}\n')
            path = stream.name
        old_config = self.sialib.CONFIG
        cursors = {"custom.fixture": 0}
        self.sialib.CONFIG = {"custom_senses": [{
            "name": "fixture", "path": path, "type": "jsonl",
            "field": "message", "kind": "event", "tags": []}]}
        try:
            for ordinal in range(2):
                events, errors = self.sialib.sense_custom(cursors)
                self.assertEqual((events, errors), ([], []))
                refusal = self.sialib._take_source_record_refusals(cursors)
                self.assertEqual(refusal[0]["reason"],
                                 "malformed-json-record")
                self.assertEqual(refusal[0]["ordinal"], ordinal)
            events, errors = self.sialib.sense_custom(cursors)
            self.assertEqual(errors, [])
            self.assertEqual([event.summary for event in events],
                             ["reachable"])
        finally:
            self.sialib.CONFIG = old_config
            os.unlink(path)

    def test_custom_match_refuses_regex_and_literal_alternatives_progress(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as stream:
            stream.write(("a" * 100000) + "!\nERROR reachable\n")
            path = stream.name
        old_config = self.sialib.CONFIG
        cursors = {"custom.fixture": 0}
        try:
            self.sialib.CONFIG = {"custom_senses": [{
                "name": "fixture", "path": path,
                "match": "(a+)+$"}]}
            with mock.patch.object(
                    self.sialib.re, "compile",
                    side_effect=AssertionError("custom regex executed")):
                events, errors = self.sialib.sense_custom(cursors)
            self.assertEqual(events, [])
            self.assertIn("literal alternatives only", errors[0]["error"])
            self.assertEqual(cursors, {"custom.fixture": 0})

            self.sialib.CONFIG = {"custom_senses": [{
                "name": "fixture", "path": path,
                "match": "ERROR|FATAL"}]}
            events, errors = self.sialib.sense_custom(cursors)
            self.assertEqual(errors, [])
            self.assertEqual([event.summary for event in events],
                             ["ERROR reachable"])
        finally:
            self.sialib.CONFIG = old_config
            os.unlink(path)

    def test_custom_exclude_is_literal_bounded_and_preserves_cursor_safety(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as stream:
            stream.write("completed\nFAILED integrity\n")
            path = stream.name
        old_config = self.sialib.CONFIG
        cursors = {"custom.fixture": 0}
        try:
            self.sialib.CONFIG = {"custom_senses": [{
                "name": "fixture", "path": path,
                "exclude": "FAILED|FATAL"}]}
            events, errors = self.sialib.sense_custom(cursors)
            self.assertEqual(errors, [])
            self.assertEqual([event.summary for event in events],
                             ["completed"])

            cursors = {"custom.fixture": 0}
            self.sialib.CONFIG = {"custom_senses": [{
                "name": "fixture", "path": path,
                "exclude": "^(?!.*FAILED)"}]}
            with mock.patch.object(
                    self.sialib.re, "compile",
                    side_effect=AssertionError("custom regex executed")):
                events, errors = self.sialib.sense_custom(cursors)
            self.assertEqual(events, [])
            self.assertIn("literal alternatives only", errors[0]["error"])
            self.assertEqual(cursors, {"custom.fixture": 0})
        finally:
            self.sialib.CONFIG = old_config
            os.unlink(path)

    def test_config_parser_and_shapes_degrade_without_import_crash(self):
        old_errors = copy.deepcopy(self.sialib.CONFIG_ERRORS)
        with tempfile.TemporaryDirectory() as root:
            config_path = os.path.join(root, "config.json")
            old_path = self.sialib.CONFIG_PATH
            self.sialib.CONFIG_PATH = config_path
            try:
                for raw, expected in (
                        ('{"n":' + ("9" * 5000) + "}",
                         "config-invalid-json"),
                        ("[]", "config-must-be-object")):
                    with open(config_path, "w", encoding="utf-8") as stream:
                        stream.write(raw)
                    self.assertEqual(self.sialib.load_config(), {})
                    self.assertEqual(
                        self.sialib.CONFIG_ERRORS[0]["error"],
                        expected)
                with open(config_path, "w", encoding="utf-8") as stream:
                    stream.write("{}")
                with mock.patch.object(
                        self.sialib.json, "loads",
                        side_effect=RecursionError("parser depth")):
                    self.assertEqual(self.sialib.load_config(), {})
                self.assertEqual(
                    self.sialib.CONFIG_ERRORS[0]["error"],
                    "config-invalid-json")
            finally:
                self.sialib.CONFIG_PATH = old_path

        old_config = self.sialib.CONFIG
        try:
            self.sialib.CONFIG_ERRORS.clear()
            malformed = {
                "senses": ["not-an-object"],
                "custom_senses": [
                    "not-an-object",
                    {"name": ["not-a-string"], "path": "/tmp/source"},
                    {"name": "bad-description", "path": "/tmp/source",
                     "description": {"not": "text"}},
                ],
            }
            self.sialib.CONFIG = malformed
            organs = self.sialib._build_organs()
            self.assertTrue(all(
                organs.get(name) == value
                for name, value in self.sialib.BASE_ORGANS.items()))
            self.assertNotIn("bad-description", organs)
            events, errors, successful = self.sialib.sense_custom(
                {}, include_sources=True)
            self.assertEqual(events, [])
            self.assertEqual(successful, [])
            self.assertEqual(len(errors), len(malformed["custom_senses"]))
        finally:
            self.sialib.CONFIG = old_config
            self.sialib.CONFIG_ERRORS[:] = old_errors

    def test_custom_json_surrogate_is_refused_and_next_row_progresses(self):
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", delete=False) as stream:
            stream.write('{"message":"\\ud800"}\n')
            stream.write('{"message":"reachable"}\n')
            path = stream.name
        old_config = self.sialib.CONFIG
        old_errors = copy.deepcopy(self.sialib.CONFIG_ERRORS)
        cursors = {"custom.fixture": 0}
        try:
            self.sialib.CONFIG_ERRORS.clear()
            self.sialib.CONFIG = {"custom_senses": [{
                "name": "fixture", "path": path, "type": "jsonl",
                "field": "message"}]}
            events, errors = self.sialib.sense_custom(cursors)
            self.assertEqual((events, errors), ([], []))
            refusal = self.sialib._take_source_record_refusals(cursors)
            self.assertEqual(refusal[0]["reason"],
                             "invalid-utf8-json-field")
            events, errors = self.sialib.sense_custom(cursors)
            self.assertEqual(errors, [])
            self.assertEqual([event.summary for event in events],
                             ["reachable"])
        finally:
            self.sialib.CONFIG = old_config
            self.sialib.CONFIG_ERRORS[:] = old_errors
            os.unlink(path)

    def test_best_effort_json_parser_limits_return_default(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as stream:
            path = stream.name
        try:
            with open(path, "w", encoding="utf-8") as stream:
                stream.write('{"n":' + ("9" * 5000) + "}")
            self.assertEqual(
                self.sialib.read_json(path, {"safe": True}),
                {"safe": True})
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("{}")
            with mock.patch.object(
                    self.sialib.json, "loads",
                    side_effect=RecursionError("parser depth")):
                self.assertEqual(
                    self.sialib.read_json(path, {"safe": True}),
                    {"safe": True})
        finally:
            os.unlink(path)

    def test_authoritative_json_parser_limits_are_named_and_source_free(self):
        with tempfile.TemporaryDirectory() as root:
            corpus = os.path.join(root, "corpus")
            os.makedirs(corpus)
            state_path = os.path.join(root, "state.json")
            inbox_path = os.path.join(root, "inbox.json")
            source_path = os.path.join(root, "source.json")
            memo_path = os.path.join(root, "memo.json")
            recovery_path = os.path.join(root, "recovery.json")
            legacy_path = os.path.join(root, "legacy.json")
            pending_path = os.path.join(root, "pending.json")
            for path, payload in (
                    (state_path, "{}"), (inbox_path, "[]"),
                    (source_path, "{}"), (memo_path, "{}"),
                    (recovery_path, "{}"), (legacy_path, "{}"),
                    (pending_path, "{}")):
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write(payload)
                os.chmod(path, 0o600)
            claim_path = os.path.join(
                root, self.sialib.THOUGHT_RECOVERY_CLAIM_NAME)
            with open(claim_path, "w", encoding="utf-8") as stream:
                stream.write("{}")
            os.chmod(claim_path, 0o600)
            event_id = "a" * 64
            event_path = os.path.join(
                corpus,
                self.sialib._event_index_relative("fixture", event_id))
            os.makedirs(os.path.dirname(event_path))
            with open(event_path, "w", encoding="utf-8") as stream:
                stream.write("{}")

            with mock.patch.object(self.sialib, "CORPUS", corpus), \
                    mock.patch.object(self.sialib, "STATE", root), \
                    mock.patch.object(self.sialib, "MEMO_PATH", memo_path):
                cases = (
                    (lambda: self.sialib.read_state_json(
                        state_path, {}, "cursor"), RuntimeError,
                     "cursor state is unreadable or malformed"),
                    (lambda: self.sialib._read_thought_inbox(inbox_path),
                     ValueError, "thought inbox is malformed"),
                    (lambda: self.sialib._read_bounded_source_json(
                        source_path, "fixture source"), ValueError,
                     "fixture source is malformed"),
                    (self.sialib.load_memo, RuntimeError,
                     "brainstem memo is unreadable or malformed"),
                    (lambda: self.sialib._read_event_index_entry(
                        "fixture", event_id), ValueError,
                     "consolidated event index entry is malformed"),
                    (lambda: self.sialib._read_thought_recovery_record(
                        recovery_path), ValueError,
                     "thought recovery record is malformed"),
                    (self.sialib._read_thought_recovery_claim, ValueError,
                     "thought recovery claim is malformed"),
                    (lambda: self.sialib._read_thought_legacy_index_entry(
                        legacy_path), ValueError,
                     "legacy thought index is malformed"),
                    (lambda: self.sialib._read_pending_record(pending_path),
                     ValueError, "ledger recovery record is malformed"),
                    (lambda: self.sialib._decode_exact_thought_page(
                        "thoughts/fixture", "sia_thought: {}\n"),
                     RuntimeError,
                     "thought recovery metadata is malformed"),
                    (lambda: self.sialib._parse_sia_counts(
                        "{}", "event page"), ValueError,
                     "event page sia_counts is malformed"),
                    (lambda: self.sialib._epoch_json_field(
                        "sia_sources: []", "sia_sources", "epoch page", []),
                     RuntimeError, "epoch page sia_sources is malformed"),
                    (lambda: self.sialib._yaml_scalar('"fixture"'),
                     ValueError, "quoted scalar is malformed"),
                )
                for parser_error in (ValueError, RecursionError):
                    for call, error_type, expected in cases:
                        with self.subTest(parser_error=parser_error.__name__,
                                          expected=expected), \
                                mock.patch.object(
                                    self.sialib.json, "loads",
                                    side_effect=parser_error(
                                        "private source content")), \
                                self.assertRaises(error_type) as raised:
                            call()
                        self.assertEqual(str(raised.exception), expected)

    def test_best_effort_parser_limits_skip_rows_and_expose_truncation(self):
        for parser_error in (ValueError, RecursionError):
            with self.subTest(parser_error=parser_error.__name__), \
                    mock.patch.object(
                        self.sialib, "_stable_bounded_source_tail",
                        return_value=(b"{}\n", False)), \
                    mock.patch.object(
                        self.sialib.json, "loads",
                        side_effect=parser_error("private source content")):
                cursors = {}
                self.assertEqual(self.sialib.sense_jackal(cursors), [])
                self.assertEqual(cursors["jackal.window"]["seen"], [])

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as stream:
            stream.write("{}\n")
            trend_path = stream.name
        try:
            with mock.patch.object(
                    self.sialib.json, "loads",
                    side_effect=RecursionError("private source content")):
                rows, boundary = self.sialib._bench_trend_snapshot(
                    trend_path, include_metadata=True)
            self.assertEqual(rows, [])
            self.assertTrue(boundary["legacy_truncated"])
        finally:
            os.unlink(trend_path)

    def test_custom_organ_roster_uses_canonical_inert_pages(self):
        old_config = self.sialib.CONFIG
        old_organs = self.sialib.ORGANS
        old_errors = copy.deepcopy(self.sialib.CONFIG_ERRORS)
        with tempfile.TemporaryDirectory() as corpus:
            try:
                self.sialib.CONFIG_ERRORS.clear()
                self.sialib.CONFIG = {"custom_senses": [
                    {"name": "dash", "organ": "-", "path": "/tmp/a",
                     "description": "line\n[[forged]]"},
                    {"name": "dot", "organ": ".x", "path": "/tmp/b",
                     "description": "safe"},
                    {"name": "surrogate", "organ": "surrogate",
                     "path": "/tmp/c", "description": "\ud800"},
                ]}
                organs = self.sialib._build_organs()
                self.assertIn("unknown", organs)
                self.assertIn("x", organs)
                self.assertNotIn("surrogate", organs)
                self.sialib.ORGANS = {
                    key: organs[key] for key in ("unknown", "x")}
                with mock.patch.object(self.sialib, "CORPUS", corpus), \
                        mock.patch.object(
                            self.sialib, "_before_corpus_mutation"):
                    self.sialib.ensure_organs()
                self.assertTrue(os.path.isfile(
                    os.path.join(corpus, "organs", "unknown.md")))
                self.assertTrue(os.path.isfile(
                    os.path.join(corpus, "organs", "x.md")))
                self.assertFalse(os.path.lexists(
                    os.path.join(corpus, "organs", "-.md")))
                with open(os.path.join(corpus, "organs", "unknown.md"),
                          encoding="utf-8") as stream:
                    rendered = stream.read()
                self.assertNotIn("[[forged]]", rendered)
                self.assertIn("⟦⟦forged⟧⟧", rendered)
            finally:
                self.sialib.CONFIG = old_config
                self.sialib.ORGANS = old_organs
                self.sialib.CONFIG_ERRORS[:] = old_errors

    def test_notification_cap_advances_only_through_processed_batch(self):
        with tempfile.TemporaryDirectory() as home:
            history = os.path.join(
                home, ".local/state/omarchy/notifications/history")
            os.makedirs(history)
            names = []
            for index in range(101):
                name = f"{index:03d}.json"
                names.append(name)
                with open(os.path.join(history, name), "w") as stream:
                    json.dump({"app": "fixture", "summary": name}, stream)
            old_home = self.sialib.HOME
            self.sialib.HOME = home
            cursors = {"notify.last": ""}
            try:
                first = self.sialib.sense_notify(cursors)
                self.assertTrue(first)
                self.assertEqual(cursors["notify.last"], names[-2])
                second = self.sialib.sense_notify(cursors)
                self.assertTrue(second)
                self.assertEqual(cursors["notify.last"], names[-1])
            finally:
                self.sialib.HOME = old_home


class SkillSenseContainment(unittest.TestCase):
    def test_sensing_facade_keeps_dynamic_alias_contexts_isolated(self):
        first = _load("sialib_sense_alias_first",
                      os.path.join(BIN, "sialib.py"))
        second = _load("sialib_sense_alias_second",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as root:
            first_home = os.path.join(root, "first")
            second_home = os.path.join(root, "second")
            first_log = os.path.join(root, "first.log")
            second_log = os.path.join(root, "second.log")
            with open(first_log, "w", encoding="utf-8") as stream:
                stream.write("first alias evidence\n")
            with open(second_log, "w", encoding="utf-8") as stream:
                stream.write("second alias evidence\n")
            first.HOME, second.HOME = first_home, second_home
            first.CONFIG = {
                "skills": {"roots": ["first-skills"]},
                "custom_senses": [{"name": "first", "path": first_log}],
            }
            second.CONFIG = {
                "skills": {"roots": ["second-skills"]},
                "custom_senses": [{"name": "second", "path": second_log}],
            }
            first_events, first_errors = first.sense_custom({"custom.first": 0})
            second_events, second_errors = second.sense_custom({"custom.second": 0})
            self.assertEqual(first_errors, [])
            self.assertEqual(second_errors, [])
            self.assertIn("first alias evidence", first_events[0].summary)
            self.assertIn("second alias evidence", second_events[0].summary)
            self.assertEqual(first._configured_skill_roots(), [
                os.path.join(first_home, "first-skills")])
            self.assertEqual(second._configured_skill_roots(), [
                os.path.join(second_home, "second-skills")])
            self.assertIs(first.SENSES[-1], first.sense_custom)
            self.assertIs(second.SENSES[-1], second.sense_custom)

    def test_skill_snapshot_captures_once_with_digest_and_description(self):
        sialib = _load("sialib_skill_single_capture",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "skills")
            skill = os.path.join(root, "stable")
            os.makedirs(skill)
            raw = b"---\ndescription: captured once\n---\n"
            with open(os.path.join(skill, "SKILL.md"), "wb") as stream:
                stream.write(raw)
            sialib.SKILL_ROOTS = [root]
            sialib.CORPUS = os.path.join(directory, "corpus")
            os.makedirs(sialib.CORPUS)
            original = sialib._read_skill_manifest
            calls = []

            def capture_once(capture_root, name):
                calls.append((capture_root, name))
                if len(calls) > 1:
                    raise AssertionError("skill manifest reopened")
                return original(capture_root, name)

            with mock.patch.object(
                    sialib, "_read_skill_manifest",
                    side_effect=capture_once):
                events = sialib.sense_skills({"skills.snapshot": {}})
            self.assertEqual(calls, [(root, "stable")])
            installed = [event for event in events
                         if event.kind == "installed"]
            self.assertEqual(len(installed), 1)
            self.assertIn("captured once", installed[0].summary)

            cursors = {"skills.snapshot": {}}
            with mock.patch.object(
                    sialib, "_read_skill_manifest", wraps=original):
                sialib.sense_skills(cursors)
            state = cursors["skills.snapshot"]["stable"]
            self.assertEqual(state["description"], "captured once")
            root_row = state["roots"][0]
            self.assertEqual(root_row["description"], "captured once")
            self.assertEqual(
                root_row["manifest"]["head_sha256"],
                hashlib.sha256(raw).hexdigest())
            self.assertEqual(root_row["manifest"]["head_bytes"], len(raw))
            self.assertFalse(root_row["manifest"]["head_truncated"])

            # Entity projection consumes only the already-rendered event; it
            # must not reopen a manifest after the sense boundary.
            with mock.patch.object(
                    sialib, "_read_skill_manifest",
                    side_effect=AssertionError("second manifest open")):
                sialib.ensure_event_entities(installed)

    def test_rewrite_after_root_validation_refuses_then_updates(self):
        sialib = _load("sialib_skill_post_validation_rewrite",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "skills")
            skill = os.path.join(root, "mutable")
            os.makedirs(skill)
            manifest = os.path.join(skill, "SKILL.md")
            before = "---\ndescription: old capture\n---\n"
            after = "---\ndescription: new capture\n---\n"
            with open(manifest, "w") as stream:
                stream.write(before)
            sialib.SKILL_ROOTS = [root]
            cursors = {"skills.snapshot": {}}
            sialib.sense_skills(cursors)
            prior_state = copy.deepcopy(
                cursors["skills.snapshot"]["mutable"])
            prior_stat = os.stat(manifest)
            original = sialib._skill_root_generation_matches
            rewritten = []

            def rewrite_after_validation(capture_root, generation):
                stable = original(capture_root, generation)
                if stable and not rewritten:
                    rewritten.append(True)
                    with open(manifest, "w") as stream:
                        stream.write(after)
                    os.utime(manifest, ns=(prior_stat.st_atime_ns,
                                           prior_stat.st_mtime_ns))
                return stable

            with mock.patch.object(
                    sialib, "_skill_root_generation_matches",
                    side_effect=rewrite_after_validation):
                first = sialib.sense_skills(cursors)
            self.assertTrue(cursors["skills.partial"])
            self.assertFalse(any(event.kind == "updated" for event in first))
            self.assertTrue(any(event.kind == "source-refused"
                                for event in first))
            self.assertEqual(
                cursors["skills.snapshot"]["mutable"], prior_state)

            second = sialib.sense_skills(cursors)
            updated = [event for event in second if event.kind == "updated"]
            self.assertEqual(len(updated), 1)
            self.assertIn("new capture", updated[0].summary)
            current_state = cursors["skills.snapshot"]["mutable"]
            self.assertEqual(
                current_state["roots"][0]["manifest"]["mtime_ns"],
                prior_state["roots"][0]["manifest"]["mtime_ns"])
            self.assertNotEqual(
                current_state["roots"][0]["manifest"]["head_sha256"],
                prior_state["roots"][0]["manifest"]["head_sha256"])

    def test_manifest_path_replacement_marks_root_partial_and_retains_state(self):
        sialib = _load("sialib_skill_path_replacement",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "skills")
            skill = os.path.join(root, "resident")
            os.makedirs(skill)
            manifest = os.path.join(skill, "SKILL.md")
            with open(manifest, "wb") as stream:
                stream.write(b"---\ndescription: original\n---\n")
            sialib.SKILL_ROOTS = [root]
            cursors = {}
            sialib.sense_skills(cursors)
            replacement = os.path.join(directory, "replacement")
            with open(replacement, "wb") as stream:
                stream.write(b"---\ndescription: replaced\n---\n")
            real_read = sialib.os.read
            swapped = []

            def replace_after_read(descriptor, count):
                data = real_read(descriptor, count)
                if data and not swapped:
                    swapped.append(True)
                    os.replace(replacement, manifest)
                return data

            with mock.patch.object(
                    sialib.os, "read", side_effect=replace_after_read):
                events = sialib.sense_skills(cursors)
            self.assertTrue(swapped)
            self.assertTrue(cursors["skills.partial"])
            self.assertIn("resident", cursors["skills.snapshot"])
            self.assertFalse(any(event.kind in {"updated", "removed"}
                                 for event in events))
            self.assertTrue(any(event.kind == "source-refused"
                                for event in events))

    def test_in_place_manifest_change_during_read_is_refused(self):
        sialib = _load("sialib_skill_in_place_rewrite",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "skills")
            skill = os.path.join(root, "mutable")
            os.makedirs(skill)
            manifest = os.path.join(skill, "SKILL.md")
            before = b"---\ndescription: alpha\n---\n"
            after = b"---\ndescription: bravo\n---\n"
            with open(manifest, "wb") as stream:
                stream.write(before)
            real_read = sialib.os.read
            rewritten = []

            def rewrite_after_read(descriptor, count):
                data = real_read(descriptor, count)
                if data and not rewritten:
                    rewritten.append(True)
                    with open(manifest, "r+b") as stream:
                        stream.write(after)
                        stream.truncate()
                        stream.flush()
                        os.fsync(stream.fileno())
                return data

            with mock.patch.object(
                    sialib.os, "read", side_effect=rewrite_after_read):
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    sialib._read_skill_manifest(root, "mutable")
            self.assertTrue(rewritten)

    def test_skill_event_occurrence_is_exact_across_crash_retry(self):
        sialib = _load("sialib_skill_crash_retry",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "skills")
            skill = os.path.join(root, "retry")
            os.makedirs(skill)
            with open(os.path.join(skill, "SKILL.md"), "w") as stream:
                stream.write("---\ndescription: exact retry\n---\n")
            sialib.SKILL_ROOTS = [root]
            first_cursors = {"skills.snapshot": {}}
            second_cursors = copy.deepcopy(first_cursors)
            first = sialib.sense_skills(first_cursors)
            second = sialib.sense_skills(second_cursors)
            first_event = next(event for event in first
                               if event.kind == "installed")
            second_event = next(event for event in second
                                if event.kind == "installed")
            self.assertEqual(first_event.occurrence, second_event.occurrence)
            self.assertEqual(first_cursors["skills.snapshot"],
                             second_cursors["skills.snapshot"])

    def test_linked_roots_directories_and_manifests_are_not_opened(self):
        sialib = _load("sialib_skill_containment",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "skills")
            outside = os.path.join(directory, "outside")
            os.makedirs(root)
            os.makedirs(outside)
            real = os.path.join(root, "real")
            os.makedirs(real)
            with open(os.path.join(real, "SKILL.md"), "w") as stream:
                stream.write("---\ndescription: admitted context\n---\n")
            with open(os.path.join(outside, "SKILL.md"), "w") as stream:
                stream.write("---\ndescription: PRIVATE SENTINEL\n---\n")
            os.symlink(outside, os.path.join(root, "linked-directory"))
            linked_file = os.path.join(root, "linked-file")
            os.makedirs(linked_file)
            os.symlink(os.path.join(outside, "SKILL.md"),
                       os.path.join(linked_file, "SKILL.md"))
            linked_root = os.path.join(directory, "linked-root")
            os.symlink(outside, linked_root)
            sialib.SKILL_ROOTS = [root, linked_root]
            cursors = {}
            events = sialib.sense_skills(cursors)

            self.assertEqual(set(cursors["skills.snapshot"]), {"real"})
            rendered = " ".join(event.summary for event in events)
            self.assertIn("real", rendered)
            self.assertNotIn("PRIVATE SENTINEL", rendered)
            self.assertEqual(sialib._skill_description("linked-directory"),
                             "")
            self.assertEqual(sialib._skill_description("linked-file"), "")

    def test_skill_snapshot_is_bounded_and_partial_pages_cannot_remove(self):
        sialib = _load("sialib_skill_bounds",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "skills")
            os.makedirs(root)
            for name in ("one", "two", "three"):
                skill = os.path.join(root, name)
                os.makedirs(skill)
                with open(os.path.join(skill, "SKILL.md"), "w") as stream:
                    stream.write("---\ndescription: bounded\n---\n")
            sialib.SKILL_ROOTS = [root]
            cursors = {
                "skills.snapshot": {
                    "previous": {"name": "previous", "mtime": 0,
                                 "roots": []}},
                "skills.truncated": False,
            }
            with mock.patch.object(
                    sialib, "MAX_SKILL_SNAPSHOT_ENTRIES", 2):
                events = sialib.sense_skills(cursors)

            self.assertTrue(cursors["skills.truncated"])
            self.assertLessEqual(len(cursors["skills.snapshot"]), 2)
            self.assertFalse(any(event.kind == "removed"
                                 for event in events))

    def test_non_utf8_skill_name_has_safe_stable_identity(self):
        sialib = _load("sialib_skill_non_utf8",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "skills")
            os.makedirs(root)
            raw_skill = os.path.join(os.fsencode(root), b"agent-\xff")
            os.mkdir(raw_skill)
            with open(os.path.join(raw_skill, b"SKILL.md"), "wb") as stream:
                stream.write(b"---\ndescription: arbitrary bytes\n---\n")
            sialib.SKILL_ROOTS = [root]
            cursors = {}
            first = sialib.sense_skills(cursors)
            second = sialib.sense_skills(cursors)

            self.assertTrue(first)
            self.assertEqual(second, [])
            self.assertEqual(len(cursors["skills.snapshot"]), 1)
            state = next(iter(cursors["skills.snapshot"].values()))
            self.assertIn(r"\xff", state["name"])
            json.dumps(cursors, ensure_ascii=False).encode("utf-8")
            for event in first:
                sialib.event_memory_identity(event)

    def test_missing_root_retains_state_until_two_complete_snapshots(self):
        sialib = _load("sialib_skill_root_coverage",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "skills")
            hidden = os.path.join(directory, "skills-hidden")
            skill = os.path.join(root, "resident")
            os.makedirs(skill)
            with open(os.path.join(skill, "SKILL.md"), "w") as stream:
                stream.write("---\ndescription: durable\n---\n")
            sialib.SKILL_ROOTS = [root]
            cursors = {}
            sialib.sense_skills(cursors)

            os.rename(root, hidden)
            missing = sialib.sense_skills(cursors)
            self.assertTrue(cursors["skills.partial"])
            self.assertIn("resident", cursors["skills.snapshot"])
            self.assertFalse(any(event.kind == "removed"
                                 for event in missing))
            self.assertTrue(any(event.kind == "source-refused"
                                for event in missing))

            os.rename(hidden, root)
            os.unlink(os.path.join(skill, "SKILL.md"))
            os.rmdir(skill)
            first_complete = sialib.sense_skills(cursors)
            self.assertFalse(cursors["skills.partial"])
            self.assertIn("resident", cursors["skills.snapshot"])
            self.assertFalse(any(event.kind == "removed"
                                 for event in first_complete))

            second_complete = sialib.sense_skills(cursors)
            self.assertTrue(any(event.kind == "removed"
                                for event in second_complete))
            self.assertNotIn("resident", cursors["skills.snapshot"])

    def test_lossy_slug_replacement_has_distinct_cross_generation_identity(self):
        sialib = _load("sialib_skill_cross_generation_identity",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "skills")
            os.makedirs(root)
            first_path = os.path.join(root, "a+b")
            os.makedirs(first_path)
            with open(os.path.join(first_path, "SKILL.md"), "w") as stream:
                stream.write("---\ndescription: first\n---\n")
            sialib.SKILL_ROOTS = [root]
            cursors = {}
            sialib.sense_skills(cursors)
            first_token = next(iter(cursors["skills.snapshot"]))

            os.unlink(os.path.join(first_path, "SKILL.md"))
            os.rmdir(first_path)
            second_path = os.path.join(root, "a b")
            os.makedirs(second_path)
            with open(os.path.join(second_path, "SKILL.md"), "w") as stream:
                stream.write("---\ndescription: second\n---\n")
            events = sialib.sense_skills(cursors)
            second_token = next(iter(cursors["skills.snapshot"]))

            self.assertNotEqual(first_token, second_token)
            self.assertEqual({event.kind for event in events
                              if event.kind in {"installed", "removed"}},
                             {"installed", "removed"})


class TouchWeighting(unittest.TestCase):
    """World-originated touches count full; endogenous self-reference is
    steeply discounted (no echo chamber)."""

    def test_exo_beats_endo(self):
        now = time.time()
        exo = {"nodes": {}}
        endo = {"nodes": {}}
        for _ in range(5):
            siamind.touch(exo, "p", now, src="organ")
            siamind.touch(endo, "p", now, src="ponder")
        b_exo = siamind.actr_base(exo["nodes"]["p"], now + 60)
        b_endo = siamind.actr_base(endo["nodes"]["p"], now + 60)
        self.assertGreater(b_exo, b_endo,
                           "organ touches must outweigh self-reference")


class EpochMerge(unittest.TestCase):
    """Consolidation is idempotent: re-running against an existing epoch
    page EXTENDS it (sums counts), never atomically overwrites — the
    data-loss regression a reviewer would probe."""

    def test_jackal_consolidation_remains_derived_recall(self):
        sialib = _load("sialib_epoch_jackal_origin",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as corpus:
            sialib.CORPUS = corpus
            old_mind_path = sialib.siamind.MIND_PATH
            sialib.siamind.MIND_PATH = os.path.join(corpus, "mind.json")
            self.addCleanup(
                setattr, sialib.siamind, "MIND_PATH", old_mind_path)
            sialib.log = lambda *_args: None
            event_dir = os.path.join(corpus, "events", "jackal")
            os.makedirs(event_dir)
            for day in ("2026-01-05", "2026-01-06"):
                with open(os.path.join(event_dir, day + ".md"), "w",
                          encoding="utf-8") as stream:
                    stream.write(
                        f'---\ntype: event-day\norigin: derived\n'
                        f'title: "JACKAL {day}"\n'
                        f'tags: [jackal, checked]\ndate: {day}\n'
                        'sia_counts: {"checked": 1}\n---\n# JACKAL\n\n'
                        '## Log\n- unverified result observed\n\n'
                        f'## Timeline\n- **{day}** — one observation\n')
            subprocess.run(["git", "init", "-q", corpus], check=True)
            subprocess.run([
                "git", "-C", corpus, "-c", "user.email=t@t",
                "-c", "user.name=t", "add", "-A"], check=True)
            subprocess.run([
                "git", "-C", corpus, "-c", "user.email=t@t",
                "-c", "user.name=t", "commit", "-qm", "fixture"],
                check=True)
            with mock.patch.dict(os.environ, {"SIA_EPISODIC_DAYS": "1"}):
                compacted, epochs, _kept = sialib.consolidate_corpus()
            self.assertGreaterEqual(compacted, 1)
            self.assertGreaterEqual(epochs, 1)
            epoch_paths = []
            for directory, _subdirs, names in os.walk(
                    os.path.join(corpus, "epochs", "jackal")):
                epoch_paths.extend(os.path.join(directory, name)
                                   for name in names if name.endswith(".md"))
            self.assertEqual(len(epoch_paths), 1)
            with open(epoch_paths[0], encoding="utf-8") as stream:
                epoch_text = stream.read()
            self.assertIn("\norigin: derived\n", epoch_text)
            epoch_slug = os.path.relpath(
                epoch_paths[0][:-3], corpus).replace(os.sep, "/")
            self.assertEqual(sialib.corpus_origin(epoch_slug), "derived")

    def test_huge_event_shard_number_refuses_before_range_materialization(self):
        sialib = _load("sialib_epoch_huge_shard",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as corpus:
            sialib.CORPUS = corpus
            event_dir = os.path.join(corpus, "events", "org")
            os.makedirs(event_dir)
            with open(os.path.join(event_dir, "2026-01-05.md"), "w") \
                    as stream:
                stream.write("base\n")
            huge = "9" * 40
            with open(os.path.join(
                    event_dir, f"2026-01-05-part-{huge}.md"), "w") \
                    as stream:
                stream.write("overflow\n")

            with self.assertRaisesRegex(
                    ValueError, "invalid or exceeds its bound"):
                sialib._event_day_shards("org", "2026-01-05")

    def test_queued_operator_pin_protects_day_before_next_pulse(self):
        sialib = _load("sialib_epoch_queued_pin",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as root:
            corpus = os.path.join(root, "corpus")
            state = os.path.join(root, "state")
            os.makedirs(os.path.join(corpus, "events", "journal"))
            os.makedirs(state)
            old_corpus = sialib.siamind.CORPUS
            old_mind_path = sialib.siamind.MIND_PATH
            old_touch_queue = sialib.siamind.TOUCH_QUEUE
            old_window = sialib.siamind.EPISODIC_DAYS
            self.addCleanup(setattr, sialib.siamind, "CORPUS", old_corpus)
            self.addCleanup(
                setattr, sialib.siamind, "MIND_PATH", old_mind_path)
            self.addCleanup(
                setattr, sialib.siamind, "TOUCH_QUEUE", old_touch_queue)
            self.addCleanup(
                setattr, sialib.siamind, "EPISODIC_DAYS", old_window)
            sialib.CORPUS = corpus
            sialib.siamind.CORPUS = corpus
            sialib.siamind.MIND_PATH = os.path.join(state, "mind.json")
            sialib.siamind.TOUCH_QUEUE = os.path.join(
                state, "touch-queue.jsonl")
            sialib.siamind.EPISODIC_DAYS = 1
            sialib.log = lambda *_args: None
            day_slug = "events/journal/2026-01-05"
            day_path = os.path.join(corpus, day_slug + ".md")
            with open(day_path, "w", encoding="utf-8") as stream:
                stream.write(
                    '---\ntype: event-day\ntitle: "journal day"\n'
                    'tags: [journal, observation]\ndate: 2026-01-05\n'
                    'sia_counts: {"observation": 1}\n---\n# journal\n\n'
                    '## Log\n- observed\n\n## Timeline\n- held\n')
            sialib.siamind.save_mind({"nodes": {}, "edges": {}})
            subprocess.run(["git", "init", "-q", corpus], check=True)
            subprocess.run([
                "git", "-C", corpus, "-c", "user.email=t@t",
                "-c", "user.name=t", "add", "-A"], check=True)
            subprocess.run([
                "git", "-C", corpus, "-c", "user.email=t@t",
                "-c", "user.name=t", "commit", "-qm", "x"], check=True)
            self.assertTrue(sialib.siamind.queue_pin(
                day_slug, True, ts=10))

            compacted, epochs, kept = sialib.consolidate_corpus()

            self.assertEqual((compacted, epochs, kept), (0, 0, 1))
            self.assertTrue(os.path.exists(day_path))

    def test_recurring_safety_class_remains_verbatim(self):
        sialib = _load("sialib_epoch_safety",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as d:
            sialib.CORPUS = d
            old_mind_path = sialib.siamind.MIND_PATH
            old_window = sialib.siamind.EPISODIC_DAYS
            sialib.siamind.MIND_PATH = os.path.join(d, "mind.json")
            sialib.siamind.EPISODIC_DAYS = 1
            self.addCleanup(setattr, sialib.siamind, "MIND_PATH",
                            old_mind_path)
            self.addCleanup(setattr, sialib.siamind, "EPISODIC_DAYS",
                            old_window)
            sialib.log = lambda *a: None
            subprocess.run(["git", "init", "-q", d], check=True)
            event_dir = os.path.join(d, "events", "journal")
            os.makedirs(event_dir)
            path = os.path.join(event_dir, "2026-01-05.md")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(
                    '---\ntype: event-day\ntitle: "crash day"\n'
                    'tags: [journal, crash]\ndate: 2026-01-05\n'
                    'sia_counts: {"crash": 1}\n---\n# crash\n\n'
                    '## Log\n- observed\n\n## Timeline\n- held\n')
            # A recurring class remains protected; lifetime frequency does
            # not silently turn a safety-preservation policy into compaction.
            sialib.siamind.save_mind({
                "nodes": {}, "edges": {}, "tagn": {"crash": 1000000}})
            subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                            "-c", "user.name=t", "add", "-A"], check=True)
            subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                            "-c", "user.name=t", "commit", "-qm", "x"],
                           check=True)

            compacted, epochs, kept = sialib.consolidate_corpus()
            self.assertEqual((compacted, epochs, kept), (0, 0, 1))
            self.assertTrue(os.path.exists(path))

    def test_merge_extends_not_overwrites(self):
        sialib = _load("sialib_e", os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as d:
            sialib.CORPUS = d
            old_mind_path = sialib.siamind.MIND_PATH
            sialib.siamind.MIND_PATH = os.path.join(d, "mind.json")
            self.addCleanup(setattr, sialib.siamind, "MIND_PATH",
                            old_mind_path)
            sialib.log = lambda *a: None
            subprocess.run(["git", "init", "-q", d], check=True)
            os.makedirs(os.path.join(d, "events/org"))
            # two old day pages, same ISO week, well past the window
            for day, obs in (("2026-01-05", 4), ("2026-01-06", 3)):
                p = os.path.join(d, f"events/org/{day}.md")
                with open(p, "w") as stream:
                    stream.write(
                        f'---\ntype: event-day\ntitle: "org {day}"\n'
                        f'tags: [org, obs]\ndate: {day}\n'
                        f'sia_counts: {{"obs": {obs}}}\n---\n# org\n\n## Log\n'
                        f'- 01:00:00Z obs thing\n\n## Timeline\n'
                        f'- **{day}** — {obs}\n')
            subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                            "-c", "user.name=t", "add", "-A"], check=True)
            subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                            "-c", "user.name=t", "commit", "-qm", "x"],
                           check=True)
            os.environ["SIA_EPISODIC_DAYS"] = "1"
            n1, e1, _ = sialib.consolidate_corpus()
            self.assertGreaterEqual(n1, 2)
            epoch = None
            for root, _, files in os.walk(os.path.join(d, "epochs")):
                for f in files:
                    epoch = os.path.join(root, f)
            self.assertIsNotNone(epoch, "epoch page must exist")
            import re
            with open(epoch) as stream:
                epoch_text = stream.read()
            c1 = json.loads(re.search(r"^sia_counts: (.*)$",
                                      epoch_text, re.M).group(1))
            self.assertEqual(c1["obs"], 7)
            # add another old day for the SAME week, commit, re-consolidate
            p = os.path.join(d, "events/org/2026-01-07.md")
            with open(p, "w") as stream:
                stream.write(
                    '---\ntype: event-day\ntitle: "org 2026-01-07"\n'
                    'tags: [org, obs]\ndate: 2026-01-07\n'
                    'sia_counts: {"obs": 5}\n---\n# org\n\n## Log\n'
                    '- 01:00:00Z obs thing\n\n## Timeline\n'
                    '- **2026-01-07** — 5\n')
            subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                            "-c", "user.name=t", "add", "-A"], check=True)
            subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                            "-c", "user.name=t", "commit", "-qm", "y"],
                           check=True)
            sialib.consolidate_corpus()
            with open(epoch) as stream:
                epoch_text = stream.read()
            c2 = json.loads(re.search(r"^sia_counts: (.*)$",
                                      epoch_text, re.M).group(1))
            self.assertEqual(c2["obs"], 12, "merge must sum, not replace")

    def test_partial_source_cleanup_replays_without_double_counting(self):
        sialib = _load("sialib_epoch_replay",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as d:
            sialib.CORPUS = d
            old_mind_path = sialib.siamind.MIND_PATH
            sialib.siamind.MIND_PATH = os.path.join(d, "mind.json")
            self.addCleanup(setattr, sialib.siamind, "MIND_PATH",
                            old_mind_path)
            sialib.log = lambda *a: None
            subprocess.run(["git", "init", "-q", d], check=True)
            event_dir = os.path.join(d, "events/org")
            os.makedirs(event_dir)
            for day, obs in (("2026-01-05", 4), ("2026-01-06", 3)):
                path = os.path.join(event_dir, day + ".md")
                with open(path, "w") as stream:
                    stream.write(
                        f'---\ntype: event-day\ntitle: "org {day}"\n'
                        f'tags: [org, obs]\ndate: {day}\n'
                        f'sia_counts: {{"obs": {obs}}}\n---\n# org\n\n'
                        f'## Log\n- 01:00:00Z obs thing\n\n## Timeline\n'
                        f'- **{day}** — {obs}\n')
            subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                            "-c", "user.name=t", "add", "-A"], check=True)
            subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                            "-c", "user.name=t", "commit", "-qm", "x"],
                           check=True)

            real_unlink = sialib.os.unlink
            removed = []

            def interrupt_cleanup(path):
                if path.startswith(event_dir + os.sep):
                    if removed:
                        raise OSError("simulated interruption")
                    real_unlink(path)
                    removed.append(path)
                    return
                real_unlink(path)

            with mock.patch.object(sialib.os, "unlink",
                                   side_effect=interrupt_cleanup):
                with self.assertRaisesRegex(OSError,
                                            "simulated interruption"):
                    sialib.consolidate_corpus()

            epoch = next(
                os.path.join(root, filename)
                for root, _dirs, files in os.walk(os.path.join(d, "epochs"))
                for filename in files)
            with open(epoch) as stream:
                interrupted_text = stream.read()
            interrupted_counts = json.loads(re.search(
                r"^sia_counts: (.*)$", interrupted_text, re.M).group(1))

            sialib.consolidate_corpus()
            with open(epoch) as stream:
                recovered_text = stream.read()
            recovered_counts = json.loads(re.search(
                r"^sia_counts: (.*)$", recovered_text, re.M).group(1))
            self.assertEqual(recovered_counts, interrupted_counts)
            self.assertEqual(os.listdir(event_dir), [])
            self.assertRegex(recovered_text, r"(?m)^sia_sources: \[")

    def test_multi_shard_cleanup_recovers_missing_base_and_hole(self):
        for mode in ("missing-base", "missing-middle"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                sialib = _load(
                    "sialib_epoch_shard_" + mode.replace("-", "_"),
                    os.path.join(BIN, "sialib.py"))
                sialib.CORPUS = d
                old_mind_path = sialib.siamind.MIND_PATH
                old_window = sialib.siamind.EPISODIC_DAYS
                old_bullets = sialib.MAX_EVENT_BULLETS
                sialib.siamind.MIND_PATH = os.path.join(d, "mind.json")
                sialib.siamind.EPISODIC_DAYS = 1
                sialib.MAX_EVENT_BULLETS = 1
                self.addCleanup(setattr, sialib.siamind, "MIND_PATH",
                                old_mind_path)
                self.addCleanup(setattr, sialib.siamind,
                                "EPISODIC_DAYS", old_window)
                self.addCleanup(setattr, sialib, "MAX_EVENT_BULLETS",
                                old_bullets)
                sialib.log = lambda *a: None
                subprocess.run(["git", "init", "-q", d], check=True)
                stamp = sialib.datetime.datetime(
                    2026, 1, 5, 12, tzinfo=sialib.datetime.timezone.utc)
                events = [
                    sialib.Event(
                        "org", stamp, "obs", f"observation {number}",
                        occurrence=f"native:shard:{number}")
                    for number in (1, 2, 3)
                ]
                sialib.update_day_page("org", "2026-01-05", events)
                subprocess.run(
                    ["git", "-C", d, "-c", "user.email=t@t", "-c",
                     "user.name=t", "add", "-A"], check=True)
                subprocess.run(
                    ["git", "-C", d, "-c", "user.email=t@t", "-c",
                     "user.name=t", "commit", "-qm", "sources"],
                    check=True)

                event_dir = os.path.join(d, "events", "org")
                base = os.path.join(event_dir, "2026-01-05.md")
                middle = os.path.join(
                    event_dir, "2026-01-05-part-2.md")
                last = os.path.join(event_dir, "2026-01-05-part-3.md")
                real_unlink = sialib.os.unlink
                removed = []

                def interrupt_cleanup(path):
                    if path.startswith(event_dir + os.sep):
                        if mode == "missing-base" and not removed:
                            real_unlink(path)
                            removed.append(path)
                            return
                        raise OSError("simulated shard cleanup interruption")
                    real_unlink(path)

                with mock.patch.object(
                        sialib.os, "unlink", side_effect=interrupt_cleanup):
                    with self.assertRaisesRegex(
                            OSError, "simulated shard cleanup interruption"):
                        sialib.consolidate_corpus()

                epoch = sialib.corpus_path(
                    sialib._epoch_slug_for_day("org", "2026-01-05"))
                with open(epoch, encoding="utf-8") as stream:
                    epoch_before = stream.read()
                manifest = json.loads(re.search(
                    r"^sia_source_manifest: (.*)$", epoch_before,
                    re.M).group(1))
                self.assertEqual(len(manifest), len(events))
                index_files = [
                    os.path.join(root, filename)
                    for root, _dirs, files in os.walk(
                        os.path.join(d, "event-index"))
                    for filename in files if filename.endswith(".json")
                ]
                self.assertEqual(len(index_files), len(events))

                if mode == "missing-base":
                    self.assertFalse(os.path.exists(base))
                    self.assertTrue(os.path.exists(middle))
                else:
                    real_unlink(middle)
                    self.assertTrue(os.path.exists(base))
                self.assertTrue(os.path.exists(last))

                sialib.consolidate_corpus()
                with open(epoch, encoding="utf-8") as stream:
                    self.assertEqual(stream.read(), epoch_before)
                self.assertEqual(os.listdir(event_dir), [])

    def test_multi_shard_recovery_refuses_lineage_conflict(self):
        sialib = _load("sialib_epoch_shard_conflict",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as d:
            sialib.CORPUS = d
            old_mind_path = sialib.siamind.MIND_PATH
            old_window = sialib.siamind.EPISODIC_DAYS
            old_bullets = sialib.MAX_EVENT_BULLETS
            sialib.siamind.MIND_PATH = os.path.join(d, "mind.json")
            sialib.siamind.EPISODIC_DAYS = 1
            sialib.MAX_EVENT_BULLETS = 1
            self.addCleanup(setattr, sialib.siamind, "MIND_PATH",
                            old_mind_path)
            self.addCleanup(setattr, sialib.siamind, "EPISODIC_DAYS",
                            old_window)
            self.addCleanup(setattr, sialib, "MAX_EVENT_BULLETS",
                            old_bullets)
            sialib.log = lambda *a: None
            subprocess.run(["git", "init", "-q", d], check=True)
            stamp = sialib.datetime.datetime(
                2026, 1, 5, 12, tzinfo=sialib.datetime.timezone.utc)
            events = [
                sialib.Event("org", stamp, "obs", f"event {number}",
                             occurrence=f"native:conflict:{number}")
                for number in (1, 2, 3)
            ]
            sialib.update_day_page("org", "2026-01-05", events)
            subprocess.run(
                ["git", "-C", d, "-c", "user.email=t@t", "-c",
                 "user.name=t", "add", "-A"], check=True)
            subprocess.run(
                ["git", "-C", d, "-c", "user.email=t@t", "-c",
                 "user.name=t", "commit", "-qm", "sources"], check=True)

            event_dir = os.path.join(d, "events", "org")
            real_unlink = sialib.os.unlink

            def stop_before_cleanup(path):
                if path.startswith(event_dir + os.sep):
                    raise OSError("simulated pre-cleanup interruption")
                real_unlink(path)

            with mock.patch.object(
                    sialib.os, "unlink", side_effect=stop_before_cleanup):
                with self.assertRaisesRegex(
                        OSError, "simulated pre-cleanup interruption"):
                    sialib.consolidate_corpus()

            middle = os.path.join(event_dir, "2026-01-05-part-2.md")
            with open(middle, "a", encoding="utf-8") as stream:
                stream.write("\nconflicting bytes\n")
            epoch = sialib.corpus_path(
                sialib._epoch_slug_for_day("org", "2026-01-05"))
            with open(epoch, encoding="utf-8") as stream:
                epoch_before = stream.read()

            with self.assertRaisesRegex(
                    RuntimeError, "conflicts with epoch source lineage"):
                sialib.consolidate_corpus()
            with open(epoch, encoding="utf-8") as stream:
                self.assertEqual(stream.read(), epoch_before)
            self.assertEqual(len(os.listdir(event_dir)), len(events))

    def test_over_capacity_week_is_retained_without_partial_mutation(self):
        for mode in ("source-records", "source-bytes", "event-index",
                     "rendered-epoch"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                sialib = _load(
                    "sialib_epoch_capacity_" + mode.replace("-", "_"),
                    os.path.join(BIN, "sialib.py"))
                sialib.CORPUS = d
                old_mind_path = sialib.siamind.MIND_PATH
                old_window = sialib.siamind.EPISODIC_DAYS
                sialib.siamind.MIND_PATH = os.path.join(d, "mind.json")
                sialib.siamind.EPISODIC_DAYS = 1
                self.addCleanup(setattr, sialib.siamind, "MIND_PATH",
                                old_mind_path)
                self.addCleanup(setattr, sialib.siamind,
                                "EPISODIC_DAYS", old_window)
                sialib.log = lambda *a: None
                subprocess.run(["git", "init", "-q", d], check=True)
                stamp = sialib.datetime.datetime(
                    2026, 1, 5, 12, tzinfo=sialib.datetime.timezone.utc)
                events = [
                    sialib.Event(
                        "org", stamp, "obs", f"capacity event {number}",
                        occurrence=f"native:capacity:{mode}:{number}")
                    for number in (1, 2, 3)
                ]
                if mode == "source-records":
                    sialib.MAX_EVENT_BULLETS = 1
                    sialib.MAX_EPOCH_SOURCE_RECORDS = 2
                sialib.update_day_page("org", "2026-01-05", events)
                if mode == "source-bytes":
                    sialib.MAX_EPOCH_SOURCE_MANIFEST_BYTES = 1
                elif mode == "event-index":
                    sialib.MAX_EVENT_INDEX_RECORDS = 1
                elif mode == "rendered-epoch":
                    sialib.MAX_EPOCH_PAGE_BYTES = 1
                subprocess.run(
                    ["git", "-C", d, "-c", "user.email=t@t", "-c",
                     "user.name=t", "add", "-A"], check=True)
                subprocess.run(
                    ["git", "-C", d, "-c", "user.email=t@t", "-c",
                     "user.name=t", "commit", "-qm", "sources"],
                    check=True)

                result = sialib.consolidate_corpus()
                self.assertEqual(result, (0, 0, 1))
                event_dir = os.path.join(d, "events", "org")
                self.assertTrue(os.listdir(event_dir))
                self.assertFalse(os.path.exists(os.path.join(d, "epochs")))
                self.assertFalse(
                    os.path.exists(os.path.join(d, "event-index")))

    def test_legacy_epoch_metadata_capacity_retains_exact_source(self):
        sialib = _load("sialib_epoch_legacy_capacity",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as d:
            sialib.CORPUS = d
            old_mind_path = sialib.siamind.MIND_PATH
            old_window = sialib.siamind.EPISODIC_DAYS
            sialib.siamind.MIND_PATH = os.path.join(d, "mind.json")
            sialib.siamind.EPISODIC_DAYS = 1
            self.addCleanup(setattr, sialib.siamind, "MIND_PATH",
                            old_mind_path)
            self.addCleanup(setattr, sialib.siamind, "EPISODIC_DAYS",
                            old_window)
            sialib.log = lambda *a: None
            subprocess.run(["git", "init", "-q", d], check=True)
            stamp = sialib.datetime.datetime(
                2026, 1, 5, 12, tzinfo=sialib.datetime.timezone.utc)
            event = sialib.Event(
                "org", stamp, "obs", "legacy recovery source",
                occurrence="native:legacy-capacity")
            sialib.update_day_page("org", "2026-01-05", [event])
            relative = "events/org/2026-01-05.md"
            source_path = os.path.join(d, relative)
            with open(source_path, "rb") as stream:
                source_bytes = stream.read()
            source_id = hashlib.sha256(
                relative.encode("utf-8") + b"\0" + source_bytes).hexdigest()
            epoch_slug = sialib._epoch_slug_for_day(
                "org", "2026-01-05")
            sialib.write_page(
                epoch_slug,
                ["type: epoch", sialib.fm_title("legacy epoch"),
                 "tags: [org]", "date: 2026-01-05",
                 "sia_sources: " + json.dumps(
                     [source_id], separators=(",", ":")),
                 'sia_dates: ["2026-01-05"]',
                 'sia_counts: {"obs": 1}'],
                "# legacy epoch\n\n"
                "Consolidated from 1 day-memories "
                "(2026-01-05 … 2026-01-05).\n")
            subprocess.run(
                ["git", "-C", d, "-c", "user.email=t@t", "-c",
                 "user.name=t", "add", "-A"], check=True)
            subprocess.run(
                ["git", "-C", d, "-c", "user.email=t@t", "-c",
                 "user.name=t", "commit", "-qm", "legacy state"],
                check=True)
            epoch_path = sialib.corpus_path(epoch_slug)
            with open(epoch_path, encoding="utf-8") as stream:
                epoch_before = stream.read()
            sialib.MAX_EPOCH_PAGE_BYTES = len(epoch_before.encode("utf-8"))

            self.assertEqual(sialib.consolidate_corpus(), (0, 0, 1))
            self.assertTrue(os.path.exists(source_path))
            with open(epoch_path, encoding="utf-8") as stream:
                self.assertEqual(stream.read(), epoch_before)
            self.assertFalse(
                os.path.exists(os.path.join(d, "event-index")))

    def test_first_event_index_publish_fsyncs_new_directory_links(self):
        sialib = _load("sialib_epoch_index_durability",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as d:
            sialib.CORPUS = d
            old_mind_path = sialib.siamind.MIND_PATH
            old_window = sialib.siamind.EPISODIC_DAYS
            sialib.siamind.MIND_PATH = os.path.join(d, "mind.json")
            sialib.siamind.EPISODIC_DAYS = 1
            self.addCleanup(setattr, sialib.siamind, "MIND_PATH",
                            old_mind_path)
            self.addCleanup(setattr, sialib.siamind, "EPISODIC_DAYS",
                            old_window)
            sialib.log = lambda *a: None
            subprocess.run(["git", "init", "-q", d], check=True)
            stamp = sialib.datetime.datetime(
                2026, 1, 5, 12, tzinfo=sialib.datetime.timezone.utc)
            event = sialib.Event(
                "org", stamp, "obs", "durable event index",
                occurrence="native:index-durability")
            sialib.update_day_page("org", "2026-01-05", [event])
            subprocess.run(
                ["git", "-C", d, "-c", "user.email=t@t", "-c",
                 "user.name=t", "add", "-A"], check=True)
            subprocess.run(
                ["git", "-C", d, "-c", "user.email=t@t", "-c",
                 "user.name=t", "commit", "-qm", "source"], check=True)
            real_fsync = sialib.os.fsync
            synced = set()

            def track_fsync(fd):
                try:
                    synced.add(os.path.realpath(
                        os.readlink(f"/proc/self/fd/{fd}")))
                except OSError:
                    pass
                return real_fsync(fd)

            with mock.patch.object(
                    sialib.os, "fsync", side_effect=track_fsync):
                sialib.consolidate_corpus()

            event_id = sialib.event_memory_identity(event)
            index_leaf = os.path.join(
                d, sialib._event_index_relative("org", event_id))
            prefix = os.path.dirname(index_leaf)
            expected = {
                os.path.realpath(d),
                os.path.realpath(os.path.join(d, "event-index")),
                os.path.realpath(os.path.join(d, "event-index", "org")),
                os.path.realpath(prefix),
            }
            self.assertTrue(expected <= synced)
            self.assertTrue(os.path.isfile(index_leaf))

    def test_event_index_directory_retry_repairs_visible_chain(self):
        sialib = _load("sialib_epoch_index_directory_retry",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as d:
            sialib.CORPUS = d
            old_mind_path = sialib.siamind.MIND_PATH
            old_window = sialib.siamind.EPISODIC_DAYS
            sialib.siamind.MIND_PATH = os.path.join(d, "mind.json")
            sialib.siamind.EPISODIC_DAYS = 1
            self.addCleanup(setattr, sialib.siamind, "MIND_PATH",
                            old_mind_path)
            self.addCleanup(setattr, sialib.siamind, "EPISODIC_DAYS",
                            old_window)
            sialib.log = lambda *a: None
            subprocess.run(["git", "init", "-q", d], check=True)
            stamp = sialib.datetime.datetime(
                2026, 1, 5, 12, tzinfo=sialib.datetime.timezone.utc)
            event = sialib.Event(
                "org", stamp, "obs", "retry durable event index",
                occurrence="native:index-directory-retry")
            sialib.update_day_page("org", "2026-01-05", [event])
            subprocess.run(
                ["git", "-C", d, "-c", "user.email=t@t", "-c",
                 "user.name=t", "add", "-A"], check=True)
            subprocess.run(
                ["git", "-C", d, "-c", "user.email=t@t", "-c",
                 "user.name=t", "commit", "-qm", "source"], check=True)
            event_id = sialib.event_memory_identity(event)
            index_leaf = os.path.join(
                d, sialib._event_index_relative("org", event_id))
            prefix = os.path.dirname(index_leaf)
            organ_directory = os.path.dirname(prefix)
            source_path = sialib.corpus_path(
                sialib.day_slug("org", "2026-01-05"))
            real_fsync = sialib.os.fsync
            organ_syncs = []

            def fail_last_parent_sync(fd):
                target = os.path.realpath(os.readlink(f"/proc/self/fd/{fd}"))
                if target == os.path.realpath(organ_directory):
                    organ_syncs.append(target)
                    if len(organ_syncs) == 2:
                        raise OSError("simulated event-index parent fsync")
                return real_fsync(fd)

            with mock.patch.object(
                    sialib.os, "fsync", side_effect=fail_last_parent_sync):
                with self.assertRaisesRegex(
                        OSError, "simulated event-index parent fsync"):
                    sialib.consolidate_corpus()
            self.assertTrue(os.path.isdir(prefix))
            self.assertFalse(os.path.exists(index_leaf))
            self.assertTrue(os.path.exists(source_path))

            retry_synced = set()

            def track_retry(fd):
                retry_synced.add(os.path.realpath(
                    os.readlink(f"/proc/self/fd/{fd}")))
                return real_fsync(fd)

            with mock.patch.object(sialib.os, "fsync", side_effect=track_retry):
                sialib.consolidate_corpus()
            self.assertTrue({os.path.realpath(prefix),
                             os.path.realpath(organ_directory)}
                            <= retry_synced)
            self.assertTrue(os.path.isfile(index_leaf))
            self.assertFalse(os.path.exists(source_path))

    def test_consolidated_occurrence_index_suppresses_replay_and_conflict(self):
        sialib = _load("sialib_epoch_event_index",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as d:
            sialib.CORPUS = d
            old_mind_path = sialib.siamind.MIND_PATH
            old_window = sialib.siamind.EPISODIC_DAYS
            sialib.siamind.MIND_PATH = os.path.join(d, "mind.json")
            sialib.siamind.EPISODIC_DAYS = 1
            self.addCleanup(setattr, sialib.siamind, "MIND_PATH",
                            old_mind_path)
            self.addCleanup(setattr, sialib.siamind, "EPISODIC_DAYS",
                            old_window)
            sialib.log = lambda *a: None
            subprocess.run(["git", "init", "-q", d], check=True)
            old_stamp = sialib.datetime.datetime(
                2026, 1, 5, 12, tzinfo=sialib.datetime.timezone.utc)
            original = sialib.Event(
                "org", old_stamp, "obs", "source-native observation",
                links=("projects/demo",), tags=("remembered",),
                occurrence="native:stable:one")
            sialib.update_day_page("org", "2026-01-05", [original])
            subprocess.run(
                ["git", "-C", d, "-c", "user.email=t@t", "-c",
                 "user.name=t", "add", "-A"], check=True)
            subprocess.run(
                ["git", "-C", d, "-c", "user.email=t@t", "-c",
                 "user.name=t", "commit", "-qm", "source"], check=True)
            sialib.consolidate_corpus()

            event_id = sialib.event_memory_identity(original)
            entry = sialib._read_event_index_entry("org", event_id)
            self.assertIsNotNone(entry)
            self.assertEqual(entry["semantic_id"],
                             sialib.event_semantic_identity(original))
            self.assertFalse(sialib.page_exists(
                sialib.day_slug("org", "2026-01-05")))

            later_stamp = sialib.datetime.datetime(
                2026, 8, 29, 20, tzinfo=sialib.datetime.timezone.utc)
            replay = sialib.Event(
                "org", later_stamp, "obs", "source-native observation",
                links=("projects/demo",), tags=("remembered",),
                occurrence="native:stable:one")
            _pages, appended, admitted = sialib.update_day_page(
                "org", "2026-08-29", [replay])
            self.assertEqual(appended, [])
            self.assertEqual([slug for _event, slug in admitted],
                             [entry["epoch_slug"]])
            self.assertFalse(sialib.page_exists(
                sialib.day_slug("org", "2026-08-29")))

            conflict = sialib.Event(
                "org", later_stamp, "changed", "changed meaning",
                occurrence="native:stable:one")
            with self.assertRaisesRegex(
                    ValueError, "conflicts with another day page"):
                sialib.update_day_page("org", "2026-08-29", [conflict])

            novel = sialib.Event(
                "org", later_stamp, "obs", "new source observation",
                occurrence="native:stable:two")
            _pages, appended, _admitted = sialib.update_day_page(
                "org", "2026-08-29", [novel])
            self.assertEqual(appended, [novel])
            self.assertTrue(sialib.page_exists(
                sialib.day_slug("org", "2026-08-29")))

    def test_malformed_counts_refuse_consolidation_and_day_rewrite(self):
        sialib = _load("sialib_epoch_malformed",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as d:
            sialib.CORPUS = d
            old_mind_path = sialib.siamind.MIND_PATH
            sialib.siamind.MIND_PATH = os.path.join(d, "mind.json")
            self.addCleanup(setattr, sialib.siamind, "MIND_PATH",
                            old_mind_path)
            sialib.log = lambda *a: None
            subprocess.run(["git", "init", "-q", d], check=True)
            event_dir = os.path.join(d, "events/org")
            os.makedirs(event_dir)
            path = os.path.join(event_dir, "2026-01-05.md")
            damaged = (
                '---\ntype: event-day\ntitle: "damaged"\n'
                'tags: [org]\ndate: 2026-01-05\n'
                'sia_counts: {broken\n---\n# org\n\n## Log\n- held\n')
            with open(path, "w") as stream:
                stream.write(damaged)
            subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                            "-c", "user.name=t", "add", "-A"], check=True)
            subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                            "-c", "user.name=t", "commit", "-qm", "x"],
                           check=True)

            with self.assertRaisesRegex(ValueError,
                                        "sia_counts is malformed"):
                sialib.consolidate_corpus()
            with open(path) as stream:
                self.assertEqual(stream.read(), damaged)

            event = sialib.Event("org", sialib.utcnow(), "obs", "new")
            with self.assertRaisesRegex(ValueError,
                                        "sia_counts is malformed"):
                sialib.update_day_page("org", "2026-01-05", [event])
            with open(path) as stream:
                self.assertEqual(stream.read(), damaged)


    def test_bounded_scan_cursor_never_deletes_from_a_partial_page(self):
        sialib = _load(
            "sialib_epoch_bounded_cursor", os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as d:
            sialib.CORPUS = d
            old_mind_path = sialib.siamind.MIND_PATH
            old_window = sialib.siamind.EPISODIC_DAYS
            sialib.siamind.MIND_PATH = os.path.join(d, "mind.json")
            sialib.siamind.EPISODIC_DAYS = 1
            self.addCleanup(
                setattr, sialib.siamind, "MIND_PATH", old_mind_path)
            self.addCleanup(
                setattr, sialib.siamind, "EPISODIC_DAYS", old_window)
            subprocess.run(["git", "init", "-q", d], check=True)
            event_dir = os.path.join(d, "events", "org")
            os.makedirs(event_dir)
            source = os.path.join(event_dir, "2026-01-05.md")
            with open(source, "w", encoding="utf-8") as stream:
                stream.write(
                    '---\ntype: event-day\ntitle: "bounded"\n'
                    'tags: [org]\ndate: 2026-01-05\n'
                    'sia_counts: {"obs": 1}\n---\n# org\n\n'
                    '## Log\n- observed\n\n## Timeline\n- held\n')
            sialib.siamind.save_mind({"nodes": {}, "edges": {}})
            subprocess.run(
                ["git", "-C", d, "-c", "user.email=t@t", "-c",
                 "user.name=t", "add", "-A"], check=True)
            subprocess.run(
                ["git", "-C", d, "-c", "user.email=t@t", "-c",
                 "user.name=t", "commit", "-qm", "source"], check=True)
            with mock.patch.object(sialib, "MAX_SOURCE_SCAN_ENTRIES", 1):
                self.assertEqual(sialib.consolidate_corpus(), (0, 0, 0))
                self.assertTrue(os.path.exists(source))
                self.assertIn("pending", sialib._consolidation_scan_debt())
                for _attempt in range(20):
                    sialib.consolidate_corpus()
                    if not os.path.exists(source):
                        break
            self.assertFalse(os.path.exists(source))

    def test_pulses_resume_marker_free_scan_debt_until_readiness_returns(self):
        sialib = _load(
            "sialib_epoch_pulse_scan", os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as corpus:
            sialib.CORPUS = corpus
            event_dir = os.path.join(corpus, "events", "org")
            os.makedirs(event_dir)
            for day in ("2999-01-05", "2999-01-06"):
                with open(os.path.join(event_dir, day + ".md"), "w",
                          encoding="utf-8") as stream:
                    stream.write("future event\n")
            empty_mind = {"nodes": {}, "edges": {}}
            with mock.patch.object(
                    sialib, "MAX_SOURCE_SCAN_ENTRIES", 1), \
                    mock.patch.object(
                        sialib, "corpus_commit", return_value="clean"), \
                    mock.patch.object(
                        sialib.siamind, "load_mind",
                        return_value=empty_mind), \
                    mock.patch.object(
                        sialib.siamind, "pending_user_pin_slugs",
                        return_value=set()):
                # DREAM owns consolidation mutations, but one bounded pass is
                # intentionally insufficient to finish this directory tree.
                self.assertEqual(sialib.consolidate_corpus(), (0, 0, 0))
            self.assertIn("pending", sialib._consolidation_scan_debt())

            memo = {"ready": {
                "v": 1, "completed_at": "2026-08-30T12:00:00Z",
                "kind": "recovery", "identity": "0" * 32}}
            store = {"v": 1, "thoughts": []}

            def recover_once():
                return sialib._recover_before_pulse(memo, store)

            recovery_patches = (
                mock.patch.object(
                    sialib, "_recover_pending_thought_projection"),
                mock.patch.object(
                    sialib, "recover_ledger_transitions",
                    return_value=([], [])),
                mock.patch.object(
                    sialib, "_settle_pending_dream_unit",
                    return_value=None),
                mock.patch.object(sialib, "_complete_pending_dream_cycle"),
                mock.patch.object(
                    sialib.siatakes, "recover_natural_history_transactions",
                    return_value=([], [])),
                mock.patch.object(
                    sialib.siatakes, "recover_grade_transactions",
                    return_value=([], [])),
                mock.patch.object(
                    sialib.siatakes, "migrate_legacy_take_pages",
                    return_value=([], [])),
                mock.patch.object(
                    sialib.siatakes, "advance_intent_history",
                    return_value=([], [])),
                mock.patch.object(
                    sialib.siamind, "load_mind", return_value={}),
                mock.patch.object(
                    sialib.siamind, "pending_user_pin_slugs",
                    return_value=set()),
                mock.patch.object(sialib, "MAX_SOURCE_SCAN_ENTRIES", 1),
                mock.patch.object(
                    sialib, "corpus_commit", return_value="clean"),
                mock.patch.object(sialib, "_write_memo"),
                mock.patch.object(
                    sialib, "queue_ledger_transition",
                    return_value="pending"),
                mock.patch.object(sialib, "_settle_ledger_transition"),
            )
            with contextlib.ExitStack() as stack:
                for patcher in recovery_patches:
                    stack.enter_context(patcher)
                before_crash = sialib.read_state_json(
                    sialib._consolidation_scan_path(), {},
                    "consolidation scan")
                save_scan = sialib._save_consolidation_scan

                def save_then_crash(value):
                    saved = save_scan(value)
                    raise RuntimeError("crash after consolidation checkpoint")

                with mock.patch.object(
                        sialib, "_save_consolidation_scan",
                        side_effect=save_then_crash):
                    with self.assertRaisesRegex(
                            RuntimeError, "after consolidation checkpoint"):
                        recover_once()
                after_crash = sialib.read_state_json(
                    sialib._consolidation_scan_path(), {},
                    "consolidation scan")
                self.assertNotEqual(after_crash, before_crash)

                previous = json.dumps(after_crash, sort_keys=True)
                for _attempt in range(sialib.MAX_EVENT_LOOKUP_PAGES):
                    if not sialib._consolidation_scan_debt():
                        break
                    recover_once()
                    current = json.dumps(sialib.read_state_json(
                        sialib._consolidation_scan_path(), {},
                        "consolidation scan"), sort_keys=True)
                    self.assertNotEqual(current, previous)
                    previous = current
            self.assertEqual(sialib._consolidation_scan_debt(), "")

            readiness_patches = (
                mock.patch.object(
                    sialib, "corpus_owner",
                    side_effect=lambda: contextlib.nullcontext()),
                mock.patch.object(sialib, "load_memo", return_value=memo),
                mock.patch.object(
                    sialib, "_thought_recovery_debt", return_value=""),
                mock.patch.object(
                    sialib, "_graph_projection_debt", return_value=""),
                mock.patch.object(
                    sialib.siamind, "load_mind", return_value={}),
                mock.patch.object(
                    sialib.siatakes, "natural_history_recovery_required",
                    return_value=False),
                mock.patch.object(
                    sialib.siatakes, "grade_recovery_required",
                    return_value=False),
                mock.patch.object(
                    sialib.siatakes, "take_migration_required",
                    return_value=False),
                mock.patch.object(
                    sialib.siatakes, "intent_history_required",
                    return_value=False),
            )
            with contextlib.ExitStack() as stack:
                for patcher in readiness_patches:
                    stack.enter_context(patcher)
                self.assertEqual(sialib.memory_readiness(), (True, ""))

    def test_originating_dream_marker_spans_old_day_claim_batches(self):
        sialib = _load(
            "sialib_epoch_claim_pulses", os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as corpus:
            sialib.CORPUS = corpus
            event_dir = os.path.join(corpus, "events", "org")
            os.makedirs(event_dir)
            sources = []
            for day in ("2026-01-05", "2026-01-06"):
                path = os.path.join(event_dir, day + ".md")
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write(
                        '---\ntype: event-day\ntitle: "claim batch"\n'
                        f'tags: [org]\ndate: {day}\n'
                        'sia_counts: {"obs": 1}\n---\n# org\n\n'
                        f'## Log\n- {day}\n\n## Timeline\n- held\n')
                sources.append(path)
            subprocess.run(["git", "init", "-q", corpus], check=True)
            subprocess.run(
                ["git", "-C", corpus, "-c", "user.email=t@t", "-c",
                 "user.name=t", "add", "-A"], check=True)
            subprocess.run(
                ["git", "-C", corpus, "-c", "user.email=t@t", "-c",
                 "user.name=t", "commit", "-qm", "old sources"],
                check=True)

            memo = {"ready": {
                "v": 1, "completed_at": "2026-08-30T12:00:00Z",
                "kind": "recovery", "identity": "0" * 32}}
            store = {"v": 1, "thoughts": []}
            settled = []
            fixed_now = datetime.datetime(
                2026, 8, 30, tzinfo=datetime.timezone.utc)
            recovery_patches = (
                mock.patch.object(sialib, "_write_memo"),
                mock.patch.object(
                    sialib, "queue_ledger_transition",
                    return_value="pending"),
                mock.patch.object(
                    sialib, "_settle_ledger_transition",
                    side_effect=lambda path: settled.append(path)),
                mock.patch.object(sialib, "MAX_SOURCE_SCAN_ENTRIES", 1),
                mock.patch.object(
                    sialib, "MAX_CONSOLIDATION_DAYS_PER_RUN", 1),
                mock.patch.object(sialib, "utcnow", return_value=fixed_now),
                mock.patch.object(
                    sialib.siamind, "load_mind",
                    return_value={"nodes": {}, "edges": {}}),
                mock.patch.object(
                    sialib.siamind, "pending_user_pin_slugs",
                    return_value=set()),
                mock.patch.object(
                    sialib, "_recover_pending_thought_projection"),
                mock.patch.object(
                    sialib, "recover_ledger_transitions",
                    return_value=([], [])),
                mock.patch.object(
                    sialib, "_settle_pending_dream_unit",
                    return_value=None),
                mock.patch.object(sialib, "_complete_pending_dream_cycle"),
                mock.patch.object(
                    sialib.siatakes, "recover_natural_history_transactions",
                    return_value=([], [])),
                mock.patch.object(
                    sialib.siatakes, "recover_grade_transactions",
                    return_value=([], [])),
                mock.patch.object(
                    sialib.siatakes, "migrate_legacy_take_pages",
                    return_value=([], [])),
                mock.patch.object(
                    sialib.siatakes, "advance_intent_history",
                    return_value=([], [])),
                mock.patch.object(sialib, "_settle_pending_publication"),
            )
            with contextlib.ExitStack() as stack:
                for patcher in recovery_patches:
                    stack.enter_context(patcher)
                marker = sialib._mark_consolidation_pending(memo)
                sialib._bind_consolidation_ledger(
                    memo, "DREAM:consolidate", f"id={marker['id']}",
                    "completed")

                # The originating DREAM performs one bounded unit and leaves
                # its exact ledger identity pending, not falsely completed.
                sialib._recover_pending_consolidation(memo)
                pending = sialib._pending_consolidation_marker(memo)
                self.assertIsInstance(pending, dict)
                self.assertNotIn("applied_at", pending)
                self.assertIn("pending", sialib._consolidation_scan_debt())
                self.assertEqual(settled, [])

                saw_one_removed_while_pending = False
                saw_all_removed_while_pending = False
                for _attempt in range(sialib.MAX_EVENT_LOOKUP_PAGES):
                    if sialib._pending_consolidation_marker(memo) is None:
                        break
                    sialib._recover_before_pulse(memo, store)
                    still_pending = \
                        sialib._pending_consolidation_marker(memo) is not None
                    live = [os.path.exists(path) for path in sources]
                    if still_pending and live in ([False, True], [True, False]):
                        saw_one_removed_while_pending = True
                    if still_pending and live == [False, False]:
                        saw_all_removed_while_pending = True
                    if still_pending:
                        self.assertNotIn(
                            "applied_at",
                            sialib._pending_consolidation_marker(memo))

            self.assertTrue(saw_one_removed_while_pending)
            self.assertTrue(saw_all_removed_while_pending)
            self.assertFalse(any(os.path.exists(path) for path in sources))
            self.assertIsNone(sialib._pending_consolidation_marker(memo))
            self.assertEqual(sialib._consolidation_scan_debt(), "")
            self.assertEqual(settled, ["pending"])
            epoch = sialib.corpus_path(
                sialib._epoch_slug_for_day("org", "2026-01-05"))
            with open(epoch, encoding="utf-8") as stream:
                epoch_text = stream.read()
            self.assertIn("2026-01-05", epoch_text)
            self.assertIn("2026-01-06", epoch_text)

            readiness_patches = (
                mock.patch.object(
                    sialib, "corpus_owner",
                    side_effect=lambda: contextlib.nullcontext()),
                mock.patch.object(sialib, "load_memo", return_value=memo),
                mock.patch.object(
                    sialib, "_thought_recovery_debt", return_value=""),
                mock.patch.object(
                    sialib, "_graph_projection_debt", return_value=""),
                mock.patch.object(
                    sialib.siamind, "load_mind", return_value={}),
                mock.patch.object(
                    sialib.siatakes, "natural_history_recovery_required",
                    return_value=False),
                mock.patch.object(
                    sialib.siatakes, "grade_recovery_required",
                    return_value=False),
                mock.patch.object(
                    sialib.siatakes, "take_migration_required",
                    return_value=False),
                mock.patch.object(
                    sialib.siatakes, "intent_history_required",
                    return_value=False),
            )
            with contextlib.ExitStack() as stack:
                for patcher in readiness_patches:
                    stack.enter_context(patcher)
                self.assertEqual(sialib.memory_readiness(), (True, ""))

    def test_cutoff_rollover_waits_for_incomplete_generation_suffix(self):
        sialib = _load(
            "sialib_epoch_cutoff_rollover", os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as d:
            sialib.CORPUS = d
            old_mind_path = sialib.siamind.MIND_PATH
            old_window = sialib.siamind.EPISODIC_DAYS
            sialib.siamind.MIND_PATH = os.path.join(d, "mind.json")
            sialib.siamind.EPISODIC_DAYS = 1
            self.addCleanup(
                setattr, sialib.siamind, "MIND_PATH", old_mind_path)
            self.addCleanup(
                setattr, sialib.siamind, "EPISODIC_DAYS", old_window)
            subprocess.run(["git", "init", "-q", d], check=True)
            event_dir = os.path.join(d, "events", "org")
            os.makedirs(event_dir)
            sources = []
            for day in ("2026-01-05", "2026-01-06"):
                path = os.path.join(event_dir, day + ".md")
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write(
                        f'---\ntype: event-day\ntitle: "{day}"\n'
                        f'tags: [org]\ndate: {day}\n'
                        'sia_counts: {"obs": 1}\n---\n# org\n\n'
                        f'## Log\n- {day}\n\n## Timeline\n- held\n')
                sources.append(path)
            sialib.siamind.save_mind({"nodes": {}, "edges": {}})
            subprocess.run(
                ["git", "-C", d, "-c", "user.email=t@t", "-c",
                 "user.name=t", "add", "-A"], check=True)
            subprocess.run(
                ["git", "-C", d, "-c", "user.email=t@t", "-c",
                 "user.name=t", "commit", "-qm", "sources"], check=True)
            before_rollover = datetime.datetime(
                2026, 8, 30, tzinfo=datetime.timezone.utc)
            after_rollover = datetime.datetime(
                2026, 8, 31, tzinfo=datetime.timezone.utc)
            before_cutoff = (before_rollover - datetime.timedelta(
                days=sialib.siamind.EPISODIC_DAYS)).strftime("%Y-%m-%d")
            after_cutoff = (after_rollover - datetime.timedelta(
                days=sialib.siamind.EPISODIC_DAYS)).strftime("%Y-%m-%d")
            with mock.patch.object(sialib, "MAX_SOURCE_SCAN_ENTRIES", 1), \
                    mock.patch.object(
                        sialib, "utcnow", return_value=before_rollover):
                self.assertEqual(sialib.consolidate_corpus(), (0, 0, 0))
            state = sialib._load_consolidation_scan(before_cutoff)
            generation = state["generation"]
            self.assertEqual(state["phase"], "scan")
            self.assertTrue(state["queue"])
            self.assertTrue(all(os.path.exists(path) for path in sources))

            # The new day's wider cutoff must not discard the durable suffix.
            pinned = sialib._load_consolidation_scan(after_cutoff)
            self.assertEqual(pinned["generation"], generation)
            self.assertEqual(pinned["cutoff"], before_cutoff)
            self.assertEqual(pinned["queue"], state["queue"])
            self.assertTrue(all(os.path.exists(path) for path in sources))

            with mock.patch.object(sialib, "MAX_SOURCE_SCAN_ENTRIES", 1), \
                    mock.patch.object(
                        sialib, "utcnow", return_value=after_rollover):
                for _attempt in range(sialib.MAX_EVENT_LOOKUP_PAGES):
                    sialib.consolidate_corpus()
                    if not any(os.path.exists(path) for path in sources):
                        break
            self.assertFalse(any(os.path.exists(path) for path in sources))
            epoch = sialib.corpus_path(
                sialib._epoch_slug_for_day("org", "2026-01-05"))
            self.assertTrue(os.path.exists(epoch))
            with open(epoch, encoding="utf-8") as stream:
                text = stream.read()
            self.assertIn("2026-01-05", text)
            self.assertIn("2026-01-06", text)

            # Finish the deletion-triggered conservative rescan at its pinned
            # cutoff, then (and only then) admit the later cutoff generation.
            with mock.patch.object(sialib, "MAX_SOURCE_SCAN_ENTRIES", 1), \
                    mock.patch.object(
                        sialib, "utcnow", return_value=before_rollover):
                for _attempt in range(sialib.MAX_EVENT_LOOKUP_PAGES):
                    sialib.consolidate_corpus()
                    completed = sialib._load_consolidation_scan(
                        before_cutoff)
                    if completed["phase"] == "complete" \
                            and not completed["pending_days"] \
                            and not completed["claims"]:
                        break
            self.assertEqual(completed["phase"], "complete")
            completed_generation = completed["generation"]
            rolled = sialib._load_consolidation_scan(after_cutoff)
            self.assertNotEqual(rolled["generation"], completed_generation)
            self.assertEqual(rolled["cutoff"], after_cutoff)
            self.assertEqual(rolled["phase"], "scan")


class HealHoldRate(unittest.TestCase):
    """Auto-proposed take confidence is arithmetic over the corpus's own
    heal history — thin history falls to the prior, never a model."""

    def _mk(self, d, days):
        droot = os.path.join(d, "events/sekhmet")
        os.makedirs(droot, exist_ok=True)
        for day in days:
            with open(os.path.join(droot, day + ".md"), "w") as stream:
                stream.write(
                    "# sekhmet\n- 01:00Z outcome OUTCOME:restart_wireplumber "
                    "- ok\n")

    def test_hold_rate_arithmetic(self):
        st = _load("siatakes_h", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            # heal 01-05 repeats on 01-08 (broken); the other three hold
            self._mk(d, ["2026-01-05", "2026-01-08", "2026-02-01",
                         "2026-03-01"])
            conf, judged, held = st.heal_hold_rate("restart_wireplumber",
                                                   corpus=d)
            self.assertEqual((judged, held), (4, 3))
            self.assertAlmostEqual(conf, 0.75)

    def test_thin_history_prior(self):
        st = _load("siatakes_h2", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            self._mk(d, ["2026-01-05"])
            conf, judged, held = st.heal_hold_rate("restart_wireplumber",
                                                   corpus=d)
            self.assertEqual(conf, st.HEAL_PRIOR)


class AutoPropose(unittest.TestCase):
    """Heals become PROPOSALS in the queue — never committed takes — and
    the same action is not proposed twice while one is pending."""

    class Ev:
        def __init__(self, organ, summary):
            self.organ, self.summary = organ, summary

    def test_propose_and_dedup(self):
        st = _load("siatakes_a", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            st.CORPUS = d
            st.TAKES_DIR = os.path.join(d, "takes")
            state = os.path.join(d, "state")
            os.makedirs(state)
            evs = [self.Ev("sekhmet", "OUTCOME:restart_wireplumber - ok"),
                   self.Ev("pacman", "OUTCOME:not_a_heal ok"),
                   self.Ev("sekhmet", "INTENT:restart_wireplumber - -")]
            p1 = st.auto_propose_heals(evs, state)
            self.assertEqual(len(p1), 1)
            self.assertIn("`restart_wireplumber`", p1[0]["claim"])
            self.assertTrue(p1[0]["proposed"].startswith("auto:heal-hold"))
            # queued now -> second pulse with same heal proposes nothing
            p2 = st.auto_propose_heals(evs, state)
            self.assertEqual(p2, [])
            # queue holds exactly one; no take page was minted
            with open(os.path.join(state, "take-proposals.json")) as stream:
                q = json.load(stream)
            self.assertEqual(len(q), 1)
            self.assertFalse(os.path.isdir(st.TAKES_DIR))

    def test_hyphenated_action_never_truncates(self):
        st = _load("siatakes_a2", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            st.CORPUS = d
            st.TAKES_DIR = os.path.join(d, "takes")
            state = os.path.join(d, "state")
            os.makedirs(state)
            # "ok" inside the action name must not truncate the capture
            p = st.auto_propose_heals(
                [self.Ev("sekhmet", "OUTCOME:probe-ok-net unit ok")],
                state)
            self.assertEqual(len(p), 1)
            self.assertIn("`probe-ok-net`", p[0]["claim"])

    def test_locked_proposals_serializes(self):
        st = _load("siatakes_l", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            def proposal(claim):
                return {"claim": claim, "confidence": 0.7,
                        "deadline": "2030-01-01", "domain": "test",
                        "source": "sia/cortex", "proposed": "unit"}
            st.locked_proposals(d, lambda cur: cur + [proposal("a")])
            out = st.locked_proposals(
                d, lambda cur: cur + [proposal("b")])
            self.assertEqual([p["claim"] for p in out], ["a", "b"])


def _intent_page(st):
    for name in os.listdir(st.INTENTS_DIR):
        if name.endswith(".md"):
            return os.path.join(st.INTENTS_DIR, name)
    raise AssertionError("no intent page")


class Intents(unittest.TestCase):
    """Prospective memory: create, surface by deadline, close on the
    operator's word only."""

    def test_lifecycle(self):
        st = _load("siatakes_i", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            st.CORPUS = d
            st.INTENTS_DIR = os.path.join(d, "intents")
            it = st.create_intent("rotate ledger keys", "2099-01-01")
            self.assertEqual(it["status"], "open")
            opened = st.open_intents()
            self.assertEqual(len(opened), 1)
            self.assertGreater(opened[0]["days_left"], 0)
            done = st.close_intent(it["id"][:6], "rotated")
            self.assertEqual(done["status"], "done")
            self.assertEqual(st.open_intents(), [])
            with open(_intent_page(st)) as stream:
                body = stream.read()
            self.assertIn("tags: [intent, done]", body)

    def test_bad_date_raises(self):
        st = _load("siatakes_i2", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            st.CORPUS = d
            st.INTENTS_DIR = os.path.join(d, "intents")
            with self.assertRaises(ValueError):
                st.create_intent("x", "not-a-date")

    def test_non_ascii_and_backslash_survive_close(self):
        # regression: re.sub once treated the JSON as a template — em
        # dashes crashed the close and backslashes were silently halved
        st = _load("siatakes_i3", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            st.CORPUS = d
            st.INTENTS_DIR = os.path.join(d, "intents")
            it = st.create_intent("réviser — clean C:\\temp \\d dir",
                                  "2099-01-01")
            done = st.close_intent(it["id"][:6], "done — rotated ☑")
            self.assertEqual(done["status"], "done")
            self.assertEqual(done["text"], "réviser — clean C:\\temp \\d dir")
            # page must round-trip: reload sees the closed intent intact
            loaded = st.load_intents()
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["text"], done["text"])
            self.assertEqual(loaded[0]["note"], "done — rotated ☑")


class Coincidence(unittest.TestCase):
    """Two organs spiking in the same window is an observation; the
    thought states the coincidence and the sighting count, no cause."""

    def test_pairs_counted(self):
        sialib = _load("sialib_c", os.path.join(BIN, "sialib.py"))
        mind = {}
        f1 = [("journal", "spike", "x"), ("pacman", "spike", "y"),
              ("jackal", "absence", "z")]
        out = sialib.coincidence_findings(mind, f1, now=1000.0)
        self.assertEqual(len(out), 1)
        self.assertIn("first sighting", out[0][0])
        self.assertIn("not a cause", out[0][0])
        self.assertEqual(sorted(out[0][1]),
                         ["organs/journal", "organs/pacman"])
        out2 = sialib.coincidence_findings(mind, f1, now=2000.0)
        self.assertIn("2nd sighting", out2[0][0])
        self.assertEqual(mind["coincide"]["journal|pacman"]["n"], 2)

    def test_single_organ_none(self):
        sialib = _load("sialib_c2", os.path.join(BIN, "sialib.py"))
        self.assertEqual(sialib.coincidence_findings(
            {}, [("journal", "spike", "x")], now=1.0), [])


class DomainEdgeInference(unittest.TestCase):
    """SIA's schema-pack regexes type explicit domain wikilinks without
    depending on gbrain's person/company gazetteer."""

    def setUp(self):
        self.sialib = _load("sialib_edges", os.path.join(BIN, "sialib.py"))
        self.tmp = tempfile.TemporaryDirectory()
        self.sialib.CORPUS = self.tmp.name
        pack = os.path.join(REPO, "schema-pack", "pack.yaml")
        self.rules, self.entity_types = \
            self.sialib.load_domain_edge_spec(pack)

    def tearDown(self):
        self.tmp.cleanup()

    def _page(self, slug, page_type, body, tags=None, origin=None):
        path = os.path.join(self.tmp.name, slug + ".md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tag_line = f"tags: [{', '.join(tags)}]\n" if tags else ""
        origin_line = f"origin: {origin}\n" if origin else ""
        with open(path, "w") as f:
            f.write(f"---\ntype: {page_type}\ntitle: test\n"
                    f"{tag_line}{origin_line}---\n{body}")

    def _edges(self, source):
        return [e for e in self.sialib.corpus_edges(
            self.rules, self.entity_types, [source])
                if e["from_slug"] == source]

    def test_every_declared_rule_types_its_record(self):
        self.assertEqual([name for name, _ in self.rules], [
            "verified_by", "healed", "crashed", "upgraded", "refused"])
        self._page("events/domain", "event-day", """# domain

- chain evidence pass [[organs/aegis]]
- OUTCOME:restart_audio ok [[units/audio]]
- process dumped core [[units/worker]]
- installed: [[packages/widget]]
- declined to answer [[organs/jackal]]
- ordinary observation [[organs/journal]]
""")
        got = {e["to_slug"]: e["link_type"]
               for e in self._edges("events/domain")}
        self.assertEqual(got, {
            "organs/aegis": "verified_by",
            "units/audio": "healed",
            "units/worker": "crashed",
            "packages/widget": "upgraded",
            "organs/jackal": "refused",
            "organs/journal": "mentions",
        })

    def test_link_names_cannot_mint_relations_or_leak_across_records(self):
        self._page("events/scoped", "event-day", """# scoped

- cataloged [[skills/diagnose-crash]] [[packages/refusal-kit]]
- process dumped core [[units/failed-worker]]
- ordinary observation [[units/plain-worker]]
""")
        got = {e["to_slug"]: e["link_type"]
               for e in self._edges("events/scoped")}
        self.assertEqual(got["skills/diagnose-crash"], "mentions")
        self.assertEqual(got["packages/refusal-kit"], "mentions")
        self.assertEqual(got["units/failed-worker"], "crashed")
        self.assertEqual(got["units/plain-worker"], "mentions")

    def test_link_only_evidence_line_inherits_preceding_prose(self):
        self._page("thoughts/crash", "thought", """# crash

The worker dumped core.

[[organs/journal]] [[units/systemd-coredump]]
""", tags=["thought", "crash"], origin="derived")
        self.assertEqual(
            {e["link_type"] for e in self._edges("thoughts/crash")},
            {"crashed"})

    def test_model_and_legacy_safety_thoughts_stay_neutral(self):
        for suffix, origin in (("model", "model"), ("legacy", None)):
            slug = f"thoughts/{suffix}-integrity"
            self._page(
                slug, "thought",
                "chain verified by [[organs/aegis]]\n",
                tags=["thought", "integrity"], origin=origin)
            self.assertEqual(
                {edge["link_type"] for edge in self._edges(slug)},
                {"mentions"})

    def test_entity_descriptions_stay_neutral(self):
        self._page("organs/sekhmet", "organ",
                   "Self-healing fabric. Organ of [[sia/cortex]].\n")
        self._page("skills/diagnose-crash", "skill",
                   "Agent skill installed here. Watched by [[organs/skills]].\n")
        self.assertIn("skill", self.entity_types)
        for source in ("organs/sekhmet", "skills/diagnose-crash"):
            self.assertEqual(
                {e["link_type"] for e in self._edges(source)}, {"mentions"})

    def test_model_and_commitment_pages_cannot_mint_typed_relations(self):
        for page_type in ("note", "synthesis", "take", "intent"):
            slug = f"{page_type}s/untrusted"
            self._page(slug, page_type,
                       "A model says this crashed [[units/critical]].\n")
            self.assertEqual(
                {e["link_type"] for e in self._edges(slug)}, {"mentions"})

    def test_take_grade_links_never_enter_the_graph(self):
        self._page("takes/legacy", "take", """# take

Operator-approved context [[organs/sekhmet]].

## Grade · 2026-08-30T12:00:00Z

**TRUE** — model-assisted.

Legacy model prose [[units/forged]].
""")
        self.assertEqual(
            {(edge["to_slug"], edge["link_type"])
             for edge in self._edges("takes/legacy")},
            {("organs/sekhmet", "mentions")})

    def test_quoted_missing_and_unknown_types_fail_closed(self):
        path = os.path.join(self.tmp.name, "notes", "quoted.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as stream:
            stream.write('---\ntype: "note"\n---\n'
                         'crashed [[units/quoted]]\n')
        for slug, frontmatter in (
                ("unknown/page", "type: alien"),
                ("missing/page", "title: no type")):
            target = os.path.join(self.tmp.name, slug + ".md")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w") as stream:
                stream.write(f"---\n{frontmatter}\n---\n"
                             "healed [[units/target]]\n")
        for source in ("notes/quoted", "unknown/page", "missing/page"):
            self.assertEqual(
                {edge["link_type"] for edge in self._edges(source)},
                {"mentions"})

    def test_snapshot_preserves_distinct_relations_for_same_pair(self):
        old_graph = self.sialib.GRAPH_PATH
        self.sialib.GRAPH_PATH = os.path.join(self.tmp.name, "graph.json")
        pages = [
            {"slug": "events/day", "type": "event-day", "title": "day",
             "updated_at": "2099-01-01T00:00:00Z"},
            {"slug": "units/x", "type": "unit", "title": "x",
             "updated_at": "2099-01-01T00:00:00Z"},
        ]
        old_list = self.sialib.gbrain_all_pages
        old_edges = self.sialib.corpus_edges
        self.sialib.gbrain_all_pages = lambda: (pages, True, None)
        self.sialib.corpus_edges = lambda *_args: [
            {"from_slug": "events/day", "to_slug": "units/x",
             "link_type": "crashed", "context": "crashed"},
            {"from_slug": "events/day", "to_slug": "units/x",
             "link_type": "healed", "context": "healed"},
            {"from_slug": "events/day", "to_slug": "units/x",
             "link_type": "mentions", "context": "generic"},
        ]
        try:
            self.sialib.export_graph()
            with open(self.sialib.GRAPH_PATH) as stream:
                graph = json.load(stream)
            self.assertEqual({edge["t"] for edge in graph["edges"]},
                             {"crashed", "healed"})
        finally:
            self.sialib.gbrain_all_pages = old_list
            self.sialib.corpus_edges = old_edges
            self.sialib.GRAPH_PATH = old_graph

    def test_unreadable_corpus_page_marks_graph_snapshot_partial(self):
        self._page("events/unreadable", "event-day",
                   "observed [[organs/journal]]\n")
        path = os.path.join(self.tmp.name, "events", "unreadable.md")
        old_graph = self.sialib.GRAPH_PATH
        self.sialib.GRAPH_PATH = os.path.join(self.tmp.name, "graph.json")
        pages = [{"slug": "events/unreadable", "type": "event-day",
                  "title": "unreadable",
                  "updated_at": "2099-01-01T00:00:00Z"}]
        real_read = self.sialib._read_graph_corpus_page

        def refuse(slug):
            if slug == "events/unreadable":
                raise OSError("simulated read refusal")
            return real_read(slug)

        try:
            with mock.patch.object(self.sialib, "gbrain_all_pages",
                                   return_value=(pages, True, None)), \
                    mock.patch.object(
                        self.sialib, "_read_graph_corpus_page",
                        side_effect=refuse):
                self.sialib.export_graph(require_complete=False)
            with open(self.sialib.GRAPH_PATH) as stream:
                graph = json.load(stream)
            self.assertFalse(graph["snapshot"]["complete"])
            self.assertIn("corpus_edges", graph["snapshot"]["failed_ops"])
            self.assertEqual(graph["edges"], [])
        finally:
            self.sialib.GRAPH_PATH = old_graph

        for kind in ("note", "ponder", "grade", "take", "intent",
                     "association"):
            slug = f"thoughts/untrusted-{kind}"
            self._page(slug, "thought",
                       "A derived statement says this crashed "
                       "[[units/critical]].\n",
                       tags=["thought", kind])
            self.assertEqual(
                {e["link_type"] for e in self._edges(slug)}, {"mentions"})

    def test_typed_occurrence_suppresses_generic_duplicate(self):
        self._page("events/packages", "event-day", """# packages

See [[packages/widget]].
- installed: [[packages/widget]]
""")
        matches = [e for e in self._edges("events/packages")
                   if e["to_slug"] == "packages/widget"]
        self.assertEqual([edge["link_type"] for edge in matches],
                         ["upgraded"])

    def test_distinct_typed_relations_survive_mention_suppression(self):
        self._page("events/lifecycle", "event-day", """# lifecycle

- process dumped core [[units/worker]]
- OUTCOME:restart_worker ok [[units/worker]]
- ordinary observation [[units/worker]]
""")
        matches = [e for e in self._edges("events/lifecycle")
                   if e["to_slug"] == "units/worker"]
        self.assertEqual({edge["link_type"] for edge in matches},
                         {"crashed", "healed"})

    def test_unsafe_pack_regex_fails_closed(self):
        pack = os.path.join(self.tmp.name, "unsafe.yaml")
        with open(pack, "w") as f:
            f.write("""api_version: gbrain-schema-pack-v1
name: unsafe
page_types: []
link_types:
  - name: bad
    inference:
      regex: "(a+)+$"
""")
        with self.assertRaisesRegex(ValueError, "unsafe domain regex"):
            self.sialib.load_domain_edge_spec(pack)

    def test_ambiguous_alternation_repeat_bypass_fails_closed(self):
        pack = os.path.join(self.tmp.name, "ambiguous-repeat.yaml")
        with open(pack, "w") as f:
            f.write("""api_version: gbrain-schema-pack-v1
name: unsafe
page_types: []
link_types:
  - name: bad
    inference:
      regex: "(a|aa)+$"
""")
        with self.assertRaisesRegex(ValueError, "unsafe domain regex"):
            self.sialib.load_domain_edge_spec(pack)

    def test_schema_pack_symlink_is_refused_without_following(self):
        target = os.path.join(self.tmp.name, "pack-target.yaml")
        with open(target, "w", encoding="utf-8") as stream:
            stream.write("link_types:\n")
        link = os.path.join(self.tmp.name, "pack-link.yaml")
        os.symlink(target, link)
        with self.assertRaises(OSError):
            self.sialib.load_domain_edge_spec(link)

    def test_schema_pack_newline_free_byte_overflow_is_refused(self):
        pack = os.path.join(self.tmp.name, "oversize.yaml")
        # JACKAL status=exact: parsed=65536+1, exact=65537. Exact rational
        # arithmetic outside the Lean certificate chain (NOT formal-bounded).
        with open(pack, "wb") as stream:
            stream.write(b"x" * (self.sialib.MAX_SCHEMA_PACK_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "bounded regular file"):
            self.sialib.load_domain_edge_spec(pack)

    def test_schema_pack_physical_line_aggregate_is_bounded(self):
        pack = os.path.join(self.tmp.name, "many-lines.yaml")
        # JACKAL status=exact: parsed=4096+1, exact=4097. Exact rational
        # arithmetic outside the Lean certificate chain (NOT formal-bounded).
        with open(pack, "wb") as stream:
            stream.write(
                b"\n" * (self.sialib.MAX_SCHEMA_PACK_LINES + 1))
        with self.assertRaisesRegex(ValueError, "line limit"):
            self.sialib.load_domain_edge_spec(pack)

    def test_schema_pack_rule_aggregate_is_bounded(self):
        pack = os.path.join(self.tmp.name, "many-rules.yaml")
        # JACKAL status=exact: parsed=256+1, exact=257. Exact rational
        # arithmetic outside the Lean certificate chain (NOT formal-bounded).
        with open(pack, "w", encoding="utf-8") as stream:
            stream.write("page_types: []\nlink_types:\n")
            for index in range(self.sialib.MAX_DOMAIN_EDGE_RULES + 1):
                stream.write(
                    f"  - name: relation{index}\n"
                    "    inference:\n"
                    "      regex: ok\n")
        with self.assertRaisesRegex(ValueError, "inference-rule limit"):
            self.sialib.load_domain_edge_spec(pack)

    def test_schema_pack_entity_aggregate_is_bounded(self):
        pack = os.path.join(self.tmp.name, "many-entities.yaml")
        with open(pack, "w", encoding="utf-8") as stream:
            stream.write("page_types:\n")
            for index in range(self.sialib.MAX_DOMAIN_ENTITY_TYPES + 1):
                stream.write(
                    f"  - name: entity{index}\n"
                    "    primitive: entity\n")
            stream.write(
                "link_types:\n"
                "  - name: relation\n"
                "    inference:\n"
                "      regex: ok\n")
        with self.assertRaisesRegex(ValueError, "entity-type limit"):
            self.sialib.load_domain_edge_spec(pack)

    def test_refused_schema_pack_keeps_mentions_and_marks_partial(self):
        invalid = os.path.join(self.tmp.name, "invalid-pack.yaml")
        with open(invalid, "wb") as stream:
            stream.write(b"\xff")
        self._page("events/day", "event-day",
                   "crashed [[units/worker]]\n")
        self._page("units/worker", "unit", "worker\n")
        old_graph = self.sialib.GRAPH_PATH
        self.sialib.GRAPH_PATH = os.path.join(self.tmp.name, "graph.json")
        pages = [
            {"slug": "events/day", "type": "event-day", "title": "day",
             "updated_at": "2099-01-01T00:00:00Z"},
            {"slug": "units/worker", "type": "unit", "title": "worker",
             "updated_at": "2099-01-01T00:00:00Z"},
        ]
        try:
            with mock.patch.dict(
                    os.environ, {"SIA_SCHEMA_PACK": invalid}), \
                    mock.patch.object(
                        self.sialib, "gbrain_all_pages",
                        return_value=(pages, True, None)):
                self.sialib.export_graph(require_complete=False)
            with open(self.sialib.GRAPH_PATH, encoding="utf-8") as stream:
                graph = json.load(stream)
            self.assertFalse(graph["snapshot"]["complete"])
            self.assertIn(
                "domain_link_rules", graph["snapshot"]["failed_ops"])
            self.assertEqual(
                [(edge["s"], edge["d"], edge["t"])
                 for edge in graph["edges"]],
                [("events/day", "units/worker", "mentions")])
        finally:
            self.sialib.GRAPH_PATH = old_graph

    def test_brain_sync_keeps_gazetteer_ner_lane(self):
        calls = []

        class Result:
            returncode = 0
            stdout = stderr = ""

        def fake_gbrain(args, timeout=None, json_out=False):
            calls.append(args)
            return Result()

        self.sialib.gbrain = fake_gbrain
        self.assertEqual(self.sialib.brain_sync(), (True, ""))
        self.assertEqual(calls[0], ["sync", "--source", "sia"])
        self.assertIn("--stale", calls[1])
        self.assertIn("--by-mention", calls[2])
        self.assertIn("--ner", calls[2])
        self.assertEqual(calls[2][calls[2].index("--source-id") + 1], "sia")


class BoundedGraphProjection(unittest.TestCase):
    """The resident graph advances bounded durable pages and fails closed."""

    def setUp(self):
        self.sialib = _load(
            "sialib_bounded_graph", os.path.join(BIN, "sialib.py"))
        self.tmp = tempfile.TemporaryDirectory()
        self.corpus = os.path.join(self.tmp.name, "corpus")
        self.state = os.path.join(self.tmp.name, "state")
        os.makedirs(os.path.join(self.corpus, "events", "journal"))
        os.makedirs(self.state)
        self.sialib.STATE = self.state
        self.sialib.CORPUS = self.corpus
        self.sialib.GRAPH_PATH = os.path.join(self.state, "graph.json")
        self.sialib.LIFECYCLE_LOCK = os.path.join(
            self.state, "lifecycle.lock")
        self.sialib.LIFECYCLE_TOMBSTONE = os.path.join(
            self.state, "lifecycle-removed")

    def tearDown(self):
        self.tmp.cleanup()

    def _page(self, slug, title="page", page_type="event-day", body=None):
        path = os.path.join(self.corpus, slug + ".md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if body is None:
            body = "[[sia/cortex]]\n"
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(
                f"---\ntype: {page_type}\ntitle: "
                f"{json.dumps(title)}\n---\n{body}")

    def _graph(self):
        with open(self.sialib.GRAPH_PATH, encoding="utf-8") as stream:
            return json.load(stream)

    def test_directory_cookie_resumes_without_whole_corpus_materialization(self):
        self._page("events/journal/first")
        self._page("events/journal/second")
        pages, complete, failure = self.sialib.gbrain_all_pages(batch_size=1)
        self.assertFalse(complete)
        self.assertEqual(failure, "graph_projection_pending")
        self.assertLessEqual(len(pages), self.sialib.MAX_GRAPH_NODES)
        for _attempt in range(20):
            pages, complete, failure = self.sialib.gbrain_all_pages(
                batch_size=1)
            if complete:
                break
        self.assertTrue(complete, failure)
        self.assertEqual({page["slug"] for page in pages}, {
            "events/journal/first", "events/journal/second"})

    def test_root_genesis_readme_is_repository_metadata_not_a_page(self):
        with open(os.path.join(self.corpus, "README.md"), "w",
                  encoding="utf-8") as stream:
            stream.write("# SIA memory corpus\n")
        self._page("events/journal/first")

        for _attempt in range(20):
            pages, complete, failure = self.sialib.gbrain_all_pages(
                batch_size=1)
            if complete:
                break
        self.assertTrue(complete, failure)
        self.assertEqual(
            [page["slug"] for page in pages], ["events/journal/first"])

        state = self.sialib._load_graph_projection_state()
        state["failed_ops"] = [self.sialib.LEGACY_GRAPH_README_FAILURE]
        self.sialib._save_graph_projection_state(state)
        migrated = self.sialib._load_graph_projection_state()
        self.assertEqual(migrated["failed_ops"], [])
        with open(self.sialib._graph_projection_state_path(),
                  encoding="utf-8") as stream:
            self.assertEqual(json.load(stream)["failed_ops"], [])

    def test_supported_mutation_restarts_projection_before_page_write(self):
        self._page("events/journal/first")
        for _attempt in range(20):
            _pages, complete, _failure = \
                self.sialib.gbrain_all_pages(batch_size=1)
            if complete:
                break
        self.assertTrue(complete)
        with self.sialib.corpus_mutation_barrier(lambda: None):
            self.sialib.write_page(
                "events/journal/second",
                ["type: event-day", self.sialib.fm_title("second")],
                "[[sia/cortex]]\n")
        state = self.sialib._load_graph_projection_state()
        self.assertEqual(state["phase"], "scan")
        self.assertEqual(state["candidates"], [])

    def test_projection_failure_and_metadata_state_are_bounded(self):
        state = self.sialib._fresh_graph_projection_state()
        with mock.patch.object(self.sialib, "MAX_GRAPH_SCAN_ENTRIES", 2):
            state["failed_ops"] = ["first", "second"]
            self.sialib._record_graph_failure(state, "third")
            self.assertEqual(len(state["failed_ops"]), 2)
            self.assertIn("graph_failure_capacity", state["failed_ops"])
        long_title = "x" * (self.sialib.MAX_SOURCE_NAME_CHARS + 1)
        self._page("events/journal/title", title=long_title)
        record, _frontmatter, _body = \
            self.sialib._read_graph_corpus_page("events/journal/title")
        self.assertLessEqual(
            len(record["title"]), self.sialib.MAX_SOURCE_NAME_CHARS)
        self._page(
            "events/journal/type", page_type=
            "x" * (self.sialib.MAX_SOURCE_NAME_CHARS + 1))
        with self.assertRaisesRegex(RuntimeError, "type is invalid"):
            self.sialib._read_graph_corpus_page("events/journal/type")
        origin_path = os.path.join(
            self.corpus, "events", "journal", "origin.md")
        with open(origin_path, "w", encoding="utf-8") as stream:
            stream.write(
                "---\ntype: event-day\norigin: evidence\n"
                "origin: model\n---\n[[sia/cortex]]\n")
        with self.assertRaisesRegex(RuntimeError, "origin is ambiguous"):
            self.sialib._read_graph_corpus_page("events/journal/origin")

    def test_recent_node_cap_is_complete_with_explicit_nonabsence_boundary(self):
        for index in range(self.sialib.MAX_GRAPH_NODES + 1):
            self._page(f"events/journal/recent-{index:04d}")

        pages, complete, failure = self.sialib.gbrain_all_pages()
        self.assertTrue(complete, failure)
        self.assertEqual(len(pages), self.sialib.MAX_GRAPH_NODES)
        self.assertEqual(self.sialib._graph_projection_debt(), "")

        nodes, _edges, pages_total = self.sialib.export_graph()
        graph = self._graph()
        self.assertEqual(nodes, self.sialib.MAX_GRAPH_NODES)
        self.assertGreater(pages_total, nodes)
        self.assertTrue(graph["snapshot"]["complete"])
        self.assertGreater(graph["snapshot"]["truncated"], 0)
        self.assertEqual(graph["snapshot"]["omitted_nodes"],
                         graph["snapshot"]["truncated"])
        self.assertEqual(graph["snapshot"]["omitted_edges"], 0)
        self.assertFalse(
            graph["snapshot"]["omissions_imply_absence"])
        self.assertEqual(graph["snapshot"]["failed_ops"], [])
        self.assertEqual(self.sialib._graph_projection_debt(), "")
        # The display omission does not delete or rename the source page; the
        # corpus/PGLite lane remains the authoritative recall surface.
        displayed = {node["id"] for node in graph["nodes"]}
        omitted = [slug for slug in (
            f"events/journal/recent-{index:04d}"
            for index in range(self.sialib.MAX_GRAPH_NODES + 1))
                   if slug not in displayed]
        self.assertTrue(omitted)
        self.assertTrue(os.path.isfile(
            os.path.join(self.corpus, omitted[0] + ".md")))

    def test_dense_valid_edge_window_caps_without_publication_debt(self):
        slugs = [f"events/journal/dense-{index:04d}"
                 for index in range(self.sialib.MAX_GRAPH_NODES)]
        bodies = {slug: [] for slug in slugs}
        admitted = 0
        for source in slugs:
            for target in slugs:
                if source == target:
                    continue
                bodies[source].append(f"[[{target}]]")
                admitted += 1
                if admitted > self.sialib.MAX_GRAPH_EDGES:
                    break
            if admitted > self.sialib.MAX_GRAPH_EDGES:
                break
        self.assertGreater(admitted, self.sialib.MAX_GRAPH_EDGES)
        for slug in slugs:
            self._page(slug, body="\n".join(bodies[slug]) + "\n")

        pages, complete, failure = self.sialib.gbrain_all_pages()
        self.assertTrue(complete, failure)
        self.assertEqual(len(pages), self.sialib.MAX_GRAPH_NODES)
        _nodes, edges, _pages_total = self.sialib.export_graph()
        graph = self._graph()
        self.assertTrue(graph["snapshot"]["complete"])
        self.assertEqual(edges, self.sialib.MAX_GRAPH_EDGES)
        self.assertGreater(graph["snapshot"]["omitted_edges"], 0)
        self.assertEqual(graph["snapshot"]["omitted_nodes"], 0)
        self.assertFalse(
            graph["snapshot"]["omissions_imply_absence"])
        self.assertEqual(graph["snapshot"]["failed_ops"], [])
        self.assertEqual(self.sialib._graph_projection_debt(), "")

    def test_duplicate_and_aged_out_links_cannot_exhaust_display_edge_cap(self):
        aged_body = "\n".join(
            f"[[external/aged-{index:05d}]]"
            for index in range(self.sialib.MAX_GRAPH_EDGES + 1)) + "\n"
        duplicate_body = (
            "[[events/journal/target-a]]\n"
            * (self.sialib.MAX_GRAPH_EDGES + 1)
            + "[[events/journal/target-b]]\n")
        self._page("events/journal/aged", body=aged_body)
        self._page("events/journal/source", body=duplicate_body)
        self._page("events/journal/target-a", body="no links\n")
        self._page("events/journal/target-b", body="no links\n")
        pages = [
            {"slug": "events/journal/aged", "type": "event-day",
             "title": "aged", "updated_at": "2000-01-01T00:00:00Z"},
            {"slug": "events/journal/source", "type": "event-day",
             "title": "source", "updated_at": "2099-01-01T00:00:00Z"},
            {"slug": "events/journal/target-a", "type": "event-day",
             "title": "target a", "updated_at": "2099-01-01T00:00:00Z"},
            {"slug": "events/journal/target-b", "type": "event-day",
             "title": "target b", "updated_at": "2099-01-01T00:00:00Z"},
        ]
        with mock.patch.object(
                self.sialib, "gbrain_all_pages",
                return_value=(pages, True, None)):
            self.sialib.export_graph()
        graph = self._graph()
        self.assertTrue(graph["snapshot"]["complete"])
        self.assertEqual(graph["snapshot"]["omitted_edges"], 0)
        self.assertEqual(
            {(edge["s"], edge["d"]) for edge in graph["edges"]},
            {("events/journal/source", "events/journal/target-a"),
             ("events/journal/source", "events/journal/target-b")})
        self.assertNotIn(
            "events/journal/aged",
            {node["id"] for node in graph["nodes"]})

    def test_graph_publication_drains_pending_but_not_permanent_or_churning_state(self):
        pending = self.sialib.GraphProjectionPending("pending")
        scanning = self.sialib._fresh_graph_projection_state()
        with mock.patch.object(
                self.sialib, "export_graph",
                side_effect=[pending, pending, (1, 2, 3)]) as export, \
                mock.patch.object(
                    self.sialib, "_load_graph_projection_state",
                    return_value=scanning):
            self.assertEqual(
                self.sialib._export_graph_publication(), (1, 2, 3))
            self.assertEqual(export.call_count, 3)
        permanent = dict(scanning, phase="ready", queue=[],
                         failed_ops=["refused"])
        with mock.patch.object(
                self.sialib, "export_graph", side_effect=pending), \
                mock.patch.object(
                    self.sialib, "_load_graph_projection_state",
                    return_value=permanent), \
                self.assertRaises(self.sialib.GraphProjectionPending):
            self.sialib._export_graph_publication()
        with mock.patch.object(self.sialib, "MAX_EVENT_LOOKUP_PAGES", 2), \
                mock.patch.object(
                    self.sialib, "export_graph", side_effect=pending), \
                mock.patch.object(
                    self.sialib, "_load_graph_projection_state",
                    return_value=scanning), \
                self.assertRaisesRegex(
                    self.sialib.GraphProjectionPending,
                    "generation ceiling"):
            self.sialib._export_graph_publication()

    def test_first_light_converges_legacy_memory_authority(self):
        take_pending = mock.Mock(side_effect=[True, False])
        intent_pending = mock.Mock(return_value=False)
        with mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}), \
                mock.patch.object(
                    self.sialib.siatakes, "migrate_legacy_take_pages",
                    return_value=([], [])) as take_advance, \
                mock.patch.object(
                    self.sialib.siatakes, "advance_intent_history",
                    return_value=([], [])) as intent_advance, \
                mock.patch.object(
                    self.sialib.siatakes, "take_migration_required",
                    take_pending), \
                mock.patch.object(
                    self.sialib.siatakes, "intent_history_required",
                    intent_pending):
            self.sialib._reconcile_legacy_memory_authority({})
        self.assertEqual(take_advance.call_count, 2)
        self.assertEqual(intent_advance.call_count, 2)

    def test_first_light_legacy_authority_has_a_generation_ceiling(self):
        with mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}), \
                mock.patch.object(
                    self.sialib, "MAX_EVENT_LOOKUP_PAGES", 2), \
                mock.patch.object(
                    self.sialib.siatakes, "migrate_legacy_take_pages",
                    return_value=([], [])) as take_advance, \
                mock.patch.object(
                    self.sialib.siatakes, "advance_intent_history",
                    return_value=([], [])), \
                mock.patch.object(
                    self.sialib.siatakes, "take_migration_required",
                    return_value=True), \
                self.assertRaisesRegex(
                    RuntimeError, "backfill exceeded its generation ceiling"):
            self.sialib._reconcile_legacy_memory_authority({})
        self.assertEqual(take_advance.call_count, 2)

if __name__ == "__main__":
    unittest.main(verbosity=2)
