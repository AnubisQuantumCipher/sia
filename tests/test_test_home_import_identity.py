"""Both supported isolation imports must own one process-wide test home."""

import os
from pathlib import Path
import subprocess
import sys
import unittest

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home


REPO = Path(__file__).resolve().parent.parent

_CHILD = r'''
import importlib
import os
from pathlib import Path
import sys

root, first_name, second_name = sys.argv[1:]
sys.path.insert(0, root)
sys.path.insert(0, str(Path(root) / "tests"))
sys.path.insert(0, str(Path(root) / "bin"))
original_expanduser = os.path.expanduser
first = importlib.import_module(first_name)
first_home = first.ISOLATED_HOME
first_cache = sys.pycache_prefix
first_expander = os.path.expanduser
runtime = importlib.import_module("sialib")
second = importlib.import_module(second_name)
assert first is second, "supported import spellings constructed distinct isolation owners"
assert sys.modules["sia_test_home"] is sys.modules["tests.sia_test_home"]
assert first._REAL_EXPANDUSER is original_expanduser
assert second.ISOLATED_HOME == first_home
assert sys.pycache_prefix == first_cache
assert os.path.expanduser is first_expander
assert os.path.expanduser("~") == first_home
assert os.path.expanduser("~/nested") == os.path.join(first_home, "nested")
assert os.path.expanduser("relative") == "relative"
assert os.path.isdir(first_home)
assert os.path.isdir(first_cache)
assert runtime.HOME == first_home
assert os.path.commonpath((runtime.SHARE, first_home)) == first_home
assert os.path.commonpath((runtime.STATE, first_home)) == first_home
assert runtime.GBRAIN_ENV["GBRAIN_HOME"] == runtime.SHARE
print("same isolation owner; original expander retained; imported runtime remains inside it")
'''


class TestHomeImportIdentity(unittest.TestCase):
    def test_both_import_orders_retain_one_owner_and_the_imported_runtime(self):
        for first, second in (
                ("sia_test_home", "tests.sia_test_home"),
                ("tests.sia_test_home", "sia_test_home")):
            with self.subTest(first=first):
                result = subprocess.run(
                    [sys.executable, "-B", "-W", "error", "-c", _CHILD,
                     str(REPO), first, second], cwd=REPO,
                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, encoding="utf-8",
                    errors="strict", timeout=60, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout,
                                 "same isolation owner; original expander retained; imported runtime remains inside it\n")


if __name__ == "__main__":
    unittest.main()
