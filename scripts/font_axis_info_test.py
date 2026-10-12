#!/usr/bin/env python3
"""Real SFNT/TTC axis metadata, malformed fvar and bounded-read regressions."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tracemalloc
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from font_axis_info import read_axis_info
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont


def fixture(path, axes=()):
    font = FontBuilder(1000, isTTF=True)
    font.setupGlyphOrder(['.notdef', 'A'])
    font.setupCharacterMap({65: 'A'})
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0)); pen.lineTo((500, 700)); pen.lineTo((500, 0)); pen.closePath()
    font.setupGlyf({name: pen.glyph() for name in ['.notdef', 'A']})
    font.setupHorizontalMetrics({name: (600, 0) for name in ['.notdef', 'A']})
    font.setupHorizontalHeader(ascent=800, descent=-200)
    font.setupNameTable({'familyName': 'Original Axis Fixture', 'styleName': 'Regular'})
    font.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    font.setupPost(); font.setupMaxp()
    if axes:
        font.setupFvar(axes, [])
    font.save(path)


class FontAxisInfoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'arbitrary-name.ttf'

    def test_static_font_has_no_adjustable_axes(self):
        fixture(self.path)
        report = read_axis_info(self.path)
        self.assertEqual(report['axes'], [])
        self.assertFalse(report['variable'])
        self.assertFalse(report['hasWeight'])

    def test_custom_axis_uses_font_declared_name_and_range(self):
        fixture(self.path, [('wght', 100, 450, 900, 'Weight'), ('XTRA', -2, 1.5, 8, '细节纹理')])
        report = read_axis_info(self.path)
        self.assertEqual(report['weight']['default'], 450)
        self.assertEqual(report['axes'][1], dict(tag='XTRA', name='细节纹理', min=-2, default=1.5, max=8, hidden=False))

    def test_width_only_variable_font_does_not_claim_weight(self):
        fixture(self.path, [('wdth', 75, 100, 125, 'Width')])
        report = read_axis_info(self.path)
        self.assertTrue(report['variable'])
        self.assertFalse(report['hasWeight'])
        self.assertIsNone(report['weight'])

    def test_hidden_axis_is_retained_with_declared_flag(self):
        fixture(self.path, [('XTRA', 0, 1, 2, 'Internal')])
        with TTFont(self.path) as font:
            font['fvar'].axes[0].flags = 1
            font.save(self.path)
        report = read_axis_info(self.path)
        self.assertTrue(report['axes'][0]['hidden'])
        self.assertEqual(report['axes'][0]['default'], 1)

    def test_collection_keeps_existing_first_face_metadata_policy(self):
        fixture(self.path, [('wght', 100, 400, 900, 'Weight')])
        other = self.path.with_name('other.ttf')
        fixture(other, [('wdth', 75, 100, 125, 'Width')])
        collection = TTCollection()
        collection.fonts = [TTFont(self.path), TTFont(other)]
        try:
            output = self.path.with_suffix('.ttc')
            collection.save(output)
        finally:
            collection.close()
        self.assertEqual(read_axis_info(output)['axes'][0]['tag'], 'wght')

    def test_large_font_axis_read_does_not_allocate_whole_font(self):
        fixture(self.path, [('wght', 100, 400, 900, 'Weight')])
        # A real readable SFNT with a large trailing data region. The old
        # read_bytes() path allocated >64 MiB before its lazy table reader.
        with self.path.open('ab') as output:
            output.truncate(64 * 1024 * 1024)
        tracemalloc.start()
        try:
            report = read_axis_info(self.path)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertTrue(report['hasWeight'])
        self.assertLess(peak, 8 * 1024 * 1024, f'Whole-font allocation returned: {peak} bytes')

    def test_invalid_default_range_fails_instead_of_inventing_slider_value(self):
        fixture(self.path, [('wght', 100, 950, 900, 'Weight')])
        with self.assertRaisesRegex(ValueError, '定义无效'):
            read_axis_info(self.path)

    def test_duplicate_axis_tags_are_rejected(self):
        fixture(self.path, [('wght', 100, 400, 900, 'Weight'), ('wght', 200, 500, 800, 'Other')])
        with self.assertRaisesRegex(ValueError, '定义无效'):
            read_axis_info(self.path)

    def test_cli_reports_structured_failure_for_corrupt_font(self):
        self.path.write_bytes(b'not-a-font')
        result = subprocess.run([sys.executable, str(ROOT / 'common/font_axis_info.py'), str(self.path)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['status'], 'error')
        self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
