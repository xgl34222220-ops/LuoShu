#!/usr/bin/env python3
"""Real cmap regressions for stock Latin primary / staged CJK fallback routing.

FreeType checks the actual character-to-glyph lookup used by font selection.
This verifies the routing contract, not QQ/Coolapk rendering on a K80 device.
"""
import ctypes as C
import json
import os
import subprocess
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
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
import font_inventory as inventory
import font_inventory_scan_v3 as scanner
import hyperos_metrics_batch as batch
from font_slot_coverage import valid_coverage
from hyperos_layout_freetype_test import FreeType, Face

HAN = 0x4E2D
OTHER_HAN = 0x20000
UVS_HAN = 0x56FD
PUNCT = 0x3001
LATIN = 65
EMOJI = 0x2600
DEFAULT_POINTS = (LATIN, 48, 0xFF11, HAN, OTHER_HAN, UVS_HAN, PUNCT, EMOJI)


def make_font(path, points=DEFAULT_POINTS, cff=False, variable=False, uvs=False):
    cmap = {cp: f'u{cp:X}' for cp in points}
    names = ['.notdef', *cmap.values()]
    builder = FontBuilder(1000, isTTF=not cff)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap(cmap)
    glyphs = {}
    for name in names:
        pen = T2CharStringPen(600, None) if cff else TTGlyphPen(None)
        if name != '.notdef':
            pen.moveTo((20, -80)); pen.lineTo((550, -80))
            pen.lineTo((550, 850)); pen.lineTo((20, 850)); pen.closePath()
        glyphs[name] = pen.getCharString() if cff else pen.glyph()
    if cff:
        builder.setupCFF('RoutingFixture-Regular', {'FullName': 'RoutingFixture'}, glyphs, {})
    else:
        builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 20) for name in names})
    builder.setupHorizontalHeader(ascent=980, descent=-250)
    builder.setupOS2(sTypoAscender=980, sTypoDescender=-250,
                     usWinAscent=1050, usWinDescent=300)
    builder.setupNameTable({'familyName': 'RoutingFixture', 'styleName': 'Regular'})
    builder.setupPost(); builder.setupMaxp()
    if variable:
        builder.setupFvar([('wght', 100, 400, 900, 'Weight')], [])
        builder.setupGvar({name: [] for name in names})
    if uvs:
        table = CmapSubtable.newSubtable(14)
        table.platformID = 0; table.platEncID = 5; table.language = 0
        table.cmap = {}
        table.uvsDict = {0xFE00: [(cp, None) for cp in (UVS_HAN, LATIN, EMOJI) if cp in cmap]}
        builder.font['cmap'].tables.append(table)
    builder.save(path)


class RoutingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.stage = self.module / '.luoshu-payload-next'
        self.fonts = self.stage / 'system/fonts'
        self.fonts.mkdir(parents=True)
        (self.module / 'config').mkdir()
        env = {'LUOSHU_BUILD_KEY': 'routing-test'}
        for part in batch.PARTS:
            root = self.root / 'stock' / part
            root.mkdir(parents=True)
            env[f'LUOSHU_{part.upper()}_FONTS_ROOT'] = str(root)
        self.patch = patch.dict(os.environ, env)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.slots = {}
        self.dynamic_aliases = {}

    def stock(self, name, points, families=('sans-serif',)):
        path = self.root / 'stock/system' / name
        make_font(path, points)
        fmt, metrics = inventory._read_metrics(path)
        logical = '/system/fonts/' + name
        self.slots[logical] = {'slotName': name, 'path': logical,
                               'families': list(families), 'format': fmt, 'metrics': metrics}
        return self.slots[logical]

    def build(self, names=None):
        (self.module / 'config/device_font_inventory.json').write_text(json.dumps({
            'schema': inventory.SCHEMA, 'inventoryRevision': 1, 'metricsRevision': 3,
            'state': 'ready', 'buildKey': 'routing-test', 'slots': self.slots,
            'preservedDynamicAliases': self.dynamic_aliases}))
        with patch.object(TTFont, 'getGlyphSet', side_effect=AssertionError('rebuild outlines')):
            result = batch.build(self.module, self.stage,
                                 names or [Path(logical).name for logical in (*self.slots, *self.dynamic_aliases)])
        self.reports = {entry['slot']: entry for entry in json.loads(
            (self.stage / '.luoshu-metrics-report.json').read_text())['slots']}
        return result

    def default_pair(self, cff=False, variable=False):
        make_font(self.fonts / '400.ttf', cff=cff, variable=variable, uvs=True)
        self.stock('Roboto-Regular.ttf', (LATIN, 48))
        self.stock('MiSansVF.ttf', DEFAULT_POINTS, ('mi-sans',))

    def assert_routing_and_compact_outlines(self, cff=False, variable=False):
        self.default_pair(cff, variable)
        result = self.build()
        self.assertEqual(result, {'mapped': 2, 'generated': 2, 'fallbackSlots': 0})
        with TTFont(self.fonts / '400.ttf', lazy=True) as source, \
                TTFont(self.fonts / 'Roboto-Regular.ttf', lazy=True) as primary, \
                TTFont(self.fonts / 'MiSansVF.ttf', lazy=True) as fallback:
            self.assertIn(HAN, source.getBestCmap(), 'pre-fix primary would take CJK')
            self.assertNotIn(HAN, primary.getBestCmap())
            self.assertIn(HAN, fallback.getBestCmap())
            self.assertNotIn(OTHER_HAN, primary.getBestCmap())
            self.assertNotIn(PUNCT, primary.getBestCmap())
            for cp in (LATIN, 48, 0xFF11, EMOJI):
                self.assertEqual(primary.getBestCmap()[cp], source.getBestCmap()[cp])
            for tag in ('glyf', 'loca', 'CFF ', 'CFF2', 'gvar'):
                if tag in source:
                    self.assertEqual(fallback.reader[tag], source.reader[tag], tag)
            # Latin aliases now physically subset unreachable glyphs. Compare
            # retained outlines instead of requiring the old, bloated binary.
            self.assertLess(len(primary.getGlyphOrder()), len(source.getGlyphOrder()))
            for cp in (LATIN, 48, 0xFF11, EMOJI, UVS_HAN):
                actual, expected = RecordingPen(), RecordingPen()
                primary.getGlyphSet()[primary.getBestCmap()[cp]].draw(actual)
                source.getGlyphSet()[source.getBestCmap()[cp]].draw(expected)
                self.assertEqual(actual.value, expected.value)
            uvs = next(table for table in primary['cmap'].tables if table.format == 14)
            self.assertEqual(uvs.uvsDict[0xFE00], [(LATIN, None), (EMOJI, None), (UVS_HAN, None)])
            self.assertIn(UVS_HAN, primary.getBestCmap(), 'unproven Han variation must stay usable')
            fallback_uvs = next(table for table in fallback['cmap'].tables if table.format == 14)
            self.assertIn((UVS_HAN, None), fallback_uvs.uvsDict[0xFE00])
        report = self.reports['/system/fonts/Roboto-Regular.ttf']
        self.assertEqual(report['removedCjkMappings'], 3)
        self.assertEqual(report['cjkRoutingSource'], 'stock-fallback')
        self.assertEqual(report['layoutBoundsSource'], 'stock')

    def test_ttf_cjk_routes_to_fallback_and_retained_outlines_survive(self):
        self.assert_routing_and_compact_outlines(variable=True)

    def test_cff_cjk_routes_to_fallback_with_compact_latin_outlines(self):
        self.assert_routing_and_compact_outlines(cff=True)

    def test_compaction_preserves_legacy_symbol_and_variation_only_mappings(self):
        self.default_pair()
        source_path = self.fonts / '400.ttf'
        with TTFont(source_path, recalcBBoxes=False) as font:
            # Existing non-Unicode mappings are not proof of a CJK fallback.
            # Keep their referenced glyphs even when its Unicode Han route moves.
            for platform, encoding, cp in ((1, 0, 0x80), (3, 0, 0xF041)):
                table = CmapSubtable.newSubtable(4)
                table.platformID, table.platEncID, table.language = platform, encoding, 0
                table.cmap = {cp: f'u{HAN:X}'}
                font['cmap'].tables.append(table)
            variation = next(table for table in font['cmap'].tables if table.format == 14)
            variation.uvsDict[0xE0100] = [(0x9FFF, f'u{OTHER_HAN:X}')]
            font.save(source_path)
        original = source_path.read_bytes()
        self.build()
        self.assertEqual(source_path.read_bytes(), original, 'user source is read-only')
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            for platform, encoding, cp in ((1, 0, 0x80), (3, 0, 0xF041)):
                table = next(table for table in font['cmap'].tables
                             if (table.platformID, table.platEncID) == (platform, encoding))
                self.assertEqual(table.cmap[cp], f'u{HAN:X}')
                self.assertIn(table.cmap[cp], font.getGlyphOrder())
            variation = next(table for table in font['cmap'].tables if table.format == 14)
            self.assertEqual(variation.uvsDict[0xE0100], [(0x9FFF, f'u{OTHER_HAN:X}')])
            self.assertIn(f'u{OTHER_HAN:X}', font.getGlyphOrder())
            self.assertNotIn(HAN, font.getBestCmap(), 'Unicode route still uses the proven fallback')

    def test_many_latin_contracts_compact_shared_source_only_once(self):
        self.default_pair(variable=True)
        for index in range(20):
            name = f'Roboto-Extra{index}.ttf'
            self.stock(name, (LATIN, 48))
            self.slots[f'/system/fonts/{name}']['metrics']['hhea']['ascent'] += index + 1
        with patch.object(batch, 'compact_routed_source', wraps=batch.compact_routed_source) as compact:
            result = self.build()
        self.assertEqual(result['mapped'], 22)
        self.assertEqual(compact.call_count, 1)
        self.assertFalse(list((self.fonts / '.luoshu-font-store').glob('hyperos-metrics-*')))

    def test_dali_dynamic_overlay_is_not_frozen_to_the_init_roboto_seed(self):
        self.default_pair()
        # Measured dali stock line contracts differ. Paint.getFontMetrics can
        # inspect the configured Overlay face before drawText's getNativeInstance
        # invokes Xiaomi's checkMiuiFont and selects MiSans. Freezing Overlay to
        # Roboto therefore makes those operations use different line frames.
        for name, ascent, descent in (('MiSansVF.ttf', 1044, -282),
                                      ('Roboto-Regular.ttf', 928, -244)):
            metrics = self.slots['/system/fonts/' + name]['metrics']
            metrics['hhea'].update(ascent=ascent, descent=descent, lineGap=0)
            metrics['os2'].update(fsSelection=64)
        name = 'MiSansVF_Overlay.ttf'
        logical = '/system/fonts/' + name
        target = '/data/system/fonts/theme_webview/Roboto-Regular.ttf'
        stock_link = self.root / 'stock/system' / name
        stock_link.symlink_to(target)
        self.dynamic_aliases[logical] = {
            'source': 'hyperos-framework-symlink', 'target': target}
        # Initial generic mapping and previously installed Test6 both create
        # this wrong regular font. Final staging must remove it even if the
        # mutable /data link is not initialized on this host/pre-mount boot.
        make_font(self.fonts / name)
        result = self.build()
        self.assertFalse((self.fonts / name).exists())
        self.assertEqual(os.readlink(stock_link), target)
        self.assertEqual(result['mapped'], 2)
        with TTFont(self.fonts / 'MiSansVF.ttf') as han, \
                TTFont(self.fonts / 'Roboto-Regular.ttf') as latin:
            self.assertIn(HAN, han.getBestCmap())
            self.assertIn(48, han.getBestCmap())
            self.assertNotIn(HAN, latin.getBestCmap())
        self.assertNotIn(logical, self.reports)
        report = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())
        self.assertEqual(report['preservedDynamicAliases'], [logical])

        # Model the unchanged ROM symlink chain inside the fixture namespace.
        # It follows the mapped MiSans selected by the framework, then follows
        # Roboto when that framework route changes; no cached copied alias exists.
        routes = self.root / 'framework-route'
        routes.mkdir()
        overlay_route = routes / name
        mutable_route = routes / 'theme-webview-Roboto.ttf'
        overlay_route.symlink_to(mutable_route.name)
        mutable_route.symlink_to(self.fonts / 'MiSansVF.ttf')
        ft = FreeType()
        try:
            measured = ft.inspect(overlay_route)
            drawn = ft.inspect(self.fonts / 'MiSansVF.ttf')
            roboto = ft.inspect(self.fonts / 'Roboto-Regular.ttf')
            frame = lambda font: (font['ascender'], font['descender'])
            self.assertEqual(frame(measured), (1044, -282))
            self.assertEqual(frame(measured), frame(drawn))
            self.assertNotEqual(frame(roboto), frame(drawn), 'Test6 froze the wrong frame')
            mutable_route.unlink()
            mutable_route.symlink_to(self.fonts / 'Roboto-Regular.ttf')
            self.assertEqual(frame(ft.inspect(overlay_route)), frame(roboto))
        finally:
            ft.close()

        # Boot compatibility used to recreate every absent Overlay alias.
        # It must now expose the exact ROM link in both overlay and bind modes.
        env = {**os.environ, 'IS_HYPEROS': 'true',
               'LUOSHU_REAL_MODDIR': str(self.module),
               'LUOSHU_HYPEROS_CLOCK_PAYLOAD_ROOT': str(self.stage)}
        helper = ROOT / 'common/legacy_v14_4/hyperos_clock_compat.sh'
        command = '. "$1"; luoshu_hyperos_clock_payload_ensure'
        for stale in (False, True):
            if stale:
                make_font(self.fonts / name)
            subprocess.run(['sh', '-c', command, 'sh', str(helper)], env=env, check=True)
            self.assertFalse((self.fonts / name).exists())
            self.assertEqual(os.readlink(stock_link), target)

        # Static Overlay files on another ROM are still mapped by boot repair.
        stock_link.unlink()
        make_font(stock_link)
        subprocess.run(['sh', '-c', command, 'sh', str(helper)], env=env, check=True)
        self.assertTrue((self.fonts / name).is_file())

    def test_test6_overlay_reference_migrates_before_deferred_scan(self):
        self.default_pair()
        overlay = self.stock('MiSansVF_Overlay.ttf', (LATIN, 48), ())
        overlay['source'] = 'hyperos-rom-reference'
        overlay['metricsReferencePath'] = '/system/fonts/Roboto-Regular.ttf'
        make_font(self.fonts / 'MiSansVF_Overlay.ttf')
        self.build()
        self.assertFalse((self.fonts / 'MiSansVF_Overlay.ttf').exists())

    def test_old_inventory_keeps_cjk_and_reports_pending_scan(self):
        self.default_pair()
        for entry in self.slots.values():
            del entry['metrics']['coverage']
        self.build()
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertIn(HAN, font.getBestCmap())
        self.assertEqual(self.reports['/system/fonts/Roboto-Regular.ttf']['cjkRoutingReason'],
                         'stock-coverage-refresh-pending')

    def test_misans_latin_direct_alias_keeps_full_cjk_for_launcher_paths(self):
        self.default_pair()
        make_font(self.fonts / '400.ttf', (*DEFAULT_POINTS, 0x3007))
        latin = self.stock('MiSansLatinVF.ttf', (LATIN, 48, 0x3007), ())
        self.assertTrue(latin['metrics']['coverage']['hasHan'])
        self.assertEqual(latin['metrics']['coverage']['hanCount'], 1)
        self.build()
        with TTFont(self.fonts / 'MiSansLatinVF.ttf') as font:
            self.assertIn(HAN, font.getBestCmap(),
                          'HyperOS launcher can open MiSansLatin directly without family fallback')
            self.assertIn(OTHER_HAN, font.getBestCmap())
            self.assertIn(0x3007, font.getBestCmap())
            self.assertIn(48, font.getBestCmap())
        self.assertEqual(self.reports['/system/fonts/MiSansLatinVF.ttf']['cjkRoutingReason'],
                         'oem-direct-full-coverage')
        self.assertEqual(self.reports['/system/fonts/MiSansLatinVF.ttf']['removedCjkMappings'], 0)
        self.assertTrue(batch.bitmap_bottom_slot(
            {'slots': {'/system/fonts/MiSansLatinVF.ttf': latin}},
            '/system/fonts/MiSansLatinVF.ttf',
            batch.contract_for_slot({'slots': {'/system/fonts/MiSansLatinVF.ttf': latin}},
                                    '/system/fonts/MiSansLatinVF.ttf')))
        # The direct-load rule is filename/ROM-path based, independent of whether
        # the stock seed happened to contain one real ideograph on this build.
        self.stock('MiSansLatinVF.ttf', (LATIN, 48, 0x3007, HAN), ())
        self.build()
        self.assertEqual(self.reports['/system/fonts/MiSansLatinVF.ttf']['cjkRoutingReason'],
                         'oem-direct-full-coverage')

    def test_numeric_hyperos_weight_alias_keeps_full_cjk(self):
        self.default_pair()
        self.stock('400.ttf', (LATIN, 48), ())
        self.build()
        with TTFont(self.fonts / '400.ttf') as font:
            self.assertIn(HAN, font.getBestCmap())
            self.assertIn(OTHER_HAN, font.getBestCmap())
        self.assertEqual(self.reports['/system/fonts/400.ttf']['cjkRoutingReason'],
                         'oem-direct-full-coverage')

    def test_no_staged_fallback_keeps_primary_han(self):
        self.default_pair()
        self.build(['Roboto-Regular.ttf'])
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertIn(HAN, font.getBestCmap())
        self.assertEqual(self.reports['/system/fonts/Roboto-Regular.ttf']['cjkRoutingReason'],
                         'no-staged-cjk-fallback')

    def test_unrelated_named_han_family_is_not_proof_of_system_fallback(self):
        make_font(self.fonts / '400.ttf')
        self.stock('Roboto-Regular.ttf', (LATIN, 48))
        self.stock('PrivateDisplay.ttf', DEFAULT_POINTS, ('private-display',))
        self.build()
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertIn(HAN, font.getBestCmap())
        self.assertEqual(self.reports['/system/fonts/Roboto-Regular.ttf']['cjkRoutingReason'],
                         'no-staged-cjk-fallback')

    def test_stock_han_fallback_with_latin_only_output_is_not_proof(self):
        self.default_pair()
        (self.fonts / '400.ttf').rename(self.fonts / 'Roboto-Regular.ttf')
        make_font(self.fonts / 'MiSansVF.ttf', (LATIN, 48, PUNCT))
        self.build()
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertIn(HAN, font.getBestCmap())
        self.assertEqual(self.reports['/system/fonts/Roboto-Regular.ttf']['removedCjkMappings'], 0)

    def test_cjk_primary_is_never_guessed_from_roboto_filename(self):
        self.default_pair()
        self.stock('Roboto-Regular.ttf', DEFAULT_POINTS)
        self.build()
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertIn(HAN, font.getBestCmap())

    def test_clock_and_mono_slots_keep_existing_routing(self):
        self.default_pair()
        names = ('MiClock.otf', 'RobotoMono-Regular.ttf', 'DroidSansMono.ttf',
                 'NotoSansMono-Regular.ttf')
        for name in names:
            self.stock(name, (LATIN, 48))
        self.build()
        for name in names:
            with TTFont(self.fonts / name) as font:
                self.assertIn(HAN, font.getBestCmap())
                self.assertIn(LATIN, font.getBestCmap())
                self.assertIn(48, font.getBestCmap())
            self.assertEqual(self.reports['/system/fonts/' + name]['cjkRoutingReason'],
                             'specialized-slot')

    def test_stale_script_targets_are_removed_only_from_isolated_stage(self):
        self.default_pair()
        original = {}
        for name in ('NotoSansAdlam-VF.ttf', 'NotoSansCuneiform-Regular.ttf',
                     'NotoSansMono-Icons.ttf', 'MiSansOdiaVF.ttf', 'RobotoSymbols.ttf'):
            self.stock(name, (0x12000,), ())
            original[name] = (self.root / 'stock/system' / name).read_bytes()
            make_font(self.fonts / name)
        result = self.build()
        self.assertEqual(result['mapped'], 2)
        for name, expected in original.items():
            self.assertFalse((self.fonts / name).exists())
            self.assertEqual((self.root / 'stock/system' / name).read_bytes(), expected)

    def test_restored_latin_targets_keep_complete_english_and_digits(self):
        self.default_pair()
        alphanumeric = tuple(map(ord, 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'))
        points = tuple(dict.fromkeys((*DEFAULT_POINTS, *alphanumeric)))
        source_path = self.fonts / '400.ttf'
        make_font(source_path, points, variable=True)
        names = ('DroidSansMono.ttf', 'DroidSansFallback.ttf', 'NotoSansMono-Regular.ttf',
                 'NotoSansDisplay-Regular.ttf', 'NotoSansCondensed-Regular.ttf',
                 'NotoSansSemiCondensed-Regular.ttf', 'NotoSansVF.ttf')
        stock_before = {}
        for name in names:
            self.stock(name, alphanumeric, ())
            stock_before[name] = (self.root / 'stock/system' / name).read_bytes()
            make_font(self.fonts / name)
        source_before = source_path.read_bytes()
        result = self.build()
        self.assertEqual(result['mapped'], len(names) + 2)
        self.assertEqual(result['fallbackSlots'], 0)
        self.assertEqual(source_path.read_bytes(), source_before)
        with TTFont(source_path) as source:
            for name in names:
                with self.subTest(name=name), TTFont(self.fonts / name) as output:
                    self.assertTrue(set(alphanumeric).issubset(output.getBestCmap()))
                    for cp in alphanumeric:
                        actual, expected = RecordingPen(), RecordingPen()
                        output.getGlyphSet()[output.getBestCmap()[cp]].draw(actual)
                        source.getGlyphSet()[source.getBestCmap()[cp]].draw(expected)
                        self.assertEqual(actual.value, expected.value)
                self.assertEqual((self.root / 'stock/system' / name).read_bytes(), stock_before[name])
                self.assertEqual(self.reports['/system/fonts/' + name]['metricsSource'], 'stock')
        # Reapplying uses the same preserved donor rather than dropping aliases.
        self.assertEqual(self.build()['mapped'], len(names) + 2)
        self.assertEqual(source_path.read_bytes(), source_before)

    def test_stock_latin_noto_ui_slots_are_physically_compacted(self):
        self.default_pair()
        names = ('NotoSans-Regular.ttf', 'NotoSansUI-Regular.ttf', 'DroidSans.ttf',
                 'NotoSans.ttf', 'NotoSans.otf', 'NotoSansUI.ttf', 'NotoSansUI.otf')
        for name in names:
            self.stock(name, (LATIN, 48), ())
        self.build()
        for name in names:
            with TTFont(self.fonts / name) as font:
                self.assertNotIn(HAN, font.getBestCmap())
                self.assertIn(LATIN, font.getBestCmap())
            self.assertEqual(self.reports['/system/fonts/' + name]['cjkRoutingReason'],
                             'stock-latin-primary')

    def test_obsolete_script_alias_is_removed_even_when_target_list_is_current(self):
        self.default_pair()
        name = 'NotoSansAdlam-VF.ttf'
        make_font(self.fonts / name)
        stock = self.root / 'stock/system' / name
        make_font(stock, (0x1E900,))
        expected = stock.read_bytes()
        self.build(['MiSansVF.ttf', 'Roboto-Regular.ttf'])
        self.assertFalse((self.fonts / name).exists())
        self.assertEqual(stock.read_bytes(), expected)

    def test_original_cjk_punctuation_is_preserved(self):
        self.default_pair()
        self.stock('Roboto-Regular.ttf', (LATIN, 48, PUNCT))
        self.build()
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertIn(PUNCT, font.getBestCmap())
            self.assertNotIn(HAN, font.getBestCmap())

    def test_only_codepoints_still_present_in_staged_fallback_are_removed(self):
        self.default_pair()
        (self.fonts / '400.ttf').rename(self.fonts / 'Roboto-Regular.ttf')
        make_font(self.fonts / 'MiSansVF.ttf', (LATIN, HAN))
        self.build()
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertNotIn(HAN, font.getBestCmap())
            self.assertIn(OTHER_HAN, font.getBestCmap())
            self.assertIn(PUNCT, font.getBestCmap())

    def freetype_index(self, path, codepoint, selector=None):
        ft = FreeType()
        face = C.POINTER(Face)()
        try:
            ft.check(ft.api.FT_New_Face(ft.library, bytes(path), 0, C.byref(face)), 'load cmap fixture')
            if selector is None:
                query = ft.api.FT_Get_Char_Index
                query.argtypes = [C.POINTER(Face), C.c_ulong]
                query.restype = C.c_uint
                return query(face, codepoint)
            query = ft.api.FT_Face_GetCharVariantIndex
            query.argtypes = [C.POINTER(Face), C.c_ulong, C.c_ulong]
            query.restype = C.c_uint
            return query(face, codepoint, selector)
        finally:
            if face:
                ft.check(ft.api.FT_Done_Face(face), 'close cmap fixture')
            ft.close()

    def test_conflicting_cmaps_do_not_claim_an_unreachable_fallback_glyph(self):
        self.default_pair()
        (self.fonts / '400.ttf').rename(self.fonts / 'Roboto-Regular.ttf')
        fallback_path = self.fonts / 'MiSansVF.ttf'
        make_font(fallback_path)
        with TTFont(fallback_path, recalcBBoxes=False) as font:
            for table in font['cmap'].tables:
                if table.format == 12:
                    del table.cmap[HAN]
            self.assertTrue(any(HAN in table.cmap for table in font['cmap'].tables
                                if table.format == 4))
            self.assertNotIn(HAN, font.getBestCmap())
            font.save(fallback_path)
        self.assertEqual(self.freetype_index(fallback_path, HAN), 0,
                         'default FreeType cmap must agree that the conflicting glyph is missing')
        self.build()
        self.assertGreater(self.freetype_index(self.fonts / 'Roboto-Regular.ttf', HAN), 0)
        self.assertEqual(self.freetype_index(fallback_path, HAN), 0)
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertIn(HAN, font.getBestCmap(), 'do not remove glyph visible only in secondary cmap')
            self.assertNotIn(OTHER_HAN, font.getBestCmap(), 'proven fallback glyph may still move')

    def test_nondefault_han_variation_and_base_survive_without_matching_fallback_uvs(self):
        self.default_pair()
        source = self.fonts / '400.ttf'
        with TTFont(source, recalcBBoxes=False) as font:
            table = next(table for table in font['cmap'].tables if table.format == 14)
            table.uvsDict[0xFE00] = [(LATIN, None), (EMOJI, None), (UVS_HAN, f'u{HAN:X}')]
            font.save(source)
        source.rename(self.fonts / 'Roboto-Regular.ttf')
        make_font(self.fonts / 'MiSansVF.ttf', uvs=False)
        before_variant = self.freetype_index(self.fonts / 'Roboto-Regular.ttf', UVS_HAN, 0xFE00)
        self.assertGreater(before_variant, 0)
        self.assertEqual(self.freetype_index(self.fonts / 'MiSansVF.ttf', UVS_HAN, 0xFE00), 0)
        self.build()
        primary = self.fonts / 'Roboto-Regular.ttf'
        self.assertGreater(self.freetype_index(primary, UVS_HAN), 0)
        self.assertGreater(self.freetype_index(primary, UVS_HAN, 0xFE00), 0)
        with TTFont(primary) as font:
            table = next(table for table in font['cmap'].tables if table.format == 14)
            self.assertIn((UVS_HAN, f'u{HAN:X}'), table.uvsDict[0xFE00])
            self.assertIn(UVS_HAN, font.getBestCmap())
            self.assertNotIn(HAN, font.getBestCmap(), 'ordinary Han still routes to proven fallback')

    def test_shared_three_argument_writer_does_not_change_coloros_routing(self):
        self.default_pair()
        contract = batch.contract_for_slot({'slots': self.slots}, '/system/fonts/Roboto-Regular.ttf')
        output = self.root / 'coloros-output.ttf'
        report = batch.write_metrics(self.fonts / '400.ttf', output, contract)
        with TTFont(output) as font:
            self.assertIn(HAN, font.getBestCmap())
        self.assertEqual(report['removedCjkMappings'], 0)

    def test_stock_coverage_is_read_from_actual_cmap_and_revision_two_is_stale(self):
        self.default_pair()
        latin = self.slots['/system/fonts/Roboto-Regular.ttf']['metrics']['coverage']
        cjk = self.slots['/system/fonts/MiSansVF.ttf']['metrics']['coverage']
        self.assertEqual((latin['hasHan'], latin['hasLatin'], latin['hanCount']), (False, True, 0))
        self.assertEqual((cjk['hasHan'], cjk['hanCount']), (True, 3))
        self.assertTrue(valid_coverage(latin))
        previous = {'metricsRevision': 2, 'slots': self.slots,
                    'mainSlot': self.slots['/system/fonts/Roboto-Regular.ttf']}
        self.assertFalse(scanner._has_current_metrics(previous))
        previous['metricsRevision'] = scanner.METRICS_REVISION
        self.assertTrue(scanner._has_current_metrics(previous))

    def test_host_freetype_primary_han_missing_and_fallback_han_renderable(self):
        ft = FreeType()
        self.addCleanup(ft.close)
        ft.api.FT_Get_Char_Index.argtypes = [C.POINTER(Face), C.c_ulong]
        ft.api.FT_Get_Char_Index.restype = C.c_uint
        for cff in (False, True):
            self.default_pair(cff=cff)
            self.build()
            found = []
            for name in ('Roboto-Regular.ttf', 'MiSansVF.ttf'):
                face = C.POINTER(Face)()
                ft.check(ft.api.FT_New_Face(ft.library, bytes(self.fonts / name), 0, C.byref(face)),
                         'load staged font')
                try:
                    found.append(ft.api.FT_Get_Char_Index(face, HAN))
                    self.assertGreater(ft.api.FT_Get_Char_Index(face, LATIN), 0)
                finally:
                    ft.check(ft.api.FT_Done_Face(face), 'close staged font')
            self.assertEqual(found[0], 0, 'primary must let Han fall through')
            self.assertGreater(found[1], 0, 'staged fallback must still render user Han')


if __name__ == '__main__':
    unittest.main()
