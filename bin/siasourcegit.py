"""Descriptor-bound Git generation for a published controller source batch."""

import hashlib
import json
import os
import re
import stat


_HEX = re.compile(r"[0-9a-f]{64}")
_OIDS = {
    "sha1": re.compile(r"[0-9a-f]{40}"),
    "sha256": re.compile(r"[0-9a-f]{64}"),
}
_EXECUTABLE_CEILING = 16_777_216


def _refuse(source, reason, *, upstream=None):
    source.refuse(reason, phase="effects", upstream=upstream)


def _identity(info):
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
    )


class _HeldGitBoundary:
    def __init__(self, owner, source):
        self.owner = owner
        self.source = source
        self.root_fd = None
        self.executable_parent_fd = None
        self.executable_fd = None
        self.root_path = os.path.abspath(owner["CORPUS"])
        self.executable_path = os.path.abspath(owner["GIT"])
        try:
            directory_flags = (
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0))
            self.root_fd = os.open(self.root_path, directory_flags)
            root = os.fstat(self.root_fd)
            if not stat.S_ISDIR(root.st_mode) \
                    or root.st_uid != os.geteuid() \
                    or root.st_mode & 0o022:
                _refuse(source, "source-git-corpus-directory")
            self.root_identity = (
                root.st_dev, root.st_ino, root.st_mode,
                root.st_uid, root.st_gid)

            parent, leaf = os.path.split(self.executable_path)
            if not leaf:
                _refuse(source, "source-git-executable-path")
            self.executable_parent = parent
            self.executable_leaf = leaf
            self.executable_parent_fd = os.open(parent, directory_flags)
            parent_info = os.fstat(self.executable_parent_fd)
            if not stat.S_ISDIR(parent_info.st_mode) \
                    or parent_info.st_mode & 0o022:
                _refuse(source, "source-git-executable-parent")
            self.executable_parent_identity = (
                parent_info.st_dev, parent_info.st_ino,
                parent_info.st_mode, parent_info.st_uid,
                parent_info.st_gid)
            file_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                          | getattr(os, "O_NOFOLLOW", 0))
            self.executable_fd = os.open(
                leaf, file_flags, dir_fd=self.executable_parent_fd)
            executable = os.fstat(self.executable_fd)
            if not stat.S_ISREG(executable.st_mode) \
                    or executable.st_uid not in (0, os.geteuid()) \
                    or executable.st_nlink != 1 \
                    or executable.st_mode & 0o022 \
                    or executable.st_mode & 0o111 == 0 \
                    or not 0 < executable.st_size <= _EXECUTABLE_CEILING:
                _refuse(source, "source-git-executable")
            self.executable_identity = _identity(executable)
            self.executable_sha256 = self._hash_executable(
                executable.st_size)
            self.current()
        except BaseException:
            self.close()
            raise

    def _hash_executable(self, size):
        digest = hashlib.sha256()
        offset = 0
        while offset < size:
            block = os.pread(
                self.executable_fd, min(1_048_576, size - offset), offset)
            if not block:
                _refuse(self.source, "source-git-executable-short-read")
            digest.update(block)
            offset += len(block)
        if offset != size \
                or _identity(os.fstat(self.executable_fd)) \
                != self.executable_identity:
            _refuse(self.source, "source-git-executable-changed")
        return digest.hexdigest()

    def current(self):
        root = os.fstat(self.root_fd)
        if (root.st_dev, root.st_ino, root.st_mode,
                root.st_uid, root.st_gid) != self.root_identity:
            _refuse(self.source, "source-git-corpus-descriptor-changed")
        try:
            named_root = os.stat(self.root_path, follow_symlinks=False)
        except OSError as exc:
            _refuse(
                self.source, "source-git-corpus-name-changed", upstream=exc)
        if not stat.S_ISDIR(named_root.st_mode) \
                or (named_root.st_dev, named_root.st_ino,
                    named_root.st_mode, named_root.st_uid,
                    named_root.st_gid) != self.root_identity:
            _refuse(self.source, "source-git-corpus-name-changed")

        parent = os.fstat(self.executable_parent_fd)
        if (parent.st_dev, parent.st_ino, parent.st_mode,
                parent.st_uid, parent.st_gid) \
                != self.executable_parent_identity \
                or _identity(os.fstat(self.executable_fd)) \
                != self.executable_identity:
            _refuse(self.source, "source-git-executable-descriptor-changed")
        try:
            named_parent = os.stat(
                self.executable_parent, follow_symlinks=False)
            named_executable = os.stat(
                self.executable_leaf, dir_fd=self.executable_parent_fd,
                follow_symlinks=False)
        except OSError as exc:
            _refuse(
                self.source, "source-git-executable-name-changed",
                upstream=exc)
        if not stat.S_ISDIR(named_parent.st_mode) \
                or (named_parent.st_dev, named_parent.st_ino,
                    named_parent.st_mode, named_parent.st_uid,
                    named_parent.st_gid) != self.executable_parent_identity \
                or not stat.S_ISREG(named_executable.st_mode) \
                or _identity(named_executable) != self.executable_identity:
            _refuse(self.source, "source-git-executable-name-changed")

    def close(self):
        for name in ("executable_fd", "executable_parent_fd", "root_fd"):
            descriptor = getattr(self, name)
            if descriptor is not None:
                os.close(descriptor)
                setattr(self, name, None)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _run(owner, source, held, arguments, *, label, allowed=(0,)):
    held.current()
    command = [
        owner["_chain_descriptor_path"](held.executable_fd),
        "-c", "core.hooksPath=/dev/null",
        "-c", "commit.gpgsign=false",
        *arguments,
    ]
    environment = dict(os.environ)
    environment.update({
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
    })
    try:
        result = owner["_run_bounded_text_process"](
            command, env=environment, timeout=60,
            cwd=owner["_chain_descriptor_path"](held.root_fd),
            pass_fds=(held.executable_fd, held.root_fd), label=label,
            output_limit=owner["MAX_EXTERNAL_OUTPUT_BYTES"])
    except (OSError, ValueError, RuntimeError, OverflowError) as exc:
        _refuse(source, "source-git-process", upstream=exc)
    held.current()
    if result.returncode not in allowed:
        _refuse(source, "source-git-command")
    return result


def _one_line(source, result, reason):
    value = result.stdout.strip()
    if not value or "\n" in value or "\r" in value or "\x00" in value:
        _refuse(source, reason)
    return value


def commit_generation(owner, *, source_batch_sha256,
                      event_closure_sha256):
    """Commit the exact current corpus cut and return its closed identity."""
    return _commit_generation(
        owner, source_batch_sha256=source_batch_sha256,
        publication_sha256=event_closure_sha256)


def commit_content_generation(owner, *, source_batch_sha256,
                              content_publication_sha256):
    """Commit the corpus cut selected by an event/gist effects publication."""
    return _commit_generation(
        owner, source_batch_sha256=source_batch_sha256,
        publication_sha256=content_publication_sha256)


def _commit_generation(owner, *, source_batch_sha256, publication_sha256):
    import siasourcebatch as source

    for value in (source_batch_sha256, publication_sha256):
        if type(value) is not str or _HEX.fullmatch(value) is None:
            _refuse(source, "source-git-input-digest")
    held = _HeldGitBoundary(owner, source)
    try:
        object_format = _one_line(source, _run(
            owner, source, held, ["rev-parse", "--show-object-format"],
            label="source Git object format"),
            "source-git-object-format")
        if object_format not in _OIDS:
            _refuse(source, "source-git-object-format")
        oid = _OIDS[object_format]
        before = _one_line(source, _run(
            owner, source, held, ["rev-parse", "HEAD"],
            label="source Git prior commit"), "source-git-prior-commit")
        if oid.fullmatch(before) is None:
            _refuse(source, "source-git-prior-commit")
        _run(owner, source, held, ["add", "-A", "--"],
             label="source Git stage")
        staged = _run(
            owner, source, held,
            ["diff", "--cached", "--quiet", "--no-ext-diff", "--"],
            label="source Git staged difference", allowed=(0, 1))
        if staged.returncode == 1:
            _run(owner, source, held, [
                "-c", "user.email=sia@omarchy.local",
                "-c", "user.name=SIA", "commit", "-q", "-m",
                "SIA source batch " + source_batch_sha256,
            ], label="source Git commit")
        committed = _one_line(source, _run(
            owner, source, held, ["rev-parse", "HEAD"],
            label="source Git committed generation"),
            "source-git-committed-generation")
        tree = _one_line(source, _run(
            owner, source, held, ["rev-parse", "HEAD^{tree}"],
            label="source Git committed tree"),
            "source-git-committed-tree")
        if oid.fullmatch(committed) is None or oid.fullmatch(tree) is None:
            _refuse(source, "source-git-object-id")
        clean = _run(
            owner, source, held,
            ["status", "--porcelain", "--untracked-files=all"],
            label="source Git clean status")
        if clean.stdout != "" or clean.stderr != "":
            _refuse(source, "source-git-not-clean")
        retained_format = _one_line(source, _run(
            owner, source, held, ["rev-parse", "--show-object-format"],
            label="source Git retained object format"),
            "source-git-retained-object-format")
        retained_head = _one_line(source, _run(
            owner, source, held, ["rev-parse", "HEAD"],
            label="source Git retained commit"),
            "source-git-retained-commit")
        retained_tree = _one_line(source, _run(
            owner, source, held, ["rev-parse", "HEAD^{tree}"],
            label="source Git retained tree"),
            "source-git-retained-tree")
        if retained_format != object_format \
                or retained_head != committed or retained_tree != tree:
            _refuse(source, "source-git-generation-changed")
        body = {
            "schema": "sia-controller-source-corpus-generation-v1",
            "object_format": object_format,
            "git_executable_sha256": held.executable_sha256,
            "before_commit_oid": before,
            "corpus_commit_oid": committed,
            "corpus_tree_oid": tree,
            "clean": True,
        }
        result = {
            **body,
            "generation_sha256": hashlib.sha256(_canonical(body)).hexdigest(),
        }
        held.current()
        return result
    finally:
        held.close()
