"""Exercise installed gbrain against disposable, read-only corpus exports."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

TOKEN = "siaisolationfixturetoken"
SLUG = "events/test/alpha"
UNCOMMITTED_TOKEN = "notindexedfixturezzzx"
DIRTY_TOKEN = "modifiedtrackedfixturezzzx"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(directory):
    return {str(p.relative_to(directory)): digest(p)
            for p in sorted(directory.rglob("*")) if p.is_file()}


def git(cwd, arguments):
    environment = {"PATH": "/usr/bin", "HOME": "/nonexistent",
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                   "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
                   "LC_ALL": "C"}
    return subprocess.check_output(
        ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
         "-c", "init.templateDir=", *arguments], cwd=cwd, env=environment,
        stderr=subprocess.PIPE, timeout=10).decode("utf-8", "strict").strip()


def prepare(output):
    corpus = output / "corpus"
    page = corpus / "events/test/alpha.md"
    page.parent.mkdir(parents=True)
    page.write_text("---\ntitle: alpha\n---\n# alpha\n" + TOKEN + "\n")
    for arguments in (["init", "-q"], ["add", "--all"],
                      ["-c", "user.name=isolation", "-c", "user.email=isolation@test",
                       "commit", "-qm", "disposable source fixture"]):
        git(corpus, arguments)
    committed = git(corpus, ["rev-parse", "HEAD"])
    (page.parent / "uncommitted.md").write_text(
        "---\ntitle: uncommitted\n---\n# uncommitted\n" + UNCOMMITTED_TOKEN + "\n")
    page.write_text("---\ntitle: alpha\n---\n# alpha\n" + DIRTY_TOKEN + "\n")
    git(output, ["clone", "--no-local", "--no-hardlinks", "--no-checkout",
                 str(corpus), str(output / "export")])
    git(output / "export", ["checkout", "--detach", committed])
    if git(output / "export", ["rev-parse", "HEAD"]) != committed \
            or git(output / "export", ["status", "--porcelain", "--untracked-files=all"]):
        raise RuntimeError("export is not the exact clean commit")
    (output / "export-commit.txt").write_text(committed + "\n")
    for name in ("state", "tmp"):
        (output / name).mkdir(mode=0o700)
    return inventory(corpus)


def sandbox(output, binary, bwrap):
    return [bwrap, "--unshare-user", "--unshare-net", "--unshare-pid",
            "--unshare-ipc", "--unshare-uts", "--disable-userns",
            "--die-with-parent", "--new-session", "--cap-drop", "ALL", "--clearenv",
            "--setenv", "PATH", "/usr/bin", "--setenv", "HOME", "/state",
            "--setenv", "GBRAIN_HOME", "/state",
            "--setenv", "GBRAIN_SELF_UPGRADE_MODE", "off",
            "--setenv", "TMPDIR", "/tmp",
            "--setenv", "GIT_CONFIG_COUNT", "1",
            "--setenv", "GIT_CONFIG_KEY_0", "safe.directory",
            "--setenv", "GIT_CONFIG_VALUE_0", "/source",
            "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib",
            "--proc", "/proc", "--dev", "/dev",
            "--ro-bind", str(output / "export"), "/source",
            "--bind", str(output / "state"), "/state",
            "--bind", str(output / "tmp"), "/tmp",
            "--ro-bind", str(binary), "/engine", "--remount-ro", "/",
            "--chdir", "/source", "--", "/engine"]


def run(output, name, base, arguments):
    invocation = ["/usr/bin/prlimit", "--fsize=67108864", "--nofile=256", "--cpu=45",
                  "/usr/bin/timeout", "--kill-after=5s", "60s", *base, *arguments]
    (output / (name + ".command.json")).write_text(json.dumps(invocation) + "\n")
    with (output / (name + ".stdout")).open("wb") as stdout, \
            (output / (name + ".stderr")).open("wb") as stderr:
        result = subprocess.run(invocation, stdin=subprocess.DEVNULL, stdout=stdout,
                                stderr=stderr, timeout=70, close_fds=True)
    (output / (name + ".exit")).write_text(str(result.returncode) + "\n")
    if result.returncode:
        raise RuntimeError(name + " failed; inspect retained output")
    with (output / (name + ".stdout")).open("rb") as stream:
        data = stream.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise RuntimeError(name + " output exceeds validation bound")
    return data.decode("utf-8", "strict")


def check_search(output, base, name, token, expected):
    found = run(output, name, base, ["search", token, "--source", "sia", "--json"])
    rows = json.loads(found)
    if not isinstance(rows, list):
        raise RuntimeError("search result is not a list")
    if not expected:
        if rows:
            raise RuntimeError("uncommitted fixture token retrieved")
    elif len(rows) != 1 or rows[0].get("slug") != SLUG \
            or rows[0].get("source_id") != "sia" or TOKEN not in rows[0].get("chunk_text", ""):
        raise RuntimeError("search did not retrieve committed fixture token")


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_engine_boundary.py GBRAIN_BINARY NEW_EVIDENCE_DIR")
    binary = Path(sys.argv[1]).resolve(strict=True)
    output = Path(sys.argv[2]).resolve()
    output.mkdir(mode=0o700)
    initial_binary = digest(binary)
    initial_source = prepare(output)
    initial_export = inventory(output / "export")
    (output / "corpus-before.json").write_text(json.dumps(initial_source, indent=2) + "\n")
    (output / "export-before.json").write_text(json.dumps(initial_export, indent=2) + "\n")
    bwrap = str(Path(shutil.which("bwrap") or "/missing-bwrap").resolve(strict=True))
    base = sandbox(output, binary, bwrap)
    version = run(output, "version", base, ["--version"])
    run(output, "init", base, ["init", "--pglite", "--non-interactive", "--json",
        "--skip-embed-check", "--path", "/state/.gbrain/brain.pglite", "--no-embedding"])
    run(output, "source", base, ["sources", "add", "sia", "--path", "/source"])
    sync = ["sync", "--source", "sia", "--no-pull", "--no-embed", "--no-extract"]
    run(output, "sync", base, sync)
    status = run(output, "status", base, ["engine", "status", "--probe", "--json"])
    report = json.loads(status[status.index("{"):])
    if report.get("database_path") != "/state/.gbrain/brain.pglite" or report.get("probe", {}).get("ok") is not True:
        raise RuntimeError("database path/probe mismatch")
    page = run(output, "get", base, ["get", SLUG, "--source", "sia"])
    if len(page.split("---", 2)) != 3 or page.split("---", 2)[2].strip() != "# alpha\n" + TOKEN:
        raise RuntimeError("retrieved committed page body mismatch")
    check_search(output, base, "search", TOKEN, True)
    check_search(output, base, "uncommitted-search", UNCOMMITTED_TOKEN, False)
    check_search(output, base, "dirty-search", DIRTY_TOKEN, False)
    run(output, "resync", base, sync)
    check_search(output, base, "resync-search", TOKEN, True)
    check_search(output, base, "resync-uncommitted-search", UNCOMMITTED_TOKEN, False)
    check_search(output, base, "resync-dirty-search", DIRTY_TOKEN, False)
    if initial_source != inventory(output / "corpus") \
            or initial_export != inventory(output / "export") or initial_binary != digest(binary):
        raise RuntimeError("read-only source or engine binary changed")
    summary = {"status": "TESTED", "version_output": version.strip(),
               "binary_sha256": initial_binary, "bwrap_sha256": digest(Path(bwrap)),
               "origin_file_contents_unchanged": True, "source_scoped_get_and_search": True,
               "export_file_contents_unchanged": True,
               "export_commit": (output / "export-commit.txt").read_text().strip(),
               "uncommitted_tokens_not_retrieved_before_and_after_resync": True,
               "resource_scope": "per-file, descriptor, CPU and time limits; aggregate disk and memory bounds UNPROVEN",
               "scope": "real gbrain offline indexing in disposable namespace; no embedding or production authority"}
    (output / "report.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
