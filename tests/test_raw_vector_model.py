"""CPU-only private model admission and launch contracts; no real server starts.

Fixture ELF bytes test descriptor authority, not Ollama correctness or successful
loading. The real namespace/model lane remains a separately scheduled root gate.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

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

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "bin"))


class _OsShim:
    """Forward real syscalls except for model-module-local test hooks."""

    def __init__(self, **overrides):
        self._overrides = overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(os, name)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


class RawVectorModelContract(unittest.TestCase):
    def setUp(self):
        try:
            self.model = importlib.import_module("siavectormodel")
        except ModuleNotFoundError as exc:
            self.fail(f"private raw-vector model binding must exist: {exc}")
        self.tmp = tempfile.TemporaryDirectory(prefix="sia-vector-model-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.package = self.root / "package"
        self.library = self.package / "lib" / "ollama"
        self.library.mkdir(parents=True)
        (self.package / "bin").mkdir()
        self._file(self.package / "bin" / "ollama", b"\x7fELFollama", 0o700)
        self._file(self.library / "llama-server", b"\x7fELFrunner", 0o700)
        self._file(self.library / "libggml-base.so.0", b"\x7fELFbase")
        (self.library / "libggml-base.so").symlink_to("libggml-base.so.0")
        self._file(self.library / "libggml-cpu-armv8.0_1.so", b"\x7fELFcpu")
        (self.library / "cuda_v13").mkdir()
        self._file(self.library / "cuda_v13" / "libggml-cuda.so", b"\x7fELFgpu")
        self._file(self.package / ".sia-release", (
            "managed-by=khephri.sia\nversion=0.33.2\n"
            "asset=ollama-linux-arm64.tar.zst\nsha256=" + "a" * 64
            + "\nbinary_sha256=" + digest(b"\x7fELFollama") + "\n").encode())
        self.models = self.root / "models"
        (self.models / "blobs").mkdir(parents=True)
        self.manifest_path = self.models / "manifests" / "registry.ollama.ai" \
            / "library" / "nomic-embed-text" / "v1.5"
        self.manifest_path.parent.mkdir(parents=True)
        self.model_blob = self._blob(b"GGUFfixture model", "application/vnd.ollama.image.model")
        self.config_blob = self._blob(b'{"model_format":"gguf"}',
                                     "application/vnd.docker.container.image.v1+json")
        self.params_blob = self._blob(b'{"num_ctx":8192}',
                                     "application/vnd.ollama.image.params")
        self.manifest = {
            "schemaVersion": 2,
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "config": self.config_blob,
            "layers": [self.model_blob, self.params_blob],
        }
        self._write_manifest()
        self.inventory = self.model.inventory_package(str(self.package))
        self.package_digest = digest(canonical(self.inventory))

    def _file(self, path, data, mode=0o600):
        path.write_bytes(data)
        path.chmod(mode)
        return path

    def _blob(self, data, media_type):
        sha = digest(data)
        self._file(self.models / "blobs" / ("sha256-" + sha), data)
        return {"digest": "sha256:" + sha, "size": len(data), "mediaType": media_type}

    def _write_manifest(self, raw=None):
        data = canonical(self.manifest) if raw is None else raw
        self._file(self.manifest_path, data)
        self.manifest_digest = digest(data)

    def _admit(self, **overrides):
        args = {
            "package_root": str(self.package), "package_sha256": self.package_digest,
            "model_root": str(self.models), "model_name": "nomic-embed-text:v1.5",
            "manifest_sha256": self.manifest_digest,
            "release_version": "0.33.2", "release_archive_sha256": "a" * 64,
        }
        args.update(overrides)
        return self.model.admit_model(**args)

    def test_full_package_provenance_but_only_cpu_and_referenced_model_bytes_sealed(self):
        self.assertIn("lib/ollama/cuda_v13/libggml-cuda.so",
                      [entry["path"] for entry in self.inventory])
        with self._admit() as admitted:
            self.assertEqual(admitted.identity["package_sha256"], self.package_digest)
            self.assertEqual(admitted.identity["manifest_sha256"], self.manifest_digest)
            self.assertEqual(admitted.identity["execution_policy"], "ollama-cpu-only-v1")
            self.assertEqual(admitted.identity["model_name"], "nomic-embed-text:v1.5")
            self.assertIn("lib/ollama/cuda_v13/libggml-cuda.so",
                          admitted.identity["excluded_execution_paths"])
            self.assertTrue(admitted.identity["non_claims"])
            mounts = {item["destination"]: item for item in admitted.mounts}
            self.assertNotIn("/runtime/ollama/lib/ollama/cuda_v13/libggml-cuda.so", mounts)
            self.assertEqual(mounts["/runtime/ollama/lib/ollama/libggml-base.so"]["target"],
                             "libggml-base.so.0")
            for item in admitted.mounts:
                if item["kind"] == "file":
                    fd = item["fd"]
                    self.assertTrue(fcntl.fcntl(fd, fcntl.F_GET_SEALS) & fcntl.F_SEAL_WRITE)
                    self.assertEqual(digest(os.pread(fd, item["bytes"], 0)), item["sha256"])
            admitted.assert_current()

    def test_pinned_package_manifest_release_and_blob_mismatches_refuse(self):
        for changed in ({"package_sha256": "0" * 64},
                        {"manifest_sha256": "0" * 64},
                        {"release_version": "wrong"},
                        {"release_archive_sha256": "0" * 64}):
            with self.subTest(changed=changed), self.assertRaises(self.model.ModelRefusal):
                with self._admit(**changed):
                    self.fail("mismatched expectation admitted")
        blob = self.models / "blobs" / self.model_blob["digest"].replace(":", "-")
        blob.write_bytes(b"changed weights")
        with self.assertRaises(self.model.ModelRefusal):
            with self._admit():
                self.fail("changed weights admitted")

    def test_gpu_change_is_not_hidden_by_cpu_execution_selection(self):
        (self.library / "cuda_v13" / "libggml-cuda.so").write_bytes(b"changed GPU package bytes")
        with self.assertRaises(self.model.ModelRefusal):
            with self._admit():
                self.fail("full package identity ignored excluded GPU bytes")

    def test_model_paths_duplicate_json_reference_types_and_byte_budgets_refuse(self):
        for name in ("nomic-embed-text", "../nomic:v1.5", "nomic:latest", "x:y/z"):
            with self.subTest(name=name), self.assertRaises(self.model.ModelRefusal):
                with self._admit(model_name=name):
                    self.fail("unpinned or unsafe model name admitted")
        self._write_manifest(b'{"schemaVersion":2,"schemaVersion":2}')
        with self.assertRaises(self.model.ModelRefusal):
            with self._admit():
                self.fail("duplicate keys admitted")
        self.manifest["layers"][0]["size"] = True
        self._write_manifest()
        with self.assertRaises(self.model.ModelRefusal):
            with self._admit():
                self.fail("boolean blob size admitted")
        self.manifest["layers"][0]["size"] = self.model.MAX_SEALED_BYTES + 1
        self._write_manifest()
        with self.assertRaises(self.model.ModelRefusal):
            with self._admit():
                self.fail("over-budget model admitted")

    def test_package_links_cannot_escape_cpu_selection_or_hide_mutable_aliases(self):
        link = self.library / "libggml-base.so"
        link.unlink()
        link.symlink_to("cuda_v13/libggml-cuda.so")
        with self.assertRaises(self.model.ModelRefusal):
            self.model.inventory_package(str(self.package))
        link.unlink()
        link.symlink_to("../../../../outside")
        with self.assertRaises(self.model.ModelRefusal):
            self.model.inventory_package(str(self.package))
        link.unlink()
        os.link(self.package / "bin" / "ollama", self.package / "alias")
        with self.assertRaises(self.model.ModelRefusal):
            self.model.inventory_package(str(self.package))

    def test_post_admission_source_generation_change_is_refused(self):
        with self.assertRaises(self.model.ModelRefusal), self._admit() as admitted:
            (self.package / "bin" / "ollama").write_bytes(b"\x7fELFnew generation")
            admitted.assert_current()

    def _plan(self, admitted, **overrides):
        adapter = self._file(self.root / "adapter", b"\x7fELFadapter", 0o700)
        python = self._file(self.root / "python", b"\x7fELFpython", 0o700)
        runtime = self._file(self.root / "libc.so.6", b"\x7fELFlibc")
        index = self.root / "private-index-parent"
        index.mkdir(mode=0o700, exist_ok=True)
        (index / "index").mkdir(mode=0o700, exist_ok=True)
        args = {
            "admitted": admitted, "executable": str(adapter),
            "executable_sha256": digest(adapter.read_bytes()),
            "request": {"v": 1, "operation": "capture", "snapshot": {"fd": None},
                        "embedding": {"model": "ollama:nomic-embed-text:v1.5",
                                      "dimensions": 768,
                                      "endpoint": "http://127.0.0.1:11434/v1"}},
            "snapshot_directory": str(index), "timeout": 10,
            "shared_runtime": [
                {"source": str(python), "destination": "/usr/bin/python3",
                 "sha256": digest(python.read_bytes())},
                {"source": str(runtime), "destination": "/usr/lib/libc.so.6",
                 "sha256": digest(runtime.read_bytes())}],
        }
        args.update(overrides)
        return self.model.launch_plan(**args)

    def test_launch_plan_binds_immutable_cpu_model_config_and_isolates_network(self):
        with self._admit() as admitted, mock.patch.dict(os.environ, {
                "HTTP_PROXY": "http://host", "OLLAMA_HOST": "http://host:11434",
                "OLLAMA_LLM_LIBRARY": "cuda_v13", "PYTHONPATH": "/host"}), \
                self._plan(admitted) as plan:
            argv = plan.argv
            for flag in ("--unshare-user", "--unshare-pid", "--unshare-net",
                         "--unshare-ipc", "--unshare-uts", "--clearenv",
                         "--die-with-parent", "--new-session"):
                self.assertIn(flag, argv)
            self.assertNotIn("--share-net", argv)
            self.assertNotIn("--ro-bind-fd", argv)
            self.assertIn("--ro-bind-data", argv)
            self.assertNotIn(str(self.package), argv)
            self.assertNotIn(str(self.models), argv)
            self.assertNotIn("HTTP_PROXY", plan.environment)
            self.assertNotIn("PYTHONPATH", plan.environment)
            self.assertEqual(plan.environment["OLLAMA_LLM_LIBRARY"], "cpu")
            self.assertEqual(plan.environment["OLLAMA_HOST"], "127.0.0.1:11434")
            self.assertEqual(plan.environment["OLLAMA_MODELS"], "/models")
            self.assertEqual(plan.environment["OLLAMA_NUM_PARALLEL"], "1")
            self.assertEqual(plan.environment["OLLAMA_MAX_LOADED_MODELS"], "1")
            self.assertEqual(plan.environment["OLLAMA_NO_CLOUD"], "1")
            self.assertEqual(plan.environment["OLLAMA_NOPRUNE"], "1")
            self.assertEqual(plan.config["embedding"]["model"], "ollama:nomic-embed-text:v1.5")
            self.assertEqual(plan.config_sha256, digest(canonical(plan.config)))
            self.assertEqual(set(plan.pass_fds), set(plan.input_fds))
            self.assertTrue(plan.non_claims)
            self.assertTrue(any("shared" in text.lower() for text in plan.non_claims))
            self.assertIn("/private-index", argv)
            self.assertIn("/runtime/supervisor.py", argv)

    def test_launch_refuses_model_endpoint_and_unidentified_or_broad_host_runtime(self):
        with self._admit() as admitted:
            for override in (
                {"shared_runtime": []},
                {"shared_runtime": [{"source": "/usr/lib", "destination": "/usr/lib",
                                     "sha256": "0" * 64}]},
                {"request": {"snapshot": {"fd": None}, "embedding": {
                    "model": "ollama:other:v1", "endpoint": "http://127.0.0.1:11434/v1"}}},
                {"request": {"snapshot": {"fd": None}, "embedding": {
                    "model": "ollama:nomic-embed-text:v1.5", "endpoint": "http://host:11434/v1"}}},
            ):
                with self.subTest(override=override), self.assertRaises(self.model.ModelRefusal):
                    with self._plan(admitted, **override):
                        self.fail("unsafe launch admitted")

    def test_readonly_runtime_roots_are_actual_mounts_before_remount(self):
        with self._admit() as admitted, self._plan(admitted) as plan:
            argv = plan.argv
            mounts = {argv[index + 1] for index, token in enumerate(argv[:-1])
                      if token == "--tmpfs"}
            readonly = {argv[index + 1] for index, token in enumerate(argv[:-1])
                        if token == "--remount-ro"}
            self.assertEqual(readonly, {"/runtime", "/models", "/usr", "/empty"})
            self.assertTrue(readonly <= mounts,
                            "bwrap cannot remount a plain --dir mount-table entry")
            for root in readonly:
                self.assertLess(argv.index(root), argv.index("--remount-ro"))

    def test_dynamic_loader_is_an_executable_sealed_runtime_leaf(self):
        python = self._file(self.root / "python", b"\x7fELFpython", 0o700)
        loader = self._file(self.root / "loader", b"\x7fELFloader", 0o700)
        runtime = [{"source": str(python), "destination": "/usr/bin/python3",
                    "sha256": digest(python.read_bytes())},
                   {"source": str(loader), "destination": "/usr/lib/ld-linux-aarch64.so.1",
                    "sha256": digest(loader.read_bytes())}]
        with self._admit() as admitted, self._plan(admitted, shared_runtime=runtime) as plan:
            arguments = iter(plan.argv)
            permissions = None
            mounted = {}
            for token in arguments:
                if token == "--perms":
                    permissions = next(arguments)
                elif token == "--ro-bind-data":
                    descriptor = int(next(arguments))
                    destination = next(arguments)
                    mounted[destination] = (permissions, os.fstat(descriptor).st_mode & 0o111)
            self.assertEqual(mounted["/usr/lib/ld-linux-aarch64.so.1"], ("0500", 0o100))

    def test_model_service_generation_change_refuses_and_reaps_only_owned_service(self):
        service = mock.Mock(pid=321)
        service.poll.return_value = None
        service.wait.return_value = 0
        config = {"model_name": "nomic-embed-text:v1.5", "timeout": 10}
        generation = {"service": {"pid": 321, "starttime": "one"},
                      "runner": {"pid": 322, "starttime": "one"}}
        changed = {"service": generation["service"],
                   "runner": {"pid": 323, "starttime": "two"}}
        kill = mock.Mock()
        with mock.patch.object(self.model, "_spawn_service", return_value=service), \
                mock.patch.object(self.model, "_warm_model"), \
                mock.patch.object(self.model, "_serving_generation", side_effect=[generation, changed]), \
                mock.patch.object(self.model, "_invoke_in_namespace", return_value={"ok": True}), \
                mock.patch.object(self.model, "os", _OsShim(kill=kill)), \
                self.assertRaisesRegex(self.model.ModelRefusal, "generation"):
            self.model.run_owned_session(config)
        service.terminate.assert_called_once_with()
        service.wait.assert_called()
        kill.assert_not_called()

    def test_service_failure_never_borrows_existing_endpoint_or_invokes_adapter(self):
        service = mock.Mock(pid=321)
        service.poll.return_value = 1
        with mock.patch.object(self.model, "_spawn_service", return_value=service), \
                mock.patch.object(self.model, "_warm_model") as warm, \
                mock.patch.object(self.model, "_invoke_in_namespace") as invoke, \
                self.assertRaises(self.model.ModelRefusal):
            self.model.run_owned_session({"model_name": "nomic-embed-text:v1.5", "timeout": 10})
        warm.assert_not_called()
        invoke.assert_not_called()
        service.wait.assert_called()

    def test_adapter_timeout_reaps_owned_namespace_service_and_retains_refusal(self):
        service = mock.Mock(pid=321)
        service.poll.return_value = None
        service.wait.side_effect = [subprocess.TimeoutExpired("owned", 1), 0]
        with mock.patch.object(self.model, "_spawn_service", return_value=service), \
                mock.patch.object(self.model, "_warm_model"), \
                mock.patch.object(self.model, "_serving_generation", return_value={"runner": "fixed"}), \
                mock.patch.object(self.model, "_invoke_in_namespace",
                                  side_effect=subprocess.TimeoutExpired("adapter", 1)), \
                self.assertRaisesRegex(self.model.ModelRefusal, "timeout"):
            self.model.run_owned_session({"model_name": "nomic-embed-text:v1.5", "timeout": 10})
        service.terminate.assert_called_once_with()
        service.kill.assert_called_once_with()
        self.assertEqual(service.wait.call_count, 2)

    def test_release_metadata_ceiling_precedes_whole_body_allocation(self):
        original_pread = os.pread

        def bounded_pread(fd, count, offset):
            self.assertLessEqual(count, 64,
                                 "release receipt was allocated before its metadata ceiling")
            return original_pread(fd, count, offset)

        with mock.patch.object(self.model, "MAX_JSON_BYTES", 64), \
                mock.patch.object(self.model, "os", _OsShim(pread=mock.Mock(side_effect=bounded_pread))), \
                self.assertRaisesRegex(self.model.ModelRefusal, "metadata|receipt"):
            with self._admit():
                self.fail("oversized release metadata was admitted")

    def test_stable_owned_service_returns_generation_and_nonclaims_then_is_reaped(self):
        service = mock.Mock(pid=321)
        service.poll.return_value = None
        service.wait.return_value = 0
        config = {"model_name": "nomic-embed-text:v1.5", "timeout": 10}
        generation = {"service": {"pid": 321, "starttime": "same"},
                      "runner": {"pid": 322, "starttime": "same"}}
        observation = {"payload": {"status": "observed", "non_claims": ["adapter boundary"]}}
        with mock.patch.object(self.model, "_spawn_service", return_value=service) as spawn, \
                mock.patch.object(self.model, "_warm_model") as warm, \
                mock.patch.object(self.model, "_serving_generation", return_value=generation) as check, \
                mock.patch.object(self.model, "_invoke_in_namespace", return_value=observation) as invoke:
            result = self.model.run_owned_session(config)
        spawn.assert_called_once_with(config)
        warm.assert_called_once_with(config, service)
        invoke.assert_called_once_with(config)
        self.assertEqual(check.call_args_list, [mock.call(config, service), mock.call(config, service)])
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["serving_generation"], generation)
        self.assertEqual(result["observation"], observation)
        self.assertEqual(result["launch_config_sha256"], digest(canonical(config)))
        self.assertEqual(result["non_claims"], self.model.NON_CLAIMS)
        service.terminate.assert_called_once_with()
        service.wait.assert_called_once_with(timeout=1)

    def test_adapter_producer_ceiling_reaps_the_owned_fixture_process(self):
        # Only this known Python byte producer executes, never a model, adapter
        # or namespace. Exercise the real bounded pipe drain, not fabricated IO.
        original_popen = subprocess.Popen
        spawned = []
        command = [sys.executable, "-I", "-S", "-B", "-c",
                   "import os; os.write(1, b'x' * 4096); os.write(2, b'y' * 4096)"]

        def fixture_popen(argv, **kwargs):
            self.assertEqual(argv, command)
            kwargs["cwd"] = str(self.root)
            process = original_popen(argv, **kwargs)
            spawned.append(process)
            return process

        with mock.patch.object(self.model, "MAX_OUTPUT_BYTES", 8), \
                mock.patch.object(subprocess, "Popen", side_effect=fixture_popen), \
                self.assertRaisesRegex(self.model.ModelRefusal, "byte ceiling"):
            self.model._bounded_adapter(command, (), 10)
        self.assertTrue(spawned)
        self.assertIsNotNone(spawned[0].poll())
        self.assertTrue(spawned[0].stdout.closed)
        self.assertTrue(spawned[0].stderr.closed)

    def test_runtime_file_replacement_is_detected_after_immutable_mount_admission(self):
        with self._admit() as admitted, self.assertRaisesRegex(self.model.ModelRefusal, "generation"), \
                self._plan(admitted) as plan:
            target = "/usr/lib/libc.so.6"
            position = plan.argv.index(target)
            descriptor = int(plan.argv[position - 1])
            self.assertEqual(os.pread(descriptor, 4096, 0), b"\x7fELFlibc")
            replacement = self._file(self.root / "replacement-libc", b"\x7fELFreplaced")
            replacement.replace(self.root / "libc.so.6")
            self.assertEqual(os.pread(descriptor, 4096, 0), b"\x7fELFlibc")

    def test_fixed_index_child_replacement_cannot_inherit_parent_descriptor_authority(self):
        with self._admit() as admitted, self.assertRaisesRegex(self.model.ModelRefusal, "index.*generation"), \
                self._plan(admitted):
            parent = self.root / "private-index-parent"
            (parent / "index").rename(parent / "previous-index")
            (parent / "index").mkdir(mode=0o700)

    def test_process_probe_binds_inode_from_the_open_executable_descriptor(self):
        observed = self.model._process(os.getpid())
        expected = os.stat("/proc/self/exe")
        self.assertEqual(observed.get("executable_device"), expected.st_dev)
        self.assertEqual(observed.get("executable_inode"), expected.st_ino)

    def test_mounted_executable_identity_hashes_nofollow_regular_leaf(self):
        probe = getattr(self.model, "_mounted_executable_identity", None)
        self.assertTrue(callable(probe), "explicit immutable mount identity probe must exist")
        target = self.package / "bin" / "ollama"
        observed = probe(str(target))
        expected = target.stat()
        self.assertEqual(observed["device"], expected.st_dev)
        self.assertEqual(observed["inode"], expected.st_ino)
        self.assertEqual(observed["sha256"], digest(target.read_bytes()))
        alias = self.root / "executable-alias"
        alias.symlink_to(target)
        with self.assertRaises(self.model.ModelRefusal):
            probe(str(alias))

    def _serving_probe_fixture(self, *, changed=None):
        service = mock.Mock(pid=321)
        service.poll.return_value = None
        parent_stat = (self.package / "bin" / "ollama").stat()
        runner_stat = (self.library / "llama-server").stat()
        parent = {
            "pid": 321, "ppid": 320, "starttime": "parent-generation",
            "executable": "/bwrap-copy/anonymous-ollama (deleted)",
            "executable_device": parent_stat.st_dev, "executable_inode": parent_stat.st_ino,
            "executable_sha256": digest(b"\x7fELFollama"),
            "argv": ["/runtime/ollama/bin/ollama", "serve"],
            "network_namespace": "net:[fixture]",
        }
        model_path = "/models/blobs/" + self.model_blob["digest"].replace(":", "-")
        runner = {
            "pid": 322, "ppid": 321, "starttime": "runner-generation",
            "executable": "/bwrap-copy/anonymous-runner (deleted)",
            "executable_device": runner_stat.st_dev, "executable_inode": runner_stat.st_ino,
            "executable_sha256": digest(b"\x7fELFrunner"),
            "argv": ["/runtime/ollama/lib/ollama/llama-server", "--model", model_path],
            "network_namespace": "net:[fixture]",
        }
        mounted = {
            "/runtime/ollama/bin/ollama": {"device": parent_stat.st_dev, "inode": parent_stat.st_ino,
                                           "sha256": parent["executable_sha256"]},
            "/runtime/ollama/lib/ollama/llama-server": {"device": runner_stat.st_dev, "inode": runner_stat.st_ino,
                                                       "sha256": runner["executable_sha256"]},
        }
        config = {"model_name": "nomic-embed-text:v1.5", "model_identity": {
            "ollama_sha256": parent["executable_sha256"], "runner_sha256": runner["executable_sha256"],
            "model_path": model_path, "manifest_sha256": self.manifest_digest}}
        if changed:
            selected, field, value = changed
            (parent if selected == "service" else runner)[field] = value
        response = {"models": [{"digest": self.manifest_digest,
                                "name": "nomic-embed-text:v1.5", "size_vram": 0}]}
        processes = {321: parent, 322: runner}
        return service, config, processes, mounted, response

    def test_serving_executable_display_alias_is_not_mistaken_for_object_authority(self):
        service, config, processes, mounted, response = self._serving_probe_fixture()
        with mock.patch.object(self.model, "_process", side_effect=processes.__getitem__), \
                mock.patch.object(self.model, "_mounted_executable_identity", create=True,
                                  side_effect=mounted.__getitem__) as mount_probe, \
                mock.patch.object(self.model, "os", _OsShim(listdir=mock.Mock(return_value=["321", "322"]))), \
                mock.patch.object(self.model, "_api", return_value=response):
            try:
                result = self.model._serving_generation(config, service)
            except self.model.ModelRefusal as exc:
                self.fail("same sealed executable inode/hash was rejected by display alias: " + str(exc))
        self.assertEqual(result["service"], processes[321])
        self.assertEqual(result["runner"], processes[322])
        self.assertEqual(set(call.args[0] for call in mount_probe.call_args_list), set(mounted))

    def test_serving_executable_inode_device_or_hash_mismatch_refuses(self):
        for changed in (("service", "executable_inode", -1),
                        ("runner", "executable_inode", -1),
                        ("service", "executable_device", -1),
                        ("runner", "executable_device", -1),
                        ("service", "executable_sha256", "0" * 64),
                        ("runner", "executable_sha256", "0" * 64)):
            service, config, processes, mounted, response = self._serving_probe_fixture(changed=changed)
            with self.subTest(changed=changed), \
                    mock.patch.object(self.model, "_process", side_effect=processes.__getitem__), \
                    mock.patch.object(self.model, "_mounted_executable_identity", create=True,
                                      side_effect=mounted.__getitem__), \
                    mock.patch.object(self.model, "os", _OsShim(listdir=mock.Mock(return_value=["321", "322"]))), \
                    mock.patch.object(self.model, "_api", return_value=response), \
                    self.assertRaises(self.model.ModelRefusal):
                self.model._serving_generation(config, service)


if __name__ == "__main__":
    unittest.main()
