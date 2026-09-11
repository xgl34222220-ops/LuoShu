#!/usr/bin/env python3
"""Behavioral regressions for actual HyperOS staging and boot repair."""
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
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
import hyperos_metrics_batch as batch


def font_file(path, top=700):
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0)); pen.lineTo((500, 0)); pen.lineTo((500, top)); pen.closePath()
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(['.notdef', 'A'])
    fb.setupCharacterMap({65: 'A'})
    fb.setupGlyf({'.notdef': pen.glyph(), 'A': pen.glyph()})
    fb.setupHorizontalMetrics({name: (600, 0) for name in ['.notdef', 'A']})
    fb.setupHorizontalHeader(ascent=1600, descent=-600)
    fb.setupOS2(sTypoAscender=1600, sTypoDescender=-600, usWinAscent=1700, usWinDescent=700)
    fb.setupNameTable({'familyName': 'Fixture', 'styleName': 'Regular'})
    fb.setupPost(); fb.setupMaxp(); fb.save(path)


def slot(ascent=1100, descent=-350, win=1400, typo=1080, use_typo=True):
    return {'metrics': {'upem': 1000,
        'hhea': {'ascent': ascent, 'descent': descent, 'lineGap': 30},
        'os2': {'typoAscender': typo, 'typoDescender': -320, 'typoLineGap': 20,
                'winAscent': win, 'winDescent': 400, 'fsSelection': 128 if use_typo else 0}}}


class HyperOSMetricsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.stage = self.module / '.luoshu-payload-next'
        self.fonts = self.stage / 'system/fonts'
        self.fonts.mkdir(parents=True)
        (self.module / 'config').mkdir()
        # The host may load FontTools only through the bundled pure-Python path.
        # Preserve that path separately before the Android entry point replaces it.
        self.env = {'LUOSHU_BUILD_KEY': 'fixture',
                    'LUOSHU_TEST_PYTHONPATH': os.pathsep.join(sys.path)}
        for part in batch.PARTS:
            root = self.root / 'stock' / part
            root.mkdir(parents=True)
            self.env[f'LUOSHU_{part.upper()}_FONTS_ROOT'] = str(root)
        self.env_patch = patch.dict(os.environ, self.env)
        self.env_patch.start(); self.addCleanup(self.env_patch.stop)
        font_file(self.fonts / '400.ttf')

    def inventory(self, slots):
        (self.module / 'config/device_font_inventory.json').write_text(json.dumps({
            'schema': 'device-font-inventory-v1', 'inventoryRevision': 1,
            'state': 'ready', 'buildKey': 'fixture', 'slots': slots}))
        for logical in slots:
            part, name = logical.split('/')[1], logical.split('/')[-1]
            (self.root / 'stock' / part / name).touch()

    def test_full_stock_contract_and_glyphs_unchanged(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot()})
        with patch.object(TTFont, 'getGlyphSet', side_effect=AssertionError('outline rebuild')):
            result = batch.build(self.module, self.stage, ['MiSansVF.ttf'])
        self.assertEqual(result, {'mapped': 1, 'generated': 1, 'fallbackSlots': 0})
        report = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())
        self.assertEqual(report['slots'][0]['metricsSource'], 'stock')
        self.assertEqual(report['slots'][0]['slot'], '/system/fonts/MiSansVF.ttf')
        with TTFont(self.fonts / 'MiSansVF.ttf') as out, TTFont(self.fonts / '400.ttf') as src:
            self.assertEqual((out['hhea'].ascent, out['hhea'].descent, out['hhea'].lineGap), (1100, -350, 30))
            self.assertEqual((out['OS/2'].sTypoAscender, out['OS/2'].sTypoLineGap), (1080, 20))
            self.assertEqual(out['OS/2'].usWinAscent, 1400)
            self.assertEqual(out['glyf'].compile(out), src['glyf'].compile(src))
            self.assertEqual(out['head'].yMax, src['head'].yMax)

    def test_full_contract_cache_and_multiweight(self):
        font_file(self.fonts / '700.ttf', 900)
        self.inventory({'/system/fonts/Roboto-Regular.ttf': slot(),
                        '/product/fonts/Roboto-Regular.ttf': slot(win=1500, use_typo=False),
                        '/system/fonts/Roboto-Bold.ttf': slot(),
                        '/system/fonts/MiSansVF.ttf': slot()})
        result = batch.build(self.module, self.stage, ['Roboto-Regular.ttf', 'Roboto-Bold.ttf', 'MiSansVF.ttf'])
        self.assertEqual(result['generated'], 3)
        with TTFont(self.stage / 'product/fonts/Roboto-Regular.ttf') as font:
            self.assertEqual(font['OS/2'].usWinAscent, 1500)
            self.assertFalse(font['OS/2'].fsSelection & 128)
        with TTFont(self.fonts / 'Roboto-Bold.ttf') as font:
            self.assertEqual(font['head'].yMax, 900)

    def test_no_cascade_when_alias_is_source(self):
        (self.fonts / '400.ttf').rename(self.fonts / 'MiSansVF.ttf')
        self.inventory({'/system/fonts/MiSansVF.ttf': slot(),
                        '/product/fonts/MiSansVF.ttf': slot()})
        result = batch.build(self.module, self.stage, ['MiSansVF.ttf'])
        self.assertEqual(result['generated'], 1)

    def test_missing_inventory_reports_fallback_and_bad_source_fails(self):
        (self.root / 'stock/system/MiSansVF.ttf').touch()
        result = batch.build(self.module, self.stage, ['MiSansVF.ttf'])
        self.assertEqual(result['fallbackSlots'], 1)
        report = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())
        self.assertEqual(report['slots'][0]['metricsSource'], 'fallback')
        (self.fonts / '400.ttf').write_bytes(b'corrupt')
        with self.assertRaises(Exception):
            batch.build(self.module, self.stage, ['MiSansVF.ttf'])

    def test_boot_repair_preserves_partition_contract(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot(),
                        '/product/fonts/MiSansVF.ttf': slot(ascent=850, descent=-150)})
        batch.build(self.module, self.stage, ['MiSansVF.ttf'])
        target = self.stage / 'product/fonts/MiSansVF.ttf'
        before = target.read_bytes()
        subprocess.run(['sh', '-c', '. "$1"; luoshu_hyperos_clock_payload_ensure', 'sh',
                        str(ROOT / 'common/legacy_v14_4/hyperos_clock_compat.sh')],
                       env={**os.environ, 'MODDIR': str(self.module), 'IS_HYPEROS': 'true',
                            'LUOSHU_HYPEROS_CLOCK_PAYLOAD_ROOT': str(self.stage)}, check=True)
        self.assertEqual(target.read_bytes(), before)

    def test_reject_live_payload(self):
        with self.assertRaisesRegex(ValueError, '本次启动'):
            batch.build(self.module, self.module / '.luoshu-payload', ['MiSansVF.ttf'])

    def test_stage_covers_the_same_dynamic_slots_as_boot(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot(),
                        '/product/fonts/MiSansDisplayVF.ttf': slot(ascent=850, descent=-150),
                        '/product/fonts/XiaomiSansVF.otf': slot(ascent=900, descent=-200)})
        common = self.module / 'common'
        (common / 'python/bin').mkdir(parents=True)
        (common / 'legacy_v14_4').mkdir()
        (self.module / 'module.prop').touch()
        for relative in ('hyperos_metrics_batch.py', 'font_metrics_normalize.py',
                         'legacy_v14_4/hyperos_full_coverage.sh',
                         'legacy_v14_4/hyperos_clock_compat.sh'):
            (common / relative).write_bytes((ROOT / 'common' / relative).read_bytes())
        (common / 'hyperos_global.sh').write_text('''
_hyperos_core_files() { echo MiSansVF.ttf; }
_hyperos_weight_files() { :; }
_hyperos_upright_ui_files() { :; }
_hyperos_clock_ui_files() { :; }
''')
        launcher = common / 'python/bin/luoshu-python'
        launcher.write_text('#!/bin/sh\nunset PYTHONHOME LD_LIBRARY_PATH\n'
                            'PYTHONPATH="$LUOSHU_TEST_PYTHONPATH" '
                            'exec "$LUOSHU_TEST_PYTHON" "$@"\n')
        launcher.chmod(0o755)
        result = subprocess.run(['sh', str(ROOT / 'common/hyperos_stage_complete.sh'), str(self.stage)],
            env={**os.environ, 'LUOSHU_REAL_MODDIR': str(self.module),
                 'LUOSHU_TEST_PYTHON': sys.executable}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name, ascent in (('MiSansDisplayVF.ttf', 850), ('XiaomiSansVF.otf', 900)):
            target = self.stage / 'product/fonts' / name
            self.assertTrue(target.exists(), 'boot-only aliases bypass per-slot metrics')
            with TTFont(target) as font:
                self.assertEqual(font['hhea'].ascent, ascent)

    def test_stage_failure_propagates_through_both_callers(self):
        helper = self.module / 'common/hyperos_stage_complete.sh'
        helper.parent.mkdir(parents=True)
        helper.write_text('exit 7\n')
        for relative, function in (
            ('common/legacy_v14_4/font_switch_safe.sh', 'stage_hyperos_complete'),
            ('common/legacy_v14_4/mix_router.sh', 'complete_hyperos_stage'),
        ):
            source = (ROOT / relative).read_text()
            start = source.index(function + '() {')
            code = source[start:source.index('\n}', start) + 2]
            result = subprocess.run(['sh', '-c', code + '\ngetprop() { echo HyperOS; }\n' + function],
                env={**os.environ, 'IS_HYPEROS': 'true', 'MODDIR': str(self.module),
                     'REALMOD': str(self.module), 'LOG_FILE': str(self.root / 'log'),
                     'STAGE_PAYLOAD': str(self.stage), 'MIX_STAGE': str(self.stage)})
            self.assertNotEqual(result.returncode, 0, relative)

    def test_shell_entry_uses_one_python_process(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot(),
                        '/product/fonts/MiSansVF.ttf': slot()})
        common = self.module / 'common'
        (common / 'python/bin').mkdir(parents=True)
        (self.module / 'module.prop').touch()
        for name in ('hyperos_metrics_batch.py', 'font_metrics_normalize.py'):
            (common / name).write_bytes((ROOT / 'common' / name).read_bytes())
        (common / 'hyperos_global.sh').write_text('''
_hyperos_core_files() { echo MiSansVF.ttf; }
_hyperos_weight_files() { :; }
_hyperos_upright_ui_files() { :; }
_hyperos_clock_ui_files() { :; }
''')
        launcher = common / 'python/bin/luoshu-python'
        launcher.write_text('#!/bin/sh\nprintf "launch\\n" >> "$LUOSHU_TEST_LAUNCHES"\n'
                            'unset PYTHONHOME LD_LIBRARY_PATH\n'
                            'PYTHONPATH="$LUOSHU_TEST_PYTHONPATH" '
                            'exec "$LUOSHU_TEST_PYTHON" "$@"\n')
        launcher.chmod(0o755)
        launches = self.root / 'launches'
        command = ['sh', str(ROOT / 'common/hyperos_stage_complete.sh'), str(self.stage)]
        env = {**os.environ, 'LUOSHU_REAL_MODDIR': str(self.module),
               'LUOSHU_TEST_LAUNCHES': str(launches), 'LUOSHU_TEST_PYTHON': sys.executable}
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['mapped'], 2)
        self.assertEqual(launches.read_text().splitlines(), ['launch'])
        (self.fonts / '400.ttf').write_bytes(b'corrupt')
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('HyperOS 字体处理失败', result.stderr)


if __name__ == '__main__':
    unittest.main()
