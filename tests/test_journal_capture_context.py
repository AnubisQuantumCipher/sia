"""Operation-owned journal capture, never cursor acknowledgment.

Root alone runs this draft. It composes EvidenceCursorHealth's actual bounded
subprocess fixture and the real catalog/projector/sense functions. The child
process is a synthetic Python producer, not the host journal. No machine
journal, engine, model, database, or source acknowledgment is exercised.

The new optional context does not alter the legacy no-keyword return contract.
Native Event clock/summary/occurrence construction is compared through the
existing projection and an explicit fixed datetime fixture, not local time
conversion or an arithmetic oracle. All byte capacities use declared limits
or the observed complete synthetic representation.
"""

import base64
import contextlib
import copy
import datetime
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_sia as legacy_tests


NON_CLAIMS = [
    "This receipt retains operation-observed cursor bytes and catalog order; it does not authenticate the journal or establish complete machine history.",
    "No real journal cursor is acknowledged or advanced by this capture; corpus publication, cursor commit, source acknowledgment, and live generation publication remain separate operations.",
    "Existing bounded journal parsing and catalog-prefix selection remain controlling; retained refusal records do not make omitted payloads complete.",
    "Named-path and descriptor guards cover the checked generations, not hostile same-user mutation or changes after the returned receipt.",
]
RESULT_KEYS = {"schema", "status", "operation_id", "cursors", "non_claims", "capture_sha256"}
ROW_KEYS = {"scope", "cursor_name", "metadata_only", "before", "target", "catalog", "processed_count"}
IMAGE_KEYS = {"raw_base64", "raw_bytes", "raw_sha256"}
GENERATION_KEYS = {"device", "inode", "mode", "uid", "nlink", "size", "mtime_ns", "ctime_ns"}
SCOPES = ("sys", "user")
SCRATCH_NAMES = {scope + suffix for scope in SCOPES for suffix in (".catalog", ".full", ".selected")}
STAMP = datetime.datetime(2026, 1, 5, 12, 0, tzinfo=datetime.timezone.utc)
RECORD = {"MESSAGE": "fixture journal failure", "_SYSTEMD_UNIT": "example.service",
          "__CURSOR": "next-cursor"}
REFUSALS = (ValueError, RuntimeError, OSError)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class _ModuleShim:
    def __init__(self, module, **overrides):
        self._module = module
        self.__dict__.update(overrides)

    def __getattr__(self, name):
        return getattr(self._module, name)


class JournalCaptureContext(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy_tests.EvidenceCursorHealth(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.sialib
        self.assertTrue(callable(getattr(self.lib, "_journal_capture_context", None)),
                        "missing operation-owned journal context factory")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.operation = self.root / "journal-operation"
        self.state.mkdir(mode=0o700)
        self.operation.mkdir(mode=0o700)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for name, path in (
                ("HOME", self.root), ("SHARE", self.root / "share"),
                ("BIN", self.root / "bin"), ("STATE", self.state),
                ("CORPUS", self.root / "corpus"),
                ("CURSORS_PATH", self.state / "cursors.json"),
                ("CORPUS_OWNER_LOCK", self.state / "corpus-owner.lock"),
                ("BRAINSTEM_OWNER_LOCK", self.state / "brainstem-owner.lock"),
                ("LIFECYCLE_LOCK", self.state / "lifecycle.lock"),
                ("LIFECYCLE_TOMBSTONE", self.state / "lifecycle-removed"),
                ("RESTORE_BARRIER_PATH", self.root / "restore" / "in-progress.json"),
                ("RESTORE_MASK_PATH", self.root / "restore" / "runtime-mask"),
                ("RESTORE_SUPERVISOR_PATH", self.root / "restore" / "supervisor.json")):
            self.stack.enter_context(mock.patch.object(self.lib, name, str(path)))
        # The inherited fixture patches Popen on this private shim, not on the
        # process-wide subprocess module. Its actual child/pipes remain real.
        self.stack.enter_context(mock.patch.object(self.lib, "subprocess", _ModuleShim(subprocess)))
        self.pending = [("unrelated-pending-temp", "unrelated-pending-real")]
        self.stack.enter_context(mock.patch.object(self.lib, "PENDING_CURSOR_RENAMES", self.pending))
        self.stack.enter_context(mock.patch.object(self.lib, "utcnow", return_value=STAMP))
        for name in ("gbrain", "gbrain_call", "brain_sync", "_commit_sense_cursors"):
            self.stack.enter_context(mock.patch.object(
                self.lib, name, side_effect=AssertionError("capture invoked " + name)))

    def cursor(self, scope):
        return self.state / ("journal-" + scope + ".cursor")

    def seed(self, *, sys_raw=b"old-system", user_raw=b"old-user"):
        for scope, raw in (("sys", sys_raw), ("user", user_raw)):
            if raw is not None:
                self.cursor(scope).write_bytes(raw)
                self.cursor(scope).chmod(0o600)

    def snapshot(self):
        return {scope: None if not self.cursor(scope).exists() else self.cursor(scope).read_bytes()
                for scope in SCOPES}

    @contextlib.contextmanager
    def owned_context(self, *, operation_id="fixture-journal-capture", directory=None):
        # The fresh source-batch caller owns these leases; the journal context
        # retains its own directory/cursor descriptors, not a global pending list.
        with self.lib.brainstem_owner(), self.lib.corpus_owner():
            with self.lib._journal_capture_context(
                    operation_id=operation_id,
                    directory=str(self.operation if directory is None else directory)) as context:
                yield context

    def producer(self, *, metadata=None, cursor_bytes=b"producer-ran-ahead", returncode=0):
        raw = canonical(RECORD) + b"\n"
        catalog = b'{"__CURSOR":"next-cursor"}\n'
        return self.fixture._journal_process(
            "os.write(1, " + repr(raw) + ")", returncode=returncode,
            cursor_bytes=cursor_bytes,
            metadata="os.write(1, " + repr(catalog if metadata is None else metadata) + ")")

    def assert_image(self, image, raw):
        self.assertEqual(set(image), IMAGE_KEYS)
        self.assertEqual(image["raw_base64"], base64.b64encode(raw).decode("ascii"))
        self.assertEqual(image["raw_bytes"], len(raw))
        self.assertEqual(image["raw_sha256"], digest(raw))

    def assert_receipt(self, result, before, *, metadata_only=False, target=b"next-cursor", catalog=None,
                       processed_count=None):
        self.assertEqual(set(result), RESULT_KEYS)
        self.assertEqual(result["schema"], "sia-journal-cursor-capture-v1")
        self.assertEqual(result["status"], "captured-not-acknowledged")
        self.assertEqual(result["operation_id"], "fixture-journal-capture")
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertEqual(result["capture_sha256"], digest(canonical(
            {key: value for key, value in result.items() if key != "capture_sha256"})))
        self.assertEqual([row["scope"] for row in result["cursors"]], list(SCOPES))
        expected_catalog = ["next-cursor"] if catalog is None else catalog
        for row in result["cursors"]:
            self.assertEqual(set(row), ROW_KEYS)
            self.assertEqual(row["cursor_name"], "journal-" + row["scope"] + ".cursor")
            self.assertIs(row["metadata_only"], metadata_only)
            self.assertEqual(row["catalog"], expected_catalog)
            self.assertEqual(row["processed_count"], len(expected_catalog)
                             if processed_count is None else processed_count)
            self.assert_image(row["target"], target)
            raw = before[row["scope"]]
            if raw is None:
                self.assertIsNone(row["before"])
            else:
                self.assertEqual(set(row["before"]), IMAGE_KEYS | {"generation"})
                self.assert_image({key: row["before"][key] for key in IMAGE_KEYS}, raw)
                generation = row["before"]["generation"]
                self.assertEqual(set(generation), GENERATION_KEYS)
                info = self.cursor(row["scope"]).stat()
                self.assertEqual(generation, {
                    "device": info.st_dev, "inode": info.st_ino, "mode": info.st_mode,
                    "uid": info.st_uid, "nlink": info.st_nlink, "size": info.st_size,
                    "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns})
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.pending, [("unrelated-pending-temp", "unrelated-pending-real")])

    def assert_pinned_commands(self):
        self.assertTrue(self.fixture.journal_commands)
        for command in self.fixture.journal_commands:
            cursors = [arg.split("=", 1)[1] for arg in command if arg.startswith("--cursor-file=")]
            self.assertEqual(len(cursors), len(["one-cursor-file"]))
            path = Path(cursors[0])
            self.assertEqual(path.parts[:4], ("/", "proc", str(os.getpid()), "fd"))
            self.assertTrue(path.parts[4].isdigit())
            self.assertIn(path.name, SCRATCH_NAMES)
            self.assertNotIn(".pulse", str(path))

    def test_keyword_only_optional_lane_and_explicit_factory(self):
        parameters = inspect.signature(self.lib._journal_capture_context).parameters
        self.assertEqual(list(parameters), ["operation_id", "directory"])
        for parameter in parameters.values():
            self.assertIs(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)
        for function in (self.lib._journalctl, self.lib.sense_journal):
            parameter = inspect.signature(function).parameters["journal_context"]
            self.assertIs(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIsNone(parameter.default)

    def test_real_catalog_projection_and_sense_return_exact_images_without_ack(self):
        self.seed()
        before = self.snapshot()
        cursors = {"unrelated": "retained"}
        with self.owned_context() as context, self.producer():
            events = self.lib.sense_journal(cursors, journal_context=context)
            result = context.result()
            self.assert_receipt(result, before)
            self.assertEqual(context.result(), result)
            self.assert_pinned_commands()
        self.assertEqual(cursors, {"unrelated": "retained"})
        self.assertEqual([self.lib._event_replay_record(event) for event in events], [
            self.lib._event_replay_record(self.lib.Event(
                "journal", STAMP, "error", "example.service: fixture journal failure",
                {"organs/journal", "units/example"}, {"journal", "journal-error"},
                occurrence="journal:" + scope + ":next-cursor")) for scope in SCOPES])
        self.assertEqual(list(self.operation.iterdir()), [])

    def test_direct_journalctl_returns_context_row_not_a_rename_pair(self):
        self.seed()
        before = self.snapshot()
        with self.owned_context() as context, self.producer():
            observed = []
            for scope in SCOPES:
                args = [] if scope == "sys" else ["--user"]
                records, captured, refusals = self.lib._journalctl(
                    args, str(self.cursor(scope)), scope=scope, journal_context=context)
                self.assertEqual(records, [RECORD])
                self.assertEqual(refusals, [])
                self.assertEqual(set(captured), ROW_KEYS)
                observed.append(captured)
            result = context.result()
            self.assertEqual(result["cursors"], observed)
            self.assert_receipt(result, before)

    def test_missing_baselines_and_existing_empty_cursors_are_not_conflated(self):
        before = self.snapshot()
        with self.owned_context() as context, self.fixture._journal_process("pass", cursor_bytes=None):
            self.assertEqual(self.lib.sense_journal({}, journal_context=context), [])
            self.assert_receipt(context.result(), before, metadata_only=True, target=b"", catalog=[])
        self.seed(sys_raw=b"", user_raw=b"")
        before = self.snapshot()
        with self.owned_context() as context, self.producer():
            events = self.lib.sense_journal({}, journal_context=context)
            self.assertTrue(events)
            self.assert_receipt(context.result(), before)
        self.assertTrue(all("+300" in cmd for cmd in self.fixture.journal_commands
                            if "-p" in cmd))

    def test_fresh_nonempty_baseline_discards_history_but_retains_targets(self):
        before = self.snapshot()
        with self.owned_context() as context, self.producer():
            self.assertEqual(self.lib.sense_journal({}, journal_context=context), [])
            self.assert_receipt(context.result(), before, metadata_only=True)
        self.assertTrue(all("--output-fields=__CURSOR" in cmd for cmd in self.fixture.journal_commands))
        self.assertTrue(all("+300" not in cmd for cmd in self.fixture.journal_commands))

    def test_empty_existing_catalog_preserves_exact_before_bytes_as_target(self):
        self.seed(sys_raw=b"unchanged-cursor\n", user_raw=b"unchanged-cursor\n")
        before = self.snapshot()
        with self.owned_context() as context, self.fixture._journal_process("pass", cursor_bytes=None):
            self.assertEqual(self.lib.sense_journal({}, journal_context=context), [])
            self.assert_receipt(context.result(), before, target=b"unchanged-cursor\n", catalog=[])

    def test_context_never_touches_legacy_shared_scratch_or_global_pending(self):
        self.seed()
        legacy = {}
        for scope in SCOPES:
            for suffix in (".pulse", ".pulse.catalog", ".pulse.full"):
                path = Path(str(self.cursor(scope)) + suffix)
                path.write_bytes((scope + suffix).encode("ascii"))
                legacy[path] = path.read_bytes()
        before = self.snapshot()
        with self.owned_context() as context, self.producer():
            self.lib.sense_journal({}, journal_context=context)
            self.assert_receipt(context.result(), before)
            self.assert_pinned_commands()
        self.assertEqual({path: path.read_bytes() for path in legacy}, legacy)

    def test_legacy_no_keyword_return_and_pending_rename_contract_are_unchanged(self):
        self.seed()
        before = self.snapshot()
        with self.producer():
            records, pending, refusals = self.lib._journalctl([], str(self.cursor("sys")))
        self.assertEqual(records, [RECORD])
        self.assertEqual(pending, (str(self.cursor("sys")) + ".pulse", str(self.cursor("sys"))))
        self.assertEqual(refusals, [])
        self.assertEqual(Path(pending[0]).read_bytes(), b"next-cursor")
        Path(pending[0]).unlink()
        with self.producer():
            events = self.lib.sense_journal({})
        self.assertEqual([event.occurrence for event in events],
                         ["journal:" + scope + ":next-cursor" for scope in SCOPES])
        self.assertEqual(self.pending, [("unrelated-pending-temp", "unrelated-pending-real")] + [
            (str(self.cursor(scope)) + ".pulse", str(self.cursor(scope))) for scope in SCOPES])
        self.assertEqual(self.snapshot(), before)
        for scope in SCOPES:
            Path(str(self.cursor(scope)) + ".pulse").unlink()

    def test_incomplete_or_reused_scope_cannot_publish_a_complete_capture(self):
        self.seed()
        before = self.snapshot()
        with self.owned_context() as context, self.producer():
            self.lib._journalctl([], str(self.cursor("sys")), journal_context=context)
            with self.assertRaises(REFUSALS):
                context.result()
            commands = list(self.fixture.journal_commands)
            with self.assertRaises(REFUSALS):
                self.lib._journalctl([], str(self.cursor("sys")), journal_context=context)
            self.assertEqual(self.fixture.journal_commands, commands)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.pending, [("unrelated-pending-temp", "unrelated-pending-real")])

    def test_user_process_failure_never_acks_the_successful_system_prefix(self):
        self.seed()
        before = self.snapshot()
        trial = {"unrelated": "retained"}
        real_records = self.lib._journalctl_records

        def records(command, **kwargs):
            if "--user" in command:
                with self.fixture._journal_process("os.write(2, b'user denied')", returncode=1):
                    return real_records(command, **kwargs)
            return real_records(command, **kwargs)

        with self.owned_context() as context, self.producer(), \
                mock.patch.object(self.lib, "_journalctl_records", side_effect=records):
            with self.assertRaises(REFUSALS):
                self.lib.sense_journal(trial, journal_context=context)
            with self.assertRaises(REFUSALS):
                context.result()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(trial, {"unrelated": "retained"})
        self.assertEqual(self.pending, [("unrelated-pending-temp", "unrelated-pending-real")])
        self.assertEqual(list(self.operation.iterdir()), [])

    def test_complete_catalog_and_poison_prefix_refusal_grammar_are_retained(self):
        self.seed()
        before = self.snapshot()
        # These exact artificial ceilings and producer bytes come from
        # EvidenceCursorHealth.test_journal_newline_free_overflow_binds_cursor_refusal.
        with self.owned_context() as context, self.fixture._journal_process("os.write(1, b'x' * 32)"), \
                mock.patch.object(self.lib, "MAX_JOURNAL_RECORD_BYTES", 16), \
                mock.patch.object(self.lib, "MAX_JOURNAL_OUTPUT_BYTES", 16):
            cursors = {}
            self.assertEqual(self.lib.sense_journal(cursors, journal_context=context), [])
            self.assert_receipt(context.result(), before)
        refusals = cursors[self.lib.SOURCE_RECORD_REFUSALS_KEY]
        self.assertEqual([row["scope"] for row in refusals], list(SCOPES))
        for row in refusals:
            self.assertEqual(row["schema"], "sia-journal-record-refusal-v1")
            self.assertEqual(row["reason"], "journal-record-over-aggregate")
            self.assertIs(row["complete"], False)
            self.assertEqual(row["cursor"], "next-cursor")

    def test_full_catalog_survives_when_only_the_existing_bounded_prefix_is_processed(self):
        self.seed()
        before = self.snapshot()
        # Exact synthetic roster and budget construction from the existing
        # EvidenceCursorHealth aggregate-prefix test; no new count oracle.
        rows = [(json.dumps({"MESSAGE": f"row-{index}", "__CURSOR": f"cursor-{index}"},
                            separators=(",", ":")) + "\n").encode() for index in range(3)]
        metadata_rows = [(json.dumps({"__CURSOR": f"cursor-{index}"},
                                     separators=(",", ":")) + "\n").encode() for index in range(3)]
        with self.owned_context() as context, \
                self.fixture._journal_process(f"os.write(1, {b''.join(rows)!r})",
                                              metadata=f"os.write(1, {b''.join(metadata_rows)!r})"), \
                mock.patch.object(self.lib, "MAX_JOURNAL_RECORD_BYTES", 128), \
                mock.patch.object(self.lib, "MAX_JOURNAL_OUTPUT_BYTES", sum(len(row) for row in rows[:2])):
            observed = []
            for scope in SCOPES:
                args = [] if scope == "sys" else ["--user"]
                records, captured, refusals = self.lib._journalctl(
                    args, str(self.cursor(scope)), scope=scope, journal_context=context)
                self.assertEqual([record["MESSAGE"] for record in records], ["row-0", "row-1"])
                self.assertEqual(refusals, [])
                observed.append(captured)
            result = context.result()
            self.assertEqual(result["cursors"], observed)
            self.assert_receipt(result, before, target=b"cursor-1",
                                catalog=[json.loads(row)["__CURSOR"] for row in metadata_rows],
                                processed_count=len(rows[:2]))

    def test_same_byte_system_cursor_replacement_during_user_capture_refuses(self):
        self.seed()
        before = self.snapshot()
        real_records = self.lib._journalctl_records
        changed = []

        def records(command, **kwargs):
            result = real_records(command, **kwargs)
            if "--user" in command and not changed:
                self.cursor("sys").rename(self.state / "retained-original-system")
                self.cursor("sys").write_bytes(before["sys"])
                self.cursor("sys").chmod(0o600)
                changed.append(True)
            return result

        with self.assertRaises(REFUSALS):
            with self.owned_context() as context, self.producer(), \
                    mock.patch.object(self.lib, "_journalctl_records", side_effect=records):
                self.lib.sense_journal({}, journal_context=context)
                context.result()
        self.assertTrue(changed, "the real user capture boundary was not reached")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual((self.state / "retained-original-system").read_bytes(), before["sys"])
        self.assertEqual(self.pending, [("unrelated-pending-temp", "unrelated-pending-real")])

    def test_noop_real_user_capture_callback_preserves_complete_success(self):
        self.seed()
        before = self.snapshot()
        real_records = self.lib._journalctl_records
        observed = []

        def records(command, **kwargs):
            result = real_records(command, **kwargs)
            if "--user" in command:
                observed.append(True)
            return result

        with self.owned_context() as context, self.producer(), \
                mock.patch.object(self.lib, "_journalctl_records", side_effect=records):
            self.lib.sense_journal({}, journal_context=context)
            self.assert_receipt(context.result(), before)
        self.assertTrue(observed)

    def test_journalctl_atomic_cursor_replacement_is_admitted_and_cleaned(self):
        self.seed()
        before = self.snapshot()
        real_records = self.lib._journalctl_records
        real_projected = self.lib._journalctl_projected_records
        replaced = []

        def replace(command):
            cursor = next(argument.split("=", 1)[1] for argument in command
                          if argument.startswith("--cursor-file="))
            replacement = cursor + ".journalctl-replacement"
            with open(replacement, "xb") as stream:
                stream.write(b"producer-ran-ahead")
            os.chmod(replacement, 0o644)
            os.replace(replacement, cursor)
            replaced.append(Path(cursor).name)

        def records(command, **kwargs):
            result = real_records(command, **kwargs)
            replace(command)
            return result

        def projected(command, *args, **kwargs):
            result = real_projected(command, *args, **kwargs)
            replace(command)
            return result

        with self.owned_context() as context, self.producer(), \
                mock.patch.object(
                    self.lib, "_journalctl_records", side_effect=records), \
                mock.patch.object(
                    self.lib, "_journalctl_projected_records",
                    side_effect=projected):
            events = self.lib.sense_journal({}, journal_context=context)
            self.assertTrue(events)
            self.assert_receipt(context.result(), before)
        self.assertEqual(replaced, [
            "sys.catalog", "sys.full", "user.catalog", "user.full"])
        self.assertEqual(list(self.operation.iterdir()), [])

    def test_named_operation_directory_replacement_refuses_without_cleaning_replacement(self):
        self.seed()
        before = self.snapshot()
        real_records = self.lib._journalctl_records
        moved = self.root / "original-operation"
        changed = []

        def records(command, **kwargs):
            result = real_records(command, **kwargs)
            if "--user" in command and not changed:
                self.operation.rename(moved)
                self.operation.mkdir(mode=0o700)
                (self.operation / "sys.selected").write_bytes(b"unrelated-replacement")
                changed.append(True)
            return result

        with self.assertRaises(REFUSALS):
            with self.owned_context() as context, self.producer(), \
                    mock.patch.object(self.lib, "_journalctl_records", side_effect=records):
                self.lib.sense_journal({}, journal_context=context)
                context.result()
        self.assertTrue(changed)
        self.assertEqual((self.operation / "sys.selected").read_bytes(), b"unrelated-replacement")
        self.assertEqual(self.snapshot(), before)

    def test_context_rejects_linked_or_nonprivate_directory_before_subprocess(self):
        linked = self.root / "linked-operation"
        linked.symlink_to(self.operation, target_is_directory=True)
        linked_parent = self.root / "linked-parent"
        linked_parent.symlink_to(self.root, target_is_directory=True)
        for directory in (linked, linked_parent / self.operation.name):
            with self.subTest(directory=str(directory)), self.assertRaises(REFUSALS):
                with self.owned_context(directory=directory):
                    self.fail("linked operation directory was admitted")
        self.operation.chmod(0o755)
        with self.assertRaises(REFUSALS):
            with self.owned_context():
                self.fail("nonprivate operation directory was admitted")
        self.assertEqual(self.fixture.journal_commands, [])

    def test_preexisting_known_scratch_is_not_deleted_or_adopted(self):
        self.seed()
        before = self.snapshot()
        target = self.operation / "sys.catalog"
        target.write_bytes(b"preexisting-other-operation")
        with self.assertRaises(REFUSALS):
            with self.owned_context() as context, self.producer():
                self.lib.sense_journal({}, journal_context=context)
                context.result()
        self.assertEqual(target.read_bytes(), b"preexisting-other-operation")
        self.assertEqual(self.fixture.journal_commands, [])
        self.assertEqual(self.snapshot(), before)

    def test_absent_cursor_appearing_during_capture_is_not_an_unchanged_baseline(self):
        real_records = self.lib._journalctl_records
        changed = []

        def records(command, **kwargs):
            result = real_records(command, **kwargs)
            if "--user" in command and not changed:
                self.cursor("sys").write_bytes(b"foreign-late-cursor")
                self.cursor("sys").chmod(0o600)
                changed.append(True)
            return result

        with self.assertRaises(REFUSALS):
            with self.owned_context() as context, self.producer(), \
                    mock.patch.object(self.lib, "_journalctl_records", side_effect=records):
                self.lib.sense_journal({}, journal_context=context)
                context.result()
        self.assertTrue(changed)
        self.assertEqual(self.cursor("sys").read_bytes(), b"foreign-late-cursor")
        self.assertFalse(self.cursor("user").exists())
        self.assertEqual(self.pending, [("unrelated-pending-temp", "unrelated-pending-real")])

    def test_final_receipt_copy_cannot_hide_source_generation_mutation(self):
        self.seed()
        before = self.snapshot()
        changed = []

        def copied(value, *args, **kwargs):
            result = copy.deepcopy(value, *args, **kwargs)
            if type(value) is dict and value.get("schema") == "sia-journal-cursor-capture-v1" and not changed:
                self.cursor("sys").rename(self.state / "original-before-copy")
                self.cursor("sys").write_bytes(before["sys"])
                self.cursor("sys").chmod(0o600)
                changed.append(True)
            return result

        with self.assertRaises(REFUSALS):
            with self.owned_context() as context, self.producer():
                self.lib.sense_journal({}, journal_context=context)
                with mock.patch.object(self.lib, "copy", _ModuleShim(copy, deepcopy=copied)):
                    context.result()
        self.assertTrue(changed, "actual final receipt copy was not exercised")
        self.assertEqual(self.snapshot(), before)

    def test_complete_receipt_capacity_never_clips_the_second_scope_or_catalog(self):
        self.seed()
        before = self.snapshot()
        with self.owned_context() as context, self.producer():
            self.lib.sense_journal({}, journal_context=context)
            result = context.result()
            self.assert_receipt(result, before)
        boundary = max(len(canonical(value)) for value in result.values())
        self.assertGreater(len(canonical(result)), boundary)
        with mock.patch.object(self.lib, "MAX_STATE_JSON_BYTES", boundary), self.assertRaises(REFUSALS):
            with self.owned_context() as context, self.producer():
                self.lib.sense_journal({}, journal_context=context)
                context.result()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.pending, [("unrelated-pending-temp", "unrelated-pending-real")])


if __name__ == "__main__":
    unittest.main()
