"""V2 uses one explicitly bound runner family and never an ambient model.

All serving is synthetic. No tests execute a binary, model or real database.
The UTF-8 boundary fixture is JACKAL-first as retained in the admission suite.
"""

import contextlib
import copy
import unittest
from unittest import mock

from tests import test_raw_vector_bound_runner as bound
from tests import test_raw_vector_runner as base
from tests import test_raw_vector_prefix_admission as fixtures


class PrefixRunner(unittest.TestCase):
    setUp = base.RawVectorRunner.setUp
    _inputs = bound.BoundVectorRunner._inputs
    _model = bound.BoundVectorRunner._model
    _private = base.RawVectorRunner._private

    def _function(self, name):
        result = getattr(self.runner, name, None)
        self.assertTrue(callable(result), "explicit v2 entrypoint must exist: " + name)
        return result

    def _run_query(self, **changes):
        arguments = dict(
            executable=str(self.root / "executable"), expected=self.expected,
            build_receipt=str(self.receipt), build_receipt_sha256=self.receipt_sha,
            index_archive=str(self.root / "index.tar"), index_sha256=self.index_sha,
            embedding=self.embedding, queries=self.queries, limit=5, timeout=30,
            scratch_parent=str(self.root), model_expectations=self.model_expectations,
            shared_runtime=self.runtime, embedding_input_policy=self.input_policy,
            expected_embedding_input_policy_sha256=self.input_policy_sha)
        arguments.update(changes)
        return self._function("observe_bound_v2")(**arguments)

    def _run_prepare(self, **changes):
        arguments = dict(
            executable=str(self.root / "executable"), expected=self.expected,
            build_receipt=str(self.receipt), build_receipt_sha256=self.receipt_sha,
            request=self.prepare_request, output_directory=str(self.root / "fresh-parent"),
            timeout=30, scratch_parent=str(self.root), model_expectations=self.model_expectations,
            shared_runtime=self.runtime, expected_embedding_input_policy_sha256=self.input_policy_sha)
        arguments.update(changes)
        return self._function("prepare_bound_v2")(**arguments)

    def _served(self, **kwargs):
        self.assertIs(kwargs["admitted"], self.model)
        self.assertEqual(kwargs["shared_runtime"], self.runtime)
        request = copy.deepcopy(kwargs["request"])
        self.requests.append(request)
        self.assertEqual(request["v"], 2)
        self.assertEqual(request["embedding_input_policy"], self.input_policy)
        self.assertEqual(request["embedding_input_policy_sha256"], self.input_policy_sha)
        self.assertEqual(kwargs["executable_sha256"], self.expected["executable_sha256"])
        sealed = copy.deepcopy(request)
        if request["operation"] == "prepare_index":
            self.assertEqual(kwargs["snapshot_directory"], str(self.root / "fresh-parent"))
            self.assertEqual(request, self.prepare_request)
            payload = copy.deepcopy(self.prepare_payload)
            sealed["output"]["parent_fd"] = 9
        else:
            self.assertEqual(kwargs["snapshot_directory"], str(self.root / "copy-parent"))
            payload, _, _ = fixtures.query_fixture(self.input_policy["mode"], request["operation"])
            payload["bindings"].update(request["binding"])
            payload["bindings"]["config_sha256"] = fixtures.raw._sha(fixtures.raw._json(
                fixtures.configuration(self.embedding, request["limit"], self.input_policy)))
            sealed["snapshot"]["fd"] = 9
        request_sha = fixtures.raw._sha(fixtures.raw._json(sealed))
        payload["bindings"]["request_sha256"] = request_sha
        return {
            "schema": "sia-raw-vector-served-observation-v1", "status": "observed",
            "model_identity": copy.deepcopy(self.model.identity),
            "launch_config_sha256": base.sha(b"owned launch"),
            "launch_config": {"model_identity": copy.deepcopy(self.model.identity)},
            "serving_generation": {"model_manifest_sha256": self.model.identity["manifest_sha256"]},
            "non_claims": list(bound.siavectormodel.NON_CLAIMS),
            "observation": {"payload": payload, "request_sha256": request_sha,
                            "bound_request_sha256": fixtures.raw._sha(fixtures.raw._json(request)),
                            "executable_sha256": self.expected["executable_sha256"],
                            "returncode": 0, "stdout_sha256": base.sha(b"synthetic stdout")}}

    @contextlib.contextmanager
    def _controls(self, mode="nomic-prefix-v1", invoke=None):
        self._inputs()
        _, request, _ = fixtures.query_fixture(mode)
        self.embedding = request["embedding"]
        self.queries = request["queries"]
        self.input_policy = request["embedding_input_policy"]
        self.input_policy_sha = request["embedding_input_policy_sha256"]
        self.prepare_payload, self.prepare_request, _ = fixtures.prepare_fixture(mode)
        self.requests = []
        with mock.patch.object(bound.siavectormodel, "admit_model", side_effect=self._model) as model, \
                mock.patch.object(bound.siavectormodel, "invoke_model_adapter", side_effect=invoke or self._served) as serving, \
                mock.patch.object(self.runner.siavector, "invoke_adapter") as ambient, \
                mock.patch.object(self.runner.siavector, "private_index_snapshot", side_effect=self._private) as snapshots:
            yield {"model": model, "serving": serving, "ambient": ambient, "snapshots": snapshots}

    def test_both_modes_use_same_v2_build_model_and_complete_original_queries(self):
        observations = []
        for mode in ("bare-v1", "nomic-prefix-v1"):
            with self._controls(mode) as controls:
                before = copy.deepcopy(self.queries)
                result = self._run_query()
                self.assertEqual([q["operation"] for q in self.requests], ["capture", "query"])
                self.assertEqual(self.requests[0]["queries"], [])
                self.assertEqual(self.requests[-1]["queries"], before)
                self.assertEqual(self.queries, before)
                self.assertEqual(result["schema"], "sia-raw-vector-bound-observation-v2")
                self.assertEqual(result["embedding_input_policy"], self.input_policy)
                self.assertEqual(result["embedding_input_policy_sha256"], self.input_policy_sha)
                self.assertEqual(result["model_identity"], self.model.identity)
                self.assertEqual(result["build_non_claims"], self.build["non_claims"])
                for operation in ("capture", "query"):
                    self.assertEqual(result[operation]["payload"]["embedding_input_policy"], self.input_policy)
                    self.assertEqual(result[operation]["model_serving"]["non_claims"], bound.siavectormodel.NON_CLAIMS)
                controls["ambient"].assert_not_called()
                observations.append(result)
        for key in ("expected", "build_receipt_sha256", "embedding", "model_identity"):
            self.assertEqual(observations[0][key], observations[-1][key])
        self.assertNotEqual(observations[0]["config_sha256"], observations[-1]["config_sha256"])

    def test_configuration_hash_binds_full_explicit_policy_without_changing_v1(self):
        operation = self._function("configuration_sha256_v2")
        for mode in ("bare-v1", "nomic-prefix-v1"):
            p = fixtures.policy(mode)
            digest = fixtures.raw._sha(fixtures.raw._json(p))
            expected = fixtures.configuration(self.embedding, 5, p)
            self.assertEqual(operation(self.embedding, 5, embedding_input_policy=p,
                                       expected_embedding_input_policy_sha256=digest),
                             fixtures.raw._sha(fixtures.raw._json(expected)))
            del expected["embedding_input_policy"]
            del expected["embedding_input_policy_sha256"]
            self.assertEqual(self.runner.configuration_sha256(self.embedding, 5),
                             fixtures.raw._sha(fixtures.raw._json(expected)))

    def test_external_policy_pin_is_required_before_artifact_or_model_admission(self):
        for kind in ("query", "prepare"):
            with self._controls() as controls, mock.patch.object(self.runner.siavector, "sealed_file") as files:
                run = self._run_query if kind == "query" else self._run_prepare
                for pin in (None, True, "", base.sha(b"independent different policy")):
                    with self.subTest(kind=kind, pin=pin), self.assertRaises(self.runner.siavector.VectorRefusal):
                        run(expected_embedding_input_policy_sha256=pin)
                files.assert_not_called()
                controls["model"].assert_not_called()
                controls["serving"].assert_not_called()
                controls["snapshots"].assert_not_called()
                controls["ambient"].assert_not_called()

    def test_complete_prefixed_query_budget_refuses_before_capture_or_model_launch(self):
        with self._controls() as controls, mock.patch.object(self.runner.siavector, "sealed_file") as files:
            self.queries[0]["text"] = "é" * 3993 + "é"
            with self.assertRaises(self.runner.siavector.VectorRefusal): self._run_query()
            files.assert_not_called()
            controls["model"].assert_not_called()
            controls["serving"].assert_not_called()
            controls["snapshots"].assert_not_called()

    def test_capture_policy_substitution_cannot_authorize_querying_another_index(self):
        def substitute(**kwargs):
            result = self._served(**kwargs)
            payload = result["observation"]["payload"]
            payload["embedding_input_policy"] = fixtures.policy("bare-v1")
            payload["bindings"]["embedding_input_policy_sha256"] = fixtures.raw._sha(
                fixtures.raw._json(payload["embedding_input_policy"]))
            return result
        with self._controls(invoke=substitute) as controls:
            with self.assertRaises(self.runner.siavector.VectorRefusal): self._run_query()
            self.assertEqual([q["operation"] for q in self.requests], ["capture"])
            controls["ambient"].assert_not_called()

    def test_query_provider_input_witness_substitution_refuses_success(self):
        def substitute(**kwargs):
            result = self._served(**kwargs)
            if kwargs["request"]["operation"] == "query":
                result["observation"]["payload"]["results"][0]["embedding_input_sha256"] = base.sha(b"foreign")
            return result
        with self._controls(invoke=substitute) as controls:
            with self.assertRaises(self.runner.siavector.VectorRefusal): self._run_query()
            controls["ambient"].assert_not_called()

    def test_complete_v2_preparation_joins_policy_original_sources_and_model_receipts(self):
        for mode in ("bare-v1", "nomic-prefix-v1"):
            with self._controls(mode) as controls:
                before = copy.deepcopy(self.prepare_request)
                result = self._run_prepare()
                self.assertEqual(result["schema"], "sia-raw-vector-bound-preparation-v2")
                self.assertEqual(result["embedding_input_policy"], self.input_policy)
                self.assertEqual(result["embedding_input_policy_sha256"], self.input_policy_sha)
                self.assertEqual(result["dataset_sha256"], before["dataset_sha256"])
                self.assertEqual(result["pages_sha256"], before["pages_sha256"])
                self.assertEqual(result["preparation"]["payload"], self.prepare_payload)
                self.assertEqual(self.prepare_request, before)
                controls["snapshots"].assert_not_called()
                controls["ambient"].assert_not_called()

    def test_preparation_refuses_substituted_policy_original_origin_and_input_witness(self):
        for kind in ("policy", "origin", "input"):
            with self._controls() as controls:
                if kind == "policy":
                    self.prepare_payload["embedding_input_policy"] = fixtures.policy("bare-v1")
                    self.prepare_payload["bindings"]["embedding_input_policy_sha256"] = fixtures.raw._sha(
                        fixtures.raw._json(self.prepare_payload["embedding_input_policy"]))
                elif kind == "origin": self.prepare_payload["pages"][0]["origin"] = "model"
                else: self.prepare_payload["pages"][0]["chunks"][0]["embedding_input_sha256"] = base.sha(b"other")
                with self.assertRaises(self.runner.siavector.VectorRefusal): self._run_prepare()
                controls["ambient"].assert_not_called()

    def test_build_and_model_identity_still_refuse_without_fallback(self):
        for kind in ("query", "prepare"):
            with self._controls() as controls:
                self.expected["adapter_sha256"] = base.sha(b"wrong new executable source")
                run = self._run_query if kind == "query" else self._run_prepare
                with self.assertRaises(self.runner.siavector.VectorRefusal): run()
                controls["model"].assert_not_called()
                controls["serving"].assert_not_called()
                controls["ambient"].assert_not_called()
                self.expected["adapter_sha256"] = self.build["adapter"]["sha256"]
        with self._controls(invoke=bound.siavectormodel.ModelRefusal("owned model refused")) as controls:
            with self.assertRaisesRegex(self.runner.siavector.VectorRefusal, "owned model refused"):
                self._run_query()
            controls["ambient"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
