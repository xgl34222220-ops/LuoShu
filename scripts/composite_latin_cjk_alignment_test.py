#!/usr/bin/env python3
"""Imported Latin/digits must stay proportional and seated against the CJK.

Regression for mixed fonts that looked offset on HyperOS and ColorOS ("36岁",
"39.7万", "renneng123"): the CJK companion's round digits overshoot while a
geometric Latin font's digits are flat, which inflated imported digits against
the letters; and the Latin baseline ignored where the CJK design seats Han.
Both composite engines (current and the linked compatibility runtime) share
composite_layout.py, so each case runs through both.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
ENGINES = {'current': ROOT / 'common/composite_font.py',
           'legacy': ROOT / 'common/legacy_v14_4/composite_font.py'}
UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
LOWER = 'abcdefghijklmnopqrstuvwxyz'
DIGITS = '0123456789'
CJK = '中国田日口目四回永岁万'
ROUND = set('OCGQSU0689') | set('ocegos')


def make_font(path: Path, *, cap: int, xh: int, digit: int, overshoot: int,
              cjk: tuple[int, int] | None, family: str) -> None:
    chars = UPPER + LOWER + DIGITS + (CJK if cjk else '')
    cmap = {ord(char): f'u{ord(char):04X}' for char in chars}
    order = ['.notdef', *cmap.values()]
    glyphs = {}
    for char in chars:
        if char in CJK:
            lo, hi = cjk
        else:
            top = cap if char in UPPER else digit if char in DIGITS else xh
            lo, hi = 0, top
            if char in ROUND:
                lo, hi = -overshoot, top + overshoot
        pen = TTGlyphPen(None)
        pen.moveTo((60, lo)); pen.lineTo((540, lo)); pen.lineTo((540, hi)); pen.lineTo((60, hi))
        pen.closePath()
        glyphs[cmap[ord(char)]] = pen.glyph()
    pen = TTGlyphPen(None)
    pen.moveTo((60, 0)); pen.lineTo((540, 0)); pen.lineTo((540, 700)); pen.lineTo((60, 700)); pen.closePath()
    glyphs['.notdef'] = pen.glyph()
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(order); fb.setupCharacterMap(cmap); fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (1000 if name in {f'u{ord(c):04X}' for c in CJK} else 600, 60)
                               for name in order})
    fb.setupHorizontalHeader(ascent=1044, descent=-282)
    fb.setupOS2(sTypoAscender=890, sTypoDescender=-110, usWinAscent=1044, usWinDescent=282)
    fb.setupNameTable({'familyName': family, 'styleName': 'Regular'})
    fb.setupPost(); fb.setupMaxp(); fb.save(path)


def box(font: TTFont, char: str):
    glyphs = font.getGlyphSet()
    pen = BoundsPen(glyphs)
    glyphs[font.getBestCmap()[ord(char)]].draw(pen)
    return pen.bounds


class CompositeLatinCjkAlignmentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'cjk.ttf'
        self.latin = self.root / 'latin.ttf'
        self.digit = self.root / 'digit.ttf'
        # MiSans-like companion: caps/digits 740 with round overshoot, Han -71..847.
        make_font(self.base, cap=740, xh=530, digit=740, overshoot=14, cjk=(-71, 847), family='Base')
        # Geometric "tech" Latin: flat everywhere, small caps, tall x-height.
        make_font(self.latin, cap=643, xh=510, digit=643, overshoot=0, cjk=None, family='Tech')
        shutil.copyfile(self.latin, self.digit)  # the app passes separate copies

    def build(self, engine: str) -> TTFont:
        output = self.root / f'{engine}.ttf'
        result = subprocess.run([sys.executable, str(ENGINES[engine]), '--cjk', str(self.base),
                                 '--latin', str(self.latin), '--digit', str(self.digit),
                                 '--output', str(output)], env=os.environ.copy(),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        font = TTFont(output)
        self.addCleanup(font.close)
        return font

    def test_one_tech_font_keeps_digit_letter_proportions(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                font = self.build(engine)
                cap, digit, xh = box(font, 'H'), box(font, '1'), box(font, 'x')
                # Round base digits overshoot; flat source digits must still equal caps.
                self.assertLessEqual(abs(digit[3] - cap[3]), 2, (digit, cap))
                self.assertLessEqual(abs(box(font, '0')[3] - cap[3]), 2)
                self.assertAlmostEqual(xh[3] / cap[3], 510 / 643, delta=0.01)
                self.assertTrue(735 <= cap[3] <= 745, cap)
                for char in 'H1x0':
                    self.assertLessEqual(abs(box(font, char)[1]), 1, char)

    def test_separate_digit_font_is_not_inflated_by_base_overshoot(self):
        make_font(self.digit, cap=700, xh=500, digit=700, overshoot=0, cjk=None, family='Digits')
        for engine in ENGINES:
            with self.subTest(engine=engine):
                font = self.build(engine)
                self.assertLessEqual(abs(box(font, '1')[3] - box(font, 'H')[3]), 2)
                self.assertLessEqual(abs(box(font, '0')[3] - 740), 2)

    def test_conventional_cjk_keeps_baseline_zero(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                font = self.build(engine)
                self.assertEqual(round(box(font, 'H')[1]), 0)
                self.assertEqual(round(box(font, '1')[1]), 0)
                self.assertEqual(tuple(round(v) for v in box(font, '中')[1::2]), (-71, 847))

    def test_han_seated_on_baseline_lifts_latin_and_digits_together(self):
        make_font(self.base, cap=740, xh=530, digit=740, overshoot=14, cjk=(0, 918), family='High')
        for engine in ENGINES:
            with self.subTest(engine=engine):
                font = self.build(engine)
                han = box(font, '岁')
                expected = han[1] + 0.08 * (han[3] - han[1])
                for char in 'H1x':
                    self.assertLessEqual(abs(box(font, char)[1] - expected), 2, char)
                self.assertLessEqual(abs(box(font, '1')[3] - box(font, 'H')[3]), 2)
                self.assertEqual(tuple(round(v) for v in han[1::2]), (0, 918))

    def test_han_far_below_baseline_lowers_latin_within_limit(self):
        make_font(self.base, cap=740, xh=530, digit=740, overshoot=14, cjk=(-300, 618), family='Low')
        for engine in ENGINES:
            with self.subTest(engine=engine):
                font = self.build(engine)
                bottom = box(font, '1')[1]
                self.assertLess(bottom, -100)
                self.assertGreaterEqual(bottom, -150)  # never more than 0.15 em
                self.assertLessEqual(abs(box(font, 'H')[1] - bottom), 1)


if __name__ == '__main__':
    unittest.main()
