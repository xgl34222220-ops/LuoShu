#!/usr/bin/env python3
"""Digit/Latin coverage gaps and switch-path speedups (ColorOS 16 / Android 17).

Covers:
- measured digit/display faces (OEM lock-screen numerals, "clock" files) are
  admitted as replaceable slots, while script/mono/emoji/italic faces stay stock;
- ColorOS/OxygenOS UI families (OplusOSUI, OnePlus Sans) are recognised;
- the metrics-only fast writer is equivalent to the fontTools re-save;
- the glyf fallback proof and the forked draw give the same verdict as the
  original per-glyph BoundsPen draw.
"""
import array
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
import font_inventory as inventory
import font_slot_coverage as coverage
import hyperos_metrics_batch as batch
import font_live_payload as live


def build_font(path, codepoints, cff=False, empty=(), composite=(), flat=(), os2_version=4,
               top=800):
    names = {cp: f'u{cp:04X}' for cp in codepoints}
    order = ['.notdef', *names.values()]
    glyphs = {}
    for name in order:
        if cff:
            pen = T2CharStringPen(600, None)
        else:
            pen = TTGlyphPen(glyphs)
        if name in empty:
            pass
        elif name in flat:
            # Zero-height outline: a line, never a proof.
            pen.moveTo((0, 100)); pen.lineTo((500, 100)); pen.lineTo((250, 100)); pen.closePath()
        elif name in composite and not cff:
            pen.addComponent(order[1], (1, 0, 0, 1, 10, 0))
        else:
            pen.moveTo((0, -50)); pen.qCurveTo((250, top + 100), (500, -50)) if not cff else pen.lineTo((500, top))
            pen.lineTo((500, -50)); pen.closePath()
        glyphs[name] = pen.getCharString() if cff else pen.glyph()
    fb = FontBuilder(1000, isTTF=not cff)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(names)
    if cff:
        fb.setupCFF('Fixture', {'FullName': 'Fixture'}, glyphs, {})
    else:
        fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (600, 0) for name in order})
    fb.setupHorizontalHeader(ascent=1600, descent=-600)
    fb.setupOS2(version=os2_version, sTypoAscender=1600, sTypoDescender=-600,
                usWinAscent=1700, usWinDescent=700)
    fb.setupNameTable({'familyName': 'Fixture', 'styleName': 'Regular'})
    fb.setupPost(); fb.setupMaxp()
    path.parent.mkdir(parents=True, exist_ok=True)
    fb.save(path)
    return names


def metrics_for(path):
    return inventory._read_metrics(path)[1]


DIGITS = list(range(0x30, 0x3A))
LATIN = list(range(0x41, 0x5B)) + list(range(0x61, 0x7B))


class NumericDisplaySlotTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_coverage_records_digits_and_script_code_points(self):
        path = self.root / 'a.ttf'
        build_font(path, DIGITS + [0x3A, 0x2E] + list(range(0x0E01, 0x0E21)))
        summary = metrics_for(path)['coverage']
        self.assertEqual(summary['digitCount'], 10)
        self.assertEqual(summary['extendedCount'], 0x20)
        self.assertTrue(coverage.valid_coverage(summary))
        # Old inventories without the new keys stay valid; bad values do not.
        legacy = {key: value for key, value in summary.items() if key not in ('digitCount', 'extendedCount')}
        self.assertTrue(coverage.valid_coverage(legacy))
        self.assertFalse(coverage.valid_coverage({**summary, 'digitCount': 11}))
        self.assertFalse(coverage.valid_coverage({**summary, 'extendedCount': -1}))

    def test_digit_only_display_and_clock_faces_are_admitted(self):
        for name in ('OplusLockNumber-Regular.ttf', 'SysClock-Regular.ttf', 'WeatherDigits.otf'):
            with self.subTest(name=name):
                path = self.root / name
                build_font(path, DIGITS + [0x3A, 0x2E, 0x2D, 0x41, 0x50, 0x4D])
                metrics = metrics_for(path)
                self.assertTrue(inventory._generic_text_slot_candidate(name, metrics))
                slot = {'path': f'/system/fonts/{name}', 'source': 'verified-scan',
                        'style': 'normal', 'faceIndex': 0, 'format': 'TTF', 'metrics': metrics}
                self.assertTrue(batch.inventory_completion_slot(slot, slot['path']))

    def test_specialized_and_script_faces_stay_stock(self):
        cases = {
            'NotoSansThaiDigits-Regular.ttf': DIGITS + list(range(0x0E01, 0x0E3A)),
            'DigitsWithScript-Regular.ttf': DIGITS + list(range(0x0E01, 0x0E3A)),
            'RobotoMono-Regular.ttf': DIGITS,
            'SysClock-Italic.ttf': DIGITS,
            'NotoColorEmoji.ttf': DIGITS,
            'NotoSansSymbols-Regular.ttf': DIGITS,
            'PartialDigits-Regular.ttf': DIGITS[:9],
            'HanNumerals-Regular.ttf': DIGITS + [0x4E00, 0x4E8C, 0x4E09],
        }
        for name, points in cases.items():
            with self.subTest(name=name):
                path = self.root / name
                build_font(path, points)
                metrics = metrics_for(path)
                self.assertFalse(inventory._numeric_display_slot_candidate(name, metrics))
                slot = {'path': f'/system/fonts/{name}', 'source': 'verified-scan',
                        'style': 'normal', 'faceIndex': 0, 'format': 'TTF', 'metrics': metrics}
                self.assertFalse(batch.inventory_completion_slot(slot, slot['path']))

    def test_full_latin_gate_is_unchanged(self):
        path = self.root / 'Text-Regular.ttf'
        build_font(path, LATIN + DIGITS + list(range(0x20, 0x30)) + list(range(0xC0, 0x100)))
        self.assertTrue(inventory._generic_text_slot_candidate(path.name, metrics_for(path)))
        self.assertFalse(inventory._generic_text_slot_candidate('NotoSansMono-Regular.ttf', metrics_for(path)))

    def test_verified_scan_admits_numeric_face_and_keeps_old_exclusions(self):
        fonts = self.root / 'system/fonts'
        build_font(fonts / 'OplusClockNumber-Regular.ttf', DIGITS + [0x3A])
        build_font(fonts / 'NotoSansThai-Regular.ttf', DIGITS + list(range(0x0E01, 0x0E3A)))
        build_font(fonts / 'DroidSansMono.ttf', DIGITS + LATIN)
        slots = {}
        root = inventory.FontRoot('system', Path('/system/fonts'), fonts)
        inventory._add_verified_text_slots(slots, [root])
        self.assertEqual(sorted(slots), ['/system/fonts/OplusClockNumber-Regular.ttf'])

    def test_coloros_oneplus_ui_families_are_recognised(self):
        for name in ('OplusOSUI-XThin.ttf', 'OplusOSUI-Regular.otf', 'OnePlusSans-Medium.ttf',
                     'OplusSans-SemiBold.ttf'):
            self.assertTrue(inventory._heuristic_candidate(name), name)
        for family in ('OplusOSUI-Display', 'oplus-osui', 'OnePlusSans-Text', 'oneplus-sans'):
            self.assertTrue(inventory._is_ui_family(family), family)
        for name in ('OplusOSUI-Italic.ttf',):
            slot = {'path': f'/system/fonts/{name}', 'style': 'normal', 'faceIndex': 0, 'format': 'TTF',
                    'metrics': {}}
            self.assertFalse(batch.inventory_completion_slot(slot, slot['path']))
        self.assertFalse(inventory._heuristic_candidate('Oplus-Serif.ttf'))


CONTRACT = (1000, 900, -250, 0, 880, -120, 0, 1050, 280, True, (-280, 1100), 'stock')


def file_checksum(path):
    data = path.read_bytes()
    data += b'\0' * ((4 - len(data) % 4) % 4)
    words = array.array('I', data)
    if sys.byteorder == 'little':
        words.byteswap()
    return sum(words) & 0xFFFFFFFF


class FastMetricsWriterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_both(self, source, **kwargs):
        fast, slow = self.root / 'fast.font', self.root / 'slow.font'
        calls = []
        original = batch._patch_metric_tables

        def tracked(*args):
            result = original(*args)
            calls.append(result)
            return result
        with patch.object(batch, '_patch_metric_tables', new=tracked):
            fast_report = batch.write_metrics(source, fast, CONTRACT, **kwargs)
        with patch.object(batch, '_patch_metric_tables', new=lambda *args: False):
            slow_report = batch.write_metrics(source, slow, CONTRACT, **kwargs)
        return fast, slow, fast_report, slow_report, calls

    def assert_equivalent(self, fast, slow):
        with TTFont(fast) as a, TTFont(slow) as b:
            self.assertEqual(sorted(a.keys()), sorted(b.keys()))
            for tag in ('hhea', 'OS/2'):
                self.assertEqual(a[tag].compile(a), b[tag].compile(b), tag)
            head_a, head_b = dict(vars(a['head'])), dict(vars(b['head']))
            head_a.pop('checkSumAdjustment'); head_b.pop('checkSumAdjustment')
            self.assertEqual(head_a, head_b)
            self.assertEqual(a.getBestCmap(), b.getBestCmap())
            for tag in ('glyf', 'CFF ', 'loca', 'hmtx'):
                if tag in a.reader:
                    self.assertEqual(a.reader[tag], b.reader[tag], tag)
        self.assertEqual(file_checksum(fast), 0xB1B0AFBA)
        self.assertEqual(file_checksum(slow), 0xB1B0AFBA)

    def test_truetype_and_cff_sources_take_the_patch_path(self):
        for cff in (False, True):
            with self.subTest(cff=cff):
                source = self.root / ('cff.otf' if cff else 'tt.ttf')
                build_font(source, LATIN + DIGITS + [0x4E2D], cff=cff)
                fast, slow, fast_report, slow_report, calls = self.write_both(source)
                self.assertEqual(calls, [True])
                self.assertEqual(fast_report, slow_report)
                self.assert_equivalent(fast, slow)
                with TTFont(fast) as font:
                    self.assertEqual(font['hhea'].ascent, 900)
                    self.assertEqual((font['head'].yMin, font['head'].yMax), (-280, 1100))
                    self.assertEqual(font['OS/2'].usWinAscent, 1050)

    def test_os2_version_promotion_falls_back_to_full_save(self):
        source = self.root / 'v1.ttf'
        build_font(source, LATIN + DIGITS, os2_version=1)
        fast, slow, fast_report, slow_report, calls = self.write_both(source)
        self.assertEqual(calls, [False])
        self.assertEqual(fast.read_bytes(), slow.read_bytes())
        with TTFont(fast) as font:
            self.assertEqual(font['OS/2'].version, 4)

    def test_cjk_routing_rewrite_keeps_full_save(self):
        source = self.root / 'routed.ttf'
        build_font(source, LATIN + [0x4E2D, 0x4E8C])
        fast, slow, fast_report, slow_report, calls = self.write_both(
            source, cjk_fallback_codepoints=frozenset({0x4E2D}))
        self.assertEqual(calls, [])  # cmap rewrite: the fast path is not attempted
        with TTFont(fast) as font:
            self.assertNotIn(0x4E2D, font.getBestCmap())
            self.assertIn(0x4E8C, font.getBestCmap())

    def test_source_bytes_are_never_modified(self):
        source = self.root / 'pinned.ttf'
        build_font(source, LATIN + DIGITS)
        before = source.read_bytes()
        self.write_both(source)
        self.assertEqual(source.read_bytes(), before)


class FallbackProofTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.han = list(range(0x4E00, 0x4E00 + 60))

    def reference(self, path, candidates):
        """The original per-glyph BoundsPen proof."""
        with TTFont(path, lazy=True) as font:
            cmap = font.getBestCmap()
            glyphs = font.getGlyphSet()
            proven = set()
            for cp in candidates & cmap.keys():
                pen = BoundsPen(glyphs)
                try:
                    glyphs[cmap[cp]].draw(pen)
                except Exception:
                    continue
                b = pen.bounds
                if b is not None and b[2] > b[0] and b[3] > b[1]:
                    proven.add(cp)
        return frozenset(proven)

    def test_glyf_header_proof_matches_draw_including_edge_glyphs(self):
        path = self.root / 'han.ttf'
        names = build_font(path, LATIN + self.han,
                           empty={f'u{self.han[1]:04X}'}, flat={f'u{self.han[2]:04X}'},
                           composite={f'u{self.han[3]:04X}'})
        candidates = frozenset(self.han + [0x3000])
        with patch.object(batch, '_draw_outline_proof', wraps=batch._draw_outline_proof) as draw:
            proven, mapped, drawn = batch.final_fallback_codepoints(path, candidates)
        self.assertEqual(proven, self.reference(path, candidates))
        self.assertNotIn(self.han[1], proven)
        self.assertNotIn(self.han[2], proven)
        self.assertIn(self.han[3], proven)
        self.assertEqual(mapped, frozenset(self.han))
        # Only the composite and the records without a fast verdict are drawn.
        drawn_names = draw.call_args.args[2]
        self.assertIn(names[self.han[3]], drawn_names)
        self.assertLessEqual(len(drawn_names), 3)
        self.assertEqual(drawn, len(self.han))

    def test_corrupt_glyf_record_is_not_proven_by_header(self):
        path = self.root / 'corrupt.ttf'
        build_font(path, LATIN + self.han)
        with TTFont(path) as font:
            gid = font.getGlyphID(f'u{self.han[0]:04X}')
            offset = font['loca'].locations[gid]
        with TTFont(path, lazy=True) as font:
            glyf_offset = font.reader.tables['glyf'].offset
        data = bytearray(path.read_bytes())
        # numberOfContours claims 300 contours: end points overrun the record.
        data[glyf_offset + offset:glyf_offset + offset + 2] = (300).to_bytes(2, 'big')
        path.write_bytes(bytes(data))
        with TTFont(path, lazy=True) as font:
            verdict = batch._glyf_simple_outline_proof(font, [f'u{self.han[0]:04X}', f'u{self.han[5]:04X}'])
        self.assertNotIn(f'u{self.han[0]:04X}', verdict)
        self.assertTrue(verdict[f'u{self.han[5]:04X}'])

    def test_forked_draw_matches_serial_draw_for_cff(self):
        path = self.root / 'han.otf'
        build_font(path, LATIN + self.han, cff=True, empty={f'u{self.han[4]:04X}'})
        candidates = frozenset(self.han)
        with patch.object(batch, 'PARALLEL_DRAW_MIN_GLYPHS', 1), \
                patch.object(batch.os, 'sched_getaffinity', create=True, new=lambda _pid: set(range(4))):
            parallel = batch.final_fallback_codepoints(path, candidates)
        with patch.dict(os.environ, {'LUOSHU_SERIAL_GLYPH_PROOF': '1'}):
            serial = batch.final_fallback_codepoints(path, candidates)
        self.assertEqual(parallel, serial)
        self.assertEqual(parallel[0], self.reference(path, candidates))
        self.assertNotIn(self.han[4], parallel[0])

    def test_failed_worker_falls_back_to_in_process_draw(self):
        path = self.root / 'han2.otf'
        build_font(path, LATIN + self.han, cff=True)
        candidates = frozenset(self.han)
        with patch.object(batch, 'PARALLEL_DRAW_MIN_GLYPHS', 1), \
                patch.object(batch, '_draw_names', new=lambda *args: {}), \
                patch.object(batch.os, 'sched_getaffinity', create=True, new=lambda _pid: set(range(3))):
            proven = batch.final_fallback_codepoints(path, candidates)[0]
        self.assertEqual(proven, self.reference(path, candidates))


class LivePayloadCopyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / 'cache'

    def payload(self, name, size):
        source = self.root / name
        (source / 'system/fonts').mkdir(parents=True)
        (source / 'system/fonts/A.ttf').write_bytes(name.encode() * size)
        os.link(source / 'system/fonts/A.ttf', source / 'system/fonts/B.ttf')
        return source

    def prepare(self, source, label):
        reads = []
        original = live._read_source

        def counted(path, info, destination=None):
            reads.append(destination is not None)
            return original(path, info, destination)
        with patch.object(live, '_read_source', new=counted):
            generation = live.prepare(source, self.cache, 'boot-1', self.root / f'tmp-{label}')
        return generation, reads

    def test_second_font_in_same_boot_is_read_once(self):
        first, reads = self.prepare(self.payload('one', 4000), 'a')
        self.assertEqual(reads, [True])  # one shared inode, fused hash+copy
        second, reads = self.prepare(self.payload('two', 5000), 'b')
        self.assertNotEqual(first, second)
        self.assertEqual(reads, [True], 'different payload: no hash-only second read')
        self.assertEqual((second / 'system/fonts/A.ttf').read_bytes(), b'two' * 5000)
        self.assertEqual(os.stat(second / 'system/fonts/A.ttf').st_ino,
                         os.stat(second / 'system/fonts/B.ttf').st_ino)

    def test_same_payload_again_keeps_warm_hash_only_path(self):
        source = self.payload('same', 4000)
        first, _reads = self.prepare(source, 'a')
        again, reads = self.prepare(source, 'b')
        self.assertEqual(first, again)
        self.assertEqual(reads, [False], 'existing generation: verify without staging writes')
        self.assertFalse((self.root / 'tmp-b').exists())


if __name__ == '__main__':
    unittest.main()
