"""A physical index generation is copied only from admitted sealed bytes."""

import hashlib
import importlib
import io
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))


class RawVectorSnapshot(unittest.TestCase):
    def setUp(self):
        self.vector = importlib.import_module("siavector")
        self.assertTrue(hasattr(self.vector, "private_index_snapshot"),
                        "physical snapshot admission must exist")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / "index.tar"

    def _archive(self, entries):
        with tarfile.open(self.archive, "w", format=tarfile.USTAR_FORMAT) as tar:
            for name, kind, content in entries:
                item = tarfile.TarInfo(name)
                item.type = kind
                if kind == tarfile.REGTYPE:
                    item.size = len(content)
                    tar.addfile(item, io.BytesIO(content))
                else:
                    item.linkname = content
                    tar.addfile(item)
        self.archive.chmod(0o600)
        return hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def _snapshot(self, digest):
        return self.vector.private_index_snapshot(
            str(self.archive), digest, scratch_parent=str(self.root))

    def test_private_copy_retains_physical_bytes_without_mutating_archive(self):
        digest = self._archive([("base", tarfile.DIRTYPE, ""),
                                ("base/index", tarfile.REGTYPE, b"HNSW topology"),
                                ("PG_VERSION", tarfile.REGTYPE, b"17\n")])
        with self._snapshot(digest) as snapshot:
            directory = Path(snapshot["directory"])
            self.assertEqual(snapshot["archive_sha256"], digest)
            self.assertEqual((directory / "base/index").read_bytes(), b"HNSW topology")
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
            self.assertEqual((directory / "base/index").stat().st_nlink, 1)
            self.assertEqual(snapshot["manifest"], [
                {"path": "base", "type": "directory"},
                {"path": "base/index", "type": "file", "bytes": len(b"HNSW topology"),
                 "sha256": hashlib.sha256(b"HNSW topology").hexdigest()},
                {"path": "PG_VERSION", "type": "file", "bytes": len(b"17\n"),
                 "sha256": hashlib.sha256(b"17\n").hexdigest()},
            ])
            (directory / "base/index").write_bytes(b"private WAL changes")
            self.assertEqual(hashlib.sha256(self.archive.read_bytes()).hexdigest(), digest)
        self.assertFalse(directory.exists())

    def test_wrong_digest_refuses_before_any_database_copy(self):
        self._archive([("PG_VERSION", tarfile.REGTYPE, b"17\n")])
        with self.assertRaises(self.vector.VectorRefusal):
            with self._snapshot("0" * 64):
                self.fail("unadmitted archive was extracted")
        self.assertEqual(list(self.root.iterdir()), [self.archive])

    def test_engine_directory_is_an_ordinary_fixed_child_of_descriptor_parent(self):
        digest = self._archive([("PG_VERSION", tarfile.REGTYPE, b"17\n")])
        with self._snapshot(digest) as snapshot:
            self.assertIn("descriptor_parent", snapshot)
            parent = Path(snapshot["descriptor_parent"])
            self.assertEqual(Path(snapshot["directory"]), parent / "index")
            self.assertFalse((parent / "index").is_symlink())
            self.assertEqual(parent.stat().st_mode & 0o777, 0o700)

    def test_links_escapes_aliases_and_duplicate_members_refuse(self):
        cases = [
            [("../outside", tarfile.REGTYPE, b"bad")],
            [("/absolute", tarfile.REGTYPE, b"bad")],
            [("a/../alias", tarfile.REGTYPE, b"bad")],
            [("./alias", tarfile.REGTYPE, b"bad")],
            [("alias//file", tarfile.REGTYPE, b"bad")],
            [("link", tarfile.SYMTYPE, "/outside")],
            [("link", tarfile.LNKTYPE, "other")],
            [("fifo", tarfile.FIFOTYPE, "")],
            [("dup", tarfile.REGTYPE, b"first"),
             ("dup", tarfile.REGTYPE, b"second")],
            [("parent", tarfile.REGTYPE, b"file"),
             ("parent/child", tarfile.REGTYPE, b"bad")],
        ]
        for entries in cases:
            with self.subTest(entries=entries):
                digest = self._archive(entries)
                with self.assertRaises(self.vector.VectorRefusal):
                    with self._snapshot(digest):
                        self.fail("unsafe archive was admitted")
                self.assertEqual(list(self.root.iterdir()), [self.archive])

    def test_archive_path_replacement_invalidates_completed_private_use(self):
        digest = self._archive([("PG_VERSION", tarfile.REGTYPE, b"17\n")])
        with self.assertRaisesRegex(self.vector.VectorRefusal, "changed"):
            with self._snapshot(digest):
                replacement = self.root / "replacement"
                replacement.write_bytes(self.archive.read_bytes())
                os.replace(replacement, self.archive)


if __name__ == "__main__":
    unittest.main()
