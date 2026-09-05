"""Bound raw-vector observations, separate from the cognitive claim gate.

This controller admits caller-pinned build provenance, restores a physical
index generation for each invocation, and validates complete adapter output.
Model-service admission and held-out comparisons are further obligations.
"""

import copy
import hashlib
import math
import os
import re

import siaqueue
import siavector
import siavectoradmit


_EXPECTED = {
    "executable_sha256": ("output", "sha256"),
    "builder_sha256": ("builder", "sha256"),
    "adapter_sha256": ("adapter", "sha256"),
    "bun_sha256": ("bun", "binary_sha256"),
    "gbrain_commit": ("gbrain", "commit"),
    "gbrain_lock_sha256": ("gbrain", "bun_lock_sha256"),
}


def configuration_sha256(embedding, limit):
    """Independently construct the adapter's effective, non-hybrid policy."""
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


def observe(*, executable, expected, build_receipt, build_receipt_sha256,
            index_archive, index_sha256, embedding, queries, limit, timeout,
            scratch_parent):
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
    # Validate every query before capturing or opening artifacts. These null
    # digest sentinels are shape-only placeholders, never sent to a process;
    # capture below removes them and supplies the independently observed roots.
    pending = siavectoradmit.admit_request({
        "v": 1, "lane": "raw_vector", "operation": "query",
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
    with siavector.sealed_file(
            build_receipt, build_receipt_sha256,
            max_bytes=siavector.sialib.MAX_STATE_JSON_BYTES) as build:
        try:
            raw = os.pread(build.fd, build.size, 0)
            receipt = siaqueue.strict_json_loads(raw.decode("utf-8", errors="strict"))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise siavector.VectorRefusal("vector build receipt is invalid JSON") from exc
        _admit_build(receipt, expected)
        try:
            config_sha256 = configuration_sha256(embedding, limit)
        except (KeyError, TypeError, ValueError) as exc:
            raise siavector.VectorRefusal("vector embedding configuration is invalid") from exc
        request = {
            "v": 1, "lane": "raw_vector", "operation": "capture",
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
                observation = siavector.invoke_adapter(
                    executable, expected["executable_sha256"], request,
                    snapshot["descriptor_parent"], timeout=timeout,
                    scratch_parent=scratch_parent)
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
        return {
            "schema": "sia-raw-vector-observation-v1", "status": "observed",
            "lane": "raw_vector", "build_receipt_sha256": build.sha256,
            "index_archive_sha256": index_sha256,
            "expected": copy.deepcopy(expected), "embedding": embedding,
            "config_sha256": config_sha256,
            "capture": observations[0], "query": observations[1],
            "build_non_claims": receipt["non_claims"],
            "non_claims": [
                "This observation does not attest served model weights or earn a cognitive claim.",
                "Build receipt identities are caller expectations, not independent package authentication.",
                "The physical archive scopes this run; it does not attest the resident index or complete machine history.",
                "Adapter non_claims remain controlling and are retained in each complete response.",
            ],
        }
