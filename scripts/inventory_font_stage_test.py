#!/usr/bin/env python3
"""Execute the inventory-only writer with real SFNT, CFF, variable and TTC fonts."""
from pathlib import Path
import hashlib
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTCollection, TTFont, getTableClass
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
import font_inventory
import inventory_font_stage as engine

LATIN = set(range(32, 127))
HAN = set(range(0x4e00, 0x5000))


def source_font(path, weight=400, points=None, family='User chosen family',
                cff=False, variable=False, italic=False, mono=False, right=570):
    points = LATIN | HAN if points is None else points
    cmap = {point: f'uni{point:04X}' for point in sorted(points)}
    order = ['.notdef', *cmap.values()]
    builder = FontBuilder(1000, isTTF=not cff)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(cmap)
    glyphs = {}
    for name in order:
        pen = T2CharStringPen(600, None) if cff else TTGlyphPen(None)
        pen.moveTo((30, -80)); pen.lineTo((right, -80)); pen.lineTo((right, 760)); pen.closePath()
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


def drawn_glyph(font, point):
    glyphs = font.getGlyphSet()
    pen = RecordingPen()
    glyphs[font.getBestCmap()[point]].draw(pen)
    return pen.value


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
        self.stock_sequence = 0

    def slot(self, weight=400, points=None, **extras):
        path = self.root / f'stock-{self.stock_sequence}.font'
        self.stock_sequence += 1
        source_font(path, weight, points=points)
        fmt, metrics = font_inventory._read_metrics(path)
        metrics['hhea'] = {'ascent': 950, 'descent': -250, 'lineGap': 10}
        metrics['os2'].update(typoAscender=900, typoDescender=-220, typoLineGap=0,
                              winAscent=1100, winDescent=350)
        metrics['head'].update(yMin=-330, yMax=1100)
        return {'format': fmt, 'weight': weight, 'style': 'normal', 'metrics': metrics,
                'requiresScripts': list(metrics['fontTraits']['letterScripts']),
                '_testStockFile': str(path), **extras}

    def inventory(self, slots):
        slots = copy.deepcopy(slots)
        roots = {}
        for logical, slot in slots.items():
            output = self.root / 'stock' / logical[1:]
            output.parent.mkdir(parents=True, exist_ok=True)
            prototypes = slot.get('faces') or [slot]
            opened = []
            for face in prototypes:
                font = TTFont(face.pop('_testStockFile'))
                font.recalcBBoxes = False
                metrics = face['metrics']
                for attribute, value in metrics['head'].items():
                    setattr(font['head'], attribute, value)
                for attribute, value in metrics['hhea'].items():
                    setattr(font['hhea'], attribute, value)
                for field, attribute in (('typoAscender', 'sTypoAscender'), ('typoDescender', 'sTypoDescender'),
                                         ('typoLineGap', 'sTypoLineGap'), ('winAscent', 'usWinAscent'),
                                         ('winDescent', 'usWinDescent'), ('fsSelection', 'fsSelection')):
                    setattr(font['OS/2'], attribute, metrics['os2'][field])
                font['post'].isFixedPitch = int(metrics['fontTraits'].get('monospaced', False))
                opened.append(font)
            if slot.get('format') in {'TTC', 'OTC'}:
                collection = TTCollection(); collection.fonts = opened
                collection.save(output); collection.close()
            else:
                opened[0].save(output); opened[0].close()
            for index, face in enumerate(prototypes):
                face['metrics'] = font_inventory._read_metrics(output, index)[1]
                face['stockSource'] = {'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}
            slot.pop('_testStockFile', None)
            slot['metrics'] = prototypes[0]['metrics']
            slot['stockSource'] = prototypes[0]['stockSource']
            parent = str(Path(logical).parent)
            roots[parent] = {'partition': Path(logical).parts[1], 'logical': parent,
                             'actual': str(output.parent)}
        data = {'schema': 'device-font-inventory-v1', 'state': 'ready', 'inventoryRevision': 1,
                'scannerRevision': 10, 'metricsRevision': 5, 'buildKey': 'fixture',
                'slots': slots, 'mainSlotPath': next(iter(slots)), 'sourceRoots': list(roots.values())}
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

    def test_incomplete_collection_replaces_available_face_and_preserves_stock_face(self):
        source_font(self.source, right=450)
        retained = dict(self.slot(700), faceIndex=1)
        with TTFont(retained['_testStockFile']) as font:
            uvs = CmapSubtable.newSubtable(14)
            uvs.platformID, uvs.platEncID, uvs.language = 0, 5, 0
            uvs.cmap = {}; uvs.uvsDict = {0xFE00: [(0x4e00, 'uni4E00')]}
            font['cmap'].tables.append(uvs)
            font.save(retained['_testStockFile'])
        target = self.slot(format='TTC', faces=[dict(self.slot(), faceIndex=0), retained])
        self.inventory({'/system/fonts/Regular.ttf': self.slot(), '/system/fonts/Shared.ttc': target})
        result = self.run_engine()
        self.assertEqual((result['mapped'], result['preserved']), (2, 0))
        with TTCollection(self.stage / 'system/fonts/Shared.ttc') as output, \
                TTCollection(self.root / 'stock/system/fonts/Shared.ttc') as stock, TTFont(self.source) as donor:
            self.assertEqual(len(output.fonts), 2)
            self.assertEqual(drawn_glyph(output.fonts[0], 0x41), drawn_glyph(donor, 0x41))
            self.assertNotEqual(drawn_glyph(output.fonts[0], 0x41), drawn_glyph(stock.fonts[0], 0x41))
            self.assertEqual([font['OS/2'].usWeightClass for font in output.fonts], [400, 700])
            # All retained SFNT table bytes, including cmap format 14, layout,
            # naming and the outline glyph order, survive TTC repacking.
            self.assertEqual(set(output.fonts[1].reader.keys()), set(stock.fonts[1].reader.keys()))
            for tag in stock.fonts[1].reader.keys():
                actual, expected = output.fonts[1].reader[tag], stock.fonts[1].reader[tag]
                if tag == 'head':
                    actual, expected = actual[:8] + actual[12:], expected[:8] + expected[12:]
                self.assertEqual(actual, expected, tag)
            self.assertEqual([table.uvsDict for table in output.fonts[1]['cmap'].tables if table.format == 14],
                             [{0xFE00: [(0x4e00, 'uni4E00')]}])
        report = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())
        rows = [row for row in report['slots'] if row['slot'].endswith('Shared.ttc')]
        self.assertEqual([row['state'] for row in rows], ['replaced', 'retained-stock'])
        self.assertEqual(rows[1]['reason'], 'source-weight-missing')
        self.assertEqual(rows[1]['replacedRoleCounts'], {})
        self.assertEqual(report['partialSlots'], ['/system/fonts/Shared.ttc'])

    def test_partial_chinese_latin_digits_replace_only_real_intersection(self):
        selected = {0x41, 0x30, 0x4e00}
        source_font(self.source, points=selected, right=420)
        path = '/system/fonts/Main.ttf'
        self.inventory({path: self.slot()})
        self.run_engine()
        with TTFont(self.stage / path[1:]) as output, TTFont(self.root / 'stock' / path[1:]) as stock, \
                TTFont(self.source) as donor:
            self.assertEqual(set(output.getBestCmap()), set(stock.getBestCmap()))
            for point in selected:
                self.assertEqual(drawn_glyph(output, point), drawn_glyph(donor, point))
                self.assertNotEqual(drawn_glyph(output, point), drawn_glyph(stock, point))
            for point in {0x42, 0x31, 0x4e01}:
                self.assertEqual(drawn_glyph(output, point), drawn_glyph(stock, point))
        row = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())['slots'][0]
        self.assertEqual(row['replacedRoleCounts'], {'cjk': 1, 'latin': 1, 'digit': 1})
        self.assertEqual(row['retainedTargetRoleCounts'], {'cjk': len(HAN) - 1, 'latin': 51, 'digit': 9})
        self.assertEqual(row['replacedCodepoints'], 3)

    def test_unavailable_optional_stock_does_not_block_certain_source_capability_rejections(self):
        paths = ['/system/fonts/Heavy.ttf', '/system/fonts/Italic.ttf', '/system/fonts/Unused.ttc']
        collection = self.slot(format='TTC', faces=[dict(self.slot(700), faceIndex=0),
            dict(self.slot(900), faceIndex=1)])
        self.inventory({'/system/fonts/Main.ttf': self.slot(), paths[0]: self.slot(700),
                        paths[1]: self.slot(style='italic'), paths[2]: collection})
        for path in paths:
            (self.root / 'stock' / path[1:]).unlink()
        with patch.object(engine.StockSourceResolver, 'resolve', autospec=True,
                          side_effect=engine.StockSourceResolver.resolve) as resolver:
            result = self.run_engine()
        self.assertEqual((result['mapped'], result['preserved']), (1, 3))
        self.assertEqual([call.args[1] for call in resolver.call_args_list], ['/system/fonts/Main.ttf'])

    def test_role_without_any_actual_intersection_does_not_count_as_replacement(self):
        source_font(self.source, points={0x41}, right=420)
        self.inventory({'/system/fonts/Main.ttf': self.slot(points={0x41}),
                        '/system/fonts/Other.ttf': self.slot(points={0x42})})
        result = self.run_engine()
        self.assertEqual((result['mapped'], result['preserved']), (1, 1))
        self.assertFalse((self.stage / 'system/fonts/Other.ttf').exists())
        self.assertIn('source-target-characters-missing', (self.stage / '.luoshu-coverage-preserved.tsv').read_text())

    def test_one_digit_is_enough_for_a_matching_digit_slot(self):
        source_font(self.source, points={0x30}, right=420)
        self.inventory({'/system/fonts/Digit.ttf': self.slot(points=set(range(48, 58)))})
        result = self.run_engine()
        self.assertEqual(result['mapped'], 1)
        row = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())['slots'][0]
        self.assertEqual(row['replacedRoleCounts'], {'cjk': 0, 'latin': 0, 'digit': 1})

    def test_collection_protected_symbol_face_keeps_original_glyphs(self):
        source_font(self.source, right=420)
        target = self.slot(format='TTC', faces=[dict(self.slot(), faceIndex=0),
            dict(self.slot(points={0x2605}), faceIndex=1, preservedReason='protected-symbol-font')])
        self.inventory({'/system/fonts/Shared.ttc': target})
        self.run_engine()
        with TTCollection(self.stage / 'system/fonts/Shared.ttc') as output, \
                TTCollection(self.root / 'stock/system/fonts/Shared.ttc') as stock:
            self.assertEqual(output.fonts[1].reader['glyf'], stock.fonts[1].reader['glyf'])
            self.assertEqual(output.fonts[1].getBestCmap(), stock.fonts[1].getBestCmap())
        rows = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())['slots']
        self.assertEqual(rows[1]['state'], 'retained-stock')
        self.assertEqual(rows[1]['reason'], 'protected-symbol-font')

    def test_collection_cannot_hide_main_face_failure_with_secondary_face(self):
        target = self.slot(format='TTC', faces=[dict(self.slot(), faceIndex=0, supportedAxes=['wght'],
            xmlReferences=[{'weight': 400}, {'weight': 700}]), dict(self.slot(), faceIndex=1)])
        self.inventory({'/system/fonts/Shared.ttc': target})
        with self.assertRaisesRegex(engine.StageError, '主要中文或英文字体'):
            self.run_engine()
        self.assertFalse((self.stage / 'system/fonts/Shared.ttc').exists())

    def test_collection_packing_rejects_face_reordering_before_payload_write(self):
        target = self.slot(format='TTC', faces=[dict(self.slot(), faceIndex=0), dict(self.slot(700), faceIndex=1)])
        self.inventory({'/system/fonts/Shared.ttc': target})
        original = TTCollection.save
        def reverse_faces(collection, output, *args, **kwargs):
            collection.fonts.reverse()
            return original(collection, output, *args, **kwargs)
        with patch.object(TTCollection, 'save', reverse_faces):
            with self.assertRaisesRegex(engine.StageError, '集合面顺序'):
                self.run_engine()
        self.assertFalse((self.stage / 'system/fonts/Shared.ttc').exists())

    def test_collection_inventory_must_include_every_original_face(self):
        target = self.slot(format='TTC', faces=[dict(self.slot(), faceIndex=0), dict(self.slot(700), faceIndex=1)])
        self.inventory({'/system/fonts/Shared.ttc': target})
        inventory = self.module / 'config/device_font_inventory.json'
        data = json.loads(inventory.read_text())
        data['slots']['/system/fonts/Shared.ttc']['faces'].pop()
        inventory.write_text(json.dumps(data))
        with self.assertRaisesRegex(engine.StageError, '原厂字体集合面数'):
            self.run_engine()
        self.assertFalse((self.stage / 'system/fonts/Shared.ttc').exists())

    def test_collection_repair_cannot_reduce_previously_replaced_face_roles(self):
        source_font(self.source.parent / 'bold.ttf', 700)
        path = '/system/fonts/Shared.ttc'
        target = self.slot(format='TTC', faces=[dict(self.slot(), faceIndex=0), dict(self.slot(700), faceIndex=1)])
        self.inventory({path: target})
        self.run_engine()
        before = self.stage_snapshot()
        plan = self.root / 'plan.lst'; plan.write_text(path + '\n')
        original = engine.SourcePool.pick
        def decline_bold(pool, face):
            if face['faceIndex'] == 1:
                return None, 700, 'source-weight-missing'
            return original(pool, face)
        with patch.object(engine.SourcePool, 'pick', decline_bold):
            with self.assertRaisesRegex(engine.StageError, '减少了字体集合已有的字形替换'):
                engine.run(self.module, self.stage, 'direct', plan=plan)
        self.assertEqual(self.stage_snapshot(), before)

    def test_optional_collection_supplement_limit_preserves_only_affected_face(self):
        source_font(self.source, variable=True)
        optional = self.slot(format='TTC', faces=[dict(self.slot(), faceIndex=0),
            dict(self.slot(points=LATIN | HAN | {0x3a9}), faceIndex=1, supportedAxes=['wght'])])
        self.inventory({'/system/fonts/Main.ttf': self.slot(), '/system/fonts/Shared.ttc': optional})
        result = self.run_engine()
        self.assertEqual(result['mapped'], 2)
        report = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())
        rows = [row for row in report['slots'] if row['slot'].endswith('Shared.ttc')]
        self.assertEqual([row['state'] for row in rows], ['replaced', 'retained-stock'])
        self.assertEqual(rows[1]['reason'], 'source-variable-supplement-unavailable')

    def test_script_style_and_monospace_require_actual_source_capability(self):
        arabic = self.slot(points=LATIN | set(range(0x620, 0x650)))
        italic = self.slot(style='italic')
        mono = self.slot()
        mono['metrics']['fontTraits']['monospaced'] = True
        self.inventory({'/system/fonts/Main.ttf': self.slot(), '/system/fonts/Arabic.ttf': arabic,
                        '/system/fonts/Italic.ttf': italic, '/system/fonts/Mono.ttf': mono})
        self.assertEqual(self.run_engine()['mapped'], 2)
        report = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())
        arabic_row = next(row for row in report['slots'] if row['slot'].endswith('Arabic.ttf'))
        self.assertTrue(arabic_row['supplemented'])
        self.assertGreater(arabic_row['retainedStockCodepoints'], 0)
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
            self.assertNotIn(0x4e00, font.getBestCmap())
        rows = {row['slot']: row for row in json.loads((self.stage / '.luoshu-metrics-report.json').read_text())['slots']}
        self.assertEqual(rows['/system/fonts/Latin.ttf']['cjkRoutingSource'], 'stock-fallback')
        self.assertEqual(rows['/system/fonts/Private.ttf']['cjkRoutingSource'], 'source')

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

    def mix_store(self, mode='fixed'):
        store = self.stage / 'system/fonts/.luoshu-font-store'; store.mkdir(parents=True)
        source_font(store / 'mix-composite.font')
        digest = hashlib.sha256((store / 'mix-composite.font').read_bytes()).hexdigest()
        (store / '.luoshu-mix-source-weights.json').write_text(json.dumps({
            'schema': 'luoshu-mix-source-weights-v1', 'sources': {'mix-composite.font': {
                'cjkWeight': 400, 'latinWeight': 400, 'digitWeight': 400,
                'cjkMode': mode, 'latinMode': mode, 'digitMode': mode, 'digest': digest}}}))

    def test_all_fixed_composite_can_replace_multiweight_primary_without_fake_axis(self):
        self.mix_store()
        path = '/system/fonts/Main.ttf'
        self.inventory({path: self.slot(supportedAxes=['wght'],
            xmlReferences=[{'weight': 400}, {'weight': 700}])})
        result = engine.run(self.module, self.stage, 'mix')
        self.assertEqual(result['mapped'], 1)
        with TTFont(self.stage / path[1:]) as font:
            self.assertNotIn('fvar', font)
            self.assertEqual(font['OS/2'].usWeightClass, 400)

    def test_static_auto_composite_cannot_fake_dynamic_primary_or_optional_axis(self):
        self.mix_store('auto')
        main, optional = '/system/fonts/Main.ttf', '/system/fonts/Optional.ttf'
        self.inventory({main: self.slot(), optional: self.slot(supportedAxes=['wght'])})
        result = engine.run(self.module, self.stage, 'mix')
        self.assertEqual(result['mapped'], 1)
        self.assertIn('source-variable-range-missing', (self.stage / '.luoshu-coverage-preserved.tsv').read_text())
        self.inventory({main: self.slot(supportedAxes=['wght']), optional: self.slot()})
        before = self.stage_snapshot()
        with self.assertRaisesRegex(engine.StageError, '主要中文或英文字体'):
            engine.run(self.module, self.stage, 'mix')
        self.assertEqual(self.stage_snapshot(), before)

    def test_primary_cjk_failure_cannot_be_masked_by_another_latin_success(self):
        main, other = '/system/fonts/Cjk.ttf', '/system/fonts/Latin.ttf'
        self.inventory({main: self.slot(points=HAN, supportedAxes=['wght'],
            xmlReferences=[{'weight': 400}, {'weight': 700}]),
            other: self.slot(points=LATIN, families=['sans-serif'])})
        with self.assertRaisesRegex(engine.StageError, '主要中文或英文字体.*cjk'):
            self.run_engine()
        self.assertFalse((self.stage / other[1:]).exists())

    def test_primary_latin_fallback_cjk_is_a_required_role(self):
        main, fallback = '/system/fonts/Latin.ttf', '/product/fonts/Cjk.ttf'
        self.inventory({main: self.slot(points=LATIN, fallbackTargets=[fallback]),
                        fallback: self.slot(points=HAN, supportedAxes=['wght'],
                            xmlReferences=[{'weight': 400}, {'weight': 700}])})
        with self.assertRaisesRegex(engine.StageError, '主要中文或英文字体.*cjk'):
            self.run_engine()
        self.assertFalse((self.stage / main[1:]).exists())

    def test_source_with_more_requested_roles_beats_selected_digits_only_face(self):
        source_font(self.source, points=set(range(48, 58)))
        source_font(self.source.parent / 'sibling.ttf')
        self.inventory({'/system/fonts/Main.ttf': self.slot()})
        self.run_engine()
        rows = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())['slots']
        self.assertEqual(set(rows[0]['replacedRoles']), {'cjk', 'latin', 'digit'})

    def test_known_optional_supplement_limit_is_preserved_but_unknown_failure_aborts(self):
        source_font(self.source, variable=True)
        main, optional = '/system/fonts/Main.ttf', '/system/fonts/Optional.ttf'
        self.inventory({main: self.slot(), optional: self.slot(points=LATIN | HAN | {0x3a9}, supportedAxes=['wght'])})
        result = self.run_engine()
        self.assertEqual(result['mapped'], 1)
        self.assertIn('source-variable-supplement-unavailable', (self.stage / '.luoshu-coverage-preserved.tsv').read_text())
        source_font(self.source)
        before = self.stage_snapshot()
        with patch.object(engine, 'supplement', side_effect=OSError('write failed')):
            with self.assertRaisesRegex(OSError, 'write failed'):
                self.run_engine()
        self.assertEqual(before, self.stage_snapshot())

    def test_raw_cmap_scope_does_not_add_donor_extra_scripts_or_recompile_cff(self):
        source_font(self.source, cff=True, points=LATIN | HAN | {0x627})
        self.inventory({'/system/fonts/Latin.ttf': self.slot(points=LATIN)})
        self.run_engine()
        with TTFont(self.source, lazy=True) as src, TTFont(self.stage / 'system/fonts/Latin.ttf', lazy=True) as output:
            self.assertEqual(set(output.getBestCmap()), LATIN)
            self.assertEqual(output.reader['CFF '], src.reader['CFF '])

    def test_supplement_is_reused_for_actual_metric_only_stock_variants(self):
        first, second = '/system/fonts/First.ttf', '/product/fonts/Second.ttf'
        stock1 = self.slot(points=LATIN | HAN | {0x3a9})
        stock2 = copy.deepcopy(stock1)
        stock2['metrics']['hhea']['ascent'] = 990
        stock2['metrics']['os2']['winAscent'] = 1200
        self.inventory({first: stock1, second: stock2})
        physical1, physical2 = self.root / 'stock' / first[1:], self.root / 'stock' / second[1:]
        self.assertNotEqual(hashlib.sha256(physical1.read_bytes()).hexdigest(), hashlib.sha256(physical2.read_bytes()).hexdigest())
        with patch.object(engine, 'supplement', wraps=engine.supplement) as merge:
            result = self.run_engine()
        self.assertEqual(merge.call_count, 1)
        self.assertEqual(result['supplementedSources'], 1)
        for path, ascent in ((first, 950), (second, 990)):
            with TTFont(self.stage / path[1:]) as font:
                self.assertEqual(font['hhea'].ascent, ascent)
                self.assertIn(0x3a9, font.getBestCmap())

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

    def stage_snapshot(self):
        return {path.relative_to(self.stage).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.stage.rglob('*') if path.is_file()}

    def test_repair_does_not_reclassify_or_delete_four_of_fifteen_valid_slots(self):
        paths = [f'/system/fonts/Text{i}.ttf' for i in range(15)]
        self.inventory({path: self.slot(repairRegressionExcluded=index >= 11)
                        for index, path in enumerate(paths)})
        self.run_engine()
        before = {path: (self.stage / path[1:]).read_bytes() for path in paths}
        plan = self.root / 'repair.lst'; plan.write_text(paths[0] + '\n')
        original = engine.SourcePool.pick
        visited = []
        # These four slots remain valid even if capability reconstruction now
        # rejects their metadata. A repair must never ask that question for an
        # unrequested, verified existing output.
        def deny_nonrequested(pool, face):
            visited.append(face)
            if face.get('repairRegressionExcluded'):
                return None, 400, 'source-script-coverage-missing'
            return original(pool, face)
        with patch.object(engine.SourcePool, 'pick', deny_nonrequested):
            result = engine.run(self.module, self.stage, 'direct', plan=plan)
        self.assertEqual(len(visited), 2)  # preflight, then actual stock intersection
        self.assertIs(visited[0], visited[1])
        self.assertEqual((result['mapped'], result['preserved'], result['planned']), (15, 0, 1))
        for path in paths[1:]:
            self.assertEqual((self.stage / path[1:]).read_bytes(), before[path])
        covered = (self.stage / '.luoshu-metrics-covered.lst').read_text().splitlines()
        self.assertEqual(set(covered), set(paths))

    def test_repair_requested_unsupported_source_fails_without_protected_success(self):
        path = '/system/fonts/A.ttf'
        self.inventory({path: self.slot()}); self.run_engine()
        before = self.stage_snapshot()
        plan = self.root / 'repair.lst'; plan.write_text(path + '\n')
        with patch.object(engine.SourcePool, 'pick', return_value=(None, 400, 'source-script-coverage-missing')):
            with self.assertRaises(engine.StageError):
                engine.run(self.module, self.stage, 'direct', plan=plan)
        self.assertEqual(self.stage_snapshot(), before)

    def test_repair_refuses_changed_anchor_inventory_mode_and_unrequested_output(self):
        first, second = '/system/fonts/A.ttf', '/system/fonts/B.ttf'
        self.inventory({first: self.slot(), second: self.slot()})
        plan = self.root / 'repair.lst'; plan.write_text(first + '\n')
        for failure in ('anchor', 'inventory', 'mode', 'output'):
            with self.subTest(failure=failure):
                self.inventory({first: self.slot(), second: self.slot()})
                self.run_engine()
                mode = 'direct'
                if failure == 'anchor':
                    (self.stage / 'system/fonts/.luoshu-font-store/regular.font').write_bytes(b'changed')
                elif failure == 'inventory':
                    self.inventory({first: self.slot(700), second: self.slot()})
                elif failure == 'mode':
                    mode = 'mix'
                else:
                    # Replace one directory entry so the other hardlink stays valid.
                    path = self.stage / second[1:]; path.unlink(); path.write_bytes(b'corrupt')
                before = self.stage_snapshot()
                with self.assertRaises(engine.StageError):
                    engine.run(self.module, self.stage, mode, plan=plan)
                self.assertEqual(self.stage_snapshot(), before)

    def test_repair_requires_clone_proof_and_cannot_switch_explicit_source(self):
        path = '/system/fonts/A.ttf'; self.inventory({path: self.slot()})
        plan = self.root / 'repair.lst'; plan.write_text(path + '\n')
        with self.assertRaises(engine.StageError):
            engine.run(self.module, self.stage, 'direct', plan=plan)
        self.run_engine(); before = self.stage_snapshot()
        with self.assertRaises(engine.StageError):
            engine.run(self.module, self.stage, 'direct', self.source, plan=plan)
        self.assertEqual(self.stage_snapshot(), before)


if __name__ == '__main__':
    unittest.main()
