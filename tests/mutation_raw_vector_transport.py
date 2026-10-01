#!/usr/bin/env python3
"""Scheduled, isolated mutation controls for the raw-vector observation path.

Only this script's retained checkout is mutated. Each selected case requires
an unchanged green control, an assertion-only mutant failure, and a green
byte-identical restoration. Errors, skips, and incomplete runs are not kills.
The extra unittest cases below isolate guards that broader refusal fixtures
cannot distinguish because another guard also refuses the same input.

This does not execute the compiled adapter or an embedding service. It does
not establish live-index integrity, namespace containment, model identity,
build reproducibility, exhaustive security, or a cognitive benchmark win.
"""

import argparse
import contextlib
import difflib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from tests import test_raw_vector_runner as runner_tests
from tests import test_raw_vector_snapshot as snapshot_tests
from tests import test_raw_vector_transport as transport_tests
from tests.mutation_familiarity import (
    Mutation, _green, _hashes, _mutated, _run, _sha, _write_json,
)


class TransportBoundary(unittest.TestCase):
    setUp = transport_tests.RawVectorTransport.setUp
    _invoke = transport_tests.RawVectorTransport._invoke

    def test_parent_path_replacement_refuses_after_execution(self):
        def replace_parent(command, **kwargs):
            self.database.rename(self.root / "retained-parent")
            self.database.mkdir(mode=0o700)
            (self.database / "index").mkdir(mode=0o700)
            return subprocess.CompletedProcess(command, 0, '{"ok":true}\n', '')

        with mock.patch.object(self.vector.sialib, "_run_bounded_text_process",
                               side_effect=replace_parent), \
                self.assertRaisesRegex(self.vector.VectorRefusal, "changed"):
            self._invoke()

    def test_nonprivate_parent_refuses_before_execution(self):
        self.database.chmod(0o755)
        with mock.patch.object(
                self.vector.sialib, "_run_bounded_text_process",
                return_value=subprocess.CompletedProcess([], 0, '{"ok":true}\n', '')) as run, \
                self.assertRaises(self.vector.VectorRefusal):
            self._invoke()
        run.assert_not_called()


class SnapshotBoundary(unittest.TestCase):
    setUp = snapshot_tests.RawVectorSnapshot.setUp
    _archive = snapshot_tests.RawVectorSnapshot._archive
    _snapshot = snapshot_tests.RawVectorSnapshot._snapshot

    def test_duplicate_directory_members_cannot_collapse_to_one_path(self):
        digest = self._archive([
            ("base", tarfile.DIRTYPE, ""),
            ("base", tarfile.DIRTYPE, ""),
            ("base/index", tarfile.REGTYPE, b"physical index"),
        ])
        with self.assertRaises(self.vector.VectorRefusal):
            with self._snapshot(digest):
                self.fail("duplicate directory declarations were admitted")
        self.assertEqual(list(self.root.iterdir()), [self.archive])

    def test_special_members_cannot_be_silently_skipped(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE):
            with self.subTest(kind=kind):
                digest = self._archive([
                    ("PG_VERSION", tarfile.REGTYPE, b"17\n"),
                    ("special", kind, "PG_VERSION"),
                ])
                with self.assertRaises(self.vector.VectorRefusal):
                    with self._snapshot(digest):
                        self.fail("an unsupported physical member was skipped")
                self.assertEqual(list(self.root.iterdir()), [self.archive])


class RunnerBoundary(unittest.TestCase):
    setUp = runner_tests.RawVectorRunner.setUp
    _run = runner_tests.RawVectorRunner._run
    _private = runner_tests.RawVectorRunner._private

    def _observation(self, executable, executable_sha, request, directory, **kwargs):
        return {
            "payload": {"bindings": {
                "logical_sha256": _sha(b"logical"),
                "catalog_sha256": _sha(b"catalog"),
            }, "results": [], "non_claims": ["fixture adapter boundary"]},
            "executable_sha256": executable_sha,
            "request_sha256": _sha(request["operation"].encode()),
            "returncode": 0, "wall_elapsed_ns": 123,
            "stdout_sha256": _sha(b"stdout"),
            "launch_sha256": _sha(b"launch"), "launch_contract": {},
        }

    def test_capture_admission_refusal_stops_before_query(self):
        refusal = self.runner.siavector.VectorRefusal("capture protocol refused")
        with mock.patch.object(self.runner.siavector, "private_index_snapshot",
                               side_effect=self._private) as snapshots, \
                mock.patch.object(self.runner.siavector, "invoke_adapter",
                                  side_effect=self._observation) as invoke, \
                mock.patch.object(self.runner.siavectoradmit, "admit_response",
                                  side_effect=refusal) as admission, \
                self.assertRaisesRegex(self.runner.siavector.VectorRefusal,
                                       "capture protocol refused"):
            self._run()
        self.assertEqual(snapshots.call_count, 1)
        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(admission.call_count, 1)
        self.assertEqual(invoke.call_args.args[2]["operation"], "capture")

    def test_distinct_physical_manifests_refuse_even_with_admitted_payloads(self):
        manifests = iter((_sha(b"first physical tree"), _sha(b"other physical tree")))

        @contextlib.contextmanager
        def private(*args, **kwargs):
            with self._private(*args, **kwargs) as snapshot:
                yield {**snapshot, "manifest_sha256": next(manifests)}

        with mock.patch.object(self.runner.siavector, "private_index_snapshot",
                               side_effect=private) as snapshots, \
                mock.patch.object(self.runner.siavector, "invoke_adapter",
                                  side_effect=self._observation), \
                mock.patch.object(self.runner.siavectoradmit, "admit_response",
                                  side_effect=lambda payload, *args, **kwargs: payload), \
                self.assertRaisesRegex(self.runner.siavector.VectorRefusal,
                                       "physical snapshot copies disagree"):
            self._run()
        self.assertEqual(snapshots.call_count, 2)


TRANSPORT = "tests.test_raw_vector_transport.RawVectorTransport."
SNAPSHOT = "tests.test_raw_vector_snapshot.RawVectorSnapshot."
RUNNER = "tests.test_raw_vector_runner.RawVectorRunner."
EXTRA = "tests.mutation_raw_vector_transport."
MUTATIONS = (
    Mutation(
        "source-write-seal-omitted", "bin/siavector.py",
        "_SEALS = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW\n",
        "_SEALS = (fcntl.F_SEAL_GROW\n",
        TRANSPORT + "test_source_bytes_are_sealed_and_path_replacement_is_detected"),
    Mutation(
        "request-not-sealed", "bin/siavector.py",
        "        _seal(descriptor)\n", "",
        TRANSPORT + "test_launch_uses_only_sealed_authority_and_allowlisted_environment",
        "_sealed_request"),
    Mutation(
        "source-digest-not-compared", "bin/siavector.py",
        "        if size != info.st_size or digest.hexdigest() != expected_sha256:\n",
        "        if size != info.st_size:\n",
        TRANSPORT + "test_digest_budget_type_and_link_guards_precede_launch",
        "sealed_file"),
    Mutation(
        "archive-digest-not-compared", "bin/siavector.py",
        "        if size != info.st_size or digest.hexdigest() != expected_sha256:\n",
        "        if size != info.st_size:\n",
        SNAPSHOT + "test_wrong_digest_refuses_before_any_database_copy",
        "sealed_file"),
    Mutation(
        "multiply-linked-source-admitted", "bin/siavector.py",
        "        if info.st_uid != os.geteuid() or info.st_nlink != 1 \\\n",
        "        if info.st_uid != os.geteuid() \\\n",
        TRANSPORT + "test_digest_budget_type_and_link_guards_precede_launch",
        "sealed_file"),
    Mutation(
        "source-symlink-canonicalized-before-admission", "bin/siavector.py",
        "        original, generation = sialib._open_chain_generation(\n",
        "        path = os.path.realpath(path)\n"
        "        original, generation = sialib._open_chain_generation(\n",
        TRANSPORT + "test_digest_budget_type_and_link_guards_precede_launch",
        "sealed_file"),
    Mutation(
        "executable-generation-change-ignored", "bin/siavector.py",
        "        if not sialib._chain_generation_matches(self.source):\n"
        '            raise VectorRefusal("vector source generation changed")\n',
        "",
        TRANSPORT + "test_post_execution_generation_change_refuses_complete_output"),
    Mutation(
        "archive-generation-replacement-ignored", "bin/siavector.py",
        "        if not sialib._chain_generation_matches(self.source):\n"
        '            raise VectorRefusal("vector source generation changed")\n',
        "",
        SNAPSHOT + "test_archive_path_replacement_invalidates_completed_private_use"),
    Mutation(
        "physical-file-bytes-not-preserved", "bin/siavector.py",
        "                                    output.write(block)\n",
        '                                    output.write(b"\\x00" * len(block))\n',
        SNAPSHOT + "test_private_copy_retains_physical_bytes_without_mutating_archive",
        "private_index_snapshot"),
    Mutation(
        "archive-parent-components-accepted", "bin/siavector.py",
        '                                or any(part in ("", ".", "..") for part in parts) \\\n',
        '                                or any(part in ("", ".") for part in parts) \\\n',
        SNAPSHOT + "test_links_escapes_aliases_and_duplicate_members_refuse",
        "private_index_snapshot"),
    Mutation(
        "archive-duplicate-directories-collapse", "bin/siavector.py",
        '                                or "\\x00" in name or name in seen \\\n',
        '                                or "\\x00" in name \\\n',
        EXTRA + "SnapshotBoundary.test_duplicate_directory_members_cannot_collapse_to_one_path",
        "private_index_snapshot"),
    Mutation(
        "archive-special-members-silently-skipped", "bin/siavector.py",
        '                            raise VectorRefusal("vector archive contains an unsupported member")\n',
        "                            continue\n",
        EXTRA + "SnapshotBoundary.test_special_members_cannot_be_silently_skipped",
        "private_index_snapshot"),
    Mutation(
        "archive-engine-child-name-changed", "bin/siavector.py",
        '                directory = os.path.join(parent, "index")\n',
        '                directory = os.path.join(parent, "data")\n',
        SNAPSHOT + "test_engine_directory_is_an_ordinary_fixed_child_of_descriptor_parent",
        "private_index_snapshot"),
    Mutation(
        "nonprivate-snapshot-parent-admitted", "bin/siavector.py",
        "                or initial.st_uid != os.geteuid() or initial.st_mode & 0o077:\n",
        "                or initial.st_uid != os.geteuid():\n",
        EXTRA + "TransportBoundary.test_nonprivate_parent_refuses_before_execution",
        "invoke_adapter"),
    Mutation(
        "fixed-index-symlink-followed-before-launch", "bin/siavector.py",
        "        index_fd = os.open(\"index\", os.O_RDONLY | os.O_CLOEXEC\n"
        "                           | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=database_fd)\n",
        "        index_fd = os.open(\"index\", os.O_RDONLY | os.O_CLOEXEC\n"
        "                           | os.O_DIRECTORY, dir_fd=database_fd)\n",
        TRANSPORT + "test_fixed_index_child_cannot_be_a_symlink",
        "invoke_adapter"),
    Mutation(
        "fixed-index-postreplacement-ignored", "bin/siavector.py",
        "                    if _directory_identity(os.fstat(index_fd)) \\\n"
        "                            != _directory_identity(index_initial) \\\n"
        "                            or _directory_identity(os.fstat(index_rebound)) \\\n"
        "                            != _directory_identity(index_initial):\n"
        '                        raise VectorRefusal("vector fixed index child changed")\n',
        "                    pass\n",
        TRANSPORT + "test_fixed_index_child_generation_is_rechecked_after_execution",
        "invoke_adapter"),
    Mutation(
        "snapshot-parent-postreplacement-ignored", "bin/siavector.py",
        "                    if _directory_identity(os.fstat(database_fd)) \\\n"
        "                            != _directory_identity(initial) \\\n"
        "                            or _directory_identity(os.fstat(rebound)) \\\n"
        "                            != _directory_identity(initial):\n"
        '                        raise VectorRefusal("vector snapshot directory changed")\n',
        "                    pass\n",
        EXTRA + "TransportBoundary.test_parent_path_replacement_refuses_after_execution",
        "invoke_adapter"),
    Mutation(
        "ambient-environment-inherited", "bin/siavector.py",
        '                environment = {**_ENVIRONMENT, "HOME": launch,\n',
        '                environment = {**os.environ, **_ENVIRONMENT, "HOME": launch,\n',
        TRANSPORT + "test_launch_uses_only_sealed_authority_and_allowlisted_environment",
        "invoke_adapter"),
    Mutation(
        "extra-index-descriptor-inherited", "bin/siavector.py",
        "                    pass_fds=(code.fd, request_fd, database_fd),\n",
        "                    pass_fds=(code.fd, request_fd, database_fd, index_fd),\n",
        TRANSPORT + "test_launch_uses_only_sealed_authority_and_allowlisted_environment",
        "invoke_adapter"),
    Mutation(
        "engine-child-substituted-for-parent-role", "bin/siavector.py",
        '            bound_request["snapshot"]["fd"] = database_fd\n',
        '            bound_request["snapshot"]["fd"] = index_fd\n',
        TRANSPORT + "test_launch_uses_only_sealed_authority_and_allowlisted_environment",
        "invoke_adapter"),
    Mutation(
        "process-tree-isolation-not-requested", "bin/siavector.py",
        "                    isolate_process_tree=True)\n",
        "                    isolate_process_tree=False)\n",
        TRANSPORT + "test_launch_uses_only_sealed_authority_and_allowlisted_environment",
        "invoke_adapter"),
    Mutation(
        "transport-json-uses-last-key-wins", "bin/siavector.py",
        "                    payload = siaqueue.strict_json_loads(process.stdout)\n",
        "                    payload = json.loads(process.stdout)\n",
        TRANSPORT + "test_rejected_output_never_becomes_an_observation",
        "invoke_adapter"),
    Mutation(
        "transport-exit-payload-verdict-not-bound", "bin/siavector.py",
        '                if (process.returncode == 2) != (payload.get("status") == "refused"):\n'
        '                    raise VectorRefusal("vector adapter exit verdict disagrees with output")\n',
        "",
        TRANSPORT + "test_rejected_output_never_becomes_an_observation",
        "invoke_adapter"),
    Mutation(
        "caller-build-expectations-not-admitted", "bin/siavectorrun.py",
        "        _admit_build(receipt, expected)\n", "",
        RUNNER + "test_build_mismatches_refuse_before_snapshot_or_execution",
        "_observe"),
    Mutation(
        "query-request-validation-deferred-until-after-capture", "bin/siavectorrun.py",
        "    pending = siavectoradmit.admit_request({\n",
        "    pending = dict({\n",
        RUNNER + "test_bad_query_refuses_before_artifact_reads_or_capture",
        "_observe"),
    Mutation(
        "capture-roots-not-propagated-to-query", "bin/siavectorrun.py",
        '                    request["snapshot"][field] = observations[0]["payload"]["bindings"][field]\n',
        '                    request["snapshot"][field] = "0" * 64\n',
        RUNNER + "test_capture_then_query_are_separate_copies_of_one_physical_generation",
        "_observe"),
    Mutation(
        "controller-passes-engine-child-instead-of-parent", "bin/siavectorrun.py",
        '                        snapshot["descriptor_parent"], timeout=timeout,\n',
        '                        snapshot["directory"], timeout=timeout,\n',
        RUNNER + "test_capture_then_query_are_separate_copies_of_one_physical_generation",
        "_observe"),
    Mutation(
        "query-reuses-capture-snapshot-context", "bin/siavectorrun.py",
        "            with siavector.private_index_snapshot(\n"
        "                    index_archive, index_sha256,\n"
        "                    scratch_parent=scratch_parent) as snapshot:\n",
        "            with (siavector.private_index_snapshot(\n"
        "                    index_archive, index_sha256,\n"
        '                    scratch_parent=scratch_parent) if operation == "capture"\n'
        '                    else __import__("contextlib").nullcontext(snapshot)) as snapshot:\n',
        RUNNER + "test_capture_then_query_are_separate_copies_of_one_physical_generation",
        "_observe"),
    Mutation(
        "capture-admission-refusal-bypassed", "bin/siavectorrun.py",
        '                observation["payload"] = siavectoradmit.admit_response(\n'
        '                    observation["payload"], request,\n'
        '                    executable_sha256=expected["executable_sha256"],\n'
        '                    request_sha256=observation["request_sha256"],\n'
        "                    config_sha256=config_sha256)\n",
        '                observation["payload"] = observation["payload"]\n',
        EXTRA + "RunnerBoundary.test_capture_admission_refusal_stops_before_query",
        "_observe"),
    Mutation(
        "physical-copy-manifest-disagreement-ignored", "bin/siavectorrun.py",
        '                if observations and snapshot["manifest_sha256"] \\\n'
        '                        != observations[0]["physical_manifest_sha256"]:\n'
        '                    raise siavector.VectorRefusal("vector physical snapshot copies disagree")\n',
        "",
        EXTRA + "RunnerBoundary.test_distinct_physical_manifests_refuse_even_with_admitted_payloads",
        "_observe"),
)
SUPPORT = (
    "tests/sia_test_home.py", "tests/test_raw_vector_transport.py",
    "tests/test_raw_vector_snapshot.py", "tests/test_raw_vector_runner.py",
    "tests/mutation_familiarity.py", "tests/mutation_raw_vector_transport.py",
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
    run = Path(tempfile.mkdtemp(prefix="raw-vector-transport-mutations-", dir=parent))
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
        "schema": "sia-raw-vector-transport-mutation-snapshot-v1",
        "source": str(source), "files": hashes,
        "python": {"path": str(executable), "sha256": _sha(executable.read_bytes())},
        "node": {"path": str(node), "sha256": _sha(node.read_bytes())},
        "non_claims": [
            "Selected mutation cases only; not exhaustive correctness or security.",
            "Some identical guard mutations have distinct transport and archive controls.",
            "Captured checkout tests only; no live index or embedding provider was accessed.",
            "Mocked launches check transport requests, not real namespace containment.",
            "Build reproducibility, served model weights, and cognitive wins are not established.",
            "Interpreter libraries and operating system are not transitively bound.",
        ],
    }
    _write_json(run / "snapshot.json", snapshot)
    # Reject every stale/nonunique anchor before starting the first control.
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
        "schema": "sia-raw-vector-transport-mutation-report-v1",
        "outcome": "selected-mutation-cases-killed", "mutations": records,
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
