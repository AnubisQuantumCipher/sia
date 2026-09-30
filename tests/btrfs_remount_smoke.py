#!/usr/bin/env python3
"""Opt-in Linux integration check on a disposable loopback btrfs filesystem.

CI calls this explicitly with --run. Requires mkfs.btrfs and passwordless sudo
for mount/umount/chown only. Never mounts or changes an existing filesystem.
The isolated CLI fixture supplies an absent delivery epoch; the real adopted
case is exercised separately by test_controller_delivery_epoch.
"""
import contextlib
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock

import sia_test_home  # redirect all runtime defaults before importing SIA


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True)


def main():
    if sys.argv[1:] != ['--run']:
        raise SystemExit('explicit --run required (disposable privileged mount test)')
    repo = Path(__file__).resolve().parents[1]
    loader = importlib.machinery.SourceFileLoader('sia_btrfs_smoke', str(repo / 'bin/sia'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    sia = importlib.util.module_from_spec(spec)
    loader.exec_module(sia)
    import siacontrollerdeliveryepoch as epochs

    with tempfile.TemporaryDirectory(prefix='sia-btrfs-') as temporary:
        root = Path(temporary)
        image = root / 'filesystem.img'
        mount = root / 'mount'
        mount.mkdir()
        run('truncate', '-s', '256M', str(image))
        run('mkfs.btrfs', '-f', str(image))
        mounted = False

        def mount_image(*options):
            nonlocal mounted
            run('sudo', '-n', 'mount', '-o', ','.join(('loop', *options)),
                str(image), str(mount))
            mounted = True

        def unmount_image():
            nonlocal mounted
            run('sudo', '-n', 'umount', str(mount))
            mounted = False

        try:
            mount_image()
            run('sudo', '-n', 'btrfs', 'subvolume', 'create', str(mount / 'primary'))
            run('sudo', '-n', 'btrfs', 'subvolume', 'create', str(mount / 'replacement'))
            for name in ('primary', 'replacement'):
                run('sudo', '-n', 'chown', str(os.geteuid()) + ':' + str(os.getegid()),
                    str(mount / name))
            unmount_image()
            mount_image('subvol=primary')
            corpus = mount / 'corpus'
            corpus.mkdir(mode=0o700)
            state = root / 'state'
            managed = state / 'managed-install'
            managed.mkdir(parents=True, mode=0o700)
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(sia.sialib, 'STATE', str(state)))
                stack.enter_context(mock.patch.object(sia.sialib, 'CORPUS', str(corpus)))
                stack.enter_context(mock.patch.object(sia.sialib, 'load_memo', return_value={}))
                stack.enter_context(mock.patch.object(epochs, 'readmit_epoch',
                                                       return_value={'status': 'absent'}))
                original = sia._corpus_root_identity()
                receipt = managed / 'corpus'
                receipt.write_text('managed-by=khephri.sia\nkind=corpus-v2\npath='
                                   + str(corpus) + '\nroot=' + original + '\n')
                receipt.chmod(0o600)
                assert sia._btrfs_readmit(enroll=True)['status'] == 'enrolled'
                binding = sia._btrfs_directory_identity(str(corpus))
                unmount_image()
                mount_image('subvol=primary')
                current = sia._corpus_root_identity()
                assert sia._btrfs_directory_identity(str(corpus)) == binding
                observed = sia._btrfs_readmit(enroll=False)
                assert observed['status'] == ('bound' if current == original else 'readmitted')
                assert sia._corpus_receipt_readmit(False)['status'] == 'bound'
                print('real btrfs remount:', original, '->', current, observed['status'])
                unmount_image()
                mount_image('subvol=replacement')
                corpus.mkdir(mode=0o700)
                previous = receipt.read_bytes()
                try:
                    sia._btrfs_readmit(enroll=False)
                except ValueError:
                    pass
                else:
                    raise AssertionError('replacement subvolume was readmitted')
                assert receipt.read_bytes() == previous
                print('replacement btrfs subvolume refused; receipt preserved')
        finally:
            if mounted:
                unmount_image()


if __name__ == '__main__':
    main()
