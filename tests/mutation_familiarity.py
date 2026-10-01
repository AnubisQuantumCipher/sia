#!/usr/bin/env python3
"""Run isolated, sequential production mutations for familiarity integrity.

This is an explicitly scheduled evidence harness, not a discovery test. It
copies only the runtime and named test dependencies into a fresh directory
under --output-parent. It never edits the source checkout. Every mutation
runs its named tests green, changes copied production bytes, requires an
assertion failure without errors/skips, restores the exact bytes, and runs
the same tests green again. The copied tree, patches, logs, result records,
and their SHA-256 manifest are retained for review.

The result distinguishes these selected mutants only. It is not exhaustive
mutation coverage, a live-system test, or evidence of a cognitive benchmark
win. The cockpit binding check is explicitly labeled as a source contract;
the text formatter, CLI, producer, and policy checks execute real behavior.
"""

import argparse
from dataclasses import dataclass
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


@dataclass(frozen=True)
class Mutation:
    name: str
    path: str
    before: str
    after: str
    test: str
    function: str = ""
    check_kind: str = "behavior"


NOVELTY = "tests.test_cognitive_attention_novelty.NoveltyEncodingContract."
MIGRATION = "tests.test_rehearsal.Migration."
SURFACE = "tests.test_familiarity_surface."
MUTATIONS = (
    Mutation(
        "missing-state-claims-complete", "bin/siamind.py",
        '        mind["familiarity_complete"] = False\n'
        '        mind["familiarity_bootstrap_pending"] = True\n',
        '        mind["familiarity_complete"] = True\n'
        '        mind["familiarity_bootstrap_pending"] = False\n',
        NOVELTY + "test_missing_mind_cannot_claim_complete_familiarity",
        "load_mind"),
    Mutation(
        "clean-bootstrap-capability-disabled", "bin/siamind.py",
        "        inventory_complete and not history_bearing)",
        "        False)",
        NOVELTY + "test_exhaustive_history_free_bootstrap_enables_real_first_claims",
        "baseline_graph_familiarity"),
    Mutation(
        "history-bootstrap-claims-complete", "bin/siamind.py",
        "        inventory_complete and not history_bearing)",
        "        inventory_complete)",
        NOVELTY + "test_history_bearing_inventory_cannot_complete_bootstrap",
        "baseline_graph_familiarity"),
    Mutation(
        "history-namespace-check-removed", "bin/siamind.py",
        '        or slug.startswith(("events/", "epochs/"))\n', "",
        NOVELTY + "test_history_namespace_disguised_as_note_cannot_complete_bootstrap",
        "baseline_graph_familiarity"),
    Mutation(
        "omitted-inventory-claims-complete", "bin/siamind.py",
        "        inventory_complete and not history_bearing)",
        "        not history_bearing)",
        NOVELTY + "test_admitted_graph_omissions_terminally_withhold_completeness",
        "baseline_graph_familiarity"),
    Mutation(
        "unadmitted-graph-bootstrap-accepted", "bin/siamind.py",
        "    if not snapshot_complete or not pages_total_complete:\n"
        '        raise ValueError("graph familiarity snapshot is not admitted")\n',
        "",
        NOVELTY + "test_unadmitted_or_malformed_graph_refuses_bootstrap_atomically",
        "baseline_graph_familiarity"),
    Mutation(
        "legacy-completeness-trusted", "bin/siamind.py",
        '        mind["familiarity_complete"] = False\n',
        '        mind["familiarity_complete"] = bool(mind["familiarity_complete"])\n',
        MIGRATION + "test_legacy_and_downgraded_familiarity_markers_are_not_trusted",
        "migrate_mind"),
    Mutation(
        "familiarity-key-validation-removed", "bin/siamind.py",
        "        _canonical_familiarity_key(label)\n", "",
        MIGRATION + "test_persisted_familiarity_map_requires_strict_finite_timestamps",
        "_normalized_familiarity_map"),
    Mutation(
        "familiarity-number-types-coerced", "bin/siamind.py",
        "        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):\n"
        '            raise ValueError("mind familiarity time must be a JSON number")\n',
        "",
        MIGRATION + "test_persisted_familiarity_map_requires_strict_finite_timestamps",
        "_normalized_familiarity_map"),
    Mutation(
        "pending-bootstrap-encoding-admitted", "bin/siamind.py",
        "    if pending:\n"
        '        raise ValueError("novelty familiarity bootstrap is pending")\n',
        "",
        NOVELTY + "test_pending_bootstrap_cannot_observe_before_graph_admission",
        "novelty_encoding_gate"),
    Mutation(
        "pair-watermark-stops-refreshing", "bin/siamind.py",
        "    seen[pair] = ts if pair_last is None else max(pair_last, ts)\n",
        "    seen[pair] = ts if pair_last is None else pair_last\n",
        NOVELTY + "test_older_observation_cannot_move_familiarity_backward",
        "novelty_encoding_gate"),
    Mutation(
        "summary-always-claims-complete", "bin/siamind.py",
        '    familiarity_status = ("bootstrap-pending" if pending else\n'
        '                          "complete" if complete else "incomplete")\n',
        '    familiarity_status = "complete"\n',
        SURFACE + "FamiliaritySummarySurface."
        "test_summary_preserves_detector_availability_without_mutating_state",
        "memory_summary_view"),
    Mutation(
        "producer-always-claims-complete", "bin/sialib.py",
        '                   "familiarity_status": memory_state.get(\n'
        '                       "familiarity_status", "bootstrap-pending"\n'
        '                       if mind.get("familiarity_bootstrap_pending", False)\n'
        '                       else "complete"\n'
        '                       if mind.get("familiarity_complete", False)\n'
        '                       else "incomplete"),\n',
        '                   "familiarity_status": "complete",\n',
        "tests.test_pulse_sync.PulseSyncRetry."
        "test_pulse_publishes_actual_familiarity_from_memory_summary",
        "_pulse_transaction_guarded"),
    Mutation(
        "resident-enum-validation-removed", "bin/sialib.py",
        '            or value["v"] == 2 and (\n'
        '                not isinstance(mind.get("familiarity_status"), str)\n'
        '                or mind["familiarity_status"] not in {\n'
        '                    "complete", "incomplete", "bootstrap-pending"}) \\\n',
        "",
        SURFACE + "FamiliaritySummarySurface."
        "test_resident_validator_rejects_missing_or_malformed_detector_state",
        "_recoverable_status_integrity_checked"),
    Mutation(
        "cli-hides-familiarity", "bin/sia",
        '        print(f"  familiarity {familiarity}")\n', "",
        SURFACE + "FamiliarityCliSurface."
        "test_ready_corpus_does_not_hide_incomplete_familiarity",
        "_cmd_status_owned"),
    Mutation(
        "model-enum-validation-removed", "Model.js",
        '    if (["complete", "incomplete", "bootstrap-pending"].indexOf(\n'
        '          status.mind.familiarity_status) === -1) return false\n',
        "",
        SURFACE + "FamiliarityCockpitSurface."
        "test_current_model_requires_exact_current_shape_and_detector_state"),
    Mutation(
        "model-label-overclaims-completeness", "Model.js",
        '    return "incomplete · first/new-shape claims withheld"\n',
        '    return "complete · first/new-shape detection available"\n',
        SURFACE + "FamiliarityCockpitSurface."
        "test_memory_lens_renders_scoped_availability_in_plain_text"),
    Mutation(
        "cockpit-disconnects-live-familiarity", "Cockpit.qml",
        "text: Model.familiarityStatusText(memoryLens.mind)",
        'text: "complete"',
        SURFACE + "FamiliarityCockpitSurface."
        "test_memory_lens_renders_scoped_availability_in_plain_text",
        check_kind="source-wiring-contract"),
)

SUPPORT_FILES = (
    "Model.js", "Cockpit.qml", "tests/sia_test_home.py",
    "tests/test_cli.py", "tests/test_cockpit_boundary_horizon.py",
    "tests/test_cognitive_attention_novelty.py", "tests/test_rehearsal.py",
    "tests/test_familiarity_surface.py", "tests/test_pulse_sync.py",
    "tests/mutation_familiarity.py",
)

RUNNER = r'''
import json
from pathlib import Path
import sys
import unittest

suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[2:])
result = unittest.TextTestRunner(verbosity=2).run(suite)
record = {
    "tests_run": result.testsRun,
    "failures": [{"test": test.id(), "traceback": trace}
                 for test, trace in result.failures],
    "errors": [{"test": test.id(), "traceback": trace}
               for test, trace in result.errors],
    "skipped": [{"test": test.id(), "reason": reason}
                for test, reason in result.skipped],
    "unexpected_successes": [test.id() for test in result.unexpectedSuccesses],
    "expected_failures": [test.id() for test, _ in result.expectedFailures],
    "successful": result.wasSuccessful(),
}
Path(sys.argv[1]).write_text(json.dumps(record, sort_keys=True) + "\n")
raise SystemExit(0 if result.wasSuccessful() else 1)
'''


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def _write_json(path, value):
    path.write_bytes(_json_bytes(value))


def _hashes(root, names):
    return {name: _sha((root / name).read_bytes()) for name in names}


def _mutated(source, spec):
    start, end = 0, len(source)
    if spec.function:
        marker = "\ndef " + spec.function + "("
        start = source.index(marker) + 1
        following = source.find("\ndef ", start)
        end = len(source) if following == -1 else following
    region = source[start:end]
    if region.count(spec.before) != 1 or spec.before == spec.after:
        raise RuntimeError("mutation anchor is not unique: " + spec.name)
    return source[:start] + region.replace(spec.before, spec.after) + source[end:]


def _run(repo, case, phase, test, executable, node):
    home = case / (phase + "-home")
    scratch = case / (phase + "-tmp")
    home.mkdir()
    scratch.mkdir()
    result_path = case / (phase + ".result.json")
    log_path = case / (phase + ".log")
    command = [str(executable), "-W", "error", "-c", RUNNER,
               str(result_path), test]
    env = {
        "HOME": str(home), "TMPDIR": str(scratch),
        "PATH": os.pathsep.join((str(executable.parent),
                                 str(node.parent), os.defpath)),
        "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
    }
    with log_path.open("wb") as output:
        completed = subprocess.run(
            command, cwd=repo, env=env, stdout=output,
            stderr=subprocess.STDOUT, timeout=60, check=False)
    result = json.loads(result_path.read_bytes())
    if result["tests_run"] != 1 or result["skipped"] \
            or result["expected_failures"] or result["unexpected_successes"]:
        raise RuntimeError("incomplete targeted execution: " + test)
    record = {
        "command": command, "cwd": str(repo), "environment": env,
        "returncode": completed.returncode, "result": result,
        "result_sha256": _sha(result_path.read_bytes()),
        "log_sha256": _sha(log_path.read_bytes()),
    }
    _write_json(case / (phase + ".execution.json"), record)
    return record


def _green(record):
    return record["returncode"] == 0 and record["result"]["successful"] \
        and not record["result"]["failures"] and not record["result"]["errors"]


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
    node_path = shutil.which("node")
    if node_path is None:
        parser.error("Node is required; cockpit checks must not skip")
    node = Path(node_path).resolve(strict=True)
    run = Path(tempfile.mkdtemp(prefix="familiarity-mutations-", dir=parent))
    repo = run / "checkout"
    repo.mkdir()
    print(str(run), flush=True)
    names = sorted(set(SUPPORT_FILES) | {
        str(path.relative_to(source)) for path in (source / "bin").iterdir()
        if path.is_file() and path.suffix != ".pyc"})
    source_hashes = {}
    for name in names:
        original, target = source / name, repo / name
        if original.is_symlink() or not original.is_file():
            raise RuntimeError("capture requires a regular source file: " + name)
        data = original.read_bytes()
        source_hashes[name] = _sha(data)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(original.stat().st_mode & 0o777)
    if _hashes(source, names) != source_hashes:
        raise RuntimeError("source changed while capturing snapshot")
    snapshot = {
        "schema": "sia-familiarity-mutation-snapshot-v1",
        "source": str(source), "files": source_hashes,
        "python": {"path": str(executable),
                   "sha256": _sha(executable.read_bytes())},
        "node": {"path": str(node), "sha256": _sha(node.read_bytes())},
        "non_claims": [
            "Selected mutation coverage only; not exhaustive correctness.",
            "Captured checkout behavior only; not a live-system test.",
            "No cognitive benchmark superiority is established.",
            "Interpreter libraries and operating system are not transitively bound.",
            "Cockpit binding is a source contract; no rendered QML session is tested.",
        ],
    }
    _write_json(run / "snapshot.json", snapshot)
    # Validate the complete mutation plan before spending any test runs.
    # Wrappers may retain a function name after its implementation moves.
    mutant_sources = {
        spec.name: _mutated((repo / spec.path).read_text(), spec).encode()
        for spec in MUTATIONS
    }
    records = []
    for spec in MUTATIONS:
        case = run / spec.name
        case.mkdir()
        target = repo / spec.path
        original = target.read_bytes()
        changed = mutant_sources[spec.name]
        plan = {
            "name": spec.name, "path": spec.path, "test": spec.test,
            "check_kind": spec.check_kind,
            "before_sha256": _sha(original), "after_sha256": _sha(changed),
            "snapshot_sha256": _sha((run / "snapshot.json").read_bytes()),
        }
        _write_json(case / "plan.json", plan)
        patch = "".join(difflib.unified_diff(
            original.decode().splitlines(keepends=True),
            changed.decode().splitlines(keepends=True),
            fromfile="a/" + spec.path, tofile="b/" + spec.path))
        (case / "mutation.patch").write_text(patch)
        if _hashes(repo, names) != source_hashes:
            raise RuntimeError("captured tree changed before control")
        baseline = _run(repo, case, "control", spec.test, executable, node)
        if not _green(baseline):
            raise RuntimeError("baseline is not green: " + spec.name)
        if _hashes(repo, names) != source_hashes:
            raise RuntimeError("control run changed captured source files")
        try:
            target.write_bytes(changed)
            mutant_hashes = dict(source_hashes)
            mutant_hashes[spec.path] = _sha(changed)
            if _hashes(repo, names) != mutant_hashes:
                raise RuntimeError("mutation changed unexpected source files")
            mutant = _run(repo, case, "mutant", spec.test, executable, node)
            if _hashes(repo, names) != mutant_hashes:
                raise RuntimeError("mutant run changed captured source files")
        finally:
            target.write_bytes(original)
        if _hashes(repo, names) != source_hashes:
            raise RuntimeError("exact copied-tree restoration failed")
        restored = _run(repo, case, "restored", spec.test, executable, node)
        if _hashes(repo, names) != source_hashes:
            raise RuntimeError("restored run changed captured source files")
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
    artifacts = {
        str(path.relative_to(run)): _sha(path.read_bytes())
        for path in sorted(run.rglob("*"))
        if path.is_file() and repo not in path.parents
    }
    report = {
        "schema": "sia-familiarity-mutation-report-v1",
        "outcome": "selected-mutants-killed",
        "captured_source_files_unchanged": _hashes(source, names) == source_hashes,
        "copied_tree_restored": _hashes(repo, names) == source_hashes,
        "mutations": records, "artifacts_sha256": artifacts,
        "non_claims": snapshot["non_claims"],
    }
    _write_json(run / "report.json", report)
    print("report: " + str(run / "report.json"), flush=True)
    return 0 if report["captured_source_files_unchanged"] \
        and report["copied_tree_restored"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
