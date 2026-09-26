#!/usr/bin/env python3
"""Host inotify + real-shell regressions; not Android rendering validation."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
spec = importlib.util.spec_from_file_location('font_watch', ROOT / 'common/google_font_watch_wait.py')
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


class EventTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.module = self.root / 'module'
        (self.module / 'config').mkdir(parents=True)
        self.fonts = self.root / 'fonts'
        self.fonts.mkdir()
        self.proc = self.root / 'proc'
        self.proc.mkdir()
        self.event = watch.EventWait()
        self.addCleanup(self.event.close)

    def pid(self, number, start, namespace='mnt:[41]', name='com.android.chrome'):
        path = self.proc / str(number)
        (path / 'ns').mkdir(parents=True, exist_ok=True)
        (path / 'stat').write_text(f'{number} (test process) S ' + '0 ' * 18 + str(start) + ' 0\n')
        (path / 'cmdline').write_bytes(name.encode() + b'\0')
        link = path / 'ns/mnt'
        link.unlink(missing_ok=True)
        link.symlink_to(namespace)

    def test_real_close_write_wakes_without_font_parsing(self):
        self.event.tree(self.fonts)
        (self.fonts / 'opaque-cache').write_bytes(b'not a font; notification only')
        self.assertTrue(self.event.changed())

    def test_atomic_replacement_wakes(self):
        target = self.fonts / 'cached'
        target.write_bytes(b'before')
        temp = self.root / 'new'
        temp.write_bytes(b'after')
        self.event.tree(self.fonts)
        os.replace(temp, target)
        self.assertTrue(self.event.changed())
        self.assertEqual(target.read_bytes(), b'after')

    def test_existing_nested_cache_is_watched(self):
        nested = self.fonts / 'one/two'
        nested.mkdir(parents=True)
        self.event.tree(self.fonts)
        (nested / '400').write_text('download')
        self.assertTrue(self.event.changed())

    def test_missing_fonts_directory_creation_wakes(self):
        missing = self.root / 'package/files/fonts'
        self.event.tree(missing)
        (self.root / 'package').mkdir()
        self.assertTrue(self.event.changed())

    def test_directory_replacement_wakes(self):
        self.event.tree(self.fonts)
        self.fonts.rename(self.root / 'old')
        self.fonts.mkdir()
        self.assertTrue(self.event.changed())

    def test_own_journal_writes_do_not_wake(self):
        with patch.dict(os.environ, {'LUOSHU_GOOGLE_FONT_WATCH_ROOTS': str(self.fonts)}):
            watch.configure(self.event, self.module)
        (self.module / 'config/google-font-provider-mounts.conf').write_text('journal')
        self.assertFalse(self.event.changed())
        (self.module / 'config/active_font.conf').write_text('custom')
        self.assertTrue(self.event.changed())

    def test_inventory_dynamic_target_is_watched_without_scanning_its_directory(self):
        aliases = self.root / 'system/fonts'
        aliases.mkdir(parents=True)
        target = self.fonts / 'unbranded-active-font'
        target.write_text('notification fixture')
        alias = aliases / 'BodyAlias.ttf'
        alias.symlink_to(target)
        inventory = {'schema': 'device-font-inventory-v1', 'state': 'ready',
                     'sourceRoots': [{'logical': str(aliases)}],
                     'dynamicFontRoutes': [{'alias': str(alias), 'target': str(target)}]}
        (self.module / 'config/device_font_inventory.json').write_text(json.dumps(inventory))
        with patch.dict(os.environ, {}, clear=True):
            watch.configure(self.event, self.module)
        (self.fonts / 'unrelated-private-file').write_text('ignore')
        self.assertFalse(self.event.changed())
        target.write_text('changed font generation')
        self.assertTrue(self.event.changed())

    def test_disable_and_remove_are_observed(self):
        with patch.dict(os.environ, {'LUOSHU_GOOGLE_FONT_WATCH_ROOTS': ''}):
            watch.configure(self.event, self.module)
        (self.module / 'disable').touch()
        self.assertTrue(self.event.changed())
        (self.module / 'remove').touch()
        self.assertTrue(self.event.changed())

    def test_symlink_subdirectory_is_not_traversed(self):
        other = self.root / 'unrelated'
        other.mkdir()
        (self.fonts / 'escape').symlink_to(other, target_is_directory=True)
        self.event.tree(self.fonts)
        (other / 'private').write_text('untouched')
        self.assertFalse(self.event.changed())

    def test_overflow_requests_reconciliation(self):
        raw = watch.HEADER.pack(-1, watch.OVERFLOW, 0, 0)
        with patch.object(watch.os, 'read', return_value=raw):
            self.assertTrue(self.event.changed())

    def test_new_consumer_in_existing_namespace_is_visible(self):
        self.pid(10, 100, name='zygote64')
        processes = watch.ProcessView(self.proc)
        before = processes.snapshot()
        self.pid(20, 200)
        self.assertNotEqual(processes.snapshot(), before)

    def test_pid_reuse_and_namespace_recreation_are_visible(self):
        self.pid(20, 200)
        processes = watch.ProcessView(self.proc)
        before = processes.snapshot()
        self.pid(20, 300)
        after = processes.snapshot()
        self.assertNotEqual(before, after)
        self.pid(20, 300, namespace='mnt:[99]')
        self.assertNotEqual(after, processes.snapshot())

    def test_unrelated_process_does_not_wake_font_repair(self):
        self.pid(10, 100, name='zygote64')
        processes = watch.ProcessView(self.proc)
        before = processes.snapshot()
        self.pid(30, 300, name='example.unrelated')
        self.assertEqual(before, processes.snapshot())

    def test_deadline_is_bounded_and_does_not_create_module_files(self):
        before = set(self.module.rglob('*'))
        with patch.dict(os.environ, {'LUOSHU_GOOGLE_FONT_WATCH_ROOTS': ''}):
            result = watch.wait(self.module, 0.03, self.proc, tick=0.01)
        self.assertEqual(result, 2)
        self.assertEqual(set(self.module.rglob('*')), before)

    def test_invalid_invocation_fails_without_busy_loop(self):
        import sys
        result = subprocess.run([sys.executable, str(ROOT / 'common/google_font_watch_wait.py'),
                                 str(self.root / 'missing'), '30'], timeout=3)
        self.assertEqual(result.returncode, 3)


class FingerprintTest(unittest.TestCase):
    setUp = EventTest.setUp
    pid = EventTest.pid
    # Use the real bridge and its proc discovery, never mock its fingerprint.
    def fingerprint(self):
        bridge = Path(os.environ.get('LUOSHU_BRIDGE_UNDER_TEST', ROOT / 'common/google_font_provider_bridge.sh'))
        bin_dir = self.root / 'bin'
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / 'pidof').write_text('#!/bin/sh\nexit 1\n')
        (bin_dir / 'pidof').chmod(0o755)
        target = self.fonts / 'google'
        if not target.exists():
            target.write_bytes(b'x' * 2048)
        env = dict(os.environ, MODDIR=str(self.module), LUOSHU_PROC_ROOT=str(self.proc),
                   LUOSHU_GOOGLE_FONT_TARGETS=str(target), PATH=f'{bin_dir}:' + os.environ['PATH'])
        result = subprocess.run(['sh', str(bridge), 'fingerprint'], env=env, check=True,
                                capture_output=True, text=True, timeout=5)
        return result.stdout.strip()

    def test_shell_fingerprint_tracks_shared_namespace_consumers(self):
        self.pid(10, 100, name='zygote64')
        before = self.fingerprint()
        self.assertEqual(self.fingerprint(), before)
        self.pid(20, 200)
        self.assertNotEqual(self.fingerprint(), before)

    def test_shell_fingerprint_tracks_same_pid_new_starttime(self):
        self.pid(10, 100, name='zygote64')
        self.pid(20, 200)
        before = self.fingerprint()
        self.pid(20, 300)
        self.assertNotEqual(self.fingerprint(), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
