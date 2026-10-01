"""Journal acquisition inside the inert controller-source capture.

Root alone executes this module.  It composes ControllerSourceCapture instead
of inheriting its test roster and selects the real ``sense_journal`` collector
alone.  Synthetic child processes stand in for journalctl; no host journal,
resident service, model, database, source acknowledgment, or publication is
used.

The real operation-owned journal context remains responsible for its cursor
images, catalog-prefix binding, receipt and scratch cleanup.  Instrumentation
only observes the public factory and delegates to the real collector.  Native
batch serialization and the journal receipt's original serializer remain
distinct.
"""

import base64
import contextlib
import functools
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import unittest
from unittest import mock

from tests import test_controller_source_capture as capture_tests
from tests import test_journal_capture_context as journal_tests


CURSOR_BYTES = {"sys": b"system-before", "user": b"user-before"}
NEXT_CURSORS = {"sys": "system-next", "user": "user-next"}
SCOPES = ("sys", "user")
REFUSALS = (ValueError, RuntimeError, OSError)


class ControllerSourceJournal(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        case = capture_tests.ControllerSourceCapture(methodName="runTest")
        try:
            case.setUp()
            state = case.root / "state"
            state.mkdir(parents=True, exist_ok=True)
            pending = [("unrelated-private-temp", "unrelated-private-real")]
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(case.lib, "STATE", str(state)))
                stack.enter_context(mock.patch.object(
                    case.lib, "subprocess", journal_tests._ModuleShim(subprocess)))
                stack.enter_context(mock.patch.object(
                    case.lib, "PENDING_CURSOR_RENAMES", pending))
                stack.enter_context(mock.patch.object(
                    case.lib, "utcnow", return_value=journal_tests.STAMP))
                disabled = sorted(
                    (set(case.lib.BASE_ORGANS) | set(case.lib.OPTIONAL_ORGANS))
                    - {"journal"})
                case.install_config({
                    "senses": {"disable": disabled}, "custom_senses": []})
                case.configure_selection(["sense_journal"], [])
                self.assertEqual(case.configuration["native_collectors"],
                                 ["sense_journal"])
                self.assertEqual(case.configuration["custom_collectors"], [])
                self.assertEqual(case.catalog["sources"], [{
                    "source_id": "sense_journal", "collector": "sense_journal",
                    "organ": "journal", "custom_name": None,
                }])
                self.assertEqual(list(case.lib.ORGANS), ["journal"])
                self.assertEqual([sense.__name__ for sense in case.lib.SENSES],
                                 ["sense_journal", "sense_custom"])
                yield case
        finally:
            case.doCleanups()

    def seed_journal_cursors(self, case):
        paths = {}
        for scope in SCOPES:
            path = Path(case.lib.STATE) / ("journal-" + scope + ".cursor")
            path.write_bytes(CURSOR_BYTES[scope])
            path.chmod(0o600)
            paths[scope] = path
        return paths

    @staticmethod
    def cursor_snapshot(paths):
        return {scope: path.read_bytes() for scope, path in paths.items()}

    @contextlib.contextmanager
    def synthetic_journal(self, case, *, fail_user=False):
        real_popen = subprocess.Popen
        calls = []

        def launch(command, **kwargs):
            scope = "user" if "--user" in command else "sys"
            phase = ("catalog" if "--output-fields=__CURSOR" in command
                     else "records")
            failing = fail_user and scope == "user"
            calls.append((scope, phase, "failure" if failing else "success"))
            cursor_arguments = [argument for argument in command
                                if argument.startswith("--cursor-file=")]
            cursor_path = (cursor_arguments[0].split("=", 1)[1]
                           if cursor_arguments else None)
            ahead = (scope + "-producer-ran-ahead").encode("ascii")
            if failing:
                payload = b""
                stderr = b"private-user-scope-failure"
                returncode = 1
            elif phase == "catalog":
                payload = journal_tests.canonical({
                    "__CURSOR": NEXT_CURSORS[scope]}) + b"\n"
                stderr = b""
                returncode = 0
            else:
                payload = journal_tests.canonical({
                    "MESSAGE": scope + " fixture journal fault",
                    "_SYSTEMD_UNIT": scope + ".service",
                    "__CURSOR": NEXT_CURSORS[scope],
                }) + b"\n"
                stderr = b""
                returncode = 0
            program = "import os,sys\n"
            if cursor_path is not None:
                program += "open(" + repr(cursor_path) \
                    + ", 'wb').write(" + repr(ahead) + ")\n"
            program += "os.write(1, " + repr(payload) + ")\n"
            program += "os.write(2, " + repr(stderr) + ")\n"
            program += "sys.exit(" + repr(returncode) + ")\n"
            return real_popen([sys.executable, "-c", program], **kwargs)

        with mock.patch.object(
                case.lib.subprocess, "Popen", side_effect=launch):
            yield calls

    @contextlib.contextmanager
    def observe_actual_journal(self, case):
        original_factory = case.lib._journal_capture_context
        original_journal = case.lib.sense_journal
        context_calls = []
        sense_calls = []
        receipts = []

        @functools.wraps(original_factory)
        def factory(*, operation_id, directory):
            path = Path(directory)
            self.assertTrue(path.is_dir())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
            context = original_factory(
                operation_id=operation_id, directory=directory)
            context_calls.append({
                "operation_id": operation_id, "directory": path,
                "context": context,
            })
            return context

        @functools.wraps(original_journal)
        def journal(cursors, *, journal_context=None):
            self.assertIsNotNone(journal_context)
            self.assertTrue(context_calls)
            self.assertIs(journal_context, context_calls[-1]["context"])
            sense_calls.append(journal_context)
            events = original_journal(
                cursors, journal_context=journal_context)
            receipts.append(journal_context.result())
            return events

        with mock.patch.object(case.lib, "_journal_capture_context", factory), \
                mock.patch.object(case.lib, "sense_journal", journal), \
                mock.patch.object(case.lib, "SENSES", [journal, case.lib.sense_custom]):
            yield context_calls, sense_calls, receipts

    def assert_scratch_clean(self, context_calls):
        self.assertEqual(len(context_calls), 1)
        directory = context_calls[0]["directory"]
        for leaf in journal_tests.SCRATCH_NAMES:
            self.assertFalse(os.path.lexists(directory / leaf),
                             "journal operation scratch survived: " + leaf)
        if directory.exists():
            self.assertEqual(list(directory.iterdir()), [])

    def assert_receipt(self, receipt, context_call):
        self.assertEqual(set(receipt), journal_tests.RESULT_KEYS)
        self.assertEqual(receipt["schema"], "sia-journal-cursor-capture-v1")
        self.assertEqual(receipt["status"], "captured-not-acknowledged")
        self.assertEqual(receipt["operation_id"], context_call["operation_id"])
        self.assertIs(type(receipt["operation_id"]), str)
        self.assertIsNotNone(re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:-]*", receipt["operation_id"]))
        self.assertEqual(receipt["non_claims"], journal_tests.NON_CLAIMS)
        body = {key: value for key, value in receipt.items()
                if key != "capture_sha256"}
        self.assertEqual(receipt["capture_sha256"],
                         journal_tests.digest(journal_tests.canonical(body)))
        self.assertEqual([row["scope"] for row in receipt["cursors"]],
                         list(SCOPES))
        for row in receipt["cursors"]:
            scope = row["scope"]
            self.assertEqual(set(row), journal_tests.ROW_KEYS)
            self.assertEqual(row["cursor_name"],
                             "journal-" + scope + ".cursor")
            self.assertIs(row["metadata_only"], False)
            self.assertEqual(row["catalog"], [NEXT_CURSORS[scope]])
            self.assertEqual(row["processed_count"], 1)
            before = row["before"]
            self.assertEqual(set(before),
                             journal_tests.IMAGE_KEYS | {"generation"})
            self.assertEqual(before["raw_base64"], base64.b64encode(
                CURSOR_BYTES[scope]).decode("ascii"))
            self.assertEqual(before["raw_bytes"], len(CURSOR_BYTES[scope]))
            self.assertEqual(before["raw_sha256"], hashlib.sha256(
                CURSOR_BYTES[scope]).hexdigest())
            target = NEXT_CURSORS[scope].encode("ascii")
            self.assertEqual(row["target"], {
                "raw_base64": base64.b64encode(target).decode("ascii"),
                "raw_bytes": len(target),
                "raw_sha256": hashlib.sha256(target).hexdigest(),
            })

    def test_real_journal_capture_retains_whole_operation_receipt_without_ack(self):
        with self.fixture() as case:
            paths = self.seed_journal_cursors(case)
            journal_before = self.cursor_snapshot(paths)
            before = case.inert_before()
            with self.synthetic_journal(case) as process_calls, \
                    self.observe_actual_journal(case) as observed:
                context_calls, sense_calls, receipts = observed
                batch = case.capture()
            case.assert_batch(batch)
            self.assertEqual(process_calls, [
                ("sys", "catalog", "success"),
                ("sys", "records", "success"),
                ("user", "catalog", "success"),
                ("user", "records", "success"),
            ])
            self.assertEqual(len(sense_calls), 1)
            self.assertEqual(len(receipts), 1)
            self.assertEqual(batch["journal_proposals"], [receipts[0]])
            self.assert_receipt(batch["journal_proposals"][0], context_calls[0])
            self.assertEqual(batch["source_returns"]["runs"][0]["source_id"],
                             "sense_journal")
            self.assertEqual(len(batch["source_returns"]["runs"][0]["events"]),
                             len(SCOPES))
            self.assertEqual(self.cursor_snapshot(paths), journal_before)
            case.assert_inert(before)
            self.assert_scratch_clean(context_calls)

    def test_user_process_failure_after_system_success_refuses_whole_capture(self):
        with self.fixture() as case:
            paths = self.seed_journal_cursors(case)
            journal_before = self.cursor_snapshot(paths)
            before = case.inert_before()
            with self.synthetic_journal(case, fail_user=True) as process_calls, \
                    self.observe_actual_journal(case) as observed:
                context_calls, sense_calls, receipts = observed
                with self.assertRaises(REFUSALS) as caught:
                    case.capture()
            error = caught.exception
            self.assertEqual(getattr(error, "source_id", None), "sense_journal")
            self.assertEqual(getattr(error, "phase", None), "collect")
            self.assertTrue(getattr(error, "non_claims", None))
            self.assertNotIn("private-user-scope-failure", str(error))
            self.assertEqual(process_calls, [
                ("sys", "catalog", "success"),
                ("sys", "records", "success"),
                ("user", "catalog", "failure"),
            ])
            self.assertEqual(len(sense_calls), 1)
            self.assertEqual(receipts, [])
            self.assertEqual(self.cursor_snapshot(paths), journal_before)
            case.assert_inert(before)
            self.assert_scratch_clean(context_calls)


if __name__ == "__main__":
    unittest.main()
