#!/usr/bin/env python3
"""Exercise service routing, active provider sources and slow-copy staging."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function(relative, name):
    source = (ROOT / relative).read_text()
    start = source.index(name + '() {')
    return source[start:source.index('\n}', start) + 2]


class SwitchProviderTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        (self.module / 'common').mkdir(parents=True)
        (self.module / 'config').mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.env = {**os.environ, 'MODDIR': str(self.module),
                    'PATH': str(self.bin) + os.pathsep + os.environ['PATH']}

    def executable(self, name, content):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + content)
        path.chmod(0o755)
        return path

    def test_both_service_routes_launch_provider_once(self):
        shutil.copyfile(ROOT / 'service.sh', self.module / 'service.sh')
        (self.module / '.luoshu-runtime/core/service.sh').write_text('exit 0\n')
        marker = self.root / 'provider-starts'
        (self.module / 'common/google_font_provider_service.sh').write_text(
            'printf "started\\n" >> "$TEST_STARTS"\n')
        self.executable('getprop', 'echo 1\n')
        legacy = self.module / 'config/font_runtime_legacy_v14_4.conf'
        for route in ('v4', 'physical'):
            with self.subTest(route=route):
                if route == 'physical':
                    legacy.write_text('font=example\n')
                marker.unlink(missing_ok=True)
                subprocess.run(['sh', str(self.module / 'service.sh')],
                    env={**self.env, 'TEST_STARTS': str(marker)},
                    capture_output=True, timeout=5, check=True)
                deadline = time.monotonic() + 1
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(marker.exists(), 'provider service was never launched')
                self.assertEqual(marker.read_text().splitlines(), ['started'])

    def provider_source(self, weight):
        return subprocess.run(['sh', '-c', '. "$1"; _gfp_source_for_weight "$2"',
            'sh', str(ROOT / 'common/google_font_provider_bridge.sh'), str(weight)],
            env=self.env, capture_output=True, text=True)

    def test_provider_service_recovers_empty_lock_from_previous_boot(self):
        marker = self.root / 'bridge-applied'
        service = self.module / 'common/google_font_provider_service.sh'
        shutil.copyfile(ROOT / 'common/google_font_provider_service.sh', service)
        shutil.copyfile(ROOT / 'common/font_switch_lock.sh', self.module / 'common/font_switch_lock.sh')
        (self.module / 'common/google_font_provider_bridge.sh').write_text(
            'case "$1" in fingerprint) echo unchanged;; '
            'apply) printf "applied\\n" >> "$TEST_APPLIED";; esac\n')
        (self.module / 'config/active_font.conf').write_text('example\n')
        lock = self.module / '.google-font-provider.lock'
        lock.mkdir()
        self.executable('getprop', 'echo 1\n')
        subprocess.run(['sh', str(service)], env={**self.env,
            'TEST_APPLIED': str(marker), 'LUOSHU_FONT_LOCK_INIT_GRACE_SECONDS': '0.01',
            'LUOSHU_GOOGLE_FONT_RETRIES': '1', 'LUOSHU_GOOGLE_FONT_WATCH_CYCLES': '0'},
            capture_output=True, check=True, timeout=5)
        self.assertEqual(marker.read_text().splitlines(), ['applied'])
        self.assertFalse(lock.exists())
        marker.unlink()
        (self.module / 'config/active_font.conf').write_text('default\n')
        # Default now pauses rather than permanently exiting the boot guard.
        # Bound this lock/no-replacement fixture explicitly; the resume suite
        # exercises default -> custom and cancellation of the live watcher.
        subprocess.run(['sh', str(service)], env={**self.env,
            'TEST_APPLIED': str(marker), 'LUOSHU_GOOGLE_FONT_RETRIES': '1',
            'LUOSHU_GOOGLE_FONT_WATCH_CYCLES': '0'}, check=True, timeout=5)
        self.assertFalse(marker.exists(), 'default font must not run provider replacement')
        self.assertFalse(lock.exists(), 'finite test run must release the guard lock')

    def test_provider_reads_current_physical_payload_before_old_cache(self):
        live = self.module / '.luoshu-payload/system/fonts'
        live.mkdir(parents=True)
        selected = live / '400.ttf'
        selected.write_bytes(b'current selection' * 200)
        stale = self.module / 'config/device-font-sources'
        stale.mkdir()
        (stale / 'LuoShu-400.ttf').write_bytes(b'old selection' * 200)
        self.assertEqual(self.provider_source(400).stdout.strip(), str(selected))
        selected.unlink()
        selected = live / 'SysSans-En-Regular.ttf'
        selected.write_bytes(b'current ColorOS selection' * 200)
        self.assertEqual(self.provider_source(400).stdout.strip(), str(selected))
        selected.unlink()
        self.assertNotEqual(self.provider_source(400).returncode, 0,
                            'missing current source must not revive stale cache')

    def test_provider_keeps_weight_and_legacy_layout_support(self):
        live = self.module / '.luoshu-payload/system/fonts'
        live.mkdir(parents=True)
        for weight in (400, 700):
            (live / f'{weight}.ttf').write_bytes(str(weight).encode() * 500)
        self.assertEqual(self.provider_source(700).stdout.strip(), str(live / '700.ttf'))
        shutil.rmtree(self.module / '.luoshu-payload')
        old = self.module / 'config/device-font-sources'
        old.mkdir()
        (old / 'LuoShu-700.ttf').write_bytes(b'old layout' * 200)
        self.assertEqual(self.provider_source(700).stdout.strip(), str(old / 'LuoShu-700.ttf'))

    def test_staging_never_copies_discarded_font_trees(self):
        source = self.module / '.luoshu-payload'
        (source / 'system/fonts/.luoshu-font-store').mkdir(parents=True)
        (source / 'system/fonts/.luoshu-font-store/old.font').write_bytes(b'x' * 4096)
        (source / 'system/etc').mkdir()
        (source / 'system/etc/retained.conf').write_text('keep config\n')
        (source / '.retained state').write_text('keep metadata\n')
        (source / '.luoshu-metrics-report.json').write_text('{"slots": ["old selection"]}')
        original = (source / 'system/fonts/.luoshu-font-store/old.font').read_bytes()
        real_cp = shutil.which('cp')
        self.executable('cp', '''
[ "$1" != -al ] || exit 1
for arg in "$@"; do
    if [ -d "$arg/system/fonts" ] || [ -d "$arg/fonts" ]; then
        echo 'attempted to copy discarded fonts' >&2
        exit 75
    fi
done
exec "$TEST_REAL_CP" "$@"
''')
        helper = ROOT / 'common/legacy_v14_4/payload_clone.sh'
        prelude = f'. "{helper}"\n' if helper.exists() else ''
        for relative, name, variable in (
            ('common/legacy_v14_4/font_switch_safe.sh', 'clone_payload_tree', 'STAGE_PAYLOAD'),
            ('common/legacy_v14_4/mix_router.sh', 'clone_mix_tree', 'MIX_STAGE'),
        ):
            with self.subTest(route=name):
                stage = self.module / name
                code = prelude + '\ncleanup_stage() { rm -rf "$STAGE_PAYLOAD"; }\n'
                code += function(relative, name) + f'\n{name} "$1"'
                result = subprocess.run(['sh', '-c', code, 'sh', str(source)],
                    env={**self.env, variable: str(stage), 'TEST_REAL_CP': real_cp},
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((stage / 'system/fonts').exists())
                self.assertFalse((stage / '.luoshu-metrics-report.json').exists())
                self.assertEqual((stage / 'system/etc/retained.conf').read_text(), 'keep config\n')
                self.assertEqual((stage / '.retained state').read_text(), 'keep metadata\n')
                self.assertEqual((source / 'system/fonts/.luoshu-font-store/old.font').read_bytes(), original)

    def test_real_switch_router_commits_only_successful_stages(self):
        legacy = self.module / 'common/legacy_v14_4'
        legacy.mkdir()
        for name in ('font_switch_safe.sh', 'payload_clone.sh'):
            shutil.copyfile(ROOT / 'common/legacy_v14_4' / name, legacy / name)
        shutil.copyfile(ROOT / 'common/font_switch_lock.sh', self.module / 'common/font_switch_lock.sh')
        (legacy / 'util_functions.sh').write_text('''
check_coloros() { IS_COLOROS=false; }
check_hyperos() { IS_HYPEROS=false; }
detect_font_family() { printf '%s\\n' "${1%.ttf}"; }
''')
        (legacy / 'rom_adapters.sh').write_text('''
apply_font_by_rom() {
    [ "${TEST_MAPPING_FAIL:-0}" != 1 ] || return 7
    mkdir -p "$2/.luoshu-font-store"
    cp "$1" "$2/.luoshu-font-store/regular.font" || return 1
    cp "$1" "$2/Roboto-Regular.ttf"
}
''')
        public = self.root / 'public'
        (public / 'fonts').mkdir(parents=True)
        (public / 'fonts/Selected.ttf').write_bytes(b'new selected font' * 300)
        live = self.module / '.luoshu-payload/system/fonts'
        live.mkdir(parents=True)
        old = live / 'Roboto-Regular.ttf'
        old.write_bytes(b'old active font' * 300)
        dynamic = self.module / '.luoshu-payload/future_oem/fonts'
        dynamic.mkdir(parents=True)
        (dynamic / 'OldDynamic.ttf').write_bytes(b'stale dynamic font' * 300)
        (self.module / 'config/device_font_partitions.conf').write_text('future_oem\n')
        before = old.read_bytes()
        command = ['sh', str(legacy / 'font_switch_safe.sh'), 'action', 'switch', 'Selected']
        prewarm_command = ['sh', str(legacy / 'font_switch_safe.sh'), 'action', 'prewarm', 'Selected']
        env = {**self.env, 'LUOSHU_PUBLIC_DIR': str(public)}
        # Prewarming must never commit a pending payload or alter the live tree.
        (self.module / 'config/device_font_inventory.json').write_text('{}')
        prewarm = subprocess.run(prewarm_command, env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(prewarm.returncode, 0, prewarm.stdout + prewarm.stderr)
        self.assertEqual(old.read_bytes(), before)
        self.assertFalse((self.module / '.luoshu-payload-next').exists())
        cache_confs = list((self.module / 'config/safe-switch-cache').glob('*/cache.conf'))
        self.assertTrue(cache_confs)
        cache_root = cache_confs[0].parent
        self.assertFalse((cache_root / 'tree/future_oem/fonts/OldDynamic.ttf').exists(),
                         'discovered OEM partitions must not retain stale font payloads')
        success = subprocess.run(command, env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(success.returncode, 0, success.stdout + success.stderr)
        self.assertIn('"status":"ok"', success.stdout)
        pending = self.module / '.luoshu-payload-next'
        self.assertEqual((pending / 'system/fonts/Roboto-Regular.ttf').read_bytes(),
                         (public / 'fonts/Selected.ttf').read_bytes())
        self.assertEqual(old.read_bytes(), before)
        shutil.rmtree(pending)
        (self.module / 'config/font-payload-next.conf').unlink()
        # Force a cache miss before exercising the mapper-failure rollback path.
        # A previously verified cache is allowed to bypass expensive regeneration.
        shutil.rmtree(self.module / 'config/safe-switch-cache', ignore_errors=True)
        failed = subprocess.run(command, env={**env, 'TEST_MAPPING_FAIL': '1'},
                                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse(pending.exists())
        self.assertEqual(old.read_bytes(), before)
        self.assertFalse(list(self.module.glob('.luoshu-payload-stage.*')))


if __name__ == '__main__':
    unittest.main()
