#!/usr/bin/env python3
"""Exercise the composite engine actually linked into the compatibility runtime."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables._f_v_a_r import Axis
from fontTools.varLib.builder import (buildVarData, buildVarIdxMap,
                                     buildVarRegionList, buildVarStore)
from fontTools.varLib.varStore import VarStoreInstancer

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / 'common/legacy_v14_4'
CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789中永国À'


def fixture(path, bottom=0, height=700, accent=800, cff=False, upem=1000):
    cmap = {ord(char): f'u{ord(char):04X}' for char in CHARS}
    order = ['.notdef', *cmap.values()]
    glyphs = {}
    for name in order:
        lo, hi = bottom, bottom + height
        if name in [cmap[ord(c)] for c in '中永国']:
            lo, hi = -80, 880
        elif name == cmap[ord('À')]:
            lo, hi = bottom, accent
        pen = T2CharStringPen(620, None) if cff else TTGlyphPen(None)
        pen.moveTo((50, lo)); pen.lineTo((550, lo))
        pen.lineTo((550, hi)); pen.lineTo((50, hi)); pen.closePath()
        glyphs[name] = pen.getCharString() if cff else pen.glyph()
    fb = FontBuilder(upem, isTTF=not cff)
    fb.setupGlyphOrder(order); fb.setupCharacterMap(cmap)
    if cff:
        fb.setupCFF('LayoutFixture', {'FullName': 'LayoutFixture'}, glyphs, {})
    else:
        fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (620, 50) for name in order})
    fb.setupHorizontalHeader(ascent=1000, descent=-300)
    fb.setupOS2(sTypoAscender=1000, sTypoDescender=-300,
               usWinAscent=1000, usWinDescent=300)
    fb.setupNameTable({'familyName': 'LayoutFixture', 'styleName': 'Regular'})
    fb.setupPost(); fb.setupMaxp(); fb.save(path)


def bounds(font, char):
    glyphs = font.getGlyphSet()
    pen = BoundsPen(glyphs)
    glyphs[font.getBestCmap()[ord(char)]].draw(pen)
    return pen.bounds


def add_metric_variations(path, explicit=False):
    """A base whose old letters and untouched CJK share +300 metric deltas."""
    with TTFont(path) as font:
        axis = Axis()
        axis.axisTag = 'wght'; axis.minValue = 100; axis.defaultValue = 400
        axis.maxValue = 900; axis.flags = 0; axis.axisNameID = 256
        font['fvar'] = newTable('fvar')
        font['fvar'].axes = [axis]; font['fvar'].instances = []
        order = font.getGlyphOrder()
        font['gvar'] = newTable('gvar')
        font['gvar'].version = 1; font['gvar'].reserved = 0
        font['gvar'].variations = {name: [] for name in order}
        for tag, fields in (
            ('HVAR', ('AdvWidthMap', 'LsbMap', 'RsbMap')),
            ('VVAR', ('AdvHeightMap', 'TsbMap', 'BsbMap', 'VOrgMap')),
        ):
            variation = newTable(tag)
            variation.table = getattr(ot, tag)()
            table = variation.table
            table.Version = 0x10000
            table.VarStore = buildVarStore(
                buildVarRegionList([{'wght': (0, 1, 1)}], ['wght']),
                [buildVarData([0], [[300] for _ in order])])
            for field in fields:
                # Shared maps catch accidental mutation of a delta used by CJK.
                setattr(table, field, buildVarIdxMap([0] * len(order), order)
                        if explicit or field != fields[0] else None)
            font[tag] = variation
        font.save(path)


def metric_delta(font, tag, field, char, weight):
    table = font[tag].table
    name = font.getBestCmap()[ord(char)]
    mapping = getattr(table, field)
    index = mapping[name] if mapping is not None else font.getGlyphID(name)
    return VarStoreInstancer(table.VarStore, font['fvar'].axes, {'wght': weight})[index]


class LegacyCompositeLayoutTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'base.ttf'
        self.latin = self.root / 'latin.ttf'
        self.digit = self.root / 'digit.ttf'
        self.output = self.root / 'output.ttf'
        fixture(self.base)
        fixture(self.latin, bottom=180, height=800, accent=1600)
        fixture(self.digit, bottom=150, height=750)

    def build(self, runtime=False, current=False):
        engine = (ROOT / 'common' if current else LEGACY) / 'composite_font.py'
        if runtime:
            common = self.root / 'runtime/common'
            common.mkdir(parents=True)
            engine = common / 'composite_font.py'
            engine.symlink_to(LEGACY / 'composite_font.py')
            for helper in ('composite_layout.py',):
                if (LEGACY / helper).exists():
                    (common / helper).symlink_to(LEGACY / helper)
        result = subprocess.run([sys.executable, str(engine), '--cjk', str(self.base),
            '--latin', str(self.latin), '--digit', str(self.digit), '--output', str(self.output)],
            env=os.environ.copy(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        font = TTFont(self.output)
        self.addCleanup(font.close)
        return font

    def test_runtime_aligns_raised_latin_and_digits(self):
        font = self.build(runtime=True)
        for char in 'HIE147':
            self.assertLessEqual(abs(bounds(font, char)[1]), 1, char)
            self.assertTrue(650 <= bounds(font, char)[3] <= 750, char)

    def test_new_accent_ink_is_enclosed_by_global_bounds(self):
        font = self.build()
        accent = bounds(font, 'À')
        self.assertGreaterEqual(font['head'].yMax, accent[3])
        self.assertLessEqual(font['head'].yMin, accent[1])
        with TTFont(self.base) as source:
            name = source.getBestCmap()[ord('中')]
            self.assertEqual(source['glyf'][name].compile(source['glyf']),
                             font['glyf'][name].compile(font['glyf']))

    def test_cff_base_aligns_and_updates_both_bounding_boxes(self):
        fixture(self.base, cff=True)
        font = self.build()
        self.assertLessEqual(abs(bounds(font, '1')[1]), 1)
        self.assertGreaterEqual(font['head'].yMax, bounds(font, 'À')[3])
        self.assertGreaterEqual(font['CFF '].cff.topDictIndex[0].FontBBox[3], bounds(font, 'À')[3])

    def test_flat_source_does_not_inherit_raised_base_ascii(self):
        fixture(self.base, bottom=150)
        fixture(self.latin); fixture(self.digit)
        font = self.build()
        self.assertEqual(bounds(font, 'H')[1], 0)
        self.assertEqual(bounds(font, '1')[1], 0)

    def test_cff_donors_with_different_units_per_em(self):
        fixture(self.latin, bottom=360, height=1600, accent=3200, cff=True, upem=2000)
        fixture(self.digit, bottom=300, height=1500, cff=True, upem=2000)
        font = self.build()
        for char in 'H147':
            self.assertLessEqual(abs(bounds(font, char)[1]), 1, char)
            self.assertTrue(650 <= bounds(font, char)[3] <= 750, char)
        self.assertGreaterEqual(font['head'].yMax, bounds(font, 'À')[3])

    def assert_static_imports_keep_cjk_variations(self, explicit, current=False):
        add_metric_variations(self.base, explicit=explicit)
        with TTFont(self.base) as original:
            before_tables = {tag: original.reader[tag] for tag in ('HVAR', 'VVAR')}
            name = original.getBestCmap()[ord('A')]
            self.assertEqual(original.getGlyphSet(location={'wght': 900})[name].width, 920)
        font = self.build(current=current)
        for char in 'AH01':
            name = font.getBestCmap()[ord(char)]
            advance = font['hmtx'][name][0]
            for weight in (100, 400, 650, 900):
                with self.subTest(char=char, weight=weight):
                    self.assertEqual(font.getGlyphSet(location={'wght': weight})[name].width, advance)
        for tag, fields in (
            ('HVAR', ('AdvWidthMap', 'LsbMap', 'RsbMap')),
            ('VVAR', ('AdvHeightMap', 'TsbMap', 'BsbMap', 'VOrgMap')),
        ):
            for field in fields:
                self.assertEqual(metric_delta(font, tag, field, 'A', 1), 0)
                self.assertEqual(metric_delta(font, tag, field, '1', 1), 0)
                self.assertEqual(metric_delta(font, tag, field, '中', 1), 300)
                self.assertEqual(metric_delta(font, tag, field, '中', 0), 0)
                self.assertEqual(metric_delta(font, tag, field, '中', .5), 150)
        cjk_name = font.getBestCmap()[ord('中')]
        self.assertEqual(font.getGlyphSet(location={'wght': 400})[cjk_name].width, 620)
        self.assertEqual(font.getGlyphSet(location={'wght': 900})[cjk_name].width, 920)
        with TTFont(self.base) as source:
            for tag in before_tables:
                self.assertEqual(source.reader[tag], before_tables[tag], 'source font mutated')

    def test_implicit_variable_metrics_are_detached_from_imported_glyphs(self):
        self.assert_static_imports_keep_cjk_variations(explicit=False)

    def test_shared_variable_metrics_preserve_untouched_cjk(self):
        self.assert_static_imports_keep_cjk_variations(explicit=True)

    def test_current_composite_engine_keeps_the_same_metric_isolation(self):
        self.assert_static_imports_keep_cjk_variations(explicit=False, current=True)

    def test_freetype_uses_static_donor_advances_at_variable_weights(self):
        from hyperos_layout_freetype_test import C, Face, FreeType
        fixture(self.latin); fixture(self.digit)
        add_metric_variations(self.base)
        font = self.build()
        font.close()
        freetype = FreeType()
        self.addCleanup(freetype.close)
        api = freetype.api
        api.FT_Set_Var_Design_Coordinates.argtypes = [C.POINTER(Face), C.c_uint,
                                                      C.POINTER(C.c_long)]
        api.FT_Set_Var_Design_Coordinates.restype = C.c_int
        for path in (self.base, self.output):
            face = C.POINTER(Face)()
            freetype.check(api.FT_New_Face(freetype.library, bytes(path), 0, C.byref(face)),
                           'load variable composite')
            try:
                for weight in (400, 900):
                    coordinates = (C.c_long * 1)(weight * 65536)
                    freetype.check(api.FT_Set_Var_Design_Coordinates(face, 1, coordinates),
                                   'select variable weight')
                    for char in 'A1中':
                        freetype.check(api.FT_Load_Char(face, ord(char), 1 | 2 | 8),
                                       'read unscaled variable glyph advance')
                        expected = 920 if weight == 900 and (path == self.base or char == '中') else 620
                        self.assertEqual(face.contents.glyph.contents.metrics.horiAdvance, expected)
            finally:
                freetype.check(api.FT_Done_Face(face), 'close variable composite')


if __name__ == '__main__':
    unittest.main()
