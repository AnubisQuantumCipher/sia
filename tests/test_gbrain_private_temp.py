"""Private extension-cache boundary, without touching the resident brain."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sialib_private_temp", REPO / "bin/sialib.py")
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)
import siasourceengine
import siacapsule


@contextlib.contextmanager
def fixture_lease():
    with open(os.devnull) as stream:
        yield stream.fileno()


class PrivateGbrainTemp(unittest.TestCase):
    def test_compatibility_and_restore_ignore_poisoned_or_symlinked_cache(self):
        # Model the pinned engine's same-size cache reuse at the actual child
        # process boundary. The real binary contract suite separately checks
        # the unmodified engine's legitimate workflows.
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            hostile = root / "hostile"
            hostile.mkdir()
            cache = hostile / "gbrain-pglite-assets"
            cache.mkdir()
            archive = cache / "vector-fixture.tar.gz"
            archive.write_bytes(b"evil")
            fake = root / "gbrain"
            fake.write_text('''#!/usr/bin/env python3
import json, os, pathlib, stat
root = pathlib.Path(os.environ.get("TMPDIR", "/tmp"))
cache = root / "gbrain-pglite-assets"
cache.mkdir(exist_ok=True)
archive = cache / "vector-fixture.tar.gz"
if not archive.exists() or archive.stat().st_size != len(b"good"):
    archive.write_bytes(b"good")
print(json.dumps({"asset": archive.read_text(), "tmp": str(root),
                  "mode": stat.S_IMODE(root.stat().st_mode),
                  "home": os.environ["GBRAIN_HOME"]}))
''')
            fake.chmod(0o755)
            environment = dict(os.environ, TMPDIR=str(hostile),
                               TMP=str(hostile), TEMP=str(hostile),
                               GBRAIN_HOME=str(root / "brain"))
            # Negative control: the unfixed environment accepts planted bytes.
            control = subprocess.run([str(fake)], env=environment,
                                     capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(control.stdout)["asset"], "evil")
            owner = dict(vars(lib), GBRAIN=str(fake), GBRAIN_ENV=environment,
                         CORPUS=str(root),
                         gbrain_owner=fixture_lease)
            for symlinked in (False, True):
                if symlinked:
                    cache.rename(hostile / "planted")
                    cache.symlink_to(hostile / "planted", target_is_directory=True)
                with self.subTest(symlinked=symlinked):
                    ordinary = siasourceengine.compatibility_gbrain(owner, ["query"])
                    called = siasourceengine.compatibility_gbrain_call_unlocked(
                        owner, "fixture", {})
                    with mock.patch.object(siacapsule, "sialib", lib), \
                            mock.patch.object(lib, "GBRAIN", str(fake)), \
                            mock.patch.object(lib, "GBRAIN_ENV", environment), \
                            mock.patch.object(lib, "CORPUS", str(root)):
                        restored = siacapsule._run_gbrain(
                            ["engine", "status"], home=str(root / "restore"),
                            label="restore fixture")
                    for result in (json.loads(ordinary.stdout), called,
                                   json.loads(restored.stdout)):
                        self.assertEqual(result["asset"], "good")
                        self.assertEqual(result["mode"], 0o700)
                        self.assertNotEqual(result["tmp"], str(hostile))
                        self.assertFalse(Path(result["tmp"]).exists())
                    self.assertEqual(json.loads(restored.stdout)["home"],
                                     str(root / "restore"))
                    self.assertEqual(archive.read_bytes(), b"evil")
                    self.assertEqual(environment["TMPDIR"], str(hostile))

    def test_exception_cleans_private_directory_and_preserves_error_semantics(self):
        seen = []
        def failed(command, **kwargs):
            seen.append(kwargs["env"]["TMPDIR"])
            self.assertTrue(Path(seen[-1]).is_dir())
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        owner = dict(vars(lib), _run_bounded_text_process=failed,
                     gbrain_owner=fixture_lease)
        result = siasourceengine.compatibility_gbrain(owner, ["query"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timed out", result.stderr)
        self.assertIsNone(siasourceengine.compatibility_gbrain_call_unlocked(
            owner, "fixture", {}))
        for path in seen:
            self.assertFalse(Path(path).exists())

    def test_temp_creation_failure_never_launches_engine(self):
        launch = mock.Mock()
        owner = dict(vars(lib), _run_bounded_text_process=launch,
                     gbrain_owner=fixture_lease)
        with mock.patch.object(lib.tempfile, "TemporaryDirectory",
                               side_effect=OSError("no private temp")):
            result = siasourceengine.compatibility_gbrain(owner, ["query"])
            self.assertNotEqual(result.returncode, 0)
            self.assertIsNone(siasourceengine.compatibility_gbrain_call_unlocked(
                owner, "fixture", {}))
        launch.assert_not_called()

    def test_installer_temp_setup_overrides_hostile_parent(self):
        installer = (REPO / "install.sh").read_text()
        setup = 'SIA_INSTALL_TMP=' + installer.split('SIA_INSTALL_TMP=', 1)[1].split(
            '\nSIA_BRAINSTEM_WAS_ACTIVE=', 1)[0]
        with tempfile.TemporaryDirectory() as hostile:
            result = subprocess.run(
                ["bash", "-c", 'set -eu\n' + setup + '''
trap 'rm -rf -- "$SIA_INSTALL_TMP"' EXIT
python3 -c 'import json,os,stat; p=os.environ["TMPDIR"]; print(json.dumps({"tmp":p,"mode":stat.S_IMODE(os.stat(p).st_mode)}))'
'''], env=dict(os.environ, TMPDIR=hostile),
                capture_output=True, text=True, check=True)
            observed = json.loads(result.stdout)
            self.assertEqual(Path(observed["tmp"]).parent, Path("/tmp"))
            self.assertEqual(observed["mode"], 0o700)
            self.assertFalse(Path(observed["tmp"]).exists())


if __name__ == "__main__":
    unittest.main()
