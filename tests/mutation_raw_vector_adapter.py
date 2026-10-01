#!/usr/bin/env python3
"""Run scheduled sequential Bun contract mutations on retained private copies.

Every selected mutant requires its named test green before mutation, a JUnit
expect-assertion failure (not an import/parser/runtime error), and the same test
green after exact byte restoration. No compiled adapter, database, embedding
provider, resident SIA state, or dependency installation is used here.
"""

import argparse
from dataclasses import dataclass
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
import tempfile
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parent.parent
# Existing protocol byte ceiling, also used to bound each diagnostic artifact.
MAX_ARTIFACT_BYTES = 2097152
TIMEOUT_SECONDS = 60
ADAPTER = "raw-vector/adapter.ts"
PREPARER = "raw-vector/prepare-index.ts"


@dataclass(frozen=True)
class Mutation:
    name: str
    path: str
    before: str
    after: str
    suite: str
    test: str
    check_kind: str = "injected-core-behavior"

    @property
    def test_path(self):
        return self.path.removesuffix(".ts") + ".test.ts"


QUERY = "query-only raw-vector request admission"
EXECUTION = "raw-vector execution contract"
META = "snapshot embedding compatibility"
PREP = "lossless benchmark index preparation"
DIAGNOSTICS = "bounded initSchema diagnostic receipt"
READBACK = "rejects content, origin, chunk omission and embedding mutations found during readback"
MUTATIONS = (
    Mutation("gateway-byte-ceiling-bypassed", ADAPTER,
             "export const MAX_QUERY_BYTES = 8000;", "export const MAX_QUERY_BYTES = MAX_REQUEST_BYTES;",
             QUERY, "never admits a query beyond the pinned gateway ceiling and counts Unicode bytes exactly"),
    Mutation("fixed-child-symlink-followed", ADAPTER,
             "import { fstatSync, lstatSync, readSync, readlinkSync, writeSync } from 'node:fs';",
             "import { fstatSync, statSync as lstatSync, readSync, readlinkSync, writeSync } from 'node:fs';",
             QUERY, "opens only the fixed ordinary index child of an owned private descriptor parent"),
    Mutation("snapshot-before-identity-ignored", ADAPTER,
             "    if (request.operation === 'query' && (before.logical_sha256 !== request.snapshot.logical_sha256\n"
             "      || before.catalog_sha256 !== request.snapshot.catalog_sha256)) refuse('snapshot-identity-mismatch');\n",
             "", EXECUTION, "does not embed or search an unbound generation and always closes the engine"),
    Mutation("snapshot-after-identity-ignored", ADAPTER,
             "    if (canonicalJson(before) !== canonicalJson(after)) refuse('snapshot-changed-during-query');\n",
             "", EXECUTION, "refuses post-search mutation and never returns ranked rows with the refusal"),
    Mutation("raw-search-source-boosts-enabled", ADAPTER,
             "sourceId: 'sia', detail: 'high',", "sourceId: 'sia', detail: 'low',",
             EXECUTION, "binds the snapshot before embedding and after search, retaining only normalized raw rows"),
    Mutation("raw-search-exclusions-removed", ADAPTER,
             "exclude_slug_prefixes: [...EXCLUDES], include_slug_prefixes: [], excludePrivate: false,",
             "exclude_slug_prefixes: [], include_slug_prefixes: [], excludePrivate: false,",
             EXECUTION, "binds the snapshot before embedding and after search, retaining only normalized raw rows"),
    Mutation("ranked-row-hash-binds-other-bytes", ADAPTER,
             "ranked_rows_sha256: sha(rowBytes),", "ranked_rows_sha256: sha(vectorBytes),",
             EXECUTION, "publishes the exact row bytes whose digest is claimed across language serializers"),
    Mutation("configured-model-sql-predicate-removed", ADAPTER,
             "bool_and(value=$1),false)", "bool_and(true),false)", META,
             "queries each compatibility condition without projecting stored labels or text", "sql-source-contract"),
    Mutation("configured-dimension-sql-predicate-removed", ADAPTER,
             "bool_and(value=$2),false)", "bool_and(true),false)", META,
             "queries each compatibility condition without projecting stored labels or text", "sql-source-contract"),
    Mutation("physical-column-sql-predicate-removed", ADAPTER,
             "bool_and(format_type(a.atttypid,a.atttypmod)=$3),false)", "bool_and(true),false)", META,
             "queries each compatibility condition without projecting stored labels or text", "sql-source-contract"),
    Mutation("chunk-model-sql-predicate-weakened", ADAPTER,
             "cc.model IS DISTINCT FROM $1) AS chunk_models_match",
             "cc.model <> $1) AS chunk_models_match", META,
             "queries each compatibility condition without projecting stored labels or text", "sql-source-contract"),
    Mutation("embedded-text-sql-hash-predicate-removed", ADAPTER,
             "cc.embedded_text_hash IS NULL OR cc.embedded_text_hash <> md5(cc.chunk_text)",
             "cc.embedded_text_hash IS NULL", META,
             "queries each compatibility condition without projecting stored labels or text", "sql-source-contract"),
    Mutation("lossless-chunks-trimmed", PREPARER,
             "  return parts;", "  return parts.map(part => part.trim());", PREP,
             "deterministically splits all UTF-8 text without dropping whitespace or cutting codepoints"),
    Mutation("page-text-readback-ignored", PREPARER,
             "stored.compiled_truth !== page.text || stored.timeline !== ''", "stored.timeline !== ''",
             PREP, READBACK),
    Mutation("page-origin-readback-ignored", PREPARER,
             " || stored.frontmatter?.origin !== page.origin", "", PREP, READBACK),
    Mutation("chunk-roster-readback-ignored", PREPARER,
             " || chunks.length !== expected.length", "", PREP, READBACK),
    Mutation("vector-readback-hash-ignored", PREPARER,
             "        if (digest !== pages[index].chunks[chunkIndex].vector_sha256) refuse('index-readback-mismatch');\n",
             "", PREP, READBACK),
    Mutation("source-page-roster-readback-ignored", PREPARER,
             "    if (canonicalJson((await engine.listSlugs()).sort()) !== canonicalJson(request.pages.map(p => p.slug).sort()))\n"
             "      refuse('index-readback-mismatch');\n", "", PREP, READBACK),
    Mutation("unknown-diagnostics-relabelled-known", PREPARER,
             "      classification = 'unrecognized-setup-diagnostics';",
             "      classification = 'known-setup-diagnostics';", DIAGNOSTICS,
             "unknown/error output refuses with its original bytes and cannot become known setup progress"),
    Mutation("diagnostic-prefix-retention-ceiling-removed", PREPARER,
             "const remaining = MAX_SETUP_DIAGNOSTIC_BYTES - retainedBytes;",
             "const remaining = Number.MAX_SAFE_INTEGER - retainedBytes;", DIAGNOSTICS,
             "excess diagnostics refuse with an explicitly bounded prefix and restore the writer"),
    Mutation("diagnostic-overflow-classification-removed", PREPARER,
             "const truncated = seen > MAX_SETUP_DIAGNOSTIC_BYTES;", "const truncated = false;", DIAGNOSTICS,
             "excess diagnostics refuse with an explicitly bounded prefix and restore the writer"),
    Mutation("diagnostic-writer-not-restored", PREPARER,
             "finally { stream.write = original; }", "finally { void original; }", DIAGNOSTICS,
             "retains known setup diagnostics verbatim with a digest and restores the original writer"),
    Mutation("diagnostic-failed-init-writer-not-restored", PREPARER,
             "finally { stream.write = original; }", "finally { void original; }", DIAGNOSTICS,
             "restores stderr after initSchema throws, preserving diagnostics without returning success"),
)
FILES = (ADAPTER, PREPARER, "raw-vector/adapter.test.ts", "raw-vector/prepare-index.test.ts",
         "tests/mutation_raw_vector_adapter.py")
NON_CLAIMS = [
    "Only the listed mutations and selected tests are distinguished; this is not exhaustive correctness or security.",
    "SQL-predicate mutations exercise declared source contracts, not a live database's SQL semantics.",
    "Raw-search options execute through the injected engine seam; compiled provider routing is not independently established here.",
    "No resident database, embedding service, compiled artifact, model weights, or cognitive benchmark improvement is attested.",
    "The Bun executable and copied source bytes are bound; operating-system and interpreter-library closure is not transitively attested.",
]


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False,
                               allow_nan=False, separators=(",", ":")) + "\n")


def _hashes(root):
    result = {}
    for name in FILES:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("source is no longer an ordinary file: " + name)
        result[name] = _file_sha(path)
    return result


def _exact_roster(root):
    return sorted(str(path.relative_to(root)) for path in root.rglob("*")
                  if path.is_file() or path.is_symlink()) == sorted(FILES)


def _junit(path, spec):
    raw = path.read_bytes()
    if len(raw) > MAX_ARTIFACT_BYTES or b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise RuntimeError("JUnit report is outside its closed XML boundary")
    document = ET.fromstring(raw)
    cases = list(document.iter("testcase"))
    selected_names = {spec.test, spec.suite + " > " + spec.test}
    selected = [case for case in cases if case.get("name") in selected_names]
    if len(selected) != 1:
        raise RuntimeError("JUnit did not record exactly the selected test")
    case = selected[0]
    if case.get("classname") != spec.suite or case.get("file") != spec.test_path:
        raise RuntimeError("JUnit selected source/suite identity differs")
    if list(document.iter("error")) or list(case.iter("skipped")):
        raise RuntimeError("JUnit errors or selected skips are not mutation evidence")
    if re.fullmatch(r"[1-9][0-9]*", case.get("assertions", "")) is None:
        raise RuntimeError("JUnit selected case recorded no assertions")
    for other in cases:
        if other is case:
            continue
        # Pinned Bun reports filtered-out cases as skips. They may have no
        # execution/failure evidence, and never substitute for the selection.
        children = list(other)
        if other.get("assertions") != "0" or len(children) != 1 \
                or children[0].tag != "skipped" or list(children[0]) \
                or children[0].attrib or (children[0].text or "").strip():
            raise RuntimeError("JUnit contains an extra executed or ambiguous case")
    failures = list(case.iter("failure"))
    if len(list(document.iter("failure"))) != len(failures) or len(failures) > 1:
        raise RuntimeError("JUnit failure roster is ambiguous")
    details = [{"attributes": dict(item.attrib), "text": "".join(item.itertext())} for item in failures]
    return {"test": dict(case.attrib), "failures": details,
            "sha256": _sha(raw), "assertion_failure": bool(details) and _assertion(details[0])}


def _assertion(failure):
    text = failure["text"] + "\n" + failure["attributes"].get("message", "")
    # Bun's test runner can put runtime exceptions in <failure> as well.
    # An actual expect assertion is mandatory; unrelated failures never kill.
    forbidden = ("Cannot find module", "ModuleNotFound", "SyntaxError", "ReferenceError",
                 "TypeError", "Unhandled", "Failed to resolve", "error: Expected")
    if any(marker in text for marker in forbidden):
        return False
    return re.search(r"(?:error:\s*)?expect\([^\n]*\)\.[A-Za-z]", text) is not None


def _run(repo, case, phase, spec, executable, expected_sha):
    if _file_sha(executable) != expected_sha:
        raise RuntimeError("Bun executable changed before launch")
    junit = case / (phase + ".junit.xml")
    command = [str(executable), "test", spec.test_path, "--test-name-pattern",
               re.escape(spec.test) + "$", "--max-concurrency=1", "--no-orphans",
               "--reporter=junit", "--reporter-outfile=" + str(junit)]
    scratch = case / (phase + "-tmp")
    scratch.mkdir(mode=0o700)
    environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                   "TZ": "UTC", "NO_COLOR": "1", "TMPDIR": str(scratch),
                   "XDG_CONFIG_HOME": str(scratch), "BUN_INSTALL": str(scratch)}

    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_ARTIFACT_BYTES, MAX_ARTIFACT_BYTES))

    stdout_path, stderr_path = case / (phase + ".stdout"), case / (phase + ".stderr")
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(command, cwd=repo, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, close_fds=True,
                                   start_new_session=True, preexec_fn=limits)
        try:
            returncode = process.wait(timeout=TIMEOUT_SECONDS)
        except BaseException:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise
    if _file_sha(executable) != expected_sha:
        raise RuntimeError("Bun executable changed during launch")
    if any(path.stat().st_size > MAX_ARTIFACT_BYTES for path in (stdout_path, stderr_path)):
        raise RuntimeError("test diagnostics exceeded their byte ceiling")
    observation = {"command": command, "environment": environment, "returncode": returncode,
                   "stdout_sha256": _file_sha(stdout_path), "stderr_sha256": _file_sha(stderr_path),
                   "junit": _junit(junit, spec)}
    _json(case / (phase + ".json"), observation)
    return observation


def _green(observation):
    return observation["returncode"] == 0 and not observation["junit"]["failures"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=REPO)
    parser.add_argument("--output-parent", required=True, type=Path)
    parser.add_argument("--bun", required=True, type=Path)
    parser.add_argument("--bun-sha256", required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    parent = args.output_parent.resolve(strict=True)
    executable = args.bun.resolve(strict=True)
    if not source.is_dir() or not parent.is_dir() or not executable.is_file() \
            or re.fullmatch(r"[a-f0-9]{64}", args.bun_sha256) is None \
            or _file_sha(executable) != args.bun_sha256:
        parser.error("ordinary source/output directories and independently pinned Bun are required")
    run = Path(tempfile.mkdtemp(prefix="raw-vector-adapter-mutations-", dir=parent))
    repo = run / "checkout"
    repo.mkdir(mode=0o700)
    print(str(run), flush=True)
    hashes = _hashes(source)
    for name in FILES:
        original, target = source / name, repo / name
        data = original.read_bytes()
        if _sha(data) != hashes[name]:
            raise RuntimeError("source changed during capture")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(stat.S_IMODE(original.stat().st_mode))
    if _hashes(source) != hashes or _hashes(repo) != hashes or not _exact_roster(repo):
        raise RuntimeError("source capture is not a complete coherent byte copy")
    snapshot = {"schema": "sia-raw-vector-adapter-mutation-snapshot-v1", "source": str(source),
                "files": hashes, "bun": {"path": str(executable), "sha256": args.bun_sha256},
                "non_claims": NON_CLAIMS}
    _json(run / "snapshot.json", snapshot)
    changed_sources = {}
    for spec in MUTATIONS:
        original = (repo / spec.path).read_text()
        if original.count(spec.before) != 1 or spec.before == spec.after:
            raise RuntimeError("mutation anchor is not unique: " + spec.name)
        changed_sources[spec.name] = original.replace(spec.before, spec.after).encode("utf-8")
    records = []
    for spec in MUTATIONS:
        case = run / spec.name
        case.mkdir(mode=0o700)
        target = repo / spec.path
        original, changed = target.read_bytes(), changed_sources[spec.name]
        plan = {"name": spec.name, "path": spec.path, "suite": spec.suite, "test": spec.test,
                "check_kind": spec.check_kind, "before_sha256": _sha(original), "after_sha256": _sha(changed),
                "snapshot_sha256": _file_sha(run / "snapshot.json")}
        _json(case / "plan.json", plan)
        (case / "mutation.patch").write_text("".join(difflib.unified_diff(
            original.decode().splitlines(keepends=True), changed.decode().splitlines(keepends=True),
            fromfile="a/" + spec.path, tofile="b/" + spec.path)))
        if _hashes(repo) != hashes or not _exact_roster(repo):
            raise RuntimeError("captured source changed before control")
        control = _run(repo, case, "control", spec, executable, args.bun_sha256)
        if not _green(control) or _hashes(repo) != hashes or not _exact_roster(repo):
            raise RuntimeError("control is not unchanged and green: " + spec.name)
        try:
            target.write_bytes(changed)
            expected = {**hashes, spec.path: _sha(changed)}
            if _hashes(repo) != expected or not _exact_roster(repo):
                raise RuntimeError("unexpected source change before mutant")
            mutant = _run(repo, case, "mutant", spec, executable, args.bun_sha256)
            if _hashes(repo) != expected or not _exact_roster(repo):
                raise RuntimeError("mutant changed its copied source")
        finally:
            target.write_bytes(original)
        if _hashes(repo) != hashes or not _exact_roster(repo):
            raise RuntimeError("exact source restoration failed")
        restored = _run(repo, case, "restored", spec, executable, args.bun_sha256)
        killed = mutant["returncode"] == 1 and mutant["junit"]["assertion_failure"]
        record = {**plan, "killed": killed, "restored_green": _green(restored),
                  "restored_sha256": _file_sha(target)}
        _json(case / "verdict.json", record)
        records.append(record)
        print(spec.name + (": killed; exact restoration green" if killed and _green(restored) else ": FAILED"), flush=True)
        if not killed or not _green(restored) or _hashes(repo) != hashes or not _exact_roster(repo):
            raise RuntimeError("mutation contract failed: " + spec.name)
    artifacts = {}
    for path in sorted(run.rglob("*")):
        if path.is_symlink():
            raise RuntimeError("unexpected symlink in retained artifacts")
        if path.is_file() and repo not in path.parents:
            artifacts[str(path.relative_to(run))] = _file_sha(path)
    report = {"schema": "sia-raw-vector-adapter-mutation-report-v1", "outcome": "selected-mutants-killed",
              "mutations": records, "captured_source_files_unchanged": _hashes(source) == hashes,
              "copied_tree_restored": _hashes(repo) == hashes and _exact_roster(repo),
              "artifacts_sha256": artifacts, "non_claims": NON_CLAIMS}
    _json(run / "report.json", report)
    print("report: " + str(run / "report.json"), flush=True)
    return 0 if report["captured_source_files_unchanged"] and report["copied_tree_restored"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
