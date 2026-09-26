#!/usr/bin/env python3
"""All public mutation APIs share the inventory/next-boot switch transaction."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FontMutationEntryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.common = self.module / 'common'
        self.common.mkdir(parents=True)
        self.config = self.module / 'config'
        self.config.mkdir()
        (self.module / 'logs').mkdir()
        self.public = self.root / 'public'
        (self.public / 'fonts').mkdir(parents=True)
        self.source = self.public / 'fonts/Demo-Regular.ttf'
        self.source.write_bytes(b'user-font-source')
        self.live = self.module / '.luoshu-payload/system/fonts/DeviceActual.otf'
        self.live.parent.mkdir(parents=True)
        self.live.write_bytes(b'pinned-live-font')
        (self.config / 'active_font.conf').write_text('Demo\n')
        for name in ('font_manager.sh', 'font_manager_v4.sh', 'legacy_v14_4_switch.sh',
                     'font_switch_lock.sh'):
            shutil.copy(ROOT / 'common' / name, self.common / name)
        legacy = self.common / 'legacy_v14_4'
        legacy.mkdir()
        for name in ('font_switch_safe.sh', 'payload_clone.sh'):
            shutil.copy(ROOT / 'common/legacy_v14_4' / name, legacy / name)
        self.safe = legacy / 'font_switch_safe.sh'
        (self.common / 'util_functions.sh').write_text('''detect_font_family() { printf '%s\\n' "${1%-Regular.ttf}"; }
''')
        # Any use of the old ROM mapper during these API requests is an error.
        (self.common / 'rom_adapters.sh').write_text('exit 91\n')
        (self.common / 'font_config_runtime.sh').write_text('exit 92\n')
        self.env = dict(os.environ, MODDIR=str(self.module), LUOSHU_PUBLIC_DIR=str(self.public))

    def command(self, name, *args, success=True):
        result = subprocess.run(['sh', str(self.common / name), *args], env=self.env,
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        self.assertEqual(self.live.read_bytes(), b'pinned-live-font')
        return result

    def test_delete_active_font_queues_default_and_keeps_live_bytes(self):
        result = self.command('font_manager.sh', 'action', 'delete', 'Demo')
        data = json.loads(result.stdout)
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['data']['deleted'], 1)
        self.assertFalse(self.source.exists())
        self.assertIn('font=default\n', (self.config / 'font-payload-next.conf').read_text())
        self.assertTrue((self.module / '.luoshu-payload-next').is_dir())

    def test_delete_keeps_source_if_default_cannot_be_prepared(self):
        self.safe.write_text('printf \'{"status":"error","message":"stage failed"}\\n\'\nexit 1\n')
        result = self.command('font_manager.sh', 'action', 'delete', 'Demo')
        self.assertEqual(json.loads(result.stdout)['status'], 'error')
        self.assertTrue(self.source.exists())
        self.assertFalse((self.module / '.luoshu-payload-next').exists())

    def test_compatibility_switch_entries_use_real_safe_default(self):
        for name in ('legacy_v14_4_switch.sh', 'font_manager_v4.sh'):
            result = self.command(name, 'action', 'switch', 'default')
            self.assertEqual(json.loads(result.stdout)['data']['pipeline'], 'next-boot-stage')
            self.assertTrue(self.source.exists())

    def test_missing_safe_core_never_runs_old_fallback(self):
        self.safe.unlink()
        (self.common / 'legacy_v14_4_switch.sh').write_text('touch "$MODDIR/old-fallback-ran"\n')
        for name in ('font_manager.sh', 'font_manager_v4.sh'):
            result = self.command(name, 'action', 'switch', 'default', success=False)
            self.assertEqual(json.loads(result.stdout)['status'], 'error')
            self.assertFalse((self.module / 'old-fallback-ran').exists())
        self.assertTrue(self.source.exists())

    def test_old_async_and_status_apis_forward_arguments_before_loading_helpers(self):
        (self.common / 'util_functions.sh').write_text('exit 93\n')
        (self.common / 'font_switch_task.sh').write_text('printf "%s\\n" "$1" "$2"\n')
        for name in ('font_manager.sh', 'font_manager_v4.sh'):
            for action, forwarded in (('switch_async', 'start'), ('switch_status', 'status')):
                result = self.command(name, 'action', action, '字体 A')
                self.assertEqual(result.stdout, forwarded + '\n字体 A\n')
        self.assertTrue(self.source.exists())


if __name__ == '__main__':
    unittest.main()
