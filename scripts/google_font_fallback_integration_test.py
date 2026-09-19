#!/usr/bin/env python3
"""Real v1 journal migration + built-in state/actions; no device render claims."""
import json
from pathlib import Path
import tempfile
import unittest
from google_font_fallback_test import m, FakeAndroid

ROOT = Path(__file__).resolve().parents[1]

class IntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = self.root / 'store'
        self.store.mkdir(mode=0o700)
        self.journal = m.Journal(self.store, 0)
        self.backend = FakeAndroid()
        self.module = self.root / 'module'
        (self.module / 'config').mkdir(parents=True)
        (self.module / 'module.prop').write_text('id=LuoShu\n')
        (self.module / 'config/active_font.conf').write_text('custom\n')

    def status(self):
        return m.describe(self.backend, self.journal, self.module)

    def test_initial_visit_only_reads_and_offers_enable(self):
        result = self.status()
        self.assertEqual(result['state'], 'off')
        self.assertTrue(result['canEnable'])
        self.assertFalse(result['canRestore'])
        self.assertIsNone(self.journal.read())
        self.assertEqual(self.backend.calls, [])

    def test_previously_distributed_v1_script_record_is_recognized_and_restorable(self):
        saved = {**self.backend.snapshot(0), 'schema': 'luoshu-google-font-fallback-v1', 'original': 0}
        self.journal.save(saved)
        original = self.journal.path.read_bytes()
        self.backend.states[0] = 2
        result = self.status()
        self.assertEqual(result['state'], 'enabled')
        self.assertTrue(result['managed'])
        self.assertTrue(result['canRestore'])
        self.assertFalse(result['canEnable'])
        self.assertEqual(self.journal.path.read_bytes(), original)
        self.assertEqual(self.backend.calls, [])
        m.restore(self.backend, self.journal)
        self.assertEqual(self.backend.states[0], 0)
        self.assertEqual(self.backend.states[10], 2)
        self.assertEqual(self.status()['state'], 'off')

    def test_external_disable_is_not_claimed_as_our_feature(self):
        self.backend.states[0] = 2
        result = self.status()
        self.assertEqual(result['state'], 'external')
        self.assertFalse(result['canEnable'])
        self.assertFalse(result['canRestore'])
        self.assertEqual(self.backend.calls, [])

    def test_changed_install_does_not_offer_dangerous_restore(self):
        m.enable(self.backend, self.journal)
        self.backend.appid += 1
        result = self.status()
        self.assertEqual(result['state'], 'conflict')
        self.assertFalse(result['canEnable'])
        self.assertFalse(result['canRestore'])
        self.assertIsNotNone(self.journal.read())

    def test_gms_upgrade_same_install_preserves_undo(self):
        m.enable(self.backend, self.journal)
        data = self.journal.read()
        data['versionCode'] = 1
        self.journal.save(data)
        self.assertTrue(self.status()['canRestore'])

    def test_default_font_prevents_enable_but_not_restoration(self):
        (self.module / 'config/active_font.conf').write_text('default\n')
        self.assertFalse(self.status()['canEnable'])
        m.enable(self.backend, self.journal)
        self.assertTrue(self.status()['canRestore'])

    def test_module_disabled_does_not_block_existing_undo(self):
        m.enable(self.backend, self.journal)
        (self.module / 'disable').touch()
        self.assertTrue(self.status()['canRestore'])
        self.assertFalse(self.status()['canEnable'])

    def test_uninstall_restores_only_users_with_our_journals(self):
        m.enable(self.backend, self.journal)
        result = m.restore_owned(self.backend, self.store)
        self.assertEqual(result['users'], [0])
        self.assertEqual(self.backend.states, {0: 0, 10: 2})
        self.assertEqual(self.backend.calls, [(0, 2), (0, 0)])
        self.assertIsNone(self.journal.read())

    def test_uninstall_failure_retains_record(self):
        m.enable(self.backend, self.journal)
        self.backend.fail = 0
        result = m.restore_owned(self.backend, self.store)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['errors'][0]['user'], 0)
        self.assertIsNotNone(self.journal.read())

    def test_uninstall_without_ownership_does_not_mutate(self):
        result = m.restore_owned(self.backend, self.root / 'missing')
        self.assertEqual(result['status'], 'unchanged')
        self.assertEqual(self.backend.calls, [])

    def test_old_script_store_and_schema_are_unchanged(self):
        self.assertEqual(str(m.STORE), '/data/adb/luoshu-google-font-fallback')
        self.assertEqual(m.SCHEMA, 'luoshu-google-font-fallback-v1')

    def test_runtime_and_ui_are_in_real_routes_and_payload(self):
        manifest = (ROOT / 'scripts/module_payload_manifest.txt').read_text().splitlines()
        for file in ('common/google_font_fallback_core.py', 'common/google_font_fallback.py', 'common/google_font_fallback.sh'):
            self.assertIn(file, manifest)
            self.assertTrue((ROOT / file).is_file())
        ui = ROOT / 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/settings'
        self.assertIn('SettingsSection.GOOGLE -> GoogleFontCompatibilityPage()', (ui / 'SettingsHubScreen.kt').read_text())
        page = (ui / 'GoogleFontCompatibilityPage.kt').read_text()
        for text in ('怎么用', '影响与恢复', '恢复原设置', '了解影响，确认开启', '停用模块不会保证自动撤销'):
            self.assertIn(text, page)
        self.assertNotIn('model.enable()', page.split('confirmButton')[0])
        uninstall = (ROOT / 'uninstall.sh').read_text()
        self.assertLess(uninstall.index('restore-owned --json'), uninstall.index('. "$MODDIR/.luoshu-runtime/compat/v227/uninstall.sh"'))

if __name__ == '__main__':
    unittest.main(verbosity=2)
