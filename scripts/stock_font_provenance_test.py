#!/usr/bin/env python3
"""Synthetic mountinfo tests; no device mounts or private font bytes."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
import stock_font_provenance as proof
import stock_inventory_scan as scanner

class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.info = self.root / 'mountinfo'
        self.lower = self.root / 'lower'
        self.lower.mkdir()
        self.font = self.lower / 'Original.ttf'
        self.font.write_bytes(b'original-font')
        self.patch = patch.dict(os.environ, {'LUOSHU_MOUNTINFO': str(self.info)})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.base = ('1 0 0:1 / / rw - tmpfs tmpfs rw\n'
                     '2 1 253:0 / /system ro - erofs /dev/block/dm-0 ro\n')
        self.good = f'3 1 253:0 /fonts {self.lower} rw - erofs /dev/block/dm-0 ro\n'
    def write(self, extra=''):
        self.info.write_text(self.base + extra)
    def test_real_partition_lower_accepted(self):
        self.write(self.good)
        self.assertTrue(proof.verify_stock_path('/system/fonts/Original.ttf', self.font)['verified'])
    def test_scanner_accepts_proven_lower(self):
        state = self.root / 'state'
        lower = state / 'lower' / 'system-fonts'
        lower.mkdir(parents=True)
        self.write(self.good.replace(str(self.lower), str(lower)))
        with patch.dict(os.environ, {'LUOSHU_SELF_MOUNT_STATE_ROOT': str(state)}):
            self.assertEqual(scanner._safe_pick_actual_root(Path('/system/fonts'), None, True), lower)
    def test_scanner_does_not_accept_naked_lower(self):
        state = self.root / 'state'
        lower = state / 'lower' / 'system-fonts'
        lower.mkdir(parents=True)
        self.write()
        with patch.dict(os.environ, {'LUOSHU_SELF_MOUNT_STATE_ROOT': str(state)}), \
                patch.object(scanner.inventory, 'MIRROR_PREFIXES', ()), \
                patch.object(scanner, '_installer_namespace_is_stock', return_value=False), \
                patch.object(scanner, '_bind_parent_stock_snapshot', return_value=None):
            # /system/fonts is absent on the host: absence is returned, never the naked lower.
            self.assertNotEqual(scanner._safe_pick_actual_root(Path('/system/fonts'), None, True), lower)
    def test_relative_rom_alias_and_chain_accepted(self):
        self.write(self.good)
        alias = self.lower / 'Alias.ttf'
        alias.symlink_to('Original.ttf')
        second = self.lower / 'Second.ttf'
        second.symlink_to('Alias.ttf')
        self.assertTrue(proof.verify_stock_path('/system/fonts/Alias.ttf', alias)['verified'])
        self.assertTrue(proof.verify_stock_path('/system/fonts/Second.ttf', second)['verified'])
        identity = proof.stock_identity('/system/fonts/Alias.ttf', self.font, 0, 'build', provenance_path=alias)
        self.assertTrue(identity['provenance']['verified'])
        other = self.lower / 'Other.ttf'
        other.write_bytes(b'other')
        self.assertFalse(proof.stock_identity('/system/fonts/Alias.ttf', other, 0, 'build', provenance_path=alias)['provenance']['verified'])
    def test_rom_alias_cannot_escape_to_data(self):
        self.write(self.good)
        outside = self.root / 'replacement.ttf'
        outside.write_bytes(b'replacement')
        alias = self.lower / 'Alias.ttf'
        alias.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'alias-target-unproven'):
            proof.verify_stock_path('/system/fonts/Alias.ttf', alias)
    def test_rom_alias_cannot_pass_through_data_symlink(self):
        self.write(self.good)
        outside = self.root / 'return.ttf'
        outside.symlink_to(self.font)
        alias = self.lower / 'Alias.ttf'
        alias.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'alias-link-unproven'):
            proof.verify_stock_path('/system/fonts/Alias.ttf', alias)
    def test_lower_under_whole_partition_overlay_is_proven(self):
        for fs, source in [('tmpfs', 'tmpfs'), ('overlay', 'overlay')]:
            self.write(f'8 2 0:8 / /system rw - {fs} {source} rw\n' + self.good)
            result = proof.verify_stock_path('/system/fonts/Original.ttf', self.font)
            self.assertEqual(result['originMountId'], '2')
    def test_overlay_does_not_legitimize_data_lower(self):
        self.write('8 2 0:8 / /system rw - overlay overlay rw\n'
                   + f'9 1 253:9 /fonts {self.lower} ro - ext4 /dev/block/dm-9 rw\n')
        with self.assertRaisesRegex(ValueError, 'lineage-mismatch'):
            proof.verify_stock_path('/system/fonts/Original.ttf', self.font)
    def test_overlay_does_not_legitimize_wrong_rom_location(self):
        self.write('8 2 0:8 / /system rw - tmpfs tmpfs rw\n'
                   + self.good.replace('/fonts ', '/unrelated '))
        with self.assertRaisesRegex(ValueError, 'lineage-mismatch'):
            proof.verify_stock_path('/system/fonts/Original.ttf', self.font)
    def test_naked_lower_rejected(self):
        self.write()
        with self.assertRaisesRegex(ValueError, 'lineage-mismatch'):
            proof.verify_stock_path('/system/fonts/Original.ttf', self.font)
    def test_data_origin_lower_rejected(self):
        self.write(f'3 1 253:9 /adb/payload {self.lower} ro - ext4 /dev/block/dm-9 rw\n')
        with self.assertRaises(ValueError):
            proof.verify_stock_path('/system/fonts/Original.ttf', self.font)
    def test_wrong_subtree_same_device_rejected(self):
        self.write(self.good.replace('/fonts ', '/other '))
        with self.assertRaises(ValueError):
            proof.verify_stock_path('/system/fonts/Original.ttf', self.font)
    def test_foreign_child_mount_rejected(self):
        self.write(self.good + f'4 3 253:9 /replacement {self.font} ro - ext4 /dev/block/dm-9 rw\n')
        with self.assertRaises(ValueError):
            proof.verify_stock_path('/system/fonts/Original.ttf', self.font)
    def test_hash_changes_without_metric_assumptions(self):
        self.write(self.good)
        a = proof.stock_identity('/system/fonts/Original.ttf', self.font, 2, 'build')
        self.font.write_bytes(b'replacement-font')
        b = proof.stock_identity('/system/fonts/Original.ttf', self.font, 2, 'build')
        self.assertNotEqual(a['sha256'], b['sha256'])
        self.assertEqual(a['faceIndex'], 2)
        self.assertEqual(a['buildKey'], 'build')
    def test_unproven_identity_is_never_attested(self):
        self.write()
        self.assertFalse(proof.stock_identity('/system/fonts/Original.ttf', self.font, 0, 'build')['provenance']['verified'])
    def test_proof_rechecks_current_mount_generation(self):
        self.write(self.good)
        proof.verify_stock_path('/system/fonts/Original.ttf', self.font)
        self.write()
        with self.assertRaises(ValueError):
            proof.verify_stock_path('/system/fonts/Original.ttf', self.font)
    def test_partition_itself_from_userdata_rejected(self):
        self.base = self.base.replace('253:0 / /system ro - erofs /dev/block/dm-0 ro', '253:9 /adb/payload /system ro - ext4 /dev/block/dm-9 rw')
        self.write(self.good)
        with self.assertRaisesRegex(ValueError, 'partition-not-readonly-block'):
            proof.verify_stock_path('/system/fonts/Original.ttf', self.font)

if __name__ == '__main__':
    unittest.main()
