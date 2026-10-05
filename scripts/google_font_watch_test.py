#!/usr/bin/env python3
"""The retired compatibility entry never observes or waits for font changes."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from google_font_provider_lifecycle_test import install_support

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('font_watch', ROOT / 'common/google_font_watch_wait.py')
WATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WATCH)


class RetiredWatchTest(unittest.TestCase):
    def test_entry_has_no_inotify_process_scan_or_background_dependency(self):
        with patch('os.scandir', side_effect=AssertionError('unexpected process scan')), \
             patch('time.sleep', side_effect=AssertionError('unexpected wait')):
            self.assertEqual(WATCH.main(), 2)
        self.assertFalse(hasattr(WATCH, 'EventWait'))
        self.assertFalse(hasattr(WATCH, 'ProcessView'))

    def test_old_maximum_wait_invocation_exits_immediately_without_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            module = Path(temporary)
            started = time.monotonic()
            result = subprocess.run([sys.executable, str(ROOT / 'common/google_font_watch_wait.py'),
                                     str(module), '300'], capture_output=True, timeout=2)
            self.assertEqual(result.returncode, 2)
            self.assertLess(time.monotonic() - started, 1.5)
            self.assertEqual(result.stdout, b'')
            self.assertEqual(result.stderr, b'')
            self.assertEqual(list(module.iterdir()), [])

    def test_missing_or_invalid_arguments_still_have_no_waiter(self):
        for arguments in ([], ['/missing/module', '300'], ['/missing/module', 'invalid']):
            with self.subTest(arguments=arguments):
                result = subprocess.run([sys.executable, str(ROOT / 'common/google_font_watch_wait.py'),
                                         *arguments], capture_output=True, timeout=2)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b'')


class ExplicitFingerprintTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='provider-fingerprint-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        install_support(self.module)
        self.proc = self.root / 'proc'
        self.proc.mkdir()
        self.font = self.root / 'downloaded-font'
        self.font.write_bytes(b'x' * 2048)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        (self.bin / 'pidof').write_text('#!/bin/sh\nexit 1\n')
        (self.bin / 'pidof').chmod(0o755)

    def pid(self, number, start, namespace='mnt:[41]', name='com.android.chrome'):
        path = self.proc / str(number)
        (path / 'ns').mkdir(parents=True, exist_ok=True)
        (path / 'stat').write_text(f'{number} (test process) S ' + '0 ' * 18 + str(start) + ' 0\n')
        (path / 'cmdline').write_bytes(name.encode() + b'\0')
        link = path / 'ns/mnt'
        link.unlink(missing_ok=True)
        link.symlink_to(namespace)

    def fingerprint(self):
        env = dict(os.environ, MODDIR=str(self.module), LUOSHU_PROC_ROOT=str(self.proc),
                   LUOSHU_GOOGLE_FONT_TARGETS=str(self.font), LUOSHU_TASK_SCOPE_PYTHON=sys.executable,
                   LUOSHU_RUNTIME_PATHS_PYTHON=sys.executable, PATH=f'{self.bin}:' + os.environ['PATH'])
        result = subprocess.run(['sh', str(ROOT / 'common/google_font_provider_bridge.sh'), 'fingerprint'],
                                env=env, check=True, capture_output=True, text=True, timeout=5)
        self.assertRegex(result.stdout, r'^[a-f0-9]{64}\n$')
        self.assertEqual(list((self.module / '.luoshu-state/tmp').iterdir()), [])
        return result.stdout

    def test_one_snapshot_tracks_shared_namespace_consumers_and_pid_reuse(self):
        self.pid(10, 100, name='zygote64')
        before = self.fingerprint()
        self.assertEqual(self.fingerprint(), before)
        self.pid(20, 200)
        shared = self.fingerprint()
        self.assertNotEqual(shared, before)
        self.pid(20, 300)
        self.assertNotEqual(self.fingerprint(), shared)

    def test_one_snapshot_tracks_cache_replacement_without_observing_unrelated_apps(self):
        self.pid(10, 100, name='zygote64')
        before = self.fingerprint()
        self.pid(30, 300, name='example.unrelated')
        self.assertEqual(self.fingerprint(), before)
        replacement = self.font.with_suffix('.new')
        replacement.write_bytes(self.font.read_bytes())
        os.replace(replacement, self.font)
        self.assertNotEqual(self.fingerprint(), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
