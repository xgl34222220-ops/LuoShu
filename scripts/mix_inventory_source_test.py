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

    def test_auto_worker_hands_all_weights_to_inventory_before_commit(self):
        sources = self.base / 'weights'
        sources.mkdir()
        for weight in range(100, 1000, 100):
            font = sources / f'{weight}.ttf'
            fixture(font)
            with TTFont(font) as loaded:
                loaded['OS/2'].usWeightClass = weight
                for name in loaded.getGlyphOrder():
                    glyph = loaded['glyf'][name]
                    glyph.coordinates = type(glyph.coordinates)((x + (weight // 10 if x > 50 else 0), y)
                                                               for x, y in glyph.coordinates)
                loaded.save(font)
        self.env['TEST_WEIGHT_SOURCES'] = str(sources)
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
find_best_source() { printf '%s/%s.ttf\n' "$TEST_WEIGHT_SOURCES" "$2"; }
font_validate() { FONT_CHECK_VARIABLE=false; FONT_CHECK_FORMAT=TTF; [ -s "$1" ]; }
prepare_compat_payload() {
    [ -s "$LUOSHU_MIX_MANIFEST" ] || return 1
    for role in thin extralight light regular medium semibold bold extrabold black; do
        [ -s "$MODDIR/system/fonts/.luoshu-font-store/$role.font" ] || return 1
    done
    printf 'prepared\n' >"$MODDIR/config/test-finalize"
}
finalize_compat_payload() { [ -s "$MODDIR/config/test-finalize" ]; }
worker auto-test
'''
        self.run_shell(code)
        store = self.stage / 'system/fonts/.luoshu-font-store'
        roles = ('thin', 'extralight', 'light', 'regular', 'medium', 'semibold', 'bold', 'extrabold', 'black')
        self.assertEqual(sorted(p.name for p in store.iterdir()), sorted([r + '.font' for r in roles] + ['.luoshu-mix-source-weights.json']))
        data = json.loads((store / '.luoshu-mix-source-weights.json').read_text())
        for weight, role in zip(range(100, 1000, 100), roles):
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
        self.assertEqual((self.runtime / 'config/build-calls').read_text().splitlines(), ['build'] * 9)
        self.run_shell(code)
        self.assertEqual((self.runtime / 'config/build-calls').read_text().splitlines(), ['build'] * 9)
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
