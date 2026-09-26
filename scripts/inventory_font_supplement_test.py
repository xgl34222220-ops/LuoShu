#!/usr/bin/env python3
"""Real outlines and HarfBuzz shaping for selective stock supplementation."""
from pathlib import Path
import ctypes as C
from ctypes.util import find_library
import tempfile
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from fontTools.fontBuilder import FontBuilder
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont, TTCollection
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.cffLib.CFFToCFF2 import convertCFFToCFF2
from fontTools.cffLib import SubrsIndex
from fontTools.misc.psCharStrings import T2CharString
from inventory_font_supplement import supplement, SupplementError, UnsupportedSupplementError, _merged_cff_table


def fixture(path, *, source=False, cff=False, upem=1000, cff2=False):
    points = {65: 'A', 66: 'B', 48: 'zero', 32: 'space'}
    if not source:
        points.update({0x391: 'alpha', 0x392: 'beta', 0x410: 'cyrillic',
                       0x627: 'alef', 0x628: 'beh', 0x64E: 'mark'})
    names = ['.notdef', *points.values()]
    if not source:
        names.extend(['alef.fina', 'beh.init', 'arabicLigature'])
    builder = FontBuilder(upem, isTTF=not cff)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap(points)
    outlines = {}
    for index, name in enumerate(names):
        pen = T2CharStringPen(600, None, roundTolerance=0) if cff else TTGlyphPen(None)
        if name not in {'.notdef', 'space'}:
            x, y = (100, 100) if source else (10 + index * 3, -20)
            pen.moveTo((x, y)); pen.lineTo((x + (150 if source else 300), y))
            pen.lineTo((x + 100, y + (320 if source else 700))); pen.closePath()
        outlines[name] = pen.getCharString() if cff else pen.glyph()
    if not cff and not source:
        # The preserved Greek outline depends on the original A, whose Unicode
        # mapping is replaced. The merger must keep this component independent.
        pen = TTGlyphPen(outlines)
        pen.addComponent('A', (1, 0, 0, 1, 70, 50))
        outlines['alpha'] = pen.glyph()
    if cff:
        builder.setupCFF('SupplementFixture', {}, outlines, {})
    else:
        builder.setupGlyf(outlines)
    builder.setupHorizontalMetrics({name: (0 if name == 'mark' else 600, 10) for name in names})
    builder.setupHorizontalHeader(ascent=900, descent=-250)
    builder.setupOS2(sTypoAscender=900, sTypoDescender=-250,
                    usWinAscent=900, usWinDescent=250, usWeightClass=400)
    builder.setupNameTable({'familyName': 'Selected' if source else 'Stock', 'styleName': 'Regular'})
    builder.setupPost(); builder.setupMaxp()
    if not source:
        addOpenTypeFeaturesFromString(builder.font, '''
languagesystem DFLT dflt;
languagesystem grek dflt;
languagesystem arab dflt;
feature init { script arab; sub beh by beh.init; } init;
feature fina { script arab; sub alef by alef.fina; } fina;
feature rlig { script arab; sub beh.init alef.fina by arabicLigature; } rlig;
feature kern { script grek; pos alpha beta -73; } kern;
markClass mark <anchor 100 200> @TOP;
feature mark { script arab; pos base arabicLigature <anchor 300 800> mark @TOP;
pos base beh <anchor 200 700> mark @TOP; } mark;
''')
    if cff2:
        convertCFFToCFF2(builder.font)
    builder.save(path)


def outline(font, name):
    glyphs = font.getGlyphSet()
    pen = DecomposingRecordingPen(glyphs)
    glyphs[name].draw(pen)
    return pen.value


class Info(C.Structure):
    _fields_ = [('codepoint', C.c_uint32), ('mask', C.c_uint32), ('cluster', C.c_uint32),
                ('var1', C.c_uint32), ('var2', C.c_uint32)]


class Position(C.Structure):
    _fields_ = [('x_advance', C.c_int32), ('y_advance', C.c_int32),
                ('x_offset', C.c_int32), ('y_offset', C.c_int32), ('var', C.c_uint32)]


def shape(path, text):
    library = find_library('harfbuzz')
    if not library:
        raise unittest.SkipTest('host HarfBuzz shared library unavailable')
    hb = C.CDLL(library)
    for name, args, result in [
        ('hb_blob_create', [C.c_char_p, C.c_uint, C.c_int, C.c_void_p, C.c_void_p], C.c_void_p),
        ('hb_face_create', [C.c_void_p, C.c_uint], C.c_void_p),
        ('hb_font_create', [C.c_void_p], C.c_void_p),
        ('hb_ot_font_set_funcs', [C.c_void_p], None),
        ('hb_font_set_scale', [C.c_void_p, C.c_int, C.c_int], None),
        ('hb_buffer_create', [], C.c_void_p),
        ('hb_buffer_add_utf8', [C.c_void_p, C.c_char_p, C.c_int, C.c_uint, C.c_int], None),
        ('hb_buffer_guess_segment_properties', [C.c_void_p], None),
        ('hb_shape', [C.c_void_p, C.c_void_p, C.c_void_p, C.c_uint], None),
        ('hb_buffer_get_glyph_infos', [C.c_void_p, C.POINTER(C.c_uint)], C.POINTER(Info)),
        ('hb_buffer_get_glyph_positions', [C.c_void_p, C.POINTER(C.c_uint)], C.POINTER(Position)),
        ('hb_buffer_destroy', [C.c_void_p], None), ('hb_font_destroy', [C.c_void_p], None),
        ('hb_face_destroy', [C.c_void_p], None), ('hb_blob_destroy', [C.c_void_p], None),
    ]:
        method = getattr(hb, name); method.argtypes = args; method.restype = result
    data = path.read_bytes()
    blob = hb.hb_blob_create(data, len(data), 0, None, None)
    face = hb.hb_face_create(blob, 0); font = hb.hb_font_create(face)
    buffer = hb.hb_buffer_create()
    try:
        with TTFont(path) as tt:
            upem = tt['head'].unitsPerEm
            hb.hb_ot_font_set_funcs(font); hb.hb_font_set_scale(font, upem, upem)
            raw = text.encode('utf-8')
            hb.hb_buffer_add_utf8(buffer, raw, len(raw), 0, len(raw))
            hb.hb_buffer_guess_segment_properties(buffer)
            hb.hb_shape(font, buffer, None, 0)
            length = C.c_uint()
            infos = hb.hb_buffer_get_glyph_infos(buffer, C.byref(length))
            positions = hb.hb_buffer_get_glyph_positions(buffer, C.byref(length))
            order = tt.getGlyphOrder()
            return [(outline(tt, order[infos[i].codepoint]), positions[i].x_advance,
                     positions[i].y_advance, positions[i].x_offset, positions[i].y_offset,
                     infos[i].cluster) for i in range(length.value)]
    finally:
        hb.hb_buffer_destroy(buffer); hb.hb_font_destroy(font)
        hb.hb_face_destroy(face); hb.hb_blob_destroy(blob)


class SupplementTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source, self.stock, self.output = (self.root / name for name in ('source.ttf', 'stock.ttf', 'out.otf'))

    def prepare(self, source_cff=False, stock_cff=False, cff2=False):
        fixture(self.source, source=True, cff=source_cff, cff2=cff2)
        fixture(self.stock, cff=stock_cff)
        return supplement(self.source, self.stock, self.output, replace_codepoints={65, 66, 48})

    def test_ttf_replaces_real_shapes_without_mutating_stock_composite_dependencies(self):
        report = self.prepare()
        self.assertEqual(report['replacedCodepoints'], 3)
        self.assertEqual(report['retainedStockCodepoints'], 7)
        with TTFont(self.source) as donor, TTFont(self.stock) as stock, TTFont(self.output) as result:
            self.assertEqual(set(stock.getBestCmap()), set(result.getBestCmap()))
            for cp in (65, 66, 48):
                self.assertEqual(outline(donor, donor.getBestCmap()[cp]), outline(result, result.getBestCmap()[cp]))
                self.assertNotEqual(outline(stock, stock.getBestCmap()[cp]), outline(result, result.getBestCmap()[cp]))
            for cp in (0x391, 0x410, 0x627, 0x628):
                self.assertEqual(outline(stock, stock.getBestCmap()[cp]), outline(result, result.getBestCmap()[cp]))

    def test_greek_kerning_and_arabic_ligatures_marks_shape_identically(self):
        self.prepare()
        self.assertEqual(shape(self.stock, '\u0391\u0392'), shape(self.output, '\u0391\u0392'))
        self.assertEqual(shape(self.stock, '\u0628\u0627\u064e'), shape(self.output, '\u0628\u0627\u064e'))
        self.assertLess(shape(self.stock, '\u0391\u0392')[0][1], 600)
        self.assertLess(len(shape(self.stock, '\u0628\u0627')), 2)

    def test_cff_same_outline_and_cff_source_ttf_stock_keep_unreplaced_shaping(self):
        for source_cff, stock_cff in ((True, True), (True, False), (False, True)):
            with self.subTest(source_cff=source_cff, stock_cff=stock_cff):
                self.prepare(source_cff, stock_cff)
                self.assertEqual(shape(self.stock, '\u0628\u0627\u064e'), shape(self.output, '\u0628\u0627\u064e'))
                with TTFont(self.source) as donor, TTFont(self.output) as result:
                    self.assertIn('CFF ', result)
                    self.assertEqual(outline(donor, donor.getBestCmap()[65]), outline(result, result.getBestCmap()[65]))

    def test_static_cff2_source_is_supported_without_converting_unselected_glyphs(self):
        report = self.prepare(True, False, True)
        self.assertEqual(report['actualFormat'], 'OTF')
        self.assertEqual(report['convertedSourceGlyphs'], 4)
        self.assertEqual(shape(self.stock, '\u0628\u0627'), shape(self.output, '\u0628\u0627'))

    def test_original_font_files_are_unchanged(self):
        fixture(self.source, source=True); fixture(self.stock)
        before = (self.source.read_bytes(), self.stock.read_bytes())
        supplement(self.source, self.stock, self.output)
        self.assertEqual(before, (self.source.read_bytes(), self.stock.read_bytes()))

    def test_exact_collection_face_is_used(self):
        fixture(self.source, source=True); fixture(self.stock)
        alternate = self.root / 'other.ttf'
        fixture(alternate, source=True)
        collection = TTCollection()
        collection.fonts = [TTFont(alternate), TTFont(self.stock)]
        path = self.root / 'stock.ttc'
        collection.save(path)
        for font in collection.fonts:
            font.close()
        report = supplement(self.source, path, self.output, stock_face_index=1)
        self.assertGreater(report['retainedStockCodepoints'], 0)
        self.assertEqual(shape(self.stock, '\u0628\u0627'), shape(self.output, '\u0628\u0627'))
        with self.assertRaises(SupplementError):
            supplement(self.source, path, self.output)

    def test_alternate_stock_cmap_entries_remain_reachable_in_output(self):
        fixture(self.source, source=True); fixture(self.stock)
        with TTFont(self.stock) as font:
            preferred = CmapSubtable.newSubtable(12)
            preferred.platformID, preferred.platEncID, preferred.language = 3, 10, 0
            preferred.cmap = dict(font.getBestCmap())
            for table in font['cmap'].tables:
                if table.format == 4:
                    table.cmap[0x3A9] = 'B'
            font['cmap'].tables.append(preferred)
            font.save(self.stock)
        supplement(self.source, self.stock, self.output)
        with TTFont(self.stock) as stock, TTFont(self.output) as result:
            self.assertNotIn(0x3A9, stock.getBestCmap())
            self.assertIn(0x3A9, result.getBestCmap())
            self.assertEqual(outline(stock, 'B'), outline(result, result.getBestCmap()[0x3A9]))

    def test_missing_source_variation_sequence_keeps_original_variant_shape(self):
        fixture(self.source, source=True); fixture(self.stock)
        with TTFont(self.stock) as font:
            uvs = CmapSubtable.newSubtable(14)
            uvs.platformID, uvs.platEncID, uvs.language = 0, 5, 0
            uvs.cmap = {}; uvs.uvsDict = {0xFE00: [(65, None)]}
            font['cmap'].tables.append(uvs)
            font.save(self.stock)
        report = supplement(self.source, self.stock, self.output)
        self.assertEqual(report['retainedStockUvsRecords'], 1)
        with TTFont(self.stock) as stock, TTFont(self.output) as result:
            variant = next(t for t in result['cmap'].tables if t.format == 14).uvsDict[0xFE00][0][1]
            self.assertIsNotNone(variant)
            self.assertEqual(outline(stock, 'A'), outline(result, variant))
            self.assertNotEqual(outline(result, variant), outline(result, result.getBestCmap()[65]))

    def test_variable_source_is_rejected_instead_of_silently_pinning_default_weight(self):
        fixture(self.source, source=True); fixture(self.stock)
        with TTFont(self.source) as font:
            builder = FontBuilder(font=font)
            builder.setupFvar([('wght', 100, 400, 900, 'Weight')], [])
            builder.setupGvar({name: [] for name in font.getGlyphOrder()})
            font.save(self.source)
        with self.assertRaisesRegex(UnsupportedSupplementError, 'lose its axes'):
            supplement(self.source, self.stock, self.output)
        self.assertFalse(self.output.exists())

    def test_cid_cff_local_and_global_subroutines_keep_independent_programs(self):
        fixture(self.source, source=True, cff=True); fixture(self.stock, cff=True)
        for path, x in ((self.source, 170), (self.stock, 35)):
            with TTFont(path) as font:
                cff = font['CFF '].cff
                private = cff[0].Private
                global_subrs = cff.GlobalSubrs
                global_subrs.append(T2CharString(
                    program=[x, 70, 'rmoveto', 100, 0, 0, 220, -100, -220, 'rlineto', 'return'],
                    private=private, globalSubrs=global_subrs))
                private.Subrs = SubrsIndex()
                private.Subrs.append(T2CharString(program=[-107, 'callgsubr', 'return'],
                                                 private=private, globalSubrs=global_subrs))
                names = ['A'] if path == self.source else ['A', 'alpha']
                for name in names:
                    cff[0].CharStrings[name] = T2CharString(program=[600, -107, 'callsubr', 'endchar'],
                                                         private=private, globalSubrs=global_subrs)
                font['CFF '] = _merged_cff_table([font])
                font['post'].formatType = 3.0
                font.recalcBBoxes = False
                font.save(path)
        report = supplement(self.source, self.stock, self.output)
        self.assertEqual(report['convertedStockGlyphs'], 0)
        self.assertEqual(report['convertedSourceGlyphs'], 0)
        with TTFont(self.source) as source, TTFont(self.stock) as stock, TTFont(self.output) as result:
            self.assertEqual(outline(source, source.getBestCmap()[65]), outline(result, result.getBestCmap()[65]))
            self.assertEqual(outline(stock, stock.getBestCmap()[0x391]), outline(result, result.getBestCmap()[0x391]))
            self.assertEqual(len(result['CFF '].cff[0].FDArray), 2)
        self.assertEqual(shape(self.stock, 'ΑΒ'), shape(self.output, 'ΑΒ'))

    def test_stock_baseline_table_keeps_original_glyph_point_reference(self):
        fixture(self.source, source=True); fixture(self.stock)
        with TTFont(self.stock) as font:
            addOpenTypeFeaturesFromString(font, '''table BASE {
HorizAxis.BaseTagList romn;
HorizAxis.BaseScriptList latn romn 0;
} BASE;''')
            coord = font['BASE'].table.HorizAxis.BaseScriptList.BaseScriptRecord[0].BaseScript.BaseValues.BaseCoord[0]
            coord.Format = 2
            coord.ReferenceGlyph = 'B'
            coord.BaseCoordPoint = 0
            font.save(self.stock)
        supplement(self.source, self.stock, self.output)
        with TTFont(self.stock) as stock, TTFont(self.output) as result:
            coord = result['BASE'].table.HorizAxis.BaseScriptList.BaseScriptRecord[0].BaseScript.BaseValues.BaseCoord[0]
            self.assertEqual(coord.Format, 2)
            self.assertEqual(coord.BaseCoordPoint, 0)
            self.assertEqual(outline(stock, 'B'), outline(result, coord.ReferenceGlyph))
            self.assertNotEqual(coord.ReferenceGlyph, result.getBestCmap()[66])

    def test_named_cff_seac_components_expand_before_cid_serialization(self):
        fixture(self.source, source=True, cff=True); fixture(self.stock, cff=True)
        with TTFont(self.source) as font:
            cff = font['CFF '].cff
            cff[0].CharStrings['B'] = T2CharString(program=[600, 50, 90, 65, 65, 'endchar'],
                                                private=cff[0].Private, globalSubrs=cff.GlobalSubrs)
            font.save(self.source)
        report = supplement(self.source, self.stock, self.output)
        self.assertEqual(report['convertedSourceGlyphs'], 1)
        with TTFont(self.source) as source, TTFont(self.output) as result:
            self.assertEqual(outline(source, source.getBestCmap()[66]), outline(result, result.getBestCmap()[66]))

    def test_explicit_stock_weight_controls_stock_instance_independently(self):
        fixture(self.source, source=True); fixture(self.stock)
        with TTFont(self.stock) as font:
            builder = FontBuilder(font=font)
            builder.setupFvar([('wght', 100, 400, 900, 'Weight')], [])
            builder.setupGvar({name: [] for name in font.getGlyphOrder()})
            font.save(self.stock)
        report = supplement(self.source, self.stock, self.output, stock_weight=700)
        self.assertEqual(report['sourceWeight'], 400)
        self.assertEqual(report['stockWeight'], 700)
        self.assertEqual(report['stockInstanceAxes'], {'wght': 700})

    def test_public_dejavu_arabic_and_marks_preserve_real_outlines_and_positions(self):
        path = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        if not path.is_file():
            self.skipTest('public DejaVu fixture unavailable')
        fixture(self.source, source=True)
        report = supplement(self.source, path, self.output, replace_codepoints={65, 66, 48})
        self.assertGreater(report['retainedStockCodepoints'], 5000)
        self.assertEqual(shape(path, 'العَرَبِيَّة'), shape(self.output, 'العَرَبِيَّة'))
        with TTFont(path) as stock, TTFont(self.output) as result:
            self.assertIn('MATH', result)
            self.assertIn('kern', result)
            for tag in ('fpgm', 'prep', 'cvt '):
                self.assertEqual(stock.getTableData(tag), result.getTableData(tag))


if __name__ == '__main__':
    unittest.main()
