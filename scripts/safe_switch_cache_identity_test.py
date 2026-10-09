#!/usr/bin/env python3
"""Exercise the production safe-switch cache against donor/policy changes."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(os.environ.get('LUOSHU_TEST_ROOT', str(Path(__file__).resolve().parents[1])))
FUNCTIONS = ('read_state_value', 'safe_hash_stream', 'safe_source_identity',
             'safe_inventory_identity', 'safe_code_identity', 'safe_mapper_identity',
             'safe_validator_identity', 'safe_family_files', 'safe_family_identity', 'safe_rom_identity',
             'safe_partition_list', 'safe_validation_key', 'safe_validation_restore',
             'safe_validation_store', 'safe_switch_cache_key', 'safe_switch_cache_matches', 'safe_switch_cache_ready',
             'safe_switch_cache_restore', 'safe_switch_cache_dir_kb', 'safe_switch_cache_prune',
             'safe_switch_cache_store', 'wait_for_prewarm_cache')


def functions_from(source: str) -> str:
    return '\n'.join(re.search(r'^' + name + r'\(\) \{.*?^\}', source,
                              re.M | re.S).group() for name in FUNCTIONS)


class SafeSwitchCacheIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        shutil.copytree(ROOT / 'common', self.module / 'common',
                        ignore=shutil.ignore_patterns('python', '__pycache__'))
        self.config = self.module / 'config'; self.config.mkdir()
        self.fonts = self.root / 'public/fonts'; self.fonts.mkdir(parents=True)
        self.regular = self.fonts / 'Demo-Regular.ttf'; self.regular.write_bytes(b'R' * 4096)
        self.bold = self.fonts / 'Demo-Bold.ttf'; self.bold.write_bytes(b'B' * 4096)
        self.stage = self.root / 'stage'; self.stage.mkdir()
        self.scope = self.root / 'scope'; self.scope.mkdir()
        self.cache = self.root / 'cache'; self.cache.mkdir()
        self.log = self.root / 'log'
        self.source = (ROOT / 'common/legacy_v14_4/font_switch_safe.sh').read_text()
        self.code = functions_from(self.source)
        self.env = {**os.environ, 'MODDIR': str(self.module), 'MODULE_DIR': str(self.module),
                    'LUOSHU_PUBLIC_DIR': str(self.fonts.parent),
                    'LEGACY_DIR': str(self.module / 'common/legacy_v14_4'),
                    'CONFIG_DIR': str(self.config), 'USER_FONTS_DIR': str(self.fonts),
                    'STAGE_PAYLOAD': str(self.stage), 'SWITCH_CACHE_ROOT': str(self.cache),
                    'LUOSHU_TASK_SCOPE_TMPDIR': str(self.scope), 'SWITCH_CACHE_MAX_ENTRIES': '3',
                    'SWITCH_CACHE_MAX_KB': '786432',
                    'SWITCH_VALIDATION_CACHE_ROOT': str(self.root / 'validation'),
                    'SWITCH_CACHE_SCHEMA': 'safe-switch-metrics-v2', 'LOG_FILE': str(self.log),
                    'LUOSHU_BUILD_KEY': 'fixture-build', 'FONT': str(self.regular)}

    def shell(self, body, **env):
        # The actual legacy family parser is used for every key computation.
        script = self.code + '\n. "$LEGACY_DIR/util_functions.sh"\n' + body
        return subprocess.run(['sh', '-c', script], env={**self.env, **env},
                              text=True, capture_output=True, timeout=15)

    def key(self):
        result = self.shell('safe_switch_cache_key "$FONT" Demo')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout.strip(), r'^[0-9a-f]{64}$')
        return result.stdout.strip()

    def seed_cache(self):
        result = self.shell('''
key=$(safe_switch_cache_key "$FONT" Demo) || exit 1
mkdir -p "$SWITCH_CACHE_ROOT/$key/tree/system/fonts"
printf cached-donor > "$SWITCH_CACHE_ROOT/$key/tree/system/fonts/Roboto-Regular.ttf"
{
  printf 'schema=%s\nfont=Demo\n' "$SWITCH_CACHE_SCHEMA"
  printf 'sourceIdentity=%s\n' "$(safe_source_identity "$FONT")"
  printf 'familyIdentity=%s\n' "$(safe_family_identity Demo)"
  printf 'inventoryIdentity=%s\n' "$(safe_inventory_identity)"
  printf 'rom=%s\n' "$(safe_rom_identity)"
  printf 'mapperIdentity=%s\n' "$(safe_mapper_identity)"
} > "$SWITCH_CACHE_ROOT/$key/cache.conf"
safe_switch_cache_ready "$FONT" Demo && safe_switch_cache_restore "$FONT" Demo
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.stage / 'system/fonts/Roboto-Regular.ttf').read_text(), 'cached-donor')

    def assert_cache_miss(self):
        for action in ('safe_switch_cache_ready', 'safe_switch_cache_restore'):
            result = self.shell(action + ' "$FONT" Demo')
            self.assertNotEqual(result.returncode, 0, action)

    def test_unchanged_cache_restores_and_other_families_do_not_invalidate(self):
        self.seed_cache()
        before = self.key()
        (self.fonts / 'Unrelated-Bold.ttf').write_bytes(b'U' * 4096)
        self.assertEqual(self.key(), before)
        self.assertEqual(self.shell('safe_switch_cache_restore "$FONT" Demo').returncode, 0)
        marker = self.root / 'readiness-calls'
        probe = '''
safe_switch_cache_ready() { printf called >> "$MARKER"; return 0; }
luoshu_font_lock_active() { return "$PRODUCER_ACTIVE_RC"; }
wait_for_prewarm_cache "$FONT" Demo
'''
        self.assertNotEqual(self.shell(probe, MARKER=str(marker), PRODUCER_ACTIVE_RC='1').returncode, 0)
        self.assertFalse(marker.exists(), 'ordinary switches must not repeat the full readiness proof')
        self.assertEqual(self.shell(probe, MARKER=str(marker), PRODUCER_ACTIVE_RC='0').returncode, 0)
        self.assertEqual(marker.read_text(), 'called', 'active prewarm workers still require readiness proof')

    def test_donor_edit_add_and_remove_each_invalidate_the_tree(self):
        self.seed_cache()
        self.bold.write_bytes(b'N' * 4096)
        self.assert_cache_miss()
        self.seed_cache()
        (self.fonts / 'Demo-Medium.ttf').write_bytes(b'M' * 4096)
        self.assert_cache_miss()
        self.seed_cache()
        self.bold.unlink()
        self.assert_cache_miss()

    def test_same_size_same_second_primary_edit_invalidates_validation_and_tree(self):
        self.seed_cache()
        result = self.shell('safe_validation_store "$FONT"; safe_validation_restore "$FONT"')
        self.assertEqual(result.returncode, 0, result.stderr)
        before = self.regular.stat()
        self.regular.write_bytes(b'N' * before.st_size)
        # Deliberately retain the whole-second timestamp to reproduce old keys.
        os.utime(self.regular, ns=(before.st_atime_ns, before.st_mtime_ns + 1))
        self.assert_cache_miss()
        self.assertNotEqual(self.shell('safe_validation_restore "$FONT"').returncode, 0)

    def test_late_donor_edit_after_key_selection_never_restores_stale_tree(self):
        self.seed_cache()
        original = re.search(r'^safe_switch_cache_key\(\) \{.*?^\}', self.source,
                             re.M | re.S).group().replace('safe_switch_cache_key()', '_fixture_original_key()', 1)
        body = original + '''
safe_switch_cache_key() {
  _fixture_key=$(_fixture_original_key "$@") || return 1
  printf late-edit >> "$USER_FONTS_DIR/Demo-Bold.ttf"
  printf '%s\n' "$_fixture_key"
}
safe_switch_cache_restore "$FONT" Demo
'''
        self.assertNotEqual(self.shell(body).returncode, 0)
        self.assertEqual((self.stage / 'system/fonts/Roboto-Regular.ttf').read_text(), 'cached-donor')

    def test_changed_donor_during_generation_never_labels_old_tree_with_new_identity(self):
        fonts = self.stage / 'system/fonts'; fonts.mkdir(parents=True)
        shutil.copyfile(self.bold, fonts / 'Roboto-Bold.ttf')
        before = self.key()
        self.bold.write_bytes(b'N' * 4096)
        result = self.shell('safe_switch_cache_store "$FONT" Demo "$EXPECTED"', EXPECTED=before)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.cache.iterdir()), [])
        self.assert_cache_miss()

    def test_production_store_requires_original_inputs_and_rechecks_before_publication(self):
        fonts = self.stage / 'system/fonts'; fonts.mkdir(parents=True)
        shutil.copyfile(self.bold, fonts / 'Roboto-Bold.ttf')
        expected = self.key()
        self.assertNotEqual(self.shell('safe_switch_cache_store "$FONT" Demo').returncode, 0)
        self.assertEqual(self.shell('safe_switch_cache_store "$FONT" Demo "$EXPECTED"',
                                   EXPECTED=expected).returncode, 0)
        self.assertEqual(self.shell('safe_switch_cache_restore "$FONT" Demo').returncode, 0)
        self.assertEqual((fonts / 'Roboto-Bold.ttf').read_bytes(), self.bold.read_bytes())
        # Delay the mutation until store has selected its matching key and
        # copied the old stage. Its final full-key comparison must refuse it.
        original = re.search(r'^safe_family_identity\(\) \{.*?^\}', self.source,
                             re.M | re.S).group().replace('safe_family_identity()', '_fixture_original_family()', 1)
        shutil.rmtree(self.cache); self.cache.mkdir()
        body = original + '''
safe_family_identity() {
  if [ -d "$LUOSHU_TASK_SCOPE_TMPDIR/switch-cache-$EXPECTED/tree/system/fonts" ]; then
    printf late-edit >> "$USER_FONTS_DIR/Demo-Bold.ttf"
  fi
  _fixture_original_family "$@"
}
safe_switch_cache_store "$FONT" Demo "$EXPECTED"
'''
        self.assertNotEqual(self.shell(body, EXPECTED=expected).returncode, 0)
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_python_policy_inventory_partition_and_current_build_changes_invalidate(self):
        for path in (self.module / 'common/coloros_metrics_batch.py',
                     self.module / 'common/font_slot_coverage.py',
                     self.config / 'device_font_inventory.json',
                     self.config / 'device_font_partitions.conf'):
            with self.subTest(path=path.name):
                self.seed_cache()
                with path.open('a') as stream:
                    stream.write('\nchanged\n')
                self.assert_cache_miss()
        self.seed_cache()
        self.assertNotEqual(self.shell('safe_switch_cache_restore "$FONT" Demo',
                                      LUOSHU_BUILD_KEY='new-build').returncode, 0)

    def test_validation_policy_changes_invalidate_only_validation_cache(self):
        self.assertEqual(self.shell('safe_validation_store "$FONT"').returncode, 0)
        with (self.module / 'common/legacy_v14_4/font_coverage.py').open('a') as stream:
            stream.write('\n# stronger validation\n')
        self.assertNotEqual(self.shell('safe_validation_restore "$FONT"').returncode, 0)

    def test_missing_nonregular_and_checksum_failures_never_restore_a_tree(self):
        self.seed_cache()
        helper = self.module / 'common/coloros_metrics_batch.py'
        helper.unlink(); self.assert_cache_miss()
        helper.mkdir(); self.assert_cache_miss()
        helper.rmdir(); helper.write_text('policy')
        self.seed_cache()
        fakebin = self.root / 'bin'; fakebin.mkdir()
        command = fakebin / 'cksum'
        for code in ('exit 1', 'echo malformed', 'echo "0 0 wrong-path"', ':'):
            command.write_text('#!/bin/sh\n' + code + '\n'); command.chmod(0o755)
            for action in ('safe_switch_cache_key', 'safe_switch_cache_ready', 'safe_switch_cache_restore'):
                result = self.shell(action + ' "$FONT" Demo', PATH=str(fakebin) + ':' + os.environ['PATH'])
                self.assertNotEqual(result.returncode, 0, (action, code))
        command.unlink()
        command = fakebin / 'sha256sum'
        for code in ('exit 1', ':', 'echo nonhex', 'echo ' + 'a' * 32):
            command.write_text('#!/bin/sh\n' + code + '\n'); command.chmod(0o755)
            for action in ('safe_switch_cache_key', 'safe_switch_cache_ready', 'safe_switch_cache_restore'):
                result = self.shell(action + ' "$FONT" Demo', PATH=str(fakebin) + ':' + os.environ['PATH'])
                self.assertNotEqual(result.returncode, 0, (action, code))

    def test_malformed_cache_metadata_is_never_reused(self):
        self.seed_cache()
        config = self.cache / self.key() / 'cache.conf'
        original = config.read_text()
        for altered in ('schema=unknown\nfont=Demo\n', original.replace('font=Demo', 'font=Other'),
                        original.replace('mapperIdentity=', 'unrecognized='), original + 'font=Demo\n'):
            with self.subTest(metadata=altered.splitlines()[0]):
                config.write_text(altered)
                self.assert_cache_miss()


class LegacyAliasValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.font = self.root / 'font.ttf'
        source = (ROOT / 'common/legacy_v14_4/rom_adapters.sh').read_text()
        self.code = '\n'.join(re.search(r'^' + name + r'\(\) \{.*?^\}', source,
                                       re.M | re.S).group()
                              for name in ('_font_file_size_fast', '_verify_font_copy'))

    def run_check(self, override=''):
        return subprocess.run(['sh', '-c', self.code + '\n_log_step() { :; }\n' + override +
                               '\n_verify_font_copy "$1"', 'fixture', str(self.font)],
                              capture_output=True, text=True)

    def test_size_threshold_missing_empty_and_short_files_remain_rejected(self):
        self.assertNotEqual(self.run_check().returncode, 0)
        for size in (0, 1, 1023, 1024, 32768):
            with self.subTest(size=size):
                self.font.write_bytes(b'F' * size)
                self.assertEqual(self.run_check().returncode == 0, size >= 1024)

    def test_metadata_path_does_not_invoke_wc_and_fallback_is_retained(self):
        self.font.write_bytes(b'F' * 4096)
        self.assertEqual(self.run_check('wc() { exit 7; }').returncode, 0)
        self.assertEqual(self.run_check('stat() { return 1; }\ntoybox() { return 1; }').returncode, 0)
        self.assertNotEqual(self.run_check('stat() { echo unknown; }').returncode, 0)


if __name__ == '__main__':
    unittest.main()
