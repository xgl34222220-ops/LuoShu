#!/usr/bin/env python3
"""Filesystem regressions for the real staging/cache shell functions.

No Root, mounts or Android service commands run. Tiny marker files model payload
identity, not valid fonts; glyph generation is tested by font_instance_contract.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(os.environ.get('LUOSHU_TEST_SOURCE_ROOT', Path(__file__).resolve().parents[1]))
SAFE = ROOT / 'common/legacy_v14_4/font_switch_safe.sh'
CLONE = ROOT / 'common/legacy_v14_4/payload_clone.sh'
PRIVATE = ROOT / 'common/private_payload.sh'
PROVENANCE = ROOT / 'common/font_provenance.sh'


def functions(text: str) -> str:
    # Shell functions close at column zero in these files. Exclude all top-level
    # initialization, traps and CLI dispatch so the fixture cannot touch a phone.
    return '\n'.join(re.findall(r'^[A-Za-z_][A-Za-z_0-9]*\(\) [({]\n.*?^[})]$',
                                text, flags=re.M | re.S))


class FontStageChainTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='luoshu stage ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.config = self.module / 'config'
        self.legacy = self.module / 'common/legacy_v14_4'
        self.config.mkdir(parents=True)
        self.legacy.mkdir(parents=True)
        self.source = self.root / 'fonts/Demo.ttf'
        self.source.parent.mkdir()
        self.source.write_text('source-font-generation-A')
        self.write('config/device_font_inventory.json', '{"state":"ready","slots":{}}')
        self.write('config/device_font_partitions.conf', 'aurora_product\n')
        self.write('common/font_instance.py', '# instance A\n')
        self.write('common/font_metrics_normalize.py', '# metrics A\n')
        self.write('common/legacy_v14_4/font_coverage.py', '# coverage A\n')
        self.write('common/legacy_v14_4/rom_adapters.sh', '# mapper A\n')
        self.write('.luoshu-payload/system/fonts/Old.ttf', 'old-live-font')
        self.write('.luoshu-payload/aurora_product/fonts/OldClock.ttf', 'old-live-clock')
        self.write('.luoshu-payload/aurora_product/etc/fonts_customization.xml',
                   '<familyset><font>LuoShu-400.ttf</font></familyset>')
        self.write('.luoshu-payload/aurora_product/etc/keep.xml', '<settings>luoshu</settings>')
        self.write('.luoshu-payload/system/bin/keep', 'retain-binary-marker')
        self.write('.luoshu-payload/config/fonts/notes.txt', 'not-a-partition')
        (self.module / 'logs').mkdir()
        self.library = self.root / 'functions.sh'
        text = SAFE.read_text()
        self.library.write_text(functions(CLONE.read_text()) + '\n' +
                                functions(PROVENANCE.read_text()) + '\n' + functions(text))
        self.schema = re.search(r'^SWITCH_CACHE_SCHEMA="([^"]+)"', text, re.M).group(1)
        self.env = dict(os.environ, MODDIR=str(self.module), MODULE_DIR=str(self.module),
                        CONFIG_DIR=str(self.config), LEGACY_DIR=str(self.legacy),
                        USER_FONTS_DIR=str(self.source.parent), USER_ROOT=str(self.source.parent.parent),
                        LIVE_PAYLOAD=str(self.module / '.luoshu-payload'),
                        STAGE_PAYLOAD=str(self.module / '.luoshu-payload-stage.fixture'),
                        NEXT_PAYLOAD=str(self.module / '.luoshu-payload-next'),
                        NEXT_STATE=str(self.config / 'font-payload-next.conf'),
                        ACTIVE_FONT_CONF=str(self.config / 'active_font.conf'),
                        LEGACY_MODE_CONF=str(self.config / 'font_runtime_legacy_v14_4.conf'),
                        TEXT_REBOOT_REQUIRED=str(self.config / 'text_reboot_required.conf'),
                        SWITCH_CACHE_ROOT=str(self.config / 'safe-switch-cache'),
                        SWITCH_VALIDATION_CACHE_ROOT=str(self.config / 'safe-switch-validation'),
                        SWITCH_CACHE_SCHEMA=self.schema, SWITCH_CACHE_MAX_ENTRIES='3',
                        SWITCH_CACHE_MAX_KB='786432', LOG_FILE=str(self.module / 'logs/fontswitch.log'),
                        SOURCE=str(self.source), IS_HYPEROS='false', IS_COLOROS='false',
                        PROGRESS_FILE='', LIBRARY=str(self.library), PRIVATE=str(PRIVATE),
                        CP_BIN=shutil.which('cp'), WORK=str(self.root))
        for name in ('REALMOD', 'LUOSHU_REAL_MODDIR', 'SAFE_STAGE_ENGINE', 'SAFE_STAGE_KEY'):
            self.env.pop(name, None)

    def write(self, relative: str, content: str) -> Path:
        path = self.module / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def run_sh(self, code: str, check: bool = True, **env):
        result = subprocess.run(['sh', '-eu', '-c', '. "$LIBRARY"\n' + code],
                                env={**self.env, **env}, text=True, capture_output=True,
                                timeout=20)
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def digest(self, function='safe_switch_cache_key') -> str:
        return self.run_sh(f'{function} "$SOURCE" Demo').stdout.strip()

    def seed_cache(self) -> None:
        self.run_sh('''
            safe_stage_begin "$SOURCE" Demo
            mkdir -p "$STAGE_PAYLOAD/system/fonts" "$STAGE_PAYLOAD/aurora_product/fonts"
            cp "$SOURCE" "$STAGE_PAYLOAD/system/fonts/Ready.ttf"
            cp "$SOURCE" "$STAGE_PAYLOAD/aurora_product/fonts/ReadyClock.ttf"
            safe_switch_cache_store "$SOURCE" Demo
        ''')

    def test_partition_manifest_is_consumed(self):
        parts = self.run_sh('safe_partition_list').stdout.split()
        self.assertIn('aurora_product', parts)
        self.assertIn('system', parts)

    def test_partition_manifest_deduplicates(self):
        self.write('config/device_font_partitions.conf', 'system\naurora_product\naurora_product\n')
        parts = self.run_sh('safe_partition_list').stdout.split()
        self.assertEqual(parts.count('aurora_product'), 1)
        self.assertEqual(parts.count('system'), 1)

    def test_unterminated_manifest_line_is_not_lost(self):
        self.write('config/device_font_partitions.conf', 'aurora_product')
        self.assertIn('aurora_product', self.run_sh('safe_partition_list').stdout.split())

    def test_partition_policy_matches_mount_layer(self):
        self.write('config/device_font_partitions.conf',
                   'aurora_product\nproc\ndata\ncache\nconfig\n../outside\n1bad\n_bad\nbad-name\n')
        expected = self.run_sh('. "$PRIVATE"; luoshu_private_partitions').stdout.split()
        self.assertEqual(self.run_sh('safe_partition_list').stdout.split(), expected)

    def test_manifest_is_data_not_shell(self):
        self.write('config/device_font_partitions.conf',
                   f'$(touch {self.root}/executed)\n../../escape\nproc\nconfig\naurora_product\n')
        actual = self.run_sh('safe_partition_list').stdout.split()
        self.assertNotIn('proc', actual)
        self.assertNotIn('config', actual)
        self.assertIn('aurora_product', actual)
        self.assertFalse((self.root / 'executed').exists())

    def test_clone_omits_scanned_partition_fonts(self):
        self.run_sh('luoshu_clone_payload_metadata "$LIVE_PAYLOAD" "$STAGE_PAYLOAD"')
        stage = Path(self.env['STAGE_PAYLOAD'])
        self.assertFalse((stage / 'system/fonts').exists())
        self.assertFalse((stage / 'aurora_product/fonts').exists())
        self.assertTrue((stage / 'aurora_product/etc/keep.xml').is_file())

    def test_clone_omits_old_generated_font_config(self):
        self.run_sh('luoshu_clone_payload_metadata "$LIVE_PAYLOAD" "$STAGE_PAYLOAD"')
        self.assertFalse((Path(self.env['STAGE_PAYLOAD']) / 'aurora_product/etc/fonts_customization.xml').exists())

    def test_clone_preserves_nonfont_data(self):
        self.run_sh('luoshu_clone_payload_metadata "$LIVE_PAYLOAD" "$STAGE_PAYLOAD"')
        stage = Path(self.env['STAGE_PAYLOAD'])
        self.assertEqual((stage / 'system/bin/keep').read_text(), 'retain-binary-marker')
        self.assertEqual((stage / 'config/fonts/notes.txt').read_text(), 'not-a-partition')

    def test_clone_keeps_unmodified_stock_font_config(self):
        self.write('.luoshu-payload/aurora_product/etc/fonts.xml', '<familyset><font>Stock.ttf</font></familyset>')
        self.run_sh('luoshu_clone_payload_metadata "$LIVE_PAYLOAD" "$STAGE_PAYLOAD"')
        self.assertTrue((Path(self.env['STAGE_PAYLOAD']) / 'aurora_product/etc/fonts.xml').is_file())

    def test_mix_real_module_wins_over_compatibility_directory(self):
        runtime = self.module / '.legacy-v14-runtime'
        runtime.mkdir()
        self.run_sh('luoshu_clone_payload_metadata "$LIVE_PAYLOAD" "$STAGE_PAYLOAD"',
                    REALMOD=str(self.module), MODULE_DIR=str(runtime), MODDIR=str(runtime))
        self.assertFalse((Path(self.env['STAGE_PAYLOAD']) / 'aurora_product/fonts').exists())

    def test_clone_copy_fallback_keeps_live_unchanged(self):
        live = self.module / '.luoshu-payload'
        before = {str(p.relative_to(live)): p.read_bytes() for p in live.rglob('*') if p.is_file()}
        self.run_sh('''
            cp() { if [ "$1" = -al ]; then return 1; fi; "$CP_BIN" "$@"; }
            luoshu_clone_payload_metadata "$LIVE_PAYLOAD" "$STAGE_PAYLOAD"
        ''')
        after = {str(p.relative_to(live)): p.read_bytes() for p in live.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((Path(self.env['STAGE_PAYLOAD']) / 'aurora_product/fonts').exists())

    def test_same_inputs_retain_cache_key(self):
        self.assertEqual(self.digest(), self.digest())

    def test_instancer_change_invalidates_cache(self):
        before = self.digest()
        self.write('common/font_instance.py', '# instance B\n')
        self.assertNotEqual(before, self.digest())

    def test_metrics_change_invalidates_cache(self):
        before = self.digest()
        self.write('common/font_metrics_normalize.py', '# metrics B\n')
        self.assertNotEqual(before, self.digest())

    def test_added_and_deleted_helpers_invalidate_cache(self):
        before = self.digest()
        helper = self.write('common/font_extra.py', '# new dependency\n')
        self.assertNotEqual(before, self.digest())
        helper.unlink()
        self.assertEqual(before, self.digest())

    def test_partition_only_change_invalidates_cache(self):
        before = self.digest()
        self.write('config/device_font_partitions.conf', 'aurora_product\nextra_fonts\n')
        self.assertNotEqual(before, self.digest())

    def test_inventory_change_invalidates_cache(self):
        before = self.digest()
        self.write('config/device_font_inventory.json', '{"state":"ready","revision":2}')
        self.assertNotEqual(before, self.digest())

    def test_checker_change_invalidates_validation_cache(self):
        before = self.digest('safe_validation_key')
        self.write('common/legacy_v14_4/font_coverage.py', '# coverage B\n')
        self.assertNotEqual(before, self.digest('safe_validation_key'))

    def test_checksum_read_failure_cannot_be_a_cache_hit(self):
        self.run_sh('''
            cksum() { return 1; }
            if safe_switch_cache_key "$SOURCE" Demo; then exit 1; fi
        ''')

    def test_cache_roundtrip_includes_scanned_partition(self):
        self.seed_cache()
        self.run_sh('rm -rf "$STAGE_PAYLOAD"; safe_stage_begin "$SOURCE" Demo; safe_switch_cache_restore "$SOURCE" Demo')
        output = Path(self.env['STAGE_PAYLOAD']) / 'aurora_product/fonts/ReadyClock.ttf'
        self.assertEqual(output.read_bytes(), self.source.read_bytes())

    def test_old_cache_rejected_after_engine_update(self):
        self.seed_cache()
        self.write('common/font_instance.py', '# instance B\n')
        self.run_sh('''
            safe_stage_begin "$SOURCE" Demo
            if safe_switch_cache_restore "$SOURCE" Demo; then exit 1; fi
        ''')

    def test_cache_store_requires_generation_context(self):
        self.run_sh('''
            mkdir -p "$STAGE_PAYLOAD/system/fonts"
            cp "$SOURCE" "$STAGE_PAYLOAD/system/fonts/Ready.ttf"
            if safe_switch_cache_store "$SOURCE" Demo; then exit 1; fi
        ''')

    def test_engine_change_during_build_rejects_store(self):
        self.run_sh('''
            safe_stage_begin "$SOURCE" Demo
            mkdir -p "$STAGE_PAYLOAD/system/fonts"
            cp "$SOURCE" "$STAGE_PAYLOAD/system/fonts/Ready.ttf"
            printf '# engine changed\n' >> "$MODDIR/common/font_instance.py"
            if safe_switch_cache_store "$SOURCE" Demo; then exit 1; fi
        ''')
        self.assertFalse((self.config / 'safe-switch-cache').exists())

    def test_inventory_change_during_build_rejects_store(self):
        self.run_sh('''
            safe_stage_begin "$SOURCE" Demo
            printf 'other_partition\n' >> "$CONFIG_DIR/device_font_partitions.conf"
            if safe_stage_unchanged "$SOURCE" Demo; then exit 1; fi
        ''')

    def test_source_change_during_build_rejects_store(self):
        self.run_sh('''
            safe_stage_begin "$SOURCE" Demo
            printf 'more-glyphs' >> "$SOURCE"
            if safe_stage_unchanged "$SOURCE" Demo; then exit 1; fi
        ''')

    def test_polling_uses_pinned_engine_identity(self):
        result = self.run_sh('''
            safe_stage_begin "$SOURCE" Demo
            safe_mapper_identity() { echo 'UNEXPECTED_ENGINE_REHASH' >&2; return 1; }
            safe_switch_cache_key "$SOURCE" Demo
            safe_validation_key "$SOURCE"
        ''')
        self.assertNotIn('UNEXPECTED_ENGINE_REHASH', result.stderr)

    def test_partial_link_restore_cleans_before_copy_fallback(self):
        self.seed_cache()
        self.run_sh('''
            rm -rf "$STAGE_PAYLOAD"
            cp() {
                if [ "$1" = -al ]; then
                    mkdir -p "$3"
                    printf 'partial' > "$3/poison.ttf"
                    return 1
                fi
                "$CP_BIN" "$@"
            }
            safe_stage_begin "$SOURCE" Demo
            safe_switch_cache_restore "$SOURCE" Demo
        ''')
        stage = Path(self.env['STAGE_PAYLOAD'])
        self.assertTrue((stage / 'system/fonts/Ready.ttf').is_file())
        self.assertFalse(list(stage.rglob('poison.ttf')))
        self.assertFalse((stage / 'system/fonts/fonts').exists())

    def test_partial_link_store_cleans_before_copy_fallback(self):
        self.run_sh('''
            safe_stage_begin "$SOURCE" Demo
            mkdir -p "$STAGE_PAYLOAD/system/fonts"
            cp "$SOURCE" "$STAGE_PAYLOAD/system/fonts/Ready.ttf"
            cp() {
                if [ "$1" = -al ]; then
                    mkdir -p "$3"
                    printf 'partial' > "$3/poison.ttf"
                    return 1
                fi
                "$CP_BIN" "$@"
            }
            safe_switch_cache_store "$SOURCE" Demo
        ''')
        cache = self.config / 'safe-switch-cache'
        self.assertFalse(list(cache.rglob('poison.ttf')))
        self.assertEqual(len(list(cache.rglob('Ready.ttf'))), 1)

    def switch_fixture(self, extra=''):
        # Override hardware/glyph operations only. Keep real transaction, clone,
        # cache, freshness checks, staging cleanup and next-boot state writes.
        return self.run_sh('''
            lock_acquire() { return 0; }
            validate_global() { return 0; }
            mirror_existing_targets() { return 0; }
            apply_font_by_rom() {
                mkdir -p "$STAGE_PAYLOAD/system/fonts/.luoshu-font-store" "$STAGE_PAYLOAD/aurora_product/fonts"
                cp "$SOURCE" "$STAGE_PAYLOAD/system/fonts/New.ttf"
                cp "$SOURCE" "$STAGE_PAYLOAD/system/fonts/.luoshu-font-store/regular.font"
                cp "$SOURCE" "$STAGE_PAYLOAD/aurora_product/fonts/NewClock.ttf"
            }
        ''' + extra + '\nswitch_font Demo\n', check=False)

    def test_failed_partial_restore_is_cleared_before_rebuild(self):
        result = self.switch_fixture('''
            safe_switch_cache_restore() {
                mkdir -p "$STAGE_PAYLOAD/aurora_product/fonts"
                printf 'stale-cache' > "$STAGE_PAYLOAD/aurora_product/fonts/Stale.ttf"
                return 1
            }
        ''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        nxt = self.module / '.luoshu-payload-next'
        self.assertTrue((nxt / 'aurora_product/fonts/NewClock.ttf').exists())
        self.assertFalse((nxt / 'aurora_product/fonts/Stale.ttf').exists())
        self.assertFalse((nxt / 'aurora_product/fonts/OldClock.ttf').exists())
        self.assertEqual((self.module / '.luoshu-payload/system/fonts/Old.ttf').read_text(), 'old-live-font')

    def test_failed_stage_verification_never_populates_cache(self):
        result = self.switch_fixture('stage_verify() { return 1; }')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.config / 'safe-switch-cache').exists())
        self.assertFalse((self.module / '.luoshu-payload-next').exists())

    def test_changed_inventory_rejects_commit_and_preserves_queued_tree(self):
        self.write('.luoshu-payload-next/system/fonts/Queued.ttf', 'existing-queued-font')
        result = self.switch_fixture('''
            stage_verify() {
                printf 'new_partition\n' >> "$CONFIG_DIR/device_font_partitions.conf"
                return 0
            }
        ''')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.module / '.luoshu-payload-next/system/fonts/Queued.ttf').read_text(), 'existing-queued-font')

    def test_input_change_while_cache_is_saved_still_rejects_commit(self):
        result = self.switch_fixture('''
            safe_switch_cache_store() {
                printf 'changed-before-commit\\n' >> "$SOURCE"
                return 1
            }
        ''')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.module / '.luoshu-payload-next').exists())

    def test_syntax(self):
        for path in (SAFE, CLONE):
            result = subprocess.run(['sh', '-n', path], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
