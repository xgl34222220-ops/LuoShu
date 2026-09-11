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
from fontTools.ttLib import TTFont

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

    def build(self, runtime=False):
        engine = LEGACY / 'composite_font.py'
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


if __name__ == '__main__':
    unittest.main()
