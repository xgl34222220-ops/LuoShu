#!/usr/bin/env python3
"""Real fixed composite driver, fonts, validation, mapper and next transaction.

Only the embedded ARM launcher is adapted to host Python. Counter/race/hold
wrappers run the real generator, validator and mv before observing their result.
No device, live mount, fake font validator or fake mapper is used.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

import fontTools
from fontTools.ttLib import TTFont, TTCollection
from fontTools.pens.ttGlyphPen import TTGlyphPen

from legacy_mix_fixed_prepare_reuse_test import variable_font

ROOT = Path(__file__).resolve().parents[1]
ENGINE = Path(os.environ.get('LUOSHU_FIXED_CACHE_TEST_ENGINE', ROOT / 'common/legacy_v14_4/font_mix_engine.sh'))
HOST_SITE = str(Path(fontTools.__file__).resolve().parent.parent)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def values(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines() if '=' in line) if path.exists() else {}


def ink(path, char='A'):
    with TTFont(path, recalcTimestamp=False) as font:
        glyph = font['glyf'][font.getBestCmap()[ord(char)]]
        return (glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax)


class FixedCompositeCacheIdentity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='luoshu-fixed-proof-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.public = self.root / 'public'
        common = self.module / 'common'
        shutil.copytree(ROOT / 'common', common, ignore=shutil.ignore_patterns('python', '__pycache__'))
        shutil.copyfile(ENGINE, common / 'legacy_v14_4/font_mix_engine.sh')
        (common / 'font_live_switch.sh').unlink()
        (self.module / 'module.prop').write_text('id=LuoShu\nversion=fixed-proof-test\n')
        (common / 'python/bin').mkdir(parents=True)
        (common / 'python/bin/luoshu-python').write_text(
            '#!/bin/sh\nunset PYTHONHOME LD_LIBRARY_PATH\n'
            'PYTHONPATH="$FIXED_HOST_SITE"; export PYTHONPATH\nexec "$FIXED_HOST_PYTHON" "$@"\n')
        (common / 'python/bin/luoshu-python').chmod(0o755)
        self.calls = self.root / 'generator-calls'
        self.validations = self.root / 'validator-calls'
        self.ink_checks = self.root / 'ink-check-calls'
        self.ready = self.root / 'hold-ready'
        self.runner = common / 'luoshu_composite.sh'
        self.runner.write_text('''#!/bin/sh
if [ "${1:-}" = --self-test ]; then exec "$MODDIR/common/python/bin/luoshu-python" -c 'import fontTools; print("ok")'; fi
if [ "${1:-}" = --validate-output ]; then
    printf 'validate-ink\\n' >> "$FIXED_INK_CHECKS"
    exec "$MODDIR/common/python/bin/luoshu-python" "$MODDIR/common/composite_font.py" "$@"
fi
printf 'run\\n' >> "$FIXED_GENERATOR_CALLS"
"$MODDIR/common/python/bin/luoshu-python" "$MODDIR/common/composite_font.py" "$@" || exit $?
if [ -n "${FIXED_MUTATE_AFTER_GEN:-}" ]; then printf '\\n# changed after real generation\\n' >> "$FIXED_MUTATE_AFTER_GEN"; fi
if [ "${FIXED_DAMAGE_OUTPUT:-0}" = 1 ]; then
    while [ "$#" -gt 0 ]; do [ "$1" != --output ] || { shift; printf damaged > "$1"; break; }; shift; done
fi
if [ "${FIXED_HOLD:-0}" = 1 ]; then printf '%s\\n' "$$" > "$FIXED_HOLD_READY"; exec sleep 30; fi
''')
        validator = common / 'legacy_v14_4/font_check.sh'
        actual = validator.read_text().replace('font_validate() {', 'fixed_actual_font_validate() {', 1)
        validator.write_text(actual + '\nfont_validate() { printf \'%s\\n\' "$1" >> "$FIXED_VALIDATOR_CALLS"; fixed_actual_font_validate "$@"; }\n')
        # These are the same links made by the actual compatibility router.
        for name in ('util_functions.sh', 'font_check.sh', 'rom_adapters.sh', 'composite_font.py',
                     'composite_layout.py', 'composite_cache_proof.sh'):
            target = common / name
            if target.exists() or target.is_symlink():
                target.unlink()
            target.symlink_to(common / 'legacy_v14_4' / name)
        # The real compatibility runtime intentionally has no mount helpers.
        (common / 'mount_compat.sh').write_text('# compatibility staging only\n')
        (self.public / 'fonts').mkdir(parents=True)
        self.sources = []
        for family, top in (('CJK', 700), ('Latin', 820), ('Digit', 780)):
            path = self.public / 'fonts' / f'{family}-Regular.ttf'
            variable_font(path, top)
            with TTFont(path, recalcTimestamp=False) as font:
                del font['fvar']; del font['gvar']; font.save(path)
            self.sources.append(path)
        self.scope_tmp = self.root / 'direct-owned-temp'
        self.scope_tmp.mkdir()
        self.env = {**os.environ, 'MODDIR': str(self.module), 'LUOSHU_REAL_MODDIR': str(self.module),
                    'LUOSHU_PUBLIC_DIR': str(self.public), 'LUOSHU_TASK_SCOPE_TMPDIR': str(self.scope_tmp),
                    'LUOSHU_TASK_SCOPE_PYTHON': sys.executable, 'LUOSHU_RUNTIME_PATHS_PYTHON': sys.executable,
                    'FIXED_HOST_PYTHON': sys.executable, 'FIXED_HOST_SITE': HOST_SITE,
                    'FIXED_GENERATOR_CALLS': str(self.calls), 'FIXED_VALIDATOR_CALLS': str(self.validations),
                    'FIXED_INK_CHECKS': str(self.ink_checks),
                    'FIXED_HOLD_READY': str(self.ready), 'PYTHONDONTWRITEBYTECODE': '1',
                    'LUOSHU_MIX_TASK_TIMEOUT': '15', 'LUOSHU_MIX_MONITOR_TIMEOUT': '20'}
        self.cache = self.module / '.luoshu-state/cache/full-composite-v7'
        definitions = (common / 'legacy_v14_4/font_mix_engine.sh').read_text().split('case "${1:-status}" in', 1)[0]
        (common / 'fixed-definitions.sh').write_text(definitions)
        self.driver = self.root / 'driver.sh'
        self.driver.write_text('''#!/bin/sh
. "$MODDIR/common/fixed-definitions.sh" || exit $?
build_composite_file "$1" "$2" "$3" || exit $?
printf 'output=%s\\nreport=%s\\ncacheHit=%s\\nsha256=%s\\n' "$COMPOSITE_RESULT" "$COMPOSITE_REPORT" "$COMPOSITE_CACHE_HIT" "$COMPOSITE_OUTPUT_HASH"
''')
        self.sentinel_file = self.root / 'outside-owned-temp'
        self.sentinel_file.write_text('preserved')
        self.addCleanup(self.cancel_owned_scopes)

    def cancel_owned_scopes(self):
        for owner in (self.module / '.luoshu-state/tasks').glob('*.owner.json'):
            record = json.loads(owner.read_text())
            subprocess.run([sys.executable, str(self.module / 'common/task_scope.py'), 'cancel', record['pidfile'], record['task']],
                           env=self.env, capture_output=True, timeout=10)

    def count(self, path):
        return len(path.read_text().splitlines()) if path.exists() else 0

    def build(self, *, sources=None, extra_env=None):
        result = subprocess.run(['sh', str(self.driver), *map(str, sources or self.sources)],
                                env={**self.env, **(extra_env or {})}, capture_output=True, text=True, timeout=15)
        result.data = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        return result

    def good(self, **kwargs):
        result = self.build(**kwargs)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        path = Path(result.data['output'])
        self.assertEqual(digest(path), result.data['sha256'])
        with TTFont(path, recalcTimestamp=False) as font:
            self.assertTrue(set(map(ord, 'Aa09中文')).issubset(font.getBestCmap()))
        return result, path

    def test_real_cold_warm_and_missing_receipt(self):
        first, font = self.good()
        original = font.read_bytes()
        self.assertEqual((self.count(self.calls), self.count(self.validations)), (1, 1))
        receipt = Path(str(font) + '.receipt')
        self.assertEqual(values(receipt)['schema'], 'fixed-composite-receipt-v1')
        warm, again = self.good()
        self.assertEqual(warm.data['cacheHit'], 'true')
        self.assertEqual(again.read_bytes(), original)
        self.assertEqual((self.count(self.calls), self.count(self.validations)), (1, 1))
        receipt.unlink()
        rebuilt, again = self.good()
        self.assertEqual(rebuilt.data['cacheHit'], 'false')
        self.assertEqual(again.read_bytes(), original)
        self.assertEqual((self.count(self.calls), self.count(self.validations)), (2, 2))

    def test_actual_engine_layout_and_runner_contents_invalidate_cache(self):
        _, font = self.good()
        original = font.read_bytes()
        for name in ('composite_font.py', 'composite_layout.py', 'luoshu_composite.sh'):
            with self.subTest(dependency=name):
                before = self.count(self.calls)
                with (self.module / 'common' / name).open('a') as stream:
                    stream.write('\n# real dependency identity changed\n')
                result, again = self.good()
                self.assertEqual(result.data['cacheHit'], 'false')
                self.assertEqual(self.count(self.calls), before + 1)
                self.assertEqual(again.read_bytes(), original)

    def test_real_layout_strategy_changes_ink_and_preserves_cjk(self):
        _, font = self.good()
        old_latin, old_digit, old_han = ink(font), ink(font, '0'), ink(font, '中')
        layout = self.module / 'common/composite_layout.py'
        text = layout.read_text()
        old = 'return scale, max(-limit, min(limit, shift))'
        self.assertIn(old, text)
        layout.write_text(text.replace(old, old + ' + 37.0'))
        result, fresh = self.good()
        self.assertEqual(self.count(self.calls), 2)
        self.assertEqual(ink(fresh), (old_latin[0], old_latin[1] + 37, old_latin[2], old_latin[3] + 37))
        self.assertEqual(ink(fresh, '0'), (old_digit[0], old_digit[1] + 37, old_digit[2], old_digit[3] + 37))
        self.assertEqual(ink(fresh, '中'), old_han)
        self.assertEqual(result.data['cacheHit'], 'false')

    def test_changed_real_input_bytes_invalidate_the_key(self):
        _, font = self.good()
        old = font.read_bytes()
        with TTFont(self.sources[1], recalcTimestamp=False) as source:
            source['head'].fontRevision += 1
            source.save(self.sources[1])
        _, changed = self.good()
        self.assertEqual(self.count(self.calls), 2)
        self.assertNotEqual(font.name, changed.name)
        self.assertEqual(changed.read_bytes(), old)

    def test_nonempty_corrupt_and_valid_changed_payloads_are_rebuilt(self):
        _, font = self.good()
        original = font.read_bytes()
        for damaged in (b'damaged', b'damaged-cache-block' * 456):
            with self.subTest(bytes=len(damaged)):
                font.write_bytes(damaged)
                before = self.count(self.calls)
                result, font = self.good()
                self.assertEqual(self.count(self.calls), before + 1)
                self.assertEqual(result.data['cacheHit'], 'false')
                self.assertEqual(font.read_bytes(), original)
        with TTFont(font, recalcTimestamp=False) as changed:
            changed['head'].fontRevision += 1; changed.save(font)
        self.assertNotEqual(font.read_bytes(), original)
        before = self.count(self.calls)
        _, font = self.good()
        self.assertEqual(self.count(self.calls), before + 1)
        self.assertEqual(font.read_bytes(), original)

    def test_bad_cross_schema_and_symlink_proofs_do_not_reuse(self):
        _, font = self.good()
        original = font.read_bytes()
        receipt = Path(str(font) + '.receipt')
        for mutate in ('cross-schema', 'extra-field', 'receipt-symlink', 'payload-symlink'):
            with self.subTest(mutation=mutate):
                before = self.count(self.calls)
                if mutate == 'cross-schema':
                    receipt.write_text(receipt.read_text().replace('fixed-composite-receipt-v1', 'auto-composite-receipt-v1'))
                elif mutate == 'extra-field':
                    with receipt.open('a') as stream: stream.write('unknown=true\n')
                elif mutate == 'receipt-symlink':
                    receipt.unlink(); receipt.symlink_to(self.sentinel_file)
                else:
                    font.unlink(); font.symlink_to(self.sentinel_file)
                _, font = self.good()
                self.assertEqual(self.count(self.calls), before + 1)
                self.assertEqual(font.read_bytes(), original)
                self.assertEqual(self.sentinel_file.read_text(), 'preserved')

    def test_same_source_preserves_bytes_and_real_validation(self):
        sources = [self.sources[0]] * 3
        first, font = self.good(sources=sources)
        self.assertEqual(self.count(self.calls), 0)
        self.assertEqual(self.count(self.validations), 1)
        self.assertEqual(self.count(self.ink_checks), 1)
        self.assertEqual(font.read_bytes(), self.sources[0].read_bytes())
        warm, font = self.good(sources=sources)
        self.assertEqual(warm.data['cacheHit'], 'true')
        self.assertEqual(self.count(self.validations), 1)
        self.assertEqual(self.count(self.ink_checks), 1)
        self.assertEqual(json.loads(Path(first.data['report']).read_text())['fastPath'], 'same-source')

    def test_blank_same_source_never_publishes_a_receipt(self):
        with TTFont(self.sources[0], recalcTimestamp=False) as font:
            font['glyf'][font.getBestCmap()[ord('B')]] = TTGlyphPen(None).glyph()
            font.save(self.sources[0])
        result = self.build(sources=[self.sources[0]] * 3)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.count(self.calls), 0)
        self.assertEqual(self.count(self.ink_checks), 1)
        self.assertFalse(list(self.cache.glob('*.otf')))
        self.assertFalse(list(self.cache.glob('*.receipt')))
        self.assertFalse(list(self.scope_tmp.iterdir()))
        self.assertEqual(self.sentinel_file.read_text(), 'preserved')

    def test_changed_contract_cannot_reuse_a_warm_receipt_for_blank_glyphs(self):
        layout = self.module / 'common/composite_layout.py'
        checked = layout.read_text()
        # Model the previous exact three-probe acceptance in the fixture only.
        old = '''
def validate_required_ink(font, latin, digits, cjk_probes):
    cmap = font.getBestCmap(); glyphs = font.getGlyphSet(); bounds = {}
    for char in '中A1':
        pen = BoundsPen(glyphs); glyphs[cmap[ord(char)]].draw(pen)
        if pen.bounds is None: raise ValueError('previous three-probe failed')
        bounds[char] = list(pen.bounds)
    return {"bounds": bounds}
'''
        layout.write_text(checked + old)
        with TTFont(self.sources[1], recalcTimestamp=False) as font:
            font['glyf'][font.getBestCmap()[ord('B')]] = TTGlyphPen(None).glyph()
            font.save(self.sources[1])
        first, cached = self.good()
        source_hashes = [digest(path) for path in self.sources]
        warm, _ = self.good()
        self.assertEqual(warm.data['cacheHit'], 'true')
        self.assertEqual(self.count(self.calls), 1)
        old_bytes = cached.read_bytes()
        layout.write_text(checked)
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.count(self.calls), 2)
        self.assertEqual([digest(path) for path in self.sources], source_hashes)
        self.assertEqual(cached.read_bytes(), old_bytes)
        self.assertNotIn('output=', result.stdout)
        self.assertFalse(list(self.scope_tmp.iterdir()))

    def test_same_source_collection_uses_role_aware_generator(self):
        collection = TTCollection()
        collection.fonts = [TTFont(self.sources[0]), TTFont(self.sources[1])]
        path = self.root / 'complete-collection.ttc'
        collection.save(path); collection.close()
        first, output = self.good(sources=[path] * 3)
        self.assertEqual(self.count(self.calls), 1)
        self.assertEqual(self.count(self.ink_checks), 0)
        self.assertNotEqual(output.read_bytes()[:4], b'ttcf')
        warm, _ = self.good(sources=[path] * 3)
        self.assertEqual(warm.data['cacheHit'], 'true')
        self.assertEqual(self.count(self.calls), 1)

    def test_missing_dependencies_cannot_reuse_a_verified_cache(self):
        self.good()
        for name in ('composite_font.py', 'composite_layout.py', 'luoshu_composite.sh'):
            with self.subTest(dependency=name):
                path = (self.module / 'common' / name).resolve()
                old = path.read_bytes(); path.unlink()
                try:
                    result = self.build()
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(self.count(self.calls), 1)
                finally:
                    path.write_bytes(old)

    def test_generation_dependency_and_input_races_never_publish(self):
        targets = [self.module / 'common' / name for name in
                   ('composite_font.py', 'composite_layout.py', 'luoshu_composite.sh', 'font_check.sh')]
        for target in targets + self.sources:
            with self.subTest(target=target.name):
                result = self.build(extra_env={'FIXED_MUTATE_AFTER_GEN': str(target)})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(list(self.cache.glob('*.otf')))
                self.assertFalse(list(self.cache.glob('*.receipt')))
                self.assertFalse(list(self.scope_tmp.iterdir()))

    def test_atomic_publication_dependency_and_input_races_never_publish(self):
        bin_dir = self.root / 'bin'; bin_dir.mkdir()
        real_mv = shutil.which('mv')
        (bin_dir / 'mv').write_text('#!/bin/sh\n' + real_mv + ' "$@" || exit $?\n'
                                  'last=""; for value in "$@"; do last="$value"; done\n'
                                  'case "$last" in "$FIXED_CACHE"/*.otf) printf "\\n# changed during real rename\\n" >> "$FIXED_PUBLISH_MUTATE" ;; esac\n')
        (bin_dir / 'mv').chmod(0o755)
        self.cache.mkdir(parents=True)
        sentinel = self.cache / '.other-owner.tmp.font'; sentinel.write_text('preserved')
        targets = [self.module / 'common' / name for name in
                   ('composite_font.py', 'composite_layout.py', 'luoshu_composite.sh', 'font_check.sh')]
        for target in targets + self.sources:
            with self.subTest(target=target.name):
                result = self.build(extra_env={'PATH': str(bin_dir) + ':' + os.environ['PATH'],
                                               'FIXED_CACHE': str(self.cache), 'FIXED_PUBLISH_MUTATE': str(target)})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(list(self.cache.glob('*.otf')))
                self.assertFalse(list(self.cache.glob('*.receipt')))
                self.assertFalse(list(self.scope_tmp.iterdir()))
                self.assertEqual(sentinel.read_text(), 'preserved')

    def test_real_validator_failure_has_no_cache_or_owned_temp(self):
        result = self.build(extra_env={'FIXED_DAMAGE_OUTPUT': '1'})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.count(self.calls), 1)
        self.assertEqual(self.count(self.validations), 1)
        self.assertFalse(list(self.cache.glob('*.otf')))
        self.assertFalse(list(self.scope_tmp.iterdir()))

    def test_real_fixed_router_repairs_cache_before_next_transaction(self):
        _, cached = self.good()
        original = cached.read_bytes()
        cached.write_bytes(b'damaged-cache-block' * 456)
        router = self.module / 'common/legacy_v14_4/mix_router.sh'
        result = subprocess.run(['sh', str(router), 'start', 'CJK', 'Latin', 'Digit', 'wght=400', 'wght=400', 'wght=400'],
                                env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(response['status'], 'ok', response)
        task = response['data']['task']; deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            config = values(self.module / 'config/axes_task.conf')
            if config.get('task') == task and config.get('state') in ('success', 'failed') and not list((self.module / '.luoshu-state/tasks').glob('*.owner.json')):
                break
            time.sleep(.04)
        self.assertEqual(config.get('state'), 'success', config)
        self.assertEqual(self.count(self.calls), 2)
        next_font = self.module / '.luoshu-payload-next/system/fonts/Roboto-Regular.ttf'
        self.assertEqual(next_font.read_bytes(), original)
        with TTFont(next_font, recalcTimestamp=False) as font:
            self.assertTrue(set(map(ord, 'Aa09中文')).issubset(font.getBestCmap()))
        receipt = values(self.module / 'config/mix-commit.conf')
        self.assertEqual(receipt['requestId'], config['requestId'])
        status = subprocess.run(['sh', str(router), 'status', task], env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(json.loads(status.stdout)['data']['state'], 'success', status.stdout + status.stderr)
        self.assertEqual(json.loads(status.stdout)['data']['liveApplied'], False)
        self.assertEqual(self.sentinel_file.read_text(), 'preserved')

    def test_timeout_and_cancel_retire_only_owned_temp_and_workers(self):
        sentinel = subprocess.Popen(['sleep', '30'])
        self.addCleanup(sentinel.wait)
        self.addCleanup(lambda: sentinel.kill() if sentinel.poll() is None else None)
        self.cache.mkdir(parents=True)
        cache_sentinel = self.cache / '.other-owner.tmp.font'; cache_sentinel.write_text('preserved')
        for mode in ('timeout', 'cancel'):
            with self.subTest(mode=mode):
                self.ready.unlink(missing_ok=True)
                task = f'fixed-{mode}'
                pidfile = self.module / '.luoshu-state/tasks' / f'{task}.pid'
                args = [sys.executable, str(self.module / 'common/task_scope.py'), 'run', '--pid-file', str(pidfile),
                        '--task', task, '--timeout', '2' if mode == 'timeout' else '15', '--',
                        'sh', str(self.driver), *map(str, self.sources)]
                proc = subprocess.Popen(args, env={**self.env, 'FIXED_HOLD': '1'}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                deadline = time.monotonic() + 5
                while not self.ready.exists() and time.monotonic() < deadline and proc.poll() is None:
                    time.sleep(.02)
                self.assertTrue(self.ready.exists())
                owner = json.loads(Path(str(pidfile) + '.owner.json').read_text())
                if mode == 'cancel':
                    cancelled = subprocess.run([sys.executable, str(self.module / 'common/task_scope.py'), 'cancel', str(pidfile), task],
                                               env=self.env, capture_output=True, text=True, timeout=8)
                    self.assertEqual(cancelled.returncode, 0, cancelled.stdout + cancelled.stderr)
                stdout, stderr = proc.communicate(timeout=8)
                self.assertNotEqual(proc.returncode, 0, stdout + stderr)
                proof = json.loads(Path(str(pidfile) + '.cleanup.json').read_text())
                self.assertTrue(proof['cleaned'], proof)
                self.assertEqual(proof['task'], task)
                self.assertEqual(proof['leftoverPids'], [])
                self.assertFalse(Path(owner['temporary']).exists())
                self.assertFalse(pidfile.exists())
                self.assertIsNone(sentinel.poll())
                self.assertEqual(cache_sentinel.read_text(), 'preserved')
                self.assertEqual(self.sentinel_file.read_text(), 'preserved')
                self.assertFalse(list(self.cache.glob('*.otf')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
