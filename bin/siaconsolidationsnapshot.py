"""Experimental bounded immutable-tree discovery; not wired into recovery.

Git and the supplied bounded subprocess runner are trusted dependencies.
Tree identity is a namespace snapshot, not permission to remove live sources.
"""
import re

MAX_TREE_BYTES = 16_777_216
MAX_TREE_ENTRIES = 4096
MAX_PAGE_ENTRIES = 1024


def object_id(value):
    if not isinstance(value, str) or re.fullmatch(
            r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is None:
        raise ValueError("snapshot requires a full object identity")
    return value


def parse_tree(text):
    if not isinstance(text, str) or len(text) > MAX_TREE_BYTES \
            or len(text.encode("utf-8")) > MAX_TREE_BYTES:
        raise ValueError("snapshot tree exceeds its byte bound")
    if text and not text.endswith("\0"):
        raise ValueError("snapshot tree output is incomplete")
    if text.count("\0") > MAX_TREE_ENTRIES:
        raise ValueError("snapshot tree exceeds its entry bound")
    entries, names = [], set()
    for record in text.split("\0")[:-1]:
        metadata, separator, name = record.partition("\t")
        fields = metadata.split(" ")
        if not separator or len(fields) != 3:
            raise ValueError("snapshot tree record is malformed")
        mode, kind, identity = fields
        if (mode, kind) not in {
                ("040000", "tree"), ("100644", "blob"), ("100755", "blob")}:
            raise ValueError("snapshot contains an unsupported entry type")
        object_id(identity)
        if not name or name in {".", ".."} or "/" in name \
                or len(name.encode("utf-8")) > 255 \
                or any(ord(char) < 32 or ord(char) == 127 for char in name) \
                or name in names:
            raise ValueError("snapshot entry name is invalid")
        names.add(name)
        entries.append({"name": name, "kind": kind, "mode": mode,
                        "object": identity})
    return entries


def tree_page(run, corpus, identity, offset, limit):
    """Read a page of one pinned tree; reject moving refs and bad cursors."""
    object_id(identity)
    if isinstance(offset, bool) or not isinstance(offset, int) \
            or not 0 <= offset <= MAX_TREE_ENTRIES \
            or isinstance(limit, bool) or not isinstance(limit, int) \
            or not 1 <= limit <= MAX_PAGE_ENTRIES:
        raise ValueError("snapshot page cursor or bound is invalid")
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
           "GIT_TERMINAL_PROMPT": "0", "GIT_ALLOW_PROTOCOL": ""}
    command = ["/usr/bin/git", "--no-replace-objects",
               "-c", "protocol.allow=never"]
    kind = run(command + ["cat-file", "-t", identity], env=env, timeout=30,
               cwd=corpus, label="snapshot object type", output_limit=64)
    if kind.returncode != 0 or kind.stdout != "tree\n":
        raise ValueError("snapshot identity is not an available tree")
    result = run(command + ["ls-tree", "--full-tree", "-z", identity],
                 env=env, timeout=30, cwd=corpus,
                 label="snapshot tree", output_limit=MAX_TREE_BYTES)
    if result.returncode != 0:
        raise ValueError("snapshot tree read failed")
    entries = parse_tree(result.stdout)
    if offset > len(entries):
        raise ValueError("snapshot cursor exceeds tree entries")
    page = entries[offset:offset + limit]
    following = offset + len(page)
    return {"tree": identity, "entries": page, "next": following,
            "complete": following == len(entries)}
