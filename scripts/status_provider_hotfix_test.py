#!/usr/bin/env python3
"""Exercise real shell entrypoints without a phone or root daemon."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HotfixTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.common = self.module / 'common'
        self.common.mkdir(parents=True)
        (self.module / 'config').mkdir()
        (self.module / 'module.prop').write_text('id=LuoShu\nversion=test\nversionCode=1\n')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.env = {**os.environ, 'MODDIR': str(self.module), 'MODULE_DIR': str(self.module),
                    'PATH': f'{self.bin}:{os.environ["PATH"]}',
                    'LUOSHU_PUBLIC_DIR': str(self.root / 'public'), 'TEST_ROOT': str(self.root)}

    def command(self, name, content):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + content)
        path.chmod(0o755)

    def copy(self, name):
        target = self.common / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'common' / name, target)
        return target

    def run_shell(self, path, *args):
        return subprocess.run(['sh', str(path), *args], env=self.env,
                              capture_output=True, text=True, check=True, timeout=3).stdout

    def test_mix_reconcile_never_rewrites_live_runtime_or_payload(self):
        self.copy('legacy_v14_4/mix_router.sh')
        self.run_shell(self.common / 'legacy_v14_4/mix_router.sh', 'reconcile')
        self.assertFalse((self.module / '.legacy-v14-runtime').exists())
        self.assertFalse((self.module / '.luoshu-payload').exists())

    def test_weight_read_does_not_migrate_fonts_and_queries_settings_once(self):
        for name in ('font_manager_v4.sh', 'util_functions.sh', 'util_functions_core.sh'):
            self.copy(name)
        legacy = self.root / 'legacy'
        legacy.mkdir()
        (legacy / 'Large-Regular.ttf').write_bytes(b'old-user-font')
        self.env['LEGACY_FONTS_DIR'] = str(legacy)
        self.command('settings', 'echo call >> "$TEST_ROOT/settings-calls"\necho 50\n')
        result = json.loads(self.run_shell(self.common / 'font_manager_v4.sh', 'action', 'font_weight_status'))
        self.assertEqual(result['data']['weight'], 450)
        self.assertEqual((self.root / 'settings-calls').read_text().splitlines(), ['call'])
        self.assertFalse((self.root / 'public').exists(), 'status migrated public fonts')

    def test_weight_write_targets_current_user_and_verifies_readback(self):
        for name in ('font_manager_v4.sh', 'util_functions.sh', 'util_functions_core.sh'):
            self.copy(name)
        self.command('settings', r'''
echo "$*" >> "$TEST_ROOT/settings-args"
if [ "$1" = "--user" ] && [ "$2" = "current" ]; then
    shift 2
else
    exit 9
fi
case "$1:$2" in
    get:secure)
        cat "$TEST_ROOT/weight-state" 2>/dev/null || echo 0
        ;;
    put:secure)
        printf '%s\n' "$4" > "$TEST_ROOT/weight-state"
        ;;
    *) exit 8 ;;
esac
''')
        self.command('am', 'exit 0\n')
        applied = json.loads(self.run_shell(
            self.common / 'font_manager_v4.sh', 'action', 'font_weight_set', '520'
        ))
        self.assertEqual(applied['status'], 'ok')
        self.assertEqual((self.root / 'weight-state').read_text().strip(), '120')
        calls = (self.root / 'settings-args').read_text().splitlines()
        self.assertTrue(calls)
        self.assertTrue(all(line.startswith('--user current ') for line in calls), calls)

        reset = json.loads(self.run_shell(
            self.common / 'font_manager_v4.sh', 'action', 'font_weight_reset'
        ))
        self.assertEqual(reset['status'], 'ok')
        self.assertEqual((self.root / 'weight-state').read_text().strip(), '0')
        calls = (self.root / 'settings-args').read_text().splitlines()
        self.assertTrue(all(line.startswith('--user current ') for line in calls), calls)

    def test_status_does_not_start_deep_verifier_or_root_manager_daemon(self):
        self.copy('font_boot_state.sh')
        self.copy('app_bridge.sh')
        config = self.module / 'config'
        (config / 'active_font.conf').write_text('fixture\n')
        (config / 'text_reboot_required.conf').write_text('bootId=previous-boot\n')
        (config / 'font-payload-boot.conf').write_text('state=booting\n')
        (self.common / 'device_font_load_verify.sh').write_text(
            'case "$1" in verify|deep) touch "$TEST_ROOT/deep-verify" ;; '
            'status) touch "$TEST_ROOT/lightweight-status" ;; esac\nexit 2\n')
        self.command('ksud', 'touch "$TEST_ROOT/daemon"\n')
        self.command('getprop', 'echo test\n')
        result = json.loads(self.run_shell(self.common / 'app_bridge.sh', 'status'))
        self.assertTrue(result['data']['installed'])
        self.assertTrue(result['data']['rebootRequired'], 'unverified state must remain pending')
        self.assertFalse((self.root / 'deep-verify').exists())
        self.assertTrue((self.root / 'lightweight-status').exists())
        self.assertFalse((self.root / 'daemon').exists())

    def test_provider_watch_includes_chrome_consumers_but_not_shell_arguments(self):
        proc = self.root / 'proc'
        for pid, command in {11: 'com.android.chrome', 12: 'com.android.chrome:privileged_process0',
                             13: 'com.google.android.gm', 14: 'com.google.android.gms',
                             15: 'sh\0-c\0echo com.google.android.gms', 16: 'unrelated.app'}.items():
            directory = proc / str(pid)
            directory.mkdir(parents=True)
            (directory / 'cmdline').write_bytes(command.encode() + b'\0')
        self.command('pidof', 'exit 1\n')
        self.env['LUOSHU_PROC_ROOT'] = str(proc)
        out = subprocess.run(['sh', '-c', '. "$1"; _gfp_namespace_pids', 'sh',
                              str(ROOT / 'common/google_font_provider_bridge.sh')],
                             env=self.env, text=True, capture_output=True, check=True, timeout=3)
        self.assertEqual(set(out.stdout.split()), {'11', '12', '13', '14'})


if __name__ == '__main__':
    unittest.main()
