"""Public preparation controller joins admitted build, model and page receipts."""

import contextlib
import copy
import unittest
from unittest import mock

from tests import test_raw_vector_bound_runner as bound
from tests import test_raw_vector_prepare_admission as preparation
from tests import test_raw_vector_runner as fixtures


class BoundVectorPreparer(unittest.TestCase):
    setUp = fixtures.RawVectorRunner.setUp
    _inputs = bound.BoundVectorRunner._inputs
    _model = bound.BoundVectorRunner._model

    def _run(self, **changes):
        operation = getattr(self.runner, "prepare_bound", None)
        self.assertTrue(callable(operation), "public bound preparation controller must exist")
        arguments = dict(
            executable=str(self.root / "executable"), expected=self.expected,
            build_receipt=str(self.receipt), build_receipt_sha256=self.receipt_sha,
            request=self.request, output_directory=str(self.root / "fresh-parent"),
            timeout=30, scratch_parent=str(self.root),
            model_expectations=self.model_expectations, shared_runtime=self.runtime)
        arguments.update(changes)
        return operation(**arguments)

    def _served(self, **kwargs):
        self.assertIs(kwargs["admitted"], self.model)
        self.assertEqual(kwargs["shared_runtime"], self.runtime)
        self.assertEqual(kwargs["request"], self.request)
        self.assertIsNone(kwargs["request"]["output"]["parent_fd"])
        self.assertEqual(kwargs["snapshot_directory"], str(self.root / "fresh-parent"))
        self.assertEqual(kwargs["executable_sha256"], self.expected["executable_sha256"])
        return {
            "schema": "sia-raw-vector-served-observation-v1", "status": "observed",
            "model_identity": copy.deepcopy(self.model.identity),
            "launch_config_sha256": fixtures.sha(b"launch"),
            "launch_config": {"model_identity": copy.deepcopy(self.model.identity)},
            "serving_generation": {"model_manifest_sha256": self.model.identity["manifest_sha256"]},
            "non_claims": list(bound.siavectormodel.NON_CLAIMS),
            "observation": {
                "payload": copy.deepcopy(self.payload), "request_sha256": self.wire["request_sha256"],
                "bound_request_sha256": preparation._sha(preparation._json(self.request)),
                "executable_sha256": self.expected["executable_sha256"],
                "returncode": 0, "stdout_sha256": fixtures.sha(b"stdout")}}

    @contextlib.contextmanager
    def _controls(self, invoke=None):
        self._inputs()
        self.payload, self.request, self.wire = preparation._fixture()
        with mock.patch.object(bound.siavectormodel, "admit_model", side_effect=self._model) as model, \
                mock.patch.object(bound.siavectormodel, "invoke_model_adapter",
                                  side_effect=invoke or self._served) as serving, \
                mock.patch.object(self.runner.siavector, "invoke_adapter") as ambient, \
                mock.patch.object(self.runner.siavector, "private_index_snapshot") as snapshots:
            yield model, serving, ambient, snapshots

    def test_complete_preparation_retains_parent_admitted_receipt_and_model_boundaries(self):
        with self._controls() as controls:
            result = self._run()
        controls[0].assert_called_once_with(**self.model_expectations)
        controls[1].assert_called_once()
        controls[2].assert_not_called()
        controls[3].assert_not_called()
        self.assertEqual(result["schema"], "sia-raw-vector-bound-preparation-v1")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["dataset_sha256"], self.request["dataset_sha256"])
        self.assertEqual(result["pages_sha256"], self.request["pages_sha256"])
        self.assertEqual(result["preparation"]["payload"], self.payload)
        self.assertEqual(result["preparation"]["model_serving"]["non_claims"],
                         bound.siavectormodel.NON_CLAIMS)
        self.assertEqual(result["build_non_claims"], self.build["non_claims"])
        self.assertEqual(result["model_identity"], self.model.identity)
        self.assertTrue(result["non_claims"])

    def test_malformed_page_refuses_before_artifacts_or_models(self):
        with self._controls() as controls, \
                mock.patch.object(self.runner.siavector, "sealed_file") as artifacts:
            self.request["pages"][0]["text"] = "unbound replacement"
            with self.assertRaises(self.runner.siavector.VectorRefusal):
                self._run()
        artifacts.assert_not_called()
        controls[0].assert_not_called()
        controls[1].assert_not_called()

    def test_missing_model_expectations_and_invalid_timeout_never_launch(self):
        with self._controls() as controls:
            self.model_expectations = None
            with self.assertRaises(self.runner.siavector.VectorRefusal):
                self._run()
        controls[0].assert_not_called()
        controls[1].assert_not_called()
        for timeout in (False, 0, "30", float("inf"), float("nan")):
            with self.subTest(timeout=timeout), self._controls() as controls, \
                    mock.patch.object(self.runner.siavector, "sealed_file") as artifacts:
                with self.assertRaises(self.runner.siavector.VectorRefusal):
                    self._run(timeout=timeout)
            artifacts.assert_not_called()
            controls[0].assert_not_called()
            controls[1].assert_not_called()

    def test_foreign_build_refuses_before_model(self):
        with self._controls() as controls:
            self.expected["adapter_sha256"] = fixtures.sha(b"foreign adapter")
            with self.assertRaises(self.runner.siavector.VectorRefusal):
                self._run()
        controls[0].assert_not_called()
        controls[1].assert_not_called()

    def test_complete_parent_admission_rejects_substituted_original_page_receipt(self):
        with self._controls() as controls:
            self.payload["pages"][0]["origin"] = "model"
            with self.assertRaises(self.runner.siavector.VectorRefusal):
                self._run()
        controls[1].assert_called_once()
        controls[2].assert_not_called()

    def test_model_or_original_request_identity_cannot_be_substituted(self):
        for field in ("model", "original-request", "executable", "returncode"):
            def substitute(**kwargs):
                result = self._served(**kwargs)
                if field == "model":
                    result["model_identity"]["manifest_sha256"] = fixtures.sha(b"other")
                elif field == "original-request":
                    result["observation"]["bound_request_sha256"] = fixtures.sha(b"other")
                elif field == "executable":
                    result["observation"]["executable_sha256"] = fixtures.sha(b"other")
                else:
                    result["observation"]["returncode"] = 1
                return result
            with self.subTest(field=field), self._controls(invoke=substitute) as controls:
                with self.assertRaises(self.runner.siavector.VectorRefusal):
                    self._run()
            controls[2].assert_not_called()

    def test_serving_refusal_retains_nonclaims_without_ambient_fallback(self):
        with self._controls(invoke=bound.siavectormodel.ModelRefusal("named refusal")) as controls:
            with self.assertRaisesRegex(self.runner.siavector.VectorRefusal, "named refusal") as raised:
                self._run()
        self.assertEqual(raised.exception.non_claims, bound.siavectormodel.NON_CLAIMS)
        controls[2].assert_not_called()


if __name__ == "__main__":
    unittest.main()
