#!/usr/bin/env python3
"""Exercise real shell entrypoints without a phone or root daemon."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
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
                    'LUOSHU_PUBLIC_DIR': str(self.root / 'public'), 'TEST_ROOT': str(self.root),
                    'LUOSHU_TASK_SCOPE_PYTHON': sys.executable,
                    'LUOSHU_RUNTIME_PATHS_PYTHON': sys.executable}
        for key in ('LUOSHU_TASK_SCOPE_PID', 'LUOSHU_TASK_SCOPE_PIDFILE', 'LUOSHU_TASK_SCOPE_TASK',
                    'LUOSHU_TASK_SCOPE_TMPDIR', 'LUOSHU_REAL_MODDIR', 'LUOSHU_STATE_DIR',
                    'LUOSHU_CONFIG_DIR', 'LUOSHU_LOG_DIR', 'LUOSHU_CACHE_DIR', 'LUOSHU_TASKS_DIR',
                    'LUOSHU_TMP_DIR', 'LUOSHU_BACKUP_DIR', 'LUOSHU_REPORTS_DIR',
                    'LUOSHU_RUNTIME_PATHS_MODULE', 'LUOSHU_SCOPE_ALLOW_HANDOFF', 'LUOSHU_SCOPE_HANDOFF'):
            self.env.pop(key, None)

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
        for name in ('font_next_transaction.sh', 'font_switch_lock.sh', 'task_scope.sh',
                     'task_scope.py', 'runtime_paths.sh', 'runtime_paths_lock.py'):
            self.copy(name)
        self.run_shell(self.common / 'legacy_v14_4/mix_router.sh', 'reconcile')
        self.assertFalse((self.module / '.legacy-v14-runtime').exists())
        self.assertFalse((self.module / '.luoshu-payload').exists())

    def test_retired_weight_actions_are_inert_before_loading_helpers(self):
        for name in ('font_manager_v4.sh', 'font_manager.sh', 'util_functions.sh', 'util_functions_core.sh',
                     'task_scope.sh', 'task_scope.py', 'runtime_paths.sh', 'runtime_paths_lock.py'):
            self.copy(name)
        legacy = self.root / 'legacy'
        legacy.mkdir()
        (legacy / 'Large-Regular.ttf').write_bytes(b'old-user-font')
        self.env['LEGACY_FONTS_DIR'] = str(legacy)
        self.command('settings', 'echo call >> "$TEST_ROOT/settings-calls"\necho 50\n')
        configs = {
            'font_weight.conf': 'weight=500\nadjustment=100\n',
            'font_weight_original.conf': 'adjustment=-25\n',
        }
        for name, content in configs.items():
            (self.module / 'config' / name).write_text(content)
        for manager in ('font_manager_v4.sh', 'font_manager.sh'):
            for action in ('font_weight_status', 'font_weight_set', 'font_weight_reset'):
                with self.subTest(manager=manager, action=action):
                    result = json.loads(self.run_shell(self.common / manager, 'action', action, '500'))
                    self.assertEqual(result['status'], 'error')
                    self.assertIn('已移除', result['message'])
                    self.assertFalse((self.root / 'settings-calls').exists())
                    self.assertFalse((self.root / 'public').exists(), 'retired action migrated public fonts')
                    for name, content in configs.items():
                        self.assertEqual((self.module / 'config' / name).read_text(), content)

    def test_settings_policy_blocks_only_retired_secure_put_and_is_idempotent(self):
        policy = self.copy('font_settings_policy.sh')
        self.command('settings',
                     'printf "call\\n" >> "$TEST_ROOT/settings-calls"\n'
                     'printf "%s\\n" "$@" >> "$TEST_ROOT/settings-arguments"\nexit 7\n')
        blocked = [
            ('put', 'secure', 'font_weight_adjustment', '100'),
            ('--user', 'current', 'put', 'secure', 'font_weight_adjustment', '100'),
            ('--user', '0', 'put', 'secure', 'font_weight_adjustment', '100'),
            ('--user', 'null', 'put', 'secure', 'font_weight_adjustment', '100'),
        ]
        forwarded = [
            (), ('--user',), ('--user', 'null'),
            ('get', 'secure', 'font_weight_adjustment'),
            ('put', 'system', 'font_weight_adjustment', '100'),
            ('put', 'secure', 'font_scale', '1.2'),
            ('--user', '0', 'put', 'secure', 'other_key', 'value with spaces'),
        ]
        for arguments, expected in [(args, 1) for args in blocked] + [(args, 7) for args in forwarded]:
            with self.subTest(arguments=arguments):
                calls = self.root / 'settings-calls'
                recorded = self.root / 'settings-arguments'
                calls.unlink(missing_ok=True)
                recorded.unlink(missing_ok=True)
                result = subprocess.run(
                    ['sh', '-c', '. "$1"; . "$1"; shift; settings "$@"', 'sh', str(policy), *arguments],
                    env=self.env, capture_output=True, text=True, timeout=3)
                self.assertEqual(result.returncode, expected, result.stderr)
                if expected == 1:
                    self.assertFalse(calls.exists())
                    self.assertFalse(recorded.exists())
                else:
                    self.assertEqual(calls.read_text().splitlines(), ['call'])
                    self.assertEqual(recorded.read_text().splitlines(), list(arguments) or [''])

    def test_real_service_routes_never_replay_retired_weight_configuration(self):
        for name in ('util_functions.sh', 'util_functions_core.sh', 'font_settings_policy.sh'):
            self.copy(name)
        shutil.copyfile(ROOT / 'service.sh', self.module / 'service.sh')
        core = self.module / '.luoshu-runtime/core'
        core.mkdir(parents=True)
        shutil.copyfile(ROOT / '.luoshu-runtime/core/service.sh', core / 'service.sh')
        self.command('settings', 'echo call >> "$TEST_ROOT/settings-calls"\n')
        self.command('getprop', 'echo 1\n')
        config = self.module / 'config'
        weight = config / 'font_weight.conf'
        original = config / 'font_weight_original.conf'
        weight.write_text('weight=500\nadjustment=100\n')
        original.write_text('adjustment=-25\n')
        legacy = config / 'font_runtime_legacy_v14_4.conf'
        for route in ('v4', 'physical'):
            with self.subTest(route=route):
                if route == 'physical':
                    legacy.write_text('font=default\n')
                self.run_shell(self.module / 'service.sh')
                self.assertFalse((self.root / 'settings-calls').exists())
                self.assertEqual(weight.read_text(), 'weight=500\nadjustment=100\n')
                self.assertEqual(original.read_text(), 'adjustment=-25\n')
                if route == 'v4':
                    log = (self.module / 'logs/fontswitch.log').read_text()
                    self.assertIn('字体粗细调整恢复失败', log, 'frozen weight replay branch was not exercised')
                    self.assertIn('服务脚本执行完成', log)
                else:
                    self.assertIn('physical compatibility service complete',
                                  (self.module / 'logs/service-legacy-v14.4.log').read_text())

    def test_real_uninstall_never_resets_unowned_or_owned_global_weight(self):
        self.copy('font_settings_policy.sh')
        shutil.copyfile(ROOT / 'uninstall.sh', self.module / 'uninstall.sh')
        compat = self.module / '.luoshu-runtime/compat/v227'
        compat.mkdir(parents=True)
        shutil.copyfile(ROOT / '.luoshu-runtime/compat/v227/uninstall.sh', compat / 'uninstall.sh')
        self.command('settings', 'echo call >> "$TEST_ROOT/settings-calls"\n')
        self.env.update({
            'LUOSHU_MODULES_DIR': str(self.root / 'modules'),
            'LUOSHU_MODULES_UPDATE_DIR': str(self.root / 'modules-update'),
            'LUOSHU_METAMODULE_MNT': str(self.root / 'metamodule'),
            'LUOSHU_MAGIC_MOUNT_CONFIG': str(self.root / 'magic-mount/config.toml'),
            'LUOSHU_SELF_MOUNT_STATE': str(self.root / 'self-mount'),
        })
        original = self.module / 'config/font_weight_original.conf'
        for owned in (False, True):
            with self.subTest(owned=owned):
                if owned:
                    original.write_text('adjustment=-25\n')
                self.run_shell(self.module / 'uninstall.sh')
                self.assertFalse((self.root / 'settings-calls').exists())
                if owned:
                    self.assertEqual(original.read_text(), 'adjustment=-25\n')

    def test_native_app_has_no_retired_global_weight_control_and_policy_is_packaged(self):
        app = ROOT / 'android-app/app/src/main/java'
        for path in app.rglob('*.kt'):
            source = path.read_text()
            for action in ('font_weight_status', 'font_weight_set', 'font_weight_reset'):
                self.assertNotIn(action, source, str(path))
        manifest = (ROOT / 'scripts/module_payload_manifest.txt').read_text().splitlines()
        self.assertIn('common/font_settings_policy.sh', manifest)

    def test_status_does_not_start_deep_verifier_or_root_manager_daemon(self):
        self.copy('font_boot_state.sh')
        self.copy('app_bridge.sh')
        for name in ('task_scope.sh', 'task_scope.py', 'runtime_paths.sh', 'runtime_paths_lock.py'):
            self.copy(name)
        config = self.module / 'config'
        (config / 'active_font.conf').write_text('fixture\n')
        (config / 'text_reboot_required.conf').write_text('bootId=previous-boot\n')
        (config / 'font-payload-boot.conf').write_text('state=booting\n')
        (self.common / 'device_font_load_verify.sh').write_text('touch "$TEST_ROOT/deep-verify"\n')
        self.command('ksud', 'touch "$TEST_ROOT/daemon"\n')
        self.command('getprop', 'echo test\n')
        result = json.loads(self.run_shell(self.common / 'app_bridge.sh', 'status'))
        self.assertTrue(result['data']['installed'])
        self.assertTrue(result['data']['rebootRequired'], 'unverified state must remain pending')
        self.assertFalse((self.root / 'deep-verify').exists())
        self.assertFalse((self.root / 'daemon').exists())
        tasks = self.module / '.luoshu-state/tasks'
        proofs = list(tasks.glob('request-*.pid.cleanup.json'))
        self.assertEqual(len(proofs), 1, proofs)
        proof = json.loads(proofs[0].read_text())
        self.assertTrue(proof['cleaned'], proof)
        self.assertEqual(proof['leftoverPids'], [], proof)
        self.assertEqual(proof['cleanupErrors'], [], proof)
        self.assertEqual(proof['result'], 0, proof)
        for pattern in ('request-*.pid', 'request-*.pid.owner.json', 'request-*.pid.task',
                        'request-*.pid.boot', 'request-*.pid.start'):
            self.assertEqual(list(tasks.glob(pattern)), [], pattern)

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
