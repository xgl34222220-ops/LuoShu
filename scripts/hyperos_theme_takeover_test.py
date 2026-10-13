#!/usr/bin/env python3
"""Optional HyperOS theme-store font takeover, the v4 early-boot route hook and
the App's HyperOS coverage bridge.

Mounts use the same PATH shims as hyperos_webview_route_test (hardlink the
clone in place, keep the original aside), so inode ownership is real.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from hyperos_cjk_routing_test import make_font  # noqa: E402
from hyperos_webview_route_test import MOUNT_SHIM, UMOUNT_SHIM  # noqa: E402

SCRIPT = ROOT / 'common/hyperos_theme_takeover.sh'


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        (self.module / 'config').mkdir(parents=True)
        (self.module / 'common').symlink_to(ROOT / 'common', target_is_directory=True)
        (self.module / 'module.prop').write_text('id=LuoShu\n')
        (self.module / 'config/active_font.conf').write_text('safe-test\n')
        fonts = self.module / '.luoshu-payload/system/fonts'
        (fonts / '.luoshu-font-store').mkdir(parents=True)
        make_font(fonts / '.luoshu-font-store/regular.font', points=(*range(32, 127), 0x4E2D))
        make_font(fonts / '.luoshu-font-store/wght-700.font', points=(*range(32, 127), 0x4E2E))
        self.regular = (fonts / '.luoshu-font-store/regular.font').read_bytes()
        self.bold = (fonts / '.luoshu-font-store/wght-700.font').read_bytes()
        self.theme = self.root / 'data/system/theme/fonts'
        self.theme.mkdir(parents=True)
        self.mountinfo = self.root / 'mountinfo'
        self.mountinfo.write_text('1 0 0:0 / / rw - rootfs rootfs rw\n')
        self.boot = self.root / 'boot_id'
        self.boot.write_text('boot-a\n')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.command('mount', MOUNT_SHIM)
        self.command('umount', UMOUNT_SHIM)
        self.command('chcon', '#!/bin/sh\nexit 0\n')
        self.command('getprop', '#!/bin/sh\n[ "$1" = ro.mi.os.version.name ] && echo OS3.0\n')
        self.env = {**os.environ, 'MODDIR': str(self.module), 'LUOSHU_REAL_MODDIR': str(self.module),
                    'TEST_ROOT': str(self.root), 'PATH': f'{self.bin}:{os.environ["PATH"]}',
                    'LUOSHU_THEME_TAKEOVER_DIR': str(self.theme),
                    'LUOSHU_THEME_TAKEOVER_MOUNTINFO': str(self.mountinfo),
                    'LUOSHU_THEME_TAKEOVER_BOOT_ID': str(self.boot)}

    def command(self, name, body):
        path = self.bin / name
        path.write_text(body)
        path.chmod(0o755)

    def run_sh(self, *args, **extra):
        return subprocess.run(['sh', str(SCRIPT), *args], env={**self.env, **extra},
                              capture_output=True, text=True, timeout=30)

    def user_theme(self):
        # A theme-store font: CJK-sized regular + bold, plus a TTC that must stay.
        make_font(self.theme / 'Roboto-Regular.ttf', points=tuple(range(32, 127)))
        with open(self.theme / 'Roboto-Regular.ttf', 'ab') as handle:
            handle.write(b'\0' * 200000)
        make_font(self.theme / 'Roboto-Bold.ttf', points=tuple(range(32, 127)))
        with open(self.theme / 'Roboto-Bold.ttf', 'ab') as handle:
            handle.write(b'\0' * 200000)
        (self.theme / 'Theme.ttc').write_bytes(b'ttcf' + b'\0' * 70000)
        return {p.name: p.read_bytes() for p in self.theme.iterdir()}

    def enable(self, value='1'):
        (self.module / 'config/hyperos_theme_takeover.conf').write_text(f'enabled={value}\n')

    def status(self):
        out = self.run_sh('status').stdout
        return dict(line.split('=', 1) for line in out.splitlines() if '=' in line)



class ThemeTakeoverTest(_Fixture):
    def test_detection_without_takeover_changes_nothing(self):
        self.assertEqual(self.status()['state'], 'none')
        (self.theme / 'Roboto-Regular.ttf').write_bytes(b'\0\1\0\0' + b'x' * 9000)
        self.assertEqual(self.status()['state'], 'placeholder')
        original = self.user_theme()
        status = self.status()
        self.assertEqual((status['state'], status['takeover'], status['owned']), ('user-theme', '0', '0'))
        self.assertEqual(self.run_sh('ensure').returncode, 2)
        self.assertFalse((self.root / 'mount.log').exists())
        self.assertEqual({p.name: p.read_bytes() for p in self.theme.iterdir()}, original)

    def test_takeover_binds_every_single_font_by_weight_and_restores_exactly(self):
        original = self.user_theme()
        self.enable()
        result = self.run_sh('ensure')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.theme / 'Roboto-Regular.ttf').read_bytes(), self.regular)
        self.assertEqual((self.theme / 'Roboto-Bold.ttf').read_bytes(), self.bold)
        # A collection cannot take a single face; it keeps the theme font.
        self.assertEqual((self.theme / 'Theme.ttc').read_bytes(), original['Theme.ttc'])
        self.assertEqual(self.status()['owned'], '1')
        self.assertIn('ro ', (self.root / 'ro.log').read_text())
        # Idempotent within the boot.
        self.assertEqual(self.run_sh('ensure').returncode, 0)
        self.assertEqual(self.mountinfo.read_text().count('Roboto-Regular.ttf'), 1)
        self.assertEqual(self.run_sh('restore').returncode, 0)
        self.assertEqual({p.name: p.read_bytes() for p in self.theme.iterdir()}, original)
        self.assertFalse((self.module / 'config/hyperos-theme-takeover.journal').exists())

    def test_disable_default_font_or_turning_off_restores(self):
        original = self.user_theme()
        self.enable()
        self.assertEqual(self.run_sh('ensure').returncode, 0)
        self.enable('0')
        self.assertEqual(self.run_sh('ensure').returncode, 2)
        self.assertEqual({p.name: p.read_bytes() for p in self.theme.iterdir()}, original)
        self.enable()
        self.assertEqual(self.run_sh('ensure').returncode, 0)
        (self.module / 'config/active_font.conf').write_text('default\n')
        self.run_sh('ensure')
        self.assertEqual({p.name: p.read_bytes() for p in self.theme.iterdir()}, original)

    def test_stale_journal_from_earlier_boot_never_unmounts(self):
        original = self.user_theme()
        self.enable()
        self.assertEqual(self.run_sh('ensure').returncode, 0)
        self.boot.write_text('boot-b\n')
        # New boot: the old journal is discarded; restore must not pop anything.
        self.assertEqual(self.run_sh('restore').returncode, 0)
        self.assertNotIn('umount', (self.root / 'mount.log').read_text())
        self.assertNotEqual((self.theme / 'Roboto-Regular.ttf').read_bytes(), original['Roboto-Regular.ttf'])

    def test_foreign_mount_on_target_is_left_alone(self):
        self.user_theme()
        self.enable()
        target = self.theme / 'Roboto-Regular.ttf'
        with open(self.mountinfo, 'a') as handle:
            handle.write(f'9 1 0:0 / {target} ro - bind none ro\n')
        self.run_sh('ensure')
        self.assertIn('target-already-mounted-by-other',
                      (self.module / 'logs/fontswitch.log').read_text())
        self.assertNotIn(f'--bind', ''.join(line for line in (self.root / 'mount.log').read_text().splitlines()
                                            if line.endswith('Roboto-Regular.ttf')))

    def test_uninstall_and_provider_restore_know_the_takeover(self):
        self.assertIn('hyperos_theme_takeover.sh', (ROOT / 'uninstall.sh').read_text())
        self.assertIn('hyperos_theme_takeover.sh restore',
                      (ROOT / 'common/google_font_provider_service.sh').read_text().replace(
                          '"$MODDIR/common/hyperos_theme_takeover.sh" restore', 'hyperos_theme_takeover.sh restore'))
        bridge = (ROOT / 'common/hyperos_theme_font_bridge.sh').read_text()
        self.assertIn('hyperos_theme_takeover.sh" owned', bridge)


class BootRoutesTest(_Fixture):
    """common/util_functions.sh -> hyperos_boot_routes.sh runs only on the v4 route."""

    def run_routes(self, **extra):
        script = f'. "{ROOT}/common/hyperos_boot_routes.sh"; luoshu_hyperos_boot_routes_ensure'
        return subprocess.run(['sh', '-c', script], env={**self.env, **extra},
                              capture_output=True, text=True, timeout=30)

    def test_v4_route_runs_takeover_and_legacy_route_skips(self):
        original = self.user_theme()
        self.enable()
        (self.module / 'config/font_runtime_legacy_v14_4.conf').write_text('1\n')
        self.run_routes(LUOSHU_WEBVIEW_ROUTE_ALIAS=str(self.root / 'absent'))
        self.assertEqual({p.name: p.read_bytes() for p in self.theme.iterdir()}, original)
        (self.module / 'config/font_runtime_legacy_v14_4.conf').unlink()
        self.run_routes(LUOSHU_WEBVIEW_ROUTE_ALIAS=str(self.root / 'absent'))
        self.assertEqual((self.theme / 'Roboto-Regular.ttf').read_bytes(), self.regular)

    def test_non_hyperos_rom_is_untouched(self):
        original = self.user_theme()
        self.enable()
        self.command('getprop', '#!/bin/sh\nexit 0\n')
        self.run_routes(LUOSHU_WEBVIEW_ROUTE_ALIAS=str(self.root / 'absent'))
        self.assertEqual({p.name: p.read_bytes() for p in self.theme.iterdir()}, original)

    def test_util_functions_hooks_post_fs_data_only(self):
        text = (ROOT / 'common/util_functions.sh').read_text()
        hook = text.split('# v4 runtime only: HyperOS MiSansVF_Overlay route', 1)[1]
        self.assertIn('post-fs-data.sh)', hook.split('esac', 1)[0])
        self.assertIn('luoshu_hyperos_boot_routes_ensure', hook)

    def test_webview_route_falls_back_to_v4_font_store(self):
        text = (ROOT / 'common/hyperos_webview_route.sh').read_text()
        self.assertIn('_lwr_default_payload', text)
        out = subprocess.run(['sh', '-c', f'. "{ROOT}/common/hyperos_webview_route.sh"; '
                              f'_lwr_default_payload "{self.module}/.luoshu-payload/system/fonts"'],
                             env=self.env, capture_output=True, text=True).stdout.strip()
        self.assertTrue(out.endswith('.luoshu-font-store/regular.font'), out)


class CoverageBridgeTest(_Fixture):
    def bridge(self, *args, **extra):
        out = subprocess.run(['sh', str(ROOT / 'common/hyperos_coverage_bridge.sh'), *args],
                             env={**self.env, 'IS_HYPEROS': 'true', **extra},
                             capture_output=True, text=True, timeout=30).stdout
        return json.loads(out)

    def test_status_defaults_and_settings_round_trip(self):
        data = self.bridge('status')['data']
        self.assertEqual(data['groups'], {'miui_ex': True, 'misans_ext': True, 'lockscreen_styles': False})
        self.assertTrue(data['sourceXml'])
        self.assertEqual(data['theme']['state'], 'none')
        self.assertFalse(data['theme']['takeover'])
        result = self.bridge('set', 'group:lockscreen_styles', '1')['data']
        self.assertTrue(result['needsReapply'])
        self.bridge('set', 'group:miui_ex', '0')
        self.bridge('set', 'xml', '0')
        self.bridge('set', 'theme_takeover', '1')
        self.user_theme()
        data = self.bridge('status')['data']
        self.assertEqual(data['groups'], {'miui_ex': False, 'misans_ext': True, 'lockscreen_styles': True})
        self.assertFalse(data['sourceXml'])
        self.assertEqual((data['theme']['state'], data['theme']['takeover']), ('user-theme', True))
        # The Python policy reads the very file the App wrote.
        sys.path.insert(0, str(ROOT / 'common'))
        import hyperos_physical_policy as policy
        self.assertEqual(policy.enabled_groups(self.module / 'config/hyperos_slot_groups.conf'),
                         frozenset({'misans_ext', 'lockscreen_styles'}))
        self.assertEqual(self.bridge('set', 'nope', '1')['status'], 'error')
        self.assertEqual(self.bridge('set', 'xml', '2')['status'], 'error')

    def test_locate_validates_package_and_runs_helper(self):
        self.assertEqual(self.bridge('locate', 'bad pkg;id')['status'], 'error')
        self.assertEqual(self.bridge('locate', '../x')['status'], 'error')
        data = self.bridge('locate', 'com.android.systemui', LUOSHU_COVERAGE_PYTHON=sys.executable,
                           LUOSHU_COVERAGE_PID='', LUOSHU_COVERAGE_THEME_DIR=str(self.theme))
        self.assertEqual(data['status'], 'ok', data)
        self.assertEqual(data['data']['verdict'], 'not-running')

    def test_app_bridge_dispatches_coverage_commands(self):
        text = (ROOT / 'common/app_bridge.sh').read_text()
        for command in ('hyperos_coverage_status', 'hyperos_coverage_set', 'coverage_locate'):
            self.assertIn(command, text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
