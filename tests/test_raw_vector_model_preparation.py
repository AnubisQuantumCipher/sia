"""Owned private model preparation transport; fixtures never launch a server."""

try:
    import sia_test_home
    import test_raw_vector_model as fixtures
except ModuleNotFoundError:
    from tests import sia_test_home
    from tests import test_raw_vector_model as fixtures

import copy
import fcntl
import os
import subprocess
import unittest
from unittest import mock


class RawVectorModelPreparation(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RawVectorModelContract(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.model = self.fixture.model
        self.parent = self.fixture.root / "preparation-output"
        self.parent.mkdir(mode=0o700)

    def _request(self, *, large=False):
        text = "a" * 65536 if large else "A frozen evidence page."
        pages = [{"slug": "event/page" + str(index), "title": "Fixture", "type": "event",
                  "origin": "evidence", "text": text, "text_sha256": fixtures.digest(text.encode())}
                 for index in range(20 if large else 1)]
        return {"v": 1, "operation": "prepare_index", "source": "sia",
                "dataset_sha256": "a" * 64, "pages_sha256": fixtures.digest(fixtures.canonical(pages)),
                "embedding": {"model": "ollama:nomic-embed-text:v1.5", "dimensions": 768,
                              "endpoint": "http://127.0.0.1:11434/v1"},
                "output": {"parent_fd": None}, "pages": pages}

    def _plan(self, admitted, request=None):
        return self.fixture._plan(admitted, snapshot_directory=str(self.parent),
                                  request=self._request() if request is None else request)

    def _request_fd(self, plan):
        position = plan.argv.index("/runtime/request.json")
        self.assertEqual(plan.argv[position - 2], "--ro-bind-data")
        return int(plan.argv[position - 1])

    def test_prepare_request_is_separate_sealed_input_with_explicit_larger_wire_ceiling(self):
        request = self._request(large=True)
        raw = fixtures.canonical(request)
        self.assertGreater(len(raw), self.model.MAX_JSON_BYTES)
        with self.fixture._admit() as admitted:
            try:
                with self._plan(admitted, request) as plan:
                    self.assertEqual(self.model.MAX_PREPARE_REQUEST_BYTES, 8388608)
                    self.assertEqual(self.model.MAX_QUERY_REQUEST_BYTES, 262144)
                    self.assertNotIn("request", plan.config)
                    self.assertEqual(plan.config["operation"], "prepare_index")
                    self.assertEqual(plan.config["request_sha256"], fixtures.digest(raw))
                    self.assertEqual(plan.config["request_bytes"], len(raw))
                    self.assertLessEqual(len(fixtures.canonical(plan.config)), self.model.MAX_JSON_BYTES)
                    descriptor = self._request_fd(plan)
                    self.assertEqual(os.pread(descriptor, len(raw), 0), raw)
                    self.assertTrue(fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) & fcntl.F_SEAL_WRITE)
                    self.assertFalse((self.parent / "index").exists())
                    (self.parent / "index").mkdir(mode=0o700)
            except self.model.ModelRefusal as exc:
                self.fail("bounded preparation request was rejected: " + str(exc))
        self.assertEqual(request["output"], {"parent_fd": None})

    def test_prepare_requires_empty_owned_parent_and_absent_fixed_child(self):
        for kind in ("directory", "file", "symlink", "nonempty-parent", "public-parent"):
            parent = self.fixture.root / ("output-" + kind)
            parent.mkdir(mode=0o700)
            child = parent / "index"
            if kind == "directory":
                child.mkdir(mode=0o700)
            elif kind == "file":
                child.write_bytes(b"do not replace")
            elif kind == "symlink":
                child.symlink_to(self.fixture.root / "absent-target")
            elif kind == "nonempty-parent":
                (parent / "unrelated").write_bytes(b"do not delete")
            else:
                parent.chmod(0o755)
            with self.subTest(kind=kind), self.fixture._admit() as admitted, \
                    self.assertRaises(self.model.ModelRefusal):
                with self.fixture._plan(admitted, snapshot_directory=str(parent), request=self._request()):
                    self.fail("nonfresh preparation authority admitted")
            self.assertTrue(parent.exists())

    def test_success_requires_created_ordinary_private_child_and_failure_retains_partial_output(self):
        with self.fixture._admit() as admitted:
            for kind in ("missing", "public", "symlink", "file"):
                parent = self.fixture.root / ("created-" + kind)
                parent.mkdir(mode=0o700)
                entered = False
                with self.subTest(kind=kind), self.assertRaisesRegex(self.model.ModelRefusal, "index"):
                    with self.fixture._plan(admitted, snapshot_directory=str(parent), request=self._request()):
                        entered = True
                        if kind == "public":
                            (parent / "index").mkdir(mode=0o755)
                        elif kind == "symlink":
                            (parent / "index").symlink_to(self.parent)
                        elif kind == "file":
                            (parent / "index").write_bytes(b"partial")
                self.assertTrue(entered, "preparation refused before admitting its empty parent")
                if kind != "missing":
                    self.assertTrue(os.path.lexists(parent / "index"))
            with self.assertRaisesRegex(self.model.ModelRefusal, "fixture failed"):
                with self._plan(admitted):
                    (self.parent / "index").mkdir(mode=0o700)
                    (self.parent / "index" / "partial").write_bytes(b"retain diagnosis")
                    raise self.model.ModelRefusal("fixture failed")
        partial = self.parent / "index" / "partial"
        self.assertTrue(partial.is_file(), "failed preparation output was deleted")
        self.assertEqual(partial.read_bytes(), b"retain diagnosis")

    def test_preparation_capacity_does_not_widen_default_metadata_parsing_or_sealing(self):
        self.assertEqual(self.model.MAX_JSON_BYTES, 1048576)
        oversized = b"x" * self.model.MAX_JSON_BYTES + b"x"
        with self.assertRaises(self.model.ModelRefusal):
            with self.model._sealed_bytes(oversized):
                self.fail("preparation widened the default metadata sealing ceiling")
        with self.assertRaises(self.model.ModelRefusal):
            self.model._json(b'"' + oversized + b'"')

    def test_operation_specific_request_limits_precede_runtime_snapshotting(self):
        for operation, amount in (("prepare_index", 8388608), ("capture", 262144)):
            request = self._request()
            request["operation"] = operation
            if operation == "capture":
                request.pop("output")
                request["snapshot"] = {"fd": None}
            request["padding"] = "x" * amount
            with self.subTest(operation=operation), self.fixture._admit() as admitted, \
                    mock.patch.object(self.model, "_sealed_file",
                                      side_effect=AssertionError("request budget was checked after runtime allocation")), \
                    self.assertRaisesRegex(self.model.ModelRefusal, "request.*ceiling|request.*budget"):
                with self._plan(admitted, request):
                    self.fail("operation request ceiling was not enforced")

    def test_bound_request_reader_rejects_changed_digest_length_operation_and_role(self):
        reader = getattr(self.model, "_read_bound_request", None)
        self.assertTrue(callable(reader), "separate sealed request reader must exist")
        request = self._request()
        raw = fixtures.canonical(request)
        source = self.fixture.root / "bound-request.json"
        source.write_bytes(raw)
        original_open = self.model._open

        def open_request(path, flags):
            return original_open(str(source) if path == "/runtime/request.json" else path, flags)

        config = {"operation": "prepare_index", "request_sha256": fixtures.digest(raw),
                  "request_bytes": len(raw), "embedding": request["embedding"]}
        with mock.patch.object(self.model, "_open", side_effect=open_request):
            self.assertEqual(reader(config), request)
            for patch in ({"request_sha256": "0" * 64}, {"request_bytes": 1},
                          {"operation": "capture"}):
                with self.subTest(patch=patch), self.assertRaises(self.model.ModelRefusal):
                    reader({**config, **patch})
            for invalid in ({**request, "snapshot": {"fd": None}},
                            {**request, "output": {"parent_fd": 7}}):
                changed = fixtures.canonical(invalid)
                source.write_bytes(changed)
                with self.assertRaises(self.model.ModelRefusal):
                    reader({**config, "request_sha256": fixtures.digest(changed), "request_bytes": len(changed)})

    def test_inner_preparer_receives_only_output_parent_fd_and_distinct_wire_identity(self):
        self.assertTrue(callable(getattr(self.model, "_read_bound_request", None)),
                        "bound request reader must exist")
        request = self._request()
        raw = fixtures.canonical(request)
        config = {"operation": "prepare_index", "request_sha256": fixtures.digest(raw),
                  "request_bytes": len(raw), "embedding": request["embedding"],
                  "adapter_sha256": "b" * 64, "timeout": 10}
        parent_fd = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, parent_fd)
        original_open = os.open
        observed = {}

        def open_parent(path, flags, *args, **kwargs):
            if path == "/private-index":
                return os.dup(parent_fd)
            return original_open(path, flags, *args, **kwargs)

        def invoke(argv, descriptors, timeout):
            bound_parent, request_fd = descriptors
            wire = os.pread(request_fd, 8388608, 0)
            payload = self.model._json(wire)
            self.assertEqual(payload["output"], {"parent_fd": bound_parent})
            self.assertNotIn("snapshot", payload)
            self.assertEqual(os.fstat(bound_parent).st_ino, self.parent.stat().st_ino)
            observed["wire"] = wire
            (self.parent / "index").mkdir(mode=0o700)
            return subprocess.CompletedProcess(argv, 0,
                b'{"v":1,"status":"ok","operation":"prepare_index","non_claims":["preparer boundary"]}\n', b"")

        with mock.patch.object(self.model, "_read_bound_request", return_value=copy.deepcopy(request)), \
                mock.patch.object(os, "open", side_effect=open_parent), \
                mock.patch.object(self.model, "_bounded_adapter", side_effect=invoke):
            result = self.model._invoke_in_namespace(config)
        self.assertEqual(result["bound_request_sha256"], fixtures.digest(raw))
        self.assertEqual(result["request_sha256"], fixtures.digest(observed["wire"]))
        self.assertNotEqual(result["bound_request_sha256"], result["request_sha256"])
        self.assertEqual(result["payload"]["non_claims"], ["preparer boundary"])
        self.assertEqual(request["output"], {"parent_fd": None})

    def test_inner_preparer_named_refusal_retains_partial_index_without_success_envelope(self):
        request = self._request()
        config = {"operation": "prepare_index", "request_sha256": fixtures.digest(fixtures.canonical(request)),
                  "adapter_sha256": "b" * 64, "timeout": 10}
        original_open = os.open

        def open_parent(path, flags, *args, **kwargs):
            return original_open(str(self.parent) if path == "/private-index" else path,
                                 flags, *args, **kwargs)

        def refuse(argv, descriptors, timeout):
            (self.parent / "index").mkdir(mode=0o700)
            (self.parent / "index" / "partial").write_bytes(b"retain this refusal")
            return subprocess.CompletedProcess(argv, 2,
                b'{"v":1,"status":"refused","operation":"prepare_index","reason":"fixture-embedding-failed",'
                b'"non_claims":["partial index is not complete"]}\n', b"")

        with mock.patch.object(self.model, "_read_bound_request", return_value=copy.deepcopy(request)), \
                mock.patch.object(os, "open", side_effect=open_parent), \
                mock.patch.object(self.model, "_bounded_adapter", side_effect=refuse), \
                self.assertRaisesRegex(self.model.ModelRefusal, "fixture-embedding-failed"):
            self.model._invoke_in_namespace(config)
        partial = self.parent / "index" / "partial"
        self.assertTrue(partial.is_file(), "refusal output was deleted")
        self.assertEqual(partial.read_bytes(), b"retain this refusal")


if __name__ == "__main__":
    unittest.main()
