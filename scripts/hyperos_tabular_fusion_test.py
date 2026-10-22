#!/usr/bin/env python3
"""Clock-slot tabular digits fused into the metrics pass (complete_hyperos).

Device exports (HyperOS OS3.0, 2026-10) showed eight tabular_digits steps of
~1.2 s each inside complete_hyperos: every clock alias was written once by
write_metrics, then re-opened and fully re-saved (20 MB) only to widen ten hmtx
entries. The fused pass must give exactly the same font content as the old two
passes, for every case the old pass handled, and must be faster.
"""
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
import hyperos_metrics_batch as batch

# upem, hhea a/d/gap, typo a/d/gap, win a/d, useTypo, head frame, source
CONTRACT = (1000, 1100, -350, 30, 1080, -320, 20, 1400, 400, True, (-400, 1200), 'stock')
DIGITS = {0x30 + index: 480 + index * 20 for index in range(10)}  # proportional


def build_font(path: Path, *, cff=False, widths=DIGITS, extra=0, hdmx=False, variable=False,
               missing_digit=False):
    codepoints = [cp for cp in widths if not (missing_digit and cp == 0x35)]
    cmap = {cp: f'u{cp:X}' for cp in (*codepoints, 65)}
    for index in range(extra):  # bulk glyphs: a realistically large hmtx/glyf
        cmap[0x4E00 + index] = f'uni{0x4E00 + index:04X}'
    order = ['.notdef', *cmap.values()]
    advances = {name: (widths.get(int(name[1:], 16), 600)
                       if name.startswith('u') and len(name) == 3 else 600) for name in order}
    fb = FontBuilder(1000, isTTF=not cff)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    if cff:
        charstrings = {}
        for name in order:
            pen = T2CharStringPen(advances[name], None)
            pen.moveTo((40, 0)); pen.lineTo((400, 0)); pen.lineTo((400, 700)); pen.closePath()
            charstrings[name] = pen.getCharString()
        fb.setupCFF('Fixture-Regular', {'FullName': 'Fixture'}, charstrings, {})
    else:
        glyphs = {}
        for name in order:
            pen = TTGlyphPen(None)
            pen.moveTo((40, 0)); pen.lineTo((400, 0)); pen.lineTo((400, 700)); pen.closePath()
            glyphs[name] = pen.glyph()
        fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (advances[name], 40) for name in order})
    fb.setupHorizontalHeader(ascent=1600, descent=-600)
    fb.setupOS2(sTypoAscender=1600, sTypoDescender=-600, usWinAscent=1700, usWinDescent=700)
    fb.setupNameTable({'familyName': 'Fixture', 'styleName': 'Regular'})
    fb.setupPost()
    if variable:
        fb.setupFvar([('wght', 100, 400, 900, 'Weight')], [])
    if not cff:
        fb.setupMaxp()
    if hdmx:
        table = newTable('hdmx')
        table.hdmx = {12: {name: 7 for name in order}}
        fb.font['hdmx'] = table
    fb.save(path)
    return path


def legacy(source: Path, output: Path) -> dict:
    """The pre-fusion pipeline: metrics pass, then a separate tabular re-save."""
    report = batch.write_metrics(source, output, CONTRACT)
    report.update(batch.apply_tabular_digits(output))
    return report


def table_dump(path: Path) -> dict:
    """Decoded content of every table; head.checkSumAdjustment is file framing."""
    dump = {}
    with TTFont(path) as font:
        for tag in sorted(font.keys()):
            if tag == 'GlyphOrder':
                dump[tag] = font.getGlyphOrder()
                continue
            table = font[tag]
            if tag == 'head':
                values = dict(vars(table)); values.pop('checkSumAdjustment')
                dump[tag] = values
            elif tag == 'hmtx':
                dump[tag] = dict(table.metrics)
            elif tag == 'cmap':
                dump[tag] = font.getBestCmap()
            elif tag == 'glyf':
                dump[tag] = {name: table[name].compile(table) for name in font.getGlyphOrder()}
            elif tag == 'CFF ':
                charstrings = table.cff.topDictIndex[0].CharStrings
                dump[tag] = {name: charstrings[name].bytecode if charstrings[name].bytecode is not None
                             else charstrings[name].compile() for name in font.getGlyphOrder()}
            else:
                dump[tag] = table.compile(font)
    return dump


class TabularFusionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='luoshu-tabular-fusion-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def both(self, source: Path):
        old, new = self.root / 'old.font', self.root / 'new.font'
        old_report = legacy(source, old)
        calls = []
        original = batch._patch_metric_tables

        def tracked(*args):
            calls.append((args[4] if len(args) > 4 else batch.PATCHED_METRIC_TABLES, original(*args)))
            return calls[-1][1]
        with patch.object(batch, '_patch_metric_tables', new=tracked):
            new_report = batch.write_metrics(source, new, CONTRACT, tabular_digits=True)
        return old, new, old_report, new_report, calls

    def assert_same_font(self, old: Path, new: Path):
        a, b = table_dump(old), table_dump(new)
        self.assertEqual(sorted(a), sorted(b))
        for tag in a:
            self.assertEqual(a[tag], b[tag], tag)

    def test_truetype_digits_match_two_pass_output_through_the_patch_path(self):
        source = build_font(self.root / 'tt.ttf')
        old, new, old_report, new_report, calls = self.both(source)
        self.assertEqual(old_report, new_report)
        self.assertEqual('applied', new_report['tabularDigits'])
        self.assertTrue(new_report['tabularCentered'])
        self.assertEqual([(('hmtx', 'head', 'hhea', 'OS/2'), True)], calls)
        self.assert_same_font(old, new)
        with TTFont(new) as font:
            hmtx, cmap = font['hmtx'].metrics, font.getBestCmap()
            self.assertEqual({660}, {hmtx[cmap[cp]][0] for cp in DIGITS})
            self.assertEqual(40 + (660 - 480) // 2, hmtx[cmap[0x30]][1])
            self.assertEqual(1100, font['hhea'].ascent)

    def test_cff_digits_keep_position_and_match(self):
        source = build_font(self.root / 'cff.otf', cff=True)
        old, new, old_report, new_report, calls = self.both(source)
        self.assertEqual(old_report, new_report)
        self.assertFalse(new_report['tabularCentered'])
        self.assertTrue(calls and calls[-1][1])
        self.assert_same_font(old, new)

    def test_hdmx_forces_the_full_save_and_still_matches(self):
        source = build_font(self.root / 'hdmx.ttf', hdmx=True)
        old, new, old_report, new_report, calls = self.both(source)
        self.assertEqual(old_report, new_report)
        self.assertEqual([], calls)  # stale per-size table dropped: full save
        self.assert_same_font(old, new)
        with TTFont(new) as font:
            self.assertNotIn('hdmx', font)

    def test_unchanged_cases_report_like_the_old_pass(self):
        cases = {
            'already-tabular': dict(widths={cp: 600 for cp in DIGITS}),
            'missing-digits': dict(missing_digit=True),
            'skipped-variable': dict(variable=True),
        }
        for expected, options in cases.items():
            with self.subTest(expected):
                source = build_font(self.root / f'{expected}.ttf', **options)
                old, new, old_report, new_report, calls = self.both(source)
                self.assertEqual(expected, new_report['tabularDigits'])
                self.assertEqual(old_report, new_report)
                self.assert_same_font(old, new)

    def test_planning_failure_falls_back_to_the_legacy_pass(self):
        source = build_font(self.root / 'tt.ttf')
        with patch.object(batch, '_plan_tabular_digits', side_effect=KeyError('cmap')):
            report = batch.write_metrics(source, self.root / 'out.font', CONTRACT, tabular_digits=True)
        self.assertNotIn('tabularDigits', report)  # build() then runs apply_tabular_digits

    def test_non_clock_slots_are_untouched(self):
        source = build_font(self.root / 'tt.ttf')
        report = batch.write_metrics(source, self.root / 'plain.font', CONTRACT)
        self.assertNotIn('tabularDigits', report)
        with TTFont(self.root / 'plain.font') as font:
            hmtx, cmap = font['hmtx'].metrics, font.getBestCmap()
            self.assertEqual(set(DIGITS.values()), {hmtx[cmap[cp]][0] for cp in DIGITS})

    def test_benchmark_fused_pass_is_faster_than_two_passes(self):
        # A larger donor: the old second pass re-reads and re-serialises it.
        source = build_font(self.root / 'big.ttf', extra=12000)
        rounds = 3

        def timed(function):
            best = None
            for index in range(rounds):
                began = time.perf_counter()
                function(index)
                spent = time.perf_counter() - began
                best = spent if best is None else min(best, spent)
            return best
        old = timed(lambda index: legacy(source, self.root / f'old-{index}.font'))
        new = timed(lambda index: batch.write_metrics(source, self.root / f'new-{index}.font', CONTRACT,
                                                      tabular_digits=True))
        print(f'[BENCH] tabular clock slot: two-pass {old * 1000:.0f} ms, fused {new * 1000:.0f} ms '
              f'({os.path.getsize(source)} bytes)', file=sys.stderr)
        self.assert_same_font(self.root / 'old-0.font', self.root / 'new-0.font')
        self.assertLess(new, old)


class StageCompletionFusionTest(unittest.TestCase):
    """build(): clock slots no longer run a separate tabular_digits step."""

    def test_clock_slot_is_tabular_in_one_step(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import hyperos_metrics_batch_test as fixture_suite
        import contextlib
        import io
        case = fixture_suite.HyperOSMetricsTest('test_clock_slots_get_tabular_digits_from_the_user_font')
        case.setUp()
        try:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                case.test_clock_slots_get_tabular_digits_from_the_user_font()
            lines = [line for line in stderr.getvalue().splitlines() if line.startswith('[STAGE-STEP]')]
            self.assertFalse([line for line in lines if 'step=tabular_digits' in line], lines)
            self.assertTrue([line for line in lines if 'step=slot_metrics' in line and 'tabular=fused' in line
                             and 'MiClockMono' in line], lines)
        finally:
            case.doCleanups()


if __name__ == '__main__':
    unittest.main(verbosity=2)
