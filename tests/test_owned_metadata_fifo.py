"""FIFO admission controls for extracted install/uninstall metadata readers."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests import test_release as release


def _identity(path):
    value = os.lstat(path)
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


class OwnedMetadataFifo(unittest.TestCase):
    def test_managed_receipt_and_target_fifos_refuse_without_adoption(self):
        for script in ("install.sh", "uninstall.sh"):
            program = release._owned_metadata_python(release._read(script))
            for role in ("receipt", "target"):
                with self.subTest(script=script, role=role), \
                        tempfile.TemporaryDirectory() as root:
                    target = Path(root) / "target"
                    receipt = Path(root) / "receipt"
                    target.write_bytes(b"managed target\n")
                    receipt.write_text(release._managed_file_receipt(str(target), "sia-cli"))
                    special = receipt if role == "receipt" else target
                    regular = target if role == "receipt" else receipt
                    content = regular.read_bytes()
                    special.unlink()
                    os.mkfifo(special, 0o600)
                    before = _identity(special)
                    try:
                        result = subprocess.run(
                            [sys.executable, "-I", "-W", "error", "-c", program,
                             "managed-file", str(receipt), "sia-cli", str(target)],
                            stdin=subprocess.DEVNULL, capture_output=True,
                            timeout=3, check=False)
                    finally:
                        self.assertEqual(_identity(special), before)
                        self.assertEqual(regular.read_bytes(), content)
                        self.assertEqual(set(os.listdir(root)), {"receipt", "target"})
                    # This existing boolean front door communicates refusal by
                    # exit status. Its output contract stays byte-for-byte empty.
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, b"")
                    self.assertEqual(result.stderr, b"")


if __name__ == "__main__":
    unittest.main()
