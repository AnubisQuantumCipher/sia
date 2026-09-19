"""Bound raw-vector observations, separate from the cognitive claim gate.

This controller admits caller-pinned build provenance, restores a physical
index generation for each invocation, and validates complete adapter output.
Model-service admission and held-out comparisons are further obligations.
"""

import contextlib
import copy
import hashlib
import math
import os
import re

import siaqueue
import siavector
import siavectoradmit
import siavectormodel
import siavectorprepare


_EXPECTED = {
    "executable_sha256": ("output", "sha256"),
    "builder_sha256": ("builder", "sha256"),
    "adapter_sha256": ("adapter", "sha256"),
    "bun_sha256": ("bun", "binary_sha256"),
    "gbrain_commit": ("gbrain", "commit"),
    "gbrain_lock_sha256": ("gbrain", "bun_lock_sha256"),
}


def _configuration(embedding, limit):
    """The unchanged original raw-search configuration body."""
    config = {
        "engine": "pglite", "embedding": embedding,
        "search": {
            "limit": limit, "offset": 0, "sourceId": "sia", "detail": "high",
            "exclude_slug_prefixes": ["test/", "attachments/", ".raw/"],
            "include_slug_prefixes": [], "excludePrivate": False,
            "embeddingColumn": {"name": "embedding", "type": "vector",
                                "dimensions": embedding["dimensions"],
                                "embeddingModel": embedding["model"]},
        },
        "env": {"GBRAIN_SEARCH_EXCLUDE": "", "GBRAIN_SOURCE_BOOST": "",
                "GBRAIN_PGLITE_WAL_REPAIR": "off", "TZ": "UTC"},
    }
    return config


def configuration_sha256(embedding, limit):
    """Independently construct the adapter's effective, non-hybrid v1 policy."""
    return hashlib.sha256(siavector._canonical_bytes(_configuration(embedding, limit))).hexdigest()


def configuration_sha256_v2(embedding, limit, *, embedding_input_policy,
                            expected_embedding_input_policy_sha256):
    """Bind the full declared transform without changing the v1 identity."""
    policy = siavectoradmit.admit_embedding_input_policy(
        embedding_input_policy, expected_sha256=expected_embedding_input_policy_sha256, embedding=embedding)
    if type(limit) is not int or not 1 <= limit <= siavectoradmit.MAX_RESULTS:
        raise siavector.VectorRefusal("vector result limit is invalid")
    config = _configuration(embedding, limit)
    config.update(embedding_input_policy=policy,
                  embedding_input_policy_sha256=expected_embedding_input_policy_sha256)
    return hashlib.sha256(siavector._canonical_bytes(config)).hexdigest()


def _expectation_values(expected):
    if type(expected) is not dict or set(expected) != set(_EXPECTED):
        raise siavector.VectorRefusal("vector build expectations are invalid")
    for name in _EXPECTED:
        pattern = r"[0-9a-f]{40}" if name == "gbrain_commit" else r"[0-9a-f]{64}"
        if type(expected[name]) is not str \
                or re.fullmatch(pattern, expected[name]) is None:
            raise siavector.VectorRefusal("vector build expectation is invalid: " + name)
    return dict(expected)


def _admit_build(receipt, expected):
    _expectation_values(expected)
    if type(receipt) is not dict \
            or receipt.get("schema") != "sia-raw-vector-build-v1":
        raise siavector.VectorRefusal("vector build admission shape is invalid")
    for name, (section, field) in _EXPECTED.items():
        if type(receipt.get(section)) is not dict \
                or receipt[section].get(field) != expected[name]:
            raise siavector.VectorRefusal("vector build expectation mismatch: " + name)
    if receipt["output"].get("path") != "sia-raw-vector" \
            or receipt["adapter"].get("staged_path") != "src/sia-raw-vector.ts" \
            or type(receipt.get("non_claims")) is not list \
            or not receipt["non_claims"] \
            or any(type(item) is not str or not item for item in receipt["non_claims"]):
        raise siavector.VectorRefusal("vector build receipt contract is invalid")


def _served_observation(served, model):
    """Admit the common owned-service envelope before operation-specific data."""
    if type(served) is not dict or set(served) != {
            "schema", "status", "observation", "serving_generation",
            "launch_config_sha256", "launch_config", "model_identity", "non_claims"} \
            or served["schema"] != "sia-raw-vector-served-observation-v1" \
            or served["status"] != "observed" \
            or served["model_identity"] != model.identity \
            or served["non_claims"] != siavectormodel.NON_CLAIMS \
            or type(served["observation"]) is not dict \
            or type(served["launch_config"]) is not dict \
            or served["launch_config"].get("model_identity") != model.identity \
            or type(served["serving_generation"]) is not dict \
            or served["serving_generation"].get("model_manifest_sha256") \
            != model.identity["manifest_sha256"]:
        raise siavector.VectorRefusal("vector served model identity disagrees")
    observation = copy.deepcopy(served["observation"])
    observation["model_serving"] = {
        key: copy.deepcopy(value) for key, value in served.items() if key != "observation"}
    return observation


def _observe(*, executable, expected, build_receipt, build_receipt_sha256,
             index_archive, index_sha256, embedding, queries, limit, timeout,
             scratch_parent, model_inputs=None, version=1,
             embedding_input_policy=None, expected_embedding_input_policy_sha256=None):
    """Capture then query fresh copies of one admitted physical archive.

    Caller expectations are supplied independently of the build under review.
    The observed status is deliberately not a benchmark verdict or JACKAL
    mathematical assurance class. No files are published and no hybrid
    fallback is available. Named adapter refusals propagate unchanged.
    """
    expected = _expectation_values(expected)
    if type(timeout) not in (int, float) or not 0 < timeout <= 1800 \
            or not math.isfinite(timeout):
        raise siavector.VectorRefusal("vector timeout is invalid")
    policy_fields = {}
    if version == 2:
        policy_fields = {"embedding_input_policy": siavectoradmit.admit_embedding_input_policy(
            embedding_input_policy, expected_sha256=expected_embedding_input_policy_sha256, embedding=embedding),
            "embedding_input_policy_sha256": expected_embedding_input_policy_sha256}
    # Validate every query before capturing or opening artifacts. These null
    # digest sentinels are shape-only placeholders, never sent to a process;
    # capture below removes them and supplies the independently observed roots.
    pending = siavectoradmit.admit_request({
        "v": version, "lane": "raw_vector", "operation": "query", **policy_fields,
        "queries": queries, "limit": limit,
        "snapshot": {"fd": None, "logical_sha256": "0" * 64,
                     "catalog_sha256": "0" * 64},
        "embedding": embedding,
        "binding": {"executable_sha256": expected["executable_sha256"],
                    "build_receipt_sha256": build_receipt_sha256},
    })
    embedding = pending["embedding"]
    queries = pending["queries"]
    limit = pending["limit"]
    if version == 2:
        if type(model_inputs) is not dict or set(model_inputs) != {"expectations", "runtime"}:
            raise siavector.VectorRefusal("v2 vector observation requires owned model inputs")
        # The full query/policy request has already been admitted before making
        # detached model-launch inputs. V2 has no unbound diagnostic fallback.
        model_inputs = _bound_model_inputs(model_inputs["expectations"], model_inputs["runtime"])
    with siavector.sealed_file(
            build_receipt, build_receipt_sha256,
            max_bytes=siavector.sialib.MAX_STATE_JSON_BYTES) as build, \
            contextlib.ExitStack() as model_stack:
        try:
            raw = os.pread(build.fd, build.size, 0)
            receipt = siaqueue.strict_json_loads(raw.decode("utf-8", errors="strict"))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise siavector.VectorRefusal("vector build receipt is invalid JSON") from exc
        _admit_build(receipt, expected)
        try:
            config_sha256 = (configuration_sha256_v2(
                embedding, limit, embedding_input_policy=policy_fields["embedding_input_policy"],
                expected_embedding_input_policy_sha256=expected_embedding_input_policy_sha256)
                if version == 2 else configuration_sha256(embedding, limit))
        except (KeyError, TypeError, ValueError) as exc:
            raise siavector.VectorRefusal("vector embedding configuration is invalid") from exc
        model = None
        if model_inputs is not None:
            model = model_stack.enter_context(siavectormodel.admit_model(
                **model_inputs["expectations"]))
        request = {
            "v": version, "lane": "raw_vector", "operation": "capture", **policy_fields,
            "queries": [], "limit": limit,
            "snapshot": {"fd": None, "logical_sha256": None,
                         "catalog_sha256": None},
            "embedding": embedding,
            "binding": {"executable_sha256": expected["executable_sha256"],
                        "build_receipt_sha256": build.sha256},
        }
        observations = []
        for operation in ("capture", "query"):
            request["operation"] = operation
            if operation == "query":
                request["queries"] = queries
                for field in ("logical_sha256", "catalog_sha256"):
                    request["snapshot"][field] = observations[0]["payload"]["bindings"][field]
            with siavector.private_index_snapshot(
                    index_archive, index_sha256,
                    scratch_parent=scratch_parent) as snapshot:
                if model is None:
                    observation = siavector.invoke_adapter(
                        executable, expected["executable_sha256"], request,
                        snapshot["descriptor_parent"], timeout=timeout,
                        scratch_parent=scratch_parent)
                else:
                    served = siavectormodel.invoke_model_adapter(
                        admitted=model, shared_runtime=model_inputs["runtime"],
                        executable=executable, executable_sha256=expected["executable_sha256"],
                        request=request, snapshot_directory=snapshot["descriptor_parent"],
                        timeout=timeout, scratch_parent=scratch_parent)
                    observation = _served_observation(served, model)
                observation["payload"] = siavectoradmit.admit_response(
                    observation["payload"], request,
                    executable_sha256=expected["executable_sha256"],
                    request_sha256=observation["request_sha256"],
                    config_sha256=config_sha256)
                observation["physical_manifest_sha256"] = snapshot["manifest_sha256"]
                if observations and snapshot["manifest_sha256"] \
                        != observations[0]["physical_manifest_sha256"]:
                    raise siavector.VectorRefusal("vector physical snapshot copies disagree")
                observations.append(observation)
            build.assert_current()
        result = {
            "schema": "sia-raw-vector-bound-observation-v2" if version == 2
                      else "sia-raw-vector-observation-v1" if model is None
                      else "sia-raw-vector-bound-observation-v1", "status": "observed", **policy_fields,
            "lane": "raw_vector", "build_receipt_sha256": build.sha256,
            "index_archive_sha256": index_sha256,
            "expected": copy.deepcopy(expected), "embedding": embedding,
            "config_sha256": config_sha256,
            "capture": observations[0], "query": observations[1],
            "build_non_claims": receipt["non_claims"],
            "non_claims": [
                "This observation does not attest served model weights or earn a cognitive claim."
                if model is None else
                "Sealed CPU model inputs and owned serving generations are bound; computation, relevance and cognitive claims are not proved.",
                "Build receipt identities are caller expectations, not independent package authentication.",
                "The physical archive scopes this run; it does not attest the resident index or complete machine history.",
                "Adapter non_claims remain controlling and are retained in each complete response.",
            ],
        }
        if model is not None:
            result["model_identity"] = copy.deepcopy(model.identity)
        return result


def observe(*, executable, expected, build_receipt, build_receipt_sha256,
            index_archive, index_sha256, embedding, queries, limit, timeout,
            scratch_parent):
    """Diagnostic raw-vector observation; served model inputs are not admitted."""
    return _observe(executable=executable, expected=expected, build_receipt=build_receipt,
                    build_receipt_sha256=build_receipt_sha256, index_archive=index_archive,
                    index_sha256=index_sha256, embedding=embedding, queries=queries,
                    limit=limit, timeout=timeout, scratch_parent=scratch_parent)


def _bound_model_inputs(model_expectations, shared_runtime):
    if type(model_expectations) is not dict or set(model_expectations) != {
            "package_root", "package_sha256", "model_root", "model_name",
            "manifest_sha256", "release_version", "release_archive_sha256"} \
            or type(shared_runtime) is not list or not shared_runtime:
        raise siavector.VectorRefusal("vector model expectations and runtime are required")
    return {"expectations": copy.deepcopy(model_expectations),
            "runtime": copy.deepcopy(shared_runtime)}


def observe_bound(*, model_expectations, shared_runtime, **observation_inputs):
    """Require admitted model inputs for capture and query, without an ambient fallback."""
    if {"version", "embedding_input_policy", "expected_embedding_input_policy_sha256"} & set(observation_inputs):
        raise siavector.VectorRefusal("v1 vector observation does not accept v2 policy arguments")
    model_inputs = _bound_model_inputs(model_expectations, shared_runtime)
    try:
        return _observe(**observation_inputs, model_inputs=model_inputs)
    except siavectormodel.ModelRefusal as exc:
        refusal = siavector.VectorRefusal("vector model serving refused: " + str(exc))
        refusal.non_claims = list(siavectormodel.NON_CLAIMS)
        raise refusal from exc


def observe_bound_v2(*, executable, expected, build_receipt, build_receipt_sha256,
                     index_archive, index_sha256, embedding, queries, limit, timeout,
                     scratch_parent, model_expectations, shared_runtime,
                     embedding_input_policy, expected_embedding_input_policy_sha256):
    """A separately versioned, policy-bound observation with no guessed mode."""
    try:
        return _observe(
            executable=executable, expected=expected, build_receipt=build_receipt,
            build_receipt_sha256=build_receipt_sha256, index_archive=index_archive,
            index_sha256=index_sha256, embedding=embedding, queries=queries, limit=limit,
            timeout=timeout, scratch_parent=scratch_parent, version=2,
            model_inputs={"expectations": model_expectations, "runtime": shared_runtime},
            embedding_input_policy=embedding_input_policy,
            expected_embedding_input_policy_sha256=expected_embedding_input_policy_sha256)
    except siavectormodel.ModelRefusal as exc:
        refusal = siavector.VectorRefusal("vector model serving refused: " + str(exc))
        refusal.non_claims = list(siavectormodel.NON_CLAIMS)
        raise refusal from exc


def _prepare_bound(*, executable, expected, build_receipt, build_receipt_sha256,
                   request, output_directory, timeout, scratch_parent,
                   model_expectations, shared_runtime, version,
                   expected_embedding_input_policy_sha256=None):
    """Prepare a new private index and admit its complete page/chunk receipt.

    Output freshness and partial-index retention are enforced by the owned
    model launch lane. This controller never archives or promotes a partial
    result. No resident index or ambient model fallback is available.
    """
    expected = _expectation_values(expected)
    if version == 2:
        if type(request) is not dict:
            raise siavector.VectorRefusal("v2 vector preparation request is invalid")
        siavectoradmit._embedding_input_policy(request.get("embedding_input_policy"),
                                             expected_embedding_input_policy_sha256, request.get("embedding"))
        if request.get("embedding_input_policy_sha256") != expected_embedding_input_policy_sha256:
            raise siavector.VectorRefusal("v2 vector preparation policy differs from its external pin")
    request = siavectorprepare.admit_request(request)
    if request["v"] != version:
        raise siavector.VectorRefusal("vector preparation request version differs from its entrypoint")
    policy_fields = ({key: request[key] for key in ("embedding_input_policy", "embedding_input_policy_sha256")}
                     if version == 2 else {})
    if type(timeout) not in (int, float) or not 0 < timeout <= 1800 \
            or not math.isfinite(timeout):
        raise siavector.VectorRefusal("vector timeout is invalid")
    model_inputs = _bound_model_inputs(model_expectations, shared_runtime)
    original_request_sha256 = hashlib.sha256(siavector._canonical_bytes(request)).hexdigest()
    try:
        with siavector.sealed_file(
                build_receipt, build_receipt_sha256,
                max_bytes=siavector.sialib.MAX_STATE_JSON_BYTES) as build:
            try:
                receipt = siaqueue.strict_json_loads(
                    os.pread(build.fd, build.size, 0).decode("utf-8", errors="strict"))
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise siavector.VectorRefusal("vector build receipt is invalid JSON") from exc
            _admit_build(receipt, expected)
            with siavectormodel.admit_model(**model_inputs["expectations"]) as model:
                served = siavectormodel.invoke_model_adapter(
                    admitted=model, shared_runtime=model_inputs["runtime"],
                    executable=executable, executable_sha256=expected["executable_sha256"],
                    request=request, snapshot_directory=output_directory,
                    timeout=timeout, scratch_parent=scratch_parent)
                observation = _served_observation(served, model)
                if observation.get("bound_request_sha256") != original_request_sha256 \
                        or observation.get("executable_sha256") != expected["executable_sha256"] \
                        or type(observation.get("returncode")) is not int \
                        or observation["returncode"] != 0:
                    raise siavector.VectorRefusal("vector preparation observation binding disagrees")
                observation["payload"] = siavectorprepare.admit_response(
                    observation.get("payload"), request,
                    request_sha256=observation.get("request_sha256"))
                model_identity = copy.deepcopy(model.identity)
            build.assert_current()
            return {
                "schema": "sia-raw-vector-bound-preparation-v2" if version == 2
                          else "sia-raw-vector-bound-preparation-v1", "status": "observed", **policy_fields,
                "dataset_sha256": request["dataset_sha256"], "pages_sha256": request["pages_sha256"],
                "build_receipt_sha256": build.sha256, "expected": expected,
                "model_identity": model_identity, "preparation": observation,
                "build_non_claims": receipt["non_claims"],
                "non_claims": [
                    "Sealed CPU model inputs and complete preparation receipts are bound; computation and cognitive improvement are not proved.",
                    "Caller build expectations are not independent package authentication.",
                    "This is a new private projection, not an attestation of the resident index or complete machine history.",
                    "Digest-only document-vector witnesses are not independently reconstructed by the parent.",
                    "All preparer and model non_claims remain controlling in the complete retained observation.",
                ],
            }
    except siavectormodel.ModelRefusal as exc:
        refusal = siavector.VectorRefusal("vector model serving refused: " + str(exc))
        refusal.non_claims = list(siavectormodel.NON_CLAIMS)
        raise refusal from exc


def prepare_bound(*, executable, expected, build_receipt, build_receipt_sha256,
                  request, output_directory, timeout, scratch_parent,
                  model_expectations, shared_runtime):
    """Original v1 preparation entrypoint; v2 must be selected explicitly."""
    return _prepare_bound(
        executable=executable, expected=expected, build_receipt=build_receipt,
        build_receipt_sha256=build_receipt_sha256, request=request,
        output_directory=output_directory, timeout=timeout, scratch_parent=scratch_parent,
        model_expectations=model_expectations, shared_runtime=shared_runtime, version=1)


def prepare_bound_v2(*, executable, expected, build_receipt, build_receipt_sha256,
                     request, output_directory, timeout, scratch_parent,
                     model_expectations, shared_runtime, expected_embedding_input_policy_sha256):
    """Prepare a fresh index for an independently pinned explicit input policy."""
    return _prepare_bound(
        executable=executable, expected=expected, build_receipt=build_receipt,
        build_receipt_sha256=build_receipt_sha256, request=request,
        output_directory=output_directory, timeout=timeout, scratch_parent=scratch_parent,
        model_expectations=model_expectations, shared_runtime=shared_runtime, version=2,
        expected_embedding_input_policy_sha256=expected_embedding_input_policy_sha256)
