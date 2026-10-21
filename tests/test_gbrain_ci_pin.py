"""Exercise the actual CI pin parser, including real special-file refusal."""

import hashlib
from pathlib import Path
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest


REPO = Path(__file__).resolve().parents[1]


def _program():
    workflow = (REPO / '.github/workflows/ci.yml').read_text(encoding='utf-8')
    marker = '<<\'PYPIN\'\n'
    if workflow.count(marker) != 1:
        raise AssertionError('exact CI pin parser missing or ambiguous')
    remainder = workflow.split(marker, 1)[1]
    terminator = '\n          PYPIN\n'
    if remainder.count(terminator) != 1:
        raise AssertionError('exact CI pin parser terminator missing or ambiguous')
    block = remainder.split(terminator, 1)[0]
    return textwrap.dedent(block)


def _valid_pin(overlay):
    return ('commit=' + 'a' * 40 + '\nversion=0.47.6.0\n'
            + 'bun_lock_sha256=' + 'b' * 64 + '\noverlay_sha256='
            + hashlib.sha256(overlay).hexdigest() + '\noverlay_tree_oid='
            + 'c' * 40 + '\nverified=2026-09-06\n').encode()


def _snapshot(root):
    result = {}
    for path in sorted(Path(root).iterdir()):
        info = path.lstat()
        content = None
        if stat.S_ISREG(info.st_mode):
            with path.open('rb') as stream:
                content = hashlib.file_digest(stream, 'sha256').hexdigest()
        elif stat.S_ISLNK(info.st_mode):
            content = os.readlink(path)
        result[path.name] = (info.st_dev, info.st_ino, info.st_mode,
                             info.st_nlink, info.st_uid, info.st_size,
                             info.st_mtime_ns, info.st_ctime_ns, content)
    return result


class GbrainCIPin(unittest.TestCase):
    def _run(self, pin, overlay, *, program=None):
        return subprocess.run(
            [sys.executable, '-I', '-W', 'error', '-c', program or _program(),
             str(pin), str(overlay)], stdin=subprocess.DEVNULL,
            capture_output=True, timeout=3, check=False)

    def test_valid_pin_returns_exact_build_identities(self):
        with tempfile.TemporaryDirectory() as root:
            pin, overlay = Path(root) / 'pin', Path(root) / 'overlay'
            overlay.write_bytes(b'fixture overlay\n')
            raw = _valid_pin(overlay.read_bytes())
            pin.write_bytes(raw)
            before = _snapshot(root)
            result = self._run(pin, overlay)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, b'')
            self.assertEqual(result.stdout.decode().strip().split('\t'), [
                'a' * 40, '0.47.6.0', 'b' * 64,
                hashlib.sha256(overlay.read_bytes()).hexdigest(), 'c' * 40,
                hashlib.sha256(raw).hexdigest()])
            self.assertEqual(pin.read_bytes(), raw)
            self.assertEqual(_snapshot(root), before)

    def test_invalid_fields_and_special_files_refuse_before_identity_output(self):
        cases = ('duplicate', 'unknown', 'missing', 'utf8', 'date', 'commit',
                 'digest', 'pin-symlink', 'overlay-symlink', 'pin-fifo',
                 'overlay-fifo', 'pin-oversize', 'overlay-oversize')
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as root:
                pin, overlay = Path(root) / 'pin', Path(root) / 'overlay'
                overlay.write_bytes(b'fixture overlay\n')
                raw = _valid_pin(overlay.read_bytes())
                variants = {
                    'duplicate': raw + b'verified=2026-09-06\n',
                    'unknown': raw + b'extra=yes\n',
                    'missing': raw.replace(b'verified=2026-09-06\n', b''),
                    'utf8': raw + b'\xff\n',
                    'date': raw.replace(b'2026-09-06', b'2026-02-30'),
                    'commit': raw.replace(b'commit=a', b'commit=z', 1),
                }
                pin.write_bytes(variants.get(case, raw))
                if case == 'digest':
                    overlay.write_bytes(b'different overlay\n')
                if '-' in case:
                    role, kind = case.split('-', 1)
                    target = pin if role == 'pin' else overlay
                    if kind == 'oversize':
                        with target.open('wb') as stream:
                            stream.truncate(65537 if role == 'pin' else 16777217)
                    else:
                        target.unlink()
                        if kind == 'fifo':
                            os.mkfifo(target, 0o600)
                        else:
                            backing = Path(root) / 'backing'
                            backing.write_bytes(raw if role == 'pin' else b'fixture overlay\n')
                            target.symlink_to(backing)
                before = _snapshot(root)
                result = self._run(pin, overlay)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b'')
                self.assertEqual(_snapshot(root), before)

    def test_held_pin_growth_refuses_before_identity_output(self):
        with tempfile.TemporaryDirectory() as root:
            pin, overlay = Path(root) / 'pin', Path(root) / 'overlay'
            overlay.write_bytes(b'fixture overlay\n')
            raw = _valid_pin(overlay.read_bytes())
            pin.write_bytes(raw)
            # Deterministically append after the actual first read. The parser
            # must refuse that generation; this is an injected race control.
            prefix = '''import os, sys
_original_read = os.read
_changed = False
def _grow_after_read(fd, count):
    global _changed
    data = _original_read(fd, count)
    if data and not _changed:
        _changed = True
        with open(sys.argv[1], "ab") as stream:
            stream.write(b"x")
    return data
os.read = _grow_after_read
'''
            result = self._run(pin, overlay, program=prefix + _program())
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b'')
            self.assertIn(b'CI pin input changed', result.stderr)
            self.assertEqual(pin.read_bytes(), raw + b'x')
            self.assertEqual(overlay.read_bytes(), b'fixture overlay\n')


if __name__ == '__main__':
    unittest.main()
