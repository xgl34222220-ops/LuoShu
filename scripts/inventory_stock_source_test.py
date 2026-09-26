#!/usr/bin/env python3
"""Original font identity and namespace tests for selective glyph replacement."""
from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTCollection, TTFont
import font_inventory as inventory
import stock_inventory_scan as wrapper
from inventory_stock_source import StockSourceError, StockSourceResolver, codepoint_digest, file_digest


def make_font(path: Path, points=(65, 66, 0x391, 0x4E2D), weight=400, *, cff=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    cmap = {point: f'u{point:04X}' for point in points}
    order = ['.notdef', *cmap.values()]
    builder = FontBuilder(1000, isTTF=not cff)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(cmap)
    glyphs = {}
    for name in order:
        pen = T2CharStringPen(600, None) if cff else TTGlyphPen(None)
        if name != '.notdef':
            pen.moveTo((0, 0)); pen.lineTo((500, 0))
            pen.lineTo((500, 700)); pen.lineTo((0, 700)); pen.closePath()
        glyphs[name] = pen.getCharString() if cff else pen.glyph()
    if cff:
        builder.setupCFF('OriginalFixture', {}, glyphs, {})
    else:
        builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 0) for name in order})
    builder.setupHorizontalHeader(ascent=1000, descent=-250)
    builder.setupOS2(usWeightClass=weight, sTypoAscender=1000, sTypoDescender=-250,
                     usWinAscent=1000, usWinDescent=250)
    builder.setupNameTable({'familyName': 'Original fixture', 'styleName': 'Regular'})
    builder.setupPost(); builder.setupMaxp(); builder.save(path)


class StockSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.state = self.root / 'state'
        self.mirror = self.root / 'mirror'
        self.actual = self.root / 'original/system/fonts'
        self.stock = self.actual / 'Unknown.ttf'
        make_font(self.stock)
        self.logical = '/system/fonts/Unknown.ttf'
        self.data = {'sourceRoots': [{'partition': 'system', 'logical': '/system/fonts',
                                    'actual': str(self.actual)}], 'slots': {}}
        self.set_slot(self.logical, self.stock)

    def set_slot(self, logical, path, face=0, *, proof=True):
        fmt, metrics = inventory._read_metrics(path, face)
        entry = {'format': fmt, 'faceIndex': face, 'metrics': metrics}
        if proof:
            entry['stockSource'] = {'sha256': file_digest(path),
                                   'cmapSha256': metrics['stockCmapSha256']}
        else:
            metrics.pop('stockCmapSha256', None)
            metrics.pop('stockCodepointSha256', None)
        self.data['slots'][logical] = entry
        return entry

    def resolver(self):
        return StockSourceResolver(self.module, self.data, state_root=self.state,
                                   mirrors=[self.mirror])

    def lower_copy(self, partition='system', name='Unknown.ttf', source=None):
        target = self.state / 'lower' / f'{partition}-fonts' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source or self.stock, target)
        return target

    def test_current_original_requires_whole_file_scan_hash(self):
        result = self.resolver().resolve(self.logical)
        self.assertEqual(result.path, self.stock)
        self.assertEqual(result.verified_by, 'scan-sha256')
        self.assertEqual(result.codepoints, frozenset({65, 66, 0x391, 0x4E2D}))
        self.assertEqual(codepoint_digest(result.codepoints),
                         self.data['slots'][self.logical]['metrics']['stockCodepointSha256'])
        self.set_slot(self.logical, self.stock, proof=False)
        with self.assertRaises(StockSourceError):
            self.resolver().resolve(self.logical)

    def test_legacy_inventory_uses_stock_lower_without_rescan(self):
        lower = self.lower_copy()
        self.set_slot(self.logical, self.stock, proof=False)
        make_font(self.stock, points=(65, 0x4E00))
        result = self.resolver().resolve(self.logical)
        self.assertEqual(result.path, lower)
        self.assertEqual(result.verified_by, 'stock-lower')

    def test_legacy_metric_mismatch_is_rejected(self):
        lower = self.lower_copy()
        self.set_slot(self.logical, self.stock, proof=False)
        make_font(lower, weight=700)
        with self.assertRaisesRegex(StockSourceError, 'weightClass'):
            self.resolver().resolve(self.logical)

    def test_same_metrics_cmap_but_changed_outlines_fail_full_hash(self):
        old = copy.deepcopy(self.data['slots'][self.logical]['metrics'])
        with TTFont(self.stock, recalcTimestamp=False) as font:
            coordinates = font['glyf']['u0041'].coordinates
            coordinates[1] = (450, 0)
            font.save(self.stock)
        self.assertEqual(old, inventory._read_metrics(self.stock)[1])
        with self.assertRaisesRegex(StockSourceError, 'SHA256'):
            self.resolver().resolve(self.logical)

    def test_same_count_different_codepoints_fail_cmap_proof(self):
        lower = self.lower_copy()
        self.data['slots'][self.logical].pop('stockSource')
        make_font(lower, points=(67, 68, 0x392, 0x4E01))
        with self.assertRaises(StockSourceError):
            self.resolver().resolve(self.logical)

    def test_absolute_alias_remaps_into_other_stock_partition(self):
        self.lower_copy()
        target = self.lower_copy('product', 'Actual.ttf')
        alias = self.state / 'lower/system-fonts/Alias.ttf'
        alias.symlink_to('/system/product/fonts/Actual.ttf')
        logical = '/system/fonts/Alias.ttf'
        self.set_slot(logical, self.stock, proof=False)
        result = self.resolver().resolve(logical)
        self.assertEqual(result.path, target)
        self.assertEqual(result.verified_by, 'stock-lower')

    def test_alias_into_live_partition_requires_full_hash(self):
        self.lower_copy()
        alias = self.state / 'lower/system-fonts/Alias.ttf'
        alias.symlink_to('/product/fonts/Actual.ttf')
        actual = self.root / 'original/product/fonts'
        make_font(actual / 'Actual.ttf')
        self.data['sourceRoots'].append({'partition': 'product', 'logical': '/product/fonts',
                                        'actual': str(actual)})
        logical = '/system/fonts/Alias.ttf'
        self.set_slot(logical, actual / 'Actual.ttf', proof=False)
        with self.assertRaises(StockSourceError):
            self.resolver().resolve(logical)
        self.set_slot(logical, actual / 'Actual.ttf')
        result = self.resolver().resolve(logical)
        self.assertEqual(result.verified_by, 'scan-sha256')

    def test_mutable_namespace_and_symlinked_lower_are_rejected(self):
        (self.state / 'lower').mkdir(parents=True)
        (self.state / 'lower/system-fonts').symlink_to(self.actual)
        self.set_slot(self.logical, self.stock, proof=False)
        with self.assertRaises(StockSourceError):
            self.resolver().resolve(self.logical)
        (self.state / 'lower/system-fonts').unlink()
        self.lower_copy()
        alias = self.state / 'lower/system-fonts/Alias.ttf'
        alias.symlink_to('/data/system/fonts/theme.ttf')
        self.set_slot('/system/fonts/Alias.ttf', self.stock)
        with self.assertRaises(StockSourceError):
            self.resolver().resolve('/system/fonts/Alias.ttf')

    def test_unknown_nested_directory_uses_exact_mount_key(self):
        relative = 'assets/typefaces'
        key = 'nebula-nested-' + hashlib.sha256(f'nebula/{relative}'.encode()).hexdigest()[:16]
        target = self.state / 'lower' / key / 'blob.bin'
        make_font(target)
        logical = '/nebula/assets/typefaces/blob.bin'
        record = {'partition': 'nebula', 'logical': '/nebula/assets/typefaces',
                  'relative': relative, 'mountKey': key}
        self.data['discoveredFontRoots'] = [record]
        self.set_slot(logical, target, proof=False)
        self.assertEqual(self.resolver().resolve(logical).path, target)
        record['mountKey'] = 'system-fonts'
        with self.assertRaises(StockSourceError):
            self.resolver().resolve(logical)

    def test_mirror_is_trusted_for_legacy_inventory(self):
        target = self.mirror / 'system/fonts/Unknown.ttf'
        target.parent.mkdir(parents=True)
        shutil.copy2(self.stock, target)
        self.set_slot(self.logical, self.stock, proof=False)
        result = self.resolver().resolve(self.logical)
        self.assertEqual(result.path, target)
        self.assertEqual(result.verified_by, 'stock-mirror')

    def test_mirror_partition_alias_stays_inside_stock_namespace(self):
        target = self.mirror / 'system/product/fonts/Unknown.ttf'
        target.parent.mkdir(parents=True)
        shutil.copy2(self.stock, target)
        (self.mirror / 'product').symlink_to('system/product')
        self.set_slot('/product/fonts/Unknown.ttf', self.stock, proof=False)
        self.assertEqual(self.resolver().resolve('/product/fonts/Unknown.ttf').path, target)
        (self.mirror / 'product').unlink()
        (self.mirror / 'product').symlink_to(self.actual.parent)
        with self.assertRaises(StockSourceError):
            self.resolver().resolve('/product/fonts/Unknown.ttf')

    def test_cross_partition_alias_can_skip_bad_lower_for_valid_mirror(self):
        self.lower_copy()
        target = self.lower_copy('product', 'Actual.ttf')
        make_font(target, weight=700)
        alias = self.state / 'lower/system-fonts/Alias.ttf'
        alias.symlink_to('/product/fonts/Actual.ttf')
        mirror = self.mirror / 'product/fonts/Actual.ttf'
        mirror.parent.mkdir(parents=True)
        shutil.copy2(self.stock, mirror)
        self.set_slot('/system/fonts/Alias.ttf', self.stock, proof=False)
        self.assertEqual(self.resolver().resolve('/system/fonts/Alias.ttf').path, mirror)

    def test_expired_install_snapshot_is_recaptured_for_engine_lifetime(self):
        original = self.root / 'immutable.ttf'
        shutil.copy2(self.stock, original)
        self.data['sourceRoots'][0]['actual'] = str(self.root / 'expired-installer-snapshot/fonts')
        live = self.root / 'live/system'
        make_font(live / 'fonts/Unknown.ttf', points=(65, 0x4E99))
        mountinfo = self.root / 'mountinfo'
        mountinfo.write_text(f'11 1 0:2 / {live}/fonts/Unknown.ttf rw - ext4 /dev/block/dm-9 rw\n')
        snapshot_root = self.root / 'engine-snapshots'
        binds = []

        def fake_mount(*args):
            if args[0] == '--bind':
                binds.append(args)
                destination = Path(args[2]) / 'fonts/Unknown.ttf'
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, destination)
            return True

        resolver = self.resolver()
        self.addCleanup(resolver.close)
        with patch.dict(os.environ, {'LUOSHU_MOUNTINFO': str(mountinfo),
                                      'LUOSHU_INSTALL_STOCK_SNAPSHOT_ROOT': str(snapshot_root)}), \
             patch.object(wrapper, '_partition_logical_candidates',
                          side_effect=lambda partition, root: [live] if partition == 'system' else []), \
             patch.object(wrapper, '_private_snapshot_namespace', return_value=True), \
             patch.object(wrapper, '_run_mount', side_effect=fake_mount), \
             patch.object(wrapper, '_run_umount') as umount:
            result = resolver.resolve(self.logical)
            self.assertEqual(result.verified_by, 'stock-snapshot')
            self.assertEqual(result.digest, file_digest(original))
            self.assertEqual(len(binds), 1)
            self.assertEqual(binds[0][1], str(live))
            self.assertTrue(result.path.is_file())
            resolver.close()
            self.assertEqual(umount.call_count, 1)
            self.assertFalse(result.path.exists())

    def test_partition_snapshot_distinguishes_readonly_block_from_overlay(self):
        mountinfo = self.root / 'mountinfo'
        child = '/product/fonts'
        with patch.dict(os.environ, {'LUOSHU_MOUNTINFO': str(mountinfo)}):
            mountinfo.write_text('10 1 253:2 / /product ro - erofs /dev/block/dm-2 ro\n'
                                 f'11 10 0:2 / {child} rw - overlay KSU rw\n')
            self.assertEqual(wrapper._child_mount_targets(Path('/product')), [child])
            for entry in ['10 1 0:2 / /product ro - overlay KSU ro',
                          '10 1 253:2 /data/adb/modules/foo /product ro - ext4 /dev/block/dm-9 ro',
                          '10 1 253:2 / /product rw - ext4 /dev/block/dm-2 rw']:
                mountinfo.write_text(entry + f'\n11 10 0:2 / {child} rw - overlay KSU rw\n')
                self.assertEqual(wrapper._child_mount_targets(Path('/product')), [])

    def test_snapshot_namespace_requires_private_propagation_before_mounts(self):
        with patch.object(wrapper, '_SNAPSHOT_NAMESPACE_READY', False), \
             patch.object(os, 'unshare') as unshare, \
             patch.object(wrapper, '_run_mount', return_value=True) as mount:
            self.assertTrue(wrapper._private_snapshot_namespace())
            self.assertTrue(wrapper._private_snapshot_namespace())
            unshare.assert_called_once_with(os.CLONE_NEWNS)
            mount.assert_called_once_with('--make-rprivate', '/')
        with patch.object(wrapper, '_SNAPSHOT_NAMESPACE_READY', False), \
             patch.object(os, 'unshare', side_effect=PermissionError('no namespace capability')), \
             patch.object(wrapper, '_run_mount') as mount:
            self.assertFalse(wrapper._private_snapshot_namespace())
            mount.assert_not_called()
        with patch.object(wrapper, '_SNAPSHOT_NAMESPACE_READY', False), \
             patch.object(os, 'unshare'), \
             patch.object(wrapper, '_run_mount', return_value=False):
            self.assertFalse(wrapper._private_snapshot_namespace())

    def test_collection_returns_physical_path_and_original_face_index(self):
        second = self.root / 'second.ttf'
        make_font(second, points=(90, 0x4E99), weight=700)
        collection = self.actual / 'Unknown.ttc'
        with TTFont(self.stock) as first, TTFont(second) as other:
            fonts = TTCollection(); fonts.fonts = [first, other]; fonts.save(collection)
        logical = '/system/fonts/Unknown.ttc'
        face = self.set_slot(logical, collection, face=1)
        self.data['slots'][logical]['faces'] = [copy.deepcopy(face)]
        result = self.resolver().resolve(logical, face)
        self.assertEqual(result.path, collection)
        self.assertEqual(result.face_index, 1)
        self.assertEqual(result.codepoints, frozenset({90, 0x4E99}))

    def test_cache_reuses_hardlink_profile_and_detects_mutation(self):
        alias = self.actual / 'Alias.ttf'
        os.link(self.stock, alias)
        self.set_slot('/system/fonts/Alias.ttf', alias)
        resolver = self.resolver()
        with patch.object(inventory, '_read_metrics_uncached', wraps=inventory._read_metrics_uncached) as reader:
            first = resolver.resolve(self.logical)
            resolver.resolve('/system/fonts/Alias.ttf')
        self.assertEqual(reader.call_count, 1)
        self.stock.write_bytes(self.stock.read_bytes() + b'changed')
        with self.assertRaises(StockSourceError):
            first.verify_unchanged()
        with self.assertRaises(StockSourceError):
            resolver.resolve(self.logical)

    def test_metrics_only_cff_variants_decode_charset_once_but_validate_every_header(self):
        first, second = self.actual / 'First.otf', self.actual / 'Second.otf'
        make_font(first, cff=True)
        with TTFont(first, lazy=True, recalcBBoxes=False, recalcTimestamp=False) as font:
            font['hhea'].ascent += 100
            font['OS/2'].sTypoAscender += 100
            font.save(second)
        first_path, second_path = '/system/fonts/First.otf', '/system/fonts/Second.otf'
        self.set_slot(first_path, first)
        self.set_slot(second_path, second)
        resolver = self.resolver()
        with patch.object(inventory, '_cmap_metrics', wraps=inventory._cmap_metrics) as cmap_reader, \
             patch.object(inventory, '_read_metrics_uncached', wraps=inventory._read_metrics_uncached) as metric_reader:
            first_result = resolver.resolve(first_path)
            second_result = resolver.resolve(second_path)
        self.assertEqual(cmap_reader.call_count, 1)
        self.assertEqual(metric_reader.call_count, 2)
        self.assertIs(first_result.codepoints, second_result.codepoints)
        self.assertNotEqual(first_result.digest, second_result.digest)
        self.data['slots'][second_path]['metrics']['hhea']['ascent'] -= 100
        with self.assertRaisesRegex(StockSourceError, 'hhea'):
            resolver.resolve(second_path)

    def test_scanner_captures_optional_proofs_for_every_face(self):
        root = inventory.FontRoot('system', Path('/system/fonts'), self.actual)
        slots = {}
        with inventory._scan_metrics_cache():
            inventory._add_verified_text_slots(slots, [root])
        slot = slots[self.logical]
        self.assertEqual(slot['stockSource']['sha256'], file_digest(self.stock))
        self.assertEqual(slot['faces'][0]['stockSource'], slot['stockSource'])
        self.assertEqual(slot['stockSource']['cmapSha256'], slot['metrics']['stockCmapSha256'])

    def test_discovered_mutable_partition_cannot_become_trusted(self):
        self.data['discoveredPartitions'] = ['data']
        target = self.lower_copy('data', 'Bad.ttf')
        self.set_slot('/data/fonts/Bad.ttf', target)
        with self.assertRaises(StockSourceError):
            self.resolver().resolve('/data/fonts/Bad.ttf')


if __name__ == '__main__':
    unittest.main()
