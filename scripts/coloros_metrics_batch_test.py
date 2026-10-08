#!/usr/bin/env python3
"""Exercise the real ColorOS staged aliases, including distinct weight sources."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.sfnt import SFNTReader
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from font_inventory import _read_metrics
import coloros_metrics_batch as batch


def font_file(path, top=800, cff=False, points=None, variable=False, uvs=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if points is None:
        points = (65, 49, 0x4E2D)
    original_names = {65: 'A', 49: 'one', 0x4E2D: 'uni4E2D'}
    cmap = {cp: original_names.get(cp, f'u{cp:X}') for cp in points}
    order = ['.notdef', *cmap.values()]
    glyphs = {}
    for name in order:
        pen = T2CharStringPen(600, None) if cff else TTGlyphPen(None)
        pen.moveTo((0, -50)); pen.lineTo((500, -50))
        pen.lineTo((500, top)); pen.lineTo((0, top)); pen.closePath()
        glyphs[name] = pen.getCharString() if cff else pen.glyph()
    fb = FontBuilder(1000, isTTF=not cff)
    fb.setupGlyphOrder(order); fb.setupCharacterMap(cmap)
    if cff:
        fb.setupCFF('ColorOSFixture', {'FullName': 'ColorOSFixture'}, glyphs, {})
    else:
        fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (600, 0) for name in order})
    fb.setupHorizontalHeader(ascent=1600, descent=-600)
    fb.setupOS2(sTypoAscender=1600, sTypoDescender=-600,
               usWinAscent=1700, usWinDescent=700)
    fb.setupNameTable({'familyName': 'ColorOSFixture', 'styleName': 'Regular'})
    fb.setupPost(); fb.setupMaxp()
    if variable:
        fb.setupFvar([('wght', 100, 400, 900, 'Weight')], [])
        fb.setupGvar({name: [] for name in order})
    if uvs:
        table = CmapSubtable.newSubtable(14)
        table.platformID = 0; table.platEncID = 5; table.language = 0
        table.cmap = {}
        table.uvsDict = {0xFE00: [(0x56FD, None)]}
        fb.font['cmap'].tables.append(table)
    fb.save(path)


def stock(ascent=920, descent=-240, head=(-250, 1050), upem=1000):
    result = {'metrics': {'upem': upem,
        'hhea': {'ascent': ascent, 'descent': descent, 'lineGap': 0},
        'os2': {'typoAscender': ascent - 10, 'typoDescender': descent,
                'typoLineGap': 0, 'winAscent': ascent + 20,
                'winDescent': -descent + 20, 'fsSelection': 128}}}
    if head is not None:
        result['metrics']['head'] = {'yMin': head[0], 'yMax': head[1]}
    return result


class ColorOSMetricsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.stage = self.module / '.luoshu-payload-next'
        self.stage.mkdir(parents=True)
        (self.module / 'config').mkdir()
        self.env = patch.dict(os.environ, {'LUOSHU_BUILD_KEY': 'coloros-fixture'})
        self.env.start(); self.addCleanup(self.env.stop)

    def target(self, name='SysSans-Hans-Regular.ttf', partition='system'):
        return self.stage / partition / 'fonts' / name

    def inventory(self, slots, build='coloros-fixture'):
        (self.module / 'config/device_font_inventory.json').write_text(json.dumps({
            'schema': 'device-font-inventory-v1', 'inventoryRevision': 1,
            'state': 'ready', 'buildKey': build, 'slots': slots}))

    def report(self):
        result = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())
        self.assertEqual(result['schema'], 'luoshu-slot-metrics-v1')
        self.assertEqual(result['romKind'], 'coloros')
        return result['slots']

    def stock_file(self, name, partition='system', symlink=False):
        root = self.root / 'stock' / partition
        root.mkdir(parents=True, exist_ok=True)
        path = root / name
        if symlink:
            donor = root / 'framework-managed.ttf'
            font_file(donor)
            path.symlink_to(donor)
        else:
            font_file(path)
        os.environ[f'LUOSHU_{partition.upper()}_FONTS_ROOT'] = str(root)
        return path

    def collection_file(self, path, faces=2, missing_last_cmap=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        members = []
        try:
            for index in range(faces):
                member = self.root / f'collection-face-{index}.ttf'
                font_file(member, top=800 + index * 100)
                font = TTFont(member)
                if missing_last_cmap and index == faces - 1:
                    del font['cmap']
                members.append(font)
            collection = TTCollection()
            collection.fonts = members
            collection.save(path)
        finally:
            for font in members:
                font.close()
        return path

    def real_collection_slot(self, name='SysFont-Regular.ttf', face=1):
        path = self.collection_file(self.stock_file(name))
        fmt, metrics = _read_metrics(path, face)
        return path, {'format': fmt, 'faceIndex': face, 'metrics': metrics}

    def test_restores_each_existing_alias_and_preserves_real_weight_source(self):
        regular = self.target()
        bold = self.target('SysSans-Hans-Bold.ttf')
        numeric = self.target('400.ttf')
        font_file(regular, top=730); font_file(bold, top=940); font_file(numeric, top=1100)
        originals = {path.name: path.read_bytes() for path in (regular, bold, numeric)}
        self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': stock(),
                        '/system/fonts/SysSans-Hans-Bold.ttf': stock(),
                        '/system/fonts/SysSans-En-Regular.ttf': stock()})
        with patch.object(TTFont, 'getGlyphSet', side_effect=AssertionError('outline rebuild')):
            result = batch.build(self.module, self.stage)
        self.assertEqual(result, {'mapped': 2, 'generated': 2, 'preservedSlots': 1})
        self.assertFalse(self.target('SysSans-En-Regular.ttf').exists(), 'must not add slots')
        self.assertEqual(numeric.read_bytes(), originals[numeric.name])
        for path, top in ((regular, 730), (bold, 940)):
            with TTFont(path) as font:
                self.assertEqual(font['hhea'].ascent, 920)
                self.assertEqual(font['head'].yMax, 1050)
                self.assertEqual(font['glyf']['A'].yMax, top)
        self.assertEqual(len(self.report()), 3)

    def test_cross_partition_hardlinks_do_not_cascade_or_share_distinct_frames(self):
        regular = self.target(); font_file(regular)
        product = self.target(partition='oplus_product')
        product.parent.mkdir(parents=True); os.link(regular, product)
        same = self.target('SysFont-Regular.ttf'); os.link(regular, same)
        source_bytes = regular.read_bytes()
        self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': stock(),
                        '/system/fonts/SysFont-Regular.ttf': stock(),
                        '/oplus_product/fonts/SysSans-Hans-Regular.ttf': stock(
                            ascent=1800, descent=-400, head=(-410, 2000), upem=2000)})
        writer = batch.write_metrics
        def checked_writer(source, output, contract, **options):
            for path in (regular, product, same):
                self.assertEqual(path.read_bytes(), source_bytes,
                                 'every font must be generated before replacing aliases')
            return writer(source, output, contract, **options)
        with patch.object(batch, 'write_metrics', side_effect=checked_writer):
            result = batch.build(self.module, self.stage)
        self.assertEqual(result['generated'], 3)
        self.assertNotEqual(regular.stat().st_ino, same.stat().st_ino,
                            'Latin alignment must not leak into CJK aliases')
        self.assertNotEqual(regular.stat().st_ino, product.stat().st_ino)
        with TTFont(product) as font:
            self.assertEqual(font['hhea'].ascent, 900)
            self.assertEqual((font['head'].yMin, font['head'].yMax), (-205, 1000))

    def test_ttf_and_cff_tables_are_not_recompiled(self):
        for cff, name, table in ((False, 'SysSans-Hans-Regular.ttf', 'glyf'),
                                 (True, 'OPPODIN-Regular.otf', 'CFF ')):
            font_file(self.target(name), cff=cff)
        raw = {}
        for name, table in (('SysSans-Hans-Regular.ttf', 'glyf'), ('OPPODIN-Regular.otf', 'CFF ')):
            with TTFont(self.target(name), lazy=True) as font:
                raw[name] = (table, font.reader[table])
        self.inventory({f'/system/fonts/{name}': stock() for name in raw})
        with patch.object(TTFont, 'getGlyphSet', side_effect=AssertionError('outline rebuild')):
            batch.build(self.module, self.stage)
        for name, (table, contents) in raw.items():
            with TTFont(self.target(name), lazy=True) as font:
                self.assertEqual(font.reader[table], contents)

    def test_missing_stale_or_invalid_inventory_does_not_use_hyperos_fallback(self):
        font_file(self.target())
        original = self.target().read_bytes()
        for mode in ('missing', 'stale', 'invalid'):
            with self.subTest(mode=mode):
                if mode == 'stale':
                    self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': stock()}, build='old')
                elif mode == 'invalid':
                    self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': stock(ascent=-1)})
                result = batch.build(self.module, self.stage)
                self.assertEqual(result['mapped'], 0)
                self.assertEqual(self.target().read_bytes(), original)
                self.assertEqual(self.report()[0]['metricsSource'], 'preserved')

    def test_old_inventory_without_head_preserves_source_bounds(self):
        font_file(self.target())
        self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': stock(head=None)})
        batch.build(self.module, self.stage)
        with TTFont(self.target()) as font:
            self.assertEqual(font['hhea'].ascent, 920)
            self.assertEqual((font['head'].yMin, font['head'].yMax), (-50, 800))
        self.assertEqual(self.report()[0]['layoutBoundsSource'], 'source')

    def test_ineligible_symbol_slot_and_path_mismatch_are_preserved(self):
        self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': {
                            **stock(), 'path': '/system/fonts/another.ttf'},
                        '/system/fonts/StatusIcons.ttf': {**stock(), 'families': ['sans-serif']},
                        '/system/fonts/NovelFont.ttf': {**stock(), 'families': ['serif']}})
        paths = [self.target(name) for name in ('SysSans-Hans-Regular.ttf', 'StatusIcons.ttf', 'NovelFont.ttf')]
        for path in paths:
            font_file(path)
        originals = [path.read_bytes() for path in paths]
        self.assertEqual(batch.build(self.module, self.stage)['mapped'], 0)
        self.assertEqual([path.read_bytes() for path in paths], originals)

    def test_explicit_ui_xml_slot_can_use_an_unusual_filename(self):
        target = self.target('VendorText.otf'); font_file(target, cff=True)
        self.inventory({'/system/fonts/VendorText.otf': {**stock(), 'families': ['sans-serif']}})
        self.assertEqual(batch.build(self.module, self.stage)['mapped'], 1)

    def test_completes_existing_inventory_slots_in_real_partitions_and_uses_weight_donors(self):
        regular = self.target(); font_file(regular, top=730)
        store = regular.parent / '.luoshu-font-store'
        font_file(store / 'regular.font', top=730)
        font_file(store / 'semibold.font', top=950)
        slots = {'/system/fonts/SysSans-Hans-Regular.ttf': stock()}
        for partition, name, weight, ascent in (
                ('product', 'VendorText.otf', 600, 810),
                ('oplus_product', 'GoogleSansText-VF.ttf', 400, 910)):
            self.stock_file(name, partition)
            slots[f'/{partition}/fonts/{name}'] = {
                **stock(ascent=ascent), 'families': ['sans-serif'], 'source': 'xml', 'weight': weight}
        self.inventory(slots)
        result = batch.build(self.module, self.stage)
        self.assertEqual(result, {'mapped': 3, 'generated': 3, 'preservedSlots': 0})
        for partition, name, top, ascent in (
                ('product', 'VendorText.otf', 950, 810),
                ('oplus_product', 'GoogleSansText-VF.ttf', 730, 910)):
            with TTFont(self.target(name, partition)) as font:
                self.assertEqual(font['glyf']['A'].yMax, top)
                self.assertEqual(font['hhea'].ascent, ascent)
        self.assertEqual(sum(row.get('slotSource') == 'stock-inventory' for row in self.report()), 2)

    def test_completes_scanner_verified_unusual_text_without_a_rom_filename_list(self):
        font_file(self.target())
        font_file(self.target().parent / '.luoshu-font-store/regular.font')
        self.stock_file('NovelUI.ttf')
        coverage = {'hasHan': False, 'hasLatin': True, 'hanCount': 0,
                    'latinCount': 52, 'unicodeCount': 96, 'cjkPunctuation': []}
        slot = stock(); slot['metrics']['coverage'] = coverage
        self.inventory({'/system/fonts/NovelUI.ttf': {**slot, 'source': 'verified-scan'}})
        self.assertEqual(batch.build(self.module, self.stage)['mapped'], 1)
        self.assertTrue(self.target('NovelUI.ttf').exists())

    def test_completion_does_not_promote_symbols_scripts_collections_or_dynamic_symlinks(self):
        font_file(self.target())
        font_file(self.target().parent / '.luoshu-font-store/regular.font')
        slots = {}
        names = ('StatusIcons.ttf', 'NotoSansArabic.ttf', 'RobotoMono.ttf', 'Roboto-Italic.ttf',
                 'VendorCollection.ttc', 'NovelUI.ttf', 'ExternalUI.ttf', 'GoogleSansManaged.ttf')
        for name in names:
            self.stock_file(name, symlink=name == 'GoogleSansManaged.ttf')
            slots[f'/system/fonts/{name}'] = {**stock(), 'families': ['sans-serif']}
        slots['/system/fonts/NovelUI.ttf']['source'] = 'verified-scan'  # no measured coverage
        slots['/system/fonts/NovelUI.ttf']['families'] = []
        slots['/system/fonts/ExternalUI.ttf']['faceIndex'] = 1
        self.inventory(slots)
        self.assertEqual(batch.build(self.module, self.stage)['mapped'], 0)
        for name in names:
            self.assertFalse(self.target(name).exists(), name)

    def test_dynamic_partition_completion_requires_safe_manifest_and_canonical_slot_path(self):
        font_file(self.target())
        font_file(self.target().parent / '.luoshu-font-store/regular.font')
        for part in ('vendor_custom', 'unrecorded', 'data'):
            self.stock_file('VendorUI.ttf', part)
        (self.module / 'config/device_font_partitions.conf').write_text('vendor_custom\ndata\n../escape\n')
        self.inventory({f'/{part}/fonts/VendorUI.ttf': {**stock(), 'families': ['sans-serif']}
                        for part in ('vendor_custom', 'unrecorded', 'data')})
        self.assertEqual(batch.build(self.module, self.stage)['mapped'], 1)
        self.assertTrue(self.target('VendorUI.ttf', 'vendor_custom').exists())
        self.assertFalse(self.target('VendorUI.ttf', 'unrecorded').exists())
        self.assertFalse(self.target('VendorUI.ttf', 'data').exists())

    def test_completion_rejects_stage_font_directory_escape(self):
        font_file(self.target())
        font_file(self.target().parent / '.luoshu-font-store/regular.font')
        self.stock_file('VendorUI.ttf', 'product')
        outside = self.root / 'outside'; outside.mkdir()
        (self.stage / 'product').symlink_to(outside, target_is_directory=True)
        self.inventory({'/product/fonts/VendorUI.ttf': {**stock(), 'families': ['sans-serif']}})
        with self.assertRaisesRegex(ValueError, '隔离目录之外'):
            batch.build(self.module, self.stage)
        self.assertEqual(list(outside.iterdir()), [])

    def test_collection_is_preserved_instead_of_discarding_other_faces(self):
        first = self.root / 'first.ttf'; second = self.root / 'second.ttf'
        font_file(first); font_file(second, top=900)
        path = self.target('SysSans-Hans-Regular.ttc'); path.parent.mkdir(parents=True)
        with TTFont(first) as a, TTFont(second) as b:
            collection = TTCollection(); collection.fonts = [a, b]; collection.save(path)
        original = path.read_bytes()
        stock_path = self.stock_file(path.name)
        stock_path.write_bytes(original)
        self.inventory({'/system/fonts/SysSans-Hans-Regular.ttc': {**stock(), 'faceIndex': 1}})
        self.assertEqual(batch.build(self.module, self.stage)['mapped'], 0)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.report()[0]['reason'], 'collection-metrics-preserved')

    def test_incomplete_staged_collection_keeps_every_stock_face_visible(self):
        name = 'SysFont-Regular.ttf'
        stock_path, slot = self.real_collection_slot(name)
        original = stock_path.read_bytes()
        path = self.collection_file(self.target(name), faces=1)
        self.inventory({f'/system/fonts/{name}': slot})

        result = batch.build(self.module, self.stage)

        self.assertFalse(path.exists(), 'ttcf header is not proof that stock face 1 survives')
        self.assertEqual(stock_path.read_bytes(), original)
        with TTFont(stock_path, fontNumber=1) as retained:
            self.assertEqual(retained['glyf']['A'].yMax, 900)
        self.assertEqual(result['mapped'], 0)
        self.assertEqual(self.report()[0]['reason'], 'stock-collection-slot-preserved')

    def test_staged_collection_requires_all_faces_readable_not_only_selected_index(self):
        name = 'SysFont-Regular.ttf'
        stock_path, slot = self.real_collection_slot(name, face=0)
        original = stock_path.read_bytes()
        path = self.collection_file(self.target(name), missing_last_cmap=True)
        self.inventory({f'/system/fonts/{name}': slot})
        result = batch.build(self.module, self.stage)
        self.assertFalse(path.exists(), 'an unreadable unselected face still violates the stock collection')
        self.assertEqual(stock_path.read_bytes(), original)
        self.assertEqual(result['mapped'], 0)

    def test_truncated_staged_collection_exposes_stock_without_parsing_metrics(self):
        name = 'SysFont-Regular.ttf'
        stock_path, slot = self.real_collection_slot(name)
        original = stock_path.read_bytes()
        path = self.target(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'ttcf\x00\x01\x00\x00\x00\x00\x00\x02\x00')
        self.inventory({f'/system/fonts/{name}': slot})
        with patch.object(batch, 'write_metrics', side_effect=AssertionError('unreadable collection writer')):
            batch.build(self.module, self.stage)
        self.assertFalse(path.exists())
        self.assertEqual(stock_path.read_bytes(), original)

    def test_collection_stock_missing_or_invalid_contract_fails_without_stage_mutation(self):
        name = 'SysFont-Regular.ttf'
        for failure in ('missing-stock', 'broken-stock', 'invalid-index'):
            with self.subTest(failure=failure):
                stock_path, slot = self.real_collection_slot(name)
                path = self.collection_file(self.target(name))
                original = path.read_bytes()
                if failure == 'missing-stock':
                    stock_path.unlink()
                elif failure == 'broken-stock':
                    stock_path.write_bytes(b'ttcfbroken')
                else:
                    slot['faceIndex'] = 2
                self.inventory({f'/system/fonts/{name}': slot})
                with self.assertRaisesRegex(ValueError, '原厂.*集合|原厂.*索引'):
                    batch.build(self.module, self.stage)
                self.assertEqual(path.read_bytes(), original)

    def test_matching_staged_collection_keeps_faces_and_bytes(self):
        name = 'SysFont-Regular.ttf'
        stock_path, slot = self.real_collection_slot(name)
        original_stock = stock_path.read_bytes()
        path = self.collection_file(self.target(name))
        original = path.read_bytes()
        self.inventory({f'/system/fonts/{name}': slot})
        self.assertEqual(batch.build(self.module, self.stage)['mapped'], 0)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(stock_path.read_bytes(), original_stock)
        self.assertEqual(self.report()[0]['reason'], 'collection-metrics-preserved')

    def test_collection_index_type_and_declared_container_must_match_real_stock(self):
        name = 'SysFont-Regular.ttf'
        for failure in ('negative-index', 'boolean-index', 'string-index',
                        'stock-collection-declared-single', 'stock-single-declared-collection'):
            with self.subTest(failure=failure):
                stock_path, slot = self.real_collection_slot(name, face=0)
                path = self.collection_file(self.target(name))
                if failure == 'negative-index':
                    slot['faceIndex'] = -1
                elif failure == 'boolean-index':
                    slot['faceIndex'] = False
                    font_file(path)
                elif failure == 'string-index':
                    slot['faceIndex'] = '0'
                elif failure == 'stock-collection-declared-single':
                    slot['format'] = 'TTF'
                else:
                    font_file(stock_path)
                original_stock, original_stage = stock_path.read_bytes(), path.read_bytes()
                self.inventory({f'/system/fonts/{name}': slot})
                with self.assertRaisesRegex(ValueError, '原厂.*集合|原厂.*索引'):
                    batch.build(self.module, self.stage)
                self.assertEqual(stock_path.read_bytes(), original_stock)
                self.assertEqual(path.read_bytes(), original_stage)

    def test_extra_staged_faces_are_not_a_matching_stock_collection(self):
        name = 'SysFont-Regular.ttf'
        stock_path, slot = self.real_collection_slot(name)
        original_stock = stock_path.read_bytes()
        path = self.collection_file(self.target(name), faces=3)
        self.inventory({f'/system/fonts/{name}': slot})
        batch.build(self.module, self.stage)
        self.assertFalse(path.exists())
        self.assertEqual(stock_path.read_bytes(), original_stock)

    def test_unselected_stock_face_must_be_readable_before_alias_can_be_removed(self):
        name = 'SysFont-Regular.ttf'
        stock_path, slot = self.real_collection_slot(name, face=0)
        self.collection_file(stock_path, missing_last_cmap=True)
        path = self.collection_file(self.target(name), faces=1)
        original_stock, original_stage = stock_path.read_bytes(), path.read_bytes()
        self.inventory({f'/system/fonts/{name}': slot})
        with self.assertRaisesRegex(ValueError, '原厂.*集合结构无效'):
            batch.build(self.module, self.stage)
        self.assertEqual(stock_path.read_bytes(), original_stock)
        self.assertEqual(path.read_bytes(), original_stage)

    def test_invalid_unselected_face_header_is_not_a_readable_collection_contract(self):
        name = 'SysFont-Regular.ttf'
        for bad_stock in (True, False):
            with self.subTest(bad_stock=bad_stock):
                stock_path, slot = self.real_collection_slot(name, face=0)
                path = self.collection_file(self.target(name))
                invalid = stock_path if bad_stock else path
                with TTCollection(invalid) as collection:
                    collection.fonts[1]['head'].unitsPerEm = 0
                    collection.save(invalid)
                original_stock, original_stage = stock_path.read_bytes(), path.read_bytes()
                self.inventory({f'/system/fonts/{name}': slot})
                if bad_stock:
                    with self.assertRaisesRegex(ValueError, '原厂.*集合结构无效'):
                        batch.build(self.module, self.stage)
                    self.assertEqual(path.read_bytes(), original_stage)
                else:
                    batch.build(self.module, self.stage)
                    self.assertFalse(path.exists())
                self.assertEqual(stock_path.read_bytes(), original_stock)

    def test_collection_guard_uses_stock_namespace_for_cross_partition_absolute_links(self):
        name = 'SysFont-Regular.ttf'
        stock_path, slot = self.real_collection_slot(name)
        product = self.collection_file(self.stock_file('RealCollection.ttc', 'product'))
        stock_path.unlink()
        stock_path.symlink_to('/product/fonts/RealCollection.ttc')
        original_stock = product.read_bytes()
        path = self.collection_file(self.target(name), faces=1)
        self.inventory({f'/system/fonts/{name}': slot})
        batch.build(self.module, self.stage)
        self.assertFalse(path.exists())
        self.assertEqual(product.read_bytes(), original_stock)

    def test_collection_guard_rejects_stage_as_an_explicit_stock_view(self):
        name = 'SysFont-Regular.ttf'
        path = self.collection_file(self.target(name))
        original = path.read_bytes()
        os.environ['LUOSHU_SYSTEM_FONTS_ROOT'] = str(path.parent)
        self.inventory({f'/system/fonts/{name}': {**stock(), 'format': 'TTC', 'faceIndex': 1}})
        with self.assertRaisesRegex(ValueError, '原厂.*可信'):
            batch.build(self.module, self.stage)
        self.assertEqual(path.read_bytes(), original)

    def test_collection_all_face_inspection_is_cached_for_hardlinked_aliases(self):
        name = 'SysFont-Regular.ttf'
        stock_path, slot = self.real_collection_slot(name)
        path = self.collection_file(self.target(name))
        second_name = 'SysFont-Bold.ttf'
        os.link(stock_path, stock_path.with_name(second_name))
        second = self.target(second_name)
        os.link(path, second)
        self.inventory({f'/system/fonts/{name}': slot,
                        f'/system/fonts/{second_name}': {**slot, 'faceIndex': 0}})
        reads = []
        table_reads = {}
        original_open = Path.open
        original_table_read = SFNTReader.__getitem__
        def counted_open(candidate, *args, **kwargs):
            if candidate in (path, second, stock_path, stock_path.with_name(second_name)):
                reads.append(candidate.name + ':' + (args[0] if args else kwargs.get('mode', 'r')))
            return original_open(candidate, *args, **kwargs)
        def counted_table_read(reader, tag):
            key = (str(reader.file.name), reader.tables['head'].offset, str(tag))
            table_reads[key] = table_reads.get(key, 0) + 1
            return original_table_read(reader, tag)
        with patch.object(Path, 'open', counted_open), \
                patch.object(SFNTReader, '__getitem__', counted_table_read), \
                patch.object(batch, 'write_metrics', side_effect=AssertionError('collection writer')):
            result = batch.build(self.module, self.stage)
        self.assertEqual(result['mapped'], 0)
        self.assertEqual(reads, ['SysFont-Bold.ttf:rb', 'SysFont-Bold.ttf:rb',
                                 'SysFont-Bold.ttf:rb', 'SysFont-Regular.ttf:rb'])
        self.assertEqual({row['stockFaceCount'] for row in self.report()}, {2})
        self.assertEqual(len(table_reads), 32, 'eight core tables per face in each namespace')
        self.assertEqual(set(table_reads.values()), {1}, 'hardlinked aliases never reread font tables')

    def test_incomplete_collection_is_not_removed_if_another_job_fails(self):
        name = 'SysFont-Regular.ttf'
        stock_path, slot = self.real_collection_slot(name)
        path = self.collection_file(self.target(name), faces=1)
        normal = self.target('SysSans-Hans-Regular.ttf'); font_file(normal)
        broken = self.target('SysSans-Z-Broken.ttf'); broken.write_bytes(b'brokenfont')
        original_stage, original_stock = path.read_bytes(), stock_path.read_bytes()
        original_normal = normal.read_bytes()
        self.inventory({f'/system/fonts/{name}': slot,
                        '/system/fonts/SysSans-Hans-Regular.ttf': stock(),
                        '/system/fonts/SysSans-Z-Broken.ttf': stock()})
        with self.assertRaises(Exception):
            batch.build(self.module, self.stage)
        self.assertEqual(path.read_bytes(), original_stage)
        self.assertEqual(stock_path.read_bytes(), original_stock)
        self.assertEqual(normal.read_bytes(), original_normal)
        self.assertFalse((self.stage / '.luoshu-metrics-report.json').exists())
        self.assertFalse(list(self.stage.glob('.coloros-metrics-*')))

    def test_single_face_alias_keeps_stock_collection_and_nonzero_faces_visible(self):
        for name, fmt, face in (('SysFont-Regular.ttf', 'TTC', 1),
                                ('SysSans-Hans-Regular.ttc', 'TTC', 0),
                                ('SysSans-Hant-Regular.otf', 'OTC', 1)):
            with self.subTest(name=name, face=face):
                path = self.target(name)
                font_file(path)
                stock_path = self.stock_file(name)
                second = self.root / 'second-stock.ttf'
                font_file(second, top=900)
                with TTFont(stock_path) as first, TTFont(second) as other:
                    collection = TTCollection()
                    collection.fonts = [first, other]
                    collection.save(stock_path)
                original = stock_path.read_bytes()
                actual_format, metrics = _read_metrics(stock_path, face)
                self.assertEqual(actual_format, 'TTC')
                self.inventory({f'/system/fonts/{name}': {
                    'format': fmt, 'faceIndex': face, 'metrics': metrics}})

                result = batch.build(self.module, self.stage)

                self.assertFalse(path.exists(), 'single-face alias must expose the original collection')
                self.assertEqual(stock_path.read_bytes(), original)
                with TTFont(stock_path, fontNumber=1) as retained:
                    self.assertEqual(retained['glyf']['A'].yMax, 900)
                self.assertEqual(result['mapped'], 0)
                self.assertEqual(self.report()[0]['reason'], 'stock-collection-slot-preserved')

    def test_nonzero_stock_index_alias_is_preserved_before_metrics_reads(self):
        path = self.target('SysFont-Regular.ttf')
        font_file(path)
        _, slot = self.real_collection_slot(path.name)
        self.inventory({'/system/fonts/SysFont-Regular.ttf': slot})
        with patch.object(batch, 'write_metrics', side_effect=AssertionError('unsafe single-face write')):
            result = batch.build(self.module, self.stage)
        self.assertFalse(path.exists())
        self.assertEqual(result['mapped'], 0)
        self.assertEqual(self.report()[0]['reason'], 'stock-collection-slot-preserved')

    def test_stock_collection_alias_is_preserved_even_when_metrics_are_invalid(self):
        path = self.target('SysFont-Regular.ttf')
        font_file(path)
        self.real_collection_slot(path.name)
        self.inventory({'/system/fonts/SysFont-Regular.ttf': {'format': 'TTC', 'metrics': {}}})
        result = batch.build(self.module, self.stage)
        self.assertFalse(path.exists())
        self.assertEqual(result['mapped'], 0)
        self.assertEqual(self.report()[0]['reason'], 'stock-collection-slot-preserved')

    def test_single_face_stock_slot_still_aligns_metrics_without_extra_header_reads(self):
        path = self.target('SysFont-Regular.ttf')
        font_file(path, top=730)
        self.inventory({'/system/fonts/SysFont-Regular.ttf': {
            **stock(), 'format': 'TTF', 'faceIndex': 0}})
        reads = []
        original_open = Path.open

        def counted_open(candidate, *args, **kwargs):
            if candidate == path:
                reads.append(args[0] if args else kwargs.get('mode', 'r'))
            return original_open(candidate, *args, **kwargs)

        with patch.object(Path, 'open', counted_open):
            result = batch.build(self.module, self.stage)
        self.assertEqual(result['mapped'], 1)
        with TTFont(path) as retained:
            self.assertEqual(retained['glyf']['A'].yMax, 730)
            self.assertEqual(retained['hhea'].ascent, 920)
        # Alias and collection-selection header probes plus the existing writer
        # stream; the stock-slot guard adds no font-table or header read.
        self.assertEqual(reads, ['rb', 'rb', 'rb'])

    def test_generation_failure_does_not_replace_any_existing_alias(self):
        first = self.target('SysSans-Hans-Regular.ttf'); font_file(first)
        second = self.target('SysSans-Z-Broken.ttf'); second.write_bytes(b'brokenfont')
        guarded = self.target('SysFont-Regular.ttf'); font_file(guarded)
        self.real_collection_slot(guarded.name)
        self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': stock(),
                        '/system/fonts/SysSans-Z-Broken.ttf': stock(),
                        '/system/fonts/SysFont-Regular.ttf': {**stock(), 'format': 'TTC', 'faceIndex': 1}})
        original = first.read_bytes()
        guarded_original = guarded.read_bytes()
        with self.assertRaises(Exception):
            batch.build(self.module, self.stage)
        self.assertEqual(first.read_bytes(), original)
        self.assertEqual(guarded.read_bytes(), guarded_original,
                         'stock-preserving alias removal waits for every generated result')
        self.assertFalse(list(self.stage.glob('.coloros-metrics-*')))
        self.assertFalse((self.stage / '.luoshu-metrics-report.json').exists())

    def test_report_and_stale_report_temp_cannot_mutate_live_inodes(self):
        font_file(self.target())
        self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': stock()})
        live = self.module / '.luoshu-payload'; live.mkdir()
        sentinel = live / '.luoshu-metrics-report.json'
        sentinel.write_bytes(b'live-record-must-stay-unchanged')
        report = self.stage / '.luoshu-metrics-report.json'
        for link in ('symlink', 'hardlink', 'stale-temp-symlink', 'stale-temp-hardlink'):
            with self.subTest(link=link):
                report.unlink(missing_ok=True)
                leaf = report.with_name(report.name + f'.tmp.{os.getpid()}') if link.startswith('stale-temp') else report
                leaf.unlink(missing_ok=True)
                if link.endswith('symlink'):
                    leaf.symlink_to(sentinel)
                else:
                    os.link(sentinel, leaf)
                batch.build(self.module, self.stage)
                self.assertEqual(sentinel.read_bytes(), b'live-record-must-stay-unchanged')
                self.assertFalse(report.is_symlink())
                self.assertNotEqual(report.stat().st_ino, sentinel.stat().st_ino)
                self.assertEqual(len(self.report()), 1)
                leaf.unlink(missing_ok=True)

    def test_rejects_live_and_module_roots(self):
        for target in (self.module, self.module / '.luoshu-payload',
                       self.module / '.luoshu-payload/system'):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, '本次启动'):
                batch.build(self.module, target)

    def test_shell_uses_one_python_process_and_passes_real_module(self):
        common = self.module / 'common'
        (common / 'python/bin').mkdir(parents=True)
        (self.module / 'module.prop').touch()
        for name in ('coloros_metrics_batch.py', 'font_inventory.py', 'font_inventory_scan.py',
                     'hyperos_metrics_batch.py', 'font_metrics_normalize.py'):
            (common / name).symlink_to(ROOT / 'common' / name)
        launcher = common / 'python/bin/luoshu-python'
        launcher.write_text('#!/bin/sh\necho called >> "$LUOSHU_TEST_CALLS"\n'
                            'unset PYTHONHOME LD_LIBRARY_PATH\n'
                            'PYTHONPATH="$LUOSHU_TEST_PATH" exec "$LUOSHU_TEST_PYTHON" "$@"\n')
        launcher.chmod(0o755)
        font_file(self.target())
        self.inventory({'/system/fonts/SysSans-Hans-Regular.ttf': stock()})
        calls = self.root / 'calls'
        result = subprocess.run(['sh', str(ROOT / 'common/coloros_stage_complete.sh'), str(self.stage)],
            env={**os.environ, 'LUOSHU_REAL_MODDIR': str(self.module),
                 'LUOSHU_TEST_PATH': os.pathsep.join(sys.path),
                 'LUOSHU_TEST_PYTHON': sys.executable, 'LUOSHU_TEST_CALLS': str(calls)},
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls.read_text().splitlines(), ['called'])
        self.assertEqual(json.loads(result.stdout)['mapped'], 1)

    def test_both_legacy_entrypoints_propagate_metric_failures(self):
        helper = self.module / 'common/coloros_stage_complete.sh'
        helper.parent.mkdir(parents=True)
        helper.write_text('printf "called\\n" >> "$TEST_CALLS"\nexit 7\n')
        marker = self.root / 'calls'
        for filename, function in (('font_switch_safe.sh', 'stage_coloros_complete'),
                                   ('mix_router.sh', 'complete_coloros_stage')):
            source = (ROOT / 'common/legacy_v14_4' / filename).read_text()
            start = source.index(function + '() {')
            code = source[start:source.index('\n}', start) + 2]
            getprop = '\ngetprop() { [ "$1" != ro.build.version.oplusrom ] || echo 16; }\n'
            result = subprocess.run(['sh', '-c', '. "$1"\n' + code + getprop + function,
                                     'sh', str(ROOT / 'common/legacy_v14_4/mix_phase_timing.sh')],
                env={**os.environ, 'IS_COLOROS': 'true', 'MODDIR': str(self.module),
                     'REALMOD': str(self.module), 'STAGE_PAYLOAD': str(self.stage),
                     'MIX_STAGE': str(self.stage), 'LOG_FILE': str(self.root / 'log'),
                     'TEST_CALLS': str(marker)})
            self.assertNotEqual(result.returncode, 0, filename)
        self.assertEqual(marker.read_text().splitlines(), ['called', 'called'])

    def test_coloros_postpass_leaves_hyperos_on_its_working_path(self):
        source = (ROOT / 'common/legacy_v14_4/mix_router.sh').read_text()
        start = source.index('complete_coloros_stage() {')
        code = source[start:source.index('\n}', start) + 2]
        # A HyperOS device may also expose OEM markers. Never run a second
        # ColorOS pass over the already aligned clock/UI payload.
        result = subprocess.run(['sh', '-c', code + '\ngetprop() { echo marker; }\ncomplete_coloros_stage'],
            env={**os.environ, 'REALMOD': str(self.module), 'MIX_STAGE': str(self.stage)})
        self.assertEqual(result.returncode, 0)


class ColorOSRoutingTest(unittest.TestCase):
    """Cmap behavior in real staged mixed fonts, not OEM phone measurements."""
    HAN, EXTRA_HAN, UVS_HAN, PUNCT = 0x4E2D, 0x20000, 0x56FD, 0x3001
    MAIN = '/system/fonts/SysSans-Hans-Regular.ttf'
    GOOGLE = '/product/fonts/GoogleSansText-Regular.ttf'
    POINTS = (65, 49, 0xFF11, HAN, EXTRA_HAN, UVS_HAN, PUNCT)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.stage = self.module / '.luoshu-payload-next'
        self.fonts = self.stage / 'system/fonts'
        self.fonts.mkdir(parents=True)
        (self.module / 'config').mkdir()
        self.slots = {}
        env = {'LUOSHU_BUILD_KEY': 'coloros-routing'}
        for partition in ('system', 'product'):
            stock_root = self.root / 'stock' / partition
            stock_root.mkdir(parents=True)
            env[f'LUOSHU_{partition.upper()}_FONTS_ROOT'] = str(stock_root)
        self.env = patch.dict(os.environ, env)
        self.env.start(); self.addCleanup(self.env.stop)

    def stock(self, logical, points, families=('sans-serif',)):
        part, name = logical.split('/')[1], Path(logical).name
        path = self.root / 'stock' / part / name
        font_file(path, points=points)
        fmt, metrics = _read_metrics(path)
        self.slots[logical] = {'path': logical, 'families': list(families),
                               'format': fmt, 'metrics': metrics, 'source': 'xml'}
        return path

    def pair(self, *, cff=False, variable=False, uvs=False):
        font_file(self.fonts / '.luoshu-font-store/regular.font', points=self.POINTS,
                  cff=cff, variable=variable, uvs=uvs)
        font_file(self.fonts / 'SysSans-Hans-Regular.ttf', points=self.POINTS,
                  cff=cff, variable=variable, uvs=uvs)
        self.stock(self.MAIN, self.POINTS)
        self.stock(self.GOOGLE, (65, 49), ('google-sans-text',))

    def build(self, main=MAIN, build='coloros-routing'):
        (self.module / 'config/device_font_inventory.json').write_text(json.dumps({
            'schema': 'device-font-inventory-v1', 'inventoryRevision': 1,
            'state': 'ready', 'buildKey': build, 'mainSlotPath': main, 'slots': self.slots}))
        result = batch.build(self.module, self.stage)
        self.reports = {row['slot']: row for row in json.loads(
            (self.stage / '.luoshu-metrics-report.json').read_text())['slots']}
        return result

    def test_existing_latin_and_completed_google_alias_route_only_proven_cjk(self):
        self.pair()
        name = 'SysSans-En-Regular.ttf'
        font_file(self.fonts / name, points=self.POINTS)
        self.stock('/system/fonts/' + name, (65, 49))
        donor = self.fonts / '.luoshu-font-store/regular.font'
        before = donor.read_bytes()
        result = self.build()
        self.assertEqual(result['mapped'], 3)
        for path in (self.fonts / name, self.stage / 'product/fonts/GoogleSansText-Regular.ttf'):
            with TTFont(path) as font:
                self.assertNotIn(self.HAN, font.getBestCmap())
                self.assertNotIn(self.EXTRA_HAN, font.getBestCmap())
                for cp in (65, 49, 0xFF11):
                    self.assertIn(cp, font.getBestCmap())
        with TTFont(self.fonts / 'SysSans-Hans-Regular.ttf') as fallback:
            self.assertIn(self.HAN, fallback.getBestCmap())
            self.assertIn(self.EXTRA_HAN, fallback.getBestCmap())
        self.assertEqual(donor.read_bytes(), before)
        self.assertEqual(self.reports[self.GOOGLE]['cjkRoutingReason'], 'stock-latin-primary')
        self.assertEqual(self.reports[self.GOOGLE]['slotSource'], 'stock-inventory')

    def test_empty_final_fallback_mapping_keeps_visible_primary_han(self):
        self.pair()
        main = self.fonts / Path(self.MAIN).name
        with TTFont(main) as font:
            name = font.getBestCmap()[self.HAN]
            font['glyf'][name] = TTGlyphPen(None).glyph()
            font.save(main)
        self.build()
        google = self.stage / 'product/fonts' / Path(self.GOOGLE).name
        with TTFont(google) as font:
            cmap = font.getBestCmap()
            self.assertIn(self.HAN, cmap, 'an empty staged fallback cannot authorize primary pruning')
            self.assertGreater(font['glyf'][cmap[self.HAN]].numberOfContours, 0)
            self.assertNotIn(self.EXTRA_HAN, cmap, 'positive final fallback geometry still permits pruning')
        with TTFont(main) as font:
            self.assertEqual(font['glyf'][font.getBestCmap()[self.HAN]].numberOfContours, 0)
        report = self.reports[self.GOOGLE]
        self.assertEqual(report['cjkUnprovenMappingsPreserved'], 1)
        self.assertEqual(report['cjkRoutingReason'], 'stock-latin-primary-unproven-glyphs-preserved')

    def test_final_fallback_failure_keeps_every_alias_and_removal_pending(self):
        self.pair()
        main = self.fonts / Path(self.MAIN).name
        donor = self.fonts / '.luoshu-font-store/regular.font'
        original_main, original_donor = main.read_bytes(), donor.read_bytes()
        with patch.object(batch, 'write_metrics', side_effect=ValueError('final fallback generation')):
            with self.assertRaisesRegex(ValueError, 'final fallback generation'):
                self.build()
        self.assertEqual(main.read_bytes(), original_main)
        self.assertEqual(donor.read_bytes(), original_donor)
        self.assertFalse((self.stage / 'product/fonts' / Path(self.GOOGLE).name).exists())
        self.assertFalse((self.stage / '.luoshu-metrics-report.json').exists())
        self.assertFalse(list(self.stage.glob('.coloros-metrics-*')))

    def test_cff_and_variable_retained_outlines_and_variants_survive(self):
        for cff, variable in ((True, False), (False, True)):
            with self.subTest(cff=cff, variable=variable):
                self.pair(cff=cff, variable=variable, uvs=True)
                self.build()
                donor = self.fonts / '.luoshu-font-store/regular.font'
                with TTFont(donor, lazy=True) as source, \
                        TTFont(self.stage / 'product/fonts/GoogleSansText-Regular.ttf') as primary, \
                        TTFont(self.fonts / 'SysSans-Hans-Regular.ttf', lazy=True) as fallback:
                    self.assertNotIn(self.HAN, primary.getBestCmap())
                    self.assertIn(self.UVS_HAN, primary.getBestCmap(), 'unproven variants keep their base')
                    variants = next(table for table in primary['cmap'].tables if table.format == 14)
                    self.assertEqual(variants.uvsDict[0xFE00], [(self.UVS_HAN, None)])
                    from fontTools.pens.recordingPen import RecordingPen
                    for cp in (65, 49, 0xFF11, self.UVS_HAN):
                        actual, expected = RecordingPen(), RecordingPen()
                        primary.getGlyphSet()[primary.getBestCmap()[cp]].draw(actual)
                        source.getGlyphSet()[source.getBestCmap()[cp]].draw(expected)
                        self.assertEqual(actual.value, expected.value)
                    for tag in ('glyf', 'loca', 'CFF ', 'gvar'):
                        if tag in source:
                            self.assertEqual(fallback.reader[tag], source.reader[tag], tag)

    def test_missing_physical_fallback_keeps_google_han(self):
        self.pair()
        (self.fonts / 'SysSans-Hans-Regular.ttf').unlink()
        (self.root / 'stock/system/SysSans-Hans-Regular.ttf').unlink()
        self.build()
        with TTFont(self.stage / 'product/fonts/GoogleSansText-Regular.ttf') as primary:
            self.assertIn(self.HAN, primary.getBestCmap())
        self.assertEqual(self.reports[self.GOOGLE]['cjkRoutingReason'], 'no-staged-cjk-fallback')

    def test_latin_only_generated_fallback_cannot_remove_google_han(self):
        self.pair()
        font_file(self.fonts / 'SysSans-Hans-Regular.ttf', points=(65, 49))
        self.build()
        with TTFont(self.stage / 'product/fonts/GoogleSansText-Regular.ttf') as primary:
            self.assertIn(self.HAN, primary.getBestCmap())
        self.assertEqual(self.reports[self.GOOGLE]['removedCjkMappings'], 0)

    def test_partial_fallback_and_stock_punctuation_are_preserved(self):
        self.pair()
        font_file(self.fonts / 'SysSans-Hans-Regular.ttf', points=(65, 49, self.HAN, self.PUNCT))
        self.stock(self.GOOGLE, (65, 49, self.PUNCT), ('google-sans-text',))
        self.build()
        with TTFont(self.stage / 'product/fonts/GoogleSansText-Regular.ttf') as primary:
            self.assertNotIn(self.HAN, primary.getBestCmap())
            self.assertIn(self.EXTRA_HAN, primary.getBestCmap(), 'fallback has not proved this glyph')
            self.assertIn(self.PUNCT, primary.getBestCmap(), 'keep stock primary punctuation')
        self.assertEqual(self.reports[self.GOOGLE]['removedCjkMappings'], 1)

    def test_old_coverage_and_unrelated_display_family_do_not_prove_fallback(self):
        self.pair()
        for slot in self.slots.values():
            slot['metrics'].pop('coverage')
        self.build()
        with TTFont(self.stage / 'product/fonts/GoogleSansText-Regular.ttf') as primary:
            self.assertIn(self.HAN, primary.getBestCmap())
        self.assertEqual(self.reports[self.GOOGLE]['cjkRoutingReason'], 'stock-coverage-refresh-pending')
        self.pair()
        self.build(main='/system/fonts/PrivateDisplay.ttf')
        with TTFont(self.stage / 'product/fonts/GoogleSansText-Regular.ttf') as primary:
            self.assertIn(self.HAN, primary.getBestCmap())
        self.assertEqual(self.reports[self.GOOGLE]['cjkRoutingReason'], 'no-staged-cjk-fallback')

    def test_many_latin_contracts_compact_each_shared_donor_once(self):
        self.pair()
        for index in range(10):
            logical = f'/product/fonts/GoogleSansText-Extra{index}.ttf'
            self.stock(logical, (65, 49), ('google-sans-text',))
            self.slots[logical]['metrics']['hhea']['ascent'] += index + 1
        with patch.object(batch, 'compact_routed_source', wraps=batch.compact_routed_source) as compact:
            result = self.build()
        self.assertEqual(result['mapped'], 12)
        self.assertEqual(compact.call_count, 1)
        self.assertFalse(list(self.stage.glob('.coloros-metrics-*')))

    def test_rebuilt_a_b_a_stages_and_copied_payload_keep_selected_glyphs(self):
        # This models independent precommit/reboot payload reconstruction; it
        # cannot prove Android process refresh or the phone's mounted view.
        for index, top in enumerate((730, 940, 730)):
            self.stage = self.module / f'.luoshu-payload-next-{index}'
            self.fonts = self.stage / 'system/fonts'; self.fonts.mkdir(parents=True)
            self.pair()
            for name in ('SysSans-Hans-Regular.ttf', '.luoshu-font-store/regular.font'):
                font_file(self.fonts / name, top=top, points=self.POINTS)
            self.build()
            copied = self.root / f'restored-boot-payload-{index}'
            shutil.copytree(self.stage, copied)
            with TTFont(copied / 'system/fonts/SysSans-Hans-Regular.ttf') as cjk, \
                    TTFont(copied / 'product/fonts/GoogleSansText-Regular.ttf') as latin:
                self.assertIn(self.HAN, cjk.getBestCmap())
                self.assertNotIn(self.HAN, latin.getBestCmap())
                for cp in (65, 49, 0xFF11):
                    self.assertEqual(latin['glyf'][latin.getBestCmap()[cp]].yMax, top)
                self.assertEqual(cjk['glyf'][cjk.getBestCmap()[self.HAN]].yMax, top)
                self.assertEqual(latin['hhea'].ascent, self.slots[self.GOOGLE]['metrics']['hhea']['ascent'])


if __name__ == '__main__':
    unittest.main()
