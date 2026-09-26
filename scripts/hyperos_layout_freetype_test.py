#!/usr/bin/env python3
"""Load staged fonts with host FreeType; this is not an Android device test.

The public FreeType ABI is used through ctypes, so this check needs neither
freetype-py nor Pillow. It skips explicitly when the host has no FreeType.
"""
import ctypes as C
from ctypes.util import find_library
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
import hyperos_metrics_batch as batch


# Prefixes of the public FT_FaceRec and FT_GlyphSlotRec structs. Stop after the
# last field inspected; FreeType itself owns and allocates the full records.
class Generic(C.Structure):
    _fields_ = [('data', C.c_void_p), ('finalizer', C.c_void_p)]


class Vector(C.Structure):
    _fields_ = [('x', C.c_long), ('y', C.c_long)]


class BBox(C.Structure):
    _fields_ = [(name, C.c_long) for name in ('xMin', 'yMin', 'xMax', 'yMax')]


class GlyphMetrics(C.Structure):
    _fields_ = [(name, C.c_long) for name in (
        'width', 'height', 'horiBearingX', 'horiBearingY', 'horiAdvance',
        'vertBearingX', 'vertBearingY', 'vertAdvance')]


class Bitmap(C.Structure):
    _fields_ = [('rows', C.c_uint), ('width', C.c_uint), ('pitch', C.c_int),
                ('buffer', C.POINTER(C.c_ubyte)), ('num_grays', C.c_ushort),
                ('pixel_mode', C.c_ubyte), ('palette_mode', C.c_ubyte),
                ('palette', C.c_void_p)]


class Outline(C.Structure):
    _fields_ = [('n_contours', C.c_short), ('n_points', C.c_short),
                ('points', C.POINTER(Vector)), ('tags', C.POINTER(C.c_ubyte)),
                ('contours', C.POINTER(C.c_short)), ('flags', C.c_int)]


class GlyphSlot(C.Structure):
    _fields_ = [('library', C.c_void_p), ('face', C.c_void_p),
                ('next', C.c_void_p), ('glyph_index', C.c_uint),
                ('generic', Generic), ('metrics', GlyphMetrics),
                ('linearHoriAdvance', C.c_long), ('linearVertAdvance', C.c_long),
                ('advance', Vector), ('format', C.c_uint), ('bitmap', Bitmap),
                ('bitmap_left', C.c_int), ('bitmap_top', C.c_int),
                ('outline', Outline)]


class Face(C.Structure):
    _fields_ = [(name, C.c_long) for name in (
        'num_faces', 'face_index', 'face_flags', 'style_flags', 'num_glyphs')] + [
        ('family_name', C.c_char_p), ('style_name', C.c_char_p),
        ('num_fixed_sizes', C.c_int), ('available_sizes', C.c_void_p),
        ('num_charmaps', C.c_int), ('charmaps', C.c_void_p), ('generic', Generic),
        ('bbox', BBox), ('units_per_EM', C.c_ushort), ('ascender', C.c_short),
        ('descender', C.c_short), ('height', C.c_short),
        ('max_advance_width', C.c_short), ('max_advance_height', C.c_short),
        ('underline_position', C.c_short), ('underline_thickness', C.c_short),
        ('glyph', C.POINTER(GlyphSlot))]


class FreeType:
    def __init__(self):
        name = find_library('freetype')
        if not name:
            raise unittest.SkipTest('host FreeType unavailable; Android rendering untested')
        try:
            self.api = C.CDLL(name)
        except OSError as error:
            raise unittest.SkipTest(f'host FreeType unavailable: {error}') from error
        api = self.api
        signatures = {
            'FT_Init_FreeType': [C.POINTER(C.c_void_p)],
            'FT_Done_FreeType': [C.c_void_p],
            'FT_New_Face': [C.c_void_p, C.c_char_p, C.c_long, C.POINTER(C.POINTER(Face))],
            'FT_Done_Face': [C.POINTER(Face)],
            'FT_Set_Pixel_Sizes': [C.POINTER(Face), C.c_uint, C.c_uint],
            'FT_Load_Char': [C.POINTER(Face), C.c_ulong, C.c_int32],
        }
        for name, arguments in signatures.items():
            getattr(api, name).argtypes = arguments
            getattr(api, name).restype = C.c_int
        self.library = C.c_void_p()
        self.check(api.FT_Init_FreeType(C.byref(self.library)), 'initialize FreeType')

    @staticmethod
    def check(result, operation):
        if result:
            raise AssertionError(f'FreeType failed to {operation}: error {result}')

    def close(self):
        self.check(self.api.FT_Done_FreeType(self.library), 'close library')

    def inspect(self, path):
        face = C.POINTER(Face)()
        self.check(self.api.FT_New_Face(self.library, bytes(path), 0, C.byref(face)),
                   f'load {path.name}')
        try:
            record = face.contents
            bounds = tuple(getattr(record.bbox, name) for name in ('xMin', 'yMin', 'xMax', 'yMax'))
            result = {'bbox': bounds, 'upem': record.units_per_EM,
                      'ascender': record.ascender, 'descender': record.descender,
                      'glyphs': {}}
            self.check(self.api.FT_Set_Pixel_Sizes(face, 0, 48), 'set raster size')
            for character in 'A02':
                # NO_SCALE | NO_HINTING | NO_BITMAP: retain actual design-space
                # points, independently from the face's declared layout bounds.
                self.check(self.api.FT_Load_Char(face, ord(character), 1 | 2 | 8), 'load outline')
                glyph = record.glyph.contents
                outline = glyph.outline
                points = tuple((outline.points[i].x, outline.points[i].y)
                               for i in range(outline.n_points))
                shape = (points, bytes(outline.tags[:outline.n_points]),
                         tuple(outline.contours[:outline.n_contours]))
                # RENDER | NO_HINTING: compare pixels, pen advance and bitmap
                # placement relative to the same baseline, not image top edges.
                self.check(self.api.FT_Load_Char(face, ord(character), 4 | 2), 'rasterize glyph')
                glyph = record.glyph.contents
                bitmap = glyph.bitmap
                raster = (bitmap.width, bitmap.rows, bitmap.pitch, bitmap.pixel_mode,
                          C.string_at(bitmap.buffer, abs(bitmap.pitch) * bitmap.rows),
                          glyph.bitmap_left, glyph.bitmap_top,
                          glyph.advance.x, glyph.advance.y)
                result['glyphs'][character] = (shape, raster)
            return result
        finally:
            self.check(self.api.FT_Done_Face(face), 'close font')


def fixture_font(path, upem, cff, latin_bottom=-80, combining_bottom=None, variable=False,
                 extra_codepoint=None, substitution=False):
    """Include a distant, unused glyph to model a large donor's global bounds."""
    names = ['.notdef', 'A', 'zero', 'two', 'unused.extreme']
    cmap = {65: 'A', 48: 'zero', 50: 'two'}
    if combining_bottom is not None:
        names.append('combining.low')
        cmap[0x323] = 'combining.low'
    if extra_codepoint is not None or substitution:
        names.append('extra.low')
        if extra_codepoint is not None:
            cmap[extra_codepoint] = 'extra.low'
    scale = upem / 1000
    width = round(600 * scale)
    fb = FontBuilder(upem, isTTF=not cff)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap(cmap)
    outlines = {}
    for name in names:
        pen = T2CharStringPen(width, None) if cff else TTGlyphPen(None)
        if name != '.notdef':
            bottom, top = (-500, 1500) if name == 'unused.extreme' else (latin_bottom, 720)
            if name == 'combining.low':
                bottom, top = combining_bottom, combining_bottom + 40
            if name == 'extra.low':
                bottom, top = -350, 720
            for method, point in (
                    ('moveTo', (0, bottom)), ('lineTo', (500, bottom)),
                    ('lineTo', (400, top)), ('lineTo', (100, top))):
                getattr(pen, method)(tuple(round(v * scale) for v in point))
            pen.closePath()
        outlines[name] = pen.getCharString() if cff else pen.glyph()
    fb.setupHorizontalMetrics({name: (width, 0) for name in names})
    fb.setupHorizontalHeader(ascent=round(1600 * scale), descent=round(-600 * scale))
    fb.setupNameTable({'familyName': 'FreeTypeLayoutFixture', 'styleName': 'Regular'})
    fb.setupOS2(sTypoAscender=round(1600 * scale), sTypoDescender=round(-600 * scale),
                usWinAscent=round(1700 * scale), usWinDescent=round(700 * scale))
    fb.setupPost()
    if cff:
        fb.setupCFF('FreeTypeLayoutFixture-Regular',
                    {'FullName': 'FreeType Layout Fixture', 'FamilyName': 'FreeTypeLayoutFixture',
                     'Weight': 'Regular'}, outlines, {})
    else:
        fb.setupGlyf(outlines)
        fb.setupMaxp()
    if variable:
        fb.setupFvar([('wght', 100, 400, 900, 'Weight')], [])
    if substitution:
        from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
        addOpenTypeFeaturesFromString(fb.font, 'feature liga { sub A A by extra.low; } liga;')
    fb.save(path)


def bitmap_span_baseline(font, pixels=48):
    """Model QQ's same-Paint bitmap span, not general Android span layout.

    QQ allocates ceil(bottom-top) pixels, draws text at -top, then bottom-aligns
    the bitmap to the line. The line uses this same face's effective descent.
    A line with other fallback faces can have different extents and is outside
    this regression model. Bitmap allocation can leave a subpixel difference.
    """
    scale = pixels / font['upem']
    top, bottom = -font['bbox'][3] * scale, -font['bbox'][1] * scale
    line_bottom = math.ceil(-font['descender'] * scale)
    bitmap_height = math.ceil(bottom - top)
    return line_bottom - bitmap_height - top


def table_bytes(path, tags):
    with TTFont(path, lazy=True) as font:
        return {tag: font.reader[tag] for tag in tags if tag in font}


class HyperOSLayoutFreeTypeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.freetype = FreeType()
        cls.addClassCleanup(cls.freetype.close)

    def assert_layout_contract(self, cff, upem, with_head=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / ('donor.otf' if cff else 'donor.ttf')
            output = root / ('staged.otf' if cff else 'staged.ttf')
            fixture_font(source, upem, cff)
            before_bytes = source.read_bytes()
            before = self.freetype.inspect(source)
            self.assertEqual(before['upem'], upem)
            self.assertTrue(before['glyphs']['A'][0][0], 'fixture has no outline')
            self.assertTrue(any(before['glyphs']['A'][1][4]), 'fixture raster is empty')
            metrics = {'upem': 1000,
                       'hhea': {'ascent': 1044, 'descent': -282, 'lineGap': 0},
                       'os2': {'typoAscender': 1044, 'typoDescender': -282,
                               'typoLineGap': 0, 'winAscent': 1044, 'winDescent': 282,
                               'fsSelection': 128}}
            if with_head:
                metrics['head'] = {'yMin': -120, 'yMax': 800}
            logical = '/system/fonts/MiClock.otf' if cff else '/system/fonts/Roboto-Regular.ttf'
            contract = batch.contract_for_slot({'slots': {logical: {'metrics': metrics}}}, logical)
            self.assertEqual(contract[-1], 'stock')
            report = batch.write_metrics(source, output, contract)
            after = self.freetype.inspect(output)
            if with_head:
                expected = (round(-120 * upem / 1000), round(800 * upem / 1000))
                self.assertEqual((after['bbox'][1], after['bbox'][3]), expected)
                self.assertNotEqual(after['bbox'], before['bbox'])
                self.assertEqual(report['layoutBoundsSource'], 'stock')
            else:
                self.assertEqual(after['bbox'], before['bbox'])
                self.assertEqual(report['layoutBoundsSource'], 'source')
            self.assertEqual(after['glyphs'], before['glyphs'],
                             'metadata-only staging moved or changed actual glyphs')
            self.assertEqual(source.read_bytes(), before_bytes, 'staging mutated donor')

    def test_ttf_stock_bounds_and_raster(self):
        self.assert_layout_contract(cff=False, upem=1000)

    def test_ttf_mixed_upem_stock_bounds_and_raster(self):
        self.assert_layout_contract(cff=False, upem=2048)

    def test_cff_stock_bounds_and_raster(self):
        self.assert_layout_contract(cff=True, upem=1000)

    def test_cff_mixed_upem_stock_bounds_and_raster(self):
        self.assert_layout_contract(cff=True, upem=2048)

    def test_old_inventory_without_head_preserves_source_bounds(self):
        for cff in (False, True):
            with self.subTest(cff=cff):
                self.assert_layout_contract(cff=cff, upem=2048, with_head=False)

    @staticmethod
    def bitmap_contract(use_typo=False, descent=-282, typo_descent=-220,
                        head_min=-430, with_head=True):
        metrics = {'upem': 1000,
                   'hhea': {'ascent': 1044, 'descent': descent, 'lineGap': 0},
                   'os2': {'typoAscender': 890, 'typoDescender': typo_descent,
                           'typoLineGap': 30, 'winAscent': 1044, 'winDescent': 430,
                           'fsSelection': 128 if use_typo else 0}}
        if with_head:
            metrics['head'] = {'yMin': head_min, 'yMax': 1044}
        logical = '/system/fonts/Roboto-Regular.ttf'
        return batch.contract_for_slot({'slots': {logical: {'metrics': metrics}}}, logical)

    def assert_bitmap_correction(self, cff, upem, use_typo=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suffix = '.otf' if cff else '.ttf'
            source, control, output = (root / (name + suffix)
                                       for name in ('source', 'stock-frame', 'aligned'))
            fixture_font(source, upem, cff)
            source_bytes = source.read_bytes()
            contract = self.bitmap_contract(use_typo=use_typo)
            batch.write_metrics(source, control, contract)
            report = batch.write_metrics(source, output, contract, align_bitmap_bottom=True)
            before, after = self.freetype.inspect(control), self.freetype.inspect(output)
            expected_descent = round((-220 if use_typo else -282) * upem / 1000)
            self.assertEqual(before['descender'], expected_descent)
            self.assertEqual(after['descender'], expected_descent)
            self.assertLess(bitmap_span_baseline(before), -5,
                            'fixture must reproduce a visible raised bitmap span')
            self.assertLessEqual(abs(bitmap_span_baseline(after)), 1,
                                 'same-Paint bitmap baseline must agree within rounding')
            self.assertEqual(after['bbox'][1], expected_descent)
            self.assertEqual(after['bbox'][::2], before['bbox'][::2])
            self.assertEqual(after['bbox'][3], before['bbox'][3], 'top frame changed')
            self.assertEqual(after['ascender'], before['ascender'])
            self.assertEqual(after['glyphs'], before['glyphs'],
                             'bitmap correction must not translate or reshape glyphs')
            unchanged = ('hhea', 'OS/2', 'hmtx', 'cmap', 'glyf', 'loca', 'CFF ', 'gvar')
            self.assertEqual(table_bytes(output, unchanged), table_bytes(control, unchanged),
                             'only the staged bottom envelope may change')
            self.assertEqual(source.read_bytes(), source_bytes, 'source font was mutated')
            self.assertEqual(report['layoutBoundsSource'], 'stock-line-descent')
            self.assertEqual(report['bitmapBaselineCorrection'],
                             expected_descent - before['bbox'][1])

    def test_ttf_qq_bitmap_bottom_alignment(self):
        self.assert_bitmap_correction(cff=False, upem=1000)

    def test_ttf_qq_bitmap_bottom_alignment_mixed_upem(self):
        self.assert_bitmap_correction(cff=False, upem=2048)

    def test_cff_qq_bitmap_bottom_alignment(self):
        self.assert_bitmap_correction(cff=True, upem=1000)

    def test_cff_qq_bitmap_bottom_alignment_mixed_upem(self):
        self.assert_bitmap_correction(cff=True, upem=2048)

    def test_qq_bitmap_alignment_uses_effective_typo_descent(self):
        for cff in (False, True):
            for upem in (1000, 2048):
                with self.subTest(cff=cff, upem=upem):
                    self.assert_bitmap_correction(cff=cff, upem=upem, use_typo=True)

    def test_qq_bitmap_alignment_is_byte_idempotent(self):
        for cff in (False, True):
            for upem in (1000, 2048):
                with self.subTest(cff=cff, upem=upem), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    source, first, second = (root / name for name in ('source', 'first', 'second'))
                    fixture_font(source, upem, cff)
                    contract = self.bitmap_contract(use_typo=True)
                    batch.write_metrics(source, first, contract, align_bitmap_bottom=True)
                    batch.write_metrics(first, second, contract, align_bitmap_bottom=True)
                    self.assertEqual(first.read_bytes(), second.read_bytes())
                    self.assertEqual(self.freetype.inspect(first), self.freetype.inspect(second))

    def assert_bitmap_preserved(self, contract, cff=False, **fixture_options):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, control, output = (root / name for name in ('source', 'stock-frame', 'aligned'))
            fixture_font(source, 1000, cff, **fixture_options)
            batch.write_metrics(source, control, contract)
            report = batch.write_metrics(source, output, contract, align_bitmap_bottom=True)
            self.assertEqual(output.read_bytes(), control.read_bytes(),
                             'an unproven or unnecessary correction changed the font')
            self.assertEqual(report['bitmapBaselineCorrection'], 0)

    def test_qq_bitmap_alignment_requires_trusted_stock_frame(self):
        contracts = (batch.contract_for_slot({}, '/system/fonts/Roboto-Regular.ttf'),
                     self.bitmap_contract(with_head=False))
        for cff in (False, True):
            for contract in contracts:
                with self.subTest(cff=cff, contract=contract):
                    self.assert_bitmap_preserved(contract, cff=cff)

    def test_qq_bitmap_alignment_preserves_zero_effective_descent(self):
        for use_typo in (False, True):
            contract = self.bitmap_contract(use_typo=use_typo, descent=0, typo_descent=0)
            with self.subTest(use_typo=use_typo):
                self.assert_bitmap_preserved(contract)

    def test_qq_bitmap_alignment_preserves_nonexcess_bottom(self):
        for head_min in (-282, -120):
            with self.subTest(head_min=head_min):
                self.assert_bitmap_preserved(self.bitmap_contract(head_min=head_min))

    def test_qq_bitmap_alignment_protects_latin_ink_and_variable_fonts(self):
        for cff in (False, True):
            for options in ({'latin_bottom': -350}, {'combining_bottom': -350},
                            {'variable': True}):
                with self.subTest(cff=cff, options=options):
                    self.assert_bitmap_preserved(self.bitmap_contract(), cff=cff, **options)

    def test_qq_bitmap_alignment_protects_all_retained_and_substituted_ink(self):
        for cff in (False, True):
            for options in ({'extra_codepoint': 0x1E9E}, {'extra_codepoint': 0x3B2},
                            {'extra_codepoint': 0x1AB0}, {'substitution': True}):
                with self.subTest(cff=cff, options=options):
                    self.assert_bitmap_preserved(self.bitmap_contract(), cff=cff, **options)


if __name__ == '__main__':
    unittest.main()
