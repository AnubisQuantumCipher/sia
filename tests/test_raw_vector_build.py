"""Executable-construction contract, using an explicitly pinned compiler fixture.

These tests exercise admission and receipts; the real Bun build is a separate
integration gate and cannot be inferred from a fixture compiler returning zero.
"""

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


REPO = Path(__file__).resolve().parents[1]
BUILDER = REPO / "scripts" / "build-raw-vector"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class RawVectorBuildContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sia-vector-build-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "gbrain"
        (self.source / "src" / "core").mkdir(parents=True)
        (self.source / "src" / "core" / "engine.ts").write_text(
            "export const source = 'pinned fixture';\n", encoding="utf-8")
        (self.source / "package.json").write_text(
            '{"name":"gbrain","type":"module"}\n', encoding="utf-8")
        (self.source / "bun.lock").write_text(
            '{"lockfileVersion":1}\n', encoding="utf-8")
        self._git("init", "-q")
        self._git("add", ".")
        self._git("-c", "user.name=Fixture", "-c",
                  "user.email=fixture@invalid", "-c", "commit.gpgsign=false",
                  "commit", "-qm", "Fixture source")
        self.commit = self._git("rev-parse", "HEAD").strip()
        self.pin = self.root / "GBRAIN_PIN"
        self._write_pin()
        self.adapter = self.root / "adapter.ts"
        self.adapter.write_text("export const adapter = 'fixture';\n",
                                encoding="utf-8")
        self.bun = self.root / "bun"
        self.bun_receipt = self.root / "bun-release"
        self.compiler_calls = self.root / "compiler-calls.jsonl"
        self.output = self.root / "built"
        self._write_compiler()

    def _git(self, *arguments):
        return subprocess.run(
            ["git", "-C", str(self.source), *arguments],
            check=True, capture_output=True, text=True).stdout

    def _write_pin(self, *, commit=None, lock=None):
        self.pin.write_text(
            "commit=" + (commit or self.commit) + "\nversion=0.47.6.0\n"
            "bun_lock_sha256=" + (lock or _sha(self.source / "bun.lock"))
            + "\nverified=2026-08-30\n", encoding="utf-8")

    def _write_compiler(self, mode="normal"):
        program = textwrap.dedent("""\
            import json
            import os
            from pathlib import Path
            import signal
            import sys
            import time
            calls = Path(CALLS_PATH)
            with calls.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'argv': sys.argv[1:],
                                         'cwd': os.getcwd(),
                                         'env': dict(os.environ)}) + '\\n')
            if sys.argv[1:] == ['--version']:
                print('1.4.0')
            elif sys.argv[1] == 'install':
                args = sys.argv[2:]
                source = Path(args[args.index('--cwd') + 1])
                dependency = source / 'node_modules' / 'fixture' / 'index.js'
                dependency.parent.mkdir(parents=True)
                dependency.write_text('export const dependency = true;\\n')
                if BUILD_MODE == 'backend-contract' and '--backend=copyfile' not in args:
                    cache_alias = Path(os.environ['BUN_INSTALL_CACHE_DIR']) / 'fixture-index.js'
                    os.link(dependency, cache_alias)
                if BUILD_MODE == 'source-mutation':
                    (source / 'src' / 'core' / 'engine.ts').write_text('changed')
            elif sys.argv[1] == 'build':
                args = sys.argv[2:]
                output = Path(args[args.index('--outfile') + 1])
                source = Path(args[-1]).parent.parent
                if BUILD_MODE in {'build-failure', 'build-killed'}:
                    print('fixture compiler progress', flush=True)
                    print('fixture compiler diagnostic', file=sys.stderr, flush=True)
                    if BUILD_MODE == 'build-killed':
                        deadline = time.monotonic() + 2
                        while time.monotonic() < deadline:
                            logs = output.parent / 'command-logs'
                            if any(b'fixture compiler diagnostic' in path.read_bytes()
                                   for path in logs.glob('*.stderr')):
                                os.kill(os.getppid(), signal.SIGKILL)
                                raise SystemExit(0)
                            time.sleep(0.01)
                    raise SystemExit(7)
                if BUILD_MODE == 'dependency-mutation':
                    (source / 'node_modules' / 'fixture' / 'index.js').write_text(
                        'different bytes after compiler entry')
                if BUILD_MODE == 'output-symlink':
                    output.symlink_to(source / 'package.json')
                else:
                    output.write_bytes(b'\\x7fELFfixture-compiled-output')
                    output.chmod(0o700)
            else:
                raise SystemExit('unexpected compiler command')
            """)
        program = program.replace("CALLS_PATH", repr(str(self.compiler_calls)))
        program = program.replace("BUILD_MODE", repr(mode))
        self.bun.write_text("#!" + sys.executable + "\n" + program,
                            encoding="utf-8")
        self.bun.chmod(0o700)
        self.bun_receipt.write_text(
            "managed-by=khephri.sia\nversion=1.4.0\n"
            "asset=bun-linux-aarch64.zip\nsha256=" + "a" * 64 + "\n"
            "binary_sha256=" + _sha(self.bun) + "\n", encoding="utf-8")

    def _run(self, *extra, env=None):
        environment = dict(os.environ)
        environment.update(env or {})
        return subprocess.run([
            sys.executable, str(BUILDER),
            "--gbrain-source", str(self.source), "--pin", str(self.pin),
            "--adapter", str(self.adapter), "--bun", str(self.bun),
            "--bun-sha256", _sha(self.bun), "--bun-version", "1.4.0",
            "--bun-receipt", str(self.bun_receipt),
            "--output-dir", str(self.output), *extra,
        ], capture_output=True, text=True, env=environment, timeout=30)

    def _assert_refused(self, result, reason):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(reason, result.stderr)
        self.assertFalse((self.output / "build-receipt.json").exists())

    def test_receipt_binds_exact_source_compiler_adapter_closure_and_output(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads((self.output / "build-receipt.json").read_text())
        self.assertEqual(receipt["schema"], "sia-raw-vector-build-v1")
        self.assertEqual(receipt["gbrain"]["commit"], self.commit)
        self.assertEqual(receipt["gbrain"]["pin_sha256"], _sha(self.pin))
        self.assertEqual(receipt["gbrain"]["bun_lock_sha256"],
                         _sha(self.source / "bun.lock"))
        self.assertEqual(receipt["adapter"]["sha256"], _sha(self.adapter))
        self.assertEqual(receipt["bun"]["binary_sha256"], _sha(self.bun))
        self.assertEqual(receipt["bun"]["receipt_sha256"],
                         _sha(self.bun_receipt))
        self.assertEqual(receipt["output"]["sha256"],
                         _sha(self.output / "sia-raw-vector"))
        self.assertEqual(receipt["output"]["path"], "sia-raw-vector")
        self.assertEqual(receipt["adapter"]["staged_path"],
                         "src/sia-raw-vector.ts")
        closure = json.loads((self.output / "dependency-closure.json").read_text())
        self.assertEqual(receipt["dependencies"]["manifest_sha256"],
                         _sha(self.output / "dependency-closure.json"))
        self.assertTrue(any(row["path"] == "fixture/index.js"
                            for row in closure["entries"]))
        self.assertEqual(receipt["source"]["manifest_sha256"],
                         _sha(self.output / "source-closure.json"))
        self.assertIn("machine", receipt["platform"])
        self.assertIn("system", receipt["platform"])
        self.assertTrue(receipt["commands"])
        self.assertIn("Build observation is not a reproducible-build proof.",
                      receipt["non_claims"])
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        self.assertFalse((self.source / "node_modules").exists())
        self.assertEqual(self._git("status", "--porcelain"), "")

    def test_wrong_commit_is_refused_before_compiler_execution(self):
        self._write_pin(commit="0" * 40)
        self._assert_refused(self._run(), "source-commit-mismatch")
        self.assertFalse(self.compiler_calls.exists())

    def test_receipt_binds_builder_recipe_and_enforced_limits(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads((self.output / "build-receipt.json").read_text())
        self.assertEqual(receipt["builder"]["sha256"], _sha(BUILDER))
        self.assertEqual(receipt["builder"]["bytes"], BUILDER.stat().st_size)
        self.assertEqual(receipt["limits"], {
            "metadata_bytes": 1_048_576,
            "source_archive_bytes": 536_870_912,
            "closure_bytes": 2_147_483_648,
            "closure_entries": 100_000,
            "command_output_bytes": 8_388_608,
            "command_timeout_seconds": 1800,
        })

    def test_uncommitted_source_cannot_be_claimed_as_pinned(self):
        (self.source / "src" / "core" / "engine.ts").write_text("local edit")
        self._assert_refused(self._run(), "source-worktree-dirty")
        self.assertFalse(self.compiler_calls.exists())

    def test_lock_must_match_operator_pin(self):
        self._write_pin(lock="0" * 64)
        self._assert_refused(self._run(), "source-lock-mismatch")
        self.assertFalse(self.compiler_calls.exists())

    def test_bun_byte_expectation_is_checked_before_execution(self):
        result = self._run("--bun-sha256", "0" * 64)
        self._assert_refused(result, "bun-digest-mismatch")
        self.assertFalse(self.compiler_calls.exists())

    def test_symlink_adapter_is_not_an_admitted_source(self):
        linked = self.root / "linked-adapter.ts"
        linked.symlink_to(self.adapter)
        self._assert_refused(self._run("--adapter", str(linked)),
                             "adapter-unsafe-file")

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        sentinel = self.output / "operator-file"
        sentinel.write_text("retain these bytes", encoding="utf-8")
        self._assert_refused(self._run(), "output-already-exists")
        self.assertEqual(sentinel.read_text(), "retain these bytes")
        self.assertFalse(self.compiler_calls.exists())

    def test_build_uses_private_home_cache_and_closed_install_flags(self):
        result = self._run(env={
            "BUN_INSTALL_CACHE_DIR": "/must-not-use-caller-cache",
            "BUN_OPTIONS": "--preload=/must-not-load.ts",
            "NODE_OPTIONS": "--require=/must-not-load.js",
            "npm_config_registry": "https://must-not-use.invalid",
            "SIA_BUILD_TEST_SECRET": "must-not-inherit",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.compiler_calls.read_text().splitlines()]
        for call in calls:
            self.assertNotIn("BUN_OPTIONS", call["env"])
            self.assertNotIn("NODE_OPTIONS", call["env"])
            self.assertNotIn("npm_config_registry", call["env"])
            self.assertNotIn("SIA_BUILD_TEST_SECRET", call["env"])
            self.assertTrue(Path(call["env"]["HOME"]).is_relative_to(self.output))
        install = next(call for call in calls if call["argv"][0] == "install")
        for argument in ("--frozen-lockfile", "--production", "--ignore-scripts"):
            self.assertIn(argument, install["argv"])
        self.assertTrue(Path(install["env"]["BUN_INSTALL_CACHE_DIR"])
                        .is_relative_to(self.output))
        build = next(call for call in calls if call["argv"][0] == "build")
        self.assertIn("--compile", build["argv"])
        self.assertEqual(Path(build["argv"][-1]).name, "sia-raw-vector.ts")

    def test_dependency_mutation_during_compilation_invalidates_receipt(self):
        self._write_compiler("dependency-mutation")
        self._assert_refused(self._run(), "dependency-closure-changed")

    def test_supported_copyfile_backend_keeps_dependency_leaves_single_link(self):
        self._write_compiler("backend-contract")
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.compiler_calls.read_text().splitlines()]
        install = next(call for call in calls if call["argv"][0] == "install")
        self.assertIn("--backend=copyfile", install["argv"])
        staged_source = Path(install["argv"][install["argv"].index("--cwd") + 1])
        dependency = staged_source / "node_modules" / "fixture" / "index.js"
        self.assertEqual(dependency.stat().st_nlink, 1)
        receipt = json.loads((self.output / "build-receipt.json").read_text())
        self.assertEqual(receipt["dependencies"]["manifest_sha256"],
                         _sha(self.output / "dependency-closure.json"))

    def test_command_failure_keeps_durable_output_and_refusal_record(self):
        self._write_compiler("build-failure")
        result = self._run()
        self._assert_refused(result, "command-failed")
        failure = json.loads((self.output / "build-failure.json").read_text())
        self.assertEqual(failure["schema"], "sia-raw-vector-build-failure-v1")
        self.assertIn("command-failed", failure["reason"])
        command = failure["commands"][-1]
        self.assertEqual(command["returncode"], 7)
        stderr = self.output / command["stderr_path"]
        stdout = self.output / command["stdout_path"]
        self.assertIn("fixture compiler diagnostic", stderr.read_text())
        self.assertIn("fixture compiler progress", stdout.read_text())
        self.assertEqual(command["stderr_sha256"], _sha(stderr))
        self.assertEqual(command["stdout_sha256"], _sha(stdout))

    def test_noncommand_refusal_keeps_diagnostics_after_successful_install(self):
        self._write_compiler("source-mutation")
        result = self._run()
        self._assert_refused(result, "source-closure-changed")
        failure = json.loads((self.output / "build-failure.json").read_text())
        self.assertEqual(failure["reason"], "source-closure-changed")
        self.assertEqual(failure["commands"][-1]["returncode"], 0)
        self.assertIn("install", failure["commands"][-1]["argv"])

    def test_command_output_is_durable_before_builder_is_killed(self):
        self._write_compiler("build-killed")
        result = self._run()
        self.assertEqual(result.returncode, -9, result.stderr)
        self.assertFalse((self.output / "build-receipt.json").exists())
        stderr_logs = list((self.output / "command-logs").glob("*.stderr"))
        self.assertTrue(any(b"fixture compiler diagnostic" in path.read_bytes()
                            for path in stderr_logs))
        events = [json.loads(line) for line in
                  (self.output / "build-commands.jsonl").read_text().splitlines()]
        self.assertEqual(events[-1]["event"], "started")
        self.assertIn("build", events[-1]["command"]["argv"])

    def test_install_cannot_rewrite_pinned_source(self):
        self._write_compiler("source-mutation")
        self._assert_refused(self._run(), "source-closure-changed")

    def test_compiler_output_must_be_a_regular_executable(self):
        self._write_compiler("output-symlink")
        self._assert_refused(self._run(), "output-unsafe-file")


if __name__ == "__main__":
    unittest.main()
