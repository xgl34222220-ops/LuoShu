#!/usr/bin/env python3
"""Execute the inventory-only writer with real SFNT, CFF, variable and TTC fonts."""
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTCollection, TTFont, getTableClass
import font_inventory
import inventory_font_stage as engine

LATIN = set(range(32, 127))
HAN = set(range(0x4e00, 0x5000))


def source_font(path, weight=400, points=None, family='User chosen family',
                cff=False, variable=False, italic=False, mono=False):
    points = LATIN | HAN if points is None else points
    cmap = {point: f'uni{point:04X}' for point in sorted(points)}
    order = ['.notdef', *cmap.values()]
    builder = FontBuilder(1000, isTTF=not cff)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(cmap)
    glyphs = {}
    for name in order:
        pen = T2CharStringPen(600, None) if cff else TTGlyphPen(None)
        pen.moveTo((30, -80)); pen.lineTo((570, -80)); pen.lineTo((570, 760)); pen.closePath()
        glyphs[name] = pen.getCharString() if cff else pen.glyph()
    if cff:
        builder.setupCFF('Fixture', {'FullName': 'Fixture'}, glyphs, {})
    else:
        builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 30) for name in order})
    builder.setupHorizontalHeader(ascent=1200, descent=-500)
    builder.setupOS2(usWeightClass=weight, sTypoAscender=1200, sTypoDescender=-500,
                    usWinAscent=1300, usWinDescent=600, fsSelection=1 if italic else 0)
    builder.setupNameTable({'familyName': family, 'styleName': f'Weight {weight}'})
    builder.setupPost(isFixedPitch=int(mono)); builder.setupMaxp()
    if variable:
        builder.setupFvar([('wght', 100, 400, 900, 'Weight')], [])
        builder.setupGvar({name: [] for name in order})
    path.parent.mkdir(parents=True, exist_ok=True)
    builder.save(path)


class InventoryStageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        (self.module / 'config').mkdir(parents=True)
        self.stage = self.module / '.luoshu-payload-stage'
        self.source = self.root / 'sources/selected.ttf'
        source_font(self.source)
        self.env = patch.dict(os.environ, {'LUOSHU_BUILD_KEY': 'fixture'})
        self.env.start(); self.addCleanup(self.env.stop)

    def slot(self, weight=400, points=None, **extras):
        path = self.root / 'stock.font'
        source_font(path, weight, points=points)
        fmt, metrics = font_inventory._read_metrics(path)
        metrics['hhea'] = {'ascent': 950, 'descent': -250, 'lineGap': 10}
        metrics['os2'].update(typoAscender=900, typoDescender=-220, typoLineGap=0,
                              winAscent=1100, winDescent=350)
        metrics['head'].update(yMin=-330, yMax=1100)
        return {'format': fmt, 'weight': weight, 'style': 'normal', 'metrics': metrics,
                'requiresScripts': list(metrics['fontTraits']['letterScripts']), **extras}

    def inventory(self, slots):
        data = {'schema': 'device-font-inventory-v1', 'state': 'ready', 'inventoryRevision': 1,
                'scannerRevision': 9, 'metricsRevision': 4, 'buildKey': 'fixture',
                'slots': slots, 'mainSlotPath': next(iter(slots))}
        (self.module / 'config/device_font_inventory.json').write_text(json.dumps(data))

    def run_engine(self, **kwargs):
        return engine.run(self.module, self.stage, 'direct', self.source, **kwargs)

    def test_unknown_names_all_partitions_share_identical_contract_and_raw_tables(self):
        paths = ['/system/fonts/UnknownVendorText.ttf', '/product/fonts/OtherName.ttf',
                 '/vendor/fonts/Nested/ActualUI.otf']
        self.inventory({path: self.slot() for path in paths})
        with patch.object(getTableClass('glyf'), 'compile', side_effect=AssertionError('outline compile')):
            report = self.run_engine()
        self.assertEqual(report['mapped'], 3)
        self.assertEqual(report['generated'], 1)
        outputs = [self.stage / path[1:] for path in paths]
        self.assertEqual(len({path.stat().st_ino for path in outputs}), 1)
        with TTFont(self.source, lazy=True) as src, TTFont(outputs[0]) as out:
            self.assertEqual(src.reader['glyf'], out.reader['glyf'])
            self.assertEqual((out['hhea'].ascent, out['hhea'].descent), (950, -250))
            self.assertEqual((out['head'].yMin, out['head'].yMax), (-330, 1100))

    def test_missing_weight_never_labels_regular_as_bold(self):
        self.inventory({'/system/fonts/Text.ttf': self.slot(), '/system/fonts/Bold.ttf': self.slot(700)})
        result = self.run_engine()
        self.assertEqual((result['mapped'], result['preserved']), (1, 1))
        self.assertFalse((self.stage / 'system/fonts/Bold.ttf').exists())
        self.assertIn('source-weight-missing', (self.stage / '.luoshu-coverage-preserved.tsv').read_text())

    def test_metadata_family_weight_search_and_unrelated_font_not_selected(self):
        source_font(self.source.parent / 'unrelated.ttf', 500, family='Other')
        source_font(self.source.parent / 'arbitrary-name.ttf', 700)
        self.inventory({'/system/fonts/regular.ttf': self.slot(), '/system/fonts/heavy.ttf': self.slot(700),
                        '/system/fonts/medium.ttf': self.slot(500)})
        report = self.run_engine()
        self.assertEqual(report['mapped'], 2)
        with TTFont(self.stage / 'system/fonts/heavy.ttf') as out:
            self.assertEqual(out['OS/2'].usWeightClass, 700)

    def test_variable_instances_and_dynamic_axes_preserved(self):
        source_font(self.source, variable=True)
        self.inventory({'/system/fonts/LiveVariable.ttf': self.slot(supportedAxes=['wght']),
                        '/product/fonts/500.ttf': self.slot(500),
                        '/system/fonts/500.ttf': self.slot(500),
                        '/system/fonts/700.ttf': self.slot(700)})
        result = self.run_engine()
        self.assertEqual(result['sourceInstances'], 3)
        with TTFont(self.stage / 'system/fonts/LiveVariable.ttf') as font:
            self.assertIn('fvar', font)
        for name, weight in [('500.ttf', 500), ('700.ttf', 700)]:
            with TTFont(self.stage / 'system/fonts' / name) as font:
                self.assertNotIn('fvar', font)
                self.assertEqual(font['OS/2'].usWeightClass, weight)

    def test_collection_order_and_distinct_real_weights(self):
        source_font(self.source.parent / 'bold.ttf', 700)
        target = self.slot(format='TTC', faces=[dict(self.slot(), faceIndex=0), dict(self.slot(700), faceIndex=1)])
        self.inventory({'/system/fonts/Shared.ttc': target})
        self.run_engine()
        with TTCollection(self.stage / 'system/fonts/Shared.ttc') as fonts:
            self.assertEqual([font['OS/2'].usWeightClass for font in fonts.fonts], [400, 700])

    def test_incomplete_collection_is_preserved_as_whole(self):
        target = self.slot(format='TTC', faces=[dict(self.slot(), faceIndex=0), dict(self.slot(700), faceIndex=1)])
        self.inventory({'/system/fonts/Shared.ttc': target, '/system/fonts/Regular.ttf': self.slot()})
        self.run_engine()
        self.assertFalse((self.stage / 'system/fonts/Shared.ttc').exists())
        self.assertIn('preserved-collection:source-weight-missing', (self.stage / '.luoshu-coverage-preserved.tsv').read_text())

    def test_script_style_and_monospace_require_actual_source_capability(self):
        arabic = self.slot(points=LATIN | set(range(0x620, 0x650)))
        italic = self.slot(style='italic')
        mono = self.slot()
        mono['metrics']['fontTraits']['monospaced'] = True
        self.inventory({'/system/fonts/Main.ttf': self.slot(), '/system/fonts/Arabic.ttf': arabic,
                        '/system/fonts/Italic.ttf': italic, '/system/fonts/Mono.ttf': mono})
        self.assertEqual(self.run_engine()['mapped'], 1)
        source_font(self.source.parent / 'arabic.ttf', points=LATIN | set(range(0x620, 0x650)))
        source_font(self.source.parent / 'italic.ttf', italic=True)
        source_font(self.source.parent / 'mono.ttf', mono=True)
        self.assertEqual(self.run_engine()['mapped'], 4)

    def test_cjk_routing_requires_scanner_proven_reachable_fallback(self):
        fallback = '/product/fonts/Chinese.ttf'
        self.inventory({fallback: self.slot(), '/system/fonts/Latin.ttf': self.slot(points=LATIN, fallbackTargets=[fallback]),
                        '/system/fonts/Private.ttf': self.slot(points=LATIN)})
        self.run_engine()
        with TTFont(self.stage / 'system/fonts/Latin.ttf') as font:
            self.assertNotIn(0x4e00, font.getBestCmap())
        with TTFont(self.stage / 'system/fonts/Private.ttf') as font:
            self.assertIn(0x4e00, font.getBestCmap())

    def test_incremental_plan_does_not_rewrite_unrequested_outputs(self):
        self.inventory({'/system/fonts/A.ttf': self.slot(), '/product/fonts/B.ttf': self.slot()})
        self.run_engine()
        unchanged = self.stage / 'system/fonts/A.ttf'
        inode = unchanged.stat().st_ino
        plan = self.root / 'plan.lst'
        plan.write_text('/product/fonts/B.ttf\n')
        result = engine.run(self.module, self.stage, 'direct', plan=plan)
        self.assertEqual((result['planned'], result['existing'], result['requested']), (1, 1, 1))
        self.assertEqual(unchanged.stat().st_ino, inode)

    def test_failure_never_replaces_stage_aliases_or_live(self):
        second = self.slot()
        second['metrics']['hhea']['ascent'] = 1050
        self.inventory({'/system/fonts/A.ttf': self.slot(), '/product/fonts/B.ttf': second})
        live = self.module / '.luoshu-payload/system/fonts/Live.ttf'
        live.parent.mkdir(parents=True); live.write_bytes(b'live')
        original = engine.write_metrics
        calls = []
        def fail_second(*args, **kwargs):
            calls.append(args)
            if len(calls) > 1:
                raise MemoryError('fixture memory limit')
            return original(*args, **kwargs)
        with patch.object(engine, 'write_metrics', side_effect=fail_second), self.assertRaises(MemoryError):
            self.run_engine()
        self.assertFalse((self.stage / 'system/fonts/A.ttf').exists())
        self.assertEqual(live.read_bytes(), b'live')

    def test_cff_font_retains_exact_outline_table(self):
        source_font(self.source, cff=True)
        self.inventory({'/system/fonts/Actual.ttf': self.slot()})
        self.run_engine()
        with TTFont(self.source, lazy=True) as src, TTFont(self.stage / 'system/fonts/Actual.ttf', lazy=True) as out:
            self.assertEqual(src.reader['CFF '], out.reader['CFF '])

    def test_reject_live_path_and_symlink_destination(self):
        self.inventory({'/system/fonts/Actual.ttf': self.slot()})
        with self.assertRaises(engine.StageError):
            engine.run(self.module, self.module / '.luoshu-payload', 'direct', self.source)
        outside = self.root / 'outside'; outside.mkdir()
        (self.stage / 'system').mkdir(parents=True)
        (self.stage / 'system/fonts').symlink_to(outside)
        with self.assertRaises(engine.StageError):
            self.run_engine()
        self.assertFalse(list(outside.iterdir()))

    def test_mix_never_restores_unselected_variable_donor(self):
        store = self.stage / 'system/fonts/.luoshu-font-store'; store.mkdir(parents=True)
        source_font(store / 'mix-composite.font')
        source_font(store / 'regular.font', variable=True)
        self.inventory({'/system/fonts/A.ttf': self.slot(), '/system/fonts/B.ttf': self.slot(700)})
        result = engine.run(self.module, self.stage, 'mix')
        self.assertEqual(result['mapped'], 1)

    def test_source_snapshot_survives_user_file_overwrite(self):
        self.inventory({'/system/fonts/A.ttf': self.slot()})
        self.run_engine()
        anchor = self.stage / 'system/fonts/.luoshu-font-store/regular.font'
        previous = anchor.read_bytes()
        self.source.write_bytes(b'user replaced source')
        self.assertEqual(anchor.read_bytes(), previous)

    def test_unusual_xml_font_extension_and_stale_manifest_cleanup(self):
        old = '/product/assets/typefaces/vendor.bin'
        current = '/product/assets/typefaces/new.fontdata'
        self.inventory({old: self.slot()})
        self.run_engine()
        self.inventory({current: self.slot()})
        self.run_engine()
        self.assertTrue((self.stage / current[1:]).is_file())
        self.assertFalse((self.stage / old[1:]).exists())

    def test_same_weight_style_variants_survive_incremental_repair(self):
        source_font(self.source.parent / 'italic.ttf', italic=True)
        normal, italic = '/system/fonts/A.ttf', '/system/fonts/I.ttf'
        self.inventory({normal: self.slot(), italic: self.slot(style='italic')})
        self.run_engine()
        plan = self.root / 'plan.lst'; plan.write_text(italic + '\n')
        engine.run(self.module, self.stage, 'direct', plan=plan)
        with TTFont(self.stage / italic[1:]) as font:
            self.assertTrue(font['OS/2'].fsSelection & 1)

    def test_fixed_composite_weight_keeps_explicit_selection(self):
        store = self.stage / 'system/fonts/.luoshu-font-store'; store.mkdir(parents=True)
        source_font(store / 'mix-composite.font')
        digest = hashlib.sha256((store / 'mix-composite.font').read_bytes()).hexdigest()
        (store / '.luoshu-mix-source-weights.json').write_text(json.dumps({
            'schema': 'luoshu-mix-source-weights-v1', 'sources': {'mix-composite.font': {
                'cjkWeight': 400, 'latinWeight': 400, 'digitWeight': 400,
                'cjkMode': 'fixed', 'latinMode': 'fixed', 'digitMode': 'fixed', 'digest': digest}}}))
        self.inventory({'/system/fonts/A.ttf': self.slot(), '/system/fonts/B.ttf': self.slot(700)})
        result = engine.run(self.module, self.stage, 'mix')
        self.assertEqual(result['mapped'], 2)
        with TTFont(self.stage / 'system/fonts/B.ttf') as font:
            self.assertEqual(font['OS/2'].usWeightClass, 400)

    def test_variable_italic_axis_is_instanced_for_italic_target(self):
        source_font(self.source, variable=True)
        with TTFont(self.source) as font:
            from fontTools.ttLib.tables._f_v_a_r import Axis
            font['gvar']
            axis = Axis()
            axis.axisTag = 'ital'; axis.minValue = 0; axis.defaultValue = 0
            axis.maxValue = 1; axis.flags = 0; axis.axisNameID = 257
            font['fvar'].axes.append(axis)
            font.save(self.source)
        self.inventory({'/system/fonts/A.ttf': self.slot(style='italic')})
        self.run_engine()
        with TTFont(self.stage / 'system/fonts/A.ttf') as font:
            self.assertNotIn('fvar', font)
            self.assertTrue(font['OS/2'].fsSelection & 1)

    def test_old_inventory_cannot_reach_writer(self):
        self.inventory({'/system/fonts/A.ttf': self.slot()})
        path = self.module / 'config/device_font_inventory.json'
        data = json.loads(path.read_text()); data['scannerRevision'] = 8
        path.write_text(json.dumps(data))
        with self.assertRaises(engine.StageError):
            self.run_engine()


if __name__ == '__main__':
    unittest.main()
