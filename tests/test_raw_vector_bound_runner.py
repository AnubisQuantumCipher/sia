"""The benchmark-bound controller must never borrow an ambient model service."""
import contextlib
import copy
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home
from tests import test_raw_vector_runner as fixtures

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
import siavectormodel


class BoundVectorRunner(unittest.TestCase):
    setUp = fixtures.RawVectorRunner.setUp
    _private = fixtures.RawVectorRunner._private

    def _inputs(self):
        self.model_expectations = {
            "package_root": str(self.root / "package"),
            "package_sha256": fixtures.sha(b"package"),
            "model_root": str(self.root / "models"),
            "model_name": "nomic-embed-text:v1.5",
            "manifest_sha256": fixtures.sha(b"model manifest"),
            "release_version": "0.33.2",
            "release_archive_sha256": fixtures.sha(b"release"),
        }
        self.runtime = [{"source": str(self.root / "python"),
                         "destination": "/usr/bin/python3",
                         "sha256": fixtures.sha(b"python")}]
        self.model = SimpleNamespace(identity={
            "model_name": self.model_expectations["model_name"],
            "manifest_sha256": self.model_expectations["manifest_sha256"],
            "package_sha256": self.model_expectations["package_sha256"],
            "non_claims": list(siavectormodel.NON_CLAIMS)})

    def _run(self):
        operation = getattr(self.runner, "observe_bound", None)
        self.assertTrue(callable(operation), "model-bound observation entrypoint must exist")
        return operation(
            executable=str(self.root / "executable"), expected=self.expected,
            build_receipt=str(self.receipt), build_receipt_sha256=self.receipt_sha,
            index_archive=str(self.root / "index.tar"), index_sha256=self.index_sha,
            embedding=self.embedding, queries=self.queries, limit=5, timeout=30,
            scratch_parent=str(self.root), model_expectations=self.model_expectations,
            shared_runtime=self.runtime)

    @contextlib.contextmanager
    def _model(self, **kwargs):
        self.assertEqual(kwargs, self.model_expectations)
        yield self.model

    def _served(self, **kwargs):
        self.assertIs(kwargs["admitted"], self.model)
        self.assertEqual(kwargs["shared_runtime"], self.runtime)
        self.assertEqual(kwargs["snapshot_directory"], str(self.root / "copy-parent"))
        request = copy.deepcopy(kwargs["request"])
        self.requests.append(request)
        if request["operation"] == "query":
            self.assertEqual(request["snapshot"]["logical_sha256"], fixtures.sha(b"logical"))
            self.assertEqual(request["queries"], self.queries)
        return {
            "schema": "sia-raw-vector-served-observation-v1", "status": "observed",
            "model_identity": copy.deepcopy(self.model.identity),
            "launch_config_sha256": fixtures.sha(b"launch"),
            "launch_config": {"model_identity": copy.deepcopy(self.model.identity)},
            "serving_generation": {"model_manifest_sha256": self.model.identity["manifest_sha256"],
                                   "execution_policy": "ollama-cpu-only-v1"},
            "non_claims": list(siavectormodel.NON_CLAIMS),
            "observation": {
                "payload": {"bindings": {"logical_sha256": fixtures.sha(b"logical"),
                                         "catalog_sha256": fixtures.sha(b"catalog")},
                            "results": [], "non_claims": ["adapter boundary"]},
                "request_sha256": fixtures.sha(request["operation"].encode()),
                "executable_sha256": self.expected["executable_sha256"],
                "returncode": 0, "stdout_sha256": fixtures.sha(b"stdout")}}

    @contextlib.contextmanager
    def _controls(self, invoke=None):
        self._inputs()
        self.requests = []
        with mock.patch.object(siavectormodel, "admit_model", side_effect=self._model) as model, \
                mock.patch.object(siavectormodel, "invoke_model_adapter",
                                  side_effect=invoke or self._served) as serving, \
                mock.patch.object(self.runner.siavector, "invoke_adapter") as ambient, \
                mock.patch.object(self.runner.siavector, "private_index_snapshot",
                                  side_effect=self._private) as snapshots, \
                mock.patch.object(self.runner.siavectoradmit, "admit_response",
                                  side_effect=lambda payload, request, **kw: payload) as admission:
            yield model, serving, ambient, snapshots, admission

    def test_capture_and_query_require_the_same_admitted_model_inputs(self):
        with self._controls() as (model, serving, ambient, snapshots, admission):
            result = self._run()
        self.assertEqual([item["operation"] for item in self.requests], ["capture", "query"])
        model.assert_called_once_with(**self.model_expectations)
        self.assertEqual(serving.call_count, 2)
        self.assertEqual(snapshots.call_count, 2)
        self.assertEqual(admission.call_count, 2)
        ambient.assert_not_called()
        self.assertEqual(result["schema"], "sia-raw-vector-bound-observation-v1")
        self.assertEqual(result["model_identity"], self.model.identity)
        self.assertEqual(result["build_non_claims"], self.build["non_claims"])
        self.assertTrue(result["non_claims"])
        for operation in ("capture", "query"):
            self.assertEqual(result[operation]["model_serving"]["non_claims"],
                             siavectormodel.NON_CLAIMS)
            self.assertEqual(result[operation]["payload"]["non_claims"], ["adapter boundary"])

    def test_model_refusal_never_falls_back_or_runs_a_query(self):
        with self._controls(invoke=siavectormodel.ModelRefusal("owned model refused")) as controls:
            with self.assertRaisesRegex(self.runner.siavector.VectorRefusal, "owned model refused"):
                self._run()
        self.assertEqual(controls[1].call_count, 1)
        controls[2].assert_not_called()

    def test_invalid_query_refuses_before_build_or_model_admission(self):
        with self._controls() as controls, \
                mock.patch.object(self.runner.siavector, "sealed_file") as artifact:
            self.queries = [{"id": "empty", "text": ""}]
            with self.assertRaises(self.runner.siavector.VectorRefusal):
                self._run()
        artifact.assert_not_called()
        controls[0].assert_not_called()
        controls[1].assert_not_called()
        controls[2].assert_not_called()

    def test_served_model_identity_cannot_be_substituted(self):
        def substitute(**kwargs):
            result = self._served(**kwargs)
            result["model_identity"]["manifest_sha256"] = fixtures.sha(b"other model")
            return result
        with self._controls(invoke=substitute) as controls:
            with self.assertRaises(self.runner.siavector.VectorRefusal):
                self._run()
        self.assertEqual(controls[1].call_count, 1)
        controls[2].assert_not_called()

    def test_missing_model_inputs_cannot_select_the_diagnostic_lane(self):
        with self._controls() as controls:
            self.model_expectations = None
            with self.assertRaises(self.runner.siavector.VectorRefusal):
                self._run()
        controls[1].assert_not_called()
        controls[2].assert_not_called()


if __name__ == "__main__":
    unittest.main()
