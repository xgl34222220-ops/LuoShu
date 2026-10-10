#!/usr/bin/env python3
"""App fine-tuning of imported Latin/digits (英数大小 / 英数上下位置).

Both composite engines honour --latin-size/--latin-offset on top of the
automatic alignment; 0/0 must be byte-identical to not passing them. Size grows
around the imported cap centre, offset moves by a percentage of the em, and the
values are part of the fixed and auto-multiweight composite cache keys.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from composite_latin_cjk_alignment_test import ENGINES, box, make_font  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class CompositeManualTuneTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'cjk.ttf'
        self.latin = self.root / 'latin.ttf'
        self.digit = self.root / 'digit.ttf'
        make_font(self.base, cap=740, xh=530, digit=740, overshoot=14, cjk=(-62, 782), family='Base')
        make_font(self.latin, cap=643, xh=510, digit=643, overshoot=0, cjk=None, family='Tech')
        shutil.copyfile(self.latin, self.digit)

    def build(self, engine: str, *extra: str, name: str | None = None) -> Path:
        output = self.root / f'{name or engine}.ttf'
        result = subprocess.run([sys.executable, str(ENGINES[engine]), '--cjk', str(self.base),
                                 '--latin', str(self.latin), '--digit', str(self.digit),
                                 '--output', str(output), *extra], env=os.environ.copy(),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return output

    def boxes(self, path: Path):
        with TTFont(path) as font:
            return {char: box(font, char) for char in 'H1x中'}

    def test_zero_tune_is_byte_identical_to_no_tune(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                plain = self.build(engine, name=f'{engine}-plain').read_bytes()
                zero = self.build(engine, '--latin-size', '0', '--latin-offset', '0',
                                  name=f'{engine}-zero').read_bytes()
                self.assertEqual(plain, zero)

    def test_size_grows_caps_and_digits_around_their_centre(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                auto = self.boxes(self.build(engine, name=f'{engine}-auto'))
                big = self.boxes(self.build(engine, '--latin-size', '10', name=f'{engine}-big'))
                small = self.boxes(self.build(engine, '--latin-size', '-10', name=f'{engine}-small'))
                for char in 'H1':
                    height = auto[char][3] - auto[char][1]
                    centre = (auto[char][1] + auto[char][3]) / 2
                    self.assertAlmostEqual((big[char][3] - big[char][1]) / height, 1.10, delta=0.01)
                    self.assertAlmostEqual((small[char][3] - small[char][1]) / height, 0.90, delta=0.01)
                    self.assertLessEqual(abs((big[char][1] + big[char][3]) / 2 - centre), 2, char)
                    self.assertLessEqual(abs((small[char][1] + small[char][3]) / 2 - centre), 2, char)
                self.assertEqual(big['中'], auto['中'])

    def test_offset_raises_or_lowers_by_percent_of_em(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                auto = self.boxes(self.build(engine, name=f'{engine}-auto'))
                up = self.boxes(self.build(engine, '--latin-offset', '5', name=f'{engine}-up'))
                down = self.boxes(self.build(engine, '--latin-offset', '-3', name=f'{engine}-down'))
                for char in 'H1x':
                    self.assertLessEqual(abs(up[char][1] - (auto[char][1] + 50)), 1, char)
                    self.assertLessEqual(abs(down[char][1] - (auto[char][1] - 30)), 1, char)
                    self.assertLessEqual(abs((up[char][3] - up[char][1]) - (auto[char][3] - auto[char][1])), 1)
                self.assertEqual(up['中'], auto['中'])

    def test_out_of_range_values_are_clamped(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                wild = self.build(engine, '--latin-size', '90', '--latin-offset', '-70', name=f'{engine}-wild')
                capped = self.build(engine, '--latin-size', '15', '--latin-offset', '-10', name=f'{engine}-capped')
                self.assertEqual(wild.read_bytes(), capped.read_bytes())

    def test_shell_tune_key_suffix(self):
        script = '. "$1"; composite_tune_load; printf "%s|%s|%s" "$COMPOSITE_TUNE_SIZE" "$COMPOSITE_TUNE_OFFSET" "$(composite_tune_key_suffix)"'
        proof = ROOT / 'common/legacy_v14_4/composite_cache_proof.sh'
        cases = {(None, None): '0|0|', ('0', '0'): '0|0|', ('', 'x'): '0|0|',
                 ('5', '0'): '5|0|-latin-tune-size=5-offset=0',
                 ('0', '-3'): '0|-3|-latin-tune-size=0-offset=-3',
                 ('40', '-99'): '15|-10|-latin-tune-size=15-offset=-10',
                 ('007', '1;rm'): '7|0|-latin-tune-size=7-offset=0'}
        for (size, offset), expected in cases.items():
            env = {k: v for k, v in os.environ.items() if not k.startswith('LUOSHU_MIX_LATIN_')}
            if size is not None:
                env['LUOSHU_MIX_LATIN_SIZE'] = size
            if offset is not None:
                env['LUOSHU_MIX_LATIN_OFFSET'] = offset
            with self.subTest(size=size, offset=offset):
                result = subprocess.run(['sh', '-c', script, 'sh', str(proof)], env=env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)

    def test_both_cache_paths_key_and_pass_the_tune(self):
        for path, marker in (('common/legacy_v14_4/font_mix_engine.sh', 'full-composite-v8-content-identity%s'),
                             ('common/legacy_v14_4/v143_auto_multiweight_mix.sh', 'auto-multiweight-v4-content-identity%s')):
            with self.subTest(path=path):
                text = (ROOT / path).read_text()
                self.assertIn(marker, text)
                self.assertIn('"$(composite_tune_key_suffix)" | hash_text', text)
                self.assertIn('composite_tune_load', text)
                self.assertIn('--latin-size "$COMPOSITE_TUNE_SIZE" --latin-offset "$COMPOSITE_TUNE_OFFSET"', text)
        router = (ROOT / 'common/legacy_v14_4/mix_router.sh').read_text()
        self.assertIn('export LUOSHU_MIX_LATIN_SIZE=', router)
        self.assertIn('export LUOSHU_MIX_LATIN_OFFSET=', router)
        bridge = (ROOT / 'common/app_bridge.sh').read_text()
        self.assertIn('"${8:-0}" "${9:-0}"', bridge)

    def router_function(self, name: str) -> str:
        import re
        source = (ROOT / 'common/legacy_v14_4/mix_router.sh').read_text()
        return re.search(r'\n' + name + r'\(\) \{.*?\n\}\n', source, re.S).group(0)

    def test_router_sanitises_request_and_reports_committed_tune(self):
        block = '\n'.join(line for line in self.router_function('prepare_mix_stage').splitlines()
                          if '_pms_' in line and 'printf' not in line)
        script = 'set -- c l d a b c "$@"\n' + block + '\necho "$_pms_size $_pms_offset"'
        for args, expected in ((['5', '-3'], '5 -3'), (['20', '-50'], '15 -10'),
                               (['x', '1;2'], '0 0'), (['', ''], '0 0'), ([], '0 0')):
            with self.subTest(args=args):
                result = subprocess.run(['sh', '-c', script, 'sh', *args], capture_output=True, text=True)
                self.assertEqual(result.stdout.strip(), expected, result.stderr)
        config = self.root / 'config'
        config.mkdir()
        (config / 'active_font.conf').write_text('mix\n')
        (config / 'axes_mix.conf').write_text('cjk=C\nlatin=L\ndigit=D\n')
        handler = ''.join(self.router_function(name) for name in ('read_value', 'json_escape_router', 'mix_config_json_fast'))
        handler += '\nREALMOD="$1"; ACTIVE_CONF="$1/config/active_font.conf"; mix_config_json_fast\n'
        for tune, expected in (('', (0, 0)), ('latinSize=-4\nlatinOffset=6\n', (-4, 6)),
                               ('latinSize=9;x\nlatinOffset=\n', (0, 0))):
            with self.subTest(tune=tune):
                if tune:
                    (config / 'mix_tune.conf').write_text(tune)
                result = subprocess.run(['sh', '-c', handler, 'sh', str(self.root)], capture_output=True, text=True)
                data = json.loads(result.stdout)['data']
                self.assertEqual((data['latinSize'], data['latinOffset']), expected)


class FixedEngineTuneCacheTest(unittest.TestCase):
    """The real fixed composite driver regenerates when the tune changes."""

    def setUp(self):
        from legacy_mix_fixed_cache_identity_test import FixedCompositeCacheIdentity
        self.harness = FixedCompositeCacheIdentity('test_real_cold_warm_and_missing_receipt')
        self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)

    def test_tune_is_part_of_the_cache_key(self):
        h = self.harness
        default, default_font = h.good()
        original = default_font.read_bytes()
        self.assertEqual(h.count(h.calls), 1)
        tuned_env = {'LUOSHU_MIX_LATIN_SIZE': '8', 'LUOSHU_MIX_LATIN_OFFSET': '2'}
        tuned, tuned_font = h.good(extra_env=tuned_env)
        self.assertEqual(tuned.data['cacheHit'], 'false')
        self.assertEqual(h.count(h.calls), 2)
        self.assertNotEqual(tuned_font, default_font)
        self.assertNotEqual(tuned_font.read_bytes(), original)
        warm, again = h.good(extra_env=tuned_env)
        self.assertEqual((warm.data['cacheHit'], again), ('true', tuned_font))
        back, back_font = h.good(extra_env={'LUOSHU_MIX_LATIN_SIZE': '0', 'LUOSHU_MIX_LATIN_OFFSET': '0'})
        self.assertEqual((back.data['cacheHit'], back_font), ('true', default_font))
        self.assertEqual(back_font.read_bytes(), original)
        self.assertEqual(h.count(h.calls), 2)


if __name__ == '__main__':
    unittest.main()
