#!/usr/bin/env python3
"""Load staged fonts with host FreeType; this is not an Android device test.

The public FreeType ABI is used through ctypes, so this check needs neither
freetype-py nor Pillow. It skips explicitly when the host has no FreeType.
"""
import ctypes as C
from ctypes.util import find_library
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
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
            result = {'bbox': bounds, 'upem': record.units_per_EM, 'glyphs': {}}
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


def fixture_font(path, upem, cff):
    """Include a distant, unused glyph to model a large donor's global bounds."""
    names = ['.notdef', 'A', 'zero', 'two', 'unused.extreme']
    scale = upem / 1000
    width = round(600 * scale)
    fb = FontBuilder(upem, isTTF=not cff)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({65: 'A', 48: 'zero', 50: 'two'})
    outlines = {}
    for name in names:
        pen = T2CharStringPen(width, None) if cff else TTGlyphPen(None)
        if name != '.notdef':
            bottom, top = (-500, 1500) if name == 'unused.extreme' else (-80, 720)
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
    fb.save(path)


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


if __name__ == '__main__':
    unittest.main()
