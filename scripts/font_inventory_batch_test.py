#!/usr/bin/env python3
"""Host regression for the non-mounting batch inventory contract."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('batch', ROOT / 'common/font_inventory_batch.py')
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.module = self.base / 'module'
        self.public = self.base / 'public'
        self.config = self.module / 'config'
        self.fonts = self.public / 'fonts'
        batch.ensure_storage(self.public, self.config)

    def tearDown(self):
        self.temp.cleanup()

    def font(self, name, magic=b'\x00\x01\x00\x00', size=8192):
        target = self.fonts / name
        target.write_bytes(magic + b'\0' * max(0, size - len(magic)))
        return target

    def action(self, name):
        return batch.execute(name, self.module, self.public)

    def test_family_and_weight_match_existing_shell_single_pass(self):
        names = ['Foo-Italic-Black.ttf', 'Foo-Black-Italic.ttf', 'Foo-Regular-Bold.ttf',
                 'Foo-Bold-Regular.ttf', 'Foo-DemiBold.ttf', 'Foo-REGULAR.ttf', 'Foo-400.ttf',
                 'Foo-VF.ttf', 'Foo-重.ttf', 'Foo-重体.ttf', 'Foo-ExtraLight.ttf',
                 'Foo-SemiBold.ttf', 'Foo-variable.ttf', 'Foo-_  .TTF', 'Nervar-Regular.ttf']
        script = '. "$1"; shift; for name do printf "%s|%s\\n" "$(detect_font_family "$name")" "$(detect_font_weight "$name")"; done'
        result = subprocess.check_output(['sh', '-c', script, 'test', str(ROOT / 'common/util_functions_core.sh'), *names], text=True)
        self.assertEqual(result.splitlines(), [batch.family_of(n) + '|' + batch.weight_of(n) for n in names])

    def test_grouping_variants_and_representative_preserve_order(self):
        self.font('Family-Bold.ttf', size=9000)
        self.font('Family-Regular.otf', magic=b'OTTO', size=10000)
        self.font('Family-Thin.ttf', size=8000)
        self.font('Other-VF.ttf')
        data = self.action('refresh')['data']
        self.assertEqual(['Family', 'Other-VF'], [f['id'] for f in data['fonts']])
        family = data['fonts'][0]
        self.assertEqual(['thin', 'regular', 'bold'], family['weights'])
        self.assertEqual('Family-Regular.otf', family['file'])
        self.assertEqual('static-family', family['familyType'])
        self.assertEqual(10000, family['bytes'])
        self.assertEqual('OTF', family['format'])
        self.assertEqual({'thin': 'Family-Thin.ttf', 'regular': 'Family-Regular.otf', 'bold': 'Family-Bold.ttf'}, family['variants'])
        self.assertTrue(data['fonts'][1]['variable'])

    def test_preview_real_rows_are_never_valid_or_persisted(self):
        self.font('Alpha.ttf')
        self.font('Beta.otf', b'OTTO')
        value = self.action('preview')['data']
        self.assertEqual(2, value['stats']['count'])
        self.assertEqual('', value['fingerprint'])
        self.assertTrue(all(not f['valid'] and f['provisional'] for f in value['fonts']))
        self.assertFalse((self.config / 'native_font_index.json').exists())
        self.assertTrue(all(f['valid'] and not f['provisional'] for f in self.action('scan')['data']['fonts']))

    def test_config_is_data_and_metadata_edits_invalidate_fingerprint(self):
        self.font('Alpha.ttf')
        config = self.fonts / 'Alpha.conf'
        config.write_text('name=Display "Name"\nname=ignored\nsupports_cjk=false\n$(touch bad)\n')
        first = self.action('scan')['data']
        self.assertEqual('Display "Name"', first['fonts'][0]['name'])
        self.assertFalse(first['fonts'][0]['supportsCjk'])
        config.write_text('name=Changed\nsupports_cjk=true\n')
        second = self.action('scan')['data']
        self.assertNotEqual(first['fingerprint'], second['fingerprint'])
        self.assertEqual('Changed', second['fonts'][0]['name'])
        config.write_bytes(b'name=CRLF\r\nsupports_cjk=false\r\n')
        third = self.action('scan')['data']['fonts'][0]
        self.assertEqual('CRLF', third['name'])
        self.assertFalse(third['supportsCjk'])

    def test_imported_variable_probe_wins_over_single_file_name(self):
        self.font('Plain.ttf')
        (self.fonts / 'Plain.conf').write_bytes(b'is_variable=true\r\nsupports_cjk=false\r\n')
        row = self.action('scan')['data']['fonts'][0]
        self.assertTrue(row['variable'])
        self.assertEqual(['variable'], row['weights'])
        self.assertEqual({'variable': 'Plain.ttf'}, row['variants'])
        self.assertEqual('variable', row['familyType'])
        self.assertFalse(row['supportsCjk'])
        self.font('Nervar-Bold.ttf')
        (self.fonts / 'Nervar.conf').write_text('is_variable=false\n')
        row = next(f for f in self.action('scan')['data']['fonts'] if f['id'] == 'Nervar')
        self.assertFalse(row['variable'])
        self.assertEqual(['bold'], row['weights'])

    def test_shared_metadata_does_not_reclassify_every_multiweight_file(self):
        self.font('Family-Regular.ttf'); self.font('Family-Bold.ttf')
        (self.fonts / 'Family.conf').write_text('is_variable=true\n')
        row = self.action('refresh')['data']['fonts'][0]
        self.assertEqual(['regular', 'bold'], row['weights'])
        self.assertFalse(row['variable'])
        self.assertEqual('static-family', row['familyType'])

    def test_scanner_revision_invalidates_persisted_semantic_cache(self):
        self.font('Plain.ttf')
        (self.fonts / 'Plain.conf').write_text('is_variable=true\n')
        with patch.object(batch, 'SCANNER_REVISION', 1):
            old = self.action('refresh')
        old['data']['fonts'][0]['variable'] = False
        (self.config / 'native_font_index.json').write_text(batch.compact(old))
        self.assertFalse(self.action('cached')['data']['fonts'][0]['variable'])
        current = self.action('fingerprint')['data']['fingerprint']
        self.assertNotEqual(old['data']['fingerprint'], current)
        new = self.action('scan')['data']
        self.assertEqual(current, new['fingerprint'])
        self.assertTrue(new['fonts'][0]['variable'])

    def test_invalid_or_duplicate_cached_rows_are_rebuilt_without_a_retry_loop(self):
        self.font('Alpha.ttf')
        for rows in ([None], [1], [{}], [{'id': None}], [{'id': ''}],
                     [{'id': 'A'}, {'id': ' A '}], [{'id': 123}]):
            with self.subTest(rows=rows):
                cached = self.action('refresh')
                cached['data']['fonts'] = rows
                (self.config / 'native_font_index.json').write_text(batch.compact(cached))
                self.assertEqual('cache_miss', self.action('cached')['code'])
                rebuilt = self.action('scan')['data']
                self.assertEqual(['Alpha'], [f['id'] for f in rebuilt['fonts']])
                self.assertEqual(rebuilt['fingerprint'], rebuilt['verification']['fingerprint'])

    def test_formats_size_errors_and_exclusions(self):
        for name, magic in [('A.ttf', b'\x00\x01\x00\x00'), ('B.otf', b'OTTO'), ('C.ttc', b'ttcf'),
                            ('D.ttf', b'wOFF'), ('E.ttf', b'wOF2'), ('F.ttf', b'PK\x03\x04')]:
            self.font(name, magic)
        self.font('Unknown.ttf', b'bad!')
        self.font('Small.ttf', size=100)
        for name in ['SysFont.ttf', 'SysSans.ttf', 'bad|name.ttf', '.hidden.ttf', 'Mixed.TtF', 'No.otc']:
            self.font(name)
        rows = {f['id']: f for f in self.action('refresh')['data']['fonts']}
        self.assertEqual(8, len(rows))
        self.assertEqual('字体文件过小', rows['Small']['error'])
        self.assertEqual('字体格式无法识别', rows['Unknown']['error'])
        self.assertTrue(rows['D']['valid']) # Deep application validation remains separate.
        self.assertEqual('WOFF2', rows['E']['format'])
        self.assertEqual('ZIP', rows['F']['format'])

    def test_add_delete_replace_permission_and_empty_invalidation(self):
        path = self.font('Alpha.ttf')
        first = self.action('refresh')['data']['fingerprint']
        before = path.stat()
        self.font('Alpha.ttf', b'OTTO')
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        second = self.action('fingerprint')['data']['fingerprint']
        self.assertNotEqual(first, second)
        path.chmod(0o600)
        self.assertNotEqual(second, self.action('fingerprint')['data']['fingerprint'])
        self.font('Beta.ttf')
        self.assertEqual(2, self.action('scan')['data']['stats']['count'])
        path.unlink()
        self.assertEqual(['Beta'], [f['id'] for f in self.action('scan')['data']['fonts']])
        (self.fonts / 'Beta.ttf').unlink()
        self.assertEqual([], self.action('scan')['data']['fonts'])
        self.fonts.rmdir()
        with self.assertRaises(PermissionError):
            self.action('fingerprint')

    def test_symlink_lstat_size_and_target_replacement_identity(self):
        target = self.base / 'target.ttf'
        target.write_bytes(b'OTTO' + b'\0' * 8192)
        link = self.fonts / 'Link.ttf'
        link.symlink_to(target)
        data = self.action('scan')['data']
        self.assertEqual(link.lstat().st_size, data['fonts'][0]['bytes'])
        self.assertFalse(data['fonts'][0]['valid'])
        target.write_bytes(b'ttcf' + b'\0' * 8192)
        self.assertNotEqual(data['fingerprint'], self.action('fingerprint')['data']['fingerprint'])

    def test_cache_hit_and_corruption_recovery(self):
        self.font('Alpha.ttf')
        self.action('scan')
        path = self.config / 'native_font_index.json'
        first_mtime = path.stat().st_mtime_ns
        self.action('scan')
        self.assertEqual(first_mtime, path.stat().st_mtime_ns)
        path.write_text('{broken')
        self.assertEqual('cache_miss', self.action('cached')['code'])
        self.assertEqual(1, self.action('scan')['data']['stats']['count'])
        (self.config / 'native_font_index.key').write_text('native-v3|old\n')
        self.assertTrue(self.action('scan')['data']['fingerprint'].startswith('font-list-v5:'))
        self.assertEqual([], list(self.config.glob('.native_font_index.*')))

    def test_abnormal_cache_and_config_reads_are_bounded(self):
        self.font('Alpha.ttf')
        (self.config / 'native_font_index.json').write_bytes(b' ' * (batch.MAX_CACHE_BYTES + 1))
        self.assertEqual('cache_miss', self.action('cached')['code'])
        (self.fonts / 'Alpha.conf').write_bytes(b'name=' + b'x' * batch.MAX_CONFIG_BYTES)
        with self.assertRaises(ValueError):
            self.action('refresh')

    def test_large_library_uses_single_batch_and_returns_all_rows(self):
        for i in range(1000):
            self.font(f'Font{i:04d}.ttf')
        started = time.monotonic()
        value = self.action('refresh')
        elapsed = time.monotonic() - started
        self.assertEqual(1000, len(value['data']['fonts']))
        self.assertTrue(all(f['valid'] for f in value['data']['fonts']))
        self.assertEqual(1000, json.loads(batch.compact(value))['data']['stats']['count'])
        print(f'HOST batch inventory 1000 files: {elapsed:.4f}s (not Android latency)')

    def test_fresh_and_reused_scan_bind_same_request_verification(self):
        self.font('Alpha.ttf')
        for action in ('refresh', 'scan'):
            data = self.action(action)['data']
            self.assertEqual({'schema': 'font-list-verification-v1',
                              'fingerprint': data['fingerprint'], 'current': data['current']},
                             data['verification'])
        self.assertNotIn('verification', self.action('cached')['data'])

    def test_mid_scan_change_preserves_previous_cache_and_key(self):
        self.font('Alpha.ttf')
        self.action('refresh')
        cache = self.config / 'native_font_index.json'
        key = self.config / 'native_font_index.key'
        original = (cache.read_bytes(), key.read_bytes())
        snapshot = batch.snapshot
        calls = 0
        def change_before_second(path):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.font('Beta.ttf')
            return snapshot(path)
        with patch.object(batch, 'snapshot', side_effect=change_before_second):
            with self.assertRaisesRegex(ValueError, '扫描期间'):
                self.action('refresh')
        self.assertEqual(original, (cache.read_bytes(), key.read_bytes()))

    def test_permission_loss_during_scan_cannot_publish_verified_cache(self):
        self.font('Alpha.ttf')
        snapshot = batch.snapshot
        calls = 0
        def lose_permission(path):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise PermissionError('permission lost')
            return snapshot(path)
        with patch.object(batch, 'snapshot', side_effect=lose_permission):
            with self.assertRaises(PermissionError):
                self.action('refresh')
        self.assertFalse((self.config / 'native_font_index.json').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
