#!/usr/bin/env python3
"""Exercise the real ColorOS staged aliases, including distinct weight sources."""
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
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont
import coloros_metrics_batch as batch


def font_file(path, top=800, cff=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    order = ['.notdef', 'A', 'one', 'uni4E2D']
    glyphs = {}
    for name in order:
        pen = T2CharStringPen(600, None) if cff else TTGlyphPen(None)
        pen.moveTo((0, -50)); pen.lineTo((500, -50))
        pen.lineTo((500, top)); pen.lineTo((0, top)); pen.closePath()
        glyphs[name] = pen.getCharString() if cff else pen.glyph()
    fb = FontBuilder(1000, isTTF=not cff)
    fb.setupGlyphOrder(order); fb.setupCharacterMap({65: 'A', 49: 'one', 0x4E2D: 'uni4E2D'})
    if cff:
        fb.setupCFF('ColorOSFixture', {'FullName': 'ColorOSFixture'}, glyphs, {})
    else:
        fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (600, 0) for name in order})
    fb.setupHorizontalHeader(ascent=1600, descent=-600)
    fb.setupOS2(sTypoAscender=1600, sTypoDescender=-600,
               usWinAscent=1700, usWinDescent=700)
    fb.setupNameTable({'familyName': 'ColorOSFixture', 'styleName': 'Regular'})
    fb.setupPost(); fb.setupMaxp(); fb.save(path)


def stock(ascent=920, descent=-240, head=(-250, 1050), upem=1000):
    result = {'metrics': {'upem': upem,
        'hhea': {'ascent': ascent, 'descent': descent, 'lineGap': 0},
        'os2': {'typoAscender': ascent - 10, 'typoDescender': descent,
                'typoLineGap': 0, 'winAscent': ascent + 20,
                'winDescent': -descent + 20, 'fsSelection': 128}}}
    if head is not None:
        result['metrics']['head'] = {'yMin': head[0], 'yMax': head[1]}
    return result


class ColorOSMetricsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.stage = self.module / '.luoshu-payload-next'
        self.stage.mkdir(parents=True)
        (self.module / 'config').mkdir()
        self.env = patch.dict(os.environ, {'LUOSHU_BUILD_KEY': 'coloros-fixture'})
        self.env.start(); self.addCleanup(self.env.stop)

    def target(self, name='SysSans-Hans-Regular.ttf', partition='system'):
        return self.stage / partition / 'fonts' / name

    def inventory(self, slots, build='coloros-fixture'):
        (self.module / 'config/device_font_inventory.json').write_text(json.dumps({
            'schema': 'device-font-inventory-v1', 'inventoryRevision': 1,
            'state': 'ready', 'buildKey': build, 'slots': slots}))

    def report(self):
        result = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())
        self.assertEqual(result['schema'], 'luoshu-slot-metrics-v1')
        self.assertEqual(result['romKind'], 'coloros')
        return result['slots']

    def test_restores_each_existing_alias_and_preserves_real_weight_source(self):
        regular = self.target()
        bold = self.target('SysSans-Hans-Bold.ttf')
        numeric = self.target('400.ttf')
        font_file(regular, top=730); font_file(bold, top=940); font_file(numeric, top=1100)
        originals = {path.name: path.read_bytes() for path in (regular, bold, numeric)}
        self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': stock(),
                        '/system/fonts/SysSans-Hans-Bold.ttf': stock(),
                        '/system/fonts/SysSans-En-Regular.ttf': stock()})
        with patch.object(TTFont, 'getGlyphSet', side_effect=AssertionError('outline rebuild')):
            result = batch.build(self.module, self.stage)
        self.assertEqual(result, {'mapped': 2, 'generated': 2, 'preservedSlots': 1})
        self.assertFalse(self.target('SysSans-En-Regular.ttf').exists(), 'must not add slots')
        self.assertEqual(numeric.read_bytes(), originals[numeric.name])
        for path, top in ((regular, 730), (bold, 940)):
            with TTFont(path) as font:
                self.assertEqual(font['hhea'].ascent, 920)
                self.assertEqual(font['head'].yMax, 1050)
                self.assertEqual(font['glyf']['A'].yMax, top)
        self.assertEqual(len(self.report()), 3)

    def test_cross_partition_hardlinks_do_not_cascade_or_share_distinct_frames(self):
        regular = self.target(); font_file(regular)
        product = self.target(partition='oplus_product')
        product.parent.mkdir(parents=True); os.link(regular, product)
        same = self.target('SysFont-Regular.ttf'); os.link(regular, same)
        source_bytes = regular.read_bytes()
        self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': stock(),
                        '/system/fonts/SysFont-Regular.ttf': stock(),
                        '/oplus_product/fonts/SysSans-Hans-Regular.ttf': stock(
                            ascent=1800, descent=-400, head=(-410, 2000), upem=2000)})
        writer = batch.write_metrics
        def checked_writer(source, output, contract, **options):
            for path in (regular, product, same):
                self.assertEqual(path.read_bytes(), source_bytes,
                                 'every font must be generated before replacing aliases')
            return writer(source, output, contract, **options)
        with patch.object(batch, 'write_metrics', side_effect=checked_writer):
            result = batch.build(self.module, self.stage)
        self.assertEqual(result['generated'], 3)
        self.assertNotEqual(regular.stat().st_ino, same.stat().st_ino,
                            'Latin alignment must not leak into CJK aliases')
        self.assertNotEqual(regular.stat().st_ino, product.stat().st_ino)
        with TTFont(product) as font:
            self.assertEqual(font['hhea'].ascent, 900)
            self.assertEqual((font['head'].yMin, font['head'].yMax), (-205, 1000))

    def test_ttf_and_cff_tables_are_not_recompiled(self):
        for cff, name, table in ((False, 'SysSans-Hans-Regular.ttf', 'glyf'),
                                 (True, 'OPPODIN-Regular.otf', 'CFF ')):
            font_file(self.target(name), cff=cff)
        raw = {}
        for name, table in (('SysSans-Hans-Regular.ttf', 'glyf'), ('OPPODIN-Regular.otf', 'CFF ')):
            with TTFont(self.target(name), lazy=True) as font:
                raw[name] = (table, font.reader[table])
        self.inventory({f'/system/fonts/{name}': stock() for name in raw})
        with patch.object(TTFont, 'getGlyphSet', side_effect=AssertionError('outline rebuild')):
            batch.build(self.module, self.stage)
        for name, (table, contents) in raw.items():
            with TTFont(self.target(name), lazy=True) as font:
                self.assertEqual(font.reader[table], contents)

    def test_missing_stale_or_invalid_inventory_does_not_use_hyperos_fallback(self):
        font_file(self.target())
        original = self.target().read_bytes()
        for mode in ('missing', 'stale', 'invalid'):
            with self.subTest(mode=mode):
                if mode == 'stale':
                    self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': stock()}, build='old')
                elif mode == 'invalid':
                    self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': stock(ascent=-1)})
                result = batch.build(self.module, self.stage)
                self.assertEqual(result['mapped'], 0)
                self.assertEqual(self.target().read_bytes(), original)
                self.assertEqual(self.report()[0]['metricsSource'], 'preserved')

    def test_old_inventory_without_head_preserves_source_bounds(self):
        font_file(self.target())
        self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': stock(head=None)})
        batch.build(self.module, self.stage)
        with TTFont(self.target()) as font:
            self.assertEqual(font['hhea'].ascent, 920)
            self.assertEqual((font['head'].yMin, font['head'].yMax), (-50, 800))
        self.assertEqual(self.report()[0]['layoutBoundsSource'], 'source')

    def test_ineligible_symbol_slot_and_path_mismatch_are_preserved(self):
        self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': {
                            **stock(), 'path': '/system/fonts/another.ttf'},
                        '/system/fonts/StatusIcons.ttf': {**stock(), 'families': ['sans-serif']},
                        '/system/fonts/NovelFont.ttf': {**stock(), 'families': ['serif']}})
        paths = [self.target(name) for name in ('SysSans-Hans-Regular.ttf', 'StatusIcons.ttf', 'NovelFont.ttf')]
        for path in paths:
            font_file(path)
        originals = [path.read_bytes() for path in paths]
        self.assertEqual(batch.build(self.module, self.stage)['mapped'], 0)
        self.assertEqual([path.read_bytes() for path in paths], originals)

    def test_explicit_ui_xml_slot_can_use_an_unusual_filename(self):
        target = self.target('VendorText.otf'); font_file(target, cff=True)
        self.inventory({'/system/fonts/VendorText.otf': {**stock(), 'families': ['sans-serif']}})
        self.assertEqual(batch.build(self.module, self.stage)['mapped'], 1)

    def test_collection_is_preserved_instead_of_discarding_other_faces(self):
        first = self.root / 'first.ttf'; second = self.root / 'second.ttf'
        font_file(first); font_file(second, top=900)
        path = self.target('SysSans-Hans-Regular.ttc'); path.parent.mkdir(parents=True)
        with TTFont(first) as a, TTFont(second) as b:
            collection = TTCollection(); collection.fonts = [a, b]; collection.save(path)
        original = path.read_bytes()
        self.inventory({'/system/fonts/SysSans-Hans-Regular.ttc': {**stock(), 'faceIndex': 1}})
        self.assertEqual(batch.build(self.module, self.stage)['mapped'], 0)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.report()[0]['reason'], 'collection-metrics-preserved')

    def test_generation_failure_does_not_replace_any_existing_alias(self):
        first = self.target('SysSans-Hans-Regular.ttf'); font_file(first)
        second = self.target('SysSans-Z-Broken.ttf'); second.write_bytes(b'brokenfont')
        self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': stock(),
                        '/system/fonts/SysSans-Z-Broken.ttf': stock()})
        original = first.read_bytes()
        with self.assertRaises(Exception):
            batch.build(self.module, self.stage)
        self.assertEqual(first.read_bytes(), original)
        self.assertFalse(list(self.stage.glob('.coloros-metrics-*')))
        self.assertFalse((self.stage / '.luoshu-metrics-report.json').exists())

    def test_rejects_live_and_module_roots(self):
        for target in (self.module, self.module / '.luoshu-payload',
                       self.module / '.luoshu-payload/system'):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, '本次启动'):
                batch.build(self.module, target)

    def test_shell_uses_one_python_process_and_passes_real_module(self):
        common = self.module / 'common'
        (common / 'python/bin').mkdir(parents=True)
        (self.module / 'module.prop').touch()
        for name in ('coloros_metrics_batch.py', 'font_inventory.py', 'font_inventory_scan.py',
                     'hyperos_metrics_batch.py', 'font_metrics_normalize.py'):
            (common / name).symlink_to(ROOT / 'common' / name)
        launcher = common / 'python/bin/luoshu-python'
        launcher.write_text('#!/bin/sh\necho called >> "$LUOSHU_TEST_CALLS"\n'
                            'unset PYTHONHOME LD_LIBRARY_PATH\n'
                            'PYTHONPATH="$LUOSHU_TEST_PATH" exec "$LUOSHU_TEST_PYTHON" "$@"\n')
        launcher.chmod(0o755)
        font_file(self.target())
        self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': stock()})
        calls = self.root / 'calls'
        result = subprocess.run(['sh', str(ROOT / 'common/coloros_stage_complete.sh'), str(self.stage)],
            env={**os.environ, 'LUOSHU_REAL_MODDIR': str(self.module),
                 'LUOSHU_TEST_PATH': os.pathsep.join(sys.path),
                 'LUOSHU_TEST_PYTHON': sys.executable, 'LUOSHU_TEST_CALLS': str(calls)},
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls.read_text().splitlines(), ['called'])
        self.assertEqual(json.loads(result.stdout)['mapped'], 1)

    def test_inventory_entrypoints_propagate_metric_failures(self):
        helper = self.module / 'common/inventory_font_stage.sh'
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text('printf "called\\n" >> "$TEST_CALLS"\nexit 7\n')
        marker = self.root / 'calls'
        stub = '\n'.join((
            'mix_request_is_current() { return 0; }',
            'precommit_ready() { return 1; }',
            'next_mix_payload_ready_for_request() { return 1; }',
            'stage_has_fonts() { return 0; }',
            'stage_generation_matches() { return 0; }',
            'read_value() { :; }',
            'mix_finalize_state_write() { :; }',
            'precommit_fail() { return 1; }',
        ))
        for filename, function in (('font_switch_safe.sh', 'stage_inventory_map'),
                                   ('mix_router.sh', 'prepare_mix_stage_for_commit')):
            source = (ROOT / 'common/legacy_v14_4' / filename).read_text()
            start = source.index(function + '() {')
            code = source[start:source.index('\n}', start) + 2]
            result = subprocess.run(['sh', '-c', code + '\n' + stub + '\n' + function + ' source Demo'],
                env={**os.environ, 'IS_COLOROS': 'true', 'IS_HYPEROS': 'true',
                     'MODDIR': str(self.module), 'REALMOD': str(self.module),
                     'INVENTORY_STAGE_HELPER': str(helper), 'USER_ROOT': str(self.root),
                     'STAGE_PAYLOAD': str(self.stage), 'MIX_STAGE': str(self.stage),
                     'LOG_FILE': str(self.root / 'log'), 'TEST_CALLS': str(marker)})
            self.assertNotEqual(result.returncode, 0, filename)
        self.assertEqual(marker.read_text().splitlines(), ['called', 'called'])

    def test_inventory_mapping_has_no_second_brand_postpass(self):
        # With overlapping vendor markers, the safe entry still invokes exactly
        # one inventory pass. Unexpected old helpers terminate with a clear code.
        helper = self.module / 'common/inventory_font_stage.sh'
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text('printf "mapped\\n" >> "$TEST_CALLS"\n')
        source = (ROOT / 'common/legacy_v14_4/font_switch_safe.sh').read_text()
        start = source.index('stage_inventory_map() {')
        code = source[start:source.index('\n}', start) + 2]
        marker = self.root / 'calls'
        result = subprocess.run(['sh', '-c', code + '\n' +
            'getprop() { echo marker; }; stage_hyperos_complete() { exit 91; }; ' +
            'stage_coloros_complete() { exit 92; }; stage_inventory_map source Demo'],
            env={**os.environ, 'IS_HYPEROS': 'true', 'IS_COLOROS': 'true',
                 'MODDIR': str(self.module), 'USER_ROOT': str(self.root),
                 'INVENTORY_STAGE_HELPER': str(helper), 'STAGE_PAYLOAD': str(self.stage),
                 'LOG_FILE': str(self.root / 'log'), 'TEST_CALLS': str(marker)})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(marker.read_text().splitlines(), ['mapped'])


if __name__ == '__main__':
    unittest.main()
