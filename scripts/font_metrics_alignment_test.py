#!/usr/bin/env python3
"""Replaced fonts must lay out on the ROM's own line box (host FreeType, not a device).

For every staged slot the Android/Skia vertical frame (ascent, descent, leading,
top, bottom; USE_TYPO_METRICS honoured the way Skia does) is computed from the
generated file with the host FreeType and compared with the stock slot it
replaces. Fixtures are synthetic; their numbers follow the documented stock
contracts (K80 MiSansVF / Roboto, a ColorOS SysSans/OplusOSUI-like contract).
"""
from __future__ import annotations

import ctypes as C
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
sys.path.insert(0, str(ROOT / 'scripts'))
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables as ot

from font_inventory import _read_metrics
import coloros_metrics_batch as coloros
import hyperos_metrics_batch as batch
from hyperos_layout_freetype_test import Face, FreeType

HAN = 0x4E2D
CHARS = [ord('A'), ord('H'), ord('g'), *range(0x30, 0x3A), HAN]


def build_font(path: Path, upem: int, *, ascent: int, descent: int, line_gap: int = 0,
               typo: tuple[int, int, int] | None = None, use_typo: bool = False,
               win: tuple[int, int] | None = None, ink: tuple[int, int] = (-120, 880),
               cff: bool = False, variable: bool = False, mvar: bool = False,
               family: str = 'Fixture') -> None:
    """Build a real SFNT. Values are font units of this face's own unitsPerEm."""
    path.parent.mkdir(parents=True, exist_ok=True)
    names = ['.notdef'] + [f'u{cp:04X}' for cp in CHARS]
    fb = FontBuilder(upem, isTTF=not cff)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({cp: f'u{cp:04X}' for cp in CHARS})
    outlines = {}
    width = upem // 2
    for name in names:
        pen = T2CharStringPen(width, None) if cff else TTGlyphPen(None)
        if name != '.notdef':
            bottom, top = ink if name == f'u{HAN:04X}' else (0, round(upem * 0.7))
            if name == 'u0067':  # 'g' descender
                bottom = round(-upem * 0.2)
            pen.moveTo((10, bottom)); pen.lineTo((width - 10, bottom))
            pen.lineTo((width - 10, top)); pen.lineTo((10, top)); pen.closePath()
        outlines[name] = pen.getCharString() if cff else pen.glyph()
    fb.setupHorizontalMetrics({name: (width, 10) for name in names})
    fb.setupHorizontalHeader(ascent=ascent, descent=descent, lineGap=line_gap)
    fb.setupNameTable({'familyName': family, 'styleName': 'Regular'})
    typo = typo or (ascent, descent, line_gap)
    win = win or (max(ascent, 0), max(-descent, 0))
    fb.setupOS2(sTypoAscender=typo[0], sTypoDescender=typo[1], sTypoLineGap=typo[2],
                usWinAscent=win[0], usWinDescent=win[1], version=4,
                fsSelection=0x40 | (0x80 if use_typo else 0))
    fb.setupPost()
    if cff:
        fb.setupCFF(f'{family}-Regular', {'FullName': family, 'FamilyName': family}, outlines, {})
    else:
        fb.setupGlyf(outlines)
        fb.setupMaxp()
    if variable:
        fb.setupFvar([('wght', 100, 400, 900, 'Weight')], [])
    if mvar:
        table = newTable('MVAR')
        table.table = ot.MVAR()
        table.table.Version = 0x00010000
        table.table.Reserved = 0
        table.table.ValueRecordSize = 8
        table.table.ValueRecordCount = 0
        table.table.ValueRecord = []
        table.table.VarStore = None
        fb.font['MVAR'] = table
    fb.save(path)


# Stock contracts. K80 values are the documented dali OS3.0.305.0 metrics;
# the ColorOS one is a fixture with typo != hhea to exercise USE_TYPO_METRICS.
STOCK = {
    'MiSansVF': dict(upem=1000, ascent=1044, descent=-282, ink=(-282, 1044), use_typo=False),
    'MiSansLatinVF': dict(upem=1000, ascent=1044, descent=-282, ink=(-282, 1044), use_typo=False),
    'Roboto': dict(upem=2048, ascent=1900, descent=-500, typo=(1536, -512, 102),
                   win=(2163, 555), ink=(-555, 2163), use_typo=False),
    'SysSans': dict(upem=1000, ascent=1100, descent=-300, typo=(950, -250, 120), use_typo=True,
                    win=(1150, 320), ink=(-300, 1100)),
}
DONORS = {
    'ttf-1000': dict(upem=1000, ascent=880, descent=-120, typo=(860, -140, 0), use_typo=True,
                     ink=(-150, 1100)),
    'ttf-2048': dict(upem=2048, ascent=2200, descent=-600, line_gap=67, ink=(-300, 2150)),
    'cff-1000': dict(upem=1000, ascent=1000, descent=-250, cff=True, ink=(-90, 900)),
    'vf-1000': dict(upem=1000, ascent=950, descent=-230, variable=True, ink=(-100, 880)),
    'vf-mvar': dict(upem=1000, ascent=900, descent=-260, variable=True, mvar=True, ink=(-100, 880)),
}


class Frame:
    """Skia SkScalerContext_FreeType::generateFontMetrics, in em units."""

    def __init__(self, freetype: FreeType):
        self.ft = freetype

    def __call__(self, path: Path) -> dict:
        face = C.POINTER(Face)()
        self.ft.check(self.ft.api.FT_New_Face(self.ft.library, bytes(path), 0, C.byref(face)),
                      f'load {path.name}')
        try:
            record = face.contents
            upem = record.units_per_EM
            ascender, descender, height = record.ascender, record.descender, record.height
            bbox = (record.bbox.yMin, record.bbox.yMax)
        finally:
            self.ft.check(self.ft.api.FT_Done_Face(face), 'close font')
        with TTFont(path, lazy=True) as font:
            os2 = font['OS/2']
            mvar = 'MVAR' in font
            if os2.version != 0xFFFF and os2.fsSelection & 0x80:
                ascender, descender = os2.sTypoAscender, os2.sTypoDescender
                leading = os2.sTypoLineGap
            else:
                leading = height + descender - ascender
        return {'ascent': -ascender / upem, 'descent': -descender / upem,
                'leading': leading / upem, 'top': -bbox[1] / upem, 'bottom': -bbox[0] / upem,
                'upem': upem, 'mvar': mvar}


def glyph_bytes(path: Path) -> dict:
    with TTFont(path, lazy=True) as font:
        return {tag: font.reader[tag] for tag in ('glyf', 'loca', 'CFF ', 'hmtx', 'gvar')
                if tag in font.reader}


class AlignmentBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.freetype = FreeType()
        cls.addClassCleanup(cls.freetype.close)
        cls.frame = Frame(cls.freetype)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='luoshu-align-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.stage = self.module / '.luoshu-payload-next'
        (self.module / 'config').mkdir(parents=True)
        self.env = {'LUOSHU_BUILD_KEY': 'align-fixture'}
        for part in batch.PARTS:
            stock = self.root / 'stock' / part
            stock.mkdir(parents=True)
            self.env[f'LUOSHU_{part.upper()}_FONTS_ROOT'] = str(stock)
        env = patch.dict(os.environ, self.env)
        env.start(); self.addCleanup(env.stop)
        self.slots = {}

    def stock(self, part: str, name: str, kind: str, *, record: bool = True, weight: int = 400) -> Path:
        path = self.root / 'stock' / part / name
        values = dict(STOCK[kind])
        build_font(path, values.pop('upem'), cff=name.endswith('.otf'), **values)
        if record:
            fmt, metrics = _read_metrics(path)
            self.slots[f'/{part}/fonts/{name}'] = {
                'path': f'/{part}/fonts/{name}', 'slotName': name, 'source': 'heuristic',
                'families': [], 'weight': weight, 'style': 'normal', 'faceIndex': 0,
                'format': fmt, 'metrics': metrics}
        return path

    def write_inventory(self, main: str) -> None:
        (self.module / 'config/device_font_inventory.json').write_text(json.dumps({
            'schema': 'device-font-inventory-v1', 'inventoryRevision': 1, 'state': 'ready',
            'buildKey': 'align-fixture', 'slots': self.slots, 'mainSlotPath': main,
            'mainSlot': self.slots[main]}))

    def donor(self, key: str, path: Path) -> Path:
        values = dict(DONORS[key])
        build_font(path, values.pop('upem'), **values)
        return path

    def assert_same_frame(self, output: Path, stock: Path, label: str) -> None:
        actual, expected = self.frame(output), self.frame(stock)
        # Each stock value is rescaled to the donor's own unitsPerEm and
        # rounded once: at most half a unit of either grid.
        tolerance = 0.5 / actual['upem'] + 0.5 / expected['upem'] + 1e-9
        for key in ('ascent', 'descent', 'leading', 'top', 'bottom'):
            self.assertLessEqual(abs(actual[key] - expected[key]), tolerance,
                                 f'{label}: {key} {actual[key]:.4f} != stock {expected[key]:.4f}')
        baseline = -actual['ascent']
        box = actual['descent'] - actual['ascent'] + actual['leading']
        stock_box = expected['descent'] - expected['ascent'] + expected['leading']
        self.assertLessEqual(abs(baseline + expected['ascent']), tolerance, f'{label}: baseline moved')
        self.assertLessEqual(abs(box - stock_box), 2 * tolerance, f'{label}: line box height changed')
        self.assertFalse(actual['mvar'], f'{label}: MVAR could restore donor metrics at other weights')

    def report(self) -> dict:
        return {row['slot']: row for row in json.loads(
            (self.stage / '.luoshu-metrics-report.json').read_text())['slots']}


class HyperOSAlignmentTest(AlignmentBase):
    def stage_donor(self, key: str) -> Path:
        fonts = self.stage / 'system/fonts'
        store = fonts / '.luoshu-font-store'
        store.mkdir(parents=True, exist_ok=True)
        return self.donor(key, store / 'regular.font')

    def test_every_staged_slot_uses_the_stock_line_box_for_any_donor(self):
        pairs = (('system', 'MiSansVF.ttf', 'MiSansVF'), ('system', 'MiSansLatinVF.ttf', 'MiSansLatinVF'),
                 ('system', 'Roboto-Regular.ttf', 'Roboto'), ('product', 'MiSansVF.ttf', 'MiSansVF'))
        for key in DONORS:
            with self.subTest(donor=key):
                for leftover in (self.stage, self.root / 'stock'):
                    if leftover.exists():
                        subprocess.run(['rm', '-rf', str(leftover)], check=True)
                for part in batch.PARTS:
                    (self.root / 'stock' / part).mkdir(parents=True, exist_ok=True)
                self.slots = {}
                stocks = {(part, name): self.stock(part, name, kind) for part, name, kind in pairs}
                self.write_inventory('/system/fonts/MiSansVF.ttf')
                donor = self.stage_donor(key)
                before = donor.read_bytes()
                result = batch.build(self.module, self.stage,
                                     ['MiSansVF.ttf', 'MiSansLatinVF.ttf', 'Roboto-Regular.ttf'])
                self.assertEqual(donor.read_bytes(), before, 'staging mutated the donor')
                self.assertEqual(result['fallbackSlots'], 0)
                for (part, name), stock in stocks.items():
                    output = self.stage / part / 'fonts' / name
                    self.assert_same_frame(output, stock, f'{key} {part}/{name}')
                    # Only metadata changed: glyph programs and advances are the donor's.
                    if 'MVAR' not in DONORS[key] and not DONORS[key].get('mvar'):
                        self.assertEqual(glyph_bytes(output), glyph_bytes(donor), f'{key} {name}')

    def test_slot_missing_from_inventory_borrows_its_sibling_not_the_compact_box(self):
        stock_system = self.stock('system', 'MiSansVF.ttf', 'MiSansVF')
        # Same file on /product (K80 links it there) without its own record.
        stock_product = self.stock('product', 'MiSansVF.ttf', 'MiSansVF', record=False)
        roboto = self.stock('system', 'Roboto-Regular.ttf', 'Roboto')
        medium = self.stock('system', 'Roboto-Medium.ttf', 'Roboto', record=False, weight=500)
        self.write_inventory('/system/fonts/MiSansVF.ttf')
        self.stage_donor('ttf-2048')
        result = batch.build(self.module, self.stage,
                             ['MiSansVF.ttf', 'Roboto-Regular.ttf', 'Roboto-Medium.ttf'])
        self.assertEqual(result['fallbackSlots'], 0)
        reports = self.report()
        self.assertEqual(reports['/product/fonts/MiSansVF.ttf']['metricsSource'], 'stock-sibling')
        self.assertEqual(reports['/product/fonts/MiSansVF.ttf']['metricsReferencePath'],
                         '/system/fonts/MiSansVF.ttf')
        self.assertEqual(reports['/system/fonts/Roboto-Medium.ttf']['metricsReferencePath'],
                         '/system/fonts/Roboto-Regular.ttf')
        # Borrowed contracts never authorise coverage routing or bitmap corrections.
        self.assertEqual(reports['/system/fonts/Roboto-Medium.ttf']['cjkRoutingSource'], 'source')
        self.assertEqual(reports['/system/fonts/Roboto-Medium.ttf']['bitmapBaselineCorrection'], 0)
        self.assert_same_frame(self.stage / 'product/fonts/MiSansVF.ttf', stock_product, 'product MiSansVF')
        self.assert_same_frame(self.stage / 'system/fonts/Roboto-Medium.ttf', medium, 'Roboto-Medium')
        self.assert_same_frame(self.stage / 'system/fonts/MiSansVF.ttf', stock_system, 'system MiSansVF')
        self.assert_same_frame(self.stage / 'system/fonts/Roboto-Regular.ttf', roboto, 'Roboto-Regular')

    def test_without_a_family_sibling_the_old_explicit_fallback_is_kept(self):
        self.stock('system', 'MiSansVF.ttf', 'MiSansVF')
        self.stock('system', 'MiClock.ttf', 'MiSansVF', record=False)
        self.write_inventory('/system/fonts/MiSansVF.ttf')
        self.stage_donor('ttf-1000')
        result = batch.build(self.module, self.stage, ['MiSansVF.ttf', 'MiClock.ttf'])
        self.assertEqual(result['fallbackSlots'], 1)
        self.assertEqual(self.report()['/system/fonts/MiClock.ttf']['metricsSource'], 'fallback')

    def test_italic_aliases_from_older_mappers_expose_the_stock_italic(self):
        self.stock('system', 'MiSansVF.ttf', 'MiSansVF')
        for name in ('Roboto-Italic.ttf', 'Roboto-BoldItalic.ttf'):
            self.stock('system', name, 'Roboto', record=False)
        self.write_inventory('/system/fonts/MiSansVF.ttf')
        donor = self.stage_donor('ttf-1000')
        for name in ('Roboto-Italic.ttf', 'Roboto-BoldItalic.ttf'):
            os.link(donor, self.stage / 'system/fonts' / name)
        names = subprocess.run(
            ['sh', '-c', '. "$1"; _lhcc_names_for_root "$2"', 'sh',
             str(ROOT / 'common/legacy_v14_4/hyperos_full_coverage.sh'), str(self.root / 'stock/system')],
            check=True, text=True, capture_output=True,
            env={**os.environ, 'LUOSHU_REAL_MODDIR': str(ROOT)}).stdout.split()
        self.assertNotIn('Roboto-Italic.ttf', names)
        batch.build(self.module, self.stage, names)
        for name in ('Roboto-Italic.ttf', 'Roboto-BoldItalic.ttf'):
            self.assertFalse((self.stage / 'system/fonts' / name).exists(), name)
        preserved = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())['preservedStockAliases']
        self.assertIn('/system/fonts/Roboto-Italic.ttf', preserved)

    def test_legacy_hyperos_mapper_never_writes_italic_slots(self):
        script = ('. "$1"; get_all_hyperos_files; echo ---; _hyperos_retired_italic_files; echo ---; '
                  'type copy_as_hyperos')
        output = subprocess.run(['sh', '-c', script, 'sh', str(ROOT / 'common/legacy_v14_4/rom_adapters.sh')],
                                check=True, text=True, capture_output=True).stdout
        active, retired, body = output.split('---')
        self.assertNotIn('Italic', active)
        self.assertIn('Roboto-Italic.ttf', retired.split())
        self.assertIn('Roboto-Regular.ttf', active.split())
        self.assertNotIn('Italic.ttf"', body)


class ColorOSAlignmentTest(AlignmentBase):
    def test_coloros_slots_and_unrecorded_family_members_use_stock_frames(self):
        regular = self.stock('system', 'SysSans-Hans-Regular.ttf', 'SysSans')
        osui = self.stock('system', 'OplusOSUI-Regular.ttf', 'MiSansVF')
        osui_medium = self.stock('system', 'OplusOSUI-Medium.ttf', 'MiSansVF', record=False, weight=500)
        self.stock('system', 'OplusOSUI-Italic.ttf', 'MiSansVF', record=False)
        self.write_inventory('/system/fonts/SysSans-Hans-Regular.ttf')
        fonts = self.stage / 'system/fonts'
        for key in ('ttf-1000', 'ttf-2048', 'cff-1000'):
            with self.subTest(donor=key):
                if fonts.exists():
                    subprocess.run(['rm', '-rf', str(self.stage)], check=True)
                fonts.mkdir(parents=True)
                donor = self.donor(key, self.root / f'{key}.font')
                for name in ('SysSans-Hans-Regular.ttf', 'OplusOSUI-Regular.ttf',
                             'OplusOSUI-Medium.ttf', 'OplusOSUI-Italic.ttf'):
                    os.link(donor, fonts / name)
                coloros.build(self.module, self.stage)
                self.assert_same_frame(fonts / 'SysSans-Hans-Regular.ttf', regular, f'{key} SysSans')
                self.assert_same_frame(fonts / 'OplusOSUI-Regular.ttf', osui, f'{key} OplusOSUI')
                # Previously kept the donor's own hhea/OS2 (missing-or-ineligible).
                self.assert_same_frame(fonts / 'OplusOSUI-Medium.ttf', osui_medium, f'{key} OplusOSUI-Medium')
                reports = self.report()
                self.assertEqual(reports['/system/fonts/OplusOSUI-Medium.ttf']['metricsSource'], 'stock-sibling')
                self.assertEqual(reports['/system/fonts/SysSans-Hans-Regular.ttf']['metricsSource'], 'stock')
                # Italic stays out of the metric stage entirely.
                self.assertEqual(reports['/system/fonts/OplusOSUI-Italic.ttf']['metricsSource'], 'preserved')
                self.assertEqual((fonts / 'OplusOSUI-Italic.ttf').read_bytes(), donor.read_bytes())


class FastPatchParityTest(AlignmentBase):
    def test_fast_patch_equals_full_save_for_stock_and_sibling_contracts(self):
        self.stock('system', 'Roboto-Regular.ttf', 'Roboto')
        self.stock('system', 'SysSans-Hans-Regular.ttf', 'SysSans')
        data = {'slots': self.slots}
        stock_contract, _ = batch.resolve_slot_contract(data, '/system/fonts/Roboto-Regular.ttf')
        sibling, reference = batch.resolve_slot_contract(data, '/system/fonts/Roboto-Medium.ttf')
        typo_contract, _ = batch.resolve_slot_contract(data, '/system/fonts/SysSans-Hans-Regular.ttf')
        self.assertEqual(stock_contract[-1], 'stock')
        self.assertEqual((sibling[-1], reference), ('stock-sibling', '/system/fonts/Roboto-Regular.ttf'))
        self.assertEqual(sibling[:-1], stock_contract[:-1])
        for key in ('ttf-1000', 'ttf-2048', 'cff-1000', 'vf-1000'):
            for label, contract in (('stock', stock_contract), ('sibling', sibling), ('typo', typo_contract)):
                with self.subTest(donor=key, contract=label):
                    source = self.donor(key, self.root / f'{key}.font')
                    fast, slow = self.root / 'fast.font', self.root / 'slow.font'
                    calls = []
                    original = batch._patch_metric_tables

                    def tracked(*args):
                        calls.append(original(*args))
                        return calls[-1]
                    with patch.object(batch, '_patch_metric_tables', new=tracked):
                        fast_report = batch.write_metrics(source, fast, contract)
                    with patch.object(batch, '_patch_metric_tables', new=lambda *args: False):
                        slow_report = batch.write_metrics(source, slow, contract)
                    self.assertEqual(calls, [True], 'metrics-only alias must take the patch path')
                    self.assertEqual(fast_report, slow_report)
                    with TTFont(fast) as a, TTFont(slow) as b:
                        self.assertEqual(sorted(a.keys()), sorted(b.keys()))
                        for tag in ('hhea', 'OS/2'):
                            self.assertEqual(a[tag].compile(a), b[tag].compile(b), tag)
                        head_a, head_b = dict(vars(a['head'])), dict(vars(b['head']))
                        head_a.pop('checkSumAdjustment'); head_b.pop('checkSumAdjustment')
                        self.assertEqual(head_a, head_b)
                    self.assertEqual(glyph_bytes(fast), glyph_bytes(slow))
                    self.assertEqual(self.frame(fast), self.frame(slow))

    def test_mvar_donor_takes_full_save_and_loses_mvar(self):
        self.stock('system', 'MiSansVF.ttf', 'MiSansVF')
        contract, _ = batch.resolve_slot_contract({'slots': self.slots}, '/system/fonts/MiSansVF.ttf')
        source = self.donor('vf-mvar', self.root / 'mvar.font')
        with TTFont(source) as font:
            self.assertIn('MVAR', font)
        calls = []
        with patch.object(batch, '_patch_metric_tables', new=lambda *a: calls.append(1) or True):
            batch.write_metrics(source, self.root / 'out.font', contract)
        self.assertEqual(calls, [])
        with TTFont(self.root / 'out.font') as font:
            self.assertNotIn('MVAR', font)
            self.assertIn('fvar', font)


class HyperOSXmlScanTest(unittest.TestCase):
    """hyper_fonts.xml / miui_font_fallback.xml are HyperOS's live font configs."""

    def test_hyperos_font_xml_names_and_families_are_scanned(self):
        import contextlib, io
        import font_inventory_scan as scanner
        from font_inventory import _is_ui_family
        for family in ('mipro', 'mipro-medium', 'miui', 'milanpro', 'xiaomisans-bold'):
            self.assertTrue(scanner._is_ui_family(family), family)
            self.assertTrue(_is_ui_family(family), family)
        for family in ('miui-mono', 'mipro-serif', 'miui-emoji'):
            self.assertFalse(scanner._is_ui_family(family), family)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fonts, etc = root / 'system_ext/fonts', root / 'system_ext/etc'
            system_fonts, system_etc = root / 'system/fonts', root / 'system/etc'
            for path in (fonts, etc, system_fonts, system_etc):
                path.mkdir(parents=True)
            # Digits + caps only: the coverage-only pass rejects it (no full
            # alphabet), so only the HyperOS XML can make it a stock slot.
            build_font(fonts / 'MiProDisplay-Regular.ttf', 1000, ascent=1044, descent=-282)
            build_font(system_fonts / 'Roboto-Regular.ttf', 2048, ascent=1900, descent=-500)
            (system_etc / 'fonts.xml').write_text(
                '<familyset><family name="sans-serif"><font weight="400">Roboto-Regular.ttf'
                '</font></family></familyset>', encoding='utf-8')
            (etc / 'hyper_fonts.xml').write_text(
                '<familyset><family name="mipro"><font weight="400">MiProDisplay-Regular.ttf'
                '</font></family></familyset>', encoding='utf-8')
            args = scanner.build_parser().parse_args([
                '--scan', '--build-key', 'xml-fixture', '--output', str(root / 'inventory.json')])
            for specs in (scanner.PRIMARY_FONT_SPECS, scanner.PRIMARY_ETC_SPECS,
                          scanner.AUX_FONT_SPECS, scanner.AUX_ETC_SPECS):
                for spec in specs:
                    setattr(args, spec[2], root / 'missing' / spec[2])
            args.system_fonts, args.system_etc = system_fonts, system_etc
            args.system_ext_fonts, args.system_ext_etc = fonts, etc
            args.force = True
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scanner.scan(args), 0)
            result = json.loads((root / 'inventory.json').read_text())
            self.assertIn('/system_ext/etc/hyper_fonts.xml', result['xmlSources'])
            slot = result['slots']['/system_ext/fonts/MiProDisplay-Regular.ttf']
            self.assertEqual(slot['families'], ['mipro'])
            self.assertTrue(batch.inventory_completion_slot(slot, '/system_ext/fonts/MiProDisplay-Regular.ttf'))


class FamilyStemTest(unittest.TestCase):
    def test_weight_suffixes_share_one_family(self):
        stem = batch.family_stem
        self.assertEqual(stem('OplusOSUI-Medium.ttf'), stem('OplusOSUI-Regular.ttf'))
        self.assertEqual(stem('SysSans-Hans-Bold.ttf'), 'syssans-hans')
        self.assertNotEqual(stem('SysSans-Hans-Bold.ttf'), stem('SysSans-En-Bold.ttf'))
        self.assertEqual(stem('GoogleSansText-SemiBold.ttf'), 'googlesanstext')
        self.assertNotEqual(stem('GoogleSansText-Medium.ttf'), stem('GoogleSans-Medium.ttf'))
        self.assertNotEqual(stem('MiSansVF.ttf'), stem('MiSansLatinVF.ttf'))
        self.assertEqual(stem('700.ttf'), stem('350.ttf'))
        self.assertEqual(stem('Regular.ttf'), 'regular')


if __name__ == '__main__':
    unittest.main()
