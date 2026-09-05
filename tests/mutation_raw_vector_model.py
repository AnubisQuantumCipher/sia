#!/usr/bin/env python3
"""Isolated assertion-kill evidence for private CPU model binding.

No Ollama, compiled adapter or namespace is launched. Selected fixture tests
run sequentially against copied production bytes. One test runs a tiny known
Python byte producer to exercise bounded draining and owned-process reaping.
Original files are never edited; exact copied bytes and modes are restored.
"""

import argparse
from dataclasses import dataclass
import difflib
import json
from pathlib import Path
import sys
import tempfile

from mutation_raw_vector_build import capture, file_sha, green, run_test, sha, write_json


PRODUCTION = "bin/siavectormodel.py"
TEST = "tests.test_raw_vector_model.RawVectorModelContract."
SUPPORT_FILES = (
    PRODUCTION, "tests/test_raw_vector_model.py", "tests/sia_test_home.py",
    "tests/mutation_raw_vector_build.py", "tests/mutation_raw_vector_model.py",
)


@dataclass(frozen=True)
class Mutation:
    name: str
    edits: tuple
    test: str


MUTATIONS = (
    Mutation("full-package-provenance-comparison-disabled", (
        ('    if _sha(_canonical(entries)) != package_sha256:\n', '    if False:\n'),
        ('                or _sha(_canonical(entries)) != self.identity["package_sha256"]:\n',
         '                or False:\n'),
    ), TEST + "test_gpu_change_is_not_hidden_by_cpu_execution_selection"),
    Mutation("write-seal-omitted", ((
        '_SEALS = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW\n',
        '_SEALS = (0 | fcntl.F_SEAL_GROW\n',
    ),), TEST + "test_full_package_provenance_but_only_cpu_and_referenced_model_bytes_sealed"),
    Mutation("excluded-gpu-backend-mounted", ((
        '            if _cpu_path(name):\n',
        '            if _cpu_path(name) or name.endswith("/libggml-cuda.so"):\n',
    ),), TEST + "test_full_package_provenance_but_only_cpu_and_referenced_model_bytes_sealed"),
    Mutation("sealed-leaf-digest-comparison-disabled", ((
        '        if size != info.st_size or digest.hexdigest() != expected:\n',
        '        if size != info.st_size:\n',
    ),), TEST + "test_pinned_package_manifest_release_and_blob_mismatches_refuse"),
    Mutation("cpu-force-policy-replaced-by-cuda", ((
        '    "OLLAMA_LLM_LIBRARY": "cpu", "OLLAMA_NO_CLOUD": "1",\n',
        '    "OLLAMA_LLM_LIBRARY": "cuda_v13", "OLLAMA_NO_CLOUD": "1",\n',
    ),), TEST + "test_launch_plan_binds_immutable_cpu_model_config_and_isolates_network"),
    Mutation("private-network-replaced-by-host-network", ((
        '        argv = ["/usr/bin/bwrap", "--unshare-user", "--unshare-pid", "--unshare-net",\n',
        '        argv = ["/usr/bin/bwrap", "--unshare-user", "--unshare-pid", "--share-net",\n',
    ),), TEST + "test_launch_plan_binds_immutable_cpu_model_config_and_isolates_network"),
    Mutation("readonly-runtime-root-not-an-actual-mount", ((
        '                "--size", "64000000", "--tmpfs", "/runtime",\n',
        '                "--dir", "/runtime",\n',
    ),), TEST + "test_readonly_runtime_roots_are_actual_mounts_before_remount"),
    Mutation("dynamic-loader-execute-permission-omitted", ((
        '            runtime_executable = destination in (\n'
        '                "/usr/bin/python3", "/usr/lib/ld-linux-aarch64.so.1")\n',
        '            runtime_executable = destination == "/usr/bin/python3"\n',
    ),), TEST + "test_dynamic_loader_is_an_executable_sealed_runtime_leaf"),
    Mutation("sealed-system-runtime-generation-recheck-disabled", ((
        '            if _generation(os.fstat(self.source_fd)) != self.generation \\\n'
        '                    or _generation(os.fstat(rebound)) != self.generation \\\n'
        '                    or fcntl.fcntl(self.fd, fcntl.F_GET_SEALS) & _SEALS != _SEALS:\n',
        '            if False:\n',
    ),), TEST + "test_runtime_file_replacement_is_detected_after_immutable_mount_admission"),
    Mutation("serving-generation-change-accepted", ((
        '        if before != after:\n', '        if False:\n',
    ),), TEST + "test_model_service_generation_change_refuses_and_reaps_only_owned_service"),
    Mutation("dead-owned-service-readiness-guard-disabled", ((
        '        service = _spawn_service(config)\n'
        '        if service.poll() is not None:\n',
        '        service = _spawn_service(config)\n'
        '        if False:\n',
    ),), TEST + "test_service_failure_never_borrows_existing_endpoint_or_invokes_adapter"),
    Mutation("release-metadata-allocation-ceiling-disabled", ((
        '        if receipt.size > MAX_JSON_BYTES:\n', '        if False:\n',
    ),), TEST + "test_release_metadata_ceiling_precedes_whole_body_allocation"),
    Mutation("fixed-index-child-generation-recheck-disabled", ((
        '                if (info.st_dev, info.st_ino, info.st_uid, info.st_mode) != (\n'
        '                        child_info.st_dev, child_info.st_ino, child_info.st_uid, child_info.st_mode):\n',
        '                if False:\n',
    ),), TEST + "test_fixed_index_child_replacement_cannot_inherit_parent_descriptor_authority"),
    Mutation("adapter-output-ceiling-disabled", ((
        '                    if count > MAX_OUTPUT_BYTES:\n', '                    if False:\n',
    ),), TEST + "test_adapter_producer_ceiling_reaps_the_owned_fixture_process"),
    Mutation("observation-nonclaims-dropped", ((
        '                "launch_config_sha256": _sha(_canonical(config)),\n'
        '                "non_claims": list(NON_CLAIMS)}\n',
        '                "launch_config_sha256": _sha(_canonical(config)),\n'
        '                "non_claims": []}\n',
    ),), TEST + "test_stable_owned_service_returns_generation_and_nonclaims_then_is_reaped"),
    Mutation("process-executable-inode-observation-omitted", ((
        '            "executable_device": before.st_dev, "executable_inode": before.st_ino,\n',
        '',
    ),), TEST + "test_process_probe_binds_inode_from_the_open_executable_descriptor"),
    Mutation("mounted-executable-probe-follows-alias", ((
        '        descriptor = _open(path, os.O_RDONLY)\n',
        '        descriptor = os.open(path, os.O_RDONLY)\n',
    ),), TEST + "test_mounted_executable_identity_hashes_nofollow_regular_leaf"),
    Mutation("proc-display-name-replaces-mounted-object-authority", ((
        '        if parent["executable_device"] != service_mount["device"] \\\n',
        '        if parent["executable"] != "/runtime/ollama/bin/ollama" \\\n'
        '                or parent["executable_device"] != service_mount["device"] \\\n',
    ),), TEST + "test_serving_executable_display_alias_is_not_mistaken_for_object_authority"),
    Mutation("service-and-runner-mounted-inode-comparisons-disabled", (
        ('        if parent["executable_device"] != service_mount["device"] \\\n'
         '                or parent["executable_inode"] != service_mount["inode"] \\\n',
         '        if False \\\n'),
        ('                if info["ppid"] == service.pid \\\n'
         '                        and info["executable_device"] == runner_mount["device"] \\\n'
         '                        and info["executable_inode"] == runner_mount["inode"]:\n',
         '                if info["ppid"] == service.pid:\n'),
    ), TEST + "test_serving_executable_inode_device_or_hash_mismatch_refuses"),
)


def identity(root):
    result = {}
    for name in SUPPORT_FILES:
        raw, mode = capture(root / name)
        result[name] = {"sha256": sha(raw), "mode": mode}
    return result


def mutated(original, mutation):
    changed = original
    for before, after in mutation.edits:
        if changed.count(before) != 1 or before == after:
            raise RuntimeError("mutation anchor is not unique: " + mutation.name)
        changed = changed.replace(before, after)
    compile(changed, "<isolated-model-mutation>", "exec")
    return changed.encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--output-parent", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    parent = args.output_parent.resolve(strict=True)
    if not source.is_dir() or not parent.is_dir():
        parser.error("source and output-parent must be existing directories")
    executable = Path(sys.executable).resolve(strict=True)
    run = Path(tempfile.mkdtemp(prefix="raw-vector-model-mutations-", dir=parent))
    repo = run / "checkout"
    repo.mkdir(mode=0o700)
    print(str(run), flush=True)
    original_identity = {}
    for name in SUPPORT_FILES:
        raw, mode = capture(source / name)
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        target.chmod(mode)
        original_identity[name] = {"sha256": sha(raw), "mode": mode}
    if identity(source) != original_identity or identity(repo) != original_identity:
        raise RuntimeError("source changed during isolated capture")
    snapshot = {
        "schema": "sia-raw-vector-model-mutation-snapshot-v1", "source": str(source),
        "files": original_identity,
        "python": {"path": str(executable), "sha256": file_sha(executable)},
        "non_claims": [
            "Selected assertion-killed mutations are not exhaustive correctness or proof of a real model launch.",
            "ELF/model bytes are nonexecuted fixtures; a bounded known Python byte producer is the only subprocess fixture.",
            "No resident model service, live index or production namespace is exercised.",
            "The Python executable is hashed; its complete interpreter libraries and host kernel are not bound here.",
        ],
    }
    write_json(run / "snapshot.json", snapshot)
    original = (repo / PRODUCTION).read_bytes()
    mutants = {item.name: mutated(original.decode(), item) for item in MUTATIONS}
    records = []
    for item in MUTATIONS:
        case = run / item.name
        case.mkdir(mode=0o700)
        target = repo / PRODUCTION
        changed = mutants[item.name]
        plan = {"name": item.name, "path": PRODUCTION, "test": item.test,
                "before_sha256": sha(original), "after_sha256": sha(changed),
                "snapshot_sha256": file_sha(run / "snapshot.json")}
        write_json(case / "plan.json", plan)
        (case / "mutation.patch").write_text("".join(difflib.unified_diff(
            original.decode().splitlines(keepends=True), changed.decode().splitlines(keepends=True),
            fromfile="a/" + PRODUCTION, tofile="b/" + PRODUCTION)))
        if identity(repo) != original_identity:
            raise RuntimeError("copied source changed before control")
        control = run_test(repo, case, "control", item.test, executable)
        if not green(control) or identity(repo) != original_identity:
            raise RuntimeError("selected control is not green and unchanged: " + item.name)
        expected_mutant = dict(original_identity)
        expected_mutant[PRODUCTION] = {"sha256": sha(changed), "mode": original_identity[PRODUCTION]["mode"]}
        mutant, mutation_error = None, None
        try:
            target.write_bytes(changed)
            if identity(repo) != expected_mutant:
                raise RuntimeError("mutation changed unexpected copied bytes")
            mutant = run_test(repo, case, "mutant", item.test, executable)
            if identity(repo) != expected_mutant:
                raise RuntimeError("mutant run changed copied source")
        except Exception as exc:
            mutation_error = str(exc)
        finally:
            target.write_bytes(original)
            target.chmod(original_identity[PRODUCTION]["mode"])
        if identity(repo) != original_identity:
            raise RuntimeError("exact copied-tree restoration failed")
        restored = run_test(repo, case, "restored", item.test, executable)
        restored_unchanged = identity(repo) == original_identity
        killed = mutant is not None and mutant["returncode"] == 1 \
            and bool(mutant["result"]["failures"]) and not mutant["result"]["errors"]
        record = {**plan, "killed": killed, "mutation_error": mutation_error,
                  "restored_green": green(restored), "restored_unchanged": restored_unchanged,
                  "restored_sha256": file_sha(target)}
        write_json(case / "verdict.json", record)
        records.append(record)
        print(item.name + ": " + ("assertion kill; exact restoration green"
              if killed and green(restored) and restored_unchanged else "FAILED"), flush=True)
        if mutation_error or not killed or not green(restored) or not restored_unchanged:
            raise RuntimeError("mutation contract failed: " + item.name)
    artifacts = {str(path.relative_to(run)): file_sha(path)
                 for path in sorted(run.rglob("*"))
                 if path.is_file() and repo not in path.parents}
    report = {"schema": "sia-raw-vector-model-mutation-report-v1",
              "outcome": "selected-mutants-killed",
              "captured_source_files_unchanged": identity(source) == original_identity,
              "copied_tree_restored": identity(repo) == original_identity,
              "mutations": records, "artifacts_sha256": artifacts,
              "non_claims": snapshot["non_claims"]}
    write_json(run / "report.json", report)
    print("report: " + str(run / "report.json"), flush=True)
    return 0 if report["captured_source_files_unchanged"] and report["copied_tree_restored"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
