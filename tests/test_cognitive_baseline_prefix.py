"""Additive explicit embedding-input baseline contracts; root executes only.

These are complete synthetic signed-history/model/process/transport fixtures,
not retained machine queries or outcomes. V2 changes only the bytes submitted
for embedding after lossless document chunking and before query embedding.
Existing v1 public APIs, source text, queries, occurrence targets and metric
definitions must retain their meaning. No metric expression is evaluated here.

The fixture adapts the existing full v1 producer double to the agreed v2 wire
contract, then exercises real baseline and pure measurement admission. Numeric
constants are existing fixture/source literals; no new derived result is claimed.
"""

import contextlib
import copy
import importlib
import inspect
import json
from pathlib import Path
import unittest
from unittest import mock

from tests import test_cognitive_baseline as baseline_tests
from tests import test_cognitive_command as command_tests
from tests import test_cognitive_measurement as measurement_tests
from tests import test_raw_vector_admission as raw_tests
from tests import test_raw_vector_prepare_admission as prepare_tests


sha = baseline_tests.sha
canonical = baseline_tests.canonical
body_digest = baseline_tests._body_digest
PREFIX_NON_CLAIMS = [
    "Embedding input prefixes affect only provider input; original query, page and chunk text identities are retained.",
    "Embedding-input digests bind adapter-supplied UTF-8 text, not an independently observed HTTP body or proof of model computation.",
]
NON_CLAIMS_V2 = [*baseline_tests.NON_CLAIMS, *PREFIX_NON_CLAIMS]


def embedding_policy(mode="bare-v1"):
    if mode not in ("bare-v1", "nomic-prefix-v1"):
        raise ValueError("fixture policy mode must be explicit")
    return {
        "schema": "sia-embedding-input-policy-v1", "mode": mode,
        "document_prefix": "search_document: " if mode == "nomic-prefix-v1" else "",
        "query_prefix": "search_query: " if mode == "nomic-prefix-v1" else "",
        "encoding": "utf-8", "document_stage": "after-lossless-chunking",
        "query_stage": "original-query", "overflow": "refuse",
    }


class PrefixBaselineFixture(unittest.TestCase):
    """Reusable real v2 fixture, with the legacy fixture's public helper shape."""

    setUp = baseline_tests.CognitiveBaseline.setUp
    _capture = baseline_tests.CognitiveBaseline._capture
    _build = baseline_tests.CognitiveBaseline._build
    _freeze = baseline_tests.CognitiveBaseline._freeze
    _queries = baseline_tests.CognitiveBaseline._queries
    _model_identity = baseline_tests.CognitiveBaseline._model_identity
    _process_generation = baseline_tests.CognitiveBaseline._process_generation
    _serving = baseline_tests.CognitiveBaseline._serving
    _no_success = baseline_tests.CognitiveBaseline._no_success

    def _module(self):
        module = importlib.import_module("siacognitivebaseline")
        self.assertTrue(callable(getattr(module, "run_baseline_v2", None)),
                        "additive explicit-prefix baseline API is missing")
        return module

    def _inputs(self, module, split="calibration", mode="bare-v1"):
        baseline_tests.CognitiveBaseline._inputs(self, module, split)
        policy = embedding_policy(mode)
        self.kw.update(embedding_input_policy=policy,
                       expected_embedding_input_policy_sha256=sha(canonical(policy)))

    def _contract(self):
        result = baseline_tests.CognitiveBaseline._contract(self)
        result.update(schema="sia-cognitive-baseline-contract-v2",
                      embedding_input_policy=copy.deepcopy(self.kw["embedding_input_policy"]),
                      embedding_input_policy_sha256=self.kw["expected_embedding_input_policy_sha256"])
        return result

    def _policy_fields(self):
        return {"embedding_input_policy": copy.deepcopy(self.kw["embedding_input_policy"]),
                "embedding_input_policy_sha256": self.kw["expected_embedding_input_policy_sha256"]}

    def _request(self, operation, queries, roots):
        return {
            "v": 2, "lane": "raw_vector", "operation": operation,
            "queries": copy.deepcopy(queries) if operation == "query" else [],
            "limit": self.kw["limit"], "embedding": copy.deepcopy(self.kw["embedding"]),
            "snapshot": {"fd": None, **(roots if operation == "query" else {
                "logical_sha256": None, "catalog_sha256": None})},
            "binding": {"executable_sha256": self.kw["adapter"]["expected"]["executable_sha256"],
                        "build_receipt_sha256": self.kw["adapter"]["build_receipt_sha256"]},
            **self._policy_fields(),
        }

    def _rebind(self, observation, request, role):
        wire = copy.deepcopy(request)
        if request["operation"] == "prepare_index":
            wire["output"]["parent_fd"] = 9
        else:
            wire["snapshot"]["fd"] = 9
        original_sha = sha(canonical(request))
        wire_sha = sha(canonical(wire))
        observation["bound_request_sha256"] = original_sha
        observation["request_sha256"] = wire_sha
        observation["payload"]["bindings"]["request_sha256"] = wire_sha
        observation["model_serving"] = self._serving(
            request["operation"], self.kw[role]["expected"]["executable_sha256"], original_sha)
        # Canonical JSON is only this synthetic producer's chosen wire format.
        # Real stdout remains an opaque digest, never reconstructed by replay.
        observation["stdout_sha256"] = sha(canonical(observation["payload"]))

    def _prepare(self, **kwargs):
        self.assertEqual(kwargs["expected_embedding_input_policy_sha256"],
                         self.kw["expected_embedding_input_policy_sha256"])
        request = kwargs["request"]
        expected = {"v": 2, "operation": "prepare_index", "source": "sia",
                    "dataset_sha256": self.kw["expected_selection_sha256"],
                    "pages_sha256": self.kw["selection"]["pages_sha256"],
                    "embedding": self.kw["embedding"], "output": {"parent_fd": None},
                    "pages": self.kw["selection"]["pages"], **self._policy_fields()}
        self.assertEqual(request, expected)
        legacy_kwargs = {key: value for key, value in kwargs.items()
                         if key != "expected_embedding_input_policy_sha256"}
        legacy_kwargs["request"] = {key: copy.deepcopy(value) for key, value in request.items()
                                    if key not in self._policy_fields()}
        legacy_kwargs["request"]["v"] = 1
        result = baseline_tests.CognitiveBaseline._prepare(self, **legacy_kwargs)
        result.update(schema="sia-raw-vector-bound-preparation-v2", **self._policy_fields())
        observation = result["preparation"]
        payload = observation["payload"]
        payload["v"] = 2
        payload["non_claims"] = [*prepare_tests.NON_CLAIMS, *PREFIX_NON_CLAIMS]
        payload["embedding_input_policy"] = copy.deepcopy(self.kw["embedding_input_policy"])
        payload["bindings"]["embedding_input_policy_sha256"] = self.kw["expected_embedding_input_policy_sha256"]
        prefix = self.kw["embedding_input_policy"]["document_prefix"]
        for prepared, page in zip(payload["pages"], request["pages"], strict=True):
            for chunk, text in zip(prepared["chunks"], prepare_tests._chunks(page["text"]), strict=True):
                submitted = (prefix + text).encode("utf-8")
                chunk.update(embedding_input_sha256=sha(submitted), embedding_input_bytes=len(submitted))
        self._rebind(observation, request, "preparer")
        self.prepared_result = copy.deepcopy(result)
        return result

    def _observe(self, **kwargs):
        self.assertEqual(kwargs["embedding_input_policy"], self.kw["embedding_input_policy"])
        self.assertEqual(kwargs["expected_embedding_input_policy_sha256"],
                         self.kw["expected_embedding_input_policy_sha256"])
        legacy_kwargs = {key: value for key, value in kwargs.items()
                         if key not in ("embedding_input_policy", "expected_embedding_input_policy_sha256")}
        result = baseline_tests.CognitiveBaseline._observe(self, **legacy_kwargs)
        runner = importlib.import_module("siavectorrun")
        config_sha = runner.configuration_sha256_v2(
            kwargs["embedding"], kwargs["limit"], embedding_input_policy=kwargs["embedding_input_policy"],
            expected_embedding_input_policy_sha256=kwargs["expected_embedding_input_policy_sha256"])
        result.update(schema="sia-raw-vector-bound-observation-v2", config_sha256=config_sha,
                      **self._policy_fields())
        roots = {key: result["capture"]["payload"]["bindings"][key]
                 for key in ("logical_sha256", "catalog_sha256")}
        queries = {row["id"]: row["text"] for row in kwargs["queries"]}
        for operation in ("capture", "query"):
            observation = result[operation]
            payload = observation["payload"]
            payload.update(v=2, embedding_input_policy=copy.deepcopy(self.kw["embedding_input_policy"]))
            payload["non_claims"] = [*raw_tests.NON_CLAIMS, *PREFIX_NON_CLAIMS]
            payload["bindings"].update(config_sha256=config_sha,
                embedding_input_policy_sha256=self.kw["expected_embedding_input_policy_sha256"])
            for row in payload["results"]:
                submitted = (self.kw["embedding_input_policy"]["query_prefix"] + queries[row["id"]]).encode("utf-8")
                row.update(embedding_input_sha256=sha(submitted), embedding_input_bytes=len(submitted))
            self._rebind(observation, self._request(operation, kwargs["queries"], roots), "adapter")
        self.observed_result = copy.deepcopy(result)
        return result

    @contextlib.contextmanager
    def _controls(self, prepare=None, observe=None):
        runner = importlib.import_module("siavectorrun")
        # create=True lets the missing baseline API be the initial RED reason;
        # no absent controller is silently implemented by a test double.
        with (mock.patch.object(runner, "prepare_bound_v2", create=True,
                                side_effect=prepare or self._prepare) as preparing,
              mock.patch.object(runner, "observe_bound_v2", create=True,
                                side_effect=observe or self._observe) as observing,
              mock.patch.object(runner, "prepare_bound", side_effect=AssertionError("v1 preparer fallback forbidden")),
              mock.patch.object(runner, "observe_bound", side_effect=AssertionError("v1 observer fallback forbidden")),
              mock.patch.object(runner, "observe", side_effect=AssertionError("ambient observer forbidden")) as ambient,
              mock.patch.object(runner.siavector, "invoke_adapter", side_effect=AssertionError("ambient adapter forbidden")),
              mock.patch.object(self.bench, "run", side_effect=AssertionError("hybrid benchmark forbidden")),
              mock.patch("subprocess.Popen", side_effect=AssertionError("fixture launched a child"))):
            yield preparing, observing, ambient

    def _run(self):
        return self.module.run_baseline_v2(**self.kw)

    def _source_inputs(self):
        metric = measurement_tests.policy_fixture()
        return {
            **{key: copy.deepcopy(self.kw[key]) for key in (
                "capture", "expected_capture_sha256", "selection_policy", "expected_policy_sha256",
                "selection", "expected_selection_sha256")},
            "baseline_contract": self._contract(),
            "expected_baseline_contract_sha256": sha(canonical(self._contract())),
            "metric_policy": metric, "expected_metric_policy_sha256": sha(canonical(metric)),
        }

    @contextlib.contextmanager
    def _pure(self):
        runner = importlib.import_module("siavectorrun")
        with (mock.patch("builtins.open", side_effect=AssertionError("pure replay opened file")),
              mock.patch("os.open", side_effect=AssertionError("pure replay opened descriptor")),
              mock.patch("os.scandir", side_effect=AssertionError("pure replay enumerated sources")),
              mock.patch("subprocess.Popen", side_effect=AssertionError("pure replay launched child")),
              mock.patch.object(runner, "prepare_bound_v2", create=True, side_effect=AssertionError("pure preparation")),
              mock.patch.object(runner, "observe_bound_v2", create=True, side_effect=AssertionError("pure observation")),
              mock.patch.object(runner, "prepare_bound", side_effect=AssertionError("pure v1 preparation")),
              mock.patch.object(runner, "observe_bound", side_effect=AssertionError("pure v1 observation"))):
            yield

    def _measurement(self, source, protocol, baseline):
        module = importlib.import_module("siacognitivemeasure")
        with self._pure():
            return module.prepare_measurement(
                **source, protocol=protocol, expected_protocol_sha256=protocol["protocol_sha256"],
                baseline=baseline, expected_baseline_sha256=baseline["artifact_sha256"],
                expected_parameter_freeze_sha256=self.kw["expected_parameter_freeze_sha256"])


class CognitiveBaselinePrefix(PrefixBaselineFixture):
    def test_additive_explicit_api_does_not_change_legacy_signature(self):
        module = self._module()
        old = inspect.signature(module.run_baseline).parameters
        new = inspect.signature(module.run_baseline_v2).parameters
        fields = {"embedding_input_policy", "expected_embedding_input_policy_sha256"}
        self.assertTrue(fields.isdisjoint(old))
        self.assertEqual(set(new), set(old) | fields)
        for name in fields:
            self.assertEqual(new[name].kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(new[name].default, inspect.Parameter.empty)

    def test_both_explicit_modes_preserve_sources_queries_rows_origins_and_raw_latency(self):
        module = self._module()
        for mode in ("bare-v1", "nomic-prefix-v1"):
            with self.subTest(mode=mode):
                self._inputs(module, mode=mode)
                self.kw["output_directory"] = str(self.root / ("output-" + mode))
                before = copy.deepcopy(self.kw)
                with self._controls() as controls:
                    result = self._run()
                self.assertEqual(self.kw, before)
                controls[0].assert_called_once()
                controls[1].assert_called_once()
                controls[2].assert_not_called()
                self.assertEqual(result["schema"], "sia-cognitive-baseline-v2")
                self.assertEqual(result["contract"], self._contract())
                self.assertEqual(result["baseline_contract_sha256"], sha(canonical(self._contract())))
                for key, value in self._policy_fields().items():
                    self.assertEqual(result[key], value)
                self.assertEqual(result["queries"], self._queries())
                self.assertEqual(result["pages"], self.kw["selection"]["pages"])
                ids = {row["id"] for row in self._queries()}
                self.assertEqual(result["answer_key"], [row for row in self.kw["selection"]["answer_key"] if row["id"] in ids])
                self.assertEqual(result["preparation"], self.prepared_result)
                self.assertEqual(result["observation"], self.observed_result)
                self.assertEqual(result["non_claims"], NON_CLAIMS_V2)
                self.assertEqual(result["artifact_sha256"], body_digest(result, "artifact_sha256"))
                self.assertEqual(json.loads((Path(self.kw["output_directory"]) / "baseline.json").read_bytes()), result)
                for result_row in result["observation"]["query"]["payload"]["results"]:
                    original = next(row["text"] for row in self._queries() if row["id"] == result_row["id"])
                    self.assertEqual(result_row["query_sha256"], sha(original.encode("utf-8")))
                    submitted = (self.kw["embedding_input_policy"]["query_prefix"] + original).encode("utf-8")
                    self.assertEqual(result_row["embedding_input_sha256"], sha(submitted))
                    self.assertEqual(result_row["embedding_input_bytes"], len(submitted))
                for forbidden in ("metrics", "recall", "mrr", "win", "significance"):
                    self.assertNotIn(forbidden, result)

    def test_invalid_or_unpinned_policy_refuses_before_files_and_controllers(self):
        module = self._module()
        self._inputs(module)
        valid = copy.deepcopy(self.kw)
        mutations = [("expected_embedding_input_policy_sha256", None),
                     ("expected_embedding_input_policy_sha256", True),
                     ("expected_embedding_input_policy_sha256", sha(b"foreign policy")),
                     ("embedding_input_policy", None), ("embedding_input_policy", True),
                     ("embedding_input_policy", {**embedding_policy(), "hidden": "not ignored"}),
                     ("embedding_input_policy", {**embedding_policy(), "query_prefix": "search_query: "}),
                     ("embedding_input_policy", {**embedding_policy(), "mode": "automatic"})]
        cycle = embedding_policy()
        cycle["hidden"] = cycle
        mutations.append(("embedding_input_policy", cycle))
        for key, value in mutations:
            self.kw = {**valid, key: value}
            if key == "embedding_input_policy" and type(value) is dict and value is not cycle:
                self.kw["expected_embedding_input_policy_sha256"] = sha(canonical(value))
            with (self.subTest(key=key, kind=type(value).__name__), self._controls() as controls,
                  mock.patch.object(module, "_Directory", side_effect=AssertionError("opened before policy refusal"))):
                with self.assertRaises(module.BaselineRefusal):
                    self._run()
                controls[0].assert_not_called()
                controls[1].assert_not_called()
        self.assertFalse(Path(valid["output_directory"]).exists())

    def test_complete_policy_bounds_precede_copy_hash_or_output(self):
        module = self._module()
        self._inputs(module)
        cyclic = embedding_policy()
        cyclic["hidden"] = cyclic
        self.kw["embedding_input_policy"] = cyclic
        with (self._controls() as controls,
              mock.patch.object(module.copy, "deepcopy", side_effect=AssertionError("copy before complete bounds")),
              mock.patch.object(module, "_canonical", side_effect=AssertionError("serialization before complete bounds")),
              mock.patch.object(module, "_Directory", side_effect=AssertionError("open before complete bounds"))):
            with self.assertRaises(module.BaselineRefusal):
                self._run()
        controls[0].assert_not_called()
        controls[1].assert_not_called()

    def test_prefix_mode_refuses_foreign_embedding_model_before_any_index(self):
        module = self._module()
        self._inputs(module, mode="nomic-prefix-v1")
        self.kw["embedding"]["model"] = "ollama:other-model:v1"
        self.kw["model_expectations"]["model_name"] = "other-model:v1"
        with self._controls() as controls, self.assertRaises(module.BaselineRefusal):
            self._run()
        controls[0].assert_not_called()
        controls[1].assert_not_called()
        self.assertFalse(Path(self.kw["output_directory"]).exists())

    def test_no_v1_or_mixed_policy_producer_can_claim_v2_success(self):
        module = self._module()
        cases = [(stage, field) for stage in ("preparation", "observation", "capture", "query")
                 for field in ("version", "policy", "policy-pin")]
        for stage, field in cases:
            with self.subTest(stage=stage, field=field):
                self._inputs(module, mode="nomic-prefix-v1")
                self.kw["output_directory"] = str(self.root / (stage + "-" + field))

                def mutate(value):
                    target = (value[stage]["payload"] if stage in ("capture", "query") else value)
                    if field == "version":
                        if stage in ("capture", "query"):
                            target["v"] = 1
                        else:
                            target["schema"] = target["schema"].removesuffix("v2") + "v1"
                    elif field == "policy":
                        target["embedding_input_policy"] = embedding_policy("bare-v1")
                    elif stage in ("capture", "query"):
                        target["bindings"]["embedding_input_policy_sha256"] = sha(canonical(embedding_policy()))
                    else:
                        target["embedding_input_policy_sha256"] = sha(canonical(embedding_policy()))
                    return value

                def prepare(**kwargs):
                    return mutate(self._prepare(**kwargs)) if stage == "preparation" else self._prepare(**kwargs)

                def observe(**kwargs):
                    return mutate(self._observe(**kwargs))

                with self._controls(prepare=prepare, observe=observe), self.assertRaises(module.BaselineRefusal):
                    self._run()
                self._no_success()

    def test_document_embedding_witness_is_admitted_before_observer(self):
        module = self._module()
        for field in ("embedding_input_sha256", "embedding_input_bytes"):
            self._inputs(module, mode="nomic-prefix-v1")
            self.kw["output_directory"] = str(self.root / field)

            def prepare(**kwargs):
                value = self._prepare(**kwargs)
                row = value["preparation"]["payload"]["pages"][0]["chunks"][0]
                row[field] = row["text_sha256"] if field.endswith("sha256") else True
                return value

            with self.subTest(field=field), self._controls(prepare=prepare) as controls:
                with self.assertRaises(module.BaselineRefusal):
                    self._run()
                controls[1].assert_not_called()
            self._no_success()

    def test_query_embedding_witness_and_original_row_bytes_cannot_be_forged(self):
        module = self._module()
        for field in ("embedding_input_sha256", "embedding_input_bytes", "chunk_text", "score_f64le_base64", "origin"):
            self._inputs(module, mode="nomic-prefix-v1")
            self.kw["output_directory"] = str(self.root / field)

            def observe(**kwargs):
                value = self._observe(**kwargs)
                row = value["query"]["payload"]["results"][0]
                if field == "embedding_input_sha256":
                    row[field] = row["query_sha256"]
                elif field == "embedding_input_bytes":
                    row[field] = True
                else:
                    changed = copy.deepcopy(row["rows"])
                    if field == "chunk_text":
                        changed[0][field] = self.kw["embedding_input_policy"]["document_prefix"] + changed[0][field]
                    elif field == "score_f64le_base64":
                        replacement = raw_tests._b64(raw_tests.struct.pack("<d", 0.0))
                        self.assertNotEqual(changed[0][field], replacement)
                        changed[0][field] = replacement
                    else:
                        changed[0][field] = "evidence"
                    raw_tests._bind_rows(row, changed)
                return value

            with self.subTest(field=field), self._controls(observe=observe), self.assertRaises(module.BaselineRefusal):
                self._run()
            self._no_success()

    def test_complete_model_serving_and_wire_bindings_remain_required_in_v2(self):
        module = self._module()
        for defect in ("model", "runner", "boolean-pid", "request", "wire", "runtime"):
            self._inputs(module)
            self.kw["output_directory"] = str(self.root / defect)

            def observe(**kwargs):
                value = self._observe(**kwargs)
                observation = value["query"]
                if defect == "model":
                    del value["model_identity"]["selected_execution_paths"]
                elif defect == "runner":
                    del observation["model_serving"]["serving_generation"]["runner"]
                elif defect == "boolean-pid":
                    observation["model_serving"]["serving_generation"]["service"]["pid"] = True
                elif defect == "request":
                    observation["bound_request_sha256"] = observation["request_sha256"]
                elif defect == "wire":
                    observation["payload"]["bindings"]["request_sha256"] = observation["bound_request_sha256"]
                else:
                    observation["model_serving"]["launch_config"]["system_runtime"][0]["sha256"] = sha(b"foreign runtime")
                return value

            with self.subTest(defect=defect), self._controls(observe=observe), self.assertRaises(module.BaselineRefusal):
                self._run()
            self._no_success()

    def test_heldout_freeze_cannot_be_reused_across_input_modes(self):
        module = self._module()
        self._inputs(module, "heldout", "bare-v1")
        self._freeze()
        self.kw["embedding_input_policy"] = embedding_policy("nomic-prefix-v1")
        self.kw["expected_embedding_input_policy_sha256"] = sha(canonical(self.kw["embedding_input_policy"]))
        with self._controls() as controls, self.assertRaises(module.BaselineRefusal):
            self._run()
        controls[0].assert_not_called()
        controls[1].assert_not_called()
        self.assertFalse(Path(self.kw["output_directory"]).exists())

    def test_protocol_freezes_v2_contract_before_results_without_changing_target_definitions(self):
        module = self._module()
        self._inputs(module, mode="nomic-prefix-v1")
        source = self._source_inputs()
        measurement = importlib.import_module("siacognitivemeasure")
        legacy = copy.deepcopy(source)
        contract = legacy["baseline_contract"]
        contract["schema"] = "sia-cognitive-baseline-contract-v1"
        del contract["embedding_input_policy"]
        del contract["embedding_input_policy_sha256"]
        legacy["expected_baseline_contract_sha256"] = sha(canonical(contract))
        before = copy.deepcopy(source)
        with self._pure():
            protocol = measurement.build_protocol(**source)
            old_protocol = measurement.build_protocol(**legacy)
        self.assertEqual(source, before)
        self.assertIsNone(self.prepared_result)
        self.assertIsNone(self.observed_result)
        self.assertEqual(protocol["schema"], "sia-cognitive-retrieval-protocol-v1")
        self.assertEqual(protocol["metric_policy"], old_protocol["metric_policy"])
        for key in ("queries", "groups", "coverage", "exclusions", "non_claims", "source_non_claims"):
            self.assertEqual(protocol[key], old_protocol[key], key)
        self.assertNotEqual(protocol["baseline_contract_sha256"], old_protocol["baseline_contract_sha256"])

    def test_measurement_replays_both_v2_modes_with_unchanged_unevaluated_metrics(self):
        module = self._module()
        measurement = importlib.import_module("siacognitivemeasure")
        for mode in ("bare-v1", "nomic-prefix-v1"):
            self._inputs(module, mode=mode)
            self.kw["output_directory"] = str(self.root / mode)
            source = self._source_inputs()
            with self._pure():
                protocol = measurement.build_protocol(**source)
            with self._controls():
                observed = self._run()
            plan = self._measurement(source, protocol, observed)
            with self.subTest(mode=mode):
                self.assertEqual(plan["schema"], "sia-cognitive-measurement-plan-v1")
                self.assertEqual(plan["arithmetic_status"], "not-evaluated")
                self.assertEqual(plan["baseline"], observed)
                self.assertEqual(plan["protocol"], protocol)
                self.assertEqual(plan["non_claims"], measurement_tests.NON_CLAIMS)
                self.assertTrue(plan["jackal_requests"])

    def test_rehashed_v2_baseline_tampering_is_not_accepted_by_measurement(self):
        module = self._module()
        self._inputs(module, mode="nomic-prefix-v1")
        measurement = importlib.import_module("siacognitivemeasure")
        source = self._source_inputs()
        with self._pure():
            protocol = measurement.build_protocol(**source)
        with self._controls():
            original = self._run()
        for defect in ("policy", "policy-pin", "answer", "source", "raw", "witness", "missing-nonclaims", "v1"):
            altered = copy.deepcopy(original)
            if defect == "policy":
                altered["embedding_input_policy"] = embedding_policy()
            elif defect == "policy-pin":
                altered["embedding_input_policy_sha256"] = sha(canonical(embedding_policy()))
            elif defect == "answer":
                altered["answer_key"][0]["answer"]["sequences"] = []
            elif defect == "source":
                altered["pages"][0]["text"] += "\nsubstituted source\n"
            elif defect in ("raw", "witness"):
                row = altered["observation"]["query"]["payload"]["results"][0]
                if defect == "witness":
                    row["embedding_input_sha256"] = row["query_sha256"]
                else:
                    changed = copy.deepcopy(row["rows"])
                    changed[0]["chunk_text"] += "\nsubstituted row"
                    raw_tests._bind_rows(row, changed)
            elif defect == "missing-nonclaims":
                altered["non_claims"] = list(baseline_tests.NON_CLAIMS)
            else:
                altered["schema"] = "sia-cognitive-baseline-v1"
            altered["artifact_sha256"] = body_digest(altered, "artifact_sha256")
            with self.subTest(defect=defect), self.assertRaises(measurement.MeasurementRefusal):
                self._measurement(source, protocol, altered)

    def test_v2_heldout_measurement_requires_independent_matching_protocol_freeze(self):
        module = self._module()
        self._inputs(module, "heldout", "nomic-prefix-v1")
        measurement = importlib.import_module("siacognitivemeasure")
        source = self._source_inputs()
        with self._pure():
            protocol = measurement.build_protocol(**source)
        freeze = self._freeze()
        freeze["parameters"]["measurement_protocol_sha256"] = protocol["protocol_sha256"]
        freeze["parameters_sha256"] = sha(canonical(freeze["parameters"]))
        freeze["freeze_sha256"] = body_digest(freeze, "freeze_sha256")
        self.kw["expected_parameter_freeze_sha256"] = freeze["freeze_sha256"]
        with self._controls():
            observed = self._run()
        plan = self._measurement(source, protocol, observed)
        self.assertEqual(plan["split"], "heldout")
        self.assertEqual(plan["parameter_freeze_sha256"], freeze["freeze_sha256"])
        self.kw["expected_parameter_freeze_sha256"] = sha(b"independent different freeze")
        with self.assertRaises(measurement.MeasurementRefusal):
            self._measurement(source, protocol, observed)

    def _command_document(self, *, schema="sia-cognitive-command-request-v2", omit=None, extra=None):
        inputs = {key: copy.deepcopy(value) for key, value in self.kw.items() if key != "output_directory"}
        if omit:
            del inputs[omit]
        if extra:
            inputs.update(extra)
        raw = canonical({"schema": schema, "baseline": inputs})
        path = self.root / "prefix-command.json"
        path.write_bytes(raw)
        path.chmod(0o600)
        return path, sha(raw), raw

    def test_v2_command_dispatches_real_v2_baseline_and_emits_no_private_rows(self):
        module = self._module()
        self._inputs(module, mode="nomic-prefix-v1")
        path, digest, raw = self._command_document()
        command = importlib.import_module("siacognitivecommand")
        with (self._controls(), mock.patch.object(module, "run_baseline_v2", wraps=module.run_baseline_v2) as invoked,
              mock.patch.object(module, "run_baseline", side_effect=AssertionError("v1 dispatch forbidden"))):
            result = command.run_command(self.kw["output_directory"], request_file=str(path), request_sha256=digest)
        invoked.assert_called_once_with(**self.kw)
        observed = json.loads((Path(self.kw["output_directory"]) / "baseline.json").read_bytes())
        self.assertEqual(result, {
            "schema": "sia-cognitive-command-observation-v2", "status": "observed", "request_sha256": digest,
            "baseline_artifact_sha256": observed["artifact_sha256"], "output_directory": self.kw["output_directory"],
            "artifact": "baseline.json", "embedding_input_policy_sha256": self.kw["expected_embedding_input_policy_sha256"],
            "baseline_non_claims": NON_CLAIMS_V2, "non_claims": command_tests.COMMAND_NON_CLAIMS,
        })
        self.assertEqual(path.read_bytes(), raw)

    def test_command_version_and_closed_policy_roster_refuse_before_any_baseline(self):
        module = self._module()
        self._inputs(module)
        command = importlib.import_module("siacognitivecommand")
        cases = [dict(schema="sia-cognitive-command-request-v1"),
                 dict(schema="sia-cognitive-command-request-v3"),
                 dict(omit="embedding_input_policy"), dict(omit="expected_embedding_input_policy_sha256"),
                 dict(extra={"output_directory": self.kw["output_directory"]}),
                 dict(extra={"automatic_prefix": True})]
        for case in cases:
            path, digest, _raw = self._command_document(**case)
            with (self.subTest(case=case), mock.patch.object(module, "run_baseline_v2") as new,
                  mock.patch.object(module, "run_baseline") as old, self.assertRaises(command.CommandRefusal)):
                command.run_command(self.kw["output_directory"], request_file=str(path), request_sha256=digest)
            new.assert_not_called()
            old.assert_not_called()
        self.assertFalse(Path(self.kw["output_directory"]).exists())

    def test_command_rehashed_policy_or_legacy_result_cannot_follow_its_own_pins(self):
        module = self._module()
        self._inputs(module, mode="nomic-prefix-v1")
        with self._controls():
            original = self._run()
        self.kw["output_directory"] = str(self.root / "command-result-only")
        path, digest, _raw = self._command_document()
        command = importlib.import_module("siacognitivecommand")
        for field in ("embedding_input_policy", "embedding_input_policy_sha256", "schema", "non_claims"):
            result = copy.deepcopy(original)
            if field == "embedding_input_policy":
                result[field] = embedding_policy()
            elif field == "embedding_input_policy_sha256":
                result[field] = sha(canonical(embedding_policy()))
            elif field == "schema":
                result[field] = "sia-cognitive-baseline-v1"
            else:
                result[field] = list(baseline_tests.NON_CLAIMS)
            result["artifact_sha256"] = body_digest(result, "artifact_sha256")
            with (self.subTest(field=field), mock.patch.object(module, "run_baseline_v2", return_value=result),
                  mock.patch.object(module, "run_baseline", side_effect=AssertionError("v1 dispatch forbidden")),
                  self.assertRaises(command.CommandRefusal)):
                command.run_command(self.kw["output_directory"], request_file=str(path), request_sha256=digest)

    def test_command_request_generation_change_withdraws_v2_receipt_without_deleting_baseline(self):
        module = self._module()
        self._inputs(module, mode="nomic-prefix-v1")
        path, digest, raw = self._command_document()
        command = importlib.import_module("siacognitivecommand")
        execute = module.run_baseline_v2

        def changed(**kwargs):
            result = execute(**kwargs)
            path.write_bytes(raw + b"\n")
            return result

        with (self._controls(), mock.patch.object(module, "run_baseline_v2", side_effect=changed),
              self.assertRaises(command.CommandRefusal)):
            command.run_command(self.kw["output_directory"], request_file=str(path), request_sha256=digest)
        self.assertTrue((Path(self.kw["output_directory"]) / "baseline.json").is_file())

    def test_legacy_baseline_and_command_remain_v1_without_prefix_fields(self):
        module = self._module()
        legacy = baseline_tests.CognitiveBaseline(methodName="test_public_baseline_execution_api_exists")
        legacy.setUp()
        self.addCleanup(legacy.doCleanups)
        legacy._inputs(module)
        with legacy._controls():
            observed = legacy._run()
        self.assertEqual(observed["schema"], "sia-cognitive-baseline-v1")
        self.assertEqual(observed["contract"]["schema"], "sia-cognitive-baseline-contract-v1")
        self.assertEqual(observed["non_claims"], baseline_tests.NON_CLAIMS)
        self.assertNotIn("embedding_input_policy", observed)
        self.assertNotIn("embedding_input_policy_sha256", observed)
        command = importlib.import_module("siacognitivecommand")
        self.assertEqual(command.REQUEST_SCHEMA, "sia-cognitive-command-request-v1")
        self.assertEqual(command.RECEIPT_SCHEMA, "sia-cognitive-command-observation-v1")


if __name__ == "__main__":
    unittest.main()
