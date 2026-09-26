#!/usr/bin/env python3
"""Composite tasks retain sources; only the inventory engine creates font targets."""
from pathlib import Path
import os
import json
import sys
from fontTools.ttLib import TTFont
from legacy_composite_layout_test import fixture, bounds
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / 'common/legacy_v14_4'


def functions_only(path):
    return path.read_text().split('\ncase "${1:-', 1)[0]


class InventoryMixSourceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.real = self.base / 'module'
        self.runtime = self.real / '.legacy-v14-runtime'
        self.stage = self.real / '.luoshu-mix-stage'
        self.live = self.real / '.luoshu-payload'
        for tree in (self.stage, self.live):
            (tree / 'system/fonts').mkdir(parents=True)
        for name in ('config', 'logs', 'cache', 'common'):
            (self.runtime / name).mkdir(parents=True)
        (self.runtime / 'system').symlink_to(self.stage / 'system', target_is_directory=True)
        self.live_font = self.live / 'system/fonts/ActualDeviceSans.ttf'
        self.live_font.write_bytes(b'previous-live-font')
        self.source = self.base / 'source.font'
        fixture(self.source)
        helper = self.real / 'common/mix_source_manifest.py'
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.symlink_to(ROOT / 'common/mix_source_manifest.py')
        python = self.runtime / 'common/python/bin/luoshu-python'
        python.parent.mkdir(parents=True)
        python.write_text(f'#!/bin/sh\nunset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH\nexec {sys.executable} "$@"\n')
        python.chmod(0o755)
        self.env = dict(os.environ, MODDIR=str(self.runtime), LUOSHU_REAL_MODDIR=str(self.real),
                        LUOSHU_MIX_REQUEST_ID='source-test',
                        LUOSHU_MIX_MANIFEST=str(self.stage / '.luoshu-mix-generation.conf'))

    def run_shell(self, code, *args):
        result = subprocess.run(['sh', '-c', code, 'sh', *map(str, args)], env=self.env,
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.live_font.read_bytes(), b'previous-live-font')
        return result

    def test_fixed_apply_preserves_single_source_and_manifest(self):
        code = functions_only(LEGACY / 'font_mix_engine.sh') + r'''
find_family_file() { printf '%s\n' "$1"; }
validate_source() { [ -s "$1" ]; }
build_composite_file() {
    COMPOSITE_RESULT="$1"
    COMPOSITE_OUTPUT_HASH=$(composite_hash_file "$1")
}
apply_mix "$1" "$1" "$1"
'''
        self.run_shell(code, self.source)
        store = self.stage / 'system/fonts/.luoshu-font-store'
        self.assertEqual(sorted(p.name for p in store.iterdir()), ['.luoshu-mix-source-weights.json', 'mix-composite.font'])
        self.assertEqual((store / 'mix-composite.font').read_bytes(), self.source.read_bytes())
        self.assertEqual(list((self.stage / 'system/fonts').glob('*.ttf')), [])
        manifest = (self.stage / '.luoshu-mix-generation.conf').read_text()
        self.assertIn('requestId=source-test\n', manifest)
        self.assertIn('compositeHash=', manifest)

    def test_real_fixed_source_then_mapper_failure_preserves_selection_and_recovery(self):
        # Use the real fixed source generator, source transaction, and router.
        # Only the mapper is failed deliberately, after a valid composite exists.
        for name in ('config', 'logs', 'cache'):
            (self.runtime / name).rename(self.real / name)
            (self.runtime / name).symlink_to(self.real / name, target_is_directory=True)
        config = self.real / 'config'
        active = config / 'active_font.conf'
        active.write_text('previous-font\n')
        previous_mix = b'cjk=Previous\nlatin=Previous\ndigit=Previous\n'
        (config / 'font_mix.conf').write_bytes(previous_mix)
        identity = 'requestId=source-test\ncjk=CJK\nlatin=Latin\ndigit=Digit\n'
        (config / 'mix-stage-next.conf').write_text(identity + 'previousFont=previous-font\npreviousLegacy=false\n')
        (config / 'axes_task.conf').write_text('task=fixed-test\nstate=running\npercent=70\n')
        (self.real / 'common/python').symlink_to(self.runtime / 'common/python', target_is_directory=True)
        (self.real / 'common/mix_stage_watchdog.py').symlink_to(ROOT / 'common/mix_stage_watchdog.py')
        for name in ('composite_font.py', 'composite_layout.py'):
            (self.runtime / 'common' / name).symlink_to(LEGACY / name)
        runner = self.runtime / 'common/luoshu_composite.sh'
        runner.write_text(f'''#!/bin/sh
if [ "$1" = --self-test ]; then printf 'ok\\n'; exit 0; fi
exec {sys.executable} "$MODDIR/common/composite_font.py" "$@"
''')
        latin, digit = self.base / 'latin.ttf', self.base / 'digit.ttf'
        fixture(latin, height=550)
        fixture(digit, height=400)
        self.env.update(LUOSHU_MIX_CONTROLLER_OWNS_COMMIT='true',
                        LUOSHU_MIX_EXPECTED_CJK='CJK', LUOSHU_MIX_EXPECTED_LATIN='Latin',
                        LUOSHU_MIX_EXPECTED_DIGIT='Digit')
        code = functions_only(LEGACY / 'font_mix_engine.sh') + '''
find_family_file() { printf '%s\\n' "$1"; }
apply_mix "$1" "$2" "$3"
'''
        self.run_shell(code, self.source, latin, digit)
        reports = list((self.real / 'cache/full-composite-v8').glob('*.json'))
        self.assertEqual(len(reports), 1)
        self.assertGreater(json.loads(reports[0].read_text())['replaced']['latin'], 0)
        store = self.stage / 'system/fonts/.luoshu-font-store/mix-composite.font'
        committed_source = store.read_bytes()
        self.assertEqual(active.read_text(), 'previous-font\n')
        self.assertEqual((config / 'font_mix.conf').read_bytes(), previous_mix)
        self.assertFalse((config / 'text_reboot_required.conf').exists())
        (self.real / 'common/inventory_font_stage.sh').write_text(
            "printf '通用字体生成失败：injected mapper error\\n' >&2\nexit 7\n")
        result = subprocess.run(['sh', str(LEGACY / 'mix_router.sh'), 'prepare-finalize'],
            env=dict(self.env, MODDIR=str(self.real)), text=True, capture_output=True, timeout=8)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('injected mapper error', result.stdout)
        self.assertEqual(active.read_text(), 'previous-font\n')
        self.assertEqual((config / 'font_mix.conf').read_bytes(), previous_mix)
        self.assertFalse((config / 'text_reboot_required.conf').exists())
        self.assertFalse((self.real / '.luoshu-payload-next').exists())
        self.assertEqual(self.live_font.read_bytes(), b'previous-live-font')
        # A completed source handoff marker survives a crash before backup
        # deletion. Recovery must discard that old source backup, not restore it
        # or alter the public selection after the failed physical mapping.
        backup = self.runtime / '.font-payload-backup.fixture'
        backup.mkdir()
        (backup / 'old.ttf').write_bytes(b'old-source')
        (self.runtime / '.font-payload-commit.ok').write_text('time=1\n')
        result = subprocess.run(['sh', str(LEGACY / 'font_mix_engine.sh'), 'recover'],
            env=self.env, text=True, capture_output=True, timeout=4)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(backup.exists())
        self.assertEqual(store.read_bytes(), committed_source)
        self.assertEqual(active.read_text(), 'previous-font\n')
        self.assertEqual((config / 'font_mix.conf').read_bytes(), previous_mix)
        self.assertFalse((config / 'text_reboot_required.conf').exists())

    def test_auto_worker_hands_all_weights_to_inventory_before_commit(self):
        self.exercise_auto_worker(list(range(100, 1000, 100)))

    def test_auto_worker_only_builds_device_weights_including_550(self):
        self.exercise_auto_worker([400, 550, 700])

    def test_failed_auto_mapping_does_not_change_active_font_or_reboot_flag(self):
        self.exercise_auto_worker([400], fail=True)

    def exercise_auto_worker(self, weights, fail=False):
        sources = self.base / 'weights'
        sources.mkdir()
        for weight in set(weights) | {400}:
            font = sources / f'{weight}.ttf'
            fixture(font)
            with TTFont(font) as loaded:
                loaded['OS/2'].usWeightClass = weight
                for name in loaded.getGlyphOrder():
                    glyph = loaded['glyf'][name]
                    glyph.coordinates = type(glyph.coordinates)((x + (weight // 10 if x > 50 else 0), y)
                                                               for x, y in glyph.coordinates)
                loaded.save(font)
        real_config = self.real / 'config'
        real_config.mkdir(exist_ok=True)
        (real_config / 'device_font_inventory.json').write_text(json.dumps({'slots': {
            str(weight): {'weight': weight} for weight in weights}}))
        (self.real / 'common/mix_inventory_weights.py').symlink_to(ROOT / 'common/mix_inventory_weights.py')
        (self.real / 'common/inventory_font_stage.sh').write_text('exit 0\n')
        self.env['TEST_WEIGHT_SOURCES'] = str(sources)
        self.env['TEST_MAPPER_FAIL'] = '1' if fail else '0'
        active = self.runtime / 'config/active_font.conf'
        active.write_text('previous-font\n')
        self.env['TEST_COMPOSITE_ENGINE'] = str(LEGACY / 'composite_font.py')
        self.env['TEST_HOST_PYTHON'] = sys.executable
        runner = self.runtime / 'common/luoshu_composite.sh'
        runner.write_text('#!/bin/sh\nprintf \'build\\n\' >> "$MODDIR/config/build-calls"\nexec "$TEST_HOST_PYTHON" "$TEST_COMPOSITE_ENGINE" "$@"\n')
        root = self.runtime / 'cache/auto-source-test' 
        task = self.runtime / 'config/axes_task.conf'
        task.write_text(f'''task=auto-test
state=running
cjk=cjk
latin=latin
digit=digit
cjkAxes=wght=400
latinAxes=wght=400
digitAxes=wght=400
cjkMode=fixed
latinMode=auto
digitMode=auto
root={root}
started=1
''')
        code = functions_only(LEGACY / 'v143_auto_multiweight_mix.sh') + r'''
luoshu_provenance_engine_identity() { printf 'test-engine\n'; }
find_best_source() {
    printf 'lookup\n' >> "$MODDIR/config/source-lookups"
    printf '%s/%s.ttf\n' "$TEST_WEIGHT_SOURCES" "$2"
}
font_validate() { FONT_CHECK_VARIABLE=false; FONT_CHECK_FORMAT=TTF; [ -s "$1" ]; }
prepare_compat_payload() {
    [ "${TEST_MAPPER_FAIL:-0}" != 1 ] || return 1
    [ -s "$LUOSHU_MIX_MANIFEST" ] || return 1
    for weight in $(cat "$_root/weights.list"); do
        role=$(anchor_key "$weight")
        [ -s "$MODDIR/system/fonts/.luoshu-font-store/$role.font" ] || return 1
    done
    printf 'prepared\n' >"$MODDIR/config/test-finalize"
}
finalize_compat_payload() { [ -s "$MODDIR/config/test-finalize" ]; }
worker auto-test
'''
        if fail:
            result = subprocess.run(['sh', '-c', code], env=self.env, text=True, capture_output=True, timeout=20)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('state=failed\n', task.read_text())
            self.assertEqual(active.read_text(), 'previous-font\n')
            self.assertFalse((self.runtime / 'config/text_reboot_required.conf').exists())
            self.assertFalse((self.runtime / 'config/font_mix.conf').exists())
            return
        self.run_shell(code)
        store = self.stage / 'system/fonts/.luoshu-font-store'
        keys = dict(zip(range(100, 1000, 100), ('thin', 'extralight', 'light', 'regular', 'medium', 'semibold', 'bold', 'extrabold', 'black')))
        roles = [keys.get(weight, f'wght-{weight}') for weight in weights]
        self.assertEqual(sorted(p.name for p in store.iterdir()), sorted([r + '.font' for r in roles] + ['.luoshu-mix-source-weights.json']))
        data = json.loads((store / '.luoshu-mix-source-weights.json').read_text())
        for weight, role in zip(weights, roles):
            entry = data['sources'][role + '.font']
            self.assertEqual((entry['cjkWeight'], entry['latinWeight'], entry['digitWeight']),
                             (400, weight, weight))
            self.assertEqual(entry['cjkMode'], 'fixed')
            self.assertEqual(entry['latinMode'], 'auto')
            self.assertEqual(entry['latinAxes'], f'wght={weight}')
            with TTFont(store / (role + '.font')) as font:
                self.assertEqual(font['OS/2'].usWeightClass, 400)
        with TTFont(store / 'regular.font') as regular, TTFont(store / 'bold.font') as bold:
            self.assertEqual(bounds(regular, '中'), bounds(bold, '中'))
            self.assertNotEqual(bounds(regular, 'A'), bounds(bold, 'A'))
            self.assertNotEqual(bounds(regular, '1'), bounds(bold, '1'))
        self.assertIn('state=success\n', task.read_text())
        self.assertIn('cjk=cjk\n', (self.runtime / 'config/font_mix.conf').read_text())
        self.assertIn('latin=latin\n', (self.runtime / 'config/font_mix.conf').read_text())
        self.assertIn('mode=auto-multiweight\n', (self.stage / '.luoshu-mix-generation.conf').read_text())
        self.assertFalse(root.exists())
        self.assertEqual(list((self.stage / 'system/fonts').glob('*.ttf')), [])
        self.assertEqual((self.runtime / 'config/build-calls').read_text().splitlines(), ['build'] * len(weights))
        self.assertEqual(len((self.runtime / 'config/source-lookups').read_text().splitlines()), 1 + 2 * len(weights))
        self.run_shell(code)
        self.assertEqual((self.runtime / 'config/build-calls').read_text().splitlines(), ['build'] * len(weights))
        self.assertIn('state=success\n', task.read_text())

    def test_auto_missing_weight_does_not_destroy_previous_stage(self):
        old = self.stage / 'system/fonts/previous.ttf'
        old.write_bytes(b'previous-stage')
        source = self.base / 'incomplete/fonts'
        source.mkdir(parents=True)
        (source / 'LuoShuAutoMix-Thin.otf').write_bytes(b'only-one-weight')
        code = functions_only(LEGACY / 'v143_auto_multiweight_mix.sh') + '\n! stage_auto_sources "$1"\n'
        self.run_shell(code, source.parent)
        self.assertEqual(old.read_bytes(), b'previous-stage')

    def test_public_entry_routes_start_status_recover_without_loading_rom(self):
        router = self.real / 'common/legacy_v14_4/mix_router.sh'
        router.parent.mkdir(parents=True)
        router.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        env = dict(os.environ, MODDIR=str(self.real))
        entry = ROOT / 'common/font_mix.sh'
        for args, expected in ((['start', 'CJK', 'Latin', 'Digit'], 'start\nCJK\nLatin\nDigit\n'),
                               (['status'], 'config\n'), (['status', 'task1'], 'status\ntask1\n'),
                               (['recover'], 'recover\n')):
            result = subprocess.run(['sh', str(entry), *args], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, expected)

    def test_worker_restores_matching_axes_and_explicit_values_win(self):
        router = self.real / 'common/legacy_v14_4/mix_router.sh'
        router.parent.mkdir(parents=True, exist_ok=True)
        router.write_text('''#!/bin/sh
case "$1" in
start) printf '%s\\n' "$@" > "$MODDIR/request-args"
       printf '{"status":"ok","data":{"task":"restored"}}\\n' ;;
status) printf '{"status":"ok","data":{"state":"success"}}\\n' ;;
esac
''')
        config = self.real / 'config'
        config.mkdir(exist_ok=True)
        (config / 'axes_mix.conf').write_text('''cjk=CJK
latin=Latin
digit=Digit
cjkAxes=wght=450,wdth=90
latinAxes=wght=550
digitAxes=wght=650
cjkMode=fixed
latinMode=auto
digitMode=fixed
''')
        env = dict(os.environ, MODDIR=str(self.real))
        entry = ROOT / 'common/font_mix.sh'
        args = ['worker', 'old-task', 'CJK', 'Latin', 'Digit', '1']
        result = subprocess.run(['sh', str(entry), *args], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.real / 'request-args').read_text().splitlines(),
                         ['start', 'CJK', 'Latin', 'Digit', 'wght=450,wdth=90', 'wght=550', 'wght=650',
                          'fixed', 'auto', 'fixed'])
        result = subprocess.run(['sh', str(entry), *args, 'wght=600', 'wght=500', 'wght=300',
                                 'auto', 'fixed', 'auto'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.real / 'request-args').read_text().splitlines()[4:],
                         ['wght=600', 'wght=500', 'wght=300', 'auto', 'fixed', 'auto'])

    def test_mix_bridge_honors_saved_explicit_modes(self):
        common = self.runtime / 'common'
        (common / 'v142_weighted_mix.sh').write_text('exit 99\n')
        (common / 'v143_auto_multiweight_mix.sh').write_text('printf "%s\\n" "$@"\n')
        (common / 'font_role_check.sh').write_text('exit 0\n')
        (common / 'mix_weight_mode.sh').write_text('infer_mix_weight_mode() { echo auto; }\n')
        result = subprocess.run(['sh', str(LEGACY / 'v14_mix.sh'), 'start', 'CJK', 'Latin', 'Digit',
                                 'wght=400', 'wght=550', 'wght=600', 'fixed', 'auto', 'fixed'],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-3:], ['fixed', 'auto', 'fixed'])

    def test_direct_legacy_worker_cannot_write_live(self):
        env = dict(os.environ, MODDIR=str(self.real))
        env.pop('LUOSHU_REAL_MODDIR', None)
        for name in ('v142_weighted_mix.sh', 'v143_auto_multiweight_mix.sh', 'font_mix_engine.sh'):
            result = subprocess.run(['sh', str(LEGACY / name), 'worker', 'old-task'],
                                    env=env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('隔离暂存目录', result.stdout)
            self.assertEqual(self.live_font.read_bytes(), b'previous-live-font')


if __name__ == '__main__':
    unittest.main()
