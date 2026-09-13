#!/usr/bin/env python3
"""Host parser/transaction tests. No Android device/rendering claims."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fallback', ROOT / 'common/google_font_fallback.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def dump(states=None, modern=True):
    states = states or {0: 0, 10: 2}
    head = ('Registered ContentProviders:\n'
            '  com.google.android.gms/.fonts.provider.FontsProvider:\n'
            '    Provider{abc com.google.android.gms/com.google.android.gms.fonts.provider.FontsProvider}\n'
            'Packages:\n'
            '  Package [com.google.android.gms] (abc):\n'
            '    userId=10123\n    versionCode=123456 minSdk=28 targetSdk=36\n')
    if not modern:
        head += '    firstInstallTime=2026-01-01 12:00:00\n'
    for user, state in states.items():
        head += f'    User {user}: installed=true hidden=false suspended=false enabled=0 stopped=false\n'
        if modern:
            head += f'      firstInstallTime=2026-01-{user+1:02d} 12:00:00\n'
        head += '      runtime permissions:\n        android.permission.INTERNET: granted=true\n'
        if state:
            key = 'enabled' if state == 1 else 'disabled'
            head += f'      {key}Components:\n        {m.PROVIDER}\n'
    head += ('Hidden system packages:\n'
             '  Package [com.google.android.gms] (old):\n'
             '    userId=1\n    versionCode=1\n'
             '    firstInstallTime=2020-01-01 00:00:00\n'
             '    User 0: installed=true enabled=0\n'
             f'      disabledComponents:\n        {m.PROVIDER}\n')
    return head


class FakeAndroid:
    def __init__(self, states=None):
        self.states = states or {0: 0, 10: 2}
        self.calls = []
        self.fail = None
        self.fake_success = False
        self.mutate_then_fail = False
        self.appid = 10123
        self.declared = True
        self.reads = 0

    def snapshot(self, user):
        self.reads += 1
        data = m.parse_snapshot(dump(self.states), user)
        data['appId'] = self.appid
        data['declared'] = self.declared
        return data

    def change(self, user, value):
        self.calls.append((user, value))
        if self.fail == value:
            if self.mutate_then_fail:
                self.states[user] = value
            raise m.FallbackError('fixture failure')
        if not self.fake_success:
            self.states[user] = value


class FallbackTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.journal = m.Journal(self.directory, 0)
        self.android = FakeAndroid()

    def test_parser_scopes_main_installed_package_and_user(self):
        a = m.parse_snapshot(dump(), 0)
        b = m.parse_snapshot(dump(), 10)
        self.assertEqual((a['componentState'], b['componentState']), (0, 2))
        self.assertEqual(a['appId'], 10123)
        self.assertTrue(a['declared'])
        self.assertNotEqual(a['firstInstallTime'], b['firstInstallTime'])

    def test_parser_supports_legacy_package_wide_install_time(self):
        data = m.parse_snapshot(dump({0: 1}, modern=False), 0)
        self.assertEqual(data['componentState'], 1)
        self.assertEqual(data['firstInstallTime'], '2026-01-01 12:00:00')

    def test_missing_or_error_dump_never_assumes_enabled(self):
        for data in ('', 'DUMP TIMEOUT', dump().split('Packages:')[0], dump().replace('userId=10123','')):
            with self.subTest(data=data[:10]), self.assertRaises(m.FallbackError):
                m.parse_snapshot(data, 0)

    def test_noninstalled_user_and_missing_user_are_rejected(self):
        for data, user in ((dump().replace('User 0: installed=true', 'User 0: installed=false'), 0),
                           (dump(), 11)):
            with self.subTest(user=user), self.assertRaises(m.FallbackError):
                m.parse_snapshot(data, user)

    def test_live_enabled_disabled_conflict_rejected(self):
        text = dump({0: 1}).replace('Hidden system packages:',
                                  f'      disabledComponents:\n        {m.PROVIDER}\nHidden system packages:')
        with self.assertRaises(m.FallbackError):
            m.parse_snapshot(text, 0)

    def test_absent_registered_provider_does_not_modify(self):
        self.android.declared = False
        with self.assertRaises(m.FallbackError):
            m.enable(self.android, self.journal)
        self.assertEqual(self.android.calls, [])

    def test_write_ahead_record_exists_before_component_change(self):
        original = self.android.change
        def change(user, state):
            self.assertEqual(self.journal.read()['original'], 0)
            original(user, state)
        self.android.change = change
        result = m.enable(self.android, self.journal)
        self.assertEqual(result['status'], 'component-disabled')
        self.assertEqual(self.android.calls, [(0,2)])
        self.assertEqual(self.android.states[10], 2)

    def test_repeat_enable_is_idempotent_and_preserves_original(self):
        m.enable(self.android, self.journal)
        before = self.journal.path.read_bytes()
        m.enable(self.android, self.journal)
        self.assertEqual(self.android.calls, [(0,2)])
        self.assertEqual(self.journal.path.read_bytes(), before)

    def test_restore_returns_default_not_force_enable(self):
        m.enable(self.android, self.journal)
        m.restore(self.android, self.journal)
        self.assertEqual(self.android.calls, [(0,2), (0,0)])
        self.assertIsNone(self.journal.read())

    def test_restore_returns_explicit_enable_when_originally_enabled(self):
        self.android.states[0] = 1
        m.enable(self.android, self.journal)
        m.restore(self.android, self.journal)
        self.assertEqual(self.android.calls, [(0,2), (0,1)])

    def test_preexisting_disabled_component_not_owned_or_reenabled(self):
        self.android.states[0] = 2
        result = m.enable(self.android, self.journal)
        self.assertEqual(result['status'], 'externally-disabled')
        m.restore(self.android, self.journal)
        self.assertIsNone(self.journal.read())
        self.assertEqual(self.android.calls, [])

    def test_disable_failure_rolls_back_record_without_unrelated_changes(self):
        self.android.fail = 2
        with self.assertRaises(m.FallbackError):
            m.enable(self.android, self.journal)
        self.assertEqual(self.android.states[0], 0)
        self.assertIsNone(self.journal.read())

    def test_timeout_after_real_mutation_rolls_back_to_original(self):
        self.android.fail = 2
        self.android.mutate_then_fail = True
        with self.assertRaises(m.FallbackError):
            m.enable(self.android, self.journal)
        self.assertEqual(self.android.calls, [(0,2), (0,0)])
        self.assertEqual(self.android.states[0], 0)
        self.assertIsNone(self.journal.read())

    def test_command_success_without_state_change_is_not_success(self):
        self.android.fake_success = True
        with self.assertRaises(m.FallbackError):
            m.enable(self.android, self.journal)
        self.assertIsNone(self.journal.read())

    def test_restore_failure_preserves_recovery_record(self):
        m.enable(self.android, self.journal)
        self.android.fail = 0
        with self.assertRaises(m.FallbackError):
            m.restore(self.android, self.journal)
        self.assertEqual(self.journal.read()['original'], 0)

    def test_new_gms_install_not_modified_by_old_record(self):
        m.enable(self.android, self.journal)
        self.android.appid = 10199
        with self.assertRaises(m.FallbackError):
            m.restore(self.android, self.journal)
        self.assertEqual(self.android.calls, [(0,2)])
        self.assertIsNotNone(self.journal.read())

    def test_external_change_not_overwritten_on_restore(self):
        m.enable(self.android, self.journal)
        self.android.states[0] = 1
        with self.assertRaises(m.FallbackError):
            m.restore(self.android, self.journal)
        self.assertEqual(self.android.calls, [(0,2)])

    def test_malicious_journal_component_not_executed(self):
        m.enable(self.android, self.journal)
        data = self.journal.read()
        data['component'] = 'com.google.android.gms'  # no whole-package operation
        self.journal.path.write_text(json.dumps(data))
        with self.assertRaises(m.FallbackError):
            m.restore(self.android, self.journal)
        self.assertEqual(self.android.calls, [(0,2)])

    def test_symlink_journal_rejected(self):
        target = self.directory / 'other'
        target.write_text('{}')
        self.journal.path.symlink_to(target)
        with self.assertRaises(m.FallbackError):
            self.journal.read()

    def test_file_lock_is_exclusive_and_reusable(self):
        root = self.directory / 'private'
        with m.locked_store(root):
            with self.assertRaises(m.FallbackError):
                with m.locked_store(root):
                    pass
        with m.locked_store(root):
            pass

    def test_unknown_inline_components_are_rejected(self):
        text = dump({0: 1}).replace('enabledComponents:', 'enabledComponents: [unknown]')
        with self.assertRaises(m.FallbackError):
            m.parse_snapshot(text, 0)

    def test_recovery_record_for_wrong_user_is_rejected(self):
        m.enable(self.android, self.journal)
        data = self.journal.read()
        data['user'] = 10
        self.journal.path.write_text(json.dumps(data))
        with self.assertRaises(m.FallbackError):
            m.restore(self.android, self.journal)
        self.assertEqual(self.android.calls, [(0,2)])

    def test_backend_can_only_change_exact_font_component_for_one_user(self):
        backend = m.Android()
        with patch.object(backend, 'run') as run:
            for value in (0,1,2):
                backend.change(10,value)
            self.assertEqual([x.args for x in run.call_args_list], [
                ('/system/bin/pm', command, '--user', '10', m.COMPONENT)
                for command in ('default-state','enable','disable')])

    def test_status_default_and_no_automatic_enable_in_source(self):
        source = (ROOT / 'common/google_font_fallback.py').read_text()
        self.assertIn("default='status'", source)
        self.assertNotIn('shutil.rmtree', source)
        self.assertNotIn("'force-stop'", source)
        self.assertNotIn("'UpdateSchedulerService'", source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
