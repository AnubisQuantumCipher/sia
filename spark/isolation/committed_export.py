"""Conservative pre-check for disposable exports; not a protected exporter."""
import re
import subprocess
import tempfile

MAX_TREE_BYTES = 1024 * 1024
MAX_FILES = 4096
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024


def validate_records(data):
    """Accept bounded regular-file trees with unambiguous relative UTF-8 paths."""
    if len(data) > MAX_TREE_BYTES or not data or not data.endswith(b"\0"):
        raise ValueError("missing or oversized tree listing")
    records = data[:-1].split(b"\0")
    if len(records) > MAX_FILES:
        raise ValueError("too many files")
    seen = set()
    total = 0
    for record in records:
        header, path = record.split(b"\t", 1)
        mode, kind, oid, size_text = header.split()
        if mode != b"100644" or kind != b"blob" or not re.fullmatch(rb"[0-9a-f]{40}", oid):
            raise ValueError("unsupported Git entry")
        if not re.fullmatch(rb"[0-9]{1,10}", size_text):
            raise ValueError("invalid blob size")
        size = int(size_text)
        total += size
        if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise ValueError("blob budget exceeded")
        name = path.decode("utf-8", "strict")
        parts = name.split("/")
        if len(path) > 1024 or any(ord(c) < 32 or ord(c) == 127 for c in name) \
                or any(p in ("", ".", "..") or p.casefold() == ".git" for p in parts) \
                or "\\" in name or name in seen:
            raise ValueError("unsafe or duplicate export path")
        seen.add(name)
    return {"files": len(records), "blob_bytes": total}


def validate_commit(repository, commit):
    """Inspect the pinned tree before checkout, with bounded listing storage."""
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("expected full SHA-1 commit identity")
    environment = {"PATH": "/usr/bin", "HOME": "/nonexistent",
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                   "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
                   "LC_ALL": "C"}
    with tempfile.TemporaryFile() as listing, tempfile.TemporaryFile() as errors:
        subprocess.run(["/usr/bin/prlimit", "--fsize=1048576", "--cpu=5", "--",
                        "/usr/bin/git", "ls-tree", "-r", "-l", "-z", commit],
                       cwd=repository, env=environment, stdin=subprocess.DEVNULL,
                       stdout=listing, stderr=errors, timeout=10, check=True)
        listing.seek(0)
        return validate_records(listing.read(MAX_TREE_BYTES + 1))
