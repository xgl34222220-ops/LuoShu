#!/usr/bin/env python3
"""Real outlines and HarfBuzz shaping for selective stock supplementation."""
from pathlib import Path
import ctypes as C
from ctypes.util import find_library
import tempfile
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from fontTools.fontBuilder import FontBuilder
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont, TTCollection, newTable
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.ttLib.tables._k_e_r_n import KernTable_format_0
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.builder import buildVarRegionList, buildVarData, buildVarStore
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.otlLib.builder import buildMathTable
from fontTools.cffLib.CFFToCFF2 import convertCFFToCFF2
from fontTools.cffLib import SubrsIndex
from fontTools.misc.psCharStrings import T2CharString
from inventory_font_supplement import supplement, SupplementError, UnsupportedSupplementError, _merged_cff_table, _cff_global_layout, _subset, plan_stock_glyph_union, _cache_prepared_source
from fontTools.misc.psCharStrings import calcSubrBias


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

    def test_required_layout_features_from_both_fonts_remain_required(self):
        fixture(self.source, source=True); fixture(self.stock)
        for path, expression in ((self.source, 'sub A by B;'), (self.stock, 'sub alpha by beta;')):
            with TTFont(path) as font:
                addOpenTypeFeaturesFromString(font, 'languagesystem DFLT dflt; languagesystem grek dflt; '
                                              'feature rlig {' + expression + '} rlig;')
                table = font['GSUB'].table
                for record in table.ScriptList.ScriptRecord:
                    system = record.Script.DefaultLangSys
                    system.ReqFeatureIndex = system.FeatureIndex[0]
                    system.FeatureIndex = []; system.FeatureCount = 0
                font.save(path)
        supplement(self.source, self.stock, self.output)
        self.assertEqual(shape(self.source, 'AB0'), shape(self.output, 'AB0'))
        self.assertEqual(shape(self.stock, 'ΑΒ'), shape(self.output, 'ΑΒ'))
        with TTFont(self.output) as font:
            for record in font['GSUB'].table.ScriptList.ScriptRecord:
                self.assertNotEqual(record.Script.DefaultLangSys.ReqFeatureIndex, 0xFFFF)

    def test_post3_serialization_preserves_retained_components_and_shaping(self):
        # No glyph names are persisted. Removing the replaced Latin cmap entry
        # changes the retained Greek component A to glyph00001 on reopening.
        # This reproduced the exact Test6 on-device exception.
        for stock_post, donor_post in ((3, 2), (3, 3), (2, 3)):
            with self.subTest(stock_post=stock_post, donor_post=donor_post):
                fixture(self.source, source=True); fixture(self.stock)
                for path, post in ((self.stock, stock_post), (self.source, donor_post)):
                    with TTFont(path) as font:
                        font['post'].formatType = post
                        font.save(path)
                supplement(self.source, self.stock, self.output)
                with TTFont(self.stock) as stock, TTFont(self.source) as source, TTFont(self.output) as result:
                    for cp in (65, 66, 48):
                        self.assertEqual(outline(source, source.getBestCmap()[cp]),
                                         outline(result, result.getBestCmap()[cp]))
                    for cp in (0x391, 0x392, 0x410, 0x627, 0x628):
                        self.assertEqual(outline(stock, stock.getBestCmap()[cp]),
                                         outline(result, result.getBestCmap()[cp]))
                self.assertEqual(shape(self.stock, 'ΑΒ'), shape(self.output, 'ΑΒ'))
                self.assertEqual(shape(self.stock, 'بَا'), shape(self.output, 'بَا'))

    def test_serialized_layout_references_keep_stock_math_base_kern_and_uvs(self):
        for stock_cff, source_cff, cid in ((False, False, False), (False, True, False),
                                           (True, True, False), (True, True, True)):
            with self.subTest(stock_cff=stock_cff, source_cff=source_cff, cid=cid):
                fixture(self.source, source=True, cff=source_cff)
                fixture(self.stock, cff=stock_cff)
                with TTFont(self.stock) as font:
                    # Keep the existing GSUB/GPOS while adding BASE. Rebuilding
                    # features in place would remove the Arabic shaping test.
                    other = TTFont(self.stock)
                    addOpenTypeFeaturesFromString(other, '''table BASE {
HorizAxis.BaseTagList romn;
HorizAxis.BaseScriptList latn romn 0;
} BASE;''')
                    font['BASE'] = other['BASE']; other.close()
                    coord = font['BASE'].table.HorizAxis.BaseScriptList.BaseScriptRecord[0].BaseScript.BaseValues.BaseCoord[0]
                    coord.Format, coord.ReferenceGlyph, coord.BaseCoordPoint = 2, 'B', 0
                    buildMathTable(font, italicsCorrections={'alpha': 47},
                                   vertGlyphVariants={'alpha': [('alpha', 700), ('B', 900)]})
                    kern = newTable('kern'); kern.version = 0
                    pairs = KernTable_format_0(); pairs.version = 0; pairs.coverage = 1
                    pairs.kernTable = {('alpha', 'beta'): -37, ('alpha', 'B'): -41}
                    kern.kernTables = [pairs]; font['kern'] = kern
                    uvs = CmapSubtable.newSubtable(14)
                    uvs.platformID, uvs.platEncID, uvs.language = 0, 5, 0
                    uvs.cmap = {}; uvs.uvsDict = {0xFE00: [(65, None)]}
                    font['cmap'].tables.append(uvs)
                    font['post'].formatType = 3
                    if cid:
                        font['CFF '] = _merged_cff_table([font])
                    font.recalcBBoxes = False
                    font.save(self.stock)
                supplement(self.source, self.stock, self.output)
                with TTFont(self.stock) as stock, TTFont(self.output) as result:
                    coord = result['BASE'].table.HorizAxis.BaseScriptList.BaseScriptRecord[0].BaseScript.BaseValues.BaseCoord[0]
                    self.assertEqual(outline(stock, stock.getBestCmap()[66]), outline(result, coord.ReferenceGlyph))
                    self.assertNotEqual(coord.ReferenceGlyph, result.getBestCmap()[66])
                    math = result['MATH'].table
                    variant = math.MathVariants.VertGlyphConstruction[0].MathGlyphVariantRecord[1].VariantGlyph
                    self.assertEqual(outline(stock, stock.getBestCmap()[66]), outline(result, variant))
                    correction = math.MathGlyphInfo.MathItalicsCorrectionInfo
                    self.assertEqual(correction.ItalicsCorrection[0].Value, 47)
                    self.assertEqual(outline(stock, stock.getBestCmap()[0x391]),
                                     outline(result, correction.Coverage.glyphs[0]))
                    pair = next(pair for pair, value in result['kern'].kernTables[0].kernTable.items() if value == -41)
                    self.assertEqual(outline(stock, stock.getBestCmap()[0x391]), outline(result, pair[0]))
                    self.assertEqual(outline(stock, stock.getBestCmap()[66]), outline(result, pair[1]))
                    variant = next(t for t in result['cmap'].tables if t.format == 14).uvsDict[0xFE00][0][1]
                    self.assertEqual(outline(stock, stock.getBestCmap()[65]), outline(result, variant))
                    self.assertNotEqual(variant, result.getBestCmap()[65])
                self.assertEqual(shape(self.stock, 'بَا'), shape(self.output, 'بَا'))

    def test_unusual_glyph_names_and_collision_suffixes_keep_numeric_identity(self):
        fixture(self.source, source=True); fixture(self.stock)
        rename = {'.notdef': 'missing.glyph', 'A': 'glyph00001', 'B': '.notdef.1',
                  'alpha': 'glyph00001.1', 'beta': 'glyph00001.2'}
        for path in (self.source, self.stock):
            # Set names before the binary tables are decoded, so every glyph-ID
            # reference follows the deliberately unusual persisted post names.
            with TTFont(path) as font:
                font.setGlyphOrder([rename.get(name, name) for name in font.getGlyphOrder()])
                font.save(path)
        supplement(self.source, self.stock, self.output)
        with TTFont(self.source) as source, TTFont(self.stock) as stock, TTFont(self.output) as result:
            for cp in stock.getBestCmap():
                expected = source if cp in source.getBestCmap() else stock
                self.assertEqual(outline(expected, expected.getBestCmap()[cp]),
                                 outline(result, result.getBestCmap()[cp]))
            self.assertEqual(len(result.getGlyphOrder()), len(set(result.getGlyphOrder())))
            self.assertEqual(outline(stock, stock.getGlyphOrder()[0]), outline(result, result.getGlyphOrder()[0]))
        self.assertEqual(shape(self.stock, 'ΑΒ'), shape(self.output, 'ΑΒ'))
        self.assertEqual(shape(self.stock, 'بَا'), shape(self.output, 'بَا'))

    def test_source_legacy_kern_uses_renamed_source_glyphs_after_merge(self):
        fixture(self.source, source=True); fixture(self.stock)
        with TTFont(self.source) as font:
            kern = newTable('kern'); kern.version = 0
            pairs = KernTable_format_0(); pairs.version = 0; pairs.coverage = 1
            pairs.kernTable = {('A', 'B'): -89}
            kern.kernTables = [pairs]; font['kern'] = kern
            font['post'].formatType = 3
            font.save(self.source)
        with TTFont(self.stock) as font:
            font['post'].formatType = 3
            font.save(self.stock)
        supplement(self.source, self.stock, self.output)
        with TTFont(self.output) as result:
            self.assertEqual(result['kern'].kernTables[-1].kernTable,
                             {(result.getBestCmap()[65], result.getBestCmap()[66]): -89})
        self.assertEqual(shape(self.source, 'AB'), shape(self.output, 'AB'))

    def test_cid_vertical_origins_follow_serialized_stock_and_source_glyph_ids(self):
        fixture(self.source, source=True, cff=True); fixture(self.stock, cff=True)
        for path, default, overrides in (
                (self.stock, 880, {'alpha': 910, 'beta': 920}),
                (self.source, 980, {'A': 1030, 'B': 1040})):
            with TTFont(path) as font:
                builder = FontBuilder(font=font)
                builder.setupVerticalMetrics({name: (1100, 130) for name in font.getGlyphOrder()})
                builder.setupVerticalHeader(ascent=950, descent=-300)
                table = newTable('VORG'); table.majorVersion, table.minorVersion = 1, 0
                table.defaultVertOriginY = default; table.VOriginRecords = overrides
                font['VORG'] = table
                font['CFF '] = _merged_cff_table([font])
                font['post'].formatType = 3
                font.recalcBBoxes = False
                font.save(path)
        supplement(self.source, self.stock, self.output)
        with TTFont(self.stock) as stock, TTFont(self.source) as source, TTFont(self.output) as result:
            table = result['VORG']
            for cp in (65, 66, 48, 0x391, 0x392, 0x627):
                expected = source if cp in source.getBestCmap() else stock
                expected_name, actual_name = expected.getBestCmap()[cp], result.getBestCmap()[cp]
                self.assertEqual(expected['VORG'].VOriginRecords.get(expected_name, expected['VORG'].defaultVertOriginY),
                                 table.VOriginRecords.get(actual_name, table.defaultVertOriginY))
                self.assertEqual(expected['vmtx'].metrics[expected_name], result['vmtx'].metrics[actual_name])
                self.assertEqual(outline(expected, expected_name), outline(result, actual_name))

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

    def test_prepared_source_cache_reuses_conversion_without_reusing_stock_layout(self):
        fixture(self.source, source=True); fixture(self.stock, cff=True)
        cache = {}
        first = supplement(self.source, self.stock, self.output, prepared_cache=cache)
        expected = shape(self.output, 'AB0ΑΒ')
        self.assertFalse(first['preparedSourceCacheHit'])
        self.assertGreater(first['convertedSourceGlyphs'], 0)
        second = supplement(self.source, self.stock, self.output, prepared_cache=cache)
        self.assertTrue(second['preparedSourceCacheHit'])
        self.assertEqual(first['convertedSourceGlyphs'], second['convertedSourceGlyphs'])
        self.assertEqual(expected, shape(self.output, 'AB0ΑΒ'))
        self.assertEqual(shape(self.stock, 'باَ'), shape(self.output, 'باَ'))
        # Same path, new font contents: a path-only key would use stale glyphs.
        fixture(self.source, source=True, upem=2000)
        third = supplement(self.source, self.stock, self.output, prepared_cache=cache)
        self.assertFalse(third['preparedSourceCacheHit'])
        self.assertNotEqual(expected, shape(self.output, 'AB0ΑΒ'))

    def test_prepared_source_cache_cannot_cross_requested_repertoires(self):
        fixture(self.source, source=True); fixture(self.stock, cff=True)
        cache = {}
        supplement(self.source, self.stock, self.output, prepared_cache=cache, replace_codepoints={65})
        report = supplement(self.source, self.stock, self.output, prepared_cache=cache, replace_codepoints={66})
        self.assertFalse(report['preparedSourceCacheHit'])
        with TTFont(self.stock) as stock, TTFont(self.source) as source, TTFont(self.output) as result:
            self.assertEqual(outline(stock, stock.getBestCmap()[65]), outline(result, result.getBestCmap()[65]))
            self.assertEqual(outline(source, source.getBestCmap()[66]), outline(result, result.getBestCmap()[66]))

    def test_proven_nonfitting_prepared_font_is_not_serialized(self):
        fixture(self.source, source=True, cff=True)
        with TTFont(self.source) as font:
            font._luoshu_encoded_cff_size = len(font.getTableData('CFF '))
            # The cache's recorded byte budget is authoritative; no large
            # allocation is needed to exercise a one-byte budget shortfall.
            cache = {'outline_entries': {'used': {
                'size': 64 * 1024 * 1024 - font._luoshu_encoded_cff_size + 1}}}
            with patch.object(font, 'save', side_effect=AssertionError('nonfitting cache serialized font')):
                _cache_prepared_source(cache, 'target', font, 0)
            self.assertNotIn('entries', cache)

    def test_outline_cache_shares_conversion_but_not_regional_scope_or_vertical_contract(self):
        fixture(self.source, source=True); fixture(self.stock, cff=True)
        for path in (self.source, self.stock):
            with TTFont(path) as font:
                for table in font['cmap'].tables:
                    if table.isUnicode():
                        table.cmap.update({cp: 'A' for cp in range(0x100, 0x118)})
                font.save(path)
        cache = {}
        requested = set(range(0x100, 0x118)) | {32, 48, 65, 66}
        for index, excluded in enumerate((65, 66)):
            with TTFont(self.stock) as font:
                builder = FontBuilder(font=font)
                builder.setupVerticalMetrics({name: (1100, 130 + 211 * index)
                                              for name in font.getGlyphOrder()})
                builder.setupVerticalHeader(ascent=950 + index, descent=-300)
                table = newTable('VORG'); table.majorVersion, table.minorVersion = 1, 0
                table.defaultVertOriginY = 880; table.VOriginRecords = {}
                font['VORG'] = table
                font.save(self.stock)
            report = supplement(self.source, self.stock, self.output, prepared_cache=cache,
                                replace_codepoints=requested - {excluded})
            self.assertFalse(report['preparedSourceCacheHit'])
            self.assertEqual(report['outlineSourceCacheHit'], bool(index))
            with TTFont(self.stock) as stock, TTFont(self.source) as source, TTFont(self.output) as result:
                points = result.getBestCmap()
                for cp in (65, 66, 0x100):
                    expected = stock if cp == excluded else source
                    self.assertEqual(outline(expected, expected.getBestCmap()[cp]), outline(result, points[cp]))
                    if cp != excluded:
                        glyphs = result.getGlyphSet(); pen = BoundsPen(glyphs)
                        glyphs[points[cp]].draw(pen)
                        expected_origin = round(pen.bounds[3] + 130 + 211 * index)
                        self.assertEqual(result['VORG'].VOriginRecords.get(
                            points[cp], result['VORG'].defaultVertOriginY), expected_origin)
            self.assertEqual(shape(self.stock, 'باَ'), shape(self.output, 'باَ'))
        self.assertEqual(len(cache['outline_entries']), 1)
        self.assertLessEqual(sum(item['size'] for item in cache['outline_entries'].values())
                             + sum(len(item[0]) for item in cache['entries'].values()), 64 * 1024 * 1024)

    def test_capacity_fallback_keeps_every_character_and_selector_without_cache_leakage(self):
        start, source_count, stock_count = 0x20000, 35000, 40000
        def large_font(path, count, width):
            names = ['.notdef', *(f'g{i}' for i in range(count))]
            builder = FontBuilder(1000, isTTF=True)
            builder.setupGlyphOrder(names)
            builder.setupCharacterMap({start + i: f'g{i}' for i in range(count)})
            empty = TTGlyphPen(None).glyph()
            builder.setupGlyf({name: empty for name in names})
            builder.setupHorizontalMetrics({name: (width, 0) for name in names})
            builder.setupHorizontalHeader(ascent=900, descent=-250)
            builder.setupOS2(sTypoAscender=900, sTypoDescender=-250,
                            usWinAscent=900, usWinDescent=250, usWeightClass=400)
            builder.setupNameTable({'familyName': 'Capacity', 'styleName': 'Regular'})
            builder.setupPost(); builder.setupMaxp(); builder.save(path)
        large_font(self.source, source_count, 700)
        large_font(self.stock, stock_count, 600)
        with TTFont(self.source) as font:
            table = CmapSubtable.newSubtable(14)
            table.platformID, table.platEncID, table.language = 0, 5, 0
            table.cmap = {}; table.uvsDict = {0xE0100: [(start, 'g1')]}
            font['cmap'].tables.append(table); font.save(self.source)
        cache = {}
        for index, selector in enumerate((0xE0100, 0xE0101)):
            with TTFont(self.stock) as font:
                font['cmap'].tables = [table for table in font['cmap'].tables if table.format != 14]
                table = CmapSubtable.newSubtable(14)
                table.platformID, table.platEncID, table.language = 0, 5, 0
                table.cmap = {}
                table.uvsDict = {selector: [(start + i, f'g{i}') for i in range(30000)] + [
                    (start + source_count, None), (start + source_count + 1, 'g39999')]}
                font['cmap'].tables.append(table); font.save(self.stock)
            report = supplement(self.source, self.stock, self.output, prepared_cache=cache,
                                replace_codepoints=set(range(start, start + source_count)))
            expected_fallbacks = 29999 if index == 0 else 30000
            self.assertEqual(report['selectedVariantFallbacks'], expected_fallbacks)
            self.assertEqual(report['selectedVariantFallbackSource'], 'selected-base-glyph')
            self.assertEqual(report['preparedSourceCacheHit'], bool(index))
            with TTFont(self.output) as result:
                self.assertEqual(set(result.getBestCmap()), set(range(start, start + stock_count)))
                self.assertLessEqual(len(result.getGlyphOrder()), 65535)
                variants = {(vs, cp): glyph for table in result['cmap'].tables if table.format == 14
                            for vs, entries in table.uvsDict.items() for cp, glyph in entries}
                expected_pairs = {(selector, start + i) for i in range(30000)} | {
                    (selector, start + source_count), (selector, start + source_count + 1), (0xE0100, start)}
                self.assertEqual(set(variants), expected_pairs)
                self.assertEqual(variants[(selector, start + 100)] or result.getBestCmap()[start + 100],
                                 result.getBestCmap()[start + 100])
                self.assertIsNone(variants[(selector, start + source_count)])
                self.assertEqual(result['hmtx'].metrics[variants[(selector, start + source_count + 1)]][0], 600)
                self.assertEqual(result['hmtx'].metrics[variants[(0xE0100, start)]][0], 700)
                for cp, advance in ((start, 700), (start + source_count, 600)):
                    self.assertEqual(result['hmtx'].metrics[result.getBestCmap()[cp]][0], advance)

    def test_identical_vertical_tables_with_regional_cmap_do_not_share_prepared_metrics(self):
        fixture(self.source, source=True); fixture(self.stock, cff=True)
        with TTFont(self.stock) as font:
            builder = FontBuilder(font=font)
            metrics = {name: (1100, 130) for name in font.getGlyphOrder()}
            metrics['B'] = (1100, 330)
            builder.setupVerticalMetrics(metrics)
            builder.setupVerticalHeader(ascent=950, descent=-300)
            table = newTable('VORG'); table.majorVersion, table.minorVersion = 1, 0
            table.defaultVertOriginY = 880; table.VOriginRecords = {}
            font['VORG'] = table; font.save(self.stock)
        cache, vertical_tables = {}, None
        for index in range(2):
            if index:
                with TTFont(self.stock) as font:
                    for table in font['cmap'].tables:
                        if table.isUnicode() and table.format != 14:
                            table.cmap[65], table.cmap[66] = 'B', 'A'
                    font.save(self.stock)
            with TTFont(self.stock) as font:
                actual_tables = (font.getTableData('vhea'), font.getTableData('vmtx'))
                if vertical_tables is not None:
                    self.assertEqual(actual_tables, vertical_tables)
                vertical_tables = actual_tables
            report = supplement(self.source, self.stock, self.output, prepared_cache=cache)
            self.assertFalse(report['preparedSourceCacheHit'])
            self.assertEqual(report['outlineSourceCacheHit'], bool(index))
            with TTFont(self.output) as result:
                name = result.getBestCmap()[65]
                self.assertEqual(result['vmtx'].metrics[name], (1100, 330 if index else 130))
                self.assertEqual(result['VORG'].VOriginRecords.get(name, result['VORG'].defaultVertOriginY),
                                 750 if index else 550)

    def test_vertical_rounding_boundary_uses_exact_serialized_cff_curve(self):
        fixture(self.source, source=True); fixture(self.stock, cff=True)
        with TTFont(self.source) as font:
            pen = TTGlyphPen(None)
            pen.moveTo((0, 0)); pen.qCurveTo((100, 1), (200, 0)); pen.closePath()
            font['glyf']['A'] = pen.glyph(); font.save(self.source)
        with TTFont(self.stock) as font:
            builder = FontBuilder(font=font)
            builder.setupVerticalMetrics({name: (1100, 130) for name in font.getGlyphOrder()})
            builder.setupVerticalHeader(ascent=950, descent=-300)
            table = newTable('VORG'); table.majorVersion, table.minorVersion = 1, 0
            table.defaultVertOriginY = 880; table.VOriginRecords = {}
            font['VORG'] = table; font.save(self.stock)
        cache = {}
        for _ in range(2):
            supplement(self.source, self.stock, self.output, prepared_cache=cache)
            with TTFont(self.output) as result:
                glyphs = result.getGlyphSet(); name = result.getBestCmap()[65]
                pen = BoundsPen(glyphs); glyphs[name].draw(pen)
                self.assertEqual(result['VORG'].VOriginRecords.get(name, result['VORG'].defaultVertOriginY),
                                 round(pen.bounds[3] + result['vmtx'].metrics[name][1]))

    def test_collection_union_shares_outlines_while_preserving_regional_mapping_and_shaping(self):
        fixture(self.source, source=True); fixture(self.stock, cff=True)
        with TTFont(self.stock) as font:
            font['CFF '] = _merged_cff_table([font])
            font['post'].formatType = 3; font.recalcBBoxes = False; font.save(self.stock)
        collection = TTCollection(); collection.fonts = [TTFont(self.stock), TTFont(self.stock)]
        regional = collection.fonts[1]
        replacement = regional.getBestCmap()[65]
        for table in regional['cmap'].tables:
            if table.isUnicode() and table.format != 14:
                table.cmap[0x391] = replacement
        path = self.root / 'regional.ttc'; collection.save(path)
        for font in collection.fonts:
            font.close()
        plan = plan_stock_glyph_union(self.source, path, [0, 1], {65, 66, 48}, 400)
        self.assertIsNotNone(plan)
        outputs = []
        for index in range(2):
            baseline, result = self.root / f'independent-{index}.otf', self.root / f'union-{index}.otf'
            supplement(self.source, path, baseline, stock_face_index=index, replace_codepoints={65, 66, 48})
            report = supplement(self.source, path, result, stock_face_index=index,
                replace_codepoints={65, 66, 48}, retained_stock_glyphs=plan)
            self.assertEqual(report['sharedStockGlyphCount'], len(plan))
            with TTFont(baseline) as reference, TTFont(result) as actual:
                for cp, name in reference.getBestCmap().items():
                    self.assertEqual(outline(reference, name), outline(actual, actual.getBestCmap()[cp]))
                    self.assertEqual(reference['hmtx'].metrics[name], actual['hmtx'].metrics[actual.getBestCmap()[cp]])
            for text in ('AB0ΑΒ', 'باَ'):
                self.assertEqual(shape(baseline, text), shape(result, text))
            outputs.append(result)
        with TTFont(outputs[0]) as first, TTFont(outputs[1]) as second:
            self.assertEqual(first.getTableData('CFF '), second.getTableData('CFF '))
            self.assertNotEqual(first.getTableData('cmap'), second.getTableData('cmap'))
        # Equal file names or glyph counts cannot prove metric compatibility.
        changed = TTCollection(path)
        name = changed.fonts[1].getGlyphOrder()[1]
        width, lsb = changed.fonts[1]['hmtx'].metrics[name]
        changed.fonts[1]['hmtx'].metrics[name] = (width + 1, lsb)
        incompatible = self.root / 'different-metrics.ttc'; changed.save(incompatible)
        for font in changed.fonts:
            font.close()
        self.assertIsNone(plan_stock_glyph_union(self.source, incompatible, [0, 1], {65, 66, 48}, 400))

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

    def test_variable_source_retains_real_gvar_hvar_and_avar_across_weights(self):
        fixture(self.source, source=True); fixture(self.stock)
        for path in (self.source, self.stock):
            with TTFont(path) as font:
                builder = FontBuilder(font=font)
                builder.setupVerticalMetrics({name: (1000, 80) for name in font.getGlyphOrder()})
                builder.setupVerticalHeader(ascent=900, descent=-250)
                font.save(path)
        with TTFont(self.source) as font:
            builder = FontBuilder(font=font)
            builder.setupFvar([('wght', 100, 400, 900, 'Weight')], [])
            supports = [{'wght': (-1, -1, 0)}, {'wght': (0, 1, 1)}]
            variations = {}
            for name in font.getGlyphOrder():
                count = len(font['glyf'][name].getCoordinates(font['glyf'])[0])
                variations[name] = [TupleVariation(support, [(index * x, x) for index in range(count)] +
                                                   [(0, 0), (advance, 0), (0, 0), (0, -advance // 2)])
                                    for support, x, advance in zip(supports, (-20, 80), (-60, 120))]
            builder.setupGvar(variations)
            font['avar'] = newTable('avar')
            font['avar'].segments = {'wght': {-1: -1, 0: 0, 0.6: 0.8, 1: 1}}
            hvar = newTable('HVAR'); hvar.table = otTables.HVAR()
            hvar.table.Version = 0x10000
            hvar.table.VarStore = buildVarStore(buildVarRegionList(supports, ['wght']),
                                               [buildVarData([0, 1], [[-60, 120] for _ in font.getGlyphOrder()])])
            hvar.table.AdvWidthMap = hvar.table.LsbMap = hvar.table.RsbMap = None
            font['HVAR'] = hvar
            vvar = newTable('VVAR'); vvar.table = otTables.VVAR()
            vvar.table.Version = 0x10000
            vvar.table.VarStore = buildVarStore(buildVarRegionList(supports, ['wght']),
                                               [buildVarData([0, 1], [[-30, 60] for _ in font.getGlyphOrder()])])
            vvar.table.AdvHeightMap = vvar.table.TsbMap = vvar.table.BsbMap = vvar.table.VOrgMap = None
            font['VVAR'] = vvar
            font['post'].formatType = 3
            font.save(self.source)
        cache = {}
        for cached in (False, True):
            report = supplement(self.source, self.stock, self.output, prepared_cache=cache)
            self.assertEqual(report['preservedAxes'], ['wght'])
            self.assertEqual(report['preparedSourceCacheHit'], cached)
            widths = []
            for weight in (100, 400, 700, 900):
                with TTFont(self.source) as source, TTFont(self.stock) as stock, TTFont(self.output) as result:
                    self.assertEqual(source['avar'].segments, result['avar'].segments)
                    source = instantiateVariableFont(source, {'wght': weight}, inplace=True)
                    result = instantiateVariableFont(result, {'wght': weight}, inplace=True)
                    for cp in (65, 66, 48):
                        expected, actual = source.getBestCmap()[cp], result.getBestCmap()[cp]
                        self.assertEqual(outline(source, expected), outline(result, actual))
                        self.assertEqual(source['hmtx'][expected], result['hmtx'][actual])
                        self.assertEqual(source['vmtx'][expected], result['vmtx'][actual])
                    widths.append(result['hmtx'][result.getBestCmap()[65]][0])
                    for cp in (0x391, 0x392, 0x410, 0x627, 0x628):
                        expected, actual = stock.getBestCmap()[cp], result.getBestCmap()[cp]
                        self.assertEqual(outline(stock, expected), outline(result, actual))
                        self.assertEqual(stock['hmtx'][expected], result['hmtx'][actual])
                        self.assertEqual(stock['vmtx'][expected], result['vmtx'][actual])
                    instance = self.root / f'instance-{weight}.ttf'
                    result.save(instance)
                    self.assertEqual(shape(self.stock, 'باَ'), shape(instance, 'باَ'))
                    self.assertEqual(shape(self.stock, 'ΑΒ'), shape(instance, 'ΑΒ'))
            self.assertEqual(len(set(widths)), 4)

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

    def test_cff_bias_boundaries_keep_largest_program_bytes_and_both_shapes(self):
        # A realistic CJK subset can cross either Type2 bias boundary. Global
        # pool order may change; stock-first glyph IDs and both outlines cannot.
        for stock_count, source_count in ((1239, 1), (33899, 1), (1, 1240), (0, 2), (0, 1240), (1, 1)):
            with self.subTest(stock_count=stock_count, source_count=source_count):
                fixture(self.stock, cff=True); fixture(self.source, source=True, cff=True)
                fonts = [TTFont(self.stock), TTFont(self.source)]
                try:
                    expected, original_bytes = [], []
                    for font, count, x in zip(fonts, (stock_count, source_count), (35, 170)):
                        cff = font['CFF '].cff
                        top, global_subrs = cff[0], cff.GlobalSubrs
                        private = top.Private
                        global_subrs.items = [T2CharString(bytecode=b'\x0b', private=private,
                                                         globalSubrs=global_subrs) for _ in range(count)]
                        path = [x, 70, 'rmoveto', 100, 0, 0, 220, -100, -220, 'rlineto']
                        if count:
                            global_subrs.items[0] = T2CharString(program=[*path, 'return'],
                                                                private=private, globalSubrs=global_subrs)
                            program = [600, -calcSubrBias(global_subrs), 'callgsubr', 'endchar']
                        else:
                            program = [600, *path, 'endchar']
                        char = T2CharString(program=program, private=private, globalSubrs=global_subrs)
                        pen = RecordingPen(); char.draw(pen); expected.append(pen.value)
                        char.compile(); original_bytes.append(char.bytecode)
                        # Reload raw bytes: preserving names alone cannot prove
                        # that the expensive large program was left untouched.
                        top.CharStrings['A'] = T2CharString(bytecode=char.bytecode, private=private,
                                                           globalSubrs=global_subrs)
                    stock_size = len(fonts[0].getGlyphOrder())
                    glyph_ids = [fonts[0].getGlyphID('A'), stock_size + fonts[1].getGlyphID('A')]
                    offsets, count = _cff_global_layout(fonts)
                    unchanged = (not stock_count or
                        calcSubrBias(range(stock_count)) + offsets[0] == calcSubrBias(range(count)))
                    self.assertEqual(unchanged, stock_count != 33899)
                    raw = _merged_cff_table(fonts)
                    with TTFont(recalcBBoxes=False) as container:
                        table = newTable('CFF '); table.decompile(raw.data, container)
                        top = table.cff[0]
                        for i, gid in enumerate(glyph_ids):
                            char = top.CharStrings[top.charset[gid]]
                            if i == 0 and unchanged:
                                self.assertEqual(char.bytecode, original_bytes[0])
                            pen = RecordingPen(); char.draw(pen)
                            self.assertEqual(pen.value, expected[i])
                finally:
                    for font in fonts:
                        font.close()

    def test_cid_subset_keeps_raw_programs_without_executing_type2_interpreter(self):
        fixture(self.stock, cff=True)
        with TTFont(self.stock) as font:
            cff = font['CFF '].cff
            cff.GlobalSubrs.append(T2CharString(bytecode=b'\x0b', globalSubrs=cff.GlobalSubrs))
            font['CFF '] = _merged_cff_table([font])
            font['post'].formatType = 3
            font.recalcBBoxes = False
            font.save(self.stock)
        requested = {65, 48, 0x391}
        with TTFont(self.stock, lazy=True, recalcBBoxes=False) as font:
            before = {cp: font['CFF '].cff[0].CharStrings[font.getBestCmap()[cp]].bytecode for cp in requested}
            with patch.object(T2CharString, 'decompile', side_effect=AssertionError('unexpected Type2 decoding')):
                _subset(font, requested)
                font.save(self.output, reorderTables=False)
        with TTFont(self.output) as result:
            self.assertEqual(set(result.getBestCmap()), requested)
            self.assertEqual(len(result['CFF '].cff.GlobalSubrs), 1)
            for cp in requested:
                self.assertEqual(result['CFF '].cff[0].CharStrings[result.getBestCmap()[cp]].bytecode, before[cp])

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

    def test_public_post3_dejavu_preserves_math_outlines_shaping_and_hint_programs(self):
        path = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        if not path.is_file():
            self.skipTest('public DejaVu fixture unavailable')
        with TTFont(path) as font:
            upem = font['head'].unitsPerEm
            font['post'].formatType = 3
            font.save(self.stock)
        fixture(self.source, source=True, upem=upem)
        supplement(self.source, self.stock, self.output, replace_codepoints={65, 66, 48})
        self.assertEqual(shape(self.stock, 'العَرَبِيَّة'), shape(self.output, 'العَرَبِيَّة'))
        self.assertEqual(shape(self.stock, 'ΑΒΓДЖ'), shape(self.output, 'ΑΒΓДЖ'))
        with TTFont(self.stock) as stock, TTFont(self.output) as result, TTFont(self.source) as source:
            for cp in (65, 66, 48):
                self.assertEqual(outline(source, source.getBestCmap()[cp]), outline(result, result.getBestCmap()[cp]))
            for cp in (set(stock.getBestCmap()) - {65, 66, 48}):
                self.assertEqual(outline(stock, stock.getBestCmap()[cp]), outline(result, result.getBestCmap()[cp]))
            self.assertIn('MATH', result)
            self.assertIn('kern', result)
            for tag in ('fpgm', 'prep', 'cvt '):
                self.assertEqual(stock.getTableData(tag), result.getTableData(tag))


if __name__ == '__main__':
    unittest.main()
