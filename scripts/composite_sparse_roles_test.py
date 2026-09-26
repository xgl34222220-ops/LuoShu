#!/usr/bin/env python3
"""Real sparse-role fonts must compose without a pre-existing ABC/012 base."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]


def make_font(path, points, *, cff=False, width=440, post3=False, glyph_count=0):
    cmap = {point: f'u{point:06X}' for point in points}
    order = ['.notdef', *cmap.values()]
    order.extend(f'reserved{index}' for index in range(len(order), glyph_count))
    encoded = set(cmap.values())
    glyphs = {}
    for name in order:
        pen = T2CharStringPen(700, None) if cff else TTGlyphPen(None)
        if name in encoded:
            pen.moveTo((40, 0)); pen.lineTo((width, 0))
            pen.lineTo((width, 700)); pen.lineTo((40, 700)); pen.closePath()
        glyphs[name] = pen.getCharString() if cff else pen.glyph()
    fb = FontBuilder(1000, isTTF=not cff)
    fb.setupGlyphOrder(order); fb.setupCharacterMap(cmap)
    if cff:
        fb.setupCFF('SparseRole', {'FullName': 'SparseRole'}, glyphs, {})
    else:
        fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (700, 40) for name in order})
    fb.setupHorizontalHeader(ascent=900, descent=-200)
    fb.setupNameTable({'familyName': 'Sparse Role', 'styleName': 'Regular'})
    fb.setupOS2(sTypoAscender=900, sTypoDescender=-200, usWinAscent=900, usWinDescent=200)
    fb.setupPost(keepGlyphNames=not post3); fb.setupMaxp()
    if cff and glyph_count > 65000:
        # A full CFF font needs CID charset numbers rather than 65k custom SIDs.
        sys.path.insert(0, str(ROOT / 'common'))
        from inventory_font_supplement import _merged_cff_table
        fb.font['CFF '] = _merged_cff_table([fb.font])
        fb.font.recalcBBoxes = False
    fb.save(path)


def bounds(font, point):
    glyphs = font.getGlyphSet()
    pen = BoundsPen(glyphs)
    glyphs[font.getBestCmap()[point]].draw(pen)
    return pen.bounds


class SparseCompositeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='luoshu-sparse-composite-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base, self.latin, self.digit, self.output = [self.root / name for name in
            ('base.font', 'latin.font', 'digit.font', 'output.font')]

    def build(self, *, current=False):
        engine = ROOT / 'common' / ('' if current else 'legacy_v14_4') / 'composite_font.py'
        return subprocess.run([sys.executable, str(engine), '--cjk', str(self.base),
            '--latin', str(self.latin), '--digit', str(self.digit), '--output', str(self.output)],
            env=os.environ.copy(), capture_output=True, text=True)

    def test_sparse_roles_append_real_missing_glyphs_in_both_engines_and_outline_formats(self):
        for current in (False, True):
            for cff in (False, True):
                with self.subTest(current=current, cff=cff):
                    make_font(self.base, {ord('永')}, cff=cff, width=640, post3=not cff)
                    make_font(self.latin, {ord('ě')}, cff=not cff, width=340)
                    make_font(self.digit, {ord('７')}, cff=cff, width=240)
                    result = self.build(current=current)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    report = json.loads(result.stdout)
                    self.assertEqual(report['replaced'], {'latin': 1, 'digit': 1})
                    with TTFont(self.output) as font:
                        self.assertEqual(set(font.getBestCmap()), set(map(ord, '永ě７')))
                        self.assertEqual(len(set(font.getGlyphOrder())), font['maxp'].numGlyphs)
                        self.assertEqual(bounds(font, ord('永')), (40, 0, 640, 700))
                        self.assertEqual(bounds(font, ord('ě')), (40, 0, 340, 700))
                        self.assertEqual(bounds(font, ord('７')), (40, 0, 240, 700))

    def test_sparse_donor_keeps_base_characters_it_does_not_supply(self):
        make_font(self.base, set(map(ord, '永AB01')), width=640)
        make_font(self.latin, {ord('A')}, width=240)
        make_font(self.digit, {ord('0')}, width=340)
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        with TTFont(self.output) as font:
            self.assertEqual(set(font.getBestCmap()), set(map(ord, '永AB01')))
            for char in '永B1':
                self.assertEqual(bounds(font, ord(char)), (40, 0, 640, 700))
            self.assertEqual(bounds(font, ord('A')), (40, 0, 240, 700))
            self.assertEqual(bounds(font, ord('0')), (40, 0, 340, 700))

    def test_missing_actual_role_fails_without_replacing_previous_output(self):
        make_font(self.base, {ord('永')})
        make_font(self.latin, {ord('7')})
        make_font(self.digit, {ord('0')})
        self.output.write_bytes(b'previous verified output')
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('英文源字体', result.stderr)
        self.assertEqual(self.output.read_bytes(), b'previous verified output')

    def test_sparse_imports_append_static_metrics_without_changing_variable_cjk(self):
        from legacy_composite_layout_test import add_metric_variations, metric_delta
        for current in (False, True):
            for explicit in (False, True):
                with self.subTest(current=current, explicit=explicit):
                    make_font(self.base, {ord('永')}, width=640)
                    add_metric_variations(self.base, explicit=explicit)
                    make_font(self.latin, {ord('ě')}, width=340)
                    make_font(self.digit, {ord('７')}, width=240)
                    result = self.build(current=current)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    with TTFont(self.output) as font:
                        for weight in (100, 400, 700, 900):
                            glyphs = font.getGlyphSet(location={'wght': weight})
                            for char in 'ě７':
                                name = font.getBestCmap()[ord(char)]
                                self.assertEqual(glyphs[name].width, 700)
                                self.assertEqual(font['gvar'].variations[name], [])
                        for tag, field in (('HVAR', 'AdvWidthMap'), ('VVAR', 'AdvHeightMap')):
                            for char in 'ě７':
                                self.assertEqual(metric_delta(font, tag, field, char, 1), 0)
                            self.assertEqual(metric_delta(font, tag, field, '永', 1), 300)

    def test_sparse_cid_base_appends_valid_charstrings_and_fdselect(self):
        sys.path.insert(0, str(ROOT / 'common'))
        from inventory_font_supplement import _merged_cff_table
        for current in (False, True):
            with self.subTest(current=current):
                make_font(self.base, {ord('永')}, cff=True, width=640)
                with TTFont(self.base) as font:
                    font['CFF '] = _merged_cff_table([font])
                    font['post'].formatType = 3.0
                    font.recalcBBoxes = False
                    font.save(self.base)
                make_font(self.latin, {ord('ě')}, width=340)
                make_font(self.digit, {ord('７')}, cff=True, width=240)
                result = self.build(current=current)
                self.assertEqual(result.returncode, 0, result.stderr)
                with TTFont(self.output) as font:
                    top = font['CFF '].cff[0]
                    self.assertEqual(len(top.charset), len(top.FDSelect.gidArray))
                    self.assertEqual(len(top.charset), font['maxp'].numGlyphs)
                    self.assertEqual(bounds(font, ord('永')), (40, 0, 640, 700))
                    self.assertEqual(bounds(font, ord('ě')), (40, 0, 340, 700))
                    self.assertEqual(bounds(font, ord('７')), (40, 0, 240, 700))

    def test_full_65535_glyph_base_still_replaces_existing_roles_and_reports_new_omissions(self):
        for current, cff in ((False, True), (True, False)):
            with self.subTest(current=current, cff=cff):
                make_font(self.base, set(map(ord, '永A0')), cff=cff, width=640, post3=True, glyph_count=65535)
                make_font(self.latin, set(map(ord, 'Aě')), width=340)
                make_font(self.digit, set(map(ord, '0７')), width=240)
                result = self.build(current=current)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report['glyphCapacitySkipped'], {'latin': [ord('ě')], 'digit': [ord('７')]})
                self.assertEqual(report['replaced'], {'latin': 1, 'digit': 1})
                with TTFont(self.output) as font:
                    self.assertEqual(font['maxp'].numGlyphs, 65535)
                    self.assertEqual(set(font.getBestCmap()), set(map(ord, '永A0')))
                    self.assertEqual(bounds(font, ord('永')), (40, 0, 640, 700))
                    self.assertEqual(bounds(font, ord('A')), (40, 0, 340, 700))
                    self.assertEqual(bounds(font, ord('0')), (40, 0, 240, 700))


if __name__ == '__main__':
    unittest.main()
