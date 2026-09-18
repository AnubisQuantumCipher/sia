"""Installed-overlay transport controls, not actual engine execution proof.

The existing module-qualified fixture owns temporary artifact bytes and actual
SIA corpus/gbrain leases. Its executable is a real copied ELF, but the sole
bounded-process provider is controlled and is never called as a real engine.
Overlay values below are explicit fixture premises, not historical build proof.
Root alone runs this private draft after admission into the repository tests.
"""

import contextlib
import copy
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import types
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_controller_source_engine_generation as existing


REFUSALS = (ValueError, RuntimeError, OSError)
TIMEOUT = 120  # Existing sialib.gbrain default, not a timing claim.
OVERLAY_SHA = hashlib.sha256(b"fixture-only overlay patch bytes").hexdigest()
OVERLAY_TREE = existing.COMMIT
PROJECTION = "get_page_render_projection"
BINDING_KEYS = {
    "schema", "status", "source_id", "expected_expectations_sha256", "pin_fields",
    "artifacts", "corpus", "non_claims", "binding_sha256",
}
TRANSPORT_KEYS = {
    "schema", "status", "operation", "source_id", "binding_sha256",
    "expected_expectations_sha256", "request_sha256", "returncode", "timeout",
    "stdout", "stderr", "stdout_sha256", "stderr_sha256", "non_claims",
    "transport_sha256",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class CallerStop(BaseException):
    pass


class _ObservedOs:
    """Module-local open observer; the shared stdlib object is untouched."""

    def __init__(self, opening):
        self.open = opening

    def __getattr__(self, name):
        return getattr(os, name)


class InstalledEngineBoundary(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "bin" / "siainstalledengine.py"
        self.assertTrue(path.is_file(), "missing installed-overlay engine boundary module")
        self.module = importlib.import_module("siainstalledengine")
        self.hold = getattr(self.module, "hold_overlay_engine", None)
        self.assertTrue(callable(self.hold), "missing installed-overlay engine boundary API")
        # Composition, not subclassing or imported TestCase rediscovery.
        self.fixture = existing.ControllerSourceEngineGeneration(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.core = existing.sialib
        self.owner = self.core.__dict__
        self.calls = []
        self.request_observations = []
        self.authority_calls = []
        self.install_overlay_fixture()
        self.authority_path = self.fixture.state / "fixture-authority"
        self.authority_path.write_bytes(b"explicit fixture authority\n")
        self.authority_bytes = self.authority_path.read_bytes()
        self.authority_identity = self.identity(self.authority_path.stat())
        self.expectations = self.make_expectations()

    @staticmethod
    def identity(info):
        return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns

    def install_overlay_fixture(self):
        f = self.fixture
        lines = []
        for line in f.pin.read_text(encoding="utf-8").splitlines():
            if line.startswith("overlay_sha256="):
                line = "overlay_sha256=" + OVERLAY_SHA
            elif line.startswith("overlay_tree_oid="):
                line = "overlay_tree_oid=" + OVERLAY_TREE
            lines.append(line)
        f.pin.write_text("\n".join(lines) + "\n", encoding="utf-8")
        f.pin_receipt.write_text(
            "managed-by=khephri.sia\nkind=gbrain-pin\n"
            + "path=" + str(f.pin) + "\nsha256=" + sha(f.pin.read_bytes()) + "\n",
            encoding="utf-8")
        f.release_receipt.write_text(
            "managed-by=khephri.sia\ncommit=" + existing.PINNED_COMMIT + "\n"
            + "version=" + existing.VERSION + "\n"
            + "bun_lock_sha256=" + existing.LOCK_SHA256 + "\n"
            + "overlay_sha256=" + OVERLAY_SHA + "\n"
            + "overlay_tree_oid=" + OVERLAY_TREE + "\n"
            + "binary_sha256=" + sha(f.engine_bin.read_bytes()) + "\n",
            encoding="utf-8")

    def make_expectations(self):
        f = self.fixture
        return {
            "schema": "sia-installed-overlay-engine-expectations-v1", "source_id": "sia",
            "commit": existing.PINNED_COMMIT, "version": existing.VERSION,
            "bun_lock_sha256": existing.LOCK_SHA256,
            "overlay_sha256": OVERLAY_SHA, "overlay_tree_oid": OVERLAY_TREE,
            "verified": "2026-08-30",
            "gbrain_pin_sha256": sha(f.pin.read_bytes()),
            "gbrain_pin_receipt_sha256": sha(f.pin_receipt.read_bytes()),
            "gbrain_runtime_receipt_sha256": sha(f.release_receipt.read_bytes()),
            "gbrain_executable_sha256": sha(f.engine_bin.read_bytes()),
            "limits": {
                "max_executable_bytes": self.module.structural.MAX_EXECUTABLE_BYTES,
                "max_metadata_bytes": self.core.MAX_CONFIG_BYTES,
                "max_request_bytes": self.module.structural.MAX_PROJECTION_REQUEST_BYTES,
                "max_output_bytes": min(self.core.MAX_EXTERNAL_OUTPUT_BYTES,
                                        self.core.MAX_STATE_JSON_BYTES),
            },
        }

    def check_authority(self):
        # A real external-currentness callback over an actual fixture file;
        # it does not pretend to be source ACK or index-generation authority.
        current = self.identity(self.authority_path.stat())
        if current != self.authority_identity or self.authority_path.read_bytes() != self.authority_bytes:
            raise RuntimeError("fixture authority changed")
        self.authority_calls.append(current)
        return None

    def held(self, *, expectations=None, expected=None, authority=None):
        value = self.expectations if expectations is None else expectations
        return self.hold(self.owner, expectations=value,
                         expected_expectations_sha256=existing._digest(value) if expected is None else expected,
                         authority_current=self.check_authority if authority is None else authority)

    def request(self):
        page = self.core._corpus_page_version_from_bytes(
            slug=self.fixture.slug, raw=self.fixture.raw.encode("utf-8"))
        # Deliberately supplied GET text, not claimed engine rendering. This
        # boundary captures an opaque projection response, not its admission.
        output = "fixture GET premise\n"
        value = {"source_id": "sia", "source_version": page,
                 "get_stdout": output, "expected_get_stdout_sha256": sha(output.encode("utf-8"))}
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                          allow_nan=False).encode("utf-8") + b"\n"

    def scratch(self):
        return sorted(self.fixture.state.glob("sia-installed-projection-*"))

    @contextlib.contextmanager
    def track_owned_fds(self):
        # Start only after the caller has acquired its real corpus lease.
        actual_open = os.open
        opened = set()

        def opening(*args, **kwargs):
            descriptor = actual_open(*args, **kwargs)
            opened.add(descriptor)
            return descriptor

        # Installed artifact/request opens use this module's os binding.
        # Its _Admission copies that binding into native_owner, so the
        # source._DirectoryChain helpers use the same observer. Real SIA
        # lease opens instead resolve core.os. No queue publisher is called
        # by these controlled version/projection observations.
        observed_os = _ObservedOs(opening)
        previous = getattr(self, "_tracked_owned_fds", None)
        with mock.patch.object(self.module, "os", observed_os), \
                mock.patch.object(self.core, "os", observed_os):
            self.assertIs(os.open, actual_open)
            self._tracked_owned_fds = opened
            try:
                yield opened
            finally:
                self._tracked_owned_fds = previous

    def assert_closed(self, descriptors):
        for descriptor in descriptors:
            with self.subTest(descriptor=descriptor), self.assertRaises(OSError):
                os.fstat(descriptor)

    def provider(self, command, **kwargs):
        self.assertRegex(command[0], r"^/proc/self/fd/[0-9]+$")
        self.assertRegex(kwargs["cwd"], r"^/proc/self/fd/[0-9]+$")
        descriptors = tuple(kwargs["pass_fds"])
        for descriptor in descriptors:
            os.fstat(descriptor)
        executable_fd = int(command[0].rsplit("/", 1)[-1])
        corpus_fd = int(kwargs["cwd"].rsplit("/", 1)[-1])
        self.assertIn(executable_fd, descriptors)
        self.assertIn(corpus_fd, descriptors)
        self.assertEqual(os.pread(executable_fd, 4, 0), b"\x7fELF")
        self.assertEqual(self.identity(os.fstat(executable_fd)),
                         self.identity(self.fixture.engine_bin.stat()))
        self.assertEqual(os.fstat(corpus_fd).st_ino, self.fixture.corpus.stat().st_ino)
        self.assertIn(self.core._CORPUS_OWNER_FD.get(), descriptors)
        self.assertIn(self.core._GBRAIN_OWNER_FD.get(), descriptors)
        tracked = getattr(self, "_tracked_owned_fds", None)
        if tracked is not None:
            borrowed = self.core._CORPUS_OWNER_FD.get()
            self.assertNotIn(borrowed, tracked)
            self.assertTrue((set(descriptors) - {borrowed}).issubset(tracked),
                            "every inherited boundary-owned FD must cross its actual observer")
        self.assertGreater(self.core._CORPUS_OWNER_DEPTH.get(), 0)
        self.assertEqual(kwargs["timeout"], TIMEOUT)
        self.assertEqual(kwargs["output_limit"], self.expectations["limits"]["max_output_bytes"])
        environment = kwargs["env"]
        self.assertEqual(environment["GBRAIN_HOME"], str(self.fixture.share))
        self.assertEqual(environment["BUN_OPTIONS"], "--no-env-file")
        self.assertNotIn("DATABASE_URL", environment)
        self.assertNotIn("GBRAIN_DATABASE_URL", environment)
        self.assertIs(type(environment["GBRAIN_BRAIN_ID"]), str)
        self.assertEqual(environment["GBRAIN_BRAIN_ID"], "host")
        self.assertNotIn("GBRAIN_MOUNTS_PATH", environment)
        self.assertEqual(environment["GBRAIN_SELF_UPGRADE_MODE"], "off")
        args = tuple(command[1:])
        if args == ("--version",):
            stdout = "gbrain " + existing.VERSION + "\n"
        else:
            self.assertEqual(args[:5], ("call", "--no-migrate", "--source", "sia", "--params-file"))
            self.assertEqual(args[-1], PROJECTION)
            self.assertEqual(len(args), 7)
            match = re.fullmatch(r"/proc/self/fd/([0-9]+)/request[.]json", args[5])
            self.assertIsNotNone(match, "request must select a regular leaf through an inherited directory")
            directory_fd = int(match.group(1))
            self.assertIn(directory_fd, descriptors)
            directory = os.fstat(directory_fd)
            self.assertTrue(stat.S_ISDIR(directory.st_mode))
            self.assertEqual(stat.S_IMODE(directory.st_mode), 0o700)
            request_fd = os.open("request.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            try:
                info = os.fstat(request_fd)
                self.assertTrue(stat.S_ISREG(info.st_mode))
                self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
                self.assertEqual(info.st_nlink, 1)
                payload = os.pread(request_fd, info.st_size, 0)
                self.assertEqual(payload, self.request_bytes)
                matching = [descriptor for descriptor in descriptors
                            if self.identity(os.fstat(descriptor)) == self.identity(info)]
                self.assertTrue(matching, "the actual regular request FD must also be inherited")
                directory_path = Path(os.readlink("/proc/self/fd/" + str(directory_fd)))
                self.assertEqual(directory_path.parent, self.fixture.state)
                self.request_observations.append({"directory": directory_path,
                    "directory_fd": directory_fd, "file_fd": matching[0], "payload": payload})
            finally:
                os.close(request_fd)
            stdout = '{"fixture":"unadmitted projection bytes"}\n'
        self.calls.append((tuple(command), kwargs))
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    def test_explicit_api_and_actual_installed_overlay_read_version_project_lifetimes(self):
        signature = inspect.signature(self.hold)
        self.assertEqual(set(signature.parameters), {
            "owner", "expectations", "expected_expectations_sha256", "authority_current"})
        for name in ("expectations", "expected_expectations_sha256", "authority_current"):
            self.assertEqual(signature.parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(signature.parameters[name].default, inspect.Parameter.empty)
        self.request_bytes = self.request()
        with self.core.corpus_owner() as borrowed:
            with self.track_owned_fds() as opened, mock.patch.object(
                    self.core, "_run_bounded_text_process", side_effect=self.provider):
                with self.held() as held:
                    binding = held.read()
                    self.assertEqual(set(binding), BINDING_KEYS)
                    self.assertEqual(binding["status"], "bound-installed-artifacts")
                    self.assertEqual(binding["pin_fields"]["overlay_sha256"], OVERLAY_SHA)
                    self.assertEqual(binding["pin_fields"]["overlay_tree_oid"], OVERLAY_TREE)
                    self.assertEqual(binding["expected_expectations_sha256"], existing._digest(self.expectations))
                    self.assertEqual(binding["non_claims"], list(self.module.NON_CLAIMS))
                    self.assertIsNone(held.current())
                    version = held.version(timeout=TIMEOUT)
                    result = held.project(operation=PROJECTION, request_utf8=self.request_bytes,
                        expected_request_sha256=sha(self.request_bytes), timeout=TIMEOUT)
                    for value in (version, result):
                        self.assertEqual(set(value), TRANSPORT_KEYS)
                        self.assertEqual(value["non_claims"], list(self.module.NON_CLAIMS))
                        self.assertEqual(value["binding_sha256"], binding["binding_sha256"])
                        self.assertEqual(value["stdout_sha256"], sha(value["stdout"].encode("utf-8")))
                    self.assertEqual(version["status"], "observed-version-only")
                    self.assertIsNone(version["request_sha256"])
                    self.assertEqual(result["status"], "captured-unadmitted-projection")
                    self.assertEqual(result["request_sha256"], sha(self.request_bytes))
                    self.assertEqual(self.scratch(), [])
                    self.assert_closed({value[key] for value in self.request_observations
                                        for key in ("directory_fd", "file_fd")})
                self.assert_closed(opened)
                os.fstat(borrowed)
                self.assertIsNone(self.core._GBRAIN_OWNER_FD.get())
                self.assertEqual(self.core._CORPUS_OWNER_FD.get(), borrowed)
                for operation in (held.current, held.read,
                                  lambda: held.version(timeout=TIMEOUT)):
                    with self.assertRaises(REFUSALS):
                        operation()
        self.assertEqual([call[0][1] for call in self.calls], ["--version", "call"])
        self.assertTrue(self.authority_calls)

    def test_missing_external_pin_unentered_owner_and_nonnull_authority_return_refuse_before_provider(self):
        with mock.patch.object(self.core, "_run_bounded_text_process",
                               side_effect=AssertionError("unexpected process")):
            with self.assertRaises(REFUSALS), self.held():
                self.fail("unentered corpus admitted")
            with self.core.corpus_owner():
                for expected in (None, sha(b"wrong external expectation")):
                    with self.subTest(expected=expected), self.assertRaises(REFUSALS):
                        with self.hold(self.owner, expectations=self.expectations,
                                       expected_expectations_sha256=expected,
                                       authority_current=self.check_authority):
                            self.fail("wrong external expectation admitted")
                with self.assertRaises(REFUSALS), self.held(authority=lambda: True):
                    self.fail("authority callback returned a value")
        self.assertEqual(self.scratch(), [])

    def test_closed_expectations_and_overlay_receipt_semantics_not_just_recomputed_artifact_digests(self):
        original_receipt = self.fixture.release_receipt.read_bytes()
        with self.core.corpus_owner(), self.track_owned_fds() as opened, mock.patch.object(
                self.core, "_run_bounded_text_process", side_effect=AssertionError("unexpected process")):
            wrong = copy.deepcopy(self.expectations)
            wrong["allow_pending"] = True
            with self.assertRaises(REFUSALS), self.held(expectations=wrong):
                self.fail("unknown expectation admitted")
            wrong = copy.deepcopy(self.expectations)
            wrong["overlay_tree_oid"] = existing.PINNED_COMMIT
            with self.assertRaises(REFUSALS), self.held(expectations=wrong):
                self.fail("self-selected overlay tree admitted")
            # Authorize the new file digest but NOT a changed semantic overlay
            # relation. Exact receipt-to-pin comparison still has to refuse.
            self.fixture.release_receipt.write_bytes(original_receipt.replace(
                ("overlay_sha256=" + OVERLAY_SHA + "\n").encode("ascii"), b""))
            wrong = copy.deepcopy(self.expectations)
            wrong["gbrain_runtime_receipt_sha256"] = sha(self.fixture.release_receipt.read_bytes())
            with self.assertRaises(REFUSALS), self.held(expectations=wrong):
                self.fail("overlay-less receipt admitted")
            self.assert_closed(opened)
        self.assertEqual(self.scratch(), [])

    def test_closed_projection_operation_source_bytes_digest_and_capacity_before_scratch_or_process(self):
        self.request_bytes = self.request()
        bad_source = self.request_bytes.replace(b'"source_id":"sia"', b'"source_id":"foreign"')
        cases = [
            {"operation": "sync"},
            {"operation": "get_page_projection"},
            {"request_utf8": bytearray(self.request_bytes)},
            {"expected_request_sha256": sha(b"wrong request")},
            {"request_utf8": b'{"source_id":"sia","source_id":"foreign"}',
             "expected_request_sha256": sha(b'{"source_id":"sia","source_id":"foreign"}')},
            {"request_utf8": bad_source, "expected_request_sha256": sha(bad_source)},
            {"request_utf8": b"\xff", "expected_request_sha256": sha(b"\xff")},
            {"timeout": True},
        ]
        with self.core.corpus_owner(), mock.patch.object(
                self.core, "_run_bounded_text_process", side_effect=AssertionError("unexpected process")):
            for change in cases:
                with self.subTest(change=change), self.assertRaises(REFUSALS):
                    with self.held() as held:
                        kwargs = {"operation": PROJECTION, "request_utf8": self.request_bytes,
                                  "expected_request_sha256": sha(self.request_bytes), "timeout": TIMEOUT}
                        kwargs.update(change)
                        held.project(**kwargs)
                self.assertEqual(self.scratch(), [])
            small = copy.deepcopy(self.expectations)
            small["limits"]["max_request_bytes"] = len(b"{}")
            with self.assertRaises(REFUSALS), self.held(expectations=small) as held:
                held.project(operation=PROJECTION, request_utf8=self.request_bytes,
                             expected_request_sha256=sha(self.request_bytes), timeout=TIMEOUT)
            self.assertEqual(self.scratch(), [])

    def test_actual_artifact_replacement_and_authority_file_drift_retire_without_leaking_own_fds(self):
        with self.core.corpus_owner() as borrowed:
            with self.track_owned_fds() as opened:
                with self.assertRaises(REFUSALS), self.held() as held:
                    replacement = self.fixture.root / "replacement-pin"
                    replacement.write_bytes(self.fixture.pin.read_bytes())
                    os.replace(replacement, self.fixture.pin)
                    held.current()
                self.assert_closed(opened)
                os.fstat(borrowed)
            with self.track_owned_fds() as opened:
                with self.assertRaises(REFUSALS), self.held() as held:
                    self.authority_path.write_bytes(self.authority_bytes + b"changed\n")
                    held.current()
                self.assert_closed(opened)
                os.fstat(borrowed)

    def test_actual_lease_context_and_selected_owner_path_drift_refuse(self):
        with self.core.corpus_owner() as borrowed:
            with self.assertRaises(REFUSALS), self.held() as held:
                token = self.core._CORPUS_OWNER_FD.set(None)
                try:
                    held.current()
                finally:
                    self.core._CORPUS_OWNER_FD.reset(token)
            os.fstat(borrowed)
            with self.assertRaises(REFUSALS), self.held() as held:
                with mock.patch.object(self.core, "GBRAIN", str(self.fixture.root / "other-engine")):
                    held.current()
            os.fstat(borrowed)

    def test_mutation_of_actual_request_leaf_is_refused_and_changed_scratch_is_preserved(self):
        self.request_bytes = self.request()

        def change_request(command, **kwargs):
            result = self.provider(command, **kwargs)
            observed = self.request_observations[-1]
            (observed["directory"] / "request.json").write_bytes(self.request_bytes + b"changed\n")
            return result

        with self.core.corpus_owner() as borrowed:
            with self.track_owned_fds() as opened, mock.patch.object(
                    self.core, "_run_bounded_text_process", side_effect=change_request):
                with self.assertRaises(REFUSALS), self.held() as held:
                    held.project(operation=PROJECTION, request_utf8=self.request_bytes,
                                 expected_request_sha256=sha(self.request_bytes), timeout=TIMEOUT)
                self.assert_closed(opened)
                os.fstat(borrowed)
        self.assertEqual(len(self.calls), 1)
        observed = self.request_observations[-1]
        self.assertEqual((observed["directory"] / "request.json").read_bytes(), self.request_bytes + b"changed\n")

    def test_returned_copy_mutation_refuses_before_exposing_read_result_and_closes_fds(self):
        actual_copy = copy.deepcopy

        def changed_copy(value):
            detached = actual_copy(value)
            if isinstance(value, dict) and value.get("schema") == "sia-installed-overlay-engine-binding-v1":
                detached["source_id"] = "changed-copy"
            return detached

        with self.core.corpus_owner() as borrowed:
            with self.track_owned_fds() as opened, mock.patch.object(
                    self.module, "copy", types.SimpleNamespace(deepcopy=changed_copy)):
                with self.assertRaises(REFUSALS), self.held() as held:
                    held.read()
                self.assert_closed(opened)
                os.fstat(borrowed)

    def test_real_engine_owner_normal_exit_checks_mutated_returned_transport(self):
        actual_owner = self.core.gbrain_owner
        result = {}

        @contextlib.contextmanager
        def mutating_exit():
            with actual_owner() as descriptor:
                yield descriptor
            result["returned"]["stdout"] = "mutated after actual engine-owner exit\n"

        with self.core.corpus_owner() as borrowed:
            with self.track_owned_fds() as opened, mock.patch.object(
                    self.core, "gbrain_owner", mutating_exit), mock.patch.object(
                    self.core, "_run_bounded_text_process", side_effect=self.provider):
                with self.assertRaises(REFUSALS), self.held() as held:
                    result["returned"] = held.version(timeout=TIMEOUT)
                self.assert_closed(opened)
                os.fstat(borrowed)
        self.assertEqual(len(self.calls), 1)

    def test_real_nested_corpus_owner_exit_checks_original_expectation_mutation(self):
        actual_owner = self.core.corpus_owner

        @contextlib.contextmanager
        def mutating_exit():
            with actual_owner() as descriptor:
                yield descriptor
            self.expectations["overlay_sha256"] = sha(b"changed expectation at corpus exit")

        with actual_owner() as borrowed:
            with self.track_owned_fds() as opened, mock.patch.object(self.core, "corpus_owner", mutating_exit):
                with self.assertRaises(REFUSALS), self.held() as held:
                    held.read()
                self.assert_closed(opened)
                os.fstat(borrowed)

    def test_caller_baseexception_survives_real_owner_exit_failure_and_handle_retires(self):
        actual_owner = self.core.gbrain_owner
        stop = CallerStop("preserve actual caller exception")

        @contextlib.contextmanager
        def failing_exit():
            try:
                with actual_owner() as descriptor:
                    yield descriptor
            finally:
                raise RuntimeError("cleanup failure must not replace caller exception")

        with self.core.corpus_owner() as borrowed:
            with self.track_owned_fds() as opened, mock.patch.object(self.core, "gbrain_owner", failing_exit):
                with self.assertRaises(CallerStop) as caught:
                    with self.held() as held:
                        held.read()
                        raise stop
                self.assertIs(caught.exception, stop)
                self.assert_closed(opened)
                os.fstat(borrowed)
                with self.assertRaises(REFUSALS):
                    held.current()
        self.assertEqual(self.scratch(), [])


if __name__ == "__main__":
    unittest.main()
