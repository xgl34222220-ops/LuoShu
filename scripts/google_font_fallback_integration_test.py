#!/usr/bin/env python3
"""Real v1 journal migration + built-in state/actions; no device render claims."""
import json
import os
import shutil
import stat
import subprocess
from unittest.mock import patch
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

    def test_store_survives_module_removal_and_v1_schema_remains_compatible(self):
        self.assertEqual(str(m.STORE), '/data/adb/luoshu/google-font-fallback')
        self.assertEqual(str(m.LEGACY_STORE), '/data/adb/luoshu-google-font-fallback')
        self.assertNotIn('/modules/', str(m.STORE))
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


class JournalMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fallback-journal-migration-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.legacy = self.root / 'luoshu-google-font-fallback'
        self.legacy.mkdir(mode=0o700)
        self.canonical = self.root / 'luoshu/google-font-fallback'
        self.backend = FakeAndroid()
        self.saved = {**self.backend.snapshot(0), 'schema': m.SCHEMA, 'original': 0}
        m.Journal(self.legacy, 0).save(self.saved)

    def migrate(self):
        return m.prepare_store(self.canonical, self.legacy)

    def canonical_store(self):
        self.canonical.mkdir(mode=0o700, parents=True)

    def test_complete_legacy_tree_moves_with_original_journal_inode_and_exact_bytes(self):
        before_root = self.legacy.stat().st_ino
        before = self.legacy / 'user-0.json'
        old_inode, old_bytes = before.stat().st_ino, before.read_bytes()
        self.assertEqual(self.migrate(), self.canonical)
        self.assertEqual(self.canonical.stat().st_ino, before_root)
        journal = m.Journal(self.canonical, 0)
        self.assertEqual(journal.path.stat().st_ino, old_inode)
        self.assertEqual(journal.path.read_bytes(), old_bytes)
        self.assertTrue(self.legacy.is_symlink())
        self.assertEqual(self.legacy.resolve(), self.canonical)
        self.backend.states[0] = 2
        m.restore(self.backend, journal)
        self.assertEqual(self.backend.states, {0: 0, 10: 2})

    def test_repeated_migration_is_idempotent(self):
        self.migrate()
        before = (self.canonical / 'user-0.json').stat().st_ino
        self.migrate()
        self.assertEqual((self.canonical / 'user-0.json').stat().st_ino, before)
        self.assertEqual(list(self.canonical.parent.glob('google-font-fallback-legacy-*')), [])

    def test_unknown_symlink_is_rejected_without_following_or_moving(self):
        outsider = self.root / 'unrelated'
        outsider.mkdir()
        sentinel = outsider / 'keep'
        sentinel.write_text('unrelated app data')
        shutil.rmtree(self.legacy)
        self.legacy.symlink_to(outsider, target_is_directory=True)
        with self.assertRaises(m.FallbackError):
            self.migrate()
        self.assertEqual(sentinel.read_text(), 'unrelated app data')
        self.assertTrue(self.legacy.is_symlink())
        self.assertFalse(self.canonical.exists())

    def test_unknown_files_and_unsafe_journals_keep_old_tree_intact(self):
        original = (self.legacy / 'user-0.json').read_bytes()
        unknown = self.legacy / 'not-owned.txt'
        unknown.write_text('unrelated')
        with self.assertRaises(m.FallbackError):
            self.migrate()
        self.assertEqual((self.legacy / 'user-0.json').read_bytes(), original)
        self.assertFalse(self.canonical.exists())
        unknown.unlink()
        (self.legacy / 'user-0.json').chmod(0o666)
        with self.assertRaises(m.FallbackError):
            self.migrate()
        self.assertEqual((self.legacy / 'user-0.json').read_bytes(), original)
        self.assertFalse(self.canonical.exists())

    def test_arbitrary_component_record_is_never_migrated_or_executed(self):
        path = self.legacy / 'user-0.json'
        bad = {**self.saved, 'component': 'example.unrelated/.Service'}
        path.write_text(json.dumps(bad))
        with self.assertRaises(m.FallbackError):
            self.migrate()
        self.assertEqual(json.loads(path.read_text()), bad)
        self.assertEqual(self.backend.calls, [])
        self.assertFalse(self.canonical.exists())

    def test_conflicting_undo_records_preserve_both_and_refuse_migration(self):
        self.canonical_store()
        newer = {**self.saved, 'original': 1}
        m.Journal(self.canonical, 0).save(newer)
        old_bytes = (self.legacy / 'user-0.json').read_bytes()
        new_bytes = (self.canonical / 'user-0.json').read_bytes()
        with self.assertRaises(m.FallbackError):
            self.migrate()
        self.assertFalse(self.legacy.is_symlink())
        self.assertEqual((self.legacy / 'user-0.json').read_bytes(), old_bytes)
        self.assertEqual((self.canonical / 'user-0.json').read_bytes(), new_bytes)
        self.assertEqual(self.backend.calls, [])

    def test_existing_identical_record_is_archived_without_discarding_duplicate_inode(self):
        self.canonical_store()
        m.Journal(self.canonical, 0).save(self.saved)
        old_inode = (self.legacy / 'user-0.json').stat().st_ino
        old_bytes = (self.legacy / 'user-0.json').read_bytes()
        self.migrate()
        archives = list(self.canonical.parent.glob('google-font-fallback-legacy-*'))
        self.assertEqual(len(archives), 1)
        archived = archives[0] / 'user-0.json'
        self.assertEqual(archived.stat().st_ino, old_inode)
        self.assertEqual(archived.read_bytes(), old_bytes)
        self.assertEqual(m.Journal(self.canonical, 0).read(), self.saved)

    def test_nonoverlapping_users_merge_by_inode_without_cross_user_changes(self):
        self.canonical_store()
        saved10 = {**self.backend.snapshot(10), 'schema': m.SCHEMA, 'original': 1}
        m.Journal(self.canonical, 10).save(saved10)
        old_inode = (self.legacy / 'user-0.json').stat().st_ino
        self.migrate()
        self.assertEqual((self.canonical / 'user-0.json').stat().st_ino, old_inode)
        self.assertEqual(m.Journal(self.canonical, 10).read(), saved10)
        self.assertEqual(self.backend.calls, [])

    def test_active_legacy_transaction_blocks_migration_without_moving_records(self):
        with m.locked_store(self.legacy):
            with self.assertRaises(m.FallbackError):
                self.migrate()
        self.assertTrue((self.legacy / 'user-0.json').is_file())
        self.assertFalse(self.canonical.exists())

    def test_interruption_after_inode_move_keeps_recovery_record_available_on_retry(self):
        old_inode = (self.legacy / 'user-0.json').stat().st_ino
        with patch.object(m.os, 'symlink', side_effect=OSError('fixture interruption')):
            with self.assertRaises(OSError):
                self.migrate()
        self.assertEqual((self.canonical / 'user-0.json').stat().st_ino, old_inode)
        self.migrate()
        self.backend.states[0] = 2
        m.restore(self.backend, m.Journal(self.canonical, 0))
        self.assertEqual(self.backend.states[0], 0)

    def test_failed_restore_survives_deletion_of_module_directory(self):
        self.migrate()
        module = self.root / 'modules/LuoShu'
        module.mkdir(parents=True)
        self.backend.states[0] = 2
        self.backend.fail = 0
        result = m.restore_owned(self.backend, self.canonical)
        self.assertEqual(result['status'], 'error')
        shutil.rmtree(module)
        self.assertIsNotNone(m.Journal(self.canonical, 0).read())
        self.backend.fail = None
        self.assertEqual(m.restore_owned(self.backend, self.canonical)['status'], 'restored')


class SharedStoreParentTest(unittest.TestCase):
    """Reproduce the module helper's shared root, keeping its payload untouched."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fallback-shared-parent-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backend = FakeAndroid()
        self.saved = {**self.backend.snapshot(0), 'schema': m.SCHEMA, 'original': 0}

    def fixture(self, name='case', umask=None, mode=0o755):
        ancestor = self.root / name
        ancestor.mkdir(mode=0o700)
        parent = ancestor / 'luoshu'
        module = ancestor / 'module'
        (module / '.luoshu-payload').mkdir(mode=0o700, parents=True)
        if umask is None:
            parent.mkdir(mode=mode)
            parent.chmod(mode)
        else:
            env = {**os.environ, 'MODULE_DIR': str(module),
                   'LUOSHU_PRIVATE_STATE_ROOT': str(parent / 'private-payload')}
            # The empty payload makes the real mount helper create only its
            # state files, so this fixture never attempts any host mount.
            result = subprocess.run(
                ['sh', '-c', 'umask "$1"; . "$2"; luoshu_private_mount_module_view "$3"',
                 'private-payload-fixture', f'{umask:03o}',
                 str(ROOT / 'common/private_payload.sh'), str(module)],
                env=env, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0o777 & ~umask)
            state = parent / 'private-payload'
            (state / 'module-view.mounts').write_bytes(b'/module/system\n')
            (state / 'module-view.symlinks').write_bytes(b'/module/product|/private/product\n')
            retained = parent / 'self-mount'
            retained.mkdir()
            (retained / 'mount.ids').write_bytes(b'12 48\n')
            (retained / 'payload-alias').symlink_to(module / '.luoshu-payload')
        return ancestor, parent, parent / 'google-font-fallback', ancestor / 'luoshu-google-font-fallback'

    def snapshot(self, directory):
        result = {}
        for path in (directory, *sorted(directory.rglob('*'))):
            info = path.lstat()
            value = (os.readlink(path) if stat.S_ISLNK(info.st_mode)
                     else path.read_bytes() if stat.S_ISREG(info.st_mode) else None)
            result[str(path.relative_to(directory))] = (
                info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid, value)
        return result

    def save(self, directory):
        directory.mkdir(mode=0o700)
        journal = m.Journal(directory, 0)
        journal.save(self.saved)
        return journal

    def assert_record(self, journal, inode, contents):
        self.assertEqual(journal.path.stat().st_ino, inode)
        self.assertEqual(journal.path.read_bytes(), contents)
        self.assertEqual(journal.read(), self.saved)

    def test_real_private_payload_umasks_repair_shared_root_without_touching_payload(self):
        for mask in (0o000, 0o002):
            with self.subTest(umask=f'{mask:03o}'):
                _, parent, canonical, legacy = self.fixture(f'helper-{mask:03o}', umask=mask)
                before = {name: self.snapshot(parent / name)
                          for name in ('private-payload', 'self-mount')}
                self.assertEqual(m.prepare_store(canonical, legacy), canonical)
                self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0o755)
                self.assertEqual(stat.S_IMODE(canonical.stat().st_mode), 0o700)
                self.assertEqual({name: self.snapshot(parent / name) for name in before}, before)
                self.assertEqual(self.backend.calls, [])

    def test_existing_v1_record_survives_helper_root_repair_and_remains_restorable(self):
        for mask in (0o000, 0o002):
            with self.subTest(umask=f'{mask:03o}'):
                _, parent, canonical, legacy = self.fixture(f'existing-{mask:03o}', umask=mask)
                journal = self.save(canonical)
                inode, contents = journal.path.stat().st_ino, journal.path.read_bytes()
                before = self.snapshot(parent / 'private-payload')
                m.prepare_store(canonical, legacy)
                self.assert_record(journal, inode, contents)
                self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0o755)
                self.assertEqual(self.snapshot(parent / 'private-payload'), before)
                self.backend.states[0] = 2
                m.restore(self.backend, journal)
                self.assertEqual(self.backend.states, {0: 0, 10: 2})
                self.assertIsNone(journal.read())

    def test_legacy_v1_record_migrates_by_inode_after_shared_root_repair(self):
        for mask in (0o000, 0o002):
            with self.subTest(umask=f'{mask:03o}'):
                _, parent, canonical, legacy = self.fixture(f'legacy-{mask:03o}', umask=mask)
                journal = self.save(legacy)
                inode, contents = journal.path.stat().st_ino, journal.path.read_bytes()
                before = self.snapshot(parent / 'private-payload')
                m.prepare_store(canonical, legacy)
                migrated = m.Journal(canonical, 0)
                self.assert_record(migrated, inode, contents)
                self.assertTrue(legacy.is_symlink())
                self.assertEqual(legacy.resolve(), canonical)
                self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0o755)
                self.assertEqual(self.snapshot(parent / 'private-payload'), before)
                self.backend.states[0] = 2
                m.restore(self.backend, migrated)
                self.assertEqual(self.backend.states, {0: 0, 10: 2})

    def test_repair_preserves_existing_read_and_execute_bits(self):
        for original in (0o777, 0o775, 0o771, 0o773, 0o770, 0o733):
            with self.subTest(mode=f'{original:04o}'):
                _, parent, canonical, legacy = self.fixture(f'bits-{original:04o}', mode=original)
                inode = parent.stat().st_ino
                m.prepare_store(canonical, legacy)
                self.assertEqual(stat.S_IMODE(parent.stat().st_mode), original & ~0o022)
                self.assertEqual(parent.stat().st_ino, inode)

    def test_safe_shared_root_modes_remain_unchanged_without_chmod(self):
        for mode in (0o700, 0o711, 0o750, 0o755):
            with self.subTest(mode=f'{mode:04o}'):
                _, parent, canonical, legacy = self.fixture(f'safe-{mode:04o}', mode=mode)
                inode = parent.stat().st_ino
                with patch.object(m.os, 'fchmod', side_effect=AssertionError('safe parent chmod')):
                    m.prepare_store(canonical, legacy)
                self.assertEqual(stat.S_IMODE(parent.stat().st_mode), mode)
                self.assertEqual(parent.stat().st_ino, inode)

    def test_parent_symlink_is_rejected_without_following_it(self):
        ancestor, parent, canonical, legacy = self.fixture(mode=0o777)
        outsider = ancestor / 'outsider'
        parent.rename(outsider)
        sentinel = outsider / 'unrelated'
        sentinel.write_bytes(b'unrelated data')
        before = self.snapshot(outsider)
        parent.symlink_to(outsider, target_is_directory=True)
        with self.assertRaises((m.FallbackError, OSError)):
            m.prepare_store(canonical, legacy)
        self.assertEqual(self.snapshot(outsider), before)
        self.assertTrue(parent.is_symlink())

    def test_parent_regular_file_is_rejected_without_mutating_it(self):
        _, parent, canonical, legacy = self.fixture()
        parent.rmdir()
        parent.write_bytes(b'unrelated regular file')
        before = self.snapshot(parent)
        with self.assertRaises((m.FallbackError, OSError)):
            m.prepare_store(canonical, legacy)
        self.assertEqual(self.snapshot(parent), before)

    def test_foreign_parent_uid_metadata_is_rejected_without_repair(self):
        _, parent, canonical, legacy = self.fixture(mode=0o777)
        self.save(canonical)
        before = self.snapshot(parent)
        real_lstat = Path.lstat

        def foreign_lstat(path, *args, **kwargs):
            info = real_lstat(path, *args, **kwargs)
            if path == parent:
                fields = list(info)
                fields[4] = os.geteuid() + 1
                return os.stat_result(fields)
            return info

        # Synthetic UID metadata: the managed host maps only UID 0 and cannot
        # chown a fixture to another UID. No device ownership claim is made.
        with patch.object(Path, 'lstat', foreign_lstat):
            with self.assertRaises(m.FallbackError):
                m.prepare_store(canonical, legacy)
        self.assertEqual(self.snapshot(parent), before)
        self.assertFalse(legacy.exists())
        self.assertEqual(self.backend.calls, [])

    def test_group_or_world_writable_ancestor_blocks_repair_and_preserves_records(self):
        for ancestor_mode in (0o777, 0o775):
            with self.subTest(mode=f'{ancestor_mode:04o}'):
                ancestor, parent, canonical, legacy = self.fixture(
                    f'unsafe-ancestor-{ancestor_mode:04o}', mode=0o777)
                self.save(legacy)
                before = self.snapshot(parent), self.snapshot(legacy)
                ancestor.chmod(ancestor_mode)
                with self.assertRaises(m.FallbackError):
                    m.prepare_store(canonical, legacy)
                self.assertEqual((self.snapshot(parent), self.snapshot(legacy)), before)
                self.assertFalse(canonical.exists())

    def test_symlink_ancestor_blocks_repair_without_following_to_shared_root(self):
        ancestor, parent, canonical, legacy = self.fixture(mode=0o777)
        self.save(legacy)
        before = self.snapshot(parent), self.snapshot(legacy)
        actual = self.root / 'actual-ancestor'
        ancestor.rename(actual)
        ancestor.symlink_to(actual, target_is_directory=True)
        with self.assertRaises((m.FallbackError, OSError)):
            m.prepare_store(canonical, legacy)
        self.assertEqual((self.snapshot(parent), self.snapshot(legacy)), before)
        self.assertFalse(canonical.exists())

    def test_foreign_ancestor_uid_metadata_blocks_repair(self):
        ancestor, parent, canonical, legacy = self.fixture(mode=0o777)
        self.save(legacy)
        before = self.snapshot(parent), self.snapshot(legacy)
        real_fstat = os.fstat
        identity = ancestor.stat().st_dev, ancestor.stat().st_ino

        def foreign_fstat(fd):
            info = real_fstat(fd)
            if (info.st_dev, info.st_ino) == identity:
                fields = list(info)
                fields[4] = os.geteuid() + 1
                return os.stat_result(fields)
            return info

        with patch.object(m.os, 'fstat', foreign_fstat):
            with self.assertRaises(m.FallbackError):
                m.prepare_store(canonical, legacy)
        self.assertEqual((self.snapshot(parent), self.snapshot(legacy)), before)
        self.assertFalse(canonical.exists())

    def test_chmod_error_keeps_both_v1_record_trees_and_payload_unchanged(self):
        _, parent, canonical, legacy = self.fixture(umask=0o000)
        self.save(canonical)
        self.save(legacy)
        before = self.snapshot(parent), self.snapshot(legacy)
        with patch.object(m.os, 'fchmod', side_effect=PermissionError('fixture chmod denied')) as chmod:
            with self.assertRaises((m.FallbackError, OSError)):
                m.prepare_store(canonical, legacy)
        chmod.assert_called_once()
        self.assertEqual((self.snapshot(parent), self.snapshot(legacy)), before)
        self.assertEqual(self.backend.calls, [])

    def test_parent_replaced_during_chmod_never_mutates_new_target_or_moves_records(self):
        ancestor, parent, canonical, legacy = self.fixture(umask=0o000)
        self.save(legacy)
        legacy_before = self.snapshot(legacy)
        original = ancestor / 'original-luoshu'
        outsider = ancestor / 'unrelated'
        outsider.mkdir(mode=0o777)
        outsider.chmod(0o777)
        (outsider / 'sentinel').write_bytes(b'unrelated data')
        outsider_before = self.snapshot(outsider)
        original_payload = self.snapshot(parent / 'private-payload')
        real_fchmod = os.fchmod

        def replace_parent(fd, mode):
            real_fchmod(fd, mode)
            parent.rename(original)
            parent.symlink_to(outsider, target_is_directory=True)

        with patch.object(m.os, 'fchmod', side_effect=replace_parent) as chmod:
            with self.assertRaises((m.FallbackError, OSError)):
                m.prepare_store(canonical, legacy)
        chmod.assert_called_once()
        self.assertEqual(self.snapshot(outsider), outsider_before)
        self.assertEqual(self.snapshot(legacy), legacy_before)
        self.assertEqual(self.snapshot(original / 'private-payload'), original_payload)
        self.assertEqual(stat.S_IMODE(original.stat().st_mode), 0o755)
        self.assertEqual(self.backend.calls, [])

    def test_ancestor_replaced_during_chmod_blocks_migration(self):
        ancestor, parent, canonical, legacy = self.fixture(umask=0o000)
        self.save(legacy)
        records_before = self.snapshot(legacy)
        payload_before = self.snapshot(parent / 'private-payload')
        actual = self.root / 'actual-ancestor'
        real_fchmod = os.fchmod

        def replace_ancestor(fd, mode):
            real_fchmod(fd, mode)
            ancestor.rename(actual)
            ancestor.symlink_to(actual, target_is_directory=True)

        with patch.object(m.os, 'fchmod', side_effect=replace_ancestor) as chmod:
            with self.assertRaises((m.FallbackError, OSError)):
                m.prepare_store(canonical, legacy)
        chmod.assert_called_once()
        self.assertEqual(self.snapshot(legacy), records_before)
        self.assertEqual(self.snapshot(parent / 'private-payload'), payload_before)
        self.assertFalse(canonical.exists())

    def test_ancestor_widened_during_chmod_blocks_migration(self):
        ancestor, parent, canonical, legacy = self.fixture(umask=0o000)
        self.save(legacy)
        records_before = self.snapshot(legacy)
        payload_before = self.snapshot(parent / 'private-payload')
        real_fchmod = os.fchmod

        def widen_ancestor(fd, mode):
            real_fchmod(fd, mode)
            ancestor.chmod(0o777)

        with patch.object(m.os, 'fchmod', side_effect=widen_ancestor) as chmod:
            with self.assertRaises((m.FallbackError, OSError)):
                m.prepare_store(canonical, legacy)
        chmod.assert_called_once()
        self.assertEqual(self.snapshot(legacy), records_before)
        self.assertEqual(self.snapshot(parent / 'private-payload'), payload_before)
        self.assertFalse(canonical.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
