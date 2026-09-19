#!/usr/bin/env python3
"""Collect isolated, sequential mutation evidence for executable construction.

This explicit harness runs no real Bun builds. It copies the builder and its
fixture-compiler tests below --output-parent, runs the selected test green,
changes only copied production bytes, requires an assertion failure without
errors or skips, restores exact bytes, and runs the same test green again.
All patches, command logs, structured outcomes, and artifact hashes are kept.
The source checkout and resident installation are never modified.
"""

import argparse
from dataclasses import dataclass
import difflib
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile


BUILDER = "scripts/build-raw-vector"
TEST = "tests.test_raw_vector_build.RawVectorBuildContract."
SUPPORT_FILES = (
    BUILDER, "tests/sia_test_home.py", "tests/test_raw_vector_build.py",
    "tests/mutation_raw_vector_build.py",
)


@dataclass(frozen=True)
class Mutation:
    name: str
    edits: tuple
    test: str


PIN_COMPARISON = (
    '        if self.git("rev-parse", "HEAD").decode("ascii").strip() != pin["commit"]:\n'
)
MUTATIONS = (
    Mutation("requested-commit-replaced-by-observed-head", ((
        PIN_COMPARISON,
        '        pin["commit"] = self.git("rev-parse", "HEAD").decode("ascii").strip()\n'
        + PIN_COMPARISON,
    ),), TEST + "test_wrong_commit_is_refused_before_compiler_execution"),
    Mutation("source-closure-rechecks-disabled", (
        ("        if after_install != source_closure:\n", "        if False:\n"),
        ('        if self.closure(staged_source, self.work / "source-after-build.json",\n'
         '                        exclude=("node_modules",)) != source_closure:\n',
         "        if False:\n"),
    ), TEST + "test_install_cannot_rewrite_pinned_source"),
    Mutation("dependency-closure-recheck-disabled", ((
        '        if self.closure(dependencies, self.work / "dependencies-after-build.json") \\\n'
        '                != dependency_closure:\n',
        "        if False:\n",
    ),), TEST + "test_dependency_mutation_during_compilation_invalidates_receipt"),
    Mutation("dependency-copyfile-replaced-with-hardlink", ((
        '"--backend=copyfile"', '"--backend=hardlink"',
    ),), TEST + "test_supported_copyfile_backend_keeps_dependency_leaves_single_link"),
    Mutation("receipt-output-digest-fabricated", ((
        '            "output": {"path": "sia-raw-vector", "sha256": binary_digest,\n',
        '            "output": {"path": "sia-raw-vector", "sha256": "0" * 64,\n',
    ),), TEST + "test_receipt_binds_exact_source_compiler_adapter_closure_and_output"),
    Mutation("command-output-buffered-until-exit", ((
        "                        log.flush()\n"
        "                        os.fsync(log.fileno())\n",
        "                        pass\n",
    ),), TEST + "test_command_output_is_durable_before_builder_is_killed"),
    Mutation("command-start-journal-omitted", ((
        '            self.command_event("started", record)\n',
        "            pass\n",
    ),), TEST + "test_command_output_is_durable_before_builder_is_killed"),
    Mutation("failure-reason-replaced-with-generic-label", ((
        '            "reason": reason, "commands": self.commands,\n',
        '            "reason": "refused", "commands": self.commands,\n',
    ),), TEST + "test_command_failure_keeps_durable_output_and_refusal_record"),
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


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(65_536):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    with path.open("xb") as stream:
        stream.write((json.dumps(value, sort_keys=True, indent=2) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())


def capture(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 \
                or before.st_size > 1_048_576:
            raise RuntimeError("unsafe source file: " + str(path))
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(1_048_577)
        after = os.fstat(descriptor)
        current = path.stat(follow_symlinks=False)
        fields = lambda item: (item.st_dev, item.st_ino, item.st_mode,
                               item.st_nlink, item.st_size,
                               item.st_mtime_ns, item.st_ctime_ns)
        if fields(before) != fields(after) or fields(after) != fields(current) \
                or len(raw) > 1_048_576:
            raise RuntimeError("source changed during capture: " + str(path))
        return raw, stat.S_IMODE(before.st_mode)
    finally:
        os.close(descriptor)


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
    compile(changed, "<isolated-builder-mutation>", "exec")
    return changed.encode()


def run_test(repo, case, phase, selected, executable):
    home = case / (phase + "-home")
    scratch = case / (phase + "-tmp")
    home.mkdir(mode=0o700)
    scratch.mkdir(mode=0o700)
    result_path = case / (phase + ".result.json")
    log_path = case / (phase + ".log")
    command = [str(executable), "-B", "-W", "error", "-c", RUNNER,
               str(result_path), selected]
    environment = {
        "HOME": str(home), "TMPDIR": str(scratch),
        "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }
    with log_path.open("xb") as output:
        completed = subprocess.run(
            command, cwd=repo, env=environment, stdin=subprocess.DEVNULL,
            stdout=output, stderr=subprocess.STDOUT, timeout=60, check=False)
        output.flush()
        os.fsync(output.fileno())
    result = json.loads(result_path.read_bytes())
    record = {
        "command": command, "cwd": str(repo), "environment": environment,
        "returncode": completed.returncode, "result": result,
        "result_sha256": file_sha(result_path), "log_sha256": file_sha(log_path),
    }
    write_json(case / (phase + ".execution.json"), record)
    if result["tests_run"] != 1 or result["skipped"] \
            or result["expected_failures"] or result["unexpected_successes"]:
        raise RuntimeError("incomplete selected execution: " + selected)
    return record


def green(record):
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
    run = Path(tempfile.mkdtemp(prefix="raw-vector-build-mutations-", dir=parent))
    repo = run / "checkout"
    repo.mkdir(mode=0o700)
    print(str(run), flush=True)
    source_identity = {}
    for name in SUPPORT_FILES:
        raw, mode = capture(source / name)
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        target.chmod(mode)
        source_identity[name] = {"sha256": sha(raw), "mode": mode}
    if identity(source) != source_identity or identity(repo) != source_identity:
        raise RuntimeError("source changed while capturing snapshot")
    snapshot = {
        "schema": "sia-raw-vector-build-mutation-snapshot-v1",
        "source": str(source), "files": source_identity,
        "python": {"path": str(executable), "sha256": file_sha(executable)},
        "git": {"path": "/usr/bin/git", "sha256": file_sha(Path("/usr/bin/git"))},
        "non_claims": [
            "Selected production mutations only; not exhaustive correctness.",
            "The compiler is a byte-pinned fixture; this is not a real Bun build or retrieval benchmark.",
            "No resident service or index is exercised.",
            "Durability checks cover builder process loss, not a simulated power or storage failure.",
            "Interpreter libraries and the operating system are not transitively bound.",
        ],
    }
    write_json(run / "snapshot.json", snapshot)
    original = (repo / BUILDER).read_bytes()
    mutants = {item.name: mutated(original.decode(), item) for item in MUTATIONS}
    records = []
    for item in MUTATIONS:
        case = run / item.name
        case.mkdir(mode=0o700)
        target = repo / BUILDER
        changed = mutants[item.name]
        plan = {
            "name": item.name, "path": BUILDER, "test": item.test,
            "before_sha256": sha(original), "after_sha256": sha(changed),
            "snapshot_sha256": file_sha(run / "snapshot.json"),
        }
        write_json(case / "plan.json", plan)
        (case / "mutation.patch").write_text("".join(difflib.unified_diff(
            original.decode().splitlines(keepends=True),
            changed.decode().splitlines(keepends=True),
            fromfile="a/" + BUILDER, tofile="b/" + BUILDER)))
        if identity(repo) != source_identity:
            raise RuntimeError("copied source changed before control")
        control = run_test(repo, case, "control", item.test, executable)
        if not green(control) or identity(repo) != source_identity:
            raise RuntimeError("control is not green and unchanged: " + item.name)
        expected_mutant = dict(source_identity)
        expected_mutant[BUILDER] = {
            "sha256": sha(changed), "mode": source_identity[BUILDER]["mode"]}
        mutant = None
        mutation_error = None
        try:
            target.write_bytes(changed)
            if identity(repo) != expected_mutant:
                raise RuntimeError("mutation changed unexpected source files")
            mutant = run_test(repo, case, "mutant", item.test, executable)
            if identity(repo) != expected_mutant:
                raise RuntimeError("mutant run changed copied source files")
        except Exception as exc:
            mutation_error = str(exc)
        finally:
            target.write_bytes(original)
        if identity(repo) != source_identity:
            raise RuntimeError("exact copied-tree restoration failed")
        restored = run_test(repo, case, "restored", item.test, executable)
        restored_unchanged = identity(repo) == source_identity
        killed = mutant is not None and mutant["returncode"] == 1 \
            and bool(mutant["result"]["failures"]) \
            and not mutant["result"]["errors"]
        record = {
            **plan, "killed": killed, "mutation_error": mutation_error,
            "restored_green": green(restored),
            "restored_unchanged": restored_unchanged,
            "restored_sha256": file_sha(target),
        }
        write_json(case / "verdict.json", record)
        records.append(record)
        print(item.name + ": " + (
            "assertion kill; exact restoration green"
            if killed and green(restored) and restored_unchanged else "FAILED"),
            flush=True)
        if mutation_error or not killed or not green(restored) or not restored_unchanged:
            raise RuntimeError("mutation contract failed: " + item.name)
    artifacts = {
        str(path.relative_to(run)): file_sha(path)
        for path in sorted(run.rglob("*"))
        if path.is_file() and repo not in path.parents
    }
    report = {
        "schema": "sia-raw-vector-build-mutation-report-v1",
        "outcome": "selected-mutants-killed",
        "captured_source_files_unchanged": identity(source) == source_identity,
        "copied_tree_restored": identity(repo) == source_identity,
        "mutations": records, "artifacts_sha256": artifacts,
        "non_claims": snapshot["non_claims"],
    }
    write_json(run / "report.json", report)
    print("report: " + str(run / "report.json"), flush=True)
    return 0 if report["captured_source_files_unchanged"] \
        and report["copied_tree_restored"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
