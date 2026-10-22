#!/usr/bin/env python3
"""ColorOS 15/16 Latin/digit coverage (2026-10).

Fixtures follow public ColorOS 15/16 firmware layouts: fonts_base.xml families
sys-sans-en / op-sans-en / osans-solid-digits, SysFont-*.ttf symlinks into the
flip-font directory /data/format_unclear/font (dangling and looping chains),
OSans-RC (rare-Han store) and OSans-Ext (placeholder) fallbacks.

Covers both shell mappers (legacy safe-switch and coloros_global), the shared
filename policy, the metrics post-pass gate and the read-only flip-font
diagnostic.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
import coloros_latin_policy as policy  # noqa: E402

LEGACY = ROOT / 'common/legacy_v14_4/rom_adapters.sh'
GLOBAL = ROOT / 'common/coloros_global.sh'
FLIP = ROOT / 'common/coloros_flipfont.sh'

MAPPED = ('SysSans-En-Regular.ttf', 'Roboto-Regular.ttf', 'OPSans-En-Regular.ttf',
          'SysSans-Hans-Regular.ttf', 'RobotoStatic-Regular.ttf')
SYMLINK_SLOTS = ('SysFont-Regular.ttf', 'SysFont-Static-Regular.ttf', 'SysFont-Hans-Regular.ttf')
STOCK_ONLY = ('OSans-RC-Regular.ttf', 'OSans-Ext-Regular.otf', 'SysFont-Myanmar.ttf',
              'Oplus-Serif.ttf', 'CutiveMono.ttf')
# Monospace and clock faces are replaced (clock digits get tabular widths).
MONO_CLOCK = ('DroidSansMono.ttf', 'AndroidClock.ttf')
DIGITS = 'OSans-Solid-Digits-VF.ttf'


def fake_font(path: Path, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(marker.encode() + b'\n' + b'\0' * 2048)


def coloros_rom(base: Path) -> tuple[Path, Path]:
    """A ColorOS 16-like /system/fonts plus its flip-font directory."""
    fonts = base / 'system/fonts'
    flip = base / 'data/format_unclear/font'
    flip.mkdir(parents=True)
    for name in (*MAPPED, DIGITS, 'OSans-RC-Regular.ttf', 'OSans-Ext-Regular.otf',
                 'DroidSansMono.ttf', 'AndroidClock.ttf', 'Oplus-Serif.ttf', 'CutiveMono.ttf',
                 'OplusOSUI-XThin.ttf'):
        fake_font(fonts / name, 'stock-' + name)
    # init.oplus.rootdir.rc: OplusOSUI-Regular -> Roboto-Regular resolves; the
    # framework may re-point it at a weight file absent on ColorOS 15/16.
    (flip / 'OplusOSUI-Regular.ttf').symlink_to(fonts / 'Roboto-Medium.ttf')          # dangling
    (flip / 'OplusOSUI-Static-Regular.ttf').symlink_to(fonts / 'RobotoStatic-Regular.ttf')
    (flip / 'OplusOSUI-Hans-Regular.ttf').symlink_to(fonts / 'SysFont-Hans-Regular.ttf')  # loop
    (flip / 'OplusOSUI-Myanmar.ttf').symlink_to(fonts / 'OplusOSUI-XThin.ttf')
    for slot, target in (('SysFont-Regular.ttf', 'OplusOSUI-Regular.ttf'),
                         ('SysFont-Static-Regular.ttf', 'OplusOSUI-Static-Regular.ttf'),
                         ('SysFont-Hans-Regular.ttf', 'OplusOSUI-Hans-Regular.ttf'),
                         ('SysFont-Myanmar.ttf', 'OplusOSUI-Myanmar.ttf')):
        (fonts / slot).symlink_to(flip / target)
    assert not (fonts / 'SysFont-Regular.ttf').exists()       # dangling chain
    assert not os.path.exists(fonts / 'SysFont-Hans-Regular.ttf')  # ELOOP
    return fonts, flip


def run_sh(script: str, env: dict) -> subprocess.CompletedProcess:
    full = dict(os.environ)
    full.update(env)
    return subprocess.run(['sh', '-c', script], env=full, capture_output=True, text=True, timeout=120)


class PolicyTest(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(policy.classify(DIGITS), 'digits')
        self.assertEqual(policy.classify('OSans-Rounded-Digits.ttf'), 'digits')
        for name in ('OSans-RC-Regular.ttf', 'OSans-Ext-Regular.otf', 'OSans-RC-Bold.ttf'):
            self.assertEqual(policy.classify(name), 'keep', name)
            self.assertTrue(policy.keeps_stock(name, frozenset({'osans_digits'})))
        for name in ('OSans-Solid-Digits-Mono.ttf', 'OSans-Digits-Italic.ttf', 'OSans-Clock-Digits.ttf',
                     'SysSans-En-Regular.ttf', 'Roboto-Regular.ttf'):
            self.assertEqual(policy.classify(name), 'other', name)
        self.assertTrue(policy.mapped_digit_name(DIGITS, frozenset({'osans_digits'})))
        self.assertTrue(policy.keeps_stock(DIGITS, frozenset()))

    def test_group_parsing_matches_shell_rule(self):
        self.assertEqual(policy.parse_groups(''), frozenset({'osans_digits'}))
        self.assertEqual(policy.parse_groups('osans_digits=0\n'), frozenset())
        self.assertEqual(policy.parse_groups('osans_digits=0\r\nosans_digits=1\n'), frozenset({'osans_digits'}))
        self.assertEqual(policy.parse_groups('osans_digits = 0\nosans_digits=no\n'), frozenset({'osans_digits'}))

    def test_shell_copies_match_policy(self):
        for path in (LEGACY, GLOBAL):
            text = path.read_text(encoding='utf-8')
            block = re.search(r'# >>> LUOSHU_COLOROS_LATIN_POLICY.*?# <<< LUOSHU_COLOROS_LATIN_POLICY', text, re.S)
            self.assertIsNotNone(block, path)
            body = block.group(0)
            for name in policy.DIGIT_FILES:
                self.assertIn(Path(name).stem, body, path)
            for name in policy.KEEP_STOCK_FILES:
                self.assertIn(name, body, path)
            for prefix in policy.KEEP_STOCK_PREFIXES:
                self.assertIn(prefix + '*', body, path)
            self.assertIn('osans_digits=', body)
        self.assertIn(f'LUOSHU_COLOROS_TARGETS_REVISION={policy.POLICY_REVISION}', GLOBAL.read_text())


class LegacyMapperTest(unittest.TestCase):
    def run_mapper(self, groups: str | None):
        with tempfile.TemporaryDirectory(prefix='luoshu-coloros-latin-') as tmp:
            tmp = Path(tmp)
            fonts, _flip = coloros_rom(tmp / 'stock')
            dest = tmp / 'stage/system/fonts'
            dest.mkdir(parents=True)
            user = tmp / 'public/fonts'
            fake_font(user / 'Demo-Regular.ttf', 'regular-source')
            module = tmp / 'module'
            (module / 'config').mkdir(parents=True)
            if groups is not None:
                (module / 'config/coloros_slot_groups.conf').write_text(groups)
            script = f'''
set +eu
. "{ROOT}/common/legacy_v14_4/util_functions.sh" >/dev/null 2>&1
. "{LEGACY}"
USER_FONTS_DIR="{user}"
IS_COLOROS=true IS_HYPEROS=false
apply_font_by_rom "{user}/Demo-Regular.ttf" "{dest}" quick Demo
'''
            result = run_sh(script, {'USER_FONTS_DIR': str(user), 'MODULE_DIR': str(module),
                                     'LUOSHU_LEGACY_STOCK_ROOT': str(tmp / 'stock')})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            source = (user / 'Demo-Regular.ttf').read_bytes()
            staged = {p.name: p.read_bytes() == source for p in dest.iterdir() if p.is_file()}
            return staged, result.stdout + result.stderr

    def test_digits_and_symlinked_latin_slots_are_mapped(self):
        staged, log = self.run_mapper(None)
        for name in (*MAPPED, *SYMLINK_SLOTS, DIGITS, *MONO_CLOCK):
            self.assertTrue(staged.get(name), f'{name} 未换成用户字体\n{log}')
        for name in STOCK_ONLY:
            self.assertNotIn(name, staged, f'{name} 应保留原厂\n{log}')

    def test_digit_group_switch_keeps_digits_stock(self):
        staged, log = self.run_mapper('osans_digits=0\n')
        self.assertNotIn(DIGITS, staged, log)
        for name in (*MAPPED, *SYMLINK_SLOTS):
            self.assertTrue(staged.get(name), f'{name} 未换成用户字体\n{log}')


class GlobalMapperTest(unittest.TestCase):
    def run_mapper(self, groups: str | None):
        with tempfile.TemporaryDirectory(prefix='luoshu-coloros-global-') as tmp:
            tmp = Path(tmp)
            fonts, _flip = coloros_rom(tmp / 'real')
            for part in ('system_ext', 'product'):
                (tmp / 'real' / part / 'fonts').mkdir(parents=True)
            module = tmp / 'module'
            (module / 'system/fonts').mkdir(parents=True)
            (module / 'config').mkdir()
            if groups is not None:
                (module / 'config/coloros_slot_groups.conf').write_text(groups)
            user = tmp / 'public/fonts'
            fake_font(user / 'Demo-Regular.ttf', 'regular-source')
            script = f'''
set +eu
_log_step() {{ printf '%s\\n' "$*"; }}
. "{ROOT}/common/util_functions.sh" >/dev/null 2>&1
. "{ROOT}/common/rom_adapters.sh" >/dev/null 2>&1
. "{GLOBAL}"
copy_as_coloros "{user}/Demo-Regular.ttf" "{module}/system/fonts" quick Demo
'''
            env = {'MODULE_DIR': str(module), 'MODDIR': str(module),
                   'LUOSHU_PUBLIC_DIR': str(tmp / 'public'), 'USER_FONTS_DIR': str(user),
                   'LUOSHU_COLOROS_SYSTEM_FONTS_ROOT': str(fonts),
                   'LUOSHU_COLOROS_SYSTEM_EXT_FONTS_ROOT': str(tmp / 'real/system_ext/fonts'),
                   'LUOSHU_COLOROS_PRODUCT_FONTS_ROOT': str(tmp / 'real/product/fonts')}
            result = run_sh(script, env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            source = (user / 'Demo-Regular.ttf').read_bytes()
            staged = {p.name: p.read_bytes() == source
                      for p in (module / 'system/fonts').iterdir() if p.is_file()}
            files = run_sh(f'. "{GLOBAL}"; get_all_coloros_files', env).stdout.split()
            return staged, files, result.stdout + result.stderr

    def test_digits_and_symlinked_latin_slots_are_mapped(self):
        staged, files, log = self.run_mapper(None)
        for name in (*MAPPED, *SYMLINK_SLOTS, DIGITS, *MONO_CLOCK):
            self.assertTrue(staged.get(name), f'{name} 未换成用户字体\n{log}')
        for name in STOCK_ONLY:
            self.assertNotIn(name, staged, f'{name} 应保留原厂\n{log}')
        self.assertIn(DIGITS, files)
        self.assertNotIn('OSans-RC-Regular.ttf', files)

    def test_digit_group_switch_keeps_digits_stock(self):
        staged, files, log = self.run_mapper('osans_digits=0\n')
        self.assertNotIn(DIGITS, staged, log)
        self.assertNotIn(DIGITS, files)
        self.assertTrue(staged.get('SysFont-Regular.ttf'), log)


class MetricsGateTest(unittest.TestCase):
    def test_digit_slot_eligible_only_while_group_enabled(self):
        import coloros_metrics_batch as batch
        logical = '/system/fonts/' + DIGITS
        slot = {'path': logical, 'families': ['osans-solid-digits']}
        self.assertTrue(batch.eligible_slot(slot, logical, frozenset({'osans_digits'})))
        self.assertFalse(batch.eligible_slot(slot, logical, frozenset()))
        rare = '/system/fonts/OSans-RC-Regular.ttf'
        self.assertFalse(batch.eligible_slot({'path': rare, 'families': []}, rare, frozenset({'osans_digits'})))

    def test_completion_never_restores_kept_slots(self):
        import coloros_metrics_batch as batch
        source = (ROOT / 'common/coloros_metrics_batch.py').read_text()
        self.assertTrue('coloros_latin_policy.keeps_stock(destination.name, groups)' in source)


class FlipFontDiagnosticTest(unittest.TestCase):
    def status(self, flip: Path, fonts: Path, extra: str = '') -> dict:
        env = {'LUOSHU_COLOROS_FLIP_DIR': str(flip), 'LUOSHU_COLOROS_FLIP_SYSTEM_FONTS': str(fonts)}
        result = run_sh(f'sh "{FLIP}" status{extra}', env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_init_links_are_ok_and_settings_font_is_reported(self):
        with tempfile.TemporaryDirectory(prefix='luoshu-coloros-flip-') as tmp:
            tmp = Path(tmp)
            fonts, flip = coloros_rom(tmp)
            data = self.status(flip, fonts)
            self.assertEqual(data['schema'], 'luoshu-coloros-flipfont-v1')
            self.assertEqual(data['verdict'], 'ok')
            states = {entry['name']: entry['state'] for entry in data['entries']}
            self.assertEqual(states['OplusOSUI-Regular.ttf'], 'system-dangling')
            self.assertEqual(states['OplusOSUI-Static-Regular.ttf'], 'system')
            self.assertEqual(states['OplusOSUI-Hans-Regular.ttf'], 'system-dangling')

            # A Settings/Theme font: the Latin flip face becomes a real /data file
            # and the bold face a link outside /system/fonts.
            (flip / 'OplusOSUI-Regular.ttf').unlink()
            (flip / 'OplusOSUI-Regular.ttf').write_bytes(b'\0' * 70000)
            theme = tmp / 'data/theme/fonts/Theme-Bold.ttf'
            fake_font(theme, 'theme')
            (flip / 'OplusOSUI-Bold.ttf').symlink_to(theme)
            data = self.status(flip, fonts)
            self.assertEqual(data['verdict'], 'redirected')
            self.assertEqual(data['latinRedirected'], 2)
            states = {entry['name']: entry['state'] for entry in data['entries']}
            self.assertEqual(states['OplusOSUI-Regular.ttf'], 'file')
            self.assertEqual(states['OplusOSUI-Bold.ttf'], 'external')

            report = tmp / 'report.json'
            env = {'LUOSHU_COLOROS_FLIP_DIR': str(flip), 'LUOSHU_COLOROS_FLIP_SYSTEM_FONTS': str(fonts),
                   'LUOSHU_COLOROS_FLIP_REPORT': str(report)}
            hint = run_sh(f'. "{FLIP}"; luoshu_coloros_flipfont_hint', env)
            self.assertIn('英文和数字', hint.stdout)
            self.assertIn('OplusOSUI-Regular.ttf', hint.stdout)
            self.assertEqual(json.loads(report.read_text())['verdict'], 'redirected')
            # The diagnostic is read-only.
            self.assertEqual((flip / 'OplusOSUI-Regular.ttf').stat().st_size, 70000)
            self.assertTrue((flip / 'OplusOSUI-Bold.ttf').is_symlink())

    def test_absent_directory_is_silent(self):
        with tempfile.TemporaryDirectory(prefix='luoshu-coloros-flip-') as tmp:
            tmp = Path(tmp)
            data = self.status(tmp / 'missing', tmp)
            self.assertEqual(data['verdict'], 'absent')
            self.assertEqual(data['entries'], [])
            env = {'LUOSHU_COLOROS_FLIP_DIR': str(tmp / 'missing'),
                   'LUOSHU_COLOROS_FLIP_REPORT': str(tmp / 'r.json')}
            self.assertEqual(run_sh(f'. "{FLIP}"; luoshu_coloros_flipfont_hint', env).stdout, '')

    def test_hint_is_wired_into_both_mappers(self):
        for path in (LEGACY, GLOBAL):
            self.assertTrue('luoshu_coloros_flipfont_hint' in path.read_text(), path)


if __name__ == '__main__':
    unittest.main(verbosity=1)
