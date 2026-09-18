"""Frozen event-page rendering and byte-only publication.

The owner runs these tests strictly sequentially in isolated fixture roots.
The existing isolated EventEpochAdmissionIntegrity fixture supplies real Event,
source-day and bounded consolidation behavior. Its only allowed subprocesses
are private fixture Git calls; engine/model/keeper front doors are forbidden.

An independent plan pin is caller authority for that original producer plan,
not authentication of events or a proof that arbitrary supplied bytes are true.
Before-page bytes are retained, not reconstructed from their hashes. Existing
event-entry content follows the appender's splitlines delimiter policy: line
terminators are excluded, but entry text/IDs/semantics/payload/order are kept.
Whole unchanged pages retain their original bytes, including odd frontmatter.
This standalone bound does NOT reserve a complete live candidate/status/memo.
"""

import base64
import contextlib
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_corpus_version_capture as capture_tests
from tests import test_event_epoch_admission_integrity as retention_tests


PLAN_KEYS = {"schema", "organ", "date", "input_records", "day_slugs",
             "appended_event_ids", "admissions", "pages", "read_dependencies",
             "non_claims", "plan_sha256"}
PAGE_KEYS = {"slug", "write", "before", "raw_utf8_base64", "raw_bytes",
             "raw_sha256", "version_sha256", "origin"}
ADMISSION_KEYS = {"event_id", "semantic_id", "slug", "version_sha256", "disposition"}
GENERATION_KEYS = {"device", "inode", "mode", "uid", "gid", "nlink", "size",
                   "mtime_ns", "ctime_ns"}
DIRECTORY_KEYS = {"device", "inode", "mode", "uid", "gid"}
FILE_BEFORE_KEYS = {"generation", "raw_bytes", "raw_sha256"}
PAGE_BEFORE_KEYS = FILE_BEFORE_KEYS | {"raw_utf8_base64"}
RESULT_KEYS = {"schema", "status", "plan_sha256", "day_slugs", "appended_event_ids",
               "admissions", "page_versions", "non_claims"}
NON_CLAIMS = [
    "This bounded render plan binds controller-supplied normalized event records and observed corpus bytes; it does not authenticate source events or establish complete machine history.",
    "Page-byte publication is not a corpus commit, index synchronization, source cursor acknowledgment, live-loop candidate admission, status/memo readiness, or observed recall delivery.",
    "Retried publication preserves the original plan and append/admission roster; a matching target is not evidence that this attempt appended the event.",
    "Original retained page bytes and event-entry content/order remain bound; title/count/timeline regeneration does not preserve the whole old file as an unchanged prefix.",
]
REFUSALS = (RuntimeError, ValueError, OSError)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def own(plan):
    return digest(canonical({key: value for key, value in plan.items() if key != "plan_sha256"}))


def generation(info):
    return {"device": info.st_dev, "inode": info.st_ino, "mode": info.st_mode,
            "uid": info.st_uid, "gid": info.st_gid, "nlink": info.st_nlink,
            "size": info.st_size, "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns}


class _ModuleShim:
    def __init__(self, module, **overrides):
        self.module = module
        self.overrides = overrides

    def __getattr__(self, name):
        return self.overrides[name] if name in self.overrides else getattr(self.module, name)


class EventPageRenderPlan(unittest.TestCase):
    def setUp(self):
        self.fixture = retention_tests.EventEpochAdmissionIntegrity(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.corpus = Path(self.lib.CORPUS)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        # Actual owner and lifecycle operations stay inside this fixture,
        # rather than the shared process-isolated home used at import time.
        for name, relative in (
                ("HOME", "."), ("SHARE", "share"), ("BIN", "bin"),
                ("CORPUS_OWNER_LOCK", "state/corpus-owner.lock"),
                ("LIFECYCLE_LOCK", "state/lifecycle.lock"),
                ("LIFECYCLE_TOMBSTONE", "state/lifecycle-removed"),
                ("RESTORE_BARRIER_PATH", "restore/in-progress.json"),
                ("RESTORE_MASK_PATH", "restore/runtime-mask"),
                ("RESTORE_SUPERVISOR_PATH", "restore/supervisor.json")):
            self.stack.enter_context(mock.patch.object(
                self.lib, name, str(self.fixture.root / relative)))
        self.stack.enter_context(mock.patch.object(
            self.lib.siamind, "TOUCH_QUEUE", str(self.fixture.root / "state/touch-queue.jsonl")))
        for name in ("gbrain_call", "gbrain", "brain_sync", "ledger_append", "durable_ledger_append"):
            if hasattr(self.lib, name):
                self.stack.enter_context(mock.patch.object(
                    self.lib, name, side_effect=AssertionError("forbidden runtime front door: " + name)))
        for name in ("_prepare_event_page_plan", "_publish_event_page_plan"):
            self.assertTrue(callable(getattr(self.lib, name, None)), "missing event render-plan API: " + name)
        self.day = "2026-01-05"
        self.slug = "events/org/2026-01-05"

    def event(self, day=None, occurrence="native:admission:retained"):
        return self.fixture._event(self.day if day is None else day, occurrence)

    def prepare(self, events, *, day=None, organ="org"):
        return self.lib._prepare_event_page_plan(
            organ=organ, date=self.day if day is None else day, events=events)

    def publish(self, plan, *, expected=None):
        return self.lib._publish_event_page_plan(
            plan=plan, expected_plan_sha256=plan["plan_sha256"] if expected is None else expected)

    def raw(self, page):
        return base64.b64decode(page["raw_utf8_base64"], validate=True)

    def snapshot(self):
        result = {}
        for root, directories, files in os.walk(self.corpus, followlinks=False):
            for name in sorted(directories + files):
                path = Path(root) / name
                info = path.lstat()
                item = {"generation": generation(info)}
                if stat.S_ISREG(info.st_mode):
                    item["raw"] = path.read_bytes()
                elif stat.S_ISLNK(info.st_mode):
                    item["link"] = os.readlink(path)
                result[str(path.relative_to(self.corpus))] = item
        return result

    def entries(self, raw):
        text = raw.decode("utf-8")
        match = self.lib.FM_RE.match(text)
        self.assertIsNotNone(match)
        log = text[match.end():].split("## Timeline", 1)[0]
        if "## Log" in log:
            log = log.split("## Log", 1)[1]
        return [line for line in log.splitlines() if line.startswith("- ")]

    def assert_owned(self):
        self.assertGreater(self.lib._CORPUS_OWNER_DEPTH.get(), 0)
        held = os.fstat(self.lib._CORPUS_OWNER_FD.get())
        descriptor = os.open(self.lib.CORPUS_OWNER_LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            named = os.fstat(descriptor)
            self.assertEqual((held.st_dev, held.st_ino), (named.st_dev, named.st_ino))
            with self.assertRaises(BlockingIOError):
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(descriptor)

    def assert_owner_released(self):
        descriptor = os.open(self.lib.CORPUS_OWNER_LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def replace_same_bytes(self, source, retained_name):
        raw = source.read_bytes()
        mode = stat.S_IMODE(source.stat().st_mode)
        retained = self.fixture.root / retained_name
        source.rename(retained)
        source.write_bytes(raw)
        source.chmod(mode)
        self.assertEqual(source.read_bytes(), retained.read_bytes())
        self.assertNotEqual(generation(source.stat()), generation(retained.stat()))
        return retained

    def assert_plan(self, plan):
        self.assertEqual(set(plan), PLAN_KEYS)
        self.assertEqual(plan["schema"], "sia-event-page-render-plan-v1")
        self.assertEqual(plan["plan_sha256"], own(plan))
        self.assertEqual(plan["non_claims"], NON_CLAIMS)
        self.assertLessEqual(len(canonical(plan)), self.lib.MAX_STATE_JSON_BYTES)
        deps = plan["read_dependencies"]
        self.assertEqual(set(deps), {"schema", "corpus_identity", "directories", "files"})
        self.assertEqual(deps["schema"], "sia-event-page-read-dependencies-v1")
        self.assertEqual(set(deps["corpus_identity"]), DIRECTORY_KEYS)
        self.assertEqual(deps["corpus_identity"],
                         {key: generation(self.corpus.stat())[key] for key in DIRECTORY_KEYS})
        for field in ("directories", "files"):
            names = [row["relative"] for row in deps[field]]
            self.assertEqual(names, sorted(set(names)))
            for row in deps[field]:
                self.assertEqual(set(row), {"relative", "before"})
                self.assertFalse(Path(row["relative"]).is_absolute())
                self.assertNotIn("..", Path(row["relative"]).parts)
        for row in deps["directories"]:
            before = row["before"]
            path = self.corpus / row["relative"]
            if before is None:
                self.assertFalse(os.path.lexists(path))
                continue
            self.assertEqual(set(before), {"identity", "entries"})
            self.assertEqual(set(before["identity"]), DIRECTORY_KEYS)
            info = path.lstat()
            self.assertTrue(stat.S_ISDIR(info.st_mode))
            self.assertEqual(before["identity"], {key: generation(info)[key] for key in DIRECTORY_KEYS})
            if before["entries"] is not None:
                names = [entry["name"] for entry in before["entries"]]
                self.assertEqual(names, sorted(set(names)))
                for entry in before["entries"]:
                    self.assertEqual(set(entry), {"name", "generation"})
                    self.assertEqual(set(entry["generation"]), GENERATION_KEYS)
                self.assertEqual(before["entries"], [
                    {"name": child.name, "generation": generation(child.lstat())}
                    for child in sorted(path.iterdir(), key=lambda child: child.name)])
        files = {row["relative"]: row["before"] for row in deps["files"]}
        for relative, before in files.items():
            path = self.corpus / relative
            if before is None:
                self.assertFalse(os.path.lexists(path))
                continue
            self.assertEqual(set(before), FILE_BEFORE_KEYS)
            self.assertEqual(set(before["generation"]), GENERATION_KEYS)
            info = path.lstat()
            self.assertTrue(stat.S_ISREG(info.st_mode))
            self.assertEqual(info.st_uid, os.geteuid())
            self.assertEqual(info.st_nlink, 1)
            observed = path.read_bytes()
            self.assertEqual(before, {"generation": generation(info),
                                     "raw_bytes": len(observed), "raw_sha256": digest(observed)})
        slugs = [page["slug"] for page in plan["pages"]]
        self.assertEqual(slugs, sorted(set(slugs)))
        versions = {}
        for page in plan["pages"]:
            self.assertEqual(set(page), PAGE_KEYS)
            self.assertIs(type(page["write"]), bool)
            raw = self.raw(page)
            self.assertEqual(base64.b64encode(raw).decode("ascii"), page["raw_utf8_base64"])
            self.assertEqual(page["raw_bytes"], len(raw))
            self.assertEqual(page["raw_sha256"], digest(raw))
            projected = self.lib._corpus_page_version_from_bytes(slug=page["slug"], raw=raw)
            self.assertEqual(page["version_sha256"], projected["version_sha256"])
            self.assertEqual(page["origin"], projected["origin"])
            versions[page["slug"]] = page["version_sha256"]
            before = page["before"]
            self.assertIn(page["slug"] + ".md", files)
            if before is None:
                self.assertIsNone(files[page["slug"] + ".md"])
            else:
                self.assertEqual(set(before), PAGE_BEFORE_KEYS)
                old = self.raw(before)
                self.assertEqual(before["raw_bytes"], len(old))
                self.assertEqual(before["raw_sha256"], digest(old))
                self.assertEqual({key: before[key] for key in FILE_BEFORE_KEYS},
                                 files[page["slug"] + ".md"])
                if not page["write"]:
                    self.assertEqual(raw, old)
        seen = set()
        for admission in plan["admissions"]:
            self.assertEqual(set(admission), ADMISSION_KEYS)
            self.assertNotIn(admission["event_id"], seen)
            seen.add(admission["event_id"])
            self.assertEqual(admission["version_sha256"], versions[admission["slug"]])
            self.assertIn(admission["disposition"], {"appended", "retained-day", "retained-epoch"})
        records = {}
        for record in plan["input_records"]:
            event = self.lib._event_from_replay_record(record)
            self.assertEqual(self.lib._event_replay_record(event), record)
            if record["event_id"] in records:
                self.assertEqual(record["semantic_id"], records[record["event_id"]]["semantic_id"])
            else:
                records[record["event_id"]] = record
        self.assertEqual([row["event_id"] for row in plan["admissions"]], list(records))
        for admission in plan["admissions"]:
            self.assertEqual(admission["semantic_id"], records[admission["event_id"]]["semantic_id"])
        self.assertEqual(plan["appended_event_ids"], [row["event_id"] for row in plan["admissions"]
                                                   if row["disposition"] == "appended"])

    def assert_result(self, result, plan):
        self.assertEqual(set(result), RESULT_KEYS)
        self.assertEqual(result["schema"], "sia-event-page-render-publication-v1")
        self.assertEqual(result["status"], "page-bytes-published")
        for key in ("plan_sha256", "day_slugs", "appended_event_ids", "admissions", "non_claims"):
            self.assertEqual(result[key], plan[key])
        self.assertEqual(result["page_versions"], [
            {key: page[key] for key in ("slug", "raw_sha256", "version_sha256")}
            for page in plan["pages"]])
        self.assertLessEqual(len(canonical(result)), self.lib.MAX_STATE_JSON_BYTES)

    def assert_refused_without_writes(self, plan):
        before = self.snapshot()
        with mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("write before refusal")), \
                self.assertRaises(REFUSALS):
            self.publish(plan)
        self.assertEqual(self.snapshot(), before)

    def test_new_plan_is_readonly_and_publishes_frozen_render_without_rerender(self):
        event = self.event()
        before = self.snapshot()
        with mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("planner published bytes")), \
                mock.patch.object(self.lib, "_before_corpus_mutation", side_effect=AssertionError("planner invoked mutation barrier")):
            plan = self.prepare([event])
        self.assertEqual(self.snapshot(), before)
        self.assert_plan(plan)
        self.assertEqual(plan["input_records"], [self.lib._event_replay_record(event)])
        self.assertEqual(plan["day_slugs"], [self.slug])
        self.assertEqual(plan["appended_event_ids"], [self.lib.event_memory_identity(event)])
        self.assertEqual([row["disposition"] for row in plan["admissions"]], ["appended"])
        pinned = copy.deepcopy(plan)
        with mock.patch.object(self.lib, "_render_event_shard", side_effect=AssertionError("publisher rerendered")), \
                mock.patch.object(self.lib, "update_day_page", side_effect=AssertionError("publisher replanned")):
            result = self.publish(plan)
        self.assert_result(result, pinned)
        self.assertEqual(plan, pinned)
        for page in plan["pages"]:
            self.assertEqual(Path(self.lib.corpus_path(page["slug"])).read_bytes(), self.raw(page))

    def test_architecture_names_event_plan_ownership_and_its_publication_boundary(self):
        architecture = (retention_tests.REPO / "docs/ARCHITECTURE.md").read_text(encoding="utf-8")
        self.assertIn("`bin/siaeventplan.py`", architecture)
        self.assertIn("Event-day admission and occurrence indexing share this owner.", architecture)
        self.assertIn("_prepare_event_page_plan", architecture)
        self.assertIn("_publish_event_page_plan", architecture)
        self.assertIn("Page-byte publication is not live-loop admission", architecture)
        self.assertNotIn("Event-day admission, occurrence indexing,\ngeneric corpus publication", architecture)

    def test_helpers_acquire_real_owner_through_reads_projection_copies_writes_and_final_checks(self):
        self.fixture._source()
        event = self.event(occurrence="native:admission:new")
        phase, observed, written = ["prepare"], [], []
        actual_owner = self.lib.corpus_owner
        actual_read = self.lib._read_event_page
        actual_identity = self.lib._source_path_identity
        actual_projection = self.lib._corpus_page_version_from_bytes
        actual_write = self.lib.atomic_write

        def probe(boundary):
            self.assert_owned()
            observed.append((phase[0], boundary))

        @contextlib.contextmanager
        def owned():
            with actual_owner() as descriptor:
                probe("owner-enter")
                try:
                    yield descriptor
                finally:
                    probe("owner-exit")

        def read(*args, **kwargs):
            probe("read")
            result = actual_read(*args, **kwargs)
            probe("read-return")
            return result

        def identity(path, *args, **kwargs):
            in_corpus = os.path.commonpath((os.path.abspath(path), str(self.corpus))) == str(self.corpus)
            if in_corpus:
                probe("name-check")
            result = actual_identity(path, *args, **kwargs)
            if in_corpus:
                probe("readback-name-check" if written else "name-check-return")
            return result

        def project(*args, **kwargs):
            probe("projection")
            result = actual_projection(*args, **kwargs)
            probe("projection-return")
            return result

        def detach(*args, **kwargs):
            probe("copy")
            result = copy.deepcopy(*args, **kwargs)
            probe("copy-return")
            return result

        def write(path, data, **kwargs):
            probe("write")
            result = actual_write(path, data, **kwargs)
            written.append(os.fspath(path))
            probe("write-return")
            return result

        with mock.patch.object(self.lib, "corpus_owner", owned), \
                mock.patch.object(self.lib, "_read_event_page", side_effect=read), \
                mock.patch.object(self.lib, "_source_path_identity", side_effect=identity), \
                mock.patch.object(self.lib, "_corpus_page_version_from_bytes", side_effect=project), \
                mock.patch.object(self.lib, "copy", _ModuleShim(copy, deepcopy=detach)), \
                mock.patch.object(self.lib, "hashlib", capture_tests._HashShim(lambda _raw: probe("hash"))), \
                mock.patch.object(self.lib, "atomic_write", side_effect=write):
            plan = self.prepare([event])
            self.assert_owner_released()
            phase[0] = "publish"
            result = self.publish(plan)
            self.assert_owner_released()
        self.assert_plan_after_publication(result, plan)
        for operation in ("prepare", "publish"):
            for boundary in ("owner-enter", "projection", "hash", "owner-exit"):
                self.assertIn((operation, boundary), observed)
        self.assertIn(("prepare", "read"), observed)
        self.assertIn(("publish", "write"), observed)
        self.assertIn(("publish", "readback-name-check"), observed)

    def assert_plan_after_publication(self, result, plan):
        self.assert_result(result, plan)
        for page in plan["pages"]:
            self.assertEqual(Path(self.lib.corpus_path(page["slug"])).read_bytes(), self.raw(page))

    def test_helpers_are_reentrant_and_do_not_release_the_callers_real_owner(self):
        event = self.event()
        with self.lib.corpus_owner():
            held = self.lib._CORPUS_OWNER_FD.get()
            plan = self.prepare([event])
            self.assert_owned()
            self.assertEqual(self.lib._CORPUS_OWNER_FD.get(), held)
            result = self.publish(plan)
            self.assert_owned()
            self.assertEqual(self.lib._CORPUS_OWNER_FD.get(), held)
        self.assert_owner_released()
        self.assert_plan_after_publication(result, plan)

    def test_publication_result_is_detached_from_the_original_plan(self):
        self.fixture._source()
        plan = self.prepare([self.event(occurrence="native:admission:new")])
        original = copy.deepcopy(plan)
        result = self.publish(plan)
        self.assert_result(result, original)
        self.assertTrue(result["admissions"])
        self.assertTrue(result["page_versions"])
        result["admissions"][0]["slug"] = "caller-mutated-result"
        result["page_versions"][0]["raw_sha256"] = "caller-mutated-version"
        for field in ("day_slugs", "appended_event_ids", "admissions", "page_versions", "non_claims"):
            result[field].clear()
        self.assertEqual(plan, original)

    def test_legacy_update_dry_run_preserves_exact_return_triple_and_event_objects(self):
        self.fixture._source()
        replay = self.event("2026-01-07")
        new = self.event("2026-01-07", "native:admission:new")
        events = [replay, new]
        before = self.snapshot()
        legacy = self.lib.update_day_page("org", "2026-01-07", events, dry_run=True)
        self.assertIs(type(legacy), tuple)
        self.assertEqual(legacy, (["events/org/2026-01-07"], [new],
                                  [(replay, self.slug), (new, "events/org/2026-01-07")]))
        plan = self.prepare(events, day="2026-01-07")
        self.assert_plan(plan)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(plan["day_slugs"], legacy[0])
        self.assertEqual(plan["appended_event_ids"], [self.lib.event_memory_identity(event) for event in legacy[1]])
        self.assertEqual([(row["event_id"], row["slug"]) for row in plan["admissions"]],
                         [(self.lib.event_memory_identity(event), slug) for event, slug in legacy[2]])
        self.assertEqual(plan["input_records"], [self.lib._event_replay_record(event) for event in events])

    def test_preparation_does_not_cleanup_legacy_atomic_entries(self):
        event, source, _record = self.fixture._source()
        staging = source.parent / ".page.fixture.new"
        staging.write_bytes(b"retained legacy staging bytes\n")
        staging.chmod(0o600)
        before = self.snapshot()
        plan = self.prepare([event])
        self.assertEqual(self.snapshot(), before)
        self.assert_plan(plan)
        scan = next(row for row in plan["read_dependencies"]["directories"]
                    if row["relative"] == "events/org")
        self.assertIn(staging.name, [entry["name"] for entry in scan["before"]["entries"]])

    def test_complete_dependencies_include_unselected_historical_pages_and_absence_witnesses(self):
        _old, source, _record = self.fixture._source()
        _other, other, _other_record = self.fixture._source("2026-01-06", "native:admission:other")
        ignored = source.parent / "retained-nonauthority.txt"
        ignored.write_bytes(b"a scan member, not an event authority\n")
        event = self.event("2026-01-07", "native:admission:new")
        plan = self.prepare([event], day="2026-01-07")
        self.assert_plan(plan)
        files = {row["relative"]: row["before"] for row in plan["read_dependencies"]["files"]}
        for path in (source, other):
            self.assertEqual(files[str(path.relative_to(self.corpus))], {
                "generation": generation(path.stat()), "raw_bytes": len(path.read_bytes()),
                "raw_sha256": digest(path.read_bytes())})
        missing_index = self.lib._event_index_relative("org", self.lib.event_memory_identity(event))
        self.assertIn(missing_index, files)
        self.assertIsNone(files[missing_index])
        directories = {row["relative"]: row["before"] for row in plan["read_dependencies"]["directories"]}
        self.assertIsNotNone(directories["events/org"]["entries"])
        self.assertIn(ignored.name, [row["name"] for row in directories["events/org"]["entries"]])
        self.assertIn("epochs/org", directories)
        self.assertIsNone(directories["epochs/org"])

    def test_rehashed_missing_dependency_or_scan_member_refuses_before_writes(self):
        _old, source, _record = self.fixture._source()
        event = self.event("2026-01-07", "native:admission:new")
        original = self.prepare([event], day="2026-01-07")
        source_relative = str(source.relative_to(self.corpus))
        absent_index = self.lib._event_index_relative("org", self.lib.event_memory_identity(event))
        variants = {}
        for label, field, relative in (("historical-file", "files", source_relative),
                                       ("missing-index-witness", "files", absent_index),
                                       ("complete-scan", "directories", "events/org")):
            changed = copy.deepcopy(original)
            rows = changed["read_dependencies"][field]
            self.assertIn(relative, [row["relative"] for row in rows])
            changed["read_dependencies"][field] = [row for row in rows if row["relative"] != relative]
            variants[label] = changed
        changed = copy.deepcopy(original)
        directory = next(row for row in changed["read_dependencies"]["directories"] if row["relative"] == "events/org")
        self.assertIn(source.name, [row["name"] for row in directory["before"]["entries"]])
        directory["before"]["entries"] = [row for row in directory["before"]["entries"] if row["name"] != source.name]
        variants["unlisted-observed-member"] = changed
        for label, plan in variants.items():
            plan["plan_sha256"] = own(plan)
            with self.subTest(mutation=label):
                self.assert_refused_without_writes(plan)

    def test_retained_same_day_preserves_all_original_bytes_and_exact_before(self):
        event, source, _record = self.fixture._source()
        raw = source.read_bytes().replace(b"---\n", b"---\n# retained unusual frontmatter\n", 1)
        raw = raw.replace(b"## Log\n", b"## Log\r\n") + b"\noriginal trailing whitespace  "
        source.write_bytes(raw)
        prior = generation(source.stat())
        plan = self.prepare([event])
        self.assert_plan(plan)
        self.assertEqual(plan["appended_event_ids"], [])
        self.assertEqual([row["disposition"] for row in plan["admissions"]], ["retained-day"])
        page = next(page for page in plan["pages"] if page["slug"] == self.slug)
        self.assertIs(page["write"], False)
        self.assertEqual(self.raw(page), raw)
        self.assertEqual(self.raw(page["before"]), raw)
        self.assertEqual(page["before"]["generation"], prior)
        before = self.snapshot()
        with mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("retained page rewritten")):
            self.assert_result(self.publish(plan), plan)
        self.assertEqual(self.snapshot(), before)

    def test_append_retains_before_bytes_and_ordered_original_entry_content(self):
        old, source, _record = self.fixture._source()
        raw = source.read_bytes().replace(b"## Log\n", b"## Log\r\n")
        source.write_bytes(raw)
        new = self.event(occurrence="native:admission:new")
        plan = self.prepare([new])
        self.assert_plan(plan)
        page = next(page for page in plan["pages"] if page["slug"] == self.slug)
        self.assertEqual(self.raw(page["before"]), raw)
        old_entries = self.entries(raw)
        self.assertEqual(self.entries(self.raw(page))[:len(old_entries)], old_entries)
        expected_new = self.lib._event_line(new, self.lib.event_memory_identity(new),
                                           self.lib.event_semantic_identity(new))[0]
        self.assertEqual(self.entries(self.raw(page)), old_entries + [expected_new])
        self.assert_result(self.publish(plan), plan)
        self.assertEqual(source.read_bytes(), self.raw(page))

    def test_cross_day_retention_joins_actual_page_not_unwritten_requested_day(self):
        _old, source, _record = self.fixture._source()
        replay = self.event("2026-01-07")
        plan = self.prepare([replay], day="2026-01-07")
        self.assert_plan(plan)
        self.assertEqual(plan["day_slugs"], ["events/org/2026-01-07"])
        self.assertEqual(plan["appended_event_ids"], [])
        self.assertEqual([row["slug"] for row in plan["admissions"]], [self.slug])
        self.assertEqual([row["disposition"] for row in plan["admissions"]], ["retained-day"])
        self.assertEqual([page["slug"] for page in plan["pages"]], [self.slug])
        self.assertEqual(self.raw(plan["pages"][0]), source.read_bytes())
        self.assert_result(self.publish(plan), plan)
        self.assertFalse(Path(self.lib.corpus_path("events/org/2026-01-07")).exists())

    def test_retained_epoch_and_index_dependencies_preserve_exact_mapping(self):
        old, source, _record = self.fixture._source()
        self.fixture._commit_corpus()
        self.lib.consolidate_corpus()
        self.assertFalse(source.exists(), "existing bounded consolidation fixture did not retain the epoch")
        event_id = self.lib.event_memory_identity(old)
        index = self.lib._event_index_relative("org", event_id)
        entry = self.lib._read_event_index_entry("org", event_id)
        self.assertIsNotNone(entry)
        plan = self.prepare([self.event("2026-01-07")], day="2026-01-07")
        self.assert_plan(plan)
        self.assertEqual([row["slug"] for row in plan["admissions"]], [entry["epoch_slug"]])
        self.assertEqual([row["disposition"] for row in plan["admissions"]], ["retained-epoch"])
        self.assertEqual(plan["appended_event_ids"], [])
        dependencies = {row["relative"]: row["before"] for row in plan["read_dependencies"]["files"]}
        self.assertIsNotNone(dependencies[index])
        self.assertIsNotNone(dependencies[entry["epoch_slug"] + ".md"])
        self.assert_result(self.publish(plan), plan)
        index_path = self.corpus / index
        index_path.write_bytes(index_path.read_bytes() + b" ")
        self.assert_refused_without_writes(plan)

    def test_complete_original_duplicate_roster_dedupes_admissions_not_input_records(self):
        event = self.event()
        plan = self.prepare([event, event])
        self.assert_plan(plan)
        self.assertEqual(plan["input_records"], [self.lib._event_replay_record(event)] * 2)
        self.assertEqual([row["event_id"] for row in plan["admissions"]], [self.lib.event_memory_identity(event)])
        self.assertEqual(plan["appended_event_ids"], [self.lib.event_memory_identity(event)])
        conflicting = self.lib.Event("org", event.ts, "changed", "changed meaning", occurrence=event.occurrence)
        before = self.snapshot()
        with self.assertRaises(REFUSALS):
            self.prepare([event, conflicting])
        self.assertEqual(self.snapshot(), before)

    def test_stale_before_generation_refuses_even_with_unchanged_source_bytes(self):
        _old, source, _record = self.fixture._source()
        plan = self.prepare([self.event(occurrence="native:admission:new")])
        source.chmod(0o400)
        self.assert_refused_without_writes(plan)

    def test_rehashed_coherent_file_generations_reject_boolean_nlink(self):
        _old, source, _record = self.fixture._source()
        plan = self.prepare([self.event(occurrence="native:admission:new")])
        observed = generation(source.stat())
        self.assertEqual(observed["nlink"], 1)
        changed = []

        def substitute(value):
            if type(value) is dict:
                if set(value) == GENERATION_KEYS and value == observed:
                    value["nlink"] = True
                    changed.append(value)
                else:
                    for child in value.values():
                        substitute(child)
            elif type(value) is list:
                for child in value:
                    substitute(child)

        substitute(plan)
        self.assertTrue(changed, "fixture did not substitute an actual source generation")
        page = next(page for page in plan["pages"] if page["slug"] == self.slug)
        dependency = next(row for row in plan["read_dependencies"]["files"]
                          if row["relative"] == self.slug + ".md")
        directory = next(row for row in plan["read_dependencies"]["directories"]
                         if row["relative"] == "events/org")
        entry = next(row for row in directory["before"]["entries"] if row["name"] == source.name)
        for metadata in (page["before"]["generation"], dependency["before"]["generation"], entry["generation"]):
            self.assertIs(metadata["nlink"], True)
        plan["plan_sha256"] = own(plan)
        self.assert_refused_without_writes(plan)

    def test_native_pre_epoch_file_timestamp_is_retained_without_numeric_conversion(self):
        _old, source, _record = self.fixture._source()
        os.utime(source, ns=(-1, -1))
        observed = generation(source.stat())
        self.assertLess(observed["mtime_ns"], 0)
        plan = self.prepare([self.event(occurrence="native:admission:new")])
        self.assert_plan(plan)
        page = next(page for page in plan["pages"] if page["slug"] == self.slug)
        self.assertEqual(page["before"]["generation"], observed)
        self.assertIs(type(page["before"]["generation"]["mtime_ns"]), int)
        self.assert_result(self.publish(plan), plan)

    def test_changed_historical_scan_source_refuses_before_new_target_write(self):
        _old, source, _record = self.fixture._source()
        plan = self.prepare([self.event("2026-01-07", "native:admission:new")], day="2026-01-07")
        source.write_bytes(source.read_bytes() + b"\nchanged historical source\n")
        self.assert_refused_without_writes(plan)
        self.assertFalse(Path(self.lib.corpus_path("events/org/2026-01-07")).exists())

    def test_missing_historical_dependency_refuses_without_reclassifying_as_novel(self):
        _old, source, _record = self.fixture._source()
        original = source.read_bytes()
        plan = self.prepare([self.event("2026-01-07", "native:admission:new")], day="2026-01-07")
        retained = self.fixture.root / "retained-missing-source.md"
        source.rename(retained)
        self.assert_refused_without_writes(plan)
        self.assertFalse(source.exists())
        self.assertEqual(retained.read_bytes(), original)

    def test_same_byte_source_replacement_during_real_projection_refuses_preparation(self):
        _old, source, _record = self.fixture._source()
        actual_projection = self.lib._corpus_page_version_from_bytes
        changed = []

        def project(*args, **kwargs):
            result = actual_projection(*args, **kwargs)
            if kwargs.get("slug") == self.slug and not changed:
                self.assert_owned()
                changed.append(self.replace_same_bytes(source, "retained-projection-source.md"))
            return result

        with mock.patch.object(self.lib, "_corpus_page_version_from_bytes", side_effect=project), \
                mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("write during failed preparation")), \
                self.assertRaises(REFUSALS):
            self.prepare([self.event(occurrence="native:admission:new")])
        self.assertTrue(changed, "real projection mutation boundary did not execute")
        self.assertEqual(source.read_bytes(), changed[0].read_bytes())
        self.assert_owner_released()

    def test_caller_event_mutation_during_real_projection_refuses_preparation(self):
        self.fixture._source()
        event = self.event(occurrence="native:admission:new")
        original = self.lib._event_replay_record(event)
        before = self.snapshot()
        actual_projection = self.lib._corpus_page_version_from_bytes
        changed = []

        def project(*args, **kwargs):
            result = actual_projection(*args, **kwargs)
            if not changed:
                self.assert_owned()
                event.summary = "caller changed the supplied observation after rendering"
                changed.append(self.lib._event_replay_record(event))
            return result

        with mock.patch.object(self.lib, "_corpus_page_version_from_bytes", side_effect=project), \
                mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("planner published bytes")), \
                self.assertRaises(REFUSALS):
            self.prepare([event])
        self.assertTrue(changed, "actual projection mutation boundary did not execute")
        self.assertNotEqual(changed[0], original)
        self.assertEqual(self.snapshot(), before)
        self.assert_owner_released()

    def test_late_same_byte_dependency_replacement_during_readback_refuses_success_but_retains_prefix(self):
        _old, source, _record = self.fixture._source()
        event = self.event("2026-01-07", "native:admission:new")
        plan = self.prepare([event], day="2026-01-07")
        target_page = next(page for page in plan["pages"] if page["write"])
        target = Path(self.lib.corpus_path(target_page["slug"]))
        target_raw = self.raw(target_page)
        actual_write = self.lib.atomic_write
        written, changed = [], []

        def write(path, data, **kwargs):
            result = actual_write(path, data, **kwargs)
            if os.fspath(path) == str(target):
                written.append(str(target))
            return result

        def finalized(raw):
            if written and raw == target_raw and not changed:
                self.assert_owned()
                self.assertEqual(target.read_bytes(), target_raw)
                changed.append(self.replace_same_bytes(source, "retained-readback-source.md"))

        with mock.patch.object(self.lib, "atomic_write", side_effect=write), \
                mock.patch.object(self.lib, "hashlib", capture_tests._HashShim(finalized)), \
                self.assertRaises(REFUSALS):
            self.publish(plan)
        self.assertTrue(written, "fixture did not publish an actual target prefix")
        self.assertTrue(changed, "real post-write target hash boundary did not execute")
        self.assertEqual(target.read_bytes(), target_raw)
        self.assertEqual(source.read_bytes(), changed[0].read_bytes())
        self.assert_owner_released()

    def test_dependency_replacement_during_actual_final_result_copy_refuses_success(self):
        _old, source, _record = self.fixture._source()
        plan = self.prepare([self.event("2026-01-07", "native:admission:new")], day="2026-01-07")
        page = next(page for page in plan["pages"] if page["write"])
        target = Path(self.lib.corpus_path(page["slug"]))
        original = copy.deepcopy(plan)
        changed = []

        def detach(value, *args, **kwargs):
            result = copy.deepcopy(value, *args, **kwargs)
            if type(value) is dict and value.get("schema") == "sia-event-page-render-publication-v1" and not changed:
                self.assert_owned()
                self.assertEqual(target.read_bytes(), self.raw(page))
                changed.append(self.replace_same_bytes(source, "retained-final-copy-source.md"))
            return result

        with mock.patch.object(self.lib, "copy", _ModuleShim(copy, deepcopy=detach)), \
                self.assertRaises(REFUSALS):
            self.publish(plan)
        self.assertTrue(changed, "actual final result-copy boundary did not execute")
        self.assertEqual(plan, original)
        self.assertEqual(target.read_bytes(), self.raw(page))
        self.assertEqual(source.read_bytes(), changed[0].read_bytes())
        self.assert_owner_released()

    def test_new_scan_member_and_new_previously_absent_index_leaf_refuse(self):
        self.fixture._source()
        event = self.event("2026-01-07", "native:admission:new")
        plan = self.prepare([event], day="2026-01-07")
        absent_index = self.lib._event_index_relative("org", self.lib.event_memory_identity(event))
        dependencies = {row["relative"]: row["before"] for row in plan["read_dependencies"]["files"]}
        self.assertIn(absent_index, dependencies)
        self.assertIsNone(dependencies[absent_index])
        index_path = self.corpus / absent_index
        index_path.parent.mkdir(parents=True)
        index_path.write_bytes(b"{}\n")
        index_path.chmod(0o600)
        self.assert_refused_without_writes(plan)

    def test_new_directory_member_invalidates_complete_occurrence_roster(self):
        self.fixture._source()
        plan = self.prepare([self.event("2026-01-07", "native:admission:new")], day="2026-01-07")
        added = self.corpus / "events/org/unobserved-file.txt"
        added.write_bytes(b"new unscanned entry\n")
        self.assert_refused_without_writes(plan)

    def test_partial_prefix_retry_uses_original_plan_and_never_rerenders(self):
        events = [self.event(occurrence="native:admission:first"), self.event(occurrence="native:admission:second")]
        with mock.patch.object(self.lib, "MAX_EVENT_BULLETS", 1):
            plan = self.prepare(events)
        writes = [page for page in plan["pages"] if page["write"]]
        self.assertGreater(len(writes), 1, "fixture must have a real interrupted write prefix")
        last_path = self.lib.corpus_path(writes[-1]["slug"])
        actual_write = self.lib.atomic_write
        interrupted = []

        def interrupt(path, data, **kwargs):
            if os.fspath(path) == last_path:
                interrupted.append(last_path)
                raise OSError("synthetic late page publication interruption")
            return actual_write(path, data, **kwargs)

        with mock.patch.object(self.lib, "atomic_write", side_effect=interrupt), self.assertRaises(REFUSALS):
            self.publish(plan)
        self.assertEqual(interrupted, [last_path])
        self.assertEqual(Path(self.lib.corpus_path(writes[0]["slug"])).read_bytes(), self.raw(writes[0]))
        original = copy.deepcopy(plan)
        with mock.patch.object(self.lib, "_render_event_shard", side_effect=AssertionError("retry rerendered")):
            result = self.publish(plan)
        self.assert_result(result, original)
        self.assertEqual(plan, original)
        before = self.snapshot()
        self.assertEqual(self.publish(plan), result)
        self.assertEqual(self.snapshot(), before)
        refreshed = self.prepare(events)
        self.assertEqual(refreshed["appended_event_ids"], [])
        self.assertEqual({row["disposition"] for row in refreshed["admissions"]}, {"retained-day"})

    def retarget(self, plan, page, raw):
        projected = self.lib._corpus_page_version_from_bytes(slug=page["slug"], raw=raw)
        page.update(raw_utf8_base64=base64.b64encode(raw).decode("ascii"), raw_bytes=len(raw),
                    raw_sha256=digest(raw), version_sha256=projected["version_sha256"], origin=projected["origin"])
        for row in plan["admissions"]:
            if row["slug"] == page["slug"]:
                row["version_sha256"] = page["version_sha256"]
        plan["plan_sha256"] = own(plan)

    def test_rehashed_target_cannot_drop_rewrite_or_reorder_event_entries(self):
        old, _source, _record = self.fixture._source()
        new = self.event(occurrence="native:admission:new")
        original = self.prepare([new])
        original_page = next(page for page in original["pages"] if page["write"])
        original_raw = self.raw(original_page)
        old_entry, new_entry = [self.lib._event_line(
            selected, self.lib.event_memory_identity(selected), self.lib.event_semantic_identity(selected)
        )[0].encode("utf-8") for selected in (old, new)]
        variants = {
            "drop-old": original_raw.replace(old_entry, b""),
            "drop-new": original_raw.replace(new_entry, b""),
            "rewrite-old": original_raw.replace(
                old_entry, old_entry.replace(b"retained observation", b"modified observation")),
            "reorder": original_raw.replace(old_entry + b"\n" + new_entry, new_entry + b"\n" + old_entry),
        }
        for label, raw in variants.items():
            plan = copy.deepcopy(original)
            page = next(page for page in plan["pages"] if page["write"])
            self.assertNotEqual(raw, original_raw, "synthetic mutation did not change the target")
            self.retarget(plan, page, raw)
            with self.subTest(mutation=label):
                self.assert_refused_without_writes(plan)

    def test_rehashed_target_must_remain_admitted_by_the_native_event_page_parser(self):
        original = self.prepare([self.event()])
        original_page = next(page for page in original["pages"] if page["write"])
        original_raw = self.raw(original_page)
        for label, field, replacement in (
                ("missing-counts", b"sia_counts:", b""),
                ("invalid-counts", b"sia_counts:", b"sia_counts: []\n"),
                ("invalid-shard", b"sia_shard:", b"sia_shard: invalid\n")):
            plan = copy.deepcopy(original)
            page = next(page for page in plan["pages"] if page["write"])
            raw = b"".join(replacement if line.startswith(field) else line
                           for line in original_raw.splitlines(keepends=True))
            self.assertNotEqual(raw, original_raw, "fixture did not change native event metadata")
            self.retarget(plan, page, raw)
            with self.subTest(mutation=label):
                self.assert_refused_without_writes(plan)

    def test_rehashed_input_admission_and_append_rosters_must_join_exact_event_markers(self):
        original = self.prepare([self.event()])
        variants = {}
        for field in ("input_records", "admissions", "appended_event_ids"):
            changed = copy.deepcopy(original)
            self.assertTrue(changed[field])
            changed[field] = []
            variants["omit-" + field] = changed
        changed = copy.deepcopy(original)
        changed["admissions"][0]["semantic_id"] = digest(b"foreign admitted semantics")
        self.assertNotEqual(changed["admissions"], original["admissions"])
        variants["foreign-admitted-semantics"] = changed
        changed = copy.deepcopy(original)
        changed["input_records"][0]["summary"] = "unrepresented input meaning"
        variants["unrepresented-input"] = changed
        changed = copy.deepcopy(original)
        changed["admissions"][0]["disposition"] = "retained-day"
        changed["appended_event_ids"] = []
        variants["invented-retention-without-before"] = changed
        for label, plan in variants.items():
            plan["plan_sha256"] = own(plan)
            with self.subTest(mutation=label):
                self.assert_refused_without_writes(plan)

    def test_rehashed_before_bytes_must_match_dependency_and_original_source(self):
        self.fixture._source()
        plan = self.prepare([self.event(occurrence="native:admission:new")])
        page = next(page for page in plan["pages"] if page["write"])
        page["before"]["raw_utf8_base64"] = base64.b64encode(b"invented prior source").decode("ascii")
        plan["plan_sha256"] = own(plan)
        self.assert_refused_without_writes(plan)

    def test_mutually_rehashed_before_target_and_dependency_cannot_replace_actual_source(self):
        old, _source, _record = self.fixture._source()
        plan = self.prepare([self.event(occurrence="native:admission:new")])
        page = next(page for page in plan["pages"] if page["write"])
        entry = self.lib._event_line(old, self.lib.event_memory_identity(old),
                                     self.lib.event_semantic_identity(old))[0].encode("utf-8")
        invented = entry.replace(b"retained observation", b"invented observation")
        old_raw = self.raw(page["before"]).replace(entry, invented)
        page["before"].update(raw_utf8_base64=base64.b64encode(old_raw).decode("ascii"),
                              raw_bytes=len(old_raw), raw_sha256=digest(old_raw))
        dependency = next(row for row in plan["read_dependencies"]["files"]
                          if row["relative"] == page["slug"] + ".md")
        dependency["before"] = {key: page["before"][key] for key in FILE_BEFORE_KEYS}
        self.retarget(plan, page, self.raw(page).replace(entry, invented))
        self.assert_refused_without_writes(plan)

    def test_nonregular_historical_source_is_not_novel_or_silently_excluded(self):
        _old, source, _record = self.fixture._source()
        retained = source.with_suffix(".held")
        source.rename(retained)
        source.symlink_to(retained)
        before = self.snapshot()
        with self.assertRaises(REFUSALS):
            self.prepare([self.event("2026-01-07")], day="2026-01-07")
        self.assertEqual(self.snapshot(), before)

    def test_origin_of_existing_model_day_is_preserved_or_refused_before_writes(self):
        _old, source, _record = self.fixture._source()
        raw = source.read_bytes().replace(b"type: event-day\n", b"type: event-day\norigin: model\n")
        source.write_bytes(raw)
        before = self.snapshot()
        try:
            plan = self.prepare([self.event(occurrence="native:admission:new")])
        except REFUSALS:
            self.assertEqual(self.snapshot(), before)
            return
        self.assertEqual(self.snapshot(), before)
        page = next(page for page in plan["pages"] if page["slug"] == self.slug)
        self.assertEqual(page["origin"], "model", "renderer promoted original model page to inferred evidence")
        self.assertEqual(self.lib._corpus_page_version_from_bytes(
            slug=self.slug, raw=self.raw(page["before"]))["origin"], "model")
        try:
            self.publish(plan)
        except REFUSALS:
            self.assertEqual(self.snapshot(), before)
            return
        self.assertEqual(self.lib._capture_corpus_page_version(self.slug)["origin"], "model")

    def test_foreign_write_domain_and_admission_rehash_do_not_grant_authority(self):
        plan = self.prepare([self.event()])
        changed = copy.deepcopy(plan)
        changed["admissions"][0]["slug"] = "notes/not-an-event-target"
        changed["plan_sha256"] = own(changed)
        self.assert_refused_without_writes(changed)
        changed = copy.deepcopy(plan)
        changed["pages"][0]["slug"] = "../outside-corpus"
        changed["plan_sha256"] = own(changed)
        self.assert_refused_without_writes(changed)

    def test_external_plan_pin_is_required_and_checked_before_writes(self):
        plan = self.prepare([self.event()])
        before = self.snapshot()
        with mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("write before pin")), \
                self.assertRaises(REFUSALS):
            self.publish(plan, expected="not-an-independent-plan-digest")
        self.assertEqual(self.snapshot(), before)

    def test_complete_plan_cap_precedes_copy_base64_hash_and_writes(self):
        event = self.event()
        before = self.snapshot()
        forbidden = mock.Mock(side_effect=AssertionError("allocation/hash/write before whole-plan cap"))
        with mock.patch.object(self.lib, "MAX_STATE_JSON_BYTES", 1), \
                mock.patch.object(self.lib, "copy", SimpleNamespace(deepcopy=forbidden)), \
                mock.patch.object(self.lib, "hashlib", SimpleNamespace(sha256=forbidden)), \
                mock.patch.object(self.lib, "base64", SimpleNamespace(b64encode=forbidden, b64decode=forbidden), create=True), \
                mock.patch.object(self.lib, "atomic_write", forbidden), self.assertRaises(REFUSALS):
            self.prepare([event])
        forbidden.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_input_event_roster_cap_precedes_identity_hash_and_copy(self):
        event = self.event()
        forbidden = mock.Mock(side_effect=AssertionError("hash/copy before complete input-count cap"))
        with mock.patch.object(self.lib, "MAX_SOURCE_REPLAY_EVENTS", 1), \
                mock.patch.object(self.lib, "copy", SimpleNamespace(deepcopy=forbidden)), \
                mock.patch.object(self.lib, "hashlib", SimpleNamespace(sha256=forbidden)), self.assertRaises(REFUSALS):
            self.prepare([event, event])
        forbidden.assert_not_called()

    def test_publisher_complete_before_and_target_cap_precedes_decode_hash_or_copy(self):
        self.fixture._source()
        plan = self.prepare([self.event(occurrence="native:admission:new")])
        pin = plan["plan_sha256"]
        forbidden = mock.Mock(side_effect=AssertionError("materialized complete plan before byte-cap admission"))
        with mock.patch.object(self.lib, "MAX_STATE_JSON_BYTES", 1), \
                mock.patch.object(self.lib, "copy", SimpleNamespace(deepcopy=forbidden)), \
                mock.patch.object(self.lib, "hashlib", SimpleNamespace(sha256=forbidden)), \
                mock.patch.object(self.lib, "base64", SimpleNamespace(b64encode=forbidden, b64decode=forbidden), create=True), \
                mock.patch.object(self.lib, "atomic_write", forbidden), self.assertRaises(REFUSALS):
            self.publish(plan, expected=pin)
        forbidden.assert_not_called()

    def test_publisher_aggregate_cap_counts_complete_before_target_and_dependency_documents(self):
        self.fixture._source()
        plan = self.prepare([self.event(occurrence="native:admission:new")])
        # The control supplies the actual complete document sizes. Each
        # constituent fits this observed boundary, but their enclosing plan
        # does not; no hand-calculated byte oracle or raised ceiling is used.
        constituent_sizes = [len(canonical(plan[field])) for field in
                             ("input_records", "pages", "read_dependencies")]
        boundary = max(constituent_sizes)
        self.assertGreater(len(canonical(plan)), boundary)
        for size in constituent_sizes:
            self.assertLessEqual(size, boundary)
        self.assertTrue(any(page["before"] is not None for page in plan["pages"]))
        pin = plan["plan_sha256"]
        before = self.snapshot()
        forbidden = mock.Mock(side_effect=AssertionError("materialized members before complete aggregate admission"))
        with mock.patch.object(self.lib, "MAX_STATE_JSON_BYTES", boundary), \
                mock.patch.object(self.lib, "copy", _ModuleShim(copy, deepcopy=forbidden)), \
                mock.patch.object(self.lib, "hashlib", _ModuleShim(hashlib, sha256=forbidden)), \
                mock.patch.object(self.lib, "base64", _ModuleShim(base64, b64encode=forbidden, b64decode=forbidden), create=True), \
                mock.patch.object(self.lib, "atomic_write", forbidden), self.assertRaises(REFUSALS):
            self.publish(plan, expected=pin)
        forbidden.assert_not_called()
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
