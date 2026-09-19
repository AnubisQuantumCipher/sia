"""Explicit held GET transport controls, not actual gbrain execution.

Compose the real installed-artifact/owner fixture. Only its existing bounded
process provider is controlled. Returned Markdown is a test premise, not an
engine rendering, retained source version, human delivery or no-write proof.
Root alone admits/runs this draft, sequentially. All fixture paths are private.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import contextlib
import copy
import importlib
import inspect
import os
import subprocess
import unittest
from unittest import mock

from tests import test_event_page_plan as page_tests
from tests import test_installed_engine_boundary as boundary_tests


GET_SCHEMA = "sia-installed-overlay-engine-get-transport-v1"
GET_STATUS = "captured-unadmitted-get"
GET_KEYS = boundary_tests.TRANSPORT_KEYS | {"subject"}
TIMEOUT = boundary_tests.TIMEOUT
STDOUT = "---\ntype: note\norigin: model\n---\n\nFixture café and cafe\u0301.\n"
STDERR = "fixture diagnostic, not engine evidence\n"
GET_NON_CLAIMS = [
    "Installed artifact bytes and native descriptor identities are joined to independently supplied expectations; receipts alone do not select or authorize their own expected runtime.",
    "This captures stdout and stderr from one ordinary source-qualified GET through the held executable; it is not a source generation, synchronized index, source-version join, rendered-field admission, output delivery or held-out retrieval evidence.",
    "Ordinary GET is not the no-migrate render-projection operation: connection migrations and retrieval bookkeeping may occur; this transport does not establish whether they occurred or that no engine writes occurred.",
    "GET stdout is the engine's CLI rendition, not necessarily original Markdown bytes; source identity, complete displayed fields and exact current-version fidelity still require separate projection admission.",
    "The existing SIA engine lease coordinates participating local processes; descriptor checks do not protect against hostile same-user mutation or prove receipt build provenance beyond the checked bytes.",
    "No runtime selection, adoption, installation, source publication, memory-use acknowledgment, clock observation, CLI activation, JACKAL assurance or biological cognition is established.",
    "Returned objects remain checked through this context's normal exit; a retained observation is not fresh authority after its descriptor lifetime ends.",
]


class NativeStringSubclass(str):
    pass


class ProviderStop(BaseException):
    pass


class InstalledEngineGetBoundary(unittest.TestCase):
    def setUp(self):
        module = importlib.import_module("siainstalledengine")
        self.assertTrue(callable(getattr(module._Engine, "get", None)),
                        "missing explicit held-engine GET boundary")
        self.assertTrue(hasattr(module, "GET_NON_CLAIMS"))
        self.assertTrue(hasattr(module, "InstalledEngineGetRefusal"))
        self.assertEqual(list(module.GET_NON_CLAIMS), GET_NON_CLAIMS)
        # Missing additive API fails before the real composed setup.
        self.f = boundary_tests.InstalledEngineBoundary(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.module, self.core = self.f.module, self.f.core
        self.subject = self.f.fixture.slug
        self.calls = []
        self.observed_descriptors = None

    @contextlib.contextmanager
    def owned_descriptors(self):
        # Enter after the real caller corpus lease. Runtime module names only:
        # admission.native_owner captures installedengine.os for source chains;
        # core.os provides actual gbrain/lifecycle lease opens.
        actual_open = os.open
        opened = set()

        def observe(*args, **kwargs):
            descriptor = actual_open(*args, **kwargs)
            # Record immediately; do not insert a fallible fstat between
            # native acquisition and the production holder's registration.
            opened.add(descriptor)
            return descriptor

        with contextlib.ExitStack() as stack:
            for module in (self.module, self.core):
                stack.enter_context(mock.patch.object(
                    module, "os", page_tests._ModuleShim(module.os, open=observe)))
            self.observed_descriptors = opened
            try:
                yield opened
            finally:
                self.observed_descriptors = None

    @staticmethod
    def native_identity(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)

    def assert_owned_closed(self, opened):
        self.assertTrue(opened, "control missed actual descriptor acquisitions")
        for descriptor in opened:
            with self.subTest(descriptor=descriptor), self.assertRaises(OSError):
                os.fstat(descriptor)

    def provider(self, command, **kwargs):
        self.assertRegex(command[0], r"\A/proc/self/fd/[0-9]+\Z")
        self.assertRegex(kwargs["cwd"], r"\A/proc/self/fd/[0-9]+\Z")
        executable = int(command[0].rsplit("/", 1)[-1])
        corpus = int(kwargs["cwd"].rsplit("/", 1)[-1])
        self.assertEqual(tuple(command[1:]), ("get", self.subject, "--source", "sia"))
        self.assertEqual(tuple(kwargs["pass_fds"]), (
            executable, corpus, self.core._CORPUS_OWNER_FD.get(),
            self.core._GBRAIN_OWNER_FD.get()))
        for descriptor in kwargs["pass_fds"]:
            os.fstat(descriptor)
        if self.observed_descriptors is not None:
            self.assertNotIn(self.core._CORPUS_OWNER_FD.get(), self.observed_descriptors)
            self.assertTrue(set(kwargs["pass_fds"]) - {self.core._CORPUS_OWNER_FD.get()}
                            <= self.observed_descriptors,
                            "local observer missed inherited owned descriptors")
        self.assertEqual(os.pread(executable, len(b"\x7fELF"), 0), b"\x7fELF")
        self.assertEqual(self.f.identity(os.fstat(executable)),
                         self.f.identity(self.f.fixture.engine_bin.stat()))
        self.assertEqual(self.native_identity(os.fstat(corpus)),
                         self.native_identity(self.f.fixture.corpus.stat()))
        self.assertGreater(self.core._CORPUS_OWNER_DEPTH.get(), 0)
        self.assertEqual(kwargs["timeout"], TIMEOUT)
        self.assertEqual(kwargs["output_limit"],
                         self.f.expectations["limits"]["max_output_bytes"])
        self.assertEqual(kwargs["label"], "installed engine get")
        environment = kwargs["env"]
        self.assertEqual(environment["GBRAIN_HOME"], str(self.f.fixture.share))
        self.assertEqual(environment["BUN_OPTIONS"], "--no-env-file")
        self.assertEqual(environment["GBRAIN_SELF_UPGRADE_MODE"], "off")
        self.assertNotIn("DATABASE_URL", environment)
        self.assertNotIn("GBRAIN_DATABASE_URL", environment)
        self.assertIs(type(environment["GBRAIN_BRAIN_ID"]), str)
        self.assertEqual(environment["GBRAIN_BRAIN_ID"], "host")
        self.assertNotIn("GBRAIN_MOUNTS_PATH", environment)
        self.assertEqual(self.f.scratch(), [])
        self.calls.append((tuple(command), kwargs))
        return subprocess.CompletedProcess(command, 0, stdout=STDOUT, stderr=STDERR)

    def assert_get(self, value, binding):
        self.assertEqual(set(value), GET_KEYS)
        self.assertEqual(value["schema"], GET_SCHEMA)
        self.assertEqual(value["status"], GET_STATUS)
        self.assertEqual(value["operation"], "get")
        self.assertEqual(value["source_id"], "sia")
        self.assertEqual(value["subject"], self.subject)
        self.assertEqual(value["binding_sha256"], binding["binding_sha256"])
        self.assertEqual(value["expected_expectations_sha256"],
                         boundary_tests.existing._digest(self.f.expectations))
        self.assertEqual(value["request_sha256"], boundary_tests.existing._digest({
            "operation": "get", "source_id": "sia", "subject": self.subject,
            "timeout": TIMEOUT,
        }))
        self.assertEqual(value["returncode"], 0)
        self.assertEqual(value["timeout"], TIMEOUT)
        self.assertEqual(value["stdout"], STDOUT)
        self.assertEqual(value["stderr"], STDERR)
        self.assertEqual(value["stdout_sha256"], boundary_tests.sha(STDOUT.encode("utf-8")))
        self.assertEqual(value["stderr_sha256"], boundary_tests.sha(STDERR.encode("utf-8")))
        self.assertEqual(value["non_claims"], list(self.module.GET_NON_CLAIMS))
        self.assertEqual(value["transport_sha256"], boundary_tests.existing._digest(
            {key: item for key, item in value.items() if key != "transport_sha256"}))
        self.assertNotIn("retrieval_bookkeeping_updated", value)
        self.assertNotIn("operation_writes_performed", value)

    def test_explicit_get_contract_exact_argv_premise_and_actual_owned_lifetime(self):
        signature = inspect.signature(self.module._Engine.get)
        self.assertEqual(tuple(signature.parameters), ("self", "subject", "timeout"))
        for name in ("subject", "timeout"):
            self.assertEqual(signature.parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(signature.parameters[name].default, inspect.Parameter.empty)
        with self.core.corpus_owner() as borrowed:
            with self.owned_descriptors() as opened, mock.patch.object(
                    self.core, "_run_bounded_text_process", side_effect=self.provider):
                with self.f.held() as held:
                    binding = held.read()
                    result = held.get(subject=self.subject, timeout=TIMEOUT)
                    self.assert_get(result, binding)
                    self.assertIsNone(held.current())
                    self.assertEqual(self.f.scratch(), [])
                self.assert_owned_closed(opened)
                os.fstat(borrowed)
                self.assertEqual(self.core._CORPUS_OWNER_FD.get(), borrowed)
                self.assertIsNone(self.core._GBRAIN_OWNER_FD.get())
                with self.assertRaises(self.module.InstalledEngineGetRefusal):
                    held.get(subject=self.subject, timeout=TIMEOUT)
        self.assertEqual(len(self.calls), 1)

    def test_native_subject_grammar_and_timeout_refuse_before_process_or_scratch(self):
        capacity = self.module.source._live.activation.MAX_SUBJECT_BYTES
        changes = [{"subject": value} for value in (
            None, True, b"notes/bytes", NativeStringSubclass(self.subject), "",
            "/notes/absolute", "-option", "../parent", "notes/../parent",
            "notes//empty", "notes/trailing/", "Notes/case", "notes/café",
            " notes/space", "notes/space ", "notes/new\nline", "notes\\backslash",
            "notes/" + "a" * capacity,
        )]
        changes.extend({"timeout": value} for value in (None, True, 0, -1, 1.0))
        process = mock.Mock(side_effect=AssertionError("invalid GET reached process"))
        scratch = mock.Mock(side_effect=AssertionError("GET created projection request scratch"))
        with self.core.corpus_owner(), mock.patch.object(
                self.core, "_run_bounded_text_process", process), mock.patch.object(
                self.module, "_RequestFile", scratch):
            for change in changes:
                with self.subTest(change=change), self.assertRaises(
                        self.module.InstalledEngineGetRefusal) as caught:
                    with self.f.held() as held:
                        held.get(**{"subject": self.subject, "timeout": TIMEOUT, **change})
                self.assertEqual(caught.exception.non_claims, list(self.module.GET_NON_CLAIMS))
                self.assertEqual(self.f.scratch(), [])
        process.assert_not_called()
        scratch.assert_not_called()

    def test_closed_get_arguments_and_explicit_small_request_envelope(self):
        process = mock.Mock(side_effect=AssertionError("invalid GET reached process"))
        with self.core.corpus_owner(), mock.patch.object(
                self.core, "_run_bounded_text_process", process):
            for supplied in (
                    {"timeout": TIMEOUT}, {"subject": self.subject},
                    {"subject": self.subject, "timeout": TIMEOUT, "source_id": "foreign"},
                    {"subject": self.subject, "timeout": TIMEOUT, "flags": ["--no-migrate"]}):
                with self.subTest(supplied=supplied):
                    with self.f.held() as held:
                        with self.assertRaises(TypeError):
                            held.get(**supplied)
            small = copy.deepcopy(self.f.expectations)
            small["limits"]["max_request_bytes"] = len(b"{}")
            with self.assertRaises(self.module.InstalledEngineGetRefusal) as caught:
                with self.f.held(expectations=small) as held:
                    held.get(subject=self.subject, timeout=TIMEOUT)
            self.assertEqual(caught.exception.non_claims, list(self.module.GET_NON_CLAIMS))
            self.assertEqual(self.f.scratch(), [])
        process.assert_not_called()

    def test_process_fields_and_combined_utf8_output_remain_strict_and_bounded(self):
        original = copy.deepcopy(self.f.expectations)
        cases = [
            {"returncode": False}, {"returncode": True}, {"returncode": 1}, {"stdout": b"bytes"},
            {"stderr": b"bytes"}, {"stdout": NativeStringSubclass(STDOUT)},
            {"stdout": "\ud800"},
            {"stdout": "abc", "stderr": "", "limit": len(b"{}")},
            {"stdout": "éé", "stderr": "", "limit": len("é".encode("utf-8"))},
            {"stdout": "é", "stderr": "é", "limit": len("é".encode("utf-8"))},
        ]
        with self.core.corpus_owner() as borrowed:
            for change in cases:
                self.f.expectations = copy.deepcopy(original)
                if "limit" in change:
                    self.f.expectations["limits"]["max_output_bytes"] = change["limit"]

                def produce(command, **kwargs):
                    response = self.provider(command, **kwargs)
                    for field in ("returncode", "stdout", "stderr"):
                        if field in change:
                            setattr(response, field, change[field])
                    return response

                with self.subTest(change=change), self.owned_descriptors() as opened, \
                        mock.patch.object(self.core, "_run_bounded_text_process", side_effect=produce):
                    with self.assertRaises(self.module.InstalledEngineGetRefusal) as caught:
                        with self.f.held() as held:
                            held.get(subject=self.subject, timeout=TIMEOUT)
                    self.assertEqual(caught.exception.non_claims, list(self.module.GET_NON_CLAIMS))
                    self.assert_owned_closed(opened)
                    os.fstat(borrowed)
                    self.assertEqual(self.f.scratch(), [])

    def test_process_fields_are_snapshotted_before_later_authority_callback(self):
        produced = []
        changed = []

        def produce(command, **kwargs):
            value = self.provider(command, **kwargs)
            produced.append(value)
            return value

        def authority():
            self.f.check_authority()
            if produced and not changed:
                produced[-1].stdout = "changed mutable producer wrapper after return\n"
                changed.append(True)
            return None

        with self.core.corpus_owner(), mock.patch.object(
                self.core, "_run_bounded_text_process", side_effect=produce):
            with self.f.held(authority=authority) as held:
                binding = held.read()
                result = held.get(subject=self.subject, timeout=TIMEOUT)
                self.assert_get(result, binding)
        self.assertTrue(changed, "control missed the post-process authority callback")

    def test_actual_authority_drift_during_provider_refuses_without_returning_get(self):
        returned = []

        def changed_authority(command, **kwargs):
            value = self.provider(command, **kwargs)
            self.f.authority_path.write_bytes(self.f.authority_bytes + b"changed\n")
            return value

        with self.core.corpus_owner() as borrowed:
            with self.owned_descriptors() as opened, mock.patch.object(
                    self.core, "_run_bounded_text_process", side_effect=changed_authority):
                with self.assertRaises(self.module.InstalledEngineGetRefusal) as caught:
                    with self.f.held() as held:
                        returned.append(held.get(subject=self.subject, timeout=TIMEOUT))
                self.assertEqual(caught.exception.non_claims, list(self.module.GET_NON_CLAIMS))
                self.assertEqual(returned, [])
                self.assert_owned_closed(opened)
                os.fstat(borrowed)
        self.assertEqual(len(self.calls), 1)

    def test_real_engine_owner_exit_cannot_accept_mutated_returned_get(self):
        original_owner = self.core.gbrain_owner
        returned = {}

        @contextlib.contextmanager
        def mutating_exit():
            with original_owner() as descriptor:
                yield descriptor
            returned["get"]["stdout"] = "changed after actual engine-owner exit\n"

        with self.core.corpus_owner() as borrowed:
            with self.owned_descriptors() as opened, mock.patch.object(
                    self.core, "gbrain_owner", mutating_exit), mock.patch.object(
                    self.core, "_run_bounded_text_process", side_effect=self.provider):
                with self.assertRaises(self.module.InstalledEngineGetRefusal) as caught:
                    with self.f.held() as held:
                        returned["get"] = held.get(subject=self.subject, timeout=TIMEOUT)
                self.assertEqual(caught.exception.non_claims, list(self.module.GET_NON_CLAIMS))
                self.assert_owned_closed(opened)
                os.fstat(borrowed)
        self.assertEqual(len(self.calls), 1)

    def test_arbitrary_provider_baseexception_identity_survives_actual_owner_exit_failure(self):
        original_owner = self.core.gbrain_owner
        stop = ProviderStop("actual controlled provider stop")
        reached = []

        @contextlib.contextmanager
        def failing_exit():
            try:
                with original_owner() as descriptor:
                    yield descriptor
            finally:
                raise RuntimeError("owner cleanup must not replace provider BaseException")

        def fail(command, **kwargs):
            self.provider(command, **kwargs)
            reached.append(True)
            raise stop

        with self.core.corpus_owner() as borrowed:
            with self.owned_descriptors() as opened, mock.patch.object(
                    self.core, "gbrain_owner", failing_exit), mock.patch.object(
                    self.core, "_run_bounded_text_process", side_effect=fail):
                with self.assertRaises(ProviderStop) as caught:
                    with self.f.held() as held:
                        held.get(subject=self.subject, timeout=TIMEOUT)
                self.assertIs(caught.exception, stop)
                self.assert_owned_closed(opened)
                os.fstat(borrowed)
        self.assertTrue(reached, "control never reached the bounded provider")
        self.assertEqual(self.f.scratch(), [])


if __name__ == "__main__":
    unittest.main()
