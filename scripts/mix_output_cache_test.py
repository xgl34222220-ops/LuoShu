#!/usr/bin/env python3
"""Composite output cache must reuse glyphs without reusing task ownership."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('mix_output_cache', ROOT / 'common/mix_output_cache.py')
cache = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cache)
ROUTER = ROOT / 'common/legacy_v14_4/mix_router.sh'
PATHS = ('/system/fonts/Detected.ttf', '/product/framework/odd-font', '/system/fonts/Alias.ttf')


class CompositeCacheTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='luoshu-mix-cache-')
        self.addCleanup(self.temp.cleanup)
        self.module = Path(self.temp.name)
        self.stage = self.module / '.luoshu-mix-stage'
        self.cache = self.module / 'config/mix-inventory-cache'
        for relative in ('config', 'common/legacy_v14_4', 'common/python/bin', 'logs', 'bin'):
            (self.module / relative).mkdir(parents=True)
        (self.module / 'module.prop').write_text('id=LuoShu\n')
        for name in ('mix_output_cache.py', 'mix_stage_watchdog.py'):
            shutil.copyfile(ROOT / 'common' / name, self.module / 'common' / name)
        self.script('common/python/bin/luoshu-python',
            f'#!/bin/sh\nunset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH\nexec {sys.executable} "$@"\n')
        self.script('common/inventory_font_stage.sh', f'''#!/bin/sh
[ "$1" != --ensure-inventory ] || exit 0
exec {sys.executable} "$LUOSHU_REAL_MODDIR/common/test_mapper.py" "$1"
''')
        (self.module / 'common/test_mapper.py').write_text('''import json, os, sys
from pathlib import Path
import mix_output_cache as cache
stage = Path(sys.argv[1]); module = stage.parent
with (module / 'mapping-calls').open('a') as stream: stream.write('mapped\\n')
if (module / 'fail-mapping').exists(): raise SystemExit(19)
paths = ['/system/fonts/Detected.ttf', '/product/framework/odd-font', '/system/fonts/Alias.ttf']
source = stage / cache.STORE / 'mix-composite.font'
for number, logical in enumerate(paths):
    target = stage / logical[1:]; target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    if number: os.link(stage / paths[0][1:], target)
    else: target.write_bytes(b'generated:' + source.read_bytes())
manifest = {'schema': 'inventory-font-output-v1', 'mode': 'mix',
    'anchors': cache.anchors(stage)[1],
    'inventory': cache.inventory_proof(module),
    'files': {logical: cache.digest(stage / logical[1:]) for logical in paths}}
cache.write_json(stage / cache.OUTPUT, manifest)
(stage / '.luoshu-metrics-covered.lst').write_text(''.join(path + '\\n' for path in paths))
cache.write_json(stage / '.luoshu-metrics-report.json', {'summary': {'mapped': len(paths)}})
if (module / 'change-source').exists(): source.write_bytes(b'changed-after-generation')
''')
        self.inventory = {'schema': 'device-font-inventory-v1', 'state': 'ready',
                          'slots': {path: {} for path in PATHS},
                          'discoveredFontRoots': [{'logical': '/product/framework'}]}
        cache.write_json(self.module / 'config/device_font_inventory.json', self.inventory)
        self.env = {**os.environ, 'MODDIR': str(self.module), 'LUOSHU_REAL_MODDIR': str(self.module),
                    'PATH': str(self.module / 'bin') + os.pathsep + os.environ['PATH']}
        self.request('one')

    def script(self, relative, text):
        path = self.module / relative
        path.write_text(text)
        path.chmod(0o755)

    def request(self, request, source=b'composite-source', weight=400):
        if self.stage.exists():
            shutil.rmtree(self.stage)
        store = self.stage / cache.STORE
        store.mkdir(parents=True)
        (store / 'mix-composite.font').write_bytes(source)
        self.request_id = request
        generation = f'requestId={request}\ncjk=CJK\nlatin=Latin\ndigit=Digit\ncompositeHash=source\n'
        (self.stage / '.luoshu-mix-generation.conf').write_text(generation)
        (self.module / 'config/mix-stage-next.conf').write_text(generation + 'previousFont=old\n')
        (self.module / 'config/axes_task.conf').write_text(f'task=task-{request}\nstate=running\n')
        cache.write_json(store / cache.WEIGHTS, {'schema': 'luoshu-mix-source-weights-v1', 'requestId': request,
            'sources': {'mix-composite.font': {'targetWeight': weight, 'cjkMode': 'fixed',
                'latinAxes': 'wght=400', 'digest': cache.digest(store / 'mix-composite.font')}}})

    def apply(self):
        return subprocess.run([sys.executable, str(self.module / 'common/mix_output_cache.py'), 'apply',
            '--module', str(self.module), '--stage', str(self.stage), '--request', self.request_id],
            env=self.env, capture_output=True, text=True, timeout=5)

    def router(self):
        return subprocess.run(['sh', str(ROUTER), 'finalize'],
            env={**self.env, 'LUOSHU_MIX_REQUEST_ID': self.request_id},
            capture_output=True, text=True, timeout=8)

    def expect_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def count(self):
        return len((self.module / 'mapping-calls').read_text().splitlines())

    def entries(self):
        return [path for path in self.cache.iterdir() if not path.name.startswith('.')]

    def test_repeated_request_reuses_output_and_rebinds_exact_anchor_proof(self):
        self.expect_ok(self.apply())
        self.request('two')
        self.expect_ok(self.apply())
        self.assertEqual(self.count(), 1)
        self.assertEqual(cache.read_json(self.stage / cache.OUTPUT)['anchors'], cache.anchors(self.stage)[1])
        self.assertIn('requestId=two\n', (self.stage / '.luoshu-mix-generation.conf').read_text())
        self.assertEqual((self.stage / PATHS[1][1:]).read_bytes(), b'generated:composite-source')
        for path in self.entries()[0].rglob('*'):
            self.assertNotIn(path.name, ('.luoshu-mix-generation.conf', '.luoshu-precommit-ready.conf', cache.WEIGHTS, cache.SNAPSHOT))
        self.assertFalse((self.stage / cache.SNAPSHOT).exists())

    def test_real_inventory_engine_output_is_cached_and_later_repair_accepts_its_proof(self):
        # Exercise the real writer and its canonical inventory/anchor proof,
        # including a stock-only script and an extensionless OEM destination.
        from inventory_font_stage_test import InventoryStageTest, source_font, engine
        fixture = InventoryStageTest(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.module, fixture.stage = self.module, self.stage
        points = {ord('A'), ord('B'), ord('0'), 0x4e2d}
        source_font(self.stage / cache.STORE / 'mix-composite.font', points=points, right=430)
        real_source = (self.stage / cache.STORE / 'mix-composite.font').read_bytes()
        self.request('real-one', source=real_source)
        fixture.inventory({path: fixture.slot(points=points | {0x03b1}) for path in PATHS})
        self.assertFalse(cache.restore(self.module, self.stage, 'real-one', self.cache))
        before = cache.anchors(self.stage)[1]
        result = engine.run(self.module, self.stage, 'mix', family='mix')
        self.assertEqual(result['mapped'], 3)
        self.assertEqual(cache.anchors(self.stage)[1], before, 'Mix writer must retain input anchors')
        self.assertTrue(cache.store(self.module, self.stage, 'real-one', self.cache))
        expected = {path: (self.stage / path[1:]).read_bytes() for path in PATHS}
        self.request('real-two', source=real_source)
        self.assertTrue(cache.restore(self.module, self.stage, 'real-two', self.cache))
        for path, original in expected.items():
            self.assertEqual((self.stage / path[1:]).read_bytes(), original)
        self.assertEqual(cache.read_json(self.stage / cache.OUTPUT)['anchors'], engine.anchors_digest(self.stage / cache.STORE, {}))
        plan = self.module / 'config/repair.lst'
        plan.write_text(PATHS[0] + '\n')
        result = engine.run(self.module, self.stage, 'mix', family='mix', plan=plan)
        self.assertEqual(result['mapped'], 3)
        self.assertEqual(result['failed'], 0)

    def test_changed_sources_weights_inventory_routes_and_engine_invalidate(self):
        self.expect_ok(self.apply())
        self.request('source', source=b'another-source')
        self.expect_ok(self.apply())
        self.request('weights', source=b'another-source', weight=550)
        self.expect_ok(self.apply())
        self.request('inventory', source=b'another-source', weight=550)
        self.inventory['buildKey'] = 'updated'
        cache.write_json(self.module / 'config/device_font_inventory.json', self.inventory)
        self.expect_ok(self.apply())
        self.request('routes', source=b'another-source', weight=550)
        (self.module / 'config/device_font_roots.conf').write_text('product|framework|root\n')
        self.expect_ok(self.apply())
        self.request('engine', source=b'another-source', weight=550)
        (self.module / 'common/another_engine.py').write_text('REVISION=2\n')
        self.expect_ok(self.apply())
        self.assertEqual(self.count(), 6)
        self.assertLessEqual(len(self.entries()), 3)

    def test_same_size_corruption_with_preserved_mtime_cannot_hit(self):
        self.expect_ok(self.apply())
        target = self.entries()[0] / 'tree' / PATHS[0][1:]
        original = target.stat()
        target.write_bytes(b'x' * original.st_size)
        os.utime(target, ns=(original.st_atime_ns, original.st_mtime_ns))
        self.request('two')
        self.expect_ok(self.apply())
        self.assertEqual(self.count(), 2)
        self.assertEqual((self.stage / PATHS[0][1:]).read_bytes(), b'generated:composite-source')

    def test_changed_cached_report_or_missing_alias_rebuilds(self):
        self.expect_ok(self.apply())
        (self.entries()[0] / 'tree/.luoshu-metrics-report.json').write_text('{}')
        self.request('two')
        self.expect_ok(self.apply())
        (self.entries()[0] / 'tree' / PATHS[1][1:]).unlink()
        self.request('three')
        self.expect_ok(self.apply())
        self.assertEqual(self.count(), 3)

    def test_restore_cleans_unmapped_fonts_but_preserves_nonfont_current_metadata(self):
        self.inventory['slots']['/system/fonts/Protected.ttf'] = {'protected': True}
        cache.write_json(self.module / 'config/device_font_inventory.json', self.inventory)
        self.expect_ok(self.apply())
        self.request('two')
        (self.stage / 'system/fonts/Protected.ttf').write_bytes(b'old-font')
        (self.stage / 'system/fonts/Old.ttf').write_bytes(b'old-font')
        extra = self.stage / 'product/framework/unlisted-font'
        extra.parent.mkdir(parents=True)
        extra.write_bytes(b'OTTOoldfont')
        (self.stage / 'product/framework/keep.txt').write_text('current-user-choice')
        self.expect_ok(self.apply())
        self.assertEqual(self.count(), 1)
        self.assertFalse((self.stage / 'system/fonts/Protected.ttf').exists())
        self.assertFalse((self.stage / 'system/fonts/Old.ttf').exists())
        self.assertFalse(extra.exists())
        self.assertEqual((self.stage / 'product/framework/keep.txt').read_text(), 'current-user-choice')

    def test_restore_damaged_symlink_cannot_write_outside_stage(self):
        self.expect_ok(self.apply())
        output = self.entries()[0] / 'tree' / PATHS[0][1:]
        external = self.module / 'untouched'
        external.write_bytes(b'preserve')
        output.unlink(); output.symlink_to(external)
        self.request('two')
        self.expect_ok(self.apply())
        self.assertEqual(self.count(), 2)
        self.assertEqual(external.read_bytes(), b'preserve')

    def test_restore_rename_failure_keeps_original_isolated_stage(self):
        self.expect_ok(self.apply())
        self.request('two')
        before = (self.stage / '.luoshu-mix-generation.conf').read_bytes()
        real_rename = os.rename
        def fail_install(source, target):
            if str(source).split('/')[-1].startswith('.luoshu-mix-cache-restore.'):
                raise OSError('injected rename failure')
            return real_rename(source, target)
        with mock.patch.object(cache.os, 'rename', side_effect=fail_install):
            self.assertFalse(cache.restore(self.module, self.stage, 'two', self.cache))
        self.assertEqual((self.stage / '.luoshu-mix-generation.conf').read_bytes(), before)
        self.assertFalse((self.stage / PATHS[0][1:]).exists())
        self.assertFalse(list(self.module.glob('.luoshu-mix-cache-restore.*')))
        self.assertFalse(list(self.module.glob('.luoshu-mix-cache-backup.*')))

    def test_stale_request_does_not_restore_or_claim_new_request(self):
        self.expect_ok(self.apply())
        self.request('two')
        with self.assertRaises(cache.InputsChanged):
            cache.restore(self.module, self.stage, 'one', self.cache)
        self.assertFalse((self.stage / PATHS[0][1:]).exists())

    def test_hashes_deduplicate_hardlinked_font_aliases(self):
        self.expect_ok(self.apply())
        tree = self.entries()[0] / 'tree'
        real_open = Path.open
        opened = []
        def watch_open(path, *args, **kwargs):
            if path.name in ('Detected.ttf', 'Alias.ttf', 'odd-font'):
                opened.append(path)
            return real_open(path, *args, **kwargs)
        with mock.patch.object(Path, 'open', watch_open):
            cache.verify_outputs(tree)
        self.assertEqual(len(opened), 1)

    def test_storage_budget_rejects_oversized_entry_and_counts_hardlinks_once(self):
        self.assertFalse(cache.restore(self.module, self.stage, 'one', self.cache))
        result = subprocess.run([sys.executable, str(self.module / 'common/test_mapper.py'), str(self.stage)],
                                env=self.env, capture_output=True, text=True)
        self.expect_ok(result)
        with mock.patch.object(cache, 'CACHE_MAX_BYTES', 1):
            self.assertFalse(cache.store(self.module, self.stage, 'one', self.cache))
        self.assertEqual(list(self.cache.iterdir()), [])
        cache.store(self.module, self.stage, 'one', self.cache)
        entry = self.entries()[0]
        logical_bytes = sum(p.stat().st_size for p in entry.rglob('*') if p.is_file())
        self.assertEqual(logical_bytes - cache.tree_bytes(entry), 2 * len(b'generated:composite-source'))
        with mock.patch.object(cache, 'CACHE_MAX_BYTES', 1):
            cache.prune(self.cache)
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_abandoned_cache_store_is_removed_before_next_request(self):
        abandoned = self.cache / '.stage.dead-writer'
        abandoned.mkdir(parents=True)
        (abandoned / 'retained-font').write_bytes(b'abandoned')
        self.expect_ok(self.apply())
        self.assertFalse(abandoned.exists())

    def test_charstring_compiler_changes_invalidate_engine_fingerprint(self):
        helper = self.module / 'common/font_charstring_compile.py'
        helper.write_bytes((ROOT / 'common/font_charstring_compile.py').read_bytes())
        before = cache.snapshot(self.module, self.stage, 'one')['key']
        with helper.open('a') as stream:
            stream.write('\n# changed compiler implementation\n')
        after = cache.snapshot(self.module, self.stage, 'one')['key']
        self.assertNotEqual(before, after)

    def test_abandoned_restore_and_backup_are_reaped_without_following_symlinks(self):
        pending = self.module / '.luoshu-mix-cache-restore.dead'
        backup = self.module / '.luoshu-mix-cache-backup.dead'
        for path in (pending, backup):
            path.mkdir()
            (path / 'retained-font').write_bytes(b'abandoned')
        external = self.module / 'unrelated-directory'
        external.mkdir(); (external / 'keep').write_text('safe')
        linked = self.module / '.luoshu-mix-cache-restore.symlink'
        linked.symlink_to(external, target_is_directory=True)
        cache.reap_abandoned(self.module, self.stage, 'one', self.cache)
        self.assertFalse(pending.exists())
        self.assertFalse(backup.exists())
        self.assertTrue(linked.is_symlink())
        self.assertEqual((external / 'keep').read_text(), 'safe')

    def test_abrupt_exit_between_restore_renames_retains_recoverable_backup(self):
        self.expect_ok(self.apply())
        self.request('two')
        script = r'''import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1] + '/common')
import mix_output_cache as cache
module = Path(sys.argv[1]); stage = module / '.luoshu-mix-stage'
original = os.rename
def abort_install(source, target):
    if Path(source).name.startswith('.luoshu-mix-cache-restore.'):
        os._exit(91)
    return original(source, target)
os.rename = abort_install
cache.restore(module, stage, 'two', module / 'config/mix-inventory-cache')
'''
        result = subprocess.run([sys.executable, '-c', script, str(self.module)], timeout=5)
        self.assertEqual(result.returncode, 91)
        self.assertFalse(self.stage.exists())
        backups = list(self.module.glob('.luoshu-mix-cache-backup.*'))
        pending = list(self.module.glob('.luoshu-mix-cache-restore.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(len(pending), 1)
        cache.reap_abandoned(self.module, self.stage, 'two', self.cache)
        self.assertTrue(backups[0].exists(), 'Absent stage must retain recoverable source')
        # Recovery (or a newly created valid request stage) establishes ownership
        # before the next apply is allowed to reap either old private clone.
        os.rename(backups[0], self.stage)
        self.expect_ok(self.apply())
        self.assertEqual(self.count(), 1)
        self.assertFalse(list(self.module.glob('.luoshu-mix-cache-backup.*')))
        self.assertFalse(list(self.module.glob('.luoshu-mix-cache-restore.*')))

    def test_stale_request_or_incomplete_stage_cannot_reap_its_backup(self):
        backup = self.module / '.luoshu-mix-cache-backup.dead'
        backup.mkdir(); (backup / 'retained-font').write_bytes(b'backup')
        with self.assertRaises(cache.InputsChanged):
            cache.reap_abandoned(self.module, self.stage, 'old-request', self.cache)
        self.assertTrue(backup.exists())
        (self.stage / cache.STORE / 'mix-composite.font').unlink()
        with self.assertRaises(ValueError):
            cache.reap_abandoned(self.module, self.stage, 'one', self.cache)
        self.assertTrue(backup.exists())

    def test_router_repeated_request_commits_new_identity_with_one_mapping(self):
        self.expect_ok(self.router())
        self.request('two')
        self.expect_ok(self.router())
        self.assertEqual(self.count(), 1)
        next_path = self.module / '.luoshu-payload-next'
        self.assertIn('requestId=two\n', (next_path / '.luoshu-precommit-ready.conf').read_text())
        self.assertIn('requestId=two\n', (self.module / 'config/font-payload-next.conf').read_text())
        self.assertEqual(cache.read_json(next_path / cache.OUTPUT)['anchors'], cache.anchors(next_path)[1])

    def test_router_cache_hit_commit_failure_restores_previous_queued_selection(self):
        self.expect_ok(self.router())
        previous = (self.module / 'config/font-payload-next.conf').read_bytes()
        previous_live = self.module / '.luoshu-payload/system/fonts/Live.ttf'
        previous_live.parent.mkdir(parents=True); previous_live.write_bytes(b'live')
        self.request('two')
        real_mv = shutil.which('mv')
        self.script('bin/mv', f'''#!/bin/sh
if [ "$1" = "$MODDIR/.luoshu-mix-stage" ] && [ "$2" = "$MODDIR/.luoshu-payload-next" ]; then exit 1; fi
exec "{real_mv}" "$@"
''')
        result = self.router()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.count(), 1)
        self.assertEqual((self.module / 'config/font-payload-next.conf').read_bytes(), previous)
        self.assertEqual(previous_live.read_bytes(), b'live')
        self.assertIn('requestId=one\n', (self.module / '.luoshu-payload-next/.luoshu-mix-generation.conf').read_text())

    def test_router_source_change_mid_mapping_cannot_commit_stale_output(self):
        self.expect_ok(self.router())
        previous = (self.module / 'config/font-payload-next.conf').read_bytes()
        self.request('two', source=b'another-source')
        (self.module / 'change-source').touch()
        result = self.router()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.module / 'config/font-payload-next.conf').read_bytes(), previous)
        self.assertIn('发生变化', result.stdout)

    def test_router_failed_regeneration_after_cache_corruption_keeps_previous_selection(self):
        self.expect_ok(self.router())
        previous = (self.module / 'config/font-payload-next.conf').read_bytes()
        (self.entries()[0] / 'tree' / PATHS[1][1:]).unlink()
        self.request('two')
        (self.module / 'fail-mapping').touch()
        result = self.router()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.module / 'config/font-payload-next.conf').read_bytes(), previous)
        self.assertEqual((self.module / 'config/active_font.conf').read_text(), 'mix\n')


if __name__ == '__main__':
    unittest.main()
