#!/usr/bin/env python3
"""Scheduled sequential mutation proof for the raw-vector admission boundary.

The shared harness helpers operate only on a fresh retained disk copy. Every
selected mutation has a green control, an assertion-failing mutant, and an
exactly restored green control. Erroring/skipped tests do not count as kills.
This is selected boundary coverage, not an exhaustive security proof, live
index validation, build provenance admission, or a cognitive benchmark win.
"""

import argparse
import difflib
import os
from pathlib import Path
import shutil
import sys
import tempfile

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from tests.mutation_familiarity import (
    Mutation, _green, _hashes, _mutated, _run, _sha, _write_json,
)


RESPONSE = "tests.test_raw_vector_admission.RawVectorAdmission."
REQUEST = "tests.test_raw_vector_admission.RawVectorRequestAdmission."
MUTATIONS = (
    Mutation(
        "request-validation-removed", "bin/siavectoradmit.py",
        "        _request(request)\n", "",
        REQUEST + "test_wrong_top_level_and_nested_shapes_refuse_before_serialization",
        "admit_request"),
    Mutation(
        "request-copied-before-admission", "bin/siavectoradmit.py",
        "        _request(request)\n", "        _request(copy.deepcopy(request))\n",
        REQUEST + "test_wrong_top_level_and_nested_shapes_refuse_before_serialization",
        "admit_request"),
    Mutation(
        "request-return-aliases-caller", "bin/siavectoradmit.py",
        "        return copy.deepcopy(request)\n", "        return request\n",
        REQUEST + "test_valid_capture_and_query_requests_are_detached_after_admission",
        "admit_request"),
    Mutation(
        "gateway-truncation-ceiling-bypassed", "bin/siavectoradmit.py",
        "MAX_QUERY_BYTES = 8000\n", "MAX_QUERY_BYTES = MAX_REQUEST_BYTES\n",
        REQUEST + "test_exact_ascii_and_unicode_query_byte_boundaries_are_preserved"),
    Mutation(
        "boolean-identities-treated-as-integers", "bin/siavectoradmit.py",
        "    return type(value) is int and low <= value <= high\n",
        "    return isinstance(value, int) and low <= value <= high\n",
        RESPONSE + "test_top_level_status_lane_operation_and_version_are_exact",
        "_integer"),
    Mutation(
        "caller-generation-bindings-ignored", "bin/siavectoradmit.py",
        "    if any(bindings[key] != value for key, value in expected.items()):\n"
        '        _refuse("binding disagrees with the requested observation")\n',
        "",
        RESPONSE + "test_all_process_build_config_request_and_snapshot_identities_are_bound",
        "_admit"),
    Mutation(
        "query-identities-and-order-ignored", "bin/siavectoradmit.py",
        '        if result["id"] != query["id"] \\\n'
        '                or result["query_sha256"] != hashlib.sha256(\n'
        '                    query["text"].encode("utf-8")).hexdigest():\n'
        '            _refuse("query identity or order disagrees with the request")\n',
        "",
        RESPONSE + "test_query_ids_hashes_count_and_order_cannot_be_rewritten",
        "_admit"),
    Mutation(
        "vector-finiteness-and-nonzero-ignored", "bin/siavectoradmit.py",
        "        if not all(math.isfinite(value) for value in components) \\\n"
        "                or not any(value != 0 for value in components):\n"
        '            _refuse("query vector must be finite and nonzero")\n',
        "",
        RESPONSE + "test_query_vectors_are_exact_finite_nonzero_binary32_observations",
        "_admit"),
    Mutation(
        "ranked-row-byte-hash-ignored", "bin/siavectoradmit.py",
        '        if not _digest(result["ranked_rows_sha256"]) \\\n'
        '                or hashlib.sha256(encoded_rows).hexdigest() \\\n'
        '                != result["ranked_rows_sha256"]:\n'
        '            _refuse("ranked row byte identity is invalid")\n',
        "",
        RESPONSE + "test_row_bytes_must_hash_parse_strictly_and_match_the_returned_rows",
        "_admit"),
    Mutation(
        "returned-rows-detached-from-bound-bytes", "bin/siavectoradmit.py",
        '        if not _same_json(result["rows"], wire_rows):\n'
        '            _refuse("ranked row bytes disagree with the returned rows")\n',
        "",
        RESPONSE + "test_row_bytes_must_hash_parse_strictly_and_match_the_returned_rows",
        "_admit"),
    Mutation(
        "bound-row-json-uses-last-key-wins", "bin/siavectoradmit.py",
        "            wire_rows = siaqueue.strict_json_loads(\n",
        '            wire_rows = __import__("json").loads(\n',
        RESPONSE + "test_duplicate_members_inside_bound_row_bytes_cannot_use_last_key_wins",
        "_admit"),
    Mutation(
        "score-base64-padding-not-canonical", "bin/siavectoradmit.py",
        "    if len(decoded) > maximum \\\n"
        '            or base64.b64encode(decoded).decode("ascii") != value:\n',
        "    if len(decoded) > maximum:\n",
        RESPONSE + "test_score_base64_padding_bits_cannot_relabel_identical_bytes",
        "_blob"),
    Mutation(
        "score-binary64-check-ignored", "bin/siavectoradmit.py",
        '        if not math.isfinite(score) or row["score"] != score:\n'
        '            _refuse("score bytes disagree with the numeric score")\n',
        "",
        RESPONSE + "test_score_binary64_bytes_are_finite_complete_and_match_numeric_score",
        "_rows"),
    Mutation(
        "foreign-source-row-admitted", "bin/siavectoradmit.py",
        '                or row["source_id"] != "sia" \\\n', "",
        RESPONSE + "test_row_identity_source_and_scalar_fields_are_strict", "_rows"),
    Mutation(
        "ranked-order-not-checked", "bin/siavectoradmit.py",
        "        if previous is not None and (\n"
        "                score > previous[0]\n"
        "                or score == previous[0] and current[1:] < previous[1:]):\n"
        '            _refuse("ranked row order is invalid")\n',
        "",
        RESPONSE + "test_row_order_and_unique_page_chunk_slug_identities_are_preserved",
        "_rows"),
    Mutation(
        "adapter-nonclaims-not-required", "bin/siavectoradmit.py",
        '    if type(payload.get("non_claims")) is not list \\\n'
        '            or not _same_json(payload["non_claims"], list(NON_CLAIMS)):\n'
        '        _refuse("non-claim roster is invalid")\n',
        "",
        RESPONSE + "test_nonclaims_cannot_be_removed_extended_reworded_or_type_confused",
        "_admit"),
    Mutation(
        "refusal-drops-nonclaims", "bin/siavectoradmit.py",
        "        self.non_claims = tuple(non_claims)\n",
        "        self.non_claims = ()\n",
        RESPONSE + "test_adapter_refusal_preserves_named_reason_without_returning_rows"),
)
SUPPORT = (
    "tests/sia_test_home.py", "tests/test_raw_vector_admission.py",
    "tests/mutation_familiarity.py", "tests/mutation_raw_vector_admission.py",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=REPO)
    parser.add_argument("--output-parent", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    parent = args.output_parent.resolve(strict=True)
    if not source.is_dir() or not parent.is_dir():
        parser.error("source and output-parent must be existing directories")
    executable = Path(sys.executable).resolve(strict=True)
    node_path = shutil.which("node")
    if node_path is None:
        parser.error("shared evidence runner requires the Node executable identity")
    node = Path(node_path).resolve(strict=True)
    run = Path(tempfile.mkdtemp(prefix="raw-vector-admission-mutations-", dir=parent))
    repo = run / "checkout"
    repo.mkdir()
    print(str(run), flush=True)
    names = sorted(set(SUPPORT) | {
        str(path.relative_to(source)) for path in (source / "bin").iterdir()
        if path.is_file() and path.suffix != ".pyc"})
    hashes = {}
    for name in names:
        original, target = source / name, repo / name
        if original.is_symlink() or not original.is_file():
            raise RuntimeError("capture requires regular source: " + name)
        data = original.read_bytes()
        hashes[name] = _sha(data)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(original.stat().st_mode & 0o777)
    if _hashes(source, names) != hashes:
        raise RuntimeError("source changed during capture")
    snapshot = {
        "schema": "sia-raw-vector-admission-mutation-snapshot-v1",
        "source": str(source), "files": hashes,
        "python": {"path": str(executable), "sha256": _sha(executable.read_bytes())},
        "node": {"path": str(node), "sha256": _sha(node.read_bytes())},
        "non_claims": [
            "Selected production mutations only; not exhaustive correctness or security.",
            "Captured checkout tests only; no live index or embedding provider was accessed.",
            "Build provenance, serving-model weights, and cognitive wins are not established.",
            "Interpreter libraries and operating system are not transitively bound.",
        ],
    }
    _write_json(run / "snapshot.json", snapshot)
    changes = {spec.name: _mutated((repo / spec.path).read_text(), spec).encode()
               for spec in MUTATIONS}
    records = []
    for spec in MUTATIONS:
        case = run / spec.name
        case.mkdir()
        target = repo / spec.path
        original, changed = target.read_bytes(), changes[spec.name]
        plan = {
            "name": spec.name, "path": spec.path, "test": spec.test,
            "check_kind": spec.check_kind, "before_sha256": _sha(original),
            "after_sha256": _sha(changed),
            "snapshot_sha256": _sha((run / "snapshot.json").read_bytes()),
        }
        _write_json(case / "plan.json", plan)
        (case / "mutation.patch").write_text("".join(difflib.unified_diff(
            original.decode().splitlines(keepends=True),
            changed.decode().splitlines(keepends=True),
            fromfile="a/" + spec.path, tofile="b/" + spec.path)))
        if _hashes(repo, names) != hashes:
            raise RuntimeError("captured tree changed before control")
        control = _run(repo, case, "control", spec.test, executable, node)
        if not _green(control) or _hashes(repo, names) != hashes:
            raise RuntimeError("control is not unchanged and green: " + spec.name)
        try:
            target.write_bytes(changed)
            mutated_hashes = {**hashes, spec.path: _sha(changed)}
            if _hashes(repo, names) != mutated_hashes:
                raise RuntimeError("unexpected source change before mutant")
            mutant = _run(repo, case, "mutant", spec.test, executable, node)
            if _hashes(repo, names) != mutated_hashes:
                raise RuntimeError("mutant run changed copied source")
        finally:
            target.write_bytes(original)
        if _hashes(repo, names) != hashes:
            raise RuntimeError("byte-identical restoration failed")
        restored = _run(repo, case, "restored", spec.test, executable, node)
        if _hashes(repo, names) != hashes:
            raise RuntimeError("restored run changed copied source")
        killed = mutant["returncode"] == 1 \
            and bool(mutant["result"]["failures"]) \
            and not mutant["result"]["errors"]
        record = {**plan, "killed": killed, "restored_green": _green(restored),
                  "restored_sha256": _sha(target.read_bytes())}
        _write_json(case / "verdict.json", record)
        records.append(record)
        print(spec.name + ": " + (
            "killed; exact restoration green" if killed and _green(restored)
            else "FAILED"), flush=True)
        if not killed or not _green(restored):
            raise RuntimeError("mutation contract failed: " + spec.name)
    artifacts = {str(path.relative_to(run)): _sha(path.read_bytes())
                 for path in sorted(run.rglob("*"))
                 if path.is_file() and repo not in path.parents}
    report = {
        "schema": "sia-raw-vector-admission-mutation-report-v1",
        "outcome": "selected-mutants-killed", "mutations": records,
        "captured_source_files_unchanged": _hashes(source, names) == hashes,
        "copied_tree_restored": _hashes(repo, names) == hashes,
        "artifacts_sha256": artifacts, "non_claims": snapshot["non_claims"],
    }
    _write_json(run / "report.json", report)
    print("report: " + str(run / "report.json"), flush=True)
    return 0 if report["captured_source_files_unchanged"] \
        and report["copied_tree_restored"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
