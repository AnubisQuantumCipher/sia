"""Fixed host at the actual bounded-provider seam, not engine execution proof.

The module-qualified existing fixture supplies real temporary installed files,
external pins and SIA leases. Only the process provider is controlled. This
test does not evaluate the resolver or claim its supplied stdout is real GET.
The separate compiled hostile-ancestor extension exercises the real resolver.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import importlib
import os
import subprocess
import unittest
from unittest import mock

from tests import test_installed_engine_boundary as boundary_tests


GET_STDOUT = "fixture GET premise\n"
PROJECTION_STDOUT = '{"fixture":"unadmitted projection bytes"}\n'


class InstalledEngineFixedHost(unittest.TestCase):
    def setUp(self):
        module = importlib.import_module("siainstalledengine")
        self.assertTrue(callable(getattr(module._Engine, "get", None)),
                        "missing explicit held-engine GET boundary")
        # Composition only: no imported TestCase alias/subclass rediscovery.
        self.f = boundary_tests.InstalledEngineBoundary(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.core = self.f.core

    def test_get_version_and_projection_fix_host_despite_ambient_selectors(self):
        subject = self.f.fixture.slug
        request = self.f.request()
        calls = []
        hostile = {
            "GBRAIN_BRAIN_ID": "fixture-other",
            "GBRAIN_MOUNTS_PATH": str(self.f.fixture.root / "absent-mounts.json"),
            "GBRAIN_SOURCE": "fixture-other",
        }

        def provider(command, **kwargs):
            # Reach the genuine held-file/lease seam before checking the
            # new selection requirement. Never call the copied ELF here.
            self.assertRegex(command[0], r"\A/proc/self/fd/[0-9]+\Z")
            self.assertRegex(kwargs["cwd"], r"\A/proc/self/fd/[0-9]+\Z")
            executable = int(command[0].rsplit("/", 1)[-1])
            corpus = int(kwargs["cwd"].rsplit("/", 1)[-1])
            descriptors = tuple(kwargs["pass_fds"])
            for descriptor in descriptors:
                os.fstat(descriptor)
            self.assertIn(executable, descriptors)
            self.assertIn(corpus, descriptors)
            self.assertIn(self.core._CORPUS_OWNER_FD.get(), descriptors)
            self.assertIn(self.core._GBRAIN_OWNER_FD.get(), descriptors)
            self.assertEqual(self.f.identity(os.fstat(executable)),
                             self.f.identity(self.f.fixture.engine_bin.stat()))
            self.assertEqual(os.fstat(corpus).st_ino, self.f.fixture.corpus.stat().st_ino)
            self.assertGreater(self.core._CORPUS_OWNER_DEPTH.get(), 0)
            self.assertEqual(kwargs["timeout"], boundary_tests.TIMEOUT)
            self.assertEqual(kwargs["output_limit"],
                             self.f.expectations["limits"]["max_output_bytes"])
            environment = kwargs["env"]
            calls.append(tuple(command[1:]))
            self.assertEqual(environment.get("GBRAIN_BRAIN_ID"), "host",
                             "fixed-host selector absent or overridden at bounded GET provider")
            self.assertIs(type(environment["GBRAIN_BRAIN_ID"]), str)
            self.assertEqual(environment["HOME"], self.core.HOME)
            self.assertEqual(environment["GBRAIN_HOME"], str(self.f.fixture.share))
            self.assertEqual(environment["BUN_OPTIONS"], "--no-env-file")
            self.assertNotIn("GBRAIN_MOUNTS_PATH", environment)
            self.assertNotIn("GBRAIN_SOURCE", environment)
            self.assertNotIn("DATABASE_URL", environment)
            self.assertNotIn("GBRAIN_DATABASE_URL", environment)
            self.assertIsNot(environment, self.core.GBRAIN_ENV)
            args = tuple(command[1:])
            if args == ("get", subject, "--source", "sia"):
                self.assertEqual(descriptors, (
                    executable, corpus, self.core._CORPUS_OWNER_FD.get(),
                    self.core._GBRAIN_OWNER_FD.get()))
                self.assertEqual(self.f.scratch(), [])
                stdout = GET_STDOUT
            elif args == ("--version",):
                stdout = "gbrain " + boundary_tests.existing.VERSION + "\n"
            else:
                self.assertEqual(args[:5],
                                 ("call", "--no-migrate", "--source", "sia", "--params-file"))
                self.assertEqual(args[-1], boundary_tests.PROJECTION)
                stdout = PROJECTION_STDOUT
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        # Neither the parent's process environment nor the owner module's
        # convenience command environment may select this held transaction.
        with mock.patch.dict(os.environ, hostile), mock.patch.object(
                self.core, "GBRAIN_ENV", dict(hostile)), self.core.corpus_owner() as borrowed:
            with mock.patch.object(self.core, "_run_bounded_text_process", side_effect=provider):
                with self.f.held() as held:
                    binding = held.read()
                    # GET first: the unpatched RED reaches GET, not version
                    # setup or an inherited test provider's old assertion.
                    result = held.get(subject=subject, timeout=boundary_tests.TIMEOUT)
                    self.assertEqual(result["stdout"], GET_STDOUT)
                    self.assertEqual(result["status"], "captured-unadmitted-get")
                    self.assertEqual(result["request_sha256"], boundary_tests.existing._digest({
                        "operation": "get", "source_id": "sia", "subject": subject,
                        "timeout": boundary_tests.TIMEOUT,
                    }))
                    self.assertNotIn("operation_writes_performed", result)
                    self.assertNotIn("retrieval_bookkeeping_updated", result)
                    version = held.version(timeout=boundary_tests.TIMEOUT)
                    projection = held.project(
                        operation=boundary_tests.PROJECTION, request_utf8=request,
                        expected_request_sha256=boundary_tests.sha(request),
                        timeout=boundary_tests.TIMEOUT)
                    for captured in (result, version, projection):
                        self.assertEqual(captured["binding_sha256"], binding["binding_sha256"])
                        self.assertEqual(captured["source_id"], "sia")
                    self.assertIsNone(held.current())
                os.fstat(borrowed)
                self.assertEqual(self.core._CORPUS_OWNER_FD.get(), borrowed)
                self.assertIsNone(self.core._GBRAIN_OWNER_FD.get())
        self.assertEqual([args[0] for args in calls], ["get", "--version", "call"])
        self.assertEqual(self.f.scratch(), [])
        self.assertTrue(self.f.authority_calls)


if __name__ == "__main__":
    unittest.main()
