#!/usr/bin/env python3
"""RED contract for reproducibly overlaying SIA's pinned gbrain source.

These tests never run Bun, gbrain, SIA, or a network command.  Dynamic checks
use miniature Git repositories below a TemporaryDirectory and execute only the
small installer front doors that admit the pin and apply the raw source patch.

The intended installer boundary has three deliberately named pieces:

``gbrain_pin_frontdoor``
    Stable, no-follow parser for GBRAIN_PIN and the overlay artifact.  It emits
    one tab-separated row: commit, version, lock digest, overlay digest, and
    post-overlay Git tree OID.

``gbrain_overlay_frontdoor``
    Applies an already-digest-bound patch to a fresh detached checkout.  Its
    arguments are SOURCE, PATCH, COMMIT, BUN_LOCK_SHA256, OVERLAY_SHA256, and
    OVERLAY_TREE_OID.  It prints the admitted tree OID on success.

``GBRAIN_STERILE_ENV``
    A shell array beginning with ``/usr/bin/env -i``.  Dependency installation,
    compilation, and every candidate/installed version probe expand this array
    before the executable, so ambient machine configuration cannot reach them.
"""

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER_PATH = os.path.join(REPO, "install.sh")
PIN_PATH = os.path.join(REPO, "GBRAIN_PIN")
OVERLAY_NAME = "GBRAIN_OVERLAY.patch"
OVERLAY_PATH = os.path.join(REPO, OVERLAY_NAME)
GIT = "/usr/bin/git"


def _read(path):
    with open(path, encoding="utf-8") as stream:
        return stream.read()


def _write(path, content, mode=0o600):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(content)
    os.chmod(path, mode)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _installer():
    return _read(INSTALLER_PATH)


def _shell_array(script, name):
    match = re.search(
        rf"(?ms)^{re.escape(name)}=\(\n.*?^\)\n", script)
    if match is None:
        raise AssertionError(
            f"install.sh must declare one multiline {name}=(...) array")
    if len(re.findall(rf"(?m)^{re.escape(name)}=\(", script)) != 1:
        raise AssertionError(f"install.sh must declare {name} exactly once")
    return match.group(0)


def _embedded_python(script, function):
    marker = function + "() {\n  python3 - \"$@\" <<'PY'\n"
    if script.count(marker) != 1:
        raise AssertionError(
            f"install.sh must define exactly one self-contained {function}")
    tail = script.split(marker, 1)[1]
    if "\nPY\n}" not in tail:
        raise AssertionError(f"{function} has no closed Python heredoc")
    return tail.split("\nPY\n}", 1)[0]


def _run_python(program, arguments, environment=None):
    return subprocess.run(
        [sys.executable, "-I", "-c", program, *arguments],
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False)


def _git(repository, *arguments, input_text=None, check=True):
    environment = {
        "HOME": os.path.dirname(repository),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    result = subprocess.run(
        [GIT, "-C", repository, *arguments],
        input=input_text,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False)
    if check and result.returncode != 0:
        raise AssertionError(
            f"fixture git {' '.join(arguments)} failed: {result.stderr}")
    return result


def _make_overlay_fixture(root):
    upstream = os.path.join(root, "upstream")
    os.makedirs(os.path.join(upstream, "src"))
    _git(upstream, "init", "-q")
    _write(os.path.join(upstream, "bun.lock"), "locked dependency graph\n")
    _write(
        os.path.join(upstream, "package.json"),
        '{"name":"mini-gbrain","private":true}\n')
    _write(os.path.join(upstream, "src", "value.ts"), "export const value = 'before';\n")
    _git(upstream, "add", "bun.lock", "package.json", "src/value.ts")
    _git(
        upstream, "-c", "user.name=overlay-test",
        "-c", "user.email=overlay@test.invalid", "commit", "-qm", "base")
    commit = _git(upstream, "rev-parse", "HEAD").stdout.strip()
    lock_digest = _sha256(os.path.join(upstream, "bun.lock"))

    _write(os.path.join(upstream, "src", "value.ts"), "export const value = 'after';\n")
    patch = _git(
        upstream, "diff", "--binary", "--full-index", "HEAD", "--",
        "src/value.ts").stdout
    patch_path = os.path.join(root, "overlay.patch")
    _write(patch_path, patch)
    overlay_digest = _sha256(patch_path)
    _git(upstream, "add", "src/value.ts")
    tree_oid = _git(upstream, "write-tree").stdout.strip()
    return {
        "upstream": upstream,
        "patch": patch_path,
        "commit": commit,
        "lock_digest": lock_digest,
        "overlay_digest": overlay_digest,
        "tree_oid": tree_oid,
    }


def _clone_detached(fixture, root, name):
    target = os.path.join(root, name)
    subprocess.run(
        [GIT, "clone", "-q", fixture["upstream"], target],
        env={
            "HOME": root,
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True)
    _git(target, "checkout", "-q", "--detach", fixture["commit"])
    return target


def _apply_arguments(fixture, target, patch=None, overlay_digest=None,
                     commit=None, lock_digest=None, tree_oid=None):
    return [
        target,
        patch or fixture["patch"],
        commit or fixture["commit"],
        lock_digest or fixture["lock_digest"],
        overlay_digest or fixture["overlay_digest"],
        tree_oid or fixture["tree_oid"],
    ]


class GbrainOverlayDeliveryContract(unittest.TestCase):
    def test_overlay_artifact_has_no_trailing_whitespace(self):
        # Empty context lines may omit the unified-diff space marker. Keep
        # the artifact itself admissible to the committed-tree CI gate.
        for number, line in enumerate(_read(OVERLAY_PATH).splitlines(), 1):
            self.assertEqual(line, line.rstrip(), f"overlay line {number}")

    def test_sync_json_overlay_keeps_stdout_single_document(self):
        overlay = _read(OVERLAY_PATH)
        import_patch = overlay.split(
            "diff --git a/src/commands/import.ts b/src/commands/import.ts", 1)[1].split(
            "diff --git a/src/commands/sync.ts b/src/commands/sync.ts", 1)[0]
        sync_patch = overlay.split(
            "diff --git a/src/commands/sync.ts b/src/commands/sync.ts", 1)[1].split(
            "diff --git ", 1)[0]

        self.assertIn(
            "+  const jsonOutput = args.includes('--json') || opts.jsonToStderr === true;",
            import_patch)
        self.assertIn(
            "+    if (opts.jsonToStderr) console.error(message);",
            import_patch)
        self.assertIn(
            "+function syncInfo(opts: SyncOpts, message: string): void {",
            sync_patch)
        self.assertIn("+  if (opts.jsonOutput) serr(message);", sync_patch)
        self.assertIn("+    jsonToStderr: opts.jsonOutput === true,", sync_patch)
        self.assertIn("+    repoPath, dryRun, full, noPull, noEmbed, noExtract, jsonOutput: jsonOut,", sync_patch)
        self.assertIn(
            "+    syncInfo(opts, `Text imported. Run 'gbrain embed --stale' to generate embeddings.`);",
            sync_patch)
        self.assertIn(
            "+  syncInfo(opts, `Running full import of ${syncScopeRoot}",
            sync_patch)

    def test_overlay_artifact_is_in_release_and_plugin_snapshots_only(self):
        installer = _installer()
        self.assertTrue(
            os.path.isfile(OVERLAY_PATH),
            f"missing shipped gbrain overlay artifact: {OVERLAY_NAME}")

        release_words = shlex.split(installer.split(
            "SIA_RELEASE_FILES=(", 1)[1].split("\n)", 1)[0])
        self.assertEqual(
            release_words.count(OVERLAY_NAME), 1,
            "the release-source snapshot must bind the overlay exactly once")

        desktop = installer.split('step "8/9 desktop', 1)[1].split(
            'step "9/9 agents', 1)[0]
        plugin_words = shlex.split(desktop.split(
            "PLUGIN_ROOT_FILES=(", 1)[1].split("\n  )", 1)[0]
            if "\n  )" in desktop.split("PLUGIN_ROOT_FILES=(", 1)[1]
            else desktop.split("PLUGIN_ROOT_FILES=(", 1)[1].split(")", 1)[0])
        self.assertEqual(
            plugin_words.count(OVERLAY_NAME), 1,
            "an install launched from the installed plugin must retain the overlay")

        runtime_stage = installer.split('\nstep "3/9 runtime"\n', 1)[1].split(
            "\nSTAGED_RUNTIME_DIGEST=", 1)[0]
        self.assertNotIn(
            OVERLAY_NAME, runtime_stage,
            "the source overlay is installer provenance, not launched runtime")

    def test_pin_frontdoor_is_strict_unique_and_binds_overlay_bytes(self):
        program = _embedded_python(_installer(), "gbrain_pin_frontdoor")
        repository_pin = _run_python(program, [PIN_PATH, OVERLAY_PATH])
        self.assertEqual(repository_pin.returncode, 0, repository_pin.stderr)
        self.assertEqual(
            len(repository_pin.stdout.rstrip("\n").split("\t")), 5,
            "the admitted pin contract must emit exactly its five bound fields")
        with tempfile.TemporaryDirectory(prefix="sia-gbrain-pin-red-") as root:
            overlay = os.path.join(root, OVERLAY_NAME)
            _write(overlay, "fixture overlay bytes\n")
            overlay_digest = _sha256(overlay)
            values = {
                "commit": "b" * 40,
                "version": "0.47.6.0",
                "bun_lock_sha256": "c" * 64,
                "overlay_sha256": overlay_digest,
                "overlay_tree_oid": "d" * 40,
                "verified": "2026-08-30",
            }

            def pin_text(candidate):
                return "\n".join(
                    f"{key}={value}" for key, value in candidate.items()) + "\n"

            pin = os.path.join(root, "GBRAIN_PIN")
            _write(pin, pin_text(values))
            accepted = _run_python(program, [pin, overlay])
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(
                accepted.stdout.rstrip("\n").split("\t"),
                [values[key] for key in (
                    "commit", "version", "bun_lock_sha256",
                    "overlay_sha256", "overlay_tree_oid")])

            malformed = {}
            for field in ("overlay_sha256", "overlay_tree_oid"):
                malformed[f"duplicate {field}"] = (
                    pin_text(values) + f"{field}={values[field]}\n")
                without = dict(values)
                without.pop(field)
                malformed[f"missing {field}"] = pin_text(without)
            malformed["unknown assignment"] = pin_text(values) + "surprise=value\n"
            malformed["overlay digest mismatch"] = pin_text(
                dict(values, overlay_sha256="e" * 64))

            for label, contents in malformed.items():
                with self.subTest(label=label):
                    _write(pin, contents)
                    refused = _run_python(program, [pin, overlay])
                    self.assertNotEqual(refused.returncode, 0)

    def test_overlay_frontdoor_requires_exact_pristine_base_lock_and_package(self):
        program = _embedded_python(_installer(), "gbrain_overlay_frontdoor")
        with tempfile.TemporaryDirectory(prefix="sia-gbrain-base-red-") as root:
            fixture = _make_overlay_fixture(root)
            cases = ("wrong commit", "wrong lock digest", "changed package")
            for label in cases:
                with self.subTest(label=label):
                    target = _clone_detached(
                        fixture, root, label.replace(" ", "-"))
                    arguments = _apply_arguments(fixture, target)
                    if label == "wrong commit":
                        arguments = _apply_arguments(
                            fixture, target, commit="0" * 40)
                    elif label == "wrong lock digest":
                        arguments = _apply_arguments(
                            fixture, target, lock_digest="0" * 64)
                    else:
                        _write(
                            os.path.join(target, "package.json"),
                            '{"name":"ambient-package-change"}\n')
                    before = _read(os.path.join(target, "src", "value.ts"))
                    refused = _run_python(program, arguments)
                    self.assertNotEqual(refused.returncode, 0)
                    self.assertEqual(
                        _read(os.path.join(target, "src", "value.ts")), before)

    def test_overlay_frontdoor_refuses_bad_context_and_wrong_result_tree(self):
        program = _embedded_python(_installer(), "gbrain_overlay_frontdoor")
        with tempfile.TemporaryDirectory(prefix="sia-gbrain-context-red-") as root:
            fixture = _make_overlay_fixture(root)

            bad_patch = os.path.join(root, "wrong-context.patch")
            _write(bad_patch, """diff --git a/src/value.ts b/src/value.ts
--- a/src/value.ts
+++ b/src/value.ts
@@ -1 +1 @@
-this context does not exist
+nor does this replacement
""")
            bad_target = _clone_detached(fixture, root, "bad-context")
            bad = _run_python(program, _apply_arguments(
                fixture, bad_target, patch=bad_patch,
                overlay_digest=_sha256(bad_patch)))
            self.assertNotEqual(bad.returncode, 0)
            self.assertEqual(
                _read(os.path.join(bad_target, "src", "value.ts")),
                "export const value = 'before';\n")
            self.assertEqual(
                _git(bad_target, "diff", "--cached", "--name-only").stdout,
                "")

            wrong_tree_target = _clone_detached(fixture, root, "wrong-tree")
            wrong_tree = _run_python(program, _apply_arguments(
                fixture, wrong_tree_target, tree_oid="f" * 40))
            self.assertNotEqual(wrong_tree.returncode, 0)

    def test_overlay_frontdoor_admits_only_the_exact_post_apply_tree(self):
        program = _embedded_python(_installer(), "gbrain_overlay_frontdoor")
        with tempfile.TemporaryDirectory(prefix="sia-gbrain-tree-red-") as root:
            fixture = _make_overlay_fixture(root)
            target = _clone_detached(fixture, root, "candidate")
            accepted = _run_python(
                program, _apply_arguments(fixture, target))
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(accepted.stdout.strip(), fixture["tree_oid"])
            self.assertEqual(
                _git(target, "rev-parse", "HEAD").stdout.strip(),
                fixture["commit"])
            self.assertEqual(
                _git(target, "write-tree").stdout.strip(),
                fixture["tree_oid"])
            self.assertEqual(
                _read(os.path.join(target, "src", "value.ts")),
                "export const value = 'after';\n")
            self.assertEqual(
                _sha256(os.path.join(target, "bun.lock")),
                fixture["lock_digest"])
            self.assertEqual(
                _git(
                    target, "diff", "--name-only", "HEAD", "--",
                    "bun.lock", "package.json").stdout,
                "")

    def test_receipt_binds_overlay_and_old_receipt_never_executes_binary(self):
        installer = _installer()
        array = _shell_array(installer, "GBRAIN_STERILE_ENV")
        body = installer.split("gbrain_runtime_receipt_valid() {", 1)[1].split(
            "\n}\nif ! gbrain_runtime_receipt_valid", 1)[0]
        function = "gbrain_runtime_receipt_valid() {" + body + "\n}\n"
        self.assertIn("$PIN_OVERLAY_SHA256", function)
        self.assertIn("$PIN_OVERLAY_TREE_OID", function)

        with tempfile.TemporaryDirectory(prefix="sia-gbrain-receipt-red-") as root:
            binary = os.path.join(root, "gbrain")
            receipt = os.path.join(root, ".sia-release")
            sentinel = os.path.join(root, "executed")
            build_home = os.path.join(root, "build-home")
            os.makedirs(build_home)
            _write(
                binary,
                "#!/bin/sh\n"
                f": > {shlex.quote(sentinel)}\n"
                "printf '%s\\n' 'gbrain 0.47.6.0'\n",
                0o700)
            binary_digest = _sha256(binary)
            values = {
                "PIN": "b" * 40,
                "PIN_VERSION": "0.47.6.0",
                "PIN_LOCK_SHA256": "c" * 64,
                "PIN_OVERLAY_SHA256": "d" * 64,
                "PIN_OVERLAY_TREE_OID": "e" * 40,
            }
            old_prefix = (
                "managed-by=khephri.sia\n"
                f"commit={values['PIN']}\n"
                f"version={values['PIN_VERSION']}\n"
                f"bun_lock_sha256={values['PIN_LOCK_SHA256']}")
            new_prefix = (
                old_prefix
                + f"\noverlay_sha256={values['PIN_OVERLAY_SHA256']}"
                + f"\noverlay_tree_oid={values['PIN_OVERLAY_TREE_OID']}")

            metadata_stub = r'''
owned_metadata() {
  [ "$1" = release ] || return 1
  python3 - "$2" "$3" "$4" <<'PY'
import hashlib
import pathlib
import sys
receipt, binary, prefix = sys.argv[1:]
digest = hashlib.sha256(pathlib.Path(binary).read_bytes()).hexdigest()
expected = prefix + "\nbinary_sha256=" + digest + "\n"
raise SystemExit(0 if pathlib.Path(receipt).read_text() == expected else 1)
PY
}
bounded_command_capture() { "$@"; }
'''
            assignments = "\n".join(
                f"{key}={shlex.quote(value)}" for key, value in values.items())
            script = (
                "set -u\n"
                f"SIA_INSTALL_TMP={shlex.quote(root)}\n"
                f"GBRAIN_BUILD_HOME={shlex.quote(build_home)}\n"
                + array + metadata_stub + assignments + "\n"
                f"GBRAIN_BIN={shlex.quote(binary)}\n"
                f"GBRAIN_RECEIPT={shlex.quote(receipt)}\n"
                + function + "\ngbrain_runtime_receipt_valid\n")

            _write(receipt, old_prefix + f"\nbinary_sha256={binary_digest}\n")
            old = subprocess.run(
                ["bash", "-c", script], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(old.returncode, 0)
            self.assertFalse(os.path.exists(sentinel))

            _write(receipt, new_prefix + f"\nbinary_sha256={binary_digest}\n")
            current = subprocess.run(
                ["bash", "-c", script], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(current.returncode, 0, current.stderr)
            self.assertTrue(os.path.exists(sentinel))

    def test_overlay_is_applied_after_frozen_install_and_before_offline_build(self):
        installer = _installer()
        block = installer.split(
            'GBRAIN_SOURCE="$SIA_INSTALL_TMP/gbrain-source"', 1)[1].split(
            "gbrain_runtime_receipt_valid ||", 1)[0]
        flat = re.sub(r"\\\n\s*", " ", block)
        install_at = flat.index('"$BUN_BIN" install')
        overlay_at = flat.index('gbrain_overlay_frontdoor "$GBRAIN_SOURCE"')
        build_at = flat.index('"$BUN_BIN"')
        build_at = flat.index(" build ", max(build_at, overlay_at))
        self.assertLess(install_at, overlay_at)
        self.assertLess(overlay_at, build_at)
        self.assertIn("--frozen-lockfile", flat[install_at:overlay_at])
        self.assertIn("--production", flat[install_at:overlay_at])
        self.assertIn("--ignore-scripts", flat[install_at:overlay_at])

        compile_command = flat[overlay_at:]
        for flag in (
                "--no-env-file", "--no-install",
                "--no-compile-autoload-dotenv",
                "--no-compile-autoload-bunfig", "--compile"):
            with self.subTest(flag=flag):
                self.assertIn(flag, compile_command)
        self.assertIn('"${GBRAIN_STERILE_ENV[@]}"', compile_command)

    def test_poison_ambient_cannot_enter_build_or_version_environment(self):
        installer = _installer()
        array = _shell_array(installer, "GBRAIN_STERILE_ENV")
        self.assertIn("/usr/bin/env -i", array)

        receipt = installer.split("gbrain_runtime_receipt_valid() {", 1)[1].split(
            "\n}\nif ! gbrain_runtime_receipt_valid", 1)[0]
        self.assertIn(
            '"${GBRAIN_STERILE_ENV[@]}" "$GBRAIN_BIN" --version', receipt)
        gbrain_build = installer.split(
            'GBRAIN_SOURCE="$SIA_INSTALL_TMP/gbrain-source"', 1)[1].split(
            "gbrain_runtime_receipt_valid ||", 1)[0]
        self.assertRegex(
            re.sub(r"\\\n\s*", " ", gbrain_build),
            r'"\$\{GBRAIN_STERILE_ENV\[@\]\}" "\$BUN_BIN"[^\n]* build ')
        self.assertIn(
            '"${GBRAIN_STERILE_ENV[@]}" '
            '"$SIA_GBRAIN_STAGE/bin/gbrain" --version',
            re.sub(r"\\\n\s*", " ", gbrain_build))

        with tempfile.TemporaryDirectory(prefix="sia-gbrain-env-red-") as root:
            build_home = os.path.join(root, "build-home")
            os.makedirs(build_home)
            probe = os.path.join(root, "show-environment")
            _write(
                probe,
                "#!/usr/bin/python3\n"
                "import json, os\n"
                "print(json.dumps(dict(os.environ), sort_keys=True))\n",
                0o700)
            script = (
                "set -u\n"
                f"SIA_INSTALL_TMP={shlex.quote(root)}\n"
                f"GBRAIN_BUILD_HOME={shlex.quote(build_home)}\n"
                + array
                + f'"${{GBRAIN_STERILE_ENV[@]}}" {shlex.quote(probe)}\n')
            poison = os.environ.copy()
            poison.update({
                "HOME": os.path.join(root, "resident-home-poison"),
                "GBRAIN_HOME": os.path.join(root, "resident-brain-poison"),
                "GBRAIN_GUARDRAILS_MODULE": os.path.join(root, "guardrail-poison"),
                "GBRAIN_DATABASE_URL": "postgresql://poison.invalid/brain",
                "DATABASE_URL": "postgresql://poison.invalid/default",
                "GBRAIN_BRAIN_ID": "resident-poison",
                "GBRAIN_SOURCE": "resident-source-poison",
                "NODE_OPTIONS": "--require=ambient-poison",
                "BUN_OPTIONS": "ambient-poison",
                "BUN_CONFIG": os.path.join(root, "bunfig-poison"),
                "HTTPS_PROXY": "http://proxy-poison.invalid",
                "ALL_PROXY": "http://proxy-poison.invalid",
                "OLLAMA_HOST": "http://ollama-poison.invalid",
                "OPENAI_API_KEY": "secret-poison",
            })
            observed = subprocess.run(
                ["bash", "-c", script], env=poison, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(observed.returncode, 0, observed.stderr)
            environment = json.loads(observed.stdout)
            for key in poison:
                if key in {
                        "GBRAIN_GUARDRAILS_MODULE", "GBRAIN_DATABASE_URL",
                        "DATABASE_URL", "GBRAIN_BRAIN_ID", "GBRAIN_SOURCE",
                        "NODE_OPTIONS", "BUN_OPTIONS", "BUN_CONFIG",
                        "HTTPS_PROXY", "ALL_PROXY", "OLLAMA_HOST",
                        "OPENAI_API_KEY"}:
                    with self.subTest(poison=key):
                        self.assertNotIn(key, environment)
            self.assertEqual(environment.get("HOME"), build_home)
            self.assertEqual(environment.get("GBRAIN_HOME"), build_home)
            self.assertEqual(
                environment.get("GBRAIN_SKIP_STARTUP_HOOKS"), "1")
            self.assertEqual(
                environment.get("GBRAIN_SELF_UPGRADE_MODE"), "off")


if __name__ == "__main__":
    unittest.main(verbosity=2)
