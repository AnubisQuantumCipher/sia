"""Real Git controls for the experimental pre-check; no production authority."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from check_engine_boundary import git
from committed_export import validate_commit, validate_records


class CommittedExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        git(self.root, ["init", "-q"])
        (self.root / "page.md").write_text("fixture\n")
        self.commit = self.save()

    def save(self):
        git(self.root, ["add", "--all"])
        git(self.root, ["-c", "user.name=test", "-c", "user.email=test@test",
                        "commit", "-qm", "fixture"])
        return git(self.root, ["rev-parse", "HEAD"])

    def test_regular_and_dirty_worktree(self):
        (self.root / "page.md").write_text("uncommitted")
        (self.root / "untracked").symlink_to("/etc/passwd")
        self.assertEqual(validate_commit(self.root, self.commit),
                         {"files": 1, "blob_bytes": 8})

    def test_committed_symlink_refused(self):
        (self.root / "escape").symlink_to("/etc/passwd")
        with self.assertRaises(ValueError):
            validate_commit(self.root, self.save())

    def test_executable_refused(self):
        (self.root / "page.md").chmod(0o755)
        with self.assertRaises(ValueError):
            validate_commit(self.root, self.save())

    def test_gitlink_refused(self):
        git(self.root, ["update-index", "--add", "--cacheinfo",
                        "160000," + self.commit + ",nested"])
        git(self.root, ["-c", "user.name=test", "-c", "user.email=test@test",
                        "commit", "-qm", "gitlink"])
        with self.assertRaises(ValueError):
            validate_commit(self.root, git(self.root, ["rev-parse", "HEAD"]))

    def test_control_character_path_refused(self):
        (self.root / "line\nbreak.md").write_text("fixture")
        with self.assertRaises(ValueError):
            validate_commit(self.root, self.save())

    def test_oversized_blob_refused(self):
        (self.root / "large.md").write_bytes(b"x" * (1024 * 1024 + 1))
        with self.assertRaises(ValueError):
            validate_commit(self.root, self.save())

    def test_malformed_and_budget_controls(self):
        prefix = b"100644 blob " + b"a" * 40 + b" "
        for data in (b"", prefix + b"1\tx", prefix + b"1\t../escape\0",
                     prefix + b"1\t.git/config\0", prefix + b"1\t/a\0",
                     prefix + b"1\ta\0" + prefix + b"1\ta\0",
                     (prefix + b"1048576\ta\0") * 17,
                     b"x" * (1024 * 1024 + 1)):
            with self.subTest(data=data[:100]), self.assertRaises(ValueError):
                validate_records(data)

    def test_total_and_count_budgets(self):
        prefix = b"100644 blob " + b"a" * 40 + b" "
        for size, count in ((1048576, 17), (0, 4097)):
            data = b"".join(prefix + str(size).encode() + b"\tfile"
                            + str(i).encode() + b"\0" for i in range(count))
            with self.subTest(size=size), self.assertRaises(ValueError):
                validate_records(data)

    def test_invalid_commit_refused(self):
        for commit in ("HEAD", "--help", "0" * 40):
            with self.subTest(commit=commit), self.assertRaises(
                    (ValueError, subprocess.CalledProcessError)):
                validate_commit(self.root, commit)


if __name__ == "__main__":
    unittest.main()
