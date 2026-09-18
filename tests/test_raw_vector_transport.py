"""Descriptor and launch contracts for the real vector adapter transport."""

import contextlib
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "bin"))


class RawVectorTransport(unittest.TestCase):
    def setUp(self):
        try:
            self.vector = importlib.import_module("siavector")
        except ModuleNotFoundError as exc:
            self.fail(f"raw-vector transport must exist: {exc}")
        self.root_context = tempfile.TemporaryDirectory()
        self.addCleanup(self.root_context.cleanup)
        self.root = Path(self.root_context.name)
        self.runner = self.root / "runner"
        # This fixture never executes these bytes; the launch observer asserts
        # exact descriptor authority. The real compiled adapter has its own lane.
        self.runner.write_bytes(b"\x7fELFfixture executable")
        self.runner.chmod(0o700)
        self.expected = hashlib.sha256(self.runner.read_bytes()).hexdigest()
        self.database = self.root / "private-index"
        self.database.mkdir(mode=0o700)
        (self.database / "index").mkdir(mode=0o700)

    def _sealed(self, path=None, expected=None, limit=4096):
        return self.vector.sealed_file(
            str(path or self.runner), expected or self.expected,
            max_bytes=limit, executable=True)

    def test_source_bytes_are_sealed_and_path_replacement_is_detected(self):
        with self.assertRaisesRegex(self.vector.VectorRefusal, "changed"), \
                self._sealed() as sealed:
            self.assertEqual(os.pread(sealed.fd, 4096, 0),
                             b"\x7fELFfixture executable")
            required = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW
                        | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
            self.assertEqual(fcntl.fcntl(sealed.fd, fcntl.F_GET_SEALS)
                             & required, required)
            with self.assertRaises(OSError):
                os.pwrite(sealed.fd, b"changed", 0)
            replacement = self.root / "replacement"
            replacement.write_bytes(b"\x7fELFreplaced")
            replacement.chmod(0o700)
            replacement.replace(self.runner)
            self.assertEqual(os.pread(sealed.fd, 4096, 0),
                             b"\x7fELFfixture executable")
            with self.assertRaisesRegex(self.vector.VectorRefusal, "changed"):
                sealed.assert_current()

    def test_digest_budget_type_and_link_guards_precede_launch(self):
        cases = [(self.runner, "0" * 64, 4096),
                 (self.runner, self.expected, 1)]
        link = self.root / "link"
        link.symlink_to(self.runner)
        cases.append((link, self.expected, 4096))
        for path, digest, limit in cases:
            with self.subTest(path=path, digest=digest, limit=limit), \
                    self.assertRaises(self.vector.VectorRefusal):
                with self._sealed(path, digest, limit):
                    self.fail("unsafe source was admitted")
        hardlink = self.root / "hardlink"
        os.link(self.runner, hardlink)
        with self.assertRaises(self.vector.VectorRefusal):
            with self._sealed():
                self.fail("multiply linked source was admitted")

    def _invoke(self, request=None):
        return self.vector.invoke_adapter(
            str(self.runner), self.expected,
            {"operation": "capture", "snapshot": {"fd": None}}
            if request is None else request,
            str(self.database), timeout=10, scratch_parent=str(self.root))

    def test_launch_uses_only_sealed_authority_and_allowlisted_environment(self):
        original = self.runner.stat()
        seen = {}

        def observe(command, **kwargs):
            seen.update(kwargs)
            self.assertEqual(command[1], "--request-fd")
            self.assertEqual(len(command), 3)
            executable_fd = int(command[0].rsplit("/", 1)[1])
            request_fd = int(command[2])
            request_bytes = os.pread(request_fd, 262144, 0)
            request = json.loads(request_bytes)
            database_fd = request["snapshot"]["fd"]
            self.assertEqual(set(kwargs["pass_fds"]),
                             {executable_fd, request_fd, database_fd})
            for descriptor in (executable_fd, request_fd):
                self.assertTrue(fcntl.fcntl(descriptor, fcntl.F_GET_SEALS)
                                & fcntl.F_SEAL_WRITE)
                info = os.fstat(descriptor)
                self.assertNotEqual((info.st_dev, info.st_ino),
                                    (original.st_dev, original.st_ino))
            self.assertEqual(os.fstat(database_fd).st_ino,
                             self.database.stat().st_ino)
            self.assertEqual(set(kwargs["env"]),
                             {"PATH", "LANG", "LC_ALL", "TZ", "HOME",
                              "TMPDIR", "GBRAIN_HOME",
                              "GBRAIN_SKIP_STARTUP_HOOKS"})
            self.assertTrue(kwargs["isolate_process_tree"])
            self.assertNotEqual(kwargs["cwd"], str(REPO))
            return subprocess.CompletedProcess(command, 0, '{"ok":true}\n', '')

        with mock.patch.dict(os.environ,
                             {"NODE_OPTIONS": "ambient", "HTTP_PROXY": "bad",
                              "GBRAIN_SOURCE_BOOST": "bad"}), \
                mock.patch.object(self.vector.sialib,
                                  "_run_bounded_text_process", side_effect=observe):
            result = self._invoke()
        self.assertEqual(result["payload"], {"ok": True})
        self.assertEqual(result["executable_sha256"], self.expected)
        self.assertEqual(result["stdout_sha256"],
                         hashlib.sha256(b'{"ok":true}\n').hexdigest())
        self.assertFalse(Path(seen["cwd"]).exists())

    def test_rejected_output_never_becomes_an_observation(self):
        cases = [(0, '{"ok":true}\n', 'warning'),
                 (1, '{"ok":true}\n', ''),
                 (2, '{"ok":true}\n', ''),
                 (0, '{"status":"refused"}\n', ''),
                 (0, '{"x":1,"x":2}\n', ''),
                 (0, '{"x":NaN}\n', ''),
                 (0, '{"ok":true}', ''),
                 (0, '[]\n', '')]
        for code, stdout, stderr in cases:
            with self.subTest(code=code, stdout=stdout, stderr=stderr), \
                    mock.patch.object(
                        self.vector.sialib, "_run_bounded_text_process",
                        return_value=subprocess.CompletedProcess(
                            [], code, stdout, stderr)), \
                    self.assertRaises(self.vector.VectorRefusal):
                self._invoke()

    def test_named_adapter_refusal_reaches_protocol_admission_unchanged(self):
        payload = {"v": 1, "status": "refused", "lane": "raw_vector",
                   "reason": "snapshot-embedding-mismatch",
                   "non_claims": ["Not a retrieval observation."]}
        with mock.patch.object(
                self.vector.sialib, "_run_bounded_text_process",
                return_value=subprocess.CompletedProcess(
                    [], 2, json.dumps(payload) + "\n", "")):
            result = self._invoke()
        self.assertEqual(result["payload"], payload)
        self.assertEqual(result["returncode"], 2)
        self.assertIs(type(result["wall_elapsed_ns"]), int)
        self.assertGreaterEqual(result["wall_elapsed_ns"], 0)

    def test_process_timeout_is_a_named_transport_refusal(self):
        with mock.patch.object(
                self.vector.sialib, "_run_bounded_text_process",
                side_effect=subprocess.TimeoutExpired("sealed runner", 10)), \
                self.assertRaisesRegex(self.vector.VectorRefusal, "timeout"):
            self._invoke()

    def test_post_execution_generation_change_refuses_complete_output(self):
        def mutate(command, **kwargs):
            self.runner.write_bytes(b"\x7fELFchanged")
            return subprocess.CompletedProcess(command, 0, '{"ok":true}\n', '')
        with mock.patch.object(self.vector.sialib,
                               "_run_bounded_text_process", side_effect=mutate), \
                self.assertRaisesRegex(self.vector.VectorRefusal, "changed"):
            self._invoke()

    def test_request_nonfinite_or_oversized_refuses_before_process(self):
        for request in ({"bad": float("inf")}, {"big": "x" * 262144}):
            with mock.patch.object(self.vector.sialib,
                                   "_run_bounded_text_process") as run, \
                    self.assertRaises(self.vector.VectorRefusal):
                self._invoke(request)
            run.assert_not_called()

    def test_fixed_index_child_cannot_be_a_symlink(self):
        (self.database / "index").rename(self.database / "retained-index")
        (self.database / "index").symlink_to(self.database / "retained-index")
        with mock.patch.object(self.vector.sialib, "_run_bounded_text_process",
                               return_value=subprocess.CompletedProcess([], 0, '{"ok":true}\n', '')) as run, \
                self.assertRaises(self.vector.VectorRefusal):
            self._invoke()
        run.assert_not_called()

    def test_fixed_index_child_generation_is_rechecked_after_execution(self):
        def mutate(command, **kwargs):
            (self.database / "index").rename(self.database / "retained-index")
            (self.database / "index").mkdir(mode=0o700)
            return subprocess.CompletedProcess(command, 0, '{"ok":true}\n', '')
        with mock.patch.object(self.vector.sialib, "_run_bounded_text_process",
                               side_effect=mutate), \
                self.assertRaisesRegex(self.vector.VectorRefusal, "changed"):
            self._invoke()


if __name__ == "__main__":
    unittest.main()
