"""Originals survive HEAD rewrite/GC; lost admitted retention refuses replay."""
import copy
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from tests import test_consolidation_delivery_execution as execution_fixture


class ConsolidationOriginals(unittest.TestCase):
    def setUp(self):
        self.fixture = execution_fixture.ConsolidationDeliveryExecution(
            methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib, self.delivery = self.fixture.lib, self.fixture.delivery
        self.originals = self.delivery.originals
        self.discovery = self.fixture.fixture.fixture
        self.path = Path(self.originals._path(self.lib))

    def value(self):
        return json.loads(self.path.read_text())

    def ref(self):
        return self.originals._name(self.value()["binding"])

    def observe(self):
        return self.delivery.inspect_outcomes(self.lib, self.fixture.record)

    def assert_pending(self, phase):
        self.assertEqual(self.fixture.retained()["phase"], phase)
        self.assertEqual(self.fixture.memo_path.read_bytes(), self.fixture.memo_bytes)

    def test_newer_original_survives_history_rewrite_and_gc(self):
        source = self.fixture.sources[0]
        raw = source.read_bytes() + b"\nsource version after admission\n"
        source.write_bytes(raw)
        self.fixture.stage()
        self.fixture.execute()
        original = self.value()["commit"]
        self.assertNotEqual(original, self.fixture.record["commit"])
        expected = self.observe()
        before = self.path.read_bytes(), self.fixture.path.read_bytes()
        self.discovery.git("add", "-u")
        tree = self.discovery.git("write-tree")
        root = self.discovery.git("-c", "user.name=Fixture",
                                  "-c", "user.email=t@t", "commit-tree",
                                  tree, "-m", "independent root")
        self.discovery.git("update-ref", "HEAD", root)
        self.discovery.git("reflog", "expire", "--expire=now", "--all")
        self.discovery.git("pack-refs", "--all", "--prune")
        self.discovery.git("gc", "--prune=now", "--quiet")
        relative = source.relative_to(self.lib.CORPUS).as_posix()
        retained = subprocess.check_output(
            ["git", "-C", self.lib.CORPUS, "cat-file", "blob",
             original + ":" + relative], timeout=10)
        self.assertEqual(retained, raw)
        self.assertEqual(self.observe(), expected)
        self.discovery.git("update-ref", "-d", self.ref(), original)
        self.discovery.git("reflog", "expire", "--expire=now", "--all")
        self.discovery.git("gc", "--prune=now", "--quiet")
        self.assertEqual(self.discovery.git("cat-file", "-t", root), "commit")
        gone = subprocess.run(
            ["git", "-C", self.lib.CORPUS, "cat-file", "-e", original],
            capture_output=True, timeout=10)
        self.assertEqual((gone.returncode, gone.stdout, gone.stderr), (1, b"", b""))
        with self.assertRaisesRegex(ValueError, "pin is missing or differs"):
            self.observe()
        self.assertEqual((self.path.read_bytes(), self.fixture.path.read_bytes()), before)
        self.assert_pending("effects-returned")

    def test_each_retention_boundary_precedes_effects_and_replays_exact_plan(self):
        claimed = self.fixture.stage()
        identity = None
        for stage, phase in (("originals-planned", "planned"),
                             ("originals-pinned", "planned"),
                             ("originals-retained", "retained")):
            def cut(observed):
                if observed == stage:
                    raise RuntimeError("retention cut")
            with mock.patch.object(self.originals, "_boundary", cut):
                with self.assertRaisesRegex(RuntimeError, "retention cut"):
                    self.fixture.execute()
            value = self.value()
            self.assertEqual(value["phase"], phase)
            if identity is None:
                identity = value["commit"]
                self.discovery.git("commit", "--allow-empty", "-m",
                                   "unrelated HEAD advance after planning")
                self.assertNotEqual(self.discovery.git("rev-parse", "HEAD"), identity)
            self.assertEqual(value["commit"], identity)
            self.assertEqual(self.fixture.retained(), claimed)
            self.fixture.fixture.assert_sources_unchanged()
        self.fixture.execute()
        self.assertEqual(self.value()["commit"], identity)
        self.assertEqual(len(self.observe()["outcomes"]), 3)

    def test_retained_journal_cannot_be_bootstrapped_after_execution_intent(self):
        self.fixture.stage()
        def cut(stage):
            if stage == "execution-persisted":
                raise RuntimeError("execution cut")
        with mock.patch.object(self.delivery, "_boundary", cut):
            with self.assertRaisesRegex(RuntimeError, "execution cut"):
                self.fixture.execute()
        raw = self.path.read_bytes()
        self.path.unlink()
        for operation in (self.fixture.execute, self.fixture.fixture.offer):
            with self.assertRaisesRegex(ValueError, "originals are not retained"):
                operation()
            self.assertFalse(self.path.exists())
            self.fixture.fixture.assert_sources_unchanged()
        self.path.write_bytes(raw)
        self.fixture.execute()
        self.assert_pending("effects-returned")

    def test_missing_conflicting_and_symbolic_retained_pins_are_not_repaired(self):
        self.fixture.stage()
        self.fixture.execute()
        original, ref = self.value()["commit"], self.ref()
        self.discovery.git("commit", "--allow-empty", "-m", "different fixture head")
        different = self.discovery.git("rev-parse", "HEAD")
        before = self.path.read_bytes(), self.fixture.path.read_bytes()
        for kind in ("missing", "different", "symbolic"):
            self.discovery.git("update-ref", "--no-deref", "-d", ref)
            if kind == "different":
                self.discovery.git("update-ref", ref, different)
            elif kind == "symbolic":
                self.discovery.git("symbolic-ref", ref, "HEAD")
            for operation in (self.observe, self.fixture.execute,
                              self.fixture.fixture.offer):
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    operation()
            self.assertEqual((self.path.read_bytes(), self.fixture.path.read_bytes()), before)
            if kind == "missing":
                found = subprocess.run(
                    ["git", "-C", self.lib.CORPUS, "rev-parse", "--verify",
                     "--quiet", ref], capture_output=True, timeout=10)
                self.assertEqual(found.returncode, 1)
            elif kind == "different":
                self.assertEqual(self.discovery.git("rev-parse", ref), different)
            else:
                self.assertEqual(self.discovery.git(
                    "symbolic-ref", "--no-recurse", ref), "HEAD")
        self.discovery.git("update-ref", "--no-deref", "-d", ref)
        self.discovery.git("update-ref", ref, original)
        self.assertEqual(len(self.observe()["outcomes"]), 3)

    def test_binding_rejects_changed_admission_or_claims(self):
        claimed = self.fixture.stage()
        self.fixture.execute()
        before = self.path.read_bytes()
        changed = copy.deepcopy(claimed["claims"])
        changed["claims"][0]["sources"][0]["sha256"] = "0" * 64
        for record, claims in (
                (dict(self.fixture.record, transaction="e" * 64), claimed["claims"]),
                (self.fixture.record, changed)):
            with self.lib.corpus_owner(), self.assertRaisesRegex(
                    ValueError, "conflict with retained claims"):
                self.originals.check(self.lib, record, claims)
        self.assertEqual(self.path.read_bytes(), before)
        self.assert_pending("effects-returned")

    def test_wrong_committed_bytes_cannot_create_retention(self):
        claimed = self.fixture.stage()
        source = self.fixture.sources[0]
        source.write_bytes(source.read_bytes() + b"\nconflicting content\n")
        self.discovery.fixture._commit()
        with self.lib.corpus_owner(), self.assertRaisesRegex(
                ValueError, "lacks exact claimed original"):
            self.originals.retain(self.lib, self.fixture.record, claimed["claims"])
        self.assertFalse(self.path.exists())
        self.assertFalse(self.fixture.epoch.exists())
        self.assert_pending("claimed")

    def test_failed_plan_and_retained_writes_preserve_live_sources(self):
        claimed = self.fixture.stage()
        write = self.lib.atomic_write
        for phase in ("planned", "retained"):
            def fail(path, data, **kwargs):
                if str(path) == str(self.path) and json.loads(data)["phase"] == phase:
                    raise OSError("retention writer refused")
                return write(path, data, **kwargs)
            with mock.patch.object(self.lib, "atomic_write", fail):
                with self.assertRaisesRegex(OSError, "retention writer refused"):
                    self.fixture.execute()
            if phase == "planned":
                self.assertFalse(self.path.exists())
            else:
                self.assertEqual(self.value()["phase"], "planned")
                self.assertEqual(self.discovery.git("rev-parse", self.ref()),
                                 self.value()["commit"])
            self.assertEqual(self.fixture.retained(), claimed)
            self.fixture.fixture.assert_sources_unchanged()
        self.fixture.execute()
        self.assert_pending("effects-returned")

    def test_malformed_retained_records_refuse_without_repair(self):
        self.fixture.stage()
        self.fixture.execute()
        value = self.value()
        for changed in (dict(value, phase=True), dict(value, phase="planned"),
                        dict(value, commit=True),
                        dict(value, authority=True), dict(value, schema="unknown")):
            self.path.write_text(json.dumps(changed))
            raw = self.path.read_bytes()
            with self.assertRaises(ValueError):
                self.observe()
            self.assertEqual(self.path.read_bytes(), raw)
            self.assert_pending("effects-returned")
        self.path.write_text(json.dumps(value))
        self.assertEqual(len(self.observe()["outcomes"]), 3)

    def test_planned_pin_conflict_and_creation_failure_preserve_original_plan(self):
        claimed = self.fixture.stage()
        def cut(stage):
            if stage == "originals-planned":
                raise RuntimeError("planned cut")
        with mock.patch.object(self.originals, "_boundary", cut):
            with self.assertRaisesRegex(RuntimeError, "planned cut"):
                self.fixture.execute()
        before = self.path.read_bytes()
        original, ref = self.value()["commit"], self.ref()
        self.discovery.git("commit", "--allow-empty", "-m", "different HEAD")
        different = self.discovery.git("rev-parse", "HEAD")
        self.assertNotEqual(original, different)
        self.discovery.git("update-ref", ref, different)
        with self.assertRaisesRegex(ValueError, "already pinned differently"):
            self.fixture.execute()
        self.assertEqual(self.discovery.git("rev-parse", ref), different)
        self.discovery.git("update-ref", "-d", ref, different)
        run = self.lib._run_bounded_text_process
        def refused(command, **kwargs):
            if "update-ref" in command:
                return subprocess.CompletedProcess(command, 1, "", "injected refusal")
            return run(command, **kwargs)
        with mock.patch.object(self.lib, "_run_bounded_text_process", refused):
            with self.assertRaisesRegex(ValueError, "pin creation failed"):
                self.fixture.execute()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.fixture.retained(), claimed)
        self.fixture.fixture.assert_sources_unchanged()
        self.fixture.execute()
        self.assertEqual(self.value()["commit"], original)
        self.assert_pending("effects-returned")

    def test_retained_record_byte_limit_refuses_before_execution_effects(self):
        claimed = self.fixture.stage()
        def cut(stage):
            if stage == "originals-planned":
                raise RuntimeError("planned cut")
        with mock.patch.object(self.originals, "_boundary", cut):
            with self.assertRaisesRegex(RuntimeError, "planned cut"):
                self.fixture.execute()
        planned = self.value()
        size = len(self.originals._encoded(planned, 4096).encode())
        with mock.patch.object(self.originals, "MAX_RECORD_BYTES", size):
            with self.assertRaisesRegex(ValueError, "exceed their byte bound"):
                self.fixture.execute()
        self.assertEqual(self.value(), planned)
        self.assertEqual(self.fixture.retained(), claimed)
        self.fixture.fixture.assert_sources_unchanged()
        self.fixture.execute()
        self.assert_pending("effects-returned")


if __name__ == "__main__":
    unittest.main()
