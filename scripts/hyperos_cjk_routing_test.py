#!/usr/bin/env python3
"""Real cmap regressions for stock Latin primary / staged CJK fallback routing.

FreeType checks the actual character-to-glyph lookup used by font selection.
This verifies the routing contract, not QQ/Coolapk rendering on a K80 device.
"""
import ctypes as C
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
import font_inventory as inventory
import font_inventory_scan_v3 as scanner
import hyperos_metrics_batch as batch
from font_slot_coverage import valid_coverage
from hyperos_layout_freetype_test import FreeType, Face

HAN = 0x4E2D
OTHER_HAN = 0x20000
UVS_HAN = 0x56FD
PUNCT = 0x3001
LATIN = 65
EMOJI = 0x2600
DEFAULT_POINTS = (LATIN, 48, 0xFF11, HAN, OTHER_HAN, UVS_HAN, PUNCT, EMOJI)


def make_font(path, points=DEFAULT_POINTS, cff=False, variable=False, uvs=False):
    cmap = {cp: f'u{cp:X}' for cp in points}
    names = ['.notdef', *cmap.values()]
    builder = FontBuilder(1000, isTTF=not cff)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap(cmap)
    glyphs = {}
    for name in names:
        pen = T2CharStringPen(600, None) if cff else TTGlyphPen(None)
        if name != '.notdef':
            pen.moveTo((20, -80)); pen.lineTo((550, -80))
            pen.lineTo((550, 850)); pen.lineTo((20, 850)); pen.closePath()
        glyphs[name] = pen.getCharString() if cff else pen.glyph()
    if cff:
        builder.setupCFF('RoutingFixture-Regular', {'FullName': 'RoutingFixture'}, glyphs, {})
    else:
        builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 20) for name in names})
    builder.setupHorizontalHeader(ascent=980, descent=-250)
    builder.setupOS2(sTypoAscender=980, sTypoDescender=-250,
                     usWinAscent=1050, usWinDescent=300)
    builder.setupNameTable({'familyName': 'RoutingFixture', 'styleName': 'Regular'})
    builder.setupPost(); builder.setupMaxp()
    if variable:
        builder.setupFvar([('wght', 100, 400, 900, 'Weight')], [])
        builder.setupGvar({name: [] for name in names})
    if uvs:
        table = CmapSubtable.newSubtable(14)
        table.platformID = 0; table.platEncID = 5; table.language = 0
        table.cmap = {}
        table.uvsDict = {0xFE00: [(cp, None) for cp in (UVS_HAN, LATIN, EMOJI) if cp in cmap]}
        builder.font['cmap'].tables.append(table)
    builder.save(path)


class RoutingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.stage = self.module / '.luoshu-payload-next'
        self.fonts = self.stage / 'system/fonts'
        self.fonts.mkdir(parents=True)
        (self.module / 'config').mkdir()
        env = {'LUOSHU_BUILD_KEY': 'routing-test'}
        for part in batch.PARTS:
            root = self.root / 'stock' / part
            root.mkdir(parents=True)
            env[f'LUOSHU_{part.upper()}_FONTS_ROOT'] = str(root)
        self.patch = patch.dict(os.environ, env)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.slots = {}

    def stock(self, name, points, families=('sans-serif',)):
        path = self.root / 'stock/system' / name
        make_font(path, points)
        fmt, metrics = inventory._read_metrics(path)
        logical = '/system/fonts/' + name
        self.slots[logical] = {'slotName': name, 'path': logical,
                               'families': list(families), 'format': fmt, 'metrics': metrics}
        return self.slots[logical]

    def build(self, names=None):
        (self.module / 'config/device_font_inventory.json').write_text(json.dumps({
            'schema': inventory.SCHEMA, 'inventoryRevision': 1, 'metricsRevision': 3,
            'state': 'ready', 'buildKey': 'routing-test', 'slots': self.slots}))
        with patch.object(TTFont, 'getGlyphSet', side_effect=AssertionError('rebuild outlines')):
            result = batch.build(self.module, self.stage,
                                 names or [Path(logical).name for logical in self.slots])
        self.reports = {entry['slot']: entry for entry in json.loads(
            (self.stage / '.luoshu-metrics-report.json').read_text())['slots']}
        return result

    def default_pair(self, cff=False, variable=False):
        make_font(self.fonts / '400.ttf', cff=cff, variable=variable, uvs=True)
        self.stock('Roboto-Regular.ttf', (LATIN, 48))
        self.stock('MiSansVF.ttf', DEFAULT_POINTS, ('mi-sans',))

    def assert_routing_and_raw_tables(self, cff=False, variable=False):
        self.default_pair(cff, variable)
        result = self.build()
        self.assertEqual(result, {'mapped': 2, 'generated': 2, 'fallbackSlots': 0})
        with TTFont(self.fonts / '400.ttf', lazy=True) as source, \
                TTFont(self.fonts / 'Roboto-Regular.ttf', lazy=True) as primary, \
                TTFont(self.fonts / 'MiSansVF.ttf', lazy=True) as fallback:
            self.assertIn(HAN, source.getBestCmap(), 'pre-fix primary would take CJK')
            self.assertNotIn(HAN, primary.getBestCmap())
            self.assertIn(HAN, fallback.getBestCmap())
            self.assertNotIn(OTHER_HAN, primary.getBestCmap())
            self.assertNotIn(PUNCT, primary.getBestCmap())
            for cp in (LATIN, 48, 0xFF11, EMOJI):
                self.assertEqual(primary.getBestCmap()[cp], source.getBestCmap()[cp])
            for tag in ('glyf', 'loca', 'CFF ', 'CFF2', 'gvar'):
                if tag in source:
                    self.assertEqual(primary.reader[tag], source.reader[tag], tag)
                    self.assertEqual(fallback.reader[tag], source.reader[tag], tag)
            uvs = next(table for table in primary['cmap'].tables if table.format == 14)
            self.assertEqual(uvs.uvsDict[0xFE00], [(LATIN, None), (EMOJI, None), (UVS_HAN, None)])
            self.assertIn(UVS_HAN, primary.getBestCmap(), 'unproven Han variation must stay usable')
            fallback_uvs = next(table for table in fallback['cmap'].tables if table.format == 14)
            self.assertIn((UVS_HAN, None), fallback_uvs.uvsDict[0xFE00])
        report = self.reports['/system/fonts/Roboto-Regular.ttf']
        self.assertEqual(report['removedCjkMappings'], 3)
        self.assertEqual(report['cjkRoutingSource'], 'stock-fallback')
        self.assertEqual(report['layoutBoundsSource'], 'stock')

    def test_ttf_cjk_routes_to_fallback_and_raw_gvar_survives(self):
        self.assert_routing_and_raw_tables(variable=True)

    def test_cff_cjk_routes_to_fallback_without_recompiling_cff(self):
        self.assert_routing_and_raw_tables(cff=True)

    def test_dali_dynamic_overlay_uses_verified_roboto_metrics_and_han_fallback(self):
        # dali OS3.0.305 ROM init copies stock Roboto into theme_webview; the
        # scanner resolves this known dynamic alias back to immutable Roboto.
        # Reproduce its measured metrics without redistributing the ROM font.
        self.default_pair()
        overlay = self.stock('MiSansVF_Overlay.ttf', (LATIN, 48), ())
        overlay['metricsReferencePath'] = '/system/fonts/Roboto-Regular.ttf'
        metrics = overlay['metrics']
        metrics['upem'] = 2048
        metrics['head'].update(yMin=-555, yMax=2163)
        metrics['hhea'].update(ascent=1900, descent=-500, lineGap=0)
        metrics['os2'].update(typoAscender=2146, typoDescender=-555, typoLineGap=0,
                              winAscent=2146, winDescent=555, fsSelection=64)
        self.build()
        report = self.reports['/system/fonts/MiSansVF_Overlay.ttf']
        self.assertEqual(report['cjkRoutingReason'], 'stock-latin-primary')
        self.assertGreater(report['removedCjkMappings'], 0)
        with TTFont(self.fonts / 'MiSansVF_Overlay.ttf', lazy=True) as out, \
                TTFont(self.fonts / 'MiSansVF.ttf', lazy=True) as han, \
                TTFont(self.fonts / '400.ttf', lazy=True) as source:
            self.assertEqual((out['hhea'].ascent, out['hhea'].descent), (928, -244))
            self.assertEqual((out['head'].yMin, out['head'].yMax), (-244, 1056))
            self.assertNotIn(HAN, out.getBestCmap())
            self.assertIn(HAN, han.getBestCmap())
            self.assertIn(48, out.getBestCmap(), 'selected digits must remain replaced')
            self.assertEqual(out.reader['glyf'], source.reader['glyf'])
            self.assertEqual(han.reader['glyf'], source.reader['glyf'])
        # A file with a similar name is not sufficient proof of the ROM link.
        del overlay['metricsReferencePath']
        self.assertFalse(batch._latin_ui_slot('/system/fonts/MiSansVF_Overlay.ttf', overlay))

    def test_old_inventory_keeps_cjk_and_reports_pending_scan(self):
        self.default_pair()
        for entry in self.slots.values():
            del entry['metrics']['coverage']
        self.build()
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertIn(HAN, font.getBestCmap())
        self.assertEqual(self.reports['/system/fonts/Roboto-Regular.ttf']['cjkRoutingReason'],
                         'stock-coverage-refresh-pending')

    def test_real_misans_latin_shared_zero_does_not_claim_chinese_repertoire(self):
        self.default_pair()
        make_font(self.fonts / '400.ttf', (*DEFAULT_POINTS, 0x3007))
        latin = self.stock('MiSansLatinVF.ttf', (LATIN, 48, 0x3007), ())
        self.assertTrue(latin['metrics']['coverage']['hasHan'])
        self.assertEqual(latin['metrics']['coverage']['hanCount'], 1)
        self.build()
        with TTFont(self.fonts / 'MiSansLatinVF.ttf') as font:
            self.assertNotIn(HAN, font.getBestCmap())
            self.assertNotIn(OTHER_HAN, font.getBestCmap())
            self.assertIn(0x3007, font.getBestCmap(), 'keep the original ideographic zero')
            self.assertIn(48, font.getBestCmap())
        self.assertEqual(self.reports['/system/fonts/MiSansLatinVF.ttf']['cjkRoutingReason'],
                         'stock-latin-primary')
        # Even one real stock ideograph remains sufficient to protect that slot.
        self.stock('MiSansLatinVF.ttf', (LATIN, 48, 0x3007, HAN), ())
        self.build()
        self.assertEqual(self.reports['/system/fonts/MiSansLatinVF.ttf']['cjkRoutingReason'],
                         'stock-han-slot')

    def test_no_staged_fallback_keeps_primary_han(self):
        self.default_pair()
        self.build(['Roboto-Regular.ttf'])
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertIn(HAN, font.getBestCmap())
        self.assertEqual(self.reports['/system/fonts/Roboto-Regular.ttf']['cjkRoutingReason'],
                         'no-staged-cjk-fallback')

    def test_unrelated_named_han_family_is_not_proof_of_system_fallback(self):
        make_font(self.fonts / '400.ttf')
        self.stock('Roboto-Regular.ttf', (LATIN, 48))
        self.stock('PrivateDisplay.ttf', DEFAULT_POINTS, ('private-display',))
        self.build()
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertIn(HAN, font.getBestCmap())
        self.assertEqual(self.reports['/system/fonts/Roboto-Regular.ttf']['cjkRoutingReason'],
                         'no-staged-cjk-fallback')

    def test_stock_han_fallback_with_latin_only_output_is_not_proof(self):
        self.default_pair()
        (self.fonts / '400.ttf').rename(self.fonts / 'Roboto-Regular.ttf')
        make_font(self.fonts / 'MiSansVF.ttf', (LATIN, 48, PUNCT))
        self.build()
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertIn(HAN, font.getBestCmap())
        self.assertEqual(self.reports['/system/fonts/Roboto-Regular.ttf']['removedCjkMappings'], 0)

    def test_cjk_primary_is_never_guessed_from_roboto_filename(self):
        self.default_pair()
        self.stock('Roboto-Regular.ttf', DEFAULT_POINTS)
        self.build()
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertIn(HAN, font.getBestCmap())

    def test_clock_mono_and_symbol_slots_keep_existing_routing(self):
        self.default_pair()
        for name in ('MiClock.otf', 'RobotoMono-Regular.ttf', 'RobotoSymbols.ttf'):
            self.stock(name, (LATIN, 48))
        self.build()
        for name in ('MiClock.otf', 'RobotoMono-Regular.ttf', 'RobotoSymbols.ttf'):
            with TTFont(self.fonts / name) as font:
                self.assertIn(HAN, font.getBestCmap())
            self.assertEqual(self.reports['/system/fonts/' + name]['cjkRoutingReason'],
                             'specialized-slot')

    def test_original_cjk_punctuation_is_preserved(self):
        self.default_pair()
        self.stock('Roboto-Regular.ttf', (LATIN, 48, PUNCT))
        self.build()
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertIn(PUNCT, font.getBestCmap())
            self.assertNotIn(HAN, font.getBestCmap())

    def test_only_codepoints_still_present_in_staged_fallback_are_removed(self):
        self.default_pair()
        (self.fonts / '400.ttf').rename(self.fonts / 'Roboto-Regular.ttf')
        make_font(self.fonts / 'MiSansVF.ttf', (LATIN, HAN))
        self.build()
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertNotIn(HAN, font.getBestCmap())
            self.assertIn(OTHER_HAN, font.getBestCmap())
            self.assertIn(PUNCT, font.getBestCmap())

    def freetype_index(self, path, codepoint, selector=None):
        ft = FreeType()
        face = C.POINTER(Face)()
        try:
            ft.check(ft.api.FT_New_Face(ft.library, bytes(path), 0, C.byref(face)), 'load cmap fixture')
            if selector is None:
                query = ft.api.FT_Get_Char_Index
                query.argtypes = [C.POINTER(Face), C.c_ulong]
                query.restype = C.c_uint
                return query(face, codepoint)
            query = ft.api.FT_Face_GetCharVariantIndex
            query.argtypes = [C.POINTER(Face), C.c_ulong, C.c_ulong]
            query.restype = C.c_uint
            return query(face, codepoint, selector)
        finally:
            if face:
                ft.check(ft.api.FT_Done_Face(face), 'close cmap fixture')
            ft.close()

    def test_conflicting_cmaps_do_not_claim_an_unreachable_fallback_glyph(self):
        self.default_pair()
        (self.fonts / '400.ttf').rename(self.fonts / 'Roboto-Regular.ttf')
        fallback_path = self.fonts / 'MiSansVF.ttf'
        make_font(fallback_path)
        with TTFont(fallback_path, recalcBBoxes=False) as font:
            for table in font['cmap'].tables:
                if table.format == 12:
                    del table.cmap[HAN]
            self.assertTrue(any(HAN in table.cmap for table in font['cmap'].tables
                                if table.format == 4))
            self.assertNotIn(HAN, font.getBestCmap())
            font.save(fallback_path)
        self.assertEqual(self.freetype_index(fallback_path, HAN), 0,
                         'default FreeType cmap must agree that the conflicting glyph is missing')
        self.build()
        self.assertGreater(self.freetype_index(self.fonts / 'Roboto-Regular.ttf', HAN), 0)
        self.assertEqual(self.freetype_index(fallback_path, HAN), 0)
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertIn(HAN, font.getBestCmap(), 'do not remove glyph visible only in secondary cmap')
            self.assertNotIn(OTHER_HAN, font.getBestCmap(), 'proven fallback glyph may still move')

    def test_nondefault_han_variation_and_base_survive_without_matching_fallback_uvs(self):
        self.default_pair()
        source = self.fonts / '400.ttf'
        with TTFont(source, recalcBBoxes=False) as font:
            table = next(table for table in font['cmap'].tables if table.format == 14)
            table.uvsDict[0xFE00] = [(LATIN, None), (EMOJI, None), (UVS_HAN, f'u{HAN:X}')]
            font.save(source)
        source.rename(self.fonts / 'Roboto-Regular.ttf')
        make_font(self.fonts / 'MiSansVF.ttf', uvs=False)
        before_variant = self.freetype_index(self.fonts / 'Roboto-Regular.ttf', UVS_HAN, 0xFE00)
        self.assertGreater(before_variant, 0)
        self.assertEqual(self.freetype_index(self.fonts / 'MiSansVF.ttf', UVS_HAN, 0xFE00), 0)
        self.build()
        primary = self.fonts / 'Roboto-Regular.ttf'
        self.assertGreater(self.freetype_index(primary, UVS_HAN), 0)
        self.assertEqual(self.freetype_index(primary, UVS_HAN, 0xFE00), before_variant)
        with TTFont(primary) as font:
            table = next(table for table in font['cmap'].tables if table.format == 14)
            self.assertIn((UVS_HAN, f'u{HAN:X}'), table.uvsDict[0xFE00])
            self.assertIn(UVS_HAN, font.getBestCmap())
            self.assertNotIn(HAN, font.getBestCmap(), 'ordinary Han still routes to proven fallback')

    def test_shared_three_argument_writer_does_not_change_coloros_routing(self):
        self.default_pair()
        contract = batch.contract_for_slot({'slots': self.slots}, '/system/fonts/Roboto-Regular.ttf')
        output = self.root / 'coloros-output.ttf'
        report = batch.write_metrics(self.fonts / '400.ttf', output, contract)
        with TTFont(output) as font:
            self.assertIn(HAN, font.getBestCmap())
        self.assertEqual(report['removedCjkMappings'], 0)

    def test_stock_coverage_is_read_from_actual_cmap_and_revision_two_is_stale(self):
        self.default_pair()
        latin = self.slots['/system/fonts/Roboto-Regular.ttf']['metrics']['coverage']
        cjk = self.slots['/system/fonts/MiSansVF.ttf']['metrics']['coverage']
        self.assertEqual((latin['hasHan'], latin['hasLatin'], latin['hanCount']), (False, True, 0))
        self.assertEqual((cjk['hasHan'], cjk['hanCount']), (True, 3))
        self.assertTrue(valid_coverage(latin))
        previous = {'metricsRevision': 2, 'slots': self.slots,
                    'mainSlot': self.slots['/system/fonts/Roboto-Regular.ttf']}
        self.assertFalse(scanner._has_current_metrics(previous))
        previous['metricsRevision'] = scanner.METRICS_REVISION
        self.assertTrue(scanner._has_current_metrics(previous))

    def test_host_freetype_primary_han_missing_and_fallback_han_renderable(self):
        ft = FreeType()
        self.addCleanup(ft.close)
        ft.api.FT_Get_Char_Index.argtypes = [C.POINTER(Face), C.c_ulong]
        ft.api.FT_Get_Char_Index.restype = C.c_uint
        for cff in (False, True):
            self.default_pair(cff=cff)
            self.build()
            found = []
            for name in ('Roboto-Regular.ttf', 'MiSansVF.ttf'):
                face = C.POINTER(Face)()
                ft.check(ft.api.FT_New_Face(ft.library, bytes(self.fonts / name), 0, C.byref(face)),
                         'load staged font')
                try:
                    found.append(ft.api.FT_Get_Char_Index(face, HAN))
                    self.assertGreater(ft.api.FT_Get_Char_Index(face, LATIN), 0)
                finally:
                    ft.check(ft.api.FT_Done_Face(face), 'close staged font')
            self.assertEqual(found[0], 0, 'primary must let Han fall through')
            self.assertGreater(found[1], 0, 'staged fallback must still render user Han')


if __name__ == '__main__':
    unittest.main()
