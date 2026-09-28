#!/usr/bin/env python3
"""Regressions for the withdrawn 2.0.0 candidate; synthetic, not phone QA."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'common'), str(ROOT/'scripts')]
from fontTools.ttLib import TTFont
import font_role_policy as roles
import hyperos_metrics_batch as batch
import stable111_round2_test as round2
make_font = round2.make_font
import stable111_repair_test as repair

class CoverageRegression(unittest.TestCase):
    def setUp(self):
        round2.Round2.setUp(self)
        make_font(self.fonts/'400.ttf', tuple(range(32,127)))
    stock = round2.Round2.stock
    save_inventory = round2.Round2.save_inventory
    build = round2.Round2.build

    def test_fixed_pitch_ui_is_not_a_code_font(self):
        name = 'MiSansLatinVF.ttf'
        self.stock(name, family='sys-sans-en')
        self.slots['/system/fonts/'+name]['metrics']['isFixedPitch'] = True
        make_font(self.fonts/name)
        self.build(['MiSansVF.ttf', name])
        self.assertTrue((self.fonts/name).is_file(), 'UI alias silently excluded as code')
        self.assertIn('/system/fonts/'+name, self.by_slot)
        self.assertNotIn('/system/fonts/'+name,
                         (self.stage/'.luoshu-stock-preserved.paths').read_text())
        with TTFont(self.fonts/name) as generated, TTFont(self.fonts/'400.ttf') as donor:
            for cp in [65, 97, *range(48, 58)]:
                self.assertIn(cp, generated.getBestCmap())
                self.assertEqual(generated['glyf'][generated.getBestCmap()[cp]].compile(generated['glyf']),
                                 donor['glyf'][donor.getBestCmap()[cp]].compile(donor['glyf']))

    def test_fixed_pitch_flag_alone_is_not_code_role(self):
        self.assertFalse(roles.is_code_monospace('VendorUI.ttf',
            {'families':['sans-serif'], 'metrics':{'isFixedPitch':True}}))
        self.assertTrue(roles.is_code_monospace('Terminal.ttf',
            {'families':['monospace'], 'metrics':{'isFixedPitch':True}}))

    def test_monotype_word_is_not_monospace(self):
        self.assertFalse(roles.is_code_monospace('MiSansMonotype-Regular.ttf',
            {'families':['sans-serif']}))
        from hyperos_physical_policy import safe_physical_font_name
        self.assertTrue(safe_physical_font_name('MiSansMonotype-Regular.ttf'))
        for n in ('DroidSansMono.ttf','NotoSansMono-Regular.ttf','RobotoMono-Regular.ttf'):
            self.assertTrue(roles.is_code_monospace(n))

    def test_digit_only_named_ui_font_is_discovered(self):
        name = 'VendorPanel-Regular.ttf'
        self.stock(name, family='system-ui', points=tuple(range(48,58)))
        self.build()
        self.assertIn('/system/fonts/'+name, self.by_slot)
        with TTFont(self.fonts/name) as font:
            self.assertTrue(set(range(48,58)) <= set(font.getBestCmap()))

    def test_digit_only_unclassified_font_stays_stock(self):
        name='UnknownSymbols.ttf'
        self.stock(name, family='', points=tuple(range(48,58)))
        self.build()
        self.assertNotIn('/system/fonts/'+name, self.by_slot)

    def test_staging_refuses_incomplete_english_donor(self):
        name='Roboto-Regular.ttf'
        self.stock(name, family='sans-serif', points=tuple(range(32,127)))
        make_font(self.fonts/'400.ttf', tuple([65,*range(48,58)]))
        self.save_inventory()
        with self.assertRaisesRegex(ValueError, '英文|英数|Latin'):
            batch.build(self.module,self.stage,['MiSansVF.ttf',name])
        self.assertFalse((self.fonts/name).exists())
        self.assertFalse(list((self.fonts/'.luoshu-font-store').glob('hyperos-metrics-*')))


class BootRouteRegression(unittest.TestCase):
    setUp = repair.ShellIntegration.setUp

    def service(self, theme):
        path = self.module/'common/google_font_provider_service.sh'
        shutil.copyfile(ROOT/'common/google_font_provider_service.sh', path)
        (self.module/'config/active_font.conf').write_text('custom\n')
        (self.module/'common/google_font_provider_bridge.sh').write_text('exit 2\n')
        (self.module/'common/hyperos_theme_font_bridge.sh').write_text(theme)
        return path

    def run_service(self, service, **extra):
        return subprocess.run(['sh',str(service),'boot'], env={**self.env,
            'LUOSHU_THEME_SETTLE_SECONDS':'3', **extra}, capture_output=True,
            text=True, timeout=7)

    def assert_clean(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"leftoverPids": []', result.stderr)
        self.assertFalse((self.module/'.google-font-provider.lock').exists())

    def test_theme_created_after_boot_is_not_silently_skipped(self):
        service=self.service('''case "$1" in
readiness) if [ -s "$MODDIR/config/theme-ready" ]; then echo 'ready|stable'; else echo pending; fi;;
apply) [ -s "$MODDIR/config/theme-ready" ] || exit 2
       echo applied > "$MODDIR/logs/theme-applied";;
restore) exit 0;;
esac
''')
        creator=subprocess.Popen([sys.executable,'-c',
            'import time,sys; from pathlib import Path; time.sleep(.2); Path(sys.argv[1]).write_text("ready")',
            str(self.module/'config/theme-ready')])
        try:
            result=self.run_service(service)
        finally:
            creator.wait(timeout=3)
        self.assert_clean(result)
        self.assertTrue((self.module/'logs/theme-applied').exists(),
                        'old service exited before framework route appeared')

    def test_missing_route_reports_partial_and_exits_without_retry_daemon(self):
        service=self.service('case "$1" in readiness) echo 1 > "$MODDIR/logs/probed"; echo pending;; apply) exit 2;; esac\n')
        start=time.monotonic()
        result=self.run_service(service, LUOSHU_THEME_SETTLE_SECONDS='1',
                                 LUOSHU_GOOGLE_FONT_WATCH_CYCLES='-1')
        self.assert_clean(result)
        self.assertLess(time.monotonic()-start, 4)
        report=(self.module/'config/font-provider-one-shot.conf').read_text()
        self.assertIn('state=partial',report)
        self.assertIn('theme-route-not-ready',report)
        self.assertIn('resident=false',report)

    def test_theme_wait_cancellation_reaps_all_children(self):
        service=self.service('case "$1" in readiness) echo 1 > "$MODDIR/logs/probed"; echo pending;; apply) exit 2;; esac\n')
        proc=subprocess.Popen(['sh',str(service),'boot'],env={**self.env,
            'LUOSHU_THEME_SETTLE_SECONDS':'30'}, stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+4
            while not (self.module/'logs/probed').exists() and time.monotonic()<deadline:
                time.sleep(.02)
            self.assertTrue((self.module/'logs/probed').exists())
            proc.terminate()
            out,err=proc.communicate(timeout=5)
            self.assertEqual(proc.returncode,143,(out,err))
            self.assertIn('"leftoverPids": []',err)
            self.assertFalse((self.module/'.google-font-provider.lock').exists(),
                             'supervisor interrupted the worker EXIT trap')
            # A cancelled task must not leave a fresh lease blocking the next task.
            recovery=self.run_service(service, LUOSHU_THEME_SETTLE_SECONDS='0',
                                      LUOSHU_FONT_LOCK_INIT_GRACE_SECONDS='0.01')
            self.assert_clean(recovery)
        finally:
            if proc.poll() is None: proc.kill();proc.wait()

    def test_real_bridge_readiness_rejects_unrelated_router(self):
        for name in ('google_font_provider_bridge.sh','hyperos_theme_font_bridge.sh'):
            shutil.copyfile(ROOT/'common'/name,self.module/'common'/name)
        (self.module/'config/active_font.conf').write_text('custom\n')
        root=self.module/'route';root.mkdir()
        target=root/'theme.ttf'; router=root/'router.ttf'; alias=root/'alias.ttf'
        router.symlink_to(target);alias.symlink_to(router)
        env={**self.env,'LUOSHU_THEME_FONT_TARGET':str(target),
             'LUOSHU_THEME_FONT_ALIAS':str(alias),'LUOSHU_THEME_FONT_ROUTER':str(router)}
        def probe():
            return subprocess.run(['sh',str(self.module/'common/hyperos_theme_font_bridge.sh'),'readiness'],
                env=env,capture_output=True,text=True,check=True,timeout=3).stdout.strip()
        self.assertEqual(probe(),'pending')
        target.write_bytes(b'fixture')
        self.assertTrue(probe().startswith('ready|'))
        alias.unlink();other=root/'other.ttf';other.write_bytes(b'foreign');alias.symlink_to(other)
        self.assertEqual(probe(),'pending')
        self.assertEqual(other.read_bytes(),b'foreign')

if __name__ == '__main__': unittest.main(verbosity=2)
