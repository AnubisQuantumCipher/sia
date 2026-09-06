"""Bound baseline orchestration, with synthetic stopped-index process doubles.

These tests never need a real model or database. Captures use existing private
signed-ledger fixtures; root alone schedules execution. No retrieval metric is
defined here. Exact event eligibility support and answer target sequences are
retained separately and never collapsed to a slug-match score.
"""

import base64
import contextlib
import copy
import importlib
import json
import os
from pathlib import Path
import stat
import struct
import tarfile
import unittest
from unittest import mock

from tests import test_cognitive_selection as selection_tests
from tests import test_raw_vector_admission as raw_tests
from tests import test_raw_vector_prepare_admission as prepare_tests


sha = selection_tests.sha
canonical = selection_tests.canonical
BIN = Path(__file__).resolve().parents[1] / "bin"
NON_CLAIMS = [
    "This is a bound raw-vector observation, not a cognitive win or a significance result.",
    "No recall, MRR, target denominator, or slug-match credit is defined by this execution artifact.",
    "Eligibility support and answer target sequences remain distinct; a separate frozen retrieval-target protocol is required before scoring.",
    "A pinned parameter freeze declares calibration-only tuning; it does not independently prove historical tuning chronology.",
    "Code-file identities do not attest loaded Python heap/interpreter behavior or the complete third-party runtime.",
    "The stopped private archive and owned model generations do not attest a resident index or complete machine history.",
    "Source origins are bound from selected pages, not inferred from raw scores or promoted by signed-row provenance.",
    "All retained capture, selection, build, preparer, model and adapter nonclaims remain controlling.",
]
FREEZE_NON_CLAIMS = [
    "This externally pinned manifest declares calibration-only tuning; it does not independently prove historical tuning chronology.",
    "Frozen parameters and identities do not establish retrieval relevance, significance, or a cognitive win.",
]


def _body_digest(value, field):
    return sha(canonical({key: item for key, item in value.items() if key != field}))


class CognitiveBaseline(unittest.TestCase):
    setUp = selection_tests.CognitiveSelection.setUp
    _capture = selection_tests.CognitiveSelection._capture

    def _module(self):
        try:
            module = importlib.import_module("siacognitivebaseline")
        except ModuleNotFoundError as exc:
            self.fail("bound cognitive baseline entrypoint must exist: " + str(exc))
        self.assertTrue(callable(getattr(module, "run_baseline", None)))
        self.assertTrue(hasattr(module, "BaselineRefusal"))
        return module

    def _build(self, name):
        executable = self.root / name
        executable.write_bytes(b"\x7fELF" + name.encode("utf-8"))
        executable.chmod(0o700)
        expected = {"executable_sha256": sha(executable.read_bytes()),
                    "builder_sha256": sha(b"builder"), "adapter_sha256": sha(name.encode()),
                    "bun_sha256": sha(b"bun"), "gbrain_commit": "7" * 40,
                    "gbrain_lock_sha256": sha(b"lock")}
        receipt = {
            "schema": "sia-raw-vector-build-v1",
            "builder": {"sha256": expected["builder_sha256"]},
            "adapter": {"sha256": expected["adapter_sha256"], "staged_path": "src/sia-raw-vector.ts"},
            "bun": {"binary_sha256": expected["bun_sha256"]},
            "gbrain": {"commit": expected["gbrain_commit"], "bun_lock_sha256": expected["gbrain_lock_sha256"]},
            "output": {"path": "sia-raw-vector", "sha256": expected["executable_sha256"]},
            "non_claims": ["Fixture build observation is not package authentication."],
        }
        path = self.root / (name + ".json")
        path.write_bytes(canonical(receipt))
        path.chmod(0o600)
        return {"executable": str(executable), "expected": expected,
                "build_receipt": str(path), "build_receipt_sha256": sha(path.read_bytes())}

    def _inputs(self, module, split="calibration"):
        capture = self._capture()
        policy = selection_tests.policy_fixture()
        # Previously JACKAL status=exact modulo fixtures: wireplumber and
        # bluetooth residue=3, pipewire residue=4. This fixture chooses residue
        # 3 for calibration so both partitions have queries; no outcome tuning.
        policy["split"]["calibration_residue"] = 3
        selector = importlib.import_module("siacognitiveselect")
        selection = selector.select_history(
            capture, expected_capture_sha256=capture["capture_sha256"], policy=policy,
            expected_policy_sha256=sha(canonical(policy)))
        runtime_file = self.root / "fixture-python"
        runtime_file.write_bytes(b"fixture system runtime")
        runtime_file.chmod(0o700)
        model = {"package_root": str(self.root / "package"), "package_sha256": sha(b"package"),
                 "model_root": str(self.root / "model"), "model_name": "nomic-embed-text:v1.5",
                 "manifest_sha256": sha(b"model manifest"), "release_version": "0.33.2",
                 "release_archive_sha256": sha(b"release")}
        self.kw = {
            "capture": capture, "expected_capture_sha256": capture["capture_sha256"],
            "selection_policy": policy, "expected_policy_sha256": sha(canonical(policy)),
            "selection": selection, "expected_selection_sha256": selection["selection_sha256"],
            "split": split, "preparer": self._build("fixture-preparer"),
            "adapter": self._build("fixture-adapter"),
            "embedding": {"model": "ollama:" + model["model_name"], "dimensions": 3,
                          "endpoint": "http://127.0.0.1:11434/v1"},
            "model_expectations": model,
            "shared_runtime": [{"source": str(runtime_file), "destination": "/usr/bin/python3",
                                "sha256": sha(runtime_file.read_bytes())}],
            "code_expectations": {"schema": "sia-bin-source-inventory-v1", "files": {
                path.name: sha(path.read_bytes()) for path in sorted(BIN.iterdir())
                if not path.name.startswith(".") and path.is_file()}},
            "limit": 5, "timeout": 30, "scratch_parent": str(self.root),
            "output_directory": str(self.root / "baseline-output"),
            "parameter_freeze": None, "expected_parameter_freeze_sha256": None,
        }
        self.module = module
        self.calls = []
        self.prepared_result = self.observed_result = None

    def _contract(self):
        kw = self.kw
        return {
            "schema": "sia-cognitive-baseline-contract-v1",
            "capture_sha256": kw["expected_capture_sha256"],
            "policy_sha256": kw["expected_policy_sha256"],
            "selection_sha256": kw["expected_selection_sha256"],
            "pages_sha256": kw["selection"]["pages_sha256"],
            **{role: {"expected": copy.deepcopy(kw[role]["expected"]),
                      "build_receipt_sha256": kw[role]["build_receipt_sha256"]}
               for role in ("preparer", "adapter")},
            "embedding": copy.deepcopy(kw["embedding"]),
            "model": {key: value for key, value in kw["model_expectations"].items()
                      if key not in ("package_root", "model_root")},
            "runtime": sorted(({"destination": row["destination"], "sha256": row["sha256"]}
                               for row in kw["shared_runtime"]), key=lambda row: row["destination"]),
            "code_expectations": copy.deepcopy(kw["code_expectations"]),
            "limit": kw["limit"], "timeout": kw["timeout"],
        }

    def _freeze(self):
        parameters = {"policy": "fixture-frozen-before-heldout", "usage_decay": "0.5"}
        value = {"schema": "sia-cognitive-parameter-freeze-v1",
                 "capture_sha256": self.kw["expected_capture_sha256"],
                 "policy_sha256": self.kw["expected_policy_sha256"],
                 "selection_sha256": self.kw["expected_selection_sha256"],
                 "baseline_contract_sha256": sha(canonical(self._contract())),
                 "calibration_run_sha256": sha(b"caller-pinned calibration observation"),
                 "tuning_split": "calibration", "parameters": parameters,
                 "parameters_sha256": sha(canonical(parameters)),
                 "non_claims": list(FREEZE_NON_CLAIMS)}
        value["freeze_sha256"] = sha(canonical(value))
        self.kw["parameter_freeze"] = value
        self.kw["expected_parameter_freeze_sha256"] = value["freeze_sha256"]
        return value

    def _queries(self):
        return [{"id": row["id"], "text": row["text"]}
                for row in self.kw["selection"]["queries"] if row["split"] == self.kw["split"]]

    def _model_identity(self):
        expected = self.kw["model_expectations"]
        return {key: expected[key] for key in ("model_name", "manifest_sha256", "package_sha256")}

    def _serving(self, operation, executable_sha256, request_sha256):
        model_module = importlib.import_module("siavectormodel")
        config = {"schema": "sia-raw-vector-model-launch-v1", "operation": operation,
                  "model_identity": self._model_identity(), "embedding": copy.deepcopy(self.kw["embedding"]),
                  "adapter_sha256": executable_sha256, "request_sha256": request_sha256,
                  "system_runtime": [{"destination": row["destination"], "sha256": row["sha256"],
                                      "bytes": Path(row["source"]).stat().st_size}
                                     for row in self.kw["shared_runtime"]]}
        return {"schema": "sia-raw-vector-served-observation-v1", "status": "observed",
                "model_identity": self._model_identity(), "launch_config": config,
                "launch_config_sha256": sha(canonical(config)),
                "serving_generation": {"model_manifest_sha256": self.kw["model_expectations"]["manifest_sha256"],
                                       "execution_policy": "ollama-cpu-only-v1"},
                "non_claims": list(model_module.NON_CLAIMS)}

    def _prepare(self, **kwargs):
        self.calls.append("prepare")
        self.assertEqual({key: kwargs[key] for key in self.kw["preparer"]}, self.kw["preparer"])
        self.assertEqual(kwargs["model_expectations"], self.kw["model_expectations"])
        self.assertEqual(kwargs["shared_runtime"], self.kw["shared_runtime"])
        request = kwargs["request"]
        self.assertEqual(request, {"v": 1, "operation": "prepare_index", "source": "sia",
                         "dataset_sha256": self.kw["expected_selection_sha256"],
                         "pages_sha256": self.kw["selection"]["pages_sha256"],
                         "embedding": self.kw["embedding"], "output": {"parent_fd": None},
                         "pages": self.kw["selection"]["pages"]})
        parent = Path(kwargs["output_directory"])
        self.assertEqual(parent, Path(self.kw["output_directory"]) / "prepared")
        self.assertEqual(list(parent.iterdir()), [])
        self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0o700)
        index = parent / "index"
        index.mkdir(mode=0o700)
        (index / "fixture.data").write_bytes(b"stopped private fixture index")
        (index / "fixture.data").chmod(0o600)
        bound = copy.deepcopy(request)
        bound["output"]["parent_fd"] = 9
        request_sha = sha(canonical(bound))
        payload = {"v": 1, "status": "ok", "operation": "prepare_index", "index_leaf": "index",
                   "bindings": {"dataset_sha256": request["dataset_sha256"],
                                "pages_sha256": request["pages_sha256"], "request_sha256": request_sha,
                                "policy_sha256": sha(canonical(prepare_tests.POLICY)),
                                "embedding_sha256": sha(canonical(request["embedding"]))},
                   "policy": copy.deepcopy(prepare_tests.POLICY), "embedding": copy.deepcopy(request["embedding"]),
                   "pages": [], "setup_diagnostics": prepare_tests._diagnostics(),
                   "non_claims": list(prepare_tests.NON_CLAIMS)}
        for page in request["pages"]:
            payload["pages"].append({"slug": page["slug"], "origin": page["origin"],
                "text_sha256": page["text_sha256"], "chunks": [
                    {"chunk_index": index, "text_sha256": sha(chunk.encode()),
                     "vector_sha256": sha(struct.pack("<fff", 1.0, 0.0, 0.0)), "bytes": len(chunk.encode())}
                    for index, chunk in enumerate(prepare_tests._chunks(page["text"]))]})
        observation = {"payload": payload, "request_sha256": request_sha,
                       "bound_request_sha256": sha(canonical(request)),
                       "executable_sha256": kwargs["expected"]["executable_sha256"],
                       "returncode": 0, "stdout_sha256": sha(canonical(payload)),
                       "model_serving": self._serving("prepare_index", kwargs["expected"]["executable_sha256"],
                                                     sha(canonical(request)))}
        self.prepared_result = {
            "schema": "sia-raw-vector-bound-preparation-v1", "status": "observed",
            "dataset_sha256": request["dataset_sha256"], "pages_sha256": request["pages_sha256"],
            "build_receipt_sha256": kwargs["build_receipt_sha256"], "expected": copy.deepcopy(kwargs["expected"]),
            "model_identity": self._model_identity(), "preparation": observation,
            "build_non_claims": ["fixture preparation build boundary"],
            "non_claims": ["fixture admitted preparation boundary"],
        }
        return copy.deepcopy(self.prepared_result)

    def _observe(self, **kwargs):
        self.calls.append("observe")
        self.assertEqual(self.calls, ["prepare", "observe"])
        self.assertEqual({key: kwargs[key] for key in self.kw["adapter"]}, self.kw["adapter"])
        self.assertEqual(kwargs["queries"], self._queries())
        self.assertTrue(kwargs["queries"])
        for query in kwargs["queries"]:
            self.assertEqual(set(query), {"id", "text"})
        self.assertEqual(kwargs["embedding"], self.kw["embedding"])
        self.assertEqual(kwargs["model_expectations"], self.kw["model_expectations"])
        self.assertEqual(kwargs["shared_runtime"], self.kw["shared_runtime"])
        archive = Path(kwargs["index_archive"])
        self.assertEqual(archive, Path(self.kw["output_directory"]) / "index.tar")
        self.assertEqual(kwargs["index_sha256"], sha(archive.read_bytes()))
        self.assertFalse((archive.parent / "baseline.json").exists())
        transport = importlib.import_module("siavector")
        with transport.private_index_snapshot(str(archive), kwargs["index_sha256"],
                                              scratch_parent=self.kw["scratch_parent"]) as snapshot:
            self.assertEqual((Path(snapshot["directory"]) / "fixture.data").read_bytes(),
                             b"stopped private fixture index")
            manifest_sha = snapshot["manifest_sha256"]
        runner = importlib.import_module("siavectorrun")
        config_sha = runner.configuration_sha256(kwargs["embedding"], kwargs["limit"])
        identity = {"logical_sha256": sha(b"fixture logical identity"),
                    "catalog_sha256": sha(b"fixture catalog identity")}
        observations = {}
        for operation in ("capture", "query"):
            request = {"v": 1, "lane": "raw_vector", "operation": operation,
                       "queries": [] if operation == "capture" else copy.deepcopy(kwargs["queries"]),
                       "limit": kwargs["limit"], "embedding": copy.deepcopy(kwargs["embedding"]),
                       "snapshot": {"fd": None, **(identity if operation == "query" else {
                           "logical_sha256": None, "catalog_sha256": None})},
                       "binding": {"executable_sha256": kwargs["expected"]["executable_sha256"],
                                   "build_receipt_sha256": kwargs["build_receipt_sha256"]}}
            original_request_sha = sha(canonical(request))
            wire_request = copy.deepcopy(request)
            wire_request["snapshot"]["fd"] = 9
            request_sha = sha(canonical(wire_request))
            payload = {"v": 1, "status": "ok", "lane": "raw_vector", "operation": operation,
                       "bindings": {**identity, **request["binding"], "request_sha256": request_sha,
                                    "config_sha256": config_sha}, "results": [],
                       "latency_ms": {"total": 0}, "non_claims": list(raw_tests.NON_CLAIMS)}
            page = self.kw["selection"]["pages"][0]
            for query in request["queries"]:
                vector = struct.pack("<fff", 1.0, 0.0, 0.0)
                result = {"id": query["id"], "query_sha256": sha(query["text"].encode()),
                          "vector_f32le_base64": base64.b64encode(vector).decode(),
                          "vector_sha256": sha(vector), "latency_ms": {"embedding": 0, "search": 0}}
                raw_tests._bind_rows(result, [raw_tests._row(
                    slug=page["slug"], title=page["title"], type=page["type"],
                    chunk_text=prepare_tests._chunks(page["text"])[0])])
                payload["results"].append(result)
            observations[operation] = {
                "payload": payload, "request_sha256": request_sha,
                "bound_request_sha256": original_request_sha,
                "executable_sha256": kwargs["expected"]["executable_sha256"],
                "returncode": 0, "stdout_sha256": sha(canonical(payload)),
                "physical_manifest_sha256": manifest_sha,
                "model_serving": self._serving(operation, kwargs["expected"]["executable_sha256"], original_request_sha),
            }
        self.observed_result = {
            "schema": "sia-raw-vector-bound-observation-v1", "status": "observed", "lane": "raw_vector",
            "build_receipt_sha256": kwargs["build_receipt_sha256"], "index_archive_sha256": kwargs["index_sha256"],
            "expected": copy.deepcopy(kwargs["expected"]), "embedding": copy.deepcopy(kwargs["embedding"]),
            "config_sha256": config_sha, **observations, "model_identity": self._model_identity(),
            "build_non_claims": ["fixture query build boundary"], "non_claims": ["fixture observed boundary"],
        }
        return copy.deepcopy(self.observed_result)

    @contextlib.contextmanager
    def _controls(self, prepare=None, observe=None):
        runner = importlib.import_module("siavectorrun")
        with mock.patch.object(runner, "prepare_bound", side_effect=prepare or self._prepare) as preparing, \
                mock.patch.object(runner, "observe_bound", side_effect=observe or self._observe) as observing, \
                mock.patch.object(runner, "observe", side_effect=AssertionError("ambient observer forbidden")) as ambient, \
                mock.patch.object(runner.siavector, "invoke_adapter", side_effect=AssertionError("ambient adapter forbidden")), \
                mock.patch.object(self.bench, "run", side_effect=AssertionError("legacy hybrid bench forbidden")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("integration double launched a child")):
            yield preparing, observing, ambient

    def _run(self):
        return self.module.run_baseline(**self.kw)

    def _no_success(self):
        self.assertFalse((Path(self.kw["output_directory"]) / "baseline.json").exists())

    def test_public_baseline_execution_api_exists(self):
        self._module()

    def test_calibration_uses_only_selected_public_queries_and_retains_admitted_evidence(self):
        module = self._module()
        self._inputs(module)
        before = copy.deepcopy(self.kw)
        with self._controls() as controls:
            result = self._run()
        controls[0].assert_called_once()
        controls[1].assert_called_once()
        controls[2].assert_not_called()
        self.assertEqual(self.kw, before)
        self.assertEqual(result["schema"], "sia-cognitive-baseline-v1")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["lane"], "raw_vector")
        self.assertEqual(result["split"], "calibration")
        for field, expected in (("capture_sha256", self.kw["expected_capture_sha256"]),
                                ("policy_sha256", self.kw["expected_policy_sha256"]),
                                ("selection_sha256", self.kw["expected_selection_sha256"]),
                                ("pages_sha256", self.kw["selection"]["pages_sha256"])):
            self.assertEqual(result[field], expected)
        self.assertEqual(result["queries"], self._queries())
        ids = {row["id"] for row in self._queries()}
        self.assertEqual(result["answer_key"], [row for row in self.kw["selection"]["answer_key"] if row["id"] in ids])
        self.assertEqual(result["pages"], self.kw["selection"]["pages"])
        self.assertEqual(result["preparation"], self.prepared_result)
        self.assertEqual(result["observation"], self.observed_result)
        self.assertEqual(result["contract"], self._contract())
        self.assertEqual(result["baseline_contract_sha256"], sha(canonical(self._contract())))
        self.assertEqual(result["query_roster_sha256"], sha(canonical(self._queries())))
        self.assertIsNone(result["parameter_freeze_sha256"])
        self.assertEqual(result["artifact_sha256"], _body_digest(result, "artifact_sha256"))
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertTrue(result["source_non_claims"])
        for name in ("metrics", "recall", "mrr", "win", "significance", "target_denominator"):
            self.assertNotIn(name, result)

    def test_output_is_private_exact_and_archive_is_actual_stopped_generation(self):
        module = self._module()
        self._inputs(module)
        with self._controls():
            result = self._run()
        output = Path(self.kw["output_directory"])
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
        for name in ("baseline.json", "index.tar"):
            info = (output / name).lstat()
            self.assertTrue(stat.S_ISREG(info.st_mode))
            self.assertEqual(info.st_nlink, 1)
            self.assertEqual(info.st_uid, os.geteuid())
            self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
        self.assertEqual(json.loads((output / "baseline.json").read_bytes()), result)
        self.assertEqual(result["archive"]["path"], "index.tar")
        self.assertEqual(result["archive"]["sha256"], sha((output / "index.tar").read_bytes()))
        self.assertEqual(result["archive"]["manifest_sha256"],
                         result["observation"]["query"]["physical_manifest_sha256"])

    def test_heldout_requires_external_freeze_before_output_or_any_execution(self):
        module = self._module()
        self._inputs(module, "heldout")
        with self._controls() as controls, self.assertRaises(module.BaselineRefusal):
            self._run()
        controls[0].assert_not_called()
        controls[1].assert_not_called()
        self.assertFalse(Path(self.kw["output_directory"]).exists())

    def test_valid_external_freeze_permits_only_heldout_query_roster(self):
        module = self._module()
        self._inputs(module, "heldout")
        freeze = self._freeze()
        with self._controls():
            result = self._run()
        self.assertEqual(result["split"], "heldout")
        self.assertEqual(result["parameter_freeze_sha256"], freeze["freeze_sha256"])
        self.assertEqual(result["parameter_freeze"], freeze)
        self.assertEqual(result["queries"], self._queries())
        calibration = {row["id"] for row in self.kw["selection"]["queries"] if row["split"] == "calibration"}
        self.assertTrue(calibration)
        self.assertTrue(calibration.isdisjoint({row["id"] for row in result["queries"]}))

    def test_freeze_self_hash_is_not_authority_and_contract_substitution_refuses(self):
        module = self._module()
        self._inputs(module, "heldout")
        original = copy.deepcopy(self._freeze())
        for field in ("capture_sha256", "policy_sha256", "selection_sha256", "baseline_contract_sha256",
                      "parameters_sha256", "calibration_run_sha256", "tuning_split", "non_claims"):
            changed = copy.deepcopy(original)
            if field == "tuning_split":
                changed[field] = "heldout"
            elif field == "non_claims":
                changed[field] = []
            elif field == "calibration_run_sha256":
                changed[field] = None
            else:
                changed[field] = sha(b"foreign")
            changed["freeze_sha256"] = _body_digest(changed, "freeze_sha256")
            self.kw["parameter_freeze"] = changed
            self.kw["expected_parameter_freeze_sha256"] = changed["freeze_sha256"]
            with self.subTest(field=field), self._controls() as controls, self.assertRaises(module.BaselineRefusal):
                self._run()
            controls[0].assert_not_called()
            controls[1].assert_not_called()
        self.kw["parameter_freeze"] = original
        self.kw["expected_parameter_freeze_sha256"] = sha(b"foreign external freeze pin")
        with self._controls() as controls, self.assertRaises(module.BaselineRefusal):
            self._run()
        controls[0].assert_not_called()

    def test_capture_policy_selection_and_code_pins_refuse_before_launch(self):
        module = self._module()
        self._inputs(module)
        original = copy.deepcopy(self.kw)
        for field in ("expected_capture_sha256", "expected_policy_sha256", "expected_selection_sha256"):
            self.kw = copy.deepcopy(original)
            self.kw[field] = sha(b"foreign pin")
            with self.subTest(field=field), self._controls() as controls, self.assertRaises(module.BaselineRefusal):
                self._run()
            controls[0].assert_not_called()
            self.assertFalse(Path(self.kw["output_directory"]).exists())
        for change in ("missing-origin-code", "wrong-code-bytes"):
            self.kw = copy.deepcopy(original)
            if change == "missing-origin-code":
                del self.kw["code_expectations"]["files"]["siamind.py"]
            else:
                self.kw["code_expectations"]["files"]["siamind.py"] = sha(b"different origin policy")
            with self.subTest(change=change), self._controls() as controls, self.assertRaises(module.BaselineRefusal):
                self._run()
            controls[0].assert_not_called()

    def test_rehashed_private_answer_edit_still_requires_selection_replay(self):
        module = self._module()
        self._inputs(module)
        changed = self.kw["selection"]
        changed["answer_key"][0]["answer"]["value"] = "invented answer"
        changed["selection_sha256"] = _body_digest(changed, "selection_sha256")
        self.kw["expected_selection_sha256"] = changed["selection_sha256"]
        with self._controls() as controls, self.assertRaises(module.BaselineRefusal):
            self._run()
        controls[0].assert_not_called()

    def test_empty_requested_split_refuses_without_rebalancing_or_execution(self):
        module = self._module()
        self._inputs(module)
        self.kw["selection_policy"]["split"]["calibration_residue"] = 0
        self.kw["expected_policy_sha256"] = sha(canonical(self.kw["selection_policy"]))
        selector = importlib.import_module("siacognitiveselect")
        self.kw["selection"] = selector.select_history(
            self.kw["capture"], expected_capture_sha256=self.kw["expected_capture_sha256"],
            policy=self.kw["selection_policy"], expected_policy_sha256=self.kw["expected_policy_sha256"])
        self.kw["expected_selection_sha256"] = self.kw["selection"]["selection_sha256"]
        self.assertFalse(self._queries())
        with self._controls() as controls, self.assertRaises(module.BaselineRefusal):
            self._run()
        controls[0].assert_not_called()
        self.assertFalse(Path(self.kw["output_directory"]).exists())

    def test_malformed_inputs_and_calibration_freeze_never_create_output(self):
        module = self._module()
        self._inputs(module)
        original = copy.deepcopy(self.kw)
        for field, value in (("split", "all"), ("split", True), ("limit", True),
                             ("timeout", float("inf")), ("timeout", float("nan")),
                             ("model_expectations", None), ("shared_runtime", []),
                             ("scratch_parent", "."), ("output_directory", ".")):
            self.kw = copy.deepcopy(original)
            self.kw[field] = value
            with self.subTest(field=field), self._controls() as controls, self.assertRaises(module.BaselineRefusal):
                self._run()
            controls[0].assert_not_called()
        self.kw = copy.deepcopy(original)
        self._freeze()
        with self._controls() as controls, self.assertRaises(module.BaselineRefusal):
            self._run()
        controls[0].assert_not_called()
        self.assertFalse(Path(original["output_directory"]).exists())

    def test_preparation_identities_and_complete_readback_are_not_trusted_by_status(self):
        module = self._module()
        self._inputs(module)
        original = self.kw["output_directory"]
        for field in ("dataset_sha256", "pages_sha256", "build_receipt_sha256", "model_identity",
                      "expected", "receipt-origin", "receipt-embedding", "status"):
            self.calls = []
            self.kw["output_directory"] = original + "-" + field
            def altered(**kwargs):
                result = self._prepare(**kwargs)
                if field == "model_identity":
                    result[field]["manifest_sha256"] = sha(b"foreign model")
                elif field == "expected":
                    result[field]["executable_sha256"] = sha(b"foreign executable")
                elif field == "receipt-origin":
                    page = result["preparation"]["payload"]["pages"][0]
                    page["origin"] = "model" if page["origin"] != "model" else "evidence"
                elif field == "receipt-embedding":
                    result["preparation"]["payload"]["embedding"]["model"] = "ollama:foreign"
                elif field == "status":
                    result[field] = "partial"
                else:
                    result[field] = sha(b"foreign identity")
                return result
            with self.subTest(field=field), self._controls(prepare=altered) as controls, \
                    self.assertRaises(module.BaselineRefusal):
                self._run()
            controls[1].assert_not_called()
            self._no_success()

    def test_query_roster_loss_duplication_or_reordering_never_publishes_success(self):
        module = self._module()
        self._inputs(module)
        original = self.kw["output_directory"]
        for change in ("missing", "duplicate", "reversed", "foreign-id"):
            self.calls = []
            self.kw["output_directory"] = original + "-" + change
            def altered(**kwargs):
                result = self._observe(**kwargs)
                rows = result["query"]["payload"]["results"]
                self.assertGreater(len(rows), 1)
                if change == "missing":
                    rows.pop()
                elif change == "duplicate":
                    rows.append(copy.deepcopy(rows[0]))
                elif change == "reversed":
                    rows.reverse()
                else:
                    rows[0]["id"] = "unrequested-query"
                return result
            with self.subTest(change=change), self._controls(observe=altered), \
                    self.assertRaises(module.BaselineRefusal):
                self._run()
            self._no_success()

    def test_raw_rows_require_exact_selected_slug_type_title_chunk_and_source(self):
        module = self._module()
        self._inputs(module)
        original = self.kw["output_directory"]
        for field, value in (("slug", "events/foreign/source"), ("title", "foreign title"),
                             ("type", "thought"), ("chunk_text", "invented answer text"),
                             ("chunk_index", 4096), ("source_id", "foreign"),
                             ("chunk_source", "raw_source")):
            self.calls = []
            self.kw["output_directory"] = original + "-" + field
            def altered(**kwargs):
                result = self._observe(**kwargs)
                query = result["query"]["payload"]["results"][0]
                rows = copy.deepcopy(query["rows"])
                self.assertNotEqual(rows[0][field], value)
                rows[0][field] = value
                raw_tests._bind_rows(query, rows)
                return result
            with self.subTest(field=field), self._controls(observe=altered), \
                    self.assertRaises(module.BaselineRefusal):
                self._run()
            self._no_success()

    def test_source_origins_are_joined_separately_without_rewriting_raw_score_bytes(self):
        module = self._module()
        self._inputs(module)
        with self._controls():
            result = self._run()
        pages = {page["slug"]: page for page in self.kw["selection"]["pages"]}
        raw_results = result["observation"]["query"]["payload"]["results"]
        self.assertEqual([row["id"] for row in result["retrieval_rows"]], [row["id"] for row in raw_results])
        for joined, raw in zip(result["retrieval_rows"], raw_results):
            self.assertEqual(len(joined["rows"]), len(raw["rows"]))
            for label, row in zip(joined["rows"], raw["rows"]):
                self.assertNotIn("origin", row)
                page = pages[row["slug"]]
                self.assertEqual(label, {"slug": row["slug"], "chunk_index": row["chunk_index"],
                    "origin": page["origin"], "page_text_sha256": page["text_sha256"],
                    "chunk_text_sha256": sha(row["chunk_text"].encode())})
            self.assertEqual(raw, next(row for row in self.observed_result["query"]["payload"]["results"]
                                       if row["id"] == raw["id"]))

    def test_query_model_build_and_physical_generation_must_match_preparation_contract(self):
        module = self._module()
        self._inputs(module)
        original = self.kw["output_directory"]
        for field in ("model_identity", "expected", "embedding", "build_receipt_sha256",
                      "index_archive_sha256", "physical_manifest_sha256", "config_sha256"):
            self.calls = []
            self.kw["output_directory"] = original + "-" + field
            def altered(**kwargs):
                result = self._observe(**kwargs)
                if field == "model_identity":
                    result[field]["manifest_sha256"] = sha(b"different model")
                elif field == "expected":
                    result[field]["adapter_sha256"] = sha(b"different query code")
                elif field == "embedding":
                    result[field]["model"] = "ollama:different"
                elif field == "physical_manifest_sha256":
                    result["query"][field] = sha(b"different physical tree")
                else:
                    result[field] = sha(b"different binding")
                return result
            with self.subTest(field=field), self._controls(observe=altered), \
                    self.assertRaises(module.BaselineRefusal):
                self._run()
            self._no_success()

    def test_preparation_refusal_preserves_partial_private_tree_without_query_or_archive(self):
        module = self._module()
        self._inputs(module)
        def refused(**kwargs):
            self._prepare(**kwargs)
            raise importlib.import_module("siavector").VectorRefusal("named preparation refusal")
        with self._controls(prepare=refused) as controls, \
                self.assertRaisesRegex(module.BaselineRefusal, "named preparation refusal"):
            self._run()
        controls[1].assert_not_called()
        self._no_success()
        output = Path(self.kw["output_directory"])
        self.assertTrue((output / "prepared" / "index" / "fixture.data").is_file())
        self.assertFalse((output / "index.tar").exists())

    def test_query_refusal_retains_archive_but_never_success_or_fallback(self):
        module = self._module()
        self._inputs(module)
        def refused(**kwargs):
            self._observe(**kwargs)
            raise importlib.import_module("siavector").VectorRefusal("named query refusal")
        with self._controls(observe=refused) as controls, \
                self.assertRaisesRegex(module.BaselineRefusal, "named query refusal"):
            self._run()
        controls[2].assert_not_called()
        self._no_success()
        self.assertTrue((Path(self.kw["output_directory"]) / "index.tar").is_file())

    def test_existing_or_symlink_output_is_never_reused_or_overwritten(self):
        module = self._module()
        self._inputs(module)
        output = Path(self.kw["output_directory"])
        output.mkdir(mode=0o700)
        marker = output / "operator.data"
        marker.write_bytes(b"preserve operator data")
        with self._controls() as controls, self.assertRaises(module.BaselineRefusal):
            self._run()
        controls[0].assert_not_called()
        self.assertEqual(marker.read_bytes(), b"preserve operator data")
        alias = self.root / "output-alias"
        alias.symlink_to(output, target_is_directory=True)
        self.kw["output_directory"] = str(alias)
        with self._controls() as controls, self.assertRaises(module.BaselineRefusal):
            self._run()
        controls[0].assert_not_called()
        self.assertEqual(marker.read_bytes(), b"preserve operator data")

    def test_archive_refuses_symlinks_hardlinks_and_special_files_without_query(self):
        module = self._module()
        self._inputs(module)
        original = self.kw["output_directory"]
        outside = self.root / "outside-source"
        outside.write_bytes(b"outside data stays outside")
        for kind in ("symlink", "hardlink", "fifo"):
            self.calls = []
            self.kw["output_directory"] = original + "-" + kind
            def linked(**kwargs):
                result = self._prepare(**kwargs)
                leaf = Path(kwargs["output_directory"]) / "index" / "not-ordinary"
                if kind == "symlink":
                    leaf.symlink_to(outside)
                elif kind == "hardlink":
                    os.link(outside, leaf)
                else:
                    os.mkfifo(leaf, 0o600)
                return result
            with self.subTest(kind=kind), self._controls(prepare=linked) as controls, \
                    self.assertRaises(module.BaselineRefusal):
                self._run()
            controls[1].assert_not_called()
            self._no_success()
        self.assertEqual(outside.read_bytes(), b"outside data stays outside")

    def test_archive_ceiling_refuses_instead_of_truncating_private_index(self):
        module = self._module()
        self._inputs(module)
        self.assertTrue(hasattr(module, "MAX_ARCHIVE_BYTES"))
        with mock.patch.object(module, "MAX_ARCHIVE_BYTES", 1), self._controls() as controls, \
                self.assertRaises(module.BaselineRefusal):
            self._run()
        controls[1].assert_not_called()
        self._no_success()
        self.assertEqual((Path(self.kw["output_directory"]) / "prepared" / "index" / "fixture.data").read_bytes(),
                         b"stopped private fixture index")

    def test_archive_source_change_during_copy_refuses_before_query(self):
        module = self._module()
        self._inputs(module)
        original_addfile = tarfile.TarFile.addfile
        changed = []
        def mutate_after_copy(archive, tarinfo, fileobj=None):
            result = original_addfile(archive, tarinfo, fileobj)
            if tarinfo.name == "fixture.data" and not changed:
                source = Path(self.kw["output_directory"]) / "prepared" / "index" / "fixture.data"
                source.write_bytes(b"changed while archive was copied")
                changed.append(True)
            return result
        with mock.patch.object(tarfile.TarFile, "addfile", mutate_after_copy), \
                self._controls() as controls, self.assertRaises(module.BaselineRefusal):
            self._run()
        self.assertTrue(changed, "fixture must change the ordinary source during archive construction")
        controls[1].assert_not_called()
        self._no_success()

    def test_output_generation_replacement_cannot_receive_success_publication(self):
        module = self._module()
        self._inputs(module)
        output = Path(self.kw["output_directory"])
        displaced = self.root / "displaced-private-output"
        def replace_output(**kwargs):
            result = self._observe(**kwargs)
            output.rename(displaced)
            output.mkdir(mode=0o700)
            (output / "operator.data").write_bytes(b"replacement generation")
            return result
        with self._controls(observe=replace_output), self.assertRaises(module.BaselineRefusal):
            self._run()
        self._no_success()
        self.assertFalse((displaced / "baseline.json").exists())
        self.assertEqual({path.name for path in output.iterdir()}, {"operator.data"})
        self.assertEqual((output / "operator.data").read_bytes(), b"replacement generation")


if __name__ == "__main__":
    unittest.main()
